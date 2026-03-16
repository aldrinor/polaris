"""Check what the snapshot and research status APIs return."""
import os
import json
import requests

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

# Snapshot
r = requests.get(f"{URL}/api/snapshot")
snap = r.json()
print("=== /api/snapshot ===")
print(f"  Keys: {list(snap.keys())}")
events_by_type = snap.get("events_by_type", {})
print(f"  events_by_type keys: {list(events_by_type.keys())}")
total = sum(len(v) for v in events_by_type.values())
print(f"  Total events: {total}")
print(f"  total_event_count: {snap.get('total_event_count')}")
print(f"  pipeline_running: {snap.get('pipeline_running')}")
print(f"  vector_id: {snap.get('vector_id')}")
if events_by_type:
    for t, evts in events_by_type.items():
        print(f"    {t}: {len(evts)} events")

# Research status
r2 = requests.get(f"{URL}/api/research/status")
status = r2.json()
print(f"\n=== /api/research/status ===")
print(f"  {json.dumps(status, indent=2)[:500]}")

# Check if there's a result
vid = snap.get("vector_id") or status.get("vector_id")
if vid:
    r3 = requests.get(f"{URL}/api/research/result/{vid}")
    if r3.ok:
        result = r3.json()
        print(f"\n=== /api/research/result/{vid} ===")
        print(f"  Keys: {list(result.keys())}")
        print(f"  bibliography count: {len(result.get('bibliography', []))}")
        print(f"  has final_report: {bool(result.get('final_report'))}")
        print(f"  report length: {len(result.get('final_report', ''))}")
    else:
        print(f"\n  Result API: {r3.status_code}")
