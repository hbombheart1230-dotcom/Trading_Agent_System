# M31 Mock Session Monitoring Template

- Last updated: 2026-03-03
- Scope: intraday mock-investor monitoring for `staging + mock + manual approval`

## 1. Session Header (fill before start)

- Date (KST): `__________`
- Session window: `09:00-15:30`
- Operator: `__________`
- Runtime profile: `staging`
- Kiwoom mode: `mock`
- Approval mode: `manual`
- Symbol allowlist: `__________`
- Max order notional: `__________`

## 2. Pre-open Checks (once)

Run:

```powershell
python scripts/run_m31_mock_investor_exam_check.py --strict-session --json
python scripts/run_m31_slo_incident_review_check.py --json
python scripts/run_m31_agent_chain_probe.py --json
python scripts/smoke_m20_llm.py --provider openai --require-openai --show-llm-event
```

Pass criteria:

- `strict-session ok=true`
- `slo check ok=true`
- `agent chain probe ok=true`
- `smoke_m20_llm` shows `strategy=OpenAIStrategist`

## 3. Intraday 5-minute Loop (repeat)

Run:

```powershell
python scripts/query_strategist_llm_events.py --limit 20
```

Also check:

```powershell
Get-Content data/logs/events.jsonl -Tail 30
```

### Record Block (copy per checkpoint)

- Time (KST): `__________`
- LLM success ratio (last 20): `__________`
- LLM avg latency ms (last 20): `__________`
- LLM `strategist_error` count (last 20): `__________`
- LLM `model_no_signal` count (last 20): `__________`
- Decision mix BUY/SELL/NOOP (last 20): `__________`
- Execution flow health (`decision -> execute_from_packet`): `OK / FAIL`
- Guard/circuit alerts: `NONE / PRESENT`
- Operator action taken: `__________`

## 4. Intraday Triage Rules

- If `strategist_error` increases:
  - check provider/API health and retry behavior.
  - if needed, switch to fallback (`AI_STRATEGIST_PROVIDER=rule`) and continue safely.
- If `model_no_signal` is dominant:
  - verify snapshot quality (`price/cash/open_positions`), then review feature inputs.
- If latency is persistently high:
  - reduce token budget (`AI_STRATEGIST_MAX_TOKENS`) or choose lighter model.
- If circuit opens:
  - stop auto tuning; keep manual approval and investigate root cause first.

## 5. End-of-day Closeout

Run:

```powershell
python scripts/run_m29_closeout_check.py --json
python scripts/run_m31_slo_incident_review_check.py --json
```

Daily summary fields:

- Total intents: `__________`
- Approved intents: `__________`
- Executed intents: `__________`
- Blocked intents: `__________`
- Error total: `__________`
- Duplicate execution incidents: `__________`
- Top 3 improvement notes for next day:
  - `1) __________`
  - `2) __________`
  - `3) __________`
