from __future__ import annotations

import calendar
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from libs.performance.strategy_memory import sync_strategy_memory_artifacts
from libs.reporting.llm_artifacts import (
    canonical_trade_day_root,
    daily_artifact_paths,
    find_trade_dir,
    monthly_artifact_paths,
    operator_summary_artifact_root,
    symbol_artifact_paths,
    weekly_artifact_paths,
)
from libs.reporting.quant_tactic_evaluation import (
    build_quant_tactic_evaluation,
    render_quant_tactic_evaluation_lines,
)
from libs.reporting.quant_shadow_candidate_evaluation import (
    build_quant_shadow_candidate_evaluation,
    load_quant_shadow_candidate_payloads,
    load_quant_shadow_candidate_payloads_for_range,
    render_quant_shadow_candidate_evaluation_lines,
)
from libs.reporting.quant_tactic_report import quant_tactic_surface as build_quant_tactic_surface
from libs.reporting.strategist_llm_evaluation import (
    build_strategist_llm_evaluation,
    render_strategist_llm_evaluation_lines,
)


_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text_value(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "-", "none", "null", "unknown", "not_captured"}:
        return ""
    return text


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text_value(value)
        if text:
            return text
    return ""


def _dig(source: Dict[str, Any], *keys: str) -> Any:
    current: Any = source
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _find_key_recursive(source: Any, key: str, *, max_nodes: int = 800) -> Any:
    seen = 0
    stack = [source]
    while stack and seen < max_nodes:
        current = stack.pop()
        seen += 1
        if isinstance(current, dict):
            if key in current and current.get(key) not in (None, ""):
                return current.get(key)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return None


def _score_bucket(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return ""
    if parsed >= 0.75:
        return ">=0.75"
    if parsed >= 0.60:
        return "0.60-0.75"
    if parsed >= 0.50:
        return "0.50-0.60"
    return "<0.50"


def _pct_bucket(value: Any) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return ""
    if parsed >= 0.012:
        return ">=1.20%"
    if parsed >= 0.006:
        return "0.60-1.20%"
    if parsed >= 0.0:
        return "0.00-0.60%"
    return "<0.00%"


def _rank_bucket(value: Any) -> str:
    parsed = _safe_int(value, default=0)
    if parsed <= 0:
        return ""
    if parsed == 1:
        return "rank1"
    if parsed <= 3:
        return "rank2-3"
    if parsed <= 10:
        return "rank4-10"
    return "rank>10"


def _bool_bucket(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return "true"
    if text in {"false", "0", "no", "n"}:
        return "false"
    return ""


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _first_recursive_dict(*roots: Any, key: str) -> Dict[str, Any]:
    for root in roots:
        found = _find_key_recursive(root, key)
        if isinstance(found, dict) and found:
            return dict(found)
    return {}


def _first_nonempty_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _first_reason_bucket(values: Any) -> str:
    rows = _first_nonempty_list(values)
    return rows[0] if rows else ""


def _confirmation_bucket(value: Any) -> str:
    if isinstance(value, bool):
        return "pending" if value else "not_pending"
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "pending"}:
        return "pending"
    if text in {"false", "0", "no", "not_pending"}:
        return "not_pending"
    return ""


def _mismatch_bucket(value: Any) -> str:
    if isinstance(value, bool):
        return "mismatch" if value else "aligned_or_unknown"
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "mismatch"}:
        return "mismatch"
    if text in {"false", "0", "no", "aligned_or_unknown"}:
        return "aligned_or_unknown"
    return ""


_UNAVAILABLE_PNL_VALUES = {"", "-", "none", "null", "unavailable", "not_available"}


def _is_unavailable_pnl(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in _UNAVAILABLE_PNL_VALUES


def _ratio_to_pct(value: Any) -> float | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return float(parsed) * 100.0


def _truth_surface_candidate_paths(row: Dict[str, Any], reports_root: Path) -> List[Path]:
    candidates: List[Path] = []
    for key in ("trade_root_path",):
        raw = str(row.get(key) or "").strip()
        if raw:
            candidates.append(Path(raw) / "reports" / "ai_trade_summary_input.json")
            candidates.append(Path(raw) / "reports" / "ai_trade_summary.json")
    report_path = str(row.get("report_path") or "").strip()
    if report_path:
        report_dir = Path(report_path).parent
        candidates.append(report_dir / "ai_trade_summary_input.json")
        candidates.append(report_dir / "ai_trade_summary.json")
    lifecycle_path = str(row.get("lifecycle_bundle_path") or "").strip()
    if lifecycle_path:
        trade_root = Path(lifecycle_path).parent
        candidates.append(trade_root / "reports" / "ai_trade_summary_input.json")
        candidates.append(trade_root / "reports" / "ai_trade_summary.json")
    trade_id = str(row.get("trade_id") or "").strip()
    day = str(row.get("date") or row.get("day") or "").strip()[:10]
    if trade_id and day:
        trade_root = find_trade_dir(canonical_trade_day_root(Path(reports_root), day), trade_id)
        if trade_root is None:
            trade_root = Path(reports_root) / "trades" / day / trade_id
        candidates.append(trade_root / "reports" / "ai_trade_summary_input.json")
        candidates.append(trade_root / "reports" / "ai_trade_summary.json")
    out: List[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _extract_truth_surface_metrics(row: Dict[str, Any], reports_root: Path) -> Dict[str, Any]:
    for path in _truth_surface_candidate_paths(row, reports_root):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        truth = payload.get("truth_surface") if isinstance(payload.get("truth_surface"), dict) else {}
        if not truth:
            continue
        pnl_raw = truth.get("pnl")
        pnl = None if _is_unavailable_pnl(pnl_raw) else _safe_float(pnl_raw)
        pnl_pct = _ratio_to_pct(truth.get("pnl_pct"))
        cost = truth.get("cost_analysis") if isinstance(truth.get("cost_analysis"), dict) else {}
        price_move_pct = _ratio_to_pct(cost.get("price_move_pct"))
        observed_pct = pnl_pct if pnl is None else None
        return {
            "truth_surface_available": True,
            "truth_surface_path": str(path),
            "truth_result_label": str(truth.get("result_label") or ""),
            "truth_source": str(truth.get("truth_source") or ""),
            "truth_net_pnl": pnl,
            "truth_net_return_pct": pnl_pct if pnl is not None else None,
            "truth_observed_return_pct": observed_pct,
            "truth_price_move_pct": price_move_pct,
            "truth_cost_drag_pct": _ratio_to_pct(cost.get("cost_drag_pct")),
            "truth_breakeven_move_pct": _ratio_to_pct(cost.get("breakeven_move_pct")),
        }
    return {"truth_surface_available": False}


def _state_snapshot_candidate_paths(reports_root: Path) -> List[Path]:
    candidates: List[Path] = []
    raw = str(os.getenv("STATE_STORE_PATH") or "").strip()
    if raw:
        candidates.append(Path(raw))
    candidates.append(Path(reports_root).parent / "data" / "state.json")
    out: List[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _load_state_snapshot(reports_root: Path) -> Tuple[Dict[str, Any], str]:
    for path in _state_snapshot_candidate_paths(reports_root):
        payload = _read_json(path)
        if isinstance(payload, dict):
            return payload, str(path)
    return {}, ""


def _normalize_symbol_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("A") and len(text) == 7:
        text = text[1:]
    return text


def _latest_account_snapshot_path(reports_root: Path, day: str | None) -> Path:
    return Path(reports_root).parent / "data" / "logs" / "kiwoom_account_snapshots" / str(day or "").strip() / "latest.json"


def _snapshot_position_symbols(snapshot: Dict[str, Any]) -> set[str]:
    symbols: set[str] = set()
    for call in list(snapshot.get("calls") or []):
        if not isinstance(call, dict):
            continue
        api_id = str(call.get("api_id") or "").strip()
        payload = call.get("payload") if isinstance(call.get("payload"), dict) else {}
        rows: List[Any] = []
        if api_id == "kt00018":
            rows = list(payload.get("acnt_evlt_remn_indv_tot") or [])
        elif api_id == "kt00004":
            rows = list(payload.get("stk_acnt_evlt_prst") or [])
        else:
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = _normalize_symbol_code(row.get("stk_cd"))
            qty = _safe_int(row.get("rmnd_qty"))
            if symbol and qty > 0:
                symbols.add(symbol)
    return symbols


def _account_snapshot_closeout_reconciliation(reports_root: Path, day: str | None) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()[:10]
    path = _latest_account_snapshot_path(reports_root, normalized_day)
    snapshot = _read_json(path)
    if not isinstance(snapshot, dict):
        return {"available": False, "reason": "account_snapshot_missing", "path": str(path)}
    generated_at = str(snapshot.get("generated_at") or "").strip()
    generated_dt = _iso_to_kst_dt(generated_at)
    generated_day = generated_dt.strftime("%Y-%m-%d") if generated_dt is not None else ""
    after_closeout_window = False
    if generated_dt is not None:
        closeout_start = generated_dt.replace(hour=15, minute=20, second=0, microsecond=0)
        after_closeout_window = bool(generated_dt >= closeout_start)
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    ok_count = _safe_int(summary.get("ok_count"))
    error_count = _safe_int(summary.get("error_count"))
    api_call_count = _safe_int(summary.get("api_call_count"))
    positions = _snapshot_position_symbols(snapshot)
    fresh = bool(
        normalized_day
        and generated_day == normalized_day
        and after_closeout_window
        and api_call_count > 0
        and ok_count > 0
    )
    return {
        "available": True,
        "fresh_after_closeout_window": fresh,
        "path": str(path),
        "snapshot_path": str(snapshot.get("path") or path),
        "generated_at": generated_at,
        "generated_at_kst": generated_dt.strftime("%Y-%m-%d %H:%M:%S KST") if generated_dt is not None else "",
        "generated_day_kst": generated_day,
        "after_closeout_window": after_closeout_window,
        "api_call_count": api_call_count,
        "ok_count": ok_count,
        "error_count": error_count,
        "position_symbols": sorted(positions),
        "position_count": len(positions),
    }


def _residual_position_status(row: Dict[str, Any], decision: Dict[str, Any], closeout: Dict[str, Any]) -> str:
    symbol = str(row.get("symbol") or "").strip().upper()
    action = str(decision.get("action") or "").strip()
    if bool(decision.get("approved")) and action == "carry_overnight":
        if _decision_is_weekend_carry(decision):
            return "주말 오버나이트 승인(주의)"
        return "오버나이트 승인"
    if action == "flatten_before_close":
        return "장마감 정리 지시"
    unresolved = {str(x or "").strip().upper() for x in list(closeout.get("unresolved_flatten_symbols") or [])}
    flattened = {str(x or "").strip().upper() for x in list(closeout.get("flattened_symbols") or [])}
    if symbol in unresolved:
        return "정리 필요"
    if symbol in flattened:
        return "정리 불일치"
    return "잔여 보유"


def _decision_is_weekend_carry(decision: Dict[str, Any]) -> bool:
    if bool(decision.get("weekend_carry")):
        return True
    calendar_ctx = decision.get("carry_calendar") if isinstance(decision.get("carry_calendar"), dict) else {}
    if bool(calendar_ctx.get("weekend_carry")):
        return True
    epoch = _safe_int(decision.get("decided_at_epoch"))
    if epoch <= 0:
        return False
    kst = timezone(timedelta(hours=9))
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(kst).weekday() == 4
    except Exception:
        return False


def _epoch_to_kst_text(epoch: Any) -> str:
    value = _safe_int(epoch)
    if value <= 0:
        return ""
    try:
        kst = timezone(timedelta(hours=9))
        return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(kst).strftime("%Y-%m-%d %H:%M:%S KST")
    except Exception:
        return ""


def _iso_to_kst_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=9)))


def _iso_to_kst_text(value: Any) -> str:
    dt = _iso_to_kst_dt(value)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S KST")


def _closeout_state_metadata(closeout: Dict[str, Any], day: str | None) -> Dict[str, Any]:
    applied_at = str(closeout.get("applied_at") or "").strip()
    applied_raw = closeout.get("applied")
    applied_known = isinstance(applied_raw, bool)
    applied = bool(applied_raw) if applied_known else False
    applied_at_kst = _iso_to_kst_text(applied_at)
    applied_day = ""
    dt = _iso_to_kst_dt(applied_at)
    if dt is not None:
        applied_day = dt.strftime("%Y-%m-%d")
    normalized_day = str(day or "").strip()
    stale = bool(normalized_day and applied_day and applied_day != normalized_day)

    note_parts: List[str] = []
    if applied_at_kst:
        if applied_known:
            note_parts.append("적용" if applied else "미적용")
        note_parts.append(f"기록시각 {applied_at_kst}")
    if stale:
        note_parts.append(f"당일({normalized_day}) 오버나이트 판단 근거 아님")
    return {
        "applied": applied,
        "applied_at_kst": applied_at_kst,
        "applied_day_kst": applied_day,
        "stale_for_day": stale,
        "report_note": "; ".join(note_parts),
    }


