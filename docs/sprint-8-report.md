# Sprint 8 — report

**Scope: separate reading from configuring, and give the author a real report.**
The presentation screen loses every button; a configuration screen per
department gains the upload, the titles and a report builder; the IQC chart
stacks its components; and every saved report is listed for download.

---

## 1. The IQC chart stacks its parts

`DepartmentSchema.chart_bars` declares it (ADR-0037):

```
IQC — stacked                       everything else — grouped (default)
  ────────────────  Total (line)      the parts side by side; nothing is
   ▓▓  ▓▓  ▓▓  ▓▓   Local            assumed for OQC and FIELD until their
   ▒▒  ▒▒  ▒▒  ▒▒   CKD              real workbooks arrive
   ██  ██  ██  ██   SKD
   '25 '26 1Q  Aug
```

The rule is generic — *the parts, at the deepest level each one reaches*: a
category with sub-groups contributes them (`SKD`, `CKD`), one without them
contributes itself (`Local`). Only the choice to stack is per department,
because whether the parts add up is a fact about the data.

## 2. Two screens

**`/department/:code` — the presentation.** Charts, tables, report. No upload
button, no edit button, no export button, no captions. The one automatic thing
that happens is translation: changing the interface language translates the
report.

**`/department/:code/config` — the configuration.** Three tabs, the same for
every department, each with its own content:

| Tab | What it does |
| --- | --- |
| Raw data | choose the workbook, see what the parser understood, save the version |
| Titles | rename each chart and each table — only the names, never the numbers |
| Report | the builder |

## 3. The report builder

The report is a table the author builds (ADR-0038):

* **columns** — create, rename, reorder, delete;
* **rows** — as many as wanted, reorderable, deletable;
* **cells** — an *ordered list of blocks*: `text`, `image` or `shape`. A cell
  can be text → photo → text, or photo → photo → text, in exactly the order
  they were placed. Every block has its own alignment; text blocks also carry
  bold, italic and a size (small / normal / large / heading); shapes are
  rectangle, circle, line, arrow or divider with a colour and a size;
* **images** — the width is picked from four presets (25 / 50 / 75 / 100% of
  the cell) rather than dragged, the drawn height is capped at 260 px, and the
  table keeps a fixed layout with a 260 px floor per column, so a large photo
  never pushes the other columns away. The file itself is stored byte for byte
  — no re-encoding, no quality loss — under a 15 MB ceiling whose rejection
  message names the limit.

Images are uploaded first (`POST …/report/media` → `assetId`) and placed
afterwards, so the same photo can appear twice without being stored twice.

Validation is a filter, not a lecture: a block the system cannot draw is
dropped, a cell of a deleted column goes with it, and a report beyond 12
columns or 200 rows is refused by name.

## 4. The reports library

`/reports` lists every saved report across departments, newest first, with a
department filter and four downloads per line: **the report alone**, **the
charts alone**, **the tables alone**, and **the full deck**. Kept off the
presentation screen on purpose — a meeting reads, it does not download.

## 5. Exports

The export request takes `includeCharts`, `includeTables` and `includeReport`.
The report keeps its shape in both formats: a real table in the PDF with each
cell's blocks stacked in order, and a **native PowerPoint table** whose cells
hold the text blocks as paragraphs with their alignment.

```
report only    2 pages   title + table + the placed image
charts only    1 page    three charts side by side
tables only    2 pages   the three workbook tables
full deck      5 slides  3 stacked charts, 3 workbook tables, 1 report table
```

## 6. Tests — **301 passing**

| File | Tests | Covers |
| --- | --- | --- |
| `test_charts_and_report.py` | 27 | stacking (and that OQC/FIELD are not assumed), chart provenance, the builder's columns/rows/blocks, mixed cells, validation, the library, settings, the image limit and byte-for-byte storage |
| `test_export.py` | 14 | the report as a table in both formats, per-part downloads, translated export keeps every number |
| `test_translation_api.py` | 13 | title, column names and text translated; nothing else sent; cache; rejection; original preserved |
| `test_fidelity.py` | 13 | upload of the real file, value and structure preservation, regression |
| Sprints 0–2 + analytics | 234 | no regressions |

