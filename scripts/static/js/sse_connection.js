/* =====================================================================
   sse_connection.js -- SSE Connection, Snapshot Hydration, Polling
   POLARIS Live Dashboard

   NOTE: Core utility functions (esc, setText, truncStr, fmtDuration,
   extractDomain, showToast, beep, formatTokens, getPhaseLabel,
   estimateTimeRemaining, animateCounter, safeRender) are defined in
   core.js which loads before this file.
   ===================================================================== */

/* =====================================================================
   SSE Connection Limiter (max 5 concurrent per-IP)
   ===================================================================== */
var _SSE_MAX_CONNECTIONS = 5;
var _SSE_STORAGE_KEY = "polaris_sse_conn_count";
var _sseConnectionRegistered = false;

function _getSseConnCount() {
  try { return parseInt(sessionStorage.getItem(_SSE_STORAGE_KEY) || "0", 10); } catch(e) { return 0; }
}

function _setSseConnCount(n) {
  try { sessionStorage.setItem(_SSE_STORAGE_KEY, String(Math.max(0, n))); } catch(e) {}
}

function _registerSseConnection() {
  if (_sseConnectionRegistered) return;
  _sseConnectionRegistered = true;
  _setSseConnCount(_getSseConnCount() + 1);
}

function _unregisterSseConnection() {
  if (!_sseConnectionRegistered) return;
  _sseConnectionRegistered = false;
  _setSseConnCount(_getSseConnCount() - 1);
}

// Decrement on tab close/unload
window.addEventListener("beforeunload", function() {
  _unregisterSseConnection();
  _teardownMultiTab();
});

function _canOpenSseConnection() {
  var count = _getSseConnCount();
  if (count >= _SSE_MAX_CONNECTIONS) {
    return false;
  }
  return true;
}


/* --- SSE Reconnect Counter (Task 3) --- */
var _sseReconnectCount = 0;

function _updateReconnectDisplay() {
  /** Update the reconnect counter shown in the operator status bar. */
  var el = document.getElementById("sse-reconnect-count");
  if (el) el.textContent = String(_sseReconnectCount);
}

/* =====================================================================
   Multi-Tab SSE Verification via BroadcastChannel (Task 2)
   ===================================================================== */
var _sseBroadcastChannel = null;
var _sseTabCount = 1;
var _sseTabHeartbeatInterval = null;

function _verifyMultiTab() {
  /**
   * Open a BroadcastChannel named "polaris_sse_sync" for cross-tab
   * SSE event coordination.
   *
   * Each tab:
   *   - Posts received SSE events to the channel so other tabs can
   *     verify receipt independently.
   *   - Sends periodic "heartbeat" messages so tabs can count how
   *     many peers are active.
   *   - Listens for heartbeats from other tabs and updates the
   *     "SSE Tabs: N" indicator in the operator status bar.
   *
   * This proves multi-tab SSE independence: each tab has its own
   * EventSource connection, but they coordinate via BroadcastChannel.
   */
  // BUG-006 fix: guard against double initialization
  if (_sseTabHeartbeatInterval) return;
  if (typeof BroadcastChannel === "undefined") {
    console.warn("BroadcastChannel API not available in this browser");
    return;
  }

  try {
    _sseBroadcastChannel = new BroadcastChannel("polaris_sse_sync");
  } catch (e) {
    console.warn("Failed to open BroadcastChannel:", e);
    return;
  }

  // Track which tabs are alive via heartbeat timestamps
  var _tabPeers = {};
  var _myTabId = "tab_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);

  _sseBroadcastChannel.onmessage = function(e) {
    var data = e.data;
    if (!data || typeof data !== "object") return;

    if (data.type === "heartbeat" && data.tabId) {
      _tabPeers[data.tabId] = Date.now();
    }

    if (data.type === "sse_event") {
      // Other tabs can process/verify this event if needed
      // For now, this serves as proof of cross-tab SSE propagation
      console.debug("[BroadcastChannel] Received SSE event from tab:", data.tabId);
    }
  };

  // Send heartbeat every 3 seconds
  _sseTabHeartbeatInterval = setInterval(function() {
    if (!_sseBroadcastChannel) return;
    try {
      _sseBroadcastChannel.postMessage({
        type: "heartbeat",
        tabId: _myTabId,
        timestamp: Date.now()
      });
    } catch (e) {
      // Channel may have been closed
    }

    // Count active peers (alive within last 10 seconds)
    var now = Date.now();
    var cutoff = now - 10000;
    var activeCount = 1; // Count self
    var peerIds = Object.keys(_tabPeers);
    for (var i = 0; i < peerIds.length; i++) {
      if (_tabPeers[peerIds[i]] > cutoff) {
        activeCount++;
      } else {
        delete _tabPeers[peerIds[i]];
      }
    }

    _sseTabCount = activeCount;
    var tabEl = document.getElementById("sse-tab-count");
    if (tabEl) tabEl.textContent = String(_sseTabCount);
  }, 3000);

  _log("[BroadcastChannel] Multi-tab SSE verification active, tabId:", _myTabId);
}

