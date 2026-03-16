/* =====================================================================
   research_view.js — Master-detail research view, activity log,
   view renderers, phase list + detail, pipeline extras,
   Gantt/Funnel/Gauge viz builders
   ===================================================================== */

/* =====================================================================
   Activity Log
   ===================================================================== */
var MAX_ACTIVITY = 30;
var activityItems = [];

function addActivity(icon, html, ts) {
  var timeStr = ts ? new Date(ts).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : "";
  activityItems.push({ icon: icon, html: html, time: timeStr });
  if (activityItems.length > MAX_ACTIVITY) activityItems.shift();
  if (state.activeView === "research") renderActivityLog();
}

function renderActivityLog() {
  var el = document.getElementById("activity-log");
  if (!el) return;
  el.innerHTML = activityItems.slice().reverse().map(function(a) {
    return '<div class="activity-item">' +
      '<span class="activity-icon">' + a.icon + '</span>' +
      '<span class="activity-time">' + a.time + '</span>' +
      '<span class="activity-text">' + a.html + '</span></div>';
  }).join("");
}

/* =====================================================================
   View Renderers
   ===================================================================== */
function renderView(viewId) {
  switch (viewId) {
    case "research": safeRender(renderResearchView, "Failed to render research view."); break;
    case "evidence": safeRender(renderEvidenceView, "Failed to render evidence view."); break;
    case "report": safeRender(renderReportView, "Failed to render report view."); break;
    case "advanced": safeRender(function() { renderAdvancedTab(state.activeAdvTab); }, "Failed to render advanced view."); break;
    case "memory": safeRender(function() { if (typeof renderMemoryDashboard === "function") renderMemoryDashboard("memory-dashboard-root"); }, "Failed to render memory view."); break;
    case "pipelines": safeRender(function() { if (typeof renderPipelinesView === "function") renderPipelinesView(); }, "Failed to render pipelines view."); break;
    case "campaigns": safeRender(function() { if (typeof renderCampaignView === "function") renderCampaignView(); }, "Failed to render campaigns view."); break;
  }
}

/* =====================================================================
   RESEARCH VIEW — Master-Detail (Phase List + Detail Pane)
   ===================================================================== */
function renderResearchView() {
  renderPhaseList();
  // If no phase selected yet, auto-select the first active or first with entries
  if (!state.selectedPhase) {
    var firstActive = null;
    var firstWithEntries = null;
    NODE_ORDER.forEach(function(n) {
      if (!firstActive && state.phaseStatus[n] === 'active') firstActive = n;
      if (!firstWithEntries && state.reasoningByPhase[n] && state.reasoningByPhase[n].length) firstWithEntries = n;
    });
    if (firstActive) selectPhase(firstActive, true);
    else if (firstWithEntries) selectPhase(firstWithEntries, true);
  } else {
    renderPhaseDetail(state.selectedPhase);
  }
  // Update total entry count in header
  var countEl = document.getElementById("reasoning-count");
  var totalEntries = 0;
  NODE_ORDER.forEach(function(n) { totalEntries += (state.reasoningByPhase[n] || []).length; });
  if (countEl) countEl.textContent = totalEntries + " entries";
  renderActivityLog();
  renderPipelineExtras();
}

/* =====================================================================
   Phase List (Left Panel) — Compact rows with timeline dots
   ===================================================================== */
function renderPhaseList() {
  var list = document.getElementById('phase-list');
  if (!list) return;
  var html = '';
  var doneCount = 0;
  NODE_ORDER.forEach(function(node) {
    var status = state.phaseStatus[node] || 'pending';
    if (status === 'done') doneCount++;
    var dur = '';
    if (state.nodeTimings[node]) {
      var totalMs = 0;
      if (Array.isArray(state.nodeTimings[node])) {
        state.nodeTimings[node].forEach(function(t) { totalMs += (t.duration_ms || 0); });
      } else if (state.nodeTimings[node].duration_s) {
        totalMs = state.nodeTimings[node].duration_s * 1000;
      }
      if (totalMs > 0) dur = fmtDuration(totalMs);
    }
    var selected = (state.selectedPhase === node) ? ' selected' : '';
    var entryCount = (state.reasoningByPhase[node] || []).length;
    html += '<div class="phase-row ' + status + selected + '" '
         + 'data-node="' + node + '" onclick="selectPhase(\'' + node + '\')">'
         + '<span class="phase-row-dot"></span>'
         + '<span class="phase-row-name">' + esc(NODE_LABELS[node] || node) + '</span>'
         + '<span class="phase-row-duration">' + (dur || (entryCount > 0 ? entryCount : '')) + '</span>'
         + '</div>';
  });
  list.innerHTML = html;
  // Update progress counter
  var prog = document.getElementById('phase-progress');
  if (prog) prog.textContent = doneCount + '/' + NODE_ORDER.length;
}

