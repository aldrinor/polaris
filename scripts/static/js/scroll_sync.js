/* =====================================================================
   scroll_sync.js — IntersectionObserver-based citation sync

   As user scrolls the report in the center panel, this module detects
   which section heading is near the top of the viewport, collects all
   citation references between it and the next heading, and updates the
   right sidebar via renderCitationSidebar().

   Depends on: workspace_manager.js (renderCitationSidebar)
   ===================================================================== */

var _scrollSyncObserver = null;
var _scrollSyncRaf = null;
var _scrollSyncActiveHeadingId = null;

/**
 * Initialize scroll-sync for a report block element.
 * Sets up IntersectionObserver on all h2/h3 headings inside it.
 *
 * @param {HTMLElement} reportBlock - The .ws-report-block element
 */
function initScrollSync(reportBlock) {
  // Cleanup previous observer
  if (_scrollSyncObserver) {
    _scrollSyncObserver.disconnect();
    _scrollSyncObserver = null;
  }

  if (!reportBlock) return;

  var headings = reportBlock.querySelectorAll("h2, h3");
  if (headings.length === 0) return;

  // Use rootMargin to detect heading near the top 30% of viewport
  _scrollSyncObserver = new IntersectionObserver(function(entries) {
    // Debounce via requestAnimationFrame
    if (_scrollSyncRaf) cancelAnimationFrame(_scrollSyncRaf);
    _scrollSyncRaf = requestAnimationFrame(function() {
      _handleScrollSyncEntries(entries, reportBlock);
    });
  }, {
    root: document.getElementById("ws-thread"),
    rootMargin: "-10% 0px -70% 0px",
    threshold: 0
  });

  headings.forEach(function(h) {
    _scrollSyncObserver.observe(h);
  });
}

/**
 * Handle IntersectionObserver entries.
 * Find the topmost visible heading and collect citations between it and next heading.
 */
function _handleScrollSyncEntries(entries, reportBlock) {
  var visibleHeading = null;

  entries.forEach(function(entry) {
    if (entry.isIntersecting) {
      visibleHeading = entry.target;
    }
  });

  if (!visibleHeading) return;
  if (visibleHeading.id === _scrollSyncActiveHeadingId) return;
  _scrollSyncActiveHeadingId = visibleHeading.id;

  // Collect citation numbers between this heading and the next
  var citeNumbers = _collectCitesBetweenHeadings(visibleHeading, reportBlock);

  // Update sidebar
  if (typeof renderCitationSidebar === "function") {
    renderCitationSidebar(citeNumbers);
  }
}

/**
 * Collect all unique citation numbers between a heading and the next heading.
 */
function _collectCitesBetweenHeadings(heading, reportBlock) {
  var cites = new Set();
  var current = heading.nextElementSibling;

  while (current) {
    // Stop at next heading of same or higher level
    var tag = current.tagName;
    if (tag === "H1" || tag === "H2" || tag === "H3") break;

    // Find all cite-ref elements
    var refs = current.querySelectorAll(".cite-ref[data-cite]");
    refs.forEach(function(ref) {
      var num = parseInt(ref.getAttribute("data-cite"));
      if (num && !isNaN(num)) cites.add(num);
    });

    current = current.nextElementSibling;
  }

  // Also check the heading itself
  var headingRefs = heading.querySelectorAll(".cite-ref[data-cite]");
  headingRefs.forEach(function(ref) {
    var num = parseInt(ref.getAttribute("data-cite"));
    if (num && !isNaN(num)) cites.add(num);
  });

  return Array.from(cites).sort(function(a, b) { return a - b; });
}

/**
 * Cleanup observer when workspace phase changes or component unmounts.
 */
function destroyScrollSync() {
  if (_scrollSyncObserver) {
    _scrollSyncObserver.disconnect();
    _scrollSyncObserver = null;
  }
  _scrollSyncActiveHeadingId = null;
}
