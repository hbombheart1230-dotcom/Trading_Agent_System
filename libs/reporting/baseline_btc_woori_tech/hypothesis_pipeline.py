from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    HYPOTHESIS_BTC_THRESHOLDS_PCT,
    HYPOTHESIS_CONTRACT_ID,
    HYPOTHESIS_CUMULATIVE_SCHEMA,
    HYPOTHESIS_DAILY_SCHEMA,
    HYPOTHESIS_HORIZONS,
    HYPOTHESIS_PROSPECTIVE_START_DAY,
    STRONG_BTC_POLICY_ID,
)
from .hypothesis_features import build_hypothesis_features
from .hypothesis_forward import entry_forward_outcomes, summarize_outcomes


DAILY_NAME = "q12_btc_woori_hypothesis_validation.json"
DAILY_REPORT_NAME = "q12_btc_woori_hypothesis_validation.md"


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _phase(day: str) -> str:
    return "PROSPECTIVE" if day >= HYPOTHESIS_PROSPECTIVE_START_DAY else "BACKCHECK"


def _daily_dimensions(payload: Mapping[str, Any]) -> dict[str, list[str]]:
    features = payload.get("features")
    features = features if isinstance(features, Mapping) else {}
    btc = features.get("btc_0855")
    btc = btc if isinstance(btc, Mapping) else {}
    daily = features.get("btc_daily_context")
    daily = daily if isinstance(daily, Mapping) else {}
    opening = features.get("woori_opening")
    opening = opening if isinstance(opening, Mapping) else {}
    dimensions: dict[str, list[str]] = {
        "btc_threshold": [],
        "surge_state": [],
        "breakout_state": [],
        "opening_gap_band": [],
    }
    btc_return = btc.get("return_24h_pct")
    if btc_return is not None:
        value = float(btc_return)
        dimensions["btc_threshold"] = [
            f"GTE_{int(threshold)}PCT"
            for threshold in HYPOTHESIS_BTC_THRESHOLDS_PCT
            if value >= threshold
        ]
    for axis, value in (
        ("surge_state", daily.get("surge_state")),
        ("breakout_state", daily.get("breakout_state")),
        ("opening_gap_band", opening.get("opening_gap_band")),
    ):
        if value not in (None, "", "MISSING"):
            dimensions[axis] = [str(value)]
    return dimensions


def _hypothesis_paths(
    payload: Mapping[str, Any], *, method: str
) -> list[str]:
    features = payload.get("features")
    features = features if isinstance(features, Mapping) else {}
    btc = features.get("btc_0855")
    btc = btc if isinstance(btc, Mapping) else {}
    daily = features.get("btc_daily_context")
    daily = daily if isinstance(daily, Mapping) else {}
    opening = features.get("woori_opening")
    opening = opening if isinstance(opening, Mapping) else {}
    local = (features.get("entry_methods") or {}).get(method)
    local = local if isinstance(local, Mapping) else {}
    btc_return = btc.get("return_24h_pct")
    btc_return = float(btc_return) if btc_return is not None else None
    surge = str(daily.get("surge_state") or "")
    breakout = str(daily.get("breakout_state") or "")
    gap_band = str(opening.get("opening_gap_band") or "")
    local_confirmation = local.get("local_confirmation")
    paths = []
    if (
        btc_return is not None
        and btc_return >= 4.0
        and surge == "FIRST_SURGE"
        and breakout in {"20D_BREAKOUT", "60D_BREAKOUT", "ATH_BREAKOUT"}
        and local_confirmation is True
    ):
        paths.append("FAST_BUY_ALL_PASS")
    if (
        btc_return is not None
        and btc_return >= 3.0
        and surge == "REPEATED_SURGE"
        and gap_band == "GTE_10"
    ):
        paths.append("WAIT_OVERHEATED_GAP")
    if btc_return is not None and btc_return >= 3.0 and local_confirmation is False:
        paths.append("NO_LOCAL_RESPONSE")
    if (
        surge in {"NO_STRONG_SURGE", "REPEATED_SURGE"}
        and local_confirmation is True
    ):
        paths.append("CONTINUATION_CONTEXT")
    return paths


def _collect_daily_payloads(root: Path, through_day: str) -> list[dict[str, Any]]:
    output = []
    for path in sorted(root.glob(f"*/{DAILY_NAME}")):
        if path.parent.name > through_day:
            continue
        payload = _read(path)
        if payload.get("contract_id") == HYPOTHESIS_CONTRACT_ID:
            output.append(payload)
    return output


