/* =====================================================================
   pipeline_editor.js — Pipeline DAG editor with collapsible macro-stage
   visualization, stage config panel, drag-and-drop, zoom/pan, and
   full CRUD against the /api/pipelines endpoints.

   Global functions exposed:
     renderPipelinesView, savePipeline, validatePipeline, runPipeline,
     pipelineZoomIn, pipelineZoomOut, pipelineFitView, startNewPipeline,
     openWizard, closeWizard, closeConfigPanel, loadPipelineIntoEditor
   ===================================================================== */

/* =====================================================================
   CSS — injected once on first load
   ===================================================================== */
var _pipelineStylesInjected = false;
function _injectPipelineStyles() {
  if (_pipelineStylesInjected) return;
  _pipelineStylesInjected = true;
  var css = document.createElement("style");
  css.id = "pipeline-editor-styles";
  css.textContent = [
    /* Layout: 3-column grid */
    '.pipelines-view { display: grid; grid-template-columns: 260px 1fr 0; gap: 0; height: 100%; min-height: 0; position: relative; }',
    '.pipelines-view.config-open { grid-template-columns: 260px 1fr 320px; }',

    /* Left sidebar */
    '.pipelines-sidebar { background: var(--bg-secondary); border-right: 1px solid var(--border); overflow-y: auto; display: flex; flex-direction: column; gap: 0; }',
    '.pipelines-sidebar-section { padding: var(--md); border-bottom: 1px solid var(--border); }',
    '.pipelines-sidebar-title { font-size: var(--text-sm); font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: var(--sm); display: flex; align-items: center; justify-content: space-between; }',

    /* Template cards */
    '.pipeline-template-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sm) var(--pad-card); margin-bottom: var(--sm); cursor: pointer; transition: border-color var(--duration-fast) var(--ease), box-shadow var(--duration-fast) var(--ease); }',
    '.pipeline-template-card:hover { border-color: var(--accent); box-shadow: var(--shadow-sm); }',
    '.pipeline-template-card-name { font-size: var(--text-base); font-weight: 600; color: var(--text-primary); margin-bottom: 2px; display: flex; align-items: center; gap: var(--xs); }',
    '.pipeline-template-card-desc { font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.35; margin-bottom: var(--xs); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }',
    '.pipeline-template-card-meta { display: flex; align-items: center; gap: var(--sm); font-size: var(--text-2xs); color: var(--text-tertiary); }',
    '.pipeline-template-card-badge { background: var(--accent-dim); color: var(--accent); padding: 1px 6px; border-radius: 9px; font-weight: 600; font-size: var(--text-3xs); }',
    '.pipeline-template-card-actions { display: flex; gap: var(--xs); margin-top: var(--xs); }',
    '.pipe-use-btn { background: var(--accent-dim); color: var(--accent); border: none; border-radius: var(--radius-sm); padding: 4px 10px; font-size: var(--text-2xs); font-weight: 600; cursor: pointer; transition: background var(--duration-fast) var(--ease); min-height: 36px; display: inline-flex; align-items: center; }',
    '.pipe-use-btn:hover { background: var(--accent); color: var(--bg-primary); }',

    /* Saved pipeline cards */
    '.pipeline-saved-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--sm) var(--pad-card); margin-bottom: var(--sm); display: flex; align-items: center; justify-content: space-between; }',
    '.pipeline-saved-card-name { font-size: var(--text-sm); font-weight: 500; color: var(--text-primary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }',
    '.pipeline-saved-card-actions { display: flex; gap: var(--xs); flex-shrink: 0; }',
    '.pipe-edit-btn, .pipe-delete-btn { background: none; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 4px 8px; font-size: var(--text-2xs); cursor: pointer; color: var(--text-secondary); transition: all var(--duration-fast) var(--ease); min-height: 36px; min-width: 36px; display: inline-flex; align-items: center; justify-content: center; }',
    '.pipe-edit-btn:hover { border-color: var(--accent); color: var(--accent); }',
    '.pipe-delete-btn:hover { border-color: var(--error); color: var(--error); }',

    /* New pipeline button */
    '.pipeline-new-btn { width: 100%; background: var(--bg-elevated); border: 1px dashed var(--border); border-radius: var(--radius); padding: var(--sm); font-size: var(--text-sm); color: var(--text-secondary); cursor: pointer; transition: all var(--duration-fast) var(--ease); margin-top: var(--xs); }',
    '.pipeline-new-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }',

    /* Canvas wrap */
    '.pipelines-canvas-wrap { position: relative; background: var(--bg-primary); overflow: hidden; display: flex; flex-direction: column; min-height: 0; }',

    /* Toolbar */
    '.pipelines-toolbar { display: flex; align-items: center; gap: var(--xs); padding: var(--xs) var(--sm); background: var(--bg-secondary); border-bottom: 1px solid var(--border); flex-shrink: 0; z-index: 2; }',
    '.pipe-tool-btn { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 4px 12px; font-size: var(--text-xs); font-weight: 500; color: var(--text-secondary); cursor: pointer; transition: all var(--duration-fast) var(--ease); font-family: var(--font-sans); }',
    '.pipe-tool-btn:hover { border-color: var(--accent); color: var(--accent); }',
    '.pipe-tool-btn:disabled { opacity: 0.4; cursor: not-allowed; }',
    '.pipe-tool-primary { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); font-weight: 600; }',
    '.pipe-tool-primary:hover { background: var(--accent); color: var(--bg-primary); }',
    '.pipe-toolbar-spacer { flex: 1; }',
    '.pipe-dirty-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--warning); margin-left: 4px; vertical-align: middle; }',

    /* SVG canvas */
    '.pipeline-dag-svg { flex: 1; width: 100%; min-height: 0; cursor: grab; }',
    '.pipeline-dag-svg.panning { cursor: grabbing; }',
    '.pipeline-dag-svg:focus { outline: 2px solid var(--accent); outline-offset: -2px; }',

    /* Empty state */
    '.pipeline-empty { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: var(--text-tertiary); font-size: var(--text-sm); text-align: center; pointer-events: none; max-width: 300px; line-height: 1.5; }',

    /* Minimap */
    '.pipeline-minimap { position: absolute; bottom: var(--sm); right: var(--sm); width: 160px; height: 100px; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; opacity: 0.85; pointer-events: none; z-index: 1; }',
    '.pipeline-minimap-svg { width: 100%; height: 100%; }',

    /* Macro group (SVG foreignObject-based styles) */
    '.macro-box { cursor: pointer; user-select: none; }',
    '.macro-box:hover .macro-border { stroke-opacity: 1; }',
    '.macro-box .macro-border { transition: stroke-opacity 0.15s; stroke-opacity: 0.8; }',
    '.macro-box.expanded .macro-border { stroke-width: 2.5; stroke-opacity: 1; }',
    '.macro-box.drag-over .macro-border { stroke-dasharray: 6 3; stroke-opacity: 1; }',
    '.macro-box.has-error .macro-border { stroke: var(--error) !important; }',

    /* Stage node (inside expanded macro) */
    '.stage-node-box { cursor: pointer; user-select: none; }',
    '.stage-node-box:hover .stage-border { stroke: var(--accent); }',
    '.stage-node-box.selected .stage-border { stroke: var(--accent); stroke-width: 2; }',
    '.stage-node-box.dragging { opacity: 0.5; }',

    /* Edge arrows */
    '.pipeline-edge { stroke: var(--border-active); stroke-width: 1.5; fill: none; marker-end: url(#pipe-arrowhead); }',
    '.pipeline-edge-internal { stroke: var(--text-tertiary); stroke-width: 1; fill: none; stroke-dasharray: 4 2; marker-end: url(#pipe-arrowhead-sm); }',

    /* Validation error tooltip */
    '.pipe-error-tooltip { position: absolute; background: var(--error); color: #fff; font-size: var(--text-2xs); padding: 3px 8px; border-radius: var(--radius-sm); pointer-events: none; white-space: nowrap; z-index: 10; }',

    /* Right config panel */
    '.pipelines-config-panel { background: var(--bg-secondary); border-left: 1px solid var(--border); overflow-y: auto; display: flex; flex-direction: column; }',
    '.config-panel-header { display: flex; align-items: center; justify-content: space-between; padding: var(--sm) var(--md); border-bottom: 1px solid var(--border); flex-shrink: 0; }',
    '.config-panel-close { background: none; border: none; font-size: 18px; color: var(--text-tertiary); cursor: pointer; padding: 2px 6px; line-height: 1; }',
    '.config-panel-close:hover { color: var(--text-primary); }',
    '.config-panel-body { padding: var(--md); flex: 1; display: flex; flex-direction: column; gap: var(--sm); }',
    '.config-field { display: flex; flex-direction: column; gap: 2px; }',
    '.config-field label { font-size: var(--text-2xs); font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }',
    '.config-field input, .config-field select, .config-field textarea { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px var(--sm); font-size: var(--text-sm); color: var(--text-primary); font-family: var(--font-sans); }',
    '.config-field textarea { resize: vertical; min-height: 56px; }',
    '.config-field input:focus, .config-field select:focus, .config-field textarea:focus { border-color: var(--accent); outline: none; box-shadow: 0 0 0 2px var(--accent-dim); }',
    '.config-kv-row { display: grid; grid-template-columns: 1fr 1fr 28px; gap: var(--xs); align-items: center; }',
    '.config-kv-row input { font-family: var(--font-mono); font-size: var(--text-xs); }',
    '.config-kv-remove { background: none; border: none; color: var(--error); font-size: 16px; cursor: pointer; padding: 0; line-height: 1; }',
    '.config-add-kv { background: none; border: 1px dashed var(--border); border-radius: var(--radius-sm); padding: 4px; font-size: var(--text-xs); color: var(--text-tertiary); cursor: pointer; width: 100%; text-align: center; }',
    '.config-add-kv:hover { border-color: var(--accent); color: var(--accent); }',
    '.config-btn-row { display: flex; gap: var(--sm); margin-top: var(--sm); }',
    '.config-btn-danger { background: var(--error-dim); color: var(--error); border: 1px solid transparent; border-radius: var(--radius-sm); padding: 6px 12px; font-size: var(--text-xs); font-weight: 500; cursor: pointer; }',
    '.config-btn-danger:hover { background: var(--error); color: #fff; }',
    '.config-btn-neutral { background: var(--bg-elevated); color: var(--text-secondary); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 12px; font-size: var(--text-xs); font-weight: 500; cursor: pointer; }',
    '.config-btn-neutral:hover { border-color: var(--accent); color: var(--accent); }',

    /* Wizard close button */
    '.wizard-close-btn { background: none; border: none; font-size: 18px; color: var(--text-tertiary); cursor: pointer; line-height: 1; }',
    '.wizard-close-btn:hover { color: var(--text-primary); }',

    /* Responsive: sidebar collapses on narrow screens */
    '@media (max-width: 1024px) {',
    '  .pipelines-view { grid-template-columns: 1fr !important; }',
    '  .pipelines-sidebar { position: absolute; left: 0; top: 0; bottom: 0; z-index: 20; width: 260px; transform: translateX(-100%); transition: transform var(--duration-normal) var(--ease); box-shadow: var(--shadow-lg); }',
    '  .pipelines-sidebar.open { transform: translateX(0); }',
    '  .pipelines-config-panel { position: absolute; right: 0; top: 0; bottom: 0; z-index: 20; width: 320px; box-shadow: var(--shadow-lg); }',
    '}'
  ].join('\n');
  document.head.appendChild(css);
}

