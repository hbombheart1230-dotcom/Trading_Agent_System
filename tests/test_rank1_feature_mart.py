from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from libs.research.rank1_feature_mart.candidates import select_candidates
from libs.research.rank1_feature_mart.chart_features import build_rank1_chart_snapshot
from libs.research.rank1_feature_mart.integrity import audit
from libs.research.rank1_feature_mart.outcomes import build_original_hold_path
from libs.research.rank1_feature_mart.prospective import build_prospective_shadow
from libs.research.rank1_feature_mart.prospective_contract import CANDIDATES, contract_payload
from libs.research.rank1_feature_mart.activation_contract import (
    contract_payload as activation_contract_payload,
)
from libs.research.rank1_feature_mart.activation_shadow import (
    build_fresh_change_activation_shadow,
)
from libs.research.rank1_feature_mart.builder import (
    _merge_opening_chart_observation,
    build_episode,
)
from libs.research.rank1_feature_mart.loaders import q9_windows
from libs.research.rank1_feature_mart.strategy_choice_observation import (
    build_strategy_choice_observation,
)
from libs.research.rank1_feature_mart.strategy_alignment_report import (
    build_strategy_alignment_report,
)
from libs.research.rank1_feature_mart.trees import build_regression_tree


KST = timezone(timedelta(hours=9))


def _epoch(day: str, hour: int, minute: int) -> int:
    return int(datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=KST).timestamp())


