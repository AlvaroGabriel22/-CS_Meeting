# Backend ↔ frontend contract

* Wire format is **camelCase**; Python stays snake_case (`CamelModel` in
  `app/schemas/common.py`).
* Types are declared twice on purpose: `backend/app/schemas/*.py` and
  `frontend/src/types/api.ts`. They change together.
* Errors always return `{ "code", "message", "detail" }` with a stable `code`
  (`upload_rejected`, `parse_error`, `not_found`, `limit_reached`, …).

## Implemented (Sprint 0)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | status, parser version, languages, presentation limit |
| `POST` | `/api/uploads` | multipart (`department`, `file`, `force`) → parsed import |
| `POST` | `/api/imports` | alias of `/api/uploads` |
| `GET` | `/api/imports` | recent imports (optional `?department=`) |
| `GET` | `/api/imports/{id}` | one import with its table summaries |
| `GET` | `/api/imports/{id}/tables/{tableId}` | full normalized table (cells included) |
| `GET` | `/api/imports/{id}/tables/{tableId}/interpretation` | semantic view (light) |
| `GET` | `/api/imports/{id}/tables/{tableId}/view` | **render model**: merges as spans, hierarchy as depth |
| `GET` | `/api/presentations` · `/api/presentations/{id}/versions` | presentations and their snapshots |
| `GET` | `/api/versions/{id}` · `/api/versions/{id}/imports` | one snapshot and the data it froze |
| `GET` | `/api/versions/{id}/view` | **render model of a whole snapshot** |

`POST /api/uploads` is the canonical endpoint; `/api/imports` stays as an alias
for compatibility and new code must not use it.

`POST /api/uploads` validates extension, MIME, size and the ZIP magic bytes,
stores the file as `data/raw/<DEPT>/<date>-<hash>.xlsx`, parses it and persists
the result. An identical file already parsed by the same parser version is
**not** parsed again: the previous import comes back with `reused: true`
(`force=true` overrides).

### Import response (trimmed)

```json
{
  "id": 3,
  "reused": false,
  "department": "IQC",
  "parserVersion": "1.0.0",
  "summary": {
    "tableCount": 1,
    "periodLabels": ["2025", "2026", "Aug", "Sep", "W33", "W34"],
    "shapes": ["matrix"]
  },
  "rawFile": { "originalFilename": "IQC_W34.xlsx", "sha256": "…", "sizeBytes": 20147 },
  "tables": [
    {
      "id": 5,
      "sheetName": "IQC",
      "sourceRange": "B1:Q38",
      "shape": "matrix",
      "periodAxis": "columns",
      "hierarchy": ["category", "subcategory", "metric"],
      "rowCount": 38,
      "colCount": 16,
      "periods": [{ "kind": "week", "label": "W34", "week": 34, "sortKey": "0000-W34" }]
    }
  ]
}
```

### Interpretation response (trimmed)

```json
{
  "department": "IQC",
  "table": "IQC — Quality Weekly Report",
  "sourceRange": "B1:Q38",
  "hierarchy": ["category", "subcategory", "metric"],
  "periods": ["2025", "2026", "Jan", "…", "Sep", "W33", "W34"],
  "rows": [
    {
      "category": "SEC", "subcategory": "Total", "metric": "PPM", "seriesType": null,
      "values": [
        { "period": "W34", "type": "number", "raw": "648", "value": 648.0,
          "display": "648.0", "source": "Q5" },
        { "period": "W33", "type": "error", "error": "#DIV/0!", "source": "P5" }
      ]
    }
  ]
}
```

Use the interpretation endpoint for charts and inspection; use the full table
endpoint only when rendering the table itself (it carries every cell).

### Render model (`/view`)

What the UI draws, so that it never re-derives structure:

```json
{
  "title": "TTL", "sheet": "IQC", "sourceRange": "B2:I17",
  "hierarchy": ["category", "subcategory", "metric"],
  "labelColumnCount": 2, "headerRowCount": 1,
  "periods": [{ "label": "Aug", "kind": "month", "quarter": "3Q", "year": 2026 }],
  "rows": [
    {
      "kind": "data", "depth": 0, "isHeadline": true, "block": 0,
      "category": "Total", "metric": "PPM", "inferred": ["category", "metric"],
      "cells": [
        { "col": 0, "kind": "empty", "text": "", "inferredText": "Total",
          "borders": ["top", "right", "bottom", "left"] },
        { "col": 1, "kind": "empty", "text": "", "borders": ["left", "right"] },
        { "col": 2, "kind": "value", "text": "6,629", "value": 6629.0,
          "align": "center", "source": "D3" }
      ]
    }
  ],
  "meta": { "reportingYear": 2026, "headlineMetric": "PPM", "headlineConfirmed": true }
}
```