/* =====================================================================
   Module State
   ===================================================================== */
var _currentPipeline = null;       /* Full pipeline definition being edited */
var _isDirty = false;              /* Unsaved changes flag */
var _expandedMacro = null;         /* macro_id of currently expanded macro, or null */
var _selectedStage = null;         /* {macroId, stageId} of selected stage */
var _svgTransform = { x: 0, y: 0, scale: 1 };  /* Zoom/pan state */
var _isPanning = false;
var _panStart = { x: 0, y: 0 };
var _dragStage = null;             /* Stage being dragged: {macroId, stageId, el} */
var _validationErrors = [];        /* Array of {macro_id, stage_id, message} */
var _templateCache = null;
var _savedCache = null;

/* Stage type colors for internal nodes */
var _stageTypeColors = {
  plan: '#6C5CE7', search: '#00B894', storm_interviews: '#A78BFA',
  analyze: '#F59E0B', verify: '#F472B6', evaluate: '#22D3EE',
  synthesize: '#38BDF8', search_gaps: '#FB923C', custom_llm: '#818CF8',
  filter: '#A3E635', merge: '#2DD4BF'
};

var _stageTypes = [
  'plan', 'search', 'storm_interviews', 'analyze', 'verify',
  'evaluate', 'synthesize', 'search_gaps', 'custom_llm', 'filter', 'merge'
];

/* =====================================================================
   API Helpers
   ===================================================================== */
function _pipeApi(method, path, body) {
  var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  return fetch('/api/pipelines' + (path || ''), opts).then(function(r) {
    if (!r.ok) return r.json().then(function(e) { throw new Error(e.detail || e.error || r.statusText); });
    if (r.status === 204) return {};
    return r.json();
  });
}

/* =====================================================================
   renderPipelinesView — Entry point called by view switcher
   ===================================================================== */
function renderPipelinesView() {
  _injectPipelineStyles();
  _fetchTemplates();
  _fetchSavedPipelines();
  if (_currentPipeline) {
    _renderDag();
  }
}

function _fetchTemplates() {
  _pipeApi('GET', '/templates').then(function(data) {
    _templateCache = data.templates || [];
    _renderTemplateList(_templateCache);
  }).catch(function(err) {
    if (typeof showToast === 'function') showToast('Failed to load templates: ' + err.message, 'error');
    _renderTemplateList([]);
  });
}

function _fetchSavedPipelines() {
  _pipeApi('GET', '').then(function(data) {
    _savedCache = data.pipelines || [];
    _renderSavedList(_savedCache);
  }).catch(function(err) {
    if (typeof showToast === 'function') showToast('Failed to load pipelines: ' + err.message, 'error');
    _renderSavedList([]);
  });
}

/* =====================================================================
   Template List (left sidebar)
   ===================================================================== */
function _renderTemplateList(templates) {
  var el = document.getElementById('pipeline-template-list');
  if (!el) return;
  if (!templates || !templates.length) {
    el.innerHTML = '<div style="font-size:var(--text-xs);color:var(--text-tertiary);padding:var(--sm)">No templates available.</div>';
    return;
  }
  el.innerHTML = templates.map(function(tpl, idx) {
    var stageCount = _countStages(tpl);
    var macroCount = (tpl.macro_stages || []).length;
    return '<div class="pipeline-template-card" data-tpl-idx="' + idx + '">' +
      '<div class="pipeline-template-card-name">' + esc(tpl.name) + '</div>' +
      '<div class="pipeline-template-card-desc">' + esc(tpl.description || '') + '</div>' +
      '<div class="pipeline-template-card-meta">' +
        '<span class="pipeline-template-card-badge">' + stageCount + ' stages</span>' +
        '<span>' + macroCount + ' phases</span>' +
        (tpl.version ? '<span>v' + esc(tpl.version) + '</span>' : '') +
      '</div>' +
      '<div class="pipeline-template-card-actions">' +
        '<button class="pipe-use-btn" onclick="_useTemplate(' + idx + ')">Use Template</button>' +
      '</div>' +
    '</div>';
  }).join('');
}

