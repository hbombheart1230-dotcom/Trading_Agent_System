from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    ALLOWED_STATUSES,
    CANDIDATE_IDS,
    CANDIDATE_REGISTRY,
    CONTRACT_VERSION,
    FEATURE_COLUMNS,
    LIVE_RESEARCH_COST_PCT,
    QUESTIONS,
    ROW_COLUMNS,
    SCHEMA_VERSION,
)
from .loaders import load_json, mapping, metric_snapshot


PERMANENTLY_CLOSED = {
    "DISLOCATION_REBOUND",
    "OPEN_0_20_RANK1_30M",
    "R1_FRESH_CHANGE_ACTIVATION_V1",
    "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1",
    "LATENT_REACTIVATION_FRESH_TRIGGER",
    "BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION",
    "R1_SCANNER_RISK_HIGH_30M_V1",
}

TARGET_HORIZONS = {
    "IMMEDIATE_OPENING_PROBE": "+5m",
    "CONFIRMED_RECURRENT_RANK": "+30m",
    "DISLOCATION_REBOUND": "+60m",
    "OPEN_0_20_RANK1_30M": "+30m",
    "R1_FRESH_CHANGE_ACTIVATION_V1": "+30m",
    "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1": "+15m",
    "LATENT_REACTIVATION_FRESH_TRIGGER": "+30m",
    "SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1": "+180m",
    "STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1": "+30m",
    "BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION": "+30m",
    "BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1": "+30m",
    "R1_SCANNER_RISK_HIGH_30M_V1": "+30m",
    "HIGH_COMMON_SHORT_ALPHA_V1": "+5m",
    "TOP_VALUE_VOLUME_NEGATIVE_CONTROL_V1": "+5m",
}

FEATURE_HINTS = {
    "IMMEDIATE_OPENING_PROBE": {
        "rank_and_selection": ["opening_rank1", "immediate_probe"],
        "horizon_and_exit": ["+5m"],
    },
    "CONFIRMED_RECURRENT_RANK": {
        "rank_and_selection": ["opening_rank1", "recurrent_rank"],
        "horizon_and_exit": ["+30m"],
    },
    "DISLOCATION_REBOUND": {
        "price_structure": ["opening_dislocation", "rebound"],
        "horizon_and_exit": ["+60m"],
    },
    "OPEN_0_20_RANK1_30M": {
        "rank_and_selection": ["opening_rank1", "09:00-09:20_control"],
        "horizon_and_exit": ["+30m"],
    },
    "R1_FRESH_CHANGE_ACTIVATION_V1": {
        "rank_and_selection": ["fresh_top_change"],
        "horizon_and_exit": ["+30m"],
    },
    "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1": {
        "price_structure": ["daily_ma5_20_post_cross_extended"],
        "horizon_and_exit": ["+15m"],
    },
    "LATENT_REACTIVATION_FRESH_TRIGGER": {
        "rank_and_selection": ["prior_rank1", "fresh_reactivation"],
        "horizon_and_exit": ["D+1-D+5 discovery", "+30m trigger"],
    },
    "SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1": {
        "asset_class": ["large_cap_common_stock", "fixed_two_symbol_universe"],
        "rank_and_selection": ["momentum_volume_top1"],
        "horizon_and_exit": ["+180m"],
    },
    "STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1": {
        "rank_and_selection": ["R1_pre_stage2", "R2_post_stage2"],
        "agent_lineage": ["strategist_stage2", "scanner_rerun"],
        "horizon_and_exit": ["+30m"],
    },
    "BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION": {
        "external_signal": ["btc_multi_horizon_momentum"],
        "price_structure": ["woori_local_confirmation"],
        "volume_and_flow": ["woori_volume_confirmation"],
    },
    "BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1": {
        "external_signal": ["btc_0855_24h_thresholds", "first_vs_repeated_surge"],
        "price_structure": ["btc_20d_60d_ath_breakout", "woori_opening_gap"],
        "volume_and_flow": ["woori_0903_0905_confirmation"],
        "horizon_and_exit": ["09:00", "09:03", "09:05", "09:10", "pullback", "+30m"],
    },
    "R1_SCANNER_RISK_HIGH_30M_V1": {
        "market_regime": ["scanner_risk_band=HIGH"],
        "rank_and_selection": ["opening_rank1"],
        "horizon_and_exit": ["+30m"],
    },
    "HIGH_COMMON_SHORT_ALPHA_V1": {
        "market_regime": ["scanner_risk_band=HIGH"],
        "asset_class": ["common_stock"],
        "horizon_and_exit": ["+5m", "+15m", "+30m", "+60m", "EOD"],
    },
    "TOP_VALUE_VOLUME_NEGATIVE_CONTROL_V1": {
        "asset_class": ["mixed_control"],
        "rank_and_selection": ["top_value_or_top_volume"],
        "volume_and_flow": ["liquidity_only_control"],
        "horizon_and_exit": ["+5m", "+15m", "+30m", "+60m", "EOD"],
    },
}


