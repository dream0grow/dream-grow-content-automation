import { Link, NavLink, Route, Routes } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import EditorPage from "./pages/EditorPage";
import CalendarPage from "./pages/CalendarPage";
import { useSystemStatus } from "./api/hooks";

function StatusDot() {
  const { data } = useSystemStatus();
  if (!data) return null;
  return (
    <div className="flex items-center gap-3 text-xs text-gray-500">
      <span className="flex items-center gap-1">
        <span
          className={`inline-block h-2 w-2 rounded-full ${data.scheduler_running ? "bg-green-500" : "bg-red-500"}`}
        />
        스케줄러
      </span>
      {data.mock_llm && (
        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-700">
          Mock LLM
        </span>
      )}
      {data.dry_run && (
        <span className="rounded bg-blue-100 px-1.5 py-0.5 text-blue-700">
          Dry-run 발행
        </span>
      )}
    </div>
  );
}

export default function App() {
  const navClass = ({ isActive }: { isActive: boolean }) =>
    `rounded px-3 py-1.5 text-sm font-medium ${
      isActive ? "bg-gray-900 text-white" : "text-gray-600 hover:bg-gray-100"
    }`;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <Link to="/" className="text-lg font-bold text-gray-900">
              Dream Grow
            </Link>
            <nav className="flex gap-1">
              <NavLink to="/" end className={navClass}>
                대시보드
              </NavLink>
              <NavLink to="/calendar" className={navClass}>
                발행 캘린더
              </NavLink>
            </nav>
          </div>
          <StatusDot />
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/contents/:id" element={<EditorPage />} />
          <Route path="/calendar" element={<CalendarPage />} />
        </Routes>
      </main>
    </div>
  );
}
