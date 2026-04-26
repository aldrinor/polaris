// POLARIS Evidence Inspector — Phase A.
// M-2 wired the shell + tabs + tier strip.
// M-3 wires View 1: rendered report with click-to-inspect citations.

(function () {
  "use strict";

  const slug = window.POLARIS_RUN_SLUG;
  if (!slug) {
    console.error("POLARIS_RUN_SLUG not set; cannot load run");
    return;
  }

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
    // Indexes for click-to-inspect lookups.
    const bibByNum = {};
    (ir.bibliography || []).forEach((b) => {
      bibByNum[String(b.num)] = b;
    });

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

    const contradictionsByEvidenceId = {};
    (ir.contradictions || []).forEach((cluster) => {
      (cluster.claims || []).forEach((claim) => {
        if (!claim.evidence_id) return;
        if (!contradictionsByEvidenceId[claim.evidence_id]) {
          contradictionsByEvidenceId[claim.evidence_id] = [];
        }
        contradictionsByEvidenceId[claim.evidence_id].push({
          cluster: cluster,
          claim: claim,
        });
      });
    });

    return { bibByNum, sentencesByEvidenceId, contradictionsByEvidenceId };
  }

  function tierBadge(tier) {
    const t = String(tier || "UNKNOWN").toUpperCase();
    return `<span class="tier-badge tier-badge-${t.toLowerCase()}">${t}</span>`;
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderEvidencePane(num, ir, idx) {
    const bib = idx.bibByNum[String(num)];
    const pane = document.getElementById("evidence-pane");
    const body = pane.querySelector(".evidence-pane-body");
    const header = pane.querySelector(".evidence-pane-header h3");

    if (!bib) {
      header.textContent = `Citation [${num}] — unresolved`;
      body.innerHTML = `<p class="placeholder">No bibliography entry for [${num}].</p>`;
      pane.hidden = false;
      pane.setAttribute("aria-hidden", "false");
      document.body.classList.add("evidence-pane-open");
      return;
    }

    const eid = bib.evidence_id;
    const sentences = idx.sentencesByEvidenceId[eid] || [];
    const contradictions = idx.contradictionsByEvidenceId[eid] || [];

    header.textContent = `Citation [${num}] — ${eid}`;

    let html = "";
    html += `<section class="evidence-block evidence-bib">`;
    html += `  <div class="evidence-block-row">`;
    html += `    ${tierBadge(bib.tier)}`;
    html += `    <span class="evidence-eid">${escHtml(eid)}</span>`;
    html += `  </div>`;
    html += `  <p class="evidence-statement">${escHtml(bib.statement)}</p>`;
    if (bib.url) {
      html += `  <p class="evidence-url"><a href="${escHtml(
        bib.url
      )}" target="_blank" rel="noopener">${escHtml(bib.url)}</a></p>`;
    }
    html += `</section>`;

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
        html += `    <span class="evidence-sentence-status status-${cls}">${label}</span>`;
        html += `    <span class="evidence-sentence-span">span ${s.token.start}–${s.token.end}</span>`;
        html += `  </div>`;
        html += `  <p class="evidence-sentence-text">${escHtml(s.sentence.text)}</p>`;
        if (!verified && (s.sentence.failure_reasons || []).length > 0) {
          html += `<p class="evidence-sentence-fail">drop: ${escHtml(
            s.sentence.failure_reasons.join("; ")
          )}</p>`;
        }
        html += `</li>`;
      });
      html += `</ul>`;
    }
    html += `</section>`;

    html += `<section class="evidence-block">`;
    html += `  <h4 class="evidence-block-title">Contradictions involving this evidence (${contradictions.length})</h4>`;
    if (contradictions.length === 0) {
      html += `<p class="placeholder">No contradiction clusters reference this evidence.</p>`;
    } else {
      html += `<ul class="evidence-contradictions">`;
      contradictions.forEach((c) => {
        html += `<li>`;
        html += `  <div class="evidence-contradiction-meta">`;
        html += `    <span class="severity severity-${escHtml(c.cluster.severity)}">${escHtml(c.cluster.severity)}</span>`;
        html += `    <span class="cluster-predicate">${escHtml(c.cluster.subject || "")} · ${escHtml(c.cluster.predicate)}</span>`;
        html += `  </div>`;
        html += `  <p class="evidence-contradiction-claim">value=${escHtml(c.claim.value)} ${escHtml(c.claim.unit)} (arm ${escHtml(c.claim.arm)}, dose ${escHtml(c.claim.dose)})</p>`;
        if (c.cluster.recommended_action) {
          html += `<p class="evidence-contradiction-action">${escHtml(c.cluster.recommended_action)}</p>`;
        }
        html += `</li>`;
      });
      html += `</ul>`;
    }
    html += `</section>`;

    body.innerHTML = html;
    pane.hidden = false;
    pane.setAttribute("aria-hidden", "false");
    document.body.classList.add("evidence-pane-open");
  }

  function closeEvidencePane() {
    const pane = document.getElementById("evidence-pane");
    pane.hidden = true;
    pane.setAttribute("aria-hidden", "true");
    document.body.classList.remove("evidence-pane-open");
    document.querySelectorAll(".citation.active").forEach((el) =>
      el.classList.remove("active")
    );
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
      renderEvidencePane(num, ir, idx);
    });
    // Keyboard activation for citations
    shell.addEventListener("keydown", (event) => {
      const target = event.target.closest("a.citation");
      if (!target) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        target.click();
      }
    });
    const closeBtn = document.querySelector(".evidence-pane-close");
    if (closeBtn) closeBtn.addEventListener("click", closeEvidencePane);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeEvidencePane();
    });
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
        shell.innerHTML = `<p class="placeholder">Failed to load run: ${err.message}</p>`;
      }
    });
})();
