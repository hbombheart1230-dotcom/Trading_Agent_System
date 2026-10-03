from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..infrastructure.bounded_reader import BoundedReadError
from ..infrastructure.paths import PathAccessError
from ..models.runtime_status import (
    RuntimeStatusResponse,
    ScheduledArtifactContentResponse,
    ScheduledIntelligenceResponse,
    WatchdogHistoryResponse,
)
from ..services.scheduled_artifacts import build_scheduled_artifact_content
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


@router.get("/scheduled-artifact", response_model=ScheduledArtifactContentResponse)
def scheduled_artifact(
    request: Request,
    path: str = Query(min_length=1, max_length=1024),
) -> ScheduledArtifactContentResponse:
    try:
        response = build_scheduled_artifact_content(request.app.state.settings, path)
    except (BoundedReadError, OSError):
        raise HTTPException(status_code=422, detail="artifact is not readable JSON") from None
    except PathAccessError:
        raise HTTPException(status_code=404, detail="artifact not found") from None
    if response is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return response
