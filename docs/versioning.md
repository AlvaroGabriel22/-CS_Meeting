# Versioning and snapshots

Every upload is a photograph of the raw data at that moment. Photographs are
**append-only**: version 3 showing `4Q | Nov | Dec` never touches version 1,
which still shows `3Q | Aug` and still points at the workbook it came from.

```
Presentation "IQC Quality Weekly"
 ├── v1  label "Aug"   → import 7  → RawdataIQC.xlsx        '25 '26 1Q 2Q 3Q Aug
 ├── v2  label "Sep"   → import 9  → IQC_2026_W36.xlsx      … Aug Sep
 └── v3  label "Dec"   → import 12 → IQC_2026_W49.xlsx      … 4Q Nov Dec
```

## The chain

| Entity | Holds | Lifecycle |
| --- | --- | --- |
| `presentations` | one per department, name, current period label, status | long-lived |
| `presentation_versions` | number, label, status, summary, warnings, parent | **immutable once created** |
| `version_imports` | which imports a version froze | reference, never a copy |
| `department_data` | one parse of one file: tables, rows, cells | immutable |
| `raw_data_files` | the original workbook on disk, its hash and size | kept for audit |

A version's `summary` records exactly what the snapshot showed:

```json
{
  "parserVersion": "1.0.0",
  "tableNames": ["TTL", "SEC", "TNP"],
  "periodLabels": ["'25", "'26", "1Q", "2Q", "3Q", "Aug"],
  "tableCount": 3,
  "rawFile": "RawdataIQC.xlsx"
}
```

## Upload flow

```
choose file → POST /api/uploads (createVersion=false)   parse + preview, no snapshot
            → user checks tables, periods, warnings
            → POST /api/uploads (createVersion=true)    snapshot saved
```

The confirmation call costs nothing extra: the file's content hash is already
known, so it is **not parsed twice** (`reused: true`). Passing `force=true`
re-parses on purpose.

Versions are created with status `published` and a `parentVersionId` pointing at
the previous one, so the chain of what the department reported is intact.

## Rules

* **Nothing is overwritten.** A new upload always produces a new version; the
  previous one keeps its imports, its periods and its warnings.
* **Nothing is deleted automatically.** The 8-presentation ceiling is enforced
  when a *presentation* is created (`limit_reached`), never by removing
  something. Archiving and the recoverable bin are user actions.
* **The original file is kept.** `data/raw/<DEPT>/<date>-<hash>.xlsx` stays on
  disk for download, audit, re-processing and version comparison.
* **The parser version is part of the snapshot.** A parser upgrade does not
  rewrite old versions; it only means a *new* upload of the same file is parsed
  again instead of reused.
* **Quarter consolidation is a new snapshot, not a mutation.** When the file
  switches from `Aug | Sep | Oct` to `4Q | Nov | Dec`, the parser reads the new
  state and the previous version still shows the months.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/uploads` | parse, persist, snapshot (`createVersion`, `force`) |
| `GET` | `/api/presentations` | presentations with their latest version |
| `GET` | `/api/presentations/{id}/versions` | every snapshot, newest first |
| `GET` | `/api/versions/{id}` | one snapshot: summary, warnings, imports |
| `GET` | `/api/versions/{id}/imports` | the data the snapshot froze |

## Not yet built (Sprint 2+)

Restoring a version into an editable draft, comparing two versions field by
field, and the `draft` autosave lane described in the master prompt. The schema
already carries `status`, `parent_version_id` and `notes` for all three.
