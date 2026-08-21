"""Translation — everything a person wrote, as a layer over it.

The page's own words are interface text and workbook labels; neither is ever
sent anywhere.  What a provider does see is what somebody typed: the report and
the titles they gave the charts and tables.  Three properties hold for both
(ADR-0035, ADR-0039):

* the **original is always available** — nothing stored is modified and the
  response carries both sides;
* **only language may change** — an answer whose data tokens differ from the
  source's is discarded and the original is kept;
* the path works **without a key**: the null provider returns the source, so
  the feature degrades to "no translation", never to "wrong translation".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.translation import documents
from app.services.translation.anthropic_provider import AnthropicProvider, _parse
from app.services.translation.provider import (
    TranslationRequest,
    TranslationResult,
    register_provider,
)

TITLE = "Relatório da semana"
LINES = [
    "Rejection rate rose in Aug, driven by the Local supplier.",
    "Containment in place since 12/08, 3.000 units re-inspected.",
    "Supplier audit scheduled for W35.",
]


def _content() -> dict:
    """A one-column report whose cell holds the three lines, in order."""
    return {
        "title": TITLE,
        "columns": [{"id": "c1", "name": "Observação"}],
        "rows": [
            {
                "id": "r1",
                "cells": {
                    "c1": [
                        {"id": f"b{index}", "type": "text", "text": line}
                        for index, line in enumerate(LINES)
                    ]
                },
            }
        ],
    }


def _texts(content: dict) -> list[str]:
    return [block["text"] for block in content["rows"][0]["cells"]["c1"]]

#: each test gets its own provider name, so one test's cache entries can never
#: answer another test's request — the cache is keyed by provider
_FAKE_COUNT = iter(range(1, 1000))


class FakeProvider:
    """A provider that really changes the words, and records what it saw."""

    def __init__(self) -> None:
        self.name = f"fake-{next(_FAKE_COUNT)}"
        self.seen: list[list[str]] = []

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.seen.append(list(request.segments))
        return TranslationResult(
            segments=[f"[{request.target_language}] {segment}" for segment in request.segments],
            provider=self.name,
            model="fake-1",
        )


class DataCorruptingProvider:
    """A provider that loses the figures it was given."""

    name = "corrupting"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        return TranslationResult(
            segments=["conteudo completamente outro" for _ in request.segments],
            provider=self.name,
            model="bad-1",
        )


@pytest.fixture()
def fake_provider(monkeypatch):
    provider = FakeProvider()
    register_provider(provider)
    monkeypatch.setattr(
        "app.services.translation.service.get_provider", lambda name=None: provider
    )
    return provider


def _upload(client, path: Path, department: str = "IQC"):
    return client.post(
        "/api/uploads",
        data={"department": department, "createVersion": "true"},
        files={
            "file": (
                path.name,
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    ).json()


def _with_report(client, iqc_real: Path) -> int:
    version_id = _upload(client, iqc_real)["versionId"]
    client.put(f"/api/versions/{version_id}/report", json={"content": _content()})
    return version_id


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #
def test_the_status_says_which_provider_is_configured(client) -> None:
    status = client.get("/api/translation/status").json()
    assert status["provider"].startswith(("null", "anthropic", "fake"))
    assert status["languages"] == ["en", "pt-BR", "ko"]
    assert "apiKey" not in status and "key" not in status  # never leaves the backend


def test_without_a_provider_the_report_comes_back_untouched(client, iqc_real: Path) -> None:
    version_id = _with_report(client, iqc_real)
    body = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "ko"}
    ).json()

    assert body["provider"] == "null"
    assert body["translated"] == body["original"]
    assert body["translated"]["title"] == TITLE


# --------------------------------------------------------------------------- #
# The report, and only the report
# --------------------------------------------------------------------------- #
def test_the_title_columns_and_text_are_translated(client, iqc_real: Path, fake_provider) -> None:
    version_id = _with_report(client, iqc_real)
    body = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "pt-BR"}
    ).json()

    assert body["original"]["title"] == TITLE  # the author's report, untouched
    assert body["translated"]["title"] == f"[pt-BR] {TITLE}"
    assert body["translated"]["columns"][0]["name"] == "[pt-BR] Observação"
    assert _texts(body["translated"]) == [f"[pt-BR] {line}" for line in LINES]
    # the structure is the author's and does not move
    assert len(body["translated"]["rows"]) == len(body["original"]["rows"])


def test_nothing_but_the_report_is_ever_sent(client, iqc_real: Path, fake_provider) -> None:
    version_id = _with_report(client, iqc_real)
    client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "pt-BR"}
    )

    sent = [segment for batch in fake_provider.seen for segment in batch]
    assert sent, "the report was sent"
    # nothing that exists only in the workbook is part of the request: no label,
    # no metric name, no value.  Words the *author* used are of course sent —
    # they are the text being translated.
    for foreign in ("Rej. Lot", "Insp. Lot", "TTL", "SEC", "TNP", "5,495", "35,714"):
        assert all(foreign not in segment for segment in sent), foreign
    # and inside the author's own sentence, the data tokens are masked out
    assert all("3.000" not in segment for segment in sent)
    assert all("W35" not in segment for segment in sent)
    assert all("12/08" not in segment for segment in sent)


def test_the_stored_report_is_never_modified(client, iqc_real: Path, fake_provider) -> None:
    version_id = _with_report(client, iqc_real)
    before = client.get(f"/api/versions/{version_id}/report").json()

    client.post(f"/api/versions/{version_id}/translation", json={"targetLanguage": "ko"})

    after = client.get(f"/api/versions/{version_id}/report").json()
    assert after["content"] == before["content"]


def test_the_second_call_is_served_from_the_cache(client, iqc_real: Path, fake_provider) -> None:
    version_id = _with_report(client, iqc_real)
    first = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "ko"}
    ).json()
    calls = len(fake_provider.seen)

    second = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "ko"}
    ).json()

    assert len(fake_provider.seen) == calls, "no second round-trip for the same text"
    assert second["cachedCount"] > 0
    assert second["translated"] == first["translated"]


def test_an_answer_that_changed_the_data_is_discarded(client, iqc_real: Path, monkeypatch) -> None:
    provider = DataCorruptingProvider()
    register_provider(provider)
    monkeypatch.setattr(
        "app.services.translation.service.get_provider", lambda name=None: provider
    )
    version_id = _with_report(client, iqc_real)
    body = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "pt-BR"}
    ).json()

    # the two lines carrying figures lost them, so they keep the author's words
    assert body["rejectedCount"] == 2
    kept = [line for line in _texts(body["translated"]) if line in LINES]
    assert kept == [LINES[1], LINES[2]]  # "12/08 … 3.000" and "W35"
    # the line with no figures had nothing to lose and was replaced
    assert LINES[0] not in _texts(body["translated"])


def test_an_unsupported_language_is_refused(client, iqc_real: Path) -> None:
    version_id = _with_report(client, iqc_real)
    response = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "fr"}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["targetLanguage"] == "fr"


def test_a_version_without_a_report_still_answers(client, iqc_real: Path) -> None:
    """An empty report is not an error — there is simply nothing to translate."""
    version_id = _upload(client, iqc_real)["versionId"]
    body = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "ko"}
    ).json()
    assert body["translated"]["rows"] == []
    assert body["stringCount"] == 0


# --------------------------------------------------------------------------- #
# The titles a person typed travel with the report
# --------------------------------------------------------------------------- #
def test_the_titles_the_user_typed_are_translated(client, iqc_real: Path, fake_provider) -> None:
    version_id = _with_report(client, iqc_real)
    client.put(
        "/api/departments/IQC/settings",
        json={
            "chartTitles": {"TTL": "Entrada total"},
            "tableTitles": {"TTL": "Resumo do mês"},
        },
    )

    body = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "ko"}
    ).json()

    assert body["chartTitles"] == {"TTL": "[ko] Entrada total"}
    assert body["tableTitles"] == {"TTL": "[ko] Resumo do mês"}
    # the stored settings keep the author's words
    saved = client.get("/api/departments/IQC/settings").json()
    assert saved["chartTitles"] == {"TTL": "Entrada total"}


def test_the_table_key_is_never_translated(client, iqc_real: Path, fake_provider) -> None:
    """``TTL`` is how the workbook names the table: it keys the map, untouched."""
    version_id = _with_report(client, iqc_real)
    client.put("/api/departments/IQC/settings", json={"chartTitles": {"TTL": "Entrada total"}})

    body = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "ko"}
    ).json()
    assert list(body["chartTitles"]) == ["TTL"]


@pytest.mark.parametrize("department", ["IQC", "OQC", "FIELD"])
def test_every_department_translates_the_same_way(
    client, iqc_real: Path, fake_provider, department
) -> None:
    """The department only decides which technical terms are masked."""
    created = client.post(
        "/api/uploads",
        data={"department": department, "createVersion": "true"},
        files={
            "file": (
                iqc_real.name,
                iqc_real.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    ).json()
    version_id = created["versionId"]
    client.put(f"/api/versions/{version_id}/report", json={"content": _content()})

    body = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "pt-BR"}
    ).json()
    assert body["department"] == department
    assert body["translated"]["title"] == f"[pt-BR] {TITLE}"


# --------------------------------------------------------------------------- #
# The rules, unit by unit
# --------------------------------------------------------------------------- #
def test_a_date_is_masked_as_one_datum() -> None:
    """``12/08`` is a date, not two numbers: it must travel as a unit.

    Split in two, a model writing the date the way its language does would
    reorder the placeholders and the answer would be discarded — correct, but
    needlessly.  Whole, it comes back untouched.
    """
    from app.domain.departments import protected_terms, schema_for

    masked, mapping = documents.mask_protected(
        "Contencao aplicada em 12/08.", protected_terms(schema_for("IQC"))
    )
    assert list(mapping.values()) == ["12/08"]
    assert masked.count("§") == 2  # one placeholder, not two
    assert "12/08" in documents.data_tokens("Contencao aplicada em 12/08.")
    assert "2026-08-12" in documents.data_tokens("entrega em 2026-08-12")


def test_the_guard_reads_a_language_that_writes_without_spaces() -> None:
    """Korean glues a particle onto the number: ``12/08에``.

    Python's ``\\w`` counts 에 as a word character, so a ``(?!\\w)`` boundary made
    the guard blind to the date and it rejected a translation that was in fact
    perfect.  Found by running a real model, not by reading the code.
    """
    from app.domain.departments import protected_terms, schema_for

    terms = protected_terms(schema_for("IQC"))
    original = "Contencao aplicada em 12/08; auditoria na proxima semana."
    korean = "12/08에 적용된 통제; 다음 주 감사."

    assert documents.data_tokens(korean) == documents.data_tokens(original)
    assert documents.preserves_data(original, korean, terms)
    # a protected term with a particle attached is still the same term
    assert documents.preserves_data("PPM subiu 13,4%", "PPM은 13,4% 상승", terms)
    # and the check still catches a number that really moved
    assert not documents.preserves_data("13,4%", "13.4%", terms)


def test_data_preservation_is_checked_token_by_token() -> None:
    assert documents.preserves_data("PPM subiu 13,4% na W33", "PPM rose 13,4% in W33", ("PPM",))
    # a localised decimal separator *is* a changed number
    assert not documents.preserves_data("13,4%", "13.4%")
    # a dropped figure
    assert not documents.preserves_data("2 lotes de 3.000", "lots of 3.000")
    # a dropped protected term
    assert not documents.preserves_data("PPM do SEC", "the section", ("PPM", "SEC"))


def test_a_language_that_spells_a_word_with_a_digit_is_not_refused() -> None:
    """Korean writes August as ``8월`` and "third party" as ``제3자``.

    The rule protects the *source's* figures: every one of them must survive
    verbatim.  A digit the translation adds is orthography, not a changed
    number — the source's figures were masked and came back untouched.
    """
    assert documents.preserves_data("Fornecedor acima do limite em Aug", "8월 한도 초과 공급업체")
    assert documents.preserves_data("Terceiros", "제3자")
    # and losing one is still refused
    assert not documents.preserves_data("Aug: 3.000 pecas", "8월: 4.000 pecas")


def test_the_cache_key_is_the_text_itself() -> None:
    doc = {"type": "doc", "content": [{"type": "paragraph", "content": [
        {"type": "text", "text": "Containment in place."}]}]}
    assert documents.text_hash("Containment in place.") == documents.content_hash(doc)


def test_a_malformed_provider_answer_keeps_the_source() -> None:
    """A broken answer must never corrupt the report."""
    source = ["first line", "second line"]
    assert _parse("not json at all", 2, source) == source
    assert _parse('["only one"]', 2, source) == source
    assert _parse('["um", "dois"]', 2, source) == ["um", "dois"]


def test_the_provider_is_configured_from_the_backend_only() -> None:
    provider = AnthropicProvider("secret-key", "claude-sonnet-5")
    assert provider.name == "anthropic"
    # the key is held here and appears in no payload the client can request
    assert "secret-key" not in str(vars(provider).keys())


# --------------------------------------------------------------------------- #
# Engines — the seam holds whichever one is configured (ADR-0040)
# --------------------------------------------------------------------------- #
def test_the_configured_engine_is_the_one_registered(monkeypatch) -> None:
    """Nothing is registered without being asked for, in either direction."""
    from app.core.config import Settings, get_settings
    from app.services.translation import provider as seam

    def settings_with(**values):
        base = get_settings().model_dump()
        base.update(values)
        return Settings(**base)

    monkeypatch.setattr(
        "app.core.config.get_settings", lambda: settings_with(translation_provider="null")
    )
    assert seam.configure_from_settings() in ("null", "corrupting", "fake", "ollama", "anthropic")

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: settings_with(translation_provider="anthropic", anthropic_api_key=None),
    )
    # asked for a remote engine with no key: nothing is sent anywhere
    assert seam.configure_from_settings() != "anthropic"


def test_the_local_engine_asks_the_same_question(monkeypatch) -> None:
    """Ollama gets the shared prompt, temperature zero and the segments as JSON."""
    import httpx

    from app.services.translation.ollama_provider import OllamaProvider

    seen: dict = {}

    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"model": "gemma4:e2b", "message": {"content": '["um", "dois"]'}}

    def fake_post(url, json=None, timeout=None):
        seen["url"] = url
        seen["payload"] = json
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider("http://127.0.0.1:11434", "gemma4:e2b")
    result = provider.translate(
        TranslationRequest(segments=["one", "two"], source_language="en", target_language="pt-BR")
    )

    assert result.segments == ["um", "dois"]
    assert seen["url"].endswith("/api/chat")
    assert seen["payload"]["options"]["temperature"] == 0
    assert seen["payload"]["stream"] is False
    system = seen["payload"]["messages"][0]["content"]
    assert "pt-BR" in system and "§A§" in system  # the placeholder rule travels


def test_a_local_engine_that_is_down_keeps_the_text(monkeypatch) -> None:
    """Ollama not running is not a reason to lose what somebody wrote."""
    import httpx

    from app.services.translation.ollama_provider import OllamaProvider

    def refuse(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", refuse)
    provider = OllamaProvider("http://127.0.0.1:11434", "gemma4:e2b")
    result = provider.translate(
        TranslationRequest(segments=["kept"], source_language="en", target_language="ko")
    )
    assert result.segments == ["kept"] and result.meta["failed"] is True


def test_an_answer_wrapped_in_an_object_is_still_read() -> None:
    """Small local models like to wrap the array; the parser copes."""
    from app.services.translation.provider import parse_segments

    assert parse_segments('{"translations": ["um", "dois"]}', 2, ["one", "two"]) == ["um", "dois"]
    assert parse_segments('here you go:\n["um", "dois"]', 2, ["one", "two"]) == ["um", "dois"]
    assert parse_segments("no json at all", 2, ["one", "two"]) == ["one", "two"]


# --------------------------------------------------------------------------- #
# Pacing, batching and retrying — the policy every engine is held to (ADR-0042)
# --------------------------------------------------------------------------- #
def test_a_quota_is_respected_by_waiting_not_by_failing(monkeypatch) -> None:
    """Three a minute means one every twenty seconds, and the caller waits."""
    from app.services.translation.limits import RateLimiter

    slept: list[float] = []
    monkeypatch.setattr("app.services.translation.limits.time.sleep", slept.append)

    limiter = RateLimiter(3)  # 3 rpm -> one every 20s
    assert limiter.interval == pytest.approx(20.0)
    assert limiter.acquire() and slept == []          # the first goes straight through
    assert limiter.acquire()
    assert slept and slept[0] == pytest.approx(20.0, abs=1)


def test_a_wait_that_is_too_long_returns_the_source(monkeypatch) -> None:
    """A meeting cannot wait five minutes for a heading."""
    from app.services.translation.limits import RateLimiter

    monkeypatch.setattr("app.services.translation.limits.time.sleep", lambda _: None)
    limiter = RateLimiter(1, max_wait=30)  # one a minute
    assert limiter.acquire()
    assert limiter.acquire() is False  # the next turn is 60s away


def test_a_local_engine_is_never_paced() -> None:
    from app.services.translation.limits import RateLimiter

    limiter = RateLimiter(0)
    assert limiter.interval == 0
    assert all(limiter.acquire() for _ in range(50))


def test_only_what_is_worth_retrying_is_retried(monkeypatch) -> None:
    from app.services.translation.limits import call_with_retry, is_retryable

    class Response:
        def __init__(self, status: int, retry_after: str | None = None):
            self.status_code = status
            self.headers = {"retry-after": retry_after} if retry_after else {}

    class Refused(Exception):
        def __init__(self, status: int, retry_after: str | None = None):
            super().__init__(str(status))
            self.response = Response(status, retry_after)

    assert is_retryable(Refused(429)) and is_retryable(Refused(503))
    assert not is_retryable(Refused(400)) and not is_retryable(Refused(401))

    waited: list[float] = []
    monkeypatch.setattr("app.services.translation.limits.time.sleep", waited.append)

    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise Refused(429, retry_after="7")
        return "done"

    assert call_with_retry(flaky, attempts=3) == "done"
    assert waited == [7.0, 7.0]  # the service asked for seven seconds, twice


def test_a_bad_request_is_not_retried(monkeypatch) -> None:
    from app.services.translation.limits import call_with_retry

    class Refused(Exception):
        response = type("R", (), {"status_code": 400, "headers": {}})()

    calls = {"count": 0}

    def rejected():
        calls["count"] += 1
        raise Refused()

    monkeypatch.setattr("app.services.translation.limits.time.sleep", lambda _: None)
    with pytest.raises(Refused):
        call_with_retry(rejected, attempts=3)
    assert calls["count"] == 1


def test_a_long_report_is_split_into_batches(client, iqc_real: Path, monkeypatch) -> None:
    """Fewer, larger requests: under a tight quota that is what decides."""
    provider = FakeProvider()
    provider.max_batch = 3
    register_provider(provider)
    monkeypatch.setattr(
        "app.services.translation.service.get_provider", lambda name=None: provider
    )

    version_id = _upload(client, iqc_real)["versionId"]
    lines = [f"linha numero {index}" for index in range(10)]
    client.put(
        f"/api/versions/{version_id}/report",
        json={
            "content": {
                "title": "Relatorio longo",
                "columns": [{"id": "c1", "name": "Observacao"}],
                "rows": [
                    {
                        "id": "r1",
                        "cells": {
                            "c1": [
                                {"id": f"b{index}", "type": "text", "text": line}
                                for index, line in enumerate(lines)
                            ]
                        },
                    }
                ],
            }
        },
    )

    body = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "ko"}
    ).json()

    assert body["stringCount"] == 12  # title + column + ten lines
    assert len(provider.seen) == 4  # 12 segments in batches of three
    assert all(len(batch) <= 3 for batch in provider.seen)
    # and the answers land against the right segments, batch boundaries included
    texts = [
        block["text"]
        for row in body["translated"]["rows"]
        for blocks in row["cells"].values()
        for block in blocks
    ]
    assert texts == [f"[ko] {line}" for line in lines]


def test_an_engine_that_keeps_failing_returns_the_source(
    client, iqc_real: Path, monkeypatch
) -> None:
    """A dead engine is a page in the original language, never a blank page."""

    class Broken:
        name = "broken"
        requests_per_minute = 0
        max_batch = 50

        def translate(self, request):
            raise RuntimeError("engine is down")

    monkeypatch.setattr("app.services.translation.limits.time.sleep", lambda _: None)
    provider = Broken()
    register_provider(provider)
    monkeypatch.setattr(
        "app.services.translation.service.get_provider", lambda name=None: provider
    )

    version_id = _with_report(client, iqc_real)
    body = client.post(
        f"/api/versions/{version_id}/translation", json={"targetLanguage": "ko"}
    ).json()
    assert body["translated"]["title"] == TITLE


def test_the_prompt_asks_for_spelling_to_be_fixed() -> None:
    """Translating a shop-floor note means tidying what was mistyped."""
    from app.services.translation.provider import SYSTEM_PROMPT

    prompt = SYSTEM_PROMPT.format(source="pt-BR", target="ko")
    assert "spelling" in prompt and "accents" in prompt
    assert "Never change, add, remove or reformat any number" in prompt
    assert "§A§" in prompt


def test_an_openai_compatible_engine_declares_its_quota() -> None:
    from app.services.translation.openai_provider import OpenAICompatibleProvider

    engine = OpenAICompatibleProvider("key", "gpt-4o-mini", requests_per_minute=3)
    assert engine.requests_per_minute == 3
    assert engine.model == "gpt-4o-mini"
    assert engine.max_batch >= 10  # a tight quota needs a generous batch
