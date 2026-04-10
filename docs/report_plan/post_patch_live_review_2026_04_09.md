# 2026-04-09 Post-Patch Live Review

## Scope
- Review window: post-patch canonical runs generated after `2026-04-09 13:49:58 +09:00`
- Objective: capture whether the exit/hold delay and pnl/effective_price anomaly patch changed live intraday behavior in the intended direction

## Post-Patch Canonical Snapshot
- Run count: `55`
- Action distribution:
  - `none`: `40`
  - `hold`: `13`
  - `buy`: `1`
  - `sell`: `1`
- Commander route distribution:
  - `full_cycle`: `33`
  - `cached_strategist`: `20`
  - `monitor_only`: `2`
- Override count: `12`
- Override reasons:
  - `repeated_hold_monitor_only`: `11`
  - `loss_threshold_exceeded`: `1`
- Price/pnl anomaly recurrence:
  - `price_anomaly_flag=true`: `0`
  - `effective_price/current_price` outside sane range (`< 0.5` or `> 1.5`): `0`
  - `pnl_fallback_applied=true`: `0`

## Primary Assessment
- The pnl/effective_price merge bug did not recur in the post-patch live window.
- Commander override is active in production and materially reduced open-position monitor-only stickiness.
- The route mix shifted toward `full_cycle` and `cached_strategist`, with `monitor_only` reduced to `2` runs in the sampled post-patch window.
- Structural risk-engine behavior looks materially healthier than the pre-patch state.

## Representative SELL Case
- Run: `reports/canonical/2026-04-09/b3127a315256455fa2971d6c778ce90f`
- Time: `2026-04-09 14:42:29 +09:00`
- Symbol: `000660`
- Route: `full_cycle`
- Decision: `SELL`
- Exit reason: `peak_drawdown`
- Effective price source: `account_pnl_ratio_mark`
- `effective_price`: `995988.0`
- `current_price`: `1005000.0`
- `effective_price/current_price`: `0.9910`
- `effective_pnl_ratio`: `-0.0060`
- Commander override:
  - `override_triggered=true`
  - `override_reason=repeated_hold_monitor_only`
  - `override_action=strategist_refresh`

## Interpretation
- The SELL sample is small, but the observed case is consistent with the intended patch behavior.
- The exit reason was structurally coherent (`peak_drawdown`), and the effective price stayed in a sane range instead of collapsing to a distorted anomaly price.
- The biggest remaining gap is not trigger correctness but observability completeness: we still want the trigger metric surfaced so the artifact itself explains the SELL without additional code reading.

## Follow-Up Checkpoints For The Next 1-3 Positions
Use this list during the next live hold/exit cycle:
- `final_exit_thresholds`
- `exit_threshold_source`
- `hold_block_reason`
- `override_triggered`
- `override_reason`
- `override_action`
- `pnl_fallback_applied`
- `price_anomaly_flag`
- `final_peak_drawdown_ratio`
- `peak_drawdown_source`
- `exit_trigger_metric_name`
- `exit_trigger_metric_value`
- `exit_trigger_metric_source`

## Closeout Note
- This patch is now best described as a successful first-pass stabilization of the live risk engine.
- Tomorrow's focus should be verifying the same behavior across another `1-3` exit samples and confirming that the surfaced observability fields explain each exit directly from the artifact.
