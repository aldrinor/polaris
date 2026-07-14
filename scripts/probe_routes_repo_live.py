#!/usr/bin/env python3
"""LIVE PROBES for routes_repo.py — CORE, OpenAIRE Graph v3, Zenodo, against REAL candidate DOIs.

    Sol V9 §9: "For every ladder step, report attempted, responded, candidate URLs, ... 401/403/429,
    and unresolved route failures."

This is not a unit test and it does not assert. It goes to the real network, on real DOIs drawn from
`outputs/acquisition_campaign/` — the no-known-OA candidates this lane exists to convert — and prints
what the three backends ACTUALLY DID. The one thing it will not do is turn a route failure into a
finding about the literature: a route that 401s is reported as a route that 401'd.

    python3 scripts/probe_routes_repo_live.py            # 12 candidate DOIs
    python3 scripts/probe_routes_repo_live.py -n 40      # more
    python3 scripts/probe_routes_repo_live.py --traps    # the three named silent failures, live
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import routes_repo as RR                                                        # noqa: E402
import source_router as SR                                                      # noqa: E402
from acquisition import Acquirer, BlobStore, ResolveContext                     # noqa: E402
from event_ledger import Ledger                                                 # noqa: E402

CAMPAIGN = ROOT / 'outputs' / 'acquisition_campaign'
OUT = ROOT / 'outputs' / 'routes_repo_probe'
ROUTES = ('core', 'openaire', 'zenodo')


def candidate_dois(n: int) -> list[dict]:
    """REAL candidates from the discovery campaign — every one of them with NO known OA URL, which is
    exactly the population Sol's 2,490-candidate forecast is about."""
    recs: list[dict] = []
    f = CAMPAIGN / 'frontier_2023_2025_FINAL.json'
    if f.exists():
        for r in json.loads(f.read_text()).get('records', []):
            if r.get('doi') and not r.get('oa_url'):
                recs.append({'doi': r['doi'], 'title': r.get('title', ''), 'year': r.get('year')})
    random.Random(72).shuffle(recs)
    return recs[:n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=12)
    ap.add_argument('--traps', action='store_true')
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    L = Ledger.load(OUT / 'probe_ledger.jsonl')
    acq = Acquirer('probe_routes_repo', ledger=L, blobs=BlobStore(OUT / 'blobs'))
    table = SR.load_table()

    print('═' * 100)
    print('PREFLIGHT — can each route run at all?  (Sol V9 §2: a rejected key marks the route '
          'UNAVAILABLE,\n            it NEVER concludes that content is absent)')
    print('═' * 100)
    pre = {}
    for rid in ROUTES:
        RR.reset_circuit()
        p = RR.preflight(acq, table, rid)
        pre[rid] = p
        print(f'\n  {rid:10s} {p.state}')
        print(f'  {"":10s} {p.basis}')

    if a.traps:
        return traps(acq, table)

    rows = candidate_dois(a.n)
    print('\n' + '═' * 100)
    print(f'LIVE RESOLUTION — {len(rows)} real no-known-OA candidates from the discovery campaign')
    print('═' * 100)

    tally: dict[str, Counter] = {r: Counter() for r in ROUTES}
    cand_urls: dict[str, int] = {r: 0 for r in ROUTES}
    rejects: list[dict] = []
    per_doi: list[dict] = []

    for i, rec in enumerate(rows, 1):
        doi = rec['doi']
        ctx = ResolveContext(work_id=doi, identifiers=(doi,), title=rec.get('title', ''),
                             contract_id='probe', permitted_expression_kinds=('journal_version',))
        print(f'\n[{i:2d}/{len(rows)}] {doi}')
        print(f'         {(rec.get("title") or "")[:88]}')
        line = {'doi': doi, 'routes': {}}
        for rid in ROUTES:
            r = RR.resolve(acq, table, rid, ctx, limit=5)
            tally[rid][r.state] += 1
            cand_urls[rid] += len(r.candidates)
            rejects.extend({**x, 'adapter': rid, 'doi': doi} for x in r.rejected)
            line['routes'][rid] = {'state': r.state, 'candidates': len(r.candidates),
                                   'records_seen': r.records_seen,
                                   'urls': [c.retrieval_url for c in r.candidates][:4]}
            mark = '·' if r.answered and not r.candidates else ('+' if r.candidates else '!')
            print(f'   {mark} {rid:9s} {r.state:14s} records={r.records_seen:2d} '
                  f'candidates={len(r.candidates)}')
            for c in r.candidates[:3]:
                o = r.candidate_obs.get(c.candidate_id, {})
                extra = ' '.join(f'{k}={v}' for k, v in o.items()
                                 if k in ('artifact_declaration', 'declares_article',
                                          'relation_to_asked_identifier', 'identifier_substitution',
                                          'inline_text_chars', 'file_bytes'))
                print(f'       -> [{c.media_hint:9s}] {c.retrieval_url[:78]}')
                if extra:
                    print(f'          {extra}')
        per_doi.append(line)

    print('\n' + '═' * 100)
    print('LADDER REPORT  (Sol V9 §9)')
    print('═' * 100)
    print(f'\n  {"route":10s} {"attempted":>9s} {"answered":>9s} {"auth_failed":>11s} {"throttled":>9s} '
          f'{"failed":>7s} {"cand.URLs":>9s}')
    for rid in ROUTES:
        t = tally[rid]
        print(f'  {rid:10s} {sum(t.values()):9d} {t[RR.ANSWERED]:9d} '
              f'{t[RR.AUTH_FAILED] + t[RR.UNAVAILABLE]:11d} {t[RR.ROUTE_THROTTLED]:9d} '
              f'{t[RR.BACKEND_FAILED] + t[RR.ROUTE_DENIED]:7d} {cand_urls[rid]:9d}')

    if rejects:
        print(f'\n  RECORDS REFUSED BY THE IDENTITY/RELATION GUARDS: {len(rejects)}')
        for x in rejects[:6]:
            print(f'    [{x["adapter"]}/{x.get("query_form")}] {(x.get("record_title") or "")[:56]}')
            print(f'       {x["why"][:110]}')

    unavailable = [r for r in ROUTES if not pre[r].answered]
    if unavailable:
        print(f'\n  ⚠ ROUTES THAT NEVER LOOKED: {unavailable}')
        print('    Their zero candidates are ZERO EVIDENCE — not evidence of zero. No absence statement')
        print('    about any DOI above may be made while these routes are in this state.')

    (OUT / 'probe_result.json').write_text(json.dumps(
        {'preflight': {r: {'state': pre[r].state, 'basis': pre[r].basis} for r in ROUTES},
         'tally': {r: dict(tally[r]) for r in ROUTES},
         'candidate_urls': cand_urls, 'per_doi': per_doi,
         'rejected': rejects}, indent=1))
    print(f'\n  written: {OUT / "probe_result.json"}')
    return 0


