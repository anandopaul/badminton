import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TrendMetric } from '../data/types'
import type { buildTrendPoints } from '../data/selectors'

type TrendPoint = ReturnType<typeof buildTrendPoints>[number]

interface TrendChartProps {
  metric: TrendMetric
  points: TrendPoint[]
}

function TrendChart({ metric, points }: TrendChartProps) {
  return (
    <div
      className="trend-chart"
      role="img"
      aria-label={`${metric === 'winPct' ? 'Win rate' : 'Rating'} by season`}
    >
      <ResponsiveContainer width="100%" height={260}>
        <LineChart
          data={points}
          margin={{ top: 16, right: 12, bottom: 4, left: -12 }}
        >
          <CartesianGrid
            stroke="#e8e9e3"
            strokeDasharray="3 5"
            vertical={false}
          />
          <XAxis
            axisLine={false}
            dataKey="label"
            tick={{ fill: '#858a82', fontSize: 11 }}
            tickLine={false}
            tickMargin={12}
            interval="preserveStartEnd"
          />
          <YAxis
            axisLine={false}
            domain={metric === 'winPct' ? [0, 100] : ['auto', 'auto']}
            tick={{ fill: '#858a82', fontSize: 11 }}
            tickFormatter={(value: number) =>
              metric === 'winPct' ? `${value}%` : String(value)
            }
            tickLine={false}
            tickMargin={8}
            width={48}
          />
          <Tooltip
            contentStyle={{
              background: '#18251f',
              border: '1px solid #32423a',
              borderRadius: 12,
              color: '#f5f5f0',
              fontSize: 12,
            }}
            formatter={(value) => [
              value === null || value === undefined
                ? 'Not recorded'
                : metric === 'winPct'
                  ? `${Number(value).toFixed(1)}%`
                  : Number(value).toFixed(2),
              metric === 'winPct' ? 'Win rate' : 'Rating',
            ]}
            labelFormatter={(_, payload) => {
              const point = payload?.[0]?.payload as TrendPoint | undefined
              return point
                ? `${point.label} · ${point.groupName} · ${point.className} · ${point.teamName} · poule ${point.pouleId}`
                : ''
            }}
          />
          <Line
            activeDot={{ r: 5, fill: '#e49d48', stroke: '#fffaf0', strokeWidth: 3 }}
            connectNulls={false}
            dataKey={metric === 'winPct' ? 'winPct' : 'rating'}
            dot={{ r: 4, fill: '#f8f6ee', stroke: '#557464', strokeWidth: 2 }}
            name={metric === 'winPct' ? 'Win rate' : 'Rating'}
            stroke="#557464"
            strokeWidth={3}
            type="monotone"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default TrendChart
