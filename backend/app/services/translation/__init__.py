"""Translation: provider seam, document rules and the cache-first service."""

from .documents import (
    apply_segments,
    content_hash,
    data_tokens,
    extract_segments,
    plain_text,
    preserves_data,
    text_hash,
)
from .provider import (
    NullProvider,
    configure_from_settings,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
    available_providers,
    get_provider,
    register_provider,
)
from .service import (
    TextTranslation,
    TextTranslationOutcome,
    TranslationOutcome,
    TranslationService,
)

__all__ = [
    "NullProvider",
    "TextTranslation",
    "TextTranslationOutcome",
    "TranslationOutcome",
    "TranslationProvider",
    "TranslationRequest",
    "TranslationResult",
    "TranslationService",
    "apply_segments",
    "available_providers",
    "configure_from_settings",
    "content_hash",
    "data_tokens",
    "extract_segments",
    "get_provider",
    "plain_text",
    "preserves_data",
    "register_provider",
    "text_hash",
]
