# Strategy Horizon Feedback

This folder documents the strategy-horizon and post-exit feedback loop.

The goal is to separate three things that are currently easy to mix together:

- strategist proposal: what kind of trade the strategist thinks this could be
- commander horizon policy: what holding horizon the runtime is allowed to operate under
- monitor action: why the position was actually exited
- post-exit evidence: what would have happened if the system had not sold there

Current design document:

- `strategy_horizon_and_post_exit_shadow_tracking_2026-04-25.md`

## Scope

This folder owns:

- strategy horizon labels such as `scalp`, `intraday`, `overnight_probe`, and `1_2day_swing`
- Commander-owned operational horizon policy derived from strategist proposal, runtime phase, memory, and live-validation constraints
- monitor exit-vs-strategy-intent logging
- post-exit shadow tracking after a closed trade
- deterministic memory fields derived from post-exit price behavior
- rollout rules for live validation before changing hold behavior

This folder does not own:

- final symbol selection; that remains Scanner responsibility
- broker truth; see `docs/kiwoom_truth`
- general runtime memory contracts; see `docs/runtime_memory`
- strategist output explanation contract; see `docs/strategist_output`

## Operating Rule

The first implementation should be observability-only.

Strategist may propose a horizon, but Commander owns the operational horizon that Monitor and Reporter should consume. Monitor may continue to exit as it does today, but every exit should record whether it aligned with the Commander horizon policy and should retain the original strategist proposal for comparison. Actual hold-extension behavior should only be enabled after enough post-exit shadow data has been collected.

## Current Validation Status

As of `2026-04-28 12:38 KST`, the latest live monitor artifact verifies the observability-only path:

- `horizon_owner=commander`
- `strategy_horizon=intraday`
- `observability_only=true`
- current action remains `NOOP` / `WAIT`
- no hold-extension behavior change is enabled

Current limitation:

- no real exit happened in the inspected latest run, so `exit_alignment` remains `unknown` with `alignment_reason=no_exit_trigger_recorded`
- post-exit shadow tracking still needs the next closed trade

Cross-folder status:

- `docs/runtime_entrypoint/current_validation_status_2026-04-28.md`
