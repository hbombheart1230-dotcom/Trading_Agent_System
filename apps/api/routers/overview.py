from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request

from ..models.overview import OverviewResponse
from ..services.overview import build_overview
from ..services.portfolio import resolve_portfolio_day

router = APIRouter(prefix="/api/v1", tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def overview(request: Request, day: date | None = None) -> OverviewResponse:
    resolved = resolve_portfolio_day(request.app.state.settings, day)
    if resolved is None:
        raise HTTPException(status_code=404, detail="no daily operating artifact found")
    return build_overview(request.app.state.settings, resolved)
