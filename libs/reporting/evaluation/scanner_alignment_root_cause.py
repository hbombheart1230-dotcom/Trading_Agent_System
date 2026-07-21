from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .metrics import performance_metrics


ROOT_CAUSES = (
    "Scanner Ranking Failure",
    "Rank Drift",
    "Strategist Override",
    "Candidate Filtering",
    "Symbol Mapping",
    "Missing Evidence",
    "Aligned / No Alignment Issue",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in (value or []) if isinstance(row, Mapping)]


def _num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _symbol(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("symbol") or "").strip()
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _selected_rank(model: Mapping[str, Any]) -> int | None:
    selection = _mapping(model.get("selection"))
    selected_candidate = _mapping(selection.get("selected_candidate"))
    value = _num(selection.get("selected_rank") or selected_candidate.get("rank"))
    return int(value) if value is not None else None


def _score_gap(model: Mapping[str, Any]) -> float | None:
    selection = _mapping(model.get("selection"))
    top1 = _mapping(selection.get("scanner_top1"))
    selected = _mapping(selection.get("selected_candidate"))
    top_score = _num(top1.get("score_total"))
    selected_score = _num(selected.get("score_total"))
    if top_score is None or selected_score is None:
        return None
    return round(top_score - selected_score, 6)


def _outcome_return(evaluation: Mapping[str, Any], model: Mapping[str, Any]) -> float | None:
    value = _num(_mapping(evaluation.get("realized_outcome")).get("net_return_pct"))
    if value is not None:
        return value
    return _num(_mapping(model.get("outcome")).get("net_return_pct"))


def classify_scanner_alignment_root_cause(
    *,
    row: Mapping[str, Any],
    model: Mapping[str, Any],
    net_return_pct: float | None,
) -> dict[str, Any]:
    raw = str(row.get("raw_scanner_top1") or "")
    post = str(row.get("post_strategy_top1") or "")
    selected = str(row.get("selected_symbol") or "")
    executed = str(row.get("executed_symbol") or "")
    rank = _selected_rank(model)
    score_gap = _score_gap(model)
    reasons: list[str] = []

    if not raw or not post or not selected or not executed:
        return {
            "root_cause": "Missing Evidence",
            "confidence": "high",
            "reasons": ["raw/post/selected/executed symbol missing"],
            "selected_rank": rank,
            "score_gap": score_gap,
        }

    if (
        row.get("final_to_executed_changed") is True
        or row.get("monitor_to_commander_changed") is True
        or row.get("selected_to_monitor_changed") is True
    ):
        return {
            "root_cause": "Symbol Mapping",
            "confidence": "high",
            "reasons": ["symbol changed after selection path"],
            "selected_rank": rank,
            "score_gap": score_gap,
        }

    if selected != post and rank is not None and rank > 1:
        reasons.append("selected candidate is below post-strategy top1")
        reasons.append(f"selected_rank={rank}")
        if score_gap is not None:
            reasons.append(f"score_gap={score_gap}")
        return {
            "root_cause": "Candidate Filtering",
            "confidence": "high",
            "reasons": reasons,
            "selected_rank": rank,
            "score_gap": score_gap,
        }

    if raw != post and selected == post:
        return {
            "root_cause": "Strategist Override",
            "confidence": "medium",
            "reasons": ["post-strategy top1 differs from raw top1 and final selection followed post-strategy top1"],
            "selected_rank": rank,
            "score_gap": score_gap,
        }

    if raw != post or (rank is not None and rank > 1):
        reasons.append("top candidate changed or selected rank drifted")
        if raw != post:
            reasons.append("raw_top1_differs_from_post_strategy_top1")
        if rank is not None and rank > 1:
            reasons.append(f"selected_rank={rank}")
        return {
            "root_cause": "Rank Drift",
            "confidence": "medium",
            "reasons": reasons,
            "selected_rank": rank,
            "score_gap": score_gap,
        }

    if net_return_pct is not None and net_return_pct < 0:
        return {
            "root_cause": "Scanner Ranking Failure",
            "confidence": "medium",
            "reasons": ["top-ranked selected candidate produced negative realized return"],
            "selected_rank": rank,
            "score_gap": score_gap,
        }

    return {
        "root_cause": "Aligned / No Alignment Issue",
        "confidence": "medium",
        "reasons": ["raw/post/selected/executed symbols are aligned"],
        "selected_rank": rank,
        "score_gap": score_gap,
    }


