/* =====================================================================
   document_upload.js — Drag-and-drop document upload zone for POLARIS
   research input. Supports PDF, DOCX, DOC, XLSX, PPTX, TXT, MD, CSV,
   HTML, HTM, Images (PNG/JPG/WEBP/GIF), Audio (MP3/WAV/M4A/AAC/OGG/FLAC).
   Integrates with the landing page and exposes uploaded doc IDs
   to the pipeline via getUploadedDocumentIds().

   Dependencies: core.js (state, showToast, esc)
   ===================================================================== */

/* =====================================================================
   Module State
   ===================================================================== */
var _uploadedDocs = [];
var _uploadStyleInjected = false;
var _uploadZoneEl = null;
var _fileListEl = null;
var _hiddenInput = null;
var _dragCounter = 0;

/* Configurable max file size in bytes (default 100 MB) */
var _maxFileSizeBytes = 100 * 1024 * 1024;

/* Accepted MIME types and extensions */
var _acceptedExtensions = [
  ".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".txt", ".md", ".csv", ".html", ".htm",
  ".png", ".jpg", ".jpeg", ".webp", ".gif",
  ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"
];
var _acceptedMimeTypes = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "text/plain",
  "text/markdown",
  "text/csv",
  "text/html",
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
  "audio/mpeg",
  "audio/wav",
  "audio/x-wav",
  "audio/mp4",
  "audio/aac",
  "audio/ogg",
  "audio/flac"
];

/* =====================================================================
   Style Injection
   ===================================================================== */
