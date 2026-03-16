/* =====================================================================
   workspace_manager.js — NotebookLM-style Unified Research Interface

   Central orchestrator for the 3-column workspace:
   - FSM (idle → running → report) via setWorkspacePhase()
   - Infinite thread management (prompt bubbles, report blocks)
   - Dynamic pulse progress (micro-task feed)
   - Chat submit handler
   - Right sidebar rendering (citations, metrics, memory)
   - SSE event routing to workspace UI

   Depends on: core.js (state, esc, getPhaseLabel, safeMarkdown, etc.)
   ===================================================================== */

/* =====================================================================
   State
   ===================================================================== */
var _wsPhase = "idle";  // "idle" | "running" | "report"
var _wsThread = [];     // Array of {type: "prompt"|"report"|"progress", content, vectorId, timestamp}
var _wsProgressTasks = []; // Micro-task feed for dynamic pulse progress
var _wsActiveTask = "";    // Current active task label
var _wsDepth = "standard"; // Selected research depth
var _wsCurrentReportEl = null; // Reference to the current report block element
var _wsMaxProgressTasks = 20; // Max visible completed tasks
var _wsMobileExpandedCite = null; // Currently expanded inline citation (mobile)
var _wsDiscoveredSources = [];  // {url, domain, title, status, ts}
var _wsTaskFeedItems = [];      // {label, status, duration, ts}
var _wsUrlToEvidence = {};      // URL → [{eid, quote, title}] map for popover enrichment
var _wsMaxTaskFeedItems = 30;
var _wsMemoryItems = [];        // Cached memory items for search filtering
var _wsPaused = false;          // Transport: pause state
var _wsTimerInterval = null;    // F02: Timer tick interval
var _wsCurrentFeedPhase = "";   // F10: Current phase for feed grouping

/* =====================================================================
   Phase Management (FSM)
   ===================================================================== */
function setWorkspacePhase(phase) {
  // Guard: never regress from "report" to "idle" when pipeline is complete
  if (phase === "idle" && _wsPhase === "report" && state.pipelineComplete) {
    return;
  }
  var prevPhase = _wsPhase;
  _wsPhase = phase;
  state.workspacePhase = phase;
  var ws = document.getElementById("workspace");
  if (ws) ws.setAttribute("data-phase", phase);
  _updateWorkspaceVisibility();
  // D4: Update dynamic island
  if (phase === "running") {
    _updateDynamicIsland("running", _wsActiveTask || "Researching...");
  } else {
    _updateDynamicIsland(phase, "");
  }
  // D4: Reset breadcrumb when idle
  if (phase === "idle") {
    _updateBreadcrumb(null);
  }
  // Right panel: set section visibility + collapse state per phase
  if (phase === "running") {
    _wsDiscoveredSources = [];
    _wsTaskFeedItems = [];
    _wsPaused = false;
  }
  if (phase === "report" && prevPhase === "running") {
    // F02: Stop timer when leaving running phase
    if (_wsTimerInterval) { clearInterval(_wsTimerInterval); _wsTimerInterval = null; }
    _animateRunToReport();
  }
  if (phase === "idle" && _wsTimerInterval) {
    clearInterval(_wsTimerInterval); _wsTimerInterval = null;
  }
  // Hide transport controls when not running
  var transport = document.querySelector(".ws-transport-controls");
  if (transport) {
    transport.style.display = (phase === "running") ? "" : "none";
  }
  _updateRightPanelForPhase(phase);
}

function _updateWorkspaceVisibility() {
  var idle = document.getElementById("ws-idle");
  var chatInput = document.getElementById("ws-chat-input");
  var thread = document.getElementById("ws-thread");
  var textarea = document.getElementById("ws-chat-textarea");
  if (!idle) return;

  if (_wsPhase === "idle") {
    if (_wsThread.length > 0) {
      // Previous thread entries exist — show thread, hide idle
      thread.style.display = "block";
      idle.style.display = "none";
    } else {
      // No thread entries — show idle, hide thread
      idle.style.display = "flex";
      thread.style.display = "none";
    }
    if (textarea) textarea.placeholder = "Enter your research question...";
  } else if (_wsPhase === "running") {
    idle.style.display = "none";
    thread.style.display = "block";
    if (textarea) textarea.placeholder = "Steer this research...";
  } else {
    idle.style.display = "none";
    thread.style.display = "block";
    if (textarea) textarea.placeholder = "Ask a follow-up question...";
  }
}

/* =====================================================================
   Thread Management
   ===================================================================== */
function appendPromptBubble(query) {
  var threadInner = document.getElementById("ws-thread-inner");
  if (!threadInner) return;

  var entry = {
    type: "prompt",
    content: query,
    timestamp: new Date().toISOString()
  };
  _wsThread.push(entry);

  var bubble = document.createElement("div");
  bubble.className = "ws-prompt-bubble";
  bubble.innerHTML =
    '<div class="ws-prompt-avatar">Q</div>' +
    '<div class="ws-prompt-content">' +
      '<div class="ws-prompt-text">' + esc(query) + '</div>' +
      '<div class="ws-prompt-meta">' + _formatTimestamp(entry.timestamp) + '</div>' +
    '</div>';
  threadInner.appendChild(bubble);
  _scrollThreadToBottom();
}

function appendProgressBlock() {
  var threadInner = document.getElementById("ws-thread-inner");
  if (!threadInner) return;

  // Remove any existing progress block
  var existing = threadInner.querySelector(".ws-progress-block");
  if (existing) existing.remove();

  _wsProgressTasks = [];
  _wsActiveTask = "Starting research...";
  _wsCurrentFeedPhase = "";  // F10: Reset phase grouping

  var block = document.createElement("div");
  block.className = "ws-progress-block";
  block.id = "ws-active-progress";
  block.innerHTML =
    '<div class="ws-progress-active" id="ws-progress-active-label">' +
      '<div class="ws-progress-pulse"></div>' +
      '<span id="ws-progress-active-text">Starting research...</span>' +
    '</div>' +
    '<div class="ws-progress-tasks" id="ws-progress-tasks"></div>' +
    // F07: Live research metrics row
    '<div class="ws-progress-metrics" id="ws-progress-metrics">' +
      '<div class="ws-progress-metric">' +
        '<span class="ws-progress-metric-val" id="ws-pm-sources">0</span>' +
        '<span class="ws-progress-metric-label">sources</span>' +
      '</div>' +
      '<div class="ws-progress-metric">' +
        '<span class="ws-progress-metric-val" id="ws-pm-evidence">0</span>' +
        '<span class="ws-progress-metric-label">evidence</span>' +
      '</div>' +
      '<div class="ws-progress-metric">' +
        '<span class="ws-progress-metric-val" id="ws-pm-faith">--</span>' +
        '<span class="ws-progress-metric-label">verified</span>' +
      '</div>' +
    '</div>' +
    '<div class="ws-progress-footer">' +
      '<span class="ws-progress-time" id="ws-progress-time"></span>' +
      '<button class="ws-progress-cancel" onclick="cancelResearch()">Cancel</button>' +
    '</div>';
  threadInner.appendChild(block);

  // F06: Source discovery card below the progress block (fills center panel space)
  var existingDisc = threadInner.querySelector(".ws-source-discovery");
  if (existingDisc) existingDisc.remove();
  var discCard = document.createElement("div");
  discCard.className = "ws-source-discovery";
  discCard.id = "ws-source-discovery";
  discCard.innerHTML =
    '<div class="ws-source-discovery-header">' +
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
      '<span>Sources discovered</span>' +
      '<span class="ws-source-discovery-count" id="ws-source-discovery-count">0</span>' +
    '</div>' +
    '<div class="ws-source-discovery-list" id="ws-source-discovery-list"></div>';
  threadInner.appendChild(discCard);
  _scrollThreadToBottom();

  // F02: Start timer tick interval
  if (_wsTimerInterval) clearInterval(_wsTimerInterval);
  _wsTimerInterval = setInterval(function() {
    // Update sidebar timer
    _updateSidebarMetrics();
    // Update progress footer timer
    var timeEl = document.getElementById("ws-progress-time");
    if (timeEl && state.startTime && state.currentNode) {
      timeEl.textContent = estimateTimeRemaining(state.currentNode);
    } else if (timeEl && state.startTime) {
      var elapsed = Math.floor((Date.now() - state.startTime) / 1000);
      var mm = Math.floor(elapsed / 60);
      var ss = elapsed % 60;
      timeEl.textContent = mm + "m " + String(ss).padStart(2, "0") + "s elapsed";
    }
  }, 1000);
}

function addProgressTask(label, status) {
  // status: "done" | "active" | "pending" (defaults to "done")
  if (!status) status = "done";
  var icon = status === "done" ? "\u2713" : status === "active" ? "\u25CB" : "\u25CB";

  if (status === "active") {
    _wsActiveTask = label;
    var activeText = document.getElementById("ws-progress-active-text");
    if (activeText) activeText.textContent = label;
  }

  if (status === "done") {
    _wsProgressTasks.push({ label: label, status: "done" });
    // Trim old tasks
    if (_wsProgressTasks.length > _wsMaxProgressTasks) {
      _wsProgressTasks = _wsProgressTasks.slice(-_wsMaxProgressTasks);
    }
    _renderProgressTasks();
  }

  // Update time estimate
  var timeEl = document.getElementById("ws-progress-time");
  if (timeEl && state.currentNode) {
    timeEl.textContent = estimateTimeRemaining(state.currentNode);
  }

  _scrollThreadToBottom();
}

function _renderProgressTasks() {
  var container = document.getElementById("ws-progress-tasks");
  if (!container) return;

  var html = "";
  _wsProgressTasks.forEach(function(t) {
    html += '<div class="ws-progress-task done">' +
      '<span class="ws-progress-task-icon">\u2713</span>' +
      '<span>' + esc(t.label) + '</span>' +
    '</div>';
  });
  container.innerHTML = html;
}

