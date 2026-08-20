import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { ComparisonResponse, Delta, Direction, Severity } from '@/types/api'

const SEVERITY_CLASS: Record<Severity, string> = {
  positive: 'text-positive',
  negative: 'text-critical',
  neutral: 'text-ink-700',
  unknown: 'text-ink-500',
}

function DirectionIcon({ direction }: { direction: Direction }) {
  const Icon =
    direction === 'up'
      ? ArrowUpRight
      : direction === 'down'
        ? ArrowDownRight
        : direction === 'flat'
          ? ArrowRight
          : Minus
  return <Icon className="h-3.5 w-3.5" aria-hidden />
}

function DeltaCell({ delta }: { delta: Delta }) {
  const { t } = useTranslation()
  if (delta.delta === null) {
    return <span className="text-ink-300">{t(`analytics.status.${delta.status}`)}</span>
  }
  return (
    <span className={cn('inline-flex items-center gap-1 tabular-nums', SEVERITY_CLASS[delta.severity])}>
      <DirectionIcon direction={delta.direction} />
      {delta.delta > 0 ? '+' : ''}
      {delta.delta.toLocaleString()}
      {delta.deltaPercent === null ? (
        <span className="text-ink-300" title={t(`analytics.status.${delta.status}`)}>
          (—)
        </span>
      ) : (
        <span>
          ({delta.deltaPercent > 0 ? '+' : ''}
          {delta.deltaPercent.toFixed(1)}%)
        </span>
      )}
    </span>
  )
}

/** A/B comparison, whether the two sides are periods or versions. */
export function ComparisonTable({ comparison }: { comparison: ComparisonResponse }) {
  const { t } = useTranslation()
  const isVersions = comparison.kind === 'versions'
  const headA = isVersions
    ? `v${comparison.versionNumber}`
    : (comparison.periodA?.label ?? 'A')
  const headB = isVersions
    ? `v${comparison.comparedVersionNumber}`
    : (comparison.periodB?.label ?? 'B')

  return (
    <div className="table-scroll">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-500">
            <th className="py-2 pr-4">{t('analytics.row')}</th>
            <th className="py-2 pr-4 text-right">{headA}</th>
            <th className="py-2 pr-4 text-right">{headB}</th>
            <th className="py-2 pr-4">{t('analytics.delta')}</th>
            <th className="py-2">{t('common.sourceRange')}</th>
          </tr>
        </thead>
        <tbody>
          {comparison.rows.map((row) => (
            <tr key={row.key} className="border-b border-line/60 last:border-0">
              <td className="py-2 pr-4 text-ink-900">{row.label}</td>
              <td className="py-2 pr-4 text-right tabular-nums text-ink-700">
                {row.delta.displayA ?? '—'}
              </td>
              <td className="py-2 pr-4 text-right tabular-nums text-ink-900">
                {row.delta.displayB ?? '—'}
              </td>
              <td className="py-2 pr-4">
                <DeltaCell delta={row.delta} />
              </td>
              <td className="py-2 font-mono text-xs text-ink-300">
                {[row.sourceA, row.sourceB].filter(Boolean).join(' → ') || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {comparison.warnings.length > 0 && (
        <p className="mt-3 text-xs text-warning">
          {comparison.warnings.map((warning) => (
            <code key={warning} className="mr-3 font-mono">
              {warning}
            </code>
          ))}
        </p>
      )}
    </div>
  )
}
