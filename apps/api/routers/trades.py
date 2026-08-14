from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from ..models.reports import ReportCatalogResponse, ReportContentResponse
from ..models.trades import TradeDetailResponse, TradeListResponse
from ..services.reports import build_report_catalog, build_report_content
from ..services.trades import build_trade_detail, build_trade_list, resolve_trade_range

router = APIRouter(prefix="/api/v1/trades", tags=["trades"])


@router.get("", response_model=TradeListResponse)
def trades(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    symbol: str | None = None,
    result: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> TradeListResponse:
    period = resolve_trade_range(request.app.state.settings, start, end)
    if period is None:
        raise HTTPException(status_code=404, detail="no trade artifacts found")
    try:
        return build_trade_list(
            request.app.state.settings,
            period[0],
            period[1],
            symbol=symbol.strip().upper() if symbol else None,
            result=result.strip() if result else None,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{trade_id}", response_model=TradeDetailResponse)
def trade_detail(request: Request, trade_id: str) -> TradeDetailResponse:
    response = build_trade_detail(request.app.state.settings, trade_id)
    if response is None:
        raise HTTPException(status_code=404, detail="trade not found")
    return response


@router.get("/{trade_id}/reports", response_model=ReportCatalogResponse)
def report_catalog(request: Request, trade_id: str) -> ReportCatalogResponse:
    response = build_report_catalog(request.app.state.settings, trade_id)
    if response is None:
        raise HTTPException(status_code=404, detail="trade not found")
    return response


@router.get(
    "/{trade_id}/reports/{report_id}",
    response_model=ReportContentResponse,
)
def report_content(
    request: Request,
    trade_id: str,
    report_id: str,
) -> ReportContentResponse:
    response = build_report_content(request.app.state.settings, trade_id, report_id)
    if response is None:
        raise HTTPException(status_code=404, detail="trade or report not found")
    return response
