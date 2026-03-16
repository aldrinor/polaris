/* =====================================================================
   citation_chain.js — Sprint 2: Chain of Custody Citation Modal
   POLARIS Live Dashboard

   Replaces the simple showCitePopover() with a multi-panel modal
   showing full citation traceability:
     Tab 1: Source Summary (title, tier, verification badge, relevance)
     Tab 2: Source Preview (sandboxed iframe + mark.js highlighting)
     Tab 3: Reasoning Chain (A→B→C→D traceability)
     Tab 4: Source Metadata (URL, year, authors, type, NLI scores)

   Dependencies: core.js (state, esc, truncStr, showToast), mark.min.js
   ===================================================================== */

/* =====================================================================
   Modal DOM creation (one-time, appended to <body>)
   ===================================================================== */
var _chainModal = null;
var _chainModalData = null;
var _pendingTab = null;

function _ensureChainModal() {
  if (_chainModal) return;
  var modal = document.createElement("div");
  modal.id = "citation-chain-modal";
  modal.className = "chain-modal-overlay";
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-label", "Citation chain of custody");
  modal.innerHTML =
    '<div class="chain-modal">' +
      '<div class="chain-modal-header">' +
        '<span class="chain-modal-title" id="chain-title">Citation [N]</span>' +
        '<button class="chain-modal-close" onclick="closeCitationChain()" aria-label="Close">&times;</button>' +
      '</div>' +
      '<div class="chain-tabs">' +
        '<button class="chain-tab active" data-tab="summary" onclick="switchChainTab(\'summary\')">Summary</button>' +
        '<button class="chain-tab" data-tab="preview" onclick="switchChainTab(\'preview\')">Source Preview</button>' +
        '<button class="chain-tab" data-tab="reasoning" onclick="switchChainTab(\'reasoning\')">Reasoning Chain</button>' +
        '<button class="chain-tab" data-tab="metadata" onclick="switchChainTab(\'metadata\')">Metadata</button>' +
      '</div>' +
      '<div class="chain-body">' +
        '<div class="chain-pane active" id="chain-pane-summary"></div>' +
        '<div class="chain-pane" id="chain-pane-preview"></div>' +
        '<div class="chain-pane" id="chain-pane-reasoning"></div>' +
        '<div class="chain-pane" id="chain-pane-metadata"></div>' +
      '</div>' +
    '</div>';
  document.body.appendChild(modal);
  _chainModal = modal;

  // Close on overlay click
  modal.addEventListener("click", function(e) {
    if (e.target === modal) closeCitationChain();
  });

  // Close on Escape
  document.addEventListener("keydown", function(e) {
    if (e.key === "Escape" && _chainModal && _chainModal.classList.contains("visible")) {
      closeCitationChain();
    }
  });
}

/* =====================================================================
   Public API: showCitationChain(event, citationNumber)
   Called from citation click handlers in the report view.
   ===================================================================== */
function showCitationChain(event, num) {
  if (event) event.stopPropagation();
  _ensureChainModal();

  // FIX-B2: Reset preview loaded flag so each citation gets fresh preview
  _previewLoaded = false;
  _pendingTab = null;

  var titleEl = document.getElementById("chain-title");
  if (titleEl) titleEl.textContent = "Citation [" + num + "]";

  // Show loading state
  _setChainLoading(true);
  _chainModal.classList.add("visible");
  document.body.style.overflow = "hidden";

  // Fetch chain data from API
  var vid = state.vectorId;
  if (!vid) {
    _renderChainError("No research result loaded.");
    return;
  }

  fetch("/api/research/chain/" + encodeURIComponent(vid) + "/" + num)
    .then(function(res) {
      if (!res.ok) throw new Error("Chain API error: " + res.status);
      return res.json();
    })
    .then(function(data) {
      if (!_chainModal || !_chainModal.classList.contains("visible")) return;
      _chainModalData = data;
      _setChainLoading(false);
      _renderSummaryTab(data, num);
      _renderReasoningTab(data, num);
      _renderMetadataTab(data, num);
      if (_pendingTab === "preview") {
        _pendingTab = null;
        // switchChainTab will call _renderPreviewTab since _chainModalData is now set
        switchChainTab("preview");
      } else {
        // Respect whatever tab the user already switched to; default to summary
        // only if still on the initial loading state (summary is default)
        var activeBtn = document.querySelector(".chain-tab.active");
        var currentTab = activeBtn ? activeBtn.dataset.tab : "summary";
        switchChainTab(currentTab);
      }
    })
    .catch(function(err) {
      _pendingTab = null;
      _setChainLoading(false);
      _renderChainError("Failed to load citation chain: " + err.message);
      switchChainTab("summary");
    });
}

