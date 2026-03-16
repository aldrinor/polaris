/* =====================================================================
   document_panel.js — Left panel document manager (NotebookLM-style)

   Vertical source list with checkmarks, "Select all" toggle,
   prominent "+ Add sources" button. Matches NotebookLM layout.

   Depends on: core.js (esc, showToast), document_upload.js
   ===================================================================== */

var _docPanelDocs = []; // Cached document list
var _selectedDocIds = new Set(); // Selected document IDs for research context

/* =====================================================================
   Render Document List
   ===================================================================== */
function renderDocumentPanel() {
  var list = document.getElementById("ws-doc-list");
  var footer = document.getElementById("ws-doc-footer");
  if (!list) return;

  // Fetch documents
  fetch("/api/documents/list")
  .then(function(r) { return r.ok ? r.json() : null; })
  .then(function(data) {
    if (!data || !data.documents) {
      _docPanelDocs = [];
      _renderDocList(list, footer);
      return;
    }
    _docPanelDocs = data.documents;
    _renderDocList(list, footer);
  })
  .catch(function() {
    _docPanelDocs = [];
    _renderDocList(list, footer);
  });
}

function _renderDocList(list, footer) {
  var docIcon = '<svg class="ws-source-row-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>';
  var checkSvg = '<svg class="ws-source-check-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';

  if (_docPanelDocs.length === 0) {
    list.innerHTML = '<div class="ws-source-empty">' +
      '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>' +
      '<span>Saved sources will appear here</span>' +
      '<span class="ws-source-empty-sub">Click Add sources above to add PDFs, websites, or text files.</span>' +
      '</div>';
    if (footer) footer.textContent = "No documents";
    _updateSourceCount();
    if (typeof generateSourceBrief === "function") generateSourceBrief();
    return;
  }

  var html = '';

  // "Select all sources" toggle row
  var allSelected = _selectedDocIds.size === _docPanelDocs.length && _docPanelDocs.length > 0;
  html += '<div class="ws-source-row ws-source-select-all" onclick="toggleSelectAllSources()">' +
    '<span class="ws-source-row-name">Select all sources</span>' +
    '<span class="ws-source-row-check' + (allSelected ? ' checked' : '') + '">' + checkSvg + '</span>' +
    '</div>';

  _docPanelDocs.forEach(function(doc) {
    var docId = doc.doc_id || doc.id || "";
    var name = doc.label || doc.original_filename || doc.filename || doc.name || docId;
    var isSelected = _selectedDocIds.has(docId);

    // Truncate display name
    var displayName = name.length > 36 ? name.substring(0, 34) + "\u2026" : name;

    html += '<div class="ws-source-row' + (isSelected ? ' selected' : '') + '" data-doc-id="' + esc(docId) + '" ' +
      'onclick="toggleDocSelection(\'' + esc(docId) + '\')" title="' + esc(doc.original_filename || doc.filename || name) + '">' +
      docIcon +
      '<span class="ws-source-row-name" ' +
        'ondblclick="event.stopPropagation(); startDocLabelEdit(this, \'' + esc(docId) + '\')">' + esc(displayName) + '</span>' +
      '<button class="ws-source-delete-btn" onclick="event.stopPropagation(); deleteDocument(\'' + esc(docId) + '\')" title="Delete source">&times;</button>' +
      '<span class="ws-source-row-check' + (isSelected ? ' checked' : '') + '">' + checkSvg + '</span>' +
      '</div>';
  });

  list.innerHTML = html;

  var selectedCount = _selectedDocIds.size;
  var totalCount = _docPanelDocs.length;
  if (selectedCount > 0) {
    if (footer) footer.textContent = selectedCount + " of " + totalCount + " selected";
  } else {
    if (footer) footer.textContent = totalCount + " source" + (totalCount !== 1 ? "s" : "");
  }
  _updateSourceCount();

  // If sources changed and no research is actively running, transition to
  // idle so the source brief can show (e.g. after uploading a doc while
  // viewing a stale report from a previous session).
  if (_docPanelDocs.length > 0 &&
      typeof _wsPhase !== "undefined" && _wsPhase !== "idle" &&
      typeof state !== "undefined" && !state.pipelineActive) {
    if (typeof setWorkspacePhase === "function") setWorkspacePhase("idle");
  }

  if (typeof generateSourceBrief === "function") generateSourceBrief();
}

/* =====================================================================
   Source count in chat input
   ===================================================================== */
function _updateSourceCount() {
  var el = document.getElementById("ws-source-count");
  if (!el) return;
  var count = _docPanelDocs.length;
  el.textContent = count > 0 ? count + " sources" : "";
  _updateLeftCount();
}

/* =====================================================================
   Left panel header count (e.g. "Sources (4)")
   ===================================================================== */
