import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api.js";
import { ArticleList, BarList, Card, ChartCard, KpiCard, Notice, Topbar } from "../components.jsx";
import { fmtDateTime, fmtDay, fmtNum, sourceName, timeAgo } from "../format.js";
import { IconArticles, IconNew, IconRefresh, IconTopics } from "../icons.jsx";

const C = { forest: "#556B5A", sage: "#8FB08A", pale: "#C9D8C4", sand: "#E6D9C7", white: "#FFFFFF" };
const PERIODS = [
  { value: "1", label: "Last 24 hours" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "all", label: "All time" },
];
// Donut: the three largest sources keep their own shade; the rest share one "Other" slice.
const DONUT = [C.forest, C.sage, C.pale];
const OTHER = C.sand;

function SimpleTable({ head, rows }) {
  return (
    <div className="table-wrap">
      <table className="data">
        <thead><tr>{head.map((h, i) => <th key={h} className={i ? "num" : ""}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r) => <tr key={r[0]}>{r.map((c, i) => <td key={i} className={i ? "num" : ""}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function SourceDonut({ rows, total, periodLabel, loading }) {
  const slices = rows.slice(0, 3).map((r, i) => ({ name: sourceName(r.source), value: r.articles, color: DONUT[i] }));
  const rest = rows.slice(3).reduce((s, r) => s + r.articles, 0);
  if (rest) slices.push({ name: "Other sources", value: rest, color: OTHER });
  const colorOf = (i) => (i < 3 ? DONUT[i] : OTHER);
  return (
    <Card className="accent a-sources" title="Article distribution by source" loading={loading}
          actions={<span className="pill light">{periodLabel}</span>}>
      {!rows.length ? <p className="muted-note">No articles collected in this period.</p> : (
        <>
          <div className="donut-wrap" role="img" aria-label="Donut chart of articles by source; values listed below">
            <ResponsiveContainer width="100%" height={210}>
              <PieChart>
                <Pie data={slices} dataKey="value" nameKey="name" innerRadius={62} outerRadius={98} startAngle={90} endAngle={-270}
                     stroke={C.white} strokeWidth={2} isAnimationActive={false}>
                  {slices.map((s) => <Cell key={s.name} fill={s.color} />)}
                </Pie>
                <Tooltip isAnimationActive={false} content={({ active, payload }) => active && payload?.length ? (
                  <div className="tooltip"><div className="t-row"><span className="k strong" />
                    <strong>{fmtNum(payload[0].value)}</strong><span>{payload[0].name}</span></div></div>) : null} />
                <text x="50%" y="47%" textAnchor="middle" fontSize={26} fontWeight={700} fill={C.forest}>{fmtNum(total)}</text>
                <text x="50%" y="58%" textAnchor="middle" fontSize={12} fontWeight={500} fill={C.forest}>articles</text>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="legend-rows">
            {rows.map((r, i) => (
              <div className="legend-row" key={r.source}>
                <span className="sw" style={{ background: colorOf(i) }} aria-hidden="true" />
                <span className="name">{sourceName(r.source)}</span>
                <span className="num">{fmtNum(r.articles)}</span>
                <span className="share">{Math.round((100 * r.articles) / total)}%</span>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

function DailyTip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="t-title">{fmtDay(label)}</div>
      <div className="t-row"><span className="k strong" /><strong>{fmtNum(payload[0].value)}</strong><span>new articles</span></div>
    </div>
  );
}

export default function Overview() {
  const [period, setPeriod] = useState("7");
  const navigate = useNavigate();
  const all = period === "all";
  const { data, error, loading } = useApi(all ? "/api/overview/all" : "/api/overview", all ? {} : { days: period });
  const periodLabel = PERIODS.find((p) => p.value === period).label;

  const controls = (
    <label>
      <span className="visually-hidden">Period</span>
      <select className="select pill-select" value={period} onChange={(e) => setPeriod(e.target.value)}>
        {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
      </select>
    </label>
  );

  if (error && !data) return <><Topbar title="Overview">{controls}</Topbar><Notice error={error} /></>;
  if (!data) return <><Topbar title="Overview">{controls}</Topbar><Notice>Loading…</Notice></>;
  const s = data.status;
  const inPeriodTotal = data.by_source.reduce((a, r) => a + r.articles, 0);
  const daily = data.daily ?? [];            // older API versions have no per-day data
  const lastDay = daily.length - 1;

  return (
    <>
      <Topbar title="Overview">{controls}</Topbar>
      <div className="overview">
        <div className="kpis-2 a-kpis">
          <KpiCard featured hero icon={<IconArticles />} label="Total collected articles" value={fmtNum(data.total)}
                   note="T20 articles currently stored" loading={loading} />
          <KpiCard icon={<IconNew />} label="New articles" value={fmtNum(data.in_period)} pill={periodLabel}
                   note={all ? "collected so far" : `since ${fmtDateTime(new Date(Date.now() - Number(period) * 864e5))}`} loading={loading} />
          <KpiCard icon={<IconTopics />} label="Topics discovered" value={fmtNum(data.n_topics)}
                   note={data.model ? `${data.model.algorithm.toUpperCase()}, updated ${timeAgo(data.model.fitted_at)}` : "no topic model yet"}
                   loading={loading} />
          <KpiCard icon={<IconRefresh />} label="Last successful data refresh" value={timeAgo(s.last_crawl)}
                   note={s.processing > 0 ? `${fmtNum(s.processing)} new articles still being analysed` : `crawl ${fmtDateTime(s.last_crawl)}`}
                   loading={loading} />
        </div>

        <SourceDonut rows={data.by_source} total={inPeriodTotal} periodLabel={periodLabel} loading={loading} />

        <ChartCard
          className="a-daily fill"
          title="New articles"
          subtitle={`Articles collected per day · ${periodLabel.toLowerCase()}`}
          loading={loading}
          table={<SimpleTable head={["Day", "New articles"]} rows={daily.map((d) => [fmtDay(d.day), fmtNum(d.articles)])} />}
        >
          {daily.length === 0 ? <p className="muted-note">No articles collected in this period.</p> : (
            <div className="fill-chart"><ResponsiveContainer width="100%" height="100%">
              <BarChart data={daily} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                <CartesianGrid vertical={false} stroke={C.sand} />
                <XAxis dataKey="day" tickFormatter={fmtDay} stroke={C.sand} tickLine={false} minTickGap={16} />
                <YAxis allowDecimals={false} stroke={C.sand} tickLine={false} axisLine={false} width={44} />
                <Tooltip content={<DailyTip />} cursor={{ fill: C.white, fillOpacity: 0 }} isAnimationActive={false} />
                <Bar dataKey="articles" maxBarSize={22} radius={[6, 6, 0, 0]} isAnimationActive={false}>
                  {daily.map((d, i) => <Cell key={d.day} fill={i === lastDay ? C.forest : C.sage} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer></div>
          )}
        </ChartCard>

        <ChartCard
          className="a-topics"
          title="Topic distribution"
          subtitle="Articles per topic"
          loading={loading}
          table={<SimpleTable head={["Topic", "Articles"]}
                              rows={[...data.topics.map((t) => [t.label, fmtNum(t.articles)]), ["Not in a topic yet", fmtNum(data.unassigned_in_period)]]} />}
        >
          <BarList
            rows={[
              ...data.topics.filter((t) => t.articles > 0).map((t) => ({
                key: t.id, label: t.label, value: t.articles, onClick: () => navigate(`/topics?topic=${t.id}`), title: `Open "${t.label}"`,
              })),
              ...(data.unassigned_in_period ? [{ key: "none", label: "Not in a topic yet", value: data.unassigned_in_period, tone: "muted" }] : []),
            ]}
            empty={data.n_topics ? "No topic articles in this period." : "Topics appear once enough articles are collected."}
          />
        </ChartCard>

        <Card className="a-recent" title="Recently collected articles" subtitle="The newest articles found by the crawler" loading={loading}>
          <ArticleList items={data.recent} dateField="scraped_at" columns />
        </Card>
      </div>
    </>
  );
}
