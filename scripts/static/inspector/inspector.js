// POLARIS Evidence Inspector — Phase A scaffold (M-2).
// View 1 click-to-inspect interaction wires in M-3.
// Views 2-5 wire in M-4..M-7.

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
  // Load AuditIR for this run + render initial scaffolding
  // ---------------------------------------------------------------------
  async function loadIR() {
    const resp = await fetch(`/api/inspector/runs/${encodeURIComponent(slug)}`);
    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(`Failed to load IR (${resp.status}): ${err}`);
    }
    return resp.json();
  }

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

  function renderReportShellPlaceholder(ir) {
    const shell = document.getElementById("report-shell");
    if (!shell) return;
    const m = ir.manifest || {};
    const proto = ir.protocol || {};
    shell.innerHTML = "";
    const heading = document.createElement("h1");
    heading.textContent = m.question || proto.research_question || slug;
    shell.appendChild(heading);
    const meta = document.createElement("p");
    meta.style.color = "var(--text-dim)";
    meta.style.fontFamily = "var(--mono)";
    meta.style.fontSize = "12px";
    meta.textContent =
      `run_id=${m.run_id || "—"}  ·  status=${m.status || "—"}  ·  ` +
      `cost=$${(m.cost_usd || 0).toFixed(4)}  ·  words=${m.word_count || 0}  ·  ` +
      `contradictions=${m.contradictions_found || 0}`;
    shell.appendChild(meta);
    const note = document.createElement("p");
    note.className = "placeholder";
    note.textContent =
      "Report rendering with click-to-inspect citations wires in M-3. " +
      "AuditIR is loaded; spans are bound; this is the M-2 skeleton.";
    shell.appendChild(note);
  }

  loadIR()
    .then((ir) => {
      window.POLARIS_IR = ir;  // M-3..M-7 read from here
      renderTierStrip(ir);
      renderTabCounts(ir);
      renderReportShellPlaceholder(ir);
    })
    .catch((err) => {
      const shell = document.getElementById("report-shell");
      if (shell) {
        shell.innerHTML = `<p class="placeholder">Failed to load run: ${err.message}</p>`;
      }
    });
})();
