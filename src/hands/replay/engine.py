from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from hands.observability.log import RunLog
from hands.replay.bind import bind_target, subst
from hands.replay.handlers import apply_handlers
from hands.safety.engine import PolicyViolation, assert_step, assert_url
from hands.schema.artifact import ActionType, Capability, RunStatus, Witness
from hands.schema.result import FailureDetail, RunResult
from hands.session.session import BrowserSession
from hands.surface.locators import TargetNotFound

EscalateHook = Callable[[BrowserSession], Awaitable[None]]


async def replay(
    capability: Capability,
    inputs: dict[str, str],
    *,
    session: BrowserSession | None = None,
    policy=None,
    evidence_dir: Path | None = None,
    headed: bool = False,
    log: RunLog | None = None,
    on_escalate: EscalateHook | None = None,
    hitl_timeout_s: float | None = 120,
    start_url: str | None = None,
) -> RunResult:
    from hands.schema.policy import load_policy

    policy = policy or (session.policy if session else load_policy())
    run_id = session.run_id if session else uuid.uuid4().hex[:12]
    evidence_dir = evidence_dir or Path(".hands-runs") / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log = log or RunLog(evidence_dir / "replay.jsonl", policy)
    own_session = session is None
    bound = capability.bind(inputs)
    started = time.time()
    recovered: list[str] = []
    steps_executed = 0
    outputs: dict[str, str] = {}

    url = start_url or capability.entry.url
    if not url:
        raise ValueError("capability has no entry url")
    try:
        assert_url(url, policy)
    except PolicyViolation as exc:
        return _fail(run_id, "replay", None, exc.expected, exc.observed, RunStatus.BLOCKED_BY_POLICY)

    if own_session:
        session = BrowserSession(policy, evidence_dir, headed=headed, run_id=run_id)
        await session.start(url)
    else:
        assert session.driver is not None
        await session.driver.goto(url)

    assert session is not None and session.driver is not None

    async def drain(step_id: str | None) -> RunResult | None:
        seen_escalate: set[str] = set()
        for _ in range(6):
            hit = await apply_handlers(session, capability, log=log)
            if hit is None:
                return None
            recovered.append(hit.handler.id)
            if hit.status is None:
                continue
            if hit.status == RunStatus.BUSINESS_OUTCOME:
                log.event("business_outcome", code=hit.handler.outcome_code, handler=hit.handler.id)
                return RunResult(
                    status=RunStatus.BUSINESS_OUTCOME,
                    run_id=run_id,
                    mode="replay",
                    capability_id=capability.id,
                    outcome_code=hit.handler.outcome_code,
                    recovered=list(recovered),
                    duration_ms=int((time.time() - started) * 1000),
                    steps_executed=steps_executed,
                )
            if hit.status == RunStatus.ESCALATED:
                if hit.handler.id in seen_escalate:
                    obs = await session.snapshot()
                    return _fail(
                        run_id,
                        "replay",
                        step_id,
                        hit.handler.message or "still blocked after human resume",
                        obs.page_text[:400],
                        RunStatus.ESCALATED,
                    )
                seen_escalate.add(hit.handler.id)
                esc = await _escalate(
                    session,
                    capability,
                    reason=hit.handler.message or hit.handler.description,
                    step_id=step_id,
                    on_escalate=on_escalate,
                    hitl_timeout_s=hitl_timeout_s,
                    log=log,
                    started=started,
                    recovered=recovered,
                    steps_executed=steps_executed,
                )
                if esc is not None:
                    return esc
                if session.page:
                    await session.page.wait_for_timeout(400)
                continue
            if hit.status == RunStatus.FAILED:
                obs = await session.snapshot()
                return _fail(
                    run_id,
                    "replay",
                    step_id,
                    hit.handler.message or "handler fail",
                    obs.page_text[:400],
                    RunStatus.FAILED,
                )
        return None

    try:
        early = await drain(None)
        if early:
            return early

        for step in capability.steps:
            try:
                assert_step(step, capability, policy)
            except PolicyViolation as exc:
                if step.risk.value == "irreversible" and capability.policy.irreversible_requires == "hitl":
                    result = await _escalate(
                        session,
                        capability,
                        reason=str(exc),
                        step_id=step.id,
                        on_escalate=on_escalate,
                        hitl_timeout_s=hitl_timeout_s,
                        log=log,
                        started=started,
                        recovered=recovered,
                        steps_executed=steps_executed,
                    )
                    if result is not None:
                        return result
                    continue
                return _fail(
                    run_id,
                    "replay",
                    step.id,
                    exc.expected,
                    exc.observed,
                    RunStatus.BLOCKED_BY_POLICY,
                )

            target = bind_target(step.target, bound) if step.target else None
            value = subst(step.value, bound) if step.value else None
            if step.parameter:
                value = str(bound[step.parameter])

            log.event(
                "step",
                step_id=step.id,
                action=step.action.value,
                parameter=step.parameter,
            )
            try:
                if step.action == ActionType.EXTRACT:
                    if target is None:
                        raise TargetNotFound("extract missing target", expected="target", observed="")
                    raw = await session.driver.read(target)
                    if step.extract_as:
                        outputs[step.extract_as] = raw
                    steps_executed += 1
                elif step.action == ActionType.WAIT:
                    await session.page.wait_for_timeout(int(value or 300))  # type: ignore[union-attr]
                    steps_executed += 1
                else:
                    if target is None:
                        raise TargetNotFound("step missing target", expected="target", observed=step.id)
                    await session.driver.act(step.action, target, value)
                    steps_executed += 1
            except TargetNotFound as exc:
                shot = await session.screenshot_to(f"fail-{step.id}.png")
                return _fail(
                    run_id,
                    "replay",
                    step.id,
                    exc.expected,
                    exc.observed,
                    RunStatus.FAILED,
                    screenshot=str(shot),
                )
            except PolicyViolation as exc:
                return _fail(
                    run_id,
                    "replay",
                    step.id,
                    exc.expected,
                    exc.observed,
                    RunStatus.BLOCKED_BY_POLICY,
                )

            early = await drain(step.id)
            if early:
                return early
            obs = await session.snapshot()
            if capability.checkpoint.all_of and all(
                _witness_holds(obs, w, bound) for w in capability.checkpoint.all_of
            ):
                break

        obs = await session.snapshot()
        for w in capability.checkpoint.all_of:
            if not _witness_holds(obs, w, bound):
                shot = await session.screenshot_to("fail-checkpoint.png")
                return _fail(
                    run_id,
                    "replay",
                    "checkpoint",
                    f"{w.kind}:{w.value}",
                    obs.page_text[:400],
                    RunStatus.FAILED,
                    screenshot=str(shot),
                )

        for spec in capability.outputs:
            if spec.name in outputs:
                continue
            target = bind_target(spec.target, bound)
            try:
                outputs[spec.name] = await session.driver.read(target)
            except TargetNotFound as exc:
                shot = await session.screenshot_to("fail-output.png")
                return _fail(
                    run_id,
                    "replay",
                    spec.name,
                    exc.expected,
                    exc.observed,
                    RunStatus.FAILED,
                    screenshot=str(shot),
                )

        log.event("success", outputs={k: outputs[k] for k in outputs})
        return RunResult(
            status=RunStatus.SUCCESS,
            run_id=run_id,
            mode="replay",
            capability_id=capability.id,
            outputs=outputs,
            recovered=recovered,
            duration_ms=int((time.time() - started) * 1000),
            steps_executed=steps_executed,
        )
    finally:
        if own_session:
            await session.close()


