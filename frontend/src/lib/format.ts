export function formatPeriod(period: string): string {
  const m = /^(\d{4})Q(\d)$/.exec(period);
  if (!m) return period;
  return `${m[1]}年${m[2]}季度`;
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function skillLevelWord(level: number): string {
  if (level >= 3) return "能独立交付";
  if (level >= 2) return "项目里用过";
  if (level >= 1) return "学过或接触过";
  return "尚未掌握";
}

export function readTheme(): "light" | "dark" {
  const saved = localStorage.getItem("jobe.theme");
  if (saved === "dark" || saved === "light") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: "light" | "dark"): void {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("jobe.theme", theme);
}
