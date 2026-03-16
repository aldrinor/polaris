/* =====================================================================
   core.js — Constants, state, theme toggle, initialization, view switching,
   DOMContentLoaded setup, safe markdown renderer, timer functions,
   utility functions (setText, setBar, animateCounter, formatTime, debounce, etc.)
   ===================================================================== */

/* =====================================================================
   Constants
   ===================================================================== */
var NODE_ORDER = ["plan","search","storm_interviews","analyze","verify","evaluate","synthesize","search_gaps"];
var NODE_LABELS = {plan:"Plan",search:"Search",storm_interviews:"STORM",analyze:"Analyze",verify:"Verify",evaluate:"Evaluate",synthesize:"Synthesize",search_gaps:"Gap Search"};
var NODE_ICONS = {plan:"\u{1F4CB}",search:"\u{1F50D}",storm_interviews:"\u{1F4AC}",analyze:"\u{1F9EA}",verify:"\u2705",evaluate:"\u{1F4CA}",synthesize:"\u{1F4DD}",search_gaps:"\u{1F504}"};
var NODE_ICON_BG = {plan:"var(--info-dim)",search:"var(--success-dim)",storm_interviews:"rgba(167,139,250,0.15)",analyze:"var(--warning-dim)",verify:"rgba(244,114,182,0.15)",evaluate:"rgba(34,211,238,0.15)",synthesize:"var(--accent-dim)",search_gaps:"var(--warning-dim)"};
var EVENT_ICONS = {node_start:"\u25B6",node_end:"\u2714",llm_call:"\u2728",fetch:"\u{1F310}",evidence:"\u{1F4CE}",quality_gate:"\u{1F6A7}",reasoning_capture:"\u{1F9E0}",storm_transcript:"\u{1F4AC}",search_result:"\u{1F50D}",query:"\u2753",iteration_decision:"\u{1F504}"};
var NODE_DESCRIPTIONS = {plan:"Planning research queries...",search:"Searching web and academic databases...",storm_interviews:"Conducting STORM multi-perspective interviews...",analyze:"Fetching content and extracting evidence...",verify:"Verifying claims against sources...",evaluate:"Evaluating quality and identifying gaps...",synthesize:"Synthesizing research report...",search_gaps:"Searching for additional evidence..."};
var AUTO_TAB_MAP = {plan:"research",search:"research",storm_interviews:"advanced",analyze:"research",verify:"research",evaluate:"research",synthesize:"report",search_gaps:"research"};
var hasMarked = typeof marked !== "undefined";

/* =====================================================================
   State
   ===================================================================== */
/* Debug flag — set to true in browser console for verbose logging */
var _DEBUG = false;
function _log() { if (_DEBUG && console.log) console.log.apply(console, arguments); }

/* Configure marked for safe rendering */
if (typeof marked !== 'undefined') {
  marked.setOptions({
    breaks: false,
    gfm: true,
    headerIds: false,
    mangle: false
  });
}

/* Safe markdown rendering: parse then sanitize.
   Citations (onclick, data-cite) are injected AFTER this call,
   so we only need to preserve target="_blank" on links from marked. */
function safeMarkdown(md) {
  var html = typeof marked !== 'undefined' ? marked.parse(md) : md.replace(/\n/g, '<br>');
  if (typeof DOMPurify !== 'undefined') {
    return DOMPurify.sanitize(html, {
      ADD_ATTR: ['target'],
      ADD_DATA_URI_TAGS: ['img'],
      ADD_URI_SAFE_ATTR: ['src']
    });
  }
  return html;
}

