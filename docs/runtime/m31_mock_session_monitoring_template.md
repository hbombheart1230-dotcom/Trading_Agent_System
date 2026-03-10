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
- Symbol allowlist (optional): `__________`
- Max order notional: `__________`

## 2. Pre-open Checks (once)

Run:

```powershell
python scripts/run_m31_mock_investor_exam_check.py --allow-offhours --json
python scripts/run_m31_slo_incident_review_check.py --json
python scripts/run_m31_agent_chain_probe.py --json
python scripts/smoke_m20_llm.py --provider openai --require-openai --show-llm-event
```

Pass criteria:

- `mock exam check ok=true` (off-hours drill mode only)
- `slo check ok=true`
- `agent chain probe ok=true`
- `smoke_m20_llm` shows `strategy=OpenAIStrategist`

At session start (`09:00+` KST), run again without `--allow-offhours`:

```powershell
python scripts/run_m31_mock_investor_exam_check.py --json
```

## 3. Intraday 5-minute Loop (repeat)

Run:

```powershell
python scripts/query_strategist_llm_events.py --limit 20
python scripts/run_live_session_summary.py --event-log-path data/logs/events_live.jsonl --report-dir reports/live_summary --lookback-min 30 --json
```

Automated alternative (recommended during session):

```powershell
scripts\run_live_session_watch.bat --once
scripts\run_live_session_watch.bat
```

- `--once`: single health check (quick spot check)
- no flag: continuous 5-minute watch loop (`sleep-sec=300`) with artifacts:
  - `reports/live_watch/live_watch_YYYY-MM-DD.jsonl`
  - `reports/live_watch/live_watch_latest.md`

Also check:

```powershell
Get-Content data/logs/events_live.jsonl -Tail 30
```

### Record Block (copy per checkpoint)

- Time (KST): `__________`
- LLM success ratio (last 20): `__________`
- LLM avg latency ms (last 20): `__________`
- LLM `strategist_error` count (last 20): `__________`
- LLM `model_no_signal` count (last 20): `__________`
- Decision mix BUY/SELL/NOOP (last 20): `__________`
- Execution flow health (`decision -> execute_from_packet`): `OK / FAIL`
- 30m summary (`cooldown_noop`, `exit_policy_sell`, `insufficient_mock_cash`): `__________`
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
