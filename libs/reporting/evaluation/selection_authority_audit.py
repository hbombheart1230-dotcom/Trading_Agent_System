from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _symbol(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("symbol") or "").strip()
    return str(value or "").strip()


def _changed(a: str, b: str) -> bool | None:
    if not a or not b:
        return None
    return a != b


def build_selection_authority_audit(
    models: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for model in models:
        selection = _mapping(model.get("selection"))
        monitor = _mapping(model.get("monitor"))
        commander = _mapping(selection.get("commander_final"))
        raw_top1 = _symbol(selection.get("raw_scanner_top1"))
        post_top1 = _symbol(selection.get("scanner_top1"))
        selected = _symbol(selection.get("selected_symbol"))
        monitor_symbol = _symbol(
            monitor.get("selected_symbol")
            or _mapping(monitor.get("entry_context")).get("selected_symbol")
        )
        commander_candidate = _symbol(commander.get("candidate_symbol"))
        commander_selected = _symbol(commander.get("selected_symbol"))
        executed = _symbol(model.get("symbol"))
        raw_to_post = _changed(raw_top1, post_top1)
        post_to_selected = _changed(post_top1, selected)
        selected_to_monitor = _changed(selected, monitor_symbol)
        monitor_to_commander = _changed(monitor_symbol or selected, commander_candidate or commander_selected)
        final_to_executed = _changed(commander_selected or commander_candidate or selected, executed)
        row = {
            "trade_id": model.get("trade_id"),
            "symbol": executed,
            "raw_scanner_top1": raw_top1,
            "post_strategy_top1": post_top1,
            "selected_symbol": selected,
            "monitor_symbol": monitor_symbol,
            "commander_candidate_symbol": commander_candidate,
            "commander_selected_symbol": commander_selected,
            "executed_symbol": executed,
            "raw_to_post_changed": raw_to_post,
            "post_to_selected_changed": post_to_selected,
            "selected_to_monitor_changed": selected_to_monitor,
            "monitor_to_commander_changed": monitor_to_commander,
            "final_to_executed_changed": final_to_executed,
            "commander_authority_scope": str(commander.get("authority_scope") or ""),
            "commander_decision": str(commander.get("decision") or ""),
            "selection_mismatch": _mapping(selection.get("selection_mismatch")),
        }
        rows.append(row)
        for key in (
            "raw_to_post_changed",
            "post_to_selected_changed",
            "selected_to_monitor_changed",
            "monitor_to_commander_changed",
            "final_to_executed_changed",
        ):
            value = row[key]
            counters[f"{key}:unavailable" if value is None else f"{key}:{bool(value)}"] += 1

    return {
        "schema_version": "selection_authority_audit.v1",
        "behavior_effect": "observation_only",
        "trade_count": len(rows),
        "summary": dict(counters),
        "interpretation": {
            "commander_scope": "final approval/veto unless symbol deltas prove otherwise",
            "strategist_scope": "post-strategy scanner/ranking state, not pure LLM stock picker by default",
        },
        "rows": rows,
    }


def render_selection_authority_audit(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Selection Authority Audit",
        "",
        f"- Behavior effect: `{payload.get('behavior_effect', '')}`",
        f"- Trades: {payload.get('trade_count', 0)}",
        "",
        "## Summary",
        "",
    ]
    summary = _mapping(payload.get("summary"))
    if summary:
        for key in sorted(summary):
            lines.append(f"- `{key}`: {summary[key]}")
    else:
        lines.append("- No rows.")
    lines.extend([
        "",
        "## Rows",
        "",
        "| Trade | Raw Top1 | Post-Strategy Top1 | Selected | Monitor | Commander Candidate | Commander Selected | Executed |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            "| "
            + " | ".join(
                str(row.get(key) or "-")
                for key in (
                    "trade_id",
                    "raw_scanner_top1",
                    "post_strategy_top1",
                    "selected_symbol",
                    "monitor_symbol",
                    "commander_candidate_symbol",
                    "commander_selected_symbol",
                    "executed_symbol",
                )
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = ["build_selection_authority_audit", "render_selection_authority_audit"]
