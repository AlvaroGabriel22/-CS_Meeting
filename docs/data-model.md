# Data model — from Excel to the internal representation

## 1. The normalized table

What the system keeps after an import. Excel-independent, serializable,
versionable.

```
NormalizedTable
├── sheetName, sourceRange "B2:Q40"     ← provenance only
├── title, department, hierarchy ["category","subcategory","metric"]
├── shape         matrix | flat | fragment
├── periodAxis    columns | rows | none
├── headerRowCount, labelColCount
├── columns[]  ColumnDescriptor
│   ├── index, sourceColumn "Q"
│   ├── headerPath ["2026","Aug","W32"]
│   ├── period {kind,label,year,month,week,sortKey}
│   ├── seriesType "Target" | "Result" | null   ← how, not what (ADR-0012)
│   └── semantic  period | series | label
├── rows[]     RowDescriptor
│   ├── index, sourceRow 40
│   ├── labelPath ["SEC","Total","PPM"]
│   ├── category "SEC", subcategory "Total", metric "PPM"
│   ├── seriesType "Target" | null              ← set instead of metric
│   ├── period (transposed tables only)
│   └── semantic  metric | period | …
├── cells[]    NormalizedCell
│   ├── row, col                 ← table-local, 0-based
│   ├── role      header | label | value | empty
│   ├── semantic  title | period | category | subcategory | metric | value
│   ├── rawValue  "3,000" | "NA" | "#DIV/0!"     ← original
│   ├── number 3000.0, text, displayValue "3,000" ← interpreted
│   ├── errorCode, formula, numberFormat, display{}
│   └── styleId, source "Q40", mergedRange "B3:B11", isMergeAnchor
├── mergedRanges[]
├── styles{}      deduplicated per table
├── warnings[]
└── meta{}        contextYear, cornerLabel, labelRoles, numericCells, …
```

### Original vs interpreted

Every reading keeps both sides, which is what makes the interpretation
auditable:

| Original | Interpreted |
| --- | --- |
| `Q2` holds `"W33"` | column period `{kind: week, week: 33, sortKey: "0000-W33"}` |
| `B10` holds `"PPM"` | row `metric = "PPM"`, semantic `metric` |
| `Q40` holds `"3,000"` | `number = 3000.0`, `displayValue = "3,000"` |
| `B3:B11` merged | `mergedRange` on all covered cells, anchor flagged |

### The semantic projection

`app/services/interpretation.py` collapses the model into the view a human (or
a chart) reads:

```json
{
  "department": "IQC",
  "table": "IQC — Quality Weekly Report",
  "hierarchy": ["category", "subcategory", "metric"],
  "periods": ["2025", "2026", "Jan", "…", "Sep", "W33", "W34"],
  "rows": [
    {
      "category": "SEC", "subcategory": "Total", "metric": "PPM",
      "values": [
        {"period": "W33", "type": "number", "raw": "372.2",
         "value": 372.2, "display": "372.2", "source": "P5"}
      ]
    }
  ]
}
```

## 2. SQLite schema

Three layers:

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

### Rules the schema encodes

* **No duplication across versions.** A version references imports through
  `version_imports`; only editorial rows are copied when a version is created.
  Publishing v4 of OQC does not copy 30,000 cells.
* **Imports are immutable.** Re-uploading creates a new `department_data`, so an
  older version keeps rendering exactly what it always rendered.
* **Re-parsing is avoided.** `raw_data_files.sha256` + `department_data.parser_version`
  make "same file, same parser" a lookup instead of a parse.
* **Presentation limit (8).** `presentations.status` separates `draft`/`ready`
  (active) from `archived`/`trashed`; `trashed_at` powers a recoverable bin.
  Nothing is deleted automatically, ever.
* **Rich content is a document.** `issue_report_cells.doc` holds a
  TipTap/ProseMirror tree — text, marks, breaks and images together.
* **Translations are cached by content hash**, unique on
  `(source_hash, target_language, provider)`. The hash covers the *linguistic*
  content only: resizing an image does not invalidate a translation, editing the
  words does.
* **Images never enter SQLite.** `assets` keeps path, mime, size, hash and
  dimensions; bytes live under `data/assets/`. `asset_usages` finds orphans.

### Raw file metadata

`raw_data_files` keeps original filename (sanitised — the uploaded name is never
trusted), stored path (relative to the data directory), mime type, size, sha256,
department and upload timestamp. The workbook itself stays on the filesystem.

## Migrations

Alembic, SQLite-friendly (`render_as_batch=True`):

```bash
cd backend && .venv/bin/alembic upgrade head
```
