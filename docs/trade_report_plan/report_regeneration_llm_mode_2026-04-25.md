# Report Regeneration LLM Mode Policy (2026-04-25)

## Decision

`scripts/run_ai_trade_report_batch.py` defaults to deterministic regeneration.

This policy is batch/manual regeneration only. Live closed-trade first-write still calls the report LLM through `run_live_execution_bundle_report.py --trade-report-ai`.

As of 2026-04-28, trade reports have a separate summary lane:

- `ai_trade_report.*`: detailed lifecycle/audit report
- `ai_trade_summary.*`: operator-facing conclusion surface

The summary lane has its own compact LLM input:

- `reports/ai_trade_summary_input.json`
- `reports/ai_trade_summary.json`
- `reports/ai_trade_summary.md`
- `reports/ai_trade_summary_llm_response.json`

Default regeneration writes the canonical report and summary artifacts without calling either report LLM or summary LLM:

```powershell
venv\Scripts\python.exe scripts\run_ai_trade_report_batch.py --day 2026-04-21 --trade-id TRD_20260421_005380_01 --json
```

Use `--with-llm` only when an operator explicitly wants the optional post-trade narrative/evaluation layer:

```powershell
venv\Scripts\python.exe scripts\run_ai_trade_report_batch.py --day 2026-04-21 --trade-id TRD_20260421_005380_01 --with-llm --json
```

`--local-debug` remains a non-destructive inspection mode. It writes `.local_debug` artifacts and does not overwrite the canonical report:

```powershell
venv\Scripts\python.exe scripts\run_ai_trade_report_batch.py --day 2026-04-21 --trade-id TRD_20260421_005380_01 --local-debug --json
```

## Rationale

- Deterministic regeneration is faster, cheaper, and avoids hallucinated prose entering the normal repair loop.
- The LLM report is an optional operator-facing retrospective, not the source of truth for facts, memory, or strategy.
- In live trading, the first closed-trade `ai_trade_report` remains an LLM artifact by default and should only be skipped by explicit emergency/manual repair controls.
- In live trading, the first closed-trade `ai_trade_summary` should use `ai_trade_summary_input.json` for the LLM evaluation conclusion.
- Future memory should be derived from deterministic artifacts and explicit memory/application traces, not `ai_trade_report.md` prose.
- `ai_trade_summary.md` prose is also not a memory source; it is an operator-facing interpretation surface.
- When `--with-llm` is used, the report LLM consumes structured `strategist_output` directly instead of reconstructing strategy rationale from prose.
- When the summary LLM is used, it consumes only `ai_trade_summary_input.json` and may fill only conclusion/root-cause/action/risk/validation fields.
- The strategist output explains market frame, memory/news use, and scanner/monitor handoff. It does not own final symbol selection.
- Final symbol-selection explanation remains owned by scanner evidence such as `selection_trace`, rank, score, `selection_basis`, and `runner_ups_lost`.
- `--with-llm` is still useful for curated acceptance checks and cases where a richer human-readable narrative/evaluation is worth the token cost.

## Status Semantics

- Deterministic regeneration sets `generation.mode = deterministic`.
- Deterministic regeneration keeps `deterministic_report_status = ok`.
- Deterministic regeneration keeps `ai_trade_report_status = skipped` because no report LLM was called.
- Deterministic regeneration writes `ai_trade_summary.json` with `summary_status = skipped` / `generation.mode = deterministic` because no summary LLM was called.
- Diagnostics should show `report_status = available` and `report_reason_code = deterministic_only`.
- Deterministic regeneration writes an `ai_trade_report_llm_response.json` skip marker with `meta.reason = deterministic_no_llm` so stale LLM artifacts are not mistaken for a fresh call.
- Deterministic regeneration writes an `ai_trade_summary_llm_response.json` skip marker with `meta.reason = summary_llm_disabled` or `local_debug_no_llm`.
- LLM regeneration through `--with-llm` may produce `ok`, `partial`, `salvaged`, or `error` depending on the model result.
- Live first-write status should not be `deterministic_only` for closed executed trades unless the run was explicitly launched with a no-AI/emergency repair path.

## Summary LLM Markdown Placement

When `ai_trade_summary.json.llm_evaluation` has content, `ai_trade_summary.md` renders:

```text
## 🔴 운영 요약 (Operator Decision Summary)
...
## 🤖 LLM 평가 결론
...
## 🧭 거래 개요
```

If the summary LLM was skipped or produced no evaluation content, `## 🤖 LLM 평가 결론` is omitted.

The full `ai_trade_report.md` remains a detailed report and should not be modified to absorb this summary-first surface.
