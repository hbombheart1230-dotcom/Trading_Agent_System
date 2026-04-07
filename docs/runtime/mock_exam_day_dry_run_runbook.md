# Mock Exam Day Orchestration Dry-Run Runbook

- Last updated: 2026-03-08
- Scope: official mock runtime entrypoint is `scripts/run_session.py`; `scripts/run_mock_exam_day.py` remains the orchestration backend for mock preopen/closeout
- Goal: verify full-day phase orchestration (`preopen -> session -> closeout`) before market-day execution

## 1) Phase Artifact Samples (Generated)

Sample day: `2026-03-08`

- preopen:
  - `reports/dev/exam/mock_exam_day/orchestration/mock_exam_day_2026-03-08_preopen.json`
  - `reports/dev/exam/mock_exam_day/orchestration/mock_exam_day_2026-03-08_preopen.md`
- session:
  - `reports/dev/exam/mock_exam_day/orchestration/mock_exam_day_2026-03-08_session.json`
  - `reports/dev/exam/mock_exam_day/orchestration/mock_exam_day_2026-03-08_session.md`
- closeout:
  - `reports/dev/exam/mock_exam_day/orchestration/mock_exam_day_2026-03-08_closeout.json`
  - `reports/dev/exam/mock_exam_day/orchestration/mock_exam_day_2026-03-08_closeout.md`

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

- if `scripts.run_session.py --mode mock --phase intraday` (or legacy `scripts.run_m13_live_loop.py`) is alive: exit `0` (`ok session_loop_alive`)
- if process is missing: trigger `run_mock_exam_session.bat` to restart session loop

## 3) Daily Dry-Run Procedure

### A. Preopen

Run:

```powershell
C:\Trading_Agent_System\venv\Scripts\python.exe scripts\run_session.py `
  --mode mock `
  --phase preopen `
  --day 2026-03-09 `
  --env-path .env `
  --report-dir reports/dev/exam/mock_exam_day `
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
C:\Trading_Agent_System\venv\Scripts\python.exe scripts\run_session.py `
  --mode mock `
  --phase intraday `
  --day 2026-03-09 `
  --env-path .env `
  --report-dir reports/dev/exam/mock_exam_day `
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

Off-hours probe mode (pipeline verification without market session):

```powershell
C:\Trading_Agent_System\venv\Scripts\python.exe scripts\run_session.py `
  --mode mock `
  --phase intraday `
  --day 2026-03-09 `
  --env-path .env `
  --report-dir reports/dev/exam/mock_exam_day `
  --event-log-path data/logs/events.jsonl `
  --probe `
  --probe-symbol 005930 `
  --json
```

Probe pass criteria:

- `ok=true`
- `phase_result.probe_mode=offhours_session_probe`
- `phase_result.steps[0].step_id=session.offhours_probe`
- `phase_result.probe_result.ok=true`

Batch helper (same behavior):

```bat
cmd /c scripts\run_mock_exam_session_probe.bat
```
(`run_mock_exam_session_probe.bat` internally sets `MOCK_EXAM_OFFHOURS_PROBE=1`)

Off-hours simulated session mode (continuous local fill/state evaluation):

```powershell
C:\Trading_Agent_System\venv\Scripts\python.exe scripts\run_session.py `
  --mode mock `
  --phase intraday `
  --day 2026-03-09 `
  --env-path .env `
  --report-dir reports/dev/exam/mock_exam_day `
  --event-log-path data/logs/events.jsonl `
  --state-path data/state/offhours_validation.json `
  --sleep-sec 60 `
  --simulated `
  --json
```

Simulated-session pass criteria:

- `ok=true`
- `phase_result.probe_mode=offhours_simulated_session`
- `phase_result.steps[0].step_id=session.offhours_validation_loop`
- background process launched with `pid`
- local state file (`data/state/offhours_validation.json`) starts accumulating mock positions/cash transitions

Batch helper (same behavior):

```bat
cmd /c scripts\run_mock_exam_session_simulated.bat
```

Optional env switches for `run_mock_exam_session.bat`:

- `MOCK_EXAM_OFFHOURS_SIMULATED=1`
- `MOCK_EXAM_STATE_PATH=data\state\offhours_validation.json`

### C. Closeout

Run:

```powershell
C:\Trading_Agent_System\venv\Scripts\python.exe scripts\run_session.py `
  --mode mock `
  --phase closeout `
  --day 2026-03-09 `
  --env-path .env `
  --report-dir reports/dev/exam/mock_exam_day `
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
- optional off-hours session probe can verify integrated chain execution (`--allow-offhours-session-probe`) without starting live loop.
- optional off-hours simulated session can keep the full chain cycling with local mock fills (`--allow-offhours-simulated-session`) for after-hours evaluation.
- orchestration report JSON contains:
  - per-step `rc`
  - `duration_sec`
  - `stdout_tail` / `stderr_tail`
  - phase-level `failure_reason`
