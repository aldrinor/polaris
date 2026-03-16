/* =====================================================================
   checkpoint_timeline.js — Checkpoint Timeline UI Component
   POLARIS Live Dashboard

   Provides:
     - initCheckpointTimeline(containerId) — create timeline in container
     - fetchCheckpoints() — load checkpoints for current vector

   Dependencies (from core.js):
     - state.vectorId
     - showToast(msg, type)
     - esc(str)
     - NODE_LABELS, NODE_ICONS

   All DOM elements created dynamically. CSS injected once into <head>.
   ===================================================================== */

/* =====================================================================
   Internal State
   ===================================================================== */
var _ckptState = {
  checkpoints: [],
  loading: false,
  error: null,
  containerId: null,
  drawerOpen: false,
  drawerCheckpoint: null,
  drawerState: null,
  drawerLoading: false,
  stateExpanded: false
};

/* =====================================================================
   CSS Injection (runs once)
   ===================================================================== */
function _ckptInjectStyles() {
  if (document.getElementById("ckpt-injected-styles")) return;
  var style = document.createElement("style");
  style.id = "ckpt-injected-styles";
  style.textContent = [
    /* --- Timeline Container --- */
    ".ckpt-panel {",
    "  background: var(--bg-card);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-lg);",
    "  padding: var(--md);",
    "  box-shadow: var(--shadow-sm);",
    "  margin-top: var(--gap-cards);",
    "}",
    ".ckpt-panel-header {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: space-between;",
    "  margin-bottom: var(--sm);",
    "}",
    ".ckpt-panel-title {",
    "  font-size: 12px;",
    "  font-weight: 700;",
    "  color: var(--text-secondary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 1px;",
    "}",
    ".ckpt-refresh-btn {",
    "  background: var(--bg-inset);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-sm);",
    "  color: var(--text-secondary);",
    "  font-size: 11px;",
    "  padding: 3px 8px;",
    "  min-height: var(--touch-min, 44px);",
    "  cursor: pointer;",
    "  font-family: var(--font-sans);",
    "  transition: all var(--duration-fast) var(--ease);",
    "}",
    ".ckpt-refresh-btn:hover {",
    "  background: var(--bg-hover);",
    "  color: var(--text-primary);",
    "  border-color: var(--border-active);",
    "}",
    ".ckpt-refresh-btn:focus-visible {",
    "  outline: 2px solid var(--accent);",
    "  outline-offset: 2px;",
    "}",

    /* --- Timeline Track --- */
    ".ckpt-timeline {",
    "  position: relative;",
    "  display: flex;",
    "  align-items: flex-start;",
    "  gap: 0;",
    "  overflow-x: auto;",
    "  padding: var(--sm) 0 var(--md) 0;",
    "  scrollbar-width: thin;",
    "}",
    ".ckpt-timeline::-webkit-scrollbar { height: 6px; }",
    ".ckpt-timeline::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }",
    ".ckpt-node {",
    "  display: flex;",
    "  flex-direction: column;",
    "  align-items: center;",
    "  min-width: 80px;",
    "  position: relative;",
    "  cursor: pointer;",
    "  flex-shrink: 0;",
    "}",
    ".ckpt-node:focus-visible {",
    "  outline: 2px solid var(--accent);",
    "  outline-offset: 2px;",
    "  border-radius: var(--radius-sm);",
    "}",

    /* --- Connector line between dots --- */
    ".ckpt-connector {",
    "  flex: 1;",
    "  min-width: 24px;",
    "  height: 2px;",
    "  background: var(--border);",
    "  align-self: center;",
    "  margin-top: -20px;",
    "  flex-shrink: 0;",
    "}",
    ".ckpt-connector.ckpt-conn-done { background: var(--success); }",

    /* --- Dot --- */
    ".ckpt-dot {",
    "  width: 16px;",
    "  height: 16px;",
    "  border-radius: 50%;",
    "  border: 2px solid var(--border);",
    "  background: var(--bg-inset);",
    "  transition: all var(--duration-normal) var(--ease);",
    "  position: relative;",
    "  z-index: 1;",
    "}",
    ".ckpt-dot.ckpt-dot-done {",
    "  background: var(--success);",
    "  border-color: var(--success);",
    "  box-shadow: 0 0 6px rgba(16, 185, 129, 0.35);",
    "}",
    ".ckpt-dot.ckpt-dot-current {",
    "  background: var(--accent);",
    "  border-color: var(--accent);",
    "  box-shadow: 0 0 8px var(--accent-glow);",
    "  animation: ckpt-pulse 2s ease-in-out infinite;",
    "}",
    ".ckpt-dot.ckpt-dot-pending {",
    "  background: var(--bg-inset);",
    "  border-color: var(--border);",
    "}",
    ".ckpt-node:hover .ckpt-dot {",
    "  transform: scale(1.25);",
    "  box-shadow: 0 0 10px var(--accent-glow);",
    "}",

    /* --- Node label --- */
    ".ckpt-label {",
    "  font-size: 10px;",
    "  color: var(--text-tertiary);",
    "  margin-top: 6px;",
    "  text-align: center;",
    "  white-space: nowrap;",
    "  font-family: var(--font-sans);",
    "  max-width: 80px;",
    "  overflow: hidden;",
    "  text-overflow: ellipsis;",
    "}",
    ".ckpt-label.ckpt-label-current { color: var(--accent); font-weight: 600; }",
    ".ckpt-label.ckpt-label-done { color: var(--text-secondary); }",
    ".ckpt-iter-badge {",
    "  font-size: 9px;",
    "  color: var(--text-tertiary);",
    "  font-family: var(--font-mono);",
    "  margin-top: 2px;",
    "}",

    /* --- Tooltip --- */
    ".ckpt-tooltip {",
    "  position: absolute;",
    "  bottom: calc(100% + 10px);",
    "  left: 50%;",
    "  transform: translateX(-50%);",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--border-active);",
    "  border-radius: var(--radius);",
    "  padding: 8px 12px;",
    "  font-size: 11px;",
    "  color: var(--text-primary);",
    "  white-space: nowrap;",
    "  pointer-events: none;",
    "  opacity: 0;",
    "  transition: opacity var(--duration-fast) var(--ease);",
    "  z-index: 100;",
    "  box-shadow: var(--shadow-lg);",
    "  font-family: var(--font-sans);",
    "  line-height: 1.5;",
    "}",
    ".ckpt-node:hover .ckpt-tooltip { opacity: 1; }",
    ".ckpt-tooltip-row { display: flex; gap: 8px; justify-content: space-between; }",
    ".ckpt-tooltip-key { color: var(--text-tertiary); }",
    ".ckpt-tooltip-val { color: var(--text-primary); font-family: var(--font-mono); font-weight: 500; }",

    /* --- Pulse animation --- */
    "@keyframes ckpt-pulse {",
    "  0%, 100% { box-shadow: 0 0 4px var(--accent-glow); }",
    "  50% { box-shadow: 0 0 14px var(--accent-glow), 0 0 28px rgba(56, 189, 248, 0.1); }",
    "}",

    /* --- Empty / Loading / Error States --- */
    ".ckpt-empty-state {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  padding: var(--lg);",
    "  color: var(--text-tertiary);",
    "  font-size: 13px;",
    "  text-align: center;",
    "}",
    ".ckpt-loading {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  gap: var(--sm);",
    "  padding: var(--lg);",
    "  color: var(--text-tertiary);",
    "  font-size: 13px;",
    "}",
    ".ckpt-spinner {",
    "  width: 16px;",
    "  height: 16px;",
    "  border: 2px solid var(--border);",
    "  border-top-color: var(--accent);",
    "  border-radius: 50%;",
    "  animation: ckpt-spin 0.7s linear infinite;",
    "}",
    "@keyframes ckpt-spin { to { transform: rotate(360deg); } }",
    ".ckpt-error {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  gap: var(--sm);",
    "  padding: var(--md);",
    "  color: var(--error);",
    "  font-size: 12px;",
    "  text-align: center;",
    "  flex-wrap: wrap;",
    "}",
    ".ckpt-retry-btn {",
    "  background: var(--error-dim);",
    "  border: 1px solid var(--error);",
    "  border-radius: var(--radius-sm);",
    "  color: var(--error);",
    "  font-size: 11px;",
    "  padding: 3px 10px;",
    "  cursor: pointer;",
    "  font-family: var(--font-sans);",
    "  transition: all var(--duration-fast) var(--ease);",
    "}",
    ".ckpt-retry-btn:hover { background: var(--error); color: #fff; }",
    ".ckpt-retry-btn:focus-visible {",
    "  outline: 2px solid var(--error);",
    "  outline-offset: 2px;",
    "}",

    /* --- State Inspector Drawer --- */
    ".ckpt-drawer-overlay {",
    "  position: fixed;",
    "  inset: 0;",
    "  background: rgba(0, 0, 0, 0.45);",
    "  z-index: 9998;",
    "  opacity: 0;",
    "  transition: opacity var(--duration-normal) var(--ease);",
    "  pointer-events: none;",
    "}",
    ".ckpt-drawer-overlay.ckpt-drawer-visible {",
    "  opacity: 1;",
    "  pointer-events: auto;",
    "}",
    ".ckpt-drawer {",
    "  position: fixed;",
    "  top: 0;",
    "  right: 0;",
    "  bottom: 0;",
    "  width: min(520px, 90vw);",
    "  background: var(--bg-secondary);",
    "  border-left: 1px solid var(--border);",
    "  z-index: 9999;",
    "  transform: translateX(100%);",
    "  transition: transform var(--duration-slow) var(--ease);",
    "  display: flex;",
    "  flex-direction: column;",
    "  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.3);",
    "}",
    ".ckpt-drawer.ckpt-drawer-open { transform: translateX(0); }",

    /* Drawer header */
    ".ckpt-drawer-header {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: space-between;",
    "  padding: var(--md) var(--lg);",
    "  border-bottom: 1px solid var(--border);",
    "  background: var(--bg-card);",
    "  flex-shrink: 0;",
    "}",
    ".ckpt-drawer-title {",
    "  font-size: 14px;",
    "  font-weight: 700;",
    "  color: var(--text-primary);",
    "  display: flex;",
    "  align-items: center;",
    "  gap: var(--sm);",
    "}",
    ".ckpt-drawer-close {",
    "  background: transparent;",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-sm);",
    "  color: var(--text-secondary);",
    "  font-size: 18px;",
    "  width: 32px;",
    "  height: 32px;",
    "  cursor: pointer;",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  transition: all var(--duration-fast) var(--ease);",
    "  font-family: var(--font-sans);",
    "  line-height: 1;",
    "}",
    ".ckpt-drawer-close:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border-active); }",
    ".ckpt-drawer-close:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }",

    /* Drawer body (scrollable) */
    ".ckpt-drawer-body {",
    "  flex: 1;",
    "  overflow-y: auto;",
    "  padding: var(--lg);",
    "}",

    /* Drawer section cards */
    ".ckpt-drawer-section {",
    "  background: var(--bg-card);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius);",
    "  padding: var(--md);",
    "  margin-bottom: var(--gap-cards);",
    "}",
    ".ckpt-drawer-section-title {",
    "  font-size: 11px;",
    "  font-weight: 700;",
    "  color: var(--text-secondary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 0.8px;",
    "  margin-bottom: var(--sm);",
    "}",

    /* Metadata rows */
    ".ckpt-meta-grid {",
    "  display: grid;",
    "  grid-template-columns: 1fr 1fr;",
    "  gap: 6px var(--md);",
    "}",
    ".ckpt-meta-item {",
    "  display: flex;",
    "  flex-direction: column;",
    "  gap: 1px;",
    "}",
    ".ckpt-meta-key {",
    "  font-size: 10px;",
    "  color: var(--text-tertiary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 0.5px;",
    "}",
    ".ckpt-meta-val {",
    "  font-size: 13px;",
    "  color: var(--text-primary);",
    "  font-family: var(--font-mono);",
    "  font-weight: 500;",
    "}",

    /* Metrics row */
    ".ckpt-metrics-row {",
    "  display: grid;",
    "  grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));",
    "  gap: var(--sm);",
    "}",
    ".ckpt-metric-item {",
    "  background: var(--bg-inset);",
    "  border-radius: var(--radius-sm);",
    "  padding: 8px;",
    "  text-align: center;",
    "}",
    ".ckpt-metric-val {",
    "  font-size: 16px;",
    "  font-weight: 700;",
    "  color: var(--text-primary);",
    "  font-family: var(--font-mono);",
    "}",
    ".ckpt-metric-label {",
    "  font-size: 9px;",
    "  color: var(--text-tertiary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 0.5px;",
    "  margin-top: 2px;",
    "}",

    /* Rewind button */
    ".ckpt-rewind-btn {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  gap: var(--sm);",
    "  width: 100%;",
    "  padding: 10px var(--md);",
    "  background: var(--warning-dim);",
    "  border: 1px solid var(--warning);",
    "  border-radius: var(--radius);",
    "  color: var(--warning);",
    "  font-size: 13px;",
    "  font-weight: 600;",
    "  cursor: pointer;",
    "  font-family: var(--font-sans);",
    "  transition: all var(--duration-fast) var(--ease);",
    "  margin-bottom: var(--gap-cards);",
    "}",
    ".ckpt-rewind-btn:hover { background: var(--warning); color: #fff; }",
    ".ckpt-rewind-btn:disabled {",
    "  opacity: 0.5;",
    "  cursor: not-allowed;",
    "}",
    ".ckpt-rewind-btn:focus-visible {",
    "  outline: 2px solid var(--warning);",
    "  outline-offset: 2px;",
    "}",

    /* State patch textarea (A7.4) */
    ".ckpt-state-patch {",
    "  width: 100%;",
    "  font-family: 'Fira Code', 'SF Mono', monospace;",
    "  font-size: 11px;",
    "  background: var(--bg-inset);",
    "  color: var(--text-primary);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-sm);",
    "  padding: 8px;",
    "  resize: vertical;",
    "  min-height: 60px;",
    "  max-height: 200px;",
    "}",
    ".ckpt-state-patch:focus {",
    "  border-color: var(--warning);",
    "  outline: none;",
    "}",

    /* State JSON viewer */
    ".ckpt-json-toggle {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: space-between;",
    "  cursor: pointer;",
    "  user-select: none;",
    "}",
    ".ckpt-json-toggle:hover { color: var(--text-primary); }",
    ".ckpt-json-chevron {",
    "  font-size: 10px;",
    "  color: var(--text-tertiary);",
    "  transition: transform var(--duration-fast) var(--ease);",
    "}",
    ".ckpt-json-chevron.ckpt-json-expanded { transform: rotate(90deg); }",
    ".ckpt-json-preview {",
    "  font-size: 11px;",
    "  font-family: var(--font-mono);",
    "  color: var(--text-tertiary);",
    "  margin-top: var(--xs);",
    "  white-space: nowrap;",
    "  overflow: hidden;",
    "  text-overflow: ellipsis;",
    "  max-width: 100%;",
    "}",
    ".ckpt-json-full {",
    "  margin-top: var(--sm);",
    "  max-height: 400px;",
    "  overflow: auto;",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-sm);",
    "  background: var(--bg-inset);",
    "}",
    ".ckpt-json-full pre {",
    "  margin: 0;",
    "  padding: var(--sm);",
    "  font-size: 11px;",
    "  font-family: var(--font-mono);",
    "  color: var(--text-secondary);",
    "  white-space: pre-wrap;",
    "  word-break: break-word;",
    "  line-height: 1.5;",
    "}",
    ".ckpt-json-hidden { display: none; }",

    /* Drawer loading */
    ".ckpt-drawer-loading {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  gap: var(--sm);",
    "  padding: var(--xxl);",
    "  color: var(--text-tertiary);",
    "  font-size: 13px;",
    "}",

    /* Node badge in drawer */
    ".ckpt-node-badge {",
    "  display: inline-flex;",
    "  align-items: center;",
    "  gap: 4px;",
    "  background: var(--accent-dim);",
    "  color: var(--accent);",
    "  font-size: 12px;",
    "  font-weight: 600;",
    "  padding: 2px 8px;",
    "  border-radius: var(--radius-sm);",
    "}",

    /* Faithfulness coloring */
    ".ckpt-faith-good { color: var(--success); }",
    ".ckpt-faith-warn { color: var(--warning); }",
    ".ckpt-faith-bad { color: var(--error); }",

    /* G5: Override corrections indicator */
    ".ckpt-override-indicator {",
    "  margin-top: var(--sm);",
    "  padding: 6px 10px;",
    "  font-size: 12px;",
    "  font-weight: 600;",
    "  color: var(--accent);",
    "  background: rgba(56,189,248,0.08);",
    "  border: 1px solid rgba(56,189,248,0.2);",
    "  border-radius: var(--radius-sm);",
    "  display: flex;",
    "  align-items: center;",
    "  gap: 4px;",
    "}",

    /* Status badge */
    ".ckpt-status-badge {",
    "  display: inline-block;",
    "  font-size: 10px;",
    "  font-weight: 600;",
    "  padding: 1px 6px;",
    "  border-radius: var(--radius-sm);",
    "  text-transform: uppercase;",
    "  letter-spacing: 0.5px;",
    "}",
    ".ckpt-status-complete { background: var(--success-dim); color: var(--success); }",
    ".ckpt-status-active { background: var(--accent-dim); color: var(--accent); }",
    ".ckpt-status-error { background: var(--error-dim); color: var(--error); }"
  ].join("\n");
  document.head.appendChild(style);
}

