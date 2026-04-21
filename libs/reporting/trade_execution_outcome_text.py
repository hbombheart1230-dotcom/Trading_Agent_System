from __future__ import annotations

from typing import Any, Dict, List


def _clip(value: Any, *, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _fmt_price(value: Any) -> str:
    try:
        if value in (None, ""):
            return "-"
        return f"{float(value):.2f}"
    except Exception:
        return "-"


def _action_label(value: Any) -> str:
    token = str(value or "").strip().upper()
    return {
        "BUY": "매수",
        "SELL": "매도",
        "HOLD": "보유",
        "WAIT": "대기",
        "NONE": "대기",
    }.get(token, token or "대기")


def _mode_label(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    if "simulation" in token or "mock" in token:
        return "시뮬레이션"
    if "real" in token or "live" in token:
        return "실거래"
    return _clip(value, max_len=60)


def _qty_text(value: Any) -> str:
    qty = _safe_int(value, 0)
    return f"{qty}주" if qty > 0 else "주문"


def _pick_order_id(*candidates: Any) -> str:
    for candidate in candidates:
        if isinstance(candidate, dict):
            value = candidate.get("ord_no") or candidate.get("order_id")
        else:
            value = candidate
        text = _clip(value, max_len=120)
        if text:
            return text
    return ""


def _pick_price(*candidates: Any) -> str:
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("filled_price", "avg_price", "price"):
                value = _fmt_price(candidate.get(key))
                if value != "-":
                    return value
        else:
            value = _fmt_price(candidate)
            if value != "-":
                return value
    return "-"


def execution_outcome_summary_is_placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    placeholders = (
        "execution outcome summary was not captured",
        "execution outcome summary was 기록되지 않음",
        "거래 생애주기 실행 요약은 기록되지 않았습니다",
        "실행 품질 세부 정보는 제한적으로만 확인됩니다",
    )
    return any(token in text for token in placeholders)


def build_execution_outcome_human_payload(
    execution: Dict[str, Any],
    executor: Dict[str, Any],
    *,
    story_type: str,
    mode_label: str,
) -> Dict[str, Any]:
    action = str(execution.get("action") or "").upper() or "WAIT"
    action_label = _action_label(action)
    symbol = _clip(execution.get("symbol"), max_len=24) or "대상 종목"
    qty_value = execution.get("qty") or execution.get("filled_qty") or executor.get("filled_qty")
    qty_text = _qty_text(qty_value)
    status_text = _clip(execution.get("status") or executor.get("broker_message"), max_len=120)
    order_id = _pick_order_id(execution, executor)
    filled_price = _pick_price(execution, executor)
    broker_env = _clip(executor.get("broker_env") or execution.get("broker_env"), max_len=80)
    mode_text = _mode_label(mode_label or execution.get("execution_mode") or executor.get("execution_mode"))

    if story_type == "simulation":
        summary = f"{symbol} {qty_text} {action_label} 주문은 시뮬레이션으로 승인 및 기록됐습니다."
        outcome = "recorded"
    elif story_type == "failed_execution":
        summary = f"{symbol} {qty_text} {action_label} 주문은 시도됐지만 정상 체결로 이어지지 않았습니다."
        outcome = "failed"
    elif story_type == "live_trade":
        if filled_price != "-":
            summary = f"{symbol} {qty_text} {action_label} 주문은 실거래로 체결됐고 체결 기준 가격은 {filled_price}였습니다."
        else:
            summary = f"{symbol} {qty_text} {action_label} 주문은 실거래로 접수 및 처리됐습니다."
        outcome = "filled"
    else:
        if order_id or status_text:
            summary = f"{symbol} {qty_text} {action_label} 주문 실행 흔적은 확인되지만 체결 상세는 제한적으로만 남아 있습니다."
        else:
            summary = f"{symbol} 주문 실행은 별도로 확인되지 않았습니다."
        outcome = "decision_only"

    bullets: List[str] = [f"실행 결과는 {outcome}입니다."]
    if _safe_int(qty_value, 0) > 0:
        bullets.append(f"주문 수량은 {_safe_int(qty_value, 0)}주였습니다.")
    if mode_text:
        bullets.append(f"실행 모드는 {mode_text}였습니다.")
    if broker_env:
        bullets.append(f"브로커 환경은 {broker_env}였습니다.")
    if status_text:
        bullets.append(f"주문 상태는 {status_text}였습니다.")
    if order_id:
        bullets.append(f"주문 번호는 {order_id}였습니다.")
    if filled_price != "-":
        bullets.append(f"체결 기준 가격은 {filled_price}였습니다.")
    return {
        "summary": summary,
        "outcome": outcome,
        "quantity": _safe_int(qty_value, 0),
        "status_text": status_text,
        "bullets": bullets,
    }


def build_execution_outcome_fallback_from_lifecycle(
    entry: Dict[str, Any],
    exit_ctx: Dict[str, Any],
    *,
    status: str,
    entry_action: str,
    exit_action: str,
    symbol: str,
) -> Dict[str, Any]:
    entry_exec = entry.get("execution_details") if isinstance(entry.get("execution_details"), dict) else {}
    exit_exec = exit_ctx.get("execution_details") if isinstance(exit_ctx.get("execution_details"), dict) else {}
    symbol_label = _clip(symbol, max_len=24) or "대상 종목"
    entry_label = _action_label(entry_action or "BUY")
    exit_label = _action_label(exit_action or "SELL")
    entry_price = _pick_price(entry_exec, entry)
    exit_price = _pick_price(exit_exec, exit_ctx)
    entry_order = _pick_order_id(entry_exec, entry)
    exit_order = _pick_order_id(exit_exec, exit_ctx)

    status_token = str(status or "").strip().lower()
    if status_token == "closed" or exit_action:
        summary = f"{symbol_label} 거래는 {entry_label} 진입 후 {exit_label} 청산까지 기록됐습니다."
        if entry_price != "-" and exit_price != "-":
            summary += f" 브로커 매수가/매도가는 {entry_price} / {exit_price}였습니다."
        elif exit_price != "-":
            summary += f" 청산 체결 기준 가격은 {exit_price}였습니다."
        elif entry_price != "-":
            summary += f" 진입 체결 기준 가격은 {entry_price}였습니다."
    elif entry_order or entry_price != "-":
        summary = f"{symbol_label} 거래는 {entry_label} 진입이 기록됐고 현재 포지션은 아직 열려 있습니다."
        if entry_price != "-":
            summary += f" 진입 체결 기준 가격은 {entry_price}였습니다."
    else:
        summary = f"{symbol_label} 거래의 주문 실행 흔적은 일부 확인되며 후행 체결 점검이 필요합니다."

    bullets: List[str] = [
        f"라이프사이클 상태는 {_clip(status, max_len=40) or 'not_captured'}입니다.",
        f"진입 액션은 {_clip(entry_action, max_len=40) or 'not_captured'}입니다.",
        f"청산 액션은 {_clip(exit_action, max_len=40) or 'not_captured'}입니다.",
    ]
    if entry_order:
        bullets.append(f"진입 주문 번호는 {entry_order}였습니다.")
    if exit_order:
        bullets.append(f"청산 주문 번호는 {exit_order}였습니다.")
    if entry_price != "-":
        bullets.append(f"진입 체결 기준 가격은 {entry_price}였습니다.")
    if exit_price != "-":
        bullets.append(f"청산 체결 기준 가격은 {exit_price}였습니다.")
    return {"summary": summary, "bullets": bullets}
