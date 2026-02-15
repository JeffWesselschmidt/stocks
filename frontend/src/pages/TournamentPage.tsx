import { useEffect, useMemo, useState } from 'react';
import MetricsChart from '../components/MetricsChart';
import {
  startTournament,
  getCurrentTournament,
  pickTournamentWinner,
  getTournamentResults,
} from '../api/client';
import type {
  TournamentCurrentResponse,
  TournamentResultsResponse,
  TournamentMatchSide,
} from '../types';

type StatDef = {
  key: string;
  label: string;
  fmt?: (v: number | null) => string;
};

const fmtPct = (v: number | null) => (v != null ? `${v.toFixed(1)}%` : '—');
const fmtNum = (v: number | null) => (v != null ? v.toFixed(2) : '—');

const STAT_FIELDS: StatDef[] = [
  { key: 'median_roic', label: 'ROIC', fmt: fmtPct },
  { key: 'median_roe', label: 'ROE', fmt: fmtPct },
  { key: 'median_roa', label: 'ROA', fmt: fmtPct },
  { key: 'median_operating_margin', label: 'Op Margin', fmt: fmtPct },
  { key: 'median_fcf_margin', label: 'FCF Margin', fmt: fmtPct },
  { key: 'median_revenue_growth', label: 'Rev Gr', fmt: fmtPct },
  { key: 'median_eps_growth', label: 'EPS Gr', fmt: fmtPct },
  { key: 'pct_eps_yoy_positive', label: 'EPS YoY +%', fmt: fmtPct },
  { key: 'eps_cagr', label: 'EPS CAGR', fmt: fmtPct },
  { key: 'revenue_cagr', label: 'Rev CAGR', fmt: fmtPct },
  { key: 'median_debt_to_equity', label: 'D/E', fmt: fmtNum },
];

function StatTable({ side }: { side: TournamentMatchSide }) {
  return (
    <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
      <table className="w-full text-sm">
        <tbody>
          {STAT_FIELDS.map((stat) => {
            const raw = side.stats[stat.key];
            const val = raw == null ? null : Number(raw);
            return (
              <tr key={stat.key} className="border-b border-gray-100">
                <td className="px-3 py-2 text-gray-500">{stat.label}</td>
                <td className="px-3 py-2 text-right text-gray-800 font-medium">
                  {stat.fmt ? stat.fmt(val) : (val ?? '—')}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function TournamentPage() {
  const [current, setCurrent] = useState<TournamentCurrentResponse | null>(null);
  const [results, setResults] = useState<TournamentResultsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noActive, setNoActive] = useState(false);

  const progressText = useMemo(() => {
    if (!current) return '';
    return `${current.decided_matches}/${current.total_matches} matches decided`;
  }, [current]);

  async function loadCurrent() {
    setLoading(true);
    setError(null);
    setNoActive(false);
    try {
      const data = await getCurrentTournament();
      setCurrent(data);
      setResults(null);
      if (!data.next_match) {
        const res = await getTournamentResults();
        setResults(res);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load tournament';
      if (msg.startsWith('404:')) {
        setNoActive(true);
        setCurrent(null);
        setResults(null);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleStart() {
    setLoading(true);
    setError(null);
    try {
      await startTournament();
      await loadCurrent();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start tournament');
      setLoading(false);
    }
  }

  async function handlePick(side: 'A' | 'B') {
    if (!current?.next_match) return;
    setLoading(true);
    setError(null);
    try {
      const next = await pickTournamentWinner(current.next_match.match_id, side);
      setCurrent(next);
      if (!next.next_match) {
        const res = await getTournamentResults();
        setResults(res);
      } else {
        setResults(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save pick');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCurrent();
  }, []);

  if (noActive) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-6 text-center">
        <h1 className="text-lg font-bold text-gray-900">Tournament</h1>
        <p className="text-sm text-gray-500 mt-2">
          Start a tournament using Good-rated stocks.
        </p>
        <button
          onClick={handleStart}
          className="mt-4 px-4 py-2 bg-red-700 text-white text-sm font-medium rounded hover:bg-red-800"
          disabled={loading}
        >
          {loading ? 'Starting…' : 'Start Tournament'}
        </button>
      </div>
    );
  }

  if (loading && !current) {
    return <div className="text-gray-500 text-sm">Loading tournament…</div>;
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
        {error}
      </div>
    );
  }

  if (results && results.results.length > 0) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900">Tournament Results</h1>
          {current && (
            <span className="text-sm text-gray-500">{progressText}</span>
          )}
        </div>
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-3 py-2 text-left font-medium text-gray-600">Rank</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Symbol</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Name</th>
                <th className="px-3 py-2 text-right font-medium text-gray-600">Seed</th>
              </tr>
            </thead>
            <tbody>
              {results.results.map((r) => (
                <tr key={r.symbol} className="border-b border-gray-100">
                  <td className="px-3 py-2">{r.rank}</td>
                  <td className="px-3 py-2 font-semibold text-gray-800">{r.symbol}</td>
                  <td className="px-3 py-2 text-gray-600">{r.name ?? '—'}</td>
                  <td className="px-3 py-2 text-right text-gray-500">#{r.seed_rank}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (!current?.next_match) {
    return (
      <div className="text-gray-500 text-sm">
        Waiting for the next matchup…
      </div>
    );
  }

  const { side_a, side_b, round } = current.next_match;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Tournament</h1>
        <span className="text-sm text-gray-500">
          Round {round} · {progressText}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-3">
          <div className="text-xs uppercase tracking-wide text-gray-400">Stock A</div>
          <StatTable side={side_a} />
          <MetricsChart data={side_a.annual_table} />
          <button
            onClick={() => handlePick('A')}
            className="w-full px-4 py-2 bg-red-700 text-white text-sm font-medium rounded hover:bg-red-800 disabled:opacity-50"
            disabled={loading}
          >
            Pick Stock A
          </button>
        </div>
        <div className="space-y-3">
          <div className="text-xs uppercase tracking-wide text-gray-400">Stock B</div>
          <StatTable side={side_b} />
          <MetricsChart data={side_b.annual_table} />
          <button
            onClick={() => handlePick('B')}
            className="w-full px-4 py-2 bg-red-700 text-white text-sm font-medium rounded hover:bg-red-800 disabled:opacity-50"
            disabled={loading}
          >
            Pick Stock B
          </button>
        </div>
      </div>
    </div>
  );
}
