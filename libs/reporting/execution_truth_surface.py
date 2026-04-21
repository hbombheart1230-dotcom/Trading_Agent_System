from __future__ import annotations

from typing import Any, Dict, List

from libs.reporting.truth_source_labels import (
    pnl_truth_source_label,
    price_truth_source_label,
    with_ro_particle,
)


def _clip(value: Any, *, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:max_len]


def _fmt_price(value: Any) -> str:
    try:
        if value in (None, ""):
            return "-"
        return f"{float(value):.2f}"
    except Exception:
        return str(value or "-")


def _fmt_pct(value: Any) -> str:
    try:
        if value in (None, ""):
            return "-"
        return f"{float(value) * 100:.2f}%"
    except Exception:
        return str(value or "-")


def _is_available(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text not in {"", "unavailable", "not_available", "none", "-"}


def build_execution_truth_bullets(
    *,
    execution_details: Dict[str, Any] | None = None,
    shared_facts: Dict[str, Any] | None = None,
) -> List[str]:
    details = dict(execution_details or {})
    facts = dict(shared_facts or {})

    broker_truth_source = _clip(details.get("broker_truth_source"), max_len=80)
    broker_fill_price = details.get("filled_price") if broker_truth_source else facts.get("broker_fill_price")
    broker_fee = details.get("broker_fee") if details.get("broker_fee") not in (None, "") else facts.get("broker_fee")
    broker_tax = details.get("broker_tax") if details.get("broker_tax") not in (None, "") else facts.get("broker_tax")
    pnl_value = details.get("broker_realized_pnl") if details.get("broker_realized_pnl") not in (None, "") else facts.get("pnl")
    pnl_pct = details.get("broker_realized_pnl_pct") if details.get("broker_realized_pnl_pct") not in (None, "") else facts.get("pnl_pct")
    price_truth_source = _clip(facts.get("price_truth_source"), max_len=40)
    pnl_truth_source = _clip(details.get("pnl_truth_source") or facts.get("pnl_truth_source"), max_len=80)

    bullets: List[str] = []
    if broker_fill_price not in (None, ""):
        bullets.append(f"브로커 체결 기준 가격은 {_fmt_price(broker_fill_price)}였습니다.")
    if _is_available(pnl_value):
        if pnl_pct not in (None, ""):
            bullets.append(f"브로커 실현 손익은 {pnl_value} / {_fmt_pct(pnl_pct)} 기준으로 정리했습니다.")
        else:
            bullets.append(f"브로커 실현 손익은 {pnl_value} 기준으로 정리했습니다.")
    if broker_fee not in (None, "") or broker_tax not in (None, ""):
        bullets.append(
            f"브로커 수수료/세금은 {broker_fee if broker_fee not in (None, '') else '-'} / {broker_tax if broker_tax not in (None, '') else '-'}였습니다."
        )
    if broker_truth_source:
        bullets.append(f"체결 truth 소스는 {broker_truth_source}였습니다.")
    if price_truth_source and price_truth_source not in {"", "unavailable"}:
        bullets.append(f"가격 truth 소스는 {with_ro_particle(price_truth_source_label(price_truth_source))} 확인했습니다.")
    if pnl_truth_source and pnl_truth_source not in {"", "unavailable"}:
        bullets.append(f"손익 truth 소스는 {with_ro_particle(pnl_truth_source_label(pnl_truth_source))} 확인했습니다.")
    return bullets
