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
