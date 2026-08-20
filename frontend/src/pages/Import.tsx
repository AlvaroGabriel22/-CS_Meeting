import { AlertTriangle, CheckCircle2, FileSpreadsheet, Loader2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Department, ImportRecord } from '@/types/api'

const DEPARTMENTS: Department[] = ['IQC', 'OQC', 'FIELD']

type Status = 'idle' | 'parsing' | 'preview' | 'saving' | 'saved' | 'error'

/**
 * Raw data import: pick a file, parse it, look at what the parser understood,
 * then save the version.  The preview call does not create a snapshot; the
 * confirmation does.
 */
export function Import() {
  const { t } = useTranslation()
  const { code } = useParams<{ code: string }>()
  const department = (DEPARTMENTS.find((item) => item === code) ?? 'IQC') as Department

  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [preview, setPreview] = useState<ImportRecord | null>(null)
  const [saved, setSaved] = useState<ImportRecord | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setPreview(null)
    setSaved(null)
    setError(null)
    setStatus('idle')
  }

  const analyze = async (selected: File) => {
    setStatus('parsing')
    setError(null)
    setSaved(null)
    try {
      setPreview(await api.uploadRawData(department, selected, { createVersion: false }))
      setStatus('preview')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
      setStatus('error')
    }
  }

  const saveVersion = async () => {
    if (!file) return
    setStatus('saving')
    try {
      setSaved(await api.uploadRawData(department, file, { createVersion: true }))
      setStatus('saved')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
      setStatus('error')
    }
  }

  const record = saved ?? preview
  const warnings = record ? [...record.warnings, ...record.tables.flatMap((table) => table.warnings)] : []

  return (
    <div className="mx-auto max-w-[1100px] px-6 py-10">
      <header className="mb-8">
        <span className="text-xs font-semibold uppercase tracking-widest text-brand-500">
          {t(`department.${department}`)}
        </span>
        <h1 className="mt-1 text-2xl font-semibold text-brand-900">{t('import.title')}</h1>
        <p className="mt-2 text-sm text-ink-500">{t('import.subtitle')}</p>
      </header>

      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-4">
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xlsm"
            className="hidden"
            onChange={(event) => {
              const selected = event.target.files?.[0] ?? null
              setFile(selected)
              reset()
              if (selected) void analyze(selected)
            }}
          />
          <Button onClick={() => inputRef.current?.click()} disabled={status === 'parsing'}>
            <Upload className="h-4 w-4" aria-hidden />
            {t('import.chooseFile')}
          </Button>

          <span className="flex items-center gap-2 text-sm text-ink-500">
            <FileSpreadsheet className="h-4 w-4" aria-hidden />
            {file ? file.name : t('import.noFile')}
          </span>

          {status === 'parsing' && (
            <span className="flex items-center gap-2 text-sm text-brand-600">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              {t('import.parsing')}
            </span>
          )}
        </div>
      </Card>

      {error && (
        <Card className="mb-6 border-critical/30 bg-critical/5">
          <CardTitle className="text-critical">{t('common.error')}</CardTitle>
          <CardDescription className="mt-1 text-critical">{error}</CardDescription>
        </Card>
      )}

      {record && (
        <div className="space-y-6">
          <Card>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
              <div>
                <CardTitle>{t('import.preview')}</CardTitle>
                <CardDescription className="mt-1">
                  {t('import.parserVersion', { version: record.parserVersion })}
                  {record.reused && ` · ${t('import.reused')}`}
                </CardDescription>
              </div>
              <span
                className={cn(
                  'inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold',
                  warnings.length ? 'bg-warning/10 text-warning' : 'bg-positive/10 text-positive',
                )}
              >
                {warnings.length ? (
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
                )}
                {warnings.length
                  ? t('import.warningCount', { count: warnings.length })
                  : t('import.clean')}
              </span>
            </div>

            <dl className="mb-6 grid gap-4 sm:grid-cols-3">
              <div className="rounded-lg bg-brand-50 p-4">
                <dt className="text-xs uppercase tracking-wide text-ink-500">
                  {t('import.tablesDetected')}
                </dt>
                <dd className="mt-1 text-lg font-semibold text-brand-900">
                  {record.tableNames.join(' · ') || record.tables.length}
                </dd>
              </div>
              <div className="rounded-lg bg-brand-50 p-4">
                <dt className="text-xs uppercase tracking-wide text-ink-500">
                  {t('import.periodsDetected')}
                </dt>
                <dd className="mt-1 text-lg font-semibold text-brand-900">
                  {record.periods.join(' · ') || '—'}
                </dd>
              </div>
              <div className="rounded-lg bg-brand-50 p-4">
                <dt className="text-xs uppercase tracking-wide text-ink-500">
                  {t('import.version')}
                </dt>
                <dd className="mt-1 text-lg font-semibold text-brand-900">
                  {saved?.versionNumber ? `v${saved.versionNumber}` : t('import.notSavedYet')}
                </dd>
              </div>
            </dl>

            <div className="table-scroll">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-500">
                    <th className="py-2 pr-4">{t('import.table')}</th>
                    <th className="py-2 pr-4">{t('common.sourceRange')}</th>
                    <th className="py-2 pr-4">{t('import.hierarchy')}</th>
                    <th className="py-2 pr-4 text-right">{t('import.rows')}</th>
                    <th className="py-2 pr-4 text-right">{t('import.columns')}</th>
                    <th className="py-2">{t('import.periodsShort')}</th>
                  </tr>
                </thead>
                <tbody>
                  {record.tables.map((table) => (
                    <tr key={table.id} className="border-b border-line/60 last:border-0">
                      <td className="py-2 pr-4 font-medium text-brand-900">
                        {table.title ?? table.sheetName}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-ink-500">
                        {table.sourceRange}
                      </td>
                      <td className="py-2 pr-4 text-ink-700">
                        {table.hierarchy.join(' › ') || '—'}
                      </td>
                      <td className="py-2 pr-4 text-right tabular-nums">{table.rowCount}</td>
                      <td className="py-2 pr-4 text-right tabular-nums">{table.colCount}</td>
                      <td className="py-2 text-ink-700">
                        {table.periods.map((period) => period.label).join(', ')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {warnings.length > 0 && (
              <ul className="mt-4 space-y-1 text-sm text-warning">
                {[...new Set(warnings)].map((warning) => (
                  <li key={warning} className="flex items-center gap-2">
                    <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
                    <code className="font-mono text-xs">{warning}</code>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="flex items-center gap-4">
            <Button onClick={() => void saveVersion()} disabled={status === 'saving' || !!saved}>
              {status === 'saving' && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              {t('common.saveVersion')}
            </Button>
            {saved && (
              <span className="flex items-center gap-2 text-sm text-positive">
                <CheckCircle2 className="h-4 w-4" aria-hidden />
                {t('import.saved', { version: saved.versionNumber ?? '' })}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
