from __future__ import annotations

from libs.core.http_client import HttpClient
from libs.kiwoom.kiwoom_account_client import KiwoomAccountClient
from libs.kiwoom.kiwoom_token_client import KiwoomTokenClient
from libs.core.settings import Settings
from libs.core.event_logger import EventLogger

def read_account_balance(state: dict) -> dict:
    s: Settings = state.get("settings") or Settings.from_env()
    logger = EventLogger(node="read_account_balance")
    logger.start({"dry_run": bool(state.get("dry_run", False))})

    http = HttpClient(
        s.base_url,
        timeout_sec=s.kiwoom_http_timeout_sec,
        retry_max=s.kiwoom_retry_max,
    )
    token_cli = KiwoomTokenClient(s, http)
    acct = KiwoomAccountClient(s, http, token_cli)

    res = acct.get_account_balance(dry_run=bool(state.get("dry_run", False)))

    state["account_balance"] = {
        "status_code": res.status_code,
        "ok": res.ok,
        "error_code": res.error_code,
    }
    logger.end(state["account_balance"])
    return state
