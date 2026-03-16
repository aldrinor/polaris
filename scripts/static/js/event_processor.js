/* =====================================================================
   event_processor.js — Event dispatch (processSSEEvent), all event type
   handlers (node_start, node_end, evidence, quality_gate, reasoning_capture,
   storm_transcript, search_result, iteration_decision, etc.), updateMetrics()
   ===================================================================== */

/* =====================================================================
   Main Event Processor
   ===================================================================== */
function processEvent(ev) {
  try {
  state.eventCount++;
  if (!state.startTime) state.startTime = ev.ts ? new Date(ev.ts).getTime() : Date.now();
  if (ev.vid && ev.vid !== "--" && ev.vid !== "unknown") state.vectorId = ev.vid;
  var evType = ev.type || "unknown";
  var node = ev.node || "";
  state.traceEvents.push(ev);
  if (state.traceEvents.length > 5000) state.traceEvents.shift();

  // ---- Phase status ----
  if (evType === "node_start" && NODE_ORDER.indexOf(node) >= 0) {
    state.phaseStatus[node] = "active";
    state.currentNode = node;
    state.activeReasoningPhase = node;
    if (!state.nodeTimings[node]) state.nodeTimings[node] = [];
    state.nodeTimings[node].push({ start: ev.ts ? new Date(ev.ts).getTime() : Date.now(), end: null, iteration: ev.iteration });
    updateStepper();
    // Master-detail: notify phase status change for auto-follow
    if (typeof onPhaseStatusChange === 'function') onPhaseStatusChange(node, 'active');
    if (state.autoTab && AUTO_TAB_MAP[node] && !state._hydrating) {
      switchView(AUTO_TAB_MAP[node]);
      if (AUTO_TAB_MAP[node] === "advanced") {
        state.activeAdvTab = "storm";
        document.querySelectorAll(".adv-tab-btn").forEach(function(b) { b.classList.toggle("active", b.dataset.adv === "storm"); });
        document.querySelectorAll(".adv-pane").forEach(function(p) { p.classList.toggle("active", p.id === "adv-storm"); });
      }
    }
    var desc = NODE_DESCRIPTIONS[node] || ("Running " + node + "...");
    setText("current-status-text", "Currently: " + desc);
    // User mode progress update
    updateUserProgress(node, {});
  }
  if (evType === "node_end" && NODE_ORDER.indexOf(node) >= 0) {
    state.phaseStatus[node] = "done";
    if (state.nodeTimings[node] && state.nodeTimings[node].length) {
      var last = state.nodeTimings[node][state.nodeTimings[node].length - 1];
      last.end = ev.ts ? new Date(ev.ts).getTime() : Date.now();
      last.duration_ms = ev.duration_ms || (last.end - last.start);
      last.metrics = { evidence_count: ev.evidence_count, total_words: ev.total_words, faithfulness: ev.faithfulness, query_count: ev.query_count };
    }
    // Extract faithfulness from verify node_end
    if (node === "verify" && ev.faithfulness !== undefined && ev.faithfulness > 0) {
      state.faithfulness = ev.faithfulness;
      updateGateDot("gate-faith", ev.faithfulness >= 0.50);
    }
    // Extract words from synthesize node_end
    if (node === "synthesize" && ev.total_words) {
      state.words = ev.total_words;
    }
    updateStepper();
    // Master-detail: notify phase status change
    if (typeof onPhaseStatusChange === 'function') onPhaseStatusChange(node, 'done');
    markDirty("research");
  }

  // ---- Pipeline start ----
  if (evType === "pipeline_start") {
    // Reset ALL run-specific state so stale data from previous run doesn't persist
    state.evidence = 0; state.sources = new Set(); state.faithfulness = 0;
    state.verifiedEvidence = 0; state.words = 0; state.citations = 0; state.cost = 0; state.iteration = 0;
    state.phaseStatus = {};
    state.queries = []; state.fetches = []; state.stormPersonas = []; state.stormChats = [];
    state.evidenceEvents = []; state.evidenceDetails = [];
    state.sectionWrites = []; state.gateHistory = []; state.traceEvents = [];
    state.reasoningCaptures = []; state.reasoningLog = [];
    state.verificationVerdicts = []; state.clusterThemes = [];
    state.bibliography = []; state.citationMapping = []; state.citationMappingFull = null;
    state.llmDetails = [];
    state.scoringDetail = []; state.dedupDetail = null;
    state.verificationContext = []; state.expansionDetails = [];
    state.funnelScored = 0; state.funnelFiltered = 0; state.funnelExtracted = 0; state.funnelVerified = 0;
    state.tierCounts = { gold: 0, silver: 0, bronze: 0 };
    state.engineCounts = {}; state.totalResults = 0;
    state.fetchSuccess = 0; state.fetchSnippet = 0; state.fetchFailed = 0;
    state.nodeTimings = {};
    state.graphNodes = []; state.graphEdges = [];
    state.gates = {};
    state.planQueries = []; state.searchStrategy = ""; state.keyConcepts = [];
    state.perspectiveDist = {}; state.missingPerspectives = [];
    state.signalStats = {}; state.dedupStats = null; state.fetchSummary = null;
    state.nliSummary = null; state.nliClaimsDetail = []; state.crossRefGroups = [];
    state.reportOutline = null; state.sectionEvidenceMap = [];
    state.hallucinationAudit = []; state.evidenceConflicts = [];
    state.expansionPasses = []; state.gapAnalysis = null; state.fullReport = "";
    state.agenticRounds = [];
    state.llmCallCount = 0; state.llmInputTokens = 0; state.llmOutputTokens = 0; state.modelCounts = {};
    state.reasoningByPhase = {}; state.activeReasoningPhase = null;
    state.selectedEvidenceIdx = -1;
    // Set new run state
    state.researchQuery = ev.query || "";
    state.application = ev.application || "";
    state.region = ev.region || "";
    state.maxIterations = ev.max_iterations || 0;
    state.budgetUsd = ev.budget_usd || 0;
    state.pipelineActive = true;
    state.pipelineComplete = false;
    state.endTime = null;
    state.startTime = ev.ts ? new Date(ev.ts).getTime() : Date.now();
    if (ev.vector_id) state.vectorId = ev.vector_id;
    // Show run-context-bar (CSS handles visibility via body:not(.user-mode))
    var banner = document.getElementById("research-query-banner") || document.getElementById("run-context-bar");
    if (banner) banner.style.display = banner.id === "run-context-bar" ? "flex" : "block";
    setText("research-query-text", state.researchQuery);
    setText("vector-id", state.vectorId);
    document.getElementById("user-progress-query").textContent = state.researchQuery;
    var appRegion = "";
    if (state.application) appRegion += state.application;
    if (state.region) appRegion += (appRegion ? " | " : "") + state.region;
    if (state.maxIterations) appRegion += (appRegion ? " | " : "") + "max " + state.maxIterations + " iters";
    if (state.budgetUsd) appRegion += (appRegion ? " | " : "") + "$" + state.budgetUsd + " budget";
    setText("research-app-region", appRegion);
    addActivity("\u{1F680}", 'Pipeline started: <span class="highlight">' + esc(state.researchQuery) + '</span>', ev.ts);
    updateUIVisibility();
  }

  // ---- Pipeline end ----
  if (evType === "pipeline_end") {
    state.endTime = ev.ts ? new Date(ev.ts).getTime() : Date.now();
    state.pipelineActive = false;
    state.pipelineComplete = true;
    if (ev.status !== "completed" && ev.status !== "timeout_synthesized") {
      // Failed/crashed — show failure status
      console.warn("[event_processor] Pipeline ended with status:", ev.status);
    }
    if (ev.total_words) state.words = ev.total_words;
    if (ev.total_citations) state.citations = ev.total_citations;
    if (ev.faithfulness_score !== undefined) state.faithfulness = ev.faithfulness_score;
    if (ev.total_cost_usd !== undefined) state.cost = ev.total_cost_usd;
    if (ev.elapsed_seconds) {
      var eSec = Math.floor(ev.elapsed_seconds);
      var eHH = String(Math.floor(eSec / 3600)).padStart(2, "0");
      var eMM = String(Math.floor((eSec % 3600) / 60)).padStart(2, "0");
      var eSS = String(eSec % 60).padStart(2, "0");
      setText("elapsed-time", eHH + ":" + eMM + ":" + eSS);
    }
    var statusEmoji = ev.status === "completed" ? "\u2705" : ev.status === "timeout_synthesized" ? "\u23F0" : "\u274C";
    addActivity(statusEmoji, 'Pipeline ' + esc(ev.status || "ended") + ' (' + (ev.elapsed_seconds ? Math.round(ev.elapsed_seconds) + 's' : '?') + ')', ev.ts);
    setText("current-status-text", "Pipeline " + (ev.status || "ended"));
    updateMetrics();
  }

  // ---- LLM detail ----
  if (evType === "llm_detail") {
    state.llmDetails.push(ev);
    markDirty("advanced");
  }

  // ---- Search results ----
  if (evType === "search_result") {
    var q = { engine: ev.engine || "unknown", query: ev.query || "", resultCount: ev.result_count || 0,
      ts: ev.ts, urls: ev.urls || [], titles: ev.titles || [], snippets: ev.snippets || [],
      scores: ev.scores || [], cached: ev.cached || false, fallback: ev.fallback || false, exa_cost: ev.exa_cost || 0 };
    state.queries.push(q);
    if (state.queries.length > 1000) state.queries.shift();
    state.engineCounts[q.engine] = (state.engineCounts[q.engine] || 0) + q.resultCount;
    state.totalResults += q.resultCount;
    addActivity("\u{1F50D}", 'Searching: <span class="highlight">' + esc(truncStr(q.query, 300)) + '</span> (' + q.engine + ' \u2192 ' + q.resultCount + ')', ev.ts);
    markDirty("advanced");
  }

  // ---- Fetch ----
  if (evType === "fetch") {
    var url = ev.url || "";
    var domain = extractDomain(url);
    var status = ev.status || "unknown";
    state.fetches.push({ url: url, domain: domain, status: status, contentLen: ev.content_len || 0, method: ev.method || "", ts: ev.ts });
    if (state.fetches.length > 300) state.fetches.shift();
    state.sources.add(domain);
    if (status === "success") state.fetchSuccess++;
    else if (status === "snippet_fallback") state.fetchSnippet++;
    else state.fetchFailed++;
    var sizeStr = (ev.content_len || 0) >= 1000 ? Math.round((ev.content_len || 0) / 1000) + "K" : (ev.content_len || 0) + "";
    var statusColor = status === "success" ? "var(--success)" : status === "snippet_fallback" ? "var(--warning)" : "var(--error)";
    addActivity("\u{1F310}", 'Fetched <span class="highlight">' + esc(domain) + '</span> <span style="color:' + statusColor + '">(' + sizeStr + ' chars)</span>', ev.ts);
    markDirty("advanced");
  }

  // ---- Evidence ----
  if (evType === "evidence") {
    state.evidenceEvents.push(ev);
    var action = ev.action || "";
    if (action === "relevance_scored") state.funnelScored = Math.max(state.funnelScored, ev.count || 0);
    if (action === "offtopic_filtered") state.funnelFiltered = Math.max(state.funnelFiltered, ev.count || 0);
    if (action === "extracted") {
      state.funnelExtracted += (ev.count || 0);
      state.evidence = state.funnelExtracted;
      state.tierCounts.gold += (ev.gold || 0);
      state.tierCounts.silver += (ev.silver || 0);
      state.tierCounts.bronze += (ev.bronze || 0);
      addActivity("\u{1F4CE}", 'Extracted <span class="highlight">' + (ev.count || 0) + ' evidence</span> (' + (ev.gold || 0) + ' gold, ' + (ev.silver || 0) + ' silver)', ev.ts);
    }
    if (action === "accumulated") state.evidence = Math.max(state.evidence, ev.count || 0);
    if (action === "evidence_detail" && Array.isArray(ev.items)) {
      ev.items.forEach(function(p) { state.evidenceDetails.push(p); });
      if (state.evidenceDetails.length > 500) state.evidenceDetails = state.evidenceDetails.slice(-500);
    }
    if (action === "clustering") {
      if (Array.isArray(ev.themes)) state.clusterThemes = ev.themes;
      addActivity("\u{1F4CE}", 'Clustering: ' + (ev.count || 0) + ' clusters from ' + (ev.evidence_count || 0) + ' evidence', ev.ts);
      markDirty("report");
    }
    if (action === "citation_audit") {
      if (Array.isArray(ev.mapping)) state.citationMapping = ev.mapping;
      addActivity("\u2714", 'Citation audit: ' + (ev.grounded || 0) + '/' + (ev.count || 0) + ' grounded', ev.ts);
      markDirty("report");
    }
    if (action === "report_assembled") {
      if (Array.isArray(ev.bibliography)) state.bibliography = ev.bibliography;
      if (Array.isArray(ev.section_titles)) {
        ev.section_titles.forEach(function(st) {
          state.sectionWrites.forEach(function(sw) { if (sw.sectionId === st.id && !sw.title) sw.title = st.title; });
        });
      }
      if (ev.full_report) { state.fullReport = ev.full_report; markDirty("report"); }
      addActivity("\u{1F4DD}", 'Report assembled: ' + (ev.count || 0) + ' words, ' + (ev.sections || 0) + ' sections, ' + (ev.total_citations || 0) + ' citations', ev.ts);
      // Auto-transition (skip during snapshot hydration)
      state.pipelineComplete = true;
      state.pipelineActive = false;
      state.endTime = ev.ts ? new Date(ev.ts).getTime() : Date.now();
      // Update status bar text and stop dot pulsing
      setText("current-status-text", "Pipeline complete");
      var statusDot = document.getElementById("status-dot");
      if (statusDot) {
        statusDot.classList.remove("connected");
        statusDot.classList.add("completed");
      }
      // Backfill bibliography from result API if trace event didn't include it
      if (state.bibliography.length === 0 && state.vectorId) {
        fetch("/api/research/result/" + encodeURIComponent(state.vectorId))
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(d) {
          if (d && Array.isArray(d.bibliography) && d.bibliography.length > 0) {
            state.bibliography = d.bibliography;
            updateMetrics();
          }
        }).catch(function() {});
      }
      // A2: Fetch checkpoint timeline after pipeline completes
      if (typeof fetchCheckpoints === "function" && state.vectorId) {
        try { fetchCheckpoints(); } catch(e) { console.warn("[event_processor] fetchCheckpoints error:", e); }
      }
      if (!state._hydrating) {
        showToast("Research complete! Viewing report...", "success");
        // In user mode, update progress bar to 100% then transition
        document.getElementById("user-progress-bar").style.width = "100%";
        document.getElementById("user-phase-text").textContent = "Report ready!";
        document.querySelectorAll("#user-progress-steps .user-step").forEach(function(s) {
          s.classList.remove("active"); s.classList.add("done");
          s.querySelector(".step-check").textContent = "\u2713";
        });
        setTimeout(function() {
          updateUIVisibility();
          if (state.autoTab) switchView("report");
        }, 1500);
      }
      markDirty("report");
    }
    if (action === "query_plan" || action === "seed_query_plan") {
      if (Array.isArray(ev.queries)) state.planQueries = ev.queries;
      state.searchStrategy = ev.search_strategy || "";
      if (Array.isArray(ev.key_concepts)) state.keyConcepts = ev.key_concepts;
      if (ev.perspective_distribution) state.perspectiveDist = ev.perspective_distribution;
      if (Array.isArray(ev.missing_perspectives)) state.missingPerspectives = ev.missing_perspectives;
      addActivity("\u{1F4CB}", 'Query plan: ' + (ev.count || 0) + ' queries, strategy=' + esc(ev.search_strategy || "?"), ev.ts);
      markDirty("advanced");
    }
    if (action === "tier_signal_distribution") { if (ev.signal_stats) state.signalStats = ev.signal_stats; markDirty("evidence"); }
    if (action === "tier_scoring_detail") {
      state.scoringDetail = ev.scores || [];
      addActivity("\u{1F4CA}", 'Tier scoring: ' + (ev.count || 0) + ' evidence scored', ev.ts);
      markDirty("evidence");
    }
    if (action === "dedup_detail") {
      state.dedupDetail = { before: ev.before_count || 0, after: ev.after_count || 0, exactRemoved: ev.exact_removed || 0, nearRemoved: ev.near_removed || 0, pairs: ev.minhash_pairs || [] };
      markDirty("evidence");
    }
    if (action === "dedup_summary") { state.dedupStats = { pre_dedup: ev.pre_dedup || 0, post_dedup: ev.post_dedup || ev.count || 0 }; markDirty("evidence"); }
    if (action === "fetch_summary") { state.fetchSummary = { total_attempted: ev.total_attempted || 0, success: ev.success || 0, snippet_fallback: ev.snippet_fallback || 0, failed: ev.failed || 0 }; markDirty("advanced"); }
    if (action === "nli_verification_detail") {
      state.nliSummary = { faithful_count: ev.faithful_count || 0, faithfulness_pct: ev.faithfulness_pct || 0, disputed_count: ev.disputed_count || 0 };
      if (Array.isArray(ev.claims_detail)) state.nliClaimsDetail = ev.claims_detail;
      markDirty("evidence");
    }
    if (action === "cross_reference_groups") { if (Array.isArray(ev.groups)) state.crossRefGroups = ev.groups; markDirty("evidence"); }
    if (action === "report_outline") {
      state.reportOutline = { title: ev.title || "", sections: ev.sections || [] };
      addActivity("\u{1F4D1}", 'Outline: "' + esc(truncStr(ev.title || "", 50)) + '" with ' + (ev.count || 0) + ' sections', ev.ts);
      markDirty("report");
    }
    if (action === "section_evidence_map") { if (Array.isArray(ev.mapping)) state.sectionEvidenceMap = ev.mapping; markDirty("report"); }
    if (action === "hallucination_audit") { if (Array.isArray(ev.sections)) state.hallucinationAudit = ev.sections; markDirty("report"); }
    if (action === "evidence_conflicts") { if (Array.isArray(ev.conflicts)) state.evidenceConflicts = ev.conflicts; markDirty("evidence"); }
    if (action === "section_conflicts") { if (Array.isArray(ev.conflicts)) { state.evidenceConflicts = (state.evidenceConflicts || []).concat(ev.conflicts); markDirty("report"); } }
    if (action === "verification_context") { state.verificationContext = ev.claims || []; markDirty("evidence"); }
    if (action === "citation_mapping_full") { state.citationMappingFull = { mapping: ev.full_mapping || [], mergePairs: ev.merge_pairs || [], ungrounded: ev.ungrounded || [] }; markDirty("report"); }
    if (action === "expansion_detail") { state.expansionDetails.push({ pass_number: ev.pass_number || 0, dynamic_target: ev.dynamic_target || 0, min_acceptable: ev.min_acceptable || 0, sections: ev.sections || [] }); markDirty("report"); }
    if (action === "expansion_pass") { state.expansionPasses.push({ pass: ev.count || state.expansionPasses.length + 1, total_words: ev.total_words || 0, total_citations: ev.total_citations || 0, thin_sections: ev.thin_sections || [] }); markDirty("report"); }
    if (action === "gap_analysis_detail") { state.gapAnalysis = { total_evidence: ev.total_evidence || 0, gold_count: ev.gold_count || 0, faithfulness: ev.faithfulness || 0, needs_iteration: ev.needs_iteration, gaps: ev.gaps || [], gap_queries: ev.gap_queries || [], perspective_coverage: ev.perspective_coverage || {} }; markDirty("research"); }
    if (action === "agentic_round_summary") {
      state.agenticRounds.push({ round: ev.count || state.agenticRounds.length + 1, queries: ev.queries || 0, web_results: ev.web_results || 0, academic_results: ev.academic_results || 0, new_urls: ev.new_urls || 0, total_urls: ev.total_urls || 0 });
      if (state.agenticRounds.length > 50) state.agenticRounds.shift();
      markDirty("advanced");
    }
    if (action === "section_evidence_filtered") {
      addActivity("\u{1F4CE}", 'Section "' + esc(truncStr(ev.title || "", 30)) + '": ' + (ev.after_filter || 0) + '/' + (ev.total_available || 0) + ' ev used', ev.ts);
      markDirty("report");
    }
    markDirty("evidence");
    // Update user-mode stats on evidence events (prevents "stalled" appearance)
    if (state.currentNode) updateUserProgress(state.currentNode, {});
  }

  // ---- LLM Call ----
  if (evType === "llm_call") {
    if (ev.cumulative_cost_usd !== undefined && ev.cumulative_cost_usd > 0) state.cost = ev.cumulative_cost_usd;
    else if (ev.cost_usd !== undefined) state.cost += ev.cost_usd;
    state.llmCallCount++;
    state.llmInputTokens += (ev.input_tokens || 0);
    state.llmOutputTokens += (ev.output_tokens || 0);
    if (ev.model) { var mName = ev.model.substring(0, 50); state.modelCounts[mName] = (state.modelCounts[mName] || 0) + 1; }
    var callType = ev.call_type || "";
    if (callType === "section_write" || callType === "section_expand") {
      state.sectionWrites.push({ sectionId: ev.section_id || "?", title: ev.title || "", content: ev.content || "", wordCount: ev.word_count || ev.expanded_words || 0, evidenceCount: ev.evidence_count || 0, type: callType, originalWords: ev.original_words, expandedWords: ev.expanded_words, addedWords: ev.added_words, ts: ev.ts });
      markDirty("report");
    }
    if (callType === "verification_batch") {
      state.funnelVerified += (ev.batch_size || 0);
      if (Array.isArray(ev.claims)) {
        ev.claims.forEach(function(c) { state.verificationVerdicts.push(c); });
        if (state.verificationVerdicts.length > 500) state.verificationVerdicts = state.verificationVerdicts.slice(-500);
      }
      markDirty("report");
    }
    if (callType === "perspective_discovery" && ev.perspectives) {
      state.stormPersonas = ev.perspectives.map(function(p) { return typeof p === "string" ? { name: p } : p; });
      addActivity("\u{1F4AC}", 'STORM perspectives: <span class="highlight">' + ev.perspectives.map(function(p) { return typeof p === "string" ? p : p.name || p; }).join(", ") + '</span>', ev.ts);
      markDirty("advanced");
    }
    if (callType === "interview_simulation") {
      addActivity("\u{1F4AC}", 'STORM interviews: ' + (ev.conversations || 0) + ' conversations, ' + (ev.total_rounds || 0) + ' rounds', ev.ts);
    }
  }

  // ---- Quality Gate ----
  if (evType === "quality_gate") {
    var passed = !!ev.passed;
    var gate = ev.gate || "";
    state.gateHistory.push({ gate: gate, passed: passed, expansionPass: ev.expansion_pass, words: ev.total_words, citations: ev.total_citations, sources: ev.unique_sources, actual: ev.actual, threshold: ev.threshold, result: ev.quality_gate_result, ts: ev.ts });
    // Populate state.gates for Report View rendering
    if (gate) {
      state.gates[gate] = { passed: passed, actual: ev.actual, threshold: ev.threshold, words: ev.total_words, citations: ev.total_citations, sources: ev.unique_sources, faith: ev.faithfulness_score || ev.faithfulness || ev.actual };
    }
    if (gate === "faithfulness" && ev.actual !== undefined) { state.faithfulness = ev.actual; updateGateDot("gate-faith", passed); }
    if (gate === "word_count" && ev.actual !== undefined) { state.words = ev.actual; updateGateDot("gate-words", passed); }
    if (gate === "citation_count" && ev.actual !== undefined) { state.citations = ev.actual; updateGateDot("gate-cite", passed); }
    if (gate === "unique_sources" && ev.actual !== undefined) { updateGateDot("gate-sources", passed); }
    if (gate === "post_synthesis" || gate === "post_synthesis_final") {
      if (ev.total_words) state.words = ev.total_words;
      if (ev.total_citations) state.citations = ev.total_citations;
      if (ev.evidence_count !== undefined) state.verifiedEvidence = ev.evidence_count;
      if (ev.total_evidence !== undefined) state.verifiedEvidence = ev.total_evidence;
      updateGateDot("gate-synth", passed);
      if (ev.total_words !== undefined) updateGateDot("gate-words", ev.total_words >= 2000);
      if (ev.total_citations !== undefined) updateGateDot("gate-cite", ev.total_citations >= 5);
      if (ev.unique_sources !== undefined) updateGateDot("gate-sources", ev.unique_sources >= 3);
      if (ev.faithfulness_score !== undefined) { state.faithfulness = ev.faithfulness_score; updateGateDot("gate-faith", ev.faithfulness_score >= 0.50); }
      var passText = passed ? '\u2705 PASS' : '\u274C FAIL';
      addActivity("\u{1F6A7}", 'Quality gate ' + passText + ': ' + (ev.total_words || 0) + ' words, ' + (ev.total_citations || 0) + ' citations' + (ev.expansion_pass ? ', pass #' + ev.expansion_pass : ''), ev.ts);
    }
    markDirty("report");
  }

  // ---- Iteration Decision ----
  if (evType === "iteration_decision") {
    if (ev.iteration !== undefined) state.iteration = ev.iteration;
    // Extract faithfulness from rationale if present
    var rationale = ev.rationale || {};
    if (rationale.faithfulness_score !== undefined && rationale.faithfulness_score > 0) {
      state.faithfulness = rationale.faithfulness_score;
      updateGateDot("gate-faith", rationale.faithfulness_score >= 0.50);
    }
    if (ev.total_words) state.words = ev.total_words;
    addActivity("\u{1F504}", 'Iteration ' + (ev.iteration || 0) + ': ' + esc(ev.decision || ""), ev.ts);
  }

  // ---- Reasoning Capture (THE FIX) ----
  if (evType === "reasoning_capture") {
    state.reasoningCaptures.push(ev);
    // ev.node is the LLM call type (structured/llm), not the pipeline node — use currentNode
    var rNode = (NODE_ORDER.indexOf(ev.node) >= 0) ? ev.node : (state.currentNode || "unknown");
    var rText = ev.reasoning_text || ev.text || "";
    var rEntry = { ts: ev.ts || new Date().toISOString(), call_type: ev.call_type || "unknown", text: rText, tokens: ev.reasoning_tokens || ev.output_tokens || 0, node: rNode };
    // Group by phase
    if (!state.reasoningByPhase[rNode]) state.reasoningByPhase[rNode] = [];
    state.reasoningByPhase[rNode].push(rEntry);
    // Also keep short log for activity
    state.reasoningLog.push({ ts: rEntry.ts, call_type: rEntry.call_type, text: rText.substring(0, 500) });
    if (state.reasoningLog.length > 50) state.reasoningLog.shift();
    if (rText.length > 0) {
      var excerpt = rText.substring(0, 100) + (rText.length > 100 ? '...' : '');
      addActivity("\u{1F9E0}", '<span class="highlight">' + esc(ev.call_type || 'reasoning') + '</span> <span style="color:var(--text-tertiary);font-size:11px">' + esc(excerpt) + '</span>', ev.ts);
    }
    markDirty("research");
  }

  // ---- STORM Transcript ----
  if (evType === "storm_transcript") {
    state.stormChats.push({ persona: ev.persona || "Unknown", round: ev.round, question: ev.question || "", answer: ev.answer || "", sources: ev.sources || [], findings: ev.key_findings || [], expertise: ev.expertise || "", questionFocus: ev.question_focus || "", ts: ev.ts });
    var stormEmptyEl = document.getElementById("storm-empty");
    if (stormEmptyEl) stormEmptyEl.style.display = "none";
    markDirty("advanced");
  }

  // ---- Query event (BUG-002 fix: track query plan data from tracer.query()) ----
  if (evType === "query") {
    if (ev.query) {
      state.queries.push({
        engine: ev.engine || "planner",
        query: ev.query || "",
        resultCount: ev.result_count || 0,
        ts: ev.ts,
        urls: [],
        titles: [],
        snippets: [],
        scores: [],
        cached: false,
        fallback: false,
        exa_cost: 0
      });
    }
    markDirty("advanced");
  }

  // ---- G4: Smart Art Diagrams (BUG-007 fix: null check on ev.diagrams) ----
  if (evType === "smart_art") {
    if (ev.diagrams !== null && Array.isArray(ev.diagrams)) {
      var diagObj = {};
      ev.diagrams.forEach(function(d) {
        var key = d.type || d.title || ("diagram_" + Math.random().toString(36).substr(2, 6));
        diagObj[key] = d.mermaid_code || d.code || "";
      });
      state.smartArtDiagrams = diagObj;
    } else if (ev.diagrams !== null && typeof ev.diagrams === "object") {
      state.smartArtDiagrams = ev.diagrams;
    }
    markDirty("report");
  }

  // ---- Update UI ----
  updateMetrics();
  markDirty("advanced");

  // ---- Route to workspace (user mode) ----
  if (typeof workspaceProcessEvent === "function") {
    try { workspaceProcessEvent(ev); } catch(we) { console.warn("workspaceProcessEvent error:", we); }
  }

  // Campaign progress events (NOVA Campaign Map) (BUG-003 fix: try-catch wrapper)
  if (evType === "campaign_progress" || evType === "node_start" || evType === "node_end") {
    if (typeof processCampaignEvent === "function") {
      try { processCampaignEvent(ev); } catch(ce) { console.warn("processCampaignEvent error:", ce); }
    }
  }

  } catch(e) { console.error("processEvent error:", e, ev); }
}

