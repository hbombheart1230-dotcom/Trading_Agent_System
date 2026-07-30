from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from libs.research.post_reclaim_alpha.kiwoom_history import (
    KiwoomHistoricalMinuteReader,
    load_or_fetch_symbol_history,
)

from .candidates import build_hypothesis_episodes, load_candidate_snapshots
from .contracts import (
    BEHAVIOR_EFFECT,
    END,
    GATES,
    HYPOTHESES,
    LIVE_COST_PCT,
    SCHEMA_VERSION,
    START,
)
from .evaluator import evaluate_hypothesis
from .report import render_markdown


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_alpha_hypothesis_competition(
    *,
    start: str = START,
    end: str = END,
    candidate_root: Path = Path("data/logs/quant_shadow_candidates"),
    cache_root: Path = Path("data/research/post_reclaim_alpha/minute_cache"),
    output_root: Path = Path(
        "reports/evaluation/offline_alpha/alpha_hypothesis_competition"
    ),
    allow_fetch: bool = True,
    max_pages: int = 25,
    reader: KiwoomHistoricalMinuteReader | None = None,
) -> dict[str, str]:
    extraction = load_candidate_snapshots(
        root=candidate_root,
        start=start,
        end=end,
    )
    episodes_by_hypothesis = build_hypothesis_episodes(
        list(extraction.get("rows") or [])
    )
    minimum_by_symbol: dict[str, int] = defaultdict(lambda: 2**63 - 1)
    for episodes in episodes_by_hypothesis.values():
        for row in episodes:
            symbol = str(row.get("symbol") or "")
            epoch = int(row.get("baseline_epoch") or 0)
            if symbol and epoch > 0:
                minimum_by_symbol[symbol] = min(minimum_by_symbol[symbol], epoch)

    history_reader = reader
    if allow_fetch and history_reader is None:
        history_reader = KiwoomHistoricalMinuteReader.from_env()
    minute_rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    provider_rows: list[dict[str, Any]] = []
    for symbol in sorted(minimum_by_symbol):
        rows, meta = load_or_fetch_symbol_history(
            reader=history_reader if allow_fetch else None,
            symbol=symbol,
            minimum_epoch=minimum_by_symbol[symbol],
            cache_root=cache_root,
            max_pages=max_pages,
        )
        minute_rows_by_symbol[symbol] = rows
        provider_rows.append(meta)

    results: dict[str, Any] = {}
    for hypothesis_id in HYPOTHESES:
        result = evaluate_hypothesis(
            list(episodes_by_hypothesis.get(hypothesis_id) or []),
            minute_rows_by_symbol=minute_rows_by_symbol,
        )
        result["name"] = HYPOTHESES[hypothesis_id]["name"]
        result["conditions"] = list(HYPOTHESES[hypothesis_id]["conditions"])
        results[hypothesis_id] = result

    payload = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": BEHAVIOR_EFFECT,
        "range": {"start": start, "end": end},
        "cost_model": {"live_cost_pct": LIVE_COST_PCT},
        "fixed_gates": dict(GATES),
        "candidate_extraction": {
            key: value for key, value in extraction.items() if key != "rows"
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
    json_path = output_dir / "alpha_hypothesis_competition_v1.json"
    markdown_path = output_dir / "alpha_hypothesis_competition_v1.md"
    _write_json(json_path, payload)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}
