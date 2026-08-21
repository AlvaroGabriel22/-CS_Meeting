"""Translation service — cache first, engine second, structure always.

Flow for one report::

    strings -> cache lookup (content hash)
            -> batches sized to what the engine takes
            -> one request per batch, paced to the engine's quota, retried
               when the service says to
            -> data-preservation check -> cache write

The UI switching language therefore costs zero requests while the text has not
changed (ADR-0007), and a quota as tight as three requests a minute is a
scheduling problem rather than a failure (ADR-0042).

The policy lives here on purpose: a provider knows how to ask one question, not
how often the system may ask it.
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
from .limits import RateLimiter, call_with_retry, chunked
from .provider import TranslationProvider, TranslationRequest, TranslationResult, get_provider

logger = logging.getLogger(__name__)

#: one limiter per engine, shared by every request in this process — two
#: browser tabs translating at once must still respect a single quota
_LIMITERS: dict[tuple[str, float], RateLimiter] = {}


def _limiter_for(name: str, rpm: float) -> RateLimiter:
    key = (name, float(rpm))
    if key not in _LIMITERS:
        _LIMITERS[key] = RateLimiter(rpm)
    return _LIMITERS[key]


@dataclass
class TranslationOutcome:
    document: dict[str, Any]
    cached: bool
    provider: str
    source_hash: str


@dataclass
class TextTranslation:
    """One string, its translation, and how it got there."""

    original: str
    translated: str
    cached: bool = False
    #: False when the string is a number, a code or empty — never sent anywhere
    translatable: bool = True
    #: set when the answer changed data and was therefore discarded
    rejected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "translated": self.translated,
            "cached": self.cached,
            "translatable": self.translatable,
            "rejected": self.rejected,
        }


@dataclass
class TextTranslationOutcome:
    entries: list[TextTranslation]
    provider: str
    model: str | None = None
    target_language: str = "en"
    source_language: str = "en"

    @property
    def mapping(self) -> dict[str, str]:
        return {entry.original: entry.translated for entry in self.entries}


class TranslationService:
    """Translates user content.  Interface strings are i18n, never this."""

    def __init__(self, provider: TranslationProvider | None = None) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        self._provider = provider or get_provider()
        # the engine declares what it can take; the settings may tighten it
        self._rpm = (
            settings.translation_rpm
            if settings.translation_rpm is not None
            else getattr(self._provider, "requests_per_minute", 0)
        )
        self._batch = min(
            settings.translation_max_batch,
            getattr(self._provider, "max_batch", settings.translation_max_batch),
        )
        self._attempts = settings.translation_retries
        self._limiter = _limiter_for(self._provider.name, self._rpm)

    # -- one request ---------------------------------------------------------- #
    def _ask(self, request: TranslationRequest) -> TranslationResult:
        """One batch: wait for the engine's turn, ask, retry what is worth it.

        Anything that still fails returns the source text.  A translation that
        did not happen is a page in the original language; an exception here
        would be a page with nothing on it.
        """
        if not self._limiter.acquire():
            return TranslationResult(
                segments=list(request.segments),
                provider=self._provider.name,
                meta={"skipped": "rate_limit"},
            )
        try:
            return call_with_retry(
                lambda: self._provider.translate(request),
                attempts=self._attempts,
                describe=f"translation via {self._provider.name}",
            )
        except Exception:  # noqa: BLE001 - the page must survive a dead engine
            logger.exception("translation failed after %d attempt(s)", self._attempts)
            return TranslationResult(
                segments=list(request.segments),
                provider=self._provider.name,
                meta={"failed": True},
            )

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

    # -- strings ------------------------------------------------------------ #
    def translate_texts(
        self,
        session: Session,
        texts: list[str],
        *,
        source_language: str,
        target_language: str,
        department: str | None = None,
    ) -> TextTranslationOutcome:
        """Translate a set of independent strings, cache first.

        Titles, headers, report lines and issue text all arrive here.  Three
        rules hold for every one of them (ADR-0035):

        * a string that is not language (a number, a code, ``""``) is returned
          untouched and never leaves the process;
        * protected terms and data tokens are masked before the request and
          restored after it;
        * an answer whose data tokens differ from the source's is **discarded**
          and the original is kept — a translation may change the language and
          nothing else.
        """
        unique: list[str] = list(dict.fromkeys(texts))
        outcome = TextTranslationOutcome(
            entries=[],
            provider=self._provider.name,
            target_language=target_language,
            source_language=source_language,
        )
        if source_language == target_language:
            outcome.entries = [TextTranslation(text, text, cached=True) for text in unique]
            return outcome

        terms = protected_terms(schema_for(department))
        results: dict[str, TextTranslation] = {}
        pending: list[str] = []

        for text in unique:
            if not documents.is_translatable(text):
                results[text] = TextTranslation(text, text, cached=True, translatable=False)
                continue
            cached = self.lookup(session, documents.text_hash(text), target_language)
            if cached is not None:
                cached.last_used_at = datetime.now(timezone.utc)
                results[text] = TextTranslation(
                    text, (cached.content or {}).get("text", text), cached=True
                )
                continue
            pending.append(text)

        if pending:
            masked: list[str] = []
            mappings: list[dict[str, str]] = []
            for text in pending:
                stripped, mapping = documents.mask_protected(text, terms)
                masked.append(stripped)
                mappings.append(mapping)

            # fewer, larger requests: under a three-a-minute quota the batch
            # size is what decides whether a report translates at all
            answers: list[str] = []
            batches = chunked(list(range(len(pending))), self._batch)
            for index, batch in enumerate(batches, start=1):
                if len(batches) > 1:
                    logger.info("translation batch %d/%d (%d segment(s))", index, len(batches), len(batch))
                result = self._ask(
                    TranslationRequest(
                        segments=[masked[position] for position in batch],
                        source_language=source_language,
                        target_language=target_language,
                        protected_terms=terms,
                    )
                )
                outcome.model = result.model or outcome.model
                outcome.provider = result.provider
                answers.extend(result.segments)

            for text, mapping, answer in zip(pending, mappings, answers):
                translated = documents.unmask_protected(answer, mapping)
                if not documents.preserves_data(text, translated, terms):
                    logger.warning(
                        "translation changed data and was discarded: %r -> %r", text, translated
                    )
                    results[text] = TextTranslation(text, text, rejected=True)
                    continue
                results[text] = TextTranslation(text, translated)
                session.add(
                    Translation(
                        source_hash=documents.text_hash(text),
                        source_language=source_language,
                        target_language=target_language,
                        provider=result.provider,
                        model=result.model,
                        source_preview=text[:200],
                        content={"text": translated},
                        last_used_at=datetime.now(timezone.utc),
                    )
                )
            logger.info(
                "translated %d string(s) (%d from cache) %s -> %s via %s",
                len(pending),
                len(unique) - len(pending),
                source_language,
                target_language,
                result.provider,
            )

        outcome.entries = [results[text] for text in unique]
        return outcome

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
