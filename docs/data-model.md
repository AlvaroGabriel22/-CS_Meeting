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


## 3. Chart projections

Nothing new is stored: analytics are computed from the same tables.

```
Series          selector {table, category, subcategory, metric, seriesType}
                points[] {period, value, display, valueType, source}
                provenance {sheet, sourceRange, tableId}

Chart           {table, metric, sheet, sourceRange, periods,
                 bars[{key, label, points}], line{key, label, points}}
ChartPoint      {period, value|null, display, source}
```

* the **selector is the identity** of a series across snapshots (ADR-0021);
* no projection carries a delta, a percentage, a severity or a score: the
  system draws the numbers the workbook holds and calculates nothing
  (ADR-0033, ADR-0036);
* every projection keeps `source` (the cell) and `sourceRange` (the block), so
  a number on a chart can always be traced back to the workbook and the version.


## 4. The report and the settings

| Table | Holds |
| --- | --- |
| `version_reports` | one report per snapshot: the rich document, its plain text and its content hash |
| `report_media` | images the author attached, pointing at `assets` |

```
version_reports
├── version_id (unique)                 the snapshot it belongs to
├── language                            what it was written in
├── content {title, columns[], rows[]}  the table the author built
│     row.cells[columnId] = [block, …]  ordered: text | image | shape
├── text                                its words, flattened, for translation
└── translation_key                     content hash → the translation cache
report_media ──▶ assets (bytes on disk, metadata in SQLite)

department_settings
├── department (unique)
├── chart_titles {"TTL": "Total incoming"}
└── table_titles {"TTL": "Summary"}
```

Rules (ADR-0036):

* the system never writes, summarises or suggests a word of it;
* a cell is an *ordered list of blocks*, so the author controls what sits above
  what (ADR-0038);
* the settings are per department and outlive an import: renaming `TTL` once
  keeps that name for every future upload of the same workbook;
* saving replaces it; the snapshot it belongs to is never touched;
* `translation_key` is the content hash, so an unchanged report costs no
  provider call;
* the Sprint 5 `issues` tables and the Sprint 0 `issue_report*` grid were
  dropped by migration `902bbcb42eb9` — this replaces both.


## 5. Translation

Nothing new is stored about the *content*: a translation is an overlay computed
on request and cached by string.

```
translations
├── source_hash        sha256 of the linguistic content (one string or one doc)
├── source_language, target_language, provider, model
├── content            {"text": "…"} for a string, a document tree for an issue
└── source_preview, created_at, last_used_at
```

* the cache key is the *text*, not the cell: the same label costs one
  round-trip for the whole product;
* `text_hash(text) == content_hash(doc_with(text))` by construction, so strings
  and rich documents share one rule;
* an answer that changed a data token is never cached — the original is kept
  (ADR-0035).
