import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi, useStatus } from "../api.js";
import { Card, ChartCard, HBars, KpiCard, Notice, SimpleTable, Topbar, TopicChip } from "../components.jsx";
import { fmtDate, fmtDay, fmtNum, fmtUpdated, fmtWeek, sourceName, timeAgo, toWeeks } from "../format.js";
import { IconArrowRight, IconCalendar, IconDatabase, IconDoc, IconRefresh, IconTopics, IconTrendUp, IconUp } from "../icons.jsx";

const C = { forest: "#2E4634", sage: "#6E9667", pale: "#869B7F", cream: "#BCA581", sand: "#E6D9C7", white: "#FFFFFF" };
// Colour follows the source, never its rank, so a period change never repaints a source.
// Slices are drawn in this fixed order so neighbours always differ enough (sage and pale sage
// are too alike to sit side by side, so the donut uses tan cream instead of pale sage).
const SOURCE_ORDER = ["hindustantimes", "wisden", "crictracker", "cricketaddictor"];
const SOURCE_COLOR = { hindustantimes: C.sage, wisden: C.forest, crictracker: C.cream, cricketaddictor: C.sand };
const byFixedOrder = (rows) => [...rows].sort((a, b) => SOURCE_ORDER.indexOf(a.source) - SOURCE_ORDER.indexOf(b.source));
const PERIODS = [
  { value: "1", label: "Last 24 hours" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "all", label: "All time" },
];
const pct = (part, whole) => (whole ? Math.round((100 * part) / whole) : 0);

function Change({ value, text }) {
  const down = value < 0;
  return (
    <>
      <span style={{ display: "inline-flex", transform: down ? "rotate(180deg)" : undefined }}><IconUp /></span>
      {`${down ? "" : "+"}${value}% ${text}`}
    </>
  );
}

