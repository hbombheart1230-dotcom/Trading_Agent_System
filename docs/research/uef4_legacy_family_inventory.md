# UEF-4A -- Legacy Family Inventory & Canonical Mapping

**Status: COMPLETE (UEF-4A research/inventory deliverable, revised under
FIX1).** Assembled from direct source-code inspection (primary authority:
real legacy source code > real artifact > documented source constant >
this document > any test). This is research/inventory only -- no adapter
is implemented here, no legacy file is modified, no frozen UEF-1..UEF-3C
file is touched. See `docs/research/uef_freeze_manifest.md` (11/11 MATCH,
verified before and after this work, and again before/after FIX1).

**FIX1** closed an independent-audit HIGH finding: `libs/research/**`
contains six additional offline research evaluators/pipelines that generate
genuine primary forward-return evidence and were omitted from the original
inventory. Sections 5.10-5.16 and the tables below are new; every
classification confirmed by the original independent audit
(Q8/Q9/Q10-Semiconductor/Q10-Index/Q11/Q12/Q13-14/Q15/Q16-17-scope/Q18/
Opening-Shadow/Opening-Alpha-attribution/Controlled-Lane-ambiguity/
Samsung-Hynix-derived-view/Alpha-Board-derived-view/Q10-Index-collector) is
preserved unchanged below -- none of that is reopened.

**FIX2 (this revision)** corrects a HIGH finding in FIX1's own output:
FIX1 incorrectly claimed the new `dual_cost_variant_forward_adapter` family
(`post_reclaim_alpha`+`structural_alpha`+`structural_alpha_batch2`+
`alpha_competition`+`existing_evidence_mining`) was LOSSLESS=YES and ready
for UEF-4B, by proposing to reconstruct its source-provided dual net figures
as two `CostPolicy`-derived `COMPUTED` `NetReturnRecord`s. Re-reading the
actual frozen contract (`contracts.py`'s `NetReturnComputationStatus`
docstring; `engine.py::calculate_net_return`'s explicit
`_require(cost_policy is None, ...)` guard for `NET_OR_COST_INCLUDED`
sources, `engine.py:186-188`) confirms that reconstruction is not valid --
it would reinterpret an already-net `SOURCE_PROVIDED` figure as if it were
`GROSS_ONLY`/`COMPUTED`, which the frozen engine structurally rejects
(double-counting). This revision downgrades that family's CANONICAL/LOSSLESS
MAPPING to **UNKNOWN** and its UEF-4B status to **BLOCKED**, while
preserving PRIMARY EVIDENCE=YES (evidence known, canonicalization blocked --
not discarded, not demoted to consumer/derived-view). The FIX1
inventory-completeness result (39 sources, 20 primary, 19 derived/consumer,
0 additional omitted families) is unchanged and not reopened. No frozen
UEF-1..UEF-3C file is modified by this correction.

## 1. Executive Summary

This inventory examined **39 distinct legacy source groups** (26 original
+ 13 added under FIX1) spanning Q8 through Q18, "Opening"/rank-1 scanner
provenance, adjacent baseline/report/policy modules, and the
`libs/research/**` offline-evaluator tree. The central finding confirms
this task's own premise: **Q numbers are naming/provenance, not
architecture.** Real semantic families collapse to a much smaller set than
the Q-number (or directory-name) count suggests --

- **6 real forward-measurement families** already have a complete,
  frozen, re-verified canonical mapping (UEF-2A's own 14-profile registry,
  `canonical/forward/profiles.py`): Q9, Q10 Semiconductor, Q10 Index, Q11,
  Q12, Opening Shadow. **Q12 Calc1 is not independent evidence -- it is a
  direct reuse of the Q10 Semiconductor engine** (confirmed by Python
  free-variable resolution in the frozen profile's own docstring), so it
  absorbs into that family rather than requiring its own adapter.
- **FIX1 finding, mapping status corrected under FIX2: a 7th real
  evidence-generating source family exists in `libs/research/**`**,
  spanning FIVE directories that all share (by direct import, not
  coincidence) the exact same checkpoint/cost engine
  (`post_reclaim_alpha/evaluator.py::evaluate_episodes`): `post_reclaim_alpha`
  (the base), `structural_alpha` + `structural_alpha_batch2` (one family,
  two hypothesis batches), `alpha_competition`, and `existing_evidence_mining`.
  This engine computes a shape none of the original 6 adapter families
  support: ONE gross figure feeding TWO independently-named net-of-cost
  figures (`live_net_return_pct`, `mock_net_return_pct`) plus a shared
  MFE/MAE excursion pair. **PRIMARY EVIDENCE = YES for all five
  directories. CANONICAL MAPPING = UNKNOWN, UEF-4B = BLOCKED** (FIX2
  correction) -- FIX1 incorrectly claimed this was losslessly
  reconstructable as two `CostPolicy`-derived `COMPUTED` `NetReturnRecord`s;
  the frozen `calculate_net_return()` engine explicitly rejects supplying a
  `cost_policy` against a `NET_OR_COST_INCLUDED`/`SOURCE_PROVIDED` source
  (double-counting), so that reconstruction is not valid under the current
  frozen contract. See Section 6 for the full corrected reasoning; the
  evidence itself is not discarded or demoted, only its canonicalization is
  blocked pending a future frozen-core-compatible resolution.
- **20 of the 39 groups own genuine PRIMARY evidence** (14 original + 6
  added under FIX1); the other 19 are DERIVED VIEWS/consumers/diagnostics
  that must never be double-counted as independent evaluation samples.
- **One family is explicitly BLOCKED pending resolution, not silently
  mapped**: `rank1_feature_mart`'s `outcomes.py` (extended multi-day
  D+1..D+5 horizons layered on a single-cost-variant net figure) does not
  cleanly match any of the 6 original families or the new 7th family, and
  this document could not fully confirm its exact field shape from source
  alone. LOSSLESS = UNKNOWN -> blocked from UEF-4B per this document's own
  policy (Section 15), not forced into a fit.
- **Two genuinely NEW evidence-generating mechanisms** were found outside
  the already-canonical set: Controlled Mock Lanes and the Opening Rank-1
  Controlled Probe, both of which submit real orders through the live
  execution path against a mock broker and record real (mock) fill
  outcomes. These are flagged AMBIGUOUS -- NEEDS DECISION (Table D), not
  silently folded in or silently excluded. (Unchanged from the original
  audit-confirmed finding.)
- **Q8, Q13/Q14, Q15, Q18 are consumers/policy/diagnostic layers with no
  primary evidence of their own** -- exactly the "report/diagnostic/policy
  accidentally promoted into a strategy lane" failure mode this task warns
  against. None needs an adapter. (Unchanged, audit-confirmed.)
- **Q16/Q17 were the one real surprise in the original pass**: they DO
  generate genuine primary forward-return evidence (via the same engine as
  Q10 Semiconductor), which contradicted this task's own "likely pure
  consumer" starting hypothesis. That evidence measures the
  REJECTED/cost-filtered branch of the candidate funnel, serving a
  defensive retain/rollback policy decision -- not an alpha lane. It
  remains explicitly recommended OUT of UEF-4B's alpha-fair-comparison
  adapter scope for that reason, not because it lacks real evidence.
  (Unchanged, audit-confirmed.)
- **FIX1's own surprise is the mirror image of Q16/Q17**: `existing_evidence_mining`
  and `alpha_competition` are OFFLINE, RESEARCH-ONLY, NEVER production-wired
  -- yet both own genuine primary evidence and are correctly inventoried as
  such. Per this task's own boundary (Section 16 of the FIX1 request):
  offline/research-only is a PRODUCTION-WIRING question, not a
  PRIMARY-EVIDENCE question; the two are independent dimensions and this
  document does not conflate them.
- **The "Opening Alpha" reporting-attribution question has a concrete,
  code-confirmed answer** (Section 8): no dedicated Opening Alpha strategy
  code exists; candidate selection is 100% the generic scanner's rank-1
  output. But execution/eligibility logic (the Controlled Probe gate) IS
  real and distinct. The actual source of attribution confusion is that
  (at least) four different layers all label their output "Opening Alpha"
  while covering different subsets of the same underlying rank-1 stream.
  (Unchanged, audit-confirmed.)

All 6 original already-canonically-mapped families carry MAPPING
CONFIDENCE = HIGH and remain APPROVED for UEF-4B. Two families are held at
genuine mapping uncertainty and explicitly **BLOCKED** rather than
force-fit, neither discarded nor demoted -- the new 7th
(`post_reclaim_alpha`-engine / dual-cost-source family, CANONICAL/LOSSLESS
MAPPING=UNKNOWN per the FIX2 correction) and `rank1_feature_mart/outcomes.py`
(LOSSLESS=UNKNOWN, unchanged from FIX1) -- see Section 6 for both.

## 2. Inventory Methodology

- Primary authority order (unchanged from every prior UEF phase): real legacy
  source code > real artifact > documented source constant > this document >
  any test.
- The single most valuable existing evidence source is UEF-2A's own frozen
  `libs/reporting/evaluation/canonical/forward/profiles.py`, which already
  re-verified, with file:line citations, the exact forward-measurement
  semantics of 14 real checkpoint calculators spanning Q9, Q10 Semiconductor
  (3 calculators), Q10 Index (3 calculators), Q11, Q12 (3 calculators), and
  Opening Shadow (3 calculators). This document treats that registry as
  authoritative for those 14 and does not re-derive what it already settled;
  it ADDS the sample-unit/identity/missing-semantics detail UEF-2A's own
  scope (forward-measurement only) did not need to settle.
- Everything NOT already covered by the 14-profile registry (Q8, Q13-Q18,
  baselines, "Opening Alpha" attribution, opportunity/shadow engines beyond
  Q11, controlled probes/mock lanes) was freshly inspected for this document.
- No adapter, legacy file, or frozen UEF file was modified. This is read-only
  research.

## 3. Complete Source Inventory

Full per-family detail lives in Section 5 (the mandatory mapping table);
Table A below is the flat inventory list. 39 source groups were classified
(26 original + 13 added under FIX1); see Section 1 for the headline
breakdown and Sections 5/8 for evidence.

## 4. Semantic Family Normalization

**Core architectural rule (per this task's own mandate): Q numbers are
legacy naming/provenance only, never architecture.** The canonical core
(UEF-1..UEF-3C) already describes exactly five reusable concepts a legacy
family maps into -- `EventOrigin`/forward-observation profile (UEF-2A),
forward engine (UEF-2B), cost/metric contract (UEF-3A), cost/metric engine
(UEF-3B), aggregation (UEF-3C) -- plus canonical identity (UEF-1). No new Q
object, no new lane, is created by this document.

Real semantic families found (normalized; a "family" = one real forward-
measurement/evidence-generating engine, regardless of how many Q numbers or
report labels point at it):

1. **Q9 Horizon/Exit** (`strategy_horizon_feedback.py`) -- 1 family, 1 profile.
2. **Q10 Semiconductor** (Samsung/Hynix baseline forward engine) -- 1 family,
   3 calculators (Calc A/B/C) sharing one engine, differing only in horizon
   window and checkpoint timing -- NOT 3 separate families.
3. **Q10 Index** (Samsung/Hynix index reaction + shadow comparison) -- 1
   family, 3 calculators (Calc F/G/H); F/G are the same collector-governed
   checkpoint mechanism at different fixed clocks, H is a directional
   shadow layer consuming F/G's own candle series. See Section 8 (Special
   Attention -- Q10) for whether F/G/H should be 1 or 2 adapter families.
4. **Q11 Opportunity Engine** (`opportunity_engine/simulator.py`) -- 1 family.
5. **Q12 BTC-Woori** (`baseline_btc_woori_tech/`) -- 1 family, 3 calculators;
   Calc1 is a direct, unmodified REUSE of family #2's own engine (Python
   free-variable resolution -- confirmed in profiles.py docstring), so Calc1
   is not independent evidence semantics, only a second PROGRAM invoking the
   same engine on different underlying candidates.
6. **Opening Shadow** (`opening_rank1_shadow/latent_forward.py` +
   `opening_rank1_longitudinal/delayed_outcomes.py`) -- 1 family, 3
   calculators (1A/1B/1C).
7. **Q8** -- see Section 8; likely a shared contract/constants module plus
   several review/decision-table utilities, not a forward-evidence family.
8. **Q13/Q14/Q15/Q16/Q17/Q18** -- see Section 8; hypothesized downstream
   consumers/policy-review layers, verified per-family below.
9. Baselines, opportunity/shadow adjuncts, Opening-Alpha attribution,
   controlled probes/mock lanes -- see Section 8.

**FIX1 Addendum -- additional families found in `libs/research/**`** (full
per-family detail in Section 5.10-5.16; these are genuinely new engines, not
Q9-18/Opening restated):

10. **`post_reclaim_alpha` engine family** (`post_reclaim_alpha`,
    `structural_alpha`, `structural_alpha_batch2`, `alpha_competition`,
    `existing_evidence_mining` -- 5 directories, 1 shared checkpoint/cost
    engine) -- 1 evidence family, dual-cost-variant shape, PRIMARY
    EVIDENCE=YES, CANONICAL MAPPING=UNKNOWN, BLOCKED from UEF-4B (FIX2
    correction -- see "Blocked Adapter Family Candidate," Section 6).
11. **`rank1_feature_mart`** -- split family: `outcomes.py`/`builder.py`/
    `pipeline.py` are a genuinely distinct, self-computing ALPHA_PROGRAM
    (extended multi-day horizons, upstream-fallback mechanic, BLOCKED
    pending lossless-mapping resolution -- Section 9 Table D);
    `activation_shadow.py`/`prospective.py`/`strategy_choice_observation.py`
    are derived views over that same family's own output, not independent
    evidence.
12. **`horizon_revision_backtest`** -- re-slices already-recorded checkpoint
    prices under alternate horizon labels; no new observation, no adapter.
13. **`conditional_alpha_diagnosis`** -- cohort/archetype cross-tabulation
    over pre-existing evaluated artifacts; no new samples, no adapter.
14. **`integrated_trade_diagnosis`** -- lineage/policy-counterfactual
    consumer; every return figure traces to an artifact another family
    already produced; no adapter.
15. **`opening_rank1_longitudinal` adjuncts** (`stage_fate.py`,
    `universe_control.py`, `analysis.py`, `daily_provider.py`) -- extend the
    already-classified Opening Shadow 1B/1C evaluator's blast radius to
    more symbols/the full universe; not a second evaluator, folds into
    family #6.
16. **Confirmed non-families**: `evidence_ledger.py`,
    `strategy_feedback_builder.py`, `strategy_memory_store.py` --
    storage/plumbing, checked and excluded (no price/return math).

## 5. Canonical Mapping Table

*(See per-family entries below; fields follow the mandatory schema from the
UEF-4A task: LEGACY NAME/SOURCE, PRIMARY ROLE, SOURCE FILES/ARTIFACTS,
OBSERVATION TYPE, SAMPLE UNIT, EVALUATION SUBJECT, HORIZON(S), REFERENCE
PRICE SEMANTICS, FORWARD PROFILE, SOURCE RESULT COST SEMANTICS, RETURN UNIT,
COST POLICY REQUIREMENT, MISSING SEMANTICS, EXCLUDED SEMANTICS, ORDERING/
TIMESTAMP AUTHORITY, AGGREGATION SCOPE, HYPOTHESIS/PROGRAM PROVENANCE,
CANONICAL UEF TARGET, ADAPTER REQUIRED, ADAPTER FAMILY, LOSSLESS MAPPING,
KNOWN AMBIGUITIES, RECOMMENDED ACTION.)*

### 5.1 Q9 Horizon/Exit

- **LEGACY NAME/SOURCE**: Q9 Horizon/Exit (post-exit shadow feedback)
- **PRIMARY ROLE**: A. ALPHA_PROGRAM (post-exit shadow measurement of the
  live strategy's own actual exits)
- **SOURCE FILES**: `libs/runtime/strategy_horizon_feedback.py` (function
  `update_post_exit_shadow_with_price_observations`)
- **SOURCE ARTIFACTS**: post-exit shadow rows keyed by decision/exit event
- **OBSERVATION TYPE**: forward price observation anchored to the strategy's
  OWN actual exit event (`EventOrigin.ACTUAL_EXIT`)
- **SAMPLE UNIT**: one realized trade's post-exit shadow window (one actual
  entry+exit episode)
