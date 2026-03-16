/* =====================================================================
   campaign_manager.js — Campaign Map + Planner (NOVA Phase 1)
   Renders campaign grid matrix, active vector sidebar, planner UI.
   Uses NODE_ORDER / NODE_LABELS from core.js.
   ===================================================================== */

/* =====================================================================
   Module State
   ===================================================================== */
var _cm = {
  activeCampaignId: null,
  campaigns: [],
  liveData: null,
  pollTimer: null,
  subView: "map",          // "map" | "planner" | "library" | "results"
  filter: "all",           // "all" | "running" | "completed" | "failed"
  searchQuery: "",
  collapsedGroups: new Set(),
  tooltipEl: null,
  plannerDepth: "standard",
  plannerPlan: null,
  plannerLoading: false,
  plannerEditingVector: null,   // "plan-{d}-{v}" key of vector being edited
  // Vector Library state
  libraryStages: null,          // Immutable cache from API
  libraryWorkingCopy: null,     // Deep mutable copy with editing state
  libraryLoading: false,
  libraryApplication: "",
  libraryDepth: "standard",
  libraryResearchBrief: "C-POLAR is a long-duration (5-year) antimicrobial coating technology. POLARIS serves the C-POLAR business intelligence mission across 13 strategic stages: contamination problem identification, cost of pain quantification, solution landscape analysis, technology gap identification, C-POLAR value proposition, market size quantification (TAM/SAM/SOM), competitive intelligence, regulatory pathway analysis, adoption barrier mapping, go-to-market strategy, risk and mitigation analysis, implementation roadmap, and ROI projection. Applications include household water filters, HVAC systems, medical devices, food processing equipment, and more. Markets: North America, Europe, Asia-Pacific (regional) and Global. Research should prioritize peer-reviewed sources, regulatory data, and quantified metrics. Every factual claim must be cited to a verifiable source.",
  libraryBriefExpanded: false,
  _editingStage: null,          // Index of stage being name-edited
  _editingVector: null,         // {s: stageIdx, v: vectorIdx} being question-edited
  // Results Dashboard state
  resultsFilter: "all",          // "all" | "completed" | "failed"
  resultsSortBy: "index",        // "index" | "faithfulness" | "evidence" | "words"
  resultsPanelVector: null,      // vector_id of open result panel
  resultsPanelData: null,        // Loaded result data
  resultsPanelTab: "report",     // "report" | "evidence" | "citations" | "trace"
  resultsPanelLoading: false,
};

/* =====================================================================
   Initialization
   ===================================================================== */
function initCampaignManager() {
  // Create tooltip element once
  if (!_cm.tooltipEl) {
    var tip = document.createElement("div");
    tip.className = "cm-tooltip";
    tip.style.display = "none";
    document.body.appendChild(tip);
    _cm.tooltipEl = tip;
  }
}

document.addEventListener("DOMContentLoaded", function() {
  initCampaignManager();
});

/* =====================================================================
   Top-Level View Renderer
   ===================================================================== */
function renderCampaignView(targetEl) {
  // Render into explicit target, or overlay if open, or tab pane
  var container = targetEl
    || _cm._overlayTarget
    || document.getElementById("view-campaigns");
  if (!container) return;

  var html = '<div class="campaign-view">';

  // Top bar: campaign selector + toggle + new btn
  html += '<div class="cm-top-bar">';

  // Back to dashboard button
  html += '<button class="cm-back-btn" onclick="backToCampaignDashboard()" title="Back to Dashboard">&larr;</button>';

  // Campaign selector dropdown
  var activeName = "Select campaign...";
  for (var ci = 0; ci < _cm.campaigns.length; ci++) {
    if (_cm.campaigns[ci].campaign_id === _cm.activeCampaignId) {
      activeName = _cm.campaigns[ci].name;
      break;
    }
  }
  html += '<div class="cm-campaign-dd" id="cm-campaign-dd">';
  html += '<button class="cm-campaign-trigger" onclick="toggleCampaignMenu()">';
  html += '<span class="cm-campaign-trigger-text">' + _escHtml(activeName) + '</span>';
  html += '<svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 4l3 3 3-3" stroke="currentColor" stroke-width="1.5" fill="none"/></svg>';
  html += '</button>';
  html += '<div class="cm-campaign-menu" id="cm-campaign-menu">';
  html += '<button class="cm-campaign-item' + (!_cm.activeCampaignId ? " active" : "") +
    '" onclick="pickCampaign(\'\')"><span class="cm-campaign-item-name">Select campaign...</span></button>';
  for (var ci2 = 0; ci2 < _cm.campaigns.length; ci2++) {
    var cc = _cm.campaigns[ci2];
    var isActive = cc.campaign_id === _cm.activeCampaignId ? " active" : "";
    html += '<button class="cm-campaign-item' + isActive +
      '" onclick="pickCampaign(\'' + _escHtml(cc.campaign_id) + '\')">';
    html += '<span class="cm-campaign-item-name">' + _escHtml(cc.name) + '</span>';
    if (cc.status) html += '<span class="cm-campaign-item-status">' + cc.status + '</span>';
    html += '</button>';
  }
  html += '</div></div>';

  // Map / Planner / Library / Results toggle
  html += '<div class="cm-toggle-group">';
  html += '<button class="cm-toggle-btn' + (_cm.subView === "map" ? " active" : "") +
    '" onclick="showCampaignMap()">Status</button>';
  html += '<button class="cm-toggle-btn' + (_cm.subView === "planner" ? " active" : "") +
    '" onclick="showPlanner()">Planner</button>';
  html += '<button class="cm-toggle-btn' + (_cm.subView === "library" ? " active" : "") +
    '" onclick="showLibrary()">Library</button>';
  html += '<button class="cm-toggle-btn' + (_cm.subView === "results" ? " active" : "") +
    '" onclick="showResults()">Results</button>';
  html += '</div>';

  html += '<button class="cm-new-btn" onclick="showPlanner()">+ New Campaign</button>';
  html += '</div>';

  // Sub-views
  if (_cm.subView === "planner") {
    html += _renderPlannerView();
  } else if (_cm.subView === "library") {
    html += _renderLibraryView();
  } else if (_cm.subView === "results") {
    html += _renderResultsView();
  } else {
    html += _renderMapView();
  }

  html += '</div>';
  container.innerHTML = html;

  // Load campaign list if empty
  if (_cm.campaigns.length === 0) {
    loadCampaignList();
  }
}

/* =====================================================================
   Map View
   ===================================================================== */
function _renderMapView() {
  var html = '<div class="campaign-map-view">';

  // Main map area
  html += '<div class="cm-map-container">';

  if (!_cm.liveData || !_cm.activeCampaignId) {
    html += _renderEmptyState();
    html += '</div>';
    // Sidebar (empty)
    html += '<div class="cm-sidebar">';
    html += '<div class="cm-sidebar-title">Active Vectors</div>';
    html += '<div class="cm-sidebar-empty">No active vectors</div>';
    html += '</div>';
    html += '</div>';
    return html;
  }

  // Filter bar
  html += _renderFilterBar();

  // Matrix
  html += '<div class="cm-matrix-wrapper">';
  html += _renderMatrix();
  html += '</div>';

  // Legend
  html += _renderLegend();

  html += '</div>';

  // Sidebar
  html += _renderActiveSidebar();

  html += '</div>';
  return html;
}

function _renderEmptyState() {
  return '<div class="cm-empty-state">' +
    '<div class="cm-empty-state-icon">&#x1F5FA;</div>' +
    '<div class="cm-empty-state-title">No campaign selected</div>' +
    '<div class="cm-empty-state-desc">' +
    'Select a campaign from the dropdown above to view its progress matrix, ' +
    'or click Planner to create a new AI-generated research plan.' +
    '</div></div>';
}

function _renderFilterBar() {
  var filters = [
    { id: "all", label: "All" },
    { id: "running", label: "Running" },
    { id: "completed", label: "Completed" },
    { id: "failed", label: "Failed" },
  ];

  var html = '<div class="cm-filter-bar">';
  for (var i = 0; i < filters.length; i++) {
    var f = filters[i];
    var cls = f.id === _cm.filter ? " active" : "";
    html += '<button class="cm-filter-chip' + cls + '" onclick="setCampaignFilter(\'' +
      f.id + '\')">' + f.label + '</button>';
  }

  html += '<input type="text" class="cm-search-input" placeholder="Search vectors..." ' +
    'value="' + _escHtml(_cm.searchQuery) + '" oninput="searchCampaignVectors(this.value)">';
  html += '</div>';
  return html;
}

/* =====================================================================
   Matrix Grid
   ===================================================================== */
function _renderMatrix() {
  if (!_cm.liveData || !_cm.liveData.queries) return "";

  var queries = _filterQueries(_cm.liveData.queries);
  if (queries.length === 0) {
    return '<div class="cm-empty-state" style="padding:24px">' +
      '<div class="cm-empty-state-desc">No vectors match the current filter.</div></div>';
  }

  var html = '<table class="cm-matrix-table">';
  html += _buildMatrixHeader();
  html += '<tbody>';

  for (var i = 0; i < queries.length; i++) {
    html += _buildQueryRow(queries[i], i);
  }

  html += '</tbody></table>';
  return html;
}

function _buildMatrixHeader() {
  var html = '<thead><tr>';
  html += '<th class="cm-header-cell cm-query-cell">Query</th>';
  for (var n = 0; n < NODE_ORDER.length; n++) {
    var nodeName = NODE_ORDER[n];
    var label = NODE_LABELS[nodeName] || nodeName;
    html += '<th class="cm-header-cell">' + label + '</th>';
  }
  html += '</tr></thead>';
  return html;
}