def _overnight_missing_context(raw_row: Dict[str, Any], monitor_state: Dict[str, Any]) -> Dict[str, Any]:
    position_entry_text = _epoch_to_kst_text(raw_row.get("position_entry_epoch"))
    if not isinstance(monitor_state, dict) or not monitor_state:
        out: Dict[str, Any] = {
            "overnight_missing_reason_code": "no_monitor_state_for_residual_position",
            "overnight_missing_detail": "모니터 상태 기록 없음; EOD 전체 보유 종목 재점검 필요",
            "overnight_decision_status": "missing",
            "overnight_decision_label": "미수행(모니터 상태 기록 없음)",
        }
        if position_entry_text:
            out["position_entry_at_kst"] = position_entry_text
        return out

    updated_epoch = _safe_int(monitor_state.get("updated_at_epoch"))
    updated_text = _epoch_to_kst_text(updated_epoch)
    posture = str(monitor_state.get("posture") or "").strip()
    monitor_reason = str(monitor_state.get("reason") or "").strip()
    entry_state = monitor_state.get("entry_state") if isinstance(monitor_state.get("entry_state"), dict) else {}
    blocking_axis = str(entry_state.get("current_blocking_axis") or "").strip()
    detail_parts: List[str] = []
    if updated_text:
        detail_parts.append(f"마지막 모니터 {updated_text}")
    if posture or monitor_reason:
        detail_parts.append(f"마지막 판단 {posture or '-'}({monitor_reason or '-'})")
    if blocking_axis:
        detail_parts.append(f"차단축 {blocking_axis}")

    reason_code = "no_persisted_overnight_decision"
    decision_label = "미확인(오버나이트 판단 저장 기록 없음)"
    if updated_epoch > 0:
        try:
            kst = timezone(timedelta(hours=9))
            updated_dt = datetime.fromtimestamp(updated_epoch, tz=timezone.utc).astimezone(kst)
            eod_window_start = updated_dt.replace(hour=15, minute=20, second=0, microsecond=0)
            market_close = updated_dt.replace(hour=15, minute=30, second=0, microsecond=0)
            if updated_dt < eod_window_start:
                reason_code = "last_monitor_before_eod_window_no_later_review"
                decision_label = "미수행(15:20 이후 재점검 없음)"
                detail_parts.append("EOD 판단창(15:20 이후) 재점검 없음")
            elif updated_dt <= market_close:
                reason_code = "last_monitor_inside_eod_window_without_persisted_decision"
                decision_label = "기록 누락 가능(EOD 판단창 내 저장 없음)"
                detail_parts.append("EOD 판단창 내 평가 기록 저장 누락 가능")
            else:
                reason_code = "last_monitor_after_market_close_without_persisted_decision"
                decision_label = "기록 누락 가능(장마감 후 저장 없음)"
                detail_parts.append("장마감 후 평가 기록 저장 누락 가능")
        except Exception:
            pass

    out = {
        "overnight_missing_reason_code": reason_code,
        "overnight_missing_detail": " / ".join(detail_parts) if detail_parts else "오버나이트 판단 저장 기록 없음",
        "overnight_decision_status": "missing",
        "overnight_decision_label": decision_label,
        "last_monitor_updated_at_epoch": updated_epoch if updated_epoch > 0 else None,
        "last_monitor_updated_at_kst": updated_text,
        "last_monitor_posture": posture,
        "last_monitor_reason": monitor_reason,
        "last_monitor_blocking_axis": blocking_axis,
    }
    if position_entry_text:
        out["position_entry_at_kst"] = position_entry_text
    return out


_FLATTEN_BEFORE_CLOSE_ACTIONS = {
    "closeout_flatten",
    "eod_flat",
    "flatten_before_close",
    "force_exit",
    "sell_before_close",
}


def _overnight_recorded_context(decision: Dict[str, Any]) -> Dict[str, Any]:
    action = str(decision.get("action") or "").strip()
    approved = bool(decision.get("approved"))
    if approved and action == "carry_overnight":
        status = "approved"
        label = "수행됨(오버나이트 승인)"
    elif action in _FLATTEN_BEFORE_CLOSE_ACTIONS:
        status = "flatten_requested"
        label = "수행됨(장마감 전 정리 지시)"
    elif action:
        status = "recorded"
        label = f"수행됨({action})"
    else:
        status = "recorded"
        label = "수행됨(결정 기록 있음)"
    return {
        "overnight_decision_status": status,
        "overnight_decision_label": label,
    }


def _price_matches(left: Any, right: Any) -> bool:
    left_value = _safe_float(left)
    right_value = _safe_float(right)
    if left_value is None or right_value is None or left_value <= 0 or right_value <= 0:
        return False
    tolerance = max(1.0, abs(left_value) * 0.001)
    return abs(left_value - right_value) <= tolerance


def _same_day_flatten_reconciliation(
    *,
    reports_root: Path,
    day: str | None,
    symbol: str,
    qty: int,
    avg_price: Any,
) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_day or not normalized_symbol or qty <= 0:
        return {}
    day_root = Path(reports_root) / "trades" / normalized_day
    if not day_root.exists():
        return {}

    day_token = normalized_day.replace("-", "")
    pattern = f"TRD_{day_token}_{normalized_symbol}_*/lifecycle_bundle.json"
    for path in sorted(day_root.rglob(pattern)):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
        exit_row = payload.get("exit") if isinstance(payload.get("exit"), dict) else {}
        if str(exit_row.get("action") or "").strip().upper() != "SELL":
            continue
        entry_qty = _safe_int(entry.get("qty"))
        exit_qty = _safe_int(exit_row.get("qty"))
        if entry_qty < qty or exit_qty < qty:
            continue
        entry_price = entry.get("price")
        if _safe_float(avg_price) is not None and not _price_matches(avg_price, entry_price):
            continue
        return {
            "symbol": normalized_symbol,
            "trade_id": str(payload.get("trade_id") or path.parent.name),
            "lifecycle_bundle_path": str(path),
            "reason": "same_day_lifecycle_full_sell_after_flatten_decision",
            "exit_reason": str(exit_row.get("reason_human") or ""),
            "exit_ts": str(exit_row.get("ts") or ""),
            "exit_qty": exit_qty,
        }
    return {}


