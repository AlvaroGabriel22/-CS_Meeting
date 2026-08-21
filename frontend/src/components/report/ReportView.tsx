import { cn } from '@/lib/utils'
import type { ReportBlock, ReportContent } from '@/types/api'

const ALIGN: Record<string, string> = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
}

const SIZE: Record<string, string> = {
  small: 'text-xs',
  normal: 'text-sm',
  large: 'text-base',
  heading: 'text-lg font-semibold',
}

/** a column never gets narrower than this: the table scrolls instead of squeezing */
export const MIN_COLUMN_WIDTH = 260

/** how tall an image may draw inside a cell, whatever the file's own size */
export const IMAGE_MAX_HEIGHT = 260

/** the widths the author picks from, as a share of the cell */
export const IMAGE_WIDTHS = [25, 50, 75, 100] as const

const FLEX_ALIGN: Record<string, string> = {
  left: 'justify-start',
  center: 'justify-center',
  right: 'justify-end',
}

/**
 * Draws one block of a cell — text, image or shape — exactly where the author
 * put it. A cell is an ordered list of these, so the same cell can hold text,
 * then a photo, then more text.
 */
export function Block({ block }: { block: ReportBlock }) {
  if (block.type === 'text') {
    return (
      <p
        className={cn(
          'whitespace-pre-wrap leading-relaxed text-ink-900',
          ALIGN[block.align] ?? 'text-left',
          SIZE[(block.size as string) ?? 'normal'] ?? 'text-sm',
          block.bold && 'font-semibold',
          block.italic && 'italic',
        )}
      >
        {block.text}
      </p>
    )
  }

  if (block.type === 'image') {
    return (
      <figure className={cn('flex flex-col', FLEX_ALIGN[block.align] ?? 'justify-start')}>
        {/* the width is the author's choice, the height cap is ours: a tall
            photo must not stretch the row it sits in */}
        <img
          src={block.url ?? ''}
          alt={block.caption ?? ''}
          style={{ width: `${block.width ?? 100}%`, maxHeight: IMAGE_MAX_HEIGHT }}
          className="rounded border border-line object-contain"
        />
        {block.caption && (
          <figcaption className={cn('mt-1 text-xs text-ink-500', ALIGN[block.align])}>
            {block.caption}
          </figcaption>
        )}
      </figure>
    )
  }

  return <Shape block={block} />
}

function Shape({ block }: { block: ReportBlock }) {
  const color = block.color ?? '#1E3A5F'
  const size = typeof block.size === 'number' ? block.size : 48

  const drawing = (() => {
    switch (block.shape) {
      case 'circle':
        return <span style={{ width: size, height: size, background: color }} className="block rounded-full" />
      case 'line':
        return <span style={{ width: size, height: 2, background: color }} className="block" />
      case 'divider':
        return <span style={{ height: 2, background: color }} className="block w-full" />
      case 'arrow':
        return (
          <svg width={size} height={12} viewBox={`0 0 ${size} 12`} aria-hidden>
            <line x1="0" y1="6" x2={size - 7} y2="6" stroke={color} strokeWidth="2" />
            <polygon points={`${size},6 ${size - 8},11 ${size - 8},1`} fill={color} />
          </svg>
        )
      default:
        return <span style={{ width: size, height: size, background: color }} className="block rounded-sm" />
    }
  })()

  return <span className={cn('flex', FLEX_ALIGN[block.align] ?? 'justify-start')}>{drawing}</span>
}

/**
 * The report as the author built it: their columns, their rows, and in each
 * cell the blocks in their order. Read-only — this is what a meeting sees.
 */
export function ReportView({ content }: { content: ReportContent }) {
  const { title, columns, rows } = content
  if (!columns.length && !rows.length && !title) return null

  return (
    <div className="space-y-3">
      {title && <h2 className="text-lg font-semibold text-brand-900">{title}</h2>}
      {columns.length > 0 && (
        <div className="table-scroll">
          {/* fixed layout: every column keeps its share of the width, so a
              large image can never push its neighbours off the page */}
          <table
            className="w-full table-fixed border-collapse text-sm"
            style={{ minWidth: columns.length * MIN_COLUMN_WIDTH }}
          >
            <thead>
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.id}
                    className="border border-line bg-brand-50 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-brand-900"
                  >
                    {column.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  {columns.map((column) => (
                    <td key={column.id} className="border border-line px-3 py-2 align-top">
                      <div className="space-y-2">
                        {(row.cells[column.id] ?? []).map((block) => (
                          <Block key={block.id} block={block} />
                        ))}
                      </div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
