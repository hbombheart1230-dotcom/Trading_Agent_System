from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from ..models.market import MarketSeriesResponse, MarketSnapshotResponse
from ..services.market import build_market_series, build_market_snapshot, resolve_market_day

router = APIRouter(prefix="/api/v1/market", tags=["market"])


@router.get("/snapshot", response_model=MarketSnapshotResponse)
def snapshot(
    request: Request,
    day: date | None = Query(default=None),
) -> MarketSnapshotResponse:
    resolved = resolve_market_day(request.app.state.settings, day)
    if resolved is None:
        raise HTTPException(status_code=404, detail="no market data")
    return build_market_snapshot(request.app.state.settings, resolved)


@router.get("/series", response_model=MarketSeriesResponse)
def series(
    request: Request,
    start: date = Query(),
    end: date = Query(),
    metric: str = Query(min_length=1, max_length=64),
) -> MarketSeriesResponse:
    try:
        return build_market_series(
            request.app.state.settings,
            start,
            end,
            metric,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
