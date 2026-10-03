# UEF (Unified Evaluation Foundation)

## Current State

| Phase | Owns | Status |
|---|---|---|
| UEF-1 | Canonical identity and record contracts | FORMALLY FROZEN |
| UEF-2A | Forward semantics profiles and policy | FORMALLY FROZEN |
| UEF-2B | Generic forward engine | FORMALLY FROZEN |
| UEF-3A | Canonical cost and metric contract | FORMALLY FROZEN |
| UEF-3B | Canonical cost and metric engine | FORMALLY FROZEN |
| UEF-3C | Canonical aggregation pipeline | FORMALLY FROZEN |
| UEF-4A | Legacy family inventory and canonical mapping | FORMALLY FROZEN |
| UEF-4 | UEF-4B adapter/classification layer (Q9–Q12, Opening, Q10 Semi/Index) | PROVISIONALLY COMPLETE — see Current/Next |
| UEF-5.1 | Clean Evidence Registry (input-boundary gate for historical recompute) | FORMALLY FROZEN |
| UEF-5.2 | Historical Recompute (market-data authority + canonical session projection) | FORMALLY FROZEN |
| UEF-5.3 | Historical Dual Run (legacy vs. canonical comparison) | FORMALLY FROZEN |
| UEF-6 | Dedup and evidence lineage (population dedup + direct lineage sidecar + historical validation) | FORMALLY FROZEN |
| UEF-7 | Alpha Board normalization (derived comparison-ready view over Alpha Research Board v2) | FORMALLY FROZEN |
| UEF-8 | Fair comparison validation (pairwise COMPARABLE/CONDITIONAL/NOT_COMPARABLE over UEF-7) | FORMALLY FROZEN |
| UEF-9 | Formal evaluation authority (final UEF-7/UEF-8 binding + integrity verification) | FORMALLY FROZEN |

## Current / Next

**UEF-4B-1: Q10 Semiconductor Adapter — FORMALLY FROZEN** (independent Codex closure: APPROVE_UEF4B1, CRITICAL:0 HIGH:0 MEDIUM:0 LOW:0). Not to be modified again unless a reproducible correctness defect is discovered.

**UEF-4B-2: Q12 — FORMALLY CLOSED** (independent Codex closure: APPROVE_UEF4B2, FORMAL CLOSURE=YES, CRITICAL:0 HIGH:0 MEDIUM:0 LOW:0). Q12 Calc1 (reuse of the frozen UEF-4B-1 `forward_measurement_adapter` semantic layer, no new Calc1 adapter, no UEF-4B-1 file modified) and Calc2 (`hypothesis_forward_adapter.py`, `NET_OR_COST_INCLUDED`, high/low legacy fallback verified against the real legacy function directly) are **APPROVED / FROZEN**. Not to be modified again unless a reproducible correctness defect is discovered.

**Q12 Calc3 — PRIMARY / KNOWN / BLOCKED** (unchanged by this closure — never approved, never canonicalized). Real legacy `vnext/outcomes.py::forward` completeness is ROW-COUNT-only; the frozen UEF-2A/2B `CONTIGUOUS_INTERVAL` policy requires the actual observed timestamp set to equal the expected grid set exactly — a strictly stronger rule, with the divergence proven by a direct legacy-vs-frozen reproducer (`tests/test_uef4b2_q12_adapter.py::test_calc3_legacy_row_count_vs_frozen_completeness_contradiction_reproducer`). PRIMARY EVIDENCE=YES (never demoted to consumer/derived-view), CANONICAL/LOSSLESS MAPPING=UNKNOWN, UEF-4B IMPLEMENTATION=BLOCKED — see [UEF-4A legacy family inventory](../research/uef4_legacy_family_inventory.md) Section 6. The experimental `vnext_completeness_adapter.py` module remains a research/reproducer artifact only (`__all__ = []`, not exported, not part of any approved canonicalization path).

**UEF-4B-3: Opening Shadow (1A/1B/1C) — FORMALLY FROZEN** (independent Codex closure, following FIX1/FIX2 below). Opening Shadow's own 3 checkpoint calculators are UEF-4A's approved, implementable Opening-family mapping — distinct from, and never to be conflated with, the Opening Rank-1 Controlled Probe or Controlled Mock Lane (execution-outcome evidence, explicitly out of UEF-4B scope) or the generic "Opening Alpha" attribution label (a reporting label spanning multiple components, never one canonical evaluator). Not to be modified again unless a reproducible correctness contradiction is discovered.

**FIX1 (population + provenance boundary):** two independently-audited HIGH findings closed. (1) 1A's `trigger_day_integrity_status != VALID` rows now resolve to canonical `SampleMemberState.EXCLUDED`, never MISSING and never a 0-return, with full lineage preserved via a dedicated, non-canonical `OpeningShadow1AExclusion` record — matching real `build_latent_reactivation_forward`'s own `EXCLUDED_TRIGGER_DAY_INTEGRITY` behavior, which never attempts forward-price resolution for these rows either. (2) Opening Shadow ingestion became provenance-gated by persisted `schema_version`.

