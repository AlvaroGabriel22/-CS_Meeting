import { Check, Loader2, Upload } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'

import { ReportBuilder } from '@/components/report/ReportBuilder'
import { VersionSelector } from '@/components/executive/VersionSelector'
import { Card, CardDescription } from '@/components/ui/card'
import { Toast } from '@/components/ui/toast'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type {
  Chart,
  Department as DepartmentCode,
  ImportRecord,
  PresentationVersion,
  ReportContent,
  VersionView,
} from '@/types/api'

const VALID: DepartmentCode[] = ['IQC', 'OQC', 'FIELD']
type Tab = 'upload' | 'titles' | 'report'

/**
 * Everything that changes a department lives here, and only here.
 *
 * The presentation screen is for reading: it carries no upload button and no
 * edit button. This screen carries all three — the raw-data upload, the names
 * of the charts and tables, and the report editor — and every department has
 * the same three, with its own content.
 */
export function DepartmentConfig() {
  const { t } = useTranslation()
  const { code } = useParams<{ code: string }>()
  const department = (VALID.find((item) => item === code) ?? 'IQC') as DepartmentCode

  const [tab, setTab] = useState<Tab>('upload')
  const [versions, setVersions] = useState<PresentationVersion[]>([])
  const [versionId, setVersionId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadVersions = useCallback(async () => {
    const presentations = await api.listPresentations(department)
    const found = presentations[0]
    if (!found) {
      setVersions([])
      setVersionId(null)
      return
    }
    const list = await api.listVersions(found.id)
    setVersions(list)
    const newest = [...list].sort((a, b) => a.number - b.number).at(-1)
    setVersionId((current) => current ?? newest?.id ?? null)
  }, [department])

  useEffect(() => {
    setVersionId(null)
    void loadVersions().catch((cause) =>
      setError(cause instanceof Error ? cause.message : String(cause)),
    )
  }, [loadVersions])

  const tabClass = (value: Tab) =>
    cn(
      'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
      tab === value ? 'bg-brand-100 text-brand-800' : 'text-ink-500 hover:bg-brand-50',
    )

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <span className="text-xs font-semibold uppercase tracking-widest text-brand-500">
            {t(`department.${department}`)}
          </span>
          <h1 className="text-2xl font-semibold text-brand-900">{t('config.title')}</h1>
        </div>
        {versions.length > 0 && (
          <VersionSelector versions={versions} value={versionId} onChange={setVersionId} />
        )}
      </header>

      <nav className="mb-6 flex gap-1 border-b border-line pb-2">
        <button type="button" className={tabClass('upload')} onClick={() => setTab('upload')}>
          {t('config.upload')}
        </button>
        <button type="button" className={tabClass('titles')} onClick={() => setTab('titles')}>
          {t('config.titles')}
        </button>
        <button type="button" className={tabClass('report')} onClick={() => setTab('report')}>
          {t('config.report')}
        </button>
      </nav>

      {error && (
        <Card className="mb-6 border-critical/30 bg-critical/5">
          <CardDescription className="text-critical">{error}</CardDescription>
        </Card>
      )}

      {tab === 'upload' && (
        <UploadPanel department={department} onImported={() => void loadVersions()} />
      )}
      {tab === 'titles' && versionId && (
        <TitlesPanel department={department} versionId={versionId} />
      )}
      {tab === 'report' && versionId && <ReportPanel versionId={versionId} />}
      {tab !== 'upload' && !versionId && (
        <Card>
          <CardDescription>{t('config.uploadFirst')}</CardDescription>
        </Card>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Upload
// --------------------------------------------------------------------------- //
function UploadPanel({
  department,
  onImported,
}: {
  department: DepartmentCode
  onImported: () => void
}) {
  const { t } = useTranslation()
  const fileInput = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<ImportRecord | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const choose = async (file: File) => {
    setBusy(true)
    setSaved(false)
    setError(null)
    try {
      setPreview(await api.uploadRawData(department, file, { createVersion: false }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  const confirm = async () => {
    if (!preview) return
    setBusy(true)
    try {
      await api.uploadRawData(department, fileInput.current!.files![0], { createVersion: true })
      setSaved(true)
      onImported()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="surface-card space-y-4 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={fileInput}
          type="file"
          accept=".xlsx,.xlsm"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) void choose(file)
          }}
        />
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-60"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Upload className="h-4 w-4" aria-hidden />
          )}
          {t('config.chooseFile')}
        </button>
        <span className="text-sm text-ink-500">
          {fileInput.current?.files?.[0]?.name ?? t('config.noFile')}
        </span>
      </div>

      {error && <p className="text-sm text-critical">{error}</p>}

      {preview && (
        <div className="space-y-3">
          <dl className="grid gap-3 sm:grid-cols-3">
            <Fact label={t('config.tablesDetected')} value={preview.tableNames.join(' · ')} />
            <Fact label={t('config.periodsDetected')} value={preview.periods.join(' · ')} />
            <Fact label={t('config.parserVersion')} value={preview.parserVersion} />
          </dl>
          <button
            type="button"
            onClick={() => void confirm()}
            disabled={busy || saved}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-60"
          >
            <Check className="h-4 w-4" aria-hidden />
            {t('config.saveVersion')}
          </button>
          <Toast show={saved} message={t('config.saved')} />
        </div>
      )}
    </section>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-brand-50 p-3">
      <dt className="text-xs uppercase tracking-wide text-ink-500">{label}</dt>
      <dd className="mt-1 text-sm font-semibold text-brand-900">{value || '—'}</dd>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Titles
// --------------------------------------------------------------------------- //
function TitlesPanel({
  department,
  versionId,
}: {
  department: DepartmentCode
  versionId: number
}) {
  const { t } = useTranslation()
  const [charts, setCharts] = useState<Chart[]>([])
  const [view, setView] = useState<VersionView | null>(null)
  const [chartTitles, setChartTitles] = useState<Record<string, string>>({})
  const [tableTitles, setTableTitles] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    void (async () => {
      const [chartData, versionView, settings] = await Promise.all([
        api.getCharts(versionId),
        api.getVersionView(versionId),
        api.getDepartmentSettings(department),
      ])
      setCharts(chartData.charts)
      setView(versionView)
      setChartTitles(settings.chartTitles)
      setTableTitles(settings.tableTitles)
    })()
  }, [department, versionId])

  const save = async () => {
    await api.saveDepartmentSettings(department, { chartTitles, tableTitles })
    setSaved(true)
    window.setTimeout(() => setSaved(false), 2000)
  }

  return (
    <section className="surface-card space-y-5 p-5">
      <p className="text-sm text-ink-500">{t('config.titlesHint')}</p>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-brand-900">{t('config.chartTitles')}</h3>
          {charts.map((chart) => (
            <TitleField
              key={chart.table}
              name={chart.table}
              value={chartTitles[chart.table] ?? ''}
              onChange={(value) => setChartTitles({ ...chartTitles, [chart.table]: value })}
            />
          ))}
        </div>
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-brand-900">{t('config.tableTitles')}</h3>
          {(view?.tables ?? []).map((table) => (
            <TitleField
              key={table.sheet + table.sourceRange}
              name={table.title ?? table.sheet}
              value={tableTitles[table.title ?? table.sheet] ?? ''}
              onChange={(value) =>
                setTableTitles({ ...tableTitles, [table.title ?? table.sheet]: value })
              }
            />
          ))}
        </div>
      </div>

      <button
        type="button"
        onClick={() => void save()}
        className="inline-flex items-center gap-2 rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800"
      >
        <Check className="h-4 w-4" aria-hidden />
        {t('common.save')}
      </button>
      <Toast show={saved} message={t('common.saved')} />
    </section>
  )
}

function TitleField({
  name,
  value,
  onChange,
}: {
  name: string
  value: string
  onChange: (value: string) => void
}) {
  const { t } = useTranslation()
  return (
    <label className="flex items-center gap-3">
      <span className="w-16 shrink-0 font-mono text-xs text-ink-500">{name}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={t('config.keepWorkbookName', { name })}
        className="w-full rounded-lg border border-line px-3 py-1.5 text-sm outline-none focus:border-brand-400"
      />
    </label>
  )
}

// --------------------------------------------------------------------------- //
// Report
// --------------------------------------------------------------------------- //
function ReportPanel({ versionId }: { versionId: number }) {
  const { t, i18n } = useTranslation()
  const [content, setContent] = useState<ReportContent | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSaved(false)
    void api
      .getReport(versionId)
      .then((report) => setContent(report.content))
      .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)))
  }, [versionId])

  const save = async () => {
    if (!content) return
    setBusy(true)
    setError(null)
    try {
      const report = await api.saveReport(versionId, { content, language: i18n.language })
      setContent(report.content)
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2000)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  if (!content) {
    return (
      <p className="flex items-center gap-2 text-sm text-ink-500">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        {t('common.loading')}
      </p>
    )
  }

  return (
    <section className="surface-card space-y-4 p-5">
      <ReportBuilder versionId={versionId} content={content} onChange={setContent} />
      {error && <p className="text-sm text-critical">{error}</p>}
      <button
        type="button"
        onClick={() => void save()}
        disabled={busy}
        className="inline-flex items-center gap-2 rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-60"
      >
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        ) : (
          <Check className="h-4 w-4" aria-hidden />
        )}
        {t('common.save')}
      </button>
      <Toast show={saved} message={t('common.saved')} />
    </section>
  )
}
