from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from libs.runtime.quant.market_regime_observation import classify_market_regime_rail
from libs.runtime.strategist_input_quality import build_risk_off_exception_policy


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, default: str = "-") -> str:
    raw = str(value or "").strip()
    return raw if raw else default


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


_STAGE_META_BY_CALL_KIND: Dict[str, Dict[str, Any]] = {
    "selected_symbol_tactical_refresh": {
        "stage_index": 2,
        "stage_name": "selected_symbol_tactical_refresh",
        "stage_component": "strategist_stage2_selected_symbol",
    },
    "stale_intraday_hold_review": {
        "stage_index": 3,
        "stage_name": "stale_intraday_hold_review",
        "stage_component": "strategist_stage3_hold_review",
    },
    "end_of_day_carry_review": {
        "stage_index": 4,
        "stage_name": "end_of_day_carry_review",
        "stage_component": "strategist_stage4_carry_review",
    },
}


def _infer_call_kind(payload: Dict[str, Any], raw: Dict[str, Any], meta: Dict[str, Any] | None = None) -> str:
    sidecar = _as_dict(meta)
    explicit = _text(
        raw.get("call_kind") or sidecar.get("call_kind") or payload.get("call_kind"),
        "",
    )
    if explicit:
        return explicit
    component = _text(
        raw.get("stage_component") or sidecar.get("stage_component") or raw.get("component") or sidecar.get("component"),
        "",
    )
    if component == "strategist_stage2_selected_symbol":
        return "selected_symbol_tactical_refresh"
    if component == "strategist_stage3_hold_review":
        return "stale_intraday_hold_review"
    if component == "strategist_stage4_carry_review":
        return "end_of_day_carry_review"
    if (
        payload.get("selected_symbol_decision") is not None
        or payload.get("target_symbol") is not None
        or payload.get("runner_up_order") is not None
    ):
        return "selected_symbol_tactical_refresh"
    if payload.get("hold_review_decision") is not None:
        return "stale_intraday_hold_review"
    if payload.get("carry_review_decision") is not None:
        return "end_of_day_carry_review"
    return ""


def _stage_meta(payload: Dict[str, Any], raw: Dict[str, Any], meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    sidecar = _as_dict(meta)
    call_kind = _infer_call_kind(payload, raw, sidecar)
    inferred = dict(_STAGE_META_BY_CALL_KIND.get(call_kind) or {})
    return {
        "call_kind": call_kind,
        "stage_index": raw.get("stage_index") or sidecar.get("stage_index") or inferred.get("stage_index"),
        "stage_name": _first_text(
            "",
            raw.get("stage_name"),
            sidecar.get("stage_name"),
            inferred.get("stage_name"),
            call_kind,
        ),
        "stage_component": _first_text(
            "",
            raw.get("stage_component"),
            sidecar.get("stage_component"),
            inferred.get("stage_component"),
            raw.get("component"),
            sidecar.get("component"),
        ),
    }


def _parse_response_body(raw: Dict[str, Any]) -> Dict[str, Any]:
    parsed = raw.get("parsed_output")
    if isinstance(parsed, dict) and parsed:
        return dict(parsed)

    response_text = raw.get("response_text")
    if isinstance(response_text, str) and response_text.strip():
        try:
            loaded = json.loads(response_text)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}

    attempts = raw.get("attempts")
    if isinstance(attempts, list):
        for row in reversed(attempts):
            if not isinstance(row, dict):
                continue
            parsed = row.get("parsed_output")
            if isinstance(parsed, dict) and parsed:
                return dict(parsed)
            response_text = row.get("raw_response_text")
            if isinstance(response_text, str) and response_text.strip():
                try:
                    loaded = json.loads(response_text)
                except json.JSONDecodeError:
                    continue
                if isinstance(loaded, dict):
                    return dict(loaded)
    return {}


def _canonical_strategist_path_for_response(source_path: Path) -> Path | None:
    if source_path.name != "response.json":
        return None
    artifact_dir = source_path.parent
    run_dir = artifact_dir.parent
    day_dir = run_dir.parent
    llm_dir = day_dir.parent
    if llm_dir.name != "llm":
        category_dir = run_dir.parent
        day_dir = category_dir.parent
        llm_dir = day_dir.parent
        if llm_dir.name != "llm":
            return None
    reports_root = llm_dir.parent
    return reports_root / "canonical" / day_dir.name / run_dir.name / "strategist.json"


def _trade_strategist_input_path_for_response(source_path: Path) -> Path | None:
    if source_path.parent.name != "reports":
        return None
    candidate = source_path.parent.parent / "strategist_input.json"
    return candidate if candidate.exists() else None


