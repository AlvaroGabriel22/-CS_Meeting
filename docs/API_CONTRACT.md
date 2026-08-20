# Backend ↔ frontend contract

* Wire format is **camelCase**; Python stays snake_case (`CamelModel` in
  `app/schemas/common.py` does the translation).
* Types are declared twice on purpose: `backend/app/schemas/*.py` and
  `frontend/src/types/api.ts`. They must be changed together — the TS file is
  the only place the frontend describes server data.
* Errors always come back as `{ "code", "message", "detail" }` with a stable
  `code` (`upload_rejected`, `parse_error`, `not_found`, `limit_reached`, …).

## Implemented in Sprint 0

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | status, parser version, languages, presentation limit |
| `POST` | `/api/imports` | multipart upload (`department`, `file`) → parsed import |
| `GET` | `/api/imports` | recent imports (optional `?department=`) |
| `GET` | `/api/imports/{id}` | one import with its table summaries |
| `GET` | `/api/imports/{id}/tables/{tableId}` | the full normalized table |

`POST /api/imports` validates extension, MIME, size and the ZIP magic bytes,
stores the file under `data/raw/<DEPT>/<date>-<hash>.xlsx` (the uploaded name is
never trusted), parses it and persists the result.

### Example — import response (trimmed)

```json
{
  "id": 1,
  "department": "IQC",
  "parserVersion": "1.0.0",
  "summary": {
    "tableCount": 1,
    "periodLabels": ["2025", "2026", "Aug", "W30", "W31", "W32"],
    "shapes": ["matrix"]
  },
  "rawFile": { "originalFilename": "IQC_W32.xlsx", "sha256": "…" },
  "tables": [
    {
      "id": 1,
      "sheetName": "IQC",
      "sourceRange": "B1:P14",
      "shape": "matrix",
      "periodAxis": "columns",
      "rowCount": 14,
      "colCount": 15,
      "periods": [{ "kind": "week", "label": "W32", "week": 32, "sortKey": "0000-W32" }]
    }
  ]
}
```

## Planned (next sprints)

| Sprint | Endpoints |
| --- | --- |
| 1 | `/api/presentations` (CRUD, 8-limit, archive/trash/restore), `/api/presentations/{id}/versions` |
| 2 | `/api/charts`, table/chart binding |
| 3 | `/api/issue-reports` (+ rows/columns/cells), `/api/assets` |
| 4 | `/api/translations` (cache-first), `TranslationProvider` |
| 5 | `/api/exports/pdf`, `/api/exports/pptx` (department / all) |
