// GeoGrid UI: business picker, scan launcher, rank heatmap, history, competitor "flip the map".
const $ = (s) => document.querySelector(s);
const KM_PER_MI = 1.609344;
const EARTH_KM = 6371.0088;
const NOT_FOUND = 21;

const S = {
  businesses: [], business: null, scans: [], scan: null,
  center: null, mode: "rank", competitor: null, pollTimer: null,
};

// ---------- map ----------
const map = L.map("map", { zoomControl: false }).setView([39.5, -98.35], 4);
L.control.zoom({ position: "bottomright" }).addTo(map);

// Keep the grid and popups clear of the floating cards.
function cardPadding() {
  const r = (sel) => { const el = $(sel); return el && !el.classList.contains("hidden") && el.offsetParent ? el.getBoundingClientRect() : null; };
  const scan = r("#scanCard"), comp = r("#compCard"), mapBox = $("#map").getBoundingClientRect();
  const top = scan ? scan.bottom - mapBox.top + 20 : 40;
  const right = comp && comp.width < mapBox.width / 2 ? mapBox.right - comp.left + 20 : 40;
  return { topLeft: [40, top], bottomRight: [right, 50] };
}
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);
const gridLayer = L.layerGroup().addTo(map);
let centerMarker = null, bizMarker = null;

// ---------- helpers ----------
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : res.statusText);
  return body;
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v, suffix = "") => (v === null || v === undefined ? "–" : `${v}${suffix}`);
const when = (iso) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const gridLabel = (s) => `${s.grid_size}×${s.grid_size} @ ${+s.spacing_km.toFixed(2)} km`;
function say(sel, kind, text) { const el = $(sel); el.className = `small ${kind}`; el.textContent = text; }

function offset(lat, lng, northKm, eastKm) {
  const dLat = (northKm / EARTH_KM) * 180 / Math.PI;
  const dLng = (eastKm / (EARTH_KM * Math.cos(lat * Math.PI / 180))) * 180 / Math.PI;
  return [lat + dLat, lng + dLng];
}
function gridPoints(lat, lng, size, spacingKm) {
  const half = Math.floor(size / 2), pts = [];
  for (let r = 0; r < size; r++) for (let c = 0; c < size; c++) pts.push(offset(lat, lng, (half - r) * spacingKm, (c - half) * spacingKm));
  return pts;
}
function spacingKm() {
  const v = parseFloat($("#spacing").value) || 1;
  return $("#unit").value === "mi" ? v * KM_PER_MI : v;
}
function rankClass(rank) {
  if (rank === null || rank === undefined) return "r4";
  return rank <= 3 ? "r1" : rank <= 10 ? "r2" : rank <= 20 ? "r3" : "r4";
}
function sameBiz(r, key) { return key.cid ? r.cid === key.cid : (r.name || "").toLowerCase() === key.name.toLowerCase(); }
function rankIn(results, key) {
  const i = (results || []).findIndex((r) => sameBiz(r, key));
  return i === -1 ? null : i + 1;
}
const myKey = () => ({ cid: S.scan.business_cid, name: S.scan.business_name });
const targetKey = () => S.competitor || myKey();

// ---------- businesses ----------
async function loadBusinesses(selectId) {
  S.businesses = await api("/api/businesses");
  const sel = $("#bizSelect");
  sel.innerHTML = `<option value="">— add a business below —</option>` +
    S.businesses.map((b) => `<option value="${b.id}">${esc(b.name)}</option>`).join("");
  const id = selectId ?? localGet("bizId");
  if (id && S.businesses.some((b) => b.id == id)) { sel.value = id; await selectBusiness(+id); }
  else if (S.businesses.length === 1) { sel.value = S.businesses[0].id; await selectBusiness(S.businesses[0].id); }
}

