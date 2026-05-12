# Strategist 4-Stage LLM Flow Draft

Date: 2026-05-08
Status: Draft

## Purpose

This document separates the Strategist LLM workflow into four clearly named stages.

The current runtime has become hard to reason about because these concerns are partially mixed:

- broad market strategy
- selected-symbol strategy after Scanner
- stale intraday hold review
- end-of-day overnight/carry decision

The proposed direction is reasonable because each stage answers a different question and should not produce overlapping instructions.

## Active Scope Clarification

The 1차/2차/3차/4차 labels in this document are Strategist LLM review stages.

They are not four position slots, not four independent trading lanes, and not the earlier four-slot strategy design.

As of 2026-05-08:

- the earlier four-slot strategy design is HOLD/deferred
- the earlier two-slot short/long design is HOLD/deferred
- the active runtime path is the existing Strategist -> Scanner -> Monitor flow
- the active capacity model is small multi-position capacity with duplicate same-symbol BUY blocking
- `strategy_horizon` is reference/observability metadata unless Commander translates it into concrete scanner/monitor/exit policy fields

Use position-capacity language such as `remaining_position_capacity` for the active path. Do not use `slot_*`, `horizon_slot`, or `remaining_position_slots` in runtime-facing JSON unless slot attribution is explicitly reactivated later.

## Current Implementation Gap

The current implementation usually performs one Strategist LLM call with `call_kind=strategic_frame`.

That one call asks the model to fill several fields at once, including:

- `strategy_refresh_trace.initial_frame`
- `strategy_refresh_trace.post_scanner_refresh`
- `strategy_refresh_trace.final_application`
- `strategy_horizon_feedback`

This means the reports can look like 1st/2nd/3rd strategy decisions exist, but operationally they are not cleanly separated LLM calls.

The important gap:

- Stage 1 exists as the main Strategist call.
- Stage 2 exists only conditionally and is not guaranteed after every Scanner selection.
- Stage 3, the stale intraday hold review, is not a dedicated LLM call today.
- Stage 4, the 15:20 overnight/carry decision, should remain separate from Stage 3.

## Implementation Update 2026-05-08

The first runtime patch is now started:

- Stage 1 calls resolve to `market_strategy_frame`.
- Stage 1 compact LLM payload excludes symbol-specific memory.
- Stage 2 calls resolve to `selected_symbol_tactical_refresh`.
- Stage 2 can run after Scanner selection when entry capacity exists and the selected symbol is not already held.
- Existing `reports/llm/.../strategist/` artifacts remain stable.
- Stage-specific artifacts are mirrored under `strategist_stage*_...` folders.
- `llm_stage_manifest.json` records stage status and skip reasons.

Stage 3/4 activation update:

- Stage 3 now uses the existing open-position refresh path when repeated HOLD/loss/carry-risk criteria request a Strategist refresh.
- Stage 4 now runs in the session closeout guard when a held position remains near close.
- Stage 4 also runs in the default closeout phase when held positions remain.
- Pending BUY cancellation remains higher priority than Stage 4.
- Preopen carry-risk review is classified as Stage 3, not Stage 4.

Stage 3 still does not run on every HOLD. It is cadence/risk triggered. Stage 4 is closeout/carry specific.

## Stage 2 Runtime Contract Update

Decision date: 2026-05-08

The target design changes Stage 2 from an optional refresh into a default post-Scanner contract.

Reason:

- Stage 1 is a broad market frame and should not choose the final stock.
- Scanner is the first component that creates the concrete ranked candidate set for the current cycle.
- The main purpose of Stage 2 is to attach selected-symbol memory to that concrete Scanner result.
- If Stage 2 stays optional, the system can enter a symbol without ever comparing that symbol against its own historical memory.

Target same-cycle flow:

```text
Commander
-> Stage 1 Strategist market frame
-> Scanner ranked candidates
-> Commander packages Stage 2 input
-> Stage 2 Strategist selected-symbol tactical refresh
-> Commander clamps policy delta
-> Monitor calculates entry/hold/runner-up cascade
-> Decision/Execution
```

