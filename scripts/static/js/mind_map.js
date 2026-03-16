/* =====================================================================
   mind_map.js — Radial Mind Map SVG Visualization
   POLARIS Live Dashboard

   Provides:
     - buildMindMapGraph(canvas, emptyEl) — radial tree mind map in SVG

   Dependencies (from core.js):
     - state.vectorId
     - esc(str)
     - truncStr(text, maxLen)

   All DOM elements created dynamically. CSS injected once into <head>.
   ===================================================================== */

/* =====================================================================
   Internal State
   ===================================================================== */
var _mmState = {
  data: null,
  loading: false,
  error: null,
  canvas: null,
  emptyEl: null,
  viewBox: { x: 0, y: 0, w: 1000, h: 1000 },
  zoom: 1.0,
  panX: 0,
  panY: 0,
  dragging: false,
  dragStartX: 0,
  dragStartY: 0,
  dragStartPanX: 0,
  dragStartPanY: 0,
  selectedNodeId: null,
  hoveredNodeId: null,
  tooltipEl: null,
  infoPanelEl: null,
  statsBarEl: null,
  animFrameId: null,
  wheelTimeout: null,
  nodePositions: {},
  edgeList: [],
  initialized: false
};

/* =====================================================================
   Configuration Constants
   ===================================================================== */
var _MM_CENTER_RADIUS = 40;
var _MM_SECTION_RADIUS = 18;
var _MM_FINDING_RADIUS = 5;
var _MM_SOURCE_RADIUS = 8;
var _MM_SOURCE_CROSS_RADIUS = 11;
var _MM_RING_SECTION = 180;
var _MM_RING_FINDING = 320;
var _MM_RING_SOURCE = 440;
var _MM_ORIGIN_X = 500;
var _MM_ORIGIN_Y = 500;
var _MM_VIEWBOX_SIZE = 1000;
var _MM_ZOOM_MIN = 0.3;
var _MM_ZOOM_MAX = 3.0;
var _MM_ZOOM_STEP = 0.1;
var _MM_MAX_FINDINGS = 150;
var _MM_MAX_SOURCES = 100;
var _MM_DIM_OPACITY = 0.12;
var _MM_WHEEL_DEBOUNCE_MS = 16;

/* =====================================================================
   CSS Injection (runs once)
   ===================================================================== */
