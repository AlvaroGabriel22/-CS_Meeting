"""Translation architecture — the seam, the cache and the format rules.

No AI is called here (Sprint 0 ships the architecture, not the provider): a
recording fake stands in for one, which is exactly what the seam is for.
"""

from __future__ import annotations

from app.db.models import Translation
from app.services.translation import (
    TranslationRequest,
    TranslationResult,
    TranslationService,
    documents,
)

DOC = {
    "type": "doc",
    "content": [
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Excessive solder was found on the connector."},
                {"type": "hardBreak"},
                {"type": "image", "attrs": {"src": "/api/assets/17", "width": 420}},
                {"type": "text", "marks": [{"type": "bold"}], "text": "PPM: 3,000 in W32."},
            ],
        }
    ],
}


class FakeProvider:
    """Uppercases text so a translation is visible, and records what it saw."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[TranslationRequest] = []

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls.append(request)
        return TranslationResult(
            segments=[segment.upper() for segment in request.segments],
            provider=self.name,
            model="fake-1",
        )


# --------------------------------------------------------------------------- #
# Document rules
# --------------------------------------------------------------------------- #
def test_only_text_nodes_are_extracted() -> None:
    assert documents.extract_segments(DOC) == [
        "Excessive solder was found on the connector.",
        "PPM: 3,000 in W32.",
    ]


def test_images_and_structure_survive_translation() -> None:
    translated = documents.apply_segments(DOC, ["Excesso de solda.", "PPM: 3,000 na W32."])
    nodes = translated["content"][0]["content"]
    assert [node["type"] for node in nodes] == ["text", "hardBreak", "image", "text"]
    assert nodes[2]["attrs"] == {"src": "/api/assets/17", "width": 420}  # image untouched
    assert nodes[3]["marks"] == [{"type": "bold"}]  # bold survives
    assert nodes[0]["text"] == "Excesso de solda."
    assert DOC["content"][0]["content"][0]["text"].startswith("Excessive")  # source untouched


def test_hash_ignores_images_and_styles_but_not_words() -> None:
    same_words = documents.apply_segments(DOC, documents.extract_segments(DOC))
    same_words["content"][0]["content"][2]["attrs"]["width"] = 999
    assert documents.content_hash(same_words) == documents.content_hash(DOC)

    edited = documents.apply_segments(DOC, ["Different text.", "PPM: 3,000 in W32."])
    assert documents.content_hash(edited) != documents.content_hash(DOC)


def test_numbers_alone_are_not_language() -> None:
    assert not documents.is_translatable("3,000")
    assert not documents.is_translatable("  ")
    assert documents.is_translatable("Excessive solder")


def test_protected_terms_are_masked_and_restored() -> None:
    masked, mapping = documents.mask_protected("PPM in W32 for SEC", ("PPM", "SEC", "W32"))
    assert "PPM" not in masked and "SEC" not in masked and "W32" not in masked
    assert documents.unmask_protected(masked, mapping) == "PPM in W32 for SEC"


# --------------------------------------------------------------------------- #
# Service behaviour
# --------------------------------------------------------------------------- #
def test_translation_is_cached_by_content_hash(session) -> None:
    provider = FakeProvider()
    service = TranslationService(provider)

    first = service.translate_document(
        session, DOC, source_language="en", target_language="pt-BR", department="IQC"
    )
    assert first.cached is False
    session.flush()

    second = service.translate_document(
        session, DOC, source_language="en", target_language="pt-BR", department="IQC"
    )
    assert second.cached is True
    assert len(provider.calls) == 1, "a language switch must not call the provider again"
    assert second.document == first.document

    stored = session.query(Translation).filter_by(source_hash=first.source_hash).all()
    assert len(stored) == 1 and stored[0].target_language == "pt-BR"


def test_edited_text_misses_the_cache(session) -> None:
    provider = FakeProvider()
    service = TranslationService(provider)
    service.translate_document(session, DOC, source_language="en", target_language="ko")
    session.flush()

    edited = documents.apply_segments(DOC, ["A different finding.", "PPM: 3,000 in W32."])
    outcome = service.translate_document(session, edited, source_language="en", target_language="ko")
    assert outcome.cached is False and len(provider.calls) == 2


def test_protected_terms_never_reach_the_provider(session) -> None:
    provider = FakeProvider()
    service = TranslationService(provider)
    service.translate_document(
        session, DOC, source_language="en", target_language="ko", department="IQC"
    )
    sent = " ".join(provider.calls[0].segments)
    assert "PPM" not in sent and "W32" not in sent

    outcome = service.translate_document(
        session, DOC, source_language="en", target_language="pt-BR", department="IQC"
    )
    text = documents.plain_text(outcome.document)
    assert "PPM" in text and "W32" in text  # restored on the way back


def test_same_language_is_a_no_op(session) -> None:
    provider = FakeProvider()
    outcome = TranslationService(provider).translate_document(
        session, DOC, source_language="en", target_language="en"
    )
    assert outcome.cached is True and outcome.document is DOC and not provider.calls
