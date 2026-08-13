from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

from .integrity import value_at
from .prospective_contract import (
    CANDIDATES,
    FIRST_ELIGIBLE_DAY,
    FIXED_VALIDATION_DAYS,
    MINIMUM_DAY_SYMBOL_COUNT,
    MINIMUM_PROFIT_FACTOR,
    MINIMUM_TARGET_COVERAGE,
    contract_payload,
)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _matches(row: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    return str(value_at(row, str(candidate["feature_path"]))) == str(candidate["expected_value"])


def _observation(row: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    horizon = str(candidate["target_horizon"])
    checkpoint = value_at(row, f"outcomes.checkpoints.{horizon}")
    checkpoint = checkpoint if isinstance(checkpoint, Mapping) else {}
    return {
        "candidate_id": candidate["candidate_id"],
        "day": value_at(row, "identity.day"),
        "episode_id": value_at(row, "identity.episode_id"),
        "decision_epoch": value_at(row, "identity.decision_epoch"),
        "symbol": value_at(row, "identity.symbol"),
        "symbol_name": value_at(row, "identity.symbol_name"),
        "feature_path": candidate["feature_path"],
        "feature_value": value_at(row, str(candidate["feature_path"])),
        "matched": _matches(row, candidate),
        "target_horizon": horizon,
        "target_status": checkpoint.get("status") or "MISSING",
        "net_return_pct": _number(checkpoint.get("net_return_pct")),
        "mfe_pct": _number(checkpoint.get("mfe_pct")),
        "mae_pct": _number(checkpoint.get("mae_pct")),
    }


def _metrics(observations: Sequence[Mapping[str, Any]], *, matched: bool | None = None) -> dict[str, Any]:
    selected = [row for row in observations if matched is None or bool(row.get("matched")) is matched]
    observed = [row for row in selected if _number(row.get("net_return_pct")) is not None]
    first_by_day_symbol: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in sorted(observed, key=lambda item: int(item.get("decision_epoch") or 0)):
        key = (str(row.get("day") or ""), str(row.get("symbol") or ""))
        first_by_day_symbol.setdefault(key, row)
    independent = list(first_by_day_symbol.values())
    values = [float(row["net_return_pct"]) for row in independent]
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    gross_loss = abs(sum(losses))
    return {
        "episode_count": len(selected),
        "observed_count": len(observed),
        "day_symbol_count": len(independent),
        "target_coverage": round(len(observed) / len(selected), 4) if selected else 1.0,
        "win_rate": round(len(wins) / len(values), 4) if values else None,
        "avg_net_return_pct": round(mean(values), 4) if values else None,
        "profit_factor": round(sum(wins) / gross_loss, 4) if gross_loss else None,
        "avg_mfe_pct": round(mean(value for row in independent if (value := _number(row.get("mfe_pct"))) is not None), 4) if any(_number(row.get("mfe_pct")) is not None for row in independent) else None,
        "avg_mae_pct": round(mean(value for row in independent if (value := _number(row.get("mae_pct"))) is not None), 4) if any(_number(row.get("mae_pct")) is not None for row in independent) else None,
    }


def _candidate_summary(candidate: Mapping[str, Any], observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidate_rows = [row for row in observations if row.get("candidate_id") == candidate["candidate_id"]]
    branch = _metrics(candidate_rows, matched=True)
    control = _metrics(candidate_rows, matched=False)
    branch_avg = _number(branch.get("avg_net_return_pct"))
    control_avg = _number(control.get("avg_net_return_pct"))
    return {
        "candidate": dict(candidate),
        "branch": branch,
        "control_complement": control,
        "alpha_vs_complement_pct": round(branch_avg - control_avg, 4) if branch_avg is not None and control_avg is not None else None,
    }


def _decision(summary: Mapping[str, Any], valid_day_count: int) -> dict[str, Any]:
    if valid_day_count < FIXED_VALIDATION_DAYS:
        return {"status": "COLLECTING", "remaining_valid_days": FIXED_VALIDATION_DAYS - valid_day_count, "manual_patch_review_eligible": False, "behavior_patch_allowed": False}
    branch = summary.get("branch") or {}
    alpha = _number(summary.get("alpha_vs_complement_pct"))
    if int(branch.get("day_symbol_count") or 0) < MINIMUM_DAY_SYMBOL_COUNT:
        status = "RETAIN_SHADOW_INSUFFICIENT_BRANCH_SAMPLE"
    elif float(branch.get("target_coverage") or 0.0) < MINIMUM_TARGET_COVERAGE:
        status = "DATA_QUALITY_FAIL"
    elif (
        _number(branch.get("avg_net_return_pct")) is not None
        and float(branch["avg_net_return_pct"]) > 0.0
        and _number(branch.get("profit_factor")) is not None
        and float(branch["profit_factor"]) >= MINIMUM_PROFIT_FACTOR
        and alpha is not None
        and alpha > 0.0
    ):
        status = "SINGLE_BEHAVIOR_PATCH_REVIEW_ELIGIBLE"
    else:
        status = "REJECT_PROSPECTIVE_EFFECT_NOT_CONFIRMED"
    return {
        "status": status,
        "remaining_valid_days": 0,
        "manual_patch_review_eligible": status == "SINGLE_BEHAVIOR_PATCH_REVIEW_ELIGIBLE",
        "behavior_patch_allowed": False,
    }


def _render(payload: Mapping[str, Any], *, cumulative: bool) -> str:
    title = "Cumulative" if cumulative else str(payload.get("day") or "Daily")
    lines = [
        f"# Rank-1 Fixed Candidate Prospective Shadow - {title}",
        "",
        f"* Behavior effect: **NONE (observation only)**",
        f"* Contract: `{payload.get('contract_sha256')}`",
        f"* Status: **{payload.get('status')}**",
        f"* Valid days: **{payload.get('valid_day_count', 0)} / {FIXED_VALIDATION_DAYS}**",
        "",
        "| Candidate | Responsibility | Target | Independent N | Win | Avg net | Alpha vs control | Decision |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in payload.get("candidate_summaries") or []:
        candidate = item.get("candidate") or {}
        branch = item.get("branch") or {}
        decision = item.get("decision") or {}
        def fmt(value: Any) -> str:
            return "-" if value is None else f"{float(value):.4f}%"
        lines.append(
            f"| {candidate.get('candidate_id')} | {candidate.get('responsibility')} | {candidate.get('target_horizon')} | "
            f"{branch.get('day_symbol_count', 0)} | {fmt(None if branch.get('win_rate') is None else float(branch['win_rate']) * 100)} | "
            f"{fmt(branch.get('avg_net_return_pct'))} | {fmt(item.get('alpha_vs_complement_pct'))} | {decision.get('status', '-')} |"
        )
    lines.extend(["", "No decision in this report changes live ranking, entry, exit, approval, or execution.", ""])
    return "\n".join(lines)


def build_prospective_shadow(
    *,
    day: str,
    reports_root: Path,
    mart_root: Path | None = None,
) -> dict[str, Any]:
    normalized_day = str(day)[:10]
    mart_root = mart_root or reports_root / "evaluation" / "feature_mart" / "opening_rank1"
    prospective_root = mart_root / "prospective"
    contract = contract_payload()
    mart = _read(mart_root / "feature_mart.json")
    all_rows = list(mart.get("episodes") or []) if isinstance(mart, Mapping) else []
    day_rows = [
        row for row in all_rows
        if isinstance(row, Mapping)
        and value_at(row, "identity.day") == normalized_day
        and value_at(row, "identity.cohort_source") == "PROSPECTIVE_OPENING_SHADOW"
    ]
    opening = _read(reports_root / "evaluation" / "opening_rank1_shadow" / normalized_day / "opening_rank1_shadow_daily.json")
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
    observations = [
        _observation(row, candidate)
        for candidate in CANDIDATES
        for row in day_rows
    ]
    daily_summaries = [_candidate_summary(candidate, observations) for candidate in CANDIDATES]
    daily_payload = {
        "schema_version": "rank1_prospective_shadow_daily.v1",
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "contract_sha256": contract["contract_sha256"],
        "day": normalized_day,
        "eligible": eligible,
        "status": status,
        "opening_source_status": opening_status,
        "episode_count": len(day_rows),
        "valid_day_count": 1 if status in {"VALID", "VALID_NO_EPISODES"} else 0,
        "candidate_summaries": daily_summaries,
        "observations": observations,
    }
    day_root = prospective_root / normalized_day
    _write(day_root / "rank1_candidate_shadow_daily.json", daily_payload)
    (day_root / "rank1_candidate_shadow_daily.md").write_text(_render(daily_payload, cumulative=False), encoding="utf-8")
    _write(prospective_root / "frozen_candidate_contract.json", contract)

    daily_payloads = []
    for path in sorted(prospective_root.glob("20??-??-??/rank1_candidate_shadow_daily.json")):
        payload = _read(path)
        if isinstance(payload, Mapping) and str(payload.get("day") or "") >= FIRST_ELIGIBLE_DAY:
            daily_payloads.append(payload)
    valid_day_count = sum(str(payload.get("status")) in {"VALID", "VALID_NO_EPISODES"} for payload in daily_payloads)
    cumulative_observations = [
        row
        for payload in daily_payloads
        if str(payload.get("status")) in {"VALID", "VALID_NO_EPISODES"}
        for row in payload.get("observations") or []
        if isinstance(row, Mapping)
    ]
    cumulative_summaries = []
    for candidate in CANDIDATES:
        candidate_rows = [row for row in cumulative_observations if row.get("candidate_id") == candidate["candidate_id"]]
        item = _candidate_summary(candidate, candidate_rows)
        item["decision"] = _decision(item, valid_day_count)
        cumulative_summaries.append(item)
    review_eligible = [item for item in cumulative_summaries if item["decision"]["manual_patch_review_eligible"]]
    cumulative_payload = {
        "schema_version": "rank1_prospective_shadow_cumulative.v1",
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "contract_sha256": contract["contract_sha256"],
        "through_day": normalized_day,
        "status": "PATCH_REVIEW_AVAILABLE" if review_eligible else "COLLECTING" if valid_day_count < FIXED_VALIDATION_DAYS else "NO_AUTOMATIC_PROMOTION",
        "valid_day_count": valid_day_count,
        "candidate_summaries": cumulative_summaries,
        "single_patch_review_candidates": [item["candidate"]["candidate_id"] for item in review_eligible],
    }
    _write(prospective_root / "rank1_candidate_shadow_cumulative.json", cumulative_payload)
    (prospective_root / "rank1_candidate_shadow_cumulative.md").write_text(_render(cumulative_payload, cumulative=True), encoding="utf-8")
    return {
        "ok": status in {"VALID", "VALID_NO_EPISODES", "IMPLEMENTATION_DAY_EXCLUDED"},
        "day_status": status,
        "valid_day_count": valid_day_count,
        "daily_json_path": str(day_root / "rank1_candidate_shadow_daily.json"),
        "daily_md_path": str(day_root / "rank1_candidate_shadow_daily.md"),
        "cumulative_json_path": str(prospective_root / "rank1_candidate_shadow_cumulative.json"),
        "cumulative_md_path": str(prospective_root / "rank1_candidate_shadow_cumulative.md"),
    }
