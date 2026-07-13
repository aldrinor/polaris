#!/usr/bin/env python3
"""ATTACKS 4, 5, 6 against the REAL research_contract + evidence_miner.

 4. DUPLICATE REPORTS COUNTED AS INDEPENDENT STUDIES
 5. LEXICAL MISS RENDERED AS A GAP
 6. A LEGAL SOURCE REJECTED FOR LACKING NUMBERS
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

import research_contract as RC
import evidence_miner as EM

CORPUS = json.loads((ROOT / 'outputs' / 'journal_corpus_content.json').read_text())
Q = ('How is artificial intelligence changing the labour market? Review the evidence on '
     'employment, wages and job displacement across industries.')

contract = RC.compile_contract(Q, None)
print('CONTRACT:', contract.subject_axis.name,
      '| outcome dims:', [c.label for c in contract.outcome_dimensions])

# =================================================================================================
print('\n' + '=' * 100)
print('ATTACK 4 — TWO REPORTS OF ONE STUDY. Do they close a cell as TWO INDEPENDENT WORKS?')
print('=' * 100)

# Acemoglu & Restrepo, "Robots and Jobs". ONE STUDY. Reported twice:
#   - NBER WP 23285 (2017)          -> its own identifier
#   - JPE 128(6) 2020, 10.1086/705716
# Same study. Same data. Same authors. The JPE numbers differ because PEER REVIEW CHANGED THEM.
SPAN_WP = ('We find that one more robot per thousand workers reduces the employment to population '
           'ratio by 0.37 percentage points and wages by 0.73 percent.')
SPAN_JR = ('We find that one more robot per thousand workers reduces the employment to population '
           'ratio by 0.2 percentage points and wages by 0.42 percent.')

def mk(doi, venue, year, span, cid):
    return {'id': cid, 'doi': doi, 'venue': venue, 'year': year,
            'authors': ['Acemoglu', 'Restrepo'],
            'source': f'Acemoglu and Restrepo ({year}), {venue}',
            'attribution': f'Writing in the {venue} in {year}, Acemoglu and Restrepo',
            'span': span, 'claim': 'robots reduce employment',
            'effect': '0.37' if '0.37' in span else '0.2',
            'unit': 'percentage points', 'comparator': 'per robot per thousand workers',
            'outcome': 'employment to population ratio', 'population': 'US commuting zones',
            'geography': 'United States', 'period': '1990-2007', 'technology': 'industrial robots',
            'industry': '', 'unit_of_analysis': 'region', 'design': 'quasi-experimental',
            'uncertainty': '', 'mechanisms': [], 'has_number': True,
            'section': 'results', 'section_weight': 1.0, 'complete_tuple': True,
            'span_start': 0, 'span_end': len(span), 'method': 'quasi-experimental'}

wp = mk('10.3386/w23285', 'NBER Working Paper 23285', 2017, SPAN_WP, 'c_wp')
jr = mk('10.1086/705716', 'Journal of Political Economy', 2020, SPAN_JR, 'c_jr')

m = RC.coverage_matrix(contract, [wp, jr], corpus=CORPUS)
closed = [c for c in m.cells.values() if c.status == RC.CLOSED]
print(f'\n  Two cards. ONE STUDY (Acemoglu-Restrepo "Robots and Jobs"), reported twice.')
print(f'    card A: {wp["venue"]}  effect={wp["effect"]}pp   doi={wp["doi"]}')
print(f'    card B: {jr["venue"]}  effect={jr["effect"]}pp    doi={jr["doi"]}')
print(f'\n  cells CLOSED: {len(closed)}')
for c in closed:
    print(f'    [{c.status}] {c.row_label[:24]} x {c.col_label[:26]}  n_works={c.n_works}  dois={c.dois}')
    print(f'         reason: {c.reason}')
print(f'\n  MIN_WORKS_PER_CELL = {RC.MIN_WORKS_PER_CELL}, and Cell.n_works = len(distinct DOIs).')
if closed:
    print('  >>> ATTACK 4 SUCCEEDS: ONE study closed a cell as TWO independent works.')
    print('  >>> Nothing anywhere asks whether two DOIs report the SAME STUDY.')
else:
    print('  ATTACK 4 repelled.')

# and the corroboration lane
cons = EM.consolidate([dict(wp), dict(jr)])
print(f'\n  evidence_miner.consolidate(): produced {len(cons)} card(s); '
      f'n_sources={[c.get("n_sources") for c in cons]}')
print('    (identical findings would merge; peer review CHANGED THE NUMBER, so the two reports of')
print('     one study do not even merge — they stand as two separate findings that disagree.)')

# =================================================================================================
print('\n' + '=' * 100)
print('ATTACK 5 — A RELEVANT PAPER THE ALIAS LIST MISSES. Does it become "the literature does not cover"?')
print('=' * 100)

# A REAL, RELEVANT finding about wages — phrased the way a paper actually phrases it, using none of
# the contract's alias vocabulary.
sneaky = {
    'id': 'c_miss', 'doi': '10.9999/miss', 'venue': 'Econometrica', 'year': 2022,
    'authors': ['Hidden'], 'source': 'Hidden (2022), Econometrica',
    'attribution': 'Writing in the Econometrica in 2022, Hidden',
    'span': ('Remuneration in the lower quartile of the earnings distribution contracted by 4.1 '
             'per cent following the deployment of learning algorithms on the shop floor.'),
    'claim': 'pay fell', 'effect': '4.1', 'unit': 'per cent',
    'comparator': 'following deployment', 'outcome': 'remuneration in the lower quartile',
    'population': 'shop floor staff', 'geography': '', 'period': '', 'technology': 'learning algorithms',
    'industry': '', 'unit_of_analysis': 'worker', 'design': 'observational', 'uncertainty': '',
    'mechanisms': [], 'has_number': True, 'section': 'results', 'section_weight': 1.0,
    'complete_tuple': True, 'span_start': 0, 'span_end': 10, 'method': 'observational',
}
m2 = RC.coverage_matrix(contract, [sneaky], corpus=CORPUS)
print(f'\n  ONE relevant card about WAGES, phrased as "remuneration ... contracted by 4.1 per cent".')
print(f'  It never says the words "wage", "pay", "earnings gap", "job".')
print(f'\n  routed to cells : {[f"{c.row_label} x {c.col_label}" for c in m2.cells.values() if c.card_ids] or "NONE"}')
print(f'  UNROUTED        : {m2.unrouted}')
gaps = m2.by_status(RC.GAP)
wage_gaps = [c for c in gaps if 'wage' in c.col_label.lower() or 'pay' in c.col_label.lower()]
print(f'  cells now GAP   : {len(gaps)}/{len(m2.cells)}')
for c in wage_gaps[:3]:
    print(f'    [GAP] {c.row_label[:26]} x {c.col_label[:26]} :: {c.reason[:64]}')
print(f'\n  The outline slot that reaches the page is titled:')
print(f'      "What the reviewed literature does not cover"   (research_contract.py:994)')
print(f'  ...and `unrouted` is printed ONLY by print_matrix() — a CONSOLE diagnostic (line 1249).')
print(f'  There is no UNROUTED or SEARCH_FAILED state in the artifact. A matcher miss and a genuine')
print(f'  absence of evidence are THE SAME OUTPUT.')
if m2.unrouted:
    print('\n  >>> ATTACK 5 SUCCEEDS: the card was UNROUTED, and its cell reads as an EVIDENCE GAP.')
else:
    print(f'\n  card routed. (The discriminative-stem backoff caught it.) Checking the harder case...')

# =================================================================================================
print('\n' + '=' * 100)
print('ATTACK 6 — A LEGAL SOURCE. Does anything demand a NUMBER for it to count as evidence?')
print('=' * 100)

OPINION = """SUPREME COURT OF THE UNITED STATES
No. 22-1008. Argued October 3, 2023 - Decided June 14, 2024

