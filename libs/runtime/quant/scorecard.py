from __future__ import annotations

from typing import Any, Dict, List

from libs.runtime.quant.contracts import TacticScorecard
from libs.runtime.quant.tactics import canonical_tactic_key


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _confidence(sample_count: int) -> str:
    if sample_count >= 20:
        return "high"
    if sample_count >= 8:
        return "medium"
    return "low"


def _loss_cluster_names(rows: List[Dict[str, Any]], *, limit: int = 4) -> List[str]:
    clusters: List[str] = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        count = _to_int(row.get("closed_or_realized_count") or row.get("count"))
        win_rate = _to_float(row.get("win_rate"))
        avg_return = _to_float(row.get("avg_return_pct"))
        if name and count >= 2 and avg_return < 0.0 and win_rate <= 0.25:
            clusters.append(name)
        if len(clusters) >= limit:
            break
    return clusters


def _problem_rows(rows: List[Dict[str, Any]], *, limit: int = 6) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        count = _to_int(row.get("closed_or_realized_count") or row.get("count"))
        avg_return = _to_float(row.get("avg_return_pct"))
        win_rate = _to_float(row.get("win_rate"))
        if count <= 0:
            continue
        if avg_return < 0.0 or win_rate <= 0.25:
            out.append(
                {
                    "name": name,
                    "count": count,
                    "win_rate": win_rate,
                    "avg_return_pct": avg_return,
                    "cost_drag_loss_count": _to_int(row.get("cost_drag_loss_count")),
                }
            )
        if len(out) >= limit:
            break
    return out


def _feedback_tags(packet: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    for row in _problem_rows(list(packet.get("quant_entry_blocker_rows") or []), limit=4):
        tags.append(f"entry_blocker:{row['name']}")
    for row in _problem_rows(list(packet.get("quant_exit_decision_rows") or []), limit=4):
        tags.append(f"exit_decision:{row['name']}")
    for row in _problem_rows(list(packet.get("quant_exit_hold_window_rows") or []), limit=3):
        tags.append(f"hold_window:{row['name']}")
    for row in _problem_rows(list(packet.get("quant_tactic_suitability_rows") or []), limit=3):
        tags.append(f"tactic_suitability:{row['name']}")
    out: List[str] = []
    for tag in tags:
        if tag not in out:
            out.append(tag)
    return out[:12]


def tactic_scorecards_from_quant_memory(packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    packet = dict(packet or {})
    exit_loss_clusters = _loss_cluster_names(list(packet.get("exit_reason_rows") or []))
    out: List[Dict[str, Any]] = []
    for row in list(packet.get("tactic_rows") or []):
        if not isinstance(row, dict):
            continue
        raw_name = str(row.get("name") or "").strip()
        tactic_id = canonical_tactic_key(raw_name)
        if not tactic_id:
            continue
        sample_count = _to_int(row.get("closed_or_realized_count") or row.get("count"))
        scorecard = TacticScorecard(
            tactic_id=tactic_id,
            sample_count=sample_count,
            win_rate=_to_float(row.get("win_rate")),
            avg_return_pct=_to_float(row.get("avg_return_pct")),
            confidence=_confidence(sample_count),
            loss_clusters=tuple(exit_loss_clusters),
        )
        payload = scorecard.as_dict()
        payload["count"] = _to_int(row.get("count"))
        payload["avg_hold_seconds"] = _to_float(row.get("avg_hold_seconds"))
        payload["cost_drag_loss_count"] = _to_int(row.get("cost_drag_loss_count"))
        out.append(payload)
    return out


def build_quant_scorecard(packet: Dict[str, Any]) -> Dict[str, Any]:
    packet = dict(packet or {})
    metrics = dict(packet.get("metrics") or {})
    tactic_scorecards = tactic_scorecards_from_quant_memory(packet)
    exit_loss_clusters = _loss_cluster_names(list(packet.get("exit_reason_rows") or []), limit=8)
    cost_floor_rows = list(packet.get("cost_floor_rows") or [])
    quant_feedback = {
        "schema_version": "quant_memory_feedback.v1",
        "entry_blocker_problem_rows": _problem_rows(list(packet.get("quant_entry_blocker_rows") or [])),
        "exit_decision_problem_rows": _problem_rows(list(packet.get("quant_exit_decision_rows") or [])),
        "exit_confirmation_problem_rows": _problem_rows(list(packet.get("quant_exit_confirmation_rows") or [])),
        "hold_window_problem_rows": _problem_rows(list(packet.get("quant_exit_hold_window_rows") or [])),
        "tactic_suitability_problem_rows": _problem_rows(list(packet.get("quant_tactic_suitability_rows") or [])),
        "feedback_tags": _feedback_tags(packet),
        "behavior_effect": "observation_only",
    }
    return {
        "schema_version": "quant_scorecard.v1",
        "source": str(packet.get("source") or "quant_memory_packet"),
        "period_type": str(packet.get("period_type") or ""),
        "period_key": str(packet.get("period_key") or ""),
        "metrics": {
            "trade_count": _to_int(metrics.get("trade_count")),
            "closed_trade_count": _to_int(metrics.get("closed_trade_count")),
            "win_rate": metrics.get("win_rate"),
            "avg_return_pct": metrics.get("avg_return_pct"),
            "avg_hold_seconds": metrics.get("avg_hold_seconds"),
            "return_basis": str(metrics.get("return_basis") or ""),
        },
        "tactic_scorecards": tactic_scorecards,
        "exit_loss_clusters": exit_loss_clusters,
        "cost_floor_rows": cost_floor_rows,
        "quant_tactic_rows": list(packet.get("quant_tactic_rows") or []),
        "quant_entry_blocker_rows": list(packet.get("quant_entry_blocker_rows") or []),
        "quant_exit_decision_rows": list(packet.get("quant_exit_decision_rows") or []),
        "quant_exit_confirmation_rows": list(packet.get("quant_exit_confirmation_rows") or []),
        "quant_exit_hold_window_rows": list(packet.get("quant_exit_hold_window_rows") or []),
        "quant_memory_feedback": quant_feedback,
        "scanner_rank_rows": list(packet.get("scanner_rank_rows") or []),
        "combined_rows": list(packet.get("combined_rows") or [])[:8],
        "behavior_effect": "observation_only",
    }


def compact_scorecard_for_llm(scorecard: Dict[str, Any], *, tactic_limit: int = 6) -> Dict[str, Any]:
    payload = dict(scorecard or {})
    return {
        "schema_version": "quant_scorecard_compact.v1",
        "period_type": str(payload.get("period_type") or ""),
        "period_key": str(payload.get("period_key") or ""),
        "metrics": dict(payload.get("metrics") or {}),
        "tactic_scorecards": list(payload.get("tactic_scorecards") or [])[: max(1, int(tactic_limit))],
        "exit_loss_clusters": list(payload.get("exit_loss_clusters") or [])[:6],
        "cost_floor_rows": list(payload.get("cost_floor_rows") or [])[:4],
        "quant_memory_feedback": dict(payload.get("quant_memory_feedback") or {}),
        "behavior_effect": "observation_only",
    }
