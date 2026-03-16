"""
Apply Task 1 (Accessibility), Task 2 (Dead URL Detection), and Task 3 (Auth UI)
patches to live_dashboard.html and live_server.py.

Run: python scripts/apply_dashboard_patches.py
"""

import re
import sys
from pathlib import Path

DASHBOARD_PATH = Path(__file__).parent / "templates" / "live_dashboard.html"
SERVER_PATH = Path(__file__).parent / "live_server.py"


def patch_dashboard():
    """Apply accessibility + auth UI patches to live_dashboard.html."""
    content = DASHBOARD_PATH.read_text(encoding="utf-8")
    original = content

    # =========================================================================
    # TASK 1A: CSS for skip-link + keyboard focus on ev-card + example-card
    # TASK 3A: CSS for auth modal, auth button, history panel
    # Insert before </head>
    # =========================================================================
    css_block = """
/* =======================================================================
   Accessibility: Skip Navigation Link (I.3)
   ======================================================================= */
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  padding: 8px 16px;
  background: var(--success);
  color: #fff;
  z-index: 10000;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  transition: top 0.2s var(--ease);
  border-radius: 0 0 var(--radius-sm) 0;
}
.skip-link:focus { top: 0; }

/* Keyboard focus styles for interactive cards */
.ev-card:focus-visible,
.example-card:focus-visible,
.depth-chip:focus-visible,
.view-mode-btn:focus-visible,
.detail-panel-close:focus-visible,
.landing-submit-btn:focus-visible,
.user-progress-cancel:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* =======================================================================
   Auth UI Styles (2B.1)
   ======================================================================= */
.auth-button {
  padding: 4px 12px;
  font-size: 11px;
  font-family: var(--font-sans);
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-inset);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease);
  white-space: nowrap;
  margin-left: var(--sm);
}
.auth-button:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-dim);
}
.auth-button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Auth Modal Overlay */
#auth-modal {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  align-items: center;
  justify-content: center;
}
#auth-modal.visible { display: flex; }

.auth-modal-content {
  background: var(--bg-elevated);
  border: 1px solid var(--border-active);
  border-radius: var(--radius-xl);
  padding: var(--xl);
  width: 100%;
  max-width: 380px;
  box-shadow: var(--shadow-lg);
}
.auth-modal-content h2 {
  font-size: var(--text-xl);
  color: var(--text-primary);
  margin-bottom: var(--lg);
  text-align: center;
}
.auth-modal-content .auth-field {
  display: block;
  width: 100%;
  padding: 10px 14px;
  margin-bottom: var(--md);
  background: var(--bg-inset);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 14px;
  font-family: var(--font-sans);
}
.auth-modal-content .auth-field:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-dim);
}
.auth-modal-content .auth-submit-btn {
  display: block;
  width: 100%;
  padding: 10px;
  background: var(--accent);
  color: #0f172a;
  border: none;
  border-radius: var(--radius);
  font-size: 14px;
  font-weight: 600;
  font-family: var(--font-sans);
  cursor: pointer;
  transition: opacity var(--duration-fast) var(--ease);
}
.auth-modal-content .auth-submit-btn:hover { opacity: 0.9; }
.auth-modal-content .auth-submit-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.auth-modal-content .auth-error {
  display: none;
  color: var(--error);
  font-size: 12px;
  margin-top: var(--sm);
  text-align: center;
}
.auth-modal-close {
  position: absolute;
  top: var(--md);
  right: var(--md);
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 20px;
  cursor: pointer;
}
.auth-modal-close:hover { color: var(--text-primary); }

/* History Panel */
.history-panel {
  display: none;
  margin-top: var(--lg);
  max-width: 600px;
  width: 100%;
}
.history-panel.visible { display: block; }
.history-panel-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: var(--sm);
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: var(--xs);
}
.history-item {
  display: flex;
  align-items: center;
  gap: var(--md);
  padding: var(--sm) var(--md);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease);
}
.history-item:hover {
  border-color: var(--accent);
  background: var(--accent-dim);
}
.history-item:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.history-item-query {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-item-meta {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
}
.history-item-status {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}
.history-item-status.completed { background: var(--success-dim); color: var(--success); }
.history-item-status.failed { background: var(--error-dim); color: var(--error); }
.history-item-status.running { background: var(--accent-dim); color: var(--accent); }

"""
    # Insert CSS before </head>
    content = content.replace("</head>", css_block + "</head>", 1)

    # =========================================================================
    # TASK 1B: Skip-to-content link at top of body
    # =========================================================================
    content = content.replace(
        "<body>\n",
        '<body>\n<a href="#main-content" class="skip-link" '
        'onfocus="this.style.top=\'0\'" onblur="this.style.top=\'-40px\'">Skip to content</a>\n',
        1,
    )

    # =========================================================================
    # TASK 1C: Add id="main-content" to the views-container
    # =========================================================================
    content = content.replace(
        '<div class="views-container">',
        '<div class="views-container" id="main-content">',
        1,
    )

    # =========================================================================
    # TASK 1D: Add role="img" and aria-label to the graph-svg
    # =========================================================================
    content = content.replace(
        '<svg id="graph-svg"></svg>',
        '<svg id="graph-svg" role="img" aria-label="Evidence relationship graph visualization"></svg>',
        1,
    )

    # =========================================================================
    # TASK 1E: Add aria-label to dynamically built SVGs (faithfulness gauge)
    # In buildFaithGauge, add role="img" and aria-label
    # =========================================================================
    content = content.replace(
        "return '<div class=\"faith-gauge-circle\"><svg width=\"' + size + '\" height=\"' + size + '\" viewBox=\"0 0 ' + size + ' ' + size + '\">'",
        "return '<div class=\"faith-gauge-circle\"><svg role=\"img\" aria-label=\"Faithfulness gauge: ' + pctStr + '\" width=\"' + size + '\" height=\"' + size + '\" viewBox=\"0 0 ' + size + ' ' + size + '\">'",
        1,
    )

    # =========================================================================
    # TASK 1F: Add aria-label to buildSignalRadar SVG
    # =========================================================================
    content = content.replace(
        "var svg = '<svg width=\"' + size + '\" height=\"' + size + '\" viewBox=\"0 0 ' + size + ' ' + size + '\">';",
        "var svg = '<svg role=\"img\" aria-label=\"5-signal radar chart showing evidence quality scores\" width=\"' + size + '\" height=\"' + size + '\" viewBox=\"0 0 ' + size + ' ' + size + '\">';",
        1,
    )

    # =========================================================================
    # TASK 1G: Add aria-label to the detail panel radar SVG
    # =========================================================================
    content = content.replace(
        "var radarSvg = '<svg width=\"160\" height=\"175\" viewBox=\"0 0 160 175\" style=\"display:block;margin:0 auto var(--sm)\">';",
        "var radarSvg = '<svg role=\"img\" aria-label=\"5-signal radar chart for this evidence\" width=\"160\" height=\"175\" viewBox=\"0 0 160 175\" style=\"display:block;margin:0 auto var(--sm)\">';",
        1,
    )

    # =========================================================================
    # TASK 1H: Keyboard support for example-cards (tabindex + onkeydown)
    # =========================================================================
    content = content.replace(
        '<div class="example-card" onclick="useExample(this)">',
        '<div class="example-card" tabindex="0" role="button" onclick="useExample(this)" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){this.click();event.preventDefault();}">',
    )

    # =========================================================================
    # TASK 1I: Keyboard support for depth-chips
    # =========================================================================
    content = content.replace(
        '<button class="depth-chip" data-depth="quick" onclick="setDepth(\'quick\')">',
        '<button class="depth-chip" data-depth="quick" onclick="setDepth(\'quick\')" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){this.click();event.preventDefault();}">',
    )
    content = content.replace(
        '<button class="depth-chip active" data-depth="standard" onclick="setDepth(\'standard\')">',
        '<button class="depth-chip active" data-depth="standard" onclick="setDepth(\'standard\')" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){this.click();event.preventDefault();}">',
    )
    content = content.replace(
        '<button class="depth-chip" data-depth="deep" onclick="setDepth(\'deep\')">',
        '<button class="depth-chip" data-depth="deep" onclick="setDepth(\'deep\')" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){this.click();event.preventDefault();}">',
    )

    # =========================================================================
    # TASK 1J: Make ev-cards keyboard-accessible via JS
    # In renderEvidenceCards, the onclick is in JS-generated HTML.
    # We add tabindex="0" and onkeydown to ev-card divs.
    # =========================================================================
    content = content.replace(
        "var html = '<div class=\"ev-card\" onclick=\"selectEvidenceFromCard(\\'' + esc(p.id || \"\") + '\\')\">';",
        "var html = '<div class=\"ev-card\" tabindex=\"0\" role=\"button\" onclick=\"selectEvidenceFromCard(\\'' + esc(p.id || \"\") + '\\')\" onkeydown=\"if(event.key===\\'Enter\\'||event.key===\\' \\'){this.click();event.preventDefault();}\">';",
    )

    # =========================================================================
    # TASK 3B: Auth button in header (next to view mode toggle)
    # Insert after the header-meta div opening
    # =========================================================================
    content = content.replace(
        '  <div class="header-meta">',
        '  <button class="auth-button" id="auth-button" style="display:none" '
        'onclick="toggleAuthModal()" aria-label="Sign in or view account">Sign In</button>\n'
        '  <div class="header-meta">',
        1,
    )

    # =========================================================================
    # TASK 3C: Auth modal + history panel HTML (before toast container)
    # =========================================================================
    auth_html = """
<!-- ===================================================================
     AUTH MODAL (2B.1) — Hidden when auth not enabled
     =================================================================== -->
<div id="auth-modal" aria-modal="true" role="dialog" aria-labelledby="auth-modal-title">
  <div class="auth-modal-content" style="position:relative">
    <button class="auth-modal-close" onclick="closeAuthModal()" aria-label="Close sign-in dialog">&times;</button>
    <h2 id="auth-modal-title">Sign In</h2>
    <form onsubmit="handleLogin(event)" novalidate>
      <label for="auth-username" class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)">Username</label>
      <input type="text" id="auth-username" class="auth-field" placeholder="Username" required autocomplete="username">
      <label for="auth-password" class="sr-only" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)">Password</label>
      <input type="password" id="auth-password" class="auth-field" placeholder="Password" required autocomplete="current-password">
      <button type="submit" class="auth-submit-btn">Sign In</button>
    </form>
    <div class="auth-error" id="auth-error"></div>
  </div>
</div>

"""
    content = content.replace(
        '<!-- Toast container -->',
        auth_html + '<!-- Toast container -->',
        1,
    )

    # =========================================================================
    # TASK 3D: History panel in the landing page (after examples, before "how it works")
    # =========================================================================
    history_html = """
  <div class="history-panel" id="history-panel">
    <div class="history-panel-title">Recent Research</div>
    <div class="history-list" id="history-list"></div>
  </div>

"""
    content = content.replace(
        '  <div class="landing-how">',
        history_html + '  <div class="landing-how">',
        1,
    )

    # =========================================================================
    # TASK 3E: Auth JavaScript (before closing </script>)
    # =========================================================================
    auth_js = """
/* =====================================================================
   AUTH UI — Login/Logout/History (2B.1)
   ===================================================================== */
var _authEnabled = false;

function initAuth() {
  fetch("/api/auth/status")
  .then(function(r) { return r.json(); })
  .then(function(data) {
    _authEnabled = data.auth_enabled === true;
    if (_authEnabled) {
      document.getElementById("auth-button").style.display = "inline-flex";
      var token = localStorage.getItem("polaris_token");
      if (token) {
        checkAuthToken(token);
      }
    }
  })
  .catch(function() {
    // Auth endpoint not available, keep hidden
  });
}

function checkAuthToken(token) {
  fetch("/api/auth/me", {
    headers: {"Authorization": "Bearer " + token}
  })
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("invalid");
  })
  .then(function(data) {
    state.authenticated = true;
    state.user = data;
    updateAuthUI();
    loadResearchHistory();
  })
  .catch(function() {
    localStorage.removeItem("polaris_token");
    state.authenticated = false;
    state.user = null;
    updateAuthUI();
  });
}

function toggleAuthModal() {
  if (state.authenticated) {
    handleLogout();
  } else {
    openAuthModal();
  }
}

function openAuthModal() {
  var modal = document.getElementById("auth-modal");
  modal.classList.add("visible");
  setTimeout(function() {
    document.getElementById("auth-username").focus();
  }, 100);
}

function closeAuthModal() {
  document.getElementById("auth-modal").classList.remove("visible");
  document.getElementById("auth-error").style.display = "none";
  document.getElementById("auth-username").value = "";
  document.getElementById("auth-password").value = "";
}

function handleLogin(e) {
  e.preventDefault();
  var username = document.getElementById("auth-username").value;
  var password = document.getElementById("auth-password").value;
  var errorEl = document.getElementById("auth-error");
  errorEl.style.display = "none";

  fetch("/api/auth/login", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({username: username, password: password})
  })
  .then(function(r) {
    if (r.ok) return r.json();
    return r.json().then(function(d) { throw new Error(d.detail || "Invalid credentials"); });
  })
  .then(function(data) {
    localStorage.setItem("polaris_token", data.token);
    state.authenticated = true;
    state.user = {username: data.username, role: data.role};
    closeAuthModal();
    showToast("Signed in as " + data.username, "success");
    updateAuthUI();
    loadResearchHistory();
  })
  .catch(function(err) {
    errorEl.textContent = err.message || "Login failed";
    errorEl.style.display = "block";
  });
}

function handleLogout() {
  localStorage.removeItem("polaris_token");
  state.authenticated = false;
  state.user = null;
  updateAuthUI();
  var histPanel = document.getElementById("history-panel");
  if (histPanel) histPanel.classList.remove("visible");
  showToast("Signed out", "info");
}

function updateAuthUI() {
  var authBtn = document.getElementById("auth-button");
  if (!authBtn) return;
  if (state.authenticated && state.user) {
    authBtn.textContent = state.user.username || "User";
    authBtn.setAttribute("aria-label", "Signed in as " + (state.user.username || "User") + ". Click to sign out.");
  } else {
    authBtn.textContent = "Sign In";
    authBtn.setAttribute("aria-label", "Sign in or view account");
  }
}

function loadResearchHistory() {
  var token = localStorage.getItem("polaris_token");
  if (!token) return;
  fetch("/api/auth/history", {
    headers: {"Authorization": "Bearer " + token}
  })
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("unauthorized");
  })
  .then(function(history) {
    renderHistoryPanel(history);
  })
  .catch(function(err) {
    console.warn("Failed to load research history:", err);
  });
}

function renderHistoryPanel(sessions) {
  var panel = document.getElementById("history-panel");
  var list = document.getElementById("history-list");
  if (!panel || !list) return;
  if (!sessions || !sessions.length) { panel.classList.remove("visible"); return; }

  panel.classList.add("visible");
  var items = sessions.slice(0, 10);
  list.innerHTML = items.map(function(s) {
    var query = esc(truncStr(s.query || "Untitled", 80));
    var statusCls = (s.status || "").toLowerCase();
    var statusText = (s.status || "unknown").toUpperCase();
    var dateStr = "";
    if (s.created_at) {
      var d = new Date(s.created_at * 1000);
      dateStr = d.toLocaleDateString() + " " + d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
    }
    return '<div class="history-item" tabindex="0" role="button" ' +
      'onclick="loadHistoryItem(\\'' + esc(s.vector_id || "") + '\\')" ' +
      'onkeydown="if(event.key===\\'Enter\\'||event.key===\\' \\'){this.click();event.preventDefault();}" ' +
      'aria-label="View research: ' + query + '">' +
      '<span class="history-item-status ' + statusCls + '">' + statusText + '</span>' +
      '<span class="history-item-query">' + query + '</span>' +
      '<span class="history-item-meta">' + esc(dateStr) + '</span>' +
      '</div>';
  }).join("");
}

function loadHistoryItem(vectorId) {
  if (!vectorId) return;
  fetch("/api/research/result/" + encodeURIComponent(vectorId))
  .then(function(r) {
    if (r.ok) return r.json();
    throw new Error("not found");
  })
  .then(function(data) {
    state.pipelineComplete = true;
    state.vectorId = vectorId;
    if (data.final_report) state.fullReport = data.final_report;
    if (data.bibliography) state.bibliography = data.bibliography;
    updateUIVisibility();
    switchView("report");
    showToast("Loaded research: " + (data.query || vectorId), "info");
  })
  .catch(function(err) {
    showToast("Could not load result: " + err.message, "error");
  });
}

// Close auth modal on Escape key
document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") {
    var modal = document.getElementById("auth-modal");
    if (modal && modal.classList.contains("visible")) {
      closeAuthModal();
    }
  }
});

// Close auth modal on backdrop click
document.getElementById("auth-modal").addEventListener("click", function(e) {
  if (e.target === this) closeAuthModal();
});

// Initialize auth on page load
initAuth();

"""
    content = content.replace(
        "window._getDebugState = function() { return state; };",
        auth_js + "window._getDebugState = function() { return state; };",
        1,
    )

    # =========================================================================
    # TASK 3F: Add auth state fields to the state object
    # =========================================================================
    content = content.replace(
        "  graphMode: \"crossref\"",
        "  graphMode: \"crossref\",\n  authenticated: false,\n  user: null",
        1,
    )

    # =========================================================================
    # Verify changes were applied
    # =========================================================================
    changes_applied = []
    if ".skip-link" in content:
        changes_applied.append("Skip-link CSS")
    if "skip-link" in content and "Skip to content" in content:
        changes_applied.append("Skip-link HTML")
    if 'id="main-content"' in content:
        changes_applied.append("main-content id")
    if 'role="img" aria-label="Evidence relationship graph' in content:
        changes_applied.append("Graph SVG aria-label")
    if 'role="img" aria-label="Faithfulness gauge' in content:
        changes_applied.append("Faith gauge aria-label")
    if 'role="img" aria-label="5-signal radar chart showing' in content:
        changes_applied.append("Radar SVG aria-label")
    if 'role="img" aria-label="5-signal radar chart for this' in content:
        changes_applied.append("Detail radar aria-label")
    if 'tabindex="0" role="button" onclick="useExample' in content:
        changes_applied.append("Example card keyboard nav")
    if "auth-button" in content:
        changes_applied.append("Auth button in header")
    if "auth-modal" in content:
        changes_applied.append("Auth modal HTML")
    if "handleLogin" in content:
        changes_applied.append("Auth JavaScript")
    if "history-panel" in content:
        changes_applied.append("History panel")
    if "authenticated: false" in content:
        changes_applied.append("Auth state fields")

    print(f"Dashboard: {len(changes_applied)} patches applied:")
    for c in changes_applied:
        print(f"  + {c}")

    if content == original:
        print("ERROR: No changes were applied to dashboard!")
        return False

    DASHBOARD_PATH.write_text(content, encoding="utf-8")
    print(f"Dashboard written: {len(content)} chars")
    return True


