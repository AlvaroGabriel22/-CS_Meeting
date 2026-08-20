import { AlertTriangle, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import { ChartsPanel } from '@/components/analytics/ChartsPanel'
import { ComparisonPanel } from '@/components/analytics/ComparisonPanel'
import { OptionSelect, PeriodSelect } from '@/components/analytics/PeriodSelect'
import { ExecutiveInsights } from '@/components/executive/ExecutiveInsights'
import { ExportButtons } from '@/components/executive/ExportButtons'
import { KpiStrip } from '@/components/executive/KpiStrip'
import { VersionSelector } from '@/components/executive/VersionSelector'
import { IssuesSection } from '@/components/issues/IssuesSection'
import { IQCTable } from '@/components/table/IQCTable'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type {
  Department as DepartmentCode,
  ExecutiveView,
  PresentationVersion,
  VersionView,
} from '@/types/api'

const VALID: DepartmentCode[] = ['IQC', 'OQC', 'FIELD']

/**
 * The department page, read top-down like a meeting:
 *
 *   header → version → period → KPIs → insights → charts → tables → comparison
 *
 * The version and the period chosen here drive **everything** below: one
 * snapshot, one period, one consistent reading of the data.
 */
export function Department() {
  const { t } = useTranslation()
  const { code } = useParams<{ code: string }>()
  const department = (VALID.find((item) => item === code) ?? 'IQC') as DepartmentCode

  const [versions, setVersions] = useState<PresentationVersion[]>([])
  const [versionId, setVersionId] = useState<number | null>(null)
  const [executive, setExecutive] = useState<ExecutiveView | null>(null)
  const [view, setView] = useState<VersionView | null>(null)

  const [period, setPeriod] = useState('')
  const [table, setTable] = useState('')
  const [metric, setMetric] = useState('')

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // --- which versions exist, and which one are we reading? -----------------
  useEffect(() => {
    let active = true
    setLoading(true)
    setVersions([])
    setVersionId(null)
    setError(null)

    void (async () => {
      try {
        const presentations = await api.listPresentations(department)
        const presentation = presentations[0]
        if (!presentation?.latestVersion) {
          if (active) setLoading(false)
          return
        }
        const history = await api.listVersions(presentation.id)
        if (!active) return
        setVersions(history)
        setVersionId(presentation.latestVersion.id)
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [department])

  // --- the selected version drives the whole page --------------------------
  useEffect(() => {
    if (!versionId) return
    let active = true
    setLoading(true)
    // a new version may not hold the period or the table selected on the old one
    setPeriod('')
    setTable('')
    setMetric('')

    void (async () => {
      try {
        const [snapshot, summary] = await Promise.all([
          api.getVersionView(versionId),
          api.getExecutiveView(versionId),
        ])
        if (!active) return
        setView(snapshot)
        setExecutive(summary)
        setPeriod(summary.period?.label ?? '')
        setTable(summary.options.tables[0] ?? '')
        setMetric(summary.metric ?? '')
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [versionId])

  // --- period, table or metric changed: refresh the executive reading ------
  useEffect(() => {
    if (!versionId || !period) return
    let active = true
    void (async () => {
      try {
        const summary = await api.getExecutiveView(versionId, {
          period,
          table: table || undefined,
          metric: metric || undefined,
        })
        if (active) setExecutive(summary)
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
      }
    })()
    return () => {
      active = false
    }
  }, [versionId, period, table, metric])

  const version = versions.find((item) => item.id === versionId) ?? null
  const hasData = Boolean(versionId && view)

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <span className="text-xs font-semibold uppercase tracking-widest text-brand-500">
            {t(`department.${department}`)}
          </span>
          <h1 className="mt-1 text-2xl font-semibold text-brand-900">
            {t(`department.${department}_full`)}
          </h1>
          {version && (
            <p className="mt-1 text-sm text-ink-500">
              {t('department.showingVersion', {
                version: version.number,
                label: version.label ?? '—',
              })}
              {version.summary.parserVersion && ` · parser ${version.summary.parserVersion}`}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <VersionSelector versions={versions} value={versionId} onChange={setVersionId} />
          {versionId && (
            <ExportButtons
              versionId={versionId}
              request={{
                period: period || undefined,
                table: table || undefined,
                metric: metric || undefined,
              }}
            />
          )}
          <Link
            to={`/department/${department}/import`}
            className={cn(buttonVariants({ variant: 'secondary' }))}
          >
            {t('import.open')}
          </Link>
        </div>
      </header>

      {error && (
        <Card className="mb-6 border-critical/30 bg-critical/5">
          <CardTitle className="text-critical">{t('common.error')}</CardTitle>
          <CardDescription className="mt-1 text-critical">{error}</CardDescription>
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
            <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
            {t('department.emptyTables')}
            <Link
              to={`/department/${department}/import`}
              className="font-medium text-brand-600 hover:text-brand-800"
            >
              {t('import.open')} →
            </Link>
          </CardDescription>
        </Card>
      )}

      {hasData && executive && (
        <div className="space-y-8">
          {/* what we are looking at — drives every panel below */}
          <Card>
            <div className="flex flex-wrap items-end gap-3">
              <PeriodSelect
                id="page-period"
                label={t('executive.period')}
                periods={executive.periods}
                value={period}
                onChange={setPeriod}
              />
              <OptionSelect
                id="page-table"
                label={t('executive.table')}
                options={executive.options.tables}
                value={table}
                onChange={setTable}
              />
              <OptionSelect
                id="page-metric"
                label={t('executive.metric')}
                options={executive.options.metrics}
                value={metric}
                onChange={setMetric}
              />
            </div>
            {executive.warnings.length > 0 && (
              <ul className="mt-4 space-y-1 text-xs text-ink-500">
                {executive.warnings.map((warning) => (
                  <li key={warning} className="flex items-center gap-2">
                    <AlertTriangle className="h-3.5 w-3.5 text-warning" aria-hidden />
                    {t(`executive.warnings.${warning}`, { defaultValue: warning })}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-brand-900">{t('executive.kpis')}</h2>
            <KpiStrip kpis={executive.kpis} basis={executive.comparisonBasis} />
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-brand-900">{t('executive.insights')}</h2>
            <ExecutiveInsights insights={executive.insights} />
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-brand-900">{t('issues.title')}</h2>
            <IssuesSection
              versionId={versionId!}
              period={period}
              table={table || undefined}
              metric={metric || undefined}
              insights={executive.insights}
            />
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-brand-900">{t('department.graphs')}</h2>
            <ChartsPanel
              versionId={versionId!}
              table={table || undefined}
              metric={metric || undefined}
              highlightPeriod={period}
            />
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-brand-900">{t('department.tables')}</h2>
            {view?.tables.map((item) => (
              <IQCTable key={`${item.sheet}-${item.sourceRange}`} view={item} />
            ))}
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-brand-900">
              {t('analytics.periodComparison', {
                a: executive.previousPeriod?.label ?? '—',
                b: period,
              })}
            </h2>
            <ComparisonPanel
              versionId={versionId!}
              versions={versions}
              periods={executive.periods}
              period={period}
              referencePeriod={executive.previousPeriod?.label ?? null}
              table={table || undefined}
              metric={metric || undefined}
            />
          </section>

        </div>
      )}
    </div>
  )
}