function closeCitationChain() {
  if (_chainModal) {
    _chainModal.classList.remove("visible");
    document.body.style.overflow = "";
    _chainModalData = null;
    _pendingTab = null;
    // Clean up iframe
    var iframe = document.getElementById("chain-preview-iframe");
    if (iframe) iframe.srcdoc = "";
  }
}

function switchChainTab(tab) {
  document.querySelectorAll(".chain-tab").forEach(function(btn) {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
  document.querySelectorAll(".chain-pane").forEach(function(pane) {
    pane.classList.toggle("active", pane.id === "chain-pane-" + tab);
  });

  if (tab === "preview") {
    if (_chainModalData) {
      _renderPreviewTab(_chainModalData);
    } else {
      _pendingTab = "preview";
    }
  } else {
    _pendingTab = null;
  }
}

/* =====================================================================
   Tab Renderers
   ===================================================================== */

function _setChainLoading(loading) {
  var panes = document.querySelectorAll(".chain-pane");
  panes.forEach(function(p) {
    if (loading) {
      p.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-tertiary)"><div class="spinner" style="margin:0 auto 12px"></div>Loading citation chain...</div>';
    }
  });
}

function _renderChainError(msg) {
  var summaryPane = document.getElementById("chain-pane-summary");
  if (summaryPane) {
    summaryPane.innerHTML = '<div style="text-align:center;padding:40px;color:var(--error)">' + esc(msg) + '</div>';
  }
}

/* --- Tab 1: Summary --- */
function _renderSummaryTab(data, num) {
  var pane = document.getElementById("chain-pane-summary");
  if (!pane) return;
  var src = data.source || {};
  var chain = data.chain || [];
  var html = '';

  // Source card
  html += '<div class="chain-source-card">';
  html += '<div class="chain-source-title">[' + num + '] ' + esc(src.formatted || src.citation_key || "Source") + '</div>';
  if (src.url) {
    html += '<a href="' + esc(src.url) + '" target="_blank" rel="noopener" class="chain-source-url">' + esc(truncStr(src.url, 80)) + '</a>';
  }
  html += '<div class="chain-source-type">' + esc(src.source_type || "web") + '</div>';
  html += '</div>';

  // Evidence summary
  html += '<div class="chain-section-header">Evidence from this source (' + chain.length + ' pieces)</div>';
  chain.forEach(function(ev, i) {
    var tierClass = "tier-" + (ev.quality_tier || "bronze").toLowerCase();
    var verdicts = ev.verification || [];
    var supportedCount = verdicts.filter(function(v) { return v.verdict === "SUPPORTED" || v.is_faithful; }).length;
    var totalVerdicts = verdicts.length;
    var verStatus = totalVerdicts > 0
      ? (supportedCount === totalVerdicts ? "verified" : (supportedCount > 0 ? "partial" : "unverified"))
      : "unverified";
    var verIcon = verStatus === "verified" ? "&#10003;" : (verStatus === "partial" ? "&#9888;" : "&#10007;");
    var verColor = verStatus === "verified" ? "var(--success)" : (verStatus === "partial" ? "var(--warning)" : "var(--error)");

    html += '<div class="chain-evidence-card">';
    html += '<div class="chain-ev-header">';
    html += '<span class="chain-tier-badge ' + tierClass + '">' + esc(ev.quality_tier || "BRONZE") + '</span>';
    html += '<span class="chain-ver-badge" style="color:' + verColor + '">' + verIcon + ' ' + (supportedCount > 0 ? supportedCount + '/' + totalVerdicts + ' claims verified' : 'Not verified') + '</span>';
    html += '<span class="chain-relevance">Relevance: ' + (ev.relevance_score ? (ev.relevance_score * 100).toFixed(0) + '%' : '--') + '</span>';
    html += '</div>';
    html += '<div class="chain-ev-quote">"' + esc(truncStr(ev.direct_quote || ev.statement || "", 250)) + '"</div>';
    if (ev.citing_sections && ev.citing_sections.length) {
      html += '<div class="chain-ev-sections">Used in: ' + ev.citing_sections.map(function(s) { return '<span class="chain-section-chip">' + esc(s.title) + '</span>'; }).join(' ') + '</div>';
    }
    html += '</div>';
  });

  pane.innerHTML = html;
}

/* --- Tab 2: Source Preview (iframe + mark.js) --- */
var _previewLoaded = false;

function _renderPreviewTab(data) {
  if (_previewLoaded) return;
  var pane = document.getElementById("chain-pane-preview");
  if (!pane) return;

  var chain = data.chain || [];
  if (chain.length === 0) {
    pane.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-tertiary)">No evidence available for preview.</div>';
    _previewLoaded = true;
    return;
  }

  // Use the first evidence piece for preview
  var firstEv = chain[0];
  var eid = firstEv.evidence_id;
  var quoteText = firstEv.direct_quote || firstEv.statement || "";

  pane.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-tertiary)"><div class="spinner" style="margin:0 auto 8px"></div>Loading source preview...</div>';

  // Fetch source preview from API
  fetch("/api/research/source-preview/" + encodeURIComponent(state.vectorId) + "/" + encodeURIComponent(eid))
    .then(function(res) {
      if (!res.ok) throw new Error("Preview unavailable");
      return res.json();
    })
    .then(function(preview) {
      _previewLoaded = true;
      if (preview.has_preview && preview.readability_html) {
        _renderIframePreview(pane, preview.readability_html, preview.quote_text || quoteText, preview.source_url, preview.source_title);
      } else {
        _renderFallbackPreview(pane, quoteText, firstEv.source_url, firstEv.source_title);
      }
    })
    .catch(function() {
      _previewLoaded = true;
      _renderFallbackPreview(pane, quoteText, firstEv.source_url, firstEv.source_title);
    });
}

