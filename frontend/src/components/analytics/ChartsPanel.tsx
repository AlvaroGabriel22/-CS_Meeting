import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { SeriesOrder, SeriesResponse } from '@/types/api'

import { QualityChart, type ChartKind } from './QualityChart'

/**
 * The chart container.
 *
 * Fully controlled by the page: the version, the table, the metric and the
 * highlighted period all arrive as props, so the chart always shows the same
 * snapshot as the KPIs, the insights and the tables. Only presentation
 * choices — line or bars, file or chronological order — live here.
 */
export function ChartsPanel({
  versionId,
  table,
  metric,
  highlightPeriod,
}: {
  versionId: number
  table?: string
  metric?: string
  highlightPeriod?: string
}) {
  const { t } = useTranslation()
  const [data, setData] = useState<SeriesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [kind, setKind] = useState<ChartKind>('line')
  const [order, setOrder] = useState<SeriesOrder>('file')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    void (async () => {
      try {
        const response = await api.getSeries(versionId, { table, metric, order })
        if (active) setData(response)
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

  if (error) {
    return (
      <Card className="border-critical/30 bg-critical/5">
        <CardTitle className="text-critical">{t('common.error')}</CardTitle>
        <CardDescription className="mt-1 text-critical">{error}</CardDescription>
      </Card>
    )
  }

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <CardDescription>
          {[table, metric].filter(Boolean).join(' · ')}
          {highlightPeriod ? ` — ${highlightPeriod}` : ''}
        </CardDescription>
        <div className="flex items-center gap-2">
          {(['line', 'bar'] as ChartKind[]).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setKind(option)}
              className={cn(
                'rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
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
            className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink-500 hover:text-brand-700"
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
        <QualityChart
          periods={data?.periods ?? []}
          series={data?.series ?? []}
          kind={kind}
          highlight={highlightPeriod}
        />
      )}
    </Card>
  )
}
