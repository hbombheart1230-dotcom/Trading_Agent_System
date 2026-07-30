from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from libs.core.http_client import HttpClient
from libs.core.settings import Settings
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.skills.dto_extractors import extract_minute_ohlcv


def _read_cache(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("rows") if isinstance(payload, Mapping) else []
    return [dict(row) for row in rows or [] if isinstance(row, Mapping)]


def _write_cache(path: Path, *, symbol: str, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "kiwoom_historical_minute_cache.v1",
        "symbol": symbol,
        "row_count": len(rows),
        "rows": [dict(row) for row in rows],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _header(headers: Mapping[str, Any], name: str) -> str:
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value or "").strip()
    return ""


class KiwoomHistoricalMinuteReader:
    API_ID = "ka10080"
    ENDPOINT = "/api/dostk/chart"

    def __init__(
        self,
        *,
        settings: Settings,
        http: HttpClient,
        token: KiwoomTokenClient,
        request_interval_sec: float = 1.15,
    ):
        self.settings = settings
        self.http = http
        self.token = token
        self.request_interval_sec = max(1.05, float(request_interval_sec))
        self._last_request_monotonic = 0.0

    @classmethod
    def from_env(cls) -> "KiwoomHistoricalMinuteReader":
        settings = Settings.from_env()
        http = HttpClient(
            settings.base_url,
            timeout_sec=settings.kiwoom_http_timeout_sec,
            retry_max=settings.kiwoom_retry_max,
        )
        return cls(
            settings=settings,
            http=http,
            token=KiwoomTokenClient(settings, http),
        )

    def _base_headers(self) -> dict[str, Any]:
        token_result = self.token.ensure_token(dry_run=False)
        if not token_result.token:
            raise RuntimeError(
                f"kiwoom_token_unavailable:{token_result.action}:{token_result.reason}"
            )
        headers = {
            **self.token.auth_headers(token_result.token),
            "Content-Type": "application/json;charset=UTF-8",
            "api-id": self.API_ID,
        }
        if self.settings.kiwoom_app_key:
            headers["appkey"] = self.settings.kiwoom_app_key
        if self.settings.kiwoom_app_secret:
            headers["appsecret"] = self.settings.kiwoom_app_secret
        return headers

    def _wait_for_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_monotonic
        remaining = self.request_interval_sec - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def fetch_until(
        self,
        *,
        symbol: str,
        minimum_epoch: int,
        max_pages: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        headers = self._base_headers()
        rows_by_epoch: dict[int, dict[str, Any]] = {}
        page_count = 0
        complete = False
        error = ""
        for page in range(1, max(1, int(max_pages)) + 1):
            response = None
            payload: dict[str, Any] = {}
            for attempt in range(3):
                self._wait_for_rate_limit()
                _url, response = self.http.request(
                    "POST",
                    self.ENDPOINT,
                    headers=headers,
                    json_body={
                        "stk_cd": str(symbol),
                        "tic_scope": "1",
                        "upd_stkpc_tp": "1",
                    },
                    dry_run=False,
                )
                self._last_request_monotonic = time.monotonic()
                if response is None:
                    break
                try:
                    payload = json.loads(response.text or "{}")
                except Exception:
                    payload = {}
                return_code = int(payload.get("return_code") or 0)
                return_message = str(payload.get("return_msg") or "")
                if return_code == 5 and "1700" in return_message and attempt < 2:
                    continue
                break
            if response is None:
                error = "response_missing"
                break
            if int(payload.get("return_code") or 0) != 0:
                error = (
                    f"kiwoom_error:{payload.get('return_code')}:"
                    f"{payload.get('return_msg')}"
                )
                break
            normalized = extract_minute_ohlcv(symbol, 1, payload).rows
            page_count += 1
            for row in normalized:
                epoch = int(row.get("ts") or 0)
                if epoch > 0:
                    rows_by_epoch[epoch] = dict(row)
            if rows_by_epoch and min(rows_by_epoch) <= int(minimum_epoch):
                complete = True
                break
            continuation = _header(response.headers, "cont-yn")
            next_key = _header(response.headers, "next-key")
            if continuation.upper() != "Y" or not next_key:
                break
            headers = {
                **self._base_headers(),
                "cont-yn": continuation,
                "next-key": next_key,
            }
        rows = [rows_by_epoch[key] for key in sorted(rows_by_epoch)]
        return rows, {
            "symbol": symbol,
            "page_count": page_count,
            "row_count": len(rows),
            "minimum_epoch_requested": int(minimum_epoch),
            "minimum_epoch_observed": min(rows_by_epoch) if rows_by_epoch else None,
            "maximum_epoch_observed": max(rows_by_epoch) if rows_by_epoch else None,
            "coverage_complete": complete,
            "error": error,
        }


def load_or_fetch_symbol_history(
    *,
    reader: KiwoomHistoricalMinuteReader | None,
    symbol: str,
    minimum_epoch: int,
    cache_root: Path,
    max_pages: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cache_path = cache_root / f"{symbol}.json"
    cached = _read_cache(cache_path)
    cached_epochs = [int(row.get("ts") or 0) for row in cached if int(row.get("ts") or 0) > 0]
    if cached_epochs and min(cached_epochs) <= int(minimum_epoch):
        return cached, {
            "symbol": symbol,
            "source": "cache",
            "cache_path": str(cache_path),
            "row_count": len(cached),
            "coverage_complete": True,
            "minimum_epoch_observed": min(cached_epochs),
            "maximum_epoch_observed": max(cached_epochs),
        }
    if reader is None:
        return cached, {
            "symbol": symbol,
            "source": "cache_only",
            "cache_path": str(cache_path),
            "row_count": len(cached),
            "coverage_complete": False,
            "error": "cache_incomplete_and_fetch_disabled",
        }

    fetched, meta = reader.fetch_until(
        symbol=symbol,
        minimum_epoch=minimum_epoch,
        max_pages=max_pages,
    )
    merged = {
        int(row.get("ts") or 0): dict(row)
        for row in [*cached, *fetched]
        if int(row.get("ts") or 0) > 0
    }
    rows = [merged[key] for key in sorted(merged)]
    if rows:
        _write_cache(cache_path, symbol=symbol, rows=rows)
    return rows, {
        **meta,
        "source": "kiwoom_paginated",
        "cache_path": str(cache_path),
        "cached_row_count": len(cached),
        "row_count": len(rows),
    }
