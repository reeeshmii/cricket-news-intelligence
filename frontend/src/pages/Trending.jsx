import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api.js";
import { BarList, ChartCard, KpiCard, Notice, Segmented, Topbar } from "../components.jsx";
import { IconArticles, IconUp } from "../icons.jsx";
import { addDays, fmtDay, fmtNum, sourceName } from "../format.js";

const C = { forest: "#556B5A", sage: "#8FB08A", pale: "#C9D8C4", sand: "#E6D9C7", white: "#FFFFFF" };
const PRESETS = [
  { value: 7, label: "7 days" },
  { value: 14, label: "14 days" },
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
  { value: "custom", label: "Custom" },
];
const MAX_LINES = 12;          // context lines beyond this add noise, not information
const axisProps = { stroke: C.sand, tickLine: false, axisLine: { stroke: C.sand } };

function growthText(t) {
  if (t.is_new) return `+${t.change} · new`;
  if (t.growth_pct == null) return t.change > 0 ? `+${t.change}` : String(t.change);
  return `${t.change > 0 ? "+" : ""}${t.change} · ${t.growth_pct > 0 ? "+" : ""}${Math.round(t.growth_pct)}%`;
}

// ------------------------------------------------------------------ tooltips (values lead, labels follow)
function VolumeTip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="t-title">{fmtDay(label)}</div>
      <div className="t-row"><span className="k strong" /><strong>{fmtNum(payload[0].value)}</strong><span>articles</span></div>
    </div>
  );
}

function TopicsTip({ active, payload, label, labels, highlight }) {
  if (!active || !payload?.length) return null;
  const rows = payload.filter((p) => p.value > 0).sort((a, b) => b.value - a.value);
  return (
    <div className="tooltip">
      <div className="t-title">{fmtDay(label)}</div>
      {rows.length === 0 && <div>No topic articles this day</div>}
      {rows.slice(0, 8).map((p) => (
        <div className="t-row" key={p.dataKey}>
          <span className={`k ${p.dataKey === highlight ? "strong" : ""}`} />
          <strong>{p.value}</strong>
          <span>{labels[p.dataKey]}</span>
        </div>
      ))}
      {rows.length > 8 && <div style={{ marginTop: 4 }}>+{rows.length - 8} more topics</div>}
    </div>
  );
}