Stage 2 should run after Scanner produces a selected symbol and before Monitor makes a new entry decision, as long as:

- the market is in session,
- new entry capacity exists,
- the selected symbol is not empty,
- trading is not blocked by preflight, closeout, or hard risk controls.

Stage 2 can be skipped only for explicit operational reasons:

- no new entry can be made because max position capacity is reached,
- selected symbol is already held or has a pending BUY and duplicate same-symbol BUY is blocked,
- runtime is in monitor-only position-management path,
- LLM is unavailable and Commander must fall back to deterministic policy,
- closeout window blocks new BUY evaluation.

The skip reason must be recorded explicitly. Silent Stage 2 omission is not acceptable for the 4-stage design.

Commander still owns the Stage 2 boundary. Its role changes from "decide whether a refresh is needed" to:

- guarantee the post-Scanner Stage 2 call when eligible,
- package only the relevant selected-symbol memory,
- attach memory confidence and data-quality status,
- include runner-up memory only in compressed comparison form,
- clamp the Strategist output to allowed policy fields,
- keep hard risk controls outside LLM authority.

Stage 2 input must include:

- Stage 1 market frame and applied Commander policy summary,
- Scanner rank 1 selected symbol,
- runner-up candidates, usually top 3 to 5,
- selected-symbol memory packet,
- memory status: `present`, `sample_count`, `stale`, `confidence`, `data_quality`,
- live chart fields: price, VWAP, previous close, open gap, previous-close distance, volume, breakout/pullback state,
- net cost hurdle and estimated roundtrip cost,
- current position capacity and duplicate-symbol guard state.

Stage 2 output must not be a direct order. It should be a bounded policy recommendation:

```json
{
  "stage": "selected_symbol_tactical_refresh",
  "selected_symbol_action": "watch | avoid | watch_with_tighter_gates | cascade_to_runner_ups",
  "memory_usage": {
    "status": "used | disabled | insufficient | stale",
    "confidence": "low | medium | high",
    "reason": "string"
  },
  "monitor_policy_delta": {
    "action": "maintain | tighten | relax",
    "target_fields": ["string"],
    "reason": "string"
  },
  "cascade_policy": {
    "allowed": true,
    "max_runner_ups": 3,
    "allowed_reasons": ["below_vwap_reclaim_not_ready", "pullback_not_mature"]
  },
  "commander_actionability": "advisory_only | policy_delta_allowed | hard_block_recommended"
}
```

Commander final authority:

- LLM may recommend `avoid`, but Commander decides whether that becomes a hard block or only tighter gates.
- LLM may recommend cascade, but Commander clamps `max_runner_ups` and allowed reasons.
- LLM may recommend relaxed gates, but Commander must still enforce cost hurdle, duplicate symbol guard, max position count, closeout window, order notional, and loss controls.
- Memory evidence must never override live chart evidence by itself. Memory can tighten, warn, or prioritize, but cannot alone force a BUY.

## Memory Boundary Decision

Decision date: 2026-05-08

Stage 1 must not consume selected-symbol memory.

Current implementation note:

- The current single `strategic_frame` payload can contain broad memory fields such as `strategy_memory`, `memory_packets`, and `read_model_facts`.
- It can also contain `commander_refresh_context.selected_symbol_memory` when a refresh context exists.
- Live defaults currently disable memory usage, so these fields are often reduced to disabled/audit-only stubs.
- Structurally, however, the Stage 1 prompt still has a path that can expose symbol-level memory.

Target boundary:

- Stage 1 may receive market-wide and day-level context:
  - market/index context,
  - theme context,
  - broad recent performance summary,
  - high-level daily operator summary,
  - memory policy status.
- Stage 1 must not receive or reason from:
  - `selected_symbol_memory`,
  - `memory_packets.symbol_memory_packet`,
  - `read_model_facts.symbol_patterns`,
  - same-symbol win/loss history,
  - symbol-specific blocker history.
- Stage 2 is the first stage that may use selected-symbol memory.
- Stage 3 may use held-symbol memory only for the currently held position.
- Stage 4 may use held-symbol memory only as one input to close/carry risk, not as a direct carry approval.

Reason:

