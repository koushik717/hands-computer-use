# Hands

The layer that gives an AI agent hands.

An LLM figures out a task inside a real UI that has **no API**. The successful run is compiled into a typed, versioned **capability**. After that, an agent invokes the capability with parameters — **no model in the loop**. Replay is deterministic, allowlisted, and explicit about the three kinds of “failure” that actually happen on a teller line: a legitimate business outcome, a recoverable interstitial, and a hard stop.

This is the take-home for interface.ai’s Software Engineer role. The company prefers a core API when one exists. This system is for the long tail of back-office screens where the only interface is the one a human already uses.

## What you can run in five minutes

```bash
# Python 3.12+, uv (https://docs.astral.sh/uv/)
make install          # uv sync + Playwright Chromium

# No model key required. Starts Pioneer Core and replays the capability.
uv run hands demo
```

That demo path is the one to read first:

1. Pioneer Core (local teller console) comes up on `http://127.0.0.1:8765`
2. Replay **member 12345** → success, `regular_share_balance = $4,250.17`
3. Replay **member 99999** → `business_outcome: member_not_found` (not a crash)
4. Same artifact against **Lakeside** (`/?inst=lakeside`) — same vendor product, different labels
5. **Fraud hold** on member 77777 → human takes the live session, resumes, extract still works

Tests, including the Playwright evals against the live console:

```bash
uv run pytest -q
```

## Discovery (the one live model run)

Replay does not need a model. Discovery does. Put a key in `.env` (see `.env.example`):

```bash
cp .env.example .env
# OPENAI_API_KEY=...     or ANTHROPIC_API_KEY=...

uv run hands core                 # terminal 1
uv run hands discover \
  --goal "Look up member 12345 and read their current regular share balance" \
  --target http://127.0.0.1:8765 \
  --out evidence/capabilities/lookup_regular_share_balance.discovered.json
```

Then replay the compiled artifact:

```bash
uv run hands replay \
  --artifact evidence/capabilities/lookup_regular_share_balance.discovered.json \
  --input member_id=12345

uv run hands replay \
  --artifact evidence/capabilities/lookup_regular_share_balance.discovered.json \
  --input member_id=99999
```

`--teacher` is a deterministic stand-in of the same loop for offline evals. The checked-in discovery evidence is a **live model run** (`evidence/discovery/result.json`, `teacher: false`).

## What Pioneer Core is

A local stand-in for a credit-union **core inquiry** screen, not a shopping cart.

- No API, no `data-testid`, nested tables, workspace iframe, rotating `__VIEWSTATE`
- Credit-union vocabulary: member number, regular share `S0000`, share draft, file maintenance
- Runtime exceptions: not found, validation, permission denial, fraud hold, session expiry, first-visit notice, slow member
- Two institution skins (`pioneer`, `lakeside`) share field names and error copy and differ in chrome/labels

Open `http://127.0.0.1:8765` while a demo is running if you want to click through it yourself.

Members worth knowing:

| Member | What happens |
| --- | --- |
| `12345` | Happy path. Regular share **$4,250.17** |
| `99999` | No such membership |
| `00001` | Permission denied |
| `77777` | Fraud hold (judgment — HITL) |
| `88888` | Slow load |

## Layout

```text
src/pioneer_core/     stand-in core (hostile UI)
src/hands/
  schema/             capability + result contract
  surface/            a11y snapshot + locator cascade (Playwright is one driver)
  safety/             allowlist, risk class, redaction
  agent/              observe → decide → act (discovery only)
  record/             compile a successful trace into a capability
  replay/             production path
  session/            control lease on one live browser
  operator/           mock operator surface, real handoff
  catalog/            stretch: agent-invocable catalog
config/policy.yaml    runtime allowlist
evidence/             discovery + replay logs (see REPORT.md)
REPORT.md             design write-up
```

## Agent-facing catalog (stretch)

```bash
uv run hands core          # terminal 1
uv run hands catalog       # terminal 2 — http://127.0.0.1:8767

curl -s http://127.0.0.1:8767/v1/capabilities
curl -s -X POST http://127.0.0.1:8767/v1/capabilities/lookup_regular_share_balance/invoke \
  -H 'content-type: application/json' \
  -d '{"member_id":"12345"}'
```

That is the seam BankGPT (or any calling agent) would use: discover a capability by name, pass typed args, get a structured result.

## Operator console (HITL)

```bash
uv run hands operator      # http://127.0.0.1:8766
```

Escalations register the live browser session. The demo fraud-hold path exercises the same lease with an in-process human callback so it is reproducible without a person at the keyboard.

## Design

See [REPORT.md](REPORT.md) for architecture, the artifact schema, determinism, multi-tenant reuse, HITL, safety, and cuts.

The short version: **the model discovers; the artifact is the product; deterministic replay is how an agent invokes it in production.** Policy can block an action even if a model asked for it. “No such member” is a result, not an exception.