def _feature_evidence(candidate_id: str) -> dict[str, list[str]]:
    hints = FEATURE_HINTS.get(candidate_id, {})
    return {column: list(hints.get(column, [])) for column in FEATURE_COLUMNS}


def _normalize_status(candidate_id: str, row: Mapping[str, Any]) -> str:
    if candidate_id in PERMANENTLY_CLOSED:
        return "CLOSED"
    decision = str(
        mapping(row.get("final_offline_review")).get("decision")
        or mapping(row.get("sensitivity_review")).get("decision")
        or row.get("source_status")
        or ""
    ).upper()
    bucket = str(row.get("board_bucket") or "").upper()
    if "PROMOT" in decision and "REVIEW" not in decision:
        return "PROMOTED"
    if decision.startswith(("REJECT", "FAIL")) or bucket.startswith("CLOSED"):
        return "CLOSED"
    if "PASS" in decision or "REVIEW_ELIGIBLE" in decision or "REVIEW_READY" in decision:
        return "REVIEW_READY"
    if bucket in {"RUNTIME_VALIDATION_NEXT", "BACKGROUND_RUNTIME_REQUIRED", "OBSERVE_FIXED"}:
        return "PROSPECTIVE"
    return "DISCOVERY"


def _decision(row: Mapping[str, Any]) -> str:
    return str(
        mapping(row.get("final_offline_review")).get("decision")
        or mapping(row.get("sensitivity_review")).get("decision")
        or row.get("source_status")
        or "INSUFFICIENT_EVIDENCE"
    )


def _rationale(row: Mapping[str, Any]) -> str:
    return str(
        mapping(row.get("final_offline_review")).get("rationale")
        or mapping(row.get("sensitivity_review")).get("rationale")
        or row.get("evidence_note")
        or "현재 입력 산출물에 설명 가능한 근거가 없다."
    )


def _latest_stage2_source(reports_root: Path, through_day: str) -> tuple[dict[str, Any], dict[str, Any]]:
    root = reports_root / "evaluation" / "agent_effectiveness"
    candidates = []
    for path in root.glob("cumulative_*/strategist_stage2_effectiveness_deep_dive.json"):
        end_day = path.parent.name.rsplit("_", 1)[-1]
        if end_day <= through_day.replace("-", ""):
            candidates.append((end_day, path))
    if not candidates:
        daily = root / through_day / "strategist_stage2_effectiveness_deep_dive.json"
        return load_json(daily)
    return load_json(max(candidates, key=lambda item: item[0])[1])


