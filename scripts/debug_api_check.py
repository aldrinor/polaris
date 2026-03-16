"""Check if source-preview API works with the evidence IDs from result API."""
import os
import requests

URL = os.environ.get("POLARIS_URL", "http://localhost:8765")

# Get result
r = requests.get(f"{URL}/api/research/result/SHOWME_TEST_003")
data = r.json()
bib = data.get("bibliography", [])
print(f"Bibliography: {len(bib)} entries")

for i, b in enumerate(bib[:5]):
    eids = b.get("evidence_ids", [])
    print(f"\n[{i+1}] {b.get('title', '?')[:50]}")
    print(f"    evidence_ids: {eids[:3]}")

    for eid in eids[:2]:
        r2 = requests.get(f"{URL}/api/research/source-preview/SHOWME_TEST_003/{eid}")
        if r2.ok:
            preview = r2.json()
            qt = preview.get("quote_text", "")
            print(f"    eid={eid}: quote_len={len(qt)} quote='{qt[:80]}...'")
        else:
            print(f"    eid={eid}: HTTP {r2.status_code}")
