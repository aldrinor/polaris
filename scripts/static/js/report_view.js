/* =====================================================================
   report_view.js — Report rendering (renderReportView), TOC building,
   citation handling (showCitePopover), export functions (PDF, Markdown, JSONL),
   STORM sidebar, bookmark handling
   ===================================================================== */

/* =====================================================================
   CHUNK 5 — Report View
   ===================================================================== */
function renderReportView() {
  var isUser = _currentViewMode === "user";

  // --- User mode: Quality summary bar (compact) ---
  var gateHtml = '<div class="report-header">';

  if (isUser) {
    // User sees a clean quality bar, not raw gate data
    var verTotal = state.verificationVerdicts.length;
    var verFaithful = state.verificationVerdicts.filter(function(v) { return v.verdict === "SUPPORTED" || v.is_faithful; }).length;
    var faithPct = verTotal > 0 ? ((verFaithful / verTotal) * 100) : 0;
    var evidenceCount = state.evidence || 0;
    var sourceCount = state.sources.size || 0;
    var wordCount = state.words || 0;
    var iterCount = state.gateHistory.length || state.iteration || 0;

    gateHtml += '<div class="user-quality-bar">';
    gateHtml += '<div class="user-q-item"><span class="user-q-value">' + (verTotal > 0 ? faithPct.toFixed(0) + '%' : '--') + '</span><span class="user-q-label">Claims Verified</span></div>';
    gateHtml += '<div class="user-q-item"><span class="user-q-value">' + evidenceCount + '</span><span class="user-q-label">Evidence Pieces</span></div>';
    gateHtml += '<div class="user-q-item"><span class="user-q-value">' + sourceCount + '</span><span class="user-q-label">Sources Cited</span></div>';
    gateHtml += '<div class="user-q-item"><span class="user-q-value">' + wordCount.toLocaleString() + '</span><span class="user-q-label">Words</span></div>';
    if (iterCount > 0) {
      gateHtml += '<div class="user-q-item"><span class="user-q-value">' + iterCount + '</span><span class="user-q-label">Verification Passes</span></div>';
    }
    gateHtml += '</div>';

    // STORM perspectives summary (user mode)
    if (state.stormPersonas.length) {
      gateHtml += '<details class="storm-perspectives-summary"><summary>' + state.stormPersonas.length + ' expert perspectives analyzed</summary><div class="storm-persp-grid">';
      state.stormPersonas.forEach(function(p) {
        var name = p.name || p.persona || "Expert";
        var expertise = p.expertise || p.field || "";
        var focus = p.focus || p.perspective || "";
        gateHtml += '<div class="storm-persp-card">' +
          '<div class="storm-persp-name">' + esc(name) + '</div>' +
          (expertise ? '<div class="storm-persp-exp">' + esc(expertise) + '</div>' : '') +
          (focus ? '<div class="storm-persp-focus">' + esc(focus) + '</div>' : '') +
          '</div>';
      });
      gateHtml += '</div></details>';
    }
    // STORM perspectives collapsible sidebar (user mode)
    if (state.stormPersonas.length) {
      gateHtml += '<div class="storm-sidebar user-only" id="storm-sidebar">';
      gateHtml += '<button class="storm-toggle" onclick="toggleStormSidebar()" aria-label="Toggle expert perspectives panel">';
      gateHtml += '<span class="storm-toggle-icon">&#9660;</span> ' + state.stormPersonas.length + ' Expert Perspectives Analyzed';
      gateHtml += '</button>';
      gateHtml += '<div class="storm-perspectives-list" id="storm-perspectives-list">';
      state.stormPersonas.forEach(function(p) {
        var name = p.name || p.persona || "Expert";
        var expertise = p.expertise || p.field || "";
        var focus = p.focus || p.perspective || "";
        var finding = "";
        var chats = state.stormChats.filter(function(c) { return c.persona === name; });
        if (chats.length && chats[0].findings && chats[0].findings.length) {
          var f = chats[0].findings[0];
          finding = typeof f === "string" ? f : (f.finding || "");
        }
        gateHtml += '<div class="storm-persp-item">';
        gateHtml += '<div class="storm-persp-item-name">' + esc(name) + '</div>';
        if (expertise) gateHtml += '<div style="font-size:11px;color:var(--accent);margin-top:1px">' + esc(expertise) + '</div>';
        if (focus) gateHtml += '<div style="font-size:10px;color:var(--text-tertiary);margin-top:1px">' + esc(focus) + '</div>';
        if (finding) gateHtml += '<div class="storm-persp-item-finding">' + esc(truncStr(finding, 200)) + '</div>';
        gateHtml += '</div>';
      });
      gateHtml += '</div></div>';
    }
  } else {
    // Operator mode: full gate details
    gateHtml += '<div class="report-gate-grid">';
    var gateKeys = Object.keys(state.gates);
    if (gateKeys.length) {
      gateHtml += '<h3>Quality Gates</h3><div class="gate-dots">';
      gateKeys.forEach(function(k) {
        var g = state.gates[k];
        var passed = g.passed !== false;
        var displayName = k.replace(/_/g, " ").replace(/post /i, "").replace(/\b\w/g, function(c) { return c.toUpperCase(); });
        var icon = passed ? "\u2713" : "\u2717";
        var statusLabel = passed ? "PASS" : "FAIL";
        gateHtml += '<span class="gate-dot ' + (passed ? "pass" : "fail") + '" title="' + esc(k) + ': ' + statusLabel + '">' + icon + ' ' + esc(displayName) + ' \u2014 ' + statusLabel + '</span>';
      });
      gateHtml += '</div>';
    }
    gateHtml += '</div>';

    // Iteration timeline (operator)
    if (state.gateHistory.length) {
      gateHtml += '<div class="iteration-timeline"><h3>Iteration Timeline</h3><div class="timeline-track">';
      state.gateHistory.forEach(function(gh, i) {
        var passed = gh.passed !== false;
        gateHtml += '<div class="timeline-node ' + (passed ? "pass" : "fail") + '">' +
          '<div class="timeline-num">' + (i + 1) + '</div>' +
          '<div class="timeline-label">' + (gh.faith !== undefined ? (gh.faith * 100).toFixed(0) + '%' : '--') + '</div>' +
          '</div>';
        if (i < state.gateHistory.length - 1) gateHtml += '<div class="timeline-connector"></div>';
      });
      gateHtml += '</div></div>';
    }

    // Verification summary (operator)
    var verTotal = state.verificationVerdicts.length;
    var verFaithful = state.verificationVerdicts.filter(function(v) { return v.verdict === "SUPPORTED" || v.is_faithful; }).length;
    if (verTotal > 0) {
      gateHtml += '<div class="verification-summary">' +
        '<h3>Verification</h3>' +
        '<div class="ver-bar-wrap">' +
        '<div class="ver-bar-fill" style="width:' + ((verFaithful / verTotal) * 100).toFixed(1) + '%;background:var(--success)"></div>' +
        '</div>' +
        '<span class="ver-label">' + verFaithful + '/' + verTotal + ' claims supported (' + ((verFaithful / verTotal) * 100).toFixed(1) + '%)</span>' +
        '</div>';
    }
  }
  gateHtml += '</div>';

  // Quality verification banner
  var qualityBannerHtml = '';
  if (state.fullReport) {
    var _verTotal = state.verificationVerdicts.length;
    var _verFaith = state.verificationVerdicts.filter(function(v) { return v.verdict === "SUPPORTED" || v.is_faithful; }).length;
    var _srcCount = state.sources.size || state.bibliography.length || 0;
    var _faithPct = _verTotal > 0 ? ((_verFaith / _verTotal) * 100).toFixed(0) : '0';
    var _bannerClass = _verTotal > 0 && (_verFaith / _verTotal) >= 0.70 ? '' : ' partial';
    var _bannerIcon = _bannerClass === '' ? '&#10003;' : '&#9888;';
    qualityBannerHtml = '<div class="report-quality-banner' + _bannerClass + '">' +
      '<div class="quality-badge-icon">' + _bannerIcon + '</div>' +
      '<div class="quality-badge-text">' +
      '<div class="quality-badge-title">' + _verFaith + ' claims verified from ' + _srcCount + ' sources</div>' +
      '<div class="quality-badge-sub">' + _faithPct + '% verification rate across ' + (state.words || 0).toLocaleString() + ' words</div>' +
      '</div></div>';
    if (isUser && state.bibliography.length) {
      qualityBannerHtml += '<div class="citation-hint">Click any <span class="cite-ref-demo">[1]</span> in the text to preview its source.</div>';
    }
  }

  // Report content
  var reportHtml = '';
  var tocHtml = '';
  if (state.fullReport) {
    reportHtml += '<div class="report-rendered">';
    try {
      var rendered = safeMarkdown(state.fullReport);
      // Inject clickable citations: [1] [2] etc
      rendered = rendered.replace(/\[(\d+)\]/g, function(m, num) {
        return '<span class="cite-ref" data-cite="' + num + '" onclick="showCitePopover(event, ' + num + ')">[' + num + ']</span>';
      });
      // Add IDs to headings for TOC navigation
      var tocItems = [];
      var headingIdx = 0;
      rendered = rendered.replace(/<h([23])([^>]*)>(.*?)<\/h\1>/gi, function(match, level, attrs, content) {
        headingIdx++;
        var id = 'section-' + headingIdx;
        var textOnly = content.replace(/<[^>]*>/g, '');
        tocItems.push({ id: id, text: textOnly, level: parseInt(level) });
        return '<h' + level + attrs + ' id="' + id + '">' + content + '</h' + level + '>';
      });
      // Inject section-level faithfulness badges after h2/h3 headings
      if (state.hallucinationAudit.length) {
        state.hallucinationAudit.forEach(function(ha) {
          var sectionTitle = ha.section || ha.section_id || "";
          if (!sectionTitle) return;
          var faithScore = ha.faithfulness_score !== undefined ? ha.faithfulness_score : (ha.hallucination_ratio !== undefined ? (1 - ha.hallucination_ratio) : undefined);
          if (faithScore === undefined) return;
          var pct = (faithScore * 100).toFixed(0);
          var icon = faithScore >= 0.80 ? "&#10003;" : "&#9888;";
          var badgeColor = faithScore >= 0.80 ? "var(--success)" : "var(--warning)";
          var badge = '<span class="section-faith-badge" style="color:' + badgeColor + ';">' + icon + ' ' + pct + '%</span>';
          var escapedTitle = sectionTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          var headingRegex = new RegExp("(<h[23][^>]*>)(.*?" + escapedTitle + ".*?)(</h[23]>)", "i");
          rendered = rendered.replace(headingRegex, function(match, open, inner, close) {
            return open + inner + badge + close;
          });
        });
      }
      // A5A: Inject conflict badges on section headings where sources disagree
      if (state.evidenceConflicts.length) {
        // Build section_id -> title map from multiple sources for heading matching
        var secIdToTitle = {};
        if (state.reportOutline && Array.isArray(state.reportOutline.sections)) {
          state.reportOutline.sections.forEach(function(sec) {
            var sid = sec.section_id || sec.id || "";
            if (sid && sec.title) secIdToTitle[sid] = sec.title;
          });
        }
        // Fallback: also build from sectionWrites (has sectionId + title)
        if (Array.isArray(state.sectionWrites)) {
          state.sectionWrites.forEach(function(sw) {
            if (sw.sectionId && sw.title && !secIdToTitle[sw.sectionId]) {
              secIdToTitle[sw.sectionId] = sw.title;
            }
          });
        }
        // Build a map of section title -> conflict indices
        var conflictsBySection = {};
        state.evidenceConflicts.forEach(function(c, idx) {
          var sections = [];
          if (c.section_a) sections.push(c.section_a);
          if (c.section_b) sections.push(c.section_b);
          sections.forEach(function(secId) {
            // Resolve section_id to title for heading matching
            var label = secIdToTitle[secId] || secId;
            if (!conflictsBySection[label]) conflictsBySection[label] = [];
            conflictsBySection[label].push(idx);
          });
        });
        // Inject conflict badge after headings that match section titles
        Object.keys(conflictsBySection).forEach(function(secTitle) {
          var count = conflictsBySection[secTitle].length;
          var conflictBadge = '<span class="section-conflict-badge" ' +
            'onclick="event.stopPropagation();showConflictModal(' + conflictsBySection[secTitle][0] + ')" ' +
            'title="' + count + ' source' + (count > 1 ? 's' : '') + ' disagree on this topic">' +
            'Conflict (' + count + ')</span>';
          // Match heading containing section title text
          var escapedSec = secTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          var secHeadingRegex = new RegExp("(<h[23][^>]*>)(.*?" + escapedSec + ".*?)(</h[23]>)", "i");
          rendered = rendered.replace(secHeadingRegex, function(match, open, inner, close) {
            // Avoid duplicating if badge already present
            if (inner.indexOf("section-conflict-badge") !== -1) return match;
            return open + inner + conflictBadge + close;
          });
        });
        // Fallback: if no section-level badges were injected (conflicts lack section_a/section_b),
        // add a global conflict badge after the first h1/h2 heading
        if (rendered.indexOf("section-conflict-badge") === -1) {
          var totalConflicts = state.evidenceConflicts.length;
          var globalBadge = '<span class="section-conflict-badge" ' +
            'onclick="event.stopPropagation();showConflictModal(0)" ' +
            'title="' + totalConflicts + ' evidence conflict' + (totalConflicts > 1 ? 's' : '') + ' detected">' +
            'Conflicts (' + totalConflicts + ')</span>';
          rendered = rendered.replace(/(<h[12][^>]*>)(.*?)(<\/h[12]>)/, function(match, open, inner, close) {
            return open + inner + globalBadge + close;
          });
        }
      }

      // GEMINI-ARCH 3C: Wrap "Key Findings" blocks in styled container
      rendered = rendered.replace(
        /<p><strong>Key Findings:?<\/strong><\/p>\s*<ul>([\s\S]*?)<\/ul>/gi,
        function(match, listContent) {
          return '<div class="key-findings"><div class="key-findings-title">Key Findings</div><ul>' + listContent + '</ul></div>';
        }
      );
      // Also handle h3/h4 Key Findings headers
      rendered = rendered.replace(
        /<h([34])[^>]*>Key Findings:?<\/h\1>\s*<ul>([\s\S]*?)<\/ul>/gi,
        function(match, level, listContent) {
          return '<div class="key-findings"><div class="key-findings-title">Key Findings</div><ul>' + listContent + '</ul></div>';
        }
      );

      // GEMINI-ARCH 3D: Parse :::metrics blocks into infographic cards
      rendered = rendered.replace(
        /<p>:::metrics\s*\n?([\s\S]*?):::<\/p>/gi,
        function(match, metricsContent) {
          var items = metricsContent.split('|').map(function(s) { return s.trim(); }).filter(Boolean);
          var cardHtml = '<div class="report-metrics-card">';
          items.forEach(function(item) {
            var parts = item.split(':').map(function(s) { return s.trim(); });
            if (parts.length >= 2) {
              cardHtml += '<div class="metric-item"><div class="metric-value">' + esc(parts[1]) + '</div><div class="metric-label">' + esc(parts[0]) + '</div></div>';
            }
          });
          cardHtml += '</div>';
          return cardHtml;
        }
      );

      reportHtml += rendered;

      // Build TOC HTML
      if (tocItems.length > 1) {
        tocHtml = '<nav class="report-toc" aria-label="Table of contents"><div class="report-toc-title">Contents</div><ul class="toc-list">';
        tocItems.forEach(function(item) {
          var cls = item.level === 3 ? ' toc-h3' : '';
          tocHtml += '<li class="toc-item"><a class="toc-link' + cls + '" onclick="scrollToSection(\'' + item.id + '\')" data-target="' + item.id + '">' + esc(item.text) + '</a></li>';
        });
        tocHtml += '</ul></nav>';
      }
    } catch(e) {
      reportHtml += '<pre>' + esc(state.fullReport) + '</pre>';
    }
    reportHtml += '</div>';
  } else {
    reportHtml += '<div class="report-empty">' +
      '<div class="empty-icon">&#x1f4dd;</div>' +
      '<div class="empty-text">Report will appear here when the pipeline completes synthesis.</div>' +
      '</div>';
  }

  // Bibliography as source cards
  var bibHtml = '';
  if (state.bibliography.length) {
    bibHtml += '<div class="report-bib" id="report-bibliography"><h3>Sources (' + state.bibliography.length + ')</h3><div class="source-cards">';
    state.bibliography.forEach(function(b, i) {
      var url = b.url || b.source_url || "";
      var title = b.title || b.domain || url || ("Source " + (i + 1));
      var domain = url ? extractDomain(url) : "";
      var faviconUrl = domain ? 'https://www.google.com/s2/favicons?domain=' + encodeURIComponent(domain) + '&sz=32' : '';
      var firstLetter = (domain || title || "S").charAt(0).toUpperCase();

      bibHtml += '<div class="source-card" id="bib-' + (i + 1) + '">';
      bibHtml += '<span class="source-num">[' + (i + 1) + ']</span>';
      bibHtml += '<div class="source-favicon">';
      if (faviconUrl) {
        bibHtml += '<img src="' + esc(faviconUrl) + '" alt="" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\'">';
        bibHtml += '<span class="favicon-fallback" style="display:none">' + esc(firstLetter) + '</span>';
      } else {
        bibHtml += '<span class="favicon-fallback">' + esc(firstLetter) + '</span>';
      }
      bibHtml += '</div>';
      bibHtml += '<div class="source-info">';
      if (url) {
        bibHtml += '<div class="source-title"><a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(title) + '</a></div>';
      } else {
        bibHtml += '<div class="source-title">' + esc(title) + '</div>';
      }
      bibHtml += '<div class="source-domain">';
      if (domain) bibHtml += '<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(domain) + '</a>';
      if (b.authors) {
        var authStr = typeof b.authors === 'string' ? b.authors : b.authors.join(', ');
        bibHtml += '<span>' + esc(truncStr(authStr, 40)) + '</span>';
      }
      bibHtml += '</div>';
      if (b.year || b.venue) {
        bibHtml += '<div class="source-meta">';
        if (b.year) bibHtml += '<span class="source-year">' + b.year + '</span>';
        if (b.venue) bibHtml += '<span class="source-venue">' + esc(b.venue) + '</span>';
        bibHtml += '</div>';
      }
      bibHtml += '</div></div>';
    });
    bibHtml += '</div></div>';
  }

  // Collapsible extras
  var extrasHtml = '<div class="report-extras">';

  // Cluster themes
  if (state.clusterThemes.length) {
    extrasHtml += '<details class="report-detail-block"><summary>Cluster Themes (' + state.clusterThemes.length + ')</summary><div class="detail-body">';
    state.clusterThemes.forEach(function(ct) {
      var label = ct.theme || ct.label || ct.name || "Theme";
      var count = ct.evidence_count || ct.count || 0;
      extrasHtml += '<div class="cluster-chip"><strong>' + esc(label) + '</strong>' + (count ? ' <span class="chip-count">' + count + ' evidence</span>' : '') + '</div>';
    });
    extrasHtml += '</div></details>';
  }

  // Section writes
  if (state.sectionWrites.length) {
    extrasHtml += '<details class="report-detail-block"><summary>Section Writes (' + state.sectionWrites.length + ')</summary><div class="detail-body">';
    state.sectionWrites.forEach(function(sw) {
      var typeTag = sw.type === "expand" ? "expanded" : sw.type === "revise" ? "revised" : "written";
      extrasHtml += '<div class="section-write-card">' +
        '<span class="sw-title">' + esc(sw.title || sw.sectionId) + '</span>' +
        '<span class="sw-type tag-' + typeTag + '">' + typeTag + '</span>' +
        '<span class="sw-words">' + (sw.wordCount || 0) + 'w</span>';
      if (sw.expandedWords) extrasHtml += '<span class="sw-expand">' + (sw.originalWords || 0) + ' \u2192 ' + sw.expandedWords + 'w</span>';
      extrasHtml += '</div>';
    });
    extrasHtml += '</div></details>';
  }

  // Hallucination audit
  if (state.hallucinationAudit.length) {
    extrasHtml += '<details class="report-detail-block"><summary>Hallucination Audit (' + state.hallucinationAudit.length + ' sections)</summary><div class="detail-body">';
    state.hallucinationAudit.forEach(function(ha) {
      var ratio = ha.hallucination_ratio !== undefined ? (ha.hallucination_ratio * 100).toFixed(1) + '%' : 'N/A';
      var flagged = ha.flagged_spans || 0;
      var cls = ha.hallucination_ratio > 0.3 ? "high" : ha.hallucination_ratio > 0.1 ? "med" : "low";
      extrasHtml += '<div class="halluc-row ' + cls + '">' +
        '<span class="halluc-section">' + esc(ha.section || ha.section_id || "?") + '</span>' +
        '<span class="halluc-ratio">' + ratio + '</span>' +
        '<span class="halluc-spans">' + flagged + ' flagged</span>' +
        (ha.rewritten ? '<span class="halluc-rewritten">rewritten</span>' : '') +
        '</div>';
    });
    extrasHtml += '</div></details>';
  }

  // Expansion history
  if (state.expansionPasses.length) {
    extrasHtml += '<details class="report-detail-block"><summary>Expansion Passes (' + state.expansionPasses.length + ')</summary><div class="detail-body">';
    state.expansionPasses.forEach(function(ep) {
      extrasHtml += '<div class="expansion-row">' +
        '<span>' + esc(ep.section || ep.section_id || "?") + '</span>' +
        '<span>' + (ep.original_words || 0) + ' \u2192 ' + (ep.expanded_words || 0) + 'w</span>' +
        '</div>';
    });
    extrasHtml += '</div></details>';
  }

  // Evidence conflicts (enhanced A5A)
  if (state.evidenceConflicts.length) {
    extrasHtml += '<details class="report-detail-block"><summary>Evidence Conflicts (' + state.evidenceConflicts.length + ')</summary><div class="detail-body">';
    state.evidenceConflicts.forEach(function(c, idx) {
      var stmtA = c.statement_a || c.claim_a || c.evidence_a || "";
      var stmtB = c.statement_b || c.claim_b || c.evidence_b || "";
      var cType = c.type || "conflict";
      var score = c.score || c.contradiction_score || c.similarity || 0;
      var signals = Array.isArray(c.contradiction_signals) ? c.contradiction_signals.join(", ") : "";
      var srcUrl = c.source_url || "";
      var secA = c.section_a || "";
      var secB = c.section_b || "";

      extrasHtml += '<div class="conflict-card-enhanced" data-conflict-idx="' + idx + '" role="button" tabindex="0" onclick="showConflictModal(' + idx + ')" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){showConflictModal(' + idx + ');event.preventDefault();}">' +
        '<div class="conflict-card-header">' +
          '<span class="conflict-badge-pill">' + esc(cType.replace(/_/g, " ")) + '</span>' +
          (score > 0 ? '<span class="conflict-score-pill">Score: ' + (score * 100).toFixed(0) + '%</span>' : '') +
        '</div>' +
        '<div class="conflict-vs-row">' +
          '<div class="conflict-side conflict-side-a"><div class="conflict-side-label">A</div><div class="conflict-side-text">' + esc(truncStr(stmtA, 120)) + '</div></div>' +
          '<div class="conflict-vs-divider">vs</div>' +
          '<div class="conflict-side conflict-side-b"><div class="conflict-side-label">B</div><div class="conflict-side-text">' + esc(truncStr(stmtB, 120)) + '</div></div>' +
        '</div>' +
        (signals ? '<div class="conflict-signals">Signals: ' + esc(signals) + '</div>' : '') +
        (srcUrl ? '<div class="conflict-source">Source: ' + esc(truncStr(srcUrl, 60)) + '</div>' : '') +
        (secA && secB ? '<div class="conflict-sections">Sections: ' + esc(secA) + ' / ' + esc(secB) + '</div>' : '') +
        '<div class="conflict-click-hint">Click to compare</div>' +
        '</div>';
    });
    extrasHtml += '</div></details>';
  }

  // Gap analysis
  if (state.gapAnalysis) {
    extrasHtml += '<details class="report-detail-block"><summary>Gap Analysis</summary><div class="detail-body">' +
      '<pre class="gap-pre">' + esc(typeof state.gapAnalysis === 'string' ? state.gapAnalysis : JSON.stringify(state.gapAnalysis, null, 2)) + '</pre>' +
      '</div></details>';
  }

  extrasHtml += '</div>';

  // Export toolbar
  var exportHtml = '<div class="export-toolbar">';
  // Bookmark button (visible in both user and operator modes)
  if (state.fullReport && state.vectorId) {
    var _bkmkActive = isBookmarked(state.vectorId);
    exportHtml += '<button class="bookmark-btn' + (_bkmkActive ? ' bookmarked' : '') + '" id="report-bookmark-btn" ' +
      'onclick="toggleBookmark()" ' +
      'title="' + (_bkmkActive ? 'Remove bookmark' : 'Save to bookmarks') + '" ' +
      'aria-label="' + (_bkmkActive ? 'Remove bookmark' : 'Save to bookmarks') + '">' +
      (_bkmkActive ? '&#9733;' : '&#9734;') + '</button>';
  }
  if (state.fullReport) {
    exportHtml += '<button class="export-btn" onclick="exportReport(\'pdf\')">Export PDF</button>';
    exportHtml += '<button class="export-btn" onclick="exportReport(\'markdown\')">Export Markdown</button>';
    exportHtml += '<button class="export-btn" onclick="exportReport(\'docx\')">Export Word</button>';
    if (!isUser) {
      exportHtml += '<button class="export-btn" onclick="exportReport(\'jsonl\')">Export JSONL</button>';
    }
    // Operator-only: Audit trace export
    if (!isUser) {
      exportHtml += '<button class="export-btn-audit operator-only" onclick="exportAuditTrace()">Export Audit Trace</button>';
    }
  }
  exportHtml += '</div>';

  var reportPane = document.getElementById("view-report");
  var layoutHtml = '';
  if (tocHtml && state.fullReport) {
    layoutHtml = qualityBannerHtml + gateHtml +
      '<div class="report-layout">' + tocHtml +
      '<div class="report-main">' + reportHtml + bibHtml + '</div>' +
      '</div>' + extrasHtml + exportHtml;
  } else {
    layoutHtml = qualityBannerHtml + gateHtml + reportHtml + bibHtml + extrasHtml + exportHtml;
  }
  reportPane.innerHTML = '<div class="report-view"><div class="report-content">' +
    layoutHtml +
    '</div></div>';

  // A5: Render Mermaid.js diagrams in the report
  _renderMermaidDiagrams(reportPane);
}

