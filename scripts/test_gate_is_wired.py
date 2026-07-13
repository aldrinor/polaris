#!/usr/bin/env python3
"""CI CANARY — FAILS IF THE FAITHFULNESS GATE IS BYPASSED.

WHY THIS EXISTS, IN ONE PARAGRAPH:
I built `synthesis_contract.py`, ran 14 adversarial attacks I had written myself, watched it print
"ZERO FALSE ADMISSIONS", and reported it as working. An adversarial reviewer then found that
`validate()` was imported at `cellcog_composer.py:49` and **never called anywhere in the repo except
its own self_test()**. The gate was a closed loop: invoked only by its own test, fed its own examples,
printing green. It had never seen a sentence from the pipeline. Behind that unlocked door, 43% of our
evidence-card mechanisms were pure LLM invention.

A self-test that passes because the gate returns True in isolation is worth NOTHING.
This test FAILS IF THE GATE IS NOT ON THE CRITICAL PATH. That is a different thing, and it is the only
kind of test that would have caught the bug.

    python scripts/test_gate_is_wired.py
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSER = ROOT / 'scripts' / 'cellcog_composer.py'
CARDS = ROOT / 'outputs' / 'evidence_cards.json'

fails: list[str] = []


def check(name: str, ok: bool, detail: str = '') -> None:
    print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
    if detail:
        print(f"            {detail}")
    if not ok:
        fails.append(name)


print('=== CI CANARY: IS THE FAITHFULNESS GATE ACTUALLY ON THE CRITICAL PATH? ===\n')

src = COMPOSER.read_text()
tree = ast.parse(src)

# 1. validate() must be CALLED, not merely imported. This is the exact bug that shipped.
calls = {n.func.id for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
check('validate() is CALLED in the composer (not just imported)',
      'validate' in calls,
      'imported at :49 and never called — the gate has never seen a real sentence' if 'validate' not in calls else '')

# 2. the mechanism field must be span-gated at extraction
mech_gated = bool(re.search(r'mechanism gate|m_words\s*&\s*span_words', src))
check('the `mechanisms` field is span-checked at extraction',
      mech_gated,
      'mechanisms copied raw from LLM output -> 43% pure invention' if not mech_gated else '')

# 3. no card on disk may carry a mechanism absent from its own span
if CARDS.exists():
    cards = json.loads(CARDS.read_text())
    norm = lambda s: re.sub(r'\s+', ' ', (s or '').lower())
    bad = []
    for c in cards:
        sw = {w for w in re.findall(r'[a-z]{4,}', norm(c.get('span')))}
        for m in (c.get('mechanisms') or []):
            mw = {w for w in re.findall(r'[a-z]{4,}', m.lower())}
            if mw and len(mw & sw) / len(mw) < 0.6:
                bad.append((m, (c.get('authors') or ['?'])[0], c.get('year')))
    check(f'zero fabricated mechanisms in {CARDS.name}',
          not bad,
          f'{len(bad)} mechanisms not present in their own span, e.g. "{bad[0][0]}" -> {bad[0][1]} ({bad[0][2]})' if bad else '')
else:
    print('  [skip] no evidence_cards.json on disk yet')

# 4. THE ATTACK CASES. The gate must REJECT a fabricated binding assembled from REAL particulars.
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    from synthesis_contract import Premise, Synthesis, validate  # noqa: E402
    P = {
        'p1': Premise('p1', 'Computer automation of such work has been correspondingly limited in its scope.',
                      'Bresnahan et al. (2002), Quarterly Journal of Economics',
                      level='firm', horizon='long-run', method='observational', mechanisms=[]),
        'p2': Premise('p2', 'Routine task-intensive occupations declined as computerisation spread.',
                      'Autor et al. (2003), Quarterly Journal of Economics',
                      level='occupation', horizon='long-run', method='observational',
                      mechanisms=['task displacement']),
    }
    # THE EXACT FABRICATION FOUND ON DISK: a real mechanism bound to the wrong paper.
    ok, why = validate(Synthesis('CONTRASTS_LEVEL', ['p1', 'p2'],
                                 'These findings are attributable to task displacement, which Bresnahan '
                                 'and colleagues establish as the operative channel.'), P)
    check('gate REJECTS a real mechanism bound to a paper that never states it',
          not ok, f'ADMITTED IT: {why or "no reason"}' if ok else f'rejected: {why}')
except Exception as e:
    check('synthesis_contract importable', False, str(e))

# 5. THE TEST THAT WOULD HAVE CAUGHT THE INVERSION.
#    The canary passed while the fabrication shipped, because it tested the gate in MY phrasing and the
#    composer emits the phrasing MY OWN WRITER PROMPT MANDATES ("Writing in the <JOURNAL>, <AUTHORS> show
#    that ..."). That form matched the attribution regex, so the gate was SKIPPED ENTIRELY.
#    A canary that only tests the phrasing you thought of is not a canary.
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import importlib.util as _u
    _sp = _u.spec_from_file_location('cc', COMPOSER)
    cc = _u.module_from_spec(_sp)
    _sp.loader.exec_module(cc)
    bres = {'authors': ['Bresnahan', 'Brynjolfsson'], 'year': 2002,
            'span': 'Computer automation of such work has been correspondingly limited in its scope.',
            'claim': 'Computer automation of routine work has been limited in scope.',
            'source': 'Bresnahan et al. (2002), Quarterly Journal of Economics', 'mechanisms': []}
    # THE EXACT FORM THE WRITER PROMPT MANDATES -- the one that used to bypass the gate completely.
    shipped, _ = cc._clean(
        'Writing in the Quarterly Journal of Economics in 2002, Bresnahan et al. show that task '
        'displacement is the operative channel driving occupational decline.', [bres])
    check('ATTRIBUTED lane is GATED in the form the writer prompt mandates',
          shipped.strip() == '',
          'THE FABRICATION SHIPPED: it names Bresnahan and reports something Bresnahan never says'
          if shipped.strip() else '')
    # a fabricated NUMBER credited to a real paper
    shipped2, _ = cc._clean(
        'Writing in the Quarterly Journal of Economics in 2002, Bresnahan et al. show that 47 percent '
        'of employment is at risk of computerisation.', [bres])
    check('ATTRIBUTED number not in the source is REJECTED',
          shipped2.strip() == '',
          'A FABRICATED NUMBER SHIPPED under a real citation' if shipped2.strip() else '')
except Exception as e:
    check('composer gate importable', False, str(e))

# ---------------------------------------------------------------------------------------------
# CHECK THE ARTIFACT, NOT THE CODE.
#
# Every defect that has cost us a turn got past a GREEN canary, because the canary tested a CODE
# PATH in a phrasing I invented, and the judge reads a FILE.
#   - the gate inversion:   the fabrication was rejected in MY phrasing, admitted in the writer's.
#   - the 'the The' bug:    the fix ran AFTER write_text() on a dead variable. The stats printed the
#                           CORRECTED string; the disk kept the BROKEN one. Both looked fine.
# The only question that cannot be fooled is: WHAT IS IN THE FILE THE JUDGE WILL READ?
# ---------------------------------------------------------------------------------------------
rep = ROOT / 'outputs' / 'cellcog_arm' / 'report.md'
if rep.exists():
    art = rep.read_text()
    n_the = len(re.findall(r'\bthe The\b', art))
    check('SHIPPED ARTIFACT: no "the The <Journal>" doubling',
          n_the == 0, f'{n_the} in the file the judge reads')
    orphan = [p for p in art.split('\n\n')
              if re.match(r'^\*{0,2}\[[A-Za-z /-]+\]\*{0,2}[.:]?$', p.strip())]
    check('SHIPPED ARTIFACT: no paragraph the gate emptied to a bare label',
          not orphan, f'{len(orphan)} orphan label(s): {orphan[:2]}')
    check('SHIPPED ARTIFACT: no [n] citation markers (the cleaner deletes them anyway)',
          not re.search(r'\[\d+\]', art), 'markers present')

print()
if fails:
    print(f'** {len(fails)} FAILURE(S). THE DOOR IS OPEN. NOTHING SHIPS. **')
    for f in fails:
        print(f'    - {f}')
    raise SystemExit(1)
print('** GATE IS WIRED AND ON THE CRITICAL PATH. **')
