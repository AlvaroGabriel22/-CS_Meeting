# Sprint 6 — report

**Scope: the product as defined.** Upload a real workbook, interpret it,
render its tables, charts and *report* faithfully, translate the words with AI
without touching a single number, and export what the screen shows. OQC and
FIELD were not started; no analytical module was added.

---

## 1. Implementation summary

```
RAW EXCEL ─ parser ─ regions ─┬─ interpreter ─ normalizer ─▶ NormalizedTable
                              │                                    │
                              └─ narrative ─────────▶ ReportBlock   │
                                                          │         │
   translation (overlay, cache-first) ◀── content.collect ─┴─────────┤
                                                                    │
                        render model ─ charts ─ figures ─ exports ◀──┘
```

Two new capabilities, one new rule:

| Priority | What changed |
| --- | --- |
| **1 — upload & fidelity** | verified end to end against the file itself, and the prose the parser used to drop is now kept |
| **2 — charts** | unchanged and now pinned by tests: every point proves its cell, the same snapshot always draws the same chart |
| **3 — report** | `app/excel/narrative.py`, `report_blocks`, the API, a page section, the import preview and both exports |
| **4 — translation** | real provider, string cache, collection rules, a data-preservation check, an endpoint, and a UI overlay |
| **5 — export** | PDF and PPT carry the report and follow the page's language, with identical numbers either way |
| **6 — issue report** | touched only where the flow needed it (raise-from-figure text, translation of title and description) |

## 2. Priority 1 — upload and faithful rendering

Nothing about the pipeline was rewritten. What Sprint 6 added is **proof** plus
the missing content:

* `tests/test_fidelity.py` reads the real workbook twice — once with openpyxl
  directly, once through upload → parse → snapshot → API → render model → chart
  — and compares. Every number served matches the file by cell address, and
  **no number of the data sheet is dropped**;
* merges arrive as spans with the covered coordinates absent, the hierarchy
  (`category › subcategory › metric`) is preserved, the headline row keeps the
  empty cell the file has, and the period axis is the file's own columns;
* `#DIV/0!` stays an error, never a zero;
* re-uploading the same file reuses one interpretation, and an older snapshot
  keeps showing what it froze.

**The one fidelity defect found and fixed:** the real workbook's README sheet —
four sentences and a bold title explaining how the sheet is laid out — was
parsed, found non-tabular and **discarded with a warning**. That is content the
file has. It is now kept (§4).

## 3. Priority 2 — charts

Unchanged by design: the chart already read the same normalized model as the
tables. Sprint 6 pinned the behaviour:

* every plotted point carries the cell it came from, and its value equals the
  workbook's value at that address;
* a missing reading is a gap (`value: null` with its `valueType`), never a zero;
* the same snapshot and the same parameters always produce a byte-identical
  payload — no sampling, no smoothing, no randomness.

Nothing is generated around the chart: no insight, no cause, no recommendation
(ADR-0033 still holds).

## 4. Priority 3 — the report the file carries

`app/excel/narrative.py` (ADR-0034). The rule is structural, not a keyword list
and not a sheet name:

| Region | Becomes |
| --- | --- |
| has numbers or periods | a table, as before |
| has words, no numbers, no periods | a **report block** |
| has neither words nor numbers | skipped, with a warning |

* one paragraph per row, cells joined left to right, merges counted once, **in
  the file's order**;
* every paragraph keeps its cell (`A3`) and row; every block keeps its range;
* `kind: "heading"` only when the file makes the line bold; a block's title is
  that line itself — nothing composed;
* `find_regions` gained `min_cells`, so a title alone on its row survives; a
  one-cell region may only become a report block, never a one-cell table.

On the real workbook this recovers:

```
README!A1:A1   heading    IQC — estrutura fiel às duas fotografias
README!A3:A6   paragraph  As duas fotos são partes da mesma folha…
                          Estrutura reproduzida: TTL em B2:I17, SEC em K2:R17…
                          As células de categoria Imported e Local foram…
                          Períodos: '25, '26, 1Q, 2Q, 3Q e Aug.
```

A test asserts the served lines are **identical, in the same order**, to what
openpyxl reads from the sheet. No summary, no rewrite, no narrative.

