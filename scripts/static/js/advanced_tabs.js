/* =====================================================================
   advanced_tabs.js -- Advanced View (Queries, Sources, STORM, Trace,
   Cost), Settings Listeners, View Mode, Research Submission, User
   Progress, Auth UI, Campaigns, Bookmarks, Initialization
   POLARIS Live Dashboard

   NOTE: This file loads LAST. It depends on core.js (state, utilities),
   event_processor.js (processEvent, updateMetrics), research_view.js
   (renderView), sse_connection.js (loadSnapshot, connectSSE,
   _currentViewMode), and operator_console.js (updateOperatorPanels).
   ===================================================================== */

/* FMT-2: Locale-safe number formatting */
var _numFmt = new Intl.NumberFormat(undefined);
var _compactFmt = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });

/* =====================================================================
   Advanced View -- Queries sub-tab
   ===================================================================== */
function renderAdvancedTab(tab) {
  tab = tab || state.activeAdvTab;
  if (tab === "queries") renderAdvQueries();
  else if (tab === "sources") renderAdvSources();
  else if (tab === "storm") renderAdvStorm();
  else if (tab === "trace") renderAdvTrace();
  else if (tab === "cost") renderAdvCost();
}

/* --- Queries sub-tab --- */
function renderAdvQueries() {
  var el = document.getElementById("adv-queries");
  var html = '';

  // Empty state (distinct from Sources tab — early return to avoid rendering empty data cards)
  if (!state.queries.length && !state.searchStrategy && !state.keyConcepts.length) {
    html += '<div style="min-height:400px;background:linear-gradient(135deg,rgba(59,130,246,0.12) 0%,rgba(59,130,246,0.03) 100%);border-radius:var(--radius-lg);padding:var(--xxl);display:flex;flex-direction:column;align-items:center;justify-content:center;border:2px dashed rgba(59,130,246,0.25);">' +
      '<div style="font-size:4rem;margin-bottom:var(--lg);opacity:0.5;">&#128269;</div>' +
      '<h3 style="margin-bottom:var(--sm);color:var(--text-secondary);">Query Explorer</h3>' +
      '<p style="color:var(--text-tertiary);max-width:40ch;text-align:center;">No queries executed yet. Search queries, engine breakdowns, and agentic rounds will appear here as the research pipeline runs.</p></div>';
    el.innerHTML = html;
    return;
  }

  // Research plan / strategy
  if (state.searchStrategy) {
    html += '<div class="adv-card"><h4>Search Strategy</h4><p>' + esc(state.searchStrategy) + '</p></div>';
  }

  // Key concepts
  if (state.keyConcepts.length) {
    html += '<div class="adv-card"><h4>Key Concepts</h4><div class="concept-chips">';
    state.keyConcepts.forEach(function(c) {
      html += '<span class="concept-chip">' + esc(typeof c === 'string' ? c : c.name || c.concept || JSON.stringify(c)) + '</span>';
    });
    html += '</div></div>';
  }

  // Engine breakdown
  var engines = state.engineCounts;
  var engKeys = Object.keys(engines);
  if (engKeys.length) {
    html += '<div class="adv-card"><h4>Search Engines</h4><div class="engine-bars">';
    var maxEng = Math.max.apply(null, engKeys.map(function(k) { return engines[k]; }));
    engKeys.sort(function(a, b) { return engines[b] - engines[a]; });
    engKeys.forEach(function(k) {
      var pct = maxEng > 0 ? (engines[k] / maxEng * 100) : 0;
      html += '<div class="engine-row"><span class="engine-name">' + esc(k) + '</span>' +
        '<div class="engine-bar"><div class="engine-bar-fill" style="width:' + pct + '%"></div></div>' +
        '<span class="engine-count">' + engines[k] + '</span></div>';
    });
    html += '</div></div>';
  }

  // Agentic rounds
  if (state.agenticRounds.length) {
    html += '<div class="adv-card"><h4>Agentic Rounds (' + state.agenticRounds.length + ')</h4>';
    state.agenticRounds.forEach(function(r, i) {
      html += '<div class="agentic-round"><strong>Round ' + (i + 1) + ':</strong> ' +
        esc(r.reason || r.focus || "") +
        (r.query_count ? ' (' + r.query_count + ' queries)' : '') + '</div>';
    });
    html += '</div>';
  }

  // Planned queries
  if (state.planQueries.length) {
    html += '<div class="adv-card"><h4>Planned Queries (' + state.planQueries.length + ')</h4>';
    html += '<div class="query-list" tabindex="0" role="region" aria-label="Planned queries">';
    state.planQueries.forEach(function(q) {
      html += '<div class="query-item">' + esc(typeof q === 'string' ? q : q.query || JSON.stringify(q)) + '</div>';
    });
    html += '</div></div>';
  }

  // Query log
  html += '<div class="adv-card"><h4>All Queries (' + state.queries.length + ')</h4>';
  html += '<div class="query-log" tabindex="0" role="log" aria-label="Query log">';
  var displayQueries = state.queries.slice(-100);
  displayQueries.forEach(function(q) {
    var eng = q.engine || "web";
    html += '<div class="query-log-item"><span class="q-engine tag-' + eng + '">' + esc(eng) + '</span><span class="q-text">' + esc(q.query || q.text || q) + '</span>' +
      (q.results !== undefined ? '<span class="q-results">' + q.results + ' results</span>' : '') + '</div>';
  });
  html += '</div></div>';

  el.innerHTML = html;
}