One test worth naming: `test_a_cell_can_mix_text_images_and_shapes_in_any_order`
asserts the block order survives the round trip, because that order *is* the
feature.

`conftest.py` gained an autouse fixture that clears `department_settings`
between tests — the titles are the one piece of shared state in the schema, and
one test's rename was leaking into another's assertions.

## 7. Browser validation

Real workbook, version 4, driven through the UI:

| Check | Result |
| --- | --- |
| presentation screen | ✅ charts → tables → report, no buttons of any kind |
| stacked chart | ✅ SKD · CKD · Local stacked, Total as a line, periods from the file |
| configuration | ✅ three tabs; upload, titles and report each work |
| report builder | ✅ two columns named, one row, first cell = **centered bold text → image with caption → text** |
| saved report | ✅ read back block for block, in order |
| presentation renders it | ✅ same table, same order, image included |
| reports library | ✅ one line, four downloads, filter by department |
| downloads | ✅ report / charts / tables / deck each carry only their part |
| language switch | ✅ interface in Korean, report unchanged (no provider configured), no console errors |
| settings screen | ✅ one card per department, one link each — the unclickable list and the duplicate presentation link are gone |

## 8. Limitations

1. **No Anthropic key configured**, so switching language leaves the report in
   the original. `CSM_TRANSLATION_PROVIDER=anthropic` + `CSM_ANTHROPIC_API_KEY`
   in `backend/.env` activates it with no code change.
2. **The stacked y-axis is driven by the largest column.** In the real file
   `SKD` reaches 105,263 PPM in 2Q, so the stack tops out near 120,000 and the
   other periods look small. That is the data; a log scale or a per-chart
   maximum is possible if wanted.
3. **Text blocks are plain text** with alignment, weight, italic and size —
   there is no rich inline formatting inside a single block yet.
4. **Image width is four presets, not free-form.** Precise percentages would
   need a drag handle; the presets cover the cases and cannot produce a broken
   layout.
5. **Shapes are decorative**: they carry a colour and a size, but not a caption
   or a link.
6. **A report belongs to one version.** Changing the version in the
   configuration switches which report is edited; there is no copy-forward.
7. **Table titles are keyed by the workbook's table name**, so a workbook that
   renames `TTL` starts with the default name again.
8. **OQC and FIELD** remain untouched, waiting for their real workbooks.

## 9. Architectural decisions

| ADR | Decision |
| --- | --- |
| **0037** | How the bars stand is declared per department; IQC stacks its leaf components, nothing else is assumed. |
| **0038** | Reading and configuring are two different screens; the report is a table of ordered blocks; downloads live in their own library. |

## 10. Files

**New (backend):** `schemas/report.py` (rewritten), `services/reports.py`
(rewritten as a block document), `DepartmentSettings` model, migrations
`902bbcb42eb9` and `30154abbfc42`.

**New (frontend):** `pages/DepartmentConfig.tsx`, `pages/Reports.tsx`,
`components/report/ReportBuilder.tsx`, `components/report/ReportView.tsx`.

**Removed (frontend):** `pages/Import.tsx`, `components/report/ReportEditor.tsx`,
`components/executive/ExportButtons.tsx`.

**Modified:** `domain/departments.py`, `services/charts.py`,
`api/routes/reports.py`, `api/routes/exports.py`,
`services/export/{context,pdf,powerpoint}.py`, `db/models.py`,
`pages/Department.tsx`, `components/charts/DepartmentCharts.tsx`,
`components/table/IQCTable.tsx`, `components/layout/Topbar.tsx`, `App.tsx`,
`lib/api.ts`, `types/api.ts`, i18n `en` / `pt-BR` / `ko`, and `docs/*`.

