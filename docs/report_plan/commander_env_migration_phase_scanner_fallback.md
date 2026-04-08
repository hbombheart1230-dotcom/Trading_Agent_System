# Commander Env Migration: Scanner Fallback and Source Ownership

## Purpose
This phase moves scanner candidate source and fallback strictness ownership from
env to Commander-applied policy.

The goal is ownership migration only. Trading semantics and scanner fallback
behavior remain unchanged.

## Removed env keys
- `STRICT_KIWOOM_CANDIDATES_ONLY`
- `BLOCK_STATIC_FALLBACK_WHEN_KIWOOM_EMPTY`
- `CANDIDATE_SOURCE`
- `KIWOOM_CANDIDATE_LIVE_FETCH`
- `KIWOOM_CANDIDATE_INCLUDE_CHANGE_RATE`

## Canonical applied policy paths
- `applied_policy.scanner.source.type`
- `applied_policy.scanner.kiwoom.strict_only`
- `applied_policy.scanner.fallback.block_static_when_empty`
- `applied_policy.scanner.kiwoom.live_fetch`
- `applied_policy.scanner.kiwoom.include_change_rate`

## Baseline
Commander injects the runtime baseline through `applied_policy.scanner.*`.

- `scanner.source.type = "kiwoom"`
- `scanner.kiwoom.strict_only = true`
- `scanner.fallback.block_static_when_empty = true`
- `scanner.kiwoom.live_fetch = true`
- `scanner.kiwoom.include_change_rate = true`

Compatibility fallbacks may still read state/policy fields when canonical
Commander policy is not present, but env is no longer the owner.

## Fallback behavior
The fallback behavior is intentionally preserved.

1. Kiwoom results present:
   - use Kiwoom candidates
   - no strategist/static fallback
2. Kiwoom empty and `strict_only = true`:
   - no fallback
3. Kiwoom empty and `strict_only = false` and `block_static_when_empty = true`:
   - pure static fallback remains blocked
4. Kiwoom empty and `strict_only = false` and `block_static_when_empty = false`:
   - static fallback is allowed

## Observability
The scanner surface now makes Commander ownership explicit.

- `scanner_policy_source`
- `scanner_candidate_source`
- `scanner_fallback_mode`
- `scanner_strict_mode`
- `commander_applied_policy_summary.scanner_fields`
- `policy_sources.commander_owned_scanner_fields`

## Runtime semantics unchanged
- Commander owns configuration choice.
- Scanner consumes policy and does not own runtime fallback toggles.
- Candidate generation semantics are unchanged.
- This migration does not affect execution, monitor, strategist, approval, or guard authority.
