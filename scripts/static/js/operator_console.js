/* =====================================================================
   operator_console.js — Operator-mode specific: cost breakdown panel,
   quality metrics panel, audit trace export, model info updater,
   all updateOperator* functions
   ===================================================================== */

/* =====================================================================
   Operator View — Cost Breakdown Panel Renderer
   ===================================================================== */
function renderOpCostBreakdown() {
  var el = document.getElementById("op-cost-details");
  if (!el) return;

  // Empty state: no LLM calls yet
  if (!state.llmDetails || state.llmDetails.length === 0) {
    el.innerHTML = '<div style="text-align:center;padding:24px 12px;color:var(--text-tertiary)">' +
      '<div style="font-size:24px;margin-bottom:8px;opacity:0.5">$</div>' +
      '<div style="font-size:12px;font-weight:600">No cost data yet</div>' +
      '<div style="font-size:11px;margin-top:4px">Run a research query to see LLM cost breakdown</div>' +
      '</div>';
    return;
  }

  // Compute cost by category from llmDetails
  var categories = {};
  var CATEGORY_MAP = {
    "plan_queries": "Planning",
    "research_plan": "Planning",
    "outline": "Planning",
    "fallback_outline": "Planning",
    "search": "Search",
    "search_gap": "Search",
    "gap_queries": "Search",
    "citation_chase": "Search",
    "perspective_discovery": "Search",
    "interview_simulation": "STORM",
    "storm_interview": "STORM",
    "verification_batch": "Verification",
    "verify_claims": "Verification",
    "nli_verification": "Verification",
    "cross_source_verify": "Verification",
    "section_write": "Synthesis",
    "section_expand": "Synthesis",
    "cluster_plan": "Synthesis",
    "merge_themes": "Synthesis",
    "abstract_write": "Synthesis",
    "hallucination_rewrite": "Synthesis",
    "evidence_extraction": "Analysis",
    "analyze": "Analysis",
    "scoring": "Analysis",
    "evaluate": "Evaluation",
    "gap_analysis": "Evaluation",
    "quality_assessment": "Evaluation"
  };

  state.llmDetails.forEach(function(d) {
    var ct = d.call_type || d.type || "other";
    var cat = CATEGORY_MAP[ct] || "Other";
    if (!categories[cat]) categories[cat] = { cost: 0, calls: 0, inputTok: 0, outputTok: 0 };
    categories[cat].cost += (d.cost_usd || 0);
    categories[cat].calls += 1;
    categories[cat].inputTok += (d.input_tokens || d.prompt_tokens || 0);
    categories[cat].outputTok += (d.output_tokens || d.completion_tokens || 0);
  });

  var html = '';

  // Total cost header
  html += '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px">';
  html += '<span style="font-size:18px;font-weight:700;font-family:var(--font-mono);color:var(--text-primary)">$' + state.cost.toFixed(3) + '</span>';
  html += '<span style="font-size:10px;color:var(--text-tertiary)">' + state.llmCallCount + ' calls</span>';
  html += '</div>';

  // Category breakdown
  var catKeys = Object.keys(categories).sort(function(a, b) { return categories[b].cost - categories[a].cost; });
  if (catKeys.length > 0) {
    html += '<div class="cost-cat-grid">';
    catKeys.forEach(function(cat) {
      var c = categories[cat];
      html += '<div class="cost-cat-item">';
      html += '<span class="cost-cat-name">' + cat + ' <span style="color:var(--text-tertiary);font-size:9px">(' + c.calls + ')</span></span>';
      html += '<span class="cost-cat-val">$' + c.cost.toFixed(3) + '</span>';
      html += '</div>';
    });
    html += '</div>';
  }

  // Token usage
  html += '<div style="margin-top:8px;border-top:1px solid var(--border);padding-top:6px">';
  html += '<div class="cost-token-row"><span>Input tokens</span><span class="cost-token-val">' + formatTokens(state.llmInputTokens) + '</span></div>';
  html += '<div class="cost-token-row"><span>Output tokens</span><span class="cost-token-val">' + formatTokens(state.llmOutputTokens) + '</span></div>';
  var totalTok = state.llmInputTokens + state.llmOutputTokens;
  html += '<div class="cost-token-row"><span>Total tokens</span><span class="cost-token-val">' + formatTokens(totalTok) + '</span></div>';
  if (totalTok > 0) {
    var costPerMTok = (state.cost / (totalTok / 1000000)).toFixed(2);
    html += '<div class="cost-token-row"><span>Avg $/MTok</span><span class="cost-token-val">$' + costPerMTok + '</span></div>';
  }
  html += '</div>';

  el.innerHTML = html;
}