function _countStages(pipeline) {
  var count = 0;
  (pipeline.macro_stages || []).forEach(function(m) { count += (m.stages || []).length; });
  return count;
}

function _useTemplate(idx) {
  if (!_templateCache || !_templateCache[idx]) return;
  var meta = _templateCache[idx];

  /* Fetch full pipeline definition (includes macro_stages) from server */
  fetch('/api/pipelines/' + encodeURIComponent(meta.pipeline_id))
    .then(function(r) { return r.json(); })
    .then(function(full) {
      var tpl = JSON.parse(JSON.stringify(full));
      tpl.pipeline_id = 'pipe_' + Date.now().toString(36);
      tpl.is_template = false;
      tpl.name = (tpl.name || meta.name) + ' (Copy)';
      loadPipelineIntoEditor(tpl);
      if (typeof showToast === 'function') showToast('Loaded template: ' + tpl.name, 'info');
    })
    .catch(function(err) {
      /* Fallback: use cached summary (no macro_stages — DAG will be empty) */
      var tpl = JSON.parse(JSON.stringify(meta));
      tpl.pipeline_id = 'pipe_' + Date.now().toString(36);
      tpl.is_template = false;
      tpl.name = tpl.name + ' (Copy)';
      loadPipelineIntoEditor(tpl);
      if (typeof showToast === 'function') showToast('Loaded template (offline): ' + tpl.name, 'warning');
    });
}

/* =====================================================================
   Saved Pipelines List (left sidebar)
   ===================================================================== */
function _renderSavedList(pipelines) {
  var el = document.getElementById('pipeline-saved-list');
  if (!el) return;
  var custom = (pipelines || []).filter(function(p) { return !p.is_template; });
  if (!custom.length) {
    el.innerHTML = '<div style="font-size:var(--text-xs);color:var(--text-tertiary);padding:var(--sm)">No saved pipelines yet.</div>';
    return;
  }
  el.innerHTML = custom.map(function(p, idx) {
    return '<div class="pipeline-saved-card">' +
      '<span class="pipeline-saved-card-name" title="' + esc(p.name) + '">' + esc(p.name) + '</span>' +
      '<div class="pipeline-saved-card-actions">' +
        '<button class="pipe-edit-btn" onclick="_editSavedPipeline(\'' + esc(p.pipeline_id) + '\')">Edit</button>' +
        '<button class="pipe-delete-btn" onclick="_deleteSavedPipeline(\'' + esc(p.pipeline_id) + '\')">Del</button>' +
      '</div>' +
    '</div>';
  }).join('');
}

function _editSavedPipeline(pipelineId) {
  _pipeApi('GET', '/' + pipelineId).then(function(data) {
    loadPipelineIntoEditor(data.pipeline || data);
    if (typeof showToast === 'function') showToast('Loaded pipeline for editing.', 'info');
  }).catch(function(err) {
    if (typeof showToast === 'function') showToast('Failed to load pipeline: ' + err.message, 'error');
  });
}

function _deleteSavedPipeline(pipelineId) {
  if (!confirm('Delete this pipeline? This cannot be undone.')) return;
  _pipeApi('DELETE', '/' + pipelineId).then(function() {
    if (typeof showToast === 'function') showToast('Pipeline deleted.', 'success');
    if (_currentPipeline && _currentPipeline.pipeline_id === pipelineId) {
      _currentPipeline = null;
      _isDirty = false;
      _expandedMacro = null;
      _selectedStage = null;
      _renderDag();
      closeConfigPanel();
    }
    _fetchSavedPipelines();
  }).catch(function(err) {
    if (typeof showToast === 'function') showToast('Delete failed: ' + err.message, 'error');
  });
}

/* =====================================================================
   loadPipelineIntoEditor — Public: load a pipeline def into the editor
   ===================================================================== */
function loadPipelineIntoEditor(pipelineDef) {
  _currentPipeline = JSON.parse(JSON.stringify(pipelineDef));
  _isDirty = true;
  _expandedMacro = null;
  _selectedStage = null;
  _validationErrors = [];
  _svgTransform = { x: 0, y: 0, scale: 1 };
  closeConfigPanel();
  _renderDag();
  _updateDirtyIndicator();
}

/* =====================================================================
   DAG Rendering
   ===================================================================== */
var _MACRO_W = 280;
var _MACRO_H = 80;
var _MACRO_GAP_X = 60;
var _MACRO_GAP_Y = 40;
var _STAGE_W = 200;
var _STAGE_H = 50;
var _STAGE_GAP = 16;
var _STAGE_PAD_TOP = 44;
var _STAGE_PAD_X = 20;
var _STAGE_PAD_BOTTOM = 16;

