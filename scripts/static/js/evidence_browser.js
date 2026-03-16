/* =====================================================================
   evidence_browser.js — Evidence card rendering, tier filtering, sorting,
   detail panel, radar chart, evidence search, graph node click handler
   ===================================================================== */

/* =====================================================================
   EVIDENCE VIEW — Graph + Cards + Detail Panel
   ===================================================================== */
function renderEvidenceView() {
  renderEvidenceGraph();
  renderEvidenceCards();
}

function renderEvidenceGraph() {
  var canvas = document.getElementById("graph-svg");
  var emptyEl = document.getElementById("graph-empty");
  if (!canvas) return;

  var mode = state.graphMode || "crossref";
  if (mode === "crossref") {
    buildCrossRefGraph(canvas, emptyEl);
  } else if (mode === "citation") {
    buildCitationMapGraph(canvas, emptyEl);
  } else if (mode === "source") {
    buildSourceNetGraph(canvas, emptyEl);
  } else if (mode === "mindmap") {
    if (typeof buildMindMapGraph === "function") {
      buildMindMapGraph(canvas, emptyEl);
    } else {
      canvas.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="var(--text-tertiary)" font-size="13">Mind Map: loading module...</text>';
    }
  }
}

/* Tier filter chip click handler */
function setTierFilter(tier) {
  var chips = document.querySelectorAll("#tier-chips .filter-chip");
  chips.forEach(function(c) {
    var isActive = c.dataset.tier === tier;
    c.classList.toggle("active", isActive);
    c.setAttribute("aria-checked", isActive ? "true" : "false");
  });
  renderEvidenceCards();
}

/* Evidence cards (below graph) */
function renderEvidenceCards() {
  var isUser = _currentViewMode === "user";
  var activeTier = document.querySelector("#tier-chips .filter-chip.active");
  var tierFilter = activeTier ? activeTier.dataset.tier : "all";
  var items = state.evidenceDetails.slice();
  if (tierFilter !== "all") items = items.filter(function(p) { return (p.tier || "").toLowerCase() === tierFilter; });
  var sortField = state.scoringSortField || "composite";
  var sortKeyMap = { composite: "composite", authority: "sig_authority", freshness: "sig_freshness", density: "sig_density", grounding: "sig_grounding" };
  var sortKey = sortKeyMap[sortField] || "composite";
  items.sort(function(a, b) {
    var sa = state.scoringDetail.find(function(s) { return s.id === a.id; });
    var sb = state.scoringDetail.find(function(s) { return s.id === b.id; });
    return ((sb ? sb[sortKey] : 0) || 0) - ((sa ? sa[sortKey] : 0) || 0);
  });
  items = items.slice(0, 100);
  var el = document.getElementById("evidence-card-list");
  if (!el) return;
  if (!items.length) { el.innerHTML = '<div class="empty-state">Evidence cards will appear during analysis...</div>'; return; }

  // In user mode, group evidence by section
  if (isUser && state.sectionEvidenceMap && state.sectionEvidenceMap.length) {
    var grouped = {};
    var ungrouped = [];
    state.sectionEvidenceMap.forEach(function(sem) {
      var sectionTitle = sem.section || sem.section_id || "General";
      if (!grouped[sectionTitle]) grouped[sectionTitle] = [];
      (sem.evidence_ids || []).forEach(function(eid) {
        var ev = items.find(function(p) { return p.id === eid; });
        if (ev) grouped[sectionTitle].push(ev);
      });
    });
    // Find ungrouped items
    var groupedIds = new Set();
    Object.values(grouped).forEach(function(arr) { arr.forEach(function(ev) { groupedIds.add(ev.id); }); });
    items.forEach(function(p) { if (!groupedIds.has(p.id)) ungrouped.push(p); });
    if (ungrouped.length) grouped["Other Evidence"] = ungrouped;

    var allHtml = '';
    Object.keys(grouped).forEach(function(section) {
      var sectionItems = grouped[section];
      if (!sectionItems.length) return;
      allHtml += '<div style="margin-bottom:12px"><div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px">' + esc(section) + '</div>';
      allHtml += sectionItems.map(function(p) { return renderEvidenceCardItem(p, true); }).join("");
      allHtml += '</div>';
    });
    el.innerHTML = allHtml;
  } else {
    el.innerHTML = items.map(function(p) { return renderEvidenceCardItem(p, isUser); }).join("");
  }
}