function _injectUploadStyles() {
  if (_uploadStyleInjected) return;
  _uploadStyleInjected = true;

  var style = document.createElement("style");
  style.id = "polaris-upload-styles";
  style.textContent = [
    /* Upload zone container */
    ".doc-upload-zone {",
    "  display: flex;",
    "  flex-direction: column;",
    "  align-items: center;",
    "  justify-content: center;",
    "  width: 100%;",
    "  max-width: 640px;",
    "  min-height: 96px;",
    "  margin: 0 auto var(--lg) auto;",
    "  padding: var(--md) var(--lg);",
    "  border: 2px dashed var(--border);",
    "  border-radius: var(--radius-lg);",
    "  background: transparent;",
    "  cursor: pointer;",
    "  transition: all var(--duration-normal) var(--ease);",
    "  position: relative;",
    "  user-select: none;",
    "}",

    /* Hover and drag-over states */
    ".doc-upload-zone:hover {",
    "  border-color: var(--border-active);",
    "  background: var(--bg-inset);",
    "}",
    ".doc-upload-zone.drag-over {",
    "  border-color: var(--accent);",
    "  background: var(--accent-dim);",
    "  box-shadow: 0 0 0 3px var(--accent-dim);",
    "}",

    /* Has files state — more compact */
    ".doc-upload-zone.has-files {",
    "  min-height: 64px;",
    "  padding: var(--sm) var(--md);",
    "}",

    /* Inner content */
    ".doc-upload-zone-inner {",
    "  display: flex;",
    "  flex-direction: column;",
    "  align-items: center;",
    "  gap: var(--xs);",
    "  pointer-events: none;",
    "}",
    ".doc-upload-zone.has-files .doc-upload-zone-inner {",
    "  display: none;",
    "}",

    /* File icon */
    ".doc-upload-icon {",
    "  font-size: 28px;",
    "  line-height: 1;",
    "  color: var(--text-tertiary);",
    "  transition: color var(--duration-fast) var(--ease);",
    "}",
    ".doc-upload-zone:hover .doc-upload-icon,",
    ".doc-upload-zone.drag-over .doc-upload-icon {",
    "  color: var(--accent);",
    "}",

    /* Label text */
    ".doc-upload-label {",
    "  font-size: var(--text-sm);",
    "  color: var(--text-tertiary);",
    "  text-align: center;",
    "  line-height: 1.4;",
    "}",
    ".doc-upload-label strong {",
    "  color: var(--accent);",
    "  font-weight: 600;",
    "}",

    /* Accepted formats hint */
    ".doc-upload-hint {",
    "  font-size: var(--text-3xs);",
    "  color: var(--text-tertiary);",
    "  margin-top: 2px;",
    "}",

    /* File list area */
    ".doc-file-list {",
    "  display: flex;",
    "  flex-wrap: wrap;",
    "  gap: var(--sm);",
    "  width: 100%;",
    "  max-width: 640px;",
    "  margin: 0 auto;",
    "  justify-content: center;",
    "}",

    /* Individual file chip */
    ".doc-file-chip {",
    "  display: inline-flex;",
    "  align-items: center;",
    "  gap: 6px;",
    "  padding: 5px 10px;",
    "  background: var(--bg-card);",
    "  border: 1px solid var(--border);",
    "  border-radius: var(--radius);",
    "  font-size: var(--text-xs);",
    "  color: var(--text-primary);",
    "  max-width: 260px;",
    "  transition: all var(--duration-fast) var(--ease);",
    "  animation: doc-chip-appear 250ms var(--ease) both;",
    "}",
    ".doc-file-chip:hover {",
    "  border-color: var(--border-active);",
    "  background: var(--bg-hover);",
    "}",

    /* Chip filename (truncated) */
    ".doc-chip-name {",
    "  overflow: hidden;",
    "  text-overflow: ellipsis;",
    "  white-space: nowrap;",
    "  max-width: 150px;",
    "  font-weight: 500;",
    "}",

    /* Chip file size */
    ".doc-chip-size {",
    "  color: var(--text-tertiary);",
    "  font-size: var(--text-3xs);",
    "  white-space: nowrap;",
    "}",

    /* Status indicators */
    ".doc-chip-status {",
    "  display: inline-flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  width: 16px;",
    "  height: 16px;",
    "  flex-shrink: 0;",
    "}",

    /* Spinner (uploading/parsing) */
    ".doc-chip-spinner {",
    "  width: 14px;",
    "  height: 14px;",
    "  border: 2px solid var(--border);",
    "  border-top-color: var(--accent);",
    "  border-radius: 50%;",
    "  animation: doc-spin 0.7s linear infinite;",
    "}",

    /* Checkmark (success) */
    ".doc-chip-check {",
    "  color: var(--success);",
    "  font-size: 14px;",
    "  line-height: 1;",
    "  font-weight: 700;",
    "}",

    /* Error indicator */
    ".doc-chip-error {",
    "  color: var(--error);",
    "  font-size: 14px;",
    "  line-height: 1;",
    "  font-weight: 700;",
    "}",

    /* Delete button on chip */
    ".doc-chip-delete {",
    "  display: inline-flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  width: 36px;",
    "  height: 36px;",
    "  border: none;",
    "  background: transparent;",
    "  color: var(--text-tertiary);",
    "  font-size: 14px;",
    "  line-height: 1;",
    "  cursor: pointer;",
    "  border-radius: var(--radius-sm);",
    "  transition: all var(--duration-fast) var(--ease);",
    "  padding: 0;",
    "  flex-shrink: 0;",
    "}",
    ".doc-chip-delete:hover {",
    "  background: var(--error-dim);",
    "  color: var(--error);",
    "}",
    ".doc-chip-delete:focus-visible {",
    "  outline: 2px solid var(--accent);",
    "  outline-offset: 1px;",
    "}",

    /* Pages badge */
    ".doc-chip-pages {",
    "  font-size: var(--text-3xs);",
    "  color: var(--text-tertiary);",
    "  white-space: nowrap;",
    "}",

    /* Upload zone focus-visible for keyboard */
    ".doc-upload-zone:focus-visible {",
    "  outline: 2px solid var(--accent);",
    "  outline-offset: 2px;",
    "}",

    /* Inline chip section between search input and depth row */
    ".doc-upload-inline-chips {",
    "  display: flex;",
    "  flex-wrap: wrap;",
    "  gap: 6px;",
    "  width: 100%;",
    "  max-width: 640px;",
    "  margin: 0 auto var(--sm) auto;",
    "  justify-content: center;",
    "  min-height: 0;",
    "}",
    ".doc-upload-inline-chips:empty {",
    "  display: none;",
    "}",

    /* Animations */
    "@keyframes doc-spin {",
    "  to { transform: rotate(360deg); }",
    "}",
    "@keyframes doc-chip-appear {",
    "  from { opacity: 0; transform: scale(0.85) translateY(4px); }",
    "  to { opacity: 1; transform: scale(1) translateY(0); }",
    "}",

    /* File type icon colors */
    ".doc-type-icon {",
    "  font-size: 14px;",
    "  flex-shrink: 0;",
    "}",
    ".doc-type-pdf { color: #ef4444; }",
    ".doc-type-doc { color: #3b82f6; }",
    ".doc-type-xls { color: #22c55e; }",
    ".doc-type-ppt { color: #f97316; }",
    ".doc-type-txt { color: var(--text-secondary); }",
    ".doc-type-csv { color: #14b8a6; }",
    ".doc-type-html { color: #a855f7; }",
    ".doc-type-md { color: var(--text-secondary); }",
    ".doc-type-img { color: #ec4899; }",
    ".doc-type-audio { color: #8b5cf6; }",

    /* Responsive */
    "@media (max-width: 640px) {",
    "  .doc-upload-zone { min-height: 72px; padding: var(--sm) var(--md); }",
    "  .doc-upload-icon { font-size: 22px; }",
    "  .doc-file-chip { max-width: 200px; }",
    "  .doc-chip-name { max-width: 100px; }",
    "}"
  ].join("\n");

  document.head.appendChild(style);
}

