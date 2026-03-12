# Evidence Ledger (Reasoning Trace Layer)

## Purpose
- Keep an append-only, agent-level reasoning trace for audit/debug.
- Preserve both compact summaries and raw reasoning artifacts.
- Passive logging only: this layer must never alter runtime decisions.

## Storage
- Path: `data/evidence_ledger/events.jsonl`
- Override: `EVIDENCE_LEDGER_PATH`
- Format: JSONL (one record per line, append-only)

## Canonical Record Schema
```json
{
  "run_id": "string",
  "timestamp": "ISO8601 UTC",
  "agent": "strategist|scanner|monitor|reporter",
  "stage": "string",
  "raw_input": {},
  "llm_prompt": "string",
  "llm_response": "string",
  "parsed_output": {},
  "decision_link": {}
}
```

## Current Integration Points
- Strategist:
  - raw collected context snapshot (`stage=theme_selection`)
  - LLM prompt/response trace (when strategist LLM stage is enabled)
  - strategist decision bridge (`stage=decision_bridge`)
- Scanner:
  - candidate retrieval + frame input snapshot (`stage=symbol_selection`)
  - scanner selection bridge (`stage=decision_bridge`)
- Monitor:
  - entry/exit input snapshot (`stage=entry_exit_decision`)
  - monitor entry/exit bridge (`stage=decision_bridge`)
- Reporter:
  - deterministic report input snapshot (`stage=post_run_analysis`)
  - optional AI review prompt/response trace (`stage=post_run_analysis`)
  - reporter analysis bridge (`stage=post_run_analysis`)

## Decision Bridge Intent
- Bridge records link:
  - strategist frame (`theme`/`playbook`)
  - scanner selection (`selected symbol`)
  - monitor outcome (`entry_reason`/`exit_reason`)
- Reporter uses these records for post-run chain explanation.

## Safety Boundary
- Evidence ledger does not:
  - choose symbols
  - create intents
  - approve/reject orders
  - execute trades
- It is observability-only.
