# SQLite schema

Three layers, deliberately separated:

| Layer | Tables | Lifecycle |
| --- | --- | --- |
| **Facts** | `raw_data_files`, `department_data`, `table_definitions`, `table_columns`, `table_rows`, `table_cells` | written once at import, never edited |
| **Editorial** | `presentations`, `presentation_versions`, `version_imports`, `chart_definitions`, `issue_reports`, `issue_report_columns`, `issue_report_rows`, `issue_report_cells` | what the user edits and versions |
| **Support** | `translations`, `assets`, `asset_usages` | caches and files on disk |

```
presentations 1─* presentation_versions ─┬─* chart_definitions
                                         ├─* issue_reports ─┬─* issue_report_columns
                                         │                  ├─* issue_report_rows
                                         │                  └─* issue_report_cells (doc = TipTap JSON)
                                         └─* version_imports *─ department_data
raw_data_files 1─* department_data 1─* table_definitions ─┬─* table_columns
                                                          ├─* table_rows
                                                          └─* table_cells
assets 1─* asset_usages *─1 issue_report_cells
```

## Rules encoded in the model

* **No duplication across versions.** A version *references* imports through
  `version_imports`; only editorial content is copied when a new version is
  created. Publishing v4 of OQC does not copy 30,000 cells.
* **Imports are immutable.** Re-uploading produces a new `department_data`, so
  an older version keeps rendering exactly what it always rendered.
* **Presentation limit (8).** `presentations.status` distinguishes
  `draft`/`ready` (active) from `archived`/`trashed`. Nothing is ever deleted
  automatically; `trashed_at` powers a recoverable bin before permanent
  deletion.
* **Rich content lives as a document.** `issue_report_cells.doc` holds a
  TipTap/ProseMirror JSON tree — text, marks, hard breaks and images together.
  That is what makes format-preserving translation possible.
* **Translation is cached by content hash.** Unique on
  `(source_hash, target_language, provider)`; the hash is computed over the
  canonical source document, so an unchanged text is never re-translated and an
  edited one automatically misses the cache.
* **Images never enter SQLite.** `assets` stores path, mime, size, hash and
  dimensions; the bytes stay under `data/assets/`. `asset_usages` records where
  each file is referenced so orphans can be collected.

## Migrations

Alembic, SQLite-friendly (`render_as_batch=True`). The initial revision creates
the full schema:

```bash
cd backend && .venv/bin/alembic upgrade head
```