async function selectBusiness(id) {
  closeScan();
  S.business = S.businesses.find((b) => b.id === id) || null;
  $("#runBtn").disabled = !S.business;
  if (!S.business) { $("#bizInfo").textContent = ""; gridLayer.clearLayers(); return; }
  localSet("bizId", id);
  const b = S.business;
  $("#bizInfo").textContent = [b.category, b.address].filter(Boolean).join(" · ");
  if (bizMarker) bizMarker.remove();
  bizMarker = L.marker([b.lat, b.lng], { icon: L.divIcon({ className: "", html: '<div class="biz-pin">📍</div>', iconSize: [26, 26], iconAnchor: [13, 26] }) })
    .bindTooltip(esc(b.name)).addTo(map);
  bizMarker.setZIndexOffset(-1000);  // stay under the rank pins
  setCenter([b.lat, b.lng]);
  await loadHistory();
  if (S.scans.length) await openScan(S.scans[0].id);
  else { drawPreview(); fitGrid(); }
}

$("#bizSelect").addEventListener("change", (e) => selectBusiness(+e.target.value || null));

$("#bizForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#bizQuery").value.trim();
  if (!q) return;
  const btn = e.submitter; btn.disabled = true;
  say("#bizMsg", "muted", "Looking it up on Google Maps…");
  try {
    const b = await api("/api/businesses", { method: "POST", body: JSON.stringify({ query: q }) });
    say("#bizMsg", "ok", `Added: ${b.name}`);
    $("#bizQuery").value = "";
    await loadBusinesses(b.id);
  } catch (err) {
    say("#bizMsg", "err", err.message);
  } finally { btn.disabled = false; }
});

// ---------- grid preview & center ----------
function setCenter(latlng) {
  S.center = latlng;
  if (!centerMarker) {
    centerMarker = L.marker(latlng, { draggable: true, icon: L.divIcon({ className: "", html: '<div class="center-pin"></div>', iconSize: [18, 18] }), zIndexOffset: 2000 })
      .bindTooltip("Grid center: drag to move").addTo(map);
    centerMarker.on("dragend", () => { S.center = [centerMarker.getLatLng().lat, centerMarker.getLatLng().lng]; showPreview(); });
  } else centerMarker.setLatLng(latlng);
}
$("#previewGrid").addEventListener("click", (e) => { e.preventDefault(); if (S.business) { showPreview(); fitGrid(); } });
$("#resetCenter").addEventListener("click", (e) => { e.preventDefault(); if (S.business) { setCenter([S.business.lat, S.business.lng]); showPreview(); } });

function updateHint() {
  const n = +$("#gridSize").value, km = spacingKm(), span = (n - 1) * km;
  const kws = keywords().length || 1;
  const mins = Math.ceil((n * n * kws * 7) / 2 / 60);
  $("#gridHint").textContent = `${n * n} points × ${kws} keyword${kws > 1 ? "s" : ""} · covers ${span.toFixed(1)} × ${span.toFixed(1)} km · ~${mins} min`;
}
function drawPreview() {
  updateHint();
  if (!S.center || S.scan) return;
  if (centerMarker && !map.hasLayer(centerMarker)) centerMarker.addTo(map);
  gridLayer.clearLayers();
  for (const p of gridPoints(S.center[0], S.center[1], +$("#gridSize").value, spacingKm()))
    L.marker(p, { icon: L.divIcon({ className: "", html: '<div class="pin preview"></div>', iconSize: [12, 12] }), interactive: false }).addTo(gridLayer);
}
function showPreview() {  // leave the scan view and show the grid that will be scanned
  if (S.scan && S.scan.status !== "running") closeScan();
  drawPreview();
}
function fitGrid() {
  if (!S.center) return;
  const [n, km, c] = S.scan
    ? [S.scan.grid_size, S.scan.spacing_km, [S.scan.center_lat, S.scan.center_lng]]
    : [+$("#gridSize").value, spacingKm(), S.center];
  const h = (Math.floor(n / 2) + 0.7) * km;
  const pad = cardPadding();
  map.fitBounds([offset(c[0], c[1], -h, -h), offset(c[0], c[1], h, h)], { paddingTopLeft: pad.topLeft, paddingBottomRight: pad.bottomRight });
}
["#gridSize", "#spacing", "#unit"].forEach((s) => $(s).addEventListener("input", () => { showPreview(); fitGrid(); }));
$("#keywords").addEventListener("input", updateHint);

