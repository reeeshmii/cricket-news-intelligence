import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../api.js";
import { Card, Notice, Pagination, TopicChip, Topbar } from "../components.jsx";
import { fmtDate, fmtNum, sourceName } from "../format.js";

const SORTS = [
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
  { value: "source", label: "Source" },
  { value: "topic", label: "Topic" },
  { value: "title", label: "Headline A–Z" },
];
const DEFAULTS = { q: "", source: "", topic: "", date_from: "", date_to: "", sort: "newest", page: "1", page_size: "20" };

/** Filters live in the URL, so a filtered view can be bookmarked or shared. */
function useUrlState() {
  const [params, setParams] = useSearchParams();
  const state = Object.fromEntries(Object.entries(DEFAULTS).map(([k, v]) => [k, params.get(k) ?? v]));
  const update = (patch, { resetPage = true } = {}) => {
    const next = { ...state, ...patch, ...(resetPage && !("page" in patch) ? { page: "1" } : {}) };
    setParams(Object.fromEntries(Object.entries(next).filter(([k, v]) => v !== "" && v !== DEFAULTS[k])), { replace: true });
  };
  return [state, update];
}

export default function LatestNews() {
  const [f, update] = useUrlState();
  const [query, setQuery] = useState(f.q);
  useEffect(() => setQuery(f.q), [f.q]);
  useEffect(() => {                                    // search as you type, without a request per keystroke
    const id = setTimeout(() => query !== f.q && update({ q: query }), 350);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const meta = useApi("/api/meta");
  const { data, error, loading } = useApi("/api/articles", f);
  const filtered = ["q", "source", "topic", "date_from", "date_to"].some((k) => f[k]);
  const topicOptions = meta.data?.topics ?? [];

  return (
    <>
      <Topbar title="Latest News" />

      <Card className="toolbar-card">
      <div className="toolbar" role="search">
        <label className="field">
          Search headlines and keywords
          <input className="input search" type="search" value={query} placeholder="e.g. Iyer, auction, injury"
                 onChange={(e) => setQuery(e.target.value)} />
        </label>
        <label className="field">
          Source
          <select className="select" value={f.source} onChange={(e) => update({ source: e.target.value })}>
            <option value="">All sources</option>
            {(meta.data?.sources ?? []).map((s) => <option key={s} value={s}>{sourceName(s)}</option>)}
          </select>
        </label>
        <label className="field">
          Topic
          <select className="select" value={f.topic} onChange={(e) => update({ topic: e.target.value })} style={{ maxWidth: 260 }}>
            <option value="">All topics</option>
            <option value="none">Not in a topic yet</option>
            {topicOptions.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </label>
        <label className="field">
          Published from
          <input className="input" type="date" value={f.date_from} max={f.date_to || undefined}
                 onChange={(e) => update({ date_from: e.target.value })} />
        </label>
        <label className="field">
          to
          <input className="input" type="date" value={f.date_to} min={f.date_from || undefined}
                 onChange={(e) => update({ date_to: e.target.value })} />
        </label>
        <label className="field">
          Sort
          <select className="select" value={f.sort} onChange={(e) => update({ sort: e.target.value })}>
            {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
        {filtered && (
          <button className="btn" type="button" onClick={() => { setQuery(""); update({ q: "", source: "", topic: "", date_from: "", date_to: "" }); }}>
            Clear filters
          </button>
        )}
      </div>
      </Card>

      {error && !data && <Notice error={error} />}
      {data && (
        <Card
          loading={loading}
          title="Articles"
          subtitle={`${fmtNum(data.total)} ${filtered ? "matching" : "collected"} articles`}
          actions={
            <label className="field" style={{ gridAutoFlow: "column", alignItems: "center", gap: 8 }}>
              Per page
              <select className="select pill-select" value={f.page_size} onChange={(e) => update({ page_size: e.target.value })}>
                {[10, 20, 50].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          }
        >
          <div className="table-wrap">
            <table className="data">
              <caption className="visually-hidden">Articles</caption>
              <thead>
                <tr>
                  <th style={{ width: "52%" }}>Headline</th>
                  <th>Source</th>
                  <th>Published</th>
                  <th>Topic</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id}>
                    <td className="headline">
                      <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>{sourceName(a.source)}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{fmtDate(a.published_at ?? a.scraped_at)}</td>
                    <td style={{ maxWidth: 260 }}><TopicChip id={a.topic_id} label={a.topic_label} status={a.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.items.length && <p className="muted-note">No articles match these filters.</p>}
          </div>
          <Pagination page={Number(f.page)} pageSize={Number(f.page_size)} total={data.total}
                      onPage={(p) => { update({ page: String(p) }, { resetPage: false }); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </Card>
      )}
      {!data && !error && <Notice>Loading articles…</Notice>}
    </>
  );
}