function _renderDag() {
  var svg = document.getElementById('pipeline-dag-svg');
  var emptyEl = document.getElementById('pipeline-empty');
  if (!svg) return;

  if (!_currentPipeline || !_currentPipeline.macro_stages || !_currentPipeline.macro_stages.length) {
    svg.innerHTML = '';
    if (emptyEl) emptyEl.style.display = 'block';
    _renderMinimap();
    return;
  }
  if (emptyEl) emptyEl.style.display = 'none';

  var macros = _currentPipeline.macro_stages;
  var positions = _layoutMacros(macros);
  var svgContent = '';

  /* Defs: arrowhead markers */
  svgContent += '<defs>';
  svgContent += '<marker id="pipe-arrowhead" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="8" markerHeight="6" orient="auto-start-reverse">';
  svgContent += '<polygon points="0 0, 10 3.5, 0 7" fill="var(--border-active)" />';
  svgContent += '</marker>';
  svgContent += '<marker id="pipe-arrowhead-sm" viewBox="0 0 10 7" refX="10" refY="3.5" markerWidth="6" markerHeight="5" orient="auto-start-reverse">';
  svgContent += '<polygon points="0 0, 10 3.5, 0 7" fill="var(--text-tertiary)" />';
  svgContent += '</marker>';
  svgContent += '</defs>';

  /* Transform group for zoom/pan */
  svgContent += '<g id="pipe-dag-root" transform="translate(' + _svgTransform.x + ',' + _svgTransform.y + ') scale(' + _svgTransform.scale + ')">';

  /* Render macro-to-macro edges first (behind nodes) */
  macros.forEach(function(macro) {
    var deps = macro.depends_on_macros || [];
    var toPos = positions[macro.macro_id];
    if (!toPos) return;
    deps.forEach(function(depId) {
      var fromPos = positions[depId];
      if (!fromPos) return;
      var x1 = fromPos.x + fromPos.w;
      var y1 = fromPos.y + fromPos.h / 2;
      var x2 = toPos.x;
      var y2 = toPos.y + toPos.h / 2;
      var mx = (x1 + x2) / 2;
      svgContent += '<path class="pipeline-edge" d="M' + x1 + ',' + y1 + ' C' + mx + ',' + y1 + ' ' + mx + ',' + y2 + ' ' + x2 + ',' + y2 + '" />';
    });
  });

  /* Render each macro */
  macros.forEach(function(macro) {
    var pos = positions[macro.macro_id];
    if (!pos) return;
    var isExpanded = _expandedMacro === macro.macro_id;
    var hasError = _validationErrors.some(function(e) { return e.macro_id === macro.macro_id; });
    var cls = 'macro-box' + (isExpanded ? ' expanded' : '') + (hasError ? ' has-error' : '');

    svgContent += '<g class="' + cls + '" data-macro="' + esc(macro.macro_id) + '" transform="translate(' + pos.x + ',' + pos.y + ')">';

    /* Background rect */
    var color = macro.color || '#6C5CE7';
    svgContent += '<rect class="macro-border" x="0" y="0" width="' + pos.w + '" height="' + pos.h + '" rx="12" ry="12" fill="var(--bg-card)" stroke="' + color + '" stroke-width="2" />';

    /* Color accent strip */
    svgContent += '<rect x="0" y="8" width="4" height="' + (pos.h - 16) + '" rx="2" fill="' + color + '" />';

    /* Header area (always visible) — uses SVG text */
    svgContent += '<text x="16" y="26" font-size="14" font-weight="600" fill="var(--text-primary)" font-family="var(--font-sans)" style="cursor:pointer" data-macro-header="' + esc(macro.macro_id) + '">' + esc(truncStr(macro.label || macro.macro_id, 28)) + '</text>';

    /* Stage count badge */
    var stageCount = (macro.stages || []).length;
    svgContent += '<rect x="16" y="34" width="' + (stageCount > 9 ? 60 : 52) + '" height="16" rx="8" fill="' + color + '" opacity="0.15" />';
    svgContent += '<text x="' + (16 + (stageCount > 9 ? 30 : 26)) + '" y="45" font-size="10" fill="' + color + '" text-anchor="middle" font-family="var(--font-sans)" font-weight="600">' + stageCount + ' stage' + (stageCount !== 1 ? 's' : '') + '</text>';

    /* Estimated duration */
    var dur = macro.estimated_minutes;
    if (dur !== undefined && dur !== null) {
      svgContent += '<text x="' + (pos.w - 12) + '" y="45" font-size="10" fill="var(--text-tertiary)" text-anchor="end" font-family="var(--font-sans)">~' + dur + ' min</text>';
    }

    /* Description (collapsed only, 1 line truncated) */
    if (!isExpanded && macro.description) {
      svgContent += '<text x="16" y="66" font-size="11" fill="var(--text-tertiary)" font-family="var(--font-sans)">' + esc(truncStr(macro.description, 38)) + '</text>';
    }

    /* Expand indicator */
    var chevron = isExpanded ? '\u25B2' : '\u25BC';
    svgContent += '<text x="' + (pos.w - 14) + '" y="26" font-size="10" fill="var(--text-tertiary)" text-anchor="end" style="cursor:pointer" data-macro-header="' + esc(macro.macro_id) + '">' + chevron + '</text>';

    /* If expanded, render internal stages */
    if (isExpanded) {
      svgContent += _renderInternalStages(macro, pos);
    }

    svgContent += '</g>';
  });

  svgContent += '</g>';
  svg.innerHTML = svgContent;

  /* Attach event listeners */
  _attachDagEvents(svg);
  _renderMinimap();
  _updateDirtyIndicator();
}

/* =====================================================================
   Layout: position macros in a horizontal flow with wrapping
   ===================================================================== */
function _layoutMacros(macros) {
  var positions = {};
  var svg = document.getElementById('pipeline-dag-svg');
  var canvasW = (svg ? svg.clientWidth : 900) / _svgTransform.scale;
  var maxRowW = Math.max(canvasW - 80, 800);

  var x = 40, y = 40;
  var rowH = 0;

  /* Build dependency map for topological ordering */
  var placed = {};
  var queue = macros.slice();

  /* Simple left-to-right layout respecting dependencies */
  var depColumns = {};
  macros.forEach(function(m) {
    var deps = m.depends_on_macros || [];
    var col = 0;
    deps.forEach(function(d) { if (depColumns[d] !== undefined) col = Math.max(col, depColumns[d] + 1); });
    depColumns[m.macro_id] = col;
  });

  /* Group by column */
  var columns = {};
  macros.forEach(function(m) {
    var c = depColumns[m.macro_id] || 0;
    if (!columns[c]) columns[c] = [];
    columns[c].push(m);
  });

  var colKeys = Object.keys(columns).sort(function(a, b) { return Number(a) - Number(b); });
  var cx = 40;

  colKeys.forEach(function(colKey) {
    var colMacros = columns[colKey];
    var cy = 40;
    var maxW = 0;

    colMacros.forEach(function(macro) {
      var isExpanded = _expandedMacro === macro.macro_id;
      var w = _MACRO_W;
      var h = _MACRO_H;

      if (isExpanded) {
        var stages = macro.stages || [];
        /* Calculate expanded height: header + stages stacked */
        var rows = _layoutInternalStages(stages);
        h = _STAGE_PAD_TOP + rows.totalH + _STAGE_PAD_BOTTOM;
        h = Math.max(h, _MACRO_H);
        w = Math.max(_MACRO_W, _STAGE_PAD_X * 2 + rows.maxW);
      }

      positions[macro.macro_id] = { x: cx, y: cy, w: w, h: h };
      cy += h + _MACRO_GAP_Y;
      maxW = Math.max(maxW, w);
    });

    cx += maxW + _MACRO_GAP_X;
  });

  return positions;
}

/* =====================================================================
   Internal Stage Layout (within an expanded macro)
   ===================================================================== */
function _layoutInternalStages(stages) {
  if (!stages || !stages.length) return { positions: {}, totalH: 0, maxW: _STAGE_W };

  /* Build dep columns for internal stages */
  var depCol = {};
  stages.forEach(function(s) {
    var deps = s.depends_on || [];
    var col = 0;
    deps.forEach(function(d) { if (depCol[d] !== undefined) col = Math.max(col, depCol[d] + 1); });
    depCol[s.stage_id] = col;
  });

  /* Group by column */
  var cols = {};
  stages.forEach(function(s) {
    var c = depCol[s.stage_id] || 0;
    if (!cols[c]) cols[c] = [];
    cols[c].push(s);
  });

  var colKeys = Object.keys(cols).sort(function(a, b) { return Number(a) - Number(b); });
  var positions = {};
  var sx = _STAGE_PAD_X;
  var maxTotalH = 0;

  colKeys.forEach(function(ck) {
    var colStages = cols[ck];
    var sy = _STAGE_PAD_TOP;
    colStages.forEach(function(stage) {
      positions[stage.stage_id] = { x: sx, y: sy, w: _STAGE_W, h: _STAGE_H };
      sy += _STAGE_H + _STAGE_GAP;
    });
    maxTotalH = Math.max(maxTotalH, sy - _STAGE_PAD_TOP);
    sx += _STAGE_W + _STAGE_GAP;
  });

  return { positions: positions, totalH: maxTotalH, maxW: sx - _STAGE_GAP + _STAGE_PAD_X };
}

/* =====================================================================
   Render internal stages (SVG fragment inside a macro group)
   ===================================================================== */
