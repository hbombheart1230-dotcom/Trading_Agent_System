from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Mapping

from libs.core.http_client import HttpClient
from libs.core.settings import Settings
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.market_data import receipts as mdr
from libs.skills.dto_extractors import extract_minute_ohlcv

_NORMALIZER_PATH = Path(__file__).resolve().parents[2] / "skills" / "dto_extractors.py"
_LOGGER = logging.getLogger(__name__)


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
        raw_pages: list[str] = []  # verbatim provider response bytes, one entry per successfully parsed page
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
            raw_pages.append(response.text or "")  # retained verbatim, in fetch order -- never re-serialized
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
            "raw_pages": raw_pages,
        }


def _attested_normalized_bytes(symbol: str, rows: list[Mapping[str, Any]]) -> bytes:
    """The exact bytes an attested normalized artifact persists -- ONLY the rows passed in (never merged
    with the legacy convenience cache). Same on-disk shape as `_write_cache`'s legacy artifact, so
    `candle_authority.verify_structure` validates it unchanged."""
    payload = {
        "schema_version": "kiwoom_historical_minute_cache.v1",
        "symbol": symbol,
        "row_count": len(rows),
        "rows": [dict(row) for row in rows],
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _issue_market_data_receipt(
    *, symbol: str, raw_pages: list[str], fetched_rows: list[dict[str, Any]],
    archive_root: Path, receipt_root: Path, normalized_root: Path, meta: Mapping[str, Any],
) -> bool:
    """Architecture-approved provenance lifecycle (docs/decisions/ADR-0003_*), steps 1-7, additive only --
    never changes what `load_or_fetch_symbol_history` returns or how candles are served.

    CORE AUTHORITY INVARIANT: the receipt attests ONLY `fetched_rows` -- the rows THIS acquisition's own
    raw page bundle actually produced -- persisted as an INDEPENDENT, content-addressed attested artifact
    under `normalized_root`. It never hashes or otherwise references the legacy convenience merged cache
    (`_write_cache`'s own file), which may still hold older, unattested rows; merging the two into one
    file for legacy consumers must never let a fresh receipt retroactively attest those older rows.

    Exact order: (1) raw page bundle assembled deterministically, (2) atomically persisted, (3) re-read +
    re-hashed; (4) normalization already happened, during `fetch_until`'s own loop, from these EXACT
    pages -- `fetched_rows` corresponds 1:1 to `raw_pages`; (5) the attested-normalized-only artifact is
    atomically persisted, (6) re-read + re-hashed; (7) the receipt is written atomically LAST. Any
    failure at any stage is reported via a structured warning log (symbol / stage / exception class --
    never raw payload contents or secrets) and this function returns False; the caller proceeds without a
    receipt, which is safe by construction: no receipt visible means UEF-5.2 correctly finds NOT_PROVEN.
    """
    scope = f"symbol={symbol} page_count={len(raw_pages)} fetched_row_count={len(fetched_rows)}"

    try:  # 1-3: complete raw page bundle -> atomic publication -> re-read + re-hash
        raw_bytes = mdr.raw_page_bundle_bytes(raw_pages)
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        raw_ref = mdr.content_addressed_ref(
            provider=mdr.PROVIDER_KIWOOM, producer_id=mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1, symbol=symbol, raw_sha256=raw_sha256)
        mdr.persist_raw_artifact(archive_root, raw_ref, raw_bytes)
        if not mdr.verify_raw_archive(archive_root, raw_ref, raw_sha256):
            _LOGGER.warning("market_data_receipt_issuance_failed %s stage=raw_verify reason=hash_mismatch_after_publish", scope)
            return False
    except Exception as exc:  # noqa: BLE001 -- provenance issuance must never break candle acquisition/serving
        _LOGGER.warning("market_data_receipt_issuance_failed %s stage=raw_publish exception=%s", scope, type(exc).__name__)
        return False

    try:  # 4-6: normalize FROM that same raw page set (already done above) -> atomic attested-normalized
          # publication -> re-read + re-hash
        attested_bytes = _attested_normalized_bytes(symbol, fetched_rows)
        normalized_sha256 = hashlib.sha256(attested_bytes).hexdigest()
        normalized_ref = mdr.normalized_content_ref(
            provider=mdr.PROVIDER_KIWOOM, producer_id=mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1,
            symbol=symbol, normalized_sha256=normalized_sha256)
        mdr.persist_raw_artifact(normalized_root, normalized_ref, attested_bytes)
        if not mdr.verify_raw_archive(normalized_root, normalized_ref, normalized_sha256):
            _LOGGER.warning("market_data_receipt_issuance_failed %s stage=normalized_verify reason=hash_mismatch_after_publish", scope)
            return False
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("market_data_receipt_issuance_failed %s stage=normalized_publish exception=%s", scope, type(exc).__name__)
        return False

    try:  # 7: receipt written atomically LAST
        epochs = [int(r.get("ts") or 0) for r in fetched_rows if int(r.get("ts") or 0) > 0]
        receipt = mdr.MarketDataReceipt(
            receipt_schema=mdr.RECEIPT_SCHEMA, provider=mdr.PROVIDER_KIWOOM, producer_id=mdr.PRODUCER_KIWOOM_HISTORICAL_MINUTE_V1,
            producer_version="1", symbol=symbol,
            trading_date=None,  # one receipt spans the whole multi-day acquisition window this reader actually
                                 # fetches; source_window_start/end are the authoritative acquisition scope,
                                 # checked ROW-BY-ROW by UEF (never a day-level overlap)
            interval="1m", source_window_start=min(epochs) if epochs else 0, source_window_end=max(epochs) if epochs else 0,
            raw_payload_sha256=raw_sha256, raw_archive_ref=raw_ref, normalized_candle_sha256=normalized_sha256,
            normalizer_id="libs.skills.dto_extractors.extract_minute_ohlcv", normalizer_version="1",
            normalizer_implementation_digest=mdr.file_content_sha256(_NORMALIZER_PATH),
            row_count=len(fetched_rows),
            diagnostic={"page_count": meta.get("page_count"), "coverage_complete": meta.get("coverage_complete")},
        )
        mdr.write_receipt(receipt_root, receipt)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("market_data_receipt_issuance_failed %s stage=receipt_write exception=%s", scope, type(exc).__name__)
        return False
    return True


def load_or_fetch_symbol_history(
    *,
    reader: KiwoomHistoricalMinuteReader | None,
    symbol: str,
    minimum_epoch: int,
    cache_root: Path,
    max_pages: int,
    raw_archive_root: Path | None = None,
    receipt_root: Path | None = None,
    normalized_root: Path | None = None,
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
        _write_cache(cache_path, symbol=symbol, rows=rows)  # legacy convenience artifact -- NEVER receipt-authoritative
    if fetched:
        raw_pages = meta.get("raw_pages") or []
        if raw_pages:
            archive_root = raw_archive_root if raw_archive_root is not None else cache_root.parent.parent / "market_data" / "raw_archive"
            rcpt_root = receipt_root if receipt_root is not None else cache_root.parent.parent / "market_data" / "receipts"
            norm_root = normalized_root if normalized_root is not None else cache_root.parent.parent / "market_data" / "normalized"
            _issue_market_data_receipt(
                symbol=symbol, raw_pages=raw_pages, fetched_rows=fetched,
                archive_root=archive_root, receipt_root=rcpt_root, normalized_root=norm_root, meta=meta)
    return rows, {
        **meta,
        "source": "kiwoom_paginated",
        "cache_path": str(cache_path),
        "cached_row_count": len(cached),
        "row_count": len(rows),
    }
