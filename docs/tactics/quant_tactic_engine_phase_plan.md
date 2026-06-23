# Quant Tactic Engine Phase Plan

Last updated: 2026-05-27

## Implementation Status

- 2026-05-20: Phase Q1 completed.
  - Added `libs/runtime/quant/contracts.py`.
  - Added `libs/runtime/quant/tactics.py`.
  - Added `libs/runtime/quant/__init__.py`.
  - Rewired strategist tactic normalization to the quant tactic catalog.
  - Rewired `libs/strategies/playbook_contracts.py` inventory to expose tactic
    IDs and legacy aliases.
  - Added `tests/test_quant_tactics.py`.
- 2026-05-20: Phase Q2 completed.
  - Added `libs/runtime/quant/factors.py`.
  - Added observation-only factor snapshots for scanner selected/ranking
    payloads.
  - Added observation-only monitor entry factor snapshot.
  - Added `tests/test_quant_factors.py`.
- 2026-05-20: Phase Q3 completed.
  - Added `libs/runtime/quant/memory.py`.
  - Added `libs/runtime/quant/scorecard.py`.
  - Added operator summary to quant memory packet adapter.
  - Added tactic scorecard and compact LLM scorecard helpers.
  - Added `tests/test_quant_memory_scorecard.py`.
- 2026-05-20: Phase Q4 completed.
  - Added `libs/runtime/quant/context.py`.
  - Injected `quant_context` into strategist LLM compact payload when runtime
    reports root is explicit or stage-specific context exists.
  - Added `quant_market_context` for Stage 1.
  - Added `selected_symbol_quant_snapshot` for Stage 2.
  - Added `hold_quant_context` for Stage 3.
  - Added `carry_quant_context` for Stage 4.
  - Added `tests/test_quant_context.py`.
- 2026-05-20: Phase Q5 completed.
  - Added `libs/runtime/quant/suitability.py`.
  - Added observation-only tactic suitability scoring for scanner candidates.
  - Exposed `tactic_suitability` in selected scanner output, ranking rows, and
    candidate selection reason payloads.
  - Preserved scanner ranking behavior; suitability is diagnostic only.
  - Added `tests/test_quant_suitability.py`.
- 2026-05-20: Phase Q6 completed.
  - Added `libs/runtime/quant/decision.py`.
  - Added monitor-side `entry_quant_decision` diagnostics for cost edge,
    volume confirmation, pullback maturity, tactic suitability, and commander
    override requirement.
  - Added monitor-side `exit_quant_decision` diagnostics for hard exit versus
    confirmation-required exit, early exit before expected hold window, and
    cost-floor exit blockers.
  - Exposed quant decisions in monitor output and entry/exit decision detail
    artifacts.
  - Preserved live behavior; decisions are diagnostic/observation-only.
  - Added `tests/test_quant_decision.py`.
- 2026-05-20: Phase Q7 Slice 1 completed.
  - Added `libs/reporting/quant_tactic_report.py`.
  - Added trade-report quant tactic surface and markdown lines.
  - Surfaced tactic ID, scanner tactic suitability, entry quant decision, exit
    quant decision, cost edge, hold-window mismatch, and factor snapshot in the
    full trade report.
  - Added compact quant tactic diagnostics to trade summary markdown.
  - Propagated quant decisions through `monitor_reason_human` and deterministic
    monitor snapshots.
  - Added `tests/test_quant_tactic_report.py`.
- 2026-05-20: Phase Q7 Slice 2 completed.
  - Extended operator summary trade enrichment with quant tactic fields.
  - Added `pattern_performance.quant` aggregations for tactic ID, tactic
    suitability, entry decision/blocker/cost edge, exit decision/confirmation,
    hold-window mismatch, and hard-exit state.
  - Added quant lines to daily/weekly/monthly Pattern Performance markdown.
  - Added operator summary regression coverage for quant diagnostic aggregation.
- 2026-05-20: Phase Q7 Slice 3 completed.
  - Extended `quant_memory_packet` with `pattern_performance.quant` rows.
  - Added `quant_memory_feedback` to quant scorecards and compact strategist
    LLM scorecard context.
  - Added feedback tags for entry blockers, exit decision quality, hold-window
    mismatch, and weak tactic suitability.
  - Preserved observation-only behavior.