var state = {
  vectorId: "--", connected: false, eventCount: 0, startTime: null, endTime: null, currentNode: "",
  evidence: 0, sources: new Set(), faithfulness: 0, verifiedEvidence: 0, words: 0, citations: 0, cost: 0, iteration: 0,
  phaseStatus: {},
  queries: [], fetches: [], stormPersonas: [], stormChats: [], evidenceEvents: [], evidenceDetails: [],
  sectionWrites: [], gateHistory: [], traceEvents: [], reasoningCaptures: [], reasoningLog: [],
  verificationVerdicts: [], clusterThemes: [], bibliography: [], citationMapping: [],
  researchQuery: "", application: "", region: "", maxIterations: 0, budgetUsd: 0,
  llmDetails: [], snapshotEventCount: 0,
  scoringDetail: [], scoringSortField: "composite", dedupDetail: null,
  verificationContext: [], citationMappingFull: null, expansionDetails: [],
  funnelScored: 0, funnelFiltered: 0, funnelExtracted: 0, funnelVerified: 0,
  tierCounts: { gold: 0, silver: 0, bronze: 0 },
  engineCounts: {}, totalResults: 0,
  fetchSuccess: 0, fetchSnippet: 0, fetchFailed: 0,
  autoScroll: true, soundEnabled: true, autoTab: true,
  activeView: "campaigns", dirtyViews: new Set(), renderedViews: new Set(),
  activeAdvTab: "queries",
  nodeTimings: {},
  graphNodes: [], graphEdges: [],
  gates: {},
  anomalies: [], lastAnomalyCount: 0,
  traceFilter: "all",
  planQueries: [], searchStrategy: "", keyConcepts: [], perspectiveDist: {}, missingPerspectives: [],
  signalStats: {}, dedupStats: null, fetchSummary: null,
  nliSummary: null, nliClaimsDetail: [], crossRefGroups: [],
  reportOutline: null, sectionEvidenceMap: [], hallucinationAudit: [], evidenceConflicts: [],
  expansionPasses: [], gapAnalysis: null, fullReport: "",
  agenticRounds: [],
  llmCallCount: 0, llmInputTokens: 0, llmOutputTokens: 0, modelCounts: {},
  // NEW: Reasoning by phase
  reasoningByPhase: {},
  activeReasoningPhase: null,
  pipelineComplete: false,
  pipelineActive: false,
  selectedEvidenceIdx: -1,
  graphMode: "crossref",
  authenticated: false,
  user: null,
  smartArtDiagrams: {},
  // Master-detail phase selection
  selectedPhase: null,
  userPinnedPhase: false,
  // Workspace state
  workspacePhase: "idle",
  sessionThread: [],
  activeCampaignId: null,
  campaignMapActive: false
};
NODE_ORDER.forEach(function(n) { state.phaseStatus[n] = "pending"; });

/* =====================================================================
   Initialization — theme first, then DOM
   ===================================================================== */
initTheme();
renderPhaseStepper();

/* =====================================================================
   Theme Toggle (Light/Dark)
   ===================================================================== */
function _getEffectiveTheme() {
  var saved = localStorage.getItem("polaris-theme");
  if (saved === "light" || saved === "dark") return saved;
  // No saved preference — detect system preference
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) return "light";
  return "dark";
}
function initTheme() {
  var theme = _getEffectiveTheme();
  document.documentElement.setAttribute("data-theme", theme);
  updateThemeIcon();
}
function toggleTheme() {
  var current = document.documentElement.getAttribute("data-theme") || "dark";
  var next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("polaris-theme", next);
  updateThemeIcon();
  // QW-4: Update D3/SVG graph colors on theme toggle
  if (typeof window.refreshGraphColors === 'function') window.refreshGraphColors();
  // A5: Re-render Mermaid diagrams with updated theme
  if (typeof mermaid !== "undefined") {
    try {
      mermaid.initialize({ startOnLoad: false, theme: next === "dark" ? "dark" : "default", securityLevel: "strict" });
      var mermaidDivs = document.querySelectorAll(".mermaid[data-processed]");
      mermaidDivs.forEach(function(d) { d.removeAttribute("data-processed"); d.innerHTML = d.getAttribute("data-original") || d.textContent; });
      if (mermaidDivs.length) mermaid.run({ nodes: mermaidDivs });
    } catch(e) { /* non-blocking */ }
  }
}
function updateThemeIcon() {
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  var theme = document.documentElement.getAttribute("data-theme") || "dark";
  btn.innerHTML = theme === "dark" ? "&#9788;" : "&#9789;";
  btn.title = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
}

/* =====================================================================
   View Switching
   ===================================================================== */
document.querySelectorAll(".nav-btn").forEach(function(btn) {
  btn.addEventListener("click", function() { switchView(this.dataset.view); });
});

