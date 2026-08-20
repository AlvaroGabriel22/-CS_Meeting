import { ImagePlus, Loader2, Pencil, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Issue, IssueSeverity, IssueStatus, IssueUpdate } from '@/types/api'

const SEVERITY_STYLE: Record<IssueSeverity, string> = {
  high: 'border-l-critical',
  medium: 'border-l-warning',
  low: 'border-l-brand-300',
  info: 'border-l-line',
}

const STATUSES: IssueStatus[] = ['open', 'in_progress', 'resolved', 'closed']
const SEVERITIES: IssueSeverity[] = ['info', 'low', 'medium', 'high']

/**
 * One issue: the text a person wrote, and the numbers that justify it.
 *
 * Only the editorial half is editable here — the value, the period, the delta
 * and the origin cell come from the snapshot and are shown, never typed.
 */
export function IssueCard({
  issue,
  onUpdate,
  onAttach,
}: {
  issue: Issue
  onUpdate: (changes: IssueUpdate) => Promise<void>
  onAttach: (file: File) => Promise<void>
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [title, setTitle] = useState(issue.title)
  const [description, setDescription] = useState(issue.description ?? '')
  const fileRef = useRef<HTMLInputElement>(null)

  const save = async () => {
    setBusy(true)
    try {
      await onUpdate({ title, description })
      setEditing(false)
    } finally {
      setBusy(false)
    }
  }

  const change = async (changes: IssueUpdate) => {
    setBusy(true)
    try {
      await onUpdate(changes)
    } finally {
      setBusy(false)
    }
  }

  const origin = [issue.table, issue.category, issue.subcategory, issue.metric]
    .filter(Boolean)
    .join(' · ')

  return (
    <article className={cn('surface-card border-l-4 p-4', SEVERITY_STYLE[issue.severity])}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {editing ? (
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="w-full rounded-lg border border-line px-3 py-2 text-sm font-semibold text-ink-900 focus:border-brand-300 focus:outline-none"
            />
          ) : (
            <h3 className="text-sm font-semibold text-brand-900">{issue.title}</h3>
          )}
          <p className="mt-1 text-xs text-ink-500">
            {origin}
            {issue.period ? ` · ${issue.period.label}` : ''}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={issue.status}
            disabled={busy}
            onChange={(event) => void change({ status: event.target.value as IssueStatus })}
            className="rounded-lg border border-line bg-white px-2 py-1 text-xs text-ink-700 focus:border-brand-300 focus:outline-none"
            aria-label={t('issues.status')}
          >
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {t(`issues.statuses.${status}`)}
              </option>
            ))}
          </select>
          <select
            value={issue.severity}
            disabled={busy}
            onChange={(event) => void change({ severity: event.target.value as IssueSeverity })}
            className="rounded-lg border border-line bg-white px-2 py-1 text-xs text-ink-700 focus:border-brand-300 focus:outline-none"
            aria-label={t('issues.severity')}
          >
            {SEVERITIES.map((severity) => (
              <option key={severity} value={severity}>
                {t(`issues.severities.${severity}`)}
              </option>
            ))}
          </select>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setEditing((current) => !current)}
            aria-label={t('issues.edit')}
          >
            {editing ? <X className="h-4 w-4" aria-hidden /> : <Pencil className="h-4 w-4" aria-hidden />}
          </Button>
        </div>
      </header>

      {/* the numbers: read from the snapshot, shown but never typed */}
      <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs">
        {issue.value !== null && (
          <div className="flex items-baseline gap-2">
            <dt className="text-ink-500">{issue.metric}</dt>
            <dd className="font-semibold tabular-nums text-brand-900">
              {issue.value.toLocaleString()}
            </dd>
          </div>
        )}
        {issue.delta !== null && (
          <div className="flex items-baseline gap-2">
            <dt className="text-ink-500">
              {issue.referencePeriod ? `vs ${issue.referencePeriod.label}` : t('analytics.delta')}
            </dt>
            <dd className="tabular-nums text-ink-700">
              {issue.delta > 0 ? '+' : ''}
              {issue.delta.toLocaleString()}
              {issue.deltaPercent !== null &&
                ` (${issue.deltaPercent > 0 ? '+' : ''}${issue.deltaPercent.toFixed(1)}%)`}
            </dd>
          </div>
        )}
        {issue.trend && issue.trend.classification !== 'insufficient_data' && (
          <div className="flex items-baseline gap-2">
            <dt className="text-ink-500">{t('issues.trend')}</dt>
            <dd className="text-ink-700">
              {t(`trends.${issue.trend.classification}`)}
              {issue.trend.quality !== 'unknown' && ` · ${t(`trends.${issue.trend.quality}`)}`}
            </dd>
          </div>
        )}
      </dl>

      {editing ? (
        <div className="mt-3 space-y-2">
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            placeholder={t('issues.descriptionPlaceholder')}
            className="w-full rounded-lg border border-line px-3 py-2 text-sm text-ink-900 focus:border-brand-300 focus:outline-none"
          />
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => void save()} disabled={busy}>
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
              {t('common.save')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setEditing(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      ) : (
        issue.description && (
          <p className="mt-3 whitespace-pre-line text-sm text-ink-700">{issue.description}</p>
        )
      )}

      {issue.media.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-3">
          {issue.media.map((media) => (
            <figure key={media.id} className="w-40">
              <img
                src={media.url}
                alt={media.caption ?? issue.title}
                className="h-24 w-full rounded-lg border border-line object-cover"
              />
              {media.caption && (
                <figcaption className="mt-1 text-[11px] text-ink-500">{media.caption}</figcaption>
              )}
            </figure>
          ))}
        </div>
      )}

      <footer className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2">
        <span className="font-mono text-[11px] text-ink-300">
          {issue.sourceRange}
          {issue.sourceCell ? ` · ${issue.sourceCell}` : ''} · v{issue.versionId}
        </span>
        <>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void onAttach(file)
              event.target.value = ''
            }}
          />
          <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()} disabled={busy}>
            <ImagePlus className="h-4 w-4" aria-hidden />
            {t('issues.attach')}
          </Button>
        </>
      </footer>
    </article>
  )
}