function _mmInjectStyles() {
  if (document.getElementById("mindmap-injected-styles")) return;
  var style = document.createElement("style");
  style.id = "mindmap-injected-styles";
  style.textContent = [
    /* --- Stats Bar --- */
    ".mindmap-stats-bar {",
    "  display: flex;",
    "  align-items: center;",
    "  gap: 16px;",
    "  padding: 8px 14px;",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-md);",
    "  margin-bottom: 8px;",
    "  font-size: 11px;",
    "  font-family: var(--font-sans);",
    "  color: var(--text-secondary);",
    "  flex-wrap: wrap;",
    "}",
    ".mindmap-stat-item {",
    "  display: flex;",
    "  align-items: center;",
    "  gap: 5px;",
    "}",
    ".mindmap-stat-value {",
    "  font-weight: 700;",
    "  font-family: var(--font-mono);",
    "  color: var(--text-primary);",
    "  font-size: 13px;",
    "}",
    ".mindmap-stat-label {",
    "  color: var(--text-tertiary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 0.5px;",
    "  font-size: 9px;",
    "}",
    ".mindmap-stat-dot {",
    "  width: 8px;",
    "  height: 8px;",
    "  border-radius: 50%;",
    "  flex-shrink: 0;",
    "}",

    /* --- Tooltip --- */
    ".mindmap-tooltip {",
    "  position: fixed;",
    "  z-index: 10000;",
    "  pointer-events: none;",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-md);",
    "  padding: 10px 14px;",
    "  font-size: 12px;",
    "  font-family: var(--font-sans);",
    "  color: var(--text-primary);",
    "  box-shadow: 0 8px 24px rgba(0,0,0,0.35);",
    "  max-width: 340px;",
    "  line-height: 1.5;",
    "  opacity: 0;",
    "  transition: opacity 0.15s ease;",
    "  display: none;",
    "}",
    ".mindmap-tooltip.mindmap-tooltip-visible {",
    "  opacity: 1;",
    "  display: block;",
    "}",
    ".mindmap-tooltip-title {",
    "  font-weight: 700;",
    "  font-size: 12px;",
    "  color: var(--text-primary);",
    "  margin-bottom: 4px;",
    "  overflow: hidden;",
    "  text-overflow: ellipsis;",
    "  white-space: nowrap;",
    "}",
    ".mindmap-tooltip-row {",
    "  display: flex;",
    "  justify-content: space-between;",
    "  gap: 12px;",
    "  font-size: 11px;",
    "}",
    ".mindmap-tooltip-key {",
    "  color: var(--text-tertiary);",
    "}",
    ".mindmap-tooltip-val {",
    "  color: var(--text-primary);",
    "  font-family: var(--font-mono);",
    "  font-weight: 500;",
    "}",
    ".mindmap-tooltip-text {",
    "  font-size: 11px;",
    "  color: var(--text-secondary);",
    "  margin-top: 4px;",
    "  line-height: 1.4;",
    "  display: -webkit-box;",
    "  -webkit-line-clamp: 3;",
    "  -webkit-box-orient: vertical;",
    "  overflow: hidden;",
    "}",

    /* --- Tier Badge (inline) --- */
    ".mindmap-tier-badge {",
    "  display: inline-block;",
    "  font-size: 9px;",
    "  font-weight: 700;",
    "  padding: 1px 5px;",
    "  border-radius: 3px;",
    "  text-transform: uppercase;",
    "  letter-spacing: 0.5px;",
    "}",
    ".mindmap-tier-gold { background: rgba(245,158,11,0.15); color: var(--gold); }",
    ".mindmap-tier-silver { background: rgba(148,163,184,0.15); color: var(--silver); }",
    ".mindmap-tier-bronze { background: rgba(180,130,80,0.15); color: var(--bronze); }",

    /* --- Info Panel --- */
    ".mindmap-info-panel {",
    "  position: absolute;",
    "  top: 8px;",
    "  right: 8px;",
    "  width: 280px;",
    "  max-height: 340px;",
    "  overflow-y: auto;",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-md);",
    "  padding: 14px;",
    "  font-size: 12px;",
    "  font-family: var(--font-sans);",
    "  color: var(--text-primary);",
    "  box-shadow: 0 4px 16px rgba(0,0,0,0.25);",
    "  z-index: 100;",
    "  display: none;",
    "  scrollbar-width: thin;",
    "}",
    ".mindmap-info-panel.mindmap-info-visible {",
    "  display: block;",
    "}",
    ".mindmap-info-close {",
    "  position: absolute;",
    "  top: 8px;",
    "  right: 8px;",
    "  background: transparent;",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius-md);",
    "  color: var(--text-secondary);",
    "  font-size: 14px;",
    "  width: 24px;",
    "  height: 24px;",
    "  cursor: pointer;",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  transition: all 0.15s ease;",
    "  font-family: var(--font-sans);",
    "  line-height: 1;",
    "}",
    ".mindmap-info-close:hover { background: var(--bg-secondary); color: var(--text-primary); }",
    ".mindmap-info-title {",
    "  font-weight: 700;",
    "  font-size: 13px;",
    "  margin-bottom: 8px;",
    "  padding-right: 28px;",
    "  line-height: 1.3;",
    "}",
    ".mindmap-info-row {",
    "  display: flex;",
    "  justify-content: space-between;",
    "  padding: 3px 0;",
    "  font-size: 11px;",
    "  border-bottom: 1px solid rgba(255,255,255,0.04);",
    "}",
    ".mindmap-info-key { color: var(--text-tertiary); }",
    ".mindmap-info-val { color: var(--text-primary); font-family: var(--font-mono); }",
    ".mindmap-info-text {",
    "  font-size: 11px;",
    "  color: var(--text-secondary);",
    "  line-height: 1.5;",
    "  margin-top: 8px;",
    "}",
    ".mindmap-info-link {",
    "  font-size: 11px;",
    "  color: var(--accent);",
    "  text-decoration: none;",
    "  word-break: break-all;",
    "}",
    ".mindmap-info-link:hover { text-decoration: underline; }",
    ".mindmap-info-connections {",
    "  margin-top: 8px;",
    "  padding-top: 8px;",
    "  border-top: 1px solid var(--border);",
    "}",
    ".mindmap-info-conn-title {",
    "  font-size: 10px;",
    "  font-weight: 600;",
    "  color: var(--text-tertiary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 0.5px;",
    "  margin-bottom: 4px;",
    "}",
    ".mindmap-info-conn-item {",
    "  font-size: 11px;",
    "  color: var(--text-secondary);",
    "  padding: 2px 0;",
    "}",

    /* --- SVG node interaction classes --- */
    ".mindmap-node { cursor: pointer; transition: opacity 0.25s ease; }",
    ".mindmap-node:hover { filter: brightness(1.2); }",
    ".mindmap-edge { transition: opacity 0.25s ease; }",
    ".mindmap-dimmed { opacity: " + _MM_DIM_OPACITY + "; }",

    /* --- Halo for cross-cutting sources --- */
    "@keyframes mindmap-halo-pulse {",
    "  0%, 100% { opacity: 0.35; }",
    "  50% { opacity: 0.65; }",
    "}",
    ".mindmap-halo {",
    "  animation: mindmap-halo-pulse 3s ease-in-out infinite;",
    "}",

    /* --- Loading state --- */
    ".mindmap-loading {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  gap: 8px;",
    "  padding: 40px;",
    "  color: var(--text-tertiary);",
    "  font-size: 13px;",
    "  font-family: var(--font-sans);",
    "}",
    ".mindmap-loading-spinner {",
    "  width: 16px;",
    "  height: 16px;",
    "  border: 2px solid var(--border);",
    "  border-top-color: var(--accent);",
    "  border-radius: 50%;",
    "  animation: mindmap-spin 0.7s linear infinite;",
    "}",
    "@keyframes mindmap-spin { to { transform: rotate(360deg); } }",

    /* --- Zoom controls --- */
    ".mindmap-zoom-controls {",
    "  position: absolute;",
    "  bottom: 12px;",
    "  left: 12px;",
    "  display: flex;",
    "  flex-direction: column;",
    "  gap: 2px;",
    "  z-index: 50;",
    "}",
    ".mindmap-zoom-btn {",
    "  width: 28px;",
    "  height: 28px;",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--border);",
    "  color: var(--text-secondary);",
    "  font-size: 16px;",
    "  font-weight: 700;",
    "  cursor: pointer;",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  font-family: var(--font-mono);",
    "  line-height: 1;",
    "  transition: all 0.15s ease;",
    "}",
    ".mindmap-zoom-btn:first-child { border-radius: var(--radius-md) var(--radius-md) 0 0; }",
    ".mindmap-zoom-btn:last-child { border-radius: 0 0 var(--radius-md) var(--radius-md); }",
    ".mindmap-zoom-btn:hover { background: var(--bg-secondary); color: var(--text-primary); }",
    ".mindmap-zoom-label {",
    "  width: 28px;",
    "  height: 22px;",
    "  background: var(--bg-elevated);",
    "  border-left: 1px solid var(--border);",
    "  border-right: 1px solid var(--border);",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  font-size: 9px;",
    "  font-family: var(--font-mono);",
    "  color: var(--text-tertiary);",
    "}"
  ].join("\n");
  document.head.appendChild(style);
}

/* =====================================================================
   Tooltip Management
   ===================================================================== */
function _mmEnsureTooltip() {
  if (_mmState.tooltipEl) return;
  var tip = document.createElement("div");
  tip.id = "mindmap-tooltip";
  tip.className = "mindmap-tooltip";
  tip.setAttribute("role", "tooltip");
  document.body.appendChild(tip);
  _mmState.tooltipEl = tip;
}

function _mmShowTooltip(evt, html) {
  _mmEnsureTooltip();
  var tip = _mmState.tooltipEl;
  tip.innerHTML = html;
  tip.classList.add("mindmap-tooltip-visible");

  var tx = evt.clientX + 14;
  var ty = evt.clientY + 14;
  var tipW = tip.offsetWidth || 280;
  var tipH = tip.offsetHeight || 100;
  if (tx + tipW > window.innerWidth - 10) tx = evt.clientX - tipW - 10;
  if (ty + tipH > window.innerHeight - 10) ty = evt.clientY - tipH - 10;
  tip.style.left = tx + "px";
  tip.style.top = ty + "px";
}

function _mmHideTooltip() {
  if (_mmState.tooltipEl) {
    _mmState.tooltipEl.classList.remove("mindmap-tooltip-visible");
  }
}

/* =====================================================================
   Info Panel Management
   ===================================================================== */
function _mmEnsureInfoPanel() {
  if (_mmState.infoPanelEl) return;
  var panel = document.createElement("div");
  panel.id = "mindmap-info-panel";
  panel.className = "mindmap-info-panel";
  _mmState.infoPanelEl = panel;
}

