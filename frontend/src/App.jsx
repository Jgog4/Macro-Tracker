import { useState, useRef, useEffect } from "react";
import { format, addDays, subDays } from "date-fns";
import { CalendarDays, BookOpen, Plus, Camera, Search, Utensils, Sparkles, Menu, BarChart2, X } from "lucide-react";
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
  const [tab, setTab]                 = useState("today");
  const [currentDate, setCurrentDate] = useState(new Date());
  const [showSheet, setShowSheet]     = useState(false);   // add-food action sheet
  const [showAdd, setShowAdd]         = useState(false);   // search modal
  const [showCamera, setShowCamera]   = useState(false);   // scan label modal
  const [showRecipes, setShowRecipes] = useState(false);   // recipes-only modal
  const [savedFood, setSavedFood]     = useState(null);    // food returned from camera scan
  const [dashboardKey, setDashboardKey] = useState(0);
  const [showMenu, setShowMenu]       = useState(false);
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
        {tab === "today"   && <Dashboard key={dashboardKey} currentDate={currentDate} onOpenAdd={() => setShowSheet(true)} onOpenVision={() => setShowCamera(true)} />}
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
            onClick={() => setShowSheet(true)}
            className="w-13 h-13 rounded-full bg-accent-blue flex items-center justify-center -mt-4 shadow-blue-glow transition-transform active:scale-95"
            style={{ width: 52, height: 52 }}>
            <Plus size={26} className="text-white" />
          </button>
        </div>

        {/* Scan */}
        <NavItem label="Scan" active={false} onClick={() => setShowCamera(true)}>
          <Camera size={22} />
        </NavItem>

        {/* Suggest — opens modal from dashboard */}
        <NavItem label="Suggest" active={false} onClick={() => { setTab("today"); }}>
          <Sparkles size={22} />
        </NavItem>
      </nav>

      {/* ── Add Food action sheet ── */}
      {showSheet && (
        <div
          className="fixed inset-0 z-50 flex items-end"
          style={{ backgroundColor: "rgba(0,0,0,0.4)" }}
          onClick={() => setShowSheet(false)}
        >
          <div
            className="w-full max-w-md mx-auto bg-white rounded-t-3xl px-4 pt-4 pb-8"
            style={{ paddingBottom: "calc(32px + env(safe-area-inset-bottom,0px))" }}
            onClick={e => e.stopPropagation()}
          >
            <div className="w-9 h-1 bg-surface-3 rounded-full mx-auto mb-5" />
            <div className="flex items-center justify-between mb-4 px-1">
              <h2 className="text-lg font-bold text-foreground">Add Food</h2>
              <button onClick={() => setShowSheet(false)} className="w-8 h-8 flex items-center justify-center rounded-full bg-surface-2 text-muted">
                <X size={15} />
              </button>
            </div>

            <div className="flex flex-col gap-3">
              {/* Search */}
              <button
                onClick={() => { setShowSheet(false); setSavedFood(null); setShowAdd(true); }}
                className="flex items-center gap-4 p-4 rounded-2xl bg-surface-1 active:bg-surface-2 text-left transition-colors"
              >
                <div className="w-11 h-11 rounded-2xl bg-blue-100 flex items-center justify-center shrink-0">
                  <Search size={20} className="text-accent-blue" />
                </div>
                <div>
                  <p className="font-semibold text-foreground">Search Foods</p>
                  <p className="text-xs text-muted mt-0.5">Search USDA database and your foods</p>
                </div>
              </button>

              {/* Take a Photo */}
              <button
                onClick={() => { setShowSheet(false); setShowCamera(true); }}
                className="flex items-center gap-4 p-4 rounded-2xl bg-surface-1 active:bg-surface-2 text-left transition-colors"
              >
                <div className="w-11 h-11 rounded-2xl bg-purple-100 flex items-center justify-center shrink-0">
                  <Camera size={20} className="text-purple-600" />
                </div>
                <div>
                  <p className="font-semibold text-foreground">Take a Photo</p>
                  <p className="text-xs text-muted mt-0.5">Scan a nutrition label — saves to My Foods</p>
                </div>
              </button>

              {/* From Recipes */}
              <button
                onClick={() => { setShowSheet(false); setShowRecipes(true); }}
                className="flex items-center gap-4 p-4 rounded-2xl bg-surface-1 active:bg-surface-2 text-left transition-colors"
              >
                <div className="w-11 h-11 rounded-2xl bg-green-100 flex items-center justify-center shrink-0">
                  <Utensils size={20} className="text-green-600" />
                </div>
                <div>
                  <p className="font-semibold text-foreground">From Recipes</p>
                  <p className="text-xs text-muted mt-0.5">Log one of your saved recipes</p>
                </div>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Global modals ── */}

      {/* Search modal */}
      {showAdd && (
        <AddFoodModal
          dateStr={dateStr}
          defaultMealNumber={null}
          preselected={savedFood}
          onClose={() => { setShowAdd(false); setSavedFood(null); }}
          onLogged={() => { setShowAdd(false); setSavedFood(null); setTab("today"); setDashboardKey(k => k + 1); }}
        />
      )}

      {/* Camera / label scan — saves to My Foods, then opens log screen */}
      {showCamera && (
        <VisionModal
          onClose={() => setShowCamera(false)}
          onSaved={(food) => {
            setShowCamera(false);
            if (food) { setSavedFood(food); setShowAdd(true); }
            setDashboardKey(k => k + 1);   // refresh today view
          }}
        />
      )}

      {/* Recipes-only log modal */}
      {showRecipes && (
        <AddFoodModal
          dateStr={dateStr}
          defaultMealNumber={null}
          recipesOnly
          onClose={() => setShowRecipes(false)}
          onLogged={() => { setShowRecipes(false); setTab("today"); setDashboardKey(k => k + 1); }}
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
