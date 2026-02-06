import { useState, useEffect, useRef } from 'react';
import { searchSymbols } from '../api/client';
import type { SearchResult } from '../types';

interface Props {
  onSelect: (symbol: string) => void;
  currentSymbol?: string;
}

export default function SearchBar({ onSelect, currentSymbol }: Props) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  function handleChange(value: string) {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (value.length < 1) {
      setResults([]);
      setOpen(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await searchSymbols(value);
        setResults(res);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
  }

  function handleSelect(symbol: string) {
    setQuery('');
    setOpen(false);
    onSelect(symbol);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && query.trim()) {
      setOpen(false);
      onSelect(query.trim().toUpperCase());
      setQuery('');
    }
  }

  return (
    <div ref={ref} className="relative w-full max-w-md">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Search symbol or company..."
          className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {loading && (
          <div className="absolute right-3 top-2.5">
            <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-500 rounded-full animate-spin" />
          </div>
        )}
      </div>
      {currentSymbol && !query && (
        <span className="absolute -top-6 left-0 text-xs text-gray-400">
          Viewing: {currentSymbol}
        </span>
      )}
      {open && results.length > 0 && (
        <ul className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
          {results.map((r) => (
            <li
              key={r.symbol}
              onClick={() => handleSelect(r.symbol)}
              className="px-4 py-2 cursor-pointer hover:bg-blue-50 flex justify-between items-center text-sm"
            >
              <span className="font-semibold text-gray-900">{r.symbol}</span>
              <span className="text-gray-500 truncate ml-3">{r.name}</span>
              {r.exchange && (
                <span className="text-xs text-gray-400 ml-2 shrink-0">{r.exchange}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