def _stage2_candidate(reports_root: Path, through_day: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload, source = _latest_stage2_source(reports_root, through_day)
    metric = mapping(mapping(payload.get("changed_symbol_by_horizon")).get("+30m"))
    coverage = mapping(payload.get("coverage"))
    historical = {
        "sample_count": int(metric.get("comparison_count") or 0),
        "window_count": int(metric.get("observation_count") or 0),
        "win_rate": metric.get("after_positive_rate"),
        "avg_net_return_pct": metric.get("after_average_return_pct"),
        "profit_factor": None,
        "max_drawdown_pct": None,
        "coverage": None,
        "avg_mfe_pct": None,
        "avg_mae_pct": None,
    }
    return (
        {
            "candidate_id": "STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1",
            "target_horizon": "+30m",
            "source_status": "OBSERVATION_ONLY",
            "board_bucket": "OBSERVE_FIXED",
            "historical": historical,
            "validation": {},
            "prospective": {},
            "concentration": {
                "day_count": metric.get("day_count"),
                "max_single_day_share": metric.get("max_single_day_share"),
            },
            "agent_attribution": {
                "refresh_records": coverage.get("refresh_records"),
                "stage2_attributable_records": coverage.get("stage2_attributable_records"),
                "same_symbol_records": coverage.get("same_symbol_records"),
                "changed_symbol_records": coverage.get("changed_symbol_records"),
                "before_avg_return_pct": metric.get("before_average_return_pct"),
                "after_avg_return_pct": metric.get("after_average_return_pct"),
                "average_delta_pct": metric.get("average_delta_pct"),
                "interpretation": mapping(payload.get("role_definition")).get(
                    "important_boundary"
                ),
            },
            "evidence_note": (
                "R2는 2차 전략가 이후 Scanner 재실행 결과이며 LLM의 명시적 종목 교체와 동일하지 않다."
            ),
            "next_action": "재순위·후보 교체·진입 강화·no-trade 권한별 표본만 누적한다.",
            "source_keys": ["strategist_stage2_effectiveness"],
        },
        source,
    )


def _negative_control_candidate(short_alpha: Mapping[str, Any]) -> dict[str, Any]:
    cohorts = mapping(short_alpha.get("cohort_review")).get("cohorts") or []
    cohort = next(
        (
            mapping(value)
            for value in cohorts
            if mapping(value).get("cohort_id") == "TOP_VALUE_VOLUME_NEGATIVE_CONTROL_V1"
        ),
        {},
    )
    historical = metric_snapshot(mapping(cohort.get("horizons")).get("+5m"))
    return {
        "candidate_id": "TOP_VALUE_VOLUME_NEGATIVE_CONTROL_V1",
        "target_horizon": "+5m",
        "source_status": "NEGATIVE_CONTROL",
        "board_bucket": "OBSERVE_FIXED",
        "historical": historical,
        "validation": {},
        "prospective": {},
        "concentration": {
            "day_count": cohort.get("day_count"),
            "largest_day_share": cohort.get("largest_day_share"),
            "largest_symbol_share": cohort.get("largest_symbol_share"),
        },
        "evidence_note": "거래대금·거래량만 높은 후보가 충분한 구분자인지 확인하는 고정 음성 대조군이다.",
        "next_action": "대조군으로만 누적하며 독립 정책 후보로 승격하지 않는다.",
        "source_keys": ["short_alpha_discriminator"],
    }


def _source_artifacts(
    row: Mapping[str, Any], sources: Mapping[str, Any]
) -> list[dict[str, Any]]:
    artifacts = []
    for key in row.get("source_keys") or []:
        source = mapping(sources.get(str(key)))
        artifacts.append(
            {
                "source_key": str(key),
                "path": source.get("path"),
                "available": source.get("available"),
                "error": source.get("error"),
            }
        )
    return artifacts


def _net_metrics(row: Mapping[str, Any]) -> dict[str, Any]:
    for cohort in ("prospective", "validation", "historical"):
        metric = mapping(row.get(cohort))
        if int(metric.get("sample_count") or 0) > 0:
            return {"cohort": cohort, **dict(metric)}
    return {"cohort": None, **metric_snapshot({})}


def _question_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for question in QUESTIONS:
        question_id = str(question["question_id"])
        grouped = [row for row in rows if row["question_id"] == question_id]
        counts = {
            status: sum(row["status"] == status for row in grouped)
            for status in ALLOWED_STATUSES
        }
        summaries.append(
            {
                **dict(question),
                "candidate_count": len(grouped),
                "status_counts": counts,
                "active_candidate_ids": [
                    row["candidate_id"]
                    for row in grouped
                    if row["status"] in {"DISCOVERY", "PROSPECTIVE", "REVIEW_READY"}
                ],
                "closed_candidate_ids": [
                    row["candidate_id"] for row in grouped if row["status"] == "CLOSED"
                ],
            }
        )
    return summaries


def canonicalize_board(
    legacy: Mapping[str, Any], *, reports_root: Path, through_day: str
) -> dict[str, Any]:
    legacy_rows = {
        str(mapping(value).get("candidate_id")): mapping(value)
        for value in legacy.get("candidates") or []
    }
    sources = dict(mapping(legacy.get("sources")))
    stage2, stage2_source = _stage2_candidate(reports_root, through_day)
    legacy_rows[stage2["candidate_id"]] = stage2
    sources["strategist_stage2_effectiveness"] = stage2_source
    negative = _negative_control_candidate(mapping(legacy.get("short_alpha_discriminator")))
    legacy_rows[negative["candidate_id"]] = negative
    sources.setdefault(
        "short_alpha_discriminator",
        {
            "path": str(
                reports_root
                / "evaluation"
                / "short_alpha_discriminator"
                / through_day
                / "short_alpha_discriminator.json"
            ),
            "available": True,
            "error": None,
        },
    )

    rows: list[dict[str, Any]] = []
    for question_id, candidate_id, hypothesis in CANDIDATE_REGISTRY:
        legacy_row = legacy_rows.get(candidate_id, {})
        status = _normalize_status(candidate_id, legacy_row)
        row = {
            "question_id": question_id,
            "candidate_id": candidate_id,
            "status": status,
            "hypothesis": hypothesis,
            "feature_evidence": _feature_evidence(candidate_id),
            "target_horizon": str(
                legacy_row.get("target_horizon")
                or TARGET_HORIZONS.get(candidate_id)
                or ""
            ),
            "historical_evidence": dict(mapping(legacy_row.get("historical"))),
            "prospective_evidence": dict(mapping(legacy_row.get("prospective"))),
            "sample_quality": {
                "historical_sample_count": int(
                    mapping(legacy_row.get("historical")).get("sample_count") or 0
                ),
                "prospective_sample_count": int(
                    mapping(legacy_row.get("prospective")).get("sample_count") or 0
                ),
                "source_status": legacy_row.get("source_status"),
            },
            "concentration": dict(mapping(legacy_row.get("concentration"))),
            "net_metrics": _net_metrics(legacy_row),
            "agent_attribution": dict(mapping(legacy_row.get("agent_attribution"))),
            "decision": _decision(legacy_row),
            "rationale": _rationale(legacy_row),
            "next_action": (
                "종료 상태를 유지하고 참고 근거만 누적한다."
                if status == "CLOSED"
                else str(legacy_row.get("next_action") or "고정 계약으로 표본을 누적한다.")
            ),
            "source_artifacts": _source_artifacts(legacy_row, sources),
            "updated_through_day": through_day,
        }
        rows.append(row)

    column_errors = [
        row["candidate_id"]
        for row in rows
        if tuple(row.keys()) != ROW_COLUMNS
        or tuple(row["feature_evidence"].keys()) != FEATURE_COLUMNS
    ]
    candidate_ids = tuple(row["candidate_id"] for row in rows)
    missing_sources = [
        key
        for key, source in sources.items()
        if not mapping(source).get("available") or mapping(source).get("error")
    ]
    question_summaries = _question_summaries(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "behavior_effect": "evaluation_only",
        "through_day": through_day,
        "authority": {
            "closeout_explanation_source": "alpha_research_board_only",
            "legacy_evaluations_are_inputs_only": True,
            "questions_frozen": True,
            "candidate_ids_frozen": True,
            "row_columns_frozen": True,
            "feature_columns_frozen": True,
        },
        "cost_authority": {
            "live_equity_round_trip_pct": LIVE_RESEARCH_COST_PCT,
            "rule": "Gross, live-research net, and broker mock net must not be mixed.",
        },
        "questions": question_summaries,
        "candidate_count": len(rows),
        "candidate_ids": list(candidate_ids),
        "row_columns": list(ROW_COLUMNS),
        "feature_columns": list(FEATURE_COLUMNS),
        "candidates": rows,
        "closeout_summary": [
            {
                "question_id": row["question_id"],
                "question": row["question"],
                "active_candidates": len(row["active_candidate_ids"]),
                "closed_candidates": len(row["closed_candidate_ids"]),
                "statement": (
                    f"{row['question_id']}: 활성 {len(row['active_candidate_ids'])}개, "
                    f"CLOSED {len(row['closed_candidate_ids'])}개. "
                    "판정은 historical과 prospective를 분리해 유지한다."
                ),
            }
            for row in question_summaries
        ],
        "settled_findings": list(legacy.get("settled_findings") or []),
        "integrity": {
            "status": (
                "FAIL_CONTRACT"
                if candidate_ids != CANDIDATE_IDS or column_errors
                else "PASS_WITH_MISSING_SOURCES"
                if missing_sources
                else "PASS"
            ),
            "candidate_registry_matches": candidate_ids == CANDIDATE_IDS,
            "column_errors": column_errors,
            "missing_or_invalid_sources": sorted(set(missing_sources)),
            "historical_prospective_separated": True,
        },
        "sources": sources,
        "behavior_change_authorized": False,
    }


__all__ = ["canonicalize_board"]