/* --- Sources sub-tab --- */
function renderAdvSources() {
  var el = document.getElementById("adv-sources");
  var html = '';

  // Empty state (distinct from Queries tab — early return to avoid rendering empty data cards)
  if (!state.sources.size && !state.fetchSuccess && !state.fetchFailed && !state.missingPerspectives.length) {
    html += '<div style="min-height:400px;background:linear-gradient(135deg,rgba(16,185,129,0.12) 0%,rgba(16,185,129,0.03) 100%);border-radius:var(--radius-lg);padding:var(--xxl);display:flex;flex-direction:column;align-items:center;justify-content:center;border:2px dashed rgba(16,185,129,0.25);">' +
      '<div style="font-size:4rem;margin-bottom:var(--lg);opacity:0.5;">&#127760;</div>' +
      '<h3 style="margin-bottom:var(--sm);color:var(--text-secondary);">Source Analysis</h3>' +
      '<p style="color:var(--text-tertiary);max-width:40ch;text-align:center;">No sources fetched yet. Domain analysis, fetch statistics, and perspective coverage will appear here during research.</p></div>';
    el.innerHTML = html;
    return;
  }

  // Fetch summary
  html += '<div class="adv-card"><h4>Fetch Pipeline</h4><div class="fetch-summary">' +
    '<div class="fetch-stat"><span class="fetch-num success">' + state.fetchSuccess + '</span><span>Success</span></div>' +
    '<div class="fetch-stat"><span class="fetch-num snippet">' + state.fetchSnippet + '</span><span>Snippet</span></div>' +
    '<div class="fetch-stat"><span class="fetch-num failed">' + state.fetchFailed + '</span><span>Failed</span></div>' +
    '</div></div>';

  // Missing perspectives (MI-10: warning-first, moved above domains)
  if (state.missingPerspectives.length) {
    html += '<div class="adv-card adv-card-warning"><h4>Missing Perspectives</h4><div class="missing-persp">';
    state.missingPerspectives.forEach(function(p) {
      html += '<span class="missing-chip">' + esc(p) + '</span>';
    });
    html += '</div></div>';
  }

  // Domain bars
  var domainArr = Array.from(state.sources);
  if (domainArr.length) {
    html += '<div class="adv-card"><h4>Source Domains (' + domainArr.length + ')</h4><div class="domain-list">';
    domainArr.slice(0, 50).forEach(function(d) {
      html += '<div class="domain-item"><span class="domain-badge"></span>' + esc(d) + '</div>';
    });
    if (domainArr.length > 50) html += '<div class="domain-more">+' + (domainArr.length - 50) + ' more</div>';
    html += '</div></div>';
  }

  // Perspective distribution
  var persKeys = Object.keys(state.perspectiveDist);
  if (persKeys.length) {
    html += '<div class="adv-card"><h4>Perspective Distribution</h4><div class="perspective-bars">';
    var maxPers = Math.max.apply(null, persKeys.map(function(k) { return state.perspectiveDist[k]; }));
    persKeys.sort(function(a, b) { return state.perspectiveDist[b] - state.perspectiveDist[a]; });
    persKeys.forEach(function(k) {
      var pct = maxPers > 0 ? (state.perspectiveDist[k] / maxPers * 100) : 0;
      html += '<div class="pers-row"><span class="pers-name">' + esc(k) + '</span>' +
        '<div class="pers-bar"><div class="pers-bar-fill" style="width:' + pct + '%"></div></div>' +
        '<span class="pers-count">' + state.perspectiveDist[k] + '</span></div>';
    });
    html += '</div></div>';
  }

  el.innerHTML = html;
}

/* --- STORM sub-tab (enhanced persona cards) --- */
function renderAdvStorm() {
  var el = document.getElementById("adv-storm");
  var html = '';

  // Persona cards
  var personaMap = {};
  state.stormChats.forEach(function(chat) {
    var name = chat.persona || "Unknown";
    if (!personaMap[name]) personaMap[name] = { name: name, expertise: chat.expertise || "", questionFocus: chat.questionFocus || "", interviews: 0, findings: 0, failed: false };
    personaMap[name].interviews++;
    personaMap[name].findings += (chat.findings ? chat.findings.length : 0);
    if (!personaMap[name].expertise && chat.expertise) personaMap[name].expertise = chat.expertise;
    if (!personaMap[name].questionFocus && chat.questionFocus) personaMap[name].questionFocus = chat.questionFocus;
  });

  var personas = Object.values(personaMap);
  if (personas.length) {
    html += '<div class="storm-personas"><h4>STORM Personas (' + personas.length + ')</h4><div class="persona-grid">';
    personas.forEach(function(p) {
      var initial = p.name.charAt(0).toUpperCase();
      var colors = ["#20C8D8", "#FBBF24", "#F43F5E", "#10B981", "#A78BFA", "#F97316", "#3B82F6", "#EC4899"];
      var color = colors[p.name.charCodeAt(0) % colors.length];
      html += '<div class="persona-card">' +
        '<div class="persona-header">' +
        '<div class="persona-avatar" style="background:' + color + '">' + esc(initial) + '</div>' +
        '<div class="persona-info">' +
        '<div class="persona-name">' + esc(p.name) + '</div>' +
        (p.expertise ? '<div class="persona-expertise">' + esc(p.expertise) + '</div>' : '') +
        '</div>' +
        '</div>' +
        (p.questionFocus ? '<div class="persona-focus"><span class="focus-label">Research Focus:</span> ' + esc(p.questionFocus) + '</div>' : '') +
        '<div class="persona-stats">' +
        '<span class="ps-item">' + p.interviews + ' interviews</span>' +
        '<span class="ps-item">' + p.findings + ' findings</span>' +
        '</div>' +
        (p.failed ? '<div class="persona-failed">FAILED</div>' : '') +
        '</div>';
    });
    html += '</div></div>';
  } else {
    html += '<div class="storm-empty">STORM personas will appear after interviews begin.</div>';
  }

  // Chat transcript
  if (state.stormChats.length) {
    html += '<div class="storm-transcript"><h4>Interview Transcript (' + state.stormChats.length + ' exchanges)</h4>';
    state.stormChats.slice(-50).forEach(function(chat) {
      var initial = (chat.persona || "?").charAt(0).toUpperCase();
      html += '<div class="storm-exchange">' +
        '<div class="storm-q"><span class="storm-avatar-sm">' + esc(initial) + '</span>' +
        '<span class="storm-persona-name">' + esc(chat.persona || "?") + '</span>' +
        (chat.round ? '<span class="storm-round">R' + chat.round + '</span>' : '') +
        '</div>';
      if (chat.question) html += '<div class="storm-question">' + esc(truncStr(chat.question, 500)) + '</div>';
      if (chat.answer) html += '<div class="storm-answer">' + esc(truncStr(chat.answer, 500)) + '</div>';
      if (chat.findings && chat.findings.length) {
        html += '<div class="storm-findings">';
        chat.findings.forEach(function(f) {
          html += '<div class="finding-chip">' + esc(truncStr(typeof f === 'string' ? f : f.finding || JSON.stringify(f), 200)) + '</div>';
        });
        html += '</div>';
      }
      html += '</div>';
    });
    if (state.stormChats.length > 50) html += '<div class="storm-more">Showing last 50 of ' + state.stormChats.length + ' exchanges</div>';
    html += '</div>';
  }

  el.innerHTML = html;
}