function _updateLeftCount() {
  var el = document.getElementById("ws-left-count");
  if (!el) return;
  var count = _docPanelDocs.length;
  el.textContent = count > 0 ? "(" + count + ")" : "";
}

/* =====================================================================
   Select All Toggle
   ===================================================================== */
function toggleSelectAllSources() {
  var allSelected = _selectedDocIds.size === _docPanelDocs.length && _docPanelDocs.length > 0;
  if (allSelected) {
    _selectedDocIds.clear();
  } else {
    _docPanelDocs.forEach(function(doc) {
      var id = doc.doc_id || doc.id;
      if (id) _selectedDocIds.add(id);
    });
  }
  // Re-render to update all checkmarks
  var list = document.getElementById("ws-doc-list");
  var footer = document.getElementById("ws-doc-footer");
  _renderDocList(list, footer);
}

/* =====================================================================
   Document Selection Toggle
   ===================================================================== */
function toggleDocSelection(docId) {
  if (_selectedDocIds.has(docId)) {
    _selectedDocIds.delete(docId);
  } else {
    _selectedDocIds.add(docId);
  }

  // Update row visual state
  var row = document.querySelector('.ws-source-row[data-doc-id="' + docId + '"]');
  if (row) {
    row.classList.toggle("selected", _selectedDocIds.has(docId));
    var check = row.querySelector(".ws-source-row-check");
    if (check) check.classList.toggle("checked", _selectedDocIds.has(docId));
  }

  // Update "Select all" row
  var selectAllRow = document.querySelector(".ws-source-select-all");
  if (selectAllRow) {
    var allSelected = _selectedDocIds.size === _docPanelDocs.length;
    var saCheck = selectAllRow.querySelector(".ws-source-row-check");
    if (saCheck) saCheck.classList.toggle("checked", allSelected);
  }

  // Update footer count
  var footer = document.getElementById("ws-doc-footer");
  var selectedCount = _selectedDocIds.size;
  var totalCount = _docPanelDocs.length;
  if (selectedCount > 0) {
    if (footer) footer.textContent = selectedCount + " of " + totalCount + " selected";
  } else {
    if (footer) footer.textContent = totalCount + " source" + (totalCount !== 1 ? "s" : "");
  }

  // Trigger source brief if not yet generated
  if (typeof generateSourceBrief === "function") generateSourceBrief();
}

/* =====================================================================
   Document Label Editing
   ===================================================================== */
function startDocLabelEdit(nameEl, docId) {
  var currentText = nameEl.textContent;
  var input = document.createElement("input");
  input.className = "ws-source-row-name-input";
  input.type = "text";
  input.value = currentText;
  input.maxLength = 100;

  nameEl.replaceWith(input);
  input.focus();
  input.select();

  function save() {
    var newLabel = input.value.trim();
    if (!newLabel) newLabel = currentText;

    var span = document.createElement("span");
    span.className = "ws-source-row-name";
    span.textContent = newLabel;
    span.setAttribute("ondblclick", "event.stopPropagation(); startDocLabelEdit(this, '" + esc(docId) + "')");
    input.replaceWith(span);

    if (newLabel !== currentText) {
      saveDocLabel(docId, newLabel);
    }
  }

  input.addEventListener("keydown", function(e) {
    if (e.key === "Enter") { e.preventDefault(); save(); }
    if (e.key === "Escape") {
      var span = document.createElement("span");
      span.className = "ws-source-row-name";
      span.textContent = currentText;
      span.setAttribute("ondblclick", "event.stopPropagation(); startDocLabelEdit(this, '" + esc(docId) + "')");
      input.replaceWith(span);
    }
  });

  input.addEventListener("blur", save);
}

function saveDocLabel(docId, label) {
  fetch("/api/documents/" + encodeURIComponent(docId), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label: label })
  })
  .then(function(r) {
    if (!r.ok) throw new Error("Failed to save label");
  })
  .catch(function(err) {
    showToast("Failed to save label: " + err.message, "error");
  });
}

/* =====================================================================
   Add Source Popup (NotebookLM-style type picker)
   ===================================================================== */
function toggleAddSourcePopup() {
  var popup = document.getElementById("ws-add-source-popup");
  if (!popup) return;
  var isOpen = popup.classList.contains("open");
  if (isOpen) {
    closeAddSourcePopup();
  } else {
    _populateCloudProviders();
    popup.classList.add("open");
    setTimeout(function() {
      document.addEventListener("click", _closeAddSourcePopupOutside);
    }, 0);
  }
}

function closeAddSourcePopup() {
  var popup = document.getElementById("ws-add-source-popup");
  if (popup) popup.classList.remove("open");
  document.removeEventListener("click", _closeAddSourcePopupOutside);
}

