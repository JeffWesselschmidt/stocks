import type { KeyStatistics as KeyStatsType } from '../types';

interface Props {
  stats: KeyStatsType;
}

function fmtNum(val: number | null | undefined, suffix = ''): string {
  if (val == null) return '—';
  return `${val.toFixed(1)}${suffix}`;
}

function fmtPct(val: number | null | undefined): string {
  if (val == null) return '—';
  return `${val.toFixed(1)}%`;
}

function fmtRatio(val: number | null | undefined): string {
  if (val == null) return '—';
  return val.toFixed(1);
}

export default function KeyStatistics({ stats }: Props) {
  const { valuation_ratios: v, median_returns: r, median_margins: m, cagr_10yr: c, capital_structure: cs } = stats;

  return (
    <div className="border border-gray-300 rounded-lg p-5 bg-white">
      <h2 className="text-2xl font-serif font-bold mb-4 text-gray-900">Key Statistics</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Column 1: Valuation Ratios */}
        <div>
          <h3 className="text-sm font-bold text-red-700 border-b border-red-200 pb-1 mb-2">
            Valuation Ratios
          </h3>
          <table className="w-full text-sm">
            <tbody>
              <StatRow label="P/E" value={fmtRatio(v.pe)} />
              <StatRow label="P/B" value={fmtRatio(v.pb)} />
              <StatRow label="P/S" value={fmtRatio(v.ps)} />
              <StatRow label="EV/S" value={fmtRatio(v.ev_s)} />
              <StatRow label="EV/EBITDA" value={fmtRatio(v.ev_ebitda)} />
              <StatRow label="EV/EBIT" value={fmtRatio(v.ev_ebit)} />
              <StatRow label="EV/Pretax" value={fmtRatio(v.ev_pretax)} />
              <StatRow label="EV/FCF" value={fmtRatio(v.ev_fcf)} />
            </tbody>
          </table>
        </div>

        {/* Column 2: Returns + CAGR */}
        <div>
          <h3 className="text-sm font-bold text-red-700 border-b border-red-200 pb-1 mb-2">
            10-Yr Median Returns
          </h3>
          <table className="w-full text-sm">
            <tbody>
              <StatRow label="ROA" value={fmtPct(r.roa)} />
              <StatRow label="ROE" value={fmtPct(r.roe)} />
              <StatRow label="ROIC" value={fmtPct(r.roic)} />
            </tbody>
          </table>

          <h3 className="text-sm font-bold text-red-700 border-b border-red-200 pb-1 mb-2 mt-4">
            10-Year CAGR
          </h3>
          <table className="w-full text-sm">
            <tbody>
              <StatRow label="Revenue" value={fmtPct(c.revenue_cagr)} />
              <StatRow label="Assets" value={fmtPct(c.assets_cagr)} />
              <StatRow label="EPS" value={fmtPct(c.eps_cagr)} />
            </tbody>
          </table>
        </div>

        {/* Column 3: Margins + Capital Structure */}
        <div>
          <h3 className="text-sm font-bold text-red-700 border-b border-red-200 pb-1 mb-2">
            10-Yr Median Margins
          </h3>
          <table className="w-full text-sm">
            <tbody>
              <StatRow label="Gross Profit" value={fmtPct(m.gross_margin)} />
              <StatRow label="EBIT" value={fmtPct(m.operating_margin)} />
              <StatRow label="Pre-Tax Income" value={fmtPct(m.pretax_margin)} />
              <StatRow label="FCF" value={fmtPct(m.fcf_margin)} />
            </tbody>
          </table>

          <h3 className="text-sm font-bold text-red-700 border-b border-red-200 pb-1 mb-2 mt-4">
            Capital Structure (Median)
          </h3>
          <table className="w-full text-sm">
            <tbody>
              <StatRow label="Assets / Equity" value={fmtNum(cs.assets_to_equity)} />
              <StatRow label="Debt / Equity" value={fmtNum(cs.debt_to_equity)} />
              <StatRow label="Debt / Assets" value={fmtNum(cs.debt_to_assets)} />
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <tr className="border-b border-gray-100 last:border-0">
      <td className="py-1 text-gray-600">{label}</td>
      <td className="py-1 text-right font-medium text-gray-900">{value}</td>
    </tr>
  );
}