def _witness_holds(obs, witness: Witness, inputs: dict) -> bool:
    value = subst(witness.value, inputs) or witness.value
    if witness.kind in {"heading", "text"}:
        return value in obs.page_text or value in obs.title
    if witness.kind == "title":
        return value in obs.title
    if witness.kind == "url_glob":
        from fnmatch import fnmatch

        return fnmatch(obs.url, value)
    return False


async def _escalate(
    session: BrowserSession,
    capability: Capability,
    *,
    reason: str,
    step_id: str | None,
    on_escalate: EscalateHook | None,
    hitl_timeout_s: float | None,
    log: RunLog,
    started: float,
    recovered: list[str],
    steps_executed: int,
) -> RunResult | None:
    obs = await session.snapshot()
    ticket = await session.escalate(reason=reason, step_id=step_id, excerpt=obs.page_text)
    log.event("escalated", escalation_id=ticket.id, reason=reason, step_id=step_id)
    if on_escalate is not None:
        await on_escalate(session)
        await session.resume()
        log.event("resumed", escalation_id=ticket.id, human_actions=ticket.human_actions)
        return None
    try:
        await session.wait_for_resume(hitl_timeout_s)
    except TimeoutError:
        return RunResult(
            status=RunStatus.ESCALATED,
            run_id=session.run_id,
            mode="replay",
            capability_id=capability.id,
            escalation_id=ticket.id,
            recovered=recovered,
            duration_ms=int((time.time() - started) * 1000),
            steps_executed=steps_executed,
            controller_at_end="human",
            failure=FailureDetail(
                step_id=step_id,
                expected="human resume",
                observed="timed out waiting for operator",
                screenshot=ticket.screenshot_path,
            ),
        )
    return None


def _fail(
    run_id: str,
    mode: str,
    step_id: str | None,
    expected: str,
    observed: str,
    status: RunStatus,
    screenshot: str | None = None,
) -> RunResult:
    return RunResult(
        status=status,
        run_id=run_id,
        mode=mode,  # type: ignore[arg-type]
        failure=FailureDetail(
            step_id=step_id,
            expected=expected,
            observed=observed[:800],
            screenshot=screenshot,
        ),
    )
