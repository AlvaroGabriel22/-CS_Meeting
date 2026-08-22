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
from app.domain.glossary import UNIVERSAL, glossary_for
from app.schemas.translation import GlossaryOut, TranslationStatusOut
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


@router.get("/glossary", response_model=GlossaryOut)
def glossary(language: str | None = None) -> GlossaryOut:
    """How the workbook's own vocabulary reads in one language.

    A table somebody decided, not a translation asked for each time: ``Total``
    is ``누적`` because the department says so, and ``PPM`` is ``PPM`` because
    it is read that way everywhere (ADR-0044).  A term that is not in the table
    is shown exactly as the workbook writes it.
    """
    settings = get_settings()
    wanted = language or settings.default_language
    return GlossaryOut(
        language=wanted,
        terms=glossary_for(wanted),
        universal=list(UNIVERSAL),
    )
