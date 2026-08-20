import { ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { buttonVariants } from '@/components/ui/button'
import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { Department } from '@/types/api'

const DEPARTMENTS: Department[] = ['IQC', 'OQC', 'FIELD']

export function Home() {
  const { t } = useTranslation()

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-14">
      <header className="mb-10 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-brand-900 sm:text-4xl">
          {t('home.title')}
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-ink-500">{t('home.subtitle')}</p>
      </header>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {DEPARTMENTS.map((department) => (
          <Card key={department} className="surface-card-interactive flex flex-col">
            <div className="mb-6">
              <span className="inline-flex rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold tracking-wide text-brand-600">
                {t(`department.${department}`)}
              </span>
              <CardTitle className="mt-4 text-xl">{t(`department.${department}_full`)}</CardTitle>
              <CardDescription className="mt-1">{t('home.noPresentation')}</CardDescription>
            </div>

            <dl className="mb-6 space-y-2 text-sm">
              {(['status', 'period', 'issues', 'lastUpdate'] as const).map((key) => (
                <div key={key} className="flex justify-between border-b border-line/70 pb-2">
                  <dt className="text-ink-500">{t(`card.${key}`)}</dt>
                  <dd className="font-medium text-ink-700">
                    {key === 'issues' ? '0' : key === 'status' ? t('status.draft') : '—'}
                  </dd>
                </div>
              ))}
            </dl>

            <Link
              to={`/department/${department}`}
              className={cn(buttonVariants({ variant: 'primary' }), 'mt-auto w-full')}
            >
              {t('home.openPresentation')}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </Card>
        ))}
      </div>
    </div>
  )
}
