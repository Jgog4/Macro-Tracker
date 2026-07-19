/**
 * CalendarPicker — iOS-style month grid modal.
 * Opens when the user taps the date in the header.
 * Allows jumping back months/years.
 */
import { useState, useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import {
  startOfMonth, endOfMonth, startOfWeek, endOfWeek,
  addDays, addMonths, subMonths, format, isSameMonth,
  isSameDay, isAfter,
} from "date-fns";

const DOW = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

export default function CalendarPicker({ currentDate, onSelect, onClose }) {
  const today = new Date();
  const [viewMonth, setViewMonth] = useState(
    new Date(currentDate.getFullYear(), currentDate.getMonth(), 1)
  );
  const [pickingYear, setPickingYear] = useState(false);
  const ref = useRef();

  // Close on outside tap
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [onClose]);

  // Build calendar grid
  const monthStart = startOfMonth(viewMonth);
  const monthEnd   = endOfMonth(viewMonth);
  const gridStart  = startOfWeek(monthStart);
  const gridEnd    = endOfWeek(monthEnd);

  const days = [];
  let d = gridStart;
  while (!isAfter(d, gridEnd)) {
    days.push(d);
    d = addDays(d, 1);
  }

  // Year picker: show ±6 years from viewMonth year
  const viewYear = viewMonth.getFullYear();
  const years = Array.from({ length: 13 }, (_, i) => viewYear - 6 + i);

  const handleDayClick = (day) => {
    if (isAfter(day, today)) return; // no future dates
    onSelect(day);
    onClose();
  };

  return (
    /* Backdrop */
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-16 px-4"
         style={{ background: "rgba(0,0,0,0.35)" }}>
      <div ref={ref}
           className="w-full max-w-sm bg-surface-1 rounded-2xl shadow-xl overflow-hidden">

        {/* ── Header: month/year + nav ── */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-surface-3">
          <button
            onClick={() => setViewMonth(m => subMonths(m, 1))}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-2 text-muted">
            <ChevronLeft size={18} />
          </button>

          {/* Tap month/year to open year picker */}
          <button
            onClick={() => setPickingYear(p => !p)}
            className="text-sm font-semibold text-foreground hover:text-accent-blue transition-colors px-2 py-1 rounded-lg hover:bg-surface-2">
            {format(viewMonth, "MMMM yyyy")}
            <span className="ml-1 text-muted text-xs">{pickingYear ? "▲" : "▼"}</span>
          </button>

          <button
            onClick={() => setViewMonth(m => addMonths(m, 1))}
            disabled={isSameMonth(viewMonth, today)}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-2 text-muted disabled:opacity-30">
            <ChevronRight size={18} />
          </button>
        </div>

        {/* ── Year picker overlay ── */}
        {pickingYear && (
          <div className="grid grid-cols-3 gap-2 px-4 py-3 border-b border-surface-3 bg-surface">
            {years.map(y => (
              <button
                key={y}
                onClick={() => {
                  setViewMonth(new Date(y, viewMonth.getMonth(), 1));
                  setPickingYear(false);
                }}
                className={`py-1.5 rounded-lg text-sm font-medium transition-colors
                  ${y === viewYear
                    ? "bg-accent-blue text-white"
                    : "hover:bg-surface-3 text-foreground"}`}>
                {y}
              </button>
            ))}
          </div>
        )}

        {/* ── Day-of-week headers ── */}
        <div className="grid grid-cols-7 px-2 pt-2">
          {DOW.map(dow => (
            <div key={dow}
                 className="text-center text-[11px] font-medium text-muted py-1">
              {dow}
            </div>
          ))}
        </div>

        {/* ── Day grid ── */}
        <div className="grid grid-cols-7 px-2 pb-3">
          {days.map((day, i) => {
            const inMonth  = isSameMonth(day, viewMonth);
            const selected = isSameDay(day, currentDate);
            const isToday  = isSameDay(day, today);
            const future   = isAfter(day, today);

            return (
              <button
                key={i}
                onClick={() => handleDayClick(day)}
                disabled={future || !inMonth}
                className={`
                  relative h-9 w-full flex items-center justify-center rounded-full
                  text-sm transition-colors
                  ${!inMonth || future ? "opacity-0 pointer-events-none" : ""}
                  ${selected
                    ? "bg-accent-blue text-white font-semibold"
                    : isToday
                      ? "border border-accent-blue text-accent-blue font-semibold hover:bg-blue-50"
                      : "text-foreground hover:bg-surface-2"}
                `}>
                {format(day, "d")}
              </button>
            );
          })}
        </div>

        {/* ── Jump to today ── */}
        {!isSameDay(currentDate, today) && (
          <div className="border-t border-surface-3 px-4 py-2">
            <button
              onClick={() => { onSelect(today); onClose(); }}
              className="w-full text-center text-sm font-medium text-accent-blue py-1.5 hover:bg-surface-2 rounded-lg transition-colors">
              Jump to Today
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