/**
 * A5: Convert mermaid code blocks to rendered diagrams.
 *
 * Finds <pre><code class="language-mermaid"> blocks (produced by marked.js
 * from ```mermaid fences) and replaces them with <div class="mermaid"> blocks
 * that mermaid.js renders into SVG. Also injects any smart art diagrams from
 * state.smartArtDiagrams that weren't already in the markdown.
 */
function _renderMermaidDiagrams(container) {
  if (typeof mermaid === "undefined") return;

  // Convert <pre><code class="language-mermaid">...</code></pre> -> <div class="mermaid">
  var codeBlocks = container.querySelectorAll('code.language-mermaid');
  codeBlocks.forEach(function(code) {
    var pre = code.parentElement;
    if (pre && pre.tagName === "PRE") {
      var div = document.createElement("div");
      div.className = "mermaid";
      div.textContent = code.textContent;
      pre.replaceWith(div);
    }
  });

  // Inject smart art diagrams from state that may not be in the markdown
  if (state.smartArtDiagrams && Object.keys(state.smartArtDiagrams).length > 0) {
    var existingMermaids = container.querySelectorAll(".mermaid");
    var existingCount = existingMermaids.length;

    // Only inject if report has no mermaid blocks already
    if (existingCount === 0) {
      var sections = container.querySelectorAll("h2, h3");
      Object.keys(state.smartArtDiagrams).forEach(function(sectionId) {
        var code = state.smartArtDiagrams[sectionId];
        if (!code) return;
        var inserted = false;
        // Find the section heading by matching title or index
        var sectionTitle = sectionId.toLowerCase().replace(/_/g, " ").replace(/-/g, " ");
        sections.forEach(function(heading) {
          if (inserted) return;
          var headingText = heading.textContent.toLowerCase().trim().replace(/-/g, " ");
          if (headingText.indexOf(sectionTitle) !== -1 || heading.id === sectionId) {
            // Insert mermaid div after the first paragraph following this heading
            var nextEl = heading.nextElementSibling;
            if (nextEl) {
              var mermaidDiv = document.createElement("div");
              mermaidDiv.className = "mermaid";
              mermaidDiv.textContent = code;
              nextEl.after(mermaidDiv);
              inserted = true;
            }
          }
        });
        // If no heading match, append at end of report content
        if (!inserted) {
          var reportMain = container.querySelector(".report-main, .report-content");
          if (reportMain) {
            var mermaidDiv = document.createElement("div");
            mermaidDiv.className = "mermaid";
            mermaidDiv.textContent = code;
            reportMain.appendChild(mermaidDiv);
          }
        }
      });
    }
  }

  // Run mermaid rendering on all .mermaid divs
  var mermaidDivs = container.querySelectorAll(".mermaid");
  if (mermaidDivs.length > 0) {
    // Set theme based on current mode
    var isDark = document.documentElement.getAttribute("data-theme") !== "light";
    try {
      mermaid.initialize({
        startOnLoad: false,
        theme: isDark ? "dark" : "default",
        securityLevel: "strict"
      });
      mermaid.run({ nodes: mermaidDivs });
    } catch (err) {
      console.warn("[report_view] Mermaid rendering failed:", err);
    }
  }
}

