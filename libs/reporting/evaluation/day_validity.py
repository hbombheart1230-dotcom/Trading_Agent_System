from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
MIN_COMPLETE_WINDOWS = 20
MIN_LINKAGE_RATIO = 0.95
MIN_FORWARD_COVERAGE = 0.95


def _parse_kst(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _is_synthetic_window(row: dict[str, Any]) -> bool:
    identity = " ".join(
        str(row.get(key) or "").lower()
        for key in ("decision_id", "run_id", "candidate_pool_id")
    )
    return any(marker in identity for marker in ("test", "fixture", "synthetic"))


def build_q9_day_validity(
    *,
    day: str,
    inventory: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(KST)).astimezone(KST)
    daily = inventory.get("daily_artifacts")
    daily = daily if isinstance(daily, dict) else {}
    decision = daily.get("q9_decision_windows")
    decision = decision if isinstance(decision, dict) else {}

    window_count = int(decision.get("scanner_selection_window_count") or 0)
    complete_count = int(
        decision.get("complete_pabc_window_count")
        or decision.get("complete_abc_window_count")
        or 0
    )
    linkage_ratio = complete_count / window_count if window_count else 0.0
    synthetic_count = int(decision.get("synthetic_window_count") or 0)
    missing_selected = int(decision.get("missing_selected_candidate_count") or 0)
    invalid_forward = int(decision.get("forward_invalid_candidate_count") or 0)
    pending_forward = int(decision.get("forward_pending_candidate_count") or 0)
    observed_forward = int(decision.get("forward_observed_candidate_count") or 0)
    forward_total = int(decision.get("pre_strategist_forward_candidate_count") or 0)
    forward_usable = observed_forward + pending_forward
    forward_coverage = forward_usable / forward_total if forward_total else 0.0

    session_day = datetime.fromisoformat(day).date()
    is_future = session_day > current.date()
    is_complete = session_day < current.date() or (
        session_day == current.date() and (current.hour, current.minute) >= (15, 30)
    )

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not decision.get("exists"):
        blockers.append({"code": "missing_q9_artifact", "count": 1})
    elif not bool(decision.get("schema_match", True)):
        blockers.append({"code": "q9_schema_mismatch", "count": 1})
    if is_complete and complete_count < MIN_COMPLETE_WINDOWS:
        blockers.append(
            {
                "code": "insufficient_complete_pabc_windows",
                "count": max(0, MIN_COMPLETE_WINDOWS - complete_count),
            }
        )
    if is_complete and window_count and linkage_ratio < MIN_LINKAGE_RATIO:
        blockers.append(
            {
                "code": "pabc_linkage_ratio_below_threshold",
                "count": max(0, window_count - complete_count),
            }
        )
    if synthetic_count:
        warnings.append(
            {
                "code": "synthetic_windows_excluded",
                "count": synthetic_count,
                "invalidates_day": False,
            }
        )
    if missing_selected:
        blockers.append({"code": "missing_selected_candidate", "count": missing_selected})
    if invalid_forward:
        target = blockers if is_complete and forward_coverage < MIN_FORWARD_COVERAGE else warnings
        target.append(
            {
                "code": "invalid_forward_observation",
                "count": invalid_forward,
                "coverage": round(forward_coverage, 4),
                "required_coverage": MIN_FORWARD_COVERAGE,
                "invalidates_day": bool(is_complete and forward_coverage < MIN_FORWARD_COVERAGE),
            }
        )
    if is_complete and forward_total == 0:
        blockers.append({"code": "missing_forward_candidate_rows", "count": 1})
    if pending_forward:
        warnings.append(
            {
                "code": "legitimate_forward_pending",
                "count": pending_forward,
                "invalidates_day": False,
            }
        )
    if not bool(decision.get("full_session_coverage")):
        target = blockers if is_complete else warnings
        target.append(
            {
                "code": "full_session_coverage_not_confirmed",
                "count": 1,
                "invalidates_day": bool(is_complete),
            }
        )

    if is_future:
        status = "PREOPEN"
    elif not is_complete:
        status = "IN_PROGRESS"
    else:
        status = "VALID" if not blockers else "INVALID"

    return {
        "schema_version": "q9_day_validity.v1",
        "behavior_effect": "evaluation_only",
        "day": day,
        "status": status,
        "counts_as_formal_day": status == "VALID",
        "trade_required": False,
        "checks": {
            "artifact_exists": bool(decision.get("exists")),
            "schema_match": bool(decision.get("schema_match", True)),
            "complete_pabc_window_count": complete_count,
            "scanner_selection_window_count": window_count,
            "pabc_linkage_ratio": round(linkage_ratio, 4),
            "full_session_coverage": bool(decision.get("full_session_coverage")),
            "first_window_kst": decision.get("first_scanner_window_kst"),
            "last_window_kst": decision.get("last_scanner_window_kst"),
            "last_runtime_evidence_kst": decision.get("last_q9_runtime_evidence_kst"),
            "session_coverage_source": decision.get("session_coverage_source"),
            "synthetic_window_count": synthetic_count,
            "missing_selected_candidate_count": missing_selected,
            "forward_candidate_count": forward_total,
            "forward_observed_candidate_count": observed_forward,
            "forward_pending_candidate_count": pending_forward,
            "forward_invalid_candidate_count": invalid_forward,
            "forward_usable_coverage": round(forward_coverage, 4),
        },
        "blockers": blockers,
        "warnings": warnings,
        "rule": (
            "A no-trade day remains eligible when the runtime covered the regular "
            "session and Q9 P/A/B/C plus forward evidence are trustworthy."
        ),
    }


__all__ = ["build_q9_day_validity"]
