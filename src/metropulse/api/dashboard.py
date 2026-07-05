"""The internal ops dashboard: a single self-contained HTML page.

Served at ``/admin/dashboard``. The page itself is public (it contains no
data); every data request it makes carries the admin key the operator enters,
which is validated server-side by the ``/api/v1/admin/stats`` endpoint.
"""

from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MetroPulse Ops</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; }
  body { font: 14px/1.5 system-ui, sans-serif; background: #0e1116; color: #e6e8eb;
         padding: 24px; }
  h1 { font-size: 18px; margin-bottom: 16px; }
  h1 span { color: #4c9aff; }
  .bar { display: flex; gap: 8px; margin-bottom: 20px; align-items: center; }
  input { background: #161b22; border: 1px solid #30363d; color: #e6e8eb;
          border-radius: 6px; padding: 8px 10px; width: 280px; }
  button { background: #1f6feb; color: #fff; border: 0; border-radius: 6px;
           padding: 8px 14px; cursor: pointer; }
  #status { margin-left: 8px; color: #8b949e; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 12px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 10px;
          padding: 14px 16px; }
  .card .label { color: #8b949e; font-size: 12px; text-transform: uppercase;
                 letter-spacing: .04em; }
  .card .value { font-size: 26px; font-weight: 600; margin-top: 4px; }
  .ok { color: #3fb950; } .warn { color: #d29922; } .bad { color: #f85149; }
</style>
</head>
<body>
<h1>Metro<span>Pulse</span> — operations</h1>
<div class="bar">
  <input id="key" type="password" placeholder="Admin API key" autocomplete="off">
  <button onclick="saveKey()">Connect</button>
  <span id="status">enter the admin key to begin</span>
</div>
<div class="grid" id="grid"></div>
<script>
"use strict";
const CARDS = [
  ["Feed", s => s.feed_status, s => s.feed_status === "ok" ? "ok"
      : (s.feed_status === "stale" ? "bad" : "warn")],
  ["GTFS latency", s => s.feed_age_seconds == null ? "–"
      : s.feed_age_seconds.toFixed(1) + " s",
   s => s.feed_age_seconds != null && s.feed_age_seconds < 30 ? "ok" : "warn"],
  ["Active trains", s => s.active_trains, () => ""],
  ["Users (15 min)", s => s.users_active_15m + " / " + s.users_total, () => ""],
  ["Redis", s => s.redis_ok ? "healthy" : "DOWN", s => s.redis_ok ? "ok" : "bad"],
  ["PostgreSQL", s => s.database_ok ? "healthy" : "DOWN",
   s => s.database_ok ? "ok" : "bad"],
  ["WS connections", s => s.ws_connections, () => ""],
  ["WS frames sent", s => Math.round(s.ws_messages_sent_total), () => ""],
  ["WS drops", s => Math.round(s.ws_connections_dropped_total),
   s => s.ws_connections_dropped_total > 0 ? "warn" : "ok"],
  ["Rate-limited (429)", s => Math.round(s.http_429_total),
   s => s.http_429_total > 0 ? "warn" : "ok"],
  ["Events published", s => Math.round(s.events_published_total), () => ""],
  ["Diff sequence", s => s.diff_sequence, () => ""],
];
let timer = null;
function saveKey() {
  localStorage.setItem("mp-admin-key", document.getElementById("key").value);
  if (timer) clearInterval(timer);
  refresh();
  timer = setInterval(refresh, 5000);
}
async function refresh() {
  const key = localStorage.getItem("mp-admin-key") || "";
  const status = document.getElementById("status");
  try {
    const response = await fetch("/api/v1/admin/stats", {
      headers: { "X-Admin-Key": key },
    });
    if (!response.ok) {
      status.textContent = response.status === 403
        ? "invalid admin key" : "error " + response.status;
      status.className = "bad";
      return;
    }
    render(await response.json());
    status.textContent = "updated " + new Date().toLocaleTimeString();
    status.className = "ok";
  } catch (err) {
    status.textContent = "unreachable: " + err;
    status.className = "bad";
  }
}
function render(stats) {
  const grid = document.getElementById("grid");
  grid.innerHTML = "";
  for (const [label, valueOf, classOf] of CARDS) {
    const card = document.createElement("div");
    card.className = "card";
    const value = document.createElement("div");
    value.className = "value " + classOf(stats);
    value.textContent = valueOf(stats);
    const caption = document.createElement("div");
    caption.className = "label";
    caption.textContent = label;
    card.append(caption, value);
    grid.append(card);
  }
}
if (localStorage.getItem("mp-admin-key")) saveKey();
</script>
</body>
</html>
"""
