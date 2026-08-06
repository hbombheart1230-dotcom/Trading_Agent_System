from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from libs.research.opening_rank1_deep_dive.loaders import load_all_q9_windows

from .io import read_json
from .metrics import number


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _candidate(window: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    control = _mapping(window.get("scanner_control"))
    universe = _mapping(window.get("scanner_pre_strategist_universe"))
    rows = (
        control.get("top20")
        or control.get("top10")
        or universe.get("intrinsic_ranked_top20")
        or []
    )
    return next(
        (
            dict(row)
            for row in rows
            if isinstance(row, Mapping) and str(row.get("symbol") or "") == symbol
        ),
        {},
    )


def load_prospective_opening_rows(
    reports_root: Path,
    *,
    start_day: str,
    end_day: str,
) -> list[dict[str, Any]]:
    root = reports_root / "evaluation" / "opening_rank1_shadow"
    payloads = []
    for path in sorted(root.glob("*/opening_rank1_shadow_daily.json")):
        payload = read_json(path)
        day = str(payload.get("day") or path.parent.name)
        if start_day <= day <= end_day and payload.get("eligible_for_validation") is True:
            payloads.append(payload)
    days = {str(payload.get("day") or "") for payload in payloads}
    windows = load_all_q9_windows(reports_root, days) if days else {}
    rows = []
    for payload in payloads:
        for episode in payload.get("episodes") or []:
            if not isinstance(episode, Mapping) or episode.get("prospective_eligible") is not True:
                continue
            day = str(episode.get("day") or payload.get("day") or "")
            symbol = str(episode.get("symbol") or "")
            decision_id = str(episode.get("decision_id") or "")
            window = windows.get(decision_id, {})
            strategist = _mapping(window.get("strategist_selection"))
            commander = _mapping(window.get("commander_final"))
            candidate = _candidate(window, symbol)
            quant = _mapping(candidate.get("quant_factor_snapshot"))
            factors = _mapping(quant.get("factors"))
            observation = _mapping(episode.get("opening_observability"))
            checkpoints = _mapping(episode.get("checkpoints"))
            c30 = _mapping(checkpoints.get("+30m"))
            is_below = factors.get("is_below_vwap")
            rows.append(
                {
                    "decision_id": decision_id,
                    "day": day,
                    "symbol": symbol,
                    "decision_from_open_sec": observation.get("decision_from_open_sec"),
                    "playbook": strategist.get("playbook"),
                    "above_vwap": (not bool(is_below)) if is_below is not None else None,
                    "completed_bar_count_before_decision": observation.get(
                        "completed_bar_count_at_decision"
                    ),
                    "precompleted_return_1m_pct": None,
                    "opening_relative_volume": None,
                    "entry_vs_prior_close_pct": None,
                    "intrinsic_30m_net_pct": number(c30.get("live_net_return_pct")),
                    "monitor_candidate_30m_net_pct": None,
                    "monitor_intent": commander.get("monitor_intent"),
                    "commander_decision": commander.get("decision"),
                    "prospective_source": True,
                    "prospective_eligible": True,
                    "forward_30m_status": c30.get("status"),
                    "source_schema": payload.get("schema_version"),
                }
            )
    return rows
