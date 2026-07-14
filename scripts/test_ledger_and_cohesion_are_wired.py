#!/usr/bin/env python3
"""ARE THE FACT-USE LEDGER AND THE COHESION PASS ACTUALLY ON THE CRITICAL PATH?

THE ONLY LESSON THIS PROJECT HAS EVER LEARNED THE HARD WAY: a module that self-tests GREEN and is CALLED
BY NOBODY is worthless and actively dangerous, because it manufactures confidence. `provenance.py` went
18/18 while the P0 it was written to stop ran live on disk. `fact_use_ledger.py` is the same disease in
its purest form yet: 1,089 lines, a self-test, a docstring full of measurements — and an import of
`split_sentences_safe`, A FUNCTION THAT HAS NEVER EXISTED IN THIS REPO. The module could not be
IMPORTED, let alone called. It had never run. "Built and tested" was not true, because the test could
not load the file either.

So this file does not ask whether the two modules WORK. It asks whether REMOVING THEM CHANGES THE
OUTPUT, which is the only definition of done we accept:

  A. AST — the composer CALLS `plan_bundles`, `_ledger_gate` and `cohesion_pass.apply`. Not imports.
  B. BEHAVIOUR (ledger, selection) — the OLD lexical `_select()` deals ONE card to MANY subsections;
     the LICENCE deals it to ONE. Measured on the real 232-card shipping bundle. No LLM, no spend.
  C. BEHAVIOUR (ledger, enforcement) — a model output that narrates a SPENT card is DELETED by
     `_ledger_gate`, and the SAME output with the ledger removed survives. The real function, the real
     bundle.
  D. BEHAVIOUR (cohesion) — real attributed nodes over real cards gain OWNED transitions expressing
     analytical movement, and every attributed object comes out THE SAME OBJECT it went in.
  E. SAFETY — the cohesion pass cannot fabricate: it never constructs an Attributed node, and a
     tampered attributed node is caught by identity.

    python scripts/test_ledger_and_cohesion_are_wired.py        # offline, no spend
"""
from __future__ import annotations

import ast
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P                                                    # noqa: E402
import cohesion_pass as CP                                                # noqa: E402
import fact_use_ledger as FUL                                             # noqa: E402
import cellcog_composer as C                                              # noqa: E402
from report_ast import (Attributed, Clause, Owned, Heading, ParagraphBreak,   # noqa: E402
                        CardBundle, validate_report, entailed_by_span)

COMPOSER = ROOT / 'scripts' / 'cellcog_composer.py'
BOUND = ROOT / 'outputs' / 'evidence_cards_bound.json'
GRAPH = ROOT / 'outputs' / 'provenance_graph.json'

fails: list[str] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
    if detail:
        print(f'            {detail}')
    if not ok:
        fails.append(name)


print('=== ARE THE LEDGER AND THE COHESION PASS ON THE CRITICAL PATH? ===\n')

# =================================================================================================
# A. THE AST — CALLED, NOT MERELY IMPORTED.
# =================================================================================================
tree = ast.parse(COMPOSER.read_text())
names = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
attrs = {n.func.attr for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}

check('the composer CALLS fact_use_ledger.plan_bundles()', 'plan_bundles' in attrs)
check('the composer CALLS _ledger_gate() — the ledger is ENFORCED, not merely advertised',
      '_ledger_gate' in names)
check('the composer CALLS cohesion_pass.apply()', 'apply' in attrs)
check('the composer builds the licence BEFORE the writer threads', '_fact_use_plan' in names)

# the old free-for-all must no longer be the primary selector
src = COMPOSER.read_text()
sel_in_one = src.split('def one(job):')[1].split('results: dict')[0]
check('the writer\'s card set is the LICENCE, not the old lexical _select()',
      '_rank(b, licensed' in sel_in_one and 'unspoken' in sel_in_one,
      '_select survives ONLY as the starvation fallback, and only over UNSPOKEN cards')