## 5. Priority 4 — translation

Wired end to end (ADR-0035), with the guarantee expressed structurally rather
than by good behaviour.

**Provider.** `AnthropicProvider` implements the Sprint 0 seam and is
registered only when `CSM_TRANSLATION_PROVIDER=anthropic` **and**
`CSM_ANTHROPIC_API_KEY` are set. Without a key the null provider stays and text
comes back unchanged — the feature degrades to *no translation*, never to
*wrong translation*. The key never reaches the browser. A malformed answer
keeps the source text.

**What is sent.** `translation/content.py` collects strings by the role of
their cell:

| Sent | Never sent |
| --- | --- |
| table titles | value cells |
| header and label cells whose column carries no period | period columns (`Aug`, `3Q`, `'25`) |
| report paragraphs and their headings | formulas, cell addresses, numbers |
| issue titles and descriptions | anything the department declares protected (masked out even inside a sentence) |

**What comes back is checked.** `preserves_data()` compares the data tokens
(numbers, week labels, product codes) and protected terms of the answer against
the source. A rounded figure, a localised decimal separator or a dropped code
**discards the answer**; the original is kept and the response says
`rejected: true`.

**How it reaches the page.** `POST /versions/{id}/translation` returns pairs of
original and translated string. The snapshot is untouched; the client holds an
overlay keyed by the original. Switching off costs no request, every translated
string carries its original in `title`, and the report card has its own *show
original* switch.

**Cache.** One row per string × language × provider. The second call for the
same snapshot makes **zero** provider round-trips — asserted by a test.

## 6. Priority 5 — exports

* the PDF gained a **Report** block (each line, then `README!A3:A6`);
* the deck gained one **report slide per block**, as editable text, line for
  line;
* the export request accepts `language` and `translate`, so a page being read
  translated exports translated;
* a test asserts that the translated PDF's numbers are **identical** to the
  untranslated one's, extracted with a regex over the whole document.

Nothing artificial is composed: the file carries the figures, the workbook's
report, the issues a person wrote, the chart and the tables.

## 7. Priority 6 — issue reports

Touched only as the main flow required: issue title and description travel
through the same translation layer, and the raise-from-figure list (Sprint 5's
revision) now names the figure and its value. The rich TipTap editor was **not**
built — it stays a candidate for a later sprint, as instructed.

## 8. Tests — **337 passing** (was 293)

| File | Tests | Covers |
| --- | --- | --- |
| `test_fidelity.py` | 13 | upload of the real file, value preservation, structure preservation, deterministic charts, regression |
| `test_report_blocks.py` | 13 | extraction, verbatim text, provenance, headings, persistence, API, "no report invented" |
| `test_translation_api.py` | 15 | status, no-provider path, what is sent, snapshot untouched, both sides present, cache, rejection, unsupported language, issue text, unit rules |
| `test_export.py` | 16 (+4) | report in PDF and PPT, translated export keeps every number |
| Sprints 0–5 | 280 | no regressions |

Three of the new tests are worth naming:

* `test_every_line_of_the_file_is_present_and_unchanged` — the report, compared
  to openpyxl's own reading;
* `test_no_number_period_or_address_is_ever_sent` — inspects what the provider
  actually received;
* `test_a_translated_export_keeps_every_number` — the numbers of both PDFs.

## 9. Browser validation

Real workbook (`RawdataIQC.xlsx`), uploaded through the UI, saved as **v4**.
Translation was exercised with a **stub provider** that prefixes each segment
with the target language: no Anthropic key is configured on this machine, and a
stub makes the overlay visible without pretending to be a real translation.

| # | Check | Result |
| --- | --- | --- |
| 1 | file imported | ✅ preview: TTL · SEC · TNP, periods `'25 '26 1Q 2Q 3Q Aug`, **Report found in the file** with `README!A1:A1` and `README!A3:A6` |
| 2 | table rendered | ✅ merges, hierarchy, borders, empty headline cells, `IQC!B2:I17` |
| 3 | chart | ✅ six periods from the file, five series, tooltip values matching the table |
| 4 | report | ✅ own section, bold title, four paragraphs, ranges shown |
| 5 | translation | ✅ labels and report translated, **periods and every value unchanged**, per-card *show original*, global switch off restores the file instantly |
| 6 | PDF | ✅ 5 pages, *Key figures*, *Report*, chart, three tables |
| 7 | PPT | ✅ 7 slides, 1 native chart, 3 native tables, report slides as editable text |

