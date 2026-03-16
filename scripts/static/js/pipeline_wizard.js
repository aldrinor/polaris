/* =====================================================================
   pipeline_wizard.js — Conversational wizard UI for POLARIS pipeline
   builder. Guides users through a 6-stage interview (problem, sources,
   analysis, verification, output, constraints) and produces a pipeline
   draft that can be loaded into the DAG editor.

   Dependencies: core.js (safeMarkdown, showToast, esc, state)
   ===================================================================== */

/* =====================================================================
   Style Injection
   ===================================================================== */
var _wizardStyleInjected = false;

function _injectWizardStyles() {
  if (_wizardStyleInjected) return;
  _wizardStyleInjected = true;

  var style = document.createElement("style");
  style.id = "polaris-wizard-styles";
  style.textContent = [

    /* ---- Progress bar ---- */
    ".wizard-progress {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: space-between;",
    "  padding: var(--sm) var(--md);",
    "  margin-bottom: var(--sm);",
    "  position: relative;",
    "}",

    ".wizard-progress-step {",
    "  display: flex;",
    "  flex-direction: column;",
    "  align-items: center;",
    "  gap: 4px;",
    "  flex: 1;",
    "  position: relative;",
    "  z-index: 1;",
    "}",

    ".wizard-progress-dot {",
    "  width: 24px;",
    "  height: 24px;",
    "  border-radius: 50%;",
    "  background: var(--bg-inset);",
    "  border: 2px solid var(--border);",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  font-size: 11px;",
    "  font-weight: 600;",
    "  color: var(--text-tertiary);",
    "  transition: all 0.25s ease;",
    "}",

    ".wizard-progress-dot.active {",
    "  background: var(--accent);",
    "  border-color: var(--accent);",
    "  color: #fff;",
    "  box-shadow: 0 0 0 3px var(--accent-dim);",
    "}",

    ".wizard-progress-dot.completed {",
    "  background: var(--success);",
    "  border-color: var(--success);",
    "  color: #fff;",
    "}",

    ".wizard-progress-label {",
    "  font-size: 9px;",
    "  font-weight: 500;",
    "  color: var(--text-tertiary);",
    "  text-transform: uppercase;",
    "  letter-spacing: 0.5px;",
    "  white-space: nowrap;",
    "  transition: color 0.25s ease;",
    "}",

    ".wizard-progress-label.active {",
    "  color: var(--accent);",
    "}",

    ".wizard-progress-label.completed {",
    "  color: var(--success);",
    "}",

    ".wizard-progress-line {",
    "  position: absolute;",
    "  top: 20px;",
    "  left: 12%;",
    "  right: 12%;",
    "  height: 2px;",
    "  background: var(--border);",
    "  z-index: 0;",
    "}",

    ".wizard-progress-line-fill {",
    "  height: 100%;",
    "  background: var(--success);",
    "  transition: width 0.4s ease;",
    "  border-radius: 1px;",
    "}",

    ".wizard-progress-pct {",
    "  font-size: 10px;",
    "  font-weight: 600;",
    "  color: var(--text-secondary);",
    "  position: absolute;",
    "  top: -2px;",
    "  right: 0;",
    "}",

    /* ---- Chat container ---- */
    ".wizard-chat {",
    "  max-height: 400px;",
    "  min-height: 180px;",
    "  overflow-y: auto;",
    "  padding: var(--sm);",
    "  display: flex;",
    "  flex-direction: column;",
    "  gap: var(--sm);",
    "  scroll-behavior: smooth;",
    "}",

    /* ---- Message bubbles ---- */
    ".wizard-msg {",
    "  display: flex;",
    "  flex-direction: column;",
    "  max-width: 88%;",
    "  animation: wizardFadeIn 0.25s ease;",
    "}",

    ".wizard-msg-user {",
    "  align-self: flex-end;",
    "  align-items: flex-end;",
    "}",

    ".wizard-msg-bot {",
    "  align-self: flex-start;",
    "  align-items: flex-start;",
    "}",

    ".wizard-msg-label {",
    "  font-size: 10px;",
    "  font-weight: 600;",
    "  color: var(--text-tertiary);",
    "  margin-bottom: 2px;",
    "  padding: 0 6px;",
    "  display: flex;",
    "  align-items: center;",
    "  gap: 4px;",
    "}",

    ".wizard-msg-label .sparkle {",
    "  font-size: 12px;",
    "}",

    ".wizard-msg-bubble {",
    "  padding: var(--sm) 12px;",
    "  border-radius: var(--radius);",
    "  font-size: 13px;",
    "  line-height: 1.55;",
    "  word-wrap: break-word;",
    "}",

    ".wizard-msg-user .wizard-msg-bubble {",
    "  background: var(--accent);",
    "  color: #fff;",
    "  border-bottom-right-radius: var(--radius-sm);",
    "}",

    ".wizard-msg-bot .wizard-msg-bubble {",
    "  background: var(--bg-card);",
    "  color: var(--text-primary);",
    "  border: 1px solid var(--border);",
    "  border-bottom-left-radius: var(--radius-sm);",
    "}",

    ".wizard-msg-bot .wizard-msg-bubble p {",
    "  margin: 0 0 6px 0;",
    "}",
    ".wizard-msg-bot .wizard-msg-bubble p:last-child {",
    "  margin-bottom: 0;",
    "}",
    ".wizard-msg-bot .wizard-msg-bubble ul,",
    ".wizard-msg-bot .wizard-msg-bubble ol {",
    "  margin: 4px 0;",
    "  padding-left: 18px;",
    "}",
    ".wizard-msg-bot .wizard-msg-bubble code {",
    "  background: var(--bg-inset);",
    "  padding: 1px 4px;",
    "  border-radius: 3px;",
    "  font-family: var(--font-mono);",
    "  font-size: 12px;",
    "}",

    /* ---- Typing indicator ---- */
    ".wizard-typing {",
    "  display: flex;",
    "  align-items: center;",
    "  gap: 4px;",
    "  padding: 10px 14px;",
    "  align-self: flex-start;",
    "}",

    ".wizard-typing-dot {",
    "  width: 6px;",
    "  height: 6px;",
    "  border-radius: 50%;",
    "  background: var(--text-tertiary);",
    "  animation: wizardPulse 1.4s ease-in-out infinite;",
    "}",

    ".wizard-typing-dot:nth-child(2) {",
    "  animation-delay: 0.2s;",
    "}",

    ".wizard-typing-dot:nth-child(3) {",
    "  animation-delay: 0.4s;",
    "}",

    "@keyframes wizardPulse {",
    "  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }",
    "  40% { opacity: 1; transform: scale(1.1); }",
    "}",

    "@keyframes wizardFadeIn {",
    "  from { opacity: 0; transform: translateY(6px); }",
    "  to { opacity: 1; transform: translateY(0); }",
    "}",

    /* ---- Input area ---- */
    ".wizard-input-wrap {",
    "  padding: var(--sm);",
    "  border-top: 1px solid var(--border);",
    "}",

    ".wizard-chips {",
    "  display: flex;",
    "  flex-wrap: wrap;",
    "  gap: 6px;",
    "  margin-bottom: var(--sm);",
    "  min-height: 0;",
    "}",

    ".wizard-chips:empty {",
    "  display: none;",
    "}",

    ".wizard-chip {",
    "  display: inline-flex;",
    "  align-items: center;",
    "  padding: 4px 12px;",
    "  border-radius: 100px;",
    "  border: 1px solid var(--border);",
    "  background: var(--bg-elevated);",
    "  color: var(--text-secondary);",
    "  font-size: 12px;",
    "  font-weight: 500;",
    "  cursor: pointer;",
    "  transition: all 0.15s ease;",
    "  white-space: nowrap;",
    "}",

    ".wizard-chip:hover {",
    "  border-color: var(--accent);",
    "  color: var(--accent);",
    "  background: var(--accent-dim);",
    "}",

    ".wizard-chip:active {",
    "  transform: scale(0.96);",
    "}",

    ".wizard-input-row {",
    "  display: flex;",
    "  gap: 6px;",
    "}",

    ".wizard-input {",
    "  flex: 1;",
    "  padding: 8px 12px;",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius);",
    "  background: var(--bg-inset);",
    "  color: var(--text-primary);",
    "  font-size: 13px;",
    "  font-family: var(--font-sans);",
    "  outline: none;",
    "  transition: border-color 0.15s ease;",
    "}",

    ".wizard-input:focus {",
    "  border-color: var(--accent);",
    "}",

    ".wizard-input:disabled {",
    "  opacity: 0.5;",
    "  cursor: not-allowed;",
    "}",

    ".wizard-send-btn {",
    "  padding: 8px 16px;",
    "  border: none;",
    "  border-radius: var(--radius);",
    "  background: var(--accent);",
    "  color: #fff;",
    "  font-size: 13px;",
    "  font-weight: 600;",
    "  cursor: pointer;",
    "  transition: all 0.15s ease;",
    "  white-space: nowrap;",
    "}",

    ".wizard-send-btn:hover {",
    "  filter: brightness(1.1);",
    "}",

    ".wizard-send-btn:active {",
    "  transform: scale(0.97);",
    "}",

    ".wizard-send-btn:disabled {",
    "  opacity: 0.5;",
    "  cursor: not-allowed;",
    "}",

    /* ---- Close button ---- */
    ".wizard-close-btn {",
    "  background: none;",
    "  border: none;",
    "  color: var(--text-tertiary);",
    "  font-size: 20px;",
    "  cursor: pointer;",
    "  padding: 2px 6px;",
    "  line-height: 1;",
    "  border-radius: var(--radius-sm);",
    "  transition: all 0.15s ease;",
    "}",

    ".wizard-close-btn:hover {",
    "  color: var(--text-primary);",
    "  background: var(--bg-hover);",
    "}",

    /* ---- Pipeline draft card ---- */
    ".wizard-draft-card {",
    "  background: var(--bg-elevated);",
    "  border: 1px solid var(--success);",
    "  border-radius: var(--radius);",
    "  padding: 12px;",
    "  margin-top: var(--sm);",
    "}",

    ".wizard-draft-card-header {",
    "  display: flex;",
    "  align-items: center;",
    "  gap: var(--sm);",
    "  margin-bottom: var(--sm);",
    "}",

    ".wizard-draft-card-icon {",
    "  font-size: 18px;",
    "}",

    ".wizard-draft-card-title {",
    "  font-size: 14px;",
    "  font-weight: 600;",
    "  color: var(--success);",
    "}",

    ".wizard-draft-card-meta {",
    "  display: flex;",
    "  gap: var(--md);",
    "  margin-bottom: 10px;",
    "  font-size: 12px;",
    "  color: var(--text-secondary);",
    "}",

    ".wizard-draft-card-meta span {",
    "  display: inline-flex;",
    "  align-items: center;",
    "  gap: 4px;",
    "}",

    ".wizard-draft-card-actions {",
    "  display: flex;",
    "  gap: var(--sm);",
    "}",

    ".wizard-draft-btn-primary {",
    "  flex: 1;",
    "  padding: 8px 12px;",
    "  border: none;",
    "  border-radius: var(--radius);",
    "  background: var(--accent);",
    "  color: #fff;",
    "  font-size: 12px;",
    "  font-weight: 600;",
    "  cursor: pointer;",
    "  transition: all 0.15s ease;",
    "}",

    ".wizard-draft-btn-primary:hover {",
    "  filter: brightness(1.1);",
    "}",

    ".wizard-draft-btn-secondary {",
    "  flex: 1;",
    "  padding: 8px 12px;",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius);",
    "  background: var(--bg-card);",
    "  color: var(--text-secondary);",
    "  font-size: 12px;",
    "  font-weight: 600;",
    "  cursor: pointer;",
    "  transition: all 0.15s ease;",
    "}",

    ".wizard-draft-btn-secondary:hover {",
    "  border-color: var(--border-active);",
    "  color: var(--text-primary);",
    "}",

    /* ---- Error message inside chat ---- */
    ".wizard-msg-error .wizard-msg-bubble {",
    "  background: rgba(239, 68, 68, 0.08);",
    "  border-color: var(--error);",
    "  color: var(--error);",
    "}",

    /* ---- Session-expired retry link ---- */
    ".wizard-retry-link {",
    "  color: var(--accent);",
    "  cursor: pointer;",
    "  text-decoration: underline;",
    "  font-weight: 600;",
    "}",

    ".wizard-retry-link:hover {",
    "  opacity: 0.8;",
    "}"

  ].join("\n");
  document.head.appendChild(style);
}

