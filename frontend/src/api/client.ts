import type { SymbolPageData, SearchResult, ScreenerResponse } from '../types';

const BASE = '/api';

async function fetchJSON<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${text}`);
  }
  return resp.json();
}

export async function getSymbolPage(symbol: string): Promise<SymbolPageData> {
  return fetchJSON<SymbolPageData>(`${BASE}/symbol/${encodeURIComponent(symbol)}`);
}

export async function searchSymbols(query: string): Promise<SearchResult[]> {
  return fetchJSON<SearchResult[]>(`${BASE}/search?q=${encodeURIComponent(query)}`);
}

export async function getScreenerResults(
  params: Record<string, string>,
): Promise<ScreenerResponse> {
  const qs = new URLSearchParams(params).toString();
  return fetchJSON<ScreenerResponse>(`${BASE}/screener?${qs}`);
}
