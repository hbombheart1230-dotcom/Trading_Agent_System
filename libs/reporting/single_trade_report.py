from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from libs.reporting.llm_artifacts import (
    build_compact_input_artifact,
    persist_llm_artifact_refs,
    trade_artifact_paths,
    write_json,
)
from libs.reporting.trade_report_ai import (
    build_ai_trade_report,
    build_ai_trade_report_compact_input,
    render_trade_report_markdown,
)
from libs.reporting.trade_story_pipeline import (
    build_execution_outcome_human,
    build_filters_human,
    build_guard_reason_human,
    build_lifecycle_bundle,
    build_market_context_human,
    build_monitor_reason_human,
    build_operator_conclusion_human,
    build_reporter_status_human,
    build_scanner_reason_human,
    build_story_contract,
    build_timeline,
    build_trade_story_input,
)


def _root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", []):
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, "", []):
            return None
        return int(float(value))
    except Exception:
        return None


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _execution_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    return state.get("execution") if isinstance(state.get("execution"), dict) else {}


def _execution_order(state: Dict[str, Any]) -> Dict[str, Any]:
    execution = _execution_payload(state)
    return execution.get("order") if isinstance(execution.get("order"), dict) else {}


def _execution_action(state: Dict[str, Any]) -> str:
    execution = _execution_payload(state)
    order = _execution_order(state)
    return str(order.get("action") or execution.get("action") or "").strip().upper()


def _execution_symbol(state: Dict[str, Any]) -> str:
    execution = _execution_payload(state)
    order = _execution_order(state)
    return _normalize_symbol(order.get("symbol") or execution.get("symbol") or state.get("symbol") or "")


def _resolve_trade_day(state: Dict[str, Any], *, root: Path | None = None) -> str:
    raw_day = str(state.get("day") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_day):
        return raw_day
    execution = _execution_payload(state)
    ts_candidates = [
        execution.get("ts"),
        state.get("ts"),
        ((state.get("monitor_output") or {}) if isinstance(state.get("monitor_output"), dict) else {}).get("ts"),
        ((state.get("scanner_output") or {}) if isinstance(state.get("scanner_output"), dict) else {}).get("ts"),
    ]
    for candidate in ts_candidates:
        text = str(candidate or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return text
        match = re.match(r"^(\d{4}-\d{2}-\d{2})[T\s]", text)
        if match:
            return match.group(1)
    run_id = str(state.get("run_id") or "").strip()
    repo_root = Path(root) if root is not None else _root_dir()
    if run_id:
        canonical_root = repo_root / "reports" / "canonical"
        if canonical_root.exists():
            for day_dir in sorted(canonical_root.iterdir(), key=lambda path: path.name, reverse=True):
                if day_dir.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_dir.name):
                    if (day_dir / run_id).exists():
                        return day_dir.name
    return datetime.now().astimezone().date().isoformat()


def _execution_ok(state: Dict[str, Any]) -> bool:
    execution = _execution_payload(state)
    return bool(execution.get("ok")) and bool(execution.get("allowed", True))


def _trade_report_policy(state: Dict[str, Any]) -> Dict[str, Any]:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    reporter = applied_policy.get("reporter") if isinstance(applied_policy.get("reporter"), dict) else {}
    trade_report = reporter.get("trade_report") if isinstance(reporter.get("trade_report"), dict) else {}
    if trade_report:
        return dict(trade_report)
    commander = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    commander_policy = commander.get("applied_policy") if isinstance(commander.get("applied_policy"), dict) else {}
    commander_reporter = commander_policy.get("reporter") if isinstance(commander_policy.get("reporter"), dict) else {}
    commander_trade_report = (
        commander_reporter.get("trade_report")
        if isinstance(commander_reporter.get("trade_report"), dict)
        else {}
    )
    return dict(commander_trade_report or {})


