from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json
import time


@dataclass
class TokenRecord:
    access_token: str
    token_type: str = "Bearer"
    expires_at_epoch: int = 0  # unix epoch seconds
    raw: Dict[str, Any] = None

    def __post_init__(self):
        if self.raw is None:
            self.raw = {}

    @property
    def is_expired(self) -> bool:
        return int(time.time()) >= int(self.expires_at_epoch)

    def will_expire_within(self, margin_sec: int) -> bool:
        return int(time.time()) + int(margin_sec) >= int(self.expires_at_epoch)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_at_epoch": int(self.expires_at_epoch),
            "raw": self.raw or {},
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "TokenRecord":
        return TokenRecord(
            access_token=str(d.get("access_token", "")),
            token_type=str(d.get("token_type", "Bearer")),
            expires_at_epoch=int(d.get("expires_at_epoch", 0)),
            raw=dict(d.get("raw", {}) or {}),
        )


class TokenCache:
    """File-based token cache (JSON).
    Keeps last token record to avoid re-auth on every run.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> Optional[TokenRecord]:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            rec = TokenRecord.from_dict(data)
            if not rec.access_token:
                return None
            return rec
        except Exception:
            return None

    def save(self, rec: TokenRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
