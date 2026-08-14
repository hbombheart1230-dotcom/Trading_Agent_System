from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from ..models.opportunities import OpportunityFunnelResponse, OpportunityOutcomesResponse
from ..services.opportunities import (
    build_opportunity_funnel,
    build_opportunity_outcomes,
    resolve_opportunity_day,
)

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


@router.get("/funnel", response_model=OpportunityFunnelResponse)
def funnel(
    request: Request,
    day: date | None = Query(default=None),
) -> OpportunityFunnelResponse:
    resolved = resolve_opportunity_day(request.app.state.settings, day)
    if resolved is None:
        raise HTTPException(status_code=404, detail="no opportunity data")
    return build_opportunity_funnel(request.app.state.settings, resolved)


@router.get("/outcomes", response_model=OpportunityOutcomesResponse)
def outcomes(
    request: Request,
    day: date | None = Query(default=None),
) -> OpportunityOutcomesResponse:
    resolved = resolve_opportunity_day(
        request.app.state.settings,
        day,
        outcomes=True,
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="no opportunity outcome data")
    return build_opportunity_outcomes(request.app.state.settings, resolved)
