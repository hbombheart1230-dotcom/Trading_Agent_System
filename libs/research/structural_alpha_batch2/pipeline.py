from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping

from libs.research.post_reclaim_alpha.kiwoom_history import (
    KiwoomHistoricalMinuteReader,
    load_or_fetch_symbol_history,
)
from libs.research.structural_alpha.evaluator import evaluate_strategy
from libs.research.structural_alpha.windows import load_point_in_time_windows

from .contracts import (
    BEHAVIOR_EFFECT,
    END,
    GATES,
    HYPOTHESES,
    LIVE_COST_PCT,
    MARKET_PROXY_SYMBOLS,
    SCHEMA_VERSION,
    START,
)
from .report import render_markdown
from .strategies import (
    build_market_shock_reversal_episodes,
    build_oversold_reversal_episodes,
    build_trend_pullback_episodes,
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_structural_alpha_batch2(
    *,
    start: str = START,
    end: str = END,
    reports_root: Path = Path("reports"),
    cache_root: Path = Path("data/research/post_reclaim_alpha/minute_cache"),
    output_root: Path = Path(
        "reports/evaluation/offline_alpha/structural_alpha_batch2"
    ),
    allow_fetch: bool = True,
    max_pages: int = 18,
    reader: KiwoomHistoricalMinuteReader | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, str]:
    extraction = load_point_in_time_windows(
        reports_root=reports_root,
        start=start,
        end=end,
    )
    windows = list(extraction.get("windows") or [])
    minimum_by_symbol: dict[str, int] = defaultdict(lambda: 2**63 - 1)
    for window in windows:
        minimum_epoch = max(1, int(window.get("decision_epoch") or 0) - 2 * 3600)
        for candidate in window.get("candidates") or []:
            symbol = str(candidate.get("symbol") or "")
            if symbol:
                minimum_by_symbol[symbol] = min(
                    minimum_by_symbol[symbol],
                    minimum_epoch,
                )
    earliest_epoch = min(minimum_by_symbol.values(), default=1)
    for symbol in MARKET_PROXY_SYMBOLS:
        minimum_by_symbol[symbol] = min(
            minimum_by_symbol[symbol],
            earliest_epoch,
        )

    history_reader = reader
    if allow_fetch and history_reader is None:
        history_reader = KiwoomHistoricalMinuteReader.from_env()
    minute_rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    provider_rows: list[dict[str, Any]] = []
    symbols = sorted(minimum_by_symbol)
    for index, symbol in enumerate(symbols, start=1):
        rows, meta = load_or_fetch_symbol_history(
            reader=history_reader if allow_fetch else None,
            symbol=symbol,
            minimum_epoch=minimum_by_symbol[symbol],
            cache_root=cache_root,
            max_pages=max_pages,
        )
        minute_rows_by_symbol[symbol] = rows
        provider_rows.append(meta)
        if progress is not None:
            progress(index, len(symbols), symbol)

    episodes = {
        "H7_MARKET_SHOCK_RELATIVE_STRENGTH_REVERSAL": (
            build_market_shock_reversal_episodes(
                windows,
                minute_rows_by_symbol=minute_rows_by_symbol,
            )
        ),
        "H8_OVERSOLD_MEAN_REVERSION": build_oversold_reversal_episodes(
            windows,
            minute_rows_by_symbol=minute_rows_by_symbol,
        ),
        "H9_TREND_PULLBACK_RESUMPTION": build_trend_pullback_episodes(
            windows,
            minute_rows_by_symbol=minute_rows_by_symbol,
        ),
    }
    results = {
        strategy_id: evaluate_strategy(
            rows,
            minute_rows_by_symbol=minute_rows_by_symbol,
        )
        for strategy_id, rows in episodes.items()
    }
    for strategy_id, result in results.items():
        result["name"] = HYPOTHESES[strategy_id]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": BEHAVIOR_EFFECT,
        "range": {"start": start, "end": end},
        "cost_model": {"live_cost_pct": LIVE_COST_PCT},
        "fixed_gates": dict(GATES),
        "window_extraction": {
            key: value for key, value in extraction.items() if key != "windows"
        },
        "provider_summary": {
            "symbol_count": len(provider_rows),
            "complete_symbol_count": sum(
                1 for row in provider_rows if row.get("coverage_complete")
            ),
            "rows": provider_rows,
        },
        "results": results,
    }
    output_dir = output_root / f"{start}_{end}"
    json_path = output_dir / "structural_alpha_batch2.json"
    markdown_path = output_dir / "structural_alpha_batch2.md"
    _write_json(json_path, payload)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}
