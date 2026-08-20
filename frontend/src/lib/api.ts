import type {
  Department,
  HealthInfo,
  ImportRecord,
  Interpretation,
  NormalizedTable,
  Presentation,
  PresentationVersion,
} from '@/types/api'

const BASE = import.meta.env.VITE_API_BASE ?? ''

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
}
