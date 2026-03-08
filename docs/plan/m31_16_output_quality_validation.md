# M31-16 Output Quality Validation (Operator Reports)

- Date: 2026-03-08
- Objective: validate operator-facing report readability on real artifacts and patch UX gaps.

## Sample Outputs (Generated)

- operator summary:
  - `reports/operator_summary/operator_summary_2026-03-07.md`
- decision story:
  - `reports/decision_story/decision_story_2026-03-07.md`
- run cards:
  - `reports/run_cards/run_cards_2026-03-07.md`

## Readability Gaps Found

1. Executive summary was technically correct but not operator-first.
- Top issues and actions were below detailed sections.

2. Reason fields exposed raw machine codes.
- Examples: `noop_intent_skipped`, `duplicate_buy_position_exists`.

3. Large-day outputs were too long for quick operator scan.
- Decision story and run cards listed all runs without render cap.

4. Some lines showed awkward action forms (`BUY 0`).

## Applied UX Patches

- Patched `libs/reporting/operator_visibility.py`:
  - reason humanization mapping and formatter added
  - top issues + recommended actions moved to top section
  - health badge style normalized to `[GREEN|YELLOW|RED]`
  - human-readable blocked/noop/fallback summaries added
  - decision story/run cards support render cap and show total vs rendered counts
  - guard reason display uses human-readable text
  - action formatting avoids `BUY 0` style noise

- Patched scripts:
  - `scripts/run_decision_story_report.py` adds `--max-runs`
  - `scripts/run_run_card_report.py` adds `--max-runs`

## Validation Result

- Operator summary keeps key actions/issues immediately visible.
- Decision story and run cards remain reproducible while becoming scan-friendly for high run-volume days.
- No raw event schema change and no contract-breaking DTO change.
