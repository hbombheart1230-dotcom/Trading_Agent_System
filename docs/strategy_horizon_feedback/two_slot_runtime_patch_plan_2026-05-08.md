# Two-Slot Runtime Patch Plan

## Status

HOLD / deferred design note.

As of 2026-05-08, this is not the next runtime patch. The active path is
`multi_position_minimal_patch_plan_2026-05-08.md`.

This document is retained only as a historical alternative if the system later
needs explicit holding-period slot attribution.

Do not implement this plan unless the two-slot design is explicitly reactivated.
The current live path is not slot-based and should not use `slot_*`,
`horizon_slot`, or slot-capacity fields.

Current target:

- `short_term`: current scalp/intraday trading lane
- `long_hold`: overnight, 1-2 day, and multi-day holding lane

Commander owns every executable decision. Strategist proposes slot intent,
scanner/monitor directives, and carry guidance. Scanner and Monitor calculate
evidence and candidate/entry/exit signals. Commander decides which slot may
act and whether the proposal is allowed in live runtime.

## Non-Negotiable Rules

1. Commander is the final owner.

Strategist output must never directly open a slot, override risk, or force an
overnight hold. It only proposes.

2. Maximum active symbols:

- `short_term`: max 1 active symbol
- `long_hold`: max 1 active symbol
- account total: max 2 active symbols

3. Same symbol cannot be held by both slots.

If `short_term=005930`, `long_hold` must reject `005930` until the short-term
position is closed and broker truth confirms the close.

4. Hard risk overrides both slots.

Emergency exit, broker truth mismatch, daily loss limit, price anomaly,
liquidity collapse, and account-level risk limits override strategist slot
intent.

5. If `long_hold` carry decision is missing or stale at the close decision
time, default is flatten before close.

Long hold is allowed only when the system can explain why the position should
survive overnight.

## Slot Ownership Model

Runtime should maintain a deterministic `slot_runtime_state`:

```json
{
  "schema_version": "slot_runtime_state.v1",
  "owner": "commander",
  "slots": {
    "short_term": {
      "max_symbols": 1,
      "status": "available|occupied|blocked",
      "symbol": "005930",
      "position_qty": 10,
      "entry_trade_id": "TRD_...",
      "block_reason": ""
    },
    "long_hold": {
      "max_symbols": 1,
      "status": "available|occupied|blocked",
      "symbol": "000660",
      "position_qty": 1,
      "entry_trade_id": "TRD_...",
      "block_reason": ""
    }
  },
  "total_active_symbols": 2,
  "same_symbol_cross_slot_blocked": false,
  "global_block_reason": ""
}
```

Slot state is derived from:

- broker positions
- open order / pending order state
- recent execution metadata
- persisted trade lifecycle metadata
- fallback inference after restart

Fallback rule after restart:

- If a position has persisted `horizon_slot`, restore that slot.
- If no slot metadata exists, classify the existing position as `short_term`
  unless there is a persisted overnight/carry approval for the same symbol.
- Do not infer `long_hold` only from the fact that a position survived close;
  it needs a recorded carry approval or explicit persisted slot.

## Strategist Input Additions

Every strategist call should receive a compact slot context:

```json
{
  "slot_context": {
    "available_slots": ["short_term", "long_hold"],
    "occupied_slots": {
      "short_term": {"symbol": "", "qty": 0},
      "long_hold": {"symbol": "", "qty": 0}
    },
    "blocked_slots": {
      "short_term": "",
      "long_hold": ""
    },
    "same_symbol_blocklist": ["005930"],
    "runtime_decision_time": {
      "phase": "session|closeout",
      "minutes_to_close": 10.0,
      "carry_review_due": true,
      "carry_review_cutoff_kst": "15:20"
    },
    "commander_constraints": {
      "max_symbols_per_slot": 1,
      "max_total_symbols": 2,
      "commander_final_authority": true,
      "long_hold_requires_carry_approval": true
    }
  }
}
```

The input must also tell the strategist whether the call is:

- first/base market strategy
- post-scanner selected-symbol refresh
- open-position refresh
- close/carry review refresh

The post-scanner refresh is still mandatory. It becomes more important because
the strategist must say whether the selected symbol is a `short_term` trade, a
`long_hold` candidate, or no trade after seeing the concrete symbol.

