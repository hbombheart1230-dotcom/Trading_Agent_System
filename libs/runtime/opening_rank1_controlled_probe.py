from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from libs.runtime.opening_rank1_probe_cost_edge import evaluate_opening_probe_cost_edge


SCHEMA_VERSION = "opening_rank1_controlled_probe.v2"
KST = ZoneInfo("Asia/Seoul")
ALLOWED_SETUP_TYPES = frozenset({"DIRECTIONAL_BREADTH", "FRESH_CHANGE_ACTIVATION"})
OVERRIDABLE_WAIT_REASONS = frozenset(
    {
        "below_vwap_reclaim_not_ready",
        "breakout_not_ready",
        "pullback_below_vwap_reclaim_not_ready",
        "pullback_not_mature",
        "volume_confirmation_missing",
        "volume_insufficient",
        "vwap_reclaim_not_ready",
    }
)
OVERRIDABLE_QUANT_BLOCKERS = frozenset(
    {
        "volume_confirmation_missing",
        "vwap_pullback_promoted_quality_gate",
    }
)
FALLBACK_COST_QUANT_BLOCKERS = frozenset(
    {
        "cost_edge_fail",
        "directional_edge_evidence_missing",
    }
)
DEFAULT_LEDGER_ROOT = Path("data/logs/opening_rank1_controlled_probe")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _is_enabled(value: Any = None) -> bool:
    raw = _text(
        value
        if value is not None
        else os.getenv("OPENING_RANK1_CONTROLLED_PROBE_ENABLED", "true")
    ).lower()
    return raw not in {"0", "false", "no", "off", "disabled"}


def selected_rank(candidate: Mapping[str, Any] | None) -> int:
    row = candidate or {}
    for key in ("rank", "priority_rank", "scanner_rank", "selected_rank"):
        rank = _to_int(row.get(key))
        if rank > 0:
            return rank
    return 0


def classify_candidate_setup(candidate: Mapping[str, Any] | None) -> str:
    row = candidate or {}
    explicit = _text(row.get("candidate_setup") or row.get("setup_type")).upper()
    if explicit:
        return explicit

    sources = {
        _text(item).lower()
        for item in list(row.get("sources") or [])
        if _text(item)
    }
    if "top_change_rate" in sources:
        return "FRESH_CHANGE_ACTIVATION"

    breakdown = row.get("score_breakdown")
    breakdown = breakdown if isinstance(breakdown, Mapping) else {}
    directional_keys = (
        "momentum",
        "trend",
        "ma_alignment",
        "adx_trend",
        "volume_surge",
        "intraday_strength",
        "theme_boost",
    )
    directional_count = sum(_to_float(breakdown.get(key)) > 0.0 for key in directional_keys)
    if directional_count >= 4:
        return "DIRECTIONAL_BREADTH"
    if sources and sources.issubset({"top_value", "top_volume"}):
        return "LIQUIDITY_ONLY"
    return "UNCLASSIFIED"


def session_clock(now_epoch: int) -> tuple[str, int]:
    current = datetime.fromtimestamp(int(now_epoch), tz=KST)
    minutes = (current.hour * 60 + current.minute) - (9 * 60)
    return current.date().isoformat(), int(minutes)


def _wait_reason_is_overrideable(reason: str) -> bool:
    normalized = _text(reason).lower()
    if normalized in OVERRIDABLE_WAIT_REASONS:
        return True
    return any(item in normalized.split(",") for item in OVERRIDABLE_WAIT_REASONS)


def _probe_qty(normal_qty: int, qty_fraction: float) -> int:
    qty = max(0, int(normal_qty))
    if qty <= 0:
        return 0
    return max(1, min(qty, int(math.floor(qty * max(0.0, qty_fraction)))))


