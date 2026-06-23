from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

from libs.reporting.q8_evaluation_contract import dedupe_q8_candidates
from libs.reporting.quant_shadow_candidate_evaluation import (
    build_quant_shadow_candidate_evaluation,
    load_quant_shadow_candidate_payloads_for_range,
)
from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes

from .artifact_inventory import iter_trade_dirs
from .metrics import performance_metrics
from .trade_read_model import build_q9_trade_read_model


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _iter_days(start: str, end: str) -> Iterable[str]:
    current = date.fromisoformat(start[:10])
    final = date.fromisoformat(end[:10])
    while current <= final:
        yield current.isoformat()
        current += timedelta(days=1)


def _checkpoint_return(row: Mapping[str, Any], label: str) -> float | None:
    outcome = row.get("shadow_forward_outcome")
    outcome = outcome if isinstance(outcome, Mapping) else {}
    checkpoints = outcome.get("checkpoints")
    checkpoints = checkpoints if isinstance(checkpoints, Mapping) else {}
    checkpoint = checkpoints.get(label)
    if not isinstance(checkpoint, Mapping) or checkpoint.get("status") != "observed":
        return None
    return _to_float(checkpoint.get("return_pct"))


def _rank_bucket(value: Any) -> str:
    try:
        rank = int(float(value))
    except (TypeError, ValueError):
        return "unknown"
    if rank == 1:
        return "rank1"
    if rank <= 3:
        return "rank2-3"
    if rank <= 5:
        return "rank4-5"
    if rank <= 10:
        return "rank6-10"
    return "rank11+"


def _candidate_rows(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        generated_at = payload.get("generated_at")
        for raw in payload.get("candidates") or []:
            if not isinstance(raw, Mapping):
                continue
            row = dict(raw)
            row.setdefault("_payload_generated_at", generated_at)
            rows.append(row)
    return dedupe_q8_candidates(attach_forward_outcomes(rows))


def _group_forward(rows: list[dict[str, Any]], key_fn: Any) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(key_fn(row) or "unknown")].append(row)
    out: list[dict[str, Any]] = []
    for name, members in groups.items():
        result: dict[str, Any] = {
            "name": name,
            "candidate_count": len(members),
        }
        observed_any: set[int] = set()
        for label in ("+5m", "+15m", "+30m", "+60m"):
            values: list[float] = []
            for index, row in enumerate(members):
                value = _checkpoint_return(row, label)
                if value is None:
                    continue
                observed_any.add(index)
                values.append(value)
            result[f"observed_{label[1:-1]}m"] = len(values)
            result[f"avg_return_{label[1:-1]}m_pct"] = (
                round(sum(values) / len(values), 4) if values else None
            )
        result["observed_count"] = len(observed_any)
        result["coverage"] = round(len(observed_any) / len(members), 4) if members else 0.0
        out.append(result)
    return sorted(out, key=lambda row: (-int(row["observed_count"]), row["name"]))


def _load_trade_models(reports_root: Path, start: str, end: str) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    for day in _iter_days(start, end):
        models.extend(build_q9_trade_read_model(path) for path in iter_trade_dirs(reports_root, day))
    return models


def _realized_trade_summary(models: list[dict[str, Any]]) -> dict[str, Any]:
    returns: list[float] = []
    by_rank: dict[str, list[float]] = defaultdict(list)
    selection_mismatch = 0
    for model in models:
        value = _to_float((model.get("outcome") or {}).get("net_return_pct"))
        if value is None:
            continue
        returns.append(value)
        selection = model.get("selection") or {}
        by_rank[_rank_bucket(selection.get("selected_rank"))].append(value)
        scanner_top1 = selection.get("scanner_top1")
        scanner_top1 = scanner_top1 if isinstance(scanner_top1, Mapping) else {}
        if scanner_top1.get("symbol") and selection.get("selected_symbol") != scanner_top1.get("symbol"):
            selection_mismatch += 1
    return {
        "performance": performance_metrics(returns),
        "by_executed_rank": [
            {"rank_bucket": name, **performance_metrics(values)}
            for name, values in sorted(by_rank.items())
        ],
        "scanner_top1_execution_mismatch_count": selection_mismatch,
        "comparable_trade_count": len(returns),
    }


