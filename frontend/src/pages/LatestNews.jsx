import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../api.js";
import { Card, Notice, Pager, Topbar, TopicChip } from "../components.jsx";
import { addDays, fmtDate, fmtNum, isoDay, sourceName } from "../format.js";
import { IconCalendar, IconExternal, IconRefresh, IconSearch } from "../icons.jsx";

const SORTS = [
  { value: "newest", label: "Newest First" },
  { value: "oldest", label: "Oldest First" },
  { value: "source", label: "Source" },
  { value: "topic", label: "Topic" },
  { value: "title", label: "Headline A–Z" },
];
const RANGES = [
  { value: "", label: "Any time" },
  { value: "1", label: "Last 24 hours" },
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
];
const PAGE_SIZE = 10;
const DEFAULTS = { q: "", source: "", topic: "", range: "", sort: "newest", page: "1" };

/** Filters live in the URL, so a filtered view can be bookmarked or shared. */
function useUrlState() {
  const [params, setParams] = useSearchParams();
  const state = Object.fromEntries(Object.entries(DEFAULTS).map(([k, v]) => [k, params.get(k) ?? v]));
  const update = (patch) => {
    const next = { ...state, ...patch, ...("page" in patch ? {} : { page: "1" }) };
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
  const params = {
    q: f.q, source: f.source, topic: f.topic, sort: f.sort, page: f.page, page_size: PAGE_SIZE,
    date_from: f.range ? addDays(isoDay(new Date()), -Number(f.range)) : "",
  };
  const { data, error, loading } = useApi("/api/articles", params);
  const filtered = ["q", "source", "topic", "range"].some((k) => f[k]);

  return (
    <>
      <Topbar title="Latest News" subtitle="Browse, search and filter cricket news articles" />

      <Card className="filter-card">
        <div className="filter-row" role="search">
          <label className="with-icon grow">
            <IconSearch size={17} />
            <span className="visually-hidden">Search by title or keywords</span>
            <input className="input" type="search" value={query} placeholder="Search by title or keywords…"
                   onChange={(e) => setQuery(e.target.value)} />
          </label>
          <label className="with-icon" style={{ width: 190 }}>
            <IconCalendar size={17} />
            <span className="visually-hidden">Published</span>
            <select className="select" value={f.range} onChange={(e) => update({ range: e.target.value })}>
              {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </label>
          <button className="icon-btn" type="button" aria-label="Reset filters" title="Reset filters" disabled={!filtered && query === ""}
                  onClick={() => { setQuery(""); update({ q: "", source: "", topic: "", range: "" }); }}>
            <IconRefresh size={17} />
          </button>
        </div>
        <div className="filter-row">
          <label className="field">Source
            <select className="select" value={f.source} onChange={(e) => update({ source: e.target.value })}>
              <option value="">All Sources</option>
              {(meta.data?.sources ?? []).map((s) => <option key={s} value={s}>{sourceName(s)}</option>)}
            </select>
          </label>
          <label className="field">Topic
            <select className="select" value={f.topic} onChange={(e) => update({ topic: e.target.value })}>
              <option value="">All Topics</option>
              <option value="none">Not in a topic yet</option>
              {(meta.data?.topics ?? []).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          <label className="field">Sort by
            <select className="select" value={f.sort} onChange={(e) => update({ sort: e.target.value })}>
              {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </label>
        </div>
      </Card>

      {error && !data && <Notice error={error} />}
      {!data && !error && <Notice>Loading articles…</Notice>}
      {data && (
        <div className={loading ? "loading-fade" : ""}>
          {data.items.length === 0 && <Notice>No articles match these filters.</Notice>}
          <div className="news-list">
            {data.items.map((a) => (
              <article key={a.id} className="card news-item">
                <div style={{ minWidth: 0 }}>
                  <h3><a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a></h3>
                  {a.summary && <p className="summary">{a.summary}</p>}
                  <div className="meta">
                    <span className="src">{sourceName(a.source)}</span>
                    <TopicChip id={a.topic_id} label={a.topic_label} status={a.status} />
                    <span>{fmtDate(a.published_at ?? a.scraped_at)}</span>
                  </div>
                </div>
                <a className="icon-btn ext" href={a.url} target="_blank" rel="noopener noreferrer"
                   aria-label={`Open the original article on ${sourceName(a.source)}`} title="Open original article">
                  <IconExternal size={17} />
                </a>
              </article>
            ))}
          </div>
          <Pager page={Number(f.page)} pageSize={PAGE_SIZE} total={data.total}
                 onPage={(p) => { update({ page: String(p) }); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
          <p className="result-count">{fmtNum(data.total)} {filtered ? "matching" : ""} articles</p>
        </div>
      )}
    </>
  );
}