/* =====================================================================
   Time Formatting Utilities
   ===================================================================== */
function _ckptRelativeTime(isoStr) {
  if (!isoStr) return "--";
  var date;
  try { date = new Date(isoStr); } catch (e) { return isoStr; }
  var now = Date.now();
  var diffMs = now - date.getTime();
  if (isNaN(diffMs)) return isoStr;

  var absDiff = Math.abs(diffMs);
  var seconds = Math.floor(absDiff / 1000);
  var minutes = Math.floor(seconds / 60);
  var hours = Math.floor(minutes / 60);
  var days = Math.floor(hours / 24);

  if (seconds < 60) return "just now";
  if (minutes < 60) return minutes + "m ago";
  if (hours < 24) return hours + "h ago";
  if (days < 7) return days + "d ago";

  /* Fall back to short date */
  var month = String(date.getMonth() + 1).padStart(2, "0");
  var day = String(date.getDate()).padStart(2, "0");
  var hh = String(date.getHours()).padStart(2, "0");
  var mm = String(date.getMinutes()).padStart(2, "0");
  return month + "/" + day + " " + hh + ":" + mm;
}

function _ckptShortDatetime(isoStr) {
  if (!isoStr) return "--";
  var date;
  try { date = new Date(isoStr); } catch (e) { return isoStr; }
  if (isNaN(date.getTime())) return isoStr;
  var month = String(date.getMonth() + 1).padStart(2, "0");
  var day = String(date.getDate()).padStart(2, "0");
  var hh = String(date.getHours()).padStart(2, "0");
  var mm = String(date.getMinutes()).padStart(2, "0");
  var ss = String(date.getSeconds()).padStart(2, "0");
  return month + "/" + day + " " + hh + ":" + mm + ":" + ss;
}