Rules the payload guarantees: a merged range appears once with its spans and the
covered coordinates are omitted; `text` is already formatted and is never
recomputed on the client; `borders` are the sides the workbook draws;
`inferredText` is what the parser read for a cell the file leaves empty and must
be shown as visibly different from real content (ADR-0020); `headlineMetric` is
metadata and is never drawn as a label (ADR-0019).

## Analytics (Sprint 3)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/versions/{id}/analytics/series` | chart-ready series + selector options |
| `GET` | `/api/versions/{id}/analytics/comparison` | two periods of one snapshot |
| `GET` | `/api/versions/{id}/analytics/versus/{otherId}` | one period across two snapshots |
| `GET` | `/api/versions/{id}/analytics/executive` | key figures for one period |

Query parameters are model dimensions, never period names in the path:
`table`, `category`, `subcategory`, `metric`, plus `order=file|chronological`
for the series and `periodA`/`periodB` (or `period`) for the comparisons.

```json
{
  "versionId": 2, "department": "IQC", "order": "file",
  "periods": [{ "label": "Aug", "kind": "month", "quarter": "3Q", "sortKey": "2026-M08" }],
  "series": [
    {
      "key": "TTL|Total||PPM|",
      "label": "Total · PPM",
      "selector": { "table": "TTL", "category": "Total", "metric": "PPM" },
      "sheet": "IQC", "sourceRange": "B2:I17",
      "points": [{ "period": { "label": "Aug" }, "value": 5495.0,
                   "display": "5,495", "source": "I3" }]
    }
  ],
  "options": { "tables": ["TTL", "SEC", "TNP"], "metrics": ["PPM", "Rej. Lot", "Insp. Lot"] }
}
```

A comparison answers with one row per series:

```json
{
  "kind": "periods", "periodA": { "label": "3Q" }, "periodB": { "label": "Aug" },
  "rows": [{
    "label": "Total · PPM",
    "delta": { "valueA": 6329.0, "valueB": 5495.0, "delta": -834.0,
               "deltaPercent": -13.18, "direction": "down",
               "status": "ok" },
    "sourceA": "H3", "sourceB": "I3"
  }],
  "warnings": []
}
```

`deltaPercent` is `null` when the baseline is missing or zero — `status` says
which (`missing_a`, `missing_b`, `undefined_percent`). `direction` is the sign
of the subtraction; no field says whether that movement is good, and there is no
`insights` key in any response (ADR-0033).

### Executive view (`/analytics/executive`)