**FIX2 (trusted artifact ingestion + closed public API):** independent audit found FIX1's gate was schema-only (a caller-supplied `Mapping` carrying the right literal was still accepted) and that the non-VALID-1A exclusion invariant did not hold at every public boundary (`build_1a_episode` remained directly callable on a non-VALID row). Both closed architecturally: the approved ingestion path is now `canonicalize_opening_shadow_1a_artifact` / `canonicalize_opening_shadow_1bc_artifact` — each reads a real JSON file off disk and verifies BOTH its real, repo-relative artifact-family path layout (the exact path each real writer uses: `.../opening_rank1_shadow/latent_watch/latent_reactivation_forward.json`, `.../offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.json`) AND its persisted `schema_version` before canonicalizing anything; a Controlled Probe (`opening_rank1_controlled_probe.v3`) or Controlled Mock Lane (`controlled_mock_lanes.v1`) artifact is rejected by real origin even when a forged `schema_version` string is attached. The former public row/case builders (`parse_1a_candidate`, `build_1a_episode`, `parse_1bc_case`, `build_1bc_episode`) are now internal-only (`_`-prefixed, removed from `__all__`), and the internal 1A episode builder additionally rejects a non-VALID candidate defensively regardless of caller.

**1A is a genuinely DIFFERENT physical event population from 1B/1C** (verified directly against source, not inferred from naming): 1A (`opening_rank1_shadow.py`) reuses the frozen `forward_measurement_adapter` generic layer verbatim (GROSS_ONLY, same shape as Q9/Q10 Semiconductor/Q12 Calc1) over "fresh trigger" latent-reactivation events (`latent_forward.py::_observe`). **1B and 1C ARE the same physical episode** — both operate on the SAME "virtual buy" MONITOR_DECISION event (`delayed_outcomes.py::forward_30m_net`/`delayed_path`; `delayed_path` even directly consumes 1B's own `net_return_30m_pct` as an input) — merged into ONE canonical `EpisodeRecord` per (trading_date, symbol, decision_epoch) via the new `already_net_shadow_adapter.py` (`NET_OR_COST_INCLUDED`, net/MFE figures verified against the real legacy functions called directly, never recomputed). No evidence multiplication: 3 source fresh-triggers produce 3 canonical episodes (1A); one virtual-buy case produces one episode with 4 checkpoints, not three separate samples (1B/1C).

**UEF-4B-4: Q10 Index (Calc F/G/H) — FORMALLY FROZEN** (independent Codex closure, following FIX1 below). Not to be modified again unless a reproducible correctness contradiction is discovered.

**FIX1 (Calc H policy evaluation identity):** independent audit found all 5 `SHADOW_ENTRY_POLICIES` for one (day, target) collided onto the same `evaluation_subject_id`/`evaluation_record_id`, since `canonical_event_id`, `hypothesis_id`, `observation_type`, and `execution_mode` were all identical across policies. Closed by binding entry-policy into the existing, frozen `hypothesis_id` evaluation-identity dimension (`policy_hypothesis_id()`, e.g. `..._entry_0900`) — physical event identity (`canonical_event_id`) stays shared across all 5 policies for the same (day, symbol), exactly as before; only the evaluation/hypothesis layer now varies per policy. No new canonical field or id system.

**F/G ambiguity RESOLVED** (UEF-4A Table D, previously MEDIUM/unresolved): F and G are ONE source family / ONE computational algorithm (`reaction_reader.py`'s `_stock_reaction`, which `_index_reaction` thinly wraps) reused across TWO DISJOINT physical populations by target kind — stock symbols (005930, 000660) for F, index symbols (KOSPI, KOSDAQ) for G — verified directly against `build_actual_reactions()`, which iterates the same 4-entry `TARGETS` tuple and branches only on `target["kind"]`. Each (day, symbol) is its own distinct physical event; 4 targets/day produce 4 distinct canonical episodes, never merged, never multiplied. G's only genuine difference is a richer, collector-governed 3-state missing taxonomy (ABSENT/INVALID/VERIFIED, mapped to OBSERVED/PARTIAL/MISSING) for its 3 checkpoints (09:30/10:00/CLOSE) — an adapter-local missing-semantics decision, not a physical-identity difference. Calc F reuses the frozen `forward_measurement_adapter` generic layer verbatim (GROSS_ONLY, candle-driven, oracle-verified against `_stock_reaction` directly); Calc G's 3 governed checkpoints are built SOURCE-PROVIDED (verbatim from the trusted artifact's own already-resolved `points[label]`, `calculate_gross_return()` called directly rather than reimplemented) because the frozen `build_q10_index_calc_g_profile()` declares 3 duplicate-labeled `HorizonSpec`s (one per evidence-verification variant) that `build_forward_measurement_episode()` would otherwise reject as a duplicate-label misconfiguration.

**Calc H is a directional-shadow HYPOTHESIS over the SAME physical (day, symbol) observation F/G already canonicalize** (verified directly against `build_shadow_comparison`, which reads F/G's own `reactions["targets"]` dict directly, reusing its `points`/`path`/`CLOSE` verbatim) — same `canonical_event_id` as the matching F/G episode, distinct `hypothesis_id`. A NEUTRAL `expected_state` (`_direction()==0`) is the source's OWN population-exclusion rule (`q10_shadow_entry_comparison.json` never persists an outcome row for it at all) — mapped to canonical `SampleMemberState.EXCLUDED` with full lineage (`Q10IndexShadowExclusion`), mirroring Opening Shadow FIX1/FIX2's exact EXCLUDED pattern; return/excursion figures (`gross_eod_return_pct`/`net_eod_return_pct`/`mfe_pct`/`mae_pct`) are taken verbatim (irreducibly `SOURCE_PROVIDED`, `NET_OR_COST_INCLUDED`) since real `build_shadow_comparison` already resolves them, including direction adjustment and cost.

**Trusted ingestion**: `canonicalize_q10_index_calc_f_artifact`/`_g_artifact`/`_h_artifact` each verify the real, repo-relative `baseline_samsung_hynix/<day>/q10_forward_validation/` directory family layout (day validated by ISO-date shape, never a hardcoded date) AND both real persisted discriminators (`schema_version` AND `evaluation_program_id`, imported directly from `forward_validation/contracts.py`, never retyped) before parsing anything. Calc H also derives its key-to-symbol authority from the same verified `q10_actual_market_reactions.json` artifact F/G consume, not from a caller-supplied mapping. Q10 Index's real controlled-lane execution symbols (069500/114800/229200/251340, `controlled_mock_lanes/contracts.py::Q10_INDEX_SYMBOLS`) are never the same symbols these adapters read (005930/000660/KOSPI/KOSDAQ) — evaluation and execution evidence are disjoint symbol universes in the real source itself.

**UEF-4B-5: Q11 Opportunity Engine — PROVISIONALLY CLOSED / AWAITING CODEX RATIFICATION.** Not formally frozen. Legacy `opportunity_engine_virtual_trades.v1` artifacts: **PRIMARY / KNOWN / BLOCKED** for direct lossless canonicalization (observed_price never persisted for a price-based checkpoint). `.v2` artifacts (source-contract repair): **SOL PRE-AUDIT PASS** — a Claude self-PASS does not authorize freeze; only an independent Codex audit may ratify this provisional closure.

**Q11 is a self-contained research probe, not a counterfactual view over another family's event** (verified directly against source): `build_signal_timeline` generates its OWN candidate stream directly from real minute candles + real macro snapshots (`signal_id = f"OE_{day}_{symbol}_{epoch}"`, never a Scanner/Commander/Strategist decision id) — `opportunity_engine/contracts.py::PROHIBITED_RUNTIME_DEPENDENCIES` explicitly forbids the package from importing `graphs.nodes`, `libs.runtime.commander`, `libs.runtime.execution`, `libs.runtime.quant.shadow_candidates`, or even `libs.reporting.evaluation` itself — a real, deliberate architectural isolation. "Virtual" means the resulting position was never submitted to a broker (every real trade carries `order_execution_allowed: False` verbatim); "negative control" means Q11 encodes ONE fixed, always-on research rule (`strategy_id="probe_v0"`) evaluated against real market data as a baseline arm, never compared against the live strategy within this adapter (that comparison is an explicit downstream/Q100 concern). Each closed virtual position is its own sole physical event — 1 physical event = 1 canonical episode with 6 checkpoints (+5m/+15m/+30m/+60m/EOD, all `SIGNAL`-anchored, from `forward_returns`; EXIT, `ACTUAL_EXIT`-anchored, from the trade's own top-level fields) — never multiplied, never shared with another family.

**FIX1 (source evidence contract repair):** independent audit rejected the original `CheckpointMetricKind.AGGREGATE_ONLY` usage for the 5 SIGNAL-anchored forward/EOD checkpoints — these ARE genuinely anchored to one real, actually-observed candle close (`simulator.py`'s own `_forward_returns`), so `AGGREGATE_ONLY` (declared for values *not* anchored to one observed price) was an invalid workaround for a real upstream gap: the legacy artifact computed every return/MFE/MAE from a specific candle close but never persisted that price. Repaired at the SOURCE, not the adapter: `libs/research/opportunity_engine/simulator.py`'s `_forward_returns()` now additionally persists `"observed_price": close` for every OBSERVED horizon (byte-for-byte additive — no return/MFE/MAE/observed_epoch selection, rounding, or fallback logic changed); `contracts.py::TRADES_SCHEMA` bumped `opportunity_engine_virtual_trades.v1` → `.v2` to mark the real schema-shape change (`TRADES_SCHEMA_LEGACY_V1` names the superseded literal). **Legacy v1 artifacts remain real, authentic PRIMARY EVIDENCE (real origin, real `PROGRAM_ID`) but are explicitly BLOCKED from direct lossless UEF-4B canonicalization** — the trusted-ingestion gate detects an authentic v1 artifact and rejects it with the specific reason (`observed_price` never persisted for a price-based checkpoint), never a generic schema-mismatch message; v1 is never rewritten, backfilled, or mutated (historical recovery is an explicit UEF-5 Historical Recompute concern). **v2 artifacts use `CheckpointMetricKind.PRICE_BASED`** with the real, verbatim `observed_price`, verified oracle-exact against the real `simulate_probe_v0` output and against a real end-to-end run of `build_opportunity_engine_artifacts` itself.

**`virtual_probe_adapter.py`** (new family-local module, per UEF-4A's own recommendation — distinct from `forward_measurement_adapter`, which has no equivalent for Q11's EXIT checkpoint / already-net semantics): every return/excursion/timestamp/price figure is taken verbatim from the real, persisted `opportunity_engine_virtual_trades.json` v2 artifact (irreducibly `SOURCE_PROVIDED`, `NET_OR_COST_INCLUDED`) — `evaluate_forward()` is never called, mirroring the precedent Q10 Index Calc G/H already established. Trusted ingestion requires both the real, repo-relative `opportunity_engine_shadow/<day>/opportunity_engine_virtual_trades.json` path layout AND both real persisted discriminators (`schema_version`==`TRADES_SCHEMA` (v2), `evaluation_program_id`==`PROGRAM_ID`, imported directly from `opportunity_engine/contracts.py`), mirroring Q10 Index's dual-discriminator pattern. Every ingested trade must carry `order_execution_allowed: False` explicitly — missing or `True` is rejected outright, never assumed.

**UEF-4B-6: Q9 Horizon/Exit — PRIMARY / KNOWN / BLOCKED.** Not formally frozen, not an approved canonical path. Q9 is the ONE UEF-4B family genuinely anchored to the live strategy's own REAL, actually-executed exit (`EventOrigin.ACTUAL_EXIT`) — a real realized trade IS legitimate Q9 source lineage — but this module's entire input surface is the trusted `post_exit_shadow_recap.json` artifact's own `trades[]` list (`trade_id`/`symbol`/`post_exit_shadow` only); it never reads `ai_trade_report.json`/`lifecycle_bundle.json`/any execution-detail artifact directly, so broker mechanics (order submission, ACK, fill fragments, retries, reconciliation) are structurally unreachable, never merely asserted excluded. Real source verified directly: `strategy_horizon_feedback.py::update_post_exit_shadow_with_price_observations` computes `+5m/+15m/+30m/+60m/EOD` from a real 4-deep price alias chain (`filled_price`→`current_price`→`price`→`avg_price` for `exit_price`; `close`→`price`→`current_price`→`cur_price` per checkpoint), `ReturnUnit.FRACTION` (never `*100`), `GROSS_ONLY` (no net/cost field exists in source at all). **The session-close fallback the frozen profile declares (`MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK`) is REAL, not aspirational**: `post_exit_shadow_recap.py::_fill_regular_close_bound_pending_checkpoints` substitutes the EOD checkpoint's own observed price/timestamp into any intraday checkpoint whose target falls after the regular 15:30 KST close — verified oracle-exact. **FIX1 (observation identity closure):** the canonical event is `ObservationType.EXIT_EVENT`, not `SHADOW_ENTRY` (no synthetic/simulated position exists in Q9's real evidence) and not `ACTUAL_TRADE` (the trusted artifact carries no entry_time/entry_price at all, and reading one from `ai_trade_report.json` would cross the broker-mechanics boundary above) — see `q9_horizon_exit_adapter.py::build_q9_episode` for the full source-grounded proof. **BLOCKED (not fabricated):** the real 4-deep `exit_price` alias chain resolves to a single number with NO persisted record of which alias fired, so `exit_price_authority` cannot be reconstructed losslessly — no existing `EntryAuthority` value represents this without inventing a specific, unverifiable claim (claiming `BROKER_FILL`/`MOCK_FILL` would assert a confirmed fill 2 of the 4 real branches never provide). **PRIMARY EVIDENCE=YES, KNOWN=YES, EXIT PRICE VALUE=LOSSLESS, EXIT PRICE AUTHORITY=NOT PERSISTED, DIRECT LOSSLESS UEF-4 MAPPING=NO, STATUS=PRIMARY/KNOWN/BLOCKED.** `q9_horizon_exit_adapter.py` is retained only as a research/reproducer candidate (`__all__ = []`, not exported, not part of any approved canonicalization path — matching the `vnext_completeness_adapter`/Q12-Calc3 precedent); a future, explicitly-authorized versioned source-contract change persisting which alias resolved `exit_price` is the identified repair candidate, not performed here.

**UEF-5.1: Clean Evidence Registry — FORMALLY FROZEN** (independent Codex closure after FIX1: APPROVE,
FORMAL FREEZE YES, READY_FOR_UEF5_2 YES; one non-blocking MEDIUM on the Incident C 75.47% vs 44.67%
numeric discrepancy, intentionally left unresolved). Frozen at commit `b2efd84`. The mandatory input
boundary for UEF-5 historical recompute: `CLEAN`/`QUARANTINED`/`FIELD_INVALID`/`REVIEW_REQUIRED`/`NO_RULE`,
with `MATCHED CLEAN DOMAIN != CLEAN` (positive clean authority requires a matched candidate domain, a
`PROVEN_CLEAN` verifier result, every declared check passed, and no negative rule match at file or record
level). See [Clean Evidence Registry](../research/uef5_1_clean_evidence_registry.md).

**UEF-5.2: Historical Recompute — FORMALLY FROZEN** (independent Codex closure audit after Implementation
Correction 1: CRITICAL 0, HIGH 0, MEDIUM 1, LOW 0; `APPROVE_UEF5_2`, `FORMAL_FREEZE: YES`). Deterministic,
offline recompute of UEF-5.1-CLEAN evidence through the frozen canonical layer and approved UEF-4
adapters — no legacy comparison, no parity claim (that is UEF-5.3). Candle admission requires a verified,
acquisition-issued `MarketDataReceipt` (never a caller-supplied trust flag); a separate, UEF-owned
`SessionPolicy` projects admitted candles to the canonical 09:00–15:30 KST regular session before any
frozen adapter call; the run identity binds a bounded, explicit semantic implementation manifest plus the
effective run configuration. One non-blocking debt item is recorded (`UEF5_2_DEBT_001`, acquisition-
lifecycle stage ordering; authority corruption NOT reproduced). See
[Historical Recompute](../research/uef5_2_historical_recompute.md) and
[ADR-0003](../decisions/ADR-0003_UEF5_2_Market_Data_Authority_and_Recompute_Identity.md).

**UEF-5.3: Historical Dual Run — FORMALLY FROZEN** (independent Codex final closure audit: CRITICAL 0,
HIGH 0, MEDIUM 0, LOW 0; `CORE_VERDICT: APPROVE_CORE`, `UEF5_3_COMPLETE: YES`). Compares legacy (pre-UEF)
evaluation outputs against UEF-5.2's canonical output for the same historical evidence and classifies
every material difference through a bounded taxonomy — never converts an undefined legacy metric into a
fake zero, never lets a non-comparable metric suppress a comparable one, and gates any numeric comparison
on a positively-proven population identity (never count equality alone). Final audited real run
`UEF53DUAL_5e22b07eb2a62894`: 4359 total comparison units, 0 unexplained divergences, 0 unaccounted, 0
collisions. Real non-empty parity evidence is limited to Q11 EXIT (3 units, profit_factor and
population counts matching; MDD parity explicitly NOT_ESTABLISHED, since legacy has no MDD figure at
all); Q12 Calc1 numeric comparison is 0 today by correct, fail-closed design (legacy member identities
unavailable — see the freeze record for the exact reactivation condition). Q10 Index and Q12 Calc2 remain
`NON_COMPARABLE_CONFIRMED` / `NO_COMPARABLE_LEGACY_DAILY_AGGREGATE` (no new legacy aggregator invented).
One non-blocking debt item is recorded (`UEF5_3_DEBT_001`, live-ledger hashing test/observability
efficiency, not a correctness or freeze blocker). See
[Historical Dual Run](../research/uef5_3_historical_dual_run.md).

**UEF-6: Dedup & Evidence Lineage — FORMALLY FROZEN** (independent Codex final closure audit: CRITICAL 0,
HIGH 0, MEDIUM 0, LOW 0; `CORE_VERDICT: APPROVE_UEF6`, `UEF6_COMPLETE: YES`, `UEF6_FORMAL_FREEZE: YES`).
UEF-6A (population dedup detection, reusing the frozen UEF-1 identity model verbatim, no new duplicate-
relation authority), UEF-6B (direct evidence-lineage sidecar over the frozen `aggregate_canonical_samples()`,
called exactly once, never reconstructing membership heuristically), and UEF-6C (historical dedup + direct-
lineage validation: Mode A frozen-output observation, Mode B instrumented replay over an isolated, byte-
verified snapshot) are all **APPROVED / COMPLETE**. Checkpoint commits: UEF-6A `ab699bb`, UEF-6B `b1dbe5e`,
UEF-6C `657ddaa`. Real Mode A run against `UEF5RUN_bc1e299667c2ca94b977` reproduces the audited baseline
exactly (107 raw / 80 events / 107 subjects / 107 records / 0 duplicates / 6 multi-evaluation events / 75
LEGITIMATE_MULTI_HYPOTHESIS pairs). Real Mode B for that same target run is `NOT_REPRODUCIBLE` (one
discovered input artifact's current bytes no longer match its historically recorded sha256, and no
authoritative exact-byte archive was found) — non-blocking for this freeze, since fail-closed behavior
under an unrecoverable byte mismatch is the correct contract; no lineage was fabricated and no approximate
replay was accepted. Final regression: UEF-6A 22 + UEF-6B 14 + UEF-6C 28 = 64 passed. See
[UEF-6 Dedup & Evidence Lineage Freeze](../research/uef6_dedup_evidence_lineage_freeze.md).

**UEF-7: Alpha Board Normalization — FORMALLY FROZEN** (independent Codex final closure audit: CRITICAL 0,
HIGH 0, MEDIUM 0, LOW 0; `CORE_VERDICT: APPROVE_UEF7`, `UEF7_COMPLETE: YES`, `UEF7_FORMAL_FREEZE: YES`).
Produces one deterministic, comparison-ready normalized view over the frozen Alpha Research Board v2 —
never adds a field to its frozen `ROW_COLUMNS`, never calls `canonicalize_board()`/`build_alpha_research_board()`
differently, never mutates a candidate row/metric/decision/promotion state. Candidate row != independent
evidence population, and same/different source provenance != proven same/independent population —
`population_identity_status` stays `NOT_PROVABLE_FROM_ALPHA_BOARD_V2` for all 14 real candidates (no
evidence-independence count ever invented). Full four-field `SourceReference` identity
(`source_key`+`path`+`available`+`error`) is the one shared authority for source-overlap grouping and
multiset-sensitive `source_bundle_id`; the frozen, imported `ROW_COLUMNS` (never the board's own
published field) is the sole candidate-row trust root, closing an adversarial-input trust-chain gap found
during bounded audit. No ranking/score/promotion/strategy change of any kind. Checkpoint commit `cc7fb4b`.
Real board (`through_day=2026-09-25`): 14 candidate rows, 5 shared-source groups (`btc_woori_history`,
`feature_candidates`, `opening_cumulative`, `prospective_candidates`, `short_alpha_discriminator`), 10
rows with shared source, 0 proven population groups, 14 unresolved population candidates — all derived
dynamically, none hardcoded. Final regression: UEF-7 38 + Alpha Board 36 + UEF-6A 22 + UEF-6B 14 + UEF-6C
28 = 138 passed. See [UEF-7 Alpha Board Normalization Freeze](../research/uef7_alpha_board_normalization_freeze.md).

**UEF-8: Fair Comparison Validation — FORMALLY FROZEN** (independent final closure audit: CRITICAL 0, HIGH
0, MEDIUM 0, LOW 0; `CORE_VERDICT: APPROVE_UEF8`, `UEF8_COMPLETE: YES`, `UEF8_FORMAL_FREEZE: YES`).
Determines, for every unordered pair of frozen UEF-7 normalized candidate rows, whether the pair is
`COMPARABLE`, `CONDITIONAL`, or `NOT_COMPARABLE` — never which candidate is better. Core invariant:
individual UEF-7 `population_identity_status` proof on both sides of a pair never establishes the pair's
own population RELATION — the frozen `uef7.alpha_board_normalization.v1` schema exposes no pairwise
population-relation field at all, so `POPULATION_RELATION_NOT_PROVEN` is unconditional and
`COMPARABLE_REACHABLE_WITH_CURRENT_UEF7_SCHEMA: NO` is a schema-contract property, not merely today's data
— `COMPARABLE` remains reserved for a future explicitly frozen upstream authority extension, never
invented by UEF-8 itself. `comparison_pair_id` is a SHA-256 digest over the canonical ordered candidate
pair (never delimiter concatenation, which could collide across adversarial candidate-id shapes), with a
fail-closed collision guard requiring pair_count == unique pair ids == unique canonical pair tuples. Hard
scope blockers (different question/horizon/cohort/no shared outcome metric) force `NOT_COMPARABLE`;
metric-availability mismatch, unresolved sample accounting, unproven population relation, and shared
source provenance keep an otherwise-aligned pair `CONDITIONAL` — shared/different source provenance is
descriptive only, never population authority in either direction. No ranking/score/promotion/strategy
change of any kind. Checkpoint commit `b91d926`. Real board (`through_day=2026-09-25`): 14 candidates, 91
pairs, 0 COMPARABLE / 7 CONDITIONAL / 84 NOT_COMPARABLE, 91 unique pair ids,
`POPULATION_RELATION_NOT_PROVEN=91` — all derived dynamically, none hardcoded. Final regression: UEF-8 41
+ UEF-7 38 = 79 passed. See [UEF-8 Fair Comparison Validation Freeze](../research/uef8_fair_comparison_validation_freeze.md).

**UEF-9: Formal Evaluation Authority — FORMALLY FROZEN** (independent final closure audit: CRITICAL 0,
HIGH 0, MEDIUM 0, LOW 0; `CORE_VERDICT: APPROVE_UEF9`, `UEF9_COMPLETE: YES`, `UEF9_FORMAL_FREEZE: YES`,
`UEF_COMPLETE: YES`). The FINAL UEF stage — binds the already-frozen UEF-7 candidate-level facts and UEF-8
pairwise comparison-validity facts into one final, fail-closed authority contract, without evaluating
strategies again, ranking candidates, recomputing metrics, or reopening raw evidence. Proves UEF-8's
result genuinely belongs to the supplied UEF-7 result (run-id and normalized-rows-digest binding),
conserves the exact candidate universe and the full `N*(N-1)/2` pair universe (unique semantic pairs and
unique `comparison_pair_id`s), conserves `COMPARABLE+CONDITIONAL+NOT_COMPARABLE == pair_count`, and
detects a current-schema capability contradiction (`COMPARABLE>0` while the frozen schema declares it
unreachable) — any contradiction raises `UEF9AuthorityError` and fails closed; `authority_status` is
exactly `VALID` or a raised error, never a partial-valid or confidence-scored state. Freezes the explicit
authority limitation that individual UEF-7 population proof is not pairwise population relation proof, so
`COMPARABLE_REACHABLE_WITH_CURRENT_UEF7_SCHEMA: NO` remains the frozen current-schema contract. UEF-8
exposes no native semantic digest of its own comparison results, so UEF-9 computes its own local
binding/integrity digest over the supplied UEF-8 object — explicitly never relabeled as a native UEF-8
digest. No ranking/promotion/trading authority of any kind. Checkpoint commit `608ddff`. Real authority
(`through_day=2026-09-25`): 14 candidates, 91 pairs, 0 COMPARABLE / 7 CONDITIONAL / 84 NOT_COMPARABLE,
`authority_status=VALID` — all derived dynamically, none hardcoded. Final regression: UEF-9 20 + UEF-8 41
+ UEF-7 38 = 99 passed. See [UEF-9 Formal Evaluation Authority Freeze](../research/uef9_formal_evaluation_authority_freeze.md).

════════════════════════════════════════════════════════════════════════
**UEF COMPLETE.** UEF-1 through UEF-9 are all FORMALLY FROZEN. Final authority ownership: candidate
evaluation facts (UEF-7), pairwise comparison-validity facts (UEF-8), final authority binding (UEF-9).
**NEXT: Strategy Program Integration** — not "UEF-10"; UEF remains frozen as the evaluation-authority
foundation underneath it. Not started by this closure.

## Post-Freeze Operations

- **P1.1 Real-Run Acceptance: PASS.** The frozen UEF-7 to UEF-8 to UEF-9 chain was verified against one
  current real Alpha Board capture. See [P1.1 real-run acceptance](../research/uef_p1_1_real_run_acceptance.md).
- **P1.2 Cross-day Observation: BLOCKED / IDEMPOTENCY REPAIR REQUIRED.** The registered daily task
  successfully published the first 2026-09-30 COMPLETE authority and exactly one registry observation.
  Its same-day retry then created a different COMPLETE generation and advanced current/latest before the
  registry rejected the conflicting authority. Source freshness remains fail-closed, but deterministic
  same-authority replay must be repaired before P1.2 can close. This does not alter frozen UEF semantics.
- **Current execution priority: P1.3 Docker.** Strategy Program Integration remains P2. This current
  roadmap priority does not rewrite the historical next-action statements in frozen records.

### Current Authority Summary

```
candidate evaluation authority       -> UEF-7
pairwise comparison authority        -> UEF-8
final evaluation binding             -> UEF-9

ranking authority                    -> NONE
promotion authority                  -> NONE
trading authority                    -> NONE
```

`COMPARABLE_REACHABLE_WITH_CURRENT_UEF7_SCHEMA: NO` remains a frozen current-schema limitation because
the UEF-7 schema has no pairwise population-relation authority. It is not a Docker blocker.
════════════════════════════════════════════════════════════════════════

**UEF-4 CONSOLIDATED PROVISIONAL CLOSURE.** All six UEF-4B families have completed implementation/classification work. Five are formally frozen or formally closed (Q10 Semiconductor, Q12 Calc1/Calc2, Opening Shadow, Q10 Index) or provisionally closed pending ratification (Q11); Q9 and Q12 Calc3 are classified **PRIMARY / KNOWN / BLOCKED** — known, intentional closure outcomes, not unfinished hidden work. **UEF-4 IMPLEMENTATION/CLASSIFICATION: COMPLETE. UEF-4 FORMALLY FROZEN: NO. UEF-4 PROVISIONALLY COMPLETE: YES.** No family in this phase is formally frozen by self-assessment alone; final ratification (Q11, and any future Q9/Calc3 repair) is an independent Codex audit matter. The next planned phase is **UEF-5 Historical Recompute & Dual Run — NOT STARTED.**

UEF-4A classifies 39 sources: 20 primary-evidence sources and 19 derived or consumer sources. Five adapter families are approved for implementation; Q9 and Q12 Calc3's candidate adapters are BLOCKED, not counted among them. The authoritative inventory and all mapping constraints remain in [UEF-4A legacy family inventory](../research/uef4_legacy_family_inventory.md).

### UEF-4B Order

1. Q10 Semiconductor - FORMALLY FROZEN
2. Q12 Calc1 / Calc2 - APPROVED / FROZEN (Q12 Calc3 - PRIMARY / KNOWN / BLOCKED)
3. Opening Shadow (1A/1B/1C) - FORMALLY FROZEN
4. Q10 Index (Calc F/G/H) - FORMALLY FROZEN
5. Q11 - PROVISIONALLY CLOSED / AWAITING CODEX RATIFICATION (legacy v1 artifacts: PRIMARY / KNOWN / BLOCKED for direct lossless canonicalization; v2 artifacts: SOL PRE-AUDIT PASS)
6. Q9 - PRIMARY / KNOWN / BLOCKED (exit_price authority provenance not persisted)

### Blocked / Out of Scope

- Q9 (`q9_horizon_exit_adapter` candidate) — trusted `post_exit_shadow_recap.v1` artifact does not persist which real source branch (`filled_price`/`current_price`/`price`/`avg_price`) resolved `exit_price`, so `exit_price_authority` cannot be reconstructed losslessly (UEF-4B-6 FIX1)
- Q11 legacy `opportunity_engine_virtual_trades.v1` artifacts — `observed_price` never persisted for a price-based checkpoint (superseded by `.v2`, still real/authentic PRIMARY EVIDENCE)
- Q12 Calc3 (`vnext_completeness_adapter` candidate) — legacy/frozen completeness contract contradiction (UEF-4B-2 FIX2)
- Dual-cost source family
- `rank1_feature_mart`
- Controlled Mock Lane / Opening Rank-1 Controlled Probe

These remain separate from the approved UEF-4B adapter sequence.

## Roadmap

| Phase | Owns | Status |
|---|---|---|
| UEF-4 Final Freeze | Adapter layer final freeze | PLANNED |
| UEF-5.1 | Clean Evidence Registry | FORMALLY FROZEN |
| UEF-5.2 | Historical Recompute | FORMALLY FROZEN |
| UEF-5.3 | Historical dual run (legacy comparison) | FORMALLY FROZEN |
| UEF-6 | Dedup and evidence lineage | FORMALLY FROZEN |
| UEF-7 | Alpha Board normalization | FORMALLY FROZEN |
| UEF-8 | Fair comparison validation | FORMALLY FROZEN |
| UEF-9 | Formal evaluation authority freeze | FORMALLY FROZEN |
| UEF COMPLETE | UEF-1..UEF-9 fully frozen evaluation-authority foundation | COMPLETE |
| P1.1 | UEF real-run acceptance | PASS |
| P1.2 | UEF cross-day observation | NON-BLOCKING / OBSERVE |
| P1.3 | Docker | NEXT |
| P1.5 | Large-file refactor / modularization | PLANNED |
| P2 | Strategy Program Integration (not UEF-10) | PLANNED |
| P3 | Safety Step5D / Step5E / Step6 | PLANNED |
| P4 | Q100 / Reporter v2 | PLANNED |
| P5 | Evidence Memory / Obsidian | PLANNED |
| P6 | Self-improvement | PLANNED |
| P7 | System V2 Freeze | PLANNED |
| P8 | Paper final experiments | PLANNED |

## Authority Documents

- [Unified Evaluation Foundation](../research/unified_evaluation_foundation.md)
- [UEF-4A legacy family inventory](../research/uef4_legacy_family_inventory.md)
- [UEF freeze manifest](../research/uef_freeze_manifest.md)
- [UEF-5.1 Clean Evidence Registry](../research/uef5_1_clean_evidence_registry.md)
- [UEF-5.2 Historical Recompute](../research/uef5_2_historical_recompute.md)
- [UEF-5.3 Historical Dual Run](../research/uef5_3_historical_dual_run.md)
- [UEF-6 Dedup & Evidence Lineage Freeze](../research/uef6_dedup_evidence_lineage_freeze.md)
- [UEF-7 Alpha Board Normalization Freeze](../research/uef7_alpha_board_normalization_freeze.md)
- [UEF-8 Fair Comparison Validation Freeze](../research/uef8_fair_comparison_validation_freeze.md)
- [UEF-9 Formal Evaluation Authority Freeze](../research/uef9_formal_evaluation_authority_freeze.md)
- [P1.1 UEF real-run acceptance](../research/uef_p1_1_real_run_acceptance.md)
- [ADR-0003: UEF-5.2 Market-Data Authority and Recompute Identity](../decisions/ADR-0003_UEF5_2_Market_Data_Authority_and_Recompute_Identity.md)
- [Evaluation roadmap](../en/12_roadmap.md)

## Related

- [[Strategy_Program_Integration|Strategy Program Integration]]
- [[Reporter_Q100|Reporter Q100]]
- [[Evidence_Memory|Evidence Memory]]
- [[System_V2|System V2]]