## Strategist Output Additions

Strategist should output a slot proposal, not only a generic horizon:

```json
{
  "slot_strategy": {
    "recommended_slot": "short_term|long_hold|none",
    "source_strategy_horizon": "scalp|intraday|overnight_probe|1_2day_swing|short_term|long_hold",
    "slot_reason": "string",
    "slot_confidence": 0.0,
    "slot_rejection_reason": "",
    "candidate_watch_policy": {
      "short_term": {
        "max_priority_rank": 10,
        "max_runner_ups": 4,
        "cascade_enabled": true,
        "reason": "string"
      },
      "long_hold": {
        "max_priority_rank": 5,
        "max_runner_ups": 2,
        "cascade_enabled": true,
        "reason": "string"
      }
    },
    "slot_policies": {
      "short_term": {
        "entry_style": "breakout|pullback|reclaim|opening_gap|none",
        "monitor_timing": "current_intraday",
        "allow_eod_flat": true,
        "requires_1520_carry_review": false
      },
      "long_hold": {
        "entry_style": "pullback_reclaim|trend_continuation|close_strength|none",
        "monitor_timing": "less_chase_more_confirmation",
        "allow_eod_flat": false,
        "requires_1520_carry_review": true,
        "carry_review_policy": {
          "default_without_fresh_review": "flatten_before_close",
          "minimum_hold_reason": "theme_or_market_continuation",
          "required_positive_checks": ["trend_strength", "vwap_or_close_strength", "market_support"],
          "hard_blockers": ["loss_beyond_floor", "vwap_breakdown", "market_regime_flip", "liquidity_collapse"]
        }
      }
    }
  }
}
```

This output remains a proposal. Commander normalizes it into
`commander_slot_policy`.

## Commander Slot Policy

Commander should produce the executable policy:

```json
{
  "schema_version": "commander_slot_policy.v1",
  "owner": "commander",
  "active_cycle_slot": "short_term|long_hold|monitor_only",
  "slot_runtime_state": {},
  "slot_entry_permission": {
    "short_term": {
      "allowed": true,
      "reason": "slot_available",
      "max_priority_rank": 10,
      "max_runner_ups": 4
    },
    "long_hold": {
      "allowed": true,
      "reason": "slot_available",
      "max_priority_rank": 5,
      "max_runner_ups": 2
    }
  },
  "slot_exit_permission": {
    "short_term": {"manage_existing_position": true},
    "long_hold": {"manage_existing_position": true, "requires_1520_carry_review": true}
  },
  "global_blocks": [],
  "same_symbol_blocklist": []
}
```

Commander should choose the active cycle in this order:

1. Emergency exit / broker truth mismatch for any slot
2. Open-position monitoring for occupied slots
3. 15:20 long-hold carry review if a `long_hold` position exists
4. Entry search for available slots
5. No action

The runtime may still emit at most one order intent per tick. That is
acceptable if Commander rotates the active cycle deterministically and always
prioritizes exits over entries.

## Short-Term Slot Behavior

`short_term` should keep the current behavior:

- Same scanner candidate ranking and cascade concept
- Same post-scanner strategist refresh
- Same intraday monitor entry signal logic
- Same cost-aware entry filter
- Same profit-taking and stop-loss monitor policy
- Same closeout buy block
- Same EOD flat behavior

The main change is guard scope:

- Current global `open_position_present` must become
  `short_term_slot_occupied` for short-term entries.
- If `long_hold` is occupied but `short_term` is available, `short_term` entry
  may still run unless global risk blocks it.

## Long-Hold Slot Behavior

`long_hold` should use the same raw scanner/monitor data surfaces, but
Commander and Strategist should ask different questions.

Scanner differences:

- prefer liquidity and stable turnover over single-tick acceleration
- prefer market/index support and sector breadth
- prefer daily/previous-close structure and close strength
- penalize extreme intraday extension unless there is a pullback/reclaim
- reject symbols already active in `short_term`

Monitor entry differences:

- do not chase late spikes
- prefer pullback/reclaim, VWAP recovery, or close-strength continuation
- require cost-adjusted edge like short-term, but expected edge must include
  overnight risk