/* =====================================================================
   Phase Selection — Master-detail switching
   ===================================================================== */
function selectPhase(node, isAutoFollow) {
  // Manual selection pinning: once user manually clicks a phase,
  // auto-follow stops unless Auto-nav is on
  if (!isAutoFollow) {
    state.userPinnedPhase = true;
  }
  state.selectedPhase = node;
  // Update phase list selection highlight
  document.querySelectorAll('.phase-row').forEach(function(el) {
    el.classList.toggle('selected', el.dataset.node === node);
  });
  // Update detail header
  var nameEl = document.getElementById('phase-detail-name');
  var statusEl = document.getElementById('phase-detail-status');
  var metaEl = document.getElementById('phase-detail-meta');
  var iconEl = document.getElementById('phase-detail-icon');
  if (nameEl) nameEl.textContent = NODE_LABELS[node] || node;
  if (iconEl) iconEl.textContent = NODE_ICONS[node] || '';
  var status = state.phaseStatus[node] || 'pending';
  if (statusEl) {
    statusEl.textContent = status;
    statusEl.className = 'phase-detail-status ' + status;
  }
  // Show duration/token meta
  if (metaEl) {
    var entries = state.reasoningByPhase[node] || [];
    var totalTokens = 0;
    entries.forEach(function(e) { totalTokens += (e.tokens || 0); });
    var parts = [];
    if (entries.length) parts.push(entries.length + ' entries');
    if (totalTokens > 0) parts.push(totalTokens.toLocaleString() + ' tok');
    metaEl.textContent = parts.join(' · ');
  }
  // Render entries into detail stream
  renderPhaseDetail(node);
}

function renderPhaseDetail(node) {
  var stream = document.getElementById('phase-detail-stream');
  if (!stream) return;
  var entries = state.reasoningByPhase[node] || [];
  if (entries.length === 0) {
    stream.innerHTML = '<div class="empty-state">No entries yet for '
      + esc(NODE_LABELS[node] || node) + '</div>';
    return;
  }
  // Render reasoning entries (same format as before, just in the detail pane)
  var html = '';
  entries.forEach(function(entry, i) {
    html += renderReasoningEntry(entry, node, i);
  });
  stream.innerHTML = html;
  // Auto-scroll to bottom
  if (typeof window.polaris_autoScrollStream === 'function') {
    window.polaris_autoScrollStream();
  }
}

