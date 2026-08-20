# Sprint 0 — report

Goal of the sprint: **prove the system can turn a real weekly workbook into a
reliable internal model**, and put the architecture in place — not build the
application.

---

## 1. Architecture created

Four explicit layers with four contracts, plus the services around them:

```
RAW EXCEL
   │  app/excel/parser.py          (openpyxl, values + styles + merges)
   ▼  RawWorkbook
   │  app/excel/regions.py         (finds the table blocks)
   ▼  Rect[]  ("B1:Q38" — output, not input)
   │  app/excel/interpreter.py     (title, headers, labels, periods, hierarchy)
   ▼  TableInterpretation
   │  app/excel/normalizer.py      (typed cells: original + interpreted)
   ▼  NormalizedTable
   │  app/services/import_service.py
   ▼  SQLite
   │  app/services/interpretation.py
   ▼  Semantic view  →  UI / charts / export
```

Supporting pieces: `app/domain/departments.py` (department schemas as
configuration), `app/services/translation/` (provider seam + cache + document
rules), `app/services/storage.py` (upload validation), `app/tools/inspect_raw.py`
(CLI proof).

Full description in [architecture.md](architecture.md).

## 2. Folder structure

```
CS_Meeting/
├── backend/app/{core,db,domain,excel,schemas,services,tools,api}
├── backend/{alembic,tests,data}
├── frontend/src/{components,pages,i18n,lib,types}
└── docs/
```

## 3. SQLite schema

17 tables in three groups — facts (immutable imports), editorial (presentations,
versions, charts, issue reports) and support (translations, assets). Alembic
migration applied. Details and rules in [data-model.md](data-model.md).

Key decisions encoded: versions reference imports instead of copying them;
`sha256 + parser_version` makes re-parsing unnecessary; images stay on disk;
translations are cached by content hash; nothing is ever deleted automatically.

## 4. Normalized model

`NormalizedTable` — columns, rows and cells with **both readings**:

| Original | Interpreted |
| --- | --- |
| `Q2 = "W33"` | period `{kind: week, week: 33, sortKey: "0000-W33"}` |
| `B10 = "PPM"` | row `metric = "PPM"`, semantic `metric` |
| `Q40 = "3,000"` | `number = 3000.0`, `displayValue = "3,000"` |
| `B3:B11` merged | `mergedRange` on every covered cell, anchor flagged |

## 5. Parser strategy

Regions found by trimming and guillotine-cutting on empty rows/columns; merged
ranges resolved at read time so covered cells inherit the anchor's value; styles,
widths and heights captured as visual metadata that no logic reads.

## 6. Interpretation strategy

Title → header band → label columns → periods → hierarchy → axis, all inferred:

* a row is *data* when enough of its cells are real measurements — period tokens
  don't count, so a merged `2026` header is not mistaken for data;
* a row may only discount its numbers when it is *dominated* by period tokens,
  so a value like `1961` is never read as a year;
* periods are read as a vocabulary (`W32`, `WK32`, `Semana 32`, `32주`, `Ago`,
  `8월`, `CY26`), finest token wins, `Target`/`Result` become a series;
* hierarchy `category > subcategory > metric` from the label columns, with
  merged labels carried down;
* department schemas raise confidence but are never required.

## 7. Tests executed

```
cd backend && .venv/bin/python -m pytest -q
130 passed, 2 skipped
```

(the 2 skipped are the real-workbook tests, waiting for the files)

| File | Tests | Covers |
| --- | --- | --- |
| `test_parser_contract.py` | 17 | the 15 required acceptance tests (§16) |
| `test_periods.py` | 10 | period vocabulary in en / pt-BR / ko |
| `test_values.py` | 8 | NA, `#DIV/0!`, number parsing, formatting |
| `test_parser_structure.py` | 7 | nested headers, side-by-side, transposed, flat |
| `test_dynamic_periods.py` | 5 | datasets A → B → C |
| `test_interpretation.py` | 5 | the acceptance view (§25) + CLI |
| `test_import_api.py` | 9 | upload validation, reuse, endpoints |
| `test_persistence.py` | 3 | parse → persist → serialize round trip |
| `test_translation_architecture.py` | 9 | provider seam, cache, format preservation |
| `test_validation_report.py` | 8 | the real-file report and its ambiguity detection |
| `test_real_files.py` | 2 | skipped until the real workbooks arrive |

Frontend: `npm run build` passes (`tsc -b && vite build`).

## 8. Results

**The acceptance criterion is met.** Running

```bash
.venv/bin/python -m app.tools.inspect_raw iqc_dataset_c.xlsx --department IQC
```

prints:

```
┌─ IQC — Quality Weekly Report
│  sheet=IQC  source=B1:Q38  shape=matrix  periodAxis=columns
│  hierarchy: category > subcategory > metric
│  periods (13): 2025, 2026, Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, W33, W34
│  SEC / Total / PPM     2025=443.6, 2026=367.3, …, Sep=84.8, W33=372.2, W34=648.0
│  SEC / Total / Def.    …
│  SEC / Total / Insp.   2025=11,300, 2026=53,287, …
└─
```

The three datasets (A: `W31 W32`; B: `W33 W34`; C: `W33 W34` + `Sep` + a new
metric) are read by the same code path, with the same header/label/hierarchy
reading and no configuration change.

## 9. Limitations found

1. **The real workbooks were never seen.** Every fixture is synthetic and
   labelled as such (ADR-0011). The heuristics match the *described* structures;
   they have not met the real files' quirks (extra title rows, notes columns,
   footers, multi-sheet layouts, unusual merge patterns).
