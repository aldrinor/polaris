() => {
    var result = {};
    result.viewMode = typeof _currentViewMode !== "undefined" ? _currentViewMode : "unknown";
    result.wsPhase = typeof _wsPhase !== "undefined" ? _wsPhase : "unknown";
    result.pipelineActive = typeof state !== "undefined" ? state.pipelineActive : false;
    result.pipelineComplete = typeof state !== "undefined" ? state.pipelineComplete : false;
    result.eventCount = typeof state !== "undefined" ? state.eventCount : 0;
    result.evidence = typeof state !== "undefined" ? (state.evidence || 0) : 0;
    result.sources = typeof state !== "undefined" && state.sources ? state.sources.size : 0;
    result.connected = typeof state !== "undefined" ? state.connected : false;

    result.threadVisible = !!(document.getElementById("ws-thread") && document.getElementById("ws-thread").style.display !== "none");
    result.progressBlock = !!document.getElementById("ws-active-progress");
    result.metricsRow = !!document.getElementById("ws-progress-metrics");
    result.discoveryCard = !!document.getElementById("ws-source-discovery");
    result.timerText = (document.getElementById("ws-progress-time") || {}).textContent || "";
    result.activeLabel = (document.getElementById("ws-progress-active-text") || {}).textContent || "";

    var island = document.getElementById("dynamic-island-text") || document.querySelector(".dynamic-island-label");
    result.dynamicIsland = island ? island.textContent : "";

    var feed = document.getElementById("ws-task-feed");
    result.feedItems = feed ? feed.querySelectorAll(".ws-task-item").length : 0;
    result.phaseDividers = feed ? feed.querySelectorAll(".ws-task-phase-divider").length : 0;

    result.pmSources = (document.getElementById("ws-pm-sources") || {}).textContent || "?";
    result.pmEvidence = (document.getElementById("ws-pm-evidence") || {}).textContent || "?";
    result.pmFaith = (document.getElementById("ws-pm-faith") || {}).textContent || "?";

    var disc = document.getElementById("ws-source-discovery-list");
    result.discoverySources = disc ? disc.querySelectorAll(".ws-sd-item").length : 0;

    result.hasSearchedZero = (feed ? feed.textContent : "").includes("Searched 0 sources");

    return result;
}
