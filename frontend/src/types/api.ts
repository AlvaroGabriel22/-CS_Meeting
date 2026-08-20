/**
 * Backend contract (mirrors backend/app/schemas/*).
 *
 * Keep both sides in sync — this file is the only place the frontend is
 * allowed to describe server data.
 */

export type Department = 'IQC' | 'OQC' | 'FIELD'
export type Language = 'en' | 'pt-BR' | 'ko'

export type PeriodKind = 'year' | 'quarter' | 'month' | 'week' | 'day' | 'unknown'
export type CellRole = 'header' | 'label' | 'value' | 'empty'
export type ValueType = 'empty' | 'number' | 'text' | 'date' | 'bool' | 'error' | 'na'
export type TableShape = 'matrix' | 'flat' | 'fragment'
export type PeriodAxis = 'columns' | 'rows' | 'none'

/** A time slot discovered in the raw data — never hardcoded on the client. */
export interface Period {
  kind: PeriodKind
  label: string
  year: number | null
  quarter: number | null
  month: number | null
  week: number | null
  day: number | null
  sortKey: string
  tokens: string[]
}

export interface DisplayFormat {
  kind: 'auto' | 'integer' | 'decimal' | 'percent' | 'currency' | 'text'
  decimals: number | null
  thousands: boolean
  currency: string | null
}

export interface CellStyle {
  bold: boolean
  italic: boolean
  underline: boolean
  fontSize: number | null
  fontName: string | null
  fontColor: string | null
  fillColor: string | null
  alignH: string | null
  alignV: string | null
  wrap: boolean
  borders: string[]
}

export interface TableColumn {
  index: number
  sourceColumn: string | null
  headerPath: string[]
  label: string
  period: Period | null
  series: string | null
  isLabelColumn: boolean
  width: number | null
}

export interface TableRow {
  index: number
  sourceRow: number | null
  labelPath: string[]
  label: string
  level: number
  isHeaderRow: boolean
  period: Period | null
  height: number | null
}

export interface TableCell {
  row: number
  col: number
  role: CellRole
  valueType: ValueType
  number: number | null
  text: string | null
  errorCode: string | null
  formula: string | null
  numberFormat: string | null
  display: DisplayFormat | null
  styleId: string | null
  /** Excel address, provenance only (e.g. "Q40") */
  source: string | null
  mergedRange: string | null
  isMergeAnchor: boolean
}

export interface NormalizedTable {
  id: number | null
  sheetName: string
  sourceRange: string
  title: string | null
  shape: TableShape
  periodAxis: PeriodAxis
  headerRowCount: number
  labelColCount: number
  columns: TableColumn[]
  rows: TableRow[]
  cells: TableCell[]
  mergedRanges: string[]
  styles: Record<string, CellStyle>
  warnings: string[]
  meta: Record<string, unknown>
}

export interface TableSummary {
  id: number | null
  sheetName: string
  sourceRange: string
  title: string | null
  shape: TableShape
  periodAxis: PeriodAxis
  rowCount: number
  colCount: number
  periods: Period[]
  warnings: string[]
}

export interface RawFile {
  id: number
  originalFilename: string
  mimeType: string
  sizeBytes: number
  sha256: string
  createdAt: string
}

export interface ImportRecord {
  id: number
  department: Department
  parserVersion: string
  parsedAt: string
  summary: {
    filename?: string
    sheets?: string[]
    tableCount?: number
    periodLabels?: string[]
    shapes?: string[]
  }
  warnings: string[]
  rawFile: RawFile | null
  tables: TableSummary[]
}

export interface HealthInfo {
  status: string
  app: string
  parserVersion: string
  maxActivePresentations: number
  languages: Language[]
  defaultLanguage: Language
  translationProvider: string
}

export interface ApiError {
  code: string
  message: string
  detail?: Record<string, unknown>
}

/* -------------------------------------------------------------------------- *
 * Rich text (Issue Report cells) — a TipTap/ProseMirror document.
 * Images live inside the document, which is what lets a translation replace
 * only the text nodes and leave everything else untouched.
 * -------------------------------------------------------------------------- */
export interface RichMark {
  type: 'bold' | 'italic' | 'underline' | 'textStyle'
  attrs?: Record<string, unknown>
}

export interface RichNode {
  type: 'doc' | 'paragraph' | 'text' | 'hardBreak' | 'image' | 'bulletList' | 'listItem'
  text?: string
  marks?: RichMark[]
  attrs?: Record<string, unknown>
  content?: RichNode[]
}

export type RichDocument = RichNode & { type: 'doc' }
