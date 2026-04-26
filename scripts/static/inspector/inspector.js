// POLARIS Evidence Inspector — Phase A.
// M-2 wired the shell + tabs + tier strip.
// M-3 wires View 1: rendered report with click-to-inspect citations.
//
// Codex M-3 review fixes integrated:
// - real split-pane layout (HTML restructured to put pane in flex row)
// - full cluster rendering (all claims, active claim highlighted)
// - URL-stem resolver as secondary contradiction match
// - URL protocol sanitization (only http/https in href)
// - tier/severity validated against an enum before injection
// - aria-controls / aria-expanded / focus management

(function () {
  "use strict";

  const slug = window.POLARIS_RUN_SLUG;
  if (!slug) {
    console.error("POLARIS_RUN_SLUG not set; cannot load run");
    return;
  }

  const VALID_TIERS = new Set(["T1", "T2", "T3", "T4", "T5", "T6", "T7", "UNKNOWN"]);
  const VALID_SEVERITIES = new Set(["low", "medium", "high", "critical", "unknown"]);

  const tabs = document.querySelectorAll(".tab-btn");
  const views = document.querySelectorAll(".view");

  function activateView(viewName) {
    tabs.forEach((t) => {
      const isActive = t.dataset.view === viewName;
      t.classList.toggle("active", isActive);
      t.setAttribute("aria-selected", isActive ? "true" : "false");
    });
    views.forEach((v) => {
      const isActive = v.id === `view-${viewName}`;
      v.hidden = !isActive;
      v.classList.toggle("active", isActive);
    });
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => activateView(tab.dataset.view));
  });

  // ---------------------------------------------------------------------
  // Helpers (XSS hardening + value validation)
  // ---------------------------------------------------------------------

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Only http/https URLs are allowed in href. Anything else (javascript:,
  // data:, file:, mailto:, etc.) collapses to "" so the link is rendered
  // inert. Codex M-3 fix: protocol sanitization.
  function sanitizeUrl(url) {
    const s = String(url == null ? "" : url).trim();
    if (!s) return "";
    if (/^https?:\/\//i.test(s)) return s;
    return "";
  }

  function validateTier(t) {
    const up = String(t == null ? "" : t).toUpperCase();
    return VALID_TIERS.has(up) ? up : "UNKNOWN";
  }

  function validateSeverity(sev) {
    const lo = String(sev == null ? "" : sev).toLowerCase();
    return VALID_SEVERITIES.has(lo) ? lo : "unknown";
  }

  // Normalize a URL for comparison. Preserves query string (Codex M-3 v2
  // review fix: stripping query was too lossy and over-joined distinct URLs).
  // Only drops scheme, www. prefix, trailing slash, and lowercases.
  function urlStem(url) {
    const s = String(url == null ? "" : url).trim().toLowerCase();
    if (!s) return "";
    return s
      .replace(/^https?:\/\//, "")
      .replace(/^www\./, "")
      .replace(/#.*$/, "")
      .replace(/\/+$/, "");
  }

  // Strip known non-URL prefixes from retrieval_attempt_log entries.
  // Codex M-3 v3 review fix: some retrieval URLs are stored as
  // "oa_full_text:https://...", "url_pattern:https://...", "pdf:https://...".
  // Without stripping the prefix, urlStem produces "oa_full_text:https://..."
  // which never matches a real source_url.
  function stripUrlPrefix(url) {
    const s = String(url == null ? "" : url).trim();
    if (!s) return "";
    const m = s.match(/^[A-Za-z][A-Za-z0-9_]+:(https?:\/\/.+)$/);
    if (m) return m[1];
    return s;
  }

  // Trim publisher suffixes from a captured DOI so distinct publisher
  // URLs that share the same DOI canonicalize to one key.
  // Codex M-3 v3 review fix: e.g. "10.3389/fphar.2022.998816/pdf" and
  // "10.3389/fphar.2022.998816" should collapse to one DOI key.
  function canonicalizeDoi(doi) {
    if (!doi) return "";
    let d = String(doi).toLowerCase().trim();
    // Repeatedly strip trailing publisher artefacts
    let prev = "";
    while (d !== prev) {
      prev = d;
      d = d.replace(/\/(pdf|full|abstract|html|epdf|metrics|references)$/, "");
      d = d.replace(/\.(pdf|html|xml|epub)$/, "");
      d = d.replace(/\/+$/, "");
    }
    return d;
  }

  // Extract canonical identifiers (DOI, PMID, full URL stem) from a URL.
  // Used to bridge bibliography (surpass_X / entity-anchored) and
  // contradiction (ev_NNN / corpus-anchored) namespaces in run-14 by
  // matching on shared DOI/PMID even when evidence_ids differ.
  function extractIdentifiers(url) {
    const out = new Set();
    const raw = String(url == null ? "" : url).trim();
    if (!raw) return out;
    const s = stripUrlPrefix(raw);
    // DOI: 10.NNNN/anything, then trim publisher suffixes for canonicalization
    const doiMatch = s.match(/\b10\.\d{4,9}\/\S+/i);
    if (doiMatch) {
      const canonical = canonicalizeDoi(doiMatch[0]);
      if (canonical) out.add("doi:" + canonical);
    }
    // PMID via pubmed URL
    const pmidUrlMatch = s.match(/pubmed\.ncbi\.nlm\.nih\.gov\/(\d+)/i);
    if (pmidUrlMatch) out.add("pmid:" + pmidUrlMatch[1]);
    // PMID via efetch query string
    const pmidEfetchMatch = s.match(/efetch\.fcgi[^\s]*[?&]id=(\d+)/i);
    if (pmidEfetchMatch) out.add("pmid:" + pmidEfetchMatch[1]);
    // Full URL stem
    const stem = urlStem(s);
    if (stem) out.add("url:" + stem);
    return out;
  }

  // Identifiers bound to a bibliography entry. Pulls DOI/PMID directly
  // from frame_coverage_report entries (entity-anchored citations like
  // surpass_1_primary have empty bib.url but a DOI in frame_coverage).
  function bibIdentifiers(bib, ir) {
    const ids = new Set();
    const fcEntries = (ir.frame_coverage && ir.frame_coverage.entries) || [];
    const fcEntry = fcEntries.find((e) => e.entity_id === bib.evidence_id);
    if (fcEntry) {
      if (fcEntry.doi) {
        const canonical = canonicalizeDoi(fcEntry.doi);
        if (canonical) ids.add("doi:" + canonical);
      }
      if (fcEntry.pmid) ids.add("pmid:" + String(fcEntry.pmid));
      (fcEntry.retrieval_attempt_log || []).forEach((att) => {
        extractIdentifiers(att.url).forEach((id) => ids.add(id));
      });
    }
    extractIdentifiers(bib.url).forEach((id) => ids.add(id));
    return ids;
  }

  // ---------------------------------------------------------------------
  // Data fetch
  // ---------------------------------------------------------------------
  async function fetchJSON(path) {
    const resp = await fetch(path);
    if (!resp.ok) {
      throw new Error(`${path} returned ${resp.status}`);
    }
    return resp.json();
  }
  async function fetchText(path) {
    const resp = await fetch(path);
    if (!resp.ok) {
      throw new Error(`${path} returned ${resp.status}`);
    }
    return resp.text();
  }

  // ---------------------------------------------------------------------
  // Tier strip + tab counts
  // ---------------------------------------------------------------------
  function renderTierStrip(ir) {
    const strip = document.getElementById("tier-bar-strip");
    if (!strip) return;
    const fractions = (ir.tier_mix && ir.tier_mix.fractions) || {};
    const ordered = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "UNKNOWN"];
    strip.innerHTML = "";
    ordered.forEach((tier) => {
      const frac = Number(fractions[tier] || 0);
      if (frac <= 0) return;
      const seg = document.createElement("div");
      seg.className = `tier-segment tier-segment-${tier.toLowerCase()}`;
      seg.style.flex = String(frac);
      seg.title = `${tier}: ${(frac * 100).toFixed(1)}%`;
      strip.appendChild(seg);
    });
  }

  function renderTabCounts(ir) {
    const cContradictions = (ir.contradictions || []).length;
    const fc = ir.frame_coverage || {};
    const cFrames = (fc.entries || []).length;
    const elC = document.getElementById("contradictions-count");
    const elF = document.getElementById("frame-coverage-count");
    if (elC) elC.textContent = String(cContradictions);
    if (elF) elF.textContent = String(cFrames);
  }

  // ---------------------------------------------------------------------
  // M-3: View 1 — Report click-to-inspect
  // ---------------------------------------------------------------------

  function buildEvidenceIndex(ir) {
    const bibByNum = {};
    (ir.bibliography || []).forEach((b) => {
      bibByNum[String(b.num)] = b;
    });

    // sentencesByEvidenceId: claim_id -> sentences
    const sentencesByEvidenceId = {};
    (ir.verified_report?.sections || []).forEach((section) => {
      (section.sentences || []).forEach((sent) => {
        (sent.tokens || []).forEach((tok) => {
          if (!tok.evidence_id) return;
          if (!sentencesByEvidenceId[tok.evidence_id]) {
            sentencesByEvidenceId[tok.evidence_id] = [];
          }
          sentencesByEvidenceId[tok.evidence_id].push({
            section: section.title,
            sentence: sent,
            token: tok,
          });
        });
      });
    });

    // Primary index: cluster matches by exact evidence_id of any of its claims
    const clustersByEvidenceId = {};
    // Secondary index: cluster matches by canonical identifier (DOI/PMID/URL)
    // of any claim's source_url. Bridges entity-anchored (surpass_X) ↔
    // corpus-anchored (ev_NNN) namespaces in run-14.
    const clustersByIdentifier = {};
    (ir.contradictions || []).forEach((cluster) => {
      (cluster.claims || []).forEach((claim) => {
        if (claim.evidence_id) {
          if (!clustersByEvidenceId[claim.evidence_id]) {
            clustersByEvidenceId[claim.evidence_id] = [];
          }
          if (!clustersByEvidenceId[claim.evidence_id].includes(cluster)) {
            clustersByEvidenceId[claim.evidence_id].push(cluster);
          }
        }
        extractIdentifiers(claim.source_url).forEach((id) => {
          if (!clustersByIdentifier[id]) {
            clustersByIdentifier[id] = [];
          }
          if (!clustersByIdentifier[id].includes(cluster)) {
            clustersByIdentifier[id].push(cluster);
          }
        });
      });
    });

    return {
      bibByNum,
      sentencesByEvidenceId,
      clustersByEvidenceId,
      clustersByIdentifier,
    };
  }

  function findClustersForBibEntry(bib, ir, idx) {
    const bySet = new Set();
    const eid = bib.evidence_id || "";
    (idx.clustersByEvidenceId[eid] || []).forEach((c) => bySet.add(c));
    bibIdentifiers(bib, ir).forEach((id) => {
      (idx.clustersByIdentifier[id] || []).forEach((c) => bySet.add(c));
    });
    return Array.from(bySet);
  }

  function tierBadgeHtml(tier) {
    const t = validateTier(tier);
    return `<span class="tier-badge tier-badge-${t.toLowerCase()}">${escHtml(t)}</span>`;
  }

  function severityBadgeHtml(sev) {
    const s = validateSeverity(sev);
    return `<span class="severity severity-${escHtml(s)}">${escHtml(s)}</span>`;
  }

  function renderEvidencePane(num, ir, idx) {
    const bib = idx.bibByNum[String(num)];
    const pane = document.getElementById("evidence-pane");
    const body = pane.querySelector(".evidence-pane-body");
    const header = pane.querySelector(".evidence-pane-header h3");

    if (!bib) {
      header.textContent = `Citation [${num}] — unresolved`;
      body.innerHTML = `<p class="placeholder">No bibliography entry for [${escHtml(num)}].</p>`;
      openPane();
      return;
    }

    const eid = bib.evidence_id;
    const sentences = idx.sentencesByEvidenceId[eid] || [];
    const clusters = findClustersForBibEntry(bib, ir, idx);
    const bibIds = bibIdentifiers(bib, ir);

    header.textContent = `Citation [${num}] — ${eid}`;

    let html = "";

    // Bibliography block
    html += `<section class="evidence-block evidence-bib">`;
    html += `  <div class="evidence-block-row">`;
    html += `    ${tierBadgeHtml(bib.tier)}`;
    html += `    <span class="evidence-eid">${escHtml(eid)}</span>`;
    html += `  </div>`;
    html += `  <p class="evidence-statement">${escHtml(bib.statement)}</p>`;
    const safeUrl = sanitizeUrl(bib.url);
    if (safeUrl) {
      html += `  <p class="evidence-url"><a href="${escHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${escHtml(safeUrl)}</a></p>`;
    } else if (bib.url) {
      html += `  <p class="evidence-url evidence-url-blocked">URL omitted (non-http(s) scheme blocked)</p>`;
    }
    html += `</section>`;

    // Verified sentences citing this evidence
    html += `<section class="evidence-block">`;
    html += `  <h4 class="evidence-block-title">Sentences citing this evidence (${sentences.length})</h4>`;
    if (sentences.length === 0) {
      html += `<p class="placeholder">No sentences in the verified report cite this evidence directly.</p>`;
    } else {
      html += `<ul class="evidence-sentences">`;
      sentences.forEach((s) => {
        const verified = s.sentence.is_verified;
        const cls = verified ? "kept" : "dropped";
        const label = verified ? "verified" : "dropped";
        html += `<li class="evidence-sentence evidence-sentence-${cls}">`;
        html += `  <div class="evidence-sentence-meta">`;
        html += `    <span class="evidence-sentence-section">${escHtml(s.section)}</span>`;
        html += `    <span class="evidence-sentence-status status-${cls}">${escHtml(label)}</span>`;
        html += `    <span class="evidence-sentence-span">span ${Number(s.token.start)}–${Number(s.token.end)}</span>`;
        html += `  </div>`;
        html += `  <p class="evidence-sentence-text">${escHtml(s.sentence.text)}</p>`;
        if (!verified && (s.sentence.failure_reasons || []).length > 0) {
          html += `<p class="evidence-sentence-fail">drop: ${escHtml(s.sentence.failure_reasons.join("; "))}</p>`;
        }
        html += `</li>`;
      });
      html += `</ul>`;
    }
    html += `</section>`;

    // Contradiction clusters — all claims, active claim highlighted
    html += `<section class="evidence-block">`;
    html += `  <h4 class="evidence-block-title">Contradictions involving this evidence (${clusters.length})</h4>`;
    if (clusters.length === 0) {
      html += `<p class="placeholder">No contradiction clusters reference this evidence directly. See the Contradictions tab for the corpus-wide matrix.</p>`;
    } else {
      html += `<ul class="evidence-contradictions">`;
      clusters.forEach((cluster) => {
        html += `<li class="contradiction-cluster">`;
        html += `  <div class="evidence-contradiction-meta">`;
        html += `    ${severityBadgeHtml(cluster.severity)}`;
        html += `    <span class="cluster-predicate">${escHtml(cluster.subject || "")} · ${escHtml(cluster.predicate)}</span>`;
        html += `  </div>`;
        if (cluster.recommended_action) {
          html += `<p class="evidence-contradiction-action">${escHtml(cluster.recommended_action)}</p>`;
        }
        html += `<ol class="cluster-claims">`;
        (cluster.claims || []).forEach((claim) => {
          const claimIds = extractIdentifiers(claim.source_url);
          const idIntersect = Array.from(bibIds).some((id) => claimIds.has(id));
          const isActive =
            (claim.evidence_id && claim.evidence_id === eid) || idIntersect;
          const claimUrl = sanitizeUrl(claim.source_url);
          html += `<li class="cluster-claim ${isActive ? "cluster-claim-active" : ""}">`;
          html += `  <div class="cluster-claim-meta">`;
          html += `    ${tierBadgeHtml(claim.source_tier)}`;
          html += `    <span class="cluster-claim-eid">${escHtml(claim.evidence_id || "—")}</span>`;
          html += `    <span class="cluster-claim-value">${escHtml(claim.value)} ${escHtml(claim.unit || "")}</span>`;
          if (claim.dose) html += `    <span class="cluster-claim-dose">dose ${escHtml(claim.dose)}</span>`;
          if (claim.arm) html += `    <span class="cluster-claim-arm">arm ${escHtml(claim.arm)}</span>`;
          html += `  </div>`;
          if (claim.context_snippet) {
            html += `  <p class="cluster-claim-snippet">${escHtml(claim.context_snippet)}</p>`;
          }
          if (claimUrl) {
            html += `  <p class="cluster-claim-url"><a href="${escHtml(claimUrl)}" target="_blank" rel="noopener noreferrer">${escHtml(claimUrl)}</a></p>`;
          }
          html += `</li>`;
        });
        html += `</ol>`;
        html += `</li>`;
      });
      html += `</ul>`;
    }
    html += `</section>`;

    body.innerHTML = html;
    openPane();
  }

  function openPane() {
    const pane = document.getElementById("evidence-pane");
    pane.hidden = false;
    pane.setAttribute("aria-hidden", "false");
    document.body.classList.add("evidence-pane-open");
    // Mark all citations as not expanded; we update the active one separately.
    document.querySelectorAll("a.citation").forEach((a) => a.setAttribute("aria-expanded", "false"));
    const active = document.querySelector("a.citation.active");
    if (active) active.setAttribute("aria-expanded", "true");
    // Move focus to the pane body so screen readers announce it.
    const body = document.getElementById("evidence-pane-body");
    if (body) body.focus();
  }

  function closeEvidencePane(returnFocus) {
    const pane = document.getElementById("evidence-pane");
    pane.hidden = true;
    pane.setAttribute("aria-hidden", "true");
    document.body.classList.remove("evidence-pane-open");
    document.querySelectorAll(".citation.active").forEach((el) => {
      el.classList.remove("active");
      el.setAttribute("aria-expanded", "false");
    });
    if (returnFocus) returnFocus.focus();
  }

  let _wired = false;
  let _lastFocused = null;
  function wireGlobalListeners() {
    if (_wired) return;
    _wired = true;
    const closeBtn = document.querySelector(".evidence-pane-close");
    if (closeBtn) closeBtn.addEventListener("click", () => closeEvidencePane(_lastFocused));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        const pane = document.getElementById("evidence-pane");
        if (pane && !pane.hidden) closeEvidencePane(_lastFocused);
      }
    });
  }

  function wireCitationInteraction(ir, idx) {
    const shell = document.getElementById("report-shell");
    if (!shell) return;
    shell.addEventListener("click", (event) => {
      const target = event.target.closest("a.citation");
      if (!target) return;
      event.preventDefault();
      const num = target.dataset.num;
      document.querySelectorAll(".citation.active").forEach((el) =>
        el.classList.remove("active")
      );
      target.classList.add("active");
      _lastFocused = target;
      renderEvidencePane(num, ir, idx);
    });
    shell.addEventListener("keydown", (event) => {
      const target = event.target.closest("a.citation");
      if (!target) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        target.click();
      }
    });
    // Add a11y attributes to every citation in the rendered prose.
    shell.querySelectorAll("a.citation").forEach((a) => {
      a.setAttribute("aria-controls", "evidence-pane");
      a.setAttribute("aria-expanded", "false");
      const num = a.dataset.num;
      const bib = idx.bibByNum[num];
      if (bib) {
        a.setAttribute(
          "aria-label",
          `Citation ${num}: ${bib.tier || "UNKNOWN"} source — ${
            bib.statement ? bib.statement.slice(0, 80) : bib.evidence_id
          }`
        );
      } else {
        a.setAttribute("aria-label", `Citation ${num} (unresolved)`);
      }
    });
    wireGlobalListeners();
  }

  async function renderReportView(ir) {
    const shell = document.getElementById("report-shell");
    if (!shell) return;
    const md = await fetchText(`/api/inspector/runs/${encodeURIComponent(slug)}/report.md`);
    const html = window.PolarisMarkdown.render(md);

    shell.innerHTML = "";
    const m = ir.manifest || {};
    const meta = document.createElement("p");
    meta.className = "report-runmeta";
    meta.textContent =
      `run_id=${m.run_id || "—"}  ·  status=${m.status || "—"}  ·  ` +
      `cost=$${(m.cost_usd || 0).toFixed(4)}  ·  words=${m.word_count || 0}  ·  ` +
      `contradictions=${m.contradictions_found || 0}  ·  ` +
      `verified=${ir.verified_report?.sentences_verified ?? "—"}  ·  ` +
      `dropped=${ir.verified_report?.sentences_dropped ?? "—"}`;
    shell.appendChild(meta);

    const prose = document.createElement("div");
    prose.className = "report-prose";
    prose.innerHTML = html;
    shell.appendChild(prose);

    const idx = buildEvidenceIndex(ir);
    wireCitationInteraction(ir, idx);
  }

  // ---------------------------------------------------------------------
  // M-4: View 2 — Contradiction Matrix
  //
  // First-class disagreement-disclosure view (FINAL_PLAN.md): renders all
  // tier-labeled clusters as a filterable matrix. No competitor surfaces
  // contradictions as their own primary view — this is the moat.
  // ---------------------------------------------------------------------

  function uniqueSorted(values) {
    return Array.from(new Set(values)).filter((v) => v !== undefined && v !== null && v !== "").sort();
  }

  function clusterTiers(cluster) {
    return uniqueSorted((cluster.claims || []).map((c) => validateTier(c.source_tier)));
  }

  function clusterDoses(cluster) {
    return uniqueSorted((cluster.claims || []).map((c) => String(c.dose || "").trim()));
  }

  function clusterValues(cluster) {
    const vs = (cluster.claims || [])
      .map((c) => Number(c.value))
      .filter((v) => Number.isFinite(v));
    if (vs.length === 0) return null;
    return { min: Math.min(...vs), max: Math.max(...vs) };
  }

  function clusterMatchesQuery(cluster, q) {
    // Trim whitespace; "   " behaves like empty (Codex M-4 review fix).
    const trimmed = String(q == null ? "" : q).trim();
    if (!trimmed) return true;
    const needle = trimmed.toLowerCase();
    const hasMatch = (s) => typeof s === "string" && s.toLowerCase().includes(needle);
    if (hasMatch(cluster.subject)) return true;
    if (hasMatch(cluster.predicate)) return true;
    if (hasMatch(cluster.recommended_action)) return true;
    for (const claim of cluster.claims || []) {
      // All visibly-rendered claim fields are searchable per Codex M-4 fix.
      if (hasMatch(claim.evidence_id)) return true;
      if (hasMatch(claim.source_url)) return true;
      if (hasMatch(claim.context_snippet)) return true;
      if (hasMatch(claim.dose)) return true;
      if (hasMatch(claim.arm)) return true;
      if (hasMatch(claim.unit)) return true;
      if (hasMatch(claim.source_tier)) return true;
      // Numeric value: stringify so "25.3" matches "25.3 %" snippets too.
      if (claim.value != null && hasMatch(String(claim.value))) return true;
    }
    return false;
  }

  const _matrixState = {
    severity: "all",
    tier: "all",
    dose: "all",
    query: "",
    expanded: new Set(),
  };

  function applyMatrixFilters(clusters) {
    return clusters.filter((cluster) => {
      if (
        _matrixState.severity !== "all" &&
        validateSeverity(cluster.severity) !== _matrixState.severity
      ) return false;
      if (_matrixState.tier !== "all" && !clusterTiers(cluster).includes(_matrixState.tier)) return false;
      if (_matrixState.dose !== "all" && !clusterDoses(cluster).includes(_matrixState.dose)) return false;
      if (!clusterMatchesQuery(cluster, _matrixState.query)) return false;
      return true;
    });
  }

  function renderMatrixRow(cluster) {
    const id = `matrix-row-${cluster.cluster_id}`;
    const expanded = _matrixState.expanded.has(cluster.cluster_id);
    const tiers = clusterTiers(cluster);
    const valueRange = clusterValues(cluster);
    let html = `<li class="matrix-row ${expanded ? "expanded" : ""}" id="${id}" data-cluster-id="${cluster.cluster_id}" tabindex="0" role="button" aria-expanded="${expanded ? "true" : "false"}">`;
    html += `<div class="matrix-row-header">`;
    html += `  ${severityBadgeHtml(cluster.severity)}`;
    html += `  <span class="matrix-row-predicate">${escHtml(cluster.subject || "")} · ${escHtml(cluster.predicate)}</span>`;
    if (valueRange) {
      html += `  <span class="matrix-row-spread">range ${escHtml(valueRange.min)} → ${escHtml(valueRange.max)}</span>`;
    }
    html += `  <span class="matrix-row-tiers">${tiers.map((t) => tierBadgeHtml(t)).join("")}</span>`;
    html += `  <span class="matrix-row-meta"><span>Δ ${escHtml(cluster.absolute_difference)}</span><span>rel ${escHtml(cluster.relative_difference)}%</span><span>${escHtml((cluster.claims || []).length)} claims</span></span>`;
    html += `</div>`;
    if (cluster.recommended_action) {
      html += `<p class="matrix-row-action">${escHtml(cluster.recommended_action)}</p>`;
    }
    html += `<ol class="matrix-row-claims">`;
    (cluster.claims || []).forEach((claim) => {
      const url = sanitizeUrl(claim.source_url);
      html += `<li class="matrix-claim">`;
      html += `  <div class="matrix-claim-meta">`;
      html += `    ${tierBadgeHtml(claim.source_tier)}`;
      html += `    <span>${escHtml(claim.evidence_id || "—")}</span>`;
      html += `    <span class="matrix-claim-value">${escHtml(claim.value)} ${escHtml(claim.unit || "")}</span>`;
      if (claim.dose) html += `    <span>dose ${escHtml(claim.dose)}</span>`;
      if (claim.arm) html += `    <span>arm ${escHtml(claim.arm)}</span>`;
      html += `  </div>`;
      if (claim.context_snippet) {
        html += `  <p class="matrix-claim-snippet">${escHtml(claim.context_snippet)}</p>`;
      }
      if (url) {
        html += `  <p class="matrix-claim-url"><a href="${escHtml(url)}" target="_blank" rel="noopener noreferrer">${escHtml(url)}</a></p>`;
      }
      html += `</li>`;
    });
    html += `</ol>`;
    html += `</li>`;
    return html;
  }

  // Codex M-4 review fix: split the matrix view into a stable toolbar
  // (rendered ONCE) and a results region (re-rendered on filter change).
  // Previously every keystroke replaced the whole shell, including the
  // active <input>, dropping focus/caret mid-search.

  function _renderSelect(name, current, options) {
    let html = `<select data-matrix-filter="${name}" aria-label="Filter by ${name}">`;
    html += `<option value="all">${escHtml(name)} = all</option>`;
    options.forEach((opt) => {
      html += `<option value="${escHtml(opt)}" ${current === opt ? "selected" : ""}>${escHtml(opt)}</option>`;
    });
    html += `</select>`;
    return html;
  }

  function renderMatrixToolbar(ir, shell) {
    const clusters = ir.contradictions || [];
    const allSeverities = uniqueSorted(clusters.map((c) => validateSeverity(c.severity)));
    const allTiers = uniqueSorted(clusters.flatMap((c) => clusterTiers(c)));
    const allDoses = uniqueSorted(clusters.flatMap((c) => clusterDoses(c)));

    let html = "";
    html += `<div class="matrix-toolbar" id="matrix-toolbar">`;
    html += `  <label class="matrix-filter">severity ${_renderSelect("severity", _matrixState.severity, allSeverities)}</label>`;
    html += `  <label class="matrix-filter">tier ${_renderSelect("tier", _matrixState.tier, allTiers)}</label>`;
    html += `  <label class="matrix-filter">dose ${_renderSelect("dose", _matrixState.dose, allDoses)}</label>`;
    html += `  <label class="matrix-filter">search <input type="search" data-matrix-filter="query" placeholder="subject / predicate / source / snippet" value="${escHtml(_matrixState.query)}"></label>`;
    html += `  <button class="matrix-clear" type="button">clear</button>`;
    html += `  <span class="matrix-summary" id="matrix-summary"></span>`;
    html += `</div>`;
    html += `<div id="matrix-results"></div>`;
    shell.innerHTML = html;
  }

  function renderMatrixResults(ir) {
    const clusters = ir.contradictions || [];
    const filtered = applyMatrixFilters(clusters);
    const results = document.getElementById("matrix-results");
    const summary = document.getElementById("matrix-summary");
    if (!results) return;
    let html = "";
    if (filtered.length === 0) {
      html = `<p class="matrix-empty">No clusters match the current filters.</p>`;
    } else {
      html = `<ul class="matrix-list" role="list">`;
      filtered.forEach((cluster) => {
        html += renderMatrixRow(cluster);
      });
      html += `</ul>`;
    }
    results.innerHTML = html;
    if (summary) summary.textContent = `${filtered.length} / ${clusters.length} clusters`;
    wireMatrixRowInteraction();
  }

  function renderMatrixView(ir) {
    const root = document.getElementById("view-contradictions");
    if (!root) return;
    const shell = root.querySelector(".view-shell");
    if (!shell) return;
    renderMatrixToolbar(ir, shell);
    wireMatrixToolbar(ir);
    renderMatrixResults(ir);
  }

  function wireMatrixToolbar(ir) {
    const root = document.getElementById("view-contradictions");
    if (!root) return;
    root.querySelectorAll("select[data-matrix-filter], input[data-matrix-filter]").forEach((el) => {
      const handler = () => {
        const name = el.dataset.matrixFilter;
        _matrixState[name] = el.value;
        // Only re-render results; the toolbar and its <input> stay stable
        // so focus/caret are preserved (Codex M-4 review fix).
        renderMatrixResults(ir);
      };
      el.addEventListener("change", handler);
      if (el.tagName === "INPUT") el.addEventListener("input", handler);
    });
    const clearBtn = root.querySelector(".matrix-clear");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        _matrixState.severity = "all";
        _matrixState.tier = "all";
        _matrixState.dose = "all";
        _matrixState.query = "";
        // Reflect cleared state in the toolbar inputs.
        root.querySelectorAll("select[data-matrix-filter]").forEach((s) => {
          s.value = "all";
        });
        const queryInput = root.querySelector('input[data-matrix-filter="query"]');
        if (queryInput) queryInput.value = "";
        renderMatrixResults(ir);
      });
    }
  }

  function wireMatrixRowInteraction() {
    const root = document.getElementById("view-contradictions");
    if (!root) return;
    root.querySelectorAll(".matrix-row").forEach((row) => {
      const toggle = (event) => {
        if (event.target.closest("a")) return;  // don't toggle when clicking a link
        if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
        if (event.type === "keydown") event.preventDefault();
        const id = Number(row.dataset.clusterId);
        if (_matrixState.expanded.has(id)) {
          _matrixState.expanded.delete(id);
          row.classList.remove("expanded");
          row.setAttribute("aria-expanded", "false");
        } else {
          _matrixState.expanded.add(id);
          row.classList.add("expanded");
          row.setAttribute("aria-expanded", "true");
        }
      };
      row.addEventListener("click", toggle);
      row.addEventListener("keydown", toggle);
    });
  }

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------
  fetchJSON(`/api/inspector/runs/${encodeURIComponent(slug)}`)
    .then((ir) => {
      window.POLARIS_IR = ir;
      renderTierStrip(ir);
      renderTabCounts(ir);
      renderMatrixView(ir);
      return renderReportView(ir);
    })
    .catch((err) => {
      const shell = document.getElementById("report-shell");
      if (shell) {
        shell.innerHTML = `<p class="placeholder">Failed to load run: ${escHtml(err.message)}</p>`;
      }
    });
})();
