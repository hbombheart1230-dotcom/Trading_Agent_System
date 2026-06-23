from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from libs.core.settings import Settings
from libs.kiwoom.token_cache import TokenCache


MARKET_STATUS_PATH = Path("data/state/kiwoom_market_status.json")
MARKET_STATUS_LISTENER_PATH = Path("data/state/kiwoom_market_status_listener.json")
_EVENT_LIMIT = 100

STATUS_LABELS = {
    "0": "preopen_notice",
    "3": "regular_session_open",
    "2": "closeout_notice",
    "4": "regular_session_close",
    "8": "regular_session_close_confirmed",
    "9": "all_markets_closed",
    "a": "after_hours_close_price_open",
    "b": "after_hours_close_price_closed",
    "c": "after_hours_single_price_open",
    "d": "after_hours_single_price_closed",
    "R": "regular_session_open",
}

CLOSEOUT_NOTICE_CODES = {"2"}
REGULAR_CLOSE_CODES = {"4", "8"}
FINAL_REFRESH_CODES = {"b", "9", "d"}
SESSION_OPEN_CODES = {"3", "R"}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{threading.get_ident()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _write_listener_status(*, status: str, detail: str = "") -> None:
    _write_json_atomic(
        MARKET_STATUS_LISTENER_PATH,
        {
            "schema_version": "kiwoom_market_status_listener.v1",
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": status,
            "detail": detail[:500],
        },
    )


def _return_code(payload: Dict[str, Any]) -> int:
    try:
        return int(payload.get("return_code"))
    except Exception:
        return -1


def parse_market_status_messages(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if str(payload.get("trnm") or "").upper() != "REAL":
        return []
    received_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: List[Dict[str, Any]] = []
    for row in list(payload.get("data") or []):
        if not isinstance(row, dict) or str(row.get("type") or "") != "0s":
            continue
        values = row.get("values") if isinstance(row.get("values"), dict) else {}
        code = str(values.get("215") or "").strip()
        if not code:
            continue
        exchange_time = str(values.get("20") or "").strip()
        out.append(
            {
                "event_id": f"{received_at}:{code}:{exchange_time}",
                "received_at": received_at,
                "code": code,
                "label": STATUS_LABELS.get(code, "unknown"),
                "exchange_time": exchange_time,
                "expected_remaining_time": str(values.get("214") or "").strip(),
                "source": "kiwoom.websocket.0s",
            }
        )
    return out


def record_market_status_events(events: List[Dict[str, Any]], *, path: Path = MARKET_STATUS_PATH) -> Dict[str, Any]:
    current = _read_json(path)
    history = [dict(row) for row in list(current.get("events") or []) if isinstance(row, dict)]
    known = {str(row.get("event_id") or "") for row in history}
    for event in events:
        event_id = str(event.get("event_id") or "")
        if event_id and event_id not in known:
            history.append(dict(event))
            known.add(event_id)
    history = history[-_EVENT_LIMIT:]
    payload = {
        "schema_version": "kiwoom_market_status.v1",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "current": dict(history[-1]) if history else {},
        "events": history,
    }
    _write_json_atomic(path, payload)
    return payload


def load_market_status(*, path: Path = MARKET_STATUS_PATH) -> Dict[str, Any]:
    return _read_json(path)


class KiwoomMarketStatusListener:
    def __init__(self, *, path: Path = MARKET_STATUS_PATH, settings: Settings | None = None) -> None:
        self.path = path
        self.settings = settings or Settings.from_env()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="kiwoom-market-status", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _run(self) -> None:
        from websockets.sync.client import connect

        url = (
            "wss://mockapi.kiwoom.com:10000/api/dostk/websocket"
            if str(self.settings.kiwoom_mode or "").lower() == "mock"
            else "wss://api.kiwoom.com:10000/api/dostk/websocket"
        )
        while not self._stop.is_set():
            token = TokenCache(self.settings.kiwoom_token_cache_path).load()
            if not token or token.is_expired:
                _write_listener_status(status="waiting_for_valid_token")
                self._stop.wait(5)
                continue
            try:
                with connect(
                    url,
                    open_timeout=10,
                    close_timeout=3,
                ) as ws:
                    ws.send(json.dumps({"trnm": "LOGIN", "token": token.access_token}))
                    login_response = json.loads(ws.recv(timeout=10))
                    if _return_code(login_response) != 0:
                        raise RuntimeError(f"kiwoom_websocket_login_failed:{login_response}")
                    ws.send(
                        json.dumps(
                            {
                                "trnm": "REG",
                                "grp_no": "9001",
                                "refresh": "1",
                                "data": [{"item": [""], "type": ["0s"]}],
                            }
                        )
                    )
                    register_response = json.loads(ws.recv(timeout=10))
                    if _return_code(register_response) != 0:
                        raise RuntimeError(f"kiwoom_market_status_register_failed:{register_response}")
                    _write_listener_status(status="registered", detail=url)
                    while not self._stop.is_set():
                        try:
                            raw = ws.recv(timeout=5)
                        except TimeoutError:
                            continue
                        payload = json.loads(raw)
                        events = parse_market_status_messages(payload if isinstance(payload, dict) else {})
                        if events:
                            record_market_status_events(events, path=self.path)
            except Exception as exc:
                _write_listener_status(status="reconnecting", detail=f"{type(exc).__name__}: {exc}")
                self._stop.wait(5)


__all__ = [
    "CLOSEOUT_NOTICE_CODES",
    "FINAL_REFRESH_CODES",
    "KiwoomMarketStatusListener",
    "MARKET_STATUS_PATH",
    "MARKET_STATUS_LISTENER_PATH",
    "REGULAR_CLOSE_CODES",
    "SESSION_OPEN_CODES",
    "load_market_status",
    "parse_market_status_messages",
    "record_market_status_events",
]