- 2026-05-21: Phase Q7 residual strategist quant-context exposure completed.
  - Added `libs/reporting/strategist_quant_context_report.py`.
  - Added full-report `전략가 Quant Context 사용` section.
  - Preserved compact quant context usage fields in strategist refresh trace.
  - Added `tests/test_strategist_quant_context_report.py`.
  - Preserved observation-only behavior.
- 2026-05-24: Phase Q8 data truth gate started.
  - Q8 validation is blocked unless trade count, order/fill count, and realized
    PnL truth are reliable.
  - `ka10170` 당일매매일지 is the preferred realized trade result source when
    a single symbol row can be matched.
  - `ka10077` remains the detailed realized PnL fallback and ambiguity surface.
  - `kt00007`/`kt00009` remain the order/fill count reconciliation sources.
  - Broad Kiwoom account snapshots are archived under
    `data/logs/kiwoom_account_snapshots/YYYY-MM-DD/` at report-generation
    alignment time.
- 2026-05-24: Phase Q8 candidate shadow dataset started.
  - Added `libs/runtime/quant/shadow_candidates.py`.
  - Added `libs/reporting/quant_shadow_candidate_evaluation.py`.
  - Monitor now saves observation-only top-pick, runner-up evaluated, and
    runner-up skipped candidate rows under
    `data/logs/quant_shadow_candidates/YYYY-MM-DD/`.
  - Operator daily/weekly/monthly/symbol summaries now surface Q8 shadow
    candidate counts, roles, reasons, tactic IDs, suitability tiers, cost-floor
    states, and failure axes.
  - Operator summaries expose Q8 shadow candidate counts, but blocker counts
    alone are not promotion evidence.
  - Promotion review requires the Q8 Evaluation Contract:
    canonical dedupe, trusted same-day forward outcomes, and
    `evaluation_trust_gate.promotion_allowed=true`.
  - If a candidate is already enforced in live runtime, the summary must show
    `already_promoted_monitor_hard_gate` instead of recommending a duplicate
    promotion.
  - Added observation-only `opening_momentum_probe_shadow` so strong opening
    momentum opportunities can be evaluated without changing live buy behavior.
  - Added observation-only `opening_largecap_surge_shadow` for the 09:00-09:20
    largecap watchlist lane (`005930`, `000660`, `009150`). It records whether
    fixed largecap leaders were missed by the normal scanner/monitor path,
    including ranked watchlist rows that were not evaluated by monitor.
  - This does not change entry behavior. It creates a larger evaluation set for
    Q8 when actual trade count is too low.
  - Added `tests/test_quant_shadow_candidates.py` and
    `tests/test_quant_shadow_candidate_evaluation.py`.

Q7 alignment note:

- The original Q7 slice list below was implemented in a slightly different
  order to keep runtime risk low.
- Original Slice 1, trade report quant block: completed as Q7 Slice 1.
- Original Slice 3, weekly/operator summary: completed as Q7 Slice 2.
- Original Slice 4, structured memory feedback: completed as Q7 Slice 3.
- Original Slice 2, strategist LLM summary exposure: functionally covered by
  Q4 `quant_context` injection plus Q7 Slice 3 compact scorecard feedback,
  and completed in the 2026-05-21 residual patch with the full-report
  `전략가 Quant Context 사용` section.

## Phase Q8 - Validation Gate And Truth First

Goal: validate Q1-Q7 only on reliable samples.

Q8 is not a passive waiting phase. It is the validation layer that decides
which quant diagnostics are safe to promote from observation/shadow into live
behavior, and it must separate deterministic pre-entry guards from realized
PnL-dependent strategy conclusions.

### Q8 Promotion Classes

1. Deterministic pre-entry guards.
   - Examples: broker restriction, same-symbol position open, cost-edge fail,
     volume confirmation missing, and promoted weak-lane quality gates.
   - These fields are known before an order is sent.
   - `shadow_readiness` is enough to promote them when the shadow sample has
     adequate coverage.
2. Strategy allocation and lane weighting.
   - Examples: `vwap_reclaim_pullback` downweighting, breakout versus pullback
     preference, runner-up cascade quality.
   - Requires either actual closed-trade evidence or forward-labeled shadow
     outcomes.
3. Exit and hold behavior.
   - Examples: VWAP breakdown confirmation, `intraday_low_break` confirmation,
     long-horizon unlock.
   - Requires actual trade exits plus post-exit or forward-labeled evidence.

