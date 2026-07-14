#!/usr/bin/env python3
"""LIVE PROBES for the biomedical + OA-index lane, on REAL DOIs FROM OUR OWN CANDIDATE LISTS.

    python3 scripts/probe_routes_bio_live.py

Sol V9 §2 asks for the three routes to be wired and PROVEN. This fires them against real DOIs drawn from
`outputs/acquisition_campaign/frontier_2023_2025_FINAL.json` and reports, per route, what was OBSERVED —
never what this script would like to be true. Every request goes through `acquisition.Acquirer`, so every
attempt lands on the event ledger, and every label printed below is DERIVED by a reducer from the bytes.

THE PROBE SET IS CHOSEN TO MAKE THE LANE FAIL IN EVERY WAY SOL PREDICTED IT COULD:

  A. 10.1186/s13643-025-03000-0   BMC Systematic Reviews. In PMC, in DOAJ, CC BY.  -> the happy path.
  B. 10.1097/jom.0000000000003825 JOEM. A real journal article that PMC's index does not carry.
                                  -> "Identifier not found in PMC", INSIDE AN HTTP 200.
  C. 10.1115/1.4071773            An NIH AUTHOR MANUSCRIPT (PMC13200213). It HAS a PMCID.
                                  -> the OA service says `idDoesNotExist`; the full text is not in the OA
                                     subset. A PMCID IS NOT A DOCUMENT.
  D. 10.1057/s41599-025-06418-y   Palgrave Humanities & Social Sciences Comms. Genuinely open, and NOT in
                                  PMC at all -> the DOAJ/EPMC lane is what reaches it, or nothing does.

The ledger is written to a PROBE-LOCAL path, not the production one: a probe must not be able to write
evidence into the corpus.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import acquisition  # noqa: E402
import routes_bio as RB  # noqa: E402
from acquisition import Acquirer, BlobStore, ResolveContext, select_evidence  # noqa: E402
from event_ledger import Ledger  # noqa: E402
from source_router import classify_discovery_outcome, load_table  # noqa: E402

OUT = ROOT / 'outputs' / 'routes_bio_probe'
CAMPAIGN = ROOT / 'outputs' / 'acquisition_campaign' / 'frontier_2023_2025_FINAL.json'

PROBES = [
    ('10.1186/s13643-025-03000-0', 'BMC Systematic Reviews — OA VoR, in PMC + DOAJ'),
    ('10.1097/jom.0000000000003825', 'JOEM — a journal article PMC does not index'),
    ('10.1115/1.4071773', 'ASME — an NIH AUTHOR MANUSCRIPT with a PMCID (PMC13200213)'),
    ('10.1057/s41599-025-06418-y', 'Palgrave HSSC — open, but not in PMC'),
]


def corpus_titles() -> dict[str, dict]:
    """The requested identity, taken from OUR candidate list — so the wrong-work reducer has something
    to check the fetched bytes AGAINST. Without it, identity is unfalsifiable."""
    if not CAMPAIGN.exists():
        return {}
    recs = json.loads(CAMPAIGN.read_text()).get('records', [])
    return {str(r.get('doi', '')).lower(): r for r in recs if r.get('doi')}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    table = load_table()
    ledger = Ledger.load(OUT / 'ledger.jsonl')
    blobs = BlobStore(OUT / 'blobs')
    acq = Acquirer('probe_routes_bio', ledger=ledger, blobs=blobs)
    meta = corpus_titles()

    print('=' * 100)
    print('LIVE PROBES — PMC / EUROPE PMC / DOAJ AS FULL-TEXT ROUTES')
    print(f'  ledger : {OUT / "ledger.jsonl"}   (NOT the production ledger)')
    pol, _default = __import__('host_scheduler').load_policies()
    budgets = ', '.join(f'{h}={p.min_spacing_s}s/{p.max_concurrency}'
                        for h, p in sorted(pol.items())
                        if any(k in h for k in ('ncbi', 'ebi', 'doaj')))
    print(f'  budgets: {budgets}   (host_scheduler, from source_routes.yaml — not from this script)')
    print('=' * 100)

    # ---- HOP 1, BATCHED: every probe DOI in ONE ID-converter request (the documented ceiling is 200) --
    dois = [d for d, _ in PROBES]
    id_records, _rid = RB.pmc_convert_ids(acq, table, dois, unit=dois[0])
    print('\n--- PMC ID CONVERTER (1 request, 4 ids — batching is the politeness rule, not an option) ---')
    for d in dois:
        rec = id_records.get(d, {})
        if str(rec.get('status', '')).lower() == 'error':
            print(f'  {d:32s} -> NOT IN PMC INDEX  ({rec.get("errmsg", "")})')
        else:
            print(f'  {d:32s} -> {rec.get("pmcid", "-"):14s} pmid={rec.get("pmid", "-")}')

    summary = []
    for doi, note in PROBES:
        m = meta.get(doi.lower(), {})
        ctx = ResolveContext(
            work_id=doi, contract_id='probe:journal_only', identifiers=(doi,),
            title=str(m.get('title') or ''),
            authors=tuple(m.get('authors') or ()),
            year=m.get('year'),
            permitted_expression_kinds=('journal_version',))

        print('\n' + '=' * 100)
        print(f'{doi}\n  {note}')
        print(f'  title (from our candidate list): {(ctx.title or "(none)")[:78]}')
        print('-' * 100)

        report = RB.resolve_work(acq, table, ctx, fetch=True, id_records=id_records)
        for route, row in report['routes'].items():
            outcome, basis = classify_discovery_outcome(acq.ledger, doi, route)
            print(f'  {route:11s} candidates={row["candidates"]:<2d} manifestations={row["manifestations"]:<2d} '
                  f'-> {outcome}')
            print(f'              {basis[:96]}')

        # ---- WHAT DID WE ACTUALLY END UP HOLDING? Derived from the bytes, by the shared reducer. -----
        best = select_evidence(acq.ledger, doi, blobs)
        if best:
            print(f'  BEST DOCUMENT HELD:')
            print(f'      content_class   = {best["content_class"]}   (complete={best["is_complete"]})')
            print(f'      expression_kind = {best["expression_kind"]}')
            print(f'          because: {best["expression_basis"][:80]}')
            print(f'      readable_words  = {best["readable_words"]:,}   via {best["manifestation"].get("extraction_method")}')
            print(f'      locator         = {best["manifestation"].get("locator", "")[:80]}')
            summary.append((doi, best['content_class'], best['expression_kind'],
                            best['readable_words'], best['is_complete']))
        else:
            print('  BEST DOCUMENT HELD: none — and NONE IS NOT AN ABSENCE. See the route outcomes above:')
            print('      the backends ANSWERED. What they answered is on the ledger, in its own words.')
            summary.append((doi, '-', '-', 0, False))

    print('\n' + '=' * 100)
    print('SUMMARY — every label below was DERIVED FROM BYTES, none was asserted by an adapter')
    print('=' * 100)
    print(f'  {"DOI":34s} {"content_class":16s} {"expression_kind":20s} {"words":>8s}  complete')
    for doi, cls, ek, words, comp in summary:
        print(f'  {doi:34s} {cls:16s} {ek:20s} {words:>8,}  {comp}')
    print(f'\n  events on the probe ledger: {len(acq.ledger.events())}')
    print(f'  blobs written:              {sum(1 for _ in (OUT / "blobs").rglob("*.bin"))}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