function _renderInternalStages(macro, macroPos) {
  var stages = macro.stages || [];
  if (!stages.length) return '';

  var layout = _layoutInternalStages(stages);
  var pos = layout.positions;
  var svgFrag = '';

  /* Render internal edges */
  stages.forEach(function(stage) {
    var deps = stage.depends_on || [];
    var toP = pos[stage.stage_id];
    if (!toP) return;
    deps.forEach(function(depId) {
      var fromP = pos[depId];
      if (!fromP) return;
      var x1 = fromP.x + fromP.w;
      var y1 = fromP.y + fromP.h / 2;
      var x2 = toP.x;
      var y2 = toP.y + toP.h / 2;
      svgFrag += '<line class="pipeline-edge-internal" x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" />';
    });
  });

  /* Render stage nodes */
  stages.forEach(function(stage) {
    var sp = pos[stage.stage_id];
    if (!sp) return;
    var color = _stageTypeColors[stage.stage_type] || '#94A3B8';
    var isSelected = _selectedStage && _selectedStage.stageId === stage.stage_id && _selectedStage.macroId === macro.macro_id;
    var hasError = _validationErrors.some(function(e) { return e.stage_id === stage.stage_id; });
    var cls = 'stage-node-box' + (isSelected ? ' selected' : '');

    svgFrag += '<g class="' + cls + '" data-stage="' + esc(stage.stage_id) + '" data-macro="' + esc(macro.macro_id) + '" draggable="true" transform="translate(' + sp.x + ',' + sp.y + ')">';

    /* Stage rect */
    var strokeColor = hasError ? 'var(--error)' : color;
    svgFrag += '<rect class="stage-border" x="0" y="0" width="' + sp.w + '" height="' + sp.h + '" rx="8" ry="8" fill="var(--bg-elevated)" stroke="' + strokeColor + '" stroke-width="' + (isSelected ? 2 : 1.5) + '" />';

    /* Color dot */
    svgFrag += '<circle cx="14" cy="' + (sp.h / 2) + '" r="5" fill="' + color + '" />';

    /* Label */
    svgFrag += '<text x="28" y="' + (sp.h / 2 - 4) + '" font-size="12" font-weight="500" fill="var(--text-primary)" font-family="var(--font-sans)">' + esc(truncStr(stage.label || stage.stage_id, 22)) + '</text>';

    /* Type tag */
    svgFrag += '<text x="28" y="' + (sp.h / 2 + 12) + '" font-size="10" fill="var(--text-tertiary)" font-family="var(--font-mono)">' + esc(stage.stage_type || '?') + '</text>';

    svgFrag += '</g>';
  });

  return svgFrag;
}

/* =====================================================================
   Event Handling (DAG interactions)
   ===================================================================== */
function _attachDagEvents(svg) {
  /* Click handler — delegate from SVG root */
  svg.onclick = function(e) {
    var target = e.target;

    /* Click on macro header text or chevron → toggle expand */
    var headerAttr = _findAttr(target, 'data-macro-header', 4);
    if (headerAttr) {
      _toggleMacro(headerAttr);
      return;
    }

    /* Click on stage node → select and open config */
    var stageG = _findParentWithAttr(target, 'data-stage', 5);
    if (stageG) {
      var stageId = stageG.getAttribute('data-stage');
      var macroId = stageG.getAttribute('data-macro');
      _selectStage(macroId, stageId);
      return;
    }

    /* Click on macro body (not header, not stage) → expand/collapse */
    var macroG = _findParentWithClass(target, 'macro-box', 5);
    if (macroG) {
      var mId = macroG.getAttribute('data-macro');
      /* Only toggle if click was on the collapsed body, not internal content */
      if (!_expandedMacro || _expandedMacro !== mId) {
        _toggleMacro(mId);
        return;
      }
    }

    /* Click on background → deselect */
    if (target === svg || target.id === 'pipe-dag-root') {
      if (_expandedMacro) {
        _expandedMacro = null;
        _selectedStage = null;
        closeConfigPanel();
        _renderDag();
      }
    }
  };

  /* Mouse wheel → zoom */
  svg.onwheel = function(e) {
    e.preventDefault();
    var delta = e.deltaY > 0 ? -0.08 : 0.08;
    var newScale = Math.max(0.25, Math.min(3, _svgTransform.scale + delta));
    /* Zoom toward mouse position */
    var rect = svg.getBoundingClientRect();
    var mx = e.clientX - rect.left;
    var my = e.clientY - rect.top;
    var ratio = newScale / _svgTransform.scale;
    _svgTransform.x = mx - ratio * (mx - _svgTransform.x);
    _svgTransform.y = my - ratio * (my - _svgTransform.y);
    _svgTransform.scale = newScale;
    _applyTransform();
    _renderMinimap();
  };

  /* Pan: mousedown/mousemove/mouseup */
  svg.onmousedown = function(e) {
    /* Only pan on background or the root group */
    if (e.target !== svg && e.target.id !== 'pipe-dag-root' && !e.target.classList.contains('macro-border')) {
      /* Check for stage drag start */
      var stageG = _findParentWithAttr(e.target, 'data-stage', 5);
      if (stageG && _expandedMacro) {
        _startStageDrag(e, stageG);
        return;
      }
      return;
    }
    if (e.button !== 0) return;
    _isPanning = true;
    _panStart = { x: e.clientX - _svgTransform.x, y: e.clientY - _svgTransform.y };
    svg.classList.add('panning');
    e.preventDefault();
  };

  svg.onmousemove = function(e) {
    if (_dragStage) {
      _onStageDragMove(e);
      return;
    }
    if (!_isPanning) return;
    _svgTransform.x = e.clientX - _panStart.x;
    _svgTransform.y = e.clientY - _panStart.y;
    _applyTransform();
    _renderMinimap();
  };

  svg.onmouseup = function(e) {
    if (_dragStage) {
      _onStageDragEnd(e);
      return;
    }
    _isPanning = false;
    svg.classList.remove('panning');
  };

  svg.onmouseleave = function() {
    _isPanning = false;
    svg.classList.remove('panning');
    if (_dragStage) _cancelStageDrag();
  };
}

function _applyTransform() {
  var g = document.getElementById('pipe-dag-root');
  if (g) g.setAttribute('transform', 'translate(' + _svgTransform.x + ',' + _svgTransform.y + ') scale(' + _svgTransform.scale + ')');
}

/* =====================================================================
   DOM traversal helpers
   ===================================================================== */
function _findAttr(el, attr, depth) {
  for (var i = 0; i < depth && el; i++) {
    if (el.getAttribute && el.getAttribute(attr)) return el.getAttribute(attr);
    el = el.parentNode;
  }
  return null;
}

function _findParentWithAttr(el, attr, depth) {
  for (var i = 0; i < depth && el; i++) {
    if (el.getAttribute && el.getAttribute(attr)) return el;
    el = el.parentNode;
  }
  return null;
}

function _findParentWithClass(el, cls, depth) {
  for (var i = 0; i < depth && el; i++) {
    if (el.classList && el.classList.contains(cls)) return el;
    el = el.parentNode;
  }
  return null;
}

/* =====================================================================
   Macro Expand/Collapse
   ===================================================================== */
function _toggleMacro(macroId) {
  if (_expandedMacro === macroId) {
    _expandedMacro = null;
    _selectedStage = null;
    closeConfigPanel();
  } else {
    _expandedMacro = macroId;
    _selectedStage = null;
    closeConfigPanel();
  }
  _renderDag();
}

/* =====================================================================
   Stage Selection and Config Panel
   ===================================================================== */
function _selectStage(macroId, stageId) {
  _selectedStage = { macroId: macroId, stageId: stageId };
  _renderDag();
  _openConfigPanel(macroId, stageId);
}