Q8 must not keep reporting "sample insufficient" when the relevant evidence
class has enough data. Low actual trade count is only a blocker for realized
PnL claims, not for deterministic pre-entry guards.

### Q8 Priority Order

1. Data truth and sample validity.
   - Use `ka10170` as the preferred same-day trade result source.
   - Use `ka10077` as detailed realized PnL fallback.
   - Use `kt00007`/`kt00009` for broker order/fill count alignment.
   - Mark Q8 samples invalid when broker/local counts or report artifacts are
     inconsistent.
2. Q8 evaluation surface.
   - Daily/weekly reports must show tactic state, sample count, invalid sample
     count, win/loss, average PnL, and observation/shadow/live mode.
   - Invalid samples must include compact examples with trade ID, symbol, and
     invalid reason so reporting integrity problems can be fixed before tactic
     promotion.
3. Candidate shadow dataset.
   - Store blocked top candidates, runner-up candidates, and cost-edge failed
     candidates as shadow observations so low real-trade count does not stall
     evaluation.
   - Runtime storage path:
     `data/logs/quant_shadow_candidates/YYYY-MM-DD/`.
   - Current captured roles: `top_pick`, `runner_up_evaluated`,
     `runner_up_skipped`, `opening_largecap_watchlist`.
   - Operator summary exposes shadow candidate counts by role, reason, tactic
     ID, tactic suitability, cost-floor state, and primary failure axis.
   - Operator summary also exposes `promotion_candidate` and
     `shadow_readiness` separately from live-trade readiness.
   - Shadow-only promotion is allowed for pre-entry filters whose outcome is
     fully observable before order placement. Cost-edge is the first such
     candidate: it can be promoted from a sufficient shadow sample even when
     actual closed-trade performance samples are still insufficient.
   - Opening momentum probe shadow is tracked separately from normal
     `would_enter`, so Q8 can compare missed opening momentum against late
     pullback entries without mixing policies.
   - Opening largecap surge shadow is tracked separately again so 09:00-09:20
     moves in `005930`, `000660`, and `009150` can be reviewed without opening
     live orders or weakening the normal scanner rank.
   - Shadow candidates must carry a baseline minute price when available, and
     reporting must attach forward checkpoint outcomes when later minute data
     exists. Without forward outcomes, shadow can validate deterministic guards
     but cannot validate strategy expectancy.
   - Current storage behavior effect: `observation_only`; summary forward
     labeling behavior effect: `evaluation_only`.
4. Behavior promotion.
   - Promote one behavior at a time only after enough valid samples exist for
     the relevant evidence type.
   - `live_trade_readiness` is required for claims about realized win rate,
     average PnL, exits, and holding windows.
   - `shadow_readiness` is enough for pre-entry guard promotion when the guard
     only depends on fields known before a BUY order.
   - Current first candidates are cost-edge filter, runner-up independent
     suitability, and entry guard hard veto.

### Q8 Hard Rule

No tactic conclusion should be promoted from a day where trade reports, broker
orders, or realized PnL truth disagree. Such samples are evidence for reporting
integrity fixes, not tactic quality.

## Purpose

This document records the implementation phases for the quant tactic engine.
The priority is modularity, extensibility, and operational safety.

The standing rule is:

- keep the current commander, strategist, scanner, monitor, execution,
  reporting, and memory flow
- add new quant/tactic modules beside the existing flow
- avoid growing already large files when a new module can own the concept
- do not refactor unrelated code only for cleanliness
- when a touched path naturally needs separation, extract that logic into a
  module instead of embedding more strategy logic in the caller

## Phase Q1 - Quant Tactic Contracts And Catalog

Goal: freeze the tactic language in code.

### Slice 1: Contracts

Target:

- `libs/runtime/quant/contracts.py`

Content:

- tactic ID contract
- factor snapshot contract
- tactic scorecard contract
- quant decision contract
- compatibility fields for existing `tactical_strategy` and
  `tactical_subtype`

### Slice 2: Tactic Catalog

Target:

- `libs/runtime/quant/tactics.py`

Content:

- tactic ID list
- playbook to tactic candidate mapping
- `vwap_reclaim_pullback` subtype compatibility
- `leader_vwap_reclaim_pullback` as alias only, not a formal tactic ID

Expected effort: 1 turn.