function _mmShowInfoPanel(nodeData) {
  _mmEnsureInfoPanel();
  var panel = _mmState.infoPanelEl;
  var html = '<button class="mindmap-info-close" onclick="_mmCloseInfoPanel()" aria-label="Close">&times;</button>';

  if (nodeData.type === "center") {
    html += '<div class="mindmap-info-title">' + esc(nodeData.label) + '</div>';
    html += '<div class="mindmap-info-row"><span class="mindmap-info-key">Type</span><span class="mindmap-info-val">Research Question</span></div>';
    if (_mmState.data && _mmState.data.stats) {
      var st = _mmState.data.stats;
      html += '<div class="mindmap-info-row"><span class="mindmap-info-key">Sections</span><span class="mindmap-info-val">' + (st.total_sections || 0) + '</span></div>';
      html += '<div class="mindmap-info-row"><span class="mindmap-info-key">Findings</span><span class="mindmap-info-val">' + (st.total_findings || 0) + '</span></div>';
      html += '<div class="mindmap-info-row"><span class="mindmap-info-key">Sources</span><span class="mindmap-info-val">' + (st.total_sources || 0) + '</span></div>';
    }
  } else if (nodeData.type === "section") {
    html += '<div class="mindmap-info-title">' + esc(nodeData.title || nodeData.id) + '</div>';
    html += '<div class="mindmap-info-row"><span class="mindmap-info-key">Type</span><span class="mindmap-info-val">Section</span></div>';
    html += '<div class="mindmap-info-row"><span class="mindmap-info-key">Findings</span><span class="mindmap-info-val">' + (nodeData.finding_count || 0) + '</span></div>';
    /* Show connected findings summary */
    var connFindings = _mmGetConnectedFindings(nodeData.id);
    if (connFindings.length) {
      html += '<div class="mindmap-info-connections">';
      html += '<div class="mindmap-info-conn-title">Key Findings (' + connFindings.length + ')</div>';
      var showCount = Math.min(connFindings.length, 5);
      for (var i = 0; i < showCount; i++) {
        html += '<div class="mindmap-info-conn-item">' + esc(truncStr(connFindings[i].text || "", 80)) + '</div>';
      }
      if (connFindings.length > showCount) {
        html += '<div class="mindmap-info-conn-item" style="color:var(--text-tertiary)">...and ' + (connFindings.length - showCount) + ' more</div>';
      }
      html += '</div>';
    }
  } else if (nodeData.type === "finding") {
    html += '<div class="mindmap-info-title">Finding</div>';
    html += '<div class="mindmap-info-text">' + esc(nodeData.text || "") + '</div>';
    html += '<div class="mindmap-info-row" style="margin-top:8px"><span class="mindmap-info-key">Evidence ID</span><span class="mindmap-info-val">' + esc(nodeData.evidence_id || "--") + '</span></div>';
    html += '<div class="mindmap-info-row"><span class="mindmap-info-key">Section</span><span class="mindmap-info-val">' + esc(nodeData.section_id || "--") + '</span></div>';
  } else if (nodeData.type === "source") {
    html += '<div class="mindmap-info-title">' + esc(nodeData.title || "Source") + '</div>';
    if (nodeData.url) {
      html += '<a class="mindmap-info-link" href="' + esc(nodeData.url) + '" target="_blank" rel="noopener">' + esc(truncStr(nodeData.url, 60)) + '</a>';
    }
    var tierClass = "mindmap-tier-" + (nodeData.tier || "bronze").toLowerCase();
    html += '<div style="margin-top:8px"><span class="mindmap-tier-badge ' + tierClass + '">' + esc((nodeData.tier || "BRONZE").toUpperCase()) + '</span></div>';
    html += '<div class="mindmap-info-row" style="margin-top:8px"><span class="mindmap-info-key">Citations</span><span class="mindmap-info-val">' + (nodeData.citation_count || 0) + '</span></div>';
    html += '<div class="mindmap-info-row"><span class="mindmap-info-key">Cross-cutting</span><span class="mindmap-info-val">' + (nodeData.cross_cutting ? "Yes" : "No") + '</span></div>';
    if (nodeData.sections_cited_in && nodeData.sections_cited_in.length) {
      html += '<div class="mindmap-info-connections">';
      html += '<div class="mindmap-info-conn-title">Cited in sections</div>';
      for (var j = 0; j < nodeData.sections_cited_in.length; j++) {
        var secTitle = _mmGetSectionTitle(nodeData.sections_cited_in[j]);
        html += '<div class="mindmap-info-conn-item">' + esc(secTitle) + '</div>';
      }
      html += '</div>';
    }
  }

  panel.innerHTML = html;
  panel.classList.add("mindmap-info-visible");

  /* Attach to SVG parent container */
  var svgParent = _mmState.canvas ? _mmState.canvas.parentElement : null;
  if (svgParent && !panel.parentElement) {
    svgParent.style.position = "relative";
    svgParent.appendChild(panel);
  } else if (svgParent && panel.parentElement !== svgParent) {
    svgParent.style.position = "relative";
    svgParent.appendChild(panel);
  }
}

function _mmCloseInfoPanel() {
  if (_mmState.infoPanelEl) {
    _mmState.infoPanelEl.classList.remove("mindmap-info-visible");
  }
  _mmClearSelection();
}

/* =====================================================================
   Stats Bar
   ===================================================================== */
function _mmRenderStatsBar(container) {
  if (!_mmState.data || !_mmState.data.stats) return;
  var st = _mmState.data.stats;
  var bar = document.getElementById("mindmap-stats-bar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "mindmap-stats-bar";
    bar.className = "mindmap-stats-bar";
    container.insertBefore(bar, container.firstChild);
    _mmState.statsBarEl = bar;
  }
  bar.innerHTML =
    '<div class="mindmap-stat-item">' +
      '<div class="mindmap-stat-dot" style="background:var(--accent)"></div>' +
      '<span class="mindmap-stat-value">' + (st.total_sections || 0) + '</span>' +
      '<span class="mindmap-stat-label">Sections</span>' +
    '</div>' +
    '<div class="mindmap-stat-item">' +
      '<div class="mindmap-stat-dot" style="background:var(--info)"></div>' +
      '<span class="mindmap-stat-value">' + (st.total_findings || 0) + '</span>' +
      '<span class="mindmap-stat-label">Findings</span>' +
    '</div>' +
    '<div class="mindmap-stat-item">' +
      '<div class="mindmap-stat-dot" style="background:var(--success)"></div>' +
      '<span class="mindmap-stat-value">' + (st.total_sources || 0) + '</span>' +
      '<span class="mindmap-stat-label">Sources</span>' +
    '</div>' +
    '<div class="mindmap-stat-item">' +
      '<div class="mindmap-stat-dot" style="background:var(--warning)"></div>' +
      '<span class="mindmap-stat-value">' + (st.cross_cutting_sources || 0) + '</span>' +
      '<span class="mindmap-stat-label">Cross-cutting</span>' +
    '</div>';
}

/* =====================================================================
   Helper: get section title by ID
   ===================================================================== */
function _mmGetSectionTitle(sectionId) {
  if (!_mmState.data || !_mmState.data.sections) return sectionId;
  for (var i = 0; i < _mmState.data.sections.length; i++) {
    if (_mmState.data.sections[i].id === sectionId) {
      return _mmState.data.sections[i].title || sectionId;
    }
  }
  return sectionId;
}

/* =====================================================================
   Helper: get connected findings for a section
   ===================================================================== */
