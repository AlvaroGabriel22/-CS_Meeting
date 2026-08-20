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
