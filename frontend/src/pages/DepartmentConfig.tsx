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
  ChartSeriesChoice,
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
  const [chartSeries, setChartSeries] = useState<Record<string, ChartSeriesChoice>>({})
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    const [chartData, versionView, settings] = await Promise.all([
      api.getCharts(versionId),
      api.getVersionView(versionId),
      api.getDepartmentSettings(department),
    ])
    setCharts(chartData.charts)
    setView(versionView)
    // defensive: a backend that predates the composition must not blank the page
    setChartTitles(settings.chartTitles ?? {})
    setTableTitles(settings.tableTitles ?? {})
    setChartSeries(settings.chartSeries ?? {})
  }, [department, versionId])

  useEffect(() => {
    void load()
  }, [load])

  const save = async () => {
    await api.saveDepartmentSettings(department, { chartTitles, tableTitles, chartSeries })
    setSaved(true)
    window.setTimeout(() => setSaved(false), 2000)
    // the chart is redrawn from what was just stored, so the preview is the truth
    await load()
  }

  /** The composition of one chart, defaulting to what it is drawing today.
   *
   * Settings written when a table meant exactly one chart are keyed by the
   * table's name, so both keys are looked up before falling back.
   */
  const choiceOf = (chart: Chart): ChartSeriesChoice =>
    (chartSeries ?? {})[chart.id] ??
    (chartSeries ?? {})[chart.table] ?? {
      bars: chart.bars.map((series) => series.key),
      line: chart.line?.key ?? null,
      enabled: chart.enabled,
    }

  const setChoice = (id: string, choice: ChartSeriesChoice) =>
    setChartSeries({ ...chartSeries, [id]: choice })

  return (
    <section className="surface-card space-y-6 p-5">
      <p className="text-sm text-ink-500">{t('config.titlesHint')}</p>

      <div className="space-y-5">
        <h3 className="text-sm font-semibold text-brand-900">{t('config.chartTitles')}</h3>
        {charts.map((chart) => (
          <ChartPanel
            key={chart.id}
            chart={chart}
            title={chartTitles[chart.id] ?? chartTitles[chart.table] ?? ''}
            choice={choiceOf(chart)}
            onTitle={(value) => setChartTitles({ ...chartTitles, [chart.id]: value })}
            onChoice={(choice) => setChoice(chart.id, choice)}
            onReset={() => {
              const next = { ...chartSeries }
              delete next[chart.id]
              delete next[chart.table]
              setChartSeries(next)
            }}
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

/**
 * One chart's name and composition.
 *
 * The rows on offer are the rows the workbook has — every category, sub-group
 * and metric of that table. Choosing changes *which* of them is drawn and
 * nothing else: the numbers are always the file's.
 */
function ChartPanel({
  chart,
  title,
  choice,
  onTitle,
  onChoice,
  onReset,
}: {
  chart: Chart
  title: string
  choice: ChartSeriesChoice
  onTitle: (value: string) => void
  onChoice: (choice: ChartSeriesChoice) => void
  onReset: () => void
}) {
  const { t } = useTranslation()

  // the stack follows the workbook's own row order, not the order of clicking:
  // the chart should read like the table it came from
  const order = new Map(chart.available.map((option, index) => [option.key, index]))
  const toggleBar = (key: string) => {
    const next = choice.bars.includes(key)
      ? choice.bars.filter((item) => item !== key)
      : [...choice.bars, key]
    next.sort((a, b) => (order.get(a) ?? 0) - (order.get(b) ?? 0))
    onChoice({ ...choice, bars: next })
  }

  // one table can hold several charts, so a panel is named by the model it
  // plots rather than by the table it came from
  const name =
    chart.kind === 'pair'
      ? [chart.category, chart.subcategory].filter(Boolean).join(' · ') || chart.table
      : chart.table
  const shown = choice.enabled ?? chart.enabled

  return (
    <article className="rounded-lg border border-line p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-mono text-xs text-ink-500">{name}</span>
        <div className="flex items-center gap-4">
          {chart.kind === 'pair' && (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-600">
              <input
                type="checkbox"
                checked={shown}
                onChange={(event) => onChoice({ ...choice, enabled: event.target.checked })}
                className="h-3.5 w-3.5"
              />
              {t('config.showChart')}
            </label>
          )}
          {chart.configured && (
            <button
              type="button"
              onClick={onReset}
              className="text-xs font-medium text-brand-600 hover:text-brand-800"
            >
              {t('config.resetChart')}
            </button>
          )}
        </div>
      </div>

      <input
        value={title}
        onChange={(event) => onTitle(event.target.value)}
        placeholder={t('config.keepWorkbookName', { name })}
        className="mt-2 w-full rounded-lg border border-line px-3 py-1.5 text-sm outline-none focus:border-brand-400"
      />

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-500">
            {t('config.bars')}
          </p>
          <ul className="max-h-56 space-y-1 overflow-y-auto pr-1">
            {chart.available.map((option) => (
              <li key={option.key}>
                <label className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-brand-50">
                  <input
                    type="checkbox"
                    checked={choice.bars.includes(option.key)}
                    onChange={() => toggleBar(option.key)}
                    className="h-3.5 w-3.5"
                  />
                  <span className="text-ink-700">{option.path}</span>
                </label>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-500">
            {t('config.line')}
          </p>
          <select
            value={choice.line ?? ''}
            onChange={(event) => onChoice({ ...choice, line: event.target.value || null })}
            className="w-full rounded-lg border border-line px-3 py-1.5 text-sm outline-none focus:border-brand-400"
          >
            <option value="">{t('config.noLine')}</option>
            {chart.available.map((option) => (
              <option key={option.key} value={option.key}>
                {option.path}
              </option>
            ))}
          </select>
          <p className="mt-3 text-xs text-ink-500">{t('config.chartHint')}</p>
        </div>
      </div>
    </article>
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
