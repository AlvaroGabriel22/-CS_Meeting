import { ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import type { Department } from '@/types/api'

const DEPARTMENTS: Department[] = ['IQC', 'OQC', 'FIELD']

/**
 * One card per department, and one thing to do on it: open its configuration.
 *
 * The presentation is reached from the top bar; listing it here as well only
 * made the card look like a menu of things that were not clickable.
 */
export function Settings() {
  const { t } = useTranslation()

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-10">
      <h1 className="text-2xl font-semibold text-brand-900">{t('settings.title')}</h1>
      <p className="mt-2 text-ink-500">{t('settings.chooseDepartment')}</p>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        {DEPARTMENTS.map((department) => (
          <Link key={department} to={`/department/${department}/config`} className="block">
            <Card className="surface-card-interactive h-full">
              <CardTitle>{t(`department.${department}_full`)}</CardTitle>
              <CardDescription className="mt-1">{t(`department.${department}`)}</CardDescription>
              <span className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-brand-600">
                {t('config.title')}
                <ArrowRight className="h-4 w-4" aria-hidden />
              </span>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
