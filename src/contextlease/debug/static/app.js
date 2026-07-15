"use strict";

const state = { arenaId: null, snapshot: null, events: [], history: [], source: null, live: true, refreshTimer: null };
const byId = (id) => document.getElementById(id);
const formatTokens = (value) => new Intl.NumberFormat().format(Number(value || 0));
const percent = (value) => `${Math.round(Number(value || 0) * 100)}%`;

async function api(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function setStatus(text, kind) {
  const element = byId("connection"); element.textContent = text; element.className = `status ${kind}`;
}

function cell(row, value) { const element = document.createElement("td"); element.textContent = String(value); row.appendChild(element); }
function colorFor(text) { let hash = 0; for (const char of text) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0; return `hsl(${Math.abs(hash) % 360} 72% 62%)`; }

function renderBudget(snapshot) {
  const total = Math.max(1, snapshot.context_limit_tokens);
  const framework = snapshot.framework_reserve_tokens;
  const output = snapshot.reserved_output_tokens;
  const used = snapshot.used_tokens;
  const slack = Math.max(0, total - used - framework - output);
  [["budget-used", used], ["budget-slack", slack], ["budget-framework", framework], ["budget-output", output]].forEach(([id, value]) => { byId(id).style.width = `${100 * value / total}%`; });
  byId("kpi-used").textContent = `${formatTokens(used)} / ${formatTokens(snapshot.input_budget_tokens)}`;
  byId("kpi-utilization").textContent = percent(snapshot.utilization);
  byId("kpi-reclaimable").textContent = formatTokens(snapshot.modules.reduce((sum, item) => sum + item.reclaimable_tokens, 0));
  byId("kpi-leases").textContent = formatTokens(snapshot.leases.length);
  byId("kpi-pressure").textContent = snapshot.pressure;
  byId("snapshot-meta").textContent = `${snapshot.model_profile_id} · ${snapshot.token_count_mode} · seq ${snapshot.snapshot_seq} · ${new Date(snapshot.captured_at).toLocaleTimeString()}`;
}

function renderModules(modules) {
  const map = byId("module-map"); map.replaceChildren();
  const rows = byId("module-rows"); rows.replaceChildren();
  if (!modules.length) { const row = document.createElement("tr"); const empty = document.createElement("td"); empty.colSpan = 8; empty.className = "empty"; empty.textContent = "No module data"; row.appendChild(empty); rows.appendChild(row); return; }
  modules.forEach((module) => {
    const tile = document.createElement("div"); tile.className = "module-tile"; tile.setAttribute("role", "listitem");
    tile.style.setProperty("--weight", String(Math.max(1, module.used_tokens)));
    tile.style.setProperty("--tile", colorFor(module.module_id));
    tile.style.setProperty("--reclaim", percent(module.reclaimable_tokens / Math.max(1, module.used_tokens)));
    const name = document.createElement("strong"); name.textContent = module.module_id;
    const usage = document.createElement("span"); usage.textContent = `${formatTokens(module.used_tokens)} tokens · ${module.pressure}`;
    tile.append(name, usage); map.appendChild(tile);
    const row = document.createElement("tr");
    cell(row, module.module_id); cell(row, `${module.floor_tokens} / ${module.target_tokens} / ${module.max_tokens}`);
    cell(row, formatTokens(module.demanded_tokens)); cell(row, formatTokens(module.used_tokens));
    cell(row, formatTokens(module.borrowed_capacity_tokens)); cell(row, `${module.fixed_tokens} / ${module.variable_tokens}`);
    cell(row, `${module.pinned_tokens} / ${module.elastic_tokens}`); cell(row, module.pressure); rows.appendChild(row);
  });
}

function renderLeases(leases) {
  const rows = byId("lease-rows"); rows.replaceChildren();
  if (!leases.length) { const row = document.createElement("tr"); const empty = document.createElement("td"); empty.colSpan = 7; empty.className = "empty"; empty.textContent = "No active leases"; row.appendChild(empty); rows.appendChild(row); return; }
  leases.forEach((lease) => { const row = document.createElement("tr"); [lease.donor_module_id, lease.borrower_module_id, formatTokens(lease.granted_tokens), formatTokens(lease.currently_used_tokens), formatTokens(lease.reclaimable_tokens), lease.release_pipeline.join(" → "), lease.state].forEach((value) => cell(row, value)); rows.appendChild(row); });
}

function renderEvents(events) {
  const list = byId("event-list"); list.replaceChildren(); byId("event-count").textContent = String(events.length);
  if (!events.length) { const item = document.createElement("li"); item.className = "empty"; item.textContent = "No events yet"; list.appendChild(item); return; }
  events.slice(-60).reverse().forEach((event) => { const item = document.createElement("li"); const time = document.createElement("time"); time.textContent = new Date(event.occurred_at).toLocaleTimeString(); const name = document.createElement("strong"); const module = event.payload && event.payload.module_id ? ` · ${event.payload.module_id}` : ""; name.textContent = `${event.event_type}${module}`; item.append(time, name); list.appendChild(item); });
}

function renderTrend(snapshot) {
  state.history.push({ used: snapshot.used_tokens, capacity: snapshot.input_budget_tokens }); if (state.history.length > 60) state.history.shift();
  const points = state.history.map((item, index) => { const x = state.history.length === 1 ? 0 : 720 * index / (state.history.length - 1); const y = 210 - 200 * item.used / Math.max(1, item.capacity); return `${x.toFixed(1)},${Math.max(10, y).toFixed(1)}`; });
  byId("trend-line").setAttribute("points", points.join(" "));
}

function render(snapshot, events) { state.snapshot = snapshot; renderBudget(snapshot); renderModules(snapshot.modules); renderLeases(snapshot.leases); renderEvents(events); renderTrend(snapshot); byId("main").setAttribute("aria-busy", "false"); }

async function refresh() {
  if (!state.arenaId || !state.live) return;
  try { const [snapshot, eventPage] = await Promise.all([api(`/api/v1/arenas/${encodeURIComponent(state.arenaId)}/snapshot`), api(`/api/v1/arenas/${encodeURIComponent(state.arenaId)}/events?limit=200`)]); state.events = eventPage.items || []; render(snapshot, state.events); setStatus("Live", "live"); }
  catch (error) { setStatus("Disconnected", "error"); console.error(error); }
}

function connectStream() {
  if (state.source) state.source.close(); if (!state.arenaId || !state.live) return;
  state.source = new EventSource(`/api/v1/arenas/${encodeURIComponent(state.arenaId)}/stream`);
  state.source.onopen = () => setStatus("Live", "live");
  state.source.onmessage = scheduleRefresh;
  ["layout.compiled", "lease.granted", "lease.reclaimed", "chunk.compressed", "context.rendered", "request.completed"].forEach((name) => state.source.addEventListener(name, scheduleRefresh));
  state.source.onerror = () => setStatus("Reconnecting", "pending");
}

function scheduleRefresh() { if (state.refreshTimer) return; state.refreshTimer = window.setTimeout(() => { state.refreshTimer = null; refresh(); }, 400); }

async function loadArenas() {
  const select = byId("arena-select");
  try { const page = await api("/api/v1/arenas"); select.replaceChildren(); if (!page.items.length) { const option = document.createElement("option"); option.textContent = "No arenas"; select.appendChild(option); byId("empty-state").hidden = false; byId("main").setAttribute("aria-busy", "false"); setStatus("Empty", "pending"); return; }
    page.items.forEach((arena) => { const option = document.createElement("option"); option.value = arena.arena_id; option.textContent = arena.arena_id; select.appendChild(option); }); state.arenaId = page.items[0].arena_id; await refresh(); connectStream(); }
  catch (error) { select.replaceChildren(); const option = document.createElement("option"); option.textContent = "Unavailable"; select.appendChild(option); setStatus("Error", "error"); console.error(error); }
}

byId("arena-select").addEventListener("change", (event) => { state.arenaId = event.target.value; state.history = []; refresh(); connectStream(); });
byId("live-toggle").addEventListener("click", (event) => { state.live = !state.live; event.currentTarget.setAttribute("aria-pressed", String(state.live)); event.currentTarget.textContent = state.live ? "● Live" : "Ⅱ Paused"; if (state.live) { refresh(); connectStream(); } else { if (state.source) state.source.close(); setStatus("Paused", "pending"); } });
loadArenas();
