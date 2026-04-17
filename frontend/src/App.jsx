import { useState } from "react";
import { format, addDays, subDays, parseISO } from "date-fns";
import Dashboard from "./pages/Dashboard";

export default function App() {
  const [currentDate, setCurrentDate] = useState(new Date());

  const goBack    = () => setCurrentDate(d => subDays(d, 1));
  const goForward = () => setCurrentDate(d => addDays(d, 1));
  const isToday   = format(currentDate, "yyyy-MM-dd") === format(new Date(), "yyyy-MM-dd");

  return (
    <div className="min-h-screen bg-surface text-white">
      {/* ── Top navigation bar ─── */}
      <header className="sticky top-0 z-40 bg-surface/90 backdrop-blur border-b border-border">
        <div className="max-w-2xl mx-auto px-4 h-14 flex items-center justify-between">
          {/* Logo */}
          <span className="font-semibold text-sm tracking-tight text-white flex items-center gap-2">
            <span className="w-6 h-6 rounded-md bg-accent-blue flex items-center justify-center text-xs font-bold">M</span>
            Macro Tracker
          </span>

          {/* Date navigator */}
          <div className="flex items-center gap-3">
            <button onClick={goBack}
              className="w-7 h-7 rounded-full flex items-center justify-center text-subtle hover:text-white hover:bg-surface-3 transition-colors">
              ‹
            </button>
            <span className="text-sm font-medium min-w-[100px] text-center">
              {isToday ? "Today" : format(currentDate, "MMM d, yyyy")}
            </span>
            <button onClick={goForward} disabled={isToday}
              className="w-7 h-7 rounded-full flex items-center justify-center text-subtle hover:text-white hover:bg-surface-3 transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
              ›
            </button>
          </div>

          {/* Spacer to balance logo */}
          <div className="w-[110px]" />
        </div>
      </header>

      {/* ── Main content ─── */}
      <main className="max-w-2xl mx-auto px-4 pb-24">
        <Dashboard currentDate={currentDate} />
      </main>
    </div>
  );
}
