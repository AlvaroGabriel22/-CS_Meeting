# Normalized table model

## Why it exists

The raw files carry their structure *visually*: merged cells, group headers,
a label column, period columns that move every week. Excel coordinates
(`B2:B40`, `Q40`) describe where things happened to be on the day the file was
saved — not what they mean.

After import, the system works exclusively on this model. The Excel file is the
source; it is never consulted again.

## Shape

```
NormalizedTable
├── sheetName, sourceRange ("B2:Q40")   ← provenance / debug only
├── title                               ← detected, may be null
├── shape        matrix | flat | fragment
├── periodAxis   columns | rows | none
├── headerRowCount, labelColCount
├── columns[]  ColumnDescriptor
│   ├── index, sourceColumn ("Q")
│   ├── headerPath ["2026", "Aug", "W32"]
│   ├── period  { kind, label, year, month, week, sortKey }
│   └── series  "Target" | "Result" | …
├── rows[]     RowDescriptor
│   ├── index, sourceRow (40)
│   ├── labelPath ["SEC", "PPM"], level
│   └── period  (only when the table is transposed)
├── cells[]    NormalizedCell
│   ├── row, col              ← table-local, 0-based
│   ├── role      header | label | value | empty
│   ├── valueType empty | number | text | date | bool | error | na
│   ├── number, text, errorCode, formula
│   ├── display   { kind, decimals, thousands, currency }
│   ├── styleId   → styles{}
│   └── source "Q40", mergedRange "B3:B6", isMergeAnchor
├── mergedRanges[]
├── styles{}      deduplicated per table
├── warnings[]
└── meta{}        contextYear, cornerLabel, numericCells, flatPeriodColumns…
```

## How the structure is inferred

1. **Regions** — the sheet is trimmed and cut recursively on fully empty rows
   and columns. Two tables side by side become two regions; the resulting
   `B2:Q40` is *recorded*, never assumed.
2. **Merged cells** — resolved at read time: every covered cell inherits the
   anchor's value, so a merged `2026` header applies to all months under it and
   a merged `SEC` label applies to all of its metric rows.
3. **Title** — a lone, wide, non-numeric row at the top of a region.
4. **Header band** — leading rows that are not measurements. A row is *data*
   when enough of its cells are real measurements; period tokens (`2026`,
   `Aug`, `W32`) don't count, which is what keeps a merged year header from
   looking like data.
5. **Label columns** — leading columns that stay textual through the data band.
6. **Periods** — each data column's header path is parsed top-down
   (`2026` → `Aug` → `W32` → `Target`); the finest token wins, `Target`/`Result`
   become the *series*. Bare integers only become months/weeks when their
   header row is already dominated by months/weeks.
7. **Axis** — if two or more columns carry a period, the time dimension is on
   the columns; otherwise the first label column is tested for a period
   sequence (transposed tables).

## Values

| In the file | Stored as | Shown as |
| --- | --- | --- |
| `3000` | `number: 3000` | `3,000` (en) / `3.000` (pt-BR) |
| `0.1336` with format `0.0%` | `number: 0.1336`, `display.kind=percent` | `13.4%` |
| `NA` | `valueType: na` | `NA` |
| `#DIV/0!` | `valueType: error`, `errorCode` | `#DIV/0!` |
| formula with no cached value | `formula` kept, warning raised | empty + notice |

Numbers are never rewritten. Formatting is a *hint* carried to the UI, the PDF
and the PPT so the same value looks the same everywhere
(`backend/app/excel/values.py::format_number` ↔ `frontend/src/lib/format.ts`).

## What charts are allowed to reference

Selection by **label** and **sortKey**, never by index. A chart configured for
`W32` keeps working when `W32` moves from the 13th to the 12th column, and it
simply reports no data when `W32` scrolls out of the file.
