import { FileDown, Loader2, Presentation, Table2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Card, CardDescription } from '@/components/ui/card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Department as DepartmentCode, ExportRequest, ReportSummary } from '@/types/api'

const DEPARTMENTS: DepartmentCode[] = ['IQC', 'OQC', 'FIELD']

/** What each download button asks the backend to put in the file. */
const PARTS: Record<string, ExportRequest> = {
  report: { includeCharts: false, includeTables: false },
  charts: { includeTables: false, includeReport: false },
  tables: { includeCharts: false, includeReport: false },
}

/**
 * Every saved report, ready to take away.
 *
 * Kept out of the presentation screen on purpose: a meeting reads, it does not
 * download. Each line offers its three parts separately — the report, the
 * charts, the tables — plus the whole deck.
 */
export function Reports() {
  const { t } = useTranslation()
  const [reports, setReports] = useState<ReportSummary[]>([])
  const [filter, setFilter] = useState<DepartmentCode | 'all'>('all')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    void api
      .listReports(filter === 'all' ? undefined : filter)
      .then(setReports)
      .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)))
      .finally(() => setLoading(false))
  }, [filter])

  const download = async (versionId: number, part: keyof typeof PARTS | 'all', format: 'pdf' | 'ppt') => {
    const key = `${versionId}-${part}-${format}`
    setBusy(key)
    setError(null)
    try {
      const { blob, filename } = await api.exportView(
        versionId,
        format,
        part === 'all' ? {} : PARTS[part],
      )
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-brand-900">{t('reports.title')}</h1>
        <div className="flex gap-1">
          {(['all', ...DEPARTMENTS] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              className={cn(
                'rounded-lg px-3 py-1.5 text-sm font-medium',
                filter === value ? 'bg-brand-100 text-brand-800' : 'text-ink-500 hover:bg-brand-50',
              )}
            >
              {value === 'all' ? t('reports.all') : value}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <Card className="mb-6 border-critical/30 bg-critical/5">
          <CardDescription className="text-critical">{error}</CardDescription>
        </Card>
      )}

      {loading ? (
        <p className="flex items-center gap-2 text-sm text-ink-500">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          {t('common.loading')}
        </p>
      ) : reports.length === 0 ? (
        <Card>
          <CardDescription>{t('reports.empty')}</CardDescription>
        </Card>
      ) : (
        <div className="surface-card table-scroll p-0">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-500">
                <th className="px-4 py-3">{t('reports.department')}</th>
                <th className="px-4 py-3">{t('reports.version')}</th>
                <th className="px-4 py-3">{t('reports.reportTitle')}</th>
                <th className="px-4 py-3">{t('reports.size')}</th>
                <th className="px-4 py-3">{t('reports.updated')}</th>
                <th className="px-4 py-3">{t('reports.download')}</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr key={report.versionId} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-3 font-medium text-brand-900">{report.department}</td>
                  <td className="px-4 py-3 text-ink-700">
                    v{report.versionNumber} · {report.versionLabel ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-ink-900">{report.title || '—'}</td>
                  <td className="px-4 py-3 text-ink-500">
                    {t('reports.counts', {
                      columns: report.columnCount,
                      rows: report.rowCount,
                      images: report.imageCount,
                    })}
                  </td>
                  <td className="px-4 py-3 text-ink-500">
                    {report.updatedAt ? new Date(report.updatedAt).toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      <DownloadButton
                        label={t('reports.partReport')}
                        busy={busy === `${report.versionId}-report-pdf`}
                        onClick={() => void download(report.versionId, 'report', 'pdf')}
                      >
                        <FileDown className="h-3.5 w-3.5" aria-hidden />
                      </DownloadButton>
                      <DownloadButton
                        label={t('reports.partCharts')}
                        busy={busy === `${report.versionId}-charts-pdf`}
                        onClick={() => void download(report.versionId, 'charts', 'pdf')}
                      >
                        <Presentation className="h-3.5 w-3.5" aria-hidden />
                      </DownloadButton>
                      <DownloadButton
                        label={t('reports.partTables')}
                        busy={busy === `${report.versionId}-tables-pdf`}
                        onClick={() => void download(report.versionId, 'tables', 'pdf')}
                      >
                        <Table2 className="h-3.5 w-3.5" aria-hidden />
                      </DownloadButton>
                      <DownloadButton
                        label={t('reports.partAllPpt')}
                        busy={busy === `${report.versionId}-all-ppt`}
                        onClick={() => void download(report.versionId, 'all', 'ppt')}
                      >
                        <Presentation className="h-3.5 w-3.5" aria-hidden />
                      </DownloadButton>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function DownloadButton({
  children,
  label,
  busy,
  onClick,
}: {
  children: React.ReactNode
  label: string
  busy: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs text-ink-700 hover:border-brand-300 hover:text-brand-800 disabled:opacity-50"
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : children}
      {label}
    </button>
  )
}
