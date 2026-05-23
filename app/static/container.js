import {
  api, fmtBytes, fmtPct, fmtAgo, qs, setupNav, setupAnalysisToggle,
  toRateSeries, toValueSeries,
} from "/static/common.js";

setupNav("/");
setupAnalysisToggle();

const containerId = qs("id");
if (!containerId) { document.body.innerHTML = "<p>Missing ?id=</p>"; throw new Error("no id"); }

const titleEl = document.getElementById("title");
const statsEl = document.getElementById("stats");
const rangeBtns = document.querySelectorAll("#ranges button");
const dlCsv = document.getElementById("dl-csv");
const dlCsvSize = document.getElementById("dl-csv-size");
const dlJson = document.getElementById("dl-json");

let hours = 24;
let charts = {};

function chartOpts(yFormatter, yTitle) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: "nearest", intersect: false },
    scales: {
      x: { type: "time", time: { tooltipFormat: "PP HH:mm" }, ticks: { color: "#8a93a6", maxRotation: 0 }, grid: { color: "#2a3142" } },
      y: { ticks: { color: "#8a93a6", callback: yFormatter }, grid: { color: "#2a3142" }, title: { display: !!yTitle, text: yTitle, color: "#8a93a6" } },
    },
    plugins: {
      legend: { labels: { color: "#e6e8ec" } },
      tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${yFormatter(ctx.parsed.y)}` } },
    },
  };
}

function color(i) {
  return ["#f7931a", "#4aa8ff", "#3fb950", "#d29922", "#f85149", "#a371f7"][i % 6];
}

function makeOrReplace(id, datasets, yFormatter, yTitle) {
  const ctx = document.getElementById(id);
  if (charts[id]) { charts[id].destroy(); }
  charts[id] = new Chart(ctx, {
    type: "line",
    data: { datasets: datasets.map((d, i) => ({
      label: d.label, data: d.data, borderColor: d.color || color(i),
      backgroundColor: (d.color || color(i)) + "22",
      borderWidth: 1.5, pointRadius: 0, spanGaps: false, tension: 0.15, fill: false,
    })) },
    options: chartOpts(yFormatter, yTitle),
  });
}

async function load() {
  const [c, m] = await Promise.all([
    api(`/api/containers/${encodeURIComponent(containerId)}`),
    api(`/api/containers/${encodeURIComponent(containerId)}/metrics?hours=${hours}`),
  ]);
  titleEl.textContent = `${c.name} — ${c.image || ""}`;
  document.title = `${c.name} · Umbrel Analyser`;

  const l = c.latest || {};
  const s = c.latest_size || {};
  statsEl.innerHTML = `
    <div class="stat"><div class="k">CPU</div><div class="v">${fmtPct(l.cpu_percent)}</div></div>
    <div class="stat"><div class="k">RAM</div><div class="v">${l.mem_bytes != null ? fmtBytes(l.mem_bytes) : "—"}</div></div>
    <div class="stat"><div class="k">RAM %</div><div class="v">${fmtPct(l.mem_percent)}</div></div>
    <div class="stat"><div class="k">Data dir</div><div class="v">${s.data_dir_bytes != null ? fmtBytes(s.data_dir_bytes) : "—"}</div></div>
    <div class="stat"><div class="k">RW layer</div><div class="v">${s.rw_bytes != null ? fmtBytes(s.rw_bytes) : "—"}</div></div>
    <div class="stat"><div class="k">Last seen</div><div class="v">${fmtAgo(c.last_seen)}</div></div>
  `;

  const samples = m.samples;
  const sizes = m.size_samples;

  makeOrReplace("cpu", [
    { label: "CPU %", data: toValueSeries(samples, "cpu_percent") },
  ], (v) => `${v.toFixed(1)}%`, "CPU %");

  makeOrReplace("mem", [
    { label: "RAM bytes", data: toValueSeries(samples, "mem_bytes") },
    { label: "RAM limit", data: toValueSeries(samples, "mem_limit_bytes"), color: "#8a93a6" },
  ], (v) => fmtBytes(v, 0), "Memory");

  makeOrReplace("blk", [
    { label: "Disk read /s", data: toRateSeries(samples, "blk_read_bytes") },
    { label: "Disk write /s", data: toRateSeries(samples, "blk_write_bytes") },
  ], (v) => `${fmtBytes(v, 0)}/s`, "Disk I/O");

  makeOrReplace("net", [
    { label: "Net RX /s", data: toRateSeries(samples, "net_rx_bytes") },
    { label: "Net TX /s", data: toRateSeries(samples, "net_tx_bytes") },
  ], (v) => `${fmtBytes(v, 0)}/s`, "Network");

  makeOrReplace("size", [
    { label: "Data dir size", data: toValueSeries(sizes, "data_dir_bytes") },
    { label: "RW layer", data: toValueSeries(sizes, "rw_bytes"), color: "#8a93a6" },
  ], (v) => fmtBytes(v, 1), "Disk usage");

  const q = `hours=${hours}`;
  dlCsv.href = `/api/containers/${encodeURIComponent(containerId)}/export.csv?${q}&kind=samples`;
  dlCsvSize.href = `/api/containers/${encodeURIComponent(containerId)}/export.csv?${q}&kind=sizes`;
  dlJson.href = `/api/containers/${encodeURIComponent(containerId)}/export.json?${q}`;
}

rangeBtns.forEach((b) => b.addEventListener("click", () => {
  rangeBtns.forEach((x) => x.classList.remove("active"));
  b.classList.add("active");
  hours = parseInt(b.dataset.h, 10);
  load().catch((e) => alert(e.message));
}));

load().catch((e) => { titleEl.textContent = "Error"; statsEl.innerHTML = `<div class="err">${e.message}</div>`; });
setInterval(() => load().catch(() => {}), 30000);
