from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .artifact_inventory import read_json
from .counterfactuals import build_selection_attribution
from .metrics import performance_metrics
from .trade_evaluator import evaluate_trade
from .trade_read_model import build_q9_trade_read_model


DEFAULT_BEFORE_DAY = "2026-06-29"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _day_from_trade_dir(trade_dir: Path) -> str:
    parts = list(trade_dir.parts)
    for index, part in enumerate(parts):
        if part == "trades" and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def iter_historical_trade_dirs(
    reports_root: Path,
    *,
    from_day: str = "",
    before_day: str = DEFAULT_BEFORE_DAY,
) -> list[Path]:
    trades_root = Path(reports_root) / "trades"
    if not trades_root.exists():
        return []
    rows: list[Path] = []
    for path in sorted({item.parent for item in trades_root.rglob("lifecycle_bundle.json")}):
        day = _day_from_trade_dir(path)
        if not day:
            continue
        if from_day and day < from_day:
            continue
        if before_day and day >= before_day:
            continue
        rows.append(path)
    return rows


def _net_return(evaluation: dict[str, Any]) -> float | None:
    value = (evaluation.get("realized_outcome") or {}).get("net_return_pct")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rank_bucket(value: Any) -> str:
    try:
        rank = int(float(value))
    except (TypeError, ValueError):
        return "unknown"
    if rank <= 1:
        return "rank1"
    if rank <= 3:
        return "rank2-3"
    if rank <= 10:
        return "rank4-10"
    return "rank11_plus"


def _group_metrics(rows: Iterable[tuple[str, float]]) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for key, value in rows:
        grouped[str(key or "unknown")].append(float(value))
    return {
        key: performance_metrics(values)
        for key, values in sorted(grouped.items())
    }


def summarize_historical_prior(
    *,
    models: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    attributions: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    from_day: str,
    before_day: str,
) -> dict[str, Any]:
    eligible = [
        row for row in evaluations
        if bool((row.get("integrity") or {}).get("promotion_metric_eligible"))
    ]
    returns = [value for value in (_net_return(row) for row in eligible) if value is not None]
    all_returns = [value for value in (_net_return(row) for row in evaluations) if value is not None]
    integrity_counts = Counter(str((row.get("integrity") or {}).get("status") or "unknown") for row in evaluations)
    watch_counts = Counter(
        item
        for row in evaluations
        for item in list((row.get("integrity") or {}).get("watch_items") or [])
    )
    defect_counts = Counter(
        item
        for row in evaluations
        for item in list((row.get("integrity") or {}).get("defects") or [])
    )
    rank_rows: list[tuple[str, float]] = []
    playbook_rows: list[tuple[str, float]] = []
    symbol_rows: list[tuple[str, float]] = []
    horizon_bucket_rows: list[tuple[str, float]] = []
    source_days = sorted({str(row.get("day") or "") for row in evaluations if str(row.get("day") or "")})
    for model, evaluation in zip(models, evaluations):
        value = _net_return(evaluation)
        if value is None:
            continue
        selection = model.get("selection") if isinstance(model.get("selection"), dict) else {}
        horizon = evaluation.get("horizon_alignment") if isinstance(evaluation.get("horizon_alignment"), dict) else {}
        rank_rows.append((_rank_bucket(selection.get("selected_rank")), value))
        playbook_rows.append((selection.get("strategist_playbook") or "unknown", value))
        symbol_rows.append((model.get("symbol") or "unknown", value))
        horizon_bucket_rows.append((horizon.get("bucket") or "unknown", value))
    comparable_attributions = [
        row for row in attributions
        if (row.get("deltas") or {}).get("strategist_delta_pct") is not None
    ]
    return {
        "schema_version": "historical_q9_prior_summary.v1",
        "behavior_effect": "read_only_historical_prior",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "from_day": from_day,
            "before_day": before_day,
            "source": "reports/trades lifecycle_bundle artifacts",
            "official_q9_freeze_sample": False,
            "usage": "prior_evidence_only",
        },
        "coverage": {
            "source_day_count": len(source_days),
            "source_days": source_days,
            "trade_count": len(evaluations),
            "eligible_trade_count": len(eligible),
            "build_error_count": len(errors),
            "integrity_status_counts": dict(integrity_counts),
            "top_watch_items": dict(watch_counts.most_common(20)),
            "top_defects": dict(defect_counts.most_common(20)),
        },
        "performance": {
            "eligible": performance_metrics(returns),
            "all_realized": performance_metrics(all_returns),
        },
        "breakdowns": {
            "selected_rank_bucket": _group_metrics(rank_rows),
            "strategist_playbook": _group_metrics(playbook_rows),
            "symbol": _group_metrics(symbol_rows),
            "horizon_bucket": _group_metrics(horizon_bucket_rows),
        },
        "selection_attribution": {
            "comparison_count": len(comparable_attributions),
            "unavailable_count": len(attributions) - len(comparable_attributions),
            "note": "Historical artifacts often lack Q9-native A/B/C forward controls; use as prior only.",
        },
        "interpretation_guardrails": [
            "Do not merge these rows into the frozen Q9 five-day validation sample.",
            "Do not promote a new tactic from historical_prior alone.",
            "Use this report to decide whether Q9 freeze findings agree with older evidence.",
        ],
        "errors": errors[:50],
    }