def _load_canonical_strategist(source_path: Path) -> Tuple[Path | None, Dict[str, Any]]:
    canonical_path = _canonical_strategist_path_for_response(source_path)
    if canonical_path is not None and canonical_path.exists():
        try:
            raw = json.loads(canonical_path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        if isinstance(raw, dict) and raw:
            return canonical_path, dict(raw)

    input_path = _trade_strategist_input_path_for_response(source_path)
    if input_path is None:
        return canonical_path, {}
    try:
        raw_input = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception:
        return input_path, {}
    if not isinstance(raw_input, dict):
        return input_path, {}
    source_input = _as_dict(raw_input.get("source_input"))
    if not source_input:
        return input_path, {}
    canonical = dict(source_input)
    canonical.setdefault("generated_at", raw_input.get("saved_at"))
    canonical.setdefault("run_id", raw_input.get("run_id"))
    return input_path, canonical


def _headline_count_from_sample_map(value: Any) -> int:
    total = 0
    if not isinstance(value, dict):
        return total
    for row in value.values():
        if not isinstance(row, dict):
            continue
        try:
            total += int(row.get("count") or 0)
        except Exception:
            pass
    return total


def _directive(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    directives = _as_dict(payload.get("strategy_adjustment_directives"))
    return _as_dict(directives.get(key))


def _compact_operator_summary(value: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "available": bool(value.get("available")),
        "status": _text(value.get("status"), ""),
        "artifact_path": _text(value.get("artifact_path"), ""),
        "trade_count": value.get("trade_count"),
        "closed_trade_count": value.get("closed_trade_count"),
        "win_rate": value.get("win_rate"),
        "avg_return_pct": value.get("avg_return_pct"),
    }


def _memory_usage_from_canonical(canonical: Dict[str, Any]) -> Dict[str, Any]:
    trace = _as_dict(canonical.get("memory_usage_trace"))
    visibility = _as_dict(canonical.get("memory_packet_visibility"))
    layer_decisions = _as_dict(trace.get("layer_decisions"))
    compact_layers: Dict[str, Any] = {}
    for layer in ("daily", "weekly", "monthly", "symbol"):
        row = _as_dict(layer_decisions.get(layer))
        if not row:
            continue
        compact_layers[layer] = {
            "status": _text(row.get("status"), ""),
            "active": bool(row.get("active")),
            "used": bool(row.get("used")),
            "confidence": row.get("confidence"),
            "effect": _text(row.get("effect"), ""),
            "reason": _text(row.get("reason"), ""),
            "gate_reason": _text(row.get("gate_reason"), ""),
            "operator_summary": _compact_operator_summary(_as_dict(row.get("operator_summary"))),
        }

    return {
        "available": bool(trace or visibility),
        "active_layers": _as_list(trace.get("active_layers")),
        "priority_order": _as_list(trace.get("priority_order")),
        "human_summary": _text(trace.get("human_summary"), ""),
        "applied_to_strategy": _as_dict(trace.get("applied_to_strategy")),
        "scanner_application": _as_dict(trace.get("scanner_application")),
        "monitor_application": _as_dict(trace.get("monitor_application")),
        "layer_decisions": compact_layers,
        "memory_packet_visibility": {
            "reporter_feedback_packet": _as_dict(visibility.get("reporter_feedback_packet")),
            "selected_symbol_memory": _as_dict(visibility.get("selected_symbol_memory")),
            "commander_refresh_context": _as_dict(visibility.get("commander_refresh_context")),
        },
    }


def _news_usage_from_canonical(canonical: Dict[str, Any]) -> Dict[str, Any]:
    trace = _as_dict(canonical.get("news_usage_trace"))
    context = _as_dict(canonical.get("news_context"))
    query_targets = _as_list(trace.get("query_targets")) or _as_list(canonical.get("news_query_targets"))
    market_headlines = _as_list(trace.get("market_headlines_used"))
    candidate_headlines = _as_list(trace.get("candidate_headlines_used"))
    market_count = len(market_headlines)
    candidate_count = len(candidate_headlines)
    if market_count <= 0:
        market_count = int(context.get("market_headline_count") or 0) or _headline_count_from_sample_map(canonical.get("market_news_sample"))
    if candidate_count <= 0:
        candidate_count = int(context.get("candidate_headline_count") or 0) or _headline_count_from_sample_map(canonical.get("candidate_news_sample"))
    headline_count = int(context.get("headline_count") or 0)
    if headline_count and market_count <= 0 and candidate_count <= 0:
        market_count = int(context.get("market_signal_total") or 0)
        candidate_count = max(0, headline_count - market_count)
    return {
        "available": bool(trace or context or canonical.get("news_evidence_summary") or query_targets),
        "query_targets": query_targets,
        "human_summary": _text(trace.get("human_summary") or context.get("summary"), ""),
        "market_effect": _text(trace.get("market_effect"), ""),
        "playbook_effect": _text(trace.get("playbook_effect"), ""),
        "scanner_guidance_effect": _text(trace.get("scanner_guidance_effect"), ""),
        "monitor_policy_effect": _text(trace.get("monitor_policy_effect"), ""),
        "confidence": _text(trace.get("confidence") or ("medium" if context else ""), ""),
        "news_evidence_summary": _text(canonical.get("news_evidence_summary"), ""),
        "news_query_reasoning": _text(canonical.get("news_query_reasoning"), ""),
        "market_headline_count": market_count,
        "candidate_headline_count": candidate_count,
        "market_headlines_sample": market_headlines[:3],
        "candidate_headlines_sample": candidate_headlines[:3],
    }


def _market_rail_from_canonical(canonical: Dict[str, Any]) -> Dict[str, Any]:
    global_signal = _as_dict(canonical.get("global_sentiment_signal"))
    if not global_signal:
        global_signal = _as_dict(_as_dict(canonical.get("market_context")).get("global_signal"))
    packet = {
        "generated_at": _text(canonical.get("generated_at") or canonical.get("saved_at"), ""),
        "global_sentiment": {
            "score": global_signal.get("score"),
            "status": global_signal.get("status"),
            "source": global_signal.get("source"),
        },
        "index_moves": _as_dict(global_signal.get("index_moves")),
        "korea_indices": _as_dict(global_signal.get("korea_indices")),
        "macro_moves": _as_dict(global_signal.get("macro_moves")),
    }
    return classify_market_regime_rail(packet)


def _news_quality_audit(canonical: Dict[str, Any], news_usage: Dict[str, Any]) -> Dict[str, Any]:
    ranked = _as_dict(canonical.get("news_evidence_ranked"))
    candidate_ranked = _as_list(ranked.get("candidate_news_ranked"))
    market_ranked = _as_list(ranked.get("market_news_ranked"))
    query_targets = _as_list(news_usage.get("query_targets"))
    market_count = int(news_usage.get("market_headline_count") or len(market_ranked) or 0)
    candidate_count = int(news_usage.get("candidate_headline_count") or len(candidate_ranked) or 0)
    total = market_count + candidate_count
    confidence = _text(news_usage.get("confidence"), "")
    summary = _text(news_usage.get("human_summary") or news_usage.get("news_evidence_summary"), "")
    no_effect = not any(
        _text(news_usage.get(key), "")
        for key in ("market_effect", "playbook_effect", "scanner_guidance_effect", "monitor_policy_effect")
    )
    issues: List[str] = []
    if total <= 0:
        issues.append("news_headlines_missing")
    if not query_targets:
        issues.append("news_query_targets_missing")
    if no_effect:
        issues.append("news_effect_trace_missing")
    if confidence.lower() in {"", "-", "low", "none", "unknown"}:
        issues.append("news_confidence_low_or_missing")
    if not summary:
        issues.append("news_summary_missing")
    if total > 0 and candidate_count <= 0:
        issues.append("candidate_news_missing")
    if total > 0 and market_count <= 0:
        issues.append("market_news_missing")
    if not issues:
        status = "ok"
    elif total > 0:
        status = "partial"
    else:
        status = "weak"
    return {
        "schema_version": "strategist_news_quality_audit.v1",
        "status": status,
        "headline_count": total,
        "market_headline_count": market_count,
        "candidate_headline_count": candidate_count,
        "query_target_count": len(query_targets),
        "query_targets": query_targets[:10],
        "confidence": confidence,
        "issues": issues,
        "market_effect": _text(news_usage.get("market_effect"), ""),
        "playbook_effect": _text(news_usage.get("playbook_effect"), ""),
        "scanner_guidance_effect": _text(news_usage.get("scanner_guidance_effect"), ""),
        "monitor_policy_effect": _text(news_usage.get("monitor_policy_effect"), ""),
    }


def _strategist_output_quality_audit(
    *,
    payload: Dict[str, Any],
    canonical: Dict[str, Any],
    stage_decision: Dict[str, Any],
    strategy_detail: Dict[str, Any],
    market_rail: Dict[str, Any],
    news_quality: Dict[str, Any],
) -> Dict[str, Any]:
    candidate_watch = _as_dict(strategy_detail.get("candidate_watch_policy"))
    memory_usage = _memory_usage_from_canonical(canonical)
    is_stage_specific = bool(stage_decision.get("is_stage_specific"))
    decision = _text(stage_decision.get("decision") or payload.get("decision"), "")
    confidence = stage_decision.get("confidence")
    if confidence in (None, ""):
        confidence = payload.get("confidence")
    issues: List[str] = []
    if not decision:
        issues.append("decision_missing")
    if confidence in (None, ""):
        issues.append("confidence_missing")
    if is_stage_specific:
        if not _as_dict(stage_decision.get("monitor_instruction")) and not _as_dict(stage_decision.get("entry_policy_delta")):
            issues.append("stage_control_fields_missing")
    else:
        if not _text(strategy_detail.get("final_playbook"), ""):
            issues.append("final_playbook_missing")
        if not _text(strategy_detail.get("tactical_strategy"), ""):
            issues.append("tactical_strategy_missing")
        if not candidate_watch:
            issues.append("candidate_watch_policy_missing")
    if _text(market_rail.get("market_regime_rail"), "") in {"", "macro_packet_unavailable"}:
        issues.append("market_regime_rail_missing")
    if news_quality.get("status") != "ok":
        issues.append("news_quality_not_ok")
    if not bool(memory_usage.get("available")):
        issues.append("memory_trace_missing_or_disabled")
    elif not _as_list(memory_usage.get("active_layers")):
        issues.append("memory_active_layers_empty")
    if not issues:
        status = "ok"
    elif len(issues) <= 2:
        status = "watch"
    else:
        status = "needs_review"
    return {
        "schema_version": "strategist_output_quality_audit.v1",
        "status": status,
        "issues": issues,
        "decision": decision,
        "confidence": confidence,
        "final_playbook": _text(strategy_detail.get("final_playbook"), ""),
        "tactical_strategy": _text(strategy_detail.get("tactical_strategy"), ""),
        "market_regime": _text(market_rail.get("market_regime"), ""),
        "market_regime_rail": _text(market_rail.get("market_regime_rail"), ""),
        "candidate_watch_policy_present": bool(candidate_watch),
        "memory_available": bool(memory_usage.get("available")),
        "memory_active_layers": _as_list(memory_usage.get("active_layers")),
        "news_quality_status": _text(news_quality.get("status"), ""),
    }


def _stage_decision_from_payload(
    payload: Dict[str, Any],
    raw: Dict[str, Any],
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    stage_meta = _stage_meta(payload, raw, meta)
    call_kind = _text(stage_meta.get("call_kind"), "")
    stage_name = _text(stage_meta.get("stage_name") or payload.get("stage_name"), "")
    try:
        stage_index = int(stage_meta.get("stage_index") or payload.get("stage_index") or 0)
    except (TypeError, ValueError):
        stage_index = 0
    is_market_frame = stage_index in (0, 1) and call_kind in {"", "market_strategy_frame", "theme_selection", "strategic_frame"}
    if is_market_frame:
        return {"is_stage_specific": False}

    selected_symbol_review = _as_dict(payload.get("selected_symbol_tactical_review"))
    candidate_watch = _as_dict(payload.get("candidate_watch_policy"))
    refresh_trace = _as_dict(payload.get("strategy_refresh_trace"))
    decision = _first_text(
        "",
        selected_symbol_review.get("selected_symbol_decision"),
        payload.get("hold_review_decision"),
        payload.get("carry_review_decision"),
        payload.get("tactical_refresh_decision"),
        payload.get("selected_symbol_decision"),
        payload.get("decision"),
    )
    monitor_adjustment = _first_dict(payload.get("monitor_adjustment"), selected_symbol_review.get("monitor_adjustment"))
    priority_exit_triggers = _as_list(payload.get("priority_exit_triggers"))
    runner_up_order = _as_list(payload.get("runner_up_order")) or _as_list(selected_symbol_review.get("runner_up_order"))
    commander_actionability = _first_dict(
        payload.get("commander_actionability"),
        selected_symbol_review.get("commander_actionability"),
    )
    if not commander_actionability:
        actionability_text = _first_text("", payload.get("commander_actionability"), selected_symbol_review.get("commander_actionability"))
        commander_actionability = {"value": actionability_text} if actionability_text else {}
    return {
        "is_stage_specific": True,
        "stage_index": stage_index,
        "stage_name": stage_name,
        "call_kind": call_kind,
        "stage_component": _text(stage_meta.get("stage_component"), ""),
        "decision": decision,
        "target_symbol": _first_text("", selected_symbol_review.get("target_symbol"), payload.get("target_symbol")),
        "target_rank": selected_symbol_review.get("target_rank") or payload.get("target_rank"),
        "runner_up_order": runner_up_order,
        "monitor_instruction": _first_dict(payload.get("monitor_instruction"), selected_symbol_review.get("monitor_instruction")),
        "entry_policy_delta": _first_dict(payload.get("entry_policy_delta"), selected_symbol_review.get("entry_policy_delta")),
        "commander_actionability": commander_actionability,
        "confidence": selected_symbol_review.get("confidence") if selected_symbol_review.get("confidence") is not None else payload.get("confidence"),
        "exit_pressure": _text(payload.get("exit_pressure"), ""),
        "thesis_status": _text(payload.get("thesis_status"), ""),
        "next_check_minutes": payload.get("next_check_minutes"),
        "priority_exit_triggers": priority_exit_triggers,
        "monitor_adjustment": monitor_adjustment,
        "reason": _first_text("", payload.get("reason"), selected_symbol_review.get("reason"), candidate_watch.get("reason"), refresh_trace.get("summary")),
        "raw_payload_keys": sorted(str(key) for key in payload.keys()),
    }


def _operator_readout(payload: Dict[str, Any], stage_decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    stage_decision = _as_dict(stage_decision)
    if bool(stage_decision.get("is_stage_specific")):
        stage_name = _text(stage_decision.get("stage_name"), "stage_specific")
        decision = _text(stage_decision.get("decision"), "-")
        reason = _text(stage_decision.get("reason"), "")
        return {
            "headline": f"{stage_name} / decision={decision}",
            "good_points": [
                "Stage-specific strategist response was parsed.",
                "Market-frame fields such as selected_themes are not required for this stage.",
            ],
            "issues": [] if reason else ["stage-specific reason is empty"],
            "root_cause": reason or "stage-specific response did not include a reason",
            "recommended_actions": ["Review the stage decision fields instead of the market-frame section."],
            "validation_questions": ["Confirm monitor/executor behavior followed the stage decision."],
        }

    theme_strategy = _as_dict(payload.get("theme_strategy"))
    rationale = _text(payload.get("rationale"), "")
    selected_themes = _as_list(payload.get("selected_themes"))
    fallback_reason = _text(theme_strategy.get("fallback_reason"), "")
    selected_symbol_bias = _directive(payload, "selected_symbol_bias_action")

    good_points: List[str] = []
    issues: List[str] = []
    actions: List[str] = []
    validation: List[str] = []

    entry_policy = _directive(payload, "entry_policy_action")
    monitor_focus = _directive(payload, "monitor_focus_action")
    refresh_action = _directive(payload, "refresh_action")

    if entry_policy:
        good_points.append("최근 손실/과매매 피드백을 진입 정책 조정 근거로 명시했습니다.")
    if monitor_focus:
        good_points.append("모니터가 집중해야 할 축을 volume/reclaim처럼 실행 가능한 형태로 남겼습니다.")
    if refresh_action:
        good_points.append("전략 refresh가 요청된 이유와 최종 적용 단계를 분리해 남겼습니다.")

    if not selected_themes:
        issues.append("selected_themes가 비어 있어 테마 기반 전략 분기가 실제로 작동하지 않았습니다.")
        actions.append("다음 실행에서 Commander가 available_themes/theme_strength_packet을 전략가 호출 전에 채우는지 확인합니다.")
        validation.append("다음 전략가 요약에서 selected_themes가 실제 테마명으로 채워지는가?")
    if "best 및 worst" in rationale or "best and worst" in rationale.lower():
        issues.append("전략 메모리에서 같은 플레이북이 best/worst에 동시에 잡혀 방향성 신호가 약합니다.")
        actions.append("best/worst 중복 플레이북은 방향성 bias가 아니라 memory_quality_flag로만 표시합니다.")
    if str(selected_symbol_bias.get("action") or "").strip().lower() == "none":
        issues.append("심볼 메모리 근거가 없어 특정 종목 편향 조정은 적용되지 않았습니다.")
        validation.append("심볼 summary/memory가 누적된 뒤 selected_symbol_bias_action이 계속 none인지 확인합니다.")

    if not good_points:
        good_points.append("전략가 출력은 파싱 가능하며 playbook, entry policy, refresh trace를 포함합니다.")
    if not issues:
        issues.append("즉시 확인할 구조적 문제는 요약에서 감지되지 않았습니다.")
    if not actions:
        actions.append("다음 실행 결과와 비교해 같은 playbook 반복 여부를 확인합니다.")
    if not validation:
        validation.append("다음 실행에서 playbook/theme/entry policy가 시장 입력에 따라 달라지는가?")

    headline_parts = [_text(payload.get("playbook"), "unknown")]
    if selected_themes:
        headline_parts.append(f"themes={', '.join(str(x) for x in selected_themes[:3])}")
    else:
        headline_parts.append("theme=none")
    if theme_strategy.get("selection_mode"):
        headline_parts.append(f"mode={theme_strategy.get('selection_mode')}")

    root_cause = fallback_reason or rationale or "전략가 출력의 rationale 확인 필요"
    return {
        "headline": " / ".join(headline_parts),
        "good_points": good_points[:4],
        "issues": issues[:4],
        "root_cause": root_cause,
        "recommended_actions": actions[:4],
        "validation_questions": validation[:4],
    }


def _first_text(default: str, *values: Any) -> str:
    for value in values:
        text = _text(value, "")
        if text:
            return text
    return default


def _operator_readout_clean(payload: Dict[str, Any], stage_decision: Dict[str, Any] | None = None) -> Dict[str, Any]:
    stage_decision = _as_dict(stage_decision)
    if bool(stage_decision.get("is_stage_specific")):
        stage_name = _text(stage_decision.get("stage_name"), "stage_specific")
        decision = _text(stage_decision.get("decision"), "-")
        reason = _text(stage_decision.get("reason"), "")
        return {
            "headline": f"{stage_name} / decision={decision}",
            "good_points": [
                "단계별 전략가 응답이 파싱됐습니다.",
                "이 단계는 시장 프레임이 아니므로 selected_themes 같은 1차 필드는 필수가 아닙니다.",
            ],
            "issues": [] if reason else ["단계별 응답의 reason이 비어 있습니다."],
            "root_cause": reason or "단계별 응답에 reason이 포함되지 않았습니다.",
            "recommended_actions": ["시장 프레임 섹션이 아니라 단계별 decision 필드를 확인합니다."],
            "validation_questions": ["모니터/집행 흐름이 이 단계별 decision을 따랐는지 확인합니다."],
        }

    theme_strategy = _as_dict(payload.get("theme_strategy"))
    rationale = _text(payload.get("rationale"), "")
    selected_themes = _as_list(payload.get("selected_themes"))
    fallback_reason = _text(theme_strategy.get("fallback_reason"), "")
    selected_symbol_bias = _directive(payload, "selected_symbol_bias_action")
    entry_policy = _directive(payload, "entry_policy_action")
    monitor_focus = _directive(payload, "monitor_focus_action")
    refresh_action = _directive(payload, "refresh_action")

    good_points: List[str] = []
    issues: List[str] = []
    actions: List[str] = []
    validation: List[str] = []

    if entry_policy:
        good_points.append("최근 손실/과매매 피드백을 진입 정책 조정 근거로 명시했습니다.")
    if monitor_focus:
        good_points.append("모니터가 집중할 축을 volume/reclaim처럼 실행 가능한 형태로 넘겼습니다.")
    if refresh_action:
        good_points.append("전략 refresh 요청 사유와 최종 적용 단계를 분리해 남겼습니다.")
    if not selected_themes:
        issues.append("selected_themes가 비어 있어 테마 기반 전략 분기가 약합니다.")
        actions.append("다음 실행에서 Commander가 available_themes/theme_strength_packet을 전략가 호출 전에 채우는지 확인합니다.")
        validation.append("다음 전략가 요약에서 selected_themes가 실제 테마명으로 채워지는지 확인합니다.")
    if ("best" in rationale.lower() and "worst" in rationale.lower()) or "best 諛?worst" in rationale:
        issues.append("전략 메모리에서 같은 플레이북이 best/worst에 동시에 잡혀 방향 신호가 혼합됩니다.")
        actions.append("best/worst 중복 플레이북은 방향성 bias가 아니라 memory_quality_flag로만 표시합니다.")
    if str(selected_symbol_bias.get("action") or "").strip().lower() == "none":
        issues.append("성과 메모리 근거가 없어 특정 종목 영향 조정은 적용되지 않았습니다.")
        validation.append("성과 summary/memory가 누적돼도 selected_symbol_bias_action이 계속 none인지 확인합니다.")

    if not good_points:
        good_points.append("전략가 출력은 파싱 가능하며 playbook, entry policy, refresh trace를 포함합니다.")
    if not issues:
        issues.append("즉시 확인할 구조적 문제는 요약에서 감지되지 않았습니다.")
    if not actions:
        actions.append("다음 실행 결과를 비교해 같은 playbook 반복 여부를 확인합니다.")
    if not validation:
        validation.append("다음 실행에서 playbook/theme/entry policy가 시장 입력에 따라 달라지는지 확인합니다.")

    headline_parts = [_text(payload.get("playbook"), "unknown")]
    if selected_themes:
        headline_parts.append(f"themes={', '.join(str(x) for x in selected_themes[:3])}")
    else:
        headline_parts.append("theme=none")
    if theme_strategy.get("selection_mode"):
        headline_parts.append(f"mode={theme_strategy.get('selection_mode')}")

    return {
        "headline": " / ".join(headline_parts),
        "good_points": good_points[:4],
        "issues": issues[:4],
        "root_cause": fallback_reason or rationale or "전략가 출력의 rationale 확인 필요",
        "recommended_actions": actions[:4],
        "validation_questions": validation[:4],
    }


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        row = _as_dict(value)
        if row:
            return row
    return {}


def _strategy_detail_from_sources(payload: Dict[str, Any], canonical: Dict[str, Any]) -> Dict[str, Any]:
    canonical_detail = _as_dict(canonical.get("strategy_detail"))
    strategy_policy = _as_dict(canonical.get("strategy_policy"))
    market_policy = _as_dict(strategy_policy.get("market_policy"))
    scanner_policy = _as_dict(strategy_policy.get("scanner_policy"))
    return {
        "pre_llm_playbook": _first_text(
            "",
            canonical_detail.get("pre_llm_playbook"),
            canonical.get("pre_llm_playbook"),
            market_policy.get("pre_llm_playbook"),
            payload.get("pre_llm_playbook"),
        ),
        "llm_requested_playbook": _first_text(
            "",
            canonical_detail.get("llm_requested_playbook"),
            canonical.get("llm_requested_playbook"),
            market_policy.get("llm_requested_playbook"),
            payload.get("llm_requested_playbook"),
        ),
        "requested_playbook": _first_text(
            "",
            canonical_detail.get("requested_playbook"),
            canonical.get("requested_playbook"),
            market_policy.get("requested_playbook"),
            payload.get("requested_playbook"),
        ),
        "requested_playbook_source": _first_text(
            "",
            canonical_detail.get("requested_playbook_source"),
            canonical.get("requested_playbook_source"),
            market_policy.get("requested_playbook_source"),
            payload.get("requested_playbook_source"),
        ),
        "final_playbook": _first_text(
            "",
            canonical_detail.get("final_playbook"),
            canonical.get("final_playbook"),
            market_policy.get("final_playbook"),
            canonical.get("playbook"),
            payload.get("final_playbook"),
            payload.get("playbook"),
        ),
        "tactical_strategy": _first_text(
            "",
            canonical_detail.get("tactical_strategy"),
            canonical.get("tactical_strategy"),
            market_policy.get("tactical_strategy"),
            payload.get("tactical_strategy"),
        ),
        "tactical_subtype": _first_text(
            "",
            canonical_detail.get("tactical_subtype"),
            canonical.get("tactical_subtype"),
            market_policy.get("tactical_subtype"),
            payload.get("tactical_subtype"),
        ),
        "strategy_scores": _first_dict(
            canonical_detail.get("strategy_scores"),
            canonical.get("strategy_scores"),
            market_policy.get("strategy_scores"),
            payload.get("strategy_scores"),
        ),
        "rejected_strategy_reasons": _first_dict(
            canonical_detail.get("rejected_strategy_reasons"),
            canonical.get("rejected_strategy_reasons"),
            market_policy.get("rejected_strategy_reasons"),
            payload.get("rejected_strategy_reasons"),
        ),
        "candidate_watch_policy": _first_dict(
            canonical_detail.get("candidate_watch_policy"),
            canonical.get("candidate_watch_policy"),
            scanner_policy.get("candidate_watch_policy"),
            payload.get("candidate_watch_policy"),
        ),
    }


def _json_inline(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def _watch_scope_label(value: Dict[str, Any]) -> str:
    if not value:
        return ""
    rank = value.get("max_priority_rank")
    runner_ups = value.get("max_runner_ups")
    parts: List[str] = []
    if rank not in (None, ""):
        parts.append(f"{rank}위까지")
    if runner_ups not in (None, ""):
        parts.append(f"차순위 {runner_ups}개")
    if value.get("cascade_enabled") not in (None, ""):
        parts.append(f"cascade {'활성' if bool(value.get('cascade_enabled')) else '비활성'}")
    return " / ".join(parts)


def _strategy_patch_status(detail: Dict[str, Any]) -> str:
    required_keys = (
        "pre_llm_playbook",
        "llm_requested_playbook",
        "requested_playbook",
        "requested_playbook_source",
        "final_playbook",
        "tactical_strategy",
        "strategy_scores",
        "rejected_strategy_reasons",
        "candidate_watch_policy",
    )
    missing = [key for key in required_keys if not detail.get(key)]
    if not missing:
        return "적용됨"
    return f"일부 누락 ({', '.join(missing)})"


def _playbook_flow_label(detail: Dict[str, Any]) -> str:
    pre = _text(detail.get("pre_llm_playbook"), "")
    requested = _text(detail.get("requested_playbook"), "")
    final = _text(detail.get("final_playbook"), "")
    parts = [part for part in (pre, requested, final) if part]
    if not parts:
        return "-"
    flow = " -> ".join(parts)
    source = _text(detail.get("requested_playbook_source"), "")
    return f"{flow} (source={source})" if source else flow


def _score_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _score_label(value: Any) -> str:
    numeric = _score_value(value)
    if numeric != float("-inf"):
        return f"{numeric:.2f}".rstrip("0").rstrip(".")
    return _text(value)


def _strategy_score_lines(scores: Dict[str, Any], *, selected: str) -> List[str]:
    if not scores:
        return ["- -"]
    rows = sorted(scores.items(), key=lambda row: (_score_value(row[1]), str(row[0])), reverse=True)
    lines: List[str] = []
    for name, score in rows:
        marker = " (선택)" if str(name) == selected else ""
        lines.append(f"- {name}: {_score_label(score)}{marker}")
    return lines


def _watch_scope_label_clean(value: Dict[str, Any]) -> str:
    if not value:
        return ""
    rank = value.get("max_priority_rank")
    runner_ups = value.get("max_runner_ups")
    parts: List[str] = []
    if rank not in (None, ""):
        parts.append(f"{rank}위까지")
    if runner_ups not in (None, ""):
        parts.append(f"차순위 {runner_ups}개")
    if value.get("cascade_enabled") not in (None, ""):
        parts.append(f"cascade {'활성' if bool(value.get('cascade_enabled')) else '비활성'}")
    return " / ".join(parts)


def _strategy_patch_status_clean(detail: Dict[str, Any]) -> str:
    required_keys = (
        "pre_llm_playbook",
        "llm_requested_playbook",
        "requested_playbook",
        "requested_playbook_source",
        "final_playbook",
        "tactical_strategy",
        "strategy_scores",
        "rejected_strategy_reasons",
        "candidate_watch_policy",
    )
    missing = [key for key in required_keys if not detail.get(key)]
    if not missing:
        return "적용됨"
    return f"일부 누락 ({', '.join(missing)})"


def _strategy_score_lines_clean(scores: Dict[str, Any], *, selected: str) -> List[str]:
    if not scores:
        return ["- -"]
    rows = sorted(scores.items(), key=lambda row: (_score_value(row[1]), str(row[0])), reverse=True)
    lines: List[str] = []
    for name, score in rows:
        marker = " (선택)" if str(name) == selected else ""
        lines.append(f"- {name}: {_score_label(score)}{marker}")
    return lines


def _rejected_strategy_lines(reasons: Dict[str, Any], *, selected: str) -> List[str]:
    if not reasons:
        return ["- -"]
    lines: List[str] = []
    for name in sorted(reasons):
        if str(name) == selected:
            continue
        reason = reasons.get(name)
        if isinstance(reason, (dict, list)):
            reason_text = _json_inline(reason)
        else:
            reason_text = _text(reason)
        lines.append(f"- {name}: {reason_text}")
    return lines if lines else ["- -"]


def build_strategist_llm_summary_payload(response_json_path: Path) -> Dict[str, Any]:
    source_path = Path(response_json_path)
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    sidecar_meta = _read_json(source_path.with_name("meta.json"))
    payload = _parse_response_body(raw)
    canonical_path, canonical = _load_canonical_strategist(source_path)
    theme_strategy = _as_dict(payload.get("theme_strategy"))
    refresh_trace = _as_dict(payload.get("strategy_refresh_trace"))
    horizon = _as_dict(payload.get("strategy_horizon_feedback"))
    strategy_detail = _strategy_detail_from_sources(payload, canonical)
    stage_decision = _stage_decision_from_payload(payload, raw, sidecar_meta)
    stage_meta = _stage_meta(payload, raw, sidecar_meta)
    news_usage = _news_usage_from_canonical(canonical)
    market_regime_rail = _market_rail_from_canonical(canonical)
    news_quality = _news_quality_audit(canonical, news_usage)
    risk_off_exception_policy = _as_dict(canonical.get("risk_off_exception_policy")) or build_risk_off_exception_policy(
        market_regime_rail=market_regime_rail,
        news_quality=news_quality,
    )
    output_quality = _strategist_output_quality_audit(
        payload=payload,
        canonical=canonical,
        stage_decision=stage_decision,
        strategy_detail=strategy_detail,
        market_rail=market_regime_rail,
        news_quality=news_quality,
    )

    return {
        "schema_version": "strategist_llm_summary.v1",
        "artifact_type": "strategist_llm_summary",
        "source_response_json": str(source_path),
        "source_canonical_strategist_json": str(canonical_path) if canonical_path else "",
        "generated_at": _utc_now_iso(),
        "llm_meta": {
            "stage": _first_text("", raw.get("stage"), sidecar_meta.get("stage")),
            "stage_index": stage_meta.get("stage_index"),
            "stage_name": _text(stage_meta.get("stage_name"), ""),
            "call_kind": _text(stage_meta.get("call_kind"), ""),
            "stage_component": _text(stage_meta.get("stage_component"), ""),
            "provider": _first_text("", raw.get("provider"), sidecar_meta.get("provider")),
            "model": _first_text("", raw.get("model"), sidecar_meta.get("model")),
            "status": _first_text("", raw.get("status"), raw.get("llm_status"), sidecar_meta.get("status"), sidecar_meta.get("llm_status")),
            "reason": _first_text("", raw.get("reason"), sidecar_meta.get("reason")),
            "run_id": _first_text("", raw.get("run_id"), sidecar_meta.get("run_id")),
            "day": _first_text("", raw.get("day"), sidecar_meta.get("day")),
            "saved_at": _first_text("", raw.get("saved_at"), sidecar_meta.get("saved_at")),
            "repair_used": bool(raw.get("repair_used") or sidecar_meta.get("repair_used")),
            "profile_name": _first_text("", raw.get("llm_execution_profile_name"), sidecar_meta.get("llm_execution_profile_name")),
            "profile_source": _first_text("", raw.get("llm_execution_profile_source"), sidecar_meta.get("llm_execution_profile_source")),
        },
        "operator_readout": _operator_readout_clean(payload, stage_decision),
        "stage_decision": stage_decision,
        "strategy_frame": {
            "playbook": _text(payload.get("playbook")),
            "selected_themes": _as_list(payload.get("selected_themes")),
            "theme_selection_mode": _text(theme_strategy.get("selection_mode")),
            "fallback_reason": _text(theme_strategy.get("fallback_reason"), ""),
            "rationale": _text(payload.get("rationale"), ""),
        },
        "strategy_detail": strategy_detail,
        "policy_changes": {
            "playbook_action": _directive(payload, "playbook_action"),
            "entry_policy_action": _directive(payload, "entry_policy_action"),
            "monitor_focus_action": _directive(payload, "monitor_focus_action"),
            "selected_symbol_bias_action": _directive(payload, "selected_symbol_bias_action"),
            "refresh_action": _directive(payload, "refresh_action"),
        },
        "monitor_entry_policy": _as_dict(payload.get("monitor_entry_policy")),
        "memory_usage": _memory_usage_from_canonical(canonical),
        "news_usage": news_usage,
        "news_event_intelligence": _as_dict(
            payload.get("news_event_intelligence") or canonical.get("news_event_intelligence")
        ),
        "news_event_intelligence_usage": _as_dict(payload.get("news_event_intelligence_usage")),
        "market_regime_rail": market_regime_rail,
        "news_quality_audit": news_quality,
        "risk_off_exception_policy": risk_off_exception_policy,
        "risk_off_exception_conditions": _as_list(payload.get("risk_off_exception_conditions")),
        "strategist_output_quality_audit": output_quality,
        "strategy_refresh_trace": {
            "summary": _text(refresh_trace.get("summary"), ""),
            "bullets": _as_list(refresh_trace.get("bullets")),
            "stages": _as_list(refresh_trace.get("stages")),
        },
        "strategy_horizon_feedback": horizon,
    }


def _bullet_lines(items: List[Any], *, empty: str = "-") -> List[str]:
    rows = [f"- {item}" for item in items if str(item or "").strip()]
    return rows if rows else [f"- {empty}"]


def _directive_line(label: str, value: Dict[str, Any]) -> str:
    if not value:
        return f"- {label}: -"
    action = _text(value.get("action"))
    target = value.get("target")
    if target is None:
        target = value.get("target_fields") or value.get("target_axes")
    reason = _text(value.get("reason"), "")
    target_text = ", ".join(str(x) for x in target) if isinstance(target, list) else _text(target, "")
    if target_text and reason:
        return f"- {label}: **{action}** -> {target_text}; {reason}"
    if target_text:
        return f"- {label}: **{action}** -> {target_text}"
    if reason:
        return f"- {label}: **{action}**; {reason}"
    return f"- {label}: **{action}**"


def _memory_usage_lines(memory: Dict[str, Any]) -> List[str]:
    if not bool(memory.get("available")):
        return ["- 메모리 사용 trace: -"]
    lines = [
        f"- 활성 레이어: {', '.join(str(x) for x in _as_list(memory.get('active_layers'))) or '-'}",
        f"- 우선순위: {' -> '.join(str(x) for x in _as_list(memory.get('priority_order'))) or '-'}",
        f"- 요약: {_text(memory.get('human_summary'))}",
    ]
    applied = _as_dict(memory.get("applied_to_strategy"))
    if applied:
        lines.append(f"- 전략 반영: playbook={_text(applied.get('playbook_effect'))}, risk={_text(applied.get('risk_posture_effect'))}")
        lines.append(
            f"- scanner/monitor 반영: scanner={_text(applied.get('scanner_guidance_effect'))}, "
            f"monitor={_text(applied.get('monitor_policy_effect'))}"
        )
    layer_decisions = _as_dict(memory.get("layer_decisions"))
    for layer in ("daily", "weekly", "monthly", "symbol"):
        row = _as_dict(layer_decisions.get(layer))
        if not row:
            continue
        summary = _as_dict(row.get("operator_summary"))
        metrics = []
        if summary.get("trade_count") is not None:
            metrics.append(f"trades={summary.get('trade_count')}")
        if summary.get("win_rate") is not None:
            metrics.append(f"win_rate={summary.get('win_rate')}")
        if summary.get("avg_return_pct") is not None:
            metrics.append(f"avg_return_pct={summary.get('avg_return_pct')}")
        metric_text = f" ({', '.join(metrics)})" if metrics else ""
        lines.append(
            f"- {layer}: used={row.get('used')} status={_text(row.get('status'), '')} "
            f"effect={_text(row.get('effect'), '')}{metric_text}"
        )
    return lines


def _news_usage_lines(news: Dict[str, Any]) -> List[str]:
    if not bool(news.get("available")):
        return ["- 뉴스 사용 trace: -"]
    query_targets = ", ".join(str(x) for x in _as_list(news.get("query_targets"))[:10]) or "-"
    return [
        f"- 검색/수집 타깃: {query_targets}",
        f"- 사용 요약: {_text(news.get('human_summary'))}",
        f"- 시장 효과: {_text(news.get('market_effect'))}",
        f"- 플레이북 효과: {_text(news.get('playbook_effect'))}",
        f"- 스캐너 반영: {_text(news.get('scanner_guidance_effect'))}",
        f"- 모니터 반영: {_text(news.get('monitor_policy_effect'))}",
        f"- 근거 헤드라인 수: market={news.get('market_headline_count')}, candidate={news.get('candidate_headline_count')}",
        f"- query reasoning: {_text(news.get('news_query_reasoning'))}",
    ]


def render_strategist_llm_summary_markdown(payload: Dict[str, Any]) -> str:
    meta = _as_dict(payload.get("llm_meta"))
    readout = _as_dict(payload.get("operator_readout"))
    stage_decision = _as_dict(payload.get("stage_decision"))
    if bool(stage_decision.get("is_stage_specific")):
        return _render_stage_specific_summary_markdown(payload)

    frame = _as_dict(payload.get("strategy_frame"))
    detail = _as_dict(payload.get("strategy_detail"))
    changes = _as_dict(payload.get("policy_changes"))
    entry = _as_dict(payload.get("monitor_entry_policy"))
    memory = _as_dict(payload.get("memory_usage"))
    news = _as_dict(payload.get("news_usage"))
    refresh = _as_dict(payload.get("strategy_refresh_trace"))
    horizon = _as_dict(payload.get("strategy_horizon_feedback"))
    hold = _as_dict(horizon.get("expected_hold_window"))
    exit_guidance = _as_dict(horizon.get("exit_guidance"))
    handoff = _as_dict(horizon.get("monitor_handoff"))

    selected_themes = _as_list(frame.get("selected_themes"))
    theme_text = ", ".join(str(x) for x in selected_themes) if selected_themes else "-"
    watch = _as_dict(detail.get("candidate_watch_policy"))
    watch_scope = _watch_scope_label(watch)
    tactical_strategy = _text(detail.get("tactical_strategy"), "")
    strategy_scores = _as_dict(detail.get("strategy_scores"))
    rejected_reasons = _as_dict(detail.get("rejected_strategy_reasons"))

    lines: List[str] = [
        f"# Strategist LLM Summary ({_text(meta.get('day'), '-')})",
        "",
        "---",
        "",
        "## 전략가 원문 해석 출력",
        "",
        "> 아래 내용은 전략가 LLM 응답의 구조화 필드를 재배치한 것입니다. 리포터가 새로 해석한 문장이 아니라 `response.json`에 저장된 전략가 출력입니다.",
        "",
        f"- 상태: {_text(meta.get('status'))} / model={_text(meta.get('model'))}",
        "",
        "### 전략 프레임",
        "",
        f"- 플레이북: **{_text(frame.get('playbook'))}**",
        f"- 선택 테마: {theme_text}",
        f"- 테마 선택 모드: {_text(frame.get('theme_selection_mode'))}",
        f"- fallback 사유: {_text(frame.get('fallback_reason'))}",
        "",
        "**전략가 rationale**",
        "",
        _text(frame.get("rationale")),
        "",
        "### 전략 디테일",
        "",
        f"- 전략 강화 필드: {_strategy_patch_status(detail)}",
        f"- 플레이북 흐름: {_playbook_flow_label(detail)}",
        f"- LLM 요청 플레이북: {_text(detail.get('llm_requested_playbook'))}",
        f"- 최종 플레이북: {_text(detail.get('final_playbook'))}",
        f"- 선택 전술: {_text(detail.get('tactical_strategy'))}",
        f"- 후보 감시 제안: {watch_scope or '-'}",
        "",
        "#### 전략 점수",
        "",
        *_strategy_score_lines(strategy_scores, selected=tactical_strategy),
        "",
        "#### 탈락 전략 이유",
        "",
        *_rejected_strategy_lines(rejected_reasons, selected=tactical_strategy),
        "",
        "### 메모리 사용",
        "",
        *_memory_usage_lines(memory),
        "",
        "### 뉴스 사용",
        "",
        *_news_usage_lines(news),
        "",
        *_quality_audit_lines(payload),
        "### 정책 조정",
        "",
        _directive_line("플레이북", _as_dict(changes.get("playbook_action"))),
        _directive_line("진입 정책", _as_dict(changes.get("entry_policy_action"))),
        _directive_line("모니터 초점", _as_dict(changes.get("monitor_focus_action"))),
        _directive_line("심볼 bias", _as_dict(changes.get("selected_symbol_bias_action"))),
        _directive_line("refresh", _as_dict(changes.get("refresh_action"))),
        "",
        "### 전략 Refresh 흐름",
        "",
        f"- 요약: {_text(refresh.get('summary'))}",
        "",
    ]
    lines.extend(_bullet_lines(_as_list(refresh.get("bullets"))))
    lines += ["", "#### 단계", ""]
    stages = _as_list(refresh.get("stages"))
    stage_line_count = 0
    for stage in stages:
        row = _as_dict(stage)
        if not row:
            continue
        stage_line_count += 1
        lines.append(
            f"- {_text(row.get('stage'))}: {_text(row.get('label'))}; "
            f"effective={row.get('effective')}; {_text(row.get('summary'))}"
        )
    if stage_line_count == 0:
        lines.append("- -")

    lines += [
        "",
        "### 모니터 진입 정책",
        "",
        f"- enabled: {entry.get('enabled')}",
        f"- timeframe_minutes: {entry.get('timeframe_minutes')}",
        f"- volume_ratio_min: {entry.get('volume_ratio_min')}",
        f"- vwap 확장 허용: min={entry.get('min_extended_from_vwap_pct')}, max={entry.get('max_extended_from_vwap_pct')}",
        f"- pullback 범위: min={entry.get('pullback_min_pct')}, max={entry.get('pullback_max_pct')}",
        f"- reclaim_tolerance_pct: {entry.get('reclaim_tolerance_pct')}",
        f"- intent_cooldown_sec: {entry.get('intent_cooldown_sec')}",
        f"- require_vwap_reclaim / require_rebound: {entry.get('require_vwap_reclaim')} / {entry.get('require_rebound')}",
        "",
        "### 운용 Horizon",
        "",
        f"- strategy_horizon: {_text(horizon.get('strategy_horizon'))}",
        f"- hold_window_sec: min={hold.get('min_sec')}, target={hold.get('target_sec')}, max={hold.get('max_sec')}",
        f"- preferred_exit: {_text(handoff.get('preferred_exit') or exit_guidance.get('profit_take_style'))}",
        f"- hold_bias: {_text(handoff.get('hold_bias'))}",
        f"- do_not_force_hold: {handoff.get('do_not_force_hold')}",
        f"- allow_early_exit: {exit_guidance.get('allow_early_exit')}",
        "",
        "#### 무효화 조건",
        "",
        *_bullet_lines(_as_list(horizon.get("invalidation_conditions"))),
        "",
        "---",
        "",
        "## 운영자 검수 요약",
        "",
        "> 아래 내용은 전략가 원문을 기준으로 한 deterministic 검수입니다. 추가 LLM 호출이나 새 전략 해석은 포함하지 않습니다.",
        "",
        f"- 검수 결론: **{_text(readout.get('headline'))}**",
        f"- 주요 원인: {_text(readout.get('root_cause'))}",
        "",
        "### 잘된 점",
        "",
        *_bullet_lines(_as_list(readout.get("good_points"))),
        "",
        "### 문제점",
        "",
        *_bullet_lines(_as_list(readout.get("issues"))),
        "",
        "### 권고 액션",
        "",
        *_bullet_lines(_as_list(readout.get("recommended_actions"))),
        "",
        "### 검증 포인트",
        "",
        *_bullet_lines(_as_list(readout.get("validation_questions"))),
        "",
        "---",
        "",
        "## 근거",
        "",
        f"- source_response_json: `{payload.get('source_response_json')}`",
        f"- source_canonical_strategist_json: `{payload.get('source_canonical_strategist_json')}`",
        f"- run_id: `{_text(meta.get('run_id'), '')}`",
        f"- saved_at: `{_text(meta.get('saved_at'), '')}`",
        f"- generated_at: `{_text(payload.get('generated_at'), '')}`",
        "",
    ]
    return "\n".join(lines)


def _monitor_adjustment_lines(value: Dict[str, Any]) -> List[str]:
    if not value:
        return ["- -"]
    return [f"- {key}: {value.get(key)}" for key in sorted(value)]


def _render_stage_specific_summary_markdown(payload: Dict[str, Any]) -> str:
    meta = _as_dict(payload.get("llm_meta"))
    readout = _as_dict(payload.get("operator_readout"))
    stage_decision = _as_dict(payload.get("stage_decision"))
    detail = _as_dict(payload.get("strategy_detail"))
    watch = _as_dict(detail.get("candidate_watch_policy"))
    triggers = ", ".join(str(x) for x in _as_list(stage_decision.get("priority_exit_triggers"))) or "-"
    monitor_adjustment = _as_dict(stage_decision.get("monitor_adjustment"))

    lines: List[str] = [
        f"# Strategist LLM Summary ({_text(meta.get('day'), '-')})",
        "",
        "---",
        "",
        "## Stage-Specific LLM Output",
        "",
        f"- status: {_text(meta.get('status'))} / model={_text(meta.get('model'))}",
        f"- stage: {stage_decision.get('stage_index')} / {_text(stage_decision.get('stage_name'))}",
        f"- call_kind: {_text(stage_decision.get('call_kind'))}",
        f"- stage_component: {_text(meta.get('stage_component'))}",
        "",
        "### Decision",
        "",
        f"- decision: **{_text(stage_decision.get('decision'))}**",
        f"- exit_pressure: {_text(stage_decision.get('exit_pressure'))}",
        f"- thesis_status: {_text(stage_decision.get('thesis_status'))}",
        f"- next_check_minutes: {stage_decision.get('next_check_minutes')}",
        f"- priority_exit_triggers: {triggers}",
        "",
        "### Monitor Adjustment",
        "",
        *_monitor_adjustment_lines(monitor_adjustment),
        "",
        "### Reason",
        "",
        _text(stage_decision.get("reason")),
        "",
        "## Strategy Context From Canonical",
        "",
        f"- final_playbook: {_text(detail.get('final_playbook'))}",
        f"- tactical_strategy: {_text(detail.get('tactical_strategy'))}",
        f"- playbook_flow: {_playbook_flow_label(detail)}",
        f"- candidate_watch: {_watch_scope_label_clean(watch) or '-'}",
        "",
        *_quality_audit_lines(payload),
        "## Operator Check",
        "",
        f"- summary: **{_text(readout.get('headline'))}**",
        f"- main_reason: {_text(readout.get('root_cause'))}",
        "",
        "### Good Points",
        "",
        *_bullet_lines(_as_list(readout.get("good_points"))),
        "",
        "### Issues",
        "",
        *_bullet_lines(_as_list(readout.get("issues"))),
        "",
        "### Recommended Actions",
        "",
        *_bullet_lines(_as_list(readout.get("recommended_actions"))),
        "",
        "---",
        "",
        "## Evidence",
        "",
        f"- source_response_json: `{payload.get('source_response_json')}`",
        f"- source_canonical_strategist_json: `{payload.get('source_canonical_strategist_json')}`",
        f"- run_id: `{_text(meta.get('run_id'), '')}`",
        f"- saved_at: `{_text(meta.get('saved_at'), '')}`",
        f"- generated_at: `{_text(payload.get('generated_at'), '')}`",
        "",
    ]
    return "\n".join(lines)


def _memory_usage_lines_clean(memory: Dict[str, Any]) -> List[str]:
    if not bool(memory.get("available")):
        return ["- 메모리 사용 trace: -"]
    lines = [
        f"- 활성 레이어: {', '.join(str(x) for x in _as_list(memory.get('active_layers'))) or '-'}",
        f"- 우선순위: {' -> '.join(str(x) for x in _as_list(memory.get('priority_order'))) or '-'}",
        f"- 요약: {_text(memory.get('human_summary'))}",
    ]
    applied = _as_dict(memory.get("applied_to_strategy"))
    if applied:
        lines.append(f"- 전략 반영: playbook={_text(applied.get('playbook_effect'))}, risk={_text(applied.get('risk_posture_effect'))}")
        lines.append(
            f"- scanner/monitor 반영: scanner={_text(applied.get('scanner_guidance_effect'))}, "
            f"monitor={_text(applied.get('monitor_policy_effect'))}"
        )
    layer_decisions = _as_dict(memory.get("layer_decisions"))
    for layer in ("daily", "weekly", "monthly", "symbol"):
        row = _as_dict(layer_decisions.get(layer))
        if not row:
            continue
        summary = _as_dict(row.get("operator_summary"))
        metrics = []
        if summary.get("trade_count") is not None:
            metrics.append(f"trades={summary.get('trade_count')}")
        if summary.get("win_rate") is not None:
            metrics.append(f"win_rate={summary.get('win_rate')}")
        if summary.get("avg_return_pct") is not None:
            metrics.append(f"avg_return_pct={summary.get('avg_return_pct')}")
        metric_text = f" ({', '.join(metrics)})" if metrics else ""
        lines.append(
            f"- {layer}: used={row.get('used')} status={_text(row.get('status'), '')} "
            f"effect={_text(row.get('effect'), '')}{metric_text}"
        )
    return lines


def _news_usage_lines_clean(news: Dict[str, Any]) -> List[str]:
    if not bool(news.get("available")):
        return ["- 뉴스 사용 trace: -"]
    query_targets = ", ".join(str(x) for x in _as_list(news.get("query_targets"))[:10]) or "-"
    return [
        f"- 검색/수집 대상: {query_targets}",
        f"- 사용 요약: {_text(news.get('human_summary'))}",
        f"- 시장 효과: {_text(news.get('market_effect'))}",
        f"- 플레이북 효과: {_text(news.get('playbook_effect'))}",
        f"- 스캐너 반영: {_text(news.get('scanner_guidance_effect'))}",
        f"- 모니터 반영: {_text(news.get('monitor_policy_effect'))}",
        f"- 근거 헤드라인 수: market={news.get('market_headline_count')}, candidate={news.get('candidate_headline_count')}",
        f"- query reasoning: {_text(news.get('news_query_reasoning'))}",
    ]


def _quality_audit_lines(payload: Dict[str, Any]) -> List[str]:
    rail = _as_dict(payload.get("market_regime_rail"))
    news = _as_dict(payload.get("news_quality_audit"))
    risk_policy = _as_dict(payload.get("risk_off_exception_policy"))
    risk_conditions = _as_list(payload.get("risk_off_exception_conditions"))
    news_event = _as_dict(payload.get("news_event_intelligence"))
    news_event_usage = _as_dict(payload.get("news_event_intelligence_usage"))
    output = _as_dict(payload.get("strategist_output_quality_audit"))
    metrics = _as_dict(rail.get("metrics"))
    rail_issues = _as_list(rail.get("issues"))
    news_issues = _as_list(news.get("issues"))
    output_issues = _as_list(output.get("issues"))

    def _issue_text(items: List[Any]) -> str:
        return ", ".join(str(x) for x in items if str(x or "").strip()) or "-"

    def _watch_text(items: List[Any], key: str) -> str:
        values: List[str] = []
        for item in items:
            if isinstance(item, dict):
                text = str(item.get(key) or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                values.append(text)
        return ", ".join(values[:6]) or "-"

    return [
        "## Input/Output Quality Audit",
        "",
        "### Market Regime Rail",
        "",
        f"- market_regime: {_text(rail.get('market_regime'), '-')}",
        f"- market_regime_rail: {_text(rail.get('market_regime_rail'), '-')}",
        f"- risk_score: {rail.get('risk_score')}",
        f"- kospi_pct: {metrics.get('kospi_pct')}",
        f"- kosdaq_pct: {metrics.get('kosdaq_pct')}",
        f"- breadth_score: {metrics.get('breadth_score')}",
        f"- issues: {_issue_text(rail_issues)}",
        "",
        "### News Quality",
        "",
        f"- status: {_text(news.get('status'), '-')}",
        f"- headline_count: {news.get('headline_count')}",
        f"- market_headline_count: {news.get('market_headline_count')}",
        f"- candidate_headline_count: {news.get('candidate_headline_count')}",
        f"- query_target_count: {news.get('query_target_count')}",
        f"- issues: {_issue_text(news_issues)}",
        "",
        "### Risk-Off Exceptions",
        "",
        f"- risk_off_active: {risk_policy.get('risk_off_active')}",
        f"- allowed_exception_conditions: {_issue_text(_as_list(risk_policy.get('allowed_exception_conditions')))}",
        f"- strategist_reported_conditions: {_issue_text(risk_conditions)}",
        f"- instruction: {_text(risk_policy.get('instruction'), '-')}",
        "",
        "### News Event Intelligence",
        "",
        f"- behavior_effect: {_text(news_event.get('behavior_effect'), 'observation_only')}",
        f"- trading_action_allowed: {news_event.get('trading_action_allowed', False)}",
        f"- event_count: {_as_dict(news_event.get('input_summary')).get('event_count', 0)}",
        f"- theme_watchlist: {_watch_text(_as_list(news_event.get('theme_watchlist')), 'theme')}",
        f"- symbol_watchlist: {_watch_text(_as_list(news_event.get('symbol_watchlist')), 'symbol')}",
        f"- llm_usage_status: {_text(news_event_usage.get('status'), '-')}",
        f"- llm_usage_reason: {_text(news_event_usage.get('reason'), '-')}",
        "",
        "### Strategist Output Quality",
        "",
        f"- status: {_text(output.get('status'), '-')}",
        f"- decision: {_text(output.get('decision'), '-')}",
        f"- confidence: {output.get('confidence')}",
        f"- final_playbook: {_text(output.get('final_playbook'), '-')}",
        f"- tactical_strategy: {_text(output.get('tactical_strategy'), '-')}",
        f"- issues: {_issue_text(output_issues)}",
        "",
    ]


def _render_stage_specific_summary_markdown_clean(payload: Dict[str, Any]) -> str:
    meta = _as_dict(payload.get("llm_meta"))
    readout = _as_dict(payload.get("operator_readout"))
    stage_decision = _as_dict(payload.get("stage_decision"))
    detail = _as_dict(payload.get("strategy_detail"))
    watch = _as_dict(detail.get("candidate_watch_policy"))
    monitor_instruction = _as_dict(stage_decision.get("monitor_instruction"))
    entry_policy_delta = _as_dict(stage_decision.get("entry_policy_delta"))
    commander_actionability = _as_dict(stage_decision.get("commander_actionability"))
    runners = ", ".join(str(x) for x in _as_list(stage_decision.get("runner_up_order"))) or "-"
    triggers = ", ".join(str(x) for x in _as_list(stage_decision.get("priority_exit_triggers"))) or "-"

    lines: List[str] = [
        f"# Strategist LLM Summary ({_text(meta.get('day'), '-')})",
        "",
        "---",
        "",
        "## 단계별 전략가 LLM 출력",
        "",
        f"- 상태: {_text(meta.get('status'))} / model={_text(meta.get('model'))}",
        f"- 단계: {stage_decision.get('stage_index')} / {_text(stage_decision.get('stage_name'))}",
        f"- 호출 종류: {_text(stage_decision.get('call_kind'))}",
        f"- stage component: {_text(stage_decision.get('stage_component') or meta.get('stage_component'))}",
        "",
        "### 결정",
        "",
        f"- decision: **{_text(stage_decision.get('decision'))}**",
        f"- target_symbol: {_text(stage_decision.get('target_symbol'))}",
        f"- target_rank: {stage_decision.get('target_rank')}",
        f"- runner_up_order: {runners}",
        f"- confidence: {stage_decision.get('confidence')}",
        f"- exit_pressure: {_text(stage_decision.get('exit_pressure'), '')}",
        f"- thesis_status: {_text(stage_decision.get('thesis_status'), '')}",
        f"- next_check_minutes: {stage_decision.get('next_check_minutes')}",
        f"- priority_exit_triggers: {triggers}",
        "",
        "### 모니터 지시",
        "",
    ]
    if monitor_instruction:
        for key in sorted(monitor_instruction):
            lines.append(f"- {key}: {_json_inline(monitor_instruction.get(key))}")
    else:
        lines.append("- -")
    lines += ["", "### 진입 정책 delta", ""]
    if entry_policy_delta:
        for key in sorted(entry_policy_delta):
            lines.append(f"- {key}: {_json_inline(entry_policy_delta.get(key))}")
    else:
        lines.append("- -")
    lines += ["", "### 지휘관 적용 가능성", ""]
    if commander_actionability:
        for key in sorted(commander_actionability):
            lines.append(f"- {key}: {_json_inline(commander_actionability.get(key))}")
    else:
        lines.append("- -")
    lines += [
        "",
        "### 사유",
        "",
        _text(stage_decision.get("reason")),
        "",
        "## Canonical 전략 컨텍스트",
        "",
        f"- final_playbook: {_text(detail.get('final_playbook'))}",
        f"- tactical_strategy: {_text(detail.get('tactical_strategy'))}",
        f"- playbook_flow: {_playbook_flow_label(detail)}",
        f"- candidate_watch: {_watch_scope_label_clean(watch) or '-'}",
        "",
        *_quality_audit_lines(payload),
        "## 운영 점검",
        "",
        f"- 요약: **{_text(readout.get('headline'))}**",
        f"- 주요 원인: {_text(readout.get('root_cause'))}",
        "",
        "### 잘 된 점",
        "",
        *_bullet_lines(_as_list(readout.get("good_points"))),
        "",
        "### 문제점",
        "",
        *_bullet_lines(_as_list(readout.get("issues"))),
        "",
        "### 권고 액션",
        "",
        *_bullet_lines(_as_list(readout.get("recommended_actions"))),
        "",
        "---",
        "",
        "## 근거",
        "",
        f"- source_response_json: `{payload.get('source_response_json')}`",
        f"- source_canonical_strategist_json: `{payload.get('source_canonical_strategist_json')}`",
        f"- run_id: `{_text(meta.get('run_id'), '')}`",
        f"- saved_at: `{_text(meta.get('saved_at'), '')}`",
        f"- generated_at: `{_text(payload.get('generated_at'), '')}`",
        "",
    ]
    return "\n".join(lines)


def render_strategist_llm_summary_markdown(payload: Dict[str, Any]) -> str:
    meta = _as_dict(payload.get("llm_meta"))
    readout = _as_dict(payload.get("operator_readout"))
    stage_decision = _as_dict(payload.get("stage_decision"))
    if bool(stage_decision.get("is_stage_specific")):
        return _render_stage_specific_summary_markdown_clean(payload)

    frame = _as_dict(payload.get("strategy_frame"))
    detail = _as_dict(payload.get("strategy_detail"))
    changes = _as_dict(payload.get("policy_changes"))
    entry = _as_dict(payload.get("monitor_entry_policy"))
    memory = _as_dict(payload.get("memory_usage"))
    news = _as_dict(payload.get("news_usage"))
    refresh = _as_dict(payload.get("strategy_refresh_trace"))
    horizon = _as_dict(payload.get("strategy_horizon_feedback"))
    hold = _as_dict(horizon.get("expected_hold_window"))
    exit_guidance = _as_dict(horizon.get("exit_guidance"))
    handoff = _as_dict(horizon.get("monitor_handoff"))
    selected_themes = _as_list(frame.get("selected_themes"))
    theme_text = ", ".join(str(x) for x in selected_themes) if selected_themes else "-"
    watch = _as_dict(detail.get("candidate_watch_policy"))
    tactical_strategy = _text(detail.get("tactical_strategy"), "")
    strategy_scores = _as_dict(detail.get("strategy_scores"))
    rejected_reasons = _as_dict(detail.get("rejected_strategy_reasons"))

    lines: List[str] = [
        f"# Strategist LLM Summary ({_text(meta.get('day'), '-')})",
        "",
        "---",
        "",
        "## 전략가 원문 해석 출력",
        "",
        "> 아래 내용은 전략가 LLM 응답과 canonical 전략가 산출물을 사람이 읽기 좋게 재배열한 것입니다.",
        "",
        f"- 상태: {_text(meta.get('status'))} / model={_text(meta.get('model'))}",
        "",
        "### 전략 프레임",
        "",
        f"- 플레이북: **{_text(frame.get('playbook'))}**",
        f"- 선택 테마: {theme_text}",
        f"- 테마 선택 모드: {_text(frame.get('theme_selection_mode'))}",
        f"- fallback 사유: {_text(frame.get('fallback_reason'))}",
        "",
        "**전략가 rationale**",
        "",
        _text(frame.get("rationale")),
        "",
        "### 전략 디테일",
        "",
        f"- 전략 강화 필드: {_strategy_patch_status_clean(detail)}",
        f"- 플레이북 흐름: {_playbook_flow_label(detail)}",
        f"- LLM 요청 플레이북: {_text(detail.get('llm_requested_playbook'))}",
        f"- 최종 플레이북: {_text(detail.get('final_playbook'))}",
        f"- 선택 전술: {_text(detail.get('tactical_strategy'))}",
        f"- 후보 감시 제안: {_watch_scope_label_clean(watch) or '-'}",
        "",
        "#### 전략 점수",
        "",
        *_strategy_score_lines_clean(strategy_scores, selected=tactical_strategy),
        "",
        "#### 제외 전략 이유",
        "",
        *_rejected_strategy_lines(rejected_reasons, selected=tactical_strategy),
        "",
        "### 메모리 사용",
        "",
        *_memory_usage_lines_clean(memory),
        "",
        "### 뉴스 사용",
        "",
        *_news_usage_lines_clean(news),
        "",
        *_quality_audit_lines(payload),
        "### 정책 조정",
        "",
        _directive_line("플레이북", _as_dict(changes.get("playbook_action"))),
        _directive_line("진입 정책", _as_dict(changes.get("entry_policy_action"))),
        _directive_line("모니터 초점", _as_dict(changes.get("monitor_focus_action"))),
        _directive_line("성과 bias", _as_dict(changes.get("selected_symbol_bias_action"))),
        _directive_line("refresh", _as_dict(changes.get("refresh_action"))),
        "",
        "### 전략 Refresh 흐름",
        "",
        f"- 요약: {_text(refresh.get('summary'))}",
        "",
    ]
    lines.extend(_bullet_lines(_as_list(refresh.get("bullets"))))
    lines += ["", "#### 단계", ""]
    stages = _as_list(refresh.get("stages"))
    stage_line_count = 0
    for stage in stages:
        row = _as_dict(stage)
        if not row:
            continue
        stage_line_count += 1
        lines.append(
            f"- {_text(row.get('stage'))}: {_text(row.get('label'))}; "
            f"effective={row.get('effective')}; {_text(row.get('summary'))}"
        )
    if stage_line_count == 0:
        lines.append("- -")

    lines += [
        "",
        "### 모니터 진입 정책",
        "",
        f"- enabled: {entry.get('enabled')}",
        f"- timeframe_minutes: {entry.get('timeframe_minutes')}",
        f"- volume_ratio_min: {entry.get('volume_ratio_min')}",
        f"- vwap 확장 허용: min={entry.get('min_extended_from_vwap_pct')}, max={entry.get('max_extended_from_vwap_pct')}",
        f"- pullback 범위: min={entry.get('pullback_min_pct')}, max={entry.get('pullback_max_pct')}",
        f"- reclaim_tolerance_pct: {entry.get('reclaim_tolerance_pct')}",
        f"- intent_cooldown_sec: {entry.get('intent_cooldown_sec')}",
        f"- require_vwap_reclaim / require_rebound: {entry.get('require_vwap_reclaim')} / {entry.get('require_rebound')}",
        "",
        "### 보유 Horizon",
        "",
        f"- strategy_horizon: {_text(horizon.get('strategy_horizon'))}",
        f"- hold_window_sec: min={hold.get('min_sec')}, target={hold.get('target_sec')}, max={hold.get('max_sec')}",
        f"- preferred_exit: {_text(handoff.get('preferred_exit') or exit_guidance.get('profit_take_style'))}",
        f"- hold_bias: {_text(handoff.get('hold_bias'))}",
        f"- do_not_force_hold: {handoff.get('do_not_force_hold')}",
        f"- allow_early_exit: {exit_guidance.get('allow_early_exit')}",
        "",
        "#### 무효화 조건",
        "",
        *_bullet_lines(_as_list(horizon.get("invalidation_conditions"))),
        "",
        "---",
        "",
        "## 운영자 검토 요약",
        "",
        "> 아래 내용은 전략가 원문을 기준으로 한 deterministic 검토입니다. 추가 LLM 호출은 포함하지 않습니다.",
        "",
        f"- 검토 결론: **{_text(readout.get('headline'))}**",
        f"- 주요 원인: {_text(readout.get('root_cause'))}",
        "",
        "### 잘 된 점",
        "",
        *_bullet_lines(_as_list(readout.get("good_points"))),
        "",
        "### 문제점",
        "",
        *_bullet_lines(_as_list(readout.get("issues"))),
        "",
        "### 권고 액션",
        "",
        *_bullet_lines(_as_list(readout.get("recommended_actions"))),
        "",
        "### 검증 포인트",
        "",
        *_bullet_lines(_as_list(readout.get("validation_questions"))),
        "",
        "---",
        "",
        "## 근거",
        "",
        f"- source_response_json: `{payload.get('source_response_json')}`",
        f"- source_canonical_strategist_json: `{payload.get('source_canonical_strategist_json')}`",
        f"- run_id: `{_text(meta.get('run_id'), '')}`",
        f"- saved_at: `{_text(meta.get('saved_at'), '')}`",
        f"- generated_at: `{_text(payload.get('generated_at'), '')}`",
        "",
    ]
    return "\n".join(lines)


def generate_strategist_llm_summary(response_json_path: Path) -> Tuple[Path, Path, Dict[str, Any]]:
    source_path = Path(response_json_path)
    payload = build_strategist_llm_summary_payload(source_path)
    md_path = source_path.with_name("strategist_summary.md")
    json_path = source_path.with_name("strategist_summary.json")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_strategist_llm_summary_markdown(payload), encoding="utf-8-sig", newline="\n")
    return md_path, json_path, payload