function _buildQueryRow(q, idx) {
  var nodeStatus = q.node_status || {};
  var nodeMetrics = q.node_metrics || {};

  var html = '<tr>';
  // Query label cell
  var statusCls = q.status || "queued";
  html += '<td class="cm-query-cell" title="' + _escHtml(q.query) + '">';
  html += '<span class="cm-query-status ' + statusCls + '"></span>';
  html += _escHtml(_truncate(q.query, 40));
  html += '</td>';

  // Node cells
  for (var n = 0; n < NODE_ORDER.length; n++) {
    var nodeName = NODE_ORDER[n];
    var cellStatus = _getCellClass(nodeStatus, nodeName, q.status);
    html += '<td class="cm-cell ' + cellStatus + '" ' +
      'onmouseenter="showCellTooltip(event, ' + idx + ', \'' + nodeName + '\')" ' +
      'onmouseleave="hideCellTooltip()" ' +
      'onclick="onCampaignCellClick(\'' + (_cm.activeCampaignId || "") + '\', ' + idx + ', \'' + nodeName + '\')">';
    html += '<span class="cm-cell-dot ' + cellStatus + '"></span>';
    html += '</td>';
  }

  html += '</tr>';
  return html;
}

function _getCellClass(nodeStatus, nodeName, queryStatus) {
  if (nodeStatus[nodeName]) {
    return nodeStatus[nodeName];
  }
  // If query hasn't started, all cells are idle
  if (queryStatus === "queued") return "idle";
  if (queryStatus === "failed") return "idle";
  if (queryStatus === "completed") return "passed";
  return "idle";
}

/* =====================================================================
   Filter Logic
   ===================================================================== */
function _filterQueries(queries) {
  var result = [];
  for (var i = 0; i < queries.length; i++) {
    var q = queries[i];

    // Status filter
    if (_cm.filter !== "all" && q.status !== _cm.filter) continue;

    // Search filter
    if (_cm.searchQuery) {
      var sq = _cm.searchQuery.toLowerCase();
      if ((q.query || "").toLowerCase().indexOf(sq) === -1 &&
          (q.vector_id || "").toLowerCase().indexOf(sq) === -1) {
        continue;
      }
    }

    result.push(q);
  }
  return result;
}

function setCampaignFilter(f) {
  _cm.filter = f;
  renderCampaignView();
}

function searchCampaignVectors(q) {
  _cm.searchQuery = q;
  // Debounce re-render
  if (_cm._searchTimer) clearTimeout(_cm._searchTimer);
  _cm._searchTimer = setTimeout(function() {
    renderCampaignView();
  }, 200);
}

/* =====================================================================
   Legend
   ===================================================================== */
function _renderLegend() {
  var items = [
    { cls: "idle", label: "Idle" },
    { cls: "running", label: "Running" },
    { cls: "passed", label: "Passed" },
    { cls: "warning", label: "Warning" },
    { cls: "failed", label: "Failed" },
  ];

  var html = '<div class="cm-legend">';
  for (var i = 0; i < items.length; i++) {
    html += '<div class="cm-legend-item">';
    html += '<div class="cm-legend-dot ' + items[i].cls + '"></div>';
    html += items[i].label;
    html += '</div>';
  }
  html += '</div>';
  return html;
}

/* =====================================================================
   Active Vector Sidebar
   ===================================================================== */
function _renderActiveSidebar() {
  var html = '<div class="cm-sidebar">';
  html += '<div class="cm-sidebar-title">Active Vectors</div>';

  if (!_cm.liveData || !_cm.liveData.queries) {
    html += '<div class="cm-sidebar-empty">No active vectors</div>';
    html += '</div>';
    return html;
  }

  var running = [];
  for (var i = 0; i < _cm.liveData.queries.length; i++) {
    var q = _cm.liveData.queries[i];
    if (q.status === "running") running.push(q);
  }

  if (running.length === 0) {
    html += '<div class="cm-sidebar-empty">No active vectors</div>';
    html += '</div>';
    return html;
  }

  for (var j = 0; j < running.length; j++) {
    html += _renderActiveCard(running[j]);
  }

  html += '</div>';
  return html;
}

function _renderActiveCard(q) {
  var nodeLabel = q.current_node ? (NODE_LABELS[q.current_node] || q.current_node) : "Starting...";
  var elapsed = q.elapsed_ms ? _formatDuration(q.elapsed_ms) : "--";
  var evCount = q.evidence_count || 0;
  var faith = q.faithfulness != null ? (q.faithfulness * 100).toFixed(0) + "%" : "--";

  var html = '<div class="cm-active-card">';
  html += '<div class="cm-active-id">' + _escHtml(q.vector_id || "--") + '</div>';
  html += '<div class="cm-active-query">' + _escHtml(_truncate(q.query, 50)) + '</div>';
  html += '<div class="cm-active-stage">Stage: ' + _escHtml(nodeLabel) + '</div>';
  html += '<div class="cm-active-stats">';
  html += '<span class="cm-active-stat">Ev: ' + evCount + '</span>';
  html += '<span class="cm-active-stat">Faith: ' + faith + '</span>';
  html += '<span class="cm-active-stat">' + elapsed + '</span>';
  html += '</div>';
  html += '<button class="cm-follow-btn" onclick="followCampaignVector(\'' +
    _escHtml(q.vector_id || "") + '\')">Follow</button>';
  html += '</div>';
  return html;
}

/* =====================================================================
   Tooltip
   ===================================================================== */
function showCellTooltip(e, queryIdx, nodeName) {
  if (!_cm.tooltipEl || !_cm.liveData || !_cm.liveData.queries) return;

  var q = _cm.liveData.queries[queryIdx];
  if (!q) return;

  var nodeStatus = (q.node_status || {})[nodeName] || "idle";
  var nodeMetrics = (q.node_metrics || {})[nodeName] || {};
  var nodeLabel = NODE_LABELS[nodeName] || nodeName;

  var html = '<div class="cm-tooltip-title">' + _escHtml(nodeLabel) + '</div>';
  html += '<div class="cm-tooltip-row"><span>Status</span><span class="cm-tooltip-value">' +
    nodeStatus + '</span></div>';

  if (nodeMetrics.duration_ms) {
    html += '<div class="cm-tooltip-row"><span>Duration</span><span class="cm-tooltip-value">' +
      _formatDuration(nodeMetrics.duration_ms) + '</span></div>';
  }

  if (q.evidence_count != null) {
    html += '<div class="cm-tooltip-row"><span>Evidence</span><span class="cm-tooltip-value">' +
      q.evidence_count + '</span></div>';
  }

  if (q.faithfulness != null) {
    html += '<div class="cm-tooltip-row"><span>Faithfulness</span><span class="cm-tooltip-value">' +
      (q.faithfulness * 100).toFixed(1) + '%</span></div>';
  }

  if (q.elapsed_ms) {
    html += '<div class="cm-tooltip-row"><span>Elapsed</span><span class="cm-tooltip-value">' +
      _formatDuration(q.elapsed_ms) + '</span></div>';
  }

  _cm.tooltipEl.innerHTML = html;
  _cm.tooltipEl.style.display = "block";

  // Position near cursor
  var x = e.clientX + 12;
  var y = e.clientY + 12;
  if (x + 280 > window.innerWidth) x = e.clientX - 290;
  if (y + 150 > window.innerHeight) y = e.clientY - 160;
  _cm.tooltipEl.style.left = x + "px";
  _cm.tooltipEl.style.top = y + "px";
}

function hideCellTooltip() {
  if (_cm.tooltipEl) _cm.tooltipEl.style.display = "none";
}

/* =====================================================================
   Interactions
   ===================================================================== */
function onCampaignCellClick(campaignId, queryIdx, nodeName) {
  if (!_cm.liveData || !_cm.liveData.queries) return;
  var q = _cm.liveData.queries[queryIdx];
  if (!q || !q.vector_id) return;

  // Navigate to Research tab with this vector focused
  followCampaignVector(q.vector_id);
}

function followCampaignVector(vectorId) {
  if (!vectorId) return;
  // Switch to research view
  if (typeof switchView === "function") {
    switchView("research");
  }
  // Set vector ID in state
  if (typeof state !== "undefined") {
    state.vectorId = vectorId;
  }
}

function toggleCampaignGroup(groupId) {
  if (_cm.collapsedGroups.has(groupId)) {
    _cm.collapsedGroups.delete(groupId);
  } else {
    _cm.collapsedGroups.add(groupId);
  }
  renderCampaignView();
}

/* =====================================================================
   Data Fetching
   ===================================================================== */
function loadCampaignList() {
  fetch("/api/campaigns")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _cm.campaigns = data.campaigns || [];
      _updateCampaignBadge();
      // Re-render to update campaign dropdown with fresh list
      renderCampaignView();
    })
    .catch(function(err) {
      console.warn("Failed to load campaigns:", err);
    });
}

function toggleCampaignMenu() {
  var menu = document.getElementById("cm-campaign-menu");
  if (!menu) return;
  var isOpen = menu.classList.contains("open");
  // Close all other menus
  var all = document.querySelectorAll(".cm-depth-menu.open, .cm-campaign-menu.open");
  for (var i = 0; i < all.length; i++) all[i].classList.remove("open");
  if (!isOpen) menu.classList.add("open");
}

function pickCampaign(id) {
  var menu = document.getElementById("cm-campaign-menu");
  if (menu) menu.classList.remove("open");
  selectCampaign(id);
}

// Close campaign menu on outside click
document.addEventListener("click", function(e) {
  if (!e.target.closest(".cm-campaign-dd")) {
    var menu = document.getElementById("cm-campaign-menu");
    if (menu) menu.classList.remove("open");
  }
});

