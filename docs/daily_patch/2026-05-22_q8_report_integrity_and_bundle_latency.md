# 2026-05-22 Q8 Report Integrity And Bundle Latency

## Scope

This patch keeps Q8 focused on artifact integrity before promoting more tactic
behavior.

It fixes two issues found during the 2026-05-22 live review:

1. Trade summary symbol metadata could accept entry reason text or news headline
   fragments as a symbol name.
2. Intraday trade report bundle jobs could lag far behind SELL executions while
   repeatedly rescanning append-only multi-GB event and evidence JSONL files.

## Closed Trade Report Gap

Execution events showed seven closed round trips by the review point, while
only four trade report folders existed.

Missing closed trade reports:

| Trade | Exit run |
| --- | --- |
| `TRD_20260522_009150_01` | `0bbd9c3ce66e4272bf1cc92263202553` |
| `TRD_20260522_046970_01` | `fbc0be0f824947b3a275d0715b948815` |
| `TRD_20260522_062970_01` | `41e52be5336f4eb3b472e2b3117a4df6` |

The SELL hooks did request bundle generation. The requests were queued behind
existing bundle workers, then delayed because each worker rediscovered the day
and rescanned full event/evidence logs.

Manual deterministic targeted recovery regenerated the three closed trade
folders and their `ai_trade_summary` artifacts. After recovery the daily
operator summary reported eight trade folders and seven closed trades; the
eighth folder was the currently open `TRD_20260522_009150_03`.

## Code Changes

### Trade Summary Metadata

- `libs/reporting/trade_report_symbol_metadata.py`
  - Rejects snake-case entry reason strings as symbol names.
  - Prefers the symbol prefix when parsing narrative text shaped like
    `symbol: stock_name, headline tail`.
  - Adds current fallback symbol names for:
    - `009150` Samsung Electro-Mechanics
    - `011930` Shinsung E&G
    - `046970` Wooriro
    - `062970` Korea Advanced Materials
    - `126340` Vinatech

No theme fallback was added for the recovered 2026-05-22 rows because those
trade inputs did not carry symbol-specific theme evidence.

### Q8 Quant Tactic Surface

- `libs/reporting/quant_tactic_report.py`
  - Makes entry-side tactic evidence authoritative before exit-side tactic
    evidence.
  - Exposes `tactic_id_source`.
  - Exposes `tactic_id_mismatches` when entry/factor and exit diagnostics
    disagree.

This keeps the Q8 evaluation table from collapsing an entry tactic into
`defensive_observe` solely because a later exit decision carried that tactic.

### Intraday Bundle Throughput

- `libs/reporting/intraday_trade_reports.py`
  - Derives the UTC trade day from the live execution state.
  - Passes `--day` to spawned intraday report bundle workers.
- `libs/reporting/live_execution_bundle_runner.py`
  - Uses the day-filtered JSONL reader for both event rows and evidence rows.
- `libs/reporting/event_log_reader.py`
  - Accepts both `ts` and `timestamp` rows.
  - Updates day caches incrementally when source JSONL files only append.

The runtime process that was already running before this patch still holds the
old spawn hook in memory. A later live restart is required before new SELL hook
spawns include `--day` automatically.

### Queued Follow-Up Bundle Entrypoint

The 2026-05-22 `12:01:58 KST` SELL for `009150` exposed one more reporting
gap:

- the busy bundle path queued run
  `45c6c36d962648d0bb8975952d6f833a`
- the queue follow-up used the direct
  `scripts/run_live_execution_bundle_report.py` path
- direct script execution does not put the repository root on `sys.path` in
  this environment, so `libs.reporting` import resolution fails before the
  queued follow-up can write the final trade report

Fix:

- `libs/reporting/live_execution_bundle_runner.py`
  - queued follow-up workers now use
    `python -m scripts.run_live_execution_bundle_report`
  - the existing `cwd=repo root` and parent-spawn lock environment are kept

Recovery:

- Re-ran the missing SELL run in targeted mode with `--day 2026-05-22`.
- `TRD_20260522_009150_03` moved from `open` to `closed`.
- `ai_trade_summary.md` and related summary artifacts were regenerated.
- Daily operator summary moved to eight closed trades after the recovery.

### Kiwoom SELL Lifecycle Alignment

The queued-worker failure was separate from lifecycle truth alignment. The live
bundle flow still decided a trade was closed before the broker status lookup was
attached to the SELL side:

- accepted SELL order quantity could equal entry quantity
- `trade_lifecycle_builder` could therefore close the trade from requested
  quantity alone