def _impact_score(returns: list[float]) -> float:
    return round(sum(value for value in returns if value < 0), 4)


def _largest_cause(
    cause_summary: Sequence[Mapping[str, Any]],
    *,
    excluded: set[str] | None = None,
) -> dict[str, Any]:
    excluded = excluded or set()
    observed = [
        row
        for row in cause_summary
        if int(row.get("trade_count") or 0) > 0 and str(row.get("root_cause") or "") not in excluded
    ]
    return dict(
        max(
            observed,
            key=lambda row: (
                int(row.get("trade_count") or 0),
                abs(float(row.get("negative_impact_pct") or 0.0)),
            ),
            default={},
        )
    )


def _patch_candidate(cause: str) -> str:
    if cause == "Candidate Filtering":
        return "Tighten runner-up/candidate filtering evidence before selecting below post-strategy top1."
    if cause == "Strategist Override":
        return "Audit strategy-context rank adjustments before allowing post-strategy top1 to replace raw top1."
    if cause == "Rank Drift":
        return "Require explicit rank-drift reason and score-gap evidence when Top1 changes."
    if cause == "Scanner Ranking Failure":
        return "Decompose scanner raw score components for aligned losing Top1 trades."
    if cause == "Symbol Mapping":
        return "Fix symbol propagation before any trading behavior patch."
    if cause == "Missing Evidence":
        return "Fix missing selection evidence before interpreting scanner alignment."
    return "No scanner-alignment behavior patch candidate from aligned rows."


def build_scanner_alignment_root_cause_report(
    *,
    day: str,
    models: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    selection_authority: Mapping[str, Any],
) -> dict[str, Any]:
    model_by_trade = {str(model.get("trade_id") or ""): model for model in models}
    evaluation_by_trade = {str(row.get("trade_id") or ""): row for row in evaluations}
    rows: list[dict[str, Any]] = []
    for row in _rows(selection_authority.get("rows")):
        trade_id = str(row.get("trade_id") or "")
        model = _mapping(model_by_trade.get(trade_id))
        evaluation = _mapping(evaluation_by_trade.get(trade_id))
        net_return = _outcome_return(evaluation, model)
        classification = classify_scanner_alignment_root_cause(
            row=row,
            model=model,
            net_return_pct=net_return,
        )
        rows.append(
            {
                "trade_id": trade_id,
                "symbol": row.get("executed_symbol") or row.get("symbol"),
                "raw_scanner_top1": row.get("raw_scanner_top1"),
                "post_strategy_top1": row.get("post_strategy_top1"),
                "selected_symbol": row.get("selected_symbol"),
                "executed_symbol": row.get("executed_symbol"),
                "net_return_pct": net_return,
                "root_cause": classification["root_cause"],
                "confidence": classification["confidence"],
                "selected_rank": classification["selected_rank"],
                "score_gap": classification["score_gap"],
                "reasons": classification["reasons"],
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("root_cause") or "Missing Evidence")].append(row)

    cause_summary: list[dict[str, Any]] = []
    for cause in ROOT_CAUSES:
        cause_rows = grouped.get(cause, [])
        returns = [
            float(row["net_return_pct"])
            for row in cause_rows
            if row.get("net_return_pct") is not None
        ]
        metrics = performance_metrics(returns)
        cause_summary.append(
            {
                "root_cause": cause,
                "trade_count": len(cause_rows),
                "return_observation_count": len(returns),
                "win_rate": metrics["win_rate"],
                "avg_return_pct": metrics["average_return_pct"],
                "profit_factor": metrics["profit_factor"],
                "max_drawdown_pct": metrics["maximum_drawdown_pct"],
                "negative_impact_pct": _impact_score(returns),
            }
        )

    largest = _largest_cause(cause_summary)
    largest_behavior = _largest_cause(
        cause_summary,
        excluded={"Missing Evidence", "Aligned / No Alignment Issue"},
    )
    patch_candidate = _patch_candidate(str(largest_behavior.get("root_cause") or ""))

    return {
        "schema_version": "scanner_alignment_root_cause.v1",
        "evaluation_program_id": "Q14_SCANNER_ALIGNMENT_ROOT_CAUSE",
        "behavior_effect": "observation_only",
        "day": day,
        "trade_count": len(rows),
        "cause_summary": cause_summary,
        "largest_root_cause": largest,
        "largest_observed_root_cause": largest,
        "largest_behavior_root_cause": largest_behavior,
        "q15_behavior_patch_candidate": patch_candidate,
        "rows": rows,
        "interpretation_rule": (
            "Q14 explains why scanner_alignment_score is low. It does not authorize behavior changes. "
            "Q15 may select one behavior patch after reviewing the largest evidence-backed root cause."
        ),
    }


