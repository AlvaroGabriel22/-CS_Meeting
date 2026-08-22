/**
 * Backend contract (mirrors backend/app/schemas/*).
 *
 * Keep both sides in sync — this file is the only place the frontend is
 * allowed to describe server data.
 */

export type Department = 'IQC' | 'OQC' | 'FIELD'
export type Language = 'en' | 'pt-BR' | 'ko'

export type PeriodKind = 'year' | 'quarter' | 'month' | 'week' | 'day' | 'unknown'
export type Quarter = '1Q' | '2Q' | '3Q' | '4Q'
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
  /** canonical quarter label — "1Q" | "2Q" | "3Q" | "4Q" */
  quarter: Quarter | null
  /** the same quarter as an ordinal, for arithmetic */
  quarterNumber: number | null
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
  success: boolean
  id: number
  /** true when an identical file had already been parsed (no re-parse) */
  reused: boolean
  department: Department
  parserVersion: string
  parsedAt: string
  /** the snapshot this upload created (null when createVersion=false) */
  presentationId: number | null
  versionId: number | null
  versionNumber: number | null
  /** detected table names, in file order — "TTL", "SEC", "TNP" */
  tableNames: string[]
  /** period labels, in file order — "'25", "'26", "1Q", "2Q", "3Q", "Aug" */
  periods: string[]
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
  presentationId: number | null
  number: number
  label: string | null
  status: VersionStatus
  notes: string | null
  createdAt: string
  publishedAt: string | null
  parentVersionId: number | null
  summary: {
    parserVersion?: string
    tableNames?: string[]
    periodLabels?: string[]
    tableCount?: number
    rawFile?: string | null
  }
  warnings: string[]
  importIds: number[]
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

/* -------------------------------------------------------------------------- *
 * Render model (Sprint 2) — the table already prepared for display.
 * The UI draws this as it comes: merges arrive as spans, hierarchy as depth,
 * periods as whatever the file holds.  No structure is re-derived here.
 * -------------------------------------------------------------------------- */
export type CellKind = 'corner' | 'period' | 'label' | 'value' | 'empty'
export type BorderSide = 'top' | 'right' | 'bottom' | 'left'

export interface RenderCell {
  row: number
  col: number
  rowSpan: number
  colSpan: number
  kind: CellKind
  semantic: string
  /** already formatted for reading — never recomputed on the client */
  text: string
  value: number | null
  valueType: ValueType
  align: string
  bold: boolean
  fillColor: string | null
  textColor: string | null
  borders: BorderSide[]
  wrap: boolean
  indent: number
  isHeadline: boolean
  /** what the parser inferred for a cell the workbook leaves empty */
  inferredText: string | null
  source: string | null
  mergedRange: string | null
}

export interface RenderColumn {
  index: number
  kind: 'label' | 'period'
  label: string
  period: Period | null
  seriesType: string | null
  sourceColumn: string | null
  width: number | null
}

export interface RenderRow {
  index: number
  kind: 'header' | 'data'
  semantic: string
  category: string | null
  subcategory: string | null
  metric: string | null
  seriesType: string | null
  block: number
  isHeadline: boolean
  depth: number
  inferred: string[]
  sourceRow: number | null
  height: number | null
  cells: RenderCell[]
}

export interface TableView {
  id: number | null
  title: string | null
  department: Department | null
  sheet: string
  sourceRange: string
  hierarchy: string[]
  headerRowCount: number
  labelColumnCount: number
  columnCount: number
  rowCount: number
  periods: Period[]
  columns: RenderColumn[]
  rows: RenderRow[]
  warnings: string[]
  meta: {
    reportingYear?: number | null
    blocks?: number | null
    /** metadata only — never drawn as a label (the value *is* the metric) */
    headlineMetric?: string | null
    headlineConfirmed?: boolean
  }
}

export interface VersionView {
  version: PresentationVersion
  department: Department
  tables: TableView[]
}

/* -------------------------------------------------------------------------- *
 * Analytics (Sprint 3) — charts, period comparison, version comparison.
 * Everything is expressed in model terms; the origin cell travels along so any
 * number on a chart can be traced back to the workbook.
 * -------------------------------------------------------------------------- */
/** the sign of a subtraction — never a statement about whether it is good */
export type Direction = 'up' | 'down' | 'flat' | 'unknown'
export type DeltaStatus = 'ok' | 'missing_a' | 'missing_b' | 'undefined_percent'
export type SeriesOrder = 'file' | 'chronological'

export interface SeriesSelector {
  table: string | null
  category: string | null
  subcategory: string | null
  metric: string | null
  seriesType: string | null
}

export interface SeriesPoint {
  period: Period
  value: number | null
  display: string | null
  valueType: ValueType
  /** provenance: the cell this number came from */
  source: string | null
}

export interface Series {
  key: string
  label: string
  selector: SeriesSelector
  sheet: string | null
  sourceRange: string | null
  tableId: number | null
  points: SeriesPoint[]
}

export interface SelectorOptions {
  tables: string[]
  categories: string[]
  subcategories: string[]
  metrics: string[]
  seriesTypes: string[]
}

export interface SeriesResponse {
  versionId: number
  department: Department
  order: SeriesOrder
  periods: Period[]
  series: Series[]
  options: SelectorOptions
}

/* -------------------------------------------------------------------------- *
 * Charts — one per table, drawn from values the workbook already holds.
 * -------------------------------------------------------------------------- */
