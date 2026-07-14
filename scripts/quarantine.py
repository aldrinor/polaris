#!/usr/bin/env python3
"""(d) QUARANTINE, DO NOT PURGE. — "Purging destroys the audit trail. Re-attributing everything is unsafe."

    1. FREEZE AND HASH the present corpus, cards, report, graph and logs as CONTAMINATED LEGACY.
    2. QUARANTINE the released report and ALL old `evidence_cards.json` cards — they lack binding.
    3. For each v2 card attempt a UNIQUE REBIND (work candidate, source_version, raw offsets, exact
       span). If EXACTLY ONE manifestation matches, call `bind_span()`.
    4. Apply the question's SOURCE POLICY:
           journal manifestation     -> RETAIN, reattribute FROM THE GRAPH
           working paper / preprint  -> DISCOVERY LEAD; EXCLUDED from task 72
           landing page / wrong work -> QUARANTINE
           unresolved version        -> QUARANTINE until identity is proven
    5. Rebind corroborating sources INDEPENDENTLY.
    6. Collapse expressions into EVIDENCE-UNIT FAMILIES before consolidation and coverage.

NOTHING IS DELETED. Every byte we acquired stays on disk, addressable, with the reason it is not being
cited written next to it. A quarantined card is not a deleted card: it is a card WE CANNOT PROVE, and the
difference between those two is the entire audit trail.

THE REBIND KEY IS THE CONTENT HASH, NOT THE DOI.
------------------------------------------------
A DOI names a WORK. A work has no bytes. `10.1086/705716` is on the corpus row for Acemoglu & Restrepo,
and the bytes in that row's `fulltext` are NBER WORKING PAPER 23285 — 0.37pp in the working paper, 0.2pp
in the published JPE. Rebinding on the DOI would have re-attached every one of those 38 cards to the
Journal of Political Economy and reproduced the P0 inside its own fix.

So the key is `source_version` = `manifestation.content_hash[:12]` — the miner recorded WHICH BYTES it
read. It resolves to exactly one manifestation (66/66 distinct on this corpus, zero collisions), and the
rebind is then CONFIRMED against the bytes: `bind_span()` must accept the raw offsets AND the sliced text
must equal the card's stored `span_raw`, character for character. A card that cannot prove which document
it came from is quarantined, not guessed at.
"""
from __future__ import annotations

import collections
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P  # noqa: E402

OUT = ROOT / 'outputs'
QDIR = OUT / 'quarantine'

GRAPH = OUT / 'provenance_graph.json'
LEDGER = OUT / 'event_ledger.jsonl'
CORPUS = OUT / 'journal_corpus_content.json'
CARDS_V1 = OUT / 'evidence_cards.json'          # THE OLD LANE. No bindings. Quarantined wholesale.
CARDS_V2 = OUT / 'evidence_cards_v2.json'       # mined spans, raw offsets, content-hash version key
LEGACY_REPORT = OUT / 'cellcog_arm' / 'report.md'

#: THE ONE CARD LANE. The composer reads THIS and nothing else.
BOUND = OUT / 'evidence_cards_bound.json'


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ''


# =================================================================================================
# 1. FREEZE
# =================================================================================================

def freeze() -> dict:
    """Hash everything the contaminated pipeline produced, and COPY the artifacts that are about to
    stop being authoritative. The hash is the audit trail; the copy is so the audit trail can be READ."""
    QDIR.mkdir(parents=True, exist_ok=True)
    frozen = {}
    for label, p in [('corpus', CORPUS), ('cards_v1_UNBOUND', CARDS_V1), ('cards_v2_PREBIND', CARDS_V2),
                     ('graph', GRAPH), ('ledger', LEDGER), ('released_report', LEGACY_REPORT)]:
        frozen[label] = dict(path=str(p), exists=p.exists(), sha256=sha(p),
                             bytes=p.stat().st_size if p.exists() else 0)
    # the two artifacts that LOSE their authority are copied into quarantine, byte-identical.
    for p, nm in [(CARDS_V1, 'CONTAMINATED_evidence_cards_v1.json'),
                  (LEGACY_REPORT, 'CONTAMINATED_report.md')]:
        if p.exists():
            shutil.copy2(p, QDIR / nm)
    return frozen