/* =====================================================================
   Module State
   ===================================================================== */
var _wizardSessionId = null;
var _wizardMessages = [];
var _wizardStage = "";
var _wizardCompletionPct = 0;
var _wizardPendingRequest = false;
var _wizardLatestDraft = null;

/* Stage metadata — order matters */
var _WIZARD_STAGES = [
  { key: "problem",       label: "Problem" },
  { key: "sources",       label: "Sources" },
  { key: "analysis",      label: "Analysis" },
  { key: "verification",  label: "Verification" },
  { key: "output",        label: "Output" },
  { key: "constraints",   label: "Constraints" }
];

/* =====================================================================
   Progress Bar Rendering
   ===================================================================== */
function _renderWizardProgress() {
  var el = document.getElementById("wizard-progress");
  if (!el) return;

  var currentIdx = _getStageIndex(_wizardStage);
  var pct = Math.round(_wizardCompletionPct);

  var html = '<div class="wizard-progress-line">' +
    '<div class="wizard-progress-line-fill" style="width:' + pct + '%"></div>' +
    '</div>';

  html += '<span class="wizard-progress-pct">' + pct + '%</span>';

  for (var i = 0; i < _WIZARD_STAGES.length; i++) {
    var s = _WIZARD_STAGES[i];
    var dotClass = "wizard-progress-dot";
    var labelClass = "wizard-progress-label";

    if (i < currentIdx) {
      dotClass += " completed";
      labelClass += " completed";
    } else if (i === currentIdx) {
      dotClass += " active";
      labelClass += " active";
    }

    var dotContent = "";
    if (i < currentIdx) {
      dotContent = "&#10003;"; /* checkmark */
    } else {
      dotContent = String(i + 1);
    }

    html += '<div class="wizard-progress-step">' +
      '<div class="' + dotClass + '">' + dotContent + '</div>' +
      '<span class="' + labelClass + '">' + esc(s.label) + '</span>' +
      '</div>';
  }

  el.innerHTML = html;
}