/* =====================================================================
   Operator View — Quality Metrics Panel Renderer
   ===================================================================== */
function renderOpQualityMetrics() {
  var el = document.getElementById("op-quality-details");
  if (!el) return;

  // Empty state: no evidence or verification data
  if (state.evidence === 0 && state.verificationVerdicts.length === 0) {
    el.innerHTML = '<div style="text-align:center;padding:24px 12px;color:var(--text-tertiary)">' +
      '<div style="font-size:24px;margin-bottom:8px;opacity:0.5">&#9733;</div>' +
      '<div style="font-size:12px;font-weight:600">No quality data yet</div>' +
      '<div style="font-size:11px;margin-top:4px">Quality metrics appear once evidence is collected and verified</div>' +
      '</div>';
    return;
  }

  var html = '';

  // Faithfulness with trend
  var faithPct = state.faithfulness * 100;
  var faithClass = faithPct >= 80 ? "good" : faithPct >= 60 ? "warn" : faithPct > 0 ? "bad" : "";
  html += '<div class="qm-faith-row">';
  html += '<span class="qm-faith-pct ' + faithClass + '">' + (faithPct > 0 ? faithPct.toFixed(1) + '%' : '--') + '</span>';

  // Compute trend from gateHistory faithfulness entries
  var faithEntries = state.gateHistory.filter(function(g) {
    return g.gate === "faithfulness" && g.actual !== undefined;
  });
  if (faithEntries.length >= 2) {
    var prev = faithEntries[faithEntries.length - 2].actual * 100;
    var curr = faithEntries[faithEntries.length - 1].actual * 100;
    var delta = curr - prev;
    var trendClass = delta > 0.5 ? "up" : delta < -0.5 ? "down" : "flat";
    var arrow = delta > 0.5 ? "+" : delta < -0.5 ? "" : "";
    html += '<span class="qm-trend ' + trendClass + '">' + arrow + delta.toFixed(1) + 'pp</span>';
  }
  html += '<span style="font-size:10px;color:var(--text-tertiary);margin-left:auto">Faithfulness</span>';
  html += '</div>';

  // Evidence tier distribution bar
  var gT = state.tierCounts.gold || 0;
  var sT = state.tierCounts.silver || 0;
  var bT = state.tierCounts.bronze || 0;
  var totalTier = gT + sT + bT;
  if (totalTier > 0) {
    var gP = Math.round((gT / totalTier) * 100);
    var sP = Math.round((sT / totalTier) * 100);
    var bP = 100 - gP - sP;
    html += '<div class="qm-tier-bar">';
    html += '<div class="qm-tier-seg gold" style="width:' + gP + '%"></div>';
    html += '<div class="qm-tier-seg silver" style="width:' + sP + '%"></div>';
    html += '<div class="qm-tier-seg bronze" style="width:' + bP + '%"></div>';
    html += '</div>';
    html += '<div class="qm-tier-labels">';
    html += '<span>GOLD ' + gT + '</span><span>SILVER ' + sT + '</span><span>BRONZE ' + bT + '</span>';
    html += '</div>';
  }

  // Citation density
  var citDensity = 0;
  if (state.words > 0 && state.citations > 0) {
    citDensity = (state.citations / state.words * 1000).toFixed(1);
  }
  html += '<div style="margin-top:8px;border-top:1px solid var(--border);padding-top:6px">';
  html += '<div class="qm-stat-row"><span>Citation density</span><span class="qm-stat-val">' + citDensity + ' / 1K words</span></div>';

  // Source diversity
  var srcCount = state.sources.size || 0;
  html += '<div class="qm-stat-row"><span>Unique domains</span><span class="qm-stat-val">' + srcCount + '</span></div>';

  // Verified evidence
  var verEvCount = state.verifiedEvidence || 0;
  html += '<div class="qm-stat-row"><span>Verified evidence</span><span class="qm-stat-val">' + verEvCount + '</span></div>';

  // Verification verdicts breakdown
  var verTotal = state.verificationVerdicts.length;
  if (verTotal > 0) {
    var supported = state.verificationVerdicts.filter(function(v) { return v.verdict === "SUPPORTED" || v.is_faithful; }).length;
    var notSupported = state.verificationVerdicts.filter(function(v) { return v.verdict === "NOT_SUPPORTED" || (v.is_faithful === false && v.verdict !== "PARTIAL"); }).length;
    html += '<div class="qm-stat-row"><span>Verdicts (S/NS)</span><span class="qm-stat-val">' + supported + ' / ' + notSupported + '</span></div>';
  }

  // Iteration count
  html += '<div class="qm-stat-row"><span>Iterations</span><span class="qm-stat-val">' + (state.iteration || state.gateHistory.length || 0) + '</span></div>';
  html += '</div>';

  el.innerHTML = html;
}

