import { useGlossary } from '@/lib/glossary'
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
export function IQCTable({ view, title }: { view: TableView; title?: string }) {
  const term = useGlossary()
  const headerRows = view.rows.filter((row) => row.kind === 'header')
  const bodyRows = view.rows.filter((row) => row.kind === 'data')

  return (
    <section className="min-w-0 overflow-hidden rounded-lg border border-line">
      <header className="border-b border-line px-4 py-2.5">
        <h3 className="text-sm font-semibold text-brand-900">
          {title || view.title || term(view.sheet)}
        </h3>
      </header>

      {/* the table is naturally wide: it scrolls, it is never broken up */}
      <div className="table-scroll">
        <table className="w-full border-collapse text-xs">
          <thead>
            <TableRows rows={headerRows} />
          </thead>
          <tbody>
            <TableRows rows={bodyRows} />
          </tbody>
        </table>
      </div>

    </section>
  )
}
