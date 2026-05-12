# Strategy Horizon Visibility And Patch Priority - 2026-05-11

## Purpose

This note records whether the recently added strategy horizon fields were reflected in today's run, why they were not visible in the operator-facing reports, and which improvement area should be patched first across Strategist, Scanner, and Monitor.

This is documentation only. No runtime code change is included here.

## Horizon Field Status From 2026-05-11 Trades

The horizon fields were captured in artifacts, but they were not surfaced in the main `ai_trade_summary.md` files.

Observed trade artifact values:

| Trade | Captured horizon values |
|---|---|
| `TRD_20260511_005930_01` | `scalp`, `intraday` |
| `TRD_20260511_078890_02` | `intraday`, `scalp` |
| `TRD_20260511_078890_03` | `intraday`, `scalp` |
| `TRD_20260511_115160_01` | `intraday`, `scalp` |
| `TRD_20260511_115160_03` | `intraday`, `scalp` |
| `TRD_20260511_005930_03` | `scalp`, `intraday` |
| `TRD_20260511_000660_01` | `scalp` |
| `TRD_20260511_078890_04` | `scalp` |
| `TRD_20260511_005930_04` | `scalp`, `intraday`, `overnight_probe` |
| `TRD_20260511_073490_01` | `scalp` |

Search result:

- `strategy_horizon` / `source_strategy_horizon` were found in trade artifacts.
- `ai_trade_summary.md` files did not show `strategy_horizon`, `horizon`, `scalp`, `intraday`, `overnight`, or Korean report labels for horizon.
- `daily_summary.md` also did not explain horizon proposal versus Commander-applied horizon.

## Current Schema Reality

The current runtime field is:

```json
{
  "strategy_horizon": "scalp | intraday | overnight_probe | 1_2day_swing"
}
```

The system currently does not use `primary_horizon` as the main field.

Operator-facing label mapping should be:

| Runtime value | Operator label |
|---|---|
| `scalp` | ultra-short / scalp |
| `intraday` | intraday |
| `overnight_probe` | overnight probe |
| `1_2day_swing` | 1-2 day swing |

## Commander Behavior

The horizon path is currently observability-first.

Important fields:

```json
{
  "observability_only": true,
  "allow_behavior_change": false,
  "do_not_force_hold": true
}
```

Meaning:

- Strategist can propose a horizon.
- Commander records and owns the operational horizon.
- Monitor should not force holding just because the horizon is longer.
- Current behavior change is intentionally disabled.

For long horizons:

- If Strategist proposes `overnight_probe` or `1_2day_swing`, Commander can cap it during live validation.
- Example observed reason:

```text
commander_caps_long_horizon_during_live_validation_observability_only
```

This means the proposal was captured, but Commander did not allow it to change live behavior yet.

## Report Gap

The main gap is not schema capture. The gap is report visibility and explanation.

Reports should show:

1. Strategist proposed horizon
2. Commander applied horizon
3. Whether Commander capped the proposal
4. Expected hold window
5. Actual hold duration
6. Whether exit was aligned with the proposed horizon
7. Whether early exit was allowed by hard-risk reason

Recommended report section:

```markdown
## Strategy Horizon

* Strategist proposal: intraday
* Commander applied: scalp
* Behavior authority: observation-only
* Expected hold window: 5m / 30m / 4h
* Actual hold: 7m 42s
* Exit vs horizon: early exit, allowed by hard stop / cost-aware exit / liquidity collapse
* Note: horizon did not force holding.
```

## Patch Priority Across Strategist / Scanner / Monitor

### P1 - Monitor

Monitor should be first priority.

Reason:

- Today's main performance issue was not lack of horizon labels.
- It was poor net edge after cost, weak take-profit capture, and delayed or missed exit checks during spikes.
- Monitor owns actual entry approval, hold review, exit timing, profit protection, and cost-aware sell logic.
- If Monitor remains weak, improved Strategist or Scanner output will still result in poor realized outcomes.