function _openConfigPanel(macroId, stageId) {
  var panel = document.getElementById('pipelines-config-panel');
  var body = document.getElementById('config-panel-body');
  var title = document.getElementById('config-panel-title');
  var view = document.querySelector('.pipelines-view');
  if (!panel || !body || !_currentPipeline) return;
  /* G11: Clear empty state placeholder */
  var emptyState = document.getElementById('config-empty-state');
  if (emptyState) emptyState.style.display = 'none';

  var macro = _findMacro(macroId);
  var stage = macro ? _findStageInMacro(macro, stageId) : null;
  if (!stage) return;

  if (title) title.textContent = 'Stage: ' + (stage.label || stage.stage_id);

  var html = '';

  /* Stage ID (read-only) */
  html += '<div class="config-field">';
  html += '<label>Stage ID</label>';
  html += '<input type="text" value="' + esc(stage.stage_id) + '" readonly style="opacity:0.6;cursor:not-allowed" />';
  html += '</div>';

  /* Stage Type */
  html += '<div class="config-field">';
  html += '<label>Stage Type</label>';
  html += '<select id="cfg-stage-type" onchange="_updateStageField(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\',\'stage_type\',this.value)">';
  _stageTypes.forEach(function(t) {
    html += '<option value="' + t + '"' + (stage.stage_type === t ? ' selected' : '') + '>' + t + '</option>';
  });
  html += '</select>';
  html += '</div>';

  /* Label */
  html += '<div class="config-field">';
  html += '<label>Label</label>';
  html += '<input type="text" id="cfg-stage-label" value="' + esc(stage.label || '') + '" onchange="_updateStageField(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\',\'label\',this.value)" />';
  html += '</div>';

  /* Description */
  html += '<div class="config-field">';
  html += '<label>Description</label>';
  html += '<textarea id="cfg-stage-desc" onchange="_updateStageField(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\',\'description\',this.value)">' + esc(stage.description || '') + '</textarea>';
  html += '</div>';

  /* Dependencies */
  html += '<div class="config-field">';
  html += '<label>Depends On (comma-separated stage IDs)</label>';
  html += '<input type="text" id="cfg-stage-deps" value="' + esc((stage.depends_on || []).join(', ')) + '" onchange="_updateStageDeps(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\',this.value)" />';
  html += '</div>';

  /* Config key-value pairs */
  html += '<div class="config-field">';
  html += '<label>Configuration</label>';
  html += '<div id="cfg-kv-container">';
  var configEntries = Object.entries(stage.config || {});
  configEntries.forEach(function(entry, idx) {
    html += _renderKvRow(macroId, stageId, entry[0], entry[1], idx);
  });
  html += '</div>';
  html += '<button class="config-add-kv" onclick="_addConfigKey(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\')">+ Add Key</button>';
  html += '</div>';

  /* Validation errors for this stage */
  var stageErrors = _validationErrors.filter(function(e) { return e.stage_id === stageId; });
  if (stageErrors.length) {
    html += '<div style="margin-top:var(--sm)">';
    stageErrors.forEach(function(err) {
      html += '<div style="font-size:var(--text-xs);color:var(--error);padding:2px 0">' + esc(err.message) + '</div>';
    });
    html += '</div>';
  }

  /* Action buttons */
  html += '<div class="config-btn-row">';
  html += '<button class="config-btn-neutral" onclick="_duplicateStage(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\')">Duplicate</button>';
  html += '<button class="config-btn-danger" onclick="_removeStage(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\')">Remove Stage</button>';
  html += '</div>';

  body.innerHTML = html;
  panel.style.display = '';
  if (view) view.classList.add('config-open');
}

function _renderKvRow(macroId, stageId, key, value, idx) {
  return '<div class="config-kv-row" data-kv-idx="' + idx + '">' +
    '<input type="text" value="' + esc(key) + '" placeholder="key" onchange="_updateConfigKey(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\',' + idx + ',this.value,null)" />' +
    '<input type="text" value="' + esc(String(value)) + '" placeholder="value" onchange="_updateConfigKey(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\',' + idx + ',null,this.value)" />' +
    '<button class="config-kv-remove" onclick="_removeConfigKey(\'' + esc(macroId) + '\',\'' + esc(stageId) + '\',' + idx + ')" title="Remove">&times;</button>' +
  '</div>';
}

function closeConfigPanel() {
  var panel = document.getElementById('pipelines-config-panel');
  var view = document.querySelector('.pipelines-view');
  if (panel) panel.style.display = 'none';
  if (view) view.classList.remove('config-open');
  /* G11: Restore empty state placeholder */
  var body = document.getElementById('config-panel-body');
  var emptyState = document.getElementById('config-empty-state');
  if (body && emptyState) emptyState.style.display = '';
}

/* =====================================================================
   Stage Field Updates
   ===================================================================== */
function _updateStageField(macroId, stageId, field, value) {
  var macro = _findMacro(macroId);
  var stage = macro ? _findStageInMacro(macro, stageId) : null;
  if (!stage) return;
  stage[field] = value;
  _markDirty();
  _renderDag();
  /* Re-open panel if selected */
  if (_selectedStage && _selectedStage.stageId === stageId) {
    _openConfigPanel(macroId, stageId);
  }
}

function _updateStageDeps(macroId, stageId, value) {
  var macro = _findMacro(macroId);
  var stage = macro ? _findStageInMacro(macro, stageId) : null;
  if (!stage) return;
  stage.depends_on = value.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
  _markDirty();
  _renderDag();
}

function _updateConfigKey(macroId, stageId, idx, newKey, newVal) {
  var macro = _findMacro(macroId);
  var stage = macro ? _findStageInMacro(macro, stageId) : null;
  if (!stage || !stage.config) return;
  var entries = Object.entries(stage.config);
  if (idx >= entries.length) return;
  if (newKey !== null) {
    var oldKey = entries[idx][0];
    var val = stage.config[oldKey];
    delete stage.config[oldKey];
    stage.config[newKey] = val;
  }
  if (newVal !== null) {
    var key = Object.keys(stage.config)[idx];
    if (key !== undefined) stage.config[key] = newVal;
  }
  _markDirty();
}

function _addConfigKey(macroId, stageId) {
  var macro = _findMacro(macroId);
  var stage = macro ? _findStageInMacro(macro, stageId) : null;
  if (!stage) return;
  if (!stage.config) stage.config = {};
  var keyName = 'NEW_KEY_' + Object.keys(stage.config).length;
  stage.config[keyName] = '';
  _markDirty();
  _openConfigPanel(macroId, stageId);
}

function _removeConfigKey(macroId, stageId, idx) {
  var macro = _findMacro(macroId);
  var stage = macro ? _findStageInMacro(macro, stageId) : null;
  if (!stage || !stage.config) return;
  var key = Object.keys(stage.config)[idx];
  if (key !== undefined) delete stage.config[key];
  _markDirty();
  _openConfigPanel(macroId, stageId);
}

function _duplicateStage(macroId, stageId) {
  var macro = _findMacro(macroId);
  var stage = macro ? _findStageInMacro(macro, stageId) : null;
  if (!macro || !stage) return;
  var clone = JSON.parse(JSON.stringify(stage));
  clone.stage_id = stage.stage_id + '_copy_' + Date.now().toString(36);
  clone.label = (clone.label || clone.stage_id) + ' (Copy)';
  macro.stages.push(clone);
  _markDirty();
  _renderDag();
  _selectStage(macroId, clone.stage_id);
  if (typeof showToast === 'function') showToast('Stage duplicated.', 'info');
}

function _removeStage(macroId, stageId) {
  if (!confirm('Remove this stage? This cannot be undone.')) return;
  var macro = _findMacro(macroId);
  if (!macro) return;
  macro.stages = (macro.stages || []).filter(function(s) { return s.stage_id !== stageId; });
  /* Clean up depends_on references in remaining stages */
  (macro.stages || []).forEach(function(s) {
    s.depends_on = (s.depends_on || []).filter(function(d) { return d !== stageId; });
  });
  _selectedStage = null;
  closeConfigPanel();
  _markDirty();
  _renderDag();
  if (typeof showToast === 'function') showToast('Stage removed.', 'info');
}

