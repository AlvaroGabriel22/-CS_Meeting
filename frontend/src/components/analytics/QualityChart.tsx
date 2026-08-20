import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { Period, Series } from '@/types/api'

const PALETTE = ['#1e3a5f', '#3a6499', '#6a8fbe', '#9dbadd', '#c7d9ef']

export type ChartKind = 'line' | 'bar'

/**
 * Plots series that arrive ready from the model.
 *
 * The component knows nothing about months, quarters, weeks, tables or
 * metrics: it receives labelled points and draws them in the order given.
 */
export function QualityChart({
  periods,
  series,
  kind = 'line',
  highlight,
  height = 320,
}: {
  periods: Period[]
  series: Series[]
  kind?: ChartKind
  /** period label to mark as the one under discussion */
  highlight?: string
  height?: number
}) {
  const data = periods.map((period) => {
    const row: Record<string, string | number | null> = { period: period.label }
    for (const item of series) {
      const point = item.points.find((entry) => entry.period.label === period.label)
      row[item.label] = point?.value ?? null
    }
    return row
  })

  const Chart = kind === 'bar' ? BarChart : LineChart

  return (
    // the legend is measured by the chart library and can lag behind a
    // shrinking container: clipping here keeps a stale measurement from
    // pushing the page sideways on a narrow screen
    <div style={{ height }} className="overflow-hidden">
      <ResponsiveContainer width="100%" height="100%">
        <Chart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="#e3eaf3" vertical={false} />
          <XAxis
            dataKey="period"
            tick={({ x, y, payload }) => (
              <text
                x={x}
                y={y + 14}
                textAnchor="middle"
                fontSize={12}
                fontWeight={payload.value === highlight ? 700 : 400}
                fill={payload.value === highlight ? '#1e3a5f' : '#6b7d94'}
              >
                {payload.value}
              </text>
            )}
            axisLine={{ stroke: '#e3eaf3' }}
            tickLine={false}
          />
          <YAxis
            width={72}
            tick={{ fontSize: 12, fill: '#6b7d94' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(value: number) => value.toLocaleString()}
          />
          <Tooltip
            formatter={(value) =>
              typeof value === 'number' ? value.toLocaleString() : '—'
            }
            contentStyle={{
              borderRadius: 12,
              border: '1px solid #e3eaf3',
              fontSize: 12,
            }}
          />
          <Legend
            wrapperStyle={{
              fontSize: 12,
              width: '100%',
              maxWidth: '100%',
              lineHeight: '1.6',
              paddingTop: 4,
            }}
          />
          {series.map((item, index) =>
            kind === 'bar' ? (
              <Bar
                key={item.key}
                dataKey={item.label}
                fill={PALETTE[index % PALETTE.length]}
                radius={[4, 4, 0, 0]}
              />
            ) : (
              <Line
                key={item.key}
                type="monotone"
                dataKey={item.label}
                stroke={PALETTE[index % PALETTE.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls={false}
              />
            ),
          )}
        </Chart>
      </ResponsiveContainer>
    </div>
  )
}
