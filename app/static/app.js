const $ = (id) => document.getElementById(id);
let socket;

function setPage(name, title) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  const page = $("page-" + name);
  if (page) page.classList.add("active");
  document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.page === name));
  $("page-title").textContent = title || ({home:"Home",bans:"Concurrent Bans",reports:"Recent Reports",lookup:"User Lookup",catalog:"Catalog",title:"Title Data"}[name] || name);
}
document.querySelectorAll(".nav-item").forEach(b => b.addEventListener("click", () => {
  setPage(b.dataset.page);
  if (b.dataset.page === "title") loadTitleData();
  if (b.dataset.page === "catalog") loadCatalog();
  if (b.dataset.page === "reports") loadReports();
}));
document.querySelectorAll("[data-goto]").forEach(b => b.addEventListener("click", () => { setPage(b.dataset.goto); loadReports(); }));
document.querySelectorAll(".priority-link").forEach(b => b.addEventListener("click", () => {
  setPage("reports", b.textContent.trim());
  loadReports(b.dataset.priority);
}));

async function api(url, options) {
  const r = await fetch(url, options);
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || data.error || "Request failed");
  return data;
}
function reportElement(r) {
  const priority = (r.priority || "Normal").toLowerCase();
  return `<div class="report-row"><div class="report-main"><b>${escapeHtml(r.targetUsername || "Unknown player")} · ${escapeHtml(r.reason || "Unspecified")}</b><small>${escapeHtml(r.reportID || "")} · ${escapeHtml(r.reporterRank || "Player")} · ${escapeHtml(r.timestamp || "")}</small></div><span class="tag ${priority}">${escapeHtml(r.priority || "Normal")}</span></div>`;
}
function escapeHtml(v) { return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

async function loadHome() {
  try {
    const d = await api("/api/home");
    $("stat-total").textContent = d.reports_total;
    $("stat-pending").textContent = d.reports_pending;
    $("stat-playfab").textContent = d.playfab_configured ? "Ready" : "Setup";
    $("stat-playfab-sub").textContent = d.playfab_configured ? "Credentials configured" : "Add credentials to .env";
    $("stat-priority").textContent = d.recent_reports.filter(r => ["Critical","High","Medium"].includes(r.priority)).length;
    $("recent-reports").innerHTML = d.recent_reports.length ? d.recent_reports.map(reportElement).join("") : '<div class="empty-state">No locally synchronized reports yet.</div>';
    $("pf-status").textContent = d.playfab_configured ? "Configured" : "Not configured";
    $("pf-status").className = d.playfab_configured ? "status-good" : "";
    $("catalog-version").textContent = d.catalog_version || "—";
  } catch(e) { console.error(e); }
}
async function loadReports(priority=null) {
  try {
    const d = await api("/api/reports?limit=250");
    let rows = d.reports || [];
    if (priority) rows = rows.filter(r => String(r.reporterRank || "Player").trim().toLowerCase() === String(priority).trim().toLowerCase());
    $("all-reports").innerHTML = rows.length ? rows.map(reportElement).join("") : '<div class="empty-state">No matching reports in the local archive.</div>';
  } catch(e) { $("all-reports").textContent = e.message; }
}
async function loadTitleData() {
  $("title-save-status").textContent = "Loading from PlayFab…";
  try {
    const d = await api("/api/title-data");
    $("motd").value = d.data?.MOTD || "";
    $("game-version").value = d.data?.GameVersion || "";
    $("title-save-status").textContent = "Loaded from PlayFab.";
  } catch(e) { $("title-save-status").textContent = e.message; }
}
$("save-title").addEventListener("click", async () => {
  const btn = $("save-title"); btn.disabled = true;
  try {
    await api("/api/title-data", {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:"MOTD",value:$("motd").value})});
    await api("/api/title-data", {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:"GameVersion",value:$("game-version").value})});
    $("title-save-status").textContent = "Saved MOTD and GameVersion to PlayFab.";
  } catch(e) { $("title-save-status").textContent = e.message; }
  finally { btn.disabled = false; }
});
async function loadCatalog() {
  $("catalog-list").textContent = "Loading catalog…";
  try {
    const d = await api("/api/catalog");
    $("catalog-subtitle").textContent = `${d.catalog.length} item(s) · ${d.catalog_version}`;
    $("catalog-list").innerHTML = d.catalog.length ? d.catalog.map(i => `<div class="catalog-row"><div class="report-main"><b>${escapeHtml(i.DisplayName || i.ItemId)}</b><small>${escapeHtml(i.ItemId)}</small></div><span class="tag">Catalog item</span></div>`).join("") : '<div class="empty-state">No items found.</div>';
  } catch(e) { $("catalog-list").textContent = e.message; }
}
$("load-catalog").addEventListener("click", loadCatalog);
$("refresh-home").addEventListener("click", loadHome);
async function openPlayerDetail(id) {
  const cleanId = String(id || "").trim();
  if (!/^[A-Za-z0-9-]{16,}$/.test(cleanId)) {
    $("player-lookup-status").textContent = "Enter the complete PlayFab ID (at least 16 characters).";
    return;
  }

  setPage("lookup", "User Lookup");
  $("player-query").value = cleanId;
  $("player-search-view").hidden = true;
  $("player-detail-view").hidden = false;
  $("player-result").innerHTML = '<div class="empty-state">Loading full player information…</div>';
  window.scrollTo({top: 0, behavior: "smooth"});
  await loadPlayerProfile(cleanId);
}