/* =====================================================================
   File Type Helpers
   ===================================================================== */
function _getFileExtension(filename) {
  if (!filename) return "";
  var idx = filename.lastIndexOf(".");
  if (idx < 0) return "";
  return filename.substring(idx).toLowerCase();
}

function _isAcceptedFile(file) {
  var ext = _getFileExtension(file.name);
  if (_acceptedExtensions.indexOf(ext) !== -1) return true;
  if (file.type && _acceptedMimeTypes.indexOf(file.type) !== -1) return true;
  return false;
}

function _getFileTypeIcon(filename) {
  var ext = _getFileExtension(filename);
  switch (ext) {
    case ".pdf": return '<span class="doc-type-icon doc-type-pdf">&#128196;</span>';
    case ".docx":
    case ".doc": return '<span class="doc-type-icon doc-type-doc">&#128462;</span>';
    case ".xlsx": return '<span class="doc-type-icon doc-type-xls">&#128202;</span>';
    case ".pptx": return '<span class="doc-type-icon doc-type-ppt">&#128218;</span>';
    case ".txt": return '<span class="doc-type-icon doc-type-txt">&#128196;</span>';
    case ".md": return '<span class="doc-type-icon doc-type-md">&#128221;</span>';
    case ".csv": return '<span class="doc-type-icon doc-type-csv">&#128200;</span>';
    case ".html":
    case ".htm": return '<span class="doc-type-icon doc-type-html">&#128195;</span>';
    case ".png":
    case ".jpg":
    case ".jpeg":
    case ".webp":
    case ".gif": return '<span class="doc-type-icon doc-type-img">&#128248;</span>';
    case ".mp3":
    case ".wav":
    case ".m4a":
    case ".aac":
    case ".ogg":
    case ".flac": return '<span class="doc-type-icon doc-type-audio">&#127925;</span>';
    default: return '<span class="doc-type-icon">&#128196;</span>';
  }
}

