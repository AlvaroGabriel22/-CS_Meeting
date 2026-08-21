import { ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import type { Department } from '@/types/api'

const DEPARTMENTS: Department[] = ['IQC', 'OQC', 'FIELD']

/**
 * Three doors in one frame, centred on the screen.
 *
 * The height is a *minimum*, not a fixed value: on a notebook the frame sits in
 * the middle of what is left below the top bar, and on a short window it simply
 * scrolls instead of clipping. `dvh` rather than `vh` so a mobile browser's
 * collapsing toolbar does not leave a gap, and the top bar's own 1px bottom
 * border is subtracted too — otherwise the page scrolls by exactly that pixel.
 */
export function Home() {
  const { t } = useTranslation()

  return (
    <div className="flex min-h-[calc(100dvh-4rem-1px)] flex-col items-center justify-center px-6 py-10">
      <h1 className="mb-10 text-center text-2xl font-semibold uppercase tracking-[0.3em] text-brand-800 sm:text-3xl">
        {t('app.name')}
      </h1>

      <section className="surface-card card-3d-stage w-full max-w-[1440px] bg-canvas/60 p-10 sm:p-16">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-3">
          {DEPARTMENTS.map((department) => (
            <Link
              key={department}
              to={`/department/${department}`}
              className="card-3d group flex flex-col items-center justify-center gap-6 rounded-2xl border border-line bg-white px-6 py-20"
            >
              <span className="text-5xl font-semibold leading-none tracking-tight text-brand-900 sm:text-6xl">
                {department}
              </span>
              <span className="h-px w-12 bg-line transition-colors group-hover:bg-brand-300" />
              <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-500 transition-colors group-hover:text-brand-700">
                {t('home.open')}
                <ArrowRight
                  className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
                  aria-hidden
                />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