// ---------- run ----------
function keywords() { return $("#keywords").value.split("\n").map((k) => k.trim()).filter(Boolean); }

$("#runBtn").addEventListener("click", async () => {
  const kws = keywords();
  if (!S.business) return;
  if (!kws.length) { say("#runMsg", "err", "Enter at least one keyword."); return; }
  $("#runBtn").disabled = true; $("#runMsg").textContent = "";
  try {
    const { scan_ids } = await api("/api/scans", { method: "POST", body: JSON.stringify({
      business_id: S.business.id, keywords: kws, grid_size: +$("#gridSize").value,
      spacing_km: +spacingKm().toFixed(4), center_lat: S.center[0], center_lng: S.center[1],
    }) });
    say("#runMsg", "ok", `Started ${scan_ids.length} scan${scan_ids.length > 1 ? "s" : ""}.`);
    await loadHistory();
    await openScan(scan_ids[0]);
  } catch (err) {
    say("#runMsg", "err", err.message);
  } finally { $("#runBtn").disabled = false; }
});

// ---------- history ----------
async function loadHistory() {
  if (!S.business) return;
  S.scans = await api(`/api/scans?business_id=${S.business.id}`);
  const ul = $("#history");
  if (!S.scans.length) { ul.innerHTML = '<li class="muted small">No scans yet.</li>'; return; }
  ul.innerHTML = S.scans.map((s) => {
    const m = s.metrics || {};
    const badge = s.status === "done" ? `SoLV ${fmt(m.solv, "%")}` : s.status === "running" ? `${s.progress}/${s.total}` : "failed";
    return `<li class="item ${S.scan && S.scan.id === s.id ? "active" : ""}" data-id="${s.id}">
      <span class="kw">${esc(s.keyword)}</span><span class="badge ${s.status}">${badge}</span>
      <span class="meta">${when(s.created)} · ${gridLabel(s)}${s.status === "done" ? ` · ARP ${fmt(m.arp)}` : ""}</span></li>`;
  }).join("");
}
$("#history").addEventListener("click", (e) => { const li = e.target.closest("li.item"); if (li) openScan(+li.dataset.id); });

// ---------- scan view ----------
async function openScan(id, { keepView = false } = {}) {
  const scan = await api(`/api/scans/${id}`);
  const switched = !S.scan || S.scan.id !== id;
  S.scan = scan;
  if (switched && !keepView) { S.competitor = null; S.mode = "rank"; }
  renderScan(switched);
  document.querySelectorAll("#history li.item").forEach((li) => li.classList.toggle("active", +li.dataset.id === id));
  stopPolling();
  if (scan.status === "running") S.pollTimer = setTimeout(async () => { await loadHistory(); openScan(id, { keepView: true }); }, 2500);
  else if (!switched) loadHistory();
}
function stopPolling() { clearTimeout(S.pollTimer); S.pollTimer = null; }
function closeScan() {
  stopPolling(); S.scan = null; S.competitor = null;
  $("#scanCard").classList.add("hidden"); $("#compCard").classList.add("hidden");
  document.querySelectorAll("#history li.item").forEach((li) => li.classList.remove("active"));
}

