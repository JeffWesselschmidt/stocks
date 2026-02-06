import type { CompanyInfo, MarketData } from '../types';

interface Props {
  company: CompanyInfo;
  market: MarketData;
}

function fmt(val: number | null | undefined, opts?: { prefix?: string; suffix?: string; decimals?: number }): string {
  if (val == null) return '—';
  const d = opts?.decimals ?? 2;
  const prefix = opts?.prefix ?? '';
  const suffix = opts?.suffix ?? '';

  if (Math.abs(val) >= 1e12) return `${prefix}${(val / 1e12).toFixed(1)}T${suffix}`;
  if (Math.abs(val) >= 1e9) return `${prefix}${(val / 1e9).toFixed(1)}B${suffix}`;
  if (Math.abs(val) >= 1e6) return `${prefix}${(val / 1e6).toFixed(0)}M${suffix}`;
  return `${prefix}${val.toFixed(d)}${suffix}`;
}

export default function HeaderStrip({ company, market }: Props) {
  return (
    <div className="bg-[#8b2500] text-white px-6 py-3 rounded-lg">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
        <Item label="Last Close" value={fmt(market.last_close, { prefix: '$' })} bold />
        <Item label="Market Cap" value={fmt(market.market_cap, { prefix: '$' })} />
        <Item label="EV" value={fmt(market.ev, { prefix: '$' })} />
        <Item label="Industry" value={company.industry || '—'} />
        <Item label="Display Currency" value={company.currency || 'USD'} bold />
      </div>
    </div>
  );
}

function Item({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <span>
      <span className="text-red-200">{label}:</span>{' '}
      <span className={bold ? 'font-bold' : 'font-medium'}>{value}</span>
    </span>
  );
}