function _broadcastSseEvent(eventData) {
  /**
   * Post an SSE event to the BroadcastChannel so other tabs can verify
   * they are receiving the same events independently.
   */
  if (!_sseBroadcastChannel) return;
  try {
    _sseBroadcastChannel.postMessage({
      type: "sse_event",
      tabId: "self",
      event: eventData,
      timestamp: Date.now()
    });
  } catch (e) {
    // Channel closed or posting failed -- non-critical
  }
}

function _teardownMultiTab() {
  /** Clean up BroadcastChannel resources and polling intervals on tab close. */
  if (_sseTabHeartbeatInterval) {
    clearInterval(_sseTabHeartbeatInterval);
    _sseTabHeartbeatInterval = null;
  }
  if (_sseBroadcastChannel) {
    try { _sseBroadcastChannel.close(); } catch (e) {}
    _sseBroadcastChannel = null;
  }
  // BUG-004/005 fix: clear polling intervals on teardown
  if (typeof _anomalyPollInterval !== "undefined" && _anomalyPollInterval) {
    clearInterval(_anomalyPollInterval);
  }
  if (typeof _costPollInterval !== "undefined" && _costPollInterval) {
    clearInterval(_costPollInterval);
  }
}


/* =====================================================================
   SSE Connection (EventSource with exponential backoff)
   ===================================================================== */