/* Citation popover */
function showCitePopover(event, num) {
  event.stopPropagation();
  hideCitePopover();
  var bib = state.bibliography[num - 1];
  if (!bib) return;
  var pop = document.createElement("div");
  pop.className = "cite-popover";
  pop.id = "cite-popover-active";
  var title = bib.title || bib.domain || ("Source " + num);
  var url = bib.url || bib.source_url || "";
  var quote = bib.quote || bib.excerpt || "";
  // Determine verification verdict for this citation
  var bibVerdict = bib.verdict || bib.verification_status || "";
  if (!bibVerdict && bib.evidence_id) {
    var matchedVerdict = state.verificationVerdicts.find(function(v) { return v.evidence_id === bib.evidence_id; });
    if (matchedVerdict) bibVerdict = matchedVerdict.verdict || (matchedVerdict.faithful ? "SUPPORTED" : "NOT_SUPPORTED");
  }
  var popVerdictHtml = "";
  if (bibVerdict) {
    var popVerdictColor = bibVerdict === "SUPPORTED" ? "var(--success, #22c55e)" : "var(--error, #ef4444)";
    var popVerdictLabel = bibVerdict === "SUPPORTED" ? "&#10003; VERIFIED" : "&#10007; UNVERIFIED";
    popVerdictHtml = '<div style="margin-top:4px;font-size:0.8em;font-weight:600;color:' + popVerdictColor + ';">' + popVerdictLabel + '</div>';
  }
  pop.innerHTML = '<div class="cite-pop-title">' + esc(title) + '</div>' +
    (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener" class="cite-pop-url">' + esc(truncStr(url, 60)) + '</a>' : '') +
    (quote ? '<div class="cite-pop-quote">"' + esc(truncStr(quote, 300)) + '"</div>' : '') +
    popVerdictHtml +
    (bib.year ? '<div class="cite-pop-year">Year: ' + bib.year + '</div>' : '') +
    '<div class="cite-pop-close" role="button" tabindex="0" onclick="hideCitePopover()" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){hideCitePopover();event.preventDefault();}">\u00d7</div>';
  // Position near the clicked element
  var rect = event.target.getBoundingClientRect();
  pop.style.position = "fixed";
  pop.style.top = (rect.bottom + 6) + "px";
  pop.style.left = Math.min(rect.left, window.innerWidth - 320) + "px";
  document.body.appendChild(pop);
  // Close on outside click
  setTimeout(function() {
    document.addEventListener("click", hideCitePopover, { once: true });
  }, 10);
}
function hideCitePopover() {
  var old = document.getElementById("cite-popover-active");
  if (old) old.remove();
}

/* Scroll to section (TOC navigation) */
function scrollToSection(sectionId) {
  var el = document.getElementById(sectionId);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  // Highlight active TOC item
  document.querySelectorAll('.toc-link').forEach(function(l) { l.classList.remove('active'); });
  var tocLink = document.querySelector('.toc-link[data-target="' + sectionId + '"]');
  if (tocLink) tocLink.classList.add('active');
}

/* Export */
function exportReport(fmt) {
  var content, filename, mime;
  if (fmt === "pdf") {
    exportPDF();
    return;
  } else if (fmt === "docx") {
    exportDocx();
    return;
  } else if (fmt === "markdown") {
    content = state.fullReport || "No report generated.";
    filename = (state.vectorId || "polaris") + "_report.md";
    mime = "text/markdown";
  } else {
    content = state.traceEvents.map(function(ev) { return JSON.stringify(ev); }).join("\n");
    filename = (state.vectorId || "polaris") + "_trace.jsonl";
    mime = "application/jsonl";
  }
  var blob = new Blob([content], { type: mime });
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast("Exported " + filename);
}

function exportPDF() {
  // Build print-friendly report with evidence chain
  var reportContent = state.fullReport || "No report generated.";
  var rendered = safeMarkdown(reportContent);

  // Quality summary
  var verTotal = state.verificationVerdicts.length;
  var verFaithful = state.verificationVerdicts.filter(function(v) { return v.verdict === "SUPPORTED" || v.is_faithful; }).length;
  var faithPct = verTotal > 0 ? ((verFaithful / verTotal) * 100).toFixed(1) : "N/A";

  // Build bibliography
  var bibHtml = '';
  if (state.bibliography.length) {
    bibHtml = '<h2>Bibliography</h2><ol>';
    state.bibliography.forEach(function(b, i) {
      var url = b.url || b.source_url || "";
      var title = b.title || url || "Source " + (i + 1);
      var authors = b.authors ? (typeof b.authors === 'string' ? b.authors : b.authors.join(', ')) : '';
      bibHtml += '<li>' + title + (authors ? ' \u2014 ' + authors : '') + (b.year ? ' (' + b.year + ')' : '') + (url ? ' <span style="color:#888">' + url + '</span>' : '') + '</li>';
    });
    bibHtml += '</ol>';
  }

  // Audit certificate
  var now = new Date().toISOString();
  var auditHtml = '<h2>Audit Certificate</h2>' +
    '<table style="border-collapse:collapse;width:100%;margin-top:8px">' +
    '<tr><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">Research Query</td><td style="padding:4px 8px;border:1px solid #ccc">' + (state.researchQuery || '--') + '</td></tr>' +
    '<tr><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">Vector ID</td><td style="padding:4px 8px;border:1px solid #ccc">' + (state.vectorId || '--') + '</td></tr>' +
    '<tr><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">Claims Verified</td><td style="padding:4px 8px;border:1px solid #ccc">' + faithPct + '% (' + verFaithful + '/' + verTotal + ')</td></tr>' +
    '<tr><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">Evidence Pieces</td><td style="padding:4px 8px;border:1px solid #ccc">' + state.evidence + '</td></tr>' +
    '<tr><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">Sources</td><td style="padding:4px 8px;border:1px solid #ccc">' + state.sources.size + '</td></tr>' +
    '<tr><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">Words</td><td style="padding:4px 8px;border:1px solid #ccc">' + (state.words || 0).toLocaleString() + '</td></tr>' +
    '<tr><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">Verification Passes</td><td style="padding:4px 8px;border:1px solid #ccc">' + (state.gateHistory.length || state.iteration || 0) + '</td></tr>' +
    '<tr><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">Generated</td><td style="padding:4px 8px;border:1px solid #ccc">' + now + '</td></tr>' +
    '<tr><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">Pipeline</td><td style="padding:4px 8px;border:1px solid #ccc">POLARIS Sovereign Deep Research</td></tr>' +
    '</table>';

  // Open print window
  var printWin = window.open('', '_blank', 'width=800,height=600');
  printWin.document.write('<!DOCTYPE html><html><head><title>POLARIS Research Report</title>' +
    '<style>' +
    'body { font-family: Georgia, Cambria, serif; max-width: 750px; margin: 40px auto; padding: 0 20px; color: #1a1a1a; line-height: 1.7; font-size: 14px; }' +
    'h1 { font-family: Inter, sans-serif; font-size: 28px; margin-bottom: 16px; }' +
    'h2 { font-family: Inter, sans-serif; font-size: 20px; margin-top: 32px; border-bottom: 1px solid #ddd; padding-bottom: 8px; }' +
    'h3 { font-family: Inter, sans-serif; font-size: 17px; }' +
    'p { margin-bottom: 12px; }' +
    'blockquote { border-left: 3px solid #38bdf8; padding-left: 16px; color: #555; font-style: italic; }' +
    'ol, ul { padding-left: 24px; }' +
    'li { margin-bottom: 4px; }' +
    '@media print { body { max-width: 100%; margin: 0; } }' +
    '@page { margin: 2cm; }' +
    '.header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 12px; border-bottom: 2px solid #38bdf8; }' +
    '.polaris-logo { font-family: Inter, sans-serif; font-weight: 700; color: #38bdf8; font-size: 24px; letter-spacing: 6px; }' +
    '.header-meta { font-size: 12px; color: #666; text-align: right; }' +
    '</style></head><body>' +
    '<div class="header-bar"><span class="polaris-logo">POLARIS</span><div class="header-meta">Sovereign Deep Research<br>' + now.split('T')[0] + '</div></div>' +
    rendered + bibHtml + auditHtml +
    '<p style="text-align:center;color:#888;margin-top:40px;font-size:11px">Generated by POLARIS Sovereign Deep Research Platform</p>' +
    '</body></html>');
  printWin.document.close();
  printWin.focus();
  setTimeout(function() { printWin.print(); }, 500);
  showToast("PDF export opened in print dialog", "info");
}

/* A5A: Conflict comparison modal */
function showConflictModal(idx) {
  hideConflictModal();
  var c = state.evidenceConflicts[idx];
  if (!c) return;

  var stmtA = c.statement_a || c.claim_a || c.evidence_a || "(no statement)";
  var stmtB = c.statement_b || c.claim_b || c.evidence_b || "(no statement)";
  var cType = (c.type || "conflict").replace(/_/g, " ");
  var score = c.score || c.contradiction_score || c.similarity || 0;
  var signals = Array.isArray(c.contradiction_signals) ? c.contradiction_signals : [];
  var srcUrl = c.source_url || "";
  var secA = c.section_a || "";
  var secB = c.section_b || "";
  var explanation = c.explanation || c.reason || "";

  // Build resolution text
  var resolutionHtml = "";
  if (explanation) {
    resolutionHtml = '<div class="conflict-modal-resolution">' +
      '<div class="conflict-modal-resolution-title">How POLARIS resolved this</div>' +
      '<div class="conflict-modal-resolution-text">' + esc(explanation) + '</div></div>';
  } else if (signals.length > 0) {
    resolutionHtml = '<div class="conflict-modal-resolution">' +
      '<div class="conflict-modal-resolution-title">Contradiction signals detected</div>' +
      '<div class="conflict-modal-resolution-text">' +
      'The following linguistic indicators suggest these claims may conflict: <strong>' +
      esc(signals.join(", ")) + '</strong>. ' +
      'POLARIS weighs source quality tier, recency, and corroboration count when resolving conflicts.</div></div>';
  }

  var overlay = document.createElement("div");
  overlay.className = "conflict-modal-overlay";
  overlay.id = "conflict-modal-overlay";
  overlay.onclick = function(e) { if (e.target === overlay) hideConflictModal(); };

  var totalConflicts = state.evidenceConflicts.length;
  var navHtml = '';
  if (totalConflicts > 1) {
    var prevIdx = (idx - 1 + totalConflicts) % totalConflicts;
    var nextIdx = (idx + 1) % totalConflicts;
    navHtml = '<div class="conflict-modal-nav">' +
      '<button class="conflict-nav-btn" onclick="showConflictModal(' + prevIdx + ')">&larr; Prev</button>' +
      '<span class="conflict-nav-counter">' + (idx + 1) + ' / ' + totalConflicts + '</span>' +
      '<button class="conflict-nav-btn" onclick="showConflictModal(' + nextIdx + ')">Next &rarr;</button></div>';
  }

  overlay.innerHTML = '<div class="conflict-modal">' +
    '<div class="conflict-modal-header">' +
      '<div class="conflict-modal-title">' +
        '<span class="conflict-badge-pill modal">' + esc(cType) + '</span>' +
        (score > 0 ? ' <span class="conflict-score-pill modal">Contradiction: ' + (score * 100).toFixed(0) + '%</span>' : '') +
        (srcUrl ? '<div class="conflict-modal-source">' + esc(truncStr(srcUrl, 80)) + '</div>' : '') +
        (secA && secB ? '<div class="conflict-modal-sections">' + esc(secA) + ' &harr; ' + esc(secB) + '</div>' : '') +
      '</div>' +
      '<button class="conflict-modal-close" onclick="hideConflictModal()">&times;</button>' +
    '</div>' +
    '<div class="conflict-modal-body">' +
      '<div class="conflict-compare">' +
        '<div class="conflict-compare-col">' +
          '<div class="conflict-compare-label">Source A</div>' +
          '<div class="conflict-compare-text">' + esc(stmtA) + '</div>' +
          (c.evidence_a_id ? '<div class="conflict-compare-id">' + esc(c.evidence_a_id) + '</div>' : '') +
        '</div>' +
        '<div class="conflict-compare-divider">' +
          '<div class="conflict-compare-vs">VS</div>' +
          (score > 0 ? '<div class="conflict-compare-score">' + (score * 100).toFixed(0) + '%<br>contradiction</div>' : '') +
        '</div>' +
        '<div class="conflict-compare-col">' +
          '<div class="conflict-compare-label">Source B</div>' +
          '<div class="conflict-compare-text">' + esc(stmtB) + '</div>' +
          (c.evidence_b_id ? '<div class="conflict-compare-id">' + esc(c.evidence_b_id) + '</div>' : '') +
        '</div>' +
      '</div>' +
      resolutionHtml +
    '</div>' +
    navHtml +
    '</div>';

  document.body.appendChild(overlay);
  // Trap escape key
  document.addEventListener("keydown", _conflictModalEscHandler);
}

function hideConflictModal() {
  var old = document.getElementById("conflict-modal-overlay");
  if (old) old.remove();
  document.removeEventListener("keydown", _conflictModalEscHandler);
}

function _conflictModalEscHandler(e) {
  if (e.key === "Escape") hideConflictModal();
}

function exportDocx() {
  if (!state.vectorId) {
    showToast("No research result available for export", "error");
    return;
  }
  showToast("Generating Word document...", "info");
  fetch("/api/research/export/" + encodeURIComponent(state.vectorId) + "/docx")
    .then(function(res) {
      if (!res.ok) throw new Error("Export failed: " + res.status);
      return res.blob();
    })
    .then(function(blob) {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (state.vectorId || "polaris") + "_report.docx";
      a.click();
      URL.revokeObjectURL(a.href);
      showToast("Exported " + a.download);
    })
    .catch(function(err) {
      showToast("Word export failed: " + err.message, "error");
    });
}
