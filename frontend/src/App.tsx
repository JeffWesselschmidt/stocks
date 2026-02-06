import { useState } from 'react';
import SearchBar from './components/SearchBar';
import SymbolPage from './pages/SymbolPage';

export default function App() {
  const [symbol, setSymbol] = useState<string>('');

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center gap-6">
          <h1 className="text-lg font-bold text-gray-800 shrink-0">Stocks</h1>
          <SearchBar onSelect={setSymbol} currentSymbol={symbol} />
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        {symbol ? (
          <SymbolPage symbol={symbol} />
        ) : (
          <div className="text-center py-20 text-gray-400">
            <p className="text-xl mb-2">Search for a stock symbol to get started</p>
            <p className="text-sm">
              Try <button onClick={() => setSymbol('COST')} className="text-blue-500 hover:underline">COST</button>,{' '}
              <button onClick={() => setSymbol('AAPL')} className="text-blue-500 hover:underline">AAPL</button>, or{' '}
              <button onClick={() => setSymbol('MSFT')} className="text-blue-500 hover:underline">MSFT</button>
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
