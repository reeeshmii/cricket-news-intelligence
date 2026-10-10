import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api.js";
import { ArticleList, Card, ChartCard, Notice, Pagination, Topbar } from "../components.jsx";
import { fmtNum, sourceName } from "../format.js";

const COLORS = { forest: "#556B5A", sage: "#8FB08A", pale: "#C9D8C4", white: "#FFFFFF" };
const ENTITY_NAMES = { PERSON: "People", TEAM: "Teams", TOURNAMENT: "Tournaments", CRICKET_ORG: "Boards" };

// ------------------------------------------------------------------ embedding map
// Emphasis encoding: the selected topic in forest, other topics in sage, articles in no
// topic as hollow rings. Each dot has a 24px transparent hit area and a 2px surface ring.
function MapDot({ cx, cy, payload, selected }) {
  if (cx == null || cy == null) return null;
  const inTopic = payload.cluster_id != null;
  const isSel = selected != null && payload.cluster_id === selected;
  return (
    <g style={{ cursor: inTopic ? "pointer" : "default" }}>
      <circle cx={cx} cy={cy} r={12} fill="transparent" />
      {inTopic ? (
        <circle cx={cx} cy={cy} r={isSel ? 6.5 : 5} fill={isSel ? COLORS.forest : COLORS.sage}
                stroke={COLORS.white} strokeWidth={2} />
      ) : (
        <circle cx={cx} cy={cy} r={4.5} fill={COLORS.white} stroke={COLORS.sage} strokeWidth={1.5} />
      )}
    </g>
  );
}

function MapTooltip({ active, payload, topics }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tooltip">
      <div className="t-title">{p.title}</div>
      <div>{sourceName(p.source)}</div>
      <div style={{ marginTop: 4 }}>
        <strong>{p.cluster_id != null ? topics[p.cluster_id]?.label ?? "Topic" : "Not in a topic yet"}</strong>
      </div>
    </div>
  );
}

