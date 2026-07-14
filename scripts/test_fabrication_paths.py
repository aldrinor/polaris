#!/usr/bin/env python3
"""SOL LADDER — RUNG 1: THE HOSTILE TESTS. One per burn, each driving THE REAL VALIDATOR.

Sol reviewed the reasoning engine (SOL_BURN_V10.md) and found SIX live fabrication paths plus a false
owned-verdict path. Our OWN adversarial suites all passed WHILE THE REAL VALIDATOR ADMITTED EVERY
HOSTILE INPUT. "The tests prove only that their chosen attacks were blocked."

This file is the first rung of the fix: it converts Sol's prose into EXECUTABLE PROOF that the holes are
real. Every test constructs a hostile report node and drives `report_ast.validate_report()` /
`report_ast.render()` — THE CODE THAT ACTUALLY SHIPS — against a REAL, BOUND graph (bytes on disk, real
`bind_span()`, real `verify_span()`, real `resolve_attribution()`). There is no hand-built dict and no
reimplementation of the gate anywhere below.

    CONTRACT OF EACH TEST: the hostile input MUST be REJECTED.
    PREDICTION (Sol): against HEAD, EVERY ONE IS WRONGLY ADMITTED — the gate returns zero failures.

A test "passes its own contract" only when the validator REJECTS the attack. Against HEAD we EXPECT the
contract to be VIOLATED (attack admitted). That expected-violation is this rung's deliverable: proof the
hole is open. Rung 2+ will make the validator reject these, and then these same tests will pass.

    python3 scripts/test_fabrication_paths.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import provenance as P                                                    # noqa: E402
import report_ast as A                                                    # noqa: E402
import _test_fixtures                                                     # noqa: E402
from report_ast import (Attributed, Clause, Owned, Heading,               # noqa: E402
                        EvidenceTable, CardBundle)

# =================================================================================================
# FIXTURE — a REAL bound graph. We reuse the shipping test fixture (bres/autor/leak/ar) and extend it
# with two employment-ratio journal articles whose spans we control, so the negation / units / year
# attacks mirror Sol's EXACT admitted inputs. Every manifestation below binds real bytes and every
# card is resolved through the real `bind_span` / `resolve_attribution` chain.
# =================================================================================================

# THE SPAN Sol reversed on the page. "rose ... 1.5 points". AER, 2021.
ROSE_SPAN = ('the local employment-to-population ratio rose by 1.5 points in regions that adopted '
             'the technology')
# A second, genuinely opposed employment finding from a DISTINCT source, for the false-reconciliation
# test. "declined ... 2.3 points". Review of Economic Studies, 2019.
FELL_SPAN = ('the local employment-to-population ratio declined by 2.3 points in regions that adopted '
             'the technology')
# A FIRM-LEVEL employment finding from a THIRD, distinct source. Same outcome (employment), a DIFFERENT
# unit of analysis (the firm), and the span SAYS so ("firm-level ... establishments") — so "these concern
# different units and are not directly comparable" is a PROVABLE verdict over (firm, region), where the
# same claim over two region-level findings (T7) is not.
FIRM_SPAN = ('firm-level employment expanded at the establishments that adopted the technology, relative '
             'to non-adopting firms')

_FILLER = ('The paper proceeds as follows. We describe the data, the identification strategy and the '
           'estimation. ') * 120


def build_bundle() -> CardBundle:
    """The shipping fixture, extended with two controlled employment-ratio journal articles."""
    g, cards = _test_fixtures.build()

    def add_journal(wid, eid, mid, authors, year, venue, span):
        g.works[wid] = P.Work(id=wid, title='A study of technology and employment', authors=authors,
                              year=year, venue=venue, doi=f'10.9/{wid}', kind='study')
        g.expressions[eid] = P.Expression(id=eid, work_id=wid, kind='journal_version',
                                          kind_basis='test fixture',
                                          attribution=P._attribution_for('journal_version', g.works[wid]))
        text = _FILLER + span + ' ' + _FILLER
        g.manifestations[mid] = P.Manifestation(
            id=mid, expression_id=eid, work_id=wid, text=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(), n_words=len(text.split()),
            locator='http://example/x', locator_status='RECORDED', fetched_by='test',
            text_field='fulltext',
            profile=dict(artifact_kind='journal_article', complete=True,
                         extractability=P.extractability(text), incomplete_because=[]))

    add_journal('w:up', 'e:up:j', 'm:up', ['Bloom', 'Draca'], 2021, 'American Economic Review', ROSE_SPAN)
    add_journal('w:down', 'e:down:j', 'm:down', ['Graetz', 'Michaels'], 2019,
                'The Review of Economic Studies', FELL_SPAN)
    add_journal('w:firm', 'e:firm:j', 'm:firm', ['Babina', 'Fedyk'], 2024,
                'Journal of Financial Economics', FIRM_SPAN)

    def card(cid, mid, span, claim, **kw):
        m = g.manifestations[mid]
        s = m.text.index(span)
        b = g.bind_span(mid, s, s + len(span))
        att = g.resolve_attribution(mid, P.JOURNAL_ONLY)
        w = g.works[m.work_id]
        return dict(
            id=cid, manifestation_id=mid, content_hash=b['content_hash'],
            span_start=s, span_end=s + len(span), span_raw=b['text'], span=span, claim=claim,
            expression_id=b['expression_id'],
            permitted_expression_ids=list(b['permitted_expression_ids']),
            attribution_target_expression_id=att.names_expression_id,
            work_id=m.work_id, evidence_unit_id=m.work_id, authors=w.authors, year=w.year,
            venue=w.venue, level=kw.get('level', 'region'), horizon=kw.get('horizon', 'long-run'),
            method=kw.get('method', 'observational'), mechanisms=kw.get('mech', []),
            corroborating_sources=[], source_version=m.content_hash[:12], text_field='fulltext')

    cards += [
        # A truthful "rose" card, and a REVERSED-claim twin over the SAME span with invented facets.
        card('c:up', 'm:up', ROSE_SPAN, 'the local employment-to-population ratio rose by 1.5 points'),
        card('c:up_rev', 'm:up', ROSE_SPAN,
             'the local employment-to-population ratio fell by 1.5 points',
             level='children with cancer', method='randomized trial'),
        # The opposed "declined" card, a distinct source.
        card('c:down', 'm:down', FELL_SPAN,
             'the local employment-to-population ratio declined by 2.3 points'),
        # A firm-level employment card, a third distinct source and a genuinely different unit.
        card('c:firm', 'm:firm', FIRM_SPAN,
             'firm-level employment expanded at adopting establishments', level='firm'),
    ]
    return CardBundle(cards, g, P.JOURNAL_ONLY)


# =================================================================================================
# HARNESS. Each test returns (name, description, admitted, expectation_text). `admitted` True means the
# REAL validator returned ZERO failures for the hostile input — i.e. THE HOLE IS OPEN.
# =================================================================================================

def _admitted(nodes, b: CardBundle) -> tuple[bool, str]:
    """Drive the real gate. -> (was the hostile input admitted?, the refusal(s) if any)."""
    fails = A.validate_report(nodes, b)
    return (not fails), '; '.join(str(f) for f in fails)


RESULTS: list[tuple[str, bool, str, str]] = []   # (name, admitted, refusal, note)


def record(name: str, admitted: bool, refusal: str, note: str = '') -> None:
    RESULTS.append((name, admitted, refusal, note))


# ---- P0  POSITIVE CONTROL: a TRUE attributed finding, entailed by its span, MUST still ship ---------
#      Rung 2 must reject the reversals WITHOUT killing the truth. This is the same "rose by 1.5 points"
#      span, stated faithfully. It must be ADMITTED (admitted==True here means CORRECTLY shipped).
def p0_positive_control(b):
    n = Attributed(clauses=(Clause('c:up',
        'the local employment-to-population ratio rose by 1.5 points in regions that adopted '
        'the technology'),))
    admitted, refusal = _admitted([n], b)
    # For this ONE row, "admitted" is the desired outcome; record its refusal so a regression is visible.
    record('P0  POSITIVE CONTROL (true "rose by 1.5 points" finding MUST ship)', admitted, refusal,
           note='this row is a TRUE finding: ADMITTED == correct, REJECTED == regression')


# ---- P1  POSITIVE CONTROL: a LEGITIMATE owned synthesis over two admitted premises MUST still ship ---
#      Rung 3a tightens the OWNED lane; it must reject premise-free factual claims WITHOUT killing a
#      genuine reviewer synthesis. This one names two admitted premises, carries no particular (no
#      number, no spelled quantity, no magnitude word, no novel named entity) and adjudicates them.
def p1_positive_synthesis(b):
    # A PROVABLE "different units" verdict: a firm-level finding and a region-level finding, same outcome
    # (employment), each unit SPAN-SUPPORTED. This is the verdict RUNG 4 must still ship, while it rejects
    # the same words asserted over two findings that share a unit (T7's "not contradictory").
    n = Owned(text='These employment findings concern different units of analysis and are not directly '
                   'comparable across the firm and regional levels.',
              premise_ids=('c:firm', 'c:down'))
    admitted, refusal = _admitted([n], b)
    record('P1  POSITIVE CONTROL (legitimate owned synthesis MUST ship)', admitted, refusal,
           note='premise-bound owned synthesis, no particular: ADMITTED == correct, REJECTED == regression')


# ---- P2  POSITIVE CONTROL: a NORMAL heading (a section label, no assertion) MUST still ship ----------
def p2_positive_heading(b):
    n = Heading(2, 'Employment effects')
    admitted, refusal = _admitted([n], b)
    record('P2  POSITIVE CONTROL (normal heading "Employment effects" MUST ship)', admitted, refusal,
           note='a section label carries no number/source/forecast: ADMITTED == correct, REJECTED == regression')


# ---- T1  NEGATION: "rose ... 1.5 points" (span) rendered as "fell ... 1.5 points" (clause) ----------
def t1_negation(b):
    n = Attributed(clauses=(Clause('c:up',
        'the local employment-to-population ratio fell by 1.5 points in regions that adopted '
        'the technology'),))
    admitted, refusal = _admitted([n], b)
    record('T1  negation  (span says ROSE, clause says FELL)', admitted, refusal)


# ---- T1b UNITS: "1.5 points" rendered as "1.5 percent" ----------------------------------------------
def t1b_units(b):
    n = Attributed(clauses=(Clause('c:up',
        'the local employment-to-population ratio rose by 1.5 percent in regions that adopted '
        'the technology'),))
    admitted, refusal = _admitted([n], b)
    record('T1b units     (span says 1.5 POINTS, clause says 1.5 PERCENT)', admitted, refusal)


# ---- T1c SINGLE-DIGIT: fabricated "9 percent" not in the span --------------------------------------
def t1c_single_digit(b):
    n = Attributed(clauses=(Clause('c:up',
        'the local employment-to-population ratio rose by 9 percent in regions that adopted '
        'the technology'),))
    admitted, refusal = _admitted([n], b)
    record('T1c single-digit (fabricated "9 percent" absent from the span)', admitted, refusal)


# ---- T1d FAKE YEAR: a fabricated number equal to work.year (2021), not a real finding ---------------
def t1d_fake_year(b):
    n = Attributed(clauses=(Clause('c:up',
        'the local employment-to-population ratio rose across 2021 regions that adopted '
        'the technology'),))
    admitted, refusal = _admitted([n], b)
    record('T1d fake-year (fabricated quantity 2021 == work.year is exempt)', admitted, refusal)


# ---- T2  OWNED FACT: a premise-free reviewer sentence asserting a novel particular ------------------
def t2_owned_fact(b):
    n = Owned(text='The intervention causes fatal liver injury among children.')
    admitted, refusal = _admitted([n], b)
    record('T2  owned-fact ("...causes fatal liver injury among children.")', admitted, refusal)


# ---- T2b OWNED NUMBER: a premise-free reviewer sentence with a SPELLED quantity ---------------------
def t2b_owned_number(b):
    n = Owned(text='The intervention doubled mortality among children.')
    admitted, refusal = _admitted([n], b)
    record('T2b owned-number ("...doubled mortality among children.")', admitted, refusal)


# ---- T3  HEADING: an untyped, unreceipted heading that ASSERTS a fabricated finding -----------------
def t3_heading(b):
    n = Heading(2, 'Acemoglu proves that 47 percent of jobs will disappear.')
    admitted, refusal = _admitted([n], b)
    # ALSO show it reaches the page: render() emits it verbatim.
    reached = ''
    try:
        md, _ = A.render([n], b)
        reached = md.strip()
    except Exception as e:                                                # noqa: BLE001
        reached = f'(render refused: {e})'
    record('T3  heading   ("Acemoglu proves that 47 percent...")', admitted, refusal,
           note=f'render() emitted -> {reached!r}')


# ---- T4  TABLE: a row whose model `claim` REVERSES its span, with invented level/method -------------
def t4_table(b):
    n = EvidenceTable(card_ids=('c:up_rev', 'c:bres', 'c:autor'))
    admitted, refusal = _admitted([n], b)
    note = ''
    try:
        md, _ = A.render([n], b)
        note = 'table row shipped: ' + ('fell by 1.5 points' in md
                                        and 'children with cancer' in md and 'randomized trial' in md
                                        and 'REVERSED claim + invented level/method printed' or md[:80])
    except Exception as e:                                                # noqa: BLE001
        note = f'(render refused: {e})'
    record('T4  table     (claim REVERSES span; invented level/method)', admitted, refusal, note=note)


# ---- T5  CONNECTIVE: two positive, unrelated findings joined by "by contrast" -----------------------
def t5_connective(b):
    n = Attributed(clauses=(
        Clause('c:bres', 'computer automation of such work has been correspondingly limited '
                         'in its scope'),
        Clause('c:autor', 'computer capital substitutes for workers in carrying out a limited and '
                          'well-defined set of cognitive and manual activities, namely routine tasks'),
    ), connective='by contrast')
    admitted, refusal = _admitted([n], b)
    record('T5  connective (two POSITIVE findings joined by "by contrast")', admitted, refusal)


# ---- T6  VENUE: the model types a journal name ("Science") under an AER card ------------------------
def t6_venue(b):
    n = Attributed(clauses=(Clause('c:up',
        'Science reports that the local employment-to-population ratio rose by 1.5 points in regions '
        'that adopted the technology'),))
    admitted, refusal = _admitted([n], b)
    note = ''
    try:
        md, _ = A.render([n], b)
        note = f'rendered under AER card -> {md.strip()[:120]!r}'
    except Exception as e:                                                # noqa: BLE001
        note = f'(render refused: {e})'
    record('T6  venue     (model types "Science" under an AER card)', admitted, refusal, note=note)


# ---- T7  OWNED VERDICT: CONVERGES admits BOTH "opposite directions" AND "not contradictory" ---------
def t7_owned_verdict(b):
    opposed = Owned(
        text='These employment findings across regions point in opposite directions.',
        premise_ids=('c:up', 'c:down'))
    reconciled = Owned(
        text='These employment findings across regions are not contradictory.',
        premise_ids=('c:up', 'c:down'))
    a1, r1 = _admitted([opposed], b)
    a2, r2 = _admitted([reconciled], b)
    both = a1 and a2
    # At most ONE of two contradictory reconciliations may pass. If BOTH pass, a false reconciliation
    # is admissible -> the hole is open.
    record('T7  owned-verdict (BOTH "opposite directions" AND "not contradictory" admitted)',
           both,
           f'opposite-directions: {"ADMIT" if a1 else "REJECT:" + r1} | '
           f'not-contradictory: {"ADMIT" if a2 else "REJECT:" + r2}',
           note='at most one may pass; both passing = false reconciliation is admissible')


def main() -> int:
    b = build_bundle()
    for t in (p0_positive_control, p1_positive_synthesis, p2_positive_heading,
              t1_negation, t1b_units, t1c_single_digit, t1d_fake_year,
              t2_owned_fact, t2b_owned_number, t3_heading, t4_table,
              t5_connective, t6_venue, t7_owned_verdict):
        t(b)

    print('=== SOL LADDER RUNG 2+3a — FABRICATION TESTS (driving the REAL validator) ===')
    print('    Each attack MUST be REJECTED. The P0/P1/P2 POSITIVE CONTROLS MUST be ADMITTED.\n')
    # Rung 2 closes the ENTAILMENT lanes: T1 (direction), T1b (units), T1c (single digit), T1d (year),
    # and T4 (the evidence-table row, which shares this same entailment check).
    # Rung 3a closes the OWNED-FRAME and HEADING lanes: T2 (premise-free owned fact), T2b (premise-free
    # owned spelled quantity), and T3 (a heading that asserts a fabricated finding).
    # Rung 4 closes the VERDICT lane: T7 (a false reconciliation — "not contradictory" over premises that
    # share a scope). An owned verdict now carries the operation its own claim names and ships ONLY if
    # that operation's proof holds against span-bound facets. At most ONE of two contradictory
    # reconciliations may pass; both passing is the hole, and it is now closed.
    RUNG2 = {'T1 ', 'T1b', 'T1c', 'T1d', 'T4 '}
    RUNG3 = {'T2 ', 'T2b', 'T3 '}
    RUNG4 = {'T7'}

    def tag(name):  # the short test id at the head of the name
        return name.split('(')[0].strip()[:3].rstrip()

    holes_open = 0
    positive_regressed = False
    for name, admitted, refusal, note in RESULTS:
        is_positive = name[:2] in ('P0', 'P1', 'P2')
        if is_positive:
            if admitted:
                print(f'  [OK  — legitimate node SHIPPED] {name}')
            else:
                positive_regressed = True
                print(f'  [REGRESSION — LEGITIMATE REJECTED] {name}')
                print(f'                                 refusal: {refusal}')
            continue
        if admitted:
            holes_open += 1
            print(f'  [HOLE OPEN  — attack ADMITTED] {name}')
            if note:
                print(f'                                 {note}')
        else:
            print(f'  [closed — attack REJECTED    ] {name}')
            print(f'                                 refusal: {refusal}')

    def _open(rung):
        ids = {t.strip() for t in rung}
        return [name for name, admitted, _, _ in RESULTS
                if admitted and name[:2] not in ('P0', 'P1', 'P2') and tag(name) in ids]

    rung2_open, rung3_open, rung4_open = _open(RUNG2), _open(RUNG3), _open(RUNG4)
    print(f'\n  Rung-2 lanes still open (entailment): {len(rung2_open)}  (target: 0)')
    print(f'  Rung-3a lanes still open (owned/heading): {len(rung3_open)}  (target: 0)')
    print(f'  Rung-4 lanes still open (false verdict): {len(rung4_open)}  (target: 0)')
    print(f'  Positive controls: {"REGRESSED — a legitimate node was rejected" if positive_regressed else "OK — every legitimate node still ships"}')
    ok = (not rung2_open) and (not rung3_open) and (not rung4_open) and (not positive_regressed)
    if ok:
        print('  RUNG 2+3a+4 CLEAR: every entailment/owned/heading/verdict attack is rejected AND every '
              'legitimate node still ships.')
    else:
        print('  NOT CLEAR: a lane is open or a positive control regressed.')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
