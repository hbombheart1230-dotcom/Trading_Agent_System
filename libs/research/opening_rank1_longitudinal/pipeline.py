from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from libs.research.opening_rank1_deep_dive.loaders import (
    load_all_q9_windows,
)
from libs.research.opening_rank1_deep_dive.microstructure import (
    load_minute_rows,
)

from .analysis import analyze_longitudinal, analyze_stage_fates
from .daily_provider import (
    load_daily_cache,
    merge_minute_and_daily,
    refresh_daily_cache,
)
from .delayed_outcomes import delayed_path
from .report import render_markdown
from .stage_fate import load_executions_by_q9, stage_fate
from .universe_control import (
    analyze_universe_paths,
    build_universe_paths,
    universe_candidates,
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    flattened = []
    for row in rows:
        copy = {
            key: value
            for key, value in row.items()
            if not isinstance(value, (dict, list))
        }
        flattened.append(copy)
    fields = sorted({key for row in flattened for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flattened)


def _stage_symbols(window: Mapping[str, Any]) -> set[str]:
    strategist = window.get("strategist_selection")
    strategist = strategist if isinstance(strategist, Mapping) else {}
    commander = window.get("commander_final")
    commander = commander if isinstance(commander, Mapping) else {}
    return {
        str(value)
        for value in (
            strategist.get("selected_symbol"),
            commander.get("candidate_symbol"),
            commander.get("selected_symbol"),
        )
        if str(value or "").strip()
    }


def _deduplicate_events(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(
        rows,
        key=lambda value: str(value.get("decision_time_kst") or ""),
    ):
        key = (
            str(row.get("day") or ""),
            str(row.get("symbol") or ""),
        )
        selected.setdefault(key, row)
    return list(selected.values())


def _trading_calendar(reports_root: Path) -> list[str]:
    root = reports_root / "operator_summary" / "daily"
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir()
        and len(path.name) == 10
        and path.name[4] == "-"
        and path.name[7] == "-"
    ) if root.exists() else []


def _daily_trading_calendar(
    daily_rows: Mapping[str, list[Mapping[str, Any]]],
) -> list[str]:
    return sorted(
        {
            str(row.get("day") or "")
            for rows in daily_rows.values()
            for row in rows
            if len(str(row.get("day") or "")) == 10
        }
    )


def run_opening_rank1_longitudinal(
    *,
    deep_dive_path: Path = Path(
        "reports/evaluation/offline_alpha/opening_rank1_deep_dive/"
        "opening_rank1_deep_dive.json"
    ),
    reports_root: Path = Path("reports"),
    minute_cache_root: Path = Path(
        "data/research/post_reclaim_alpha/minute_cache"
    ),
    output_root: Path = Path(
        "reports/evaluation/offline_alpha/opening_rank1_longitudinal"
    ),
    daily_cache_root: Path = Path(
        "data/research/opening_rank1_longitudinal/daily_cache"
    ),
    refresh_daily: bool = False,
    base_day: str = "2026-07-31",
) -> dict[str, str]:
    deep_dive = _read_json(deep_dive_path)
    cases = [
        dict(row)
        for row in deep_dive.get("cases") or []
        if isinstance(row, Mapping)
    ]
    days = {str(row.get("day") or "") for row in cases}
    windows = load_all_q9_windows(reports_root, days)
    executions = load_executions_by_q9(reports_root, days)
    decision_ids = {
        str(row.get("decision_id") or "")
        for row in cases
    }
    universe_rows = universe_candidates(windows, decision_ids)
    symbols = {str(row.get("symbol") or "") for row in cases}
    for decision_id in decision_ids:
        symbols.update(_stage_symbols(windows.get(decision_id, {})))
    symbols.update(
        str(row.get("symbol") or "")
        for row in executions.values()
    )
    symbols.update(str(row.get("symbol") or "") for row in universe_rows)
    symbols.discard("")
    minute_rows = load_minute_rows(minute_cache_root, symbols)
    refresh_result: dict[str, Any] = {
        "attempted": False,
        "success_count": 0,
        "errors": {},
    }
    if refresh_daily:
        refresh_result = {
            "attempted": True,
            **refresh_daily_cache(
                cache_root=daily_cache_root,
                symbols=symbols,
                base_day=base_day,
            ),
        }
    daily_rows = load_daily_cache(daily_cache_root, symbols)
    longitudinal_rows = {
        symbol: merge_minute_and_daily(
            minute_rows.get(symbol) or [],
            daily_rows.get(symbol) or [],
        )
        for symbol in symbols
    }

    stage_rows = []
    for case in cases:
        decision_id = str(case.get("decision_id") or "")
        stage_rows.append(
            {
                **case,
                **stage_fate(
                    case,
                    window=windows.get(decision_id, {}),
                    minute_rows_by_symbol=minute_rows,
                    execution=executions.get(decision_id),
                ),
            }
        )

    events = []
    daily_calendar = _daily_trading_calendar(daily_rows)
    trading_calendar = daily_calendar or _trading_calendar(reports_root)
    for case in _deduplicate_events(stage_rows):
        events.append(
            {
                **case,
                **delayed_path(
                    case,
                    longitudinal_rows.get(
                        str(case.get("symbol") or ""),
                        [],
                    ),
                    trading_calendar=trading_calendar,
                ),
            }
        )
    decision_days = {
        str(row.get("decision_id") or ""): str(row.get("day") or "")
        for row in cases
    }
    universe_paths = build_universe_paths(
        universe_rows,
        decision_days=decision_days,
        rows_by_symbol=longitudinal_rows,
        trading_calendar=trading_calendar,
    )
    payload = {
        "schema_version": "opening_rank1_longitudinal.v1",
        "behavior_effect": "offline_analysis_only",
        "source_deep_dive": str(deep_dive_path),
        "trading_calendar": trading_calendar,
        "daily_cache": {
            "root": str(daily_cache_root),
            "refresh": refresh_result,
            "symbols_with_rows": sum(
                bool(rows)
                for rows in daily_rows.values()
            ),
        },
        "stage_rows": stage_rows,
        "events": events,
        "universe_paths": universe_paths,
        "stage_analysis": analyze_stage_fates(stage_rows),
        "longitudinal_analysis": analyze_longitudinal(events),
        "universe_control_analysis": analyze_universe_paths(
            universe_paths
        ),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "opening_rank1_longitudinal.json"
    stage_csv = output_root / "opening_rank1_stage_fates.csv"
    event_csv = output_root / "opening_rank1_longitudinal_events.csv"
    universe_csv = output_root / "opening_rank1_universe_control.csv"
    markdown_path = output_root / "opening_rank1_longitudinal.md"
    _write_json(json_path, payload)
    _write_csv(stage_csv, stage_rows)
    _write_csv(event_csv, events)
    _write_csv(universe_csv, universe_paths)
    markdown_path.write_text(
        render_markdown(payload),
        encoding="utf-8",
    )
    return {
        "json": str(json_path),
        "stage_csv": str(stage_csv),
        "event_csv": str(event_csv),
        "universe_csv": str(universe_csv),
        "markdown": str(markdown_path),
    }
