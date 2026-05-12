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


def _overnight_missing_context(raw_row: Dict[str, Any], monitor_state: Dict[str, Any]) -> Dict[str, Any]:
    position_entry_text = _epoch_to_kst_text(raw_row.get("position_entry_epoch"))
    if not isinstance(monitor_state, dict) or not monitor_state:
        out: Dict[str, Any] = {
            "overnight_missing_reason_code": "no_monitor_state_for_residual_position",
            "overnight_missing_detail": "모니터 상태 기록 없음; EOD 전체 보유 종목 재점검 필요",
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
    if updated_epoch > 0:
        try:
            kst = timezone(timedelta(hours=9))
            updated_dt = datetime.fromtimestamp(updated_epoch, tz=timezone.utc).astimezone(kst)
            eod_window_start = updated_dt.replace(hour=15, minute=20, second=0, microsecond=0)
            market_close = updated_dt.replace(hour=15, minute=30, second=0, microsecond=0)
            if updated_dt < eod_window_start:
                reason_code = "last_monitor_before_eod_window_no_later_review"
                detail_parts.append("EOD 판단창(15:20 이후) 재점검 없음")
            elif updated_dt <= market_close:
                reason_code = "last_monitor_inside_eod_window_without_persisted_decision"
                detail_parts.append("EOD 판단창 내 평가 기록 저장 누락 가능")
            else:
                reason_code = "last_monitor_after_market_close_without_persisted_decision"
                detail_parts.append("장마감 후 평가 기록 저장 누락 가능")
        except Exception:
            pass

    out = {
        "overnight_missing_reason_code": reason_code,
        "overnight_missing_detail": " / ".join(detail_parts) if detail_parts else "오버나이트 판단 저장 기록 없음",
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
    positions: List[Dict[str, Any]] = []
    reconciled_closed: List[Dict[str, Any]] = []
    for raw_row in raw_positions:
        if not isinstance(raw_row, dict):
            continue
        symbol = str(raw_row.get("symbol") or "").strip().upper()
        qty = _safe_int(raw_row.get("qty"))
        if not symbol or qty <= 0:
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
        positions.append(row)

    reconciled_symbols = {str(row.get("symbol") or "").strip().upper() for row in reconciled_closed}
    carry_forward_symbols = [
        item
        for item in list(closeout.get("carry_forward_symbols") or [])
        if str(item or "").strip().upper() not in reconciled_symbols
    ]

    return {
        "available": True,
        "source": "state_snapshot",
        "source_path": state_path,
        "position_count": len(positions),
        "positions": positions,
        "reconciled_closed_positions": reconciled_closed,
        "closeout_state": {
            "mode": str(closeout.get("mode") or ""),
            "reason": str(closeout.get("reason") or ""),
            "applied_at": str(closeout.get("applied_at") or ""),
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
    summary_input = summary_input if isinstance(summary_input, dict) else {}
    summary_report = summary_report if isinstance(summary_report, dict) else {}
    full_report = full_report if isinstance(full_report, dict) else {}

    decision_flow = summary_input.get("decision_flow") if isinstance(summary_input.get("decision_flow"), dict) else {}
    if not decision_flow:
        decision_flow = summary_report.get("decision_flow") if isinstance(summary_report.get("decision_flow"), dict) else {}
    shared_facts = full_report.get("shared_facts") if isinstance(full_report.get("shared_facts"), dict) else {}
    if not shared_facts:
        shared_facts = summary_input.get("shared_facts") if isinstance(summary_input.get("shared_facts"), dict) else {}

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
    return out


def _operator_reason_name(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower().strip()
    if lowered.startswith("entry evidence was not captured"):
        return ""
    if lowered.startswith("entry context was recovered"):
        return ""
    if "position is still open" in lowered or "포지션은 아직 열려" in raw:
        return ""
    if "청산 근거가 누락" in raw:
        return ""
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
    if "position is still open" in lowered or "포지션은 아직 열려" in raw:
        return ""
    if "청산 근거가 누락" in raw:
        return ""
    if lowered in {"", "-", "no", "none", "unknown", "no_position", "no position"}:
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
    if trade_index:
        rows = _daily_trade_index_rows(reports_root=reports_root, trade_index=trade_index)
    else:
        rows = [
            row
            for row in _iter_symbol_trade_history(reports_root)
            if str(row.get("date") or "").strip() == normalized_day
        ]
    rows = _enrich_rows_with_truth_surface(rows, reports_root)
    metrics = _trade_metrics(rows)
    counters = _pattern_counters(rows)
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
    if not bool(residual.get("available")):
        lines.append("- 상태 스냅샷을 읽지 못해 잔여 보유 종목을 확인하지 못했습니다.")
    elif not residual_positions:
        lines.append("- 장마감 기준 잔여 보유 종목이 없습니다.")
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
            lines.append(f"- closeout 상태: {closeout_mode or '-'} / {closeout_reason or '-'}")
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
            signals = [str(x) for x in list(row.get("overnight_positive_signals") or []) if str(x or "").strip()]
            blockers = [str(x) for x in list(row.get("overnight_blockers") or []) if str(x or "").strip()]
            price_text = f"평균 {avg_price:,.0f}" if isinstance(avg_price, (int, float)) and avg_price else "평균 -"
            current_text = f"현재 {current_price:,.0f}" if isinstance(current_price, (int, float)) and current_price else "현재 -"
            ratio_text = f" / 평가손익률 {float(pnl_ratio) * 100:.2f}%" if isinstance(pnl_ratio, (int, float)) else ""
            detail = f"- {symbol}: {status} / {qty}주 / {price_text} / {current_text}{ratio_text}"
            if reason:
                detail += f" / 사유 {reason}"
            if bool(row.get("weekend_carry")):
                detail += f" / 주말보유 {int(row.get('holding_gap_days') or 3)}일"
            lines.append(detail)
            if bool(row.get("weekend_carry")) and not bool(row.get("allow_weekend_carry")):
                lines.append("  - 주의: 금요일 carry 승인이라 주말 갭 리스크가 포함됩니다.")
            missing_detail = str(row.get("overnight_missing_detail") or "").strip()
            if bool(row.get("overnight_decision_missing")) and missing_detail:
                lines.append(f"  - 판단 기록 상태: {missing_detail}")
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