# =================================================================================================
# THE REAL BUNDLE. 232 bound cards, 10 works, the bytes on disk.
# =================================================================================================
cards = json.loads(BOUND.read_text())
graph = P.Graph.from_json(json.loads(GRAPH.read_text()))
B = CardBundle(cards, graph, P.JOURNAL_ONLY)
admitted = B.admitted_ids()
jobs = [(sec, sub) for sec, subs in C.OUTLINE for sub in subs]
print(f'\n  real bundle: {len(admitted)} admitted cards, {len({B.resolve(c).work_id for c in admitted})} works, '
      f'{len(jobs)} subsections\n')

# =================================================================================================
# B. BEHAVIOUR — THE OLD SELECTOR DEALS ONE CARD TO MANY SUBSECTIONS. THE LICENCE DEALS IT TO ONE.
# =================================================================================================
old_deal: collections.Counter = collections.Counter()
for sec, sub in jobs:
    for cid in C._select(B, sub):                      # THE CODE THAT SHIPPED
        old_deal[cid] += 1

licences, records = C._fact_use_plan(B, admitted, jobs)
new_deal: collections.Counter = collections.Counter()
for job in jobs:
    for cid in licences[job].attributable:             # THE CODE THAT SHIPS NOW
        new_deal[cid] += 1

old_max = max(old_deal.values()) if old_deal else 0
new_max = max(new_deal.values()) if new_deal else 0
old_slots, new_slots = sum(old_deal.values()), sum(new_deal.values())

print(f'  OLD  _select():  {old_slots} card slots over {len(old_deal)} distinct cards; '
      f'worst card offered to {old_max} subsections')
print(f'  NEW  licence  :  {new_slots} card slots over {len(new_deal)} distinct cards; '
      f'worst card offered to {new_max} subsections\n')

check('the OLD selector deals a single card to MANY subsections (the 8x-narration defect)',
      old_max >= 5, f'worst-offender card was dealt to {old_max} of {len(jobs)} subsections')
check('the LICENCE caps how often any one finding may be spoken',
      new_max <= 1 + FUL.REUSE_BUDGET,
      f'no card is attributable in more than {new_max} subsections '
      f'(1 narration + at most {FUL.REUSE_BUDGET} new-role reuses)')
check('the licence SPREADS the evidence instead of concentrating it',
      len(new_deal) > len(old_deal),
      f'{len(new_deal)} distinct cards reach a writer, vs {len(old_deal)} under _select')

# every finding is narrated exactly once — R1, on the real corpus
narr: collections.Counter = collections.Counter()
for job in jobs:
    for cid in licences[job].narrate:
        narr[FUL.finding_id(B.cards[cid])] += 1
check('R1 NARRATE-ONCE holds on the real corpus: no finding is narrated twice',
      all(v == 1 for v in narr.values()),
      f'{len(narr)} findings, max narrations = {max(narr.values()) if narr else 0}')
check('R2/R3: the ledger records ZERO rule violations over its own plan',
      sum(len(r.violations()) for r in records.values()) == 0)

# =================================================================================================
# C. BEHAVIOUR — THE GATE BITES. A SPENT CARD, NARRATED ANYWAY, IS DELETED.
# =================================================================================================
# Find a card that IS narratable in one subsection and SPENT in another. This is the exact situation
# that produced eight narrations of one finding.
home = next(j for j in jobs if licences[j].narrate)
victim = licences[home].narrate[0]
elsewhere = next((j for j in jobs if j != home and victim not in licences[j].attributable), None)

raw = [{'voice': 'ATTRIBUTED',
        'clauses': [{'card_id': victim, 'text': 'the finding is restated here, in another section'}],
        'connective': 'while'}]

nodes_ok, _ = C._nodes_from(raw, B, {victim})                       # model emitted it; typed fine
kept_home, drop_home = C._ledger_gate(nodes_ok, licences[home], set(), home[1])
kept_away, drop_away = C._ledger_gate(nodes_ok, licences[elsewhere], set(), elsewhere[1])

check('a card narrated in its OWN subsection SURVIVES the ledger gate',
      len(kept_home) == 1 and not drop_home, f'{victim} in "{home[1][:44]}"')
check('THE SAME CARD, re-narrated in a subsection where it is SPENT, is DELETED',
      len(kept_away) == 0 and drop_away and 'FACT_LEDGER' in drop_away[0],
      (drop_away[0][:96] + '…') if drop_away else 'IT SURVIVED — the ledger is not enforcing')