/* --- Trace sub-tab --- */
function renderAdvTrace() {
  var el = document.getElementById("adv-trace");
  var html = '';

  // Filter chips — always include standard types so UI is stable before events load
  var standardTypes = ["all", "node", "llm_call", "evidence", "reasoning_capture", "llm_detail", "storm_transcript"];
  var filterTypes = standardTypes.slice();
  var typeCounts = {};
  state.traceEvents.forEach(function(ev) {
    var t = ev.type || ev.event || "unknown";
    if (!typeCounts[t]) { typeCounts[t] = 0; if (filterTypes.indexOf(t) === -1) filterTypes.push(t); }
    typeCounts[t]++;
  });

  html += '<div class="filter-chips" id="trace-filters">';
  filterTypes.slice(0, 20).forEach(function(ft) {
    var active = state.traceFilter === ft ? " active" : "";
    var label = ft === "all" ? "All (" + state.traceEvents.length + ")" : ft + " (" + (typeCounts[ft] || 0) + ")";
    html += '<button class="filter-chip' + active + '" data-ttype="' + esc(ft) + '" onclick="setTraceFilter(\'' + esc(ft) + '\')">' + esc(label) + '</button>';
  });
  html += '</div>';

  // Trace events
  var filtered = state.traceFilter === "all" ? state.traceEvents : state.traceEvents.filter(function(ev) {
    return (ev.type || ev.event || "unknown") === state.traceFilter;
  });
  var showing = filtered.slice(-200);

  var _timeFmt = new Intl.DateTimeFormat(undefined, { hour:'2-digit', minute:'2-digit', second:'2-digit', hour12: false });
  html += '<div class="trace-list">';
  showing.forEach(function(ev) {
    var evType = ev.type || ev.event || "unknown";
    var ts = ev.ts ? _timeFmt.format(new Date(ev.ts)) : "";
    var node = ev.node || "";
    html += '<details class="trace-card"><summary>' +
      '<span class="trace-ts">' + esc(ts) + '</span>' +
      '<span class="trace-type-badge" data-type="' + esc(evType) + '">' + esc(evType) + '</span>' +
      (node ? '<span class="trace-node">' + esc(node) + '</span>' : '') +
      '</summary>' +
      '<pre class="trace-body">' + esc(JSON.stringify(ev, null, 2).substring(0, 3000)) + '</pre>' +
      '</details>';
  });
  if (filtered.length > 200) {
    html += '<div class="trace-more">Showing last 200 of ' + filtered.length + ' events</div>';
  }
  html += '</div>';

  el.innerHTML = html;
}

function setTraceFilter(ft) {
  state.traceFilter = ft;
  renderAdvTrace();
}