$("player-lookup-form").addEventListener("submit", async e => {
  e.preventDefault();
  await openPlayerDetail($("player-query").value);
});

$("player-back").addEventListener("click", () => {
  $("player-detail-view").hidden = true;
  $("player-search-view").hidden = false;
  $("player-lookup-status").textContent = "";
  window.scrollTo({top: 0, behavior: "smooth"});
});

function formatDate(value) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

async function loadPlayerProfile(id) {
  const result = $("player-result");
  try {
    const full = await api("/api/player/" + encodeURIComponent(id));
    const info = full.account?.UserInfo || full.account?.AccountInfo || {};
    const title = info.TitleInfo || {}, bans = full.bans?.BanData || [];
    const localNotes = full.local_notes || [], cloudNotes = full.playfab_notes || [];
    const against = full.reports_against || [], submitted = full.reports_submitted || [];
    const inventory = full.inventory || {};
    const currency = inventory.VirtualCurrency || {};
    const ssBalance = full.inventory_error ? null : (currency.SS ?? 0);
    const displayName = title.DisplayName || info.Username || id;
    const origin = title.Origination || title.OriginationSource || "Unavailable";
    const banRows = bans.length ? bans.map(b => `<div class="profile-record"><b>${escapeHtml(b.Reason || "No reason supplied")}</b><small>${escapeHtml(formatDate(b.Created))} · Expires: ${escapeHtml(b.Expires ? formatDate(b.Expires) : "Permanent / no expiry")}</small></div>`).join("") : '<p class="muted">No bans returned by PlayFab.</p>';
    const reportRows = (rows, submittedByPlayer=false) => rows.length ? rows.map(r => `<div class="profile-record"><b>${escapeHtml(r.reason || "Unspecified")} · ${escapeHtml(r.status || "Pending")}</b><small>${escapeHtml(formatDate(r.timestamp))} · ${submittedByPlayer ? "Target" : "Reporter"}: ${escapeHtml(submittedByPlayer ? (r.targetUsername || r.targetPlayFabID || "Unknown") : (r.reporterPlayFabID || "Unknown"))} · Reporter rank: ${escapeHtml(r.reporterRank || "Player")} · Priority: ${escapeHtml(r.priority || "Normal")}</small><p>Lobby: ${escapeHtml(r.lobbyID || "Unknown")} · Region: ${escapeHtml(r.photonRegion || "Unknown")}</p></div>`).join("") : '<p class="muted">No reports in the local archive.</p>';
    const noteRows = localNotes.length ? localNotes.map(n => `<div class="profile-record"><b>${escapeHtml(n.category || "General")}</b><p>${escapeHtml(n.note)}</p><small>${escapeHtml(formatDate(n.created_at || n.createdAt))} · ${escapeHtml(n.author || "Local Admin")}</small></div>`).join("") : '<p class="muted">No local admin notes yet.</p>';
    result.innerHTML = `
      <div class="result-card player-profile">
        <div class="profile-heading"><div><h3>${escapeHtml(displayName)}</h3><small>${escapeHtml(id)}</small></div><button class="button secondary" id="copy-player-id" type="button">Copy ID</button></div>
        <div class="profile-grid">
          <div><span>Account created</span><b>${escapeHtml(formatDate(title.Created || info.Created))}</b></div>
          <div><span>Last login</span><b>${escapeHtml(formatDate(title.LastLogin))}</b></div>
          <div><span>First login</span><b>${escapeHtml(formatDate(title.FirstLogin))}</b></div>
          <div><span>Account origin</span><b>${escapeHtml(origin)}</b></div>
          <div><span>Ban status</span><b class="${title.isBanned ? "profile-banned" : "status-good"}">${title.isBanned ? "Banned" : "Not banned"}</b></div>
          <div><span>Username</span><b>${escapeHtml(info.Username || "Not set")}</b></div>
          <div class="currency-stat"><span>Springy Springs (SS)</span><b>${ssBalance === null ? "Unavailable" : escapeHtml(Number(ssBalance).toLocaleString()) + " SS"}</b></div>
        </div>
        <div class="profile-section"><h4>Account ban history (${bans.length})</h4>${banRows}</div>
        <div class="profile-section"><h4>Reports against this player (${against.length})</h4>${reportRows(against)}</div>
        <div class="profile-section"><h4>Reports submitted by this player (${submitted.length})</h4>${reportRows(submitted, true)}</div>
        <div class="profile-section"><h4>Local admin notes (${localNotes.length})</h4>
          <form id="local-note-form" class="local-note-form">
            <input id="local-note-category" maxlength="40" placeholder="Category (e.g. Warning, Staff note)" value="General">
            <textarea id="local-note-text" maxlength="2000" required placeholder="Add a note visible only in this local admin panel…"></textarea>
            <button class="button primary" type="submit">Save local note</button><span id="local-note-status" class="muted"></span>
          </form>
          <div id="local-note-list">${noteRows}</div>
        </div>
        <details class="profile-section"><summary>PlayFab internal account data</summary><pre>${escapeHtml(JSON.stringify(full.internal_data?.Data || {}, null, 2))}</pre></details>
        <details class="profile-section"><summary>PlayFab-synced notes (${cloudNotes.length})</summary>${cloudNotes.length ? cloudNotes.map(n => `<div class="profile-record"><b>${escapeHtml(n.category || "General")}</b><p>${escapeHtml(n.note)}</p><small>${escapeHtml(n.createdAt || "")}</small></div>`).join("") : '<p class="muted">No PlayFab notes.</p>'}</details>
        <details class="profile-section"><summary>Full PlayFab response (raw)</summary><pre>${escapeHtml(JSON.stringify(full, null, 2))}</pre></details>
      </div>`;
    $("copy-player-id").addEventListener("click", async () => {
      await navigator.clipboard.writeText(id);
      $("copy-player-id").textContent = "Copied";
    });
    $("local-note-form").addEventListener("submit", async e => {
      e.preventDefault();
      const status = $("local-note-status"), button = e.currentTarget.querySelector("button[type=submit]");
      const note = $("local-note-text").value.trim();
      if (!note) return;
      button.disabled = true; status.textContent = "Saving…";
      try {
        await api(`/api/player/${encodeURIComponent(id)}/local-notes`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({note,category:$("local-note-category").value.trim() || "General"})});
        await loadPlayerProfile(id);
      } catch(err) { status.textContent = err.message; }
      finally { button.disabled = false; }
    });
  } catch(e) { result.innerHTML = `<div class="search-error">${escapeHtml(e.message)}</div>`; }
}


function connectSocket() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${scheme}://${location.host}/ws`);
  socket.onopen = () => { $("ws-status").textContent = "Connected"; $("ws-status").className = "status-good"; $("connection-label").textContent = "Local backend connected"; };
  socket.onclose = () => { $("ws-status").textContent = "Disconnected"; $("connection-label").textContent = "Reconnecting…"; setTimeout(connectSocket, 1800); };
  socket.onmessage = e => { const m = JSON.parse(e.data); if (m.type === "reports_changed") { loadHome(); loadReports(); } };
}
loadHome();
connectSocket();