- Stage 1 is a broad market frame. If it sees symbol memory before Scanner has selected a concrete symbol, it can overfit to noisy historical data.
- Symbol memory belongs at the moment where the system knows which symbol is actually being considered.
- Keeping symbol memory out of Stage 1 makes the pipeline identity clearer: Strategist frames the market, Scanner selects candidates, Stage 2 reviews the selected symbol, Monitor calculates entry.

Implementation implication:

- Split the LLM payload by `call_kind`.
- For `market_strategy_frame`, strip symbol-level memory fields.
- For `selected_symbol_tactical_refresh`, include selected-symbol memory and compressed runner-up memory if available.
- For `stale_intraday_hold_review`, include only the held symbol's position, thesis, and relevant memory excerpt.
- For `end_of_day_carry_review`, include held-position and overnight risk memory only.

## Stage 3 and Stage 4 LLM Necessity Decision

Decision date: 2026-05-08

Stage 3 and Stage 4 should be conditional LLM calls, not unconditional per-cycle calls.

Stage 3 is useful when:

- a position is still open,
- deterministic exit rules have not already fired,
- the position has become stale relative to its intended horizon,
- repeated HOLD continues without enough progress,
- the original entry thesis is ambiguous rather than clearly intact or clearly broken,
- a bounded policy decision is needed: `hold`, `tighten_exit`, `exit_now`, or `wait_until_next_check`.

Stage 3 is not needed when:

- hard stop, stop loss, broker truth mismatch, price/PnL anomaly, or closeout hard block already applies,
- the position is fresh and still inside its expected hold window,
- Monitor has a clear deterministic exit signal,
- there is no open position.

Stage 4 is useful when:

- the closeout/15:20 window is active,
- one or more positions are still held,
- deterministic rules have not already forced flattening,
- the position is a plausible overnight/carry candidate,
- qualitative risk matters: Friday/weekend, holiday, overnight event, gap risk, news shock, index close quality.

Stage 4 is not needed when:

- no position is held,
- closeout hard-flat rules already require selling,
- weekend/holiday carry is disallowed by hard policy,
- underlying stop/loss/liquidity rules already require exit,
- carry conditions fail deterministic minimums such as PnL, VWAP, trend, or peak-drawdown floor.

Commander remains the final owner:

- Stage 3/4 LLM outputs are advisory or bounded policy deltas.
- Deterministic risk controls can override the LLM.
- LLM cannot approve a BUY, force an overnight carry, bypass cost gates, bypass same-symbol duplicate checks, or bypass closeout controls.

## Runtime Field Alignment

The runtime field for the operating horizon is `strategy_horizon`, not `primary_horizon`.

Allowed runtime values are:

- `scalp`
- `intraday`
- `overnight_probe`
- `1_2day_swing`

`scalp_intraday` and `swing_1_2day` are draft wording only and should not be used in runtime-facing JSON.

Current implementation note:

- Strategist may propose `strategy_horizon_feedback.strategy_horizon`.
- Commander converts that proposal into `commander_horizon_policy`.
- The policy is passed through `strategy_policy` and `monitor_policy`.
- Today this is primarily observability/reporting metadata.
- Runtime defaults keep `observability_only=true`, `allow_behavior_change=false`, and `do_not_force_hold=true`.
- Long-horizon proposals can be capped back to `intraday` during live validation.

Therefore `strategy_horizon` should not be treated as a direct behavior switch. If the horizon should affect live behavior, Commander must translate it into concrete policy fields such as:

- `scanner_scope.max_rank_to_monitor`
- `scanner_scope.runner_up_count`
- `scanner_scope.cascade_allowed`
- `monitor_instruction.watch_intensity`
- `monitor_instruction.required_confirmations`
- `exit_policy_delta.profit_take_style`
- `exit_policy_delta.tighten_stop`
- `exit_policy_delta.allow_overnight`

## Stage Summary

