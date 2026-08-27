from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes


Q9_DECISION_SCHEMA = "q9_decision_windows.v1"
_KRX_SYMBOL_RE = re.compile(r"^\d{6}$")


def _synthetic_identity(row: dict[str, Any]) -> bool:
    identity = " ".join(
        str(row.get(key) or "").lower()
        for key in ("decision_id", "q9_decision_id", "run_id", "candidate_pool_id")
    )
    if any(marker in identity for marker in ("test", "fixture", "synthetic")):
        return True
    symbols: list[str] = []

    def collect(value: Any, *, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = (*path, str(key))
                if key in {
                    "symbol",
                    "ticker",
                    "selected_symbol",
                    "top1_symbol",
                    "candidate_symbol",
                } and not any(
                    part == "layer_packet_ids" or part.endswith("_packet_ids")
                    for part in path
                ):
                    text = str(child or "").strip()
                    if text:
                        symbols.append(text)
                elif isinstance(child, (dict, list)):
                    collect(child, path=child_path)
        elif isinstance(value, list):
            for child in value:
                collect(child, path=path)

    collect(row)
    return any(not _KRX_SYMBOL_RE.fullmatch(symbol) for symbol in symbols)


def _regular_session_window(row: dict[str, Any]) -> bool:
    parsed = _parse_window_kst(row.get("generated_at"))
    if parsed is None:
        return True
    return (9, 0) <= (parsed.hour, parsed.minute) <= (15, 30)


def is_synthetic_evaluation_row(row: dict[str, Any]) -> bool:
    return _synthetic_identity(row)


def is_regular_session_evaluation_row(row: dict[str, Any]) -> bool:
    return _regular_session_window(row)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def iter_trade_dirs(reports_root: Path, day: str) -> list[Path]:
    root = Path(reports_root) / "trades" / day
    if not root.exists():
        return []
    return sorted({path.parent for path in root.rglob("lifecycle_bundle.json")})


def _record(path: Path, *, required: bool) -> dict[str, Any]:
    exists = path.exists()
    payload = read_json(path) if exists and path.suffix.lower() == ".json" else {}
    return {
        "path": str(path),
        "required": required,
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
        "modified_epoch": path.stat().st_mtime if exists else None,
        "schema_version": str(payload.get("schema_version") or ""),
        "evidence_status": str(payload.get("evidence_status") or ""),
        "forward_windows_complete": bool(payload.get("forward_windows_complete")),
        "missing_reason": "" if exists else "artifact_not_found",
    }


def _q9_daily_diagnostics(reports_root: Path, day: str, record: dict[str, Any]) -> dict[str, Any]:
    path = Path(record.get("path") or "")
    payload = read_json(path) if path.exists() else {}
    windows = [row for row in payload.get("windows") or [] if isinstance(row, dict)]
    scanner_windows = [row for row in windows if isinstance(row.get("scanner_control"), dict)]
    synthetic_windows = [row for row in scanner_windows if _synthetic_identity(row)]
    post_session_windows = [
        row
        for row in scanner_windows
        if row not in synthetic_windows and not _regular_session_window(row)
    ]
    trusted_scanner_windows = [
        row
        for row in scanner_windows
        if row not in synthetic_windows and row not in post_session_windows
    ]
    shadow_root = Path(reports_root).parent / "data" / "logs" / "quant_shadow_candidates" / day
    shadow_payloads: list[dict[str, Any]] = []
    if shadow_root.exists():
        for shadow_path in sorted(shadow_root.glob("*.json")):
            if shadow_path.name == "latest.json":
                continue
            shadow = read_json(shadow_path)
            if shadow:
                shadow_payloads.append(shadow)
    pre_rows: list[dict[str, Any]] = []
    for shadow in shadow_payloads:
        generated_at = str(shadow.get("generated_at") or "")
        for raw in shadow.get("q9_decision_candidates") or []:
            if (
                not isinstance(raw, dict)
                or str(raw.get("q9_decision_role") or "")
                != "P_SCANNER_PRE_STRATEGIST_UNIVERSE"
            ):
                continue
            row = dict(raw)
            row.setdefault("_payload_generated_at", generated_at)
            if _synthetic_identity(row) or not _regular_session_window(
                {"generated_at": generated_at}
            ):
                continue
            pre_rows.append(row)
    observed_rows = attach_forward_outcomes(pre_rows) if pre_rows else []
    forward_observed = sum(
        1
        for row in observed_rows
        if bool((row.get("shadow_forward_outcome") or {}).get("available"))
    )
    forward_pending = 0
    forward_unavailable = 0
    forward_invalid = 0
    forward_reason_counts: Counter[str] = Counter()
    for row in observed_rows:
        outcome = row.get("shadow_forward_outcome")
        outcome = outcome if isinstance(outcome, dict) else {}
        if outcome.get("available"):
            continue
        reason = str(outcome.get("reason") or "")
        forward_reason_counts[reason or "checkpoint_status_only"] += 1
        checkpoints = outcome.get("checkpoints")
        checkpoints = checkpoints if isinstance(checkpoints, dict) else {}
        statuses = {
            str(checkpoint.get("status") or "")
            for checkpoint in checkpoints.values()
            if isinstance(checkpoint, dict)
        }
        if reason in {"", "forward_window_pending"} and statuses <= {"", "pending"}:
            forward_pending += 1
        elif reason in {
            "baseline_or_minute_rows_unavailable",
            "baseline_unavailable",
            "minute_rows_unavailable",
        }:
            forward_unavailable += 1
        else:
            forward_invalid += 1
    window_times = [
        parsed
        for parsed in (
            _parse_window_kst(row.get("generated_at"))
            for row in trusted_scanner_windows
        )
        if parsed is not None
    ]
    shadow_times = [
        parsed
        for parsed in (
            _parse_window_kst(row.get("generated_at"))
            for row in shadow_payloads
            if row.get("q9_decision_candidates")
        )
        if parsed is not None
    ]
    first_window = min(window_times) if window_times else None
    last_window = max(window_times) if window_times else None
    last_runtime_evidence = max(window_times + shadow_times) if (window_times or shadow_times) else None
    closeout = read_json(Path(reports_root) / "operator_summary" / "daily" / day / "closeout_maintenance.json")
    closeout_steps = closeout.get("steps") if isinstance(closeout.get("steps"), dict) else {}
    residual = closeout_steps.get("closeout_residual_position_reconciliation")
    residual = residual if isinstance(residual, dict) else {}
    account_snapshot = closeout_steps.get("account_snapshot")
    account_snapshot = account_snapshot if isinstance(account_snapshot, dict) else {}
    post_close_account_ok = bool(
        closeout.get("ok")
        and account_snapshot.get("ok")
        and residual.get("ok")
        and not residual.get("requires_next_open_flatten")
    )
    late_session_runtime_evidence = bool(
        last_runtime_evidence
        and (last_runtime_evidence.hour, last_runtime_evidence.minute) >= (15, 10)
    )
    closeout_trigger = str(closeout.get("trigger") or "")
    closeout_trigger_ok = bool(
        closeout_trigger.startswith("kiwoom_market_status_")
        or (
            closeout_trigger
            and post_close_account_ok
            and late_session_runtime_evidence
        )
    )
    time_coverage_ok = bool(
        first_window
        and last_runtime_evidence
        and (first_window.hour, first_window.minute) <= (9, 10)
        and late_session_runtime_evidence
    )
    post_close_override = bool(
        first_window
        and (first_window.hour, first_window.minute) <= (9, 10)
        and post_close_account_ok
        and closeout_trigger_ok
    )
    record.update(
        {
            "expected_schema_version": Q9_DECISION_SCHEMA,
            "schema_match": bool(record.get("schema_version") == Q9_DECISION_SCHEMA),
            "window_count": len(windows),
            "scanner_selection_window_count": len(trusted_scanner_windows),
            "complete_abc_window_count": sum(
                1
                for row in trusted_scanner_windows
                if isinstance(row.get("strategist_selection"), dict)
                and isinstance(row.get("commander_final"), dict)
            ),
            "complete_pabc_window_count": sum(
                1
                for row in trusted_scanner_windows
                if isinstance(row.get("scanner_pre_strategist_universe"), dict)
                and isinstance(row.get("scanner_control"), dict)
                and isinstance(row.get("strategist_selection"), dict)
                and isinstance(row.get("commander_final"), dict)
            ),
            "pre_strategist_universe_window_count": sum(
                1
                for row in trusted_scanner_windows
                if isinstance(row.get("scanner_pre_strategist_universe"), dict)
                and bool(
                    (row.get("scanner_pre_strategist_universe") or {}).get("intrinsic_ranked_top20")
                )
            ),
            "missing_selected_candidate_count": sum(
                1
                for row in trusted_scanner_windows
                if bool((row.get("strategist_selection") or {}).get("post_strategist_top10"))
                and not str((row.get("strategist_selection") or {}).get("selected_symbol") or "")
            ),
            "synthetic_window_count": len(synthetic_windows),
            "post_session_window_count": len(post_session_windows),
            "first_scanner_window_kst": first_window.isoformat() if first_window else "",
            "last_scanner_window_kst": last_window.isoformat() if last_window else "",
            "last_q9_runtime_evidence_kst": (
                last_runtime_evidence.isoformat() if last_runtime_evidence else ""
            ),
            "session_coverage_source": (
                "post_close_account_snapshot_override"
                if post_close_override and not time_coverage_ok
                else
                "scanner_selection_plus_q9_shadow_runtime"
                if last_runtime_evidence and last_runtime_evidence != last_window
                else "scanner_selection"
            ),
            "full_session_coverage": bool(time_coverage_ok or post_close_override),
            "post_close_account_snapshot_coverage": bool(post_close_override),
            "post_close_account_snapshot_ok": bool(post_close_account_ok),
            "post_close_trigger": closeout_trigger,
            "late_session_runtime_evidence": bool(late_session_runtime_evidence),
            "shadow_payload_count": len(shadow_payloads),
            "pre_strategist_forward_candidate_count": len(pre_rows),
            "forward_observed_candidate_count": forward_observed,
            "forward_missing_candidate_count": max(0, len(pre_rows) - forward_observed),
            "forward_pending_candidate_count": forward_pending,
            "forward_unavailable_candidate_count": forward_unavailable,
            "forward_invalid_candidate_count": forward_invalid,
            "forward_outcome_reason_counts": dict(forward_reason_counts),
        }
    )
    return record


def _parse_window_kst(value: Any):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed.astimezone(ZoneInfo("Asia/Seoul"))


def inventory_trade(trade_dir: Path) -> dict[str, Any]:
    paths: Iterable[tuple[str, Path, bool]] = (
        ("lifecycle_bundle", trade_dir / "lifecycle_bundle.json", True),
        ("entry", trade_dir / "entry.json", True),
        ("exit", trade_dir / "exit.json", False),
        ("scanner_evidence", trade_dir / "evidence" / "scanner_evidence.json", True),
        ("strategist_evidence", trade_dir / "evidence" / "strategist_evidence.json", True),
        ("commander_evidence", trade_dir / "evidence" / "commander_evidence.json", True),
        ("monitor_evidence", trade_dir / "evidence" / "monitor_evidence.json", True),
        ("ai_trade_summary", trade_dir / "reports" / "ai_trade_summary.json", False),
        ("post_exit_shadow", trade_dir / "reports" / "post_exit_shadow.json", False),
    )
    artifacts = {name: _record(path, required=required) for name, path, required in paths}
    missing_required = [name for name, row in artifacts.items() if row["required"] and not row["exists"]]
    return {
        "trade_dir": str(trade_dir),
        "trade_id": trade_dir.name,
        "artifacts": artifacts,
        "missing_required": missing_required,
        "complete": not missing_required,
    }


def build_artifact_inventory(reports_root: Path, day: str) -> dict[str, Any]:
    trades = [inventory_trade(path) for path in iter_trade_dirs(reports_root, day)]
    daily_root = Path(reports_root) / "operator_summary" / "daily" / day
    daily = {
        name: _record(daily_root / filename, required=required)
        for name, filename, required in (
            ("daily_summary", "daily_summary.json", True),
            ("operator_summary", "operator_summary.json", False),
            ("q8_shadow_blocker_review", "q8_shadow_blocker_review.json", True),
            ("closeout_maintenance", "closeout_maintenance.json", False),
            ("q9_decision_windows", "q9_decision_windows.json", False),
        )
    }
    daily["q9_vs_samsung_hynix_comparison"] = _record(
        Path(reports_root)
        / "evaluation"
        / "baseline_samsung_hynix"
        / day
        / "q9_vs_samsung_hynix_daily_comparison.json",
        required=False,
    )
    daily["q9_decision_windows"] = _q9_daily_diagnostics(
        reports_root,
        day,
        daily["q9_decision_windows"],
    )
    required_count = sum(
        1 for trade in trades for row in trade["artifacts"].values() if row["required"]
    ) + sum(1 for row in daily.values() if row["required"])
    present_required_count = sum(
        1 for trade in trades for row in trade["artifacts"].values() if row["required"] and row["exists"]
    ) + sum(1 for row in daily.values() if row["required"] and row["exists"])
    return {
        "schema_version": "artifact_inventory.v1",
        "day": day,
        "trade_count": len(trades),
        "required_artifact_count": required_count,
        "present_required_artifact_count": present_required_count,
        "required_coverage": round(present_required_count / required_count, 4) if required_count else 0.0,
        "trades": trades,
        "daily_artifacts": daily,
    }
