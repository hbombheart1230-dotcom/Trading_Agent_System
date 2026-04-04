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
from libs.reporting.symbol_trade_report import build_daily_trade_index
from libs.reporting.symbol_trade_report import collect_symbols_for_day
from libs.reporting.symbol_trade_report import generate_symbol_trade_report
from libs.reporting.policy_surface_summary import (
    build_policy_surface_quality_executive_summary,
    build_policy_surface_quality_summary,
)
from libs.reporting.chart_structure_decision_hint_summary import (
    build_chart_structure_decision_hint_executive_summary,
    build_chart_structure_decision_hint_summary,
)
from scripts.check_phase_5_2_5_3_runtime_health import build_phase_5_2_5_3_runtime_health


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


def _load_operator_summary_snapshot(out_dir: Path, day: str) -> Dict[str, Any]:
    paths = daily_artifact_paths(out_dir, day)
    operator_summary = _read_json(paths["operator_summary_json"])
    if not operator_summary:
        return {}
    executive = operator_summary.get("executive_summary") if isinstance(operator_summary.get("executive_summary"), dict) else {}
    system_health = (
        operator_summary.get("system_health_status")
        if isinstance(operator_summary.get("system_health_status"), dict)
        else {}
    )
    trading_activity = (
        operator_summary.get("trading_activity_summary")
        if isinstance(operator_summary.get("trading_activity_summary"), dict)
        else {}
    )
    top_issues = operator_summary.get("top_issues") if isinstance(operator_summary.get("top_issues"), list) else []
    recommended_actions = (
        operator_summary.get("recommended_operator_actions")
        if isinstance(operator_summary.get("recommended_operator_actions"), list)
        else []
    )
    return {
        "available": True,
        "report_json_path": str(paths["operator_summary_json"]),
        "report_md_path": str(paths["operator_summary_md"]),
        "executive_summary": {
            "system_status": str(executive.get("system_status") or ""),
            "summary_lines": [str(x or "") for x in list(executive.get("summary_lines") or []) if str(x or "").strip()][:5],
        },
        "system_health_status": {
            "system_health_level": str(system_health.get("system_health_level") or ""),
            "reasoning": [str(x or "") for x in list(system_health.get("reasoning") or []) if str(x or "").strip()][:5],
            "recommended_action": [str(x or "") for x in list(system_health.get("recommended_action") or []) if str(x or "").strip()][:3],
        },
        "trading_activity_summary": {
            "run_total": trading_activity.get("run_total"),
            "decision_action_counts": dict(trading_activity.get("decision_action_counts") or {}),
            "strategy_counts": dict(trading_activity.get("strategy_counts") or {}),
            "executions_total": trading_activity.get("executions_total"),
            "executions_ok_total": trading_activity.get("executions_ok_total"),
            "executions_fail_total": trading_activity.get("executions_fail_total"),
            "blocked_total": trading_activity.get("blocked_total"),
        },
        "top_issues": [
            {
                "code": str((issue or {}).get("code") or ""),
                "severity": str((issue or {}).get("severity") or ""),
                "detail": str((issue or {}).get("detail") or ""),
            }
            for issue in top_issues[:5]
            if isinstance(issue, dict)
        ],
        "recommended_operator_actions": [str(x or "") for x in recommended_actions[:5] if str(x or "").strip()],
    }


def _load_policy_surface_quality_snapshot(events_path: Path, out_dir: Path, day: str) -> Dict[str, Any]:
    try:
        runtime_health = build_phase_5_2_5_3_runtime_health(
            reports_root=out_dir,
            event_log_path=events_path,
            day=day,
            limit=500,
        )
    except FileNotFoundError:
        summary = build_policy_surface_quality_summary([])
        chart_summary = build_chart_structure_decision_hint_summary([])
        return {
            "summary": summary,
            "executive_summary": build_policy_surface_quality_executive_summary(summary),
            "chart_structure_summary": chart_summary,
            "chart_structure_executive_summary": build_chart_structure_decision_hint_executive_summary(chart_summary),
            "source": {
                "run_count": 0,
                "date": day,
                "source": "daily_monitor_artifacts",
                "notes": ["no_canonical_monitor_runs_found"],
            },
        }
    except Exception:
        summary = build_policy_surface_quality_summary([])
        chart_summary = build_chart_structure_decision_hint_summary([])
        return {
            "summary": summary,
            "executive_summary": build_policy_surface_quality_executive_summary(summary),
            "chart_structure_summary": chart_summary,
            "chart_structure_executive_summary": build_chart_structure_decision_hint_executive_summary(chart_summary),
            "source": {
                "run_count": 0,
                "date": day,
                "source": "daily_monitor_artifacts",
                "notes": ["policy_surface_quality_summary_unavailable"],
            },
        }

    summary = runtime_health.get("policy_surface_quality_summary")
    if not isinstance(summary, dict):
        summary = build_policy_surface_quality_summary([])
    chart_summary = runtime_health.get("chart_structure_decision_hint_summary")
    if not isinstance(chart_summary, dict):
        chart_summary = build_chart_structure_decision_hint_summary([])
    return {
        "summary": dict(summary),
        "executive_summary": build_policy_surface_quality_executive_summary(summary),
        "chart_structure_summary": dict(chart_summary),
        "chart_structure_executive_summary": build_chart_structure_decision_hint_executive_summary(chart_summary),
        "source": {
            "run_count": int(runtime_health.get("run_count") or 0),
            "date": day,
            "source": "daily_monitor_artifacts",
            "health_schema_version": str(runtime_health.get("schema_version") or ""),
        },
    }


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
        operator_summary_snapshot = _load_operator_summary_snapshot(out_dir, day)
        policy_surface_quality = _load_policy_surface_quality_snapshot(events_path, out_dir, day)
        payload = {
            "day": day,
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
        }
        md_lines = [
            f"# Daily Report ({day})",
            "",
            "No events found.",
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
    operator_summary_snapshot = _load_operator_summary_snapshot(out_dir, day)
    policy_surface_quality = _load_policy_surface_quality_snapshot(events_path, out_dir, day)
    summary["trade_index"] = trade_index
    summary["symbols_observed"] = symbols_for_day
    summary["generated_symbol_report_count"] = len(generated_symbol_reports)
    summary["operator_summary_snapshot"] = operator_summary_snapshot
    summary["policy_surface_quality_summary"] = dict(policy_surface_quality.get("summary") or {})
    summary["policy_surface_quality_executive_summary"] = dict(policy_surface_quality.get("executive_summary") or {})
    summary["chart_structure_decision_hint_summary"] = dict(policy_surface_quality.get("chart_structure_summary") or {})
    summary["chart_structure_decision_hint_executive_summary"] = dict(policy_surface_quality.get("chart_structure_executive_summary") or {})
    summary["policy_surface_quality_source"] = dict(policy_surface_quality.get("source") or {})
    summary["chart_structure_decision_hint_source"] = dict(policy_surface_quality.get("source") or {})

    md_lines = [
        f"# Daily Report ({day})",
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