function updateGateDot(id, passed) {
  var el = document.getElementById(id);
  if (el) el.className = "gate-dot " + (passed ? "pass" : "fail");
}
/* =====================================================================
   Metrics Update
   ===================================================================== */
function updateMetrics() {
  var srcCount = state.sources.size;
  var bibCount = state.bibliography.length > 0 ? state.bibliography.length : srcCount;
  var evCount = state.verifiedEvidence || state.evidence;
  setText("pm-evidence", evCount.toLocaleString());
  setText("pm-words", state.words.toLocaleString());
  setText("pm-cost", "$" + state.cost.toFixed(2));
  var faithEl = document.getElementById("pm-faith");
  if (state.faithfulness > 0 || state.verificationVerdicts.length > 0) {
    faithEl.textContent = (state.faithfulness * 100).toFixed(1) + "%";
    faithEl.className = "value " + (state.faithfulness >= 0.80 ? "good" : state.faithfulness >= 0.60 ? "warn" : "bad");
  } else {
    faithEl.textContent = "\u2014";
    faithEl.className = "value";
  }
  setText("event-counter", state.eventCount);
  setText("vector-id", state.vectorId);
  setText("total-cost", "$" + state.cost.toFixed(2));
  setText("badge-evidence", state.evidence);
  updateOperatorPanels();
}
