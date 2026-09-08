from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

from hands.agent.llm import LLM, make_llm
from hands.observability.log import RunLog
from hands.record.compiler import compile_capability
from hands.replay.handlers import apply_handlers
from hands.safety.engine import PolicyViolation, assert_url, classify_risk
from hands.schema.artifact import Capability, RiskClass, RunStatus
from hands.schema.policy import RuntimePolicy, load_policy
from hands.schema.result import FailureDetail, RunResult
from hands.session.session import BrowserSession

_MEMBER = re.compile(r"\b(\d{5})\b")


def infer_params(goal: str) -> dict[str, str]:
    m = _MEMBER.search(goal)
    if m:
        return {"member_id": m.group(1)}
    return {}


async def discover(
    goal: str,
    target_url: str,
    *,
    policy: RuntimePolicy | None = None,
    evidence_dir: Path | None = None,
    headed: bool = False,
    llm: LLM | None = None,
    max_steps: int | None = None,
) -> tuple[Capability | None, RunResult]:
    policy = policy or load_policy()
    run_id = uuid.uuid4().hex[:12]
    evidence_dir = evidence_dir or Path(".hands-runs") / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log = RunLog(evidence_dir / "discovery.jsonl", policy)
    llm = llm or make_llm()
    params = infer_params(goal)
    started = time.time()
    max_steps = max_steps or policy.max_steps

    try:
        assert_url(target_url, policy)
    except PolicyViolation as exc:
        return None, RunResult(
            status=RunStatus.BLOCKED_BY_POLICY,
            run_id=run_id,
            mode="discovery",
            failure=FailureDetail(expected=exc.expected, observed=exc.observed),
        )

    session = BrowserSession(policy, evidence_dir, headed=headed, run_id=run_id)
    await session.start(target_url)
    stub = _stub_capability(target_url, policy)
    trace: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    outputs: dict[str, str] = {}
    steps_executed = 0

    try:
        for _ in range(max_steps):
            hit = await apply_handlers(session, stub, log=log)
            if hit and hit.status == RunStatus.BUSINESS_OUTCOME:
                log.event("business_outcome", code=hit.handler.outcome_code)
                return None, RunResult(
                    status=RunStatus.BUSINESS_OUTCOME,
                    run_id=run_id,
                    mode="discovery",
                    outcome_code=hit.handler.outcome_code,
                    duration_ms=int((time.time() - started) * 1000),
                    steps_executed=steps_executed,
                )
            if hit and hit.status == RunStatus.ESCALATED:
                obs = await session.snapshot()
                ticket = await session.escalate(
                    reason=hit.handler.message or hit.handler.description,
                    step_id=None,
                    excerpt=obs.page_text,
                )
                return None, RunResult(
                    status=RunStatus.ESCALATED,
                    run_id=run_id,
                    mode="discovery",
                    escalation_id=ticket.id,
                    outcome_code=hit.handler.outcome_code,
                    duration_ms=int((time.time() - started) * 1000),
                    steps_executed=steps_executed,
                    controller_at_end="human",
                )

            obs = await session.snapshot()
            await session.screenshot_to(f"discovery-step-{steps_executed:02d}.png")
            decision = await llm.decide(goal=goal, observation=obs, history=history)
            log.event(
                "decision",
                thought=decision.thought,
                action=decision.action,
                ref=decision.ref,
                text=decision.text,
                outputs=decision.outputs,
                reason=decision.reason,
            )
            history.append({"action": decision.action, "ref": decision.ref, "reason": decision.reason})

            if decision.action == "done":
                outputs.update(decision.outputs or {})
                cap = compile_capability(
                    trace=trace,
                    goal=goal,
                    target_url=target_url,
                    run_id=run_id,
                    policy=policy,
                    parameters=params,
                    outputs=outputs,
                )
                out_path = evidence_dir / "capability.json"
                out_path.write_text(cap.model_dump_json(indent=2))
                log.event("compiled", capability=cap.id)
                return cap, RunResult(
                    status=RunStatus.SUCCESS,
                    run_id=run_id,
                    mode="discovery",
                    capability_id=cap.id,
                    outcome_code=decision.outcome_code,
                    outputs=outputs,
                    duration_ms=int((time.time() - started) * 1000),
                    steps_executed=steps_executed,
                )

            if decision.action == "escalate":
                ticket = await session.escalate(
                    reason=decision.reason,
                    step_id=None,
                    excerpt=obs.page_text,
                )
                return None, RunResult(
                    status=RunStatus.ESCALATED,
                    run_id=run_id,
                    mode="discovery",
                    escalation_id=ticket.id,
                    duration_ms=int((time.time() - started) * 1000),
                    steps_executed=steps_executed,
                    controller_at_end="human",
                )

            if decision.action == "wait":
                await session.page.wait_for_timeout(400)  # type: ignore[union-attr]
                steps_executed += 1
                continue

            if decision.ref is None:
                continue

            control = obs.by_ref(decision.ref)
            risk = classify_risk(control.name, policy)
            if risk in {RiskClass.IRREVERSIBLE, RiskClass.JUDGMENT}:
                ticket = await session.escalate(
                    reason=f"{risk.value} control {control.name!r}",
                    step_id=None,
                    excerpt=obs.page_text,
                )
                return None, RunResult(
                    status=RunStatus.ESCALATED,
                    run_id=run_id,
                    mode="discovery",
                    escalation_id=ticket.id,
                    duration_ms=int((time.time() - started) * 1000),
                    steps_executed=steps_executed,
                    controller_at_end="human",
                )

            if decision.action == "click":
                await session.click_ref(decision.ref)
                trace.append({"action": "click", "control": control, "thought": decision.thought})
            elif decision.action == "type":
                text = decision.text or params.get("member_id") or ""
                await session.type_ref(decision.ref, text)
                trace.append(
                    {
                        "action": "type",
                        "control": control,
                        "text": text,
                        "thought": decision.thought,
                    }
                )
            elif decision.action == "extract":
                name = decision.extract_as or "regular_share_balance"
                outputs[name] = control.value or control.text
                trace.append(
                    {
                        "action": "extract",
                        "control": control,
                        "extract_as": name,
                    }
                )
            steps_executed += 1

        shot = await session.screenshot_to("discovery-stuck.png")
        return None, RunResult(
            status=RunStatus.FAILED,
            run_id=run_id,
            mode="discovery",
            duration_ms=int((time.time() - started) * 1000),
            steps_executed=steps_executed,
            failure=FailureDetail(
                expected="goal completed within max_steps",
                observed=f"stopped after {steps_executed} steps",
                screenshot=str(shot),
            ),
        )
    finally:
        await session.close()


def _stub_capability(url: str, policy: RuntimePolicy) -> Capability:
    from hands.record.compiler import compile_capability

    return compile_capability(
        trace=[],
        goal="",
        target_url=url,
        run_id="stub",
        policy=policy,
        parameters={"member_id": "0"},
        outputs={},
    )