function _closeAddSourcePopupOutside(e) {
  var wrap = document.getElementById("ws-add-source-wrap");
  if (wrap && !wrap.contains(e.target)) {
    closeAddSourcePopup();
  }
}

function _populateCloudProviders() {
  var container = document.getElementById("ws-add-source-cloud");
  if (!container) return;
  container.innerHTML = "";

  if (!_cloudProviderStatus) return;

  var cloudIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>';
  var providers = [
    { id: "google_drive", label: "Google Drive" },
    { id: "onedrive", label: "OneDrive" },
    { id: "dropbox", label: "Dropbox" }
  ];

  var hasAny = false;
  providers.forEach(function(p) {
    var st = _cloudProviderStatus[p.id];
    if (!st || !st.configured) return;
    hasAny = true;
    var item = document.createElement("button");
    item.className = "ws-add-source-item";
    var dotClass = st.connected ? "ws-cloud-status-dot connected" : "ws-cloud-status-dot";
    item.innerHTML = cloudIcon + '<span style="flex:1;text-align:left">' + p.label + '</span><span class="' + dotClass + '"></span>';
    item.onclick = function() {
      closeAddSourcePopup();
      if (st.connected) {
        showCloudFileBrowser(p.id, p.label);
      } else {
        connectCloudProvider(p.id);
      }
    };
    container.appendChild(item);
  });

  // Hide separator if no cloud providers
  var sep = container.previousElementSibling;
  if (sep && sep.classList.contains("ws-add-source-sep")) {
    sep.style.display = hasAny ? "" : "none";
  }
}

function showWebSearchInline() {
  var searchEl = document.getElementById("ws-source-search");
  if (searchEl) {
    searchEl.style.display = "";
    var input = document.getElementById("ws-source-search-input");
    if (input) {
      input.focus();
      input.select();
    }
  }
}

/* =====================================================================
   Document Upload (Drag & Drop)
   ===================================================================== */
function initDocDropzone() {
  // Wire hidden file input for the new "+ Add source" popup "Upload file" action
  var fileInput = document.getElementById("ws-doc-dropzone-input");
  if (fileInput) {
    fileInput.addEventListener("change", function() {
      if (fileInput.files.length) uploadDocFiles(fileInput.files);
      fileInput.value = ""; // Reset so same file can be re-uploaded
    });
  }

  // Keep drag-and-drop on the entire left panel as a convenience
  var leftPanel = document.getElementById("ws-left");
  if (leftPanel) {
    leftPanel.addEventListener("dragover", function(e) {
      e.preventDefault();
      var btn = document.getElementById("ws-add-source-btn");
      if (btn) { btn.style.borderColor = "var(--accent)"; btn.style.color = "var(--accent)"; }
    });

    leftPanel.addEventListener("dragleave", function(e) {
      e.preventDefault();
      var btn = document.getElementById("ws-add-source-btn");
      if (btn) { btn.style.borderColor = ""; btn.style.color = ""; }
    });

    leftPanel.addEventListener("drop", function(e) {
      e.preventDefault();
      var btn = document.getElementById("ws-add-source-btn");
      if (btn) { btn.style.borderColor = ""; btn.style.color = ""; }
      var files = e.dataTransfer.files;
      if (files.length) uploadDocFiles(files);
    });
  }
}

function uploadDocFiles(files) {
  Array.from(files).forEach(function(file) {
    var formData = new FormData();
    formData.append("file", file);

    fetch("/api/documents/upload", {
      method: "POST",
      body: formData
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        showToast("Upload failed: " + data.error, "error");
      } else {
        showToast("Uploaded: " + (data.filename || file.name), "success");
        renderDocumentPanel();
      }
    })
    .catch(function(err) {
      showToast("Upload failed: " + err.message, "error");
    });
  });
}

/* =====================================================================
   Document Delete
   ===================================================================== */
function deleteDocument(docId) {
  fetch("/api/documents/" + encodeURIComponent(docId), {
    method: "DELETE"
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    showToast(data.message || "Deleted", "info");
    renderDocumentPanel();
  })
  .catch(function(err) {
    showToast("Delete failed: " + err.message, "error");
  });
}

/* =====================================================================
   Web Source Search (NotebookLM-style)
   ===================================================================== */
var _sourceSearchResults = []; // Last search results
var _sourceTypeMenuOpen = false;

