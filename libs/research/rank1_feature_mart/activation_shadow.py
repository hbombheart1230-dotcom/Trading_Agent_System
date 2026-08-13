from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from .activation_contract import (
    FIRST_ELIGIBLE_DAY,
    MAXIMUM_VALID_DAYS,
    MINIMUM_INDEPENDENT_DAY_SYMBOLS,
    MINIMUM_TARGET_COVERAGE,
    TARGET_HORIZON,
    contract_payload,
)
from .integrity import value_at


HORIZONS = ("+5m", "+15m", "+30m", "EOD")


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _subgroups(row: Mapping[str, Any]) -> dict[str, Any]:
    completed_return = _number(value_at(row, "chart.completed_return_1m_pct"))
    return {
        "theme_match": value_at(row, "scanner.theme_match"),
        "directional_breadth_ge4": int(
            value_at(row, "scanner.directional_component_count") or 0
        ) >= 4,
        "completed_1m_positive": (
            None if completed_return is None else completed_return > 0.0
        ),
        "above_vwap": value_at(row, "chart.above_vwap"),
        "recurrent_rank": int(
            value_at(row, "scanner.prior_rank1_observations_5m") or 0
        ) > 0,
        "quote_status": value_at(row, "execution_evidence.quote_status"),
        "candidate_setup": value_at(row, "scanner.candidate_setup"),
    }


def _observation(row: Mapping[str, Any]) -> dict[str, Any]:
    checkpoints = {}
    for horizon in HORIZONS:
        checkpoint = value_at(row, f"outcomes.checkpoints.{horizon}")
        checkpoint = checkpoint if isinstance(checkpoint, Mapping) else {}
        checkpoints[horizon] = {
            "status": checkpoint.get("status") or "MISSING",
            "net_return_pct": _number(checkpoint.get("net_return_pct")),
            "mfe_pct": _number(checkpoint.get("mfe_pct")),
            "mae_pct": _number(checkpoint.get("mae_pct")),
        }
    return {
        "day": value_at(row, "identity.day"),
        "episode_id": value_at(row, "identity.episode_id"),
        "decision_epoch": value_at(row, "identity.decision_epoch"),
        "symbol": value_at(row, "identity.symbol"),
        "symbol_name": value_at(row, "identity.symbol_name"),
        "matched": value_at(row, "scanner.source_top_change_rate") is True,
        "sources": value_at(row, "scanner.sources") or [],
        "top_change_rate_observation_status": value_at(
            row, "scanner.top_change_rate_observation_status"
        ),
        "top_change_rate_observation": dict(
            value_at(row, "scanner.top_change_rate_observation") or {}
        ),
        "subgroups": _subgroups(row),
        "strategy": dict(value_at(row, "strategy") or {}),
        "checkpoints": checkpoints,
    }


def _independent(
    observations: Sequence[Mapping[str, Any]], *, matched: bool
) -> list[Mapping[str, Any]]:
    first: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in sorted(
        (item for item in observations if bool(item.get("matched")) is matched),
        key=lambda item: int(item.get("decision_epoch") or 0),
    ):
        key = (str(row.get("day") or ""), str(row.get("symbol") or ""))
        first.setdefault(key, row)
    return list(first.values())


def _metrics(
    observations: Sequence[Mapping[str, Any]], *, matched: bool
) -> dict[str, Any]:
    rows = _independent(observations, matched=matched)
    horizons: dict[str, Any] = {}
    for horizon in HORIZONS:
        values = [
            value
            for row in rows
            if (value := _number((row.get("checkpoints") or {}).get(horizon, {}).get("net_return_pct")))
            is not None
        ]
        wins = [value for value in values if value > 0.0]
        losses = [value for value in values if value < 0.0]
        gross_loss = abs(sum(losses))
        horizons[horizon] = {
            "observed_count": len(values),
            "coverage": round(len(values) / len(rows), 4) if rows else 1.0,
            "win_rate": round(len(wins) / len(values), 4) if values else None,
            "avg_net_return_pct": round(mean(values), 4) if values else None,
            "profit_factor": round(sum(wins) / gross_loss, 4) if gross_loss else None,
        }
    return {"day_symbol_count": len(rows), "horizons": horizons}


