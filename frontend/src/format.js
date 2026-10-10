const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const shortFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

export const toDate = (v) => (v instanceof Date ? v : v ? new Date(v) : null);
export const fmtDate = (v) => (v ? dateFmt.format(toDate(v)) : "—");
export const fmtShort = (v) => (v ? shortFmt.format(toDate(v)) : "—");
export const fmtDateTime = (v) => (v ? `${dateFmt.format(toDate(v))}, ${timeFmt.format(toDate(v))}` : "—");
export const fmtNum = (n) => (n ?? 0).toLocaleString("en-GB");

// "2026-10-09" (a UTC calendar day from the API) -> "9 Oct"
export const fmtDay = (iso) => shortFmt.format(new Date(`${iso}T00:00:00Z`));

export function timeAgo(v, now = new Date()) {
  const d = toDate(v);
  if (!d) return "never";
  const s = Math.round((now - d) / 1000);
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

export const SOURCE_NAMES = {
  wisden: "Wisden",
  hindustantimes: "Hindustan Times",
  crictracker: "CricTracker",
  cricketaddictor: "Cricket Addictor",
};
export const sourceName = (s) => SOURCE_NAMES[s] ?? s;

// ISO yyyy-mm-dd for date inputs / API params
export const isoDay = (d) => d.toISOString().slice(0, 10);
export const addDays = (iso, n) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return isoDay(d);
};

const fullFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
export const fmtUpdated = (v) => (v ? fullFmt.format(toDate(v)).replace(",", " ·") : "—");

/** Sum daily values into weeks starting on Monday: [{day, value}] -> [{day (week start), value}] */
export function toWeeks(rows, key) {
  const out = new Map();
  for (const r of rows) {
    const d = new Date(`${r.day}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    const wk = isoDay(d);
    const prev = out.get(wk) ?? { day: wk };
    for (const k of key) prev[k] = (prev[k] ?? 0) + (r[k] ?? 0);
    out.set(wk, prev);
  }
  return [...out.values()];
}
export const fmtWeek = (iso) => `w/c ${fmtDay(iso)}`;
