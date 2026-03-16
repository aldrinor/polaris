"""Monitor a running POLARIS pipeline — polls /api/snapshot every 30s."""
import json
import time
import urllib.request
from datetime import datetime

BASE = "http://localhost:8765"
INTERVAL = 30


def fetch_json(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 70)
    print("  POLARIS Pipeline Monitor — polling every %ds" % INTERVAL)
    print("=" * 70)

    prev_events = 0
    while True:
        now = datetime.now().strftime("%H:%M:%S")
        status = fetch_json(BASE + "/api/research/status")
        snap = fetch_json(BASE + "/api/snapshot")

        if "error" in snap and "error" in status:
            print("[%s] ERROR: Server unreachable" % now)
            time.sleep(INTERVAL)
            continue

        running = status.get("running", False)
        total_ev = snap.get("total_event_count", 0)
        new_ev = total_ev - prev_events
        prev_events = total_ev

        s = snap.get("stats", {})
        ec = s.get("event_counts", {})
        nd = s.get("node_durations_ms", {})

        # Determine current phase from last node_start
        ebt = snap.get("events_by_type", {})
        node_starts = ebt.get("node_start", [])
        current_node = node_starts[-1].get("node", "?") if node_starts else "?"
        node_ends = ebt.get("node_end", [])
        ended_nodes = set(e.get("node", "") for e in node_ends)

        # Evidence count
        evidence_count = s.get("total_evidence", 0)

        # Cost
        cost = s.get("total_cost_usd", 0)

        # Searches
        searches = ec.get("search_result", 0)

        # LLM calls
        llm_calls = ec.get("llm_call", 0)

        # Fetches
        fetches = ec.get("fetch", 0)

        # Verification verdicts
        verdicts = ec.get("verification_batch", 0)

        # STORM
        storm = ec.get("storm_transcript", 0)

        # Iteration
        iters = ec.get("iteration_decision", 0)

        # Node durations summary
        phase_times = []
        for node, ms in nd.items():
            phase_times.append("%s=%.0fs" % (node, ms / 1000))

        status_icon = "RUN" if running else "DONE"
        if not running and status.get("error"):
            status_icon = "ERR"

        print(
            "[%s] %s | events=%d (+%d) | node=%s | ev=%d | src=%d | "
            "llm=%d | fetch=%d | storm=%d | verify=%d | iter=%d | $%.4f"
            % (
                now, status_icon, total_ev, new_ev, current_node,
                evidence_count, searches, llm_calls, fetches,
                storm, verdicts, iters, cost,
            )
        )
        if phase_times:
            print("         phases: %s" % " | ".join(phase_times))

        if not running:
            result_path = status.get("result_path")
            error = status.get("error")
            if error:
                print("\n  PIPELINE ERROR: %s" % error)
            elif result_path:
                print("\n  PIPELINE COMPLETE — result: %s" % result_path)
            else:
                print("\n  PIPELINE FINISHED (no result path)")
            break

        time.sleep(INTERVAL)

    print("=" * 70)
    print("  Monitor stopped.")
    print("=" * 70)


if __name__ == "__main__":
    main()
