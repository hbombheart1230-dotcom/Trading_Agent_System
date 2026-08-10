from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .builder import build_day_sequences


DECISION_COUNT = 10


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cumulative(root: Path) -> dict[str, Any]:
    sequences = []
    for path in sorted(root.glob("20??-??-??/same_symbol_sequence.json")):
        payload = _read(path)
        sequences.extend(row for row in payload.get("sequences") or [] if isinstance(row, Mapping))
    clean = sum(int(row.get("clean_profit_exit_reentry_count") or 0) for row in sequences)
    repeated = [row for row in sequences if int(row.get("repeat_count") or 0) > 0]
    return {
        "schema_version": "same_symbol_sequence_cumulative.v1",
        "behavior_effect": "observation_only",
        "summary": {
            "sequence_count": len(sequences),
            "repeated_sequence_count": len(repeated),
            "clean_profit_exit_reentry_count": clean,
            "decision_at_count": DECISION_COUNT,
            "status": "READY_FOR_POLICY_REVIEW" if clean >= DECISION_COUNT else "COLLECTING",
        },
        "sequences": sequences,
        "policy_change_authorized": False,
    }


def _render(payload: Mapping[str, Any], title: str) -> str:
    summary = payload.get("summary") or {}
    lines = [
        f"# {title}", "",
        "- Behavior effect: observation only",
        f"- Status: **{summary.get('status', 'COLLECTING')}**",
        f"- Sequences: {summary.get('sequence_count', len(payload.get('sequences') or []))}",
        f"- Clean profit-exit reentries: {summary.get('clean_profit_exit_reentry_count', 0)} / {summary.get('decision_at_count', DECISION_COUNT)}",
        "", "| Day | Symbol | Trades | Cumulative | Peak | Giveback | Giveback ratio |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("sequences") or []:
        lines.append(f"| {row.get('day')} | {row.get('symbol')} | {row.get('trade_count')} | {float(row.get('cumulative_return_pct') or 0):+.4f}% | {float(row.get('maximum_cumulative_return_pct') or 0):+.4f}% | {float(row.get('profit_giveback_pct') or 0):.4f}% | {row.get('profit_giveback_ratio') if row.get('profit_giveback_ratio') is not None else '-'} |")
    lines += ["", "A changed Q9 decision ID alone does not prove a new independent setup.", ""]
    return "\n".join(lines)


def build_same_symbol_sequence_artifacts(*, reports_root: Path, day: str) -> dict[str, Any]:
    root = Path(reports_root) / "evaluation" / "same_symbol_sequences"
    sequences = build_day_sequences(reports_root=Path(reports_root), day=day)
    daily = {
        "schema_version": "same_symbol_sequence_daily.v1",
        "behavior_effect": "observation_only",
        "day": day,
        "summary": {
            "sequence_count": len(sequences),
            "repeated_sequence_count": sum(int(row.get("repeat_count") or 0) > 0 for row in sequences),
            "clean_profit_exit_reentry_count": sum(int(row.get("clean_profit_exit_reentry_count") or 0) for row in sequences),
            "status": "OBSERVED",
        },
        "sequences": sequences,
        "policy_change_authorized": False,
    }
    day_root = root / day
    daily_json = day_root / "same_symbol_sequence.json"
    daily_md = day_root / "same_symbol_sequence.md"
    _write(daily_json, daily)
    daily_md.write_text(_render(daily, f"Same-Symbol Sequence ({day})"), encoding="utf-8")
    cumulative = _cumulative(root)
    cumulative_json = root / "same_symbol_sequence_cumulative.json"
    cumulative_md = root / "same_symbol_sequence_cumulative.md"
    _write(cumulative_json, cumulative)
    cumulative_md.write_text(_render(cumulative, "Same-Symbol Sequence Cumulative"), encoding="utf-8")
    return {
        "daily_json": str(daily_json), "daily_markdown": str(daily_md),
        "cumulative_json": str(cumulative_json), "cumulative_markdown": str(cumulative_md),
        "summary": cumulative["summary"],
    }


__all__ = ["build_same_symbol_sequence_artifacts"]
