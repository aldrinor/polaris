/* =====================================================================
   graph_viz.js — Graph visualization (buildCrossRefGraph, buildCitationMapGraph,
   buildSourceNetGraph), canvas/SVG rendering, zoom/pan, force simulation
   ===================================================================== */

function buildCrossRefGraph(canvas, emptyEl) {
  var crossRefGroups = state.crossRefGroups;
  var conflicts = state.evidenceConflicts;
  var evidenceDetails = state.evidenceDetails;
  var scoringDetail = state.scoringDetail;
  if ((!crossRefGroups || !crossRefGroups.length) && (!conflicts || !conflicts.length)) {
    if (emptyEl) emptyEl.style.display = "block";
    canvas.innerHTML = '';
    return;
  }
  if (emptyEl) emptyEl.style.display = "none";

  var nodeMap = {};
  var edges = [];
  var colorMode = (document.getElementById("graph-color-mode") || {}).value || "tier";
  var tierFilter = (document.getElementById("graph-tier-filter") || {}).value || "all";
  var minAgree = ((document.getElementById("graph-min-agree") || {}).value || 50) / 100;

  (evidenceDetails || []).forEach(function(ev) {
    if (!ev.id) return;
    if (tierFilter !== "all" && (ev.tier || "").toLowerCase() !== tierFilter) return;
    var scoring = (scoringDetail || []).find(function(s) { return s.id === ev.id || s.evidence_id === ev.id; });
    nodeMap[ev.id] = { id: ev.id, tier: ev.tier || "BRONZE", perspective: ev.perspective || "", statement: ev.statement || "", source_url: ev.source_url || "",
      relevance: scoring ? scoring.sig_relevance || 0 : ev.relevance || 0, authority: scoring ? scoring.sig_authority || 0 : 0,
      composite: scoring ? scoring.composite || 0 : 0, freshness: scoring ? scoring.sig_freshness || 0 : 0,
      x: Math.random() * 700 + 50, y: Math.random() * 400 + 50 };
  });

  (crossRefGroups || []).forEach(function(g) {
    var ids = g.evidence_ids || [];
    var score = g.similarity || g.agreement_score || 0;
    if (score < minAgree) return;
    for (var i = 0; i < ids.length; i++) for (var j = i + 1; j < ids.length; j++) {
      if (nodeMap[ids[i]] && nodeMap[ids[j]]) edges.push({ a: ids[i], b: ids[j], score: score, type: "agree" });
    }
  });

  (conflicts || []).forEach(function(c) {
    var idA = c.evidence_id_a || c.id_a, idB = c.evidence_id_b || c.id_b;
    if (idA && idB && nodeMap[idA] && nodeMap[idB]) edges.push({ a: idA, b: idB, score: c.score || 0, type: "conflict" });
  });

  var nodes = Object.values(nodeMap);
  if (!nodes.length) { canvas.innerHTML = ''; if (emptyEl) emptyEl.style.display = "block"; return; }

  // Force simulation (BUG-092: viewport-aware, prevents clustering at 1920px)
  var W = canvas.clientWidth || 800, H = canvas.clientHeight || 500;
  // Scale repulsion force with viewport area so nodes spread at any resolution
  var viewportScale = (W * H) / (800 * 500);
  var chargeStrength = 800 * viewportScale;
  // Minimum separation radius per node (collision force)
  var nodeRadius = 4 + 8; // base radius + max composite scaling
  var collisionRadius = nodeRadius * 2.5;
  // More iterations for larger node counts (min 60, max 150)
  var simIterations = Math.min(150, Math.max(60, nodes.length * 2));

  nodes.forEach(function(n) { n.x = Math.random() * (W - 100) + 50; n.y = Math.random() * (H - 100) + 50; });
  for (var iter = 0; iter < simIterations; iter++) {
    // Cooling factor: reduce force magnitude as simulation progresses
    var alpha = 1.0 - (iter / simIterations) * 0.7;

    // Charge repulsion (Coulomb-like)
    for (var i = 0; i < nodes.length; i++) for (var j = i + 1; j < nodes.length; j++) {
      var dx = nodes[j].x - nodes[i].x, dy = nodes[j].y - nodes[i].y;
      var dist = Math.sqrt(dx * dx + dy * dy) || 1;
      var force = alpha * chargeStrength / (dist * dist);
      var fx = (dx / dist) * force, fy = (dy / dist) * force;
      nodes[i].x -= fx; nodes[i].y -= fy; nodes[j].x += fx; nodes[j].y += fy;
    }

    // Collision force: prevent node overlap
    for (var i = 0; i < nodes.length; i++) for (var j = i + 1; j < nodes.length; j++) {
      var dx = nodes[j].x - nodes[i].x, dy = nodes[j].y - nodes[i].y;
      var dist = Math.sqrt(dx * dx + dy * dy) || 1;
      if (dist < collisionRadius) {
        var overlap = (collisionRadius - dist) / 2;
        var ox = (dx / dist) * overlap, oy = (dy / dist) * overlap;
        nodes[i].x -= ox; nodes[i].y -= oy; nodes[j].x += ox; nodes[j].y += oy;
      }
    }

    // Spring forces on edges (viewport-aware link distance)
    var linkDistScale = Math.sqrt(viewportScale);
    edges.forEach(function(e) {
      var na = nodeMap[e.a], nb = nodeMap[e.b];
      if (!na || !nb) return;
      var dx = nb.x - na.x, dy = nb.y - na.y;
      var springK = e.type === "agree" ? 0.02 * e.score * linkDistScale : -0.01 * linkDistScale;
      na.x += dx * springK * alpha; na.y += dy * springK * alpha;
      nb.x -= dx * springK * alpha; nb.y -= dy * springK * alpha;
    });

    // Boundary clamping
    nodes.forEach(function(n) { n.x = Math.max(20, Math.min(W - 20, n.x)); n.y = Math.max(20, Math.min(H - 20, n.y)); });
  }

  var perspColors = { regulatory:"#3b82f6", scientific:"#10b981", industry:"#f59e0b", environmental:"#22d3ee", economic:"#f472b6", public_health:"#a78bfa", consumer:"#fb923c", engineering:"#6366f1", policy:"#ec4899", technical:"#10b981", comparative:"#22d3ee" };
  var svg = '';
  edges.forEach(function(e) {
    var na = nodeMap[e.a], nb = nodeMap[e.b];
    if (!na || !nb) return;
    var color = e.type === "conflict" ? "var(--error)" : "rgba(16,185,129,0.12)";
    var dash = e.type === "conflict" ? ' stroke-dasharray="4,3"' : '';
    var width = e.type === "agree" ? Math.max(0.5, e.score * 2) : 1;
    svg += '<line x1="' + na.x.toFixed(1) + '" y1="' + na.y.toFixed(1) + '" x2="' + nb.x.toFixed(1) + '" y2="' + nb.y.toFixed(1) + '" stroke="' + color + '" stroke-width="' + width + '"' + dash + '/>';
  });
  nodes.forEach(function(n, idx) {
    var r = 4 + (n.composite || 0.3) * 8;
    var fill;
    if (colorMode === "perspective") fill = perspColors[(n.perspective || "").toLowerCase()] || "var(--text-tertiary)";
    else fill = n.tier === "GOLD" ? "var(--gold)" : n.tier === "SILVER" ? "var(--silver)" : "var(--bronze)";
    svg += '<circle cx="' + n.x.toFixed(1) + '" cy="' + n.y.toFixed(1) + '" r="' + r.toFixed(1) + '"' +
      ' fill="' + fill + '" fill-opacity="0.7" stroke="' + fill + '" stroke-width="1" style="cursor:pointer"' +
      ' onclick="selectEvidenceNode(' + idx + ')"' +
      ' onmouseenter="showGraphTooltip(event,' + idx + ')" onmouseleave="hideGraphTooltip()"/>';
  });
  canvas.innerHTML = svg;
  state.graphNodes = nodes;
  state.graphEdges = edges;
}

