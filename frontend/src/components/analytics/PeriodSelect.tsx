import { cn } from '@/lib/utils'
import type { Period } from '@/types/api'

/**
 * Period picker driven entirely by the model.
 *
 * The list is whatever the snapshot holds — a month more, a quarter that just
 * closed, a week — and it is ordered by the engine's `sortKey`, while the label
 * shown stays the semantic one ("Aug", "3Q").
 */
export function PeriodSelect({
  periods,
  value,
  onChange,
  label,
  id,
}: {
  periods: Period[]
  value: string
  onChange: (label: string) => void
  label: string
  id: string
}) {
  const ordered = [...periods].sort((a, b) => a.sortKey.localeCompare(b.sortKey))

  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-xs text-ink-500">
      {label}
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          'rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink-900',
          'focus:border-brand-300 focus:outline-none',
        )}
      >
        {ordered.map((period) => (
          <option key={period.sortKey + period.label} value={period.label}>
            {period.label}
            {period.quarter && period.kind === 'month' ? ` · ${period.quarter}` : ''}
          </option>
        ))}
      </select>
    </label>
  )
}

/** A plain option list, for the model dimensions (table, metric, …). */
export function OptionSelect({
  options,
  value,
  onChange,
  label,
  id,
  allowEmpty,
}: {
  options: string[]
  value: string
  onChange: (value: string) => void
  label: string
  id: string
  allowEmpty?: string
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-xs text-ink-500">
      {label}
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink-900 focus:border-brand-300 focus:outline-none"
      >
        {allowEmpty !== undefined && <option value="">{allowEmpty}</option>}
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  )
}