def evaluate_opening_rank1_controlled_probe(
    *,
    selected: Mapping[str, Any] | None,
    entry_info: Mapping[str, Any] | None,
    original_wait_reason: str,
    base_entry_guard_blocked: bool,
    base_entry_guard_reason: str,
    entry_quality_gate: Mapping[str, Any] | None,
    entry_cost_filter: Mapping[str, Any] | None,
    quant_entry_enforcement: Mapping[str, Any] | None,
    risk_off_policy: Mapping[str, Any] | None,
    selection_authority: Mapping[str, Any] | None,
    now_epoch: int,
    normal_qty: int,
    prior_probe_count: int,
    is_top_pick: bool,
    same_symbol_reentry_detected: bool,
    broker_mode: str,
    enabled: Any = None,
    opening_end_minute: int = 20,
    qty_fraction: float = 0.25,
) -> dict[str, Any]:
    candidate = dict(selected or {})
    entry = dict(entry_info or {})
    quality = dict(entry_quality_gate or {})
    cost = dict(entry_cost_filter or {})
    enforcement = dict(quant_entry_enforcement or {})
    risk_off = dict(risk_off_policy or {})
    authority = dict(selection_authority or {})
    day, minutes_since_open = session_clock(now_epoch)
    rank = selected_rank(candidate)
    setup = classify_candidate_setup(candidate)
    matched_quant_blockers = [
        _text(item) for item in list(enforcement.get("matched_blockers") or []) if _text(item)
    ]
    quality_reasons = [_text(item) for item in list(quality.get("reasons") or []) if _text(item)]
    probe_qty = _probe_qty(normal_qty, qty_fraction)
    probe_cost_edge = evaluate_opening_probe_cost_edge(
        candidate_setup=setup,
        entry_cost_filter=cost,
    )

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "enabled": _is_enabled(enabled),
        "behavior_effect": "controlled_mock_entry_probe",
        "evaluated": True,
        "eligible": False,
        "applied": False,
        "reason": "",
        "day": day,
        "minutes_since_open": minutes_since_open,
        "opening_end_minute": int(opening_end_minute),
        "symbol": _text(candidate.get("symbol")),
        "scanner_rank": int(rank),
        "candidate_setup": setup,
        "allowed_setup_types": sorted(ALLOWED_SETUP_TYPES),
        "original_wait_reason": _text(original_wait_reason),
        "base_entry_guard_reason": _text(base_entry_guard_reason),
        "matched_quant_blockers": matched_quant_blockers,
        "entry_quality_reasons": quality_reasons,
        "selection_authority": authority,
        "cost_edge_evidence": dict(probe_cost_edge),
        "normal_qty": max(0, int(normal_qty)),
        "probe_qty": int(probe_qty),
        "qty_fraction_target": float(qty_fraction),
        "qty_fraction_effective": (
            round(float(probe_qty) / float(normal_qty), 6) if int(normal_qty) > 0 else 0.0
        ),
        "prior_probe_count": max(0, int(prior_probe_count)),
        "max_daily_probes": 1,
        "safety_contract": {
            "mock_only": True,
            "cost_filter_required": True,
            "missing_cost_evidence_fallback_bounded": True,
            "intrinsic_rank1_symbol_alignment_required": True,
            "chart_hard_floor_required": True,
            "risk_off_block_preserved": True,
            "position_and_order_guards_preserved": True,
            "same_lane_reentry_allowed": False,
            "exit_policy_unchanged": True,
        },
    }

    def reject(reason: str) -> dict[str, Any]:
        result["reason"] = reason
        return result

    if not result["enabled"]:
        return reject("probe_disabled")
    if _text(broker_mode).lower() != "mock":
        return reject("mock_broker_required")
    if not is_top_pick:
        return reject("top_pick_only")
    if rank != 1:
        return reject("scanner_rank1_required")
    if not bool(authority.get("evidence_available")):
        return reject("intrinsic_rank1_evidence_missing")
    if not bool(authority.get("aligned")):
        return reject("intrinsic_rank1_symbol_mismatch")
    if minutes_since_open < 0 or minutes_since_open > int(opening_end_minute):
        return reject("outside_opening_window")
    if setup not in ALLOWED_SETUP_TYPES:
        return reject("candidate_setup_not_allowed")
    if same_symbol_reentry_detected:
        return reject("same_symbol_reentry_not_allowed")
    if int(prior_probe_count) >= 1:
        return reject("daily_probe_limit_reached")
    if probe_qty <= 0:
        return reject("probe_qty_not_available")
    if bool(risk_off.get("blocked")):
        return reject("risk_off_policy_blocked")
    if quality_reasons:
        return reject("entry_quality_hard_floor_not_met")
    if not bool(probe_cost_edge.get("passed")):
        return reject("cost_adjusted_edge_not_ready")
    fallback_cost_edge_applied = bool(probe_cost_edge.get("fallback_applied"))
    if bool(base_entry_guard_blocked) and not (
        fallback_cost_edge_applied
        and _text(base_entry_guard_reason) == "cost_adjusted_edge_not_ready"
    ):
        return reject(_text(base_entry_guard_reason) or "base_entry_guard_blocked")
    effective_overrideable_quant_blockers = set(OVERRIDABLE_QUANT_BLOCKERS)
    if fallback_cost_edge_applied:
        effective_overrideable_quant_blockers.update(FALLBACK_COST_QUANT_BLOCKERS)
    if any(item not in effective_overrideable_quant_blockers for item in matched_quant_blockers):
        return reject("non_overrideable_quant_blocker")
    if bool(entry.get("triggered")):
        if not bool(enforcement.get("blocked")):
            return reject("normal_entry_ready")
        if not matched_quant_blockers:
            return reject("quant_blocker_evidence_missing")
    elif not _wait_reason_is_overrideable(original_wait_reason):
        return reject("wait_reason_not_overrideable")

    result["eligible"] = True
    result["applied"] = True
    result["reason"] = "opening_rank1_controlled_probe_applied"
    result["overridden_wait_reason"] = _text(original_wait_reason)
    result["overridden_quant_blockers"] = matched_quant_blockers
    result["overridden_base_guard_reason"] = (
        _text(base_entry_guard_reason)
        if fallback_cost_edge_applied
        and _text(base_entry_guard_reason) == "cost_adjusted_edge_not_ready"
        else ""
    )
    return result


