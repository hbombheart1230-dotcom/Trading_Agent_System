"""UEF-5.1 Clean Evidence Registry (incl. FIX1 positive clean authority) -- tests.

Real contract strings (asserted equal to production constants) and real
persisted-shape payloads. Read-only; fixtures live under tmp_path and nothing
here writes under reports/ or data/.
"""
from __future__ import annotations

import ast
import json
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from libs.reporting.evaluation.uef5 import clean_evidence_rules as rules
from libs.reporting.evaluation.uef5.clean_evidence_coverage import (
    COVERAGE_KIND,
    DEFAULT_FAMILIES,
    build_coverage_manifest,
    build_repo_registry,
    coverage_manifest_json,
)
from libs.reporting.evaluation.uef5.clean_evidence_registry import (
    CleanDomain,
    EvidenceRule,
    EvidenceStatus as S,
    PositiveAuditResult,
    PositiveOutcome as PO,
    ReasonCode as R,
    RegistryContractError,
    build_registry,
    make_descriptor,
    make_scope,
    matching_domains,
    path_matches_glob,
    resolve_evidence_status,
)

ROOT = Path(__file__).resolve().parents[1]
REG = rules.build_default_registry()
BSH = "reports/evaluation/baseline_samsung_hynix"
BTC = "reports/evaluation/baseline_btc_woori_tech"
V1 = f"{BTC}/vnext/Q12_CRYPTO_EQUITY_CONFIRM_V1_SHADOW"
V2 = f"{BTC}/vnext/Q12_CRYPTO_EQUITY_CONFIRM_V2_ALIGNED_SHADOW"
KST = timezone(timedelta(hours=9))
KNOWN_INVALID_DAYS = ("2026-06-23", "2026-06-25", "2026-07-17", "2026-07-24", "2026-09-09", "2026-09-24", "2026-09-25")