function _formatFileSize(bytes) {
  if (bytes === 0) return "0 B";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

/* =====================================================================
   DOM Construction
   ===================================================================== */
function _buildUploadZone() {
  if (_uploadZoneEl) return;

  _injectUploadStyles();

  /* Hidden file input */
  _hiddenInput = document.createElement("input");
  _hiddenInput.type = "file";
  _hiddenInput.multiple = true;
  _hiddenInput.accept = _acceptedExtensions.join(",");
  _hiddenInput.style.display = "none";
  _hiddenInput.setAttribute("aria-hidden", "true");
  _hiddenInput.addEventListener("change", _onFileInputChange);

  /* Inline chip container (between search input and depth row) */
  _fileListEl = document.createElement("div");
  _fileListEl.className = "doc-upload-inline-chips";
  _fileListEl.id = "doc-upload-file-list";

  /* Upload zone */
  _uploadZoneEl = document.createElement("div");
  _uploadZoneEl.className = "doc-upload-zone";
  _uploadZoneEl.id = "doc-upload-zone";
  _uploadZoneEl.setAttribute("role", "button");
  _uploadZoneEl.setAttribute("tabindex", "0");
  _uploadZoneEl.setAttribute("aria-label", "Document upload area. Drop files here or click to browse.");
  _uploadZoneEl.innerHTML = [
    '<div class="doc-upload-zone-inner">',
    '  <div class="doc-upload-icon">&#128206;</div>',
    '  <div class="doc-upload-label">Drop files here or <strong>click to upload</strong></div>',
    '  <div class="doc-upload-hint">PDF, DOCX, XLSX, PPTX, TXT, CSV, HTML, Images, Audio &mdash; up to ' + _formatFileSize(_maxFileSizeBytes) + '</div>',
    '</div>'
  ].join("\n");

  _uploadZoneEl.appendChild(_hiddenInput);

  /* Insert into the DOM: after .landing-depth-row */
  var depthRow = document.querySelector(".landing-depth-row");
  if (depthRow && depthRow.parentNode) {
    /* Insert the inline file chips between input-wrap and depth row */
    var inputWrap = document.querySelector(".landing-input-wrap");
    if (inputWrap && inputWrap.nextSibling) {
      depthRow.parentNode.insertBefore(_fileListEl, depthRow);
    } else {
      depthRow.parentNode.insertBefore(_fileListEl, depthRow);
    }
    /* Insert upload zone after the depth row */
    if (depthRow.nextSibling) {
      depthRow.parentNode.insertBefore(_uploadZoneEl, depthRow.nextSibling);
    } else {
      depthRow.parentNode.appendChild(_uploadZoneEl);
    }
  }

  /* Bind events */
  _bindUploadEvents();
}

/* =====================================================================
   Event Binding
   ===================================================================== */
function _bindUploadEvents() {
  if (!_uploadZoneEl) return;

  /* Click to browse */
  _uploadZoneEl.addEventListener("click", function(e) {
    /* Do not trigger if click was on a chip delete button inside the zone */
    if (e.target.closest && e.target.closest(".doc-chip-delete")) return;
    _hiddenInput.click();
  });

  /* Keyboard activation */
  _uploadZoneEl.addEventListener("keydown", function(e) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      _hiddenInput.click();
    }
  });

  /* Drag events */
  _uploadZoneEl.addEventListener("dragenter", _onDragEnter);
  _uploadZoneEl.addEventListener("dragover", _onDragOver);
  _uploadZoneEl.addEventListener("dragleave", _onDragLeave);
  _uploadZoneEl.addEventListener("drop", _onDrop);

  /* Also bind drag events on the full landing page for better UX */
  var landingPage = document.getElementById("landing-page");
  if (landingPage) {
    landingPage.addEventListener("dragenter", _onPageDragEnter);
    landingPage.addEventListener("dragover", _onPageDragOver);
    landingPage.addEventListener("dragleave", _onPageDragLeave);
    landingPage.addEventListener("drop", _onPageDrop);
  }
}

/* =====================================================================
   Drag Event Handlers
   ===================================================================== */
function _onDragEnter(e) {
  e.preventDefault();
  e.stopPropagation();
  _dragCounter++;
  _uploadZoneEl.classList.add("drag-over");
}

function _onDragOver(e) {
  e.preventDefault();
  e.stopPropagation();
  /* Set the drop effect */
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = "copy";
  }
}

function _onDragLeave(e) {
  e.preventDefault();
  e.stopPropagation();
  _dragCounter--;
  if (_dragCounter <= 0) {
    _dragCounter = 0;
    _uploadZoneEl.classList.remove("drag-over");
  }
}

function _onDrop(e) {
  e.preventDefault();
  e.stopPropagation();
  _dragCounter = 0;
  _uploadZoneEl.classList.remove("drag-over");

  var files = e.dataTransfer ? e.dataTransfer.files : null;
  if (files && files.length > 0) {
    _processFiles(files);
  }
}

