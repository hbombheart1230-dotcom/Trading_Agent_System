# 2026-05-18 Entry Cascade Hard Block and Same-Day Average Fix

## Scope

- Hardened monitor entry candidate cascade so hard blockers do not bypass rank-1 vetoes into runner-up buys.
- Fixed trade summary same-day average rendering when reporter feedback provides `avg pnl pct` as a ratio.

## Entry Cascade Policy

- Removed volume blockers from commander pool expansion and default cascade-allowed reasons.
- Added these to default cascade-blocked reasons:
  - `volume_confirmation_missing`
  - `volume_insufficient`
  - `volume_missing`
  - cost/edge/data/risk guard blockers
- Monitor candidate cascade now returns `hard_entry_blocker_no_cascade` for:
  - duplicate symbol guards
  - volume confirmation/insufficient guards
  - cost filter and edge evidence guards
  - risk/data/closeout/post-exit cooldown guards

## Report Summary Average

- `avg pnl pct -0.0107` is now treated as a ratio and displayed as `-1.07%`.
- Explicit percent text remains percent text.
- Same-day result counts are clamped so wins/losses/flat/unknown never exceed the closed trade count.

## Verification

- `python -m py_compile` on changed runtime/reporting modules.
- `pytest tests/test_monitor_candidate_cascade.py tests/test_trade_summary_symbol_metadata.py`
- Targeted commander cascade tests.
- Broader monitor/report compatibility tests:
  - selected monitor cascade tests
  - `tests/test_scanner_monitor_compatibility.py`
  - `tests/test_reporter_feedback.py`

