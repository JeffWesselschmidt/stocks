import { useState, useCallback, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getScreenerResults, getSavedScreens, createSavedScreen, deleteSavedScreen } from '../api/client';
import type { ScreenerRow, ScreenerResponse, SavedScreen } from '../types';

// ---------------------------------------------------------------------------
// Filter configuration
// ---------------------------------------------------------------------------

interface FilterDef {
  key: string;
  label: string;
  /** If true, only show a "min" input (e.g. profit %). If 'max', only max. */
  mode?: 'min' | 'max';
}

interface FilterGroup {
  /** Stable key matching the backend group key (used for or_groups param). */
  groupKey: string;
  title: string;
  filters: FilterDef[];
}

const FILTER_GROUPS: FilterGroup[] = [
  {
    groupKey: 'returns',
    title: 'Returns (10yr median %)',
    filters: [
      { key: 'median_roic', label: 'ROIC' },
      { key: 'median_roe', label: 'ROE' },
      { key: 'median_roa', label: 'ROA' },
    ],
  },
  {
    groupKey: 'profitability',
    title: 'Profitability',
    filters: [
      { key: 'profit_pct', label: 'Profit %', mode: 'min' },
    ],
  },
  {
    groupKey: 'margins',
    title: 'Margins (10yr median %)',
    filters: [
      { key: 'median_gross_margin', label: 'Gross' },
      { key: 'median_operating_margin', label: 'Operating' },
      { key: 'median_net_margin', label: 'Net' },
      { key: 'median_fcf_margin', label: 'FCF' },
    ],
  },
  {
    groupKey: 'growth_yoy',
    title: 'Growth — Median YoY %',
    filters: [
      { key: 'median_revenue_growth', label: 'Revenue' },
      { key: 'median_eps_growth', label: 'EPS' },
      { key: 'median_ocf_growth', label: 'Op CF' },
      { key: 'median_fcf_growth', label: 'FCF' },
      { key: 'median_ni_growth', label: 'Net Inc' },
    ],
  },
  {
    groupKey: 'growth_cagr',
    title: 'Growth — CAGR %',
    filters: [
      { key: 'revenue_cagr', label: 'Revenue' },
      { key: 'eps_cagr', label: 'EPS' },
      { key: 'ocf_cagr', label: 'Op CF' },
      { key: 'fcf_cagr', label: 'FCF' },
    ],
  },
  {
    groupKey: 'debt',
    title: 'Debt & Liquidity',
    filters: [
      { key: 'median_debt_to_equity', label: 'D/E', mode: 'max' },
      { key: 'latest_current_ratio', label: 'Current Ratio', mode: 'min' },
    ],
  },
];

/** All filter param keys that can appear in the URL (min_* / max_*). */
const ALL_FILTER_KEYS: string[] = FILTER_GROUPS.flatMap((g) =>
  g.filters.flatMap((f) => {
    const keys: string[] = [];
    if (!f.mode || f.mode === 'min') keys.push(`min_${f.key}`);
    if (!f.mode || f.mode === 'max') keys.push(`max_${f.key}`);
    return keys;
  }),
);

// ---------------------------------------------------------------------------
// Table column configuration
// ---------------------------------------------------------------------------

interface ColDef {
  key: keyof ScreenerRow;
  label: string;
  fmt?: (v: unknown) => string;
}

const fmtPct = (v: unknown) => (v != null ? `${Number(v).toFixed(1)}%` : '—');
const fmtNum = (v: unknown) => (v != null ? Number(v).toFixed(2) : '—');
const fmtBigNum = (v: unknown) => {
  if (v == null) return '—';
  const n = Number(v);
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(0);
};

const COLUMNS: ColDef[] = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'name', label: 'Name' },
  { key: 'sector', label: 'Sector' },
  { key: 'median_roic', label: 'ROIC', fmt: fmtPct },
  { key: 'median_roe', label: 'ROE', fmt: fmtPct },
  { key: 'median_roa', label: 'ROA', fmt: fmtPct },
  { key: 'profit_pct', label: 'Profit %', fmt: fmtPct },
  { key: 'median_operating_margin', label: 'Op Margin', fmt: fmtPct },
  { key: 'median_revenue_growth', label: 'Rev Gr', fmt: fmtPct },
  { key: 'median_eps_growth', label: 'EPS Gr', fmt: fmtPct },
  { key: 'median_fcf_growth', label: 'FCF Gr', fmt: fmtPct },
  { key: 'revenue_cagr', label: 'Rev CAGR', fmt: fmtPct },
  { key: 'eps_cagr', label: 'EPS CAGR', fmt: fmtPct },
  { key: 'median_debt_to_equity', label: 'D/E', fmt: fmtNum },
  { key: 'latest_long_term_debt', label: 'LT Debt', fmt: fmtBigNum },
  { key: 'latest_current_ratio', label: 'Curr Ratio', fmt: fmtNum },
  { key: 'years_of_data', label: 'Years' },
];

