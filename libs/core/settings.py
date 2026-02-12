from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict
import os


def load_env_file(path: str | Path = ".env") -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}

    loaded: Dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if (len(v) >= 2) and ((v[0] == v[-1]) and v[0] in ("'", '"')):
            v = v[1:-1]
        if k and (k not in os.environ):
            os.environ[k] = v
            loaded[k] = v
    return loaded


@dataclass(frozen=True)
class Settings:
    kiwoom_mode: str
    kiwoom_base_url_mock: str
    kiwoom_base_url_real: str
    kiwoom_app_key: str
    kiwoom_app_secret: str
    kiwoom_account_no: str
    kiwoom_token_cache_path: str
    kiwoom_token_refresh_margin_sec: int
    kiwoom_api_catalog_path: str
    state_store_path: str
    event_log_path: str
    report_dir: str
    kiwoom_http_timeout_sec: int
    kiwoom_retry_max: int
    kiwoom_pagination_max_calls: int

    # Risk guardrails
    risk_daily_loss_limit: float
    risk_per_trade_loss_limit: float
    risk_max_positions: int
    risk_order_cooldown_sec: int

    @property
    def base_url(self) -> str:
        mode = (self.kiwoom_mode or "mock").lower()
        return self.kiwoom_base_url_mock if mode == "mock" else self.kiwoom_base_url_real

    @staticmethod
    def from_env(env_path: str | Path = ".env") -> "Settings":
        load_env_file(env_path)

        def g(key: str, default: Optional[str] = None) -> str:
            v = os.getenv(key, default)
            return "" if v is None else str(v)

        def gi(key: str, default: int) -> int:
            v = os.getenv(key)
            if v is None or v == "":
                return int(default)
            try:
                return int(v)
            except ValueError:
                raise ValueError(f"Invalid int for {key}: {v}")

        def gf(key: str, default: float) -> float:
            v = os.getenv(key)
            if v is None or v == "":
                return float(default)
            try:
                return float(v)
            except ValueError:
                raise ValueError(f"Invalid float for {key}: {v}")

        catalog_path = g("KIWOOM_API_CATALOG_PATH", "").strip() or "./data/specs/api_catalog.jsonl"
        event_log_path = g("EVENT_LOG_PATH", "").strip() or "./data/logs/events.jsonl"

        return Settings(
            kiwoom_mode=g("KIWOOM_MODE", "mock").strip() or "mock",
            kiwoom_base_url_mock=g("KIWOOM_BASE_URL_MOCK", "https://mockapi.kiwoom.com").strip(),
            kiwoom_base_url_real=g("KIWOOM_BASE_URL_REAL", "https://api.kiwoom.com").strip(),
            kiwoom_app_key=g("KIWOOM_APP_KEY", "").strip(),
            kiwoom_app_secret=g("KIWOOM_APP_SECRET", "").strip(),
            kiwoom_account_no=g("KIWOOM_ACCOUNT_NO", "").strip(),
            kiwoom_token_cache_path=g("KIWOOM_TOKEN_CACHE_PATH", "./data/token_cache.json").strip(),
            kiwoom_token_refresh_margin_sec=gi("KIWOOM_TOKEN_REFRESH_MARGIN_SEC", 300),
            kiwoom_api_catalog_path=catalog_path,
            state_store_path=g("STATE_STORE_PATH", "./data/state.json").strip(),
            event_log_path=event_log_path,
            report_dir=g("REPORT_DIR", "./reports").strip(),
            kiwoom_http_timeout_sec=gi("KIWOOM_HTTP_TIMEOUT_SEC", 10),
            kiwoom_retry_max=gi("KIWOOM_RETRY_MAX", 2),
            kiwoom_pagination_max_calls=gi("KIWOOM_PAGINATION_MAX_CALLS", 10),
            risk_daily_loss_limit=gf("RISK_DAILY_LOSS_LIMIT", 0.0),
            risk_per_trade_loss_limit=gf("RISK_PER_TRADE_LOSS_LIMIT", 0.0),
            risk_max_positions=gi("RISK_MAX_POSITIONS", 1),
            risk_order_cooldown_sec=gi("RISK_ORDER_COOLDOWN_SEC", 0),
        )