function _mmGetConnectedFindings(sectionId) {
  if (!_mmState.data || !_mmState.data.findings) return [];
  return _mmState.data.findings.filter(function(f) {
    return f.section_id === sectionId;
  });
}

/* =====================================================================
   Layout Computation: Radial Tree Positions
   ===================================================================== */
function _mmComputeLayout(data) {
  var positions = {};
  var edges = [];
  var cx = _MM_ORIGIN_X;
  var cy = _MM_ORIGIN_Y;

  /* Center node */
  positions["center"] = {
    x: cx, y: cy, r: _MM_CENTER_RADIUS,
    type: "center", label: data.center ? data.center.label : "Research Question",
    data: data.center || {}
  };

  /* Section nodes — evenly distributed on the first ring */
  var sections = data.sections || [];
  var sectionCount = sections.length;
  for (var si = 0; si < sectionCount; si++) {
    var sAngle = (2 * Math.PI * si / sectionCount) - (Math.PI / 2);
    var sx = cx + _MM_RING_SECTION * Math.cos(sAngle);
    var sy = cy + _MM_RING_SECTION * Math.sin(sAngle);
    var sec = sections[si];
    positions[sec.id] = {
      x: sx, y: sy, r: _MM_SECTION_RADIUS,
      type: "section", label: sec.title,
      angle: sAngle, data: sec
    };
    edges.push({
      from: "center", to: sec.id, type: "section",
      weight: 1
    });
  }

  /* Finding nodes — clustered around their parent section, capped */
  var findings = (data.findings || []).slice(0, _MM_MAX_FINDINGS);
  /* Group findings by section */
  var findingsBySection = {};
  for (var fi = 0; fi < findings.length; fi++) {
    var f = findings[fi];
    var sid = f.section_id || "";
    if (!findingsBySection[sid]) findingsBySection[sid] = [];
    findingsBySection[sid].push(f);
  }

  for (var sectionId in findingsBySection) {
    if (!findingsBySection.hasOwnProperty(sectionId)) continue;
    var sectionPos = positions[sectionId];
    if (!sectionPos) continue;

    var sectionFindings = findingsBySection[sectionId];
    var fCount = sectionFindings.length;
    /* Compute angular spread around the section's angle */
    var baseAngle = sectionPos.angle !== undefined ? sectionPos.angle : 0;
    /* Spread findings in a cone radiating outward from the section */
    var spreadAngle = Math.min(Math.PI * 0.5, (fCount * 0.06) + 0.15);

    for (var fj = 0; fj < fCount; fj++) {
      var finding = sectionFindings[fj];
      var fFraction = fCount > 1 ? (fj / (fCount - 1)) - 0.5 : 0;
      var fAngle = baseAngle + fFraction * spreadAngle;
      /* Add slight radial jitter for visual interest */
      var rJitter = (_mmHashCode(finding.id) % 30) - 15;
      var fx = cx + (_MM_RING_FINDING + rJitter) * Math.cos(fAngle);
      var fy = cy + (_MM_RING_FINDING + rJitter) * Math.sin(fAngle);

      positions[finding.id] = {
        x: fx, y: fy, r: _MM_FINDING_RADIUS,
        type: "finding", label: truncStr(finding.text || "", 40),
        data: finding
      };
      edges.push({
        from: sectionId, to: finding.id, type: "finding",
        weight: 1
      });
    }
  }

  /* Source nodes — distributed on the outer ring, capped */
  var sources = (data.sources || []).slice(0, _MM_MAX_SOURCES);
  var sourceCount = sources.length;
  for (var sci = 0; sci < sourceCount; sci++) {
    var src = sources[sci];
    var srcAngle = (2 * Math.PI * sci / sourceCount) - (Math.PI / 2);
    /* Cross-cutting sources get slightly larger orbit */
    var srcOrbit = src.cross_cutting ? _MM_RING_SOURCE + 20 : _MM_RING_SOURCE;
    var srcX = cx + srcOrbit * Math.cos(srcAngle);
    var srcY = cy + srcOrbit * Math.sin(srcAngle);
    var srcR = src.cross_cutting ? _MM_SOURCE_CROSS_RADIUS : _MM_SOURCE_RADIUS;

    positions[src.id] = {
      x: srcX, y: srcY, r: srcR,
      type: "source", label: src.title,
      data: src
    };
  }

  /* Build edges from the data.edges array if available */
  if (data.edges && data.edges.length) {
    for (var ei = 0; ei < data.edges.length; ei++) {
      var edge = data.edges[ei];
      /* Avoid duplicating section edges already added */
      if (edge.type === "section") continue;
      if (positions[edge.from] && positions[edge.to]) {
        edges.push({
          from: edge.from, to: edge.to,
          type: edge.type || "link",
          weight: edge.weight || 1
        });
      }
    }
  }

  /* Additionally, connect sources to their cited sections */
  for (var si2 = 0; si2 < sources.length; si2++) {
    var srcNode = sources[si2];
    var citedSections = srcNode.sections_cited_in || [];
    for (var ci = 0; ci < citedSections.length; ci++) {
      if (positions[citedSections[ci]] && positions[srcNode.id]) {
        edges.push({
          from: citedSections[ci], to: srcNode.id,
          type: "source",
          weight: srcNode.citation_count || 1
        });
      }
    }
  }

  _mmState.nodePositions = positions;
  _mmState.edgeList = edges;
}

/* Simple string hash for deterministic jitter */
function _mmHashCode(str) {
  var hash = 0;
  if (!str) return hash;
  for (var i = 0; i < str.length; i++) {
    var ch = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + ch;
    hash = hash & hash;
  }
  return Math.abs(hash);
}

/* =====================================================================
   SVG Rendering
   ===================================================================== */
