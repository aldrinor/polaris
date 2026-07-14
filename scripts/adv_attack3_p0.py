#!/usr/bin/env python3
"""ATTACK 3 (THE P0) — PREDECESSOR RENDERED AS JOURNAL VERSION.

Take an NBER WORKING-PAPER span out of the LIVE CORPUS and try to get it attributed to the journal
article. It must be REFUSED unless a verbatim span alignment proves it.

We do not simulate anything. We use:
  - the real corpus row,
  - the real evidence_miner.gate_card(),
  - the real cellcog_composer._clean() (the faithfulness gate the canary certifies).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

CORPUS = json.loads((ROOT / 'outputs' / 'journal_corpus_content.json').read_text())

print('=' * 100)
print('ATTACK 3 (P0) — CAN WORKING-PAPER TEXT BE PRINTED AS A FINDING OF THE JOURNAL ARTICLE?')
print('=' * 100)

# ---------------------------------------------------------------------------------------------
# Step 0: establish, FROM THE BYTES, which rows are working papers wearing a journal's name.
# ---------------------------------------------------------------------------------------------
import provenance as P
from provenance import Work, profile, derive_expression_kind

print('\n--- STEP 0: what do the bytes of each FULLTEXT row actually say they are? ---')
wp_rows = []
for c in CORPUS:
    if c.get('content_status') != 'FULLTEXT':
        continue
    txt = c.get('fulltext') or ''
    w = Work(id='w', title=c.get('title', ''), authors=c.get('authors', []), year=c.get('year'),
             venue=c.get('venue'), doi=c.get('doi'))
    pr = profile(txt, w, independent_abstract=c.get('abstract') or '')
    if pr['expression_kind'] == 'working_paper':
        wp_rows.append((c, pr))
        m = re.search(r'(?i)(nber working paper|working paper (no\.?|series)|iza discussion paper)[^\n]{0,40}',
                      txt[:12000])
        print(f"  {(c['authors'] or ['?'])[0]:<12} ({c['year']})  venue={c['venue'][:38]:<38}")
        print(f"       corpus row says : content_status=FULLTEXT   attribution={c.get('attribution','')[:64]!r}")
        print(f"       THE BYTES SAY   : {m.group(0)[:70]!r}" if m else '')

print(f'\n  {len(wp_rows)} rows carry a JOURNAL attribution over WORKING-PAPER bytes.')

# ---------------------------------------------------------------------------------------------
# Step 1: THE MINER. Feed a working-paper row through the REAL gate. What attribution comes out?
# ---------------------------------------------------------------------------------------------
print('\n--- STEP 1: evidence_miner.gate_card() — what attribution does a WP span receive? ---')
import evidence_miner as EM

target, tprof = next((c, p) for c, p in wp_rows
                     if (c['authors'] or [''])[0] in ('Acemoglu', 'Bresnahan', 'Krueger', 'Goldin'))
src = target['fulltext']
print(f"  TARGET: {(target['authors'] or ['?'])[0]} ({target['year']}), {target['venue']}")
print(f"          bytes = {tprof['expression_kind']} ({tprof['expression_kind_basis'][:56]})")

# THE GRAPH. gate_card() cannot be called without one — a card IS a bound span.
G = P.migrate(CORPUS)
MID = next(m for m, x in G.manifestations.items()
           if G.works[x.work_id].doi == target['doi'] and x.text_field == 'fulltext')
target = dict(target, manifestation_id=MID)
src = G.manifestations[MID].text

view, chunks = EM.chunk_document('t', src)
contract = EM.load_contract('AI and the labour market', None)

# find a REAL quantitative sentence in the working paper's own body
cand = None
for ch in chunks:
    if ch.weight <= 0:
        continue
    for c0 in EM.harvest(ch, contract):
        if c0['result_verb'] and len(c0['text']) > 90:
            cand, chosen = c0, ch
            break
    if cand:
        break

span = view.text[cand['v_start']:cand['v_end']].strip()
print(f"\n  a real span from the WORKING PAPER's body:\n    {span[:150]!r}")

nums = sorted(EM.number_tokens(span))
raw = {'span': span, 'effect': nums[0] if nums else '', 'unit': '', 'comparator': '',
       'outcome': 'employment', 'population': '', 'geography': '', 'period': '', 'technology': '',
       'industry': '', 'unit_of_analysis': '', 'design': '', 'uncertainty': '', 'horizon': '',
       'mechanisms': []}
rejects = EM.new_rejects()
pw = EM.paper_window(view, chunks, target)
card = EM.gate_card(raw, view, chosen, target, pw, contract, rejects,
                    graph=G, source_policy=P.JOURNAL_ONLY)

if card is None:
    fired = [k for k, v in rejects.items() if not k.startswith('_') and v]
    print(f'\n  gate_card REJECTED it under `journal_articles_only`: {fired}')
    for q in rejects.get('_quarantine', []):
        print(f"\n  >>> ATTACK 3 IS DEAD. The span is REAL and VERBATIM, and it is REFUSED.")
        print(f"      it would have been printed as: {q['row_attribution_that_would_have_been_used']!r}")
        print(f"      refusal: {q['refusal'][:150]}")
        print(f"      QUARANTINED (not deleted): expression={q['expression_id']}")
    card_any = EM.gate_card(raw, view, chosen, target, pw, contract, EM.new_rejects(),
                            graph=G, source_policy=P.ANY_VERSION)
    if card_any:
        print(f"\n  under `any_identified_version` the SAME span IS admitted — as what it is:")
        print(f"      attribution : {card_any['attribution']!r}")
        print(f"      names       : {card_any['attribution_target_expression_id']}")
        print(f"      bound to    : {card_any['manifestation_id']} / {card_any['content_hash'][:16]}...")
else:
    print(f"\n  >>> gate_card ADMITTED the span. THE CARD IT PRODUCED:")
    print(f"        source      : {card['source']!r}")
    print(f"        attribution : {card['attribution']!r}")
    print(f"        venue       : {card['venue']!r}")
    print(f"        span        : {card['span'][:80]!r}")
    print(f"        manifestation_id / content_hash on the card? "
          f"{[k for k in card if 'manif' in k or 'hash' in k] or 'ABSENT — the card cannot say which BYTES it came from'}")

# ---------------------------------------------------------------------------------------------
# Step 2: THE COMPOSER'S FAITHFULNESS GATE — the one test_gate_is_wired.py certifies 16/16.
#         Write the journal attribution over the working paper's span. Does the gate stop it?
# ---------------------------------------------------------------------------------------------
print('\n--- STEP 2: cellcog_composer._clean() — the gate the canary certifies. ---')
import importlib.util as _u

_sp = _u.spec_from_file_location('cc', ROOT / 'scripts' / 'cellcog_composer.py')
cc = _u.module_from_spec(_sp)
_sp.loader.exec_module(cc)

gate_card_in = card if card else {
    'authors': target['authors'], 'year': target['year'], 'venue': target['venue'],
    'span': span, 'claim': span[:80], 'source': target.get('attribution_short', ''),
    'attribution': target.get('attribution', ''), 'mechanisms': [],
}

who = (target['authors'] or ['?'])[0]
sentence = (f"Writing in the {target['venue']} in {target['year']}, {who} et al. report that "
            f"{span[0].lower() + span[1:]}")
sentence = re.sub(r'\s+', ' ', sentence).strip()
if not sentence.endswith('.'):
    sentence += '.'

shipped, why = cc._clean(sentence, [gate_card_in])
print(f"\n  THE SENTENCE OFFERED TO THE GATE:")
print(f"    {sentence[:190]!r}")
print(f"\n  ...its span is VERBATIM in {who}'s WORKING PAPER, and the sentence names {target['venue']}.")
print(f"\n  >>> GATE OUTPUT: {'(deleted)' if not shipped.strip() else shipped[:190]!r}")
print(f"  >>> reasons: {why}")
print()
if shipped.strip():
    print('  ' + '!' * 92)
    print('  !! ATTACK 3 SUCCEEDS. WORKING-PAPER TEXT SHIPPED UNDER THE JOURNAL\'S NAME.')
    print(f'  !! The gate checked the span against the bytes we hold — and those bytes are the')
    print(f'  !! WORKING PAPER. It never asked WHICH DOCUMENT the bytes are. That question is not')
    print(f'  !! in the gate, and the module that can answer it is called by nobody.')
    print('  ' + '!' * 92)
else:
    print('  ATTACK 3 REPELLED.')

# ---------------------------------------------------------------------------------------------
# Step 3: is the rule that WOULD have stopped it actually reachable from the pipeline?
# ---------------------------------------------------------------------------------------------
print('\n--- STEP 3: is Sol\'s rule on the critical path? ---')
import subprocess

for sym in ('journal_attributable', 'attribution_targets', 'bind_span'):
    r = subprocess.run(['grep', '-rn', sym, '--include=*.py', str(ROOT / 'scripts'), str(ROOT / 'src')],
                       capture_output=True, text=True)
    hits = [l for l in r.stdout.splitlines()
            if 'scripts/provenance.py' not in l and 'adv_attack' not in l]
    print(f"  {sym:<22} called outside provenance.py by: {hits or 'NOTHING'}")