def traps(acq: Acquirer, table: SR.RouteTable) -> int:
    """The three silent failures Sol names, reproduced against the LIVE backends."""
    print('\n' + '═' * 100)
    print('TRAP 1 — ZENODO: a deposit that merely CITES the DOI must not become that DOI\'s document')
    print('═' * 100)
    doi = '10.1038/s41586-021-03819-2'          # AlphaFold, Nature 2021
    ctx = ResolveContext(work_id=doi, identifiers=(doi,), title='Highly accurate protein structure prediction')
    r = RR.resolve(acq, table, 'zenodo', ctx, limit=10)
    print(f'\n  zenodo state={r.state}  records_seen={r.records_seen}  candidates={len(r.candidates)}')
    print(f'  records REFUSED: {len(r.rejected)}')
    for x in r.rejected[:5]:
        print(f'    - {(x.get("record_title") or "")[:60]}')
        print(f'      {x["why"][:120]}')
    for c in r.candidates[:5]:
        o = r.candidate_obs.get(c.candidate_id, {})
        print(f'    + ADMITTED {c.retrieval_url[:70]}  relation='
              f'{o.get("relation_to_asked_identifier")}  declares_article={o.get("declares_article")}')

    print('\n' + '═' * 100)
    print('TRAP 2 — ZENODO: a CONCEPT DOI resolves to a DIFFERENT version DOI, with HTTP 200 and no warning')
    print('═' * 100)
    cdoi = '10.5281/zenodo.1215934'             # a CONCEPT doi
    ctx2 = ResolveContext(work_id=cdoi, identifiers=(cdoi,))
    r2 = RR.resolve(acq, table, 'zenodo', ctx2, limit=5)
    print(f'\n  zenodo state={r2.state}  candidates={len(r2.candidates)}')
    for c in r2.candidates[:3]:
        o = r2.candidate_obs.get(c.candidate_id, {})
        print(f'    asked for : {o.get("identifier_asked")}')
        print(f'    record IS : {o.get("identifier_the_record_carries")}   <- A DIFFERENT DOI')
        print(f'    recorded  : identifier_substitution={o.get("identifier_substitution")!r}')
        print(f'    file      : {c.retrieval_url[:70]}')
        break

    print('\n' + '═' * 100)
    print('TRAP 3 — OPENAIRE: `accessRight: OPEN` on a record whose URL is only a doi.org LANDING PAGE')
    print('═' * 100)
    ctx3 = ResolveContext(work_id=doi, identifiers=(doi,))
    r3 = RR.resolve(acq, table, 'openaire', ctx3, limit=5)
    print(f'\n  openaire state={r3.state}  candidates={len(r3.candidates)}')
    for c in r3.candidates:
        print(f'    [{c.media_hint:8s}] {c.retrieval_url[:72]}')
        print(f'              license_observation={c.license_observation!r} version_hint={c.version_hint!r}')
    print('\n  Every one of these is a CANDIDATE. Not one is a document: `media_hint=landing` on a')
    print('  doi.org URL is the adapter saying "this is a page ABOUT the paper" — and even a `.pdf`')
    print('  here is only a lead until the executor fetches the bytes and a reducer profiles them.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