def _null_execution_details() -> Dict[str, Any]:
    return {
        "order_status": None,
        "order_id": None,
        "execution_mode": None,
        "broker_env": None,
        "filled_qty": None,
        "avg_price": None,
    }


def _execution_details_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    execution = _execution_payload(state)
    order = _execution_order(state)
    payload = execution.get("payload") if isinstance(execution.get("payload"), dict) else {}
    response_payload = payload.get("response_payload") if isinstance(payload.get("response_payload"), dict) else {}
    order_status = (
        execution.get("reason")
        or execution.get("status")
        or payload.get("status")
        or response_payload.get("status")
        or response_payload.get("return_msg")
        or None
    )
    order_id = (
        payload.get("order_id")
        or response_payload.get("ord_no")
        or response_payload.get("order_id")
        or execution.get("order_id")
        or execution.get("ord_no")
        or None
    )
    execution_mode = (
        execution.get("execution_mode")
        or execution.get("effective_mode")
        or payload.get("mode")
        or None
    )
    broker_env = execution.get("broker_env") or payload.get("broker_env") or None
    filled_qty = (
        execution.get("filled_qty")
        or order.get("filled_qty")
        or payload.get("filled_qty")
        or response_payload.get("filled_qty")
        or order.get("qty")
        or execution.get("qty")
        or None
    )
    avg_price = (
        order.get("avg_fill_price")
        or order.get("avg_price")
        or payload.get("avg_fill_price")
        or payload.get("fill_price")
        or response_payload.get("avg_fill_price")
        or response_payload.get("fill_price")
        or None
    )
    return {
        "order_status": str(order_status).strip() if order_status not in (None, "") else None,
        "order_id": str(order_id).strip() if order_id not in (None, "") else None,
        "execution_mode": str(execution_mode).strip() if execution_mode not in (None, "") else None,
        "broker_env": str(broker_env).strip() if broker_env not in (None, "") else None,
        "filled_qty": _safe_int(filled_qty),
        "avg_price": _safe_float(avg_price),
    }


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _matching_trade_dirs(trade_day_root: Path, symbol: str) -> Iterable[Path]:
    compact_day = trade_day_root.name.replace("-", "")
    pattern = re.compile(rf"^TRD_{re.escape(compact_day)}_{re.escape(symbol)}_(\d+)$")
    if not trade_day_root.exists():
        return []
    return sorted(
        (
            path
            for path in trade_day_root.iterdir()
            if path.is_dir() and pattern.match(path.name)
        ),
        key=lambda path: path.name,
    )


def _find_open_trade_id(trade_day_root: Path, symbol: str) -> str:
    for trade_dir in reversed(list(_matching_trade_dirs(trade_day_root, symbol))):
        bundle = _read_json(trade_dir / "lifecycle_bundle.json")
        lifecycle = bundle.get("lifecycle") if isinstance(bundle.get("lifecycle"), dict) else {}
        exit_payload = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        exit_available = bool((bundle.get("exit") or {}).get("available")) if isinstance(bundle.get("exit"), dict) else False
        if exit_payload or exit_available:
            continue
        status = str(bundle.get("trade_lifecycle_status") or "").strip().lower()
        if status in {"", "open"}:
            return trade_dir.name
    return ""


def build_single_trade_report_id(state: Dict[str, Any], *, root: Path | None = None) -> str:
    repo_root = Path(root) if root is not None else _root_dir()
    day = _resolve_trade_day(state, root=repo_root)
    symbol = _execution_symbol(state)
    compact_day = day.replace("-", "")
    trade_day_root = repo_root / "reports" / "trades" / day
    if _execution_action(state) == "SELL":
        existing_open = _find_open_trade_id(trade_day_root, symbol)
        if existing_open:
            return existing_open
    seq = 0
    pattern = re.compile(rf"^TRD_{re.escape(compact_day)}_{re.escape(symbol)}_(\d+)$")
    for trade_dir in _matching_trade_dirs(trade_day_root, symbol):
        match = pattern.match(trade_dir.name)
        if not match:
            continue
        seq = max(seq, int(match.group(1)))
    return f"TRD_{compact_day}_{symbol}_{seq + 1:02d}"


