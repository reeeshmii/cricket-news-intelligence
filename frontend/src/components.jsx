import { useState } from "react";
import { Link } from "react-router-dom";
import { fmtNum } from "./format.js";
import { IconChevronLeft, IconChevronRight } from "./icons.jsx";

/** Page header: serif title + one-line description; page controls on the right. */
export function Topbar({ title, subtitle, children }) {
  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="sub">{subtitle}</p>}
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
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

/** A chart card with its accessible "Table" twin one click away. */
export function ChartCard({ title, subtitle, table, children, loading, className = "", extra }) {
  const [view, setView] = useState("chart");
  return (
    <Card title={title} subtitle={subtitle} loading={loading} className={className}
          actions={(table || extra) && (
            <>
              {extra}
              {table && <Segmented label={`${title}: view`} value={view} onChange={setView}
                                   options={[{ value: "chart", label: "Chart" }, { value: "table", label: "Table" }]} />}
            </>
          )}>
      {view === "chart" ? children : table}
    </Card>
  );
}

export function Segmented({ value, onChange, options, label }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}

/** KPI card: round icon, label, serif number, one short note line. */
export function KpiCard({ icon, label, value, note, loading }) {
  return (
    <section className={`card kpi ${loading ? "loading-fade" : ""}`}>
      <span className="kpi-icon">{icon}</span>
      <div>
        <div className="kpi-label">{label}</div>
        <div className="kpi-value">{value}</div>
        {note && <div className="kpi-note">{note}</div>}
      </div>
    </section>
  );
}

/** Horizontal bars: label | bar | value. rows: [{key, label, value, display?, tone?, onClick?, title?}] */
export function HBars({ rows, empty = "No data yet.", leftLabels = false }) {
  if (!rows.length) return <p className="muted-note">{empty}</p>;
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.value)));
  return (
    <div className={`hbars ${leftLabels ? "left-labels" : ""}`}>
      {rows.map((r) => {
        const Tag = r.onClick ? "button" : "div";
        return (
          <Tag key={r.key} type={r.onClick ? "button" : undefined} className={`hbar ${r.onClick ? "clickable" : ""}`}
               onClick={r.onClick} title={r.title ?? r.label}>
            <span className="hbar-label">{r.label}</span>
            <span className="hbar-track" aria-hidden="true">
              <span className={`hbar-fill ${r.tone ?? ""}`} style={{ display: "block", width: `${(Math.abs(r.value) / max) * 100}%` }} />
            </span>
            <span className="hbar-value">{r.display ?? fmtNum(r.value)}</span>
          </Tag>
        );
      })}
    </div>
  );
}

export function TopicChip({ id, label, status }) {
  if (!id && status && status !== "clustered") {
    return <span className="chip sand" title="Collected recently; analysis and topic assignment are still running">Being analysed</span>;
  }
  if (!id) {
    return <span className="chip sand" title="Not part of any topic yet (a one-off story, or waiting for the next re-fit)">No topic yet</span>;
  }
  return <Link className="chip" to={`/topics?topic=${id}`} title={`Open topic: ${label}`}>{label}</Link>;
}

/** Centered pager: ‹ 1 2 3 … 12 › */
export function Pager({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  const nums = new Set([1, pages]);
  for (let p = page - 2; p <= page + 2; p++) if (p >= 1 && p <= pages) nums.add(p);
  const list = [...nums].sort((a, b) => a - b);
  const items = [];
  list.forEach((p, i) => {
    if (i && p - list[i - 1] > 1) items.push(<span key={`gap${p}`} className="gap" aria-hidden="true">…</span>);
    items.push(<button key={p} type="button" aria-current={p === page ? "page" : undefined} onClick={() => onPage(p)}>{p}</button>);
  });
  return (
    <nav className="pager" aria-label="Pages">
      <button type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}><IconChevronLeft size={16} /></button>
      {items}
      <button type="button" aria-label="Next page" disabled={page >= pages} onClick={() => onPage(page + 1)}><IconChevronRight size={16} /></button>
    </nav>
  );
}

export function Notice({ error, children }) {
  return (
    <div className={`notice ${error ? "error" : ""}`} role={error ? "alert" : "status"}>
      {error ? `Could not load data. ${error.message.replace(/^\d+: /, "")}` : children}
    </div>
  );
}

export function SimpleTable({ head, rows }) {
  return (
    <div className="table-wrap">
      <table className="data">
        <thead><tr>{head.map((h, i) => <th key={h} className={i ? "num" : ""}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, j) => <tr key={j}>{r.map((c, i) => <td key={i} className={i ? "num" : ""}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
