#!/usr/bin/env python3
"""CI CANARY — FAILS IF THE FAITHFULNESS GATE IS BYPASSED.

WHY THIS EXISTS, IN ONE PARAGRAPH:
I built `synthesis_contract.py`, ran 14 adversarial attacks I had written myself, watched it print "ZERO
FALSE ADMISSIONS", and reported it as working. An adversarial reviewer then found that `validate()` was
imported at `cellcog_composer.py:49` and **never called anywhere in the repo except its own self_test()**.
The gate was a closed loop: invoked only by its own test, fed its own examples, printing green.

WHY IT WAS REWRITTEN — AND THIS IS THE WHOLE LESSON OF THE NIGHT:
This canary then went 16/16 GREEN while SIX ADVERSARY ATTACKS SUCCEEDED and nothing had been weakened.
It was not defeated. It was ORPHANED. It drove `cellcog_composer._clean()` with hand-built dicts —
`{'authors': [...], 'span': '...'}` — and the fabrication had moved to a lane where cards carry
manifestations and content hashes. **THE CHECKS CERTIFIED A LANE THE FABRICATION NO LONGER USED.**

A canary that tests a dead function is worse than no canary, because it is green.

So every fixture here is now a BOUND card in a real graph (`_test_fixtures.py`), and every check drives
THE CODE THAT ACTUALLY SHIPS: `report_ast.validate_report()` -> `publisher.publish()` -> the sealed
release directory. If the composer, the AST or the publisher stops calling the gate, this goes red.

    python scripts/test_gate_is_wired.py
"""
from __future__ import annotations

import ast
import inspect
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import hashlib                                                            # noqa: E402
import provenance as P                                                    # noqa: E402
import report_ast as A                                                    # noqa: E402
import publisher                                                          # noqa: E402
import _test_fixtures                                                     # noqa: E402
import test_fabrication_paths as _FAB                                     # noqa: E402
from report_ast import (Attributed, Clause, Owned, Heading, EvidenceTable,  # noqa: E402
                        CardBundle, set_entailment_judge)

COMPOSER = ROOT / 'scripts' / 'cellcog_composer.py'
MINER = ROOT / 'scripts' / 'evidence_miner.py'
BOUND = ROOT / 'outputs' / 'evidence_cards_bound.json'
RELEASE = publisher.RELEASE / 'report.md'

fails: list[str] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
    if detail and not ok:
        print(f'            {detail}')
    if not ok:
        fails.append(name)


print('=== CI CANARY: IS THE FAITHFULNESS GATE ACTUALLY ON THE CRITICAL PATH? ===\n')

g, CARDS = _test_fixtures.build()
B = CardBundle(CARDS, g, P.JOURNAL_ONLY)