def render_historical_prior_markdown(payload: dict[str, Any]) -> str:
    coverage = payload.get("coverage") or {}
    performance = payload.get("performance") or {}
    eligible = performance.get("eligible") or {}
    all_realized = performance.get("all_realized") or {}
    scope = payload.get("scope") or {}
    breakdowns = payload.get("breakdowns") or {}
    lines = [
        "# Historical Q9 Prior",
        "",
        f"- Scope: `{scope.get('from_day') or 'beginning'}` to before `{scope.get('before_day')}`",
        "- Behavior effect: read-only historical prior",
        "- Official Q9 freeze sample: **False**",
        "- Usage: prior evidence only, not promotion evidence by itself",
        "",
        "## Coverage",
        "",
        f"- Source days: {coverage.get('source_day_count', 0)}",
        f"- Trades: {coverage.get('trade_count', 0)} total / {coverage.get('eligible_trade_count', 0)} eligible",
        f"- Build errors: {coverage.get('build_error_count', 0)}",
        f"- Integrity counts: {coverage.get('integrity_status_counts', {})}",
        "",
        "## Performance",
        "",
        f"- Eligible count: {eligible.get('count', 0)}",
        f"- Eligible win rate: {float(eligible.get('win_rate') or 0) * 100:.1f}%",
        f"- Eligible average return: {float(eligible.get('average_return_pct') or 0):.4f}%",
        f"- Eligible profit factor: {eligible.get('profit_factor', 0)}",
        f"- Eligible maximum drawdown: {float(eligible.get('maximum_drawdown_pct') or 0):.4f}%",
        f"- All-realized count: {all_realized.get('count', 0)}",
        f"- All-realized average return: {float(all_realized.get('average_return_pct') or 0):.4f}%",
        "",
        "## Key Breakdowns",
        "",
    ]
    for name in ("selected_rank_bucket", "strategist_playbook", "horizon_bucket"):
        lines.append(f"### {name}")
        rows = breakdowns.get(name) if isinstance(breakdowns.get(name), dict) else {}
        if not rows:
            lines.append("- No comparable rows")
            lines.append("")
            continue
        for key, metrics in rows.items():
            lines.append(
                f"- {key}: count {metrics.get('count', 0)}, "
                f"win {float(metrics.get('win_rate') or 0) * 100:.1f}%, "
                f"avg {float(metrics.get('average_return_pct') or 0):.4f}%, "
                f"PF {metrics.get('profit_factor', 0)}"
            )
        lines.append("")
    lines.extend([
        "## Guardrails",
        "",
        "- This does not reopen Q8.",
        "- This does not extend the Q9 five-valid-day freeze.",
        "- Monday Q9 close remains the authoritative decision point; this report is a tie-breaker and root-cause prior.",
        "",
    ])
    return "\n".join(lines)


def build_historical_q9_prior(
    reports_root: Path,
    *,
    from_day: str = "",
    before_day: str = DEFAULT_BEFORE_DAY,
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    output_root = reports_root / "evaluation" / "historical_q9_prior"
    trade_dirs = iter_historical_trade_dirs(reports_root, from_day=from_day, before_day=before_day)
    models: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    attributions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for trade_dir in trade_dirs:
        try:
            model = build_q9_trade_read_model(trade_dir)
            evaluation = evaluate_trade(model)
            attribution = build_selection_attribution(model)
        except Exception as exc:
            errors.append({
                "trade_dir": str(trade_dir),
                "day": _day_from_trade_dir(trade_dir),
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        models.append(model)
        evaluations.append(evaluation)
        attributions.append(attribution)

    summary = summarize_historical_prior(
        models=models,
        evaluations=evaluations,
        attributions=attributions,
        errors=errors,
        from_day=from_day,
        before_day=before_day,
    )
    _write_json(output_root / "historical_q9_trade_read_models.json", {
        "schema_version": "historical_q9_trade_read_models.v1",
        "behavior_effect": "read_only_historical_prior",
        "rows": models,
    })
    _write_json(output_root / "historical_q9_trade_evaluations.json", {
        "schema_version": "historical_q9_trade_evaluations.v1",
        "behavior_effect": "read_only_historical_prior",
        "rows": evaluations,
    })
    _write_json(output_root / "historical_q9_selection_attributions.json", {
        "schema_version": "historical_q9_selection_attributions.v1",
        "behavior_effect": "read_only_historical_prior",
        "rows": attributions,
    })
    _write_json(output_root / "historical_q9_prior_summary.json", summary)
    _write_text(output_root / "historical_q9_prior_report.md", render_historical_prior_markdown(summary))
    return {
        "ok": True,
        "trade_count": len(models),
        "error_count": len(errors),
        "output_dir": str(output_root),
        "summary": str(output_root / "historical_q9_prior_summary.json"),
        "report": str(output_root / "historical_q9_prior_report.md"),
    }


__all__ = [
    "DEFAULT_BEFORE_DAY",
    "build_historical_q9_prior",
    "iter_historical_trade_dirs",
    "render_historical_prior_markdown",
    "summarize_historical_prior",
]