function appendReportBlock(reportContent, bibliography) {
  var threadInner = document.getElementById("ws-thread-inner");
  if (!threadInner) return;

  // Remove progress block
  var progress = document.getElementById("ws-active-progress");
  if (progress) progress.remove();

  var entry = {
    type: "report",
    content: reportContent,
    vectorId: state.vectorId,
    timestamp: new Date().toISOString()
  };
  _wsThread.push(entry);

  var block = document.createElement("div");
  block.className = "ws-report-block";
  block.setAttribute("data-vector-id", state.vectorId || "");

  // Quality banner
  var verTotal = state.verificationVerdicts.length;
  var verFaith = state.verificationVerdicts.filter(function(v) { return v.verdict === "SUPPORTED" || v.is_faithful; }).length;
  var faithPct = verTotal > 0 ? ((verFaith / verTotal) * 100).toFixed(0) : "0";
  var srcCount = state.sources.size || state.bibliography.length || 0;
  var bannerClass = verTotal > 0 && (verFaith / verTotal) >= 0.70 ? "" : " partial";
  var bannerIcon = bannerClass === "" ? "\u2713" : "\u26A0";

  var bannerHtml = '<div class="ws-report-quality-banner' + bannerClass + '">' +
    '<div class="ws-report-quality-icon">' + bannerIcon + '</div>' +
    '<div class="ws-report-quality-text">' +
      '<div class="ws-report-quality-title">' + verFaith + ' claims verified from ' + srcCount + ' sources</div>' +
      '<div class="ws-report-quality-sub">' + faithPct + '% verification rate across ' + (state.words || 0).toLocaleString() + ' words</div>' +
    '</div>' +
  '</div>';

  // Render report body
  var rendered = "";
  try {
    rendered = safeMarkdown(reportContent);
    // Inject clickable citations
    rendered = rendered.replace(/\[(\d+)\]/g, function(m, num) {
      return '<span class="cite-ref" data-cite="' + num + '" onclick="showCitePopover(event, ' + num + ')">[' + num + ']</span>';
    });
    // Add IDs to headings
    var headingIdx = 0;
    rendered = rendered.replace(/<h([23])([^>]*)>(.*?)<\/h\1>/gi, function(match, level, attrs, content) {
      headingIdx++;
      var id = "ws-section-" + state.vectorId + "-" + headingIdx;
      return '<h' + level + attrs + ' id="' + id + '">' + content + '</h' + level + '>';
    });
  } catch(e) {
    rendered = '<pre>' + esc(reportContent) + '</pre>';
  }

  // Bibliography
  var bibHtml = "";
  if (bibliography && bibliography.length) {
    bibHtml = '<div class="ws-report-bib"><h3>Sources (' + bibliography.length + ')</h3><div class="source-cards">';
    bibliography.forEach(function(b, i) {
      var url = b.url || b.source_url || "";
      var title = b.title || b.domain || url || ("Source " + (i + 1));
      var domain = url ? extractDomain(url) : "";
      var faviconUrl = domain ? 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(domain) + '&sz=32' : '';

      bibHtml += '<div class="source-card" id="ws-bib-' + (i + 1) + '">' +
        '<span class="source-num">[' + (i + 1) + ']</span>' +
        '<div class="source-favicon">';
      if (faviconUrl) {
        bibHtml += '<img src="' + esc(faviconUrl) + '" alt="" loading="lazy" onerror="this.style.display=\'none\'">';
      }
      bibHtml += '</div><div class="source-info">';
      if (url) {
        bibHtml += '<div class="source-title"><a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(title) + '</a></div>';
      } else {
        bibHtml += '<div class="source-title">' + esc(title) + '</div>';
      }
      if (domain) bibHtml += '<div class="source-domain">' + esc(domain) + '</div>';
      bibHtml += '</div></div>';
    });
    bibHtml += '</div></div>';
  }

  // Export buttons
  var exportHtml = '<div class="ws-report-export">' +
    '<button class="ws-report-export-btn" onclick="exportReport(\'markdown\')">Markdown</button>' +
    '<button class="ws-report-export-btn" onclick="exportReport(\'docx\')">Word</button>' +
    '<button class="ws-report-export-btn" onclick="exportReport(\'jsonl\')">JSONL</button>' +
  '</div>';

  block.innerHTML = bannerHtml +
    '<div class="ws-report-body">' + rendered + '</div>' +
    bibHtml + exportHtml;

  threadInner.appendChild(block);
  _wsCurrentReportEl = block;
  _scrollThreadToBottom();

  // Initialize scroll-sync citations for this report block
  if (typeof initScrollSync === "function") {
    setTimeout(function() { initScrollSync(block); }, 100);
  }
}

function _scrollThreadToBottom() {
  var thread = document.getElementById("ws-thread");
  if (thread) {
    setTimeout(function() {
      thread.scrollTop = thread.scrollHeight;
    }, 50);
  }
}

function _formatTimestamp(iso) {
  try {
    var d = new Date(iso);
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  } catch(e) { return ""; }
}

/* =====================================================================
   Chat Submit
   ===================================================================== */
function handleWorkspaceChatSubmit(e) {
  if (e) e.preventDefault();
  var textarea = document.getElementById("ws-chat-textarea");
  if (!textarea) return;
  var query = textarea.value.trim();
  if (query.length < 5) return;

  textarea.value = "";
  textarea.style.height = "44px";

  // D2: If running, submit as steering directive instead of new research
  if (_wsPhase === "running") {
    handleSteeringSubmit(query);
    return;
  }

  // Append prompt bubble
  appendPromptBubble(query);

  // D4: Update breadcrumb with query
  _updateBreadcrumb(query);

  // Transition to running
  setWorkspacePhase("running");
  appendProgressBlock();

  // Submit research
  var docIds = [];
  if (typeof getDocumentContext === "function") {
    docIds = getDocumentContext();
  }

  var payload = {
    query: query,
    depth: _wsDepth,
    document_ids: docIds
  };

  fetch("/api/research", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.error) {
      showToast("Research failed: " + data.error, "error");
      setWorkspacePhase("idle");
    } else {
      state.pipelineActive = true;
      state.pipelineComplete = false;
      state.vectorId = data.vector_id || "";
      if (typeof updateComposeBarState === "function") updateComposeBarState();
    }
  })
  .catch(function(err) {
    showToast("Research failed: " + err.message, "error");
    setWorkspacePhase("idle");
  });
}

/* =====================================================================
   Live Steering (D2)
   ===================================================================== */
function handleSteeringSubmit(directive) {
  // Append intervention bubble to thread
  var threadInner = document.getElementById("ws-thread-inner");
  if (threadInner) {
    var bubble = document.createElement("div");
    bubble.className = "ws-intervention-bubble";
    bubble.innerHTML =
      '<div class="ws-intervention-label">Steering Directive</div>' +
      '<div class="ws-intervention-text">' + esc(directive) + '</div>';
    threadInner.appendChild(bubble);
    _scrollThreadToBottom();
  }

  // POST to steering endpoint
  fetch("/api/research/steer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ directive: directive })
  })
  .then(function(r) {
    if (!r.ok) throw new Error("Steering failed (status " + r.status + ")");
    return r.json();
  })
  .then(function(data) {
    showToast("Directive queued", "info");
    addProgressTask("Directive received: " + directive.substring(0, 60), "done");
  })
  .catch(function(err) {
    showToast("Steering failed: " + err.message, "error");
  });
}

/* =====================================================================
   Transport Controls (Pause / Resume / Stop)
   ===================================================================== */
function _togglePauseResearch() {
  _wsPaused = !_wsPaused;
  var btn = document.getElementById("ws-btn-pause");
  if (!btn) return;

  if (_wsPaused) {
    // Show play icon (resume)
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><path d="M3 1.5v11l9-5.5z"/></svg>';
    btn.classList.add("paused");
    btn.setAttribute("aria-label", "Resume");
    btn.setAttribute("title", "Resume");
    _addTaskFeedItem("Paused", "active");
  } else {
    // Show pause icon
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="2" y="1" width="3.5" height="12" rx="1"/><rect x="8.5" y="1" width="3.5" height="12" rx="1"/></svg>';
    btn.classList.remove("paused");
    btn.setAttribute("aria-label", "Pause");
    btn.setAttribute("title", "Pause");
    _addTaskFeedItem("Resumed", "done");
  }

  // POST to pause/resume endpoint
  var endpoint = _wsPaused ? "/api/research/pause" : "/api/research/resume";
  fetch(endpoint, { method: "POST" })
  .then(function(r) {
    if (!r.ok) throw new Error("Status " + r.status);
  })
  .catch(function(err) {
    if (typeof showToast === "function") {
      showToast((_wsPaused ? "Pause" : "Resume") + " not available yet", "info");
    }
  });
}

/* =====================================================================
   SSE Event Routing to Workspace
   ===================================================================== */
