# UEF-5.2 — Canonical Historical Recompute

Status: **FORMALLY FROZEN** (independent Codex closure audit: CRITICAL 0, HIGH 0, MEDIUM 1, LOW 0;
`APPROVE_UEF5_2`, `FORMAL_FREEZE: YES`, `READY_FOR_UEF5_3: YES` pending this documentation gate).
UEF-5.3 (historical dual run / legacy comparison) is now also **FORMALLY FROZEN** -- see
[UEF-5.3 Historical Dual Run](uef5_3_historical_dual_run.md). Not to be modified again unless a
reproducible correctness defect is discovered.

See [ADR-0003](../decisions/ADR-0003_UEF5_2_Market_Data_Authority_and_Recompute_Identity.md) (including
its Correction 1 amendment) for the full architecture decision and the fix to the legacy-cache-
contamination / source-window-leakage defects the first implementation audit found. This document covers
scope, actual counts, the one recorded non-blocking debt item, and known limitations.

## Closure lineage (summary)
1. Historical Recompute implemented; secondary candle-authority discovery; Q10 Index cost-authority
   correction.
2. Fix1: anchor corroboration alone ruled materially insufficient (HIGH-1); Q10 Index F/G zero-cost
   fabrication closed (HIGH-2).
3. Fix2: Q12 Calc1/Calc2 pipelines wired to the approved frozen adapters; run-identity gap closed.
4. Architecture Review v1/v2/v3 (independently audited, APPROVE_ARCHITECTURE_V3): acquisition-issued
   `MarketDataReceipt`, immutable raw archive, normalizer implementation identity, `SessionPolicy` as a
   separate UEF-owned authority, canonical 09:00-15:30 projection, bounded semantic implementation
   manifest, deterministic run identity.
5. Implementation Correction 1: legacy-cache contamination (HIGH-1) and source-window leakage (HIGH-2)
   closed; independent attested normalized artifact; deterministic `RawPageBundle`; true atomic
   publication; receipt-failure observability.
6. Final Codex closure: CRITICAL 0, HIGH 0, MEDIUM 1 (`UEF5_2_DEBT_001`, recorded below, non-blocking),
   `APPROVE_UEF5_2`, `FORMAL_FREEZE: YES`.

## UEF5_2_DEBT_001 (recorded, non-blocking, not fixed by this freeze)
**Description:** the current fresh-acquisition order in `kiwoom_history.py` is
`normalize -> raw persist/verify -> attested-normalized persist/verify -> receipt`. The
architecture-preferred order is `raw persist/verify -> normalize -> attested-normalized persist/verify
-> receipt` (normalize strictly after raw is durably persisted and re-verified). Codex determination:
**Severity MEDIUM; authority corruption NOT REPRODUCED; Formal Freeze blocker: NO** (normalization in
this reader is already computed page-by-page, in lockstep with the exact pages later archived, so no
row currently escapes correspondence with its raw material -- the ordering gap is a lifecycle-sequencing
debt, not a proven contamination path). **Required future action, only if the acquisition lifecycle is
modified again:** (1) align the normalizer invocation to run strictly after raw persistence/verification;
(2) add a regression that verifies the actual invocation order (extending the existing
`test_receipt_last_finalization_order` instrumentation pattern in
`tests/test_kiwoom_history_receipt_lifecycle.py`). Do not reopen UEF-5.2 for this debt alone.

## Correction 1 summary
The first implementation let a receipt attest the legacy convenience merged cache (old + new rows), and
verified source scope by day-level overlap. Both are fixed: acquisition now persists an INDEPENDENT,
content-addressed attested normalized artifact containing ONLY the freshly-fetched rows a receipt
describes; UEF-5.2 reads candles ONLY from that artifact (never the legacy cache path) and checks EVERY
consumed row individually against the receipt's source window (one out-of-range row fails the unit
closed). See ADR-0003's amendment for the full detail.

## Scope
Offline, deterministic recompute of historical evidence through the frozen canonical layer (UEF-1..3C)
and the approved UEF-4 adapters. Only evidence the UEF-5.1 registry classifies CLEAN, for adapters that
are not BLOCKED, is recomputed. **No legacy comparison, no parity claim.** Nothing in production, graphs
or apps imports it.

