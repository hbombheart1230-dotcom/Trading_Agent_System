from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, Request

from ..models.llm_operations import LlmOperationsResponse
from ..services.llm_operations import build_llm_operations, resolve_llm_day

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


@router.get("/operations", response_model=LlmOperationsResponse)
def operations(
    request: Request,
    day: date | None = Query(default=None),
) -> LlmOperationsResponse:
    settings = request.app.state.settings
    return build_llm_operations(settings, resolve_llm_day(settings, day))
