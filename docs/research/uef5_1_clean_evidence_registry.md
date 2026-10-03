# UEF-5.1 — Clean Evidence Registry (incl. FIX1: positive clean authority)

**Status:** UEF-5.1 FORMALLY FROZEN (independent Codex audit: APPROVE, FORMAL FREEZE YES,
READY_FOR_UEF5_2 YES; one non-blocking MEDIUM on the Incident C 75.47% vs 44.67% numeric
discrepancy, intentionally left unresolved). Frozen at commit `b2efd84` ("feat: freeze UEF-5.1
clean evidence registry"). UEF-1..4 and the Research Portfolio Freeze are unchanged (freeze
manifest 11/11 MATCH). Codex's first audit had rejected the original submission (HIGH ×4); this
document describes the design after FIX1, which closed all four. UEF-5.2 (Historical Recompute)
built on this registry and is itself now FORMALLY FROZEN -- see
[docs/research/uef5_2_historical_recompute.md](uef5_2_historical_recompute.md).

## Purpose

The mandatory input boundary for UEF-5 historical recompute: which legacy evidence may enter a
canonical recompute. It computes no win rate / PF / return / MDD (UEF-5.2/5.3) and does not decide
adapter eligibility. Governing principle: **a false REVIEW_REQUIRED is preferable to a false CLEAN.**

Code: `libs/reporting/evaluation/uef5/` (stdlib-only; imports nothing from runtime, broker or the
frozen core; nothing in production imports it). Modules: `clean_evidence_registry.py` (contract +
resolver), `clean_evidence_rules.py` (incident rules, candidate domains, positive verifiers, structural
day-validity derivation, adapter-eligibility table), `clean_evidence_coverage.py` (file-level coverage),
`scripts/build_uef5_clean_evidence_coverage.py` (read-only CLI).

## Status model

`CLEAN` · `QUARANTINED` · `FIELD_INVALID` · `REVIEW_REQUIRED` · `NO_RULE` (resolver-only: outside every
candidate domain and unmatched; fail closed, reported as "unclassified"). Merge order
`QUARANTINED > REVIEW_REQUIRED > FIELD_INVALID > CLEAN > NO_RULE` plus set unions, so rule order never
matters. Duplicate ids or identical-scope rules (duplicate or conflicting) make registry construction fail.

## Positive clean authority (FIX1, HIGH-1)

```
MATCHED CLEAN DOMAIN  !=  CLEAN
```

A `CleanDomain` is only a **candidate**: "eligible to be positively audited". CLEAN requires all of:

1. a matched candidate domain, **and**
2. a `PositiveAuditResult` from that domain's declared verifier (stable `verifier_id`) with outcome
   `PROVEN_CLEAN`, **and**
3. every check in the domain's `required_checks` present in `passed_checks` (a verifier cannot skip a
   declared check) and no failed check, **and**
4. no negative rule matching the file **or any internal record**.

Outcomes: `PROVEN_CLEAN` / `NOT_PROVEN` (a needed persisted field is absent, no verifier, no audit) /
`INVALID` (persisted evidence contradicts). Matched-but-unproven ⇒ `REVIEW_REQUIRED` with
`POSITIVE_CLEAN_NOT_PROVEN` or `POSITIVE_CLEAN_CONTRADICTED`. A domain with no verifier can never yield
CLEAN. Verifiers use only persisted fields; absent field ⇒ NOT_PROVEN, wrong field ⇒ INVALID. Logic never
reads `human_note`.

**What a verifier proves — and does not.** Structural / native-identity / provenance-field consistency
from persisted fields. It is not a chain-of-custody proof against a perfect mimic, which is why the
negative record-level rules keep dominating CLEAN.

### Per-family positive proof (persisted fields only)

| Family | Verifier proves | Notes |
|---|---|---|
| Q10 Semiconductor | schema, program id, `day`==path date, `behavior_effect`, `cost_model.source == kiwoom.ka10170`, `row_count`, every row `symbol` = 6 digits and `baseline_decision_id == BSH_<yyyymmdd>_<epoch>` with id date and KST epoch date == `day`, day not forward-coverage-invalid | persists a Q9 comparison, so the forward-day check applies |
| Q12 Calc1 | same shape with `BTW_` ids and Q12 program | persists no Q9 comparison ⇒ forward-day check deliberately not applied |
| Q12 Calc2 | schema, `contract_id`, `day`==path, `evidence_phase == PROSPECTIVE` and day ≥ `prospective_start_day`, orders disabled, `btc_delivery_source == canonical_0855_capture`, epochs' KST date == `day` | the delivery source is persisted in only 1 of 22 files; the rest are NOT_PROVEN (REVIEW_REQUIRED). The one BACKCHECK file is INVALID |
| Opening Shadow 1A | schema, contract flags, per-row `watch_id`/`trigger_decision_id` native ids match `initial_day`/`trigger_day`, `initial ≤ trigger ≤ through_day`, no producer-`VALID` row on a forward-invalid day | audited per record |
| Opening Shadow 1B/1C | **no verifier** | cumulative multi-date artifact; see below |
| Q10 Index | schema + program, `day`==path, exact guard contract, and the day's reactions file carries the authoritative target sources | each of the three day files |
| Q11 v2 | schema + program, `day`==path, `behavior_effect == shadow_only`, `trade_count`, every trade id `OE_TRD_<symbol>_<epoch>` == `symbol` and `entry_epoch` and KST date == `day`, `order_execution_allowed is False` | |

