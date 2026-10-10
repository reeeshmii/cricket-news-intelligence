import { createContext, createElement, useContext, useEffect, useRef, useState } from "react";

export async function getJSON(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(`${res.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return res.json();
}

// ------------------------------------------------------------------ live status
// Polls the cheap /api/status endpoint. Its `version` changes whenever new articles,
// assignments or a new topic model arrive; every page refetches when it changes.
const StatusContext = createContext({ status: null, version: null, error: null, lastChecked: null, tick: 0, refresh: () => {} });
const POLL_MS = 60_000;

export function StatusProvider({ children }) {
  const [state, setState] = useState({ status: null, version: null, error: null, lastChecked: null, tick: 0 });
  const checkRef = useRef(() => {});
  useEffect(() => {
    let alive = true;
    const check = (force = false) =>
      getJSON("/api/status")
        .then((s) => alive && setState((p) => ({ status: s, version: s.version, error: null, lastChecked: new Date(),
                                                  tick: force ? p.tick + 1 : p.tick })))
        .catch((e) => alive && setState((p) => ({ ...p, error: e, lastChecked: new Date() })));
    checkRef.current = check;
    check();
    const id = setInterval(check, POLL_MS);
    const onFocus = () => check();
    window.addEventListener("focus", onFocus);
    return () => { alive = false; clearInterval(id); window.removeEventListener("focus", onFocus); };
  }, []);
  // refresh(): check for new data now and refetch every visible panel (the header's refresh button)
  const value = { ...state, refresh: () => checkRef.current(true) };
  return createElement(StatusContext.Provider, { value }, children);
}

export const useStatus = () => useContext(StatusContext);

// ------------------------------------------------------------------ data hook
// Keeps the previous data while refetching (the UI fades it instead of flashing a skeleton).
export function useApi(path, params = {}, { enabled = true } = {}) {
  const { version, tick } = useStatus();
  const key = JSON.stringify([path, params]);
  const [state, setState] = useState({ data: null, error: null, loading: enabled });
  const seq = useRef(0);
  useEffect(() => {
    if (!enabled || version === null) return;
    const mine = ++seq.current;
    setState((s) => ({ ...s, loading: true }));
    getJSON(path, params)
      .then((data) => mine === seq.current && setState({ data, error: null, loading: false }))
      .catch((error) => mine === seq.current && setState((s) => ({ ...s, error, loading: false })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, version, tick, enabled]);
  return state;
}
