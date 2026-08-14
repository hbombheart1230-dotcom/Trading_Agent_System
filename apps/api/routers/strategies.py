from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from ..models.strategies import StrategyDimension, StrategyPerformanceResponse
from ..services.strategy_performance import build_strategy_performance

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


@router.get("/performance", response_model=StrategyPerformanceResponse)
def performance(
    request: Request,
    start: date = Query(),
    end: date = Query(),
    dimension: StrategyDimension = StrategyDimension.PLAYBOOK,
) -> StrategyPerformanceResponse:
    try:
        return build_strategy_performance(
            request.app.state.settings,
            start,
            end,
            dimension,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
