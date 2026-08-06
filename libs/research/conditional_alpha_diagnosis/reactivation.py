from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .loaders import read_json
from .metrics import number


def _epoch(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return None


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def load_q9_symbol_occurrences(
    operator_daily_root: Path, symbols: set[str]
) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], set[str]]:
    occurrences: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    observed_days: set[str] = set()
    for path in sorted(operator_daily_root.glob("20??-??-??/q9_decision_windows.json")):
        payload = read_json(path)
        day = str(payload.get("day") or path.parent.name)[:10]
        windows = _rows(payload.get("windows"))
        if windows:
            observed_days.add(day)
        for window in windows:
            timestamp = window.get("generated_at")
            scanner_control = window.get("scanner_control")
            scanner_control = scanner_control if isinstance(scanner_control, Mapping) else {}
            pre = window.get("scanner_pre_strategist_universe")
            pre = pre if isinstance(pre, Mapping) else {}
            strategist = window.get("strategist_selection")
            strategist = strategist if isinstance(strategist, Mapping) else {}
            commander = window.get("commander_final")
            commander = commander if isinstance(commander, Mapping) else {}
            pools = {
                "pre": _rows(pre.get("intrinsic_ranked_top20")),
                "control": _rows(scanner_control.get("top10")),
                "post": _rows(strategist.get("post_strategist_top10")),
            }
            found: dict[str, dict[str, Any]] = {}
            for stage, candidates in pools.items():
                for index, candidate in enumerate(candidates, 1):
                    symbol = str(candidate.get("symbol") or "")
                    if symbol not in symbols:
                        continue
                    item = found.setdefault(
                        symbol,
                        {
                            "day": day,
                            "timestamp": timestamp,
                            "epoch": _epoch(timestamp),
                            "decision_id": window.get("decision_id"),
                            "stages": {},
                        },
                    )
                    item["stages"][stage] = {
                        "rank": candidate.get("rank", index),
                        "score": number(candidate.get("score_total")),
                        "risk_score": number(candidate.get("risk_score")),
                        "confidence": number(candidate.get("confidence")),
                        "tactic_id": (
                            candidate.get("quant_factor_snapshot") or {}
                        ).get("tactic_id")
                        if isinstance(candidate.get("quant_factor_snapshot"), Mapping)
                        else None,
                    }
            for symbol, item in found.items():
                item["strategist_selected"] = (
                    str(strategist.get("selected_symbol") or "") == symbol
                )
                item["strategist_scenario"] = strategist.get("scenario")
                item["strategist_playbook"] = strategist.get("playbook")
                item["commander_selected"] = (
                    str(commander.get("selected_symbol") or "") == symbol
                )
                item["commander_decision"] = commander.get("decision")
                item["commander_reason"] = commander.get("reason")
                item["commander_detail"] = commander.get("detail")
                item["monitor_intent"] = commander.get("monitor_intent")
                occurrences[symbol][day].append(item)
    return {symbol: dict(days) for symbol, days in occurrences.items()}, observed_days


def _classification(before: list[dict[str, Any]], after: list[dict[str, Any]], day_observed: bool) -> tuple[str, str]:
    if not day_observed:
        return "MEASUREMENT_MISSING", "Q9 decision windows were not available on the threshold day."
    if not before:
        if after:
            return "CANDIDATE_REDETECTED_TOO_LATE", "The symbol returned to the captured candidate set after the +5% threshold had already been reached."
        return "CANDIDATE_NOT_REDETECTED", "The symbol did not return to the captured pre-Strategist Top20 before the threshold. Historical source-universe symbols were not persisted, so source availability and ranking cannot be separated."
    control = [row for row in before if "control" in row.get("stages", {})]
    if not control:
        return "SCANNER_CONTROL_FILTERED", "The symbol appeared in pre-Strategist Top20 but not Scanner control Top10."
    selected = [row for row in control if row.get("strategist_selected")]
    if not selected:
        return "STRATEGIST_NOT_SELECTED", "Scanner found the symbol but Strategist did not select it."
    approved_buy = [
        row
        for row in selected
        if str(row.get("commander_decision") or "").lower() == "approve"
        and str(row.get("monitor_intent") or "").upper() == "BUY"
    ]
    if approved_buy:
        return "ENTRY_SIGNAL_AVAILABLE", "A point-in-time approved BUY signal existed before the threshold."
    rejected = [row for row in selected if str(row.get("commander_decision") or "").lower() == "reject"]
    if rejected:
        reasons = sorted({str(row.get("commander_reason") or "unknown") for row in rejected})
        return "COMMANDER_REJECTED", f"Strategist selected it, but Commander rejected it: {', '.join(reasons)}."
    return "MONITOR_NO_ENTRY", "Scanner and Strategist selected it, but no approved BUY intent was recorded."


def build_reactivation_lineage(
    events: Iterable[Mapping[str, Any]],
    *,
    operator_daily_root: Path,
) -> list[dict[str, Any]]:
    delayed = [
        dict(row)
        for row in events
        if row.get("selection_horizon_label")
        in {"DELAYED_HIGH_ONLY", "HORIZON_TOO_SHORT_CONFIRMED"}
    ]
    occurrences, observed_days = load_q9_symbol_occurrences(
        operator_daily_root, {str(row.get("symbol") or "") for row in delayed}
    )
    output = []
    for event in delayed:
        symbol = str(event.get("symbol") or "")
        trigger_day = str(event.get("first_plus_5pct_day") or "")
        trigger_epoch = _epoch(event.get("first_plus_5pct_epoch"))
        trigger_rows = list(occurrences.get(symbol, {}).get(trigger_day, []))
        before = [row for row in trigger_rows if trigger_epoch is not None and (row.get("epoch") or 0) <= trigger_epoch]
        after = [row for row in trigger_rows if trigger_epoch is not None and (row.get("epoch") or 0) > trigger_epoch]
        classification, reason = _classification(before, after, trigger_day in observed_days)
        prior_days = {
            day: rows
            for day, rows in occurrences.get(symbol, {}).items()
            if str(event.get("day") or "") <= day < trigger_day
        }
        output.append(
            {
                "episode_id": event.get("episode_id"),
                "initial_day": event.get("day"),
                "symbol": symbol,
                "symbol_name": event.get("symbol_name"),
                "themes": event.get("themes") or [],
                "initial_playbook": event.get("playbook"),
                "initial_scenario": event.get("strategist_scenario"),
                "initial_30m_return_pct": number(event.get("net_return_30m_pct")),
                "trigger_day": trigger_day,
                "trigger_epoch": trigger_epoch,
                "d5_high_net_pct": number(event.get("d5_max_high_net_pct")),
                "d5_close_net_pct": number(event.get("d5_close_net_pct")),
                "q9_threshold_day_observed": trigger_day in observed_days,
                "source_universe_symbol_list_available": False,
                "pre_threshold_occurrence_count": len(before),
                "post_threshold_occurrence_count": len(after),
                "prior_day_occurrence_count": sum(len(rows) for rows in prior_days.values()),
                "prior_observed_days": sorted(prior_days),
                "classification": classification,
                "reason": reason,
                "pre_threshold_occurrences": before,
                "post_threshold_occurrences": after[:10],
            }
        )
    return sorted(output, key=lambda row: (str(row.get("initial_day")), str(row.get("symbol"))))
