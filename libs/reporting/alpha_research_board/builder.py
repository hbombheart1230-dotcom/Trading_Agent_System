from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    LIVE_RESEARCH_COST_PCT,
    SCHEMA_VERSION,
    SETTLED_FINDINGS,
    SOURCE_PATHS,
    TRACKS,
)
from .canonical import canonicalize_board
from .loaders import find_by_id, find_horizon, load_json, mapping, metric_snapshot
from .large_cap_review import build_large_cap_daily_review
from .report import render_alpha_research_board
from .remaining_reviews import (
    build_remaining_candidate_reviews,
    render_remaining_candidate_reviews,
)
from .runtime_validation import (
    build_immediate_opening_runtime_validation,
    render_immediate_opening_runtime_validation,
)
from .sensitivity import build_risk_high_sensitivity, render_risk_high_sensitivity
from ..short_alpha_discriminator import build_short_alpha_discriminator
from ..short_alpha_discriminator.report import render_short_alpha_discriminator


def _candidate(
    *,
    candidate_id: str,
    track_id: str,
    discriminator: str,
    target_horizon: str,
    source_status: str,
    board_bucket: str,
    owner: str,
    historical: Mapping[str, Any] | None = None,
    validation: Mapping[str, Any] | None = None,
    prospective: Mapping[str, Any] | None = None,
    concentration: Mapping[str, Any] | None = None,
    evidence_note: str,
    next_action: str,
    source_keys: list[str],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "track_id": track_id,
        "discriminator": discriminator,
        "target_horizon": target_horizon,
        "source_status": source_status,
        "board_bucket": board_bucket,
        "responsibility_if_proven": owner,
        "historical": dict(historical or {}),
        "validation": dict(validation or {}),
        "prospective": dict(prospective or {}),
        "concentration": dict(concentration or {}),
        "evidence_note": evidence_note,
        "next_action": next_action,
        "source_keys": source_keys,
    }


