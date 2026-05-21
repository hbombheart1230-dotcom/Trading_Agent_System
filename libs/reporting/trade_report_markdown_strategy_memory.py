from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List


def strategy_horizon_label(value: Any, *, metadata_value: Callable[[Any], str]) -> str:
    raw = str(value or "").strip()
    labels = {
        "scalp": "초단타(scalp)",
        "intraday": "단타/당일(intraday)",
        "overnight_probe": "오버나이트 탐색(overnight_probe)",
        "1_2day_swing": "1~2일 스윙(1_2day_swing)",
    }
    return labels.get(raw, metadata_value(raw) or "-")


def strategy_horizon_reason_label(value: Any, *, metadata_value: Callable[[Any], str]) -> str:
    raw = str(value or "").strip()
    labels = {
        "commander_accepts_strategist_horizon_proposal_observability_only": "전략가 제안을 관측-only로 수용",
        "commander_caps_long_horizon_during_live_validation_observability_only": "장기 보유 제안은 live validation 중이라 단타/당일로 제한",
        "commander_default_intraday_horizon_without_strategist_proposal": "전략가 보유 기간 제안 부재로 기본 단타/당일 적용",
    }
    return labels.get(raw, metadata_value(raw) or "-")


def strategy_horizon_alignment_label(value: Any, *, metadata_value: Callable[[Any], str]) -> str:
    raw = str(value or "").strip()
    labels = {
        "aligned": "전략 보유 구간과 충돌 없음",
        "early_but_justified": "전략 최소 보유 전 조기 청산이지만 하드 리스크로 정당화",
        "early_unproven": "전략 최소 보유 전 조기 청산, 근거 검증 필요",
        "held_beyond_expected_window": "기대 최대 보유시간 초과",
        "unknown": "판단 불가",
    }
    return labels.get(raw, metadata_value(raw) or "-")


