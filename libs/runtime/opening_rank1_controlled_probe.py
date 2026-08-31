from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from libs.runtime.opening_rank1_probe_cost_edge import evaluate_opening_probe_cost_edge
from libs.core.path_isolation import resolve_runtime_write_path


SCHEMA_VERSION = "opening_rank1_controlled_probe.v3"
KST = ZoneInfo("Asia/Seoul")
ALLOWED_LANE_CONDITIONS = frozenset(
    {"HIGH_COMMON_DIRECTIONAL", "CONFIRMED_RECURRENT_RANK"}
)
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
DEFAULT_OBSERVATION_ROOT = Path("data/logs/opening_alpha_rank_observations")


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


def effective_selected_rank(
    candidate: Mapping[str, Any] | None,
    selection_authority: Mapping[str, Any] | None,
) -> tuple[int, str]:
    candidate_rank = selected_rank(candidate)
    if candidate_rank > 0:
        return candidate_rank, "selected_candidate"

    authority = selection_authority or {}
    authority_rank = _to_int(authority.get("intrinsic_rank1_rank"))
    if (
        bool(authority.get("evidence_available"))
        and bool(authority.get("aligned"))
        and authority_rank == 1
    ):
        return authority_rank, "scanner_authority_intrinsic_rank1"
    return 0, "missing"


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


def _asset_class(candidate: Mapping[str, Any]) -> str:
    compact = candidate.get("compact_feature_snapshot")
    compact = compact if isinstance(compact, Mapping) else {}
    return _text(
        candidate.get("asset_class_detected")
        or candidate.get("asset_class")
        or compact.get("asset_class_detected")
        or compact.get("asset_class")
    ).lower()


def _risk_band(candidate: Mapping[str, Any]) -> tuple[str, float]:
    explicit = _text(candidate.get("risk_band")).upper()
    risk_score = _to_float(candidate.get("risk_score"))
    if explicit:
        return explicit, risk_score
    if risk_score >= 0.7:
        return "HIGH", risk_score
    if risk_score >= 0.4:
        return "MEDIUM", risk_score
    return "LOW", risk_score


def _completed_return_1m_pct(rows: list[Mapping[str, Any]] | None) -> float | None:
    usable = [row for row in list(rows or []) if _to_float(row.get("close")) > 0.0]
    if len(usable) < 2:
        return None
    previous = _to_float(usable[-2].get("close"))
    current = _to_float(usable[-1].get("close"))
    if previous <= 0.0:
        return None
    return round((current / previous - 1.0) * 100.0, 6)


def rank_observation_path(day: str, *, root: Path | str | None = None) -> Path:
    base = resolve_runtime_write_path(
        root
        or os.getenv("OPENING_ALPHA_RANK_OBSERVATION_ROOT")
        or DEFAULT_OBSERVATION_ROOT
    )
    return base / _text(day) / "rank1_observations.json"


def load_rank_observations(
    day: str, *, root: Path | str | None = None
) -> list[dict[str, Any]]:
    path = rank_observation_path(day, root=root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("observations") if isinstance(payload, Mapping) else []
    return [dict(row) for row in list(rows or []) if isinstance(row, Mapping)]


def record_rank1_observation(
    *,
    day: str,
    symbol: str,
    observed_epoch: int,
    run_id: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    path = rank_observation_path(day, root=root)
    rows = load_rank_observations(day, root=root)
    key = (_text(symbol), int(observed_epoch))
    if key[0] and not any(
        (_text(row.get("symbol")), _to_int(row.get("observed_epoch"))) == key
        for row in rows
    ):
        rows.append(
            {
                "symbol": key[0],
                "observed_epoch": key[1],
                "run_id": _text(run_id),
            }
        )
    rows = sorted(rows, key=lambda row: _to_int(row.get("observed_epoch")))[-500:]
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "opening_alpha_rank_observations.v1",
        "day": _text(day),
        "observations": rows,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    temporary.replace(path)
    return {"recorded": True, "path": str(path), "count": len(rows)}


def classify_opening_alpha_condition(
    *,
    candidate: Mapping[str, Any] | None,
    now_epoch: int,
    prior_rank_observations: list[Mapping[str, Any]] | None,
    recent_minute_rows: list[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    row = dict(candidate or {})
    symbol = _text(row.get("symbol"))
    setup = classify_candidate_setup(row)
    asset_class = _asset_class(row)
    risk_band, risk_score = _risk_band(row)
    return_1m = _completed_return_1m_pct(recent_minute_rows)
    prior_same_symbol = [
        item
        for item in list(prior_rank_observations or [])
        if _text(item.get("symbol")) == symbol
        and 0 < int(now_epoch) - _to_int(item.get("observed_epoch")) <= 300
    ]
    high_common_directional = bool(
        asset_class == "common_stock"
        and risk_band == "HIGH"
        and setup == "DIRECTIONAL_BREADTH"
    )
    confirmed_recurrent = bool(
        prior_same_symbol and return_1m is not None and return_1m > 0.0
    )
    condition = (
        "HIGH_COMMON_DIRECTIONAL"
        if high_common_directional
        else "CONFIRMED_RECURRENT_RANK"
        if confirmed_recurrent
        else ""
    )
    return {
        "eligible": bool(condition),
        "condition": condition,
        "asset_class": asset_class or "unknown",
        "risk_band": risk_band,
        "risk_score": risk_score,
        "candidate_setup": setup,
        "prior_rank1_observations_5m": len(prior_same_symbol),
        "completed_return_1m_pct": return_1m,
        "conditions": {
            "HIGH_COMMON_DIRECTIONAL": high_common_directional,
            "CONFIRMED_RECURRENT_RANK": confirmed_recurrent,
        },
    }


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
    prior_rank_observations: list[Mapping[str, Any]] | None = None,
    recent_minute_rows: list[Mapping[str, Any]] | None = None,
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
    rank, rank_source = effective_selected_rank(candidate, authority)
    setup = classify_candidate_setup(candidate)
    alpha_condition = classify_opening_alpha_condition(
        candidate=candidate,
        now_epoch=now_epoch,
        prior_rank_observations=prior_rank_observations,
        recent_minute_rows=recent_minute_rows,
    )
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
        "scanner_rank_source": rank_source,
        "candidate_setup": setup,
        "opening_alpha_condition": dict(alpha_condition),
        "allowed_lane_conditions": sorted(ALLOWED_LANE_CONDITIONS),
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
    if not bool(alpha_condition.get("eligible")):
        return reject("opening_alpha_condition_not_allowed")
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
    base = resolve_runtime_write_path(root or os.getenv("OPENING_RANK1_CONTROLLED_PROBE_LOG_ROOT") or DEFAULT_LEDGER_ROOT)
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
        "opening_alpha_condition": dict(decision.get("opening_alpha_condition") or {}),
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
    "ALLOWED_LANE_CONDITIONS",
    "FALLBACK_COST_QUANT_BLOCKERS",
    "OVERRIDABLE_QUANT_BLOCKERS",
    "OVERRIDABLE_WAIT_REASONS",
    "SCHEMA_VERSION",
    "classify_candidate_setup",
    "classify_opening_alpha_condition",
    "evaluate_opening_rank1_controlled_probe",
    "effective_selected_rank",
    "ledger_path",
    "load_probe_submissions",
    "load_rank_observations",
    "rank_observation_path",
    "record_rank1_observation",
    "record_probe_submission",
    "selected_rank",
    "session_clock",
]
