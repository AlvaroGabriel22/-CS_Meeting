import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  ArrowDown,
  ArrowUp,
  Bold,
  Image as ImageIcon,
  Italic,
  Plus,
  Shapes,
  Trash2,
  Type,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Block, IMAGE_WIDTHS, MIN_COLUMN_WIDTH } from '@/components/report/ReportView'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type {
  BlockAlign,
  ReportBlock,
  ReportColumn,
  ReportContent,
  ReportRow,
  ShapeKind,
  TextSize,
} from '@/types/api'

const SHAPES: ShapeKind[] = ['rectangle', 'circle', 'line', 'arrow', 'divider']
const SIZES: TextSize[] = ['small', 'normal', 'large', 'heading']

const newId = () => Math.random().toString(36).slice(2, 10)

/**
 * The report editor: the author's table, built by hand.
 *
 * Columns are created, renamed, reordered and deleted; rows are added without
 * limit; and each cell is an ordered list of blocks the author arranges — text,
 * image or shape, in any order, with the alignment they choose.
 *
 * Nothing here suggests content. Every block, every word and every position is
 * the author's decision.
 */
export function ReportBuilder({
  versionId,
  content,
  onChange,
}: {
  versionId: number
  content: ReportContent
  onChange: (next: ReportContent) => void
}) {
  const { t } = useTranslation()
  const [selected, setSelected] = useState<{ row: string; column: string } | null>(null)

  const update = (patch: Partial<ReportContent>) => onChange({ ...content, ...patch })

  // --- columns -------------------------------------------------------------
  const addColumn = () =>
    update({ columns: [...content.columns, { id: newId(), name: '' }] })

  const renameColumn = (id: string, name: string) =>
    update({
      columns: content.columns.map((column) => (column.id === id ? { ...column, name } : column)),
    })

  const moveColumn = (index: number, delta: number) => {
    const next = [...content.columns]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    update({ columns: next })
  }

  const removeColumn = (id: string) =>
    update({
      columns: content.columns.filter((column) => column.id !== id),
      rows: content.rows.map((row) => {
        const cells = { ...row.cells }
        delete cells[id]
        return { ...row, cells }
      }),
    })

  // --- rows ----------------------------------------------------------------
  const addRow = () => {
    const cells: Record<string, ReportBlock[]> = {}
    for (const column of content.columns) cells[column.id] = []
    update({ rows: [...content.rows, { id: newId(), cells }] })
  }

  const moveRow = (index: number, delta: number) => {
    const next = [...content.rows]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    update({ rows: next })
  }

  const removeRow = (id: string) =>
    update({ rows: content.rows.filter((row) => row.id !== id) })

  // --- blocks --------------------------------------------------------------
  const setCell = (rowId: string, columnId: string, blocks: ReportBlock[]) =>
    update({
      rows: content.rows.map((row) =>
        row.id === rowId ? { ...row, cells: { ...row.cells, [columnId]: blocks } } : row,
      ),
    })

  const cellOf = (row: ReportRow, columnId: string) => row.cells[columnId] ?? []

  return (
    <div className="space-y-4">
      <label className="block">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-500">
          {t('report.reportTitle')}
        </span>
        <input
          value={content.title}
          onChange={(event) => update({ title: event.target.value })}
          placeholder={t('report.titlePlaceholder')}
          className="mt-1 w-full rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand-400"
        />
      </label>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={addColumn}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm text-ink-700 hover:border-brand-300"
        >
          <Plus className="h-4 w-4" aria-hidden />
          {t('report.addColumn')}
        </button>
        <button
          type="button"
          onClick={addRow}
          disabled={content.columns.length === 0}
          title={content.columns.length === 0 ? t('report.startWithAColumn') : undefined}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm text-ink-700 hover:border-brand-300 disabled:opacity-50"
        >
          <Plus className="h-4 w-4" aria-hidden />
          {t('report.addRow')}
        </button>
      </div>

      {content.columns.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-sm text-ink-500">
          {t('report.startWithAColumn')}
        </p>
      ) : (
        <div className="table-scroll">
          <table
            className="w-full table-fixed border-collapse text-sm"
            style={{ minWidth: content.columns.length * MIN_COLUMN_WIDTH + 48 }}
          >
            <thead>
              <tr>
                <th className="w-12 border border-line bg-brand-50 px-2 py-2" />
                {content.columns.map((column, index) => (
                  <ColumnHeader
                    key={column.id}
                    column={column}
                    index={index}
                    count={content.columns.length}
                    onRename={(name) => renameColumn(column.id, name)}
                    onMove={(delta) => moveColumn(index, delta)}
                    onRemove={() => removeColumn(column.id)}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {content.rows.map((row, index) => (
                <tr key={row.id}>
                  <td className="border border-line px-1 py-2 align-top">
                    <div className="flex flex-col items-center gap-1">
                      <IconButton
                        label={t('report.moveUp')}
                        onClick={() => moveRow(index, -1)}
                        disabled={index === 0}
                      >
                        <ArrowUp className="h-3.5 w-3.5" />
                      </IconButton>
                      <IconButton
                        label={t('report.moveDown')}
                        onClick={() => moveRow(index, 1)}
                        disabled={index === content.rows.length - 1}
                      >
                        <ArrowDown className="h-3.5 w-3.5" />
                      </IconButton>
                      <IconButton label={t('report.removeRow')} onClick={() => removeRow(row.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </IconButton>
                    </div>
                  </td>
                  {content.columns.map((column) => (
                    <CellEditor
                      key={column.id}
                      versionId={versionId}
                      blocks={cellOf(row, column.id)}
                      active={selected?.row === row.id && selected?.column === column.id}
                      onFocus={() => setSelected({ row: row.id, column: column.id })}
                      onChange={(blocks) => setCell(row.id, column.id, blocks)}
                    />
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

function ColumnHeader({
  column,
  index,
  count,
  onRename,
  onMove,
  onRemove,
}: {
  column: ReportColumn
  index: number
  count: number
  onRename: (name: string) => void
  onMove: (delta: number) => void
  onRemove: () => void
}) {
  const { t } = useTranslation()
  return (
    <th className="border border-line bg-brand-50 px-2 py-2 align-top">
      <input
        value={column.name}
        onChange={(event) => onRename(event.target.value)}
        placeholder={t('report.columnName')}
        className="w-full rounded border border-line bg-white px-2 py-1 text-sm font-semibold text-brand-900 outline-none focus:border-brand-400"
      />
      <div className="mt-1 flex items-center gap-1">
        <IconButton label={t('report.moveLeft')} onClick={() => onMove(-1)} disabled={index === 0}>
          <ArrowUp className="h-3.5 w-3.5 -rotate-90" />
        </IconButton>
        <IconButton
          label={t('report.moveRight')}
          onClick={() => onMove(1)}
          disabled={index === count - 1}
        >
          <ArrowDown className="h-3.5 w-3.5 -rotate-90" />
        </IconButton>
        <IconButton label={t('report.removeColumn')} onClick={onRemove}>
          <Trash2 className="h-3.5 w-3.5" />
        </IconButton>
      </div>
    </th>
  )
}

function CellEditor({
  versionId,
  blocks,
  active,
  onFocus,
  onChange,
}: {
  versionId: number
  blocks: ReportBlock[]
  active: boolean
  onFocus: () => void
  onChange: (blocks: ReportBlock[]) => void
}) {
  const { t } = useTranslation()
  const fileInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const add = (block: ReportBlock) => onChange([...blocks, block])
  const patch = (id: string, changes: Partial<ReportBlock>) =>
    onChange(blocks.map((block) => (block.id === id ? { ...block, ...changes } : block)))
  const remove = (id: string) => onChange(blocks.filter((block) => block.id !== id))
  const move = (index: number, delta: number) => {
    const next = [...blocks]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next)
  }

  const upload = async (file: File) => {
    setBusy(true)
    setError(null)
    try {
      // the file is stored byte for byte — nothing is re-encoded, so a large
      // photo keeps its quality; the backend refuses anything over its limit
      const uploaded = await api.uploadReportImage(versionId, file)
      add({
        id: newId(),
        type: 'image',
        align: 'left',
        assetId: uploaded.assetId,
        url: uploaded.url,
        caption: '',
        width: 50,
      })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <td
      onFocus={onFocus}
      onClick={onFocus}
      className={cn('border border-line px-2 py-2 align-top', active && 'bg-brand-50/40')}
    >
      <div className="space-y-2">
        {blocks.map((block, index) => (
          <div key={block.id} className="rounded border border-line/70 p-2">
            <div className="mb-1 flex flex-wrap items-center gap-1">
              <IconButton label={t('report.moveUp')} onClick={() => move(index, -1)} disabled={index === 0}>
                <ArrowUp className="h-3.5 w-3.5" />
              </IconButton>
              <IconButton
                label={t('report.moveDown')}
                onClick={() => move(index, 1)}
                disabled={index === blocks.length - 1}
              >
                <ArrowDown className="h-3.5 w-3.5" />
              </IconButton>
              {(['left', 'center', 'right'] as BlockAlign[]).map((align) => (
                <IconButton
                  key={align}
                  label={align}
                  active={block.align === align}
                  onClick={() => patch(block.id, { align })}
                >
                  {align === 'left' ? (
                    <AlignLeft className="h-3.5 w-3.5" />
                  ) : align === 'center' ? (
                    <AlignCenter className="h-3.5 w-3.5" />
                  ) : (
                    <AlignRight className="h-3.5 w-3.5" />
                  )}
                </IconButton>
              ))}
              {block.type === 'text' && (
                <>
                  <IconButton
                    label="bold"
                    active={Boolean(block.bold)}
                    onClick={() => patch(block.id, { bold: !block.bold })}
                  >
                    <Bold className="h-3.5 w-3.5" />
                  </IconButton>
                  <IconButton
                    label="italic"
                    active={Boolean(block.italic)}
                    onClick={() => patch(block.id, { italic: !block.italic })}
                  >
                    <Italic className="h-3.5 w-3.5" />
                  </IconButton>
                  <select
                    value={(block.size as TextSize) ?? 'normal'}
                    onChange={(event) => patch(block.id, { size: event.target.value as TextSize })}
                    className="rounded border border-line px-1 py-0.5 text-xs"
                  >
                    {SIZES.map((size) => (
                      <option key={size} value={size}>
                        {t(`report.size.${size}`)}
                      </option>
                    ))}
                  </select>
                </>
              )}
              {block.type === 'shape' && (
                <>
                  <select
                    value={block.shape ?? 'rectangle'}
                    onChange={(event) => patch(block.id, { shape: event.target.value as ShapeKind })}
                    className="rounded border border-line px-1 py-0.5 text-xs"
                  >
                    {SHAPES.map((shape) => (
                      <option key={shape} value={shape}>
                        {t(`report.shape.${shape}`)}
                      </option>
                    ))}
                  </select>
                  <input
                    type="color"
                    value={block.color ?? '#1E3A5F'}
                    onChange={(event) => patch(block.id, { color: event.target.value })}
                    className="h-6 w-8 rounded border border-line"
                  />
                </>
              )}
              {block.type === 'image' && (
                <span className="flex items-center gap-0.5" title={t('report.imageWidth')}>
                  {IMAGE_WIDTHS.map((width) => (
                    <button
                      key={width}
                      type="button"
                      onClick={() => patch(block.id, { width })}
                      className={cn(
                        'rounded border px-1.5 py-0.5 text-[11px] tabular-nums',
                        (block.width ?? 100) === width
                          ? 'border-brand-300 bg-brand-50 text-brand-800'
                          : 'border-line text-ink-500 hover:border-brand-300',
                      )}
                    >
                      {width}%
                    </button>
                  ))}
                </span>
              )}
              <span className="flex-1" />
              <IconButton label={t('report.removeBlock')} onClick={() => remove(block.id)}>
                <Trash2 className="h-3.5 w-3.5" />
              </IconButton>
            </div>

            {block.type === 'text' ? (
              <textarea
                value={block.text ?? ''}
                onChange={(event) => patch(block.id, { text: event.target.value })}
                rows={2}
                placeholder={t('report.textPlaceholder')}
                className="w-full rounded border border-line px-2 py-1 text-sm outline-none focus:border-brand-400"
              />
            ) : block.type === 'image' ? (
              <div className="space-y-1">
                <Block block={block} />
                <input
                  value={block.caption ?? ''}
                  onChange={(event) => patch(block.id, { caption: event.target.value })}
                  placeholder={t('report.captionPlaceholder')}
                  className="w-full rounded border border-line px-2 py-1 text-xs outline-none focus:border-brand-400"
                />
              </div>
            ) : (
              <Block block={block} />
            )}
          </div>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1">
        <input
          ref={fileInput}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) void upload(file)
            event.target.value = ''
          }}
        />
        <SmallButton
          onClick={() => add({ id: newId(), type: 'text', align: 'left', text: '', size: 'normal' })}
        >
          <Type className="h-3.5 w-3.5" aria-hidden />
          {t('report.addText')}
        </SmallButton>
        <SmallButton onClick={() => fileInput.current?.click()} disabled={busy}>
          <ImageIcon className="h-3.5 w-3.5" aria-hidden />
          {t('report.addImage')}
        </SmallButton>
        {error && <span className="w-full text-xs text-critical">{error}</span>}
        <SmallButton
          onClick={() =>
            add({ id: newId(), type: 'shape', align: 'left', shape: 'rectangle', color: '#1E3A5F', size: 48 })
          }
        >
          <Shapes className="h-3.5 w-3.5" aria-hidden />
          {t('report.addShape')}
        </SmallButton>
      </div>
    </td>
  )
}

function IconButton({
  children,
  label,
  onClick,
  disabled,
  active,
}: {
  children: React.ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
  active?: boolean
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded border border-transparent p-1 text-ink-500 hover:border-line hover:text-brand-700 disabled:opacity-30',
        active && 'border-brand-300 bg-brand-50 text-brand-800',
      )}
    >
      {children}
    </button>
  )
}

function SmallButton({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1 rounded border border-line px-2 py-1 text-xs text-ink-600 hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
    >
      {children}
    </button>
  )
}