| Stage | Name | Timing | Core Question | Output Owner |
|---|---|---|---|---|
| 1차 | Market Strategy Frame | Before Scanner | What kind of market/trading strategy should be used now? | Strategist proposes, Commander applies |
| 2차 | Selected Symbol Tactical Refresh | After Scanner selects candidates | What does selected-symbol memory say, and how should Monitor watch this symbol? | Strategist proposes, Commander clamps |
| 3차 | Stale Intraday Hold Review | During an open position after hold gets stale | Is it still rational to keep holding this position intraday? | Strategist advises, Commander/Monitor act |
| 4차 | End-of-Day Carry Review | Around 15:20 closeout window | Should this position be closed today or carried overnight? | Commander owns final carry decision |

## 1차: Market Strategy Frame

### Intent

1차 is the broad strategy decision. It should not select the final stock and should not produce order instructions.

It decides:

- market regime
- playbook
- tactical strategy
- theme/scanner direction
- default monitor entry policy
- candidate watch proposal

### Input

Typical input:

- KOSPI/KOSDAQ current value, previous close, change percent
- US index movement, VIX, DXY, rates
- market breadth and macro risk
- market/news sentiment
- theme strength
- available Kiwoom themes
- broad candidate hints
- recent monitor blocker summary
- memory disabled/allowed policy

### Prompt Shape

Example prompt wording:

```text
You are the Strategist agent for an automated trading system.
Do not select a final stock and do not create order instructions.

Review the current market inputs:
- KOSPI/KOSDAQ index state
- US market and VIX context
- macro risk and market breadth
- available Kiwoom themes
- candidate hints
- current Commander memory policy

Choose exactly one playbook and one tactical strategy.
Return JSON only.
Explain in Korean why this playbook is appropriate.
Produce bounded scanner guidance, candidate watch proposal, and default monitor entry policy.
```

### Output Contract

Example output:

```json
{
  "call_kind": "market_strategy_frame",
  "playbook": "pullback",
  "tactical_strategy": "leader_vwap_reclaim_pullback",
  "strategy_scores": {
    "opening_gap_momentum": 0.1,
    "leader_vwap_reclaim_pullback": 0.8,
    "defensive_observe": 0.1
  },
  "selected_themes": ["반도체_시스템반도체", "셋톱박스"],
  "candidate_watch_policy": {
    "max_priority_rank": 5,
    "max_runner_ups": 4,
    "cascade_enabled": true,
    "cascade_allowed_reasons": ["below_vwap_reclaim_not_ready", "pullback_not_mature"]
  },
  "monitor_entry_policy": {
    "volume_ratio_min": 0.68,
    "max_extended_from_vwap_pct": 0.13,
    "require_vwap_reclaim": true,
    "require_rebound": true
  },
  "rationale": "시장은 중립이고 지수는 완만하게 우호적이나 강한 갭 추격 근거는 부족하므로 VWAP 회복형 풀백을 우선합니다."
}
```

## 2차: Selected Symbol Tactical Refresh

### Intent

2차 is the post-Scanner decision.

The main reason to add 2차 is selected-symbol memory.

1차 should not let noisy historical symbol memory dominate the whole market frame. 2차 is the right place to ask:

- "Scanner selected this symbol now."
- "What has happened when this same symbol or similar symbol setup appeared before?"
- "Should we still watch it, avoid it, or change Monitor conditions?"

It answers:

- What does symbol-level memory say about this selected symbol?
- Is Scanner's selected symbol still aligned with the 1차 strategy?
- Should Monitor watch only rank 1, or cascade through runner-ups?
- Which entry evidence should Monitor prioritize for this specific symbol?
- Should the 1차 monitor policy be tightened, relaxed, or kept?

This stage is important because the 1차 market strategy is broad, while actual trading happens on one selected symbol at a specific chart location with its own memory.

### At-a-Glance

| Part | What the LLM Sees or Produces |
|---|---|
| Input | Scanner selected symbol, runner-ups, current chart state, cost filter, position capacity, and selected-symbol memory |
| Prompt instruction | "Do not choose a new market strategy. Re-check this selected symbol using chart evidence and symbol memory." |
| Output | WATCH / AVOID / WATCH_WITH_TIGHTER_GATES / CASCADE_TO_RUNNER_UPS, plus memory assessment and Monitor policy delta |

### Memory Policy