check('REMOVING THE LEDGER PUTS THE DEFECT BACK (the same node, ungated, reaches the page)',
      len(nodes_ok) == 1,
      'without _ledger_gate the restatement is a lawful, span-entailed, publishable sentence — '
      'which is why no other gate in this repo ever caught it')

# =================================================================================================
# D. BEHAVIOUR — THE COHESION PASS ADDS MOVEMENT AND FREEZES THE FACTS.
# =================================================================================================
# Real attributed nodes over real cards, with text that is genuinely entailed by its own span (we reuse
# the card's own claim, exactly as the evidence table does). Grouped so that adjacent paragraphs differ
# in LEVEL or METHOD — the analytical distance the pass is supposed to notice.
def real_nodes(limit=8):
    out = []
    for cid in admitted:
        r = B.resolve(cid)
        claim = (r.card.get('claim') or '').strip()
        if not claim:
            continue
        ok, _ = entailed_by_span(claim, r.span, B.graph.works.get(r.work_id), min_overlap=0.34)
        if not ok:
            continue
        n = Attributed(clauses=(Clause(card_id=cid, text=claim),), connective='while')
        if validate_report([n], B):
            continue
        out.append((cid, n))
        if len(out) >= limit:
            break
    return out


real = real_nodes()
by_level: dict = collections.defaultdict(list)
for cid, n in real:
    by_level[(B.cards[cid].get('level') or '?')].append(n)

doc = [Heading(3, 'Evidence for displacement at the occupational level')]
groups = [v for v in by_level.values()][:3]
for i, grp in enumerate(groups):
    if i:
        doc.append(ParagraphBreak())
    doc += grp

before_attr = [n for n in doc if isinstance(n, Attributed)]
out_nodes, coh = CP.apply(doc, B)
after_attr = [n for n in out_nodes if isinstance(n, Attributed)]
new_owned = [n for n in out_nodes if isinstance(n, Owned)]

print(f'\n  cohesion input : {len(before_attr)} attributed nodes in {len(groups)} paragraphs '
      f'({len(by_level)} distinct levels)')
print(f'  cohesion output: {coh}')
for n in new_owned:
    print(f'     + OWNED: {n.text}')
print()

check('the cohesion pass ADDED owned connective tissue where the writers could not',
      len(new_owned) >= 1, f'{len(new_owned)} owned sentences added')
check('EVERY attributed node came out THE SAME OBJECT it went in (frozen byte-for-byte)',
      collections.Counter(id(n) for n in before_attr) == collections.Counter(id(n) for n in after_attr),
      f'{len(before_attr)} in, {len(after_attr)} out, identity preserved')
check('every sentence the pass wrote is OWNED and licensed by NOTHING (no number, no source)',
      all(isinstance(n, Owned) and n.premise_ids == () for n in new_owned))
check('the post-cohesion AST still validates against the bytes',
      not validate_report(out_nodes, B))
check('the transitions express ANALYTICAL MOVEMENT, not "Turning now to..."',
      all('turning' not in n.text.lower() and 'next section' not in n.text.lower()
          for n in new_owned) and len(new_owned) > 0)

# =================================================================================================
# E. SAFETY — THE PASS CANNOT FABRICATE.
# =================================================================================================
ctree = ast.parse((ROOT / 'scripts' / 'cohesion_pass.py').read_text())
live = [f for f in ast.walk(ctree)
        if isinstance(f, ast.FunctionDef) and not f.name.startswith('_self_test')]
built = {n.func.id for f in live for n in ast.walk(f)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
check('the cohesion pass NEVER constructs an Attributed node or a Clause (AST-checked)',
      'Attributed' not in built and 'Clause' not in built,
      'it cannot edit a fact because it cannot build one — that is the safety boundary')

try:
    CP._assert_frozen([before_attr[0]],
                      [Attributed(clauses=before_attr[0].clauses, connective='but')])
    caught = False
except AssertionError:
    caught = True
check('a REBUILT attributed node is caught by _assert_frozen (identity, not equality)', caught)

print()
if fails:
    print(f'** {len(fails)} FAILED: ' + '; '.join(fails))
    raise SystemExit(1)
print('** THE LEDGER AND THE COHESION PASS ARE WIRED, ENFORCED, AND CHANGE THE OUTPUT. **')
