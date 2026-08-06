from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Mapping

from .delayed_outcomes import delayed_path, forward_30m_net

KST = timezone(timedelta(hours=9))


def universe_candidates(
    windows: Mapping[str, Mapping[str, Any]],
    decision_ids: set[str],
) -> list[dict[str, Any]]:
    result = []
    for decision_id in sorted(decision_ids):
        window = windows.get(decision_id) or {}
        universe = window.get("scanner_pre_strategist_universe")
        universe = universe if isinstance(universe, Mapping) else {}
        control = window.get("scanner_control")
        control = control if isinstance(control, Mapping) else {}
        rows = (
            universe.get("intrinsic_ranked_top20")
            or control.get("top20")
            or control.get("top10")
            or []
        )
        for row in rows[:10]:
            if not isinstance(row, Mapping):
                continue
            symbol = str(row.get("symbol") or "")
            rank = int(row.get("rank") or 0)
            if symbol and rank > 0:
                result.append(
                    {
                        "decision_id": decision_id,
                        "decision_epoch": int(
                            window.get("decision_epoch") or 0
                        ),
                        "rank": rank,
                        "symbol": symbol,
                        "score_total": row.get("score_total"),
                    }
                )
    return result


def build_universe_paths(
    candidates: list[Mapping[str, Any]],
    *,
    decision_days: Mapping[str, str],
    rows_by_symbol: Mapping[str, list[Mapping[str, Any]]],
    trading_calendar: list[str],
) -> list[dict[str, Any]]:
    result = []
    for candidate in candidates:
        decision_id = str(candidate.get("decision_id") or "")
        day = str(decision_days.get(decision_id) or "")
        symbol = str(candidate.get("symbol") or "")
        decision_epoch = int(candidate.get("decision_epoch") or 0)
        rows = list(rows_by_symbol.get(symbol) or [])
        entry = next(
            (
                row
                for row in rows
                if str(row.get("raw_ts") or "")[:8]
                == day.replace("-", "")
                and int(row.get("ts") or 0) > decision_epoch
                and not row.get("daily_bar")
            ),
            None,
        )
        if entry is None:
            continue
        baseline = float(entry.get("open") or entry.get("close") or 0.0)
        net_30m = forward_30m_net(
            rows=rows,
            day=day,
            decision_epoch=decision_epoch,
        )
        if baseline <= 0.0 or net_30m is None:
            continue
        case = {
            "day": day,
            "virtual_buy_time_kst": datetime.fromtimestamp(
                int(entry.get("ts") or 0),
                tz=timezone.utc,
            ).astimezone(
                KST,
            ).isoformat(),
            "virtual_buy_price": baseline,
            "net_return_30m_pct": net_30m,
        }
        result.append(
            {
                **dict(candidate),
                **case,
                **delayed_path(
                    case,
                    rows,
                    trading_calendar=trading_calendar,
                ),
            }
        )
    return result


def _metrics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "win_rate": None,
            "average_pct": None,
            "median_pct": None,
        }
    return {
        "count": len(values),
        "win_rate": round(
            sum(value > 0.0 for value in values) / len(values),
            4,
        ),
        "average_pct": round(sum(values) / len(values), 4),
        "median_pct": round(median(values), 4),
    }


def _rank_bucket(rank: int) -> str:
    if rank == 1:
        return "rank1"
    if rank <= 3:
        return "rank2_3"
    return "rank4_10"


def analyze_universe_paths(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    complete = [
        row
        for row in rows
        if row.get("d5_status") == "OBSERVED"
    ]
    buckets: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in complete:
        buckets[_rank_bucket(int(row.get("rank") or 0))].append(row)

    bucket_summary = {}
    for name in ("rank1", "rank2_3", "rank4_10"):
        group = buckets.get(name) or []
        negative = [
            row
            for row in group
            if float(row.get("net_return_30m_pct") or 0.0) <= 0.0
        ]
        delayed = [
            row
            for row in negative
            if row.get("delayed_high_opportunity")
        ]
        bucket_summary[name] = {
            "row_count": len(group),
            "return_30m": _metrics(
                [float(row["net_return_30m_pct"]) for row in group]
            ),
            "d5_high": _metrics(
                [float(row["d5_max_high_net_pct"]) for row in group]
            ),
            "d5_close": _metrics(
                [float(row["d5_close_net_pct"]) for row in group]
            ),
            "negative_30m_count": len(negative),
            "delayed_high_count": len(delayed),
            "delayed_high_rate": round(
                len(delayed) / len(negative),
                4,
            ) if negative else None,
        }

    paired = {}
    for field in (
        "net_return_30m_pct",
        "d5_max_high_net_pct",
        "d5_close_net_pct",
    ):
        deltas = []
        by_decision: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in complete:
            by_decision[str(row.get("decision_id") or "")].append(row)
        for decision_rows in by_decision.values():
            top1 = next(
                (
                    row
                    for row in decision_rows
                    if int(row.get("rank") or 0) == 1
                    and row.get(field) is not None
                ),
                None,
            )
            alternatives = [
                float(row[field])
                for row in decision_rows
                if int(row.get("rank") or 0) > 1
                and row.get(field) is not None
            ]
            if top1 is not None and alternatives:
                deltas.append(
                    float(top1[field])
                    - sum(alternatives) / len(alternatives)
                )
        paired[field] = {
            **_metrics(deltas),
            "top1_better_count": sum(value > 0.0 for value in deltas),
            "top1_worse_count": sum(value < 0.0 for value in deltas),
        }
    return {
        "path_count": len(rows),
        "d5_complete_count": len(complete),
        "decision_count": len(
            {str(row.get("decision_id") or "") for row in rows}
        ),
        "rank_buckets": bucket_summary,
        "paired_top1_minus_alternative_mean": paired,
    }
