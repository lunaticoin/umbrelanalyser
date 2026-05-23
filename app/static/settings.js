import { api, fmtBytes, fmtTs, setupNav, setupAnalysisToggle } from "/static/common.js";

setupNav("/settings.html");
setupAnalysisToggle();

const form = document.getElementById("form");
const msg = document.getElementById("msg");
const dbinfo = document.getElementById("dbinfo");

async function load() {
  const [s, h] = await Promise.all([api("/api/settings"), api("/api/health")]);
  form.poll_interval_seconds.value = s.poll_interval_seconds;
  form.size_poll_interval_seconds.value = s.size_poll_interval_seconds;
  form.retention_days.value = s.retention_days;
  dbinfo.innerHTML = `
    ${h.db.samples.toLocaleString()} samples · ${fmtBytes(h.db.db_bytes)} on disk<br>
    Oldest sample: ${fmtTs(h.db.oldest_ts)}<br>
    Newest sample: ${fmtTs(h.db.newest_ts)}
  `;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "Saving…";
  try {
    const payload = {
      poll_interval_seconds: parseInt(form.poll_interval_seconds.value, 10),
      size_poll_interval_seconds: parseInt(form.size_poll_interval_seconds.value, 10),
      retention_days: parseInt(form.retention_days.value, 10),
    };
    await api("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    msg.textContent = "Saved. Takes effect on next poll.";
    msg.className = "ok";
    await load();
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "err";
  }
});

load().catch((e) => { dbinfo.innerHTML = `<span class="err">${e.message}</span>`; });
