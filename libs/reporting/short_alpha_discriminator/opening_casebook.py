from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any, Mapping, Sequence

from .cohorts import independent_day_symbol_rows
from .contracts import LIVE_ROUND_TRIP_COST_PCT
from .metrics import checkpoint_return, number


SHORT_HORIZONS = ("+5m", "+15m", "+30m")
SUCCESS_THRESHOLD_PCT = 1.0


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _checkpoint(episode: Mapping[str, Any], horizon: str) -> dict[str, Any]:
    return _mapping(_mapping(episode.get("checkpoints")).get(horizon))


def classify_opening_case(episode: Mapping[str, Any]) -> dict[str, Any]:
    fixed = {
        horizon: checkpoint_return(episode, horizon)
        for horizon in SHORT_HORIZONS
    }
    observed = {key: value for key, value in fixed.items() if value is not None}
    best_fixed_horizon = max(observed, key=observed.get) if observed else ""
    best_fixed = observed.get(best_fixed_horizon) if best_fixed_horizon else None
    mfe_values = [
        number(_checkpoint(episode, horizon).get("mfe_pct"))
        for horizon in SHORT_HORIZONS
    ]
    best_mfe_gross = max((value for value in mfe_values if value is not None), default=None)
    best_mfe_net = (
        round(best_mfe_gross - LIVE_ROUND_TRIP_COST_PCT, 4)
        if best_mfe_gross is not None
        else None
    )
    if best_fixed is not None and best_fixed >= SUCCESS_THRESHOLD_PCT:
        label = "FIXED_HORIZON_SUCCESS"
    elif best_fixed is not None and best_fixed > 0.0:
        label = "POSITIVE_SUBTHRESHOLD"
    elif best_mfe_net is not None and best_mfe_net >= SUCCESS_THRESHOLD_PCT:
        label = "MFE_NEAR_SUCCESS_PROFIT_FADE"
    else:
        label = "NON_QUALIFYING"
    return {
        "label": label,
        "best_fixed_horizon": best_fixed_horizon,
        "best_fixed_net_return_pct": best_fixed,
        "best_mfe_gross_pct": best_mfe_gross,
        "best_mfe_net_proxy_pct": best_mfe_net,
        "fixed_returns": fixed,
    }


def _case_row(joined: Mapping[str, Any]) -> dict[str, Any]:
    episode = _mapping(joined.get("episode"))
    feature = _mapping(joined.get("feature"))
    identity = _mapping(feature.get("identity"))
    market = _mapping(feature.get("market"))
    scanner = _mapping(feature.get("scanner"))
    strategy = _mapping(feature.get("strategy"))
    observation = _mapping(episode.get("opening_observability"))
    candidate = _mapping(observation.get("candidate_snapshot"))
    compact = _mapping(candidate.get("compact_feature_snapshot"))
    classification = classify_opening_case(episode)
    return {
        "label": classification["label"],
        "day": joined.get("day"),
        "decision_time_kst": episode.get("decision_time_kst") or identity.get("decision_time_kst"),
        "symbol": joined.get("symbol"),
        "symbol_name": identity.get("symbol_name") or _mapping(observation.get("asset_observation")).get("symbol_name"),
        "asset_class": joined.get("asset_class"),
        "decision_from_open_sec": observation.get("decision_from_open_sec"),
        "reference_entry_delay_sec": observation.get("reference_entry_delay_sec"),
        "scanner": {
            "score_total": scanner.get("score_total", joined.get("score_total")),
            "risk_score": scanner.get("risk_score", episode.get("risk_score")),
            "risk_band": joined.get("risk_band"),
            "confidence": scanner.get("confidence", candidate.get("confidence")),
            "candidate_setup": joined.get("candidate_setup"),
            "sources": joined.get("sources") or [],
            "relative_volume": scanner.get("relative_volume", observation.get("opening_relative_volume")),
            "score_breakdown": _mapping(scanner.get("score_breakdown") or episode.get("score_breakdown")),
        },
        "strategy": {
            "scenario": strategy.get("scenario"),
            "playbook": strategy.get("playbook"),
            "tactic_id": joined.get("tactic_id"),
            "entry_horizon": joined.get("entry_horizon"),
            "theme_match": scanner.get("theme_match"),
            "matched_theme_names": scanner.get("matched_theme_names") or [],
            "theme_evidence_status": scanner.get("theme_evidence_status"),
        },
        "market": {
            "snapshot_status": market.get("snapshot_evidence_status") or _mapping(observation.get("market_snapshot")).get("evidence_status"),
            "snapshot_age_sec": market.get("snapshot_age_sec", _mapping(observation.get("market_snapshot")).get("snapshot_age_sec")),
            "kospi_pct": market.get("kospi_pct"),
            "kosdaq_pct": market.get("kosdaq_pct"),
            "kospi200_pct": market.get("kospi200_pct"),
            "krx_night_futures_pct": market.get("krx_night_futures_pct"),
            "nasdaq_pct": market.get("nasdaq_pct"),
            "vix_level": market.get("vix_level"),
            "engine_regime": market.get("engine_regime"),
        },
        "chart_and_flow": {
            "completed_return_1m_pct": observation.get("completed_return_1m_pct"),
            "opening_relative_volume": observation.get("opening_relative_volume"),
            "above_vwap": observation.get("above_vwap"),
            "entry_vs_open_pct": observation.get("reference_entry_vs_open_pct"),
            "intraday_change_pct": compact.get("intraday_change_pct"),
            "quote_status": _mapping(observation.get("quote_snapshot")).get("status"),
        },
        "outcome": classification,
    }


