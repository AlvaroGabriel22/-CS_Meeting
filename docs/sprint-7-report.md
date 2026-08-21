# Sprint 7 — report

**Scope: the page, as specified.** Three containers — charts, tables, report —
and the removal of everything else. The system identifies the file's structure
and draws it; the user does the arithmetic in Excel and writes the report by
hand; AI translates that report and nothing else.

---

## 1. The page

```
┌─ charts ──────────────────────────────────────────────────────┐
│  TTL            │  SEC            │  TNP                       │
│  bars: Imported, Local · line: Total · periods from the file   │
└───────────────────────────────────────────────────────────────┘
┌─ tables ──────────────────────────────────────────────────────┐
│  TTL            │  SEC            │  TNP                       │
└───────────────────────────────────────────────────────────────┘
┌─ report ──────────────────────────────────────────────────────┐
│  written by hand · images · Translate / Show original          │
└───────────────────────────────────────────────────────────────┘
```

Header: department name, version selector, **Export PDF / PPT**, **Import raw
data**. Nothing else.

## 2. What was removed

| Removed | Where it lived |
| --- | --- |
| Key-figure strip | `services/executive.py`, `FigureStrip.tsx` |
| Issue reports | `services/issues.py`, `api/routes/issues.py`, `IssueCard`, `IssuesSection`, tables `issues` / `issue_media` |
| Period and version comparison | `analytics.compare_*`, `/analytics/comparison`, `/analytics/versus`, `ComparisonPanel`, `ComparisonTable` |
| Period / table / metric selectors | `PeriodSelect.tsx`, the page's filter card |
| Prose read out of the workbook | `excel/narrative.py`, table `report_blocks` (ADR-0034, superseded) |
| The Sprint 0 issue-report grid | tables `issue_report*`, `asset_usages` |
| On-page captions | source ranges, hierarchy lines, parser warnings, cell tooltips |
| Version-wide translation overlay | `POST /versions/{id}/translation`, `lib/translation.tsx` |

Migration `902bbcb42eb9` drops eight tables and adds two. It was verified on a
fresh database, from the first migration to head.

## 3. The charts

`app/services/charts.py` — the only thing the system computes is *which* values
to draw, never a value:

* **one chart per table**, in the workbook's order (TTL, SEC, TNP);
* **vertical bars per category** (`Imported`, `Local`) and **a line for the
  leading group** (`Total`), over the file's own period columns;
* the metric is the department's headline metric when the file has it, else the
  first metric present — no name is hardcoded;
* a category with no reading of its own falls back to the sub-group level, so a
  differently shaped workbook still draws;
* every point carries the cell it came from; a period a row does not reach is a
  gap, never a zero.

Frontend: recharts `ComposedChart` (vertical `Bar` series + one `Line`), three
per row in one container.

## 4. The report

`version_reports` + `report_media`, one report per snapshot:

* stored **to the character**, blank lines included;
* images attach as evidence, validated by magic number;
* `translationKey` is the content hash, so an unchanged report costs no
  provider call;
* nothing in the system writes, suggests or summarises it.

**Translation** (`POST /versions/{id}/report/translation`) is now the *only*
place AI appears. Everything else on the page is interface text shipped in
three languages or a label that came from the workbook — neither is ever sent
anywhere. The rules of ADR-0035 still hold: masking, the data-preservation
check, the original always beside the translation, the stored text never
modified.

## 5. Exports

The file is the page: three charts on page 1, the tables on page 2, the report
on page 3. The deck is five slides — one with the three native charts, three
with the native tables, one with the report as editable text.

```
IQC_Aug_v4.pdf    3 pages    charts · tables · report
IQC_Aug_v4.pptx   5 slides   3 native charts, 3 native tables, 1 report slide
```

## 6. Tests — **288 passing**