function _mmRenderSvg() {
  var canvas = _mmState.canvas;
  if (!canvas) return;

  var positions = _mmState.nodePositions;
  var edges = _mmState.edgeList;
  var selectedId = _mmState.selectedNodeId;
  var connectedIds = {};

  /* If a node is selected, build the set of connected node IDs */
  if (selectedId) {
    connectedIds[selectedId] = true;
    for (var i = 0; i < edges.length; i++) {
      var e = edges[i];
      if (e.from === selectedId) connectedIds[e.to] = true;
      if (e.to === selectedId) connectedIds[e.from] = true;
    }
  }

  /* Build SVG content */
  var svgParts = [];

  /* Defs: glow filter for cross-cutting sources */
  svgParts.push('<defs>');
  svgParts.push('<filter id="mm-glow" x="-50%" y="-50%" width="200%" height="200%">');
  svgParts.push('<feGaussianBlur stdDeviation="3" result="blur"/>');
  svgParts.push('<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>');
  svgParts.push('</filter>');
  /* Radial gradient for center node */
  svgParts.push('<radialGradient id="mm-center-grad">');
  svgParts.push('<stop offset="0%" stop-color="var(--accent)" stop-opacity="0.9"/>');
  svgParts.push('<stop offset="100%" stop-color="var(--accent)" stop-opacity="0.6"/>');
  svgParts.push('</radialGradient>');
  svgParts.push('</defs>');

  /* Ring guides (faint circles for visual structure) */
  svgParts.push('<circle cx="' + _MM_ORIGIN_X + '" cy="' + _MM_ORIGIN_Y + '" r="' + _MM_RING_SECTION + '" fill="none" stroke="var(--border)" stroke-width="0.5" stroke-dasharray="4,6" opacity="0.3"/>');
  svgParts.push('<circle cx="' + _MM_ORIGIN_X + '" cy="' + _MM_ORIGIN_Y + '" r="' + _MM_RING_FINDING + '" fill="none" stroke="var(--border)" stroke-width="0.3" stroke-dasharray="2,8" opacity="0.15"/>');
  svgParts.push('<circle cx="' + _MM_ORIGIN_X + '" cy="' + _MM_ORIGIN_Y + '" r="' + _MM_RING_SOURCE + '" fill="none" stroke="var(--border)" stroke-width="0.3" stroke-dasharray="2,8" opacity="0.1"/>');

  /* Render edges first (below nodes) */
  for (var ei = 0; ei < edges.length; ei++) {
    var edge = edges[ei];
    var fromPos = positions[edge.from];
    var toPos = positions[edge.to];
    if (!fromPos || !toPos) continue;

    var edgeDimmed = selectedId && (!connectedIds[edge.from] || !connectedIds[edge.to]);
    var edgeOpacity = edgeDimmed ? _MM_DIM_OPACITY : 1;

    var strokeColor;
    var strokeWidth;
    if (edge.type === "section") {
      strokeColor = "var(--accent)";
      strokeWidth = 2;
    } else if (edge.type === "finding") {
      strokeColor = "var(--info)";
      strokeWidth = 0.8;
    } else if (edge.type === "source") {
      /* Thickness proportional to citation_count */
      strokeWidth = Math.max(0.5, Math.min(3, (edge.weight || 1) * 0.5));
      strokeColor = "var(--text-tertiary)";
    } else {
      strokeColor = "var(--border)";
      strokeWidth = 0.5;
    }

    svgParts.push(
      '<line class="mindmap-edge" ' +
      'x1="' + fromPos.x.toFixed(1) + '" y1="' + fromPos.y.toFixed(1) + '" ' +
      'x2="' + toPos.x.toFixed(1) + '" y2="' + toPos.y.toFixed(1) + '" ' +
      'stroke="' + strokeColor + '" stroke-width="' + strokeWidth + '" ' +
      'opacity="' + (edgeOpacity * 0.4).toFixed(2) + '" ' +
      'data-from="' + esc(edge.from) + '" data-to="' + esc(edge.to) + '"/>'
    );
  }

  /* Render nodes */
  var nodeIds = Object.keys(positions);
  /* Sort so center is last (on top), then sections, then sources, then findings */
  var typeOrder = { finding: 0, source: 1, section: 2, center: 3 };
  nodeIds.sort(function(a, b) {
    return (typeOrder[positions[a].type] || 0) - (typeOrder[positions[b].type] || 0);
  });

  for (var ni = 0; ni < nodeIds.length; ni++) {
    var nid = nodeIds[ni];
    var pos = positions[nid];
    var nodeDimmed = selectedId && !connectedIds[nid];
    var nodeOpacity = nodeDimmed ? _MM_DIM_OPACITY : 1;
    var isSelected = nid === selectedId;

    if (pos.type === "center") {
      /* Center: large circle with gradient and text */
      svgParts.push(
        '<g class="mindmap-node" data-node-id="center" ' +
        'onclick="_mmOnNodeClick(event, \'center\')" ' +
        'onmouseenter="_mmOnNodeHover(event, \'center\')" ' +
        'onmouseleave="_mmOnNodeLeave()" ' +
        'opacity="' + nodeOpacity + '">'
      );
      /* Outer glow ring */
      svgParts.push('<circle cx="' + pos.x + '" cy="' + pos.y + '" r="' + (pos.r + 6) + '" fill="none" stroke="var(--accent)" stroke-width="1.5" opacity="0.25"/>');
      /* Main circle */
      svgParts.push('<circle cx="' + pos.x + '" cy="' + pos.y + '" r="' + pos.r + '" fill="url(#mm-center-grad)" stroke="var(--accent)" stroke-width="2"/>');
      /* Center label */
      var centerLabel = truncStr(pos.label || "Research Question", 50);
      var centerLines = _mmWrapText(centerLabel, 12);
      for (var cl = 0; cl < centerLines.length; cl++) {
        var lineY = pos.y + (cl - (centerLines.length - 1) / 2) * 13;
        svgParts.push(
          '<text x="' + pos.x + '" y="' + lineY.toFixed(1) + '" ' +
          'text-anchor="middle" dominant-baseline="central" ' +
          'fill="var(--text-primary)" font-size="10" font-weight="700" ' +
          'font-family="Inter,system-ui,sans-serif" pointer-events="none">' +
          esc(centerLines[cl]) + '</text>'
        );
      }
      svgParts.push('</g>');

    } else if (pos.type === "section") {
      /* Section: medium circle with label */
      var secData = pos.data || {};
      svgParts.push(
        '<g class="mindmap-node" data-node-id="' + esc(nid) + '" ' +
        'onclick="_mmOnNodeClick(event, \'' + esc(nid) + '\')" ' +
        'onmouseenter="_mmOnNodeHover(event, \'' + esc(nid) + '\')" ' +
        'onmouseleave="_mmOnNodeLeave()" ' +
        'opacity="' + nodeOpacity + '">'
      );
      /* Selection ring */
      if (isSelected) {
        svgParts.push('<circle cx="' + pos.x.toFixed(1) + '" cy="' + pos.y.toFixed(1) + '" r="' + (pos.r + 4) + '" fill="none" stroke="var(--accent)" stroke-width="2" opacity="0.6"/>');
      }
      svgParts.push(
        '<circle cx="' + pos.x.toFixed(1) + '" cy="' + pos.y.toFixed(1) + '" r="' + pos.r + '" ' +
        'fill="var(--bg-elevated)" stroke="var(--accent)" stroke-width="1.5"/>'
      );
      /* Section title — outside the circle, offset radially outward */
      var labelAngle = pos.angle !== undefined ? pos.angle : 0;
      var labelDist = pos.r + 14;
      var labelX = pos.x + labelDist * Math.cos(labelAngle);
      var labelY = pos.y + labelDist * Math.sin(labelAngle);
      var textAnchor = "middle";
      if (Math.cos(labelAngle) > 0.3) textAnchor = "start";
      else if (Math.cos(labelAngle) < -0.3) textAnchor = "end";

      svgParts.push(
        '<text x="' + labelX.toFixed(1) + '" y="' + labelY.toFixed(1) + '" ' +
        'text-anchor="' + textAnchor + '" dominant-baseline="central" ' +
        'fill="var(--text-secondary)" font-size="10" font-weight="600" ' +
        'font-family="Inter,system-ui,sans-serif" pointer-events="none">' +
        esc(truncStr(secData.title || nid, 25)) + '</text>'
      );
      /* Finding count badge */
      if (secData.finding_count) {
        svgParts.push(
          '<text x="' + pos.x.toFixed(1) + '" y="' + (pos.y + 1).toFixed(1) + '" ' +
          'text-anchor="middle" dominant-baseline="central" ' +
          'fill="var(--accent)" font-size="10" font-weight="700" ' +
          'font-family="var(--font-mono)" pointer-events="none">' +
          secData.finding_count + '</text>'
        );
      }
      svgParts.push('</g>');

    } else if (pos.type === "finding") {
      /* Finding: small dot */
      svgParts.push(
        '<circle class="mindmap-node" data-node-id="' + esc(nid) + '" ' +
        'cx="' + pos.x.toFixed(1) + '" cy="' + pos.y.toFixed(1) + '" r="' + pos.r + '" ' +
        'fill="var(--info)" fill-opacity="0.6" stroke="var(--info)" stroke-width="0.5" ' +
        'opacity="' + nodeOpacity + '" ' +
        'onclick="_mmOnNodeClick(event, \'' + esc(nid) + '\')" ' +
        'onmouseenter="_mmOnNodeHover(event, \'' + esc(nid) + '\')" ' +
        'onmouseleave="_mmOnNodeLeave()"/>'
      );

    } else if (pos.type === "source") {
      /* Source: colored by tier */
      var srcData = pos.data || {};
      var tierColor = "var(--bronze)";
      var tierStr = (srcData.tier || "BRONZE").toUpperCase();
      if (tierStr === "GOLD") tierColor = "var(--gold)";
      else if (tierStr === "SILVER") tierColor = "var(--silver)";

      svgParts.push(
        '<g class="mindmap-node" data-node-id="' + esc(nid) + '" ' +
        'onclick="_mmOnNodeClick(event, \'' + esc(nid) + '\')" ' +
        'onmouseenter="_mmOnNodeHover(event, \'' + esc(nid) + '\')" ' +
        'onmouseleave="_mmOnNodeLeave()" ' +
        'opacity="' + nodeOpacity + '">'
      );

      /* Cross-cutting halo */
      if (srcData.cross_cutting) {
        svgParts.push(
          '<circle class="mindmap-halo" cx="' + pos.x.toFixed(1) + '" cy="' + pos.y.toFixed(1) + '" ' +
          'r="' + (pos.r + 5) + '" fill="none" stroke="' + tierColor + '" stroke-width="2" ' +
          'filter="url(#mm-glow)"/>'
        );
      }

      /* Selection ring */
      if (isSelected) {
        svgParts.push('<circle cx="' + pos.x.toFixed(1) + '" cy="' + pos.y.toFixed(1) + '" r="' + (pos.r + 3) + '" fill="none" stroke="' + tierColor + '" stroke-width="2" opacity="0.7"/>');
      }

      svgParts.push(
        '<circle cx="' + pos.x.toFixed(1) + '" cy="' + pos.y.toFixed(1) + '" r="' + pos.r + '" ' +
        'fill="' + tierColor + '" fill-opacity="0.7" stroke="' + tierColor + '" stroke-width="1"/>'
      );
      svgParts.push('</g>');
    }
  }

  canvas.innerHTML = svgParts.join("");
  _mmUpdateViewBox();
}

