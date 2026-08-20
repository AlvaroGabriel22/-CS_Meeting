import type { DisplayFormat, Language, TableCell } from '@/types/api'

/**
 * Renders a stored number using the hint that came from the raw file.
 * Mirrors `backend/app/excel/values.py::format_number` so a value looks the
 * same in the UI, in the PDF and in the PPT.  The stored value is never
 * mutated — 3000 stays 3000 and is merely *shown* as "3,000".
 */
export function formatNumber(
  value: number,
  format: DisplayFormat | null | undefined,
  language: Language = 'en',
): string {
  const kind = format?.kind ?? 'auto'
  const locale = language === 'pt-BR' ? 'pt-BR' : language === 'ko' ? 'ko-KR' : 'en-US'
  const decimals =
    format?.decimals ?? (Number.isInteger(value) ? 0 : kind === 'percent' ? 1 : 2)

  const options: Intl.NumberFormatOptions = {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping: format?.thousands ?? true,
  }

  if (kind === 'percent') {
    return new Intl.NumberFormat(locale, { ...options, style: 'percent' }).format(value)
  }
  if (kind === 'currency' && format?.currency) {
    return new Intl.NumberFormat(locale, {
      ...options,
      style: 'currency',
      currency: format.currency,
    }).format(value)
  }
  return new Intl.NumberFormat(locale, options).format(value)
}

/** What a cell shows: numbers are formatted, NA and #DIV/0! are shown as-is. */
export function formatCell(cell: TableCell, language: Language = 'en'): string {
  switch (cell.valueType) {
    case 'number':
      return cell.number === null ? '' : formatNumber(cell.number, cell.display, language)
    case 'error':
      return cell.errorCode ?? '#ERROR'
    case 'na':
      return cell.text ?? 'NA'
    case 'empty':
      return ''
    default:
      return cell.text ?? ''
  }
}

/** Human label for a discovered period, e.g. "W32 · Aug 2026". */
export function periodLabel(period: { label: string; year: number | null }): string {
  return period.year ? `${period.label} ${period.year}` : period.label
}
