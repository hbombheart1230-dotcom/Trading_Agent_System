# 2026-09-28 UEF-5.1/5.2 Formal Freeze and Patch-Note Backfill

## Scope

This entry backfills the evaluation-track (UEF-5) history that accumulated since the last patch-note
update and records the formal freeze of UEF-5.1 and UEF-5.2. It changes evaluation/reporting integrity
only -- no Scanner ranking, Strategist behavior, Commander approval, Monitor entry/exit rules, position
sizing, or broker execution is affected. UEF-5.2's own acquisition-side addition
(`kiwoom_history.py`'s receipt issuance) is additive only: it does not change network request semantics,
what candles are returned, or how they are served.

## UEF-5.1 — Clean Evidence Registry

- IMPLEMENTED, then AUDITED (Codex rejected the first submission, HIGH x4), then CORRECTED (FIX1:
  positive clean authority closure -- `MATCHED CLEAN DOMAIN != CLEAN`), then APPROVED and FORMALLY
  FROZEN by an independent Codex audit (`APPROVE`, `FORMAL FREEZE: YES`, `READY_FOR_UEF5_2: YES`; one
  non-blocking MEDIUM on the Incident C 75.47% vs 44.67% numeric discrepancy, intentionally left
  unresolved).
- Freeze commit: `b2efd84` ("feat: freeze UEF-5.1 clean evidence registry").
- Detail: [docs/research/uef5_1_clean_evidence_registry.md](../research/uef5_1_clean_evidence_registry.md).

## UEF-5.2 — Historical Recompute

- IMPLEMENTED: canonical historical recompute over UEF-5.1-CLEAN evidence through the frozen canonical
  layer and approved UEF-4 adapters (Q10 Semiconductor, Q12 Calc1/Calc2, Q10 Index, Q11 v2; Opening
  deferred safely).
- AUDITED / CORRECTED (Fix1): anchor corroboration alone ruled materially insufficient for candle source
  authority (HIGH-1); Q10 Index F/G zero-cost fabrication closed, no unauthorized net metric without an
  authoritative cost policy (HIGH-2).
- CORRECTED (Fix2): Q12 Calc1/Calc2 wired to the approved frozen adapters (previously blocked-by-missing-
  input only); the run-identity gap (`historical_recompute.py` itself unbound from its own run id) closed.
- Architecture Review v1/v2/v3, independently audited and APPROVED (`APPROVE_ARCHITECTURE_V3`): the
  acquisition component issues trust evidence (`MarketDataReceipt`), never UEF itself; an immutable raw
  archive; a normalizer implementation identity travelling inside the receipt; a separate, UEF-owned
  `SessionPolicy` (never the receipt) governing the canonical 09:00-15:30 KST evaluation session; a
  bounded, explicit semantic implementation manifest; a deterministic run identity formula.
- IMPLEMENTED then AUDITED / CORRECTED (Implementation Correction 1): the first implementation let a
  receipt attest the legacy convenience merged cache (old + freshly-fetched rows together) and verified
  source scope by day-level overlap -- both closed by (a) binding a receipt to an INDEPENDENT,
  content-addressed attested normalized artifact containing only the rows that acquisition actually
  produced, and (b) checking every individually consumed row against the receipt's own source window
  (one out-of-range row fails the whole unit closed).
- APPROVED and FORMALLY FROZEN by an independent Codex closure audit: `CRITICAL 0, HIGH 0, MEDIUM 1, LOW
  0`, `APPROVE_UEF5_2`, `FORMAL_FREEZE: YES`. The one remaining MEDIUM is recorded as non-blocking debt
  `UEF5_2_DEBT_001` (acquisition-lifecycle stage ordering; authority corruption NOT reproduced) and is
  intentionally left unfixed by this freeze.
- Detail: [docs/research/uef5_2_historical_recompute.md](../research/uef5_2_historical_recompute.md),
  [ADR-0003](../decisions/ADR-0003_UEF5_2_Market_Data_Authority_and_Recompute_Identity.md).

## Verification (at freeze)

- Freeze manifest (UEF-1..3C): `11 / 11 MATCH`.
- UEF-5.1: unchanged (`git diff` clean against its 7 frozen files and the canonical layer).
- Focused UEF-5.2 tests: 117 passed (`test_uef5_2_historical_recompute.py`,
  `test_market_data_receipts.py`, `test_uef5_2_session_policy.py`,
  `test_kiwoom_history_receipt_lifecycle.py`).
- Relevant UEF-1..5.1 regression: 777 passed.
- Production imports: 0. Broker calls: 0. Live trading behavior changed: NO.

## Reviewed for other missing milestones (not added -- see reasoning)

This backfill also checked for other operations milestones the roadmap review asked about:

- **Safety Step5C** (durable execution ownership / atomic order-intent admission) -- already documented
  as FROZEN in [docs/milestones/Safety.md](../milestones/Safety.md); nothing to backfill.
- **Q10 / Q12 / Opening evaluation milestones** -- already fully documented in
  [docs/milestones/UEF.md](../milestones/UEF.md) (UEF-4B-1 through UEF-4B-4 formally frozen, UEF-4B-5
  provisionally closed, UEF-4B-6 primary/known/blocked); nothing to backfill.
- **Docker/1GiB OOM incident, EOD full-file memory root cause, memory-bounded event-reader correction,
  host/Docker isolation verification** -- these were NOT found committed to git history or recorded in
  any repository document; the related code changes remain uncommitted working-tree modifications.
  Per this backfill's own instruction to omit rather than fabricate when repository evidence is
  insufficient, these are intentionally NOT recorded here. They should get their own patch-note entry
  at the point they are actually committed.

## Governance

`docs/daily_patch/README.md` now states an explicit "When To Add An Entry" rule (formal freezes,
architecture decisions, production/runtime safety fixes, research-lifecycle promotion/deprecation, major
incidents, major roadmap changes -- not routine tests/refactors/formatting).