def epoch(day: str, hh: int = 9, mm: int = 0) -> int:
    return int(datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00").replace(tzinfo=KST).timestamp())


# --------------------------------------------------------- helpers / builders

def _audits_proven(d, reg=REG):
    return [
        PositiveAuditResult(dom.verifier_id, PO.PROVEN_CLEAN, tuple(dom.required_checks))
        for dom in matching_domains(d, reg) if dom.verifier_id
    ]


def _res(d, reg=REG, **kw):
    """No positive audit supplied (candidate only)."""
    return resolve_evidence_status(d, reg, **kw)


def _clean(d, reg=REG, **kw):
    """Every matched domain's verifier reports PROVEN_CLEAN with all required checks."""
    return resolve_evidence_status(d, reg, audits=_audits_proven(d, reg), **kw)


def _q10d(day="2026-09-10", **kw):
    args = dict(family=rules.F_Q10_SEMI, path=f"{BSH}/{day}/baseline_samsung_hynix_forward_returns.json",
                schema_version=rules.Q10_SEMI_SCHEMA, program_id=rules.Q10_SEMI_PROGRAM, trading_date=day)
    args.update(kw)
    return make_descriptor(**args)


def q10_payload(day="2026-09-10", n=2, prefix="BSH", symbol="005930", schema=None, program=None):
    ep = epoch(day)
    return {
        "schema_version": schema or rules.Q10_SEMI_SCHEMA, "evaluation_program_id": program or rules.Q10_SEMI_PROGRAM,
        "behavior_effect": "evaluation_only", "day": day, "cost_model": {"source": "kiwoom.ka10170"},
        "row_count": n,
        "rows": [{"baseline_decision_id": f"{prefix}_{day.replace('-', '')}_{ep + i}", "symbol": symbol,
                  "ticker": symbol + ".KS", "rank": 1} for i in range(n)],
    }


def calc2_payload(day="2026-09-10", **over):
    d = {
        "schema_version": rules.Q12_CALC2_SCHEMA, "contract_id": "q12_btc_woori_five_variable_validation.v1",
        "day": day, "behavior_effect": "observation_only", "evidence_phase": "PROSPECTIVE",
        "prospective_start_day": "2026-08-28", "order_execution_allowed": False, "order_intent": None,
        "btc_delivery_source": "canonical_0855_capture",
        "features": {"btc_0855": {"target_epoch": epoch(day, 8, 55)},
                     "entry_methods": {"09:00": {"entry_epoch": epoch(day, 9, 0)}, "PULLBACK": {"entry_epoch": None}}},
    }
    d.update(over)
    return d


def q10_index_pair(day="2026-09-10"):
    guards = dict(rules._Q10_INDEX_GUARDS)
    base = {"schema_version": rules.Q10_INDEX_SCHEMA, "evaluation_program_id": rules.Q10_INDEX_PROGRAM, "day": day,
            "guards": guards}
    reactions = {**base, "targets": {k: {"source": v} for k, v in rules._Q10_INDEX_TARGET_SOURCES.items()}}
    expected = {**base, "rows": []}
    return reactions, expected


def q11_payload(day="2026-09-22", n=1, **over):
    ep = epoch(day)
    d = {
        "schema_version": rules.Q11_V2_SCHEMA, "evaluation_program_id": rules.Q11_PROGRAM, "day": day,
        "behavior_effect": "shadow_only", "trade_count": n,
        "trades": [{"trade_id": f"OE_TRD_009150_{ep + i}", "symbol": "009150", "entry_epoch": ep + i,
                    "order_execution_allowed": False} for i in range(n)],
    }
    d.update(over)
    return d


def opening_1a_payload(rows=None, through="2026-09-25"):
    rows = rows if rows is not None else [{
        "watch_id": "LATENT:OPEN_0_20_RANK1_30M:20260803:122630:1785715338",
        "initial_day": "2026-08-03", "trigger_day": "2026-08-04",
        "trigger_decision_id": "Q9_20260804_" + "9ed0decf47aa47b9aece5a8a18afa998",
        "symbol": "122630", "trigger_day_integrity_status": "VALID"}]
    return {"schema_version": rules.OPENING_1A_SCHEMA, "behavior_effect": "observation_only",
            "policy_change_authorized": False, "through_day": through, "rows": rows}


def ctx(day="2026-09-10", invalid=(), sibling=None):
    return rules.VerificationContext(trading_date=day, invalid_forward_days=frozenset(invalid),
                                     load_sibling=(lambda name: sibling) if sibling is not None else None)


def _write(root: Path, rel: str, payload) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")


def _validity(day, blockers):
    return {"schema_version": rules.DAY_VALIDITY_SCHEMA, "day": day, "status": "INVALID", "blockers": blockers}


def _fwd_blocker(code="invalid_forward_observation", invalidates=True):
    return {"code": code, "count": 1, "coverage": 0.5, "required_coverage": 0.95, "invalidates_day": invalidates}


# ------------------------------------------------------------------ contracts

def test_literals_match_production_contract_constants():
    from libs.reporting.baseline_btc_woori_tech import contracts as btc
    from libs.reporting.baseline_samsung_hynix import contracts as bsh
    from libs.reporting.baseline_samsung_hynix.forward_validation import contracts as fv
    from libs.research.opportunity_engine import contracts as oe

    assert rules.Q10_SEMI_SCHEMA == bsh.FORWARD_SCHEMA
    assert rules.Q12_CALC1_SCHEMA == btc.FORWARD_SCHEMA
    assert rules.Q12_CALC2_SCHEMA == btc.HYPOTHESIS_DAILY_SCHEMA
    assert rules.Q10_INDEX_SCHEMA == fv.SCHEMA_VERSION and rules.Q10_INDEX_PROGRAM == fv.PROGRAM_ID
    assert rules.Q11_V2_SCHEMA == oe.TRADES_SCHEMA and rules.Q11_V1_SCHEMA == oe.TRADES_SCHEMA_LEGACY_V1
    assert rules.Q11_PROGRAM == oe.PROGRAM_ID


def test_default_registry_well_formed_and_holds_no_hardcoded_day_list():
    assert REG.rules and REG.clean_domains
    for r in REG.rules:
        assert r.source_authority and r.reason_code
    assert not [r.rule_id for r in REG.rules if r.rule_id.startswith(("DV_", "C_"))]
    assert {r.status for r in REG.rules} == {S.QUARANTINED, S.FIELD_INVALID, S.REVIEW_REQUIRED}


# ------------------------------------------- A. positive authority (HIGH-1)

def test_candidate_domain_match_alone_is_review_required_not_clean():
    d = _q10d()  # matches schema + program + path
    res = _res(d)
    assert res.matched_domain_ids == ("CD_Q10_SEMICONDUCTOR",) and res.proven_domain_ids == ()
    assert res.status is S.REVIEW_REQUIRED and res.reason_codes == (R.POSITIVE_CLEAN_NOT_PROVEN.value,)
    assert not res.field_usable("anything")


def test_clean_requires_proven_audit_with_every_declared_check():
    d = _q10d()
    dom = REG.clean_domains[[c.domain_id for c in REG.clean_domains].index("CD_Q10_SEMICONDUCTOR")]
    ok = PositiveAuditResult(dom.verifier_id, PO.PROVEN_CLEAN, tuple(dom.required_checks))
    assert _res(d, audits=[ok]).status is S.CLEAN and _res(d, audits=[ok]).field_usable("x")
    # a verifier cannot skip a declared check
    partial = PositiveAuditResult(dom.verifier_id, PO.PROVEN_CLEAN, tuple(dom.required_checks[:-1]))
    r = _res(d, audits=[partial])
    assert r.status is S.REVIEW_REQUIRED and dom.required_checks[-1] in r.failed_checks
    # PROVEN outcome that still carries a failed check is not proof
    tainted = PositiveAuditResult(dom.verifier_id, PO.PROVEN_CLEAN, tuple(dom.required_checks), ("schema_exact",))
    assert _res(d, audits=[tainted]).status is S.REVIEW_REQUIRED
    # wrong verifier id, NOT_PROVEN, INVALID
    assert _res(d, audits=[PositiveAuditResult("SOMEONE_ELSE", PO.PROVEN_CLEAN, tuple(dom.required_checks))]).status is S.REVIEW_REQUIRED
    assert _res(d, audits=[PositiveAuditResult(dom.verifier_id, PO.NOT_PROVEN)]).reason_codes == (R.POSITIVE_CLEAN_NOT_PROVEN.value,)
    r = _res(d, audits=[PositiveAuditResult(dom.verifier_id, PO.INVALID, (), ("schema_exact",))])
    assert r.status is S.REVIEW_REQUIRED and r.reason_codes == (R.POSITIVE_CLEAN_CONTRADICTED.value,)


def test_domain_without_verifier_can_never_be_clean_even_with_forged_audit():
    reg = build_registry("t", [], [CleanDomain("D1", make_scope(family="f"), ("t",), "n")])
    d = make_descriptor(family="f", path="a/x.json")
    forged = PositiveAuditResult("ANY", PO.PROVEN_CLEAN, ("c",))
    assert resolve_evidence_status(d, reg, audits=[forged]).status is S.REVIEW_REQUIRED


def test_domain_contract_validation():
    sc = make_scope(family="f")
    with pytest.raises(RegistryContractError):
        CleanDomain("D1", sc, ("t",), "n", verifier_id="V")  # verifier without required_checks
    with pytest.raises(RegistryContractError):
        CleanDomain("D1", sc, ("t",), "n", required_checks=("c",))  # checks without verifier


def test_q10_semiconductor_missing_program_id_stays_no_rule_even_with_proof():
    d = _q10d("2026-06-23", program_id=None)
    assert _res(d).status is S.NO_RULE
    assert resolve_evidence_status(d, REG, audits=[PositiveAuditResult(rules.V_Q10_SEMI, PO.PROVEN_CLEAN, rules.Q10_SEMI_CHECKS)]).status is S.NO_RULE


# ---------------------------------------- family verifiers (persisted fields)

def test_q10_semiconductor_verifier_proves_or_refuses():
    good = rules.verify_q10_semiconductor(q10_payload(), ctx())
    assert good.outcome is PO.PROVEN_CLEAN and set(rules.Q10_SEMI_CHECKS) <= set(good.passed_checks) and good.record_count == 2
    bad_symbol = q10_payload(symbol="TEST01")
    assert rules.verify_q10_semiconductor(bad_symbol, ctx()).outcome is PO.INVALID
    p = q10_payload(); p["rows"][0]["baseline_decision_id"] = "BSH_20260101_" + str(epoch("2026-01-01"))
    r = rules.verify_q10_semiconductor(p, ctx())
    assert r.outcome is PO.INVALID and "records_native_identity" in r.failed_checks
    p = q10_payload(); del p["cost_model"]
    r = rules.verify_q10_semiconductor(p, ctx())
    assert r.outcome is PO.NOT_PROVEN and "broker_cost_source" in r.failed_checks
    p = q10_payload(); p["row_count"] = 99
    assert "row_count_consistent" in rules.verify_q10_semiconductor(p, ctx()).failed_checks
    assert rules.verify_q10_semiconductor(q10_payload(), ctx(invalid=["2026-09-10"])).failed_checks == ("forward_coverage_valid_day",)
    assert rules.verify_q10_semiconductor([], ctx()).outcome is PO.NOT_PROVEN
    assert rules.verify_q10_semiconductor(q10_payload(), ctx(day=None)).outcome is PO.NOT_PROVEN  # date scope unproven


def test_q12_calc1_verifier_and_no_forward_day_dependence_asserted():
    p = q10_payload("2026-09-10", prefix="BTW", symbol="041190", schema=rules.Q12_CALC1_SCHEMA, program=rules.Q12_PROGRAM)
    assert rules.verify_q12_calc1(p, ctx()).outcome is PO.PROVEN_CLEAN
    assert rules.verify_q12_calc1(p, ctx(invalid=["2026-09-10"])).outcome is PO.PROVEN_CLEAN  # documented: no Q9 dependence persisted
    assert rules.verify_q12_calc1(q10_payload(), ctx()).outcome is PO.INVALID  # wrong schema/program/prefix


def test_q12_calc2_verifier_requires_prospective_and_delivery_provenance():
    assert rules.verify_q12_calc2(calc2_payload(), ctx()).outcome is PO.PROVEN_CLEAN
    p = calc2_payload(); del p["btc_delivery_source"]
    r = rules.verify_q12_calc2(p, ctx())
    assert r.outcome is PO.NOT_PROVEN and r.failed_checks == ("btc_delivery_source_canonical",)
    back = calc2_payload("2026-08-27", evidence_phase="BACKCHECK")
    r = rules.verify_q12_calc2(back, ctx("2026-08-27"))
    assert r.outcome is PO.INVALID and {"evidence_phase_prospective", "prospective_window"} <= set(r.failed_checks)
    assert rules.verify_q12_calc2(calc2_payload(order_execution_allowed=True), ctx()).outcome is PO.INVALID
    p = calc2_payload(); p["features"]["btc_0855"]["target_epoch"] = epoch("2026-09-09", 8, 55)
    assert "epoch_date_scope" in rules.verify_q12_calc2(p, ctx()).failed_checks


def test_q10_index_verifier_needs_guards_and_authoritative_sources():
    reactions, expected = q10_index_pair()
    assert rules.verify_q10_index(expected, ctx(sibling=reactions)).outcome is PO.PROVEN_CLEAN
    assert rules.verify_q10_index(reactions, ctx(sibling=reactions)).outcome is PO.PROVEN_CLEAN
    assert rules.verify_q10_index(expected, ctx()).outcome is PO.NOT_PROVEN  # no sibling
    bad = json.loads(json.dumps(expected)); bad["guards"]["historical_backfill_allowed"] = True
    assert rules.verify_q10_index(bad, ctx(sibling=reactions)).outcome is PO.INVALID
    wrong = json.loads(json.dumps(reactions)); wrong["targets"]["kospi"]["source"] = "manual_csv"
    assert rules.verify_q10_index(expected, ctx(sibling=wrong)).outcome is PO.INVALID


def test_q11_v2_verifier_native_identity_and_order_disabled():
    assert rules.verify_q11_v2(q11_payload(), ctx("2026-09-22")).outcome is PO.PROVEN_CLEAN
    assert rules.verify_q11_v2(q11_payload(n=0), ctx("2026-09-22")).outcome is PO.PROVEN_CLEAN
    p = q11_payload(); p["trades"][0]["order_execution_allowed"] = True
    assert rules.verify_q11_v2(p, ctx("2026-09-22")).outcome is PO.INVALID
    p = q11_payload(); p["trades"][0]["entry_epoch"] += 1
    assert "records_native_identity" in rules.verify_q11_v2(p, ctx("2026-09-22")).failed_checks
    p = q11_payload(); del p["trades"][0]["order_execution_allowed"]
    assert rules.verify_q11_v2(p, ctx("2026-09-22")).outcome is PO.NOT_PROVEN
    assert rules.verify_q11_v2(q11_payload(behavior_effect="live"), ctx("2026-09-22")).outcome is PO.INVALID


# ------------------------- B / HIGH-2. Opening cumulative artifacts cannot be CLEAN

def test_opening_1bc_cumulative_mixed_dates_cannot_be_file_level_clean():
    d = make_descriptor(family=rules.F_OPENING_1BC,
                        path="reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.json",
                        schema_version=rules.OPENING_1BC_SCHEMA)
    rows = [{"day": day, "decision_id": f"Q9_{day.replace('-', '')}_" + "a" * 32} for day in ("2026-06-25", "2026-07-24", "2026-07-30")]
    recs = [make_descriptor(family=rules.F_OPENING_1BC, path=d.path, trading_date=r["day"], record_type="stage_rows") for r in rows]
    for audits in ([], [PositiveAuditResult("UEF5_V_OPENING_1BC", PO.PROVEN_CLEAN, ("x",))]):
        res = resolve_evidence_status(d, REG, audits=audits, records=recs)
        assert res.status is S.REVIEW_REQUIRED and not res.field_usable("net_return_30m_pct")
    dom = [c for c in REG.clean_domains if c.domain_id == "CD_OPENING_SHADOW_1BC"][0]
    assert dom.verifier_id is None


def test_opening_1a_verified_per_record_and_forward_invalid_valid_row_blocks_file():
    assert rules.verify_opening_1a(opening_1a_payload(), ctx(None)).outcome is PO.PROVEN_CLEAN
    row = opening_1a_payload()["rows"][0]
    row = {**row, "initial_day": "2026-09-04", "trigger_day": "2026-09-09",
           "watch_id": "LATENT:OPEN_0_20_RANK1_30M:20260904:122630:1785715338",
           "trigger_decision_id": "Q9_20260909_" + "b" * 32}
    r = rules.verify_opening_1a(opening_1a_payload([row]), ctx(None, invalid=["2026-09-09"]))
    assert r.outcome is PO.INVALID and r.failed_checks == ("forward_coverage_valid_day",)
    # a producer-flagged non-VALID row on an invalid day is excluded by the adapter, so it does not block
    row2 = {**row, "trigger_day_integrity_status": "NO_OPENING_RANK1"}
    assert rules.verify_opening_1a(opening_1a_payload([row2]), ctx(None, invalid=["2026-09-09"])).outcome is PO.PROVEN_CLEAN
    # impossible date ordering / bad native id
    bad = {**opening_1a_payload()["rows"][0], "trigger_day": "2026-07-01"}
    assert rules.verify_opening_1a(opening_1a_payload([bad]), ctx(None)).outcome is PO.INVALID


# --------------------- C/D/HIGH-3. structural global 95% forward-coverage rule

def test_structural_rule_derives_field_invalid_for_every_known_invalid_day():
    payloads = [(f"p{i}", _validity(d, [_fwd_blocker()])) for i, d in enumerate(KNOWN_INVALID_DAYS)]
    days, rejected = rules.forward_coverage_invalid_days(payloads)
    assert tuple(days) == KNOWN_INVALID_DAYS and rejected == ()
    reg = rules.build_default_registry(days)
    for day in KNOWN_INVALID_DAYS:
        for path in (f"reports/evaluation/daily/{day}/q9_day_validity.json", f"data/logs/quant_shadow_candidates/{day}/a.json"):
            res = resolve_evidence_status(make_descriptor(family="x", path=path, trading_date=day), reg)
            # 2026-07-17's daily dir ALSO carries the static Incident A REVIEW_REQUIRED rule; merge = higher severity
            merged_with_incident_a = day == "2026-07-17" and path.startswith("reports/evaluation/daily/")
            assert res.status is (S.REVIEW_REQUIRED if merged_with_incident_a else S.FIELD_INVALID)
            assert R.INSUFFICIENT_SOURCE_COVERAGE.value in res.reason_codes
            assert res.invalid_fields == rules.FORWARD_COVERAGE_INVALID_FIELDS
            for f in rules.FORWARD_COVERAGE_INVALID_FIELDS:
                assert res.field_status(f) in (S.FIELD_INVALID, S.REVIEW_REQUIRED) and not res.field_usable(f)
    other = resolve_evidence_status(make_descriptor(family="x", path="reports/evaluation/daily/2026-07-23/a.json", trading_date="2026-07-23"), reg)
    assert other.status is not S.FIELD_INVALID
    unrelated = resolve_evidence_status(make_descriptor(family="x", path=f"{BSH}/2026-07-24/x.json", trading_date="2026-07-24"), reg)
    assert R.INSUFFICIENT_SOURCE_COVERAGE.value not in unrelated.reason_codes  # same-day unrelated evidence untouched


def test_future_low_coverage_day_needs_no_code_change():
    future = "2099-03-04"  # not anywhere in the code
    days, _ = rules.forward_coverage_invalid_days([("p", _validity(future, [_fwd_blocker("forward_observation_unavailable")]))])
    assert future in days and future not in json.dumps(REG.to_canonical_dict())
    reg = rules.build_default_registry(days)
    res = resolve_evidence_status(make_descriptor(family="x", path=f"reports/evaluation/daily/{future}/daily_scorecard.json", trading_date=future), reg)
    assert res.status is S.FIELD_INVALID and set(res.invalid_fields) == {"formal_day_eligibility", "forward_outcome", "forward_usable_coverage"}


def test_day_validity_derivation_is_conservative_and_contract_bound():
    other_reason = _validity("2026-07-25", [{"code": "pabc_linkage_ratio_below_threshold", "invalidates_day": None}])
    session = _validity("2026-09-11", [{"code": "full_session_coverage_not_confirmed", "invalidates_day": True}])
    not_invalidating = _validity("2026-09-12", [_fwd_blocker(invalidates=False)])
    numbers_missing = _validity("2026-09-13", [{"code": "invalid_forward_observation", "invalidates_day": True}])
    malformed = [("bad1", {"schema_version": "other.v1", "day": "2026-09-14", "blockers": []}), ("bad2", None),
                 ("bad3", {"schema_version": rules.DAY_VALIDITY_SCHEMA, "day": "not-a-day", "blockers": []})]
    days, rejected = rules.forward_coverage_invalid_days(
        [("a", other_reason), ("b", session), ("c", not_invalidating), ("d", numbers_missing)] + malformed)
    assert tuple(days) == ("2026-09-13",)  # decision = invalidates_day, never a percentage
    assert rejected == ("bad1", "bad2", "bad3")


def test_real_persisted_day_validity_contains_the_known_invalid_days():
    files = sorted((ROOT / "reports" / "evaluation" / "daily").glob("*/q9_day_validity.json"))
    if not files:
        pytest.skip("no persisted q9_day_validity artifacts in this checkout")
    payloads = []
    for f in files:
        try:
            payloads.append((f.name, json.loads(f.read_text(encoding="utf-8"))))
        except ValueError:
            continue
    days, _ = rules.forward_coverage_invalid_days(payloads)
    present = {p["day"] for _, p in payloads if isinstance(p, dict)}
    for day in KNOWN_INVALID_DAYS:
        if day in present:
            assert day in days, day


# ------------------------- E. internal contaminated record (HIGH-2/record-level)

def test_internal_contaminated_record_prevents_whole_file_clean():
    d = _q10d()
    rec_bad = make_descriptor(family=rules.F_Q10_SEMI, path=d.path, trading_date="2026-09-10", markers={"decision_id": ["pytest_fixture_1"]})
    rec_ok = make_descriptor(family=rules.F_Q10_SEMI, path=d.path, trading_date="2026-09-10", markers={"decision_id": ["BSH_20260910_1"]})
    assert _clean(d, records=[rec_ok]).status is S.CLEAN
    res = _clean(d, records=[rec_ok, rec_bad])
    assert res.status is S.REVIEW_REQUIRED and "B_SYNTHETIC_DECISION_ID_ANY_FAMILY" in res.record_level_rule_ids
    assert not res.field_usable("x")


def test_record_level_review_rule_also_blocks_file_clean():
    d = make_descriptor(family="f", path="a/x.json", schema_version="s")
    reg = build_registry(
        "t",
        [EvidenceRule("R1", S.REVIEW_REQUIRED, R.UNRESOLVED_SOURCE_PROVENANCE,
                      make_scope(family="f", date_start="2026-08-01", date_end="2026-08-02"), ("t",), "n")],
        [CleanDomain("D1", make_scope(family="f", schema_versions=["s"]), ("t",), "n", verifier_id="V", required_checks=("c",))],
    )
    proven = [PositiveAuditResult("V", PO.PROVEN_CLEAN, ("c",))]
    assert resolve_evidence_status(d, reg, audits=proven).status is S.CLEAN
    rec = make_descriptor(family="f", path="a/x.json", trading_date="2026-08-01")
    assert resolve_evidence_status(d, reg, audits=proven, records=[rec]).status is S.REVIEW_REQUIRED


def test_coverage_never_whitelists_a_file_holding_a_contaminated_record(tmp_path):
    good = q10_payload("2026-09-10", n=2)
    poisoned = q10_payload("2026-09-11", n=2)
    poisoned["rows"][1]["baseline_decision_id"] = poisoned["rows"][1]["baseline_decision_id"].replace("BSH", "BSH_pytest")
    _write(tmp_path, f"{BSH}/2026-09-10/baseline_samsung_hynix_forward_returns.json", good)
    _write(tmp_path, f"{BSH}/2026-09-11/baseline_samsung_hynix_forward_returns.json", poisoned)
    m = build_coverage_manifest(tmp_path)
    q10 = {f["label"]: f for f in m["families"]}["Q10 Semiconductor"]["registry_classification"]
    assert q10["CLEAN"] == 1 and q10["CLEAN"] + q10["QUARANTINED"] + q10["REVIEW_REQUIRED"] == 2


# ------------------------------------------- F. controlled-lane P&L downgrade

def _lane(day="2026-09-02", trade="TRD_20260902_251340_01"):
    return make_descriptor(family=rules.F_CONTROLLED_LANE_TRADE, path=f"reports/trades/{day}/0900/{trade}/entry.json",
                           trading_date=day, markers={"lane_id": ["Q10_INDEX"]}, native_ids={"trade_id": [trade]})


def test_controlled_lane_rank_fields_invalid_and_pnl_review_required_never_clean():
    res = _clean(_lane())  # even with a (forged) proof for every matched domain
    assert not [c for c in REG.clean_domains if c.domain_id == "CD_CONTROLLED_LANE_OUTCOME_FIELDS"]
    assert res.status is S.REVIEW_REQUIRED
    for f in ("scanner_rank", "selected_rank", "scanner_to_entry_delay_sec"):
        assert res.field_status(f) is S.FIELD_INVALID and not res.field_usable(f)
    for f in ("realized_pnl", "realized_pnl_pct", "entry_price", "exit_price", "fill_status"):
        assert res.field_status(f) is S.REVIEW_REQUIRED and not res.field_usable(f), f
    assert R.INVALID_SCANNER_ATTRIBUTION.value in res.reason_codes and R.UNRESOLVED_SOURCE_PROVENANCE.value in res.reason_codes


def test_controlled_lane_outside_window_and_other_lane_not_matched():
    kw = dict(family=rules.F_CONTROLLED_LANE_TRADE, path="reports/trades/2026-09-15/0900/t/entry.json")
    assert _res(make_descriptor(**kw, trading_date="2026-09-15", markers={"lane_id": ["Q10_INDEX"]})).status is S.NO_RULE
    assert _res(make_descriptor(**kw, trading_date="2026-09-02", markers={"lane_id": ["OPENING_RANK1_PROBE"]})).status is S.NO_RULE


def test_review_fields_contract_validation():
    sc = make_scope(family="f")
    with pytest.raises(RegistryContractError):
        EvidenceRule("R1", S.QUARANTINED, R.STALE_MOCK_FILL, sc, ("t",), "n", review_fields=("a",), review_reason_code=R.UNRESOLVED_SOURCE_PROVENANCE)
    with pytest.raises(RegistryContractError):
        EvidenceRule("R2", S.FIELD_INVALID, R.STALE_MOCK_FILL, sc, ("t",), "n", invalid_fields=("a",), review_fields=("b",))  # no reason
    with pytest.raises(RegistryContractError):
        EvidenceRule("R3", S.FIELD_INVALID, R.STALE_MOCK_FILL, sc, ("t",), "n", invalid_fields=("a",), review_fields=("a",), review_reason_code=R.UNRESOLVED_SOURCE_PROVENANCE)


# --------------------------------------------- G. coverage transparency

def test_coverage_manifest_discloses_scope_skips_and_unscanned(tmp_path):
    _write(tmp_path, f"{BSH}/2026-09-10/baseline_samsung_hynix_forward_returns.json", q10_payload())
    _write(tmp_path, f"{BSH}/2026-09-11/baseline_samsung_hynix_forward_returns.json", "{ not json")
    _write(tmp_path, f"{BSH}/2026-09-12/baseline_samsung_hynix_forward_returns.json", q10_payload("2026-09-12", n=50))
    _write(tmp_path, f"{V1}/2026-09-07/daily_report.md", "# report")
    _write(tmp_path, f"{V1}/2026-09-07/observations/0900.json", {"features": {"crypto_equity_confirm": "DIVERGENCE"}})
    _write(tmp_path, "data/logs/events.jsonl", '{"run_id":"pytest_x"}\n')  # record-level source: present but NOT scanned
    big = q10_payload("2026-09-12", n=50)
    limit = len(json.dumps(q10_payload())) + 10  # only the small file fits
    m = build_coverage_manifest(tmp_path, max_parse_bytes=limit)
    assert m["coverage_kind"] == COVERAGE_KIND == "UEF-5.1 FILE-LEVEL ARTIFACT COVERAGE"
    assert m["complete_historical_coverage"] is False and "NOT complete historical" in m["scope_disclosure"]
    fam = {f["label"]: f for f in m["families"]}
    acct = fam["Q10 Semiconductor"]["accounting"]
    assert acct == {"discovered": 3, "classified": 1, "skipped_oversize": 1, "parse_failed": 1,
                    "unsupported_format": 0, "unclassified": acct["unclassified"]}
    assert acct["discovered"] == acct["classified"] + acct["skipped_oversize"] + acct["parse_failed"] + acct["unsupported_format"]
    calc3 = fam["Q12 Calc3"]["accounting"]
    assert calc3["discovered"] == 2 and calc3["unsupported_format"] == 1 and calc3["classified"] == 1
    assert m["totals"]["discovered"] == sum(f["accounting"]["discovered"] for f in m["families"])
    sources = {s["source_id"] for s in m["record_level_not_scanned"]}
    assert {"events_jsonl", "quant_shadow_candidates", "q9_decision_windows", "evaluation_daily_rows",
            "per_trade_artifacts", "evidence_ledger", "root_b_jsonl", "other_reports_and_data"} <= sources
    assert str(tmp_path) not in coverage_manifest_json(m)
    del big


def test_coverage_reads_structural_invalid_days_from_persisted_validity_and_reports_others(tmp_path):
    _write(tmp_path, "reports/evaluation/daily/2026-09-10/q9_day_validity.json", _validity("2026-09-10", [_fwd_blocker()]))
    _write(tmp_path, "reports/evaluation/daily/2026-09-11/q9_day_validity.json", _validity("2026-09-11", [{"code": "full_session_coverage_not_confirmed", "invalidates_day": True}]))
    _write(tmp_path, "reports/evaluation/daily/2026-09-12/q9_day_validity.json", "garbage")
    _write(tmp_path, f"{BSH}/2026-09-10/baseline_samsung_hynix_forward_returns.json", q10_payload("2026-09-10"))
    _write(tmp_path, f"{BSH}/2026-09-13/baseline_samsung_hynix_forward_returns.json", q10_payload("2026-09-13"))
    reg, dv = build_repo_registry(tmp_path)
    m = build_coverage_manifest(tmp_path, reg, day_validity=dv)
    sf = m["structural_forward_coverage"]
    assert sf["invalid_days"] == {"2026-09-10": ["invalid_forward_observation"]}
    assert sf["other_invalidating_blocker_days_not_encoded"] == {"full_session_coverage_not_confirmed": 1}
    assert sf["payloads_rejected"] == ["reports/evaluation/daily/2026-09-12/q9_day_validity.json"]
    q10 = {f["label"]: f for f in m["families"]}["Q10 Semiconductor"]["registry_classification"]
    assert (q10["CLEAN"], q10["REVIEW_REQUIRED"]) == (1, 1)  # 09-13 clean; 09-10 forward-invalid -> not proven


# ------------------------------------- H. existing guarantees (retained)

def test_synthetic_evidence_quarantined_and_krx_symbols_not_flagged():
    for d in (
        _q10d(markers={"run_id": ["pytest_fixture_run_1"]}), _q10d(markers={"decision_id": ["synthetic-decision"]}),
        make_descriptor(family=rules.F_EVENTS, path="data/logs/events.jsonl", trading_date="2026-07-20", markers={"symbol": ["ABC"]}),
        make_descriptor(family=rules.F_EVENTS, path="data/logs/events.jsonl", trading_date="2026-07-20", markers={"run_id": ["baseline_samsung_hynix_2026-07-20_XYZ_1"]}),
        make_descriptor(family=rules.F_QUANT_SHADOW, path="data/logs/quant_shadow_candidates/2026-07-21/a.json", trading_date="2026-07-21", markers={"symbol": ["TEST1"]}),
        make_descriptor(family=rules.F_Q9_WINDOWS, path="reports/operator_summary/daily/2026-08-05/q9_decision_windows.json", trading_date="2026-08-05", markers={"decision_id": ["my_test_decision"]}),
        make_descriptor(family="x", path="data/logs/dev/testing/quarantine/20260730T092633Z/data/logs/events.jsonl"),
    ):
        res = _clean(d)
        assert res.status is S.QUARANTINED and res.reason_codes == (R.TEST_SYNTHETIC_CONTAMINATION.value,)
    ok = make_descriptor(family=rules.F_EVENTS, path="data/logs/events.jsonl", trading_date="2026-09-18",
                         markers={"symbol": ["041190"], "run_id": ["baseline_btc_woori_tech_2026-09-18_041190_1"]})
    assert _res(ok).status is not S.QUARANTINED
    assert _clean(_q10d(markers={"symbol": ["005930.KS"]})).status is S.CLEAN


def _trade(trade_id, day, **kw):
    return make_descriptor(family="trade", path=f"reports/trades/{day}/1200/{trade_id}/lifecycle_bundle.json",
                           trading_date=day, native_ids={"trade_id": [trade_id]}, **kw)


@pytest.mark.parametrize("n", ["01", "02", "03", "04"])
def test_stale_fill_exact_trade_ids_quarantined(n):
    res = _res(_trade(f"TRD_20260717_001790_{n}", "2026-07-17"))
    assert res.status is S.QUARANTINED and res.reason_codes == (R.STALE_MOCK_FILL.value,)


def test_stale_fill_scope_is_exact_and_not_broadened_by_fix1():
    for tid, day in (("TRD_20260716_001790_01", "2026-07-16"), ("TRD_20260717_005930_01", "2026-07-17"),
                     ("TRD_20260717_001790_05", "2026-07-17"), ("TRD_20260717_001790_01", "2026-07-18")):
        assert R.STALE_MOCK_FILL.value not in _res(_trade(tid, day)).reason_codes
    base = dict(family="order", path="data/logs/orders.json", native_ids={"order_id": ["0088903"]})
    assert _res(make_descriptor(**base, trading_date="2026-07-17", markers={"symbol": ["001790"]})).status is S.QUARANTINED
    assert _res(make_descriptor(**base, trading_date="2026-07-17", markers={"symbol": ["005930"]})).status is not S.QUARANTINED
    assert _res(make_descriptor(**base, trading_date="2026-07-18", markers={"symbol": ["001790"]})).status is not S.QUARANTINED
    m = {"recovery_source": ["broker_synthesized_missing_trade_bundle"]}
    assert _res(make_descriptor(family="trade", path="reports/trades/x.json", trading_date="2026-07-20", markers=m)).status is not S.QUARANTINED
    # the rule set itself is exactly the four seeded stale-fill rules (no additions slipped in)
    assert sorted(r.rule_id for r in REG.rules if r.reason_code is R.STALE_MOCK_FILL) == [
        "A_STALE_FILL_ORDER_IDS", "A_STALE_FILL_QUARANTINE_DIR", "A_STALE_FILL_SYNTH_BUNDLE", "A_STALE_FILL_TRADE_IDS"]
    ids = [r for r in REG.rules if r.rule_id == "A_STALE_FILL_ORDER_IDS"][0].scope.native_ids
    assert len(ids[0][1]) == 8
    q = make_descriptor(family="x", path="data/logs/artifact_quarantine/2026-07-17_stale_ka10076/evaluation_daily/q9_day_validity.json")
    assert _res(q).status is S.QUARANTINED
    d = make_descriptor(family="daily", path="reports/evaluation/daily/2026-07-17/daily_scorecard.json", trading_date="2026-07-17")
    assert _res(d).status is S.REVIEW_REQUIRED


def test_incident_b_late_leaks_and_cleaned_days():
    assert _res(make_descriptor(family="canonical", path="reports/canonical/2026-08-20/trace-r1/commander.json")).status is S.QUARANTINED
    assert _res(make_descriptor(family="canonical", path="reports/canonical/2026-08-20/run-real/commander.json")).status is not S.QUARANTINED
    led = lambda day: make_descriptor(family=rules.F_EVIDENCE_LEDGER, path="data/evidence_ledger/events.jsonl", trading_date=day)
    assert _res(led("2026-08-15")).status is S.REVIEW_REQUIRED and _res(led("2026-09-02")).status is S.NO_RULE
    q9 = lambda day: make_descriptor(family="q9w", path=f"reports/operator_summary/daily/{day}/q9_decision_windows.json", trading_date=day)
    assert _res(q9("2026-07-24")).status is S.REVIEW_REQUIRED and _res(q9("2026-07-31")).status is S.NO_RULE
    assert _res(make_descriptor(family="x", path="b.jsonl")).status is S.REVIEW_REQUIRED


def test_q12_calc3_isolation_never_clean_and_v1_confirmation_invalid():
    obs = make_descriptor(family=rules.F_Q12_CALC3, path=f"{V1}/2026-09-07/observations/0900.json", trading_date="2026-09-07")
    res = _clean(obs)
    assert res.status is S.FIELD_INVALID and "crypto_equity_confirm" in res.invalid_fields and not res.field_usable("crypto_equity_confirm")
    fwd = make_descriptor(family=rules.F_Q12_CALC3, path=f"{V1}/2026-09-07/forward/0930.json", trading_date="2026-09-07")
    assert _clean(fwd).status is S.REVIEW_REQUIRED
    v2 = make_descriptor(family=rules.F_Q12_CALC3, path=f"{V2}/2026-09-08/observations/0900.json", trading_date="2026-09-08")
    r2 = _clean(v2)
    assert r2.status is not S.CLEAN and "legacy_unaligned_direction" in r2.invalid_fields and not r2.field_usable("crypto_equity_confirm")
    assert not [d for d in REG.clean_domains if "CALC3" in d.domain_id]


def test_blocked_family_evidence_defects_and_adapter_isolation():
    q11v1 = make_descriptor(family=rules.F_Q11, path="reports/evaluation/opportunity_engine_shadow/2026-08-01/opportunity_engine_virtual_trades.json",
                            schema_version=rules.Q11_V1_SCHEMA, program_id=rules.Q11_PROGRAM, trading_date="2026-08-01")
    q9 = make_descriptor(family=rules.F_Q9, path="reports/dev/analysis/post_exit_shadow_recap/2026-09-10/post_exit_shadow_recap.json",
                         schema_version=rules.Q9_RECAP_SCHEMA, trading_date="2026-09-10")
    assert _clean(q11v1).status is S.REVIEW_REQUIRED and _clean(q9).status is S.REVIEW_REQUIRED
    for k in ("q11_v1", rules.F_Q9, rules.F_Q12_CALC3, "q18", "rank1_feature_mart"):
        assert rules.ADAPTER_ELIGIBILITY[k]["adapter_status"] == "BLOCKED"
    intended = {f.label for f in DEFAULT_FAMILIES if f.intended_for_uef5}
    assert intended == {"Q10 Semiconductor", "Q12 Calc1", "Q12 Calc2", "Opening Shadow 1A", "Opening Shadow 1B/1C", "Q10 Index", "Q11 v2"}
    assert {f.label for f in DEFAULT_FAMILIES if not f.intended_for_uef5} == {"Q9", "Q11 v1", "Q12 Calc3", "Q18", "rank1_feature_mart"}
    for f in DEFAULT_FAMILIES:
        assert f.adapter_key in rules.ADAPTER_ELIGIBILITY


def test_registry_classification_stays_independent_of_adapter_eligibility(tmp_path):
    _write(tmp_path, "reports/dev/analysis/post_exit_shadow_recap/2026-09-10/post_exit_shadow_recap.json", {"schema_version": rules.Q9_RECAP_SCHEMA})
    reg = build_registry("t", [], [CleanDomain("CD_Q9_H", make_scope(family=rules.F_Q9, schema_versions=[rules.Q9_RECAP_SCHEMA]), ("t",), "n")])
    row = {r["label"]: r for r in build_coverage_manifest(tmp_path, reg, day_validity={"invalid_days": {}, "rejected": (), "payload_count": 0, "other_invalidating_blocker_days": {}})["families"]}["Q9"]
    assert row["registry_classification"]["CLEAN"] == 0 and row["registry_classification"]["REVIEW_REQUIRED"] == 1  # unproven
    assert row["uef_adapter_eligibility"]["adapter_status"] == "BLOCKED" and not row["intended_for_uef5"]


def test_coverage_manifest_positive_clean_and_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    reactions, expected = q10_index_pair("2026-09-10")
    calc1 = q10_payload("2026-09-10", prefix="BTW", symbol="041190", schema=rules.Q12_CALC1_SCHEMA, program=rules.Q12_PROGRAM)
    files = [
        (f"{BSH}/2026-09-10/baseline_samsung_hynix_forward_returns.json", q10_payload()),
        (f"{BTC}/2026-09-10/baseline_btc_woori_forward_returns.json", calc1),
        (f"{BTC}/2026-09-10/q12_btc_woori_hypothesis_validation.json", calc2_payload()),
        (f"{BSH}/2026-09-10/q10_forward_validation/q10_actual_market_reactions.json", reactions),
        (f"{BSH}/2026-09-10/q10_forward_validation/q10_expected_vs_actual.json", expected),
        ("reports/evaluation/opportunity_engine_shadow/2026-09-22/opportunity_engine_virtual_trades.json", q11_payload()),
        ("reports/evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_forward.json", opening_1a_payload()),
        ("reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.json",
         {"schema_version": rules.OPENING_1BC_SCHEMA, "stage_rows": [{"day": "2026-06-25", "decision_id": "Q9_x"}]}),
    ]
    for i in range(len(files)):
        _write(a, *files[i])
    for i in reversed(range(len(files))):
        _write(b, *files[i])
    ma, mb = build_coverage_manifest(a), build_coverage_manifest(b)
    assert coverage_manifest_json(ma) == coverage_manifest_json(mb) == coverage_manifest_json(build_coverage_manifest(a))
    rows = {r["label"]: r["registry_classification"] for r in ma["families"]}
    for label in ("Q10 Semiconductor", "Q12 Calc1", "Q12 Calc2", "Opening Shadow 1A", "Q10 Index", "Q11 v2"):
        assert rows[label]["CLEAN"] == rows[label]["total_discovered"] > 0, label
    assert rows["Opening Shadow 1B/1C"]["CLEAN"] == 0 and rows["Opening Shadow 1B/1C"]["REVIEW_REQUIRED"] == 1


def test_coverage_default_is_positive_only_when_calc2_delivery_source_persisted(tmp_path):
    p = calc2_payload(); del p["btc_delivery_source"]
    _write(tmp_path, f"{BTC}/2026-09-10/q12_btc_woori_hypothesis_validation.json", p)
    row = {r["label"]: r["registry_classification"] for r in build_coverage_manifest(tmp_path)["families"]}["Q12 Calc2"]
    assert row["CLEAN"] == 0 and row["REVIEW_REQUIRED"] == 1
    assert row["failed_check_counts"] == {"btc_delivery_source_canonical": 1}


def test_rule_and_domain_order_does_not_change_result_or_digest():
    probes = [_q10d(), _q10d(markers={"run_id": ["pytest_x"]}), _trade("TRD_20260717_001790_02", "2026-07-17"), _lane(),
              make_descriptor(family=rules.F_Q12_CALC3, path=f"{V1}/2026-09-07/forward/a.json", trading_date="2026-09-07")]
    days = {"2026-07-24": ("invalid_forward_observation",)}
    base = rules.build_default_registry(days)
    expected = [_clean(p, base).to_canonical_dict() for p in probes]
    rng = random.Random(1234)
    for _ in range(12):
        r, c = list(rules._rules()) + rules.derive_forward_coverage_rules(days), list(rules._domains())
        rng.shuffle(r)
        rng.shuffle(c)
        reg = build_registry(rules.REGISTRY_VERSION, r, c)
        assert reg.digest() == base.digest() and reg.to_canonical_json() == base.to_canonical_json()
        assert [_clean(p, reg).to_canonical_dict() for p in probes] == expected


def test_duplicate_conflicting_and_malformed_rules_fail_closed():
    sc = make_scope(family="f", path_globs=["a/*"])
    r1 = EvidenceRule("R1", S.QUARANTINED, R.STALE_MOCK_FILL, sc, ("t",), "n")
    with pytest.raises(RegistryContractError, match="duplicate id"):
        build_registry("t", [r1, EvidenceRule("R1", S.REVIEW_REQUIRED, R.STALE_MOCK_FILL, make_scope(family="g"), ("t",), "n")], [])
    with pytest.raises(RegistryContractError, match="conflicting"):
        build_registry("t", [r1, EvidenceRule("R2", S.REVIEW_REQUIRED, R.STALE_MOCK_FILL, sc, ("t",), "n")], [])
    with pytest.raises(RegistryContractError, match="duplicate"):
        build_registry("t", [r1, EvidenceRule("R2", S.QUARANTINED, R.STALE_MOCK_FILL, sc, ("t",), "other note")], [])
    with pytest.raises(RegistryContractError, match="duplicate clean domains"):
        build_registry("t", [], [CleanDomain("D1", sc, ("t",), "n"), CleanDomain("D2", sc, ("t",), "n")])
    for bad in (lambda: EvidenceRule("R3", S.FIELD_INVALID, R.STALE_MOCK_FILL, sc, ("t",), "n"),
                lambda: EvidenceRule("R4", S.QUARANTINED, R.STALE_MOCK_FILL, sc, ("t",), "n", invalid_fields=("x",)),
                lambda: EvidenceRule("R5", S.CLEAN, R.STALE_MOCK_FILL, sc, ("t",), "n"),
                lambda: EvidenceRule("R6", S.QUARANTINED, R.STALE_MOCK_FILL, sc, (), "n"),
                lambda: make_scope(family="f", marker_patterns={"x": ["("]}),
                lambda: make_scope(family="f", date_start="2026-02-01", date_end="2026-01-01")):
        with pytest.raises(RegistryContractError):
            bad()
    with pytest.raises(RegistryContractError, match="empty scope"):
        make_scope()
    for path in ("reports\\a.json", "/abs/a.json", "C:/a.json"):
        with pytest.raises(RegistryContractError):
            make_descriptor(family="f", path=path)


def test_overlapping_rules_merge_by_severity_and_union():
    a = EvidenceRule("A1", S.FIELD_INVALID, R.INVALID_SCANNER_ATTRIBUTION, make_scope(family="f"), ("t",), "n", invalid_fields=("x",))
    b = EvidenceRule("B1", S.QUARANTINED, R.STALE_MOCK_FILL, make_scope(path_globs=["p/*"]), ("t",), "n")
    c = EvidenceRule("C1", S.FIELD_INVALID, R.INVALID_TIMING_ALIGNMENT, make_scope(record_type="r"), ("t",), "n", invalid_fields=("y",))
    d = make_descriptor(family="f", path="p/1", record_type="r")
    for perm in ([a, b, c], [c, b, a], [b, a, c]):
        res = resolve_evidence_status(d, build_registry("t", perm, []))
        assert res.status is S.QUARANTINED and res.invalid_fields == ("x", "y")


def test_unknown_family_schema_and_undated_are_explicit_no_rule():
    assert _res(make_descriptor(family="brand_new", path="reports/new/a.json")).status is S.NO_RULE
    unknown = make_descriptor(family=rules.F_Q11, path="reports/evaluation/opportunity_engine_shadow/2026-09-10/opportunity_engine_virtual_trades.json",
                              schema_version="opportunity_engine_virtual_trades.v3", program_id=rules.Q11_PROGRAM, trading_date="2026-09-10")
    assert _res(unknown).status is S.NO_RULE
    assert _res(make_descriptor(family=rules.F_EVIDENCE_LEDGER, path="data/evidence_ledger/events.jsonl")).status is S.NO_RULE


def test_glob_semantics_star_does_not_cross_directories():
    assert path_matches_glob("a/b/c.json", "a/*/c.json") and not path_matches_glob("a/b/x/c.json", "a/*/c.json")
    assert path_matches_glob("a/b/x/c.json", "a/**")
    assert path_matches_glob("a/bXc", "a/b?c") and not path_matches_glob("a/b/c", "a/b?c")


def test_registry_serialization_is_deterministic_json():
    a, b = REG.to_canonical_json(), rules.build_default_registry().to_canonical_json()
    assert a == b and json.loads(a)["registry_digest"] == REG.digest()


# ------------------------------- frozen state, isolation, imports

def test_uef5_package_is_stdlib_only_and_not_imported_by_production_or_core():
    pkg = ROOT / "libs" / "reporting" / "evaluation" / "uef5"
    forbidden = ("libs.runtime", "libs.kiwoom", "libs.execution", "graphs", "libs.read", "libs.supervisor", "requests")
    for py in sorted(pkg.glob("*.py")):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for n in names:
                assert not n.startswith(forbidden), f"{py.name} imports {n}"
    offenders = []
    for base in ("libs", "graphs", "apps"):
        for py in sorted((ROOT / base).rglob("*.py")):
            if pkg not in py.parents and "evaluation.uef5" in py.read_text(encoding="utf-8", errors="replace"):
                offenders.append(py.relative_to(ROOT).as_posix())
    assert offenders == [], offenders


def test_freeze_manifest_stays_11_of_11():
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_uef_freeze_manifest.py")],
                          capture_output=True, text=True, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "FILES TRACKED: 11" in proc.stdout and "MISMATCH: 0" in proc.stdout and "STATUS: PASS" in proc.stdout


def test_uef4_adapters_do_not_reference_uef5():
    for py in sorted((ROOT / "libs" / "reporting" / "evaluation" / "canonical").rglob("*.py")):
        assert "uef5" not in py.read_text(encoding="utf-8"), py.name
