# ADR-0003: UEF-5.2 Market-Data Authority and Recompute Identity

## Status

Accepted (architecture v3 approved). Implementation Correction 1 applied (see amendment below) after
the first implementation audit found two HIGH defects (legacy-cache contamination, source-window
leakage) and two MEDIUM defects (finalization-order/atomicity, receipt-failure observability) -- all
implementation divergence from this already-approved architecture, not an architecture change.

**UEF-5.2 is FORMALLY FROZEN** (independent Codex closure audit after Correction 1: CRITICAL 0, HIGH 0,
MEDIUM 1, LOW 0; `APPROVE_UEF5_2`, `FORMAL_FREEZE: YES`). The one remaining MEDIUM is recorded as
non-blocking technical debt `UEF5_2_DEBT_001` (acquisition-lifecycle stage ordering; authority corruption
NOT reproduced) -- see [docs/research/uef5_2_historical_recompute.md](../research/uef5_2_historical_recompute.md)
for its full description and required future action. Not to be modified again unless a reproducible
correctness defect is discovered.

### Amendment: Implementation Correction 1 (post-audit)

The first implementation of Decision 1 let a receipt's `normalized_candle_sha256` point at the LEGACY
convenience merged cache (old cached rows unioned with freshly-fetched ones), so a fresh receipt could
retroactively attest pre-existing unattested rows merely because they shared one on-disk file. It also
verified a receipt's acquisition scope by day-level window overlap rather than checking every individual
consumed row.

Both are corrected as follows, with no change to the approved trust boundary, session ownership split,
or semantic-identity model above:

- **Attested artifact is independent of the legacy cache.** The acquisition side now persists an
  INDEPENDENT, content-addressed "attested normalized artifact"
  (`libs.market_data.receipts.normalized_content_ref`, keyed by its own sha256) containing ONLY the rows
  a specific acquisition's raw page bundle actually produced. `MarketDataReceipt.normalized_candle_sha256`
  binds to THIS artifact, never to the legacy convenience merged cache the acquisition side still writes
  for other consumers. UEF-5.2's `candle_authority.verify_receipt_bound_candles` reads candles ONLY from
  this attested artifact -- it never resolves, hashes, or otherwise consults any legacy cache path, so a
  fresh receipt can never retroactively attest rows it did not itself produce (CORE AUTHORITY INVARIANT:
  a row may receive `FULL_SOURCE_AUTHORITY` iff it is present in the exact attested artifact the receipt's
  own hash describes).
- **Row-level source-scope verification.** Admission now checks, for EVERY individual consumed row,
  `receipt.source_window_start <= row.ts <= receipt.source_window_end` -- never a day-level overlap. One
  row outside the window fails the entire unit closed (`SECONDARY_INPUT_SOURCE_SCOPE_VIOLATION`); there is
  no partial admission of an in-range subset.
- **Multi-page raw completeness.** The raw archive persists a deterministic `RawPageBundle`
  (`libs.market_data.receipts.raw_page_bundle_bytes`) preserving every contributing provider page's exact
  text and order; `raw_payload_sha256` binds the whole bundle, so removing or mutating any one page
  invalidates the receipt.
- **True atomic publication.** Raw and attested-normalized artifacts are now published by writing a
  complete, fsynced temp file and then atomically linking it into its final, previously-absent path
  (`os.link`) -- the final path is never visible partially written. Receipts (mutable pointers, unlike the
  immutable content-addressed blobs) are published via a fsynced temp file plus `os.replace`.
  Finalization order is unchanged (raw -> verify -> normalize -> attested-normalized -> verify -> receipt
  LAST) and is now instrumented/tested stage by stage.
- **Receipt-failure observability.** The acquisition side's `except Exception: pass` is replaced with a
  structured warning log per failed stage (symbol, acquisition scope, failure stage, exception class --
  never raw payload content or secrets); candle acquisition/serving still never breaks because provenance
  issuance failed, and a failed/partial issuance is guaranteed to leave no valid receipt (content-addressed
  identity means a stale receipt can never validate different bytes than the ones it was issued for).

