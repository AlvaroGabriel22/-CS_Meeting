import {
  Bar,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTranslation } from 'react-i18next'

import { useGlossary } from '@/lib/glossary'
import type { Chart, ChartPoint } from '@/types/api'

/** the department palette: navy for the whole, lighter blues for the parts */
const BAR_COLORS = ['#1e3a5f', '#6a8fbe', '#9dbadd', '#c7d9ef']
const LINE_COLOR = '#b3382f'

/** a pair chart: the closing years stand apart from the months of this one */
const YEAR_BAR = '#1e3a5f'
const MONTH_BAR = '#9dbadd'
const TARGET_LINE = '#4a7fbf'

/**
 * The charts of a department page, side by side, in the workbook's order.
 *
 * Two shapes, both drawn from values the file already holds:
 *
 * - `components` — the parts of a table as bars with its total as a line.
 *   IQC stacks them, and the backend has already shared the total out among
 *   the parts, so the column closes on the line (ADR-0046);
 * - `pair` — one model's result as bars against its target as the line. The
 *   line is cut where the axis changes granularity, because a segment from a
 *   year to a month would state a trend that does not exist (ADR-0047).
 *
 * Nothing is computed here. The bars are the numbers that arrived, the labels
 * are the strings that arrived, and a gap in the file stays a gap.
 */
export function DepartmentCharts({
  charts,
  titles = {},
}: {
  charts: Chart[]
  /** the department's titles, translated when the reader asked for it */
  titles?: Record<string, string>
}) {
  if (charts.length === 0) return null

  const columns =
    charts.length === 1 ? 'lg:grid-cols-1' : charts.length === 2 ? 'lg:grid-cols-2' : 'lg:grid-cols-3'

  return (
    <div className={`surface-card grid gap-4 p-4 ${columns}`}>
      {charts.map((chart) => (
        <OneChart key={chart.id} chart={chart} title={titles[chart.id] ?? titles[chart.table]} />
      ))}
    </div>
  )
}

