from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import json

@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    ok: bool
    payload: Dict[str, Any]
    error_code: Optional[str]
    error_message: Optional[str]
    raw_text: str

    @staticmethod
    def from_http(status_code: int, text: str) -> "ApiResponse":
        payload: Dict[str, Any] = {}
        err_code = None
        err_msg = None
        ok = 200 <= int(status_code) < 300

        try:
            data = json.loads(text or "{}")
            if isinstance(data, dict):
                payload = data
                # absorb common error fields
                for k in ("error_code", "err_cd", "rt_cd", "code"):
                    if k in data and not ok:
                        err_code = str(data.get(k))
                        break
                for k in ("error_message", "msg", "message"):
                    if k in data and not ok:
                        err_msg = str(data.get(k))
                        break
            else:
                payload = {"_value": data}
        except Exception:
            payload = {"_raw": text}

        if not ok and err_msg is None:
            err_msg = payload.get("msg") or payload.get("message")

        return ApiResponse(
            status_code=int(status_code),
            ok=ok,
            payload=payload,
            error_code=err_code,
            error_message=err_msg,
            raw_text=text or "",
        )
