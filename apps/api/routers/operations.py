from __future__ import annotations

from fastapi import APIRouter, Request

from ..models.operations import OperationsDashboardResponse
from ..services.operations import build_operations_dashboard

router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


@router.get("", response_model=OperationsDashboardResponse)
def operations_dashboard(request: Request) -> OperationsDashboardResponse:
    return build_operations_dashboard(request.app.state.settings)
