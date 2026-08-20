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
/** What a cell / row / column *means*, independent of where it sits. */
export type SemanticType =
  | 'title'
  | 'period'
  | 'series'
  | 'category'
  | 'subcategory'
  | 'metric'
  | 'value'
  | 'label'
  | 'unknown'

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
  /** "Target" / "Result" / "Plan" — how the number was produced, never a metric */
  seriesType: string | null
  semantic: SemanticType
  isLabelColumn: boolean
  width: number | null
}

export interface TableRow {
  index: number
  sourceRow: number | null
  labelPath: string[]
  label: string
  level: number
  /** interpreted hierarchy: category > subcategory > metric */
  category: string | null
  subcategory: string | null
  metric: string | null
  /** a Target/Result row keeps its series meaning instead of faking a metric */
  seriesType: string | null
  semantic: SemanticType
  isHeaderRow: boolean
  period: Period | null
  height: number | null
}

export interface TableCell {
  row: number
  col: number
  role: CellRole
  semantic: SemanticType
  valueType: ValueType
  /** the value exactly as the workbook holds it ("3,000", "NA", "#DIV/0!") */
  rawValue: string | null
  /** the interpreted number — never a rewritten original */
  number: number | null
  text: string | null
  /** canonical rendering of `number` */
  displayValue: string | null
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
  department: Department | null
  /** label levels, outermost first */
  hierarchy: string[]
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
  hierarchy: string[]
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
  /** true when an identical file had already been parsed (no re-parse) */
  reused: boolean
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

/** Semantic projection of a table — periods, hierarchy and values. */
export interface InterpretationValue {
  period: string
  seriesType?: string | null
  metric?: string
  type: ValueType
  raw?: string | null
  value?: number | null
  display?: string | null
  error?: string | null
  source?: string | null
}

export interface InterpretationRow {
  category?: string | null
  subcategory?: string | null
  metric?: string | null
  seriesType?: string | null
  label?: string
  period?: string
  sourceRow?: number | null
  values: InterpretationValue[]
}

export interface Interpretation {
  department: Department | null
  sheet: string
  table: string | null
  sourceRange: string
  shape: TableShape
  periodAxis: PeriodAxis
  hierarchy: string[]
  periods: string[]
  rows: InterpretationRow[]
  warnings: string[]
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

/* -------------------------------------------------------------------------- *
 * Presentation model (contract only in Sprint 0 — served from Sprint 1 on).
 * -------------------------------------------------------------------------- */
export type PresentationStatus = 'draft' | 'ready' | 'archived' | 'trashed'
export type VersionStatus = 'draft' | 'published'
export type ChartKind = 'line' | 'bar' | 'grouped-bar' | 'kpi' | 'target-result'

export interface ChartDefinition {
  id: number
  orderIndex: number
  kind: ChartKind
  title: string | null
  subtitle: string | null
  tableDefinitionId: number | null
  /** series/periods selected by label, never by column index */
  config: Record<string, unknown>
}

export interface IssueReportCell {
  id: number
  rowId: number
  columnId: number
  doc: RichDocument
  align: string
  valign: string
}

export interface IssueReport {
  id: number
  department: Department
  orderIndex: number
  title: string
  language: Language
  columns: { id: number; index: number; title: string; width: number | null; align: string }[]
  rows: { id: number; index: number; height: number | null }[]
  cells: IssueReportCell[]
  config: Record<string, unknown>
}

export interface Asset {
  id: number
  url: string
  mimeType: string
  sizeBytes: number
  width: number | null
  height: number | null
}

export interface PresentationVersion {
  id: number
  number: number
  label: string | null
  status: VersionStatus
  notes: string | null
  createdAt: string
  publishedAt: string | null
  parentVersionId: number | null
}

export interface Presentation {
  id: number
  department: Department
  name: string
  periodLabel: string | null
  status: PresentationStatus
  createdAt: string
  updatedAt: string
  archivedAt: string | null
  trashedAt: string | null
  latestVersion: PresentationVersion | null
  versionCount: number
  issueCount: number
}

export interface PresentationModel {
  presentation: Presentation
  version: PresentationVersion
  imports: ImportRecord[]
  tables: TableSummary[]
  charts: ChartDefinition[]
  issueReports: IssueReport[]
  assets: Asset[]
  language: Language
}