2차 should use memory differently from 1차.

- 1차 memory use should be broad and conservative, or disabled if Commander has disabled strategy memory.
- 2차 may consume `symbol_memory_packet` when Commander explicitly allows selected-symbol memory.
- 2차 must not use weekly/monthly broad memory to override the market playbook by itself.
- 2차 must separate memory evidence from live chart evidence.
- If memory is disabled, 2차 must say `memory_usage.status=disabled` and rely only on live Scanner/Monitor evidence.

### Input

Typical input:

- Stage 1 strategy output
- Scanner selected symbol
- Scanner rank, score, and selected reason
- runner-up candidates
- selected-symbol memory packet:
  - previous trades in the same symbol
  - win/loss count
  - average return
  - repeated entry failure reasons
  - repeated exit failure reasons
  - post-exit shadow behavior, if available
  - symbol-specific cautions or positive patterns
- current price, VWAP distance, previous close, open gap
- volume ratio, breakout gap, pullback depth
- cost filter evidence
- open position count and max position capacity
- recent same-symbol/pending-position guard state

### Input Example

```json
{
  "call_kind": "selected_symbol_tactical_refresh",
  "stage1_strategy": {
    "playbook": "pullback",
    "tactical_strategy": "leader_vwap_reclaim_pullback",
    "monitor_entry_policy": {
      "volume_ratio_min": 0.68,
      "require_vwap_reclaim": true,
      "require_rebound": true
    }
  },
  "scanner_selection": {
    "selected_symbol": "078890",
    "rank": 1,
    "score": 1.43,
    "selected_reason": "theme support + volume recovery",
    "runner_ups": ["005930", "000660", "005380"]
  },
  "live_symbol_evidence": {
    "current_price": 8850,
    "previous_close": 8300,
    "open_gap_pct": -0.0157,
    "prev_close_distance_pct": 0.0663,
    "vwap_distance_pct": 0.0375,
    "volume_ratio": 1.11,
    "breakout_gap_pct": 0.0103,
    "pullback_depth_pct": 0.0103,
    "cost_adjusted_edge_ok": true
  },
  "symbol_memory_packet": {
    "enabled": true,
    "symbol": "078890",
    "trade_count": 4,
    "win_rate": 0.25,
    "avg_return_pct": -0.42,
    "repeated_entry_failures": ["late_breakout_chase", "weak_follow_through_after_vwap_reclaim"],
    "repeated_exit_failures": ["small_gross_win_net_loss_after_costs"],
    "positive_patterns": ["works better when volume_ratio > 1.2 and VWAP reclaim holds for 2 bars"],
    "post_exit_shadow": {
      "often_recovered_after_sell": false,
      "often_faded_after_entry": true
    }
  },
  "portfolio_capacity": {
    "open_position_count": 2,
    "max_positions": 3,
    "capacity_remaining": 1,
    "same_symbol_already_held": false
  }
}
```

### Prompt Shape

Example prompt wording:

```text
Scanner selected one primary symbol and several runner-ups.
Re-check the Stage 1 strategy against this selected symbol.

The main reason for this call is selected-symbol memory.
Use symbol_memory_packet only for this selected symbol.
Do not use symbol memory to rewrite the whole market playbook.
Separate live chart evidence from memory evidence.

Do not create an order.
Decide whether Monitor should:
- watch only the selected symbol
- allow cascade to runner-ups
- avoid this symbol because symbol memory is poor
- watch this symbol only with tighter gates because symbol memory is mixed
- tighten or relax entry checks
- prioritize VWAP reclaim, breakout, pullback, volume, or cost edge

Return:
- symbol memory assessment
- live chart assessment
- final symbol decision
- monitor focus
- candidate/cascade scope
- entry policy delta

Return JSON only.
```

### Output Contract

Example output:

