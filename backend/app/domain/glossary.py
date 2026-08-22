"""The vocabulary of the shop floor, in three languages.

A workbook label is not free text.  ``PPM``, ``SKD``, ``Rej. Lot`` and ``Total``
are a closed vocabulary that the same people use every week, and the Korean for
each of them is a decision somebody made once — not something to ask a model
each time and hope it answers the same way (ADR-0044).

So this is a table, not a translation: a term is either in it, and is rendered
the way the department agreed, or it is not, and is shown exactly as the
workbook writes it.  Never a guess.

The screen and the exports read the same table, so a deck handed out after the
meeting says what the screen said.
"""

from __future__ import annotations

import re
from typing import Iterable

#: term as the workbook writes it -> how it reads in each language.
#: Terms absent from a language are shown as they are: leaving `PPM` alone is
#: right, and inventing a word for it would not be.
GLOSSARY: dict[str, dict[str, str]] = {
    "ko": {
        # departments
        "IQC": "부품품질",
        "OQC": "출하품질",
        "FIELD": "시장품질",
        # hierarchy
        "Total": "누적",
        "Imported": "수입",
        "Local": "국내",
        # metrics
        "Rej. Lot": "불량 로트",
        "Insp. Lot": "검사 로트",
        # what a row is, where a department sets itself a goal (FIELD)
        "Target": "목표",
        "Result": "실적",
        # how firm a figure is — the qualifier row of the FIELD sheet
        "Simulation": "시뮬레이션",
        "Partial": "잠정",
        # periods
        "Jan": "1월",
        "Feb": "2월",
        "Mar": "3월",
        "Apr": "4월",
        "May": "5월",
        "Jun": "6월",
        "Jul": "7월",
        "Aug": "8월",
        "Sep": "9월",
        "Oct": "10월",
        "Nov": "11월",
        "Dec": "12월",
        "1Q": "1분기",
        "2Q": "2분기",
        "3Q": "3분기",
        "4Q": "4분기",
    },
    "pt-BR": {
        "Imported": "Importado",
        "Target": "Meta",
        "Result": "Resultado",
        "Simulation": "Simulação",
        "Partial": "Parcial",
        "Rej. Lot": "Lote rejeitado",
        "Insp. Lot": "Lote inspecionado",
        "Jan": "Jan",
        "Feb": "Fev",
        "Mar": "Mar",
        "Apr": "Abr",
        "May": "Mai",
        "Jun": "Jun",
        "Jul": "Jul",
        "Aug": "Ago",
        "Sep": "Set",
        "Oct": "Out",
        "Nov": "Nov",
        "Dec": "Dez",
        "1Q": "1º Tri",
        "2Q": "2º Tri",
        "3Q": "3º Tri",
        "4Q": "4º Tri",
    },
    "en": {},
}

#: terms deliberately left alone in every language: they are read the same way
#: on any factory floor, and a translation would only obscure them
UNIVERSAL = ("PPM", "SKD", "CKD", "TTL", "SEC", "TNP", "TECPLAM", "ASR", "CASR", "TSI", "MX")


def glossary_for(language: str | None) -> dict[str, str]:
    """The table for one language — empty when there is nothing to change."""
    return dict(GLOSSARY.get(language or "", {}))


def translate_term(text: str | None, language: str | None) -> str:
    """One label, rendered for a reader.  Unknown terms come back untouched."""
    if not text:
        return text or ""
    table = GLOSSARY.get(language or "", {})
    return table.get(text.strip(), text)


#: what may sit next to a term without being part of it.  ASCII on purpose:
#: Korean glues a particle straight onto a word, and a ``\w`` boundary would
#: refuse to see ``IQC의`` at all.
_EDGE = r"[0-9A-Za-z_]"


def render_terms(text: str, terms: Iterable[str], language: str | None) -> str:
    """Render decided terms inside a sentence a person wrote.

    A protected term travels through translation untouched — that is exactly
    what the masking is for — so when it comes back it is still the word the
    workbook uses, and putting the department's agreed Korean in its place is a
    substitution, never a guess.  ``IQC`` in a title the author typed therefore
    reads ``부품품질`` in Korean, the same as the column beside it (ADR-0044).

    Terms with no entry for the language are left exactly as they are.
    """
    table = GLOSSARY.get(language or "", {})
    if not text or not table:
        return text
    wanted = {term for term in terms if term and term in table}
    for term in sorted(wanted, key=len, reverse=True):
        pattern = re.compile(rf"(?<!{_EDGE})" + re.escape(term) + rf"(?!{_EDGE})")
        text = pattern.sub(table[term], text)
    return text