function OneChart({ chart, title }: { chart: Chart; title?: string }) {
  const term = useGlossary()
  const { i18n } = useTranslation()

  const isPair = chart.kind === 'pair'
  const lineLabel = chart.line ? term(chart.line.label) : null

  // the axis and the legend read in the reader's language; the values do not
  const data = chart.periods.map((period, index) => {
    const row: Record<string, string | number | null> = { period: term(period.label), index }
    for (const series of chart.bars) row[term(series.label)] = series.points[index]?.value ?? null
    if (chart.line && lineLabel) {
      // a broken line is drawn as one series per block: the gaps between them
      // are what keeps recharts from joining a year to a month
      for (const [block, range] of blocksOf(chart.breaks, chart.periods.length).entries()) {
        row[`${lineLabel}__${block}`] =
          index >= range[0] && index < range[1] ? (chart.line.points[index]?.value ?? null) : null
      }
    }
    return row
  })

  const blocks = blocksOf(chart.breaks, chart.periods.length)
  const display = (series: 'bar' | 'line', key: number, index: number) =>
    series === 'bar' ? chart.bars[key]?.points[index] : chart.line?.points[index]

  const label = title || chart.title || defaultTitle(chart, term)

  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 text-sm font-semibold text-brand-900">{label}</figcaption>
      {/* the legend is measured by the chart library and can lag behind a
          shrinking container: clipping keeps a stale measurement from pushing
          the page sideways */}
      <div className="h-[300px] overflow-hidden">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 18, right: 8, bottom: 4, left: 0 }}>
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: '#6b7d94' }}
              tickLine={false}
              axisLine={{ stroke: '#d5dde8' }}
            />
            {/* a second, invisible axis measured in column positions: it is the
                only way to draw the seam *between* two columns rather than
                through the middle of one */}
            <XAxis
              xAxisId="position"
              type="number"
              domain={[-0.5, chart.periods.length - 0.5]}
              hide
            />
            {/* the axis still sets the scale the bars are drawn against; it
                simply is not printed — the values are read on the bars, in the
                table below and in the tooltip */}
            <YAxis hide />
            <Tooltip
              cursor={{ fill: '#f1f5fa' }}
              content={<ChartTooltip language={i18n.language} />}
              wrapperStyle={{ outline: 'none' }}
            />
            <Legend wrapperStyle={{ fontSize: 11, maxWidth: '100%' }} />
            {chart.breaks.map((position) => (
              <ReferenceLine
                key={position}
                xAxisId="position"
                x={position - 0.5}
                stroke="#c7d3e2"
                strokeDasharray="3 3"
              />
            ))}
            {chart.bars.map((series, seriesIndex) => (
              <Bar
                key={series.key}
                dataKey={term(series.label)}
                stackId={chart.stacked ? 'parts' : undefined}
                fill={BAR_COLORS[seriesIndex % BAR_COLORS.length]}
                radius={
                  chart.stacked && seriesIndex < chart.bars.length - 1 ? undefined : [2, 2, 0, 0]
                }
                maxBarSize={34}
                isAnimationActive={false}
                label={
                  <ValueLabel
                    inside={chart.stacked}
                    language={i18n.language}
                    pointAt={(index) => display('bar', seriesIndex, index)}
                  />
                }
              >
                {isPair
                  ? chart.periods.map((period) => (
                      <Cell
                        key={period.label}
                        fill={period.kind === 'year' ? YEAR_BAR : MONTH_BAR}
                      />
                    ))
                  : null}
              </Bar>
            ))}
            {chart.line && lineLabel
              ? blocks.map((_range, block) => (
                  <Line
                    key={block}
                    type="monotone"
                    dataKey={`${lineLabel}__${block}`}
                    name={lineLabel}
                    stroke={isPair ? TARGET_LINE : LINE_COLOR}
                    strokeWidth={2}
                    dot={
                      isPair
                        ? { r: 3, fill: '#ffffff', stroke: TARGET_LINE, strokeWidth: 2 }
                        : { r: 2.5 }
                    }
                    legendType={block === 0 ? 'line' : 'none'}
                    isAnimationActive={false}
                    connectNulls={false}
                  />
                ))
              : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

/** The name of a chart nobody has renamed: its table, or the model it plots. */
function defaultTitle(chart: Chart, term: (text: string) => string): string {
  if (chart.kind !== 'pair') return term(chart.table)
  const parts = [chart.category, chart.subcategory].filter(Boolean) as string[]
  return parts.length ? parts.map(term).join(' · ') : term(chart.table)
}

/** The index ranges the line is drawn in, split at every break. */
function blocksOf(breaks: number[], length: number): [number, number][] {
  const edges = [0, ...breaks.filter((index) => index > 0 && index < length), length]
  const blocks: [number, number][] = []
  for (let i = 0; i < edges.length - 1; i += 1) blocks.push([edges[i], edges[i + 1]])
  return blocks
}

function formatValue(point: ChartPoint | undefined, value: number, language: string): string {
  // the workbook's own formatting when it has one; a shared bar has none,
  // because no single cell holds it
  if (point?.display) return point.display
  return value.toLocaleString(language, {
    maximumFractionDigits: Math.abs(value) < 10 ? 2 : 0,
  })
}

/**
 * The value written on the bar: inside it when it is tall enough to hold the
 * text, above it otherwise. A segment too short for a legible number is left
 * unlabelled rather than overprinted.
 */
function ValueLabel(props: {
  inside: boolean
  language: string
  pointAt: (index: number) => ChartPoint | undefined
  // supplied by recharts
  x?: number
  y?: number
  width?: number
  height?: number
  value?: number
  index?: number
}) {
  const { inside, language, pointAt, x = 0, y = 0, width = 0, height = 0, index = 0 } = props
  // never the number recharts hands over: on a stacked bar that is the top of
  // the stack so far, and the label must say what *this* segment is worth
  const point = pointAt(index)
  const value = point?.value
  if (value === null || value === undefined || Number.isNaN(value)) return null

  const text = formatValue(point, value, language)
  const fitsInside = inside && height >= 16
  if (inside && !fitsInside) return null

  return (
    <text
      x={x + width / 2}
      y={fitsInside ? y + height / 2 : y - 5}
      textAnchor="middle"
      dominantBaseline={fitsInside ? 'middle' : 'auto'}
      fontSize={10}
      fill={fitsInside ? '#ffffff' : '#44556b'}
    >
      {text}
    </text>
  )
}

/**
 * One tooltip line per series that actually has a reading here. A line drawn
 * in blocks contributes several keys and only one of them is ever filled, so
 * the empty ones are dropped instead of being shown as blanks.
 */
function ChartTooltip({
  active,
  payload,
  label,
  language,
}: {
  active?: boolean
  payload?: { name?: string; value?: number | null; color?: string }[]
  label?: string
  language: string
}) {
  if (!active || !payload?.length) return null
  const seen = new Set<string>()
  const entries = payload.filter((entry) => {
    const name = entry.name ?? ''
    if (entry.value === null || entry.value === undefined || seen.has(name)) return false
    seen.add(name)
    return true
  })
  if (!entries.length) return null

  return (
    <div className="rounded-lg border border-line bg-white px-2.5 py-1.5 text-xs shadow-sm">
      <p className="mb-1 font-semibold text-brand-900">{label}</p>
      {entries.map((entry) => (
        <p key={entry.name} className="flex items-center gap-1.5 text-ink-600">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span>{entry.name}</span>
          <span className="font-medium text-ink-900">
            {(entry.value as number).toLocaleString(language, {
              maximumFractionDigits: Math.abs(entry.value as number) < 10 ? 2 : 0,
            })}
          </span>
        </p>
      ))}
    </div>
  )
}
