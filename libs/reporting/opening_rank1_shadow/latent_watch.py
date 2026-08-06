from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


KST = timezone(timedelta(hours=9))
WATCH_DAYS = 5


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


def _decision_time(epoch: int) -> str:
    if epoch <= 0:
        return ""
    return datetime.fromtimestamp(epoch, tz=KST).isoformat(timespec="seconds")


def _candidate_signal_evidence(candidate: Mapping[str, Any]) -> dict[str, Any]:
    breakdown = candidate.get("score_breakdown")
    breakdown = breakdown if isinstance(breakdown, Mapping) else {}
    compact = candidate.get("compact_feature_snapshot")
    compact = compact if isinstance(compact, Mapping) else {}
    above_vwap = candidate.get("above_vwap", compact.get("above_vwap"))
    volume_confirmation = float(breakdown.get("volume_surge") or 0.0) > 0.0
    vwap_confirmation = (
        above_vwap is True
        or float(breakdown.get("vwap_alignment") or 0.0) > 0.0
    )
    breakout_confirmation = (
        float(breakdown.get("momentum") or 0.0) > 0.0
        and float(breakdown.get("intraday_strength") or 0.0) > 0.0
    )
    evidence_count = sum(
        (volume_confirmation, vwap_confirmation, breakout_confirmation)
    )
    return {
        "volume_confirmation": volume_confirmation,
        "vwap_confirmation": vwap_confirmation,
        "breakout_confirmation": breakout_confirmation,
        "evidence_count": evidence_count,
        "status": (
            "SIGNAL_EVIDENCE_OBSERVED"
            if evidence_count
            else "REDETECTED_WITHOUT_SIGNAL_EVIDENCE"
        ),
    }


def _trading_days(reports_root: Path, through_day: str) -> list[str]:
    root = reports_root / "operator_summary" / "daily"
    if not root.exists():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir()
        and len(path.name) == 10
        and path.name <= through_day
        and (
            path / "q9_decision_windows.json"
        ).exists()
    )


def _candidate_reappearances(
    *,
    reports_root: Path,
    symbol: str,
    days: list[str],
) -> list[dict[str, Any]]:
    rows = []
    for day in days:
        path = (
            reports_root
            / "operator_summary"
            / "daily"
            / day
            / "q9_decision_windows.json"
        )
        payload = _read_json(path)
        for window in payload.get("windows") or []:
            if not isinstance(window, Mapping) or window.get("window_type") != "scanner_selection":
                continue
            universe = window.get("scanner_pre_strategist_universe")
            universe = universe if isinstance(universe, Mapping) else {}
            candidate = next(
                (
                    row
                    for row in universe.get("intrinsic_ranked_top20") or []
                    if isinstance(row, Mapping)
                    and str(row.get("symbol") or "") == symbol
                ),
                None,
            )
            if candidate is None:
                continue
            epoch = int(window.get("decision_epoch") or 0)
            rows.append(
                {
                    "day": day,
                    "decision_id": str(window.get("decision_id") or ""),
                    "decision_epoch": epoch,
                    "decision_time_kst": _decision_time(epoch),
                    "rank": int(candidate.get("rank") or 0),
                    "score_total": candidate.get("score_total"),
                    "confidence": candidate.get("confidence"),
                    "risk_score": candidate.get("risk_score"),
                    "signal_evidence": _candidate_signal_evidence(candidate),
                }
            )
    compact = []
    for day in days:
        day_rows = sorted(
            (row for row in rows if row.get("day") == day),
            key=lambda row: int(row.get("decision_epoch") or 0),
        )
        if not day_rows:
            continue
        first_signal = next(
            (
                row
                for row in day_rows
                if int((row.get("signal_evidence") or {}).get("evidence_count") or 0)
                > 0
            ),
            None,
        )
        best_rank = min(
            (int(row.get("rank") or 999) for row in day_rows),
            default=999,
        )
        compact.append(
            {
                **day_rows[0],
                "observation_count": len(day_rows),
                "best_rank": best_rank if best_rank < 999 else None,
                "first_signal_evidence": first_signal,
            }
        )
    return compact


