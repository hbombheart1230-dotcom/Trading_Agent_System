from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .data_access import (
    OperatorUIConfig,
    load_health,
    load_overview,
    load_recent_runs,
    load_run_detail,
    load_trade_report_detail,
)


def create_app(config: Optional[OperatorUIConfig] = None) -> FastAPI:
    cfg = config or OperatorUIConfig.from_env()
    base_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(base_dir / "templates"))

    app = FastAPI(
        title="Trading Agent Operator UI",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.operator_ui_config = cfg
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            name="overview.html",
            request=request,
            context={
                "page_title": "Operator Console",
                "section": "overview",
                "overview": load_overview(cfg),
            },
        )

    @app.get("/runs", response_class=HTMLResponse)
    def runs(
        request: Request,
        limit: int = Query(default=50, ge=1, le=200),
        mismatch_only: bool = Query(default=False),
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            name="runs.html",
            request=request,
            context={
                "page_title": "Recent Runs",
                "section": "runs",
                "runs": load_recent_runs(cfg, limit=limit, mismatch_only=mismatch_only),
                "limit": int(limit),
                "mismatch_only": bool(mismatch_only),
            },
        )

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(request: Request, run_id: str) -> HTMLResponse:
        detail = load_run_detail(cfg, run_id)
        if not detail.get("found"):
            raise HTTPException(status_code=404, detail=f"run_id not found: {run_id}")
        return templates.TemplateResponse(
            name="run_detail.html",
            request=request,
            context={
                "page_title": f"Run {run_id}",
                "section": "runs",
                "detail": detail,
            },
        )

    @app.get("/reports/trade/{story_id}", response_class=HTMLResponse)
    def trade_report_detail(request: Request, story_id: str) -> HTMLResponse:
        report = load_trade_report_detail(cfg, story_id)
        if not report.get("found"):
            raise HTTPException(status_code=404, detail=f"trade report not found: {story_id}")
        return templates.TemplateResponse(
            name="trade_report_detail.html",
            request=request,
            context={
                "page_title": f"Trade Report {story_id}",
                "section": "runs",
                "report": report,
            },
        )

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        return JSONResponse(load_health(cfg))

    return app


app = create_app()
