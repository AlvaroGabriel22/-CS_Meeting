# Architecture decision log

## ADR-0001 — SQLite, FastAPI, React; nothing else

**Decision.** One backend process, one file database, one frontend. No Redis,
no Celery, no Postgres, no microservices.

**Why.** The system runs locally for a weekly meeting; its load is one analyst.
Every extra moving part is a thing that can be broken on a Monday morning.

**Consequences.** Long operations (PPT/PDF export) run in-request. If one ever
becomes slow enough to matter, the fix is a background thread, not a broker.

---

## ADR-0002 — Table structure is inferred, never configured by coordinates

**Decision.** The parser discovers regions, header bands, label columns and
periods. Excel addresses (`B2:B40`, `Q40`) are stored as provenance only.

**Why.** The files change every week: weeks shift (`W32` → `W33` → `W34`),
months appear (`Sep`, `Oct`), columns are added, some departments have periods
others don't. Any rule of the form `column == 15` or `week == "W32"` is a bug
with a delayed fuse.

**Consequences.** Detection is heuristic, so the model carries `warnings[]` and
enough metadata (`sourceRange`, `sourceAddress`, `headerPath`) for a human to
see *why* something was read the way it was. Tests pin the behaviour on
fixtures that deliberately shift week by week.

---

## ADR-0003 — Period tokens are a vocabulary, not a format

**Decision.** `periods.py` recognises years, quarters, months and weeks in
English, Portuguese and Korean, in many spellings (`W32`, `WK32`, `Week 32`,
`Semana 32`, `32주`), plus series labels (`Target`, `Result`, `실적`).

Bare integers only become periods when their header row is already dominated by
the same kind of token — so a `1961` sitting in a data row never becomes a year.

**Why.** Header wording varies between departments and between the people who
maintain the files; the meaning does not.

---

## ADR-0004 — Values are preserved, formatting is a hint

**Decision.** `#DIV/0!` stays an error, `NA` stays NA, `3000` stays `3000`.
The Excel number format is translated into a `display` hint carried to the UI
and the exporters.

**Why.** A quality report that silently turns a broken formula into `0` reports
a defect rate that never happened. And a value formatted at import time can no
longer be re-formatted per language.

---

## ADR-0005 — Imports are immutable; versions reference them

**Decision.** Each upload creates a new `department_data`. A
`presentation_version` points at imports through `version_imports` and only
*copies* editorial content (charts, issue reports).

**Why.** "Never modify an old version silently" and "don't duplicate data" are
both satisfied: the facts are shared, the editorial state is snapshotted.

---

## ADR-0006 — Rich text is a document tree, not a string

**Decision.** Issue Report cells store a TipTap/ProseMirror JSON document.

**Why.** A cell holds text *and* images *and* line breaks *and* bold runs. Only
a tree lets translation replace text nodes while leaving image nodes untouched,
and lets the PDF/PPT exporters lay the same content out natively instead of
screenshotting the UI.

---

## ADR-0007 — Two kinds of translation, never mixed

**Decision.** Interface strings use i18next (`en`, `pt-BR`, `ko` JSON files).
User content goes to an AI provider behind a `TranslationProvider` interface,
with a cache keyed by the content hash of the source document, and a
do-not-translate list (numbers, `PPM`, `W32`, `SEC`, `TNP`, `FIELD`, `IQC`,
`OQC`, product codes).

**Why.** Menus must never cost an API call, and report text must never be
re-translated when it hasn't changed. The API key stays on the server.

---

## ADR-0008 — Fixtures are generated, not committed as binaries

**Decision.** `tests/fixtures/build_fixtures.py` writes the `.xlsx` files that
the tests parse (matrix, next-week matrix, nested merged header, two tables in
one sheet, transposed, long format).

**Why.** A committed binary hides the very structure under test. A generator is
reviewable, parameterised (which is how "next week's file" is expressed) and
keeps the repository text-only.

**Open point.** These fixtures reproduce the *described* structure. The real
department files (IQC / OQC / FIELD raw data) have not been added to the
repository yet — once they are, they should be parsed in an additional test to
confirm the heuristics on the genuine layout.
