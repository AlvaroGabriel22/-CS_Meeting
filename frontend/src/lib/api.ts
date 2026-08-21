import type {
  ChartsResponse,
  Department,
  ExportRequest,
  HealthInfo,
  ImportRecord,
  Interpretation,
  NormalizedTable,
  Presentation,
  PresentationVersion,
  DepartmentSettings,
  AuthoredTranslation,
  Report,
  ReportSummary,
  UploadedImage,
  SeriesOrder,
  SeriesResponse,
  TableView,
  TranslationStatus,
  VersionView,
} from '@/types/api'

const BASE = import.meta.env.VITE_API_BASE ?? ''

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({ message: response.statusText }))
    throw Object.assign(new Error(body.message ?? 'Request failed'), { api: body })
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<HealthInfo>('/api/health'),

  listImports: (department?: Department) =>
    request<ImportRecord[]>(`/api/imports${department ? `?department=${department}` : ''}`),

  getImport: (id: number) => request<ImportRecord>(`/api/imports/${id}`),

  getTable: (importId: number, tableId: number) =>
    request<NormalizedTable>(`/api/imports/${importId}/tables/${tableId}`),

  /** Light semantic view: periods, hierarchy and values — no cells. */
  getInterpretation: (importId: number, tableId: number) =>
    request<Interpretation>(`/api/imports/${importId}/tables/${tableId}/interpretation`),

  /**
   * Upload a raw workbook.
   *
   * `createVersion: false` parses and returns the preview without saving a
   * snapshot — the import screen uses it before the user confirms.  Confirming
   * afterwards is free: the identical file is not parsed twice.
   */
  uploadRawData: (
    department: Department,
    file: File,
    options: { createVersion?: boolean } = {},
  ) => {
    const form = new FormData()
    form.append('department', department)
    form.append('file', file)
    form.append('createVersion', String(options.createVersion ?? true))
    return request<ImportRecord>('/api/uploads', { method: 'POST', body: form })
  },

  listPresentations: (department?: Department) =>
    request<Presentation[]>(`/api/presentations${department ? `?department=${department}` : ''}`),

  listVersions: (presentationId: number) =>
    request<PresentationVersion[]>(`/api/presentations/${presentationId}/versions`),

  /** One table, ready to draw (merges as spans, hierarchy as depth). */
  getTableView: (importId: number, tableId: number) =>
    request<TableView>(`/api/imports/${importId}/tables/${tableId}/view`),

  /** A whole snapshot, rendered exactly as it was saved. */
  getVersionView: (versionId: number) =>
    request<VersionView>(`/api/versions/${versionId}/view`),

  /** Chart-ready series of one snapshot, plus the selector options it offers. */
  getSeries: (
    versionId: number,
    params: {
      table?: string
      category?: string
      subcategory?: string
      metric?: string
      order?: SeriesOrder
    } = {},
  ) => request<SeriesResponse>(`/api/versions/${versionId}/analytics/series${query(params)}`),

  /** One chart per table: bars per category, a line over them. */
  getCharts: (versionId: number) => request<ChartsResponse>(`/api/versions/${versionId}/charts`),

  /** The report a person wrote about this snapshot. */
  getReport: (versionId: number) => request<Report>(`/api/versions/${versionId}/report`),

  saveReport: (
    versionId: number,
    payload: { content: unknown; language?: string },
  ) =>
    request<Report>(`/api/versions/${versionId}/report`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  /** Upload an image so the author can place it in a cell. */
  uploadReportImage: (versionId: number, file: File, caption?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (caption) form.append('caption', caption)
    return request<UploadedImage>(`/api/versions/${versionId}/report/media`, {
      method: 'POST',
      body: form,
    })
  },

  /** Every saved report, newest first. */
  listReports: (department?: Department) =>
    request<ReportSummary[]>(`/api/reports${department ? `?department=${department}` : ''}`),

  /** What this department's charts and tables are called. */
  getDepartmentSettings: (code: Department) =>
    request<DepartmentSettings>(`/api/departments/${code}/settings`),

  saveDepartmentSettings: (
    code: Department,
    payload: {
      chartTitles: Record<string, string>
      tableTitles: Record<string, string>
      chartSeries: Record<string, { bars: string[]; line: string | null }>
    },
  ) =>
    request<DepartmentSettings>(`/api/departments/${code}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  /**
   * Translate everything a person wrote: the report and the titles they gave
   * the charts and tables. The only content AI ever touches.
   *
   * The answer carries the original beside the translation; nothing stored is
   * modified either way.
   */
  translateAuthored: (
    versionId: number,
    payload: { targetLanguage: string; sourceLanguage?: string },
  ) =>
    request<AuthoredTranslation>(`/api/versions/${versionId}/translation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  /** Which translation provider the backend is configured with. */
  getTranslationStatus: () => request<TranslationStatus>('/api/translation/status'),

  /** Export what the page is showing; the browser downloads the file. */
  exportView: async (versionId: number, format: 'pdf' | 'ppt', payload: ExportRequest) => {
    const response = await fetch(`${BASE}/api/versions/${versionId}/export/${format}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({ message: response.statusText }))
      throw Object.assign(new Error(body.message ?? 'Export failed'), { api: body })
    }
    const disposition = response.headers.get('content-disposition') ?? ''
    const match = /filename="?([^";]+)"?/.exec(disposition)
    return { blob: await response.blob(), filename: match?.[1] ?? `export.${format}` }
  }
}
