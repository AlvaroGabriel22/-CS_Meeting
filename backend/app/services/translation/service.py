"""Translation service — cache first, provider second, structure always.

Flow for one Issue Report cell::

    document -> linguistic segments -> cache lookup (content hash)
             -> provider (only on a miss, protected terms masked)
             -> cache write -> document with translated text

The UI switching language therefore costs zero API calls while the text has not
changed (ADR-0007).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Translation
from app.domain.departments import protected_terms, schema_for

from . import documents
from .provider import TranslationProvider, TranslationRequest, get_provider

logger = logging.getLogger(__name__)


@dataclass
class TranslationOutcome:
    document: dict[str, Any]
    cached: bool
    provider: str
    source_hash: str


class TranslationService:
    """Translates user content.  Interface strings are i18n, never this."""

    def __init__(self, provider: TranslationProvider | None = None) -> None:
        self._provider = provider or get_provider()

    # -- cache ------------------------------------------------------------- #
    def lookup(self, session: Session, source_hash: str, target_language: str) -> Translation | None:
        return session.scalars(
            select(Translation)
            .where(
                Translation.source_hash == source_hash,
                Translation.target_language == target_language,
                Translation.provider == self._provider.name,
            )
            .limit(1)
        ).first()

    # -- main entry point --------------------------------------------------- #
    def translate_document(
        self,
        session: Session,
        document: dict[str, Any],
        *,
        source_language: str,
        target_language: str,
        department: str | None = None,
    ) -> TranslationOutcome:
        source_hash = documents.content_hash(document)

        if source_language == target_language:
            return TranslationOutcome(document, True, self._provider.name, source_hash)

        cached = self.lookup(session, source_hash, target_language)
        if cached is not None:
            cached.last_used_at = datetime.now(timezone.utc)
            logger.info("translation cache hit (%s -> %s)", source_language, target_language)
            return TranslationOutcome(cached.content, True, self._provider.name, source_hash)

        terms = protected_terms(schema_for(department))
        segments = documents.extract_segments(document)
        masked: list[str] = []
        mappings: list[dict[str, str]] = []
        for segment in segments:
            if not documents.is_translatable(segment):
                masked.append(segment)
                mappings.append({})
                continue
            text, mapping = documents.mask_protected(segment, terms)
            masked.append(text)
            mappings.append(mapping)

        result = self._provider.translate(
            TranslationRequest(
                segments=masked,
                source_language=source_language,
                target_language=target_language,
                protected_terms=terms,
            )
        )
        restored = [
            documents.unmask_protected(segment, mapping)
            for segment, mapping in zip(result.segments, mappings)
        ]
        translated = documents.apply_segments(document, restored)

        session.add(
            Translation(
                source_hash=source_hash,
                source_language=source_language,
                target_language=target_language,
                provider=result.provider,
                model=result.model,
                source_preview=documents.plain_text(document)[:200],
                content=translated,
                last_used_at=datetime.now(timezone.utc),
            )
        )
        logger.info(
            "translated %d segment(s) %s -> %s via %s",
            len(segments),
            source_language,
            target_language,
            result.provider,
        )
        return TranslationOutcome(translated, False, result.provider, source_hash)