def duration_label_compact(value: Any, *, num_opt: Callable[[Any], float | None]) -> str:
    seconds = num_opt(value)
    if seconds is None or seconds <= 0:
        return ""
    total = int(round(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    parts: List[str] = []
    if days:
        parts.append(f"{days}일")
    if hours:
        parts.append(f"{hours}시간")
    if minutes:
        parts.append(f"{minutes}분")
    if sec and not days:
        parts.append(f"{sec}초")
    if not parts:
        parts.append("0초")
    return " ".join(parts)


def hold_window_label(
    window: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
    duration_label_compact_fn: Callable[[Any], str],
) -> str:
    obj = as_dict(window)
    if not obj:
        return "-"
    min_label = duration_label_compact_fn(obj.get("min_sec")) or "-"
    target_label = duration_label_compact_fn(obj.get("target_sec")) or "-"
    max_label = duration_label_compact_fn(obj.get("max_sec")) or "-"
    return f"최소 {min_label} / 목표 {target_label} / 최대 {max_label}"


def strategy_horizon_report_surface(
    report: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
    first_report_path: Callable[[Dict[str, Any], Iterable[str]], Any],
    compact_post_exit_shadow: Callable[[Dict[str, Any]], Dict[str, Any]],
    post_exit_shadow_surface: Callable[[Dict[str, Any]], Dict[str, Any]],
    carryover_context: Callable[[Dict[str, Any]], Dict[str, Any]],
    num_opt: Callable[[Any], float | None],
    duration_label_compact_fn: Callable[[Any], str],
) -> Dict[str, Any]:
    def _first_non_empty(*values: Any) -> Any:
        for value in values:
            if value not in (None, "", [], {}):
                return value
        return ""

    def _first_dict(*values: Any) -> Dict[str, Any]:
        for value in values:
            obj = as_dict(value)
            if obj:
                return obj
        return {}

    exit_vs_strategy = _first_dict(
        report.get("exit_vs_strategy_intent"),
        first_report_path(
            report,
            [
                "monitor_snapshot.exit_vs_strategy_intent",
                "monitor_snapshot.decision_trace.exit_vs_strategy_intent",
                "fact_payload.trade.exit_vs_strategy_intent",
                "fact_payload.trade.monitor_snapshot.exit_vs_strategy_intent",
                "fact_payload.trade.canonical_agent_artifacts.monitor.exit_vs_strategy_intent",
                "fact_payload.trade.canonical_agent_artifacts.monitor.decision_trace.exit_vs_strategy_intent",
                "lifecycle.exit.monitor_context.exit_vs_strategy_intent",
                "lifecycle_bundle.exit_vs_strategy_intent",
            ],
        ),
    )
    commander_policy = _first_dict(
        report.get("commander_horizon_policy"),
        exit_vs_strategy.get("commander_horizon_policy"),
        first_report_path(
            report,
            [
                "strategy_policy.commander_horizon_policy",
                "strategy_policy.monitor_policy.commander_horizon_policy",
                "strategist_output.commander_horizon_policy",
                "fact_payload.trade.commander_horizon_policy",
                "fact_payload.trade.canonical_agent_artifacts.strategist.commander_horizon_policy",
                "fact_payload.trade.canonical_agent_artifacts.monitor.applied_policy.horizon",
                "fact_payload.trade.shared_facts.commander_route.applied_policy.horizon",
                "shared_facts.commander_route.applied_policy.horizon",
                "monitor_snapshot.applied_policy.horizon",
                "monitor_snapshot.decision_trace.applied_policy.horizon",
            ],
        ),
    )
    feedback = _first_dict(
        report.get("strategy_horizon_feedback"),
        report.get("strategist_horizon_proposal"),
        first_report_path(
            report,
            [
                "strategist_output.strategy_horizon_feedback",
                "strategy_policy.monitor_policy.strategy_horizon_feedback",
                "fact_payload.trade.strategy_horizon_feedback",
                "fact_payload.trade.canonical_agent_artifacts.strategist.strategy_horizon_feedback",
                "entry_summary.strategist_context.strategy_horizon_feedback",
            ],
        ),
    )
    proposal = _first_dict(
        commander_policy.get("strategist_horizon_proposal"),
        commander_policy.get("proposal"),
        exit_vs_strategy.get("strategist_horizon_proposal"),
        feedback,
    )
    shadow = compact_post_exit_shadow(post_exit_shadow_surface(report))
    carryover = carryover_context(report)

    strategist_horizon = _first_non_empty(
        commander_policy.get("source_strategy_horizon"),
        exit_vs_strategy.get("source_strategy_horizon"),
        proposal.get("strategy_horizon"),
        feedback.get("strategy_horizon"),
        shadow.get("source_strategy_horizon"),
        shadow.get("strategy_horizon"),
    )
    commander_horizon = _first_non_empty(
        commander_policy.get("strategy_horizon"),
        exit_vs_strategy.get("strategy_horizon"),
        report.get("strategy_horizon"),
        first_report_path(report, ["fact_payload.trade.strategy_horizon"]),
        shadow.get("strategy_horizon"),
        strategist_horizon,
    )
    expected_window = _first_dict(
        commander_policy.get("expected_hold_window"),
        exit_vs_strategy.get("expected_hold_window"),
        shadow.get("expected_hold_window"),
        feedback.get("expected_hold_window"),
        proposal.get("expected_hold_window"),
    )
    source_window = _first_dict(
        commander_policy.get("source_expected_hold_window"),
        exit_vs_strategy.get("source_expected_hold_window"),
        proposal.get("expected_hold_window"),
        feedback.get("expected_hold_window"),
        expected_window,
    )
    actual_hold_sec = num_opt(
        _first_non_empty(
            exit_vs_strategy.get("actual_hold_sec"),
            first_report_path(
                report,
                [
                    "fact_payload.trade.exit_vs_strategy_intent.actual_hold_sec",
                    "fact_payload.trade.canonical_agent_artifacts.monitor.exit_vs_strategy_intent.actual_hold_sec",
                    "fact_payload.trade.monitor_snapshot.exit_vs_strategy_intent.actual_hold_sec",
                    "monitor_snapshot.exit_vs_strategy_intent.actual_hold_sec",
                    "shared_facts.exit_vs_strategy_intent.actual_hold_sec",
                ],
            ),
            carryover.get("actual_hold_sec"),
        )
    )

    alignment = str(exit_vs_strategy.get("exit_alignment") or "").strip()
    if not alignment and actual_hold_sec is not None and expected_window:
        min_sec = num_opt(expected_window.get("min_sec")) or 0.0
        max_sec = num_opt(expected_window.get("max_sec")) or 0.0
        if min_sec > 0 and actual_hold_sec < min_sec:
            alignment = "early_unproven"
        elif max_sec > 0 and actual_hold_sec > max_sec:
            alignment = "held_beyond_expected_window"
        else:
            alignment = "aligned"

    if not any([strategist_horizon, commander_horizon, expected_window, exit_vs_strategy]):
        return {}
    allow_behavior_change = bool(commander_policy.get("allow_behavior_change", False))
    observability_only = bool(
        _first_non_empty(
            commander_policy.get("observability_only"),
            exit_vs_strategy.get("observability_only"),
            feedback.get("observability_only"),
            True,
        )
    )
    do_not_force_hold = bool(
        _first_non_empty(
            commander_policy.get("do_not_force_hold"),
            as_dict(commander_policy.get("monitor_handoff")).get("do_not_force_hold"),
            True,
        )
    )
    behavior_translation = _first_dict(
        commander_policy.get("behavior_translation"),
        exit_vs_strategy.get("behavior_translation"),
        feedback.get("behavior_translation"),
    )
    return {
        "strategist_horizon": strategist_horizon,
        "commander_horizon": commander_horizon,
        "expected_hold_window": expected_window,
        "source_expected_hold_window": source_window,
        "actual_hold_sec": actual_hold_sec,
        "actual_hold_label": duration_label_compact_fn(actual_hold_sec),
        "exit_alignment": alignment,
        "alignment_reason": str(exit_vs_strategy.get("alignment_reason") or "").strip(),
        "early_exit_flag": bool(exit_vs_strategy.get("early_exit_flag")) if exit_vs_strategy else bool(alignment == "early_unproven"),
        "hard_exit": bool(exit_vs_strategy.get("hard_exit")) if exit_vs_strategy else False,
        "hard_exit_reason": str(exit_vs_strategy.get("hard_exit_reason") or "").strip(),
        "exit_reason": str(exit_vs_strategy.get("exit_reason") or "").strip(),
        "horizon_owner": str(exit_vs_strategy.get("horizon_owner") or ("commander" if commander_policy else "strategist")),
        "observability_only": observability_only,
        "allow_behavior_change": allow_behavior_change,
        "allow_behavior_translation": bool(commander_policy.get("allow_behavior_translation") or behavior_translation),
        "behavior_translation": behavior_translation,
        "do_not_force_hold": do_not_force_hold,
        "decision_reason": str(commander_policy.get("decision_reason") or exit_vs_strategy.get("commander_decision_reason") or "").strip(),
    }


def build_strategy_horizon_lines(
    report: Dict[str, Any],
    *,
    compact: bool = False,
    strategy_horizon_report_surface_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    strategy_horizon_label_fn: Callable[[Any], str],
    strategy_horizon_alignment_label_fn: Callable[[Any], str],
    strategy_horizon_reason_label_fn: Callable[[Any], str],
    as_dict: Callable[[Any], Dict[str, Any]],
    axis_label: Callable[[Any], str],
    hold_window_label_fn: Callable[[Dict[str, Any]], str],
    duration_label_compact_fn: Callable[[Any], str],
) -> List[str]:
    surface = strategy_horizon_report_surface_fn(report)
    if not surface:
        return []
    lines: List[str] = []
    strategist = surface.get("strategist_horizon")
    commander = surface.get("commander_horizon")
    if strategist:
        lines.append(f"* 전략가 제안: {strategy_horizon_label_fn(strategist)}")
    if commander:
        lines.append(f"* 지휘관 적용: {strategy_horizon_label_fn(commander)}")
    authority = "행동 반영 허용" if surface.get("allow_behavior_change") else "관측-only"
    if surface.get("allow_behavior_translation"):
        authority += ", 보유기간 번역 반영"
    if surface.get("do_not_force_hold"):
        authority += ", 보유 강제 없음"
    lines.append(f"* 권한: {authority}")
    translation = as_dict(surface.get("behavior_translation"))
    if translation:
        pieces = [
            str(translation.get("scanner_scope_bias") or ""),
            str(translation.get("hold_control_bias") or ""),
            str(translation.get("exit_policy_bias") or ""),
        ]
        pieces = [item for item in pieces if item]
        if pieces:
            lines.append(f"* 실제 반영: {' / '.join(pieces[:3])}")
        if translation.get("monitor_review_cadence_sec") not in (None, ""):
            lines.append(f"* 모니터 리뷰 주기: {duration_label_compact_fn(translation.get('monitor_review_cadence_sec'))}")
    if surface.get("expected_hold_window"):
        lines.append(f"* 적용 예상 보유 구간: {hold_window_label_fn(as_dict(surface.get('expected_hold_window')))}")
    if not compact and surface.get("source_expected_hold_window") and surface.get("source_expected_hold_window") != surface.get("expected_hold_window"):
        lines.append(f"* 전략가 원 제안 구간: {hold_window_label_fn(as_dict(surface.get('source_expected_hold_window')))}")
    if surface.get("actual_hold_label"):
        lines.append(f"* 실제 보유: {surface.get('actual_hold_label')}")
    if surface.get("exit_alignment"):
        detail = strategy_horizon_alignment_label_fn(surface.get("exit_alignment"))
        if surface.get("hard_exit_reason"):
            detail += f" ({axis_label(surface.get('hard_exit_reason'))})"
        lines.append(f"* 청산 정합성: {detail}")
    reason = strategy_horizon_reason_label_fn(surface.get("decision_reason"))
    if reason and reason != "-":
        lines.append(f"* 지휘관 조정 사유: {reason}")
    if not compact:
        lines.append("* 해석: 이 값은 전략 의도와 실제 보유/청산을 비교하기 위한 기록이며, 현재는 모니터 청산을 강제로 지연시키지 않습니다.")
    return lines
