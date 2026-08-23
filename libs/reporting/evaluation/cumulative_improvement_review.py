from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.q8_historical_review import build_q8_historical_review_payload
from libs.reporting.quant_shadow_candidate_evaluation import (
    iter_quant_shadow_candidate_payloads_for_range,
)
from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes
from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .cost_basis_comparison import build_evaluation_cost_bases
from .episode_scanner_review import (
    build_episode_scanner_review,
    build_same_symbol_reentry_review,
)
from .post_reclaim_shadow_review import build_post_reclaim_shadow_review
from .scanner_quality import extract_pre_strategist_candidate_rows
from .scanner_alignment_root_cause import (
    build_scanner_alignment_root_cause_range,
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _strategist_weighting_review(
    reports_root: Path,
    *,
    start: str,
    end: str,
) -> dict[str, Any]:
    daily_deltas: dict[str, list[float]] = {
        "+5m": [],
        "+15m": [],
        "+30m": [],
        "EOD": [],
    }
    source_root = reports_root / "evaluation" / "baseline_samsung_hynix"
    if source_root.exists():
        for day_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
            if not start <= day_dir.name <= end:
                continue
            payload = _read_json(day_dir / "q9_vs_samsung_hynix_daily_comparison.json")
            for horizon in payload.get("horizons") or []:
                if not isinstance(horizon, Mapping):
                    continue
                name = str(horizon.get("horizon") or "")
                if name not in daily_deltas:
                    continue
                performers = {
                    str(row.get("performer") or ""): row
                    for row in horizon.get("performers") or []
                    if isinstance(row, Mapping)
                }
                scanner = performers.get("A_SCANNER_CONTROL")
                strategist = performers.get("B_STRATEGIST_RANKED")
                if not scanner or not strategist:
                    continue
                if not int(scanner.get("trade_count") or 0) or not int(
                    strategist.get("trade_count") or 0
                ):
                    continue
                daily_deltas[name].append(
                    float(strategist.get("avg_return_pct") or 0.0)
                    - float(scanner.get("avg_return_pct") or 0.0)
                )
    rows = []
    for horizon, values in daily_deltas.items():
        rows.append(
            {
                "horizon": horizon,
                "observed_day_count": len(values),
                "strategist_better_day_count": sum(value > 0 for value in values),
                "strategist_worse_day_count": sum(value < 0 for value in values),
                "avg_strategist_minus_scanner_pct": (
                    round(sum(values) / len(values), 4) if values else None
                ),
            }
        )
    return {
        "schema_version": "strategist_weighting_cumulative_review.v1",
        "behavior_effect": "evaluation_only",
        "rows": rows,
        "interpretation": (
            "Paired daily B minus A deltas measure strategy-weighted ranking versus "
            "the same Scanner candidate universe. They do not measure candidate sourcing."
        ),
    }


def _rank_row(
    review: Mapping[str, Any],
    *,
    bucket: str,
    horizon: str,
) -> Mapping[str, Any]:
    return next(
        (
            row
            for row in review.get("rank_horizon_rows") or []
            if isinstance(row, Mapping)
            and row.get("rank_bucket") == bucket
            and row.get("horizon") == horizon
        ),
        {},
    )


def _candidate_rows(
    *,
    episode_review: Mapping[str, Any],
    reentry_review: Mapping[str, Any],
    post_reclaim_review: Mapping[str, Any],
    strategist_review: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rank1 = _rank_row(episode_review, bucket="rank1", horizon="+30m")
    rank23 = _rank_row(episode_review, bucket="rank2_3", horizon="+30m")
    rank1_live = float(
        (rank1.get("live_net") or {}).get("expectancy_pct") or 0.0
    )
    rank23_live = float(
        (rank23.get("live_net") or {}).get("expectancy_pct") or 0.0
    )
    strategist_30 = next(
        (
            row
            for row in strategist_review.get("rows") or []
            if isinstance(row, Mapping) and row.get("horizon") == "+30m"
        ),
        {},
    )
    return [
        {
            "priority": 1,
            "candidate": "same_symbol_loss_reentry_control",
            "class": "damage_reduction",
            "status": (
                "APPLIED_2026_07_29"
                if reentry_review.get("behavior_candidate_eligible")
                else "INSUFFICIENT_EVIDENCE"
            ),
            "evidence": {
                "repeat_count": (reentry_review.get("repeat_entry") or {}).get("count"),
                "repeat_expectancy_pct": (
                    reentry_review.get("repeat_entry") or {}
                ).get("expectancy_pct"),
                "repeat_minus_first_expectancy_pct": reentry_review.get(
                    "repeat_minus_first_expectancy_pct"
                ),
                "repeat_after_loss": reentry_review.get("repeat_after_loss"),
                "repeat_after_non_loss": reentry_review.get(
                    "repeat_after_non_loss"
                ),
            },
        },
        {
            "priority": 2,
            "candidate": "confirmed_post_reclaim_pullback_subtype",
            "class": "alpha_research",
            "status": post_reclaim_review.get("promotion_status"),
            "evidence": {
                "observed_count": post_reclaim_review.get("observed_count"),
                "observed_day_count": post_reclaim_review.get("observed_day_count"),
                "horizon_rows": post_reclaim_review.get("rows"),
            },
        },
        {
            "priority": 3,
            "candidate": "scanner_rank_ordering_component_review",
            "class": "ranking_diagnosis",
            "status": (
                "DIAGNOSTIC_CANDIDATE"
                if rank1_live <= 0 and rank23_live <= 0
                and (episode_review.get("score_component_review") or {}).get(
                    "status"
                )
                == "READY"
                else "OBSERVABILITY_NOT_READY"
                if (episode_review.get("score_component_review") or {}).get(
                    "status"
                )
                != "READY"
                else "RETAIN_UNDER_OBSERVATION"
            ),
            "evidence": {
                "rank1_live_net_30m_pct": rank1_live,
                "rank2_3_live_net_30m_pct": rank23_live,
                "rank1_minus_rank2_3_gross_30m_pct": episode_review.get(
                    "rank1_minus_rank2_3_gross_30m_pct"
                ),
                "score_component_review": episode_review.get(
                    "score_component_review"
                ),
            },
        },
        {
            "priority": 4,
            "candidate": "strategist_ranking_weight_guard",
            "class": "strategist_effectiveness",
            "status": (
                "DIAGNOSTIC_CANDIDATE"
                if float(
                    strategist_30.get("avg_strategist_minus_scanner_pct") or 0.0
                )
                < 0
                else "RETAIN_UNDER_OBSERVATION"
            ),
            "evidence": dict(strategist_30),
        },
    ]


def build_cumulative_improvement_review(
    *,
    reports_root: Path,
    start: str,
    end: str,
    payloads: list[dict[str, Any]] | None = None,
    historical_review: Mapping[str, Any] | None = None,
    q14_range: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    cost_bases = build_evaluation_cost_bases(load_broker_cost_profile(None))
    mock_drag = float(
        (cost_bases.get("mock_observed") or {}).get(
            "total_drag_with_slippage_pct"
        )
        or 0.0
    )
    live_drag = float(
        (cost_bases.get("live_deployment_equity") or {}).get(
            "total_drag_with_slippage_pct"
        )
        or 0.0
    )
    prepared_scanner_rows: list[dict[str, Any]] | None = None
    if payloads is not None:
        source_payloads = payloads
    else:
        source_payloads = []
        deduped_rows: dict[tuple[str, str, int], dict[str, Any]] = {}
        for payload in iter_quant_shadow_candidate_payloads_for_range(
            reports_root=reports_root,
            start=start,
            end=end,
        ):
            for row in extract_pre_strategist_candidate_rows([payload]):
                key = (
                    str(row.get("q9_decision_id") or ""),
                    str(row.get("symbol") or ""),
                    int(float(row.get("rank") or 0)),
                )
                deduped_rows[key] = row
        prepared_scanner_rows = attach_forward_outcomes(list(deduped_rows.values()))
    q8 = (
        dict(historical_review)
        if historical_review is not None
        else build_q8_historical_review_payload(
            reports_root=reports_root,
            start=start,
            end=end,
        )
    )
    q14 = (
        dict(q14_range)
        if q14_range is not None
        else build_scanner_alignment_root_cause_range(
            reports_root=reports_root,
            start=start,
            end=end,
        )
    )
    episode_review = build_episode_scanner_review(
        source_payloads,
        mock_drag_pct=mock_drag,
        live_drag_pct=live_drag,
        prepared_rows=prepared_scanner_rows,
    )
    reentry_review = build_same_symbol_reentry_review(q14.get("rows") or [])
    post_reclaim_review = build_post_reclaim_shadow_review(
        q8,
        mock_drag_pct=mock_drag,
        live_drag_pct=live_drag,
    )
    strategist_review = _strategist_weighting_review(
        reports_root,
        start=start,
        end=end,
    )
    candidates = _candidate_rows(
        episode_review=episode_review,
        reentry_review=reentry_review,
        post_reclaim_review=post_reclaim_review,
        strategist_review=strategist_review,
    )
    outcome_conditioned_count = sum(
        int(row.get("trade_count") or 0)
        for row in q14.get("cause_summary") or []
        if isinstance(row, Mapping)
        and row.get("diagnostic_kind") == "outcome_conditioned"
    )
    return {
        "schema_version": "cumulative_improvement_review.v1",
        "behavior_effect": "evaluation_only",
        "range": {"start": start, "end": end},
        "active_validation": "same_symbol_loss_reentry_control",
        "behavior_patch_authorized": bool(
            reentry_review.get("behavior_candidate_eligible")
        ),
        "cost_bases": cost_bases,
        "q14_causal_interpretation": {
            "largest_legacy_behavior_root_cause": q14.get(
                "largest_behavior_root_cause"
            ),
            "largest_structural_root_cause": q14.get(
                "largest_structural_root_cause"
            ),
            "outcome_conditioned_trade_count": outcome_conditioned_count,
            "rule": (
                "Outcome-conditioned Q14 labels cannot independently authorize "
                "a Scanner behavior patch."
            ),
        },
        "episode_scanner_review": episode_review,
        "same_symbol_reentry_review": reentry_review,
        "post_reclaim_shadow_review": post_reclaim_review,
        "strategist_weighting_review": strategist_review,
        "improvement_candidates": candidates,
        "next_decision": (
            "Run one full-day contract smoke test for the Q17 repair and the "
            "same-symbol loss reentry control. Do not add another behavior patch."
        ),
    }


def render_cumulative_improvement_review(payload: Mapping[str, Any]) -> str:
    date_range = payload.get("range") or {}
    q14 = payload.get("q14_causal_interpretation") or {}
    episode = payload.get("episode_scanner_review") or {}
    reentry = payload.get("same_symbol_reentry_review") or {}
    reclaim = payload.get("post_reclaim_shadow_review") or {}
    lines = [
        f"# Cumulative Improvement Review - {date_range.get('start')} to {date_range.get('end')}",
        "",
        f"- Behavior effect: `{payload.get('behavior_effect')}`",
        f"- Active validation: `{payload.get('active_validation')}`",
        f"- Behavior patch authorized: `{payload.get('behavior_patch_authorized')}`",
        f"- Scanner rows/episodes: {episode.get('raw_candidate_row_count', 0)} / {episode.get('episode_count', 0)}",
        f"- Score component coverage: {float((episode.get('score_component_review') or {}).get('coverage') or 0):.1%}",
        "",
        "## Q14 Causal Interpretation",
        "",
        f"- Legacy outcome-conditioned result: `{(q14.get('largest_legacy_behavior_root_cause') or {}).get('root_cause') or 'NONE'}`",
        f"- Largest structural result: `{(q14.get('largest_structural_root_cause') or {}).get('root_cause') or 'NONE'}`",
        f"- Outcome-conditioned trades: {q14.get('outcome_conditioned_trade_count', 0)}",
        f"- Rule: {q14.get('rule') or 'N/A'}",
        "",
        "## Episode-Level Scanner Ranking",
        "",
        "| Rank | Horizon | Episodes | Observed | Days | Gross | Live Net | Mock Net |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in episode.get("rank_horizon_rows") or []:
        if not isinstance(row, Mapping) or row.get("rank_bucket") == "unknown":
            continue
        lines.append(
            f"| {row.get('rank_bucket')} | {row.get('horizon')} | "
            f"{row.get('episode_count')} | {row.get('observed_count')} | "
            f"{row.get('observed_day_count')} | "
            f"{float((row.get('gross') or {}).get('expectancy_pct') or 0):.4f}% | "
            f"{float((row.get('live_net') or {}).get('expectancy_pct') or 0):.4f}% | "
            f"{float((row.get('mock_net') or {}).get('expectancy_pct') or 0):.4f}% |"
        )
    lines += [
        "",
        "## Same-Symbol Reentry",
        "",
        "| Cohort | Count | Win Rate | Expectancy | Profit Factor |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, key in (
        ("First", "first_entry"),
        ("Repeat", "repeat_entry"),
        ("Repeat after loss", "repeat_after_loss"),
        ("Repeat after non-loss", "repeat_after_non_loss"),
    ):
        row = reentry.get(key) or {}
        lines.append(
            f"| {label} | {row.get('count', 0)} | "
            f"{float(row.get('win_rate') or 0):.1%} | "
            f"{float(row.get('expectancy_pct') or 0):.4f}% | "
            f"{float(row.get('profit_factor') or 0):.4f} |"
        )
    lines += [
        "",
        "## Confirmed Post-Reclaim Shadow",
        "",
        f"- Status: `{reclaim.get('promotion_status')}`",
        f"- Observed: {reclaim.get('observed_count', 0)} across {reclaim.get('observed_day_count', 0)} days",
        "",
        "| Horizon | Gross | Live Net | Mock Net |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in reclaim.get("rows") or []:
        lines.append(
            f"| {row.get('horizon')} | "
            f"{float(row.get('gross_expectancy_pct') or 0):.4f}% | "
            f"{float(row.get('live_net_expectancy_pct') or 0):.4f}% | "
            f"{float(row.get('mock_net_expectancy_pct') or 0):.4f}% |"
        )
    lines += [
        "",
        "## Improvement Candidates",
        "",
        "| Priority | Candidate | Class | Status |",
        "| ---: | --- | --- | --- |",
    ]
    for row in payload.get("improvement_candidates") or []:
        lines.append(
            f"| {row.get('priority')} | {row.get('candidate')} | "
            f"{row.get('class')} | {row.get('status')} |"
        )
    lines += [
        "",
        "## Decision Boundary",
        "",
        f"- {payload.get('next_decision')}",
        "",
    ]
    return "\n".join(lines)


def write_cumulative_improvement_review(
    *,
    reports_root: Path,
    start: str,
    end: str,
) -> dict[str, str]:
    payload = build_cumulative_improvement_review(
        reports_root=reports_root,
        start=start,
        end=end,
    )
    output_dir = (
        Path(reports_root) / "evaluation" / "range" / f"{start}_{end}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "cumulative_improvement_review.json"
    markdown_path = output_dir / "cumulative_improvement_review.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_cumulative_improvement_review(payload),
        encoding="utf-8",
    )
    return {"json": str(json_path), "markdown": str(markdown_path)}


__all__ = [
    "build_cumulative_improvement_review",
    "render_cumulative_improvement_review",
    "write_cumulative_improvement_review",
]