Monitor patch focus:

- Make cost-aware profit protection visible and deterministic.
- Improve fast profit spike handling.
- Strengthen peak-drawdown profit-protection after cost floor is crossed.
- Confirm open-position exit review runs before scanner/strategy work when a position is already held.
- Add horizon-vs-actual-hold reporting without forcing hold behavior.
- Keep `do_not_force_hold=true` unless Commander explicitly allows behavior change later.

Expected impact:

- Highest immediate effect on win rate and net PnL quality.
- Reduces cases where gross price briefly moves favorably but realized result is negative after fee/tax/slippage.

### P2 - Scanner

Scanner should be second priority.

Reason:

- Scanner quality determines whether Monitor spends time on useful candidates or repeatedly blocks structurally poor ones.
- However, Scanner should not become a hard entry gate.
- Scanner improvements should remain soft ranking bias.

Scanner patch focus:

- Surface `scanner_chart_fit_score` and `scanner_chart_fit_components`.
- Keep chart-fit authority as `soft_bias_only`.
- Cap chart-fit impact so it can flip near-ties but cannot override all liquidity/trend evidence.
- Improve candidate explanation: rank #1 versus actual cascade-selected candidate.
- Continue preserving top candidates and runner-ups for Stage 2 strategist refresh.
- Do not hard-reject normal candidates only because VWAP reclaim, breakout, volume confirmation, or pullback timing is not ready.

Expected impact:

- Fewer repeated Monitor NOOPs.
- Better candidate quality without creating a second hidden gate.

### P3 - Strategist

Strategist should be third priority, after Monitor and Scanner visibility/quality.

Reason:

- Stage 1 and Stage 2 already produce useful strategy fields.
- Horizon proposal is captured.
- Strategy diversity exists, but its behavior authority is intentionally limited.
- Without Monitor and Scanner fixes, richer Strategist output can still fail at execution quality.

Strategist patch focus:

- Make horizon proposal more consistent with actual tactical strategy.
- Make Stage 2 selected-symbol refresh always compare:
  - scanner rank #1
  - actual selected candidate
  - runner-ups
  - selected symbol memory when memory is re-enabled
- Add clearer "why this horizon" and "what would invalidate this horizon".
- Keep horizon behavior advisory until enough live validation data exists.
- Avoid introducing new strategy names unless Commander/Scanner/Monitor can actually consume them.

Expected impact:

- Improves reasoning trace and future policy quality.
- Less immediate PnL impact than Monitor or Scanner unless behavior authority is enabled later.

## Overall Recommended Order

1. Monitor: cost-aware exit / profit capture / hold review cadence / horizon-vs-actual-hold report fields
2. Scanner: soft chart-fit scoring visibility / candidate quality / rank1-vs-selected clarity
3. Strategist: horizon explanation quality / Stage 2 selected-symbol comparison / future behavior authority preparation

## 2026-05-11 Patch Update

The patch direction was corrected from pure visibility to runtime consumption.

Applied:

- Strategist still proposes `strategy_horizon`.
- Commander now builds `behavior_translation` from the applied horizon.
- Monitor consumes the translation for hold-control and exit-policy bias.
- Scanner receives a separate chart-fit path through `scanner_chart_fit_score`, but only as soft ranking bias.
- Reports surface the proposed horizon, Commander-applied horizon, hold window, actual hold, and horizon translation.

Important guardrail:

- `allow_behavior_change=false` still means "do not force holding".
- `allow_behavior_translation=true` means "Commander can translate horizon into review cadence, exit-policy bias, and report context".

## Key Decision

Do not turn horizon into a forced holding rule.

For now:

```text
Strategist proposes horizon.
Commander records, may cap horizon, and translates it into bounded runtime guidance.
Monitor can exit early for hard risk, cost, liquidity, breakdown, or profit-protection reasons.
Reports must show the proposal, applied policy, translation, and actual hold result.
```

This keeps the system honest while live validation is still weak.
