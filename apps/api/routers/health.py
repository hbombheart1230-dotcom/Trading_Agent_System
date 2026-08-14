from __future__ import annotations

from fastapi import APIRouter, Request

from ..models.health import HealthResponse, ReadinessResponse
from ..services.health import build_liveness, build_readiness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def live(request: Request) -> HealthResponse:
    return build_liveness(request.app.state.settings)


@router.get("/ready", response_model=ReadinessResponse)
def ready(request: Request) -> ReadinessResponse:
    return build_readiness(request.app.state.settings)