/* =====================================================================
   Text Wrapping for center label
   ===================================================================== */
function _mmWrapText(text, maxCharsPerLine) {
  if (!text) return [""];
  var words = text.split(" ");
  var lines = [];
  var currentLine = "";
  for (var i = 0; i < words.length; i++) {
    var testLine = currentLine ? currentLine + " " + words[i] : words[i];
    if (testLine.length > maxCharsPerLine && currentLine) {
      lines.push(currentLine);
      currentLine = words[i];
    } else {
      currentLine = testLine;
    }
  }
  if (currentLine) lines.push(currentLine);
  /* Cap at 4 lines for the center node */
  if (lines.length > 4) {
    lines = lines.slice(0, 4);
    lines[3] = truncStr(lines[3], maxCharsPerLine - 3);
  }
  return lines;
}

/* =====================================================================
   ViewBox Management (Zoom/Pan)
   ===================================================================== */
function _mmUpdateViewBox() {
  var canvas = _mmState.canvas;
  if (!canvas) return;

  var size = _MM_VIEWBOX_SIZE;
  var zoom = _mmState.zoom;
  var viewW = size / zoom;
  var viewH = size / zoom;
  var viewX = (_MM_ORIGIN_X - viewW / 2) + _mmState.panX;
  var viewY = (_MM_ORIGIN_Y - viewH / 2) + _mmState.panY;

  canvas.setAttribute("viewBox",
    viewX.toFixed(1) + " " + viewY.toFixed(1) + " " +
    viewW.toFixed(1) + " " + viewH.toFixed(1)
  );
}

function _mmApplyZoom(delta) {
  var newZoom = _mmState.zoom + delta;
  newZoom = Math.max(_MM_ZOOM_MIN, Math.min(_MM_ZOOM_MAX, newZoom));
  _mmState.zoom = newZoom;

  if (_mmState.animFrameId) cancelAnimationFrame(_mmState.animFrameId);
  _mmState.animFrameId = requestAnimationFrame(function() {
    _mmUpdateViewBox();
    _mmUpdateZoomLabel();
    _mmState.animFrameId = null;
  });
}

function _mmResetView() {
  _mmState.zoom = 1.0;
  _mmState.panX = 0;
  _mmState.panY = 0;
  _mmClearSelection();
  if (_mmState.animFrameId) cancelAnimationFrame(_mmState.animFrameId);
  _mmState.animFrameId = requestAnimationFrame(function() {
    _mmUpdateViewBox();
    _mmUpdateZoomLabel();
    _mmState.animFrameId = null;
  });
}

function _mmUpdateZoomLabel() {
  var label = document.getElementById("mindmap-zoom-label");
  if (label) label.textContent = Math.round(_mmState.zoom * 100) + "%";
}

/* =====================================================================
   Zoom Controls Overlay
   ===================================================================== */
function _mmRenderZoomControls(container) {
  var existing = document.getElementById("mindmap-zoom-controls");
  if (existing) existing.remove();

  var controls = document.createElement("div");
  controls.id = "mindmap-zoom-controls";
  controls.className = "mindmap-zoom-controls";
  controls.innerHTML =
    '<button class="mindmap-zoom-btn" onclick="_mmApplyZoom(' + _MM_ZOOM_STEP + ')" aria-label="Zoom in" title="Zoom in">+</button>' +
    '<div class="mindmap-zoom-label" id="mindmap-zoom-label">100%</div>' +
    '<button class="mindmap-zoom-btn" onclick="_mmApplyZoom(-' + _MM_ZOOM_STEP + ')" aria-label="Zoom out" title="Zoom out">&minus;</button>';

  container.style.position = "relative";
  container.appendChild(controls);
}

