from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from libs.reporting.q8_evaluation_contract import (
    DUPLICATE_RATE_MAX,
    PROMOTION_CANDIDATE_MIN_DAYS,
    PROMOTION_CANDIDATE_MIN_OBSERVED,
    TRUSTED_FORWARD_MIN_COUNT,
    TRUSTED_FORWARD_MIN_COVERAGE,
)
from libs.reporting.quant_shadow_candidate_evaluation import (
    build_quant_shadow_candidate_evaluation,
    load_quant_shadow_candidate_payloads,
)


def _iter_days(start: str, end: str) -> Iterable[str]:
    current = date.fromisoformat(str(start)[:10])
    final = date.fromisoformat(str(end)[:10])
    while current <= final:
        yield current.isoformat()
        current += timedelta(days=1)


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):.2%}"
    except Exception:
        return "-"


def _fmt_num(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "0"


def _watchlist_rows(scorecard: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [dict(row) for row in list(scorecard.get("promotion_watchlist") or []) if isinstance(row, Mapping)]


def build_q8_trusted_reaggregation(*, reports_root: Path, start: str, end: str) -> Dict[str, Any]:
    daily: List[Dict[str, Any]] = []
    all_payloads: List[Dict[str, Any]] = []
    promotion_allowed_day_count = 0
    for day in _iter_days(start, end):
        payloads = load_quant_shadow_candidate_payloads(reports_root=reports_root, days=[day])
        if not payloads:
            continue
        all_payloads.extend(payloads)
        evaluation = build_quant_shadow_candidate_evaluation(payloads)
        scorecard = (
            evaluation.get("no_trade_scorecard")
            if isinstance(evaluation.get("no_trade_scorecard"), Mapping)
            else {}
        )
        trust_gate = (
            evaluation.get("evaluation_trust_gate")
            if isinstance(evaluation.get("evaluation_trust_gate"), Mapping)
            else {}
        )
        row = {
            "day": day,
            "payload_count": int(evaluation.get("payload_count") or 0),
            "candidate_count": int(evaluation.get("candidate_count") or 0),
            "deduped_candidate_count": int(evaluation.get("deduped_candidate_count") or 0),
            "duplicate_candidate_count": int(evaluation.get("duplicate_candidate_count") or 0),
            "duplicate_rate": float(trust_gate.get("duplicate_rate") or 0.0),
            "trusted_forward_count": int(evaluation.get("forward_outcome_available_count") or 0),
            "trusted_forward_coverage": float(evaluation.get("forward_outcome_coverage") or 0.0),
            "scorecard_status": scorecard.get("status") or "not_available",
            "trust_gate_status": trust_gate.get("status") or "not_available",
            "promotion_allowed": bool(trust_gate.get("promotion_allowed")),
            "trust_reasons": list(trust_gate.get("block_reasons") or trust_gate.get("reasons") or []),
            "promotion_watchlist": _watchlist_rows(scorecard),
        }
        daily.append(row)
        if row["promotion_allowed"]:
            promotion_allowed_day_count += 1

    cumulative_evaluation = build_quant_shadow_candidate_evaluation(all_payloads) if all_payloads else {}
    cumulative_scorecard = (
        cumulative_evaluation.get("no_trade_scorecard")
        if isinstance(cumulative_evaluation.get("no_trade_scorecard"), Mapping)
        else {}
    )
    cumulative_trust_gate = (
        cumulative_evaluation.get("evaluation_trust_gate")
        if isinstance(cumulative_evaluation.get("evaluation_trust_gate"), Mapping)
        else {}
    )
    aggregate = {
        "candidate_count": int(cumulative_evaluation.get("candidate_count") or 0),
        "deduped_candidate_count": int(cumulative_evaluation.get("deduped_candidate_count") or 0),
        "duplicate_candidate_count": int(cumulative_evaluation.get("duplicate_candidate_count") or 0),
        "duplicate_rate": float(cumulative_trust_gate.get("duplicate_rate") or 0.0),
        "forward_outcome_available_count": int(cumulative_evaluation.get("forward_outcome_available_count") or 0),
        "trusted_forward_coverage": float(cumulative_evaluation.get("forward_outcome_coverage") or 0.0),
        "promotion_allowed_day_count": promotion_allowed_day_count,
        "cumulative_trust_gate_status": cumulative_trust_gate.get("status") or "not_available",
        "cumulative_promotion_allowed": bool(cumulative_trust_gate.get("promotion_allowed")),
        "cumulative_trust_reasons": list(
            cumulative_trust_gate.get("block_reasons") or cumulative_trust_gate.get("reasons") or []
        ),
        "promotion_watchlist": _watchlist_rows(cumulative_scorecard),
    }
    return {
        "schema_version": "q8_trusted_reaggregation.v2",
        "behavior_effect": "evaluation_only",
        "generated_with": "same_day_max_delay_forward_outcomes_deduped_candidates_and_trust_gate",
        "range": {"start": str(start)[:10], "end": str(end)[:10], "days_with_payloads": len(daily)},
        "aggregate": aggregate,
        "daily": daily,
        "important_note": (
            "Promotion decisions must use trusted same-day forward outcomes, deduped candidates, "
            "and promotion_allowed=true trust-gate rows only."
        ),
    }


def render_q8_trusted_reaggregation_markdown(payload: Mapping[str, Any]) -> str:
    date_range = payload.get("range") if isinstance(payload.get("range"), Mapping) else {}
    aggregate = payload.get("aggregate") if isinstance(payload.get("aggregate"), Mapping) else {}
    daily = list(payload.get("daily") or [])
    lines = [
        f"# Q8 Trusted Reaggregation ({date_range.get('start') or '-'} ~ {date_range.get('end') or '-'})",
        "",
        "This report is evaluation-only. It does not change trading behavior.",
        "",
        "## Summary",
        "",
        f"- raw candidates: **{_fmt_num(aggregate.get('candidate_count'))}**",
        f"- deduped candidates: **{_fmt_num(aggregate.get('deduped_candidate_count'))}**",
        f"- duplicate count/rate: **{_fmt_num(aggregate.get('duplicate_candidate_count'))} / {_fmt_pct(aggregate.get('duplicate_rate'))}**",
        f"- trusted forward: **{_fmt_num(aggregate.get('forward_outcome_available_count'))} / {_fmt_pct(aggregate.get('trusted_forward_coverage'))}**",
        f"- promotion allowed days: **{_fmt_num(aggregate.get('promotion_allowed_day_count'))}**",
        f"- cumulative trust gate: **`{aggregate.get('cumulative_trust_gate_status') or 'not_available'}`**",
        f"- cumulative promotion allowed: **`{bool(aggregate.get('cumulative_promotion_allowed'))}`**",
        f"- cumulative block reasons: **{', '.join(str(x) for x in list(aggregate.get('cumulative_trust_reasons') or [])) or '-'}**",
        "",
        "## Daily Trust Gate",
        "",
        "| Day | Raw | Deduped | Dup Rate | Trusted Forward | Trust Gate | Promotion | Reasons |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
    for row in daily:
        reasons = ", ".join(str(x) for x in list(row.get("trust_reasons") or [])) or "-"
        lines.append(
            "| {day} | {raw} | {deduped} | {dup_rate} | {forward} ({coverage}) | `{gate}` | `{allowed}` | {reasons} |".format(
                day=row.get("day") or "-",
                raw=_fmt_num(row.get("candidate_count")),
                deduped=_fmt_num(row.get("deduped_candidate_count")),
                dup_rate=_fmt_pct(row.get("duplicate_rate")),
                forward=_fmt_num(row.get("trusted_forward_count")),
                coverage=_fmt_pct(row.get("trusted_forward_coverage")),
                gate=row.get("trust_gate_status") or "-",
                allowed=bool(row.get("promotion_allowed")),
                reasons=reasons,
            )
        )
    lines += [
        "",
        "## Promotion Watchlist",
        "",
        "| Day | Candidate | Observed | Days | +5m | +15m | MAE5 | State |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    watch_count = 0
    for item in list(aggregate.get("promotion_watchlist") or []):
        if not isinstance(item, Mapping):
            continue
        watch_count += 1
        lines.append(
            "| {day} | `{name}` | {obs}/{count} | {days} | {ret5} | {ret15} | {mae5} | `{state}` |".format(
                day="cumulative",
                name=item.get("name") or "-",
                obs=_fmt_num(item.get("observed_count")),
                count=_fmt_num(item.get("candidate_count")),
                days=_fmt_num(item.get("observed_day_count")),
                ret5=f"{float(item.get('avg_return_5m_pct')):.4f}%" if item.get("avg_return_5m_pct") is not None else "-",
                ret15=f"{float(item.get('avg_return_15m_pct')):.4f}%" if item.get("avg_return_15m_pct") is not None else "-",
                mae5=f"{float(item.get('avg_mae_5m_pct')):.4f}%" if item.get("avg_mae_5m_pct") is not None else "-",
                state=item.get("review_state") or "-",
            )
        )
    for row in daily:
        for item in list(row.get("promotion_watchlist") or []):
            if not isinstance(item, Mapping):
                continue
            watch_count += 1
            lines.append(
                "| {day} | `{name}` | {obs}/{count} | {days} | {ret5} | {ret15} | {mae5} | `{state}` |".format(
                    day=row.get("day") or "-",
                    name=item.get("name") or "-",
                    obs=_fmt_num(item.get("observed_count")),
                    count=_fmt_num(item.get("candidate_count")),
                    days=_fmt_num(item.get("observed_day_count")),
                    ret5=f"{float(item.get('avg_return_5m_pct')):.4f}%" if item.get("avg_return_5m_pct") is not None else "-",
                    ret15=f"{float(item.get('avg_return_15m_pct')):.4f}%" if item.get("avg_return_15m_pct") is not None else "-",
                    mae5=f"{float(item.get('avg_mae_5m_pct')):.4f}%" if item.get("avg_mae_5m_pct") is not None else "-",
                    state=item.get("review_state") or "-",
                )
            )
    if watch_count <= 0:
        lines.append("| - | - | 0/0 | 0 | - | - | - | no_watchlist |")
    lines += [
        "",
        "## Decision Rule",
        "",
        "- PROMOTE is not allowed unless the daily trust gate has `promotion_allowed=true`.",
        f"- A day is promotion-review eligible only when trusted forward count >= {TRUSTED_FORWARD_MIN_COUNT}, "
        f"trusted coverage >= {TRUSTED_FORWARD_MIN_COVERAGE:.0%}, and duplicate rate <= {DUPLICATE_RATE_MAX:.0%}.",
        f"- Candidate-level promotion requires at least {PROMOTION_CANDIDATE_MIN_OBSERVED} trusted observations "
        f"across at least {PROMOTION_CANDIDATE_MIN_DAYS} observed days.",
        "- Cross-day or stale forward observations are excluded from trusted forward counts.",
        "- Duplicate candidates are removed before forward performance is averaged.",
    ]
    return "\n".join(lines)


def write_q8_trusted_reaggregation(
    *,
    reports_root: Path,
    start: str,
    end: str,
    output_dir: Path,
) -> Dict[str, Path]:
    payload = build_q8_trusted_reaggregation(reports_root=reports_root, start=start, end=end)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"q8_trusted_reaggregation_{str(start)[:10]}_to_{str(end)[:10]}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_q8_trusted_reaggregation_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
