from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.q8_evaluation_contract import candidate_day
from libs.reporting.quant_shadow_candidate_evaluation import (
    load_quant_shadow_candidate_payloads_for_range,
)
from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .loss_decomposition import _candidate_rows, _checkpoint_return
from .metrics import performance_metrics


HORIZONS = ("+5m", "+15m", "+30m", "+60m")
MIN_OBSERVATIONS = 20
MIN_DAYS = 3
MAX_DAY_SHARE = 0.60
MAX_SYMBOL_SHARE = 0.40
MIN_AVERAGE_NET_RETURN_PCT = 0.30
MIN_NET_PROFIT_FACTOR = 1.20


def _text(value: Any, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _lane_observation(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get("entry_lane_observation")
    return dict(value) if isinstance(value, Mapping) else {}


def _group_key(row: Mapping[str, Any], dimensions: tuple[str, ...]) -> tuple[str, ...]:
    lane = _lane_observation(row)
    values = {
        "time_bucket": _text(lane.get("time_bucket")),
        "tactic": _text(row.get("quant_tactic_id")),
        "primary_lane": _text(lane.get("primary_lane")),
        "market_regime_rail": _text(lane.get("market_regime_rail")),
        "selection_role": _text(row.get("shadow_role")),
    }
    return tuple(values[name] for name in dimensions)


def _profit_factor(values: list[float]) -> float:
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses <= 0:
        return 999.0 if gains > 0 else 0.0
    return round(gains / losses, 4)


def _combo_rows(
    candidates: list[dict[str, Any]],
    *,
    dimensions: tuple[str, ...],
    cost_pct: float,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        grouped[_group_key(row, dimensions)].append(row)

    output: list[dict[str, Any]] = []
    for key, members in grouped.items():
        for horizon in HORIZONS:
            observations: list[tuple[dict[str, Any], float]] = []
            for row in members:
                gross = _checkpoint_return(row, horizon)
                if gross is not None:
                    observations.append((row, gross))
            if not observations:
                continue
            gross_values = [value for _, value in observations]
            net_values = [value - cost_pct for value in gross_values]
            days = Counter(candidate_day(row) or "unknown" for row, _ in observations)
            symbols = Counter(_text(row.get("symbol")) for row, _ in observations)
            count = len(observations)
            max_day_share = max(days.values()) / count if days else 1.0
            max_symbol_share = max(symbols.values()) / count if symbols else 1.0
            avg_gross = sum(gross_values) / count
            avg_net = sum(net_values) / count
            profit_factor = _profit_factor(net_values)
            daily_net: dict[str, list[float]] = defaultdict(list)
            for (row, _), net_value in zip(observations, net_values):
                daily_net[candidate_day(row) or "unknown"].append(net_value)
            daily_net_returns = {
                day: round(sum(values) / len(values), 4)
                for day, values in sorted(daily_net.items())
            }
            leave_one_day_out = {}
            for excluded_day in daily_net:
                retained = [
                    value
                    for day, values in daily_net.items()
                    if day != excluded_day
                    for value in values
                ]
                leave_one_day_out[excluded_day] = (
                    round(sum(retained) / len(retained), 4)
                    if retained
                    else None
                )
            observed_lodo = [
                value for value in leave_one_day_out.values()
                if value is not None
            ]
            worst_lodo = min(observed_lodo) if observed_lodo else None
            robust_across_days = bool(observed_lodo) and all(
                value > 0 for value in observed_lodo
            )
            eligible = (
                count >= MIN_OBSERVATIONS
                and len(days) >= MIN_DAYS
                and max_day_share <= MAX_DAY_SHARE
                and max_symbol_share <= MAX_SYMBOL_SHARE
            )
            positive = (
                eligible
                and avg_net >= MIN_AVERAGE_NET_RETURN_PCT
                and profit_factor >= MIN_NET_PROFIT_FACTOR
                and robust_across_days
            )
            output.append({
                "dimensions": dict(zip(dimensions, key)),
                "horizon": horizon,
                "candidate_count": len(members),
                "observed_count": count,
                "observed_day_count": len(days),
                "observed_symbol_count": len(symbols),
                "coverage": round(count / len(members), 4) if members else 0.0,
                "average_gross_return_pct": round(avg_gross, 4),
                "round_trip_cost_pct": round(cost_pct, 4),
                "average_net_return_pct": round(avg_net, 4),
                "net_win_rate": round(sum(1 for value in net_values if value > 0) / count, 4),
                "net_profit_factor": profit_factor,
                "net_maximum_drawdown_pct": performance_metrics(net_values)["maximum_drawdown_pct"],
                "daily_net_returns_pct": daily_net_returns,
                "positive_day_count": sum(
                    1 for value in daily_net_returns.values() if value > 0
                ),
                "leave_one_day_out_net_returns_pct": leave_one_day_out,
                "worst_leave_one_day_out_net_return_pct": worst_lodo,
                "robust_across_days": robust_across_days,
                "maximum_day_share": round(max_day_share, 4),
                "maximum_symbol_share": round(max_symbol_share, 4),
                "top_days": [{"day": name, "count": value} for name, value in days.most_common(3)],
                "top_symbols": [{"symbol": name, "count": value} for name, value in symbols.most_common(5)],
                "evidence_eligible": eligible,
                "cost_positive": positive,
                "decision": (
                    "CONTROLLED_ADOPTION_CANDIDATE"
                    if positive
                    else "INSUFFICIENT_EVIDENCE"
                    if not eligible
                    else "RETAIN_UNDER_OBSERVATION"
                    if avg_net > 0
                    else "REJECT_COST_NEGATIVE"
                ),
            })
    return sorted(
        output,
        key=lambda row: (
            not bool(row["cost_positive"]),
            -float(row["average_net_return_pct"]),
            -int(row["observed_count"]),
        ),
    )


def build_horizon_alignment_review(
    *,
    reports_root: Path,
    start: str,
    end: str,
    cost_profile_path: Path | None = None,
) -> dict[str, Any]:
    payloads = load_quant_shadow_candidate_payloads_for_range(
        reports_root=reports_root,
        start=start,
        end=end,
    )
    candidates = _candidate_rows(payloads)
    profile = load_broker_cost_profile(cost_profile_path)
    cost_ratio = float(
        profile.get("conservative_round_trip_cost_pct")
        or profile.get("ema_round_trip_cost_pct")
        or 0.009
    )
    cost_pct = cost_ratio * 100.0
    time_tactic = _combo_rows(
        candidates,
        dimensions=("time_bucket", "tactic"),
        cost_pct=cost_pct,
    )
    time_lane = _combo_rows(
        candidates,
        dimensions=("time_bucket", "primary_lane"),
        cost_pct=cost_pct,
    )
    time_tactic_rail = _combo_rows(
        candidates,
        dimensions=("time_bucket", "tactic", "market_regime_rail"),
        cost_pct=cost_pct,
    )
    candidates_for_adoption = [
        row for row in time_tactic
        if row.get("cost_positive")
    ]
    observation_candidates = [
        row for row in time_tactic
        if row.get("decision") == "RETAIN_UNDER_OBSERVATION"
    ]
    decision = (
        "CONTROLLED_ADOPTION_CANDIDATE_FOUND"
        if candidates_for_adoption
        else "RETAIN_UNDER_OBSERVATION"
        if observation_candidates
        else "NO_COST_POSITIVE_COMBINATION"
    )
    return {
        "schema_version": "horizon_alignment_review.v2",
        "behavior_effect": "evaluation_only",
        "range": {"start": start[:10], "end": end[:10]},
        "cost_model": {
            "source": str(profile.get("source") or "fallback"),
            "sample_count": int(profile.get("sample_count") or 0),
            "ema_round_trip_cost_pct": float(profile.get("ema_round_trip_cost_pct") or 0.0) * 100.0,
            "conservative_round_trip_cost_pct": cost_pct,
            "profile_path": str(cost_profile_path or "data/state/broker_cost_profile.json"),
        },
        "eligibility_contract": {
            "minimum_observations": MIN_OBSERVATIONS,
            "minimum_days": MIN_DAYS,
            "maximum_day_share": MAX_DAY_SHARE,
            "maximum_symbol_share": MAX_SYMBOL_SHARE,
            "net_profit_factor_min": MIN_NET_PROFIT_FACTOR,
            "average_net_return_min_pct": MIN_AVERAGE_NET_RETURN_PCT,
            "leave_one_day_out_net_return_positive": True,
        },
        "candidate_count": len(candidates),
        "decision": decision,
        "controlled_adoption_candidates": candidates_for_adoption,
        "observation_candidates": observation_candidates,
        "time_tactic": time_tactic,
        "time_lane": time_lane,
        "time_tactic_market_rail": time_tactic_rail,
        "next_action": {
            "behavior_change_authorized": False,
            "decision": (
                "PREPARE_SHADOW_POLICY_SPEC"
                if candidates_for_adoption
                else "KEEP_FIXED_SHADOW_OBSERVATION"
                if observation_candidates
                else "REJECT_CURRENT_HYPOTHESIS_AND_RESEARCH_NEW_ALPHA"
            ),
            "reason": (
                "At least one time/tactic/horizon combination remains materially positive after "
                "observed costs, concentration checks, and leave-one-day-out validation."
                if candidates_for_adoption
                else "A combination is marginally positive after cost but fails the fixed robustness "
                "contract; it is not eligible for controlled adoption."
                if observation_candidates
                else "No time/tactic/horizon combination survives observed cost and robustness checks."
            ),
        },
    }


def render_horizon_alignment_review(payload: Mapping[str, Any]) -> str:
    date_range = payload.get("range") or {}
    cost = payload.get("cost_model") or {}
    lines = [
        f"# Horizon Alignment Review ({date_range.get('start')} ~ {date_range.get('end')})",
        "",
        "This report is evaluation-only. It does not change runtime behavior.",
        "",
        "## Cost Basis",
        "",
        f"- source: `{cost.get('source')}`",
        f"- samples: {cost.get('sample_count')}",
        f"- EMA round-trip cost: {float(cost.get('ema_round_trip_cost_pct') or 0):.4f}%",
        f"- conservative round-trip cost: {float(cost.get('conservative_round_trip_cost_pct') or 0):.4f}%",
        "",
        f"## Decision: **{payload.get('decision')}**",
        "",
        "## Time x Tactic x Horizon",
        "",
        "| Time | Tactic | Horizon | Obs/Days | Gross | Net | Net Win | PF | Day Max | Symbol Max | Decision |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload.get("time_tactic") or []:
        dimensions = row.get("dimensions") or {}
        lines.append(
            f"| {dimensions.get('time_bucket')} | {dimensions.get('tactic')} | {row.get('horizon')} | "
            f"{row.get('observed_count')}/{row.get('observed_day_count')} | "
            f"{row.get('average_gross_return_pct')}% | {row.get('average_net_return_pct')}% | "
            f"{float(row.get('net_win_rate') or 0):.1%} | {row.get('net_profit_factor')} | "
            f"{float(row.get('maximum_day_share') or 0):.1%} | "
            f"{float(row.get('maximum_symbol_share') or 0):.1%} | `{row.get('decision')}` |"
        )
    lines += [
        "",
        "## Controlled-Adoption Candidates",
        "",
    ]
    adoption = payload.get("controlled_adoption_candidates") or []
    if not adoption:
        lines.append("- None")
    else:
        for row in adoption:
            dimensions = row.get("dimensions") or {}
            lines.append(
                f"- `{dimensions.get('time_bucket')} | {dimensions.get('tactic')} | {row.get('horizon')}`: "
                f"net {row.get('average_net_return_pct')}%, PF {row.get('net_profit_factor')}, "
                f"{row.get('observed_count')} observations across {row.get('observed_day_count')} days"
            )
    lines += [
        "",
        "## Observation Candidates",
        "",
    ]
    observation = payload.get("observation_candidates") or []
    if not observation:
        lines.append("- None")
    else:
        for row in observation:
            dimensions = row.get("dimensions") or {}
            lines.append(
                f"- `{dimensions.get('time_bucket')} | {dimensions.get('tactic')} | {row.get('horizon')}`: "
                f"net {row.get('average_net_return_pct')}%, PF {row.get('net_profit_factor')}, "
                f"worst leave-one-day-out {row.get('worst_leave_one_day_out_net_return_pct')}%, "
                f"robust={row.get('robust_across_days')}"
            )
    lines += [
        "",
        "## Next Action",
        "",
        f"- decision: **{(payload.get('next_action') or {}).get('decision')}**",
        f"- reason: {(payload.get('next_action') or {}).get('reason')}",
        "- behavior change authorized: **False**",
    ]
    return "\n".join(lines) + "\n"


def write_horizon_alignment_review(
    *,
    reports_root: Path,
    start: str,
    end: str,
    output_dir: Path,
    cost_profile_path: Path | None = None,
) -> dict[str, str]:
    payload = build_horizon_alignment_review(
        reports_root=reports_root,
        start=start,
        end=end,
        cost_profile_path=cost_profile_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "horizon_alignment_review.json"
    md_path = output_dir / "horizon_alignment_review.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_horizon_alignment_review(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
