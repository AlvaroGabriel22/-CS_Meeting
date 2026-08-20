"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analytics, exports, health, imports, issues, presentations
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.debug)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Executive quality presentations for IQC / OQC / FIELD.",
    )

    # local-only tool: the Vite dev server talks to this API from another port
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        logger.warning("%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )

    app.include_router(health.router)
    app.include_router(imports.router)
    app.include_router(presentations.router)
    app.include_router(analytics.router)
    app.include_router(issues.router)
    app.include_router(exports.router)
    return app


app = create_app()