One call for the top of a department page: `period` (default: the last one in
the file), `table` and `metric` (default: the department's headline metric).

```json
{
  "versionId": 2, "versionNumber": 2, "department": "IQC",
  "period": { "label": "Aug", "quarter": "3Q", "year": 2026 },
  "previousPeriod": { "label": "3Q" },
  "comparisonBasis": "preceding",
  "metric": "PPM",
  "figures": [{
    "key": "TTL|Local||PPM|", "label": "Local · PPM",
    "selector": { "table": "TTL", "category": "Local", "metric": "PPM" },
    "period": { "label": "Aug" },
    "display": "35,714", "value": 35714.0, "valueType": "number",
    "previousPeriod": { "label": "3Q" },
    "previousDisplay": "9,709", "previousValue": 9709.0,
    "delta": 26005.0, "deltaPercent": 267.8, "direction": "up", "status": "ok",
    "target": null, "targetDisplay": null, "targetStatus": null,
    "source": "I15", "sourceRange": "B2:I17"
  }],
  "warnings": ["reference_period_is_preceding_column", "no_target_in_snapshot"]
}
```

`comparisonBasis` says what the figure compares against (ADR-0025); `target`
appears only when the workbook carries one, and `targetStatus`
(`above`/`below`/`at`) compares the two numbers without saying which side is the
desirable one. The figures come back in the order the workbook lists them — they
are not ranked, and the response carries no sentence, score or verdict about
them (ADR-0033).

## Issue reports and exports (Sprint 5)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/versions/{id}/issues` | issues of a snapshot (`period`, `status`) |
| `POST` | `/api/versions/{id}/issues` | raise an issue about one reading |
| `PATCH` | `/api/versions/{id}/issues/{issueId}` | edit the editorial half only |
| `POST` | `/api/versions/{id}/issues/{issueId}/media` | attach an image (multipart) |
| `GET` | `/api/assets/{assetId}` | serve an image |
| `POST` | `/api/versions/{id}/export/pdf` | structured PDF of the current view |
| `POST` | `/api/versions/{id}/export/ppt` | editable PowerPoint of the current view |

Creating an issue takes a **selector**, never numbers:

```json
POST /api/versions/2/issues
{ "table": "TTL", "category": "Local", "metric": "PPM", "period": "Aug",
  "title": "Local PPM spike", "description": "Containment in place.",
  "origin": { "view": "executive", "figure": "TTL|Local||PPM|" } }
```

`title` and `severity` are optional: without them the service stores a neutral
default title (the selection and the period) and `severity: "info"`, for the
user to set — the system does not classify an issue it did not raise
(ADR-0033). `origin` is free-form provenance: what the user was looking at.

The response carries the numbers the service read from the snapshot —
`value`, `previousValue`, `delta`, `deltaPercent`, `direction`, `sourceCell`,
`sourceRange` — plus the editorial fields. `PATCH` accepts only `title`,
`description`, `severity`, `status` and `language`; anything else is refused
with `validation_error` naming the field (ADR-0029).

Exports take the page's state and stream the file back:

```json
POST /api/versions/2/export/pdf
{ "period": "Oct", "table": "TTL", "metric": "PPM", "compareWith": 1 }
```

Both formats are built from one context (ADR-0030): a different period gives a
different file, and the deck's chart and tables are native, editable objects.

## Planned

| Sprint | Endpoints |
| --- | --- |
| 1 | `GET/POST /api/presentations`, `PATCH /api/presentations/{id}` (archive/trash/restore), `GET/POST /api/presentations/{id}/versions`, `POST /api/presentations/{id}/versions/{n}/restore` |
| 2 | `GET/POST/PATCH /api/charts` bound to a version + table |
| 3 | `/api/issue-reports` (+ rows/columns/cells), `POST /api/assets` |
| 4 | `POST /api/translations` (cache-first), `GET /api/translations/{hash}` |
| 5 | `POST /api/exports/pdf`, `POST /api/exports/pptx` (department / all) |

The presentation model these will serve is already defined in
`app/schemas/presentation.py` and `frontend/src/types/api.ts`:

```
PresentationModel {
  presentation, version,
  imports[], tables[], charts[], issueReports[], assets[], language
}
```

## The department page (Sprint 8)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/versions/{id}/charts` | one chart per table; `stacked` says how the bars stand |
| `GET` / `PUT` | `/api/versions/{id}/report` | the report the author built |
| `POST` | `/api/versions/{id}/report/media` | upload an image to place in a cell |
| `POST` | `/api/versions/{id}/translation` | the report and the typed titles in another language |
| `GET` | `/api/reports` | every saved report (`?department=IQC`) |
| `GET` / `PUT` | `/api/departments/{code}/settings` | chart and table titles |
| `GET` | `/api/assets/{assetId}` | serve an image |
| `POST` | `/api/versions/{id}/export/pdf` · `/export/ppt` | the page, or one part of it |

```json
GET /api/versions/4/charts
{
  "metric": "PPM",
  "charts": [{
    "table": "TTL", "title": "Total incoming", "stacked": true,
    "periods": [{ "label": "Aug", "kind": "month" }],
    "bars": [{ "label": "SKD", "points": [{ "period": "Aug", "value": 0.0, "source": "I8" }] },
             { "label": "CKD", "points": [] }, { "label": "Local", "points": [] }],
    "line": { "label": "Total", "points": [] }
  }]
}
```

`title` is what the department settings call it, or `null` for the workbook's
own name. `stacked` comes from `DepartmentSchema.chart_bars` (ADR-0037).

### The report

```json
PUT /api/versions/4/report
{ "content": {
    "title": "Weekly quality review",
    "columns": [{ "id": "c1", "name": "Finding" }, { "id": "c2", "name": "Action" }],
    "rows": [{ "id": "r1", "cells": { "c1": [
      { "id": "b1", "type": "text", "text": "Local supplier above the limit",
        "align": "center", "bold": true, "size": "large" },
      { "id": "b2", "type": "image", "assetId": 2, "align": "center", "width": 80,
        "caption": "Rejected part" },
      { "id": "b3", "type": "text", "text": "Dimensional analysis under way." }
    ] } }]
} }
```

A cell is an **ordered list of blocks** — `text`, `image` or `shape` — so the
same cell can hold text, then a photo, then more text, in exactly that order
(ADR-0038). Blocks the system cannot draw are dropped rather than stored;
cells of a deleted column go with it. Shapes are `rectangle`, `circle`, `line`,
`arrow` or `divider`, with a colour and a size.

Images are uploaded first and placed afterwards:

```json
POST /api/versions/4/report/media   (multipart)
→ { "assetId": 2, "url": "/api/assets/2", "mimeType": "image/png", "sizeBytes": 337 }
```

### Downloads

The three parts can be taken separately, which is what the reports library
offers:

```json
POST /api/versions/4/export/pdf
{ "includeCharts": false, "includeTables": false }   // the report alone
{ "includeTables": false, "includeReport": false }   // the charts alone
{ "includeCharts": false, "includeReport": false }   // the tables alone
{ "language": "ko", "translate": true }              // everything, translated
```

Translating an export translates the report and only the report; the numbers of
a translated file are identical to an untranslated one, and a test asserts it.
