# Architecture decision log

## ADR-0001 — SQLite, FastAPI, React; nothing else

**Decision.** One backend process, one file database, one frontend. No Redis, no
Celery, no Postgres, no microservices.

**Why.** The system runs locally for a weekly meeting; its load is one analyst.
Every extra moving part is something that can break on a Monday morning.

**Consequences.** Long operations (PPT/PDF) run in-request. If one becomes slow
enough to matter, the fix is a background thread, not a broker.

---

## ADR-0002 — Structure is inferred; coordinates are provenance

**Decision.** The parser discovers regions, header bands, label columns, periods
and hierarchy. Excel addresses (`B2:B40`, `Q40`) are stored for traceability and
never used as rules.

**Why.** The files change every week: weeks shift (`W32` → `W33` → `W34`),
months appear (`Sep`), columns are added, some departments have periods others
don't. Any rule shaped like `column == 15` or `week == "W32"` is a bug with a
delayed fuse.

**Consequences.** Detection is heuristic, so the model carries `warnings[]` and
enough metadata (`sourceRange`, `source`, `headerPath`, `labelRoles`) for a human
to see *why* something was read a given way. Datasets A/B/C pin the behaviour.

---

## ADR-0003 — Four layers: parser, interpreter, normalizer, repository

**Decision.** Reading the file, deciding what it means, building the model and
storing it are four modules with four contracts (`RawWorkbook` →
`TableInterpretation` → `NormalizedTable` → SQLite).

**Why.** Mixing them is what makes spreadsheet importers unmaintainable: a
change to "where the header is" ends up touching persistence. With the seams in
place, the interpreter can be rewritten without the parser noticing, and the
interpreter is testable on plain dictionaries.

---

## ADR-0004 — Period tokens are a vocabulary, not a format

**Decision.** `periods.py` recognises years, quarters, months and weeks in
English, Portuguese and Korean, in many spellings (`W32`, `WK32`, `Week 32`,
`Semana 32`, `32주`), plus series labels (`Target`, `Result`, `실적`). Bare
integers only become periods when their header row is already dominated by that
kind of token.

**Why.** Header wording varies between departments and between the people who
maintain the files; the meaning does not. And a value like `1961` must never be
read as a year just because it has four digits.

---

## ADR-0005 — Values are preserved; formatting is a hint

**Decision.** `#DIV/0!` stays an error, `NA` stays NA, `3000` stays `3000`. Each
cell carries `rawValue` (original), `number` (interpreted) and `displayValue`
(rendered). The Excel number format becomes a `display` hint.

**Why.** A quality report that silently turns a broken formula into `0` reports
a defect rate that never happened. And a value formatted at import time can no
longer be re-rendered per language.

---

## ADR-0006 — Departments are configuration, not branches

**Decision.** `app/domain/departments.py` holds each department's sections,
subgroups, metrics and protected terms. The parser consults a schema to raise
confidence but works without one.

**Why.** `if department == "IQC"` scattered through the parser would make the
fourth department a rewrite. Adding a section is a data change.

---

## ADR-0007 — Two kinds of translation, never mixed

**Decision.** Interface strings use i18next (`en`, `pt-BR`, `ko` JSON). User
content goes to an AI provider behind a `TranslationProvider` interface, with a
cache keyed by the content hash of the source document, protected vocabulary
(`PPM`, `SEC`, `TNP`, `TECPLAM`, `IQC`, `OQC`, `FIELD`, `ASR`, `CASR`…) and
protected *patterns* (week labels, numbers, product codes) masked before the
provider sees them.

**Why.** Menus must never cost an API call; report text must never be
re-translated when it hasn't changed; and week labels are dynamic, so they
cannot be a static list. The API key stays on the server.

---

## ADR-0008 — Rich text is a document tree, not a string

**Decision.** Issue Report cells store a TipTap/ProseMirror JSON document.

**Why.** A cell holds text *and* images *and* line breaks *and* bold runs. Only
a tree lets translation replace text nodes while leaving image nodes untouched,
and lets the exporters lay content out natively instead of screenshotting the UI.

---

## ADR-0009 — Imports are immutable; versions reference them

**Decision.** Each upload creates a new `department_data`. A version points at
imports through `version_imports` and copies only editorial content.

**Why.** "Never modify an old version silently" and "don't duplicate data" are
both satisfied: facts are shared, editorial state is snapshotted.

---

## ADR-0010 — Re-parsing is content-addressed

**Decision.** An upload whose sha256 already exists for the same department and
the same `PARSER_VERSION` returns the previous import (`reused: true`) instead
of parsing again. `force=true` overrides; a parser upgrade invalidates the reuse.

