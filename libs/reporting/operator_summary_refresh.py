from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict

from libs.reporting.operator_period_summary import (
    default_month_key,
    default_week_key,
    generate_operator_daily_summary_artifact,
    generate_operator_period_summary,
)
from libs.reporting.symbol_trade_report import generate_symbol_trade_report


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_day(value: Any) -> date | None:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except Exception:
        return None


def _summary_ref(md_path: Path, json_path: Path, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    metrics = {}
    if isinstance(payload, dict) and isinstance(payload.get("metrics"), dict):
        metrics = dict(payload.get("metrics") or {})
    return {
        "status": "ok",
        "md_path": str(md_path),
        "json_path": str(json_path),
        "metrics": metrics,
    }


def refresh_operator_summaries_after_trade(
    *,
    reports_root: Path,
    event_log_path: Path,
    day: str,
    symbol: str = "",
) -> Dict[str, Any]:
    """Refresh bounded operator summary surfaces after a trade artifact update.

    This is intentionally deterministic and best-effort. The caller can record
    failures for observability, but summary refresh must not block trading or
    the trade report persistence path.
    """
    reports_root = Path(reports_root)
    event_log_path = Path(event_log_path)
    normalized_day = str(day or "").strip()[:10]
    normalized_symbol = str(symbol or "").strip().upper()
    day_obj = _parse_day(normalized_day)

    result: Dict[str, Any] = {
        "schema_version": "operator_summary_refresh.v1",
        "generated_at": _utc_now_iso(),
        "day": normalized_day,
        "symbol": normalized_symbol,
        "status": "skipped",
        "artifacts": {},
        "errors": [],
    }
    artifacts: Dict[str, Any] = result["artifacts"]
    errors: list[Dict[str, str]] = result["errors"]

    if not normalized_day or day_obj is None:
        errors.append({"layer": "period", "error": "invalid_day"})
        result["status"] = "error"
        return result

    if normalized_symbol:
        try:
            symbol_out = generate_symbol_trade_report(
                events_path=event_log_path,
                reports_root=reports_root,
                symbol=normalized_symbol,
            )
            artifacts["symbol"] = {
                "status": "ok",
                "symbol": normalized_symbol,
                "md_path": str(symbol_out.get("symbol_summary_md_path") or ""),
                "json_path": str(symbol_out.get("symbol_summary_json_path") or ""),
                "trade_history_path": str(symbol_out.get("trade_history_path") or ""),
            }
        except Exception as exc:
            errors.append({"layer": "symbol", "error": f"{type(exc).__name__}: {exc}"[:500]})

    try:
        daily_md, daily_json, daily_payload = generate_operator_daily_summary_artifact(
            reports_root=reports_root,
            day=normalized_day,
        )
        artifacts["daily"] = _summary_ref(daily_md, daily_json, daily_payload)
    except Exception as exc:
        errors.append({"layer": "daily", "error": f"{type(exc).__name__}: {exc}"[:500]})

    week_key = default_week_key(day_obj)
    try:
        weekly_md, weekly_json, weekly_payload = generate_operator_period_summary(
            reports_root=reports_root,
            period_type="weekly",
            period_key=week_key,
        )
        artifacts["weekly"] = _summary_ref(weekly_md, weekly_json, weekly_payload)
        artifacts["weekly"]["period_key"] = week_key
    except Exception as exc:
        errors.append({"layer": "weekly", "error": f"{type(exc).__name__}: {exc}"[:500]})

    month_key = default_month_key(day_obj)
    try:
        monthly_md, monthly_json, monthly_payload = generate_operator_period_summary(
            reports_root=reports_root,
            period_type="monthly",
            period_key=month_key,
        )
        artifacts["monthly"] = _summary_ref(monthly_md, monthly_json, monthly_payload)
        artifacts["monthly"]["period_key"] = month_key
    except Exception as exc:
        errors.append({"layer": "monthly", "error": f"{type(exc).__name__}: {exc}"[:500]})

    if errors and artifacts:
        result["status"] = "partial"
    elif errors:
        result["status"] = "error"
    elif artifacts:
        result["status"] = "ok"
    return result