function searchWebSources() {
  var input = document.getElementById("ws-source-search-input");
  var query = (input ? input.value : "").trim();
  if (query.length < 2) return;

  var chip = document.getElementById("ws-source-type-chip");
  var sourceType = (chip && chip.dataset.type) || "web";

  // Show loading
  var list = document.getElementById("ws-doc-list");
  var existingLoading = list ? list.querySelector(".ws-source-search-loading") : null;
  if (existingLoading) existingLoading.remove();

  var loading = document.createElement("div");
  loading.className = "ws-source-search-loading";
  loading.innerHTML = '<div class="ws-spin"></div><span>Searching...</span>';
  if (list) list.prepend(loading);

  fetch("/api/sources/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: query, source_type: sourceType, max_results: 8 })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    // Remove loading
    var ld = list ? list.querySelector(".ws-source-search-loading") : null;
    if (ld) ld.remove();

    if (data.error || data.detail) {
      showToast("Search failed: " + (data.detail || data.error), "error");
      return;
    }

    _sourceSearchResults = data.results || [];
    _renderSearchResults(list);
  })
  .catch(function(err) {
    var ld = list ? list.querySelector(".ws-source-search-loading") : null;
    if (ld) ld.remove();
    showToast("Search failed: " + err.message, "error");
  });
}

function _renderSearchResults(list) {
  if (!list || _sourceSearchResults.length === 0) return;

  // Remove previous search results
  var old = list.querySelectorAll(".ws-source-search-result-group");
  old.forEach(function(el) { el.remove(); });

  var globeIcon = '<svg class="ws-source-row-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>';

  var group = document.createElement("div");
  group.className = "ws-source-search-result-group";

  var header = document.createElement("div");
  header.className = "ws-source-search-header";
  header.innerHTML = '<span>Search results</span><button class="ws-source-search-dismiss" onclick="dismissSearchResults()">Dismiss</button>';
  group.appendChild(header);

  _sourceSearchResults.forEach(function(result, i) {
    var row = document.createElement("div");
    row.className = "ws-source-row ws-source-web-result";
    row.setAttribute("data-url", result.url);
    row.setAttribute("title", result.snippet || result.title);

    var displayTitle = result.title.length > 34 ? result.title.substring(0, 32) + "\u2026" : result.title;

    row.innerHTML = globeIcon +
      '<span class="ws-source-row-name">' + esc(displayTitle) + '</span>' +
      '<span class="ws-source-web-domain">' + esc(result.domain) + '</span>' +
      '<button class="ws-source-add-btn" onclick="event.stopPropagation(); addWebSource(' + i + ')" title="Add as source">+</button>';

    group.appendChild(row);
  });

  // Insert at top of list (after select-all if present)
  var selectAll = list.querySelector(".ws-source-select-all");
  if (selectAll && selectAll.nextSibling) {
    list.insertBefore(group, selectAll.nextSibling);
  } else {
    list.prepend(group);
  }
}

function dismissSearchResults() {
  _sourceSearchResults = [];
  var groups = document.querySelectorAll(".ws-source-search-result-group");
  groups.forEach(function(el) { el.remove(); });
}

function addWebSource(index) {
  var result = _sourceSearchResults[index];
  if (!result || !result.url) return;

  // Disable the button to prevent double-click
  var btns = document.querySelectorAll(".ws-source-add-btn");
  if (btns[index]) {
    btns[index].disabled = true;
    btns[index].textContent = "...";
  }

  fetch("/api/sources/import-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: result.url, title: result.title })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.error || data.detail) {
      showToast("Import failed: " + (data.detail || data.error), "error");
      if (btns[index]) { btns[index].disabled = false; btns[index].textContent = "+"; }
      return;
    }
    showToast("Added: " + (data.title || data.filename), "success");
    // Refresh document list
    renderDocumentPanel();
    // Remove this result from the search results
    _sourceSearchResults.splice(index, 1);
    var list = document.getElementById("ws-doc-list");
    _renderSearchResults(list);
  })
  .catch(function(err) {
    showToast("Import failed: " + err.message, "error");
    if (btns[index]) { btns[index].disabled = false; btns[index].textContent = "+"; }
  });
}

/* =====================================================================
   Source Type Menu (Web / Scholar / News)
   ===================================================================== */