def ledger_path(day: str, *, root: Path | str | None = None) -> Path:
    base = Path(root or os.getenv("OPENING_RANK1_CONTROLLED_PROBE_LOG_ROOT") or DEFAULT_LEDGER_ROOT)
    return base / _text(day) / "probe_submissions.json"


def load_probe_submissions(day: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    path = ledger_path(day, root=root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("submissions") if isinstance(payload, Mapping) else []
    return [dict(row) for row in list(rows or []) if isinstance(row, Mapping)]


def record_probe_submission(
    decision: Mapping[str, Any],
    *,
    run_id: str,
    recorded_at: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    day = _text(decision.get("day"))
    path = ledger_path(day, root=root)
    rows = load_probe_submissions(day, root=root)
    if rows:
        return {
            "recorded": False,
            "reason": "daily_probe_limit_reached",
            "path": str(path),
            "count": len(rows),
        }

    row = {
        "schema_version": SCHEMA_VERSION,
        "run_id": _text(run_id),
        "recorded_at": _text(recorded_at),
        "symbol": _text(decision.get("symbol")),
        "scanner_rank": _to_int(decision.get("scanner_rank")),
        "candidate_setup": _text(decision.get("candidate_setup")),
        "probe_qty": _to_int(decision.get("probe_qty")),
        "original_wait_reason": _text(decision.get("original_wait_reason")),
        "overridden_quant_blockers": list(decision.get("overridden_quant_blockers") or []),
        "cost_edge_evidence": dict(decision.get("cost_edge_evidence") or {}),
        "selection_authority": dict(decision.get("selection_authority") or {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "day": day,
        "submissions": [row],
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return {"recorded": True, "reason": "recorded", "path": str(path), "count": 1, "row": row}


__all__ = [
    "ALLOWED_SETUP_TYPES",
    "FALLBACK_COST_QUANT_BLOCKERS",
    "OVERRIDABLE_QUANT_BLOCKERS",
    "OVERRIDABLE_WAIT_REASONS",
    "SCHEMA_VERSION",
    "classify_candidate_setup",
    "evaluate_opening_rank1_controlled_probe",
    "ledger_path",
    "load_probe_submissions",
    "record_probe_submission",
    "selected_rank",
    "session_clock",
]
