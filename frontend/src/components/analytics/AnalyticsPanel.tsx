import { Loader2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type {
  ComparisonResponse,
  PresentationVersion,
  SeriesOrder,
  SeriesResponse,
} from '@/types/api'

import { ComparisonTable } from './ComparisonTable'
import { OptionSelect, PeriodSelect } from './PeriodSelect'
import { QualityChart, type ChartKind } from './QualityChart'

/**
 * The analytical container of a department page.
 *
 * It picks nothing by name: tables, metrics and periods all come from the
 * snapshot, and the two comparison panels work on whatever the user selected.
 */
export function AnalyticsPanel({
  versionId,
  versions,
}: {
  versionId: number
  versions: PresentationVersion[]
}) {
  const { t } = useTranslation()

  const [data, setData] = useState<SeriesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [table, setTable] = useState('')
  const [metric, setMetric] = useState('')
  const [order, setOrder] = useState<SeriesOrder>('file')
  const [kind, setKind] = useState<ChartKind>('line')

  const [periodA, setPeriodA] = useState('')
  const [periodB, setPeriodB] = useState('')
  const [periodComparison, setPeriodComparison] = useState<ComparisonResponse | null>(null)

  const [otherVersion, setOtherVersion] = useState('')
  const [versionComparison, setVersionComparison] = useState<ComparisonResponse | null>(null)

  // --- series -------------------------------------------------------------
  useEffect(() => {
    let active = true
    setLoading(true)
    void (async () => {
      try {
        const response = await api.getSeries(versionId, {
          table: table || undefined,
          metric: metric || undefined,
          order,
        })
        if (!active) return
        setData(response)
        setTable((current) => current || response.options.tables[0] || '')
        setMetric((current) => current || response.options.metrics[0] || '')
        setPeriodB((current) => current || response.periods.at(-1)?.label || '')
        setPeriodA((current) => current || response.periods.at(-2)?.label || '')
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        if (active) setLoading(false)
      }
    })()
    return () => {
      active = false
    }
  }, [versionId, table, metric, order])

  // --- period comparison --------------------------------------------------
  useEffect(() => {
    if (!periodA || !periodB || !table) return
    let active = true
    void (async () => {
      try {
        const response = await api.comparePeriods(versionId, {
          periodA,
          periodB,
          table,
          metric: metric || undefined,
        })
        if (active) setPeriodComparison(response)
      } catch {
        if (active) setPeriodComparison(null)
      }
    })()
    return () => {
      active = false
    }
  }, [versionId, periodA, periodB, table, metric])

  // --- version comparison -------------------------------------------------
  useEffect(() => {
    if (!otherVersion || !periodB || !table) {
      setVersionComparison(null)
      return
    }
    let active = true
    void (async () => {
      try {
        const response = await api.compareVersions(versionId, Number(otherVersion), {
          period: periodB,
          table,
          metric: metric || undefined,
        })
        if (active) setVersionComparison(response)
      } catch {
        if (active) setVersionComparison(null)
      }
    })()
    return () => {
      active = false
    }
  }, [versionId, otherVersion, periodB, table, metric])

  const series = useMemo(() => data?.series ?? [], [data])
  const periods = data?.periods ?? []
  const otherVersions = versions.filter((version) => version.id !== versionId)

  if (error) {
    return (
      <Card className="border-critical/30 bg-critical/5">
        <CardTitle className="text-critical">{t('common.error')}</CardTitle>
        <CardDescription className="mt-1 text-critical">{error}</CardDescription>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="mb-5 flex flex-wrap items-end gap-3">
          <OptionSelect
            id="analytics-table"
            label={t('analytics.table')}
            options={data?.options.tables ?? []}
            value={table}
            onChange={setTable}
          />
          <OptionSelect
            id="analytics-metric"
            label={t('analytics.metric')}
            options={data?.options.metrics ?? []}
            value={metric}
            onChange={setMetric}
            allowEmpty={t('analytics.allMetrics')}
          />
          <PeriodSelect
            id="analytics-period-a"
            label={t('analytics.periodA')}
            periods={periods}
            value={periodA}
            onChange={setPeriodA}
          />
          <PeriodSelect
            id="analytics-period-b"
            label={t('analytics.periodB')}
            periods={periods}
            value={periodB}
            onChange={setPeriodB}
          />

          <div className="ml-auto flex items-end gap-2">
            {(['line', 'bar'] as ChartKind[]).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setKind(option)}
                className={cn(
                  'rounded-lg border px-3 py-2 text-xs font-medium transition-colors',
                  kind === option
                    ? 'border-brand-300 bg-brand-50 text-brand-800'
                    : 'border-line text-ink-500 hover:text-brand-700',
                )}
              >
                {t(`analytics.chart.${option}`)}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setOrder(order === 'file' ? 'chronological' : 'file')}
              className="rounded-lg border border-line px-3 py-2 text-xs font-medium text-ink-500 hover:text-brand-700"
              title={t('analytics.orderHint')}
            >
              {t(`analytics.order.${order}`)}
            </button>
          </div>
        </div>

        {loading && !data ? (
          <div className="flex items-center gap-2 py-8 text-sm text-ink-500">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            {t('common.loading')}
          </div>
        ) : (
          <QualityChart periods={periods} series={series} kind={kind} highlight={periodB} />
        )}
      </Card>

      {periodComparison && (
        <Card>
          <CardTitle className="text-base">
            {t('analytics.periodComparison', { a: periodA, b: periodB })}
          </CardTitle>
          <div className="mt-4">
            <ComparisonTable comparison={periodComparison} />
          </div>
        </Card>
      )}

      {otherVersions.length > 0 && (
        <Card>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <CardTitle className="text-base">{t('analytics.versionComparison')}</CardTitle>
            <OptionSelect
              id="analytics-other-version"
              label={t('analytics.compareWith')}
              options={otherVersions.map((version) => String(version.id))}
              value={otherVersion}
              onChange={setOtherVersion}
              allowEmpty={t('analytics.pickVersion')}
            />
          </div>
          {versionComparison && (
            <div className="mt-4">
              <ComparisonTable comparison={versionComparison} />
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
