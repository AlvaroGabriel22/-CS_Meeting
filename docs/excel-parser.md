# Excel parser — how the structure is identified

> The riskiest part of this system. Everything here is *inferred*; nothing is
> positional. `B2:Q40` is recorded as provenance, never used as a rule.

## The four stages

```
file ──parser──▶ RawWorkbook ──regions──▶ Rect[] ──interpreter──▶ TableInterpretation ──normalizer──▶ NormalizedTable
      (values,                 (blocks of        (title, header band,          (typed cells, raw +
       styles,                  cells)            labels, periods,              interpreted values,
       merges)                                    hierarchy)                    styles, provenance)
```

### 1. Parser — what the file literally holds

`app/excel/parser.py`, the only module that imports openpyxl. The workbook is
opened twice: with cached values (what the analyst sees, including `#DIV/0!`)
and with formulas (kept for traceability). For every cell it records value,
formula, number format, font/fill/border/alignment, merged range and the Excel
address. Column widths and row heights come along.

**Merged ranges are resolved here**: every covered cell inherits the anchor's
value, and knows its range and whether it is the anchor. Nothing downstream has
to ask "is this cell hidden under a merge?".

### 2. Regions — finding the tables

`app/excel/regions.py`. The used area is trimmed of empty borders and cut
recursively on fully empty rows and columns (a guillotine cut). Two tables side
by side (ASR and CASR) become two regions; a merged cell spanning a would-be
separator keeps that separator occupied, so merges never split a table.

The resulting range is stored as `sourceRange`. It is output, not input.

### 3. Interpreter — what it means

`app/excel/interpreter.py` (helped by `app/excel/hierarchy.py` for the labels
and `app/excel/period_engine.py` for the time axis).

**Title** — a lone, wide, non-numeric row at the top of the region, or a corner
cell merged across the label columns. In the real IQC sheet the header starts
with `TTL` merged over both label columns: that is the table naming itself, and
it becomes the table's title (`TTL`, `SEC`, `TNP`).

**Header band** — leading rows that are not measurements. A row counts as data
when enough of its cells are real measurements. Period tokens (`2026`, `Aug`,
`W32`) do not count as measurements, which is what stops a merged year header
from looking like a data row. Conversely, a row is only allowed to discount its
numbers when it is *dominated* by period tokens — so a value of `1961` sitting
in a data row is never mistaken for a year.

**Label columns** — leading columns that stay textual through the data band.

**Periods** — each data column's header path is read top-down:

```
"2026"  →  "Aug"  →  "W32"  →  "Target"
 year      month     week      series
```

The finest token wins (`kind = week`), the coarser ones fill in the details
(`year=2026, month=8`), and `Target`/`Result`/`실적` become the **series**, not a
period. Recognised spellings (en / pt-BR / ko):

| Kind | Examples |
| --- | --- |
| year | `2026`, `CY26`, `FY2026`, `'26`, `2026년` |
| quarter | `Q3`, `3Q`, `T3`, `3분기` |
| month | `Aug`, `August`, `Ago`, `Agosto`, `8월`, `Aug-26`, `2026-08` |
| week | `W32`, `WK32`, `W-32`, `Week 32`, `S32`, `Semana 32`, `32주` |

A bare integer becomes a period **only** when its header row is already
dominated by that kind of token (a row reading `W30 W31 32` gives the `32`
meaning; a lonely `8` does not become August).

**Period axis** — two or more columns carrying a period puts time on the
columns. Otherwise the first label column is tested as a period sequence, which
catches transposed tables (`W30 W31 W32` running downwards).

**Period engine** — once the columns are known they are resolved *against each
other*: undated quarters and months inherit the reporting year, months learn
their quarter, and everything gets a chronological `sortKey`. See
[period-engine.md](period-engine.md).

**Hierarchy** — label columns are assigned in this order (ADR-0012):

1. a column dominated by *plan-vs-outcome* labels (`Target`, `Result`, `Plan`,
   `Forecast`, at least two distinct) is a **series**, not a metric;
2. the outermost remaining column groups the rows, so it is the **category** and
   is never considered for the metric role;
3. the **metric** is the innermost remaining column whose values read as measured
   quantities (`PPM`, `Def.`, `Insp.`…), or — failing that — the innermost
   column, because the layout implies it;
4. a single label column of unknown words names the rows: category.

Merged and blank label cells are carried downwards, so `SEC` written once above
nine rows reaches all nine. The interpreter also records *where the analyst
actually typed* each label, because that is what separates a new block from a
continuation.

**Blocks, and metrics that are never written** — the real IQC tables look like
this (column B on the left, column C in the middle):

```
(empty)   (empty)      6629     ← the headline metric of the block: PPM
(empty)   Rej. Lot      139
(empty)   Insp. Lot   20970
Imported  (empty)      5319     ← headline metric of "Imported"
Imported  Rej. Lot       83
Imported  Insp. Lot   15604
Imported  SKD         18847     ← a sub-group, and its headline metric
Imported  Rej. Lot       69
Imported  Insp. Lot    3661
```

The word `PPM` never appears, `SKD`/`CKD` sit in the *metric* column although
they are sub-groups, and the first block has no name. Three structural rules
read it (ADR-0014), with no vocabulary requirement:

1. **repetition separates metrics from groups** — a label that comes back in
   every block (`Rej. Lot`, `Insp. Lot`) is a metric; a label appearing once
   (`SKD`, `CKD`) opens a sub-group;