// ---------------------------------------------------------------------------
// Helpers: read / write URL search params
// ---------------------------------------------------------------------------

/** Extract screener state from URLSearchParams. */
function readStateFromParams(sp: URLSearchParams) {
  const filters: Record<string, string> = {};
  for (const key of ALL_FILTER_KEYS) {
    const v = sp.get(key);
    if (v) filters[key] = v;
  }
  const sector = sp.get('sector') ?? '';
  const sortBy = sp.get('sort_by') ?? 'symbol';
  const sortDir = (sp.get('sort_dir') === 'desc' ? 'desc' : 'asc') as 'asc' | 'desc';
  const offset = Math.max(0, Number(sp.get('offset')) || 0);
  const orGroups = new Set((sp.get('or_groups') ?? '').split(',').filter(Boolean));
  return { filters, sector, sortBy, sortDir, offset, orGroups };
}

/** Build a URLSearchParams from the current screener state. */
function buildParams(
  filters: Record<string, string>,
  sector: string,
  sortBy: string,
  sortDir: string,
  offset: number,
  orGroups: Set<string>,
): URLSearchParams {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v) p.set(k, v);
  }
  if (sector) p.set('sector', sector);
  if (sortBy !== 'symbol') p.set('sort_by', sortBy);
  if (sortDir !== 'asc') p.set('sort_dir', sortDir);
  if (offset > 0) p.set('offset', String(offset));
  if (orGroups.size > 0) p.set('or_groups', [...orGroups].join(','));
  return p;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50;