/* =====================================================================
   Pipeline Lookup Helpers
   ===================================================================== */
function _findMacro(macroId) {
  if (!_currentPipeline || !_currentPipeline.macro_stages) return null;
  return _currentPipeline.macro_stages.find(function(m) { return m.macro_id === macroId; }) || null;
}

function _findStageInMacro(macro, stageId) {
  return (macro.stages || []).find(function(s) { return s.stage_id === stageId; }) || null;
}

/* =====================================================================
   Dirty State
   ===================================================================== */
function _markDirty() {
  _isDirty = true;
  _updateDirtyIndicator();
}

function _updateDirtyIndicator() {
  var saveBtn = document.getElementById('pipe-btn-save');
  if (!saveBtn) return;
  var existing = saveBtn.querySelector('.pipe-dirty-dot');
  if (_isDirty && _currentPipeline) {
    if (!existing) {
      var dot = document.createElement('span');
      dot.className = 'pipe-dirty-dot';
      saveBtn.appendChild(dot);
    }
    saveBtn.disabled = false;
  } else {
    if (existing) existing.remove();
  }
  /* Disable toolbar buttons when no pipeline is loaded */
  var btns = ['pipe-btn-save', 'pipe-btn-validate', 'pipe-btn-run'];
  btns.forEach(function(id) {
    var btn = document.getElementById(id);
    if (btn) btn.disabled = !_currentPipeline;
  });
}

/* =====================================================================
   Minimap
   ===================================================================== */
function _renderMinimap() {
  var minimapSvg = document.getElementById('pipeline-minimap-svg');
  if (!minimapSvg || !_currentPipeline || !_currentPipeline.macro_stages) {
    if (minimapSvg) minimapSvg.innerHTML = '';
    return;
  }

  var macros = _currentPipeline.macro_stages;
  var positions = _layoutMacros(macros);
  var keys = Object.keys(positions);
  if (!keys.length) { minimapSvg.innerHTML = ''; return; }

  /* Compute bounding box */
  var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  keys.forEach(function(k) {
    var p = positions[k];
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x + p.w);
    maxY = Math.max(maxY, p.y + p.h);
  });

  var bw = maxX - minX + 40;
  var bh = maxY - minY + 40;
  minimapSvg.setAttribute('viewBox', (minX - 20) + ' ' + (minY - 20) + ' ' + bw + ' ' + bh);

  var html = '';

  /* Edges */
  macros.forEach(function(macro) {
    var deps = macro.depends_on_macros || [];
    var toP = positions[macro.macro_id];
    if (!toP) return;
    deps.forEach(function(d) {
      var fromP = positions[d];
      if (!fromP) return;
      html += '<line x1="' + (fromP.x + fromP.w) + '" y1="' + (fromP.y + fromP.h / 2) + '" x2="' + toP.x + '" y2="' + (toP.y + toP.h / 2) + '" stroke="var(--text-tertiary)" stroke-width="1" opacity="0.5" />';
    });
  });

  /* Macro boxes */
  macros.forEach(function(macro) {
    var p = positions[macro.macro_id];
    if (!p) return;
    var color = macro.color || '#6C5CE7';
    html += '<rect x="' + p.x + '" y="' + p.y + '" width="' + p.w + '" height="' + p.h + '" rx="4" fill="var(--bg-card)" stroke="' + color + '" stroke-width="1.5" opacity="0.7" />';
  });

  /* Viewport indicator */
  var svg = document.getElementById('pipeline-dag-svg');
  if (svg) {
    var vw = svg.clientWidth / _svgTransform.scale;
    var vh = svg.clientHeight / _svgTransform.scale;
    var vx = -_svgTransform.x / _svgTransform.scale;
    var vy = -_svgTransform.y / _svgTransform.scale;
    html += '<rect x="' + vx + '" y="' + vy + '" width="' + vw + '" height="' + vh + '" fill="var(--accent)" opacity="0.08" stroke="var(--accent)" stroke-width="1" rx="2" />';
  }

  minimapSvg.innerHTML = html;
}

/* =====================================================================
   Zoom Controls (global functions)
   ===================================================================== */
function pipelineZoomIn() {
  _svgTransform.scale = Math.min(3, _svgTransform.scale + 0.15);
  _applyTransform();
  _renderMinimap();
}

function pipelineZoomOut() {
  _svgTransform.scale = Math.max(0.25, _svgTransform.scale - 0.15);
  _applyTransform();
  _renderMinimap();
}

function pipelineFitView() {
  if (!_currentPipeline || !_currentPipeline.macro_stages || !_currentPipeline.macro_stages.length) return;
  var svg = document.getElementById('pipeline-dag-svg');
  if (!svg) return;

  var positions = _layoutMacros(_currentPipeline.macro_stages);
  var keys = Object.keys(positions);
  if (!keys.length) return;

  var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  keys.forEach(function(k) {
    var p = positions[k];
    minX = Math.min(minX, p.x);
    minY = Math.min(minY, p.y);
    maxX = Math.max(maxX, p.x + p.w);
    maxY = Math.max(maxY, p.y + p.h);
  });

  var bw = maxX - minX + 80;
  var bh = maxY - minY + 80;
  var sw = svg.clientWidth;
  var sh = svg.clientHeight;
  if (!sw || !sh) return;

  var scale = Math.min(sw / bw, sh / bh, 2);
  scale = Math.max(0.25, Math.min(2, scale));
  var cx = (minX + maxX) / 2;
  var cy = (minY + maxY) / 2;
  _svgTransform.scale = scale;
  _svgTransform.x = sw / 2 - cx * scale;
  _svgTransform.y = sh / 2 - cy * scale;
  _applyTransform();
  _renderMinimap();
}

/* =====================================================================
   Toolbar Actions (global functions)
   ===================================================================== */
function savePipeline() {
  if (!_currentPipeline) {
    if (typeof showToast === 'function') showToast('No pipeline loaded.', 'warning');
    return;
  }
  var def = JSON.parse(JSON.stringify(_currentPipeline));
  var id = def.pipeline_id;

  /* Determine if this is an update (existing saved pipeline) or a new save */
  var isExisting = (_savedCache || []).some(function(p) { return p.pipeline_id === id; });
  var method = isExisting ? 'PUT' : 'POST';
  var path = isExisting ? '/' + id : '';
  var body = { pipeline_definition: def };

  _pipeApi(method, path, body).then(function(data) {
    _isDirty = false;
    /* Update pipeline_id if server assigned one */
    if (data.pipeline_id) _currentPipeline.pipeline_id = data.pipeline_id;
    if (data.pipeline && data.pipeline.pipeline_id) _currentPipeline.pipeline_id = data.pipeline.pipeline_id;
    _updateDirtyIndicator();
    _fetchSavedPipelines();
    if (typeof showToast === 'function') showToast('Pipeline saved successfully.', 'success');
  }).catch(function(err) {
    if (typeof showToast === 'function') showToast('Save failed: ' + err.message, 'error');
  });
}

function validatePipeline() {
  if (!_currentPipeline) {
    if (typeof showToast === 'function') showToast('No pipeline loaded.', 'warning');
    return;
  }
  var id = _currentPipeline.pipeline_id;
  _pipeApi('POST', '/' + id + '/validate').then(function(data) {
    _validationErrors = [];
    if (data.valid) {
      if (typeof showToast === 'function') showToast('Pipeline is valid.', 'success');
    } else {
      var errors = data.errors || [];
      errors.forEach(function(err) {
        _validationErrors.push({
          macro_id: err.macro_id || '',
          stage_id: err.stage_id || '',
          message: err.message || err.error || String(err)
        });
      });
      if (typeof showToast === 'function') showToast('Validation found ' + errors.length + ' error(s).', 'error');
    }
    _renderDag();
  }).catch(function(err) {
    if (typeof showToast === 'function') showToast('Validation failed: ' + err.message, 'error');
  });
}

