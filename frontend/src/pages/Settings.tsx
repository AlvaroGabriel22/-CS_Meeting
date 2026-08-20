import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { Card, CardDescription, CardTitle } from '@/components/ui/card'
import type { Department } from '@/types/api'

const DEPARTMENTS: Department[] = ['IQC', 'OQC', 'FIELD']
const SECTIONS = [
  'rawDataUpload',
  'issueReport',
  'presentationManagement',
  'versions',
  'translations',
  'export',
] as const

export function Settings() {
  const { t } = useTranslation()

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-10">
      <h1 className="text-2xl font-semibold text-brand-900">{t('settings.title')}</h1>
      <p className="mt-2 text-ink-500">{t('settings.chooseDepartment')}</p>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        {DEPARTMENTS.map((department) => (
          <Card key={department} className="surface-card-interactive">
            <CardTitle>{t(`department.${department}_full`)}</CardTitle>
            <CardDescription className="mt-1">{t(`department.${department}`)}</CardDescription>
            <ul className="mt-4 space-y-1 text-sm text-ink-500">
              {SECTIONS.map((section) => (
                <li key={section} className="rounded-md px-2 py-1 hover:bg-brand-50">
                  {t(`settings.${section}`)}
                </li>
              ))}
            </ul>
            <div className="mt-4 flex flex-col gap-1 text-sm font-medium">
              <Link
                to={`/department/${department}/import`}
                className="text-brand-600 hover:text-brand-800"
              >
                {t('import.open')} →
              </Link>
              <Link
                to={`/department/${department}`}
                className="text-brand-600 hover:text-brand-800"
              >
                {t('home.openPresentation')} →
              </Link>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
