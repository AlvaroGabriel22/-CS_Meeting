import type { CSSProperties } from 'react'

import { useGlossary } from '@/lib/glossary'
import { cn } from '@/lib/utils'
import type { RenderCell } from '@/types/api'

/** Border sides the workbook draws — nothing is added, nothing is removed. */
function borderStyle(cell: RenderCell): CSSProperties {
  const rule = '1px solid var(--color-line-strong)'
  return {
    borderTop: cell.borders.includes('top') ? rule : undefined,
    borderRight: cell.borders.includes('right') ? rule : undefined,
    borderBottom: cell.borders.includes('bottom') ? rule : undefined,
    borderLeft: cell.borders.includes('left') ? rule : undefined,
    backgroundColor: cell.fillColor ? `#${cell.fillColor}` : undefined,
    color: cell.textColor ? `#${cell.textColor}` : undefined,
    paddingLeft: cell.indent ? `${0.75 + cell.indent * 0.9}rem` : undefined,
  }
}

const ALIGN: Record<string, string> = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
  justify: 'text-justify',
}

/**
 * One structural cell.
 *
 * A merged range in Excel is a single cell here, carrying its spans; the
 * coordinates it covers are simply absent from the model. Empty cells stay
 * empty — the IQC headline rows hold the block's figure and no metric name, so
 * nothing may be written into them.
 *
 * A label, a corner and a period header read in the reader's language through
 * the glossary; a value never does (ADR-0044).
 */
export function IQCCell({ cell }: { cell: RenderCell }) {
  const term = useGlossary()
  const Tag = cell.kind === 'corner' || cell.kind === 'period' ? 'th' : 'td'
  const isNumber = cell.kind === 'value'
  const isWords = cell.kind === 'label' || cell.kind === 'corner' || cell.kind === 'period'
  const text = isWords ? term(cell.text) : cell.text

  return (
    <Tag
      scope={cell.kind === 'period' ? 'col' : undefined}
      rowSpan={cell.rowSpan > 1 ? cell.rowSpan : undefined}
      colSpan={cell.colSpan > 1 ? cell.colSpan : undefined}
      style={borderStyle(cell)}
      data-kind={cell.kind}
      data-source={cell.source ?? undefined}
      data-sticky={cell.col === 0 ? 'true' : undefined}
      className={cn(
        'px-2 py-1 align-middle',
        ALIGN[cell.align] ?? 'text-left',
        cell.wrap ? 'whitespace-normal' : 'whitespace-nowrap',
        isNumber && 'tabular-nums',
        cell.bold && 'font-semibold',
        cell.kind === 'corner' && 'bg-brand-700 text-white',
        cell.kind === 'period' && 'bg-brand-50 text-brand-900',
        cell.kind === 'label' && 'text-ink-900',
        cell.isHeadline && cell.kind === 'label' && 'font-semibold text-brand-900',
      )}
    >
      {text}
      {!cell.text && cell.inferredText && (
        // the workbook does not say this; the parser read it. Shown apart so it
        // can never be mistaken for the file's own content.
        <span className="italic text-ink-300">{term(cell.inferredText)}</span>
      )}
    </Tag>
  )
}
