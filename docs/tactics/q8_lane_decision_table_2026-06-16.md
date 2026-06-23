# Q8 Lane Decision Table - 2026-06-16

## Summary

- payloads: 482
- candidates: 1625
- deduped candidates: 788
- duplicates: 837
- dedupe_key: `day, symbol, baseline_epoch, entry_lane_subtype`
- evaluated: 1619
- forward observed: 754 (95.7%)
- trust_gate: `promotion_blocked_no_repeatable_candidate`
- promotion_allowed: `False`
- trust_block_reasons: `no_repeatable_promotion_watch_candidate`
- would-enter: 0
- top reasons: below_vwap_reclaim_not_ready 717, pullback_not_mature 470, volume_confirmation_missing 202, pullback_below_vwap_reclaim_not_ready 74, breakout_above_recent_high_with_vwap_hold_and_volume_confirmation 49, human_chart_sanity_guard_blocked 22

## Lane Verdicts

| Lane | Verdict | Decision | n | obs | +5m | +15m | +30m | MFE5 | MAE5 | Rationale |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| vwap_reclaim | TRUST_GATE_BLOCKED | retain under observation | 365 | 352 | 0.0430% | -0.0022% | 0.0438% | 0.3996% | -0.3695% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |
| cost_edge | TRUST_GATE_BLOCKED | retain under observation | 159 | 155 | -0.0709% | -0.0985% | -0.0891% | 0.2276% | -0.3038% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |
| pullback_quality | TRUST_GATE_BLOCKED | retain under observation | 136 | 131 | 0.0360% | 0.1184% | 0.1368% | 0.3265% | -0.3336% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |
| volume_confirmation | TRUST_GATE_BLOCKED | retain under observation | 53 | 49 | -0.1154% | -0.2773% | -0.4909% | 0.3083% | -0.5688% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |
| opening_momentum | TRUST_GATE_BLOCKED | retain under observation | 23 | 22 | -0.1396% | -0.1813% | -0.4960% | 1.2396% | -1.0687% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |
| runner_up_selection | TRUST_GATE_BLOCKED | retain under observation | 20 | 16 | 0.0873% | 0.0577% | -0.4448% | 0.4733% | -0.2904% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |
| breakout_readiness | TRUST_GATE_BLOCKED | retain under observation | 13 | 11 | -0.0632% | -0.4023% | -0.3053% | 0.2429% | -0.3593% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |
| human_chart_sanity | TRUST_GATE_BLOCKED | retain under observation | 10 | 9 | -0.0853% | -0.2978% | -0.5267% | 0.3645% | -0.4393% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |
| confirmed_or_other | TRUST_GATE_BLOCKED | retain under observation | 5 | 5 | 0.0306% | 0.2779% | -0.0105% | 0.1907% | -0.2239% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |
| opening_largecap_surge | TRUST_GATE_BLOCKED | retain under observation | 4 | 4 | -0.5474% | -0.7839% | -1.0579% | 0.1641% | -0.7665% | Q8 trust gate blocked promotion review; lane signal is diagnostic only. |

## Operating Interpretation

- `TRUST_GATE_BLOCKED`: lane signal is visible, but Q8 evidence is not eligible for policy promotion.
- `MISSED_OPPORTUNITY`: blocked candidates rose afterward. This is a review target, not direct permission to buy.
- `GOOD_BLOCK`: blocked candidates underperformed after the block. Keep the gate under observation.
- `DATA_INCOMPLETE`: sample or coverage is insufficient for a policy conclusion.

## Current Action

No new behavior patch is implied by this table unless the Q8 trust gate allows promotion review.
