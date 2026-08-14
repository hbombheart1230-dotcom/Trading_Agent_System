from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request

from ..models.portfolio import PortfolioResponse
from ..services.portfolio import build_portfolio, resolve_portfolio_day

router = APIRouter(prefix="/api/v1", tags=["portfolio"])


@router.get("/portfolio", response_model=PortfolioResponse)
def portfolio(request: Request, day: date | None = None) -> PortfolioResponse:
    resolved = resolve_portfolio_day(request.app.state.settings, day)
    if resolved is None:
        raise HTTPException(status_code=404, detail="no daily portfolio artifact found")
    return build_portfolio(request.app.state.settings, resolved)
