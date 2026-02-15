import { BrowserRouter, Routes, Route, Outlet, Link, useNavigate, useMatch } from 'react-router-dom';
import SearchBar from './components/SearchBar';
import SymbolPage from './pages/SymbolPage';
import ScreenerPage from './pages/ScreenerPage';
import TournamentPage from './pages/TournamentPage';

function Layout() {
  const navigate = useNavigate();
  const symbolMatch = useMatch('/symbol/:symbol');
  const currentSymbol = symbolMatch?.params.symbol || '';

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center gap-6">
          <Link to="/" className="text-lg font-bold text-gray-800 shrink-0 hover:text-gray-600">
            Stocks
          </Link>
          <SearchBar
            onSelect={(sym) => navigate(`/symbol/${sym}`)}
            currentSymbol={currentSymbol}
          />
          <Link
            to="/screener"
            className="text-sm font-medium text-gray-600 hover:text-red-700 shrink-0"
          >
            Screener
          </Link>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}

function HomePage() {
  const navigate = useNavigate();

  return (
    <div className="text-center py-20 text-gray-400">
      <p className="text-xl mb-2">Search for a stock symbol to get started</p>
      <p className="text-sm">
        Try{' '}
        <button onClick={() => navigate('/symbol/COST')} className="text-blue-500 hover:underline">
          COST
        </button>
        ,{' '}
        <button onClick={() => navigate('/symbol/AAPL')} className="text-blue-500 hover:underline">
          AAPL
        </button>
        , or{' '}
        <button onClick={() => navigate('/symbol/MSFT')} className="text-blue-500 hover:underline">
          MSFT
        </button>
      </p>
      <p className="text-sm mt-4">
        Or try the{' '}
        <button onClick={() => navigate('/screener')} className="text-blue-500 hover:underline">
          Screener
        </button>
      </p>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="symbol/:symbol" element={<SymbolPage />} />
          <Route path="screener" element={<ScreenerPage />} />
          <Route path="tournament" element={<TournamentPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
