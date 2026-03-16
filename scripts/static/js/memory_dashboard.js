/* =====================================================================
   memory_dashboard.js — Memory Tab UI Component
   POLARIS Live Dashboard

   Provides:
     - renderMemoryDashboard(containerId) — create full memory UI in container

   Dependencies (from core.js):
     - esc(str)
     - truncStr(str, maxLen)
     - showToast(msg, type)
     - setText(elementId, text)

   All DOM elements created dynamically. CSS injected once into <head>.
   ===================================================================== */

/* =====================================================================
   Internal State
   ===================================================================== */
var _memState = {
  containerId: null,
  loading: false,
  error: null,
  stats: null,
  items: [],
  itemsTotal: 0,
  itemsOffset: 0,
  itemsLimit: 100,
  searchQuery: "",
  searchResults: null,
  activeDomainFilter: null,
  debounceTimer: null,
  timelineOpen: false,
  timelineSessions: [],
  bubbleData: []
};

/* =====================================================================
   CSS Injection (runs once)
   ===================================================================== */
function _memInjectStyles() {
  if (document.getElementById("mem-injected-styles")) return;
  var style = document.createElement("style");
  style.id = "mem-injected-styles";
  style.textContent = [
    /* --- Main Container --- */
    ".mem-dashboard {",
    "  display: flex;",
    "  flex-direction: column;",
    "  gap: 16px;",
    "  padding: 16px 0;",
    "}",

    /* --- Stats Bar --- */
    ".mem-stats-bar {",
    "  display: grid;",
    "  grid-template-columns: auto 1fr auto;",
    "  gap: 16px;",
    "  align-items: start;",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-md);",
    "  padding: 16px 20px;",
    "}",
    "@media (max-width: 768px) {",
    "  .mem-stats-bar {",
    "    grid-template-columns: 1fr;",
    "  }",
    "}",
    ".mem-stat-total {",
    "  display: flex;",
    "  flex-direction: column;",
    "  align-items: center;",
    "  gap: 2px;",
    "  min-width: 100px;",
    "}",
    ".mem-stat-total-number {",
    "  font-size: 36px;",
    "  font-weight: 800;",
    "  color: var(--text-primary);",
    "  font-family: var(--font-mono);",
    "  line-height: 1;",
    "}",
    ".mem-stat-total-label {",
    "  font-size: var(--text-3xs);",
    "  font-weight: 600;",
    "  color: var(--text-tertiary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 1px;",
    "}",

    /* --- Tier Badges --- */
    ".mem-tier-row {",
    "  display: flex;",
    "  gap: 10px;",
    "  align-items: center;",
    "  flex-wrap: wrap;",
    "}",
    ".mem-tier-badge {",
    "  display: inline-flex;",
    "  align-items: center;",
    "  gap: 6px;",
    "  padding: 4px 12px;",
    "  border-radius: var(--radius-sm);",
    "  font-size: 12px;",
    "  font-weight: 700;",
    "  letter-spacing: 0.5px;",
    "}",
    ".mem-tier-badge-gold {",
    "  background: var(--gold-dim);",
    "  color: var(--gold);",
    "}",
    ".mem-tier-badge-silver {",
    "  background: var(--silver-dim);",
    "  color: var(--silver);",
    "}",
    ".mem-tier-badge-bronze {",
    "  background: var(--bronze-dim);",
    "  color: var(--bronze);",
    "}",
    ".mem-tier-count {",
    "  font-family: var(--font-mono);",
    "  font-size: 14px;",
    "  font-weight: 800;",
    "}",

    /* --- Storage Indicator --- */
    ".mem-storage-indicator {",
    "  display: flex;",
    "  align-items: center;",
    "  gap: 6px;",
    "  font-size: 12px;",
    "  font-weight: 600;",
    "}",
    ".mem-storage-dot {",
    "  width: 8px;",
    "  height: 8px;",
    "  border-radius: 50%;",
    "  flex-shrink: 0;",
    "}",
    ".mem-storage-dot-online {",
    "  background: var(--success);",
    "  box-shadow: 0 0 6px rgba(16, 185, 129, 0.5);",
    "}",
    ".mem-storage-dot-offline {",
    "  background: var(--error);",
    "  box-shadow: 0 0 6px rgba(239, 68, 68, 0.5);",
    "}",

    /* --- Domain Bar Chart --- */
    ".mem-domain-chart {",
    "  margin-top: 12px;",
    "}",
    ".mem-domain-chart-title {",
    "  font-size: 11px;",
    "  font-weight: 700;",
    "  color: var(--text-secondary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 0.8px;",
    "  margin-bottom: 8px;",
    "}",
    ".mem-domain-bar-row {",
    "  display: flex;",
    "  align-items: center;",
    "  gap: 8px;",
    "  margin-bottom: 4px;",
    "}",
    ".mem-domain-bar-label {",
    "  font-size: 11px;",
    "  color: var(--text-secondary);",
    "  min-width: 140px;",
    "  max-width: 140px;",
    "  overflow: hidden;",
    "  text-overflow: ellipsis;",
    "  white-space: nowrap;",
    "  text-align: right;",
    "  font-family: var(--font-mono);",
    "}",
    ".mem-domain-bar-track {",
    "  flex: 1;",
    "  height: 14px;",
    "  background: var(--bg-inset);",
    "  border-radius: 3px;",
    "  overflow: hidden;",
    "  position: relative;",
    "}",
    ".mem-domain-bar-fill {",
    "  height: 100%;",
    "  background: var(--accent);",
    "  border-radius: 3px;",
    "  transition: width 0.4s ease;",
    "  min-width: 2px;",
    "}",
    ".mem-domain-bar-count {",
    "  font-size: 10px;",
    "  font-family: var(--font-mono);",
    "  color: var(--text-tertiary);",
    "  min-width: 30px;",
    "  text-align: right;",
    "}",

    /* --- Two-Column Layout --- */
    ".mem-columns {",
    "  display: grid;",
    "  grid-template-columns: 3fr 2fr;",
    "  gap: 16px;",
    "  min-height: 200px;",
    "}",
    "@media (max-width: 900px) {",
    "  .mem-columns {",
    "    grid-template-columns: 1fr;",
    "  }",
    "}",

    /* --- Left Column: Bubble Chart --- */
    ".mem-bubble-panel {",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-md);",
    "  padding: 16px;",
    "  display: flex;",
    "  flex-direction: column;",
    "}",
    ".mem-panel-header {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: space-between;",
    "  margin-bottom: 12px;",
    "}",
    ".mem-panel-title {",
    "  font-size: 12px;",
    "  font-weight: 700;",
    "  color: var(--text-secondary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 1px;",
    "}",
    ".mem-bubble-container {",
    "  flex: 1;",
    "  min-height: 180px;",
    "  position: relative;",
    "  overflow: hidden;",
    "}",
    ".mem-bubble-svg {",
    "  width: 100%;",
    "  height: 100%;",
    "}",
    ".mem-bubble {",
    "  cursor: pointer;",
    "  transition: opacity 0.2s ease;",
    "}",
    ".mem-bubble:hover {",
    "  opacity: 0.85;",
    "}",
    ".mem-bubble-label {",
    "  pointer-events: none;",
    "  fill: var(--text-primary);",
    "  font-size: 10px;",
    "  font-family: var(--font-sans);",
    "  font-weight: 600;",
    "  text-anchor: middle;",
    "  dominant-baseline: central;",
    "}",
    ".mem-bubble-count {",
    "  pointer-events: none;",
    "  fill: var(--text-secondary);",
    "  font-size: 9px;",
    "  font-family: var(--font-mono);",
    "  text-anchor: middle;",
    "  dominant-baseline: central;",
    "}",

    /* --- Active Filter Bar --- */
    ".mem-filter-bar {",
    "  display: flex;",
    "  align-items: center;",
    "  gap: 8px;",
    "  padding: 8px 12px;",
    "  background: var(--accent-dim, rgba(56,189,248,0.1));",
    "  border: 1px solid var(--accent);",
    "  border-radius: var(--radius-sm);",
    "  margin-bottom: 10px;",
    "  font-size: 12px;",
    "  color: var(--accent);",
    "  font-weight: 600;",
    "}",
    ".mem-filter-clear {",
    "  background: transparent;",
    "  border: 1px solid var(--accent);",
    "  border-radius: var(--radius-sm);",
    "  color: var(--accent);",
    "  font-size: 11px;",
    "  padding: 2px 8px;",
    "  cursor: pointer;",
    "  font-family: var(--font-sans);",
    "  margin-left: auto;",
    "  transition: all 0.15s ease;",
    "}",
    ".mem-filter-clear:hover {",
    "  background: var(--accent);",
    "  color: #fff;",
    "}",
    ".mem-filter-clear:focus-visible {",
    "  outline: 2px solid var(--accent);",
    "  outline-offset: 2px;",
    "}",

    /* --- Right Column: Search + List --- */
    ".mem-list-panel {",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-md);",
    "  padding: 16px;",
    "  display: flex;",
    "  flex-direction: column;",
    "  max-height: none;",
    "}",
    ".mem-search-wrap {",
    "  position: relative;",
    "  margin-bottom: 12px;",
    "}",
    ".mem-search-input {",
    "  width: 100%;",
    "  min-height: 36px;",
    "  padding: 8px 12px 8px 32px;",
    "  background: var(--bg-inset);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-sm);",
    "  color: var(--text-primary);",
    "  font-size: 13px;",
    "  font-family: var(--font-sans);",
    "  outline: none;",
    "  transition: border-color 0.15s ease;",
    "  box-sizing: border-box;",
    "}",
    ".mem-search-input:focus {",
    "  border-color: var(--accent);",
    "}",
    ".mem-search-input::placeholder {",
    "  color: var(--text-tertiary);",
    "}",
    ".mem-search-icon {",
    "  position: absolute;",
    "  left: 10px;",
    "  top: 50%;",
    "  transform: translateY(-50%);",
    "  font-size: 14px;",
    "  color: var(--text-tertiary);",
    "  pointer-events: none;",
    "}",

    /* --- Item List --- */
    ".mem-item-list {",
    "  flex: 1;",
    "  overflow-y: auto;",
    "  scrollbar-width: thin;",
    "}",
    ".mem-item-list::-webkit-scrollbar { width: 6px; }",
    ".mem-item-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }",
    ".mem-item-card {",
    "  padding: 10px 12px;",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-sm);",
    "  margin-bottom: 6px;",
    "  background: var(--bg-secondary);",
    "  transition: border-color 0.15s ease, background 0.15s ease;",
    "}",
    ".mem-item-card:hover {",
    "  border-color: var(--accent);",
    "  background: var(--bg-inset);",
    "}",
    ".mem-item-statement {",
    "  font-size: 12px;",
    "  color: var(--text-primary);",
    "  line-height: 1.5;",
    "  display: -webkit-box;",
    "  -webkit-line-clamp: 2;",
    "  -webkit-box-orient: vertical;",
    "  overflow: hidden;",
    "  margin-bottom: 6px;",
    "}",
    ".mem-item-meta {",
    "  display: flex;",
    "  align-items: center;",
    "  gap: 6px;",
    "  flex-wrap: wrap;",
    "}",
    ".mem-item-domain {",
    "  display: inline-flex;",
    "  align-items: center;",
    "  padding: 1px 6px;",
    "  background: var(--bg-inset);",
    "  border: 1px solid var(--border);",
    "  border-radius: 3px;",
    "  font-size: 10px;",
    "  font-family: var(--font-mono);",
    "  color: var(--text-secondary);",
    "}",
    ".mem-item-tier {",
    "  display: inline-block;",
    "  padding: 1px 6px;",
    "  border-radius: 3px;",
    "  font-size: 9px;",
    "  font-weight: 700;",
    "  letter-spacing: 0.5px;",
    "}",
    ".mem-item-tier-gold {",
    "  background: var(--gold-dim);",
    "  color: var(--gold);",
    "}",
    ".mem-item-tier-silver {",
    "  background: var(--silver-dim);",
    "  color: var(--silver);",
    "}",
    ".mem-item-tier-bronze {",
    "  background: var(--bronze-dim);",
    "  color: var(--bronze);",
    "}",
    ".mem-item-faith {",
    "  font-size: 10px;",
    "  font-family: var(--font-mono);",
    "  font-weight: 600;",
    "}",
    ".mem-item-faith-good { color: var(--success); }",
    ".mem-item-faith-warn { color: var(--warning); }",
    ".mem-item-faith-bad { color: var(--error); }",
    ".mem-item-vector {",
    "  display: inline-block;",
    "  padding: 1px 5px;",
    "  background: var(--accent-dim, rgba(56,189,248,0.08));",
    "  border-radius: 3px;",
    "  font-size: 9px;",
    "  font-family: var(--font-mono);",
    "  color: var(--accent);",
    "}",
    ".mem-item-delete {",
    "  margin-left: auto;",
    "  background: transparent;",
    "  border: 1px solid transparent;",
    "  border-radius: var(--radius-sm);",
    "  color: var(--text-tertiary);",
    "  font-size: 14px;",
    "  min-height: 36px;",
    "  min-width: 36px;",
    "  display: inline-flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  padding: 2px 6px;",
    "  cursor: pointer;",
    "  transition: all 0.15s ease;",
    "  line-height: 1;",
    "  font-family: var(--font-sans);",
    "}",
    ".mem-item-delete:hover {",
    "  color: var(--error);",
    "  border-color: var(--error);",
    "  background: rgba(239, 68, 68, 0.08);",
    "}",
    ".mem-item-delete:focus-visible {",
    "  outline: 2px solid var(--error);",
    "  outline-offset: 2px;",
    "}",

    /* --- Load More Button --- */
    ".mem-load-more {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  padding: 8px 16px;",
    "  margin-top: 8px;",
    "  background: var(--bg-inset);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-sm);",
    "  color: var(--text-secondary);",
    "  font-size: 12px;",
    "  font-weight: 600;",
    "  cursor: pointer;",
    "  font-family: var(--font-sans);",
    "  transition: all 0.15s ease;",
    "}",
    ".mem-load-more:hover {",
    "  background: var(--bg-secondary);",
    "  border-color: var(--accent);",
    "  color: var(--accent);",
    "}",
    ".mem-load-more:disabled {",
    "  opacity: 0.5;",
    "  cursor: not-allowed;",
    "}",
    ".mem-load-more:focus-visible {",
    "  outline: 2px solid var(--accent);",
    "  outline-offset: 2px;",
    "}",

    /* --- Timeline Section --- */
    ".mem-timeline-section {",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-md);",
    "  overflow: hidden;",
    "}",
    ".mem-timeline-toggle {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: space-between;",
    "  padding: 12px 16px;",
    "  cursor: pointer;",
    "  user-select: none;",
    "  transition: background 0.15s ease;",
    "}",
    ".mem-timeline-toggle:hover {",
    "  background: var(--bg-inset);",
    "}",
    ".mem-timeline-toggle-title {",
    "  font-size: 12px;",
    "  font-weight: 700;",
    "  color: var(--text-secondary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 1px;",
    "}",
    ".mem-timeline-chevron {",
    "  font-size: 11px;",
    "  color: var(--text-tertiary);",
    "  transition: transform 0.2s ease;",
    "}",
    ".mem-timeline-chevron-open {",
    "  transform: rotate(90deg);",
    "}",
    ".mem-timeline-body {",
    "  padding: 0 16px 16px 16px;",
    "}",
    ".mem-timeline-hidden {",
    "  display: none;",
    "}",
    ".mem-timeline-chart {",
    "  display: flex;",
    "  align-items: flex-end;",
    "  gap: 4px;",
    "  height: 120px;",
    "  padding-top: 8px;",
    "  border-bottom: 1px solid var(--border);",
    "}",
    ".mem-timeline-bar-wrap {",
    "  flex: 1;",
    "  display: flex;",
    "  flex-direction: column;",
    "  align-items: center;",
    "  gap: 4px;",
    "  height: 100%;",
    "  justify-content: flex-end;",
    "}",
    ".mem-timeline-bar {",
    "  width: 100%;",
    "  max-width: 40px;",
    "  min-width: 8px;",
    "  background: var(--accent);",
    "  border-radius: 3px 3px 0 0;",
    "  transition: height 0.3s ease;",
    "  position: relative;",
    "}",
    ".mem-timeline-bar:hover {",
    "  opacity: 0.85;",
    "}",
    ".mem-timeline-bar-label {",
    "  font-size: 8px;",
    "  color: var(--text-tertiary);",
    "  font-family: var(--font-mono);",
    "  white-space: nowrap;",
    "  max-width: 50px;",
    "  overflow: hidden;",
    "  text-overflow: ellipsis;",
    "  text-align: center;",
    "}",
    ".mem-timeline-bar-count {",
    "  font-size: 9px;",
    "  font-family: var(--font-mono);",
    "  color: var(--text-primary);",
    "  font-weight: 600;",
    "  text-align: center;",
    "}",

    /* --- Empty / Loading / Error States --- */
    ".mem-empty-state {",
    "  display: flex;",
    "  flex-direction: column;",
    "  align-items: center;",
    "  justify-content: center;",
    "  padding: 40px 20px;",
    "  color: var(--text-tertiary);",
    "  font-size: 13px;",
    "  text-align: center;",
    "  gap: 8px;",
    "  border: 2px dashed var(--border);",
    "  border-radius: var(--radius-lg);",
    "  background: var(--bg-inset);",
    "}",
    ".mem-empty-icon {",
    "  font-size: 32px;",
    "  opacity: 0.4;",
    "  margin-bottom: 4px;",
    "}",
    ".mem-loading {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  gap: 8px;",
    "  padding: 40px;",
    "  color: var(--text-tertiary);",
    "  font-size: 13px;",
    "}",
    ".mem-spinner {",
    "  width: 16px;",
    "  height: 16px;",
    "  border: 2px solid var(--border);",
    "  border-top-color: var(--accent);",
    "  border-radius: 50%;",
    "  animation: mem-spin 0.7s linear infinite;",
    "}",
    "@keyframes mem-spin { to { transform: rotate(360deg); } }",
    ".mem-error {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  gap: 8px;",
    "  padding: 20px;",
    "  color: var(--error);",
    "  font-size: 12px;",
    "  text-align: center;",
    "  flex-wrap: wrap;",
    "}",
    ".mem-retry-btn {",
    "  background: rgba(239, 68, 68, 0.1);",
    "  border: 1px solid var(--error);",
    "  border-radius: var(--radius-sm);",
    "  color: var(--error);",
    "  font-size: 11px;",
    "  padding: 3px 10px;",
    "  cursor: pointer;",
    "  font-family: var(--font-sans);",
    "  transition: all 0.15s ease;",
    "}",
    ".mem-retry-btn:hover { background: var(--error); color: #fff; }",
    ".mem-retry-btn:focus-visible {",
    "  outline: 2px solid var(--error);",
    "  outline-offset: 2px;",
    "}",

    /* --- Refresh Button --- */
    ".mem-refresh-btn {",
    "  background: var(--bg-inset);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-sm);",
    "  color: var(--text-secondary);",
    "  font-size: 11px;",
    "  min-height: 36px;",
    "  display: inline-flex;",
    "  align-items: center;",
    "  padding: 3px 8px;",
    "  cursor: pointer;",
    "  font-family: var(--font-sans);",
    "  transition: all 0.15s ease;",
    "}",
    ".mem-refresh-btn:hover {",
    "  background: var(--bg-secondary);",
    "  color: var(--text-primary);",
    "  border-color: var(--accent);",
    "}",
    ".mem-refresh-btn:focus-visible {",
    "  outline: 2px solid var(--accent);",
    "  outline-offset: 2px;",
    "}",

    /* --- Search result count --- */
    ".mem-search-count {",
    "  font-size: 11px;",
    "  color: var(--text-tertiary);",
    "  margin-bottom: 8px;",
    "  font-family: var(--font-mono);",
    "}"
  ].join("\n");
  document.head.appendChild(style);
}