def patch_server():
    """Apply dead URL detection patch to live_server.py."""
    content = SERVER_PATH.read_text(encoding="utf-8")
    original = content

    # =========================================================================
    # TASK 2A: Add aiohttp import at top of file (after existing imports)
    # =========================================================================
    if "import aiohttp" not in content:
        content = content.replace(
            "from sse_starlette.sse import EventSourceResponse",
            "from sse_starlette.sse import EventSourceResponse\n\nimport aiohttp",
            1,
        )

    # =========================================================================
    # TASK 2B: Add URL health check function before _build_pdf_html
    # =========================================================================
    url_health_fn = '''
# ---------------------------------------------------------------------------
# Dead URL Detection for PDF Export (I.3)
# ---------------------------------------------------------------------------
async def _check_url_health(url: str, timeout: float = 5.0) -> dict:
    """Check if a URL is accessible. Returns status dict."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
            ) as resp:
                return {"url": url, "status": resp.status, "alive": 200 <= resp.status < 400}
    except Exception:
        return {"url": url, "status": 0, "alive": False}


async def _check_bibliography_urls(bibliography: list[dict], concurrency: int = 10) -> list[dict]:
    """Check all bibliography URLs concurrently with a semaphore limit.

    Returns list of health check results with url, status, and alive fields.
    """
    urls = []
    for entry in bibliography:
        if isinstance(entry, dict):
            url = entry.get("url", "")
            if url and url.startswith("http"):
                urls.append(url)
        elif isinstance(entry, str) and entry.startswith("http"):
            urls.append(entry)

    if not urls:
        return []

    # Deduplicate
    unique_urls = list(dict.fromkeys(urls))

    sem = asyncio.Semaphore(concurrency)

    async def check_with_sem(u: str) -> dict:
        async with sem:
            return await _check_url_health(u)

    results = await asyncio.gather(
        *[check_with_sem(u) for u in unique_urls],
        return_exceptions=True,
    )

    health_results = []
    for r in results:
        if isinstance(r, dict):
            health_results.append(r)
        elif isinstance(r, Exception):
            health_results.append({"url": "unknown", "status": 0, "alive": False})

    return health_results


'''
    if "_check_url_health" not in content:
        content = content.replace(
            "def _build_pdf_html(result: dict, report_md: str) -> str:",
            url_health_fn + "def _build_pdf_html(result: dict, report_md: str) -> str:",
            1,
        )

    # =========================================================================
    # TASK 2C: Add url_health parameter to _build_pdf_html
    # =========================================================================
    content = content.replace(
        'def _build_pdf_html(result: dict, report_md: str) -> str:',
        'def _build_pdf_html(result: dict, report_md: str, url_health: list[dict] | None = None) -> str:',
        1,
    )

    # =========================================================================
    # TASK 2D: Add health status column to bibliography table
    # Build a URL->health lookup and add status column to biblio rows
    # Replace the bibliography table building section
    # =========================================================================
    old_biblio_build = '''    # Build bibliography HTML
    biblio_html_parts = []
    for i, entry in enumerate(bibliography, 1):
        if isinstance(entry, dict):
            title = html.escape(str(entry.get("title", "Untitled")))
            url = html.escape(str(entry.get("url", "")))
            authors = html.escape(str(entry.get("authors", "")))
            year = html.escape(str(entry.get("year", "")))

            # Build cell content incrementally (avoids nested f-string issues)
            cell = "<strong>" + title + "</strong>"
            if year:
                cell += " (" + year + ")"
            if authors:
                cell += "<br><em>" + authors + "</em>"
            if url:
                cell += '<br><a href="' + url + '">' + url + "</a>"
            biblio_html_parts.append(
                '<tr><td class="bib-num">[' + str(i) + "]</td>"
                "<td>" + cell + "</td></tr>"
            )
        elif isinstance(entry, str):
            biblio_html_parts.append(
                '<tr><td class="bib-num">[' + str(i) + "]</td>"
                "<td>" + html.escape(entry) + "</td></tr>"
            )

    biblio_table = (
        '<table class="bibliography">' + "\\n".join(biblio_html_parts) + "</table>"
        if biblio_html_parts
        else "<p><em>No bibliography entries available.</em></p>"
    )'''

    new_biblio_build = '''    # Build URL health lookup
    health_lookup: dict[str, dict] = {}
    if url_health:
        for h in url_health:
            health_lookup[h.get("url", "")] = h

    # Build bibliography HTML
    biblio_html_parts = []
    dead_count = 0
    total_checked = 0
    for i, entry in enumerate(bibliography, 1):
        if isinstance(entry, dict):
            title = html.escape(str(entry.get("title", "Untitled")))
            url = html.escape(str(entry.get("url", "")))
            raw_url = str(entry.get("url", ""))
            authors = html.escape(str(entry.get("authors", "")))
            year = html.escape(str(entry.get("year", "")))

            # Build cell content incrementally (avoids nested f-string issues)
            cell = "<strong>" + title + "</strong>"
            if year:
                cell += " (" + year + ")"
            if authors:
                cell += "<br><em>" + authors + "</em>"
            if url:
                cell += '<br><a href="' + url + '">' + url + "</a>"

            # URL health status column
            status_cell = ""
            if health_lookup and raw_url in health_lookup:
                total_checked += 1
                h = health_lookup[raw_url]
                if h.get("alive"):
                    status_cell = '<td style="text-align:center;color:#2a7a4a;font-size:14pt">&#10003;</td>'
                else:
                    dead_count += 1
                    status_cell = '<td style="text-align:center;color:#c0392b;font-size:14pt">&#10007;</td>'
            elif health_lookup:
                status_cell = '<td style="text-align:center;color:#999;font-size:9pt">--</td>'

            biblio_html_parts.append(
                '<tr><td class="bib-num">[' + str(i) + "]</td>"
                "<td>" + cell + "</td>" + status_cell + "</tr>"
            )
        elif isinstance(entry, str):
            status_cell = ""
            if health_lookup:
                status_cell = '<td style="text-align:center;color:#999;font-size:9pt">--</td>'
            biblio_html_parts.append(
                '<tr><td class="bib-num">[' + str(i) + "]</td>"
                "<td>" + html.escape(entry) + "</td>" + status_cell + "</tr>"
            )

    # Dead URL warning banner
    dead_url_banner = ""
    if total_checked > 0 and dead_count > 0:
        dead_pct = (dead_count / total_checked) * 100
        if dead_pct > 20:
            dead_url_banner = (
                '<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;'
                'padding:8pt;margin:8pt 0;font-size:10pt;color:#856404">'
                '<strong>Warning:</strong> '
                + str(dead_count) + ' of ' + str(total_checked)
                + ' URLs (' + f"{dead_pct:.0f}" + '%) returned errors or were unreachable.'
                + '</div>'
            )
        else:
            dead_url_banner = (
                '<div style="font-size:9pt;color:#666;margin:4pt 0">'
                + str(dead_count) + ' of ' + str(total_checked)
                + ' URLs returned errors.</div>'
            )

    # Add Status header if health data available
    bib_header = ""
    if health_lookup:
        bib_header = "<tr><th></th><th>Source</th><th>Status</th></tr>"

    biblio_table = (
        dead_url_banner
        + '<table class="bibliography">' + bib_header + "\\n".join(biblio_html_parts) + "</table>"
        if biblio_html_parts
        else "<p><em>No bibliography entries available.</em></p>"
    )'''

    content = content.replace(old_biblio_build, new_biblio_build, 1)

    # =========================================================================
    # TASK 2E: In the export endpoint, add URL health checking before PDF gen
    # =========================================================================
    old_export = """    # Generate HTML for PDF
    export_html = _build_pdf_html(result, report_md)"""

    new_export = """    # Check bibliography URL health (non-blocking, short timeout)
    bibliography = result.get("bibliography", [])
    url_health = []
    try:
        url_health = await _check_bibliography_urls(bibliography, concurrency=10)
        logger.info(
            "URL health check: %d/%d alive for vector_id=%s",
            sum(1 for h in url_health if h.get("alive")),
            len(url_health),
            safe_id,
        )
    except Exception as exc:
        logger.warning("URL health check failed (non-fatal): %s", exc)

    # Generate HTML for PDF
    export_html = _build_pdf_html(result, report_md, url_health=url_health)"""

    content = content.replace(old_export, new_export, 1)

    # =========================================================================
    # TASK 2F: Add history endpoint (wired to session manager)
    # Insert after the auth router mounting section
    # =========================================================================
    history_route = '''

# ---------------------------------------------------------------------------
# Research history endpoint (requires auth)
# ---------------------------------------------------------------------------
@app.get("/api/auth/history")
async def get_research_history(request: Request):
    """Get research history for the authenticated user.

    Falls back to listing recent result files if session manager unavailable.
    """
    # Try to get user from auth header
    user_id = "anonymous"
    if _AUTH_AVAILABLE and get_current_user is not None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from src.auth.auth_middleware import get_auth_manager
                auth_mgr = get_auth_manager()
                token = auth_header.split(" ", 1)[1]
                payload = auth_mgr.verify_token(token)
                if payload:
                    user_id = payload.get("user_id", payload.get("sub", "anonymous"))
            except Exception:
                pass

    # Try session manager first
    try:
        from src.auth.session_manager import SessionManager
        sm = SessionManager()
        history = sm.get_user_history(user_id, limit=50)
        return JSONResponse(history)
    except Exception:
        pass

    # Fallback: list recent result files
    results_dir = Path("outputs/polaris_graph")
    if not results_dir.exists():
        return JSONResponse([])

    result_files = sorted(results_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    history = []
    for f in result_files[:20]:
        if f.name.endswith("_report.md"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            history.append({
                "vector_id": f.stem,
                "query": data.get("original_query", data.get("query", "")),
                "status": data.get("status", "unknown"),
                "created_at": f.stat().st_mtime,
                "depth": data.get("depth", "standard"),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return JSONResponse(history)

'''

    if "get_research_history" not in content:
        content = content.replace(
            '# ---------------------------------------------------------------------------\n# Global Exception Handler',
            history_route + '# ---------------------------------------------------------------------------\n# Global Exception Handler',
            1,
        )

    # =========================================================================
    # Verify changes
    # =========================================================================
    changes_applied = []
    if "import aiohttp" in content:
        changes_applied.append("aiohttp import")
    if "_check_url_health" in content:
        changes_applied.append("URL health check function")
    if "_check_bibliography_urls" in content:
        changes_applied.append("Bibliography URL checker")
    if "url_health: list[dict]" in content:
        changes_applied.append("_build_pdf_html url_health param")
    if "health_lookup" in content:
        changes_applied.append("Health status in bibliography table")
    if "dead_url_banner" in content:
        changes_applied.append("Dead URL warning banner")
    if "url_health = await _check_bibliography_urls" in content:
        changes_applied.append("Export endpoint URL checking")
    if "get_research_history" in content:
        changes_applied.append("History endpoint")

    print(f"\nServer: {len(changes_applied)} patches applied:")
    for c in changes_applied:
        print(f"  + {c}")

    if content == original:
        print("ERROR: No changes were applied to server!")
        return False

    SERVER_PATH.write_text(content, encoding="utf-8")
    print(f"Server written: {len(content)} chars")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("POLARIS Dashboard & Server Patch Script")
    print("Tasks: I.3 Accessibility, Dead URL Detection, 2B.1 Auth UI")
    print("=" * 60)

    ok1 = patch_dashboard()
    ok2 = patch_server()

    print("\n" + "=" * 60)
    if ok1 and ok2:
        print("ALL PATCHES APPLIED SUCCESSFULLY")
    else:
        print("SOME PATCHES FAILED — check output above")
        sys.exit(1)
    print("=" * 60)