## Phase Q2 - Factor Snapshot

Goal: create a shared deterministic snapshot that strategist, scanner,
monitor, reporter, and memory can all consume.

### Slice 1: Factor Engine

Target:

- `libs/runtime/quant/factors.py`

Content:

- VWAP position
- VWAP reclaim state
- relative volume
- pullback maturity
- breakout expansion
- cost floor state
- human chart score fields
- theme/news confirmation placeholders
- liquidity/spread placeholders where available

### Slice 2: Thin Runtime Wiring

Target:

- scanner and monitor artifact builders only where needed

Content:

- attach factor snapshots to artifacts
- no behavior change
- no ranking replacement
- no entry or exit rule change

Expected effort: 1-2 turns.

## Phase Q3 - Memory And Scorecard Adapter

Goal: convert existing memory and reports into compact scorecards.

### Slice 1: Memory Adapter

Target:

- `libs/runtime/quant/memory.py`

Content:

- weekly operator summary adapter
- symbol memory adapter
- post-exit shadow adapter
- broker rejection memory adapter
- report diagnosis tag adapter

### Slice 2: Scorecard

Target:

- `libs/runtime/quant/scorecard.py`

Content:

- tactic win rate
- average return
- hold-time buckets
- tactic plus exit reason performance
- cost floor met/not-met split
- small-sample safe scoring
- loss cluster detection

Expected effort: 1-2 turns.

## Phase Q4 - Strategist LLM Stage 1-4 Injection

Goal: keep all strategist LLM calls, but replace repeated bulky context with
compact quant context.

### Slice 1: Stage 1 Market Frame

Add:

- `quant_market_context`
- session regime
- tactic scorecard
- viable tactic families
- downgraded or banned clusters

Remove where possible:

- repeated raw memory prose
- repeated long report text
- statistics that the quant module can summarize deterministically

### Slice 2: Stage 2 Selected Symbol Tactical Review

Add:

- `selected_symbol_quant_snapshot`
- selected symbol tactic fit
- runner-up tactic fit
- cost edge
- exact symbol theme/news confirmation
- pullback maturity or breakout expansion state

Target behavior visibility:

- runner-up cascade should not look like automatic entry
- runner-up should show independent tactic fit and cost edge

### Slice 3: Stage 3 Stale Intraday Hold Review

Add:

- `hold_quant_context`
- elapsed hold versus expected tactic hold window
- tactic still valid or invalidated
- hard failure versus ordinary noise
- post-entry factor decay

Target behavior visibility:

- repeated early `intraday_low_break` losses should become diagnosable by
  tactic and hold-window mismatch.

### Slice 4: Stage 4 End-Of-Day Carry Review

Add:

- `carry_quant_context`
- long-horizon eligibility
- gap risk
- theme/news continuation
- closing liquidity state
- post-exit shadow evidence

Rule:

- keep long-horizon behavior observability-only until evidence supports unlock.

Expected effort: 2-3 turns.

## Phase Q5 - Scanner Additive Tactic Suitability

Goal: make scanner ranking explain whether a candidate is actually tactic-fit
or merely liquid/high rank.

### Slice 1: Candidate Suitability

Add:

- candidate tactic suitability score
- tactic evidence reasons
- missing factor reasons

### Slice 2: Ranking Explanation

Add to artifacts/reports:

- liquidity/rank contribution
- theme/news contribution
- tactic fit contribution
- cost edge contribution

### Slice 3: Runner-Up Cascade Visibility

Add:

- runner-up independent fit fields
- cascade reason quality
- whether cascade is only advisory or behavior-affecting

Initial rule:

- no hard ranking replacement
- no symbol-name penalty
- additive or observation-only first

Expected effort: 1-2 turns.

## Phase Q6 - Monitor Observation Decision

Goal: attach tactic-aware entry and exit decisions without immediately changing
live behavior.

### Slice 1: Entry Quant Decision

Add:

- entry suitability
- entry blockers by tactic
- cost edge
- expected hold window
- commander override reason field

### Slice 2: Exit Quant Decision

Add:

- hard exit versus confirmation-required exit
- tactic invalidation state
- early exit warning
- expected hold window mismatch

### Slice 3: Hold Window Tracking

Add:

- expected hold min/target/max by tactic
- actual hold comparison
- early-exit loss cluster fields

Initial rule:

- observation-only except already agreed hard safety guards

Expected effort: 2 turns.

## Phase Q7 - Report And Memory Feedback

Goal: make tactical diagnosis visible enough for operator review and future
memory use.

### Slice 1: Trade Report Quant Block

Add:

- tactic ID
- subtype
- factor snapshot
- LLM decision versus quant decision
- cost floor state
- expected hold versus actual hold
- exit quality
- post-exit shadow result
- memory feedback tags

### Slice 2: Strategist LLM Summary

Add:

- quant context used by each stage
- selected tactic score
- rejected tactic reasons
- memory scorecard excerpt

### Slice 3: Weekly Summary

Add:

- tactic performance table
- tactic plus exit reason table
- hold-time buckets by tactic
- cost-floor performance
- human chart score buckets
- long-horizon cap count and reason

### Slice 4: Structured Memory Feedback

Add:

- compact improvement tags
- tactic failure tags
- symbol/tactic interaction tags
- broker rejection tags

Expected effort: 2 turns.

## Phase Q8 - Q1-Q7 Validation

Goal: validate Q1-Q7 in the live/runtime/reporting flow before any additional
behavior change.

Validation scope:

- quant tactic contracts and aliases remain stable
- factor snapshots are attached to scanner and monitor artifacts
- quant memory and scorecard adapters load without breaking strategist context
- strategist LLM stage 1-4 receives compact quant context
- scanner tactic suitability is visible and remains additive/diagnostic
- monitor entry/exit quant decisions are visible with the expected
  `behavior_effect`
- trade report, summary, and operator summary expose quant diagnostics
- live restart includes Q1-Q7 code paths and logs the expected artifacts

2026-05-22 evaluation surface:

- Added operator-summary `quant_tactic_evaluation` diagnostics for Q8.
- Daily/period/symbol operator summary JSON and Pattern Performance markdown
  now expose sample sufficiency, missing required quant fields, and tactic ID
  mismatch counts before any behavior promotion review.
- The summary status is evaluation-only:
  - `hold_sample_insufficient`
  - `hold_field_gaps`
  - `hold_tactic_id_mismatch`
  - `review_sample_building`
  - `promotion_review_ready`

Rules:

- Q8 may promote deterministic pre-entry guards only when the Q8 Evaluation
  Contract passes: trusted same-day forward outcomes, canonical dedupe, and
  `evaluation_trust_gate.promotion_allowed=true`.
- Q8 may promote lane downweighting when actual trade evidence and/or
  forward-labeled shadow outcomes identify one clear loss cluster.
- Q8 must not promote long-horizon unlock without post-exit/forward outcome
  evidence.
- use focused regression plus live artifact inspection
- document any mismatch before deciding the next behavior patch

Expected effort: 1-2 turns, depending on live artifact availability.

Behavior promotion candidates:

- cost floor hard veto: promoted
- repeated weak `vwap_reclaim_pullback` quality gate: promoted after W22/W23
  loss cluster
- runner-up cascade restriction: pending forward-labeled shadow comparison
- early `intraday_low_break` confirmation: active for soft exits, keep
  monitoring
- long-horizon unlock rules
- news/theme confirmation strength gate

## Total Expected Effort

Minimum implementation:

- Q1-Q3: 3-5 turns
- Q4-Q7: 7-9 turns
- Q8 validation included: 9-11 turns

Likely operational estimate:

- around 10 turns for a useful observation-first system
- 1-2 additional turns if touched large files need extraction to avoid
  embedding more logic

## Execution Order

1. Complete Q1-Q3 first.
2. Inject quant context into strategist LLM calls in Q4.
3. Add scanner and monitor observability in Q5-Q6.
4. Add report and memory feedback in Q7.
5. Validate Q1-Q7 in Q8.
6. Promote live behavior only after Q8 validation identifies one clear target
   cluster and rollback trigger.

## Modularity Rule

When implementing, prefer:

- new quant module owns new concept
- existing runtime file calls the module
- existing behavior remains unless a later, explicit behavior patch promotes it
- tests cover module output and thin integration

Avoid:

- embedding new scoring logic directly in `strategist_node.py`
- embedding new scoring logic directly in `scanner_node.py`
- embedding tactic decision logic directly in monitor signal files when it can
  live under `libs/runtime/quant`
- expanding report mega-files with reusable quant logic
