#!/usr/bin/env python3
"""ENRICH + FILTER the bibliography via Crossref — the "deep source" half of the SOTA plan.

THE PROBLEM (measured by scripts/corpus_audit.py):
  Only 4 of our 105 bibliography entries carry AUTHOR NAMES. Only 12 are confirmed journal articles.
  So the highest-value lever we found — writing "Acemoglu and Restrepo (2019, Journal of Economic
  Perspectives)" into the PROSE, which survives RACE's cleaner while [n] markers are deleted — is
  currently impossible: we have the metadata for FOUR sources.

  But this is mostly a METADATA failure, not a SOURCE failure: ~40 entries carry a DOI (or a DOI
  recoverable from the URL). Crossref will return authors, venue, year, and the publication TYPE for
  each one, for free.

THIS SCRIPT:
  1. Extracts a DOI for every entry (stored field, or parsed out of the URL).
  2. Looks each up on Crossref (api.crossref.org — no key, polite pool via mailto).
  3. Writes back: authors, venue (container-title), year, type, is-referenced-by-count.
  4. CLASSIFIES: `type == "journal-article"` is the ONLY thing the task's instruction accepts
     ("only cites high-quality, English-language journal articles"). posted-content (preprints),
     report, proceedings-article, book-chapter => NOT eligible.
  5. Emits the ATTRIBUTABLE JOURNAL SET — the sources we can safely NAME in the prose.

FABRICATION SAFETY: every field written back comes verbatim from the Crossref record for that DOI.
Nothing is guessed. An entry with no DOI is left untouched and marked unattributable — never invented.

Usage:
  python scripts/enrich_bibliography.py --bib outputs/rank10_sections_compose/bibliography.json \
      --out outputs/bibliography_enriched.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

DOI_RE = re.compile(r'(10\.\d{4,9}/[^\s?#"<>]+)')
MAILTO = 'polaris@research.local'   # Crossref polite pool

# Only these Crossref types are "journal articles" for the purposes of the task instruction.
ELIGIBLE_TYPES = {'journal-article'}


def extract_doi(e: dict) -> str:
    d = (e.get('doi') or '').strip()
    if d:
        m = DOI_RE.search(d)
        if m:
            return m.group(1).rstrip('.,;)')
    for field in ('url', 'source_title', 'statement'):
        m = DOI_RE.search(str(e.get(field) or ''))
        if m:
            return m.group(1).rstrip('.,;)')
    return ''


def crossref(doi: str, timeout: float = 12.0) -> dict | None:
    url = f'https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}'
    req = urllib.request.Request(url, headers={'User-Agent': f'POLARIS/1.0 (mailto:{MAILTO})'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get('message')
    except Exception:
        return None


def surnames(msg: dict) -> list[str]:
    out = []
    for a in (msg.get('author') or []):
        fam = (a.get('family') or '').strip()
        if fam:
            out.append(fam)
        elif a.get('name'):
            out.append(a['name'].strip())
    return out


def year_of(msg: dict) -> int | None:
    for k in ('published-print', 'published-online', 'issued', 'created'):
        parts = ((msg.get(k) or {}).get('date-parts') or [[None]])[0]
        if parts and parts[0]:
            return int(parts[0])
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--bib', default='outputs/rank10_sections_compose/bibliography.json')
    ap.add_argument('--out', default='outputs/bibliography_enriched.json')
    ap.add_argument('--sleep', type=float, default=0.12)
    a = ap.parse_args()

    bib = json.loads(Path(a.bib).read_text())
    stats = Counter()
    enriched = []

    for i, e in enumerate(bib, 1):
        doi = extract_doi(e)
        rec = dict(e)
        rec['cr_doi'] = doi
        if not doi:
            rec['cr_status'] = 'NO_DOI'
            rec['eligible_journal'] = False
            rec['attributable'] = False
            stats['NO_DOI'] += 1
            enriched.append(rec)
            print(f"  [{i:>3}/{len(bib)}] NO_DOI      {(e.get('source_title') or '')[:58]}")
            continue

        msg = crossref(doi)
        time.sleep(a.sleep)
        if not msg:
            rec['cr_status'] = 'CROSSREF_MISS'
            rec['eligible_journal'] = False
            rec['attributable'] = False
            stats['CROSSREF_MISS'] += 1
            enriched.append(rec)
            print(f"  [{i:>3}/{len(bib)}] MISS        {doi[:40]}")
            continue

        au = surnames(msg)
        venue = (msg.get('container-title') or [''])[0]
        yr = year_of(msg)
        typ = msg.get('type') or ''
        rec.update({
            'cr_status': 'OK',
            'cr_authors': au,
            'cr_venue': venue,
            'cr_year': yr,
            'cr_type': typ,
            'cr_title': (msg.get('title') or [''])[0],
            'cr_citations': msg.get('is-referenced-by-count'),
        })
        eligible = (typ in ELIGIBLE_TYPES) and bool(venue) and bool(au)
        rec['eligible_journal'] = eligible
        rec['attributable'] = bool(au and yr and venue)
        stats[typ or 'unknown-type'] += 1
        stats['ELIGIBLE' if eligible else 'INELIGIBLE'] += 1
        flag = 'JOURNAL ' if eligible else 'not-jrnl'
        print(f"  [{i:>3}/{len(bib)}] {flag} {typ:<20.20} {(au[0] if au else '?'):<14.14} {venue[:38]}")
        enriched.append(rec)

    Path(a.out).write_text(json.dumps(enriched, indent=1))

    n = len(bib)
    elig = [r for r in enriched if r.get('eligible_journal')]
    attr = [r for r in enriched if r.get('attributable')]
    print("\n" + "=" * 78)
    print("=== ENRICHMENT RESULT ===")
    print(f"  entries                                  : {n}")
    print(f"  Crossref hit                             : {stats['ELIGIBLE'] + stats['INELIGIBLE']}")
    print(f"  no DOI at all                            : {stats['NO_DOI']}")
    print(f"  Crossref miss                            : {stats['CROSSREF_MISS']}")
    print(f"\n  ** ELIGIBLE JOURNAL ARTICLES             : {len(elig)}  ({100*len(elig)/n:.0f}%) **")
    print(f"  ** ATTRIBUTABLE (author+year+venue)      : {len(attr)}  <- can be NAMED in the prose **")
    print("\n=== Crossref publication types found ===")
    for t, c in stats.most_common():
        if t not in ('ELIGIBLE', 'INELIGIBLE', 'NO_DOI', 'CROSSREF_MISS'):
            mark = ' <= ELIGIBLE' if t in ELIGIBLE_TYPES else ''
            print(f"  {c:3d}  {t}{mark}")
    print("\n=== THE ATTRIBUTABLE JOURNAL SET (what we can safely write into the prose) ===")
    for r in elig[:25]:
        au = r['cr_authors']
        who = au[0] if len(au) == 1 else (f"{au[0]} and {au[1]}" if len(au) == 2 else f"{au[0]} et al.")
        print(f"  [{r['num']:>3}] {who} ({r['cr_year']}), {r['cr_venue'][:52]}")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
