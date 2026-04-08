from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.llm_artifacts import daily_artifact_paths
from libs.reporting.narrative_axes import narrative_axis_policy
from libs.reporting.operator_visibility import (
    build_operator_daily_summary_payload,
    build_operator_summary_snapshot_from_payload,
)
from libs.reporting.report_source_helpers import build_policy_surface_quality_snapshot
from libs.reporting.symbol_trade_report import build_daily_trade_index
from libs.reporting.symbol_trade_report import collect_symbols_for_day
from libs.reporting.symbol_trade_report import generate_symbol_trade_report


def _iter_events(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    def gen():
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    return gen()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_epoch(ts: Any) -> int:
    if ts is None:
        return 0
    if isinstance(ts, (int, float)):
        return int(ts)
    s = str(ts).strip()
    if not s:
        return 0
    try:
        return int(float(s))
    except Exception:
        pass
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def _epoch_to_iso(epoch: Any) -> str:
    try:
        n = int(float(epoch))
    except Exception:
        return ""
    if n <= 0:
        return ""
    return datetime.fromtimestamp(n, tz=timezone.utc).isoformat(timespec="seconds")


def _build_report_freshness(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest_row: Dict[str, Any] | None = None
    latest_epoch = 0
    run_ids = {
        str(row.get("run_id") or "").strip()
        for row in rows
        if str(row.get("run_id") or "").strip()
    }
    for row in rows:
        ts = row.get("ts") or (row.get("payload") or {}).get("ts")
        epoch = _to_epoch(ts)
        if epoch >= latest_epoch:
            latest_epoch = epoch
            latest_row = row
    return {
        "generated_at": _utc_now_iso(),
        "source_run_count": int(len(run_ids)),
        "latest_run_id": str((latest_row or {}).get("run_id") or ""),
        "latest_run_ts": _epoch_to_iso(latest_epoch),
    }


def _load_operator_summary_snapshot(events_path: Path, out_dir: Path, day: str) -> Dict[str, Any]:
    paths = daily_artifact_paths(out_dir, day)
    payload = build_operator_daily_summary_payload(
        events_path,
        out_dir,
        day=day,
        metrics_report_dir=out_dir / "metrics",
        m30_post_golive_dir=out_dir / "milestones" / "m30_post_golive",
        m30_golive_dir=out_dir / "milestones" / "m30_golive",
        m31_slo_incident_dir=out_dir / "m31_slo_incident",
    )
    snapshot = build_operator_summary_snapshot_from_payload(payload)
    snapshot["report_json_path"] = str(paths["operator_summary_json"])
    snapshot["report_md_path"] = str(paths["operator_summary_md"])
    return snapshot


def _build_snapshot_freshness(
    *,
    snapshot: Dict[str, Any],
    source_freshness: Dict[str, Any],
) -> Dict[str, Any]:
    snapshot_run_count = 0
    if isinstance(snapshot.get("trading_activity_summary"), dict):
        try:
            snapshot_run_count = int(float((snapshot.get("trading_activity_summary") or {}).get("run_total") or 0))
        except Exception:
            snapshot_run_count = 0
    snapshot_latest_ts = str(snapshot.get("latest_run_ts") or "")
    source_latest_ts = str(source_freshness.get("latest_run_ts") or "")
    snapshot_stale = False
    notes: List[str] = []
    if snapshot and snapshot_run_count and int(source_freshness.get("source_run_count") or 0) > snapshot_run_count:
        snapshot_stale = True
        notes.append("operator_summary_run_count_behind_daily_source")
    if snapshot and snapshot_latest_ts and source_latest_ts and _to_epoch(source_latest_ts) > _to_epoch(snapshot_latest_ts):
        snapshot_stale = True
        notes.append("operator_summary_latest_run_behind_daily_source")
    return {
        "available": bool(snapshot.get("available")),
        "stale": bool(snapshot_stale),
        "notes": notes,
        "snapshot_run_total": int(snapshot_run_count),
        "snapshot_latest_run_id": str(snapshot.get("latest_run_id") or ""),
        "snapshot_latest_run_ts": snapshot_latest_ts,
        "source_run_count": int(source_freshness.get("source_run_count") or 0),
        "source_latest_run_id": str(source_freshness.get("latest_run_id") or ""),
        "source_latest_run_ts": source_latest_ts,
    }


def _load_policy_surface_quality_snapshot(events_path: Path, out_dir: Path, day: str) -> Dict[str, Any]:
    return build_policy_surface_quality_snapshot(events_path, out_dir, day)


def _day_key(ts: Any) -> str:
    """Return YYYY-MM-DD in **UTC** for determinism across machines/timezones."""
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

def generate_daily_report(events_path: Path, out_dir: Path, day: str | None = None) -> Tuple[Path, Path]:
    """Generate a daily markdown + json summary from events.jsonl.

    Notes:
      - Day bucketing uses UTC for deterministic tests and consistent reporting.
      - If `day` is provided, only events matching that UTC day are included.
    """
    out_dir = out_dir.parent if out_dir.name == "daily" else out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for e in _iter_events(events_path):
        ts = e.get("ts") or e.get("payload", {}).get("ts")
        rows.append({**e, "_day": _day_key(ts)})
    if not rows:
        day = day or date.today().isoformat()
        paths = daily_artifact_paths(out_dir, day)
        md_path = paths["daily_report_md"]
        js_path = paths["daily_report_json"]
        trade_index = build_daily_trade_index(out_dir, day)
        symbols_for_day = collect_symbols_for_day(events_path, out_dir, day)
        generated_symbol_reports = [
            generate_symbol_trade_report(events_path=events_path, reports_root=out_dir, symbol=symbol)
            for symbol in symbols_for_day
        ]
        operator_summary_snapshot = _load_operator_summary_snapshot(events_path, out_dir, day)
        report_freshness = {
            "generated_at": _utc_now_iso(),
            "source_run_count": 0,
            "latest_run_id": "",
            "latest_run_ts": "",
        }
        operator_snapshot_freshness = _build_snapshot_freshness(
            snapshot=operator_summary_snapshot,
            source_freshness=report_freshness,
        )
        policy_surface_quality = _load_policy_surface_quality_snapshot(events_path, out_dir, day)
        payload = {
            "day": day,
            "generated_at": report_freshness["generated_at"],
            "source_run_count": report_freshness["source_run_count"],
            "latest_run_id": report_freshness["latest_run_id"],
            "latest_run_ts": report_freshness["latest_run_ts"],
            "report_freshness": report_freshness,
            "operator_summary_snapshot_freshness": operator_snapshot_freshness,
            "events": 0,
            "trade_index": trade_index,
            "symbols_observed": symbols_for_day,
            "generated_symbol_report_count": len(generated_symbol_reports),
            "operator_summary_snapshot": operator_summary_snapshot,
            "policy_surface_quality_summary": dict(policy_surface_quality.get("summary") or {}),
            "policy_surface_quality_executive_summary": dict(policy_surface_quality.get("executive_summary") or {}),
            "chart_structure_decision_hint_summary": dict(policy_surface_quality.get("chart_structure_summary") or {}),
            "chart_structure_decision_hint_executive_summary": dict(policy_surface_quality.get("chart_structure_executive_summary") or {}),
            "policy_surface_quality_source": dict(policy_surface_quality.get("source") or {}),
            "chart_structure_decision_hint_source": dict(policy_surface_quality.get("source") or {}),
            "route_summary": dict(operator_summary_snapshot.get("route_summary") or {}),
            "narrative_axis_policy": narrative_axis_policy(),
        }
        md_lines = [
            f"# Daily Report ({day})",
            "",
            "No events found.",
        ]
        md_lines += [
            "",
            "## Report Freshness",
            "",
            f"- generated_at: `{report_freshness['generated_at']}`",
            f"- source_run_count: **{report_freshness['source_run_count']}**",
            f"- latest_run_id: `{report_freshness['latest_run_id'] or '-'}`",
            f"- latest_run_ts: `{report_freshness['latest_run_ts'] or '-'}`",
            f"- operator_summary_snapshot_stale: **{operator_snapshot_freshness['stale']}**",
        ]
        executive = (
            operator_summary_snapshot.get("executive_summary")
            if isinstance(operator_summary_snapshot.get("executive_summary"), dict)
            else {}
        )
        if executive.get("summary_lines"):
            md_lines += ["", "## Operator Summary Snapshot", ""]
            for line in executive.get("summary_lines") or []:
                md_lines.append(f"- {line}")
        route_summary = payload.get("route_summary") if isinstance(payload.get("route_summary"), dict) else {}
        narrative_policy = payload.get("narrative_axis_policy") if isinstance(payload.get("narrative_axis_policy"), dict) else narrative_axis_policy()
        md_lines += [
            "",
            "## Route Summary",
            "",
            f"- route_source: `{route_summary.get('route_source') or '-'}`",
            f"- route_source_run_count: **{int(route_summary.get('route_source_run_count') or 0)}**",
            f"- route_source_missing_count: **{int(route_summary.get('route_source_missing_count') or 0)}**",
            f"- route_selected_total: `{json.dumps(route_summary.get('route_selected_total') or {}, ensure_ascii=False)}`",
            "",
            "## Narrative Axis Policy",
            "",
            f"- entry_primary_for: `{narrative_policy.get('entry_primary_for') or []}`",
            f"- exit_primary_for: `{narrative_policy.get('exit_primary_for') or []}`",
            f"- mixed_only_for_ambiguous_cases: **{bool(narrative_policy.get('mixed_only_for_ambiguous_cases'))}**",
            f"- runtime_semantics_unchanged: **{bool(narrative_policy.get('runtime_semantics_unchanged'))}**",
        ]
        policy_surface_summary = payload.get("policy_surface_quality_summary") if isinstance(payload.get("policy_surface_quality_summary"), dict) else {}
        policy_surface_exec = payload.get("policy_surface_quality_executive_summary") if isinstance(payload.get("policy_surface_quality_executive_summary"), dict) else {}
        chart_structure_summary = payload.get("chart_structure_decision_hint_summary") if isinstance(payload.get("chart_structure_decision_hint_summary"), dict) else {}
        chart_structure_exec = payload.get("chart_structure_decision_hint_executive_summary") if isinstance(payload.get("chart_structure_decision_hint_executive_summary"), dict) else {}
        policy_surface_source = payload.get("policy_surface_quality_source") if isinstance(payload.get("policy_surface_quality_source"), dict) else {}
        chart_structure_source = payload.get("chart_structure_decision_hint_source") if isinstance(payload.get("chart_structure_decision_hint_source"), dict) else {}
        chart_structure_examples = chart_structure_summary.get("applied_examples") if isinstance(chart_structure_summary.get("applied_examples"), list) else []
        md_lines += [
            "",
            "## Policy Surface Executive Summary",
            "",
            f"- status: **{str(policy_surface_exec.get('status') or 'unknown').upper()}**",
            f"- headline: {str(policy_surface_exec.get('headline') or 'Policy surface unknown')}",
            "",
            "## Policy Surface Quality",
            "",
            f"- schema_available_rate: **{float(policy_surface_summary.get('schema_available_rate') or 0.0):.4f}**",
            f"- normalized_policy_rate: **{float(policy_surface_summary.get('normalized_policy_rate') or 0.0):.4f}**",
            f"- invalid_spec_rate: **{float(policy_surface_summary.get('invalid_spec_rate') or 0.0):.4f}**",
            f"- total_invalid_specs: **{int(policy_surface_summary.get('total_invalid_specs') or 0)}**",
            f"- run_count: **{int(policy_surface_source.get('run_count') or 0)}**",
            "",
            "## Chart Structure Decision Hint Executive Summary",
            "",
            f"- status: **{str(chart_structure_exec.get('status') or 'unknown').upper()}**",
            f"- headline: {str(chart_structure_exec.get('headline') or 'Chart structure guard unknown')}",
            "",
            "## Chart Structure Decision Hint",
            "",
            f"- available_run_count: **{int(chart_structure_summary.get('available_run_count') or 0)}**",
            f"- applied_count: **{int(chart_structure_summary.get('applied_count') or 0)}**",
            f"- applied_rate: **{float(chart_structure_summary.get('applied_rate') or 0.0):.4f}**",
            f"- top_blocking_features: `{json.dumps(chart_structure_summary.get('top_blocking_features') or [], ensure_ascii=False)}`",
            f"- run_count: **{int(chart_structure_source.get('run_count') or 0)}**",
        ]
        if chart_structure_examples:
            md_lines += ["", "## Chart Structure Decision Hint Applied Examples", ""]
            for example in chart_structure_examples[:3]:
                if not isinstance(example, dict):
                    continue
                md_lines.append(
                    f"- `{example.get('run_id') or '-'}` "
                    f"[{str(example.get('entry_style') or '-').upper()}] "
                    f"{example.get('reason_transition') or '-'} "
                    f"blockers=`{json.dumps(example.get('blocking_features') or [], ensure_ascii=False)}`"
                )
        md_text = "\n".join(md_lines) + "\n"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_text, encoding="utf-8")
        js_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["trade_index_json"].write_text(json.dumps(trade_index, ensure_ascii=False, indent=2), encoding="utf-8")
        return md_path, js_path

    day = day or sorted({r["_day"] for r in rows})[-1]
    day_rows = [r for r in rows if r["_day"] == day]
    report_freshness = _build_report_freshness(day_rows)

    stage_counter = Counter(r.get("stage") for r in day_rows)
    event_counter = Counter((r.get("stage"), r.get("event")) for r in day_rows)

    verdicts = []
    for r in day_rows:
        if r.get("stage") == "execute_from_packet" and r.get("event") in ("verdict", "end", "result"):
            payload = r.get("payload") or {}
            v = payload.get("allowed")
            if isinstance(v, bool):
                verdicts.append(v)
    approvals = sum(1 for v in verdicts if v)
    blocks = sum(1 for v in verdicts if v is False)

    actions = Counter()
    for r in day_rows:
        if r.get("stage") == "decision" and r.get("event") == "trace":
            payload = r.get("payload") or {}
            pkt = payload.get("decision_packet") or {}
            intent = pkt.get("intent") or {}
            act = intent.get("action") or intent.get("intent") or "UNKNOWN"
            actions[str(act).upper()] += 1

    summary = {
        "day": day,
        "events": len(day_rows),
        "stage_counts": dict(stage_counter),
        "event_counts": {f"{k[0]}::{k[1]}": v for k, v in event_counter.items()},
        "decision_actions": dict(actions),
        "approvals": approvals,
        "blocks": blocks,
    }
    trade_index = build_daily_trade_index(out_dir, day)
    symbols_for_day = collect_symbols_for_day(events_path, out_dir, day)
    generated_symbol_reports = [
        generate_symbol_trade_report(events_path=events_path, reports_root=out_dir, symbol=symbol)
        for symbol in symbols_for_day
    ]
    operator_summary_snapshot = _load_operator_summary_snapshot(events_path, out_dir, day)
    operator_summary_snapshot_freshness = _build_snapshot_freshness(
        snapshot=operator_summary_snapshot,
        source_freshness=report_freshness,
    )
    policy_surface_quality = _load_policy_surface_quality_snapshot(events_path, out_dir, day)
    summary["generated_at"] = report_freshness["generated_at"]
    summary["source_run_count"] = report_freshness["source_run_count"]
    summary["latest_run_id"] = report_freshness["latest_run_id"]
    summary["latest_run_ts"] = report_freshness["latest_run_ts"]
    summary["report_freshness"] = report_freshness
    summary["trade_index"] = trade_index
    summary["symbols_observed"] = symbols_for_day
    summary["generated_symbol_report_count"] = len(generated_symbol_reports)
    summary["operator_summary_snapshot"] = operator_summary_snapshot
    summary["operator_summary_snapshot_freshness"] = operator_summary_snapshot_freshness
    summary["route_summary"] = dict(operator_summary_snapshot.get("route_summary") or {})
    summary["policy_surface_quality_summary"] = dict(policy_surface_quality.get("summary") or {})
    summary["policy_surface_quality_executive_summary"] = dict(policy_surface_quality.get("executive_summary") or {})
    summary["chart_structure_decision_hint_summary"] = dict(policy_surface_quality.get("chart_structure_summary") or {})
    summary["chart_structure_decision_hint_executive_summary"] = dict(policy_surface_quality.get("chart_structure_executive_summary") or {})
    summary["policy_surface_quality_source"] = dict(policy_surface_quality.get("source") or {})
    summary["chart_structure_decision_hint_source"] = dict(policy_surface_quality.get("source") or {})
    summary["narrative_axis_policy"] = narrative_axis_policy()

    md_lines = [
        f"# Daily Report ({day})",
        "",
        "## Report Freshness",
        "",
        f"- generated_at: `{report_freshness['generated_at']}`",
        f"- source_run_count: **{report_freshness['source_run_count']}**",
        f"- latest_run_id: `{report_freshness['latest_run_id'] or '-'}`",
        f"- latest_run_ts: `{report_freshness['latest_run_ts'] or '-'}`",
        f"- operator_summary_snapshot_stale: **{operator_summary_snapshot_freshness['stale']}**",
        "",
        f"- events: **{summary['events']}**",
        f"- approvals: **{approvals}** / blocks: **{blocks}**",
        f"- symbols observed: **{len(symbols_for_day)}**",
        "",
        "## Decision actions",
        "",
    ]
    if actions:
        for k, v in actions.most_common():
            md_lines.append(f"- {k}: {v}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "## Stage counts", ""]
    for k, v in stage_counter.most_common():
        md_lines.append(f"- {k}: {v}")

    executive = (
        operator_summary_snapshot.get("executive_summary")
        if isinstance(operator_summary_snapshot.get("executive_summary"), dict)
        else {}
    )
    if executive.get("summary_lines"):
        md_lines += ["", "## Operator Summary Snapshot", ""]
        if executive.get("system_status"):
            md_lines.append(f"- system_status: **{executive['system_status']}**")
        for line in executive.get("summary_lines") or []:
            md_lines.append(f"- {line}")
    route_summary = summary.get("route_summary") if isinstance(summary.get("route_summary"), dict) else {}
    narrative_policy = summary.get("narrative_axis_policy") if isinstance(summary.get("narrative_axis_policy"), dict) else narrative_axis_policy()
    md_lines += [
        "",
        "## Route Summary",
        "",
        f"- route_source: `{route_summary.get('route_source') or '-'}`",
        f"- route_source_run_count: **{int(route_summary.get('route_source_run_count') or 0)}**",
        f"- route_source_missing_count: **{int(route_summary.get('route_source_missing_count') or 0)}**",
        f"- route_selected_total: `{json.dumps(route_summary.get('route_selected_total') or {}, ensure_ascii=False)}`",
        "",
        "## Narrative Axis Policy",
        "",
        f"- entry_primary_for: `{narrative_policy.get('entry_primary_for') or []}`",
        f"- exit_primary_for: `{narrative_policy.get('exit_primary_for') or []}`",
        f"- mixed_only_for_ambiguous_cases: **{bool(narrative_policy.get('mixed_only_for_ambiguous_cases'))}**",
        f"- runtime_semantics_unchanged: **{bool(narrative_policy.get('runtime_semantics_unchanged'))}**",
    ]

    policy_surface_summary = summary.get("policy_surface_quality_summary") if isinstance(summary.get("policy_surface_quality_summary"), dict) else {}
    policy_surface_exec = summary.get("policy_surface_quality_executive_summary") if isinstance(summary.get("policy_surface_quality_executive_summary"), dict) else {}
    chart_structure_summary = summary.get("chart_structure_decision_hint_summary") if isinstance(summary.get("chart_structure_decision_hint_summary"), dict) else {}
    chart_structure_exec = summary.get("chart_structure_decision_hint_executive_summary") if isinstance(summary.get("chart_structure_decision_hint_executive_summary"), dict) else {}
    policy_surface_source = summary.get("policy_surface_quality_source") if isinstance(summary.get("policy_surface_quality_source"), dict) else {}
    chart_structure_source = summary.get("chart_structure_decision_hint_source") if isinstance(summary.get("chart_structure_decision_hint_source"), dict) else {}
    chart_structure_examples = chart_structure_summary.get("applied_examples") if isinstance(chart_structure_summary.get("applied_examples"), list) else []
    md_lines += [
        "",
        "## Policy Surface Executive Summary",
        "",
        f"- status: **{str(policy_surface_exec.get('status') or 'unknown').upper()}**",
        f"- headline: {str(policy_surface_exec.get('headline') or 'Policy surface unknown')}",
        "",
        "## Policy Surface Quality",
        "",
        f"- schema_available_rate: **{float(policy_surface_summary.get('schema_available_rate') or 0.0):.4f}**",
        f"- normalized_policy_rate: **{float(policy_surface_summary.get('normalized_policy_rate') or 0.0):.4f}**",
        f"- invalid_spec_rate: **{float(policy_surface_summary.get('invalid_spec_rate') or 0.0):.4f}**",
        f"- total_invalid_specs: **{int(policy_surface_summary.get('total_invalid_specs') or 0)}**",
        f"- run_count: **{int(policy_surface_source.get('run_count') or 0)}**",
        "",
        "## Chart Structure Decision Hint Executive Summary",
        "",
        f"- status: **{str(chart_structure_exec.get('status') or 'unknown').upper()}**",
        f"- headline: {str(chart_structure_exec.get('headline') or 'Chart structure guard unknown')}",
        "",
        "## Chart Structure Decision Hint",
        "",
        f"- available_run_count: **{int(chart_structure_summary.get('available_run_count') or 0)}**",
        f"- applied_count: **{int(chart_structure_summary.get('applied_count') or 0)}**",
        f"- applied_rate: **{float(chart_structure_summary.get('applied_rate') or 0.0):.4f}**",
        f"- top_blocking_features: `{json.dumps(chart_structure_summary.get('top_blocking_features') or [], ensure_ascii=False)}`",
        f"- run_count: **{int(chart_structure_source.get('run_count') or 0)}**",
    ]
    if chart_structure_examples:
        md_lines += ["", "## Chart Structure Decision Hint Applied Examples", ""]
        for example in chart_structure_examples[:3]:
            if not isinstance(example, dict):
                continue
            md_lines.append(
                f"- `{example.get('run_id') or '-'}` "
                f"[{str(example.get('entry_style') or '-').upper()}] "
                f"{example.get('reason_transition') or '-'} "
                f"blockers=`{json.dumps(example.get('blocking_features') or [], ensure_ascii=False)}`"
            )

    top_issues = operator_summary_snapshot.get("top_issues") if isinstance(operator_summary_snapshot.get("top_issues"), list) else []
    if top_issues:
        md_lines += ["", "## Top Issues", ""]
        for issue in top_issues:
            if not isinstance(issue, dict):
                continue
            md_lines.append(
                f"- [{issue.get('severity') or '-'}] {issue.get('code') or '-'}: {issue.get('detail') or '-'}"
            )

    recommended_actions = (
        operator_summary_snapshot.get("recommended_operator_actions")
        if isinstance(operator_summary_snapshot.get("recommended_operator_actions"), list)
        else []
    )
    if recommended_actions:
        md_lines += ["", "## Recommended Operator Actions", ""]
        for action in recommended_actions:
            md_lines.append(f"- {action}")

    paths = daily_artifact_paths(out_dir, day)
    md_path = paths["daily_report_md"]
    js_path = paths["daily_report_json"]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    js_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["trade_index_json"].write_text(json.dumps(trade_index, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, js_path

def main() -> None:
    events_path = Path(os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl"))
    out_dir = Path(os.getenv("REPORT_DIR", "./reports"))
    day = os.getenv("REPORT_DAY")  # optional YYYY-MM-DD (UTC)
    md, js = generate_daily_report(events_path, out_dir, day=day)
    print(f"Wrote: {md}")
    print(f"Wrote: {js}")

if __name__ == "__main__":
    main()