/* Page-level drag handlers — redirect to upload zone visual cue */
function _onPageDragEnter(e) {
  e.preventDefault();
  /* Highlight the upload zone when files are dragged anywhere on the landing page */
  if (_uploadZoneEl && !_uploadZoneEl.classList.contains("drag-over")) {
    _uploadZoneEl.classList.add("drag-over");
  }
}

function _onPageDragOver(e) {
  e.preventDefault();
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = "copy";
  }
}

function _onPageDragLeave(e) {
  /* Only remove if actually leaving the landing page */
  var related = e.relatedTarget;
  var landingPage = document.getElementById("landing-page");
  if (landingPage && related && landingPage.contains(related)) return;
  if (_uploadZoneEl) {
    _uploadZoneEl.classList.remove("drag-over");
  }
}

function _onPageDrop(e) {
  /* If the drop happens outside the upload zone but inside the landing page,
     still process the files and remove the highlight */
  if (_uploadZoneEl) {
    _uploadZoneEl.classList.remove("drag-over");
  }
  /* Only process if the drop was NOT already handled by the zone itself */
  if (e.target.closest && e.target.closest("#doc-upload-zone")) return;
  e.preventDefault();
  var files = e.dataTransfer ? e.dataTransfer.files : null;
  if (files && files.length > 0) {
    _processFiles(files);
  }
}

/* =====================================================================
   File Input Change Handler
   ===================================================================== */
function _onFileInputChange(e) {
  var files = e.target.files;
  if (files && files.length > 0) {
    _processFiles(files);
  }
  /* Reset so the same file can be selected again */
  _hiddenInput.value = "";
}

/* =====================================================================
   File Processing and Validation
   ===================================================================== */
function _processFiles(fileList) {
  var validFiles = [];
  var rejected = [];

  for (var i = 0; i < fileList.length; i++) {
    var file = fileList[i];

    /* Check extension/type */
    if (!_isAcceptedFile(file)) {
      rejected.push(file.name + " (unsupported format)");
      continue;
    }

    /* Check size */
    if (file.size > _maxFileSizeBytes) {
      rejected.push(file.name + " (exceeds " + _formatFileSize(_maxFileSizeBytes) + ")");
      continue;
    }

    /* Check for duplicate filename already uploaded */
    var isDuplicate = false;
    for (var j = 0; j < _uploadedDocs.length; j++) {
      if (_uploadedDocs[j].filename === file.name) {
        isDuplicate = true;
        break;
      }
    }
    if (isDuplicate) {
      rejected.push(file.name + " (already uploaded)");
      continue;
    }

    validFiles.push(file);
  }

  /* Notify about rejected files */
  if (rejected.length > 0) {
    showToast("Rejected: " + rejected.join(", "), "warning");
  }

  /* Upload each valid file */
  for (var k = 0; k < validFiles.length; k++) {
    _uploadSingleFile(validFiles[k]);
  }
}

/* =====================================================================
   Single File Upload
   ===================================================================== */
