from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    CONTRACT_VERSION,
    DIRECTIONAL_MIN_DAYS,
    DIRECTIONAL_MIN_OBSERVATIONS,
)
from .full_chain_component_review import build_full_chain_component_review


MIN_MATERIAL_DELTA_PCT = 0.30
MIN_POSITIVE_RATE = 0.55
MAX_DEGRADING_POSITIVE_RATE = 0.45


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _delta_state(
    metrics: Mapping[str, Any],
    *,
    prefix: str,
    missing_control: str,
) -> dict[str, Any]:
    count = int(metrics.get(f"{prefix}_comparison_count") or 0)
    days = int(metrics.get(f"{prefix}_day_count") or 0)
    delta = _number(metrics.get(f"average_{prefix}_delta_pct"))
    positive_rate = _number(metrics.get(f"{prefix}_positive_delta_rate"))
    enough = count >= DIRECTIONAL_MIN_OBSERVATIONS and days >= DIRECTIONAL_MIN_DAYS
    if not enough or delta is None or positive_rate is None:
        state = "NOT_MEASURABLE"
        reason = (
            f"requires {DIRECTIONAL_MIN_OBSERVATIONS} paired observations across "
            f"{DIRECTIONAL_MIN_DAYS} days; current={count}/{days}"
        )
    elif delta >= MIN_MATERIAL_DELTA_PCT and positive_rate >= MIN_POSITIVE_RATE:
        state = "VALUE_ADD"
        reason = "paired cost-adjusted effect meets the fixed positive materiality contract"
    elif delta <= -MIN_MATERIAL_DELTA_PCT and positive_rate <= MAX_DEGRADING_POSITIVE_RATE:
        state = "DEGRADING"
        reason = "paired cost-adjusted effect meets the fixed negative materiality contract"
    else:
        state = "NEUTRAL"
        reason = "paired effect is measurable but does not meet positive or negative materiality"
    return {
        "state": state,
        "reason": reason,
        "comparison_count": count,
        "day_count": days,
        "average_delta_pct": delta,
        "positive_delta_rate": positive_rate,
        "missing_control": missing_control if state == "NOT_MEASURABLE" else None,
    }


def _decision_state(component: Mapping[str, Any]) -> str:
    decision = str(component.get("decision") or "")
    if decision == "INSUFFICIENT_EVIDENCE":
        return "NOT_MEASURABLE"
    if decision in {"REJECT", "DEPRECATE_CANDIDATE"}:
        return "DEGRADING"
    if decision == "ADJUST_AND_RETEST":
        return "DEGRADING"
    if decision == "PROMOTION_CANDIDATE":
        return "VALUE_ADD"
    return "NEUTRAL"