function selectCampaign(id) {
  stopCampaignPoll();
  _cm.activeCampaignId = id || null;
  _cm.liveData = null;

  if (!id) {
    renderCampaignView();
    return;
  }

  fetchCampaignLive(id);
  startCampaignPoll(id);
}

function fetchCampaignLive(id) {
  if (!id) return;

  fetch("/api/campaigns/" + encodeURIComponent(id) + "/live")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _cm.liveData = data;
      _updateCampaignBadge();
      renderCampaignView();
    })
    .catch(function(err) {
      console.warn("Failed to fetch campaign live data:", err);
    });
}

function startCampaignPoll(id) {
  stopCampaignPoll();
  _cm.pollTimer = setInterval(function() {
    fetchCampaignLive(id);
  }, 2000);
}

function stopCampaignPoll() {
  if (_cm.pollTimer) {
    clearInterval(_cm.pollTimer);
    _cm.pollTimer = null;
  }
}

/* =====================================================================
   SSE Integration
   ===================================================================== */
function processCampaignEvent(ev) {
  if (!_cm.activeCampaignId || !_cm.liveData || !_cm.liveData.queries) return;

  var evVid = ev.vid || "";
  if (!evVid) return;

  // Find matching query in active campaign
  var q = null;
  for (var i = 0; i < _cm.liveData.queries.length; i++) {
    if (_cm.liveData.queries[i].vector_id === evVid) {
      q = _cm.liveData.queries[i];
      break;
    }
  }
  if (!q) return;

  var evType = ev.type || "";
  var node = ev.node || "";

  // Update in-memory state for immediate cell updates
  if (evType === "node_start" && node) {
    if (!q.node_status) q.node_status = {};
    q.node_status[node] = "running";
    q.current_node = node;
  } else if (evType === "node_end" && node) {
    if (!q.node_status) q.node_status = {};
    q.node_status[node] = "passed";
  }

  // Targeted DOM update: find the specific cell and update its class
  var cells = document.querySelectorAll(".cm-cell");
  // Re-render is cheap enough for now; targeted update is optimization
  renderCampaignView();
}

/* =====================================================================
   Sub-View Toggles
   ===================================================================== */
function backToCampaignDashboard() {
  stopCampaignPoll();
  _cm.activeCampaignId = null;
  _cm.liveData = null;
  _cm.subView = "library";
  renderCampaignView();
  // Ensure library data is loaded
  if (!_cm.libraryStages && !_cm.libraryLoading) {
    showLibrary();
  }
}

function showPlanner() {
  _cm.subView = "planner";
  renderCampaignView();
}

function showCampaignMap() {
  _cm.subView = "map";
  renderCampaignView();
}

function showLibrary() {
  _cm.subView = "library";
  renderCampaignView();
  // Fetch stages on first open (cached after)
  if (!_cm.libraryStages && !_cm.libraryLoading) {
    _cm.libraryLoading = true;
    renderCampaignView();
    fetch("/api/vectors/library")
      .then(function(r) { return r.json(); })
      .then(function(data) {
        _cm.libraryStages = data.stages || [];
        _cm.libraryLoading = false;
        _initLibraryWorkingCopy();
        renderCampaignView();
        // Restore application input value after re-render
        var inp = document.getElementById("library-app-input");
        if (inp && _cm.libraryApplication) inp.value = _cm.libraryApplication;
      })
      .catch(function(err) {
        _cm.libraryLoading = false;
        console.error("Failed to load vector library:", err);
        renderCampaignView();
      });
  }
}

/* Deep-copy libraryStages into libraryWorkingCopy with editing state */
function _initLibraryWorkingCopy() {
  var regionKeys = ["NORTH_AMERICA", "EUROPE", "ASIA_PACIFIC"];
  var copy = [];
  for (var s = 0; s < _cm.libraryStages.length; s++) {
    var src = _cm.libraryStages[s];
    var templates = [];
    var srcTemplates = src.templates || [];
    for (var t = 0; t < srcTemplates.length; t++) {
      var tmpl = srcTemplates[t];
      // Multi-region: all 4 options always available
      // Regional stages default: one regional checkbox per vector (cycling NA/EU/AP)
      // Global stages default: GLOBAL checked
      var regSel = {};
      if (src.is_regional) {
        regSel = {
          GLOBAL: false,
          NORTH_AMERICA: (t % 3) === 0,
          EUROPE: (t % 3) === 1,
          ASIA_PACIFIC: (t % 3) === 2,
        };
      } else {
        regSel = { GLOBAL: true, NORTH_AMERICA: false, EUROPE: false, ASIA_PACIFIC: false };
      }
      templates.push({
        vector_number: tmpl.vector_number,
        question_template: tmpl.question_template,
        enabled: true,
        regions_selected: regSel,
      });
    }
    copy.push({
      stage: src.stage,
      name: src.name,
      is_regional: src.is_regional,
      vector_count: src.vector_count,
      enabled: true,
      templates: templates,
    });
  }
  _cm.libraryWorkingCopy = copy;
}

/* =====================================================================
   Planner View
   ===================================================================== */
function _renderPlannerView() {
  var html = '<div class="planner-view">';

  html += '<div class="planner-section-title">Research Planner</div>';

  // Query input
  html += '<textarea class="planner-query-input" id="planner-query" ' +
    'placeholder="Enter a broad research topic or question..."></textarea>';

  // Depth dropdown + Generate button row
  html += '<div class="planner-depth-row">';
  html += _renderDepthDropdown("planner", _cm.plannerDepth);
  html += '<button class="planner-generate-btn" id="planner-gen-btn" ' +
    'onclick="generatePlan()"' + (_cm.plannerLoading ? " disabled" : "") +
    '>Generate Plan</button>';
  html += '</div>';

  // Loading state
  if (_cm.plannerLoading) {
    html += '<div class="planner-loading">';
    html += '<div class="planner-spinner"></div>';
    html += '<div>Generating research plan...</div>';
    html += '</div>';
  }

  // Plan card
  if (_cm.plannerPlan && !_cm.plannerLoading) {
    html += _renderPlanCard(_cm.plannerPlan);
  }

  html += '</div>';
  return html;
}

var _depthLabels = { quick: "Quick", standard: "Standard", deep: "Deep" };
var _depthDescs = { quick: "Fast survey, fewer vectors", standard: "Balanced coverage", deep: "Comprehensive, more vectors" };

function _renderDepthDropdown(prefix, current) {
  var label = _depthLabels[current] || "Standard";
  var html = '<div class="cm-depth-dd" id="' + prefix + '-depth-dd">';
  html += '<button class="cm-depth-trigger" onclick="toggleDepthMenu(\'' + prefix + '\')">';
  html += '<span>' + label + '</span>';
  html += '<svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 4l3 3 3-3" stroke="currentColor" stroke-width="1.5" fill="none"/></svg>';
  html += '</button>';
  html += '<div class="cm-depth-menu" id="' + prefix + '-depth-menu">';
  var keys = ["quick", "standard", "deep"];
  for (var i = 0; i < keys.length; i++) {
    var k = keys[i];
    var active = k === current ? " active" : "";
    html += '<button class="cm-depth-option' + active + '" onclick="selectDepth(\'' + prefix + '\',\'' + k + '\')">';
    html += '<span class="cm-depth-option-label">' + _depthLabels[k] + '</span>';
    html += '<span class="cm-depth-option-desc">' + _depthDescs[k] + '</span>';
    html += '</button>';
  }
  html += '</div></div>';
  return html;
}

function toggleDepthMenu(prefix) {
  var menu = document.getElementById(prefix + "-depth-menu");
  if (!menu) return;
  var isOpen = menu.classList.contains("open");
  // Close all depth menus first
  var all = document.querySelectorAll(".cm-depth-menu.open");
  for (var i = 0; i < all.length; i++) all[i].classList.remove("open");
  if (!isOpen) menu.classList.add("open");
}

function selectDepth(prefix, val) {
  if (prefix === "planner") _cm.plannerDepth = val;
  else if (prefix === "library") _cm.libraryDepth = val;
  var menu = document.getElementById(prefix + "-depth-menu");
  if (menu) menu.classList.remove("open");
  renderCampaignView();
}

// Close depth menus on outside click
document.addEventListener("click", function(e) {
  if (!e.target.closest(".cm-depth-dd")) {
    var all = document.querySelectorAll(".cm-depth-menu.open");
    for (var i = 0; i < all.length; i++) all[i].classList.remove("open");
  }
});

function setPlannerDepth(d) {
  _cm.plannerDepth = d;
  renderCampaignView();
}

function generatePlan() {
  var queryEl = document.getElementById("planner-query");
  var query = queryEl ? queryEl.value.trim() : "";
  if (!query) return;

  _cm.plannerLoading = true;
  _cm.plannerPlan = null;
  renderCampaignView();

  // Restore query text after re-render
  var queryEl2 = document.getElementById("planner-query");
  if (queryEl2) queryEl2.value = query;

  fetch("/api/campaigns/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: query, depth: _cm.plannerDepth }),
  })
    .then(function(r) {
      if (!r.ok) throw new Error("Plan generation failed: " + r.status);
      return r.json();
    })
    .then(function(plan) {
      _cm.plannerPlan = plan;
      _cm.plannerLoading = false;
      renderCampaignView();
      // Restore query
      var qe = document.getElementById("planner-query");
      if (qe) qe.value = query;
    })
    .catch(function(err) {
      _cm.plannerLoading = false;
      console.error("Plan generation error:", err);
      renderCampaignView();
      var qe = document.getElementById("planner-query");
      if (qe) qe.value = query;
      if (typeof showToast === "function") {
        showToast("Failed to generate plan: " + err.message, "error");
      }
    });
}