- position size may be smaller than short-term until sample quality improves

Monitor exit differences:

- hard stop remains hard
- broker/data/liquidity anomalies remain hard
- soft profit exits should not automatically flatten if carry thesis is still
  intact
- EOD flat is disabled only after Commander approves carry
- without carry approval, flatten before close

## 15:20 Carry Decision

The close decision should be explicit and recorded.

Recommended timing:

- Start carry refresh around 15:15 KST when a `long_hold` position exists.
- Commander must have a fresh carry policy by 15:20 KST.
- At 15:20 KST, Commander decides carry or flatten.
- If no fresh strategist carry output exists by 15:20, flatten before close.

Carry decision output:

```json
{
  "long_hold_carry_review": {
    "symbol": "000660",
    "review_time_kst": "15:20",
    "decision": "carry_overnight|flatten_before_close",
    "confidence": 0.0,
    "carry_thesis": "string",
    "next_session_plan": {
      "expected_gap_behavior": "gap_up|flat|gap_down|unknown",
      "must_hold_conditions": ["string"],
      "next_day_exit_triggers": ["string"],
      "invalid_before_open_if": ["string"]
    },
    "positive_checks": ["string"],
    "blockers": ["string"],
    "commander_may_override": true
  }
}
```

Deterministic Commander/Monitor blockers at 15:20:

- current net PnL below carry floor
- underlying exit signal excluding soft profit exits
- VWAP/close structure breakdown
- market regime flip or index weakness
- liquidity collapse
- price anomaly or broker truth mismatch
- no fresh carry review

Existing `_evaluate_overnight_carry_decision` should be reused as the base
deterministic check, but it should become slot-aware and read
`long_hold_carry_review` / `commander_slot_policy` instead of only generic
`monitor_guidance`.

## Scanner And Monitor Integration

Initial implementation should not create a completely separate scanner or
monitor.

Use one scanner and one monitor, but pass a slot profile:

```json
{
  "active_cycle_slot": "long_hold",
  "slot_profile": {
    "candidate_profile": "long_hold",
    "entry_profile": "long_hold",
    "exit_profile": "long_hold",
    "carry_review_required": true
  }
}
```

Reason: duplicating scanner/monitor now would create two systems to debug.
The safer patch is to make the existing nodes slot-aware and keep the evidence
surfaces consistent.

## Required Code Patch Order

1. Add slot normalization helpers.

- map raw horizon hints into `short_term` / `long_hold`
- add `horizon_slot`, `source_strategy_horizon`, `commander_slot_policy`
- keep old fields for backward compatibility

2. Extend strategist schema and prompt.

- add `slot_context` to input
- add `slot_strategy` and `long_hold_carry_review` to output contract
- require post-scanner refresh to classify selected symbol into a slot

3. Add Commander slot state and slot guard.

- build slot occupancy from positions/persisted state
- replace global open-position entry block with slot-aware block
- enforce same-symbol cross-slot block
- keep account-level risk override

4. Pass slot policy to scanner and monitor.

- scanner: candidate profile and rank/cascade depth per slot
- monitor: entry/exit profile per slot
- one order intent per tick remains acceptable

5. Make overnight/carry logic long-hold aware.

- schedule or trigger carry review before 15:20
- flatten if no fresh carry decision
- persist carry decision by symbol and slot

6. Persist slot attribution.

- order intent meta
- execution packet
- lifecycle bundle
- trade report
- operator summary
- restart recovery state

7. Tests and reports.

- slot mapping
- max 1 per slot
- max 2 total
- same-symbol cross-slot block
- short-term entry allowed while long-hold occupied
- long-hold entry allowed while short-term occupied
- 15:20 carry approval
- 15:20 missing review flatten
- report slot attribution

## Implementation Boundary For First Patch

First live patch should implement:

- slot normalization
- strategist input/output contract additions
- Commander slot policy in artifacts
- slot-aware open-position block for entry
- same-symbol block
- report observability fields

First live patch should not yet:

- split one runtime tick into multiple parallel monitor executions
- let LLM override hard exit
- use memory to choose slots
- scale into same symbol from both slots

That gives live visibility first while keeping the behavioral blast radius
controlled.