# =================================================================================================
# 1-2. THE GATE IS CALLED. This is the exact bug that shipped: imported, never invoked.
# =================================================================================================
csrc = COMPOSER.read_text()
ctree = ast.parse(csrc)
ccalls = {n.func.id for n in ast.walk(ctree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
cattrs = {n.func.attr for n in ast.walk(ctree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}

check('the composer CALLS the AST validator (not just imports it)',
      'validate_report' in ccalls,
      'validate_report is imported and never called — the gate has never seen a real sentence')
check('the composer CALLS the publisher (the release is not written by the composer)',
      'publish' in cattrs)

asrc = inspect.getsource(A)
atree = ast.parse(asrc)
acalls = {n.func.id for n in ast.walk(atree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
aattrs = {n.func.attr for n in ast.walk(atree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
check('the AST CALLS synthesis_contract.validate() on the owned lane',
      'validate' in acalls)
check('the AST CALLS graph.verify_span() — the bytes are re-checked, not trusted',
      'verify_span' in aattrs)
check('the AST CALLS graph.resolve_attribution() — the policy decides what may be named',
      'resolve_attribution' in aattrs)

# =================================================================================================
# 3-4. THE MECHANISM LAUNDER. 43% of our card mechanisms were pure invention.
# =================================================================================================
msrc = MINER.read_text()
check('the `mechanisms` field is span-checked where cards are MINED',
      bool(re.search(r'mechanism|m_words\s*&\s*span_words|MECH', msrc)),
      'mechanisms copied raw from LLM output -> 43% pure invention')

if BOUND.exists():
    cards = json.loads(BOUND.read_text())
    bad = []
    for c in cards:
        sw = {w for w in re.findall(r'[a-z]{4,}', re.sub(r'\s+', ' ', (c.get('span') or '').lower()))}
        for m in (c.get('mechanisms') or []):
            mw = {w for w in re.findall(r'[a-z]{4,}', m.lower())}
            if mw and len(mw & sw) / len(mw) < 0.6:
                bad.append((m, (c.get('authors') or ['?'])[0], c.get('year')))
    check(f'zero fabricated mechanisms in the SHIPPING bundle ({BOUND.name}, {len(cards)} cards)',
          not bad,
          f'{len(bad)} mechanisms absent from their own span, e.g. "{bad[0][0]}" -> {bad[0][1]}'
          if bad else '')
else:
    check(f'the shipping card bundle exists ({BOUND.name})', False,
          'run scripts/quarantine.py — the composer has no lane to read')

# THE EXACT FABRICATION FOUND ON DISK: a real mechanism, bound to a paper that never states it.
check('the gate REJECTS a real mechanism bound to a paper that never states it',
      bool(A.validate_report(
          [Attributed(clauses=(Clause('c:bres',
                                      'task displacement is the operative channel driving occupational '
                                      'decline'),))], B)),
      'ADMITTED IT — "task displacement" is Autor\'s term and Bresnahan\'s span does not contain it')

# =================================================================================================
# 5-11. THE ATTRIBUTED LANE. A lie here is FRAUD.
# =================================================================================================
check('a TRUE finding, present in its own span, REACHES THE PAGE',
      not A.validate_report(
          [Attributed(clauses=(Clause('c:autor', _test_fixtures.AUTOR_SPAN),))], B),
      'real evidence deleted — the gate is starving again')

check('an ATTRIBUTED number that is not in the cited source is REJECTED',
      bool(A.validate_report(
          [Attributed(clauses=(Clause('c:bres', '47 percent of employment is at risk of '
                                                'computerisation'),))], B)),
      'A FABRICATED NUMBER SHIPPED under a real citation')

# THE SUBSTRING LEAK: `"0.2" in "10.25"` is True. c:leak's span really does say 10.25.
check('an ATTRIBUTED number that is only a SUBSTRING of a source number is REJECTED',
      bool(A.validate_report(
          [Attributed(clauses=(Clause('c:leak', 'employment fell by 0.2 percentage points per '
                                                'robot'),))], B)),
      'a fabricated 0.2 passed because the source happened to say 10.25')

# CROSS-SOURCE SYNTHESIS — the joint-heaviest criterion on the board (w=0.0800). The old gate deleted
# EVERY one of these, which is why our synthesis section was 210 words out of 8,012.
synth = [Attributed(clauses=(
    Clause('c:autor', _test_fixtures.AUTOR_SPAN),
    Clause('c:bres', 'computer automation of such work has been correspondingly limited in its scope')),
    connective='while')]
check('CROSS-SOURCE SYNTHESIS survives the gate (it is the heaviest criterion, w=0.0800)',
      not A.validate_report(synth, B),
      'the comparison was DELETED — critical synthesis cannot reach the judge')

check('a fabricated binding is REJECTED even when hidden inside a comparison',
      bool(A.validate_report([Attributed(clauses=(
          Clause('c:autor', 'computer capital substitutes for workers in routine tasks'),
          Clause('c:bres', 'task displacement drives the labor share down')), connective='while')], B)),
      'the multi-source lane let a fabricated binding through')

# THE EVIDENCE-LAUNDERING ATTACK. The gate used to validate against `span + claim`, and `claim` is
# WRITTEN BY THE MODEL. So: model writes claim -> writer sees only claim -> gate checks writing against
# claim. THE GATE VALIDATED THE MODEL AGAINST ITSELF.
laundered = dict(CARDS[0], claim='Computerisation reduced employment by 47 percent across affected firms.')
check('EVIDENCE LAUNDERING: a figure the extractor invented in `claim` is REJECTED',
      bool(A.validate_report(
          [Attributed(clauses=(Clause('c:bres', 'computerisation reduced employment by 47 percent across '
                                                'affected firms'),))],
          CardBundle([laundered], g, P.JOURNAL_ONLY))),
      'THE MODEL VALIDATED ITSELF — a fabricated number shipped under a real citation')

check('the gate NEVER validates against the model-authored `claim`',
      not re.search(r"(?m)^\s*src\s*=\s*f?['\"]?\{?span\}?\s*\{?claim\}?", asrc)
      and 'claim' not in inspect.signature(A.entailed_by_span).parameters,
      'the evidence-laundering path is open again: the gate validates the model against itself')

# =================================================================================================
# 12-14. THE NEW LAW — the lanes that did not exist when this canary was written.
# =================================================================================================
# THE P0. Working-paper bytes wearing a journal's name. This is the card that scored us 0.4603.
r = B.resolve('c:ar')
check('THE P0: working-paper bytes labelled "Journal of Political Economy" CANNOT BE CITED',
      not r.ok and 'SOURCE_POLICY' in (r.refusal or ''),
      f'IT RESOLVED, and would have printed: {r.attribution!r}')

check('an UNBOUND card (a DOI and a span, no manifestation) is REFUSED',
      not CardBundle([{'id': 'x', 'span': 'anything', 'claim': 'anything', 'authors': ['Z'],
                       'doi': '10.1/x', 'venue': 'Nature'}], g, P.JOURNAL_ONLY).resolve('x').ok,
      'a card with no bytes behind it was admitted — a DOI names a work, and a work has no bytes')

check('the model may NOT name a source in its prose (voice is never inferred from surnames)',
      bool(A.validate_report(
          [Attributed(clauses=(Clause('c:autor', 'Bresnahan and colleagues show that computer capital '
                                                 'substitutes for workers in routine tasks'),))], B)),
      'the model typed a citation, and the gate accepted its choice of source')

check('an OWNED sentence may not carry a number, and may not name a source',
      bool(A.validate_report([Owned(text='the effect is about 5 percentage points')], B))
      and bool(A.validate_report([Owned(text='Acemoglu is right about this')], B)))

# =================================================================================================
# 11b. THE ENTAILMENT-JUDGE BATTERY — SOL'S SYNONYM/MAGNITUDE/SCOPE/MODALITY BURNS + THE 8th.
#
# The prior fix replaced a bag-of-words check with a BIGGER 40-word DIRECTION LEXICON, and a fresh
# adversary walked past it on first contact with a SYNONYM ('rose' rendered 'plunged'). These checks
# drive `validate_report`/`render` against a REAL bound graph. Every attack MUST be REJECTED; the two
# positive controls MUST SHIP. The judge is REAL (production llm()) unless a check injects a stub.
# =================================================================================================
_JB = _FAB.build_bundle()            # c:up (rose 1.5 pts), c:down, c:firm, c:up_rev — all bound
_JG = _JB.graph
_JFILLER = _FAB._FILLER


def _add(cid, span, claim, authors, year, venue, **facets):
    """Bind ONE more real journal card THE PRODUCTION WAY (ensure_work -> ingest_bytes ->
    derive_binding_core), so its identity is EARNED (`VERSION_OF_PUBLISHED`) and the finding reaches the
    entailment judge instead of being masked by a `None`-identity source-policy refusal."""
    wid, eid, mid = f'w:{cid}', f'e:{cid}', f'm:{cid}'
    m = _test_fixtures._ingest(_JG, mid=mid, doi=f'10.8/{wid}', title='A study', authors=authors,
                               year=year, venue=venue, span=span, kind='journal')
    text = m.text
    s = text.index(span)
    bnd = _JG.bind_span(mid, s, s + len(span))
    att = _JG.resolve_attribution(bnd, P.JOURNAL_ONLY)
    return dict(id=cid, manifestation_id=mid, content_hash=bnd['content_hash'],
        span_start=s, span_end=s + len(span), span_raw=bnd['text'], span=span, claim=claim,
        expression_id=bnd['expression_id'],
        permitted_expression_ids=list(bnd['permitted_expression_ids']),
        attribution_target_expression_id=att.names_expression_id,
        work_id=wid, evidence_unit_id=wid, authors=authors, year=year, venue=venue,
        level=facets.get('level', 'region'), horizon=facets.get('horizon', 'long-run'),
        method=facets.get('method', 'observational'), mechanisms=facets.get('mech', []),
        corroborating_sources=[], source_version=_JG.manifestations[mid].content_hash[:12],
        text_field='fulltext')


_extra = [
    _add('c:assoc', 'exposure to the pesticide is associated with elevated cancer incidence in farm workers',
         'exposure to the pesticide is associated with elevated cancer incidence in farm workers',
         ['Nurse'], 2020, 'The Lancet'),
    _add('c:us', 'the unemployment rate rose by 3 percent in the United States during the study window',
         'the unemployment rate rose by 3 percent in the United States during the study window',
         ['Katz'], 2018, 'Quarterly Journal of Economics'),
    _add('c:decl', 'employment showed a decline in the regions that adopted the technology',
         'employment showed a decline in the regions that adopted the technology',
         ['Autor'], 2015, 'Journal of Economic Perspectives'),
    _add('c:adopt3', '3 percent of firms adopted the technology during the study window',
         'unemployment rose by 3 percent during the study window',
         ['Katz'], 2018, 'Quarterly Journal of Economics'),
    _add('c:plunge', _FAB.ROSE_SPAN, 'the local employment-to-population ratio plunged by 1.5 points',
         ['Bloom', 'Draca'], 2021, 'American Economic Review'),
    _add('c:metq', _FAB.ROSE_SPAN,
         'the local employment-to-population ratio rose by one and a half points',
         ['Bloom', 'Draca'], 2021, 'American Economic Review'),
]
_JB = CardBundle(list(_JB.cards.values()) + _extra, _JG, P.JOURNAL_ONLY)


def _attr(cid, text):
    return [Attributed(clauses=(Clause(cid, text),))]


def _rej(cid, text):
    return bool(A.validate_report(_attr(cid, text), _JB))


set_entailment_judge(None)                      # the REAL production judge decides the semantic burns

# ---- SIGN FLIP via OUT-OF-LEXICON synonym / metaphor (span says ROSE) --------------------------------
for _w, _p in [('plunged', 'the local employment-to-population ratio plunged by 1.5 points in regions that adopted the technology'),
               ('cratered', 'the local employment-to-population ratio cratered in regions that adopted the technology'),
               ('evaporated', 'local employment-to-population gains evaporated in regions that adopted the technology'),
               ('went south', 'the local employment-to-population ratio went south in regions that adopted the technology')]:
    check(f'SIGN FLIP via synonym "{_w}" (span says ROSE) is REJECTED', _rej('c:up', _p),
          'the judge admitted a reversed finding — the synonym walked past the lexicon')

# ---- MAGNITUDE fabrication (span says "1.5 points") --------------------------------------------------
check('MAGNITUDE "doubled" (span says "1.5 points") is REJECTED',
      _rej('c:up', 'the local employment-to-population ratio doubled in regions that adopted the technology'))
check('MAGNITUDE "tripled" (span says "1.5 points") is REJECTED',
      _rej('c:up', 'the local employment-to-population ratio tripled in regions that adopted the technology'))

# ---- SCOPE swap, identical numbers (span says "in the United States") --------------------------------
check('SCOPE "worldwide" over span "in the United States" is REJECTED',
      _rej('c:us', 'the unemployment rate rose by 3 percent worldwide during the study window'))
check('SCOPE "across every advanced economy" over span "in regions that adopted" is REJECTED',
      _rej('c:up', 'the local employment-to-population ratio rose by 1.5 points across every advanced economy'))

# ---- MODALITY flip: verb ("causes" vs "associated with") AND noun ("collapse" vs "a decline") --------
check('MODALITY "causes" over span "is associated with" is REJECTED',
      _rej('c:assoc', 'exposure to the pesticide causes elevated cancer incidence in farm workers'))
check('MODALITY-BY-NOUN "the collapse of employment" over span "a decline" is REJECTED',
      _rej('c:decl', 'the collapse of employment in the regions that adopted the technology was severe'))

# ---- WRONG QUANTITY: the span's number attached to a DIFFERENT quantity (survives the number filter) --
check('WRONG-QUANTITY "unemployment rose 3 percent" over span "3 percent of firms ADOPTED" is REJECTED',
      _rej('c:adopt3', 'unemployment rose by 3 percent among workers during the study window'))

# ---- NUMBER-WORD: spelled WRONG value rejected; spelled SAME value ships -----------------------------
check('NUMBER-WORD wrong value "two and a half points" (span "1.5 points") is REJECTED',
      _rej('c:up', 'the local employment-to-population ratio rose by two and a half points in regions that adopted the technology'))
check('NUMBER-WORD same value "one and a half points" (span "1.5 points") SHIPS (no false positive)',
      not _rej('c:metq', 'the local employment-to-population ratio rose by one and a half points in regions that adopted the technology'))

# ---- MULTI-SENTENCE node: a true clause + a fabricated SECOND sentence -------------------------------
check('TRUE clause + a fabricated SECOND sentence in one node is REJECTED',
      _rej('c:up', 'the local employment-to-population ratio rose by 1.5 points in regions that adopted '
                   'the technology. The effect was fatal for every worker in the country.'))

# ---- TABLE row: real number, wrong sign via synonym -------------------------------------------------
check('TABLE row "plunged by 1.5 points" over span "rose by 1.5 points" is REJECTED',
      bool(A.validate_report([EvidenceTable(card_ids=('c:plunge',))], _JB)))

# ---- POSITIVE CONTROL: a TRUE finding, faithful to its span, still SHIPS (real judge) ----------------
check('POSITIVE CONTROL: a TRUE "rose by 1.5 points" finding STILL SHIPS (real judge says ENTAILED)',
      not _rej('c:up', 'the local employment-to-population ratio rose by 1.5 points in regions that adopted the technology'),
      'the judge starved a faithful finding — false-positive regression')

# ---- THE JUDGE IS ACTUALLY CALLED (not fenced behind a residue detector) -----------------------------
_spy = {'n': 0, 'saw': None}
def _spy_judge(clause, span):
    _spy['n'] += 1
    _spy['saw'] = (clause, span)
    return ('ENTAILED', 'stub')
set_entailment_judge(_spy_judge)
_ok = not A.validate_report(_attr('c:up',
    'the local employment-to-population ratio cratered in regions that adopted the technology'), _JB)
check('THE JUDGE IS CALLED on a clause NO deterministic rule catches ("cratered")',
      _spy['n'] >= 1 and _ok,
      'the judge was never consulted for a bare synonym — it is fenced behind a residue again')

# ---- FAIL CLOSED: judge unavailable / uncertain / garbage => REJECT (never admit) --------------------
def _raise(clause, span):
    raise RuntimeError('transport down')
def _timeout(clause, span):
    raise TimeoutError('deadline exceeded')
def _uncertain(clause, span):
    return ('UNCERTAIN', 'cannot tell')
def _garbage(clause, span):
    return ('???', 'unparseable')
_true = 'the local employment-to-population ratio rose by 1.5 points in regions that adopted the technology'
for _name, _fn in [('RAISES', _raise), ('TIMES OUT', _timeout),
                   ('returns UNCERTAIN', _uncertain), ('returns GARBAGE', _garbage)]:
    set_entailment_judge(_fn)
    check(f'FAIL-CLOSED: judge {_name} => a faithful finding is REJECTED (not admitted)',
          _rej('c:up', _true),
          'the validator ADMITTED when it could not check — that is the whole disease')
set_entailment_judge(None)                      # restore the real judge for anything downstream

# ---- THE 8th: OBLIQUE SOURCE in a premise-free OWNED frame (Sol NAMED this: "The Cambridge team") -----
# A premise-free OWNED sentence is licensed by nothing, so per THE LAW it may carry NO new particular and
# name NO source. `names_a_source` misses "Cambridge" (not in corpus) and the attribution regex needs the
# capital subject ADJACENT to the reporting verb — "team" (lowercase) intervenes — so the oblique source
# and the bare directional finding both slip. render() then prints them to the page.
check('OBLIQUE SOURCE owned frame "The Cambridge team found the effect reverses..." is REJECTED',
      bool(A.validate_report(
          [Owned(text='The Cambridge team found the effect reverses across the whole economy.')], _JB)),
      'ADMITTED — an oblique-source attribution + a directional finding shipped in the owned voice')
check('OBLIQUE SOURCE with "that": "The Cambridge team found that the effect reverses..." is REJECTED',
      bool(A.validate_report(
          [Owned(text='The Cambridge team found that the effect reverses across the whole economy.')], _JB)))
check('BARE DIRECTIONAL owned frame "The effect reverses across the whole economy." is REJECTED',
      bool(A.validate_report(
          [Owned(text='The effect reverses across the whole economy.')], _JB)),
      'ADMITTED — a premise-free owned frame asserted a directional finding licensed by nothing')

# =================================================================================================
# 15-17. THE ARTIFACT. The only question that cannot be fooled: WHAT IS IN THE FILE THE JUDGE READS?
# =================================================================================================
check('the judged release directory is SEALED — the composer CANNOT write the artifact',
      publisher.is_sealed(),
      'the release directory is writable: the composer can publish around the publisher')

if RELEASE.exists():
    art = RELEASE.read_text()
    side = publisher.RELEASE / 'report.bindings.json'
    check('SHIPPED ARTIFACT: no "the The <Journal>" doubling',
          not re.findall(r'\bthe The\b', art))
    check('SHIPPED ARTIFACT: no [n] citation markers (the cleaner deletes them anyway)',
          not re.search(r'\[\d+\]', art))
    check('SHIPPED ARTIFACT: no paragraph the gate emptied to a bare label',
          not [p for p in art.split('\n\n')
               if re.match(r'^\*{0,2}\[[A-Za-z /-]+\]\*{0,2}[.:]?$', p.strip())])
    check('SHIPPED ARTIFACT: it has a sentence-hash-to-binding sidecar', side.exists())
    if side.exists():
        known = {e['sentence_hash'] for e in json.loads(side.read_text())['sentences']}
        orphan = []
        for line in art.splitlines():
            t = line.strip()
            if not t or t.startswith('#') or t.startswith('|') or t.startswith('**Table'):
                continue
            for s in A.split_sentences(t):
                if A.sentence_hash(s) not in known:
                    orphan.append(s)
        check('SHIPPED ARTIFACT: EVERY sentence in it resolves to a binding',
              not orphan, f'{len(orphan)} unbound sentence(s), e.g. {orphan[:1]}')
else:
    print('  [skip] no release on disk yet (run the composer with --write)')

print()
if fails:
    print(f'** {len(fails)} FAILURE(S). THE DOOR IS OPEN. NOTHING SHIPS. **')
    for f in fails:
        print(f'    - {f}')
    raise SystemExit(1)
print('** GATE IS WIRED AND ON THE CRITICAL PATH. **')
