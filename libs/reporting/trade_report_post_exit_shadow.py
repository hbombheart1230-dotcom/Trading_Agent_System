from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}

def post_exit_shadow_surface(report: Dict[str, Any]) -> Dict[str, Any]:
    fact_payload = as_dict(report.get("fact_payload"))
    fact_trade = as_dict(fact_payload.get("trade"))
    lifecycle = as_dict(report.get("lifecycle"))
    lifecycle_exit = as_dict(lifecycle.get("exit"))
    lifecycle_bundle = as_dict(report.get("lifecycle_bundle"))
    for candidate in (
        report.get("post_exit_shadow"),
        fact_trade.get("post_exit_shadow"),
        lifecycle.get("post_exit_shadow"),
        lifecycle_exit.get("post_exit_shadow"),
        lifecycle_bundle.get("post_exit_shadow"),
    ):
        obj = as_dict(candidate)
        if obj:
            return obj
    return {}


def checkpoint_label(value: str) -> str:
    mapping = {
        "+5m": "+5분",
        "+15m": "+15분",
        "+30m": "+30분",
        "+60m": "+60분",
        "EOD": "EOD",
        "T+1": "T+1",
        "T+2": "T+2",
    }
    return mapping.get(str(value or ""), str(value or ""))


def compact_post_exit_shadow(shadow: Dict[str, Any]) -> Dict[str, Any]:
    obj = as_dict(shadow)
    if not obj:
        return {}
    checkpoints: Dict[str, Any] = {}
    for key in ("+5m", "+15m", "+30m", "+60m", "EOD", "T+1", "T+2"):
        row = as_dict(as_dict(obj.get("checkpoints")).get(key))
        if not row:
            continue
        checkpoints[key] = {
            "status": row.get("status"),
            "price": row.get("price", row.get("observed_price")),
            "observed_price": row.get("observed_price", row.get("price")),
            "close": row.get("close"),
            "high_since_exit": row.get("high_since_exit"),
            "low_since_exit": row.get("low_since_exit"),
            "return_pct": row.get("return_pct"),
            "max_upside_pct": row.get("max_upside_pct"),
            "max_drawdown_pct": row.get("max_drawdown_pct"),
            "target_ts": row.get("target_ts"),
            "observed_ts": row.get("observed_ts"),
            "latest_observed_ts": row.get("latest_observed_ts"),
        }
    return {
        "observability_only": bool(obj.get("observability_only", True)),
        "status": obj.get("status"),
        "symbol": obj.get("symbol"),
        "exit_ts": obj.get("exit_ts"),
        "exit_price": obj.get("exit_price"),
        "horizon_owner": obj.get("horizon_owner"),
        "strategy_horizon": obj.get("strategy_horizon"),
        "price_observation_status": obj.get("price_observation_status"),
        "price_observation_reason": obj.get("price_observation_reason"),
        "latest_observed_ts": obj.get("latest_observed_ts"),
        "best_exit_offset": obj.get("best_exit_offset"),
        "best_exit_price": obj.get("best_exit_price"),
        "max_post_exit_upside_pct": obj.get("max_post_exit_upside_pct"),
        "max_post_exit_drawdown_pct": obj.get("max_post_exit_drawdown_pct"),
        "checkpoints": checkpoints,
    }


