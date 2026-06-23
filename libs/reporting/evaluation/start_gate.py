from __future__ import annotations

from collections import Counter
from typing import Any


REQUIRED_GATE_KEYS = (
    "decision_window_inventory",
    "raw_scanner_control_snapshot",
    "strategist_snapshot",
    "commander_final_snapshot",
    "monitor_entry_timeline",
    "monitor_exit_timeline",
    "broker_integrity",
    "baseline_freeze",
)

REQUIRED_BASELINE_KEYS = (
    "q8_contract",
    "q9_contract",
    "tactic_contract",
    "strategist_prompt",
    "cost_model",
    "strategy_policy",
)
MIN_DECISION_WINDOWS = 20


def _selection(model: dict[str, Any]) -> dict[str, Any]:
    value = model.get("selection")
    return value if isinstance(value, dict) else {}


def _monitor(model: dict[str, Any]) -> dict[str, Any]:
    value = model.get("monitor")
    return value if isinstance(value, dict) else {}


def _integrity(model: dict[str, Any]) -> dict[str, Any]:
    value = model.get("integrity")
    return value if isinstance(value, dict) else {}


def _trade_gate(model: dict[str, Any]) -> dict[str, Any]:
    selection = _selection(model)
    monitor = _monitor(model)
    integrity = _integrity(model)
    raw_source = str(selection.get("raw_scanner_snapshot_source") or "")
    post_rows = selection.get("post_strategist_top10")
    post_exit = monitor.get("post_exit")
    checkpoints = post_exit.get("checkpoints") if isinstance(post_exit, dict) else {}
    observed_post_exit = any(
        isinstance(row, dict) and str(row.get("status") or "") == "observed"
        for row in (checkpoints or {}).values()
    )
    baseline_versions = (
        model.get("baseline_versions")
        if isinstance(model.get("baseline_versions"), dict)
        else {}
    )
    checks = {
        "raw_scanner_control_snapshot": bool(
            raw_source in {"control_snapshot", "scanner_intrinsic_control_snapshot"}
            and isinstance(selection.get("raw_scanner_top10"), list)
            and selection.get("raw_scanner_top10")
        ),
        "strategist_snapshot": bool(
            isinstance(post_rows, list)
            and post_rows
            and selection.get("strategist_run_id")
        ),
        "commander_final_snapshot": bool(selection.get("commander_final_explicit")),
        "monitor_entry_timeline": bool(
            int(monitor.get("entry_decision_count") or 0) > 0
            and (model.get("entry") or {}).get("timestamp")
        ),
        "monitor_exit_timeline": bool(
            int(monitor.get("exit_decision_count") or 0) > 0
            and (model.get("exit") or {}).get("timestamp")
            and observed_post_exit
        ),
        "broker_integrity": str(integrity.get("status") or "") in {"PASS", "WATCH"},
        "baseline_freeze": all(
            str(baseline_versions.get(key) or "").strip()
            for key in REQUIRED_BASELINE_KEYS
        ),
    }
    missing = [key for key, passed in checks.items() if not passed]
    return {
        "trade_id": model.get("trade_id"),
        "symbol": model.get("symbol"),
        "checks": checks,
        "missing": missing,
        "reconstructed_scanner_snapshot_available": bool(
            isinstance(selection.get("reconstructed_pre_adjust_top10"), list)
            and selection.get("reconstructed_pre_adjust_top10")
        ),
        "ranking_only_control": bool(
            raw_source == "scanner_intrinsic_control_snapshot"
            and selection.get("raw_scanner_control_scope") == "same_candidate_universe_ranking_only"
        ),
        "universe_control_available": bool(
            selection.get("raw_scanner_universe_control_available")
        ),
        "missing_baseline_versions": [
            key for key in REQUIRED_BASELINE_KEYS
            if not str(baseline_versions.get(key) or "").strip()
        ],
    }


