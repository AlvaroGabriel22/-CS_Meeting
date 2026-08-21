"""Translation status.

The page's own words are interface text, translated by the application's
bundles.  The only *content* that is ever translated is the report a person
wrote, and that lives on the report endpoint (ADR-0036).

This endpoint exists so the UI can say whether a provider is configured at all.
The API key stays in this process: the browser asks for a language, never for a
provider (ADR-0009).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.translation import TranslationStatusOut
from app.services.translation import get_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["translation"])


@router.get("/translation/status", response_model=TranslationStatusOut)
def translation_status() -> TranslationStatusOut:
    """Which provider is configured, and what it can do.

    ``provider: "null"`` means no key is configured: the whole path still runs
    and every string comes back as it went in.  Nothing is ever sent anywhere.
    """
    settings = get_settings()
    provider = get_provider()
    return TranslationStatusOut(
        provider=provider.name,
        # the engine names its own model; the settings hold one entry per engine
        model=getattr(provider, "model", None),
        languages=list(settings.supported_languages),
        default_language=settings.default_language,
        active=provider.name != "null",
    )
