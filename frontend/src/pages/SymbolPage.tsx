import { useState, useEffect } from 'react';
import { getSymbolPage } from '../api/client';
import type { SymbolPageData } from '../types';
import HeaderStrip from '../components/HeaderStrip';
import KeyStatistics from '../components/KeyStatistics';
import MetricsChart from '../components/MetricsChart';
import AnnualTable from '../components/AnnualTable';

interface Props {
  symbol: string;
}

export default function SymbolPage({ symbol }: Props) {
  const [data, setData] = useState<SymbolPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getSymbolPage(symbol)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <div className="w-8 h-8 border-3 border-gray-300 border-t-blue-500 rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-500 text-sm">
            Loading {symbol}...
            <br />
            <span className="text-xs text-gray-400">(First load may take a moment while data is fetched)</span>
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
        Error loading {symbol}: {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-5">
      {/* Header strip */}
      <HeaderStrip company={data.company} market={data.market_data} />

      {/* Company name */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">
          {data.company.name || symbol}
          <span className="text-gray-400 font-normal ml-2 text-base">({symbol})</span>
        </h1>
        {data.company.sector && (
          <p className="text-sm text-gray-500 mt-0.5">
            {data.company.sector}
            {data.company.industry ? ` — ${data.company.industry}` : ''}
          </p>
        )}
      </div>

      {/* Key Statistics + Chart side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div className="lg:col-span-3">
          <KeyStatistics stats={data.key_statistics} />
        </div>
        <div className="lg:col-span-2">
          <MetricsChart data={data.annual_table} />
        </div>
      </div>

      {/* Annual Table */}
      <AnnualTable data={data.annual_table} />
    </div>
  );
}