/* =====================================================================
   Get friendly node display name
   ===================================================================== */
function _ckptNodeDisplayName(node) {
  if (!node) return "Unknown";
  if (node === "__end__") return "End";
  /* Use NODE_LABELS from core.js if available */
  if (typeof NODE_LABELS !== "undefined" && NODE_LABELS[node]) return NODE_LABELS[node];
  /* Fallback: capitalize and replace underscores */
  return node.replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
}

function _ckptNodeIcon(node) {
  if (!node) return "";
  if (node === "__end__") return "\u2705";
  if (typeof NODE_ICONS !== "undefined" && NODE_ICONS[node]) return NODE_ICONS[node];
  return "\u25CF";
}

/* =====================================================================
   Determine dot status for a checkpoint in the list
   ===================================================================== */
function _ckptDotClass(checkpoint, index, total) {
  /* Last checkpoint is "current" (pulsing), rest are "done" */
  if (index === total - 1) return "ckpt-dot-current";
  return "ckpt-dot-done";
}

function _ckptConnectorClass(index, total) {
  if (index < total - 1) return "ckpt-connector ckpt-conn-done";
  return "ckpt-connector";
}

/* =====================================================================
   Build Tooltip HTML for a checkpoint
   ===================================================================== */
function _ckptBuildTooltip(cp) {
  var rows = [];
  rows.push('<div class="ckpt-tooltip-row"><span class="ckpt-tooltip-key">Node</span><span class="ckpt-tooltip-val">' + esc(_ckptNodeDisplayName(cp.node)) + '</span></div>');
  rows.push('<div class="ckpt-tooltip-row"><span class="ckpt-tooltip-key">Time</span><span class="ckpt-tooltip-val">' + esc(_ckptShortDatetime(cp.timestamp)) + '</span></div>');
  if (cp.evidence_count !== undefined && cp.evidence_count !== null) {
    rows.push('<div class="ckpt-tooltip-row"><span class="ckpt-tooltip-key">Evidence</span><span class="ckpt-tooltip-val">' + esc(String(cp.evidence_count)) + '</span></div>');
  }
  if (cp.faithfulness !== undefined && cp.faithfulness !== null && cp.faithfulness > 0) {
    var faithPct = (cp.faithfulness * (cp.faithfulness <= 1 ? 100 : 1)).toFixed(1);
    rows.push('<div class="ckpt-tooltip-row"><span class="ckpt-tooltip-key">Faithfulness</span><span class="ckpt-tooltip-val">' + esc(faithPct + "%") + '</span></div>');
  }
  if (cp.iteration !== undefined && cp.iteration !== null) {
    rows.push('<div class="ckpt-tooltip-row"><span class="ckpt-tooltip-key">Iteration</span><span class="ckpt-tooltip-val">' + esc(String(cp.iteration)) + '</span></div>');
  }
  return '<div class="ckpt-tooltip">' + rows.join("") + '</div>';
}

