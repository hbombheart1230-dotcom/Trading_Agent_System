# LLM Architecture

## Before

- Model alias handling was split across multiple modules.
- `auto` / `free` were normalized in some paths, but not consistently in strategist-related env handling.
- Strategist frame, AI trade report, operator brief, and daily report did not all follow the same retry/failure policy.
- AI trade report and operator brief could fall back quickly into rendered text that looked close to a successful report.
- Raw LLM response artifacts existed in some places, but behavior and saved fields were not uniform.

## After

### Shared model normalization

- Canonical helper: `libs/llm/model_names.py`
- Behavior:
  - `auto` -> `openrouter/auto`
  - `free` -> `openrouter/free`
  - `openrouter/free` -> unchanged
  - `minimax/minimax-m2.5` -> unchanged

Used by:
- `libs/llm/llm_router.py`
- `libs/ai/providers/openai_provider.py`
- `graphs/nodes/strategist_node.py`
- `libs/reporting/trade_report_ai.py`
- `libs/reporting/llm_daily_summary.py`
- `libs/reporting/reporter_ai_review.py`
- `apps/operator_ui/data_access.py`
- `scripts/run_live_execution_bundle_report.py`

### Actual LLM call paths

- Strategist frame
  - `graphs/nodes/strategist_node.py`
  - `LLMRouter.chat("strategist", ...)`
- AI trade report
  - `libs/reporting/trade_report_ai.py`
  - `LLMRouter.chat("trade_report", ...)`
- Operator brief
  - `apps/operator_ui/data_access.py`
  - `LLMRouter.chat("operator_ui", ...)`
- Daily report
  - `libs/reporting/llm_daily_summary.py`
  - `LLMRouter.chat("daily_report", ...)`
- Reporter final review
  - `libs/reporting/reporter_ai_review.py`
  - `LLMRouter.chat("reporter_final", ...)`
- Legacy strategist provider path
  - `libs/ai/providers/openai_provider.py`
  - direct OpenAI-compatible HTTP request path

## Artifact contract by component

### Strategist

- Input artifact
  - evidence ledger prompt/response rows
  - downstream bundle reference in `aggregated_execution_bundle.json`
- Raw response artifact
  - `reports/trades/<day>/<trade_id>/strategist/strategist_llm_response.json`
- Parsed output artifact
  - stored inside the LLM response artifact as `parsed_output`
- Rendered artifact
  - strategist output is embedded into lifecycle/bundle artifacts
- Explanation contract
  - `docs/strategist_output/strategist_explanation_contract_2026-04-25.md`
  - strategist owns strategy frame, memory/news interpretation, scanner guidance, and monitor guidance
  - strategist does not own final symbol selection or order execution

### AI trade report

- Input artifact
  - `reports/trades/<day>/<trade_id>/ai_trade_report/ai_trade_report_input.json`
- Raw response artifact
  - `reports/trades/<day>/<trade_id>/ai_trade_report/ai_trade_report_llm_response.json`
- Parsed output artifact
  - stored inside the LLM response artifact as `parsed_output`
- Rendered artifact
  - `reports/trades/<day>/<trade_id>/ai_trade_report/ai_trade_report.json`
  - `reports/trades/<day>/<trade_id>/ai_trade_report/ai_trade_report.md`

### Operator brief

- Input artifact
  - run detail + canonical trade artifacts
  - `reports/trades/<day>/<trade_id>/brief_input.json`
  - `reports/trades/<day>/<trade_id>/brief_compact_input.json`
- Raw response artifact
  - `reports/trades/<day>/<trade_id>/reports/brief_llm_response.json`
- Parsed output artifact
  - stored inside the LLM response artifact as `parsed_output`
- Rendered artifact
  - `reports/trades/<day>/<trade_id>/reports/operator_brief.json`
  - `reports/trades/<day>/<trade_id>/reports/operator_brief.md`

### Daily report

- Input artifact
  - deterministic daily summary payload built in the EOD pipeline
- Raw response artifact
  - `reports/daily/<day>/daily_report_llm_response.json`
- Parsed output artifact
  - stored inside the LLM response artifact as `parsed_output`
- Rendered artifact
  - `reports/daily/<day>/daily_report.json`
  - `reports/daily/<day>/daily_report.md`

## Retry / failure policy

### Strategist

- When AI strategist mode is enabled and strict mode is active:
  - no silent fallback to `RuleStrategist` for missing config or provider construction failure
  - result must be either:
    - valid LLM-backed strategist output
    - explicit blocked/NOOP path with reason:
      - `strategist_llm_required`
      - `strategist_llm_failed`

### AI trade report

- Retries before terminal failure.
- On terminal failure:
  - saves `ai_trade_report_llm_response.json`
  - writes a failure-shaped report object
  - does not synthesize a success-like narrative body

### Operator brief

- Retries before terminal failure.
- Repair attempts remain available.
- On terminal failure:
  - saves `brief_llm_response.json`
  - returns a failure-shaped brief object
  - deterministic run/trade sections are still attached separately by the UI layer

### Daily report

- Retries before terminal failure.
- On terminal failure:
  - saves `daily_report_llm_response.json`
  - returns empty summary text plus failure artifact