```json
{
  "call_kind": "selected_symbol_tactical_refresh",
  "selected_symbol": "078890",
  "evidence_confidence": "medium",
  "data_quality": "ok",
  "commander_actionability": "can_tighten_monitor",
  "symbol_decision": "WATCH_WITH_TIGHTER_GATES",
  "memory_usage": {
    "status": "enabled",
    "symbol": "078890",
    "used": true,
    "summary": "과거 같은 종목에서는 VWAP 회복 후 추격 진입의 후속 상승이 약했고, 비용 반영 후 작은 수익이 손실로 바뀐 사례가 있었습니다.",
    "positive_evidence": ["volume_ratio > 1.2 and 2-bar VWAP hold improved outcomes"],
    "negative_evidence": ["late_breakout_chase", "weak_follow_through_after_vwap_reclaim", "small_gross_win_net_loss_after_costs"]
  },
  "live_chart_assessment": {
    "aligned_with_stage1": true,
    "strengths": ["VWAP 위 유지", "breakout gap positive", "cost_adjusted_edge_ok"],
    "weaknesses": ["vwap_distance already extended", "symbol memory warns against late chase"]
  },
  "candidate_scope": {
    "max_priority_rank": 3,
    "max_runner_ups": 2,
    "cascade_enabled": true,
    "cascade_reason": "선정 종목은 감시하되 종목 메모리가 추격 진입 리스크를 경고하므로 2~3순위도 함께 열어둡니다."
  },
  "monitor_focus": {
    "primary": ["vwap_reclaim_hold_2bars", "volume_confirmation", "cost_adjusted_edge"],
    "secondary": ["pullback_depth", "extension_control"],
    "blockers": ["cost_filter_failed", "same_symbol_position_open", "late_breakout_chase"]
  },
  "entry_policy_delta": {
    "action": "tighten",
    "fields": {
      "volume_ratio_min": 1.2,
      "require_vwap_reclaim_hold_bars": 2,
      "max_extended_from_vwap_pct": 0.1
    },
    "reason": "1차 시장 프레임은 풀백 감시에 우호적이지만, 선택 종목 메모리는 늦은 돌파 추격과 비용 손실을 경고하므로 거래량과 VWAP 유지 확인을 강화합니다."
  }
}
```

## 3차: Stale Intraday Hold Review

### Intent

3차 is not the overnight decision.

3차 is used when the system is already holding a position for too long during the same trading session.

It answers:

- Is the original entry thesis still valid?
- Is this just normal noise, or is the position wasting time?
- Should Monitor keep holding, tighten exit, or exit now?
- Has the position failed to make progress after enough time?

This stage should never create a new BUY strategy.

Additional buy / scale-in review is intentionally excluded from this draft.
If scale-in is needed later, it should be designed as a separate `scale_in_review` policy because it changes position sizing and same-symbol exposure risk.

### Trigger Examples

Possible triggers:

- hold time exceeds target hold window
- repeated HOLD count reaches a threshold
- price is flat after entry while cost drag makes breakeven difficult
- monitor keeps saying HOLD but entry thesis is no longer clean
- VWAP/reclaim/volume evidence deteriorates
- position is not at stop-loss, but opportunity cost is rising

### Review Scheduling Artifact

Stage 3 should not be triggered only by a raw HOLD count.

The runtime should persist a small review artifact when a new position is opened. Commander creates or updates this artifact from:

- Stage 1 market frame,
- Stage 2 selected-symbol tactical refresh,
- strategy horizon,
- current market regime,
- expected holding window,
- cost hurdle,
- live validation/risk policy.

Example artifact:

```json
{
  "symbol": "005930",
  "entry_epoch": 1778202720,
  "strategy_horizon": "intraday",
  "entry_thesis": "leader_vwap_reclaim_pullback",
  "expected_hold_window_sec": {
    "min": 300,
    "target": 900,
    "max": 1800
  },
  "first_review_after_sec": 900,
  "review_cadence_sec": 600,
  "next_review_epoch": 1778203620,
  "max_hold_sec_before_review": 1800,
  "review_triggers": [
    "hold_repeat",
    "thesis_weakened",
    "market_regime_flip",
    "net_profit_stall",
    "vwap_structure_changed"
  ],
  "last_review": {
    "epoch": null,
    "decision": "",
    "next_check_sec": null
  }
}
```

Initial cadence guidance:

