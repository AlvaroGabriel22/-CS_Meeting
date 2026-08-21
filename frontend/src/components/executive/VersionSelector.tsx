import { History } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { PresentationVersion } from '@/types/api'

/**
 * Picks the snapshot the whole page reads.
 *
 * Every panel below — tables, charts, key figures — receives the id chosen
 * here, so the page is always showing one consistent version of the data.
 */
export function VersionSelector({
  versions,
  value,
  onChange,
  id = 'version-selector',
}: {
  versions: PresentationVersion[]
  value: number | null
  onChange: (versionId: number) => void
  id?: string
}) {
  const { t } = useTranslation()
  if (versions.length === 0) return null

  return (
    <label htmlFor={id} className="flex items-center gap-2 text-xs text-ink-500">
      <History className="h-4 w-4" aria-hidden />
      {t('executive.version')}
      <select
        id={id}
        value={value ?? ''}
        onChange={(event) => onChange(Number(event.target.value))}
        className="rounded-lg border border-line bg-white px-3 py-2 text-sm font-medium text-ink-900 focus:border-brand-300 focus:outline-none"
      >
        {versions.map((version) => (
          <option key={version.id} value={version.id}>
            v{version.number}
            {version.label ? ` · ${version.label}` : ''}
            {version.summary.rawFile ? ` — ${version.summary.rawFile}` : ''}
          </option>
        ))}
      </select>
    </label>
  )
}