/* =====================================================================
   Event Handlers: Wheel (zoom), Drag (pan), Double-click (reset)
   ===================================================================== */
function _mmOnWheel(evt) {
  evt.preventDefault();
  /* Debounce wheel events using requestAnimationFrame */
  if (_mmState.wheelTimeout) return;
  _mmState.wheelTimeout = setTimeout(function() {
    _mmState.wheelTimeout = null;
  }, _MM_WHEEL_DEBOUNCE_MS);

  var delta = evt.deltaY < 0 ? _MM_ZOOM_STEP : -_MM_ZOOM_STEP;
  _mmApplyZoom(delta);
}

function _mmOnMouseDown(evt) {
  /* Only start drag on primary button and not on a node */
  if (evt.button !== 0) return;
  if (evt.target.closest && evt.target.closest(".mindmap-node")) return;

  _mmState.dragging = true;
  _mmState.dragStartX = evt.clientX;
  _mmState.dragStartY = evt.clientY;
  _mmState.dragStartPanX = _mmState.panX;
  _mmState.dragStartPanY = _mmState.panY;
  evt.preventDefault();

  if (_mmState.canvas) _mmState.canvas.style.cursor = "grabbing";
}

function _mmOnMouseMove(evt) {
  if (!_mmState.dragging) return;

  var canvas = _mmState.canvas;
  if (!canvas) return;

  /* Convert screen px delta to viewbox coordinate delta */
  var canvasRect = canvas.getBoundingClientRect();
  var viewW = _MM_VIEWBOX_SIZE / _mmState.zoom;
  var viewH = _MM_VIEWBOX_SIZE / _mmState.zoom;
  var scaleX = viewW / canvasRect.width;
  var scaleY = viewH / canvasRect.height;

  var dx = (evt.clientX - _mmState.dragStartX) * scaleX;
  var dy = (evt.clientY - _mmState.dragStartY) * scaleY;

  _mmState.panX = _mmState.dragStartPanX - dx;
  _mmState.panY = _mmState.dragStartPanY - dy;

  if (_mmState.animFrameId) cancelAnimationFrame(_mmState.animFrameId);
  _mmState.animFrameId = requestAnimationFrame(function() {
    _mmUpdateViewBox();
    _mmState.animFrameId = null;
  });
}

function _mmOnMouseUp() {
  _mmState.dragging = false;
  if (_mmState.canvas) _mmState.canvas.style.cursor = "grab";
}

function _mmOnDblClick(evt) {
  /* Double-click on background (not on a node) resets view */
  if (evt.target.closest && evt.target.closest(".mindmap-node")) return;
  _mmResetView();
}

/* =====================================================================
   Node Interaction: Click, Hover
   ===================================================================== */
function _mmOnNodeClick(evt, nodeId) {
  evt.stopPropagation();
  if (_mmState.selectedNodeId === nodeId) {
    /* Clicking the same node again deselects */
    _mmClearSelection();
    return;
  }

  _mmState.selectedNodeId = nodeId;
  _mmRenderSvg();

  /* Show info panel */
  var pos = _mmState.nodePositions[nodeId];
  if (!pos) return;
  var nodeData;
  if (pos.type === "center") {
    nodeData = { type: "center", label: pos.label };
  } else if (pos.type === "section") {
    nodeData = pos.data || {};
    nodeData.type = "section";
  } else if (pos.type === "finding") {
    nodeData = pos.data || {};
    nodeData.type = "finding";
  } else if (pos.type === "source") {
    nodeData = pos.data || {};
    nodeData.type = "source";
  } else {
    nodeData = { type: pos.type, label: pos.label };
  }
  _mmShowInfoPanel(nodeData);
}

function _mmOnNodeHover(evt, nodeId) {
  _mmState.hoveredNodeId = nodeId;
  var pos = _mmState.nodePositions[nodeId];
  if (!pos) return;

  var html = "";
  if (pos.type === "center") {
    html = '<div class="mindmap-tooltip-title">' + esc(truncStr(pos.label, 80)) + '</div>';
    html += '<div class="mindmap-tooltip-row"><span class="mindmap-tooltip-key">Type</span><span class="mindmap-tooltip-val">Center</span></div>';
  } else if (pos.type === "section") {
    var secData = pos.data || {};
    html = '<div class="mindmap-tooltip-title">' + esc(secData.title || pos.label) + '</div>';
    html += '<div class="mindmap-tooltip-row"><span class="mindmap-tooltip-key">Findings</span><span class="mindmap-tooltip-val">' + (secData.finding_count || 0) + '</span></div>';
  } else if (pos.type === "finding") {
    var fData = pos.data || {};
    html = '<div class="mindmap-tooltip-title">Finding</div>';
    html += '<div class="mindmap-tooltip-text">' + esc(truncStr(fData.text || "", 200)) + '</div>';
    if (fData.evidence_id) {
      html += '<div class="mindmap-tooltip-row" style="margin-top:4px"><span class="mindmap-tooltip-key">Evidence</span><span class="mindmap-tooltip-val">' + esc(truncStr(fData.evidence_id, 20)) + '</span></div>';
    }
  } else if (pos.type === "source") {
    var srcData = pos.data || {};
    html = '<div class="mindmap-tooltip-title">' + esc(truncStr(srcData.title || "Source", 60)) + '</div>';
    if (srcData.url) {
      html += '<div style="font-size:10px;color:var(--text-tertiary);margin-bottom:4px;word-break:break-all">' + esc(truncStr(srcData.url, 60)) + '</div>';
    }
    var tipTierClass = "mindmap-tier-" + (srcData.tier || "bronze").toLowerCase();
    html += '<span class="mindmap-tier-badge ' + tipTierClass + '">' + esc((srcData.tier || "BRONZE").toUpperCase()) + '</span>';
    html += '<div class="mindmap-tooltip-row" style="margin-top:4px"><span class="mindmap-tooltip-key">Citations</span><span class="mindmap-tooltip-val">' + (srcData.citation_count || 0) + '</span></div>';
    if (srcData.cross_cutting) {
      html += '<div class="mindmap-tooltip-row"><span class="mindmap-tooltip-key">Cross-cutting</span><span class="mindmap-tooltip-val" style="color:var(--warning)">Yes</span></div>';
    }
  }

  _mmShowTooltip(evt, html);
}

function _mmOnNodeLeave() {
  _mmState.hoveredNodeId = null;
  _mmHideTooltip();
}

function _mmClearSelection() {
  _mmState.selectedNodeId = null;
  _mmRenderSvg();
  if (_mmState.infoPanelEl) {
    _mmState.infoPanelEl.classList.remove("mindmap-info-visible");
  }
}

