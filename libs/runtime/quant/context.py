from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict

from libs.runtime.quant.factors import build_factor_snapshot_from_candidate
from libs.runtime.quant.memory import load_quant_memory_packet
from libs.runtime.quant.scorecard import build_quant_scorecard, compact_scorecard_for_llm
from libs.core.path_isolation import isolate_canonical_path_for_pytest


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _iso_day(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return text[:10] if len(text) >= 10 else ""


def _resolve_day(payload: Dict[str, Any]) -> str:
    for key in ("day", "trade_day", "session_day", "started_at", "now_iso", "tick_ts", "ts"):
        day = _iso_day(payload.get(key))
        if day:
            return day
    return datetime.now(timezone.utc).date().isoformat()


def _weekly_period_key(day: str) -> str:
    try:
        parsed = date.fromisoformat(str(day)[:10])
    except Exception:
        parsed = datetime.now(timezone.utc).date()
    iso_year, iso_week, _weekday = parsed.isocalendar()
    return f"{int(iso_year):04d}-W{int(iso_week):02d}"


def _candidate_tactic_id(row: Dict[str, Any]) -> str:
    snapshot = _mapping(row.get("quant_factor_snapshot"))
    suitability = _mapping(row.get("tactic_suitability"))
    for value in (
        snapshot.get("tactic_id"),
        suitability.get("tactic_id"),
        row.get("tactic_id"),
        row.get("tactical_strategy"),
    ):
        text = _text(value)
        if text:
            return text
    return ""


def _candidate_playbook(row: Dict[str, Any]) -> str:
    for value in (row.get("playbook"), row.get("strategy_playbook"), row.get("scanner_playbook")):
        text = _text(value)
        if text:
            return text
    return ""


def _candidate_has_snapshot_evidence(row: Dict[str, Any]) -> bool:
    if not _text(row.get("symbol")):
        return False
    evidence_keys = (
        "score_total",
        "score",
        "confidence",
        "risk_score",
        "entry_compatibility_score",
        "scanner_chart_fit_score",
        "scanner_macro_chart_fit_score",
        "dominant_block_reason",
        "expected_monitor_block_reason",
    )
    if any(row.get(key) not in (None, "", {}, []) for key in evidence_keys):
        return True
    return any(isinstance(row.get(key), dict) and row.get(key) for key in ("features", "components", "score_breakdown"))


def _snapshot_from_candidate(row: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _mapping(row.get("quant_factor_snapshot"))
    if snapshot:
        return snapshot
    if not _candidate_has_snapshot_evidence(row):
        return {}
    return build_factor_snapshot_from_candidate(
        row,
        tactic_id=_candidate_tactic_id(row),
        playbook=_candidate_playbook(row),
    )


def _candidate_quant_snapshot(context: Dict[str, Any], payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    roots = [context]
    if isinstance(payload, dict):
        roots.append(payload)
    for key in ("actual_selected_candidate", "scanner_primary_candidate", "scanner_rank1_candidate"):
        for root in roots:
            row = _mapping(root.get(key))
            snapshot = _snapshot_from_candidate(row)
            if snapshot:
                return snapshot
    for root in roots:
        for row in list(root.get("scanner_top_candidates") or [])[:4]:
            if isinstance(row, dict):
                snapshot = _snapshot_from_candidate(dict(row))
                if snapshot:
                    return snapshot
    return {}


def _hold_context(payload: Dict[str, Any], commander_refresh_context: Dict[str, Any]) -> Dict[str, Any]:
    position = _mapping(commander_refresh_context.get("current_position"))
    if not position:
        position = _mapping(payload.get("current_position"))
    monitor = _mapping(payload.get("monitor_output"))
    monitor_entry = _mapping(payload.get("monitor_entry"))
    return {
        "schema_version": "quant_hold_context.v1",
        "symbol": _text(
            commander_refresh_context.get("selected_symbol")
            or position.get("symbol")
            or monitor.get("selected_symbol")
        ),
        "current_position": position,
        "monitor_reason": _text(commander_refresh_context.get("monitor_reason") or monitor.get("entry_exit_reason")),
        "active_exit_axis": _text(commander_refresh_context.get("active_exit_axis")),
        "entry_factor_snapshot": _mapping(monitor_entry.get("quant_factor_snapshot")),
        "behavior_effect": "observation_only",
    }


def _carry_context(payload: Dict[str, Any], commander_refresh_context: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": "quant_carry_context.v1",
        "selected_symbol": _text(commander_refresh_context.get("selected_symbol")),
        "current_position": _mapping(commander_refresh_context.get("current_position") or payload.get("current_position")),
        "open_positions": list(payload.get("positions") or payload.get("open_positions") or [])[:8],
        "post_exit_shadow": _mapping(payload.get("post_exit_shadow")),
        "behavior_effect": "observation_only",
    }


def build_strategist_quant_context(
    payload: Dict[str, Any],
    *,
    call_kind: str,
    memory_usage_disabled: bool = False,
) -> Dict[str, Any]:
    src = dict(payload or {})
    day = _resolve_day(src)
    explicit_reports_root = bool(_text(src.get("reports_root")))
    reports_root = isolate_canonical_path_for_pytest(
        _text(src.get("reports_root")) or "reports", canonical_path="reports", isolated_name="reports"
    )
    period_key = _text(src.get("quant_period_key") or src.get("weekly_period_key")) or _weekly_period_key(day)
    period_type = _text(src.get("quant_period_type")) or "weekly"
    commander_refresh_context = _mapping(src.get("commander_refresh_context"))

    scorecard: Dict[str, Any]
    if memory_usage_disabled:
        scorecard = {
            "schema_version": "quant_scorecard_compact.v1",
            "available": False,
            "visible_to_llm": False,
            "reason": "commander_memory_usage_disabled",
            "behavior_effect": "observation_only",
        }
    elif not explicit_reports_root and not _text(src.get("quant_period_key") or src.get("weekly_period_key")):
        scorecard = {
            "schema_version": "quant_scorecard_compact.v1",
            "available": False,
            "visible_to_llm": False,
            "reason": "reports_root_not_explicit",
            "behavior_effect": "observation_only",
        }
    else:
        packet = load_quant_memory_packet(
            reports_root=reports_root,
            period_type=period_type,
            period_key=period_key,
        )
        raw_scorecard = build_quant_scorecard(packet)
        scorecard = compact_scorecard_for_llm(raw_scorecard)
        scorecard["available"] = bool(packet.get("available"))
        scorecard["artifact_path"] = _text(packet.get("artifact_path"))

    context = {
        "schema_version": "strategist_quant_context.v1",
        "call_kind": _text(call_kind) or "market_strategy_frame",
        "day": day,
        "period_type": period_type,
        "period_key": period_key,
        "quant_market_context": {
            "schema_version": "quant_market_context.v1",
            "scorecard": scorecard,
            "behavior_effect": "observation_only",
        },
        "behavior_effect": "observation_only",
    }

    if call_kind == "selected_symbol_tactical_refresh":
        context["selected_symbol_quant_snapshot"] = _candidate_quant_snapshot(commander_refresh_context, src)
    elif call_kind == "stale_intraday_hold_review":
        context["hold_quant_context"] = _hold_context(src, commander_refresh_context)
    elif call_kind == "end_of_day_carry_review":
        context["carry_quant_context"] = _carry_context(src, commander_refresh_context)
    return context
