from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin

import time

try:
    import requests
except Exception as e:  # pragma: no cover
    requests = None


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: Dict[str, Any]
    text: str


class HttpClientError(Exception):
    pass


class HttpClient:
    """Minimal HTTP client with timeout + retry.
    - Centralizes base_url handling
    - No Kiwoom-specific logic here (token/header building lives elsewhere)
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout_sec: int = 10,
        retry_max: int = 2,
        backoff_sec: float = 0.5,
        session: Optional["requests.Session"] = None,
    ):
        if requests is None:  # pragma: no cover
            raise HttpClientError("requests is required for HttpClient. Please install requests.")
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout_sec = int(timeout_sec)
        self.retry_max = int(retry_max)
        self.backoff_sec = float(backoff_sec)
        self.session = session or requests.Session()

    def build_url(self, path: str) -> str:
        path = path.lstrip("/")
        return urljoin(self.base_url, path)

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Any = None,
        dry_run: bool = False,
    ) -> Tuple[str, Optional[HttpResponse]]:
        """Perform an HTTP request.
        Returns (url, response).
        If dry_run=True, does not send the request and returns (url, None).
        """
        url = self.build_url(path)
        if dry_run:
            return url, None

        last_err: Optional[Exception] = None
        for attempt in range(self.retry_max + 1):
            try:
                r = self.session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers or {},
                    params=params,
                    json=json_body,
                    data=data,
                    timeout=self.timeout_sec,
                )
                return url, HttpResponse(
                    status_code=int(r.status_code),
                    headers=dict(r.headers),
                    text=r.text,
                )
            except Exception as e:
                last_err = e
                if attempt >= self.retry_max:
                    break
                time.sleep(self.backoff_sec * (2 ** attempt))

        raise HttpClientError(f"HTTP request failed after retries: {last_err}") from last_err
