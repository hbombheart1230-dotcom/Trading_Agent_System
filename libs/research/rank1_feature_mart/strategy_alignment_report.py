from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from .integrity import value_at


HORIZONS = ("+5m", "+15m", "+30m", "EOD")


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _independent(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    first: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in sorted(rows, key=lambda item: int(value_at(item, "identity.decision_epoch") or 0)):
        key = (
            str(value_at(row, "identity.day") or ""),
            str(value_at(row, "identity.symbol") or ""),
        )
        first.setdefault(key, row)
    return list(first.values())


def _metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    independent = _independent(rows)
    horizons = {}
    for horizon in HORIZONS:
        values = [
            value
            for row in independent
            if (
                value := _number(
                    value_at(row, f"outcomes.checkpoints.{horizon}.net_return_pct")
                )
            )
            is not None
        ]
        horizons[horizon] = {
            "observed_count": len(values),
            "coverage": round(len(values) / len(independent), 4) if independent else 1.0,
            "win_rate": (
                round(sum(value > 0.0 for value in values) / len(values), 4)
                if values
                else None
            ),
            "avg_net_return_pct": round(mean(values), 4) if values else None,
        }
    return {"day_symbol_count": len(independent), "horizons": horizons}


def build_strategy_alignment_report(
    rows: Sequence[Mapping[str, Any]], *, day: str | None = None
) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if (not day or value_at(row, "identity.day") == day)
        and value_at(row, "strategy_choice_observation.evidence_status") == "OBSERVED"
    ]
    alignments: dict[str, list[Mapping[str, Any]]] = {}
    combinations: dict[str, list[Mapping[str, Any]]] = {}
    for row in selected:
        alignment = str(
            value_at(
                row,
                "strategy_choice_observation.candidate_setup_observation.setup_playbook_alignment",
            )
            or "MISSING"
        )
        alignments.setdefault(alignment, []).append(row)
        combination = " | ".join(
            (
                str(value_at(row, "strategy.market_playbook") or "MISSING"),
                str(value_at(row, "strategy.tactical_strategy") or "MISSING"),
                str(value_at(row, "scanner.candidate_setup") or "MISSING"),
            )
        )
        combinations.setdefault(combination, []).append(row)
    return {
        "schema_version": "rank1_strategy_alignment_report.v1",
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "day": day or "ALL",
        "episode_count": len(selected),
        "independent_day_symbol_count": len(_independent(selected)),
        "playbook_distribution": dict(
            Counter(str(value_at(row, "strategy.market_playbook") or "MISSING") for row in selected)
        ),
        "tactic_distribution": dict(
            Counter(str(value_at(row, "strategy.tactical_strategy") or "MISSING") for row in selected)
        ),
        "candidate_setup_distribution": dict(
            Counter(str(value_at(row, "scanner.candidate_setup") or "MISSING") for row in selected)
        ),
        "generation_mode_distribution": dict(
            Counter(
                str(value_at(row, "strategy_choice_observation.generation.mode") or "MISSING")
                for row in selected
            )
        ),
        "default_tactic_selection": {
            "count": sum(
                value_at(
                    row,
                    "strategy_choice_observation.tactic_choice.selected_is_playbook_default",
                )
                is True
                for row in selected
            ),
            "total": len(selected),
        },
        "alignment_metrics": {
            key: _metrics(value) for key, value in sorted(alignments.items())
        },
        "combination_metrics": {
            key: _metrics(value) for key, value in sorted(combinations.items())
        },
    }


def _render(payload: Mapping[str, Any]) -> str:
    lines = [
        f"# Rank-1 Strategy / Candidate Setup Alignment - {payload.get('day')}",
        "",
        "* Behavior effect: **NONE (observation only)**",
        f"* Episodes: **{payload.get('episode_count', 0)}**",
        f"* Independent day-symbols: **{payload.get('independent_day_symbol_count', 0)}**",
        f"* Playbook-default tactic selections: **{(payload.get('default_tactic_selection') or {}).get('count', 0)} / {(payload.get('default_tactic_selection') or {}).get('total', 0)}**",
        "",
        "## Alignment Performance",
        "",
        "| Alignment | N | +5m avg | +15m avg | +30m avg | EOD avg |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, metrics in (payload.get("alignment_metrics") or {}).items():
        def avg(horizon: str) -> str:
            value = ((metrics.get("horizons") or {}).get(horizon) or {}).get("avg_net_return_pct")
            return "-" if value is None else f"{float(value):.4f}%"
        lines.append(
            f"| {key} | {metrics.get('day_symbol_count', 0)} | {avg('+5m')} | {avg('+15m')} | {avg('+30m')} | {avg('EOD')} |"
        )
    lines.extend(
        [
            "",
            "## Combination Performance",
            "",
            "| Market playbook / tactic / candidate setup | N | +15m avg | +30m avg |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for key, metrics in (payload.get("combination_metrics") or {}).items():
        h15 = ((metrics.get("horizons") or {}).get("+15m") or {}).get("avg_net_return_pct")
        h30 = ((metrics.get("horizons") or {}).get("+30m") or {}).get("avg_net_return_pct")
        lines.append(
            f"| {key} | {metrics.get('day_symbol_count', 0)} | "
            f"{'-' if h15 is None else f'{float(h15):.4f}%'} | "
            f"{'-' if h30 is None else f'{float(h30):.4f}%'} |"
        )
    lines.extend(
        [
            "",
            "Alignment is a diagnostic label. It does not change Strategist, Scanner, Monitor, Commander, or execution behavior.",
            "",
        ]
    )
    return "\n".join(lines)


def write_strategy_alignment_reports(
    rows: Sequence[Mapping[str, Any]], *, output_root: Path
) -> dict[str, Any]:
    report_root = output_root / "strategy_setup_alignment"
    cumulative = build_strategy_alignment_report(rows)
    report_root.mkdir(parents=True, exist_ok=True)
    cumulative_json = report_root / "strategy_setup_alignment_cumulative.json"
    cumulative_md = report_root / "strategy_setup_alignment_cumulative.md"
    cumulative_json.write_text(
        json.dumps(cumulative, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    cumulative_md.write_text(_render(cumulative), encoding="utf-8")
    days = sorted({str(value_at(row, "identity.day") or "") for row in rows if value_at(row, "identity.day")})
    for day in days:
        payload = build_strategy_alignment_report(rows, day=day)
        day_root = report_root / "daily" / day
        day_root.mkdir(parents=True, exist_ok=True)
        (day_root / "strategy_setup_alignment.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (day_root / "strategy_setup_alignment.md").write_text(
            _render(payload), encoding="utf-8"
        )
    return {
        "cumulative_json_path": str(cumulative_json),
        "cumulative_md_path": str(cumulative_md),
        "day_count": len(days),
    }
