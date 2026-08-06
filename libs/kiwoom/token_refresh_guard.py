from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class TokenRefreshGuard:
    """Small cross-process guard for the shared Kiwoom token cache."""

    def __init__(
        self,
        cache_path: str | Path,
        *,
        wait_sec: float = 20.0,
        stale_sec: float = 60.0,
        cooldown_sec: float = 60.0,
    ) -> None:
        cache = Path(cache_path)
        self.lock_path = cache.with_suffix(cache.suffix + ".refresh.lock")
        self.failure_path = cache.with_suffix(cache.suffix + ".refresh_failure.json")
        self.wait_sec = float(wait_sec)
        self.stale_sec = float(stale_sec)
        self.cooldown_sec = float(cooldown_sec)
        self._acquired = False

    def __enter__(self) -> "TokenRefreshGuard":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.wait_sec
        while True:
            try:
                fd = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                with os.fdopen(fd, "w", encoding="ascii") as handle:
                    handle.write(f"{os.getpid()} {int(time.time())}\n")
                self._acquired = True
                return self
            except FileExistsError:
                try:
                    age = time.time() - self.lock_path.stat().st_mtime
                    if age > self.stale_sec:
                        self.lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for Kiwoom token refresh lock")
                time.sleep(0.1)

    def __exit__(self, *_args: Any) -> None:
        if self._acquired:
            try:
                self.lock_path.unlink(missing_ok=True)
            finally:
                self._acquired = False

    def active_failure(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.failure_path.read_text(encoding="utf-8"))
            failed_at = int(payload.get("failed_at_epoch") or 0)
            if failed_at and time.time() - failed_at < self.cooldown_sec:
                return payload
        except Exception:
            return None
        return None

    def record_failure(self, reason: str) -> None:
        payload = {
            "failed_at_epoch": int(time.time()),
            "reason": str(reason or "token_refresh_failed")[:1000],
        }
        self.failure_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear_failure(self) -> None:
        self.failure_path.unlink(missing_ok=True)
