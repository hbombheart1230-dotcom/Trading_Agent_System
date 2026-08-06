# Strategy Horizon Feedback

This folder documents the strategy-horizon and post-exit feedback loop.

Current cross-domain evaluation decision:

- `docs/quant_trade_diagnosis/integrated_selection_horizon_sequence_evaluation_2026-07-31.md`
- Strategy Horizon Feedback remains the operational time contract.
- Quant Trade Diagnosis remains the per-trade evidence adapter.
- Selection, horizon, exit, delayed reactivation, and same-symbol sequences are
  evaluated together by the integrated read model; they are not independent
  promotion programs.

The goal is to separate three things that are currently easy to mix together:

- strategist proposal: what kind of trade the strategist thinks this could be
- commander horizon policy: what holding horizon the runtime is allowed to operate under
- monitor action: why the position was actually exited
- post-exit evidence: what would have happened if the system had not sold there

Current active design:

- `multi_position_minimal_patch_plan_2026-05-08.md`
- `strategist_4stage_llm_flow_draft_2026-05-08.md`
- `strategy_horizon_and_post_exit_shadow_tracking_2026-04-25.md`
- `position_horizon_revision_contract_2026-08-05.md`

Important active-scope clarification:

- The earlier four-slot strategy idea is HOLD/deferred.
- The earlier two-slot short/long design is HOLD/deferred.
- The current live path is not slot-based.
- The current live path keeps the existing Strategist -> Scanner -> Monitor flow and only allows a small multi-position capacity with duplicate same-symbol BUY blocking.
- The 1차/2차/3차/4차 language means Strategist LLM review stages, not position slots.
- New runtime-facing docs for the active path should use position-capacity wording, not `slot_*`, `horizon_slot`, or `remaining_position_slots`, unless slot attribution is explicitly reactivated later.

Deferred design notes:

- `horizon_slot_one_symbol_policy_2026-05-08.md`
- `horizon_slot_report_layout_2026-05-08.md`
- `two_slot_runtime_patch_plan_2026-05-08.md`

## Scope

This folder owns:

- minimal multi-position policy for the current runtime path
- same-symbol duplicate BUY blocking
- max-position entry gating
- Commander-owned operational horizon policy derived from strategist proposal, runtime phase, memory, and live-validation constraints
- monitor exit-vs-strategy-intent logging
- post-exit shadow tracking after a closed trade
- deterministic memory fields derived from post-exit price behavior
- rollout rules for live validation before changing hold behavior
- four-stage Strategist LLM flow separation:
  - Stage 2 target contract: default post-Scanner selected-symbol memory check, with Commander packaging memory and clamping policy deltas.
  - 1차 market strategy frame
  - 2차 selected-symbol tactical refresh
  - 3차 stale intraday hold review
  - 4차 end-of-day carry review

This folder does not own:

- final symbol selection; that remains Scanner responsibility
- broker truth; see `docs/kiwoom_truth`
- general runtime memory contracts; see `docs/runtime_memory`
- strategist output explanation contract; see `docs/strategist_output`

## Operating Rule

The original implementation was observability-only. That rollout state is
historical and is no longer the active runtime contract.

As of `2026-08-05`, Strategist proposes the horizon and Commander publishes the
authoritative operational policy. The position stores immutable
`entry_horizon` provenance and a mutable `active_horizon`. Monitor consumes the
active horizon. An unrelated strategy cycle cannot replace it; only an explicit
Stage 3 same-session review or Stage 4 closeout review can revise it.

Canonical windows:

| Horizon | Minimum | Target | Maximum |
| --- | ---: | ---: | ---: |
| `scalp` | 60 sec | 300 sec | 900 sec |
| `intraday` | 300 sec | 1,800 sec | 14,400 sec |
| `overnight_probe` | 1,800 sec | 14,400 sec | 86,400 sec |
| `1_2day_swing` | 3,600 sec | 86,400 sec | 172,800 sec |

Runtime semantics:

- minimum hold is enforced for ordinary soft exits
- hard stop, emergency, broker/data integrity, and other hard invalidations may exit before the minimum
- target hold is a reassessment/profit-management point, not a forced hold
- maximum hold is the strategy time limit
- overnight carry additionally requires `overnight_probe` or `1_2day_swing`
- weekend/holiday and independent carry-risk blocks remain authoritative
- the exit-vs-strategy artifact remains observational even though the
  Commander horizon policy now changes runtime behavior

Exit loosening must not be used as the first fix for low trade quality. As of the `2026-04-29` conservatism review, recent closed trades show that fee/tax drag and breakeven distance can turn flat gross exits into meaningful net losses. Any wider stop, delayed peak-drawdown exit, or hold-extension rule should be gated behind a cost-aware entry filter and reported as `cost_adjusted_edge_ok=true`.

## Current Validation Status

As of `2026-05-08`, the current target design is minimal multi-position:

- keep the current Strategist -> Scanner -> Monitor flow
- do not pre-assign positions into short/long slots
- increase max active positions from 1 to a small number, starting with 3
- block duplicate same-symbol BUYs
- keep existing overnight/carry policy

The two-slot design is deferred. It is not the next implementation target.

Stage 2 contract update:

- Stage 2 should be treated as the default post-Scanner selected-symbol memory check, not as a rare optional refresh.
- Stage 1 remains a broad market frame and should not pick the final stock.
- Stage 1 should not consume selected-symbol memory, symbol memory packets, or symbol-level win/loss/blocker history.
- Scanner creates the concrete ranked candidate set.
- Commander packages Stage 2 input after Scanner: selected symbol, runner-ups, selected-symbol memory, memory confidence/data quality, cost and live chart context, position capacity, and duplicate-symbol guard state.
- Commander still owns hard risk controls and clamps Stage 2 output to bounded policy deltas before Monitor uses them.
- Silent omission of Stage 2 is not acceptable in the target 4-stage design; any skip must have an explicit operational reason.

Stage 3/4 contract update:

- Stage 3 and Stage 4 are conditional LLM calls, not every-cycle calls.
- Stage 3 is for stale intraday hold review only. Commander should schedule it from a persisted review artifact using strategy horizon, elapsed hold time, thesis status, market state, and review cadence.
- Stage 3 may revise `active_horizon` only between `scalp` and `intraday`; it cannot authorize overnight carry.
- Stage 3 must not wait in front of hard deterministic exits such as stop loss, price/PnL anomaly, broker truth mismatch, or closeout hard flat.
- Stage 4 is for closeout/overnight carry review only. It should run near the carry window only when a held position is a plausible carry candidate and qualitative overnight risk matters.
- New positions require explicit per-symbol Stage 4 approval before Monitor can carry them overnight.
- Weekend/holiday carry blocks remain hard Commander/Monitor policy. LLM may explain risk but cannot bypass them.

Historical checkpoint: as of `2026-04-28 12:38 KST`, the inspected live monitor
artifact verified the then-active observability-only path:

- `horizon_owner=commander`
- `strategy_horizon=intraday`
- `observability_only=true`
- current action remains `NOOP` / `WAIT`
- no hold-extension behavior change was enabled at that checkpoint

That checkpoint must not be interpreted as the current policy. See
`horizon_operational_contract_fix_2026-07-24.md`.

Current limitation:

- no real exit happened in the inspected latest run, so `exit_alignment` remains `unknown` with `alignment_reason=no_exit_trigger_recorded`
- post-exit shadow tracking still needs the next closed trade

Cross-folder status:

- `docs/runtime_entrypoint/current_validation_status_2026-04-28.md`
- `docs/runtime_entrypoint/strategy_conservatism_review_2026-04-29.md`