def _entry_timing_summary(
    models: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        base = row.get("shadow_forward_base")
        base = base if isinstance(base, Mapping) else {}
        epoch = int(_to_float(base.get("baseline_epoch")) or 0)
        price = _to_float(base.get("baseline_price"))
        if epoch > 0 and price and price > 0:
            by_symbol[str(row.get("symbol") or "")].append(row)
    for rows in by_symbol.values():
        rows.sort(key=lambda row: int((row.get("shadow_forward_base") or {}).get("baseline_epoch") or 0))

    deltas: list[float] = []
    matched: list[dict[str, Any]] = []
    matched_days: set[str] = set()
    for model in models:
        entry = model.get("entry") or {}
        entry_ts = _parse_ts(entry.get("timestamp"))
        entry_price = _to_float(entry.get("price"))
        symbol = str(model.get("symbol") or "")
        if entry_ts is None or entry_price is None or entry_price <= 0:
            continue
        epoch = int(entry_ts.timestamp())
        eligible = []
        for row in by_symbol.get(symbol, []):
            base = row.get("shadow_forward_base") or {}
            base_epoch = int(base.get("baseline_epoch") or 0)
            if 0 <= epoch - base_epoch <= 15 * 60:
                eligible.append(row)
        if not eligible:
            continue
        candidate = eligible[-1]
        base = candidate.get("shadow_forward_base") or {}
        baseline_price = _to_float(base.get("baseline_price"))
        if baseline_price is None or baseline_price <= 0:
            continue
        delta = ((entry_price / baseline_price) - 1.0) * 100.0
        deltas.append(delta)
        matched_days.add(str(model.get("day") or "")[:10])
        matched.append({
            "trade_id": model.get("trade_id"),
            "symbol": symbol,
            "baseline_epoch": base.get("baseline_epoch"),
            "baseline_price": baseline_price,
            "entry_price": entry_price,
            "entry_price_delta_pct": round(delta, 4),
            "candidate_reason": candidate.get("reason"),
        })
    return {
        "matched_trade_count": len(matched),
        "matched_day_count": len({day for day in matched_days if day}),
        "average_entry_price_delta_pct": round(sum(deltas) / len(deltas), 4) if deltas else None,
        "median_entry_price_delta_pct": round(median(deltas), 4) if deltas else None,
        "late_entry_count": sum(1 for value in deltas if value > 0.3),
        "better_entry_count": sum(1 for value in deltas if value < -0.3),
        "examples": matched[:20],
        "limitation": "matched to nearest same-symbol shadow baseline within 15 minutes; diagnostic only",
    }


def _exit_hold_summary(models: list[dict[str, Any]]) -> dict[str, Any]:
    improvements: dict[str, list[float]] = defaultdict(list)
    examples: list[dict[str, Any]] = []
    observed_trade_count = 0
    observed_days: set[str] = set()
    for model in models:
        realized = _to_float((model.get("outcome") or {}).get("net_return_pct"))
        post_exit = (model.get("monitor") or {}).get("post_exit")
        post_exit = post_exit if isinstance(post_exit, Mapping) else {}
        checkpoints = post_exit.get("checkpoints")
        checkpoints = checkpoints if isinstance(checkpoints, Mapping) else {}
        trade_values: dict[str, float] = {}
        for label in ("+5m", "+15m", "+30m", "+60m"):
            row = checkpoints.get(label)
            if not isinstance(row, Mapping) or row.get("status") != "observed":
                continue
            ratio = _to_float(row.get("return_pct"))
            if ratio is None:
                continue
            delta_pct = ratio * 100.0
            improvements[label].append(delta_pct)
            trade_values[label] = round(delta_pct, 4)
        if trade_values:
            observed_trade_count += 1
            observed_days.add(str(model.get("day") or "")[:10])
            examples.append({
                "trade_id": model.get("trade_id"),
                "symbol": model.get("symbol"),
                "realized_net_return_pct": realized,
                "hold_improvement_pct": trade_values,
            })
    return {
        "observed_trade_count": observed_trade_count,
        "observed_day_count": len({day for day in observed_days if day}),
        "by_hold_offset": [
            {
                "offset": label,
                "count": len(values),
                "average_improvement_pct": round(sum(values) / len(values), 4),
                "improved_count": sum(1 for value in values if value > 0),
                "worsened_count": sum(1 for value in values if value < 0),
            }
            for label, values in improvements.items()
        ],
        "examples": examples[:20],
        "limitation": "price delta after actual exit; realized fees remain fixed and re-entry is not assumed",
    }


def _diagnosis(
    *,
    shadow: dict[str, Any],
    candidate_rank: list[dict[str, Any]],
    realized: dict[str, Any],
    entry: dict[str, Any],
    exit_hold: dict[str, Any],
) -> list[dict[str, Any]]:
    lane_rows = ((shadow.get("entry_lane_forward_outcomes") or {}).get("by_time_bucket") or [])
    buckets = {row.get("name"): row for row in lane_rows if isinstance(row, Mapping)}
    opening = buckets.get("open_20_60m") or {}
    mid = buckets.get("mid_session") or {}
    findings = [
        {
            "stage": "raw_candidate_edge",
            "status": "CONDITIONAL_EDGE",
            "finding": (
                "Candidate edge is horizon- and time-bucket dependent, not universally absent. "
                f"open_20_60m +30m={opening.get('avg_return_30m_pct')}%, "
                f"+60m={opening.get('avg_return_60m_pct')}%; "
                f"mid_session +30m={mid.get('avg_return_30m_pct')}%, "
                f"+60m={mid.get('avg_return_60m_pct')}%."
            ),
        },
        {
            "stage": "scanner_ranking",
            "status": "PARTIAL_RECONSTRUCTION",
            "finding": (
                "Shadow rank/role outcomes are available, but a true pre-Strategist Scanner "
                "control universe is unavailable. Ranking quality can be diagnosed but not "
                "causally attributed to Strategist yet."
            ),
        },
        {
            "stage": "strategist_commander",
            "status": "MISSING_CONTROL",
            "finding": (
                "Historical raw Scanner and explicit Commander alternatives were not persisted. "
                "No value-add claim is allowed."
            ),
        },
        {
            "stage": "monitor_entry",
            "status": "DIAGNOSTIC",
            "finding": (
                f"{entry.get('matched_trade_count')} trades matched a nearby shadow baseline; "
                f"average entry price delta={entry.get('average_entry_price_delta_pct')}%."
            ),
        },
        {
            "stage": "monitor_exit",
            "status": "DIAGNOSTIC",
            "finding": (
                f"Post-exit hold alternatives were observed for {exit_hold.get('observed_trade_count')} trades."
            ),
        },
        {
            "stage": "realized_system",
            "status": "NEGATIVE",
            "finding": (
                f"Realized count={realized.get('performance', {}).get('count')}, "
                f"expectancy={realized.get('performance', {}).get('expectancy_pct')}%, "
                f"profit_factor={realized.get('performance', {}).get('profit_factor')}."
            ),
        },
    ]
    return findings


def _next_action(
    *,
    role_rows: list[dict[str, Any]],
    realized: dict[str, Any],
    exit_hold: dict[str, Any],
) -> dict[str, Any]:
    roles = {str(row.get("name") or ""): row for row in role_rows}
    top_pick = roles.get("top_pick") or {}
    realized_expectancy = _to_float((realized.get("performance") or {}).get("expectancy_pct"))
    five_minute_exit = next(
        (
            row for row in exit_hold.get("by_hold_offset") or []
            if row.get("offset") == "+5m"
        ),
        {},
    )
    return {
        "priority": 1,
        "component": "candidate_edge_and_horizon_alignment",
        "decision": "FIX_BEFORE_ENTRY_OR_EXIT_TUNING",
        "reason": (
            "Top-pick gross forward edge is economically trivial relative to current round-trip "
            "cost, while the realized system is deeply negative. Exit delay improvement is too "
            "small to rescue the deficit."
        ),
        "evidence": {
            "top_pick_15m_pct": top_pick.get("avg_return_15m_pct"),
            "top_pick_30m_pct": top_pick.get("avg_return_30m_pct"),
            "top_pick_60m_pct": top_pick.get("avg_return_60m_pct"),
            "realized_expectancy_pct": realized_expectancy,
            "post_exit_5m_average_improvement_pct": five_minute_exit.get("average_improvement_pct"),
        },
        "required_follow_up": [
            "separate candidate scoring by time bucket and intended holding horizon",
            "treat mid-session candidate generation as a distinct negative-edge segment",
            "evaluate open_20_60m continuation against 30-60 minute holding targets",
            "do not tune exits first",
            "do not attribute the problem to Strategist until a trusted raw Scanner control exists",
        ],
        "behavior_change_authorized": False,
    }


def build_loss_decomposition(*, reports_root: Path, start: str, end: str) -> dict[str, Any]:
    payloads = load_quant_shadow_candidate_payloads_for_range(
        reports_root=reports_root,
        start=start,
        end=end,
    )
    shadow = build_quant_shadow_candidate_evaluation(payloads)
    candidates = _candidate_rows(payloads)
    models = _load_trade_models(reports_root, start, end)
    rank_rows = _group_forward(candidates, lambda row: _rank_bucket(row.get("rank")))
    role_rows = _group_forward(candidates, lambda row: row.get("shadow_role"))
    tactic_rows = _group_forward(candidates, lambda row: row.get("quant_tactic_id"))
    realized = _realized_trade_summary(models)
    entry = _entry_timing_summary(models, candidates)
    exit_hold = _exit_hold_summary(models)
    observed_days = sorted({
        str(day)
        for row in ((shadow.get("entry_lane_forward_outcomes") or {}).get("by_time_bucket") or [])
        if isinstance(row, Mapping)
        for day in row.get("observed_days") or []
    })
    return {
        "schema_version": "full_chain_loss_decomposition.v1",
        "behavior_effect": "evaluation_only",
        "range": {"start": start[:10], "end": end[:10]},
        "evidence": {
            "shadow_payload_count": len(payloads),
            "raw_shadow_candidate_count": shadow.get("candidate_count"),
            "deduped_shadow_candidate_count": shadow.get("deduped_candidate_count"),
            "trusted_forward_count": shadow.get("forward_outcome_available_count"),
            "trusted_forward_coverage": shadow.get("forward_outcome_coverage"),
            "trusted_forward_observed_days": observed_days,
            "trade_model_count": len(models),
        },
        "raw_candidate_edge": {
            "by_time_bucket": ((shadow.get("entry_lane_forward_outcomes") or {}).get("by_time_bucket") or []),
            "by_lane": ((shadow.get("entry_lane_forward_outcomes") or {}).get("by_primary_lane") or []),
            "by_tactic": tactic_rows,
        },
        "scanner_ranking": {
            "by_rank_bucket": rank_rows,
            "by_selection_role": role_rows,
            "control_status": "RECONSTRUCTED_ONLY",
        },
        "strategist_commander": {
            "status": "UNAVAILABLE",
            "reason": "true pre-Strategist Scanner control and explicit Commander alternative outcomes were not historically persisted",
        },
        "monitor_entry": entry,
        "monitor_exit": exit_hold,
        "realized_system": realized,
        "diagnosis": _diagnosis(
            shadow=shadow,
            candidate_rank=rank_rows,
            realized=realized,
            entry=entry,
            exit_hold=exit_hold,
        ),
        "next_action": _next_action(
            role_rows=role_rows,
            realized=realized,
            exit_hold=exit_hold,
        ),
    }


def render_loss_decomposition(payload: Mapping[str, Any]) -> str:
    date_range = payload.get("range") or {}
    evidence = payload.get("evidence") or {}
    realized = payload.get("realized_system") or {}
    performance = realized.get("performance") or {}
    lines = [
        f"# Full-Chain Loss Decomposition ({date_range.get('start')} ~ {date_range.get('end')})",
        "",
        "This report is evaluation-only and does not change trading behavior.",
        "",
        "## Evidence",
        "",
        f"- shadow payloads: {evidence.get('shadow_payload_count')}",
        f"- raw/deduped candidates: {evidence.get('raw_shadow_candidate_count')} / {evidence.get('deduped_shadow_candidate_count')}",
        f"- trusted forward: {evidence.get('trusted_forward_count')} ({float(evidence.get('trusted_forward_coverage') or 0):.1%})",
        f"- trusted forward observed days: {', '.join(evidence.get('trusted_forward_observed_days') or []) or '-'}",
        f"- trade models: {evidence.get('trade_model_count')}",
        "",
        "## Stage Diagnosis",
        "",
        "| Stage | Status | Finding |",
        "|---|---|---|",
    ]
    for row in payload.get("diagnosis") or []:
        lines.append(f"| {row.get('stage')} | `{row.get('status')}` | {row.get('finding')} |")
    lines += [
        "",
        "## Candidate Edge By Time Bucket",
        "",
        "| Bucket | Observed | +5m | +15m | +30m | +60m |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in (payload.get("raw_candidate_edge") or {}).get("by_time_bucket") or []:
        lines.append(
            f"| {row.get('name')} | {row.get('observed_count')} | "
            f"{row.get('avg_return_5m_pct')} | {row.get('avg_return_15m_pct')} | "
            f"{row.get('avg_return_30m_pct')} | {row.get('avg_return_60m_pct')} |"
        )
    lines += [
        "",
        "## Shadow Rank Buckets",
        "",
        "| Rank | Observed | +5m | +15m | +30m | +60m |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in (payload.get("scanner_ranking") or {}).get("by_rank_bucket") or []:
        lines.append(
            f"| {row.get('name')} | {row.get('observed_count')} | "
            f"{row.get('avg_return_5m_pct')} | {row.get('avg_return_15m_pct')} | "
            f"{row.get('avg_return_30m_pct')} | {row.get('avg_return_60m_pct')} |"
        )
    lines += [
        "",
        "## Realized System",
        "",
        f"- count: {performance.get('count')}",
        f"- win rate: {performance.get('win_rate')}",
        f"- average return: {performance.get('average_return_pct')}%",
        f"- expectancy: {performance.get('expectancy_pct')}%",
        f"- profit factor: {performance.get('profit_factor')}",
        f"- maximum drawdown: {performance.get('maximum_drawdown_pct')}%",
        "",
        "## Monitor Entry",
        "",
        f"- matched trades: {(payload.get('monitor_entry') or {}).get('matched_trade_count')}",
        f"- average entry price delta: {(payload.get('monitor_entry') or {}).get('average_entry_price_delta_pct')}%",
        f"- late entries over +0.3%: {(payload.get('monitor_entry') or {}).get('late_entry_count')}",
        "",
        "## Monitor Exit Hold Alternatives",
        "",
        "| Offset | Count | Average improvement | Improved | Worsened |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in (payload.get("monitor_exit") or {}).get("by_hold_offset") or []:
        lines.append(
            f"| {row.get('offset')} | {row.get('count')} | "
            f"{row.get('average_improvement_pct')}% | {row.get('improved_count')} | "
            f"{row.get('worsened_count')} |"
        )
    lines += [
        "",
        "## Fixed Interpretation",
        "",
        "- Do not patch every component at once.",
        "- Fix the first stage with a demonstrated loss of edge.",
        "- Strategist and Commander remain unjudged until trusted controls exist.",
        "- Reconstructed evidence is diagnostic and cannot promote behavior.",
        "",
        "## Next Action",
        "",
        f"- component: `{(payload.get('next_action') or {}).get('component')}`",
        f"- decision: **{(payload.get('next_action') or {}).get('decision')}**",
        f"- reason: {(payload.get('next_action') or {}).get('reason')}",
        "- behavior change authorized: **False**",
    ]
    return "\n".join(lines) + "\n"


def write_loss_decomposition(
    *,
    reports_root: Path,
    start: str,
    end: str,
    output_dir: Path,
) -> dict[str, str]:
    payload = build_loss_decomposition(reports_root=reports_root, start=start, end=end)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "full_chain_loss_decomposition.json"
    md_path = output_dir / "full_chain_loss_decomposition.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_loss_decomposition(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
