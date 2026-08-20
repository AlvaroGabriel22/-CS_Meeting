import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { RenderRow, TableView } from '@/types/api'

import { IQCCell } from './IQCCell'

function TableRows({ rows }: { rows: RenderRow[] }) {
  return (
    <>
      {rows.map((row) => (
        <tr
          key={row.index}
          data-block={row.block}
          data-depth={row.depth}
          className={cn(row.isHeadline && row.kind === 'data' && 'bg-brand-50/40')}
        >
          {row.cells.map((cell) => (
            <IQCCell key={`${cell.row}-${cell.col}`} cell={cell} />
          ))}
        </tr>
      ))}
    </>
  )
}

/**
 * Draws one normalized table.
 *
 * Everything structural — how many columns, which periods, where the merges
 * are, how deep a row sits — comes from the model. This component knows no
 * month, no quarter and no week name.
 */
export function IQCTable({ view }: { view: TableView }) {
  const { t } = useTranslation()
  const headerRows = view.rows.filter((row) => row.kind === 'header')
  const bodyRows = view.rows.filter((row) => row.kind === 'data')

  return (
    <section className="surface-card overflow-hidden p-0">
      <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line px-5 py-4">
        <div className="flex items-baseline gap-3">
          <h3 className="text-lg font-semibold text-brand-900">{view.title ?? view.sheet}</h3>
          <span className="text-xs text-ink-500">
            {view.hierarchy.join(' › ')}
            {view.meta.reportingYear ? ` · ${view.meta.reportingYear}` : ''}
          </span>
        </div>
        <span className="font-mono text-xs text-ink-300" title={t('common.sourceRange')}>
          {view.sheet}!{view.sourceRange}
        </span>
      </header>

      {/* the table is naturally wide: it scrolls, it is never broken up */}
      <div className="table-scroll">
        <table className="w-full border-collapse text-sm">
          <thead>
            <TableRows rows={headerRows} />
          </thead>
          <tbody>
            <TableRows rows={bodyRows} />
          </tbody>
        </table>
      </div>

      {view.warnings.length > 0 && (
        <footer className="border-t border-line px-5 py-2 text-xs text-ink-500">
          {view.warnings.map((warning) => (
            <code key={warning} className="mr-3 font-mono">
              {warning}
            </code>
          ))}
        </footer>
      )}
    </section>
  )
}