def render_scanner_alignment_root_cause_report(payload: Mapping[str, Any]) -> str:
    lines = [
        f"# Q14 Scanner Alignment Root Cause - {payload.get('day', '')}",
        "",
        f"- Behavior effect: `{payload.get('behavior_effect', '')}`",
        f"- Trades: {payload.get('trade_count', 0)}",
        f"- Largest observed root cause: `{_mapping(payload.get('largest_observed_root_cause') or payload.get('largest_root_cause')).get('root_cause') or '-'}`",
        f"- Largest behavior root cause: `{_mapping(payload.get('largest_behavior_root_cause')).get('root_cause') or '-'}`",
        f"- Q15 candidate: {payload.get('q15_behavior_patch_candidate') or '-'}",
        "",
        "## Root Cause Summary",
        "",
        "| Root Cause | Trades | Return Obs | Win Rate | Avg Return | Profit Factor | MDD | Negative Impact |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("cause_summary") or []:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            f"| {row.get('root_cause')} | {row.get('trade_count')} | "
            f"{row.get('return_observation_count')} | {float(row.get('win_rate') or 0):.1%} | "
            f"{float(row.get('avg_return_pct') or 0):.4f}% | {row.get('profit_factor')} | "
            f"{float(row.get('max_drawdown_pct') or 0):.4f}% | "
            f"{float(row.get('negative_impact_pct') or 0):.4f}% |"
        )
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| Trade | Symbol | Raw Top1 | Post Top1 | Selected | Rank | Return | Root Cause | Reasons |",
            "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in payload.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        reasons = ", ".join(str(reason) for reason in row.get("reasons") or []) or "-"
        value = row.get("net_return_pct")
        lines.append(
            f"| {row.get('trade_id')} | {row.get('symbol') or '-'} | "
            f"{row.get('raw_scanner_top1') or '-'} | {row.get('post_strategy_top1') or '-'} | "
            f"{row.get('selected_symbol') or '-'} | {row.get('selected_rank') or '-'} | "
            f"{'-' if value is None else f'{float(value):.4f}%'} | "
            f"{row.get('root_cause')} | {reasons} |"
        )
    lines.extend(["", "## Interpretation", "", f"- {payload.get('interpretation_rule', '')}", ""])
    return "\n".join(lines)