function runPipeline() {
  if (!_currentPipeline) {
    if (typeof showToast === 'function') showToast('No pipeline loaded.', 'warning');
    return;
  }
  if (_isDirty) {
    if (typeof showToast === 'function') showToast('Please save the pipeline before running.', 'warning');
    return;
  }
  var id = _currentPipeline.pipeline_id;
  if (typeof showToast === 'function') showToast('Starting pipeline run...', 'info');
  _pipeApi('POST', '/' + id + '/run').then(function(data) {
    if (typeof showToast === 'function') showToast('Pipeline run started. ID: ' + (data.run_id || id), 'success');
  }).catch(function(err) {
    if (typeof showToast === 'function') showToast('Run failed: ' + err.message, 'error');
  });
}

/* =====================================================================
   New Pipeline / Wizard (global functions)
   ===================================================================== */
function startNewPipeline() {
  openWizard();
}

function openWizard() {
  var wizSection = document.getElementById('pipeline-wizard-section');
  var tplSection = document.getElementById('pipeline-template-section');
  if (wizSection) wizSection.style.display = '';
  if (tplSection) tplSection.style.display = 'none';
  /* If the wizard module provides showWizardPanel, call it */
  if (typeof showWizardPanel === 'function') {
    showWizardPanel();
  }
}

function closeWizard() {
  var wizSection = document.getElementById('pipeline-wizard-section');
  var tplSection = document.getElementById('pipeline-template-section');
  if (wizSection) wizSection.style.display = 'none';
  if (tplSection) tplSection.style.display = '';
}

/* =====================================================================
   Drag-and-Drop Stages Between Macros
   ===================================================================== */
function _startStageDrag(e, stageG) {
  var stageId = stageG.getAttribute('data-stage');
  var macroId = stageG.getAttribute('data-macro');
  if (!stageId || !macroId) return;
  _dragStage = { stageId: stageId, macroId: macroId, startX: e.clientX, startY: e.clientY };
  stageG.classList.add('dragging');
  e.preventDefault();
}

function _onStageDragMove(e) {
  if (!_dragStage) return;
  /* Highlight macro under cursor */
  var svg = document.getElementById('pipeline-dag-svg');
  if (!svg) return;
  var rect = svg.getBoundingClientRect();
  var mx = e.clientX - rect.left;
  var my = e.clientY - rect.top;

  /* Convert screen coords to SVG coords */
  var svgX = (mx - _svgTransform.x) / _svgTransform.scale;
  var svgY = (my - _svgTransform.y) / _svgTransform.scale;

  /* Find macro under cursor */
  var macroBoxes = svg.querySelectorAll('.macro-box');
  macroBoxes.forEach(function(g) {
    var mid = g.getAttribute('data-macro');
    g.classList.remove('drag-over');
    if (mid && mid !== _dragStage.macroId) {
      /* Simple hit test using positions */
      var positions = _layoutMacros(_currentPipeline.macro_stages);
      var p = positions[mid];
      if (p && svgX >= p.x && svgX <= p.x + p.w && svgY >= p.y && svgY <= p.y + p.h) {
        g.classList.add('drag-over');
      }
    }
  });
}

function _onStageDragEnd(e) {
  if (!_dragStage) return;
  var svg = document.getElementById('pipeline-dag-svg');
  if (!svg) return;

  var rect = svg.getBoundingClientRect();
  var mx = e.clientX - rect.left;
  var my = e.clientY - rect.top;
  var svgX = (mx - _svgTransform.x) / _svgTransform.scale;
  var svgY = (my - _svgTransform.y) / _svgTransform.scale;

  /* Find target macro */
  var positions = _layoutMacros(_currentPipeline.macro_stages);
  var targetMacroId = null;
  _currentPipeline.macro_stages.forEach(function(m) {
    var p = positions[m.macro_id];
    if (p && m.macro_id !== _dragStage.macroId &&
        svgX >= p.x && svgX <= p.x + p.w &&
        svgY >= p.y && svgY <= p.y + p.h) {
      targetMacroId = m.macro_id;
    }
  });

  if (targetMacroId) {
    _moveStage(_dragStage.macroId, _dragStage.stageId, targetMacroId);
  }

  _cancelStageDrag();
}

function _cancelStageDrag() {
  var svg = document.getElementById('pipeline-dag-svg');
  if (svg) {
    svg.querySelectorAll('.drag-over').forEach(function(g) { g.classList.remove('drag-over'); });
    svg.querySelectorAll('.dragging').forEach(function(g) { g.classList.remove('dragging'); });
  }
  _dragStage = null;
}

function _moveStage(fromMacroId, stageId, toMacroId) {
  var fromMacro = _findMacro(fromMacroId);
  var toMacro = _findMacro(toMacroId);
  if (!fromMacro || !toMacro) return;

  var stageIdx = -1;
  (fromMacro.stages || []).forEach(function(s, i) { if (s.stage_id === stageId) stageIdx = i; });
  if (stageIdx === -1) return;

  var stage = fromMacro.stages.splice(stageIdx, 1)[0];
  /* Clear depends_on since it was relative to the old macro */
  stage.depends_on = [];
  if (!toMacro.stages) toMacro.stages = [];
  toMacro.stages.push(stage);

  /* Clean up old references */
  (fromMacro.stages || []).forEach(function(s) {
    s.depends_on = (s.depends_on || []).filter(function(d) { return d !== stageId; });
  });

  _markDirty();
  _selectedStage = { macroId: toMacroId, stageId: stageId };
  _renderDag();
  if (typeof showToast === 'function') showToast('Stage moved to ' + (toMacro.label || toMacroId) + '.', 'info');
}

/* =====================================================================
   Keyboard Shortcuts
   ===================================================================== */
document.addEventListener('keydown', function(e) {
  /* Only handle when pipeline view is active */
  if (typeof state !== 'undefined' && state.activeView !== 'pipelines') return;

  /* Delete key — remove selected stage */
  if (e.key === 'Delete' && _selectedStage && !_isInputFocused()) {
    _removeStage(_selectedStage.macroId, _selectedStage.stageId);
    e.preventDefault();
  }

  /* Escape — close config panel / collapse macro */
  if (e.key === 'Escape') {
    if (document.getElementById('pipelines-config-panel') &&
        document.getElementById('pipelines-config-panel').style.display !== 'none') {
      _selectedStage = null;
      closeConfigPanel();
      _renderDag();
    } else if (_expandedMacro) {
      _expandedMacro = null;
      _renderDag();
    }
    e.preventDefault();
  }

  /* Ctrl+S — save */
  if ((e.ctrlKey || e.metaKey) && e.key === 's' && _currentPipeline) {
    savePipeline();
    e.preventDefault();
  }
});

function _isInputFocused() {
  var tag = (document.activeElement || {}).tagName || '';
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
}

/* =====================================================================
   Utility: generate unique stage ID
   ===================================================================== */
function _genStageId(prefix) {
  return (prefix || 'stage') + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 6);
}

/* =====================================================================
   Initialization guard: update toolbar state on first render
   ===================================================================== */
(function() {
  /* Deferred so DOM is ready */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { _updateDirtyIndicator(); });
  } else {
    setTimeout(_updateDirtyIndicator, 0);
  }
})();