function workspaceProcessEvent(ev) {
  if (_wsPhase !== "running" && _wsPhase !== "report") return;

  var evType = ev.type || "";
  var node = ev.node || "";
  var action = ev.action || "";

  // Node start → active micro-task + F10 phase grouping
  if (evType === "node_start" && NODE_ORDER.indexOf(node) >= 0) {
    // F10: Insert phase divider when phase changes
    if (node !== _wsCurrentFeedPhase) {
      _wsCurrentFeedPhase = node;
      var dividerTs = ev.ts ? new Date(ev.ts).getTime() : Date.now();
      _wsTaskFeedItems.push({ label: node, status: "phase_divider", ts: dividerTs, phase: node });
    }
    var label = getPhaseLabel(node, ev, false);
    _addTaskFeedItem(label, "active", "", ev.ts);
    // D4: Update dynamic island with current task (skip if pipeline already completed)
    if (!state.pipelineComplete) {
      _updateDynamicIsland("running", label);
    }
  }

  // Node end → completed micro-task (F04/F05: pass isDone=true for clean labels)
  if (evType === "node_end" && NODE_ORDER.indexOf(node) >= 0) {
    var doneLabel = getPhaseLabel(node, ev, true);
    var durationStr = ev.duration_ms ? fmtDuration(ev.duration_ms) : "";
    _addTaskFeedItem(doneLabel, "done", durationStr, ev.ts);
  }

  // Evidence count updates
  if (evType === "evidence" || action === "evidence_extracted") {
    _updateSidebarMetrics();
  }

  // Build URL→evidence map from evidence_detail events (for popover enrichment)
  if (action === "evidence_detail") {
    var detailItems = ev.items || [];
    for (var di = 0; di < detailItems.length; di++) {
      var item = detailItems[di];
      var srcUrl = (item.source_url || "").replace(/\/+$/, "");
      if (srcUrl && item.id) {
        if (!_wsUrlToEvidence[srcUrl]) _wsUrlToEvidence[srcUrl] = [];
        _wsUrlToEvidence[srcUrl].push({
          eid: item.id,
          quote: item.quote || "",
          title: item.source_title || ""
        });
      }
    }
  }

  // Search results → source discovery (F01+F08: result_count + query text)
  // Skip adding individual search_result items to feed — node_start/node_end
  // already provide phase summaries. Only track source discovery.
  if (evType === "search_result") {
    var urls = ev.urls || [];
    var titles = ev.titles || [];
    for (var si = 0; si < urls.length; si++) {
      _addDiscoveredSource({ url: urls[si], title: titles[si] || "" });
    }
  }

  // Fetch events → source discovery
  if (evType === "fetch" || action === "content_fetched") {
    _addDiscoveredSource({ url: ev.url || "", title: ev.title || "" });
  }

  // Quality gate
  if (evType === "quality_gate" || action === "quality_gate") {
    var gateLabel = "Quality gate: " + (ev.gate_name || ev.passed ? "PASS" : "FAIL");
    _addTaskFeedItem(gateLabel, "done", "", ev.ts);
  }

  // Iteration decision (looping)
  if (evType === "iteration_decision" || action === "iteration_decision") {
    if (ev.should_iterate) {
      _addTaskFeedItem("Iterating: " + (ev.reason || "improving quality") + "...", "active", "", ev.ts);
    }
  }

  // STORM interview
  if (evType === "storm_transcript") {
    var persona = ev.persona || ev.expert || "Expert";
    _addTaskFeedItem("Interviewed " + persona, "done", "", ev.ts);
  }

  // Report assembled → transition to report phase
  if (action === "report_assembled") {
    // Only add completion marker once (pipeline may emit report_assembled per iteration)
    var alreadyMarked = _wsTaskFeedItems.some(function(t) { return t.label === "Research complete"; });
    if (!alreadyMarked) {
      _addTaskFeedItem("Research complete", "done", "", ev.ts);
    }
    // Enrich bibliography entries with evidence data for popover previews
    _enrichBibliography();
    setWorkspacePhase("report");
    appendReportBlock(state.fullReport, state.bibliography);
    _updateSidebarMemory();
    setTimeout(function() { _updateSidebarMemory(); }, 5000);  // Retry after 5s for late promotions
    _updateCitationsCount();
  }

  // Update live metrics in sidebar
  _updateSidebarMetrics();
}

/* =====================================================================
   Bibliography enrichment: cross-reference URLs with evidence for popovers
   ===================================================================== */
function _enrichBibliography() {
  if (!state.bibliography || !state.bibliography.length) return;
  for (var i = 0; i < state.bibliography.length; i++) {
    var bib = state.bibliography[i];
    // Skip if already enriched
    if (bib.evidence_ids && bib.evidence_ids.length) continue;
    var bibUrl = (bib.url || bib.source_url || "").replace(/\/+$/, "");
    if (!bibUrl) continue;
    var matches = _wsUrlToEvidence[bibUrl];
    if (matches && matches.length > 0) {
      bib.evidence_ids = matches.map(function(m) { return m.eid; });
      if (!bib.verification_quote && !bib.quote && matches[0].quote) {
        bib.quote = matches[0].quote;
      }
      if (!bib.title && matches[0].title) {
        bib.title = matches[0].title;
      }
    }
  }
}

/* =====================================================================
   Sidebar: Live Metrics (running phase)
   ===================================================================== */
function _updateSidebarMetrics() {
  var els = {
    evidence: document.getElementById("ws-metric-evidence"),
    sources: document.getElementById("ws-metric-sources"),
    faith: document.getElementById("ws-metric-faith"),
    cost: document.getElementById("ws-metric-cost"),
    time: document.getElementById("ws-metric-time")
  };

  if (els.evidence) els.evidence.textContent = state.evidence || 0;
  if (els.sources) els.sources.textContent = state.sources.size || 0;
  if (els.faith) {
    var faithPct = state.faithfulness > 0 ? (state.faithfulness * 100).toFixed(0) + "%" : "--";
    els.faith.textContent = faithPct;
  }
  if (els.cost) els.cost.textContent = "$" + (state.cost || 0).toFixed(2);
  if (els.time && state.startTime) {
    var elapsed = Math.floor((Date.now() - state.startTime) / 1000);
    var mm = Math.floor(elapsed / 60);
    var ss = elapsed % 60;
    els.time.textContent = mm + "m " + String(ss).padStart(2, "0") + "s";
  }

  // F07: Update progress block metrics (center panel)
  var pmSources = document.getElementById("ws-pm-sources");
  var pmEvidence = document.getElementById("ws-pm-evidence");
  var pmFaith = document.getElementById("ws-pm-faith");
  if (pmSources) pmSources.textContent = state.sources.size || 0;
  if (pmEvidence) pmEvidence.textContent = state.evidence || 0;
  if (pmFaith) {
    pmFaith.textContent = state.faithfulness > 0
      ? (state.faithfulness * 100).toFixed(0) + "%" : "--";
  }
}

/* =====================================================================
   Sidebar: Memory Snowball
   ===================================================================== */
function _updateSidebarMemory() {
  var countEl = document.getElementById("ws-memory-count-val");
  if (!countEl) return;

  // Fetch memory stats from API
  fetch("/api/memory/stats")
  .then(function(r) { return r.ok ? r.json() : null; })
  .then(function(data) {
    if (!data) return;
    var count = data.total_items || data.count || 0;
    countEl.textContent = count > 0 ? count : "0";
    // Fetch actual items if count > 0 (stats endpoint returns counts only)
    if (count > 0) {
      fetch("/api/memory/items?limit=50")
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(itemData) {
        if (itemData && itemData.items) {
          _wsMemoryItems = itemData.items;
          _renderMemoryList("");
        }
      }).catch(function() {});
    }
  })
  .catch(function() {});
}

/* =====================================================================
   Sidebar: Scroll-Synced Citations
   This wires into scroll_sync.js — see that file for IntersectionObserver
   ===================================================================== */
function renderCitationSidebar(citeNumbers) {
  var container = document.getElementById("ws-citation-list");
  if (!container) return;

  // Guard: don't overwrite when Citations section is collapsed (scroll_sync
  // fires even while collapsed and would replace the full list with a partial set)
  var citeSec = document.getElementById("ws-section-citations");
  if (citeSec && citeSec.classList.contains("collapsed")) return;

  var html = "";
  citeNumbers.forEach(function(num) {
    var bib = state.bibliography[num - 1];
    if (!bib) return;

    var url = bib.url || bib.source_url || "";
    var title = bib.title || bib.domain || url || ("Source " + num);
    var domain = url ? extractDomain(url) : "";
    var faviconUrl = domain ? 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(domain) + '&sz=16' : '';
    var verified = bib.is_faithful !== false;

    var snippet = bib.snippet || bib.quote || bib.excerpt || "";
    if (snippet.length > 80) snippet = snippet.substring(0, 80) + "\u2026";

    html += '<div class="ws-cite-card" data-cite-num="' + num + '" ' +
      'onmouseenter="highlightCiteInReport(' + num + ', true); _wsPopoverTimer=setTimeout(function(){showCitePopoverCard(document.querySelector(\'.ws-cite-card[data-cite-num=&quot;' + num + '&quot;]\'),' + num + ')},200)" ' +
      'onmouseleave="highlightCiteInReport(' + num + ', false); hideCitePopoverCard()" ' +
      'onclick="if(typeof showCitationChain===\'function\')showCitationChain(event,' + num + ')">' +
      '<span class="ws-cite-card-num">' + num + '</span>';

    if (faviconUrl) {
      html += '<img class="ws-cite-card-favicon" src="' + esc(faviconUrl) + '" alt="" loading="lazy" onerror="this.style.display=\'none\'">';
    }

    html += '<div class="ws-cite-card-info">' +
      '<div class="ws-cite-card-title">' + esc(title) + '</div>' +
      '<div class="ws-cite-card-domain">' + esc(domain) + '</div>' +
      (snippet ? '<div class="ws-cite-card-snippet">' + esc(snippet) + '</div>' : '') +
    '</div>' +
    '<span class="ws-cite-card-badge ' + (verified ? 'verified' : 'unverified') + '">' + (verified ? "\u2713" : "\u26A0") + '</span>' +
    '</div>';
  });

  container.innerHTML = html || '<div style="color:var(--text-tertiary);font-size:var(--text-xs);padding:8px">Scroll the report to see citations</div>';
}

/* =====================================================================
   Right Panel: Collapsible Sections (Live / Citations / Memory)
   ===================================================================== */

/**
 * Set section visibility + collapse state based on workspace phase.
 *   idle    → Live hidden, Citations collapsed, Memory expanded (full)
 *   running → Live expanded (full), Citations collapsed, Memory collapsed
 *   report  → Live collapsed, Citations expanded (full), Memory collapsed
 */
function _updateRightPanelForPhase(phase) {
  if (phase === "idle") {
    _setRightSection("live", "hidden");
    _setRightSection("citations", "collapsed");
    _setRightSection("memory", "expanded");
  } else if (phase === "running") {
    _setRightSection("live", "expanded");
    _setRightSection("citations", "collapsed");
    _setRightSection("memory", "collapsed");
  } else if (phase === "report") {
    _setRightSection("live", "collapsed");
    _setRightSection("citations", "expanded");
    _setRightSection("memory", "collapsed");
  }
  _updateCitationsSectionContent();
}

/**
 * Toggle a section between expanded/collapsed (accordion).
 * Expanding a section collapses all other visible sections.
 * Re-expanding Citations refreshes the child div visibility so
 * the correct content (#ws-citation-list vs #ws-source-feed) shows.
 */
