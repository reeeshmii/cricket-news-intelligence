import { useState } from "react";
import { Link } from "react-router-dom";
import { fmtDate, fmtNum, sourceName, timeAgo } from "./format.js";

const longDate = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

/** Page header: title, today's date, and the page's filters on the right. */
export function Topbar({ title, children }) {
  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        <p className="date">{longDate.format(new Date())}</p>
      </div>
      {children && <div className="controls">{children}</div>}
    </header>
  );
}

export function Card({ title, subtitle, actions, children, className = "", loading = false }) {
  return (
    <section className={`card ${className} ${loading ? "loading-fade" : ""}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

/** A chart card with the accessible "Table" twin of the chart one click away. */
export function ChartCard({ title, subtitle, table, children, loading, legend, className = "", extra }) {
  const [view, setView] = useState("chart");
  return (
    <Card
      title={title}
      subtitle={subtitle}
      loading={loading}
      className={className}
      actions={
        (table || extra) && (
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
            {extra}
            {table && (
              <Segmented small label={`${title}: view`} value={view} onChange={setView}
                         options={[{ value: "chart", label: "Chart" }, { value: "table", label: "Table" }]} />
            )}
          </div>
        )
      }
    >
      {view === "chart" ? <>{children}{legend}</> : table}
    </Card>
  );
}

export function Segmented({ value, onChange, options, label, small = false }) {
  return (
    <div className={`segmented ${small ? "small" : ""}`} role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** KPI card: icon tile + optional pill, label, value, short note. `featured` = the dark lead card. */
export function KpiCard({ icon, label, value, note, pill, featured = false, hero = false, loading }) {
  return (
    <section className={`card kpi ${featured ? "featured" : ""} ${hero ? "hero" : ""} ${loading ? "loading-fade" : ""}`}>
      <div className="kpi-top">
        <span className="icon-tile">{icon}</span>
        {pill && <span className="pill">{pill}</span>}
      </div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-row">
        <span className="kpi-value">{value}</span>
        {note && <span className="kpi-note">{note}</span>}
      </div>
    </section>
  );
}

/**
 * Progress-style rows (one series): label + value, then a rounded bar on a cream track.
 * rows: [{key, label, value, tone?: "sage"|"muted", onClick?, title?}]
 */
export function BarList({ rows, format = fmtNum, empty = "No data yet." }) {
  if (!rows.length) return <p className="muted-note">{empty}</p>;
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.value)));
  return (
    <div className="bars">
      {rows.map((r) => {
        const Tag = r.onClick ? "button" : "div";
        return (
          <Tag key={r.key} type={r.onClick ? "button" : undefined} className={`bar-row ${r.onClick ? "clickable" : ""}`}
               onClick={r.onClick} title={r.title}>
            <div className="bar-head">
              <span className="bar-label">{r.label}</span>
              <span className="bar-value">{format(r.value, r)}</span>
            </div>
            <div className="bar-track" aria-hidden="true">
              <div className={`bar-fill ${r.tone ?? ""}`} style={{ width: `${(Math.abs(r.value) / max) * 100}%` }} />
            </div>
          </Tag>
        );
      })}
    </div>
  );
}

export function TopicChip({ id, label, status }) {
  if (!id && status && status !== "clustered") {
    return (
      <span className="chip none" title="Collected recently; entities, embeddings and topic assignment are still running">
        <span className="swatch" aria-hidden="true" />
        Being analysed
      </span>
    );
  }
  if (!id) {
    return (
      <span className="chip none" title="Not part of any topic yet (a one-off story, or waiting for the next re-fit)">
        <span className="swatch" aria-hidden="true" />
        No topic yet
      </span>
    );
  }
  return (
    <Link className="chip" to={`/topics?topic=${id}`} title={`Open topic: ${label}`}>
      <span className="swatch" aria-hidden="true" />
      {label}
    </Link>
  );
}

export function ArticleList({ items, showTopic = true, dateField = "published_at", columns = false }) {
  if (!items?.length) return <p className="muted-note">No articles match.</p>;
  return (
    <ul className={`articles ${columns ? "columns" : ""}`}>
      {items.map((a) => (
        <li key={a.id} className="article">
          <h4>
            <a href={a.url} target="_blank" rel="noopener noreferrer">{a.title}</a>
          </h4>
          <div className="meta">
            <span>{sourceName(a.source)}</span>
            <span className="sep" aria-hidden="true">·</span>
            <span title={`Published ${fmtDate(a.published_at ?? a.scraped_at)}, collected ${fmtDate(a.scraped_at)}`}>
              {dateField === "scraped_at" ? `collected ${timeAgo(a.scraped_at)}` : fmtDate(a.published_at ?? a.scraped_at)}
            </span>
            {showTopic && (
              <>
                <span className="sep" aria-hidden="true">·</span>
                <TopicChip id={a.topic_id} label={a.topic_label} status={a.status} />
              </>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Pagination({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total ? (page - 1) * pageSize + 1 : 0;
  const to = Math.min(total, page * pageSize);
  const nums = [];
  for (let p = Math.max(1, page - 2); p <= Math.min(pages, page + 2); p++) nums.push(p);
  return (
    <nav className="pagination" aria-label="Pages">
      <span>{fmtNum(from)}–{fmtNum(to)} of {fmtNum(total)}</span>
      <div className="pages">
        <button className="btn" type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        {nums.map((p) => (
          <button key={p} className="btn" type="button" aria-current={p === page ? "page" : undefined} onClick={() => onPage(p)}>{p}</button>
        ))}
        <button className="btn" type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </nav>
  );
}

export function Notice({ error, children }) {
  return (
    <div className={`notice ${error ? "error" : ""}`} role={error ? "alert" : "status"}>
      {error ? `Could not load data (${error.message}). Is the API running?` : children}
    </div>
  );
}