2. **Heuristic caps.** Header bands deeper than 6 rows and more than 4 label
   columns are read partially.
3. **Metric vocabulary fallback.** When no label column matches the metric
   vocabulary, the innermost label column is assumed to be the metric (a single
   unknown label column is treated as a category instead).
4. **Uncached formulas.** Workbooks whose formulas were never evaluated give
   empty value cells; flagged as `formula_without_cached_value`, never zeroed.
5. **Ignored content.** Embedded charts, images inside the workbook, pivot
   caches and conditional-format rules are not imported.
6. **Locale edge cases.** Numbers written as text parse for common en/pt-BR
   forms; exotic separators may not.
7. **Not built yet (by design).** Presentation/version CRUD, charts, the Issue
   Report editor, the AI provider, PDF/PPT exporters — contracts exist, code does
   not.

## 10. Decisions — closed on 2026-08-19

| # | Decision | Status |
| --- | --- | --- |
| 1 | `POST /api/uploads` is canonical; `/api/imports` stays as an alias and new code must not use it | ✅ implemented |
| 2 | Identical content hash + same parser version → reuse the existing import, never re-parse (`force=true` overrides) | ✅ implemented |
| 3 | `category → subcategory → metric` is the standard semantic hierarchy | ✅ implemented |
| 4 | `Target`/`Result` are a **series** (`seriesType`), never an ordinary metric — ADR-0012 | ✅ implemented |
| 5 | NA variants (`NA`, `N/A`, `n.a.`, `n/d`, `-`, `—`, `sem dados`, `해당없음`…) normalize to one semantic `na`, `rawValue` always preserved, unknown text never promoted — ADR-0013 | ✅ implemented |
| 6 | `PARSER_VERSION` is kept; a parser change never silently rewrites old imports | ✅ implemented |
| 7 | No definitive Sprint 1 work on synthetic fixtures alone; the real workbooks come first | ⏳ waiting for the files |

### What decision 4 changed

```
FIELD:  category = ASR    subcategory = MX      seriesType = Target   metric = null
        hierarchy = category > subcategory > series

IQC:    category = SEC    subcategory = Total   metric = PPM          seriesType = null
        a "Target" row inside a metric column gets seriesType and no metric
```

`series` was renamed to `series_type` on columns and added to rows across the
model, the schema, the API and the frontend contract. Migration `61fa509752f2`
**renames** the column instead of dropping it, so imports made before the change
keep their series.

## 10b. Validation tooling for the real workbooks (§7–§8)

Ready and tested, waiting for the files:

```bash
cd backend
# put the real files in tests/fixtures/real/ first
.venv/bin/python -m app.tools.validate_real
# or one file:
.venv/bin/python -m app.tools.validate_real path/to/OQC.xlsx --department OQC
```

For each workbook it writes `reports/<name>.md` and `reports/<name>.json` with
exactly the requested checklist: sheets found, tables detected, `sourceRange` of
each table, merged ranges, periods detected, hierarchy detected, metrics and
series detected, rows/columns count, parser warnings, and **possible
ambiguities** — plus a summarized JSON of the normalized model (columns,
periods, hierarchy and a sample of rows carrying original + interpreted values
with their Excel addresses).

Each workbook gets a verdict: `ok`, `check` (questions listed) or `blocking` (a
table could not be interpreted safely). Per the safety rule, a `blocking`
verdict stops the work: the ambiguity is documented and the decision comes back
to you — no hardcoded rule for `B2:B40`, `Q2:Q40`, `W32` or `W33` will be added
to make a file "work".

Ambiguity codes currently detected: `no_period_detected`, `no_header_band`,
`header_band_at_cap`, `label_columns_at_cap`, `no_hierarchy`,
`duplicate_period_labels`, `period_without_year`, `mixed_period_granularity`,
`metric_outside_vocabulary`, `formula_without_cached_value`,
`merge_crosses_header_boundary`, `mostly_empty`, `fragment_region`.

## 11. Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Real files differ from the described structure | high — the parser may mis-read the header band or hierarchy | send the real IQC/OQC/FIELD workbooks; they become fixtures on day 1 of Sprint 1 |
| A header row that is genuinely ambiguous (numbers that look like years) | medium — wrong period axis | dominance rule already in place; `warnings[]` surfaces the doubt instead of hiding it |
| Analysts changing the layout mid-quarter (new label column) | medium | hierarchy is positional-free; a new column shifts roles automatically, but a *new kind* of level needs a vocabulary entry |
| Charts bound to periods that disappear | low | selection by label + `sortKey`, missing period renders as a gap |
| Growth of `table_cells` | low | ~600 cells per table, thousands per import; SQLite handles it, and summaries avoid shipping cells to the UI |

## 12. Recommendations for Sprint 1

1. **Validate against the real files first** (half a day): drop the real IQC,
   OQC and FIELD workbooks into `backend/tests/fixtures/real/`, run
   `inspect_raw` on each, and fix whatever the heuristics get wrong. Everything
   else depends on this.
2. Then **presentations + versions**: the 8-presentation limit with archive /
   trash / restore, `DRAFT` vs `PUBLISHED`, and the presentation model endpoint
   that the UI will consume.
3. Then **table rendering in the UI**, driven by the normalized model
   (merged cells, hierarchy, number formatting per language).

Charts, Issue Report editor, translation provider and exporters follow, in that
order — each already has its contract in place.