function _toggleRightSection(sectionId) {
  var el = document.getElementById("ws-section-" + sectionId);
  if (!el) return;
  var isCollapsed = el.classList.contains("collapsed");
  if (isCollapsed) {
    // Accordion: collapse all other visible sections, expand this one
    var allIds = ["live", "citations", "memory"];
    for (var i = 0; i < allIds.length; i++) {
      var other = document.getElementById("ws-section-" + allIds[i]);
      if (other && !other.classList.contains("hidden") && allIds[i] !== sectionId) {
        _setRightSection(allIds[i], "collapsed");
      }
    }
    _setRightSection(sectionId, "expanded");

    // Ensure the correct child div is visible for the current phase
    if (sectionId === "citations") {
      _updateCitationsSectionContent();
    }
    // Re-fetch memory items when Memory section is expanded
    if (sectionId === "memory") {
      _updateSidebarMemory();
    }
  } else {
    _setRightSection(sectionId, "collapsed");
  }
}

/**
 * Set a section to "expanded", "collapsed", or "hidden".
 */
function _setRightSection(sectionId, sectionState) {
  var el = document.getElementById("ws-section-" + sectionId);
  if (!el) return;
  el.classList.remove("expanded", "collapsed", "hidden");
  el.classList.add(sectionState);
}

/**
 * Show the right content inside the citations section body depending on phase.
 *   running → #ws-source-feed visible, #ws-citation-list hidden
 *   report  → #ws-citation-list visible, #ws-source-feed hidden
 *   idle    → both hidden
 */
function _updateCitationsSectionContent() {
  var srcFeed = document.getElementById("ws-source-feed");
  var citeList = document.getElementById("ws-citation-list");
  if (!srcFeed || !citeList) return;

  if (_wsPhase === "running") {
    srcFeed.style.display = "";
    citeList.style.display = "none";
    _renderSourceFeed();
  } else if (_wsPhase === "report") {
    srcFeed.style.display = "none";
    citeList.style.display = "";
    // Populate all citations if the list is empty (guard in renderCitationSidebar
    // blocks renders while collapsed, so first expand needs an explicit render)
    if (!citeList.children.length && state.bibliography && state.bibliography.length) {
      var allNums = [];
      for (var i = 1; i <= state.bibliography.length; i++) allNums.push(i);
      renderCitationSidebar(allNums);
    }
  } else {
    srcFeed.style.display = "none";
    citeList.style.display = "none";
  }
}

/**
 * Add item to sidebar task feed + existing center thread progress
 */
function _addTaskFeedItem(label, status, duration, eventTs) {
  // Feed the existing center-thread progress system
  addProgressTask(label, status);

  // Use original event timestamp if provided, else current time
  var ts = eventTs ? new Date(eventTs).getTime() : Date.now();

  if (status === "active") {
    // Update active item — replace any existing active item
    _wsTaskFeedItems = _wsTaskFeedItems.filter(function(t) { return t.status !== "active"; });
    _wsTaskFeedItems.push({ label: label, status: "active", duration: "", ts: ts });
  } else if (status === "done") {
    // Mark any matching active item as done
    var found = false;
    for (var i = _wsTaskFeedItems.length - 1; i >= 0; i--) {
      if (_wsTaskFeedItems[i].status === "active") {
        _wsTaskFeedItems[i].status = "done";
        _wsTaskFeedItems[i].duration = duration || "";
        if (eventTs) _wsTaskFeedItems[i].ts = ts;
        found = true;
        break;
      }
    }
    if (!found) {
      _wsTaskFeedItems.push({ label: label, status: "done", duration: duration || "", ts: ts });
    }
    // Trim old items
    if (_wsTaskFeedItems.length > _wsMaxTaskFeedItems) {
      _wsTaskFeedItems = _wsTaskFeedItems.slice(-_wsMaxTaskFeedItems);
    }
  }

  _renderTaskFeed();
}

/**
 * Render task feed into #ws-task-feed
 */
function _renderTaskFeed() {
  var container = document.getElementById("ws-task-feed");
  if (!container) return;

  // F10: Phase label map for divider headers
  var _phaseNames = {
    plan: "Planning",
    search: "Search",
    storm_interviews: "STORM Interviews",
    analyze: "Analysis",
    verify: "Verification",
    evaluate: "Evaluation",
    synthesize: "Synthesis",
    search_gaps: "Gap Search"
  };

  var html = "";
  _wsTaskFeedItems.forEach(function(t) {
    // F10: Render phase divider
    if (t.status === "phase_divider") {
      var phaseName = _phaseNames[t.phase] || t.phase.replace(/_/g, " ");
      html += '<div class="ws-task-phase-divider">' +
        '<span class="ws-task-phase-line"></span>' +
        '<span class="ws-task-phase-name">' + esc(phaseName) + '</span>' +
        '<span class="ws-task-phase-line"></span>' +
      '</div>';
      return;
    }

    var isActive = t.status === "active";
    var itemClass = "ws-task-item" + (isActive ? " active" : "");
    var iconClass = "ws-task-icon" + (isActive ? " spinning" : " done");
    var icon = isActive ? "\u25CF" : "\u2713";

    // F09: Relative timestamp (use endTime as reference for completed pipelines)
    var relTime = "";
    if (t.ts && state.startTime) {
      var refTime = state.pipelineComplete ? (state.endTime || Date.now()) : Date.now();
      var secsAgo = Math.max(0, Math.floor((refTime - t.ts) / 1000));
      if (secsAgo < 5) relTime = "now";
      else if (secsAgo < 60) relTime = secsAgo + "s ago";
      else relTime = Math.floor(secsAgo / 60) + "m ago";
    }

    html += '<div class="' + itemClass + '">';
    html += '<span class="' + iconClass + '">' + icon + '</span>';
    html += '<span class="ws-task-label">' + esc(t.label) + '</span>';
    if (t.duration) {
      html += '<span class="ws-task-duration">' + esc(t.duration) + '</span>';
    }
    if (relTime) {
      html += '<span class="ws-task-time">' + relTime + '</span>';
    }
    html += '</div>';
  });
  container.innerHTML = html;

  // Auto-scroll to bottom
  container.scrollTop = container.scrollHeight;
}

/**
 * Add discovered source (dedup by domain, prepend)
 */
function _addDiscoveredSource(ev) {
  var url = ev.url || "";
  if (!url) return;

  var domain = "";
  try { domain = new URL(url).hostname.replace("www.", ""); } catch(e) { return; }

  // Dedup by URL
  for (var i = 0; i < _wsDiscoveredSources.length; i++) {
    if (_wsDiscoveredSources[i].url === url) return;
  }

  _wsDiscoveredSources.unshift({
    url: url,
    domain: domain,
    title: ev.title || domain,
    status: ev.status || "discovered",
    ts: Date.now()
  });

  // Update section badge count
  _updateCitationsCount();
  // Render if citations section is expanded
  var citeSec = document.getElementById("ws-section-citations");
  if (citeSec && citeSec.classList.contains("expanded")) _renderSourceFeed();

  // F06: Update center panel source discovery list
  _renderCenterSourceDiscovery();
}

/**
 * F06: Render discovered sources into center panel source discovery card.
 * This fills the empty space below the progress block during running phase.
 */
function _renderCenterSourceDiscovery() {
  var list = document.getElementById("ws-source-discovery-list");
  var countEl = document.getElementById("ws-source-discovery-count");
  if (!list) return;

  if (countEl) countEl.textContent = _wsDiscoveredSources.length;

  if (_wsDiscoveredSources.length === 0) {
    list.innerHTML = '<div class="ws-sd-empty">Sources will appear here as they are discovered...</div>';
    return;
  }

  // Show up to 20 most recent sources
  var maxShow = 20;
  var sources = _wsDiscoveredSources.slice(0, maxShow);
  var html = "";
  sources.forEach(function(src) {
    var faviconUrl = "https://www.google.com/s2/favicons?domain=" +
      encodeURIComponent(src.domain) + "&sz=16";
    html += '<div class="ws-sd-item">' +
      '<img class="ws-sd-favicon" src="' + esc(faviconUrl) + '" width="14" height="14" alt="">' +
      '<span class="ws-sd-domain">' + esc(src.domain) + '</span>' +
      '<span class="ws-sd-title">' + esc(truncStr(src.title, 60)) + '</span>' +
    '</div>';
  });
  if (_wsDiscoveredSources.length > maxShow) {
    html += '<div class="ws-sd-more">+ ' +
      (_wsDiscoveredSources.length - maxShow) + ' more sources</div>';
  }
  list.innerHTML = html;
}

/**
 * Update the Citations section header badge count.
 */
function _updateCitationsCount() {
  var countEl = document.getElementById("ws-citations-count");
  if (!countEl) return;
  var count = _wsPhase === "report"
    ? (state.bibliography ? state.bibliography.length : 0)
    : _wsDiscoveredSources.length;
  countEl.textContent = count > 0 ? count : "";
}

/**
 * Render live source discovery cards into #ws-source-feed
 */
function _renderSourceFeed() {
  var container = document.getElementById("ws-source-feed");
  if (!container) return;

  if (_wsDiscoveredSources.length === 0) {
    container.innerHTML = '<div style="color:var(--text-tertiary);font-size:var(--text-xs);padding:8px">Sources will appear here as they are discovered...</div>';
    return;
  }

  var html = "";
  _wsDiscoveredSources.forEach(function(src, idx) {
    var faviconUrl = 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(src.domain) + '&sz=16';
    html += '<div class="ws-source-item" data-src-idx="' + idx + '" ' +
      'onmouseenter="_showSourcePreview(this,' + idx + ')" ' +
      'onmouseleave="hideCitePopoverCard()" ' +
      'onclick="window.open(\'' + esc(src.url) + '\',\'_blank\')">';
    html += '<img class="ws-source-favicon" src="' + esc(faviconUrl) + '" alt="" loading="lazy" onerror="this.style.display=\'none\'">';
    html += '<div class="ws-source-info">';
    html += '<div class="ws-source-title">' + esc(src.title) + '</div>';
    html += '<div class="ws-source-domain">' + esc(src.domain) + '</div>';
    html += '</div>';
    html += '<span class="ws-source-badge verified">\u2713</span>';
    html += '</div>';
  });
  container.innerHTML = html;
}