function EmbeddingMap({ selected, onSelect, topics }) {
  const { data, error, loading } = useApi("/api/topics/map");
  const points = useMemo(() => {
    if (!data?.points) return [];
    // draw the selected topic last so its dots sit on top
    return [...data.points].sort((a, b) => (a.cluster_id === selected) - (b.cluster_id === selected));
  }, [data, selected]);

  const table = (
    <div className="table-wrap" style={{ maxHeight: 420, overflowY: "auto" }}>
      <table className="data">
        <thead><tr><th>Headline</th><th>Topic</th></tr></thead>
        <tbody>
          {(data?.points ?? []).map((p) => (
            <tr key={p.id}>
              <td>{p.title}</td>
              <td>{p.cluster_id != null ? topics[p.cluster_id]?.label : "Not in a topic yet"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <ChartCard
      title="Map of all articles"
      subtitle="Each dot is an article; similar articles sit close together. Select a dot to open its topic."
      loading={loading}
      table={table}
      legend={
        <div className="chart-legend" aria-label="Legend">
          <span className="legend-key"><span className="dot strong" />Selected topic</span>
          <span className="legend-key"><span className="dot" />Other topics</span>
          <span className="legend-key"><span className="dot hollow" />Not in a topic yet</span>
        </div>
      }
    >
      {error && !data && <Notice error={error} />}
      {!data && !error && <Notice>Computing the map (the first time takes up to half a minute)…</Notice>}
      {data && !data.points.length && <Notice>The map appears once at least five articles have embeddings.</Notice>}
      {data?.points.length > 0 && (
        <div role="img" aria-label={`Scatter map of ${points.length} articles coloured by topic`}>
          <ResponsiveContainer width="100%" height={420}>
            <ScatterChart margin={{ top: 12, right: 12, bottom: 12, left: 12 }}>
              <XAxis type="number" dataKey="x" domain={[-0.03, 1.03]} hide />
              <YAxis type="number" dataKey="y" domain={[-0.03, 1.03]} hide />
              <Tooltip content={<MapTooltip topics={topics} />} cursor={false} isAnimationActive={false} />
              <Scatter
                data={points}
                isAnimationActive={false}
                shape={(props) => <MapDot {...props} selected={selected} />}
                onClick={(p) => p?.payload?.cluster_id != null && onSelect(p.payload.cluster_id)}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
    </ChartCard>
  );
}

// ------------------------------------------------------------------ topic details
function TopicArticles({ topic }) {
  const [page, setPage] = useState(1);
  const params = { topic: topic, sort: topic === "none" ? "newest" : "relevance", page, page_size: 8 };
  const { data, loading } = useApi("/api/articles", params);
  if (!data) return <p className="muted-note">Loading articles…</p>;
  return (
    <div className={loading ? "loading-fade" : ""}>
      <ArticleList items={data.items} showTopic={false} />
      {data.total > 8 && <Pagination page={page} pageSize={8} total={data.total} onPage={setPage} />}
    </div>
  );
}

function TopicDetail({ topic, unassigned }) {
  if (topic === "none") {
    return (
      <Card title="Not in a topic yet" subtitle={`${fmtNum(unassigned)} articles`}>
        <p className="muted-note" style={{ marginTop: 0 }}>
          One-off stories that are not similar enough to any topic, plus new articles that are waiting for the next
          automatic re-fit. When several of them are about the same thing, the next re-fit turns them into a new topic.
        </p>
        <TopicArticles key="none" topic="none" />
      </Card>
    );
  }
  const entities = Object.entries(topic.entities ?? {}).filter(([, names]) => names.length);
  return (
    <Card
      title={topic.label}
      subtitle={`${fmtNum(topic.articles)} articles`}
      actions={<Link className="chip" to={`/news?topic=${topic.id}`}>Open in Latest News</Link>}
    >
      <div className="stack" style={{ gap: 18 }}>
        <div>
          <div className="section-label">Top keywords</div>
          <div className="chips">
            {topic.terms.map((t) => <span key={t} className="chip">{t.replaceAll("_", " ")}</span>)}
          </div>
        </div>
        {entities.length > 0 && (
          <dl className="kv">
            {entities.map(([label, names]) => (
              <div key={label} style={{ display: "contents" }}>
                <dt>{ENTITY_NAMES[label] ?? label}</dt>
                <dd>{names.join(", ")}</dd>
              </div>
            ))}
          </dl>
        )}
        <div>
          <div className="section-label">Representative headlines</div>
          <ul className="articles">
            {topic.headlines.map((h) => (
              <li key={h.id} className="article">
                <h4><a href={h.url} target="_blank" rel="noopener noreferrer">{h.title}</a></h4>
                <div className="meta"><span>{sourceName(h.source)}</span><span className="sep">·</span><span>similarity {h.score?.toFixed(2)}</span></div>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="section-label">All articles in this topic</div>
          <TopicArticles key={topic.id} topic={topic.id} />
        </div>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ page
export default function Explorer() {
  const [params, setParams] = useSearchParams();
  const { data, error, loading } = useApi("/api/topics");
  const topicsById = useMemo(() => Object.fromEntries((data?.topics ?? []).map((t) => [t.id, t])), [data]);

  if (error && !data) return <><Topbar title="Topic & Cluster Explorer" /><Notice error={error} /></>;
  if (!data) return <><Topbar title="Topic & Cluster Explorer" /><Notice>Loading topics…</Notice></>;
  if (!data.topics.length) {
    return (
      <>
        <Topbar title="Topic & Cluster Explorer" />
        <Notice>No topics yet. They are discovered automatically once enough articles have been collected and analysed.</Notice>
      </>
    );
  }

  const raw = params.get("topic");
  const selectedId = raw === "none" ? "none" : topicsById[Number(raw)] ? Number(raw) : data.topics[0].id;
  const selected = selectedId === "none" ? "none" : topicsById[selectedId];
  const select = (id) => setParams({ topic: String(id) }, { replace: true });
  const max = Math.max(...data.topics.map((t) => t.articles), 1);

  return (
    <>
      <Topbar title="Topic & Cluster Explorer" />
      <div className="explorer">
        <Card title="Topics" subtitle={`${fmtNum(data.topics.length)} discovered automatically`} loading={loading}>
          <div className="topic-list" role="list" aria-label="Topics">
            {data.topics.map((t) => (
              <button key={t.id} type="button" role="listitem" className="topic-item" aria-pressed={selectedId === t.id} onClick={() => select(t.id)}>
                <span className="title">{t.label}</span>
                <span className="count">{fmtNum(t.articles)} articles · {t.terms.slice(0, 4).map((x) => x.replaceAll("_", " ")).join(", ")}</span>
                <span className="bar-track" aria-hidden="true">
                  <span className="bar-fill" style={{ display: "block", width: `${(t.articles / max) * 100}%` }} />
                </span>
              </button>
            ))}
            {data.unassigned > 0 && (
              <button type="button" role="listitem" className="topic-item" aria-pressed={selectedId === "none"} onClick={() => select("none")}>
                <span className="title">Not in a topic yet</span>
                <span className="count">{fmtNum(data.unassigned)} articles · one-off or waiting for the next re-fit</span>
              </button>
            )}
          </div>
        </Card>
        <div className="stack">
          <EmbeddingMap selected={selectedId === "none" ? null : selectedId} onSelect={select} topics={topicsById} />
          <TopicDetail topic={selected} unassigned={data.unassigned} />
        </div>
      </div>
    </>
  );
}