/* =====================================================================
   Operator View — Audit Trace Export
   ===================================================================== */
function exportAuditTrace() {
  var auditData = {
    export_type: "polaris_audit_trace",
    exported_at: new Date().toISOString(),
    vector_id: state.vectorId,
    query: state.researchQuery,
    started_at: state.startTime,
    pipeline_complete: state.pipelineComplete,
    summary: {
      total_events: state.eventCount,
      evidence_count: state.evidence,
      verified_evidence: state.verifiedEvidence,
      faithfulness: state.faithfulness,
      total_words: state.words,
      total_citations: state.citations,
      unique_sources: state.sources.size,
      total_cost_usd: state.cost,
      iterations: state.iteration || state.gateHistory.length || 0,
      llm_calls: state.llmCallCount,
      input_tokens: state.llmInputTokens,
      output_tokens: state.llmOutputTokens
    },
    tier_counts: state.tierCounts,
    model_distribution: state.modelCounts,
    quality_gates: state.gates,
    gate_history: state.gateHistory,
    verification_verdicts: state.verificationVerdicts,
    hallucination_audit: state.hallucinationAudit,
    evidence_conflicts: state.evidenceConflicts,
    gap_analysis: state.gapAnalysis,
    expansion_passes: state.expansionPasses,
    bibliography: state.bibliography,
    trace_events: state.traceEvents,
    queries: state.queries,
    fetches: state.fetches.map(function(f) {
      return { url: f.url, domain: f.domain, status: f.status, content_len: f.contentLen, method: f.method };
    }),
    storm_personas: state.stormPersonas,
    nli_summary: state.nliSummary,
    anomalies: state.anomalies
  };
  var blob = new Blob([JSON.stringify(auditData, null, 2)], { type: "application/json" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = "polaris_audit_" + (state.vectorId || "unknown") + "_" + new Date().toISOString().replace(/[:.]/g, "-").substring(0, 19) + ".json";
  a.click();
  URL.revokeObjectURL(url);
  showToast("Audit trace exported (" + state.eventCount + " events)");
}

/* =====================================================================
   Operator View — Model Info Updater
   ===================================================================== */
function updateModelInfo() {
  var modelKeys = Object.keys(state.modelCounts);
  if (modelKeys.length === 0) return;

  // Find the most frequently used model
  var primaryModel = modelKeys.reduce(function(best, m) {
    return state.modelCounts[m] > (state.modelCounts[best] || 0) ? m : best;
  }, modelKeys[0]);

  var el = document.getElementById("model-info-text");
  if (el) {
    // Shorten model name for display
    var shortName = primaryModel;
    if (shortName.length > 25) {
      // Try to extract just the model name part
      var parts = shortName.split("/");
      shortName = parts[parts.length - 1];
      if (shortName.length > 25) shortName = shortName.substring(0, 22) + "...";
    }
    el.textContent = shortName;
    el.title = primaryModel + " (" + state.modelCounts[primaryModel] + " calls)";
  }
}

/* =====================================================================
   Operator View — Metadata Charts (A5.4: evidence distribution,
   source type breakdown, search engine distribution)
   ===================================================================== */
function renderOpMetadataCharts() {
  var el = document.getElementById("op-metadata-charts");
  if (!el) return;

  // Empty state: no data yet
  var hasEvidence = (state.tierCounts.gold + state.tierCounts.silver + state.tierCounts.bronze) > 0;
  var hasFetches = state.fetches && state.fetches.length > 0;
  var hasEngines = state.engineCounts && Object.keys(state.engineCounts).length > 0;

  if (!hasEvidence && !hasFetches && !hasEngines) {
    el.innerHTML = '<div style="text-align:center;padding:24px 12px;color:var(--text-tertiary)">' +
      '<div style="font-size:24px;margin-bottom:8px;opacity:0.5">&#9776;</div>' +
      '<div style="font-size:12px;font-weight:600">No metadata yet</div>' +
      '<div style="font-size:11px;margin-top:4px">Source and evidence charts appear during research</div>' +
      '</div>';
    return;
  }

  var html = '';

  // --- Evidence Tier Distribution (CSS donut) ---
  if (hasEvidence) {
    var gT = state.tierCounts.gold || 0;
    var sT = state.tierCounts.silver || 0;
    var bT = state.tierCounts.bronze || 0;
    var total = gT + sT + bT;
    var gPct = Math.round((gT / total) * 100);
    var sPct = Math.round((sT / total) * 100);
    var bPct = 100 - gPct - sPct;

    html += '<div class="op-chart-section">';
    html += '<div class="op-chart-title">Evidence Tier Distribution</div>';
    html += '<div style="display:flex;align-items:center;gap:16px">';

    // CSS conic-gradient donut
    html += '<div style="width:72px;height:72px;border-radius:50%;' +
      'background:conic-gradient(' +
      'var(--gold) 0% ' + gPct + '%,' +
      'var(--silver) ' + gPct + '% ' + (gPct + sPct) + '%,' +
      'var(--bronze) ' + (gPct + sPct) + '% 100%);' +
      'position:relative;flex-shrink:0">' +
      '<div style="position:absolute;inset:18px;border-radius:50%;background:var(--bg-elevated)"></div>' +
      '<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;' +
      'font-size:12px;font-weight:800;font-family:var(--font-mono);color:var(--text-primary)">' + total + '</div>' +
      '</div>';

    // Legend
    html += '<div style="display:flex;flex-direction:column;gap:3px;font-size:11px">';
    html += '<div style="display:flex;align-items:center;gap:6px">' +
      '<span style="width:8px;height:8px;border-radius:2px;background:var(--gold);flex-shrink:0"></span>' +
      '<span>GOLD</span><span style="font-family:var(--font-mono);font-weight:700;margin-left:auto">' + gT + ' (' + gPct + '%)</span></div>';
    html += '<div style="display:flex;align-items:center;gap:6px">' +
      '<span style="width:8px;height:8px;border-radius:2px;background:var(--silver);flex-shrink:0"></span>' +
      '<span>SILVER</span><span style="font-family:var(--font-mono);font-weight:700;margin-left:auto">' + sT + ' (' + sPct + '%)</span></div>';
    html += '<div style="display:flex;align-items:center;gap:6px">' +
      '<span style="width:8px;height:8px;border-radius:2px;background:var(--bronze);flex-shrink:0"></span>' +
      '<span>BRONZE</span><span style="font-family:var(--font-mono);font-weight:700;margin-left:auto">' + bT + ' (' + bPct + '%)</span></div>';
    html += '</div>';

    html += '</div>';
    html += '</div>';
  }

  // --- Source Domain Bar Chart (top 8 domains) ---
  if (hasFetches) {
    var domainCounts = {};
    state.fetches.forEach(function(f) {
      var dom = f.domain || "unknown";
      domainCounts[dom] = (domainCounts[dom] || 0) + 1;
    });
    var domainArr = Object.keys(domainCounts).map(function(d) {
      return { domain: d, count: domainCounts[d] };
    }).sort(function(a, b) { return b.count - a.count; });
    var topDomains = domainArr.slice(0, 8);
    var maxCount = topDomains.length > 0 ? topDomains[0].count : 1;

    html += '<div class="op-chart-section" style="margin-top:12px">';
    html += '<div class="op-chart-title">Top Source Domains</div>';
    topDomains.forEach(function(d) {
      var pct = (d.count / maxCount) * 100;
      html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px">';
      html += '<span style="font-size:10px;font-family:var(--font-mono);color:var(--text-secondary);' +
        'min-width:110px;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:right" ' +
        'title="' + d.domain + '">' + d.domain + '</span>';
      html += '<div style="flex:1;height:12px;background:var(--bg-inset);border-radius:3px;overflow:hidden">' +
        '<div style="height:100%;width:' + pct.toFixed(1) + '%;background:var(--accent);border-radius:3px;min-width:2px"></div></div>';
      html += '<span style="font-size:9px;font-family:var(--font-mono);color:var(--text-tertiary);min-width:24px;text-align:right">' + d.count + '</span>';
      html += '</div>';
    });
    html += '</div>';
  }

  // --- Search Engine Distribution (from engineCounts) ---
  if (hasEngines) {
    var engines = Object.keys(state.engineCounts);
    var totalEngineResults = 0;
    engines.forEach(function(e) { totalEngineResults += state.engineCounts[e]; });

    if (totalEngineResults > 0) {
      html += '<div class="op-chart-section" style="margin-top:12px">';
      html += '<div class="op-chart-title">Search Engine Results</div>';
      html += '<div style="display:flex;gap:8px;flex-wrap:wrap">';
      var ENGINE_COLORS = {
        "serper": "var(--success)", "semantic_scholar": "var(--info)", "exa": "var(--warning)",
        "duckduckgo": "var(--accent)", "tavily": "rgba(167,139,250,0.8)", "openalex": "rgba(244,114,182,0.8)"
      };
      engines.sort(function(a, b) { return state.engineCounts[b] - state.engineCounts[a]; });
      engines.forEach(function(e) {
        var cnt = state.engineCounts[e];
        var pct = Math.round((cnt / totalEngineResults) * 100);
        var color = ENGINE_COLORS[e.toLowerCase()] || "var(--text-secondary)";
        html += '<div style="display:flex;align-items:center;gap:4px;padding:3px 8px;' +
          'background:var(--bg-inset);border-radius:var(--radius-sm);font-size:10px">';
        html += '<span style="width:6px;height:6px;border-radius:50%;background:' + color + ';flex-shrink:0"></span>';
        html += '<span style="font-weight:600">' + e + '</span>';
        html += '<span style="font-family:var(--font-mono);color:var(--text-tertiary)">' + cnt + ' (' + pct + '%)</span>';
        html += '</div>';
      });
      html += '</div>';
      html += '</div>';
    }
  }

  el.innerHTML = html;
}

/* =====================================================================
   Operator View — Update all operator panels (called from updateMetrics)
   ===================================================================== */
function updateOperatorPanels() {
  // Only render if in operator mode (avoid wasted work in user mode)
  if (_currentViewMode !== "operator") return;

  renderOpCostBreakdown();
  renderOpQualityMetrics();
  renderOpMetadataCharts();
  updateModelInfo();
}