/* =====================================================================
   Render Timeline
   ===================================================================== */
function _ckptRenderTimeline() {
  var container = document.getElementById(_ckptState.containerId);
  if (!container) return;

  /* Ensure panel wrapper exists */
  var panel = document.getElementById("ckpt-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "ckpt-panel";
    panel.className = "ckpt-panel operator-only";
    container.appendChild(panel);
  }

  /* Loading state */
  if (_ckptState.loading) {
    panel.innerHTML = '<div class="ckpt-panel-header">' +
      '<span class="ckpt-panel-title">Checkpoints</span></div>' +
      '<div class="ckpt-loading"><div class="ckpt-spinner"></div><span>Loading checkpoints...</span></div>';
    return;
  }

  /* Error state */
  if (_ckptState.error) {
    panel.innerHTML = '<div class="ckpt-panel-header">' +
      '<span class="ckpt-panel-title">Checkpoints</span>' +
      '<button class="ckpt-refresh-btn" onclick="fetchCheckpoints()" aria-label="Retry loading checkpoints">Retry</button></div>' +
      '<div class="ckpt-error"><span>' + esc(_ckptState.error) + '</span>' +
      '<button class="ckpt-retry-btn" onclick="fetchCheckpoints()" aria-label="Retry loading checkpoints">Retry</button></div>';
    return;
  }

  /* Empty state */
  if (!_ckptState.checkpoints || _ckptState.checkpoints.length === 0) {
    panel.innerHTML = '<div class="ckpt-panel-header">' +
      '<span class="ckpt-panel-title">Checkpoints</span>' +
      '<button class="ckpt-refresh-btn" onclick="fetchCheckpoints()" aria-label="Refresh checkpoints">Refresh</button></div>' +
      '<div class="ckpt-empty-state">Run a research query to see pipeline checkpoints</div>';
    return;
  }

  /* Build timeline */
  var cps = _ckptState.checkpoints;
  var total = cps.length;

  var html = '<div class="ckpt-panel-header">' +
    '<span class="ckpt-panel-title">Checkpoints (' + total + ')</span>' +
    '<button class="ckpt-refresh-btn" onclick="fetchCheckpoints()" aria-label="Refresh checkpoints">Refresh</button></div>';

  html += '<div class="ckpt-timeline" role="list" aria-label="Pipeline checkpoint timeline">';

  for (var i = 0; i < total; i++) {
    var cp = cps[i];
    var dotClass = _ckptDotClass(cp, i, total);
    var labelClass = "ckpt-label";
    if (i === total - 1) labelClass += " ckpt-label-current";
    else labelClass += " ckpt-label-done";

    html += '<div class="ckpt-node" role="listitem" tabindex="0"' +
      ' data-ckpt-idx="' + i + '"' +
      ' onclick="_ckptOnNodeClick(' + i + ')"' +
      ' onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();_ckptOnNodeClick(' + i + ');}"' +
      ' aria-label="Checkpoint at ' + esc(_ckptNodeDisplayName(cp.node)) + ', ' + esc(_ckptRelativeTime(cp.timestamp)) + '">';

    /* Tooltip */
    html += _ckptBuildTooltip(cp);

    /* Dot */
    html += '<div class="ckpt-dot ' + dotClass + '"></div>';

    /* Label */
    html += '<span class="' + labelClass + '">' + esc(_ckptNodeDisplayName(cp.node)) + '</span>';

    /* Iteration badge */
    if (cp.iteration !== undefined && cp.iteration !== null && cp.iteration > 0) {
      html += '<span class="ckpt-iter-badge">iter ' + esc(String(cp.iteration)) + '</span>';
    }

    /* Relative time */
    html += '<span class="ckpt-iter-badge">' + esc(_ckptRelativeTime(cp.timestamp)) + '</span>';

    html += '</div>';

    /* Connector (not after last node) */
    if (i < total - 1) {
      html += '<div class="' + _ckptConnectorClass(i, total) + '"></div>';
    }
  }

  html += '</div>';
  panel.innerHTML = html;
}