function _getStageIndex(stageKey) {
  for (var i = 0; i < _WIZARD_STAGES.length; i++) {
    if (_WIZARD_STAGES[i].key === stageKey) return i;
  }
  return 0;
}

/* =====================================================================
   Chat Rendering
   ===================================================================== */
function _renderWizardChat() {
  var el = document.getElementById("wizard-chat");
  if (!el) return;

  var html = "";
  for (var i = 0; i < _wizardMessages.length; i++) {
    var msg = _wizardMessages[i];
    html += _buildMessageHtml(msg);
  }

  el.innerHTML = html;
  _scrollWizardChat();
}

function _appendWizardMessage(msg) {
  _wizardMessages.push(msg);
  var el = document.getElementById("wizard-chat");
  if (!el) return;

  /* Remove typing indicator if present */
  _removeTypingIndicator();

  var wrapper = document.createElement("div");
  wrapper.innerHTML = _buildMessageHtml(msg);
  while (wrapper.firstChild) {
    el.appendChild(wrapper.firstChild);
  }
  _scrollWizardChat();
}

function _buildMessageHtml(msg) {
  var isUser = msg.role === "user";
  var isError = msg.role === "error";
  var wrapClass = "wizard-msg";

  if (isUser) {
    wrapClass += " wizard-msg-user";
  } else if (isError) {
    wrapClass += " wizard-msg-bot wizard-msg-error";
  } else {
    wrapClass += " wizard-msg-bot";
  }

  var labelHtml = "";
  if (isUser) {
    labelHtml = '<div class="wizard-msg-label">You</div>';
  } else {
    labelHtml = '<div class="wizard-msg-label">' +
      '<span class="sparkle">&#10024;</span> Wizard</div>';
  }

  var contentHtml = "";
  if (isUser) {
    contentHtml = esc(msg.text);
  } else if (typeof safeMarkdown === "function") {
    contentHtml = safeMarkdown(msg.text);
  } else {
    contentHtml = esc(msg.text);
  }

  var draftHtml = "";
  if (msg.draft) {
    draftHtml = _buildDraftCardHtml(msg.draft);
  }

  return '<div class="' + wrapClass + '">' +
    labelHtml +
    '<div class="wizard-msg-bubble">' + contentHtml + '</div>' +
    draftHtml +
    '</div>';
}