def build_cumulative_hypothesis(
    *, root: Path, through_day: str
) -> dict[str, Any]:
    days = _collect_daily_payloads(root, through_day)
    legacy_days = sorted(
        path.parent.name
        for path in root.glob("*/baseline_btc_woori_decisions.json")
        if path.parent.name <= through_day
    )
    validated_days = sorted(str(payload.get("day") or "") for payload in days)
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    phase_days: dict[str, set[str]] = defaultdict(set)
    for payload in days:
        phase = str(payload.get("evidence_phase") or "BACKCHECK")
        day = str(payload.get("day") or "")
        phase_days[phase].add(day)
        dimensions = _daily_dimensions(payload)
        outcomes = payload.get("entry_outcomes")
        outcomes = outcomes if isinstance(outcomes, Mapping) else {}
        for method, method_payload in outcomes.items():
            method_payload = method_payload if isinstance(method_payload, Mapping) else {}
            returns = method_payload.get("returns")
            returns = returns if isinstance(returns, Mapping) else {}
            for horizon in HYPOTHESIS_HORIZONS:
                checkpoint = returns.get(horizon)
                checkpoint = checkpoint if isinstance(checkpoint, Mapping) else {}
                if checkpoint.get("status") != "OBSERVED":
                    continue
                for axis, values in dimensions.items():
                    for value in values:
                        grouped[(phase, axis, value, str(method), horizon)].append(dict(checkpoint))
                for path_value in _hypothesis_paths(payload, method=str(method)):
                    grouped[
                        (phase, "hypothesis_path", path_value, str(method), horizon)
                    ].append(dict(checkpoint))
                local = (
                    ((payload.get("features") or {}).get("entry_methods") or {}).get(method)
                    if isinstance(payload.get("features"), Mapping)
                    else {}
                )
                local = local if isinstance(local, Mapping) else {}
                local_value = local.get("local_confirmation")
                if local_value is not None:
                    grouped[
                        (
                            phase,
                            "local_confirmation",
                            "PASS" if local_value else "FAIL",
                            str(method),
                            horizon,
                        )
                    ].append(dict(checkpoint))
    rows = []
    for key in sorted(grouped):
        phase, axis, value, method, horizon = key
        rows.append(
            {
                "evidence_phase": phase,
                "axis": axis,
                "value": value,
                "entry_method": method,
                "horizon": horizon,
                "metrics": summarize_outcomes(grouped[key]),
            }
        )
    return {
        "schema_version": HYPOTHESIS_CUMULATIVE_SCHEMA,
        "contract_id": HYPOTHESIS_CONTRACT_ID,
        "candidate_id": STRONG_BTC_POLICY_ID,
        "behavior_effect": "evaluation_only",
        "through_day": through_day,
        "phase_boundary": HYPOTHESIS_PROSPECTIVE_START_DAY,
        "phase_day_counts": {key: len(value) for key, value in sorted(phase_days.items())},
        "source_day_count": len(days),
        "coverage": {
            "legacy_q12_day_count": len(legacy_days),
            "exact_hypothesis_day_count": len(validated_days),
            "legacy_context_only_day_count": len(set(legacy_days) - set(validated_days)),
            "legacy_context_only_days": sorted(set(legacy_days) - set(validated_days)),
            "boundary": (
                "Legacy 09:05-or-later Q12 decisions are context only when exact "
                "08:55 and 09:03 point-in-time evidence is absent."
            ),
        },
        "row_count": len(rows),
        "rows": rows,
        "integrity": {
            "backcheck_and_prospective_separated": True,
            "missing_values_inferred": False,
            "future_data_used_for_entry_features": False,
        },
    }


def _fmt(value: Any, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}{suffix}"
    return f"{value}{suffix}"


def render_daily(payload: Mapping[str, Any]) -> str:
    features = payload.get("features") or {}
    btc = features.get("btc_0855") or {}
    daily = features.get("btc_daily_context") or {}
    opening = features.get("woori_opening") or {}
    lines = [
        f"# Q12 BTC-Woori Five-Variable Validation ({payload.get('day')})",
        "",
        f"- Evidence phase: `{payload.get('evidence_phase')}`",
        f"- Candidate: `{payload.get('candidate_id')}`",
        "- Behavior effect: `observation_only`",
        f"- BTC 08:55 24h return: {_fmt(btc.get('return_24h_pct'), '%')}",
        f"- Surge state: `{daily.get('surge_state') or 'MISSING'}`",
        f"- Breakout state: `{daily.get('breakout_state') or 'MISSING'}`",
        f"- Woori opening gap: {_fmt(opening.get('opening_gap_pct'), '%')} (`{opening.get('opening_gap_band')}`)",
        "",
        "## Entry-Time Outcomes",
        "",
        "| Entry | Local confirm | Horizon | Net return | MFE | MAE |",
        "|---|---|---|---:|---:|---:|",
    ]
    methods = features.get("entry_methods") or {}
    for method, outcome in (payload.get("entry_outcomes") or {}).items():
        local = methods.get(method) or {}
        returns = outcome.get("returns") or {}
        if not returns:
            lines.append(
                f"| {method} | {local.get('local_confirmation')} | - | MISSING ({outcome.get('reason')}) | - | - |"
            )
            continue
        for horizon in HYPOTHESIS_HORIZONS:
            row = returns.get(horizon) or {}
            lines.append(
                f"| {method} | {local.get('local_confirmation')} | {horizon} | "
                f"{_fmt(row.get('net_return_pct'), '%')} | {_fmt(row.get('mfe_pct'), '%')} | "
                f"{_fmt(row.get('mae_pct'), '%')} |"
            )
    lines += [
        "",
        "## Boundary",
        "",
        "- BACKCHECK and PROSPECTIVE evidence are never pooled.",
        "- Missing point-in-time evidence remains missing; it is not approximated.",
        "- This report cannot create an order or alter Q12 eligibility.",
    ]
    return "\n".join(lines) + "\n"


