from __future__ import annotations

from fastapi import APIRouter, Request

from ..models.profile import ExposureProfileResponse
from ..services.profile import build_exposure_profile

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.get("", response_model=ExposureProfileResponse)
def profile(request: Request) -> ExposureProfileResponse:
    return build_exposure_profile(request.app.state.settings)