function renderEvidenceCardItem(p, isUser) {
  var tierCls = (p.tier || "bronze").toLowerCase();
  var scoring = state.scoringDetail.find(function(s) { return s.id === p.id || s.evidence_id === p.id; });
  var domain = extractDomain(p.source_url || "");
  var faviconUrl = domain ? 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(domain) + '&sz=16' : '';
  var html = '<div class="ev-card" tabindex="0" role="button" onclick="selectEvidenceFromCard(\'' + esc(p.id || "") + '\')" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){this.click();event.preventDefault();}">';
  html += '<div style="display:flex;gap:6px;align-items:center;margin-bottom:4px">';

  if (isUser) {
    // User mode: plain-language confidence labels with domain favicon
    var confLabel = tierCls === "gold" ? "High confidence" : tierCls === "silver" ? "Medium confidence" : "Supporting";
    var confColor = tierCls === "gold" ? "var(--success)" : tierCls === "silver" ? "var(--info)" : "var(--text-tertiary)";
    html += '<span style="font-size:10px;font-weight:600;color:' + confColor + '">' + confLabel + '</span>';
    if (faviconUrl) {
      html += '<span style="display:inline-flex;align-items:center;gap:3px;margin-left:auto;font-size:10px;color:var(--text-secondary)">';
      html += '<img src="' + esc(faviconUrl) + '" width="12" height="12" style="border-radius:2px" alt="" loading="lazy" onerror="this.style.display=\'none\'">';
      html += esc(domain) + '</span>';
    } else {
      html += '<span style="margin-left:auto;font-size:10px;color:var(--text-tertiary)">' + esc(domain) + '</span>';
    }
  } else {
    // Operator mode: full technical details
    html += '<span class="tier-badge ' + tierCls + '">' + esc((p.tier || "?").toUpperCase()) + '</span>';
    if (scoring) html += '<span style="font-size:10px;font-family:var(--font-mono);color:var(--text-primary);font-weight:600">' + (scoring.composite || 0).toFixed(3) + '</span>';
    if (p.perspective) html += '<span style="font-size:10px;color:var(--info)">' + esc(p.perspective) + '</span>';
    html += '<span style="margin-left:auto;font-size:10px;color:var(--text-tertiary)">' + esc(domain) + '</span>';
  }

  html += '</div>';
  if (p.statement) html += '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:4px">' + esc(truncStr(p.statement, 150)) + '</div>';
  if (p.quote) html += '<div style="font-size:11px;color:var(--text-tertiary);border-left:2px solid var(--border);padding-left:8px;font-style:italic">' + esc(truncStr(p.quote, 100)) + '</div>';
  html += '</div>';
  return html;
}

function selectEvidenceFromCard(evidenceId) {
  var idx = state.graphNodes.findIndex(function(n) { return n.id === evidenceId; });
  if (idx >= 0) selectEvidenceNode(idx);
  else {
    // Build detail from evidenceDetails directly
    var ev = state.evidenceDetails.find(function(e) { return e.id === evidenceId; });
    if (ev) {
      var fakeNode = { id: ev.id, tier: ev.tier || "BRONZE", perspective: ev.perspective || "", statement: ev.statement || "", source_url: ev.source_url || "",
        relevance: ev.relevance || 0, authority: 0, composite: 0, freshness: 0 };
      state.graphNodes.push(fakeNode);
      selectEvidenceNode(state.graphNodes.length - 1);
    }
  }
}