function _uploadSingleFile(file) {
  /* Create a placeholder entry in _uploadedDocs */
  var placeholderDoc = {
    doc_id: null,
    filename: file.name,
    size_bytes: file.size,
    status: "uploading",
    pages: null,
    content_preview: null,
    _localFile: file
  };
  _uploadedDocs.push(placeholderDoc);
  _renderFileChips();
  _updateZoneState();

  /* Build FormData */
  var formData = new FormData();
  formData.append("file", file, file.name);

  /* If a vector ID is active, include it */
  if (typeof state !== "undefined" && state.vectorId && state.vectorId !== "--") {
    formData.append("vector_id", state.vectorId);
  }

  /* Send the upload request */
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/documents/upload", true);

  /* Progress tracking */
  xhr.upload.addEventListener("progress", function(e) {
    if (e.lengthComputable) {
      var pct = Math.round((e.loaded / e.total) * 100);
      _updateChipProgress(file.name, pct);
    }
  });

  xhr.addEventListener("load", function() {
    if (xhr.status >= 200 && xhr.status < 300) {
      var response;
      try {
        response = JSON.parse(xhr.responseText);
      } catch (parseErr) {
        _markUploadError(file.name, "Invalid server response");
        return;
      }

      if (response.documents && response.documents.length > 0) {
        var serverDoc = response.documents[0];
        /* Update the placeholder with real server data */
        for (var i = 0; i < _uploadedDocs.length; i++) {
          if (_uploadedDocs[i].filename === file.name && _uploadedDocs[i].status === "uploading") {
            _uploadedDocs[i].doc_id = serverDoc.doc_id;
            _uploadedDocs[i].status = serverDoc.status || "parsed";
            _uploadedDocs[i].pages = serverDoc.pages || null;
            _uploadedDocs[i].size_bytes = serverDoc.size_bytes || file.size;
            _uploadedDocs[i].content_preview = serverDoc.content_preview || null;
            _uploadedDocs[i]._localFile = null;
            break;
          }
        }
        _renderFileChips();
        showToast(esc(file.name) + " uploaded successfully", "info");
      } else {
        _markUploadError(file.name, "No document returned");
      }
    } else {
      var errMsg = "Upload failed (" + xhr.status + ")";
      try {
        var errResp = JSON.parse(xhr.responseText);
        if (errResp.error) errMsg = errResp.error;
      } catch (e) { /* use default errMsg */ }
      _markUploadError(file.name, errMsg);
    }
  });

  xhr.addEventListener("error", function() {
    _markUploadError(file.name, "Network error during upload");
  });

  xhr.addEventListener("timeout", function() {
    _markUploadError(file.name, "Upload timed out");
  });

  /* 5-minute timeout for large files */
  xhr.timeout = 300000;
  xhr.send(formData);
}

/* =====================================================================
   Upload Status Helpers
   ===================================================================== */
function _markUploadError(filename, errorMsg) {
  for (var i = 0; i < _uploadedDocs.length; i++) {
    if (_uploadedDocs[i].filename === filename && _uploadedDocs[i].status === "uploading") {
      _uploadedDocs[i].status = "error";
      _uploadedDocs[i]._errorMsg = errorMsg;
      _uploadedDocs[i]._localFile = null;
      break;
    }
  }
  _renderFileChips();
  showToast("Failed to upload " + filename + ": " + errorMsg, "error");
}

function _updateChipProgress(filename, pct) {
  var chip = document.querySelector('[data-doc-filename="' + CSS.escape(filename) + '"]');
  if (!chip) return;
  var sizeEl = chip.querySelector(".doc-chip-size");
  if (sizeEl && pct < 100) {
    sizeEl.textContent = pct + "%";
  }
}

/* =====================================================================
   Rendering — File Chips
   ===================================================================== */
function _renderFileChips() {
  if (!_fileListEl) return;

  if (_uploadedDocs.length === 0) {
    _fileListEl.innerHTML = "";
    return;
  }

  var html = "";
  for (var i = 0; i < _uploadedDocs.length; i++) {
    var doc = _uploadedDocs[i];
    var statusHtml = _buildStatusIndicator(doc.status);
    var sizeText = _formatFileSize(doc.size_bytes);
    var pagesText = (doc.pages && doc.pages > 0) ? doc.pages + "p" : "";
    var typeIcon = _getFileTypeIcon(doc.filename);
    var escapedName = esc(doc.filename);
    var deleteTitle = "Remove " + escapedName;

    html += '<div class="doc-file-chip" data-doc-filename="' + esc(doc.filename) + '"'
          + ' title="' + escapedName + (doc.content_preview ? "\n\n" + esc(doc.content_preview.substring(0, 200)) : "") + '">'
          + typeIcon
          + '<span class="doc-chip-name">' + escapedName + '</span>'
          + '<span class="doc-chip-size">' + esc(sizeText) + '</span>';

    if (pagesText) {
      html += '<span class="doc-chip-pages">' + esc(pagesText) + '</span>';
    }

    html += statusHtml;
    html += '<button class="doc-chip-delete" onclick="_removeDocument(' + i + ')" title="' + deleteTitle + '" aria-label="' + deleteTitle + '">&times;</button>';
    html += '</div>';
  }

  _fileListEl.innerHTML = html;
}