Files: `libs/reporting/evaluation/uef5/historical_recompute.py`, `candle_authority.py`,
`session_policy.py`, `libs/market_data/receipts.py`, `scripts/run_uef5_historical_recompute.py`,
`tests/test_uef5_2_historical_recompute.py`, `tests/test_market_data_receipts.py`,
`tests/test_uef5_2_session_policy.py`. It reads private helpers of the frozen UEF-5.1 coverage module
read-only; it modifies no frozen file.

## Eligible families
Q10 Semiconductor, Q12 Calc1, Q12 Calc2, Opening Shadow (1A, 1B/1C, deferred safely -- no CLEAN input
exists), Q10 Index, Q11 v2. Blocked and always excluded: Q9, Q11 v1, Q12 Calc3, Q18, rank1_feature_mart.

## Market-data authority (ADR-0003 Decision 1)
Candle admission requires a verified `libs.market_data.receipts.MarketDataReceipt`: the acquisition
component (`libs/research/post_reclaim_alpha/kiwoom_history.py`) issues trust evidence (raw artifact
persisted first, then normalized artifact, then the receipt atomically last); UEF-5.2's
`candle_authority.verify_receipt` only ever verifies it. There is no boolean "trust me" flag anywhere in
production code. Since no receipt has ever been issued for the ~339 existing legacy cache files (no raw
bytes were ever archived for them), they are `LEGACY_UNATTESTED` and permanently `NOT_BACKFILLABLE` --
real Q10 Semiconductor/Calc1/Calc2 canonical output is correctly 0 until newly-acquired data starts
carrying a receipt. Anchor corroboration against a CLEAN primary artifact's own persisted checkpoints is
kept as a diagnostic (`corroboration`) only; it never gates admission.

## Canonical session (ADR-0003 Decision 2)
A separate, UEF-owned `SessionPolicy` (09:00-15:30 KST, `session_policy.py`) projects admitted candles to
the canonical regular session before any frozen adapter call. `MarketDataReceipt.source_window_*`
describes what was physically acquired; `SessionPolicy` describes what UEF evaluates -- a raw row like
15:35 may be receipt-attested and structurally valid, and simply cannot enter the projected input, so it
cannot affect `LAST_AVAILABLE`/EOD/MFE/MAE.

## Semantic implementation identity and run id (ADR-0003 Decision 3)
`run_id` binds an explicit, bounded `SemanticImplementationManifest` (the orchestrator itself, the
receipt/session verifiers, the three UEF-5.1 registry modules, `canonical/record.py`, and the 7 exact
UEF-4 adapters used -- frozen UEF-1..3C is represented only by the existing 11-file freeze manifest
digest, never re-hashed individually) plus the effective run configuration, the primary/secondary input
manifest digests, the registry digest and the cost-authority digest. The acquisition normalizer's own
implementation digest travels inside the verified receipt rather than being duplicated in the
implementation manifest.

## Actual counts (real repository, run `UEF5RUN_bc1e299667c2ca94b977`, status PARTIAL)
| Family | Discovered | CLEAN | Recomputed units | Episodes | Checkpoints | Aggregates | Blocked / skipped |
|---|---|---|---|---|---|---|---|
| Q10 Semiconductor | 70 | 63 | 1 (0 episodes) | 0 | 0 | 21 (empty) | 62 secondary authority (no receipt), 7 registry |
| Q12 Calc1 | 68 | 68 | 4 (0 episodes) | 0 | 0 | 0 | 64 secondary authority (no receipt) |
| Q12 Calc2 | 23 | 1 | 1 (0 episodes, no candle need) | 0 | 0 | 0 | 22 registry |
| Opening 1A / 1B-1C | 1 / 1 | 0 / 0 | 0 | 0 | 0 | 0 | REVIEW_REQUIRED, no error |
| Q10 Index | 63 files (21 days) | 63 | 21 | 103 | 327 | 105 (Calc H only) | 21 days F/G aggregate blocked (no cost authority) |
| Q11 v2 | 8 | 8 | 8 | 4 | 24 | 18 | none |