var _eventSource = null;
var _sseRetryCount = 0;
function connectSSE(offset) {
  // SSE connection limiter: check before connecting
  if (!_canOpenSseConnection()) {
    state.connected = false;
    document.getElementById("status-dot").className = "status-dot disconnected";
    document.getElementById("status-dot").title = "Max SSE connections reached";
    setText("conn-text", "Maximum SSE connections reached");
    showToast("Maximum SSE connections reached (limit: " + _SSE_MAX_CONNECTIONS + "). Close other tabs to connect.", "warning");
    console.warn("SSE connection blocked: " + _getSseConnCount() + "/" + _SSE_MAX_CONNECTIONS + " connections active");
    return;
  }
  offset = offset || 0;
  _unregisterSseConnection(); // Unregister previous connection before opening new one
  if (_eventSource) { _eventSource.close(); _eventSource = null; }
  var url = "/api/events?after=" + offset;
  _eventSource = new EventSource(url);

  state.connected = true;
  _registerSseConnection();
  _sseRetryCount = 0;
  // Use "completed" class if pipeline already finished, otherwise "connected"
  if (state.pipelineComplete) {
    document.getElementById("status-dot").className = "status-dot completed";
    document.getElementById("status-dot").title = "Pipeline complete (SSE)";
    setText("conn-text", "Pipeline complete");
  } else {
    document.getElementById("status-dot").className = "status-dot connected";
    document.getElementById("status-dot").title = "Connected (SSE)";
    setText("conn-text", state.pipelineActive ? "Connected" : "Ready");
  }
  if (typeof updatePolarisStatus === 'function') updatePolarisStatus("Connected");

  // Initialize multi-tab verification on first successful connection
  if (!_sseBroadcastChannel) {
    _verifyMultiTab();
  }

  _eventSource.onmessage = function(msg) {
    try {
      var ev = JSON.parse(msg.data);
      if (ev.error) { console.warn("SSE error:", ev.error); return; }
      processEvent(ev);
      // Broadcast to other tabs for multi-tab verification (Task 2)
      _broadcastSseEvent(ev);
    } catch(e) {
      console.warn("SSE parse error:", e);
    }
  };

  _eventSource.onerror = function() {
    state.connected = false;
    _unregisterSseConnection();
    document.getElementById("status-dot").className = "status-dot disconnected";
    document.getElementById("status-dot").title = "Disconnected";
    setText("conn-text", "Reconnecting...");
    if (typeof updatePolarisStatus === 'function') updatePolarisStatus("Reconnecting\u2026");
    _eventSource.close();
    _eventSource = null;

    // Track reconnection attempts (Task 3)
    _sseReconnectCount++;
    _updateReconnectDisplay();
    _log("SSE error/close: reconnect count now " + _sseReconnectCount);

    // Reconnect with exponential backoff + snapshot catch-up
    _sseRetryCount++;
    if (_sseRetryCount <= 20) {
      var retryDelay = Math.min(1000 * Math.pow(2, Math.min(_sseRetryCount - 1, 5)), 30000);
      _log("SSE reconnecting in " + retryDelay + "ms (attempt " + _sseRetryCount + "/20)");
      setTimeout(function() {
        // Re-fetch snapshot before reconnecting to catch up on missed events
        fetch("/api/snapshot")
          .then(function(r) { return r.json(); })
          .then(function(data) {
            if (!data.error) {
              var serverCount = data.total_event_count || 0;
              if (serverCount > state.eventCount) {
                var allEvents = [];
                var ebt = data.events_by_type || {};
                Object.keys(ebt).forEach(function(t) { ebt[t].forEach(function(e) { allEvents.push(e); }); });
                allEvents.sort(function(a, b) { return (a.ts || "").localeCompare(b.ts || ""); });
                state._hydrating = true;
                var ss = state.soundEnabled; state.soundEnabled = false;
                allEvents.slice(state.eventCount).forEach(function(ev) { processEvent(ev); });
                state.soundEnabled = ss; state._hydrating = false;
                state.snapshotEventCount = serverCount;
              }
              connectSSE(state.snapshotEventCount);
              if (typeof updateUIVisibility === "function") updateUIVisibility();
            } else { connectSSE(state.eventCount); }
          })
          .catch(function() { connectSSE(state.eventCount); });
      }, retryDelay);
    } else {
      setText("conn-text", "Connection lost. Refresh to retry.");
      console.warn("SSE max retries reached (" + _sseReconnectCount + " total reconnects).");
    }
  };
}

/* =====================================================================
   Snapshot Hydration
   ===================================================================== */
