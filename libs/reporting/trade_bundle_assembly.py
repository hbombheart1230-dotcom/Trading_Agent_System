from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping

from libs.core.symbols import normalize_symbol
from libs.reporting.intraday_trade_reports import (
    build_holding_phase_observability,
    build_same_day_reporter_linkage,
)
from libs.reporting.kiwoom_day_trade_truth import attach_broker_day_pnl
from libs.reporting.trade_fallback_text import (
    EXIT_REASON_NOT_CAPTURED,
    entry_reason_missing_in_summary,
)
from libs.reporting.trade_execution_snapshot import build_execution_details, build_execution_snapshot
from libs.reporting.trade_story_pipeline import (
    build_execution_outcome_human,
    build_filters_human,
    build_guard_reason_human,
    build_market_context_human,
    build_monitor_reason_human,
    build_operator_conclusion_human,
    build_reporter_status_human,
    build_scanner_reason_human,
    build_story_contract,
    build_story_id,
    build_timeline,
    collect_story_warnings,
    compute_evidence_completeness,
    execution_mode_label,
    safe_int,
)
from libs.runtime.canonical_artifacts import load_run_canonical_artifacts


def _coalesce_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _resolve_trade_day_hint(*values: Any) -> str:
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            return raw[:10].replace("-", "")
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) >= 8:
            return digits[:8]
    return ""