def render_cumulative(payload: Mapping[str, Any]) -> str:
    lines = [
        f"# Q12 BTC-Woori Hypothesis Cumulative ({payload.get('through_day')})",
        "",
        f"- Contract: `{payload.get('contract_id')}`",
        f"- Phase days: `{payload.get('phase_day_counts')}`",
        "- BACKCHECK and PROSPECTIVE are reported separately.",
        "",
        "| Phase | Axis | Value | Entry | Horizon | N | Win | Avg net | MFE | MAE | PF |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("rows") or []:
        metric = row.get("metrics") or {}
        lines.append(
            f"| {row.get('evidence_phase')} | {row.get('axis')} | {row.get('value')} | "
            f"{row.get('entry_method')} | {row.get('horizon')} | {metric.get('sample_count')} | "
            f"{float(metric.get('win_rate') or 0):.1%} | {float(metric.get('avg_return_pct') or 0):.4f}% | "
            f"{_fmt(metric.get('avg_mfe_pct'), '%')} | {_fmt(metric.get('avg_mae_pct'), '%')} | "
            f"{_fmt(metric.get('profit_factor'))} |"
        )
    return "\n".join(lines) + "\n"


def build_hypothesis_validation_artifacts(
    *,
    day: str,
    reports_root: Path,
    candles: list[Mapping[str, Any]],
    btc_signals: Mapping[str, Any],
    cost_pct: float,
    slippage_pct: float,
) -> dict[str, str]:
    root = reports_root / "evaluation" / "baseline_btc_woori_tech"
    output_dir = root / day
    features = build_hypothesis_features(
        day=day,
        candles=list(candles),
        btc_signals=btc_signals,
    )
    drag_pct = float(cost_pct) + float(slippage_pct)
    outcomes = entry_forward_outcomes(
        features.get("entry_methods") or {},
        candles=list(candles),
        drag_pct=drag_pct,
    )
    observed = sum(
        checkpoint.get("status") == "OBSERVED"
        for outcome in outcomes.values()
        for checkpoint in (outcome.get("returns") or {}).values()
    )
    payload = {
        "schema_version": HYPOTHESIS_DAILY_SCHEMA,
        "contract_id": HYPOTHESIS_CONTRACT_ID,
        "candidate_id": STRONG_BTC_POLICY_ID,
        "behavior_effect": "observation_only",
        "day": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_phase": _phase(day),
        "prospective_start_day": HYPOTHESIS_PROSPECTIVE_START_DAY,
        "evidence_status": "AVAILABLE" if observed else "INSUFFICIENT_EVIDENCE",
        "cost_model": {
            "round_trip_cost_pct": round(float(cost_pct), 6),
            "slippage_pct": round(float(slippage_pct), 6),
            "total_drag_pct": round(drag_pct, 6),
        },
        "features": features,
        "entry_outcomes": outcomes,
        "observed_checkpoint_count": observed,
        "order_execution_allowed": False,
        "order_intent": None,
    }
    daily_json = output_dir / DAILY_NAME
    daily_md = output_dir / DAILY_REPORT_NAME
    _write(daily_json, payload)
    daily_md.write_text(render_daily(payload), encoding="utf-8")
    cumulative = build_cumulative_hypothesis(root=root, through_day=day)
    cumulative_dir = root / "hypothesis_validation"
    cumulative_json = cumulative_dir / "q12_btc_woori_hypothesis_cumulative.json"
    cumulative_md = cumulative_dir / "q12_btc_woori_hypothesis_cumulative.md"
    _write(cumulative_json, cumulative)
    cumulative_md.write_text(render_cumulative(cumulative), encoding="utf-8")
    return {
        "daily_json": str(daily_json),
        "daily_markdown": str(daily_md),
        "cumulative_json": str(cumulative_json),
        "cumulative_markdown": str(cumulative_md),
    }