Totals: 107 episodes, 351 checkpoints, 144 aggregates, 0 parse/adapter failures, 0 identity collisions.
`blocked_missing_candles` is now 0 everywhere: since no receipt has ever been issued for any real symbol
in this repository, every CLEAN-but-candle-needing unit is correctly `blocked_secondary_authority`
(`SECONDARY_INPUT_AUTHORITY_NOT_PROVEN`) rather than the old file-existence bucket -- there is no longer a
separate "file present but unattested" state once admission is receipt-only.
Discovered counts grow day over day since the host runtime keeps producing evidence for the live
trading day; this is expected and does not affect the recompute's own correctness.

## Known limitations (disclosed)
- No production acquisition has issued a `MarketDataReceipt` yet (the acquisition-side integration is
  wired and tested but not yet exercised by a real network fetch in this environment), so real candle
  admission is 0 today; this is the intended, correct effect of the architecture, not a defect.
  `kiwoom_history.py::load_or_fetch_symbol_history` now archives raw bytes and issues a receipt
  automatically on every successful fresh fetch going forward.
- Calc1/Calc2/Opening pipelines: Calc1/Calc2 are wired but candle-blocked (no 041190 cache exists at
  all); Opening has no CLEAN input.
- Aggregate member lineage is not persisted by the frozen aggregate record (UEF-6 debt, explicitly out
  of scope).
- Q10 Semiconductor member counts are not exposed by the approved adapter (`member_counts_complete: false`).
- Aggregates are per trading day.

## Freeze record

The UEF-5.2-owned implementation file set (never mixed with documentation, tests, or the separately-owned
UEF-5.1/UEF-1..4 dependency files this module reads/hashes at run time) and its SHA-256 identity at
freeze time:

| File | SHA-256 |
|---|---|
| `libs/reporting/evaluation/uef5/historical_recompute.py` | `e8f963e7b1439a231a0f89fc8f5847f006925fd6527819ebbeb41e7d4dbc0db1` |
| `libs/reporting/evaluation/uef5/candle_authority.py` | `0345eb9882ead245634b8be6f9ba1918a991b52aaafa720c6da4d4132fbed249` |
| `libs/reporting/evaluation/uef5/session_policy.py` | `ca7071174f86aeae463233e9c23fdc15395fc36a3e7abf42b95e63063f67853e` |
| `libs/market_data/__init__.py` | `687e760417175287d9c76a98bffcbed74150b2245ed14687fbb425c10da86687` |
| `libs/market_data/receipts.py` | `34998a173147f2c3e318a9fd195e3b8f4499b2e90cfcf2dda6c02bf4f5b43dd2` |
| `libs/research/post_reclaim_alpha/kiwoom_history.py` | `7d374466cacaeecff98299028ddc07d07ef1bee8badff31750323996e4e5ebd5` |
| `scripts/run_uef5_historical_recompute.py` | `5ef5f6f25c0799f8210813ab736a106dd36ddd5a1e4dbefcc6b5236b94d3d2d2` |

Referenced, separately-owned frozen dependencies (not re-frozen here; each hashed only for UEF-5.2's own
run-identity purposes, per the semantic implementation manifest in ADR-0003 Decision 3): the 11-file
UEF-1..3C freeze manifest (`docs/research/uef_freeze_manifest.md`), the three UEF-5.1 registry modules
(`clean_evidence_registry.py`, `clean_evidence_rules.py`, `clean_evidence_coverage.py`, frozen at commit
`b2efd84`), `canonical/record.py`, and the 7 exact UEF-4 adapter modules UEF-5.2 calls. None of these are
modified by, or re-frozen under, this UEF-5.2 freeze.

Following the existing UEF-4B/UEF-5.1 convention, no test file is part of the frozen semantic-authority
set (test fixtures/regressions are evidence of correctness, not authority themselves). Coverage:
`tests/test_uef5_2_historical_recompute.py`, `tests/test_market_data_receipts.py`,
`tests/test_uef5_2_session_policy.py`, `tests/test_kiwoom_history_receipt_lifecycle.py`.

Not to be modified again unless a reproducible correctness defect is discovered (matching the standing
governance for every other formally-frozen UEF phase).