## Context

UEF-5.2's canonical historical recompute needs to decide, for a minute-candle input, whether it is
authoritative enough to feed a frozen UEF-4 adapter. An earlier iteration (Fix1) treated anchor
corroboration -- the primary artifact's own persisted checkpoint closes reproduced in the candle file --
as sufficient grounds for admission. An independent audit (Codex) found this materially insufficient:
canonical MFE/MAE and every aggregate depend on the *intermediate* bars between two corroborated
anchors, and those bars carry zero independent corroboration of their own. A subsequent fix (Fix2)
downgraded anchor corroboration to a diagnostic and introduced a test-only `full_authority` boolean, but
that boolean was itself flagged as an architecture gap: no production caller could ever grant
`FULL_SOURCE_AUTHORITY`, so there was no route back to non-zero historical coverage even for
well-governed future data. A parallel finding was that `historical_recompute.py` itself -- the
orchestrator that owns every gate and dispatch decision -- was not bound into the recompute's own run
identity, so a semantic change to it would silently not change the run id.

This ADR resolves both gaps through a three-round architecture review (v1-v3) with an independent
auditor, closing every raised MEDIUM/HIGH finding before implementation.

## Decision 1: Market-data acquisition authority

The acquisition component issues trust evidence; UEF only ever verifies it. Concretely:

- `libs/market_data/receipts.py` (a new, UEF-independent, shared contract module) defines
  `MarketDataReceipt`: `receipt_schema`, `provider`, `producer_id`, `producer_version`, `symbol`,
  `trading_date`, `interval`, `source_window_start/end`, `raw_payload_sha256`, `raw_archive_ref`,
  `normalized_candle_sha256`, `normalizer_id`/`normalizer_version`/`normalizer_implementation_digest`,
  `row_count`, and a `diagnostic` bag that never participates in `receipt_digest`.
- `raw_archive_ref` is a content-addressed, confined-root reference
  (`{provider}/{producer_id}/{symbol}/{raw_sha256}.raw`); resolving it re-reads and re-hashes the bytes
  every time -- a hash alone is never treated as proof that the corresponding bytes are still retrievable.
  Absolute paths, `..` traversal, and any resolved escape of the configured archive root are rejected.
  Writes are atomic-create/no-clobber: identical content at the same ref is idempotent-safe; different
  content at the same ref is a hard failure. The raw artifact is never overwritten in place.
- Finalization order, enforced by the caller: (1) raw artifact persisted atomically, (2) raw bytes
  re-read and re-hashed, (3) normalization performed, (4) normalized artifact persisted atomically, (5)
  normalized bytes re-read and re-hashed, (6) receipt written atomically **last**. A partial acquisition
  (raw saved, normalization failed; normalized saved, receipt write failed) simply never reaches step 6,
  so no half-written provenance record can exist.
- `libs/reporting/evaluation/uef5/candle_authority.py::verify_receipt` is the one function permitted to
  return `FULL_SOURCE_AUTHORITY`. It checks: the receipt exists; its schema/provider/producer are
  recognized (`kiwoom` / `KIWOOM_HISTORICAL_MINUTE_V1` -- one identity, because
  `opening_rank1_shadow/candle_provider.py` reuses the exact same `KiwoomHistoricalMinuteReader`
  implementation rather than a semantically distinct acquisition path); the symbol matches; the day
  falls within the receipt's acquisition window; the raw archive resolves and its hash matches; the
  normalized artifact's hash matches; a normalizer identity is present. Any missing proof is
  `NOT_PROVEN`; any contradicting proof is `INVALID`. Both fail closed.
- **No caller boolean can grant production trust.** Tests exercise the identical `verify_receipt` path by
  constructing a real receipt and a real raw archive under a temporary root -- never a bypass.

## Decision 2: Source artifact vs. evaluation-session ownership