| File | Tests | Covers |
| --- | --- | --- |
| `test_charts_and_report.py` | 15 | chart composition, provenance, determinism, gaps, metric from the file, report storage, images, isolation |
| `test_export.py` | 13 | PDF and deck: order, native charts, merges, the report, translated export keeps every number |
| `test_translation_api.py` | 13 | only the report is sent, cache, rejection, original preserved, no provider configured |
| `test_fidelity.py` | 13 | upload of the real file, value preservation, structure preservation, regression |
| `test_analytics.py` / `_api.py` | 22 | series and options; the layer does no arithmetic; the removed endpoints are 404 |
| Sprints 0–2 (parser, periods, render) | 212 | no regressions |

Two tests are worth naming: `test_the_analytics_layer_does_no_arithmetic`
asserts `compute_delta`, `compare_periods` and friends do not exist, and
`test_the_api_offers_no_comparison_or_executive_endpoint` asserts the routes
are gone rather than merely unused.

## 7. Browser validation

Real workbook, version 4, at `http://localhost:5174/department/IQC`:

| Check | Result |
| --- | --- |
| order on screen | ✅ charts → tables → report |
| charts | ✅ three side by side, vertical bars per category, red line for Total, periods `'25 '26 1Q 2Q 3Q Aug` |
| tables | ✅ three side by side, TTL · SEC · TNP, merges and empty headline cells intact |
| report | ✅ written, saved, redisplayed exactly as typed |
| clutter | ✅ no source ranges, no warnings, no hierarchy captions, no tooltips |
| console | ✅ no errors |
| PDF / PPT | ✅ 3 pages / 5 slides, matching the page |

## 8. Limitations

1. **No Anthropic key configured**, so the *Translate* button on the report
   stays hidden (`/api/translation/status` reports `active: false`). Setting
   `CSM_TRANSLATION_PROVIDER=anthropic` and `CSM_ANTHROPIC_API_KEY` in
   `backend/.env` activates it with no code change.
2. **The report editor is a textarea.** The storage is already a rich document,
   so a formatted editor can replace it without a migration.
3. **One report per version.** Changing the version changes the report shown;
   there is no history view across versions.
4. **The chart's y-axis is shared by all series**, so a category an order of
   magnitude above the others flattens the rest (visible on TTL, where Local
   reaches 35,714 in Aug). A second axis for the line is possible if wanted.
5. **Export is not paginated by table**; three tables share page 2, which is
   dense on A4 landscape. One table per page is a one-line change.
6. **OQC and FIELD** remain untouched, waiting for their real workbooks.

## 9. Architectural decision

**ADR-0036 — The page is three containers, and the system only draws.**
Supersedes ADR-0034 (workbook prose) and closes out the analytical layers of
Sprints 3–5.

## 10. Files

**New:** `services/charts.py`, `services/reports.py`, `api/routes/reports.py`,
`schemas/report.py`, migration `902bbcb42eb9`, `tests/test_charts_and_report.py`,
`components/charts/DepartmentCharts.tsx`, `components/report/ReportEditor.tsx`.

**Removed:** `services/executive.py`, `services/issues.py`,
`services/translation/content.py`, `excel/narrative.py`, `schemas/issues.py`,
`api/routes/issues.py`, `tests/test_executive*.py`, `tests/test_issues.py`,
`tests/test_report_blocks.py`, and on the frontend `FigureStrip`,
`TranslateSwitch`, `IssueCard`, `IssuesSection`, `ComparisonPanel`,
`ComparisonTable`, `ChartsPanel`, `QualityChart`, `PeriodSelect`,
`ReportSection`, `lib/translation.tsx`.

**Modified:** `excel/{model,pipeline,regions}.py`, `db/models.py`,
`services/{analytics,import_service,serializers}.py`,
`services/export/{context,pdf,powerpoint}.py`,
`api/routes/{analytics,presentations,exports,translation}.py`,
`schemas/{analytics,table,imports,presentation,translation}.py`, `main.py`,
`pages/{Department,Import}.tsx`, `components/table/{IQCTable,IQCCell}.tsx`,
`components/executive/ExportButtons.tsx`, `lib/api.ts`, `types/api.ts`,
i18n `en` / `pt-BR` / `ko`, and `docs/*`.
