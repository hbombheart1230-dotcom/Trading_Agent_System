from __future__ import annotations

from typing import Any, Dict, List


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, *, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _list_text(value: Any, *, limit: int = 6, max_len: int = 80) -> List[str]:
    out: List[str] = []
    seen = set()
    for row in _list(value):
        text = _text(row, max_len=max_len)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _top_headlines(rows: Any, *, limit: int = 3) -> List[str]:
    out: List[str] = []
    seen = set()
    for row in _list(rows):
        if not isinstance(row, dict):
            continue
        titles = _list(row.get("sample_titles"))
        if not titles:
            title = row.get("title") or row.get("headline")
            titles = [title] if title else []
        target = _text(row.get("target") or row.get("symbol"), max_len=24)
        for title in titles:
            text = _text(title, max_len=160)
            if not text:
                continue
            label = f"{target}: {text}" if target and not text.startswith(f"{target}:") else text
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(label)
            if len(out) >= limit:
                return out
    return out


def _packet_confidence(packet: Dict[str, Any]) -> float:
    sample_quality = _dict(packet.get("sample_quality"))
    if sample_quality.get("confidence") not in (None, ""):
        return round(_safe_float(sample_quality.get("confidence")), 4)
    strength = _text(packet.get("evidence_strength"), max_len=24).lower()
    if strength == "strong":
        return 0.85
    if strength == "moderate":
        return 0.6
    if strength == "thin":
        return 0.25
    if bool(packet.get("active")):
        return 0.5
    return 0.0


def _operator_summary_ref(packet: Dict[str, Any]) -> Dict[str, Any]:
    summary = _dict(packet.get("operator_summary"))
    metrics = _dict(summary.get("metrics"))
    return {
        "available": bool(summary.get("available")),
        "status": _text(summary.get("status"), max_len=24),
        "artifact_path": _text(summary.get("artifact_path"), max_len=160),
        "trade_count": _safe_int(metrics.get("trade_count")),
        "closed_trade_count": _safe_int(metrics.get("closed_trade_count")),
        "win_rate": _safe_float(metrics.get("win_rate")),
        "avg_return_pct": _safe_float(metrics.get("avg_return_pct")),
    }


def _memory_layer_reason(
    *,
    layer: str,
    packet: Dict[str, Any],
    used: bool,
) -> str:
    if not packet:
        return "memory packet is unavailable"
    if layer == "symbol" and not used:
        gate = _text(packet.get("override_gate_reason"), max_len=80)
        if gate:
            return f"symbol memory was visible but gated by {gate}"
    if used:
        summary = _text(packet.get("summary"), max_len=180)
        if summary:
            return summary
        failures = _list_text(_dict(packet.get("failure_patterns")).get("dominant_failures"), limit=2)
        if failures:
            return "dominant failure patterns: " + ", ".join(failures)
        best = _list_text(packet.get("best_playbooks"), limit=2)
        worst = _list_text(packet.get("worst_playbooks"), limit=2)
        bits = []
        if best:
            bits.append("prefer " + ", ".join(best))
        if worst:
            bits.append("avoid " + ", ".join(worst))
        if bits:
            return "; ".join(bits)
        return "layer is active in commander memory policy"
    if not bool(packet.get("active")):
        status = _text(packet.get("status"), max_len=40)
        return f"layer inactive; status={status or 'unknown'}"
    return "layer visible but not selected by commander priority"


def _memory_layer_effect(
    *,
    layer: str,
    packet: Dict[str, Any],
    used: bool,
    scanner_delta_keys: List[str],
    monitor_delta_keys: List[str],
) -> str:
    if not packet:
        return "unavailable"
    if not used:
        if layer == "symbol":
            gate = _text(packet.get("override_gate_reason"), max_len=80)
            return f"blocked:{gate}" if gate else "advisory_only"
        if not bool(packet.get("active")):
            return "inactive_sample_or_context_gate"
        return "not_selected_by_commander_priority"
    if layer == "symbol":
        return "symbol_override_bias"
    if layer == "daily":
        effects: List[str] = ["primary_strategy_memory"]
        if scanner_delta_keys:
            effects.append("scanner_delta")
        if monitor_delta_keys:
            effects.append("monitor_delta")
        return "+".join(effects)
    if layer in {"weekly", "monthly"}:
        return "baseline_context_bias"
    return "shape_strategy_frame"