Console: no errors, in English and in Korean.

## 10. Export validation

```
v6_plain.pdf   10,821 bytes  5 pages    Report block present
v6_ko.pdf      10,869 bytes  5 pages    [ko] labels, identical numbers
v6_plain.pptx  45,125 bytes  7 slides   1 chart, 3 tables
v6_ko.pptx     45,172 bytes  7 slides   [ko] labels, identical numbers
```

Number sequences extracted from both PDFs and both decks compare equal.

## 11. Files

**New (backend):** `app/excel/narrative.py`,
`app/services/translation/{anthropic_provider,content}.py`,
`app/api/routes/translation.py`, `app/schemas/translation.py`, migration
`5af291c4e799`, tests `test_fidelity.py`, `test_report_blocks.py`,
`test_translation_api.py`.

**Modified (backend):** `excel/{model,pipeline,regions}.py`,
`db/models.py` (`ReportBlock`), `services/import_service.py`,
`services/serializers.py`, `services/translation/{documents,service,__init__}.py`,
`services/export/{context,pdf,powerpoint}.py`, `api/routes/{presentations,exports}.py`,
`schemas/{table,imports,presentation}.py`, `main.py`, `tests/{test_iqc_real,test_export}.py`.

**New (frontend):** `components/report/ReportSection.tsx`,
`components/executive/TranslateSwitch.tsx`, `lib/translation.tsx`.

**Modified (frontend):** `pages/{Department,Import}.tsx`,
`components/table/{IQCTable,IQCCell}.tsx`,
`components/executive/{FigureStrip,ExportButtons}.tsx`, `lib/api.ts`,
`types/api.ts`, i18n `en` / `pt-BR` / `ko`.

**Docs:** `decisions.md` (ADR-0034, ADR-0035), `architecture.md`,
`excel-parser.md`, `api-contract.md`, `data-model.md`, `README.md`.

## 12. Architectural decisions

| ADR | Decision |
| --- | --- |
| **0034** | Prose in a workbook is content: non-tabular regions become report blocks, kept verbatim with their cells. |
| **0035** | Translation is an overlay keyed by the original string; values are never collected, answers that changed data are discarded, and the original is always available. |

## 13. Limitations

1. **No Anthropic key is configured on this machine**, so the real provider was
   exercised only through its unit tests (prompt shape, answer parsing,
   malformed-answer fallback) and the UI was validated with a stub. Setting
   `CSM_TRANSLATION_PROVIDER=anthropic` and `CSM_ANTHROPIC_API_KEY` activates it
   with no code change.
2. **Composite labels are not translated as a whole.** A key figure reads
   `Total · PPM`; the overlay covers `Total` and `PPM` as cells, not the joined
   string, so the card keeps the original. The table cells — where the words
   actually live — are covered.
3. **The report is grouped by sheet, blocks kept apart.** A title and a body
   separated by a blank row are two blocks, shown one after the other. This is
   the file's structure, not a rendering choice.
4. **One translation request covers a whole snapshot.** For a very large
   workbook that is a single large call; batching by section is possible but was
   not needed for the real file (18 strings).
5. **The issue description editor is still a textarea.** TipTap remains
   unbuilt, as instructed for this sprint.
6. **`docs/sprint-5-report.md` §3–4 still describe removed features** — the
   revision note at its top and its §19 explain what happened.
7. **No frontend unit tests** (unchanged): the contract is covered by 337
   backend tests plus the browser session.

## 14. Next steps (Sprint 7 candidates — not started)

1. **Configure the Anthropic key** and validate a real translation of the IQC
   report into pt-BR and ko, checking the rejection counter stays at zero.
2. **The rich Issue Report editor** (TipTap with inline images), using the
   document model already stored.
3. **An "all periods" issue view** and issue history across versions.
4. When the real **OQC** workbook arrives: fixture, schema read from the data,
   and nothing else — the parser, report, translation and export layers should
   need no change.
