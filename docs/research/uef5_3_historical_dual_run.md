# UEF-5.3 — Historical Dual Run

Status: **FORMALLY FROZEN** (independent Codex final closure audit: CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0;
`CORE_VERDICT: APPROVE_CORE`, `UEF5_3_COMPLETE: YES`). Not to be modified again unless a reproducible
correctness defect is discovered.

Compares the legacy (pre-UEF) evaluation outputs against the FROZEN UEF-5.2 canonical historical
recompute output for the SAME historical evidence, and classifies every material difference. Read-only
against UEF-1..UEF-5.2: never mutates a frozen file, never re-derives a canonical number, never builds
its own episodes/aggregates.

## Closure lineage (summary)
1. First delivery: legacy↔canonical family mapping, smallest dual-run core (Q10 Semiconductor, Q12
   Calc1), taxonomy, comparison-unit identity, output artifacts.
2. Codex audit (Core Correction 1): the real canonical UEF-3A metric contract was misread (`"COMPUTED"`
   instead of `MetricComputationStatus.VALID`; `episode_count` used as a population signal instead of
   `SamplePopulation.evaluated_count`); MDD was read but never compared; input/canonical/run identity was
   incomplete; Q10 Semiconductor's canonical-only cells (extra horizons with no legacy counterpart) were
   silently dropped from accounting. Fixed: real metric-contract semantics, independent legacy/canonical
   universe enumeration with an explicit join, a legacy input manifest bound into `dual_run_id`, and a
   real Q11 v2 EXIT mapping (verified against `_pipeline_q11_v2`, not inferred from names).
2. Codex re-audit (Core Correction 2): a non-comparable PF could suppress a comparable MDD divergence
   (metric independence gap); evidence identity was incomplete (path-only, no canonical-content or
   reader-implementation binding); `HASH_MISMATCH` could still be reported `EXACT_SAME_SOURCE`; Q12
   Calc1's first matching legacy view silently consumed the canonical aggregate, hiding a second view's
   real divergence; an absent canonical aggregate plus a legacy count of 0 was wrongly classified
   `EXACT_EMPTY`. Fixed: per-metric independent comparison, a 4-way identity-bound `dual_run_id`
   (legacy bytes + canonical bytes + reader implementation + taxonomy), strict `None`-is-never-zero
   population handling, and comparing every eligible Q12 Calc1 view independently.
3. Source-alignment micro-fix: `source_alignment` (same proven source evidence?) was wrongly coupled to
   the numeric comparison result. Decoupled: `EXACT_SAME_SOURCE` now depends only on `hash_match ==
   HASH_MATCH`, so a proven-same-source unit can legitimately report `UNEXPLAINED_DIVERGENCE`.
4. Final Closure Fix: Q12 Calc1 still allowed metric comparison from count equality alone (labelled
   `POPULATION_IDENTITY_NOT_PROVEN` while proceeding to compare anyway); `metric_comparisons` was
   computed internally but never persisted to the output record. Fixed: metric comparison gated on a
   positive population-identity proof; every comparison record now persists a structured
   `metric_comparisons` map (`comparable`, `status`, `legacy_value`, `canonical_value`, `reason` per
   metric).
5. Final one-item audit: the population-identity proof still trusted a serialized `lineage_status ==
   "FULL"` label without structurally re-verifying it, and never required the legacy view's own member
   identities to match canonical's. Fixed: `canonical_lineage_valid()` independently re-derives the
   frozen record contract's own invariant (no duplicate `source_episode_ids`,
   `len(unique(source_episode_ids)) == episode_count`) instead of trusting the label;
   `population_identity_proven()` additionally requires the legacy view's member-ID set to exactly equal
   canonical's `source_episode_ids` set. No membership is ever reconstructed or invented.
6. Final Codex closure: `CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0`, `CORE_VERDICT: APPROVE_CORE`,
   `UEF5_3_COMPLETE: YES`.

## Approved properties (final audited state)