/**
 * Animate running→report transition: brief run summary card, then switch tabs
 */
function _animateRunToReport() {
  var summaryEl = document.getElementById("ws-run-summary");
  if (!summaryEl) return;

  var evCount = state.evidence || 0;
  var srcCount = state.sources ? state.sources.size : 0;
  var faithPct = state.faithfulness > 0 ? (state.faithfulness * 100).toFixed(0) + "%" : "--";
  var costStr = "$" + (state.cost || 0).toFixed(2);

  summaryEl.innerHTML =
    '<div class="ws-run-summary-title">Research complete</div>' +
    '<div class="ws-run-summary-grid">' +
      '<div class="ws-run-summary-stat">Evidence <span>' + evCount + '</span></div>' +
      '<div class="ws-run-summary-stat">Sources <span>' + srcCount + '</span></div>' +
      '<div class="ws-run-summary-stat">Faithful <span>' + faithPct + '</span></div>' +
      '<div class="ws-run-summary-stat">Cost <span>' + costStr + '</span></div>' +
    '</div>';
  summaryEl.style.display = "";

  // Auto-hide after 5 seconds
  setTimeout(function() {
    summaryEl.style.display = "none";
  }, 5000);
}

/**
 * Initialize memory section: search filter + initial render.
 */
function _initMemorySection() {
  var searchInput = document.getElementById("ws-memory-search");
  if (searchInput) {
    searchInput.addEventListener("input", function() {
      _renderMemoryList(this.value.trim().toLowerCase());
    });
  }
  _renderMemoryList("");
}

/**
 * Render memory items with optional search filter
 */
function _renderMemoryList(query) {
  var listEl = document.getElementById("ws-memory-list");
  if (!listEl) return;

  var items = _wsMemoryItems || [];
  if (query) {
    items = items.filter(function(item) {
      var text = (item.topic || item.content || item.key || "").toLowerCase();
      return text.indexOf(query) >= 0;
    });
  }

  if (items.length === 0) {
    listEl.innerHTML = '<div style="color:var(--text-tertiary);font-size:var(--text-xs);padding:8px">' +
      (query ? 'No matches for "' + esc(query) + '"' : 'No memory items yet') + '</div>';
    return;
  }

  var html = "";
  items.slice(0, 50).forEach(function(item) {
    var text = item.topic || item.content || item.key || "Memory item";
    html += '<div class="ws-memory-item">' + esc(text) + '</div>';
  });
  listEl.innerHTML = html;
}

/* =====================================================================
   Citation Popovers (D3) — Frosted glass popover on cite card hover
   ===================================================================== */
var _wsPopoverTimer = null;
var _wsActivePopover = null;