def _minute(day: str, minute: int, close: float) -> dict:
    moment = datetime.fromisoformat(day).replace(hour=9, tzinfo=KST) + timedelta(minutes=minute)
    return {"ts": int(moment.timestamp()), "raw_ts": moment.strftime("%Y%m%d%H%M%S"), "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 100 + minute}


def _episode(day: str, idx: int, score_band: str, value: float) -> dict:
    return {
        "identity": {"episode_id": f"e{idx}", "day": day, "decision_epoch": idx + 1, "symbol": "005930"},
        "scanner": {"score_band": score_band, "risk_band": "LOW", "relative_volume_band": "MODERATE", "source_top_volume": True, "source_top_value": False, "source_top_change_rate": False},
        "market": {"exposure_alignment": True, "engine_regime": "RISK_ON"},
        "chart": {"feature_max_epoch": idx + 1, "above_vwap": True, "intraday_ma2_5_cross_state": "POST_CROSS_HEALTHY", "intraday_ma5_20_cross_state": "INSUFFICIENT_HISTORY", "daily_ma5_20_cross_state": "POST_CROSS_HEALTHY", "support_state": "VWAP_SUPPORT", "resistance_state": "OPENING_RANGE_BREAK"},
        "strategy": {"entry_horizon": "intraday"},
        "outcomes": {"checkpoints": {label: {"status": "OBSERVED", "net_return_pct": value} for label in ("+15m", "+30m", "EOD")}},
    }


def test_chart_snapshot_uses_only_fully_closed_bars() -> None:
    rows = [_minute("2026-08-03", minute, 100 + minute) for minute in range(6)]
    result = build_rank1_chart_snapshot(day="2026-08-03", decision_epoch=_epoch("2026-08-03", 9, 3), minute_rows=rows, daily_rows=[])
    assert result["completed_bar_count"] == 3
    assert result["feature_max_epoch"] == _epoch("2026-08-03", 9, 3)
    integrity = audit([{"identity": {"episode_id": "x", "day": "2026-08-03", "decision_epoch": _epoch("2026-08-03", 9, 3), "symbol": "005930"}, "chart": result, "outcomes": {"checkpoints": {}}}])
    assert integrity["point_in_time_violations"] == []


def test_long_horizon_outcomes_apply_cost() -> None:
    rows = [_minute("2026-08-03", minute, 100 + minute / 10) for minute in range(240)]
    baseline = rows[1]
    result = build_original_hold_path(day="2026-08-03", baseline_epoch=baseline["ts"], baseline_price=100.1, minute_rows=rows, daily_rows=[], fallback={}, longitudinal={})
    assert result["checkpoints"]["+120m"]["status"] == "OBSERVED"
    expected = round((112.1 / 100.1 - 1.0) * 100.0 - 0.28, 4)
    assert result["checkpoints"]["+120m"]["net_return_pct"] == expected


def test_tree_is_deterministic_and_missing_is_not_a_split() -> None:
    rows = [_episode("2026-07-01", idx, "HIGH" if idx < 6 else "LOW", 1.0 if idx < 6 else -1.0) for idx in range(12)]
    rows.extend(_episode("2026-07-02", 20 + idx, "MISSING", 9.0) for idx in range(5))
    first = build_regression_tree(rows, name="test", features=("scanner.score_band",))
    second = build_regression_tree(deepcopy(rows), name="test", features=("scanner.score_band",))
    assert first == second
    assert first["tree"]["split_feature"] == "scanner.score_band"
    assert "MISSING" not in first["tree"]["branches"]


def test_candidate_requires_train_validation_direction_agreement() -> None:
    rows = [_episode(f"2026-07-{idx + 1:02d}", idx, "HIGH", 1.0) for idx in range(5)]
    rows.extend(_episode(f"2026-08-{idx + 3:02d}", 10 + idx, "HIGH", 0.5) for idx in range(3))
    result = select_candidates(rows)
    assert any(item["feature"] == "scanner.score_band" and item["category"] == "HIGH" for item in result["prospective_shadow_candidates"])


def test_candidate_selection_ignores_rows_after_frozen_end_day() -> None:
    rows = [_episode(f"2026-07-{idx + 1:02d}", idx, "HIGH", 1.0) for idx in range(5)]
    rows.extend(_episode(f"2026-08-{idx + 3:02d}", 10 + idx, "HIGH", 0.5) for idx in range(3))
    frozen = select_candidates(rows)
    rows.extend(_episode("2026-08-12", 100 + idx, "HIGH", -100.0) for idx in range(20))
    assert select_candidates(rows) == frozen


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _prospective_mart_episode(day: str, idx: int, *, risk: str = "HIGH", daily_cross: str = "POST_CROSS_EXTENDED", value: float = 1.0) -> dict:
    row = _episode(day, idx, "HIGH", value)
    row["identity"].update({"cohort_source": "PROSPECTIVE_OPENING_SHADOW", "symbol": f"{idx:06d}", "symbol_name": f"S{idx}"})
    row["scanner"]["risk_band"] = risk
    row["chart"]["daily_ma5_20_cross_state"] = daily_cross
    return row


def test_prospective_contract_hash_is_stable() -> None:
    first = contract_payload()
    second = contract_payload()
    assert first == second
    assert len(first["contract_sha256"]) == 64
    assert len(first["candidates"]) == 2


def test_prospective_shadow_is_observation_only_and_deduplicates_day_symbol(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    mart_root = reports / "evaluation" / "feature_mart" / "opening_rank1"
    day = "2026-08-12"
    rows = [_prospective_mart_episode(day, 1), _prospective_mart_episode(day, 1)]
    rows[1]["identity"]["episode_id"] = "duplicate-decision-same-symbol"
    rows[1]["identity"]["decision_epoch"] = 99
    _write_json(mart_root / "feature_mart.json", {"episodes": rows})
    _write_json(reports / "evaluation" / "opening_rank1_shadow" / day / "opening_rank1_shadow_daily.json", {"day_status": "VALID"})
    result = build_prospective_shadow(day=day, reports_root=reports, mart_root=mart_root)
    payload = json.loads(Path(result["daily_json_path"]).read_text(encoding="utf-8"))
    assert payload["behavior_effect"] == "NONE_OBSERVATION_ONLY"
    assert payload["candidate_summaries"][0]["branch"]["episode_count"] == 2
    assert payload["candidate_summaries"][0]["branch"]["day_symbol_count"] == 1


def test_prospective_five_day_gate_does_not_promote_insufficient_sample(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    mart_root = reports / "evaluation" / "feature_mart" / "opening_rank1"
    days = ("2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18")
    all_rows = [_prospective_mart_episode(day, index + 1) for index, day in enumerate(days)]
    _write_json(mart_root / "feature_mart.json", {"episodes": all_rows})
    result = {}
    for day in days:
        _write_json(reports / "evaluation" / "opening_rank1_shadow" / day / "opening_rank1_shadow_daily.json", {"day_status": "VALID"})
        result = build_prospective_shadow(day=day, reports_root=reports, mart_root=mart_root)
    cumulative = json.loads(Path(result["cumulative_json_path"]).read_text(encoding="utf-8"))
    assert cumulative["valid_day_count"] == 5
    assert cumulative["status"] == "NO_AUTOMATIC_PROMOTION"
    assert all(item["decision"]["status"] == "RETAIN_SHADOW_INSUFFICIENT_BRANCH_SAMPLE" for item in cumulative["candidate_summaries"])
    assert all(not item["decision"]["behavior_patch_allowed"] for item in cumulative["candidate_summaries"])


def test_prospective_contract_has_no_execution_surface() -> None:
    assert all(candidate["responsibility"] in {"SCANNER", "ENTRY"} for candidate in CANDIDATES)
    package = Path("libs/research/rank1_feature_mart")
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    assert "OrderIntent" not in source
    assert "place_order" not in source


def test_q9_windows_adds_canonical_strategy_and_scanner_evidence(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-08-12"
    run_id = "run-1"
    decision_id = "decision-1"
    _write_json(
        reports / "operator_summary" / "daily" / day / "q9_decision_windows.json",
        {
            "windows": [
                {
                    "day": day,
                    "run_id": run_id,
                    "decision_id": decision_id,
                }
            ]
        },
    )
    _write_json(
        reports / "canonical" / day / run_id / "strategist.json",
        {"tactical_strategy": "volume_breakout"},
    )
    _write_json(
        reports / "canonical" / day / run_id / "scanner.json",
        {"candidate_ranking_table": {"rows": []}},
    )
    result = q9_windows(
        reports, [{"day": day, "decision_id": decision_id}]
    )[decision_id]
    assert result["_canonical_strategist"]["tactical_strategy"] == "volume_breakout"
    assert result["_canonical_scanner"]["candidate_ranking_table"] == {"rows": []}


def test_chart_fallback_preserves_point_in_time_opening_observation() -> None:
    decision_epoch = _epoch("2026-08-12", 9, 3) + 48
    result = _merge_opening_chart_observation(
        {
            "status": "INSUFFICIENT_EVIDENCE",
            "completed_bar_count": 0,
            "feature_max_epoch": None,
            "above_vwap": None,
        },
        {
            "decision_epoch": decision_epoch,
            "opening_observability": {
                "completed_bar_count_at_decision": 3,
                "completed_return_1m_pct": 1.25,
                "above_vwap": True,
            },
        },
        prospective=True,
    )
    assert result["status"] == "PARTIAL_OPENING_OBSERVATION_FALLBACK"
    assert result["completed_bar_count"] == 3
    assert result["feature_max_epoch"] <= decision_epoch
    assert result["evidence_source"] == "OPENING_SHADOW_POINT_IN_TIME_FALLBACK"


def test_fresh_change_contract_is_separate_and_observation_only() -> None:
    frozen = contract_payload()
    activation = activation_contract_payload()
    assert activation["contract_sha256"] != frozen["contract_sha256"]
    assert activation["behavior_effect"] == "NONE_OBSERVATION_ONLY"
    assert activation["candidate"]["candidate_id"] == "R1_FRESH_CHANGE_ACTIVATION_V1"


def test_fresh_change_shadow_keeps_historical_and_prospective_separate(
    tmp_path: Path,
) -> None:
    reports = tmp_path / "reports"
    mart_root = reports / "evaluation" / "feature_mart" / "opening_rank1"
    historical = _prospective_mart_episode("2026-08-12", 1, value=2.0)
    historical["scanner"]["source_top_change_rate"] = True
    prospective = _prospective_mart_episode("2026-08-13", 2, value=1.0)
    prospective["scanner"]["source_top_change_rate"] = True
    prospective["scanner"].update(
        {"directional_component_count": 5, "theme_match": True}
    )
    _write_json(mart_root / "feature_mart.json", {"episodes": [historical, prospective]})
    _write_json(
        reports
        / "evaluation"
        / "opening_rank1_shadow"
        / "2026-08-13"
        / "opening_rank1_shadow_daily.json",
        {"day_status": "VALID"},
    )
    result = build_fresh_change_activation_shadow(
        day="2026-08-13", reports_root=reports, mart_root=mart_root
    )
    payload = json.loads(
        Path(result["cumulative_json_path"]).read_text(encoding="utf-8")
    )
    assert payload["historical_reference"]["branch"]["day_symbol_count"] == 1
    assert payload["branch"]["day_symbol_count"] == 1
    assert payload["decision"]["status"] == "COLLECTING"
    assert payload["decision"]["behavior_patch_allowed"] is False


def test_strategy_choice_observation_exposes_all_tactics_without_behavior() -> None:
    result = build_strategy_choice_observation(
        canonical_strategist={
            "pre_llm_playbook": "pullback",
            "llm_requested_playbook": "",
            "requested_playbook_source": "deterministic",
            "final_playbook": "pullback",
            "tactical_strategy": "vwap_reclaim_pullback",
            "tactical_subtype": "vwap_reclaim_setup",
            "strategy_scores": {
                "vwap_reclaim_pullback": 0.70,
                "volume_breakout": 0.60,
            },
            "commander_invocation_hint": "RUN_REFRESH",
        },
        strategy={"market_playbook": "pullback"},
        scanner={"candidate_setup": "FRESH_CHANGE_ACTIVATION"},
    )
    assert result["behavior_effect"] == "NONE_OBSERVATION_ONLY"
    assert result["generation"]["mode"] == "TACTICAL_REFRESH_INHERITED_MARKET_FRAME"
    assert result["tactic_choice"]["catalog_tactic_count"] == 12
    assert result["tactic_choice"]["scored_tactic_count"] == 2
    assert result["tactic_choice"]["selected_is_playbook_default"] is True
    assert (
        result["candidate_setup_observation"]["setup_playbook_alignment"]
        == "MISMATCH"
    )
    unscored = [
        row
        for row in result["tactic_choice"]["option_surface"]
        if row["tactic_id"] == "event_theme_momentum"
    ][0]
    assert unscored["score_status"] == "NOT_SCORED_BY_CURRENT_MODEL"


def test_strategy_alignment_report_deduplicates_day_symbol() -> None:
    row = _prospective_mart_episode("2026-08-13", 1, value=1.0)
    row["strategy"].update(
        {
            "market_playbook": "pullback",
            "tactical_strategy": "vwap_reclaim_pullback",
        }
    )
    row["scanner"]["candidate_setup"] = "FRESH_CHANGE_ACTIVATION"
    row["strategy_choice_observation"] = {
        "evidence_status": "OBSERVED",
        "generation": {"mode": "DETERMINISTIC_MARKET_FRAME"},
        "tactic_choice": {"selected_is_playbook_default": True},
        "candidate_setup_observation": {
            "setup_playbook_alignment": "MISMATCH"
        },
    }
    duplicate = deepcopy(row)
    duplicate["identity"]["episode_id"] = "later-same-day-symbol"
    duplicate["identity"]["decision_epoch"] += 10
    result = build_strategy_alignment_report([row, duplicate])
    assert result["episode_count"] == 2
    assert result["independent_day_symbol_count"] == 1
    assert result["alignment_metrics"]["MISMATCH"]["day_symbol_count"] == 1


def test_build_episode_integrates_strategy_choice_observation() -> None:
    day = "2026-08-13"
    decision_epoch = _epoch(day, 9, 3)
    row = {
        "day": day,
        "symbol": "001210",
        "decision_id": "decision-1",
        "decision_epoch": decision_epoch,
        "baseline_epoch": decision_epoch,
        "baseline_price": 100.0,
        "opening_observability": {
            "completed_bar_count_at_decision": 3,
            "completed_return_1m_pct": 1.0,
            "candidate_snapshot": {
                "rank": 1,
                "score_total": 1.2,
                "sources": ["top_change_rate", "top_volume"],
                "source_observations": {
                    "top_change_rate": {
                        "schema_version": "kiwoom_top_change_rate_observation.v1",
                        "behavior_effect": "observation_only",
                        "api_id": "ka10027",
                        "source_rank": 1,
                        "point_in_time": True,
                        "raw_fields": {"flu_rt": "+6.47"},
                        "normalized": {"change_rate_pct": 6.47},
                    }
                },
                "score_breakdown": {"momentum": 0.2, "trend": 0.1},
            },
        },
    }
    window = {
        "_canonical_strategist": {
            "pre_llm_playbook": "pullback",
            "final_playbook": "pullback",
            "requested_playbook_source": "deterministic",
            "tactical_strategy": "vwap_reclaim_pullback",
            "strategy_scores": {"vwap_reclaim_pullback": 0.7},
        },
        "_canonical_scanner": {"candidate_ranking_table": {"rows": []}},
    }
    result = build_episode(
        row=row,
        prospective=True,
        window=window,
        minute_rows=[_minute(day, minute, 100 + minute) for minute in range(10)],
        daily_rows=[],
        longitudinal={},
    )
    assert result["market"]["exposure_direction"] == "LONG_RISK_OR_OTHER"
    assert result["scanner"]["candidate_setup"] == "FRESH_CHANGE_ACTIVATION"
    assert result["scanner"]["top_change_rate_observation_status"] == "OBSERVED_POINT_IN_TIME"
    assert (
        result["scanner"]["top_change_rate_observation"]["normalized"][
            "change_rate_pct"
        ]
        == 6.47
    )
    assert (
        result["strategy_choice_observation"]["candidate_setup_observation"][
            "setup_playbook_alignment"
        ]
        == "MISMATCH"
    )
