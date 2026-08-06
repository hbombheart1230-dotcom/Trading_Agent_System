from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .analysis import (
    actual_live_cost_cross_sections,
    casebook,
    delayed_reactivation,
    horizon_cross_sections,
    horizon_reversals,
    opening_cross_sections,
    opening_archetype_analysis,
    precursor_profiles,
    predefined_opening_screens,
    research_candidates,
    themes_cross_sections,
)
from .attribution import diagnose_stage_attribution, stage_attribution_report
from .cohorts import annotate_episode
from .contrasts import conditional_contrast_report
from .horizons import conditional_horizon_report
from .loaders import load_actual_trade_context, load_existing_research
from .loaders import read_json
from .report import render
from .reactivation import build_reactivation_lineage
from .watch_replay import build_reactivation_watch_replay


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    values = [dict(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in values for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in values:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def run_conditional_alpha_diagnosis(
    *,
    reports_root: Path = Path("reports"),
    output_root: Path = Path("reports/evaluation/offline_alpha/conditional_alpha_diagnosis"),
    deep_dive_path: Path = Path("reports/evaluation/offline_alpha/opening_rank1_deep_dive/opening_rank1_deep_dive.json"),
    longitudinal_path: Path = Path("reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.json"),
    horizon_path: Path = Path("reports/evaluation/horizon_revision/2026-08-05/horizon_revision_historical_comparison.json"),
) -> dict[str, str]:
    opening_rows, events, horizon_source = load_existing_research(
        deep_dive_path=deep_dive_path,
        longitudinal_path=longitudinal_path,
        horizon_path=horizon_path,
    )
    longitudinal_payload = read_json(longitudinal_path)
    stage_by_decision = {
        str(row.get("decision_id") or ""): dict(row)
        for row in longitudinal_payload.get("stage_rows") or []
        if isinstance(row, Mapping) and row.get("decision_id")
    }
    stage_fields = (
        "intrinsic_symbol",
        "intrinsic_30m_net_pct",
        "strategist_selected_symbol",
        "intrinsic_post_strategist_rank",
        "strategist_relation",
        "strategist_selected_30m_net_pct",
        "monitor_candidate_symbol",
        "monitor_relation",
        "monitor_candidate_30m_net_pct",
        "commander_decision",
        "commander_reason",
        "executed_trade_id",
        "executed_symbol",
        "executed_30m_net_pct",
        "executed_realized_return_pct",
        "executed_holding_seconds",
        "intrinsic_preserved_to_execution",
    )
    for row in opening_rows:
        stage = stage_by_decision.get(str(row.get("decision_id") or ""), {})
        for field in stage_fields:
            if field in stage:
                row[field] = stage[field]
    opening_rows = [annotate_episode(row) for row in opening_rows]
    events = [annotate_episode(row) for row in events]
    for row in opening_rows:
        row["stage_attribution"] = diagnose_stage_attribution(row)
    for row in events:
        row["stage_attribution"] = diagnose_stage_attribution(row)
    contexts = load_actual_trade_context(reports_root)
    symbol_metadata = {
        str(row.get("symbol") or ""): {
            "symbol_name": row.get("symbol_name"),
            "themes": row.get("themes") or [],
        }
        for row in opening_rows
    }
    for context in contexts.values():
        context.update(symbol_metadata.get(str(context.get("symbol") or ""), {}))
    cross_sections = opening_cross_sections(opening_rows) + themes_cross_sections(opening_rows)
    horizon_rows, horizon_summary = horizon_reversals(horizon_source, contexts)
    reactivation_lineage = build_reactivation_lineage(
        events,
        operator_daily_root=reports_root / "operator_summary" / "daily",
    )
    symbol_names = {
        str(row.get("symbol") or "").zfill(6): row.get("symbol_name")
        for row in opening_rows
        if row.get("symbol_name")
    }
    for row in reactivation_lineage:
        recovered = symbol_names.get(str(row.get("symbol") or "").zfill(6))
        if recovered:
            row["symbol_name"] = recovered
    stage_attribution = stage_attribution_report(opening_rows)
    conditional_horizons = conditional_horizon_report(opening_rows)
    contrasts = conditional_contrast_report(opening_rows)
    watch_replay = build_reactivation_watch_replay(events)
    payload = {
        "schema_version": "conditional_alpha_diagnosis.v1",
        "behavior_effect": "NONE_OFFLINE_RESEARCH_ONLY",
        "coverage": {
            "opening_case_count": len(opening_rows),
            "longitudinal_event_count": len(events),
            "horizon_trade_count": len(horizon_rows),
            "horizon_context_count": sum(bool(contexts.get(str(row.get('trade_id') or ''))) for row in horizon_rows),
        },
        "research_candidates": research_candidates(cross_sections),
        "predefined_opening_screens": predefined_opening_screens(opening_rows),
        "opening_archetypes": opening_archetype_analysis(opening_rows),
        "precursor_profiles": precursor_profiles(opening_rows),
        "cross_sections": cross_sections,
        "horizon_scenario_delta_summary": horizon_summary,
        "horizon_cross_sections": horizon_cross_sections(horizon_rows),
        "actual_live_cost_cross_sections": actual_live_cost_cross_sections(horizon_rows),
        "selection_stage_analysis": longitudinal_payload.get("stage_analysis") or {},
        "scanner_universe_control_analysis": longitudinal_payload.get("universe_control_analysis") or {},
        "delayed_reactivation": delayed_reactivation(events),
        "reactivation_lineage": reactivation_lineage,
        "conditional_stage_attribution": stage_attribution,
        "conditional_horizon_report": conditional_horizons,
        "conditional_contrast_report": contrasts,
        "reactivation_watch_replay": watch_replay,
        "casebook": casebook(opening_rows, horizon_rows, events),
        "limitations": [
            "Opening Rank-1 cases are a narrow 09:00-09:19 cohort.",
            "Forward high and best alternative horizon are oracle upper bounds, not executable policies.",
            "Historical macro and theme coverage is incomplete for some rows.",
            "Research candidates require prospective point-in-time validation before promotion.",
        ],
    }
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / "conditional_alpha_diagnosis.json"
    report_path = output_root / "conditional_alpha_diagnosis.md"
    opening_path = output_root / "opening_episode_rows.csv"
    cross_path = output_root / "conditional_cross_sections.csv"
    horizon_rows_path = output_root / "horizon_alternative_rows.json"
    reactivation_path = output_root / "reactivation_lineage.json"
    episode_context_path = output_root / "conditional_alpha_episode_contexts.json"
    stage_attribution_path = output_root / "conditional_stage_attribution.json"
    conditional_horizon_path = output_root / "conditional_horizon_report.json"
    contrast_path = output_root / "conditional_contrast_report.json"
    watch_replay_path = output_root / "reactivation_watch_replay.json"
    _write_json(summary_path, payload)
    _write_json(horizon_rows_path, horizon_rows)
    _write_json(reactivation_path, reactivation_lineage)
    _write_json(episode_context_path, opening_rows)
    _write_json(stage_attribution_path, stage_attribution)
    _write_json(conditional_horizon_path, conditional_horizons)
    _write_json(contrast_path, contrasts)
    _write_json(watch_replay_path, watch_replay)
    _write_csv(opening_path, opening_rows)
    _write_csv(cross_path, cross_sections)
    report_path.write_text(render(payload), encoding="utf-8")
    return {
        "summary": str(summary_path),
        "report": str(report_path),
        "opening_rows": str(opening_path),
        "cross_sections": str(cross_path),
        "horizon_rows": str(horizon_rows_path),
        "reactivation_lineage": str(reactivation_path),
        "episode_contexts": str(episode_context_path),
        "stage_attribution": str(stage_attribution_path),
        "conditional_horizons": str(conditional_horizon_path),
        "contrasts": str(contrast_path),
        "reactivation_watch_replay": str(watch_replay_path),
    }