- Dual-run comparison architecture: PASS
- Canonical metric contract read: PASS (real `MetricComputationStatus`/`SamplePopulation`/
  `WinLossFlatPopulation`, never the first delivery's incorrect assumptions)
- Metric-level comparison independence: PASS (a non-comparable metric never suppresses a comparable one)
- Legacy evidence identity: PASS (path + content sha256 + reader profile, distinct paths never collide)
- Canonical evidence identity: PASS (`canonical_content_digest` over the run's actual output bytes, not
  just its run_id string)
- Reader/profile identity: PASS (`reader_implementation_digest` over the uef5_3 package's own source)
- `dual_run_id` mutation sensitivity: PASS (legacy bytes, canonical bytes, or reader implementation
  changing all change the id)
- Unit identity: PASS (full-digest `unit_id`, never a truncated hash prefix)
- Source alignment / result independence: PASS (`source_alignment` answers only "same proven source
  evidence?", never coupled to whether the metrics happened to match)
- Hash alignment consistency: PASS (`HASH_MISMATCH` can never coexist with `EXACT_SAME_SOURCE`)
- Canonical universe enumeration: PASS (canonical-only cells independently enumerated; 0 omitted)
- Union accounting: PASS (`unaccounted = 0`, `collisions = 0`)
- Q12 population proof: fail-closed (count-only proof REJECTED; a structurally-valid canonical lineage
  alone is not sufficient; legacy member identities are currently unavailable, so every Q12 Calc1 view
  correctly terminates `NON_COMPARABLE / POPULATION_IDENTITY_NOT_PROVEN` with 0 metrics compared)
- Q11 EXIT: mapped (verified equivalence to `_pipeline_q11_v2`'s realized-trade checkpoint, not inferred
  from names)
- Q10 Index: `NON_COMPARABLE_CONFIRMED` (legacy per-day artifact has no win/PF/MDD summary; the only
  legacy summary artifact is cross-day cumulative, a genuine granularity mismatch against canonical's
  strictly per-day Calc H aggregates -- no new legacy aggregator was invented)
- Q12 Calc2: `NO_COMPARABLE_LEGACY_DAILY_AGGREGATE` (legacy has per-day entry/horizon results and a
  cumulative PF summary, but no semantically equivalent per-day PF aggregate -- none invented)
- Q12 Calc3 / Opening: BLOCKED (unchanged from UEF-4B; not touched by UEF-5.3)

## Important interpretation notes

**`EXACT_EMPTY` is not performance parity.** Of the 15 `EXACT_MATCH` units in the final audited run, 12
are `EXACT_EMPTY` (both legacy and canonical evaluated populations are 0 for that cell -- a real,
evidenced agreement that there is nothing to compare, not a return/performance claim).

**The actual non-empty parity evidence is Q11 EXIT**: 3 real units (2026-09-21, 2026-09-22, 2026-09-28)
where legacy and canonical independently agree on trade/population counts and profit_factor, to the
precision persisted. **MDD parity for Q11 is explicitly NOT_ESTABLISHED** -- the legacy Q11 artifact
persists no maximum-drawdown figure at all, so every Q11 comparison record flags `max_drawdown` as
non-comparable; this is never claimed as a match.

**Q12 Calc1 final disposition**: legacy view member identities are not persisted by the legacy artifact
this reader parses (an honest, current limitation, not a defect); canonical membership lineage may exist
in principle but is not wired by UEF-5.2's own aggregate construction today (`lineage_status` is
`"UNKNOWN"` for essentially every real aggregate). Because legacy↔canonical exact member-set equality is
therefore not provable from currently available evidence, **TOP1 / BOTH_SYMBOL_AVERAGE / ELIGIBLE_ENTRIES
are all `POPULATION_IDENTITY_NOT_PROVEN`**, and numeric metric comparison without exact population proof
is **0** in the final audited run. This is the expected, correct, fail-closed outcome -- not missing
coverage to optimize. The proof mechanism (`population_identity_proven`) is real and tested; it will
begin producing real Q12 Calc1 comparisons automatically, with no UEF-5.3 code change, once a future
UEF-5.2 increment wires real episode lineage and a legacy reader that exposes member identities.

## Final audited real run

Run id: **`UEF53DUAL_5e22b07eb2a62894`** (compared against UEF-5.2 run `UEF5RUN_bc1e299667c2ca94b977`),
at `reports/evaluation/uef5_dual_run/UEF53DUAL_5e22b07eb2a62894/`.

| Metric | Count |
|---|---:|
| Total comparison units | 4359 |
| Exact match (total) | 15 |
| — of which EXACT_EMPTY | 12 |
| — of which EXACT_NONEMPTY | 3 |
| Explained divergence | 0 |
| Non-comparable | 173 |
| Blocked | 4171 |
| **Unexplained** | **0** |
| Unaccounted | 0 |
| Collisions | 0 |

The dominant `BLOCKED` count (4171) is exactly what UEF-5.2's fail-closed candle-authority architecture
predicts: no `MarketDataReceipt` has been issued for any real symbol in this repository yet, so almost
every candle-dependent unit is `blocked_secondary_authority`. This is the correct, honest current state,
not a dual-run defect.

## UEF5_3_DEBT_001 (recorded, non-blocking, not fixed by this freeze)

**Description:** live artifact write-isolation/test monitoring (the project-wide pytest isolation
fixture) repeatedly re-hashes a large (~9GB) evidence-ledger file
(`data/evidence_ledger/events.jsonl`) while the live trading host concurrently appends to it during test
runs, and this has been observed to prevent timely pytest process termination during long test sessions.

**Classification:** correctness blocker: **NO**. UEF-5.3 freeze blocker: **NO**. Execution safety issue:
**NO evidence**. Test/observability efficiency debt: **YES**.

**Required future action:** optimize the live-artifact monitoring/hashing strategy (e.g. incremental or
size-capped hashing for very large append-only files) without weakening write-isolation detection. Not
fixed by this freeze.

## Test evidence note

Codex's final audit reported `TEST_EVIDENCE: PARTIAL`, for the reason recorded in `UEF5_3_DEBT_001`
above (large-ledger hashing interfering with process termination during the audit's own test run) --
**this was NOT an assertion failure**. Codex independently verified the required fixture reproductions.
The implementation-side record, accurately stated:

- Focused UEF-5.3 suite: 31 tests (`tests/test_uef5_3_dual_run.py`).
- Combined implementation-side run: 31 UEF-5.3 + 117 UEF-5.2 = **148 passed, 0 assertion failures**.

This combined-run result is Claude's own recorded evidence from this implementation, not an independent
Codex-confirmed clean pytest exit -- the two are distinguished deliberately and must not be conflated.

## Freeze record

The UEF-5.3-owned implementation file set (never mixed with documentation or test files) and its SHA-256
identity at freeze time:

| File | SHA-256 |
|---|---|
| `libs/reporting/evaluation/uef5_3/__init__.py` | `9bb03771ee8ac87d149b2e654ba4f54a215447b9417538059bda75bf7790caea` |
| `libs/reporting/evaluation/uef5_3/canonical_run.py` | `a7107f4c84533df77511fea8b19095d4ad755a3906d11e5fc9099aa3464c6af1` |
| `libs/reporting/evaluation/uef5_3/comparison_unit.py` | `e09008d14082a43a08ec2ead3b735c700053dc5079b8196df444b792ee42e822` |
| `libs/reporting/evaluation/uef5_3/divergence_classifier.py` | `3f8401d9d57a0851f7b95a113e34459b574d55b63c3b5f53c91251256e68de6e` |
| `libs/reporting/evaluation/uef5_3/dual_run.py` | `6595f1c8dd6cc15e872fb61dd52986f139e0d0a3c7cb5af57dbf8982d46f0bb1` |
| `libs/reporting/evaluation/uef5_3/legacy_forward_returns.py` | `61e18d9c28b1227d250c71a16e4cb208d9990913c7097d623eec21d56554f2f0` |
| `libs/reporting/evaluation/uef5_3/legacy_opportunity_engine.py` | `d0c63f6da0cc5bc50bc2d508cc05062bb71926205a672bca8afeccf3733ee621` |
| `libs/reporting/evaluation/uef5_3/taxonomy.py` | `c31a4e8de2c6ea7c8db06cc7c2da9e301e9cfec59855d2f1544e0747f0a72b22` |
| `scripts/run_uef5_3_dual_run.py` | `758ffc9b68850987be9a940ee96473e25f0559d74ed1450aae72a006f35fc209` |

Referenced, separately-owned frozen dependencies (not re-frozen here; read-only): the 11-file UEF-1..3C
freeze manifest, UEF-5.1's clean-evidence-registry modules, and UEF-5.2's own frozen `historical_recompute.py`
/ `candle_authority.py` / `session_policy.py` / `libs/market_data/receipts.py` (per UEF-5.2's own freeze
record above) -- UEF-5.3 only reads UEF-5.2's already-written run output files
(`run_manifest.json`/`aggregates.json`/`input_manifest.json`), never UEF-5.2's code.

Following the existing UEF-4B/UEF-5.1/UEF-5.2 convention, no test file is part of the frozen
semantic-authority set. Coverage: `tests/test_uef5_3_dual_run.py` (31 tests).

Not to be modified again unless a reproducible correctness defect is discovered (matching the standing
governance for every other formally-frozen UEF phase).