/* =====================================================================
   Event Listener Binding/Unbinding
   ===================================================================== */
function _mmBindEvents(canvas) {
  /* Remove any previous listeners (idempotent cleanup via named refs) */
  _mmUnbindEvents(canvas);

  canvas.addEventListener("wheel", _mmOnWheel, { passive: false });
  canvas.addEventListener("mousedown", _mmOnMouseDown);
  canvas.addEventListener("dblclick", _mmOnDblClick);
  /* Mouse move and up are on window so dragging works outside SVG */
  window.addEventListener("mousemove", _mmOnMouseMove);
  window.addEventListener("mouseup", _mmOnMouseUp);

  canvas.style.cursor = "grab";
  canvas.style.userSelect = "none";
}

function _mmUnbindEvents(canvas) {
  if (!canvas) return;
  canvas.removeEventListener("wheel", _mmOnWheel);
  canvas.removeEventListener("mousedown", _mmOnMouseDown);
  canvas.removeEventListener("dblclick", _mmOnDblClick);
  window.removeEventListener("mousemove", _mmOnMouseMove);
  window.removeEventListener("mouseup", _mmOnMouseUp);
}

/* =====================================================================
   Data Fetching
   ===================================================================== */
function _mmFetchData(vectorId, callback) {
  _mmState.loading = true;
  _mmState.error = null;

  fetch("/api/research/mindmap/" + encodeURIComponent(vectorId))
    .then(function(response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status + ": " + response.statusText);
      }
      return response.json();
    })
    .then(function(data) {
      _mmState.loading = false;
      _mmState.data = data;
      _mmState.error = null;
      callback(null, data);
    })
    .catch(function(err) {
      _mmState.loading = false;
      _mmState.error = err.message || String(err);
      _mmState.data = null;
      callback(err, null);
    });
}

/* =====================================================================
   Loading / Empty / Error State Rendering
   ===================================================================== */
function _mmShowLoading(canvas) {
  canvas.innerHTML =
    '<foreignObject x="0" y="0" width="100%" height="100%">' +
    '<div xmlns="http://www.w3.org/1999/xhtml" class="mindmap-loading">' +
    '<div class="mindmap-loading-spinner"></div>' +
    '<span>Loading mind map...</span>' +
    '</div></foreignObject>';
}

function _mmShowError(canvas, message) {
  canvas.innerHTML =
    '<text x="50%" y="50%" text-anchor="middle" fill="var(--error)" ' +
    'font-size="13" font-family="Inter,system-ui,sans-serif">' +
    esc(message) + '</text>';
}

function _mmShowEmpty(canvas, emptyEl, message) {
  canvas.innerHTML = '';
  if (emptyEl) {
    emptyEl.style.display = "block";
    emptyEl.textContent = message || "No mind map data available. Run a research query first.";
  } else {
    canvas.innerHTML =
      '<text x="50%" y="50%" text-anchor="middle" fill="var(--text-tertiary)" ' +
      'font-size="13" font-family="Inter,system-ui,sans-serif">' +
      esc(message || "Mind Map: awaiting data...") + '</text>';
  }
}

/* =====================================================================
   Cleanup
   ===================================================================== */
function _mmCleanup() {
  if (_mmState.canvas) {
    _mmUnbindEvents(_mmState.canvas);
  }
  if (_mmState.animFrameId) {
    cancelAnimationFrame(_mmState.animFrameId);
    _mmState.animFrameId = null;
  }
  if (_mmState.wheelTimeout) {
    clearTimeout(_mmState.wheelTimeout);
    _mmState.wheelTimeout = null;
  }
  /* Remove info panel if attached */
  if (_mmState.infoPanelEl && _mmState.infoPanelEl.parentElement) {
    _mmState.infoPanelEl.remove();
  }
  /* Remove stats bar if attached */
  var statsBar = document.getElementById("mindmap-stats-bar");
  if (statsBar) statsBar.remove();
  /* Remove zoom controls */
  var zoomCtrl = document.getElementById("mindmap-zoom-controls");
  if (zoomCtrl) zoomCtrl.remove();

  _mmState.selectedNodeId = null;
  _mmState.hoveredNodeId = null;
  _mmState.nodePositions = {};
  _mmState.edgeList = [];
  _mmState.data = null;
  _mmState.initialized = false;
}

/* =====================================================================
   Public API: buildMindMapGraph(canvas, emptyEl)
   Called by evidence_browser.js when graphMode === "mindmap"
   ===================================================================== */
function buildMindMapGraph(canvas, emptyEl) {
  _mmInjectStyles();

  /* Cleanup previous render */
  if (_mmState.canvas && _mmState.canvas !== canvas) {
    _mmCleanup();
  }

  _mmState.canvas = canvas;
  _mmState.emptyEl = emptyEl;

  /* Check for vector ID */
  var vectorId = (typeof state !== "undefined" && state.vectorId) ? state.vectorId : null;
  if (!vectorId || vectorId === "--") {
    _mmShowEmpty(canvas, emptyEl, "Select a research vector to view the mind map.");
    return;
  }

  /* Hide empty element */
  if (emptyEl) emptyEl.style.display = "none";

  /* Show loading */
  _mmShowLoading(canvas);

  /* Fetch mind map data */
  _mmFetchData(vectorId, function(err, data) {
    if (err) {
      _mmShowError(canvas, "Failed to load mind map: " + (err.message || String(err)));
      return;
    }

    if (!data || (!data.sections && !data.findings && !data.sources)) {
      _mmShowEmpty(canvas, emptyEl, "No mind map data available for this vector.");
      return;
    }

    /* Validate we have meaningful data */
    var hasSections = data.sections && data.sections.length > 0;
    var hasFindings = data.findings && data.findings.length > 0;
    var hasSources = data.sources && data.sources.length > 0;

    if (!hasSections && !hasFindings && !hasSources) {
      _mmShowEmpty(canvas, emptyEl, "Mind map is empty. Research may still be in progress.");
      return;
    }

    /* Set initial viewBox */
    canvas.setAttribute("viewBox", "0 0 " + _MM_VIEWBOX_SIZE + " " + _MM_VIEWBOX_SIZE);
    canvas.setAttribute("preserveAspectRatio", "xMidYMid meet");

    /* Compute layout */
    _mmComputeLayout(data);

    /* Reset view state */
    _mmState.zoom = 1.0;
    _mmState.panX = 0;
    _mmState.panY = 0;
    _mmState.selectedNodeId = null;

    /* Render SVG */
    _mmRenderSvg();

    /* Bind interaction events */
    _mmBindEvents(canvas);

    /* Render stats bar above the SVG */
    var svgParent = canvas.parentElement;
    if (svgParent) {
      _mmRenderStatsBar(svgParent);
      _mmRenderZoomControls(svgParent);
    }

    _mmState.initialized = true;
  });
}
