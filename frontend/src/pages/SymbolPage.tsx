import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getSymbolPage, updateSymbolMeta } from '../api/client';
import type { SymbolPageData } from '../types';
import HeaderStrip from '../components/HeaderStrip';
import KeyStatistics from '../components/KeyStatistics';
import MetricsChart from '../components/MetricsChart';
import AnnualTable from '../components/AnnualTable';

function CompanyDescription({ description }: { description: string }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border border-gray-300 rounded-lg bg-white">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-gray-50 transition-colors rounded-lg"
      >
        <span className="text-sm font-semibold text-gray-700">About</span>
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-4 pb-4 text-sm text-gray-600 leading-relaxed border-t border-gray-100 pt-3">
          {description}
        </div>
      )}
    </div>
  );
}

export default function SymbolPage() {
  const { symbol: rawSymbol } = useParams<{ symbol: string }>();
  const symbol = rawSymbol?.toUpperCase() || '';

  const [data, setData] = useState<SymbolPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rating, setRating] = useState<'good' | 'bad' | null>(null);
  const [note, setNote] = useState('');
  const [noteDirty, setNoteDirty] = useState(false);
  const [savingRating, setSavingRating] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [metaError, setMetaError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) return;

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

  useEffect(() => {
    if (!data) return;
    setRating(data.company.rating ?? null);
    setNote(data.company.note ?? '');
    setNoteDirty(false);
  }, [data]);

  async function handleToggleRating() {
    if (!data || savingRating) return;
    const next = rating === 'bad' ? 'good' : rating === 'good' ? null : 'bad';
    const prev = rating;
    setRating(next);
    setSavingRating(true);
    setMetaError(null);
    try {
      const updated = await updateSymbolMeta(symbol, { rating: next });
      setData((current) =>
        current ? { ...current, company: { ...current.company, rating: updated.rating, note: updated.note } } : current,
      );
    } catch (e) {
      setRating(prev);
      setMetaError(e instanceof Error ? e.message : 'Failed to update rating');
    } finally {
      setSavingRating(false);
    }
  }

  async function handleSaveNote() {
    if (!data || savingNote || !noteDirty) return;
    const cleaned = note.trim();
    setSavingNote(true);
    setMetaError(null);
    try {
      const updated = await updateSymbolMeta(symbol, { note: cleaned ? cleaned : null });
      setData((current) =>
        current ? { ...current, company: { ...current.company, rating: updated.rating, note: updated.note } } : current,
      );
      setNote(updated.note ?? '');
      setNoteDirty(false);
    } catch (e) {
      setMetaError(e instanceof Error ? e.message : 'Failed to update note');
    } finally {
      setSavingNote(false);
    }
  }

  if (!symbol) return null;

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

  const ratingLabel = rating === 'good' ? 'Good' : rating === 'bad' ? 'Bad' : 'Unrated';

  return (
    <div className="space-y-5">
      {/* Header strip */}
      <HeaderStrip company={data.company} market={data.market_data} />

      {/* Company name */}
      <div>
        <div className="flex flex-wrap items-start justify-between gap-3">
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
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase tracking-wide text-gray-400">Rating</span>
            <button
              type="button"
              onClick={handleToggleRating}
              disabled={savingRating}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 border border-gray-200 rounded-full text-sm text-gray-600 hover:text-gray-900 hover:border-gray-300 disabled:opacity-50"
              title="Click to cycle Good → Bad → None"
            >
              {rating === 'good' && (
                <svg className="w-4 h-4 text-amber-500" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 17.3l-6.16 3.24 1.18-6.88L2 8.76l6.92-1 3.08-6.27 3.08 6.27 6.92 1-5.02 4.9 1.18 6.88z" />
                </svg>
              )}
              {rating === 'bad' && (
                <svg className="w-4 h-4 text-red-500" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2a10 10 0 100 20 10 10 0 000-20zm5 9H7v2h10v-2z" />
                </svg>
              )}
              {rating === null && (
                <svg className="w-4 h-4 text-gray-300" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2a10 10 0 100 20 10 10 0 000-20zm1 5h-2v6h6v-2h-4V7z" />
                </svg>
              )}
              <span>{ratingLabel}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Notes */}
      <div className="border border-gray-200 rounded-lg bg-white p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-700">Note</span>
          <button
            type="button"
            onClick={handleSaveNote}
            disabled={!noteDirty || savingNote}
            className="px-3 py-1 text-xs font-medium bg-red-700 text-white rounded-full hover:bg-red-800 disabled:opacity-40"
          >
            {savingNote ? 'Saving…' : 'Save'}
          </button>
        </div>
        <textarea
          value={note}
          onChange={(e) => { setNote(e.target.value); setNoteDirty(true); }}
          placeholder="Add a note about this stock…"
          rows={3}
          className="w-full text-sm px-3 py-2 border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-red-500"
        />
        {metaError && (
          <p className="text-xs text-red-600">{metaError}</p>
        )}
      </div>

      {/* Business description (collapsible) */}
      {data.company.description && (
        <CompanyDescription description={data.company.description} />
      )}

      {/* Key Statistics + Chart side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div className="lg:col-span-3">
          <KeyStatistics stats={data.key_statistics} />
        </div>
        <div className="lg:col-span-2">
          <MetricsChart data={data.annual_table} />
        </div>
      </div>

      {/* Financial Table (Annual / Quarterly toggle) */}
      <AnnualTable data={data.annual_table} quarterlyData={data.quarterly_table} />
    </div>
  );
}