/* Citation Map: evidence nodes -> section nodes they're cited in */
function buildCitationMapGraph(canvas, emptyEl) {
  if (!state.sectionEvidenceMap.length || !state.evidenceDetails.length) {
    if (emptyEl) emptyEl.style.display = "block";
    canvas.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="var(--text-tertiary)" font-size="13">Citation Map: awaiting section-evidence mapping...</text>';
    return;
  }
  if (emptyEl) emptyEl.style.display = "none";
  var W = canvas.clientWidth || 800, H = canvas.clientHeight || 500;
  var sectionNodes = state.sectionEvidenceMap.map(function(m, i) {
    return { id: 'sec-' + i, label: m.section_id || ('S' + i), type: 'section', x: 80, y: 40 + i * (H - 80) / Math.max(state.sectionEvidenceMap.length - 1, 1), evidence_ids: m.evidence_ids || [] };
  });
  var evNodes = state.evidenceDetails.slice(0, 100).map(function(ev, i) {
    return { id: ev.id, label: truncStr(ev.statement || ev.id, 30), type: 'evidence', tier: ev.tier || 'BRONZE', x: W - 80, y: 20 + i * (H - 40) / 100 };
  });
  var svg = '';
  sectionNodes.forEach(function(sn) {
    svg += '<circle cx="' + sn.x + '" cy="' + sn.y.toFixed(1) + '" r="12" fill="var(--accent-dim)" stroke="var(--accent)" stroke-width="1.5"/>';
    svg += '<text x="' + (sn.x + 18) + '" y="' + (sn.y + 4).toFixed(1) + '" font-size="10" fill="var(--text-secondary)" font-family="Inter">' + esc(sn.label) + '</text>';
  });
  evNodes.forEach(function(en) {
    var fill = en.tier === "GOLD" ? "var(--gold)" : en.tier === "SILVER" ? "var(--silver)" : "var(--bronze)";
    svg += '<circle cx="' + en.x + '" cy="' + en.y.toFixed(1) + '" r="4" fill="' + fill + '" fill-opacity="0.7"/>';
  });
  var evMap = {};
  evNodes.forEach(function(en) { evMap[en.id] = en; });
  sectionNodes.forEach(function(sn) {
    (sn.evidence_ids || []).forEach(function(eid) {
      var en = evMap[eid];
      if (en) svg += '<line x1="' + sn.x + '" y1="' + sn.y.toFixed(1) + '" x2="' + en.x + '" y2="' + en.y.toFixed(1) + '" stroke="rgba(56,189,248,0.15)" stroke-width="0.5"/>';
    });
  });
  canvas.innerHTML = svg;
}