def _entry_strategist_context(state: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    strategy_map = (
        persisted.get("position_strategy_context")
        if isinstance(persisted.get("position_strategy_context"), dict)
        else {}
    )
    stored = strategy_map.get(symbol) if isinstance(strategy_map.get(symbol), dict) else {}
    output = stored.get("output") if isinstance(stored.get("output"), dict) else {}
    if output:
        return dict(output)
    strategist = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    return dict(strategist)


def _build_monitor_snapshot(monitor: Dict[str, Any], *, symbol: str, run_id: str, ts: str) -> Dict[str, Any]:
    return {
        "run_id": str(run_id or ""),
        "ts": str(ts or ""),
        "symbol": str(symbol or ""),
        "decision": str(monitor.get("decision") or ""),
        "decision_summary": str(monitor.get("decision_summary") or ""),
        "primary_reason_code": str(monitor.get("primary_reason_code") or monitor.get("no_trade_reason_code") or ""),
        "current_price": monitor.get("current_price"),
        "avg_price": (
            ((monitor.get("position_snapshot") or {}) if isinstance(monitor.get("position_snapshot"), dict) else {}).get("avg_price")
        ),
        "qty": (
            ((monitor.get("position_snapshot") or {}) if isinstance(monitor.get("position_snapshot"), dict) else {}).get("qty")
        ),
        "position_age_seconds": monitor.get("position_age_seconds"),
    }


def _format_duration(seconds: int | None) -> str:
    total = max(0, int(seconds or 0))
    mins, sec = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours:02d}:{mins:02d}:{sec:02d}"
    return f"00:{mins:02d}:{sec:02d}"


