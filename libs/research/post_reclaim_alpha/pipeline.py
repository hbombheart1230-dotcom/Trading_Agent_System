from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from .contracts import LIVE_COST_PCT, MOCK_COST_PCT, SCHEMA_VERSION
from .episodes import build_independent_episodes, load_target_candidate_rows
from .evaluator import (
    build_decision,
    evaluate_episodes,
    scanner_baseline_for_days,
    summarize_horizon,
)
from .executable_policy import evaluate_executable_policy
from .executable_report import render_executable_policy_markdown
from .kiwoom_history import (
    KiwoomHistoricalMinuteReader,
    load_or_fetch_symbol_history,
)
from .report import render_markdown


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_post_reclaim_offline_research(
    *,
    start: str,
    end: str,
    candidate_root: Path = Path("data/logs/quant_shadow_candidates"),
    cache_root: Path = Path("data/research/post_reclaim_alpha/minute_cache"),
    output_root: Path = Path("reports/evaluation/offline_alpha/post_reclaim"),
    cumulative_review_path: Path = Path(
        "reports/evaluation/range/2026-06-01_2026-07-30/"
        "cumulative_improvement_review.json"
    ),
    allow_fetch: bool = True,
    max_pages: int = 20,
    reader: KiwoomHistoricalMinuteReader | None = None,
) -> dict[str, str]:
    candidate_rows = load_target_candidate_rows(
        root=candidate_root,
        start=start,
        end=end,
    )
    extraction = build_independent_episodes(candidate_rows)
    episodes = list(extraction.get("episodes") or [])
    minimum_by_symbol: dict[str, int] = defaultdict(lambda: 2**63 - 1)
    for row in episodes:
        symbol = str(row.get("symbol") or "")
        epoch = int(row.get("baseline_epoch") or 0)
        if symbol and epoch > 0:
            minimum_by_symbol[symbol] = min(minimum_by_symbol[symbol], epoch)

    history_reader = reader
    if allow_fetch and history_reader is None:
        history_reader = KiwoomHistoricalMinuteReader.from_env()
    minute_rows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    provider_meta: list[dict[str, Any]] = []
    for symbol in sorted(minimum_by_symbol):
        rows, meta = load_or_fetch_symbol_history(
            reader=history_reader if allow_fetch else None,
            symbol=symbol,
            minimum_epoch=minimum_by_symbol[symbol],
            cache_root=cache_root,
            max_pages=max_pages,
        )
        minute_rows_by_symbol[symbol] = rows
        provider_meta.append(meta)

    evaluated = evaluate_episodes(
        episodes,
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
    summaries = [
        summarize_horizon(evaluated, horizon)
        for horizon in ("+5m", "+15m", "+30m", "+60m", "EOD")
    ]
    baseline = scanner_baseline_for_days(
        _read_json(cumulative_review_path),
        days={str(row.get("day") or "") for row in evaluated},
    )
    decision = build_decision(
        episodes=evaluated,
        summaries=summaries,
        scanner_baseline=baseline,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": "research_only",
        "range": {"start": start, "end": end},
        "cost_model": {
            "live_cost_pct": LIVE_COST_PCT,
            "mock_cost_pct": MOCK_COST_PCT,
        },
        "episode_extraction": {
            key: value for key, value in extraction.items() if key != "episodes"
        },
        "provider_summary": {
            "symbol_count": len(provider_meta),
            "complete_symbol_count": sum(
                1 for row in provider_meta if row.get("coverage_complete")
            ),
            "rows": provider_meta,
        },
        "horizon_summaries": summaries,
        "scanner_rank1_baseline": baseline,
        "promotion_decision": decision,
        "episodes": evaluated,
    }
    executable_policy = evaluate_executable_policy(
        evaluated,
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
    output_dir = output_root / f"{start}_{end}"
    json_path = output_dir / "post_reclaim_offline_research.json"
    md_path = output_dir / "post_reclaim_offline_research.md"
    policy_json_path = output_dir / "post_reclaim_executable_policy_v0.json"
    policy_md_path = output_dir / "post_reclaim_executable_policy_v0.md"
    _write_json(json_path, payload)
    _write_json(policy_json_path, executable_policy)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    policy_md_path.write_text(
        render_executable_policy_markdown(executable_policy),
        encoding="utf-8",
    )
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "executable_policy_json": str(policy_json_path),
        "executable_policy_markdown": str(policy_md_path),
    }
