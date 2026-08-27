from __future__ import annotations

from typing import Any, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _pct(value: Any) -> str:
    try:
        return f"{float(value):+.4f}%p"
    except (TypeError, ValueError):
        return "-"


def render_stage2_authority_review(payload: Mapping[str, Any]) -> str:
    date_range = _mapping(payload.get("range"))
    integrity = _mapping(payload.get("integrity"))
    authorities = _mapping(payload.get("authorities"))
    lines = [
        f"# Strategist Stage-2 Authority Review ({date_range.get('start')} ~ {date_range.get('end')})",
        "",
        "Evaluation-only. No Strategist, Scanner, Monitor, Commander, or execution behavior changed.",
        "",
        "## Integrity",
        "",
        f"- Refresh records: **{integrity.get('refresh_record_count', 0)}**",
        f"- Forward comparable: **{integrity.get('forward_comparable_count', 0)}**",
        f"- Stage-2 attributable comparable: **{integrity.get('stage2_attributable_comparable_count', 0)}**",
        f"- Stage-2 response coverage: **{float(integrity.get('stage2_response_coverage') or 0) * 100:.1f}%**",
        "",
        "## Authority Decisions",
        "",
        "| Authority | Effect | N / Days | Avg / Median Delta | Max Day Share | Action |",
        "|---|---|---:|---:|---:|---|",
    ]
    labels = {
        "refresh_pipeline_all": "All refresh pipeline (diagnostic)",
        "rerank": "Rerank",
        "candidate_change": "Candidate change",
        "entry_tightening": "Entry tightening",
        "no_trade": "No-trade recommendation",
    }
    for key in ("refresh_pipeline_all", "rerank", "candidate_change", "entry_tightening", "no_trade"):
        row = _mapping(authorities.get(key))
        count = row.get("comparison_count", row.get("forward_observed_count", 0))
        action = "ADVISORY PATCH CANDIDATE" if row.get("advisory_candidate_eligible") else "RETAIN / EVIDENCE GAP"
        median_text = _pct(row.get("median_delta_pct"))
        max_day_share = row.get("max_single_day_share")
        share_text = f"{float(max_day_share) * 100:.1f}%" if max_day_share is not None else "-"
        lines.append(
            f"| {labels[key]} | `{row.get('state')}` | {count} / {row.get('day_count', 0)} | "
            f"{_pct(row.get('average_delta_pct'))} / {median_text} | {share_text} | {action} |"
        )
    lines.extend(["", "## Boundaries", ""])
    for key in ("refresh_pipeline_all", "rerank", "candidate_change", "entry_tightening", "no_trade"):
        row = _mapping(authorities.get(key))
        lines.append(f"- **{labels[key]}**: {row.get('reason')}")
        promotion = _mapping(row.get("promotion_eligibility"))
        if promotion:
            lines.append(f"  - Promotion eligibility: `{promotion.get('state')}` - {promotion.get('reason')}")
    lines.extend(
        [
            "",
            "A negative paired effect is a diagnostic signal, not sufficient authority for a runtime reduction. Promotion also requires evidence distributed across days, directional stability, and a consistent median.",
            "",
        ]
    )
    return "\n".join(lines)
