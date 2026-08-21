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

---

## ADR-0021 — Analytics identify a row by meaning, not by position

**Decision (Sprint 3).** A series is addressed by a *selector* —
`table · category · subcategory · metric · seriesType` — and that selector is
also its identity across snapshots. Endpoints are model-oriented
(`/api/versions/{id}/analytics/series?table=TTL&metric=Rej.%20Lot`); there is no
`/iqc/aug` and no `/iqc/sec`.

**Why.** The same logical row sits in a different column every month. Comparing
version 1 with version 2 works because both are looked up by what they mean:
`Total · Rej. Lot` in `I4` of one file and `J4` of the other is one series with
two readings, and both cell addresses travel in the payload.

**Consequences.** A row that exists in one version and not in the other is
reported as `missing_a`/`missing_b`, never as zero, and the response warns
`rows_only_in_a` / `rows_only_in_b`.

---

## ADR-0022 — A delta is arithmetic; whether it is *good* needs configuration

> **Superseded by [ADR-0033](#adr-0033--the-system-reports-it-does-not-analyse).** The arithmetic below still holds exactly as written; the `severity` half of it does not — no delta carries a quality any more, and `DepartmentSchema.polarity` was removed.

**Decision (Sprint 3).**

* `delta = B − A` — always, when both values exist;
* `deltaPercent = (B − A) / A × 100` — **only** when `A` is a real, non-zero
  number; otherwise `null` with `status: "undefined_percent"`;
* a missing side gives `status: "missing_a"` / `"missing_b"` and no numbers;
* `direction` (`up`/`down`/`flat`) is a fact about the numbers;
* `severity` (`positive`/`negative`) requires the department to declare the
  metric's polarity (`DepartmentSchema.polarity`): for IQC, `PPM` and
  `Rej. Lot` are `lower_is_better` and `Insp. Lot` is `neutral`. Without a
  declaration the severity is `unknown` — never guessed from the metric's name.

**Why.** A percentage against a zero baseline is not a number, and "up is bad"
is domain knowledge, not arithmetic. Both had to be explicit rather than
implied by a colour.

---

## ADR-0023 — Ordering belongs to the period engine, on both sides

**Decision (Sprint 3).** The API returns the period axis already ordered —
`order=file` keeps the workbook's columns, `order=chronological` applies the
engine's rule (year, then granularity, then ordinal). The frontend renders the
order it receives and never re-sorts.

**Why.** A first attempt sorted `sortKey` as a string in the component, which
put `2026-M08` before `2026-Q1` — August ahead of the first quarter. `sortKey`
is a *key*, not a lexicographic ordering; only the engine knows how the
granularities relate. One owner, one rule.

---

## ADR-0024 — ExecutiveInsight is built now, used later

> **Superseded by [ADR-0033](#adr-0033--the-system-reports-it-does-not-analyse).** Insights are no longer built at all. The provenance the ADR argued for stayed: every figure still carries its cell, source range and version.

**Decision (Sprint 3).** Every comparison also returns `insights`: a ranked list
of statements carrying title, department, table, category, subcategory, metric,
period, reference period, both values, delta, percentage, direction, severity —
**and** the origin (cell, source range, version). Nothing generates slides yet.

**Why.** The executive presentation of a later sprint must be able to say "PPM
of Imported·SKD fell 100% from 3Q to Aug" *and* prove it from cell `I9` of
version 2. Deciding the shape now, while the data layer is fresh, is cheaper
than retrofitting provenance later.

---

## ADR-0025 — The reference period is resolved, and its basis is stated

**Decision (Sprint 4).** A KPI compares the selected period against:

1. the previous period **of the same kind** present in the file (August against
   July, `3Q` against `2Q`) — `comparisonBasis: "same_kind"`;
2. failing that, the column immediately before it on the chronological axis,
   whatever its granularity — `comparisonBasis: "preceding"`, surfaced in the
   UI as "vs 3Q (previous column)" and as a warning;
3. failing that, nothing — `"none"`, and the KPIs show no delta.

**Why.** The real IQC sheet holds exactly one month (`Aug`) beside years and
quarters, so a strict same-kind rule leaves the executive strip empty. Refusing
to compare would be useless; comparing silently against a quarter would be
dishonest. Naming the basis keeps both the reading and the caveat.

**Consequences.** Nothing else in the system compares periods implicitly; the
chart and the comparison table still take their two periods from the user.

---

## ADR-0026 — Generated sentences travel as template + params

> **Superseded by [ADR-0033](#adr-0033--the-system-reports-it-does-not-analyse).** There are no generated sentences to carry. The lesson about i18next lacking ICU `select` is kept here for whoever adds a template next.

**Decision (Sprint 4).** An insight carries `template` (an i18n key such as
`insights.metric_moved_up`), `params`, and an English `text` fallback. The UI
renders the sentence in the user's language; the exporters will use `text`.

The direction is part of the key (`_up` / `_down`) rather than a placeholder,
because plain i18next has no ICU `select` — a first attempt rendered
"PPM up} 188.2%" on screen, caught in the browser validation.

**Why.** Insights are *generated content*, so they must exist in the three
languages without an AI round-trip (ADR-0007 reserves the AI for user-authored
text). Sentences assembled in the backend keep the wording next to the data
that justifies it.

---

## ADR-0027 — Insight ranking is a documented formula

> **Superseded by [ADR-0033](#adr-0033--the-system-reports-it-does-not-analyse).** Nothing is ranked. The key figures appear in the order the workbook lists them.

**Decision (Sprint 4).**

```
score = min(|Δ%|, 300)
      + 50  when the movement is in the declared wrong direction
      + 25  when the value is on the wrong side of a target the file carries
```

Ties break by `|Δ|`, then by the sentence, so the order is stable across calls.

**Why.** "Relevance" must be inspectable. Each term is something the data
states: how much it moved, whether the department declared that direction bad
(ADR-0022), and whether a target in the workbook was breached. The cap stops a
percentage against a tiny baseline from drowning everything else.

**Consequences.** No hidden weighting, no learned score. Changing the ranking
means changing three numbers in `app/services/executive.py` and this ADR.

---

## ADR-0028 — The page owns version and period; panels are controlled

**Decision (Sprint 4).** The department page holds `versionId`, `period`,
`table` and `metric`, and passes them down. The Sprint 3 `AnalyticsPanel`,
which owned its own selectors, was split into `ChartsPanel` and
`ComparisonPanel`, both controlled.

**Why.** Sprint 4 requires one selection to drive tables, charts, KPIs and
insights together. Leaving the state inside a panel would have meant two
sources of truth on the same screen — the chart showing one period while the
KPI strip showed another.

**What was preserved.** The analytical services, endpoints and the chart,
comparison and selector components are unchanged: only where the state lives
moved.

---

## ADR-0029 — An issue has two halves, and only one is editable

**Decision (Sprint 5).** An issue report keeps its **editorial** half — title,
description, severity, status, images — separate from its **analytical** half —
period, value, previous value, delta, trend, target, origin cell and range.

The editorial half is what an edit may touch. The analytical half is
**recomputed from the snapshot** when the issue is created and never accepted
from the client: `POST /issues` takes a *selector* (table, category,
subcategory, metric, period) and the service reads the numbers itself. An edit
carrying `value` is refused by name, not silently ignored.

**Why.** An issue is an argument, and an argument that cites a number the file
does not hold is worse than no issue at all. Recomputing means every issue can
be traced to `sheet!cell` of a given version, months later.

**Consequences.** The description is stored as a rich document (ADR-0006) with
its content hash as `translationKey`, so the translation cache and the future
TipTap editor both work without another migration. Images live in `assets`
(bytes on disk) and are attached through `issue_media` as evidence, never as
analytical data. Status is only ever moved by a person — a metric improving
never resolves an issue.

---

## ADR-0030 — Both export formats read one context

**Decision (Sprint 5).** `app/services/export/context.py` assembles what the
page is showing — version, period, table, metric, KPIs, insights, issues with
their images, chart series, tables and an optional version comparison — and
both `pdf.py` and `powerpoint.py` render *that*. The export request carries the
page's own selection, so a different period produces a different file.

**Why.** A PDF that tells a different story from the screen is a bug the user
only discovers in the meeting. One context makes the two formats structurally
incapable of disagreeing.

**Consequences.** Nothing is screenshotted: the PDF is built with ReportLab
(text stays text, tables keep their spans, the chart is drawn natively) and the
deck with python-pptx (native chart with its data behind it, native tables,
editable text). The IQC tables keep merges, hierarchy and the empty headline
cell — only the *representation* is adapted to the medium, never the model.

---

## ADR-0031 — Trend classification, and its place in the ranking

> **Superseded by [ADR-0033](#adr-0033--the-system-reports-it-does-not-analyse).** `app/services/trends.py` was deleted; the system states nothing about a sequence of periods. The chart draws the sequence and the reader reads it.

**Decision (Sprint 5).** `app/services/trends.py` classifies a series as
`rising` / `falling` / `stable` / `volatile` / `insufficient_data`:

* only periods of the **same kind** are compared, and the **finest granularity
  with at least three readings** is the one analysed (three months beat four
  quarters, because the months are the current reading);
* a step is *flat* when it moves less than **2%** of the previous value — the
  threshold is a named constant (`FLAT_TOLERANCE`) so it can be argued with;
* fewer than three comparable readings is `insufficient_data`, never a guess;
* `quality` (`improving` / `worsening`) needs the metric's declared polarity;
  a `neutral` metric is never judged and an undeclared one stays `unknown`.

The ranking of ADR-0027 gains two terms: **+30** when the trend is worsening,
**+10** when it is consistent but its quality cannot be judged.

**Why.** "It went up this month" and "it has gone up for three months" are
different statements, and only the second justifies a meeting's attention on
its own. Both remain arithmetic — nothing here is generated or learned.

---

## ADR-0032 — The application translates itself; the browser must not

**Decision (Sprint 5).** `index.html` declares `<meta name="google"
content="notranslate">` and the body carries `class="notranslate"`.

**Why.** The product ships its own translations (en / pt-BR / ko) chosen by the
user. Chrome's auto-translation contradicted that choice *and* crashed React
during the browser validation: rewriting text nodes under React made the export
spinner throw `NotFoundError: insertBefore`. The two mechanisms cannot both own
the text.

---

## ADR-0033 — The system reports, it does not analyse

**Decision (revision of Sprint 5, on the user's directive).** CS Meeting is an
instrument, not an analyst. It uploads a workbook, interprets its structure,
renders its tables faithfully, charts the numbers it actually holds and exports
that. It does **not** produce insights, causes, verdicts, rankings or trend
classifications — not by heuristic and not by AI.

Concretely, and in both directions:

| Removed | Kept |
| --- | --- |
| `build_insights`, `insight_score`, the whole ranking formula | `delta`, `deltaPercent`, `direction`, `status` — arithmetic |
| `services/trends.py` and every trend classification | the chart, which *shows* the sequence |
| `severity` on a delta, a KPI and an issue's analytical half | `severity` on an issue's **editorial** half, set by a person |
| `DepartmentSchema.polarity` and `metric_polarity()` | `target` and `targetStatus` (`above`/`below`/`at`) — a comparison of two numbers the file holds |
| `targetBreached` — which side of a target is the bad one | the source cell and range that prove every number |
| insight-derived issue titles ("Local · PPM increase") | a neutral default title: the selection and the period |
| the insights section, its i18n block, and green/red delta colouring | the figures, the tables, the charts, the exports |

**AI is confined to translation.** A provider may translate a title, a
description or a report between en / pt-BR / ko. It may not change a number, a
label read from the workbook, or the meaning of factual content — the protected
terms and patterns of ADR-0008 already enforce that at the string level.

**Why.** The people in the meeting are the analysts. A system that announces
"PPM rose 188% — this is negative, ranked first" borrows their authority for a
conclusion it derived from a formula: it can be wrong about what matters, and
being wrong confidently in an executive review is worse than being silent.
Numbers, their difference and their provenance are verifiable; "this is bad" is
not. So the system states the first and never the second, and the words on the
page belong to whoever signed the issue report.

**Consequences.**

* `analytics.compute_delta` returns `direction` and no `severity`;
* `services/executive.py` builds **key figures** (`figures`, not `kpis`), in the
  order the workbook lists them;
* `GET /analytics/executive` returns `figures`; `/analytics/comparison` and
  `/analytics/versus/{id}` no longer return `insights`;
* `issues.analytical_severity` and `issues.trend` were dropped (migration
  `7696dbad9dc7`); an issue keeps `direction`, which is the sign of a
  subtraction;
* the PDF and the deck carry key figures, issues, chart and tables — no
  statement block, and no colour that means "good" or "bad";
* the parser, the period engine, the hierarchy inference, the render model and
  the export plumbing were **not** touched: interpreting a file faithfully was
  never the thing being questioned.

**Tests.** The suite asserts the absence as explicitly as it asserts the
presence: `test_executive.py` checks the exact key set of a figure and that
`build_insights` / `insight_score` do not exist, `test_analytics.py` that a
delta carries no verdict, `test_issues.py` that an issue payload carries none,
and `test_export.py` that neither exported file contains the words a generated
analysis would need.

---

## ADR-0034 — Prose in a workbook is content, not noise

> **Superseded by ADR-0036.** The report of a presentation is written by hand in the application. Prose found in a workbook is skipped again, and `report_blocks` was dropped.

**Decision (Sprint 6).** A region that holds no numbers and no periods is not
discarded any more: it becomes a **report block**, stored with the import and
shown on the page, in the exports and in the import preview.

* the rule is structural — the pipeline already knew which regions were not
  tabular; those now go to `app/excel/narrative.py` instead of to a warning;
* one paragraph per row of the block, joined left to right, **in the file's
  order**, each keeping the cell it came from;
* a line is a *heading* only when the file makes it bold, and a block's title
  is that line itself — never a phrase this system composes;
* a block whose lines contain no letter at all (an orphan number, a stray
  symbol) is still skipped: inventing prose would be as wrong as dropping it;
* `find_regions` grew a `min_cells` parameter so a title alone on its row can
  be read. A one-cell region may only ever become a report block, never a
  one-cell "table".

**Why.** The real IQC workbook carries a README sheet that explains how the
sheet is laid out. The product's whole promise is *faithful rendering of the
file*; silently dropping four sentences the author wrote is a fidelity bug, and
the user asked for the report to be shown, preserved, and neither summarised
nor rewritten.

**Consequences.** `report_blocks` (migration `5af291c4e799`) sits beside
`table_definitions` under the same immutable import. `GET /versions/{id}/view`
and the upload response both carry `reports`. The PDF gains a *Report* block
and the deck one slide per block, with the sheet and range printed under the
text. Nothing summarises: a report is shown as written.

---

## ADR-0035 — Translation is an overlay; the original is the record

**Decision (Sprint 6).** AI translation is wired end to end, and it may do
exactly one thing: say the same words in another language.

* **Provider.** `AnthropicProvider` implements the Sprint 0 seam. It is
  registered only when `CSM_TRANSLATION_PROVIDER=anthropic` *and*
  `CSM_ANTHROPIC_API_KEY` are set; otherwise the null provider stays in place
  and text comes back unchanged. The key never leaves the backend (ADR-0009).
* **What is collected.** `translation/content.py` picks strings by the *role of
  their cell*: table titles, header and label cells, report paragraphs, issue
  titles and descriptions. Value cells, period columns, formulas and cell
  addresses are never collected, so they cannot be sent, cannot be changed and
  cannot come back wrong.
* **What is masked.** Protected terms and data patterns (numbers, week labels,
  product codes) are replaced by placeholders before the request and restored
  after it (ADR-0008).
* **What is verified.** `preserves_data()` compares the data tokens and
  protected terms of the answer against the source. A mismatch — a rounded
  figure, a localised decimal separator, a dropped code — **discards the
  answer** and keeps the original, and the response says so
  (`rejected: true`).
* **How it reaches the page.** `POST /versions/{id}/translation` returns pairs
  of original and translated string. The snapshot is not touched; the client
  holds an overlay keyed by the original, so switching the language costs no
  request in either direction and the original is always one hover — or one
  *show original* — away.
* **Cache.** One row per string, keyed by content hash × language × provider,
  reusing the Sprint 0 `translations` table. The same label costs one
  round-trip for the whole product's lifetime.
* **Exports.** `translate` and `language` on the export request apply the same
  overlay to the same strings, so a translated page exports a translated file —
  with byte-identical numbers, which a test asserts.

**Why.** The directive is explicit: AI translates titles, texts and reports and
never alters numbers, values, formulas, periods, technical names or original
cells, and the original must always remain available. An overlay satisfies all
of it structurally rather than by good behaviour: the data path and the
language path never meet, and the only bridge between them is a lookup by
string that values are never part of.

**Consequences.** A page can be read in en / pt-BR / ko without the snapshot
ever differing. A provider that misbehaves cannot corrupt a figure — the worst
it can do is have its answer thrown away. And with no key configured the
feature degrades to "no translation", never to "wrong translation".

---

## ADR-0036 — The page is three containers, and the system only draws

**Decision (Sprint 7).** A department page shows exactly three things, in this
order:

1. **the charts** — one per table, side by side, in the workbook's order:
   vertical bars per category with a line over them for the leading group;
2. **the tables** — the same three, side by side, in the same order;
3. **the report** — written by hand, by the person presenting.

Everything else was removed: the key-figure strip, the issue reports, the
period and version comparisons, the period/table/metric selectors, the parser
warnings on the page, the provenance footers, and the prose read out of the
workbook (ADR-0034).

**What the system does.** It identifies the file's structure correctly, and it
draws. The user works the tables in Excel *before* uploading — the totals, the
PPM, the percentages are already calculated there — so the system recomputes
nothing. `app/services/charts.py` selects the metric (the department's headline
metric when the file has it, else the first metric present), the categories
(whatever the hierarchy found), the periods (the file's own columns) and the
line (the department's leading group). A file with a different shape draws a
different chart with no code change.

**What the system does not do.** It does not calculate, rank, compare, judge,
summarise or write. `compute_delta`, `compare_periods`, `compare_versions`,
`build_figures` and the issue machinery are gone, along with their endpoints.

**AI translates the report, and nothing else.** Every other word on the page —
headings, buttons, warnings — is interface text shipped in three languages, and
every label inside a table came from the workbook. Neither needs a provider,
and neither is ever sent to one. The report is the only text the system cannot
know in advance, so it is the only text a provider ever sees, under the rules
of ADR-0035 (masking, data-preservation check, original always available).

**Consequences.**

* new: `services/charts.py`, `services/reports.py`, `api/routes/reports.py`,
  `schemas/report.py`, tables `version_reports` and `report_media`
  (migration `902bbcb42eb9`);
* removed: `services/executive.py`, `services/issues.py`, `excel/narrative.py`,
  the comparison half of `services/analytics.py`, the `issues`, `issue_media`,
  `issue_report*`, `asset_usages` and `report_blocks` tables, and every
  endpoint that served them;
* the API is now nine reading endpoints and four writing ones;
* the exports follow the page: charts, tables, report — a PDF of three pages
  and a deck of five slides for the real IQC file.

**Why.** The product is an instrument for a weekly meeting. The numbers are
already right when they arrive; what the meeting needs is to see them, plainly,
and to read what the person responsible wrote about them. Everything the
system added around that was noise — and noise on an executive page is worse
than nothing, because it competes with the two things that matter.

---

## ADR-0037 — How the bars stand is declared per department

**Decision (Sprint 8).** `DepartmentSchema.chart_bars` says whether a
department's chart stacks its bars or groups them:

* **IQC — `stacked`.** The bars are the *leaf components* of each table: a
  category with sub-groups contributes its sub-groups (`SKD`, `CKD`), one
  without them contributes itself (`Local`). Stacked, they read as the whole,
  with the `Total` line drawn over them.
* **everything else — `grouped`,** the neutral default. OQC and FIELD are
  marked provisional and their real workbooks have not arrived, so nothing
  about their chart is assumed.

The *rule* is generic — "the parts, at the deepest level each one reaches" —
and only the *choice* is per department, because whether the parts add up is a
fact about the data, not about the code.

**Why.** Stacking numbers that do not sum to the whole draws a lie. For IQC the
user confirmed SKD + CKD + Local are the components of the total; for the other
two departments nobody can confirm it yet, and inventing it was explicitly
ruled out.

---

## ADR-0038 — Reading and configuring are two different screens

**Decision (Sprint 8).** The department page is for a meeting: it shows the
charts, the tables and the report, and carries no upload button, no edit
button and no export button. Everything that *changes* a department lives on
its own configuration screen, and every department has the same three tabs
with its own content:

* **Raw data** — upload the workbook, see what the parser understood, save the
  version;
* **Titles** — rename what appears above each chart and each table. Only the
  names; the numbers under them always come from the workbook;
* **Report** — the editor.

**The report is a table the author builds.** Columns are created, named,
reordered and deleted. Rows are added without limit. Each **cell** holds an
ordered list of **blocks** — text, image or shape — so a cell can be "text,
photo, text" or "photo, photo, text", in exactly the order the author placed
them, each with its own alignment; text blocks also carry bold, italic and a
size. The structure is stored as it was built and rendered the same way on the
page, in the PDF and as a native table in the deck.

**Images are stored as uploaded and drawn within bounds.** Nothing is
re-encoded, so a large photo keeps its quality; the ceiling is on the *file*
(15 MB, stated in the rejection message). On screen the author picks a width
from four presets (25 / 50 / 75 / 100% of the cell), and the system caps the
drawn height at 260 px. The report table uses a fixed layout with a 260 px
floor per column, so a big image can never push its neighbours away — the table
scrolls instead.

**Downloads live in their own screen.** `/reports` lists every saved report
across departments, newest first, with a filter and four downloads per line:
the report alone, the charts alone, the tables alone, and the full deck. A
meeting reads; it does not download.

**Translation follows the reader.** Choosing another language on the
presentation screen translates the report — its title, its column names and
its text — and nothing else, because everything else on the page is interface
text shipped in three languages or a label that came from the workbook
(ADR-0035, ADR-0036).

**Why.** Two audiences, two screens. The person presenting needs a page with
nothing on it but the content; the person preparing needs full control and
nowhere near a live meeting. Mixing them put edit affordances in front of an
executive room and buried the preparation work inside the presentation.

**Consequences.** New: `department_settings`, the block-shaped
`version_reports.content`, `/api/departments/{code}/settings`, `/api/reports`,
and `includeCharts` / `includeTables` / `includeReport` on the export request.
Removed: the import screen, the export buttons on the department page, and the
plain-text report of Sprint 7.

---

## ADR-0039 — Authored text is what AI translates, and it is exactly two things

**Decision (Sprint 9).** The system draws a line between text it *ships* and
text somebody *typed*, and only the second ever reaches a translation provider.

| Shipped — never sent | Typed — sent, for every department |
| --- | --- |
| every label of the interface (three bundles: en / pt-BR / ko) | the **report**: its title, its column names, its text blocks and its image captions |
| every label the workbook carries (`Imported`, `Rej. Lot`, `SKD`, `Aug`, `3Q`) | the **titles** given to the charts and tables in the configuration |
| every value, period, formula and cell address | |

One endpoint serves both: `POST /api/versions/{id}/translation` returns the
report in the target language *beside* the original, plus the two title maps
keyed exactly as they are stored — `{"TTL": "Entrada total"}` becomes
`{"TTL": "…"}`, the key untouched, because `TTL` is how the workbook names the
table and not something a person wrote.

Switching the language on the presentation screen calls it once and overlays
the answer. Nothing stored changes, so switching back costs no request.

**The same for IQC, OQC and FIELD.** The department is not a branch in the
code: it only selects which technical terms are masked out of the request
(`protected_terms`). A department with no report and no titles gets an answer
with nothing in it rather than an error.

**Why.** The product must be readable in three languages, and two kinds of
content make that impossible to solve with bundles alone — nobody knows what
the presenter will write in the report, or what they will call a chart. Those
are exactly the strings AI is useful for, and they are also the only ones where
being wrong is recoverable: the original is always beside the translation, the
numbers are never part of the request, and an answer that altered a data token
is discarded (ADR-0035).

**Consequences.** `/versions/{id}/report/translation` became
`/versions/{id}/translation`; the response gained `chartTitles`, `tableTitles`
and `stringCount`. The real provider needs `CSM_TRANSLATION_PROVIDER=anthropic`
and `CSM_ANTHROPIC_API_KEY` in the backend environment; without them the null
provider returns the source text, so the page degrades to "not translated" and
never to "translated wrongly".

---

## ADR-0040 — Three engines behind one seam, and a local one among them

**Decision (Sprint 9).** `CSM_TRANSLATION_PROVIDER` selects the engine, and all
three implement the same `TranslationProvider` contract:

| Engine | Where the text goes | Configuration |
| --- | --- | --- |
| `null` (default) | nowhere — the source comes back | none |
| `anthropic` | the Anthropic API | `CSM_ANTHROPIC_API_KEY`, `CSM_TRANSLATION_MODEL` |
| `ollama` | a model on this machine | `CSM_OLLAMA_URL`, `CSM_OLLAMA_MODEL` |

The **question is the same for all of them**: `SYSTEM_PROMPT` and
`parse_segments()` moved out of the Anthropic provider into the seam, so no
engine can quietly ask something different — or read an answer more
generously — than another. `configure_from_settings()` registers whichever is
asked for and falls back to `null` when it cannot be built.

**A local engine is not trusted more, only closer.** The masking, the
data-preservation check and the cache all apply exactly as before (ADR-0035).
Two things are specific to it: `temperature: 0`, because a translation is not a
place for sampling and the cache assumes determinism; and an engine that is not
running returns the source text with `meta.failed`, rather than raising — a
stopped daemon must not lose what somebody wrote.

**The answer parser learned two habits of small models**: wrapping the array in
an object (`{"translations": [...]}`) and prefixing it with a sentence. Both are
now read; anything else still falls back to the source.

**A date is one datum.** `12/08` used to be masked as two numbers with a slash
between them, so a model writing the date the way its own language does would
reorder the placeholders and have its whole answer discarded. Dates are now
masked whole (`12/08`, `2026-08-12`), which is both more correct and far less
brittle.

**Why.** The report is a quality document: it names suppliers, lot numbers and
findings. Sending it to a remote vendor is a decision an organisation should be
able to decline without losing the feature. With Ollama the text never leaves
the machine, and the rest of the system cannot tell the difference — which is
the point of having had a seam since Sprint 0.

---

## ADR-0041 — The presenter composes the chart; the workbook supplies it

**Decision (Sprint 9).** The configuration screen lets a department choose, per
chart, **which rows of its table are the stacked bars and which one is the
line**. `DepartmentSettings.chart_series` stores it:

```json
{"TTL": {"bars": ["TTL|Imported||PPM|", "TTL|Local||PPM|"],
         "line": "TTL|Total||PPM|"}}
```

The keys are the series identity of ADR-0021 — table, category, subcategory,
metric — so a choice survives a new import of the same workbook.

**What is offered is what the file has.** `/charts` returns `available`: every
row of that table, at every level and for every metric it carries, labelled by
its full path (`Imported · SKD · PPM`) so two `SKD` rows can be told apart. The
chooser never shows an option the workbook cannot supply.

**What is chosen is only *which*, never *what*.** The values, the periods and
the provenance are unchanged — a composition selects rows, it does not compute
anything. A chart that mixes metrics gets the metric appended to each label,
because `SKD` in lots and `SKD` in PPM would otherwise read alike.

**Defaults stay defaults.** With no choice stored, the automatic rule of
ADR-0037 applies — for IQC, the leaf components stacked under the `Total` line.
A stored choice whose rows the workbook no longer has falls back to that rule
rather than drawing an empty chart, and *Back to the default* clears it.

**Why.** The automatic composition is a good opening position, not a law. A
presenter who wants to show `Imported` against `Local` this week, and `SKD`
against `CKD` the next, was previously asking for a code change. The line
between "the system decides" and "the system obeys" belongs here: it decides
nothing about the numbers, and obeys entirely about which of them to draw.

---

## ADR-0042 — Pacing and batching belong to the service, not to the engine

**Decision (Sprint 9).** A provider knows how to ask one question. How often the
system may ask, how many segments go in one request, and what to do when the
answer is "not yet" are decided once, in `TranslationService`, and applied to
every engine.

A provider declares two things about itself:

| Attribute | Ollama (local) | Anthropic | OpenAI-compatible |
| --- | --- | --- | --- |
| `requests_per_minute` | `0` — no quota | `30` | `3` (a modest hosted plan) |
| `max_batch` | `40` | `60` | `60` |

`CSM_TRANSLATION_RPM` overrides the declaration, so a tightened — or a
generous — quota is a setting, never a code change.

**The policy.**

* **Batch generously.** Under three requests a minute, the batch size is what
  decides whether a report translates at all. A twelve-string report is one
  request, not twelve.
* **Wait your turn.** One `RateLimiter` per engine, shared process-wide, lets a
  request through every `60 / rpm` seconds. A steady interval, not a burst: a
  quota of three a minute is usually enforced as "not more often than every
  twenty seconds", and a burst is the shape most likely to be refused.
* **Give up rather than hang.** A caller that would wait more than 90 s returns
  the source text. A meeting cannot wait five minutes for a heading.
* **Retry what the service asked for.** `429`, `408` and `5xx` are retried,
  honouring `Retry-After` when present and backing off exponentially with
  jitter when it is not. `400` and `401` are not retried — asking again with
  the same bad request only spends quota.
* **Never lose the text.** An engine that is down, over quota or nonsense
  returns the *source*. A translation that did not happen is a page in the
  original language; an exception would be a page with nothing on it.

**Why.** The system will eventually run against a hosted multimodal model with
a quota measured in single digits. Discovering that limit through failures —
each one costing a request — is the expensive way. Declaring it and scheduling
around it costs nothing and works identically for the local model that has no
quota at all: `rpm = 0` disables the pacing entirely.

**Multimodality stays out.** `gpt-4o` can read an image; this seam sends text
and only text. A report's photographs are evidence someone attached, and
sending them anywhere is a decision with its own weight — not a quiet extension
of "translate these strings".

---

## ADR-0043 — Translating a shop-floor note means tidying it

**Decision (Sprint 9).** The prompt asks the engine to do two things to every
segment: translate the meaning the author intended, and **fix what was mistyped
along the way** — spelling, accents, capitalisation, spacing — so the result
reads as a careful person would have written it in the target language.

The boundary is stated in the prompt itself: *correct the language, never the
facts*. Everything ADR-0035 guards stays guarded — numbers, dates, codes and
protected terms are masked before the request and restored after it, and an
answer whose data tokens moved is discarded.

**Why.** The report is typed between a line stop and a meeting: `contençao
aplicda em 12/08`. Translating that faithfully into a misspelling in another
language serves nobody, and the engine is already reading the sentence. The
same pass that carries the meaning across can carry it across correctly.

**Consequences.** The original is untouched and always one language-switch
away — the correction lives in the translation, not in what the author wrote.
Switching back to the language the report was written in now restores the
author's own words from memory, without a request; previously it left the last
translation on screen under the wrong flag, which is the "third time it stops
translating" a user reported.
