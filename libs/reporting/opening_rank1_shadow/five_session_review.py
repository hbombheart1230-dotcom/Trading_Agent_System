from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


WINDOW_START = "2026-08-03"
WINDOW_END = "2026-08-07"
REQUIRED_SESSIONS = 5
MINIMUM_NEW_EPISODES = 5
LANE_HORIZONS = {
    "IMMEDIATE_OPENING_PROBE": "+15m",
    "CONFIRMED_RECURRENT_RANK": "+30m",
    "DISLOCATION_REBOUND": "+60m",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _session_statuses(output_root: Path, through_day: str) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(output_root.glob("20??-??-??/opening_rank1_shadow_daily.json")):
        day = path.parent.name
        if not WINDOW_START <= day <= min(through_day, WINDOW_END):
            continue
        payload = _read_json(path)
        rows.append(
            {
                "day": day,
                "status": str(payload.get("day_status") or "MISSING"),
                "episode_count": int((payload.get("summary") or {}).get("episode_count") or 0),
            }
        )
    return rows


def evaluate_five_session_review(
    *,
    through_day: str,
    cumulative_summary: Mapping[str, Any],
    session_rows: list[Mapping[str, Any]],
    latent_summary: Mapping[str, Any],
) -> dict[str, Any]:
    window_closed = through_day >= WINDOW_END
    invalid_days = [
        str(row.get("day") or "")
        for row in session_rows
        if row.get("status") != "VALID"
    ]
    lane_results = {}
    for lane_name, horizon in LANE_HORIZONS.items():
        lane = (cumulative_summary.get("conditional_lane_summaries") or {}).get(lane_name) or {}
        metrics = ((lane.get("horizons") or {}).get(horizon) or {}).get("live_net") or {}
        count = int(lane.get("eligible_episode_count") or 0)
        average = float(metrics.get("average_return_pct") or 0.0)
        if not window_closed:
            outcome = "COLLECTING"
        elif count < MINIMUM_NEW_EPISODES:
            outcome = "RETAIN_LANE_SHADOW_ONLY"
        elif average > 0.0:
            outcome = "HISTORICAL_DIRECTION_CONFIRMED_SHADOW_ONLY"
        else:
            outcome = "REJECT_CANDIDATE"
        lane_results[lane_name] = {
            "primary_horizon": horizon,
            "eligible_episode_count": count,
            "minimum_episode_count": MINIMUM_NEW_EPISODES,
            "average_net_return_pct": average if int(metrics.get("count") or 0) else None,
            "outcome": outcome,
        }
    recurrent = lane_results["CONFIRMED_RECURRENT_RANK"]
    if not window_closed:
        selected = "NONE"
        status = "COLLECTING"
    elif recurrent["outcome"] == "HISTORICAL_DIRECTION_CONFIRMED_SHADOW_ONLY":
        selected = "CONFIRMED_RECURRENT_RANK_PRESERVATION"
        status = "SELECT_BEHAVIOR_CANDIDATE"
    else:
        selected = "NONE"
        status = "CLOSED_NO_BEHAVIOR_CANDIDATE"
    return {
        "schema_version": "opening_alpha_five_session_review.v1",
        "behavior_effect": "observation_only",
        "window": {
            "start_day": WINDOW_START,
            "end_day": WINDOW_END,
            "required_sessions": REQUIRED_SESSIONS,
            "observed_session_count": len(session_rows),
            "window_closed": window_closed,
            "no_extension": True,
        },
        "status": status,
        "selected_behavior_candidate": selected,
        "behavior_candidate_scope": "CONFIRMED_RECURRENT_RANK_ONLY",
        "selection_policy": (
            "A positive historical lane remains shadow-only. Only the predeclared "
            "CONFIRMED_RECURRENT_RANK lane may become the single behavior candidate."
        ),
        "invalid_artifact_days": invalid_days,
        "lane_results": lane_results,
        "latent_watch": {
            "watch_count": int(latent_summary.get("watch_count") or 0),
            "signal_evidence_count": int(latent_summary.get("signal_evidence_count") or 0),
            "outcome": "RETAIN_SHADOW_ONLY",
            "reason": "fresh-trigger forward outcomes are not yet part of the live watch contract",
        },
        "behavior_change_authorized": False,
    }


def _render_markdown(payload: Mapping[str, Any]) -> str:
    window = payload.get("window") or {}
    lines = [
        "# Opening Alpha Five-Session Review",
        "",
        f"- Window: `{window.get('start_day')}` through `{window.get('end_day')}`",
        f"- Status: **{payload.get('status')}**",
        f"- Selected behavior candidate: `{payload.get('selected_behavior_candidate')}`",
        f"- Behavior candidate scope: `{payload.get('behavior_candidate_scope')}`",
        f"- Invalid artifact days: `{payload.get('invalid_artifact_days') or []}`",
        "- Behavior change authorized by this report: **false**",
        "",
        "| Lane | Horizon | Eligible | Average net | Outcome |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for lane_name, row in (payload.get("lane_results") or {}).items():
        average = row.get("average_net_return_pct")
        average_text = "-" if average is None else f"{float(average):+.4f}%"
        lines.append(
            f"| {lane_name} | {row.get('primary_horizon')} | "
            f"{int(row.get('eligible_episode_count') or 0)} | {average_text} | "
            f"{row.get('outcome')} |"
        )
    lines.extend(
        [
            "",
            "Historical direction confirmation is shadow evidence, not promotion authority.",
            "",
            "This review closes on the fixed end date and cannot extend the whole analysis or change trading behavior.",
            "",
        ]
    )
    return "\n".join(lines)


def build_five_session_review(
    *,
    opening_output_root: Path,
    through_day: str,
    cumulative_summary: Mapping[str, Any],
    latent_summary: Mapping[str, Any],
) -> dict[str, str]:
    payload = evaluate_five_session_review(
        through_day=through_day,
        cumulative_summary=cumulative_summary,
        session_rows=_session_statuses(opening_output_root, through_day),
        latent_summary=latent_summary,
    )
    review_root = opening_output_root / "five_session_review"
    json_path = review_root / "opening_alpha_five_session_review.json"
    markdown_path = review_root / "opening_alpha_five_session_review.md"
    _write_json(json_path, payload)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}