/* Source Network: domain nodes -> evidence nodes */
function buildSourceNetGraph(canvas, emptyEl) {
  if (!state.evidenceDetails.length) {
    if (emptyEl) emptyEl.style.display = "block";
    canvas.innerHTML = '';
    return;
  }
  if (emptyEl) emptyEl.style.display = "none";
  var W = canvas.clientWidth || 800, H = canvas.clientHeight || 500;
  var domainMap = {};
  state.evidenceDetails.slice(0, 200).forEach(function(ev) {
    var domain = extractDomain(ev.source_url || "");
    if (!domain) return;
    if (!domainMap[domain]) domainMap[domain] = { count: 0, evidence: [] };
    domainMap[domain].count++;
    domainMap[domain].evidence.push(ev);
  });
  var domains = Object.keys(domainMap).sort(function(a, b) { return domainMap[b].count - domainMap[a].count; }).slice(0, 20);
  var svg = '';
  domains.forEach(function(d, i) {
    var angle = (2 * Math.PI * i) / domains.length;
    var dx = W / 2 + (W / 3) * Math.cos(angle), dy = H / 2 + (H / 3) * Math.sin(angle);
    var r = 6 + domainMap[d].count * 2;
    svg += '<circle cx="' + dx.toFixed(1) + '" cy="' + dy.toFixed(1) + '" r="' + Math.min(r, 25) + '" fill="var(--info-dim)" stroke="var(--info)" stroke-width="1"/>';
    svg += '<text x="' + dx.toFixed(1) + '" y="' + (dy + Math.min(r, 25) + 12).toFixed(1) + '" text-anchor="middle" font-size="9" fill="var(--text-tertiary)" font-family="Inter">' + esc(truncStr(d, 20)) + '</text>';
    domainMap[d].evidence.slice(0, 10).forEach(function(ev, j) {
      var ex = dx + (Math.random() - 0.5) * 40, ey = dy + (Math.random() - 0.5) * 40;
      var fill = (ev.tier || "").toUpperCase() === "GOLD" ? "var(--gold)" : (ev.tier || "").toUpperCase() === "SILVER" ? "var(--silver)" : "var(--bronze)";
      svg += '<circle cx="' + ex.toFixed(1) + '" cy="' + ey.toFixed(1) + '" r="3" fill="' + fill + '" fill-opacity="0.6"/>';
      svg += '<line x1="' + dx.toFixed(1) + '" y1="' + dy.toFixed(1) + '" x2="' + ex.toFixed(1) + '" y2="' + ey.toFixed(1) + '" stroke="rgba(59,130,246,0.15)" stroke-width="0.5"/>';
    });
  });
  canvas.innerHTML = svg;
}

/* =====================================================================
   Theme-aware graph colors (QW-4)
   ===================================================================== */
function readThemeColors() {
  var cs = getComputedStyle(document.documentElement);
  return {
    gold: cs.getPropertyValue('--gold').trim() || '#FCD34D',
    silver: cs.getPropertyValue('--silver').trim() || '#CBD5E1',
    bronze: cs.getPropertyValue('--bronze').trim() || '#fbbf24',
    accent: cs.getPropertyValue('--accent').trim() || '#38bdf8',
    border: cs.getPropertyValue('--border').trim() || '#334155',
    bgElevated: cs.getPropertyValue('--bg-elevated').trim() || '#1e293b',
  };
}
function refreshGraphColors() {
  var colors = readThemeColors();
  var svg = document.getElementById('graph-svg');
  if (!svg) return;
  svg.querySelectorAll('circle').forEach(function(c) {
    var fill = c.getAttribute('fill') || '';
    if (fill.indexOf('--gold') >= 0 || fill === '#FCD34D') c.setAttribute('fill', colors.gold);
    else if (fill.indexOf('--silver') >= 0 || fill === '#CBD5E1') c.setAttribute('fill', colors.silver);
    else if (fill.indexOf('--bronze') >= 0 || fill === '#fbbf24') c.setAttribute('fill', colors.bronze);
  });
}
window.refreshGraphColors = refreshGraphColors;