function renderScan(fit) {
  const s = S.scan;
  if (centerMarker) centerMarker.remove();  // it would cover the middle rank pin
  $("#scanCard").classList.remove("hidden");
  $("#scanTitle").textContent = `“${s.keyword}”`;
  $("#scanSub").textContent = `${s.business_name} · ${when(s.created)} · ${gridLabel(s)}`;

  const prog = $("#progress");
  if (s.status === "running") {
    prog.classList.remove("hidden");
    prog.querySelector("div").style.width = `${(100 * s.progress) / s.total}%`;
    prog.querySelector("span").textContent = s.progress ? `Scanning ${s.progress} / ${s.total} points…` : "Queued / starting…";
  } else prog.classList.add("hidden");

  renderMetrics();
  const cmp = s.comparison;
  $("#deltaBtn").disabled = !cmp;
  $("#deltaBtn").title = cmp ? `Compared with ${when(cmp.previous_created)}` : "Needs an earlier scan with the same keyword and grid";
  if (!cmp && S.mode === "delta") S.mode = "rank";
  document.querySelectorAll("#viewToggle button").forEach((b) => b.classList.toggle("on", b.dataset.mode === S.mode));
  $("#viewing").innerHTML = S.competitor
    ? `<span class="chip">Showing: <b>${esc(S.competitor.name)}</b> <a href="#" id="clearComp">✕ back to my business</a></span>` : "";
  const clr = $("#clearComp");
  if (clr) clr.addEventListener("click", (e) => { e.preventDefault(); S.competitor = null; renderScan(false); });

  renderCompetitors();
  drawScanGrid();
  if (fit) fitGrid();
}

function renderMetrics() {
  const s = S.scan;
  let m = s.metrics || {};
  if (S.competitor && s.competitors) m = s.competitors.find((c) => sameBiz(c, S.competitor)) || {};
  const d = (!S.competitor && s.comparison && s.comparison.metrics) || {};
  // For ARP/ATRP lower is better; for SoLV/found higher is better.
  const delta = (k, lowerBetter) => {
    const v = d[k];
    if (v === null || v === undefined || v === 0) return "";
    const good = lowerBetter ? v < 0 : v > 0;
    return `<div class="d ${good ? "up" : "down"}">${v > 0 ? "+" : ""}${v}</div>`;
  };
  if (s.status === "failed") { $("#metrics").innerHTML = `<div class="err small" style="grid-column:1/-1">Scan failed: ${esc(s.error)}</div>`; return; }
  $("#metrics").innerHTML = [
    ["ARP", fmt(m.arp), "avg rank where found", delta("arp", true)],
    ["ATRP", fmt(m.atrp), "avg rank, 20+ = 21", delta("atrp", true)],
    ["SoLV", fmt(m.solv, "%"), "points in top 3", delta("solv", false)],
    ["Found", fmt(m.found_pct, "%"), "points in top 20", delta("found_pct", false)],
  ].map(([l, v, title, dl]) => `<div class="metric" title="${title}"><div class="l">${l}</div><div class="v">${v}</div>${dl}</div>`).join("");
}

function renderCompetitors() {
  const s = S.scan, list = s.competitors || [];
  $("#compCard").classList.toggle("hidden", !list.length);
  const me = myKey();
  $("#compTable tbody").innerHTML = list.map((c, i) => `
    <tr data-i="${i}" class="${sameBiz(c, me) ? "me" : ""} ${S.competitor && sameBiz(c, S.competitor) ? "sel" : ""}">
      <td>${i + 1}</td><td title="${esc(c.name)}${c.category ? " · " + esc(c.category) : ""}">${esc(c.name)}</td>
      <td>${c.solv}%</td><td>${c.atrp}</td><td>${c.found_pct}%</td><td>${fmt(c.rating)}</td></tr>`).join("");
}
$("#compTable tbody").addEventListener("click", (e) => {
  const tr = e.target.closest("tr"); if (!tr) return;
  const c = S.scan.competitors[+tr.dataset.i];
  const isMe = sameBiz(c, myKey());
  S.competitor = isMe || (S.competitor && sameBiz(c, S.competitor)) ? null : { cid: c.cid, name: c.name };
  if (S.competitor) S.mode = "rank";
  renderScan(false);
});
$("#compToggle").addEventListener("click", () => {
  const body = $("#compBody"); body.classList.toggle("hidden");
  $("#compToggle").textContent = body.classList.contains("hidden") ? "+" : "–";
});