/* =====================================================================
   Node Click -> Open Drawer
   ===================================================================== */
function _ckptOnNodeClick(idx) {
  if (idx < 0 || idx >= _ckptState.checkpoints.length) return;
  var cp = _ckptState.checkpoints[idx];
  _ckptState.drawerCheckpoint = cp;
  _ckptState.drawerState = null;
  _ckptState.stateExpanded = false;
  _ckptOpenDrawer();
  _ckptFetchCheckpointState(cp.checkpoint_id);
}

/* =====================================================================
   Drawer Management
   ===================================================================== */
function _ckptEnsureDrawerDOM() {
  if (document.getElementById("ckpt-drawer-overlay")) return;

  /* Overlay */
  var overlay = document.createElement("div");
  overlay.id = "ckpt-drawer-overlay";
  overlay.className = "ckpt-drawer-overlay";
  overlay.addEventListener("click", _ckptCloseDrawer);
  document.body.appendChild(overlay);

  /* Drawer */
  var drawer = document.createElement("div");
  drawer.id = "ckpt-drawer";
  drawer.className = "ckpt-drawer";
  drawer.setAttribute("role", "dialog");
  drawer.setAttribute("aria-modal", "true");
  drawer.setAttribute("aria-label", "Checkpoint state inspector");
  drawer.innerHTML = '<div class="ckpt-drawer-header">' +
    '<span class="ckpt-drawer-title" id="ckpt-drawer-title">Checkpoint</span>' +
    '<button class="ckpt-drawer-close" onclick="_ckptCloseDrawer()" aria-label="Close checkpoint inspector">&times;</button></div>' +
    '<div class="ckpt-drawer-body" id="ckpt-drawer-body"></div>';
  document.body.appendChild(drawer);
}