def _broker_fill_lookup_enabled(context_obj: Mapping[str, Any]) -> bool:
    explicit = context_obj.get("broker_fill_lookup_enabled")
    if explicit is not None:
        return bool(explicit)
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return str(os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower() == "real"


def _normalize_broker_lookup_side(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "all"
    compact = text.replace("_", "").replace("-", "").replace(" ", "")
    if compact in {"sell", "s", "1"} or "매도" in text:
        return "sell"
    if compact in {"buy", "b", "2"} or "매수" in text:
        return "buy"
    return "all"


def _broker_order_status_payload(dto: Any) -> Dict[str, Any]:
    return {
        "order_id": str(getattr(dto, "ord_no", "") or "").strip() or None,
        "ord_no": str(getattr(dto, "ord_no", "") or "").strip() or None,
        "symbol": normalize_symbol(getattr(dto, "symbol", "") or "", allow_test_symbols=True),
        "status": str(getattr(dto, "status", "") or "").strip() or None,
        "fill_status": str(getattr(dto, "status", "") or "").strip() or None,
        "filled_qty": getattr(dto, "filled_qty", None),
        "filled_price": getattr(dto, "filled_price", None),
        "order_qty": getattr(dto, "order_qty", None),
        "order_price": getattr(dto, "order_price", None),
        "side": str(getattr(dto, "side", "") or "").strip() or None,
        "source": "kiwoom.order_status",
        "raw": dict(getattr(dto, "raw", {}) or {}),
    }


def _attach_broker_order_status(
    bundle: Mapping[str, Any] | None,
    *,
    context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    bundle_obj = dict(bundle or {})
    context_obj = dict(context or {})
    execution_context = (
        dict(context_obj.get("execution_context") or {})
        if isinstance(context_obj.get("execution_context"), dict)
        else {}
    )
    execution_details = (
        dict(context_obj.get("execution_details") or {})
        if isinstance(context_obj.get("execution_details"), dict)
        else {}
    )
    bundle_execution_details = (
        dict(bundle_obj.get("execution_details") or {})
        if isinstance(bundle_obj.get("execution_details"), dict)
        else {}
    )
    if isinstance(execution_context.get("broker_order_status"), dict) and execution_context.get("broker_order_status"):
        context_obj["execution_context"] = execution_context
        return context_obj

    execution = bundle_obj.get("execution") if isinstance(bundle_obj.get("execution"), dict) else {}
    executor = bundle_obj.get("executor") if isinstance(bundle_obj.get("executor"), dict) else {}
    broker_result = executor.get("broker_result") if isinstance(executor.get("broker_result"), dict) else {}
    order_request = executor.get("order_request_summary") if isinstance(executor.get("order_request_summary"), dict) else {}

    order_id = str(
        _coalesce_non_empty(
            execution_details.get("order_id"),
            execution_details.get("ord_no"),
            bundle_execution_details.get("order_id"),
            bundle_execution_details.get("ord_no"),
            execution.get("ord_no"),
            execution.get("order_id"),
            broker_result.get("ord_no"),
            broker_result.get("order_id"),
            executor.get("ord_no"),
            executor.get("order_id"),
            order_request.get("ord_no"),
            order_request.get("order_id"),
            execution_context.get("order_id"),
            execution_context.get("ord_no"),
        )
        or ""
    ).strip()
    symbol = normalize_symbol(
        _coalesce_non_empty(
            context_obj.get("symbol"),
            execution_details.get("symbol"),
            bundle_execution_details.get("symbol"),
            execution.get("symbol"),
            broker_result.get("symbol"),
            executor.get("symbol"),
            order_request.get("symbol"),
            execution_context.get("symbol"),
        )
        or "",
        allow_test_symbols=True,
    )
    side = _normalize_broker_lookup_side(
        _coalesce_non_empty(
            context_obj.get("action"),
            context_obj.get("side"),
            execution_details.get("action"),
            execution_details.get("side"),
            bundle_execution_details.get("action"),
            bundle_execution_details.get("side"),
            execution.get("action"),
            broker_result.get("action"),
            executor.get("action"),
            order_request.get("action"),
            execution_context.get("action"),
        )
        or ""
    )
    ord_dt = _resolve_trade_day_hint(
        context_obj.get("trade_day"),
        context_obj.get("ts"),
        execution_details.get("ts"),
        bundle_execution_details.get("ts"),
        execution_context.get("ts"),
        execution.get("ts"),
        broker_result.get("ts"),
        executor.get("ts"),
        bundle_obj.get("ts"),
    )
    if not (order_id and symbol and ord_dt):
        context_obj["execution_context"] = execution_context
        return context_obj

    reader = context_obj.get("broker_fill_reader")
    if reader is None:
        if not _broker_fill_lookup_enabled(context_obj):
            context_obj["execution_context"] = execution_context
            return context_obj
        try:
            from libs.read.kiwoom_order_fill_reader import KiwoomOrderFillReader

            reader = KiwoomOrderFillReader.from_env()
        except Exception as exc:
            execution_context["broker_order_status_error"] = str(exc)
            context_obj["execution_context"] = execution_context
            return context_obj

    try:
        dto = reader.get_order_status(
            ord_no=order_id,
            symbol=symbol,
            ord_dt=ord_dt,
            side=side or "all",
        )
    except Exception as exc:
        execution_context["broker_order_status_error"] = str(exc)
        context_obj["execution_context"] = execution_context
        return context_obj

    payload = _broker_order_status_payload(dto)
    if payload.get("order_id") in (None, ""):
        payload["order_id"] = order_id
        payload["ord_no"] = order_id
    if (
        payload.get("order_id") not in (None, "")
        and any(payload.get(key) not in (None, "", 0) for key in ("filled_qty", "filled_price", "status"))
    ):
        execution_context["broker_order_status"] = payload
    context_obj["execution_context"] = execution_context
    return context_obj


def build_execution_details_from_bundle(
    bundle: Mapping[str, Any] | None,
    *,
    context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    bundle_obj = dict(bundle or {})
    context_obj = dict(context or {})
    if not isinstance(context_obj.get("monitor_context"), dict):
        monitor_payload = bundle_obj.get("monitor") if isinstance(bundle_obj.get("monitor"), dict) else {}
        if monitor_payload:
            context_obj["monitor_context"] = dict(monitor_payload)
    context_obj = _attach_broker_order_status(bundle_obj, context=context_obj)
    context_obj = attach_broker_day_pnl(bundle_obj, context=context_obj)
    return build_execution_details(bundle_obj, context=context_obj)


def _has_meaningful_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    for value in payload.values():
        if isinstance(value, dict) and _has_meaningful_payload(value):
            return True
        if isinstance(value, list) and any(item not in ({}, [], None, "") for item in value):
            return True
        if value not in ({}, [], None, ""):
            return True
    return False


def _prefer_canonical_payload(
    canonical_sources: Mapping[str, Any] | None,
    agent: str,
    fallback: Mapping[str, Any] | None,
    *,
    fallback_source: str,
    normalized_payload: Mapping[str, Any] | None = None,
    normalized_path: str = "",
) -> Dict[str, Any]:
    canonical_sources = dict(canonical_sources or {})
    canonical_payload = (
        (canonical_sources.get("artifacts") or {}).get(agent)
        if isinstance(canonical_sources.get("artifacts"), dict)
        else {}
    )
    canonical_path = (
        str(((canonical_sources.get("paths") or {}).get(agent) or "")).strip()
        if isinstance(canonical_sources.get("paths"), dict)
        else ""
    )
    merged = dict(fallback or {})
    if _has_meaningful_payload(normalized_payload):
        merged.update(dict(normalized_payload or {}))
        return {"payload": merged, "source": "normalized_trade_artifact", "path": str(normalized_path or "")}
    if _has_meaningful_payload(canonical_payload):
        merged.update(dict(canonical_payload or {}))
        return {"payload": merged, "source": "canonical", "path": canonical_path}
    return {"payload": dict(fallback or {}), "source": str(fallback_source or "fallback"), "path": canonical_path}


def preferred_run_ids_for_agent(
    agent: str,
    *,
    anchor_run_id: str,
    entry_run_id: str,
    exit_run_id: str,
) -> List[str]:
    if agent in {"strategist", "scanner"}:
        ordered = [entry_run_id, anchor_run_id, exit_run_id]
    elif agent in {"monitor", "supervisor", "executor"}:
        ordered = [exit_run_id, anchor_run_id, entry_run_id]
    else:
        ordered = [anchor_run_id, entry_run_id, exit_run_id]
    out: List[str] = []
    for item in ordered:
        rid = str(item or "").strip()
        if rid and rid not in out:
            out.append(rid)
    return out


def resolve_lifecycle_bundle_sources(
    *,
    reports_root: Path,
    day: str,
    anchor_bundle: Mapping[str, Any],
    anchor_run_id: str,
    entry_run_id: str,
    exit_run_id: str,
) -> Dict[str, Any]:
    agents = ("commander", "strategist", "scanner", "monitor", "supervisor", "executor")
    artifacts = dict((anchor_bundle.get("artifacts") if isinstance(anchor_bundle.get("artifacts"), dict) else {}) or {})
    canonical_agent_artifacts = dict(
        (anchor_bundle.get("canonical_agent_artifacts") if isinstance(anchor_bundle.get("canonical_agent_artifacts"), dict) else {}) or {}
    )
    evidence_provenance = dict(
        (anchor_bundle.get("evidence_provenance") if isinstance(anchor_bundle.get("evidence_provenance"), dict) else {}) or {}
    )
    resolved_agents: Dict[str, Dict[str, Any]] = {
        agent: dict(anchor_bundle.get(agent) or {}) if isinstance(anchor_bundle.get(agent), dict) else {}
        for agent in agents
    }
    run_cache: Dict[str, Dict[str, Any]] = {}

    def _load_sources(run_id: str) -> Dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            return {}
        if rid not in run_cache:
            run_cache[rid] = load_run_canonical_artifacts(
                reports_root=reports_root,
                run_id=rid,
                day_hint=day,
            )
        return run_cache[rid]

    for agent in agents:
        canonical_key = f"canonical_{agent}_json"
        for rid in preferred_run_ids_for_agent(
            agent,
            anchor_run_id=anchor_run_id,
            entry_run_id=entry_run_id,
            exit_run_id=exit_run_id,
        ):
            sources = _load_sources(rid)
            paths = dict(sources.get("paths") or {}) if isinstance(sources.get("paths"), dict) else {}
            payloads = dict(sources.get("artifacts") or {}) if isinstance(sources.get("artifacts"), dict) else {}
            if not str(artifacts.get(canonical_key) or "").strip():
                resolved_path = str(paths.get(agent) or "").strip()
                if resolved_path:
                    artifacts[canonical_key] = resolved_path
            if not (
                isinstance(canonical_agent_artifacts.get(agent), dict) and bool(canonical_agent_artifacts.get(agent))
            ):
                resolved_payload = payloads.get(agent)
                if isinstance(resolved_payload, dict) and bool(resolved_payload):
                    canonical_agent_artifacts[agent] = dict(resolved_payload)
            if not resolved_agents.get(agent):
                if isinstance(canonical_agent_artifacts.get(agent), dict) and bool(canonical_agent_artifacts.get(agent)):
                    resolved_agents[agent] = dict(canonical_agent_artifacts.get(agent) or {})
            if resolved_agents.get(agent) and str(artifacts.get(canonical_key) or "").strip():
                break
        if not str(evidence_provenance.get(agent) or "").strip():
            if str(artifacts.get(canonical_key) or "").strip() or (
                isinstance(canonical_agent_artifacts.get(agent), dict) and bool(canonical_agent_artifacts.get(agent))
            ):
                evidence_provenance[agent] = "canonical"
            elif resolved_agents.get(agent):
                evidence_provenance[agent] = "direct_artifact"

    return {
        "artifacts": artifacts,
        "canonical_agent_artifacts": canonical_agent_artifacts,
        "evidence_provenance": evidence_provenance,
        "agents": resolved_agents,
    }


def attach_strategy_anchor(
    payload: Mapping[str, Any] | None,
    *,
    strategy_anchor_run_id: str,
    strategist_input_path: Path,
    strategist_compact_input_path: Path,
    strategist_llm_response_path: Path,
) -> Dict[str, Any]:
    out = dict(payload or {})
    out["entry_strategist_run_id"] = str(strategy_anchor_run_id or "")
    out["strategy_anchor_run_id"] = str(strategy_anchor_run_id or "")
    out["strategy_anchor"] = {
        "run_id": str(strategy_anchor_run_id or ""),
        "artifacts": {
            "strategist_input_json": str(strategist_input_path),
            "strategist_compact_input_json": str(strategist_compact_input_path),
            "strategist_llm_response_json": str(strategist_llm_response_path),
        },
    }
    return out


def apply_strategy_anchor_metadata(
    *,
    lifecycle: Dict[str, Any],
    lifecycle_bundle: Dict[str, Any],
    strategy_anchor_run_id: str,
    strategist_input_path: Path,
    strategist_compact_input_path: Path,
    strategist_llm_response_path: Path,
) -> Dict[str, Any]:
    lifecycle["entry_strategist_run_id"] = strategy_anchor_run_id
    lifecycle["strategy_anchor_run_id"] = strategy_anchor_run_id
    lifecycle["strategy_anchor"] = {
        "run_id": strategy_anchor_run_id,
        "source": "strategist_input_artifact" if strategy_anchor_run_id else "missing",
        "artifacts": {
            "strategist_input_json": str(strategist_input_path),
            "strategist_compact_input_json": str(strategist_compact_input_path),
            "strategist_llm_response_json": str(strategist_llm_response_path),
        },
    }
    lifecycle_bundle["entry_strategist_run_id"] = strategy_anchor_run_id
    lifecycle_bundle["strategy_anchor_run_id"] = strategy_anchor_run_id
    lifecycle_bundle["market_context_human"] = attach_strategy_anchor(
        lifecycle_bundle.get("market_context_human") if isinstance(lifecycle_bundle.get("market_context_human"), dict) else {},
        strategy_anchor_run_id=strategy_anchor_run_id,
        strategist_input_path=strategist_input_path,
        strategist_compact_input_path=strategist_compact_input_path,
        strategist_llm_response_path=strategist_llm_response_path,
    )
    lifecycle_bundle["scanner_reason_human"] = attach_strategy_anchor(
        lifecycle_bundle.get("scanner_reason_human") if isinstance(lifecycle_bundle.get("scanner_reason_human"), dict) else {},
        strategy_anchor_run_id=strategy_anchor_run_id,
        strategist_input_path=strategist_input_path,
        strategist_compact_input_path=strategist_compact_input_path,
        strategist_llm_response_path=strategist_llm_response_path,
    )
    lifecycle_bundle["monitor_reason_human"] = attach_strategy_anchor(
        lifecycle_bundle.get("monitor_reason_human") if isinstance(lifecycle_bundle.get("monitor_reason_human"), dict) else {},
        strategy_anchor_run_id=strategy_anchor_run_id,
        strategist_input_path=strategist_input_path,
        strategist_compact_input_path=strategist_compact_input_path,
        strategist_llm_response_path=strategist_llm_response_path,
    )
    return {
        "lifecycle": lifecycle,
        "lifecycle_bundle": lifecycle_bundle,
        "strategy_anchor_run_id": strategy_anchor_run_id,
    }


def build_live_run_bundle(
    *,
    day: str,
    run_id: str,
    merged_execution: Mapping[str, Any] | None,
    commander_payload: Mapping[str, Any] | None,
    strategist_payload: Mapping[str, Any] | None,
    scanner_payload: Mapping[str, Any] | None,
    monitor_payload: Mapping[str, Any] | None,
    supervisor_payload: Mapping[str, Any] | None,
    executor_payload: Mapping[str, Any] | None,
    reporter_trace_payload: Mapping[str, Any] | None,
    reporter_obj: Mapping[str, Any] | None,
    trade_obj: Mapping[str, Any] | None,
    trace_json_path: Path,
    trace_md_path: Path,
    trade_json_path: Path,
    trade_md_path: Path,
    reporter_json_path: Path,
    reporter_md_path: Path,
    operator_summary_json_path: Path,
    operator_summary_md_path: Path,
    commander_path: str,
    strategist_path: str,
    scanner_path: str,
    monitor_path: str,
    supervisor_path: str,
    executor_path: str,
    canonical_sources: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    reporter_obj = dict(reporter_obj or {})
    trade_obj = dict(trade_obj or {})
    bundle_out: Dict[str, Any] = {
        "schema_version": "live_execution_bundle.v2",
        "artifact_type": "aggregated_execution_bundle",
        "day": str(day or ""),
        "run_id": str(run_id or ""),
        "execution": dict(merged_execution or {}),
        "commander": dict(commander_payload or {}),
        "strategist": dict(strategist_payload or {}),
        "scanner": dict(scanner_payload or {}),
        "monitor": dict(monitor_payload or {}),
        "supervisor": dict(supervisor_payload or {}),
        "executor": dict(executor_payload or {}),
        "reporter": {
            **dict(reporter_trace_payload or {}),
            "reporter_analysis_summary": str(reporter_obj.get("ai_summary") or ""),
            "reporter_analysis_grade": str(reporter_obj.get("ai_run_grade") or "N/A"),
        },
        "artifacts": {
            "agent_pipeline_trace_json": str(trace_json_path),
            "agent_pipeline_trace_md": str(trace_md_path),
            "trade_explain_json": str(trade_json_path),
            "trade_explain_md": str(trade_md_path),
            "reporter_analysis_json": str(reporter_json_path) if Path(reporter_json_path).exists() else "",
            "reporter_analysis_md": str(reporter_md_path) if Path(reporter_md_path).exists() else "",
            "operator_summary_json": str(operator_summary_json_path) if Path(operator_summary_json_path).exists() else "",
            "operator_summary_md": str(operator_summary_md_path) if Path(operator_summary_md_path).exists() else "",
            "canonical_commander_json": str(commander_path or ""),
            "canonical_strategist_json": str(strategist_path or ""),
            "canonical_scanner_json": str(scanner_path or ""),
            "canonical_monitor_json": str(monitor_path or ""),
            "canonical_supervisor_json": str(supervisor_path or ""),
            "canonical_executor_json": str(executor_path or ""),
        },
        "canonical_agent_artifacts": dict((canonical_sources or {}).get("artifacts") or {})
        if isinstance((canonical_sources or {}).get("artifacts"), dict)
        else {},
        "trade_explain_summary": {
            "executions_total": safe_int((trade_obj.get("execution_summary") or {}).get("executions_total"), 0)
            if isinstance(trade_obj.get("execution_summary"), dict)
            else 0
        },
    }
    story_contract = build_story_contract(bundle_out)
    market_context_human = build_market_context_human(bundle_out["strategist"])
    scanner_reason_human = build_scanner_reason_human(bundle_out["scanner"], bundle_out["strategist"])
    filters_human = build_filters_human(bundle_out["scanner"], bundle_out["strategist"], bundle_out["supervisor"])
    monitor_reason_human = build_monitor_reason_human(bundle_out["monitor"], bundle_out["execution"])
    guard_reason_human = build_guard_reason_human(bundle_out["supervisor"])
    execution_outcome_human = build_execution_outcome_human(
        bundle_out["execution"],
        bundle_out["executor"],
        story_type=str(story_contract.get("story_type") or ""),
        mode_label=execution_mode_label(bundle_out["executor"]),
    )
    reporter_status_human = build_reporter_status_human(bundle_out["reporter"], reporter_obj)
    operator_conclusion_human = build_operator_conclusion_human(
        execution=bundle_out["execution"],
        scanner_reason_human=scanner_reason_human,
        filters_human=filters_human,
        monitor_reason_human=monitor_reason_human,
        execution_outcome_human=execution_outcome_human,
        reporter_status_human=reporter_status_human,
    )
    timeline = build_timeline(
        commander=bundle_out["commander"],
        market_context_human=market_context_human,
        scanner_reason_human=scanner_reason_human,
        monitor_reason_human=monitor_reason_human,
        guard_reason_human=guard_reason_human,
        execution_outcome_human=execution_outcome_human,
        reporter_status_human=reporter_status_human,
        execution=bundle_out["execution"],
    )
    warnings = collect_story_warnings(
        story_contract=story_contract,
        market_context_human=market_context_human,
        filters_human=filters_human,
        reporter_status_human=reporter_status_human,
        execution_outcome_human=execution_outcome_human,
    )
    story_contract["warnings"] = warnings
    story_id = build_story_id(day, bundle_out["execution"])
    bundle_out.update(
        {
            "trade_id": "",
            "story_id": story_id,
            "story_contract": story_contract,
            "market_context_human": market_context_human,
            "scanner_reason_human": scanner_reason_human,
            "filters_human": filters_human,
            "monitor_reason_human": monitor_reason_human,
            "guard_reason_human": guard_reason_human,
            "execution_outcome_human": execution_outcome_human,
            "reporter_status_human": reporter_status_human,
            "operator_conclusion_human": operator_conclusion_human,
            "timeline": timeline,
            "warnings": warnings,
        }
    )
    return {
        "bundle_out": bundle_out,
        "story_contract": story_contract,
        "story_id": story_id,
        "story_type": str(story_contract.get("story_type") or "unknown"),
    }


def hydrate_live_run_bundle_context(
    *,
    reports_root: Path,
    day: str,
    run_id: str,
    execution_row: Mapping[str, Any] | None,
    trace_out: Mapping[str, Any] | None,
    reporter_obj: Mapping[str, Any] | None,
    trade_obj: Mapping[str, Any] | None,
    trace_json_path: Path,
    trace_md_path: Path,
    trade_json_path: Path,
    trade_md_path: Path,
    reporter_json_path: Path,
    reporter_md_path: Path,
    operator_summary_json_path: Path,
    operator_summary_md_path: Path,
    bundle_ts: str,
) -> Dict[str, Any]:
    execution_payload = (
        dict(execution_row.get("payload") or {})
        if isinstance(execution_row, Mapping) and isinstance(execution_row.get("payload"), dict)
        else dict(execution_row or {})
        if isinstance(execution_row, Mapping)
        else {}
    )
    canonical_sources = load_run_canonical_artifacts(
        reports_root=reports_root,
        run_id=run_id,
        day_hint=day,
    )
    commander_preferred = _prefer_canonical_payload(
        canonical_sources,
        "commander",
        dict((trace_out or {}).get("commander") or {}),
        fallback_source="direct_artifact",
    )
    strategist_preferred = _prefer_canonical_payload(
        canonical_sources,
        "strategist",
        dict((trace_out or {}).get("strategist") or {}),
        fallback_source="direct_artifact",
    )
    scanner_preferred = _prefer_canonical_payload(
        canonical_sources,
        "scanner",
        dict((trace_out or {}).get("scanner") or {}),
        fallback_source="direct_artifact",
    )
    monitor_preferred = _prefer_canonical_payload(
        canonical_sources,
        "monitor",
        dict((trace_out or {}).get("monitor") or {}),
        fallback_source="direct_artifact",
    )
    supervisor_preferred = _prefer_canonical_payload(
        canonical_sources,
        "supervisor",
        dict((trace_out or {}).get("supervisor") or {}),
        fallback_source="direct_artifact",
    )
    executor_preferred = _prefer_canonical_payload(
        canonical_sources,
        "executor",
        dict((trace_out or {}).get("executor") or {}),
        fallback_source="direct_artifact",
    )
    merged_execution = build_execution_snapshot(
        candidates=[
            execution_payload,
            dict(executor_preferred.get("payload") or {}),
        ],
        run_id=run_id,
        ts=str((execution_row or {}).get("ts") or "") if isinstance(execution_row, Mapping) else "",
    )
    bundle_build = build_live_run_bundle(
        day=day,
        run_id=run_id,
        merged_execution=merged_execution,
        commander_payload=commander_preferred.get("payload") or {},
        strategist_payload=strategist_preferred.get("payload") or {},
        scanner_payload=scanner_preferred.get("payload") or {},
        monitor_payload=monitor_preferred.get("payload") or {},
        supervisor_payload=supervisor_preferred.get("payload") or {},
        executor_payload=executor_preferred.get("payload") or {},
        reporter_trace_payload=dict((trace_out or {}).get("reporter") or {}),
        reporter_obj=reporter_obj,
        trade_obj=trade_obj,
        trace_json_path=trace_json_path,
        trace_md_path=trace_md_path,
        trade_json_path=trade_json_path,
        trade_md_path=trade_md_path,
        reporter_json_path=reporter_json_path,
        reporter_md_path=reporter_md_path,
        operator_summary_json_path=operator_summary_json_path,
        operator_summary_md_path=operator_summary_md_path,
        commander_path=str(commander_preferred.get("path") or ""),
        strategist_path=str(strategist_preferred.get("path") or ""),
        scanner_path=str(scanner_preferred.get("path") or ""),
        monitor_path=str(monitor_preferred.get("path") or ""),
        supervisor_path=str(supervisor_preferred.get("path") or ""),
        executor_path=str(executor_preferred.get("path") or ""),
        canonical_sources=canonical_sources,
    )
    bundle_out = dict(bundle_build.get("bundle_out") or {})
    bundle_out["ts"] = str(bundle_ts or "")
    bundle_out["evidence_provenance"] = {
        "commander": str(commander_preferred.get("source") or ""),
        "strategist": str(strategist_preferred.get("source") or ""),
        "scanner": str(scanner_preferred.get("source") or ""),
        "monitor": str(monitor_preferred.get("source") or ""),
        "supervisor": str(supervisor_preferred.get("source") or ""),
        "executor": str(executor_preferred.get("source") or ""),
        "reporter": "direct_artifact",
    }
    return {
        "bundle_out": bundle_out,
        "story_contract": dict(bundle_build.get("story_contract") or {}),
        "story_id": str(bundle_build.get("story_id") or ""),
        "story_type": str(bundle_build.get("story_type") or "unknown"),
        "canonical_sources": dict(canonical_sources or {}),
    }


def _is_placeholder_entry_reason(value: Any) -> bool:
    raw = str(value or "").strip().lower()
    return raw in {
        "",
        "no_position",
        "entry reasoning was not captured.",
        "entry reasoning was not captured",
        "-",
        "n/a",
    }


def build_strategist_trace_summary_mirror(
    strategist_summary: Mapping[str, Any] | None,
    market_context_human: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    strategist = dict(strategist_summary or {})
    trace = strategist.get("trace_summary") if isinstance(strategist.get("trace_summary"), dict) else {}
    if trace:
        return dict(trace)
    market_context = dict(market_context_human or {})
    highlights = [
        str(x or "")
        for x in list(market_context.get("bullets") or [])
        if str(x or "").strip()
    ][:4]
    return {
        "summary": str(market_context.get("summary") or strategist.get("market_context_summary") or ""),
        "highlights": highlights,
        "market_regime": str(strategist.get("market_regime") or market_context.get("regime") or ""),
        "market_sentiment": str(strategist.get("market_sentiment") or market_context.get("market_sentiment") or ""),
        "playbook": str(strategist.get("playbook") or market_context.get("playbook") or ""),
        "themes": list(strategist.get("themes") or market_context.get("themes") or []),
        "global_sentiment_score": strategist.get("global_sentiment_score", market_context.get("global_sentiment_score")),
        "vix_level": (strategist.get("fear_index") or {}).get("level") if isinstance(strategist.get("fear_index"), dict) else market_context.get("vix_level"),
        "headline_count": market_context.get("headline_count"),
        "news_query_count": market_context.get("news_query_count"),
        "reason_chain": list((strategist.get("strategy_frame") or {}).get("reason_chain") or []),
        "missing_flags": ["trace_summary_missing"],
    }


def build_scanner_trace_summary_mirror(
    scanner_summary: Mapping[str, Any] | None,
    scanner_reason_human: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    scanner = dict(scanner_summary or {})
    trace = scanner.get("trace_summary") if isinstance(scanner.get("trace_summary"), dict) else {}
    if trace:
        return dict(trace)
    reason = dict(scanner_reason_human or {})
    highlights = [
        str(x or "")
        for x in list(reason.get("bullets") or [])
        if str(x or "").strip()
    ][:4]
    selected_symbol = str(scanner.get("selected_symbol") or reason.get("selected_symbol") or "")
    selected_rank = safe_int(scanner.get("selected_rank"), safe_int(reason.get("selected_rank"), 0))
    universe_size = safe_int(scanner.get("universe_size"), safe_int(reason.get("universe_size"), 0))
    detail = scanner.get("selection_reason_detail") if isinstance(scanner.get("selection_reason_detail"), dict) else {}
    runner_up_symbol = ""
    ranked_rows: List[Dict[str, Any]] = []
    for candidate_key in ("candidate_ranking_table", "ranking_table", "ranked_candidates"):
        candidate_value = scanner.get(candidate_key)
        if isinstance(candidate_value, dict):
            ranked_rows = [row for row in list(candidate_value.get("rows") or []) if isinstance(row, dict)]
        elif isinstance(candidate_value, list):
            ranked_rows = [row for row in list(candidate_value or []) if isinstance(row, dict)]
        if ranked_rows:
            break
    if len(ranked_rows) > 1:
        runner_up_symbol = str(ranked_rows[1].get("symbol") or "")
    if not runner_up_symbol:
        runner_up_symbol = str((list(reason.get("runner_ups") or [{}])[:1][0] or {}).get("symbol") or "")
    return {
        "summary": str(reason.get("summary") or scanner.get("selection_reason") or ""),
        "highlights": highlights,
        "selected_symbol": selected_symbol,
        "runner_up_symbol": runner_up_symbol,
        "selected_rank": selected_rank,
        "universe_size": universe_size,
        "candidate_count": universe_size,
        "selected_score_total": detail.get("selected_score_total", reason.get("selected_score")),
        "margin_vs_second": detail.get("margin_vs_second"),
        "selection_basis": list(reason.get("ranking_basis") or []),
        "critical_positive_factors": list(detail.get("critical_positive_factors") or []),
        "critical_negative_factors": list(detail.get("critical_negative_factors") or []),
        "top_candidates": list(reason.get("top_candidates") or []),
        "runner_ups": list(reason.get("runner_ups") or []),
        "missing_flags": ["trace_summary_missing"],
    }


def apply_trace_summary_context(
    *,
    trade_story_input: Dict[str, Any],
    lifecycle_bundle: Dict[str, Any],
    scanner_evidence: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    strategist_trace_summary = build_strategist_trace_summary_mirror(
        lifecycle_bundle.get("strategist") if isinstance(lifecycle_bundle.get("strategist"), dict) else {},
        trade_story_input.get("market_context_human") if isinstance(trade_story_input.get("market_context_human"), dict) else {},
    )
    scanner_trace_summary = build_scanner_trace_summary_mirror(
        lifecycle_bundle.get("scanner") if isinstance(lifecycle_bundle.get("scanner"), dict) else {},
        trade_story_input.get("scanner_reason_human") if isinstance(trade_story_input.get("scanner_reason_human"), dict) else {},
    )
    if not str(scanner_trace_summary.get("runner_up_symbol") or "").strip():
        ranking_tables = (
            list(scanner_evidence.get("candidate_ranking_tables") or [])
            if isinstance(scanner_evidence, dict)
            else []
        )
        if ranking_tables:
            payload = ranking_tables[0].get("payload") if isinstance(ranking_tables[0], dict) else {}
            rows = list(payload.get("rows") or []) if isinstance(payload, dict) else []
            if len(rows) > 1 and isinstance(rows[1], dict):
                scanner_trace_summary["runner_up_symbol"] = str(rows[1].get("symbol") or "")

    selected_symbol = str(
        scanner_trace_summary.get("selected_symbol") or lifecycle_bundle.get("symbol") or ""
    )
    runner_up_symbol = str(scanner_trace_summary.get("runner_up_symbol") or "")
    candidate_count = safe_int(
        scanner_trace_summary.get("candidate_count"),
        safe_int(scanner_trace_summary.get("universe_size"), 0),
    )

    trade_story_input["strategist_trace_summary"] = dict(strategist_trace_summary)
    trade_story_input["scanner_trace_summary"] = dict(scanner_trace_summary)
    trade_story_input["selected_symbol"] = selected_symbol
    trade_story_input["runner_up_symbol"] = runner_up_symbol
    trade_story_input["candidate_count"] = candidate_count

    lifecycle_bundle["strategist_trace_summary"] = dict(strategist_trace_summary)
    lifecycle_bundle["scanner_trace_summary"] = dict(scanner_trace_summary)
    lifecycle_bundle["selected_symbol"] = selected_symbol
    lifecycle_bundle["runner_up_symbol"] = runner_up_symbol
    lifecycle_bundle["candidate_count"] = candidate_count

    return {
        "strategist_trace_summary": strategist_trace_summary,
        "scanner_trace_summary": scanner_trace_summary,
        "trade_story_input": trade_story_input,
        "lifecycle_bundle": lifecycle_bundle,
    }


def apply_entry_exit_holding_enrichment(
    *,
    lifecycle: Dict[str, Any],
    lifecycle_bundle: Dict[str, Any],
    summary_obj: Dict[str, Any],
    trade_id: str,
    symbol: str,
    status: str,
    strategy_anchor_run_id: str,
    strategist_input_path: Path,
    strategist_compact_input_path: Path,
    strategist_llm_response_path: Path,
    entry_run_id: str,
    exit_run_id: str,
    hold_run_ids: List[str] | None,
    linked_run_ids: List[str] | None,
    monitor_timeline: Mapping[str, Any] | None,
    day_event_rows: List[Dict[str, Any]] | None,
) -> Dict[str, Any]:
    lifecycle = dict(lifecycle or {})
    lifecycle_bundle = dict(lifecycle_bundle or {})
    summary_obj = dict(summary_obj or {})
    hold_run_ids = [str(x or "").strip() for x in list(hold_run_ids or []) if str(x or "").strip()]
    linked_run_ids = [str(x or "").strip() for x in list(linked_run_ids or []) if str(x or "").strip()]
    monitor_timeline = dict(monitor_timeline or {})
    day_event_rows = [dict(row) for row in list(day_event_rows or []) if isinstance(row, dict)]

    entry_ctx_live = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    if not entry_ctx_live:
        exit_seed = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        exit_monitor_seed = exit_seed.get("monitor_context") if isinstance(exit_seed.get("monitor_context"), dict) else {}
        inferred_entry_price = (
            exit_monitor_seed.get("average_price")
            or exit_monitor_seed.get("avg_price")
            or exit_monitor_seed.get("current_price")
            or exit_seed.get("price")
        )
        entry_ctx_live = {
            "run_id": str(strategy_anchor_run_id or ""),
            "ts": "",
            "action": "BUY",
            "price": inferred_entry_price,
            "qty": safe_int(exit_seed.get("qty"), 0),
            "reason_human": "Entry evidence was not captured for this day. Position context was inferred from downstream monitor/exit artifacts.",
            "strategist_context": {},
            "scanner_context": {},
            "monitor_context": {},
            "guard_context": {},
            "execution_context": {},
            "inferred_entry": True,
        }
        lifecycle["entry"] = entry_ctx_live
        lifecycle.setdefault("warnings", []).append(
            "Entry evidence was missing; lifecycle entry context was inferred from available artifacts."
        )

    if entry_ctx_live:
        refreshed_strategist_context = dict(entry_ctx_live.get("strategist_context") or {}) if isinstance(entry_ctx_live.get("strategist_context"), dict) else {}
        refreshed_market_context = (
            lifecycle_bundle.get("market_context_human")
            if isinstance(lifecycle_bundle.get("market_context_human"), dict)
            else {}
        )
        strategist_summary_payload = (
            lifecycle_bundle.get("strategist_summary")
            if isinstance(lifecycle_bundle.get("strategist_summary"), dict)
            else {}
        )
        strategist_policy = (
            strategist_summary_payload.get("policy_selected")
            if isinstance(strategist_summary_payload.get("policy_selected"), dict)
            else {}
        )
        scanner_summary_payload = (
            lifecycle_bundle.get("scanner_summary")
            if isinstance(lifecycle_bundle.get("scanner_summary"), dict)
            else {}
        )
        scanner_source_refs = (
            scanner_summary_payload.get("source_refs")
            if isinstance(scanner_summary_payload.get("source_refs"), dict)
            else {}
        )
        if refreshed_market_context:
            refreshed_strategist_context["market_context_summary"] = str(
                refreshed_market_context.get("summary")
                or refreshed_strategist_context.get("market_context_summary")
                or ""
            )
        if not str(refreshed_strategist_context.get("playbook") or "").strip():
            fallback_playbook = str(
                strategist_summary_payload.get("playbook")
                or strategist_policy.get("playbook")
                or scanner_source_refs.get("strategist_playbook")
                or ""
            ).strip()
            if fallback_playbook:
                refreshed_strategist_context["playbook"] = fallback_playbook
        if not list(refreshed_strategist_context.get("themes") or []):
            fallback_themes = [
                str(item or "").strip()
                for item in list(
                    strategist_summary_payload.get("themes")
                    or strategist_policy.get("themes")
                    or []
                )
                if str(item or "").strip()
            ]
            if fallback_themes:
                refreshed_strategist_context["themes"] = fallback_themes[:6]
        entry_ctx_live["strategist_context"] = attach_strategy_anchor(
            refreshed_strategist_context,
            strategy_anchor_run_id=strategy_anchor_run_id,
            strategist_input_path=strategist_input_path,
            strategist_compact_input_path=strategist_compact_input_path,
            strategist_llm_response_path=strategist_llm_response_path,
        )
        refreshed_scanner_context = (
            dict(lifecycle_bundle.get("scanner_reason_human") or {})
            if isinstance(lifecycle_bundle.get("scanner_reason_human"), dict)
            else dict(entry_ctx_live.get("scanner_context") or {})
            if isinstance(entry_ctx_live.get("scanner_context"), dict)
            else {}
        )
        current_entry_reason = str(entry_ctx_live.get("reason_human") or "").strip()
        if _is_placeholder_entry_reason(current_entry_reason):
            fallback_entry_reason = str(
                refreshed_scanner_context.get("summary")
                or (
                    lifecycle_bundle.get("monitor_reason_human").get("summary")
                    if isinstance(lifecycle_bundle.get("monitor_reason_human"), dict)
                    else ""
                )
                or (
                    lifecycle_bundle.get("execution_outcome_human").get("summary")
                    if isinstance(lifecycle_bundle.get("execution_outcome_human"), dict)
                    else ""
                )
                or current_entry_reason
            ).strip()
            if fallback_entry_reason:
                entry_ctx_live["reason_human"] = fallback_entry_reason
        if entry_ctx_live.get("price") is None or entry_ctx_live.get("price") == "":
            execution_payload = (
                lifecycle_bundle.get("execution")
                if isinstance(lifecycle_bundle.get("execution"), dict)
                else {}
            )
            fallback_price = (
                execution_payload.get("price")
                or execution_payload.get("order_price")
                or execution_payload.get("avg_price")
            )
            if (fallback_price is None or fallback_price == "") and isinstance(refreshed_scanner_context.get("selected_candidate"), dict):
                selected_candidate = dict(refreshed_scanner_context.get("selected_candidate") or {})
                feature_snapshot = selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
                fallback_price = feature_snapshot.get("skill_quote_price")
            if fallback_price is None or fallback_price == "":
                holding_for_price = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
                first_monitor_ctx = {}
                for row in list(holding_for_price.get("holding_events") or []):
                    if isinstance(row, dict) and isinstance(row.get("monitor_context"), dict):
                        first_monitor_ctx = dict(row.get("monitor_context") or {})
                        break
                fallback_price = first_monitor_ctx.get("current_price") or first_monitor_ctx.get("price")
            if fallback_price is not None and fallback_price != "":
                entry_ctx_live["price"] = fallback_price
        entry_ctx_live["scanner_context"] = attach_strategy_anchor(
            refreshed_scanner_context,
            strategy_anchor_run_id=strategy_anchor_run_id,
            strategist_input_path=strategist_input_path,
            strategist_compact_input_path=strategist_compact_input_path,
            strategist_llm_response_path=strategist_llm_response_path,
        )
        entry_ctx_live["monitor_context"] = attach_strategy_anchor(
            entry_ctx_live.get("monitor_context") if isinstance(entry_ctx_live.get("monitor_context"), dict) else {},
            strategy_anchor_run_id=strategy_anchor_run_id,
            strategist_input_path=strategist_input_path,
            strategist_compact_input_path=strategist_compact_input_path,
            strategist_llm_response_path=strategist_llm_response_path,
        )
        entry_reason_final = str(entry_ctx_live.get("reason_human") or "").strip()
        if entry_reason_final:
            summary_obj["entry_reason_human"] = entry_reason_final
            current_lifecycle_summary = str(lifecycle_bundle.get("trade_lifecycle_summary") or "")
            if entry_reason_missing_in_summary(current_lifecycle_summary):
                exit_ctx_summary = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
                exit_reason_final = str(exit_ctx_summary.get("reason_human") or EXIT_REASON_NOT_CAPTURED).strip()
                refreshed_lifecycle_summary = (
                    f"Trade {trade_id} for {symbol} is {status}. "
                    f"Entry: {entry_reason_final} "
                    f"Exit: {exit_reason_final}"
                )
                lifecycle_bundle["trade_lifecycle_summary"] = refreshed_lifecycle_summary
                summary_obj["lifecycle_summary_human"] = refreshed_lifecycle_summary
                lifecycle["summary"] = summary_obj
        lifecycle["entry"] = entry_ctx_live

    exit_ctx_live = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    if exit_ctx_live:
        exit_ctx_live["monitor_context"] = attach_strategy_anchor(
            exit_ctx_live.get("monitor_context") if isinstance(exit_ctx_live.get("monitor_context"), dict) else {},
            strategy_anchor_run_id=strategy_anchor_run_id,
            strategist_input_path=strategist_input_path,
            strategist_compact_input_path=strategist_compact_input_path,
            strategist_llm_response_path=strategist_llm_response_path,
        )
        lifecycle["exit"] = exit_ctx_live

    holding_live = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    if isinstance(holding_live.get("holding_events"), list):
        updated_events: List[Dict[str, Any]] = []
        for event in list(holding_live.get("holding_events") or []):
            event_obj = dict(event or {})
            event_obj["monitor_context"] = attach_strategy_anchor(
                event_obj.get("monitor_context") if isinstance(event_obj.get("monitor_context"), dict) else {},
                strategy_anchor_run_id=strategy_anchor_run_id,
                strategist_input_path=strategist_input_path,
                strategist_compact_input_path=strategist_compact_input_path,
                strategist_llm_response_path=strategist_llm_response_path,
            )
            updated_events.append(event_obj)
        holding_live["holding_events"] = updated_events
        lifecycle["holding"] = holding_live

    holding_live = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    existing_hold_events = [
        dict(row)
        for row in list(holding_live.get("holding_events") or [])
        if isinstance(row, dict)
    ]
    if not existing_hold_events:
        fallback_hold_events: List[Dict[str, Any]] = []
        fallback_hold_run_ids: List[str] = []
        seen_hold_runs: set[str] = set()
        for collection_name in ("cycle_summaries", "state_transitions", "threshold_snapshots", "exit_decision_details"):
            for row in list(monitor_timeline.get(collection_name) or []):
                if not isinstance(row, dict):
                    continue
                run_id = str(row.get("run_id") or "").strip()
                if not run_id or run_id in seen_hold_runs or run_id in {entry_run_id, exit_run_id}:
                    continue
                payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
                monitor_reason = str(
                    payload.get("monitor_reason")
                    or payload.get("current_reason")
                    or payload.get("final_reason")
                    or payload.get("summary")
                    or ""
                ).strip()
                posture = str(
                    payload.get("posture")
                    or payload.get("current_posture")
                    or ("HOLD" if collection_name != "entry_decision_details" else "")
                ).strip()
                event_summary = str(row.get("summary") or monitor_reason or posture or "").strip()
                fallback_hold_events.append(
                    {
                        "run_id": run_id,
                        "ts": str(row.get("ts") or ""),
                        "posture": posture,
                        "monitor_reason": monitor_reason,
                        "exit_reason": str(payload.get("exit_reason") or ""),
                        "summary": event_summary,
                        "monitor_context": dict(payload),
                        "source": f"monitor_timeline.{collection_name}",
                    }
                )
                fallback_hold_run_ids.append(run_id)
                seen_hold_runs.add(run_id)
        if fallback_hold_events:
            holding_live["holding_events"] = fallback_hold_events
            holding_live["run_ids"] = fallback_hold_run_ids
            if not list(holding_live.get("monitor_updates") or []):
                holding_live["monitor_updates"] = [
                    str(row.get("summary") or "")
                    for row in fallback_hold_events
                    if str(row.get("summary") or "").strip()
                ][:20]
            lifecycle["holding"] = holding_live
            hold_run_ids = list(fallback_hold_run_ids)

    if not hold_run_ids:
        fallback_rows_by_run: Dict[str, Dict[str, Any]] = {}
        for row in list(day_event_rows or []):
            run_id = str(row.get("run_id") or "").strip()
            if not run_id or run_id in {entry_run_id, exit_run_id}:
                continue
            stage = str(row.get("stage") or row.get("agent") or "").strip().lower()
            if stage not in {"monitor", "decision_trace"}:
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if stage == "decision_trace":
                trace_agent = str(payload.get("agent") or "").strip().lower()
                payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
                if trace_agent not in {"", "monitor"}:
                    continue
            selected_symbol = normalize_symbol(
                payload.get("selected_symbol")
                or payload.get("monitor_symbol")
                or row.get("symbol")
                or symbol,
                allow_test_symbols=True,
            )
            if symbol and selected_symbol not in {"", symbol}:
                continue
            entry = fallback_rows_by_run.setdefault(
                run_id,
                {
                    "run_id": run_id,
                    "ts": str(row.get("ts") or ""),
                    "monitor_context": {},
                    "posture": "",
                    "monitor_reason": "",
                    "exit_reason": "",
                    "summary": "",
                    "source": "day_event_rows.monitor_trace",
                },
            )
            monitor_context = entry["monitor_context"] if isinstance(entry.get("monitor_context"), dict) else {}
            monitor_context.update(dict(payload))
            entry["monitor_context"] = monitor_context
            if not str(entry.get("posture") or "").strip():
                entry["posture"] = str(
                    payload.get("posture")
                    or payload.get("current_posture")
                    or payload.get("action")
                    or "HOLD"
                ).strip()
            if not str(entry.get("monitor_reason") or "").strip():
                entry["monitor_reason"] = str(
                    payload.get("monitor_reason")
                    or payload.get("current_reason")
                    or payload.get("final_reason")
                    or ""
                ).strip()
            if not str(entry.get("exit_reason") or "").strip():
                entry["exit_reason"] = str(payload.get("exit_reason") or "").strip()
            if not str(entry.get("summary") or "").strip():
                entry["summary"] = str(
                    row.get("summary")
                    or payload.get("summary")
                    or payload.get("monitor_reason")
                    or payload.get("exit_reason")
                    or entry.get("posture")
                    or ""
                ).strip()
        if fallback_rows_by_run:
            fallback_hold_events = [dict(value) for _, value in sorted(fallback_rows_by_run.items())]
            hold_run_ids = [str(row.get("run_id") or "") for row in fallback_hold_events if str(row.get("run_id") or "").strip()]
            holding_live = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
            holding_live["holding_events"] = fallback_hold_events
            holding_live["run_ids"] = hold_run_ids
            if not list(holding_live.get("monitor_updates") or []):
                holding_live["monitor_updates"] = [
                    str(row.get("summary") or "")
                    for row in fallback_hold_events
                    if str(row.get("summary") or "").strip()
                ][:20]
            lifecycle["holding"] = holding_live
    elif not hold_run_ids:
        hold_run_ids = [
            str(row.get("run_id") or "").strip()
            for row in existing_hold_events
            if str(row.get("run_id") or "").strip()
        ]
        if hold_run_ids:
            holding_live["run_ids"] = hold_run_ids
            lifecycle["holding"] = holding_live

    for hold_run_id in list(hold_run_ids or []):
        if hold_run_id and hold_run_id not in linked_run_ids:
            linked_run_ids.append(str(hold_run_id))
    lifecycle["run_ids_all"] = list(linked_run_ids)
    lifecycle_bundle["linked_run_ids"] = list(linked_run_ids)

    return {
        "lifecycle": lifecycle,
        "lifecycle_bundle": lifecycle_bundle,
        "summary_obj": summary_obj,
        "entry_ctx_live": lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {},
        "exit_ctx_live": lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {},
        "hold_run_ids": list(hold_run_ids),
        "linked_run_ids": list(linked_run_ids),
    }


def apply_live_trade_context(
    *,
    lifecycle: Dict[str, Any],
    lifecycle_bundle: Dict[str, Any],
    summary_obj: Dict[str, Any],
    status: str,
    monitor_timeline: Dict[str, Any],
    reporter_obj: Dict[str, Any],
    reporter_js: Path,
    reporter_md: Path,
    entry_run_id: str,
    exit_run_id: str,
    entry_ctx_live: Dict[str, Any],
    exit_ctx_live: Dict[str, Any],
    entry_bundle: Dict[str, Any],
    exit_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    trade_day = str(lifecycle_bundle.get("day") or "").strip()
    entry_context = {
        **dict(entry_ctx_live or {}),
        "trade_day": trade_day,
        "broker_fill_lookup_enabled": True,
        "broker_day_truth_lookup_enabled": True,
    }
    exit_context = {
        **dict(exit_ctx_live or {}),
        "trade_day": trade_day,
        "broker_fill_lookup_enabled": True,
        "broker_day_truth_lookup_enabled": True,
    }
    entry_execution_details = build_execution_details_from_bundle(entry_bundle, context=entry_context)
    exit_context["entry_execution_details"] = dict(entry_execution_details)
    exit_execution_details = build_execution_details_from_bundle(exit_bundle, context=exit_context)
    execution_details = dict(exit_execution_details if str(status or "").strip().lower() == "closed" else entry_execution_details)

    holding_phase_observability = build_holding_phase_observability(
        lifecycle,
        monitor_timeline=monitor_timeline,
    )
    same_day_reporter_linkage = build_same_day_reporter_linkage(
        reporter_obj=reporter_obj,
        reporter_js=reporter_js,
        reporter_md=reporter_md,
        entry_run_id=entry_run_id,
        exit_run_id=exit_run_id,
        entry_bundle=entry_bundle,
        exit_bundle=exit_bundle,
    )

    entry_ctx_live = dict(entry_context)
    entry_ctx_live["execution_details"] = dict(entry_execution_details)
    lifecycle["entry"] = entry_ctx_live
    if exit_ctx_live:
        exit_ctx_live = dict(exit_context)
        exit_ctx_live["execution_details"] = dict(exit_execution_details)
        lifecycle["exit"] = exit_ctx_live

    holding_live = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    holding_live["hold_duration"] = holding_phase_observability.get("hold_duration")
    holding_live["hold_duration_sec"] = holding_phase_observability.get("hold_duration_sec")
    holding_live["holding_phase_summary"] = holding_phase_observability.get("holding_phase_summary")
    holding_live["hold_events_count"] = holding_phase_observability.get("hold_events_count")
    holding_live["monitor_context_snapshots"] = list(holding_phase_observability.get("monitor_context_snapshots") or [])
    holding_live["hold_signal_transitions"] = list(holding_phase_observability.get("hold_signal_transitions") or [])
    holding_live["pre_exit_context_summary"] = dict(holding_phase_observability.get("pre_exit_context_summary") or {})
    holding_live["deterioration_signals"] = list(holding_phase_observability.get("deterioration_signals") or [])
    holding_live["hold_evidence_thin"] = bool(holding_phase_observability.get("hold_evidence_thin"))
    lifecycle["holding"] = holding_live

    summary_obj["holding_duration"] = str(
        summary_obj.get("holding_duration")
        or holding_phase_observability.get("hold_duration")
        or ""
    )
    summary_obj["holding_phase_summary"] = str(
        holding_phase_observability.get("holding_phase_summary")
        or summary_obj.get("holding_phase_summary")
        or ""
    )
    summary_obj["pre_exit_context_summary"] = dict(
        holding_phase_observability.get("pre_exit_context_summary") or {}
    )
    summary_obj["same_day_reporter_linkage_status"] = str(
        same_day_reporter_linkage.get("status") or ""
    )
    lifecycle["summary"] = summary_obj
    lifecycle["execution_details"] = dict(execution_details)
    lifecycle["same_day_reporter_linkage"] = dict(same_day_reporter_linkage)
    lifecycle["holding_phase_summary"] = str(holding_phase_observability.get("holding_phase_summary") or "")
    lifecycle["pre_exit_context_summary"] = dict(
        holding_phase_observability.get("pre_exit_context_summary") or {}
    )

    lifecycle_bundle["entry_execution_details"] = dict(entry_execution_details)
    lifecycle_bundle["exit_execution_details"] = dict(exit_execution_details)
    lifecycle_bundle["execution_details"] = dict(execution_details)
    lifecycle_bundle["hold_duration"] = holding_phase_observability.get("hold_duration")
    lifecycle_bundle["hold_duration_sec"] = holding_phase_observability.get("hold_duration_sec")
    lifecycle_bundle["holding_phase_summary"] = holding_phase_observability.get("holding_phase_summary")
    lifecycle_bundle["hold_events_count"] = holding_phase_observability.get("hold_events_count")
    lifecycle_bundle["monitor_context_snapshots"] = list(holding_phase_observability.get("monitor_context_snapshots") or [])
    lifecycle_bundle["hold_signal_transitions"] = list(holding_phase_observability.get("hold_signal_transitions") or [])
    lifecycle_bundle["pre_exit_context_summary"] = dict(holding_phase_observability.get("pre_exit_context_summary") or {})
    lifecycle_bundle["same_day_reporter_linkage"] = dict(same_day_reporter_linkage)
    lifecycle_bundle["reporter_status_human"] = {
        **(
            lifecycle_bundle.get("reporter_status_human")
            if isinstance(lifecycle_bundle.get("reporter_status_human"), dict)
            else {}
        ),
        "same_day_linkage_status": str(same_day_reporter_linkage.get("status") or ""),
        "same_day_linkage_reason": str(same_day_reporter_linkage.get("linkage_reason") or ""),
        "same_day_linkage_source": str(same_day_reporter_linkage.get("linkage_source") or ""),
    }

    return {
        "entry_execution_details": entry_execution_details,
        "exit_execution_details": exit_execution_details,
        "execution_details": execution_details,
        "holding_phase_observability": holding_phase_observability,
        "same_day_reporter_linkage": same_day_reporter_linkage,
        "summary_obj": summary_obj,
        "lifecycle": lifecycle,
        "lifecycle_bundle": lifecycle_bundle,
    }


def derive_trade_recovery_metadata(
    *,
    lifecycle: Mapping[str, Any] | None,
    evidence_completeness: Mapping[str, Any] | None,
    section_provenance: Mapping[str, Any] | None,
    has_substantive_entry_evidence_fn: Any,
) -> Dict[str, Any]:
    lifecycle_obj = dict(lifecycle or {})
    status = str(lifecycle_obj.get("status") or "").strip().lower()
    entry = lifecycle_obj.get("entry") if isinstance(lifecycle_obj.get("entry"), dict) else {}
    exit_ctx = lifecycle_obj.get("exit") if isinstance(lifecycle_obj.get("exit"), dict) else {}
    entry_present = bool(entry)
    exit_present = bool(exit_ctx)
    missing_sections = {
        str(x or "")
        for x in list((evidence_completeness or {}).get("missing_sections") or [])
        if str(x or "").strip()
    }
    provenance_sources = {
        str((value or {}).get("source") or "").strip().lower()
        for value in dict(section_provenance or {}).values()
        if isinstance(value, dict)
    }
    scanner_context = entry.get("scanner_context") if isinstance(entry.get("scanner_context"), dict) else {}
    strategist_context = entry.get("strategist_context") if isinstance(entry.get("strategist_context"), dict) else {}
    inferred_entry = bool(entry.get("inferred_entry"))
    entry_evidence_complete = bool(has_substantive_entry_evidence_fn(entry))
    scanner_selected_symbol = str(scanner_context.get("selected_symbol") or "").strip()
    scanner_summary = str(scanner_context.get("summary") or "").strip().lower()
    strategist_summary = str(strategist_context.get("market_context_summary") or "").strip()
    lifecycle_recovered = (
        status == "partial"
        or (not entry_present)
        or (status not in {"open"} and not exit_present)
        or (status not in {"open"} and not entry_evidence_complete)
    )
    recovery_sources = {
        src for src in provenance_sources if src in {"event_log", "fallback", "normalized_trade_artifact"}
    }
    if lifecycle_recovered:
        recovery_sources.add("partial_lifecycle")
    if not entry_present:
        missing_sections.add("entry")
        recovery_sources.add("entry_missing")
    if status not in {"open"} and not exit_present:
        missing_sections.add("exit")
        recovery_sources.add("exit_missing")
    if inferred_entry:
        missing_sections.add("entry_evidence")
        recovery_sources.add("inferred_entry")
    if entry_present and not entry_evidence_complete:
        missing_sections.add("entry_evidence")
        recovery_sources.add("entry_evidence_thin")
    if entry_present and (
        not scanner_selected_symbol
        or not scanner_summary
        or "not captured" in scanner_summary
        or "did not record" in scanner_summary
    ):
        missing_sections.add("scanner_context")
        recovery_sources.add("scanner_context_missing")
    if entry_present and not strategist_summary:
        missing_sections.add("strategist_context")
        recovery_sources.add("strategist_context_missing")
    evidence_recovery_used = bool(lifecycle_recovered or missing_sections or recovery_sources)
    return {
        "trade_origin": "recovered_partial" if lifecycle_recovered else "normal_lifecycle",
        "lifecycle_completeness": "partial" if evidence_recovery_used else "complete",
        "evidence_recovery_used": bool(evidence_recovery_used),
        "recovery_missing_sections": sorted(missing_sections),
        "recovery_sources": sorted(recovery_sources),
    }


def apply_final_trade_report_context(
    *,
    lifecycle: Mapping[str, Any] | None,
    lifecycle_bundle: Mapping[str, Any] | None,
    trade_story_input: Mapping[str, Any] | None,
    trade_report: Mapping[str, Any] | None,
    diagnostics: Mapping[str, Any] | None,
    failure_classification: Mapping[str, Any] | None,
    same_day_reporter_linkage: Mapping[str, Any] | None,
    execution_details: Mapping[str, Any] | None,
    strategist_evidence: Mapping[str, Any] | None,
    scanner_evidence: Mapping[str, Any] | None,
    monitor_timeline: Mapping[str, Any] | None,
    commander_evidence: Mapping[str, Any] | None,
    lifecycle_bundle_path: Path,
    entry_artifact_path: Path,
    hold_artifact_path: Path,
    exit_artifact_path: Path,
    operator_brief_json_path: Path,
    operator_brief_md_path: Path,
    story_input_path: Path,
    story_compact_input_path: Path,
    trade_report_json_written: str,
    trade_report_md_written: str,
    strategist_llm_response_path: Path,
    ai_trade_report_llm_response_written: str,
    brief_llm_response_path: Path,
    strategist_evidence_path: Path,
    scanner_evidence_path: Path,
    monitor_evidence_path: Path,
    commander_evidence_path: Path,
    trade_provenance_path: Path,
    trade_health_path: Path,
    trade_artifact_links_path: Path,
    has_substantive_entry_evidence_fn: Any,
) -> Dict[str, Any]:
    lifecycle_obj = dict(lifecycle or {})
    lifecycle_bundle_obj = dict(lifecycle_bundle or {})
    trade_story_input_obj = dict(trade_story_input or {})
    trade_report_obj = dict(trade_report or {}) if isinstance(trade_report, dict) else {}
    diagnostics_obj = dict(diagnostics or {})
    failure_classification_obj = dict(failure_classification or {})
    same_day_reporter_linkage_obj = dict(same_day_reporter_linkage or {})
    execution_details_obj = dict(execution_details or {})
    section_provenance = (
        trade_story_input_obj.get("section_provenance")
        if isinstance(trade_story_input_obj.get("section_provenance"), dict)
        else {}
    )

    lifecycle_obj["ai_report_diagnostics"] = dict(diagnostics_obj)
    lifecycle_obj["evidence_artifacts"] = dict(lifecycle_obj.get("evidence") or {})
    lifecycle_obj["section_provenance"] = dict(section_provenance)
    lifecycle_obj["failure_classification"] = dict(failure_classification_obj)
    lifecycle_obj["same_day_reporter_linkage"] = dict(same_day_reporter_linkage_obj)
    lifecycle_obj["execution_details"] = dict(execution_details_obj)

    lifecycle_bundle_obj["ai_report_diagnostics"] = dict(diagnostics_obj)
    lifecycle_bundle_obj["section_provenance"] = dict(section_provenance)
    lifecycle_bundle_obj["failure_classification"] = dict(failure_classification_obj)
    lifecycle_bundle_obj["evidence"] = {
        "strategist": dict(strategist_evidence or {}),
        "scanner": dict(scanner_evidence or {}),
        "monitor": dict(monitor_timeline or {}),
        "commander": dict(commander_evidence or {}),
        "paths": {
            "strategist_evidence_json": str(strategist_evidence_path),
            "scanner_evidence_json": str(scanner_evidence_path),
            "monitor_evidence_json": str(monitor_evidence_path),
            "commander_evidence_json": str(commander_evidence_path),
        },
    }

    trade_story_input_obj["ai_report_diagnostics"] = dict(diagnostics_obj)
    trade_story_input_obj["strategist_evidence"] = dict(strategist_evidence or {})
    trade_story_input_obj["scanner_evidence"] = dict(scanner_evidence or {})
    trade_story_input_obj["monitor_timeline"] = dict(monitor_timeline or {})
    trade_story_input_obj["same_day_reporter_linkage"] = dict(same_day_reporter_linkage_obj)
    trade_story_input_obj["failure_classification"] = dict(failure_classification_obj)

    if trade_report_obj:
        trade_report_obj["ai_report_diagnostics"] = dict(diagnostics_obj)

    artifacts = (
        lifecycle_bundle_obj.get("artifacts")
        if isinstance(lifecycle_bundle_obj.get("artifacts"), dict)
        else {}
    )
    artifacts = dict(artifacts or {})
    artifacts.update(
        {
            "lifecycle_bundle_json": str(lifecycle_bundle_path),
            "entry_json": str(entry_artifact_path),
            "hold_json": str(hold_artifact_path),
            "exit_json": str(exit_artifact_path),
            "brief_json": str(operator_brief_json_path),
            "brief_md": str(operator_brief_md_path),
            "ai_trade_report_input_json": str(story_input_path),
            "trade_story_input_json": str(story_input_path),
            "ai_trade_report_compact_input_json": str(story_compact_input_path),
            "deprecated_ai_trade_report_compact_input_json": str(story_compact_input_path),
            "deprecated_trade_report_json": "",
            "deprecated_trade_report_md": "",
            "ai_trade_report_json": str(trade_report_json_written or ""),
            "ai_trade_report_md": str(trade_report_md_written or ""),
            "operator_brief_json": str(operator_brief_json_path),
            "strategist_llm_response_json": str(strategist_llm_response_path),
            "ai_trade_report_llm_response_json": str(ai_trade_report_llm_response_written or ""),
            "brief_llm_response_json": str(brief_llm_response_path),
            "strategist_evidence_json": str(strategist_evidence_path),
            "scanner_evidence_json": str(scanner_evidence_path),
            "monitor_evidence_json": str(monitor_evidence_path),
            "commander_evidence_json": str(commander_evidence_path),
            "trade_provenance_json": str(trade_provenance_path),
            "trade_health_json": str(trade_health_path),
            "trade_artifact_links_json": str(trade_artifact_links_path),
        }
    )
    for key in (
        "canonical_commander_json",
        "canonical_strategist_json",
        "canonical_scanner_json",
        "canonical_monitor_json",
        "canonical_supervisor_json",
        "canonical_executor_json",
        "lifecycle_bundle_json",
        "entry_json",
        "hold_json",
        "exit_json",
        "brief_json",
        "brief_md",
        "operator_brief_json",
        "ai_trade_report_json",
        "ai_trade_report_md",
        "ai_trade_report_compact_input_json",
        "strategist_llm_response_json",
        "ai_trade_report_llm_response_json",
        "brief_llm_response_json",
    ):
        artifacts.setdefault(key, "")
    lifecycle_bundle_obj["artifacts"] = artifacts

    if trade_report_obj:
        trade_report_obj["paths"] = {
            **(trade_report_obj.get("paths") if isinstance(trade_report_obj.get("paths"), dict) else {}),
            "ai_trade_report_json": str(trade_report_json_written or ""),
            "ai_trade_report_md": str(trade_report_md_written or ""),
            "ai_trade_report_input_json": str(story_input_path),
            "ai_trade_report_compact_input_json": str(story_compact_input_path),
            "ai_trade_report_llm_response_json": str(ai_trade_report_llm_response_written or ""),
            "strategist_input_json": "",
            "strategist_compact_input_json": "",
            "strategist_llm_response_json": str(strategist_llm_response_path),
            "trade_lifecycle_json": "",
            "aggregated_execution_bundle_json": "",
            "lifecycle_bundle_json": str(lifecycle_bundle_path),
            "entry_json": str(entry_artifact_path),
            "hold_json": str(hold_artifact_path),
            "exit_json": str(exit_artifact_path),
            "operator_brief_json": str(operator_brief_json_path),
            "operator_brief_md": str(operator_brief_md_path),
            "brief_llm_response_json": str(brief_llm_response_path),
            "trade_provenance_json": str(trade_provenance_path),
            "trade_health_json": str(trade_health_path),
            "trade_artifact_links_json": str(trade_artifact_links_path),
        }

    evidence_completeness = compute_evidence_completeness(trade_story_input_obj)
    recovery_metadata = derive_trade_recovery_metadata(
        lifecycle=lifecycle_obj,
        evidence_completeness=evidence_completeness,
        section_provenance=section_provenance,
        has_substantive_entry_evidence_fn=has_substantive_entry_evidence_fn,
    )
    trade_story_input_obj.update(recovery_metadata)

    return {
        "lifecycle": lifecycle_obj,
        "lifecycle_bundle": lifecycle_bundle_obj,
        "trade_story_input": trade_story_input_obj,
        "trade_report": trade_report_obj,
        "section_provenance": dict(section_provenance),
        "evidence_completeness": evidence_completeness,
        "recovery_metadata": recovery_metadata,
        "resolved_operator_brief_json": str(
            (artifacts.get("operator_brief_json") or operator_brief_json_path)
        ),
        "resolved_operator_brief_md": str(
            (artifacts.get("brief_md") or operator_brief_md_path)
        ),
        "resolved_brief_llm_response_json": str(
            (artifacts.get("brief_llm_response_json") or brief_llm_response_path)
        ),
    }