**Why.** The same workbook gets uploaded repeatedly during a meeting
preparation. Parsing is the expensive step, and its result is a pure function of
(file, parser version).

---

## ADR-0011 — Fixtures are generated, and labelled provisional

**Decision.** `tests/fixtures/build_fixtures.py` writes the `.xlsx` files the
tests parse: datasets A/B/C of the weekly matrix, a nested merged header, ASR +
CASR side by side, a transposed table and a long-format sheet.

**Why.** A committed binary hides the very structure under test. A generator is
reviewable and parameterised — "next week's file" is an argument, not a second
opaque file.

**Open point.** The real IQC / OQC / FIELD workbooks were not available in
Sprint 0. These fixtures reproduce the *described* structures and are documented
as provisional; validating against the real files is the first task of Sprint 1.

---

## ADR-0012 — `Target`/`Result` are a series, never a metric

**Decision (approved 2026-08-19).** A label that opposes a plan to an outcome —
`Target`, `Result`, `Plan`, `Forecast` — is recorded as `seriesType`, on the
column when it sits in the header and on the row when it sits in a label column.
It never becomes `metric`.

```
category = ASR      subcategory = MX      seriesType = Target      metric = null
category = SEC      subcategory = Total   metric = PPM             seriesType = null
```

A label column dominated by these tokens (at least two distinct ones) takes the
role `series`, and the hierarchy of that table reads
`category > subcategory > series`. When such a label appears inside a metric
column — an IQC group that adds a `Target` row next to `PPM`/`Def.`/`Insp.` —
that single row gets `seriesType` and no metric.

Aggregation labels (`Total`, `Average`, `YTD`, `Accumulated`) are deliberately
*not* in this set: they routinely name a subcategory (`SEC > Total > PPM`).

**Why.** `Target` says *how a number was produced*, not *what was measured*.
Folding it into the metric axis would make "PPM" and "Target" siblings, which
breaks target-vs-result charts and makes the metric list meaningless.

**Consequences.** `series` was renamed to `series_type` on columns and added to
rows, in the model, the schema, the API and the frontend contract; the migration
`61fa509752f2` renames the column instead of dropping it, so imports made before
the change keep their series.

---

## ADR-0013 — The NA vocabulary is a closed list

**Decision (approved 2026-08-19).** Spellings that mean "no data" —
`NA`, `N/A`, `n.a.`, `n/d`, `-`, `--`, `–`, `—`, `no data`, `sem dados`,
`해당없음`, … — all normalize to the single semantic value `na`. The original
string is always kept in `rawValue`.

Anything outside the list stays `text`. `TBD`, `?`, `pending` are **not**
promoted to NA.

**Why.** Six ways of writing "nothing to report" must aggregate as one thing,
but silently turning unknown words into "no data" would hide real content — and
a dash is a value in some columns, which is why the decision to include it was
the user's to make, not the parser's.

**Consequences.** `values.NA_TOKENS` is the single place to extend. A cell that
is NA never carries a number, so it can never be summed as zero.

---

## ADR-0014 — A metric can be identified by structure alone

**Decision (Sprint 1).** The parser identifies the headline metric of a block
without requiring the word that names it. Three structural rules do the work:
labels that repeat in every block are metrics, labels that appear once open a
sub-group, and the first row of a block carries the block's headline figure. The
*name* of that figure comes from the department schema
(`headline_metric = "PPM"`), never from a branch in the parser.

**Why.** The real IQC workbook never writes `PPM`: the value simply sits on the
row that carries the group's name (or no name at all). A rule like
`if cell == "PPM"` would read that file as having no PPM at all.

**Safety net.** The schema also declares how the headline relates to its
siblings (`PPM = Rej. Lot / Insp. Lot × 1_000_000`). Every block is checked
against every period; on the real file 87 of 87 values match, which turns the
inference into a verified fact. A mismatch raises
`headline_metric_mismatch` — it never rewrites a value.

**Reversibility.** Everything the parser inferred is marked: rows carry
`inferred: ["category", "metric"]`, tables carry `headline_metric_inferred` and
`implicit_group_label`. If the departments later start writing `PPM` in the
sheet, the label is simply read and the inference stops firing.

---

## ADR-0015 — Undated periods inherit the table's reporting year

**Decision (Sprint 1).** When a header states years explicitly (`'25`, `'26`)
and leaves quarters or months undated (`1Q`, `Aug`), the undated periods take
the **latest explicit year** and record `yearSource: "inferred"`. With no year
anywhere, the year stays `null` and the table keeps the `period_without_year`
warning.