function renderReasoningEntry(e, node, idx) {
  var text = e.text || "";
  var isLong = text.length > 2000;
  var entryId = node + '-' + idx;
  var html = '<div class="reasoning-entry">';
  html += '<div class="reasoning-entry-header">';
  html += '<span class="reasoning-call-type">' + esc(e.call_type) + '</span>';
  html += '<span class="reasoning-ts">' + esc((e.ts || '').substring(11, 19)) + '</span>';
  if (e.tokens) html += '<span class="reasoning-tokens">' + e.tokens.toLocaleString() + ' tok</span>';
  html += '</div>';
  var safeText = esc(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>');
  html += '<div class="reasoning-text' + (isLong ? ' collapsed' : '') + '" id="rt-' + entryId + '">' + safeText + '</div>';
  if (isLong) {
    html += '<div class="reasoning-show-more" role="button" tabindex="0" onclick="toggleReasoningText(\'' + entryId + '\', this)" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){toggleReasoningText(\'' + entryId + '\', this);event.preventDefault();}">Show more (' + text.length.toLocaleString() + ' chars)</div>';
  }
  html += '</div>';
  return html;
}

/* =====================================================================
   Phase Status Change Handler — Auto-follow logic
   ===================================================================== */
// Auto-follow: only auto-select active phase when:
// 1. Auto-nav is enabled (state.autoTab === true), OR
// 2. User hasn't manually clicked a phase yet (!state.userPinnedPhase)
// Once user manually clicks a phase, stay pinned until Auto-nav re-enabled.
function onPhaseStatusChange(node, status) {
  if (status === 'active') {
    if (state.autoTab || !state.userPinnedPhase) {
      selectPhase(node, true);  // isAutoFollow = true
    }
  }
  // Always re-render the phase list to update dots
  renderPhaseList();
}

// When Auto-nav is re-enabled, reset pinning
function resetPhasePinning() {
  state.userPinnedPhase = false;
}

/* =====================================================================
   Legacy compatibility — togglePhaseBlock still works if called
   ===================================================================== */
function togglePhaseBlock(node) {
  selectPhase(node);
}

function toggleReasoningText(entryId, btn) {
  var el = document.getElementById("rt-" + entryId);
  if (!el) return;
  var isCollapsed = el.classList.contains("collapsed");
  el.classList.toggle("collapsed");
  btn.textContent = isCollapsed ? "Show less" : "Show more (" + el.textContent.length.toLocaleString() + " chars)";
}

/* Pipeline extras (right column) */
function renderPipelineExtras() {
  // Gantt
  var ganttEl = document.getElementById("pipeline-gantt");
  if (ganttEl) ganttEl.innerHTML = buildGantt(state.nodeTimings);

  // Funnel
  var funnelEl = document.getElementById("pipeline-funnel");
  if (funnelEl) {
    var stages = [];
    if (state.totalResults) stages.push({ label: "Searched", count: state.totalResults });
    if (state.funnelScored) stages.push({ label: "On-topic", count: state.funnelScored });
    if (state.fetches.length) stages.push({ label: "Fetched", count: state.fetches.length });
    if (state.funnelExtracted) stages.push({ label: "Extracted", count: state.funnelExtracted });
    if (state.dedupDetail) stages.push({ label: "Deduped", count: state.dedupDetail.after });
    else if (state.dedupStats) stages.push({ label: "Deduped", count: state.dedupStats.post_dedup });
    if (state.funnelVerified) stages.push({ label: "Verified", count: state.funnelVerified });
    if (state.citations) stages.push({ label: "Cited", count: state.citations });
    if (stages.length) funnelEl.innerHTML = buildFunnel(stages);
  }
}

/* =====================================================================
   VIZ BUILDERS
   ===================================================================== */
function buildFaithGauge(pct) {
  var size = 100, cx = size / 2, cy = size / 2, r = 40, sw = 7;
  var circ = 2 * Math.PI * r;
  var offset = circ * (1 - pct);
  var color = pct >= 0.80 ? "var(--success)" : pct >= 0.60 ? "var(--warning)" : "var(--error)";
  var pctStr = (pct * 100).toFixed(1) + "%";
  return '<div class="faith-gauge-circle"><svg role="img" aria-label="Faithfulness gauge: ' + pctStr + '" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">' +
    '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="var(--border)" stroke-width="' + sw + '"/>' +
    '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="' + sw + '"' +
    ' stroke-dasharray="' + circ.toFixed(1) + '" stroke-dashoffset="' + offset.toFixed(1) + '"' +
    ' stroke-linecap="round" transform="rotate(-90 ' + cx + ' ' + cy + ')" style="transition:stroke-dashoffset 0.8s"/>' +
    '<text x="' + cx + '" y="' + (cy + 1) + '" text-anchor="middle" dominant-baseline="middle"' +
    ' font-family="Inter,sans-serif" font-size="16" font-weight="700" fill="' + color + '">' + pctStr + '</text></svg></div>';
}

function buildStrengthMeter(gold, silver, bronze) {
  var total = gold + silver + bronze;
  if (total === 0) return '';
  var gP = Math.round((gold / total) * 100), sP = Math.round((silver / total) * 100), bP = 100 - gP - sP;
  var badge = gold > silver + bronze ? "Strong" : gold + silver > bronze ? "Moderate" : "Weak";
  var badgeColor = badge === "Strong" ? "var(--success)" : badge === "Moderate" ? "var(--warning)" : "var(--error)";
  return '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">' +
    '<span class="section-title" style="margin:0">Evidence Strength</span>' +
    '<span style="font-size:11px;font-weight:600;color:' + badgeColor + '">' + badge + ' (' + total + ')</span></div>' +
    '<div class="strength-bar">' +
    '<div class="strength-segment strength-gold" style="width:' + gP + '%"></div>' +
    '<div class="strength-segment strength-silver" style="width:' + sP + '%"></div>' +
    '<div class="strength-segment strength-bronze" style="width:' + bP + '%"></div></div>' +
    '<div class="strength-labels"><span>GOLD: ' + gold + '</span><span>SILVER: ' + silver + '</span><span>BRONZE: ' + bronze + '</span></div>';
}

function buildFunnel(stages) {
  if (!stages.length) return '';
  var maxVal = Math.max.apply(null, stages.map(function(s) { return s.count; }).concat([1]));
  var colors = ["#3b82f6","#6366f1","#a78bfa","#10b981","#f59e0b","#22d3ee","#f472b6","#fb923c"];
  return '<div class="card"><div class="section-title">Evidence Funnel</div>' +
    stages.map(function(s, i) {
      var pct = Math.round((s.count / maxVal) * 100);
      var col = colors[i % colors.length];
      return '<div class="funnel-row"><span class="funnel-label">' + esc(s.label) + '</span>' +
        '<div class="funnel-track"><div class="funnel-fill" style="width:' + pct + '%;background:' + col + '"></div></div>' +
        '<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-tertiary);min-width:35px;text-align:right">' + s.count + '</span></div>';
    }).join("") + '</div>';
}

function buildGantt(nodeTimings) {
  var allTimings = [];
  NODE_ORDER.forEach(function(n) {
    if (nodeTimings[n]) nodeTimings[n].forEach(function(t) {
      allTimings.push({ node: n, start: t.start, end: t.end || Date.now(), duration_ms: t.duration_ms, metrics: t.metrics, isActive: !t.end });
    });
  });
  if (!allTimings.length) return '';
  var minStart = Math.min.apply(null, allTimings.map(function(t) { return t.start; }));
  var maxEnd = Math.max.apply(null, allTimings.map(function(t) { return t.end; }));
  var totalSpan = maxEnd - minStart || 1;
  var html = '<div class="card"><div class="section-title">Pipeline Timeline</div><div class="gantt-container">';
  NODE_ORDER.forEach(function(n) {
    if (!nodeTimings[n] || !nodeTimings[n].length) return;
    var bars = '';
    nodeTimings[n].forEach(function(t) {
      var left = Math.round(((t.start - minStart) / totalSpan) * 100);
      var width = Math.max(1, Math.round((((t.end || Date.now()) - t.start) / totalSpan) * 100));
      var label = t.duration_ms ? fmtDuration(t.duration_ms) : '';
      bars += '<div class="gantt-bar gantt-bar-' + n + (t.isActive ? ' active' : '') + '" style="left:' + left + '%;width:' + width + '%">' + label + '</div>';
    });
    html += '<div class="gantt-row"><span class="gantt-label">' + esc(NODE_LABELS[n]) + '</span>' +
      '<div class="gantt-track">' + bars + '</div></div>';
  });
  html += '</div></div>';
  return html;
}

function buildVerdictBar(supported, partial, notSupported, noVerdict) {
  var total = supported + partial + notSupported + noVerdict;
  if (total === 0) return '';
  var sP = Math.round((supported / total) * 100), pP = Math.round((partial / total) * 100), nP = Math.round((notSupported / total) * 100), vP = 100 - sP - pP - nP;
  return '<div class="verdict-bar-container">' +
    (sP > 0 ? '<div class="verdict-seg verdict-supported" style="width:' + sP + '%">' + (sP > 8 ? supported : '') + '</div>' : '') +
    (pP > 0 ? '<div class="verdict-seg verdict-partial" style="width:' + pP + '%">' + (pP > 8 ? partial : '') + '</div>' : '') +
    (nP > 0 ? '<div class="verdict-seg verdict-not-supported" style="width:' + nP + '%">' + (nP > 8 ? notSupported : '') + '</div>' : '') +
    (vP > 0 ? '<div class="verdict-seg verdict-no-verdict" style="width:' + vP + '%"></div>' : '') +
    '</div><div class="verdict-legend">' +
    '<span class="verdict-legend-item"><span class="verdict-legend-dot" style="background:var(--success)"></span>Supported: ' + supported + '</span>' +
    '<span class="verdict-legend-item"><span class="verdict-legend-dot" style="background:var(--warning)"></span>Partial: ' + partial + '</span>' +
    '<span class="verdict-legend-item"><span class="verdict-legend-dot" style="background:var(--error)"></span>Not Supported: ' + notSupported + '</span></div>';
}

function buildGateGrid(gates) {
  if (!gates.length) return '';
  return '<div class="gate-grid">' + gates.map(function(g) {
    var passed = g.actual >= g.threshold;
    var pct = g.threshold > 0 ? Math.min(100, Math.round((g.actual / g.threshold) * 100)) : (g.actual > 0 ? 100 : 0);
    var fillColor = passed ? "var(--success)" : "var(--error)";
    var displayVal = g.isPercent ? (g.actual * 100).toFixed(1) + "%" : (typeof g.actual === "number" ? g.actual.toLocaleString() : g.actual);
    var delta = g.actual - g.threshold;
    var deltaStr = g.isPercent ? (delta >= 0 ? "+" : "") + (delta * 100).toFixed(1) + "%" : (delta >= 0 ? "+" : "") + delta.toLocaleString();
    return '<div class="gate-card"><div class="gate-card-header"><span class="gate-card-name">' + esc(g.name) + '</span>' +
      '<span class="gate-badge ' + (passed ? "gate-pass" : "gate-fail") + '">' + (passed ? "PASS" : "FAIL") + '</span></div>' +
      '<div class="gate-value" style="color:' + fillColor + '">' + displayVal + '</div>' +
      '<div class="gate-bar-track"><div class="gate-bar-fill" style="width:' + Math.min(pct, 100) + '%;background:' + fillColor + '"></div>' +
      '<div class="gate-threshold" style="left:100%"></div></div>' +
      '<div class="gate-delta ' + (delta >= 0 ? "positive" : "negative") + '">' + deltaStr + '</div></div>';
  }).join("") + '</div>';
}

function buildSignalRadar(signals) {
  if (!signals || !signals.length) return '';
  var size = 180, cx = size / 2, cy = size / 2, maxR = 65, n = signals.length;
  function polarToXY(angle, radius) { var rad = (angle - 90) * Math.PI / 180; return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) }; }
  var svg = '<svg role="img" aria-label="5-signal radar chart showing evidence quality scores" width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">';
  [0.25, 0.5, 0.75, 1.0].forEach(function(f) { svg += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (maxR * f) + '" fill="none" stroke="var(--border)" stroke-width="0.5"/>'; });
  for (var i = 0; i < n; i++) {
    var angle = (360 / n) * i, end = polarToXY(angle, maxR);
    svg += '<line x1="' + cx + '" y1="' + cy + '" x2="' + end.x.toFixed(1) + '" y2="' + end.y.toFixed(1) + '" stroke="var(--border)" stroke-width="0.5"/>';
    var lp = polarToXY(angle, maxR + 14);
    svg += '<text x="' + lp.x.toFixed(1) + '" y="' + lp.y.toFixed(1) + '" text-anchor="middle" font-size="9" fill="var(--text-tertiary)" font-family="Inter,sans-serif">' + esc(signals[i].name) + '</text>';
  }
  var points = signals.map(function(s, i) { var p = polarToXY((360 / n) * i, maxR * Math.min(s.value, 1)); return p.x.toFixed(1) + ',' + p.y.toFixed(1); }).join(' ');
  svg += '<polygon points="' + points + '" fill="rgba(56,189,248,0.15)" stroke="var(--accent)" stroke-width="1.5"/>';
  signals.forEach(function(s, i) { var p = polarToXY((360 / n) * i, maxR * Math.min(s.value, 1)); svg += '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="3" fill="var(--accent)"/>'; });
  svg += '</svg>';
  return '<div class="signal-radar-container">' + svg + '</div>';
}