### Record granularity

A file that looks clean never implies every record is. The coverage builder builds descriptors for
internal records and the resolver applies negative rules to them: a file with an internal record matching a
QUARANTINED/REVIEW_REQUIRED rule is floored at REVIEW_REQUIRED and can never be CLEAN. Multi-record files
without a record-level audit are REVIEW_REQUIRED as a whole (no averaging).

## Opening Shadow (HIGH-2)

- **1B/1C** — the cumulative artifact's internal rows span 2026-06-24..07-30 (including 06-25 and 07-24).
  It cannot be date-filtered at admission and no record-level audit exists ⇒ `REVIEW_REQUIRED` until one does.
- **1A** — independently checked, also cumulative (rows 2026-08-03..09-24). It has per-row persisted dates and
  native ids, so it is audited per record. The current artifact contains a producer-`VALID` row whose trigger
  day (2026-09-09) is a forward-coverage-invalid day, so it is NOT proven at file granularity ⇒ `REVIEW_REQUIRED`.

## Structural forward-coverage contract (HIGH-3)

`day_validity.py` defines `MIN_FORWARD_COVERAGE = 0.95` and persists each day's decision in
`reports/evaluation/daily/<day>/q9_day_validity.json` as blockers with `invalidates_day: true`. The registry
does **not** hold a date list. `forward_coverage_invalid_days` reads the persisted decision (blocker codes
`invalid_forward_observation` / `forward_observation_unavailable` with `invalidates_day == True`) and
`derive_forward_coverage_rules` produces, for each such day, a `FIELD_INVALID` rule
(`INSUFFICIENT_SOURCE_COVERAGE`) on that day's evaluation-daily and quant-shadow candidate paths with
`formal_day_eligibility`, `forward_outcome`, `forward_usable_coverage`. A future low-coverage day needs no code
change. Malformed validity payloads are reported as rejected, never silently valid. Other invalidating
blockers (`full_session_coverage_not_confirmed`, 20 days) belong to a different contract and are **not** encoded;
the coverage manifest reports them.

**Incident C numeric discrepancy: UNRESOLVED. Classification impact: NONE.** The prose says 75.47% / 465 rows;
the persisted artifact says 44.67% usable, 476 unavailable, 573 invalid. Nothing in the registry reads either
number — only `invalidates_day` under the global contract. Kept as research/measurement debt.

## Controlled mock lane (item 13)

Rank/attribution fields (`scanner_rank`, `selected_rank`, the four `*_to_entry_delay_sec` fields) stay
`FIELD_INVALID`. The former positive clean domain for outcome fields is **removed**: entry/exit price,
`fill_status`, `realized_pnl(_pct)` are field-level `REVIEW_REQUIRED` (`Resolution.field_status`), because no
authority certifies them and no exact broker/order/fill provenance is persisted for a narrow verifier. The two
facts are compatible: rank = FIELD_INVALID, P&L = REVIEW_REQUIRED.

## Preserved (unchanged by FIX1)

Incident A stale-fill scope (4 trade ids, 8 order ids scoped to symbol+date, the synthesized-bundle marker on
that day only, the quarantine dir); Q12 Calc3 (CLEAN = 0, adapter BLOCKED, V1 `crypto_equity_confirm` invalid,
V1 `forward/` REVIEW_REQUIRED); Q10 Semiconductor 2026-06-23 (missing `evaluation_program_id` ⇒ NO_RULE, never
inferred); registry cleanliness vs adapter eligibility (Q9, Q11 v1, Q12 Calc3, Q18, rank1_feature_mart stay BLOCKED
regardless of any registry status).

## Coverage = FILE-LEVEL ARTIFACT COVERAGE only (HIGH-4)

The manifest is labelled `UEF-5.1 FILE-LEVEL ARTIFACT COVERAGE` and carries
`complete_historical_coverage: false`. It inspects 11 bounded families, file by file. Per family and in `totals`
it reports `discovered`, `classified` (parsed and resolved), `skipped_oversize`, `parse_failed`,
`unsupported_format`, `unclassified`; `discovered = classified + skipped_oversize + parse_failed +
unsupported_format`. `record_level_not_scanned` explicitly lists the sources it does **not** inspect:
events.jsonl, quant-shadow candidates, Q9 windows, evaluation-daily rows, per-trade artifacts, the evidence
ledger, controlled-lane ledgers, canonical run artifacts, `b.jsonl`, and everything else under reports/ and data/.
File-level coverage does not prove those streams clean. Registry classification and adapter eligibility are
reported side by side and independent.

## How UEF-5.2 must consume it

Build a descriptor per artifact (and per internal record), run the domain verifiers, call
`resolve_evidence_status(descriptor, registry, audits=..., records=...)`, and require adapter eligibility **and**
`Resolution.field_usable(field)` before a field enters recompute. `QUARANTINED`, `REVIEW_REQUIRED`, `NO_RULE`,
and any `FIELD_INVALID`/review field must be skipped with explicit accounting, never treated as CLEAN.