/* --- Cost sub-tab --- */
function renderAdvCost() {
  var el = document.getElementById("adv-cost");
  var html = '';

  // LLM usage summary (MI-4: label ABOVE value, FMT-3: pending state)
  var costDisplay = (state.llmCallCount > 0) ? '$' + state.cost.toFixed(3) : '\u2014';
  html += '<div class="adv-card"><h4>LLM Usage Summary</h4><div class="cost-grid">' +
    '<div class="cost-item"><div class="cost-label">Total Calls</div><div class="cost-num">' + state.llmCallCount + '</div></div>' +
    '<div class="cost-item"><div class="cost-label">Input Tokens</div><div class="cost-num">' + formatTokens(state.llmInputTokens) + '</div></div>' +
    '<div class="cost-item"><div class="cost-label">Output Tokens</div><div class="cost-num">' + formatTokens(state.llmOutputTokens) + '</div></div>' +
    '<div class="cost-item"><div class="cost-label">Total Cost</div><div class="cost-num">' + costDisplay + '</div></div>' +
    '</div>';
  if (state.llmCallCount === 0) html += '<div class="cost-pending" style="text-align:center;font-size:var(--text-2xs);color:var(--text-tertiary);margin-top:var(--xs)">Cost pending provider rate lookup</div>';
  html += '</div>';

  // Model distribution
  var modelKeys = Object.keys(state.modelCounts);
  if (modelKeys.length) {
    var totalModelCalls = modelKeys.reduce(function(s, k) { return s + state.modelCounts[k]; }, 0);
    html += '<div class="adv-card"><h4>Model Distribution</h4><div class="model-bars">';
    modelKeys.sort(function(a, b) { return state.modelCounts[b] - state.modelCounts[a]; });
    modelKeys.forEach(function(m) {
      var pct = totalModelCalls > 0 ? (state.modelCounts[m] / totalModelCalls * 100) : 0;
      html += '<div class="model-row">' +
        '<span class="model-name">' + esc(m) + '</span>' +
        '<div class="model-bar"><div class="model-bar-fill" style="width:' + pct.toFixed(1) + '%"></div></div>' +
        '<span class="model-count">' + state.modelCounts[m] + ' (' + pct.toFixed(0) + '%)</span>' +
        '</div>';
    });
    html += '</div></div>';
  }

  // LLM call log (last 50)
  if (state.llmDetails.length) {
    html += '<div class="adv-card"><h4>Recent LLM Calls (last 50 of ' + state.llmDetails.length + ')</h4>';
    html += '<div class="llm-call-list">';
    state.llmDetails.slice(-50).reverse().forEach(function(d) {
      var callType = d.call_type || d.type || "?";
      var model = d.model || "?";
      var inTok = d.input_tokens || d.prompt_tokens || 0;
      var outTok = d.output_tokens || d.completion_tokens || 0;
      var dur = d.duration_s !== undefined ? d.duration_s.toFixed(1) + 's' : '';
      html += '<div class="llm-call-row">' +
        '<span class="llm-type">' + esc(callType) + '</span>' +
        '<span class="llm-model">' + esc(truncStr(model, 30)) + '</span>' +
        '<span class="llm-tokens"><span class="token-pill token-in">' + inTok + '</span><span class="token-arrow">\u25B8</span><span class="token-pill token-out">' + outTok + '</span></span>' +
        (dur ? '<span class="llm-dur">' + dur + '</span>' : '') +
        '</div>';
    });
    html += '</div></div>';
  }

  el.innerHTML = html;
}


/* =====================================================================
   Settings Listeners (DOMContentLoaded)
   ===================================================================== */
document.addEventListener("DOMContentLoaded", function() {
  // Auto-nav checkbox
  var autoNavEl = document.getElementById("chk-autotab");
  if (autoNavEl) {
    autoNavEl.checked = state.autoTab;
    autoNavEl.addEventListener("change", function() { state.autoTab = this.checked; });
  }

  // Graph mode segmented control
  document.querySelectorAll("#graph-mode-selector .seg-btn").forEach(function(btn) {
    btn.addEventListener("click", function() {
      document.querySelectorAll("#graph-mode-selector .seg-btn").forEach(function(b) { b.classList.remove("active"); });
      this.classList.add("active");
      state.graphMode = this.dataset.mode;
      if (state.activeView === "evidence") renderEvidenceView();
    });
  });

  // Tier filter
  var tierFilterEl = document.getElementById("graph-tier-filter");
  if (tierFilterEl) {
    tierFilterEl.addEventListener("change", function() {
      if (state.activeView === "evidence") renderEvidenceView();
    });
  }

  // Set view mode FIRST (purely visual, before any async hydration)
  var savedMode = localStorage.getItem("polaris_view_mode") || "user";
  setViewMode(savedMode, true);

  // Then start async hydration — these will correct workspace phase when data arrives
  checkResearchStatus();
  loadSnapshot();

  // Fetch memory status indicator (Sprint 1B)
  fetchMemoryStatus();

  // Initialize checkpoint timeline in operator view (A2)
  if (typeof initCheckpointTimeline === "function") {
    initCheckpointTimeline("checkpoint-timeline-container");
  }
});

/* =====================================================================
   Memory Status Indicator (Sprint 1B)
   ===================================================================== */
function fetchMemoryStatus() {
  var el = document.getElementById("memory-count");
  if (!el) return;
  fetch("/api/memory/stats")
    .then(function(res) {
      if (!res.ok) throw new Error("status " + res.status);
      return res.json();
    })
    .then(function(data) {
      var count = data.total_items || data.count || 0;
      if (count > 0) {
        el.textContent = count + " items";
        el.parentElement.title = "Long-term memory: " + count + " stored findings";
        el.parentElement.style.color = "var(--success)";
      } else {
        el.textContent = "Empty";
        el.parentElement.title = "Long-term memory is empty — run research to accumulate knowledge";
      }
    })
    .catch(function() {
      el.textContent = "Offline";
      el.parentElement.title = "Memory system unavailable";
      el.parentElement.style.opacity = "0.5";
    });
}

/* =====================================================================
   VIEW MODE -- User (Researcher) vs Operator toggle
   ===================================================================== */
var _currentViewMode = "user";

function setViewMode(mode, skipSave) {
  _currentViewMode = mode;
  document.body.classList.toggle("user-mode", mode === "user");

  // Update toggle buttons
  document.querySelectorAll(".view-mode-btn").forEach(function(btn) {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });

  // In user mode, hide nav bar when landing is visible and no pipeline running
  updateUIVisibility();

  if (!skipSave) {
    localStorage.setItem("polaris_view_mode", mode);
  }
}

