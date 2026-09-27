"""UEF-5.1 seed data: known-incident negative rules, CANDIDATE clean domains,
the family PositiveCleanVerifiers (FIX1), structural day-validity rule
derivation, and the (separate) UEF adapter-eligibility table.

FIX1: a clean domain only makes evidence a candidate for positive audit. CLEAN
requires the domain's verifier to return PROVEN_CLEAN with every declared
required check passed, from PERSISTED fields only. Where persisted fields cannot
prove cleanliness the outcome is REVIEW_REQUIRED (a false REVIEW_REQUIRED is
preferable to a false CLEAN).

Everything below was re-verified against docs/code/on-disk artifacts, not
prose summaries alone. Where the authority was silent or ambiguous the rule
is REVIEW_REQUIRED, never CLEAN. Human notes are explanatory only.

Field names in `invalid_fields` are LOGICAL evidence field names (the names
the legacy artifacts/evaluation rows use), so a consumer can ask
`Resolution.field_usable("scanner_rank")`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Optional

from .clean_evidence_registry import (
    CleanDomain,
    EvidenceRegistry,
    EvidenceRule,
    EvidenceStatus as S,
    PositiveAuditResult,
    PositiveOutcome,
    ReasonCode as R,
    build_registry,
    make_scope,
)

REGISTRY_VERSION = "uef5_1_fix1.2026-09-26.v1"

# Contract strings (kept as literals so this module stays stdlib-only and
# never imports production code; tests assert they equal the real constants).
Q10_SEMI_SCHEMA = "baseline_samsung_hynix_forward_returns.v1"
Q10_SEMI_PROGRAM = "Q10_LARGECAP_BASELINE_CONTROL"
Q12_CALC1_SCHEMA = "baseline_btc_woori_forward_returns.v1"
Q12_PROGRAM = "Q12_BTC_WOORI_TECH_BASELINE"
Q12_CALC2_SCHEMA = "q12_btc_woori_hypothesis_daily.v1"
OPENING_1A_SCHEMA = "latent_reactivation_forward.v1"
OPENING_1BC_SCHEMA = "opening_rank1_longitudinal.v1"
Q10_INDEX_SCHEMA = "q10_korea_lead_market_forward_validation.v1"
Q10_INDEX_PROGRAM = "Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION"
Q11_PROGRAM = "Q11_OPENING_SURGE_MARKET_REVERSAL"
Q11_V2_SCHEMA = "opportunity_engine_virtual_trades.v2"
Q11_V1_SCHEMA = "opportunity_engine_virtual_trades.v1"
Q9_RECAP_SCHEMA = "post_exit_shadow_recap.v1"

# Descriptor family keys.
F_Q10_SEMI = "q10_semiconductor"
F_Q12_CALC1 = "q12_calc1"
F_Q12_CALC2 = "q12_calc2"
F_OPENING_1A = "opening_shadow_1a"
F_OPENING_1BC = "opening_shadow_1bc"
F_Q10_INDEX = "q10_index"
F_Q11 = "q11_virtual_probe"
F_Q9 = "q9_post_exit_shadow"
F_Q12_CALC3 = "q12_calc3_vnext"
F_EVENTS = "events_jsonl"
F_QUANT_SHADOW = "quant_shadow_candidates"
F_Q9_WINDOWS = "q9_decision_windows"
F_EVIDENCE_LEDGER = "evidence_ledger"
F_CONTROLLED_LANE_TRADE = "controlled_mock_lane_trade"

_A_DOC = "docs/q13_q14_validation/broker_stale_fill_reconciliation_fix_2026-07-22.md"
_B_DOC = "docs/q13_q14_validation/evaluation_integrity_close_2026-07-30.md"
_B_SCRIPT = "scripts/clean_evaluation_test_contamination.py"
_B_LATE = "git:981acd1,8262a64,a4e3ffa (2026-08-31..2026-09-01 pytest isolation fixes)"
_C_CODE = "libs/reporting/evaluation/day_validity.py"
_D_DOC = "docs/daily_patch/2026-09-07_q10_vwap_and_opening_alpha_integrity.md"
_D_CODE = "libs/reporting/evaluation/entry_timing_attribution.py"
_E_DOC = "docs/evaluation/q12_vnext_delivery_time_alignment.md"
_FREEZE = "docs/research/research_portfolio_freeze_2026-09-16.md"

_SYNTH_ID_PATTERN = r"(?i).*(fixture|synthetic|pytest).*"
_SYNTH_ID_PATTERN_WITH_TEST = r"(?i).*(test|fixture|synthetic).*"
_NON_KRX_SYMBOL = r"(?!\d{6}$).+"
# baseline_<program>_<date>_<symbol>_<n> whose <symbol> is not exactly 6 digits
_BASELINE_NON_KRX_RUN = (
    r"baseline_(?:samsung_hynix|btc_woori_tech)_[^_]+_(?!\d{6}_)[^_]+_\d+"
)

_STALE_ORDER_IDS = (
    "0088903", "0096087", "0098982", "0101279",
    "0102394", "0104714", "0115324", "0130402",
)

_Q9_CLEANED_DAYS = (
    "2026-06-22", "2026-06-23", "2026-06-25", "2026-07-24", "2026-07-25",
    "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30",
)

_CONTROLLED_LANES = ("BTC_WOORI", "Q10_INDEX", "Q10_SEMICONDUCTOR")
_CONTROLLED_LANE_OUTCOME_FIELDS = (
    "entry_price",
    "exit_price",
    "fill_status",
    "realized_pnl",
    "realized_pnl_pct",
)
_CONTROLLED_LANE_ATTRIBUTION_FIELDS = (
    "decision_window_to_entry_delay_sec",
    "scanner_rank",
    "scanner_to_entry_delay_sec",
    "selected_rank",
    "selected_to_entry_delay_sec",
    "strategist_to_entry_delay_sec",
)


def _rules() -> list[EvidenceRule]:
    rules: list[EvidenceRule] = []

    # ---- Incident A: 2026-07-17 stale ka10076 mock-broker fills (001790) ----
    rules += [
        EvidenceRule(
            "A_STALE_FILL_TRADE_IDS", S.QUARANTINED, R.STALE_MOCK_FILL,
            make_scope(date_start="2026-07-17", date_end="2026-07-17",
                       native_ids={"trade_id": [r"TRD_20260717_001790_0[1-4]"]}),
            (_A_DOC,), "The 4 false 001790 round-trips; exact trade ids only.",
        ),
        EvidenceRule(
            "A_STALE_FILL_ORDER_IDS", S.QUARANTINED, R.STALE_MOCK_FILL,
            make_scope(date_start="2026-07-17", date_end="2026-07-17",
                       markers_equals={"symbol": ["001790"]},
                       native_ids={"order_id": list(_STALE_ORDER_IDS)}),
            (_A_DOC, "data/logs/artifact_quarantine/2026-07-17_stale_ka10076/**/lifecycle_bundle.json"),
            "The 8 BUY/SELL order ids of those trades, scoped to symbol+date (order ids restart per day).",
        ),
        EvidenceRule(
            "A_STALE_FILL_SYNTH_BUNDLE", S.QUARANTINED, R.STALE_MOCK_FILL,
            make_scope(date_start="2026-07-17", date_end="2026-07-17",
                       markers_equals={"recovery_source": ["broker_synthesized_missing_trade_bundle"]}),
            (_A_DOC,), "Broker-synthesized bundles on the incident day only; other dates untouched.",
        ),
        EvidenceRule(
            "A_STALE_FILL_QUARANTINE_DIR", S.QUARANTINED, R.STALE_MOCK_FILL,
            make_scope(path_globs=["data/logs/artifact_quarantine/2026-07-17_stale_ka10076/**"]),
            (_A_DOC,), "Already-quarantined evidence (69 files); pre-fix daily outputs included.",
        ),
        EvidenceRule(
            "A_REGENERATED_DAILY_20260717", S.REVIEW_REQUIRED, R.UNRESOLVED_SOURCE_PROVENANCE,
            make_scope(path_globs=["reports/evaluation/daily/2026-07-17/**"]),
            (_A_DOC, "reports/evaluation/daily/2026-07-17/q9_day_validity.json"),
            "Regenerated after the fix; q9_day_validity is INVALID for an unrelated "
            "forward-observation reason no doc explains, so it cannot be classified losslessly.",
        ),
    ]

    # ---- Incident B: pytest synthetic contamination of production paths ----
    rules += [
        EvidenceRule(
            "B_TEST_QUARANTINE_DIR", S.QUARANTINED, R.TEST_SYNTHETIC_CONTAMINATION,
            make_scope(path_globs=["data/logs/dev/testing/quarantine/**"]),
            (_B_DOC, _B_SCRIPT), "Contents removed by the cleanup script (552 files, stamp 20260730T092633Z).",
        ),
        EvidenceRule(
            "B_SYNTHETIC_RUN_ID_ANY_FAMILY", S.QUARANTINED, R.TEST_SYNTHETIC_CONTAMINATION,
            make_scope(marker_patterns={"run_id": [_SYNTH_ID_PATTERN]}),
            (_B_DOC, _B_SCRIPT + "::_test_event"),
            "run_id containing fixture/synthetic/pytest, any family (record-level identification).",
        ),
        EvidenceRule(
            "B_SYNTHETIC_DECISION_ID_ANY_FAMILY", S.QUARANTINED, R.TEST_SYNTHETIC_CONTAMINATION,
            make_scope(marker_patterns={"decision_id": [_SYNTH_ID_PATTERN]}),
            (_B_DOC, "libs/reporting/evaluation/artifact_inventory.py::_synthetic_identity"),
            "decision_id containing fixture/synthetic/pytest, any family. Plain 'test' is only applied to Q9 windows.",
        ),
        EvidenceRule(
            "B_EVENTS_BASELINE_NON_KRX_RUN", S.QUARANTINED, R.TEST_SYNTHETIC_CONTAMINATION,
            make_scope(family=F_EVENTS, marker_patterns={"run_id": [_BASELINE_NON_KRX_RUN]}),
            (_B_DOC, _B_SCRIPT + "::_BASELINE_RUN_RE"), "Baseline run ids whose symbol token is not 6 digits.",
        ),
        EvidenceRule(
            "B_EVENTS_NON_KRX_SYMBOL", S.QUARANTINED, R.TEST_SYNTHETIC_CONTAMINATION,
            make_scope(family=F_EVENTS, marker_patterns={"symbol": [_NON_KRX_SYMBOL]}),
            (_B_DOC, _B_SCRIPT + "::_KRX_SYMBOL_RE"), "Non-6-digit symbol in a live event row.",
        ),
        EvidenceRule(
            "B_QUANT_SHADOW_NON_KRX_SYMBOL", S.QUARANTINED, R.TEST_SYNTHETIC_CONTAMINATION,
            make_scope(family=F_QUANT_SHADOW, marker_patterns={"symbol": [_NON_KRX_SYMBOL]}),
            (_B_DOC, _B_SCRIPT + "::clean_shadow_files"), "Non-6-digit symbol in a quant-shadow file.",
        ),
        EvidenceRule(
            "B_Q9_WINDOWS_NON_KRX_SYMBOL", S.QUARANTINED, R.TEST_SYNTHETIC_CONTAMINATION,
            make_scope(family=F_Q9_WINDOWS, marker_patterns={"symbol": [_NON_KRX_SYMBOL]}),
            (_B_DOC, "libs/reporting/evaluation/artifact_inventory.py::is_synthetic_evaluation_row"),
            "Non-6-digit symbol in a Q9 decision window.",
        ),
    ]
    for field in ("candidate_pool_id", "decision_id", "q9_decision_id", "run_id"):
        rules.append(
            EvidenceRule(
                f"B_Q9_WINDOWS_TEST_{field.upper()}", S.QUARANTINED, R.TEST_SYNTHETIC_CONTAMINATION,
                make_scope(family=F_Q9_WINDOWS, marker_patterns={field: [_SYNTH_ID_PATTERN_WITH_TEST]}),
                (_B_DOC, "libs/reporting/evaluation/artifact_inventory.py::_synthetic_identity"),
                f"{field} containing test/fixture/synthetic.",
            )
        )
    rules += [
        EvidenceRule(
            "B_Q9_WINDOWS_CLEANED_IN_PLACE", S.REVIEW_REQUIRED, R.UNRESOLVED_SOURCE_PROVENANCE,
            make_scope(path_globs=[f"reports/operator_summary/daily/{d}/q9_decision_windows.json" for d in _Q9_CLEANED_DAYS]),
            (_B_DOC,), "Cleaned in place by a heuristic detector (311 windows removed across these 9 days); "
            "aggregates computed before 2026-07-30 are downgraded by the doc.",
        ),
        EvidenceRule(
            "B_POST_0730_PYTEST_LEAK_PATHS", S.QUARANTINED, R.TEST_SYNTHETIC_CONTAMINATION,
            make_scope(path_globs=[
                "reports/canonical/*/trace-r1/**",
                "reports/canonical/*/trace-r2/**",
                "reports/canonical/*/strategist-llm-test/**",
            ]),
            (_B_LATE,), "Confirmed pytest leaks found after 2026-07-30; no cleanup script covers them.",
        ),
        EvidenceRule(
            "B_ROOT_B_JSONL", S.REVIEW_REQUIRED, R.UNRESOLVED_SOURCE_PROVENANCE,
            make_scope(path_globs=["b.jsonl"]),
            (_B_LATE,), "Named as a confirmed pytest leak in commit 981acd1 but its content was never audited.",
        ),
        EvidenceRule(
            "B_EVIDENCE_LEDGER_LEAK_WINDOW", S.REVIEW_REQUIRED, R.UNRESOLVED_SOURCE_PROVENANCE,
            make_scope(family=F_EVIDENCE_LEDGER, date_start="2026-07-31", date_end="2026-09-01"),
            (_B_LATE,), "Ledger write surface fixed 2026-09-01; test rows in the window are not separately identifiable.",
        ),
    ]

    # ---- Incident C: NOT a date exception any more. The 2026-07-24 day is one instance of the
    # persisted global forward-coverage contract; its rules are DERIVED from q9_day_validity.json
    # (see derive_forward_coverage_rules), never hard-coded per date.

    # ---- Incident D: controlled mock lane scanner attribution ----
    rules += [
        EvidenceRule(
            "D_CONTROLLED_LANE_ATTRIBUTION_WINDOW", S.FIELD_INVALID, R.INVALID_SCANNER_ATTRIBUTION,
            make_scope(date_start="2026-08-28", date_end="2026-09-07",
                       markers_equals={"lane_id": list(_CONTROLLED_LANES)}),
            (_D_DOC, _D_CODE), "Fabricated scanner rank 0 / negative scanner-to-entry delay for independent lanes. "
            "Outcome/P&L fields are NOT certified by any authority: field-level REVIEW_REQUIRED.",
            invalid_fields=_CONTROLLED_LANE_ATTRIBUTION_FIELDS,
            review_fields=_CONTROLLED_LANE_OUTCOME_FIELDS, review_reason_code=R.UNRESOLVED_SOURCE_PROVENANCE,
        ),
        EvidenceRule(
            "D_CONTROLLED_LANE_ATTRIBUTION_TRADES", S.FIELD_INVALID, R.INVALID_SCANNER_ATTRIBUTION,
            make_scope(native_ids={"trade_id": [r"TRD_20260902_251340_01", r"TRD_20260907_000660_01"]}),
            (_D_DOC, "reports/trades/2026-09-02/0900/TRD_20260902_251340_01",
             "reports/trades/2026-09-07/0900/TRD_20260907_000660_01"),
            "The only two controlled-lane trades in the window; the 09-02 one was never regenerated and "
            "raw entry.json for both still carries selected_rank 0.",
            invalid_fields=_CONTROLLED_LANE_ATTRIBUTION_FIELDS,
            review_fields=_CONTROLLED_LANE_OUTCOME_FIELDS, review_reason_code=R.UNRESOLVED_SOURCE_PROVENANCE,
        ),
    ]

    # ---- Incident E: Q12 Calc3 timing alignment (semantic, not raw corruption) ----
    v1 = "reports/evaluation/baseline_btc_woori_tech/vnext/Q12_CRYPTO_EQUITY_CONFIRM_V1_SHADOW"
    v2 = "reports/evaluation/baseline_btc_woori_tech/vnext/Q12_CRYPTO_EQUITY_CONFIRM_V2_ALIGNED_SHADOW"
    rules += [
        EvidenceRule(
            "E_Q12_V1_UNALIGNED_CONFIRMATION", S.FIELD_INVALID, R.INVALID_TIMING_ALIGNMENT,
            make_scope(path_globs=[v1 + "/**"]),
            (_E_DOC, "libs/reporting/baseline_btc_woori_tech/vnext/features.py"),
            "Friday BTC close (Sat 05:00 KST) vs Monday equity reaction (08:55) = 51h55m; V1 DIVERGENCE is not causal confirmation.",
            invalid_fields=("crypto_equity_confirm",),
        ),
        EvidenceRule(
            "E_Q12_V1_FORWARD_REVIEW", S.REVIEW_REQUIRED, R.INVALID_TIMING_ALIGNMENT,
            make_scope(path_globs=[v1 + "/*/forward/**"]),
            (_E_DOC,), "Docs only condemn the confirmation label; whether V1 forward outcomes are affected is unstated.",
        ),
        EvidenceRule(
            "E_Q12_V2_LEGACY_UNALIGNED_FIELD", S.FIELD_INVALID, R.INVALID_TIMING_ALIGNMENT,
            make_scope(path_globs=[v2 + "/**"]),
            (_E_DOC,), "V2 keeps the unaligned V1 direction only as an explicitly legacy field.",
            invalid_fields=("legacy_unaligned_direction",),
        ),
    ]

    # ---- Blocked-family evidence defects (registry-level, distinct from adapter eligibility) ----
    rules += [
        EvidenceRule(
            "BLK_Q11_V1_OBSERVED_PRICE_NOT_PERSISTED", S.REVIEW_REQUIRED, R.SOURCE_FIELD_NOT_PERSISTED,
            make_scope(family=F_Q11, schema_versions=[Q11_V1_SCHEMA]),
            (_FREEZE, "libs/reporting/evaluation/canonical/adapters/virtual_probe_adapter.py"),
            "Authentic evidence, but observed_price was never persisted for price-based checkpoints.",
        ),
        EvidenceRule(
            "BLK_Q9_EXIT_PRICE_AUTHORITY_NOT_PERSISTED", S.REVIEW_REQUIRED, R.SOURCE_FIELD_NOT_PERSISTED,
            make_scope(family=F_Q9, schema_versions=[Q9_RECAP_SCHEMA]),
            (_FREEZE, "libs/reporting/evaluation/canonical/adapters/q9_horizon_exit_adapter.py"),
            "Persisted artifact does not record which source branch resolved exit_price.",
        ),
    ]
    return rules


# ---------------------------------------------------------------------------
# Positive clean verifiers (UEF-5.1 FIX1)
#
# A verifier proves cleanliness ONLY from persisted fields of the artifact.
# Field ABSENT      -> check NOT_PROVEN   (=> REVIEW_REQUIRED)
# Field CONTRADICTS -> check INVALID      (=> REVIEW_REQUIRED, reason CONTRADICTED)
# Every check declared in the domain's `required_checks` must pass. Nothing is
# inferred from file names when a persisted contract field exists. What a
# verifier proves is structural/native-identity/provenance-field consistency;
# it is NOT a chain-of-custody proof against a perfect mimic, which is why the
# negative record-level rules keep dominating CLEAN.
# ---------------------------------------------------------------------------

KST = timezone(timedelta(hours=9))
_MISSING = object()
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_Q10_INDEX_GUARDS = {
    "executor_connection_allowed": False,
    "historical_backfill_allowed": False,
    "machine_learning_allowed": False,
    "main_strategy_change_allowed": False,
    "order_intent_allowed": False,
    "prospective_only": True,
    "threshold_optimization_allowed": False,
}
_Q10_INDEX_TARGET_SOURCES = {
    "samsung": "q10_current_day_minute_candles",
    "sk_hynix": "q10_current_day_minute_candles",
    "kospi": "kiwoom_ka20009_macro_snapshots",
    "kosdaq": "kiwoom_ka20009_macro_snapshots",
}
_CALC2_CONTRACT_ID = "q12_btc_woori_five_variable_validation.v1"
_BROKER_COST_SOURCE = "kiwoom.ka10170"

V_Q10_SEMI = "UEF5_V_Q10_SEMICONDUCTOR_V1"
V_Q12_CALC1 = "UEF5_V_Q12_CALC1_V1"
V_Q12_CALC2 = "UEF5_V_Q12_CALC2_V1"
V_OPENING_1A = "UEF5_V_OPENING_1A_V1"
V_Q10_INDEX = "UEF5_V_Q10_INDEX_V1"
V_Q11_V2 = "UEF5_V_Q11_V2_V1"

_BASELINE_CHECKS = (
    "behavior_contract", "broker_cost_source", "file_day_matches_path", "program_exact",
    "records_native_identity", "records_symbol_native", "row_count_consistent", "schema_exact",
)
Q10_SEMI_CHECKS = _BASELINE_CHECKS + ("forward_coverage_valid_day",)
Q12_CALC1_CHECKS = _BASELINE_CHECKS
Q12_CALC2_CHECKS = (
    "behavior_contract", "btc_delivery_source_canonical", "contract_id_exact", "epoch_date_scope",
    "evidence_phase_prospective", "file_day_matches_path", "order_execution_disabled",
    "prospective_window", "schema_exact",
)
OPENING_1A_CHECKS = (
    "behavior_contract", "forward_coverage_valid_day", "policy_change_not_authorized",
    "records_date_scope", "records_native_identity", "schema_exact",
)
Q10_INDEX_CHECKS = (
    "file_day_matches_path", "guards_contract", "program_exact", "reaction_sources_authoritative",
    "schema_exact",
)
Q11_V2_CHECKS = (
    "behavior_contract", "file_day_matches_path", "program_exact", "records_native_identity",
    "records_order_disabled", "schema_exact", "trade_count_consistent",
)


@dataclass(frozen=True)
class VerificationContext:
    trading_date: Optional[str] = None  # ISO date parsed from the artifact path, if any
    invalid_forward_days: frozenset = frozenset()  # structural forward-coverage-invalid days
    load_sibling: Optional[Callable[[str], Any]] = None  # file name in the same dir -> parsed JSON | None


class _Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.not_proven: list[str] = []
        self.invalid: list[str] = []

    def ok(self, check_id: str, cond: bool, *, present: bool = True) -> None:
        if not present:
            self.not_proven.append(check_id)
        elif cond:
            self.passed.append(check_id)
        else:
            self.invalid.append(check_id)

    def eq(self, check_id: str, actual: Any, expected: Any) -> None:
        self.ok(check_id, actual == expected, present=actual is not _MISSING)

    def result(self, verifier_id: str, records: int = 0) -> PositiveAuditResult:
        failed = tuple(sorted(set(self.not_proven) | set(self.invalid)))
        if self.invalid:
            outcome = PositiveOutcome.INVALID
        elif self.not_proven:
            outcome = PositiveOutcome.NOT_PROVEN
        else:
            outcome = PositiveOutcome.PROVEN_CLEAN
        return PositiveAuditResult(verifier_id, outcome, tuple(sorted(self.passed)), failed, records)


def _not_proven(verifier_id: str, required: tuple[str, ...]) -> PositiveAuditResult:
    return PositiveAuditResult(verifier_id, PositiveOutcome.NOT_PROVEN, (), tuple(sorted(required)), 0)


def _get(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return _MISSING
        obj = obj[key]
    return obj


def _valid_day(value: Any) -> bool:
    if not isinstance(value, str) or not _ISO_DAY.match(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _kst_date(epoch: Any) -> Optional[str]:
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=KST).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _compact_to_iso(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _verify_baseline_forward(
    payload: Any, ctx: VerificationContext, *, verifier_id: str, schema: str, program: str,
    id_prefix: str, required: tuple[str, ...], forward_day_check: bool,
) -> PositiveAuditResult:
    if not isinstance(payload, dict):
        return _not_proven(verifier_id, required)
    c = _Checks()
    c.eq("schema_exact", _get(payload, "schema_version"), schema)
    c.eq("program_exact", _get(payload, "evaluation_program_id"), program)
    day = _get(payload, "day")
    c.ok("file_day_matches_path", day == ctx.trading_date, present=day is not _MISSING and ctx.trading_date is not None)
    c.eq("behavior_contract", _get(payload, "behavior_effect"), "evaluation_only")
    c.eq("broker_cost_source", _get(payload, "cost_model", "source"), _BROKER_COST_SOURCE)
    rows = _get(payload, "rows")
    row_count = _get(payload, "row_count")
    c.ok("row_count_consistent", isinstance(rows, list) and row_count == len(rows),
         present=rows is not _MISSING and row_count is not _MISSING and isinstance(rows, list))
    rows_list = rows if isinstance(rows, list) else []
    sym_ok, sym_present = True, True
    id_ok, id_present = True, True
    id_re = re.compile(rf"^{re.escape(id_prefix)}_(\d{{8}})_(\d{{9,10}})$")
    for row in rows_list:
        if not isinstance(row, dict):
            sym_present = id_present = False
            continue
        symbol = row.get("symbol", _MISSING)
        if symbol is _MISSING:
            sym_present = False
        elif not (isinstance(symbol, str) and re.fullmatch(r"\d{6}", symbol)):
            sym_ok = False
        rid = row.get("baseline_decision_id", _MISSING)
        if rid is _MISSING:
            id_present = False
            continue
        m = id_re.match(rid) if isinstance(rid, str) else None
        if not m or _compact_to_iso(m.group(1)) != day or _kst_date(int(m.group(2))) != day:
            id_ok = False
    c.ok("records_symbol_native", sym_ok, present=sym_present)
    c.ok("records_native_identity", id_ok, present=id_present)
    if forward_day_check:
        c.ok("forward_coverage_valid_day", day not in ctx.invalid_forward_days, present=day is not _MISSING)
    return c.result(verifier_id, len(rows_list))


def verify_q10_semiconductor(payload: Any, ctx: VerificationContext) -> PositiveAuditResult:
    return _verify_baseline_forward(
        payload, ctx, verifier_id=V_Q10_SEMI, schema=Q10_SEMI_SCHEMA, program=Q10_SEMI_PROGRAM,
        id_prefix="BSH", required=Q10_SEMI_CHECKS, forward_day_check=True,
    )


def verify_q12_calc1(payload: Any, ctx: VerificationContext) -> PositiveAuditResult:
    # Calc1 persists no Q9 comparison; no persisted dependence on Q9 forward
    # coverage is asserted, so the forward-day check is intentionally not applied.
    return _verify_baseline_forward(
        payload, ctx, verifier_id=V_Q12_CALC1, schema=Q12_CALC1_SCHEMA, program=Q12_PROGRAM,
        id_prefix="BTW", required=Q12_CALC1_CHECKS, forward_day_check=False,
    )


def verify_q12_calc2(payload: Any, ctx: VerificationContext) -> PositiveAuditResult:
    if not isinstance(payload, dict):
        return _not_proven(V_Q12_CALC2, Q12_CALC2_CHECKS)
    c = _Checks()
    c.eq("schema_exact", _get(payload, "schema_version"), Q12_CALC2_SCHEMA)
    c.eq("contract_id_exact", _get(payload, "contract_id"), _CALC2_CONTRACT_ID)
    day = _get(payload, "day")
    c.ok("file_day_matches_path", day == ctx.trading_date, present=day is not _MISSING and ctx.trading_date is not None)
    c.eq("behavior_contract", _get(payload, "behavior_effect"), "observation_only")
    c.eq("evidence_phase_prospective", _get(payload, "evidence_phase"), "PROSPECTIVE")
    start = _get(payload, "prospective_start_day")
    c.ok("prospective_window", _valid_day(start) and _valid_day(day) and day >= start,
         present=start is not _MISSING and day is not _MISSING)
    oea = _get(payload, "order_execution_allowed")
    oi = _get(payload, "order_intent")
    c.ok("order_execution_disabled", oea is False and oi is None, present=oea is not _MISSING and oi is not _MISSING)
    # Persisted delivery source is present in only some historical files; absence is NOT_PROVEN.
    c.eq("btc_delivery_source_canonical", _get(payload, "btc_delivery_source"), "canonical_0855_capture")
    epochs: list[Any] = []
    target = _get(payload, "features", "btc_0855", "target_epoch")
    entry_methods = _get(payload, "features", "entry_methods")
    if isinstance(entry_methods, dict):
        for em in entry_methods.values():
            if isinstance(em, dict) and em.get("entry_epoch") is not None:
                epochs.append(em["entry_epoch"])
    c.ok("epoch_date_scope", _kst_date(target) == day and all(_kst_date(e) == day for e in epochs),
         present=target is not _MISSING and isinstance(entry_methods, dict))
    return c.result(V_Q12_CALC2)


def verify_q10_index(payload: Any, ctx: VerificationContext) -> PositiveAuditResult:
    if not isinstance(payload, dict):
        return _not_proven(V_Q10_INDEX, Q10_INDEX_CHECKS)
    c = _Checks()
    c.eq("schema_exact", _get(payload, "schema_version"), Q10_INDEX_SCHEMA)
    c.eq("program_exact", _get(payload, "evaluation_program_id"), Q10_INDEX_PROGRAM)
    day = _get(payload, "day")
    c.ok("file_day_matches_path", day == ctx.trading_date, present=day is not _MISSING and ctx.trading_date is not None)
    c.eq("guards_contract", _get(payload, "guards"), _Q10_INDEX_GUARDS)
    sibling = ctx.load_sibling("q10_actual_market_reactions.json") if ctx.load_sibling else None
    if not isinstance(sibling, dict):
        c.ok("reaction_sources_authoritative", False, present=False)
    else:
        targets = _get(sibling, "targets")
        actual = (
            {k: (v.get("source") if isinstance(v, dict) else None) for k, v in targets.items()}
            if isinstance(targets, dict) else None
        )
        c.ok("reaction_sources_authoritative", actual == _Q10_INDEX_TARGET_SOURCES and sibling.get("day") == day,
             present=actual is not None)
    return c.result(V_Q10_INDEX)


def verify_q11_v2(payload: Any, ctx: VerificationContext) -> PositiveAuditResult:
    if not isinstance(payload, dict):
        return _not_proven(V_Q11_V2, Q11_V2_CHECKS)
    c = _Checks()
    c.eq("schema_exact", _get(payload, "schema_version"), Q11_V2_SCHEMA)
    c.eq("program_exact", _get(payload, "evaluation_program_id"), Q11_PROGRAM)
    day = _get(payload, "day")
    c.ok("file_day_matches_path", day == ctx.trading_date, present=day is not _MISSING and ctx.trading_date is not None)
    c.eq("behavior_contract", _get(payload, "behavior_effect"), "shadow_only")
    trades = _get(payload, "trades")
    count = _get(payload, "trade_count")
    c.ok("trade_count_consistent", isinstance(trades, list) and count == len(trades),
         present=trades is not _MISSING and count is not _MISSING and isinstance(trades, list))
    trades_list = trades if isinstance(trades, list) else []
    id_ok, id_present, oe_ok, oe_present = True, True, True, True
    id_re = re.compile(r"^OE_TRD_(\d{6})_(\d{9,10})$")
    for t in trades_list:
        if not isinstance(t, dict):
            id_present = oe_present = False
            continue
        tid = t.get("trade_id", _MISSING)
        if tid is _MISSING:
            id_present = False
        else:
            m = id_re.match(tid) if isinstance(tid, str) else None
            entry = t.get("entry_epoch")
            if not m or t.get("symbol") != m.group(1) or entry != int(m.group(2)) or _kst_date(entry) != day:
                id_ok = False
        flag = t.get("order_execution_allowed", _MISSING)
        if flag is _MISSING:
            oe_present = False
        elif flag is not False:
            oe_ok = False
    c.ok("records_native_identity", id_ok, present=id_present)
    c.ok("records_order_disabled", oe_ok, present=oe_present)
    return c.result(V_Q11_V2, len(trades_list))


def verify_opening_1a(payload: Any, ctx: VerificationContext) -> PositiveAuditResult:
    if not isinstance(payload, dict):
        return _not_proven(V_OPENING_1A, OPENING_1A_CHECKS)
    c = _Checks()
    c.eq("schema_exact", _get(payload, "schema_version"), OPENING_1A_SCHEMA)
    c.eq("behavior_contract", _get(payload, "behavior_effect"), "observation_only")
    c.eq("policy_change_not_authorized", _get(payload, "policy_change_authorized"), False)
    through = _get(payload, "through_day")
    rows = _get(payload, "rows")
    rows_list = rows if isinstance(rows, list) else []
    watch_re = re.compile(r"^LATENT:OPEN_\d+_\d+_RANK\d+_\d+M:(\d{8}):\d{6}:\d+$")
    dec_re = re.compile(r"^Q9_(\d{8})_[0-9a-f]{32}$")
    id_ok, id_present = True, isinstance(rows, list)
    scope_ok, scope_present = True, isinstance(rows, list) and _valid_day(through)
    fwd_ok = True
    for r in rows_list:
        if not isinstance(r, dict):
            id_present = scope_present = False
            continue
        initial, trigger = r.get("initial_day"), r.get("trigger_day")
        wid, tdid, symbol = r.get("watch_id"), r.get("trigger_decision_id"), r.get("symbol")
        if not (isinstance(wid, str) and isinstance(tdid, str) and isinstance(symbol, str)):
            id_present = False
        else:
            wm, dm = watch_re.match(wid), dec_re.match(tdid)
            if (
                not wm or not dm or not re.fullmatch(r"\d{6}", symbol)
                or not _valid_day(initial) or not _valid_day(trigger)
                or _compact_to_iso(wm.group(1)) != initial or _compact_to_iso(dm.group(1)) != trigger
            ):
                id_ok = False
        if not (_valid_day(initial) and _valid_day(trigger) and _valid_day(through)):
            scope_present = False
        elif not (initial <= trigger <= through):
            scope_ok = False
        # Only rows the producer itself marks VALID are ingested as evidence.
        if r.get("trigger_day_integrity_status") == "VALID":
            if initial in ctx.invalid_forward_days or trigger in ctx.invalid_forward_days:
                fwd_ok = False
    c.ok("records_native_identity", id_ok, present=id_present)
    c.ok("records_date_scope", scope_ok, present=scope_present)
    c.ok("forward_coverage_valid_day", fwd_ok, present=isinstance(rows, list))
    return c.result(V_OPENING_1A, len(rows_list))


VERIFIERS: dict[str, Callable[[Any, VerificationContext], PositiveAuditResult]] = {
    V_Q10_SEMI: verify_q10_semiconductor,
    V_Q12_CALC1: verify_q12_calc1,
    V_Q12_CALC2: verify_q12_calc2,
    V_OPENING_1A: verify_opening_1a,
    V_Q10_INDEX: verify_q10_index,
    V_Q11_V2: verify_q11_v2,
}


# ---------------------------------------------------------------------------
# Candidate clean domains (NOT cleanliness claims -- see CleanDomain)
# ---------------------------------------------------------------------------

def _domains() -> list[CleanDomain]:
    fr = "docs/research/uef4_legacy_family_inventory.md"
    return [
        CleanDomain(
            "CD_Q10_SEMICONDUCTOR",
            make_scope(family=F_Q10_SEMI, schema_versions=[Q10_SEMI_SCHEMA], program_ids=[Q10_SEMI_PROGRAM],
                       path_globs=["reports/evaluation/baseline_samsung_hynix/*/baseline_samsung_hynix_forward_returns.json"]),
            (fr, "libs/reporting/evaluation/canonical/adapters/q10_semiconductor.py"),
            "Program id is required: an older file lacking it is deliberately left NO_RULE. Persists a Q9 "
            "comparison, so its day must not be a structural forward-coverage-invalid day.",
            verifier_id=V_Q10_SEMI, required_checks=Q10_SEMI_CHECKS,
        ),
        CleanDomain(
            "CD_Q12_CALC1",
            make_scope(family=F_Q12_CALC1, schema_versions=[Q12_CALC1_SCHEMA], program_ids=[Q12_PROGRAM],
                       path_globs=["reports/evaluation/baseline_btc_woori_tech/*/baseline_btc_woori_forward_returns.json"]),
            (fr, "libs/reporting/evaluation/canonical/adapters/q12_baseline_btc_woori.py"),
            "Calc1 reuses the Q10 engine unmodified (CONSUMER_ONLY per the freeze doc).",
            verifier_id=V_Q12_CALC1, required_checks=Q12_CALC1_CHECKS,
        ),
        CleanDomain(
            "CD_Q12_CALC2",
            make_scope(family=F_Q12_CALC2, schema_versions=[Q12_CALC2_SCHEMA],
                       path_globs=["reports/evaluation/baseline_btc_woori_tech/*/q12_btc_woori_hypothesis_validation.json"]),
            (fr, "libs/reporting/evaluation/canonical/adapters/hypothesis_forward_adapter.py"),
            "Independent of the Calc3 timing defect. Requires the persisted canonical 08:55 delivery source "
            "and PROSPECTIVE phase; back-check files and files without a delivery source are not proven.",
            verifier_id=V_Q12_CALC2, required_checks=Q12_CALC2_CHECKS,
        ),
        CleanDomain(
            "CD_OPENING_SHADOW_1A",
            make_scope(family=F_OPENING_1A, schema_versions=[OPENING_1A_SCHEMA],
                       path_globs=["reports/evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_forward.json"]),
            (fr, "libs/reporting/evaluation/canonical/adapters/opening_rank1_shadow.py"),
            "Cumulative multi-date rows (record-level dates persisted: initial_day/trigger_day). Audited per row; "
            "any producer-VALID row on a structural forward-coverage-invalid day makes the atomic file NOT_PROVEN.",
            verifier_id=V_OPENING_1A, required_checks=OPENING_1A_CHECKS,
        ),
        CleanDomain(
            "CD_OPENING_SHADOW_1BC",
            make_scope(family=F_OPENING_1BC, schema_versions=[OPENING_1BC_SCHEMA],
                       path_globs=["reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.json"]),
            (fr, "libs/reporting/evaluation/canonical/adapters/already_net_shadow_adapter.py"),
            "Cumulative multi-date artifact (rows span 2026-06-24..07-30, including 06-25 and 07-24). No record-level "
            "audit exists, so it can never be CLEAN at file granularity: no verifier => REVIEW_REQUIRED.",
        ),
        CleanDomain(
            "CD_Q10_INDEX",
            make_scope(family=F_Q10_INDEX, schema_versions=[Q10_INDEX_SCHEMA], program_ids=[Q10_INDEX_PROGRAM],
                       path_globs=[
                           "reports/evaluation/baseline_samsung_hynix/*/q10_forward_validation/q10_actual_market_reactions.json",
                           "reports/evaluation/baseline_samsung_hynix/*/q10_forward_validation/q10_expected_vs_actual.json",
                           "reports/evaluation/baseline_samsung_hynix/*/q10_forward_validation/q10_shadow_entry_comparison.json",
                       ]),
            (fr, "libs/reporting/evaluation/canonical/adapters/q10_index_reaction_adapter.py",
             "libs/reporting/evaluation/canonical/adapters/q10_index_directional_shadow_adapter.py"),
            "Each of the three day files requires the exact guard contract AND the day's reactions file to carry the "
            "authoritative target sources (minute candles / Kiwoom ka20009).",
            verifier_id=V_Q10_INDEX, required_checks=Q10_INDEX_CHECKS,
        ),
        CleanDomain(
            "CD_Q11_V2",
            make_scope(family=F_Q11, schema_versions=[Q11_V2_SCHEMA], program_ids=[Q11_PROGRAM],
                       path_globs=["reports/evaluation/opportunity_engine_shadow/*/opportunity_engine_virtual_trades.json"]),
            (fr, "libs/reporting/evaluation/canonical/adapters/virtual_probe_adapter.py"),
            "v2 only; adapter is provisionally closed pending Codex ratification. Trade ids embed symbol + entry epoch.",
            verifier_id=V_Q11_V2, required_checks=Q11_V2_CHECKS,
        ),
    ]


# ---------------------------------------------------------------------------
# Structural forward-coverage validity (global contract, not a date list)
#
# libs/reporting/evaluation/day_validity.py defines MIN_FORWARD_COVERAGE=0.95
# and persists the verdict per day in q9_day_validity.json as blockers with
# `invalidates_day: true`. Rules are DERIVED from that persisted decision, so a
# future low-coverage day needs no code change, and neither the (unreconciled)
# prose percentage nor the on-disk percentage is consulted.
# ---------------------------------------------------------------------------

DAY_VALIDITY_SCHEMA = "q9_day_validity.v1"
FORWARD_COVERAGE_BLOCKER_CODES = frozenset({"forward_observation_unavailable", "invalid_forward_observation"})
FORWARD_COVERAGE_INVALID_FIELDS = ("formal_day_eligibility", "forward_outcome", "forward_usable_coverage")
_DAY_VALIDITY_AUTHORITY = (
    "libs/reporting/evaluation/day_validity.py::MIN_FORWARD_COVERAGE",
    "reports/evaluation/daily/<day>/q9_day_validity.json (blockers[].invalidates_day)",
)


def forward_coverage_invalid_days(
    payloads: Iterable[tuple[str, Any]],
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """(label, parsed q9_day_validity payload)* -> ({day: sorted blocker codes}, rejected labels).
    A day qualifies iff a blocker with a forward-coverage code has
    invalidates_day == True. Malformed payloads are returned as rejected (never silently valid)."""
    days: dict[str, tuple[str, ...]] = {}
    rejected: list[str] = []
    for label, payload in payloads:
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != DAY_VALIDITY_SCHEMA
            or not _valid_day(payload.get("day"))
            or not isinstance(payload.get("blockers"), list)
        ):
            rejected.append(str(label))
            continue
        codes = sorted(
            {
                b["code"]
                for b in payload["blockers"]
                if isinstance(b, dict) and b.get("code") in FORWARD_COVERAGE_BLOCKER_CODES and b.get("invalidates_day") is True
            }
        )
        if codes:
            days[payload["day"]] = tuple(codes)
    return dict(sorted(days.items())), tuple(sorted(rejected))


def derive_forward_coverage_rules(days: Mapping[str, tuple[str, ...]]) -> list[EvidenceRule]:
    rules: list[EvidenceRule] = []
    for day in sorted(days):
        rules.append(
            EvidenceRule(
                "DV_FORWARD_COVERAGE_" + day.replace("-", ""), S.FIELD_INVALID, R.INSUFFICIENT_SOURCE_COVERAGE,
                make_scope(path_globs=[f"reports/evaluation/daily/{day}/**", f"data/logs/quant_shadow_candidates/{day}/**"]),
                _DAY_VALIDITY_AUTHORITY,
                "Derived from the persisted day-validity decision (" + ", ".join(days[day]) + "); same field "
                "invalidation for every day that fails the global forward-coverage contract.",
                invalid_fields=FORWARD_COVERAGE_INVALID_FIELDS,
            )
        )
    return rules


def build_default_registry(forward_invalid_days: Optional[Mapping[str, tuple[str, ...]]] = None) -> EvidenceRegistry:
    """Static incident rules + candidate domains, plus (optionally) rules derived
    from persisted day-validity decisions. With no argument the registry holds
    NO date list at all."""
    rules = _rules() + derive_forward_coverage_rules(forward_invalid_days or {})
    return build_registry(REGISTRY_VERSION, rules, _domains())


# ---------------------------------------------------------------------------
# UEF adapter eligibility -- a DIFFERENT fact from registry classification.
# Sourced from docs/milestones/UEF.md and the Research Portfolio Freeze
# (2026-09-16); never derived from evidence and never consulted by the
# resolver. A CLEAN artifact for a BLOCKED adapter is still not recomputable.
# ---------------------------------------------------------------------------

ADAPTER_ELIGIBILITY: dict[str, dict[str, str]] = {
    F_Q10_SEMI: {"adapter_status": "APPROVED_FROZEN", "authority": "docs/milestones/UEF.md"},
    F_Q12_CALC1: {"adapter_status": "APPROVED_FROZEN", "authority": "docs/milestones/UEF.md (CONSUMER_ONLY)"},
    F_Q12_CALC2: {"adapter_status": "APPROVED_FROZEN", "authority": "docs/milestones/UEF.md"},
    F_OPENING_1A: {"adapter_status": "APPROVED_FROZEN", "authority": "docs/milestones/UEF.md"},
    F_OPENING_1BC: {"adapter_status": "APPROVED_FROZEN", "authority": "docs/milestones/UEF.md"},
    F_Q10_INDEX: {"adapter_status": "APPROVED_FROZEN", "authority": "docs/milestones/UEF.md"},
    F_Q11: {"adapter_status": "PROVISIONAL_AWAITING_RATIFICATION", "authority": "docs/milestones/UEF.md"},
    "q11_v1": {"adapter_status": "BLOCKED", "authority": _FREEZE + " (observed_price never persisted; superseded by v2)"},
    F_Q9: {"adapter_status": "BLOCKED", "authority": _FREEZE + " (exit_price_authority not reconstructible)"},
    F_Q12_CALC3: {"adapter_status": "BLOCKED", "authority": _FREEZE + " (completeness-contract contradiction; timing defect)"},
    "q18": {"adapter_status": "BLOCKED", "authority": _FREEZE + " (episode-outcome persistence missing; no adapter)"},
    "rank1_feature_mart": {"adapter_status": "BLOCKED", "authority": _FREEZE + " (dual-cost/extended-horizon shape mismatch; no adapter)"},
}