# =================================================================================================
# 3 + 4. REBIND, THEN JUDGE UNDER THE POLICY
# =================================================================================================

#: Sol's disposition table. The artifact kind of the BYTES decides — not the venue on the metadata row.
DISPOSITION = {
    'journal_article':     ('RETAIN',        'journal manifestation — reattributed FROM THE GRAPH'),
    'proceedings_paper':   ('RETAIN',        'peer-reviewed proceedings manifestation'),
    'working_paper':       ('DISCOVERY_LEAD', 'working paper — EXCLUDED from a journal-only answer; the '
                                              'bytes are retained as a lead to the published version'),
    'preprint':            ('DISCOVERY_LEAD', 'preprint — EXCLUDED from a journal-only answer'),
    'accepted_manuscript': ('DISCOVERY_LEAD', 'accepted manuscript — not the journal version of record'),
    'landing_page':        ('QUARANTINE',    'a landing page is not a paper at ANY word count'),
    'wrong_work':          ('QUARANTINE',    'these bytes are a DIFFERENT WORK from the one named'),
    'abstract':            ('QUARANTINE',    'an abstract cannot carry the paper\'s findings'),
    'citation_only':       ('QUARANTINE',    'a citation stub has no findings in it'),
    'extraction_failure':  ('QUARANTINE',    'the bytes are not readable prose (cipher / glyph dump)'),
    'unknown':             ('QUARANTINE',    'UNRESOLVED VERSION — quarantined until identity is proven'),
}


def rebind_one(g: P.Graph, by12: dict, card: dict) -> tuple[str, dict | None, str]:
    """-> (status, binding, why). A UNIQUE match, CONFIRMED AGAINST THE BYTES, or nothing."""
    sv = card.get('source_version') or ''
    if not sv:
        return 'NO_VERSION_KEY', None, ('the card records no `source_version`; which document it was '
                                        'mined from cannot be established')
    cands = by12.get(sv, [])
    if not cands:
        return 'NO_MANIFESTATION', None, f'no manifestation has content_hash starting {sv!r}'
    if len(cands) > 1:
        return 'AMBIGUOUS', None, f'{len(cands)} manifestations share the version key {sv!r}'
    mid = cands[0]

    # THE WORK MUST AGREE TOO. The version key alone would let a card whose DOI says one paper bind to
    # another paper's bytes if a hash prefix ever collided. It does not on this corpus — and it is
    # checked anyway, because "it does not happen on this corpus" is a statement about today.
    m = g.manifestations[mid]
    doi = (card.get('doi') or '').strip()
    if doi:
        wdoi = (g.works[m.work_id].doi or '').strip()
        if wdoi and wdoi.lower() != doi.lower():
            return 'WORK_MISMATCH', None, (f'card names DOI {doi!r}; the bytes it points at belong to '
                                           f'work {m.work_id!r} (DOI {wdoi!r})')
    try:
        b = g.bind_span(mid, card['span_start'], card['span_end'])
    except P.SpanBindingError as e:
        return 'BIND_REFUSED', None, str(e)[:200]
    if b['text'] != card.get('span_raw'):
        return 'BYTES_DIFFER', None, ('the manifestation\'s bytes at those offsets are not the span the '
                                      'card stored — the offsets index a document other than the one the '
                                      'card names')
    return 'REBOUND', b, ''


def judge(g: P.Graph, mid: str, policy: P.SourcePolicy) -> tuple[str, str, str]:
    """-> (disposition, artifact_kind, reason). The BYTES decide."""
    m = g.manifestations[mid]
    kind = (m.profile or {}).get('artifact_kind', 'unknown')
    disp, why = DISPOSITION.get(kind, ('QUARANTINE', f'unregistered artifact kind {kind!r}'))
    if disp == 'RETAIN':
        # ...and it must still clear the policy. A corrupt PDF of a real journal article is a journal
        # article whose bytes may not carry a finding.
        att = g.resolve_attribution(mid, policy)
        if not att.admitted:
            return 'QUARANTINE', kind, f'policy refuses these bytes: {att.refusal}'
    return disp, kind, why