/* --- Graph node click handler (THE FIX) --- */
function selectEvidenceNode(idx) {
  var n = state.graphNodes[idx];
  if (!n) return;
  state.selectedEvidenceIdx = idx;
  var panel = document.getElementById("evidence-detail-panel");
  var body = document.getElementById("detail-panel-body");
  panel.classList.add("open");

  var scoring = state.scoringDetail.find(function(s) { return s.id === n.id || s.evidence_id === n.id; });
  var verdict = state.verificationVerdicts.find(function(v) { return v.evidence_id === n.id; });
  // Find which sections cite this
  var citedIn = [];
  state.sectionEvidenceMap.forEach(function(m) {
    if ((m.evidence_ids || []).indexOf(n.id) >= 0) citedIn.push(m.section_id || "?");
  });
  // Find cross-ref groups
  var groups = [];
  state.crossRefGroups.forEach(function(g, gi) {
    if ((g.evidence_ids || []).indexOf(n.id) >= 0) groups.push({ idx: gi + 1, similarity: g.similarity || 0 });
  });

  var html = '';
  html += '<div style="margin-bottom:var(--md)"><span class="tier-badge ' + (n.tier || "bronze").toLowerCase() + '">' + esc((n.tier || "?").toUpperCase()) + '</span>';
  if (n.perspective) html += ' <span style="font-size:11px;color:var(--info)">' + esc(n.perspective) + '</span>';
  html += '</div>';

  html += '<div style="font-size:13px;color:var(--text-primary);margin-bottom:var(--md);line-height:1.5">' + esc(n.statement) + '</div>';

  // Source URL
  if (n.source_url) html += '<div style="margin-bottom:var(--md)"><a href="' + esc(n.source_url) + '" target="_blank" style="font-size:12px;word-break:break-all">' + esc(n.source_url) + '</a></div>';

  // Source quote (direct_quote)
  var sourceQuote = n.quote || n.direct_quote || "";
  if (!sourceQuote) {
    var evDetail = state.evidenceDetails.find(function(e) { return e.id === n.id; });
    if (evDetail) sourceQuote = evDetail.quote || evDetail.direct_quote || "";
  }
  if (sourceQuote) {
    html += '<div class="section-title" style="margin-top:var(--md)">Source Quote</div>';
    html += '<div style="font-size:12px;color:var(--text-secondary);border-left:3px solid var(--accent);padding:8px 12px;background:var(--bg-inset);border-radius:0 var(--radius-sm) var(--radius-sm) 0;font-style:italic;line-height:1.5;margin-bottom:var(--sm)">' + esc(sourceQuote) + '</div>';
  }


  // 5-signal scores with radar chart
  if (scoring) {
    html += '<div class="section-title" style="margin-top:var(--md)">5-Signal Scores</div>';
    var sigs = [
      { name: "Relevance", key: "sig_relevance", color: "#3b82f6" },
      { name: "Authority", key: "sig_authority", color: "#a78bfa" },
      { name: "Density", key: "sig_density", color: "#10b981" },
      { name: "Freshness", key: "sig_freshness", color: "#f59e0b" },
      { name: "Grounding", key: "sig_grounding", color: "#20c8d8" }
    ];

    // SVG Radar chart
    var cx = 80, cy = 80, r = 60, n5 = 5;
    var radarSvg = '<svg role="img" aria-label="5-signal radar chart for this evidence" width="160" height="175" viewBox="0 0 160 175" style="display:block;margin:0 auto var(--sm)">';
    // Grid rings
    [0.25, 0.5, 0.75, 1.0].forEach(function(ring) {
      var pts = [];
      for (var i = 0; i < n5; i++) {
        var angle = (Math.PI * 2 / n5) * i - Math.PI / 2;
        pts.push((cx + r * ring * Math.cos(angle)).toFixed(1) + "," + (cy + r * ring * Math.sin(angle)).toFixed(1));
      }
      radarSvg += '<polygon points="' + pts.join(" ") + '" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>';
    });
    // Axis lines
    for (var i = 0; i < n5; i++) {
      var angle = (Math.PI * 2 / n5) * i - Math.PI / 2;
      radarSvg += '<line x1="' + cx + '" y1="' + cy + '" x2="' + (cx + r * Math.cos(angle)).toFixed(1) + '" y2="' + (cy + r * Math.sin(angle)).toFixed(1) + '" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>';
    }
    // Data polygon
    var dataPts = [];
    sigs.forEach(function(s, i) {
      var val = scoring[s.key] || 0;
      var angle = (Math.PI * 2 / n5) * i - Math.PI / 2;
      dataPts.push((cx + r * val * Math.cos(angle)).toFixed(1) + "," + (cy + r * val * Math.sin(angle)).toFixed(1));
    });
    radarSvg += '<polygon points="' + dataPts.join(" ") + '" fill="rgba(56,189,248,0.2)" stroke="#38bdf8" stroke-width="2"/>';
    // Data points + labels
    sigs.forEach(function(s, i) {
      var val = scoring[s.key] || 0;
      var angle = (Math.PI * 2 / n5) * i - Math.PI / 2;
      var px = cx + r * val * Math.cos(angle);
      var py = cy + r * val * Math.sin(angle);
      radarSvg += '<circle cx="' + px.toFixed(1) + '" cy="' + py.toFixed(1) + '" r="3" fill="' + s.color + '"/>';
      // Labels
      var lx = cx + (r + 14) * Math.cos(angle);
      var ly = cy + (r + 14) * Math.sin(angle);
      var anchor = i === 0 ? "middle" : (Math.cos(angle) > 0.1 ? "start" : Math.cos(angle) < -0.1 ? "end" : "middle");
      radarSvg += '<text x="' + lx.toFixed(1) + '" y="' + (ly + 3).toFixed(1) + '" fill="' + s.color + '" font-size="9" font-family="Inter,sans-serif" text-anchor="' + anchor + '">' + s.name.substring(0, 3) + '</text>';
    });
    radarSvg += '</svg>';
    html += radarSvg;

    // Bar fallback (always shown alongside)
    sigs.forEach(function(s) {
      var val = scoring[s.key] || 0;
      html += '<div class="signal-bar-row"><span class="signal-bar-label">' + s.name.substring(0, 4) + '</span>' +
        '<div class="signal-bar-track"><div class="signal-bar-fill" style="width:' + (val * 100).toFixed(0) + '%;background:' + s.color + '"></div></div>' +
        '<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-secondary);min-width:35px;text-align:right">' + val.toFixed(3) + '</span></div>';
    });
    html += '<div style="font-size:11px;font-family:var(--font-mono);color:var(--text-primary);margin-top:4px;font-weight:600">Composite: ' + (scoring.composite || 0).toFixed(4) + '</div>';
    if (scoring.veto_reason) html += '<div style="font-size:11px;color:var(--error);margin-top:2px">Veto: ' + esc(scoring.veto_reason) + '</div>';
  }

  // Verification verdict (enhanced: fallback to is_faithful on evidence data)
  var evidenceData = state.evidenceDetails.find(function(e) { return e.id === n.id; });
  var effectiveVerdict = verdict;
  if (!effectiveVerdict && evidenceData && evidenceData.is_faithful !== undefined) {
    effectiveVerdict = { verdict: evidenceData.is_faithful ? "SUPPORTED" : "NOT_SUPPORTED", faithful: evidenceData.is_faithful, reasoning: "" };
  }
  if (effectiveVerdict) {
    html += '<div class="section-title" style="margin-top:var(--md)">Verification</div>';
    var isSupported = effectiveVerdict.faithful || effectiveVerdict.is_faithful || effectiveVerdict.verdict === "SUPPORTED";
    var vColor = isSupported ? "var(--success)" : "var(--error)";
    var vBg = isSupported ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)";
    var vBorder = isSupported ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)";
    var verdictLabel = effectiveVerdict.verdict || (isSupported ? "SUPPORTED" : "NOT_SUPPORTED");
    html += '<div style="display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:var(--radius-sm);background:' + vBg + ';border:1px solid ' + vBorder + ';margin-bottom:var(--sm)">';
    html += '<span style="width:8px;height:8px;border-radius:50%;background:' + vColor + ';display:inline-block"></span>';
    html += '<span style="font-size:12px;color:' + vColor + ';font-weight:600">' + esc(verdictLabel) + '</span>';
    html += '</div>';
    if (effectiveVerdict.reasoning) html += '<div style="font-size:11px;color:var(--text-tertiary);margin-top:4px">' + esc(truncStr(effectiveVerdict.reasoning, 300)) + '</div>';
  }

  // Cited in sections
  if (citedIn.length) {
    html += '<div class="section-title" style="margin-top:var(--md)">Cited In Sections</div>';
    html += '<div style="display:flex;gap:4px;flex-wrap:wrap">';
    citedIn.forEach(function(s) { html += '<span style="padding:2px 6px;font-size:10px;background:var(--accent-dim);border:1px solid var(--border);border-radius:4px;color:var(--accent)">' + esc(s) + '</span>'; });
    html += '</div>';
  }

  // Cross-ref groups
  if (groups.length) {
    html += '<div class="section-title" style="margin-top:var(--md)">Cross-Reference Groups</div>';
    groups.forEach(function(g) {
      html += '<div style="font-size:11px;color:var(--text-secondary)">Group ' + g.idx + ': ' + (g.similarity * 100).toFixed(0) + '% agreement</div>';
    });
  }

  // Cross-references: other evidence from the same source URL
  if (n.source_url) {
    var sameSourceEvidence = state.evidenceDetails.filter(function(e) {
      return e.source_url === n.source_url && e.id !== n.id;
    });
    if (sameSourceEvidence.length) {
      html += '<div class="section-title" style="margin-top:var(--md)">Cross-References (Same Source: ' + esc(extractDomain(n.source_url)) + ')</div>';
      html += '<div style="max-height:200px;overflow-y:auto">';
      sameSourceEvidence.slice(0, 10).forEach(function(ref) {
        var refVerdict = state.verificationVerdicts.find(function(v) { return v.evidence_id === ref.id; });
        var refVerdictText = refVerdict ? (refVerdict.verdict || (refVerdict.faithful || refVerdict.is_faithful ? "SUPPORTED" : "NOT_SUPPORTED")) : "";
        var refVerdictColor = (refVerdictText === "SUPPORTED") ? "var(--success)" : (refVerdictText === "NOT_SUPPORTED" ? "var(--error)" : "var(--text-tertiary)");
        html += '<div style="padding:6px 8px;margin-bottom:4px;background:var(--bg-inset);border-radius:var(--radius-sm);border:1px solid var(--border);cursor:pointer" role="button" tabindex="0" onclick="selectEvidenceFromCard(\'' + esc(ref.id || "") + '\')" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){selectEvidenceFromCard(\'' + esc(ref.id || "") + '\');event.preventDefault();}">';
        html += '<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">';
        html += '<span class="tier-badge ' + (ref.tier || "bronze").toLowerCase() + '" style="font-size:9px;padding:1px 5px">' + esc((ref.tier || "?").toUpperCase()) + '</span>';
        if (refVerdictText) html += '<span style="font-size:10px;font-weight:600;color:' + refVerdictColor + '">' + esc(refVerdictText) + '</span>';
        html += '</div>';
        html += '<div style="font-size:11px;color:var(--text-secondary)">' + esc(truncStr(ref.statement || "", 120)) + '</div>';
        html += '</div>';
      });
      if (sameSourceEvidence.length > 10) {
        html += '<div style="font-size:10px;color:var(--text-tertiary);text-align:center;padding:4px">...and ' + (sameSourceEvidence.length - 10) + ' more from this source</div>';
      }
      html += '</div>';
    }
  }


  body.innerHTML = html;
}