**Why.** `1Q | 2Q | 3Q | Aug` next to `'25 | '26` can only be the current year;
without this, every chart would sort months under year zero and `Aug` of two
different reports would look like the same period. This closes the open
question raised in the Sprint 0 validation report.

**Consequences.** The inference is visible per period, and reversible: removing
it only means `sortKey` falls back to source order.

---

## ADR-0016 — OQC and FIELD schemas are marked provisional

**Decision (Sprint 1).** `DepartmentSchema` gained a `provisional` flag.
`IQC` is validated against the real workbook; `OQC` and `FIELD` carry only what
the written specification says and are flagged `provisional=True` with a note.

**Why.** The real OQC and FIELD files do not exist yet in this project. Nothing
about their structure may be treated as known, and no heuristic may be tuned
for them. When the files arrive they become fixtures, the schema is filled in
from the data, and the IQC path stays untouched.

---

## ADR-0017 — A quarter is the label `1Q`…`4Q`, not a number

**Decision.** `Period.quarter` holds the canonical label the reports use —
`"1Q"`, `"2Q"`, `"3Q"`, `"4Q"` — whatever spelling the file used (`Q3`, `3Q`,
`T3`, `3분기` all normalize to `"3Q"`). The ordinal remains available as
`quarter_number` / `quarterNumber` for arithmetic, ordering and `sortKey`
(`2026-Q3`, unchanged and deterministic).

Months carry their quarter as the same label: Jan/Feb/Mar → `1Q`,
Apr/May/Jun → `2Q`, Jul/Aug/Sep → `3Q`, Oct/Nov/Dec → `4Q`.

**Why.** The internal semantic model should speak the department's language. A
bare `3` is ambiguous the moment it leaves the parser — in an API payload, a
chart legend or an export it reads as "three", not "third quarter" — and it
invited exactly the confusion this ADR closes.

**Consequences.** The change touched the model, the vocabulary, the engine, the
wire contract and the frontend types. `sortKey` was deliberately left as
`YYYY-Qn` so ordering across generations of the file stays stable.

---

## ADR-0018 — The UI receives a render model, not a table to figure out

**Decision (Sprint 2).** A new layer, `app/services/render_model.py`, turns a
`NormalizedTable` into a grid the frontend draws as it comes:

* merged ranges become `rowSpan`/`colSpan` on a single cell, and the
  coordinates they cover are **absent** from the payload;
* every cell carries its own alignment, weight, fill and **the exact border
  sides the workbook draws** — nothing added, nothing removed;
* rows carry `depth` (indentation) and `isHeadline`, derived from the hierarchy
  the parser found;
* the period axis is whatever the model holds, in the file's order.

**Why.** Structure is interpretation, and interpretation belongs to the
backend. A React component that decides where a group starts would be a second
parser — one that drifts from the first.

**Consequences.** `IQCTable` and `IQCCell` contain no month, quarter or week
name, and no rule about SKD, CKD or PPM. The same components draw every
generation of the file. New endpoints:
`GET /api/imports/{id}/tables/{tid}/view` and `GET /api/versions/{id}/view`.

---

## ADR-0019 — The headline row shows its figure, never an invented label

**Decision (Sprint 2).** In the IQC tables the first row of each block carries
the block's derived figure (PPM) and no metric name of its own. The renderer
keeps that cell **empty**, exactly as the workbook has it. `PPM` stays in the
model as `meta.headlineMetric` and on the row as `metric`, for charts, exports
and search — it is never drawn as a row label.

The workbook draws only vertical rules around that cell (no top or bottom
border): the renderer reproduces that too, so no box is closed around an
intentional emptiness.

**Why.** Writing "PPM" into the table would add content the file does not have
and would push every block one row taller than the original.

---

## ADR-0020 — Inferred labels are shown, but never as the file's own content

**Decision (Sprint 2).** The first block of each IQC table has no name in the
workbook; the parser reads it as `Total`. The render model exposes it as
`inferredText` on an otherwise empty cell, and the UI draws it in a muted
italic with a tooltip explaining that it was read from the structure.

**Why.** Two failure modes had to be avoided: an unnamed block (unreadable) and
a fabricated label indistinguishable from real content (dishonest). Marking it
keeps both the meaning and the provenance.

**Reversibility.** `inferredText` is a separate field: a UI that wants strict
fidelity simply ignores it, and the day the workbook writes `Total` itself the
value arrives as ordinary `text`.