2. **a block starts** where a category is written, where a sub-group label
   appears, or where the metric cell is empty;
3. **the first row of a block carries the headline metric** — the derived figure
   the block is about. Its name comes from the department schema
   (`headline_metric = "PPM"` for IQC) and is flagged as inferred; an unnamed
   leading block gets `implicit_group_label` (`Total`), also flagged.

Every inference is visible on the row (`inferred: ["category", "metric"]`) and
on the table (`headline_metric_inferred`, `implicit_group_label`).

**Verification** — an inference that can be checked, is checked. The schema
declares how the headline metric relates to its siblings
(`PPM = Rej. Lot / Insp. Lot × 1_000_000`), and `app/excel/verification.py`
tests every block against every period. On the real IQC file all 87 values
match, which *proves* the unnamed rows are PPM. A mismatch never rewrites a
value: it raises `headline_metric_mismatch`.

```
SEC   → Total   → PPM / Def. / Insp.        category > subcategory > metric
      → TSI     → PPM / Def. / Insp.
      → Packing → PPM / Def. / Insp.

ASR   → MX      → Target / Result           category > subcategory > series
      → Mobile  → Target / Result           (metric = null: the measured
CASR  → MX      → Target / Result            quantity is the indicator itself)
```

**Department schemas** (`app/domain/departments.py`) raise confidence — they say
that `SEC` is an IQC section and `Insp.` is a metric — but the parser works
without them. Adding a section or a metric is a data change there, never an
`if department == "IQC"` somewhere in the code.

### 4. Normalizer — the model the system keeps

`app/excel/normalizer.py` builds `NormalizedTable`: descriptors for every row
and column, and one cell object carrying **both** readings:

| Field | Meaning |
| --- | --- |
| `rawValue` | exactly what the file holds — `"3,000"`, `"NA"`, `"#DIV/0!"` |
| `number` | the interpreted value — `3000.0`, or `null` |
| `displayValue` | the canonical rendering — `"3,000"` |
| `semantic` | `period` / `category` / `subcategory` / `metric` / `value` / … |
| `source`, `mergedRange`, `styleId` | provenance and visual metadata |

## Values

| In the file | Stored | Shown |
| --- | --- | --- |
| `3000` | `number: 3000`, `rawValue: "3000"` | `3,000` (en) / `3.000` (pt-BR) |
| `0.1336` fmt `0.0%` | `number: 0.1336`, `display.kind: percent` | `13.4%` |
| `NA`, `N/A`, `n/d`, `-`, `—`, `sem dados` | `valueType: na`, `number: null`, `rawValue` kept | the original text |
| `#DIV/0!` | `valueType: error`, `errorCode` | `#DIV/0!` |
| formula, no cached value | `formula` kept, warning `formula_without_cached_value` | empty + notice |

Numbers are never rewritten. Formatting is a hint carried to the UI, the PDF and
the PPT, so the same value looks the same everywhere
(`app/excel/values.py::format_number` ↔ `frontend/src/lib/format.ts`).

## Styles

Font, weight, italic, size, colour, fill, borders, alignment, wrap, column
width and row height are captured and deduplicated per table (`styleId` →
`styles{}`). They are **visual metadata**: no branch of the parsing logic reads
them.

## Warnings instead of guesses

The parser never invents structure. When something is off, or when it had to
infer, it says so:

| Warning | Meaning |
| --- | --- |
| `headline_metric_inferred` | the block's first row was named from the schema (`PPM`) |
| `implicit_group_label` | an unnamed leading block was called `Total` |
| `headline_metric_mismatch` | the headline value does not match its own numerator/denominator |
| `unnamed_headline_metric` | no schema to name the headline row; the metric is left null |
| `period_without_year` | months/weeks with no year anywhere in the table |
| `no_period_detected` | a matrix table whose header tokens are not periods |
| `formula_without_cached_value` | the workbook was saved without evaluating its formulas |
| `region_failed:<range>` | one region raised; the rest of the file was still imported |
| `skipped_non_tabular_region:<range>` | a prose block (a README, a legend) was ignored |
| `no_table_detected`, `empty_sheet` | nothing to import |

## Known limits (see the Sprint 0 report)

* Tables whose header band is deeper than 6 rows, or with more than 4 label
  columns, are read partially (caps in `interpreter.py`).
* A metric column whose vocabulary is entirely unknown falls back to "innermost
  label column is the metric".
* The NA vocabulary is a closed list (ADR-0013): `TBD`, `?` and other unknown
  words stay text and are never counted as missing data.
* Values written as text in an unusual locale (`1 234,5` with a non-breaking
  space) parse, but exotic separators may not.
* Charts inside the workbook, images and pivot caches are ignored.
* Files produced by a tool that does not cache formula results give empty value
  cells (flagged, not silently zeroed).

## Regions that are not tables

The guillotine split (`regions.py`) cuts a sheet into blocks; the interpreter
turns the ones that hold data into tables. A block with no numbers and no
periods — a README sheet, a note, a legend — is **skipped**, with the warning
`skipped_non_tabular_region:A3:A6` recording what was left out.

Sprint 6 briefly kept such blocks as content; Sprint 7 removed that again. The
report of a presentation is written by hand in the application, not read out of
a spreadsheet (ADR-0036).