function switchView(viewId) {
  state.activeView = viewId;
  document.querySelectorAll(".nav-btn").forEach(function(b) {
    var isActive = b.dataset.view === viewId;
    b.classList.toggle("active", isActive);
    b.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  document.querySelectorAll(".view-pane").forEach(function(p) { p.classList.toggle("active", p.id === "view-" + viewId); });
  if (state.dirtyViews.has(viewId)) {
    state.dirtyViews.delete(viewId);
    renderView(viewId);
    state.renderedViews.add(viewId);
  } else if (!state.renderedViews.has(viewId)) {
    renderView(viewId);
    state.renderedViews.add(viewId);
  }
}

function markDirty(viewId) {
  if (state.activeView === viewId) {
    renderView(viewId);
  } else {
    state.dirtyViews.add(viewId);
  }
}

/* Advanced sub-tabs (with ARIA state sync) */
document.querySelectorAll(".adv-tab-btn").forEach(function(btn) {
  btn.addEventListener("click", function() {
    var tab = this.dataset.adv;
    state.activeAdvTab = tab;
    document.querySelectorAll(".adv-tab-btn").forEach(function(b) {
      var isActive = b.dataset.adv === tab;
      b.classList.toggle("active", isActive);
      b.setAttribute("aria-selected", isActive ? "true" : "false");
      b.setAttribute("tabindex", isActive ? "0" : "-1");
    });
    document.querySelectorAll(".adv-pane").forEach(function(p) { p.classList.toggle("active", p.id === "adv-" + tab); });
    renderAdvancedTab(tab);
  });
});

/* =====================================================================
   Timer
   ===================================================================== */
setInterval(function() {
  if (!state.startTime) return;
  // Stop ticking when pipeline is complete — show frozen final time
  if (state.pipelineComplete && state.endTime) {
    var elapsed = Math.floor((state.endTime - state.startTime) / 1000);
  } else if (state.pipelineComplete) {
    return; // Complete but no endTime — keep last displayed value
  } else {
    var elapsed = Math.floor((Date.now() - state.startTime) / 1000);
  }
  var hh = String(Math.floor(elapsed / 3600)).padStart(2, "0");
  var mm = String(Math.floor((elapsed % 3600) / 60)).padStart(2, "0");
  var ss = String(elapsed % 60).padStart(2, "0");
  setText("elapsed-time", hh + ":" + mm + ":" + ss);
}, 1000);

/* =====================================================================
   Phase Stepper
   ===================================================================== */
function renderPhaseStepper() {
  var el = document.getElementById("phase-stepper");
  el.innerHTML = NODE_ORDER.map(function(n) {
    var cls = state.phaseStatus[n] || "pending";
    return '<div class="step-item ' + cls + '" id="step-' + n + '">' +
      '<span class="step-dot"></span><span>' + esc(NODE_LABELS[n]) + '</span></div>';
  }).join("");
}

function updateStepper() {
  NODE_ORDER.forEach(function(n) {
    var el = document.getElementById("step-" + n);
    if (el) el.className = "step-item " + (state.phaseStatus[n] || "pending");
  });
}

/* =====================================================================
   Toast system
   ===================================================================== */
function showToast(msg, type) {
  type = type || "info";
  var container = document.getElementById("toast-container");
  var toast = document.createElement("div");
  toast.className = "toast toast-" + type;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(function() { toast.classList.add("show"); }, 10);
  setTimeout(function() {
    toast.classList.remove("show");
    setTimeout(function() { toast.remove(); }, 300);
  }, 4000);
}

/* =====================================================================
   Helpers
   ===================================================================== */
function esc(s) { if (!s) return ""; var d = document.createElement("div"); d.textContent = String(s); return d.innerHTML; }
function setText(id, txt) { var el = document.getElementById(id); if (el) el.textContent = txt; }
function truncStr(s, max) { if (!s) return ""; s = String(s); return s.length > max ? s.substring(0, max) + "..." : s; }
function fmtDuration(ms) {
  if (ms < 1000) return ms + "ms";
  var s = ms / 1000;
  if (s < 60) return s.toFixed(1) + "s";
  var m = Math.floor(s / 60);
  return m + "m " + Math.round(s % 60) + "s";
}
function extractDomain(url) {
  if (!url) return "";
  try { return new URL(url).hostname.replace("www.", ""); } catch(e) { return url.substring(0, 40); }
}

/* =====================================================================
   Audio beep (short)
   ===================================================================== */
var _audioCtx = null;
function beep() {
  if (!state.soundEnabled) return;
  try {
    if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    var osc = _audioCtx.createOscillator();
    var gain = _audioCtx.createGain();
    osc.connect(gain);
    gain.connect(_audioCtx.destination);
    osc.frequency.value = 660;
    gain.gain.value = 0.08;
    osc.start();
    osc.stop(_audioCtx.currentTime + 0.08);
  } catch(e) {}
}

/* =====================================================================
   formatTokens — Token count formatter
   ===================================================================== */
function formatTokens(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

/* =====================================================================
   Debug & exports
   ===================================================================== */

/* =====================================================================
   sortEvidence() — Sort evidence cards by selected dimension
   ===================================================================== */
function sortEvidence(field) {
  state.scoringSortField = field || "composite";
  renderEvidenceCards();
}

/* =====================================================================
   toggleStormSidebar() — Collapse/expand STORM sidebar
   ===================================================================== */
function toggleStormSidebar() {
  var sidebar = document.getElementById("storm-sidebar");
  if (sidebar) sidebar.classList.toggle("collapsed");
}

/* =====================================================================
   renderStormPerspectives() — Build STORM perspective cards
   ===================================================================== */
function renderStormPerspectives(personas) {
  var list = document.getElementById("storm-perspectives-list");
  if (!list || !personas || !personas.length) return;
  var html = "";
  personas.forEach(function(p) {
    var name = p.name || p.persona || "Expert";
    var expertise = p.expertise || p.field || "";
    var focus = p.focus || p.perspective || "";
    // Find a key finding from storm chats for this persona
    var finding = "";
    var chats = state.stormChats.filter(function(c) { return c.persona === name; });
    if (chats.length && chats[0].findings && chats[0].findings.length) {
      var f = chats[0].findings[0];
      finding = typeof f === "string" ? f : (f.finding || "");
    }
    html += '<div class="storm-persp-item">';
    html += '<div class="storm-persp-item-name">' + esc(name) + '</div>';
    if (expertise) html += '<div style="font-size:11px;color:var(--accent);margin-top:1px">' + esc(expertise) + '</div>';
    if (focus) html += '<div style="font-size:10px;color:var(--text-tertiary);margin-top:1px">' + esc(focus) + '</div>';
    if (finding) html += '<div class="storm-persp-item-finding">' + esc(truncStr(finding, 200)) + '</div>';
    html += '</div>';
  });
  list.innerHTML = html;
}

/* =====================================================================
   getPhaseLabel() — Human-language progress labels with counts
   ===================================================================== */
function getPhaseLabel(phase, stats, isDone) {
  var srcCount = stats.source_count || state.sources.size || "";
  var perspCount = stats.perspective_count || state.stormPersonas.length || "";
  var claimCount = stats.claim_count || state.evidence || "";
  var evCount = stats.evidence_count || state.evidence || "";
  var label;
  switch (phase) {
    case "plan": label = isDone ? "Planned research strategy" : "Planning research strategy..."; break;
    case "search": label = isDone ? "Searched" + (srcCount ? " " + srcCount + " sources" : " sources") : "Searching" + (srcCount ? " " + srcCount + " sources" : " sources..."); break;
    case "storm_interviews": label = isDone ? "Interviewed" + (perspCount ? " " + perspCount + " expert perspectives" : " experts") : "Interviewing " + (perspCount || "expert") + " expert perspectives"; break;
    case "analyze": label = isDone ? "Analyzed evidence" : "Analyzing and extracting evidence..."; break;
    case "verify": label = isDone ? "Verified" + (claimCount ? " " + claimCount + " claims" : " claims") : "Verifying " + (claimCount || "") + " claims against source text"; break;
    case "evaluate": label = isDone ? "Evaluated evidence quality" : "Evaluating evidence quality..."; break;
    case "synthesize": label = isDone ? "Synthesized report" : "Synthesizing " + (evCount || "") + " evidence pieces into report"; break;
    case "search_gaps": label = isDone ? "Searched for gaps" : "Searching for additional evidence..."; break;
    default: label = phase.replace(/_/g, " "); break;
  }
  return label;
}

/* =====================================================================
   estimateTimeRemaining() — Show estimated time
   ===================================================================== */
function estimateTimeRemaining(currentPhase) {
  if (!state.startTime) return "";
  var elapsed = (Date.now() - state.startTime) / 1000 / 60; // minutes
  var phaseProgress = {plan: 0.05, search: 0.25, storm_interviews: 0.40, analyze: 0.55, verify: 0.75, evaluate: 0.85, synthesize: 0.95, search_gaps: 0.50};
  var progress = phaseProgress[currentPhase] || 0.5;
  if (progress <= 0.01) return "";
  var remaining = Math.max(0, (elapsed / progress) - elapsed);
  if (remaining < 1) return "Less than a minute remaining";
  return "~" + Math.ceil(remaining) + " min remaining";
}

/* =====================================================================
   animateCounter() — Animated evidence count ticker
   ===================================================================== */
function animateCounter(elementId, targetValue) {
  var el = document.getElementById(elementId);
  if (!el) return;
  var current = parseInt(el.textContent) || 0;
  if (current === targetValue) return;
  var step = Math.max(1, Math.floor(Math.abs(targetValue - current) / 20));
  var val = current;
  var direction = targetValue > current ? 1 : -1;
  el.classList.add("counter-pulse");
  var interval = setInterval(function() {
    val += step * direction;
    if ((direction > 0 && val >= targetValue) || (direction < 0 && val <= targetValue)) {
      val = targetValue;
      clearInterval(interval);
      setTimeout(function() { el.classList.remove("counter-pulse"); }, 300);
    }
    el.textContent = val;
  }, 30);
}

/* =====================================================================
   safeRender() — Error boundary for rendering functions
   ===================================================================== */
function safeRender(fn, fallbackMessage) {
  try {
    fn();
  } catch(e) {
    console.error("Render error:", e);
    var container = document.querySelector(".views-container");
    if (container) {
      var errDiv = document.createElement("div");
      errDiv.className = "render-error";
      errDiv.innerHTML = '<strong>Display Error</strong><p>' + esc(fallbackMessage || "Failed to render this section. Check console for details.") + '</p>';
      container.appendChild(errDiv);
    }
  }
}

/* =====================================================================
   G1: Sovereign Mode Badge — fetch /api/system/info and show badge
   ===================================================================== */
function initSovereignBadge() {
  fetch("/api/system/info").then(function(r) { return r.json(); }).then(function(info) {
    var header = document.querySelector(".header-left, .app-header, header");
    if (header) {
      var badge = document.createElement("span");
      badge.id = "sovereign-badge";
      badge.className = "sovereign-badge" + (info.sovereign_mode ? " sovereign-active" : "");
      badge.textContent = info.sovereign_mode ? "Sovereign" : "Cloud";
      badge.title = info.sovereign_mode
        ? "Sovereign mode ON — all processing is local. Click to view details."
        : "Cloud mode — using external APIs. Click to view details.";
      badge.style.cursor = "pointer";
      badge.setAttribute("data-sovereign", info.sovereign_mode ? "1" : "0");
      badge.setAttribute("data-provider", info.provider || "openrouter");
      badge.addEventListener("click", function() {
        _toggleSovereignDetail(badge, info);
      });
      header.appendChild(badge);
    }
    // Store for downstream use
    state._systemInfo = info;
  }).catch(function() { /* non-blocking */ });
}

function _toggleSovereignDetail(badge, info) {
  var existing = document.getElementById("sovereign-detail-popup");
  if (existing) {
    existing.remove();
    return;
  }
  var popup = document.createElement("div");
  popup.id = "sovereign-detail-popup";
  popup.className = "sovereign-detail-popup";
  var mode = info.sovereign_mode ? "Sovereign (Air-Gapped)" : "Cloud (External APIs)";
  var provider = info.provider || "N/A";
  var rbac = info.rbac_enabled ? "Enabled" : "Disabled";
  popup.innerHTML =
    '<div class="sovereign-detail-header">Deployment Info</div>' +
    '<div class="sovereign-detail-row"><span>Mode:</span><strong>' + mode + '</strong></div>' +
    '<div class="sovereign-detail-row"><span>Provider:</span><strong>' + provider + '</strong></div>' +
    '<div class="sovereign-detail-row"><span>RBAC:</span><strong>' + rbac + '</strong></div>' +
    '<div class="sovereign-detail-row"><span>Version:</span><strong>' + (info.version || "1.0") + '</strong></div>';
  badge.parentElement.style.position = "relative";
  badge.parentElement.appendChild(popup);
  document.addEventListener("click", function dismissPopup(e) {
    if (!popup.contains(e.target) && e.target !== badge) {
      popup.remove();
      document.removeEventListener("click", dismissPopup);
    }
  });
}

/* =====================================================================
   G2: RBAC — fetch /api/auth/me and hide unauthorized UI elements
   ===================================================================== */
function initRBAC() {
  fetch("/api/auth/me").then(function(r) {
    if (!r.ok) return null;
    return r.json();
  }).then(function(user) {
    if (!user) return;
    state.authenticated = true;
    state.user = user;
    state.currentUserRole = user.role || (user.auth_enabled === false ? "admin" : "researcher");
    _applyRoleVisibility(state.currentUserRole);
  }).catch(function() { /* auth not available, skip */ });
}

function _applyRoleVisibility(role) {
  /* Comprehensive role-based feature hiding.
     | Role       | Pipeline Edit | Delete | Operator View | Export |
     |------------|--------------|--------|---------------|--------|
     | researcher | Hidden       | Hidden | Hidden        | Visible|
     | manager    | Visible      | Hidden | Visible       | Visible|
     | admin      | Visible      | Visible| Visible       | Visible|
     | auditor    | Hidden       | Hidden | Visible (RO)  | Visible| */
  /* Remove any previous rbac-hidden/rbac-readonly to support role switching */
  document.querySelectorAll(".rbac-hidden").forEach(function(el) {
    el.classList.remove("rbac-hidden");
  });
  document.querySelectorAll(".rbac-readonly").forEach(function(el) {
    el.classList.remove("rbac-readonly");
    el.removeAttribute("disabled");
  });

  if (role === "admin") return;

  var roleCfg = {
    researcher: {
      hidden: [
        "#pipe-btn-save", "#pipe-btn-delete", ".ckpt-rewind-btn",
        "#pipe-btn-run", "#pipe-btn-validate",
        ".operator-only", "#operator-view-toggle",
        "#pipelines-config-panel"
      ]
    },
    manager: {
      hidden: [
        "#pipe-btn-delete", ".ckpt-rewind-btn"
      ]
    },
    auditor: {
      hidden: [
        "#pipe-btn-save", "#pipe-btn-delete", ".ckpt-rewind-btn",
        "#pipe-btn-run"
      ]
    }
  };

  var cfg = roleCfg[role];
  if (!cfg) return;

  cfg.hidden.forEach(function(sel) {
    var els = document.querySelectorAll(sel);
    els.forEach(function(el) { el.classList.add("rbac-hidden"); });
  });

  /* Auditor: mark operator view as read-only */
  if (role === "auditor") {
    document.querySelectorAll(".operator-only input, .operator-only button").forEach(function(el) {
      el.setAttribute("disabled", "true");
      el.classList.add("rbac-readonly");
    });
  }
}

/* =====================================================================
   Toolbar roving tabindex (WAI-APG Toolbar pattern) — Phase 0E
   ===================================================================== */
function initToolbarKeyboard(toolbar) {
  var items = toolbar.querySelectorAll('button, [role="switch"]');
  if (!items.length) return;
  items.forEach(function(el, i) { el.setAttribute('tabindex', i === 0 ? '0' : '-1'); });
  toolbar.addEventListener('keydown', function(e) {
    var current = Array.from(items).indexOf(document.activeElement);
    if (current < 0) return;
    var next = -1;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (current + 1) % items.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (current - 1 + items.length) % items.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = items.length - 1;
    if (next >= 0) {
      e.preventDefault();
      items[current].setAttribute('tabindex', '-1');
      items[next].setAttribute('tabindex', '0');
      items[next].focus();
    }
  });
}

/* =====================================================================
   Tablist keyboard (WAI-APG Tabs pattern) — Phase 0E-b
   Reusable for main nav and Advanced sub-tabs.
   ===================================================================== */
function initTablistKeyboard(tablist) {
  var tabs = tablist.querySelectorAll('[role="tab"]');
  tabs.forEach(function(tab) {
    tab.setAttribute('tabindex', tab.getAttribute('aria-selected') === 'true' ? '0' : '-1');
  });
  tablist.addEventListener('keydown', function(e) {
    var tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
    var idx = tabs.indexOf(document.activeElement);
    if (idx < 0) return;
    var next = -1;
    if (e.key === 'ArrowRight') next = (idx + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') next = (idx - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = tabs.length - 1;
    if (next >= 0) {
      e.preventDefault();
      tabs[idx].setAttribute('tabindex', '-1');
      tabs[next].setAttribute('tabindex', '0');
      tabs[next].focus();
      tabs[next].click(); // automatic activation
    }
  });
}

/* =====================================================================
   updatePolarisStatus() — Advisory live region for screen readers
   ===================================================================== */
function updatePolarisStatus(msg) {
  var el = document.getElementById('polaris-status');
  if (el) el.textContent = msg;
}
function updatePolarisAlert(msg) {
  var el = document.getElementById('polaris-alert');
  if (el) el.textContent = msg;
}

/* =====================================================================
   initShellControls() — Density toggle, Auto-nav switch, toolbar keyboard
   ===================================================================== */
function initShellControls() {
  // --- Density toggle ---
  document.querySelectorAll('.density-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.density-btn').forEach(function(b) { b.classList.remove('active'); });
      this.classList.add('active');
      document.body.classList.toggle('operator-dense', this.dataset.density === 'dense');
      localStorage.setItem('polaris_density', this.dataset.density);
    });
  });
  var savedDensity = localStorage.getItem('polaris_density');
  if (savedDensity === 'dense') {
    document.body.classList.add('operator-dense');
    var b = document.querySelector('.density-btn[data-density="dense"]');
    if (b) {
      document.querySelectorAll('.density-btn').forEach(function(x) { x.classList.remove('active'); });
      b.classList.add('active');
    }
  }

  // --- Auto-nav switch (WAI-APG switch pattern) ---
  var autoNavBtn = document.getElementById('chk-autotab');
  if (autoNavBtn) {
    autoNavBtn.addEventListener('click', function() {
      var checked = this.getAttribute('aria-checked') === 'true';
      this.setAttribute('aria-checked', String(!checked));
      state.autoTab = !checked;
      // When Auto-nav re-enabled, reset phase pinning
      if (!checked && typeof resetPhasePinning === 'function') {
        resetPhasePinning();
      }
    });
  }

  // --- Toolbar roving tabindex (run-context-bar or legacy operator-toolbar) ---
  var toolbar = document.querySelector('.run-context-bar') || document.querySelector('.operator-toolbar[role="toolbar"]');
  if (toolbar) initToolbarKeyboard(toolbar);

  // --- Tab keyboard for main nav ---
  var mainTablist = document.querySelector('[role="tablist"].nav-tabs');
  if (mainTablist) initTablistKeyboard(mainTablist);

  // --- Tab keyboard for Advanced sub-tabs (if already rendered) ---
  var advTablist = document.querySelector('.adv-tab-bar[role="tablist"]');
  if (advTablist) initTablistKeyboard(advTablist);
}

