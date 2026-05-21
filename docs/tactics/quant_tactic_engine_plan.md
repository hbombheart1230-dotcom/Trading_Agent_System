# Quant Tactic Engine Plan

Last updated: 2026-05-20

## Purpose

This document freezes the next tactical direction before code changes. The goal
is not to replace the live architecture. The goal is to add a modular
quant-style tactic layer that the current commander, strategist, scanner,
monitor, reporter, and memory systems can consume.

The current live flow remains:

`Commander -> Strategist LLM stage 1-4 -> Scanner -> Monitor -> Execution -> Report/Memory`

The patch direction is:

- keep the current flow and ownership boundaries
- add deterministic tactic/factor/scorecard modules beside the existing flow
- feed compact quant context into LLM calls instead of large repeated memory
  text
- make scanner and monitor consume tactic suitability as additive or
  observation-only evidence first
- validate Q1-Q7 diagnostics in live artifacts before promoting any additional
  behavior gate

## Current Tactical State

The old broad label `leader_vwap_reclaim_pullback` has already been split at
the runtime contract level:

- `leader_vwap_reclaim_pullback` is normalized to `vwap_reclaim_pullback`
- `tactical_subtype` exists for pullback evidence
- `theme_leader_pullback` is normalized to `theme_confirmed_pullback`
- `liquidity_leader_trend` is normalized to `liquidity_confirmed_pullback`

Current pullback subtypes:

- `theme_confirmed_pullback`
- `market_representative_pullback`
- `liquidity_confirmed_pullback`
- `vwap_reclaim_setup`
- `weak_fallback_pullback`

This means the first split is done. The remaining problem is that the split is
still attached to the strategist output shape, not a reusable tactic engine.
The next patch should not reintroduce `leader_vwap_reclaim_pullback`. It should
move toward first-class tactic IDs, factor snapshots, and empirical scorecards.

## Current Options

### Strategist

Current high-level strategist options:

- playbook: `breakout`, `pullback`, `reversal`, `defensive`
- tactical strategy:
  - `opening_gap_momentum`
  - `opening_range_breakout`
  - `vwap_reclaim_pullback`
  - `volume_breakout`
  - `reversal_reclaim`
  - `cost_aware_scalp`
  - `defensive_observe`
- pullback subtype:
  - `theme_confirmed_pullback`
  - `market_representative_pullback`
  - `liquidity_confirmed_pullback`
  - `vwap_reclaim_setup`
  - `weak_fallback_pullback`
  - `none`
- horizon: `scalp`, `intraday`, `overnight_probe`, `1_2day_swing`
- aggressiveness: `low`, `medium`, `high`
- risk tone: `conservative`, `normal`, `aggressive`
- monitor guidance: `hold_through_noise`, `defensive_exit`,
  `quick_take_profit`

### Scanner

Scanner currently consumes strategist playbook and guidance, then applies
ranking bias. Chart fit exists but is mostly advisory. Candidate cascade exists
for runner-up review, but it must not become automatic entry when the top
candidate is blocked by poor maturity, missing volume confirmation, or poor
cost edge.

Scanner should receive tactic suitability as an additive score first:

- no symbol-name penalty
- no hard replacement of scanner rank in the first patch
- rank should be explained as liquidity/rank plus tactic fit, not liquidity
  alone

### Monitor

Monitor currently owns entry and exit timing. It should remain the timing
owner. The quant tactic layer should provide:

- expected hold window by tactic
- entry invalidation conditions by tactic
- exit confirmation requirements by tactic
- cost and liquidity edge at entry
- whether the current move is a tactic failure or ordinary noise

Initial monitor integration should be observation-only except for already
agreed hard safety guards.

## Proposed Tactic Portfolio

The tactic layer should use explicit tactic IDs. These are not fixed strategies
that force all trading into one setup. They are classification and evaluation
units so win rate, expected value, hold time, and failure reasons can be
measured consistently.

Initial tactic IDs:

- `trend_continuation`
- `opening_gap_momentum`
- `opening_range_breakout`
- `volume_breakout`
- `vwap_reclaim_pullback`
- `lower_vwap_rebound_probe`
- `mean_reversion_probe`
- `event_theme_momentum`
- `cost_aware_scalp`
- `defensive_observe`
- `inverse_hedge_reclaim`

Pullback subtype should remain as supporting evidence under
`vwap_reclaim_pullback`, not as a replacement for tactic ID.

## Proposed Modules

Add new modules instead of expanding already large runtime files:

- `libs/runtime/quant/contracts.py`
  - tactic IDs
  - factor snapshot schema
  - scorecard schema
  - decision output schema
- `libs/runtime/quant/tactics.py`
  - tactic definitions
  - playbook to tactic family mapping
  - subtype compatibility