function toggleSourceTypeMenu() {
  var chip = document.getElementById("ws-source-type-chip");
  if (!chip) return;

  var existing = document.getElementById("ws-source-type-menu");
  if (existing) {
    existing.remove();
    _sourceTypeMenuOpen = false;
    return;
  }

  _sourceTypeMenuOpen = true;
  var menu = document.createElement("div");
  menu.className = "ws-source-type-menu";
  menu.id = "ws-source-type-menu";

  var types = [
    { id: "web", label: "Web", icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>' },
    { id: "scholar", label: "Scholar", icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>' },
    { id: "news", label: "News", icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1"/><path d="M21 12h-8"/><path d="M21 16h-8"/><path d="M21 8h-8"/></svg>' }
  ];

  var currentType = (chip.dataset.type) || "web";
  types.forEach(function(t) {
    var item = document.createElement("div");
    item.className = "ws-source-type-item" + (t.id === currentType ? " active" : "");
    item.innerHTML = t.icon + '<span>' + t.label + '</span>';
    item.onclick = function() {
      selectSourceType(t.id, t.label);
    };
    menu.appendChild(item);
  });

  // Separator + special actions
  var sep = document.createElement("div");
  sep.className = "ws-source-type-sep";
  menu.appendChild(sep);

  // "Paste URL" action
  var urlItem = document.createElement("div");
  urlItem.className = "ws-source-type-item";
  urlItem.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg><span>Paste website URL</span>';
  urlItem.onclick = function() { closeSourceTypeMenu(); showUrlImportModal(); };
  menu.appendChild(urlItem);

  // "Paste text" action
  var textItem = document.createElement("div");
  textItem.className = "ws-source-type-item";
  textItem.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg><span>Paste copied text</span>';
  textItem.onclick = function() { closeSourceTypeMenu(); showTextImportModal(); };
  menu.appendChild(textItem);

  // Cloud storage providers (if any configured)
  if (_cloudProviderStatus) {
    var cloudIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>';
    var providers = [
      { id: "google_drive", label: "Google Drive" },
      { id: "onedrive", label: "OneDrive" },
      { id: "dropbox", label: "Dropbox" }
    ];
    var hasAny = false;
    providers.forEach(function(p) {
      var st = _cloudProviderStatus[p.id];
      if (!st || !st.configured) return;
      if (!hasAny) {
        var sep2 = document.createElement("div");
        sep2.className = "ws-source-type-sep";
        menu.appendChild(sep2);
        hasAny = true;
      }
      var cloudItem = document.createElement("div");
      cloudItem.className = "ws-source-type-item";
      var dotClass = st.connected ? "ws-cloud-status-dot connected" : "ws-cloud-status-dot";
      cloudItem.innerHTML = cloudIcon + '<span>' + p.label + '</span><span class="' + dotClass + '"></span>';
      cloudItem.onclick = function() {
        closeSourceTypeMenu();
        if (st.connected) {
          showCloudFileBrowser(p.id, p.label);
        } else {
          connectCloudProvider(p.id);
        }
      };
      menu.appendChild(cloudItem);
    });
  }

  chip.parentNode.appendChild(menu);

  // Close on click outside
  setTimeout(function() {
    document.addEventListener("click", _closeSourceTypeMenuOutside);
  }, 0);
}

function _closeSourceTypeMenuOutside(e) {
  var menu = document.getElementById("ws-source-type-menu");
  var chip = document.getElementById("ws-source-type-chip");
  if (menu && !menu.contains(e.target) && chip && !chip.contains(e.target)) {
    closeSourceTypeMenu();
  }
}

function closeSourceTypeMenu() {
  var menu = document.getElementById("ws-source-type-menu");
  if (menu) menu.remove();
  _sourceTypeMenuOpen = false;
  document.removeEventListener("click", _closeSourceTypeMenuOutside);
}

function selectSourceType(typeId, label) {
  var chip = document.getElementById("ws-source-type-chip");
  if (chip) {
    chip.dataset.type = typeId;
    var span = chip.querySelector("span");
    if (span) span.textContent = label;
  }
  closeSourceTypeMenu();
}

/* =====================================================================
   URL Import Modal
   ===================================================================== */
function showUrlImportModal() {
  // Remove existing
  var existing = document.getElementById("ws-url-import-modal");
  if (existing) existing.remove();

  var overlay = document.createElement("div");
  overlay.className = "ws-modal-overlay";
  overlay.id = "ws-url-import-modal";
  overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };

  overlay.innerHTML =
    '<div class="ws-modal">' +
      '<div class="ws-modal-header">' +
        '<span class="ws-modal-title">Add website URL</span>' +
        '<button class="ws-modal-close" onclick="document.getElementById(\'ws-url-import-modal\').remove()">&times;</button>' +
      '</div>' +
      '<div class="ws-modal-body">' +
        '<input type="url" class="ws-modal-input" id="ws-url-import-input" placeholder="https://example.com/article" autofocus>' +
        '<p class="ws-modal-hint">Paste a website URL to import its content as a source.</p>' +
      '</div>' +
      '<div class="ws-modal-actions">' +
        '<button class="ws-modal-btn ws-modal-btn-secondary" onclick="document.getElementById(\'ws-url-import-modal\').remove()">Cancel</button>' +
        '<button class="ws-modal-btn ws-modal-btn-primary" id="ws-url-import-submit" onclick="importUrlSource()">Import</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(overlay);
  setTimeout(function() {
    var inp = document.getElementById("ws-url-import-input");
    if (inp) inp.focus();
  }, 100);

  // Enter to submit
  var inp = overlay.querySelector("#ws-url-import-input");
  if (inp) {
    inp.addEventListener("keydown", function(e) {
      if (e.key === "Enter") { e.preventDefault(); importUrlSource(); }
    });
  }
}

function importUrlSource() {
  var input = document.getElementById("ws-url-import-input");
  var url = (input ? input.value : "").trim();
  if (!url || url.length < 8) {
    showToast("Please enter a valid URL", "error");
    return;
  }

  // Ensure URL has protocol
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    url = "https://" + url;
  }

  var btn = document.getElementById("ws-url-import-submit");
  if (btn) { btn.disabled = true; btn.textContent = "Importing..."; }

  fetch("/api/sources/import-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: url })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.error || data.detail) {
      showToast("Import failed: " + (data.detail || data.error), "error");
      if (btn) { btn.disabled = false; btn.textContent = "Import"; }
      return;
    }
    showToast("Imported: " + (data.title || data.filename), "success");
    var modal = document.getElementById("ws-url-import-modal");
    if (modal) modal.remove();
    renderDocumentPanel();
  })
  .catch(function(err) {
    showToast("Import failed: " + err.message, "error");
    if (btn) { btn.disabled = false; btn.textContent = "Import"; }
  });
}

