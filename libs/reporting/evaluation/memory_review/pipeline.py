from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .classifier import aggregate_by_month, aggregate_rows, classify_stage2_row
from .contracts import SCHEMA_VERSION, SYMBOL_MEMORY_MISMATCH
from .forward import (
    attach_historical_forward_outcomes,
    build_forward_comparison,
    load_linked_q9_candidate_rows,
)
from .loaders import (
    load_canonical_strategist,
    load_q9_windows_for_runs,
    load_stage2_records,
    load_trade_outcomes,
)
from .report import render_markdown


def build_memory_contamination_review(
    *,
    reports_root: Path,
    evidence_path: Path,
    start_day: str,
    end_day: str,
    output_root: Path | None = None,
) -> dict[str, Any]:
    stage2_rows = load_stage2_records(
        evidence_path,
        start_day=start_day,
        end_day=end_day,
    )
    q9_by_run = load_q9_windows_for_runs(reports_root, stage2_rows)
    trades_by_run = load_trade_outcomes(
        reports_root,
        start_day=start_day,
        end_day=end_day,
    )
    rows: list[dict[str, Any]] = []
    for stage2 in stage2_rows:
        run_id = str(stage2.get("run_id") or "")
        day = str(stage2.get("day") or "")
        rows.append(
            classify_stage2_row(
                stage2,
                strategist=load_canonical_strategist(
                    reports_root,
                    day=day,
                    run_id=run_id,
                ),
                q9_window=q9_by_run.get(run_id) or {},
                trade_outcomes=trades_by_run.get(run_id) or [],
            )
        )
    cohorts = aggregate_rows(rows)
    project_root = Path(reports_root).parent
    linked_candidates = load_linked_q9_candidate_rows(project_root, rows)
    observed_candidates = attach_historical_forward_outcomes(
        project_root,
        linked_candidates,
    )
    cost_profile = load_broker_cost_profile()
    cost_pct = float(
        cost_profile.get("conservative_round_trip_cost_pct")
        or cost_profile.get("ema_round_trip_cost_pct")
        or 0.0028
    ) * 100.0
    forward_comparison = build_forward_comparison(
        rows,
        observed_candidates,
        cost_pct=cost_pct,
    )
    forward_comparison["cost_source"] = str(cost_profile.get("source") or "fallback")
    forward_comparison["cost_profile_sample_count"] = int(
        cost_profile.get("sample_count") or 0
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "behavior_effect": "historical_reclassification_only",
        "start_day": start_day,
        "end_day": end_day,
        "stage2_call_count": len(rows),
        "day_count": len({row.get("day") for row in rows}),
        "q9_linked_count": sum(bool(row.get("q9_linked")) for row in rows),
        "trusted_trade_count": sum(int(row.get("trusted_trade_count") or 0) for row in rows),
        "cohorts": cohorts,
        "by_month": aggregate_by_month(rows),
        "forward_comparison": forward_comparison,
        "mismatch_examples": [
            row for row in rows if row.get("cohort") == SYMBOL_MEMORY_MISMATCH
        ][:50],
        "rows": rows,
        "authority": {
            "stage2_calls": str(evidence_path),
            "memory_evidence": "reports/canonical/<day>/<run_id>/strategist.json",
            "q9_decisions": "reports/operator_summary/daily/<day>/q9_decision_windows.json",
            "q9_forward_candidates": "data/logs/quant_shadow_candidates/<day>/*_<run_id>.json",
            "historical_minutes": "data/research/post_reclaim_alpha/minute_cache/<symbol>.json",
            "trade_outcomes": "q9_trade_read_model.v1",
        },
        "limitations": [
            "Historical counterfactual decisions cannot be recovered from contaminated calls.",
            "A policy delta and a memory mismatch prove exposure, not sole causal attribution.",
            "Forward-return B/C rows without a direct Stage-2 run link are not forced into a cohort.",
            "Commander C deltas include no-trade as zero and are sensitive to the configured broker cost profile.",
            "Forward comparisons are shadow outcomes, not realized trade PnL.",
        ],
    }
    target_root = output_root or (
        reports_root / "evaluation" / "range" / f"{start_day}_{end_day}"
    )
    target_root.mkdir(parents=True, exist_ok=True)
    json_path = target_root / "memory_contamination_review.json"
    markdown_path = target_root / "memory_contamination_review.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return {
        **payload,
        "artifact_paths": {
            "json": str(json_path),
            "markdown": str(markdown_path),
        },
    }
