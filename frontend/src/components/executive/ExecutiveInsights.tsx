import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { Insight, Severity } from '@/types/api'

const SEVERITY_STYLE: Record<Severity, { border: string; icon: typeof Info; tone: string }> = {
  negative: { border: 'border-l-critical', icon: AlertTriangle, tone: 'text-critical' },
  positive: { border: 'border-l-positive', icon: CheckCircle2, tone: 'text-positive' },
  neutral: { border: 'border-l-brand-300', icon: Info, tone: 'text-ink-500' },
  unknown: { border: 'border-l-line', icon: Info, tone: 'text-ink-300' },
}

/**
 * One statement, with the numbers that back it and where they came from.
 *
 * The sentence is rendered from a template key the backend chose, so it reads
 * in the user's language; `insight.text` is the English fallback. The card
 * never adds a cause — the model has none to give.
 */
export function InsightCard({ insight }: { insight: Insight }) {
  const { t } = useTranslation()
  const style = SEVERITY_STYLE[insight.severity]
  const Icon = style.icon
  const sentence = t(insight.template, {
    ...insight.params,
    defaultValue: insight.text,
  })

  return (
    <article className={cn('surface-card border-l-4 p-4', style.border)}>
      <div className="flex items-start gap-3">
        <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', style.tone)} aria-hidden />
        <div className="min-w-0">
          <p className="text-sm text-ink-900">{sentence}</p>
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-500">
            <span>{[insight.table, insight.category, insight.metric].filter(Boolean).join(' · ')}</span>
            {insight.period && <span>{insight.period.label}</span>}
            {insight.versionNumber !== null && <span>v{insight.versionNumber}</span>}
            <span className="font-mono text-ink-300">
              {insight.sourceRange}
              {insight.source ? ` · ${insight.source}` : ''}
            </span>
          </p>
        </div>
      </div>
    </article>
  )
}

export function ExecutiveInsights({ insights }: { insights: Insight[] }) {
  const { t } = useTranslation()

  if (insights.length === 0) {
    return (
      <p className="surface-card p-4 text-sm text-ink-500">{t('executive.noInsights')}</p>
    )
  }

  return (
    <div className="space-y-3">
      {insights.map((insight, index) => (
        <InsightCard key={`${insight.kind}-${insight.table}-${insight.category}-${index}`} insight={insight} />
      ))}
    </div>
  )
}