def _build_trade_report_inputs(
    trade_id: str,
    state: Dict[str, Any],
    *,
    root: Path,
) -> Dict[str, Any]:
    day = _resolve_trade_day(state, root=root)
    run_id = str(state.get("run_id") or "").strip()
    symbol = _execution_symbol(state)
    action = _execution_action(state)
    execution = _execution_payload(state)
    monitor = state.get("monitor_output") if isinstance(state.get("monitor_output"), dict) else {}
    scanner = state.get("scanner_output") if isinstance(state.get("scanner_output"), dict) else {}
    commander = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    supervisor = state.get("supervisor_output") if isinstance(state.get("supervisor_output"), dict) else {}
    strategist = _entry_strategist_context(state, symbol)
    execution_ts = str(execution.get("ts") or state.get("ts") or _utc_iso()).strip()
    execution_details = _execution_details_from_state(state)
    entry_execution_details = dict(execution_details if action == "BUY" else _null_execution_details())
    exit_execution_details = dict(execution_details if action == "SELL" else _null_execution_details())
    monitor_snapshot = _build_monitor_snapshot(monitor, symbol=symbol, run_id=run_id, ts=execution_ts)
    hold_duration_sec = _safe_int(monitor.get("position_age_seconds")) or 0
    holding_summary = (
        f"Held for approximately {_format_duration(hold_duration_sec)} before the latest {action or 'trade'} decision."
        if hold_duration_sec > 0
        else "No intermediate hold evidence was captured in the direct intraday path."
    )
    entry_reason = str(
        ((scanner.get("selected") or {}) if isinstance(scanner.get("selected"), dict) else {}).get("why")
        or monitor.get("entry_reason")
        or monitor.get("decision_summary")
        or "Entry context was recovered from the preserved strategist frame."
    )
    exit_reason = str(
        monitor.get("decision_summary")
        or monitor.get("entry_exit_reason")
        or execution.get("reason")
        or ""
    )
    lifecycle_status = "closed" if action == "SELL" else "open"
    execution_view = {
        "run_id": run_id,
        "ts": execution_ts,
        "action": action,
        "symbol": symbol,
        "qty": _safe_int((execution.get("order") or {}).get("qty") if isinstance(execution.get("order"), dict) else execution.get("qty")) or 0,
        "status": str(execution.get("reason") or ""),
        "ord_no": str(execution_details.get("order_id") or ""),
    }
    bundle_out: Dict[str, Any] = {
        "day": day,
        "run_id": run_id,
        "trade_id": trade_id,
        "story_id": trade_id,
        "execution": execution_view,
        "commander": dict(commander),
        "strategist": dict(strategist),
        "scanner": dict(scanner),
        "monitor": dict(monitor),
        "supervisor": dict(supervisor),
        "executor": {
            "execution_ok": bool(execution.get("ok")),
            "broker_env": execution_details.get("broker_env") or "",
            "effective_mode": execution.get("effective_mode") or execution.get("execution_mode") or "",
            "execution_mode": execution_details.get("execution_mode") or "",
        },
        "execution_details": dict(execution_details),
        "entry_execution_details": dict(entry_execution_details),
        "exit_execution_details": dict(exit_execution_details),
        "same_day_reporter_linkage": {
            "status": "missing",
            "reason": "intraday_single_trade_path_does_not_attach_day_reporter",
        },
        "failure_classification": {
            "entry_failure": False,
            "hold_failure": False,
            "exit_failure": False,
            "execution_failure": False,
            "reporting_failure": False,
        },
        "hold_duration": _format_duration(hold_duration_sec),
        "hold_duration_sec": hold_duration_sec,
        "holding_phase_summary": holding_summary,
        "hold_events_count": 1 if hold_duration_sec > 0 else 0,
        "monitor_context_snapshots": [monitor_snapshot] if hold_duration_sec > 0 else [],
        "hold_signal_transitions": [],
        "pre_exit_context_summary": dict(monitor_snapshot) if action == "SELL" else {},
        "canonical_agent_artifacts": {
            "commander": dict(commander),
            "strategist": dict(strategist),
            "scanner": dict(scanner),
            "monitor": dict(monitor),
            "executor": dict(execution),
        },
    }
    story_contract = build_story_contract(bundle_out)
    market_context_human = build_market_context_human(dict(strategist))
    scanner_reason_human = build_scanner_reason_human(dict(scanner), dict(strategist))
    filters_human = build_filters_human(dict(scanner), dict(strategist), dict(supervisor))
    monitor_reason_human = build_monitor_reason_human(dict(monitor), dict(execution_view))
    guard_reason_human = build_guard_reason_human(dict(supervisor))
    execution_outcome_human = build_execution_outcome_human(
        dict(execution_view),
        dict(bundle_out.get("executor") or {}),
        story_type=str(story_contract.get("story_type") or "decision_only"),
        mode_label=str(story_contract.get("execution_mode_label") or ""),
    )
    reporter_status_human = build_reporter_status_human({}, {})
    operator_conclusion_human = build_operator_conclusion_human(
        execution=dict(execution_view),
        scanner_reason_human=scanner_reason_human,
        filters_human=filters_human,
        monitor_reason_human=monitor_reason_human,
        execution_outcome_human=execution_outcome_human,
        reporter_status_human=reporter_status_human,
    )
    timeline = build_timeline(
        commander=dict(commander),
        market_context_human=market_context_human,
        scanner_reason_human=scanner_reason_human,
        monitor_reason_human=monitor_reason_human,
        guard_reason_human=guard_reason_human,
        execution_outcome_human=execution_outcome_human,
        reporter_status_human=reporter_status_human,
        execution=dict(execution_view),
    )
    bundle_out.update(
        {
            "story_contract": dict(story_contract),
            "market_context_human": dict(market_context_human),
            "scanner_reason_human": dict(scanner_reason_human),
            "filters_human": dict(filters_human),
            "monitor_reason_human": dict(monitor_reason_human),
            "guard_reason_human": dict(guard_reason_human),
            "execution_outcome_human": dict(execution_outcome_human),
            "reporter_status_human": dict(reporter_status_human),
            "operator_conclusion_human": dict(operator_conclusion_human),
            "timeline": list(timeline),
        }
    )
    lifecycle = {
        "trade_id": trade_id,
        "symbol": symbol,
        "status": lifecycle_status,
        "story_type": str(story_contract.get("story_type") or ""),
        "execution_mode_label": str(story_contract.get("execution_mode_label") or ""),
        "run_ids_all": [run_id] if run_id else [],
        "entry": {
            "available": bool(action == "BUY" or strategist),
            "run_id": run_id if action == "BUY" else "",
            "ts": execution_ts if action == "BUY" else "",
            "action": "BUY" if action in {"BUY", "SELL"} else action,
            "symbol": symbol,
            "reason_human": entry_reason,
            "strategist_context": dict(strategist),
            "scanner_context": dict(scanner if action == "BUY" else {}),
            "monitor_context": dict(monitor if action == "BUY" else {}),
            "guard_context": dict(supervisor if action == "BUY" else {}),
            "execution_context": dict(entry_execution_details),
            "execution_details": dict(entry_execution_details),
        },
        "holding": {
            "run_ids": [run_id] if hold_duration_sec > 0 and run_id else [],
            "holding_events": (
                [{"run_id": run_id, "ts": execution_ts, "monitor_context": dict(monitor_snapshot)}]
                if hold_duration_sec > 0
                else []
            ),
            "posture_history": [],
            "monitor_updates": [str(monitor.get("decision_summary") or "")] if hold_duration_sec > 0 else [],
            "hold_duration": _format_duration(hold_duration_sec),
            "hold_duration_sec": hold_duration_sec,
            "holding_phase_summary": holding_summary,
            "hold_events_count": 1 if hold_duration_sec > 0 else 0,
            "monitor_context_snapshots": [dict(monitor_snapshot)] if hold_duration_sec > 0 else [],
            "hold_signal_transitions": [],
            "pre_exit_context_summary": dict(monitor_snapshot) if action == "SELL" else {},
        },
        "exit": {
            "available": bool(action == "SELL"),
            "run_id": run_id if action == "SELL" else "",
            "ts": execution_ts if action == "SELL" else "",
            "action": action if action == "SELL" else "",
            "symbol": symbol,
            "reason_human": exit_reason,
            "monitor_context": dict(monitor if action == "SELL" else {}),
            "guard_context": dict(supervisor if action == "SELL" else {}),
            "execution_context": dict(exit_execution_details if action == "SELL" else {}),
            "execution_details": dict(exit_execution_details),
            "position_age_seconds": hold_duration_sec if action == "SELL" else None,
        },
        "summary": {
            "holding_duration": _format_duration(hold_duration_sec),
            "entry_reason_human": entry_reason,
            "exit_reason_human": exit_reason,
            "lifecycle_summary_human": str(execution_outcome_human.get("summary") or ""),
            "operator_conclusion_human": str(operator_conclusion_human.get("summary") or ""),
        },
        "reporter": {},
        "timeline": list(timeline),
        "same_day_reporter_linkage": dict(bundle_out.get("same_day_reporter_linkage") or {}),
        "execution_details": dict(execution_details),
    }
    bundle_out["trade_lifecycle"] = dict(lifecycle)
    story_input = build_trade_story_input(bundle_out, trade_lifecycle=lifecycle)
    story_input["report_runtime_mode"] = "intraday_single_trade"
    story_input["enable_separated_narrative"] = False
    story_input["skip_separated_report_llm"] = True
    story_input["applied_policy"] = dict(state.get("applied_policy") or {})
    story_input["commander"] = {
        **dict(commander),
        "applied_policy": dict(state.get("applied_policy") or {}),
    }
    story_input["reporter_policy"] = dict((state.get("applied_policy") or {}).get("reporter") or {})
    story_input["execution_details"] = dict(execution_details)
    story_input["entry_execution_details"] = dict(entry_execution_details)
    story_input["exit_execution_details"] = dict(exit_execution_details)
    story_input["same_day_reporter_linkage"] = dict(bundle_out.get("same_day_reporter_linkage") or {})
    story_input["failure_classification"] = dict(bundle_out.get("failure_classification") or {})
    story_input["hold_duration"] = _format_duration(hold_duration_sec)
    story_input["hold_duration_sec"] = hold_duration_sec
    story_input["holding_phase_summary"] = holding_summary
    story_input["hold_events_count"] = 1 if hold_duration_sec > 0 else 0
    story_input["monitor_context_snapshots"] = [dict(monitor_snapshot)] if hold_duration_sec > 0 else []
    story_input["pre_exit_context_summary"] = dict(monitor_snapshot) if action == "SELL" else {}
    artifact_links = {
        "lifecycle_bundle_json": str((root / "reports" / "trades" / day / trade_id / "lifecycle_bundle.json")),
        "entry_json": str((root / "reports" / "trades" / day / trade_id / "entry.json")),
        "hold_json": str((root / "reports" / "trades" / day / trade_id / "hold.json")),
        "exit_json": str((root / "reports" / "trades" / day / trade_id / "exit.json")),
        "ai_trade_report_json": str((root / "reports" / "trades" / day / trade_id / "reports" / "ai_trade_report.json")),
        "ai_trade_report_md": str((root / "reports" / "trades" / day / trade_id / "reports" / "ai_trade_report.md")),
        "ai_trade_report_llm_response_json": str((root / "reports" / "trades" / day / trade_id / "reports" / "ai_trade_report_llm_response.json")),
    }
    lifecycle_bundle = build_lifecycle_bundle(
        day=day,
        trade_id=trade_id,
        run_id=run_id,
        symbol=symbol,
        lifecycle=lifecycle,
        strategist_summary=dict(strategist),
        scanner_summary=dict(scanner),
        monitor_summary=dict(monitor),
        commander_summary=dict(commander),
        story_input=dict(story_input),
        diagnostics={},
        canonical_refs={},
        llm_refs={},
        artifact_links=artifact_links,
    )
    return {
        "story_input": story_input,
        "lifecycle": lifecycle,
        "lifecycle_bundle": lifecycle_bundle,
    }


