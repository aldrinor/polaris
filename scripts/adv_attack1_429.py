#!/usr/bin/env python3
"""ATTACK 1 — 429 RENDERED AS "NO COPY".

Force every backend to return HTTP 429. Run the REAL fetchers. Does anything conclude that no free
copy exists? It must say BACKEND_FAILED.

Nothing here is mocked except the SOCKET. deep_fetch.main() and wp_fetch.main() are the real ones.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

CALLS: list[str] = []


def throttled(req, *a, **k):
    url = req.full_url if hasattr(req, 'full_url') else str(req)
    CALLS.append(url)
    raise urllib.error.HTTPError(url, 429, 'Too Many Requests', {}, io.BytesIO(b'rate limited'))


# A corpus of ONE paper that we KNOW has a free copy (Autor/Levy/Murnane = NBER WP 8337).
# Ground truth: A FREE COPY EXISTS. Any conclusion of "no copy" is therefore FALSE.
ROW = {
    'doi': '10.1162/003355303322552801',
    'title': 'The Skill Content of Recent Technological Change: An Empirical Exploration',
    'authors': ['Autor', 'Levy', 'Murnane'],
    'year': 2003,
    'venue': 'The Quarterly Journal of Economics',
    'citations': 4743,
    'attribution_short': 'Autor et al. (2003), QJE',
    'content_status': 'CITATION_ONLY',
}

print('=' * 96)
print('ATTACK 1 — EVERY BACKEND RETURNS HTTP 429. GROUND TRUTH: A FREE COPY EXISTS (NBER WP 8337).')
print('=' * 96)

tmp = Path(tempfile.mkdtemp())

# ---------------------------------------------------------------------------- deep_fetch
corpus_p = tmp / 'c1.json'
corpus_p.write_text(json.dumps([dict(ROW)]))
import deep_fetch

deep_fetch.CORPUS = corpus_p
_real_open = urllib.request.urlopen
urllib.request.urlopen = throttled
try:
    print('\n--- deep_fetch.main() under HTTP 429 ---')
    deep_fetch.main()
finally:
    urllib.request.urlopen = _real_open

after = json.loads(corpus_p.read_text())[0]
print(f"\n  backend calls made : {len(CALLS)}  (all 429)")
print(f"  content_status now : {after['content_status']}")
print(f"  any BACKEND_FAILED marker on the row? {[k for k in after if 'fail' in k.lower() or 'error' in k.lower()] or 'NONE'}")

# ---------------------------------------------------------------------------- wp_fetch
CALLS.clear()
corpus_p2 = tmp / 'c2.json'
corpus_p2.write_text(json.dumps([dict(ROW)]))
import wp_fetch

wp_fetch.CORPUS = corpus_p2
deep_fetch.CORPUS = corpus_p2
urllib.request.urlopen = throttled
try:
    print('\n--- wp_fetch.main() under HTTP 429 (it has backoff; ground truth unchanged) ---')
    wp_fetch.main()
finally:
    urllib.request.urlopen = _real_open

after2 = json.loads(corpus_p2.read_text())[0]
print(f"\n  backend calls made : {len(CALLS)}  (all 429)")
print(f"  content_status now : {after2['content_status']}")
print(f"  any BACKEND_FAILED marker on the row? {[k for k in after2 if 'fail' in k.lower() or 'error' in k.lower()] or 'NONE'}")
