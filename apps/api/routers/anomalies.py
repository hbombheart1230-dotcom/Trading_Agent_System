from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, Request

from ..models.anomalies import AnomalyResponse
from ..services.anomalies import build_anomalies, resolve_anomaly_day

router = APIRouter(prefix="/api/v1/anomalies", tags=["anomalies"])


@router.get("", response_model=AnomalyResponse)
def anomalies(
    request: Request,
    day: date | None = Query(default=None),
) -> AnomalyResponse:
    return build_anomalies(
        request.app.state.settings,
        resolve_anomaly_day(day),
    )