def _sell_guard_candidate_paths(*, reports_root: Path, state_path: str) -> List[Path]:
    candidates: List[Path] = []
    state_raw = str(state_path or "").strip()
    if state_raw:
        state_file = Path(state_raw)
        candidates.append(state_file.parent / "state" / "execution_recent_sell_guard.json")
    candidates.append(Path(reports_root).parent / "data" / "state" / "execution_recent_sell_guard.json")
    out: List[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _epoch_day_kst(epoch: Any) -> str:
    value = _safe_int(epoch)
    if value <= 0:
        return ""
    try:
        kst = timezone(timedelta(hours=9))
        return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(kst).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _same_day_sell_guard_reconciliation(
    *,
    reports_root: Path,
    state_path: str,
    day: str | None,
    symbol: str,
    qty: int,
) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_day or not normalized_symbol or qty <= 0:
        return {}
    for path in _sell_guard_candidate_paths(reports_root=reports_root, state_path=state_path):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        orders = payload.get("orders") if isinstance(payload.get("orders"), dict) else {}
        row = orders.get(normalized_symbol) if isinstance(orders.get(normalized_symbol), dict) else {}
        if not row:
            continue
        if _epoch_day_kst(row.get("last_sell_epoch")) != normalized_day:
            continue
        remaining_hint = _safe_int(row.get("remaining_qty_hint"), default=-1)
        last_sell_qty = _safe_int(row.get("last_sell_qty"))
        position_qty_hint = _safe_int(row.get("position_qty_hint"))
        if remaining_hint == 0 and max(last_sell_qty, position_qty_hint) >= qty:
            return {
                "symbol": normalized_symbol,
                "trade_id": str(row.get("run_id") or ""),
                "lifecycle_bundle_path": "",
                "reason": "same_day_sell_guard_remaining_zero",
                "exit_reason": "recent sell guard reports remaining_qty_hint=0",
                "exit_ts": _epoch_to_kst_text(row.get("last_sell_epoch")),
                "exit_qty": last_sell_qty,
                "source_path": str(path),
            }
    return {}


def _build_residual_positions_payload(*, reports_root: Path, day: str | None = None) -> Dict[str, Any]:
    state, state_path = _load_state_snapshot(reports_root)
    if not state:
        return {
            "available": False,
            "source": "state_snapshot",
            "source_path": "",
            "position_count": 0,
            "positions": [],
        }

    raw_positions = state.get("mock_positions") if isinstance(state.get("mock_positions"), list) else []
    overnight = (
        state.get("overnight_decision_by_symbol")
        if isinstance(state.get("overnight_decision_by_symbol"), dict)
        else {}
    )
    closeout = state.get("closeout_backup_liquidation") if isinstance(state.get("closeout_backup_liquidation"), dict) else {}
    monitor_states = (
        state.get("monitor_last_state_by_symbol")
        if isinstance(state.get("monitor_last_state_by_symbol"), dict)
        else {}
    )
    account_snapshot_reconciliation = _account_snapshot_closeout_reconciliation(reports_root, day)
    account_snapshot_positions = {
        str(item or "").strip().upper()
        for item in list(account_snapshot_reconciliation.get("position_symbols") or [])
        if str(item or "").strip()
    }
    account_snapshot_fresh = bool(account_snapshot_reconciliation.get("fresh_after_closeout_window"))
    positions: List[Dict[str, Any]] = []
    reconciled_closed: List[Dict[str, Any]] = []
    for raw_row in raw_positions:
        if not isinstance(raw_row, dict):
            continue
        symbol = str(raw_row.get("symbol") or "").strip().upper()
        qty = _safe_int(raw_row.get("qty"))
        if not symbol or qty <= 0:
            continue
        if account_snapshot_fresh and symbol not in account_snapshot_positions:
            reconciled_closed.append(
                {
                    "symbol": symbol,
                    "trade_id": "",
                    "lifecycle_bundle_path": "",
                    "reason": "fresh_account_snapshot_position_absent_after_closeout",
                    "exit_reason": "latest Kiwoom account snapshot has no remaining position after 15:20 closeout window",
                    "exit_ts": str(account_snapshot_reconciliation.get("generated_at_kst") or ""),
                    "exit_qty": qty,
                    "source_path": str(account_snapshot_reconciliation.get("snapshot_path") or ""),
                }
            )
            continue
        sell_guard_reconciliation = _same_day_sell_guard_reconciliation(
            reports_root=reports_root,
            state_path=state_path,
            day=day,
            symbol=symbol,
            qty=qty,
        )
        if sell_guard_reconciliation:
            reconciled_closed.append(sell_guard_reconciliation)
            continue
        decision = overnight.get(symbol) if isinstance(overnight.get(symbol), dict) else {}
        action = str(decision.get("action") or "").strip()
        if action in _FLATTEN_BEFORE_CLOSE_ACTIONS:
            reconciliation = _same_day_flatten_reconciliation(
                reports_root=reports_root,
                day=day,
                symbol=symbol,
                qty=qty,
                avg_price=raw_row.get("avg_price"),
            )
            if reconciliation:
                reconciled_closed.append(reconciliation)
                continue
        weekend_carry = _decision_is_weekend_carry(decision)
        reason = str(decision.get("reason") or "").strip()
        if not reason and not decision:
            reason = "오버나이트 판단 기록 없음"
        row = {
            "symbol": symbol,
            "qty": qty,
            "avg_price": _safe_float(raw_row.get("avg_price")),
            "current_price": _safe_float(raw_row.get("current_price")),
            "unrealized_pnl": _safe_float(raw_row.get("unrealized_pnl")),
            "account_pnl_ratio": _safe_float(raw_row.get("account_pnl_ratio")),
            "status": _residual_position_status(raw_row, decision, closeout),
            "overnight_action": action,
            "overnight_reason": reason,
            "overnight_decision_missing": not bool(decision),
            "weekend_carry": bool(weekend_carry),
            "allow_weekend_carry": bool(decision.get("allow_weekend_carry")),
            "holding_gap_days": _safe_int(decision.get("holding_gap_days"), default=3 if weekend_carry else 1),
            "overnight_minutes_to_close": _safe_float(decision.get("minutes_to_close")),
            "overnight_positive_signals": [
                str(item)
                for item in list(decision.get("positive_signals") or [])
                if str(item or "").strip()
            ],
            "overnight_blockers": [
                str(item)
                for item in list(decision.get("blockers") or [])
                if str(item or "").strip()
            ],
        }
        if not decision:
            monitor_state = monitor_states.get(symbol) if isinstance(monitor_states.get(symbol), dict) else {}
            row.update(_overnight_missing_context(raw_row, monitor_state))
        else:
            row.update(_overnight_recorded_context(decision))
        positions.append(row)

    reconciled_symbols = {str(row.get("symbol") or "").strip().upper() for row in reconciled_closed}
    carry_forward_symbols = [
        item
        for item in list(closeout.get("carry_forward_symbols") or [])
        if str(item or "").strip().upper() not in reconciled_symbols
    ]
    closeout_meta = _closeout_state_metadata(closeout, day)

    return {
        "available": True,
        "source": "state_snapshot",
        "source_path": state_path,
        "position_count": len(positions),
        "positions": positions,
        "reconciled_closed_positions": reconciled_closed,
        "account_snapshot_reconciliation": account_snapshot_reconciliation,
        "closeout_state": {
            "mode": str(closeout.get("mode") or ""),
            "reason": str(closeout.get("reason") or ""),
            "applied_at": str(closeout.get("applied_at") or ""),
            **closeout_meta,
            "carry_forward_symbols": carry_forward_symbols,
            "flattened_symbols": list(closeout.get("flattened_symbols") or []),
            "unresolved_flatten_symbols": list(closeout.get("unresolved_flatten_symbols") or []),
        },
    }


def build_residual_positions_payload(*, reports_root: Path, day: str | None = None) -> Dict[str, Any]:
    return _build_residual_positions_payload(reports_root=reports_root, day=day)


def _extract_trade_decision_fields(row: Dict[str, Any], reports_root: Path) -> Dict[str, Any]:
    trade_dir = _trade_dir_for_row(row, reports_root)
    if trade_dir is None:
        return {}
    summary_input = _read_json(trade_dir / "reports" / "ai_trade_summary_input.json")
    summary_report = _read_json(trade_dir / "reports" / "ai_trade_summary.json")
    full_report = _read_json(trade_dir / "reports" / "ai_trade_report.json")
    strategist_summary = _read_json(trade_dir / "reports" / "strategist_summary.json")
    exit_payload = _read_json(trade_dir / "exit.json")
    lifecycle_bundle = _read_json(trade_dir / "lifecycle_bundle.json")
    summary_input = _as_dict(summary_input)
    summary_report = _as_dict(summary_report)
    full_report = _as_dict(full_report)
    strategist_summary = _as_dict(strategist_summary)
    exit_payload = _as_dict(exit_payload)
    lifecycle_bundle = _as_dict(lifecycle_bundle)

    decision_flow = summary_input.get("decision_flow") if isinstance(summary_input.get("decision_flow"), dict) else {}
    if not decision_flow:
        decision_flow = summary_report.get("decision_flow") if isinstance(summary_report.get("decision_flow"), dict) else {}
    shared_facts = full_report.get("shared_facts") if isinstance(full_report.get("shared_facts"), dict) else {}
    if not shared_facts:
        shared_facts = summary_input.get("shared_facts") if isinstance(summary_input.get("shared_facts"), dict) else {}
    market_strategy = _as_dict(summary_input.get("market_and_strategy"))
    broker_alignment = _first_dict(
        summary_input.get("broker_alignment"),
        summary_report.get("broker_alignment"),
        full_report.get("broker_alignment"),
    )
    strategy_detail = _as_dict(strategist_summary.get("strategy_detail"))
    strategy_frame = _as_dict(strategist_summary.get("strategy_frame"))
    candidate_watch = _as_dict(strategy_detail.get("candidate_watch_policy"))
    entry_visibility = _as_dict(decision_flow.get("entry_execution_visibility"))
    if not candidate_watch:
        candidate_watch = _as_dict(entry_visibility.get("strategy_candidate_watch_proposal"))
    commander_entry = _as_dict(entry_visibility.get("commander_entry_control"))
    entry_observation = _as_dict(decision_flow.get("entry_observation"))
    scanner_chart_fit = _as_dict(decision_flow.get("scanner_chart_fit"))
    monitor_context = _as_dict(exit_payload.get("monitor_context"))
    full_monitor = _as_dict(full_report.get("monitor_snapshot"))
    summary_monitor = _as_dict(summary_input.get("monitor_snapshot"))
    quant_tactic_surface = _first_dict(
        summary_input.get("quant_tactic"),
        summary_report.get("quant_tactic"),
        full_report.get("quant_tactic"),
        full_report.get("quant_tactic_surface"),
    )
    recomputed_quant_tactic_surface = build_quant_tactic_surface(full_report)
    if recomputed_quant_tactic_surface:
        quant_tactic_surface = recomputed_quant_tactic_surface
    entry_quant_decision = _first_dict(
        full_monitor.get("entry_quant_decision"),
        summary_monitor.get("entry_quant_decision"),
        monitor_context.get("entry_quant_decision"),
        _first_recursive_dict(summary_input, summary_report, full_report, exit_payload, lifecycle_bundle, key="entry_quant_decision"),
    )
    exit_quant_decision = _first_dict(
        full_monitor.get("exit_quant_decision"),
        summary_monitor.get("exit_quant_decision"),
        monitor_context.get("exit_quant_decision"),
        _first_recursive_dict(summary_input, summary_report, full_report, exit_payload, lifecycle_bundle, key="exit_quant_decision"),
    )
    quant_factor_snapshot = _first_dict(
        full_monitor.get("quant_factor_snapshot"),
        summary_monitor.get("quant_factor_snapshot"),
        monitor_context.get("quant_factor_snapshot"),
        _first_recursive_dict(summary_input, summary_report, full_report, exit_payload, lifecycle_bundle, key="quant_factor_snapshot"),
    )
    quant_factors = _as_dict(quant_factor_snapshot.get("factors"))
    tactic_suitability = _first_dict(
        _dig(full_report, "why_this_symbol_was_chosen", "tactic_suitability"),
        _dig(summary_input, "why_this_symbol_was_chosen", "tactic_suitability"),
        _dig(summary_report, "why_this_symbol_was_chosen", "tactic_suitability"),
        entry_quant_decision.get("tactic_suitability"),
        _first_recursive_dict(summary_input, summary_report, full_report, exit_payload, lifecycle_bundle, key="tactic_suitability"),
    )
    entry_focus = _as_dict(entry_visibility.get("monitor_focus_context"))
    entry_grouped = _as_dict(entry_visibility.get("entry_grouped_logic_trace"))
    if not entry_grouped:
        entry_grouped = _as_dict(entry_focus.get("entry_grouped_logic_trace"))
    if not entry_grouped and str(entry_focus.get("entry_triggered") or "").lower() not in {"true", "1"}:
        entry_grouped = _as_dict(monitor_context.get("entry_grouped_logic_trace"))
    if not entry_grouped and str(entry_focus.get("entry_triggered") or "").lower() not in {"true", "1"}:
        entry_grouped = _as_dict(_find_key_recursive(exit_payload, "entry_grouped_logic_trace"))
    human_detail = _as_dict(entry_grouped.get("human_chart_detail_observed"))
    if not human_detail:
        human_detail = _as_dict(entry_observation)

    out: Dict[str, Any] = {
        "trade_root_path": str(trade_dir),
        "report_path": str(trade_dir / "reports" / "ai_trade_report.json"),
    }
    entry_reason = _entry_reason_from_decision_flow(decision_flow, fallback=row.get("entry_reason"))
    exit_reason = str(
        decision_flow.get("exit_trigger")
        or decision_flow.get("exit_reason")
        or shared_facts.get("exit_reason")
        or row.get("exit_reason")
        or ""
    ).strip()
    if entry_reason:
        out["entry_reason"] = entry_reason
    if exit_reason:
        out["exit_reason"] = exit_reason
    if shared_facts:
        out["last_action"] = str(shared_facts.get("action") or row.get("last_action") or "")
        out["last_status"] = str(shared_facts.get("status") or row.get("last_status") or row.get("status") or "")
    if broker_alignment:
        alignment_status = _text_value(broker_alignment.get("status"))
        if alignment_status:
            out["broker_alignment_status"] = alignment_status
        for key in (
            "local_total",
            "broker_total",
            "missing_in_local_total",
            "missing_in_broker_total",
            "account_snapshot_error_count",
        ):
            value = broker_alignment.get(key)
            if _safe_int(value, default=-1) >= 0:
                out[f"broker_alignment_{key}"] = _safe_int(value)
        snapshot_status = _text_value(broker_alignment.get("account_snapshot_status"))
        if snapshot_status:
            out["broker_account_snapshot_status"] = snapshot_status
    for field in ("lifecycle_completeness", "trade_origin", "evidence_recovery_used"):
        if lifecycle_bundle.get(field) not in (None, ""):
            out[field] = lifecycle_bundle.get(field)

    final_playbook = _first_text(
        strategy_detail.get("final_playbook"),
        strategy_frame.get("playbook"),
        lifecycle_bundle.get("strategist_summary", {}).get("playbook") if isinstance(lifecycle_bundle.get("strategist_summary"), dict) else "",
        market_strategy.get("playbook"),
        row.get("playbook"),
    )
    if final_playbook:
        out["final_playbook"] = final_playbook
        out["playbook"] = final_playbook
    for key, value in {
        "pre_llm_playbook": strategy_detail.get("pre_llm_playbook"),
        "llm_requested_playbook": strategy_detail.get("llm_requested_playbook") or strategy_detail.get("requested_playbook"),
        "tactical_strategy": strategy_detail.get("tactical_strategy") or candidate_watch.get("tactical_strategy"),
        "risk_tone": candidate_watch.get("risk_tone") or market_strategy.get("risk_tone"),
        "trade_aggressiveness": candidate_watch.get("trade_aggressiveness"),
        "strategy_horizon": _first_text(
            _find_key_recursive(exit_payload, "strategy_horizon"),
            _dig(lifecycle_bundle, "trade_lifecycle", "exit", "monitor_context", "strategy_horizon"),
        ),
        "market_regime": candidate_watch.get("market_regime"),
    }.items():
        text = _text_value(value)
        if text:
            out[key] = text
    if candidate_watch:
        out["candidate_watch_max_priority_rank"] = _safe_int(candidate_watch.get("max_priority_rank"))
        out["candidate_watch_max_runner_ups"] = _safe_int(candidate_watch.get("max_runner_ups"))
        cascade_bucket = _bool_bucket(candidate_watch.get("cascade_enabled"))
        if cascade_bucket:
            out["candidate_watch_cascade_enabled"] = cascade_bucket
    for key in ("candidate_watch_policy_effect", "candidate_watch_policy_clamp_reason", "mode", "decision"):
        text = _text_value(commander_entry.get(key))
        if text:
            out[f"commander_entry_{key}"] = text

    scanner_rank = _safe_int(decision_flow.get("scanner_rank") or decision_flow.get("selected_rank"), default=0)
    if scanner_rank > 0:
        out["scanner_rank"] = scanner_rank
        out["scanner_rank_bucket"] = _rank_bucket(scanner_rank)
    for key, value in {
        "scanner_selection_basis": decision_flow.get("selection_basis"),
        "scanner_rank_basis": decision_flow.get("scanner_rank_basis"),
        "scanner_selection_path": decision_flow.get("selection_path"),
        "scanner_chart_fit_authority": scanner_chart_fit.get("authority") or decision_flow.get("scanner_chart_fit_authority"),
    }.items():
        text = _text_value(value)
        if text:
            out[key] = text
    scanner_chart_score = scanner_chart_fit.get("score")
    if scanner_chart_score is None:
        scanner_chart_score = decision_flow.get("scanner_chart_fit_score")
    if _safe_float(scanner_chart_score) is not None:
        out["scanner_chart_fit_score"] = _safe_float(scanner_chart_score)
        out["scanner_chart_fit_score_bucket"] = _score_bucket(scanner_chart_score)

    for key, source in {
        "human_chart_entry_score": (
            entry_observation.get("human_chart_entry_score")
            or entry_grouped.get("human_chart_entry_score")
            or entry_focus.get("human_chart_entry_score")
        ),
        "human_chart_setup_quality": entry_grouped.get("human_chart_setup_quality") or entry_focus.get("human_chart_setup_quality"),
        "human_candle_quality_score": entry_observation.get("human_candle_quality_score") or entry_grouped.get("human_candle_quality_score"),
        "human_vwap_reference_quality_score": entry_observation.get("human_vwap_reference_quality_score") or entry_grouped.get("human_vwap_reference_quality_score"),
        "human_reward_room_score": entry_observation.get("human_reward_room_score") or entry_grouped.get("human_reward_room_score"),
        "human_multi_window_structure_score": entry_observation.get("human_multi_window_structure_score") or entry_grouped.get("human_multi_window_structure_score"),
        "entry_confidence_score": entry_observation.get("confidence_score") or _dig(monitor_context, "entry_condition_scores", "confidence_score"),
        "vwap_source": entry_observation.get("vwap_source") or human_detail.get("vwap_source"),
        "late_entry_risk": entry_grouped.get("late_entry_risk"),
    }.items():
        text = _text_value(source)
        if text:
            out[key] = source
    for key in (
        "human_chart_entry_score",
        "human_candle_quality_score",
        "human_vwap_reference_quality_score",
        "human_reward_room_score",
        "human_multi_window_structure_score",
        "entry_confidence_score",
    ):
        if _safe_float(out.get(key)) is not None:
            out[f"{key}_bucket"] = _score_bucket(out.get(key))
    reward_room_pct = human_detail.get("reward_room_pct") or entry_observation.get("reward_room_pct")
    if _safe_float(reward_room_pct) is not None:
        out["reward_room_pct"] = _safe_float(reward_room_pct)
        out["reward_room_pct_bucket"] = _pct_bucket(reward_room_pct)

    exit_triggered = _find_key_recursive(exit_payload, "exit_triggered")
    if isinstance(exit_triggered, bool):
        out["monitor_exit_triggered"] = "true" if exit_triggered else "false"
    cost_floor_blocked = _find_key_recursive(exit_payload, "cost_aware_profit_floor_blocked")
    cost_floor_met = _find_key_recursive(exit_payload, "cost_aware_profit_floor_met")
    if cost_floor_blocked is not None or cost_floor_met is not None:
        out["cost_floor_state"] = (
            "blocked" if bool(cost_floor_blocked) else "met" if bool(cost_floor_met) else "not_met"
        )
    peak_urgent = _find_key_recursive(exit_payload, "peak_drawdown_profit_protection_urgent")
    peak_armed = _find_key_recursive(exit_payload, "peak_drawdown_armed")
    if bool(peak_urgent):
        out["peak_drawdown_state"] = "urgent"
    elif bool(peak_armed):
        out["peak_drawdown_state"] = "armed"
    elif _safe_float(_find_key_recursive(exit_payload, "peak_drawdown")) is not None:
        out["peak_drawdown_state"] = "observed"
    time_blocked = _find_key_recursive(exit_payload, "time_limit_reassessment_blocked")
    time_reached = _find_key_recursive(exit_payload, "time_limit_reached")
    if time_blocked is not None or time_reached is not None:
        out["time_limit_reassessment_state"] = (
            "blocked" if bool(time_blocked) else "reached" if bool(time_reached) else "not_reached"
        )
    if _safe_float(_find_key_recursive(exit_payload, "vwap_distance")) is not None:
        out["vwap_breakdown_state"] = "observed"
    quant_tactic = _first_text(
        quant_tactic_surface.get("tactic_id"),
        entry_quant_decision.get("tactic_id"),
        exit_quant_decision.get("tactic_id"),
        quant_factor_snapshot.get("tactic_id"),
        out.get("tactical_strategy"),
    )
    if quant_tactic:
        out["quant_tactic_id"] = quant_tactic
        if not out.get("tactical_strategy"):
            out["tactical_strategy"] = quant_tactic
    tactic_source = _text_value(quant_tactic_surface.get("tactic_id_source"))
    if tactic_source:
        out["quant_tactic_id_source"] = tactic_source
    tactic_mismatches = quant_tactic_surface.get("tactic_id_mismatches")
    if isinstance(tactic_mismatches, list):
        out["quant_tactic_mismatch_count"] = len([row for row in tactic_mismatches if isinstance(row, dict)])
    elif entry_quant_decision.get("tactic_id") and exit_quant_decision.get("tactic_id"):
        out["quant_tactic_mismatch_count"] = int(
            str(entry_quant_decision.get("tactic_id")).strip() != str(exit_quant_decision.get("tactic_id")).strip()
        )
    exit_tactic_drifts = quant_tactic_surface.get("exit_tactic_drifts")
    if isinstance(exit_tactic_drifts, list):
        out["quant_exit_tactic_drift_count"] = len([row for row in exit_tactic_drifts if isinstance(row, dict)])
    for key, value in {
        "entry_quant_decision": entry_quant_decision.get("decision"),
        "exit_quant_decision": exit_quant_decision.get("decision"),
        "entry_quant_primary_blocker": _first_reason_bucket(entry_quant_decision.get("blockers")),
        "entry_quant_primary_warning": _first_reason_bucket(entry_quant_decision.get("warnings")),
        "exit_quant_primary_blocker": _first_reason_bucket(exit_quant_decision.get("blockers")),
        "exit_quant_primary_warning": _first_reason_bucket(exit_quant_decision.get("warnings")),
        "exit_quant_confirmation_state": _confirmation_bucket(exit_quant_decision.get("confirmation_pending")),
        "exit_quant_hold_window_state": _mismatch_bucket(exit_quant_decision.get("hold_window_mismatch")),
        "exit_quant_hard_exit": _bool_bucket(exit_quant_decision.get("hard_exit")),
        "tactic_suitability_tier": tactic_suitability.get("tier"),
        "entry_quant_cost_floor_state": _dig(entry_quant_decision, "cost_edge", "cost_floor_state") or quant_factors.get("cost_floor_state"),
    }.items():
        text = _text_value(value)
        if text:
            out[key] = text
    if _safe_float(tactic_suitability.get("score")) is not None:
        out["tactic_suitability_score"] = _safe_float(tactic_suitability.get("score"))
        out["tactic_suitability_score_bucket"] = _score_bucket(tactic_suitability.get("score"))
    if _safe_float(_dig(entry_quant_decision, "cost_edge", "cost_adjusted_edge_pct")) is not None:
        edge = _safe_float(_dig(entry_quant_decision, "cost_edge", "cost_adjusted_edge_pct"))
        out["entry_quant_cost_edge_pct"] = edge
        out["entry_quant_cost_edge_bucket"] = _pct_bucket(edge)
    if _safe_int(exit_quant_decision.get("actual_hold_sec"), 0) > 0:
        out["exit_quant_actual_hold_sec"] = _safe_int(exit_quant_decision.get("actual_hold_sec"), 0)
    return out


def _operator_reason_name(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower().strip()
    if lowered in {"hold", "unknown", "none", "null", "-"}:
        return ""
    if lowered.startswith("entry evidence was not captured"):
        return ""
    if lowered.startswith("entry context was recovered"):
        return ""
    if "진입은 hold 조건에서 실행" in raw:
        return ""
    if "entry evidence was not captured" in lowered or "position context was inferred" in lowered:
        return ""
    if "position is still open" in lowered or "포지션은 아직 열려" in raw:
        return ""
    if "청산 근거가 누락" in raw:
        return ""
    if (
        "sell 실행 및 잔여수량" in lowered
        or "sell_execution_confirmed" in lowered
        or "full_sell_quantity_reconciled" in lowered
        or "exit_trigger_not_captured" in lowered
        or "monitor_exit_trigger_not_captured" in lowered
    ):
        return "모니터 청산 트리거 미확인"
    if lowered.startswith("진입 사유는 "):
        raw = raw[len("진입 사유는 ") :].strip()
        lowered = raw.lower().strip()
    if lowered.endswith("입니다"):
        raw = raw[:-3].strip()
        lowered = raw.lower().strip()
    scanner_match = re.search(
        r"scanner selected\s+([0-9a-zA-Z]+)\s+as rank\s+#?\d+.*?because it led on\s+(.+?)(?:\.|$)",
        raw,
        flags=re.IGNORECASE,
    )
    if scanner_match:
        basis = _operator_signal_basis_name(scanner_match.group(2))
        return f"스캐너 1순위 선정: {basis}" if basis else "스캐너 1순위 선정"
    if lowered.startswith("sell was triggered because "):
        lowered = lowered[len("sell was triggered because ") :].strip().rstrip(".")
        raw = lowered
    normalized = lowered.replace("-", "_").replace(" ", "_")
    mapping = {
        "breakout_above_recent_high": "직전 고점 돌파",
        "breakout_above_recent_high_with_vwap_structure_confirmation": "직전 고점 돌파 + VWAP 구조 확인",
        "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation": "직전 고점 돌파 + VWAP 유지 + 거래량 확인",
        "pullback_structure_above_vwap_with_volume_confirmation": "VWAP 위 눌림목 + 거래량 확인",
        "pullback_rebound": "눌림목 반등",
        "pullback_rebound_above_vwap_with_confirmation": "눌림목 반등 + VWAP 확인",
        "pullback_rebound_above_vwap_with_volume_confirmation": "눌림목 반등 + VWAP + 거래량 확인",
        "pullback_reclaim_above_vwap_with_rebound_confirmation": "눌림목 VWAP 재회복 + 반등 확인",
        "pullback_reclaim_above_vwap_with_volume_confirmation": "눌림목 VWAP 재회복 + 거래량 확인",
        "hard_stop": "고정 손절 기준",
        "stop_loss": "고정 손절 기준",
        "take_profit": "목표 수익 실현 기준",
        "partial_take_profit": "1차 일부 익절",
        "profit_ladder": "구간별 분할 익절",
        "risk_reward_take_profit": "손익비 익절",
        "vwap_extension_take_profit": "VWAP 과확장 익절",
        "resistance_take_profit": "저항권 익절",
        "volume_exhaustion_take_profit": "거래량 둔화 익절",
        "opening_gap_profit_take": "갭 추격 빠른 익절",
        "time_decay_profit_exit": "시간 경과 수익 보전",
        "vwap_breakdown": "VWAP 이탈",
        "peak_drawdown": "고점 대비 하락폭 기준",
        "intraday_low_break": "장중 저점 이탈 기준",
        "prior_low_break": "직전 저점 이탈",
        "trend_breakdown": "추세 붕괴 기준",
        "trailing_stop": "추적 손절 기준",
        "eod_flat": "장마감 정리 기준",
        "exit_trigger_not_captured": "모니터 청산 트리거 미확인",
        "monitor_exit_trigger_not_captured": "모니터 청산 트리거 미확인",
        "sell_execution_confirmed": "모니터 청산 트리거 미확인",
        "full_sell_quantity_reconciled": "모니터 청산 트리거 미확인",
        "no_position": "",
        "no": "",
        "unknown": "미분류",
    }
    korean_text = raw.strip()
    if "VWAP 위 눌림목 구조와 거래량 확인" in korean_text:
        return "VWAP 위 눌림목 + 거래량 확인"
    if "직전 고점 돌파와 VWAP 구조 확인" in korean_text:
        return "직전 고점 돌파 + VWAP 구조 확인"
    if "VWAP 유지와 거래량 확인이 있는 최근 고점 돌파" in korean_text:
        return "직전 고점 돌파 + VWAP 유지 + 거래량 확인"
    if korean_text == "눌림목·거래량 경로":
        return "눌림목 + 거래량 경로"
    if korean_text == "돌파 경로":
        return "돌파 경로"
    if korean_text == "장중 저점 이탈":
        return "장중 저점 이탈 기준"
    if "pullback reclaim above vwap with rebound confirmation" in lowered:
        return "눌림목 VWAP 재회복 + 반등 확인"
    if "pullback structure above vwap with volume confirmation" in lowered:
        return "VWAP 위 눌림목 + 거래량 확인"
    if "pullback rebound above vwap with volume confirmation" in lowered:
        return "눌림목 반등 + VWAP + 거래량 확인"
    if "pullback rebound above vwap with confirmation" in lowered:
        return "눌림목 반등 + VWAP 확인"
    return mapping.get(normalized, raw)


def _operator_signal_basis_name(value: Any) -> str:
    raw = str(value or "").strip().rstrip(".")
    if not raw:
        return ""
    pieces = [part.strip() for part in re.split(r",|\band\b", raw) if part.strip()]
    mapping = {
        "turnover": "거래대금",
        "volume": "거래량",
        "turnover and volume": "거래대금/거래량",
        "trading value": "거래대금",
        "theme": "테마",
        "theme and sector alignment": "섹터·테마 정렬",
        "sector alignment": "섹터 정렬",
        "sentiment support": "감성 지원",
        "combined scanner ranking score": "스캐너 종합점수",
        "회전율/거래량": "회전율/거래량",
        "섹터·테마 정렬": "섹터·테마 정렬",
        "감성 지원": "감성 지원",
    }
    lowered = raw.lower()
    if lowered in mapping:
        return mapping[lowered]
    out: List[str] = []
    for piece in pieces:
        key = piece.lower()
        out.append(mapping.get(key, piece))
    return " + ".join(dict.fromkeys(out))


def _operator_pattern_name(value: Any, *, axis: str, fallback_reason: Any = "") -> str:
    raw = str(value or "").strip()
    lowered = raw.lower().strip()
    if lowered.startswith("entry context was recovered"):
        return ""
    if "진입은 hold 조건에서 실행" in raw:
        return ""
    if "entry evidence was not captured" in lowered or "position context was inferred" in lowered:
        return ""
    if "position is still open" in lowered or "포지션은 아직 열려" in raw:
        return ""
    if "청산 근거가 누락" in raw:
        return ""
    if (
        "sell 실행 및 잔여수량" in lowered
        or "sell_execution_confirmed" in lowered
        or "full_sell_quantity_reconciled" in lowered
        or "exit_trigger_not_captured" in lowered
        or "monitor_exit_trigger_not_captured" in lowered
    ):
        return "청산 트리거 미확인"
    if lowered in {"", "-", "no", "none", "unknown", "hold", "no_position", "no position"}:
        reason = _operator_reason_name(fallback_reason)
        if reason:
            return _operator_pattern_from_reason_name(reason, axis=axis)
        return ""
    normalized = lowered.replace("-", "_").replace(" ", "_")
    mapping = {
        "breakout": "돌파",
        "pullback": "눌림목",
        "reclaim": "VWAP 재회복",
        "continuation": "추세 지속",
        "hard_stop": "손절",
        "stop_loss": "손절",
        "peak_drawdown": "고점 대비 하락폭",
        "vwap_breakdown": "VWAP 이탈",
        "intraday_low_break": "장중 저점 이탈",
        "trend_breakdown": "추세 붕괴",
        "trailing_stop": "추적 손절",
        "take_profit": "익절",
        "eod_flat": "장마감 정리",
        "exit_trigger_not_captured": "청산 트리거 미확인",
        "monitor_exit_trigger_not_captured": "청산 트리거 미확인",
        "sell_execution_confirmed": "청산 트리거 미확인",
        "full_sell_quantity_reconciled": "청산 트리거 미확인",
    }
    return mapping.get(normalized, raw)


def _operator_pattern_from_reason_name(reason_name: str, *, axis: str) -> str:
    text = str(reason_name or "").strip()
    if not text or text == "미분류":
        return ""
    if "고정 손절" in text:
        return "손절"
    if "장중 저점" in text:
        return "장중 저점 이탈"
    if "고점 대비" in text:
        return "고점 대비 하락폭"
    if "VWAP 이탈" in text:
        return "VWAP 이탈"
    if "목표 수익" in text or "익절" in text:
        return "익절"
    if "돌파" in text:
        return "돌파"
    if "눌림목" in text:
        return "눌림목"
    if axis == "entry" and text.startswith("스캐너 1순위 선정"):
        return ""
    return text


def _enrich_rows_with_truth_surface(rows: Iterable[Dict[str, Any]], reports_root: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        row_obj = dict(row or {})
        row_obj.update(_extract_trade_decision_fields(row_obj, reports_root))
        truth_metrics = _extract_truth_surface_metrics(row_obj, reports_root)
        row_obj.update(truth_metrics)
        out.append(row_obj)
    return out


def _metric_return_pct(row: Dict[str, Any]) -> float | None:
    if bool(row.get("truth_surface_available")):
        return _safe_float(row.get("truth_net_return_pct"))
    return _safe_float(row.get("result_pct"))


def _metric_observed_return_pct(row: Dict[str, Any]) -> float | None:
    if bool(row.get("truth_surface_available")):
        return _safe_float(row.get("truth_observed_return_pct"))
    return None


def _parse_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _period_from_week(week: str) -> Tuple[str, date, date]:
    text = str(week or "").strip()
    match = _WEEK_RE.match(text)
    if not match:
        raise ValueError(f"invalid week key: {text!r}; expected YYYY-Www")
    year = int(match.group(1))
    week_num = int(match.group(2))
    start = date.fromisocalendar(year, week_num, 1)
    end = date.fromisocalendar(year, week_num, 7)
    return f"{year:04d}-W{week_num:02d}", start, end


def _period_from_month(month: str) -> Tuple[str, date, date]:
    text = str(month or "").strip()
    match = _MONTH_RE.match(text)
    if not match:
        raise ValueError(f"invalid month key: {text!r}; expected YYYY-MM")
    year = int(match.group(1))
    month_num = int(match.group(2))
    last_day = calendar.monthrange(year, month_num)[1]
    return f"{year:04d}-{month_num:02d}", date(year, month_num, 1), date(year, month_num, last_day)


def default_week_key(day: date | None = None) -> str:
    target = day or date.today()
    iso = target.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def default_month_key(day: date | None = None) -> str:
    target = day or date.today()
    return f"{target.year:04d}-{target.month:02d}"


def _iter_symbol_trade_history(reports_root: Path) -> Iterable[Dict[str, Any]]:
    symbol_root = operator_summary_artifact_root(reports_root) / "symbols"
    if not symbol_root.exists():
        return []

    def gen() -> Iterable[Dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        for path in sorted(symbol_root.glob("*/trade_history.json")):
            payload = _read_json(path)
            if not isinstance(payload, list):
                continue
            symbol_hint = path.parent.name.upper()
            for row in payload:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or symbol_hint).strip().upper()
                trade_id = str(row.get("trade_id") or "").strip()
                key = (symbol, trade_id or f"{path}:{len(seen)}")
                if key in seen:
                    continue
                seen.add(key)
                out = dict(row)
                out["symbol"] = symbol
                yield out

    return gen()


def _top_counter(counter: Counter[str], limit: int = 5) -> List[Dict[str, Any]]:
    return [
        {"name": name, "count": int(count)}
        for name, count in counter.most_common(limit)
        if str(name or "").strip()
    ]


def _trade_status(row: Dict[str, Any]) -> str:
    return str(row.get("last_status") or row.get("status") or "").strip().lower()


def _trade_action(row: Dict[str, Any]) -> str:
    return str(row.get("last_action") or row.get("action") or "").strip().upper()


def _has_partial_lifecycle_marker(row: Dict[str, Any]) -> bool:
    return (
        _trade_status(row) == "partial"
        or str(row.get("trade_origin") or "").strip().lower() == "recovered_partial"
    )


def _is_closed_trade(row: Dict[str, Any]) -> bool:
    return _trade_status(row) == "closed" and not _has_partial_lifecycle_marker(row)


def _is_recovered_partial_marker(row: Dict[str, Any]) -> bool:
    return _has_partial_lifecycle_marker(row)


def _is_realized_nonclosed_exit(row: Dict[str, Any]) -> bool:
    if _is_closed_trade(row) or _trade_action(row) != "SELL":
        return False
    return _is_recovered_partial_marker(row)


def _return_count_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    returns = [value for value in (_metric_return_pct(row) for row in rows) if value is not None]
    observed_returns = [value for value in (_metric_observed_return_pct(row) for row in rows) if value is not None]
    price_moves = [value for value in (_safe_float(row.get("truth_price_move_pct")) for row in rows) if value is not None]
    hold_seconds = [value for value in (_safe_float(row.get("hold_seconds")) for row in rows) if value is not None]
    win_count = sum(1 for value in returns if value > 0)
    loss_count = sum(1 for value in returns if value < 0)
    flat_count = sum(1 for value in returns if value == 0)
    cost_drag_loss_count = sum(
        1
        for row in rows
        if (_metric_return_pct(row) is not None and float(_metric_return_pct(row) or 0.0) < 0.0)
        and (_safe_float(row.get("truth_price_move_pct")) is not None and float(_safe_float(row.get("truth_price_move_pct")) or 0.0) >= 0.0)
    )
    return {
        "return_sample_count": len(returns),
        "unavailable_return_count": max(0, len(rows) - len(returns)),
        "observed_return_sample_count": len(observed_returns),
        "truth_surface_count": sum(1 for row in rows if bool(row.get("truth_surface_available"))),
        "win_count": win_count,
        "loss_count": loss_count,
        "flat_count": flat_count,
        "observed_win_count": sum(1 for value in observed_returns if value > 0),
        "observed_loss_count": sum(1 for value in observed_returns if value < 0),
        "observed_flat_count": sum(1 for value in observed_returns if value == 0),
        "observed_avg_return_pct": round(sum(observed_returns) / len(observed_returns), 4) if observed_returns else 0.0,
        "price_move_win_count": sum(1 for value in price_moves if value > 0),
        "price_move_loss_count": sum(1 for value in price_moves if value < 0),
        "cost_drag_loss_count": cost_drag_loss_count,
        "win_rate": round(win_count / len(returns), 4) if returns else 0.0,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "avg_hold_seconds": round(sum(hold_seconds) / len(hold_seconds), 2) if hold_seconds else 0.0,
    }


def _symbol_rows(rows: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("symbol") or "").strip().upper()].append(row)

    out: List[Dict[str, Any]] = []
    for symbol, items in grouped.items():
        closed = [row for row in items if _is_closed_trade(row)]
        realized = [row for row in items if _is_realized_nonclosed_exit(row)]
        closed_stats = _return_count_payload(closed)
        realized_stats = _return_count_payload(realized)
        out.append(
            {
                "symbol": symbol,
                "trade_count": len(items),
                "closed_trade_count": len(closed),
                **closed_stats,
                "realized_exit_count": len(realized),
                "recovered_partial_exit_count": sum(1 for row in realized if _is_recovered_partial_marker(row)),
                "carryover_exit_count": sum(1 for row in realized if _is_recovered_partial_marker(row)),
                "realized_exit_return_sample_count": realized_stats["return_sample_count"],
                "realized_exit_unavailable_return_count": realized_stats["unavailable_return_count"],
                "realized_exit_observed_return_sample_count": realized_stats["observed_return_sample_count"],
                "realized_exit_win_count": realized_stats["win_count"],
                "realized_exit_loss_count": realized_stats["loss_count"],
                "realized_exit_flat_count": realized_stats["flat_count"],
                "realized_exit_win_rate": realized_stats["win_rate"],
                "realized_exit_avg_return_pct": realized_stats["avg_return_pct"],
                "realized_exit_cost_drag_loss_count": realized_stats["cost_drag_loss_count"],
            }
        )
    out.sort(key=lambda row: (int(row.get("trade_count") or 0), abs(float(row.get("avg_return_pct") or 0.0))), reverse=True)
    return out[:limit]


def _trade_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed_rows = [row for row in rows if _is_closed_trade(row)]
    realized_rows = [row for row in rows if _is_realized_nonclosed_exit(row)]
    closed_stats = _return_count_payload(closed_rows)
    realized_stats = _return_count_payload(realized_rows)
    return {
        "trade_count": len(rows),
        "closed_trade_count": len(closed_rows),
        **closed_stats,
        "return_basis": "truth_surface_net" if closed_stats["truth_surface_count"] else "operator_symbol_result_pct",
        "realized_exit_count": len(realized_rows),
        "recovered_partial_exit_count": sum(1 for row in realized_rows if _is_recovered_partial_marker(row)),
        "carryover_exit_count": sum(1 for row in realized_rows if _is_recovered_partial_marker(row)),
        "realized_exit_return_sample_count": realized_stats["return_sample_count"],
        "realized_exit_unavailable_return_count": realized_stats["unavailable_return_count"],
        "realized_exit_observed_return_sample_count": realized_stats["observed_return_sample_count"],
        "realized_exit_truth_surface_count": realized_stats["truth_surface_count"],
        "realized_exit_win_count": realized_stats["win_count"],
        "realized_exit_loss_count": realized_stats["loss_count"],
        "realized_exit_flat_count": realized_stats["flat_count"],
        "realized_exit_observed_win_count": realized_stats["observed_win_count"],
        "realized_exit_observed_loss_count": realized_stats["observed_loss_count"],
        "realized_exit_observed_flat_count": realized_stats["observed_flat_count"],
        "realized_exit_observed_avg_return_pct": realized_stats["observed_avg_return_pct"],
        "realized_exit_win_rate": realized_stats["win_rate"],
        "realized_exit_avg_return_pct": realized_stats["avg_return_pct"],
        "realized_exit_cost_drag_loss_count": realized_stats["cost_drag_loss_count"],
        "closed_or_realized_exit_count": len(closed_rows) + len(realized_rows),
    }


def _pattern_counters(rows: List[Dict[str, Any]]) -> Dict[str, Counter[str]]:
    entry_reasons: Counter[str] = Counter()
    exit_reasons: Counter[str] = Counter()
    entry_patterns: Counter[str] = Counter()
    exit_patterns: Counter[str] = Counter()
    playbooks: Counter[str] = Counter()
    for row in rows:
        if not _is_realized_nonclosed_exit(row):
            entry_reason = _operator_reason_name(row.get("entry_reason"))
            if entry_reason:
                entry_reasons[entry_reason] += 1
            entry_pattern = _operator_pattern_name(
                row.get("entry_pattern_type"),
                axis="entry",
                fallback_reason=row.get("entry_reason"),
            )
            if entry_pattern:
                entry_patterns[entry_pattern] += 1

        if _is_closed_trade(row) or _is_realized_nonclosed_exit(row):
            exit_reason = _operator_reason_name(row.get("exit_reason"))
            if exit_reason:
                exit_reasons[exit_reason] += 1
            exit_pattern = _operator_pattern_name(
                row.get("exit_pattern_type"),
                axis="exit",
                fallback_reason=row.get("exit_reason"),
            )
            if exit_pattern:
                exit_patterns[exit_pattern] += 1
        playbook = str(row.get("playbook") or "").strip()
        if playbook:
            playbooks[playbook] += 1
    return {
        "entry_reasons": entry_reasons,
        "exit_reasons": exit_reasons,
        "entry_pattern_types": entry_patterns,
        "exit_pattern_types": exit_patterns,
        "playbooks": playbooks,
    }


def _pattern_payload(counters: Dict[str, Counter[str]]) -> Dict[str, Any]:
    return {
        "top_entry_reasons": _top_counter(counters.get("entry_reasons") or Counter()),
        "top_exit_reasons": _top_counter(counters.get("exit_reasons") or Counter()),
        "top_entry_pattern_types": _top_counter(counters.get("entry_pattern_types") or Counter()),
        "top_exit_pattern_types": _top_counter(counters.get("exit_pattern_types") or Counter()),
        "top_playbooks": _top_counter(counters.get("playbooks") or Counter()),
    }


def _performance_source_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if _is_closed_trade(row) or _is_realized_nonclosed_exit(row)]


def _performance_field_value(row: Dict[str, Any], field: str) -> Any:
    value = row.get(field)
    if field == "entry_pattern_type":
        return _operator_pattern_name(value, axis="entry", fallback_reason=row.get("entry_reason"))
    if field == "exit_pattern_type":
        return _operator_pattern_name(value, axis="exit", fallback_reason=row.get("exit_reason"))
    if _text_value(value):
        if field in {"entry_reason", "exit_reason"}:
            return _operator_reason_name(value)
        return value
    if field == "entry_reason":
        return _operator_reason_name(row.get("entry_reason"))
    if field == "exit_reason":
        return _operator_reason_name(row.get("exit_reason"))
    return value


def _performance_rows_by_field(rows: List[Dict[str, Any]], field: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        name = _text_value(_performance_field_value(row, field))
        if not name:
            continue
        grouped[name].append(row)
    out: List[Dict[str, Any]] = []
    for name, items in grouped.items():
        sample = _performance_source_rows(items)
        stats = _return_count_payload(sample)
        out.append(
            {
                "name": name,
                "count": len(items),
                "closed_or_realized_count": len(sample),
                "win_count": stats["win_count"],
                "loss_count": stats["loss_count"],
                "flat_count": stats["flat_count"],
                "win_rate": stats["win_rate"],
                "avg_return_pct": stats["avg_return_pct"],
                "cost_drag_loss_count": stats["cost_drag_loss_count"],
                "avg_hold_seconds": stats["avg_hold_seconds"],
            }
        )
    out.sort(
        key=lambda row: (
            int(row.get("closed_or_realized_count") or 0),
            int(row.get("count") or 0),
            abs(float(row.get("avg_return_pct") or 0.0)),
        ),
        reverse=True,
    )
    return out[:limit]


def _combined_pattern_key(row: Dict[str, Any]) -> str:
    playbook = _first_text(row.get("final_playbook"), row.get("playbook"))
    tactical = _text_value(row.get("tactical_strategy"))
    rank = _text_value(row.get("scanner_rank_bucket"))
    entry = _operator_pattern_name(row.get("entry_pattern_type"), axis="entry", fallback_reason=row.get("entry_reason"))
    exit_pattern = _operator_pattern_name(row.get("exit_pattern_type"), axis="exit", fallback_reason=row.get("exit_reason"))
    parts = [part for part in (playbook, tactical, rank, entry, exit_pattern) if part]
    return " | ".join(parts)


def _pattern_performance_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows or [])
    combined_rows: List[Dict[str, Any]] = []
    for row in rows:
        key = _combined_pattern_key(row)
        if key:
            enriched = dict(row)
            enriched["combined_pattern"] = key
            combined_rows.append(enriched)
    return {
        "schema_version": "pattern_performance.v1",
        "source": "operator_summary_trade_artifact_enrichment",
        "trade_count": len(rows),
        "closed_or_realized_count": len(_performance_source_rows(rows)),
        "strategist": {
            "by_final_playbook": _performance_rows_by_field(rows, "final_playbook"),
            "by_tactical_strategy": _performance_rows_by_field(rows, "tactical_strategy"),
            "by_strategy_horizon": _performance_rows_by_field(rows, "strategy_horizon"),
            "by_risk_tone": _performance_rows_by_field(rows, "risk_tone"),
            "by_trade_aggressiveness": _performance_rows_by_field(rows, "trade_aggressiveness"),
            "by_candidate_watch_rank": _performance_rows_by_field(rows, "candidate_watch_max_priority_rank"),
            "by_candidate_watch_cascade": _performance_rows_by_field(rows, "candidate_watch_cascade_enabled"),
        },
        "scanner": {
            "by_scanner_rank_bucket": _performance_rows_by_field(rows, "scanner_rank_bucket"),
            "by_selection_basis": _performance_rows_by_field(rows, "scanner_selection_basis"),
            "by_scanner_chart_fit_bucket": _performance_rows_by_field(rows, "scanner_chart_fit_score_bucket"),
            "by_scanner_chart_fit_authority": _performance_rows_by_field(rows, "scanner_chart_fit_authority"),
            "by_candidate_watch_effect": _performance_rows_by_field(rows, "commander_entry_candidate_watch_policy_effect"),
        },
        "monitor_entry": {
            "by_entry_pattern_type": _performance_rows_by_field(rows, "entry_pattern_type"),
            "by_human_chart_entry_score": _performance_rows_by_field(rows, "human_chart_entry_score_bucket"),
            "by_human_chart_setup_quality": _performance_rows_by_field(rows, "human_chart_setup_quality"),
            "by_candle_quality": _performance_rows_by_field(rows, "human_candle_quality_score_bucket"),
            "by_vwap_quality": _performance_rows_by_field(rows, "human_vwap_reference_quality_score_bucket"),
            "by_reward_room": _performance_rows_by_field(rows, "human_reward_room_score_bucket"),
            "by_reward_room_pct": _performance_rows_by_field(rows, "reward_room_pct_bucket"),
            "by_late_entry_risk": _performance_rows_by_field(rows, "late_entry_risk"),
        },
        "monitor_exit": {
            "by_exit_pattern_type": _performance_rows_by_field(rows, "exit_pattern_type"),
            "by_exit_reason": _performance_rows_by_field(rows, "exit_reason"),
            "by_cost_floor_state": _performance_rows_by_field(rows, "cost_floor_state"),
            "by_peak_drawdown_state": _performance_rows_by_field(rows, "peak_drawdown_state"),
            "by_time_limit_reassessment": _performance_rows_by_field(rows, "time_limit_reassessment_state"),
            "by_vwap_breakdown_state": _performance_rows_by_field(rows, "vwap_breakdown_state"),
            "by_monitor_exit_triggered": _performance_rows_by_field(rows, "monitor_exit_triggered"),
        },
        "quant": {
            "by_tactic_id": _performance_rows_by_field(rows, "quant_tactic_id"),
            "by_tactic_suitability_tier": _performance_rows_by_field(rows, "tactic_suitability_tier"),
            "by_tactic_suitability_score": _performance_rows_by_field(rows, "tactic_suitability_score_bucket"),
            "by_entry_decision": _performance_rows_by_field(rows, "entry_quant_decision"),
            "by_entry_primary_blocker": _performance_rows_by_field(rows, "entry_quant_primary_blocker"),
            "by_entry_cost_floor_state": _performance_rows_by_field(rows, "entry_quant_cost_floor_state"),
            "by_entry_cost_edge": _performance_rows_by_field(rows, "entry_quant_cost_edge_bucket"),
            "by_exit_decision": _performance_rows_by_field(rows, "exit_quant_decision"),
            "by_exit_primary_blocker": _performance_rows_by_field(rows, "exit_quant_primary_blocker"),
            "by_exit_confirmation_state": _performance_rows_by_field(rows, "exit_quant_confirmation_state"),
            "by_exit_hold_window_state": _performance_rows_by_field(rows, "exit_quant_hold_window_state"),
            "by_exit_hard_exit": _performance_rows_by_field(rows, "exit_quant_hard_exit"),
        },
        "combined": {
            "by_strategy_scanner_entry_exit": _performance_rows_by_field(combined_rows, "combined_pattern", limit=12)
        },
    }


def _trade_dir_for_row(row: Dict[str, Any], reports_root: Path) -> Path | None:
    trade_id = str(row.get("trade_id") or "").strip()
    day = str(row.get("date") or row.get("day") or "").strip()[:10]
    if not trade_id or not day:
        return None
    found = find_trade_dir(canonical_trade_day_root(Path(reports_root), day), trade_id)
    if found is not None:
        return found
    fallback = Path(reports_root) / "trades" / day / trade_id
    return fallback if fallback.exists() else None


def _daily_trade_index_rows(
    *,
    reports_root: Path,
    trade_index: List[Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in trade_index:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        trade_dir = _trade_dir_for_row(row, reports_root)
        if trade_dir is not None:
            summary_input = _read_json(trade_dir / "reports" / "ai_trade_summary_input.json")
            summary_report = _read_json(trade_dir / "reports" / "ai_trade_summary.json")
            full_report = _read_json(trade_dir / "reports" / "ai_trade_report.json")
            lifecycle_bundle = _read_json(trade_dir / "lifecycle_bundle.json")
            summary_input = summary_input if isinstance(summary_input, dict) else {}
            summary_report = summary_report if isinstance(summary_report, dict) else {}
            full_report = full_report if isinstance(full_report, dict) else {}
            lifecycle_bundle = lifecycle_bundle if isinstance(lifecycle_bundle, dict) else {}
            decision_flow = summary_input.get("decision_flow") if isinstance(summary_input.get("decision_flow"), dict) else {}
            if not decision_flow:
                decision_flow = summary_report.get("decision_flow") if isinstance(summary_report.get("decision_flow"), dict) else {}
            shared_facts = full_report.get("shared_facts") if isinstance(full_report.get("shared_facts"), dict) else {}
            if not shared_facts and isinstance(summary_input, dict):
                shared_facts = summary_input.get("shared_facts") if isinstance(summary_input.get("shared_facts"), dict) else {}
            for field in ("lifecycle_completeness", "trade_origin", "evidence_recovery_used"):
                if lifecycle_bundle.get(field) not in (None, ""):
                    row[field] = lifecycle_bundle.get(field)

            entry_reason = _entry_reason_from_decision_flow(decision_flow, fallback=row.get("entry_reason"))
            exit_reason = str(
                decision_flow.get("exit_trigger")
                or decision_flow.get("exit_reason")
                or shared_facts.get("exit_reason")
                or row.get("exit_reason")
                or ""
            ).strip()
            if entry_reason:
                row["entry_reason"] = entry_reason
            if exit_reason:
                row["exit_reason"] = exit_reason
            if shared_facts:
                row["last_action"] = str(shared_facts.get("action") or row.get("last_action") or "")
                row["last_status"] = str(shared_facts.get("status") or row.get("last_status") or row.get("status") or "")
            row["trade_root_path"] = str(trade_dir)
            row["report_path"] = str(trade_dir / "reports" / "ai_trade_report.json")
        rows.append(row)
    return rows


def _daily_symbol_history_rows(reports_root: Path, day: str) -> List[Dict[str, Any]]:
    normalized_day = str(day or "").strip()
    return [
        row
        for row in _iter_symbol_trade_history(reports_root)
        if str(row.get("date") or "").strip() == normalized_day
    ]


def _merge_daily_trade_index_with_symbol_history(
    trade_rows: List[Dict[str, Any]],
    history_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    history_by_trade_id = {
        str(row.get("trade_id") or "").strip(): dict(row)
        for row in history_rows
        if str(row.get("trade_id") or "").strip()
    }
    merged_rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in trade_rows:
        trade_id = str(row.get("trade_id") or "").strip()
        base = dict(history_by_trade_id.get(trade_id) or {})
        for key, value in row.items():
            if value not in (None, ""):
                base[key] = value
        merged_rows.append(base if base else dict(row))
        if trade_id:
            seen.add(trade_id)
    for trade_id, row in history_by_trade_id.items():
        if trade_id not in seen:
            merged_rows.append(dict(row))
    return merged_rows


def _entry_reason_from_decision_flow(decision_flow: Dict[str, Any], *, fallback: Any = "") -> str:
    for value in (
        decision_flow.get("monitor_fallback_reason"),
        decision_flow.get("actual_entry_reason"),
        decision_flow.get("entry_trigger"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    fallback_text = str(fallback or "").strip()
    fallback_lower = fallback_text.lower()
    if fallback_text and not fallback_lower.startswith("scanner selected ") and not fallback_lower.startswith("entry evidence was not captured"):
        return fallback_text
    for source in (decision_flow.get("entry_confidence"), decision_flow.get("entry_reason")):
        text = str(source or "").strip()
        for pattern in (
            r"실제 트리거는\s+(.+?)(?:였|이었|입니다|였습니다)",
            r"실제 엔트리 경로는\s+(.+?)(?:였|이었|입니다|였습니다)",
            r"실제 엔트리는\s+(.+?)(?:에서\s+확정|로\s+확정|으로\s+확정)",
        ):
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip(" .")
    return fallback_text


def _latest_live_summary_payload(reports_root: Path, day: str) -> Tuple[Dict[str, Any], str]:
    day_key = re.sub(r"[^0-9]", "", str(day or ""))[:8]
    if len(day_key) != 8:
        return {}, ""
    live_root = Path(reports_root) / "live_summary"
    if not live_root.exists():
        return {}, ""
    candidates = sorted(
        live_root.glob(f"live_summary_{day_key}_*.json"),
        key=lambda path: (path.stat().st_mtime if path.exists() else 0.0, path.name),
        reverse=True,
    )
    for path in candidates:
        payload = _read_json(path)
        if isinstance(payload, dict):
            return payload, str(path)
    return {}, ""


def _runtime_activity_payload(
    *,
    reports_root: Path,
    day: str,
    source_payload: Dict[str, Any],
) -> Dict[str, Any]:
    if source_payload:
        return {
            "source": "daily_report_payload",
            "events": _safe_int(source_payload.get("events")),
            "approvals": _safe_int(source_payload.get("approvals")),
            "blocks": _safe_int(source_payload.get("blocks")),
            "symbols_observed_count": len(list(source_payload.get("symbols_observed") or [])),
            "generated_symbol_report_count": _safe_int(source_payload.get("generated_symbol_report_count")),
        }

    live_payload, live_path = _latest_live_summary_payload(reports_root, day)
    if not live_payload:
        return {
            "source": "not_available",
            "events": 0,
            "approvals": 0,
            "blocks": 0,
            "symbols_observed_count": 0,
            "generated_symbol_report_count": 0,
        }

    events = live_payload.get("events") if isinstance(live_payload.get("events"), dict) else {}
    execution = live_payload.get("execution") if isinstance(live_payload.get("execution"), dict) else {}
    return {
        "source": "live_summary_fallback",
        "source_path": live_path,
        "lookback_min": _safe_int(live_payload.get("lookback_min")),
        "events": _safe_int(events.get("window_total")),
        "events_scanned_total": _safe_int(events.get("scanned_total")),
        "approvals": _safe_int(execution.get("allowed_total")),
        "blocks": _safe_int(execution.get("blocked_total")),
        "executed_total": _safe_int(execution.get("executed_total")),
        "broker_fail_total": _safe_int(execution.get("executed_broker_fail_total")),
        "symbols_observed_count": 0,
        "generated_symbol_report_count": 0,
    }


def _operator_readout(
    *,
    trade_count: int,
    avg_return_pct: float,
    win_rate: float,
    exit_counts: Counter[str],
    entry_counts: Counter[str],
) -> Dict[str, Any]:
    positives: List[str] = []
    issues: List[str] = []
    actions: List[str] = []

    if trade_count > 0:
        positives.append("기간 내 체결/청산 기록이 운영 요약으로 연결됐습니다.")
    if entry_counts:
        positives.append("진입 패턴과 선택 사유가 집계 가능할 만큼 누적됐습니다.")
    if avg_return_pct < 0:
        issues.append("완료 거래 기준 평균 수익률이 음수입니다.")
    if win_rate < 0.2 and trade_count > 0:
        issues.append("승률이 낮아 현재 진입-청산 조합의 기대값 점검이 필요합니다.")
    if any(("peak_drawdown" in name or "고점 대비" in name) for name, _ in exit_counts.most_common(3)):
        issues.append("peak_drawdown 청산이 상위 반복 패턴입니다.")
        actions.append("peak_drawdown 발동 조건과 보유 유지 조건을 함께 재검토합니다.")
    if any(("breakout" in name or "돌파" in name) for name, _ in entry_counts.most_common(3)):
        actions.append("breakout 진입 후 유지 실패가 반복되는지 종목별로 분리해 봅니다.")
    if not actions:
        actions.append("기간 내 주요 손익 기여 종목과 exit 사유를 우선 검수합니다.")

    root_cause = "후보 포착 자체보다 진입 이후 보유/청산 밸런스가 성과를 제한하는 구조로 보입니다."
    if avg_return_pct >= 0:
        root_cause = "성과는 방어됐으나 반복 패턴이 유지되는지 다음 기간까지 확인이 필요합니다."

    return {
        "good_points": positives or ["집계 가능한 거래 표본이 아직 부족합니다."],
        "issues": issues or ["치명적인 반복 손실 패턴은 아직 집계되지 않았습니다."],
        "root_cause": root_cause,
        "recommended_actions": actions,
    }


def build_operator_period_summary(
    *,
    reports_root: Path,
    period_type: str,
    period_key: str,
) -> Dict[str, Any]:
    normalized_type = str(period_type or "").strip().lower()
    if normalized_type == "weekly":
        normalized_key, start, end = _period_from_week(period_key)
    elif normalized_type == "monthly":
        normalized_key, start, end = _period_from_month(period_key)
    else:
        raise ValueError(f"unsupported period_type: {period_type!r}")

    rows: List[Dict[str, Any]] = []
    for row in _iter_symbol_trade_history(reports_root):
        row_day = _parse_day(row.get("date"))
        if row_day is None or row_day < start or row_day > end:
            continue
        rows.append(row)

    rows = _enrich_rows_with_truth_surface(rows, reports_root)
    metrics = _trade_metrics(rows)
    counters = _pattern_counters(rows)
    shadow_payloads = load_quant_shadow_candidate_payloads_for_range(
        reports_root=reports_root,
        start=start.isoformat(),
        end=end.isoformat(),
    )

    summary = {
        "schema_version": "operator_period_summary.v1",
        "period_type": normalized_type,
        "period_key": normalized_key,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "generated_at": _utc_now_iso(),
        "source": {
            "type": "operator_symbol_trade_history",
            "root": str(operator_summary_artifact_root(reports_root) / "symbols"),
        },
        "metrics": {
            **metrics,
        },
        "patterns": _pattern_payload(counters),
        "pattern_performance": _pattern_performance_payload(rows),
        "quant_tactic_evaluation": build_quant_tactic_evaluation(rows),
        "quant_shadow_candidate_evaluation": build_quant_shadow_candidate_evaluation(shadow_payloads),
        "strategist_llm_evaluation": build_strategist_llm_evaluation(rows, shadow_payloads),
        "symbol_summary": _symbol_rows(rows),
    }
    summary["operator_readout"] = _operator_readout(
        trade_count=len(rows),
        avg_return_pct=float(metrics.get("avg_return_pct") or 0.0),
        win_rate=float(metrics.get("win_rate") or 0.0),
        exit_counts=counters.get("exit_reasons") or Counter(),
        entry_counts=counters.get("entry_reasons") or Counter(),
    )
    return summary


def build_operator_daily_summary_artifact_payload(
    *,
    reports_root: Path,
    day: str,
    daily_report_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()
    source_payload = dict(daily_report_payload or {})
    trade_index = source_payload.get("trade_index") if isinstance(source_payload.get("trade_index"), list) else []
    history_rows = _daily_symbol_history_rows(reports_root, normalized_day)
    if trade_index:
        rows = _merge_daily_trade_index_with_symbol_history(
            _daily_trade_index_rows(reports_root=reports_root, trade_index=trade_index),
            history_rows,
        )
    else:
        rows = history_rows
    rows = _enrich_rows_with_truth_surface(rows, reports_root)
    metrics = _trade_metrics(rows)
    counters = _pattern_counters(rows)
    shadow_payloads = load_quant_shadow_candidate_payloads(
        reports_root=reports_root,
        days=[normalized_day],
    )
    if metrics["trade_count"] == 0 and trade_index:
        metrics["trade_count"] = len(trade_index)

    summary = {
        "schema_version": "operator_daily_summary.v1",
        "period_type": "daily",
        "day": normalized_day,
        "generated_at": _utc_now_iso(),
        "source": {
            "type": "daily_report_plus_operator_symbol_trade_history",
            "daily_report_json": str(daily_artifact_paths(reports_root, normalized_day)["daily_report_json"]),
            "symbol_history_root": str(operator_summary_artifact_root(reports_root) / "symbols"),
        },
        "runtime_activity": _runtime_activity_payload(
            reports_root=reports_root,
            day=normalized_day,
            source_payload=source_payload,
        ),
        "metrics": metrics,
        "patterns": _pattern_payload(counters),
        "pattern_performance": _pattern_performance_payload(rows),
        "quant_tactic_evaluation": build_quant_tactic_evaluation(rows),
        "quant_shadow_candidate_evaluation": build_quant_shadow_candidate_evaluation(shadow_payloads),
        "strategist_llm_evaluation": build_strategist_llm_evaluation(rows, shadow_payloads),
        "symbol_summary": _symbol_rows(rows),
        "residual_positions": _build_residual_positions_payload(reports_root=reports_root, day=normalized_day),
    }
    summary["operator_readout"] = _operator_readout(
        trade_count=int(metrics.get("trade_count") or 0),
        avg_return_pct=float(metrics.get("avg_return_pct") or 0.0),
        win_rate=float(metrics.get("win_rate") or 0.0),
        exit_counts=counters.get("exit_reasons") or Counter(),
        entry_counts=counters.get("entry_reasons") or Counter(),
    )
    return summary


def build_operator_symbol_summary_artifact_payload(
    *,
    reports_root: Path,
    symbol: str,
    symbol_trade_report_payload: Dict[str, Any] | None = None,
    symbol_memory_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_symbol = str(symbol or "").strip().upper()
    payload = dict(symbol_trade_report_payload or {})
    history = payload.get("history_index") if isinstance(payload.get("history_index"), list) else []
    rows = [dict(row, symbol=normalized_symbol) for row in history if isinstance(row, dict)]
    rows = _enrich_rows_with_truth_surface(rows, reports_root)
    metrics = _trade_metrics(rows)
    counters = _pattern_counters(rows)
    days = sorted(
        {
            str(row.get("date") or row.get("day") or "")[:10]
            for row in rows
            if str(row.get("date") or row.get("day") or "").strip()
        }
    )
    shadow_payloads = load_quant_shadow_candidate_payloads(reports_root=reports_root, days=days)
    pattern_insights = payload.get("pattern_insights") if isinstance(payload.get("pattern_insights"), dict) else {}
    memory = dict(symbol_memory_payload or {})

    summary = {
        "schema_version": "operator_symbol_summary.v1",
        "period_type": "symbol",
        "symbol": normalized_symbol,
        "generated_at": _utc_now_iso(),
        "source": {
            "type": "symbol_trade_report",
            "symbol_trade_report_json": str(symbol_artifact_paths(reports_root, normalized_symbol)["symbol_trade_report_json"]),
            "symbol_memory_json": str(symbol_artifact_paths(reports_root, normalized_symbol)["symbol_memory_json"]),
        },
        "metrics": metrics,
        "patterns": _pattern_payload(counters),
        "pattern_performance": _pattern_performance_payload(rows),
        "quant_tactic_evaluation": build_quant_tactic_evaluation(rows),
        "quant_shadow_candidate_evaluation": build_quant_shadow_candidate_evaluation(
            shadow_payloads,
            symbol=normalized_symbol,
        ),
        "strategist_llm_evaluation": build_strategist_llm_evaluation(rows, shadow_payloads),
        "symbol_memory": {
            "available": bool(memory),
            "trade_stats": dict(memory.get("trade_stats") or {}) if isinstance(memory.get("trade_stats"), dict) else {},
            "bias_recommendation": dict(memory.get("bias_recommendation") or {}) if isinstance(memory.get("bias_recommendation"), dict) else {},
            "latest_snapshot": dict(memory.get("latest_snapshot") or {}) if isinstance(memory.get("latest_snapshot"), dict) else {},
        },
        "risk_notes": list(pattern_insights.get("risk_notes") or []),
    }
    summary["operator_readout"] = _operator_readout(
        trade_count=int(metrics.get("trade_count") or 0),
        avg_return_pct=float(metrics.get("avg_return_pct") or 0.0),
        win_rate=float(metrics.get("win_rate") or 0.0),
        exit_counts=counters.get("exit_reasons") or Counter(),
        entry_counts=counters.get("entry_reasons") or Counter(),
    )
    return summary


def _pattern_perf_rows(pattern_performance: Dict[str, Any], *path: str) -> List[Dict[str, Any]]:
    current: Any = pattern_performance
    for key in path:
        if not isinstance(current, dict):
            return []
        current = current.get(key)
    return [row for row in list(current or []) if isinstance(row, dict)]


def _pattern_perf_line(label: str, rows: List[Dict[str, Any]], *, limit: int = 3) -> str:
    parts: List[str] = []
    for row in rows[:limit]:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        parts.append(
            f"{name} ({row.get('count')}, win {float(row.get('win_rate') or 0.0) * 100:.1f}%, "
            f"avg {float(row.get('avg_return_pct') or 0.0):.2f}%, 비용역전 {row.get('cost_drag_loss_count') or 0}건)"
        )
    return f"- {label}: {', '.join(parts) if parts else 'none'}"


def _render_pattern_performance_lines(payload: Dict[str, Any]) -> List[str]:
    perf = payload.get("pattern_performance") if isinstance(payload.get("pattern_performance"), dict) else {}
    if not perf or int(perf.get("trade_count") or 0) <= 0:
        return []
    lines = [
        "",
        "---",
        "",
        "## Pattern Performance",
        "",
        _pattern_perf_line("Strategist tactical", _pattern_perf_rows(perf, "strategist", "by_tactical_strategy")),
        _pattern_perf_line("Strategist horizon", _pattern_perf_rows(perf, "strategist", "by_strategy_horizon")),
        _pattern_perf_line("Scanner rank", _pattern_perf_rows(perf, "scanner", "by_scanner_rank_bucket")),
        _pattern_perf_line("Monitor entry", _pattern_perf_rows(perf, "monitor_entry", "by_entry_pattern_type")),
        _pattern_perf_line("Monitor exit", _pattern_perf_rows(perf, "monitor_exit", "by_exit_pattern_type")),
        _pattern_perf_line("Quant tactic", _pattern_perf_rows(perf, "quant", "by_tactic_id")),
        _pattern_perf_line("Quant entry blockers", _pattern_perf_rows(perf, "quant", "by_entry_primary_blocker")),
        _pattern_perf_line("Quant exit quality", _pattern_perf_rows(perf, "quant", "by_exit_decision")),
        _pattern_perf_line(
            "Combined",
            _pattern_perf_rows(perf, "combined", "by_strategy_scanner_entry_exit"),
            limit=2,
        ),
    ]
    quant_eval = payload.get("quant_tactic_evaluation")
    if isinstance(quant_eval, dict):
        lines += [""] + render_quant_tactic_evaluation_lines(quant_eval)
    return lines


def _render_quant_shadow_candidate_lines(payload: Dict[str, Any]) -> List[str]:
    shadow_eval = payload.get("quant_shadow_candidate_evaluation")
    if not isinstance(shadow_eval, dict):
        return []
    return render_quant_shadow_candidate_evaluation_lines(shadow_eval)


def _render_strategist_llm_evaluation_lines(payload: Dict[str, Any]) -> List[str]:
    evaluation = payload.get("strategist_llm_evaluation")
    if not isinstance(evaluation, dict):
        return []
    return render_strategist_llm_evaluation_lines(evaluation)


def render_operator_period_summary_markdown(payload: Dict[str, Any]) -> str:
    period_type = str(payload.get("period_type") or "").strip().lower()
    period_label = "Weekly" if period_type == "weekly" else "Monthly"
    period_key = str(payload.get("period_key") or "")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    patterns = payload.get("patterns") if isinstance(payload.get("patterns"), dict) else {}
    readout = payload.get("operator_readout") if isinstance(payload.get("operator_readout"), dict) else {}
    date_range = payload.get("date_range") if isinstance(payload.get("date_range"), dict) else {}
    symbols = payload.get("symbol_summary") if isinstance(payload.get("symbol_summary"), list) else []

    lines = [
        f"# {period_label} Summary ({period_key})",
        "",
        "---",
        "",
        "## 운영 요약",
        "",
        f"- 기간: {date_range.get('start') or '-'} ~ {date_range.get('end') or '-'}",
        f"- 총 거래: {_safe_int(metrics.get('trade_count'))}건",
        f"- 완료 거래: {_safe_int(metrics.get('closed_trade_count'))}건",
        f"- 성과: **승률 {float(metrics.get('win_rate') or 0.0) * 100:.2f}% / 평균 {float(metrics.get('avg_return_pct') or 0.0):.2f}%**",
        "",
        "### 잘된 점",
    ]
    if _safe_int(metrics.get("realized_exit_count")) > 0:
        lines.insert(
            -2,
            f"- 완료 외 실현 청산(회수/partial 포함): {_safe_int(metrics.get('realized_exit_count'))}건 / "
            f"승패 {_safe_int(metrics.get('realized_exit_win_count'))}/{_safe_int(metrics.get('realized_exit_loss_count'))} / "
            f"평균 {float(metrics.get('realized_exit_avg_return_pct') or 0.0):.2f}%",
        )
    for item in list(readout.get("good_points") or []):
        lines.append(f"- {item}")
    lines += ["", "### 문제점"]
    for idx, item in enumerate(list(readout.get("issues") or []), start=1):
        lines.append(f"{idx}. {item}")
    lines += [
        "",
        "### 원인 해석",
        f"**{readout.get('root_cause') or '-'}**",
        "",
        "### 권고 액션",
    ]
    for idx, item in enumerate(list(readout.get("recommended_actions") or []), start=1):
        lines.append(f"{idx}. {item}")

    lines += ["", "---", "", "## 반복 패턴", ""]
    for label, key in (
        ("주요 진입 사유", "top_entry_reasons"),
        ("주요 청산 사유", "top_exit_reasons"),
        ("진입 패턴", "top_entry_pattern_types"),
        ("청산 패턴", "top_exit_pattern_types"),
        ("플레이북", "top_playbooks"),
    ):
        rows = patterns.get(key) if isinstance(patterns.get(key), list) else []
        text = ", ".join(f"{row.get('name')} ({row.get('count')})" for row in rows[:3] if isinstance(row, dict))
        lines.append(f"- {label}: {text or '없음'}")
    lines.extend(_render_pattern_performance_lines(payload))
    lines.extend(_render_quant_shadow_candidate_lines(payload))
    lines.extend(_render_strategist_llm_evaluation_lines(payload))

    lines += ["", "---", "", "## 주요 종목", ""]
    if not symbols:
        lines.append("- 기간 내 종목별 요약이 없습니다.")
    for row in symbols[:8]:
        if not isinstance(row, dict):
            continue
        realized_suffix = ""
        if _safe_int(row.get("realized_exit_count")) > 0:
            realized_suffix = (
                f" / 회수청산 {row.get('realized_exit_count')}건 "
                f"{row.get('realized_exit_win_count')}/{row.get('realized_exit_loss_count')} "
                f"평균 {float(row.get('realized_exit_avg_return_pct') or 0.0):.2f}%"
            )
        lines.append(
            f"- {row.get('symbol')}: 거래 {row.get('trade_count')}건 / 완료 {row.get('closed_trade_count')}건 / "
            f"승패 {row.get('win_count')}/{row.get('loss_count')} / 평균 {float(row.get('avg_return_pct') or 0.0):.2f}%"
            f"{realized_suffix}"
        )

    lines += [
        "",
        "---",
        "",
        "## 상세 분석",
        "",
        "> 기간별 운영 요약은 reports/operator_summary/symbols/*/trade_history.json 집계를 기준으로 생성됩니다.",
        "",
    ]
    return "\n".join(lines)


def render_operator_daily_summary_markdown(payload: Dict[str, Any]) -> str:
    day = str(payload.get("day") or "")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    runtime = payload.get("runtime_activity") if isinstance(payload.get("runtime_activity"), dict) else {}
    patterns = payload.get("patterns") if isinstance(payload.get("patterns"), dict) else {}
    readout = payload.get("operator_readout") if isinstance(payload.get("operator_readout"), dict) else {}
    symbols = payload.get("symbol_summary") if isinstance(payload.get("symbol_summary"), list) else []
    residual = payload.get("residual_positions") if isinstance(payload.get("residual_positions"), dict) else {}
    residual_positions = residual.get("positions") if isinstance(residual.get("positions"), list) else []

    lines = [
        f"# Daily Summary ({day})",
        "",
        "---",
        "",
        "## 운영 요약",
        "",
        f"- 총 거래: {_safe_int(metrics.get('trade_count'))}건",
        f"- 완료 거래: {_safe_int(metrics.get('closed_trade_count'))}건",
        f"- 성과: **승률 {float(metrics.get('win_rate') or 0.0) * 100:.2f}% / 평균 {float(metrics.get('avg_return_pct') or 0.0):.2f}%**",
        (
            "- 런타임 이벤트: 미집계"
            if str(runtime.get("source") or "") == "not_available"
            else f"- 런타임 이벤트: {runtime.get('events') or 0}건"
        ),
        (
            "- 승인/차단: 미집계"
            if str(runtime.get("source") or "") == "not_available"
            else f"- 승인/차단: {runtime.get('approvals') or 0} / {runtime.get('blocks') or 0}"
        ),
        "",
        "### 잘된 점",
    ]
    if _safe_int(metrics.get("realized_exit_count")) > 0:
        lines.insert(
            -4,
            f"- 완료 외 실현 청산(회수/partial 포함): {_safe_int(metrics.get('realized_exit_count'))}건 / "
            f"승패 {_safe_int(metrics.get('realized_exit_win_count'))}/{_safe_int(metrics.get('realized_exit_loss_count'))} / "
            f"평균 {float(metrics.get('realized_exit_avg_return_pct') or 0.0):.2f}%",
        )
    for item in list(readout.get("good_points") or []):
        lines.append(f"- {item}")
    lines += ["", "### 문제점"]
    for idx, item in enumerate(list(readout.get("issues") or []), start=1):
        lines.append(f"{idx}. {item}")
    lines += [
        "",
        "### 원인 해석",
        f"**{readout.get('root_cause') or '-'}**",
        "",
        "### 권고 액션",
    ]
    for idx, item in enumerate(list(readout.get("recommended_actions") or []), start=1):
        lines.append(f"{idx}. {item}")

    lines += ["", "---", "", "## 장마감 잔여 보유 종목", ""]
    account_snapshot = (
        residual.get("account_snapshot_reconciliation")
        if isinstance(residual.get("account_snapshot_reconciliation"), dict)
        else {}
    )
    if account_snapshot:
        snapshot_status = (
            "fresh_after_1520"
            if bool(account_snapshot.get("fresh_after_closeout_window"))
            else "stale_or_unavailable"
        )
        snapshot_time = str(account_snapshot.get("generated_at_kst") or "").strip()
        snapshot_position_count = _safe_int(account_snapshot.get("position_count"))
        lines.append(
            f"- account snapshot: {snapshot_status} / positions {snapshot_position_count}"
            + (f" / {snapshot_time}" if snapshot_time else "")
        )
    if not bool(residual.get("available")):
        lines.append("- 상태 스냅샷을 읽지 못해 잔여 보유 종목을 확인하지 못했습니다.")
    elif not residual_positions:
        lines.append("- 장마감 기준 잔여 보유 종목이 없습니다.")
        reconciled = (
            residual.get("reconciled_closed_positions")
            if isinstance(residual.get("reconciled_closed_positions"), list)
            else []
        )
        reconciled_symbols_text = ", ".join(
            str(row.get("symbol") or "").strip()
            for row in reconciled
            if isinstance(row, dict) and str(row.get("symbol") or "").strip()
        )
        if reconciled_symbols_text:
            lines.append(f"- 장중 청산 확인: {reconciled_symbols_text}은 당일 전량 매도 기록으로 잔여 보유에서 제외했습니다.")
    else:
        closeout = residual.get("closeout_state") if isinstance(residual.get("closeout_state"), dict) else {}
        reconciled = (
            residual.get("reconciled_closed_positions")
            if isinstance(residual.get("reconciled_closed_positions"), list)
            else []
        )
        closeout_mode = str(closeout.get("mode") or "").strip()
        closeout_reason = str(closeout.get("reason") or "").strip()
        if closeout_mode or closeout_reason:
            closeout_line = f"- closeout 상태: {closeout_mode or '-'} / {closeout_reason or '-'}"
            closeout_note = str(closeout.get("report_note") or "").strip()
            if closeout_note:
                closeout_line += f" ({closeout_note})"
            lines.append(closeout_line)
        if reconciled:
            reconciled_symbols_text = ", ".join(
                str(row.get("symbol") or "").strip()
                for row in reconciled
                if isinstance(row, dict) and str(row.get("symbol") or "").strip()
            )
            if reconciled_symbols_text:
                lines.append(f"- 장중 청산 확인: {reconciled_symbols_text}은 당일 전량 매도 기록으로 잔여 보유에서 제외했습니다.")
        for row in residual_positions:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "-")
            status = str(row.get("status") or "잔여 보유")
            qty = _safe_int(row.get("qty"))
            avg_price = row.get("avg_price")
            current_price = row.get("current_price")
            pnl_ratio = row.get("account_pnl_ratio")
            reason = str(row.get("overnight_reason") or "").strip()
            decision_label = str(row.get("overnight_decision_label") or "").strip()
            signals = [str(x) for x in list(row.get("overnight_positive_signals") or []) if str(x or "").strip()]
            blockers = [str(x) for x in list(row.get("overnight_blockers") or []) if str(x or "").strip()]
            price_text = f"평균 {avg_price:,.0f}" if isinstance(avg_price, (int, float)) and avg_price else "평균 -"
            current_text = f"현재 {current_price:,.0f}" if isinstance(current_price, (int, float)) and current_price else "현재 -"
            ratio_text = f" / 평가손익률 {float(pnl_ratio) * 100:.2f}%" if isinstance(pnl_ratio, (int, float)) else ""
            detail = f"- {symbol}: {status} / {qty}주 / {price_text} / {current_text}{ratio_text}"
            if decision_label:
                detail += f" / 오버나이트 판단: {decision_label}"
            if reason and not bool(row.get("overnight_decision_missing")):
                detail += f" / 사유 {reason}"
            if bool(row.get("weekend_carry")):
                detail += f" / 주말보유 {int(row.get('holding_gap_days') or 3)}일"
            lines.append(detail)
            if bool(row.get("weekend_carry")) and not bool(row.get("allow_weekend_carry")):
                lines.append("  - 주의: 금요일 carry 승인이라 주말 갭 리스크가 포함됩니다.")
            missing_detail = str(row.get("overnight_missing_detail") or "").strip()
            if bool(row.get("overnight_decision_missing")) and missing_detail:
                lines.append(f"  - 판단 기록 근거: {missing_detail}")
            if signals:
                lines.append(f"  - 승인 근거: {', '.join(signals[:5])}")
            if blockers:
                lines.append(f"  - 차단/주의 근거: {', '.join(blockers[:5])}")

    lines += ["", "---", "", "## 핵심 패턴", ""]
    for label, key in (
        ("주요 진입 사유", "top_entry_reasons"),
        ("주요 청산 사유", "top_exit_reasons"),
        ("진입 패턴", "top_entry_pattern_types"),
        ("청산 패턴", "top_exit_pattern_types"),
    ):
        rows = patterns.get(key) if isinstance(patterns.get(key), list) else []
        text = ", ".join(f"{row.get('name')} ({row.get('count')})" for row in rows[:3] if isinstance(row, dict))
        lines.append(f"- {label}: {text or '없음'}")
    lines.extend(_render_pattern_performance_lines(payload))
    lines.extend(_render_quant_shadow_candidate_lines(payload))
    lines.extend(_render_strategist_llm_evaluation_lines(payload))

    lines += ["", "---", "", "## 종목별 요약", ""]
    if not symbols:
        lines.append("- 당일 종목별 요약이 없습니다.")
    for row in symbols[:8]:
        if not isinstance(row, dict):
            continue
        realized_suffix = ""
        if _safe_int(row.get("realized_exit_count")) > 0:
            realized_suffix = (
                f" / 회수청산 {row.get('realized_exit_count')}건 "
                f"{row.get('realized_exit_win_count')}/{row.get('realized_exit_loss_count')} "
                f"평균 {float(row.get('realized_exit_avg_return_pct') or 0.0):.2f}%"
            )
        lines.append(
            f"- {row.get('symbol')}: 거래 {row.get('trade_count')}건 / 완료 {row.get('closed_trade_count')}건 / "
            f"승패 {row.get('win_count')}/{row.get('loss_count')} / 평균 {float(row.get('avg_return_pct') or 0.0):.2f}%"
            f"{realized_suffix}"
        )

    lines += [
        "",
        "---",
        "",
        "## 상세 분석",
        "",
        "> 세부 거래 및 로그 기반 분석은 같은 일자의 daily_report.md와 개별 ai_trade_report.md를 참조합니다.",
        "",
    ]
    return "\n".join(lines)


def render_operator_symbol_summary_markdown(payload: Dict[str, Any]) -> str:
    symbol = str(payload.get("symbol") or "")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    patterns = payload.get("patterns") if isinstance(payload.get("patterns"), dict) else {}
    readout = payload.get("operator_readout") if isinstance(payload.get("operator_readout"), dict) else {}
    memory = payload.get("symbol_memory") if isinstance(payload.get("symbol_memory"), dict) else {}
    risk_notes = list(payload.get("risk_notes") or [])

    lines = [
        f"# Symbol Summary ({symbol})",
        "",
        "---",
        "",
        "## 운영 요약",
        "",
        f"- 총 거래: {_safe_int(metrics.get('trade_count'))}건",
        f"- 완료 거래: {_safe_int(metrics.get('closed_trade_count'))}건",
        f"- 성과: **승률 {float(metrics.get('win_rate') or 0.0) * 100:.2f}% / 평균 {float(metrics.get('avg_return_pct') or 0.0):.2f}%**",
        "",
        "### 잘된 점",
    ]
    if _safe_int(metrics.get("realized_exit_count")) > 0:
        lines.insert(
            -2,
            f"- 완료 외 실현 청산(회수/partial 포함): {_safe_int(metrics.get('realized_exit_count'))}건 / "
            f"승패 {_safe_int(metrics.get('realized_exit_win_count'))}/{_safe_int(metrics.get('realized_exit_loss_count'))} / "
            f"평균 {float(metrics.get('realized_exit_avg_return_pct') or 0.0):.2f}%",
        )
    for item in list(readout.get("good_points") or []):
        lines.append(f"- {item}")
    lines += ["", "### 문제점"]
    for idx, item in enumerate(list(readout.get("issues") or []), start=1):
        lines.append(f"{idx}. {item}")
    lines += [
        "",
        "### 원인 해석",
        f"**{readout.get('root_cause') or '-'}**",
        "",
        "### 권고 액션",
    ]
    for idx, item in enumerate(list(readout.get("recommended_actions") or []), start=1):
        lines.append(f"{idx}. {item}")

    lines += ["", "---", "", "## 패턴 분석", ""]
    for label, key in (
        ("주요 진입 사유", "top_entry_reasons"),
        ("주요 청산 사유", "top_exit_reasons"),
        ("진입 패턴", "top_entry_pattern_types"),
        ("청산 패턴", "top_exit_pattern_types"),
        ("플레이북", "top_playbooks"),
    ):
        rows = patterns.get(key) if isinstance(patterns.get(key), list) else []
        text = ", ".join(f"{row.get('name')} ({row.get('count')})" for row in rows[:3] if isinstance(row, dict))
        lines.append(f"- {label}: {text or '없음'}")
    lines.extend(_render_pattern_performance_lines(payload))
    lines.extend(_render_quant_shadow_candidate_lines(payload))
    lines.extend(_render_strategist_llm_evaluation_lines(payload))

    bias = memory.get("bias_recommendation") if isinstance(memory.get("bias_recommendation"), dict) else {}
    if bias or risk_notes:
        lines += ["", "---", "", "## 거래 특징", ""]
        if bias:
            lines.append(f"- 메모리 bias: {json.dumps(bias, ensure_ascii=False)}")
        for note in risk_notes:
            lines.append(f"- 리스크 메모: {note}")

    lines += [
        "",
        "---",
        "",
        "## 상세 분석",
        "",
        "> 개별 ai_trade_report.md와 symbol_trade_report.md를 참조합니다.",
        "",
    ]
    return "\n".join(lines)


def generate_operator_period_summary(
    *,
    reports_root: Path,
    period_type: str,
    period_key: str,
) -> Tuple[Path, Path, Dict[str, Any]]:
    payload = build_operator_period_summary(
        reports_root=reports_root,
        period_type=period_type,
        period_key=period_key,
    )
    if payload["period_type"] == "weekly":
        paths = weekly_artifact_paths(reports_root, payload["period_key"])
        json_path = paths["weekly_summary_json"]
        md_path = paths["weekly_summary_md"]
    else:
        paths = monthly_artifact_paths(reports_root, payload["period_key"])
        json_path = paths["monthly_summary_json"]
        md_path = paths["monthly_summary_md"]

    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_operator_period_summary_markdown(payload), encoding="utf-8")
    return md_path, json_path, payload


def generate_operator_daily_summary_artifact(
    *,
    reports_root: Path,
    day: str,
    daily_report_payload: Dict[str, Any] | None = None,
) -> Tuple[Path, Path, Dict[str, Any]]:
    if daily_report_payload is None:
        daily_report_path = daily_artifact_paths(reports_root, str(day or "").strip())["daily_report_json"]
        loaded = _read_json(daily_report_path)
        daily_report_payload = loaded if isinstance(loaded, dict) else None
    payload = build_operator_daily_summary_artifact_payload(
        reports_root=reports_root,
        day=day,
        daily_report_payload=daily_report_payload,
    )
    paths = daily_artifact_paths(reports_root, payload["day"])
    json_path = paths["daily_summary_json"]
    md_path = paths["daily_summary_md"]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    payload["performance_memory_sync"] = sync_strategy_memory_artifacts(
        reports_root=reports_root,
        day=payload["day"],
        source="operator_daily_summary",
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_operator_daily_summary_markdown(payload), encoding="utf-8")
    return md_path, json_path, payload


def generate_operator_symbol_summary_artifact(
    *,
    reports_root: Path,
    symbol: str,
    symbol_trade_report_payload: Dict[str, Any] | None = None,
    symbol_memory_payload: Dict[str, Any] | None = None,
) -> Tuple[Path, Path, Dict[str, Any]]:
    payload = build_operator_symbol_summary_artifact_payload(
        reports_root=reports_root,
        symbol=symbol,
        symbol_trade_report_payload=symbol_trade_report_payload,
        symbol_memory_payload=symbol_memory_payload,
    )
    paths = symbol_artifact_paths(reports_root, payload["symbol"])
    json_path = paths["symbol_summary_json"]
    md_path = paths["symbol_summary_md"]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_operator_symbol_summary_markdown(payload), encoding="utf-8")
    return md_path, json_path, payload
