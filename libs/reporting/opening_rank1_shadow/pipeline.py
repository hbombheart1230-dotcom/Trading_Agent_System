from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.baseline_samsung_hynix.data_provider import load_existing_candles

from .contracts import (
    BEHAVIOR_EFFECT,
    COHORT_ID,
    FIRST_ELIGIBLE_DAY,
    LIVE_COST_PCT,
    SCHEMA_VERSION,
)
from .extraction import extract_opening_rank1_windows
from .episodes import build_opening_rank1_episodes
from .metrics import evaluate_promotion, summarize_episodes
from .report import render_cumulative, render_daily


KST = timezone(timedelta(hours=9))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _time_kst(epoch: int) -> str:
    if epoch <= 0:
        return ""
    return datetime.fromtimestamp(epoch, tz=KST).isoformat(timespec="seconds")


def _load_daily_episodes(output_root: Path) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for path in sorted(output_root.glob("20??-??-??/opening_rank1_shadow_daily.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if (
            not isinstance(payload, Mapping)
            or not payload.get("eligible_for_validation")
            or payload.get("day_status") != "VALID"
        ):
            continue
        for raw in payload.get("episodes") or []:
            if not isinstance(raw, Mapping):
                continue
            episode_id = str(raw.get("episode_id") or "")
            if episode_id:
                deduped[episode_id] = dict(raw)
    return [deduped[key] for key in sorted(deduped)]


def _candles_complete_for_close(
    candles: Mapping[str, list[Mapping[str, Any]]],
    symbols: tuple[str, ...],
) -> bool:
    if not symbols:
        return True
    for symbol in symbols:
        rows = candles.get(symbol) or []
        if not rows:
            return False
        latest_epoch = int(rows[-1].get("ts") or 0)
        if latest_epoch <= 0:
            return False
        latest = datetime.fromtimestamp(latest_epoch, tz=KST)
        if latest.hour * 60 + latest.minute < 15 * 60 + 20:
            return False
    return True


def build_opening_rank1_shadow(
    *,
    day: str,
    reports_root: Path = Path("reports"),
    state_path: Path = Path("data/state.json"),
    allow_fresh_fetch: bool = True,
) -> dict[str, Any]:
    normalized_day = str(day or "").strip()[:10]
    extraction = extract_opening_rank1_windows(
        reports_root=reports_root,
        day=normalized_day,
    )
    windows = list(extraction.get("windows") or [])
    symbols = tuple(str(value) for value in extraction.get("symbols") or [])
    candles = load_existing_candles(
        state_path=state_path,
        day=normalized_day,
        symbols=symbols,
        allow_fresh_fetch=False,
        run_id_prefix="opening_rank1_shadow",
    )
    fresh_fetch_used = False
    if allow_fresh_fetch and not _candles_complete_for_close(candles, symbols):
        candles = load_existing_candles(
            state_path=state_path,
            day=normalized_day,
            symbols=symbols,
            allow_fresh_fetch=True,
            run_id_prefix="opening_rank1_shadow",
        )
        fresh_fetch_used = True
    episodes = build_opening_rank1_episodes(
        windows,
        minute_rows_by_symbol=candles,
    )
    for row in episodes:
        row["cohort_id"] = COHORT_ID
        row["decision_time_kst"] = _time_kst(int(row.get("decision_epoch") or 0))
        row["entry_time_kst"] = _time_kst(int(row.get("baseline_epoch") or 0))
        row["prospective_eligible"] = normalized_day >= FIRST_ELIGIBLE_DAY
    summary = summarize_episodes(episodes)
    eligible = normalized_day >= FIRST_ELIGIBLE_DAY
    if not eligible:
        day_status = "IMPLEMENTATION_DAY_EXCLUDED"
    elif not extraction.get("source_exists"):
        day_status = "Q9_ARTIFACT_MISSING"
    elif (
        int(extraction.get("missing_universe_count") or 0) > 0
        or int(extraction.get("missing_rank1_count") or 0) > 0
    ):
        day_status = "ARTIFACT_INCOMPLETE"
    elif not windows:
        day_status = "NO_OPENING_RANK1"
    elif not episodes:
        day_status = "MINUTE_HISTORY_MISSING"
    elif int(summary.get("observed_30m_count") or 0) < int(
        summary.get("episode_count") or 0
    ):
        day_status = "FORWARD_INCOMPLETE"
    else:
        day_status = "VALID"
    output_root = (
        Path(reports_root)
        / "evaluation"
        / "opening_rank1_shadow"
    )
    daily_payload = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": BEHAVIOR_EFFECT,
        "cohort_id": COHORT_ID,
        "day": normalized_day,
        "first_eligible_day": FIRST_ELIGIBLE_DAY,
        "eligible_for_validation": eligible,
        "day_status": day_status,
        "cost_model": {"live_round_trip_cost_pct": LIVE_COST_PCT},
        "extraction": {
            key: value
            for key, value in extraction.items()
            if key != "windows"
        },
        "provider": {
            "requested_symbol_count": len(symbols),
            "symbols_with_rows": sum(1 for value in candles.values() if value),
            "fresh_fetch_allowed": bool(allow_fresh_fetch),
            "fresh_fetch_used": fresh_fetch_used,
        },
        "summary": summary,
        "episodes": episodes,
    }
    daily_dir = output_root / normalized_day
    daily_json = daily_dir / "opening_rank1_shadow_daily.json"
    daily_md = daily_dir / "opening_rank1_shadow_daily.md"
    _write_json(daily_json, daily_payload)
    daily_md.write_text(render_daily(daily_payload), encoding="utf-8")

    cumulative_episodes = _load_daily_episodes(output_root)
    cumulative_summary = summarize_episodes(cumulative_episodes)
    promotion = evaluate_promotion(cumulative_summary)
    cumulative_payload = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": BEHAVIOR_EFFECT,
        "cohort_id": COHORT_ID,
        "first_eligible_day": FIRST_ELIGIBLE_DAY,
        "through_day": normalized_day,
        "cost_model": {"live_round_trip_cost_pct": LIVE_COST_PCT},
        "summary": cumulative_summary,
        "promotion_decision": promotion,
        "episodes": cumulative_episodes,
    }
    cumulative_json = output_root / "opening_rank1_shadow_cumulative.json"
    cumulative_md = output_root / "opening_rank1_shadow_cumulative.md"
    _write_json(cumulative_json, cumulative_payload)
    cumulative_md.write_text(render_cumulative(cumulative_payload), encoding="utf-8")
    return {
        "ok": True,
        "day_status": day_status,
        "episode_count": len(episodes),
        "observed_30m_count": int(summary.get("observed_30m_count") or 0),
        "promotion_status": promotion.get("status"),
        "daily_json_path": str(daily_json),
        "daily_md_path": str(daily_md),
        "cumulative_json_path": str(cumulative_json),
        "cumulative_md_path": str(cumulative_md),
    }
