from __future__ import annotations

from typing import Any, Mapping

from .loaders import mapping


def _pct(value: Any, *, rate: bool = False) -> str:
    if value is None:
        return "-"
    number = float(value) * 100.0 if rate else float(value)
    return f"{number:.1f}%" if rate else f"{number:+.2f}%"


def _number(value: Any) -> str:
    return "-" if value is None else f"{float(value):.2f}"


def _metric(value: Any) -> str:
    row = mapping(value)
    count = int(row.get("sample_count") or 0)
    if count <= 0:
        return "-"
    return (
        f"N={count}, WR {_pct(row.get('win_rate'), rate=True)}, "
        f"avg {_pct(row.get('avg_net_return_pct'))}, "
        f"PF {_number(row.get('profit_factor'))}"
    )


def _cell(value: Any) -> str:
    return str(value or "-").replace("|", "/").replace("\n", " ")


def _feature_summary(value: Any) -> str:
    features = mapping(value)
    parts = []
    for key, items in features.items():
        values = [str(item) for item in list(items or []) if str(item)]
        if values:
            parts.append(f"{key}={','.join(values)}")
    return "; ".join(parts) or "-"


def render_alpha_research_board(payload: Mapping[str, Any]) -> str:
    questions = [mapping(row) for row in payload.get("questions") or []]
    candidates = [mapping(row) for row in payload.get("candidates") or []]
    integrity = mapping(payload.get("integrity"))
    authority = mapping(payload.get("authority"))
    lines = [
        f"# Alpha Research Board - {payload.get('through_day')}",
        "",
        "This is the sole closeout research authority. Q8-Q18 and other "
        "evaluation artifacts are inputs only.",
        "",
        "## Fixed Contract",
        "",
        f"- Schema: `{payload.get('schema_version')}`",
        f"- Contract: `{payload.get('contract_version')}`",
        f"- Integrity: **{integrity.get('status')}**",
        f"- Closeout authority: `{authority.get('closeout_explanation_source')}`",
        "- Questions, candidate IDs, row columns, and feature columns are frozen.",
        "- Historical discovery and prospective evidence are never merged.",
        "- CLOSED candidates remain visible and cannot be restarted under a new name.",
        "",
        "## Top-Level Questions",
        "",
        "| Question | Definition | Active | CLOSED |",
        "|---|---|---:|---:|",
    ]
    for row in questions:
        lines.append(
            f"| **{_cell(row.get('question_id'))}** | {_cell(row.get('question'))} | "
            f"{len(row.get('active_candidate_ids') or [])} | "
            f"{len(row.get('closed_candidate_ids') or [])} |"
        )

    lines.extend(
        [
            "",
            "## Candidate Board",
            "",
            "| Q | Candidate ID | Status | Horizon | Historical | Prospective | Current net metric | Decision |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in candidates:
        lines.append(
            f"| {row.get('question_id')} | `{row.get('candidate_id')}` | "
            f"**{row.get('status')}** | `{_cell(row.get('target_horizon'))}` | "
            f"{_metric(row.get('historical_evidence'))} | "
            f"{_metric(row.get('prospective_evidence'))} | "
            f"{_metric(row.get('net_metrics'))} | "
            f"`{_cell(row.get('decision'))}` |"
        )

    lines.extend(["", "## Candidate Evidence", ""])
    for row in candidates:
        concentration = mapping(row.get("concentration"))
        concentration_text = ", ".join(
            f"{key}={value}" for key, value in concentration.items() if value is not None
        ) or "-"
        lines.extend(
            [
                f"### {row.get('question_id')} / {row.get('candidate_id')}",
                "",
                f"- Hypothesis: {_cell(row.get('hypothesis'))}",
                f"- Status: `{row.get('status')}`",
                f"- Features: {_feature_summary(row.get('feature_evidence'))}",
                f"- Sample quality: {_cell(row.get('sample_quality'))}",
                f"- Concentration: {_cell(concentration_text)}",
                f"- Rationale: {_cell(row.get('rationale'))}",
                f"- Next action: {_cell(row.get('next_action'))}",
                "",
            ]
        )

    lines.extend(["## Closeout Summary", ""])
    for value in payload.get("closeout_summary") or []:
        row = mapping(value)
        lines.append(f"- {_cell(row.get('statement'))}")

    missing = integrity.get("missing_or_invalid_sources") or []
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- Candidate registry matches: `{integrity.get('candidate_registry_matches')}`",
            f"- Historical/prospective separated: `{integrity.get('historical_prospective_separated')}`",
            f"- Missing or invalid inputs: `{', '.join(str(item) for item in missing) or 'none'}`",
            "- This Board is observation-only and cannot change trading behavior.",
            "",
        ]
    )
    return "\n".join(lines)