---

## 11. Follow-up — AI translation of authored text (ADR-0039)

Switching the language now translates **everything a person typed** about a
snapshot, for all three departments:

* the **report** — title, column names, text blocks, image captions;
* the **titles** given to the charts and the tables in the configuration.

`/versions/{id}/report/translation` became `/versions/{id}/translation` and its
answer carries the report both ways plus the two title maps, keyed by the
workbook's own table name (`TTL`), which is never translated.

Everything else is untouched by design: the interface ships in three bundles,
and the labels inside the tables (`Imported`, `Rej. Lot`, `SKD`, `Aug`, `3Q`)
belong to the workbook and never leave the backend.

**Tests — 306 passing** (was 301). The five new ones cover the typed titles,
the untranslated key, a version with no report at all, and the same behaviour
parametrised over IQC / OQC / FIELD.

**Validated in the browser** with a stub provider (no Anthropic key on this
machine): interface in Korean, `[ko] Entrada total` / `[ko] Secao` /
`[ko] Terceiros` above the charts, `[ko] Resumo do mes` above the table, and the
whole report table translated — while every number, period and workbook label
stayed exactly as the file has it.

To use the real provider, set in `backend/.env`:

```bash
CSM_TRANSLATION_PROVIDER=anthropic
CSM_ANTHROPIC_API_KEY=sk-ant-…
```

---

## 12. Follow-up — a local engine (ADR-0040)

Translation now runs on **a model installed on this machine**, through Ollama,
so the report text never leaves it. The seam did not change: the same prompt,
the same masking, the same data-preservation check, the same cache.

```
CSM_TRANSLATION_PROVIDER=ollama
CSM_OLLAMA_URL=http://127.0.0.1:11434
CSM_OLLAMA_MODEL=gemma4:e2b
```

`SYSTEM_PROMPT` and the answer parser moved from the Anthropic provider into
the seam, so no engine can ask a different question or read an answer more
generously than another. The parser learned two habits of small models — the
array wrapped in an object, and a sentence before it — and still falls back to
the source text for anything else. An engine that is not running returns the
source with `meta.failed`: a stopped daemon must not lose what somebody wrote.

**Measured on this machine** (CPU only, 16 cores, `gemma4:e2b`): the real IQC
report — 14 strings — translated to Korean in **13 s** cold, and instantly on
the second switch, from the cache. `gemma4:12b` is also installed but exceeded
two minutes for the same call, so the smaller model is the default.

**Three real defects found by the run**, all in the guard, none in the engine:

1. `12/08` was masked as *two* numbers with a slash between them. Dates now
   mask whole (`12/08`, `2026-08-12`).
2. The token boundary was `(?!\w)`, and Python counts Hangul as word
   characters. Korean writes `12/08에` — particle glued to the number — so the
   guard could not see the date in the answer and rejected a translation that
   was in fact perfect. The boundary is now ASCII (`[0-9A-Za-z_]`).
3. The check demanded the *same* tokens on both sides, but Korean writes August
   as `8월`: a correct translation adds a digit the source never had, and every
   such line was refused. It is now a subset check — every figure of the source
   must survive, an added one is orthography.

None of the three was visible from reading the code. The safety net failed
*loudly*, which is the whole point of having one, and pointed straight at
itself.

**The suite gained isolation from the developer's environment.** With a real
`.env` present, `get_settings()` picked up `ollama` and two tests that assert
the no-engine behaviour started failing. `conftest.py` now forces
`CSM_TRANSLATION_PROVIDER=null`, so what the suite proves does not depend on
who runs it.

**Tests — 313 passing** (was 306): the configured engine is the one registered,
the local engine asks the shared question with `temperature: 0`, a stopped
engine keeps the text, the object-wrapped answer is read, a date is masked as
one datum, the guard reads a language that writes without spaces, and a
language that spells a word with a digit is not refused.

---

## 13. Follow-up — the presenter composes the chart (ADR-0041)