- `libs/runtime/quant/factors.py`
  - market regime factors
  - VWAP distance/slope factors
  - relative volume and liquidity factors
  - pullback depth and maturity factors
  - breakout expansion factors
  - cost floor and spread/liquidity factors
  - news/theme sentiment factors
  - human chart score factors
- `libs/runtime/quant/memory.py`
  - weekly operator summary adapter
  - symbol memory adapter
  - post-exit shadow tracking adapter
  - recent tactic performance adapter
- `libs/runtime/quant/scorecard.py`
  - tactic performance aggregation
  - Bayesian or shrinkage-safe small sample score
  - loss cluster detection
  - cost floor performance split
- `libs/runtime/quant/decision.py`
  - entry suitability
  - exit confirmation need
  - horizon eligibility
  - commander override explanation payload
- `libs/reporting/quant_tactic_report.py`
  - report summary section
  - LLM report compact context
  - operator-facing diagnosis table

## LLM Stage Changes

### Stage 1: Market Strategy Frame

Keep the call. Strengthen it with compact `quant_market_context`:

- market regime and breadth
- tactic scorecard for the current week/day
- cost-floor success/failure split
- viable tactic families for the current session
- banned or downgraded tactic clusters

Remove from the prompt where possible:

- repeated raw memory text
- repeated long report prose
- deterministic statistics that the quant module can summarize

### Stage 2: Selected Symbol Tactical Review

Keep the call. Strengthen it with `selected_symbol_quant_snapshot`:

- selected symbol tactic fit
- runner-up tactic fit
- cost edge
- theme/news confirmation for that exact symbol
- pullback maturity or breakout expansion state
- whether the selected symbol is merely liquid or actually fits the tactic

The key behavior target is to stop automatic runner-up entry when the top
candidate is blocked. Runner-up entry should require independent tactic fit,
cost edge, and monitor readiness.

### Stage 3: Stale Intraday Hold Review

Keep the call. Strengthen it with `hold_quant_context`:

- elapsed hold time versus tactic expected hold window
- whether the original tactic is still valid
- whether exit signal is hard failure or ordinary noise
- post-entry factor decay
- cost floor and profit-protection state

The target is to reduce repeated early `intraday_low_break` losses when the
move has not reached a true hard-stop equivalent.

### Stage 4: End-of-Day Carry Review

Keep the call. Strengthen it with `carry_quant_context`:

- long-horizon eligibility
- gap risk
- closing auction and liquidity state
- theme/news continuation state
- post-exit shadow evidence
- broker/order uncertainty

Long-horizon behavior remains observability-only until a defined subset shows
that longer holding improves results without violating hard stops.

## Report Changes

Trade report summary should add a quant/tactic block:

- tactic ID
- subtype when relevant
- factor snapshot at entry
- LLM decision versus quant decision
- cost floor state
- expected hold window versus actual hold
- exit reason quality
- post-exit shadow result
- exact memory feedback that should be stored

Weekly summary should add:

- tactic performance table
- tactic plus exit reason table
- hold-time buckets by tactic
- cost-floor met/not-met performance
- human chart score buckets
- long-horizon cap count and reason

## Memory Usage Changes

Existing memory should not be discarded. It should be converted into compact
scorecards:

- operator weekly summary -> tactic scorecard
- symbol memory -> symbol/tactic interaction summary
- post-exit shadow -> early-exit and hold-window evidence
- report LLM diagnosis -> structured improvement tags
- broker rejection history -> universe exclusion or caution memory

The first patch should only read and summarize memory. Behavior changes should
come after the report proves which memory fields are reliable.

## Patch Order

1. Add this document and keep it updated.
2. Add `libs/runtime/quant/contracts.py` and `tactics.py`.
3. Add `factors.py` as observation-only factor snapshots.
4. Add `memory.py` and `scorecard.py` adapters for existing reports/memory.
5. Inject compact quant context into strategist LLM stage 1-4.
6. Add scanner additive tactic suitability.
7. Add monitor observation-only quant decision payload.
8. Add report sections.
9. Run Q8 validation for Q1-Q7:
   - verify tactic contracts and aliases
   - verify factor snapshots and tactic suitability in scanner/monitor output
   - verify strategist quant context stage 1-4
   - verify quant decisions in trade reports and operator summaries
   - verify live restart includes the Q1-Q7 code paths
10. Promote only one proven behavior gate after Q8 validation, with a rollback
    trigger and focused tests.

## Non-Goals

- Do not replace commander, strategist, scanner, monitor, execution, or report
  ownership boundaries.
- Do not force a single tactic.
- Do not penalize specific symbols by name.
- Do not make long-horizon behavior live before post-exit evidence supports it.
- Do not expand large files with more embedded strategy logic when a new module
  can own the concept.