function _scrollWizardChat() {
  var el = document.getElementById("wizard-chat");
  if (el) {
    requestAnimationFrame(function() {
      el.scrollTop = el.scrollHeight;
    });
  }
}

/* =====================================================================
   Typing Indicator
   ===================================================================== */
function _showTypingIndicator() {
  var el = document.getElementById("wizard-chat");
  if (!el) return;
  _removeTypingIndicator();

  var indicator = document.createElement("div");
  indicator.className = "wizard-typing";
  indicator.id = "wizard-typing-indicator";
  indicator.innerHTML =
    '<div class="wizard-typing-dot"></div>' +
    '<div class="wizard-typing-dot"></div>' +
    '<div class="wizard-typing-dot"></div>';
  el.appendChild(indicator);
  _scrollWizardChat();
}

function _removeTypingIndicator() {
  var indicator = document.getElementById("wizard-typing-indicator");
  if (indicator) indicator.remove();
}

/* =====================================================================
   Quick-Reply Chips
   ===================================================================== */
function _renderWizardChips(chips) {
  var el = document.getElementById("wizard-chips");
  if (!el) return;

  if (!chips || !chips.length) {
    el.innerHTML = "";
    return;
  }

  var html = "";
  for (var i = 0; i < chips.length; i++) {
    html += '<button class="wizard-chip" onclick="_onWizardChipClick(this)" ' +
      'data-chip-text="' + esc(chips[i]).replace(/"/g, '&quot;') + '">' +
      esc(chips[i]) + '</button>';
  }
  el.innerHTML = html;
}

function _onWizardChipClick(btn) {
  var text = btn.getAttribute("data-chip-text");
  if (!text) return;

  var input = document.getElementById("wizard-input");
  if (input) input.value = text;

  sendWizardMessage();
}

/* =====================================================================
   Pipeline Draft Card
   ===================================================================== */
function _buildDraftCardHtml(draft) {
  if (!draft) return "";

  _wizardLatestDraft = draft;

  var name = draft.name || draft.pipeline_name || "Custom Pipeline";
  var stages = 0;
  var nodes = 0;

  if (draft.stages && Array.isArray(draft.stages)) {
    stages = draft.stages.length;
    for (var i = 0; i < draft.stages.length; i++) {
      var s = draft.stages[i];
      if (s.nodes && Array.isArray(s.nodes)) {
        nodes += s.nodes.length;
      } else {
        nodes += 1;
      }
    }
  } else if (draft.nodes && Array.isArray(draft.nodes)) {
    nodes = draft.nodes.length;
  }

  return '<div class="wizard-draft-card">' +
    '<div class="wizard-draft-card-header">' +
      '<span class="wizard-draft-card-icon">&#9889;</span>' +
      '<span class="wizard-draft-card-title">Pipeline Draft Ready</span>' +
    '</div>' +
    '<div class="wizard-draft-card-meta">' +
      '<span><strong>' + esc(name) + '</strong></span>' +
      (stages > 0 ? '<span>' + stages + ' stage' + (stages !== 1 ? 's' : '') + '</span>' : '') +
      (nodes > 0 ? '<span>' + nodes + ' node' + (nodes !== 1 ? 's' : '') + '</span>' : '') +
    '</div>' +
    '<div class="wizard-draft-card-actions">' +
      '<button class="wizard-draft-btn-primary" onclick="_wizardUseDraft()">Use This Pipeline</button>' +
      '<button class="wizard-draft-btn-secondary" onclick="_wizardEditDraft()">Edit Manually</button>' +
    '</div>' +
  '</div>';
}

function _wizardUseDraft() {
  if (!_wizardSessionId) {
    showToast("No active wizard session", "error");
    return;
  }

  _setWizardInputEnabled(false);

  fetch("/api/wizard/finalize/" + encodeURIComponent(_wizardSessionId), {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  })
  .then(function(resp) {
    if (!resp.ok) throw new Error("Finalize failed: " + resp.status);
    return resp.json();
  })
  .then(function(data) {
    var pipeline = data.pipeline || _wizardLatestDraft;
    showToast("Pipeline created successfully", "success");

    if (typeof loadPipelineIntoEditor === "function") {
      loadPipelineIntoEditor(pipeline);
    }

    closeWizard();
  })
  .catch(function(err) {
    showToast("Failed to finalize pipeline: " + err.message, "error");
    _setWizardInputEnabled(true);
  });
}

function _wizardEditDraft() {
  var pipeline = _wizardLatestDraft;
  if (!pipeline) {
    showToast("No draft available", "warning");
    return;
  }

  if (typeof loadPipelineIntoEditor === "function") {
    loadPipelineIntoEditor(pipeline);
  }

  closeWizard();
  showToast("Draft loaded into editor", "info");
}

/* =====================================================================
   Input Handling
   ===================================================================== */
function _setupWizardInput() {
  var input = document.getElementById("wizard-input");
  if (!input) return;

  /* Prevent duplicate listeners by tagging */
  if (input.dataset.wizardBound === "1") return;
  input.dataset.wizardBound = "1";

  input.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendWizardMessage();
    }
  });
}