def main() -> int:
    policy = P.JOURNAL_ONLY
    QDIR.mkdir(parents=True, exist_ok=True)

    print('=' * 96)
    print('(d) QUARANTINE, DO NOT PURGE — freeze, rebind from the bytes, and apply the source policy')
    print('=' * 96)

    # ---- 1. FREEZE ------------------------------------------------------------------------------
    frozen = freeze()
    print('\n--- 1. FROZEN AS CONTAMINATED LEGACY (hashed, retained, copied — nothing deleted) ---')
    for k, v in frozen.items():
        if v['exists']:
            print(f"  {k:22} {v['sha256'][:16]}…  {v['bytes']:>9,} bytes  {v['path']}")
        else:
            print(f"  {k:22} (absent)")

    g = P.Graph.from_json(json.loads(GRAPH.read_text()))
    by12: dict[str, list[str]] = collections.defaultdict(list)
    for m in g.manifestations.values():
        by12[m.content_hash[:12]].append(m.id)

    # ---- 2. THE OLD CARD LANE DIES WHOLESALE ----------------------------------------------------
    v1 = json.loads(CARDS_V1.read_text()) if CARDS_V1.exists() else []
    q_v1 = [dict(card_id=c.get('id'), authors=c.get('authors'), year=c.get('year'),
                 venue=c.get('venue'), doi=c.get('doi'), span=(c.get('span') or '')[:300],
                 disposition='QUARANTINE',
                 reason='v1 card: NO manifestation, NO content hash, NO span offsets, NO expression. '
                        'Which document this span came from cannot be established from the card, and '
                        'its `venue` is a metadata label, not a fact about the bytes.')
            for c in v1]
    print(f'\n--- 2. THE OLD LANE ({CARDS_V1.name}) ---')
    print(f'  {len(v1)} cards QUARANTINED WHOLESALE — they carry no binding information at all.')
    fo = [c for c in v1 if any('Frey' in a or 'Osborne' in a for a in (c.get('authors') or []))]
    print(f'  of these, Frey & Osborne: {len(fo)} cards, mined from an ORA LANDING PAGE (548 words).')
    print(f'  the released report {LEGACY_REPORT.name} is QUARANTINED: it is composed from this lane.')

    # ---- 3/4/5. REBIND THE V2 CARDS AND JUDGE THEM ----------------------------------------------
    v2 = json.loads(CARDS_V2.read_text()) if CARDS_V2.exists() else []
    retained, leads, quarantined = [], [], []
    stat = collections.Counter()
    corr_stat = collections.Counter()

    for c in v2:
        status, b, why = rebind_one(g, by12, c)
        stat[status] += 1
        if status != 'REBOUND':
            quarantined.append(dict(card_id=c.get('id'), doi=c.get('doi'), authors=c.get('authors'),
                                    year=c.get('year'), venue_claimed=c.get('venue'),
                                    disposition='QUARANTINE', rebind_status=status, reason=why,
                                    span=(c.get('span') or '')[:300]))
            continue

        mid = b['manifestation_id']
        disp, kind, reason = judge(g, mid, policy)
        m = g.manifestations[mid]
        rec = dict(card_id=c.get('id'), doi=c.get('doi'), authors=c.get('authors'), year=c.get('year'),
                   venue_claimed=c.get('venue'), manifestation_id=mid, content_hash=b['content_hash'],
                   work_id=m.work_id, expression_id=b['expression_id'], artifact_kind=kind,
                   disposition=disp, reason=reason, span=(c.get('span') or '')[:300])
        stat[f'  -> {disp}'] += 1

        if disp != 'RETAIN':
            (leads if disp == 'DISCOVERY_LEAD' else quarantined).append(rec)
            continue

        # ---- RETAIN: REATTRIBUTE FROM THE GRAPH. The row's `attribution`/`venue`/`source` strings are
        #      DISPLAY CACHES written by the corpus builder, and on six works they say "Journal of X"
        #      over working-paper bytes. They are overwritten here, from the expression the POLICY chose.
        att = g.resolve_attribution(mid, policy)
        expr = g.expressions[att.names_expression_id]
        work = g.works[expr.work_id]
        out = dict(c)
        out.update(
            manifestation_id=mid, content_hash=b['content_hash'], expression_id=b['expression_id'],
            attribution_target_expression_id=att.names_expression_id,
            permitted_expression_ids=list(b['permitted_expression_ids']),
            work_id=m.work_id, evidence_unit_id=m.work_id, source_policy=att.policy,
            artifact_kind=kind,
            # reattributed FROM THE GRAPH — display caches, rebuilt from the node that was resolved
            attribution=expr.attribution, venue=work.venue or '', year=work.year,
            authors=list(work.authors or []),
            source=expr.attribution, rebound=True)

        # ---- 5. CORROBORATING SOURCES REBIND INDEPENDENTLY.
        #      A corroborating source IS A CITATION. It appears in the review under its own name and it
        #      is exactly as capable of naming a document its span never came from. It gets the same
        #      chain, resolved on its own, or it is dropped from the card.
        kept_c = []
        for cs in (c.get('corroborating_sources') or []):
            cst, cb, cwhy = rebind_one(g, by12, cs)
            if cst != 'REBOUND':
                corr_stat[f'DROPPED:{cst}'] += 1
                continue
            cdisp, ckind, _ = judge(g, cb['manifestation_id'], policy)
            if cdisp != 'RETAIN':
                corr_stat[f'DROPPED:{cdisp}/{ckind}'] += 1
                continue
            catt = g.resolve_attribution(cb['manifestation_id'], policy)
            cm = g.manifestations[cb['manifestation_id']]
            cs2 = dict(cs)
            cs2.update(manifestation_id=cb['manifestation_id'], content_hash=cb['content_hash'],
                       expression_id=cb['expression_id'], work_id=cm.work_id,
                       evidence_unit_id=cm.work_id,
                       attribution_target_expression_id=catt.names_expression_id,
                       attribution=g.expressions[catt.names_expression_id].attribution,
                       source_policy=catt.policy, rebound=True)
            kept_c.append(cs2)
            corr_stat['REBOUND'] += 1
        out['corroborating_sources'] = kept_c
        out['n_sources'] = 1 + len(kept_c)
        retained.append(out)
        quarantined_or_lead = None  # noqa: F841

    print(f'\n--- 3. REBIND {len(v2)} v2 CARDS (key: content_hash[:12], confirmed against the bytes) ---')
    for k, v in stat.most_common():
        print(f'  {k:28} {v}')
    if corr_stat:
        print('\n--- 5. CORROBORATING SOURCES (rebound INDEPENDENTLY) ---')
        for k, v in corr_stat.most_common():
            print(f'  {k:28} {v}')
    else:
        print('\n--- 5. CORROBORATING SOURCES: none present in this bundle (0 cards carry any) ---')

    # ---- 6. EVIDENCE-UNIT FAMILIES --------------------------------------------------------------
    #      Two expressions of ONE study are ONE evidence unit. They may not corroborate each other, and
    #      counting them twice inflates both "corroborated" and "literature depth". The family is keyed
    #      on the WORK, which is the study — not on the manifestation, which is a document of it.
    fam: dict[str, list[dict]] = collections.defaultdict(list)
    for c in retained:
        fam[c['evidence_unit_id']].append(c)
    print(f'\n--- 6. EVIDENCE-UNIT FAMILIES ---')
    print(f'  {len(retained)} retained cards collapse into {len(fam)} evidence units (studies).')

    # ---- WORKS WE HOLD NOTHING OF ARE NOT EXCLUDED. THEY ARE RETRYABLE. --------------------------
    #      "A 429 leaves the work SEARCH_FAILED and ELIGIBLE FOR RETRY, never a permanent exclusion."
    #      A work with no manifestation is a work we have not fetched YET. Recording it as "excluded"
    #      would turn a transient network condition into a permanent editorial judgement.
    have = {m.work_id for m in g.manifestations.values()}
    retry = [dict(work_id=w.id, doi=w.doi, title=(w.title or '')[:90], authors=w.authors, year=w.year,
                  venue=w.venue, state='SEARCH_FAILED', eligible_for_retry=True,
                  reason='no manifestation: we hold no bytes of this work. This is a FETCH outcome, not '
                         'an editorial one, and it is retryable.')
             for w in g.works.values() if w.id not in have]

    # ---- EMIT ------------------------------------------------------------------------------------
    BOUND.write_text(json.dumps(retained, indent=1))
    (QDIR / 'quarantined_cards.json').write_text(json.dumps(q_v1 + quarantined, indent=1))
    (QDIR / 'discovery_leads.json').write_text(json.dumps(leads, indent=1))
    (QDIR / 'retry_eligible_works.json').write_text(json.dumps(retry, indent=1))

    manifest = dict(
        policy=policy.name,
        frozen_contaminated_legacy=frozen,
        v1_cards_quarantined=len(q_v1),
        v2_cards_in=len(v2),
        v2_rebound=stat['REBOUND'],
        retained=len(retained),
        discovery_leads=len(leads),
        quarantined_v2=len(quarantined),
        evidence_units=len(fam),
        works_in_graph=len(g.works),
        works_with_bytes=len(have),
        works_retry_eligible=len(retry),
        bound_cards_path=str(BOUND),
        bound_cards_sha256='',
    )
    manifest['bound_cards_sha256'] = sha(BOUND)
    (QDIR / 'manifest.json').write_text(json.dumps(manifest, indent=1))

    # ---- THE HONEST NUMBER -----------------------------------------------------------------------
    print('\n' + '=' * 96)
    print('THE QUARANTINE MANIFEST — the corpus SHRINKS, and here is by how much')
    print('=' * 96)
    tot_in = len(v1) + len(v2)
    print(f'  cards in  (v1 {len(v1)} unbound + v2 {len(v2)} mined) : {tot_in}')
    print(f'  cards out (BOUND, journal-only, reattributed)  : {len(retained)}')
    print(f'  ----------------------------------------------------------------')
    print(f'  v1 cards quarantined (no binding at all)      : {len(q_v1)}')
    print(f'  v2 -> DISCOVERY LEAD (working paper/preprint)  : {len(leads)}')
    print(f'  v2 -> QUARANTINE (landing page/unknown/etc.)   : {len(quarantined)}')
    print(f'  NET SHRINKAGE                                  : {tot_in - len(retained)} cards '
          f'({100.0 * (tot_in - len(retained)) / max(tot_in, 1):.1f}% of everything we had)')
    print()
    print(f'  evidence units (studies) behind the survivors  : {len(fam)}')
    print(f'  works in the graph                             : {len(g.works)}')
    print(f'  works we hold bytes of                         : {len(have)}')
    print(f'  works SEARCH_FAILED, ELIGIBLE FOR RETRY        : {len(retry)}  (not excluded — retryable)')
    print()
    by_work = collections.Counter()
    for r in leads:
        by_work[(r['authors'][0] if r['authors'] else '?', r['year'], r['venue_claimed'])] += 1
    print('  THE JOURNAL-LABELLED WORKING PAPERS THAT LOSE JOURNAL ATTRIBUTION:')
    for (a, y, v), n in by_work.most_common():
        print(f'     {n:>3} cards  {a:<14} {y}  labelled "{v}" — the BYTES are a working paper')
    print()
    print(f'  wrote {BOUND}  (sha256 {manifest["bound_cards_sha256"][:16]}…)')
    print(f'  wrote {QDIR}/manifest.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
