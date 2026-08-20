"""Health and capability discovery."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.excel import PARSER_VERSION

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "parserVersion": PARSER_VERSION,
        "maxActivePresentations": settings.max_active_presentations,
        "languages": list(settings.supported_languages),
        "defaultLanguage": settings.default_language,
        "translationProvider": settings.translation_provider,
    }