def _initial_episodes(output_root: Path) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(output_root.glob("20??-??-??/opening_rank1_shadow_daily.json")):
        payload = _read_json(path)
        if payload.get("day_status") != "VALID":
            continue
        for episode in payload.get("episodes") or []:
            if not isinstance(episode, Mapping):
                continue
            checkpoint = (episode.get("checkpoints") or {}).get("+30m") or {}
            if checkpoint.get("status") != "observed":
                continue
            if float(checkpoint.get("live_net_return_pct") or 0.0) <= 0.0:
                key = (
                    str(episode.get("day") or ""),
                    str(episode.get("symbol") or ""),
                )
                selected.setdefault(key, dict(episode))
    return [selected[key] for key in sorted(selected)]


def _render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Latent Reactivation Watch",
        "",
        "- Behavior effect: observation only",
        f"- Through day: `{payload.get('through_day')}`",
        f"- Initial failed Rank-1 episodes: {int(summary.get('watch_count') or 0)}",
        f"- Redetected: {int(summary.get('redetected_count') or 0)}",
        f"- Signal evidence observed: {int(summary.get('signal_evidence_count') or 0)}",
        "",
        "| Initial day | Symbol | Initial +30m | Watch status | Days observed | Redetections | First evidence |",
        "| --- | --- | ---: | --- | ---: | ---: | --- |",
    ]
    for row in payload.get("rows") or []:
        redetections = row.get("redetections") or []
        first = next(
            (
                value.get("first_signal_evidence") or value
                for value in redetections
                if value.get("first_signal_evidence")
            ),
            None,
        )
        lines.append(
            f"| {row.get('initial_day')} | {row.get('symbol')} | "
            f"{float(row.get('initial_30m_net_pct') or 0.0):+.4f}% | "
            f"{row.get('watch_status')} | {int(row.get('observed_watch_day_count') or 0)} | "
            f"{len(redetections)} | {(first or {}).get('decision_time_kst') or '-'} |"
        )
    lines.extend(
        [
            "",
            "A later reappearance is a new observation. It never carries the original position forward or changes live candidate selection.",
            "",
        ]
    )
    return "\n".join(lines)


def build_latent_reactivation_watch(
    *,
    reports_root: Path,
    opening_output_root: Path,
    through_day: str,
) -> dict[str, Any]:
    calendar = _trading_days(reports_root, through_day)
    rows = []
    for episode in _initial_episodes(opening_output_root):
        initial_day = str(episode.get("day") or "")
        future_days = [day for day in calendar if day > initial_day][:WATCH_DAYS]
        redetections = _candidate_reappearances(
            reports_root=reports_root,
            symbol=str(episode.get("symbol") or ""),
            days=future_days,
        )
        signal_evidence_count = sum(
            row.get("first_signal_evidence") is not None
            for row in redetections
        )
        if signal_evidence_count:
            status = "REDETECTED_WITH_SIGNAL_EVIDENCE"
        elif redetections:
            status = "REDETECTED_WITHOUT_SIGNAL_EVIDENCE"
        elif len(future_days) >= WATCH_DAYS:
            status = "NOT_REDETECTED_D5"
        else:
            status = "WATCHING"
        checkpoint = (episode.get("checkpoints") or {}).get("+30m") or {}
        rows.append(
            {
                "watch_id": f"LATENT:{episode.get('episode_id')}",
                "initial_episode_id": episode.get("episode_id"),
                "initial_day": initial_day,
                "symbol": episode.get("symbol"),
                "initial_30m_net_pct": checkpoint.get("live_net_return_pct"),
                "observed_watch_days": future_days,
                "observed_watch_day_count": len(future_days),
                "watch_status": status,
                "redetections": redetections,
                "policy_effect": "NONE_OBSERVER_ONLY",
            }
        )
    payload = {
        "schema_version": "latent_reactivation_watch.v1",
        "behavior_effect": "observation_only",
        "through_day": through_day,
        "watch_horizon_trading_days": WATCH_DAYS,
        "summary": {
            "watch_count": len(rows),
            "redetected_count": sum(bool(row.get("redetections")) for row in rows),
            "signal_evidence_count": sum(
                row.get("watch_status") == "REDETECTED_WITH_SIGNAL_EVIDENCE"
                for row in rows
            ),
            "status_counts": {
                status: sum(row.get("watch_status") == status for row in rows)
                for status in sorted({str(row.get("watch_status")) for row in rows})
            },
        },
        "rows": rows,
    }
    latent_root = opening_output_root / "latent_watch"
    json_path = latent_root / "latent_reactivation_watch.json"
    markdown_path = latent_root / "latent_reactivation_watch.md"
    _write_json(json_path, payload)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "summary": payload["summary"],
    }