function SourceDonut({ rows, total, loading }) {
  return (
    <Card title="Article Collection by Source" loading={loading}>
      {!rows.length ? <p className="muted-note">No articles collected in this period.</p> : (
        <div className="donut-layout">
          <div role="img" aria-label="Donut chart of articles by source; values listed beside it" style={{ width: 150, height: 150 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={byFixedOrder(rows)} dataKey="articles" nameKey="source" innerRadius={46} outerRadius={72} startAngle={90} endAngle={-270}
                     stroke={C.white} strokeWidth={2} isAnimationActive={false}>
                  {byFixedOrder(rows).map((r) => <Cell key={r.source} fill={SOURCE_COLOR[r.source] ?? C.sand} />)}
                </Pie>
                <Tooltip isAnimationActive={false} content={({ active, payload }) => active && payload?.length ? (
                  <div className="tooltip"><div className="t-row"><span className="k strong" />
                    <strong>{fmtNum(payload[0].value)}</strong><span>{sourceName(payload[0].name)}</span></div></div>) : null} />
                <text x="50%" y="48%" textAnchor="middle" fontFamily="Newsreader, Georgia, serif" fontSize={24} fontWeight={500} fill={C.forest}>{fmtNum(total)}</text>
                <text x="50%" y="60%" textAnchor="middle" fontSize={12} fill={C.forest}>Articles</text>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="legend-rows">
            {rows.map((r) => (
              <div className="legend-row" key={r.source}>
                <span className="sw" style={{ background: SOURCE_COLOR[r.source] ?? C.sand }} aria-hidden="true" />
                <span>
                  <span className="name">{sourceName(r.source)}</span>
                  <span className="val"><strong>{pct(r.articles, total)}%</strong> ({fmtNum(r.articles)})</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function TimeTip({ active, payload, label, weekly }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="t-title">{weekly ? fmtWeek(label) : fmtDay(label)}</div>
      <div className="t-row"><span className="k strong" /><strong>{fmtNum(payload[0].value)}</strong><span>articles</span></div>
    </div>
  );
}

export default function Overview() {
  const [period, setPeriod] = useState("7");
  const [granularity, setGranularity] = useState("daily");
  const navigate = useNavigate();
  const { status, refresh } = useStatus();
  const all = period === "all";
  const { data, error, loading } = useApi(all ? "/api/overview/all" : "/api/overview", all ? {} : { days: period });
  const periodLabel = PERIODS.find((p) => p.value === period).label;

  const header = (
    <Topbar title="Welcome to T20 News Intelligence" subtitle="Cricket news analytics using web crawling, NLP and dynamic clustering">
      <div className="updated" title="Time of the last successful crawl">
        <span className="dot" aria-hidden="true" />
        <span>Last updated</span>
        <strong>{fmtUpdated(status?.last_crawl)}</strong>
      </div>
      <button className="icon-btn" type="button" onClick={refresh} aria-label="Check for new data now" title="Check for new data now">
        <IconRefresh size={18} />
      </button>
      <label className="with-icon" style={{ width: 180 }}>
        <IconCalendar size={17} />
        <span className="visually-hidden">Period</span>
        <select className="select" value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </label>
    </Topbar>
  );

  if (error && !data) return <>{header}<Notice error={error} /></>;
  if (!data) return <>{header}<Notice>Loading…</Notice></>;

  const comparable = data.in_previous !== null && data.in_previous !== undefined;
  const startTotal = data.total - data.in_period;
  const sources = data.by_source.map((r) => sourceName(r.source));
  const periodTotal = data.by_source.reduce((a, r) => a + r.articles, 0);
  const weekly = granularity === "weekly";
  const series = weekly ? toWeeks(data.daily ?? [], ["articles"]) : (data.daily ?? []);
  const topicRows = [
    ...data.topics.filter((t) => t.articles > 0).map((t) => ({
      key: t.id, label: t.label, value: t.articles, display: `${pct(t.articles, data.in_period)}%`,
      title: `${t.label}: ${fmtNum(t.articles)} articles`, onClick: () => navigate(`/topics?topic=${t.id}`),
    })),
    ...(data.unassigned_in_period ? [{ key: "none", label: "Not in a topic yet", value: data.unassigned_in_period, tone: "sand",
                                       display: `${pct(data.unassigned_in_period, data.in_period)}%` }] : []),
  ];

  return (
    <>
      {header}
      <div className="kpis">
        <KpiCard icon={<IconDoc size={26} />} label="Total Articles" value={fmtNum(data.total)} loading={loading}
                 note={comparable && startTotal > 0 ? <Change value={pct(data.in_period, startTotal)} text="from previous period" /> : "T20 articles stored"} />
        <KpiCard icon={<IconTrendUp size={26} />} label="New Articles" value={fmtNum(data.in_period)} loading={loading}
                 note={comparable && data.in_previous > 0
                   ? <Change value={pct(data.in_period - data.in_previous, data.in_previous)} text="from previous period" />
                   : periodLabel.toLowerCase()} />
        <KpiCard icon={<IconTopics size={26} />} label="Topics Discovered" value={fmtNum(data.n_topics)} loading={loading}
                 note={data.model ? `Dynamic clustering · updated ${timeAgo(data.model.fitted_at)}` : "Dynamic clustering"} />
        <KpiCard icon={<IconDatabase size={26} />} label="Sources" value={fmtNum(data.n_sources)} loading={loading}
                 note={sources.length ? sources.join(" • ") : "—"} />
      </div>

      <div className="row3">
        <SourceDonut rows={data.by_source} total={periodTotal} loading={loading} />

        <ChartCard title="Topic Distribution" loading={loading}
                   table={<SimpleTable head={["Topic", "Articles", "Share"]}
                                       rows={topicRows.map((r) => [r.label, fmtNum(r.value), r.display])} />}>
          <HBars rows={topicRows} empty={data.n_topics ? "No topic articles in this period." : "Topics appear once enough articles are collected."} />
        </ChartCard>

        <ChartCard title="Articles Over Time" loading={loading} className="fill"
                   extra={
                     <label><span className="visually-hidden">Granularity</span>
                       <select className="select compact" value={granularity} onChange={(e) => setGranularity(e.target.value)}>
                         <option value="daily">Daily</option><option value="weekly">Weekly</option>
                       </select>
                     </label>
                   }
                   table={<SimpleTable head={[weekly ? "Week" : "Day", "Articles"]}
                                       rows={series.map((d) => [weekly ? fmtWeek(d.day) : fmtDay(d.day), fmtNum(d.articles)])} />}>
          {series.length === 0 ? <p className="muted-note">No articles collected in this period.</p> : (
            <div className="fill-chart">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 10, right: 12, bottom: 0, left: -18 }}>
                  <CartesianGrid vertical={false} stroke={C.sand} />
                  <XAxis dataKey="day" tickFormatter={weekly ? fmtWeek : fmtDay} stroke={C.sand} tickLine={false} minTickGap={18} />
                  <YAxis allowDecimals={false} stroke={C.sand} tickLine={false} axisLine={false} width={42} />
                  <Tooltip content={<TimeTip weekly={weekly} />} cursor={{ stroke: C.forest, strokeWidth: 1 }} isAnimationActive={false} />
                  <Area type="linear" dataKey="articles" stroke={C.forest} strokeWidth={2} fill={C.sage} fillOpacity={0.18}
                        dot={{ r: 4, fill: C.forest, stroke: C.white, strokeWidth: 2 }}
                        activeDot={{ r: 5.5, fill: C.forest, stroke: C.white, strokeWidth: 2 }} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>
      </div>

      <Card title="Recently Collected Articles" loading={loading}
            actions={<Link className="link" to="/news">View All <IconArrowRight size={16} /></Link>}>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Title</th><th>Source</th><th>Topic</th><th>Published</th></tr></thead>
            <tbody>
              {data.recent.slice(0, 6).map((a) => (
                <tr key={a.id}>
                  <td className="title"><a href={a.url} target="_blank" rel="noopener noreferrer" title={a.title}>{a.title}</a></td>
                  <td style={{ whiteSpace: "nowrap" }}>{sourceName(a.source)}</td>
                  <td style={{ maxWidth: 240 }}><TopicChip id={a.topic_id} label={a.topic_label} status={a.status} /></td>
                  <td style={{ whiteSpace: "nowrap" }}>{fmtDate(a.published_at ?? a.scraped_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
