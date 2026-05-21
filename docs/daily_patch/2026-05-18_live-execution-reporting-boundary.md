# 2026-05-18 Live Execution Reporting Boundary

## Out-of-Plan Refactor - Live Execution Reporting Boundary

### Scope

This work was originally documented as Phase 11, but the reporting hotspot plan uses Phase 11 for `trade_report_ai.py`.

The entries below are retained as completed live-execution reporting boundary work and should not be treated as the active Phase 11 plan.

The live session is intentionally left running. This phase avoids live restart and keeps the currently running process collecting data.

### Phase 11.1 - Post-Exit Shadow Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_post_exit.py`

Extracted responsibilities:

- runtime minute OHLCV row selection for a symbol
- post-exit shadow lookup from lifecycle/lifecycle bundle
- post-exit shadow attachment to generated trade report payloads

Design intent:

- reduce `live_execution_bundle_runner.py` without changing report behavior
- keep existing private runner function names available through imports
- keep post-exit observation logic isolated for future closeout/recap expansion

Runtime policy:

- no live restart
- no live trading behavior change
- reporting/report-bundle boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_post_exit.py`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

### Phase 11.2 - Live Execution Report Artifact Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_report_artifacts.py`

Extracted responsibilities:

- full-report artifact deferral decision
- before-full-close diagnostic report reason selection
- deferred trade report artifact cleanup
- existing report corruption/conflict checks
- legacy JSON/text artifact read/write helpers
- report-generation exception message sanitization

Design intent:

- keep report artifact policy and filesystem hygiene out of the live execution bundle orchestration body
- preserve the runner's existing private helper names through import aliases
- keep behavior unchanged while making later report-generation cleanup easier

Runtime policy:

- no live restart
- no live trading behavior change
- report bundle generation boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_report_artifacts.py libs\reporting\live_execution_post_exit.py`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

### Phase 11.3 - Live Execution Lifecycle Recovery Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_lifecycle_recovery.py`

Extracted responsibilities:

- partial SELL lifecycle reconciliation to closed when quantity evidence proves full liquidation
- recovered large closeout quantity handling
- closed SELL lifecycle summary refresh
- hold-placeholder reason detection
- remaining quantity hint and positive quantity helpers

Design intent:

- separate lifecycle recovery policy from report bundle orchestration
- keep existing runner helper names available through import aliases
- make future partial/closeout fixes local to a small module

Runtime policy:

- no live restart
- no live trading behavior change
- report lifecycle recovery boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_lifecycle_recovery.py libs\reporting\live_execution_report_artifacts.py libs\reporting\live_execution_post_exit.py`
- `INTRADAY_TRADE_REPORT_JOB_LOCK_PATH=.pytest-work\phase113_bundle.lock`
- `INTRADAY_TRADE_REPORT_JOB_QUEUE_PATH=.pytest-work\phase113_bundle.queue.json`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

Note:

- The real live bundle lock was active during validation, so the test run used isolated test-only lock/queue paths. The running live process was not stopped.

### Phase 11.4 - Live Execution Strategist Input Artifact Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_strategist_artifacts.py`

Extracted responsibilities:

- strategist evidence ledger row selection
- strategist input collection row selection
- strategist prompt input row selection
- strategist input summary construction
- strategist payload backfill from cached input summary
- strategist input and compact input artifact reconstruction
- cached prompt artifact fallback for reused strategist routes

Design intent:

- keep strategist input evidence reconstruction outside the live execution bundle orchestration body
- preserve existing runner private helper names through import aliases
- make future strategist cache/report artifact changes local to a dedicated module

Runtime policy:

- no live restart
- no live trading behavior change
- report artifact reconstruction boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_strategist_artifacts.py`
- `INTRADAY_TRADE_REPORT_JOB_LOCK_PATH=.pytest-work\phase114_bundle.lock`
- `INTRADAY_TRADE_REPORT_JOB_QUEUE_PATH=.pytest-work\phase114_bundle.queue.json`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

### Phase 11.5 - Live Execution Scanner Evidence Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_scanner_evidence.py`

Extracted responsibilities:

- scanner selection reason enrichment
- runner-up and tie-break explanation surface
- chart/feature coverage normalization from scanner evidence
- filter summary enrichment from chart coverage
- price anomaly filter propagation from monitor evidence
- spread/slippage filter fallback from execution quote snapshots

Design intent:

- keep scanner evidence interpretation outside the live execution bundle orchestration body
- preserve existing runner private helper names through import aliases
- make future scanner report evidence changes local to a dedicated module

Runtime policy:

- no live restart
- no live trading behavior change
- report evidence enrichment boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_scanner_evidence.py libs\reporting\live_execution_strategist_artifacts.py`
- `INTRADAY_TRADE_REPORT_JOB_LOCK_PATH=.pytest-work\phase115_bundle.lock`
- `INTRADAY_TRADE_REPORT_JOB_QUEUE_PATH=.pytest-work\phase115_bundle.queue.json`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

### Phase 11.6 - Live Execution Open Monitor Backfill Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_open_monitor.py`

Extracted responsibilities:

- runtime position lookup from state snapshots
- runtime position price derivation
- open lifecycle monitor reason backfill
- average/current/peak price and drawdown bullet enrichment
- runtime price source policy annotation

Design intent:

- keep open-position report backfill logic outside the live execution bundle orchestration body
- preserve existing runner private helper names through import aliases
- make future open-position report snapshot fixes local to a dedicated module

