import { useRef, useEffect } from 'react';
import type { AnnualRow } from '../types';

interface Props {
  data: AnnualRow[];
}

function fmtMil(val: number | null | undefined): string {
  if (val == null) return '—';
  return (val / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function fmtPct(val: number | null | undefined): string {
  if (val == null) return '—';
  return `${val.toFixed(1)}%`;
}

function fmtEps(val: number | null | undefined): string {
  if (val == null) return '—';
  return `$${val.toFixed(2)}`;
}

type RowDef = {
  label: string;
  key: keyof AnnualRow;
  format: (v: number | null | undefined) => string;
  isGrowth?: boolean;
};

const rows: RowDef[] = [
  { label: 'Revenue', key: 'revenue', format: fmtMil },
  { label: 'Revenue Growth', key: 'revenue_growth', format: fmtPct, isGrowth: true },
  { label: 'Gross Profit', key: 'gross_profit', format: fmtMil },
  { label: 'Gross Margin %', key: 'gross_margin', format: fmtPct, isGrowth: true },
  { label: 'Operating Profit', key: 'operating_profit', format: fmtMil },
  { label: 'Operating Margin %', key: 'operating_margin', format: fmtPct, isGrowth: true },
  { label: 'Earnings Per Share', key: 'eps', format: fmtEps },
  { label: 'EPS Growth', key: 'eps_growth', format: fmtPct, isGrowth: true },
  { label: 'Return on Assets', key: 'roa', format: fmtPct },
  { label: 'Return on Equity', key: 'roe', format: fmtPct },
  { label: 'Return on Invested Capital', key: 'roic', format: fmtPct },
];

export default function AnnualTable({ data }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the right so TTM column is visible on load
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollLeft = el.scrollWidth;
    }
  }, [data]);

  if (!data || data.length === 0) {
    return <div className="text-gray-400 text-sm">No annual data available.</div>;
  }

  return (
    <div
      ref={scrollRef}
      className="border border-gray-300 rounded-lg bg-white overflow-x-auto"
    >
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50">
            <th className="sticky left-0 z-20 bg-gray-50 text-left px-4 py-2 font-medium text-gray-600 border-b border-gray-200 min-w-[180px] shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]">
              Millions
            </th>
            {data.map((d) => (
              <th
                key={d.fiscal_year}
                className={`px-3 py-2 text-right font-bold border-b border-gray-200 min-w-[80px] ${
                  d.fiscal_year === 0 ? 'text-blue-700 bg-blue-50' : 'text-gray-800'
                }`}
              >
                {d.fiscal_year === 0 ? 'TTM' : d.fiscal_year}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((rowDef) => {
            const rowBg = rowDef.isGrowth ? 'bg-gray-50' : 'bg-white';
            return (
              <tr
                key={rowDef.key}
                className={`${rowBg} ${rowDef.isGrowth ? 'italic text-gray-600' : ''}`}
              >
                <td
                  className={`sticky left-0 z-10 ${rowBg} px-4 py-1.5 font-medium border-b border-gray-100 shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]`}
                >
                  {rowDef.isGrowth && <span className="ml-3">{rowDef.label}</span>}
                  {!rowDef.isGrowth && rowDef.label}
                </td>
                {data.map((d) => {
                  const val = d[rowDef.key] as number | null;
                  const isTTM = d.fiscal_year === 0;
                  return (
                    <td
                      key={d.fiscal_year}
                      className={`px-3 py-1.5 text-right border-b border-gray-100 tabular-nums ${
                        isTTM ? 'bg-blue-50 font-semibold text-gray-900' :
                        rowDef.isGrowth ? 'text-gray-500' : 'text-gray-900'
                      }`}
                    >
                      {rowDef.format(val)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