function closeDetailPanel() {
  document.getElementById("evidence-detail-panel").classList.remove("open");
  state.selectedEvidenceIdx = -1;
  // Re-render graph after panel close to fix dimensions (especially on mobile fullscreen overlay)
  setTimeout(function() { renderEvidenceGraph(); }, 400);
}

function showGraphTooltip(event, idx) {
  var n = state.graphNodes[idx];
  if (!n) return;
  var tip = document.getElementById("graph-tooltip");
  tip.innerHTML = '<div style="margin-bottom:4px"><span class="tier-badge ' + (n.tier || "bronze").toLowerCase() + '">' + esc((n.tier || "?").toUpperCase()) + '</span>' +
    (n.perspective ? ' <span style="color:var(--info);font-size:10px">' + esc(n.perspective) + '</span>' : '') + '</div>' +
    '<div style="color:var(--text-primary);font-size:11px;margin-bottom:4px">' + esc(truncStr(n.statement, 150)) + '</div>' +
    '<div style="font-size:10px;color:var(--text-tertiary)">' + esc(truncStr(n.source_url, 50)) + '</div>' +
    '<div style="font-size:10px;color:var(--text-tertiary);margin-top:3px">Rel: ' + (n.relevance || 0).toFixed(2) + ' | Auth: ' + (n.authority || 0).toFixed(2) + ' | Comp: ' + (n.composite || 0).toFixed(3) + '</div>';
  tip.style.display = "block";
  var rect = event.target.ownerSVGElement.getBoundingClientRect();
  tip.style.left = Math.min(event.clientX - rect.left + 10, rect.width - 330) + "px";
  tip.style.top = (event.clientY - rect.top + 10) + "px";
}

function hideGraphTooltip() {
  var tip = document.getElementById("graph-tooltip");
  if (tip) tip.style.display = "none";
}
