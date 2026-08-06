from __future__ import annotations

from collections import defaultdict
from typing import Any


def _top_rows(window: dict[str, Any]) -> list[dict[str, Any]]:
    control = window.get("scanner_control") if isinstance(window.get("scanner_control"), dict) else {}
    return [row for row in (control.get("top20") or control.get("top10") or []) if isinstance(row, dict)]


def build_rank_index(windows: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for decision_id, window in windows.items():
        rows = _top_rows(window)
        if not rows:
            continue
        epoch = int(window.get("decision_epoch") or 0)
        day = str(window.get("generated_at") or "")[:10]
        if not day:
            from datetime import datetime, timezone

            day = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone().date().isoformat()
        by_day[day].append(
            {
                "decision_id": decision_id,
                "epoch": epoch,
                "symbol": str(rows[0].get("symbol") or ""),
                "score": _float(rows[0].get("score_total")),
                "rank2_score": _float(rows[1].get("score_total")) if len(rows) >= 2 else None,
                "confidence": _float(rows[0].get("confidence")),
                "rank2_confidence": _float(rows[1].get("confidence")) if len(rows) >= 2 else None,
                "risk": _float(rows[0].get("risk_score")),
                "rank2_risk": _float(rows[1].get("risk_score")) if len(rows) >= 2 else None,
                "score_rank": next(
                    (
                        rank
                        for rank, row in enumerate(
                            sorted(
                                rows,
                                key=lambda item: -float(item.get("score_total") or -10**30),
                            ),
                            start=1,
                        )
                        if str(row.get("symbol") or "") == str(rows[0].get("symbol") or "")
                    ),
                    None,
                ),
                "candidate_count": len(rows),
            }
        )
    for rows in by_day.values():
        rows.sort(key=lambda row: row["epoch"])
    return dict(by_day)


def rank_features(
    case: dict[str, Any],
    *,
    decision_id: str,
    rank_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    rows = rank_index.get(str(case.get("day") or "")) or []
    index = next((i for i, row in enumerate(rows) if row["decision_id"] == decision_id), -1)
    if index < 0:
        return {"rank_context_status": "MISSING"}
    current = rows[index]
    symbol = current["symbol"]
    epoch = current["epoch"]
    prior = [row for row in rows if epoch - 300 <= row["epoch"] < epoch]
    future = [row for row in rows if epoch < row["epoch"] <= epoch + 300]
    streak_start = epoch
    cursor = index - 1
    while cursor >= 0:
        row = rows[cursor]
        next_epoch = rows[cursor + 1]["epoch"]
        if row["symbol"] != symbol or next_epoch - row["epoch"] > 180:
            break
        streak_start = row["epoch"]
        cursor -= 1
    streak_end = epoch
    cursor = index + 1
    while cursor < len(rows):
        row = rows[cursor]
        previous_epoch = rows[cursor - 1]["epoch"]
        if row["symbol"] != symbol or row["epoch"] - previous_epoch > 180:
            break
        streak_end = row["epoch"]
        cursor += 1
    prior_score = next(
        (row["score"] for row in reversed(prior) if row["symbol"] == symbol and row["score"] is not None),
        None,
    )
    return {
        "rank_context_status": "OBSERVED",
        "rank2_score": current["rank2_score"],
        "rank1_rank2_score_delta": round(current["score"] - current["rank2_score"], 4)
        if current["score"] is not None and current["rank2_score"] is not None
        else None,
        "rank1_rank2_gap": round(current["score"] - current["rank2_score"], 4)
        if current["score"] is not None and current["rank2_score"] is not None
        else None,
        "rank1_rank2_confidence_delta": round(
            current["confidence"] - current["rank2_confidence"], 4
        )
        if current["confidence"] is not None and current["rank2_confidence"] is not None
        else None,
        "rank1_rank2_risk_delta": round(current["risk"] - current["rank2_risk"], 4)
        if current["risk"] is not None and current["rank2_risk"] is not None
        else None,
        "rank1_score_rank": current["score_rank"],
        "rank1_is_highest_score": current["score_rank"] == 1 if current["score_rank"] else None,
        "rank_candidate_count": current["candidate_count"],
        "rank1_age_sec": epoch - streak_start,
        "rank1_forward_persistence_sec": streak_end - epoch,
        "rank1_prev5m_observations": sum(row["symbol"] == symbol for row in prior),
        "rank1_next5m_observations": sum(row["symbol"] == symbol for row in future),
        "rank1_prev5m_distinct_symbols": len({row["symbol"] for row in prior}),
        "rank1_score_change_from_prior": round(current["score"] - prior_score, 4)
        if current["score"] is not None and prior_score is not None
        else None,
    }


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
