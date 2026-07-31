from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping

from libs.research.post_reclaim_alpha.kiwoom_history import (
    KiwoomHistoricalMinuteReader,
    load_or_fetch_symbol_history,
)
from libs.research.post_reclaim_alpha.evaluator import evaluate_episodes

from .analysis import (
    actual_trade_analysis,
    blocked_opportunity_analysis,
    discovery_cohorts,
    grouped_horizon_summary,
    score_component_diagnostics,
    simulate_path_policies,
    split_summary,
)
from .contracts import (
    BEHAVIOR_EFFECT,
    CALIBRATION_END,
    END,
    LIVE_COST_PCT,
    RETROSPECTIVE_START,
    SCHEMA_VERSION,
    START,
)
from .episodes import build_candidate_episodes, candidate_integrity
from .loaders import (
    load_latest_q16_samples,
    load_quant_shadow_samples,
    load_q9_candidate_windows,
    load_trade_evaluations,
)
from .report import render_markdown


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _decision_summary(
    *,
    integrity: Mapping[str, Any],
    source_rows: Mapping[str, Any],
    blocked: Mapping[str, Any],
    discoveries: Mapping[str, Any],
) -> str:
    native = (source_rows.get("market_native_multi") or {}).get("+30m") or {}
    native_metrics = native.get("metrics") or {}
    native_count = int(native.get("observed_count") or 0)
    sector_rate = float(integrity.get("sector_theme_only_window_rate") or 0.0)
    blocked_count = int(blocked.get("sample_count") or 0)
    breakout_hold = (
        ((blocked.get("by_reason") or {}).get(
            "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation"
        )
        or {}).get("+30m")
        or {}
    )
    breakout_metrics = breakout_hold.get("net_metrics") or {}
    secondary = ""
    if (
        int(breakout_hold.get("observed_count") or 0) >= 15
        and float(breakout_metrics.get("expectancy_pct") or 0.0) > 0.0
        and float(breakout_metrics.get("profit_factor") or 0.0) >= 1.20
    ):
        secondary = (
            " A secondary insufficient-evidence cohort is the non-entered VWAP-hold, "
            "volume-confirmed breakout setup; it has fewer than 25 observed +30m paths "
            "and cannot authorize a guard relaxation."
        )
    opening = (((discoveries.get("opening_rank1") or {}).get("retrospective") or {}).get("+30m") or {})
    opening_metrics = opening.get("metrics") or {}
    opening_candidate = (
        int(opening.get("observed_count") or 0) >= 25
        and float(opening.get("coverage") or 0.0) >= 0.90
        and float(opening_metrics.get("expectancy_pct") or 0.0) > 0.0
        and float(opening_metrics.get("profit_factor") or 0.0) >= 1.20
    )
    if opening_candidate:
        candidate = (
            "The only bounded discovery candidate is OPEN_0_20_RANK1_30M. It remains positive in the "
            "retrospective split after 0.28% cost, but retrospective positive-day consistency is below the "
            "55% promotion gate. Freeze it as FUTURE_CONFIRMATION_REQUIRED; do not change runtime behavior."
        )
    elif native_count >= 25 and float(native_metrics.get("expectancy_pct") or 0.0) > 0.0:
        candidate = (
            "Market-native multi-source candidates show positive retrospective +30m net expectancy, "
            "but July is already inspected and the historical universe is contaminated by theme-only windows. "
            "Retain this as one future-confirmation candidate; do not promote it."
        )
    else:
        candidate = (
            "No market-native multi-source candidate reaches a sufficient positive retrospective edge in the "
            "available evidence. Do not create a live or shadow behavior patch from this study."
        )
    return (
        f"{candidate} Historical sector-theme-only window rate is {sector_rate:.1%}. "
        f"The separate blocked-opportunity dataset contributes {blocked_count} path-observed samples and should be "
        f"used to identify over-filtering, not merged with reconstructed Scanner episodes as independent trades.{secondary}"
    )


