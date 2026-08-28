import { Compass, Moon, Queue, Sun } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { applyTheme, readTheme } from "../lib/format";
import { EvidenceDrawer } from "./EvidenceDrawer";

const NAV = [
  { to: "/", label: "我", end: true },
  { to: "/market", label: "市场", end: false },
  { to: "/graph", label: "图谱", end: false },
];

export function Shell() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [reviewCount, setReviewCount] = useState(0);
  const [params] = useSearchParams();
  const location = useLocation();
  const meActive = location.pathname === "/" || location.pathname.startsWith("/diagnose");

  useEffect(() => {
    const t = readTheme();
    setTheme(t);
    applyTheme(t);
  }, []);

  useEffect(() => {
    api.getReviewQueue().then((q) => setReviewCount(q.length)).catch(() => setReviewCount(0));
  }, [params]);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
  }

  return (
    <div className="min-h-[100dvh] bg-paper text-ink">
        <a href="#main" className="skip-link">
          跳到主内容
        </a>
      <header className="sticky top-0 z-[20] border-b border-rule bg-paper/95 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center gap-6 px-4 sm:px-6">
          <NavLink to="/" className="flex items-center gap-2 font-medium tracking-tight">
            <Compass size={20} weight="regular" aria-hidden="true" />
            职途罗盘
          </NavLink>
          <nav aria-label="主导航" className="flex items-center gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => {
                  const on = item.to === "/" ? meActive : isActive;
                  return ["px-3 py-2 text-sm", on ? "text-ink" : "text-ink-soft hover:text-ink"].join(" ");
                }}
              >
                {({ isActive }) => {
                  const on = item.to === "/" ? meActive : isActive;
                  return (
                    <span className={on ? "border-b-2 border-accent pb-0.5" : "pb-0.5"}>{item.label}</span>
                  );
                }}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <NavLink
              to="/review"
              className="relative inline-flex size-10 items-center justify-center rounded-[4px] hover:bg-paper-2"
              aria-label={reviewCount ? `待确认 ${reviewCount} 项` : "待确认队列"}
            >
              <Queue size={18} />
              {reviewCount > 0 ? (
                <span className="absolute right-1.5 top-1.5 size-1.5 bg-accent" aria-hidden="true" />
              ) : null}
            </NavLink>
            <button
              type="button"
              onClick={toggleTheme}
              className="inline-flex size-10 items-center justify-center rounded-[4px] hover:bg-paper-2"
              aria-label={theme === "dark" ? "切换到浅色" : "切换到深色"}
            >
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </div>
      </header>
      <Outlet />
      <EvidenceDrawer />
    </div>
  );
}
