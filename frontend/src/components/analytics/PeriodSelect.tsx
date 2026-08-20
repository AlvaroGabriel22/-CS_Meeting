import { cn } from '@/lib/utils'
import type { Period } from '@/types/api'

/**
 * Period picker driven entirely by the model.
 *
 * The list is whatever the snapshot holds — a month more, a quarter that just
 * closed, a week — **in the order the API returned it**: the period engine owns
 * ordering (`order=file` keeps the workbook's columns, `order=chronological`
 * applies the engine's sortKey rules). Re-sorting `sortKey` as a string here
 * would be wrong, because `2026-M08` sorts before `2026-Q1` alphabetically
 * while August comes after the first quarter.
 *
 * The label shown stays the semantic one ("Aug", "3Q").
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
        {periods.map((period) => (
          <option key={period.sortKey + period.label} value={period.label}>
            {period.label}
            {period.quarter && period.kind === 'month' ? ` · ${period.quarter}` : ''}
          </option>
        ))}
      </select>
    </label>
  )
}

export type Option = string | { value: string; label: string }

/** A plain option list, for the model dimensions (table, metric, version…). */
export function OptionSelect({
  options,
  value,
  onChange,
  label,
  id,
  allowEmpty,
}: {
  options: Option[]
  value: string
  onChange: (value: string) => void
  label: string
  id: string
  allowEmpty?: string
}) {
  const entries = options.map((option) =>
    typeof option === 'string' ? { value: option, label: option } : option,
  )

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
        {entries.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}
