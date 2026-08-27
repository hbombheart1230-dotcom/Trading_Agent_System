from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from libs.reporting.broker_closed_trade_reconciler import reconcile_broker_closed_trade_reports

from .artifact_inventory import build_artifact_inventory, iter_trade_dirs, read_json
from .agent_effectiveness_scorecard import write_agent_effectiveness_scorecard
from .attribution_score_v0 import build_attribution_score_v0, render_attribution_score_v0
from .counterfactuals import build_selection_attribution
from .cost_basis_comparison import (
    build_cost_basis_comparison,
    render_cost_basis_comparison,
)
from .daily_scorecard import build_daily_scorecard
from .day_validity import build_q9_day_validity
from .entry_timing_attribution import (
    build_entry_timing_attribution_report,
    render_entry_timing_attribution_report,
)
from .feedback_effectiveness import build_feedback_effectiveness
from .five_day_freeze import build_freeze_manifest
from .markdown import render_daily_scorecard, render_trade_evaluation
from .rolling_scorecard import build_rolling_scorecard
from .horizon_compliance_report import (
    build_horizon_compliance_report,
    render_horizon_compliance_report,
)
from .no_trade_attribution import (
    build_no_trade_attribution_report,
    render_no_trade_attribution_report,
)
from .q16_proxy_rejection_review import (
    build_q16_proxy_rejection_review,
    render_q16_proxy_rejection_review,
)
from .selection_authority_audit import (
    build_selection_authority_audit,
    render_selection_authority_audit,
)
from .scanner_alignment_root_cause import (
    build_scanner_alignment_root_cause_report,
    render_scanner_alignment_root_cause_report,
)
from .start_gate import build_full_chain_start_gate
from .strategist_effectiveness import build_strategist_effectiveness
from .trade_evaluator import evaluate_trade
from .trade_read_model import build_q9_trade_read_model


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _baseline_hash() -> str:
    basis = build_freeze_manifest()
    return hashlib.sha256(json.dumps(basis, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()[:16]


def build_q9_evaluation(reports_root: Path, day: str, *, rolling_windows: tuple[int, ...] = (5, 10, 20)) -> dict[str, Any]:
    reports_root = Path(reports_root)
    evaluation_root = reports_root / "evaluation"
    broker_closed_reconciliation = reconcile_broker_closed_trade_reports(reports_root=reports_root, day=day)
    inventory = build_artifact_inventory(reports_root, day)
    models = [build_q9_trade_read_model(path) for path in iter_trade_dirs(reports_root, day)]
    evaluations = [evaluate_trade(model) for model in models]
    attributions = [build_selection_attribution(model) for model in models]
    q8_path = reports_root / "operator_summary" / "daily" / day / "q8_shadow_blocker_review.json"
    q8_review = read_json(q8_path)
    baseline_hash = _baseline_hash()
    day_validity = build_q9_day_validity(day=day, inventory=inventory)
    start_gate = build_full_chain_start_gate(
        models=models,
        inventory=inventory,
        baseline_hash=baseline_hash,
        day_validity=day_validity,
    )
    scorecard = build_daily_scorecard(
        day=day,
        inventory=inventory,
        trade_evaluations=evaluations,
        attributions=attributions,
        q8_review=q8_review,
        start_gate=start_gate,
        day_validity=day_validity,
    )
    scorecard["generated_at"] = datetime.now(timezone.utc).isoformat()
    scorecard["baseline_hash"] = baseline_hash
    selection_authority = build_selection_authority_audit(models)
    scanner_alignment_root_cause = build_scanner_alignment_root_cause_report(
        day=day,
        models=models,
        evaluations=evaluations,
        selection_authority=selection_authority,
    )
    horizon_compliance = build_horizon_compliance_report(evaluations)
    entry_timing = build_entry_timing_attribution_report(
        day=day,
        models=models,
        reports_root=reports_root,
    )
    attribution_score = build_attribution_score_v0(
        day=day,
        reports_root=reports_root,
        models=models,
        daily_scorecard=scorecard,
        selection_authority=selection_authority,
        horizon_compliance=horizon_compliance,
        entry_timing=entry_timing,
    )
    no_trade_attribution = build_no_trade_attribution_report(
        day=day,
        reports_root=reports_root,
        trade_count=len(models),
    )
    cost_basis_comparison = build_cost_basis_comparison(
        reports_root=reports_root,
        start=day,
        end=day,
    )
    q16_proxy_rejection = build_q16_proxy_rejection_review(
        reports_root=reports_root,
        day=day,
    )

    for trade_dir, model, evaluation, attribution in zip(
        iter_trade_dirs(reports_root, day),
        models,
        evaluations,
        attributions,
    ):
        trade_out = evaluation_root / "trades" / day / str(evaluation.get("trade_id") or trade_dir.name)
        _write_json(trade_out / "trade_read_model.json", model)
        _write_json(trade_out / "selection_attribution.json", attribution)
        _write_json(trade_out / "trade_evaluation.json", evaluation)
        _write_text(trade_out / "trade_evaluation.md", render_trade_evaluation(evaluation))

    daily_out = evaluation_root / "daily" / day
    _write_json(daily_out / "artifact_inventory.json", inventory)
    _write_json(daily_out / "full_chain_start_gate.json", start_gate)
    _write_json(daily_out / "q9_day_validity.json", day_validity)
    _write_json(daily_out / "daily_scorecard.json", scorecard)
    _write_text(daily_out / "daily_scorecard.md", render_daily_scorecard(scorecard))
    _write_json(daily_out / "selection_authority_audit.json", selection_authority)
    _write_text(
        daily_out / "selection_authority_audit.md",
        render_selection_authority_audit(selection_authority),
    )
    _write_json(daily_out / "scanner_alignment_root_cause_report.json", scanner_alignment_root_cause)
    _write_text(
        daily_out / "scanner_alignment_root_cause_report.md",
        render_scanner_alignment_root_cause_report(scanner_alignment_root_cause),
    )
    _write_json(daily_out / "horizon_compliance_report.json", horizon_compliance)
    _write_text(
        daily_out / "horizon_compliance_report.md",
        render_horizon_compliance_report(horizon_compliance),
    )
    _write_json(daily_out / "entry_timing_attribution_report.json", entry_timing)
    _write_text(
        daily_out / "entry_timing_attribution_report.md",
        render_entry_timing_attribution_report(entry_timing),
    )
    _write_json(daily_out / "attribution_score_v0.json", attribution_score)
    _write_text(
        daily_out / "attribution_score_v0.md",
        render_attribution_score_v0(attribution_score),
    )
    _write_json(daily_out / "no_trade_attribution_report.json", no_trade_attribution)
    _write_text(
        daily_out / "no_trade_attribution_report.md",
        render_no_trade_attribution_report(no_trade_attribution),
    )
    _write_json(daily_out / "cost_basis_comparison.json", cost_basis_comparison)
    _write_text(
        daily_out / "cost_basis_comparison.md",
        render_cost_basis_comparison(cost_basis_comparison),
    )
    _write_json(daily_out / "q16_proxy_rejection_review.json", q16_proxy_rejection)
    _write_text(
        daily_out / "q16_proxy_rejection_review.md",
        render_q16_proxy_rejection_review(q16_proxy_rejection),
    )
    from libs.reporting.quant_trade_diagnosis.writer import (
        write_quant_trade_diagnoses_for_day,
    )

    quant_trade_diagnosis = write_quant_trade_diagnoses_for_day(
        reports_root=reports_root,
        day=day,
        models=models,
        evaluations=evaluations,
        attributions=attributions,
        root_cause_report=scanner_alignment_root_cause,
        entry_timing_report=entry_timing,
    )

    daily_scorecards: list[dict[str, Any]] = []
    for path in sorted((evaluation_root / "daily").glob("*/daily_scorecard.json")):
        payload = read_json(path)
        if payload:
            daily_scorecards.append(payload)
    rolling_outputs: list[str] = []
    for window in rolling_windows:
        rolling = build_rolling_scorecard(daily_scorecards, window_days=window)
        rolling_out = evaluation_root / "rolling" / day
        path = rolling_out / f"scorecard_{window}d.json"
        _write_json(path, rolling)
        rolling_outputs.append(str(path))

    evaluation_days = sorted(
        path.name
        for path in (evaluation_root / "trades").iterdir()
        if path.is_dir() and path.name <= day
    )[-20:] if (evaluation_root / "trades").exists() else []
    all_evaluations: list[dict[str, Any]] = []
    all_attributions: list[dict[str, Any]] = []
    all_models: list[dict[str, Any]] = []
    for evaluation_day in evaluation_days:
        for trade_path in sorted((evaluation_root / "trades" / evaluation_day).iterdir()):
            if not trade_path.is_dir():
                continue
            evaluation_payload = read_json(trade_path / "trade_evaluation.json")
            attribution_payload = read_json(trade_path / "selection_attribution.json")
            model_payload = read_json(trade_path / "trade_read_model.json")
            if evaluation_payload:
                all_evaluations.append(evaluation_payload)
            if attribution_payload:
                all_attributions.append(attribution_payload)
            if model_payload:
                all_models.append(model_payload)

    q9_windows: list[dict[str, Any]] = []
    q9_daily_root = reports_root / "operator_summary" / "daily"
    if q9_daily_root.exists():
        q9_days = sorted(
            path.name for path in q9_daily_root.iterdir() if path.is_dir() and path.name <= day
        )[-20:]
        for q9_day in q9_days:
            payload = read_json(q9_daily_root / q9_day / "q9_decision_windows.json")
            for window in list(payload.get("windows") or []):
                if isinstance(window, dict):
                    q9_windows.append(dict(window))

    strategist = build_strategist_effectiveness(all_evaluations, all_attributions, q9_windows)
    strategist["source_days"] = evaluation_days
    feedback = build_feedback_effectiveness(all_models, q9_windows)
    feedback["source_days"] = evaluation_days
    _write_json(evaluation_root / "strategist" / day / "strategist_effectiveness.json", strategist)
    _write_json(evaluation_root / "feedback" / day / "feedback_effectiveness.json", feedback)
    agent_effectiveness = write_agent_effectiveness_scorecard(
        reports_root=reports_root,
        start=day,
        end=day,
        output_dir=evaluation_root / "agent_effectiveness" / day,
    )
    return {
        "day": day,
        "trade_count": len(models),
        "broker_closed_reconciliation": broker_closed_reconciliation,
        "daily_scorecard": str(daily_out / "daily_scorecard.json"),
        "selection_authority_audit": str(daily_out / "selection_authority_audit.json"),
        "scanner_alignment_root_cause_report": str(daily_out / "scanner_alignment_root_cause_report.json"),
        "horizon_compliance_report": str(daily_out / "horizon_compliance_report.json"),
        "entry_timing_attribution_report": str(daily_out / "entry_timing_attribution_report.json"),
        "attribution_score_v0": str(daily_out / "attribution_score_v0.json"),
        "no_trade_attribution_report": str(daily_out / "no_trade_attribution_report.json"),
        "cost_basis_comparison": str(daily_out / "cost_basis_comparison.json"),
        "q16_proxy_rejection_review": str(daily_out / "q16_proxy_rejection_review.json"),
        "quant_trade_diagnosis": quant_trade_diagnosis,
        "full_chain_start_gate": str(daily_out / "full_chain_start_gate.json"),
        "q9_day_validity": str(daily_out / "q9_day_validity.json"),
        "rolling_scorecards": rolling_outputs,
        "strategist_effectiveness": str(evaluation_root / "strategist" / day / "strategist_effectiveness.json"),
        "feedback_effectiveness": str(evaluation_root / "feedback" / day / "feedback_effectiveness.json"),
        "agent_effectiveness_scorecard": agent_effectiveness,
    }
