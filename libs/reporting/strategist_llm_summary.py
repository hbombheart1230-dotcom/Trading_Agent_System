from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, default: str = "-") -> str:
    raw = str(value or "").strip()
    return raw if raw else default


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


def _load_canonical_strategist(source_path: Path) -> Tuple[Path | None, Dict[str, Any]]:
    canonical_path = _canonical_strategist_path_for_response(source_path)
    if canonical_path is None or not canonical_path.exists():
        return canonical_path, {}
    try:
        raw = json.loads(canonical_path.read_text(encoding="utf-8"))
    except Exception:
        return canonical_path, {}
    return canonical_path, dict(raw) if isinstance(raw, dict) else {}


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
    query_targets = _as_list(trace.get("query_targets")) or _as_list(canonical.get("news_query_targets"))
    market_headlines = _as_list(trace.get("market_headlines_used"))
    candidate_headlines = _as_list(trace.get("candidate_headlines_used"))
    return {
        "available": bool(trace or canonical.get("news_evidence_summary") or query_targets),
        "query_targets": query_targets,
        "human_summary": _text(trace.get("human_summary"), ""),
        "market_effect": _text(trace.get("market_effect"), ""),
        "playbook_effect": _text(trace.get("playbook_effect"), ""),
        "scanner_guidance_effect": _text(trace.get("scanner_guidance_effect"), ""),
        "monitor_policy_effect": _text(trace.get("monitor_policy_effect"), ""),
        "confidence": _text(trace.get("confidence"), ""),
        "news_evidence_summary": _text(canonical.get("news_evidence_summary"), ""),
        "news_query_reasoning": _text(canonical.get("news_query_reasoning"), ""),
        "market_headline_count": len(market_headlines),
        "candidate_headline_count": len(candidate_headlines),
        "market_headlines_sample": market_headlines[:3],
        "candidate_headlines_sample": candidate_headlines[:3],
    }


def _stage_decision_from_payload(payload: Dict[str, Any], raw: Dict[str, Any]) -> Dict[str, Any]:
    call_kind = _text(raw.get("call_kind") or payload.get("call_kind"), "")
    stage_name = _text(raw.get("stage_name") or payload.get("stage_name"), "")
    try:
        stage_index = int(raw.get("stage_index") or payload.get("stage_index") or 0)
    except (TypeError, ValueError):
        stage_index = 0
    is_market_frame = stage_index in (0, 1) and call_kind in {"", "market_strategy_frame", "theme_selection", "strategic_frame"}
    if is_market_frame:
        return {"is_stage_specific": False}

    decision = _first_text(
        "",
        payload.get("hold_review_decision"),
        payload.get("carry_review_decision"),
        payload.get("tactical_refresh_decision"),
        payload.get("selected_symbol_decision"),
        payload.get("decision"),
    )
    monitor_adjustment = _as_dict(payload.get("monitor_adjustment"))
    priority_exit_triggers = _as_list(payload.get("priority_exit_triggers"))
    return {
        "is_stage_specific": True,
        "stage_index": stage_index,
        "stage_name": stage_name,
        "call_kind": call_kind,
        "decision": decision,
        "exit_pressure": _text(payload.get("exit_pressure"), ""),
        "thesis_status": _text(payload.get("thesis_status"), ""),
        "next_check_minutes": payload.get("next_check_minutes"),
        "priority_exit_triggers": priority_exit_triggers,
        "monitor_adjustment": monitor_adjustment,
        "reason": _text(payload.get("reason"), ""),
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
    payload = _parse_response_body(raw)
    canonical_path, canonical = _load_canonical_strategist(source_path)
    theme_strategy = _as_dict(payload.get("theme_strategy"))
    refresh_trace = _as_dict(payload.get("strategy_refresh_trace"))
    horizon = _as_dict(payload.get("strategy_horizon_feedback"))
    strategy_detail = _strategy_detail_from_sources(payload, canonical)
    stage_decision = _stage_decision_from_payload(payload, raw)

    return {
        "schema_version": "strategist_llm_summary.v1",
        "artifact_type": "strategist_llm_summary",
        "source_response_json": str(source_path),
        "source_canonical_strategist_json": str(canonical_path) if canonical_path else "",
        "generated_at": _utc_now_iso(),
        "llm_meta": {
            "stage": _text(raw.get("stage"), ""),
            "stage_index": raw.get("stage_index"),
            "stage_name": _text(raw.get("stage_name"), ""),
            "call_kind": _text(raw.get("call_kind"), ""),
            "stage_component": _text(raw.get("stage_component"), ""),
            "provider": _text(raw.get("provider"), ""),
            "model": _text(raw.get("model"), ""),
            "status": _text(raw.get("status"), ""),
            "reason": _text(raw.get("reason"), ""),
            "run_id": _text(raw.get("run_id"), ""),
            "day": _text(raw.get("day"), ""),
            "saved_at": _text(raw.get("saved_at"), ""),
            "repair_used": bool(raw.get("repair_used")),
            "profile_name": _text(raw.get("llm_execution_profile_name"), ""),
            "profile_source": _text(raw.get("llm_execution_profile_source"), ""),
        },
        "operator_readout": _operator_readout(payload, stage_decision),
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
        "news_usage": _news_usage_from_canonical(canonical),
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
        f"- candidate_watch: {_watch_scope_label(watch) or '-'}",
        "",
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


def generate_strategist_llm_summary(response_json_path: Path) -> Tuple[Path, Path, Dict[str, Any]]:
    source_path = Path(response_json_path)
    payload = build_strategist_llm_summary_payload(source_path)
    md_path = source_path.with_name("strategist_summary.md")
    json_path = source_path.with_name("strategist_summary.json")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_strategist_llm_summary_markdown(payload), encoding="utf-8")
    return md_path, json_path, payload
