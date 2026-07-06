from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from libs.reporting.evaluation.metrics import performance_metrics
from libs.reporting.evaluation.trade_read_model import build_q9_trade_read_model
from libs.reporting.evaluation.artifact_inventory import iter_trade_dirs
from libs.reporting.q8_evaluation_contract import candidate_day
from libs.reporting.quant_shadow_candidate_evaluation import load_quant_shadow_candidate_payloads_for_range
from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes
from libs.runtime.broker_cost_profile import load_broker_cost_profile


HORIZONS = ("+5m", "+15m", "+30m", "EOD")
BLOCKERS_OF_INTEREST = (
    "below_vwap_reclaim_not_ready",
    "pullback_not_mature",
    "breakout_not_ready",
    "volume_confirmation_missing",
    "human_chart_sanity_guard_blocked",
    "quant_entry_block:vwap_pullback_promoted_quality_gate",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _metric_avg(metric: Mapping[str, Any]) -> str:
    data = _as_dict(metric)
    if int(data.get("count") or 0) <= 0:
        return "-"
    return str(data.get("average_return_pct"))


def _checkpoint(row: Mapping[str, Any], horizon: str) -> dict[str, Any]:
    outcome = _as_dict(row.get("shadow_forward_outcome"))
    checkpoints = _as_dict(outcome.get("checkpoints"))
    return _as_dict(checkpoints.get(horizon))


def _checkpoint_return(row: Mapping[str, Any], horizon: str) -> float | None:
    checkpoint = _checkpoint(row, horizon)
    if checkpoint.get("status") != "observed":
        return None
    return _num(checkpoint.get("return_pct"))


def _checkpoint_mfe(row: Mapping[str, Any], horizon: str) -> float | None:
    checkpoint = _checkpoint(row, horizon)
    if checkpoint.get("status") != "observed":
        return None
    return _num(checkpoint.get("mfe_pct"))


def _checkpoint_mae(row: Mapping[str, Any], horizon: str) -> float | None:
    checkpoint = _checkpoint(row, horizon)
    if checkpoint.get("status") != "observed":
        return None
    return _num(checkpoint.get("mae_pct"))


def _rail(row: Mapping[str, Any]) -> str:
    lane = _as_dict(row.get("entry_lane_observation"))
    if lane.get("market_regime_rail"):
        return _text(lane.get("market_regime_rail"))
    shadow = _as_dict(lane.get("market_regime_rail_shadow"))
    return _text(shadow.get("market_regime_rail")) or "unknown"


def _blocker(row: Mapping[str, Any]) -> str:
    for key in ("guard_reason", "reason", "primary_failure_axis"):
        value = _text(row.get(key))
        if value:
            return value
    decision = _as_dict(row.get("entry_quant_decision"))
    blockers = decision.get("blockers")
    if isinstance(blockers, list) and blockers:
        return _text(blockers[0])
    return "unknown"


def _cost_floor_pct() -> float:
    profile = load_broker_cost_profile()
    for key in ("conservative_round_trip_cost_pct", "round_trip_cost_pct", "ema_round_trip_cost_pct"):
        value = _num(profile.get(key))
        if value is not None and value > 0:
            return value * 100.0 if value < 1 else value
    return 0.0


def _candidate_rows(payloads: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        generated_at = payload.get("generated_at")
        for raw in payload.get("candidates") or []:
            if not isinstance(raw, Mapping):
                continue
            row = dict(raw)
            row.setdefault("_payload_generated_at", generated_at)
            rows.append(row)
    return attach_forward_outcomes(rows)


def _q9_candidate_rows(payloads: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        generated_at = payload.get("generated_at")
        for raw in payload.get("q9_decision_candidates") or []:
            if not isinstance(raw, Mapping):
                continue
            row = dict(raw)
            row.setdefault("_payload_generated_at", generated_at)
            rows.append(row)
    return attach_forward_outcomes(rows)


def _forward_group(rows: list[dict[str, Any]], group_key: str, *, cost_floor_pct: float) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_text(row.get(group_key)) or "unknown"].append(row)
    out: list[dict[str, Any]] = []
    for name, members in grouped.items():
        record: dict[str, Any] = {"name": name, "candidate_count": len(members)}
        days = sorted({candidate_day(row) for row in members if candidate_day(row)})
        record["observed_days"] = days
        for horizon in HORIZONS:
            returns: list[float] = []
            mfes: list[float] = []
            maes: list[float] = []
            cost_reachable = 0
            for row in members:
                ret = _checkpoint_return(row, horizon)
                mfe = _checkpoint_mfe(row, horizon)
                mae = _checkpoint_mae(row, horizon)
                if ret is not None:
                    returns.append(ret)
                if mfe is not None:
                    mfes.append(mfe)
                    if cost_floor_pct > 0 and mfe >= cost_floor_pct:
                        cost_reachable += 1
                if mae is not None:
                    maes.append(mae)
            record[horizon] = {
                "observed_count": len(returns),
                "return": performance_metrics(returns),
                "avg_mfe_pct": round(sum(mfes) / len(mfes), 4) if mfes else None,
                "avg_mae_pct": round(sum(maes) / len(maes), 4) if maes else None,
                "cost_floor_reachable_count": cost_reachable,
                "cost_floor_reachable_rate": round(cost_reachable / len(mfes), 4) if mfes else 0.0,
            }
        out.append(record)
    return sorted(out, key=lambda row: (-max(int(_as_dict(row.get(h)).get("observed_count") or 0) for h in HORIZONS), row["name"]))


def _blocker_forward_review(rows: list[dict[str, Any]], *, cost_floor_pct: float) -> dict[str, Any]:
    prepared: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["blocker"] = _blocker(row)
        item["market_rail"] = _rail(row)
        prepared.append(item)
    interested = [
        row
        for row in prepared
        if any(token in _text(row.get("blocker")) for token in BLOCKERS_OF_INTEREST)
    ]
    return {
        "schema_version": "blocker_forward_review.v1",
        "behavior_effect": "evaluation_only",
        "cost_floor_pct": round(cost_floor_pct, 4),
        "candidate_count": len(prepared),
        "focused_candidate_count": len(interested),
        "by_blocker": _forward_group(interested, "blocker", cost_floor_pct=cost_floor_pct),
        "by_market_rail": _forward_group(prepared, "market_rail", cost_floor_pct=cost_floor_pct),
    }


def _best_role_by_horizon(rows: list[dict[str, Any]], horizon: str) -> dict[str, Any]:
    by_role: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        role = _text(row.get("q9_decision_role"))
        if role not in {"P_SCANNER_PRE_STRATEGIST_UNIVERSE", "A_SCANNER_CONTROL", "B_STRATEGIST_RANKED", "C_COMMANDER_FINAL"}:
            continue
        value = _checkpoint_return(row, horizon)
        if value is not None:
            by_role[role].append(value)
    ranked = [
        {"role": role, **performance_metrics(values)}
        for role, values in by_role.items()
        if values
    ]
    ranked.sort(key=lambda row: float(row.get("expectancy_pct") or 0.0), reverse=True)
    return {"horizon": horizon, "roles": ranked, "best_role": ranked[0]["role"] if ranked else ""}


def _strategist_delta_review(q9_rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in q9_rows:
        decision_id = _text(row.get("q9_decision_id"))
        role = _text(row.get("q9_decision_role"))
        if decision_id and role:
            grouped[decision_id][role].append(row)
    deltas_by_horizon: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        strategist_delta: list[float] = []
        commander_delta: list[float] = []
        for roles in grouped.values():
            a = min(roles.get("A_SCANNER_CONTROL") or [], key=lambda r: int(float(r.get("rank") or 999)), default={})
            b = next((r for r in roles.get("B_STRATEGIST_RANKED") or [] if r.get("q9_selected")), None)
            if not b:
                b = min(roles.get("B_STRATEGIST_RANKED") or [], key=lambda r: int(float(r.get("rank") or 999)), default={})
            c = min(roles.get("C_COMMANDER_FINAL") or [], key=lambda r: int(float(r.get("rank") or 999)), default={})
            av = _checkpoint_return(a, horizon) if a else None
            bv = _checkpoint_return(b, horizon) if b else None
            cv = _checkpoint_return(c, horizon) if c else None
            if av is not None and bv is not None:
                strategist_delta.append(bv - av)
            if bv is not None and cv is not None:
                commander_delta.append(cv - bv)
        deltas_by_horizon.append(
            {
                "horizon": horizon,
                "strategist_minus_scanner_control": performance_metrics(strategist_delta),
                "commander_minus_strategist": performance_metrics(commander_delta),
            }
        )
    return {
        "schema_version": "strategist_delta_review.v1",
        "behavior_effect": "evaluation_only",
        "decision_window_count": len(grouped),
        "best_role_by_horizon": [_best_role_by_horizon(q9_rows, horizon) for horizon in HORIZONS],
        "deltas_by_horizon": deltas_by_horizon,
    }


def _trade_models(reports_root: Path, start: str, end: str) -> list[dict[str, Any]]:
    from datetime import date, timedelta

    current = date.fromisoformat(start[:10])
    final = date.fromisoformat(end[:10])
    out: list[dict[str, Any]] = []
    while current <= final:
        for trade_dir in iter_trade_dirs(reports_root, current.isoformat()):
            out.append(build_q9_trade_read_model(trade_dir))
        current += timedelta(days=1)
    return out


def _exit_counterfactual_review(models: list[dict[str, Any]]) -> dict[str, Any]:
    by_reason: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for model in models:
        exit_reason = _text((_as_dict(model.get("exit")).get("reason"))) or _text((_as_dict(model.get("outcome")).get("exit_reason"))) or "unknown"
        monitor = _as_dict(model.get("monitor"))
        shadow = _as_dict(model.get("post_exit_shadow")) or _as_dict(monitor.get("post_exit"))
        checkpoints = _as_dict(shadow.get("checkpoints"))
        actual = _num((_as_dict(model.get("outcome")).get("net_return_pct"))
                      or (_as_dict(model.get("outcome")).get("return_pct")))
        row = {"trade_id": model.get("trade_id"), "symbol": model.get("symbol"), "actual_return_pct": actual}
        for horizon in ("+5m", "+15m", "+30m", "+60m", "EOD"):
            cp = _as_dict(checkpoints.get(horizon))
            ret = _num(cp.get("return_pct"))
            row[horizon] = ret
            if ret is not None and actual is not None:
                row[f"{horizon}_improvement_pct"] = round(ret - actual, 4)
        by_reason[exit_reason].append(row)
    groups: list[dict[str, Any]] = []
    for reason, rows in by_reason.items():
        group = {"exit_reason": reason, "trade_count": len(rows)}
        for horizon in ("+5m", "+15m", "+30m", "+60m", "EOD"):
            values = [float(row[f"{horizon}_improvement_pct"]) for row in rows if row.get(f"{horizon}_improvement_pct") is not None]
            group[horizon] = performance_metrics(values)
        groups.append(group)
    return {
        "schema_version": "exit_hold_counterfactual_review.v1",
        "behavior_effect": "evaluation_only",
        "trade_count": len(models),
        "by_exit_reason": sorted(groups, key=lambda row: (-int(row["trade_count"]), row["exit_reason"])),
    }


def build_evaluation_lens_report(*, reports_root: Path, start: str, end: str) -> dict[str, Any]:
    payloads = load_quant_shadow_candidate_payloads_for_range(reports_root=reports_root, start=start, end=end)
    candidates = _candidate_rows(payloads)
    q9_rows = _q9_candidate_rows(payloads)
    models = _trade_models(reports_root, start, end)
    cost_floor = _cost_floor_pct()
    return {
        "schema_version": "evaluation_lens_report.v1",
        "behavior_effect": "evaluation_only",
        "range": {"start": start[:10], "end": end[:10]},
        "freeze_safe": True,
        "behavior_change_authorized": False,
        "evidence": {
            "shadow_payload_count": len(payloads),
            "candidate_count": len(candidates),
            "q9_candidate_count": len(q9_rows),
            "trade_model_count": len(models),
        },
        "blocker_forward_review": _blocker_forward_review(candidates, cost_floor_pct=cost_floor),
        "strategist_delta_review": _strategist_delta_review(q9_rows),
        "exit_hold_counterfactual_review": _exit_counterfactual_review(models),
        "next_required_observations": [
            "blocker forward outcome by market rail",
            "MFE/MAE and cost-floor reachability for every blocked lane",
            "strategist-vs-scanner delta by horizon",
            "commander-vs-strategist delta by horizon",
            "exit hold counterfactual by exit reason",
        ],
    }


def render_evaluation_lens_report(payload: Mapping[str, Any]) -> str:
    rng = _as_dict(payload.get("range"))
    evidence = _as_dict(payload.get("evidence"))
    lines = [
        f"# Evaluation Lens Report ({rng.get('start')} ~ {rng.get('end')})",
        "",
        "Behavior effect: evaluation_only. This report does not change trading behavior or reset the freeze window.",
        "",
        "## Evidence",
        f"- shadow payloads: {evidence.get('shadow_payload_count')}",
        f"- shadow candidates: {evidence.get('candidate_count')}",
        f"- Q9 candidates: {evidence.get('q9_candidate_count')}",
        f"- trade models: {evidence.get('trade_model_count')}",
        "",
        "## Blocker Forward Review",
        "| Blocker | Candidates | +5m avg | +15m avg | +30m avg | +30m MFE | +30m cost reachable |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    blocker = _as_dict(payload.get("blocker_forward_review"))
    for row in blocker.get("by_blocker") or []:
        h5 = _as_dict(row.get("+5m"))
        h15 = _as_dict(row.get("+15m"))
        h30 = _as_dict(row.get("+30m"))
        lines.append(
            f"| {row.get('name')} | {row.get('candidate_count')} | "
            f"{_metric_avg(_as_dict(h5.get('return')))} | "
            f"{_metric_avg(_as_dict(h15.get('return')))} | "
            f"{_metric_avg(_as_dict(h30.get('return')))} | "
            f"{h30.get('avg_mfe_pct')} | {h30.get('cost_floor_reachable_rate')} |"
        )
    lines += [
        "",
        "## Strategist Delta",
        "| Horizon | Best role | Strategist delta avg | Commander delta avg |",
        "|---|---|---:|---:|",
    ]
    strat = _as_dict(payload.get("strategist_delta_review"))
    best_by = {row.get("horizon"): row.get("best_role") for row in strat.get("best_role_by_horizon") or []}
    for row in strat.get("deltas_by_horizon") or []:
        horizon = row.get("horizon")
        sd = _as_dict(row.get("strategist_minus_scanner_control"))
        cd = _as_dict(row.get("commander_minus_strategist"))
        lines.append(
            f"| {horizon} | {best_by.get(horizon) or ''} | "
            f"{_metric_avg(sd)} | {_metric_avg(cd)} |"
        )
    lines += [
        "",
        "## Exit Hold Counterfactual",
        "| Exit reason | Trades | +5m improvement | +15m improvement | +30m improvement | EOD improvement |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    exit_review = _as_dict(payload.get("exit_hold_counterfactual_review"))
    for row in exit_review.get("by_exit_reason") or []:
        lines.append(
            f"| {row.get('exit_reason')} | {row.get('trade_count')} | "
            f"{_metric_avg(_as_dict(row.get('+5m')))} | "
            f"{_metric_avg(_as_dict(row.get('+15m')))} | "
            f"{_metric_avg(_as_dict(row.get('+30m')))} | "
            f"{_metric_avg(_as_dict(row.get('EOD')))} |"
        )
    lines += [
        "",
        "## Rules",
        "- This report can be regenerated for past days without resetting evaluation.",
        "- It adds observability only; entry, exit, scanner, strategist, commander, and monitor behavior are unchanged.",
        "- Promotion decisions still require the promotion framework and enough comparable days.",
    ]
    return "\n".join(lines) + "\n"


def write_evaluation_lens_report(
    *,
    reports_root: Path,
    start: str,
    end: str,
    output_dir: Path | None = None,
) -> dict[str, str]:
    payload = build_evaluation_lens_report(reports_root=Path(reports_root), start=start, end=end)
    out_dir = Path(output_dir) if output_dir else Path(reports_root) / "evaluation" / "lens" / end[:10]
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "evaluation_lens_report.json"
    md_path = out_dir / "evaluation_lens_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_evaluation_lens_report(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
