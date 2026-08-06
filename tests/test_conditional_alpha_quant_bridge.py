from __future__ import annotations

from libs.reporting.quant_trade_diagnosis.conditional_alpha import (
    resolve_conditional_alpha_context,
)
from libs.research.conditional_alpha_diagnosis.attribution import (
    diagnose_stage_attribution,
)
from libs.research.conditional_alpha_diagnosis.cohorts import annotate_episode
from libs.research.conditional_alpha_diagnosis.contrasts import (
    conditional_contrast_report,
)
from libs.research.conditional_alpha_diagnosis.horizons import (
    conditional_horizon_report,
)


def _episode(decision_id: str = "Q9_1") -> dict:
    return annotate_episode(
        {
            "decision_id": decision_id,
            "day": "2026-07-01",
            "symbol": "005930",
            "decision_time_kst": "2026-07-01T09:01:00+09:00",
            "decision_from_open_sec": 60,
            "rank1_prev5m_observations": 2,
            "precompleted_return_1m_pct": 0.2,
            "opening_relative_volume": 2.0,
            "above_vwap": True,
            "intrinsic_30m_net_pct": 1.0,
            "strategist_selected_30m_net_pct": 0.5,
            "monitor_candidate_30m_net_pct": 0.5,
            "commander_decision": "approve",
            "return_5m_pct": -0.1,
            "return_15m_pct": 0.3,
            "net_return_30m_pct": 1.0,
            "return_60m_pct": 0.8,
            "return_eod_pct": -0.2,
        }
    )


def test_exact_decision_link_is_authoritative() -> None:
    episode = _episode()
    episode["stage_attribution"] = diagnose_stage_attribution(episode)
    model = {
        "day": "2026-07-01",
        "symbol": "005930",
        "selection": {"q9_decision_id": "Q9_1"},
        "entry": {"timestamp": "2026-07-01T00:02:00+00:00"},
    }
    context = resolve_conditional_alpha_context(model, [episode])
    assert context["match_status"] == "EXACT_DECISION_ID"
    assert context["stage_root_cause"] == "STRATEGIST_DEGRADATION"
    assert "CONFIRMED_RANK_POSITIVE_1M" in context["cohort_ids"]


def test_same_symbol_time_match_is_context_only() -> None:
    context = resolve_conditional_alpha_context(
        {
            "day": "2026-07-01",
            "symbol": "005930",
            "selection": {"q9_decision_id": "OTHER"},
            "entry": {"timestamp": "2026-07-01T00:02:00+00:00"},
        },
        [_episode()],
    )
    assert context["match_status"] == "TIME_SYMBOL_CONTEXT_ONLY"
    assert context["authority"] == "CONTEXT_ONLY_NOT_CAUSAL"


def test_partial_exit_child_is_not_an_independent_exact_entry() -> None:
    context = resolve_conditional_alpha_context(
        {
            "day": "2026-07-01",
            "symbol": "005930",
            "selection": {"q9_decision_id": "Q9_1"},
            "integrity": {
                "partial_exit_duplicate": {"status": "duplicate_partial_exit_child"}
            },
        },
        [_episode()],
    )
    assert context["match_status"] == "EXACT_DECISION_ID_DUPLICATE_CHILD"
    assert "do not count" in context["warning"]


def test_horizon_report_is_deterministic_and_not_per_trade_oracle() -> None:
    rows = []
    for index in range(6):
        row = _episode(f"Q9_{index}")
        row["day"] = f"2026-07-{index + 1:02d}"
        row["symbol"] = f"{index + 1:06d}"
        rows.append(row)
    first = conditional_horizon_report(rows)
    second = conditional_horizon_report(rows)
    assert first == second
    target = next(
        row
        for row in first["recommendations"]
        if row["group_id"] == "COHORT:CONFIRMED_RANK_POSITIVE_1M"
    )
    assert target["best_robust_horizon"] == "30m"
    assert "not a per-trade oracle" in target["note"]


def test_contrast_report_exposes_missing_noop_reason_without_inference() -> None:
    positive = _episode()
    positive["commander_decision"] = "approve"
    positive["monitor_intent"] = "NOOP"
    negative = {**_episode("Q9_NEG"), "intrinsic_30m_net_pct": -1.0}
    report = conditional_contrast_report([positive, negative])
    assert report["noop_observability"]["approved_no_execution_count"] == 2
    assert report["noop_observability"]["missing_reason_count"] == 2
    assert "not proof" in report["noop_observability"]["interpretation"]
