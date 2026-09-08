# Evidence

End-to-end runs against Pioneer Core.

## Discovery (LLM in the loop)

| Path | What it is |
| --- | --- |
| `discovery/discovery.jsonl` | Live-model decisions (Groq `qwen/qwen3.8-27b`) |
| `discovery/discovery-step-*.png` | Screenshots after each step |
| `discovery/capability.json` | Compiled artifact from that run |
| `discovery/result.json` | Summary |

## Capability artifacts

| Path | What it is |
| --- | --- |
| `capabilities/lookup_regular_share_balance.json` | Reviewed golden capability (also used by `hands demo`) |
| `capabilities/lookup_regular_share_balance.discovered.json` | Artifact compiled from the live discovery run |

## Replay (no model)

| Path | Result |
| --- | --- |
| `replay/success/` | member `12345` → `$4,250.17` |
| `replay/member_not_found/` | member `99999` → `business_outcome: member_not_found` |
| `replay/lakeside_tenant/` | same artifact on `/?inst=lakeside` |
| `replay/fraud_hold/` | HITL on the live session, then `$640.02` |
| `replay/from_live_discovery/` | replay of the discovered artifact (success) |
| `replay/from_live_discovery_not_found/` | replay of the discovered artifact (not found) |

Reproduce:

```bash
uv run hands demo
uv run hands discover --goal "Look up member 12345 and read their current regular share balance"
uv run hands replay --artifact evidence/capabilities/lookup_regular_share_balance.discovered.json --input member_id=12345
```
