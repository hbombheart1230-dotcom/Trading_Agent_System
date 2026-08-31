from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


StateFn = Callable[[Dict[str, Any]], Dict[str, Any]]


def emit_intraday_trade_report(
    state: Dict[str, Any],
    *,
    reporter_node: StateFn,
    trade_report_enabled_fn: Callable[[Dict[str, Any]], bool],
) -> Dict[str, Any]:
    if trade_report_enabled_fn(state):
        try:
            state["intraday_trade_report"] = reporter_node(state)
        except Exception as exc:
            state["intraday_trade_report"] = {
                "ok": False,
                "status": "failed",
                "reason": f"intraday_trade_artifact_exception:{type(exc).__name__}",
            }
    else:
        state["intraday_trade_report"] = {
            "ok": False,
            "status": "disabled",
            "reason": "reporter.trade_report.enabled is false",
            "policy_source": "commander_applied_policy",
        }
    return state


def execute_approved_monitor_decision(
    state: Dict[str, Any],
    *,
    execute_fn: StateFn,
    emit_trade_report_fn: StateFn,
    update_state_after_execution_fn: StateFn,
    intent_from_monitor_state_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_packet_from_state_fn: Callable[..., Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    decision = str(state.get("decision") or "").strip().lower()
    if decision != "approve":
        return state, {"executor_action": "", "executor_status": ""}

    intent = intent_from_monitor_state_fn(state)
    state["decision_packet"] = build_packet_from_state_fn(state, intent=intent)
    state = execute_fn(state)
    executor_action = str(
        (((state.get("execution") or {}).get("order") or {}).get("action")
        or ((state.get("decision_packet") or {}).get("intent") or {}).get("action")
        or "")
    )
    executor_status = str(
        ((state.get("execution") or {}).get("reason")
        or ((state.get("execution") or {}).get("ok_source") or ""))
    )
    state = emit_trade_report_fn(state)
    state = update_state_after_execution_fn(state)
    return state, {"executor_action": executor_action, "executor_status": executor_status}


def run_monitor_decision_path(
    state: Dict[str, Any],
    *,
    shadow_runtime: Dict[str, Any],
    hydrate_monitor_symbol_features_fn: StateFn,
    monitor_node_fn: StateFn,
    decision_node_fn: StateFn,
    execute_fn: StateFn,
    emit_trade_report_fn: StateFn,
    update_state_after_execution_fn: StateFn,
    intent_from_monitor_state_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_packet_from_state_fn: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    state = hydrate_monitor_symbol_features_fn(state)
    state = monitor_node_fn(state)
    shadow_runtime["monitor_decision"] = str(((state.get("monitor_output") or {}).get("intent_side") or "NOOP"))
    state = decision_node_fn(state)
    try:
        from libs.runtime.q9_decision_snapshots import capture_commander_decision_snapshot
        from libs.runtime.quant.shadow_candidates import sync_q9_decision_candidates_for_state

        state["q9_commander_snapshot_result"] = capture_commander_decision_snapshot(state)
        state["q9_shadow_sync_result"] = sync_q9_decision_candidates_for_state(state)
    except Exception as exc:
        state["q9_commander_snapshot_result"] = {
            "status": "error",
            "reason": f"{type(exc).__name__}: {exc}"[:300],
        }
    state, execution_meta = execute_approved_monitor_decision(
        state,
        execute_fn=execute_fn,
        emit_trade_report_fn=emit_trade_report_fn,
        update_state_after_execution_fn=update_state_after_execution_fn,
        intent_from_monitor_state_fn=intent_from_monitor_state_fn,
        build_packet_from_state_fn=build_packet_from_state_fn,
    )
    if execution_meta.get("executor_action") or execution_meta.get("executor_status"):
        shadow_runtime["executor_action"] = str(execution_meta.get("executor_action") or "")
        shadow_runtime["executor_status"] = str(execution_meta.get("executor_status") or "")
    return state


def run_controlled_mock_lane_path(
    state: Dict[str, Any],
    *,
    shadow_runtime: Dict[str, Any],
    decision_node_fn: StateFn,
    execute_fn: StateFn,
    emit_trade_report_fn: StateFn,
    update_state_after_execution_fn: StateFn,
    intent_from_monitor_state_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_packet_from_state_fn: Callable[..., Dict[str, Any]],
    reports_root: Any = "reports",
    ledger_root: Any = None,
) -> Tuple[Dict[str, Any], bool]:
    from libs.runtime.controlled_mock_lanes import (
        finalize_controlled_mock_lane_submission,
        inject_controlled_mock_lane_intent,
    )

    try:
        state = inject_controlled_mock_lane_intent(
            state,
            reports_root=reports_root,
            ledger_root=ledger_root,
        )
    except Exception as exc:
        state["controlled_mock_lanes"] = {
            "schema_version": "controlled_mock_lanes.v1",
            "enabled": True,
            "evaluated": False,
            "injected": False,
            "reason": f"measurement_exception:{type(exc).__name__}",
            "error": str(exc)[:300],
        }
        return state, False
    if not bool((state.get("controlled_mock_lanes") or {}).get("injected")):
        return state, False

    state = decision_node_fn(state)
    shadow_runtime["controlled_mock_lane"] = str(
        (state.get("controlled_mock_lanes") or {}).get("selected_lane") or ""
    )
    state, execution_meta = execute_approved_monitor_decision(
        state,
        execute_fn=execute_fn,
        emit_trade_report_fn=emit_trade_report_fn,
        update_state_after_execution_fn=update_state_after_execution_fn,
        intent_from_monitor_state_fn=intent_from_monitor_state_fn,
        build_packet_from_state_fn=build_packet_from_state_fn,
    )
    state = finalize_controlled_mock_lane_submission(state, ledger_root=ledger_root)
    if execution_meta.get("executor_action") or execution_meta.get("executor_status"):
        shadow_runtime["executor_action"] = str(execution_meta.get("executor_action") or "")
        shadow_runtime["executor_status"] = str(execution_meta.get("executor_status") or "")
    return state, str(state.get("decision") or "").strip().lower() == "approve"
