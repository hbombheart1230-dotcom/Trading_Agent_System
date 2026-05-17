from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List


def day_key(ts: Any) -> str:
    """Return YYYY-MM-DD in UTC for deterministic reporting."""
    if ts is None:
        return date.today().isoformat()

    s = str(ts).strip()
    if not s:
        return date.today().isoformat()

    try:
        epoch = int(float(s))
        return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return date.today().isoformat()


def build_event_rows(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for event in events:
        ts = event.get("ts") or event.get("payload", {}).get("ts")
        rows.append({**event, "_day": day_key(ts)})
    return rows


def build_basic_daily_event_summary(day: str, day_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    stage_counter = Counter(row.get("stage") for row in day_rows)
    event_counter = Counter((row.get("stage"), row.get("event")) for row in day_rows)

    verdicts = []
    for row in day_rows:
        if row.get("stage") == "execute_from_packet" and row.get("event") in ("verdict", "end", "result"):
            payload = row.get("payload") or {}
            allowed = payload.get("allowed")
            if isinstance(allowed, bool):
                verdicts.append(allowed)
    approvals = sum(1 for value in verdicts if value)
    blocks = sum(1 for value in verdicts if value is False)

    actions = Counter()
    for row in day_rows:
        if row.get("stage") == "decision" and row.get("event") == "trace":
            payload = row.get("payload") or {}
            packet = payload.get("decision_packet") or {}
            intent = packet.get("intent") or {}
            action = intent.get("action") or intent.get("intent") or "UNKNOWN"
            actions[str(action).upper()] += 1

    return {
        "summary": {
            "day": day,
            "events": len(day_rows),
            "stage_counts": dict(stage_counter),
            "event_counts": {f"{key[0]}::{key[1]}": value for key, value in event_counter.items()},
            "decision_actions": dict(actions),
            "approvals": approvals,
            "blocks": blocks,
        },
        "stage_counter": stage_counter,
        "event_counter": event_counter,
        "actions": actions,
        "approvals": approvals,
        "blocks": blocks,
    }


def build_no_event_daily_payload(
    *,
    day: str,
    report_freshness: Dict[str, Any],
    data_freshness: Dict[str, Any],
    trade_index: List[Dict[str, Any]],
    symbols_for_day: List[str],
    generated_symbol_reports: List[Dict[str, Any]],
    symbol_report_refresh: Dict[str, Any],
    operator_summary_snapshot: Dict[str, Any],
    residual_positions: Dict[str, Any],
    policy_surface_quality: Dict[str, Any],
    route_provenance: Dict[str, Any],
    narrative_axis_policy: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "day": day,
        "generated_at": report_freshness["generated_at"],
        "source_run_count": report_freshness["source_run_count"],
        "latest_run_id": report_freshness["latest_run_id"],
        "latest_run_ts": report_freshness["latest_run_ts"],
        "report_freshness": report_freshness,
        "data_freshness": data_freshness,
        "operator_summary_snapshot_freshness": {},
        "events": 0,
        "trade_index": trade_index,
        "symbols_observed": symbols_for_day,
        "generated_symbol_report_count": len(generated_symbol_reports),
        "symbol_report_refresh": {key: value for key, value in symbol_report_refresh.items() if key != "generated"},
        "operator_summary_snapshot": operator_summary_snapshot,
        "residual_positions": residual_positions,
        "policy_surface_quality_summary": dict(policy_surface_quality.get("summary") or {}),
        "policy_surface_quality_executive_summary": dict(policy_surface_quality.get("executive_summary") or {}),
        "chart_structure_decision_hint_summary": dict(policy_surface_quality.get("chart_structure_summary") or {}),
        "chart_structure_decision_hint_executive_summary": dict(
            policy_surface_quality.get("chart_structure_executive_summary") or {}
        ),
        "policy_surface_quality_source": dict(policy_surface_quality.get("source") or {}),
        "chart_structure_decision_hint_source": dict(policy_surface_quality.get("source") or {}),
        "route_summary": dict(operator_summary_snapshot.get("route_summary") or {}),
        "route_provenance": route_provenance,
        "narrative_axis_policy": narrative_axis_policy,
    }


def enrich_daily_summary_payload(
    *,
    summary: Dict[str, Any],
    report_freshness: Dict[str, Any],
    data_freshness: Dict[str, Any],
    trade_index: List[Dict[str, Any]],
    symbols_for_day: List[str],
    generated_symbol_reports: List[Dict[str, Any]],
    symbol_report_refresh: Dict[str, Any],
    operator_summary_snapshot: Dict[str, Any],
    residual_positions: Dict[str, Any],
    operator_summary_snapshot_freshness: Dict[str, Any],
    policy_surface_quality: Dict[str, Any],
    route_provenance: Dict[str, Any],
    narrative_axis_policy: Dict[str, Any],
) -> Dict[str, Any]:
    enriched = dict(summary)
    enriched["generated_at"] = report_freshness["generated_at"]
    enriched["source_run_count"] = report_freshness["source_run_count"]
    enriched["latest_run_id"] = report_freshness["latest_run_id"]
    enriched["latest_run_ts"] = report_freshness["latest_run_ts"]
    enriched["report_freshness"] = report_freshness
    enriched["data_freshness"] = data_freshness
    enriched["trade_index"] = trade_index
    enriched["symbols_observed"] = symbols_for_day
    enriched["generated_symbol_report_count"] = len(generated_symbol_reports)
    enriched["symbol_report_refresh"] = {key: value for key, value in symbol_report_refresh.items() if key != "generated"}
    enriched["operator_summary_snapshot"] = operator_summary_snapshot
    enriched["residual_positions"] = residual_positions
    enriched["operator_summary_snapshot_freshness"] = operator_summary_snapshot_freshness
    enriched["route_summary"] = dict(operator_summary_snapshot.get("route_summary") or {})
    enriched["route_provenance"] = route_provenance
    enriched["policy_surface_quality_summary"] = dict(policy_surface_quality.get("summary") or {})
    enriched["policy_surface_quality_executive_summary"] = dict(policy_surface_quality.get("executive_summary") or {})
    enriched["chart_structure_decision_hint_summary"] = dict(policy_surface_quality.get("chart_structure_summary") or {})
    enriched["chart_structure_decision_hint_executive_summary"] = dict(
        policy_surface_quality.get("chart_structure_executive_summary") or {}
    )
    enriched["policy_surface_quality_source"] = dict(policy_surface_quality.get("source") or {})
    enriched["chart_structure_decision_hint_source"] = dict(policy_surface_quality.get("source") or {})
    enriched["narrative_axis_policy"] = narrative_axis_policy
    return enriched