def run_existing_evidence_mining(
    *,
    start: str = START,
    end: str = END,
    reports_root: Path = Path("reports"),
    cache_root: Path = Path("data/research/post_reclaim_alpha/minute_cache"),
    quant_shadow_root: Path = Path("data/logs/quant_shadow_candidates"),
    output_root: Path = Path("reports/evaluation/offline_alpha/existing_evidence_mining"),
    allow_fetch: bool = False,
    max_pages: int = 18,
    reader: KiwoomHistoricalMinuteReader | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, str]:
    extraction = load_q9_candidate_windows(
        reports_root=reports_root,
        start=start,
        end=end,
    )
    windows = list(extraction.get("windows") or [])
    quant_shadow = load_quant_shadow_samples(
        logs_root=quant_shadow_root,
        start=start,
        end=end,
    )
    minimum_by_symbol: dict[str, int] = defaultdict(lambda: 2**63 - 1)
    for window in windows:
        minimum_epoch = max(1, int(window.get("decision_epoch") or 0) - 2 * 3600)
        for candidate in window.get("candidates") or []:
            symbol = str(candidate.get("symbol") or "")
            if symbol:
                minimum_by_symbol[symbol] = min(minimum_by_symbol[symbol], minimum_epoch)
    for sample in quant_shadow.get("samples") or []:
        symbol = str(sample.get("symbol") or "")
        baseline_epoch = int(sample.get("baseline_epoch") or 0)
        if symbol and baseline_epoch > 0:
            minimum_by_symbol[symbol] = min(minimum_by_symbol[symbol], max(1, baseline_epoch - 2 * 3600))

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

    episodes = build_candidate_episodes(windows, minute_rows_by_symbol=minute_rows_by_symbol)
    integrity = candidate_integrity(windows)
    q16 = load_latest_q16_samples(reports_root=reports_root, start=start, end=end)
    trades = load_trade_evaluations(reports_root=reports_root, start=start, end=end)
    by_source_class = grouped_horizon_summary(episodes, field="source_class")
    discoveries = discovery_cohorts(episodes)
    evaluated_shadow = evaluate_episodes(
        list(quant_shadow.get("samples") or []),
        minute_rows_by_symbol=minute_rows_by_symbol,
    )
    blocked = blocked_opportunity_analysis(evaluated_shadow)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": BEHAVIOR_EFFECT,
        "range": {"start": start, "end": end},
        "cost_model": {"live_round_trip_cost_pct": LIVE_COST_PCT},
        "limitations": [
            "July data was already inspected and is not an untouched holdout.",
            "Q9 pre-Strategist ranking is a same-candidate-universe control, not a full-market control.",
            "Historical point-in-time sector membership is unavailable.",
            "Repeated windows are converted to per-symbol 15-minute-spaced episodes.",
            "Q16 blocked samples are reported separately to avoid double counting.",
        ],
        "q9_extraction": {key: value for key, value in extraction.items() if key != "windows"},
        "provider_summary": {
            "symbol_count": len(provider_rows),
            "complete_symbol_count": sum(1 for row in provider_rows if row.get("coverage_complete")),
            "rows": provider_rows,
        },
        "candidate_integrity": integrity,
        "episode_count": len(episodes),
        "by_rank_bucket": grouped_horizon_summary(episodes, field="rank_bucket"),
        "by_source_class": by_source_class,
        "by_source": grouped_horizon_summary(episodes, field="sources"),
        "by_time_bucket": grouped_horizon_summary(episodes, field="time_bucket"),
        "source_class_splits": split_summary(
            episodes,
            field="source_class",
            calibration_end=CALIBRATION_END,
            retrospective_start=RETROSPECTIVE_START,
        ),
        "score_component_diagnostics": score_component_diagnostics(episodes),
        "discovery_cohorts": discoveries,
        "quant_shadow_inventory": {
            key: value for key, value in quant_shadow.items() if key != "samples"
        },
        "q16_reference_inventory": {key: value for key, value in q16.items() if key != "samples"},
        "blocked_samples": {
            "sample_count": len(evaluated_shadow),
            "source": "quant_shadow_candidates_15m_spaced_reconstruction",
        },
        "blocked_opportunity_analysis": blocked,
        "path_policy_analysis": simulate_path_policies(
            episodes,
            minute_rows_by_symbol=minute_rows_by_symbol,
        ),
        "path_policy_opening_rank1": simulate_path_policies(
            [
                row
                for row in episodes
                if row.get("time_bucket") == "open_0_20m" and row.get("rank_bucket") == "rank1"
            ],
            minute_rows_by_symbol=minute_rows_by_symbol,
        ),
        "trade_inventory": {key: value for key, value in trades.items() if key != "rows"},
        "actual_trade_analysis": actual_trade_analysis(list(trades.get("rows") or [])),
        "decision_summary": _decision_summary(
            integrity=integrity,
            source_rows=by_source_class,
            blocked=blocked,
            discoveries=discoveries,
        ),
        "episodes": episodes,
    }
    output_dir = output_root / f"{start}_{end}"
    json_path = output_dir / "existing_evidence_mining.json"
    markdown_path = output_dir / "existing_evidence_mining.md"
    _write_json(json_path, payload)
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}
