import { useState, useRef, useEffect } from "react";
import { format, addDays, subDays } from "date-fns";
import { CalendarDays, BookOpen, Plus, Camera, Sparkles, Menu, BarChart2 } from "lucide-react";
import Dashboard from "./pages/Dashboard";
import LibraryPage from "./pages/LibraryPage";
import ReportsPage from "./pages/ReportsPage";
import AddFoodModal from "./components/AddFoodModal";
import VisionModal from "./components/VisionModal";

const TABS = [
  { id: "today",   label: "Today",   Icon: CalendarDays },
  { id: "library", label: "Library", Icon: BookOpen },
];

export default function App() {
  const [tab, setTab]               = useState("today");
  const [currentDate, setCurrentDate] = useState(new Date());
  const [showAdd, setShowAdd]       = useState(false);
  const [showVision, setShowVision] = useState(false);
  const [dashboardKey, setDashboardKey] = useState(0);
  const [showMenu, setShowMenu]     = useState(false);
  const [showReports, setShowReports] = useState(false);
  const menuRef = useRef(null);

  // Close dropdown when tapping outside
  useEffect(() => {
    if (!showMenu) return;
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setShowMenu(false);
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => { document.removeEventListener("mousedown", handler); document.removeEventListener("touchstart", handler); };
  }, [showMenu]);

  const goBack    = () => setCurrentDate(d => subDays(d, 1));
  const goForward = () => setCurrentDate(d => addDays(d, 1));
  const isToday   = format(currentDate, "yyyy-MM-dd") === format(new Date(), "yyyy-MM-dd");
  const dateStr   = format(currentDate, "yyyy-MM-dd");

  return (
    <div className="relative overflow-x-hidden min-h-screen w-full max-w-md mx-auto bg-surface">

      {/* ── Sticky header ── */}
      <header className="sticky top-0 z-40 bg-surface-1 shadow-nav">
        <div className="px-4 h-14 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-accent-blue flex items-center justify-center">
              <span className="text-white text-xs font-bold">M</span>
            </div>
            <span className="font-bold text-foreground text-base tracking-tight">Macro Tracker</span>
          </div>

          {/* Date nav — only on Today tab */}
          {tab === "today" && (
            <div className="flex items-center gap-2">
              <button onClick={goBack}
                className="w-8 h-8 rounded-full flex items-center justify-center text-muted hover:bg-surface-3 transition-colors text-lg leading-none">
                ‹
              </button>
              <span className="text-sm font-semibold text-foreground min-w-[90px] text-center">
                {isToday ? "Today" : format(currentDate, "MMM d")}
              </span>
              <button onClick={goForward} disabled={isToday}
                className="w-8 h-8 rounded-full flex items-center justify-center text-muted hover:bg-surface-3 transition-colors disabled:opacity-30 text-lg leading-none">
                ›
              </button>
            </div>
          )}

          {tab === "library" && (
            <span className="text-base font-bold text-foreground">Library</span>
          )}

          {/* Hamburger menu */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setShowMenu(m => !m)}
              className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-surface-2 transition-colors text-muted"
            >
              <Menu size={20} />
            </button>

            {showMenu && (
              <div className="absolute right-0 top-11 w-44 bg-white rounded-xl shadow-lg border border-surface-3 overflow-hidden z-50">
                <button
                  onClick={() => { setShowMenu(false); setShowReports(true); }}
                  className="w-full flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-surface-2 transition-colors"
                >
                  <BarChart2 size={15} className="text-accent-blue shrink-0" />
                  Reports
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ── Page content ── */}
      <main className="px-4 pb-28">
        {tab === "today"   && <Dashboard key={dashboardKey} currentDate={currentDate} onOpenAdd={() => setShowAdd(true)} onOpenVision={() => setShowVision(true)} />}
        {tab === "library" && <LibraryPage />}
      </main>

      {/* ── Bottom navigation ── */}
      <nav className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-md bg-white/95 backdrop-blur shadow-nav border-t border-surface-3 flex z-50"
           style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
        {/* Today */}
        <NavItem label="Today" active={tab === "today"} onClick={() => setTab("today")}>
          <CalendarDays size={22} />
        </NavItem>

        {/* Library */}
        <NavItem label="Library" active={tab === "library"} onClick={() => setTab("library")}>
          <BookOpen size={22} />
        </NavItem>

        {/* Center + button */}
        <div className="flex-1 flex items-center justify-center">
          <button
            onClick={() => setShowAdd(true)}
            className="w-13 h-13 rounded-full bg-accent-blue flex items-center justify-center -mt-4 shadow-blue-glow transition-transform active:scale-95"
            style={{ width: 52, height: 52 }}>
            <Plus size={26} className="text-white" />
          </button>
        </div>

        {/* Scan */}
        <NavItem label="Scan" active={false} onClick={() => setShowVision(true)}>
          <Camera size={22} />
        </NavItem>

        {/* Suggest — opens modal from dashboard */}
        <NavItem label="Suggest" active={false} onClick={() => { setTab("today"); }}>
          <Sparkles size={22} />
        </NavItem>
      </nav>

      {/* ── Global modals ── */}
      {showAdd && (
        <AddFoodModal
          dateStr={dateStr}
          defaultMealNumber={null}
          onClose={() => setShowAdd(false)}
          onLogged={() => { setShowAdd(false); setTab("today"); setDashboardKey(k => k + 1); }}
        />
      )}
      {showVision && (
        <VisionModal
          onClose={() => setShowVision(false)}
          onSaved={() => setShowVision(false)}
        />
      )}
      {showReports && (
        <ReportsPage onClose={() => setShowReports(false)} />
      )}
    </div>
  );
}

function NavItem({ label, active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 transition-colors
        ${active ? "text-accent-blue" : "text-muted"}`}>
      {children}
      <span className="text-[10px] font-medium">{label}</span>
    </button>
  );
}