Runtime policy:

- no live restart
- no live trading behavior change
- open lifecycle report backfill boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_open_monitor.py libs\reporting\live_execution_scanner_evidence.py`
- `INTRADAY_TRADE_REPORT_JOB_LOCK_PATH=.pytest-work\phase116_bundle.lock`
- `INTRADAY_TRADE_REPORT_JOB_QUEUE_PATH=.pytest-work\phase116_bundle.queue.json`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

### Phase 11.7 - Live Execution LLM Artifact Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_llm_artifacts.py`

Extracted responsibilities:

- strategist LLM response artifact reconstruction
- cached strategist evidence response fallback
- strategist prompt split into system/user sections for artifact storage
- reconstructed source metadata and mismatch annotations
- no-linked-evidence placeholder artifact generation

Design intent:

- keep LLM artifact shaping outside the live execution bundle orchestration body
- preserve the runner's existing `_build_strategist_llm_response_artifact` entry point through an import alias
- make future strategist LLM cache/report artifact changes local to a dedicated module

Runtime policy:

- no live restart
- no live trading behavior change
- report artifact reconstruction boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_llm_artifacts.py libs\reporting\live_execution_strategist_artifacts.py`
- `INTRADAY_TRADE_REPORT_JOB_LOCK_PATH=.pytest-work\phase117_bundle.lock`
- `INTRADAY_TRADE_REPORT_JOB_QUEUE_PATH=.pytest-work\phase117_bundle.queue.json`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

### Phase 11.8 - Live Execution Report Context Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_report_context.py`

Extracted responsibilities:

- report failure classification flags
- empty value normalization for report payloads
- timestamp to epoch conversion
- UTC day extraction
- trade time bucket derivation from lifecycle bundles

Design intent:

- keep shared report context helpers out of the live execution bundle orchestration body
- preserve existing runner helper names through import aliases
- make future report context/time-bucket policy changes local to a small module

Runtime policy:

- no live restart
- no live trading behavior change
- report context classification boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_report_context.py libs\reporting\live_execution_llm_artifacts.py`
- `INTRADAY_TRADE_REPORT_JOB_LOCK_PATH=.pytest-work\phase118_bundle.lock`
- `INTRADAY_TRADE_REPORT_JOB_QUEUE_PATH=.pytest-work\phase118_bundle.queue.json`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

### Phase 11.9 - Live Execution Event Evidence Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_event_evidence.py`

Extracted responsibilities:

- canonical event name normalization
- canonical strategist/scanner/monitor event filtering
- cached strategist source run-id resolution
- targeted run-id expansion for cached strategist frames
- strategist payload hydration from linked evidence
- news headline counting for strategist evidence summaries

Design intent:

- isolate event evidence interpretation from live execution bundle orchestration
- preserve existing runner helper names through import aliases
- make future cached strategist evidence/report reconstruction changes local to a dedicated module

Runtime policy:

- no live restart
- no live trading behavior change
- event evidence/report reconstruction boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_event_evidence.py libs\reporting\live_execution_report_context.py`
- `INTRADAY_TRADE_REPORT_JOB_LOCK_PATH=.pytest-work\phase119_bundle.lock`
- `INTRADAY_TRADE_REPORT_JOB_QUEUE_PATH=.pytest-work\phase119_bundle.queue.json`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

### Phase 11.10 - Live Execution Run Selection Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_execution_runs.py`

Extracted responsibilities:

- execution payload normalization for report run selection
- latest execution day detection from event logs
- BUY/SELL execution run extraction
- targeted run/symbol context selection
- lifecycle target matching for report bundle generation

Design intent:

- keep execution-run selection separate from report bundle orchestration
- preserve existing runner helper names through import aliases
- make future target-run and target-symbol policy changes local to a dedicated module

Runtime policy:

- no live restart
- no live trading behavior change
- report run-selection boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_execution_runs.py`
- `INTRADAY_TRADE_REPORT_JOB_LOCK_PATH=.pytest-work\phase1110_bundle.lock`
- `INTRADAY_TRADE_REPORT_JOB_QUEUE_PATH=.pytest-work\phase1110_bundle.queue.json`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed

### Phase 11.11 - Live Execution Trade Evidence Boundary

Changed files:

- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/live_execution_event_evidence.py`
- `libs/reporting/live_execution_trade_evidence.py`

Extracted responsibilities:

- trade-level strategist/scanner/monitor evidence assembly
- monitor canonical artifact freshness mirroring
- symbol/time-window monitor event merge
- canonical monitor threshold payload propagation
- generic event row identity helpers shared by report evidence and trace filtering

Design intent:

- move trade evidence assembly out of the live execution bundle orchestration body
- keep event row identity helpers reusable for both trade evidence and target-symbol monitor filtering
- preserve the runner's existing `_build_trade_evidence_from_events` entry point through an import alias

Runtime policy:

- no live restart
- no live trading behavior change
- trade evidence/report reconstruction boundary only

Validation:

- `venv\Scripts\python.exe -m py_compile libs\reporting\live_execution_bundle_runner.py libs\reporting\live_execution_trade_evidence.py libs\reporting\live_execution_event_evidence.py`
- `INTRADAY_TRADE_REPORT_JOB_LOCK_PATH=.pytest-work\phase1111_bundle.lock`
- `INTRADAY_TRADE_REPORT_JOB_QUEUE_PATH=.pytest-work\phase1111_bundle.queue.json`
- `venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py -q`
  - 67 passed
