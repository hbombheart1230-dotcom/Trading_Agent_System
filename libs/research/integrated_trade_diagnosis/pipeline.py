from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .io import read_json, write_csv, write_json
from .policies import (
    horizon_summary,
    opening_policy_rows,
    opening_policy_summary,
    reactivation_summary,
    reentry_policy_summary,
)
from .read_model import build_symbol_day_sequences, load_trade_rows
from .report import render
from .validation import prospective_validation
from .prospective import load_prospective_opening_rows


def _opening_day_statuses(
    reports_root: Path,
    *,
    start_day: str,
    end_day: str,
) -> dict[str, str]:
    root = reports_root / "evaluation" / "opening_rank1_shadow"
    statuses = {}
    for path in sorted(root.glob("20??-??-??/opening_rank1_shadow_daily.json")):
        day = path.parent.name
        if not start_day <= day <= end_day:
            continue
        payload = read_json(path)
        statuses[day] = str(payload.get("day_status") or "MISSING")
    return statuses


def _decision_readiness(
    opening: dict[str, Any], validation: dict[str, Any]
) -> dict[str, Any]:
    if str(validation.get("status") or "") == "COMPLETE":
        return {
            "status": "SUPERSEDED_BY_FIVE_SESSION_CLOSURE",
            "leading_candidate": "NONE",
            "reason": (
                "the prospective integration gate completed; the fixed five-session "
                "review closed with no behavior candidate"
            ),
            "authority": "docs/offline_alpha/five_session_closure_2026-08-07.md",
        }
    candidates = []
    for name, payload in opening.items():
        metrics = payload.get("performance") or {}
        if name == "CURRENT_PIPELINE" or int(metrics.get("trade_count") or 0) < 3:
            continue
        candidates.append(
            (
                float(metrics.get("average_return_pct") or -10**9),
                name,
                int(metrics.get("trade_count") or 0),
            )
        )
    if not candidates:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "leading_candidate": "NONE",
            "reason": "no reconstructable shadow policy has at least three outcomes",
        }
    average, name, count = max(candidates)
    return {
        "status": "PROSPECTIVE_VALIDATION_REQUIRED",
        "leading_candidate": name,
        "reason": f"historical N={count}, average={average:.4f}%; validate point-in-time artifacts for 3 days",
    }


def run_integrated_trade_diagnosis(
    *,
    reports_root: Path = Path("reports"),
    longitudinal_path: Path = Path(
        "reports/evaluation/offline_alpha/opening_rank1_longitudinal/"
        "opening_rank1_longitudinal.json"
    ),
    output_root: Path = Path(
        "reports/evaluation/offline_alpha/integrated_trade_diagnosis"
    ),
    start_day: str = "2026-06-01",
    end_day: str = "2026-07-31",
    validation_start_day: str = "2026-08-03",
) -> dict[str, str]:
    longitudinal = read_json(longitudinal_path)
    stage_rows = [
        row
        for row in longitudinal.get("stage_rows") or []
        if isinstance(row, dict) and start_day <= str(row.get("day") or "") <= end_day
    ]
    prospective_rows = load_prospective_opening_rows(
        reports_root,
        start_day=validation_start_day,
        end_day=end_day,
    )
    historical_keys = {
        (str(row.get("decision_id") or ""), str(row.get("symbol") or ""))
        for row in stage_rows
    }
    stage_rows.extend(
        row
        for row in prospective_rows
        if (
            str(row.get("decision_id") or ""),
            str(row.get("symbol") or ""),
        )
        not in historical_keys
    )
    events = [
        row
        for row in longitudinal.get("events") or []
        if isinstance(row, dict) and start_day <= str(row.get("day") or "") <= end_day
    ]
    trades = load_trade_rows(reports_root, start_day=start_day, end_day=end_day)
    sequences = build_symbol_day_sequences(trades)
    opening_rows = opening_policy_rows(stage_rows)
    opening = opening_policy_summary(opening_rows)
    validation = prospective_validation(
        stage_rows=stage_rows,
        opening_rows=opening_rows,
        trade_rows=trades,
        start_day=validation_start_day,
        opening_day_statuses=_opening_day_statuses(
            reports_root,
            start_day=validation_start_day,
            end_day=end_day,
        ),
    )
    lineage_counts = Counter(
        str((row.get("lineage") or {}).get("confidence") or "UNKNOWN")
        for row in trades
    )
    payload = {
        "schema_version": "integrated_trade_diagnosis.v1",
        "behavior_effect": "offline_observation_only",
        "period": {"start_day": start_day, "end_day": end_day},
        "authority": {
            "trade_outcome": "q9_trade_read_model",
            "opening_forward": "opening_rank1_longitudinal",
            "missing_evidence": "do_not_infer",
        },
        "evidence_coverage": {
            "trade_row_count": len(trades),
            "symbol_day_sequence_count": len(sequences),
            "opening_decision_count": len(stage_rows),
            "prospective_opening_decision_count": len(prospective_rows),
            "exact_lineage_count": lineage_counts.get("EXACT", 0),
            "non_exact_lineage_count": len(trades) - lineage_counts.get("EXACT", 0),
            "lineage_by_confidence": dict(lineage_counts),
        },
        "opening_policies": opening,
        "reentry_policies": reentry_policy_summary(sequences),
        "horizon_policies": horizon_summary(trades),
        "reactivation": reactivation_summary(events),
        "decision_readiness": _decision_readiness(opening, validation),
        "runtime_validation_contract": {
            "required_full_trading_days": 3,
            "behavior_changes_allowed": False,
            "required_sections": [
                "trade_rows",
                "exact_stage_lineage",
                "opening_policy_rows",
                "symbol_day_sequences",
                "horizon_post_exit",
                "reactivation_watch",
            ],
            "restart_on_observability_bug": False,
        },
        "prospective_validation": validation,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "report": output_root / "historical_reprocessed_report.md",
        "summary": output_root / "integrated_trade_diagnosis.json",
        "trade_rows": output_root / "trade_thesis_rows.json",
        "sequences": output_root / "symbol_day_sequences.json",
        "opening_rows": output_root / "opening_policy_counterfactuals.json",
        "validation": output_root / "prospective_validation_status.json",
        "trade_csv": output_root / "trade_thesis_rows.csv",
        "sequence_csv": output_root / "symbol_day_sequences.csv",
    }
    write_json(paths["summary"], payload)
    write_json(paths["trade_rows"], {"schema_version": "trade_thesis_rows.v1", "rows": trades})
    write_json(paths["sequences"], {"schema_version": "symbol_day_sequences.v1", "rows": sequences})
    write_json(paths["opening_rows"], {"schema_version": "opening_policy_counterfactuals.v1", "rows": opening_rows})
    write_json(paths["validation"], validation)
    write_csv(paths["trade_csv"], trades)
    write_csv(paths["sequence_csv"], sequences)
    paths["report"].write_text(render(payload), encoding="utf-8")
    return {name: str(path) for name, path in paths.items()}
