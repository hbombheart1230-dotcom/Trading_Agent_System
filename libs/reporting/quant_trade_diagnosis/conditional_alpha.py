from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


def load_conditional_alpha_episodes(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, TypeError, ValueError):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _timestamp(value: Any) -> float | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def resolve_conditional_alpha_context(
    model: Mapping[str, Any], episodes: list[dict[str, Any]]
) -> dict[str, Any]:
    selection = model.get("selection") if isinstance(model.get("selection"), Mapping) else {}
    decision_id = str(selection.get("q9_decision_id") or "")
    exact = next(
        (row for row in episodes if decision_id and str(row.get("decision_id") or "") == decision_id),
        None,
    )
    if exact:
        selected = exact
        status = "EXACT_DECISION_ID"
        authority = "AUTHORITATIVE_POINT_IN_TIME_LINK"
    else:
        day = str(model.get("day") or "")[:10]
        symbol = str(model.get("symbol") or "").zfill(6)
        candidates = [
            row
            for row in episodes
            if str(row.get("day") or "")[:10] == day
            and str(row.get("symbol") or "").zfill(6) == symbol
        ]
        entry_ts = _timestamp((model.get("entry") or {}).get("timestamp"))
        selected = min(
            candidates,
            key=lambda row: abs((_timestamp(row.get("decision_time_kst")) or 0) - (entry_ts or 0)),
            default=None,
        )
        status = "TIME_SYMBOL_CONTEXT_ONLY" if selected else "NOT_MATCHED"
        authority = "CONTEXT_ONLY_NOT_CAUSAL" if selected else "UNAVAILABLE"
    if not selected:
        return {"match_status": status, "authority": authority}
    partial_exit = model.get("integrity") if isinstance(model.get("integrity"), Mapping) else {}
    partial_exit = (
        partial_exit.get("partial_exit_duplicate")
        if isinstance(partial_exit.get("partial_exit_duplicate"), Mapping)
        else {}
    )
    duplicate_child = partial_exit.get("status") == "duplicate_partial_exit_child"
    if duplicate_child and status == "EXACT_DECISION_ID":
        status = "EXACT_DECISION_ID_DUPLICATE_CHILD"
        authority = "DUPLICATE_PARTIAL_EXIT_CHILD_CONTEXT"
    attribution = selected.get("stage_attribution") or {}
    return {
        "match_status": status,
        "authority": authority,
        "decision_id": selected.get("decision_id"),
        "decision_time_kst": selected.get("decision_time_kst"),
        "cohort_ids": selected.get("conditional_alpha_cohorts") or [],
        "opening_archetype": selected.get("opening_archetype"),
        "stage_root_cause": attribution.get("root_cause"),
        "forward_returns_pct": {
            "5m": selected.get("return_5m_pct"),
            "15m": selected.get("return_15m_pct"),
            "30m": selected.get("net_return_30m_pct"),
            "60m": selected.get("return_60m_pct"),
            "EOD": selected.get("return_eod_pct"),
        },
        "mfe_30m_pct": selected.get("mfe_30m_pct"),
        "mae_30m_pct": selected.get("mae_30m_pct"),
        "warning": (
            "Duplicate partial-exit child; do not count as an independent entry."
            if duplicate_child
            else None
            if status == "EXACT_DECISION_ID"
            else "Same-day/symbol proximity only; do not attribute this episode to the trade."
        ),
    }
