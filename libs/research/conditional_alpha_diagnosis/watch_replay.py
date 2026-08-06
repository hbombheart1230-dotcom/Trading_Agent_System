from __future__ import annotations

from typing import Any, Mapping


def build_reactivation_watch_replay(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for event in events:
        if not event.get("delayed_high_opportunity"):
            continue
        rows.append(
            {
                "episode_id": event.get("episode_id"),
                "decision_id": event.get("decision_id"),
                "initial_day": event.get("day"),
                "symbol": event.get("symbol"),
                "symbol_name": event.get("symbol_name"),
                "themes": event.get("themes") or [],
                "initial_30m_net_pct": event.get("net_return_30m_pct"),
                "initial_eod_net_pct": event.get("return_eod_pct"),
                "first_plus_3pct_day": event.get("first_plus_3pct_day"),
                "first_plus_5pct_day": event.get("first_plus_5pct_day"),
                "first_plus_10pct_day": event.get("first_plus_10pct_day"),
                "d5_max_high_net_pct": event.get("d5_max_high_net_pct"),
                "d5_close_net_pct": event.get("d5_close_net_pct"),
                "initial_point_in_time_context": {
                    "scanner_score": event.get("scanner_score"),
                    "confidence": event.get("confidence"),
                    "risk_score": event.get("risk_score"),
                    "rank1_prev5m_observations": event.get("rank1_prev5m_observations"),
                    "precompleted_return_1m_pct": event.get("precompleted_return_1m_pct"),
                    "opening_relative_volume": event.get("opening_relative_volume"),
                    "above_vwap": event.get("above_vwap"),
                    "playbook": event.get("playbook"),
                    "scenario": event.get("strategist_scenario"),
                },
                "evidence_class": "HISTORICAL_REPLAY_WITH_FUTURE_LABEL",
                "policy_effect": "NONE_OBSERVER_ONLY",
            }
        )
    return {
        "schema_version": "reactivation_watch_replay.v1",
        "behavior_effect": "NONE_OFFLINE_RESEARCH_ONLY",
        "candidate_count": len(rows),
        "rows": rows,
        "warning": "Future labels are evaluation targets and cannot be used as live inputs.",
    }