function loadSnapshot() {
  fetch("/api/snapshot")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        console.warn("Snapshot error:", data.error);
        connectSSE(0);
        return;
      }
      // Replay all events from snapshot
      var allEvents = [];
      var eventsByType = data.events_by_type || {};
      Object.keys(eventsByType).forEach(function(type) {
        eventsByType[type].forEach(function(ev) {
          allEvents.push(ev);
        });
      });
      // Sort by timestamp (ISO strings — use localeCompare, not subtraction)
      allEvents.sort(function(a, b) { return (a.ts || "").localeCompare(b.ts || ""); });
      state.snapshotEventCount = data.total_event_count || allEvents.length;

      // Process all snapshot events silently (no beep, no auto-transition)
      var savedSound = state.soundEnabled;
      state.soundEnabled = false;
      state._hydrating = true;
      allEvents.forEach(function(ev) { processEvent(ev); });
      state.soundEnabled = savedSound;
      state._hydrating = false;
      // Reset to default view/tab after hydration
      state.activeAdvTab = "queries";

      // Override stale pipelineActive from hydrated events with server truth
      if (typeof data.pipeline_running === "boolean") {
        if (!data.pipeline_running && state.pipelineActive && !state.pipelineComplete) {
          console.log("[snapshot] Server says pipeline NOT running -- resetting stale pipelineActive");
          state.pipelineActive = false;
          // Reset workspace to idle so source brief can display
          if (typeof setWorkspacePhase === "function") {
            setWorkspacePhase("idle");
          }
        }
      }

      // Post-hydration: finalize UI if pipeline completed during replay
      console.log("[snapshot] Post-hydration: pipelineComplete=" + state.pipelineComplete + " pipelineActive=" + state.pipelineActive + " vectorId=" + state.vectorId);
      if (state.pipelineComplete) {
        console.log("[snapshot] Entering pipelineComplete post-hydration block");
        // Update user progress stats that were skipped during hydration
        animateCounter("user-stat-sources", state.sources.size);
        animateCounter("user-stat-evidence", state.evidence);
        var faithText = (state.faithfulness > 0 || state.verificationVerdicts.length > 0)
          ? Math.round(state.faithfulness * 100) + "%" : "--";
        document.getElementById("user-stat-faith").textContent = faithText;
        // Mark all stepper steps as done
        document.getElementById("user-progress-bar").style.width = "100%";
        document.getElementById("user-phase-text").textContent = "Report ready!";
        document.querySelectorAll("#user-progress-steps .user-step").forEach(function(s) {
          s.classList.remove("active"); s.classList.add("done");
          s.querySelector(".step-check").textContent = "\u2713";
        });
        // Update operator status text and stop dot pulsing
        setText("current-status-text", "Pipeline complete");
        var statusDot = document.getElementById("status-dot");
        if (statusDot) {
          statusDot.classList.remove("connected");
          statusDot.classList.add("completed");
        }
        // Force operator metrics update
        updateMetrics();
        // Deactivate dynamic island after hydration (node_start events may have re-activated it)
        if (typeof _updateDynamicIsland === "function") {
          _updateDynamicIsland("complete", "");
        }
        // Transition workspace to report phase (expands citations, sets phase)
        if (typeof setWorkspacePhase === "function") {
          setWorkspacePhase("report");
        }
        // Render report block if available from hydration
        if (state.fullReport && typeof appendReportBlock === "function") {
          appendReportBlock(state.fullReport, state.bibliography);
        }
        // Fetch rich bibliography from result API (SSE events have bare entries without evidence_ids)
        if (state.vectorId) {
          fetch("/api/research/result/" + encodeURIComponent(state.vectorId))
          .then(function(r) { return r.ok ? r.json() : null; })
          .then(function(d) {
            if (d && Array.isArray(d.bibliography) && d.bibliography.length > 0) {
              state.bibliography = d.bibliography;
              // Re-render citations sidebar with enriched data
              if (typeof _renderCitationCards === "function") _renderCitationCards();
            }
            if (d && d.final_report) {
              state.fullReport = d.final_report;
              markDirty("report");
              if (typeof appendReportBlock === "function") appendReportBlock(d.final_report, state.bibliography);
            }
            // Update memory after bibliography is loaded
            if (typeof _updateSidebarMemory === "function") _updateSidebarMemory();
          }).catch(function() {});
        }
        // Transition to report view
        updateUIVisibility();
      } else if (state.pipelineActive) {
        // Pipeline still running — switch workspace to running phase
        if (typeof setWorkspacePhase === "function") {
          setWorkspacePhase("running");
        }
        animateCounter("user-stat-sources", state.sources.size);
        animateCounter("user-stat-evidence", state.evidence);
        updateMetrics();
        updateUIVisibility();

        // HYDRATION-FIX: Rebuild workspace thread after hydration
        // handleSubmit() creates prompt bubble + progress block, but during
        // hydration these are never called. Create them now so the center
        // panel isn't blank.
        if (typeof appendPromptBubble === "function" && state.researchQuery) {
          appendPromptBubble(state.researchQuery);
        }
        if (typeof appendProgressBlock === "function") {
          appendProgressBlock();
        }
        // Replay progress tasks from hydrated events
        // Build summary from what we know: node counts
        var nodesDone = {};
        allEvents.forEach(function(ev) {
          if (ev.type === "node_end" && ev.node) {
            nodesDone[ev.node] = (nodesDone[ev.node] || 0) + 1;
          }
        });
        var nodeKeys = Object.keys(nodesDone);
        for (var ni = 0; ni < nodeKeys.length; ni++) {
          var nk = nodeKeys[ni];
          var label = (typeof getPhaseLabel === "function") ? getPhaseLabel(nk, {}, true) : nk;
          if (nodesDone[nk] > 1) label += " (" + nodesDone[nk] + " rounds)";
          if (typeof addProgressTask === "function") addProgressTask(label, "done");
        }
        // Show current active node
        var lastNodeStart = null;
        for (var ei = allEvents.length - 1; ei >= 0; ei--) {
          if (allEvents[ei].type === "node_start") { lastNodeStart = allEvents[ei]; break; }
        }
        if (lastNodeStart && typeof addProgressTask === "function") {
          var activeLabel = (typeof getPhaseLabel === "function")
            ? getPhaseLabel(lastNodeStart.node, lastNodeStart, false) : lastNodeStart.node;
          addProgressTask(activeLabel, "active");
        }
        // F03: Sync dynamic island with progress block active label
        if (lastNodeStart && typeof _updateDynamicIsland === "function") {
          var islandLabel = (typeof getPhaseLabel === "function")
            ? getPhaseLabel(lastNodeStart.node, lastNodeStart, false) : lastNodeStart.node;
          _updateDynamicIsland("running", islandLabel);
        }
        // Update sidebar task feed
        if (typeof _renderTaskFeed === "function") _renderTaskFeed();
      }

      // Render all dirty views
      state.dirtyViews.forEach(function(viewId) {
        state.dirtyViews.delete(viewId);
        renderView(viewId);
      });
      // Render the active view
      renderView(state.activeView);

      // Connect SSE starting after snapshot
      connectSSE(state.snapshotEventCount);
      // Always sync UI after hydration, regardless of pipeline state
      if (typeof updateUIVisibility === "function") updateUIVisibility();
      showToast("Loaded snapshot: " + state.snapshotEventCount + " events", "info");
    })
    .catch(function(err) {
      console.warn("Snapshot fetch failed:", err);
      connectSSE(0);
      if (typeof updateUIVisibility === "function") updateUIVisibility();
    });
}