function _ckptOpenDrawer() {
  _ckptEnsureDrawerDOM();
  _ckptState.drawerOpen = true;

  /* Show overlay */
  var overlay = document.getElementById("ckpt-drawer-overlay");
  /* Use requestAnimationFrame to ensure the class toggle triggers the CSS transition */
  requestAnimationFrame(function () {
    if (overlay) overlay.classList.add("ckpt-drawer-visible");
    var drawer = document.getElementById("ckpt-drawer");
    if (drawer) drawer.classList.add("ckpt-drawer-open");
  });

  /* Render initial drawer content (metadata from list, state loading) */
  _ckptRenderDrawerContent();

  /* Attach Escape key listener */
  document.addEventListener("keydown", _ckptEscHandler);
}

function _ckptCloseDrawer() {
  _ckptState.drawerOpen = false;
  var overlay = document.getElementById("ckpt-drawer-overlay");
  var drawer = document.getElementById("ckpt-drawer");
  if (overlay) overlay.classList.remove("ckpt-drawer-visible");
  if (drawer) drawer.classList.remove("ckpt-drawer-open");
  document.removeEventListener("keydown", _ckptEscHandler);
}

function _ckptEscHandler(e) {
  if (e.key === "Escape" && _ckptState.drawerOpen) {
    _ckptCloseDrawer();
  }
}

/* =====================================================================
   Render Drawer Content
   ===================================================================== */
function _ckptRenderDrawerContent() {
  var titleEl = document.getElementById("ckpt-drawer-title");
  var bodyEl = document.getElementById("ckpt-drawer-body");
  if (!titleEl || !bodyEl) return;

  var cp = _ckptState.drawerCheckpoint;
  if (!cp) {
    bodyEl.innerHTML = '<div class="ckpt-empty-state">No checkpoint selected</div>';
    return;
  }

  /* Title */
  titleEl.innerHTML = '<span class="ckpt-node-badge">' + esc(_ckptNodeIcon(cp.node)) + ' ' + esc(_ckptNodeDisplayName(cp.node)) + '</span>';

  var html = '';

  /* -- Metadata Section -- */
  html += '<div class="ckpt-drawer-section">';
  html += '<div class="ckpt-drawer-section-title">Checkpoint Metadata</div>';
  html += '<div class="ckpt-meta-grid">';
  html += _ckptMetaItem("Node", _ckptNodeDisplayName(cp.node));
  html += _ckptMetaItem("Timestamp", _ckptShortDatetime(cp.timestamp));
  html += _ckptMetaItem("Iteration", cp.iteration !== undefined && cp.iteration !== null ? String(cp.iteration) : "--");
  html += _ckptMetaItem("Status", cp.status || "--");
  html += _ckptMetaItem("Checkpoint ID", _ckptTruncateId(cp.checkpoint_id));
  html += _ckptMetaItem("Parent", cp.parent_checkpoint_id ? _ckptTruncateId(cp.parent_checkpoint_id) : "None (root)");
  html += '</div>';
  html += '</div>';

  /* -- Key Metrics Section -- */
  html += '<div class="ckpt-drawer-section">';
  html += '<div class="ckpt-drawer-section-title">Key Metrics</div>';
  html += '<div class="ckpt-metrics-row">';

  html += _ckptMetricItem(cp.evidence_count !== undefined && cp.evidence_count !== null ? String(cp.evidence_count) : "--", "Evidence");
  html += _ckptMetricItem(cp.claims_count !== undefined && cp.claims_count !== null ? String(cp.claims_count) : "--", "Claims");
  html += _ckptMetricItem(cp.sections_count !== undefined && cp.sections_count !== null ? String(cp.sections_count) : "--", "Sections");

  var faithVal = "--";
  var faithClass = "";
  if (cp.faithfulness !== undefined && cp.faithfulness !== null && cp.faithfulness > 0) {
    /* Normalize: if <= 1 treat as ratio, otherwise already percentage */
    var faithPct = cp.faithfulness <= 1 ? cp.faithfulness * 100 : cp.faithfulness;
    faithVal = faithPct.toFixed(1) + "%";
    faithClass = faithPct >= 80 ? " ckpt-faith-good" : faithPct >= 60 ? " ckpt-faith-warn" : " ckpt-faith-bad";
  }
  html += '<div class="ckpt-metric-item"><div class="ckpt-metric-val' + faithClass + '">' + esc(faithVal) + '</div><div class="ckpt-metric-label">Faithfulness</div></div>';

  html += _ckptMetricItem(cp.word_count !== undefined && cp.word_count !== null ? String(cp.word_count) : "--", "Words");
  html += '</div>';

  if (cp.has_report) {
    html += '<div style="margin-top:var(--sm);font-size:11px;color:var(--success);display:flex;align-items:center;gap:4px">';
    html += '<span>\u2705</span> Report available at this checkpoint';
    html += '</div>';
  }

  html += '</div>';

  /* -- G5: Human Override Corrections Count -- */
  var overrideCount = 0;
  if (cp.human_overrides && Array.isArray(cp.human_overrides)) {
    overrideCount = cp.human_overrides.length;
  } else if (cp.state_snapshot && cp.state_snapshot.human_overrides) {
    overrideCount = cp.state_snapshot.human_overrides.length || 0;
  }
  if (overrideCount > 0) {
    html += '<div class="ckpt-override-indicator">';
    html += '<span class="ckpt-override-icon">\u270F\uFE0F</span> ';
    html += 'Applied ' + overrideCount + ' correction' + (overrideCount > 1 ? 's' : '');
    html += '</div>';
  }

  /* -- State Patch Editor (A7.4: Human Override) -- */
  html += '<div class="ckpt-drawer-section">';
  html += '<div class="ckpt-drawer-section-title">State Corrections (Optional)</div>';
  html += '<div style="font-size:11px;color:var(--text-tertiary);margin-bottom:6px">Edit state before rewinding. JSON object with keys to override (e.g., remove bad evidence, correct facts).</div>';
  html += '<textarea id="ckpt-state-patch" class="ckpt-state-patch" placeholder=\'{"evidence": [...], "claims": [...]}\' rows="4" spellcheck="false"></textarea>';
  html += '</div>';

  /* -- Rewind Button -- */
  html += '<button class="ckpt-rewind-btn" id="ckpt-rewind-btn"' +
    ' onclick="_ckptRewindTo()" aria-label="Rewind pipeline to this checkpoint">' +
    '\u23EA Rewind to Here</button>';

  /* -- State JSON Section -- */
  html += '<div class="ckpt-drawer-section">';
  html += '<div class="ckpt-json-toggle" onclick="_ckptToggleState()" role="button" tabindex="0"' +
    ' onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();_ckptToggleState();}"' +
    ' aria-expanded="' + (_ckptState.stateExpanded ? 'true' : 'false') + '">';
  html += '<span class="ckpt-drawer-section-title" style="margin-bottom:0">Full State</span>';
  html += '<span class="ckpt-json-chevron' + (_ckptState.stateExpanded ? ' ckpt-json-expanded' : '') + '" id="ckpt-json-chevron">\u25B6</span>';
  html += '</div>';

  if (_ckptState.drawerLoading) {
    html += '<div class="ckpt-drawer-loading"><div class="ckpt-spinner"></div><span>Loading state...</span></div>';
  } else if (_ckptState.drawerState) {
    var jsonStr = JSON.stringify(_ckptState.drawerState, null, 2);
    var preview = jsonStr.substring(0, 120).replace(/\n/g, " ");
    if (jsonStr.length > 120) preview += "...";

    html += '<div class="ckpt-json-preview" id="ckpt-json-preview">' + esc(preview) + '</div>';
    html += '<div class="ckpt-json-full' + (_ckptState.stateExpanded ? '' : ' ckpt-json-hidden') + '" id="ckpt-json-full">';
    html += '<pre>' + esc(jsonStr) + '</pre>';
    html += '</div>';
  } else {
    html += '<div style="font-size:11px;color:var(--text-tertiary);margin-top:var(--xs)">State not loaded yet</div>';
  }

  html += '</div>';

  bodyEl.innerHTML = html;
}