/* =====================================================================
   Text Import Modal
   ===================================================================== */
function showTextImportModal() {
  var existing = document.getElementById("ws-text-import-modal");
  if (existing) existing.remove();

  var overlay = document.createElement("div");
  overlay.className = "ws-modal-overlay";
  overlay.id = "ws-text-import-modal";
  overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };

  overlay.innerHTML =
    '<div class="ws-modal">' +
      '<div class="ws-modal-header">' +
        '<span class="ws-modal-title">Paste copied text</span>' +
        '<button class="ws-modal-close" onclick="document.getElementById(\'ws-text-import-modal\').remove()">&times;</button>' +
      '</div>' +
      '<div class="ws-modal-body">' +
        '<input type="text" class="ws-modal-input" id="ws-text-import-title" placeholder="Source title (optional)">' +
        '<textarea class="ws-modal-textarea" id="ws-text-import-content" placeholder="Paste your text content here..." rows="8"></textarea>' +
        '<p class="ws-modal-hint">Paste text from any source. It will be added as a research source.</p>' +
      '</div>' +
      '<div class="ws-modal-actions">' +
        '<button class="ws-modal-btn ws-modal-btn-secondary" onclick="document.getElementById(\'ws-text-import-modal\').remove()">Cancel</button>' +
        '<button class="ws-modal-btn ws-modal-btn-primary" id="ws-text-import-submit" onclick="importTextSource()">Add source</button>' +
      '</div>' +
    '</div>';

  document.body.appendChild(overlay);
  setTimeout(function() {
    var ta = document.getElementById("ws-text-import-content");
    if (ta) ta.focus();
  }, 100);
}

function importTextSource() {
  var titleInput = document.getElementById("ws-text-import-title");
  var contentInput = document.getElementById("ws-text-import-content");
  var text = (contentInput ? contentInput.value : "").trim();
  var title = (titleInput ? titleInput.value : "").trim() || "Pasted text";

  if (text.length < 10) {
    showToast("Please paste at least 10 characters of text", "error");
    return;
  }

  var btn = document.getElementById("ws-text-import-submit");
  if (btn) { btn.disabled = true; btn.textContent = "Adding..."; }

  fetch("/api/sources/import-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text, title: title })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.error || data.detail) {
      showToast("Import failed: " + (data.detail || data.error), "error");
      if (btn) { btn.disabled = false; btn.textContent = "Add source"; }
      return;
    }
    showToast("Added: " + (data.title || data.filename), "success");
    var modal = document.getElementById("ws-text-import-modal");
    if (modal) modal.remove();
    renderDocumentPanel();
  })
  .catch(function(err) {
    showToast("Import failed: " + err.message, "error");
    if (btn) { btn.disabled = false; btn.textContent = "Add source"; }
  });
}

/* =====================================================================
   Get Document Context for Research API
   ===================================================================== */
function getDocumentContext() {
  var allIds = _docPanelDocs.map(function(d) { return d.doc_id || d.id; }).filter(Boolean);
  // If user selected specific docs, filter to only those
  if (_selectedDocIds.size > 0) {
    return allIds.filter(function(id) { return _selectedDocIds.has(id); });
  }
  return allIds;
}

/* =====================================================================
   Cloud Storage Integration (Google Drive, OneDrive, Dropbox)
   ===================================================================== */
var _cloudProviderStatus = null; // Cached from /api/cloud/status

function fetchCloudStatus() {
  fetch("/api/cloud/status")
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(data) {
      _cloudProviderStatus = data;
    })
    .catch(function() {
      _cloudProviderStatus = null;
    });
}