/* =====================================================================
   Compose Bar / Drawer / FAB — First-class research creation surface
   ===================================================================== */
var _selectedDepth = "standard";
var _composeTriggerEl = null;
var _modalStack = [];

function initCompose() {
  var trigger = document.getElementById("compose-trigger");
  var cancelBtn = document.getElementById("compose-cancel");
  var submitBtn = document.getElementById("compose-submit");
  var fab = document.getElementById("compose-fab");
  var textarea = document.getElementById("compose-query");

  if (trigger) trigger.addEventListener("click", function() { openCompose(trigger); });
  if (cancelBtn) cancelBtn.addEventListener("click", closeCompose);
  if (submitBtn) submitBtn.addEventListener("click", function() {
    submitResearchFromPayload({
      query: document.getElementById("compose-query").value,
      depth: _selectedDepth,
      documentIds: [],
      campaignId: null
    });
  });
  if (fab) fab.addEventListener("click", function() { openCompose(fab); });

  // Depth chips inside compose drawer
  var depthContainer = document.getElementById("compose-depth");
  if (depthContainer) {
    depthContainer.addEventListener("click", function(e) {
      var chip = e.target.closest(".depth-chip");
      if (!chip || !chip.dataset.depth) return;
      _selectedDepth = chip.dataset.depth;
      depthContainer.querySelectorAll(".depth-chip").forEach(function(c) { c.classList.remove("active"); });
      chip.classList.add("active");
    });
  }

  // Ctrl+K / Cmd+K global shortcut
  document.addEventListener("keydown", function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "k") {
      e.preventDefault();
      var drawer = document.getElementById("compose-drawer");
      if (drawer && drawer.classList.contains("visible")) {
        closeCompose();
      } else {
        openCompose(document.getElementById("compose-trigger") || document.getElementById("compose-fab"));
      }
    }
  });

  // Textarea keyboard shortcuts
  if (textarea) {
    textarea.addEventListener("keydown", function(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        submitBtn && submitBtn.click();
      }
      if (e.key === "Escape") {
        e.preventDefault();
        closeCompose();
      }
    });
    // Clear error on input
    textarea.addEventListener("input", function() {
      textarea.classList.remove("error");
      var errMsg = document.getElementById("compose-error-msg");
      if (errMsg) errMsg.classList.remove("visible");
    });
  }
}

