import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api.js";
import { Card, ChartCard, HBars, Notice, SimpleTable, Topbar } from "../components.jsx";
import { addDays, fmtDay, fmtNum, fmtWeek, sourceName, toWeeks } from "../format.js";
import { IconCalendar } from "../icons.jsx";

const C = { forest: "#556B5A", sage: "#8FB08A", pale: "#C9D8C4", sand: "#E6D9C7", white: "#FFFFFF" };
const RANGES = [
  { value: "7", label: "Last 7 days" },
  { value: "14", label: "Last 14 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
  { value: "custom", label: "Custom range" },
];
const MAX_LINES = 12;          // context lines beyond this add noise, not information

function growthText(t) {
  if (t.is_new) return "new";
  if (t.growth_pct == null) return t.change > 0 ? `+${t.change}` : String(t.change);
  return `${t.growth_pct > 0 ? "+" : ""}${Math.round(t.growth_pct)}%`;
}

function TrendTip({ active, payload, label, labels, focus, weekly }) {
  if (!active || !payload?.length) return null;
  const rows = payload.filter((p) => p.value > 0).sort((a, b) => b.value - a.value);
  return (
    <div className="tooltip">
      <div className="t-title">{weekly ? fmtWeek(label) : fmtDay(label)}</div>
      {rows.length === 0 && <div>No topic articles</div>}
      {rows.slice(0, 8).map((p) => (
        <div className="t-row" key={p.dataKey}>
          <span className={`k ${p.dataKey === focus ? "strong" : ""}`} /><strong>{p.value}</strong><span>{labels[p.dataKey]}</span>
        </div>
      ))}
      {rows.length > 8 && <div style={{ marginTop: 4 }}>+{rows.length - 8} more topics</div>}
    </div>
  );
}

export default function Trending() {
  const meta = useApi("/api/meta");
  const latest = meta.data?.dates?.max ?? null;
  const [range, setRange] = useState("30");
  const [custom, setCustom] = useState({ from: "", to: "" });
  const [source, setSource] = useState("");
  const [view, setView] = useState("daily");
  const [highlight, setHighlight] = useState(null);
  const [hover, setHover] = useState(null);

  const dates = useMemo(() => {
    if (range === "custom") return { date_from: custom.from, date_to: custom.to };
    if (!latest) return null;
    return { date_from: addDays(latest, -(Number(range) - 1)), date_to: latest };
  }, [range, custom, latest]);
  const ready = !!dates && (range !== "custom" || (custom.from && custom.to && custom.from <= custom.to));
  const { data, error, loading } = useApi("/api/trends", { ...dates, source }, { enabled: ready });

  const topics = data?.topics ?? [];
  const byGrowth = useMemo(() => [...topics].sort((a, b) => b.change - a.change || b.total - a.total), [topics]);
  const labels = useMemo(() => Object.fromEntries(topics.map((t) => [t.stable_key, t.label])), [topics]);
  const shown = useMemo(() => {
    const keys = new Set(topics.slice(0, MAX_LINES).map((t) => t.stable_key));
    byGrowth.slice(0, 3).forEach((t) => keys.add(t.stable_key));
    return topics.filter((t) => keys.has(t.stable_key));
  }, [topics, byGrowth]);
  useEffect(() => {                         // default emphasis: the fastest-growing topic
    if (topics.length && (!highlight || !labels[highlight])) setHighlight(byGrowth[0].stable_key);
  }, [topics, byGrowth, labels, highlight]);
  const focus = hover ?? highlight;

  const weekly = view === "weekly";
  const rows = useMemo(() => {
    const daily = (data?.days ?? []).map((day, i) => {
      const r = { day };
      for (const t of shown) r[t.stable_key] = t.series[i];
      return r;
    });
    return weekly ? toWeeks(daily, shown.map((t) => t.stable_key)) : daily;
  }, [data, shown, weekly]);

  const rangeLabel = range === "custom"
    ? (data ? `${fmtDay(data.date_from)} – ${fmtDay(data.date_to)}` : "custom range")
    : RANGES.find((r) => r.value === range).label;
  const cmp = data?.comparison;
  const cmpText = cmp?.previous ? `${fmtDay(cmp.recent[0])}–${fmtDay(cmp.recent[1])} vs ${fmtDay(cmp.previous[0])}–${fmtDay(cmp.previous[1])}` : null;
  const rising = byGrowth.filter((t) => t.change > 0);

  return (
    <>
      <Topbar title="Trending Topics" subtitle="Track how news topics change over time" />

      <Card className="filter-card">
        <div className="filter-row">
          <label className="field">Date range
            <span className="with-icon">
              <IconCalendar size={17} />
              <select className="select" value={range} onChange={(e) => setRange(e.target.value)}>
                {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </span>
          </label>
          {range === "custom" && (
            <>
              <label className="field" style={{ flexBasis: 170 }}>From
                <input className="input" type="date" value={custom.from} max={custom.to || undefined}
                       onChange={(e) => setCustom({ ...custom, from: e.target.value })} />
              </label>
              <label className="field" style={{ flexBasis: 170 }}>To
                <input className="input" type="date" value={custom.to} min={custom.from || undefined}
                       onChange={(e) => setCustom({ ...custom, to: e.target.value })} />
              </label>
            </>
          )}
          <label className="field">Source
            <select className="select" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">All Sources</option>
              {(meta.data?.sources ?? []).map((s) => <option key={s} value={s}>{sourceName(s)}</option>)}
            </select>
          </label>
          <label className="field">View
            <select className="select" value={view} onChange={(e) => setView(e.target.value)}>
              <option value="daily">Daily</option><option value="weekly">Weekly</option>
            </select>
          </label>
        </div>
      </Card>

      {range === "custom" && !ready && <Notice>Pick a start and an end date.</Notice>}
      {error && !data && <Notice error={error} />}
      {ready && !data && !error && <Notice>Loading trends…</Notice>}

      {data && (
        <div className="stack">
          <ChartCard title="Topic Trends Over Time" loading={loading}
                     subtitle={`${weekly ? "Articles per topic per week" : "Articles per topic per day"} · select a topic to highlight it`}
                     table={<SimpleTable head={["Topic", ...rows.map((r) => (weekly ? fmtWeek(r.day) : fmtDay(r.day))), "Total"]}
                                         rows={shown.map((t) => [t.label, ...rows.map((r) => r[t.stable_key] ?? 0), t.total])} />}>
            {topics.length === 0 ? <Notice>No topic articles in this range.</Notice> : (
              <div className="trend-layout">
                <ResponsiveContainer width="100%" height={330}>
                  <LineChart data={rows} margin={{ top: 10, right: 16, bottom: 4, left: 4 }}>
                    <CartesianGrid vertical={false} stroke={C.sand} />
                    <XAxis dataKey="day" tickFormatter={weekly ? fmtWeek : fmtDay} stroke={C.sand} tickLine={false} minTickGap={22} />
                    <YAxis allowDecimals={false} stroke={C.sand} tickLine={false} axisLine={false} width={46}
                           label={{ value: "Number of articles", angle: -90, position: "insideLeft", offset: 14, fill: C.forest, fontSize: 12 }} />
                    <Tooltip content={<TrendTip labels={labels} focus={focus} weekly={weekly} />} cursor={{ stroke: C.forest, strokeWidth: 1 }} isAnimationActive={false} />
                    {shown.filter((t) => t.stable_key !== focus).map((t) => (
                      <Line key={t.stable_key} dataKey={t.stable_key} type="linear" stroke={C.pale} strokeWidth={1.6} dot={false} activeDot={false} isAnimationActive={false} />
                    ))}
                    {shown.filter((t) => t.stable_key === focus).map((t) => (
                      <Line key={t.stable_key} dataKey={t.stable_key} type="linear" stroke={C.forest} strokeWidth={2.5}
                            dot={{ r: 3.5, fill: C.forest, stroke: C.white, strokeWidth: 1.5 }}
                            activeDot={{ r: 5, fill: C.forest, stroke: C.white, strokeWidth: 2 }} isAnimationActive={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
                <div className="trend-legend" role="group" aria-label="Highlight a topic">
                  {shown.map((t) => (
                    <button key={t.stable_key} type="button" aria-pressed={t.stable_key === highlight}
                            onClick={() => setHighlight(t.stable_key)}
                            onMouseEnter={() => setHover(t.stable_key)} onMouseLeave={() => setHover(null)}
                            onFocus={() => setHover(t.stable_key)} onBlur={() => setHover(null)}>
                      <span className="legend-key"><span className={`line ${t.stable_key === focus ? "strong" : ""}`} /></span>
                      <span>{t.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </ChartCard>

          <div className="row2">
            <ChartCard title={`Top Topics (${rangeLabel})`} subtitle="Total article volume per topic" loading={loading}
                       table={<SimpleTable head={["Topic", "Articles"]} rows={topics.map((t) => [t.label, fmtNum(t.total)])} />}>
              <HBars leftLabels rows={topics.slice(0, 8).map((t) => ({
                key: t.stable_key, label: t.label, value: t.total, onClick: () => setHighlight(t.stable_key),
                title: "Highlight this topic in the chart above",
              }))} empty="No topic articles in this range." />
            </ChartCard>

            <Card title="Fastest Growing Topics" loading={loading}
                  subtitle={cmpText ? `Growth in article volume: ${cmpText}` : "Choose a range of at least two days to compare periods"}>
              {rising.length === 0 ? <p className="muted-note">No topic gained coverage between the two halves of this range.</p> : (
                <div className="table-wrap">
                  <table className="data">
                    <thead><tr><th>Topic</th><th className="num">Earlier</th><th className="num">Later</th><th className="num">Growth</th></tr></thead>
                    <tbody>{rising.slice(0, 8).map((t) => (
                      <tr key={t.stable_key} style={{ cursor: "pointer" }} onClick={() => setHighlight(t.stable_key)}>
                        <td>{t.label}</td><td className="num">{t.previous}</td><td className="num">{t.recent}</td>
                        <td className="num"><strong>{growthText(t)}</strong></td>
                      </tr>
                    ))}</tbody>
                  </table>
                  {rising.some((t) => t.is_new) && <p className="muted-note" style={{ marginTop: 10 }}>“new”: no articles in the earlier period.</p>}
                </div>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
