# REPORT

## 1. Architecture

Hands is a **compiler**, not a chatbot with a browser. Discovery is an LLM-driven observe → decide → act loop against a live surface. The successful path is compiled into a typed **capability**. Production invocation is deterministic replay of that artifact. The model is not consulted on replay — which is the only version of this that a compliance officer can defend. interface.ai’s own framing is the same: generative comprehension, then least-privilege deterministic action; regulators audit deterministic behavior, not probabilistic promises.

One machine, three seams:

- **Pioneer Core** — a local stand-in for a credit-union inquiry screen with no API (nested tables, iframe workspace, rotating viewstate, no test IDs).
- **Hands runtime** — policy, surface driver, replay, discovery, control lease.
- **Operator / catalog** — a mock operator surface for handoff, and a small HTTP catalog so a calling agent can invoke a capability by name.

Playwright is a **driver**, not the schema. Artifacts name controls (`role`, adjacent label, vendor `name`, share ID `S0000`), never CSS-of-the-week. A desktop driver would implement the same `SurfaceDriver` against an AX tree.

I kept the runtime a single process with a CLI. Queues and multi-tenant plumbing would pretend at scale the assignment asked us not to build. The seams that *would* scale are the ones in the artifact: `app_family`, tenant overlays, handler packs, and the control lease.

## 2. Artifact schema

A capability is the contract a calling agent (BankGPT, Employee AI, a teller copilot) actually invokes:

- **parameters** — per-invocation inputs (`member_id`). Discovery values are bound, not copied into steps.
- **outputs** — named, typed, with a locator for where to read them (`regular_share_balance`).
- **steps** — the happy path only. Typed value vs literal is mutually exclusive so a reviewer can see what is fixed and what is supplied.
- **handlers** — exceptional states that must *not* be required steps. The Saturday maintenance notice is a recover handler; compiling it as step 0 would fail on visit two, when the cookie is already set.
- **checkpoint** — “are we actually on Share Inquiry?”, not “the last click did not throw”.
- **policy** — a tightening of the runtime allowlist, plus how irreversible steps are gated (`hitl` / `approval` / `block`).
- **overlays** — per-tenant locator rewrites that cannot add actions or widen policy.

Locators are a cascade, in this order of intent: visible structure a human could point at (`near_text` / `role`), then **vendor control names** (`txtMemNo`, `btnInq`) that survive tenant branding, then share IDs (`S0000`) that survive marketing copy. Rationale is stored on the target so a reviewer can disagree with it.

JSON Schema: `schema/capability.v1.json`.

## 3. Determinism & error handling

Replay never calls `make_llm`. That is a test, not a comment (`test_replay_does_not_use_a_model`).

Before each action: wait for the witness, resolve primary then fallbacks, act, settle, then run handlers against the new observation.

The result contract has three non-success shapes, on purpose:

| Kind | Example | What the caller should do |
| --- | --- | --- |
| **business_outcome** | `member_not_found`, `permission_denied`, `validation_error` | Use it. This is the answer. |
| **recover** | scheduled-maintenance notice | Dismiss and continue. Logged on `recovered`. |
| **hard fail / escalate** | missing control, policy block, fraud hold, session expiry | Stop with step + expected vs observed, or hand the live session to a human. |

Conflating “no such member” with a crash is the mistake the brief warned about. Inquiry returning nothing is a teller-line fact; the capability did its job.

Viewstate is a trap I refused: Pioneer Core rotates `__VIEWSTATE` every render. We click controls. We do not replay HTTP. That is the difference between computer-use and a brittle HAR.

Secondary drift: a failed witness is a wrong-page detector. Tenant label drift is why `txtMemNo` and `S0000` exist as fallbacks — demonstrated by replaying the Pioneer artifact against `/?inst=lakeside`.

## 4. Heterogeneity & multi-tenant

**Surface.** `ControlTarget` is the recorded flow. `WebDriver` maps it onto Playwright. A desktop driver would map the same role+name onto UI Automation / AX. The iframe is just a frame name on the candidate (`frame: ws`); a native window would be a different scope with the same fields.

**Tenants.** Hundreds of institutions run ~20 apps; many share a vendor core (Symitar, Jack Henry, Fiserv, …) with different chrome. The smallest honest model of that: Pioneer vs Lakeside. Same field names, same error copy, different labels (“Member Number” / “Acct Base”, “Regular Share” / “Primary Share”). One artifact, no re-record — demonstrated by replaying the Pioneer capability against `/?inst=lakeside`. Locator fallbacks carry both tenant labels; vendor names (`txtMemNo`, `btnInq`) and share ID `S0000` are the durable anchors. `TenantOverlay` is on the schema for per-institution rewrites that cannot widen policy; this demo uses fallbacks rather than a separate overlay file because the two skins differ only in labels.

## 5. Escalation & handoff

Stuck is detected, not guessed: a matching handler with `then: escalate`, a risk class of `judgment` / `irreversible` without approval, or the agent choosing `escalate`.

The session holds a **lease**: `agent` | `human`. The agent cannot act without it (`NotInControl`). Escalation does not open a new browser. That is the Nexus-shaped seam: AI owns the work; human judgment arrives on the *same* interaction; no transfer, no rebuilt context.

The operator UI is a thin mock (`hands operator`) — enough to show an intervention ticket and Resume. What is real is the lease, the same Playwright page, recorded human actions, and resume. The demo path uses an in-process human callback on that live session (and registers it with the operator store) so CI can prove the handoff without a person at the keyboard. Fraud hold (`77777`) is the fixture: unattended replay must not click through a hold; a human on that session can; extract still returns `$640.02`.

Session expiry is also escalate — Hands will not type credentials to “recover”.

## 6. Safety

Policy is evaluated **at the action**, not as a prompt appendix. Off-allowlist URLs never get `goto`. Irreversible names (`Confirm Open Share`, `Post Transaction`) cannot run unattended on a `draft` capability. Judgment names (`fraud hold`) escalate. Logs and artifacts redact SSN/PAN-like strings and names on the redact list; parameter *values* from discovery are not stored in steps. The demo teller session has no password. Limits: this is not SOC 2. There is no real IdP, no row-level entitlement beyond what the core already enforced, no encryption at rest. The allowlist is the guardrail that would have to sit in front of any driver we add later.

## 7. Cuts

**Built thin but real:** discovery loop, compiler, replay, three-way errors, lease-based HITL, allowlist, redaction, catalog invoke, two-tenant reuse, evals against a live hostile UI.

**Mocked on purpose:** the operator chrome (handoff is real); desktop driver (the schema does not assume a DOM); approval workflow beyond `draft`/`approved`; assisted LLM fallback on a single failed step.

**Teacher vs live model.** `hands discover --teacher` is a labeled deterministic stand-in of the same observe→act→compile loop for offline evals. The required live-model run in `/evidence/discovery/` used Groq (`qwen/qwen3.8-27b` via the OpenAI-compatible API). Replay of the compiled artifact is under `evidence/replay/from_live_discovery/`.

**Not built, would be next:** fingerprint-based drift; overlay *files* per institution (schema supports `TenantOverlay` today; this demo uses multi-label fallbacks); an eval harness that replays N times and tracks flakiness; emitting a Playwright test from an artifact; a real SSO/session broker so expiry can re-auth without putting secrets in Hands; assisted single-step LLM recovery on hard fail.

What I would not do with more time: put the model back in the production path.