function _buildStatusIndicator(status) {
  switch (status) {
    case "uploading":
      return '<span class="doc-chip-status"><span class="doc-chip-spinner"></span></span>';
    case "parsed":
      return '<span class="doc-chip-status"><span class="doc-chip-check">&#10003;</span></span>';
    case "error":
      return '<span class="doc-chip-status"><span class="doc-chip-error">&#10007;</span></span>';
    default:
      return '<span class="doc-chip-status"><span class="doc-chip-spinner"></span></span>';
  }
}

function _updateZoneState() {
  if (!_uploadZoneEl) return;
  if (_uploadedDocs.length > 0) {
    _uploadZoneEl.classList.add("has-files");
  } else {
    _uploadZoneEl.classList.remove("has-files");
  }
}

/* =====================================================================
   Document Removal (Local + Server)
   ===================================================================== */
function _removeDocument(idx) {
  if (idx < 0 || idx >= _uploadedDocs.length) return;

  var doc = _uploadedDocs[idx];
  var docId = doc.doc_id;
  var filename = doc.filename;

  /* Remove from local array immediately for responsive UI */
  _uploadedDocs.splice(idx, 1);
  _renderFileChips();
  _updateZoneState();

  /* If the document was successfully uploaded (has doc_id), delete from server */
  if (docId) {
    fetch("/api/documents/" + encodeURIComponent(docId), {
      method: "DELETE"
    }).then(function(r) {
      if (r.ok) {
        showToast(esc(filename) + " removed", "info");
      } else {
        showToast("Server could not delete " + esc(filename), "warning");
      }
    }).catch(function() {
      showToast("Network error removing " + esc(filename), "warning");
    });
  }
}

/* =====================================================================
   Load Existing Documents from Server
   ===================================================================== */
function _loadExistingDocuments() {
  fetch("/api/documents/list")
    .then(function(r) {
      if (!r.ok) return null;
      return r.json();
    })
    .then(function(data) {
      if (!data || !data.documents || data.documents.length === 0) return;

      /* Merge with local state, avoiding duplicates */
      for (var i = 0; i < data.documents.length; i++) {
        var serverDoc = data.documents[i];
        var exists = false;
        for (var j = 0; j < _uploadedDocs.length; j++) {
          if (_uploadedDocs[j].doc_id === serverDoc.doc_id) {
            exists = true;
            break;
          }
        }
        if (!exists) {
          _uploadedDocs.push({
            doc_id: serverDoc.doc_id,
            filename: serverDoc.filename,
            size_bytes: serverDoc.size_bytes,
            status: serverDoc.status || "parsed",
            pages: serverDoc.pages || null,
            content_preview: null,
            _localFile: null
          });
        }
      }

      _renderFileChips();
      _updateZoneState();
    })
    .catch(function() {
      /* Silent — the endpoint may not exist yet */
    });
}

/* =====================================================================
   Public API
   ===================================================================== */

/**
 * Returns an array of doc_id strings for all successfully uploaded documents.
 * Used by the pipeline to access uploaded document IDs when submitting research.
 */
function getUploadedDocumentIds() {
  var ids = [];
  for (var i = 0; i < _uploadedDocs.length; i++) {
    if (_uploadedDocs[i].doc_id && _uploadedDocs[i].status === "parsed") {
      ids.push(_uploadedDocs[i].doc_id);
    }
  }
  return ids;
}

/**
 * Returns the full array of uploaded document metadata.
 */
function getUploadedDocuments() {
  return _uploadedDocs.slice();
}

/**
 * Clears all uploaded documents (local state only, no server delete).
 */
function clearUploadedDocuments() {
  _uploadedDocs = [];
  _renderFileChips();
  _updateZoneState();
}

/* =====================================================================
   Initialization — runs when the script loads
   ===================================================================== */
(function _initDocumentUpload() {
  /* Wait for the DOM to be ready (script is loaded at bottom of body, so
     the landing page elements should already exist). Use a small
     requestAnimationFrame to ensure the layout has settled. */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function() {
      requestAnimationFrame(function() {
        _buildUploadZone();
        _loadExistingDocuments();
      });
    });
  } else {
    requestAnimationFrame(function() {
      _buildUploadZone();
      _loadExistingDocuments();
    });
  }
})();
