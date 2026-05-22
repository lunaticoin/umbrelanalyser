// Shared helpers
export async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || msg; } catch {}
    throw new Error(`${r.status} ${msg}`);
  }
  return r.json();
}

const UNITS = ["B", "KB", "MB", "GB", "TB", "PB"];
export function fmtBytes(n, digits = 1) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  if (n < 1024) return `${n} B`;
  let v = n, u = 0;
  while (v >= 1024 && u < UNITS.length - 1) { v /= 1024; u++; }
  return `${v.toFixed(digits)} ${UNITS[u]}`;
}

export function fmtRate(bytesPerSec) {
  if (bytesPerSec === null || bytesPerSec === undefined) return "—";
  return `${fmtBytes(bytesPerSec)}/s`;
}

export function fmtPct(n) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return `${n.toFixed(1)} %`;
}

export function fmtTs(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

export function fmtAgo(ts) {
  if (!ts) return "—";
  const s = Math.max(0, Math.floor(Date.now() / 1000) - ts);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function qs(name) {
  return new URL(window.location.href).searchParams.get(name);
}

// Compute rate (bytes/s) from cumulative samples
export function toRateSeries(samples, field) {
  const out = [];
  for (let i = 1; i < samples.length; i++) {
    const a = samples[i - 1];
    const b = samples[i];
    const dt = b.ts - a.ts;
    if (dt <= 0) continue;
    const av = a[field];
    const bv = b[field];
    if (av === null || bv === null) continue;
    const delta = bv - av;
    // counter reset (container restart) → skip this point
    const rate = delta < 0 ? null : delta / dt;
    if (rate === null) continue;
    out.push({ x: b.ts * 1000, y: rate });
  }
  return out;
}

export function toValueSeries(samples, field, scale = 1) {
  return samples
    .filter((s) => s[field] !== null && s[field] !== undefined)
    .map((s) => ({ x: s.ts * 1000, y: s[field] * scale }));
}

export function setupNav(activeHref) {
  document.querySelectorAll("header nav a").forEach((a) => {
    if (a.getAttribute("href") === activeHref) a.classList.add("active");
  });
}