- `kt00007` / `kt00009` order-fill truth was attached later while building the
  report context

Fix:

- `libs/reporting/live_execution_bundle_runner.py`
  - numeric Kiwoom SELL order ids are aligned through the existing broker order
    status reader before trade lifecycles are built
  - the aligned run bundle carries whether Kiwoom fill truth was actually
    confirmed
- `libs/reporting/trade_lifecycle_builder.py`
  - broker-aligned SELL runs no longer treat accepted order quantity as sold
    quantity while fill truth is missing
  - a confirmed Kiwoom order-status fill can still close the lifecycle before
    report generation

This keeps report closure tied to broker order/fill truth for Kiwoom mock and
real order numbers while leaving non-Kiwoom test execution ids unchanged.

### Q8 Evaluation Surface

- Added `libs/reporting/quant_tactic_evaluation.py`.
  - Owns Q8 sample sufficiency checks.
  - Owns required-field coverage checks for tactic ID, entry/exit decisions,
    suitability tier, and entry cost-floor state.
  - Owns tactic ID mismatch counts and markdown lines.
- `libs/reporting/operator_period_summary.py`
  - Reads `quant_tactic.tactic_id_source` and
    `quant_tactic.tactic_id_mismatches` from the trade summary input when
    available.
  - Adds `quant_tactic_evaluation` to daily, weekly/monthly, and symbol
    operator summary JSON.
  - Renders Q8 readiness, missing fields, and tactic ID integrity directly in
    Pattern Performance markdown.

This remains evaluation-only. It does not promote a new entry or exit gate.

## Validation

Focused regression:

```powershell
venv\Scripts\python.exe -m pytest tests\test_trade_summary_symbol_metadata.py tests\test_quant_tactic_report.py tests\test_quant_decision.py
venv\Scripts\python.exe -m pytest tests\test_event_log_reader.py tests\test_intraday_trade_reports.py::test_intraday_trade_reports_queues_background_job_after_timeout
venv\Scripts\python.exe -m pytest tests\test_quant_tactic_evaluation.py tests\test_operator_summary_reports.py -q --basetemp .pytest-work-q8-evaluation
venv\Scripts\python.exe -m pytest tests\test_live_execution_bundle_report.py::test_live_execution_bundle_report_spawn_followup_uses_module_entrypoint_and_repo_root tests\test_live_execution_bundle_report.py::test_live_execution_bundle_report_spawns_followup_from_queue_after_completion tests\test_intraday_trade_reports.py::test_intraday_trade_reports_queues_background_job_after_timeout -q --basetemp .pytest-work-followup-module
venv\Scripts\python.exe -m pytest tests\test_trade_lifecycle_builder.py tests\test_live_execution_bundle_report.py::test_align_sell_run_bundles_with_broker_fill_truth_marks_numeric_kiwoom_sell tests\test_live_execution_bundle_report.py::test_live_execution_bundle_report_logs_ai_generation_start_and_finish_events tests\test_live_execution_bundle_report.py::test_live_execution_bundle_report_falls_back_to_deterministic_when_ai_generation_raises -q --basetemp .pytest-work-kiwoom-lifecycle-align
venv\Scripts\python.exe -m py_compile libs\reporting\event_log_reader.py libs\reporting\intraday_trade_reports.py libs\reporting\live_execution_bundle_runner.py libs\reporting\trade_report_symbol_metadata.py libs\reporting\quant_tactic_report.py
venv\Scripts\python.exe -m py_compile libs\reporting\quant_tactic_evaluation.py libs\reporting\operator_period_summary.py
```

Observed targeted checks:

- Closed 2026-05-22 trade summaries exist for seven closed trade folders.
- Daily operator summary metrics report:
  - `trade_count=8`
  - `closed_trade_count=7`
- Regenerated 2026-05-22 daily operator summary now exposes:
  - Q8 status `hold_sample_insufficient`
  - sample `7/20`, aligned with the closed/realized operator-summary sample
  - complete required-field coverage for the current closed sample
  - one tactic ID mismatch trade:
    `TRD_20260522_009150_02`
- Cached 2026-05-22 row loads after cache creation were measured locally at:
  - events: about `2.5s`
  - evidence: about `1.2s`

## Follow-Up

Keep Q8 on integrity validation before behavior promotion:

1. Verify the next live restart produces new bundle spawn commands with
   `--day`.
2. Watch whether closed trade summary count stays aligned with SELL executions
   when multiple exits happen close together.
3. Use `tactic_id_source` and `tactic_id_mismatches` in the next Q8 review
   before changing tactic thresholds.