/* =====================================================================
   API Helpers
   ===================================================================== */
function _memFetchStats(callback) {
  fetch("/api/memory/stats")
    .then(function(response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function(data) { callback(null, data); })
    .catch(function(err) { callback(err, null); });
}

function _memFetchItems(offset, limit, callback) {
  var url = "/api/memory/items?limit=" + limit + "&offset=" + offset;
  if (_memState.activeDomainFilter) {
    url += "&domain=" + encodeURIComponent(_memState.activeDomainFilter);
  }
  fetch(url)
    .then(function(response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function(data) { callback(null, data); })
    .catch(function(err) { callback(err, null); });
}

function _memSearchItems(query, limit, callback) {
  var url = "/api/memory/search?q=" + encodeURIComponent(query) + "&limit=" + (limit || 20);
  fetch(url)
    .then(function(response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function(data) { callback(null, data); })
    .catch(function(err) { callback(err, null); });
}

function _memDeleteItem(itemId, callback) {
  fetch("/api/memory/items/" + encodeURIComponent(itemId), { method: "DELETE" })
    .then(function(response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function(data) { callback(null, data); })
    .catch(function(err) { callback(err, null); });
}

/* =====================================================================
   Data Loading Orchestrator
   ===================================================================== */
function _memLoadAll() {
  _memState.loading = true;
  _memState.error = null;
  _memRender();

  _memFetchStats(function(err, data) {
    if (err) {
      _memState.loading = false;
      _memState.error = "Failed to load memory stats: " + (err.message || String(err));
      _memRender();
      return;
    }
    _memState.stats = data;
    _memState.bubbleData = _memBuildBubbleData(data.top_domains || []);
    _memState.timelineSessions = [];

    /* Now fetch initial items */
    _memState.itemsOffset = 0;
    _memFetchItems(0, _memState.itemsLimit, function(err2, itemData) {
      _memState.loading = false;
      if (err2) {
        _memState.error = "Failed to load memory items: " + (err2.message || String(err2));
        _memRender();
        return;
      }
      _memState.items = itemData.items || [];
      _memState.itemsTotal = itemData.total || 0;
      _memState.itemsOffset = (itemData.items || []).length;

      /* Parse timeline data from vector_ids */
      _memBuildTimeline(_memState.items);

      _memState.error = null;
      _memRender();
    });
  });
}

/* =====================================================================
   Build Bubble Data from Domain Stats
   ===================================================================== */
function _memBuildBubbleData(topDomains) {
  if (!topDomains || !topDomains.length) return [];
  var maxCount = 0;
  var i;
  for (i = 0; i < topDomains.length; i++) {
    if (topDomains[i].count > maxCount) maxCount = topDomains[i].count;
  }
  if (maxCount === 0) return [];

  var bubbles = [];
  for (i = 0; i < topDomains.length; i++) {
    var d = topDomains[i];
    var ratio = d.count / maxCount;
    /* Radius between 20 and 55, proportional to sqrt(count) for area-proportional sizing */
    var minR = 20;
    var maxR = 55;
    var r = minR + (maxR - minR) * Math.sqrt(ratio);
    bubbles.push({
      domain: d.domain,
      count: d.count,
      radius: r,
      avgTier: d.avg_tier || null
    });
  }
  return bubbles;
}

/* =====================================================================
   Build Timeline from Items
   ===================================================================== */
function _memBuildTimeline(items) {
  /*
   * vector_id patterns may contain timestamps or session identifiers.
   * We group by the date portion if present, or by vector_id prefix.
   * Heuristic: extract YYYY-MM-DD or YYYYMMDD from vector_id,
   * or if not present, use a simple prefix grouping.
   */
  var sessions = {};
  var dateRegex = /(\d{4}[-_]?\d{2}[-_]?\d{2})/;
  var i;
  for (i = 0; i < items.length; i++) {
    var vid = items[i].vector_id || "";
    var match = dateRegex.exec(vid);
    var key;
    if (match) {
      key = match[1].replace(/_/g, "-");
    } else if (vid.length > 6) {
      /* Use first 8 chars as a session bucket */
      key = vid.substring(0, 8);
    } else {
      key = vid || "unknown";
    }
    if (!sessions[key]) {
      sessions[key] = { label: key, count: 0 };
    }
    sessions[key].count += 1;
  }

  /* Convert to sorted array */
  var sessionArr = [];
  var keys = Object.keys(sessions);
  for (i = 0; i < keys.length; i++) {
    sessionArr.push(sessions[keys[i]]);
  }
  sessionArr.sort(function(a, b) {
    if (a.label < b.label) return -1;
    if (a.label > b.label) return 1;
    return 0;
  });
  _memState.timelineSessions = sessionArr;
}

/* =====================================================================
   Domain Color by Tier
   ===================================================================== */
function _memTierColor(tier) {
  if (!tier) return "var(--accent)";
  var t = String(tier).toUpperCase();
  if (t === "GOLD") return "var(--gold)";
  if (t === "SILVER") return "var(--silver)";
  if (t === "BRONZE") return "var(--bronze)";
  return "var(--accent)";
}

function _memTierBg(tier) {
  if (!tier) return "rgba(56,189,248,0.25)";
  var t = String(tier).toUpperCase();
  if (t === "GOLD") return "rgba(245,158,11,0.25)";
  if (t === "SILVER") return "rgba(148,163,184,0.25)";
  if (t === "BRONZE") return "rgba(217,119,6,0.25)";
  return "rgba(56,189,248,0.25)";
}

/* =====================================================================
   Main Render
   ===================================================================== */
function _memRender() {
  var container = document.getElementById(_memState.containerId);
  if (!container) return;

  var html = '<div class="mem-dashboard">';

  /* ---------- Loading State ---------- */
  if (_memState.loading) {
    html += '<div class="mem-loading"><div class="mem-spinner"></div><span>Loading memory data...</span></div>';
    html += '</div>';
    container.innerHTML = html;
    return;
  }

  /* ---------- Error State ---------- */
  if (_memState.error) {
    html += '<div class="mem-error">';
    html += '<span>' + esc(_memState.error) + '</span>';
    html += '<button class="mem-retry-btn" onclick="_memLoadAll()" aria-label="Retry loading memory data">Retry</button>';
    html += '</div>';
    html += '</div>';
    container.innerHTML = html;
    return;
  }

  /* ---------- Empty State (no stats) ---------- */
  if (!_memState.stats) {
    html += '<div class="mem-empty-state">';
    html += '<div class="mem-empty-icon">&#128218;</div>';
    html += '<div>No memory data available</div>';
    html += '<div style="font-size:11px;color:var(--text-tertiary)">Run a research query to populate the knowledge memory</div>';
    html += '</div>';
    html += '</div>';
    container.innerHTML = html;
    return;
  }

  /* ---------- Stats Bar ---------- */
  html += _memRenderStatsBar();

  /* ---------- Two-Column Layout ---------- */
  html += '<div class="mem-columns">';
  html += _memRenderBubblePanel();
  html += _memRenderListPanel();
  html += '</div>';

  /* ---------- Timeline Section ---------- */
  html += _memRenderTimeline();

  html += '</div>';
  container.innerHTML = html;

  /* Post-render: draw the SVG bubble chart */
  _memDrawBubbles();

  /* Post-render: attach search input listener */
  var searchInput = document.getElementById("mem-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", _memOnSearchInput);
    /* Restore query value */
    if (_memState.searchQuery) {
      searchInput.value = _memState.searchQuery;
    }
  }
}

/* =====================================================================
   Render: Stats Bar
   ===================================================================== */
function _memRenderStatsBar() {
  var stats = _memState.stats;
  var byTier = stats.by_tier || {};
  var goldCount = byTier.GOLD || byTier.gold || 0;
  var silverCount = byTier.SILVER || byTier.silver || 0;
  var bronzeCount = byTier.BRONZE || byTier.bronze || 0;
  var isAvailable = stats.available !== false;
  var topDomains = stats.top_domains || [];

  var html = '<div class="mem-stats-bar">';

  /* Total count */
  html += '<div class="mem-stat-total">';
  html += '<div class="mem-stat-total-number" id="mem-total-count">' + esc(String(stats.total_items || 0)) + '</div>';
  html += '<div class="mem-stat-total-label">Memory Items</div>';
  html += '</div>';

  /* Middle: tier badges + domain chart */
  html += '<div>';

  /* Tier badges row */
  html += '<div class="mem-tier-row">';
  html += '<div class="mem-tier-badge mem-tier-badge-gold">';
  html += 'GOLD <span class="mem-tier-count">' + esc(String(goldCount)) + '</span>';
  html += '</div>';
  html += '<div class="mem-tier-badge mem-tier-badge-silver">';
  html += 'SILVER <span class="mem-tier-count">' + esc(String(silverCount)) + '</span>';
  html += '</div>';
  html += '<div class="mem-tier-badge mem-tier-badge-bronze">';
  html += 'BRONZE <span class="mem-tier-count">' + esc(String(bronzeCount)) + '</span>';
  html += '</div>';
  html += '</div>';

  /* Domain bar chart (top 10) */
  if (topDomains.length > 0) {
    var maxDomainCount = 0;
    var i;
    for (i = 0; i < topDomains.length; i++) {
      if (topDomains[i].count > maxDomainCount) maxDomainCount = topDomains[i].count;
    }
    html += '<div class="mem-domain-chart">';
    html += '<div class="mem-domain-chart-title">Top Domains</div>';
    var displayCount = Math.min(topDomains.length, 10);
    for (i = 0; i < displayCount; i++) {
      var dom = topDomains[i];
      var pct = maxDomainCount > 0 ? ((dom.count / maxDomainCount) * 100) : 0;
      html += '<div class="mem-domain-bar-row">';
      html += '<span class="mem-domain-bar-label" title="' + esc(dom.domain) + '">' + esc(dom.domain) + '</span>';
      html += '<div class="mem-domain-bar-track">';
      html += '<div class="mem-domain-bar-fill" style="width:' + pct.toFixed(1) + '%"></div>';
      html += '</div>';
      html += '<span class="mem-domain-bar-count">' + esc(String(dom.count)) + '</span>';
      html += '</div>';
    }
    html += '</div>';
  }

  html += '</div>';

  /* Storage status */
  html += '<div>';
  html += '<div class="mem-storage-indicator">';
  if (isAvailable) {
    html += '<span class="mem-storage-dot mem-storage-dot-online"></span>';
    html += '<span style="color:var(--success)">Online</span>';
  } else {
    html += '<span class="mem-storage-dot mem-storage-dot-offline"></span>';
    html += '<span style="color:var(--error)">Offline</span>';
  }
  html += '</div>';
  html += '<button class="mem-refresh-btn" onclick="_memLoadAll()" style="margin-top:8px" aria-label="Refresh memory data">Refresh</button>';
  html += '</div>';

  html += '</div>';
  return html;
}

/* =====================================================================
   Render: Bubble Panel (Left Column)
   ===================================================================== */
function _memRenderBubblePanel() {
  var html = '<div class="mem-bubble-panel">';
  html += '<div class="mem-panel-header">';
  html += '<span class="mem-panel-title">Knowledge Clusters</span>';
  html += '</div>';

  /* Active filter bar */
  if (_memState.activeDomainFilter) {
    html += '<div class="mem-filter-bar">';
    html += '<span>Filtered by: ' + esc(_memState.activeDomainFilter) + '</span>';
    html += '<button class="mem-filter-clear" onclick="_memClearDomainFilter()" aria-label="Clear domain filter">Clear filter</button>';
    html += '</div>';
  }

  if (!_memState.bubbleData || _memState.bubbleData.length === 0) {
    html += '<div class="mem-empty-state">';
    html += '<div class="mem-empty-icon">&#128300;</div>';
    html += '<div>No domain clusters yet</div>';
    html += '<div style="font-size:11px">Knowledge clusters will appear as memory items are added</div>';
    html += '</div>';
  } else {
    html += '<div class="mem-bubble-container" id="mem-bubble-container">';
    html += '<svg class="mem-bubble-svg" id="mem-bubble-svg" role="img" aria-label="Knowledge cluster bubble chart"></svg>';
    html += '</div>';
  }

  html += '</div>';
  return html;
}

/* =====================================================================
   Render: List Panel (Right Column)
   ===================================================================== */
function _memRenderListPanel() {
  var html = '<div class="mem-list-panel">';

  /* Search input */
  html += '<div class="mem-search-wrap">';
  html += '<span class="mem-search-icon">&#128269;</span>';
  html += '<input class="mem-search-input" id="mem-search-input" type="text"';
  html += ' placeholder="Search memory items..." autocomplete="off" spellcheck="false"';
  html += ' aria-label="Search memory items">';
  html += '</div>';

  /* Search result count */
  if (_memState.searchQuery && _memState.searchResults !== null) {
    var resultCount = _memState.searchResults ? _memState.searchResults.length : 0;
    html += '<div class="mem-search-count">' + esc(String(resultCount)) + ' result' + (resultCount !== 1 ? 's' : '') + ' for "' + esc(_memState.searchQuery) + '"</div>';
  }

  /* Item list */
  html += '<div class="mem-item-list" id="mem-item-list">';
  html += _memRenderItems();
  html += '</div>';

  /* Load More button (only if not searching and more items exist) */
  if (!_memState.searchQuery && _memState.itemsOffset < _memState.itemsTotal) {
    html += '<button class="mem-load-more" id="mem-load-more-btn" onclick="_memLoadMore()" aria-label="Load more memory items">';
    html += 'Load More (' + esc(String(_memState.itemsOffset)) + ' of ' + esc(String(_memState.itemsTotal)) + ')';
    html += '</button>';
  }

  html += '</div>';
  return html;
}

/* =====================================================================
   Render: Individual Items
   ===================================================================== */
function _memRenderItems() {
  var items;
  if (_memState.searchQuery && _memState.searchResults !== null) {
    items = _memState.searchResults;
  } else {
    items = _memState.items;
  }

  if (!items || items.length === 0) {
    if (_memState.searchQuery) {
      return '<div class="mem-empty-state" style="padding:20px">' +
        '<div style="font-size:13px;color:var(--text-tertiary)">No results found</div>' +
        '</div>';
    }
    return '<div class="mem-empty-state" style="padding:20px">' +
      '<div class="mem-empty-icon">&#128203;</div>' +
      '<div>No memory items yet</div>' +
      '</div>';
  }

  var html = '';
  var i;
  for (i = 0; i < items.length; i++) {
    html += _memRenderItemCard(items[i]);
  }
  return html;
}

function _memRenderItemCard(item) {
  var tier = (item.quality_tier || item.tier || "").toUpperCase();
  var tierClass = tier === "GOLD" ? "mem-item-tier-gold"
                : tier === "SILVER" ? "mem-item-tier-silver"
                : "mem-item-tier-bronze";
  var tierLabel = tier || "BRONZE";

  /* Faithfulness display */
  var faithVal = item.faithfulness;
  var faithHtml = "";
  if (faithVal !== undefined && faithVal !== null) {
    var faithPct = faithVal <= 1 ? (faithVal * 100).toFixed(0) : Number(faithVal).toFixed(0);
    var faithClass = "mem-item-faith";
    if (Number(faithPct) >= 80) faithClass += " mem-item-faith-good";
    else if (Number(faithPct) >= 60) faithClass += " mem-item-faith-warn";
    else faithClass += " mem-item-faith-bad";
    faithHtml = '<span class="' + faithClass + '">' + esc(faithPct) + '%</span>';
  }

  /* Domain */
  var domain = item.domain || "";
  if (!domain && item.source) {
    try { domain = new URL(item.source).hostname.replace("www.", ""); } catch(e) { domain = ""; }
  }

  var html = '<div class="mem-item-card">';

  /* Statement (2 lines truncated) */
  html += '<div class="mem-item-statement">' + esc(item.statement || "") + '</div>';

  /* Meta row */
  html += '<div class="mem-item-meta">';
  if (domain) {
    html += '<span class="mem-item-domain" title="' + esc(domain) + '">' + esc(truncStr(domain, 25)) + '</span>';
  }
  html += '<span class="mem-item-tier ' + tierClass + '">' + esc(tierLabel) + '</span>';
  if (faithHtml) html += faithHtml;
  if (item.vector_id) {
    html += '<span class="mem-item-vector" title="' + esc(item.vector_id) + '">' + esc(truncStr(item.vector_id, 12)) + '</span>';
  }

  /* Delete button */
  html += '<button class="mem-item-delete" onclick="_memConfirmDelete(\'' + esc(String(item.id || "")) + '\')" aria-label="Delete memory item" title="Delete item">';
  html += '&#128465;';
  html += '</button>';

  html += '</div>'; /* .mem-item-meta */
  html += '</div>'; /* .mem-item-card */
  return html;
}

/* =====================================================================
   Render: Timeline
   ===================================================================== */
function _memRenderTimeline() {
  var sessions = _memState.timelineSessions;
  var html = '<div class="mem-timeline-section">';

  /* Toggle header */
  html += '<div class="mem-timeline-toggle" onclick="_memToggleTimeline()" role="button" tabindex="0"';
  html += ' onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();_memToggleTimeline();}"';
  html += ' aria-expanded="' + (_memState.timelineOpen ? 'true' : 'false') + '">';
  html += '<span class="mem-timeline-toggle-title">Knowledge Timeline</span>';
  html += '<span class="mem-timeline-chevron' + (_memState.timelineOpen ? ' mem-timeline-chevron-open' : '') + '" id="mem-timeline-chevron">&#9654;</span>';
  html += '</div>';

  /* Body */
  html += '<div class="mem-timeline-body' + (_memState.timelineOpen ? '' : ' mem-timeline-hidden') + '" id="mem-timeline-body">';

  if (!sessions || sessions.length === 0) {
    html += '<div class="mem-empty-state" style="padding:16px">';
    html += '<div style="font-size:12px;color:var(--text-tertiary)">No timeline data available</div>';
    html += '</div>';
  } else {
    /* Find max for scaling */
    var maxSessionCount = 0;
    var i;
    for (i = 0; i < sessions.length; i++) {
      if (sessions[i].count > maxSessionCount) maxSessionCount = sessions[i].count;
    }

    html += '<div class="mem-timeline-chart" id="mem-timeline-chart">';
    var displaySessions = sessions.slice(-30); /* show last 30 sessions max */
    for (i = 0; i < displaySessions.length; i++) {
      var sess = displaySessions[i];
      var barHeight = maxSessionCount > 0 ? Math.max(4, (sess.count / maxSessionCount) * 100) : 4;
      html += '<div class="mem-timeline-bar-wrap">';
      html += '<div class="mem-timeline-bar-count">' + esc(String(sess.count)) + '</div>';
      html += '<div class="mem-timeline-bar" style="height:' + barHeight.toFixed(0) + 'px" title="' + esc(sess.label) + ': ' + esc(String(sess.count)) + ' items"></div>';
      html += '<div class="mem-timeline-bar-label">' + esc(truncStr(sess.label, 10)) + '</div>';
      html += '</div>';
    }
    html += '</div>';
  }

  html += '</div>';
  html += '</div>';
  return html;
}

/* =====================================================================
   Draw Bubble Chart (SVG, called after DOM render)
   ===================================================================== */
function _memDrawBubbles() {
  var svg = document.getElementById("mem-bubble-svg");
  var containerEl = document.getElementById("mem-bubble-container");
  if (!svg || !containerEl || !_memState.bubbleData.length) return;

  var rect = containerEl.getBoundingClientRect();
  var svgW = Math.max(rect.width, 200);
  var svgH = Math.max(rect.height, 280);

  svg.setAttribute("viewBox", "0 0 " + svgW + " " + svgH);
  svg.setAttribute("width", svgW);
  svg.setAttribute("height", svgH);

  var bubbles = _memState.bubbleData;
  var positions = _memLayoutBubbles(bubbles, svgW, svgH);

  var svgHtml = '';
  var i;
  for (i = 0; i < bubbles.length; i++) {
    var b = bubbles[i];
    var pos = positions[i];
    var fillColor = _memTierBg(b.avgTier);
    var strokeColor = _memTierColor(b.avgTier);
    var isActive = _memState.activeDomainFilter === b.domain;

    svgHtml += '<g class="mem-bubble" onclick="_memFilterByDomain(\'' + esc(b.domain) + '\')" role="button" tabindex="0"';
    svgHtml += ' onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();_memFilterByDomain(\'' + esc(b.domain) + '\');}"';
    svgHtml += ' aria-label="' + esc(b.domain) + ': ' + b.count + ' items">';

    svgHtml += '<circle cx="' + pos.x.toFixed(1) + '" cy="' + pos.y.toFixed(1) + '" r="' + b.radius.toFixed(1) + '"';
    svgHtml += ' fill="' + fillColor + '"';
    svgHtml += ' stroke="' + strokeColor + '"';
    svgHtml += ' stroke-width="' + (isActive ? '3' : '1.5') + '"';
    if (isActive) svgHtml += ' stroke-dasharray="none" opacity="1"';
    svgHtml += '/>';

    /* Domain label (truncate to fit bubble) */
    var maxChars = Math.max(3, Math.floor(b.radius / 4.5));
    var labelText = b.domain.length > maxChars ? b.domain.substring(0, maxChars) + ".." : b.domain;
    svgHtml += '<text class="mem-bubble-label" x="' + pos.x.toFixed(1) + '" y="' + (pos.y - 6).toFixed(1) + '">' + esc(labelText) + '</text>';
    svgHtml += '<text class="mem-bubble-count" x="' + pos.x.toFixed(1) + '" y="' + (pos.y + 8).toFixed(1) + '">' + esc(String(b.count)) + '</text>';

    svgHtml += '</g>';
  }

  svg.innerHTML = svgHtml;
}

/* =====================================================================
   Bubble Layout — Simple Circle Packing
   ===================================================================== */
function _memLayoutBubbles(bubbles, width, height) {
  /*
   * Simple force-directed circle packing.
   * We place bubbles roughly in the center and then nudge them apart
   * so they do not overlap.
   */
  var positions = [];
  var i, j, iteration;
  var cx = width / 2;
  var cy = height / 2;

  /* Initial placement: spiral outward from center */
  var angleStep = 2.399; /* golden angle in radians */
  var spiralScale = 8;
  for (i = 0; i < bubbles.length; i++) {
    var angle = i * angleStep;
    var dist = spiralScale * Math.sqrt(i);
    positions.push({
      x: cx + dist * Math.cos(angle),
      y: cy + dist * Math.sin(angle)
    });
  }

  /* Iterative separation (simple repulsion) */
  for (iteration = 0; iteration < 80; iteration++) {
    for (i = 0; i < bubbles.length; i++) {
      for (j = i + 1; j < bubbles.length; j++) {
        var dx = positions[j].x - positions[i].x;
        var dy = positions[j].y - positions[i].y;
        var distSq = dx * dx + dy * dy;
        var minDist = bubbles[i].radius + bubbles[j].radius + 4;
        if (distSq < minDist * minDist) {
          var dist2 = Math.sqrt(distSq) || 1;
          var overlap = (minDist - dist2) / 2;
          var nx = dx / dist2;
          var ny = dy / dist2;
          positions[i].x -= nx * overlap * 0.5;
          positions[i].y -= ny * overlap * 0.5;
          positions[j].x += nx * overlap * 0.5;
          positions[j].y += ny * overlap * 0.5;
        }
      }
      /* Gravity toward center */
      positions[i].x += (cx - positions[i].x) * 0.01;
      positions[i].y += (cy - positions[i].y) * 0.01;
    }
  }

  /* Clamp within bounds */
  for (i = 0; i < bubbles.length; i++) {
    var r = bubbles[i].radius;
    if (positions[i].x - r < 0) positions[i].x = r + 2;
    if (positions[i].x + r > width) positions[i].x = width - r - 2;
    if (positions[i].y - r < 0) positions[i].y = r + 2;
    if (positions[i].y + r > height) positions[i].y = height - r - 2;
  }

  return positions;
}

/* =====================================================================
   Event Handlers
   ===================================================================== */

/* --- Search Input (debounced 300ms) --- */
function _memOnSearchInput() {
  var input = document.getElementById("mem-search-input");
  if (!input) return;
  var query = input.value.trim();

  if (_memState.debounceTimer) {
    clearTimeout(_memState.debounceTimer);
    _memState.debounceTimer = null;
  }

  if (!query) {
    _memState.searchQuery = "";
    _memState.searchResults = null;
    _memRenderItemList();
    return;
  }

  _memState.debounceTimer = setTimeout(function() {
    _memState.searchQuery = query;
    _memSearchItems(query, 20, function(err, data) {
      if (err) {
        if (typeof showToast === "function") {
          showToast("Search failed: " + (err.message || String(err)), "error");
        }
        return;
      }
      _memState.searchResults = data.results || [];
      _memRenderItemList();
    });
  }, 300);
}

/* --- Partial re-render of just the item list (avoids full re-render) --- */
function _memRenderItemList() {
  var listEl = document.getElementById("mem-item-list");
  if (listEl) {
    listEl.innerHTML = _memRenderItems();
  }

  /* Update search count text */
  var container = document.getElementById(_memState.containerId);
  if (!container) return;

  /* Update or create the search count element */
  var existingCount = container.querySelector(".mem-search-count");
  if (_memState.searchQuery && _memState.searchResults !== null) {
    var resultCount = _memState.searchResults ? _memState.searchResults.length : 0;
    var countHtml = esc(String(resultCount)) + ' result' + (resultCount !== 1 ? 's' : '') + ' for "' + esc(_memState.searchQuery) + '"';
    if (existingCount) {
      existingCount.innerHTML = countHtml;
      existingCount.style.display = "";
    }
  } else {
    if (existingCount) {
      existingCount.style.display = "none";
    }
  }

  /* Show/hide Load More */
  var loadMoreBtn = document.getElementById("mem-load-more-btn");
  if (loadMoreBtn) {
    if (_memState.searchQuery) {
      loadMoreBtn.style.display = "none";
    } else {
      loadMoreBtn.style.display = _memState.itemsOffset < _memState.itemsTotal ? "" : "none";
      loadMoreBtn.textContent = 'Load More (' + _memState.itemsOffset + ' of ' + _memState.itemsTotal + ')';
    }
  }
}

/* --- Domain Bubble Click --- */
function _memFilterByDomain(domain) {
  if (_memState.activeDomainFilter === domain) {
    /* Toggle off if already active */
    _memClearDomainFilter();
    return;
  }
  _memState.activeDomainFilter = domain;
  _memState.items = [];
  _memState.itemsOffset = 0;
  _memState.searchQuery = "";
  _memState.searchResults = null;

  _memFetchItems(0, _memState.itemsLimit, function(err, data) {
    if (err) {
      if (typeof showToast === "function") {
        showToast("Filter failed: " + (err.message || String(err)), "error");
      }
      return;
    }
    _memState.items = data.items || [];
    _memState.itemsTotal = data.total || 0;
    _memState.itemsOffset = (data.items || []).length;
    _memRender();
  });
}

function _memClearDomainFilter() {
  _memState.activeDomainFilter = null;
  _memState.items = [];
  _memState.itemsOffset = 0;

  _memFetchItems(0, _memState.itemsLimit, function(err, data) {
    if (err) {
      if (typeof showToast === "function") {
        showToast("Failed to reload items: " + (err.message || String(err)), "error");
      }
      return;
    }
    _memState.items = data.items || [];
    _memState.itemsTotal = data.total || 0;
    _memState.itemsOffset = (data.items || []).length;
    _memRender();
  });
}

/* --- Load More --- */
function _memLoadMore() {
  var btn = document.getElementById("mem-load-more-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Loading...";
  }

  _memFetchItems(_memState.itemsOffset, _memState.itemsLimit, function(err, data) {
    if (err) {
      if (typeof showToast === "function") {
        showToast("Failed to load more items: " + (err.message || String(err)), "error");
      }
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Load More (' + _memState.itemsOffset + ' of ' + _memState.itemsTotal + ')';
      }
      return;
    }
    var newItems = data.items || [];
    var i;
    for (i = 0; i < newItems.length; i++) {
      _memState.items.push(newItems[i]);
    }
    _memState.itemsTotal = data.total || _memState.itemsTotal;
    _memState.itemsOffset = _memState.items.length;

    /* Rebuild timeline with new items */
    _memBuildTimeline(_memState.items);

    _memRender();
  });
}

/* --- Delete Item --- */
function _memConfirmDelete(itemId) {
  if (!itemId) return;
  var confirmed = confirm("Delete this memory item? This action cannot be undone.");
  if (!confirmed) return;

  _memDeleteItem(itemId, function(err, data) {
    if (err) {
      if (typeof showToast === "function") {
        showToast("Delete failed: " + (err.message || String(err)), "error");
      }
      return;
    }

    if (typeof showToast === "function") {
      showToast("Memory item deleted", "success");
    }

    /* Remove from local state */
    _memState.items = _memState.items.filter(function(item) {
      return String(item.id) !== String(itemId);
    });
    if (_memState.searchResults) {
      _memState.searchResults = _memState.searchResults.filter(function(item) {
        return String(item.id) !== String(itemId);
      });
    }
    _memState.itemsTotal = Math.max(0, _memState.itemsTotal - 1);
    _memState.itemsOffset = Math.max(0, _memState.itemsOffset - 1);

    /* Refresh stats (item counts, tiers, domains changed) */
    _memFetchStats(function(statErr, statData) {
      if (!statErr && statData) {
        _memState.stats = statData;
        _memState.bubbleData = _memBuildBubbleData(statData.top_domains || []);
      }
      /* Rebuild timeline */
      _memBuildTimeline(_memState.items);
      _memRender();
    });
  });
}

/* --- Toggle Timeline --- */
function _memToggleTimeline() {
  _memState.timelineOpen = !_memState.timelineOpen;
  var body = document.getElementById("mem-timeline-body");
  var chevron = document.getElementById("mem-timeline-chevron");
  if (body) {
    if (_memState.timelineOpen) {
      body.classList.remove("mem-timeline-hidden");
    } else {
      body.classList.add("mem-timeline-hidden");
    }
  }
  if (chevron) {
    if (_memState.timelineOpen) {
      chevron.classList.add("mem-timeline-chevron-open");
    } else {
      chevron.classList.remove("mem-timeline-chevron-open");
    }
  }
  /* Update aria-expanded */
  var toggle = body ? body.previousElementSibling : null;
  if (toggle) {
    toggle.setAttribute("aria-expanded", _memState.timelineOpen ? "true" : "false");
  }
}

/* =====================================================================
   Public API: renderMemoryDashboard(containerId)
   ===================================================================== */
function renderMemoryDashboard(containerId) {
  _memInjectStyles();
  _memState.containerId = containerId;

  /* Verify container exists */
  var container = document.getElementById(containerId);
  if (!container) {
    console.warn("renderMemoryDashboard: container #" + containerId + " not found");
    return;
  }

  /* Show loading state immediately */
  container.innerHTML = '<div class="mem-dashboard"><div class="mem-loading"><div class="mem-spinner"></div><span>Loading memory data...</span></div></div>';

  /* Load data */
  _memLoadAll();
}