function connectCloudProvider(provider) {
  var popup = window.open(
    "/api/cloud/" + encodeURIComponent(provider) + "/authorize",
    "cloud_auth",
    "width=600,height=700,scrollbars=yes"
  );
  window.addEventListener("message", function onMsg(e) {
    if (e.data && e.data.type === "cloud_auth_success") {
      window.removeEventListener("message", onMsg);
      fetchCloudStatus();
      showToast("Connected to " + (e.data.provider || provider), "success");
      showCloudFileBrowser(e.data.provider || provider);
    }
  });
}

function disconnectCloudProvider(provider) {
  fetch("/api/cloud/" + encodeURIComponent(provider) + "/disconnect", {
    method: "DELETE"
  })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      fetchCloudStatus();
      showToast(data.message || "Disconnected", "info");
    })
    .catch(function(err) {
      showToast("Disconnect failed: " + err.message, "error");
    });
}

var _cloudBrowserProvider = "";
var _cloudBrowserLabel = "";
var _cloudSelectedFiles = []; // {file_id, file_name, mime_type}

function showCloudFileBrowser(provider, label) {
  _cloudBrowserProvider = provider;
  _cloudBrowserLabel = label || provider;
  _cloudSelectedFiles = [];

  // Remove existing modal
  var existing = document.getElementById("ws-cloud-browser-modal");
  if (existing) existing.remove();

  var overlay = document.createElement("div");
  overlay.className = "ws-modal-overlay";
  overlay.id = "ws-cloud-browser-modal";
  overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };

  overlay.innerHTML =
    '<div class="ws-modal" style="max-width:560px;min-height:400px">' +
      '<div class="ws-modal-header">' +
        '<span class="ws-modal-title">' + esc(_cloudBrowserLabel) + '</span>' +
        '<button class="ws-modal-close" onclick="document.getElementById(\'ws-cloud-browser-modal\').remove()">&times;</button>' +
      '</div>' +
      '<div class="ws-cloud-breadcrumb" id="ws-cloud-breadcrumb"></div>' +
      '<div class="ws-modal-body" id="ws-cloud-file-list" style="min-height:250px;max-height:400px;overflow-y:auto;padding:0">' +
        '<div class="ws-source-search-loading" style="padding:40px 0"><div class="ws-spin"></div><span>Loading files...</span></div>' +
      '</div>' +
      '<div class="ws-cloud-import-bar" id="ws-cloud-import-bar">' +
        '<span id="ws-cloud-import-count">0 selected</span>' +
        '<div style="display:flex;gap:8px">' +
          '<button class="ws-modal-btn ws-modal-btn-secondary" onclick="disconnectCloudProvider(\'' + esc(provider) + '\'); document.getElementById(\'ws-cloud-browser-modal\').remove()">Disconnect</button>' +
          '<button class="ws-modal-btn ws-modal-btn-primary" id="ws-cloud-import-btn" onclick="importCloudSelected()" disabled>Import selected</button>' +
        '</div>' +
      '</div>' +
    '</div>';

  document.body.appendChild(overlay);
  loadCloudFolder(provider, "");
}

function loadCloudFolder(provider, folderId) {
  var listEl = document.getElementById("ws-cloud-file-list");
  if (listEl) {
    listEl.innerHTML = '<div class="ws-source-search-loading" style="padding:40px 0"><div class="ws-spin"></div><span>Loading...</span></div>';
  }

  var url = "/api/cloud/" + encodeURIComponent(provider) + "/files";
  if (folderId) url += "?folder_id=" + encodeURIComponent(folderId);

  fetch(url)
    .then(function(r) {
      if (!r.ok) throw new Error("Failed to load files");
      return r.json();
    })
    .then(function(data) {
      _renderCloudBreadcrumb(data.breadcrumb || [], provider);
      _renderCloudFiles(data.items || [], provider);
    })
    .catch(function(err) {
      if (listEl) {
        listEl.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-tertiary)">' +
          '<p>Failed to load files</p><p style="font-size:11px">' + esc(err.message) + '</p></div>';
      }
    });
}

function _renderCloudBreadcrumb(crumbs, provider) {
  var el = document.getElementById("ws-cloud-breadcrumb");
  if (!el) return;
  var html = "";
  crumbs.forEach(function(c, i) {
    if (i > 0) html += '<span class="ws-cloud-breadcrumb-sep">/</span>';
    if (i < crumbs.length - 1) {
      html += '<a class="ws-cloud-breadcrumb-link" href="#" onclick="event.preventDefault(); loadCloudFolder(\'' +
        esc(provider) + '\', \'' + esc(c.id) + '\')">' + esc(c.name) + '</a>';
    } else {
      html += '<span class="ws-cloud-breadcrumb-current">' + esc(c.name) + '</span>';
    }
  });
  el.innerHTML = html;
}