def build_post_exit_shadow_summary_lines(
    report: Dict[str, Any],
    *,
    summary_money: Callable[[Any], str],
    fmt_pct: Callable[[Any], str],
    metadata_value: Callable[[Any], str],
    num_opt: Callable[[Any], Optional[float]],
) -> List[str]:
    shadow = compact_post_exit_shadow(post_exit_shadow_surface(report))
    if not shadow:
        return []
    lines: List[str] = ["### 매도 후 가격 추적 (관측-only)", ""]
    exit_price = shadow.get("exit_price")
    exit_num = num_opt(exit_price)
    exit_price_missing = exit_num is None or exit_num <= 0
    status = str(shadow.get("price_observation_status") or "").strip().lower()
    reason = str(shadow.get("price_observation_reason") or "").strip()
    latest_observed_ts = str(shadow.get("latest_observed_ts") or "").strip()
    lines.append("* 기준: 실제 매도 후 같은 종목을 가상 보유했다고 가정한 가격 추적입니다. 실제 매매 판단에는 아직 반영하지 않습니다.")
    lines.append(f"* 매도 기준가: {'-' if exit_price_missing else summary_money(exit_price)}")

    observed_any = False
    checkpoints = as_dict(shadow.get("checkpoints"))
    for key in ("+5m", "+15m", "+30m", "+60m", "EOD"):
        row = as_dict(checkpoints.get(key))
        if not row:
            continue
        label = checkpoint_label(key)
        row_status = str(row.get("status") or "").strip().lower()
        price = row.get("price", row.get("observed_price", row.get("close")))
        if row_status == "observed" and price not in (None, ""):
            observed_any = True
            parts = [
                f"* {label}: {summary_money(price)} ({fmt_pct(row.get('return_pct'))})",
            ]
            if row.get("high_since_exit") not in (None, ""):
                parts.append(f"구간 고가 {summary_money(row.get('high_since_exit'))}")
            if row.get("low_since_exit") not in (None, ""):
                parts.append(f"구간 저가 {summary_money(row.get('low_since_exit'))}")
            lines.append(" / ".join(parts))
        elif key in {"+5m", "+15m", "+30m", "+60m"}:
            lines.append(f"* {label}: 아직 관측 대기")

    if not observed_any:
        lines.append(f"* 가격 관측 상태: {'대기' if status == 'pending' else metadata_value(status or '-')}")
        if reason:
            reason_label = {
                "no_minute_rows": "가격 추적용 minute 데이터가 아직 없습니다.",
                "no_rows_after_exit": "매도 시각 이후 minute 가격 데이터가 아직 없습니다.",
                "missing_exit_time_or_price": "매도 시각 또는 매도 기준가가 부족합니다.",
                "checkpoint_targets_not_reached": "아직 checkpoint 도달 전입니다.",
            }.get(reason, reason)
            lines.append(f"* 사유: {reason_label}")
        if latest_observed_ts:
            lines.append(f"* 마지막 보유 가격 데이터 시각: {latest_observed_ts}")
        lines.append("")
        if reason == "missing_exit_time_or_price" or exit_price_missing:
            lines.append("판단: 청산 체결 시각 또는 기준가가 확정되지 않아 매도 후 가격 경로를 평가하지 않습니다. 체결 기준점이 확정된 거래만 post-exit shadow 평가 대상으로 봅니다.")
        else:
            lines.append("판단: 아직 매도 후 가격 경로를 평가할 수 없습니다. 다음 리포트 재생성 또는 다음 runtime 가격 수집 후 +5분/+15분 checkpoint부터 채워야 합니다.")
        return lines

    best_offset = str(shadow.get("best_exit_offset") or "").strip()
    best_price = shadow.get("best_exit_price")
    if best_offset and best_price not in (None, ""):
        lines.append(f"* 현재까지 최선 가상 청산 지점: {checkpoint_label(best_offset)}, {summary_money(best_price)}")
    best_num = num_opt(best_price)
    lines.append("")
    if exit_num is not None and best_num is not None and best_num > exit_num:
        lines.append(
            f"판단: 이 거래는 매도 후 {checkpoint_label(best_offset)} 구간에서 더 좋은 청산 가격이 관측됐습니다. "
            "다만 표본이 부족하므로 보유 연장 규칙으로 바로 반영하지 않고, post-exit shadow 데이터로만 누적합니다."
        )
    else:
        lines.append(
            "판단: 현재까지는 매도 후 더 나은 가격 개선이 명확하지 않습니다. "
            "다만 표본이 부족하므로 청산 규칙 변경 없이 post-exit shadow 데이터로만 누적합니다."
        )
    return lines
