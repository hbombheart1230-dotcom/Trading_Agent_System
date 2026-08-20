from __future__ import annotations

from typing import Any, Mapping, Sequence

from .integrity import value_at


def _pct(value: Any) -> str:
    return "-" if value is None else f"{float(value):.4f}%"


def render_summary(
    rows: Sequence[Mapping[str, Any]],
    integrity: Mapping[str, Any],
    trees: Mapping[str, Any],
    candidates: Mapping[str, Any] | None = None,
) -> str:
    days = sorted({str(value_at(row, "identity.day") or "") for row in rows})
    lines = [
        "# Canonical Rank-1 Feature Mart",
        "",
        "## Status",
        "",
        "* Behavior effect: **NONE (offline research only)**",
        f"* Episodes: **{len(rows)}**",
        f"* Period: **{days[0] if days else '-'} ~ {days[-1] if days else '-'}**",
        f"* Integrity: **{integrity.get('status', 'UNKNOWN')}**",
        "* Cost basis: **0.28% round trip**",
        "",
        "## Horizon Coverage",
        "",
        "| Horizon | Observed | Total | Coverage |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, item in (integrity.get("horizon_coverage") or {}).items():
        lines.append(f"| {label} | {item.get('observed', 0)} | {item.get('total', 0)} | {float(item.get('coverage') or 0):.1%} |")
    lines.extend(["", "## Explainable Trees", "", "| Responsibility | Target | Root Split | Train Avg | Validation Avg |", "| --- | --- | --- | ---: | ---: |"])
    for key in ("scanner", "entry", "horizon"):
        tree = trees.get(key) or {}
        lines.append(
            f"| {key} | {tree.get('target', '-')} | {(tree.get('tree') or {}).get('split_feature', 'NO_STABLE_SPLIT')} | "
            f"{_pct((tree.get('train_metrics') or {}).get('avg_net_return_pct'))} | {_pct((tree.get('validation_metrics') or {}).get('avg_net_return_pct'))} |"
        )
    candidates = candidates or {}
    lines.extend(["", "## Prospective Shadow Candidates", ""])
    selected = candidates.get("prospective_shadow_candidates") or []
    if not selected:
        lines.append("No branch currently meets the frozen train/validation gate.")
    else:
        lines.extend(["| Responsibility | Feature | State | Target | Train | Validation |", "| --- | --- | --- | --- | ---: | ---: |"])
        for item in selected:
            lines.append(
                f"| {item.get('responsibility')} | `{item.get('feature')}` | {item.get('category')} | {item.get('target')} | "
                f"{_pct((item.get('train') or {}).get('avg_net_return_pct'))} | {_pct((item.get('validation') or {}).get('avg_net_return_pct'))} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "This mart separates Scanner suitability, Monitor entry timing, and Strategist horizon evidence.",
            "A branch is research evidence only. It does not change ranking, entry, exit, or order behavior.",
            "Only branches whose direction agrees before and after 2026-08-01 may become prospective shadow candidates.",
            "",
        ]
    )
    return "\n".join(lines)


def render_integrity(integrity: Mapping[str, Any]) -> str:
    lines = [
        "# Rank-1 Feature Mart Integrity",
        "",
        f"* Status: **{integrity.get('status', 'UNKNOWN')}**",
        f"* Episodes: **{integrity.get('episode_count', 0)}**",
        f"* Duplicate IDs: **{len(integrity.get('duplicate_episode_ids') or [])}**",
        f"* Point-in-time violations: **{len(integrity.get('point_in_time_violations') or [])}**",
        f"* Market snapshot time violations: **{len(integrity.get('market_snapshot_time_violations') or [])}**",
        f"* Prospective market snapshot coverage: **{float((integrity.get('market_snapshot_coverage') or {}).get('coverage') or 0.0):.1%}**",
        f"* Symbol violations: **{len(integrity.get('symbol_format_violations') or [])}**",
        "",
        "## Feature Coverage",
        "",
        "| Field | Present / Total | Eligible Present / Total | Eligible Coverage |",
        "| --- | ---: | ---: | ---: |",
    ]
    for path, item in (integrity.get("feature_coverage") or {}).items():
        lines.append(
            f"| `{path}` | {item.get('present', 0)} / {item.get('total', 0)} | "
            f"{item.get('eligible_present', 0)} / {item.get('eligible_total', 0)} | {float(item.get('eligible_coverage') or 0):.1%} |"
        )
    return "\n".join(lines) + "\n"
