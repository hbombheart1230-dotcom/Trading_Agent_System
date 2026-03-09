# Mock Exam Day Orchestration Dry-Run Runbook

- Last updated: 2026-03-08
- Scope: `scripts/run_mock_exam_day.py` based daily mock exam operations
- Goal: verify full-day phase orchestration (`preopen -> session -> closeout`) before market-day execution

## 1) Phase Artifact Samples (Generated)

Sample day: `2026-03-08`

- preopen:
  - `reports/mock_exam_day/orchestration/mock_exam_day_2026-03-08_preopen.json`
  - `reports/mock_exam_day/orchestration/mock_exam_day_2026-03-08_preopen.md`
- session:
  - `reports/mock_exam_day/orchestration/mock_exam_day_2026-03-08_session.json`
  - `reports/mock_exam_day/orchestration/mock_exam_day_2026-03-08_session.md`
- closeout:
  - `reports/mock_exam_day/orchestration/mock_exam_day_2026-03-08_closeout.json`
  - `reports/mock_exam_day/orchestration/mock_exam_day_2026-03-08_closeout.md`

Observed sample outcome:

- preopen: `ok=true`
- session: `ok=false` (`market_closed` on off-hours run, expected for this sample day/time)
- closeout: `ok=true`

## 2) Task Scheduler Example Check (Windows)

Checked files:

- `scripts/register_mock_exam_tasks_example.bat`
- `scripts/unregister_mock_exam_tasks_example.bat`
- `scripts/run_mock_exam_preopen.bat`
- `scripts/run_mock_exam_session.bat`
- `scripts/run_mock_exam_session_watchdog.bat`
- `scripts/run_mock_exam_closeout.bat`

Validation cycle executed:

1. Register:
   - `cmd /c scripts\register_mock_exam_tasks_example.bat`
2. Query:
   - `schtasks /Query /TN TradingAgent-MockExamDay-Preopen /FO LIST`
   - `schtasks /Query /TN TradingAgent-MockExamDay-Session /FO LIST`
   - `schtasks /Query /TN TradingAgent-MockExamDay-SessionWatchdog /FO LIST`
   - `schtasks /Query /TN TradingAgent-MockExamDay-Closeout /FO LIST`
3. Cleanup:
   - `cmd /c scripts\unregister_mock_exam_tasks_example.bat`

Expected schedule template:

- preopen: `08:55`
- session: `09:00`
- session watchdog: `09:05` start, every `5 min`, duration `06:20`
- closeout: `15:35`

Watchdog behavior:

- if `scripts.run_m13_live_loop` process is alive: exit `0` (`ok session_loop_alive`)
- if process is missing: trigger `run_mock_exam_session.bat` to restart session loop

## 3) Daily Dry-Run Procedure

### A. Preopen

Run:

```powershell
C:\Trading_Agent_System\venv\Scripts\python.exe -m scripts.run_mock_exam_day `
  --phase preopen `
  --day 2026-03-09 `
  --env-path .env `
  --report-dir reports/mock_exam_day `
  --event-log-path data/logs/events.jsonl `
  --json
```

Pass criteria:

- `ok=true`
- `phase_result.steps` all `ok=true`
- runtime policy check `ok=true` (`staging/mock/manual/allow_real_execution=false`)

### B. Session

Run:

```powershell
C:\Trading_Agent_System\venv\Scripts\python.exe -m scripts.run_mock_exam_day `
  --phase session `
  --day 2026-03-09 `
  --env-path .env `
  --report-dir reports/mock_exam_day `
  --event-log-path data/logs/events.jsonl `
  --sleep-sec 60 `
  --json
```

Pass criteria:

- `ok=true`
- `phase_result.steps[0].ok=true`
- live loop process started (background launch reported with `pid`)

Fail criteria (expected off-hours):

- `failure_reason` starts with `market_closed:`

### C. Closeout

Run:

```powershell
C:\Trading_Agent_System\venv\Scripts\python.exe -m scripts.run_mock_exam_day `
  --phase closeout `
  --day 2026-03-09 `
  --env-path .env `
  --report-dir reports/mock_exam_day `
  --event-log-path data/logs/events.jsonl `
  --json
```

Pass criteria:

- `ok=true`
- closeout step order and success:
  1. `closeout.m31_slo_incident`
  2. `closeout.metrics`
  3. `closeout.operator_summary`
  4. `closeout.decision_story`
  5. `closeout.run_cards`

## 4) Operational Notes

- `session` phase enforces:
  - market-hours gate
  - runtime safety mode gate (`staging/mock/manual/allow_real_execution=false`)
- off-hours dry-runs should execute `preopen` + `closeout`, and accept `session market_closed` as expected.
- orchestration report JSON contains:
  - per-step `rc`
  - `duration_sec`
  - `stdout_tail` / `stderr_tail`
  - phase-level `failure_reason`