def build_full_chain_start_gate(
    *,
    models: list[dict[str, Any]],
    inventory: dict[str, Any],
    baseline_hash: str,
) -> dict[str, Any]:
    trade_rows = [_trade_gate(model) for model in models]
    daily_artifacts = inventory.get("daily_artifacts") if isinstance(inventory.get("daily_artifacts"), dict) else {}
    decision_inventory = daily_artifacts.get("q9_decision_windows") if isinstance(daily_artifacts.get("q9_decision_windows"), dict) else {}
    aggregate: dict[str, bool] = {
        "decision_window_inventory": bool(decision_inventory.get("exists")),
        "raw_scanner_control_snapshot": bool(trade_rows) and all(
            row["checks"]["raw_scanner_control_snapshot"] for row in trade_rows
        ),
        "strategist_snapshot": bool(trade_rows) and all(
            row["checks"]["strategist_snapshot"] for row in trade_rows
        ),
        "commander_final_snapshot": bool(trade_rows) and all(
            row["checks"]["commander_final_snapshot"] for row in trade_rows
        ),
        "monitor_entry_timeline": bool(trade_rows) and all(
            row["checks"]["monitor_entry_timeline"] for row in trade_rows
        ),
        "monitor_exit_timeline": bool(trade_rows) and all(
            row["checks"]["monitor_exit_timeline"] for row in trade_rows
        ),
        "broker_integrity": bool(trade_rows) and all(
            row["checks"]["broker_integrity"] for row in trade_rows
        ),
        "baseline_freeze": bool(baseline_hash) and bool(trade_rows) and all(
            row["checks"]["baseline_freeze"] for row in trade_rows
        ),
    }
    passed_count = sum(1 for key in REQUIRED_GATE_KEYS if aggregate.get(key))
    coverage = passed_count / len(REQUIRED_GATE_KEYS)
    missing_counts: Counter[str] = Counter()
    for row in trade_rows:
        missing_counts.update(row.get("missing") or [])
    if not aggregate["decision_window_inventory"]:
        missing_counts["decision_window_inventory"] += 1
    missing = [key for key in REQUIRED_GATE_KEYS if not aggregate.get(key)]
    not_ready_reasons: list[dict[str, Any]] = []
    if not decision_inventory.get("exists"):
        not_ready_reasons.append(
            {
                "category": "missing_artifact",
                "artifact": "q9_decision_windows",
                "detail": "daily Q9 decision-window artifact is missing",
                "count": 1,
            }
        )
    if decision_inventory.get("exists") and not bool(decision_inventory.get("schema_match", True)):
        not_ready_reasons.append(
            {
                "category": "schema_mismatch",
                "artifact": "q9_decision_windows",
                "detail": (
                    f"expected={decision_inventory.get('expected_schema_version')} "
                    f"actual={decision_inventory.get('schema_version')}"
                ),
                "count": 1,
            }
        )
    decision_window_count = int(decision_inventory.get("complete_abc_window_count") or 0)
    if decision_window_count < MIN_DECISION_WINDOWS:
        not_ready_reasons.append(
            {
                "category": "insufficient_decision_window",
                "artifact": "q9_decision_windows",
                "detail": f"complete A/B/C windows {decision_window_count}/{MIN_DECISION_WINDOWS}",
                "count": max(0, MIN_DECISION_WINDOWS - decision_window_count),
            }
        )
    missing_forward = int(decision_inventory.get("forward_missing_candidate_count") or 0)
    forward_total = int(decision_inventory.get("pre_strategist_forward_candidate_count") or 0)
    if forward_total == 0 or missing_forward > 0:
        not_ready_reasons.append(
            {
                "category": "missing_forward_price",
                "artifact": "quant_shadow_candidates",
                "detail": f"observed={forward_total - missing_forward} total={forward_total}",
                "count": missing_forward if forward_total else 1,
            }
        )
    missing_selected = int(decision_inventory.get("missing_selected_candidate_count") or 0)
    if missing_selected > 0:
        not_ready_reasons.append(
            {
                "category": "missing_selected_candidate",
                "artifact": "q9_decision_windows",
                "detail": "Strategist selected_symbol is absent",
                "count": missing_selected,
            }
        )
    for row in trade_rows:
        for missing_key in row.get("missing") or []:
            if missing_key in {"raw_scanner_control_snapshot", "strategist_snapshot", "commander_final_snapshot"}:
                not_ready_reasons.append(
                    {
                        "category": "missing_artifact",
                        "artifact": missing_key,
                        "detail": f"trade_id={row.get('trade_id')}",
                        "count": 1,
                    }
                )
    ready = bool(not missing and not not_ready_reasons and coverage >= 0.95)
    return {
        "schema_version": "q9_full_chain_start_gate.v1",
        "status": "READY" if ready else "NOT_READY",
        "forward_window_started": False,
        "required_coverage": 0.95,
        "coverage": round(coverage, 4),
        "checks": aggregate,
        "missing": missing,
        "missing_counts": dict(sorted(missing_counts.items())),
        "not_ready_reasons": not_ready_reasons,
        "reason_categories": sorted(
            {str(row.get("category") or "") for row in not_ready_reasons if row.get("category")}
        ),
        "decision_window_requirement": {
            "minimum_complete_abc_windows": MIN_DECISION_WINDOWS,
            "current_complete_abc_windows": decision_window_count,
        },
        "trade_count": len(trade_rows),
        "trade_checks": trade_rows,
        "reconstructed_evidence_note": (
            "pre_adjust ranking may support RECONSTRUCTED diagnostics but does not "
            "satisfy the raw Scanner control-snapshot gate"
        ),
    }