/* =====================================================================
   AI Streaming Auto-Scroll (Phase 4.3)
   Now targets .phase-detail-stream instead of .reasoning-stream
   ===================================================================== */
(function initStreamAutoScroll() {
  var streamContainer = document.querySelector('.phase-detail-stream');
  if (!streamContainer) return;

  // Create anchor element if not present
  var anchor = streamContainer.querySelector('.stream-anchor');
  if (!anchor) {
    anchor = document.createElement('div');
    anchor.className = 'stream-anchor';
    anchor.setAttribute('aria-hidden', 'true');
    streamContainer.appendChild(anchor);
  }

  // Add stream-container class for CSS overflow-anchor
  streamContainer.classList.add('stream-container');

  // Create jump-to-bottom button if not present
  var jumpBtn = document.getElementById('jump-to-bottom');
  if (!jumpBtn) {
    jumpBtn = document.createElement('button');
    jumpBtn.id = 'jump-to-bottom';
    jumpBtn.className = 'jump-btn';
    jumpBtn.style.display = 'none';
    jumpBtn.setAttribute('aria-label', 'Jump to latest');
    jumpBtn.textContent = '\u2193 Jump to latest';
    jumpBtn.addEventListener('click', function() {
      anchor.scrollIntoView({ behavior: 'smooth', block: 'end' });
    });
    streamContainer.parentNode.insertBefore(jumpBtn, streamContainer.nextSibling);
  }

  var userAtBottom = true;
  var observer = new IntersectionObserver(function(entries) {
    userAtBottom = entries[0].isIntersecting;
    jumpBtn.style.display = userAtBottom ? 'none' : 'flex';
  }, { root: streamContainer, threshold: 0.1 });

  observer.observe(anchor);

  // Export auto-scroll function for use by SSE handlers
  window.polaris_autoScrollStream = function() {
    if (userAtBottom && anchor) {
      anchor.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  };
})();