- **EVALUATION SUBJECT**: the live strategy's own executed trade
- **HORIZON(S)**: +5m/+15m/+30m/+60m (relative to exit) + EOD
- **REFERENCE PRICE SEMANTICS**: `FIXED_OBSERVED_PRICE` anchored at
  `ACTUAL_EXIT`, 4-deep alias chain (`price`/`current_price`/`cur_price`
  fallback) -- `profiles.py:104-145`
- **FORWARD PROFILE**: `build_q9_horizon_exit_profile` (UEF-2A profile #1)
- **SOURCE RESULT COST SEMANTICS**: `GROSS_ONLY` (only `return_pct` is ever
  written -- no `net_return_pct`/cost/slippage field anywhere in the source,
  per `profiles.py:144`)
- **RETURN UNIT**: `FRACTION`
- **COST POLICY REQUIREMENT**: an explicit `CostPolicy` must be supplied
  externally to compute UEF-3A `NetReturnRecord.COMPUTED`; none exists in
  source
- **MISSING SEMANTICS**: `MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK`
  for intraday checkpoints, `KEEP_PENDING` for EOD (per UEF-2A profile)
- **EXCLUDED SEMANTICS**: not modeled at this layer (no policy-exclusion flag
  found in the cited function)
- **ORDERING/TIMESTAMP AUTHORITY**: `observed_timestamp` (checkpoint's own
  resolved observation time)
- **AGGREGATION SCOPE**: per-symbol/per-exit-event, horizon-scoped
- **HYPOTHESIS/PROGRAM PROVENANCE**: `legacy_program="q9_horizon_exit_post_exit_shadow"`
- **CANONICAL UEF TARGET**: UEF-2A (already mapped, frozen) -> UEF-2B (engine,
  frozen) -> UEF-3A/3B/3C for cost/metric/aggregation (a UEF-4B adapter is
  needed ONLY to translate the real artifact's raw row shape into UEF-2B's
  `CanonicalObservation` input -- the semantic mapping itself is already
  100% settled by UEF-2A)
- **ADAPTER REQUIRED**: YES (artifact-shape -> canonical-observation
  translation; UEF-4's actual job, not a new semantic decision)
- **ADAPTER FAMILY**: `forward_measurement_adapter` (shared shape with every
  other UEF-2A-profiled family; see Section 6)
- **LOSSLESS MAPPING**: YES (UEF-2A already re-verified this exactly)
- **KNOWN AMBIGUITIES**: none beyond the general "no CostPolicy exists in
  source" gap already flagged by UEF-2A/3A (cost must come from an external,
  explicitly-provenanced policy, never invented)
- **RECOMMENDED ACTION**: KEEP (implement adapter in UEF-4B)

### 5.2 Q10 Semiconductor (Calc A/B/C)

- **LEGACY NAME/SOURCE**: Q10 Semiconductor (Samsung/Hynix baseline forward
  engine)
- **PRIMARY ROLE**: C. BASELINE/REFERENCE (a baseline comparison engine --
  confirm final classification against Section 8's Q10 special-attention
  analysis; functionally it is the reused GROSS-only forward engine also
  invoked by Q12 Calc1)
- **SOURCE FILES**: `libs/reporting/quant_shadow_forward_outcomes.py`
  (`attach_forward_outcomes`, Calc A), `libs/reporting/baseline_samsung_hynix/forward_returns.py`
  (`_extended_checkpoint` = Calc B, inline EOD override = Calc C,
  `decision_candidate_rows`, `summarize_forward_returns`)
- **SOURCE ARTIFACTS**: `baseline_samsung_hynix_tech/*/baseline_*_forward_returns.json`
  (per earlier UEF-3A evidence read)
- **OBSERVATION TYPE**: forward price observation anchored to a ranked
  candidate at decision time (`EventOrigin.CANDIDATE`)
- **SAMPLE UNIT**: one ranked candidate within one baseline decision --
  identity is effectively `(baseline_decision_id, symbol/ticker, rank)`, per
  `decision_candidate_rows` (`forward_returns.py`). **Known subtlety**: the
  real aggregator (`summarize_forward_returns`) computes THREE overlapping
  views over this same population -- `top1` (rank==1 only), `both_symbol_average`
  (mean across all ranked candidates observed), and `eligible_entries` (only
  candidates with `eligible=True`) -- these are not three separate sample
  populations in the UEF-3A sense, but three different slices of the SAME
  evaluated set. UEF-4B must decide (with the user) which slice(s) become
  canonical `SamplePopulation`s, or whether all three become 3 distinct
  `MetricAggregationContext`s sharing one horizon.
- **EVALUATION SUBJECT**: one candidate's forward price move from its own
  baseline/reference price
- **HORIZON(S)**: +5m/+15m/+30m/+60m (Calc A), +120m/+180m (Calc B), EOD
  (Calc C)
- **REFERENCE PRICE SEMANTICS**: `BAR_CLOSE -> REFERENCE_PRICE`, anchored at
  `CANDIDATE`
- **FORWARD PROFILE**: `build_q10_semiconductor_calc_{a,b,c}_profile`
  (UEF-2A profiles #2-4)
- **SOURCE RESULT COST SEMANTICS**: `GROSS_ONLY` (no net/cost field anywhere
  in `attach_forward_outcomes`/`_extended_checkpoint` -- confirmed
  `profiles.py:179,201,219`); cost is applied DOWNSTREAM, per-sample, BEFORE
  aggregation, by `summarize_forward_returns` itself (`value - drag`, `drag =
  cost_pct + slippage_pct`) -- this downstream cost application is real
  UEF-3A `CostTiming.ROUND_TRIP` evidence, already cited in UEF-3A's own
  contract docstring
- **RETURN UNIT**: `PERCENTAGE_POINTS`
- **COST POLICY REQUIREMENT**: an explicit `CostPolicy` (ROUND_TRIP,
  `commission`+`slippage`) must be supplied to reach `NetReturnRecord.COMPUTED`
- **MISSING SEMANTICS**: `{"status": "pending"}` when the forward checkpoint
  has not yet resolved (`_extended_checkpoint` returns this when `observed is
  None`) -- "expected but unavailable", never conflated with "not applicable"
- **EXCLUDED SEMANTICS**: the `eligible` flag on each candidate row is a
  POLICY-level inclusion gate for the `eligible_entries` view specifically --
  ineligible candidates are NOT dropped from `top1`/`both_symbol_average`,
  only from `eligible_entries`. This means "excluded" is VIEW-DEPENDENT here,
  a genuine ambiguity for canonical mapping (see above).
- **ORDERING/TIMESTAMP AUTHORITY**: `observed_timestamp` (`TARGET_TIMESTAMP`-
  bounded excursion for Calc A, `OWN_CHECKPOINT_OBSERVATION` for B/C)
- **AGGREGATION SCOPE**: per-decision, per-horizon
- **HYPOTHESIS/PROGRAM PROVENANCE**: `legacy_program="baseline_samsung_hynix_calc_{a,b,c}"`
- **CANONICAL UEF TARGET**: UEF-2A/2B (frozen, settled) -> UEF-3A/3B/3C
- **ADAPTER REQUIRED**: YES
- **ADAPTER FAMILY**: `forward_measurement_adapter` (shared with Q12 Calc1 --
  literally the same engine)
- **LOSSLESS MAPPING**: MOSTLY YES, with the three-views ambiguity above
  flagged explicitly (not a UEF defect -- a real legacy multiplicity UEF-4B
  must make an explicit decision about, not silently pick one)
- **KNOWN AMBIGUITIES**: three-views-per-population (top1/both/eligible);
  which becomes canonical, or all three as separate contexts
- **RECOMMENDED ACTION**: KEEP (implement adapter in UEF-4B; resolve the
  three-views question explicitly before or during that work)

### 5.3 Q10 Index (Calc F/G/H)

- **LEGACY NAME/SOURCE**: Q10 Index (Samsung/Hynix index reaction + shadow
  comparison)
- **PRIMARY ROLE**: C. BASELINE/REFERENCE for F/G (raw reaction capture); H
  is a DERIVED directional-shadow layer over F/G's own candle series (see
  Section 8)
- **SOURCE FILES**: `libs/reporting/baseline_samsung_hynix/forward_validation/reaction_reader.py`
  (`_stock_reaction`/`_forward_window` = Calc F, `_index_reaction` = Calc G),
  `libs/reporting/baseline_samsung_hynix/forward_validation/shadow_comparison.py`
  (`build_shadow_comparison`, `_first_pullback_entry` = Calc H)
- **SOURCE ARTIFACTS**: index/stock reaction JSON (`q10_actual_market_reactions.json`),
  expected-vs-actual JSON (`q10_expected_vs_actual.json`, Calc H direction
  denominator), shadow comparison JSON (`q10_shadow_entry_comparison.json`,
  Calc H outcomes)
- **OBSERVATION TYPE**: fixed-clock forward price observation (F/G), directional
  shadow outcome anchored to a pre-resolved pullback-entry reference (H)
- **SAMPLE UNIT**: one fixed-clock checkpoint per symbol-day (F/G); one
  directional shadow trade per symbol-day (H)
- **EVALUATION SUBJECT**: index/stock reaction at fixed clocks (F/G); a
  program-specific 0.5%-retracement-scan-selected entry's forward outcome (H)
- **HORIZON(S)**: 09:00 + 09:03/09:05/09:10/09:15 (F); 09:30/10:00/CLOSE,
  3-state governed (G); EOD (H)
- **REFERENCE PRICE SEMANTICS**: `BAR_OPEN` at fixed clock (F/G);
  `PRE_RESOLVED_REFERENCE` with `provenance="FIRST_PULLBACK_ENTRY"` (H) --
  UEF-2A explicitly does NOT implement the 0.5%/60-min retracement-scan
  ALGORITHM itself (ruled a program-specific research technique, not a
  generic forward-measurement primitive -- `profiles.py:301-313`); UEF-2B
  only ever consumes an ALREADY-RESOLVED reference for H
- **FORWARD PROFILE**: `build_q10_index_calc_{f,g,h}_profile` (UEF-2A
  profiles #5-7)
- **SOURCE RESULT COST SEMANTICS**: `GROSS_ONLY` (F/G, raw OHLCV capture
  only); `NET_OR_COST_INCLUDED` (H -- `build_shadow_comparison` populates
  BOTH `gross_eod_return_pct` AND `net_eod_return_pct=gross-total_cost` in
  the same row, `shadow_comparison.py:112-113`)
- **RETURN UNIT**: `PERCENTAGE_POINTS`
- **COST POLICY REQUIREMENT**: explicit `CostPolicy` needed for F/G;
  NOT NEEDED for H (source is already `NET_OR_COST_INCLUDED` --
  `NetReturnComputationStatus.SOURCE_PROVIDED`, never reapplied)
- **MISSING SEMANTICS**: 3-state governed (`ABSENT`/`INVALID`/`VERIFIED`,
  `EvidenceVerificationState`) for G -- a materially richer missing-taxonomy
  than any other family in this inventory; F uses plain
  `EXPIRE_AFTER_TOLERANCE`
- **EXCLUDED SEMANTICS**: none found distinct from missing at this layer
- **ORDERING/TIMESTAMP AUTHORITY**: fixed-clock target time (F/G);
  `observed_timestamp` at EOD (H)
- **AGGREGATION SCOPE**: per-symbol-day
- **HYPOTHESIS/PROGRAM PROVENANCE**: `legacy_program="baseline_samsung_hynix_calc_{f,g}"` /
  `baseline_samsung_hynix_forward_validation_shadow_comparison` (H)
- **CANONICAL UEF TARGET**: UEF-2A/2B (frozen, settled) -> UEF-3A/3B/3C
- **ADAPTER REQUIRED**: YES for F/G/H
- **ADAPTER FAMILY**: `forward_measurement_adapter` for F/G;
  `directional_shadow_adapter` for H (genuinely different -- pre-resolved
  reference + already-net source + directional/SHORT gross-return convention)
- **LOSSLESS MAPPING**: YES for F/G/H's OWN checkpoint/excursion math (UEF-2A
  re-verified); the retracement-scan ALGORITHM that SELECTS H's entry point
  is explicitly OUT of UEF-2B's scope (never implemented canonically) --
  UEF-4B's H adapter must receive an ALREADY-RESOLVED reference from
  wherever that scan already runs today, never re-implement the scan
- **KNOWN AMBIGUITIES**: **RESOLVED at UEF-4B-4 implementation time** --
  F and G are ONE source family / ONE computational algorithm
  (`reaction_reader.py`'s `_stock_reaction`, which `_index_reaction`
  thinly wraps), reused across TWO DISJOINT physical populations by
  target kind (stock symbols for F, index symbols for G) -- verified
  directly against `build_actual_reactions()`, which iterates the same
  4-entry `TARGETS` tuple and branches only on `target["kind"]`. This is
  never "one physical sample, two views" -- each (day, symbol) remains
  its own distinct physical event; G's only genuine difference is its
  richer, collector-governed 3-state missing taxonomy for 3 checkpoints,
  an adapter-local missing-semantics decision, not a physical-identity
  one. See `libs/reporting/evaluation/canonical/adapters/
  q10_index_reaction_adapter.py`'s own module docstring for the full
  resolution. The retracement-scan's own home remains legacy, not
  canonical, by design (unchanged).
- **RECOMMENDED ACTION**: KEEP -- implemented as ONE adapter module
  (`q10_index_reaction_adapter.py`) covering both Calc F and Calc G
  (population-disjoint, never merged); Calc H implemented separately
  (`q10_index_directional_shadow_adapter.py`), reusing an
  externally-resolved reference and every other outcome field verbatim
  from the real, already-resolved `q10_shadow_entry_comparison.json`.
  Calc H derives its key-to-symbol physical identity authority from the
  same verified `q10_actual_market_reactions.json` artifact F/G consume,
  never from a caller-supplied map.

### 5.4 Q11 Opportunity Engine

- **LEGACY NAME/SOURCE**: Q11 Opportunity Engine
- **PRIMARY ROLE**: B. NEGATIVE_CONTROL/SHADOW -- Q11 is a virtual-opportunity
  simulator (probes hypothetical entries, not the live strategy's own real
  trades), consistent with its role as an opportunity/negative-control
  evaluator rather than an alpha program with real capital at risk
- **SOURCE FILES**: `libs/research/opportunity_engine/simulator.py`
  (`simulate_probe_v0`)
- **SOURCE ARTIFACTS**: opportunity-engine probe result JSON
- **OBSERVATION TYPE**: forward price observation anchored to a virtual
  signal (`EventOrigin.SIGNAL`), PLUS a distinct `EXIT` checkpoint anchored
  to `ACTUAL_EXIT` (the simulator's own virtual close, not a real broker fill)
- **SAMPLE UNIT**: one simulated probe/virtual position (one virtual entry ->
  forward horizons + a simulated exit)
- **EVALUATION SUBJECT**: a virtual (never-executed) candidate position
- **HORIZON(S)**: +5m/+15m/+30m/+60m (forward, from SIGNAL), EOD (from
  SIGNAL, no excursion at all -- `excursion=None`, confirmed no
  `mfe_pct`/`mae_pct` key exists in source, `profiles.py:367,385-391`), EXIT
  (relative_seconds=0, from `ACTUAL_EXIT`, its own separate excursion chain)
- **REFERENCE PRICE SEMANTICS**: entry/reference =
  `BAR_CLOSE -> SOURCE_FIELD_PRICE` (`candle.get("close") or
  features.get("price")`, `simulator.py:125`); forward-horizon excursion
  fallback terminates at `BAR_CLOSE` (2-deep, no `features` access in that
  scan); EXIT's own excursion fallback is a DIFFERENT, 3-deep chain
  (`BAR_HIGH -> BAR_CLOSE -> SOURCE_FIELD_PRICE`) -- UEF-2A's own Q11 FINAL
  FIDELITY PATCH explicitly separated these two (previously wrongly shared)
- **FORWARD PROFILE**: `build_q11_opportunity_engine_profile` (UEF-2A
  profile #8)
- **SOURCE RESULT COST SEMANTICS**: `NET_OR_COST_INCLUDED` (`simulator.py`
  populates BOTH `return_pct` (gross) AND `net_return_pct`
  (`cost_pct`/`slippage_pct`-adjusted) in the same result dict)
- **RETURN UNIT**: `PERCENTAGE_POINTS`
- **COST POLICY REQUIREMENT**: NONE -- `NetReturnComputationStatus.SOURCE_PROVIDED`,
  reapplying a `CostPolicy` here would double-count
- **MISSING SEMANTICS**: EOD has no excursion key at all by design (not
  "missing", genuinely "not applicable" for this checkpoint -- `excursion=None`,
  never conflated with a resolvable-but-absent observation); EXIT uses
  `MARK_MISSING_IMMEDIATELY` (exact-timestamp lookup, no tolerance window)
- **EXCLUDED SEMANTICS**: none found at this layer
- **ORDERING/TIMESTAMP AUTHORITY**: `observed_timestamp` per checkpoint
- **AGGREGATION SCOPE**: per virtual-probe, per-horizon
- **HYPOTHESIS/PROGRAM PROVENANCE**: `legacy_program="q11_opportunity_engine"`
- **CANONICAL UEF TARGET**: UEF-2A/2B (frozen, settled) -> UEF-3A/3B/3C
- **ADAPTER REQUIRED**: YES
- **ADAPTER FAMILY**: `virtual_probe_adapter` (distinct from
  `forward_measurement_adapter` -- Q11's EXIT checkpoint and its
  already-net source semantics have no equivalent among the GROSS_ONLY
  families)
- **LOSSLESS MAPPING**: `opportunity_engine_virtual_trades.v1` (legacy) --
  **NO**. UEF-4B-5 FIX1 (proven downstream contract contradiction, source-
  verified, not inferred): the legacy artifact's `_forward_returns()`
  (`simulator.py`) computes every +5m/+15m/+30m/+60m/EOD `return_pct`/
  `net_return_pct`/`mfe_pct`/`mae_pct` from one specific candle `close`,
  but v1 never persists that price -- only the already-derived
  percentages. These checkpoints are genuinely `CheckpointMetricKind.
  PRICE_BASED` (anchored to one real observed price), so a v1 artifact
  cannot be losslessly canonicalized without either fabricating a price
  (forbidden) or mischaracterizing the checkpoint as `AGGREGATE_ONLY`
  (semantically false -- rejected by independent audit). **v1 remains
  real PRIMARY EVIDENCE, KNOWN, but DIRECT UEF-4B CANONICALIZATION IS
  BLOCKED for this version** -- never approximated, never rewritten in
  place; recovering v1's own historical evidence is an explicit UEF-5
  Historical Recompute concern (rerunning real market inputs through the
  repaired source), never a UEF-4B adapter's job.
  `opportunity_engine_virtual_trades.v2` (repaired) -- **YES**: the same
  `_forward_returns()` now additionally persists `"observed_price": close`
  per OBSERVED horizon (additive only, `simulator.py`; `TRADES_SCHEMA`
  bumped accordingly, `contracts.py`) -- v2 is a candidate lossless
  canonical source, verified oracle-exact (price + outcome) against the
  real simulator directly and against a real end-to-end
  `build_opportunity_engine_artifacts` run.
- **KNOWN AMBIGUITIES**: none beyond the general "is a virtual probe the
  right unit to fair-compare against a real-trade family" question, which is
  a Q100/research-program concern, not a UEF-4 mapping defect
- **RECOMMENDED ACTION**: KEEP -- v2 approved for canonicalization; v1
  stays BLOCKED for direct mapping (see LOSSLESS MAPPING above)

### 5.5 Q12 BTC-Woori (Calc1/2/3)

- **LEGACY NAME/SOURCE**: Q12 BTC -> 우리기술투자 (BTC-Woori) cross-asset
  hypothesis
- **PRIMARY ROLE**: A. ALPHA_PROGRAM (Calc2/Calc3 -- the hypothesis-specific
  forward/vnext engines) with Calc1 as a REUSE of the Q10 Semiconductor
  engine (see below)
- **SOURCE FILES**: `libs/reporting/baseline_btc_woori_tech/forward_returns.py`
  (`attach_forward_returns` -> Calc1), `libs/reporting/baseline_btc_woori_tech/hypothesis_forward.py`
  (`entry_forward_outcomes` -> Calc2), `libs/reporting/baseline_btc_woori_tech/vnext/outcomes.py`
  (`forward` -> Calc3)
- **SOURCE ARTIFACTS**: BTC-Woori daily comparison/hypothesis-validation JSON
  (confirmed present under `reports/evaluation/baseline_btc_woori_tech/` in
  this session's own test-run production-write logs)
- **OBSERVATION TYPE**: forward price observation on a BTC-signal-triggered
  candidate in 우리기술투자 (local equity), at `CANDIDATE` origin (Calc1) or
  `FIXED_CLOCK` origin (Calc3)
- **SAMPLE UNIT**: Calc1 -- IDENTICAL to Q10 Semiconductor's own sample unit
  (one ranked candidate per decision) -- confirmed by UEF-2A: Python
  free-variable resolution makes `attach_baseline_forward_returns`'s
  `HORIZONS` reference resolve to `baseline_samsung_hynix.contracts.HORIZONS`
  (its DEFINING module), never Q12's own 4-element `HORIZONS` -- i.e. Calc1
  is not independent code, it is the SAME Q10 Semiconductor engine invoked
  on BTC-Woori's own candidates, producing 7 real checkpoints (not the 4 one
  might assume from Q12's own contracts module). Calc2/Calc3 -- one
  BTC-Woori hypothesis candidate at a fixed clock (09:30/10:00/EOD, Calc3)
  or relative horizon (Calc2)
- **EVALUATION SUBJECT**: 우리기술투자 forward price move following a BTC
  signal event
- **HORIZON(S)**: Calc1 -- 7 real checkpoints (+5/15/30/60m + 120/180m + EOD,
  the Q10-Semiconductor engine's full set); Calc2 -- +5/15/30/60m + EOD (5
  labels, per `HYPOTHESIS_HORIZONS`); Calc3 -- 09:30/10:00/EOD
- **REFERENCE PRICE SEMANTICS**: Calc1/Calc2 -- `BAR_CLOSE`, `CANDIDATE`
  origin; Calc3 -- `FIXED_OBSERVED_PRICE`, `CANDIDATE` origin
- **FORWARD PROFILE**: `build_q12_calc{1,2,3}_*_profile` (UEF-2A profiles
  #9-11)
- **SOURCE RESULT COST SEMANTICS**: `GROSS_ONLY` (Calc1 -- same engine as
  Q10 Semiconductor, no net field); `NET_OR_COST_INCLUDED` (Calc2/Calc3 --
  both populate `gross_return_pct` AND `net_return_pct=gross-drag_pct` in
  the same result dict, `hypothesis_forward.py:73-78` / `vnext/outcomes.py:25-27`)
- **RETURN UNIT**: `PERCENTAGE_POINTS`
- **COST POLICY REQUIREMENT**: explicit `CostPolicy` for Calc1 only; NONE
  for Calc2/Calc3 (already net, `SOURCE_PROVIDED`)
- **MISSING SEMANTICS**: Calc1 -- identical to Q10 Semiconductor; Calc3 --
  a genuine 60-second CONTIGUOUS-BAR completeness gate on the EXCURSION scan
  specifically (`complete = len(window) == expected`, `outcomes.py:24`) --
  the checkpoint's own `gross_return_pct` is reported regardless of
  `complete`, but `mfe_pct`/`mae_pct` are `None` unless the full contiguous
  window is present. This is a materially richer, genuinely distinct
  missing-semantics rule vs every other family in this inventory (partial
  completeness at the metric-component level, not just the observation
  level)
- **EXCLUDED SEMANTICS**: none found distinct from missing
- **ORDERING/TIMESTAMP AUTHORITY**: `observed_timestamp` (Calc1/2);
  `target_timestamp`-bounded, end-EXCLUSIVE except EOD (Calc3)
- **AGGREGATION SCOPE**: per-decision (Calc1/2), per-symbol-day (Calc3)
- **HYPOTHESIS/PROGRAM PROVENANCE**: `legacy_program="baseline_btc_woori_tech_calc1_shared_engine"` /
  `_hypothesis_forward` / `_vnext`
- **CANONICAL UEF TARGET**: UEF-2A/2B (frozen, settled) -> UEF-3A/3B/3C
- **ADAPTER REQUIRED**: YES for Calc2/Calc3; Calc1 needs NO new adapter code
  of its own -- it is a straight re-invocation of the Q10 Semiconductor
  `forward_measurement_adapter` on a different candidate source, per item 7's
  "do not create separate adapter architecture unless actual source
  semantics require it"
- **ADAPTER FAMILY**: `forward_measurement_adapter` (Calc1, shared with Q10
  Semiconductor); `hypothesis_forward_adapter` (Calc2); `vnext_completeness_adapter`
  (Calc3 -- the contiguous-bar completeness gate is genuinely distinct)
- **LOSSLESS MAPPING**: Calc1/Calc2 -- YES (UEF-4B-2 implemented and
  independently closed for Calc1; Calc2's legacy high/low excursion
  fallback confirmed lossless against the real legacy function directly,
  UEF-4B-2 FIX1). **Calc3 -- UNKNOWN (UEF-4B-2 FIX2, narrow reopen of this
  frozen entry under freeze-reopen case #3, "proven downstream contract
  contradiction")**: the real legacy `vnext/outcomes.py::forward` gates
  excursion completeness on `complete = len(window) == expected`
  (ROW-COUNT only), while the frozen UEF-2A/2B `CONTIGUOUS_INTERVAL`
  policy requires the actual observed timestamp SET to equal the expected
  grid SET exactly -- a strictly stronger rule. A prior pass argued the
  two are equivalent because the real shared candle loader
  (`baseline_samsung_hynix.data_provider._normalize_rows`, reused by
  Calc1/Calc2/Calc3 alike) "never produces" an off-grid timestamp; an
  independent audit correctly rejected that as an absence-of-evidence
  inference, not a proof. A synthetic, row-count-complete, off-grid
  reproducer now demonstrates the actual divergence directly against both
  the real legacy function and the frozen `evaluate_forward()` engine
  (`tests/test_uef4b2_q12_adapter.py::
  test_calc3_legacy_row_count_vs_frozen_completeness_contradiction_reproducer`):
  legacy reports `path_status="COMPLETE"` with real MFE/MAE; the frozen
  engine, fed the identical data, reports MFE/MAE as unresolved for the
  same horizon. `gross_return` agrees (the checkpoint observation itself
  is unaffected); only the excursion/completeness verdict diverges.
- **KNOWN AMBIGUITIES**: none beyond Q10 Semiconductor's own (inherited by
  Calc1). **NEW (Calc3, UEF-4B-2 FIX2)**: legacy row-count completeness is
  not proven equivalent to frozen exact-contiguous-minute completeness
  over Calc3's actual valid source domain -- see Table D.
- **RECOMMENDED ACTION**: Calc1 -> ABSORB into the Q10 Semiconductor
  adapter family (no separate implementation, IMPLEMENTED). Calc2 -> KEEP
  as its own adapter (IMPLEMENTED). **Calc3 -> KEEP as PRIMARY EVIDENCE,
  ADAPTER REQUIRED CONCEPTUALLY = YES, but CANONICALIZATION BLOCKED** --
  never demoted to consumer/derived-view/deprecated, not implemented
  pending a future architecture decision on how (or whether) to represent
  row-count-only completeness in the frozen contract. The experimental
  `vnext_completeness_adapter.py` module is retained as a research/
  reproducer artifact only (exports nothing, `__all__ = []`) -- it is not
  part of UEF-4B-2's approved scope.

### 5.6 Opening Shadow (1A/1B/1C)

- **LEGACY NAME/SOURCE**: Opening Shadow (rank-1 scanner candidate forward
  measurement)
- **PRIMARY ROLE**: B. NEGATIVE_CONTROL/SHADOW (a pure observation/measurement
  layer over the scanner's own rank-1 candidate -- see Section 8's dedicated
  Opening-Alpha-vs-scanner-rank disambiguation for whether a SEPARATE
  "Opening Alpha" alpha-program exists)
- **SOURCE FILES**: `libs/reporting/opening_rank1_shadow/latent_forward.py`
  (`_observe` -> 1A), `libs/research/opening_rank1_longitudinal/delayed_outcomes.py`
  (`forward_30m_net` -> 1B, `delayed_path` -> 1C)
- **SOURCE ARTIFACTS**: opening rank-1 shadow/longitudinal outcome JSON
- **OBSERVATION TYPE**: forward price observation anchored to a scanner
  SIGNAL (1A), a MONITOR_DECISION (1B), or a CUSTOM forward-session-count
  origin (1C)
- **SAMPLE UNIT**: one rank-1 scanner candidate episode (1A); one monitored
  decision's +30m outcome (1B); one candidate's d1/d3/d5 forward-SESSION
  (not forward-time) outcome (1C)
- **EVALUATION SUBJECT**: the scanner's own rank-1 candidate's forward price
  move
- **HORIZON(S)**: +5/15/30/60m + EOD (1A); +30m only (1B); d1/d3/d5 forward
  sessions (1C)
- **REFERENCE PRICE SEMANTICS**: `BAR_OPEN -> BAR_CLOSE`, `SIGNAL` origin
  (1A); `BAR_OPEN -> BAR_CLOSE`, `MONITOR_DECISION` origin (1B);
  `FIXED_OBSERVED_PRICE`, `CUSTOM` origin (1C)
- **FORWARD PROFILE**: `build_opening_shadow_1{a,b,c}_profile` (UEF-2A
  profiles #12-14)
- **SOURCE RESULT COST SEMANTICS**: `GROSS_ONLY` (1A -- `_observe`'s
  checkpoints only ever carry `gross_return_pct`; cost is computed
  separately downstream in `_summary()`); `NET_OR_COST_INCLUDED` (1B/1C --
  both bake `ROUND_TRIP_COST_PCT=0.28` directly into the ONLY return figure
  produced by the shared `_net()` helper -- no separable gross figure exists
  at all)
- **RETURN UNIT**: `PERCENTAGE_POINTS`
- **COST POLICY REQUIREMENT**: explicit `CostPolicy` for 1A only; NONE for
  1B/1C (already net; `SOURCE_PROVIDED`, and there is no separable gross to
  recompute from even if one wanted to)
- **MISSING SEMANTICS**: 1A -- `KEEP_PENDING` intraday, `KEEP_PENDING` EOD;
  1C -- `d{n}_status = "INSUFFICIENT_FUTURE_DAYS"` fires IMMEDIATELY
  (`MARK_MISSING_IMMEDIATELY`, never waits/expires) whenever
  `len(selected_days) < horizon or missing_days` -- a genuinely distinct,
  session-count-based (not time-based) missing rule
- **EXCLUDED SEMANTICS**: none found distinct from missing
- **ORDERING/TIMESTAMP AUTHORITY**: `observed_timestamp` (1A/1B);
  forward-SESSION count, `ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS`
  (1C -- a session-index authority, not a timestamp, genuinely distinct from
  every other family in this inventory)
- **AGGREGATION SCOPE**: per rank-1 episode, per-horizon
- **HYPOTHESIS/PROGRAM PROVENANCE**: `legacy_program="opening_rank1_shadow_latent_forward"` /
  `opening_rank1_longitudinal_forward_30m_net` / `_delayed_path`
- **CANONICAL UEF TARGET**: UEF-2A/2B (frozen, settled) -> UEF-3A/3B/3C
- **ADAPTER REQUIRED**: YES for 1A/1B/1C
- **ADAPTER FAMILY**: `forward_measurement_adapter` (1A, GROSS_ONLY, shares
  shape with Q9/Q10/Q12-Calc1); `already_net_shadow_adapter` (1B/1C, shares
  shape with Q11/Q12-Calc2/3's NET_OR_COST_INCLUDED handling, but 1C's
  forward-SESSION-count ordering authority is unique enough to flag
  separately -- see Section 8 ambiguities)
- **LOSSLESS MAPPING**: YES (UEF-2A re-verified all three, including
  dedicated fixes for 1A's excursion fallback and 1C's missing-status timing)
- **KNOWN AMBIGUITIES**: whether "Opening Alpha" (a report-attribution
  label) refers to this exact family or to something else entirely -- see
  Section 8
- **RECOMMENDED ACTION**: KEEP (implement adapters in UEF-4B); resolve the
  Opening-Alpha-attribution question (Section 8) BEFORE or ALONGSIDE this
  work so reports stop conflating the two

### 5.7 Q8 (five files, one semantic layer)

- **LEGACY NAME/SOURCE**: Q8 (`q8_evaluation_contract.py`, `q8_historical_review.py`,
  `q8_lane_decision_table.py`, `q8_shadow_blocker_review.py`,
  `q8_trusted_reaggregation.py`)
- **PRIMARY ROLE**: NOT a single role -- `q8_evaluation_contract.py` is
  shared infra (EVALUATION_CONSUMER support: dedupe key + trust-gate
  constants, no report of its own); `q8_historical_review.py` and
  `q8_lane_decision_table.py` are G. REPORT/VIEW; `q8_shadow_blocker_review.py`
  is F. POLICY/DEFENSIVE_REVIEW (judges whether a REJECTED/blocked candidate
  was correctly blocked, by forward-evaluating what would have happened);
  `q8_trusted_reaggregation.py` is E. VALIDATION/DIAGNOSTIC (multi-day
  trust-gate promotion gating)
- **SOURCE FILES**: the five `libs/reporting/q8_*.py` files, plus the REAL
  evidence engine they all sit downstream of --
  `libs/reporting/quant_shadow_candidate_evaluation.py` and
  `libs/reporting/quant_shadow_forward_outcomes.py::attach_forward_outcomes`
  (this is the SAME engine already canonically mapped as Q10 Semiconductor
  Calc A -- Section 5.2)
- **SOURCE ARTIFACTS**: `data/logs/quant_shadow_candidates/<day>/*.json`,
  `reports/operator_summary/daily/<day>/daily_summary.json`,
  `reports/trades/**/ai_trade_summary.json`
- **OBSERVATION TYPE**: none owned by Q8 itself -- see CANONICAL UEF TARGET
- **SAMPLE UNIT**: a shadow candidate keyed by `(day, symbol, baseline_epoch,
  entry_lane_subtype)` (`q8_evaluation_contract.py:15,48-59`) for the
  lane/blocker/reaggregation reports; a calendar day (`q8_historical_review.py:341-380`);
  a closed trade read from `ai_trade_summary.json` (`:279-313`)
- **EVALUATION SUBJECT**: candidates/trades already evaluated elsewhere
- **HORIZON(S)**: whatever `attach_forward_outcomes` already produced
  (+3/5/15/30/60m, EOD) -- not decided by Q8
- **REFERENCE PRICE SEMANTICS / FORWARD PROFILE**: N/A -- Q8 never resolves
  a reference price itself; it reads `attach_forward_outcomes`'s output
  (already covered under Q10 Semiconductor Calc A)
- **SOURCE RESULT COST SEMANTICS**: `GROSS_ONLY` for the forward-checkpoint
  numbers it reads (no fee/slippage term anywhere in `attach_forward_outcomes`
  or any `q8_*.py`, confirmed by grep); `UNKNOWN` for `truth_surface.pnl_pct`
  pulled from live trade reports in `q8_historical_review.py:293,300` (that
  field's own cost treatment is defined outside Q8's code)
- **RETURN UNIT**: percentage points (inherited from the underlying engine)
- **COST POLICY REQUIREMENT**: N/A (consumer only)
- **MISSING SEMANTICS**: "missing" = placeholder label for blank/unknown
  text fields (normalized: `-`/`none`/`null`/`unknown`/`not_captured` ->
  empty, `q8_evaluation_contract.py:22-24`)
- **EXCLUDED SEMANTICS**: stale/cross-day forward checkpoints (status
  `stale`/`pending`) are excluded from TRUSTED-forward counts specifically
  in `q8_trusted_reaggregation.py:220` -- a report-level exclusion, not a
  record deletion
- **ORDERING/TIMESTAMP AUTHORITY**: N/A (consumer)
- **AGGREGATION SCOPE**: per-day / per-lane / multi-day (varies by report)
- **HYPOTHESIS/PROGRAM PROVENANCE**: bespoke `(day, symbol, baseline_epoch,
  entry_lane_subtype)` key -- confirmed NOT the repo's canonical `EventRef`
  identity (`canonical/identity.py`); no `q8_*.py` file imports or uses it
- **CANONICAL UEF TARGET**: none directly -- if a UEF-2A/2B adapter is ever
  warranted for the underlying evidence, it belongs to
  `quant_shadow_candidate_evaluation.py`/`attach_forward_outcomes` itself
  (i.e. it folds into the Q10 Semiconductor Calc A adapter family, Section
  5.2), never to any `q8_*.py` report/review file
- **ADAPTER REQUIRED**: NO (all five files)
- **ADAPTER FAMILY**: N/A (consumer); the underlying engine is already
  `forward_measurement_adapter` (Q10 Semiconductor family)
- **LOSSLESS MAPPING**: N/A (nothing here to lose -- Q8 has no evidence of
  its own to map)
- **KNOWN AMBIGUITIES**: `truth_surface.pnl_pct`'s own cost semantics are
  UNKNOWN from Q8's code alone (defined in the live trade-report writer,
  out of this document's scope)
- **RECOMMENDED ACTION**: CONSUMER_ONLY (all five files)

### 5.8 Baselines & Adjacent Modules (Samsung/Hynix comparison, Q10 Index
collector, Alpha Research Board, Short Alpha Discriminator, controlled
mock lanes)

- **Samsung/Hynix `q9_comparison.py`/`unified_comparison.py`**: DERIVED VIEW
  -- `build_q9_role_comparison` (`q9_comparison.py:57-179`) reads Q9's own
  already-persisted decision-candidate logs, forward-evaluates them via the
  SAME shared `attach_forward_outcomes` utility (Q10 Semiconductor Calc A),
  and compares against a `baseline_summary` passed in as a parameter -- it
  does NOT compute the baseline itself (that happens upstream in
  `pipeline.py::build_baseline_artifacts` via `strategy.py::build_decision_snapshot`,
  a real momentum/volume rule engine, + `forward_returns.py`, already Q10
  Semiconductor Calc B/C). `unified_comparison.py` reads an already-written
  `forward_payload` JSON and re-derives markdown/JSON rows. **ADAPTER
  REQUIRED = NO** for the comparison layer itself; the underlying
  `strategy.py::build_decision_snapshot` + `forward_returns.py` pairing IS
  already covered as Q10 Semiconductor (Section 5.2). Confidence: HIGH.
- **`libs/market/q10_index_observation_collector.py`**: **PRIMARY DATA
  COLLECTOR**, not a derived view -- `capture_q10_index_snapshot` performs
  a genuine live broker-API fetch (`KiwoomMarketIndexReader.get_index_packet`)
  and persists raw KOSPI/KOSDAQ snapshots with at-most-once claim semantics.
  This is the raw-observation acquisition path Q10 Index's own forward
  evaluation (Section 5.3, Calc F/G) consumes -- its own file header states
  it fixes a prior gap ("Q10 Index EOD close had no dedicated observation-
  acquisition path"). `q10_observation_integrity.py` is pure validation
  support, not a collector. **This collector should be considered PART OF
  the Q10 Index primary-evidence chain** (feeds Calc F/G), not a separate
  family requiring its own adapter -- but UEF-4B's Q10 Index adapter must
  account for it as the actual raw-observation source. Confidence: HIGH.
- **Opportunity Engine (Q11) other files** (`contracts.py`, `engine.py`,
  `features.py`, `data_provider.py`, `report.py`, `pipeline.py`): all are
  stages of the SAME Q11 pipeline (signal generation -> simulation ->
  report) -- no separate shadow/negative-control mechanism found. Folds
  entirely into Q11 (Section 5.4). Confidence: HIGH.
- **`opening_rank1_shadow/five_session_review.py`**: DERIVED VIEW -- takes
  already-computed summaries as parameters, produces a fixed-window
  promotion-gate verdict. Folds into Opening Shadow (Section 5.6). No
  independent adapter. Confidence: HIGH.
- **`libs/reporting/alpha_research_board/`**: DERIVED VIEW -- `build_alpha_research_board`
  exclusively loads existing artifacts across every family in this
  inventory and assembles them into candidate rows; explicit self-declared
  purpose: `"Consolidate existing evidence; do not rerun broad historical
  mining."` Pure aggregation/display, zero new observations. ADAPTER
  REQUIRED = NO. Confidence: HIGH.
- **`libs/reporting/short_alpha_discriminator/` (`opening_policy_matrix.py`,
  `cohorts.py`)**: DERIVED VIEW -- reads Opening Rank1 Shadow's cumulative
  summary + the feature mart (both existing artifacts), joins by
  `decision_id`, computes cohort/leave-one-out statistics purely from
  already-computed outcomes. Folds into Opening Rank1 Shadow + feature-mart
  families. ADAPTER REQUIRED = NO. Confidence: HIGH.
- **Controlled Mock Lanes (`libs/runtime/controlled_mock_lanes/coordinator.py`+`ledger.py`)
  and `libs/runtime/opening_rank1_controlled_probe.py`**: **PRIMARY EVIDENCE
  SOURCES in their own right** -- genuinely distinct from every shadow-only
  family above. `inject_controlled_mock_lane_intent` writes real
  `state["intents"]` through the ACTUAL execution code path against a mock
  broker (`EXECUTION_MODE=real`+`KIWOOM_MODE=mock`), and
  `finalize_controlled_mock_lane_submission` records the real (mock)
  broker response (`order_id`/`broker_outcome`) into a ledger.
  `opening_rank1_controlled_probe.py::evaluate_opening_rank1_controlled_probe`
  is a SEPARATE mechanism specific to Opening Rank-1 that lets a
  reduced-quantity real mock-broker probe order through, and
  `record_rank1_observation` persists raw rank/price observations
  independent of the shadow pipeline. `controlled_validation_daily.py` and
  `controlled_mock_lane_report.py` are pure reporting/reconciliation layers
  over these ledgers (DERIVED VIEWS, no adapter needed). **This is a
  genuinely new evidence-generating mechanism this document must flag as
  its own family** -- see Table B / Ambiguities. Confidence: MEDIUM (the
  ledger-write mechanism itself is HIGH confidence; how/whether
  Monitor/Commander actually invokes the controlled-probe path in the live
  decision graph was not directly traced, only referenced in comments).

### 5.9 Q13/Q14/Q15/Q16/Q17/Q18

- **LEGACY NAME/SOURCE**: Q13/Q14 -- `libs/reporting/evaluation/q13_q14_validation.py`
  (validation layer) + `libs/reporting/evaluation/scanner_alignment_root_cause.py`
  (Q14's own attribution generator); Q15 -- no dedicated file, a live
  runtime policy in `libs/runtime/controlled_mock_lanes/contracts.py` +
  `libs/runtime/monitor_candidate_cascade.py`; Q16/Q17 -- both live inside
  `libs/reporting/evaluation/q16_proxy_rejection_review.py`; Q18 --
  `libs/reporting/evaluation/post_reclaim_shadow_review.py`
- **PRIMARY ROLE**:
  - Q13/Q14: E. VALIDATION/DIAGNOSTIC (explicit in source:
    `"decision_scope": "diagnostic_stability_only"`,
    `"behavior_patch_authorized": False`)
  - Q15: F. POLICY/DEFENSIVE_REVIEW (an ACTIVE production guardrail --
    `docs/evaluation/q9_q18_operating_status_2026-08-05.md`: "Weak
    runner-up cascade restriction | Retain | Active defensive policy")
  - Q16: F. POLICY/DEFENSIVE_REVIEW (RETAIN/ROLL_BACK authority over a cost-
    rejection filter, frozen `Q16_FINAL_DECISION = "RETAIN"`) -- but see
    below, Q16 is NOT a pure consumer
  - Q17: E. VALIDATION/DIAGNOSTIC (contract-correctness validation, no
    retain/rollback decision issued)
  - Q18: D. EVALUATION_CONSUMER (closed "RETAIN SHADOW", executable v0
    rejected, `"runtime_directional_edge_used": False"`)
- **SOURCE FILES**: as above
- **SOURCE ARTIFACTS**: `attribution_score_v0.json`,
  `scanner_alignment_root_cause_report.json`, `horizon_compliance_report.json`
  (Q13/14); raw shadow logs + minute OHLCV (Q16/Q17, self-loaded); Q8's
  historical review output (Q18)
- **OBSERVATION TYPE / SAMPLE UNIT**: Q13/14 -- one calendar trading day,
  rolled up over a >=5-day window (`REQUIRED_VALIDATION_DAYS=25`); Q15 --
  one runner-up candidate accepted/skipped during cascade selection (a
  gate decision, not a return metric); Q16 -- one shadow candidate row
  rejected by cost filtering, with a forward-outcome checkpoint at a fixed
  horizon (+15m/+30m); Q17 -- one triggered candidate with a
  `directional_edge_estimate`, evaluated at its own strategy-declared
  horizon; Q18 -- the single named profile
  `vwap_reclaim:post_reclaim_pullback_candidate`
- **EVALUATION SUBJECT**: Q13/14 -- Q9-Q12's own already-attributed trade
  outcomes; Q15 -- a live cascade candidate; Q16/Q17 -- shadow candidates
  UEF-2A's 14-profile registry never covers (a DIFFERENT population --
  rejected/cost-filtered candidates, not the admitted alpha population);
  Q18 -- Q8's already-aggregated forward-return summary for one profile
- **HORIZON(S)**: Q16/17 -- +15m/+30m and strategy-declared horizons
  respectively; others N/A (no forward measurement of their own beyond
  what's cited)
- **REFERENCE PRICE SEMANTICS / FORWARD PROFILE**: Q13/14/15/18 -- N/A (no
  own forward-measurement); Q16/Q17 -- use the SAME `attach_forward_outcomes`
  engine already covered as Q10 Semiconductor Calc A (Section 5.2), but over
  a genuinely DIFFERENT candidate population (rejected/cost-filtered, not
  admitted) -- this is real NEW evidence-generation, contradicting the
  initial "likely pure consumer" hypothesis for Q16/Q17
- **SOURCE RESULT COST SEMANTICS**: Q16/17 -- `GROSS_ONLY` (same
  `attach_forward_outcomes`/`performance_metrics` computation as Q10
  Semiconductor); others N/A
- **RETURN UNIT**: Q16/17 -- percentage points (inherited); others N/A
- **COST POLICY REQUIREMENT**: Q16/17 -- same as Q10 Semiconductor (external
  explicit `CostPolicy` needed for `NetReturnRecord.COMPUTED`); others N/A
- **MISSING SEMANTICS**: not separately re-derived for Q16/17 (inherits
  the underlying engine's); Q13/14/18 -- N/A (consumer-only, no missing
  concept of their own)
- **EXCLUDED SEMANTICS**: Q16/17's ENTIRE population IS a legacy-level
  "excluded" set (candidates that were rejected/cost-filtered by policy at
  candidate-selection time) -- this is itself the evaluation subject, not
  a within-population exclusion; a materially different EXCLUDED concept
  than every alpha-program family in this inventory (worth flagging for
  UEF-4B: Q16/Q17's population is definitionally the "excluded" branch of
  Q9-12's own candidate funnel)
- **ORDERING/TIMESTAMP AUTHORITY**: Q16/17 -- inherits `attach_forward_outcomes`'s
  own (Section 5.2); others N/A
- **AGGREGATION SCOPE**: Q13/14 -- multi-day rollup; Q15 -- per-cascade-
  decision; Q16/17 -- per-rejected-candidate-cohort; Q18 -- per-named-profile
- **HYPOTHESIS/PROGRAM PROVENANCE**: Q16 -- `q16_forward_integrity.v2`
  (self-declared contract version); Q18 -- `q18_horizon_coverage.v2`
- **CANONICAL UEF TARGET**: Q13/14/15/18 -- none (no primary evidence of
  their own); Q16/17 -- if canonicalized at all, would target UEF-2A/2B via
  the SAME `forward_measurement_adapter` shape as Q10 Semiconductor, but
  applied to a rejected/cost-filtered population that is explicitly OUT OF
  SCOPE for UEF-4A's "fair alpha comparison" purpose (this is defensive-
  policy evidence, not alpha evidence) -- **RECOMMENDED: do not adapt Q16/17
  into the alpha-comparison canonical core; if ever needed, treat as its own
  policy-evidence family, separately from Section 6's adapter table**
- **ADAPTER REQUIRED**: Q13/14/15/18 -- NO; Q16/17 -- NO for UEF-4B's
  stated purpose (alpha fair-comparison), even though they DO generate real
  primary evidence -- that evidence serves a retain/rollback POLICY decision,
  not an alpha lane, and adapting it would risk exactly the "policy/
  diagnostic promoted into a strategy lane" mistake Section 5 of the task
  explicitly warns against
- **ADAPTER FAMILY**: N/A for all six under the current recommendation
- **LOSSLESS MAPPING**: N/A (not recommended for canonical adaptation)
- **KNOWN AMBIGUITIES**: Q15's "review" half is doc-only (no checked-in
  evaluator) -- the ACTIVE POLICY code is unambiguous, but its own
  retrospective shadow-evaluation evidence (if it should ever need
  independent verification) does not exist as code today; Q16/Q17 DO own
  real primary evidence contrary to the initial consumer-only hypothesis,
  which is itself worth flagging so a future reviewer does not assume they
  are pure consumers
- **RECOMMENDED ACTION**: Q13/14/15/18 -> CONSUMER_ONLY; Q16/17 -> KEEP as
  their own defensive-policy evidence trail, but explicitly OUTSIDE the
  UEF-4B alpha-comparison adapter scope (RETIRE from adapter consideration,
  not from existence -- the code stays, just never becomes a UEF-2A profile)

---

# FIX1 Addendum — `libs/research/**` Offline Evaluator Families

The sections below close the independent audit's HIGH finding. Method:
the six audit-named anchor files were read in full alongside their
`contracts.py`/`pipeline.py`/`episodes.py`/sibling modules; every other
`libs/research/**` subdirectory was then swept (directory listing diffed
against already-covered names, plus a content grep for
`forward_return|net_return|gross_return|entry_price|exit_price|mfe|mae|def evaluate|def backtest`)
to confirm no further family was missed. Result: **0 additional omitted
families beyond the six anchors and the three directories the sweep
independently surfaced** (`existing_evidence_mining`, `integrated_trade_diagnosis`,
`rank1_feature_mart`) -- see Section 5.16.

### 5.10 The `post_reclaim_alpha` engine family (5 directories, 1 adapter family)

- **LEGACY NAME/SOURCE**: `post_reclaim_alpha` (base engine),
  `structural_alpha` + `structural_alpha_batch2` (one family, two
  hypothesis batches), `alpha_competition`, `existing_evidence_mining` --
  all FIVE directories call the identical function
  `post_reclaim_alpha/evaluator.py::evaluate_episodes`/`_checkpoint`
  (confirmed by direct import in every case: `structural_alpha/evaluator.py:7`,
  `structural_alpha_batch2/pipeline.py:12` imports `structural_alpha`'s own
  evaluator, `alpha_competition/pipeline.py` invokes the same `_checkpoint`
  logic, `existing_evidence_mining/episodes.py:121` calls
  `evaluate_episodes` imported at `evaluator.py:160`)
- **PRIMARY ROLE**: ALPHA_PROGRAM for all five (each supplies its OWN
  candidate population/hypotheses; `structural_alpha`'s hypothesis H5 is a
  stub with no evidence -- `sector_not_testable_result()`,
  `evaluator.py:191-203` -- and is EVALUATION_CONSUMER/no-evidence for that
  one hypothesis specifically, not the whole directory)
- **SOURCE FILES**:
  - `post_reclaim_alpha/evaluator.py` (`_checkpoint` lines 26-108,
    `_eod_checkpoint` 111-157) -- the base
  - `structural_alpha/evaluator.py` (imports base, own `strategies.py`
    candidate builder `_episode`, lines 38-51)
  - `structural_alpha_batch2/pipeline.py` (imports `structural_alpha`'s
    evaluator/contracts/episode-builder directly, adds new
    `features.py` RSI-14/SMA5-20/market-proxy-return, new `strategies.py`
    hypotheses H7-H9)
  - `alpha_competition/evaluator.py`+`pipeline.py`+`candidates.py`+`hypotheses.py`
    (own candidate ingestion from raw shadow-candidate logs, own H1-H3
    hypotheses, own FRESH live Kiwoom minute-history fetch via
    `kiwoom_history.py`)
  - `existing_evidence_mining/episodes.py`+`loaders.py`+`pipeline.py`
    (reconstructs candidates from raw point-in-time Q9 decision-window
    logs and quant-shadow candidate logs; explicitly self-tags
    `evidence_class: "RECONSTRUCTED_FROM_POINT_IN_TIME_Q9"` /
    `"RECONSTRUCTED_QUANT_SHADOW"`, `episodes.py:117`)
- **SOURCE ARTIFACTS**: raw minute OHLCV (all five, each via its own
  fetch/cache path); `data/logs/quant_shadow_candidates/*/*.json` and
  `reports/operator_summary/daily/*/q9_decision_windows.json` (candidate
  population sources for `existing_evidence_mining`/`alpha_competition`)
- **OBSERVATION TYPE**: forward price observation anchored to a
  point-in-time candidate/episode, with a parallel EOD checkpoint
- **SAMPLE UNIT**: one `(day, symbol, baseline_epoch[, entry_lane_subtype/strategy_id])`
  episode per directory's own candidate-construction rule (base:
  `post_reclaim_alpha/episodes.py:91,126-148`; `structural_alpha`: one
  selected cross-sectional-leader/contraction-breakout episode,
  `strategies.py:38-51`; `alpha_competition`: one hypothesis-matched,
  15-minute-gap-segmented episode, `candidates.py:132-139`;
  `existing_evidence_mining`: one reconstructed Q9/quant-shadow candidate,
  `episodes.py:98-119`)
- **EVALUATION SUBJECT**: a post-reclaim-pullback signal (base); a
  cross-sectional-leader/contraction-breakout/market-shock-reversal/
  oversold/trend-pullback candidate (structural_alpha family); an
  H1-H3-matched shadow candidate (alpha_competition); a reconstructed
  pre-Strategist scanner or quant-shadow candidate (existing_evidence_mining)
- **HORIZON(S)**: `+5m/+15m/+30m/+60m` + `EOD` -- identical across all
  five (`post_reclaim_alpha/contracts.py:9` `HORIZONS_MINUTES`, reused
  verbatim by every dependent)
- **REFERENCE PRICE SEMANTICS**: base/`existing_evidence_mining`/`alpha_competition`
  -- externally pre-resolved `baseline_price`/`baseline_epoch` read from
  `shadow_forward_base` in the raw candidate; `structural_alpha`/`structural_alpha_batch2`
  -- LOCALLY resolved as the first complete candle strictly after
  `decision_epoch` (`bar.open or bar.close`, `structural_alpha/features.py:40-58`,
  `strategies.py:37`) -- a genuinely different reference-resolution rule
  than the other four, though the downstream checkpoint math is identical
- **FORWARD PROFILE**: not yet a named UEF-2A profile (this is the
  FIX1-identified gap) -- would be a new profile family, see below
- **SOURCE RESULT COST SEMANTICS**: `NET_OR_COST_INCLUDED`, but with a
  shape none of the 6 pre-existing adapter families support: ONE
  `gross_return_pct` feeds TWO parallel net-of-cost figures in the SAME
  result -- `live_net_return_pct = gross - LIVE_COST_PCT` and
  `mock_net_return_pct = gross - MOCK_COST_PCT`
  (`post_reclaim_alpha/evaluator.py:97-105`, constants `LIVE_COST_PCT=0.28`,
  `MOCK_COST_PCT=1.086849`, `contracts.py:10-11`) -- confirmed identical in
  all five directories since all five call the same function
- **RETURN UNIT**: `PERCENTAGE_POINTS` (`(close/baseline_price-1)*100`)
- **COST POLICY REQUIREMENT**: NONE to reach the two net figures (already
  computed, `SOURCE_PROVIDED`-shaped) -- but see LOSSLESS MAPPING below for
  how two parallel cost policies/net figures fit the frozen contract
- **MISSING SEMANTICS**: `status: "missing"` with reasons
  `forward_price_missing`/`forward_observation_delay_exceeded`/
  `eod_price_missing`/`eod_close_window_not_reached`
  (`post_reclaim_alpha/evaluator.py:53,68,79,127,136`) -- identical across
  all five
- **EXCLUDED SEMANTICS**: episode-gap dedup (`EPISODE_GAP_SEC`, collapses
  near-duplicate candidates -- base/`structural_alpha` both use this,
  `episodes.py:118`/`strategies.py:101,157`); `structural_alpha`/`batch2`
  additionally apply their OWN selection/eligibility filters (candidate
  pool size, VWAP/RSI/market-shock gates) before an episode is ever built
  (`strategies.py:82,98-100,115-116,187-197,210-219`)
- **ORDERING/TIMESTAMP AUTHORITY**: raw minute-candle `ts` orders the
  forward scan; `baseline_epoch`/`decision_epoch` orders episodes --
  identical mechanism across all five
- **AGGREGATION SCOPE**: per-episode, per-horizon, per-directory's-own
  candidate population
- **HYPOTHESIS/PROGRAM PROVENANCE**: base has none beyond `episode_id`;
  `structural_alpha`/`batch2` add `strategy_id`+`decision_id`
  (`strategies.py:39-51`); `alpha_competition` adds `hypothesis_id`
  (`candidates.py:136-146`); `existing_evidence_mining` adds an explicit
  `evidence_class` reconstruction tag
- **CANONICAL UEF TARGET**: **UNRESOLVED** -- would target UEF-2A (new
  profile) -> UEF-2B -> UEF-3A/3B/3C IF the dual-net-variant shape can be
  represented under the frozen contract, but see LOSSLESS MAPPING: it
  currently cannot be, without a frozen-core change this task forbids
- **ADAPTER REQUIRED CONCEPTUALLY**: YES for `post_reclaim_alpha` (base),
  `structural_alpha`, `alpha_competition`, `existing_evidence_mining` (4
  separate candidate-population/reference-resolution adapters would feed
  ONE shared checkpoint/cost transformation, IF that transformation were
  representable); `structural_alpha_batch2` would ABSORB into
  `structural_alpha`'s adapter (identical engine/reference resolution, only
  new hypotheses/features/candidates)
- **UEF-4B IMPLEMENTABLE**: **NO -- BLOCKED** (FIX2 correction; see LOSSLESS
  MAPPING)
- **ADAPTER FAMILY**: **NOT AN APPROVED FAMILY** -- `dual_cost_variant_forward_adapter`
  is a candidate transformation family NAME only, for inventory discussion;
  it carries no implementation authority (see "Blocked Adapter Family
  Candidate," Section 6)
- **LOSSLESS MAPPING**: **UNKNOWN -- BLOCKED (FIX2 correction, was
  incorrectly YES under FIX1)**. FIX1 proposed materializing TWO canonical
  `NetReturnRecord`s from one shared gross observation, one per named cost
  policy. Re-reading the actual frozen contract shows this is not valid:
  the source's own `live_net_return_pct`/`mock_net_return_pct` are already
  net figures (`SourceResultCostSemantics.NET_OR_COST_INCLUDED`), which per
  `NetReturnComputationStatus`'s own docstring
  (`metrics/contracts.py:161-178`) can only ever reach
  `NetReturnComputationStatus.SOURCE_PROVIDED`, never `COMPUTED` -- and
  `calculate_net_return()` structurally enforces this:
  `_require(cost_policy is None, ...)` when
  `source_cost_semantics is NET_OR_COST_INCLUDED`
  (`metrics/engine.py:186-188`), explicitly to prevent double-counting an
  already-included cost. Constructing a `COMPUTED` `NetReturnRecord` with
  an explicit `CostPolicy` from this source would require reinterpreting a
  `SOURCE_PROVIDED` figure as `GROSS_ONLY`, which is exactly what item 6 of
  this task forbids and what the frozen engine already rejects at runtime.
  No mechanism in the current frozen contract represents "one gross feeding
  two independently-provenanced already-net figures" -- this is a genuine
  gap, not a resolvable adapter detail.
- **KNOWN AMBIGUITIES**: the canonicalization blocker above (frozen
  contract has no shape for two source-provided net variants sharing one
  gross); `structural_alpha`'s H5 stub carries no evidence and should
  simply be omitted from any future adapter's output, not force-mapped
- **RECOMMENDED ACTION**: **EVIDENCE FAMILY KNOWN, CANONICALIZATION
  BLOCKED.** Do not implement an adapter. Do not discard or demote this
  evidence to consumer/derived-view -- all five directories retain PRIMARY
  EVIDENCE=YES. Revisit only after either (a) a future frozen-core-compatible
  extension to UEF-3A explicitly designed to represent multiple
  source-provided net variants sharing one gross observation, or (b) a
  product decision to treat the two variants as two independent
  `SamplePopulation`s each carrying only its own already-net figure (no
  `CostPolicy` involved, `SOURCE_PROVIDED` both times) -- neither of which
  this document decides; both are noted for a future UEF-4B design pass, not
  implemented here.

### 5.11 `rank1_feature_mart` (mixed: primary evidence + internal consumers)

- **LEGACY NAME/SOURCE**: `rank1_feature_mart`
- **PRIMARY ROLE**: split by file --
  `outcomes.py`/`builder.py`/`pipeline.py` = ALPHA_PROGRAM (own
  self-computed forward outcomes); `activation_shadow.py`/`prospective.py`
  = NEGATIVE_CONTROL/SHADOW + REPORT/VIEW (read `feature_mart.json`,
  compute nothing); `strategy_choice_observation.py` = REPORT/VIEW (no
  outcome data at all)
- **SOURCE FILES**: `outcomes.py` (`_net()` lines 22-25,
  `_checkpoint()` 28-51), `builder.py`, `pipeline.py` (candidate identity
  sourced from `conditional_alpha_diagnosis/conditional_alpha_episode_contexts.json`
  and `opening_rank1_shadow/opening_rank1_shadow_cumulative.json` --
  `pipeline.py:36-37,41-43` -- this module does NOT mint its own
  candidates, only its own forward OUTCOMES on candidates named elsewhere)
- **SOURCE ARTIFACTS**: `feature_mart.json` (self-produced), raw minute
  bars via `opening_rank1_deep_dive/microstructure.py`+
  `opening_rank1_longitudinal/daily_provider.py` (`loaders.py:8-9`)
- **OBSERVATION TYPE**: forward price observation, self-computed, on a
  candidate identity owned by two OTHER already-classified families
- **SAMPLE UNIT**: one candidate (sourced from `conditional_alpha_diagnosis`
  or `opening_rank1_shadow`), evaluated at this module's OWN extended
  horizon set
- **EVALUATION SUBJECT**: the same rank-1/conditional-alpha candidates
  those two families already name -- this module adds NEW, LONGER-HORIZON
  outcomes on top of them, not a new candidate population
- **HORIZON(S)**: `5/15/30/60/120/180` minutes + `EOD`/`NEXT_OPEN`/
  `D+1_30m`/`D+1_EOD`/`D+2_EOD`/`D+3_EOD`/`D+5_EOD` (`contracts.py:9,10-24`)
  -- a materially larger and differently-shaped horizon set than any
  other family in this inventory (mixes intraday relative-minute labels
  with multi-CALENDAR-DAY labels in ONE checkpoint set, unlike Opening
  Shadow 1C's pure forward-SESSION-count d1/d3/d5)
- **REFERENCE PRICE SEMANTICS**: inherited from whichever upstream
  candidate source supplied the episode (not independently resolved here)
- **FORWARD PROFILE**: none existing; would be a new, distinct profile if
  ever canonicalized
- **SOURCE RESULT COST SEMANTICS**: `NET_OR_COST_INCLUDED` --
  `_net() = round((price/baseline-1)*100 - LIVE_COST_PCT, 4)`
  (`outcomes.py:22-25`) -- ONE cost constant, ONE net figure (NOT the
  dual-variant shape of Section 5.10's family)
- **RETURN UNIT**: `PERCENTAGE_POINTS`
- **COST POLICY REQUIREMENT**: none (already net)
- **MISSING SEMANTICS**: falls back to an upstream ALREADY-COMPUTED field
  (`fallback.get(...)`, `outcomes.py:84-85,98`; `longitudinal.get(...)`,
  `:142`) when this module's OWN raw-bar computation cannot resolve a
  value -- a genuinely novel hybrid (self-computed PRIMARY, with a
  read-from-elsewhere FALLBACK) not seen in any other family in this
  inventory
- **EXCLUDED SEMANTICS**: not independently confirmed from source in this
  pass
- **ORDERING/TIMESTAMP AUTHORITY**: raw minute-candle `ts` for intraday
  horizons; calendar-day indexing for the D+N labels
- **AGGREGATION SCOPE**: per-candidate (borrowed identity), per-extended-horizon
- **HYPOTHESIS/PROGRAM PROVENANCE**: borrowed from
  `conditional_alpha_diagnosis`/`opening_rank1_shadow`
- **CANONICAL UEF TARGET**: **UNRESOLVED** -- see LOSSLESS MAPPING
- **ADAPTER REQUIRED**: YES for `outcomes.py`/`builder.py`/`pipeline.py`
  (if ever implemented); NO for `activation_shadow.py`/`prospective.py`/
  `strategy_choice_observation.py` (pure in-package consumers of
  `feature_mart.json`)
- **ADAPTER FAMILY**: NOT YET DETERMINED -- does not cleanly match
  `already_net_shadow_adapter` (single net figure, cost baked in --
  matches) BECAUSE its horizon-authority mixes intraday relative-time with
  multi-day calendar-session labels in one checkpoint set, AND it has a
  fallback-to-upstream mechanic no existing family's contract anticipates.
  This document could not fully confirm from source alone whether a
  `gross_return_pct` field also co-exists alongside `_net()`'s output in
  every checkpoint, which materially affects which shape applies.
- **LOSSLESS MAPPING**: **UNKNOWN** -- explicitly not resolved by this
  pass. Per this document's own policy (Section 15 of the FIX1 request):
  an UNKNOWN family is BLOCKED from UEF-4B until resolved, not force-fit
  into an existing shape or used to justify a frozen-core change.
- **KNOWN AMBIGUITIES**: (a) exact field co-existence (gross vs. net-only)
  per checkpoint unconfirmed; (b) the fallback-to-upstream mechanic's
  effective frequency in real artifacts is unverified (would need a real
  `feature_mart.json` sample, not just source reading) -- both flagged as
  a new Table D entry
- **RECOMMENDED ACTION**: BLOCK from UEF-4B pending a follow-up read of
  one real `feature_mart.json` artifact and a closer read of
  `outcomes.py`'s full checkpoint-construction code (this pass read the
  net-computation core but could not exhaustively confirm every field).
  `activation_shadow.py`/`prospective.py`/`strategy_choice_observation.py`
  remain CONSUMER_ONLY regardless of how the `outcomes.py` question
  resolves.

### 5.12 `horizon_revision_backtest` -- re-slice, not new evidence

- **LEGACY NAME/SOURCE**: `horizon_revision_backtest`
- **PRIMARY ROLE**: EVALUATION_CONSUMER
- **SOURCE FILES**: `loaders.py` (`load_trade_observations`, lines 16-49),
  `analysis.py` (checkpoint re-bucketing, lines 27-78)
- **PRIMARY EVIDENCE**: NO -- `loaders.py` reads ONLY pre-existing
  `trade_read_model.json`/`trade_evaluation.json`/`post_exit_shadow_recap.json`
  (produced by other, already-recorded-trade modules); no raw price fetch
  anywhere in this package. `analysis.py` recomputes gross/live-net/mock-net
  percentages, but strictly from CHECKPOINT PRICES another evaluator
  already stored (`post_exit_shadow.checkpoints`/`recap.checkpoints`/
  `evaluation.exit_quality.observed_checkpoints`, `analysis.py:27-40`) --
  a re-bucketing of an already-completed trade's own recorded prices under
  alternate horizon labels, never a new observation
- **SAMPLE UNIT**: one already-completed trade (`trade_id`), re-evaluated
  at `("actual_exit","+5m","+15m","+30m","+60m","EOD","T+1","T+2")`
- **COST SEMANTICS**: recomputes the SAME `live_cost_pct=0.28`/
  `mock_cost_pct=1.086849` constants as Section 5.10's family
  (`pipeline.py:18-19`) -- but applied to ALREADY-RECORDED checkpoint
  prices of an ALREADY-COMPLETED trade, not a fresh forward observation
- **ADAPTER REQUIRED**: NO -- explicit `behavior_effect="offline_evaluation_only"`
  (`analysis.py:204`); this is a downstream comparison/diagnostic layer
- **LOSSLESS MAPPING**: N/A (not primary evidence)
- **RECOMMENDED ACTION**: CONSUMER_ONLY

### 5.13 `conditional_alpha_diagnosis` -- cohort/archetype diagnostic, no new samples

- **LEGACY NAME/SOURCE**: `conditional_alpha_diagnosis`
- **PRIMARY ROLE**: VALIDATION/DIAGNOSTIC
- **SOURCE FILES**: `loaders.py` (`load_existing_research`, lines 18-28,
  reads deep-dive `cases`, longitudinal `events`, AND -- notably --
  `horizon_revision_backtest`'s own output file as its third source,
  `pipeline.py:54`), `horizons.py`/`analysis.py` (field selection only,
  `analysis.py:8-14`), `cohorts.py`/`contrasts.py` (cross-tabulation)
- **PRIMARY EVIDENCE**: NO -- reads three pre-existing evaluated
  artifacts; selects already-computed fields
  (`return_5m_pct`/`net_return_30m_pct`/etc.); computes no new price delta
  anywhere (confirmed: no gross/net formula, no entry/exit price used in
  any return calculation in this package)
- **EXPLICIT SELF-DECLARATION**: `behavior_effect="NONE_OFFLINE_RESEARCH_ONLY"`
  (`horizons.py:68`); "not a per-trade oracle exit" (`horizons.py:63`)
- **ADAPTER REQUIRED**: NO
- **LOSSLESS MAPPING**: N/A (not primary evidence)
- **RECOMMENDED ACTION**: CONSUMER_ONLY

### 5.14 `integrated_trade_diagnosis` -- lineage/policy-counterfactual consumer

- **LEGACY NAME/SOURCE**: `integrated_trade_diagnosis`
- **PRIMARY ROLE**: VALIDATION/DIAGNOSTIC
- **SOURCE FILES**: `read_model.py` (reads `outcome.get("net_return_pct")`
  verbatim, line 48), `prospective.py` (reads
  `opening_rank1_shadow_daily.json` checkpoints verbatim, lines 65-88 --
  "prospective" here means "eligible for post-hoc validation of an
  ALREADY-RECORDED outcome," not a new forward measurement),
  `policies.py` (relabels existing fields into policy buckets, no new
  math, lines 62-66), `metrics.py` (generic win-rate/PF/drawdown
  aggregator over already-existing return lists, lines 14-44)
- **PRIMARY EVIDENCE**: NO -- every return figure traces to an artifact
  another family already produced; this module never touches raw price
  bars
- **ADAPTER REQUIRED**: NO
- **LOSSLESS MAPPING**: N/A
- **RECOMMENDED ACTION**: CONSUMER_ONLY

### 5.15 `opening_rank1_longitudinal` adjuncts -- reuse, not a new family

- **LEGACY NAME/SOURCE**: `stage_fate.py`, `universe_control.py`,
  `analysis.py`, `daily_provider.py` (all within
  `opening_rank1_longitudinal/`, alongside the already-classified
  `delayed_outcomes.py` = Opening Shadow 1B/1C, Section 5.6)
- **PRIMARY ROLE**: orchestration/reuse over the already-classified
  evaluator, not a second evaluator
- **FINDING**: `stage_fate.py` imports `forward_30m_net` directly from
  `delayed_outcomes.py` (line 7) and invokes it on THREE ADDITIONAL
  counterfactual symbols per decision (strategist pick, monitor candidate,
  executed symbol -- `stage_fate.py:79-86`); `universe_control.py` imports
  both `forward_30m_net` and `delayed_path` (line 8) and invokes them
  across the broader rank1-10 universe (`build_universe_paths`, lines
  50-107); `analysis.py` and `daily_provider.py` are pure statistics/raw-bar
  supply with zero independent return formula
- **PRIMARY EVIDENCE**: NO independently -- these files EXTEND the
  already-classified Opening Shadow 1B/1C evaluator's blast radius to more
  symbols/the full universe, they do not define a second return formula
- **ADAPTER REQUIRED**: NO (folds into the existing Opening Shadow
  1B/1C adapter -- a future UEF-4B implementation of that adapter should
  simply be aware these call sites exist and may want the SAME adapter
  invoked more broadly, not that a second adapter is needed)
- **RECOMMENDED ACTION**: fold into Opening Shadow 1B/1C (rows 10-11);
  no separate row needed beyond a footnote

### 5.16 Confirmed non-families -- storage/plumbing, checked and excluded

- **`libs/research/evidence_ledger.py`**: pure append-only JSONL logger,
  explicitly "passive logging only and does not mutate runtime decisions"
  (docstring, line 61); no price/return math
- **`libs/research/strategy_feedback_builder.py`**: aggregates
  QUALITATIVE feedback (monitor/scanner issue frequency), explicitly
  avoids computing returns (`performance_metric_usable: False`, lines
  70,96,281) -- "without inventing return attribution" (docstring,
  lines 34-39)
- **`libs/research/strategy_memory_store.py`**: persistence/query layer;
  its one numeric rollup (`_build_performance_summary`, lines 124-159)
  sums a pre-existing field (`estimated_realized_pnl`) computed by the
  upstream reporter, not a forward-return computation of its own
- **VERDICT for all three**: PRIMARY EVIDENCE = NO, ADAPTER REQUIRED = NO,
  ROLE = infrastructure/plumbing (not assigned one of the 9 classification
  roles -- these are not evaluation modules at all)

### Table A — Legacy → Role

| # | Legacy source | Role | Primary evidence? | Adapter? |
|---|---|---|---|---|
| 1 | Q9 Horizon/Exit (`strategy_horizon_feedback.py`) | ALPHA_PROGRAM | YES | YES |
| 2 | Q10 Semiconductor Calc A/B/C (`quant_shadow_forward_outcomes.py`, `baseline_samsung_hynix/forward_returns.py`) | BASELINE/REFERENCE | YES | YES |
| 3 | Q10 Index Calc F/G (`forward_validation/reaction_reader.py`) | BASELINE/REFERENCE | YES | YES |
| 4 | Q10 Index Calc H (`forward_validation/shadow_comparison.py`) | NEGATIVE_CONTROL/SHADOW (directional) | YES | YES |
| 5 | Q11 Opportunity Engine (`opportunity_engine/simulator.py` + pipeline) | NEGATIVE_CONTROL/SHADOW | YES | YES |
| 6 | Q12 Calc1 shared-engine reuse (`baseline_btc_woori_tech/forward_returns.py`) | BASELINE/REFERENCE | NO (= row 2's engine) | NO — absorbs into row 2 |
| 7 | Q12 Calc2 (`baseline_btc_woori_tech/hypothesis_forward.py`) | ALPHA_PROGRAM | YES | YES |
| 8 | Q12 Calc3 vnext (`baseline_btc_woori_tech/vnext/outcomes.py`) | ALPHA_PROGRAM | YES | YES — BLOCKED (CANONICAL/LOSSLESS MAPPING=UNKNOWN, UEF-4B-2 FIX2, Section 6) |
| 9 | Opening Shadow 1A (`opening_rank1_shadow/latent_forward.py`) | NEGATIVE_CONTROL/SHADOW | YES | YES |
| 10 | Opening Shadow 1B (`opening_rank1_longitudinal/delayed_outcomes.py::forward_30m_net`) | NEGATIVE_CONTROL/SHADOW | YES | YES |
| 11 | Opening Shadow 1C (`delayed_outcomes.py::delayed_path`) | NEGATIVE_CONTROL/SHADOW | YES | YES |
| 12 | Q8 (5 files: `q8_evaluation_contract/historical_review/lane_decision_table/shadow_blocker_review/trusted_reaggregation.py`) | mixed: REPORT/VIEW + POLICY/DEFENSIVE_REVIEW + VALIDATION/DIAGNOSTIC (per sub-file, Section 5.7) | NO | NO |
| 13 | Samsung/Hynix `q9_comparison.py` + `unified_comparison.py` | REPORT/VIEW | NO | NO |
| 14 | Q10 Index observation collector (`libs/market/q10_index_observation_collector.py`) | (infra) PRIMARY DATA COLLECTOR feeding row 3 | YES | NO — folds into row 3 |
| 15 | Opportunity Engine adjunct files (`contracts/engine/features/data_provider/report/pipeline.py`) | pipeline stages of row 5 | NO | NO — folds into row 5 |
| 16 | `opening_rank1_shadow/five_session_review.py` | REPORT/VIEW | NO | NO |
| 17 | Alpha Research Board (`alpha_research_board/builder.py`) | REPORT/VIEW | NO | NO |
| 18 | Short Alpha Discriminator (`opening_policy_matrix.py` + `cohorts.py`) | REPORT/VIEW | NO | NO |
| 19 | Controlled Mock Lanes (`controlled_mock_lanes/coordinator.py` + `ledger.py`) | new evidence mechanism (real mock-broker order submission) | YES | AMBIGUOUS — see Table D |
| 20 | Opening Rank-1 Controlled Probe (`opening_rank1_controlled_probe.py`) | new evidence mechanism (distinct from row 19) | YES | AMBIGUOUS — see Table D |
| 21 | `controlled_validation_daily.py` + `controlled_mock_lane_report.py` | REPORT/VIEW over rows 19/20 | NO | NO |
| 22 | `opening_rank1_deep_dive/pipeline.py` | REPORT/VIEW (analysis) | NO | NO |
| 23 | Q13/Q14 (`q13_q14_validation.py` + `scanner_alignment_root_cause.py`) | VALIDATION/DIAGNOSTIC | NO | NO |
| 24 | Q15 (`controlled_mock_lanes/contracts.py` + `monitor_candidate_cascade.py`, no dedicated file) | POLICY/DEFENSIVE_REVIEW | NO | NO |
| 25 | Q16/Q17 (`q16_proxy_rejection_review.py`) | POLICY/DEFENSIVE_REVIEW (Q16) + VALIDATION/DIAGNOSTIC (Q17) | YES (rejected-population evidence) | NO — deliberately out of alpha scope |
| 26 | Q18 (`post_reclaim_shadow_review.py`) | EVALUATION_CONSUMER | NO | NO |
| 27 | `post_reclaim_alpha` (`evaluator.py`, base engine) | ALPHA_PROGRAM | YES | YES — BLOCKED (CANONICAL/LOSSLESS MAPPING=UNKNOWN, FIX2, Section 6) |
| 28 | `structural_alpha` (`evaluator.py`+`strategies.py`, H4/H6; H5=stub/no-evidence) | ALPHA_PROGRAM | YES | YES — BLOCKED (same, absorbs row 29) |
| 29 | `structural_alpha_batch2` (`pipeline.py`, H7-H9 — same engine as row 28) | ALPHA_PROGRAM | YES | NO — absorbs into row 28 (also BLOCKED) |
| 30 | `alpha_competition` (`evaluator.py`+`candidates.py`+`hypotheses.py`, H1-H3, fresh live fetch) | ALPHA_PROGRAM | YES | YES — BLOCKED (same, Section 6) |
| 31 | `existing_evidence_mining` (`episodes.py`+`loaders.py`, reconstructs Q9/quant-shadow candidates) | ALPHA_PROGRAM (offline/reconstructive) | YES | YES — BLOCKED (same, Section 6) |
| 32 | `rank1_feature_mart` `outcomes.py`/`builder.py`/`pipeline.py` (extended D+1..D+5 horizons) | ALPHA_PROGRAM | YES | YES — BLOCKED (LOSSLESS=UNKNOWN, Table D) |
| 33 | `rank1_feature_mart` `activation_shadow.py`/`prospective.py` | NEGATIVE_CONTROL_SHADOW / REPORT_VIEW | NO | NO — reads row 32's own `feature_mart.json` |
| 34 | `rank1_feature_mart` `strategy_choice_observation.py` | REPORT_VIEW | NO | NO |
| 35 | `horizon_revision_backtest` | EVALUATION_CONSUMER | NO | NO |
| 36 | `conditional_alpha_diagnosis` | VALIDATION/DIAGNOSTIC | NO | NO |
| 37 | `integrated_trade_diagnosis` | VALIDATION/DIAGNOSTIC | NO | NO |
| 38 | `opening_rank1_longitudinal` adjuncts (`stage_fate.py`/`universe_control.py`/`analysis.py`/`daily_provider.py`) | orchestration/reuse | NO | NO — folds into rows 10-11 |
| 39 | `evidence_ledger.py` / `strategy_feedback_builder.py` / `strategy_memory_store.py` | infrastructure/plumbing (no role assigned) | NO | NO |

**Totals (post-UEF-4B-2-FIX2)**: 39 sources · 20 primary-evidence · 19
derived-view/consumer · 15 adapter-needed CONCEPTUALLY (rows
1-5,7-11,27,28,30,31,32), split into **9 UEF-4B IMPLEMENTABLE** (rows
1-5,7,9-11, approved adapter families, Section 6 Table B) and **6
BLOCKED** (row 8 -- Q12 Calc3, CANONICAL/LOSSLESS MAPPING=UNKNOWN per
UEF-4B-2 FIX2, a proven legacy-row-count-vs-frozen-exact-grid
contradiction, narrowly reopening this one classification under
freeze-reopen case #3 -- plus rows 27,28,30,31, the dual-cost candidate
family, LOSSLESS MAPPING=UNKNOWN per UEF-4B-2 FIX1 -- plus row 32,
`rank1_feature_mart`, LOSSLESS=UNKNOWN per FIX1, unchanged) · 2
ambiguous/needs-product-decision (rows 19-20) · 22 no-adapter (including
2 absorbing rows: 6, 29). Blocked rows are never folded into the
no-adapter count -- they need an adapter conceptually, they are simply not
implementable yet.

## 6. Adapter Family Table (Table B)

**APPROVED / MAPPABLE ADAPTER FAMILIES: 5.** These are the only families
with UEF-4B implementation authority from this document:

| Adapter family | Legacy sources covered | Canonical target | Mapping confidence |
|---|---|---|---|
| `forward_measurement_adapter` | Q9 (row 1), Q10 Semiconductor Calc A/B/C (row 2, absorbs row 6/Q12-Calc1), Q10 Index Calc F/G (row 3), Opening Shadow 1A (row 9) | UEF-2A (frozen profiles #1-6,#12) → UEF-2B → UEF-3A/3B/3C | HIGH |
| `directional_shadow_adapter` | Q10 Index Calc H (row 4) | UEF-2A (frozen profile #7) → UEF-2B → UEF-3A/3B/3C | HIGH |
| `virtual_probe_adapter` | Q11 Opportunity Engine (row 5) | UEF-2A (frozen profile #8) → UEF-2B → UEF-3A/3B/3C | HIGH |
| `hypothesis_forward_adapter` | Q12 Calc2 (row 7) | UEF-2A (frozen profile #10) → UEF-2B → UEF-3A/3B/3C | HIGH |
| `already_net_shadow_adapter` | Opening Shadow 1B/1C (rows 10-11) | UEF-2A (frozen profiles #13-14) → UEF-2B → UEF-3A/3B/3C | HIGH |

**`vnext_completeness_adapter` (Q12 Calc3, row 8) was REMOVED from this
approved table under UEF-4B-2 FIX2** -- see "Blocked Family (UEF-4B-2
FIX2) -- Q12 Calc3" below. It is a candidate transformation name only,
carrying no implementation authority, exactly like the other two blocked
candidates.

**BLOCKED ADAPTER FAMILY CANDIDATES: 3.** None carries UEF-4B
implementation authority. All remain PRIMARY EVIDENCE=YES; none is
discarded or demoted to consumer/derived-view -- see the write-ups
below.

| Candidate name (not an approved family) | Legacy sources | Status |
|---|---|---|
| `vnext_completeness_adapter` (candidate transformation name only, UEF-4B-2 FIX2) | Q12 Calc3 (row 8) | PRIMARY EVIDENCE=YES · CANONICAL MAPPING=UNKNOWN · LOSSLESS MAPPING=UNKNOWN · UEF-4B=BLOCKED |
| `dual_cost_variant_forward_adapter` (candidate transformation name only, FIX2-corrected) | `post_reclaim_alpha` (row 27, base), `structural_alpha` (row 28, absorbs row 29), `alpha_competition` (row 30), `existing_evidence_mining` (row 31) | PRIMARY EVIDENCE=YES · CANONICAL MAPPING=UNKNOWN · LOSSLESS MAPPING=UNKNOWN · UEF-4B=BLOCKED |
| `rank1_feature_mart` `outcomes.py` (no candidate family name assigned) | row 32 | PRIMARY EVIDENCE=YES · LOSSLESS MAPPING=UNKNOWN · UEF-4B=BLOCKED (unchanged from FIX1) |

The 5 approved families cover 9 of the 15 adapter-needed-conceptually
sources (rows 1-5,7,9-11; row 29/structural_alpha_batch2 would absorb into
row 28's candidate family if that candidate is ever approved, but is not
counted as covered while it remains blocked). Rows 8,27,28,30,31,32 are
BLOCKED, not assigned to any of the 5 approved families — see "Blocked
Family (UEF-4B-2 FIX2) -- Q12 Calc3", "Blocked Adapter Family Candidate
(FIX2)", and "Blocked Family" below. Row 14 (Q10 Index collector) remains
infrastructure feeding `forward_measurement_adapter`'s Calc F/G input, not
a family of its own.

### Blocked Family (UEF-4B-2 FIX2) — Q12 Calc3 `vnext_completeness_adapter`

**This is a candidate transformation family NAME for inventory discussion
only. It is NOT an approved adapter family and carries NO UEF-4B
implementation authority.** This entry was ADDED to this table under
UEF-4B-2 FIX2, narrowly reopening this one previously-frozen classification
under the project's freeze-reopen policy case #3 ("proven downstream
contract contradiction") -- the rest of UEF-4A's inventory is unaffected
and remains frozen as-is.

- **WHY BLOCKED**: the real legacy `libs/reporting/baseline_btc_woori_tech/
  vnext/outcomes.py::forward` gates excursion (MFE/MAE) completeness on
  `complete = len(window) == expected` -- a ROW-COUNT-only check
  (`outcomes.py:23-24`). The frozen UEF-2A profile for this family
  (`build_q12_calc3_vnext_profile`) declares
  `DataCompletenessPolicy(kind=CONTIGUOUS_INTERVAL, interval_seconds=60.0,
  require_all_expected_observations=True)`, which the frozen UEF-2B engine
  (`forward/engine.py::validate_completeness`) implements as an EXACT
  match between the observed timestamp SET and the expected grid SET --
  a strictly stronger rule than row-count alone (this stricter rule is
  itself a deliberate, already-documented UEF-2B design choice, made in an
  earlier UEF-2B fix cycle, correcting a known row-count-only weakness
  pattern -- not something newly introduced by this Calc3 investigation).
- **THE ATTEMPTED RESOLUTION AND WHY IT FAILED**: a first UEF-4B-2
  implementation pass (FIX1) argued the two rules are equivalent in
  practice, reasoning that the real shared candle-loading pipeline
  (`baseline_samsung_hynix.data_provider._normalize_rows`, reused by
  `load_woori_candles` for Calc1/Calc2/Calc3 alike) structurally
  guarantees exact-1-minute-grid alignment, so an off-grid timestamp could
  never legitimately occur. An independent audit correctly rejected this:
  absence of an observed off-grid case in this repo's own tests/artifacts
  is not a proof that the upstream feed can never produce one -- no code,
  test, or contract anywhere in `baseline_btc_woori_tech/**` (or its
  shared candle-loading dependency) POSITIVELY asserts an exact-minute-grid
  guarantee.
- **THE REPRODUCED CONTRADICTION**: a synthetic, row-count-complete,
  off-grid candle series (25 expected window rows for one horizon, all
  present, exactly one shifted 30 seconds off its canonical minute slot)
  demonstrates the actual divergence directly against both real
  functions:
  - the REAL legacy `forward()`, called directly, reports
    `path_status="COMPLETE"` with real, non-`None` `mfe_pct`/`mae_pct`;
  - the FROZEN `evaluate_forward()` (UEF-2B), fed the IDENTICAL
    translated data directly (independent of any adapter-side check),
    reports MFE/MAE as unresolved (`None`) for the same horizon --
    `gross_return` agrees between the two (the checkpoint observation
    itself, always on-grid by construction of the horizon's own fixed
    clock target, is unaffected; only the excursion/completeness verdict
    diverges).
  - See `tests/test_uef4b2_q12_adapter.py::
    test_calc3_legacy_row_count_vs_frozen_completeness_contradiction_reproducer`
    for the full, executable reproducer.
- **RESOLUTION PATH NOT TAKEN**: this document does NOT modify the frozen
  UEF-2A/2B contiguous-minute contract (it remains valid canonical
  authority), does NOT modify or strengthen the legacy candle-loading
  provider to manufacture a grid guarantee that does not verifiably exist,
  and does NOT silently drop/reject a potentially-valid off-grid legacy
  input while calling the resulting mapping "lossless". None of those
  would resolve the actual open question; they would only hide it.
- **STATUS**: PRIMARY EVIDENCE=YES (unchanged, Calc3 remains real primary
  evidence, never demoted to consumer/derived-view). ADAPTER REQUIRED
  CONCEPTUALLY=YES. CANONICAL/LOSSLESS MAPPING=UNKNOWN. UEF-4B
  IMPLEMENTATION=BLOCKED, pending a future architecture decision (e.g. a
  new, explicitly-evidenced UEF-2A completeness policy variant for this
  one family, or a product decision to exclude Calc3 from the canonical
  core entirely) that this document does not make.
- **CODE STATE**: the experimental implementation
  (`libs/reporting/evaluation/canonical/adapters/vnext_completeness_adapter.py`)
  is retained as a research/reproducer artifact only -- it exports nothing
  (`__all__ = []`) and is not part of UEF-4B-2's approved canonicalization
  path.

### Blocked Adapter Family Candidate (FIX2 correction) — `dual_cost_variant_forward_adapter`

**This is a candidate transformation family NAME for inventory discussion
only. It is NOT an approved adapter family and carries NO UEF-4B
implementation authority.** FIX1 incorrectly classified this candidate as
LOSSLESS=YES/ready for UEF-4B; this section corrects that under the
independent audit's HIGH finding.

Per this task's Section 14 requirement (document, do not implement, a new
family only if canonical transformation semantics materially differ from
all existing six):

- **NAME**: `dual_cost_variant_forward_adapter`
- **SOURCE FAMILIES**: `post_reclaim_alpha` (base engine), `structural_alpha`
  + `structural_alpha_batch2` (one family, two candidate batches),
  `alpha_competition`, `existing_evidence_mining` — 5 directories, all
  calling the identical `post_reclaim_alpha/evaluator.py::evaluate_episodes`/
  `_checkpoint` function (confirmed by direct import in every case, not
  independently reimplemented)
- **WHY THE EXISTING SIX ARE INSUFFICIENT**: every one of the six assumes
  AT MOST one net-of-cost figure per gross observation.
  `hypothesis_forward_adapter` is the closest shape (gross+net in one
  dict, relative-minute horizons+EOD) but only carries ONE net field. This
  engine populates gross_return_pct plus **TWO** parallel net-of-cost
  fields from ONE gross figure in the SAME result —
  `live_net_return_pct = gross - LIVE_COST_PCT` (0.28) and
  `mock_net_return_pct = gross - MOCK_COST_PCT` (1.086849) — a shape none
  of the six anticipate.
- **EXACT TRANSFORMATION DIFFERENCE**: one checkpoint computation produces
  one `gross_return_pct` and TWO independently-named cost-policy
  applications against it (a "live" execution-cost assumption and a
  "mock"/paper-trading-cost assumption), alongside a shared MFE/MAE
  excursion pair computed once. Population/reference-resolution
  mechanics differ per source directory (externally pre-resolved baseline
  for `post_reclaim_alpha`/`existing_evidence_mining`; locally-resolved
  first-candle-after-decision for `structural_alpha`; fresh live-fetched
  candles for `alpha_competition`) but the checkpoint/cost/excursion core
  is byte-identical across all five.
- **CANONICAL TARGET**: **UNRESOLVED.** Would be UEF-2A (a new
  `ForwardPolicy` profile, not yet written) → UEF-2B (frozen engine,
  consumed generically, no change needed) → UEF-3A/3B/3C, but the UEF-3A
  leg has no representable shape for this source today — see LOSSLESS
  MAPPING.
- **LOSSLESS MAPPING**: **UNKNOWN — BLOCKED. (FIX2 correction: this was
  incorrectly recorded as YES under FIX1; that claim is withdrawn.)**
  FIX1's reasoning proposed constructing MULTIPLE independent
  `NetReturnRecord`s from one shared `gross_return`, each via an explicit
  `CostPolicy` (a "live" policy with provenance `LIVE_COST_PCT`, a separate
  "mock" policy with provenance `MOCK_COST_PCT`), each reaching
  `NetReturnComputationStatus.COMPUTED`. Re-reading the actual frozen
  contract shows this is invalid:
  - The source's own `live_net_return_pct`/`mock_net_return_pct` are
    **already net** figures the source itself computed
    (`SourceResultCostSemantics.NET_OR_COST_INCLUDED` — confirmed above,
    "SOURCE RESULT COST SEMANTICS"). Per `NetReturnComputationStatus`'s own
    frozen docstring, a `NET_OR_COST_INCLUDED` source can only ever reach
    `SOURCE_PROVIDED`, **never** `COMPUTED`
    (`libs/reporting/evaluation/canonical/metrics/contracts.py:161-178`).
  - `calculate_net_return()` enforces this structurally, not just by
    docstring: for `source_cost_semantics is NET_OR_COST_INCLUDED` it
    executes `_require(cost_policy is None, "...reapplying a cost to an
    already-net/cost-included source would double-count it")`
    (`libs/reporting/evaluation/canonical/metrics/engine.py:186-188`). Any
    adapter that supplies a `CostPolicy` for this source — exactly what
    FIX1 proposed — is rejected at runtime by the frozen engine itself.
  - Constructing a `COMPUTED` `NetReturnRecord` here would therefore
    require reinterpreting a `SOURCE_PROVIDED` figure as `GROSS_ONLY`, i.e.
    treating `live_net_return_pct`/`mock_net_return_pct` as if they were
    the raw `gross_return_pct` and subtracting a `CostPolicy`-derived cost
    a SECOND time — a double-count, and exactly the
    "`SOURCE_PROVIDED` reinterpreted as `COMPUTED`" move this task's own
    acceptance gate forbids.
  - No mechanism in the current frozen UEF-3A contract represents "one
    gross observation feeding two independently-provenanced,
    already-net/`SOURCE_PROVIDED` figures" as two records without either
    double-counting cost or discarding one of the two named variants. This
    is a genuine frozen-contract gap, not an adapter-implementation detail.
  - **No frozen-core change is proposed to close this gap** (forbidden by
    this task, item 6). The family therefore stays **BLOCKED** until either
    a future frozen-core-compatible extension is designed, or a narrower
    product decision (e.g. treating the two variants as two separate
    `SamplePopulation`s, each `SOURCE_PROVIDED`, with no `CostPolicy`
    involved at all) is made outside this document.
- **UEF-4B STATUS**: BLOCKED. `ADAPTER REQUIRED CONCEPTUALLY = YES`,
  `UEF-4B IMPLEMENTABLE = NO`. PRIMARY EVIDENCE remains YES for all five
  source directories — this is an EVIDENCE FAMILY KNOWN, CANONICALIZATION
  BLOCKED situation, not a demotion to consumer/derived-view/retired.

### Blocked Family (FIX1) — `rank1_feature_mart` `outcomes.py`

- **STATUS**: PRIMARY EVIDENCE=YES, ADAPTER REQUIRED=YES, but **LOSSLESS
  MAPPING=UNKNOWN → explicitly BLOCKED from UEF-4B** per this document's
  own policy (do not force-fit an uncertain shape, do not use it to
  justify a frozen-core change).
- **WHY UNKNOWN, NOT NO OR YES**: this family's horizon set mixes
  intraday relative-minute labels (`5/15/30/60/120/180` min, `EOD`,
  `NEXT_OPEN`) with multi-CALENDAR-DAY labels (`D+1_30m`, `D+1_EOD`,
  `D+2_EOD`, `D+3_EOD`, `D+5_EOD`) in ONE checkpoint set — a combination
  no other family in this inventory exhibits (Opening Shadow 1C's
  `d1`/`d3`/`d5` is a pure forward-SESSION-count scheme with no intraday
  mixing). It also has a fallback-to-upstream-field mechanic
  (`outcomes.py:84-85,98,142`) when its own raw-bar computation cannot
  resolve a value — self-computed PRIMARY with a read-from-elsewhere
  FALLBACK, a hybrid no other family's contract anticipates. This document
  could not fully confirm from source reading alone whether a separate
  `gross_return_pct` field co-exists alongside the single `_net()` output
  in every checkpoint (which determines whether `already_net_shadow_adapter`
  or a new family shape applies), nor how often the fallback path fires in
  real artifacts (would require reading an actual `feature_mart.json`
  sample, not just source).
- **REQUIRED TO RESOLVE**: a follow-up read of one real `feature_mart.json`
  artifact plus a line-by-line read of `outcomes.py`'s full
  checkpoint-construction code (this pass confirmed the net-computation
  core but not every field). Not scheduled as part of this FIX1 pass —
  explicitly left open per this task's own "do not force a fit" and "block
  rather than resolve by guessing" instructions.

## 7. Consumer/Report-Only Table (Table C)

| Legacy source | Reason (no adapter) | Future owner |
|---|---|---|
| Q8 (row 12, 5 files) | Reads other evaluators' already-computed artifacts; report/policy/diagnostic roles only, own zero primary evidence | its own maintainers; underlying evidence already owned by row 2's adapter |
| Samsung/Hynix comparison (row 13) | Compares Q9's log against a baseline computed elsewhere; generates no new observation | folds into rows 1/2's adapters |
| Opportunity Engine adjuncts (row 15) | Pipeline stages of row 5, not a separate evidence source | row 5's adapter owner |
| `five_session_review.py` (row 16) | Fixed-window promotion-gate verdict over already-computed summaries | Opening Shadow adapter owner (rows 9-11) |
| Alpha Research Board (row 17) | Explicit self-declared purpose: "consolidate existing evidence; do not rerun broad historical mining" | report/dashboard maintainers, reads post-UEF-3C aggregates once available |
| Short Alpha Discriminator (row 18) | Join + cohort statistics over already-computed Opening episodes | Opening Shadow adapter owner |
| Controlled validation/report (row 21) | Reconciliation report over rows 19/20's ledgers | whoever resolves rows 19/20 in Table D |
| Opening Rank-1 Deep Dive (row 22) | Re-report/microstructure analysis over already-collected episode data | research consumers, no adapter |
| Q13/Q14 (row 23) | Explicit `"decision_scope": "diagnostic_stability_only"`, `"behavior_patch_authorized": False` | diagnostic-suite maintainers |
| Q15 (row 24) | Live gate/policy, not an evaluation artifact producer | risk/policy maintainers |
| Q16/Q17 (row 25) | Real evidence, but of the rejected/cost-filtered population for a defensive retain/rollback decision — deliberately excluded from the alpha-comparison canonical core to avoid promoting a policy review into a strategy lane | defensive-policy maintainers; revisit only if a policy-evidence canonical track is explicitly requested |
| Q18 (row 26) | Reads Q8's already-aggregated summary for one named profile; closed "RETAIN SHADOW", not promoted | closed; no further action expected |
| `rank1_feature_mart` `activation_shadow.py`/`prospective.py` (row 33) | Read row 32's own `feature_mart.json` checkpoints; compute no new price/return figure | future owner of row 32's adapter, once row 32 is resolved |
| `rank1_feature_mart` `strategy_choice_observation.py` (row 34) | Playbook/tactic-selection alignment tagging only; zero price/return fields in the file | reporting maintainers |
| `horizon_revision_backtest` (row 35) | Re-buckets an already-completed trade's own recorded checkpoint prices under alternate horizon labels; `behavior_effect="offline_evaluation_only"` | diagnostic-suite maintainers |
| `conditional_alpha_diagnosis` (row 36) | Reads 3 pre-existing evaluated artifacts (incl. row 35's own output file); selects already-computed fields, computes no new price delta; `behavior_effect="NONE_OFFLINE_RESEARCH_ONLY"` | diagnostic-suite maintainers |
| `integrated_trade_diagnosis` (row 37) | Lineage/policy-counterfactual cross-reference over already-recorded trade/shadow outcomes; every return figure traces to an artifact another family produced | diagnostic-suite maintainers |
| `opening_rank1_longitudinal` adjuncts (row 38) | Invoke the already-classified Opening Shadow 1B/1C evaluator on more symbols/the full universe; define no second return formula | Opening Shadow adapter owner (rows 10-11) |
| Research infrastructure/plumbing (row 39) | Append-only logging, qualitative feedback aggregation (`performance_metric_usable: False`), and feedback persistence/query — no price/return computation anywhere | infra maintainers |

## 8. Special Attention -- Opening Alpha vs Scanner Rank-1 (Item 14)

Directly re-derived from source (not from the pre-existing
`docs/research/q11_opening_alpha_current_state_review.md` doc, though that
doc corroborates it):

- **No dedicated "Opening Alpha" strategy/signal-generation code exists.**
  `libs/strategy/` does not exist in this repo; no `hypothesis_id`-like field
  is ever set to a literal `"OPENING_ALPHA"` anywhere. Candidate selection is
  100% the generic Scanner's own rank-1 output (`opening_rank1_controlled_probe.py:500`
  `reject("scanner_rank1_required")`).
- **"Opening Alpha" is a human-readable LABEL, not a module name.** It
  appears as field/path/schema names inside the controlled-probe module
  (`classify_opening_alpha_condition`, `DEFAULT_OBSERVATION_ROOT =
  Path("data/logs/opening_alpha_rank_observations")`), in reporting/
  aggregation code (`controlled_validation_daily.py:138`,
  `five_session_review.py:97,175-176`, `opening_policy_matrix.py:104`,
  `cohorts.py:63`), and extensively in docs -- never as a `hypothesis_id`
  literal, never as independent signal-generation code.
- **BUT execution/eligibility logic for the controlled probe IS genuinely
  distinct and real** -- `opening_rank1_controlled_probe.py` is a dedicated,
  LIVE-WIRED gate+ledger+price-guard (`graphs/nodes/monitor_node.py:899-964`,
  `graphs/nodes/execute_from_packet.py:3530-3641`) with its own reject-chain
  and daily cap. It contains NO broker/order-submission code itself (grep
  for `Executor|broker|submit_order|place_order` = zero matches) -- when
  applied, it flips the SAME generic entry-trigger fields any normal Monitor
  entry sets, then the ACTUAL broker call happens later via the identical
  `execute_owned_order(...)` every other lane (Q10/Q12) uses. It is a real
  eligibility/sizing/price-guard gate riding the shared execution pipeline,
  not a separate order-execution mechanism.
- **Direct answer to item 14's question**: BOTH are true, at different
  layers, and this does not fully resolve to one side --
  - candidate SELECTION: NOT distinct (100% generic scanner rank-1);
  - execution/ELIGIBILITY logic: genuinely distinct and real (the
    controlled-probe gate);
  - REPORTING attribution: the label "Opening Alpha" is applied across (at
    least) four layers -- shadow observation (1A/1B/1C), the controlled
    probe, the short-alpha-discriminator matrix, and the Alpha Research
    Board -- that all trace back to the same rank-1 episode stream but
    represent DIFFERENT SUBSETS (all rank-1 sightings vs. only the <=1/day
    executed probe). **This is the actual, code-confirmed source of the
    known reporting-attribution confusion**: no single normalized function
    resolves "the Opening Alpha number" -- which subset a given report means
    depends on which of the four layers produced it.
- **Confidence: HIGH** on the code-traced facts above; the ambiguity itself
  (which subset a report means) is inherent to the legacy artifacts, not a
  gap in this research.

## 9. Ambiguities/Blockers (Table D)

| Source | Ambiguity | Risk | Required decision |
|---|---|---|---|
| Q10 Semiconductor (row 2) | Real aggregator computes THREE overlapping views over one population (`top1` rank==1 only, `both_symbol_average`, `eligible_entries`) — not one canonical `SamplePopulation` | Picking the wrong view (or silently only one) as "the" canonical population would silently drop or double-count real evaluated candidates | UEF-4B must explicitly decide: one canonical view, or 3 separate `MetricAggregationContext`s sharing one horizon. NOT a UEF defect — a real legacy multiplicity. |
| Q10 Index Calc F/G (row 3) | **RESOLVED (UEF-4B-4)**: F and G are one adapter module (`q10_index_reaction_adapter.py`) over two disjoint physical populations (stock vs. index targets) sharing one algorithm (`reaction_reader.py`) — G's richer 3-state (ABSENT/INVALID/VERIFIED) missing taxonomy is preserved as an adapter-local, SOURCE-PROVIDED completeness classification, never merged into F's population nor treated as a second view of the same physical sample | (historical) merging prematurely could have lost G's richer evidence-verification state; splitting unnecessarily would have duplicated adapter logic | Closed — no further decision needed |
| Opening Alpha attribution (Section 8) | (At least) 4 layers — Shadow 1A/1B/1C, Controlled Probe, Short Alpha Discriminator, Alpha Research Board — all label output "Opening Alpha" while covering different subsets of the same rank-1 stream; no single function resolves "the Opening Alpha number" | Continuing to report without disambiguation perpetuates exactly the attribution confusion this task called out | Any UEF-4B/reporting work touching "Opening Alpha" must state EXPLICITLY which of the 4 layers/subsets it means; recommend a report-level rename/qualifier, not a code change here |
| Controlled Mock Lanes + Opening Rank-1 Controlled Probe (rows 19-20) | Both submit real orders through the live execution path against a mock broker and record real (mock) outcomes — genuine primary evidence, but of a fundamentally different KIND (order-submission outcomes) than every forward-measurement family in this inventory (pure price observation, no order). Unclear whether this belongs in the UEF canonical core at all, or is already adequately served by production Executor/ledger infrastructure outside UEF's scope | Canonicalizing prematurely could pull production-execution concerns into UEF's read-only evaluation core (explicitly forbidden scope); NOT canonicalizing could leave a real evidence source permanently invisible to fair comparison | Needs an explicit product decision: (a) leave entirely outside UEF (production-execution domain), (b) canonicalize as a NEW UEF-2A `EventOrigin` variant in a future phase (not this one), or (c) treat ledger output as an already-derived, already-net "observation" feeding a `forward_measurement_adapter`-shaped input without touching order-submission semantics at all |
| Q15 (row 24) | The POLICY code (active guardrail) is unambiguous; its own retrospective "Q15 Shadow Result" evaluation exists only in doc prose, not as a checked-in evaluator | If someone later needs to re-verify Q15's shadow-evaluation claims, no code exists to re-run | Not a UEF-4B blocker (no adapter is needed for a pure gate), but flagged so a future reviewer does not assume the doc-only shadow results are independently reproducible from code today |
| **NEW (FIX1)**: `rank1_feature_mart` `outcomes.py` (row 32) | Extended D+1..D+5 multi-day horizons mixed with intraday relative-minute horizons in ONE checkpoint set, plus a self-compute-with-upstream-fallback mechanic — does not cleanly match any of the 5 approved adapter families (nor the blocked dual-cost/Calc3 candidates); exact field co-existence (gross vs. net-only per checkpoint) unconfirmed from source alone | Force-fitting into `already_net_shadow_adapter` (the closest guess) could silently misrepresent the D+N multi-day semantics or the fallback provenance; NOT canonicalizing leaves a real, self-computed evidence source unmapped | Read one real `feature_mart.json` artifact plus a full line-by-line pass of `outcomes.py` before any UEF-4B attempt on this family; explicitly BLOCKED until then (see Section 6, "Blocked Family") |
| **NEW (UEF-4B-2 FIX2)**: Q12 Calc3 `vnext/outcomes.py::forward` (row 8) | Legacy excursion completeness is ROW-COUNT-only (`complete = len(window) == expected`); the frozen UEF-2A/2B `CONTIGUOUS_INTERVAL` policy requires the actual observed timestamp SET to equal the expected grid SET exactly — a strictly stronger rule. No code/test/contract anywhere in `baseline_btc_woori_tech/**` (or its shared candle-loading dependency) positively proves these are equivalent over Calc3's real input domain — a synthetic, row-count-complete, off-grid reproducer demonstrates an actual divergence between the two (see Section 6, "Blocked Family — Q12 Calc3") | Implementing Calc3 as if row-count and exact-grid completeness were equivalent would silently misrepresent MFE/MAE for any off-grid input the real upstream feed might someday produce — undetectable without exactly this kind of reproducer | Requires a future architecture decision (new UEF-2A completeness policy variant for this one family, or a product decision to exclude Calc3 from the canonical core) — explicitly BLOCKED until then (see Section 6, "Blocked Family — Q12 Calc3") |

## 10. Recommended UEF-4B Implementation Order

Derived from semantic clarity (mapping confidence), current production
importance, evidence volume, and fair-comparison value -- not from Q-number
order:

1. **Q10 Semiconductor (Calc A/B/C)** -- HIGH confidence, largest evidence
   volume (the core Samsung/Hynix baseline), and its adapter is REUSED
   verbatim by Q12 Calc1 (row 6) -- implementing it first gives two
   programs' worth of coverage for one adapter's effort. Resolve the
   three-views ambiguity (Table D) as part of this work, not after.
2. **Q12 Calc2 (hypothesis_forward)** -- HIGH confidence, active program,
   directly builds on adapter patterns established in step 1. **Q12 Calc3
   (vnext) is explicitly EXCLUDED from this order** -- BLOCKED, LOSSLESS
   MAPPING=UNKNOWN (UEF-4B-2 FIX2; see Section 6, "Blocked Family — Q12
   Calc3"), not merely deprioritized.
3. **Opening Shadow (1A/1B/1C)** -- HIGH confidence, highest current
   production relevance (live-wired Controlled Probe touches the same
   rank-1 stream today). Implementing this family's canonical mapping is
   also the concrete first step toward resolving the Opening-Alpha
   attribution ambiguity (Table D) -- once 1A/1B/1C are canonical, reports
   can cite a canonical aggregate instead of an ambiguous legacy label.
4. **Q10 Index (Calc F/G, then Calc H)** -- HIGH confidence; sequence after
   Q10 Semiconductor/Q12 since it shares the "collector-fed baseline"
   pattern (wire in the Q10 Index observation collector, row 14, alongside
   F/G) but adds the 3-state governed missing taxonomy and H's externally-
   resolved-reference requirement, both genuinely new patterns best tackled
   once the simpler baseline pattern (step 1) is proven.
5. **Q11 Opportunity Engine** -- HIGH confidence, but virtual/shadow-only
   (no live capital), so lower urgency than the live-relevant families
   above; its EXIT-vs-forward excursion-chain distinction is a useful
   pattern to have available once needed.
6. **Q9 Horizon/Exit** -- real evidence, but the only family in
   `FRACTION` return units (every other family is `PERCENTAGE_POINTS`) and
   has NO cost/net field anywhere in source at all (an external `CostPolicy`
   must be supplied with real provenance before any net-return comparison
   is meaningful) -- lowest fair-comparison readiness of any UNBLOCKED
   family, hence last.

This order covers exactly the 5 APPROVED adapter families (Section 6,
Table B); no blocked family is sequenced into it.

**Explicitly NOT recommended for UEF-4B** (per Table C/D): Q8, Q13/Q14,
Q15, Q18 (no primary evidence); Q16/Q17 (real evidence, deliberately out of
alpha-comparison scope); Controlled Mock Lanes / Opening Rank-1 Controlled
Probe (genuine evidence, but needs an explicit product decision on whether
it belongs in UEF's canonical core at all before any implementation);
`horizon_revision_backtest`/`conditional_alpha_diagnosis`/
`integrated_trade_diagnosis`/`rank1_feature_mart`'s consumer sub-files/
`opening_rank1_longitudinal` adjuncts/research infrastructure (all
confirmed consumer/plumbing, no primary evidence -- FIX1 additions).

**BLOCKED (not merely "not recommended") -- excluded pending future
frozen-contract resolution, PRIMARY EVIDENCE=YES retained for all three**:
- **Q12 Calc3** (`vnext/outcomes.py::forward`, the `vnext_completeness_adapter`
  candidate name) -- CANONICAL/LOSSLESS MAPPING=UNKNOWN per UEF-4B-2
  FIX2, a proven legacy-row-count-vs-frozen-exact-grid completeness
  contradiction (Section 6, "Blocked Family — Q12 Calc3"). Calc1/Calc2 of
  the same Q12 program remain IMPLEMENTABLE and unaffected.
- **Dual-cost source family** (`post_reclaim_alpha`+`structural_alpha`+
  `structural_alpha_batch2`+`alpha_competition`+`existing_evidence_mining`,
  the `dual_cost_variant_forward_adapter` candidate name) -- CANONICAL/
  LOSSLESS MAPPING=UNKNOWN per the FIX2 correction (Section 6); FIX1's
  LOSSLESS=YES claim is withdrawn.
- `rank1_feature_mart` `outcomes.py` (LOSSLESS=UNKNOWN, Section 6/Table D --
  requires a follow-up artifact read before it can even be considered for a
  future order).

## 11. Explicit Non-Goals

- No adapter is implemented by this document.
- No legacy evaluator, report, or runtime file is modified.
- No frozen UEF-1..UEF-3C file is modified (verified via the freeze manifest
  before and after this work).
- No new Q number, no new lane, no new canonical semantic is introduced.
- No dedup/evidence-lineage resolution (UEF-6's future job) is performed --
  primary-vs-derived-view is IDENTIFIED here, not resolved/merged.
- No historical recompute, dual-run, or production integration.
