# Narrative Axis Display Policy (2026-04-08)

## Scope
- Daytime-safe reporting patch only
- Runtime trading semantics unchanged
- No changes to monitor, supervisor, executor, approval, or guard precedence

## Narrative Axis Rules
- `entry`:
  - primary for `BUY`, `WAIT`, `NOOP`, `NO_TRADE`
  - primary explanation should answer "why buy" or "why not buy"
- `exit`:
  - primary for `SELL`, `EXIT`
  - primary explanation should answer "why exit" or "why sell"
- `mixed`:
  - reserved for ambiguous cases only
  - mixed should remain rare and must disclose why the view is mixed

## Display Policy
- Exit-oriented runs and trade lifecycle sections should render exit-first
- Entry-oriented runs should render entry-first
- Entry blocker context may still be preserved for exit runs, but only as secondary context
- Exit context may still be preserved for entry runs, but only as secondary context

## Report Surfaces
- `decision_story`:
  - detailed structured explanation
  - primary explanation must align with `decision_axis`
- `run_cards`:
  - fastest operator surface
  - should show the primary axis and primary explanation with minimal confusion
- `trade_explain`:
  - trade lifecycle view
  - exit sections should lead with exit narrative and keep entry blocker context secondary
- `daily_report` / `operator_summary`:
  - should expose the display policy so downstream readers understand entry-first vs exit-first ordering

## Safety Notes
- Additive only
- Existing fields such as `why_not_buy_summary`, `why_exit_summary`, and `dominant_blocker` remain available
- DTO/IO contracts remain backward compatible