/* Helper: metadata item */
function _ckptMetaItem(key, val) {
  return '<div class="ckpt-meta-item"><span class="ckpt-meta-key">' + esc(key) + '</span>' +
    '<span class="ckpt-meta-val" title="' + esc(val) + '">' + esc(val) + '</span></div>';
}

/* Helper: metric item */
function _ckptMetricItem(val, label) {
  return '<div class="ckpt-metric-item"><div class="ckpt-metric-val">' + esc(val) + '</div>' +
    '<div class="ckpt-metric-label">' + esc(label) + '</div></div>';
}

/* Helper: truncate checkpoint ID for display */
function _ckptTruncateId(id) {
  if (!id) return "--";
  if (id.length <= 12) return id;
  return id.substring(0, 8) + "..." + id.substring(id.length - 4);
}

/* =====================================================================
   Toggle State JSON Viewer
   ===================================================================== */
function _ckptToggleState() {
  _ckptState.stateExpanded = !_ckptState.stateExpanded;
  var fullEl = document.getElementById("ckpt-json-full");
  var chevEl = document.getElementById("ckpt-json-chevron");
  var previewEl = document.getElementById("ckpt-json-preview");
  if (fullEl) {
    if (_ckptState.stateExpanded) {
      fullEl.classList.remove("ckpt-json-hidden");
    } else {
      fullEl.classList.add("ckpt-json-hidden");
    }
  }
  if (chevEl) {
    if (_ckptState.stateExpanded) {
      chevEl.classList.add("ckpt-json-expanded");
    } else {
      chevEl.classList.remove("ckpt-json-expanded");
    }
  }
  if (previewEl) {
    previewEl.style.display = _ckptState.stateExpanded ? "none" : "block";
  }
  /* Update aria-expanded */
  var toggleEl = fullEl ? fullEl.parentElement.querySelector(".ckpt-json-toggle") : null;
  if (toggleEl) toggleEl.setAttribute("aria-expanded", _ckptState.stateExpanded ? "true" : "false");
}

/* =====================================================================
   Fetch Checkpoint List
   ===================================================================== */
