import type { SymbolPageData, SearchResult, ScreenerResponse, SavedScreen, CompanyInfo } from '../types';

const BASE = '/api';

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${text}`);
  }
  return resp.json();
}

export async function getSymbolPage(symbol: string): Promise<SymbolPageData> {
  return fetchJSON<SymbolPageData>(`${BASE}/symbol/${encodeURIComponent(symbol)}`);
}

export async function updateSymbolMeta(
  symbol: string,
  payload: { rating?: 'good' | 'bad' | null; note?: string | null },
): Promise<CompanyInfo> {
  return fetchJSON<CompanyInfo>(`${BASE}/symbol/${encodeURIComponent(symbol)}/meta`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
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

// ---------------------------------------------------------------------------
// Saved Screens
// ---------------------------------------------------------------------------

export async function getSavedScreens(): Promise<SavedScreen[]> {
  return fetchJSON<SavedScreen[]>(`${BASE}/screens`);
}

export async function createSavedScreen(
  name: string,
  filters: Record<string, string>,
): Promise<SavedScreen> {
  return fetchJSON<SavedScreen>(`${BASE}/screens`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, filters }),
  });
}

export async function deleteSavedScreen(id: number): Promise<void> {
  const resp = await fetch(`${BASE}/screens/${id}`, { method: 'DELETE' });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${text}`);
  }
}