// ------------------------------------------------------------------ page
export default function Trending() {
  const meta = useApi("/api/meta");
  const latest = meta.data?.dates?.max ?? null;
  const [preset, setPreset] = useState(14);
  const [custom, setCustom] = useState({ from: "", to: "" });
  const [source, setSource] = useState("");
  const [highlight, setHighlight] = useState(null);
  const [hover, setHover] = useState(null);

  const range = useMemo(() => {
    if (preset === "custom") return { date_from: custom.from, date_to: custom.to };
    if (!latest) return null;
    return { date_from: addDays(latest, -(preset - 1)), date_to: latest };
  }, [preset, custom, latest]);
  const ready = !!range && (preset !== "custom" || (custom.from && custom.to && custom.from <= custom.to));
  const { data, error, loading } = useApi("/api/trends", { ...range, source }, { enabled: ready });

  const topics = data?.topics ?? [];
  const byGrowth = useMemo(() => [...topics].sort((a, b) => b.change - a.change || b.total - a.total), [topics]);
  const labels = useMemo(() => Object.fromEntries(topics.map((t) => [t.stable_key, t.label])), [topics]);
  const shown = useMemo(() => {
    const keys = new Set(topics.slice(0, MAX_LINES).map((t) => t.stable_key));
    byGrowth.slice(0, 3).forEach((t) => keys.add(t.stable_key));
    return topics.filter((t) => keys.has(t.stable_key));
  }, [topics, byGrowth]);

  // default emphasis: the fastest-growing topic; keep the reader's choice while it exists
  useEffect(() => {
    if (!topics.length) return;
    if (!highlight || !labels[highlight]) setHighlight(byGrowth[0].stable_key);
  }, [topics, byGrowth, labels, highlight]);
  const focus = hover ?? highlight;

  const rows = useMemo(() => (data?.days ?? []).map((day, i) => {
    const r = { day, total: data.total[i] };
    for (const t of shown) r[t.stable_key] = t.series[i];
    return r;
  }), [data, shown]);

  const cmp = data?.comparison;
  const cmpText = cmp?.previous
    ? `${fmtDay(cmp.recent[0])}–${fmtDay(cmp.recent[1])} compared with ${fmtDay(cmp.previous[0])}–${fmtDay(cmp.previous[1])}`
    : "Choose a range of at least two days to compare periods.";
  const rising = byGrowth.filter((t) => t.change > 0);
  const totalArticles = data ? data.total.reduce((a, b) => a + b, 0) : 0;
  const lastIdx = rows.length - 1;

  return (
    <>
      <Topbar title="Trending Topics">
        <Segmented label="Date range" value={preset} onChange={setPreset} options={PRESETS} />
        {preset === "custom" && (
          <>
            <label><span className="visually-hidden">From</span>
              <input className="input" type="date" value={custom.from} max={custom.to || undefined}
                     onChange={(e) => setCustom({ ...custom, from: e.target.value })} />
            </label>
            <label><span className="visually-hidden">To</span>
              <input className="input" type="date" value={custom.to} min={custom.from || undefined}
                     onChange={(e) => setCustom({ ...custom, to: e.target.value })} />
            </label>
          </>
        )}
        <label>
          <span className="visually-hidden">Source</span>
          <select className="select pill-select" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">All sources</option>
            {(meta.data?.sources ?? []).map((s) => <option key={s} value={s}>{sourceName(s)}</option>)}
          </select>
        </label>
      </Topbar>

      {preset === "custom" && !ready && <Notice>Pick a start and an end date.</Notice>}
      {error && !data && <Notice error={error} />}
      {ready && !data && !error && <Notice>Loading trends…</Notice>}

      {data && (
        <div className="stack">
          <div className="kpis-2">
            <KpiCard featured icon={<IconArticles />} label="Total article volume" value={fmtNum(totalArticles)}
                     note={`${fmtDay(data.date_from)} – ${fmtDay(data.date_to)}${source ? ` · ${sourceName(source)}` : ""}`} loading={loading} />
            <KpiCard icon={<IconUp />} label="Largest increase" value={rising[0] ? growthText(rising[0]) : "—"}
                     note={rising[0]?.label ?? "no topic is growing"} loading={loading} />
          </div>

          <ChartCard
            title="Total article volume"
            subtitle={`All articles per day${source ? ` · ${sourceName(source)}` : ""}`}
            loading={loading}
            table={
              <div className="table-wrap"><table className="data">
                <thead><tr><th>Day</th><th className="num">Articles</th></tr></thead>
                <tbody>{rows.map((r) => <tr key={r.day}><td>{fmtDay(r.day)}</td><td className="num">{r.total}</td></tr>)}</tbody>
              </table></div>
            }
          >
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={rows} margin={{ top: 16, right: 24, bottom: 0, left: -8 }}>
                <CartesianGrid vertical={false} stroke={C.sand} strokeWidth={1} />
                <XAxis dataKey="day" tickFormatter={fmtDay} {...axisProps} minTickGap={24} />
                <YAxis allowDecimals={false} {...axisProps} width={40} />
                <Tooltip content={<VolumeTip />} cursor={{ stroke: C.forest, strokeWidth: 1 }} isAnimationActive={false} />
                <Area type="linear" dataKey="total" stroke={C.sage} strokeWidth={2} fill={C.sage} fillOpacity={0.12}
                      activeDot={{ r: 5, fill: C.forest, stroke: C.white, strokeWidth: 2 }} isAnimationActive={false}
                      label={({ index, x, y, value }) => index === lastIdx ? (
                        <text key="end" x={x} y={y - 10} textAnchor="end" fontSize={12} fontWeight={600} fill={C.forest}>{value}</text>) : null} />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard
            title="Topic frequency over time"
            subtitle="Articles per topic per day · select a topic below to highlight it"
            loading={loading}
            table={
              <div className="table-wrap"><table className="data">
                <thead><tr><th>Topic</th>{rows.map((r) => <th key={r.day} className="num">{fmtDay(r.day)}</th>)}<th className="num">Total</th></tr></thead>
                <tbody>{topics.map((t) => (
                  <tr key={t.stable_key}><td>{t.label}</td>{t.series.map((v, i) => <td key={i} className="num">{v}</td>)}<td className="num">{t.total}</td></tr>
                ))}</tbody>
              </table></div>
            }
            legend={
              <div className="chart-legend" aria-label="Choose the highlighted topic">
                {shown.map((t) => (
                  <button key={t.stable_key} type="button" className="chip" aria-pressed={t.stable_key === highlight}
                          style={t.stable_key === highlight ? { borderColor: C.forest, background: "var(--cream)" } : undefined}
                          onClick={() => setHighlight(t.stable_key)}
                          onMouseEnter={() => setHover(t.stable_key)} onMouseLeave={() => setHover(null)}
                          onFocus={() => setHover(t.stable_key)} onBlur={() => setHover(null)}>
                    <span className="legend-key"><span className={`line ${t.stable_key === focus ? "" : "context"}`} /></span>
                    {t.label}
                  </button>
                ))}
                {topics.length > shown.length && <span className="muted-note">+{topics.length - shown.length} smaller topics (see Table)</span>}
              </div>
            }
          >
            {topics.length === 0 ? <Notice>No topic articles in this range.</Notice> : (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={rows} margin={{ top: 16, right: 24, bottom: 0, left: -8 }}>
                  <CartesianGrid vertical={false} stroke={C.sand} strokeWidth={1} />
                  <XAxis dataKey="day" tickFormatter={fmtDay} {...axisProps} minTickGap={24} />
                  <YAxis allowDecimals={false} {...axisProps} width={40} />
                  <Tooltip content={<TopicsTip labels={labels} highlight={focus} />} cursor={{ stroke: C.forest, strokeWidth: 1 }} isAnimationActive={false} />
                  {shown.filter((t) => t.stable_key !== focus).map((t) => (
                    <Line key={t.stable_key} dataKey={t.stable_key} type="linear" stroke={C.pale} strokeWidth={1.5}
                          dot={false} activeDot={false} isAnimationActive={false} />
                  ))}
                  {shown.filter((t) => t.stable_key === focus).map((t) => (
                    <Line key={t.stable_key} dataKey={t.stable_key} type="linear" stroke={C.forest} strokeWidth={2.5}
                          dot={false} activeDot={{ r: 5, fill: C.forest, stroke: C.white, strokeWidth: 2 }} isAnimationActive={false}
                          label={({ index, x, y, value }) => index === lastIdx ? (
                            <text key="end" x={x} y={y - 10} textAnchor="end" fontSize={12} fontWeight={600} fill={C.forest}>{value}</text>) : null} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            )}
          </ChartCard>

          <div className="two">
            <ChartCard
              title="Most covered topics"
              subtitle="Total articles per topic in the range"
              loading={loading}
              table={
                <div className="table-wrap"><table className="data">
                  <thead><tr><th>Topic</th><th className="num">Articles</th></tr></thead>
                  <tbody>{topics.map((t) => <tr key={t.stable_key}><td>{t.label}</td><td className="num">{t.total}</td></tr>)}</tbody>
                </table></div>
              }
            >
              <BarList rows={topics.slice(0, 8).map((t) => ({
                key: t.stable_key, label: t.label, value: t.total, tone: "sage", onClick: () => setHighlight(t.stable_key),
                title: "Highlight this topic in the chart above",
              }))} />
            </ChartCard>

            <ChartCard
              title="Largest increase in coverage"
              subtitle={`Growth: ${cmpText}`}
              loading={loading}
              table={
                <div className="table-wrap"><table className="data">
                  <thead><tr><th>Topic</th><th className="num">Earlier</th><th className="num">Later</th><th className="num">Change</th><th className="num">Growth</th></tr></thead>
                  <tbody>{byGrowth.map((t) => (
                    <tr key={t.stable_key}><td>{t.label}</td><td className="num">{t.previous}</td><td className="num">{t.recent}</td>
                      <td className="num">{t.change > 0 ? `+${t.change}` : t.change}</td>
                      <td className="num">{t.is_new ? "new" : t.growth_pct == null ? "—" : `${Math.round(t.growth_pct)}%`}</td></tr>
                  ))}</tbody>
                </table></div>
              }
            >
              <BarList
                rows={rising.slice(0, 8).map((t) => ({
                  key: t.stable_key, label: t.label, value: t.change, onClick: () => setHighlight(t.stable_key),
                  title: `${t.previous} → ${t.recent} articles`,
                }))}
                format={(v, r) => growthText(rising.find((t) => t.stable_key === r.key))}
                empty="No topic gained coverage between the two halves of this range."
              />
              {cmp?.previous && rising.some((t) => t.is_new) && (
                <p className="muted-note" style={{ marginBottom: 0 }}>“New” means the topic had no articles in the earlier period.</p>
              )}
            </ChartCard>
          </div>

          {data.history_used && (
            <p className="muted-note">Days before {fmtDay(data.coverage_start)} come from saved daily topic counts, kept after older articles were removed by the storage limit.</p>
          )}
          {source && data.coverage_start && data.date_from < data.coverage_start && (
            <p className="muted-note">With a source selected, only articles still stored (from {fmtDay(data.coverage_start)}) are counted.</p>
          )}
        </div>
      )}
    </>
  );
}
