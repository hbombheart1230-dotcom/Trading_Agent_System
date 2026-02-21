# M31-2: Mock Investor Exam Protocol (Kiwoom Mock, Production-like)

- Date: 2026-02-21
- Goal: define a production-like mock trading exam protocol before approval automation expansion.
- Scope: strategy validation using live-market hours + replay, with strict safety-first operations.

## Core Answer (Market Hours)

- You can start the process before market open.
- Real-time mock exam quality is meaningful during regular market session.
- Current market-hours contract in code:
  - source: `libs/runtime/market_hours.py`
  - default session: weekday `09:00-15:30` (KST)
- Tick pipeline behavior:
  - source: `graphs/pipelines/m13_tick.py`
  - market closed -> `tick_skipped=True` and no trade pipeline execution.

## Runtime Mode Policy (Fixed)

- Use staging/mock profile for exam:
  - `RUNTIME_PROFILE=staging`
  - `KIWOOM_MODE=mock`
  - `ALLOW_REAL_EXECUTION=false`
  - `EXECUTION_ENABLED=true`
  - `APPROVAL_MODE=manual` (mandatory in first phase)
- Keep guardrails fixed for whole exam window:
  - allowlist required
  - max notional cap
  - daily loss cap
  - degrade fallback policy enabled

## Daily Exam Runbook (KST)

1. Pre-open preparation (`08:20-08:50`)
- Validate go-live baseline artifacts from M30.
- Run preflight and launch wrapper checks.
- Freeze strategy set and risk budget for the day.

2. Session runtime (`09:00-15:30`)
- Run mock execution with manual approval.
- Record all approvals/rejections and guard blocks.
- Track incident/error timeline and intervention actions.

3. Post-close closeout (`15:35-16:10`)
- Generate daily closeout report and metric snapshot.
- Review safety failures first, then strategy quality.
- Decide next-day parameter changes (single batch update only).

## Operator Commands (Reference)

```bash
python scripts/run_m30_final_golive_signoff.py --json
python scripts/run_m30_post_golive_monitoring_policy.py --json

python scripts/run_m28_startup_preflight_check.py --profile staging --env-path .env --json
python scripts/run_m28_scheduler_worker_launch_wrapper_check.py --profile staging --env-path .env --json
python scripts/run_m28_launch_hook_integration_check.py --profile staging --env-path .env --json

python scripts/run_m13_live_loop.py --sleep-sec 60
python scripts/run_m29_closeout_check.py --json
python scripts/run_m31_agent_chain_probe.py --json
python scripts/run_commander_runtime_once.py --mode integrated_chain --json
python scripts/smoke_m20_llm.py --provider openai --require-openai --show-llm-event
```

## Execution Artifact (Implemented)

- script: `scripts/run_m31_mock_investor_exam_check.py`
- role: validates fixed runtime-mode policy, guardrail configuration, market-hours contract, and tick behavior for M31-B exam operations.
- output:
  - `reports/m31_mock_exam/m31_mock_exam_<day>.json`
  - `reports/m31_mock_exam/m31_mock_exam_<day>.md`

- script: `scripts/run_m31_agent_chain_probe.py`
- role: visualizes end-to-end agent chain (`strategist -> scanner -> monitor -> decision -> execute`) with one JSON artifact-like output for operator understanding.

```bash
python scripts/run_m31_mock_investor_exam_check.py \
  --env-path .env \
  --event-log-path data/logs/events.jsonl \
  --report-dir reports/m31_mock_exam \
  --day 2026-02-21 \
  --json

python scripts/run_m31_agent_chain_probe.py --json
```

## Verified Runtime Snapshot (2026-02-21)

- `python scripts/run_m31_mock_investor_exam_check.py --json`
  - `ok=true`
  - required checks passed; `session_window_check` is informational when `--strict-session` is not used.
- `python scripts/run_m31_mock_investor_exam_check.py --strict-session --json`
  - fails outside weekday `09:00-15:30` KST by design.
- `python scripts/run_m31_agent_chain_probe.py --json`
  - `ok=true`
  - chain: `commander_router -> strategist -> scanner -> monitor -> decision -> supervisor -> executor -> reporter`
- `python scripts/run_commander_runtime_once.py --mode integrated_chain --json`
  - `runtime_mode=integrated_chain`, `path=integrated_chain`, `execution_allowed=true` (non-live stub smoke)
- `python scripts/smoke_m20_llm.py --provider openai --require-openai --show-llm-event`
  - strategist selection can be validated as `OpenAIStrategist` directly from `.env` (script loads `.env` before argument defaults).
  - current observed behavior (2026-02-21): LLM call succeeds (`ok=true`) and returns schema-normalized intent (currently `NOOP` on this sample input).

## Strategy Design Package (What To Fix Before Exam)

1. Universe and session policy
- tradable symbols
- no-trade windows
- max concurrent intents

2. Feature set
- technical: `rsi14`, `ma20_gap`, `atr14`, `volume_spike20`, `volatility20`, `regime`, `signal_score`
- source: `libs/runtime/feature_engine.py`

3. News and sentiment
- per-symbol sentiment + global sentiment
- negative-news risk penalty policy

4. Prompt and output contract
- structured input fields only
- strict JSON output
- include confidence, risk reason, and fallback reason fields
- provider JSON mode control:
  - `AI_STRATEGIST_JSON_RESPONSE_FORMAT=true` (default)
  - when provider rejects `response_format`, adapter retries once without it.

5. Position sizing and exit policy
- sizing source: `libs/runtime/position_sizing.py`
- exit source: `libs/runtime/exit_policy.py`
- emergency halt conditions mandatory

## Approval Progression Rule

1. Phase A (required)
- `manual` approval only
- measure what auto-approval would have done as shadow analysis in reports

2. Phase B (limited auto)
- enable scoped auto approval only when Phase A safety gates stay green
- keep hard risk caps and intervention controls unchanged

## Exam Pass/Fail Gates

1. Safety gates (must-pass)
- duplicate execution: zero
- guard precedence violation: zero
- real-execution leakage in mock mode: zero

2. Stability gates
- incident recovery time within target
- no uncontrolled retry loops
- alert escalation path deterministic

3. Strategy quality gates
- scorecard baseline met across replay + session exam days
- no single-day tail loss breach against daily risk cap

## Exit Criteria (M31-B Completion)

- safety gates remain green for exam window.
- manual-approval exam evidence is sufficient for scoped auto-approval trial.
- strategy set and risk budget are versioned and reproducible for next phase.
