import { Loader2, Plus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Card, CardDescription } from '@/components/ui/card'
import { api } from '@/lib/api'
import type { Insight, Issue, IssueUpdate } from '@/types/api'

import { IssueCard } from './IssueCard'

/**
 * The issues raised on the selected snapshot and period.
 *
 * An issue is created from an insight: the client says *what* it is about and
 * the backend attaches the numbers, so an issue can always be proved.
 */
export function IssuesSection({
  versionId,
  period,
  table,
  metric,
  insights,
}: {
  versionId: number
  period: string
  table?: string
  metric?: string
  insights: Insight[]
}) {
  const { t } = useTranslation()
  const [issues, setIssues] = useState<Issue[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (!versionId || !period) return
    setLoading(true)
    try {
      setIssues(await api.listIssues(versionId, { period }))
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setLoading(false)
    }
  }, [versionId, period])

  useEffect(() => {
    void reload()
  }, [reload])

  const raiseFrom = async (insight: Insight) => {
    setCreating(true)
    try {
      await api.createIssue(versionId, {
        period: insight.period?.label ?? period,
        table: insight.table ?? table,
        category: insight.category ?? undefined,
        subcategory: insight.subcategory ?? undefined,
        metric: insight.metric ?? metric,
        title: insight.text.slice(0, 200),
        origin: { kind: insight.kind, template: insight.template, score: insight.score },
      })
      await reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setCreating(false)
    }
  }

  const update = async (issue: Issue, changes: IssueUpdate) => {
    await api.updateIssue(versionId, issue.id, changes)
    await reload()
  }

  const attach = async (issue: Issue, file: File) => {
    await api.attachIssueImage(versionId, issue.id, file)
    await reload()
  }

  const candidates = insights.filter(
    (insight) => !issues.some((issue) => issue.origin?.template === insight.template
      && issue.category === insight.category
      && issue.metric === insight.metric),
  )

  return (
    <div className="space-y-4">
      {error && (
        <Card className="border-critical/30 bg-critical/5">
          <CardDescription className="text-critical">{error}</CardDescription>
        </Card>
      )}

      {loading && issues.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-ink-500">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          {t('common.loading')}
        </p>
      ) : (
        issues.map((issue) => (
          <IssueCard
            key={issue.id}
            issue={issue}
            onUpdate={(changes) => update(issue, changes)}
            onAttach={(file) => attach(issue, file)}
          />
        ))
      )}

      {issues.length === 0 && !loading && (
        <Card>
          <CardDescription>{t('issues.empty')}</CardDescription>
        </Card>
      )}

      {candidates.length > 0 && (
        <Card>
          <CardDescription className="mb-3">{t('issues.raiseFromInsight')}</CardDescription>
          <ul className="space-y-2">
            {candidates.slice(0, 4).map((insight, index) => (
              <li
                key={`${insight.template}-${insight.category}-${insight.metric}-${index}`}
                className="flex items-start justify-between gap-3 text-sm"
              >
                <span className="text-ink-700">{insight.text}</span>
                <button
                  type="button"
                  onClick={() => void raiseFrom(insight)}
                  disabled={creating}
                  className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs font-medium text-brand-700 hover:border-brand-300"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden />
                  {t('issues.raise')}
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
