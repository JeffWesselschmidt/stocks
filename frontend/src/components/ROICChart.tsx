import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { ROICPoint } from '../types';

interface Props {
  data: ROICPoint[];
}

export default function ROICChart({ data }: Props) {
  if (!data || data.length === 0) {
    return <div className="text-gray-400 text-sm">No ROIC data available.</div>;
  }

  const chartData = data.map((d) => ({
    year: d.year.toString(),
    roic: d.roic,
  }));

  return (
    <div className="border border-gray-300 rounded-lg p-5 bg-white">
      <h2 className="text-lg font-bold text-gray-900 mb-4">Return On Invested Capital</h2>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="year"
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickLine={false}
            axisLine={{ stroke: '#d1d5db' }}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickFormatter={(v: number) => `${v}%`}
            tickLine={false}
            axisLine={{ stroke: '#d1d5db' }}
          />
          <Tooltip
            formatter={(value: number) => [`${value?.toFixed(1)}%`, 'ROIC']}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Area
            type="monotone"
            dataKey="roic"
            stroke="#4682b4"
            fill="#4682b4"
            fillOpacity={0.15}
            strokeWidth={2}
            dot={{ r: 3, fill: '#4682b4' }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