function updateUIVisibility() {
  var landing = document.getElementById("landing-page");
  var navBar = document.getElementById("main-nav-bar");
  var viewsContainer = document.querySelector(".views-container");
  var userProgress = document.getElementById("user-progress");
  var workspace = document.getElementById("workspace");

  var isUserMode = _currentViewMode === "user";
  var isLanding = !state.pipelineActive && !state.pipelineComplete;

  if (isUserMode) {
    // User mode: show workspace, hide old landing/progress/views
    landing.classList.remove("visible");
    navBar.style.display = "none";
    viewsContainer.style.display = "none";
    userProgress.classList.remove("visible");

    if (workspace) {
      workspace.classList.add("visible");
      // Sync workspace phase with pipeline state
      if (state.pipelineActive && state.workspacePhase !== "running") {
        if (typeof setWorkspacePhase === "function") setWorkspacePhase("running");
      } else if (state.pipelineComplete && state.workspacePhase !== "report") {
        if (typeof setWorkspacePhase === "function") setWorkspacePhase("report");
      } else if (isLanding && state.workspacePhase !== "idle" && state.workspacePhase !== "report") {
        if (typeof setWorkspacePhase === "function") setWorkspacePhase("idle");
      }
    }
  } else {
    // Operator mode -- always show nav + views, hide workspace
    landing.classList.remove("visible");
    navBar.style.display = "flex";
    viewsContainer.style.display = "flex";
    userProgress.classList.remove("visible");
    if (workspace) workspace.classList.remove("visible");
  }
}

/* =====================================================================
   RESEARCH SUBMISSION — Depth selector + example cards
   submitResearchFromPayload() lives in core.js (canonical submit path).
   ===================================================================== */
function setDepth(depth) {
  _selectedDepth = depth;
  document.querySelectorAll(".depth-chip").forEach(function(chip) {
    chip.classList.toggle("active", chip.dataset.depth === depth);
  });
}

function useExample(card) {
  var text = card.querySelector(".example-text").textContent;
  var textarea = document.getElementById("compose-query");
  if (textarea) textarea.value = text;
  openCompose(document.getElementById("compose-trigger") || document.getElementById("compose-fab"));
}

function cancelResearch() {
  fetch("/api/research/cancel", { method: "POST" })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    showToast(data.message || data.error || "Cancelled", "info");
    state.pipelineActive = false;
    updateUIVisibility();
  })
  .catch(function(err) {
    showToast("Cancel failed: " + err.message, "error");
  });
}

function checkResearchStatus() {
  fetch("/api/research/status")
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.running) {
      state.pipelineActive = true;
      state.researchQuery = data.query;
      state.vectorId = data.vector_id;
      document.getElementById("user-progress-query").textContent = data.query || "Researching...";
      document.getElementById("vector-id").textContent = data.vector_id || "--";
      updateUIVisibility();
      if (typeof updateComposeBarState === "function") updateComposeBarState();
    }
  })
  .catch(function() {});
}

/* =====================================================================
   USER PROGRESS -- Map pipeline events to human-language progress
   ===================================================================== */
var USER_PHASE_MAP = {
  "plan": { step: "search", text: "Planning research strategy...", pct: 5 },
  "search": { step: "search", text: "Searching {n} sources across the web...", pct: 15 },
  "storm_interviews": { step: "interview", text: "Interviewing {n} expert perspectives...", pct: 30 },
  "analyze": { step: "interview", text: "Analyzing and extracting evidence...", pct: 45 },
  "verify": { step: "verify", text: "Verifying {n} claims against source text...", pct: 60 },
  "evaluate": { step: "verify", text: "Evaluating evidence quality...", pct: 70 },
  "synthesize": { step: "synthesize", text: "Writing and synthesizing report...", pct: 85 },
  "search_gaps": { step: "search", text: "Searching for additional evidence...", pct: 50 }
};

function updateUserProgress(node, metrics) {
  if (_currentViewMode !== "user" || !state.pipelineActive) return;

  var mapping = USER_PHASE_MAP[node];
  if (!mapping) return;

  // Update phase text with human-language labels including live counts
  var phaseText = getPhaseLabel(node, {});
  document.getElementById("user-phase-text").textContent = phaseText;

  // Update estimated time remaining
  var timeEst = estimateTimeRemaining(node);
  var timeEstEl = document.getElementById("user-time-estimate");
  if (timeEstEl) timeEstEl.textContent = timeEst;

  // Update progress bar
  document.getElementById("user-progress-bar").style.width = mapping.pct + "%";
  var barWrap = document.getElementById("user-progress-bar-wrap");
  if (barWrap) barWrap.setAttribute("aria-valuenow", mapping.pct);

  // Update step indicators
  var steps = ["search", "interview", "verify", "synthesize"];
  var currentIdx = steps.indexOf(mapping.step);
  document.querySelectorAll("#user-progress-steps .user-step").forEach(function(stepEl, i) {
    stepEl.classList.remove("active", "done");
    if (i < currentIdx) stepEl.classList.add("done");
    else if (i === currentIdx) stepEl.classList.add("active");
  });
  // Add checkmarks to done steps
  document.querySelectorAll("#user-progress-steps .user-step.done .step-check").forEach(function(el) {
    el.textContent = "\u2713";
  });

  // Update stats with animated counters
  animateCounter("user-stat-sources", state.sources.size);
  animateCounter("user-stat-evidence", state.evidence);
  var faithText = (state.faithfulness > 0 || state.verificationVerdicts.length > 0) ? Math.round(state.faithfulness * 100) + "%" : "--";
  document.getElementById("user-stat-faith").textContent = faithText;
}


