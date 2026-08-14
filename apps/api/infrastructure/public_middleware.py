from __future__ import annotations

import json

from fastapi import FastAPI
from starlette.responses import Response

from ..config import ApiSettings
from .public_sanitization import sanitize_public_payload


def install_public_sanitization(app: FastAPI, settings: ApiSettings) -> None:
    if not settings.public_mode:
        return

    @app.middleware("http")
    async def sanitize_json_response(request, call_next):
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="application/json",
            )
        sanitized = json.dumps(
            sanitize_public_payload(payload),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=sanitized,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )
