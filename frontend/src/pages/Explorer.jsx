import { useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api.js";
import { Card, ChartCard, Notice, Pager, Topbar } from "../components.jsx";
import { fmtDate, fmtNum, sourceName } from "../format.js";
import { IconChevronLeft, IconChevronRight, IconInfo } from "../icons.jsx";

const C = { forest: "#2E4634", sage: "#6E9667", pale: "#869B7F", sand: "#E6D9C7", white: "#FFFFFF" };
const PROJECTION_HELP =
  "Each dot is an article placed by a 2-D projection of its 384-d sentence embedding: similar articles sit close together. " +
  "Topics were found in the full embedding space (HDBSCAN); the projection is only for viewing them.";

// ------------------------------------------------------------------ 2-D map
// Emphasis encoding: the selected cluster in forest, other clusters in sage, articles in no
// cluster as hollow rings. Each dot has a 24px transparent hit area and a 2px white ring.
function MapDot({ cx, cy, payload, selected }) {
  if (cx == null || cy == null) return null;
  const inTopic = payload.cluster_id != null;
  const isSel = selected != null && payload.cluster_id === selected;
  return (
    <g style={{ cursor: inTopic ? "pointer" : "default" }}>
      <circle cx={cx} cy={cy} r={12} fill="transparent" />
      {inTopic
        ? <circle cx={cx} cy={cy} r={isSel ? 6.5 : 5} fill={isSel ? C.forest : C.sage} stroke={C.white} strokeWidth={2} />
        : <circle cx={cx} cy={cy} r={4.5} fill={C.white} stroke={C.sage} strokeWidth={1.5} />}
    </g>
  );
}

function MapTip({ active, payload, names }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tooltip">
      <div className="t-title serif">{p.title}</div>
      <div>{sourceName(p.source)}</div>
      <div style={{ marginTop: 4 }}><strong>{p.cluster_id != null ? names[p.cluster_id] : "Not in a topic yet"}</strong></div>
    </div>
  );
}

function ClusterMap({ selected, onSelect, names }) {
  const [method, setMethod] = useState("umap");
  const { data, error, loading } = useApi("/api/topics/map", { method });
  const points = useMemo(() => [...(data?.points ?? [])]
    .sort((a, b) => (a.cluster_id === selected) - (b.cluster_id === selected)), [data, selected]);

  const table = (
    <div className="table-wrap" style={{ maxHeight: 380, overflowY: "auto" }}>
      <table className="data">
        <thead><tr><th>Article</th><th>Cluster</th></tr></thead>
        <tbody>{(data?.points ?? []).map((p) => (
          <tr key={p.id}><td>{p.title}</td><td>{p.cluster_id != null ? names[p.cluster_id] : "Not in a topic yet"}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );

  return (
    <ChartCard title="Article Clusters (2D Projection)" loading={loading} table={table}
               extra={
                 <>
                   <label><span className="visually-hidden">Projection</span>
                     <select className="select compact" value={method} onChange={(e) => setMethod(e.target.value)}>
                       <option value="umap">UMAP</option><option value="pca">PCA</option>
                     </select>
                   </label>
                   <button type="button" className="icon-btn" style={{ width: 34, height: 34 }} aria-label={PROJECTION_HELP} title={PROJECTION_HELP}>
                     <IconInfo size={16} />
                   </button>
                 </>
               }>
      {error && !data && <Notice error={error} />}
      {!data && !error && <Notice>Computing the map (the first time takes up to half a minute)…</Notice>}
      {data && !data.points.length && <Notice>The map appears once at least five articles have embeddings.</Notice>}
      {data?.points.length > 0 && (
        <div className="map-layout">
          <div role="img" aria-label={`Scatter map of ${points.length} articles by cluster`}>
            <ResponsiveContainer width="100%" height={360}>
              <ScatterChart margin={{ top: 8, right: 8, bottom: 22, left: 4 }}>
                <XAxis type="number" dataKey="x" domain={[-0.04, 1.04]} tick={false} stroke={C.sand}
                       label={{ value: "Component 1", position: "insideBottom", offset: -12, fill: C.forest, fontSize: 12 }} />
                <YAxis type="number" dataKey="y" domain={[-0.04, 1.04]} tick={false} stroke={C.sand} width={28}
                       label={{ value: "Component 2", angle: -90, position: "insideLeft", offset: 12, fill: C.forest, fontSize: 12 }} />
                <Tooltip content={<MapTip names={names} />} cursor={false} isAnimationActive={false} />
                <Scatter data={points} isAnimationActive={false} shape={(props) => <MapDot {...props} selected={selected} />}
                         onClick={(p) => p?.payload?.cluster_id != null && onSelect(p.payload.cluster_id)} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <div className="map-legend" aria-label="Legend">
            <span className="legend-key"><span className="dot strong" />Selected cluster</span>
            <span className="legend-key"><span className="dot" />Other clusters</span>
            <span className="legend-key"><span className="dot hollow" />Not in a topic yet</span>
          </div>
        </div>
      )}
    </ChartCard>
  );
}

// ------------------------------------------------------------------ details + articles
function ClusterDetails({ topic, number, total, unassigned, loading }) {
  if (topic === "none") {
    return (
      <Card title="Cluster Details" loading={loading}>
        <span className="chip sand">Not in a topic yet</span>
        <p style={{ margin: "12px 0 0" }}>Articles: <strong>{fmtNum(unassigned)}</strong></p>
        <p className="muted-note" style={{ marginTop: 12 }}>
          One-off stories that are not similar enough to any cluster, and new articles waiting for the next automatic
          re-fit. When several of them are about the same story, the next re-fit turns them into a new cluster.
        </p>
      </Card>
    );
  }
  return (
    <Card title="Cluster Details" loading={loading}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
        <strong className="serif" style={{ fontSize: 17, fontWeight: 500 }}>Cluster {number}</strong>
        <span className="chip">{topic.label}</span>
      </div>
      <p style={{ margin: "10px 0 0" }}>Articles: <strong>{fmtNum(topic.articles)}</strong> ({Math.round((100 * topic.articles) / Math.max(1, total))}%)</p>
      <div className="detail-block">
        <div className="detail-label">Top Keywords</div>
        <div className="chips">{topic.terms.map((t) => <span key={t} className="chip outline">{t.replaceAll("_", " ")}</span>)}</div>
      </div>
      <div className="detail-block">
        <div className="detail-label">Representative Articles</div>
        <ul className="rep-list">
          {topic.headlines.map((h) => (
            <li key={h.id}><a href={h.url} target="_blank" rel="noopener noreferrer">{h.title}</a></li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

function ClusterArticles({ topic, title }) {
  const [page, setPage] = useState(1);
  const { data, loading } = useApi("/api/articles", { topic, sort: topic === "none" ? "newest" : "relevance", page, page_size: 8 });
  return (
    <Card title={title} subtitle={data ? `${fmtNum(data.total)} articles` : undefined} loading={loading}>
      {!data ? <p className="muted-note">Loading articles…</p> : (
        <>
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Title</th><th>Source</th><th>Published</th></tr></thead>
              <tbody>{data.items.map((a) => (
                <tr key={a.id}>
                  <td className="title"><a href={a.url} target="_blank" rel="noopener noreferrer" title={a.title}>{a.title}</a></td>
                  <td style={{ whiteSpace: "nowrap" }}>{sourceName(a.source)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{fmtDate(a.published_at ?? a.scraped_at)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <Pager page={page} pageSize={8} total={data.total} onPage={setPage} />
        </>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ page
export default function Explorer() {
  const [params, setParams] = useSearchParams();
  const { data, error, loading } = useApi("/api/topics");
  const track = useRef(null);
  const header = <Topbar title="Topic & Cluster Explorer" subtitle="Explore automatically discovered news topics and related articles" />;

  const names = useMemo(() => Object.fromEntries((data?.topics ?? []).map((t, i) => [t.id, `Cluster ${i + 1} · ${t.label}`])), [data]);
  if (error && !data) return <>{header}<Notice error={error} /></>;
  if (!data) return <>{header}<Notice>Loading topics…</Notice></>;
  if (!data.topics.length) return <>{header}<Notice>No topics yet. They are discovered automatically once enough articles have been analysed.</Notice></>;

  const byId = Object.fromEntries(data.topics.map((t, i) => [t.id, { ...t, number: i + 1 }]));
  const raw = params.get("topic");
  const selectedId = raw === "none" ? "none" : byId[Number(raw)] ? Number(raw) : data.topics[0].id;
  const selected = selectedId === "none" ? "none" : byId[selectedId];
  const select = (id) => setParams({ topic: String(id) }, { replace: true });
  const total = data.topics.reduce((a, t) => a + t.articles, 0) + data.unassigned;
  const scroll = (dir) => track.current?.scrollBy({ left: dir * 430, behavior: "smooth" });

  return (
    <>
      {header}
      <div className="explore-top">
        <ClusterMap selected={selectedId === "none" ? null : selectedId} onSelect={select} names={names} />
        <ClusterDetails topic={selected} number={selected?.number} total={total} unassigned={data.unassigned} loading={loading} />
      </div>

      <div className="carousel">
        <button type="button" className="round-btn" aria-label="Scroll clusters left" onClick={() => scroll(-1)}><IconChevronLeft size={18} /></button>
        <div className="carousel-track" ref={track} role="list" aria-label="Clusters">
          {data.topics.map((t, i) => (
            <button key={t.id} type="button" role="listitem" className="cluster-card" aria-pressed={selectedId === t.id} onClick={() => select(t.id)}>
              <span className="name">Cluster {i + 1}</span>
              <span className="chip" style={{ justifySelf: "start" }} title={t.label}>{t.label}</span>
              <span className="count">{fmtNum(t.articles)} articles</span>
            </button>
          ))}
          {data.unassigned > 0 && (
            <button type="button" role="listitem" className="cluster-card" aria-pressed={selectedId === "none"} onClick={() => select("none")}>
              <span className="name">Unclustered</span>
              <span className="chip sand" style={{ justifySelf: "start" }}>Not in a topic yet</span>
              <span className="count">{fmtNum(data.unassigned)} articles</span>
            </button>
          )}
        </div>
        <button type="button" className="round-btn" aria-label="Scroll clusters right" onClick={() => scroll(1)}><IconChevronRight size={18} /></button>
      </div>

      <ClusterArticles key={String(selectedId)} topic={String(selectedId)}
                       title={selectedId === "none" ? "Articles not in a topic yet" : `Articles in Cluster ${selected.number}`} />
    </>
  );
}
