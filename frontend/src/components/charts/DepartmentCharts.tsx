import {
  Bar,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { Chart } from '@/types/api'

const BAR_COLORS = ['#1e3a5f', '#6a8fbe', '#9dbadd', '#c7d9ef']
const LINE_COLOR = '#b3382f'

/**
 * One chart per table, side by side, in the workbook's order.
 *
 * Vertical bars for the parts and a line for the whole, over the periods the
 * file carries. When the backend says the parts add up (`stacked`), the bars
 * are stacked so the column reads as the total; otherwise they stand side by
 * side. Every number comes from the workbook: the user does the arithmetic in
 * Excel and the system only draws the result.
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

  return (
    <div className="surface-card grid gap-4 p-4 lg:grid-cols-3">
      {charts.map((chart) => (
        <OneChart
          key={`${chart.sheet}-${chart.sourceRange}`}
          chart={chart}
          title={titles[chart.table]}
        />
      ))}
    </div>
  )
}

function OneChart({ chart, title }: { chart: Chart; title?: string }) {
  const data = chart.periods.map((period, index) => {
    const row: Record<string, string | number | null> = { period: period.label }
    for (const series of chart.bars) row[series.label] = series.points[index]?.value ?? null
    if (chart.line) row[chart.line.label] = chart.line.points[index]?.value ?? null
    return row
  })

  return (
    <figure className="min-w-0">
      <figcaption className="mb-1 text-sm font-semibold text-brand-900">
        {title || chart.title || chart.table}
      </figcaption>
      {/* the legend is measured by the chart library and can lag behind a
          shrinking container: clipping keeps a stale measurement from pushing
          the page sideways */}
      <div className="h-[300px] overflow-hidden">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: '#6b7d94' }}
              tickLine={false}
              axisLine={{ stroke: '#d5dde8' }}
            />
            {/* the axis still sets the scale the bars are drawn against; it
                simply is not printed — the values are read in the table below
                and in the tooltip */}
            <YAxis hide />
            <Tooltip
              formatter={(value: number | string) =>
                typeof value === 'number' ? value.toLocaleString() : value
              }
              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #d5dde8' }}
            />
            <Legend wrapperStyle={{ fontSize: 11, maxWidth: '100%' }} />
            {chart.bars.map((series, index) => (
              <Bar
                key={series.key}
                dataKey={series.label}
                stackId={chart.stacked ? 'parts' : undefined}
                fill={BAR_COLORS[index % BAR_COLORS.length]}
                radius={chart.stacked && index < chart.bars.length - 1 ? undefined : [2, 2, 0, 0]}
                maxBarSize={34}
              />
            ))}
            {chart.line && (
              <Line
                type="monotone"
                dataKey={chart.line.label}
                stroke={LINE_COLOR}
                strokeWidth={2}
                dot={{ r: 2.5 }}
                connectNulls
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}