`MarketDataReceipt.source_window_start/end` describes what was physically **acquired** -- a raw source
may legitimately contain `09:00 ... 15:30 ... 15:35`. It never declares what UEF should **evaluate**.
That is a separate, UEF-owned authority: `libs/reporting/evaluation/uef5/session_policy.py::SessionPolicy`
(schema, timezone, session start/end, boundary inclusivity, extended-row behavior), with a content-derived
`policy_id` (`sha256(canonical_json(semantic fields))`, no UUID, no clock -- the same convention already
used by `CostPolicy.policy_id`). The canonical Korean regular session is `09:00-15:30 Asia/Seoul`,
both bounds inclusive, drawn from the frozen forward engine's own pervasive session clocks
(`FixedClockSpec("09:00")`/`("15:30")` throughout `forward/profiles.py`) and
`baseline_btc_woori_tech/input_delivery.py`'s own `[09:00,15:30]` candle clamp -- not an assumption.

## Decision 3: Canonical session projection

`session_policy.project_session` deterministically and non-mutatingly filters admitted candle rows to
the canonical session, sorted strictly by `ts` ascending (structural validation already rejects ambiguous
duplicate timestamps before projection, so no secondary tie-break is needed). It produces a
`canonical_projection_digest` over exactly `{ts, open, high, low, close, volume}` -- never `raw_ts`,
paths, or diagnostic metadata -- using the values already normalized and persisted (no new rounding
rule). `SecondaryCandleInputs.consume` returns **only** these projected rows to a pipeline; a frozen
adapter never sees a row outside the canonical session, so a `15:35` bar cannot affect
`LAST_AVAILABLE`/EOD/MFE/MAE. Because `ObservationSelectionMode.LAST_AVAILABLE` (frozen UEF-2B) operates
purely over whatever `observations` sequence its caller supplies, this holds with zero frozen-engine
code changed. A source change that leaves the canonical window byte-identical changes the receipt's
`normalized_candle_sha256` but leaves `canonical_projection_digest` unchanged by design -- both facts
stay independently visible.

## Decision 4: Semantic implementation identity and run id

`historical_recompute.py` is semantic implementation authority: it owns family wiring, registry gates,
secondary-input gates, cost-stage gates, accounting, and adapter/aggregation dispatch. Its own content
hash is therefore part of `SemanticImplementationManifest`, alongside `candle_authority.py`,
`session_policy.py`, `libs/market_data/receipts.py`, the three UEF-5.1 registry modules
(`clean_evidence_registry.py` -- resolution behavior; `clean_evidence_rules.py` -- admission authority;
`clean_evidence_coverage.py` -- input discovery/classification semantics), `canonical/record.py`
(confirmed, by direct inspection, to be the one canonical file that defines the serialized
episode/aggregate shape yet is absent from the 11-file freeze manifest), and the 7 exact UEF-4 adapter
modules actually used. Frozen UEF-1..3C is represented **only** by the existing freeze manifest's own
digest, never re-hashed file-by-file inside this manifest. The acquisition normalizer's own
implementation digest travels inside the verified `MarketDataReceipt` rather than being duplicated here.
`scripts/run_uef5_historical_recompute.py` is non-semantic (it only parses arguments and calls the
runner) and is therefore represented by an `effective_run_config` digest, not a file hash.

```
run_id = "UEF5RUN_" + sha256(canonical_json({
    implementation_manifest_digest,   # orchestrator + verifiers + registry modules + adapters + frozen-core digest
    effective_run_config_digest,      # families, candle_source_dirs, max_parse_bytes, session_policy_id/digest, versions
    primary_input_manifest_digest,
    secondary_input_manifest_digest,  # per unit: source_authority | evaluation_policy | canonical_projection_digest
    registry_digest,
    cost_authority_digest,
}))[:20]
```

No clock, no UUID, no random state, no filesystem-enumeration dependence (inputs are sorted before
hashing). `out_root`, `--no-write`, and console/log formatting never participate.

## Decision 5: Legacy-data policy