def _average(rows: Sequence[Mapping[str, Any]], path: tuple[str, ...]) -> float | None:
    values = []
    for row in rows:
        value: Any = row
        for key in path:
            value = _mapping(value).get(key)
        parsed = number(value)
        if parsed is not None:
            values.append(parsed)
    return round(mean(values), 4) if values else None


def build_opening_overshoot_casebook(joined: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    independent = independent_day_symbol_rows(joined)
    rows = [_case_row(row) for row in independent]
    qualifying = [row for row in rows if row["label"] != "NON_QUALIFYING"]
    qualifying.sort(
        key=lambda row: number(_mapping(row.get("outcome")).get("best_fixed_net_return_pct")) or -999.0,
        reverse=True,
    )
    labels = Counter(str(row.get("label")) for row in rows)
    feature_summary = []
    for label in ("FIXED_HORIZON_SUCCESS", "POSITIVE_SUBTHRESHOLD", "MFE_NEAR_SUCCESS_PROFIT_FADE", "NON_QUALIFYING"):
        group = [row for row in rows if row.get("label") == label]
        feature_summary.append({
            "label": label,
            "case_count": len(group),
            "avg_best_fixed_net_return_pct": _average(group, ("outcome", "best_fixed_net_return_pct")),
            "avg_best_mfe_net_proxy_pct": _average(group, ("outcome", "best_mfe_net_proxy_pct")),
            "avg_scanner_score": _average(group, ("scanner", "score_total")),
            "avg_risk_score": _average(group, ("scanner", "risk_score")),
            "avg_opening_relative_volume": _average(group, ("chart_and_flow", "opening_relative_volume")),
            "avg_decision_from_open_sec": _average(group, ("decision_from_open_sec",)),
        })
    return {
        "schema_version": "opening_overshoot_casebook.v1",
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "scope": "OPENING_RANK1_09_00_TO_09_20",
        "dedup_policy": "FIRST_EPISODE_PER_DAY_SYMBOL",
        "classification_contract": {
            "live_round_trip_cost_pct": LIVE_ROUND_TRIP_COST_PCT,
            "fixed_horizons": list(SHORT_HORIZONS),
            "success": "best fixed live-net return >= 1.0%",
            "positive_subthreshold": "best fixed live-net return > 0% and < 1.0%",
            "mfe_near_success_profit_fade": "best MFE minus live cost >= 1.0%, but all fixed checkpoints <= 0%",
        },
        "source_episode_count": len(joined),
        "independent_case_count": len(rows),
        "qualifying_case_count": len(qualifying),
        "label_counts": dict(labels),
        "feature_summary": feature_summary,
        "cases": qualifying,
        "non_qualifying_count": labels.get("NON_QUALIFYING", 0),
    }


def render_opening_overshoot_casebook(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Opening Overshoot Success And Near-Success Casebook",
        "",
        "- Scope: Rank-1 decisions from 09:00 through 09:20 only",
        "- Behavior effect: observation only",
        f"- Deduplication: `{payload.get('dedup_policy')}`",
        f"- Source episodes: **{int(payload.get('source_episode_count') or 0)}**",
        f"- Independent day-symbol cases: **{int(payload.get('independent_case_count') or 0)}**",
        f"- Success/near-success cases: **{int(payload.get('qualifying_case_count') or 0)}**",
        "",
        "## Fixed Classification",
        "",
        "- `FIXED_HORIZON_SUCCESS`: best +5/+15/+30 live-net return >= 1.0%",
        "- `POSITIVE_SUBTHRESHOLD`: best fixed live-net return is positive but below 1.0%",
        "- `MFE_NEAR_SUCCESS_PROFIT_FADE`: tradable path exceeded 1.0% net proxy but fixed checkpoints failed to retain it",
        "",
        "## Feature Summary",
        "",
        "| Label | N | Best fixed | Best MFE net proxy | Scanner | Risk | Rel volume | Open sec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("feature_summary") or []:
        def cell(key: str) -> str:
            value = row.get(key)
            return "-" if value is None else f"{float(value):.4f}"
        lines.append(
            f"| `{row.get('label')}` | {int(row.get('case_count') or 0)} | "
            f"{cell('avg_best_fixed_net_return_pct')}% | {cell('avg_best_mfe_net_proxy_pct')}% | "
            f"{cell('avg_scanner_score')} | {cell('avg_risk_score')} | "
            f"{cell('avg_opening_relative_volume')} | {cell('avg_decision_from_open_sec')} |"
        )
    lines.extend([
        "",
        "## Cases",
        "",
        "| Label | Date/time | Symbol | Name | Asset | Setup | Strategy | Score | Risk | Rel vol | KOSPI | KOSDAQ | +5m | +15m | +30m | Best MFE net |",
        "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in payload.get("cases") or []:
        scanner = _mapping(row.get("scanner"))
        strategy = _mapping(row.get("strategy"))
        market = _mapping(row.get("market"))
        flow = _mapping(row.get("chart_and_flow"))
        outcome = _mapping(row.get("outcome"))
        fixed = _mapping(outcome.get("fixed_returns"))
        def value(raw: Any, suffix: str = "") -> str:
            parsed = number(raw)
            return "-" if parsed is None else f"{parsed:+.4f}{suffix}"
        lines.append(
            f"| `{row.get('label')}` | {row.get('decision_time_kst') or row.get('day')} | "
            f"{row.get('symbol')} | {row.get('symbol_name') or '-'} | {row.get('asset_class')} | "
            f"{scanner.get('candidate_setup')} | {strategy.get('tactic_id')}/{strategy.get('entry_horizon')} | "
            f"{value(scanner.get('score_total'))} | {value(scanner.get('risk_score'))} | "
            f"{value(flow.get('opening_relative_volume'))} | {value(market.get('kospi_pct'), '%')} | "
            f"{value(market.get('kosdaq_pct'), '%')} | {value(fixed.get('+5m'), '%')} | "
            f"{value(fixed.get('+15m'), '%')} | {value(fixed.get('+30m'), '%')} | "
            f"{value(outcome.get('best_mfe_net_proxy_pct'), '%')} |"
        )
    lines.extend([
        "",
        "Missing market, theme, quote, or volume fields remain missing; this report does not infer or backfill causal evidence.",
        "No row authorizes an entry, exit, sizing, ranking, or execution change.",
        "",
    ])
    return "\n".join(lines)