function _setWizardInputEnabled(enabled) {
  var input = document.getElementById("wizard-input");
  var btn = document.getElementById("wizard-send-btn");

  if (input) input.disabled = !enabled;
  if (btn) btn.disabled = !enabled;

  _wizardPendingRequest = !enabled;
}

/* =====================================================================
   API Calls
   ===================================================================== */
function _wizardApiStart() {
  return fetch("/api/wizard/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  })
  .then(function(resp) {
    if (!resp.ok) throw new Error("Start failed: HTTP " + resp.status);
    return resp.json();
  });
}

function _wizardApiChat(sessionId, message) {
  return fetch("/api/wizard/chat/" + encodeURIComponent(sessionId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: message })
  })
  .then(function(resp) {
    if (resp.status === 404 || resp.status === 410) {
      var err = new Error("Session expired");
      err.sessionExpired = true;
      throw err;
    }
    if (!resp.ok) throw new Error("Chat failed: HTTP " + resp.status);
    return resp.json();
  });
}

/* =====================================================================
   Public API
   ===================================================================== */

/**
 * showWizardPanel() — Show the wizard section, hide template section,
 * and start a new conversational session.
 */
function showWizardPanel() {
  _injectWizardStyles();
  _setupWizardInput();

  /* Toggle section visibility */
  var wizardSection = document.getElementById("pipeline-wizard-section");
  var templateSection = document.getElementById("pipeline-template-section");
  if (wizardSection) wizardSection.style.display = "";
  if (templateSection) templateSection.style.display = "none";

  /* Reset module state */
  _wizardSessionId = null;
  _wizardMessages = [];
  _wizardStage = "";
  _wizardCompletionPct = 0;
  _wizardLatestDraft = null;

  /* Clear UI */
  _renderWizardProgress();
  _renderWizardChips([]);
  var chatEl = document.getElementById("wizard-chat");
  if (chatEl) chatEl.innerHTML = "";

  /* Show typing indicator while starting */
  _showTypingIndicator();
  _setWizardInputEnabled(false);

  /* Start session */
  _wizardApiStart()
  .then(function(data) {
    _wizardSessionId = data.session_id;
    _wizardStage = data.stage || "problem";
    _wizardCompletionPct = data.completion_pct || 0;

    _renderWizardProgress();

    if (data.greeting || data.response) {
      _appendWizardMessage({
        role: "bot",
        text: data.greeting || data.response
      });
    }

    _renderWizardChips(data.chips || []);
    _setWizardInputEnabled(true);

    /* Focus input */
    var input = document.getElementById("wizard-input");
    if (input) input.focus();
  })
  .catch(function(err) {
    _removeTypingIndicator();
    _appendWizardMessage({
      role: "error",
      text: "Failed to start wizard session: " + err.message
    });
    showToast("Could not start wizard", "error");
    _setWizardInputEnabled(true);
  });
}

