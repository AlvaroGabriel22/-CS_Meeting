import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import { DepartmentCharts } from '@/components/charts/DepartmentCharts'
import { ReportView } from '@/components/report/ReportView'
import { IQCTable } from '@/components/table/IQCTable'
import { Card, CardDescription } from '@/components/ui/card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type {
  Chart,
  Department as DepartmentCode,
  ReportContent,
  VersionView,
} from '@/types/api'

const VALID: DepartmentCode[] = ['IQC', 'OQC', 'FIELD']

/**
 * The department page: three containers, in this order.
 *
 *   charts → tables → report
 *
 * The charts and the tables are the workbook, drawn as it was calculated. The
 * report is the table a person built by hand, in the configuration screen.
 *
 * This screen only reads. There is no upload button, no edit button and no
 * version selector — those live in the configuration — and it always shows the
 * newest snapshot, which is what a meeting is about. The one automatic thing
 * that happens here is translation: choosing another language translates the
 * report the author wrote, because the system cannot ship that text in advance.
 */
export function Department() {
  const { t, i18n } = useTranslation()
  const { code } = useParams<{ code: string }>()
  const department = (VALID.find((item) => item === code) ?? 'IQC') as DepartmentCode

  const [versionId, setVersionId] = useState<number | null>(null)
  const [charts, setCharts] = useState<Chart[]>([])
  const [view, setView] = useState<VersionView | null>(null)
  const [report, setReport] = useState<ReportContent | null>(null)
  const [tableTitles, setTableTitles] = useState<Record<string, string>>({})
  const [chartTitles, setChartTitles] = useState<Record<string, string>>({})
  const [reportLanguage, setReportLanguage] = useState<string>('en')
  const [translating, setTranslating] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // which versions exist, and which one are we reading?
  useEffect(() => {
    let active = true
    setLoading(true)
    setVersionId(null)
    setError(null)

    void (async () => {
      try {
        const presentations = await api.listPresentations(department)
        if (!active) return
        const found = presentations[0]
        if (!found) {
          setLoading(false)
          return
        }
        const list = await api.listVersions(found.id)
        if (!active) return
        // the newest snapshot, whichever order the API listed them in
        const newest = [...list].sort((a, b) => a.number - b.number).at(-1)
        setVersionId(newest?.id ?? null)
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        if (active) setLoading(false)
      }
    })()

    return () => {
      active = false
    }
  }, [department])

  // the snapshot drives both containers above the report
  useEffect(() => {
    if (!versionId) return
    let active = true
    setLoading(true)

    void (async () => {
      try {
        const [chartData, versionView, reportData, settings] = await Promise.all([
          api.getCharts(versionId),
          api.getVersionView(versionId),
          api.getReport(versionId),
          api.getDepartmentSettings(department),
        ])
        if (!active) return
        setTableTitles(settings.tableTitles)
        setChartTitles(settings.chartTitles)
        setCharts(chartData.charts)
        setView(versionView)
        setReport(reportData.content)
        setReportLanguage(reportData.language)
        setError(null)
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        if (active) setLoading(false)
      }
    })()

    return () => {
      active = false
    }
  }, [versionId, department])

  // The interface ships in three languages; what a person *wrote* does not.
  // Switching language therefore sends the report and the titles they typed to
  // the translation provider, and nothing else on the page.
  useEffect(() => {
    if (!versionId || !report) return
    if (i18n.language === reportLanguage) return

    let active = true
    setTranslating(true)
    void api
      .translateAuthored(versionId, { targetLanguage: i18n.language })
      .then((answer) => {
        if (!active) return
        setReport(answer.translated)
        setChartTitles(answer.chartTitles)
        setTableTitles(answer.tableTitles)
      })
      .catch(() => undefined) // no provider configured: the original stays
      .finally(() => active && setTranslating(false))

    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i18n.language, versionId, reportLanguage])

  const hasData = Boolean(versionId && view)
  const hasReport = Boolean(report && (report.title || report.columns.length))

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-8">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold text-brand-900">
          {t(`department.${department}_full`)}
        </h1>
      </header>

      {error && (
        <Card className="mb-6 border-critical/30 bg-critical/5">
          <CardDescription className="text-critical">{error}</CardDescription>
        </Card>
      )}

      {loading && !hasData && (
        <p className="flex items-center gap-2 text-sm text-ink-500">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          {t('common.loading')}
        </p>
      )}

      {!loading && !hasData && !error && (
        <Card>
          <CardDescription className="flex flex-wrap items-center gap-2">
            {t('department.emptyTables')}
            <Link
              to={`/department/${department}/config`}
              className="font-medium text-brand-600 hover:text-brand-800"
            >
              {t('config.title')} →
            </Link>
          </CardDescription>
        </Card>
      )}

      {hasData && (
        <div className="space-y-6">
          <DepartmentCharts charts={charts} titles={chartTitles} />

          <div className="surface-card grid gap-4 p-4 lg:grid-cols-3">
            {view?.tables.map((item) => (
              <IQCTable
                key={`${item.sheet}-${item.sourceRange}`}
                view={item}
                title={tableTitles[item.title ?? item.sheet]}
              />
            ))}
          </div>

          {hasReport && (
            <section className={cn('surface-card p-5', translating && 'opacity-60')}>
              <ReportView content={report!} />
            </section>
          )}
        </div>
      )}
    </div>
  )
}
