from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from libs.reporting.trade_read_model import build_trade_read_model as build_legacy_trade_read_model

from .artifact_inventory import inventory_trade, read_json
from .contracts import CONTRACT_VERSION, EvidenceClass, IntegrityStatus
from .horizon_contract import build_horizon_contract
from .scanner_score_decomposition import decompose_scanner_score


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text or text == "unknown":
        return None
    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _meaningful(*values: Any) -> Any:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() not in {"unknown", "none", "null", "unavailable", "nan"}:
            return value
    return None


def _lifecycle_sections(bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    lifecycle = bundle.get("lifecycle") if isinstance(bundle.get("lifecycle"), dict) else bundle
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else bundle.get("entry")
    exit_row = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else bundle.get("exit")
    return lifecycle, entry if isinstance(entry, dict) else {}, exit_row if isinstance(exit_row, dict) else {}


def _is_realized_exit(exit_row: dict[str, Any], bundle: dict[str, Any]) -> bool:
    if not exit_row:
        return False
    details = exit_row.get("execution_details") if isinstance(exit_row.get("execution_details"), dict) else {}
    action = str(exit_row.get("action") or details.get("action") or "").upper()
    timestamp = exit_row.get("timestamp") or exit_row.get("ts")
    filled_quantity = details.get("filled_qty") or exit_row.get("filled_qty")
    broker_pnl = details.get("broker_realized_pnl")
    shared = bundle.get("shared_facts") if isinstance(bundle.get("shared_facts"), dict) else {}
    shared_status = str(shared.get("status") or "").lower()
    lifecycle = bundle.get("lifecycle") if isinstance(bundle.get("lifecycle"), dict) else {}
    lifecycle_status = str(lifecycle.get("status") or "").lower()
    return bool(
        (timestamp and action == "SELL")
        or (timestamp and filled_quantity)
        or broker_pnl is not None
        or shared_status in {"closed", "sold", "realized"}
        or lifecycle_status in {"closed", "sold", "realized"}
    )


def _holding_seconds(entry_ts: Any, exit_ts: Any, fallback: Any) -> Any:
    existing = _meaningful(fallback)
    if existing is not None:
        try:
            if float(existing) > 0:
                return existing
        except (TypeError, ValueError):
            pass
    entry_dt = _parse_ts(entry_ts)
    exit_dt = _parse_ts(exit_ts)
    if entry_dt is None or exit_dt is None or exit_dt < entry_dt:
        return fallback
    return int((exit_dt - entry_dt).total_seconds())


def _scanner_evidence_context(trade_dir: Path, selected_symbol: str) -> dict[str, Any]:
    evidence = read_json(trade_dir / "evidence" / "scanner_evidence.json")
    selected_rank = None
    selected_candidate = None
    ranking_rows: list[dict[str, Any]] = []
    for event in evidence.get("candidate_ranking_tables") or []:
        payload = event.get("payload") if isinstance(event, dict) and isinstance(event.get("payload"), dict) else {}
        rows = [dict(row) for row in payload.get("rows") or [] if isinstance(row, dict)]
        if rows and not ranking_rows:
            ranking_rows = rows[:10]
        for row in rows:
            if not isinstance(row, dict) or str(row.get("symbol") or "") != selected_symbol:
                continue
            selected_rank = row.get("rank")
            selected_candidate = dict(row)
            break
        if selected_candidate:
            break
    playbook = None
    for event in evidence.get("candidate_selection_reasons") or []:
        payload = event.get("payload") if isinstance(event, dict) and isinstance(event.get("payload"), dict) else {}
        strategist_ref = (
            payload.get("strategist_constraints_ref")
            if isinstance(payload.get("strategist_constraints_ref"), dict)
            else {}
        )
        playbook = _meaningful(payload.get("playbook"), strategist_ref.get("selected_playbook"))
        if playbook is not None:
            break
    return {
        "selected_rank": selected_rank,
        "selected_candidate": selected_candidate,
        "playbook": playbook,
        "post_strategist_top10": ranking_rows,
        "reconstructed_pre_adjust_top10": sorted(
            ranking_rows,
            key=lambda row: (
                -float(row.get("pre_adjust_score_total") or 0.0),
                -float(row.get("confidence") or 0.0),
                float(row.get("risk_score") or 0.0),
            ),
        ),
    }


def _candidate_by_symbol(rows: Any, symbol: str) -> dict[str, Any]:
    if not symbol or not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and str(row.get("symbol") or "") == symbol:
            return dict(row)
    return {}


def _monitor_evidence_context(trade_dir: Path) -> dict[str, Any]:
    evidence = read_json(trade_dir / "evidence" / "monitor_evidence.json")
    return {
        "entry_decision_count": len(evidence.get("entry_decision_details") or []),
        "exit_decision_count": len(evidence.get("exit_decision_details") or []),
        "state_transition_count": len(evidence.get("state_transitions") or []),
        "threshold_snapshot_count": len(evidence.get("threshold_snapshots") or []),
    }


def _closeout_broker_skip(trade_dir: Path, *, day: str, trade_id: str) -> dict[str, Any]:
    try:
        reports_root = trade_dir.parents[3]
    except IndexError:
        return {}
    closeout = read_json(
        reports_root / "operator_summary" / "daily" / day[:10] / "closeout_maintenance.json"
    )
    steps = closeout.get("steps") if isinstance(closeout.get("steps"), dict) else {}
    broker = (
        steps.get("broker_closed_trade_reconciliation")
        if isinstance(steps.get("broker_closed_trade_reconciliation"), dict)
        else {}
    )
    for row in broker.get("skipped") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("trade_id") or "") == trade_id:
            return {
                "trade_id": trade_id,
                "symbol": str(row.get("symbol") or ""),
                "reason": str(row.get("reason") or "broker_closed_trade_unresolved"),
                "snapshot_path": str(broker.get("snapshot_path") or ""),
            }
    return {}


