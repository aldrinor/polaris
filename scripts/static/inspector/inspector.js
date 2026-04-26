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
  // M-5: View 3 — Frame Coverage Manifest
  //
  // Renders frame_coverage_report (15 entities in run-14) with visual
  // pass/partial/gap coverage bar + V30 retrieval-coverage semantics
  // warning + per-section grouping + per-slot detail rows + operator-
  // action button on rows that are operator-completion-eligible.
  // Per FINAL_PLAN.md: this is the antidote to ChatGPT DR's silent omissions.
  // ---------------------------------------------------------------------

  const _coverageStatusOrder = [
    "pass", "partial", "fail_min_fields", "frame_gap", "pipeline_fault",
  ];

  // Codex M-5 review fix #1: backend semantics distinguish "fail_min_fields
  // + provenance_class=frame_gap_unrecoverable" (true gap) from
  // "fail_min_fields + non-gap row" (partial). The view must reflect that
  // distinction so the summary bar and per-row severity stay consistent.
  function classifyCoverageStatus(status, entry) {
    const s = String(status || "").toLowerCase();
    if (s === "pass") return "pass";
    if (s === "partial") return "partial";
    if (s === "pipeline_fault") return "pipeline-fault";
    if (s === "frame_gap" || s === "gap") return "gap";
    if (s === "fail_min_fields") {
      // Aggregate semantics: only a hard gap when retrieval also reports
      // an unrecoverable frame gap or zero usable artifacts.
      const provClass = String((entry && entry.provenance_class) || "").toLowerCase();
      const hasArtifacts = Array.isArray(entry && entry.available_artifacts) &&
        entry.available_artifacts.length > 0;
      if (provClass === "frame_gap_unrecoverable" || provClass === "gap") return "gap";
      if (!hasArtifacts) return "gap";
      return "partial";
    }
    return "gap";
  }

  function renderCoverageWarning(fc) {
    if (!fc.semantics_warning) return "";
    return (
      `<div class="coverage-warning" role="note">` +
      `  <div class="coverage-warning-title">Coverage semantics</div>` +
      `  ${escHtml(fc.semantics_warning)}` +
      `</div>`
    );
  }

  function renderCoverageSummaryBar(fc, total) {
    const pass = Number(fc.pass_count || 0);
    const partial = Number(fc.partial_count || 0);
    const gap = Number(fc.frame_gap_count || 0);
    const pipelineFault = Number(fc.pipeline_fault_count || 0);
    const denom = total || pass + partial + gap + pipelineFault || 1;

    let html = `<div class="coverage-summary">`;
    html += `<div class="coverage-bar" role="img" aria-label="Coverage: ${pass} pass, ${partial} partial, ${gap} gap, ${pipelineFault} pipeline-fault">`;
    [
      ["pass", pass],
      ["partial", partial],
      ["gap", gap],
      ["pipeline-fault", pipelineFault],
    ].forEach(([key, count]) => {
      if (count <= 0) return;
      const flex = count / denom;
      html += `<div class="coverage-segment coverage-segment-${key}" style="flex:${flex}" title="${escHtml(key)}: ${count}">${count > 0 ? count : ""}</div>`;
    });
    html += `</div>`;
    html += `<div class="coverage-counts">`;
    html += `  <span class="coverage-count-pass">${pass} pass</span>`;
    html += `  <span class="coverage-count-partial">${partial} partial</span>`;
    html += `  <span class="coverage-count-gap">${gap} gap</span>`;
    if (pipelineFault > 0) {
      html += `  <span>${pipelineFault} pipeline-fault</span>`;
    }
    html += `</div>`;
    html += `</div>`;
    return html;
  }

  function renderCoverageRow(entry) {
    const cls = classifyCoverageStatus(entry.status, entry);
    const status = String(entry.status || "");
    let html = `<li class="coverage-row coverage-row-${cls}" data-entity-id="${escHtml(entry.entity_id || "")}" data-slot-id="${escHtml(entry.slot_id || "")}">`;
    html += `<div class="coverage-row-header">`;
    html += `  <span class="coverage-status-badge coverage-status-${escHtml(status.toLowerCase())}">${escHtml(status)}</span>`;
    html += `  <span class="coverage-row-entity">${escHtml(entry.entity_id || "")}</span>`;
    if (entry.slot_id) {
      // Codex M-5 review fix #2: surface slot_id (canonical contract-slot
      // key) so Phase B cross-view linking has a stable handle and the
      // manifest is explicitly per-slot, not just per-entity.
      html += `  <span class="coverage-row-slot">slot ${escHtml(entry.slot_id)}</span>`;
    }
    if (entry.section) {
      html += `  <span class="coverage-row-section">${escHtml(entry.section)}</span>`;
    }
    html += `</div>`;
    if (entry.subsection_title) {
      html += `<p class="coverage-row-subsection">${escHtml(entry.subsection_title)}</p>`;
    }

    // Identifiers row (DOI / PMID / type)
    const metaParts = [];
    if (entry.entity_type) metaParts.push(`<span>type ${escHtml(entry.entity_type)}</span>`);
    if (entry.doi) {
      const doiUrl = sanitizeUrl(`https://doi.org/${entry.doi}`);
      metaParts.push(`<span>doi ${doiUrl ? `<a href="${escHtml(doiUrl)}" target="_blank" rel="noopener noreferrer">${escHtml(entry.doi)}</a>` : escHtml(entry.doi)}</span>`);
    }
    if (entry.pmid) {
      const pmUrl = sanitizeUrl(`https://pubmed.ncbi.nlm.nih.gov/${entry.pmid}/`);
      metaParts.push(`<span>pmid ${pmUrl ? `<a href="${escHtml(pmUrl)}" target="_blank" rel="noopener noreferrer">${escHtml(entry.pmid)}</a>` : escHtml(entry.pmid)}</span>`);
    }
    if (entry.provenance_class) metaParts.push(`<span>provenance ${escHtml(entry.provenance_class)}</span>`);
    if (entry.min_fields_for_completion) {
      metaParts.push(`<span>min fields ${escHtml(entry.min_fields_for_completion)}</span>`);
    }
    if (metaParts.length > 0) {
      html += `<div class="coverage-row-meta">${metaParts.join("")}</div>`;
    }

    if (entry.failure_reason) {
      html += `<p class="coverage-row-failure">${escHtml(entry.failure_reason)}</p>`;
    }

    // Codex M-5 review fix #3: visibly differentiate "what the contract
    // required" from "what retrieval produced". Both rows now carry a
    // visible label + distinct chip styling.
    if (Array.isArray(entry.required_fields) && entry.required_fields.length > 0) {
      html += `<div class="coverage-row-fields-block">`;
      html += `<span class="coverage-fields-label">required</span>`;
      html += `<div class="coverage-row-fields" aria-label="Required fields">`;
      entry.required_fields.forEach((f) => {
        html += `<span class="coverage-field-chip coverage-chip-required">${escHtml(f)}</span>`;
      });
      html += `</div>`;
      html += `</div>`;
    }
    if (Array.isArray(entry.available_artifacts) && entry.available_artifacts.length > 0) {
      html += `<div class="coverage-row-fields-block">`;
      html += `<span class="coverage-fields-label">retrieved</span>`;
      html += `<div class="coverage-row-fields" aria-label="Available artifacts">`;
      entry.available_artifacts.forEach((f) => {
        html += `<span class="coverage-field-chip coverage-chip-retrieved">${escHtml(f)}</span>`;
      });
      html += `</div>`;
      html += `</div>`;
    }

    // Operator-action bar on rows that are gap-eligible
    const isGap = cls === "gap" || cls === "partial";
    if (isGap) {
      const eligible = entry.human_completion_eligible !== false;
      const hasCurated = entry.human_curated_provenance != null;
      html += `<div class="coverage-action-bar">`;
      html += `<button type="button" class="coverage-action-btn" data-action="resolve-gap" data-entity-id="${escHtml(entry.entity_id || "")}" ${eligible ? "" : "disabled"} aria-label="Resolve gap for ${escHtml(entry.entity_id || "")}">resolve gap</button>`;
      if (!eligible) {
        html += `<span class="coverage-action-note">Not operator-completion-eligible at this stage.</span>`;
      } else if (hasCurated) {
        html += `<span class="coverage-action-note">Curator provenance present.</span>`;
      }
      html += `</div>`;
    }

    // Retrieval log preview (first 4 attempts)
    if (Array.isArray(entry.retrieval_attempt_log) && entry.retrieval_attempt_log.length > 0) {
      html += `<ul class="coverage-retrieval-log" aria-label="Retrieval attempts">`;
      entry.retrieval_attempt_log.slice(0, 4).forEach((att) => {
        const outcome = String(att.outcome || "").toLowerCase();
        const cls = outcome === "success" ? "success" : outcome === "error" ? "error" : "";
        const url = sanitizeUrl(att.url);
        html += `<li class="coverage-retrieval-attempt coverage-retrieval-attempt-${cls}">`;
        html += `  <span>${escHtml(att.source || "")}</span>`;
        html += `  <span>HTTP ${escHtml(att.http_status == null ? "—" : att.http_status)}</span>`;
        html += `  <span>${escHtml(att.outcome || "")}</span>`;
        if (url) {
          html += `  <a href="${escHtml(url)}" target="_blank" rel="noopener noreferrer">${escHtml(url)}</a>`;
        }
        html += `</li>`;
      });
      if (entry.retrieval_attempt_log.length > 4) {
        html += `<li class="coverage-retrieval-attempt"><span>+ ${entry.retrieval_attempt_log.length - 4} more attempts</span></li>`;
      }
      html += `</ul>`;
    }

    html += `</li>`;
    return html;
  }

  function renderCoverageView(ir) {
    const root = document.getElementById("view-frame-coverage");
    if (!root) return;
    const shell = root.querySelector(".view-shell");
    if (!shell) return;
    const fc = ir.frame_coverage || {};
    const entries = Array.isArray(fc.entries) ? fc.entries : [];

    let html = "";
    html += renderCoverageSummaryBar(fc, entries.length);
    html += renderCoverageWarning(fc);

    // Group entries by section, preserving original order within each group
    const bySection = new Map();
    entries.forEach((entry) => {
      const sec = entry.section || "(no section)";
      if (!bySection.has(sec)) bySection.set(sec, []);
      bySection.get(sec).push(entry);
    });

    if (bySection.size === 0) {
      html += `<p class="matrix-empty">No frame-coverage entries.</p>`;
    } else {
      bySection.forEach((rows, section) => {
        html += `<div class="coverage-section-group">`;
        html += `<h4 class="coverage-section-title">${escHtml(section)} (${rows.length})</h4>`;
        html += `<ul class="coverage-list">`;
        rows.forEach((entry) => {
          html += renderCoverageRow(entry);
        });
        html += `</ul>`;
        html += `</div>`;
      });
    }
    shell.innerHTML = html;
    wireCoverageInteraction();
  }

  function wireCoverageInteraction() {
    const root = document.getElementById("view-frame-coverage");
    if (!root) return;
    root.querySelectorAll('button[data-action="resolve-gap"]').forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        const row = btn.closest(".coverage-row");
        // Codex M-5 review fix #2: emit the full row context so operator
        // tooling has stable handles. Phase A still passes entity_id;
        // Phase B can rely on slot_id + section + subsection_title.
        const detail = {
          entity_id: btn.dataset.entityId,
          slot_id: row && row.dataset.slotId ? row.dataset.slotId : "",
          status: row && row.querySelector(".coverage-status-badge")
            ? row.querySelector(".coverage-status-badge").textContent.trim()
            : "",
          section: row && row.querySelector(".coverage-row-section")
            ? row.querySelector(".coverage-row-section").textContent.trim()
            : "",
          subsection_title: row && row.querySelector(".coverage-row-subsection")
            ? row.querySelector(".coverage-row-subsection").textContent.trim()
            : "",
        };
        document.dispatchEvent(
          new CustomEvent("polaris:resolve-gap", { detail: detail })
        );
        const original = btn.textContent;
        btn.textContent = "queued";
        btn.disabled = true;
        setTimeout(() => {
          btn.textContent = original;
          btn.disabled = false;
        }, 1500);
      });
    });
  }

  // ---------------------------------------------------------------------
  // M-6: View 4 — Methods + Provenance Bundle
  //
  // The audit-bundle header per FINAL_PLAN.md: run hash, model versions,
  // retrieval stats, abort gates, two-family invariant disclosure,
  // 13 rule checks, evaluator reasons, expected vs actual tier
  // distribution, one-click PDF audit-bundle export.
  // ---------------------------------------------------------------------

  function renderMethodsCard(title, valueHtml, sub) {
    let html = `<div class="methods-card">`;
    html += `<h4 class="methods-card-title">${escHtml(title)}</h4>`;
    html += `<div class="methods-card-value">${valueHtml}</div>`;
    if (sub) html += `<div class="methods-card-sub">${escHtml(sub)}</div>`;
    html += `</div>`;
    return html;
  }

  function renderMethodsKv(rows) {
    let html = `<table class="methods-kv-table"><tbody>`;
    rows.forEach((row) => {
      const [k, v] = row;
      html += `<tr><th>${escHtml(k)}</th><td>${v}</td></tr>`;
    });
    html += `</tbody></table>`;
    return html;
  }

  function renderTwoFamilyBanner(mp) {
    // Codex M-6 review fix: missing model_provenance is a warning state,
    // not silence. Same-family violation gets a distinct red style.
    if (!mp) {
      return (
        `<div class="methods-two-family-banner methods-two-family-banner-warning" role="note">` +
        `<div class="methods-two-family-banner-title">Two-family invariant: NOT RECORDED</div>` +
        `Model provenance was not persisted with this run (legacy artifact). ` +
        `The audit-grade two-family invariant cannot be verified.` +
        `</div>`
      );
    }
    const sameFamily = mp.generator_family && mp.generator_family === mp.evaluator_family;
    const className = sameFamily
      ? "methods-two-family-banner methods-two-family-banner-violation"
      : "methods-two-family-banner";
    const title = sameFamily
      ? "Two-family invariant: VIOLATED"
      : "Two-family invariant: holds";
    const detail = sameFamily
      ? `generator (<strong>${escHtml(mp.generator_family)}</strong>) and evaluator (<strong>${escHtml(mp.evaluator_family)}</strong>) share a family — provenance discipline broken.`
      : `generator family <strong>${escHtml(mp.generator_family || "—")}</strong> + evaluator family <strong>${escHtml(mp.evaluator_family || "—")}</strong> are distinct training lineages, so the evaluator is independent of the generator.`;
    return (
      `<div class="${className}" role="note">` +
      `<div class="methods-two-family-banner-title">${title}</div>` +
      detail +
      `</div>`
    );
  }

  function renderMethodsView(ir) {
    const root = document.getElementById("view-methods");
    if (!root) return;
    const shell = root.querySelector(".view-shell");
    if (!shell) return;

    const m = ir.manifest || {};
    const mp = ir.model_provenance;
    const proto = ir.protocol;
    const tierMix = ir.tier_mix || {};

    let html = "";

    // Export bar — Codex M-6 fix: clarify that the bundle is ZIP, not PDF.
    html += `<div class="methods-export-bar">`;
    html += `<a class="methods-export-btn" href="/api/inspector/runs/${encodeURIComponent(slug)}/audit-bundle.zip" download>Download audit bundle (ZIP)</a>`;
    html += `<span class="methods-card-sub">Procurement-grade reproducibility artifact (canonical V30 files + SHA-256 manifest)</span>`;
    html += `</div>`;

    // Two-family invariant banner
    html += renderTwoFamilyBanner(mp);

    // Top-line cards
    html += `<div class="methods-grid">`;
    html += renderMethodsCard(
      "Run ID",
      `<span class="methods-card-value-large">${escHtml(m.run_id || "—")}</span>`,
      m.created_at_iso || (proto && proto.created_at_iso) || "",
    );
    html += renderMethodsCard(
      "Protocol SHA-256",
      `<span class="methods-card-value-large">${escHtml((m.protocol_sha256 || "").slice(0, 16))}…</span>`,
      `Reproducibility hash`,
    );
    html += renderMethodsCard(
      "Cost",
      `<span class="methods-card-value-large">$${Number(m.cost_usd || 0).toFixed(6)}</span>`,
      `of $${Number(m.budget_cap_usd || 0).toFixed(2)} cap`,
    );
    html += renderMethodsCard(
      "Verified / Dropped",
      `<span class="methods-card-value-large">${escHtml(ir.verified_report?.sentences_verified ?? "—")} / ${escHtml(ir.verified_report?.sentences_dropped ?? "—")}</span>`,
      `${escHtml(m.word_count || 0)} words`,
    );
    html += renderMethodsCard(
      "Evaluator gate",
      `<span class="methods-card-value-large">${escHtml((m.evaluator_gate && m.evaluator_gate.gate_class) || "—")}</span>`,
      `release_allowed=${escHtml(m.release_allowed)}`,
    );
    html += renderMethodsCard(
      "Contradictions",
      `<span class="methods-card-value-large">${escHtml(m.contradictions_found || 0)}</span>`,
      `disclosed in report`,
    );
    html += `</div>`;

    // Models section
    html += `<div class="methods-section">`;
    html += `<h4 class="methods-section-title">Model provenance</h4>`;
    if (mp) {
      const rows = [
        ["Generator family", escHtml(mp.generator_family)],
        ["Generator model", escHtml(mp.generator_model)],
        ["Evaluator family", escHtml(mp.evaluator_family)],
        ["Evaluator model", escHtml(mp.evaluator_model)],
        ["Judge model", escHtml(mp.judge_model)],
        ["Judge parse OK", escHtml(mp.judge_parse_ok)],
        ["Judge tokens (in/out)", `${escHtml(mp.judge_input_tokens)} / ${escHtml(mp.judge_output_tokens)}`],
        ["Contradictions disclosed", escHtml(mp.contradictions_disclosed)],
      ];
      html += renderMethodsKv(rows);
    } else {
      html += `<p class="placeholder">No model provenance recorded.</p>`;
    }
    html += `</div>`;

    // Retrieval stats + queries (Codex M-6 fix: surface queries, not just counts)
    if (m.retrieval_stats) {
      html += `<div class="methods-section">`;
      html += `<h4 class="methods-section-title">Retrieval</h4>`;
      const rs = m.retrieval_stats;
      const rows = [
        ["Pre-filter", escHtml(rs.pre_filter)],
        ["Fetched", escHtml(rs.fetched)],
        ["Failed", escHtml(rs.failed)],
      ];
      const byProvider = rs.by_provider || {};
      Object.keys(byProvider).sort().forEach((k) => {
        rows.push([`provider · ${k}`, escHtml(byProvider[k])]);
      });
      const queries = Array.isArray(rs.queries) ? rs.queries : [];
      if (queries.length > 0) {
        const queryHtml = queries
          .map((q) => `<div class="methods-query-line">${escHtml(q)}</div>`)
          .join("");
        rows.push([`queries (${queries.length})`, queryHtml]);
      } else {
        rows.push(["queries", `<span class="methods-card-sub">not persisted by this run</span>`]);
      }
      html += renderMethodsKv(rows);
      html += `</div>`;
    }

    // Adequacy + corpus approval gates (Codex M-6 fix: surface non-evaluator gates)
    if (ir.adequacy || ir.corpus_approval) {
      html += `<div class="methods-section">`;
      html += `<h4 class="methods-section-title">Pre-generation gates</h4>`;
      const rows = [];
      if (ir.adequacy) {
        const a = ir.adequacy;
        rows.push([
          "Corpus adequacy",
          `decision=<strong>${escHtml(a.decision)}</strong>, findings_ok=${escHtml(a.findings_ok)}/${escHtml(a.findings_total)}, critical=${escHtml(a.critical_count)}`,
        ]);
      }
      if (ir.corpus_approval) {
        const ca = ir.corpus_approval;
        rows.push([
          "Corpus approval",
          `approved=<strong>${escHtml(ca.approved)}</strong>, decided ${escHtml(ca.decision_at_iso)}, ${escHtml(ca.approved_count)} approved / ${escHtml(ca.rejected_count)} rejected sources`,
        ]);
        if (ca.user_note) {
          rows.push(["Operator note", `<em>${escHtml(ca.user_note)}</em>`]);
        }
      }
      html += renderMethodsKv(rows);
      html += `</div>`;
    }

    // Evaluator gate detail
    if (m.evaluator_gate) {
      const eg = m.evaluator_gate;
      html += `<div class="methods-section">`;
      html += `<h4 class="methods-section-title">Evaluator gate detail</h4>`;
      const rows = [
        ["Gate class", escHtml(eg.gate_class)],
        ["Release allowed", escHtml(eg.release_allowed)],
        ["Reasons", (eg.reasons || []).map((r) => `<div>${escHtml(r)}</div>`).join("") || "—"],
        ["Rule blockers", (eg.rule_blockers || []).map((r) => `<div>${escHtml(r)}</div>`).join("") || "—"],
        ["Qwen critical axes", (eg.qwen_critical_axes || []).map((a) => `<div>${escHtml(a)}</div>`).join("") || "—"],
        ["Qwen parse OK", escHtml(eg.qwen_parse_ok)],
      ];
      html += renderMethodsKv(rows);
      html += `</div>`;
    }

    // V30 warnings
    if (Array.isArray(m.v30_warnings) && m.v30_warnings.length > 0) {
      html += `<div class="methods-section">`;
      html += `<h4 class="methods-section-title">V30 warnings</h4>`;
      const rows = m.v30_warnings.map((w, i) => [`warning ${i + 1}`, escHtml(w)]);
      html += renderMethodsKv(rows);
      html += `</div>`;
    }

    // Pre-commit rule checks
    if (mp && Array.isArray(mp.rule_checks) && mp.rule_checks.length > 0) {
      html += `<div class="methods-section">`;
      html += `<h4 class="methods-section-title">Pre-commit rule checks (${mp.rule_checks.length})</h4>`;
      html += `<ul class="methods-rule-list">`;
      mp.rule_checks.forEach((rc) => {
        const status = rc.passed ? "pass" : "fail";
        const cls = rc.passed ? "methods-rule-pass" : "methods-rule-fail";
        html += `<li class="methods-rule-row">`;
        html += `<span class="methods-rule-id">${escHtml(rc.item_id)}</span>`;
        html += `<span class="methods-rule-name">${escHtml(rc.name)}</span>`;
        html += `<span class="methods-rule-status ${cls}">${status}</span>`;
        html += `</li>`;
        if (rc.details) {
          html += `<li class="methods-rule-row" style="margin-left:10px"><span class="methods-rule-name" style="font-style:italic;color:var(--text-mute)">${escHtml(rc.details)}</span></li>`;
        }
      });
      html += `</ul>`;
      html += `</div>`;
    }

    // Protocol metadata
    if (proto) {
      html += `<div class="methods-section">`;
      html += `<h4 class="methods-section-title">Protocol</h4>`;
      const rows = [
        ["Research question", escHtml(proto.research_question || "—")],
        ["Created at (ISO)", escHtml(proto.created_at_iso || "—")],
        ["Scope decision", escHtml(proto.scope_decision || "—")],
      ];
      html += renderMethodsKv(rows);
      html += `</div>`;
    }

    // Expected vs actual tier distribution (Codex M-6 fix: nullish-safe
    // parsing for explicit 0 max_fraction; residual rows for unexpected
    // actual tiers absent from the protocol).
    if (proto && Array.isArray(proto.expected_tier_distribution) && proto.expected_tier_distribution.length > 0) {
      html += `<div class="methods-section">`;
      html += `<h4 class="methods-section-title">Expected vs actual tier distribution</h4>`;
      const kvRows = [];
      const expectedTiers = new Set();
      const numOrZero = (v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
      };
      const numOrOne = (v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 1;
      };

      proto.expected_tier_distribution.forEach((exp) => {
        const tier = exp.tier;
        expectedTiers.add(tier);
        const actual = numOrZero((tierMix.fractions || {})[tier]);
        // Use nullish-safe parsing: explicit min_fraction=0 must stay 0
        // (not be coerced to a default), and max_fraction=0 must mean
        // "this tier is forbidden" rather than max=1.
        const minF = exp.min_fraction == null ? 0 : numOrZero(exp.min_fraction);
        const maxF = exp.max_fraction == null ? 1 : numOrOne(exp.max_fraction);
        const inBand = actual >= minF && actual <= maxF;
        const pctActual = (actual * 100).toFixed(1) + "%";
        const pctMin = (minF * 100).toFixed(0) + "%";
        const pctMax = (maxF * 100).toFixed(0) + "%";
        const flag = inBand
          ? `<span class="methods-rule-pass">in band</span>`
          : `<span class="methods-rule-fail">out of band</span>`;
        kvRows.push([
          escHtml(tier),
          `actual ${pctActual}, expected ${pctMin}–${pctMax} &nbsp;·&nbsp; ${flag}`,
        ]);
      });

      // Residual rows: tiers present in actual distribution but absent
      // from the protocol's expected list — silent drift would be
      // invisible without this row.
      const residualTiers = Object.keys(tierMix.fractions || {})
        .filter((t) => !expectedTiers.has(t))
        .filter((t) => Number((tierMix.fractions || {})[t] || 0) > 0)
        .sort();
      residualTiers.forEach((tier) => {
        const actual = numOrZero((tierMix.fractions || {})[tier]);
        const pctActual = (actual * 100).toFixed(1) + "%";
        kvRows.push([
          escHtml(tier),
          `actual ${pctActual} &nbsp;·&nbsp; <span class="methods-rule-fail">unexpected (no band declared)</span>`,
        ]);
      });

      html += renderMethodsKv(kvRows);
      html += `</div>`;
    }

    shell.innerHTML = html;
  }

  // ---------------------------------------------------------------------
  // M-7: View 5 — Source Tier Mix
  //
  // Visualizes corpus-level tier distribution per FINAL_PLAN.md:
  // - Visual T1/T2/T3/... bar (large, segments labeled with %)
  // - Headline cards: corpus count, dominant tier, T1 share, deviation flag
  // - Promo-adjective count badge (V30 run-14 = 1 vs Gemini = 58)
  // - Per-tier expected-vs-actual band table with band-bracket SVG-like
  //   visual showing min, max, and where actual falls
  // - Material-deviation banner if manifest.corpus.material_deviation=true
  // ---------------------------------------------------------------------

  // Calibrated promo-adjective lexicon. Codex M-7 review fix: derived from
  // direct comparator scan against state/compare_gemini_dr.txt (yields ~54
  // hits = FINAL_PLAN's documented "58 vs 1" calibration story) while
  // run-14 gives exactly 1 ("superior" in narrative prose).
  // Excludes high-frequency clinical hedges like "significant"/"most" that
  // would create false positives in legitimate clinical reports.
  const _PROMO_PATTERNS = [
    /\bmassive\b/gi,
    /\bsuperior\b/gi,
    /\bdefinitive\b/gi,
    /\bdefinitively\b/gi,
    /\bdecisive\b/gi,
    /\bdecisively\b/gi,
    /\bastonishing\b/gi,
    /\bgold[- ]standard\b/gi,
    /\blandmark\b/gi,
    /\bdramatically\b/gi,
    /\bremarkable\b/gi,
    /\bremarkably\b/gi,
    /\bextraordinary\b/gi,
    /\bunmatched\b/gi,
    /\bunparalleled\b/gi,
    /\binnovative\b/gi,
    /\bbreakthrough\b/gi,
    /\brevolutionary\b/gi,
    /\bunprecedented\b/gi,
    /\bcutting[- ]edge\b/gi,
    /\bgroundbreaking\b/gi,
    /\bworld[- ]class\b/gi,
    /\bbest[- ]in[- ]class\b/gi,
    /\bnext[- ]generation\b/gi,
    /\bgame[- ]changing\b/gi,
    /\btransformative\b/gi,
    /\bstriking\b/gi,
    /\bprofoundly\b/gi,
    /\bparadigm(?:[- ]shift)?\b/gi,
    /\bunmistakable\b/gi,
    /\bhighly[- ]effective\b/gi,
    /\brobust\b/gi,
    /\bpowerful\b/gi,
    /\bimpressive\b/gi,
    /\bimpressively\b/gi,
  ];

  // Codex M-7 review fix: promo counting must be NARRATIVE-ONLY. Strip
  // markdown tables (rows starting with '|') and bibliography sections
  // before scanning so duplicated values in trial-summary tables don't
  // double-count.
  function _stripTablesAndBibliography(md) {
    if (!md || typeof md !== "string") return "";
    const lines = md.split("\n");
    const out = [];
    let inBiblio = false;
    for (const line of lines) {
      const lc = line.toLowerCase().trim();
      if (lc.startsWith("## bibliography") || lc.startsWith("### bibliography") ||
          lc.startsWith("## references") || lc.startsWith("### references")) {
        inBiblio = true;
        continue;
      }
      if (inBiblio && line.startsWith("## ")) {
        inBiblio = false;
      }
      if (inBiblio) continue;
      // Drop github-pipe table rows (header, separator, body).
      if (/^\s*\|/.test(line)) continue;
      out.push(line);
    }
    return out.join("\n");
  }

  function countPromoAdjectives(text) {
    if (!text || typeof text !== "string") return 0;
    const narrative = _stripTablesAndBibliography(text);
    let count = 0;
    _PROMO_PATTERNS.forEach((re) => {
      const matches = narrative.match(re);
      if (matches) count += matches.length;
    });
    return count;
  }

  // Codex M-7 review fix: marker positioning must clamp to 0..1 AND the
  // marker is 2px wide so the right edge needs `transform: translateX(-1px)`
  // (or, simpler, treat 99.x% as the rightmost render point).
  function _bandMarkerLeftPct(actualFrac) {
    const clamped = Math.max(0, Math.min(actualFrac, 1));
    // Cap at 99.5% so the 2px marker stays visible on the inside of the
    // graphic edge instead of overflowing.
    const capped = Math.min(clamped, 0.995);
    return (capped * 100).toFixed(2) + "%";
  }

  function renderTierBandRow(tier, actualFrac, minF, maxF) {
    const inBand = actualFrac >= minF && actualFrac <= maxF;
    const pctActual = (actualFrac * 100).toFixed(1) + "%";
    const pctMin = (minF * 100).toFixed(0) + "%";
    const pctMax = (maxF * 100).toFixed(0) + "%";
    const flag = inBand
      ? `<span class="methods-rule-pass">in band</span>`
      : `<span class="methods-rule-fail">out of band</span>`;
    const bracketLeft = (Math.max(0, minF) * 100).toFixed(2) + "%";
    const bracketWidth = (Math.max(0, Math.min(maxF, 1) - Math.max(0, minF)) * 100).toFixed(2) + "%";
    const markerLeft = _bandMarkerLeftPct(actualFrac);
    const markerCls = inBand ? "tier-mix-band-actual-in" : "tier-mix-band-actual-out";
    const graphic =
      `<div class="tier-mix-band-graphic">` +
      `  <div class="tier-mix-band-bracket" style="left:${bracketLeft};width:${bracketWidth}"></div>` +
      `  <div class="tier-mix-band-actual ${markerCls}" style="left:${markerLeft}" title="${escHtml(tier)} actual ${pctActual}"></div>` +
      `</div>`;
    return (
      `<tr>` +
      `<td>${tierBadgeHtml(tier)}</td>` +
      `<td>${escHtml(pctActual)}</td>` +
      `<td>${escHtml(pctMin)} – ${escHtml(pctMax)}</td>` +
      `<td>${graphic}</td>` +
      `<td>${flag}</td>` +
      `</tr>`
    );
  }

  function renderTierResidualRow(tier, actualFrac) {
    const pctActual = (actualFrac * 100).toFixed(1) + "%";
    return (
      `<tr class="tier-mix-row-residual">` +
      `<td>${tierBadgeHtml(tier)}</td>` +
      `<td>${escHtml(pctActual)}</td>` +
      `<td>—</td>` +
      `<td><div class="tier-mix-band-graphic"><div class="tier-mix-band-actual tier-mix-band-actual-out" style="left:${_bandMarkerLeftPct(actualFrac)}"></div></div></td>` +
      `<td><span class="methods-rule-fail">unexpected (no band declared)</span></td>` +
      `</tr>`
    );
  }

  // Codex M-7 review fix: per-section tier breakdown derived from the
  // verified report. Each verified sentence has tokens[].evidence_id;
  // bibliography maps evidence_id -> tier. So per-section tier counts =
  // tokens citing each tier in each section's verified sentences.
  // (frame_coverage.provenance_class is NOT used because in run-14 it
  // would collapse most rows to T1 abstract_only and misrepresent the mix.)
  function _computePerSectionTiers(ir) {
    const bibByEvidenceId = {};
    (ir.bibliography || []).forEach((b) => {
      if (b.evidence_id) bibByEvidenceId[b.evidence_id] = b;
    });
    const sections = (ir.verified_report && ir.verified_report.sections) || [];
    const out = [];
    sections.forEach((section) => {
      const counts = {};
      let total = 0;
      (section.sentences || []).forEach((sentence) => {
        if (!sentence.is_verified) return;  // narrative-only
        (sentence.tokens || []).forEach((tok) => {
          const bib = bibByEvidenceId[tok.evidence_id];
          if (!bib) return;
          const tier = validateTier(bib.tier);
          counts[tier] = (counts[tier] || 0) + 1;
          total += 1;
        });
      });
      if (total > 0) {
        out.push({
          title: section.title,
          total: total,
          counts: counts,
          fractions: Object.fromEntries(
            Object.entries(counts).map(([t, c]) => [t, c / total]),
          ),
        });
      }
    });
    return out;
  }

  function renderPerSectionTierBreakdown(ir) {
    const perSection = _computePerSectionTiers(ir);
    if (perSection.length === 0) {
      return `<p class="placeholder">No verified sentences with bibliographically-typed evidence.</p>`;
    }
    const orderedAll = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "UNKNOWN"];
    let html = `<table class="tier-mix-table"><thead><tr>`;
    html += `<th>Section</th>`;
    html += `<th>Citations</th>`;
    html += `<th>Tier mix</th>`;
    html += `</tr></thead><tbody>`;
    perSection.forEach((section) => {
      html += `<tr>`;
      html += `<td>${escHtml(section.title)}</td>`;
      html += `<td>${escHtml(section.total)}</td>`;
      html += `<td><div class="tier-mix-section-bar" style="height:14px">`;
      orderedAll.forEach((tier) => {
        const f = Number(section.fractions[tier] || 0);
        if (f <= 0) return;
        const pct = (f * 100).toFixed(1);
        html += `<div class="tier-mix-segment-large tier-segment-${tier.toLowerCase()}" style="flex:${f};font-size:9px" title="${escHtml(tier)}: ${pct}%">${f >= 0.10 ? `${escHtml(tier)} ${pct}%` : ""}</div>`;
      });
      html += `</div></td>`;
      html += `</tr>`;
    });
    html += `</tbody></table>`;
    return html;
  }

  function renderTierMixView(ir) {
    const root = document.getElementById("view-tier-mix");
    if (!root) return;
    const shell = root.querySelector(".view-shell");
    if (!shell) return;

    const tm = ir.tier_mix || { fractions: {} };
    const proto = ir.protocol;
    const fractions = tm.fractions || {};
    const orderedAll = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "UNKNOWN"];
    const ordered = orderedAll.filter((t) => Number(fractions[t] || 0) > 0);

    // Dominant tier
    let dominantTier = "—";
    let dominantFrac = 0;
    Object.entries(fractions).forEach(([t, v]) => {
      const num = Number(v);
      if (Number.isFinite(num) && num > dominantFrac) {
        dominantFrac = num;
        dominantTier = t;
      }
    });

    // T1 share
    const t1Frac = Number(fractions.T1 || 0);

    // Promo-adjective count from the rendered report.md (loaded into POLARIS_IR.report_md)
    const promoCount = countPromoAdjectives(ir.report_md || "");
    let promoCls = "tier-mix-promo-badge-good";
    let promoLabel = "well-calibrated";
    if (promoCount >= 5) {
      promoCls = "tier-mix-promo-badge-warn";
      promoLabel = "elevated";
    }
    if (promoCount >= 15) {
      promoCls = "tier-mix-promo-badge-bad";
      promoLabel = "promotional drift";
    }

    let html = "";

    // Material-deviation banner (if applicable)
    if (tm.material_deviation) {
      html += `<div class="tier-mix-banner tier-mix-deviation-warning" role="note">`;
      html += `<strong>Material tier deviation flagged.</strong> The corpus tier distribution deviates materially from the protocol's expected band. The corpus_approval gate evaluated this and accepted; see Methods + Provenance for the operator note.`;
      html += `</div>`;
    } else {
      html += `<div class="tier-mix-banner" role="note">`;
      html += `Tier distribution is the corpus-level provenance audit. Each tier slot carries an expected band from the protocol; bars show where actual falls. Distinct tier hierarchy: T1 (RCTs / primary trials) > T2 (systematic reviews) > T3 (regulatory) > T4 (narrative review) > T5 (industry HCP) > T6 (other) > T7 (general) > UNKNOWN.`;
      html += `</div>`;
    }

    // Headline cards
    html += `<div class="tier-headline">`;
    html += `<div class="tier-headline-card">`;
    html += `  <div class="tier-headline-label">Corpus size</div>`;
    html += `  <div class="tier-headline-value">${escHtml(tm.corpus_count || 0)}</div>`;
    html += `  <div class="tier-headline-sub">sources retrieved</div>`;
    html += `</div>`;

    html += `<div class="tier-headline-card">`;
    html += `  <div class="tier-headline-label">Dominant tier</div>`;
    html += `  <div class="tier-headline-value">${escHtml(dominantTier)} (${(dominantFrac * 100).toFixed(1)}%)</div>`;
    html += `  <div class="tier-headline-sub">largest fraction in corpus</div>`;
    html += `</div>`;

    html += `<div class="tier-headline-card">`;
    html += `  <div class="tier-headline-label">T1 share</div>`;
    html += `  <div class="tier-headline-value">${(t1Frac * 100).toFixed(1)}%</div>`;
    html += `  <div class="tier-headline-sub">primary RCT / pivotal trial sources</div>`;
    html += `</div>`;

    html += `<div class="tier-headline-card">`;
    html += `  <div class="tier-headline-label">Promotional adjectives</div>`;
    html += `  <div class="tier-mix-headline-row">`;
    html += `    <div class="tier-headline-value">${escHtml(promoCount)}</div>`;
    html += `    <span class="tier-mix-promo-badge ${promoCls}">${escHtml(promoLabel)}</span>`;
    html += `  </div>`;
    html += `  <div class="tier-headline-sub">in report.md (calibration signal)</div>`;
    html += `</div>`;
    html += `</div>`;

    // Visual tier bar (large)
    html += `<div class="tier-mix-bar-large" role="img" aria-label="Tier distribution: ${ordered.map((t) => `${t} ${(Number(fractions[t]) * 100).toFixed(1)}%`).join(", ")}">`;
    ordered.forEach((tier) => {
      const f = Number(fractions[tier] || 0);
      const pct = (f * 100).toFixed(1);
      html += `<div class="tier-mix-segment-large tier-segment-${tier.toLowerCase()}" style="flex:${f}" title="${escHtml(tier)}: ${pct}%">${f >= 0.05 ? `${escHtml(tier)} ${pct}%` : ""}</div>`;
    });
    html += `</div>`;

    // Tick-row labels for tiers that fell below 5% (couldn't show in segment)
    html += `<div class="tier-mix-bar-tick-row">`;
    ordered.forEach((tier) => {
      const f = Number(fractions[tier] || 0);
      const pct = (f * 100).toFixed(1);
      html += `<div class="tier-mix-tick" style="flex:${f}">${f < 0.05 ? `${escHtml(tier)} ${pct}%` : ""}</div>`;
    });
    html += `</div>`;

    // Expected-vs-actual table
    if (proto && Array.isArray(proto.expected_tier_distribution) && proto.expected_tier_distribution.length > 0) {
      html += `<table class="tier-mix-table"><thead><tr>`;
      html += `<th>Tier</th><th>Actual</th><th>Expected</th><th>Band</th><th>Status</th>`;
      html += `</tr></thead><tbody>`;

      const expectedTiers = new Set();
      const numOrZero = (v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
      };
      const numOrOne = (v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 1;
      };
      proto.expected_tier_distribution.forEach((exp) => {
        const tier = exp.tier;
        expectedTiers.add(tier);
        const actual = numOrZero(fractions[tier]);
        const minF = exp.min_fraction == null ? 0 : numOrZero(exp.min_fraction);
        const maxF = exp.max_fraction == null ? 1 : numOrOne(exp.max_fraction);
        html += renderTierBandRow(tier, actual, minF, maxF);
      });
      // Residual rows for unexpected tiers
      Object.keys(fractions)
        .filter((t) => !expectedTiers.has(t))
        .filter((t) => Number(fractions[t] || 0) > 0)
        .sort()
        .forEach((tier) => {
          const actual = numOrZero(fractions[tier]);
          html += renderTierResidualRow(tier, actual);
        });

      html += `</tbody></table>`;
    } else {
      html += `<p class="placeholder">No protocol-declared expected tier distribution available for this run.</p>`;
    }

    // Per-section tier breakdown (Codex M-7 review fix: FINAL_PLAN
    // requirement was missing from M-7 v1).
    html += `<div class="tier-mix-section-stats">`;
    html += `<h4 class="methods-section-title">Per-section tier breakdown</h4>`;
    html += `<p class="methods-card-sub" style="margin-bottom:10px">Derived from verified-sentence citations: each token's evidence_id is resolved to a bibliography tier, then aggregated per section. Dropped sentences and unmapped evidence_ids are excluded.</p>`;
    html += renderPerSectionTierBreakdown(ir);
    html += `</div>`;

    shell.innerHTML = html;
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
      renderCoverageView(ir);
      renderMethodsView(ir);
      renderTierMixView(ir);
      return renderReportView(ir);
    })
    .catch((err) => {
      const shell = document.getElementById("report-shell");
      if (shell) {
        shell.innerHTML = `<p class="placeholder">Failed to load run: ${escHtml(err.message)}</p>`;
      }
    });
})();
