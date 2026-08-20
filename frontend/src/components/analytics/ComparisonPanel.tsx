import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { OptionSelect, PeriodSelect } from '@/components/analytics/PeriodSelect'
import { Card, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import type { ComparisonResponse, Period, PresentationVersion } from '@/types/api'

import { ComparisonTable } from './ComparisonTable'

/**
 * Period and version comparison, both driven by the page's selection.
 *
 * The analytical work is the backend's (Sprint 3 endpoints, unchanged); this
 * component only chooses what to ask for and shows the answer.
 */
export function ComparisonPanel({
  versionId,
  versions,
  periods,
  period,
  referencePeriod,
  table,
  metric,
}: {
  versionId: number
  versions: PresentationVersion[]
  periods: Period[]
  period: string
  referencePeriod: string | null
  table?: string
  metric?: string
}) {
  const { t } = useTranslation()
  const [against, setAgainst] = useState(referencePeriod ?? '')
  const [periodComparison, setPeriodComparison] = useState<ComparisonResponse | null>(null)
  const [otherVersion, setOtherVersion] = useState('')
  const [versionComparison, setVersionComparison] = useState<ComparisonResponse | null>(null)

  useEffect(() => setAgainst(referencePeriod ?? ''), [referencePeriod, versionId])

  useEffect(() => {
    if (!against || !period) {
      setPeriodComparison(null)
      return
    }
    let active = true
    void (async () => {
      try {
        const response = await api.comparePeriods(versionId, {
          periodA: against,
          periodB: period,
          table,
          metric,
        })
        if (active) setPeriodComparison(response)
      } catch {
        if (active) setPeriodComparison(null)
      }
    })()
    return () => {
      active = false
    }
  }, [versionId, against, period, table, metric])

  useEffect(() => {
    if (!otherVersion || !period) {
      setVersionComparison(null)
      return
    }
    let active = true
    void (async () => {
      try {
        const response = await api.compareVersions(versionId, Number(otherVersion), {
          period,
          table,
          metric,
        })
        if (active) setVersionComparison(response)
      } catch {
        if (active) setVersionComparison(null)
      }
    })()
    return () => {
      active = false
    }
  }, [versionId, otherVersion, period, table, metric])

  const otherVersions = versions.filter((version) => version.id !== versionId)

  return (
    <div className="space-y-4">
      {periodComparison && (
        <Card>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <CardTitle className="text-base">
              {t('analytics.periodComparison', { a: against, b: period })}
            </CardTitle>
            <PeriodSelect
              id="comparison-period-a"
              label={t('analytics.periodA')}
              periods={periods}
              value={against}
              onChange={setAgainst}
            />
          </div>
          <div className="mt-4">
            <ComparisonTable comparison={periodComparison} />
          </div>
        </Card>
      )}

      {otherVersions.length > 0 && (
        <Card>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <CardTitle className="text-base">{t('executive.compareVersions')}</CardTitle>
            <OptionSelect
              id="analytics-other-version"
              label={t('analytics.compareWith')}
              options={otherVersions.map((version) => ({
                value: String(version.id),
                label: `v${version.number}${version.label ? ` · ${version.label}` : ''}`,
              }))}
              value={otherVersion}
              onChange={setOtherVersion}
              allowEmpty={t('analytics.pickVersion')}
            />
          </div>
          {versionComparison && (
            <div className="mt-4">
              <ComparisonTable comparison={versionComparison} />
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
