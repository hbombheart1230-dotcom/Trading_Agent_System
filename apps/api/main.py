from __future__ import annotations

from fastapi import FastAPI

from .config import ApiSettings
from .infrastructure.public_middleware import install_public_sanitization
from .routers.anomalies import router as anomalies_router
from .routers.health import router as health_router
from .routers.llm_operations import router as llm_operations_router
from .routers.market import router as market_router
from .routers.opportunities import router as opportunities_router
from .routers.overview import router as overview_router
from .routers.performance import router as performance_router
from .routers.portfolio import router as portfolio_router
from .routers.profile import router as profile_router
from .routers.runtime_status import router as runtime_status_router
from .routers.strategies import router as strategies_router
from .routers.trades import router as trades_router


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    resolved_settings = settings or ApiSettings.from_environment()
    app = FastAPI(
        title="Trading Agent Read-only API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = resolved_settings
    install_public_sanitization(app, resolved_settings)
    app.include_router(health_router)
    app.include_router(profile_router)
    app.include_router(runtime_status_router)
    app.include_router(anomalies_router)
    app.include_router(llm_operations_router)
    app.include_router(overview_router)
    app.include_router(portfolio_router)
    app.include_router(performance_router)
    app.include_router(trades_router)
    app.include_router(opportunities_router)
    app.include_router(strategies_router)
    app.include_router(market_router)
    return app


app = create_app()