// Cache for inlined mark.js source (fetched once from parent origin)
var _markJsSource = null;

function _renderIframePreview(pane, readabilityHtml, quoteText, sourceUrl, sourceTitle) {
  var html = '';
  html += '<div class="chain-preview-header">';
  html += '<span class="chain-preview-title">' + esc(sourceTitle || "Source Document") + '</span>';
  if (sourceUrl) {
    html += '<a href="' + esc(sourceUrl) + '" target="_blank" rel="noopener" class="chain-preview-link">View Original &rarr;</a>';
  }
  html += '</div>';
  html += '<iframe id="chain-preview-iframe" sandbox="allow-same-origin allow-scripts" class="chain-preview-iframe" srcdoc=""></iframe>';
  html += '<div class="chain-preview-quote-label">Highlighted: cited passage</div>';
  pane.innerHTML = html;

  var iframe = document.getElementById("chain-preview-iframe");
  if (!iframe) return;

  // Fetch mark.js from parent origin (srcdoc iframes can't resolve <script src=...>)
  // then inline it directly into the srcdoc
  var buildSrcdoc = function(markScript) {
    return '<!DOCTYPE html><html><head><meta charset="utf-8">' +
      '<style>' +
      'body { font-family: Georgia, Cambria, serif; line-height: 1.7; padding: 20px; color: #1a1a1a; max-width: 700px; margin: 0 auto; font-size: 15px; }' +
      'h1, h2, h3 { font-family: Inter, sans-serif; }' +
      'a { color: #2563eb; }' +
      'img { max-width: 100%; height: auto; }' +
      '.polaris-highlight { background: #FFEB3B; padding: 2px 4px; border-radius: 2px; box-shadow: 0 0 0 2px rgba(255, 235, 59, 0.3); }' +
      '</style></head><body>' +
      readabilityHtml +
      '<script>' + markScript + '<\/script>' +
      '<script>' +
      'try {' +
      '  var instance = new Mark(document.body);' +
      '  instance.mark(' + JSON.stringify(quoteText) + ', {' +
      '    accuracy: "partially",' +
      '    separateWordSearch: false,' +
      '    className: "polaris-highlight",' +
      '    each: function(el) {' +
      '      setTimeout(function() { el.scrollIntoView({ block: "center", behavior: "smooth" }); }, 300);' +
      '    }' +
      '  });' +
      '} catch(e) { console.warn("mark.js error:", e); }' +
      '<\/script></body></html>';
  };

  if (_markJsSource) {
    iframe.srcdoc = buildSrcdoc(_markJsSource);
  } else {
    fetch("/static/js/vendor/mark.min.js")
      .then(function(r) { return r.text(); })
      .then(function(src) {
        _markJsSource = src;
        iframe.srcdoc = buildSrcdoc(src);
      })
      .catch(function() {
        // If mark.js can't be loaded, render without highlighting
        iframe.srcdoc = buildSrcdoc('/* mark.js unavailable */');
      });
  }
}

