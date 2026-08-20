import { AlertTriangle, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import { AnalyticsPanel } from '@/components/analytics/AnalyticsPanel'
import { IQCTable } from '@/components/table/IQCTable'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type {
  Department as DepartmentCode,
  PresentationVersion,
  VersionView,
} from '@/types/api'

const VALID: DepartmentCode[] = ['IQC', 'OQC', 'FIELD']

/**
 * A department page: graphs, tables, issue reports.
 *
 * The tables come from the latest saved snapshot, rendered from the model the
 * backend prepared — a later upload creates a new version and leaves this one
 * exactly as it was.
 */
export function Department() {
  const { t } = useTranslation()
  const { code } = useParams<{ code: string }>()
  const department = (VALID.find((item) => item === code) ?? 'IQC') as DepartmentCode

  const [view, setView] = useState<VersionView | null>(null)
  const [versions, setVersions] = useState<PresentationVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setView(null)
    setVersions([])
    setError(null)

    void (async () => {
      try {
        const presentations = await api.listPresentations(department)
        const presentation = presentations[0]
        const versionId = presentation?.latestVersion?.id
        if (!presentation || !versionId) {
          if (active) setLoading(false)
          return
        }
        const [loaded, history] = await Promise.all([
          api.getVersionView(versionId),
          api.listVersions(presentation.id),
        ])
        if (active) {
          setView(loaded)
          setVersions(history)
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        if (active) setLoading(false)
      }
    })()

    return () => {
      active = false
    }
  }, [department])

  const version = view?.version

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <span className="text-xs font-semibold uppercase tracking-widest text-brand-500">
            {t(`department.${department}`)}
          </span>
          <h1 className="mt-1 text-2xl font-semibold text-brand-900">
            {t(`department.${department}_full`)}
          </h1>
          {version && (
            <p className="mt-1 text-sm text-ink-500">
              {t('department.showingVersion', {
                version: version.number,
                label: version.label ?? '—',
              })}
              {version.summary.parserVersion && ` · parser ${version.summary.parserVersion}`}
            </p>
          )}
        </div>
        <Link
          to={`/department/${department}/import`}
          className={cn(buttonVariants({ variant: 'secondary' }))}
        >
          {t('import.open')}
        </Link>
      </header>

      <div className="space-y-6">
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-brand-900">{t('department.graphs')}</h2>
          {version ? (
            <AnalyticsPanel versionId={version.id} versions={versions} />
          ) : (
            <Card>
              <CardDescription>{t('department.emptyGraphs')}</CardDescription>
            </Card>
          )}
        </section>

        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-brand-900">{t('department.tables')}</h2>
            {loading && <Loader2 className="h-4 w-4 animate-spin text-brand-500" aria-hidden />}
          </div>

          {error && (
            <Card className="border-critical/30 bg-critical/5">
              <CardTitle className="text-critical">{t('common.error')}</CardTitle>
              <CardDescription className="mt-1 text-critical">{error}</CardDescription>
            </Card>
          )}

          {!loading && !error && !view?.tables.length && (
            <Card>
              <CardDescription className="flex flex-wrap items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
                {t('department.emptyTables')}
                <Link
                  to={`/department/${department}/import`}
                  className="font-medium text-brand-600 hover:text-brand-800"
                >
                  {t('import.open')} →
                </Link>
              </CardDescription>
            </Card>
          )}

          {view?.tables.map((table) => (
            <IQCTable key={`${table.sheet}-${table.sourceRange}`} view={table} />
          ))}
        </section>

        <Card>
          <CardTitle>{t('department.issueReports')}</CardTitle>
          <CardDescription className="mt-2">{t('department.emptyIssues')}</CardDescription>
        </Card>
      </div>
    </div>
  )
}
