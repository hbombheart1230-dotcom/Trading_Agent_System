from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..models.runtime_status import RuntimeStatusResponse, ScheduledIntelligenceResponse, WatchdogHistoryResponse
from ..services.runtime_status import build_runtime_status, build_scheduled_intelligence, build_watchdog_history

router = APIRouter(prefix="/api/v1/runtime", tags=["runtime-status"])


@router.get("/status", response_model=RuntimeStatusResponse)
def status(request: Request) -> RuntimeStatusResponse:
    return build_runtime_status(request.app.state.settings)


@router.get("/watchdog-history", response_model=WatchdogHistoryResponse)
def watchdog_history(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
) -> WatchdogHistoryResponse:
    return build_watchdog_history(request.app.state.settings, limit=limit)


@router.get("/scheduled-intelligence", response_model=ScheduledIntelligenceResponse)
def scheduled_intelligence(request: Request) -> ScheduledIntelligenceResponse:
    return build_scheduled_intelligence(request.app.state.settings)