def _subgroup_metrics(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matched = _independent(observations, matched=True)
    result = {}
    for key in (
        "theme_match",
        "directional_breadth_ge4",
        "completed_1m_positive",
        "above_vwap",
        "recurrent_rank",
    ):
        for expected in (True, False):
            rows = [
                row
                for row in matched
                if (row.get("subgroups") or {}).get(key) is expected
            ]
            values = [
                value
                for row in rows
                if (
                    value := _number(
                        (row.get("checkpoints") or {})
                        .get(TARGET_HORIZON, {})
                        .get("net_return_pct")
                    )
                )
                is not None
            ]
            result[f"{key}={str(expected).lower()}"] = {
                "day_symbol_count": len(rows),
                "observed_count": len(values),
                "avg_net_return_pct": round(mean(values), 4) if values else None,
                "win_rate": (
                    round(sum(value > 0.0 for value in values) / len(values), 4)
                    if values
                    else None
                ),
            }
    return result


def _decision(
    *, valid_day_count: int, branch: Mapping[str, Any]
) -> dict[str, Any]:
    count = int(branch.get("day_symbol_count") or 0)
    target = (branch.get("horizons") or {}).get(TARGET_HORIZON) or {}
    if count >= MINIMUM_INDEPENDENT_DAY_SYMBOLS:
        status = "MANUAL_SINGLE_PATCH_REVIEW_READY"
    elif valid_day_count >= MAXIMUM_VALID_DAYS:
        status = "RETAIN_SHADOW_INSUFFICIENT_SAMPLE"
    else:
        status = "COLLECTING"
    quality_ok = float(target.get("coverage") or 0.0) >= MINIMUM_TARGET_COVERAGE
    return {
        "status": status,
        "independent_day_symbol_count": count,
        "remaining_sample_count": max(0, MINIMUM_INDEPENDENT_DAY_SYMBOLS - count),
        "remaining_valid_days": max(0, MAXIMUM_VALID_DAYS - valid_day_count),
        "target_coverage_ok": quality_ok,
        "behavior_patch_allowed": False,
    }


def _render(payload: Mapping[str, Any]) -> str:
    branch = payload.get("branch") or {}
    control = payload.get("control_complement") or {}
    lines = [
        "# Rank-1 Fresh Change Activation Shadow",
        "",
        "* Behavior effect: **NONE (observation only)**",
        f"* Through day: **{payload.get('through_day')}**",
        f"* Status: **{(payload.get('decision') or {}).get('status')}**",
        f"* Valid days: **{payload.get('valid_day_count', 0)} / {MAXIMUM_VALID_DAYS}**",
        f"* Independent matched day-symbols: **{branch.get('day_symbol_count', 0)} / {MINIMUM_INDEPENDENT_DAY_SYMBOLS}**",
        "",
        "| Group | Horizon | N | Coverage | Win | Avg net | PF |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, metrics in (("fresh-change", branch), ("complement", control)):
        for horizon in HORIZONS:
            row = (metrics.get("horizons") or {}).get(horizon) or {}
            win = "-" if row.get("win_rate") is None else f"{float(row['win_rate']) * 100:.2f}%"
            avg = "-" if row.get("avg_net_return_pct") is None else f"{float(row['avg_net_return_pct']):.4f}%"
            pf = "-" if row.get("profit_factor") is None else f"{float(row['profit_factor']):.4f}"
            lines.append(
                f"| {name} | {horizon} | {row.get('observed_count', 0)} | "
                f"{float(row.get('coverage') or 0.0) * 100:.2f}% | {win} | {avg} | {pf} |"
            )
    lines.extend(
        [
            "",
            "Theme, breadth, completed-bar, VWAP, recurrence, and quote fields are descriptive subgroups, not entry gates.",
            "No result in this report changes ranking, entry, exit, approval, or execution.",
            "",
        ]
    )
    return "\n".join(lines)


def build_fresh_change_activation_shadow(
    *, day: str, reports_root: Path, mart_root: Path | None = None
) -> dict[str, Any]:
    normalized_day = str(day)[:10]
    mart_root = mart_root or reports_root / "evaluation" / "feature_mart" / "opening_rank1"
    output_root = mart_root / "fresh_change_activation"
    contract = contract_payload()
    mart = _read(mart_root / "feature_mart.json")
    episodes = [row for row in (mart.get("episodes") or []) if isinstance(row, Mapping)]
    historical = [
        _observation(row)
        for row in episodes
        if str(value_at(row, "identity.day") or "") < FIRST_ELIGIBLE_DAY
    ]
    day_rows = [
        row
        for row in episodes
        if value_at(row, "identity.day") == normalized_day
        and value_at(row, "identity.cohort_source") == "PROSPECTIVE_OPENING_SHADOW"
    ]
    opening = _read(
        reports_root
        / "evaluation"
        / "opening_rank1_shadow"
        / normalized_day
        / "opening_rank1_shadow_daily.json"
    )
    opening_status = str(opening.get("day_status") or "MISSING") if isinstance(opening, Mapping) else "MISSING"
    eligible = normalized_day >= FIRST_ELIGIBLE_DAY
    if not eligible:
        status = "IMPLEMENTATION_DAY_EXCLUDED"
    elif opening_status == "NO_OPENING_RANK1" and not day_rows:
        status = "VALID_NO_EPISODES"
    elif opening_status != "VALID":
        status = f"SOURCE_{opening_status}"
    elif not day_rows:
        status = "MART_DAY_MISSING"
    else:
        status = "VALID"
    daily = {
        "schema_version": "rank1_fresh_change_activation_daily.v1",
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "contract_sha256": contract["contract_sha256"],
        "day": normalized_day,
        "status": status,
        "opening_source_status": opening_status,
        "observations": [_observation(row) for row in day_rows],
    }
    day_root = output_root / normalized_day
    _write(day_root / "fresh_change_activation_daily.json", daily)

    daily_payloads = []
    for path in sorted(output_root.glob("20??-??-??/fresh_change_activation_daily.json")):
        payload = _read(path)
        if isinstance(payload, Mapping) and str(payload.get("day") or "") >= FIRST_ELIGIBLE_DAY:
            daily_payloads.append(payload)
    valid = [
        payload
        for payload in daily_payloads
        if payload.get("status") in {"VALID", "VALID_NO_EPISODES"}
    ]
    observations = [
        row
        for payload in valid
        for row in payload.get("observations") or []
        if isinstance(row, Mapping)
    ]
    branch = _metrics(observations, matched=True)
    control = _metrics(observations, matched=False)
    historical_branch = _metrics(historical, matched=True)
    historical_control = _metrics(historical, matched=False)
    cumulative = {
        "schema_version": "rank1_fresh_change_activation_cumulative.v1",
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "contract_sha256": contract["contract_sha256"],
        "through_day": normalized_day,
        "valid_day_count": len(valid),
        "historical_reference": {
            "through_day": FIRST_ELIGIBLE_DAY,
            "branch": historical_branch,
            "control_complement": historical_control,
            "subgroups": _subgroup_metrics(historical),
        },
        "branch": branch,
        "control_complement": control,
        "subgroups": _subgroup_metrics(observations),
        "decision": _decision(valid_day_count=len(valid), branch=branch),
    }
    _write(output_root / "frozen_contract.json", contract)
    _write(output_root / "fresh_change_activation_cumulative.json", cumulative)
    (output_root / "fresh_change_activation_cumulative.md").write_text(
        _render(cumulative), encoding="utf-8"
    )
    return {
        "ok": status in {"VALID", "VALID_NO_EPISODES", "IMPLEMENTATION_DAY_EXCLUDED"},
        "day_status": status,
        "valid_day_count": len(valid),
        "decision_status": cumulative["decision"]["status"],
        "daily_json_path": str(day_root / "fresh_change_activation_daily.json"),
        "cumulative_json_path": str(output_root / "fresh_change_activation_cumulative.json"),
        "cumulative_md_path": str(output_root / "fresh_change_activation_cumulative.md"),
    }
