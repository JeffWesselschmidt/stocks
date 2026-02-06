import { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { AnnualRow } from '../types';

interface Props {
  data: AnnualRow[];
}

type MetricOption = {
  key: keyof AnnualRow;
  label: string;
  color: string;
  format: 'pct' | 'dollars' | 'millions';
};

const METRICS: MetricOption[] = [
  { key: 'roic', label: 'ROIC', color: '#4682b4', format: 'pct' },
  { key: 'roe', label: 'ROE', color: '#2e8b57', format: 'pct' },
  { key: 'roa', label: 'ROA', color: '#8b6914', format: 'pct' },
  { key: 'gross_margin', label: 'Gross Margin', color: '#7b68ee', format: 'pct' },
  { key: 'operating_margin', label: 'Operating Margin', color: '#cd5c5c', format: 'pct' },
  { key: 'eps', label: 'EPS', color: '#4682b4', format: 'dollars' },
  { key: 'revenue', label: 'Revenue', color: '#2e8b57', format: 'millions' },
];

function formatValue(val: number | null, format: string): string {
  if (val == null) return '—';
  if (format === 'pct') return `${val.toFixed(1)}%`;
  if (format === 'dollars') return `$${val.toFixed(2)}`;
  if (format === 'millions') return `$${(val / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 })}M`;
  return val.toString();
}

function tickFormatter(val: number, format: string): string {
  if (format === 'pct') return `${val}%`;
  if (format === 'dollars') return `$${val}`;
  if (format === 'millions') {
    if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(0)}B`;
    return `$${(val / 1e6).toFixed(0)}M`;
  }
  return val.toString();
}

export default function MetricsChart({ data }: Props) {
  const [selected, setSelected] = useState<MetricOption>(METRICS[0]);

  if (!data || data.length === 0) {
    return <div className="text-gray-400 text-sm">No chart data available.</div>;
  }

  const chartData = data
    .filter((d) => d.fiscal_year !== 0) // exclude TTM row from chart
    .map((d) => ({
      year: d.fiscal_year.toString(),
      value: d[selected.key] as number | null,
    }));

  return (
    <div className="border border-gray-300 rounded-lg p-5 bg-white">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-900">{selected.label}</h2>
        <div className="flex flex-wrap gap-1">
          {METRICS.map((m) => (
            <button
              key={m.key}
              onClick={() => setSelected(m)}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                selected.key === m.key
                  ? 'bg-gray-800 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
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
            tickFormatter={(v: number) => tickFormatter(v, selected.format)}
            tickLine={false}
            axisLine={{ stroke: '#d1d5db' }}
          />
          <Tooltip
            formatter={(value: number) => [formatValue(value, selected.format), selected.label]}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={selected.color}
            fill={selected.color}
            fillOpacity={0.15}
            strokeWidth={2}
            dot={{ r: 3, fill: selected.color }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
