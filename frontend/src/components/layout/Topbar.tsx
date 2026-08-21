import { Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { NavLink, useLocation } from 'react-router-dom'

import { LANGUAGES, setLanguage } from '@/i18n'
import { cn } from '@/lib/utils'
import type { Department, Language } from '@/types/api'

const DEPARTMENTS: Department[] = ['IQC', 'OQC', 'FIELD']

/**
 * One topbar for the whole system.  Department links only show up outside the
 * Home page — the Home already presents the departments as cards.
 */
export function Topbar() {
  const { t, i18n } = useTranslation()
  const isHome = useLocation().pathname === '/'

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
      isActive ? 'bg-brand-100 text-brand-800' : 'text-ink-500 hover:bg-brand-50 hover:text-brand-700',
    )

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-white/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-6 px-6">
        <NavLink to="/" className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-700 text-sm font-semibold text-white shadow-sm">
            CS
          </span>
          <span className="hidden text-sm font-semibold text-brand-900 sm:block">
            {t('app.name')}
          </span>
        </NavLink>

        <nav className="flex flex-1 items-center gap-1">
          <NavLink to="/" className={linkClass} end>
            {t('nav.home')}
          </NavLink>
          {!isHome &&
            DEPARTMENTS.map((department) => (
              <NavLink key={department} to={`/department/${department}`} className={linkClass}>
                {t(`department.${department}`)}
              </NavLink>
            ))}
          <NavLink to="/reports" className={linkClass}>
            {t('nav.reports')}
          </NavLink>
          <NavLink to="/settings" className={linkClass}>
            {t('nav.settings')}
          </NavLink>
        </nav>

        <label className="flex items-center gap-2 text-sm text-ink-500">
          <Globe className="h-4 w-4" aria-hidden />
          <span className="sr-only">{t('nav.language')}</span>
          <select
            value={i18n.language}
            onChange={(event) => void setLanguage(event.target.value as Language)}
            className="rounded-lg border border-line bg-white px-2 py-1.5 text-sm text-ink-700 focus:border-brand-300 focus:outline-none"
          >
            {LANGUAGES.map((language) => (
              <option key={language.code} value={language.code}>
                {language.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </header>
  )
}