| Horizon | First Stage 3 Review | Follow-up Cadence | Notes |
|---|---:|---:|---|
| `scalp` | 5-7 minutes | 5 minutes | Use only if no deterministic exit has fired. |
| `intraday` | 10-15 minutes | 10-15 minutes | Main default for current live path. |
| `overnight_probe` | 30-60 minutes or closeout | 30 minutes | Prefer Stage 4 near close over repeated Stage 3 calls. |
| `1_2day_swing` | Minimize intraday Stage 3 | Preopen/close review | Do not churn long-horizon ideas intraday. |

Stage 3 trigger rule:

- Monitor continues calculating every cycle.
- Commander checks the artifact.
- Stage 3 LLM is called only when `now >= next_review_epoch` or an urgent review trigger appears.
- If deterministic exit rules fire, Commander/Monitor should act without waiting for Stage 3.
- After a Stage 3 result, Commander updates `last_review` and `next_review_epoch`.

This avoids the weakness of a pure `hold_repeat_count >= 3` rule. HOLD count can still be one signal, but elapsed time and strategy horizon must be the primary schedule.

### Input

Typical input:

- symbol
- entry time and holding duration
- buy price, current price, high since entry, low since entry
- gross PnL and cost-adjusted PnL
- expected round-trip cost
- original entry reason
- current monitor reason
- repeated HOLD count
- VWAP distance, volume trend, reclaim status
- market regime change since entry
- invalidation conditions from Stage 1/2

### Prompt Shape

Example prompt wording:

```text
You are the intraday stale-hold review Strategist.
Do not produce a new entry strategy.
Only decide whether the existing held position should remain open.

Review:
- original entry thesis
- current chart evidence
- holding duration
- repeated HOLD count
- cost-adjusted PnL
- whether the position has made progress

Return JSON only with HOLD / EXIT_NOW / TIGHTEN_EXIT / WAIT_UNTIL_NEXT_CHECK.
```

### Output Contract

Example output:

```json
{
  "call_kind": "stale_intraday_hold_review",
  "symbol": "076610",
  "evidence_confidence": "medium",
  "data_quality": "ok",
  "commander_actionability": "can_tighten_monitor",
  "decision": "TIGHTEN_EXIT",
  "thesis_still_valid": true,
  "invalidation_hit": false,
  "time_decay_warning": true,
  "reason": "진입 논리는 완전히 깨지지 않았지만 보유 시간이 길어졌고 거래량 재확인이 약해졌습니다. 즉시 청산보다는 다음 확인 전까지 이탈 기준을 좁히는 것이 합리적입니다.",
  "monitor_override": {
    "tighten_stop": true,
    "reduce_next_check_sec": 120,
    "exit_if_vwap_reclaim_fails": true,
    "exit_if_cost_adjusted_pnl_below_pct": -0.004
  },
  "next_check_sec": 120
}
```

## 4차: End-of-Day Carry Review

### Intent

4차 is the closeout/overnight decision.

It is separate from 3차.

3차 asks: "This intraday hold is getting stale. Should we keep holding right now?"

4차 asks: "Near the close, should this position be closed today or carried overnight?"

### Timing

The default trigger is around 15:20 KST or the configured closeout window.

### Conditional LLM Gate

Stage 4 should not be called for every closeout cycle.

Call Stage 4 only when:

- closeout/carry review time is active,
- at least one position is still held,
- the position is not already forced flat by hard risk policy,
- deterministic carry checks say the position is at least plausible,
- qualitative overnight risk could change the decision.

Do not call Stage 4 when:

- no open position exists,
- hard stop, loss limit, broker mismatch, price/PnL anomaly, or closeout hard-flat policy already decides the action,
- Friday/weekend/holiday carry is disallowed by hard Commander policy,
- deterministic minimums fail before LLM review, such as:
  - PnL below carry floor,
  - VWAP below carry floor,
  - trend too weak,
  - peak drawdown too deep,
  - underlying non-EOD exit signal active.

The Friday/weekend rule should remain a hard Commander/Monitor guard. LLM may explain risk, but it must not bypass a default weekend-carry block.

### Input

Typical input:

