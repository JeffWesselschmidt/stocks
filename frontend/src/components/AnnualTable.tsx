import { useRef, useEffect, useState } from 'react';
import type { AnnualRow, QuarterlyRow } from '../types';

interface Props {
  data: AnnualRow[];
  quarterlyData: QuarterlyRow[];
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
  key: keyof AnnualRow & keyof QuarterlyRow;
  format: (v: number | null | undefined) => string;
  isGrowth?: boolean;
  /** If true, hide this row in quarterly view. */
  annualOnly?: boolean;
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
  { label: 'Return on Assets', key: 'roa', format: fmtPct, annualOnly: true },
  { label: 'Return on Equity', key: 'roe', format: fmtPct, annualOnly: true },
  { label: 'Return on Invested Capital', key: 'roic', format: fmtPct, annualOnly: true },
];

type ViewMode = 'annual' | 'quarterly';

export default function AnnualTable({ data, quarterlyData }: Props) {
  const [view, setView] = useState<ViewMode>('annual');
  const scrollRef = useRef<HTMLDivElement>(null);

  const isAnnual = view === 'annual';
  const visibleRows = isAnnual ? rows : rows.filter((r) => !r.annualOnly);

  // Auto-scroll to the right so most-recent column is visible
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollLeft = el.scrollWidth;
    }
  }, [data, quarterlyData, view]);

  const hasAnnual = data && data.length > 0;
  const hasQuarterly = quarterlyData && quarterlyData.length > 0;

  if (!hasAnnual && !hasQuarterly) {
    return <div className="text-gray-400 text-sm">No financial data available.</div>;
  }

  return (
    <div>
      {/* Toggle */}
      <div className="flex items-center gap-1 mb-2">
        <button
          onClick={() => setView('annual')}
          className={`px-3 py-1 text-sm font-medium rounded transition-colors ${
            isAnnual
              ? 'bg-gray-800 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Annual
        </button>
        <button
          onClick={() => setView('quarterly')}
          disabled={!hasQuarterly}
          className={`px-3 py-1 text-sm font-medium rounded transition-colors ${
            !isAnnual
              ? 'bg-gray-800 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          } disabled:opacity-40 disabled:cursor-not-allowed`}
        >
          Quarterly
        </button>
      </div>

      {/* Table */}
      <div
        ref={scrollRef}
        className="border border-gray-300 rounded-lg bg-white overflow-x-auto"
      >
        {isAnnual ? (
          <AnnualView data={data} visibleRows={visibleRows} />
        ) : (
          <QuarterlyView data={quarterlyData} visibleRows={visibleRows} />
        )}
      </div>
    </div>
  );
}

/* ---- Annual sub-view ---- */

function AnnualView({ data, visibleRows }: { data: AnnualRow[]; visibleRows: RowDef[] }) {
  return (
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
        {visibleRows.map((rowDef) => {
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
                      isTTM
                        ? 'bg-blue-50 font-semibold text-gray-900'
                        : rowDef.isGrowth
                          ? 'text-gray-500'
                          : 'text-gray-900'
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
  );
}

/* ---- Quarterly sub-view ---- */

function QuarterlyView({
  data,
  visibleRows,
}: {
  data: QuarterlyRow[];
  visibleRows: RowDef[];
}) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="bg-gray-50">
          <th className="sticky left-0 z-20 bg-gray-50 text-left px-4 py-2 font-medium text-gray-600 border-b border-gray-200 min-w-[180px] shadow-[2px_0_4px_-2px_rgba(0,0,0,0.1)]">
            Millions
          </th>
          {data.map((d) => (
            <th
              key={`${d.fiscal_year}-${d.fiscal_quarter}`}
              className="px-3 py-2 text-right font-bold border-b border-gray-200 min-w-[72px] text-gray-800"
            >
              {d.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {visibleRows.map((rowDef) => {
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
                return (
                  <td
                    key={`${d.fiscal_year}-${d.fiscal_quarter}`}
                    className={`px-3 py-1.5 text-right border-b border-gray-100 tabular-nums ${
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
  );
}