function fetchCheckpoints() {
  var vectorId = (typeof state !== "undefined" && state.vectorId) ? state.vectorId : null;
  if (!vectorId || vectorId === "--") {
    _ckptState.checkpoints = [];
    _ckptState.error = null;
    _ckptState.loading = false;
    _ckptRenderTimeline();
    return;
  }

  _ckptState.loading = true;
  _ckptState.error = null;
  _ckptRenderTimeline();

  fetch("/api/research/checkpoints/" + encodeURIComponent(vectorId))
    .then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status + ": " + response.statusText);
      }
      return response.json();
    })
    .then(function (data) {
      _ckptState.loading = false;
      if (Array.isArray(data)) {
        _ckptState.checkpoints = data;
      } else if (data && Array.isArray(data.checkpoints)) {
        _ckptState.checkpoints = data.checkpoints;
      } else {
        _ckptState.checkpoints = [];
      }
      _ckptState.error = null;
      _ckptRenderTimeline();
    })
    .catch(function (err) {
      _ckptState.loading = false;
      _ckptState.error = "Failed to load checkpoints: " + (err.message || String(err));
      _ckptState.checkpoints = [];
      _ckptRenderTimeline();
      console.warn("fetchCheckpoints error:", err);
    });
}

/* =====================================================================
   Fetch Full Checkpoint State (for drawer)
   ===================================================================== */
function _ckptFetchCheckpointState(checkpointId) {
  var vectorId = (typeof state !== "undefined" && state.vectorId) ? state.vectorId : null;
  if (!vectorId || vectorId === "--" || !checkpointId) return;

  _ckptState.drawerLoading = true;
  _ckptRenderDrawerContent();

  fetch("/api/research/checkpoint/" + encodeURIComponent(vectorId) + "/" + encodeURIComponent(checkpointId))
    .then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      return response.json();
    })
    .then(function (data) {
      _ckptState.drawerLoading = false;
      _ckptState.drawerState = data.state || data;
      /* Merge metadata from the response if available, enriching the drawer checkpoint */
      if (data.metadata && data.metadata.summary) {
        var summary = data.metadata.summary;
        var cp = _ckptState.drawerCheckpoint;
        if (cp) {
          if (summary.evidence_count !== undefined) cp.evidence_count = summary.evidence_count;
          if (summary.claims_count !== undefined) cp.claims_count = summary.claims_count;
          if (summary.sections_count !== undefined) cp.sections_count = summary.sections_count;
          if (summary.faithfulness !== undefined) cp.faithfulness = summary.faithfulness;
          if (summary.word_count !== undefined) cp.word_count = summary.word_count;
        }
      }
      _ckptRenderDrawerContent();
    })
    .catch(function (err) {
      _ckptState.drawerLoading = false;
      _ckptState.drawerState = null;
      _ckptRenderDrawerContent();
      if (typeof showToast === "function") {
        showToast("Failed to load checkpoint state: " + (err.message || String(err)), "error");
      }
      console.warn("_ckptFetchCheckpointState error:", err);
    });
}

/* =====================================================================
   Rewind to Checkpoint
   ===================================================================== */
function _ckptRewindTo() {
  var cp = _ckptState.drawerCheckpoint;
  if (!cp || !cp.checkpoint_id) {
    if (typeof showToast === "function") showToast("No checkpoint selected", "warning");
    return;
  }

  var vectorId = (typeof state !== "undefined" && state.vectorId) ? state.vectorId : null;
  if (!vectorId || vectorId === "--") {
    if (typeof showToast === "function") showToast("No active vector ID", "warning");
    return;
  }

  /* Confirmation via toast before proceeding */
  var nodeName = _ckptNodeDisplayName(cp.node);
  if (typeof showToast === "function") {
    showToast("Rewinding pipeline to " + nodeName + "...", "info");
  }

  /* Disable button to prevent double-clicks */
  var btn = document.getElementById("ckpt-rewind-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Rewinding...";
  }

  /* A7.4: Read state patch if provided */
  var patchBody = {};
  var patchTextarea = document.getElementById("ckpt-state-patch");
  if (patchTextarea && patchTextarea.value.trim()) {
    try {
      patchBody.state_patch = JSON.parse(patchTextarea.value.trim());
    } catch (parseErr) {
      if (typeof showToast === "function") showToast("Invalid JSON in state patch: " + parseErr.message, "error");
      if (btn) { btn.disabled = false; btn.textContent = "\u23EA Rewind to Here"; }
      return;
    }
  }

  fetch("/api/research/rewind/" + encodeURIComponent(vectorId) + "/" + encodeURIComponent(cp.checkpoint_id), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patchBody)
  })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status + ": " + response.statusText);
      }
      return response.json();
    })
    .then(function (data) {
      if (typeof showToast === "function") {
        showToast("Pipeline rewound to " + nodeName + " successfully", "success");
      }
      _ckptCloseDrawer();
      /* Refresh checkpoints to reflect new state */
      fetchCheckpoints();
    })
    .catch(function (err) {
      if (typeof showToast === "function") {
        showToast("Rewind failed: " + (err.message || String(err)), "error");
      }
      console.warn("Rewind error:", err);
      /* Re-enable button */
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '\u23EA Rewind to Here';
      }
    });
}

/* =====================================================================
   Public API: Initialize
   ===================================================================== */
function initCheckpointTimeline(containerId) {
  _ckptInjectStyles();
  _ckptState.containerId = containerId;

  /* Verify container exists */
  var container = document.getElementById(containerId);
  if (!container) {
    console.warn("initCheckpointTimeline: container #" + containerId + " not found");
    return;
  }

  /* Render initial empty state */
  _ckptRenderTimeline();

  /* If we already have a vector ID, attempt a fetch */
  if (typeof state !== "undefined" && state.vectorId && state.vectorId !== "--") {
    fetchCheckpoints();
  }
}