/* =====================================================================
   Vector Library View
   ===================================================================== */
function _renderLibraryView() {
  var html = '<div class="library-view">';
  var wc = _cm.libraryWorkingCopy;

  // --- 2A: Header Section ---
  html += '<div class="planner-section-title">C-POLAR Vector Library</div>';
  html += '<p style="color:var(--text-secondary);font-size:var(--text-xs);margin-bottom:16px">' +
    'Launch a full 175-vector research campaign for any application using the C-POLAR antimicrobial coating analysis framework.</p>';

  // Application name input
  html += '<div style="display:flex;align-items:flex-end;gap:12px;margin-bottom:8px">';
  html += '<div style="flex:1">';
  html += '<label style="font-size:var(--text-xs);color:var(--text-secondary);margin-bottom:4px;display:block">Application Name</label>';
  html += '<input type="text" class="library-app-input" id="library-app-input" ' +
    'placeholder="e.g. Household Water Filter, Hospital HVAC System" ' +
    'value="' + _escHtml(_cm.libraryApplication) + '" ' +
    'oninput="_cm.libraryApplication = this.value; _libraryPreviewRefresh()">';
  html += '</div>';
  if (wc) {
    html += '<button class="library-reset-btn" onclick="resetLibraryDefaults()" title="Reset to Defaults">Reset</button>';
  }
  html += '</div>';

  // Research Brief panel (collapsible)
  var briefVal = _cm.libraryResearchBrief || "";
  var briefBadge = briefVal.trim() ? '<span class="library-brief-badge">Set</span>' : '';
  var briefExpCls = _cm.libraryBriefExpanded ? "" : " collapsed";
  html += '<div class="library-brief-panel' + briefExpCls + '">';
  html += '<div class="library-brief-header" onclick="toggleResearchBrief()">';
  html += '<span class="planner-domain-chevron">&#9660;</span>';
  html += '<span class="library-brief-title">Research Brief / Domain Context</span>';
  html += briefBadge;
  html += '</div>';
  html += '<div class="library-brief-body">';
  html += '<div class="library-brief-hint">Provide context about your research domain. This text is injected into every vector\'s planning prompt so the pipeline understands what you\'re investigating.</div>';
  html += '<textarea class="library-brief-textarea" id="library-brief-input" ' +
    'maxlength="2000" oninput="updateResearchBrief(this.value)" ' +
    'placeholder="Describe your domain context...">' + _escHtml(briefVal) + '</textarea>';
  html += '<div class="library-brief-meta"><span id="library-brief-count">' +
    briefVal.length + '</span>/2000</div>';
  html += '</div></div>';

  // Depth dropdown
  html += '<div class="planner-depth-row" style="margin-top:12px">';
  html += _renderDepthDropdown("library", _cm.libraryDepth);
  html += '</div>';

  // Loading state
  if (_cm.libraryLoading) {
    html += '<div class="planner-loading">';
    html += '<div class="planner-spinner"></div>';
    html += '<div>Loading vector library...</div>';
    html += '</div>';
    html += '</div>';
    return html;
  }

  // --- 2B: Summary Bar (dynamic) ---
  if (wc && wc.length > 0) {
    var counts = _getEnabledVectorCount();
    var queryLabel = counts.vectors + ' of ' + counts.total + ' vectors (' + counts.queries + ' queries) across ' + counts.stages + ' of ' + wc.length + ' stages';
    html += '<div class="library-summary-bar">' + queryLabel + '</div>';

    // --- 2C: Stage Cards (enhanced) ---
    for (var s = 0; s < wc.length; s++) {
      var stage = wc[s];
      var key = "lib-" + s;
      var collapsed = _cm.collapsedGroups.has(key) ? " collapsed" : "";
      var disabledCls = !stage.enabled ? " library-stage-disabled" : "";
      var enabledVecCount = 0;
      for (var ec = 0; ec < stage.templates.length; ec++) {
        if (stage.templates[ec].enabled) enabledVecCount++;
      }

      html += '<div class="library-stage-card' + collapsed + disabledCls + '">';

      // Stage header row
      html += '<div class="library-stage-header">';
      html += '<input type="checkbox" class="library-stage-checkbox"' +
        (stage.enabled ? " checked" : "") +
        ' onchange="toggleStageEnabled(' + s + ')" onclick="event.stopPropagation()">';
      html += '<span class="planner-domain-chevron" onclick="toggleLibraryStageIdx(' + s + ')">&#9660;</span>';

      // Stage name: editable or display
      if (_cm._editingStage === s) {
        html += '<input type="text" class="library-inline-edit" id="lib-edit-stage-' + s + '" ' +
          'value="' + _escHtml(stage.name) + '" ' +
          'onblur="saveStageName(' + s + ')" ' +
          'onkeydown="if(event.key===\'Enter\'){saveStageName(' + s + ')}" ' +
          'onclick="event.stopPropagation()">';
      } else {
        html += '<span class="library-stage-name" onclick="event.stopPropagation(); editStageName(' + s + ')">' +
          'Stage ' + stage.stage + ': ' + _escHtml(stage.name) + '</span>';
      }

      html += '<span class="library-regional-tag ' + (stage.is_regional ? "regional" : "global") + '">' +
        (stage.is_regional ? "Regional" : "Global") + '</span>';
      html += '<span class="planner-domain-count">' + enabledVecCount + '/' + stage.templates.length + ' vectors</span>';

      // Move buttons
      html += '<button class="library-move-btn" onclick="event.stopPropagation(); moveStage(' + s + ',-1)"' +
        (s === 0 ? " disabled" : "") + ' title="Move up">&#9650;</button>';
      html += '<button class="library-move-btn" onclick="event.stopPropagation(); moveStage(' + s + ',1)"' +
        (s === wc.length - 1 ? " disabled" : "") + ' title="Move down">&#9660;</button>';
      html += '</div>';

      // Template list (collapsible)
      html += '<div class="library-template-list">';
      var templates = stage.templates || [];
      for (var t = 0; t < templates.length; t++) {
        var tmpl = templates[t];
        var vecDisabled = !tmpl.enabled ? " library-vector-disabled" : "";

        html += '<div class="library-template-item' + vecDisabled + '">';

        // Checkbox
        html += '<input type="checkbox" class="library-vector-checkbox"' +
          (tmpl.enabled ? " checked" : "") +
          ' onchange="toggleVectorEnabled(' + s + ',' + t + ')">';

        // Vector number
        html += '<span style="color:var(--text-tertiary);font-size:10px;min-width:24px">V' + tmpl.vector_number + '</span>';

        // Question text: editable or display with live preview
        if (_cm._editingVector && _cm._editingVector.s === s && _cm._editingVector.v === t) {
          html += '<textarea class="library-vector-edit" id="lib-edit-vec-' + s + '-' + t + '" ' +
            'onblur="saveVectorQuestion(' + s + ',' + t + ')" ' +
            'onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){event.preventDefault();saveVectorQuestion(' + s + ',' + t + ')}">' +
            _escHtml(tmpl.question_template) + '</textarea>';
        } else {
          // For preview, pick first checked region (prefer non-GLOBAL for regional display)
          var previewRegion = "GLOBAL";
          if (tmpl.regions_selected) {
            // First pass: try a non-GLOBAL checked region
            for (var prk in tmpl.regions_selected) {
              if (tmpl.regions_selected[prk] && prk !== "GLOBAL") { previewRegion = prk; break; }
            }
            // If only GLOBAL is checked, use that
            if (previewRegion === "GLOBAL" && tmpl.regions_selected["GLOBAL"]) {
              previewRegion = "GLOBAL";
            }
          }
          var display = _libraryPreviewTemplate(tmpl.question_template, previewRegion);
          html += '<span class="library-template-text" onclick="editVectorQuestion(' + s + ',' + t + ')">' +
            display + '<span class="library-edit-icon">&#9998;</span></span>';
        }

        // Actions: region + move + remove
        html += '<div class="library-vector-actions">';

        // Multi-region checkboxes (always show all 4 options)
        var regChecks = [
          {key: "GLOBAL", label: "GL"},
          {key: "NORTH_AMERICA", label: "NA"},
          {key: "EUROPE", label: "EU"},
          {key: "ASIA_PACIFIC", label: "AP"},
        ];
        var checkedCount = 0;
        for (var rk in tmpl.regions_selected) {
          if (tmpl.regions_selected[rk]) checkedCount++;
        }
        html += '<div class="library-region-matrix">';
        for (var r = 0; r < regChecks.length; r++) {
          var rc = regChecks[r];
          var checked = tmpl.regions_selected && tmpl.regions_selected[rc.key] ? " checked" : "";
          html += '<label class="library-region-check">' +
            '<input type="checkbox"' + checked +
            ' onchange="toggleVectorRegion(' + s + ',' + t + ',\'' + rc.key + '\')">' +
            rc.label + '</label>';
        }
        if (checkedCount > 1) {
          html += '<span class="library-region-count">' + checkedCount + ' queries</span>';
        }
        html += '</div>';

        // Move up/down
        html += '<button class="library-move-btn" onclick="moveVector(' + s + ',' + t + ',-1)"' +
          (t === 0 ? " disabled" : "") + ' title="Move up">&#9650;</button>';
        html += '<button class="library-move-btn" onclick="moveVector(' + s + ',' + t + ',1)"' +
          (t === templates.length - 1 ? " disabled" : "") + ' title="Move down">&#9660;</button>';

        // Remove
        html += '<button class="planner-vector-remove" onclick="removeVector(' + s + ',' + t + ')" title="Remove">&times;</button>';
        html += '</div>'; // vector-actions
        html += '</div>'; // template-item
      }

      // Add vector button
      html += '<button class="planner-add-vector-btn" onclick="addVector(' + s + ')">+ Add vector</button>';
      html += '</div>'; // template-list
      html += '</div>'; // stage-card
    }

    // --- 2E: Launch button (dynamic) ---
    html += '<div class="planner-actions" style="margin-top:16px">';
    var appVal = _cm.libraryApplication.trim();
    var queryCount = _getEnabledVectorCount().queries;
    var launchDisabled = (!appVal || queryCount === 0) ? " disabled" : "";
    html += '<button class="library-launch-btn"' + launchDisabled +
      ' onclick="launchLibraryCampaign()">Launch C-POLAR Campaign (' + queryCount + ' queries)</button>';
    html += '</div>';
  }

  html += '</div>';
  return html;
}