function _renderFallbackPreview(pane, quoteText, sourceUrl, sourceTitle) {
  var html = '';
  html += '<div class="chain-preview-header">';
  html += '<span class="chain-preview-title">' + esc(sourceTitle || "Source Document") + '</span>';
  if (sourceUrl) {
    html += '<a href="' + esc(sourceUrl) + '" target="_blank" rel="noopener" class="chain-preview-link">View Original &rarr;</a>';
  }
  html += '</div>';
  html += '<div class="chain-fallback-notice">Source preview unavailable. Showing extracted citation:</div>';
  html += '<blockquote class="chain-fallback-quote">"' + esc(quoteText) + '"</blockquote>';
  pane.innerHTML = html;
}

/* --- Tab 3: Reasoning Chain (A→B→C→D) --- */
function _renderReasoningTab(data, num) {
  var pane = document.getElementById("chain-pane-reasoning");
  if (!pane) return;
  var chain = data.chain || [];
  var src = data.source || {};
  var html = '';

  html += '<div class="chain-section-header">Chain of Custody: How was citation [' + num + '] used?</div>';

  if (chain.length === 0) {
    html += '<div style="padding:20px;color:var(--text-tertiary)">No evidence chain available.</div>';
    pane.innerHTML = html;
    return;
  }

  chain.forEach(function(ev, i) {
    var verdicts = ev.verification || [];

    html += '<div class="chain-reasoning-block">';

    // Step A: Finding
    html += '<div class="chain-step">';
    html += '<div class="chain-step-label">A. Finding</div>';
    html += '<div class="chain-step-content">' + esc(ev.statement || ev.direct_quote || "N/A") + '</div>';
    html += '</div>';

    // Step B: Source citation
    html += '<div class="chain-arrow">&#8595;</div>';
    html += '<div class="chain-step">';
    html += '<div class="chain-step-label">B. Citation Source</div>';
    html += '<div class="chain-step-content">' + esc(src.formatted || ev.source_title || "N/A") + '</div>';
    html += '</div>';

    // Step C: Direct quote
    if (ev.direct_quote) {
      html += '<div class="chain-arrow">&#8595;</div>';
      html += '<div class="chain-step">';
      html += '<div class="chain-step-label">C. Original Sentence</div>';
      html += '<div class="chain-step-content chain-step-quote">"' + esc(ev.direct_quote) + '"</div>';
      html += '</div>';
    }

    // Step D: Verification reasoning
    if (verdicts.length > 0) {
      html += '<div class="chain-arrow">&#8595;</div>';
      html += '<div class="chain-step">';
      html += '<div class="chain-step-label">D. Verification Reasoning</div>';
      verdicts.forEach(function(v) {
        var verdictColor = v.verdict === "SUPPORTED" ? "var(--success)" : (v.verdict === "NOT_SUPPORTED" ? "var(--error)" : "var(--text-tertiary)");
        html += '<div class="chain-verdict">';
        html += '<span class="chain-verdict-badge" style="color:' + verdictColor + '">' + esc(v.verdict || "NO_VERDICT") + '</span>';
        if (v.nli_score != null) {
          html += ' <span class="chain-nli-score">NLI: ' + (v.nli_score * 100).toFixed(0) + '%</span>';
        }
        if (v.reasoning) {
          html += '<div class="chain-verdict-reason">' + esc(v.reasoning) + '</div>';
        }
        html += '</div>';
      });
      html += '</div>';
    }

    // Conclusion
    html += '<div class="chain-arrow">&#8595;</div>';
    html += '<div class="chain-conclusion">';
    var allSupported = verdicts.length > 0 && verdicts.every(function(v) { return v.verdict === "SUPPORTED" || v.is_faithful; });
    if (allSupported) {
      html += '<span style="color:var(--success)">&#10003; Fully verified</span> — Finding [A] is supported by citation [B] with direct evidence [C] confirmed by reasoning [D].';
    } else if (verdicts.length > 0) {
      html += '<span style="color:var(--warning)">&#9888; Partially verified</span> — Some claims from this source could not be fully confirmed.';
    } else {
      html += '<span style="color:var(--text-tertiary)">&#9679; Not yet verified</span> — No verification data available for this evidence.';
    }
    html += '</div>';

    html += '</div>'; // /chain-reasoning-block

    if (i < chain.length - 1) {
      html += '<hr class="chain-separator">';
    }
  });

  pane.innerHTML = html;
}