def generate_single_trade_report(
    trade_id: str,
    *,
    state: Dict[str, Any],
    root: Path | None = None,
) -> Dict[str, Any]:
    repo_root = Path(root) if root is not None else _root_dir()
    reports_root = repo_root / "reports"
    policy = _trade_report_policy(state)
    if policy and policy.get("enabled") is False:
        return {
            "ok": False,
            "status": "disabled",
            "reason": "reporter.trade_report.enabled is false",
            "policy_source": str(policy.get("policy_source") or "commander_applied_policy"),
        }
    if not _execution_ok(state):
        return {"ok": False, "status": "skipped", "reason": "execution_not_successful"}
    action = _execution_action(state)
    if action not in {"BUY", "SELL"}:
        return {"ok": False, "status": "skipped", "reason": "non_trade_action"}
    generate_on_open = bool(policy.get("generate_on_open", False))
    if action == "BUY" and not generate_on_open:
        return {
            "ok": True,
            "status": "skipped",
            "reason": "trade_report_generate_on_open_disabled",
            "report_status": "pending",
            "symbol": _execution_symbol(state),
            "trade_id": str(trade_id or ""),
            "policy_source": str(policy.get("policy_source") or "commander_applied_policy"),
        }

    inputs = _build_trade_report_inputs(str(trade_id or "").strip(), state, root=repo_root)
    story_input = dict(inputs.get("story_input") or {})
    lifecycle = dict(inputs.get("lifecycle") or {})
    lifecycle_bundle = dict(inputs.get("lifecycle_bundle") or {})
    day = _resolve_trade_day(story_input if isinstance(story_input, dict) else state, root=repo_root)
    run_id = str(story_input.get("run_id") or state.get("run_id") or "").strip()
    symbol = str(story_input.get("symbol") or _execution_symbol(state)).strip()
    trade_paths = trade_artifact_paths(reports_root, day, trade_id)
    trade_paths["trade_root"].mkdir(parents=True, exist_ok=True)
    trade_paths["reports_dir"].mkdir(parents=True, exist_ok=True)

    write_json(trade_paths["entry_json"], dict(lifecycle.get("entry") or {}))
    write_json(trade_paths["hold_json"], dict(lifecycle.get("holding") or {}))
    write_json(trade_paths["exit_json"], dict(lifecycle.get("exit") or {}))
    write_json(trade_paths["lifecycle_bundle_json"], lifecycle_bundle)
    write_json(trade_paths["ai_trade_report_input_json"], story_input)

    compact_input = build_ai_trade_report_compact_input(story_input)
    compact_artifact = build_compact_input_artifact(
        component="ai_trade_report",
        run_id=run_id,
        trade_id=trade_id,
        story_id=str(story_input.get("story_id") or trade_id),
        day=day,
        source_artifact_path=str(trade_paths["ai_trade_report_input_json"]),
        source_input=story_input,
        compact_input=compact_input,
    )
    write_json(trade_paths["ai_trade_report_compact_input_json"], compact_artifact)

    report = build_ai_trade_report(story_input, enabled=True)
    llm_artifact = report.get("llm_response_artifact") if isinstance(report.get("llm_response_artifact"), dict) else {}
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    report_status = str(generation.get("status") or report.get("ai_trade_report_status") or report.get("status") or "").strip()
    trade_paths["ai_trade_report_json"].write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    trade_paths["ai_trade_report_md"].write_text(
        render_trade_report_markdown(report),
        encoding="utf-8",
    )
    llm_written = ""
    if llm_artifact:
        compact_llm = persist_llm_artifact_refs(
            artifact=llm_artifact,
            reports_root=reports_root,
            day=day,
            run_id=run_id,
            component="ai_trade_report",
        )
        llm_written = str(write_json(trade_paths["ai_trade_report_llm_response_json"], compact_llm))
        llm_artifact = compact_llm

    report_generation_state = {
        "schema_version": "report_generation_state.v1",
        "components": {
            "ai_trade_report": {
                "fingerprint": _json_sha256(
                    {
                        "component": "ai_trade_report",
                        "trade_id": trade_id,
                        "run_id": run_id,
                        "story_input_sha256": _json_sha256(story_input),
                        "compact_input_sha256": _json_sha256(compact_input),
                    }
                ),
                "component": "ai_trade_report",
                "status": report_status,
                "report_status": "available",
                "skip_reason": "",
                "trade_id": trade_id,
                "run_id": run_id,
                "updated_at": _utc_iso(),
                "model": str(
                    ((report.get("generation") or {}) if isinstance(report.get("generation"), dict) else {}).get("model")
                    or llm_artifact.get("model")
                    or ((llm_artifact.get("model_info") or {}) if isinstance(llm_artifact.get("model_info"), dict) else {}).get("model")
                    or ""
                ),
                "report_json_path": str(trade_paths["ai_trade_report_json"]),
                "report_md_path": str(trade_paths["ai_trade_report_md"]),
                "llm_response_path": llm_written,
                "source_inputs": {
                    "story_input_sha256": _json_sha256(story_input),
                    "compact_input_sha256": _json_sha256(compact_input),
                },
            }
        },
    }
    write_json(trade_paths["reports_dir"] / "report_generation_state.json", report_generation_state)
    return {
        "ok": True,
        "status": report_status or "ok",
        "reason": "",
        "trade_id": trade_id,
        "report_status": "available",
        "report_path": str(trade_paths["ai_trade_report_json"]),
        "symbol": symbol,
        "llm_calls": 1,
        "bundle_used": False,
    }