def build_memory_usage_trace(
    *,
    strategist_output: Dict[str, Any],
    state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = state or {}
    memory_packets = _dict(strategist_output.get("memory_packets") or _dict(state.get("commander_decision")).get("memory_packets"))
    commander_policy = _dict(
        strategist_output.get("commander_memory_policy")
        or _dict(strategist_output.get("commander_context_ref")).get("commander_memory_policy")
        or _dict(state.get("commander_decision")).get("commander_memory_policy")
    )
    scanner_bias = _dict(
        strategist_output.get("scanner_memory_bias")
        or _dict(strategist_output.get("commander_context_ref")).get("scanner_memory_bias")
    )
    monitor_bias = _dict(
        strategist_output.get("monitor_memory_bias")
        or _dict(strategist_output.get("commander_context_ref")).get("monitor_memory_bias")
    )
    active_layers = _list_text(commander_policy.get("active_layers"), limit=4, max_len=16)
    priority_order = _list_text(commander_policy.get("priority_order"), limit=4, max_len=16)
    if not priority_order:
        priority_order = ["daily", "weekly", "monthly", "symbol"]
    active_set = {x.lower() for x in active_layers}

    scanner_delta = _dict(scanner_bias.get("source_weight_delta"))
    scanner_symbol_adjustments = _dict(scanner_bias.get("symbol_adjustments"))
    monitor_entry_delta = _dict(monitor_bias.get("entry_policy_delta"))
    monitor_hold_delta = _dict(monitor_bias.get("hold_policy_delta"))
    monitor_exit_delta = _dict(monitor_bias.get("exit_policy_delta"))
    scanner_delta_keys = [str(x) for x in list(scanner_delta.keys())[:6] if str(x or "").strip()]
    monitor_delta_keys = [
        str(x)
        for x in (
            list(monitor_entry_delta.keys())[:4]
            + list(monitor_hold_delta.keys())[:3]
            + list(monitor_exit_delta.keys())[:4]
        )
        if str(x or "").strip()
    ]

    layer_to_packet_key = {
        "daily": "daily_strategy_memory",
        "weekly": "weekly_strategy_memory",
        "monthly": "monthly_strategy_memory",
        "symbol": "symbol_memory_packet",
    }
    layer_decisions: Dict[str, Any] = {}
    for layer in ("daily", "weekly", "monthly", "symbol"):
        packet = _dict(memory_packets.get(layer_to_packet_key[layer]))
        if layer == "symbol":
            used = bool(commander_policy.get("symbol_memory_override_enabled")) and layer in active_set
        else:
            used = layer in active_set
        reason = _memory_layer_reason(layer=layer, packet=packet, used=used)
        effect = _memory_layer_effect(
            layer=layer,
            packet=packet,
            used=used,
            scanner_delta_keys=scanner_delta_keys,
            monitor_delta_keys=monitor_delta_keys,
        )
        decision = {
            "status": _text(packet.get("status"), max_len=40) if packet else "unavailable",
            "active": bool(packet.get("active")) if packet else False,
            "visible": bool(packet),
            "used": bool(used),
            "confidence": _packet_confidence(packet),
            "operator_summary": _operator_summary_ref(packet),
            "effect": effect,
            "application_targets": (
                ["strategist_frame", "scanner_bias", "monitor_bias"]
                if used and layer == "daily"
                else ["strategist_frame", "commander_baseline"]
                if used
                else []
            ),
            "reason": reason,
        }
        if layer == "symbol":
            decision["gate_reason"] = _text(packet.get("override_gate_reason"), max_len=80)
            decision["evidence_strength"] = _text(packet.get("evidence_strength"), max_len=24)
        layer_decisions[layer] = decision

    policy_signals = _dict(commander_policy.get("policy_signals"))
    applied_to_strategy = {
        "playbook_effect": f"maintain_{_text(strategist_output.get('playbook'), max_len=40) or 'current'}",
        "risk_posture_effect": _text(policy_signals.get("preferred_risk_posture") or strategist_output.get("risk_tone"), max_len=40),
        "scanner_guidance_effect": (
            "source_weight_delta:" + ",".join(list(scanner_delta.keys())[:4])
            if scanner_delta
            else "no_scanner_memory_delta"
        ),
        "monitor_policy_effect": (
            "memory_delta:"
            + ",".join(
                list(monitor_entry_delta.keys())[:3]
                + list(monitor_hold_delta.keys())[:2]
                + list(monitor_exit_delta.keys())[:3]
            )
            if (monitor_entry_delta or monitor_hold_delta or monitor_exit_delta)
            else "no_monitor_memory_delta"
        ),
    }
    scanner_application = {
        "enabled": bool(scanner_bias.get("enabled")),
        "active_layers": _list_text(scanner_bias.get("active_layers"), limit=4, max_len=16),
        "source_delta_keys": scanner_delta_keys,
        "symbol_adjustment_count": len(scanner_symbol_adjustments),
        "reason": _list_text(scanner_bias.get("reason"), limit=6, max_len=120),
    }
    monitor_application = {
        "enabled": bool(monitor_bias.get("enabled")),
        "active_layers": _list_text(monitor_bias.get("active_layers"), limit=4, max_len=16),
        "entry_delta_keys": [str(x) for x in list(monitor_entry_delta.keys())[:6] if str(x or "").strip()],
        "hold_delta_keys": [str(x) for x in list(monitor_hold_delta.keys())[:4] if str(x or "").strip()],
        "exit_delta_keys": [str(x) for x in list(monitor_exit_delta.keys())[:4] if str(x or "").strip()],
        "risk_posture": _text(monitor_bias.get("risk_posture"), max_len=40),
        "reason": _list_text(monitor_bias.get("reason"), limit=6, max_len=120),
    }
    unused = [
        f"{layer}:{row.get('gate_reason') or row.get('reason')}"
        for layer, row in layer_decisions.items()
        if row.get("visible") and not row.get("used")
    ][:4]
    human_summary = (
        "Active memory layers: "
        + (", ".join(active_layers) if active_layers else "none")
        + ("; unused visible layers: " + "; ".join(unused) if unused else "")
    )
    return {
        "schema_version": "strategist.memory_usage_trace.v1",
        "active_layers": active_layers,
        "priority_order": priority_order,
        "layer_decisions": layer_decisions,
        "applied_to_strategy": applied_to_strategy,
        "scanner_application": scanner_application,
        "monitor_application": monitor_application,
        "human_summary": human_summary,
    }


def build_news_usage_trace(
    *,
    strategist_output: Dict[str, Any],
    news_evidence_ranked: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    evidence = _dict(news_evidence_ranked or strategist_output.get("news_evidence_ranked"))
    news_context = _dict(evidence.get("news_context") or strategist_output.get("news_context"))
    query_targets = _list_text(
        evidence.get("news_query_targets") or strategist_output.get("news_query_targets"),
        limit=10,
        max_len=80,
    )
    market_headlines = _top_headlines(evidence.get("market_news_ranked"), limit=3)
    candidate_headlines = _top_headlines(evidence.get("candidate_news_ranked"), limit=3)
    avg_score = _safe_float(news_context.get("avg_score"))
    if avg_score >= 0.15:
        market_effect = "supports selective risk-on context"
    elif avg_score <= -0.15:
        market_effect = "adds risk-off pressure"
    elif market_headlines or candidate_headlines:
        market_effect = "provides context but not directional permission"
    else:
        market_effect = "no material news evidence captured"
    playbook = _text(strategist_output.get("playbook"), max_len=40) or "current"
    monitor_guidance = _text(strategist_output.get("monitor_guidance"), max_len=60)
    confidence = "medium" if (market_headlines or candidate_headlines) else "low"
    if abs(avg_score) >= 0.3 and (market_headlines or candidate_headlines):
        confidence = "high"
    return {
        "schema_version": "strategist.news_usage_trace.v1",
        "query_targets": query_targets,
        "market_headlines_used": market_headlines,
        "candidate_headlines_used": candidate_headlines,
        "market_effect": market_effect,
        "playbook_effect": f"kept {playbook} frame unless tape confirmation contradicts it",
        "scanner_guidance_effect": "use news/theme alignment as ranking context, not final symbol selection",
        "monitor_policy_effect": f"news does not relax monitor gate; guidance={monitor_guidance or 'not_captured'}",
        "ignored_or_low_signal_news": [] if confidence != "low" else ["no strong headline linkage captured"],
        "confidence": confidence,
        "source_event": "strategist.news_evidence_ranked",
        "human_summary": (
            "News was used for market/theme context and scanner guidance; it was not used as final symbol selection."
        ),
    }


def build_strategy_thesis(*, strategist_output: Dict[str, Any]) -> Dict[str, Any]:
    market_regime = _text(strategist_output.get("market_regime"), max_len=40) or "neutral"
    market_sentiment = _text(strategist_output.get("market_sentiment"), max_len=40) or "neutral"
    playbook = _text(strategist_output.get("playbook"), max_len=40) or "defensive"
    risk_tone = _text(strategist_output.get("risk_tone"), max_len=40) or "normal"
    monitor_guidance = _text(strategist_output.get("monitor_guidance"), max_len=60) or "defensive_exit"
    style_map = {
        "breakout": "prefer confirmed breakout continuation",
        "pullback": "prefer pullback or reclaim confirmation",
        "reversal": "prefer reversal only after confirmation",
        "defensive": "prefer capital preservation and confirmation",
    }
    trade_style = style_map.get(playbook, "prefer confirmation before entry")
    return {
        "market_view": f"{market_regime} regime with {market_sentiment} sentiment",
        "trade_style": trade_style,
        "risk_tone": risk_tone,
        "selected_playbook": playbook,
        "one_line": f"{playbook} frame with {risk_tone} risk tone; monitor guidance is {monitor_guidance}.",
    }


def build_strategy_delta_trace(
    *,
    strategist_output: Dict[str, Any],
    state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = state or {}
    current = _text(strategist_output.get("playbook"), max_len=40)
    cache = _dict(state.get("strategist_output_cache") or _dict(state.get("persisted_state")).get("strategist_output_cache"))
    previous_output = _dict(cache.get("output"))
    previous = _text(previous_output.get("playbook"), max_len=40)
    changed = bool(previous and current and previous != current)
    if not previous:
        reason = "No prior comparable strategist frame was available."
    elif changed:
        reason = f"Playbook changed from {previous} to {current}."
    else:
        reason = "Current frame maintained the prior playbook."
    return {
        "changed": bool(changed),
        "previous_playbook": previous,
        "current_playbook": current,
        "change_reason": reason,
        "unchanged_items": ["responsibility_boundary", "scanner_owns_symbol_selection"],
        "evidence_refs": ["memory_usage_trace", "news_usage_trace"],
    }


def build_strategy_refresh_trace(
    *,
    strategist_output: Dict[str, Any],
    state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    state = state or {}
    commander_decision = _dict(state.get("commander_decision"))
    observations = _dict(commander_decision.get("observations"))
    commander_context_ref = _dict(strategist_output.get("commander_context_ref"))
    commander_refresh_context = _dict(
        strategist_output.get("commander_refresh_context")
        or commander_context_ref.get("strategist_refresh_context")
        or commander_decision.get("strategist_refresh_context")
    )
    open_position_refresh_context = _dict(
        strategist_output.get("commander_open_position_refresh_context")
        or commander_context_ref.get("open_position_refresh_context")
        or commander_decision.get("open_position_refresh_context")
    )
    route_observability = _dict(
        _first_present(
            commander_decision.get("route_observability"),
            state.get("route_observability"),
        )
    )

    invocation = _text(
        _first_present(
            strategist_output.get("commander_invocation_hint"),
            commander_context_ref.get("strategist_invocation"),
            commander_decision.get("strategist_invocation"),
        ),
        max_len=80,
    )
    route_selected = _text(
        _first_present(
            route_observability.get("route_selected"),
            commander_decision.get("route_selected"),
            commander_decision.get("selected_route"),
        ),
        max_len=80,
    )
    cache_used = bool(
        _first_present(
            commander_decision.get("strategist_cache_used"),
            observations.get("strategist_cache_used"),
            route_observability.get("strategist_cache_used"),
        )
    )
    cached_candidate_hints = _list_text(
        _first_present(
            commander_refresh_context.get("cached_candidate_hints"),
            observations.get("cached_candidate_hints"),
            strategist_output.get("candidate_hints"),
            strategist_output.get("candidates"),
        ),
        limit=8,
        max_len=24,
    )

    post_scanner_requested = bool(
        _first_present(
            observations.get("post_scanner_refresh_requested"),
            commander_decision.get("post_scanner_refresh_requested"),
            strategist_output.get("post_scanner_refresh_requested"),
        )
    )
    refresh_requested = bool(
        _first_present(
            strategist_output.get("commander_refresh_requested"),
            commander_context_ref.get("strategist_refresh_requested"),
            commander_decision.get("strategist_refresh_requested"),
            observations.get("strategist_refresh_requested"),
            post_scanner_requested,
        )
    )
    refresh_reason = _text(
        _first_present(
            strategist_output.get("commander_refresh_reason"),
            commander_context_ref.get("strategist_refresh_reason"),
            commander_decision.get("strategist_refresh_reason"),
            observations.get("strategist_refresh_reason"),
            observations.get("post_scanner_refresh_reason"),
        ),
        max_len=160,
    )
    selected_symbol = _text(
        _first_present(
            commander_refresh_context.get("selected_symbol"),
            observations.get("post_scanner_refresh_selected_symbol"),
            open_position_refresh_context.get("selected_symbol"),
            commander_decision.get("selected_symbol"),
        ),
        max_len=24,
    )
    selected_in_cached_frame = _first_present(
        commander_refresh_context.get("selected_symbol_in_cached_frame"),
        observations.get("selected_symbol_in_cached_frame"),
    )
    refresh_signal = _text(
        _first_present(
            commander_refresh_context.get("refresh_signal"),
            observations.get("refresh_signal"),
            open_position_refresh_context.get("refresh_scope"),
        ),
        max_len=80,
    )
    refresh_evaluated = bool(
        _first_present(
            commander_decision.get("strategist_refresh_evaluated"),
            observations.get("strategist_refresh_evaluated"),
            refresh_requested,
        )
    )
    refresh_effective = bool(
        _first_present(
            commander_decision.get("strategist_refresh_effective"),
            observations.get("strategist_refresh_effective"),
            False,
        )
    )
    policy_delta_count = _safe_int(
        _first_present(
            commander_decision.get("strategist_refresh_policy_delta_count"),
            observations.get("strategist_refresh_policy_delta_count"),
            _dict(strategist_output.get("policy_adjustment")).get("delta_count"),
        ),
        0,
    )
    policy_delta_fields = _list_text(
        _first_present(
            commander_decision.get("strategist_refresh_policy_delta_fields"),
            observations.get("strategist_refresh_policy_delta_fields"),
            _dict(strategist_output.get("policy_adjustment")).get("delta_fields"),
        ),
        limit=8,
        max_len=80,
    )

    initial_summary = (
        f"1차 전략 프레임은 {route_selected or 'route 기록 없음'} 경로에서 {invocation or '호출 정보 없음'} 상태로 평가됐습니다."
    )
    if cache_used:
        initial_summary += " 기존 전략가 프레임 또는 캐시 후보군을 함께 확인했습니다."
    if cached_candidate_hints:
        initial_summary += f" 캐시/후보 힌트는 {', '.join(cached_candidate_hints[:5])}였습니다."

    if post_scanner_requested or refresh_requested:
        refresh_summary = (
            f"2차 refresh는 {refresh_reason or '사유 기록 없음'} 때문에 요청됐고"
            f", 대상 종목은 {selected_symbol or '기록 없음'}이었습니다."
        )
    else:
        refresh_summary = "2차 refresh 요청은 기록되지 않았습니다."
    if selected_in_cached_frame is not None:
        refresh_summary += f" 선택 종목의 캐시 프레임 포함 여부는 {bool(selected_in_cached_frame)}였습니다."
    if refresh_signal:
        refresh_summary += f" refresh signal은 {refresh_signal}입니다."

    if refresh_evaluated:
        if refresh_effective or policy_delta_count > 0 or policy_delta_fields:
            effect_summary = (
                f"최종 적용 결과 refresh가 정책에 반영됐고 delta count는 {policy_delta_count}입니다."
            )
        else:
            effect_summary = "최종 적용 결과 refresh는 평가됐지만 정책 delta가 없어 기존 프레임을 유지했습니다."
    else:
        effect_summary = "최종 적용 결과 refresh 평가 기록이 없어 기존 프레임 유지 여부만 확인 가능합니다."
    if policy_delta_fields:
        effect_summary += f" 변경 필드는 {', '.join(policy_delta_fields[:5])}입니다."

    raw_llm_trace = _dict(strategist_output.get("strategy_refresh_trace"))
    llm_interpretation = {}
    if raw_llm_trace:
        llm_interpretation = {
            "summary": _text(raw_llm_trace.get("summary"), max_len=320),
            "bullets": _list_text(raw_llm_trace.get("bullets"), limit=4, max_len=180),
            "source": "strategist_llm_output",
        }

    return {
        "schema_version": "strategy_refresh_trace.v1",
        "summary": f"{initial_summary} {refresh_summary} {effect_summary}",
        "stages": [
            {
                "stage": "initial_frame",
                "label": "1차 전략 프레임",
                "invocation": invocation,
                "route_selected": route_selected,
                "cache_used": cache_used,
                "candidate_hints": cached_candidate_hints,
                "summary": initial_summary,
            },
            {
                "stage": "post_scanner_refresh",
                "label": "2차 후보 확정 후 refresh",
                "requested": bool(post_scanner_requested or refresh_requested),
                "reason": refresh_reason,
                "selected_symbol": selected_symbol,
                "selected_symbol_in_cached_frame": selected_in_cached_frame,
                "refresh_signal": refresh_signal,
                "summary": refresh_summary,
            },
            {
                "stage": "final_application",
                "label": "최종 적용 결과",
                "evaluated": refresh_evaluated,
                "effective": refresh_effective,
                "policy_delta_count": policy_delta_count,
                "policy_delta_fields": policy_delta_fields,
                "summary": effect_summary,
            },
        ],
        "refresh_requested": bool(post_scanner_requested or refresh_requested),
        "refresh_effective": refresh_effective,
        "policy_delta_count": policy_delta_count,
        "policy_delta_fields": policy_delta_fields,
        "source": "commander_context_ref+commander_decision",
        "llm_interpretation": llm_interpretation,
    }


def build_scanner_handoff(*, strategist_output: Dict[str, Any]) -> Dict[str, Any]:
    priority = _list_text(strategist_output.get("scanner_priority"), limit=6, max_len=80)
    themes = _list_text(strategist_output.get("themes"), limit=4, max_len=80)
    avoid = _list_text(strategist_output.get("avoid_themes"), limit=5, max_len=80)
    prefer = priority[:]
    for theme in themes[:2]:
        prefer.append(f"theme_alignment:{theme}")
    if not prefer:
        prefer = ["liquidity", "tape_confirmation"]
    penalize = avoid[:] or ["extended_move_without_confirmation", "news_only_momentum"]
    return {
        "prefer_candidate_traits": prefer[:6],
        "penalize_traits": penalize[:6],
        "disqualifiers": ["risk_policy_block", "insufficient_liquidity"],
        "ranking_guidance": "Rank candidates by strategist frame fit, tape confirmation, and risk policy alignment.",
        "not_responsible_for": ["final_symbol_selection", "final_candidate_rank"],
    }


def build_monitor_handoff(*, strategist_output: Dict[str, Any]) -> Dict[str, Any]:
    policy = _dict(strategist_output.get("monitor_entry_policy"))
    threshold = _dict(policy.get("threshold_policy")) or policy
    confirmations = []
    if threshold.get("require_vwap_reclaim") is not False:
        confirmations.append("VWAP reclaim")
    if threshold.get("require_rebound") is not False:
        confirmations.append("rebound confirmation")
    if threshold.get("volume_ratio_min") not in (None, ""):
        confirmations.append(f"volume_ratio >= {threshold.get('volume_ratio_min')}")
    if not confirmations:
        confirmations = ["monitor confirmation"]
    return {
        "entry_confirmation": confirmations[:6],
        "hold_off_conditions": ["too_extended_from_vwap", "breakout_without_volume", "risk_policy_block"],
        "entry_aggressiveness": _text(strategist_output.get("trade_aggressiveness"), max_len=40) or "medium",
        "recheck_interval_reason": "Wait for monitor confirmation before entry.",
        "policy_effect_summary": "Entry is conditional on monitor gate confirmation.",
    }


def build_conflict_analysis(
    *,
    strategist_output: Dict[str, Any],
    memory_usage_trace: Dict[str, Any],
    news_usage_trace: Dict[str, Any],
) -> Dict[str, Any]:
    bullish: List[str] = []
    bearish: List[str] = []
    if _text(strategist_output.get("market_regime"), max_len=40) == "risk_on":
        bullish.append("market_regime=risk_on")
    if _text(strategist_output.get("market_sentiment"), max_len=40) == "bullish":
        bullish.append("market_sentiment=bullish")
    if _list(strategist_output.get("themes")):
        bullish.append("theme candidates available")
    if _text(strategist_output.get("risk_tone"), max_len=40) == "conservative":
        bearish.append("risk_tone=conservative")
    if _text(strategist_output.get("monitor_guidance"), max_len=60) == "defensive_exit":
        bearish.append("monitor_guidance=defensive_exit")
    for layer, decision in _dict(memory_usage_trace.get("layer_decisions")).items():
        if isinstance(decision, dict) and decision.get("used") and "failure" in _text(decision.get("reason"), max_len=200).lower():
            bearish.append(f"{layer}_memory_failure_pattern")
    if "risk-off" in _text(news_usage_trace.get("market_effect"), max_len=120):
        bearish.append("news_risk_off_pressure")
    if not bullish:
        bullish.append("candidate search may continue if scanner finds confirmation")
    if not bearish:
        bearish.append("no major bearish conflict captured")
    return {
        "bullish_evidence": bullish[:6],
        "bearish_evidence": bearish[:6],
        "resolution": "Allow scanner ranking, but leave entry permission to monitor confirmation.",
        "confidence": news_usage_trace.get("confidence") or "medium",
        "evidence_refs": ["news_usage_trace", "memory_usage_trace"],
    }


def build_trade_permission_frame(*, strategist_output: Dict[str, Any], monitor_handoff: Dict[str, Any]) -> Dict[str, Any]:
    risk_tone = _text(strategist_output.get("risk_tone"), max_len=40)
    monitor_guidance = _text(strategist_output.get("monitor_guidance"), max_len=60)
    blocked_code = _text(strategist_output.get("commander_no_trade_reason_code"), max_len=80)
    if blocked_code:
        permission = "blocked"
    elif risk_tone == "conservative" or monitor_guidance == "defensive_exit":
        permission = "defensive"
    else:
        permission = "conditional"
    return {
        "candidate_search_allowed": permission != "blocked",
        "entry_allowed_if": _list_text(monitor_handoff.get("entry_confirmation"), limit=6, max_len=100),
        "entry_blocked_if": _list_text(monitor_handoff.get("hold_off_conditions"), limit=6, max_len=100),
        "reason": "Strategist permits only the strategy frame; scanner, monitor, supervisor, and executor still own downstream gates.",
        "permission_level": permission,
    }


def build_responsibility_boundary() -> Dict[str, Any]:
    return {
        "strategist_owns": ["market_regime", "risk_posture", "playbook", "scanner_guidance", "monitor_guidance"],
        "scanner_owns": ["candidate_ranking", "selected_symbol"],
        "monitor_owns": ["entry_condition_check", "hold_off_reason", "exit_trigger_observation"],
        "executor_supervisor_owns": ["order_permission", "broker_execution", "fill_confirmation"],
        "not_responsible_for": ["final_symbol_selection", "order_execution"],
    }


def build_strategist_explanation_fields(
    *,
    strategist_output: Dict[str, Any],
    state: Dict[str, Any] | None = None,
    news_evidence_ranked: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    base = dict(strategist_output or {})
    # Memory/news usage are deterministic-first. The LLM may improve wording,
    # but it must not invent active layers, gates, or evidence linkage.
    memory_usage_trace = build_memory_usage_trace(
        strategist_output=base,
        state=state,
    )
    raw_memory_usage = _dict(base.get("memory_usage_trace"))
    if _text(raw_memory_usage.get("human_summary"), max_len=400):
        memory_usage_trace["human_summary"] = _text(raw_memory_usage.get("human_summary"), max_len=400)

    news_usage_trace = build_news_usage_trace(
        strategist_output=base,
        news_evidence_ranked=news_evidence_ranked,
    )
    raw_news_usage = _dict(base.get("news_usage_trace"))
    if _text(raw_news_usage.get("human_summary"), max_len=400):
        news_usage_trace["human_summary"] = _text(raw_news_usage.get("human_summary"), max_len=400)

    strategy_thesis = build_strategy_thesis(strategist_output=base)
    strategy_thesis.update(_dict(base.get("strategy_thesis")))
    strategy_delta_trace = build_strategy_delta_trace(strategist_output=base, state=state)
    strategy_delta_trace.update(_dict(base.get("strategy_delta_trace")))
    strategy_refresh_trace = build_strategy_refresh_trace(strategist_output=base, state=state)
    scanner_handoff = build_scanner_handoff(strategist_output=base)
    scanner_handoff.update(_dict(base.get("scanner_handoff")))
    monitor_handoff = build_monitor_handoff(strategist_output=base)
    monitor_handoff.update(_dict(base.get("monitor_handoff")))
    conflict_analysis = build_conflict_analysis(
        strategist_output=base,
        memory_usage_trace=memory_usage_trace,
        news_usage_trace=news_usage_trace,
    )
    conflict_analysis.update(_dict(base.get("conflict_analysis")))
    trade_permission_frame = build_trade_permission_frame(strategist_output=base, monitor_handoff=monitor_handoff)
    trade_permission_frame.update(_dict(base.get("trade_permission_frame")))
    responsibility_boundary = build_responsibility_boundary()
    responsibility_boundary.update(_dict(base.get("responsibility_boundary")))
    return {
        "strategy_thesis": strategy_thesis,
        "strategy_delta_trace": strategy_delta_trace,
        "strategy_refresh_trace": strategy_refresh_trace,
        "memory_usage_trace": memory_usage_trace,
        "news_usage_trace": news_usage_trace,
        "scanner_handoff": scanner_handoff,
        "monitor_handoff": monitor_handoff,
        "conflict_analysis": conflict_analysis,
        "trade_permission_frame": trade_permission_frame,
        "responsibility_boundary": responsibility_boundary,
    }


__all__ = [
    "build_conflict_analysis",
    "build_memory_usage_trace",
    "build_monitor_handoff",
    "build_news_usage_trace",
    "build_responsibility_boundary",
    "build_scanner_handoff",
    "build_strategist_explanation_fields",
    "build_strategy_refresh_trace",
    "build_strategy_delta_trace",
    "build_strategy_thesis",
    "build_trade_permission_frame",
]