function _renderCloudFiles(items, provider) {
  var listEl = document.getElementById("ws-cloud-file-list");
  if (!listEl) return;

  if (items.length === 0) {
    listEl.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-tertiary)">This folder is empty</div>';
    return;
  }

  var folderIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>';
  var fileIcon = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';

  var html = "";
  items.forEach(function(item) {
    if (item.is_folder) {
      html += '<div class="ws-cloud-file-row is-folder" onclick="loadCloudFolder(\'' +
        esc(provider) + '\', \'' + esc(item.id) + '\')">' +
        '<span class="ws-cloud-file-icon">' + folderIcon + '</span>' +
        '<span class="ws-cloud-file-name">' + esc(item.name) + '</span>' +
        '</div>';
    } else {
      var sizeStr = item.size ? _formatFileSize(item.size) : "";
      var isChecked = _cloudSelectedFiles.some(function(f) { return f.file_id === item.id; });
      html += '<div class="ws-cloud-file-row" onclick="_toggleCloudFile(\'' + esc(item.id) + '\', \'' +
        esc(item.name) + '\', \'' + esc(item.mime_type || "") + '\')">' +
        '<input type="checkbox" class="ws-cloud-file-check" ' + (isChecked ? 'checked' : '') +
        ' onclick="event.stopPropagation(); _toggleCloudFile(\'' + esc(item.id) + '\', \'' +
        esc(item.name) + '\', \'' + esc(item.mime_type || "") + '\')">' +
        '<span class="ws-cloud-file-icon">' + fileIcon + '</span>' +
        '<span class="ws-cloud-file-name">' + esc(item.name) + '</span>' +
        '<span class="ws-cloud-file-size">' + sizeStr + '</span>' +
        '</div>';
    }
  });
  listEl.innerHTML = html;
}

function _toggleCloudFile(fileId, fileName, mimeType) {
  var idx = -1;
  _cloudSelectedFiles.forEach(function(f, i) {
    if (f.file_id === fileId) idx = i;
  });

  if (idx >= 0) {
    _cloudSelectedFiles.splice(idx, 1);
  } else {
    _cloudSelectedFiles.push({ file_id: fileId, file_name: fileName, mime_type: mimeType });
  }

  // Update checkbox visuals
  var rows = document.querySelectorAll(".ws-cloud-file-row:not(.is-folder)");
  rows.forEach(function(row) {
    var cb = row.querySelector(".ws-cloud-file-check");
    if (cb) {
      var rowFileId = row.getAttribute("onclick") || "";
      var isSelected = _cloudSelectedFiles.some(function(f) { return rowFileId.indexOf(f.file_id) > -1; });
      cb.checked = isSelected;
    }
  });

  // Update import bar
  var countEl = document.getElementById("ws-cloud-import-count");
  var btn = document.getElementById("ws-cloud-import-btn");
  var n = _cloudSelectedFiles.length;
  if (countEl) countEl.textContent = n + " selected";
  if (btn) {
    btn.disabled = n === 0;
    btn.textContent = n > 0 ? "Import selected (" + n + ")" : "Import selected";
  }
}

function importCloudSelected() {
  if (_cloudSelectedFiles.length === 0) return;

  var btn = document.getElementById("ws-cloud-import-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Importing..."; }

  var provider = _cloudBrowserProvider;

  if (_cloudSelectedFiles.length === 1) {
    // Single file import
    var f = _cloudSelectedFiles[0];
    fetch("/api/cloud/" + encodeURIComponent(provider) + "/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(f)
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error || data.detail) {
          showToast("Import failed: " + (data.detail || data.error), "error");
          if (btn) { btn.disabled = false; btn.textContent = "Import selected"; }
          return;
        }
        showToast("Imported: " + (data.filename || f.file_name), "success");
        _closeCloudBrowser();
        renderDocumentPanel();
      })
      .catch(function(err) {
        showToast("Import failed: " + err.message, "error");
        if (btn) { btn.disabled = false; btn.textContent = "Import selected"; }
      });
  } else {
    // Batch import
    fetch("/api/cloud/" + encodeURIComponent(provider) + "/import-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: _cloudSelectedFiles })
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var msg = "Imported " + (data.imported || 0) + " of " + (data.total || 0) + " files";
        showToast(msg, data.imported > 0 ? "success" : "error");
        _closeCloudBrowser();
        renderDocumentPanel();
      })
      .catch(function(err) {
        showToast("Batch import failed: " + err.message, "error");
        if (btn) { btn.disabled = false; btn.textContent = "Import selected"; }
      });
  }
}

function _closeCloudBrowser() {
  var modal = document.getElementById("ws-cloud-browser-modal");
  if (modal) modal.remove();
  _cloudSelectedFiles = [];
}

function _formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

/* =====================================================================
   Initialization
   ===================================================================== */
document.addEventListener("DOMContentLoaded", function() {
  initDocDropzone();
  renderDocumentPanel();
  fetchCloudStatus();
});
