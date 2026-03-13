# M31-18 Off-Hours Validation Loop

- Date: 2026-03-12
- Scope: continuous after-hours validation path for integrated mock exam runtime without broker-side session dependency.

## Objective

- Keep evaluating the full decision chain outside market hours:
  - Commander/runtime orchestration
  - Strategist framing
  - Scanner ranking/selection
  - Monitor entry/exit logic
  - Supervisor/Executor-compatible approval/execution path
  - Reporter/observability artifacts
- Do this without sending broker mock/live orders when the market is closed.

## Why

- Market-session validation window is too short for iterative tuning.
- One-shot probe is useful but insufficient for repeated stateful evaluation.
- We need a way to treat fills as locally simulated so portfolio state can evolve across cycles after-hours.

## Added Runtime Path

- Pipeline: `graphs/pipelines/offhours_validation.py`
- Loop runner: `scripts/run_offhours_validation_loop.py`
- Orchestration hook:
  - `scripts/run_mock_exam_day.py --phase session --allow-offhours-simulated-session`

## Runtime Contract

- Hard safety:
  - force `EXECUTION_MODE=mock`
  - force `ALLOW_REAL_EXECUTION=false`
- Local persistence:
  - use `STATE_STORE_PATH` / `--state-path` for isolated after-hours state if needed
- Shared observability:
  - use `EVENT_LOG_PATH` / `--event-log-path`
  - keep decision trace / evidence ledger / reports compatible with normal runtime

## Intended Usage

### Direct loop

```powershell
python -m scripts.run_offhours_validation_loop `
  --env-path .env `
  --event-log-path data/logs/events.jsonl `
  --state-path data/state/offhours_validation.json `
  --sleep-sec 60
```

### Mock exam day session phase

```powershell
python -m scripts.run_mock_exam_day `
  --phase session `
  --env-path .env `
  --event-log-path data/logs/events.jsonl `
  --state-path data/state/offhours_validation.json `
  --allow-offhours-simulated-session `
  --sleep-sec 60 `
  --json
```

## Expected Benefits

- Repeated after-hours evaluation of:
  - candidate selection quality
  - strategy framing consistency
  - monitor sell/buy behavior on persisted positions
  - reporting/trace visibility
- Safer tuning because broker market-session dependency is removed from this path.

## Limits

- This does not validate broker acceptance/session rules.
- This does not replace actual market-hour mock investor exam.
- Price evolution is still limited by available mock/local data sources unless enriched separately.