/* =====================================================================
   AUTH UI -- Login/Logout/History (2B.1)
   ===================================================================== */
var _authEnabled = false;

function initAuth() {
  fetch("/api/auth/status")
  .then(function(r) { return r.json(); })
  .then(function(data) {
    _authEnabled = data.auth_enabled === true;
    if (_authEnabled) {
      document.getElementById("auth-button").style.display = "inline-flex";
      var token = localStorage.getItem("polaris_token");
      if (token) {
        checkAuthToken(token);
      }
    }
  })
  .catch(function() {
    // Auth endpoint not available, keep hidden
  });
}

function checkAuthToken(token) {
  fetch("/api/auth/me", {
    headers: {"Authorization": "Bearer " + token}
  })
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("invalid");
  })
  .then(function(data) {
    state.authenticated = true;
    state.user = data;
    updateAuthUI();
    loadResearchHistory();
  })
  .catch(function() {
    localStorage.removeItem("polaris_token");
    state.authenticated = false;
    state.user = null;
    updateAuthUI();
  });
}

function toggleAuthModal() {
  if (state.authenticated) {
    handleLogout();
  } else {
    openAuthModal();
  }
}

function openAuthModal() {
  var modal = document.getElementById("auth-modal");
  modal.classList.add("visible");
  setTimeout(function() {
    document.getElementById("auth-username").focus();
  }, 100);
}

function closeAuthModal() {
  document.getElementById("auth-modal").classList.remove("visible");
  document.getElementById("auth-error").style.display = "none";
  document.getElementById("auth-username").value = "";
  document.getElementById("auth-password").value = "";
}

function handleLogin(e) {
  e.preventDefault();
  var username = document.getElementById("auth-username").value;
  var password = document.getElementById("auth-password").value;
  var errorEl = document.getElementById("auth-error");
  errorEl.style.display = "none";

  fetch("/api/auth/login", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({username: username, password: password})
  })
  .then(function(r) {
    if (r.ok) return r.json();
    return r.json().then(function(d) { throw new Error(d.detail || "Invalid credentials"); });
  })
  .then(function(data) {
    localStorage.setItem("polaris_token", data.token);
    state.authenticated = true;
    state.user = {username: data.username, role: data.role};
    closeAuthModal();
    showToast("Signed in as " + data.username, "success");
    updateAuthUI();
    loadResearchHistory();
  })
  .catch(function(err) {
    errorEl.textContent = err.message || "Login failed";
    errorEl.style.display = "block";
  });
}

function handleLogout() {
  localStorage.removeItem("polaris_token");
  state.authenticated = false;
  state.user = null;
  updateAuthUI();
  var histPanel = document.getElementById("history-panel");
  if (histPanel) histPanel.classList.remove("visible");
  showToast("Signed out", "info");
}

function updateAuthUI() {
  var authBtn = document.getElementById("auth-button");
  if (!authBtn) return;
  if (state.authenticated && state.user) {
    authBtn.textContent = state.user.username || "User";
    authBtn.setAttribute("aria-label", "Signed in as " + (state.user.username || "User") + ". Click to sign out.");
  } else {
    authBtn.textContent = "Sign In";
    authBtn.setAttribute("aria-label", "Sign in or view account");
  }
}

function loadResearchHistory() {
  var token = localStorage.getItem("polaris_token");
  if (!token) return;
  fetch("/api/auth/history", {
    headers: {"Authorization": "Bearer " + token}
  })
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("unauthorized");
  })
  .then(function(history) {
    renderHistoryPanel(history);
  })
  .catch(function(err) {
    console.warn("Failed to load research history:", err);
  });
}

function renderHistoryPanel(sessions) {
  var panel = document.getElementById("history-panel");
  var list = document.getElementById("history-list");
  if (!panel || !list) return;
  if (!sessions || !sessions.length) { panel.classList.remove("visible"); return; }

  panel.classList.add("visible");
  var items = sessions.slice(0, 10);
  list.innerHTML = items.map(function(s) {
    var query = esc(truncStr(s.query || "Untitled", 80));
    var statusCls = (s.status || "").toLowerCase();
    var statusText = (s.status || "unknown").toUpperCase();
    var dateStr = "";
    if (s.created_at) {
      var d = new Date(s.created_at * 1000);
      dateStr = d.toLocaleDateString() + " " + d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
    }
    return '<div class="history-item" tabindex="0" role="button" ' +
      'onclick="loadHistoryItem(\'' + esc(s.vector_id || "") + '\')" ' +
      'onkeydown="if(event.key===\'Enter\'||event.key===\' \'){this.click();event.preventDefault();}" ' +
      'aria-label="View research: ' + query + '">' +
      '<span class="history-item-status ' + statusCls + '">' + statusText + '</span>' +
      '<span class="history-item-query">' + query + '</span>' +
      '<span class="history-item-meta">' + esc(dateStr) + '</span>' +
      '</div>';
  }).join("");
}

function loadHistoryItem(vectorId) {
  if (!vectorId) return;
  fetch("/api/research/result/" + encodeURIComponent(vectorId))
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("not found");
  })
  .then(function(data) {
    state.pipelineComplete = true;
    state.vectorId = vectorId;
    if (data.final_report) state.fullReport = data.final_report;
    if (data.bibliography) state.bibliography = data.bibliography;
    if (data.smart_art_diagrams) state.smartArtDiagrams = data.smart_art_diagrams;
    updateUIVisibility();
    switchView("report");
    showToast("Loaded research: " + (data.query || vectorId), "info");
  })
  .catch(function(err) {
    showToast("Could not load result: " + err.message, "error");
  });
}

