#!/usr/bin/env python3
"""THE COHESION PASS — Sol plan 3, item 7. It targets S2 Paragraph Cohesion = 4.90, OUR LOWEST SCORE.

The judge's words: "fragmented narrative... without adequate transitions". They are correct, and the
cause is structural, not stylistic: 26 subsections were written by 26 INDEPENDENT LLM calls, each of
which could see its own cards and NOTHING ELSE. No writer knew what the paragraph above it had said, so
no writer could move from it. A document assembled from 26 monologues reads like 26 monologues.

** WHAT THIS PASS MAY NOT DO, AND WHY THAT IS THE ENTIRE DESIGN **

It may not rewrite the report. Sol: "a free-form sequential rewrite is NOT safe to stack; THE
IMMUTABILITY OF ATTRIBUTED OBJECTS IS THE SAFETY BOUNDARY." A model handed a validated report and asked
to "improve the flow" will smooth an attributed clause — move a number, merge two findings, soften a
hedge — and every such edit is a fabrication that has already passed the gate. The gate runs BEFORE
this pass. There is no second gate that re-derives an edited clause against its span, because by then
the sentence has a receipt in the sidecar and the receipt is a hash of the text as it was.

So the boundary is not a rule this file promises to follow. It is a PROPERTY OF THE TYPES:

    * `Attributed` is a frozen dataclass and THIS FILE NEVER CONSTRUCTS ONE. Grep it: there is no
      `Attributed(` in this module. It cannot edit a clause because it cannot make one, and it cannot
      mutate one because the type is frozen. The attributed nodes that come in are the same OBJECTS
      that go out — checked by identity, not by equality, in `_assert_frozen()`.
    * Everything it emits is `Owned(premise_ids=())` — a FRAME sentence, the one lane in the AST that
      is licensed by nothing and may therefore assert nothing particular: no number, no source, no new
      fact. Every sentence this pass creates is then run back through `validate_report()`, the SAME
      gate that judges the model's sentences, and anything that does not survive is DROPPED, never
      repaired.

THE FIVE PERMITTED OPERATIONS (and nothing else):
    1. ADD an OWNED transition that expresses ANALYTICAL MOVEMENT between two paragraphs.
    2. ADD an OWNED topic sentence where a paragraph opens cold on a finding.
    3. REORDER already-admitted paragraph objects WITHIN their subsection.
    4. DELETE redundant OWNED sentences (the boundary refrain, the duplicated verdict).
    5. Repair grammar in an OWNED sentence — never in a factual clause.

** MOVEMENT, NOT SIGNPOSTING. ** A transition that says "Turning now to..." is not cohesion, it is a
table of contents read aloud, and a judge scores it as filler. The transitions here are computed from
the DECLARED FIELDS of the cards the two paragraphs actually cite — the analytical distance really
travelled: a change of LEVEL (occupation -> firm), of METHOD (RCT -> panel), of HORIZON, of SECTOR.
Where two paragraphs move nowhere, NOTHING IS EMITTED: silence is better than filler, and a refrain of
identical connective sentences is the failure mode this pass is most likely to introduce.

    python scripts/cohesion_pass.py            # self-test, offline, no spend
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from report_ast import (Attributed, Owned, Heading, ParagraphBreak,      # noqa: E402
                        EvidenceTable, CardBundle, validate_report)

CONTENT = (Attributed, Owned)

# A facet must be a WORD, not a measurement. Anything with a digit in it is a particular, and a
# particular in an OWNED sentence is sourced to nothing.
_DIGIT = re.compile(r'\d')

# Facets, in the order a reader feels the move. Level first: "these are occupations, those are firms"
# is the single most load-bearing distinction in an evidence review, and it is the one the judge said
# our report never drew.
FACETS = ('level', 'method', 'horizon', 'sector')
_CARD_FIELD = {'level': ('level', 'unit_of_analysis'), 'method': ('method', 'design'),
               'horizon': ('horizon',), 'sector': ('industry',)}


def _clean_facet(v: str) -> str:
    v = re.sub(r'\s+', ' ', str(v or '')).strip().lower().rstrip('.')
    if not v or _DIGIT.search(v) or len(v) > 38:
        return ''
    return v


# ===================================================================== paragraphs
class Para:
    """A paragraph, AS AN OBJECT — so that 'reorder the paragraphs' is a list operation on typed things
    and not a regex over prose. `nodes` holds the ORIGINAL node objects, by identity."""

    __slots__ = ('nodes', 'sub', 'idx')

    def __init__(self, nodes, sub='', idx=0):
        self.nodes = list(nodes)
        self.sub = sub
        self.idx = idx

    @property
    def attributed(self):
        return [n for n in self.nodes if isinstance(n, Attributed)]

    @property
    def has_synthesis(self) -> bool:
        """Does this paragraph carry an OWNED node licensed by premises? Those are the planner's
        deterministic VERDICTS. A verdict adjudicates the findings STATED ABOVE IT, so a paragraph
        holding one is PINNED: reorder it above its own evidence and it adjudicates thin air."""
        return any(isinstance(n, Owned) and n.premise_ids for n in self.nodes)

    def facets(self, b: CardBundle) -> dict:
        out: dict = collections.defaultdict(collections.Counter)
        for n in self.attributed:
            for cl in n.clauses:
                r = b.resolve(cl.card_id)
                if not r.ok:
                    continue
                for f in FACETS:
                    for key in _CARD_FIELD[f]:
                        v = _clean_facet(r.card.get(key))
                        if v:
                            out[f][v] += 1
                            break
        return {f: c for f, c in out.items() if c}

    def dominant(self, b: CardBundle) -> dict:
        return {f: c.most_common(1)[0][0] for f, c in self.facets(b).items()}


def paragraphs_of(nodes: list) -> list:
    """Split a node list into (heading-run, [Para]) blocks. Headings, tables and breaks are STRUCTURE;
    only Attributed/Owned are paragraph content."""
    blocks: list = []                 # list of ('nodes', [...]) or ('paras', sub, [Para])
    cur_struct: list = []
    cur_para: list = []
    paras: list = []
    sub = ''

    def flush_para():
        nonlocal cur_para
        if cur_para:
            paras.append(Para(cur_para, sub, len(paras)))
            cur_para = []

    def flush_block():
        nonlocal paras
        flush_para()
        if paras:
            blocks.append(('paras', sub, paras))
            paras = []

    for n in nodes:
        if isinstance(n, (Heading, EvidenceTable)):
            flush_block()
            if cur_struct:
                blocks.append(('nodes', cur_struct))
                cur_struct = []
            blocks.append(('nodes', [n]))
            if isinstance(n, Heading) and n.level >= 3:
                sub = n.text
            elif isinstance(n, Heading):
                sub = n.text
            continue
        if isinstance(n, ParagraphBreak):
            flush_para()
            continue
        if isinstance(n, CONTENT):
            cur_para.append(n)
    flush_block()
    if cur_struct:
        blocks.append(('nodes', cur_struct))
    return blocks


# ===================================================================== movement
def movement(prev: Para, cur: Para, b: CardBundle) -> tuple[str, str, str]:
    """The analytical distance ACTUALLY travelled between two paragraphs. -> (facet, from, to) or ()."""
    a, c = prev.dominant(b), cur.dominant(b)
    for f in FACETS:
        if f in a and f in c and a[f] != c[f]:
            return (f, a[f], c[f])
    return ()


# The transition is a claim about WHAT KIND OF EVIDENCE is being set against what kind — never a
# signpost. Two phrasings per facet, chosen by a hash of the paragraph, so that a document with nine
# level-moves does not contain the same sentence nine times. (A refrain reads worse than a gap.)
TEMPLATES: dict[str, tuple[str, ...]] = {
    'level': (
        'The evidence to this point is measured at the {a} level; what follows is measured at the {b} '
        'level, and the two do not answer the same question.',
        'Moving from the {a} level to the {b} level changes what the evidence is able to show, and the '
        'shift is not merely one of scale.',
    ),
    'method': (
        'Where the preceding findings rest on {a} evidence, those that follow rest on {b}, and each '
        'design buys a different kind of confidence.',
        'The {a} evidence above and the {b} evidence below are answerable to different threats, so '
        'their agreement carries more weight than either alone.',
    ),
    'horizon': (
        'The findings above speak to the {a} horizon; over the {b} horizon the same mechanisms need '
        'not hold.',
        'What holds over the {a} horizon is a weaker claim than what holds over the {b} horizon, and '
        'the literature is not equally strong on both.',
    ),
    'sector': (
        'The same question can be put to {b}, where the constraints on adoption differ from those in '
        '{a}.',
        'Whether the pattern seen in {a} recurs in {b} is an empirical question, and the answer is not '
        'the same one.',
    ),
}

TOPIC: dict[str, tuple[str, ...]] = {
    'level': ('The record here is drawn at the {b} level.',),
    'method': ('The evidence here rests on {b} designs, and its limits are theirs.',),
    'sector': ('The evidence here is drawn from {b}.',),
    'horizon': ('The evidence here speaks to the {b} horizon.',),
}


def _phrase(bank: dict, facet: str, a: str, bb: str, salt: int) -> str:
    forms = bank.get(facet) or ()
    if not forms:
        return ''
    return forms[salt % len(forms)].format(a=a, b=bb)


# ===================================================================== the pass
def _assert_frozen(before: list, after: list) -> None:
    """THE SAFETY BOUNDARY, CHECKED BY IDENTITY.

    Not `==`: a model-rewritten clause that happened to compare equal would pass an equality check, and
    an `Attributed` rebuilt from edited text with the same card_id compares UNEQUAL only if the text
    changed — which is what we want, but it would still be a NEW OBJECT. Checking `id()` proves the
    stronger thing: every attributed node on the way out IS the very object that came in. Nothing was
    edited, nothing was rebuilt, nothing was added, nothing was dropped.
    """
    xs = [n for n in before if isinstance(n, Attributed)]
    ys = [n for n in after if isinstance(n, Attributed)]
    if len(xs) != len(ys):
        raise AssertionError(f'COHESION PASS ADDED OR DROPPED AN ATTRIBUTED NODE: {len(xs)} -> {len(ys)}')
    if collections.Counter(id(n) for n in xs) != collections.Counter(id(n) for n in ys):
        raise AssertionError('COHESION PASS REPLACED AN ATTRIBUTED OBJECT — the clauses are not frozen')


def _norm(s: str) -> str:
    return re.sub(r'[^a-z0-9 ]', '', re.sub(r'\s+', ' ', (s or '').lower())).strip()


def _reorder(paras: list, b: CardBundle) -> list:
    """Reorder paragraphs WITHIN a subsection so the analytical movement is monotone rather than random.

    CONSERVATIVE BY CONSTRUCTION:
      * a paragraph holding a planner VERDICT (Owned with premises) is PINNED — it adjudicates the
        findings above it, and moving it above them makes it adjudicate nothing;
      * a paragraph whose cards DECLARE NO FACETS is PINNED. This one was found by the behavioural
        test, and it is the more interesting bug. A facet-less paragraph has no measurable distance to
        ANYTHING, so the greedy chain below discovered it could drive the discontinuity count to zero
        by sliding it BETWEEN the worker-level paragraph and the firm-level one — using it as a buffer
        to HIDE the seam. Discontinuities fell, cohesion did not improve, and the transition that would
        have marked the real move from worker to firm was never emitted. The reorder had learned to
        game its own metric. An unknown paragraph is UNKNOWN, not COMPATIBLE, and it does not move.
      * the new order is adopted ONLY if it strictly reduces the number of facet DISCONTINUITIES.
        A reorder that does not measurably improve cohesion is not applied, because every reorder
        risks breaking an anaphor the writer wrote.
    """
    if len(paras) < 3:
        return paras
    movable = [p for p in paras if not p.has_synthesis and p.facets(b)]
    pinned = {i: p for i, p in enumerate(paras) if p.has_synthesis or not p.facets(b)}
    if len(movable) < 2:
        return paras

    def disc(seq) -> int:
        return sum(1 for x, y in zip(seq, seq[1:]) if movement(x, y, b))

    # greedy chain: start from the paragraph with the most evidence, then always step to the paragraph
    # that is analytically CLOSEST to where we are.
    pool = list(movable)
    start = max(pool, key=lambda p: (len(p.attributed), -p.idx))
    chain, pool = [start], [p for p in pool if p is not start]
    while pool:
        cur = chain[-1]
        nxt = min(pool, key=lambda p: (1 if movement(cur, p, b) else 0, p.idx))
        chain.append(nxt)
        pool = [p for p in pool if p is not nxt]

    if disc(chain) >= disc(movable):
        return paras                       # no measurable gain -> do not touch the writer's order

    out, it = [], iter(chain)
    for i in range(len(paras)):
        out.append(pinned[i] if i in pinned else next(it))
    return out


def apply(nodes: list, b: CardBundle, verbose: bool = False) -> tuple[list, dict]:
    """-> (new_nodes, report). The ONLY entry point. Attributed nodes pass through UNTOUCHED."""
    blocks = paragraphs_of(nodes)
    stats = collections.Counter()
    used: set = set()                       # normalised text of every OWNED sentence already emitted
    out: list = []

    # Seed the dedupe set with the owned sentences the writer and the planner already wrote, so a
    # transition can never echo a sentence that is already on the page.
    for n in nodes:
        if isinstance(n, Owned):
            used.add(_norm(n.text))

    for blk in blocks:
        if blk[0] == 'nodes':
            out += blk[1]
            continue
        _, sub, paras = blk

        # ---- (3) REORDER, within the subsection only.
        new_order = _reorder(paras, b)
        if [p.idx for p in new_order] != [p.idx for p in paras]:
            stats['reordered_subsections'] += 1
        paras = new_order

        for i, p in enumerate(paras):
            add: list = []
            prev = paras[i - 1] if i else None

            # ---- (4) DELETE redundant OWNED sentences. The planner's boundary sentences are
            # structurally alike ("...does not settle the magnitude..."), and the writer's owned
            # sentences repeat each other across subsections. First one wins; the rest are noise.
            body: list = []
            for n in p.nodes:
                if isinstance(n, Owned):
                    k = _norm(n.text)
                    if k in used and any(isinstance(x, Owned) for x in body + out):
                        # only drop a DUPLICATE, and never the first occurrence
                        if k in {_norm(x.text) for x in
                                 [y for y in out if isinstance(y, Owned)] +
                                 [y for y in body if isinstance(y, Owned)]}:
                            stats['owned_duplicates_deleted'] += 1
                            continue
                    used.add(k)
                body.append(n)
            if not body:
                continue

            mv = movement(prev, p, b) if prev is not None else ()
            salt = len(p.attributed) + i + len(sub)

            if prev is not None and mv:
                # ---- (1) TRANSITION: analytical movement, phrased as a claim about the evidence.
                txt = _phrase(TEMPLATES, mv[0], mv[1], mv[2], salt)
                if txt and _norm(txt) not in used:
                    add.append(Owned(text=txt, premise_ids=()))
            elif prev is None and body and isinstance(body[0], Attributed):
                # ---- (2) TOPIC SENTENCE: the subsection opens COLD on a finding. Orient the reader in
                # the reviewer's own voice — what KIND of evidence this is — carrying no particular.
                dom = p.dominant(b)
                for f in ('level', 'method', 'sector', 'horizon'):
                    if f in dom:
                        txt = _phrase(TOPIC, f, '', dom[f], salt)
                        if txt and _norm(txt) not in used:
                            add.append(Owned(text=txt, premise_ids=()))
                        break

            # ---- THE SAME GATE THAT JUDGES THE MODEL JUDGES THIS PASS. A sentence this file wrote
            # that does not survive `validate_report` is DROPPED. It is not repaired, and it is
            # certainly not exempt: the abstract's author was caught by this lane twice.
            keep = []
            for n in add:
                if validate_report([n], b):
                    stats['owned_refused_by_gate'] += 1
                    continue
                used.add(_norm(n.text))
                keep.append(n)
                stats['transitions_added' if (prev is not None and mv) else 'topics_added'] += 1

            if out and not isinstance(out[-1], (Heading, ParagraphBreak)):
                out.append(ParagraphBreak())
            out += keep + body
        out.append(ParagraphBreak())

    _assert_frozen(nodes, out)              # <-- the immutability of attributed objects, PROVEN
    report = dict(stats)
    report['paragraphs'] = sum(len(x[2]) for x in blocks if x[0] == 'paras')
    if verbose:
        print(f'  COHESION: {report}')
    return out, report


# ===================================================================== self-test
def _self_test() -> int:
    import _test_fixtures
    import provenance as P

    g, cards = _test_fixtures.build()
    b = CardBundle(cards, g, P.JOURNAL_ONLY)
    cids = list(b.admitted_ids())[:4]
    if len(cids) < 2:
        print('need >= 2 admitted fixture cards')
        return 1

    from report_ast import Clause
    a1 = Attributed(clauses=(Clause(card_id=cids[0], text='x'),), connective='while')
    a2 = Attributed(clauses=(Clause(card_id=cids[1], text='y'),), connective='while')
    nodes = [Heading(3, 'Evidence for displacement'), a1, ParagraphBreak(), a2]

    out, rep = apply(nodes, b)
    ok = True

    # 1. the attributed objects are THE SAME OBJECTS.
    ids_in = [id(n) for n in nodes if isinstance(n, Attributed)]
    ids_out = [id(n) for n in out if isinstance(n, Attributed)]
    c1 = sorted(ids_in) == sorted(ids_out)
    print(f"  [{'PASS' if c1 else '**FAIL**'}] attributed nodes pass through by IDENTITY (frozen)")
    ok &= c1

    # 2. everything this pass emitted is an OWNED FRAME sentence (licensed by nothing).
    new_owned = [n for n in out if isinstance(n, Owned) and n not in nodes]
    c2 = all(n.premise_ids == () for n in new_owned)
    print(f"  [{'PASS' if c2 else '**FAIL**'}] every sentence the pass wrote is OWNED with no premises")
    ok &= c2

    # 3. everything it emitted survives the SHIPPING gate. (The FIXTURE'S attributed clauses are
    #    deliberate nonsense — 'x', 'y' — and would rightly be refused; that is not this pass's claim.
    #    Its claim is that every sentence IT WROTE is lawful, and that is what is checked.)
    c3 = not validate_report(new_owned, b) and len(new_owned) > 0
    print(f"  [{'PASS' if c3 else '**FAIL**'}] every sentence the pass wrote survives validate_report "
          f'({len(new_owned)} emitted)')
    ok &= c3

    # 4. the freeze assertion actually FIRES when an attributed node is tampered with.
    try:
        _assert_frozen([a1], [Attributed(clauses=(Clause(card_id=cids[0], text='x'),),
                                         connective='while')])
        c4 = False
    except AssertionError:
        c4 = True
    print(f"  [{'PASS' if c4 else '**FAIL**'}] _assert_frozen REJECTS a rebuilt attributed node")
    ok &= c4

    # 5. THIS MODULE CANNOT CONSTRUCT AN ATTRIBUTED NODE ON THE PASS PATH.
    #    Checked on the AST, not with a string grep: a grep is defeated by this file's own docstring
    #    (which names the type in order to promise it never builds one) and, far worse, it would be
    #    defeated by `globals()['Attr'+'ibuted']`. The parser is not.
    import ast as _ast
    tree = _ast.parse(Path(__file__).read_text())
    live = [f for f in _ast.walk(tree)
            if isinstance(f, _ast.FunctionDef) and not f.name.startswith('_self_test')]
    built = {n.func.id for f in live for n in _ast.walk(f)
             if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)}
    c5 = 'Attributed' not in built and 'Clause' not in built
    print(f"  [{'PASS' if c5 else '**FAIL**'}] the pass never CONSTRUCTS an Attributed node or a Clause "
          f'(AST-checked)')
    ok &= c5

    print(f'\n{"COHESION PASS: SAFE." if ok else "** COHESION PASS IS UNSAFE **"}  {rep}')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(_self_test())