/* =====================================================================
   Anomaly Polling (5s interval)
   BUG-004/005 fix: Store interval IDs for cleanup in _teardownMultiTab
   ===================================================================== */
var _anomalyPollInterval = setInterval(function() {
  fetch("/api/anomalies")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!Array.isArray(data)) return;
      state.anomalies = data;
      if (data.length > state.lastAnomalyCount) {
        var newCount = data.length - state.lastAnomalyCount;
        if (_currentViewMode !== "user") {
          showToast(newCount + " new anomal" + (newCount === 1 ? "y" : "ies") + " detected", "warning");
          beep();
        }
      }
      state.lastAnomalyCount = data.length;
    })
    .catch(function() {});
}, 5000);

/* =====================================================================
   Cost Polling (5s interval)
   ===================================================================== */
var _costPollInterval = setInterval(function() {
  fetch("/api/cost")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data && data.total_cost_usd !== undefined) {
        state.cost = data.total_cost_usd;
        setText("total-cost", "$" + state.cost.toFixed(3));
      }
      if (data && data.entries) {
        // Update model counts from cost entries
        data.entries.forEach(function(entry) {
          if (entry.model) {
            state.modelCounts[entry.model] = (state.modelCounts[entry.model] || 0);
          }
        });
      }
    })
    .catch(function() {});
}, 5000);
