from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.core.http_client import HttpClient
from libs.core.settings import Settings
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient


KST = timezone(timedelta(hours=9))
API_ID = "ka10081"
ENDPOINT = "/api/dostk/chart"


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return abs(float(str(value).replace(",", "").replace("+", "")))
    except (TypeError, ValueError):
        return None


def _normalized_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for raw in payload.get("stk_dt_pole_chart_qry") or []:
        if not isinstance(raw, Mapping):
            continue
        compact = str(raw.get("dt") or "")
        close = _number(raw.get("cur_prc"))
        if len(compact) != 8 or not compact.isdigit() or close is None:
            continue
        day = f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
        ts = int(
            datetime.fromisoformat(day)
            .replace(hour=15, minute=20, tzinfo=KST)
            .timestamp()
        )
        rows.append(
            {
                "ts": ts,
                "raw_ts": compact + "152000",
                "day": day,
                "open": _number(raw.get("open_pric")) or close,
                "high": _number(raw.get("high_pric")) or close,
                "low": _number(raw.get("low_pric")) or close,
                "close": close,
                "volume": _number(raw.get("trde_qty")) or 0.0,
                "trading_value": _number(raw.get("trde_prica")),
                "source": "kiwoom.ka10081",
                "daily_bar": True,
            }
        )
    rows.sort(key=lambda row: int(row["ts"]))
    return rows


class KiwoomDailyResearchProvider:
    def __init__(
        self,
        settings: Settings,
        http: HttpClient,
        token: KiwoomTokenClient,
    ) -> None:
        self.settings = settings
        self.http = http
        self.token = token

    @classmethod
    def from_env(cls) -> "KiwoomDailyResearchProvider":
        settings = Settings.from_env()
        base = (
            settings.kiwoom_base_url_mock
            if settings.kiwoom_mode == "mock"
            else settings.kiwoom_base_url_real
        )
        http = HttpClient(
            base_url=base,
            timeout_sec=int(settings.kiwoom_http_timeout_sec),
            retry_max=int(settings.kiwoom_retry_max),
        )
        token = KiwoomTokenClient(settings, http)
        return cls(settings, http, token)

    def fetch(self, symbol: str, *, base_day: str) -> list[dict[str, Any]]:
        token = self.token.ensure_token(dry_run=False)
        if not token.token:
            raise RuntimeError(
                f"Token not available: {token.action} {token.reason}"
            )
        headers = self.token.auth_headers(token.token)
        headers["Content-Type"] = "application/json;charset=UTF-8"
        headers["api-id"] = API_ID
        headers["appkey"] = self.settings.kiwoom_app_key or ""
        headers["appsecret"] = self.settings.kiwoom_app_secret or ""
        _url, response = self.http.request(
            "POST",
            ENDPOINT,
            headers=headers,
            json_body={
                "stk_cd": str(symbol),
                "base_dt": str(base_day).replace("-", ""),
                "upd_stkpc_tp": "1",
            },
            dry_run=False,
        )
        if response is None:
            raise RuntimeError("kiwoom_daily_response_missing")
        try:
            payload = json.loads(response.text) if response.text else {}
        except ValueError as exc:
            raise RuntimeError("kiwoom_daily_invalid_json") from exc
        code = str(payload.get("return_code") or "0")
        if code != "0":
            raise RuntimeError(
                f"kiwoom_daily_error:{code}:{payload.get('return_msg') or ''}"
            )
        return _normalized_rows(payload)


def load_daily_cache(
    cache_root: Path,
    symbols: set[str],
) -> dict[str, list[dict[str, Any]]]:
    result = {}
    for symbol in sorted(symbols):
        path = cache_root / f"{symbol}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        result[symbol] = [
            dict(row)
            for row in payload.get("rows") or []
            if isinstance(row, Mapping)
        ]
    return result


def refresh_daily_cache(
    *,
    cache_root: Path,
    symbols: set[str],
    base_day: str,
    request_interval_sec: float = 1.05,
) -> dict[str, Any]:
    provider = KiwoomDailyResearchProvider.from_env()
    cache_root.mkdir(parents=True, exist_ok=True)
    errors: dict[str, str] = {}
    counts: dict[str, int] = {}
    for symbol in sorted(symbols):
        try:
            rows = provider.fetch(symbol, base_day=base_day)
            payload = {
                "schema_version": "opening_rank1_daily_cache.v1",
                "symbol": symbol,
                "base_day": base_day,
                "source": "kiwoom.ka10081",
                "rows": rows,
            }
            (cache_root / f"{symbol}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            counts[symbol] = len(rows)
        except Exception as exc:
            errors[symbol] = f"{type(exc).__name__}:{exc}"
        time.sleep(max(0.0, request_interval_sec))
    return {
        "symbol_count": len(symbols),
        "success_count": len(counts),
        "errors": errors,
        "row_counts": counts,
    }


def merge_minute_and_daily(
    minute_rows: list[Mapping[str, Any]],
    daily_rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    minute_days = {
        str(row.get("raw_ts") or "")[:8]
        for row in minute_rows
        if len(str(row.get("raw_ts") or "")) >= 8
    }
    merged = [
        dict(row)
        for row in minute_rows
        if isinstance(row, Mapping)
    ]
    merged.extend(
        dict(row)
        for row in daily_rows
        if str(row.get("raw_ts") or "")[:8] not in minute_days
    )
    merged.sort(key=lambda row: int(row.get("ts") or 0))
    return merged
