import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { Direction, Kpi, Severity } from '@/types/api'

const SEVERITY_TEXT: Record<Severity, string> = {
  positive: 'text-positive',
  negative: 'text-critical',
  neutral: 'text-ink-700',
  unknown: 'text-ink-500',
}

function Trend({ direction, severity }: { direction: Direction; severity: Severity }) {
  const Icon =
    direction === 'up'
      ? ArrowUpRight
      : direction === 'down'
        ? ArrowDownRight
        : direction === 'flat'
          ? ArrowRight
          : Minus
  return <Icon className={cn('h-4 w-4', SEVERITY_TEXT[severity])} aria-hidden />
}

/**
 * The executive reading of the selected period.
 *
 * Every card comes from the model: the metric exists in the workbook, the
 * comparison is against the reference period the engine resolved, and a target
 * appears only when the file carries one.
 */
export function KpiStrip({ kpis, basis }: { kpis: Kpi[]; basis: string }) {
  const { t } = useTranslation()
  if (kpis.length === 0) return null

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {kpis.map((kpi) => (
        <article key={kpi.key} className="surface-card p-5">
          <header className="flex items-start justify-between gap-2">
            <div>
              <p className="text-xs uppercase tracking-wide text-ink-500">{kpi.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-brand-900">
                {kpi.display ?? '—'}
              </p>
            </div>
            <span className="rounded-full bg-brand-50 px-2 py-1 text-xs font-medium text-brand-700">
              {kpi.period.label}
            </span>
          </header>

          <dl className="mt-4 space-y-1 text-sm">
            <div className="flex items-center justify-between gap-2">
              <dt className="text-ink-500">
                {kpi.previousPeriod
                  ? t(`executive.basis.${basis}`, { period: kpi.previousPeriod.label })
                  : t('executive.noReference')}
              </dt>
              <dd className={cn('flex items-center gap-1 tabular-nums', SEVERITY_TEXT[kpi.severity])}>
                {kpi.delta === null ? (
                  <span className="text-ink-300">{t(`analytics.status.${kpi.status}`)}</span>
                ) : (
                  <>
                    <Trend direction={kpi.direction} severity={kpi.severity} />
                    {kpi.delta > 0 ? '+' : ''}
                    {kpi.delta.toLocaleString()}
                    {kpi.deltaPercent !== null && (
                      <span>
                        ({kpi.deltaPercent > 0 ? '+' : ''}
                        {kpi.deltaPercent.toFixed(1)}%)
                      </span>
                    )}
                  </>
                )}
              </dd>
            </div>

            {kpi.target !== null && (
              <div className="flex items-center justify-between gap-2">
                <dt className="text-ink-500">{t('executive.target')}</dt>
                <dd
                  className={cn(
                    'tabular-nums',
                    kpi.targetBreached ? 'text-critical' : 'text-ink-700',
                  )}
                >
                  {kpi.targetDisplay}
                  {kpi.targetStatus && ` · ${t(`executive.targetStatus.${kpi.targetStatus}`)}`}
                </dd>
              </div>
            )}
          </dl>

          <footer className="mt-3 border-t border-line pt-2 font-mono text-[11px] text-ink-300">
            {kpi.sourceRange}
            {kpi.source ? ` · ${kpi.source}` : ''}
          </footer>
        </article>
      ))}
    </div>
  )
}