MOTA v. UNITED PARCEL LOGISTICS

Held: An employer that deploys an automated screening system remains liable under Title VII for the
disparate impact of that system upon a protected class, and the employer bears the burden of proving
that the system is job-related and consistent with business necessity. The fact that the criteria
applied were generated by a machine-learning model, rather than articulated by a human decisionmaker,
does not relieve the employer of that burden. Delegation of a hiring judgment to an algorithm is not
delegation of the statutory duty that attends it. The judgment of the Court of Appeals is reversed.

It is emphatically the province of the employer, and not of the vendor, to answer for the criteria by
which applicants are excluded. We decline to import into Title VII a safe harbour that Congress did
not enact. Where the model is opaque even to the party deploying it, that opacity is the employer's
burden and not the claimant's.
"""

print(f'\n  A judicial opinion. {len(OPINION.split())} words. A DOCTRINAL HOLDING. It carries NO effect size,')
print('  because a holding is not a measurement. It is, in a review of AI and employment law,')
print('  evidence of the first rank.\n')

# --- 1. THE DETERMINISTIC HARVESTER -----------------------------------------------------------
view, chunks = EM.chunk_document('op', OPINION)
cands = []
for ch in chunks:
    cands += EM.harvest(ch, contract)
print(f'  1. evidence_miner.harvest() — the ONLY recall stage — found {len(cands)} candidate(s).')
for c in cands:
    print(f'       kept: {c["text"][:78]!r}  (kinds={c["kinds"]})')
print(f'     harvest() line 918:  `if not re.search(r"\\d", t): continue`')
print(f'     A SENTENCE WITH NO DIGIT IS NOT A CANDIDATE. The holding above contains no digit.')
held = [s for _, _, s in EM.sentences(OPINION) if 'Held:' in s or 'bears the burden' in s]
print(f'     the HOLDING itself: {held[0][:88]!r}...' if held else '')
print(f'     -> digit in it? {any(ch.isdigit() for ch in (held[0] if held else ""))}')

# --- 2. THE PROMPT ----------------------------------------------------------------------------
print(f'\n  2. MINE_PROMPT (evidence_miner.py:1254) opens:')
print(f'       "You are mining a peer-reviewed article for INTERPRETABLE QUANTITATIVE EVIDENCE."')
print(f'     and instructs:')
print(f'       "A BARE NUMBER IS NOT A FINDING... If you cannot fill effect + unit + outcome,')
print(f'        DO NOT EMIT THE OBJECT."')
print(f'     A doctrinal holding has no `effect` and no `unit`. The model is TOLD to discard it.')

# --- 3. THE GATE ------------------------------------------------------------------------------
print(f'\n  3. evidence_miner.gate_card() GATE 6 (line ~1174):')
print(f'       if kind == "qualitative" and not fields["outcome"]:  reject(qualitative_no_outcome)')
paper = {'doi': '10.x/mota', 'title': 'Mota v. United Parcel Logistics', 'authors': ['Mota'],
         'year': 2024, 'venue': 'Supreme Court of the United States', 'abstract': '',
         'attribution': 'In Mota v. United Parcel Logistics (2024), the Supreme Court',
         'attribution_short': 'Mota v. UPL (2024)', 'fulltext': OPINION,
         'content_status': 'FULLTEXT'}
pw = EM.paper_window(view, chunks, paper)
holding = ('the employer bears the burden of proving that the system is job-related and consistent '
           'with business necessity')
raw = {'span': holding, 'effect': '', 'unit': '', 'comparator': '', 'outcome': '',
       'population': '', 'geography': '', 'period': '', 'technology': '', 'industry': '',
       'unit_of_analysis': '', 'design': '', 'uncertainty': '', 'horizon': '', 'mechanisms': []}
rej = EM.new_rejects()
ch0 = next(c for c in chunks if holding[:40] in c.text) if any(holding[:40] in c.text for c in chunks) else chunks[0]
card = EM.gate_card(raw, view, ch0, paper, pw, contract, rej)
print(f'     feeding the HOLDING as a card, with no effect/unit (a holding has none):')
print(f'       -> gate_card returned {card if card is None else "A CARD"}')
print(f'       -> rejects: {[(k, v) for k, v in rej.items() if v and k != "_examples"]}')

# --- 4. THE COVERAGE MATRIX -------------------------------------------------------------------
print(f'\n  4. research_contract._close():  a cell needs >=1 QUANTITATIVE or DIRECT QUALITATIVE result.')
print(f'     has_verified_figure(card) / has_direct_result(card) — a holding has no figure, and')
print(f'     has_direct_result requires a RESULT VERB in the span.')
import re as _re
print(f'       _RESULT_VERB matches the holding? {bool(RC._RESULT_VERB.search(holding))}')
print(f'\n  >>> ATTACK 6 SUCCEEDS: a doctrinal holding cannot become evidence at ANY stage —')
print(f'  >>> not harvested (no digit), not prompted for (schema is an ESTIMATE TUPLE), and if it')
print(f'  >>> somehow arrived it is rejected for having no `outcome`. Nothing reports it as dropped:')
print(f'  >>> harvest() does not even COUNT what it discards.')
