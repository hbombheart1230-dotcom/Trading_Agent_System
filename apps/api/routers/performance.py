from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from ..models.common import CostBasis
from ..models.performance import PerformanceSeriesResponse, PerformanceSummaryResponse
from ..services.performance import build_performance_series, build_performance_summary

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])


@router.get("/summary", response_model=PerformanceSummaryResponse)
def summary(
    request: Request,
    start: date = Query(),
    end: date = Query(),
    cost_basis: CostBasis = CostBasis.MOCK_BROKER_NET,
) -> PerformanceSummaryResponse:
    try:
        return build_performance_summary(
            request.app.state.settings,
            start,
            end,
            cost_basis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/series", response_model=PerformanceSeriesResponse)
def series(
    request: Request,
    start: date = Query(),
    end: date = Query(),
    cost_basis: CostBasis = CostBasis.MOCK_BROKER_NET,
) -> PerformanceSeriesResponse:
    try:
        return build_performance_series(
            request.app.state.settings,
            start,
            end,
            cost_basis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