function drawScanGrid() {
  const s = S.scan;
  gridLayer.clearLayers();
  const key = targetKey();
  const byCell = new Map(s.points.map((p) => [`${p.row},${p.col}`, p]));
  const pts = gridPoints(s.center_lat, s.center_lng, s.grid_size, s.spacing_km);
  const pad = cardPadding();
  pts.forEach(([lat, lng], idx) => {
    const row = Math.floor(idx / s.grid_size), col = idx % s.grid_size;
    const p = byCell.get(`${row},${col}`);
    let cls, label;
    if (!p) { cls = "pending"; label = "…"; }
    else if (p.status !== "ok") { cls = "rx"; label = "!"; }
    else {
      const rank = S.competitor ? rankIn(p.results, key) : p.rank;
      if (S.mode === "delta" && s.comparison) {
        const prevRaw = s.comparison.points[`${row},${col}`];
        if (prevRaw === undefined) { cls = "same"; label = "?"; }
        else {
          const diff = (prevRaw ?? NOT_FOUND) - (rank ?? NOT_FOUND);  // positive = moved up
          cls = diff > 0 ? "up" : diff < 0 ? "down" : "same";
          label = diff > 0 ? `+${diff}` : diff < 0 ? `${diff}` : "=";
        }
      } else { cls = rankClass(rank); label = rank ?? "20+"; }
    }
    const m = L.marker([lat, lng], { icon: L.divIcon({ className: "", html: `<div class="pin ${cls}">${label}</div>`, iconSize: [34, 34] }) });
    if (p) m.bindPopup(() => popupHtml(p, key), { maxWidth: 320, autoPanPaddingTopLeft: L.point(pad.topLeft), autoPanPaddingBottomRight: L.point(pad.bottomRight) });
    m.addTo(gridLayer);
  });
}

function popupHtml(p, key) {
  if (p.status !== "ok") return `<div class="popup"><h4>Point not scanned</h4><div class="muted">${esc(p.error)}</div></div>`;
  const rank = rankIn(p.results, key) ?? (S.competitor ? null : p.rank);
  const items = p.results.map((r) => `<li class="${sameBiz(r, key) ? "hit" : ""}">${esc(r.name)}${r.rating ? ` <span class="muted">★${r.rating}</span>` : ""}</li>`).join("");
  return `<div class="popup"><h4>${esc(key.name)}: ${rank ? "#" + rank : "not in top 20"}</h4>
    <div class="muted">${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}</div><ol>${items || "<li class='muted'>No results</li>"}</ol></div>`;
}

document.querySelectorAll("#viewToggle button").forEach((b) => b.addEventListener("click", () => {
  if (b.disabled) return;
  S.mode = b.dataset.mode; if (S.mode === "delta") S.competitor = null;
  renderScan(false);
}));

$("#printBtn").addEventListener("click", () => window.print());
$("#deleteBtn").addEventListener("click", async () => {
  if (!S.scan || !confirm(`Delete scan “${S.scan.keyword}” from ${when(S.scan.created)}?`)) return;
  try { await api(`/api/scans/${S.scan.id}`, { method: "DELETE" }); }
  catch (err) { alert(err.message); return; }
  closeScan(); await loadHistory(); drawPreview();
});

// ---------- per-viewer convenience storage ----------
function localGet(k) { try { return localStorage.getItem("geogrid." + k); } catch { return null; } }
function localSet(k, v) { try { localStorage.setItem("geogrid." + k, v); } catch { /* storage unavailable */ } }

updateHint();
loadBusinesses().catch((e) => say("#bizMsg", "err", e.message));