/* Format template text with live preview highlighting */
function _libraryPreviewTemplate(template, region) {
  var app = _cm.libraryApplication.trim();
  var regionMap = {
    "NORTH_AMERICA": "North America",
    "EUROPE": "Europe",
    "ASIA_PACIFIC": "Asia-Pacific",
    "GLOBAL": "Global",
  };
  var regionDisplay = regionMap[region] || region || "Global";
  var text = _escHtml(template);

  if (app) {
    var appDisplay = app.replace(/_/g, " ");
    text = text.replace(/\{application\}/g, '<span class="library-preview-filled">' + _escHtml(appDisplay) + '</span>');
  } else {
    text = text.replace(/\{application\}/g, '<span class="library-placeholder">&#91;application&#93;</span>');
  }
  text = text.replace(/\{region\}/g, '<span class="library-preview-region">' + _escHtml(regionDisplay) + '</span>');
  return text;
}

/* Lightweight DOM-only update of preview text (no full re-render) */
function _libraryPreviewRefresh() {
  if (_cm._previewTimer) clearTimeout(_cm._previewTimer);
  _cm._previewTimer = setTimeout(function() {
    var inp = document.getElementById("library-app-input");
    if (inp) _cm.libraryApplication = inp.value;
    // Update only the application spans inside existing vector text elements
    var texts = document.querySelectorAll(".library-template-text");
    var app = _cm.libraryApplication.trim();
    var appDisplay = app ? app.replace(/_/g, " ") : "";
    for (var i = 0; i < texts.length; i++) {
      var filled = texts[i].querySelectorAll(".library-preview-filled");
      var placeholders = texts[i].querySelectorAll(".library-placeholder");
      if (app) {
        // Update existing filled spans
        for (var f = 0; f < filled.length; f++) {
          filled[f].textContent = appDisplay;
        }
        // Convert placeholders to filled spans
        for (var p = 0; p < placeholders.length; p++) {
          placeholders[p].className = "library-preview-filled";
          placeholders[p].textContent = appDisplay;
        }
      } else {
        // Convert filled spans back to placeholders
        for (var f2 = 0; f2 < filled.length; f2++) {
          filled[f2].className = "library-placeholder";
          filled[f2].innerHTML = "&#91;application&#93;";
        }
      }
    }
  }, 80);
}