def _daily_q9_snapshot(
    trade_dir: Path,
    *,
    day: str,
    entry: dict[str, Any],
    scanner_context: dict[str, Any],
    selected_symbol: str,
) -> tuple[dict[str, Any], str]:
    try:
        reports_root = trade_dir.parents[3]
    except IndexError:
        return {}, ""
    payload = read_json(
        reports_root / "operator_summary" / "daily" / day[:10] / "q9_decision_windows.json"
    )
    windows = [dict(row) for row in payload.get("windows") or [] if isinstance(row, dict)]
    if not windows:
        return {}, ""

    decision_id = str(scanner_context.get("q9_decision_id") or "").strip()
    if decision_id:
        exact = next(
            (row for row in windows if str(row.get("decision_id") or "") == decision_id),
            None,
        )
        if exact:
            return exact, "daily_q9_window.decision_id"

    run_ids = {
        str(value or "").strip()
        for value in (
            entry.get("run_id"),
            scanner_context.get("run_id"),
            scanner_context.get("entry_run_id"),
        )
        if str(value or "").strip()
    }
    for row in windows:
        if str(row.get("run_id") or "").strip() in run_ids:
            return row, "daily_q9_window.run_id"

    entry_ts = _parse_ts(entry.get("timestamp") or entry.get("ts"))
    if entry_ts is None or not selected_symbol:
        return {}, ""
    nearest: tuple[float, dict[str, Any]] | None = None
    for row in windows:
        strategist = row.get("strategist_selection")
        strategist = strategist if isinstance(strategist, dict) else {}
        commander = row.get("commander_final")
        commander = commander if isinstance(commander, dict) else {}
        if selected_symbol not in {
            str(strategist.get("selected_symbol") or ""),
            str(commander.get("selected_symbol") or ""),
            str(commander.get("candidate_symbol") or ""),
        }:
            continue
        generated_at = _parse_ts(row.get("generated_at"))
        if generated_at is None:
            continue
        delta = abs((generated_at - entry_ts).total_seconds())
        if delta <= 600 and (nearest is None or delta < nearest[0]):
            nearest = (delta, row)
    return (nearest[1], "daily_q9_window.nearest_symbol_time") if nearest else ({}, "")