- current held positions
- time to close
- intraday PnL and cost-adjusted PnL
- liquidity near close
- end-of-day price location
- market/index closing condition
- news shock or overnight risk
- whether the trade was originally intraday/scalp/swing
- previous 3차 stale-hold review result, if any

### Prompt Shape

Example prompt wording:

```text
You are the end-of-day carry review Strategist.
Do not propose new entries.
For each held position, decide whether it should be closed today or allowed to carry overnight.

Separate intraday stale-hold concerns from overnight risk.
Return JSON only.
```

### Output Contract

Example output:

```json
{
  "call_kind": "end_of_day_carry_review",
  "as_of_time_kst": "15:20",
  "positions": [
    {
      "symbol": "005930",
      "decision": "CLOSE_TODAY",
      "overnight_carry_approved": false,
      "reason": "원래 장중 풀백 전략으로 진입했고 종가 부근 모멘텀 확장이 부족합니다. 오버나이트 보상보다 갭 리스크가 큽니다.",
      "closeout_priority": "normal"
    }
  ],
  "portfolio_decision": {
    "allow_new_overnight_exposure": false,
    "reason": "현재 전략은 장중 대응 중심이며 장마감 직전 보유 근거가 충분하지 않습니다."
  }
}
```

## Reasonableness Assessment

This four-stage design is reasonable if the stages remain strict.

Every LLM stage should include these guard fields:

- `evidence_confidence`: `low|medium|high`
- `data_quality`: `ok|stale|insufficient`
- `commander_actionability`: `advisory_only|can_tighten_monitor|can_block_entry|can_request_exit_review|can_request_carry_review`

These fields prevent weak evidence from being treated like an executable command.

Good separation:

- 1차 decides the market strategy, not the stock.
- 2차 decides how to watch the selected stock, not whether to hold an existing stale position.
- 3차 decides stale intraday holding, not overnight carry.
- 4차 decides overnight/carry, not fresh entry.
- Additional buy / scale-in is deferred and should not be mixed into 3차 in this draft.

Main risk:

- Too many LLM calls can increase latency and cost.
- If every stage can change every policy, the system becomes inconsistent.
- If 3차 is too eager, it may force exits before Monitor's technical exit rules mature.

Mitigation:

- Commander owns final execution authority.
- Every stage has a narrow output contract.
- 2차 only runs when Scanner has a selected candidate and entry capacity exists.
- 3차 only runs when hold time/repeated HOLD crosses a threshold.
- 4차 only runs in the closeout window.
- Each LLM result must be logged with `call_kind`, prompt, response, selected symbol, and final Commander action.

## Proposed Call Kinds

Use explicit call kinds so reports are understandable:

- `market_strategy_frame`
- `selected_symbol_tactical_refresh`
- `stale_intraday_hold_review`
- `end_of_day_carry_review`

## Reporting Rule

Operator summaries should show these as separate sections:

```text
1차 시장 전략:
- 입력: 지수/시장/뉴스/테마
- 출력: playbook, tactical strategy, scanner direction

2차 종목 전략:
- 입력: 스캐너 선택 종목과 후보군
- 출력: 감시 범위, 모니터 우선 조건

3차 장중 보유 점검:
- 입력: 보유 시간, 손익, HOLD 반복, 현재 차트
- 출력: HOLD/EXIT/TIGHTEN/WAIT

4차 장마감 보유 판단:
- 입력: 15:20 보유 상태, 종가 리스크, 오버나이트 근거
- 출력: CLOSE_TODAY/CARRY_OVERNIGHT
```

Reports must not imply a stage ran if there was no LLM call for that stage. In that case the report should say:

```text
3차 장중 보유 점검: 미실행
사유: 보유 시간/반복 HOLD 조건 미충족
```

## Implementation Direction

Suggested rollout order:

1. Add explicit report fields and event names for the four stages.
2. Split the current single `strategic_frame` prompt into Stage 1 and Stage 2 first.
3. Add Stage 3 as observability-only, with no execution override for the first validation period.
4. Add Stage 4 as separate closeout/overnight review.
5. Only after validation, allow Commander to consume Stage 3/4 outputs as bounded Monitor overrides.