def _feature_candidates(
    feature_payload: Mapping[str, Any],
    prospective_payload: Mapping[str, Any],
    concentrations: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prospective_rows = prospective_payload.get("candidate_summaries") or []
    specs = [
        (
            "R1_SCANNER_RISK_HIGH_30M_V1",
            "scanner.risk_band == HIGH",
            "+30m",
            "SCANNER",
        ),
        (
            "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1",
            "chart.daily_ma5_20_cross_state == POST_CROSS_EXTENDED",
            "+15m",
            "MONITOR_ENTRY",
        ),
    ]
    selected = feature_payload.get("prospective_shadow_candidates") or []
    for candidate_id, label, horizon, owner in specs:
        prospective = find_by_id(prospective_rows, "candidate_id", candidate_id)
        candidate_meta = mapping(prospective.get("candidate"))
        expected = candidate_meta.get("expected_value")
        feature_path = candidate_meta.get("feature_path")
        historical_row = next(
            (
                mapping(row)
                for row in selected
                if mapping(row).get("feature") == feature_path
                and mapping(row).get("category") == expected
            ),
            {},
        )
        decision = mapping(prospective.get("decision"))
        source_status = str(
            decision.get("status")
            or historical_row.get("decision")
            or "INSUFFICIENT_EVIDENCE"
        )
        bucket = (
            "ACTION_REVIEW"
            if source_status == "SINGLE_BEHAVIOR_PATCH_REVIEW_ELIGIBLE"
            else "OBSERVE_FIXED"
        )
        branch = metric_snapshot(prospective.get("branch"))
        rows.append(
            _candidate(
                candidate_id=candidate_id,
                track_id="OPENING_CONDITIONAL",
                discriminator=label,
                target_horizon=horizon,
                source_status=source_status,
                board_bucket=bucket,
                owner=owner,
                historical=metric_snapshot(historical_row.get("train")),
                validation=metric_snapshot(historical_row.get("validation")),
                prospective=branch,
                concentration=concentrations.get(candidate_id),
                evidence_note=(
                    "Prospective에서도 비교군을 이겼지만 날짜·종목 집중도 민감도 검토가 필요함."
                    if bucket == "ACTION_REVIEW"
                    else "과거 방향성이 prospective에서 유지되지 못함."
                ),
                next_action=(
                    "집중 종목·최대 일자를 제외한 민감도 검토 후 승격 또는 기각. 다른 영역은 변경하지 않음."
                    if bucket == "ACTION_REVIEW"
                    else "관측만 유지하고 과거 성과만으로 승격하지 않음."
                ),
                source_keys=["feature_candidates", "prospective_candidates"],
            )
        )
    return rows


def _prospective_concentrations(
    *, reports_root: Path, first_day: str, through_day: str
) -> dict[str, dict[str, Any]]:
    daily_root = (
        reports_root
        / "evaluation"
        / "feature_mart"
        / "opening_rank1"
        / "prospective"
    )
    day_symbols: dict[str, set[tuple[str, str]]] = {}
    for path in sorted(daily_root.glob("20??-??-??/rank1_candidate_shadow_daily.json")):
        day = path.parent.name
        if day < first_day or day > through_day:
            continue
        payload, source = load_json(path)
        if source.get("error"):
            continue
        for value in payload.get("observations") or []:
            row = mapping(value)
            if not row.get("matched"):
                continue
            candidate_id = str(row.get("candidate_id") or "")
            symbol = str(row.get("symbol") or "")
            row_day = str(row.get("day") or day)
            if candidate_id and symbol:
                day_symbols.setdefault(candidate_id, set()).add((row_day, symbol))

    result: dict[str, dict[str, Any]] = {}
    for candidate_id, pairs in day_symbols.items():
        days = Counter(day for day, _symbol in pairs)
        symbols = Counter(symbol for _day, symbol in pairs)
        count = len(pairs)
        result[candidate_id] = {
            "independent_day_symbol_count": count,
            "observed_day_count": len(days),
            "largest_day_share": round(max(days.values()) / count, 4) if count else None,
            "largest_symbol_share": round(max(symbols.values()) / count, 4) if count else None,
            "largest_day": days.most_common(1)[0][0] if days else None,
            "largest_symbol": symbols.most_common(1)[0][0] if symbols else None,
        }
    return result


def _fresh_change(payload: Mapping[str, Any]) -> dict[str, Any]:
    reference = mapping(payload.get("historical_reference"))
    historical = mapping(reference.get("branch"))
    historical_metric = mapping(mapping(historical.get("horizons")).get("+30m"))
    prospective_metric = mapping(mapping(mapping(payload.get("branch")).get("horizons")).get("+30m"))
    source_status = str(mapping(payload.get("decision")).get("status") or "INSUFFICIENT_EVIDENCE")
    return _candidate(
        candidate_id="R1_FRESH_CHANGE_ACTIVATION_V1",
        track_id="OPENING_CONDITIONAL",
        discriminator="fresh top-change activation",
        target_horizon="+30m",
        source_status=source_status,
        board_bucket="CLOSED_NEGATIVE_PROSPECTIVE",
        owner="SCANNER",
        historical=metric_snapshot(historical_metric),
        prospective=metric_snapshot(prospective_metric),
        evidence_note="과거 양수 결과가 prospective에서 음수로 뒤집힘.",
        next_action="승격 후보에서 기각하고 과거 참고자료로만 보존.",
        source_keys=["fresh_change"],
    )


def _opening_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = mapping(payload.get("summary"))
    lanes = mapping(summary.get("conditional_lane_summaries"))
    rows: list[dict[str, Any]] = []
    for lane_id, horizon, note in [
        (
            "IMMEDIATE_OPENING_PROBE",
            "+5m",
            "즉시 반응은 초반이 가장 강하고 EOD로 갈수록 약해짐.",
        ),
        (
            "CONFIRMED_RECURRENT_RANK",
            "+30m",
            "방향은 강하지만 독립 표본이 지나치게 작음.",
        ),
        (
            "DISLOCATION_REBOUND",
            "+60m",
            "5분보다 30~60분 반등 근거가 강함.",
        ),
    ]:
        lane = mapping(lanes.get(lane_id))
        horizon_row = mapping(mapping(lane.get("horizons")).get(horizon))
        rows.append(
            _candidate(
                candidate_id=lane_id,
                track_id="OPENING_CONDITIONAL",
                discriminator=lane_id.lower(),
                target_horizon=horizon,
                source_status="COLLECTING",
                board_bucket="OBSERVE_FIXED",
                owner="SCANNER_OR_HORIZON_REVIEW",
                prospective=metric_snapshot(horizon_row.get("live_net")),
                evidence_note=note,
                next_action="기존 고정 observer만 지속하고 새 lane은 만들지 않음.",
                source_keys=["opening_cumulative"],
            )
        )
    return rows


def _broad_opening(payload: Mapping[str, Any]) -> dict[str, Any]:
    decision = mapping(payload.get("promotion_decision"))
    values = mapping(decision.get("values"))
    return _candidate(
        candidate_id="OPEN_0_20_RANK1_30M",
        track_id="OPENING_CONDITIONAL",
        discriminator="all opening Rank-1 candidates",
        target_horizon="+30m",
        source_status=str(decision.get("status") or "INSUFFICIENT_EVIDENCE"),
        board_bucket="CLOSED",
        owner="NONE",
        prospective={
            "sample_count": values.get("observed_count", 0),
            "window_count": values.get("observed_count", 0),
            "win_rate": values.get("win_rate"),
            "avg_net_return_pct": values.get("average_net_return_pct"),
            "profit_factor": values.get("profit_factor"),
            "coverage": values.get("coverage"),
        },
        concentration={
            "largest_day_share": values.get("largest_day_share"),
            "largest_symbol_share": values.get("largest_symbol_share"),
        },
        evidence_note="평균은 양수지만 고정된 종목 집중도 gate를 통과하지 못함.",
        next_action="종료. Rank-1 전부 진입 근거로 재해석하지 않음.",
        source_keys=["opening_cumulative"],
    )


def _latent(payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = mapping(payload.get("summary"))
    horizon = mapping(mapping(summary.get("horizons")).get("+30m"))
    return _candidate(
        candidate_id="LATENT_REACTIVATION_FRESH_TRIGGER",
        track_id="SCANNER_REACTIVATION_HORIZON",
        discriminator="fresh D+1-D+5 trigger after prior Rank-1 discovery",
        target_horizon="+30m",
        source_status=str(summary.get("status") or "INSUFFICIENT_EVIDENCE"),
        board_bucket="CLOSED",
        owner="NONE",
        prospective=metric_snapshot(horizon.get("live_net")),
        concentration={
            "largest_day_share": summary.get("largest_day_share"),
            "largest_symbol_share": summary.get("largest_symbol_share"),
            "positive_day_ratio": summary.get("positive_day_ratio"),
        },
        evidence_note="수익률은 양수지만 날짜·종목 집중도와 양수 일자 gate를 통과하지 못함.",
        next_action="고정 계약은 기각하고 30~60분 방향성만 연구 힌트로 보존.",
        source_keys=["latent_reactivation"],
    )


def _btc_woori(payload: Mapping[str, Any]) -> dict[str, Any]:
    horizon = find_horizon(payload.get("episode_horizons"), "+30m")
    return _candidate(
        candidate_id="BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION",
        track_id="BTC_WOORI",
        discriminator="BTC multi-horizon momentum + Woori local price/volume confirmation",
        target_horizon="+30m",
        source_status=str(payload.get("conclusion") or "INSUFFICIENT_EVIDENCE"),
        board_bucket="OBSERVE_FIXED",
        owner="BTC_WOORI_BASELINE",
        historical=metric_snapshot(horizon.get("real_net")),
        evidence_note="BTC 단독과 광범위 v2는 약하고, 독립 v2-only +30분 하위군만 양수임.",
        next_action="고정된 현지 확인 하위군만 prospective로 수집.",
        source_keys=["btc_woori_history"],
    )


def _large_cap_candidate(reports_root: Path, through_day: str) -> tuple[dict[str, Any], dict[str, Any]]:
    review = build_large_cap_daily_review(
        reports_root=reports_root, through_day=through_day
    )
    live_net = metric_snapshot(review.get("base"))
    live_net["window_count"] = int(mapping(review.get("base")).get("window_count") or 0)
    row = _candidate(
        candidate_id="SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1",
        track_id="LARGE_CAP_TWO_SYMBOL",
        discriminator="momentum + volume confirmation within fixed two-symbol universe",
        target_horizon="+180m",
        source_status=str(review.get("decision") or "RUNTIME_DATA_REQUIRED"),
        board_bucket="BACKGROUND_RUNTIME_REQUIRED",
        owner="SAMSUNG_HYNIX_BASELINE",
        prospective=live_net,
        evidence_note="정합성 수정 이후 하루만 비교 가능하며 반복 window는 독립 거래가 아님.",
        next_action="과거 시점 오류 자료를 섞지 않고 수정 이후 day-level episode만 누적.",
        source_keys=["large_cap_daily"],
    )
    return row, {
        "path": "multiple_daily_artifacts",
        "available": bool(review.get("source_count")),
        "error": "INVALID_DAILY_ARTIFACT" if review.get("invalid_sources") else None,
        "through_day": through_day,
        "source_count": review.get("source_count"),
    }


def _attention_order(candidates: list[dict[str, Any]]) -> list[str]:
    order = {
        "RUNTIME_VALIDATION_NEXT": 0,
        "BACKGROUND_RUNTIME_REQUIRED": 1,
        "ACTION_REVIEW": 2,
        "OBSERVE_FIXED": 3,
        "DATA_REPAIR_BOUNDARY": 4,
        "CLOSED_AFTER_SENSITIVITY_REVIEW": 5,
        "CLOSED_NEGATIVE_PROSPECTIVE": 6,
        "CLOSED": 7,
    }
    return [
        row["candidate_id"]
        for row in sorted(
            candidates,
            key=lambda row: (order.get(str(row.get("board_bucket")), 9), row["candidate_id"]),
        )
    ]


def build_alpha_research_board(
    *, reports_root: Path, through_day: str
) -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for key, relative_path in SOURCE_PATHS.items():
        payloads[key], sources[key] = load_json(reports_root / relative_path)

    contract = mapping(payloads.get("prospective_contract"))
    concentrations = _prospective_concentrations(
        reports_root=reports_root,
        first_day=str(contract.get("first_eligible_day") or "0000-00-00"),
        through_day=through_day,
    )
    candidates = _feature_candidates(
        payloads["feature_candidates"],
        payloads["prospective_candidates"],
        concentrations,
    )
    risk_high_sensitivity = build_risk_high_sensitivity(
        reports_root=reports_root,
        first_day=str(contract.get("first_eligible_day") or "0000-00-00"),
        through_day=through_day,
    )
    for row in candidates:
        if row.get("candidate_id") != "R1_SCANNER_RISK_HIGH_30M_V1":
            continue
        row["sensitivity_review"] = {
            "decision": risk_high_sensitivity.get("decision"),
            "rationale": risk_high_sensitivity.get("rationale"),
        }
        if risk_high_sensitivity.get("decision") != "PROMOTION_REVIEW_PASS":
            row["board_bucket"] = "CLOSED_AFTER_SENSITIVITY_REVIEW"
            row["evidence_note"] = (
                "과거·검증·prospective 평균은 양수였지만 수익 기여 종목 leave-one-out에서 PF 기준이 무너짐."
            )
            row["next_action"] = (
                "일반 risk-band 구분자로는 기각. 결과를 보고 threshold를 재튜닝하지 않음."
            )
    candidates.extend(_opening_rows(payloads["opening_cumulative"]))
    candidates.extend(
        [
            _broad_opening(payloads["opening_cumulative"]),
            _fresh_change(payloads["fresh_change"]),
            _latent(payloads["latent_reactivation"]),
            _btc_woori(payloads["btc_woori_history"]),
        ]
    )
    large_cap, large_cap_source = _large_cap_candidate(reports_root, through_day)
    candidates.append(large_cap)
    sources["large_cap_daily"] = large_cap_source
    remaining_reviews = build_remaining_candidate_reviews(
        reports_root=reports_root, through_day=through_day
    )
    broad_btc_review = next(
        (
            mapping(row)
            for row in remaining_reviews.get("reviews") or []
            if mapping(row).get("candidate_id") == "BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION"
        ),
        {},
    )
    strong_btc_history = next(
        (
            mapping(row)
            for row in broad_btc_review.get("by_btc_regime") or []
            if mapping(row).get("btc_regime") == "strong_bull"
        ),
        {},
    )
    candidates.append(
        _candidate(
            candidate_id="BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1",
            track_id="BTC_WOORI",
            discriminator="BTC 60m >= 1.0% or 24h >= 3.0%, plus Woori local confirmation",
            target_horizon="+30m",
            source_status="PROSPECTIVE_SHADOW_FROM_2026_08_25",
            board_bucket="BACKGROUND_RUNTIME_REQUIRED",
            owner="BTC_WOORI_BASELINE",
            historical=metric_snapshot(strong_btc_history),
            evidence_note=(
                "The historical strong-bull subgroup is hypothesis-generating only; "
                "the rejected broad BTC rule remains closed."
            ),
            next_action=(
                "Collect only the fixed additive shadow variant from the next full session."
            ),
            source_keys=["btc_woori_history"],
        )
    )
    short_alpha_review = build_short_alpha_discriminator(
        reports_root=reports_root,
        through_day=through_day,
    )
    short_cohort_review = mapping(short_alpha_review.get("cohort_review"))
    short_historical = mapping(short_cohort_review.get("historical_reference"))
    short_prospective = mapping(short_cohort_review.get("prospective"))
    historical_5m = mapping(mapping(short_historical.get("horizons")).get("+5m"))
    prospective_5m = mapping(mapping(short_prospective.get("horizons")).get("+5m"))
    candidates.append(
        _candidate(
            candidate_id="HIGH_COMMON_SHORT_ALPHA_V1",
            track_id="OPENING_CONDITIONAL",
            discriminator="risk HIGH + common stock short-horizon alpha",
            target_horizon="+5m",
            source_status="PROSPECTIVE_SHADOW_FROM_2026_08_25",
            board_bucket="BACKGROUND_RUNTIME_REQUIRED",
            owner="SCANNER_OR_HORIZON_REVIEW",
            historical=metric_snapshot(historical_5m),
            prospective=metric_snapshot(prospective_5m),
            concentration={
                "historical_day_count": short_historical.get("day_count"),
                "historical_largest_day_share": short_historical.get("largest_day_share"),
                "historical_largest_symbol_share": short_historical.get("largest_symbol_share"),
            },
            evidence_note=(
                "Post-hoc historical discriminator. Historical and prospective "
                "episodes are kept separate and no behavior is changed."
            ),
            next_action=(
                "Collect the frozen HIGH common-stock cohort at +5m/+15m/+30m/EOD."
            ),
            source_keys=["short_alpha_discriminator"],
        )
    )
    runtime_validation = build_immediate_opening_runtime_validation(
        reports_root=reports_root, through_day=through_day
    )
    reviews_by_id = {
        str(row.get("candidate_id")): mapping(row)
        for row in remaining_reviews.get("reviews") or []
    }
    for row in candidates:
        review = reviews_by_id.get(str(row.get("candidate_id")))
        if not review:
            continue
        row["final_offline_review"] = {
            "decision": review.get("decision"),
            "rationale": review.get("rationale"),
        }
        decision = str(review.get("decision") or "")
        if decision == "READY_FOR_FIXED_RUNTIME_VALIDATION":
            row["board_bucket"] = "RUNTIME_VALIDATION_NEXT"
            row["next_action"] = "기존 observer로 고정된 5거래일 prospective 런 검증 수행."
        elif decision == "RUNTIME_DATA_REQUIRED":
            row["board_bucket"] = "BACKGROUND_RUNTIME_REQUIRED"
            row["next_action"] = "행동 변경 없이 기존 artifact로 필요한 독립 표본만 수집."
        elif decision.startswith("REJECT"):
            row["board_bucket"] = "CLOSED_AFTER_SENSITIVITY_REVIEW"
            row["evidence_note"] = str(review.get("rationale") or row.get("evidence_note"))
            row["next_action"] = "오프라인 판정 종료. 재튜닝하거나 이름을 바꿔 재개하지 않음."

    missing_sources = [
        key for key, source in sources.items() if not source.get("available") or source.get("error")
    ]
    legacy_payload = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": "evaluation_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "through_day": through_day,
        "cost_authority": {
            "live_equity_round_trip_pct": LIVE_RESEARCH_COST_PCT,
            "rule": "Gross, live-research net, and broker mock net must not be mixed.",
        },
        "purpose": "Consolidate existing evidence; do not rerun broad historical mining.",
        "tracks": TRACKS,
        "candidate_count": len(candidates),
        "attention_order": _attention_order(candidates),
        "candidates": candidates,
        "sensitivity_reviews": [risk_high_sensitivity],
        "remaining_candidate_reviews": remaining_reviews,
        "runtime_validation": runtime_validation,
        "short_alpha_discriminator": short_alpha_review,
        "settled_findings": SETTLED_FINDINGS,
        "integrity": {
            "status": "PASS" if not missing_sources else "PASS_WITH_MISSING_SOURCES",
            "missing_or_invalid_sources": missing_sources,
        },
        "sources": sources,
        "behavior_change_authorized": False,
    }
    return canonicalize_board(
        legacy_payload,
        reports_root=reports_root,
        through_day=through_day,
    )


def write_alpha_research_board(
    *, reports_root: Path, through_day: str, output_dir: Path
) -> dict[str, Any]:
    payload = build_alpha_research_board(
        reports_root=reports_root, through_day=through_day
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "alpha_research_board.json"
    markdown_path = output_dir / "alpha_research_board.md"
    sensitivity_json_path = output_dir / "risk_high_30m_sensitivity.json"
    sensitivity_markdown_path = output_dir / "risk_high_30m_sensitivity.md"
    remaining_json_path = output_dir / "remaining_candidate_reviews.json"
    remaining_markdown_path = output_dir / "remaining_candidate_reviews.md"
    runtime_json_path = output_dir / "immediate_opening_runtime_validation.json"
    runtime_markdown_path = output_dir / "immediate_opening_runtime_validation.md"
    short_alpha_json_path = output_dir / "short_alpha_discriminator.json"
    short_alpha_markdown_path = output_dir / "short_alpha_discriminator.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = render_alpha_research_board(payload)
    markdown_path.write_text(markdown, encoding="utf-8")
    latest_dir = output_dir.parent
    latest_json_path = latest_dir / "latest.json"
    latest_markdown_path = latest_dir / "latest.md"
    latest_json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    latest_markdown_path.write_text(markdown, encoding="utf-8")
    sensitivity = mapping((payload.get("sensitivity_reviews") or [{}])[0])
    sensitivity_json_path.write_text(
        json.dumps(sensitivity, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sensitivity_markdown_path.write_text(
        render_risk_high_sensitivity(sensitivity), encoding="utf-8"
    )
    remaining = mapping(payload.get("remaining_candidate_reviews"))
    remaining_json_path.write_text(
        json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    remaining_markdown_path.write_text(
        render_remaining_candidate_reviews(remaining), encoding="utf-8"
    )
    runtime_validation = mapping(payload.get("runtime_validation"))
    runtime_json_path.write_text(
        json.dumps(runtime_validation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    runtime_markdown_path.write_text(
        render_immediate_opening_runtime_validation(runtime_validation), encoding="utf-8"
    )
    short_alpha = mapping(payload.get("short_alpha_discriminator"))
    short_alpha_json_path.write_text(
        json.dumps(short_alpha, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    short_alpha_markdown_path.write_text(
        render_short_alpha_discriminator(short_alpha), encoding="utf-8"
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "latest_json_path": str(latest_json_path),
        "latest_markdown_path": str(latest_markdown_path),
        "sensitivity_json_path": str(sensitivity_json_path),
        "sensitivity_markdown_path": str(sensitivity_markdown_path),
        "remaining_json_path": str(remaining_json_path),
        "remaining_markdown_path": str(remaining_markdown_path),
        "runtime_json_path": str(runtime_json_path),
        "runtime_markdown_path": str(runtime_markdown_path),
        "short_alpha_json_path": str(short_alpha_json_path),
        "short_alpha_markdown_path": str(short_alpha_markdown_path),
        "candidate_count": payload["candidate_count"],
        "integrity_status": mapping(payload.get("integrity")).get("status"),
    }