function setLibraryDepth(d) {
  _cm.libraryDepth = d;
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

/* Collapse/expand stage by index (used by chevron click) */
function toggleLibraryStageIdx(stageIdx) {
  var key = "lib-" + stageIdx;
  if (_cm.collapsedGroups.has(key)) {
    _cm.collapsedGroups.delete(key);
  } else {
    _cm.collapsedGroups.add(key);
  }
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

/* --- Preserve/Restore helpers --- */
function _preserveLibraryInputs() {
  var inp = document.getElementById("library-app-input");
  if (inp) _cm.libraryApplication = inp.value;
  var briefInp = document.getElementById("library-brief-input");
  if (briefInp) _cm.libraryResearchBrief = briefInp.value;
  // Save which input has focus and cursor position
  var active = document.activeElement;
  if (active && active.id) {
    _cm._focusedInputId = active.id;
    _cm._focusedCursorPos = (typeof active.selectionStart === "number") ? active.selectionStart : null;
  } else {
    _cm._focusedInputId = null;
    _cm._focusedCursorPos = null;
  }
}

function _restoreLibraryInputs() {
  var inp = document.getElementById("library-app-input");
  if (inp) {
    inp.value = _cm.libraryApplication;
    // Restore focus + cursor if this input was focused before re-render
    if (_cm._focusedInputId === "library-app-input") {
      inp.focus();
      if (typeof _cm._focusedCursorPos === "number") {
        inp.setSelectionRange(_cm._focusedCursorPos, _cm._focusedCursorPos);
      }
    }
  }
  var briefInp = document.getElementById("library-brief-input");
  if (briefInp) {
    briefInp.value = _cm.libraryResearchBrief || "";
    if (_cm._focusedInputId === "library-brief-input") {
      briefInp.focus();
      if (typeof _cm._focusedCursorPos === "number") {
        briefInp.setSelectionRange(_cm._focusedCursorPos, _cm._focusedCursorPos);
      }
    }
  }
  // Focus editing fields if active
  if (_cm._editingStage !== null) {
    var el = document.getElementById("lib-edit-stage-" + _cm._editingStage);
    if (el) el.focus();
  }
  if (_cm._editingVector) {
    var el2 = document.getElementById("lib-edit-vec-" + _cm._editingVector.s + "-" + _cm._editingVector.v);
    if (el2) el2.focus();
  }
  _cm._focusedInputId = null;
  _cm._focusedCursorPos = null;
}

/* --- Enabled count (queries = sum of checked regions per enabled vector) --- */
function _getEnabledVectorCount() {
  var wc = _cm.libraryWorkingCopy;
  if (!wc) return { vectors: 0, total: 0, stages: 0, queries: 0 };
  var vectors = 0;
  var total = 0;
  var stages = 0;
  var queries = 0;
  for (var s = 0; s < wc.length; s++) {
    var stg = wc[s];
    total += stg.templates.length;
    if (stg.enabled) {
      stages++;
      for (var t = 0; t < stg.templates.length; t++) {
        var tmpl = stg.templates[t];
        if (!tmpl.enabled) continue;
        vectors++;
        // Count checked regions (each checked region = 1 query)
        var regionCount = 0;
        for (var rk in tmpl.regions_selected) {
          if (tmpl.regions_selected[rk]) regionCount++;
        }
        queries += Math.max(regionCount, 1);
      }
    }
  }
  return { vectors: vectors, total: total, stages: stages, queries: queries };
}

/* --- Stage toggles and editing --- */
function toggleStageEnabled(stageIdx) {
  var wc = _cm.libraryWorkingCopy;
  if (!wc || !wc[stageIdx]) return;
  wc[stageIdx].enabled = !wc[stageIdx].enabled;
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function editStageName(stageIdx) {
  _cm._editingStage = stageIdx;
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function saveStageName(stageIdx) {
  var el = document.getElementById("lib-edit-stage-" + stageIdx);
  if (el && _cm.libraryWorkingCopy && _cm.libraryWorkingCopy[stageIdx]) {
    var val = el.value.trim();
    if (val) _cm.libraryWorkingCopy[stageIdx].name = val;
  }
  _cm._editingStage = null;
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function moveStage(stageIdx, dir) {
  var wc = _cm.libraryWorkingCopy;
  if (!wc) return;
  var target = stageIdx + dir;
  if (target < 0 || target >= wc.length) return;
  // Swap
  var tmp = wc[stageIdx];
  wc[stageIdx] = wc[target];
  wc[target] = tmp;
  // Update collapsed group keys
  var keyA = "lib-" + stageIdx;
  var keyB = "lib-" + target;
  var aCollapsed = _cm.collapsedGroups.has(keyA);
  var bCollapsed = _cm.collapsedGroups.has(keyB);
  if (aCollapsed) _cm.collapsedGroups.add(keyB); else _cm.collapsedGroups.delete(keyB);
  if (bCollapsed) _cm.collapsedGroups.add(keyA); else _cm.collapsedGroups.delete(keyA);
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

/* --- Vector toggles and editing --- */
function toggleVectorEnabled(sIdx, vIdx) {
  var wc = _cm.libraryWorkingCopy;
  if (!wc || !wc[sIdx] || !wc[sIdx].templates[vIdx]) return;
  wc[sIdx].templates[vIdx].enabled = !wc[sIdx].templates[vIdx].enabled;
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function editVectorQuestion(sIdx, vIdx) {
  _cm._editingVector = { s: sIdx, v: vIdx };
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function saveVectorQuestion(sIdx, vIdx) {
  var el = document.getElementById("lib-edit-vec-" + sIdx + "-" + vIdx);
  if (el && _cm.libraryWorkingCopy && _cm.libraryWorkingCopy[sIdx] &&
      _cm.libraryWorkingCopy[sIdx].templates[vIdx]) {
    var val = el.value.trim();
    if (val) _cm.libraryWorkingCopy[sIdx].templates[vIdx].question_template = val;
  }
  _cm._editingVector = null;
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function toggleVectorRegion(sIdx, vIdx, regionKey) {
  var wc = _cm.libraryWorkingCopy;
  if (!wc || !wc[sIdx] || !wc[sIdx].templates[vIdx]) return;
  var tmpl = wc[sIdx].templates[vIdx];
  if (!tmpl.regions_selected) return;
  var current = !!tmpl.regions_selected[regionKey];
  // Prevent unchecking the last region
  if (current) {
    var checkedCount = 0;
    for (var rk in tmpl.regions_selected) {
      if (tmpl.regions_selected[rk]) checkedCount++;
    }
    if (checkedCount <= 1) {
      if (typeof showToast === "function") {
        showToast("At least one region must be selected", "warning");
      }
      return;
    }
  }
  tmpl.regions_selected[regionKey] = !current;
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function moveVector(sIdx, vIdx, dir) {
  var wc = _cm.libraryWorkingCopy;
  if (!wc || !wc[sIdx]) return;
  var templates = wc[sIdx].templates;
  var target = vIdx + dir;
  if (target < 0 || target >= templates.length) return;
  var tmp = templates[vIdx];
  templates[vIdx] = templates[target];
  templates[target] = tmp;
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function removeVector(sIdx, vIdx) {
  var wc = _cm.libraryWorkingCopy;
  if (!wc || !wc[sIdx]) return;
  wc[sIdx].templates.splice(vIdx, 1);
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function addVector(sIdx) {
  var wc = _cm.libraryWorkingCopy;
  if (!wc || !wc[sIdx]) return;
  var question = prompt("Enter vector question template:");
  if (!question || !question.trim()) return;

  var stage = wc[sIdx];
  var maxVn = 0;
  for (var t = 0; t < stage.templates.length; t++) {
    if (stage.templates[t].vector_number > maxVn) maxVn = stage.templates[t].vector_number;
  }
  var regSel = {};
  if (stage.is_regional) {
    var defIdx = stage.templates.length % 3;
    regSel = { GLOBAL: false, NORTH_AMERICA: defIdx === 0, EUROPE: defIdx === 1, ASIA_PACIFIC: defIdx === 2 };
  } else {
    regSel = { GLOBAL: true, NORTH_AMERICA: false, EUROPE: false, ASIA_PACIFIC: false };
  }
  stage.templates.push({
    vector_number: maxVn + 1,
    question_template: question.trim(),
    enabled: true,
    regions_selected: regSel,
  });
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function resetLibraryDefaults() {
  _cm._editingStage = null;
  _cm._editingVector = null;
  _initLibraryWorkingCopy();
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function launchLibraryCampaign() {
  // Read current input value
  var inp = document.getElementById("library-app-input");
  if (inp) _cm.libraryApplication = inp.value;

  var application = _cm.libraryApplication.trim();
  if (!application) {
    if (typeof showToast === "function") {
      showToast("Please enter an application name", "error");
    }
    return;
  }

  // Normalize: spaces to underscores
  application = application.replace(/\s+/g, "_");
  var appDisplay = application.replace(/_/g, " ");

  // Build vectors array from working copy — expand per checked region
  var regionMap = {
    "GLOBAL": "Global",
    "NORTH_AMERICA": "North America",
    "EUROPE": "Europe",
    "ASIA_PACIFIC": "Asia-Pacific",
  };
  var vectors = [];
  var wc = _cm.libraryWorkingCopy;
  if (wc) {
    for (var s = 0; s < wc.length; s++) {
      var stage = wc[s];
      if (!stage.enabled) continue;
      for (var t = 0; t < stage.templates.length; t++) {
        var tmpl = stage.templates[t];
        if (!tmpl.enabled) continue;
        // One query per checked region
        for (var rk in tmpl.regions_selected) {
          if (!tmpl.regions_selected[rk]) continue;
          var query = tmpl.question_template
            .replace(/\{application\}/g, appDisplay)
            .replace(/\{region\}/g, regionMap[rk] || rk);
          vectors.push({ query: query, region: rk, stage: stage.stage });
        }
      }
    }
  }

  if (vectors.length === 0) {
    if (typeof showToast === "function") {
      showToast("No enabled vectors to launch", "error");
    }
    return;
  }

  _cm.libraryLoading = true;
  renderCampaignView();

  fetch("/api/campaigns/from-library", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      application: application,
      depth: _cm.libraryDepth,
      vectors: vectors,
      research_brief: (_cm.libraryResearchBrief || "").trim() || null,
    }),
  })
    .then(function(r) {
      if (!r.ok) return r.json().then(function(e) { throw new Error(e.detail || "Failed"); });
      return r.json();
    })
    .then(function(data) {
      var campaignId = data.campaign_id;
      _cm.libraryLoading = false;

      // Switch to map view and select the new campaign
      _cm.subView = "map";
      _cm.activeCampaignId = campaignId;

      loadCampaignList();
      fetchCampaignLive(campaignId);
      startCampaignPoll(campaignId);
      renderCampaignView();

      if (typeof showToast === "function") {
        showToast("C-POLAR campaign created: " + data.name + " (" + data.total_queries + " vectors)", "success");
      }
    })
    .catch(function(err) {
      _cm.libraryLoading = false;
      console.error("Library launch error:", err);
      renderCampaignView();
      if (typeof showToast === "function") {
        showToast("Failed to create campaign: " + err.message, "error");
      }
    });
}

/* =====================================================================
   Plan Card Renderer
   ===================================================================== */
function _renderPlanCard(plan) {
  var html = '<div class="planner-plan-card">';

  // Header
  html += '<div class="planner-plan-header">';
  html += '<div class="planner-plan-title">' + _escHtml(plan.title || "Research Plan") + '</div>';
  html += '<div class="planner-plan-meta">';

  var totalVectors = 0;
  var domains = plan.domains || [];
  for (var i = 0; i < domains.length; i++) {
    totalVectors += (domains[i].vectors || []).length;
  }

  html += '<span>' + totalVectors + ' vectors</span>';
  if (plan.estimated_minutes) {
    html += '<span>~' + plan.estimated_minutes + ' min</span>';
  }
  if (plan.estimated_cost_usd) {
    html += '<span>~$' + plan.estimated_cost_usd.toFixed(2) + '</span>';
  }
  html += '</div></div>';

  // Domain groups
  for (var d = 0; d < domains.length; d++) {
    var domain = domains[d];
    var collapsed = _cm.collapsedGroups.has("plan-" + d) ? " collapsed" : "";

    html += '<div class="planner-domain-group' + collapsed + '">';
    html += '<div class="planner-domain-header" onclick="togglePlanDomain(' + d + ')">';
    html += '<span class="planner-domain-chevron">&#9660;</span>';
    html += '<span class="planner-domain-name">' + _escHtml(domain.name || "Domain " + (d + 1)) + '</span>';
    html += '<span class="planner-domain-count">' + (domain.vectors || []).length + ' vectors</span>';
    html += '</div>';

    html += '<div class="planner-vector-list">';
    var vectors = domain.vectors || [];
    for (var v = 0; v < vectors.length; v++) {
      var vec = vectors[v];
      var badgeCls = (vec.type === "custom") ? "custom" : "standard";
      var editKey = "plan-" + d + "-" + v;
      var isEditing = _cm.plannerEditingVector === editKey;
      html += '<div class="planner-vector-item">';
      if (isEditing) {
        html += '<input class="planner-vector-edit-input" id="plan-edit-' + d + '-' + v + '" ' +
          'value="' + _escHtml(vec.query || "") + '" ' +
          'onblur="savePlanVectorEdit(' + d + ',' + v + ')" ' +
          'onkeydown="if(event.key===\'Enter\'){savePlanVectorEdit(' + d + ',' + v + ')}" ' +
          'onkeyup="if(event.key===\'Escape\'){cancelPlanVectorEdit()}" />';
      } else {
        html += '<span class="planner-vector-query planner-vector-editable" ' +
          'onclick="startPlanVectorEdit(' + d + ',' + v + ')" title="Click to edit">' +
          _escHtml(vec.query || "") + '</span>';
      }
      html += '<span class="planner-vector-badge ' + badgeCls + '">' + (vec.type || "standard") + '</span>';
      html += '<button class="planner-vector-remove" onclick="removePlanVector(' + d + ',' + v +
        ')" title="Remove">&times;</button>';
      html += '</div>';
    }

    html += '<button class="planner-add-vector-btn" onclick="addPlanVector(' + d +
      ')">+ Add vector</button>';
    html += '</div>';
    html += '</div>';
  }

  html += '</div>';

  // Actions
  html += '<div class="planner-actions">';
  html += '<button class="planner-cancel-btn" onclick="cancelPlan()">Cancel</button>';
  html += '<button class="planner-launch-btn" onclick="launchPlanAsCampaign()" ' +
    (totalVectors === 0 ? "disabled" : "") + '>Launch Research (' + totalVectors + ' queries)</button>';
  html += '</div>';

  return html;
}

function togglePlanDomain(domIdx) {
  var key = "plan-" + domIdx;
  if (_cm.collapsedGroups.has(key)) {
    _cm.collapsedGroups.delete(key);
  } else {
    _cm.collapsedGroups.add(key);
  }
  renderCampaignView();
}

function removePlanVector(domIdx, vecIdx) {
  if (!_cm.plannerPlan || !_cm.plannerPlan.domains) return;
  var domain = _cm.plannerPlan.domains[domIdx];
  if (!domain || !domain.vectors) return;
  domain.vectors.splice(vecIdx, 1);

  // Remove empty domains
  if (domain.vectors.length === 0) {
    _cm.plannerPlan.domains.splice(domIdx, 1);
  }

  renderCampaignView();
}

function addPlanVector(domIdx) {
  if (!_cm.plannerPlan || !_cm.plannerPlan.domains) return;
  var domain = _cm.plannerPlan.domains[domIdx];
  if (!domain) return;

  var query = prompt("Enter research query:");
  if (!query || !query.trim()) return;

  if (!domain.vectors) domain.vectors = [];
  domain.vectors.push({ query: query.trim(), type: "custom" });
  renderCampaignView();
}

function startPlanVectorEdit(domIdx, vecIdx) {
  _cm.plannerEditingVector = "plan-" + domIdx + "-" + vecIdx;
  renderCampaignView();
  var inp = document.getElementById("plan-edit-" + domIdx + "-" + vecIdx);
  if (inp) { inp.focus(); inp.select(); }
}

function savePlanVectorEdit(domIdx, vecIdx) {
  var inp = document.getElementById("plan-edit-" + domIdx + "-" + vecIdx);
  if (!inp) { _cm.plannerEditingVector = null; renderCampaignView(); return; }
  var val = inp.value.trim();
  if (!val) {
    // Empty = delete the vector
    removePlanVector(domIdx, vecIdx);
    _cm.plannerEditingVector = null;
    return;
  }
  if (_cm.plannerPlan && _cm.plannerPlan.domains && _cm.plannerPlan.domains[domIdx]) {
    var vec = _cm.plannerPlan.domains[domIdx].vectors[vecIdx];
    if (vec) vec.query = val;
  }
  _cm.plannerEditingVector = null;
  renderCampaignView();
}

function cancelPlanVectorEdit() {
  _cm.plannerEditingVector = null;
  renderCampaignView();
}

function cancelPlan() {
  _cm.plannerPlan = null;
  _cm.plannerLoading = false;
  renderCampaignView();
}

/* =====================================================================
   Launch Plan as Campaign
   ===================================================================== */
function launchPlanAsCampaign() {
  if (!_cm.plannerPlan || !_cm.plannerPlan.domains) return;

  // Collect all queries
  var queries = [];
  var domains = _cm.plannerPlan.domains;
  for (var d = 0; d < domains.length; d++) {
    var vectors = domains[d].vectors || [];
    for (var v = 0; v < vectors.length; v++) {
      if (vectors[v].query) {
        queries.push(vectors[v].query);
      }
    }
  }

  if (queries.length === 0) return;

  var name = _cm.plannerPlan.title || "Research Campaign";

  // Create campaign
  fetch("/api/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: name,
      description: "AI-generated research plan",
      queries: queries,
      depth: _cm.plannerDepth,
    }),
  })
    .then(function(r) {
      if (!r.ok) throw new Error("Failed to create campaign: " + r.status);
      return r.json();
    })
    .then(function(data) {
      var campaignId = data.campaign_id;

      // Start the campaign
      return fetch("/api/campaigns/" + encodeURIComponent(campaignId) + "/start", {
        method: "POST",
      }).then(function(r2) {
        if (!r2.ok) throw new Error("Failed to start campaign: " + r2.status);
        return r2.json();
      }).then(function() {
        // Switch to map view
        _cm.plannerPlan = null;
        _cm.plannerLoading = false;
        _cm.subView = "map";
        _cm.activeCampaignId = campaignId;

        // Reload campaign list and select
        loadCampaignList();
        fetchCampaignLive(campaignId);
        startCampaignPoll(campaignId);
        renderCampaignView();

        if (typeof showToast === "function") {
          showToast("Campaign launched with " + queries.length + " queries", "success");
        }
      });
    })
    .catch(function(err) {
      console.error("Launch error:", err);
      if (typeof showToast === "function") {
        showToast("Failed to launch: " + err.message, "error");
      }
    });
}

/* =====================================================================
   Badge
   ===================================================================== */
function _updateCampaignBadge() {
  var badge = document.getElementById("badge-campaigns");
  var running = 0;
  for (var i = 0; i < _cm.campaigns.length; i++) {
    if (_cm.campaigns[i].status === "running") running++;
  }
  if (badge) badge.textContent = running > 0 ? running : "";

  // Also update workspace sidebar badge
  _updateWorkspaceCampaignBadge();
}

/* =====================================================================
   Research Brief Helpers
   ===================================================================== */
function toggleResearchBrief() {
  _cm.libraryBriefExpanded = !_cm.libraryBriefExpanded;
  _preserveLibraryInputs();
  renderCampaignView();
  _restoreLibraryInputs();
}

function updateResearchBrief(val) {
  _cm.libraryResearchBrief = val;
  var counter = document.getElementById("library-brief-count");
  if (counter) counter.textContent = val.length;
}

/* =====================================================================
   Results View
   ===================================================================== */
function showResults() {
  _cm.subView = "results";
  renderCampaignView();
}

function _renderResultsView() {
  var html = '<div class="results-view">';
  var queries = (_cm.liveData && _cm.liveData.queries) ? _cm.liveData.queries : [];

  // Summary bar
  var completedCount = 0, failedCount = 0, totalEvidence = 0, totalWords = 0;
  var faithSum = 0, faithCount = 0;
  for (var i = 0; i < queries.length; i++) {
    var q = queries[i];
    if (q.status === "completed") {
      completedCount++;
      totalEvidence += q.evidence_count || 0;
      totalWords += q.word_count || 0;
      if (q.faithfulness != null && q.faithfulness > 0) {
        faithSum += q.faithfulness;
        faithCount++;
      }
    } else if (q.status === "failed") {
      failedCount++;
    }
  }
  var avgFaith = faithCount > 0 ? Math.round(faithSum / faithCount * 100) : 0;

  html += '<div class="results-summary-bar">';
  html += '<div class="results-summary-stat"><span class="results-stat-value">' +
    completedCount + '/' + queries.length + '</span><span class="results-stat-label">Completed</span></div>';
  html += '<div class="results-summary-stat"><span class="results-stat-value">' +
    avgFaith + '%</span><span class="results-stat-label">Avg Faith</span></div>';
  html += '<div class="results-summary-stat"><span class="results-stat-value">' +
    _formatNumber(totalEvidence) + '</span><span class="results-stat-label">Total Evidence</span></div>';
  html += '<div class="results-summary-stat"><span class="results-stat-value">' +
    _formatNumber(totalWords) + '</span><span class="results-stat-label">Total Words</span></div>';
  html += '<div class="results-summary-stat"><span class="results-stat-value" style="color:var(--error)">' +
    failedCount + '</span><span class="results-stat-label">Failed</span></div>';
  html += '</div>';

  // Filter + sort bar
  html += '<div class="results-filter-bar">';
  var filters = [{id:"all",label:"All"},{id:"completed",label:"Completed"},{id:"failed",label:"Failed"}];
  for (var fi = 0; fi < filters.length; fi++) {
    var f = filters[fi];
    var cls = f.id === _cm.resultsFilter ? " active" : "";
    html += '<button class="cm-filter-chip' + cls + '" onclick="setResultsFilter(\'' +
      f.id + '\')">' + f.label + '</button>';
  }
  html += '<select class="results-sort-select" onchange="setResultsSort(this.value)">';
  var sorts = [{val:"index",label:"Order"},{val:"faithfulness",label:"Faithfulness"},{val:"evidence",label:"Evidence"},{val:"words",label:"Words"}];
  for (var si = 0; si < sorts.length; si++) {
    var sel = sorts[si].val === _cm.resultsSortBy ? " selected" : "";
    html += '<option value="' + sorts[si].val + '"' + sel + '>' + sorts[si].label + '</option>';
  }
  html += '</select>';
  html += '</div>';

  // Filter and sort
  var filtered = [];
  for (var qi = 0; qi < queries.length; qi++) {
    var q = queries[qi];
    q._origIndex = qi;
    if (_cm.resultsFilter === "completed" && q.status !== "completed") continue;
    if (_cm.resultsFilter === "failed" && q.status !== "failed") continue;
    filtered.push(q);
  }
  if (_cm.resultsSortBy === "faithfulness") {
    filtered.sort(function(a,b) { return (b.faithfulness||0)-(a.faithfulness||0); });
  } else if (_cm.resultsSortBy === "evidence") {
    filtered.sort(function(a,b) { return (b.evidence_count||0)-(a.evidence_count||0); });
  } else if (_cm.resultsSortBy === "words") {
    filtered.sort(function(a,b) { return (b.word_count||0)-(a.word_count||0); });
  }

  if (filtered.length === 0) {
    html += '<div class="cm-empty-state" style="padding:48px">';
    html += '<div class="cm-empty-state-desc">No results yet. Select a campaign and run it to see results here.</div></div>';
  } else {
    // Results grid
    html += '<div class="results-grid">';
    for (var ri = 0; ri < filtered.length; ri++) {
      var q = filtered[ri];
      var statusCls = q.status === "completed" ? "results-card-completed" :
                      q.status === "failed" ? "results-card-failed" : "";
      var faithPct = q.faithfulness ? Math.round(q.faithfulness * 100) : 0;
      var faithCls = faithPct >= 80 ? "faith-high" : faithPct >= 60 ? "faith-mid" : "faith-low";
      var clickable = q.status === "completed" && q.vector_id ? ' onclick="openResultPanel(\'' + q.vector_id + '\')" style="cursor:pointer"' : '';

      html += '<div class="results-card ' + statusCls + '"' + clickable + '>';
      html += '<div class="results-card-header">';
      html += '<span class="results-card-vid">' + _escHtml(q.vector_id || 'V' + (q._origIndex+1)) + '</span>';
      html += '<span class="results-card-status ' + q.status + '">' + q.status + '</span>';
      html += '</div>';
      html += '<div class="results-card-query">' + _escHtml(_truncate(q.query || "", 80)) + '</div>';
      html += '<div class="results-card-metrics">';
      if (q.status === "completed") {
        html += '<span class="results-metric ' + faithCls + '">' + faithPct + '% faith</span>';
        html += '<span class="results-metric">' + (q.evidence_count||0) + ' ev</span>';
        html += '<span class="results-metric">' + _formatNumber(q.word_count||0) + 'w</span>';
        html += '<span class="results-metric">' + (q.source_count||0) + ' src</span>';
      }
      html += '</div>';
      html += '</div>';
    }
    html += '</div>';
  }

  html += '</div>';

  // Result viewer panel (slide-in)
  if (_cm.resultsPanelVector) {
    html += _renderResultPanel();
  }

  return html;
}

function setResultsFilter(f) {
  _cm.resultsFilter = f;
  renderCampaignView();
}

function setResultsSort(s) {
  _cm.resultsSortBy = s;
  renderCampaignView();
}

function _formatNumber(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

/* =====================================================================
   Result Viewer Panel
   ===================================================================== */
function openResultPanel(vectorId) {
  _cm.resultsPanelVector = vectorId;
  _cm.resultsPanelTab = "report";
  _cm.resultsPanelData = null;
  _cm.resultsPanelLoading = true;
  renderCampaignView();

  fetch("/api/research/result/" + encodeURIComponent(vectorId))
    .then(function(r) {
      if (!r.ok) throw new Error("Failed to load result: " + r.status);
      return r.json();
    })
    .then(function(data) {
      _cm.resultsPanelData = data;
      _cm.resultsPanelLoading = false;
      renderCampaignView();
    })
    .catch(function(err) {
      _cm.resultsPanelLoading = false;
      console.error("Result panel error:", err);
      renderCampaignView();
    });
}

function closeResultPanel() {
  _cm.resultsPanelVector = null;
  _cm.resultsPanelData = null;
  _cm.resultsPanelLoading = false;
  renderCampaignView();
}

function setResultPanelTab(tab) {
  _cm.resultsPanelTab = tab;
  renderCampaignView();
}

function exportResult(vectorId) {
  fetch("/api/research/export/" + encodeURIComponent(vectorId), { method: "POST" })
    .then(function(r) {
      if (!r.ok) throw new Error("Export failed");
      return r.blob();
    })
    .then(function(blob) {
      var url = window.URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = vectorId + "_report.html";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    })
    .catch(function(err) {
      if (typeof showToast === "function") showToast("Export failed: " + err.message, "error");
    });
}

function _renderResultPanel() {
  var vid = _cm.resultsPanelVector;
  var data = _cm.resultsPanelData;
  var tab = _cm.resultsPanelTab;

  var html = '<div class="results-panel-overlay" onclick="closeResultPanel()"></div>';
  html += '<div class="results-panel open">';

  // Header
  html += '<div class="results-panel-header">';
  html += '<span class="results-panel-vid">' + _escHtml(vid) + '</span>';
  html += '<button class="results-panel-export" onclick="exportResult(\'' + _escHtml(vid) + '\')">Export</button>';
  html += '<button class="results-panel-close" onclick="closeResultPanel()">&times;</button>';
  html += '</div>';

  if (_cm.resultsPanelLoading) {
    html += '<div class="results-panel-body" style="display:flex;align-items:center;justify-content:center">';
    html += '<div class="planner-spinner"></div>';
    html += '</div>';
    html += '</div>';
    return html;
  }

  if (!data) {
    html += '<div class="results-panel-body"><p style="color:var(--text-tertiary)">No data available.</p></div>';
    html += '</div>';
    return html;
  }

  // Query
  html += '<div class="results-panel-query">' + _escHtml(data.original_query || data.query || "") + '</div>';

  // Tabs
  var tabs = [{id:"report",label:"Report"},{id:"evidence",label:"Evidence"},{id:"citations",label:"Citations"},{id:"trace",label:"Trace"}];
  html += '<div class="results-panel-tabs">';
  for (var ti = 0; ti < tabs.length; ti++) {
    var tcls = tabs[ti].id === tab ? " active" : "";
    html += '<button class="results-panel-tab' + tcls + '" onclick="setResultPanelTab(\'' +
      tabs[ti].id + '\')">' + tabs[ti].label + '</button>';
  }
  html += '</div>';

  // Body
  html += '<div class="results-panel-body">';

  if (tab === "report") {
    // Quality metrics bar
    var qm = data.quality_metrics || {};
    html += '<div class="results-quality-bar">';
    html += '<span>' + (qm.total_evidence || 0) + ' evidence</span>';
    html += '<span>' + (data.iteration_count || 0) + ' iterations</span>';
    var faith = qm.faithfulness_score || data.faithfulness_score || 0;
    html += '<span>' + Math.round(faith * 100) + '% faithfulness</span>';
    html += '</div>';
    // Rendered report
    var report = data.final_report || "";
    html += '<div class="results-report-content">' + _simpleMarkdown(report) + '</div>';

  } else if (tab === "evidence") {
    var sections = data.sections || [];
    var evidence = data.evidence || [];
    html += '<p style="color:var(--text-secondary);font-size:var(--text-xs)">' +
      evidence.length + ' total evidence pieces</p>';
    if (sections.length > 0) {
      for (var ei = 0; ei < sections.length; ei++) {
        var sec = sections[ei];
        var secEvCount = (sec.evidence_ids || []).length;
        html += '<div style="padding:6px 0;border-bottom:1px solid var(--border)">';
        html += '<strong>' + _escHtml(sec.title || "Section " + (ei+1)) + '</strong>';
        html += '<span style="color:var(--text-tertiary);margin-left:8px">' + secEvCount + ' evidence</span>';
        html += '</div>';
      }
    } else {
      html += '<p style="color:var(--text-tertiary)">No section breakdown available.</p>';
    }

  } else if (tab === "citations") {
    var bib = data.bibliography || [];
    if (bib.length === 0) {
      html += '<p style="color:var(--text-tertiary)">No citations available.</p>';
    } else {
      html += '<div class="results-citations-list">';
      for (var ci = 0; ci < bib.length; ci++) {
        var entry = bib[ci];
        html += '<div class="results-citation-entry">';
        html += '<span class="results-citation-num">[' + (entry.citation_number || ci+1) + ']</span>';
        html += '<span class="results-citation-title">' + _escHtml(entry.formatted || "") + '</span>';
        if (entry.url) {
          html += '<a class="results-citation-url" href="' + _escHtml(entry.url) + '" target="_blank" rel="noopener">' +
            _truncate(entry.url, 60) + '</a>';
        }
        html += '</div>';
      }
      html += '</div>';
    }

  } else if (tab === "trace") {
    var ts = data.timestamps || {};
    var phases = ["planning","searching","analyzing","verifying","synthesizing","complete"];
    html += '<div class="results-trace-timeline">';
    for (var pi = 0; pi < phases.length; pi++) {
      var pname = phases[pi];
      var ptime = ts[pname] || ts[pname + "_start"] || "";
      var dotCls = ptime ? "active" : "";
      html += '<div class="results-trace-phase">';
      html += '<div class="results-trace-dot ' + dotCls + '"></div>';
      html += '<div><strong>' + pname.charAt(0).toUpperCase() + pname.slice(1) + '</strong>';
      if (ptime) html += '<br><span style="color:var(--text-tertiary);font-size:10px">' + ptime + '</span>';
      html += '</div></div>';
    }
    html += '</div>';
    var traceSummary = data.trace_summary || {};
    if (traceSummary.total_events) {
      html += '<p style="color:var(--text-secondary);font-size:var(--text-xs);margin-top:12px">' +
        traceSummary.total_events + ' trace events</p>';
    }
  }

  html += '</div>'; // panel-body
  html += '</div>'; // panel
  return html;
}

function _simpleMarkdown(text) {
  if (!text) return "";
  var s = _escHtml(text);
  // Headings
  s = s.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  s = s.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  s = s.replace(/^# (.+)$/gm, '<h2>$1</h2>');
  // Bold
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Citation superscripts [N]
  s = s.replace(/\[(\d+)\]/g, '<sup class="cite-num">[$1]</sup>');
  // Paragraphs
  s = s.replace(/\n\n+/g, '</p><p>');
  s = '<p>' + s + '</p>';
  return s;
}

// Escape key handler for result panel
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape" && _cm.resultsPanelVector) {
    closeResultPanel();
  }
});

/* =====================================================================
   Utilities
   ===================================================================== */
function _escHtml(s) {
  if (!s) return "";
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(s));
  return div.innerHTML;
}

function _truncate(s, maxLen) {
  if (!s) return "";
  if (s.length <= maxLen) return s;
  return s.substring(0, maxLen) + "...";
}

function _formatDuration(ms) {
  if (!ms || ms < 0) return "0s";
  var seconds = Math.floor(ms / 1000);
  if (seconds < 60) return seconds + "s";
  var minutes = Math.floor(seconds / 60);
  var secs = seconds % 60;
  if (minutes < 60) return minutes + "m " + secs + "s";
  var hours = Math.floor(minutes / 60);
  var mins = minutes % 60;
  return hours + "h " + mins + "m";
}

/* =====================================================================
   Campaign Overlay (Researcher mode workspace panel)
   ===================================================================== */
function openCampaignOverlay() {
  var overlay = document.getElementById("ws-campaign-overlay");
  if (!overlay) return;
  overlay.classList.add("open");

  // Render campaign view inside the overlay body
  var body = document.getElementById("ws-campaign-overlay-body");
  if (body) {
    _cm._overlayTarget = body;
    renderCampaignView(body);
  }
}

function closeCampaignOverlay() {
  var overlay = document.getElementById("ws-campaign-overlay");
  if (overlay) overlay.classList.remove("open");
  _cm._overlayTarget = null;
}

function _updateWorkspaceCampaignBadge() {
  var badge = document.getElementById("ws-campaigns-badge");
  if (!badge) return;
  var running = 0;
  _cm.campaigns.forEach(function(c) {
    if (c.status === "running") running++;
  });
  badge.textContent = running > 0 ? running : "";
}