// Close auth modal on Escape key
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") {
    var modal = document.getElementById("auth-modal");
    if (modal && modal.classList.contains("visible")) {
      closeAuthModal();
    }
  }
});

// Close auth modal on backdrop click
(function() {
  var authModal = document.getElementById("auth-modal");
  if (authModal) {
    authModal.addEventListener("click", function(e) {
      if (e.target === this) closeAuthModal();
    });
  }
})();


/* =====================================================================
   CAMPAIGN MANAGEMENT -- Operator-mode batch research campaigns
   ===================================================================== */
function toggleCampaignForm() {
  var form = document.getElementById("campaign-form");
  if (!form) return;
  var isVisible = form.style.display === "block";
  form.style.display = isVisible ? "none" : "block";
}

function createCampaign() {
  var nameInput = document.getElementById("campaign-name-input");
  var descInput = document.getElementById("campaign-desc-input");
  var queriesInput = document.getElementById("campaign-queries-input");
  var depthSelect = document.getElementById("campaign-depth-select");

  var name = (nameInput.value || "").trim();
  if (!name) {
    showToast("Please enter a campaign name", "warning");
    return;
  }

  var queriesText = (queriesInput.value || "").trim();
  var queries = queriesText.split("\n").map(function(q) { return q.trim(); }).filter(function(q) { return q.length > 0; });
  if (queries.length === 0) {
    showToast("Please enter at least one research query", "warning");
    return;
  }

  var campaign = {
    id: "camp_" + Date.now() + "_" + Math.random().toString(36).slice(2, 6),
    name: name,
    description: (descInput.value || "").trim(),
    queries: queries,
    depth: depthSelect ? depthSelect.value : "standard",
    status: "pending",
    created_at: Date.now(),
    results: []
  };

  // Try server-side first, fall back to localStorage
  fetch("/api/campaigns", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(campaign)
  })
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("server");
  })
  .then(function(data) {
    showToast("Campaign created: " + name, "success");
    toggleCampaignForm();
    nameInput.value = "";
    descInput.value = "";
    queriesInput.value = "";
    getCampaigns();
  })
  .catch(function() {
    // Fallback: save to localStorage
    var campaigns = JSON.parse(localStorage.getItem("polaris_campaigns") || "[]");
    campaigns.push(campaign);
    localStorage.setItem("polaris_campaigns", JSON.stringify(campaigns));
    showToast("Campaign saved locally: " + name, "success");
    toggleCampaignForm();
    nameInput.value = "";
    descInput.value = "";
    queriesInput.value = "";
    renderCampaigns(campaigns);
  });
}

function getCampaigns() {
  fetch("/api/campaigns")
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("server");
  })
  .then(function(data) {
    renderCampaigns(Array.isArray(data) ? data : []);
  })
  .catch(function() {
    // Fallback: load from localStorage
    var campaigns = JSON.parse(localStorage.getItem("polaris_campaigns") || "[]");
    renderCampaigns(campaigns);
  });
}

function renderCampaigns(campaigns) {
  var panel = document.getElementById("campaign-panel");
  var list = document.getElementById("campaign-list");
  if (!list) return;

  // Always show campaign panel (with empty state if needed)
  if (panel) panel.classList.add("visible");

  if (!campaigns || campaigns.length === 0) {
    list.innerHTML = '<div class="campaign-empty">No campaigns yet. Create one to batch multiple research queries.</div>';
    return;
  }

  var html = '';
  campaigns.forEach(function(c) {
    var statusClass = c.status === "running" ? "running" : c.status === "completed" ? "completed" : "pending";
    var completedCount = (c.results || []).length;
    var totalCount = (c.queries || []).length;
    html += '<div class="campaign-item">' +
      '<div class="campaign-item-header" role="button" tabindex="0" onclick="toggleCampaignDetail(\'' + esc(c.id) + '\')" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){toggleCampaignDetail(\'' + esc(c.id) + '\');event.preventDefault();}">' +
      '<span class="campaign-item-status ' + statusClass + '">' + esc(c.status || "pending") + '</span>' +
      '<span class="campaign-item-name">' + esc(c.name) + '</span>' +
      '<span class="campaign-item-progress">' + completedCount + '/' + totalCount + '</span>' +
      '</div>' +
      '<div class="campaign-detail" id="campaign-detail-' + esc(c.id) + '" style="display:none">' +
      (c.description ? '<p class="campaign-desc">' + esc(c.description) + '</p>' : '') +
      '<div class="campaign-queries">';
    (c.queries || []).forEach(function(q, qi) {
      var qStatus = qi < completedCount ? "done" : "pending";
      html += '<div class="campaign-query-item ' + qStatus + '">' +
        '<span class="campaign-query-status">' + (qStatus === "done" ? "\u2713" : "\u2022") + '</span>' +
        '<span class="campaign-query-text">' + esc(q) + '</span>' +
        '</div>';
    });
    html += '</div>' +
      '<div class="campaign-actions">' +
      (c.status !== "running" && c.status !== "completed" ?
        '<button class="campaign-start-btn" onclick="startCampaign(\'' + esc(c.id) + '\')">Start</button>' : '') +
      '<button class="campaign-delete-btn" onclick="deleteCampaign(\'' + esc(c.id) + '\')">Delete</button>' +
      '</div>' +
      '</div>' +
      '</div>';
  });
  list.innerHTML = html;
}

