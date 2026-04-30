# Preopen Readiness 2026-04-29

## Status

Checked at `2026-04-29 08:22 KST`.

- runtime profile: `mock_live`
- broker mode: Kiwoom mock
- execution: enabled for mock broker path
- real-account execution: disabled
- official entrypoint: `scripts/run_session.py`
- intraday loop: running
- watch status: `GREEN`

## Why `mock_live`

The previous `dev` and `staging` strict profile checks intentionally expect `EXECUTION_ENABLED=false`.

Current operation is different:

- mock investment account is used as the broker path
- automatic execution is enabled for mock trading
- real-account execution remains disabled

Therefore preopen strict validation now uses `mock_live`.

## Commands Used

Profile/preflight:

```powershell
.\venv\Scripts\python.exe .\scripts\check_runtime_profile.py --profile mock_live --strict --json
.\venv\Scripts\python.exe .\scripts\run_m28_startup_preflight_check.py --profile mock_live --day 2026-04-29 --run-id preopen-20260429-mock-live --json
```

Runtime start:

```powershell
.\venv\Scripts\python.exe scripts\run_session.py --mode live --phase intraday --tick-pipeline integrated_chain --sleep-sec 30 --allow-offhours
```

Watch once:

```powershell
.\venv\Scripts\python.exe scripts\run_session.py --mode live --phase watch --once --json --event-log-path data\logs\events.jsonl --summary-report-dir reports\live_summary --watch-report-dir reports\live_watch --lock-path data\state\m13_live_loop.lock --lookback-min 10 --sleep-sec 30
```

## Results

Startup preflight:

- required checks: `4/4`
- profile gate: passed
- startup lock gate: passed
- commander runtime once smoke: passed
- shutdown gate: passed

Live watch:

- loop_alive: `true`
- watch health: `GREEN`
- event window total: `4`
- strategist LLM in last 10 min: `0`
- execution verdicts in last 10 min: `0`
- broker execution failures: `0`
- stderr: empty

The lack of strategist/decision/execution activity is acceptable before market open. The first required live check after open is that events, strategist route, scanner top candidates, and monitor blockers start appearing in the watch/canonical artifacts.

## Regression Tests

Ran before open:

```powershell
.\venv\Scripts\python.exe -m pytest .\tests\test_m28_1_runtime_profile_scaffold.py .\tests\test_m28_4_startup_preflight_check.py .\tests\test_strategist_llm_summary.py .\tests\test_strategist_explanation_contract.py .\tests\test_m31_17_theme_candidate_flow_upgrade.py .\tests\test_scanner_fallback_policy.py::test_commander_injects_scanner_policy_defaults_into_applied_policy -q
```

Result:

```text
25 passed
```

## First Checks After Market Open

- `reports/live_watch/live_watch_latest.md` remains `GREEN` or has an explainable `YELLOW`.
- `data/state/m13_live_loop.lock` heartbeat updates within one loop interval.
- `reports/canonical/2026-04-29/<run_id>/commander.json` appears.
- strategist route records fresh/cached/fallback explicitly.
- if Kiwoom theme data is available, strategist `selected_themes` is non-empty.
- scanner top candidates include top5/topN traces.
- monitor blockers, if any, include blocker counts and commander response.
- first order, if any, links executor result to broker mock result.