/**
 * closeWizard() — Hide wizard section, show template section.
 */
function closeWizard() {
  var wizardSection = document.getElementById("pipeline-wizard-section");
  var templateSection = document.getElementById("pipeline-template-section");

  if (wizardSection) wizardSection.style.display = "none";
  if (templateSection) templateSection.style.display = "";

  /* Clean up state but keep session alive on backend */
  _wizardPendingRequest = false;
  _removeTypingIndicator();
}

/**
 * sendWizardMessage() — Send user input to the wizard backend.
 */
function sendWizardMessage() {
  if (_wizardPendingRequest) return;

  var input = document.getElementById("wizard-input");
  if (!input) return;

  var text = input.value.trim();
  if (!text) return;

  if (!_wizardSessionId) {
    showToast("No active wizard session. Starting a new one.", "warning");
    showWizardPanel();
    return;
  }

  /* Clear input immediately */
  input.value = "";

  /* Add user message to chat */
  _appendWizardMessage({ role: "user", text: text });

  /* Clear chips while waiting */
  _renderWizardChips([]);

  /* Show typing indicator and disable input */
  _showTypingIndicator();
  _setWizardInputEnabled(false);

  /* Send to API */
  _wizardApiChat(_wizardSessionId, text)
  .then(function(data) {
    _wizardStage = data.stage || _wizardStage;
    _wizardCompletionPct = data.completion_pct || _wizardCompletionPct;

    _renderWizardProgress();

    /* Build message with optional draft */
    var msg = {
      role: "bot",
      text: data.response || ""
    };
    if (data.pipeline_draft) {
      msg.draft = data.pipeline_draft;
    }
    _appendWizardMessage(msg);

    _renderWizardChips(data.chips || []);
    _setWizardInputEnabled(true);

    /* Focus input */
    if (input) input.focus();
  })
  .catch(function(err) {
    _removeTypingIndicator();
    _setWizardInputEnabled(true);

    if (err.sessionExpired) {
      _appendWizardMessage({
        role: "error",
        text: 'Your session has expired. <span class="wizard-retry-link" ' +
          'onclick="showWizardPanel()">Start a new session</span>'
      });
      showToast("Wizard session expired", "warning");
    } else {
      _appendWizardMessage({
        role: "error",
        text: "Something went wrong: " + esc(err.message)
      });
      showToast("Wizard error: " + err.message, "error");
    }

    if (input) input.focus();
  });
}

/**
 * openWizard() — Alias for showWizardPanel, called from pipeline
 * editor toolbar.
 */
function openWizard() {
  showWizardPanel();
}