/* --- Tab 4: Metadata --- */
function _renderMetadataTab(data, num) {
  var pane = document.getElementById("chain-pane-metadata");
  if (!pane) return;
  var chain = data.chain || [];
  var src = data.source || {};
  var html = '';

  // Source metadata table
  html += '<div class="chain-section-header">Source Information</div>';
  html += '<table class="chain-meta-table">';
  html += '<tr><td>Citation Key</td><td>' + esc(src.citation_key || "--") + '</td></tr>';
  html += '<tr><td>URL</td><td>' + (src.url ? '<a href="' + esc(src.url) + '" target="_blank" rel="noopener">' + esc(truncStr(src.url, 60)) + '</a>' : '--') + '</td></tr>';
  html += '<tr><td>Source Type</td><td>' + esc(src.source_type || "--") + '</td></tr>';
  html += '<tr><td>Evidence Pieces</td><td>' + chain.length + '</td></tr>';
  html += '</table>';

  // Per-evidence details
  if (chain.length > 0) {
    html += '<div class="chain-section-header" style="margin-top:16px">Evidence Details</div>';
    chain.forEach(function(ev, i) {
      html += '<div class="chain-meta-ev">';
      html += '<div class="chain-meta-ev-header">Evidence #' + (i + 1) + ' <span class="chain-tier-badge tier-' + (ev.quality_tier || "bronze").toLowerCase() + '">' + esc(ev.quality_tier || "BRONZE") + '</span></div>';
      html += '<table class="chain-meta-table">';
      html += '<tr><td>Evidence ID</td><td><code>' + esc(ev.evidence_id || "--") + '</code></td></tr>';
      html += '<tr><td>Relevance</td><td>' + (ev.relevance_score ? (ev.relevance_score * 100).toFixed(1) + '%' : '--') + '</td></tr>';
      html += '<tr><td>Source Confidence</td><td>' + (ev.source_confidence ? (ev.source_confidence * 100).toFixed(1) + '%' : '--') + '</td></tr>';
      html += '<tr><td>Year</td><td>' + (ev.year || "--") + '</td></tr>';
      html += '<tr><td>Authors</td><td>' + (ev.authors && ev.authors.length ? esc(ev.authors.join(", ")) : "--") + '</td></tr>';
      html += '<tr><td>Perspective</td><td>' + esc(ev.perspective || "--") + '</td></tr>';
      html += '<tr><td>Corroborating Sources</td><td>' + (ev.corroborating_sources || 0) + '</td></tr>';
      if (ev.verification && ev.verification.length) {
        ev.verification.forEach(function(v) {
          html += '<tr><td>Verdict</td><td>' + esc(v.verdict || "--") + '</td></tr>';
          html += '<tr><td>Method</td><td>' + esc(v.verification_method || "--") + ' (' + esc(v.verification_type || "--") + ')</td></tr>';
          if (v.nli_score != null) html += '<tr><td>NLI Score</td><td>' + (v.nli_score * 100).toFixed(1) + '%</td></tr>';
          if (v.cross_source_score != null) html += '<tr><td>Cross-Source Score</td><td>' + (v.cross_source_score * 100).toFixed(1) + '%</td></tr>';
        });
      }
      html += '</table>';
      html += '</div>';
    });
  }

  pane.innerHTML = html;
}

/* =====================================================================
   Override showCitePopover to use chain modal instead
   ===================================================================== */
var _originalShowCitePopover = typeof showCitePopover === "function" ? showCitePopover : null;

// Replace the global showCitePopover with chain version
showCitePopover = function(event, num) {
  showCitationChain(event, num);
};