export default function ScreenerPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Hydrate initial state from URL on first render
  const initial = useRef(readStateFromParams(searchParams));

  // Filter inputs mirror the URL filters; they diverge while the user types
  // and re-sync when "Apply" is pressed.
  const [filterInputs, setFilterInputs] = useState<Record<string, string>>(initial.current.filters);
  const [activeFilters, setActiveFilters] = useState<Record<string, string>>(initial.current.filters);
  const [sectorFilter, setSectorFilter] = useState(initial.current.sector);
  const [activeSector, setActiveSector] = useState(initial.current.sector);

  // Data state
  const [data, setData] = useState<ScreenerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sort & pagination
  const [sortBy, setSortBy] = useState(initial.current.sortBy);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>(initial.current.sortDir);
  const [offset, setOffset] = useState(initial.current.offset);

  // OR groups — which filter groups use OR instead of AND
  const [orGroups, setOrGroups] = useState<Set<string>>(initial.current.orGroups);

  // Filter panel visibility
  const [filtersOpen, setFiltersOpen] = useState(true);

  // Saved screens
  const [savedScreens, setSavedScreens] = useState<SavedScreen[]>([]);
  const [saveName, setSaveName] = useState('');
  const [saveOpen, setSaveOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  // ---- Core fetch, also pushes state into the URL ----
  const fetchData = useCallback(
    async (
      filters: Record<string, string>,
      sector: string,
      sort: string,
      dir: string,
      off: number,
      orGrps: Set<string>,
      replace = false,
    ) => {
      // Sync URL
      setSearchParams(buildParams(filters, sector, sort, dir, off, orGrps), { replace });

      setLoading(true);
      setError(null);
      try {
        const params: Record<string, string> = { ...filters };
        if (sector) params.sector = sector;
        if (orGrps.size > 0) params.or_groups = [...orGrps].join(',');
        params.sort_by = sort;
        params.sort_dir = dir;
        params.limit = String(PAGE_SIZE);
        params.offset = String(off);
        const res = await getScreenerResults(params);
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    },
    [setSearchParams],
  );

  // Initial load — uses whatever was in the URL (or defaults)
  useEffect(() => {
    const s = initial.current;
    fetchData(s.filters, s.sector, s.sortBy, s.sortDir, s.offset, s.orGroups, true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load saved screens on mount
  useEffect(() => {
    getSavedScreens().then(setSavedScreens).catch(() => {});
  }, []);

  // ---- Handlers ----

  async function handleSaveScreen() {
    const name = saveName.trim();
    if (!name) return;
    setSaving(true);
    try {
      // Capture all active filters + sector + or_groups into a single object
      const filters: Record<string, string> = { ...activeFilters };
      if (activeSector) filters.sector = activeSector;
      if (orGroups.size > 0) filters.or_groups = [...orGroups].join(',');
      const created = await createSavedScreen(name, filters);
      setSavedScreens((prev) => [created, ...prev]);
      setSaveName('');
      setSaveOpen(false);
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteScreen(id: number) {
    try {
      await deleteSavedScreen(id);
      setSavedScreens((prev) => prev.filter((s) => s.id !== id));
    } catch {
      // ignore
    }
  }

  function handleLoadScreen(screen: SavedScreen) {
    const { sector: savedSector, or_groups: savedOrGroups, ...rest } = screen.filters;
    const filters = { ...rest };
    const sec = savedSector ?? '';
    const restoredOrGroups = new Set((savedOrGroups ?? '').split(',').filter(Boolean));
    setFilterInputs(filters);
    setActiveFilters(filters);
    setSectorFilter(sec);
    setActiveSector(sec);
    setOrGroups(restoredOrGroups);
    setOffset(0);
    setSortBy('symbol');
    setSortDir('asc');
    fetchData(filters, sec, 'symbol', 'asc', 0, restoredOrGroups);
  }

  function handleApply() {
    const clean: Record<string, string> = {};
    for (const [k, v] of Object.entries(filterInputs)) {
      if (v.trim()) clean[k] = v.trim();
    }
    setActiveFilters(clean);
    setActiveSector(sectorFilter);
    setOffset(0);
    fetchData(clean, sectorFilter, sortBy, sortDir, 0, orGroups);
  }

  function handleReset() {
    setFilterInputs({});
    setActiveFilters({});
    setSectorFilter('');
    setActiveSector('');
    setOrGroups(new Set());
    setOffset(0);
    setSortBy('symbol');
    setSortDir('asc');
    fetchData({}, '', 'symbol', 'asc', 0, new Set());
  }

  function handleSort(col: string) {
    let newDir: 'asc' | 'desc' = 'asc';
    if (sortBy === col) {
      newDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      newDir = col === 'symbol' || col === 'name' || col === 'sector' ? 'asc' : 'desc';
    }
    setSortBy(col);
    setSortDir(newDir);
    setOffset(0);
    fetchData(activeFilters, activeSector, col, newDir, 0, orGroups);
  }

  function handlePage(newOffset: number) {
    setOffset(newOffset);
    fetchData(activeFilters, activeSector, sortBy, sortDir, newOffset, orGroups);
  }

  function toggleOrGroup(groupKey: string) {
    setOrGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupKey)) {
        next.delete(groupKey);
      } else {
        next.add(groupKey);
      }
      return next;
    });
  }

  function setFilter(key: string, value: string) {
    setFilterInputs((prev) => ({ ...prev, [key]: value }));
  }

  const results: ScreenerRow[] = data?.results ?? [];
  const total = data?.total ?? 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Stock Screener</h1>
        <button
          onClick={() => setFiltersOpen(!filtersOpen)}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          {filtersOpen ? 'Hide Filters' : 'Show Filters'}
        </button>
      </div>

      {/* ---- Saved Screens ---- */}
      {(savedScreens.length > 0 || saveOpen) && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-gray-500 font-medium shrink-0">Saved:</span>
          {savedScreens.map((s) => (
            <span
              key={s.id}
              className="inline-flex items-center gap-1 bg-white border border-gray-200 rounded-full pl-3 pr-1 py-1 group"
            >
              <button
                onClick={() => handleLoadScreen(s)}
                className="text-gray-700 hover:text-red-700 font-medium"
                title="Load this screen"
              >
                {s.name}
              </button>
              <button
                onClick={() => handleDeleteScreen(s.id)}
                className="text-gray-300 hover:text-red-600 p-0.5 rounded-full transition-colors"
                title="Delete"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </span>
          ))}
          {saveOpen && (
            <span className="inline-flex items-center gap-1.5">
              <input
                type="text"
                value={saveName}
                onChange={(e) => setSaveName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSaveScreen()}
                placeholder="Screen name…"
                autoFocus
                className="px-2.5 py-1 border border-gray-300 rounded-full text-sm w-40 focus:outline-none focus:ring-1 focus:ring-red-500"
              />
              <button
                onClick={handleSaveScreen}
                disabled={!saveName.trim() || saving}
                className="px-2.5 py-1 text-xs font-medium bg-red-700 text-white rounded-full hover:bg-red-800 disabled:opacity-40"
              >
                {saving ? '…' : 'Save'}
              </button>
              <button
                onClick={() => { setSaveOpen(false); setSaveName(''); }}
                className="text-gray-400 hover:text-gray-600 text-xs"
              >
                Cancel
              </button>
            </span>
          )}
        </div>
      )}

      {/* ---- Filter panel ---- */}
      {filtersOpen && (
        <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
          {/* Sector filter */}
          <div className="flex items-center gap-3 text-sm">
            <label className="font-medium text-gray-700 w-16">Sector</label>
            <input
              type="text"
              value={sectorFilter}
              onChange={(e) => setSectorFilter(e.target.value)}
              placeholder="e.g. Technology"
              className="px-3 py-1.5 border border-gray-300 rounded text-sm w-48 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Metric filters grouped by category */}
          {FILTER_GROUPS.map((group) => (
            <div key={group.groupKey}>
              <div className="flex items-center gap-2 mb-1.5">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {group.title}
                </p>
                {group.filters.length > 1 && (
                  <button
                    onClick={() => toggleOrGroup(group.groupKey)}
                    className={`text-[10px] font-bold px-1.5 py-0.5 rounded transition-colors ${
                      orGroups.has(group.groupKey)
                        ? 'bg-amber-100 text-amber-700 border border-amber-300'
                        : 'bg-gray-100 text-gray-400 border border-gray-200 hover:text-gray-600'
                    }`}
                    title={orGroups.has(group.groupKey)
                      ? 'Filters in this group are OR\'d — click to switch to AND'
                      : 'Filters in this group are AND\'d — click to switch to OR'}
                  >
                    {orGroups.has(group.groupKey) ? 'OR' : 'AND'}
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                {group.filters.map((f) => (
                  <div key={f.key} className="flex items-center gap-1.5 text-sm">
                    <span className="text-gray-600 w-16 text-right shrink-0">{f.label}</span>
                    {(!f.mode || f.mode === 'min') && (
                      <input
                        type="number"
                        step="any"
                        value={filterInputs[`min_${f.key}`] ?? ''}
                        onChange={(e) => setFilter(`min_${f.key}`, e.target.value)}
                        placeholder="min"
                        className="w-20 px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    )}
                    {(!f.mode || f.mode === 'max') && (
                      <>
                        {!f.mode && <span className="text-gray-400">–</span>}
                        <input
                          type="number"
                          step="any"
                          value={filterInputs[`max_${f.key}`] ?? ''}
                          onChange={(e) => setFilter(`max_${f.key}`, e.target.value)}
                          placeholder="max"
                          className="w-20 px-2 py-1 border border-gray-300 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Apply / Reset / Save */}
          <div className="flex gap-3 pt-1">
            <button
              onClick={handleApply}
              className="px-4 py-1.5 bg-red-700 text-white text-sm font-medium rounded hover:bg-red-800 transition-colors"
            >
              Apply Filters
            </button>
            <button
              onClick={handleReset}
              className="px-4 py-1.5 border border-gray-300 text-gray-600 text-sm font-medium rounded hover:bg-gray-50 transition-colors"
            >
              Reset
            </button>
            <button
              onClick={() => setSaveOpen(true)}
              className="px-4 py-1.5 border border-gray-300 text-gray-600 text-sm font-medium rounded hover:bg-gray-50 transition-colors ml-auto"
            >
              Save Screen
            </button>
          </div>
        </div>
      )}

      {/* ---- Error ---- */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* ---- Results summary ---- */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>
          {loading ? 'Loading...' : `${total.toLocaleString()} results`}
        </span>
        {totalPages > 1 && (
          <span>
            Page {page} of {totalPages}
          </span>
        )}
      </div>

      {/* ---- Results table ---- */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              {COLUMNS.map((col) => {
                const active = sortBy === col.key;
                return (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className="px-3 py-2 text-left font-medium text-gray-600 cursor-pointer hover:text-gray-900 select-none whitespace-nowrap"
                  >
                    {col.label}
                    {active && (
                      <span className="ml-1 text-red-700">
                        {sortDir === 'asc' ? '▲' : '▼'}
                      </span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {results.length === 0 && !loading && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-3 py-8 text-center text-gray-400">
                  No results. Try adjusting your filters or run <code className="bg-gray-100 px-1 rounded">make refresh-screener</code> to populate data.
                </td>
              </tr>
            )}
            {results.map((row) => (
              <tr
                key={row.symbol}
                className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
              >
                {COLUMNS.map((col) => {
                  const raw = row[col.key];
                  let content: React.ReactNode;

                  if (col.key === 'symbol') {
                    content = (
                      <Link
                        to={`/symbol/${row.symbol}`}
                        className="font-semibold text-blue-600 hover:text-blue-800 hover:underline"
                      >
                        {row.symbol}
                      </Link>
                    );
                  } else if (col.key === 'name') {
                    content = (
                      <span className="truncate max-w-[200px] inline-block" title={raw as string ?? ''}>
                        {raw ?? '—'}
                      </span>
                    );
                  } else if (col.fmt) {
                    content = col.fmt(raw);
                  } else {
                    content = raw != null ? String(raw) : '—';
                  }

                  return (
                    <td key={col.key} className="px-3 py-2 whitespace-nowrap text-gray-700">
                      {content}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ---- Pagination ---- */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => handlePage(Math.max(0, offset - PAGE_SIZE))}
            disabled={offset === 0}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
          >
            ← Prev
          </button>
          <span className="text-sm text-gray-600">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => handlePage(offset + PAGE_SIZE)}
            disabled={offset + PAGE_SIZE >= total}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