The configuration screen gained, per chart, a list of **every row the table
carries** — each category, sub-group and metric, labelled by its full path —
with checkboxes for the stacked bars and a dropdown for the line.

```
TTL                                  bars: ☐ Total · PPM
                                           ☑ Imported · PPM
Entrada total                              ☑ Local · PPM
                                           ☐ Imported · SKD · PPM   …
                                     line: Total · PPM
```

* the choice is stored per department, keyed by the table's own name, and the
  series keys are the identity of ADR-0021 — a new import of the same workbook
  keeps it;
* the stack follows the workbook's row order, not the order of clicking;
* a chart that mixes metrics gets the metric appended to each label;
* no choice, or a choice whose rows the file no longer has, falls back to the
  automatic composition — a stale setting never empties a chart. *Back to the
  default* clears it;
* the exports read the same composition, so the PDF and the deck show what the
  screen shows.

**Tests — 319 passing** (was 313): every row is offered, the chosen rows are
the ones plotted, a composition may mix metrics and says which is which, the
plotted values are still the workbook's, a stale choice falls back, and only
the table that was configured changes.

**One defect found while validating.** The configuration screen went blank
after the change: the running backend still predated `chartSeries`, the panel
read a field that was `undefined`, and React unmounted the tree. Restarting the
API fixed it, but the page should not white-screen over a missing field — the
panel now defaults every settings map to `{}`.

---

## 14. Follow-up — spelling, and an architecture that fits a 3 RPM quota

**The bug behind "the third time it stops translating".** Switching *back* to
the language the report was written in returned early and left the previous
translation on screen under the wrong flag. The page now keeps the author's own
words in memory and restores them on that switch — no request, and never a
Korean report labelled Portuguese. Verified with five consecutive switches:
`pt-BR → ko → pt-BR → ko → en`, each one correct.

**Translation now corrects spelling** (ADR-0043). The prompt asks for two
things per segment: the meaning the author intended, and a tidy-up of what was
mistyped along the way — spelling, accents, capitalisation, spacing. *Correct
the language, never the facts.* Measured on a note typed the way one is typed
between a line stop and a meeting:

```
relatorio semanal de qualdade                     → Weekly quality report
ocorencia                                          → occurrence
fornecedor local acima do limte em Aug, 35.714 PPM → local supplier above the
                                                     limit in Aug, 35.714 PPM
contençao aplicda em 12/08; auditoria na proxima   → containment applied in
  semana                                             12/08; audit next week
```

Zero rejections: `35.714` and `12/08` came back untouched, because they were
masked out of the request in the first place.

**Pacing and batching moved into the service** (ADR-0042), against the day this
runs on a hosted model with three requests a minute:

* a provider declares `requests_per_minute` and `max_batch`; `CSM_TRANSLATION_RPM`
  overrides it without a code change;
* one `RateLimiter` per engine, shared process-wide, releases a request every
  `60 / rpm` seconds — a steady interval, not a burst;
* a caller that would wait more than 90 s returns the source text;
* `429`, `408` and `5xx` are retried, honouring `Retry-After`, backing off with
  jitter otherwise; `400` and `401` are not — asking again only spends quota;
* an engine that is down, over quota or nonsense returns the *source*: a
  translation that did not happen is a page in the original language.

A third engine came with it: `OpenAICompatibleProvider`, for `gpt-4o`, a
gateway or a self-hosted server — the same prompt and the same parser as the
other two. Its declared quota is 3 RPM, which is the case the architecture was
built for. Multimodality is deliberately *not* wired: this seam sends text, and
a report's photographs are evidence someone attached.

**Tests — 328 passing** (was 319). The nine new ones cover the quota being
respected by waiting, a wait that is too long returning the source, a local
engine never being paced, only retryable failures being retried, `Retry-After`
being honoured, a long report split into batches with the answers landing
against the right segments, a dead engine keeping the text, the prompt asking
for spelling, and an engine declaring its quota.