def _load_day_models_and_evaluations(reports_root: Path, day: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = reports_root / "evaluation" / "trades" / day
    models: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    if not root.exists():
        return models, evaluations
    for trade_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        model = _read_json(trade_dir / "trade_read_model.json")
        evaluation = _read_json(trade_dir / "trade_evaluation.json")
        if model:
            models.append(model)
        if evaluation:
            evaluations.append(evaluation)
    return models, evaluations


def build_scanner_alignment_root_cause_range(
    *,
    reports_root: Path = Path("reports"),
    start: str,
    end: str,
) -> dict[str, Any]:
    from datetime import date, timedelta

    reports_root = Path(reports_root)
    cursor = date.fromisoformat(start)
    final = date.fromisoformat(end)
    daily_payloads: list[dict[str, Any]] = []
    while cursor <= final:
        day = cursor.isoformat()
        selection_authority = _read_json(
            reports_root / "evaluation" / "daily" / day / "selection_authority_audit.json"
        )
        models, evaluations = _load_day_models_and_evaluations(reports_root, day)
        if selection_authority or models or evaluations:
            daily_payloads.append(
                build_scanner_alignment_root_cause_report(
                    day=day,
                    models=models,
                    evaluations=evaluations,
                    selection_authority=selection_authority,
                )
            )
        cursor += timedelta(days=1)

    all_rows = [row for payload in daily_payloads for row in payload.get("rows") or []]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        grouped[str(row.get("root_cause") or "Missing Evidence")].append(row)
    cause_summary: list[dict[str, Any]] = []
    for cause in ROOT_CAUSES:
        cause_rows = grouped.get(cause, [])
        returns = [
            float(row["net_return_pct"])
            for row in cause_rows
            if row.get("net_return_pct") is not None
        ]
        metrics = performance_metrics(returns)
        cause_summary.append(
            {
                "root_cause": cause,
                "trade_count": len(cause_rows),
                "return_observation_count": len(returns),
                "win_rate": metrics["win_rate"],
                "avg_return_pct": metrics["average_return_pct"],
                "profit_factor": metrics["profit_factor"],
                "max_drawdown_pct": metrics["maximum_drawdown_pct"],
                "negative_impact_pct": _impact_score(returns),
            }
        )
    largest = _largest_cause(cause_summary)
    largest_behavior = _largest_cause(
        cause_summary,
        excluded={"Missing Evidence", "Aligned / No Alignment Issue"},
    )
    return {
        "schema_version": "scanner_alignment_root_cause_range.v1",
        "evaluation_program_id": "Q14_SCANNER_ALIGNMENT_ROOT_CAUSE_RANGE",
        "behavior_effect": "observation_only",
        "start": start,
        "end": end,
        "day_count": len(daily_payloads),
        "trade_count": len(all_rows),
        "cause_summary": cause_summary,
        "largest_root_cause": largest,
        "largest_observed_root_cause": largest,
        "largest_behavior_root_cause": largest_behavior,
        "q15_behavior_patch_candidate": _patch_candidate(str(largest_behavior.get("root_cause") or "")),
        "daily_rows": [
            {
                "day": payload.get("day"),
                "trade_count": payload.get("trade_count"),
                "largest_root_cause": _mapping(payload.get("largest_root_cause")).get("root_cause") or "",
            }
            for payload in daily_payloads
        ],
        "rows": all_rows,
        "interpretation_rule": (
            "Range aggregate for Q14. Use this to choose one Q15 candidate after confirming "
            "the largest root cause is evidence-backed."
        ),
    }


def write_scanner_alignment_root_cause_range(
    *,
    reports_root: Path = Path("reports"),
    start: str,
    end: str,
) -> dict[str, str]:
    reports_root = Path(reports_root)
    payload = build_scanner_alignment_root_cause_range(
        reports_root=reports_root,
        start=start,
        end=end,
    )
    out_dir = reports_root / "evaluation" / "range" / f"{start}_{end}"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "scanner_alignment_root_cause_report.json"
    md_path = out_dir / "scanner_alignment_root_cause_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_scanner_alignment_root_cause_report(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "build_scanner_alignment_root_cause_report",
    "render_scanner_alignment_root_cause_report",
    "build_scanner_alignment_root_cause_range",
    "write_scanner_alignment_root_cause_range",
]