export interface ChartPoint {
  period: string
  /** null where the file has a gap — never a zero */
  value: number | null
  display: string | null
  /** provenance: the cell the number came from */
  source: string | null
  /** provenance of a shared number, which no single cell holds (ADR-0046) */
  derivedFrom?: { whole: string | null; weight: string | null; weightTotal: string | null } | null
}

export interface ChartSeries {
  key: string
  label: string
  points: ChartPoint[]
}

/** One row of the table a chart could plot. */
export interface ChartOption {
  key: string
  /** the most specific name — `SKD`, `Local` */
  label: string
  /** every level, so two `SKD` rows can be told apart */
  path: string
  category: string | null
  subcategory: string | null
  metric: string | null
  /** `Target` / `Result`, where the row is named by what it is */
  seriesType?: string | null
}

/** `components` — the parts of a whole; `pair` — a result against its target. */
export type ChartShape = 'components' | 'pair'

export interface Chart {
  /** the chart's own name: the table's, unless one table holds several */
  id: string
  kind: ChartShape
  table: string
  /** the model a pair chart plots */
  category?: string | null
  subcategory?: string | null
  /** the name given in the department settings, if any */
  title: string | null
  metric: string | null
  sheet: string
  sourceRange: string
  /** true when the bars are the parts of the whole and stack into it */
  stacked: boolean
  /** true when the presenter chose what to plot instead of the default */
  configured: boolean
  /** false for a chart the workbook offers but the presenter left out */
  enabled: boolean
  defaultEnabled: boolean
  periods: Period[]
  bars: ChartSeries[]
  line: ChartSeries | null
  /** indices where the period axis changes granularity and the line is cut */
  breaks: number[]
  /** true when the bars are the whole shared out among its parts (ADR-0046) */
  shared: boolean
  share: { whole: string; weight: string } | null
  /** everything this table could plot, for the configuration screen */
  available: ChartOption[]
}

export interface ChartsResponse {
  versionId: number
  department: Department
  metric: string | null
  charts: Chart[]
}

/* -------------------------------------------------------------------------- *
 * The report — a table the author builds by hand.
 * -------------------------------------------------------------------------- */
export type BlockAlign = 'left' | 'center' | 'right'
export type BlockType = 'text' | 'image' | 'shape'
export type ShapeKind = 'rectangle' | 'circle' | 'line' | 'arrow' | 'divider'
export type TextSize = 'small' | 'normal' | 'large' | 'heading'

export interface ReportBlock {
  id: string
  type: BlockType
  align: BlockAlign
  /** text */
  text?: string | null
  bold?: boolean | null
  italic?: boolean | null
  size?: TextSize | number | null
  /** image */
  assetId?: number | null
  url?: string | null
  caption?: string | null
  width?: number | null
  /** shape */
  shape?: ShapeKind | null
  color?: string | null
}

export interface ReportColumn {
  id: string
  name: string
}

export interface ReportRow {
  id: string
  /** column id -> the blocks of that cell, in the author's order */
  cells: Record<string, ReportBlock[]>
}

export interface ReportContent {
  title: string
  columns: ReportColumn[]
  rows: ReportRow[]
}

export interface ReportMedia {
  id: number
  assetId: number
  url: string
  mimeType: string
  sizeBytes: number
  caption: string | null
}

export interface Report {
  versionId: number
  department: Department
  versionNumber: number | null
  versionLabel: string | null
  language: string
  content: ReportContent
  text: string
  translationKey: string | null
  media: ReportMedia[]
  updatedAt: string | null
}

/**
 * Everything a person wrote, in another language.
 *
 * The report and the titles given to charts and tables are the only strings
 * the system cannot ship in a language bundle — nobody knows them before
 * someone types them. Everything else on the page is interface text or a label
 * the workbook carries, and neither is ever sent to a provider.
 */
export interface AuthoredTranslation {
  versionId: number
  department: Department
  sourceLanguage: string
  targetLanguage: string
  provider: string
  model: string | null
  /** the author's report, unchanged — always available */
  original: ReportContent
  translated: ReportContent
  chartTitles: Record<string, string>
  tableTitles: Record<string, string>
  stringCount: number
  cachedCount: number
  rejectedCount: number
}

export interface ReportSummary {
  versionId: number
  department: Department
  versionNumber: number | null
  versionLabel: string | null
  title: string
  columnCount: number
  rowCount: number
  imageCount: number
  language: string
  updatedAt: string | null
}

export interface UploadedImage {
  assetId: number
  url: string
  mimeType: string
  sizeBytes: number
}

/** What one chart plots, when the presenter chose it. */
export interface ChartSeriesChoice {
  bars: string[]
  line: string | null
  /** whether the chart is shown at all; null means "as the department decides" */
  enabled?: boolean | null
}

export interface DepartmentSettings {
  department: Department
  chartTitles: Record<string, string>
  tableTitles: Record<string, string>
  /** chart id -> the composition chosen for it */
  chartSeries: Record<string, ChartSeriesChoice>
}

/** The workbook's vocabulary, rendered for one language (ADR-0044). */
export interface Glossary {
  language: string
  /** term as the workbook writes it -> how it reads */
  terms: Record<string, string>
  /** terms deliberately left alone in every language */
  universal: string[]
}

export interface TranslationStatus {
  provider: string
  model: string | null
  languages: string[]
  defaultLanguage: string
  /** false when no provider is configured: text is shown as written */
  active: boolean
}

export interface ExportRequest {
  includeCharts?: boolean
  includeTables?: boolean
  includeReport?: boolean
  /** the language the report is being read in */
  language?: string
  translate?: boolean
}
