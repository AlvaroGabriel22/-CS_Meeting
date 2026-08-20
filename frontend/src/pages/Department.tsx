import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import { buttonVariants } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { Department as DepartmentCode } from '@/types/api'

const VALID: DepartmentCode[] = ['IQC', 'OQC', 'FIELD']

/**
 * Every department page has the same three stacked containers:
 * graphs, tables, issue reports.  Their content arrives in the next sprints.
 */
export function Department() {
  const { t } = useTranslation()
  const { code } = useParams<{ code: string }>()
  const department = (VALID.find((item) => item === code) ?? 'IQC') as DepartmentCode

  const containers = [
    { key: 'graphs', empty: 'emptyGraphs' },
    { key: 'tables', empty: 'emptyTables' },
    { key: 'issueReports', empty: 'emptyIssues' },
  ] as const

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
        </div>
        <Link
          to={`/department/${department}/import`}
          className={cn(buttonVariants({ variant: 'secondary' }))}
        >
          {t('import.open')}
        </Link>
      </header>

      <div className="space-y-6">
        {containers.map((container) => (
          <Card key={container.key}>
            <CardTitle>{t(`department.${container.key}`)}</CardTitle>
            <CardDescription className="mt-2">{t(`department.${container.empty}`)}</CardDescription>
          </Card>
        ))}
      </div>
    </div>
  )
}