def build_q9_trade_read_model(trade_dir: Path) -> dict[str, Any]:
    legacy = build_legacy_trade_read_model(str(trade_dir))
    bundle = read_json(trade_dir / "lifecycle_bundle.json")
    legacy_facts = legacy.get("facts") if isinstance(legacy.get("facts"), dict) else {}
    trade_id = str(legacy_facts.get("trade_id") or bundle.get("trade_id") or trade_dir.name)
    day = str(bundle.get("day") or trade_dir.parts[-3])
    lifecycle, entry, exit_row = _lifecycle_sections(bundle)
    entry_artifact = read_json(trade_dir / "entry.json")
    exit_artifact = read_json(trade_dir / "exit.json")
    if entry_artifact:
        entry = {**entry, **entry_artifact}
    if exit_artifact:
        exit_row = {**exit_row, **exit_artifact}
    realized_exit = _is_realized_exit(exit_row, bundle)
    inventory = inventory_trade(trade_dir)
    facts = legacy.get("facts") if isinstance(legacy.get("facts"), dict) else legacy
    entry_ts = _meaningful(entry.get("timestamp"), entry.get("ts"), facts.get("entry_ts"))
    entry_details = (
        entry.get("execution_details")
        if isinstance(entry.get("execution_details"), dict)
        else {}
    )
    entry_price = _meaningful(
        entry.get("filled_price"),
        entry_details.get("filled_price"),
        entry_details.get("avg_price"),
        entry.get("avg_price"),
        entry.get("price"),
    )
    exit_ts = _meaningful(exit_row.get("timestamp"), exit_row.get("ts"), facts.get("exit_ts")) if realized_exit else None
    legacy_pnl_source = (
        ((legacy.get("provenance") or {}).get("field_sources") or {}).get("pnl_pct")
        if isinstance(legacy.get("provenance"), dict)
        else ""
    )
    exit_details = exit_row.get("execution_details") if isinstance(exit_row.get("execution_details"), dict) else {}
    shared_facts = bundle.get("shared_facts") if isinstance(bundle.get("shared_facts"), dict) else {}
    broker_exit_authoritative = bool(
        exit_row.get("broker_day_authoritative")
        or exit_details.get("broker_day_authoritative")
    )
    broker_pnl_pct = (
        exit_details.get("broker_realized_pnl_pct")
        if exit_details.get("broker_realized_pnl_pct") is not None
        else exit_row.get("broker_realized_pnl_pct")
    )
    broker_pnl = (
        exit_details.get("broker_realized_pnl")
        if exit_details.get("broker_realized_pnl") is not None
        else exit_row.get("broker_realized_pnl")
    )
    pnl_ratio = broker_pnl_pct if broker_pnl_pct is not None else facts.get("pnl_pct")
    pnl_source = "exit.execution_details.broker_realized_pnl_pct" if broker_pnl_pct is not None else legacy_pnl_source
    closeout_broker_skip = _closeout_broker_skip(trade_dir, day=day, trade_id=trade_id)
    existing_broker_truth = bool(
        realized_exit
        and (
            broker_exit_authoritative
            or broker_pnl_pct is not None
            or str(shared_facts.get("pnl_truth_source") or "").startswith(("kiwoom.", "broker"))
            or str(shared_facts.get("price_truth_source") or "").startswith(("kiwoom.", "broker"))
        )
    )

    defects: list[str] = []
    watch_items: list[str] = []
    if inventory["missing_required"]:
        watch_items.extend(f"missing:{name}" for name in inventory["missing_required"])
    if not entry:
        defects.append("entry_missing")
    if realized_exit and not _parse_ts(exit_ts):
        if broker_exit_authoritative:
            watch_items.append("broker_exit_timestamp_unavailable")
        else:
            defects.append("exit_timestamp_invalid")
    if _parse_ts(entry_ts) and _parse_ts(exit_ts) and _parse_ts(exit_ts) < _parse_ts(entry_ts):
        defects.append("exit_before_entry")
    if realized_exit and not str(pnl_source or "").startswith(("lifecycle", "broker", "ai_trade_report", "exit.")):
        watch_items.append("pnl_authority_weak")
    if not realized_exit:
        watch_items.append("trade_open_or_exit_missing")
    if closeout_broker_skip and not existing_broker_truth:
        defects.append("broker_closed_trade_unresolved")
        watch_items.append(f"broker_reconciliation_skipped:{closeout_broker_skip.get('reason')}")

    if "exit_before_entry" in defects or "entry_missing" in defects:
        integrity = IntegrityStatus.BLOCKER
    elif defects:
        integrity = IntegrityStatus.FAIL
    elif watch_items:
        integrity = IntegrityStatus.WATCH
    else:
        integrity = IntegrityStatus.PASS

    scanner_context = entry.get("scanner_context") if isinstance(entry.get("scanner_context"), dict) else {}
    strategist_context = entry.get("strategist_context") if isinstance(entry.get("strategist_context"), dict) else {}
    monitor_context = entry.get("monitor_context") if isinstance(entry.get("monitor_context"), dict) else {}
    selected_symbol = str(scanner_context.get("selected_symbol") or facts.get("symbol") or "")
    scanner_evidence = _scanner_evidence_context(trade_dir, selected_symbol)
    monitor_evidence = _monitor_evidence_context(trade_dir)
    post_exit = (
        exit_artifact.get("post_exit_shadow")
        if isinstance(exit_artifact.get("post_exit_shadow"), dict)
        else bundle.get("post_exit_shadow")
        if isinstance(bundle.get("post_exit_shadow"), dict)
        else exit_row.get("post_exit_shadow")
        if isinstance(exit_row.get("post_exit_shadow"), dict)
        else {}
    )
    commander_final = (
        scanner_context.get("commander_final")
        if isinstance(scanner_context.get("commander_final"), dict)
        else {}
    )
    q9_snapshot = (
        scanner_context.get("q9_decision_snapshot")
        if isinstance(scanner_context.get("q9_decision_snapshot"), dict)
        else {}
    )
    q9_snapshot_source = "entry.scanner_context.q9_decision_snapshot" if q9_snapshot else ""
    if not q9_snapshot:
        q9_snapshot, q9_snapshot_source = _daily_q9_snapshot(
            trade_dir,
            day=str(bundle.get("day") or trade_dir.parts[-3]),
            entry=entry,
            scanner_context=scanner_context,
            selected_symbol=selected_symbol,
        )
    scanner_control = (
        q9_snapshot.get("scanner_control")
        if isinstance(q9_snapshot.get("scanner_control"), dict)
        else {}
    )
    pre_strategist_universe = (
        q9_snapshot.get("scanner_pre_strategist_universe")
        if isinstance(q9_snapshot.get("scanner_pre_strategist_universe"), dict)
        else {}
    )
    strategist_selection = (
        q9_snapshot.get("strategist_selection")
        if isinstance(q9_snapshot.get("strategist_selection"), dict)
        else {}
    )
    if not commander_final and isinstance(q9_snapshot.get("commander_final"), dict):
        commander_final = dict(q9_snapshot.get("commander_final") or {})
    raw_scanner_top10 = (
        list(scanner_control.get("top10") or [])
        if isinstance(scanner_control.get("top10"), list)
        else list(scanner_context.get("raw_scanner_top10") or [])
    )
    post_strategist_top10 = (
        list(strategist_selection.get("post_strategist_top10") or [])
        if isinstance(strategist_selection.get("post_strategist_top10"), list)
        else list(scanner_evidence.get("post_strategist_top10") or [])
    )
    raw_scanner_top1 = (
        raw_scanner_top10[0]
        if raw_scanner_top10
        else scanner_context.get("raw_scanner_top1")
        or scanner_context.get("pre_strategist_top1")
        or scanner_context.get("unbiased_top_candidate")
    )
    post_strategy_top1 = (
        post_strategist_top10[0]
        if post_strategist_top10
        else (scanner_context.get("top_candidates") or [None])[0]
    )
    selected_candidate = (
        scanner_evidence.get("selected_candidate")
        if isinstance(scanner_evidence.get("selected_candidate"), dict)
        else {}
    )
    if not selected_candidate:
        selected_candidate = (
            _candidate_by_symbol(post_strategist_top10, selected_symbol)
            or _candidate_by_symbol(raw_scanner_top10, selected_symbol)
        )
    horizon_contract = build_horizon_contract(
        bundle=bundle,
        entry=entry,
        exit_row=exit_row,
        entry_artifact=entry_artifact,
        exit_artifact=exit_artifact,
        scanner_context=scanner_context,
        strategist_context=strategist_context,
        monitor_context=monitor_context,
    )
    return {
        "schema_version": "q9_trade_read_model.v1",
        "contract_version": CONTRACT_VERSION,
        "evidence_class": EvidenceClass.REALIZED.value if realized_exit else EvidenceClass.UNAVAILABLE.value,
        "trade_id": trade_id,
        "day": day,
        "symbol": str(facts.get("symbol") or bundle.get("symbol") or ""),
        "status": str(
            lifecycle.get("status")
            or ((bundle.get("shared_facts") or {}).get("status") if isinstance(bundle.get("shared_facts"), dict) else "")
            or facts.get("execution_label")
            or ""
        ),
        "entry": {
            "timestamp": entry_ts,
            "price": entry_price,
            "quantity": entry.get("qty") or entry.get("quantity"),
            "reason": facts.get("entry_reason"),
        },
        "exit": {
            "timestamp": exit_ts,
            "price": exit_row.get("price"),
            "quantity": exit_row.get("qty") or exit_row.get("quantity"),
            "reason": facts.get("exit_reason"),
            "broker_authoritative": broker_exit_authoritative,
            "broker_truth_source": str(
                exit_row.get("broker_day_truth_source")
                or exit_details.get("broker_day_truth_source")
                or ""
            ),
        },
        "outcome": {
            "net_return_pct": round(float(pnl_ratio) * 100.0, 6) if realized_exit and pnl_ratio is not None else None,
            "net_return_ratio": float(pnl_ratio) if realized_exit and pnl_ratio is not None else None,
            "realized_pnl": broker_pnl if realized_exit and broker_pnl is not None else (facts.get("pnl") if realized_exit else None),
            "pnl_source": pnl_source,
            "holding_seconds": _holding_seconds(entry_ts, exit_ts, facts.get("hold_duration_sec")),
        },
        "horizon_contract": horizon_contract,
        "selection": {
            "scanner_top1": post_strategy_top1,
            "raw_scanner_top1": raw_scanner_top1,
            "selected_symbol": selected_symbol,
            "selected_rank": scanner_context.get("selected_rank") or scanner_evidence.get("selected_rank"),
            "selected_candidate": selected_candidate,
            "runner_ups": scanner_context.get("runner_ups") or [],
            "post_strategist_top10": post_strategist_top10,
            "reconstructed_pre_adjust_top10": scanner_evidence.get("reconstructed_pre_adjust_top10") or [],
            "raw_scanner_top10": raw_scanner_top10,
            "pre_strategist_full_universe_top20": list(
                pre_strategist_universe.get("intrinsic_ranked_top20") or []
            )[:20],
            "pre_strategist_source_universe": dict(
                pre_strategist_universe.get("source_universe_before_filters") or {}
            ),
            "raw_scanner_snapshot_source": (
                scanner_control.get("source")
                or scanner_context.get("raw_scanner_snapshot_source")
                or ""
            ),
            "raw_scanner_control_scope": str(scanner_control.get("scope") or ""),
            "raw_scanner_universe_control_available": bool(
                scanner_control.get("universe_control_available")
            ),
            "q9_decision_id": str(
                q9_snapshot.get("decision_id")
                or scanner_context.get("q9_decision_id")
                or ""
            ),
            "q9_snapshot_source": q9_snapshot_source,
            "commander_final": commander_final,
            "commander_final_explicit": bool(
                commander_final.get("decision_id")
                and (
                    commander_final.get("selected_symbol")
                    or commander_final.get("veto")
                    or commander_final.get("no_trade")
                )
            ),
            "selection_mismatch": (
                dict(scanner_context.get("selection_mismatch") or {})
                if isinstance(scanner_context.get("selection_mismatch"), dict)
                else {}
            ),
            "score_decomposition": {
                "raw_scanner_top1": decompose_scanner_score(raw_scanner_top1),
                "post_strategy_top1": decompose_scanner_score(post_strategy_top1),
                "selected_candidate": decompose_scanner_score(selected_candidate),
            },
            "strategist_playbook": (
                strategist_context.get("playbook")
                or scanner_evidence.get("playbook")
                or facts.get("playbook")
            ),
            "strategist_run_id": (
                strategist_selection.get("strategist_run_id")
                or strategist_context.get("entry_strategist_run_id")
            ),
        },
        "monitor": {
            "entry_context": monitor_context,
            "entry_reason": facts.get("entry_reason"),
            "exit_reason": facts.get("exit_reason"),
            "primary_blocker": facts.get("primary_blocker_if_no_buy"),
            **monitor_evidence,
            "post_exit": post_exit,
        },
        "baseline_versions": {
            "q9_contract": CONTRACT_VERSION,
            "q8_contract": str(scanner_context.get("q8_contract_version") or ""),
            "tactic_contract": str(
                ((legacy.get("provenance") or {}).get("field_sources") or {}).get("tactic_contract_version")
                if isinstance(legacy.get("provenance"), dict)
                else ""
            ),
            "strategist_prompt": str(strategist_context.get("prompt_version") or ""),
            "cost_model": str(
                monitor_context.get("cost_model_version")
                or monitor_context.get("broker_cost_profile_version")
                or ""
            ),
            "strategy_policy": str(
                ((legacy.get("provenance") or {}).get("field_sources") or {}).get("strategy_policy_source")
                if isinstance(legacy.get("provenance"), dict)
                else ""
            ),
        },
        "integrity": {
            "status": integrity.value,
            "defects": defects,
            "watch_items": watch_items,
            "required_artifact_complete": inventory["complete"],
            "closeout_broker_reconciliation": {
                "status": (
                    "skipped_but_existing_broker_truth_available"
                    if closeout_broker_skip and existing_broker_truth
                    else "skipped_unresolved"
                    if closeout_broker_skip
                    else "not_flagged"
                ),
                **closeout_broker_skip,
            },
        },
        "provenance": {
            "trade_dir": str(trade_dir),
            "legacy_read_model_schema": ((legacy.get("provenance") or {}).get("schema_version") if isinstance(legacy.get("provenance"), dict) else ""),
            "field_sources": ((legacy.get("provenance") or {}).get("field_sources") if isinstance(legacy.get("provenance"), dict) else {}),
        },
    }