def build_agent_effectiveness_scorecard(
    full_chain_review: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = _mapping(full_chain_review.get("evidence"))
    attribution = _mapping(evidence.get("decision_window_attribution"))
    primary = next(
        (
            dict(row)
            for row in attribution.get("by_horizon") or []
            if isinstance(row, Mapping) and row.get("horizon") == "+30m"
        ),
        {},
    )
    components = _mapping(full_chain_review.get("component_decisions"))
    scanner = _mapping(components.get("scanner"))
    scanner_measurable = str(scanner.get("decision") or "") != "INSUFFICIENT_EVIDENCE"
    scanner_relative = (
        "VALUE_ADD"
        if scanner_measurable and bool(scanner.get("relative_ranking_effect_positive"))
        else "DEGRADING"
        if scanner_measurable
        else "NOT_MEASURABLE"
    )
    scanner_absolute = (
        "VALUE_ADD"
        if scanner_measurable and bool(scanner.get("absolute_cost_adjusted_edge_positive"))
        else "DEGRADING"
        if scanner_measurable
        else "NOT_MEASURABLE"
    )
    overlay_metrics = {
        "strategy_ranking_overlay_comparison_count": primary.get(
            "strategy_ranking_overlay_comparison_count",
            primary.get("strategist_comparison_count"),
        ),
        "strategy_ranking_overlay_day_count": primary.get(
            "strategy_ranking_overlay_day_count",
            primary.get("strategist_day_count"),
        ),
        "average_strategy_ranking_overlay_delta_pct": primary.get(
            "average_strategy_ranking_overlay_delta_pct",
            primary.get("average_strategist_delta_pct"),
        ),
        "strategy_ranking_overlay_positive_delta_rate": primary.get(
            "strategy_ranking_overlay_positive_delta_rate",
            primary.get("strategist_positive_delta_rate"),
        ),
    }
    overlay = _delta_state(
        overlay_metrics,
        prefix="strategy_ranking_overlay",
        missing_control="paired same-universe intrinsic and strategy-weighted outcomes",
    )
    refresh = _delta_state(
        primary,
        prefix="post_scanner_refresh",
        missing_control="paired first-Scanner and post-refresh Scanner outcomes",
    )
    commander = _delta_state(
        primary,
        prefix="commander",
        missing_control="paired presented-candidate and Commander approve/veto outcomes",
    )
    trade_total = int(evidence.get("total_trade_model_count") or 0)
    excluded = int(evidence.get("excluded_trade_model_count") or 0)
    return {
        "schema_version": "agent_effectiveness_scorecard.v1",
        "contract_version": CONTRACT_VERSION,
        "behavior_effect": "evaluation_only",
        "range": dict(_mapping(full_chain_review.get("range"))),
        "runtime_order": [
            "commander_operating_context",
            "strategist_initial_frame",
            "strategy_guided_scanner",
            "optional_post_scanner_strategist_refresh",
            "optional_scanner_rerun",
            "monitor_entry",
            "commander_decision",
            "execution",
            "monitor_exit_horizon",
        ],
        "state_contract": [
            "NOT_MEASURABLE",
            "DEFECT",
            "DEGRADING",
            "NEUTRAL",
            "VALUE_ADD",
        ],
        "integrity": {
            "state": "PASS_WITH_EXCLUSIONS" if excluded else "PASS",
            "trade_model_count": trade_total,
            "excluded_trade_model_count": excluded,
        },
        "components": {
            "scanner": {
                "relative_ranking_state": scanner_relative,
                "absolute_edge_state": scanner_absolute,
                "question": "Given the Strategist frame, did Scanner rank cost-positive candidates well?",
                "source": "q9_full_chain_component_review.component_decisions.scanner",
            },
            "strategist": {
                "full_contribution": {
                    "state": "NOT_MEASURABLE",
                    "reason": "Strategist runs before Scanner and influences candidate sourcing.",
                    "missing_control": "parallel strategy-neutral candidate sourcing and ranking shadow",
                },
                "scenario_quality": {
                    "state": "NOT_MEASURABLE",
                    "reason": "scenario forecasts are not yet joined to a fixed subsequent-market target in this scorecard",
                    "missing_control": "scenario/horizon forecast outcome join",
                },
                "ranking_overlay": overlay,
                "post_scanner_refresh": refresh,
            },
            "commander": commander,
            "monitor_entry": {
                "state": _decision_state(_mapping(components.get("monitor_entry"))),
                "source_decision": _mapping(components.get("monitor_entry")).get("decision"),
                "reason": _mapping(components.get("monitor_entry")).get("finding"),
            },
            "monitor_exit_horizon": {
                "state": _decision_state(_mapping(components.get("monitor_exit"))),
                "source_decision": _mapping(components.get("monitor_exit")).get("decision"),
                "reason": _mapping(components.get("monitor_exit")).get("finding"),
            },
            "full_system": {
                "state": _decision_state(_mapping(components.get("full_system"))),
                "source_decision": _mapping(components.get("full_system")).get("decision"),
                "reason": _mapping(components.get("full_system")).get("finding"),
            },
        },
        "controls": {
            "A_SCANNER_CONTROL": {
                "semantic_role": "SCANNER_INTRINSIC_SAME_UNIVERSE",
                "full_pre_strategist_control": False,
            },
            "B_STRATEGIST_RANKED": {
                "semantic_role": "STRATEGY_WEIGHTED_SCANNER_RANKING",
            },
            "R1_PRE_REFRESH_SCANNER": {
                "semantic_role": "SCANNER_BEFORE_POST_SCANNER_STRATEGIST_REFRESH",
            },
            "R2_POST_REFRESH_SCANNER": {
                "semantic_role": "SCANNER_AFTER_POST_SCANNER_STRATEGIST_REFRESH",
            },
        },
        "behavior_change_authorized": False,
    }


def render_agent_effectiveness_scorecard(payload: Mapping[str, Any]) -> str:
    date_range = _mapping(payload.get("range"))
    components = _mapping(payload.get("components"))
    strategist = _mapping(components.get("strategist"))
    lines = [
        f"# Agent Effectiveness Scorecard ({date_range.get('start')} ~ {date_range.get('end')})",
        "",
        "Evaluation-only. This report does not change trading behavior.",
        "",
        "## Component States",
        "",
        "| Component | State | Meaning |",
        "|---|---|---|",
        f"| Scanner relative ranking | `{_mapping(components.get('scanner')).get('relative_ranking_state')}` | Strategy-conditioned rank precision |",
        f"| Scanner absolute edge | `{_mapping(components.get('scanner')).get('absolute_edge_state')}` | Cost-adjusted candidate edge |",
        f"| Strategist full contribution | `{_mapping(strategist.get('full_contribution')).get('state')}` | Requires strategy-neutral source control |",
        f"| Strategist ranking overlay | `{_mapping(strategist.get('ranking_overlay')).get('state')}` | Same-universe intrinsic vs strategy-weighted |",
        f"| Strategist post-Scanner refresh | `{_mapping(strategist.get('post_scanner_refresh')).get('state')}` | First Scanner vs refreshed Scanner |",
        f"| Commander | `{_mapping(components.get('commander')).get('state')}` | Presented candidate vs approve/veto |",
        f"| Monitor Entry | `{_mapping(components.get('monitor_entry')).get('state')}` | Selected baseline vs entry/block |",
        f"| Monitor Exit/Horizon | `{_mapping(components.get('monitor_exit_horizon')).get('state')}` | Actual exit vs strategy-valid alternatives |",
        f"| Full system | `{_mapping(components.get('full_system')).get('state')}` | Broker-net result |",
        "",
        "## Strategist Control Boundary",
        "",
        "- `A_SCANNER_CONTROL` is a same-candidate-universe intrinsic ranking control.",
        "- It is not a fully raw pre-Strategist Scanner because Strategist runs first.",
        "- Full Strategist value remains `NOT_MEASURABLE` until a strategy-neutral candidate-source shadow exists.",
        "- Ranking overlay and post-Scanner refresh are evaluated separately.",
        "",
        "## Evidence Shortfalls",
        "",
    ]
    for name, row in (
        ("Strategist full", _mapping(strategist.get("full_contribution"))),
        ("Strategist scenario", _mapping(strategist.get("scenario_quality"))),
        ("Strategist overlay", _mapping(strategist.get("ranking_overlay"))),
        ("Strategist refresh", _mapping(strategist.get("post_scanner_refresh"))),
        ("Commander", _mapping(components.get("commander"))),
    ):
        if row.get("state") == "NOT_MEASURABLE":
            lines.append(f"- {name}: {row.get('missing_control') or row.get('reason')}")
    return "\n".join(lines) + "\n"


def write_agent_effectiveness_scorecard(
    *,
    reports_root: Path,
    start: str,
    end: str,
    output_dir: Path,
) -> dict[str, Any]:
    review = build_full_chain_component_review(
        reports_root=Path(reports_root),
        start=start,
        end=end,
    )
    payload = build_agent_effectiveness_scorecard(review)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "agent_effectiveness_scorecard.json"
    md_path = output_dir / "agent_effectiveness_scorecard.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_agent_effectiveness_scorecard(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "range": payload.get("range"),
    }
