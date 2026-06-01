from __future__ import annotations

import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Tuple


KOFIA_ENDPOINT = "https://www.kofiabond.or.kr/proframeWeb/XMLSERVICES/"
KOFIA_BOND_CODES = {
    "kr_3y_yield": "3000",
    "kr_10y_yield": "3013",
}


def _to_float(value: Any) -> float | None:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _date_range(days: int = 14) -> Tuple[str, str]:
    end = datetime.now(timezone.utc).astimezone()
    start = end - timedelta(days=max(3, int(days)))
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _request_body(start_date: str, end_date: str, codes: Iterable[str]) -> bytes:
    values = [
        '<?xml version="1.0" encoding="utf-8"?><message>',
        "<proframeHeader>",
        "<pfmAppName>BIS-KOFIABOND</pfmAppName>",
        "<pfmSvcName>BISLastAskPrcROPSrchSO</pfmSvcName>",
        "<pfmFnName>listTrm</pfmFnName>",
        "</proframeHeader><systemHeader></systemHeader><BISComDspDatDTO>",
        "<val1>DD</val1>",
        f"<val2>{start_date}</val2>",
        f"<val3>{end_date}</val3>",
        "<val4>1530</val4>",
    ]
    for index, code in enumerate(codes, start=5):
        values.append(f"<val{index}>{str(code)}</val{index}>")
    values.append("</BISComDspDatDTO></message>")
    return "".join(values).encode("utf-8")


def _fetch_kofia_xml(*, start_date: str, end_date: str, codes: Iterable[str], timeout_sec: float) -> str:
    req = urllib.request.Request(
        KOFIA_ENDPOINT,
        data=_request_body(start_date, end_date, codes),
        headers={
            "Content-Type": "application/xml; charset=utf-8",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(req, timeout=max(3.0, float(timeout_sec))) as response:
        return response.read().decode("utf-8", "replace")


def _rows_from_xml(text: str) -> list[dict[str, str]]:
    root = ET.fromstring(text)
    rows: list[dict[str, str]] = []
    for node in root.findall(".//BISComDspDatDTO"):
        row = {child.tag: str(child.text or "").strip() for child in list(node)}
        label = str(row.get("val1") or "").strip()
        if not label or not label[:4].isdigit():
            continue
        rows.append(row)
    rows.sort(key=lambda item: str(item.get("val1") or ""), reverse=True)
    return rows


def _indicator_from_rows(*, key: str, code_index: int, rows: list[dict[str, str]]) -> dict[str, Any]:
    current_row = rows[0] if rows else {}
    previous_row = rows[1] if len(rows) > 1 else {}
    current = _to_float(current_row.get(f"val{code_index}"))
    previous = _to_float(previous_row.get(f"val{code_index}"))
    if current is None:
        return {
            "status": "unavailable",
            "source": "kofia",
            "ticker": KOFIA_BOND_CODES.get(key, ""),
            "reason": "kofia_value_missing",
        }
    out: dict[str, Any] = {
        "status": "ok",
        "source": "kofia",
        "reason": "kofia_latest_available",
        "ticker": KOFIA_BOND_CODES.get(key, ""),
        "current": current,
        "current_yield_pct": current,
        "asof": str(current_row.get("val1") or ""),
        "unit": "yield_pct",
    }
    if previous is not None:
        out["previous"] = previous
        out["previous_yield_pct"] = previous
        out["delta"] = float(current - previous)
        out["previous_asof"] = str(previous_row.get("val1") or "")
    return out


def fetch_korea_bond_yield_overrides(policy: Dict[str, Any] | None = None) -> Dict[str, Dict[str, Any]]:
    policy = dict(policy or {})
    enabled = policy.get("korea_bond_yield_provider_enabled")
    if enabled is None:
        enabled = os.getenv("KOREA_BOND_YIELD_PROVIDER_ENABLED", "true")
    if str(enabled).strip().lower() in {"0", "false", "no", "n", "off"}:
        return {}
    timeout_sec = float(policy.get("korea_bond_yield_timeout_sec") or os.getenv("KOREA_BOND_YIELD_TIMEOUT_SEC") or 8.0)
    days = int(float(policy.get("korea_bond_yield_lookback_days") or os.getenv("KOREA_BOND_YIELD_LOOKBACK_DAYS") or 14))
    start_date, end_date = _date_range(days)
    try:
        text = _fetch_kofia_xml(
            start_date=start_date,
            end_date=end_date,
            codes=[KOFIA_BOND_CODES["kr_3y_yield"], KOFIA_BOND_CODES["kr_10y_yield"]],
            timeout_sec=timeout_sec,
        )
        rows = _rows_from_xml(text)
        return {
            "kr_3y_yield": _indicator_from_rows(key="kr_3y_yield", code_index=2, rows=rows),
            "kr_10y_yield": _indicator_from_rows(key="kr_10y_yield", code_index=3, rows=rows),
        }
    except Exception as exc:
        reason = f"kofia_fetch_error:{type(exc).__name__}"
        return {
            "kr_3y_yield": {"status": "unavailable", "source": "kofia", "ticker": KOFIA_BOND_CODES["kr_3y_yield"], "reason": reason},
            "kr_10y_yield": {"status": "unavailable", "source": "kofia", "ticker": KOFIA_BOND_CODES["kr_10y_yield"], "reason": reason},
        }
