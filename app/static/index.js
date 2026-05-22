import { api, fmtBytes, fmtPct, fmtAgo, setupNav } from "/static/common.js";

setupNav("/");

const tbody = document.querySelector("#containers tbody");
const healthEl = document.getElementById("health");
const refreshBtn = document.getElementById("refresh");

let prevRows = new Map(); // container_id → { ts, net_rx, net_tx, blk_r, blk_w }
let netRates = new Map(); // container_id → total bytes/s (rx+tx), used for sorting
let sort = { key: "name", dir: "asc" };

function sortKeyValue(c, key) {
  const l = c.latest || {};
  const s = c.latest_size || {};
  switch (key) {
    case "name":      return (c.name || "").toLowerCase();
    case "image":     return (c.image || "").toLowerCase();
    case "cpu":       return l.cpu_percent ?? -1;
    case "mem":       return l.mem_bytes ?? -1;
    case "size":      return s.data_dir_bytes ?? s.rw_bytes ?? -1;
    case "net":       return netRates.get(c.id) ?? -1;
    case "last_seen": return c.last_seen ?? 0;
  }
  return 0;
}

function sortContainers(arr) {
  const sign = sort.dir === "asc" ? 1 : -1;
  return [...arr].sort((a, b) => {
    const av = sortKeyValue(a, sort.key);
    const bv = sortKeyValue(b, sort.key);
    if (typeof av === "string" || typeof bv === "string") return sign * String(av).localeCompare(String(bv));
    return sign * (av - bv);
  });
}

function updateCarets() {
  document.querySelectorAll("#containers thead th").forEach((th) => {
    const active = th.dataset.key === sort.key;
    th.classList.toggle("sort-active", active);
    const caret = th.querySelector(".caret");
    if (caret) caret.textContent = active ? (sort.dir === "asc" ? "▲" : "▼") : "";
  });
}

function render(containers) {
  if (!containers.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted">No containers detected yet. Wait for the first poll.</td></tr>';
    return;
  }
  containers = sortContainers(containers);
  const html = containers.map((c) => {
    const l = c.latest || {};
    const s = c.latest_size || {};
    const prev = prevRows.get(c.id);
    let netRx = "—", netTx = "—";
    if (prev && l.ts && l.net_rx_bytes != null && prev.net_rx != null) {
      const dt = l.ts - prev.ts;
      if (dt > 0) {
        const rxr = Math.max(0, (l.net_rx_bytes - prev.net_rx) / dt);
        const txr = Math.max(0, (l.net_tx_bytes - prev.net_tx) / dt);
        netRx = `${fmtBytes(rxr)}/s`;
        netTx = `${fmtBytes(txr)}/s`;
        netRates.set(c.id, rxr + txr);
      }
    }
    if (l.ts) {
      prevRows.set(c.id, {
        ts: l.ts,
        net_rx: l.net_rx_bytes, net_tx: l.net_tx_bytes,
        blk_r: l.blk_read_bytes, blk_w: l.blk_write_bytes,
      });
    }
    const dataDir = s.data_dir_bytes != null ? fmtBytes(s.data_dir_bytes) : (s.rw_bytes != null ? `${fmtBytes(s.rw_bytes)} (rw)` : "—");
    return `
      <tr>
        <td><a href="/container.html?id=${encodeURIComponent(c.id)}">${escapeHtml(c.name)}</a></td>
        <td class="muted">${escapeHtml(c.image || "")}</td>
        <td class="num">${fmtPct(l.cpu_percent)}</td>
        <td class="num">${l.mem_bytes != null ? fmtBytes(l.mem_bytes) : "—"} <span class="muted">(${fmtPct(l.mem_percent)})</span></td>
        <td class="num">${dataDir}</td>
        <td class="num">${netRx} / ${netTx}</td>
        <td class="num muted">${fmtAgo(c.last_seen)}</td>
      </tr>`;
  }).join("");
  tbody.innerHTML = html;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

async function refresh() {
  try {
    const [h, list] = await Promise.all([api("/api/health"), api("/api/containers")]);
    const ageStats = h.last_stats_ok ? `${Math.max(0, Math.floor(Date.now() / 1000) - h.last_stats_ok)}s` : "never";
    const ageSize = h.last_size_ok ? `${Math.max(0, Math.floor(Date.now() / 1000) - h.last_size_ok)}s` : "never";
    const dotClass = h.last_error ? "warn" : "";
    healthEl.innerHTML = `<span class="status-dot ${dotClass}"></span>
      ${list.length} containers · stats ${ageStats} ago · sizes ${ageSize} ago · ${h.db.samples} samples · ${fmtBytes(h.db.db_bytes)} db`
      + (h.last_error ? ` · <span class="err">${escapeHtml(h.last_error)}</span>` : "");
    render(list);
  } catch (e) {
    healthEl.innerHTML = `<span class="status-dot err"></span> ${escapeHtml(e.message)}`;
  }
}

refreshBtn.addEventListener("click", refresh);

// Sortable headers: click same key flips direction; click new key starts desc
// for everything except the alphabetical ones (name/image), which start asc.
document.querySelectorAll("#containers thead th").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    if (!key) return;
    if (sort.key === key) {
      sort.dir = sort.dir === "asc" ? "desc" : "asc";
    } else {
      sort.key = key;
      sort.dir = key === "name" || key === "image" ? "asc" : "desc";
    }
    updateCarets();
    refresh();
  });
});

updateCarets();
refresh();
setInterval(refresh, 15000);

// ---- global export ----
const exportRangeBtns = document.querySelectorAll("#export-range button");
const exportCsvSamples = document.getElementById("export-csv-samples");
const exportCsvSizes   = document.getElementById("export-csv-sizes");
const exportJsonBtn    = document.getElementById("export-json");
let exportHours = 24;

function refreshExportLinks() {
  const q = `hours=${exportHours}`;
  exportCsvSamples.href = `/api/export/all.csv?${q}&kind=samples`;
  exportCsvSizes.href   = `/api/export/all.csv?${q}&kind=sizes`;
  exportJsonBtn.href    = `/api/export/all.json?${q}`;
}
exportRangeBtns.forEach((b) => b.addEventListener("click", () => {
  exportRangeBtns.forEach((x) => x.classList.remove("active"));
  b.classList.add("active");
  exportHours = parseInt(b.dataset.h, 10);
  refreshExportLinks();
}));
refreshExportLinks();