function openCompose(triggerEl) {
  var drawer = document.getElementById("compose-drawer");
  var fab = document.getElementById("compose-fab");
  var trigger = document.getElementById("compose-trigger");
  if (!drawer) return;

  _composeTriggerEl = triggerEl || trigger;
  drawer.classList.add("visible");
  if (trigger) trigger.setAttribute("aria-expanded", "true");
  if (fab) fab.classList.add("hidden");

  // Focus textarea
  var textarea = document.getElementById("compose-query");
  if (textarea) {
    setTimeout(function() { textarea.focus(); }, 50);
  }

  // Announce to screen reader
  _announce("Compose drawer opened");
}

function closeCompose() {
  var drawer = document.getElementById("compose-drawer");
  var fab = document.getElementById("compose-fab");
  var trigger = document.getElementById("compose-trigger");
  if (!drawer) return;

  drawer.classList.remove("visible");
  if (trigger) trigger.setAttribute("aria-expanded", "false");
  if (fab) fab.classList.remove("hidden");

  // Clear error state
  var textarea = document.getElementById("compose-query");
  if (textarea) textarea.classList.remove("error");
  var errMsg = document.getElementById("compose-error-msg");
  if (errMsg) errMsg.classList.remove("visible");

  // Return focus
  if (_composeTriggerEl && document.body.contains(_composeTriggerEl)) {
    _composeTriggerEl.focus();
  }
  _composeTriggerEl = null;
}

