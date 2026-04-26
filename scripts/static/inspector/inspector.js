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

  // Extract canonical identifiers (DOI, PMID, full URL stem) from a URL.
  // Used to bridge bibliography (surpass_X / entity-anchored) and
  // contradiction (ev_NNN / corpus-anchored) namespaces in run-14 by
  // matching on shared DOI/PMID even when evidence_ids differ.
  function extractIdentifiers(url) {
    const out = new Set();
    const s = String(url == null ? "" : url).trim();
    if (!s) return out;
    // DOI: 10.NNNN/anything (case-insensitive)
    const doiMatch = s.match(/\b10\.\d{4,9}\/[^\s?#&]+/i);
    if (doiMatch) out.add("doi:" + doiMatch[0].toLowerCase());
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
      if (fcEntry.doi) ids.add("doi:" + String(fcEntry.doi).toLowerCase());
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
  // Boot
  // ---------------------------------------------------------------------
  fetchJSON(`/api/inspector/runs/${encodeURIComponent(slug)}`)
    .then((ir) => {
      window.POLARIS_IR = ir;
      renderTierStrip(ir);
      renderTabCounts(ir);
      return renderReportView(ir);
    })
    .catch((err) => {
      const shell = document.getElementById("report-shell");
      if (shell) {
        shell.innerHTML = `<p class="placeholder">Failed to load run: ${escHtml(err.message)}</p>`;
      }
    });
})();