Existing minute caches have neither a raw archive nor a receipt -- the acquisition path that wrote them
discarded the raw provider response after normalizing it. They are `LEGACY_UNATTESTED` and permanently
`NOT_BACKFILLABLE`: no receipt is fabricated for them, and anchor agreement is never treated as
retroactive raw provenance. Real Q10 Semiconductor/Calc1/Calc2 canonical output is therefore 0 today.
This is accepted: the evaluation framework must be correct even when historical coverage is zero, and no
historical recovery is promised. Newly-acquired data, once the acquisition side issues a receipt for it,
becomes eligible without any further UEF-5.2 change.

## Failure semantics

Any required receipt/session-policy proof absent -> `NOT_PROVEN` -> fail closed. Any proof present but
contradicting the artifact it describes (hash mismatch, symbol mismatch, unrecognized schema) ->
`INVALID` -> fail closed. Structural invalidity (schema, symbol, row_count, timestamp/grid/ordering,
duplicate handling, OHLC relation, volume) blocks admission regardless of receipt status.

## Frozen-core impact

**NONE.** UEF-1, UEF-2A, UEF-2B, UEF-3A, UEF-3B, UEF-3C, the approved UEF-4 adapters, and the formally
frozen UEF-5.1 registry are all unmodified. Receipt verification, session projection, and the semantic
implementation manifest all live at the UEF-5.2 secondary-input boundary and feed the frozen adapters
through the exact same `minute_rows`/`observations` shapes as before this ADR.

## Operational impact

`libs/research/post_reclaim_alpha/kiwoom_history.py::load_or_fetch_symbol_history` now retains raw
provider response bytes, archives them, and issues a `MarketDataReceipt` automatically after every
successful fresh fetch -- additive only; network request semantics, market-data query semantics, and
what candles are returned to a caller are all unchanged. Receipt issuance failure is swallowed and never
breaks candle acquisition or serving. No trading decision, broker/order path, or seven-agent-topology
behavior is touched.

## Migration

No migration of existing data is performed or possible (see Decision 5). Going forward, every fresh
Kiwoom minute-history fetch produces a receipt; UEF-5.2 recompute runs pointed at a populated
`raw_archive_root`/`receipt_root` will admit that data automatically, with no further code change.

## Rejected alternatives

- **Raw hash without a retained, resolvable raw artifact**: proves content identity, not persistence or
  retrievability -- rejected; `raw_archive_ref` plus re-hash-on-resolve is required.
- **Anchor corroboration as authority**: intermediate bars remain uncorroborated and materially affect
  MFE/MAE/aggregates -- rejected (the original Fix1 finding, reaffirmed here as diagnostic-only).
- **A caller-supplied boolean `full_authority=True` as a production signal**: self-asserted trust --
  rejected; no such parameter exists in production code paths.
- **`SessionPolicy` embedded inside `MarketDataReceipt` as source truth**: conflates acquisition scope
  with evaluation scope, two different authorities -- rejected in favor of the Decision 2 split.
- **Using the raw physical last row as canonical EOD**: conflates raw storage scope with canonical
  evaluation scope -- rejected in favor of the session projection.
- **A manual recompute-version string bump as the sole code-identity signal**: silently misses real
  content changes -- rejected in favor of explicit, enumerated file hashing.
- **Recursive whole-repository import hashing**: unbounded and unauditable, and would re-hash files with
  no bearing on output -- rejected in favor of the bounded, explicit dependency closure in Decision 4.
- **Legacy receipt fabrication / copying normalized files into the raw archive and calling that
  provenance**: would manufacture false authority for data whose true provenance was never captured --
  rejected outright.

## Authority

- `libs/market_data/receipts.py`
- `libs/reporting/evaluation/uef5/candle_authority.py`
- `libs/reporting/evaluation/uef5/session_policy.py`
- `libs/reporting/evaluation/uef5/historical_recompute.py`
- [docs/research/uef5_2_historical_recompute.md](../research/uef5_2_historical_recompute.md)
- [docs/research/uef_freeze_manifest.md](../research/uef_freeze_manifest.md)
