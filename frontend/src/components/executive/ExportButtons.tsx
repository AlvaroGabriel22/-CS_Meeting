import { FileDown, Loader2, Presentation } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import type { ExportRequest } from '@/types/api'

/**
 * Takes the page to the meeting.
 *
 * The current selection — version, period, table, metric, comparison — is sent
 * with the request, so the file is what the screen is showing, not a snapshot
 * of some earlier state.
 */
export function ExportButtons({
  versionId,
  request,
}: {
  versionId: number
  request: ExportRequest
}) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState<'pdf' | 'ppt' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const download = async (format: 'pdf' | 'ppt') => {
    setBusy(format)
    setError(null)
    try {
      const { blob, filename } = await api.exportView(versionId, format, request)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => void download('pdf')} disabled={busy !== null}>
        {busy === 'pdf' ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        ) : (
          <FileDown className="h-4 w-4" aria-hidden />
        )}
        {t('export.pdf')}
      </Button>
      <Button variant="outline" size="sm" onClick={() => void download('ppt')} disabled={busy !== null}>
        {busy === 'ppt' ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        ) : (
          <Presentation className="h-4 w-4" aria-hidden />
        )}
        {t('export.ppt')}
      </Button>
      {error && <span className="text-xs text-critical">{error}</span>}
    </div>
  )
}