function updateComposeBarState() {
  var bar = document.getElementById("compose-bar");
  var label = document.getElementById("compose-trigger-label");
  var fab = document.getElementById("compose-fab");

  if (state.pipelineActive && state.researchQuery) {
    if (bar) bar.classList.add("has-active-query");
    if (label) label.textContent = truncStr(state.researchQuery, 60);
    if (fab) fab.classList.add("pulse");
  } else {
    if (bar) bar.classList.remove("has-active-query");
    if (label) label.textContent = "New research...";
    if (fab) fab.classList.remove("pulse");
  }
}

function submitResearchFromPayload(payload) {
  if (!payload.query || payload.query.trim().length < 5) {
    var textarea = document.getElementById("compose-query");
    var errMsg = document.getElementById("compose-error-msg");
    if (textarea) textarea.classList.add("error");
    if (errMsg) errMsg.classList.add("visible");
    showToast("Please enter a research question (at least 5 characters)", "warning");
    return;
  }
  var body = {
    query: payload.query.trim(),
    depth: payload.depth || "standard",
    application: "general",
    region: "GLOBAL",
    document_ids: payload.documentIds || []
  };
  var submitBtn = document.getElementById("compose-submit");
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Starting..."; submitBtn.classList.add("loading"); }
  var textarea = document.getElementById("compose-query");
  if (textarea) textarea.setAttribute("readonly", "");

  fetch("/api/research", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  })
  .then(function(r) { return r.json().then(function(d) { return { ok: r.ok, data: d }; }); })
  .then(function(result) {
    if (!result.ok) {
      showToast(result.data.error || "Failed to start research", "error");
      _resetComposeButton();
      return;
    }
    state.pipelineActive = true;
    state.researchQuery = body.query;
    state.vectorId = result.data.vector_id;
    setText("user-progress-query", body.query);
    setText("vector-id", result.data.vector_id);
    showToast("Research started: " + result.data.vector_id, "info");
    _announce("Research started: " + result.data.vector_id);
    closeCompose();
    // Clear textarea for next use
    var ta = document.getElementById("compose-query");
    if (ta) ta.value = "";
    updateComposeBarState();
    if (typeof updateUIVisibility === "function") updateUIVisibility();
    setTimeout(function() { if (typeof loadSnapshot === "function") loadSnapshot(); }, 1500);
    _resetComposeButton();
  })
  .catch(function(err) {
    showToast("Network error: " + err.message, "error");
    _resetComposeButton();
  });
}

function _resetComposeButton() {
  var btn = document.getElementById("compose-submit");
  if (btn) { btn.disabled = false; btn.textContent = "Research"; btn.classList.remove("loading"); }
  var textarea = document.getElementById("compose-query");
  if (textarea) textarea.removeAttribute("readonly");
}

function _announce(msg) {
  var el = document.getElementById("global-announcer");
  if (el) el.textContent = msg;
}

/* Run on DOMContentLoaded */
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", function() {
    initSovereignBadge();
    initRBAC();
    initShellControls();
    initCompose();
  });
} else {
  initSovereignBadge();
  initRBAC();
  initShellControls();
  initCompose();
}