function showCitePopoverCard(cardEl, citeNum) {
  hideCitePopoverCard(); // Clear any existing

  var bib = state.bibliography[citeNum - 1];
  if (!bib) return;

  var url = bib.url || bib.source_url || "";
  var title = bib.title || bib.domain || url || ("Source " + citeNum);
  var domain = url ? extractDomain(url) : "";
  var verified = bib.is_faithful !== false;
  var snippet = bib.snippet || bib.text || bib.content_preview || "";
  var quote = bib.verification_quote || bib.quote || "";
  var faviconUrl = domain ? 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(domain) + '&sz=16' : '';
  var displayUrl = url.replace(/^https?:\/\//, '').substring(0, 50);
  var evidenceIds = bib.evidence_ids || [];

  var popover = document.createElement("div");
  popover.className = "ws-cite-popover";

  // 1. Chrome bar
  var html = '<div class="ws-popover-chrome">' +
        '<div class="ws-popover-url">';
  if (faviconUrl) {
    html += '<img class="ws-popover-url-favicon" src="' + esc(faviconUrl) + '" alt="" onerror="this.style.display=\'none\'">';
  }
  html += '<span class="ws-popover-url-text">' + esc(displayUrl) + '</span>' +
    '</div>' +
    '<span class="ws-popover-verified">' + (verified ? "\u2713" : "\u26A0") + '</span>' +
    '</div>';

  // 2. Iframe — Google-style mini-browser with highlighted citations
  if (url && evidenceIds.length > 0 && state.vectorId) {
    // Google-style: show loading, then async-fetch real article HTML + highlight quotes
    var iframeId = "ws-popover-iframe-" + citeNum;

    // Loading state while fetching
    var loadingSrcdoc = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
      'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:28px 24px;color:#1a1a1a;background:#fff}' +
      '.site-bar{display:flex;align-items:center;gap:6px;font-size:11px;color:#888;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid #eee}' +
      '.site-bar img{width:14px;height:14px;border-radius:2px}' +
      'h1{font-size:17px;font-weight:700;line-height:1.35;color:#111;margin-bottom:10px}' +
      '.note{font-size:12px;color:#999}' +
      '@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}' +
      '.loading-dots{animation:pulse 1.5s infinite}' +
      '</style></head><body>' +
      '<div class="site-bar">' +
        (faviconUrl ? '<img src="' + _escHtml(faviconUrl) + '" onerror="this.style.display=\'none\'">' : '') +
        _escHtml(domain) +
      '</div>' +
      '<h1>' + _escHtml(title) + '</h1>' +
      '<div class="note loading-dots">Loading source preview\u2026</div>' +
      '</body></html>';

    html += '<div class="ws-popover-iframe-wrap">' +
      '<iframe id="' + iframeId + '" class="ws-popover-iframe" srcdoc="' + loadingSrcdoc.replace(/"/g, '&quot;') + '" sandbox="allow-same-origin allow-scripts"></iframe>' +
    '</div>';

    // Async: fetch evidence previews, build real article with highlighted quotes
    {
      (function(eids, fId, srcDomain) {
        var vid = encodeURIComponent(state.vectorId);
        // Fetch all evidence previews to get quotes + readability_html
        var fetches = eids.slice(0, 5).map(function(eid) {
          return fetch("/api/research/source-preview/" + vid + "/" + encodeURIComponent(eid))
            .then(function(r) { return r.ok ? r.json() : null; })
            .catch(function() { return null; });
        });
        Promise.all(fetches).then(function(previews) {
          var iframe = document.getElementById(fId);
          if (!iframe) return;

          // Collect quotes and find best readability_html
          var quotes = [];
          var seen = {};
          var bestHtml = "";
          var bestLen = 0;
          for (var i = 0; i < previews.length; i++) {
            var p = previews[i];
            if (!p) continue;
            if (p.quote_text && !seen[p.quote_text]) {
              seen[p.quote_text] = true;
              quotes.push(p.quote_text);
            }
            if (p.readability_html && p.readability_html.length > bestLen) {
              bestLen = p.readability_html.length;
              bestHtml = p.readability_html;
            }
          }

          if (!bestHtml || bestLen < 200) {
            // No usable article HTML — fall back to quote-only view
            if (quotes.length > 0) {
              var fallbackBody = quotes.map(function(q) {
                return '<div style="margin:0 0 12px;padding:12px 16px;border-left:3px solid #eab308;background:#fefce8;font-size:14px;line-height:1.7;color:#333">' +
                  '<mark style="background:#fef08a;padding:1px 3px;border-bottom:2px solid #eab308">' + q.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</mark></div>';
              }).join('');
              iframe.srcdoc = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
                'body{font-family:Georgia,serif;padding:16px 20px;background:#fff}' +
                '.polaris-src-bar{position:sticky;top:0;z-index:99;background:#f8f9fa;border-bottom:1px solid #e5e7eb;padding:8px 12px;margin:-16px -20px 16px;display:flex;align-items:center;gap:6px;font:11px -apple-system,sans-serif;color:#70757a}' +
                '.polaris-src-bar .domain{font-weight:500;color:#202124}' +
                '.polaris-badge{background:#e8f5e9;color:#1b5e20;font-size:9px;padding:2px 6px;border-radius:3px;font-weight:600;margin-left:auto}' +
                '</style></head><body>' +
                '<div class="polaris-src-bar"><span class="domain">' + srcDomain + '</span><span class="polaris-badge">' + quotes.length + ' CITED</span></div>' +
                '<h3 style="font-size:16px;margin:12px 0 16px;color:#111">Cited excerpts from this source:</h3>' +
                fallbackBody + '</body></html>';
            }
            return;
          }

          // Extract body from readability_html
          var bodyMatch = bestHtml.match(/<body[^>]*>([\s\S]*)<\/body>/i);
          var articleBody = bodyMatch ? bodyMatch[1] : bestHtml;
          // Strip scripts (safety)
          articleBody = articleBody.replace(/<script[\s\S]*?<\/script>/gi, "");

          // Build the highlight + scroll script
          var quotesJson = JSON.stringify(quotes);
          var highlightScript = '(function(){' +
            'var quotes=' + quotesJson + ';' +
            'function walkText(node,q){' +
              'if(node.nodeType===3){' +
                'var idx=node.textContent.toLowerCase().indexOf(q.toLowerCase());' +
                'if(idx>=0){' +
                  'var span=document.createElement("mark");' +
                  'var after=node.splitText(idx);' +
                  'after.splitText(q.length);' +
                  'span.appendChild(after.cloneNode(true));' +
                  'after.parentNode.replaceChild(span,after);' +
                  'return span;' +
                '}' +
              '}else if(node.nodeType===1&&node.tagName!=="MARK"&&node.tagName!=="SCRIPT"&&node.tagName!=="STYLE"){' +
                'for(var c=node.firstChild;c;c=c.nextSibling){' +
                  'var found=walkText(c,q);' +
                  'if(found)return found;' +
                '}' +
              '}' +
              'return null;' +
            '}' +
            // Fuzzy match: try full quote, then first 60 chars, then first 40
            'var firstMark=null;' +
            'for(var i=0;i<quotes.length;i++){' +
              'var q=quotes[i];' +
              'var found=walkText(document.body,q);' +
              'if(!found&&q.length>60)found=walkText(document.body,q.substring(0,60));' +
              'if(!found&&q.length>40)found=walkText(document.body,q.substring(0,40));' +
              'if(found&&!firstMark)firstMark=found;' +
            '}' +
            'if(firstMark){' +
              'setTimeout(function(){firstMark.scrollIntoView({block:"center",behavior:"smooth"});},100);' +
            '}' +
          '})();';

          // Build clean page: real article with highlight
          var css = 'body{font-family:Georgia,"Times New Roman",serif;padding:16px 20px;color:#222;line-height:1.75;font-size:14px;background:#fff;max-width:100%;overflow-x:hidden}' +
            'img{max-width:100%;height:auto}' +
            'a{color:#1a73e8;text-decoration:none}' +
            'mark{background:#fef08a;color:#111;padding:2px 0;border-bottom:2px solid #eab308;border-radius:1px}' +
            'nav,header,footer,.nav,.menu,.cookie,.sidebar,.ad,.social,.share,.related,.comments,.signup,.newsletter{display:none!important}' +
            'h1,h2,h3{margin:0.8em 0 0.4em;line-height:1.3}' +
            'p{margin:0 0 0.8em}' +
            'table{border-collapse:collapse;width:100%;margin:1em 0}td,th{border:1px solid #ddd;padding:6px 8px;font-size:13px}' +
            '.polaris-src-bar{position:sticky;top:0;z-index:99;background:#f8f9fa;border-bottom:1px solid #e5e7eb;padding:8px 12px;margin:-16px -20px 16px;display:flex;align-items:center;gap:6px;font:11px -apple-system,sans-serif;color:#70757a}' +
            '.polaris-src-bar img{width:14px;height:14px;border-radius:2px}' +
            '.polaris-src-bar .domain{font-weight:500;color:#202124}' +
            '.polaris-badge{background:#e8f5e9;color:#1b5e20;font-size:9px;padding:2px 6px;border-radius:3px;font-weight:600;letter-spacing:0.3px;margin-left:auto}';

          var favHtml = srcDomain ? '<img src="https://www.google.com/s2/favicons?domain=' + encodeURIComponent(srcDomain) + '&sz=16" onerror="this.style.display=\'none\'">' : '';
          var srcBar = '<div class="polaris-src-bar">' + favHtml +
            '<span class="domain">' + srcDomain + '</span>' +
            '<span class="polaris-badge">' + quotes.length + ' CITED</span></div>';

          iframe.srcdoc = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' + css +
            '</style></head><body>' + srcBar + articleBody +
            '<script>' + highlightScript + '<\/script></body></html>';
        });
      })(evidenceIds, iframeId, domain);
    }
  } else if (snippet || quote) {
    // Static fallback: render cached snippet/quote with inline highlight
    var bodyText = _escHtml(snippet || quote);
    if (quote) {
      var qEsc = _escHtml(quote);
      var idx = bodyText.indexOf(qEsc);
      if (idx >= 0) {
        bodyText = bodyText.substring(0, idx) +
          '<mark>' + qEsc + '</mark>' +
          bodyText.substring(idx + qEsc.length);
      } else {
        bodyText = '<mark>' + qEsc + '</mark><br><br>' + bodyText;
      }
    }

    var faviconTag = faviconUrl
      ? '<img src="' + _escHtml(faviconUrl) + '" style="width:14px;height:14px;border-radius:2px;vertical-align:middle;margin-right:6px" onerror="this.style.display=\'none\'">'
      : '';

    var srcdoc = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
      '*{box-sizing:border-box;margin:0;padding:0}' +
      'body{font-family:Georgia,"Times New Roman",serif;padding:20px 24px;color:#1a1a1a;line-height:1.8;font-size:15px;background:#fff}' +
      '.site-bar{display:flex;align-items:center;gap:4px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:11px;color:#888;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #eee}' +
      'h1{font-size:18px;font-weight:700;line-height:1.35;margin-bottom:14px;color:#111}' +
      'p{margin:0;color:#333}' +
      'mark{background:rgba(56,189,248,0.18);color:#111;border-radius:2px;padding:1px 3px;border-bottom:2px solid rgba(56,189,248,0.5)}' +
      '</style></head><body>' +
      '<div class="site-bar">' + faviconTag + _escHtml(domain) + '</div>' +
      '<h1>' + _escHtml(title) + '</h1>' +
      '<p>' + bodyText + '</p>' +
      '</body></html>';

    html += '<div class="ws-popover-iframe-wrap">' +
      '<iframe class="ws-popover-iframe" srcdoc="' + srcdoc.replace(/"/g, '&quot;') + '" sandbox="allow-same-origin"></iframe>' +
    '</div>';
  }

  // 3. Footer
  html += '<div class="ws-popover-footer">' +
    '<span class="ws-popover-title-sm">' + esc(title) + '</span>' +
    (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener" class="ws-popover-link">Open \u2192</a>' : '') +
  '</div>';

  popover.innerHTML = html;

  // Position: fixed to viewport, left of the right panel
  var panelRect = document.getElementById("ws-right").getBoundingClientRect();
  var cardRect = cardEl.getBoundingClientRect();
  popover.style.position = "fixed";
  popover.style.left = (panelRect.left - 480 - 8) + "px";
  var idealTop = cardRect.top - 60;
  var maxTop = window.innerHeight - 630;
  popover.style.top = Math.max(8, Math.min(idealTop, maxTop)) + "px";

  document.body.appendChild(popover);
  _wsActivePopover = popover;
}

/** HTML-escape helper that does not rely on DOM (safe for srcdoc embedding). */
function _escHtml(s) {
  if (!s) return "";
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

/**
 * Show a mini browser preview for a discovered source (running phase).
 * Uses srcdoc with a styled placeholder since we don't have cached content yet.
 */
function _showSourcePreview(cardEl, srcIdx) {
  hideCitePopoverCard();
  var src = _wsDiscoveredSources[srcIdx];
  if (!src) return;

  var faviconUrl = 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(src.domain) + '&sz=16';
  var displayUrl = src.url.replace(/^https?:\/\//, '').substring(0, 50);

  var popover = document.createElement("div");
  popover.className = "ws-cite-popover";

  // Build srcdoc preview (no live iframe — most sites block embedding)
  var srcdoc = '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
    '*{box-sizing:border-box;margin:0;padding:0}' +
    'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:28px 24px;color:#1a1a1a;background:#fff}' +
    '.site-bar{display:flex;align-items:center;gap:6px;font-size:11px;color:#888;margin-bottom:20px;padding-bottom:14px;border-bottom:1px solid #eee}' +
    '.site-bar img{width:14px;height:14px;border-radius:2px}' +
    'h1{font-size:17px;font-weight:700;line-height:1.35;margin-bottom:16px;color:#111}' +
    '.status{font-size:12px;color:#aaa;margin-top:12px}' +
    '</style></head><body>' +
    '<div class="site-bar">' +
      '<img src="' + _escHtml(faviconUrl) + '" onerror="this.style.display=\'none\'">' +
      _escHtml(src.domain) +
    '</div>' +
    '<h1>' + _escHtml(src.title || src.domain) + '</h1>' +
    '<div class="status">Content preview available after research completes</div>' +
    '</body></html>';

  var html = '<div class="ws-popover-chrome">' +
        '<div class="ws-popover-url">' +
      '<img class="ws-popover-url-favicon" src="' + esc(faviconUrl) + '" alt="" onerror="this.style.display=\'none\'">' +
      '<span class="ws-popover-url-text">' + esc(displayUrl) + '</span>' +
    '</div>' +
  '</div>' +
  '<div class="ws-popover-iframe-wrap">' +
    '<iframe class="ws-popover-iframe" srcdoc="' + srcdoc.replace(/"/g, '&quot;') + '" sandbox="allow-same-origin"></iframe>' +
  '</div>' +
  '<div class="ws-popover-footer">' +
    '<span class="ws-popover-title-sm">' + esc(src.title || src.domain) + '</span>' +
    '<a href="' + esc(src.url) + '" target="_blank" rel="noopener" class="ws-popover-link">Open \u2192</a>' +
  '</div>';

  popover.innerHTML = html;

  // Position
  var panelRect = document.getElementById("ws-right").getBoundingClientRect();
  var cardRect = cardEl.getBoundingClientRect();
  popover.style.position = "fixed";
  popover.style.left = (panelRect.left - 480 - 8) + "px";
  var idealTop = cardRect.top - 20;
  var maxTop = window.innerHeight - 500;
  popover.style.top = Math.max(8, Math.min(idealTop, maxTop)) + "px";

  document.body.appendChild(popover);
  _wsActivePopover = popover;
}

function hideCitePopoverCard() {
  if (_wsPopoverTimer) {
    clearTimeout(_wsPopoverTimer);
    _wsPopoverTimer = null;
  }
  if (_wsActivePopover) {
    _wsActivePopover.remove();
    _wsActivePopover = null;
  }
}

/* Citation highlighting: bi-directional */
function highlightCiteInReport(num, active) {
  var reportBlock = _wsCurrentReportEl;
  if (!reportBlock) return;

  var refs = reportBlock.querySelectorAll('.cite-ref[data-cite="' + num + '"]');
  refs.forEach(function(ref) {
    ref.classList.toggle("highlight", active);
  });
}

function highlightCiteInSidebar(num, active) {
  var card = document.querySelector('.ws-cite-card[data-cite-num="' + num + '"]');
  if (card) {
    card.classList.toggle("active", active);
    if (active) card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

/* =====================================================================
   Dynamic Island (D4) — task pill in header center
   ===================================================================== */
function _updateDynamicIsland(phase, statusText) {
  var island = document.getElementById("ws-dynamic-island");
  if (!island) return;

  if (phase === "running") {
    island.classList.add("active");
    island.classList.remove("completed");
    var textEl = document.getElementById("ws-island-text");
    if (textEl && statusText) textEl.textContent = statusText;
  } else if (phase === "report" || phase === "complete") {
    island.classList.remove("active");
    island.classList.add("completed");
    var textEl = document.getElementById("ws-island-text");
    if (textEl) textEl.textContent = "Research complete";
    var dd = document.getElementById("ws-island-dropdown");
    if (dd) dd.classList.remove("open");
  } else {
    island.classList.remove("active");
    island.classList.remove("completed");
    var dd = document.getElementById("ws-island-dropdown");
    if (dd) dd.classList.remove("open");
  }
}

function _toggleIslandTaskList() {
  var dd = document.getElementById("ws-island-dropdown");
  if (!dd) return;
  dd.classList.toggle("open");

  // Render completed tasks
  if (dd.classList.contains("open")) {
    var html = "";
    _wsProgressTasks.forEach(function(t) {
      html += '<div class="ws-island-task">' +
        '<span class="ws-island-task-icon">\u2713</span>' +
        '<span>' + esc(t.label) + '</span>' +
      '</div>';
    });
    dd.innerHTML = html || '<div style="color:var(--text-tertiary);font-size:var(--text-2xs);padding:4px">No tasks yet</div>';
  }
}

/* =====================================================================
   Breadcrumb (D4)
   ===================================================================== */
function _updateBreadcrumb(query) {
  var active = document.getElementById("ws-breadcrumb-active");
  if (!active) return;

  if (query) {
    active.textContent = query.length > 40 ? query.substring(0, 38) + "\u2026" : query;
    active.title = query;
  } else {
    active.textContent = "Research";
    active.title = "";
  }
}

/* =====================================================================
   Workspace Depth Selector (Dropdown)
   ===================================================================== */
function setWorkspaceDepth(depth) {
  _wsDepth = depth;
  // Update dropdown label
  var label = document.getElementById("ws-depth-label");
  if (label) {
    var names = { quick: "Quick", standard: "Standard", deep: "Deep" };
    label.textContent = names[depth] || "Standard";
  }
  // Update active option in menu
  document.querySelectorAll(".ws-depth-option").forEach(function(opt) {
    opt.classList.toggle("active", opt.dataset.depth === depth);
  });
  // Legacy: update old chips if any still exist
  document.querySelectorAll(".ws-depth-chip").forEach(function(chip) {
    chip.classList.toggle("active", chip.dataset.depth === depth);
  });
}

function toggleDepthMenu() {
  var menu = document.getElementById("ws-depth-menu");
  if (!menu) return;
  var isOpen = menu.classList.contains("open");
  menu.classList.toggle("open", !isOpen);

  // Close on outside click
  if (!isOpen) {
    setTimeout(function() {
      function closeHandler(e) {
        if (!e.target.closest(".ws-depth-dropdown")) {
          menu.classList.remove("open");
          document.removeEventListener("click", closeHandler);
        }
      }
      document.addEventListener("click", closeHandler);
    }, 0);
  }
}

function selectDepth(depth) {
  setWorkspaceDepth(depth);
  var menu = document.getElementById("ws-depth-menu");
  if (menu) menu.classList.remove("open");
}

/* =====================================================================
   Idle State: Example Chips
   ===================================================================== */
function useWorkspaceExample(text) {
  var textarea = document.getElementById("ws-chat-textarea");
  if (textarea) {
    textarea.value = text;
    textarea.focus();
    _autoResizeTextarea(textarea);
  }
}

/* =====================================================================
   Idle State: Source Briefing (NotebookLM-style)
   ===================================================================== */
var _briefCache = {};       // key: sorted doc_ids hash → { summary, questions }
var _briefPending = false;  // prevent duplicate inflight requests
var _briefPendingTs = 0;    // timestamp when pending started (staleness guard)

function generateSourceBrief() {
  // Guard: only trigger when idle
  if (_wsPhase !== "idle") {
    console.log("[brief] Skipped: phase=" + _wsPhase + " (not idle)");
    return;
  }

  var briefEl = document.getElementById("ws-idle-brief");
  var greetingEl = document.getElementById("ws-idle-greeting");
  var chipsEl = document.getElementById("ws-idle-chips");

  if (!briefEl || !greetingEl || !chipsEl) {
    console.log("[brief] Skipped: missing DOM elements", {brief: !!briefEl, greeting: !!greetingEl, chips: !!chipsEl});
    return;
  }

  // No sources → show original greeting + chips, hide brief
  var idleEl = document.getElementById("ws-idle");
  if (typeof _docPanelDocs === "undefined" || _docPanelDocs.length === 0) {
    briefEl.style.display = "none";
    greetingEl.style.display = "";
    chipsEl.style.display = "";
    if (idleEl) idleEl.classList.remove("has-brief");
    console.log("[brief] Skipped: no docs loaded");
    return;
  }

  // Sources exist → hide greeting + chips, show brief
  greetingEl.style.display = "none";
  chipsEl.style.display = "none";
  briefEl.style.display = "";
  if (idleEl) idleEl.classList.add("has-brief");

  // Compute cache key from sorted doc_ids
  var docIds = _docPanelDocs.map(function(d) { return d.doc_id || d.id || ""; });
  docIds.sort();
  var cacheKey = docIds.join("|");

  // Check frontend cache
  if (_briefCache[cacheKey]) {
    console.log("[brief] Cache hit for " + _docPanelDocs.length + " docs");
    _renderSourceBrief(_briefCache[cacheKey]);
    return;
  }

  // Avoid duplicate inflight requests — with staleness guard
  if (_briefPending) {
    // If pending for >90s, assume the previous request hung — allow retry
    if (_briefPendingTs && Date.now() - _briefPendingTs > 90000) {
      console.warn("[brief] Previous request timed out after 90s, allowing retry");
      _briefPending = false;
    } else {
      console.log("[brief] Skipped: request already in-flight (" + Math.round((Date.now() - _briefPendingTs)/1000) + "s ago)");
      return;
    }
  }
  _briefPending = true;
  _briefPendingTs = Date.now();

  // Show loading, hide content
  var loadingEl = document.getElementById("ws-idle-brief-loading");
  var contentEl = document.getElementById("ws-idle-brief-content");
  if (loadingEl) loadingEl.style.display = "flex";
  if (contentEl) contentEl.style.display = "none";

  // POST to backend with AbortController timeout
  console.log("[brief] Fetching brief for " + docIds.length + " docs:", docIds);
  var controller = new AbortController();
  var timeoutId = setTimeout(function() { controller.abort(); }, 90000);

  fetch("/api/documents/brief", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_ids: docIds }),
    signal: controller.signal
  })
  .then(function(r) { return r.ok ? r.json() : null; })
  .then(function(data) {
    clearTimeout(timeoutId);
    _briefPending = false;
    if (!data) {
      _renderSourceBrief({
        summary: "Your sources are ready. Enter a research question to begin.",
        questions: []
      });
      return;
    }
    _briefCache[cacheKey] = data;
    _renderSourceBrief(data);
  })
  .catch(function(err) {
    clearTimeout(timeoutId);
    _briefPending = false;
    console.warn("[brief] Fetch failed:", err.message || err);
    _renderSourceBrief({
      summary: "Your sources are ready. Enter a research question to begin.",
      questions: []
    });
  });
}

function _renderSourceBrief(data) {
  var summaryEl = document.getElementById("ws-idle-brief-summary");
  var questionsEl = document.getElementById("ws-idle-brief-questions");
  var loadingEl = document.getElementById("ws-idle-brief-loading");
  var contentEl = document.getElementById("ws-idle-brief-content");
  var sourceCountEl = document.getElementById("ws-idle-brief-source-count");
  var actionsEl = document.getElementById("ws-idle-brief-actions");

  // --- Source count ---
  if (sourceCountEl) {
    var count = data.source_count || 0;
    sourceCountEl.textContent = count === 1 ? "1 source" : count + " sources";
  }

  // --- Summary with bold rendering ---
  if (summaryEl) {
    var raw = data.summary || "";
    var safe = esc(raw);
    var rendered = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    summaryEl.innerHTML = rendered;
  }

  // --- Questions (plain text, no bold) ---
  if (questionsEl) {
    questionsEl.innerHTML = "";
    var questions = data.questions || [];
    questions.forEach(function(q) {
      var btn = document.createElement("button");
      btn.className = "ws-idle-brief-q";
      // Use textContent — no bold in questions, ever
      var cleanQ = q.replace(/\*\*/g, "");
      btn.textContent = cleanQ;
      btn.onclick = function() { useWorkspaceExample(cleanQ); };
      questionsEl.appendChild(btn);
    });
  }

  // --- Wire action buttons ---
  if (actionsEl) {
    var copyBtn = document.getElementById("ws-brief-copy");
    var thumbsUpBtn = document.getElementById("ws-brief-thumbsup");
    var thumbsDownBtn = document.getElementById("ws-brief-thumbsdown");

    if (copyBtn) {
      copyBtn.onclick = function() {
        var summary = (data.summary || "").replace(/\*\*/g, "");
        var qs = (data.questions || []).map(function(q) {
          return "- " + q.replace(/\*\*/g, "");
        }).join("\n");
        var text = summary + "\n\nSuggested questions:\n" + qs;

        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text);
        } else {
          // Fallback for HTTP (no clipboard API)
          var ta = document.createElement("textarea");
          ta.value = text;
          ta.style.position = "fixed";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
        }
        _showBriefToast("Copied to clipboard");
      };
    }

    if (thumbsUpBtn) {
      thumbsUpBtn.onclick = function() {
        thumbsUpBtn.classList.toggle("ws-brief-action-active");
        if (thumbsDownBtn) thumbsDownBtn.classList.remove("ws-brief-action-active");
        _showBriefToast("Thanks for the feedback!");
      };
    }

    if (thumbsDownBtn) {
      thumbsDownBtn.onclick = function() {
        thumbsDownBtn.classList.toggle("ws-brief-action-active");
        if (thumbsUpBtn) thumbsUpBtn.classList.remove("ws-brief-action-active");
        _showBriefToast("Thanks — we'll improve this");
      };
    }
  }

  if (loadingEl) loadingEl.style.display = "none";
  if (contentEl) contentEl.style.display = "";
}

function _showBriefToast(message) {
  // Remove existing toast if any
  var existing = document.querySelector(".ws-brief-toast");
  if (existing) existing.remove();

  var toast = document.createElement("div");
  toast.className = "ws-brief-toast";
  toast.textContent = message;
  toast.style.cssText = (
    "position:fixed;bottom:80px;left:50%;transform:translateX(-50%);"
    + "background:var(--bg-secondary,#1e1e2e);color:var(--text-primary,#fff);"
    + "padding:8px 16px;border-radius:8px;font-size:12px;z-index:9999;"
    + "border:1px solid rgba(255,255,255,0.1);opacity:0;transition:opacity 0.2s;"
  );
  document.body.appendChild(toast);
  // Trigger fade-in
  requestAnimationFrame(function() {
    toast.style.opacity = "1";
  });
  setTimeout(function() {
    toast.style.opacity = "0";
    setTimeout(function() { toast.remove(); }, 200);
  }, 2000);
}

/* =====================================================================
   Idle State: History
   ===================================================================== */
function loadWorkspaceHistory() {
  fetch("/api/research/history")
  .then(function(r) { return r.ok ? r.json() : null; })
  .then(function(data) {
    if (!data || !data.history) return;
    var list = document.getElementById("ws-idle-history-list");
    var rightList = document.getElementById("ws-session-history-list");
    if (!list && !rightList) return;

    // Deduplicate by query text, keeping the most recent occurrence
    var seen = {};
    var unique = data.history.filter(function(h) {
      var key = (h.query || "").trim().toLowerCase();
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    });

    var html = "";
    unique.slice(0, 8).forEach(function(h) {
      html += '<div class="ws-idle-history-item" onclick="useWorkspaceExample(\'' + esc(h.query || "").replace(/'/g, "\\'") + '\')">' +
        '<span class="ws-idle-history-query">' + esc(h.query || "Untitled") + '</span>' +
        '<span class="ws-idle-history-date">' + (h.date || "") + '</span>' +
      '</div>';
    });

    if (list) list.innerHTML = html;
    if (rightList) rightList.innerHTML = html;
  })
  .catch(function() {});
}

/* =====================================================================
   Textarea Auto-Resize
   ===================================================================== */
function _autoResizeTextarea(el) {
  el.style.height = "44px";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

/* =====================================================================
   Mobile Inline Citations
   ===================================================================== */
function toggleInlineCitation(event, num) {
  event.stopPropagation();
  // Only on mobile
  if (window.innerWidth > 768) return;

  var citeRef = event.target.closest(".cite-ref");
  if (!citeRef) return;

  // Close existing expanded card
  if (_wsMobileExpandedCite !== null) {
    var existing = document.querySelector('.ws-inline-cite-card[data-cite="' + _wsMobileExpandedCite + '"]');
    if (existing) existing.remove();
    if (_wsMobileExpandedCite === num) {
      _wsMobileExpandedCite = null;
      return;
    }
  }

  var bib = state.bibliography[num - 1];
  if (!bib) return;

  var url = bib.url || bib.source_url || "";
  var title = bib.title || bib.domain || url || ("Source " + num);
  var domain = url ? extractDomain(url) : "";
  var verified = bib.is_faithful !== false;

  var card = document.createElement("div");
  card.className = "ws-inline-cite-card";
  card.setAttribute("data-cite", num);
  card.innerHTML =
    '<div class="ws-inline-cite-card-header">' +
      '<span>[' + num + ']</span> ' +
      '<span class="ws-inline-cite-card-title">' + esc(title) + '</span>' +
    '</div>' +
    '<div class="ws-inline-cite-card-meta">' + esc(domain) + ' ' + (verified ? "\u2713 Verified" : "\u26A0 Unverified") + '</div>' +
    '<div class="ws-inline-cite-card-actions">' +
      (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener">View Source</a>' : '') +
      '<button onclick="if(typeof showCitationChain===\'function\')showCitationChain(' + num + ')">Full Chain</button>' +
    '</div>';

  // Insert after the paragraph containing this citation
  var para = citeRef.closest("p") || citeRef.parentElement;
  if (para && para.parentElement) {
    para.parentElement.insertBefore(card, para.nextSibling);
  }

  _wsMobileExpandedCite = num;
}

/* =====================================================================
   Initialization
   ===================================================================== */
function initWorkspace() {
  var ws = document.getElementById("workspace");
  if (!ws) return;

  // Textarea auto-resize + keyboard submit
  var textarea = document.getElementById("ws-chat-textarea");
  if (textarea) {
    textarea.addEventListener("input", function() { _autoResizeTextarea(this); });
    textarea.addEventListener("keydown", function(e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleWorkspaceChatSubmit();
      }
    });
  }

  // Submit button
  var submitBtn = document.getElementById("ws-chat-submit-btn");
  if (submitBtn) {
    submitBtn.addEventListener("click", function() { handleWorkspaceChatSubmit(); });
  }

  // Depth dropdown (options wired via onclick in HTML)

  // Left panel drawer toggle (mobile)
  var drawerToggle = document.getElementById("ws-drawer-toggle");
  if (drawerToggle) {
    drawerToggle.addEventListener("click", function() {
      var left = document.getElementById("ws-left");
      if (left) left.classList.toggle("drawer-open");
    });
  }

  var drawerOverlay = document.getElementById("ws-drawer-overlay");
  if (drawerOverlay) {
    drawerOverlay.addEventListener("click", function() {
      var left = document.getElementById("ws-left");
      if (left) left.classList.remove("drawer-open");
    });
  }

  // Load history
  loadWorkspaceHistory();

  // Initialize memory section and fetch memory stats
  _initMemorySection();
  _updateSidebarMemory();

  // Set initial phase
  setWorkspacePhase("idle");

  // Wire citation hover from report body to sidebar
  document.addEventListener("mouseover", function(e) {
    var citeRef = e.target.closest(".ws-report-body .cite-ref");
    if (citeRef) {
      var num = parseInt(citeRef.getAttribute("data-cite"));
      if (num) highlightCiteInSidebar(num, true);
    }
  });
  document.addEventListener("mouseout", function(e) {
    var citeRef = e.target.closest(".ws-report-body .cite-ref");
    if (citeRef) {
      var num = parseInt(citeRef.getAttribute("data-cite"));
      if (num) highlightCiteInSidebar(num, false);
    }
  });

  // Mobile: override cite-ref clicks
  document.addEventListener("click", function(e) {
    if (window.innerWidth > 768) return;
    var citeRef = e.target.closest(".ws-report-body .cite-ref");
    if (citeRef) {
      e.preventDefault();
      e.stopPropagation();
      var num = parseInt(citeRef.getAttribute("data-cite"));
      if (num) toggleInlineCitation(e, num);
    }
  }, true);
}

/* =====================================================================
   Header Dropdowns — Mode, Depth, Account (user-mode clean header)
   ===================================================================== */

/**
 * Toggle a specific header dropdown menu by ID.
 * Closes all other open header dropdowns first.
 */
function toggleHeaderDropdown(menuId) {
  var menu = document.getElementById(menuId);
  if (!menu) return;
  var wasOpen = menu.classList.contains("open");
  closeAllHeaderDropdowns();
  if (!wasOpen) {
    menu.classList.add("open");
  }
}

/** Close all header dropdown menus */
function closeAllHeaderDropdowns() {
  var menus = document.querySelectorAll(".ws-header-dd-menu");
  for (var i = 0; i < menus.length; i++) {
    menus[i].classList.remove("open");
  }
}

/**
 * Mode dropdown: switch between Research (user) and Console (operator).
 * Delegates to existing setViewMode() in advanced_tabs.js.
 */
function selectHeaderMode(mode) {
  if (typeof setViewMode === "function") {
    setViewMode(mode);
  }
  // Update label
  var label = document.getElementById("ws-mode-label");
  if (label) {
    label.textContent = mode === "user" ? "Research" : "Console";
  }
  // Update active state in menu
  var menu = document.getElementById("ws-mode-menu");
  if (menu) {
    var btns = menu.querySelectorAll("button");
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle("active", btns[i].getAttribute("data-mode") === mode);
    }
  }
  closeAllHeaderDropdowns();
}

/**
 * Depth dropdown: switch research depth.
 * Delegates to existing setWorkspaceDepth().
 */
function selectHeaderDepth(depth) {
  setWorkspaceDepth(depth);
  var labels = { quick: "Fast", standard: "Standard", deep: "Extended" };
  var label = document.getElementById("ws-header-depth-label");
  if (label) {
    label.textContent = labels[depth] || "Standard";
  }
  // Update active state in menu
  var menu = document.getElementById("ws-header-depth-menu");
  if (menu) {
    var btns = menu.querySelectorAll("button");
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle("active", btns[i].getAttribute("data-depth") === depth);
    }
  }
  closeAllHeaderDropdowns();
}

/** Account menu auth handler */
function handleHeaderAuth() {
  if (typeof state !== "undefined" && state.authenticated) {
    if (typeof handleLogout === "function") handleLogout();
  } else {
    if (typeof toggleAuthModal === "function") toggleAuthModal();
  }
  closeAllHeaderDropdowns();
}

/** Settings panel placeholder */
function toggleSettingsPanel() {
  if (typeof showToast === "function") {
    showToast("Settings coming soon", "info");
  }
}

/** Update avatar initial and account info based on auth state */
function updateHeaderAccount() {
  var avatar = document.getElementById("ws-header-avatar");
  var info = document.getElementById("ws-account-info");
  var authBtn = document.getElementById("ws-account-auth-btn");
  if (!avatar || !info || !authBtn) return;

  if (typeof state !== "undefined" && state.authenticated && state.user) {
    var initial = (state.user.username || "U")[0].toUpperCase();
    avatar.textContent = initial;
    info.textContent = state.user.username;
    authBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg> Sign out';
  } else {
    avatar.textContent = "P";
    info.textContent = "Not signed in";
    authBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg> Sign in';
  }
}

/* Close header dropdowns on outside click */
document.addEventListener("click", function(e) {
  if (!e.target.closest(".ws-header-dropdown")) {
    closeAllHeaderDropdowns();
  }
});

/* Initialize on DOM ready */
document.addEventListener("DOMContentLoaded", function() {
  initWorkspace();
  updateHeaderAccount();
});