function toggleCampaignDetail(campaignId) {
  var detail = document.getElementById("campaign-detail-" + campaignId);
  if (!detail) return;
  var isVisible = detail.style.display === "block";
  detail.style.display = isVisible ? "none" : "block";
}

function startCampaign(campaignId) {
  fetch("/api/campaigns/" + encodeURIComponent(campaignId) + "/start", { method: "POST" })
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("server");
  })
  .then(function(data) {
    showToast("Campaign started: " + (data.name || campaignId), "success");
    getCampaigns();
  })
  .catch(function() {
    showToast("Could not start campaign (server unavailable)", "warning");
  });
}

function deleteCampaign(campaignId) {
  fetch("/api/campaigns/" + encodeURIComponent(campaignId), { method: "DELETE" })
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("server");
  })
  .then(function() {
    showToast("Campaign deleted", "info");
    getCampaigns();
  })
  .catch(function() {
    // Fallback: delete from localStorage
    var campaigns = JSON.parse(localStorage.getItem("polaris_campaigns") || "[]");
    campaigns = campaigns.filter(function(c) { return c.id !== campaignId; });
    localStorage.setItem("polaris_campaigns", JSON.stringify(campaigns));
    showToast("Campaign deleted locally", "info");
    renderCampaigns(campaigns);
  });
}


/* =====================================================================
   BOOKMARKS -- Save/load research results (localStorage-based)
   ===================================================================== */
function getBookmarks() {
  try {
    return JSON.parse(localStorage.getItem("polaris_bookmarks") || "[]");
  } catch(e) {
    return [];
  }
}

function isBookmarked(vectorId) {
  var bookmarks = getBookmarks();
  return bookmarks.some(function(b) { return b.vector_id === vectorId; });
}

function toggleBookmark(vectorId, query) {
  var bookmarks = getBookmarks();
  var idx = -1;
  for (var i = 0; i < bookmarks.length; i++) {
    if (bookmarks[i].vector_id === vectorId) { idx = i; break; }
  }

  if (idx >= 0) {
    bookmarks.splice(idx, 1);
    showToast("Bookmark removed", "info");
  } else {
    bookmarks.unshift({
      vector_id: vectorId,
      query: query || state.researchQuery || "Unknown",
      saved_at: Date.now()
    });
    showToast("Research bookmarked", "success");
  }

  localStorage.setItem("polaris_bookmarks", JSON.stringify(bookmarks));
  updateBookmarkButton(vectorId);
  renderBookmarksPanel();
}

function updateBookmarkButton(vectorId) {
  var btn = document.getElementById("bookmark-btn");
  if (!btn) return;
  if (isBookmarked(vectorId)) {
    btn.classList.add("active");
    btn.setAttribute("aria-label", "Remove bookmark");
  } else {
    btn.classList.remove("active");
    btn.setAttribute("aria-label", "Bookmark this research");
  }
}

function removeBookmark(vectorId) {
  var bookmarks = getBookmarks().filter(function(b) { return b.vector_id !== vectorId; });
  localStorage.setItem("polaris_bookmarks", JSON.stringify(bookmarks));
  showToast("Bookmark removed", "info");
  renderBookmarksPanel();
}

function loadBookmarkItem(vectorId) {
  if (!vectorId) return;
  fetch("/api/research/result/" + encodeURIComponent(vectorId))
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("not found");
  })
  .then(function(data) {
    state.pipelineComplete = true;
    state.vectorId = vectorId;
    if (data.final_report) state.fullReport = data.final_report;
    if (data.bibliography) state.bibliography = data.bibliography;
    if (data.smart_art_diagrams) state.smartArtDiagrams = data.smart_art_diagrams;
    updateUIVisibility();
    switchView("report");
    showToast("Loaded bookmarked research: " + (data.query || vectorId), "info");
  })
  .catch(function(err) {
    showToast("Could not load bookmarked result: " + err.message, "error");
  });
}

function renderBookmarksPanel() {
  var panel = document.getElementById("bookmarks-panel");
  var list = document.getElementById("bookmarks-list");
  if (!list) return;

  var bookmarks = getBookmarks();
  if (bookmarks.length === 0) {
    if (panel) panel.classList.remove("visible");
    list.innerHTML = '<div class="bookmark-empty">No saved research yet.</div>';
    return;
  }
  if (panel) panel.classList.add("visible");

  var html = '';
  bookmarks.slice(0, 20).forEach(function(b) {
    var dateStr = "";
    if (b.saved_at) {
      var d = new Date(b.saved_at);
      dateStr = d.toLocaleDateString();
    }
    html += '<div class="bookmark-item" tabindex="0" role="button" ' +
      'onclick="loadBookmarkItem(\'' + esc(b.vector_id || "") + '\')" ' +
      'onkeydown="if(event.key===\'Enter\'||event.key===\' \'){this.click();event.preventDefault();}">' +
      '<span class="bookmark-star-sm">&#9733;</span>' +
      '<span class="bookmark-query">' + esc(truncStr(b.query || "Untitled", 60)) + '</span>' +
      '<span class="bookmark-date">' + esc(dateStr) + '</span>' +
      '<button class="bookmark-remove" onclick="event.stopPropagation();removeBookmark(\'' + esc(b.vector_id || "") + '\')" ' +
      'aria-label="Remove bookmark">&times;</button>' +
      '</div>';
  });
  list.innerHTML = html;
}

function loadBookmarks() {
  renderBookmarksPanel();
}


/* =====================================================================
   INITIALIZATION -- Run on load after all scripts are ready
   ===================================================================== */
getCampaigns();
initAuth();
loadBookmarks();

// Debug export
window._getDebugState = function() { return state; };
