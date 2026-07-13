#!/usr/bin/env python3
"""THE ARGUMENT PLANNER — decides WHAT IS BEING COMPARED WITH WHAT, before a word of prose exists.

THE DEFECT THIS FIXES
---------------------
`cellcog_composer.write_report` fans 28 subsections out to 6 threads and generates every one of them
INDEPENDENTLY. There is no shared argument state. Nobody, anywhere in the pipeline, ever decides what
is being compared with what. So the report LISTS findings instead of ADJUDICATING them, and Critical
Synthesis came out at 210 words of 8,012 -- 2.6% of the report for 8% of the score -- and scored 6.36
on the joint-heaviest criterion (w=0.0800).

A later cohesion pass CANNOT repair this. It cannot manufacture a comparison the planner never made.
So the comparison is selected HERE, from the cards, BEFORE the writer is called.

THE TRAP, AND WHY MOST OF THIS FILE IS REFUSALS
-----------------------------------------------
The seductive failure is the FALSE RECONCILIATION:

    "These findings only look contradictory -- they measure different units."

...asserted about two cards that were never in conflict, or whose 'units' were guessed. That sentence
is a fabrication with no fabricated particular in it: every name is real, every number is real, and the
RELATION is invented. It is the exact shape of the bug that already shipped once here (a real mechanism,
'task displacement', bound to a real paper, Bresnahan 2002, that never states it). THE LIE IS IN THE
BINDING. A planner is a machine for producing bindings, so a planner is a machine for producing that lie.

Three rules hold it shut, and they are enforced in code, not in the prompt:

  1. THE SPAN IS THE ONLY EVIDENCE. Every facet is derived from the card's VERBATIM SPAN or from the
     card's DECLARED metadata. `claim` is model-authored ("state the finding in your words") and is
     NEVER read on any derivation path -- `derive_facets()` takes a `span: str`, so it is structurally
     incapable of seeing the claim. `has_number` is likewise claim-derived and is NOT TRUSTED: this
     module recomputes quantitativeness from the span. (Measured: 29 spans carry a span-verified figure;
     only 16 cards are flagged. The flag reads the paraphrase, and the paraphrase dropped the number.)

  2. A MISSING TAG IS NOT A COMPARISON. If the axis a bundle turns on is not present on both cards, the
     bundle is not emitted as a comparison -- it is emitted as NOT_A_COMPARISON with the reason. We do
     not infer a level, a horizon or a method in order to have something to say. Measured on this corpus:
     43% of cards declare NO horizon, and geography is present in 3 spans out of 133 -- so geography can
     key NOTHING here, and the planner says so instead of inventing it.

  3. YOU MAY ONLY RECONCILE AN APPARENT CONFLICT. "They only look contradictory" presupposes that they
     LOOK contradictory. That requires both directions to be KNOWN and OPPOSITE. Direction is derived
     from the span by a windowed, negation-guarded polarity rule that returns UNKNOWN on any ambiguity
     (measured: 82/133 spans carry no polarity cue at all and 15 fire both, so ~74% of cards are
     direction-UNKNOWN and can never enter a conflict). Where the directions are not both known, the
     bundle is still a real comparison -- but the planner emits the NON-reconciling verdict, which says
     the estimates bear on different units and does NOT claim they agree.

WHAT IT EMITS
-------------
A SENTENCE IR the writer must fill, so VOICE IS CARRIED STRUCTURALLY instead of being guessed back out
of the prose by a regex downstream:

    {voice: "attributed"|"owned", text, source_clauses:[{card_id, clause_text}], premise_card_ids:[]}

  * ATTRIBUTED sentences bind to a CARD_ID, never to a surname. Surname binding is ambiguous and this
    corpus proves it: "Acemoglu" names BOTH the 2018 AER robots paper and the 2019 JEP paper, and
    `_cited_cards` returns whichever happens to come first in the list. A figure from one can be gated
    against the span of the other. Five surnames here are bound to two papers each.
  * OWNED sentences carry `source_clauses: []` and are checked to name NO author in the entire corpus.
    An OWNED verdict may never silently inherit a source attribution -- that is how the reviewer's own
    voice gets laundered into a citation.
  * Every OWNED verdict is run through `synthesis_contract.validate()` HERE, at plan time. The planner
    is therefore incapable of planning a sentence the composer's gate would delete -- which is the
    reason the synthesis section starved in the first place. What survives is a guaranteed floor.

GENERAL, NOT TASK-72
--------------------
Nothing about this question is compiled into the logic. The facet vocabularies, the polarity cues, the
design ranking and the outline live in a RESEARCH CONTRACT (`ResearchContract`) -- data, compiled from
the question, loadable with --contract. The engine reads the contract. Swap the contract, plan any
question.

    python scripts/argument_planner.py                 # plan over outputs/evidence_cards.json
    python scripts/argument_planner.py --bundles       # just the comparison bundles it found
    python scripts/argument_planner.py --plans         # the per-subsection plans
    python scripts/argument_planner.py --ir SUB        # the sentence IR for one subsection
    python scripts/argument_planner.py --self-test     # the adversarial suite (false reconciliations)
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from synthesis_contract import Premise, Synthesis, validate, OPERATIONS  # noqa: E402

CARDS_V2 = ROOT / 'outputs' / 'evidence_cards_v2.json'
CARDS_V1 = ROOT / 'outputs' / 'evidence_cards.json'


def cards_path() -> Path:
    return CARDS_V2 if CARDS_V2.exists() else CARDS_V1


# ===================================================================== THE RESEARCH CONTRACT
#
# DATA, NOT LOGIC. Compiled from the question; the engine below never mentions this question.
# A facet is either DECLARED (it is a field the card already carries, gated at extraction) or
# SPAN-DERIVED (a surface form matched VERBATIM in the span, recorded so a human can audit it).
# There is no third kind. In particular there is no INFERRED facet, because an inferred facet is
# exactly what manufactures a false reconciliation.

@dataclass
class ResearchContract:
    question: str
    declared_facets: dict[str, str]                       # facet -> card field it reads
    span_facets: dict[str, dict[str, list[str]]]          # facet -> value -> [regex]
    polarity: dict[str, list[str]]                        # direction class -> [regex]
    negators: list[str]
    design_rank: dict[str, int]                           # method -> evidential strength
    empirical_designs: list[str]                          # designs that produce an ESTIMATE
    outcome_facet: str = 'outcome'                        # which facet is the dependent variable
    outline: list[tuple[str, list[str]]] = field(default_factory=list)

    @staticmethod
    def load(p: Path) -> 'ResearchContract':
        d = json.loads(p.read_text())
        d['outline'] = [(s, subs) for s, subs in d.get('outline', [])]
        return ResearchContract(**d)


def default_contract() -> ResearchContract:
    """Compiled from: 'the restructuring impact of AI on the labor market'.

    Every vocabulary below is a list of surface forms we expect to find IN A SPAN. They are matched
    against the verbatim span and the matched form is recorded. They are NOT a taxonomy of the world;
    they are a taxonomy of what the papers actually SAY, which is the only thing we are allowed to key on.
    """
    try:
        from cellcog_composer import OUTLINE            # the outline the composer will actually write
    except Exception:
        OUTLINE = []
    return ResearchContract(
        question='the restructuring impact of Artificial Intelligence on the labor market',
        # ---- DECLARED: gated at extraction, read straight off the card. NEVER inferred here.
        declared_facets={'unit_of_analysis': 'level', 'method': 'method', 'horizon': 'horizon'},
        # ---- SPAN-DERIVED: matched verbatim in the span; the matched form is kept as evidence.
        span_facets={
            'technology': {
                'robotics':        [r'\brobot\w*'],
                'generative_ai':   [r'generative ai\w*', r'large language model\w*', r'\bllms?\b',
                                    r'chatgpt', r'\bgpt-?\d?\b'],
                'ai_ml':           [r'artificial intelligence', r'\bai\b', r'machine learning',
                                    r'deep learning', r'prediction machine\w*', r'\balgorithm\w*'],
                'ict_computing':   [r'computer\w*', r'information technolog\w*', r'\bict\b',
                                    r'software', r'digiti[sz]\w*', r'computeri[sz]\w*'],
                'automation':      [r'automat\w*'],
            },
            'outcome': {
                'employment':      [r'employment', r'\bemploy\w*', r'\bjobs?\b', r'unemploy\w*',
                                    r'workforce', r'\bhiring\b', r'job loss\w*'],
                'wages':           [r'wages?\b', r'earnings?\b', r'salar\w*', r'\bincome\b',
                                    r'compensation'],
                'productivity':    [r'productivity', r'output per', r'efficiency'],
                'skills':          [r'skills?\b', r'skilled\b', r'reskill\w*', r'upskill\w*',
                                    r'human capital', r'competenc\w*', r'training'],
                'tasks':           [r'tasks?\b', r'routine\b', r'job content'],
                'labor_share':     [r'lab(?:o|ou)r share'],
                'inequality':      [r'inequalit\w*', r'polari[sz]\w*', r'disparit\w*', r'wage gap'],
            },
            'industry': {
                'manufacturing':   [r'manufactur\w*', r'\bfactor(?:y|ies)\b', r'assembly line',
                                    r'industrial robot\w*', r'\bplants?\b'],
                'healthcare':      [r'health ?care', r'\bmedical\b', r'\bclinical\b', r'\bnurs\w*',
                                    r'\bpatients?\b', r'physician\w*'],
                'finance':         [r'\bfinanc\w*', r'\bbank\w*', r'insurance', r'fintech'],
                'retail':          [r'\bretail\w*', r'e-commerce', r'\bstores?\b'],
                'education':       [r'education\w*', r'\bschools?\b', r'\bteach\w*', r'\bstudents?\b'],
                'transport':       [r'transport\w*', r'\bdrivers?\b', r'logistics?\b', r'\btrucks?\b',
                                    r'autonomous vehicle\w*'],
                'creative':        [r'\bcreative\b', r'journalis\w*', r'\bdesigners?\b', r'\bartists?\b'],
                'prof_services':   [r'professional service\w*', r'\bconsult\w*', r'\blegal\b', r'\blawyer\w*'],
                'agriculture':     [r'agricultur\w*', r'\bfarm\w*'],
            },
            'geography': {
                'united_states':   [r'united states', r'\bu\.s\.', r'\bus\b', r'american\b'],
                'europe':          [r'\beurope\w*', r'\bgermany\b', r'\bfrance\b', r'united kingdom',
                                    r'\bnordic\b', r'\beu\b'],
                'china':           [r'\bchina\b', r'\bchinese\b'],
                'developing':      [r'developing countr\w*', r'\bemerging econom\w*', r'\bglobal south\b'],
            },
        },
        # ---- DIRECTION: the most dangerous facet on the board. See derive_direction().
        polarity={
            'negative': [r'\breduc\w*', r'\bdeclin\w*', r'\bfell\b', r'\bfalls?\b', r'\bfalling\b',
                         r'\bdecreas\w*', r'\bdisplac\w*', r'\blower\w*', r'\bloss\w*', r'\bshrink\w*',
                         r'\bsubstitut\w*', r'\bdestroy\w*', r'\berod\w*', r'\bnegative\b'],
            'positive': [r'\bincreas\w*', r'\brais\w*', r'\brise\w*', r'\brose\b', r'\bgrow\w*',
                         r'\bgrew\b', r'\bgains?\b', r'\bhigher\b', r'\bcreat\w*', r'\bcomplement\w*',
                         r'\bexpand\w*', r'\bimprov\w*', r'\baugment\w*', r'\bpositive\b'],
            'null':     [r'\bno significant\b', r'\bno effect\b', r'\bno evidence\b', r'\binsignificant\b',
                         r'\btoo small to detect\b', r'\bnot significant\b', r'\bunchanged\b'],
        },
        negators=[r'\bnot\b', r'\bno\b', r'\bnor\b', r'\bnever\b', r'\bwithout\b', r'\bneither\b',
                  r'\bfails? to\b', r'\bunable to\b', r'\bcannot\b', r"\bdoes ?n[o']t\b", r'\blittle\b'],
        # ---- an ESTIMATE from a stronger design outranks one from a weaker design. DECLARED fields only.
        design_rank={'experiment': 5, 'quasi-experimental': 4, 'observational': 3, 'survey': 2,
                     'review': 1, 'theory': 0},
        empirical_designs=['experiment', 'quasi-experimental', 'observational', 'survey'],
        outline=OUTLINE,
    )


# ===================================================================== FACETS

@dataclass(frozen=True)
class Facet:
    name: str
    value: str = ''
    provenance: str = 'missing'      # 'declared' | 'span' | 'missing'
    evidence: str = ''               # the VERBATIM surface form lifted from the span

    @property
    def known(self) -> bool:
        return self.provenance != 'missing' and bool(self.value)

    def __str__(self) -> str:
        if not self.known:
            return f'{self.name}=MISSING'
        tag = 'declared' if self.provenance == 'declared' else f'span:"{self.evidence}"'
        return f'{self.name}={self.value} ({tag})'


DIR_WINDOW = 8      # a polarity cue must sit within this many tokens of an outcome cue
NEG_WINDOW = 3      # a negator this close BEFORE a cue voids the cue (we discard; we never flip)


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9''.\-]+", s.lower())


def _match_spans(text: str, patterns: list[str]) -> list[tuple[int, str]]:
    """Return (token_index, matched_surface_form) for every pattern hit. Operates on the SPAN."""
    out = []
    low = text.lower()
    toks = _tokens(low)
    # map char offset -> token index
    idx, pos = [], 0
    for t in toks:
        p = low.find(t, pos)
        if p < 0:
            p = pos
        idx.append(p)
        pos = p + len(t)
    for pat in patterns:
        for m in re.finditer(pat, low):
            ti = 0
            for i, ch in enumerate(idx):
                if ch <= m.start():
                    ti = i
                else:
                    break
            out.append((ti, m.group(0)))
    return out


def derive_span_facet(span: str, name: str, vocab: dict[str, list[str]]) -> Facet:
    """Match a facet in the VERBATIM SPAN. Records the surface form so a human can audit the tag.

    NOTE THE SIGNATURE: it takes a `span: str`. It cannot see `claim`, so it cannot launder the
    model's paraphrase into evidence. That is the point.
    """
    hits: dict[str, tuple[int, str]] = {}
    for value, pats in vocab.items():
        ms = _match_spans(span, pats)
        if ms:
            hits[value] = min(ms, key=lambda x: x[0])
    if not hits:
        return Facet(name)
    if len(hits) > 1:
        # Several values fire. Take the EARLIEST-mentioned as primary but record the ambiguity: an
        # ambiguous facet is still usable as a SHARED facet, and is refused as a comparison AXIS.
        best = min(hits.items(), key=lambda kv: kv[1][0])
        return Facet(name, best[0], 'span', best[1][1])
    v, (_, form) = next(iter(hits.items()))
    return Facet(name, v, 'span', form)


def derive_span_facet_all(span: str, name: str, vocab: dict[str, list[str]]) -> list[str]:
    """EVERY value of this facet the span mentions (a span can be about two industries)."""
    return sorted(v for v, pats in vocab.items() if _match_spans(span, pats))


def derive_direction(span: str, contract: ResearchContract, outcome_vocab: list[str]) -> Facet:
    """THE FACET THAT MANUFACTURES FALSE CONFLICTS. It returns UNKNOWN at the first sign of trouble.

    A direction is assigned ONLY when, in the verbatim span:
       (a) at least one polarity cue sits within DIR_WINDOW tokens of an OUTCOME cue -- so that
           "AI improves prediction accuracy" is not read as a POSITIVE finding about EMPLOYMENT;
       (b) no negator sits within NEG_WINDOW tokens before the cue -- and a negated cue is DISCARDED,
           never FLIPPED, because flipping is an inference and inference is what we are refusing;
       (c) exactly ONE polarity class survives. A span that says employment fell while productivity
           rose fires two classes and is therefore UNKNOWN.
    Measured on this corpus: 82/133 spans carry no polarity cue at all and 15 fire both. About three
    quarters of the corpus is direction-UNKNOWN, and can never enter a conflict bundle. That is the
    honest number, and it is the whole reason this function exists.
    """
    if not outcome_vocab:
        return Facet('direction')
    toks = _tokens(span)
    out_idx = [i for i, _ in _match_spans(span, outcome_vocab)]
    if not out_idx:
        return Facet('direction')
    neg_idx = {i for i, _ in _match_spans(span, contract.negators)}

    survivors: dict[str, str] = {}
    for cls, pats in contract.polarity.items():
        for ti, form in _match_spans(span, pats):
            if not any(abs(ti - oi) <= DIR_WINDOW for oi in out_idx):
                continue                                     # cue is not about this outcome
            if any(0 < ti - ni <= NEG_WINDOW for ni in neg_idx):
                continue                                     # negated: DISCARD, do not flip
            survivors.setdefault(cls, form)
    if len(survivors) != 1:
        return Facet('direction')                            # zero cues, or a mixed span -> UNKNOWN
    cls, form = next(iter(survivors.items()))
    _ = toks
    return Facet('direction', cls, 'span', form)


def span_numbers(card: dict) -> list[str]:
    """The figures that STAND AS THEIR OWN NUMBER in the verbatim span.

    `card['has_number']` is computed at extraction as `bool(re.search(r'\\d', claim))` -- it reads the
    MODEL-AUTHORED CLAIM. It is not evidence and it is not trusted here. (It also undercounts: 29 spans
    carry a span-verified figure and only 16 cards are flagged, because the paraphrase dropped the number.)
    """
    span, year = card.get('span') or '', str(card.get('year') or '')
    # a version number ("Industry 4.0") and a bare year are not effect sizes
    s = re.sub(r'\b[A-Z][A-Za-z&.]*\s+\d\.\d\b', ' ', span)
    s = re.sub(r'\b(?:1[89]|20)\d\d\b', ' ', s)
    return [n for n in re.findall(r'\d+(?:\.\d+)?', s) if len(n) >= 2 and n != year]


@dataclass
class CardFacets:
    card_id: str
    doi: str
    facets: dict[str, Facet]
    outcomes_all: list[str]
    industries_all: list[str]
    numbers: list[str]

    def f(self, name: str) -> Facet:
        return self.facets.get(name, Facet(name))

    @property
    def quantitative(self) -> bool:
        return bool(self.numbers)


def derive_facets(card: dict, contract: ResearchContract) -> CardFacets:
    """The 8-facet key. DECLARED fields are read off the card; the rest come from the SPAN, or are MISSING."""
    span = card.get('span') or ''
    fx: dict[str, Facet] = {}
    for fname, field_name in contract.declared_facets.items():
        v = (card.get(field_name) or '').strip()
        fx[fname] = Facet(fname, v, 'declared') if v else Facet(fname)
    for fname, vocab in contract.span_facets.items():
        fx[fname] = derive_span_facet(span, fname, vocab)
    outcome_vocab = [p for pats in contract.span_facets.get('outcome', {}).values() for p in pats]
    fx['direction'] = derive_direction(span, contract, outcome_vocab)
    return CardFacets(
        card_id=card['id'], doi=card.get('doi', ''), facets=fx,
        outcomes_all=derive_span_facet_all(span, 'outcome', contract.span_facets.get('outcome', {})),
        industries_all=derive_span_facet_all(span, 'industry', contract.span_facets.get('industry', {})),
        numbers=span_numbers(card),
    )


# ===================================================================== COMPARISON BUNDLES

BUNDLE_KINDS = {
    'SAME_OUTCOME_DIFFERENT_UNIT':  'same outcome, different unit of analysis -- the classic '
                                    '"they only look contradictory" case',
    'SAME_UNIT_OPPOSITE_DIRECTION': 'same unit, same outcome, opposite direction -- a GENUINE conflict',
    'SAME_FINDING_DIFFERENT_METHOD': 'same outcome, same direction, different identification strategy '
                                     '-- robustness',
    'SAME_OUTCOME_DIFFERENT_HORIZON': 'same outcome, different time horizon',
    'UNCOUNTERED':                  'a finding with NO counterpart anywhere in the corpus -- a boundary',
    'COVERAGE_GAP':                 'an empty cell of the evidence matrix -- a derivable research gap',
    'NOT_A_COMPARISON':             'the axis this would turn on is NOT DECLARED on both cards',
}


@dataclass
class Bundle:
    kind: str
    axis: str                       # the facet the comparison TURNS ON
    card_ids: list[str]
    shared: dict[str, str]          # facets held CONSTANT
    varies: dict[str, str]          # card_id -> value on the axis
    operation: str                  # the synthesis_contract operation this licenses
    apparent_conflict: bool         # do the two cards actually LOOK contradictory?
    comparable: bool                # are these two ESTIMATES on the same footing?
    incomparability: list[str]      # ...and if not, exactly why not
    score: float
    note: str = ''

    def key(self) -> tuple:
        return (self.kind, self.axis, tuple(sorted(self.card_ids)))


def _comparability(a: CardFacets, b: CardFacets, contract: ResearchContract) -> tuple[bool, list[str]]:
    """ARE THESE TWO ESTIMATES ON THE SAME FOOTING? Almost never, and the plan must SAY so.

    Two numbers are comparable only if they are numbers, produced by designs that estimate something,
    about the same outcome, at the same unit, over the same horizon. Anything else and 'X is bigger than
    Y' is a category error. A theory paper and a survey do not disagree about a magnitude; they are not
    both reporting a magnitude.
    """
    why: list[str] = []
    emp = set(contract.empirical_designs)
    for c, tag in ((a, 'first'), (b, 'second')):
        m = c.f('method')
        if not m.known:
            why.append(f'the {tag} card declares no method')
        elif m.value not in emp:
            why.append(f'the {tag} card is a {m.value} paper -- it states a position, not an estimate')
        if not c.quantitative:
            why.append(f'the {tag} card reports no figure in its span -- there is no estimate to compare')
    ua, ub = a.f('unit_of_analysis'), b.f('unit_of_analysis')
    if ua.known and ub.known and ua.value != ub.value:
        why.append(f'they observe different units of analysis ({ua.value} vs {ub.value})')
    ha, hb = a.f('horizon'), b.f('horizon')
    if not (ha.known and hb.known):
        why.append('at least one card declares no horizon, so the time base cannot be matched')
    elif ha.value != hb.value:
        why.append(f'they observe different horizons ({ha.value} vs {hb.value})')
    oa, ob = a.f('outcome'), b.f('outcome')
    if oa.known and ob.known and oa.value != ob.value:
        why.append(f'they measure different outcomes ({oa.value} vs {ob.value})')
    return (not why), why


def _apparent_conflict(a: CardFacets, b: CardFacets) -> bool:
    """Do these two cards actually LOOK contradictory? You may not reconcile what was never in tension.

    Requires BOTH directions to be span-derived and KNOWN and OPPOSED. An UNKNOWN direction is not a
    conflict; it is an absence of information, and treating it as a conflict is how a report ends up
    'reconciling' two papers that agreed all along.
    """
    da, db = a.f('direction'), b.f('direction')
    if not (da.known and db.known):
        return False
    return {da.value, db.value} in ({'positive', 'negative'},
                                    {'positive', 'null'}, {'negative', 'null'})


def _score(a: CardFacets, b: CardFacets, apparent: bool, comparable: bool) -> float:
    s = 0.0
    s += 3.0 * (a.quantitative + b.quantitative)      # a comparison of FIGURES is worth most
    s += 4.0 if apparent else 0.0                     # a genuine tension is the point of a review
    s += 2.0 if comparable else 0.0
    for c in (a, b):
        if c.f('method').known and c.f('method').value in ('experiment', 'quasi-experimental'):
            s += 1.5
        if c.f('horizon').known:
            s += 0.5
    return s


def find_bundles(cfs: list[CardFacets], contract: ResearchContract,
                 cards_by_id: dict[str, dict]) -> list[Bundle]:
    """Every comparison this corpus can actually support -- and no others."""
    out: list[Bundle] = []
    by_id = {c.card_id: c for c in cfs}

    def pair_ok(a: CardFacets, b: CardFacets) -> bool:
        # A CARD CANNOT BE COMPARED WITH ITSELF, AND A PAPER CANNOT CORROBORATE ITSELF.
        # synthesis_contract rejects this as `premises_share_a_single_source`; we must not hand the
        # writer a "comparison" that its own gate will refuse. (Damioli 2021 carries three productivity
        # cards at two levels -- a tempting, and entirely invalid, level contrast.)
        return a.doi != b.doi

    for a, b in itertools.combinations(cfs, 2):
        if not pair_ok(a, b):
            continue
        oa, ob = a.f('outcome'), b.f('outcome')
        if not (oa.known and ob.known and oa.value == ob.value):
            continue                                          # no shared dependent variable: not a comparison
        outcome = oa.value
        ua, ub = a.f('unit_of_analysis'), b.f('unit_of_analysis')
        ha, hb = a.f('horizon'), b.f('horizon')
        ma, mb = a.f('method'), b.f('method')
        da, db = a.f('direction'), b.f('direction')
        apparent = _apparent_conflict(a, b)
        comparable, why = _comparability(a, b, contract)
        sc = _score(a, b, apparent, comparable)
        shared = {'outcome': outcome}
        for fn in ('technology', 'industry'):
            fa, fb = a.f(fn), b.f(fn)
            if fa.known and fb.known and fa.value == fb.value:
                shared[fn] = fa.value

        # ---- 1. SAME OUTCOME, DIFFERENT UNIT -- the "they only look contradictory" case
        if ua.known and ub.known and ua.value != ub.value:
            out.append(Bundle(
                kind='SAME_OUTCOME_DIFFERENT_UNIT', axis='unit_of_analysis',
                card_ids=[a.card_id, b.card_id], shared=shared,
                varies={a.card_id: ua.value, b.card_id: ub.value},
                operation='CONTRASTS_LEVEL', apparent_conflict=apparent,
                comparable=comparable, incomparability=why, score=sc,
                note=('the estimates point in opposite directions and differ on exactly one declared '
                      'axis -- a reconciliation is licensed'
                      if apparent else
                      'the directions are not both known, so there is NO apparent conflict to '
                      'reconcile; the plan states that the evidence bears on two different units, and '
                      'does NOT claim the findings agree')))
        elif ua.value == ub.value and ua.known:
            # ---- 2. SAME UNIT, OPPOSITE DIRECTION -- a genuine conflict (only if BOTH directions known)
            if apparent:
                out.append(Bundle(
                    kind='SAME_UNIT_OPPOSITE_DIRECTION', axis='direction',
                    card_ids=[a.card_id, b.card_id], shared={**shared, 'unit_of_analysis': ua.value},
                    varies={a.card_id: da.value, b.card_id: db.value},
                    operation='CONTRASTS_DIRECTION', apparent_conflict=True,
                    comparable=comparable, incomparability=why, score=sc + 2,
                    note='same outcome, same declared unit, opposed span-derived directions -- this '
                         'conflict cannot be dissolved by pointing at the unit of analysis'))
            # ---- 3. SAME FINDING, DIFFERENT METHOD -- robustness
            elif (ma.known and mb.known and ma.value != mb.value
                  and da.known and db.known and da.value == db.value):
                out.append(Bundle(
                    kind='SAME_FINDING_DIFFERENT_METHOD', axis='method',
                    card_ids=[a.card_id, b.card_id],
                    shared={**shared, 'unit_of_analysis': ua.value, 'direction': da.value},
                    varies={a.card_id: ma.value, b.card_id: mb.value},
                    operation='RANK_EVIDENCE', apparent_conflict=False,
                    comparable=comparable, incomparability=why, score=sc + 1,
                    note='the same directional finding survives a change of identification strategy'))

        # ---- 4. SAME OUTCOME, DIFFERENT HORIZON (only when BOTH declare one -- 43% do not)
        if ha.known and hb.known and ha.value != hb.value:
            out.append(Bundle(
                kind='SAME_OUTCOME_DIFFERENT_HORIZON', axis='horizon',
                card_ids=[a.card_id, b.card_id], shared=shared,
                varies={a.card_id: ha.value, b.card_id: hb.value},
                operation='CONTRASTS_HORIZON', apparent_conflict=apparent,
                comparable=comparable, incomparability=why, score=sc,
                note='' if apparent else 'no apparent conflict: this is a horizon SPREAD, not a horizon '
                                         'DISPUTE'))

    # ---- 5. THE REFUSALS. Two cards on the same outcome whose axis is NOT DECLARED are NOT a comparison.
    #         We emit them so the refusal is VISIBLE and auditable, instead of silently inventing a tag.
    for a, b in itertools.combinations(cfs, 2):
        if not pair_ok(a, b):
            continue
        oa, ob = a.f('outcome'), b.f('outcome')
        if not (oa.known and ob.known and oa.value == ob.value):
            continue
        missing = [fn for fn in ('unit_of_analysis', 'horizon', 'method')
                   if not (a.f(fn).known and b.f(fn).known)]
        if missing and not any(bd.card_ids == [a.card_id, b.card_id] for bd in out):
            out.append(Bundle(
                kind='NOT_A_COMPARISON', axis=','.join(missing),
                card_ids=[a.card_id, b.card_id], shared={'outcome': oa.value}, varies={},
                operation='', apparent_conflict=False, comparable=False,
                incomparability=[f'{fn} is not declared on both cards' for fn in missing],
                score=0.0,
                note='REFUSED: the axis this would turn on is missing. Inventing it here is exactly how '
                     'a false reconciliation is manufactured, so no comparison is planned.'))

    # ---- 6. UNCOUNTERED: a cell of (outcome x unit) that exactly ONE source occupies -> a boundary
    cell: dict[tuple[str, str], set[str]] = {}
    for c in cfs:
        o, u = c.f('outcome'), c.f('unit_of_analysis')
        if o.known and u.known:
            cell.setdefault((o.value, u.value), set()).add(c.doi)
    for c in cfs:
        o, u = c.f('outcome'), c.f('unit_of_analysis')
        if not (o.known and u.known):
            continue
        if len(cell[(o.value, u.value)]) == 1 and c.quantitative:
            out.append(Bundle(
                kind='UNCOUNTERED', axis='unit_of_analysis', card_ids=[c.card_id],
                shared={'outcome': o.value, 'unit_of_analysis': u.value}, varies={},
                operation='COVERAGE_GAP', apparent_conflict=False, comparable=False,
                incomparability=['there is no second source in this cell to compare against'],
                score=2.0 + len(c.numbers),
                note='a span-verified figure that NO other source in the corpus counters at the same '
                     'unit -- the review can state its scope, and must not generalise beyond it'))

    dedup: dict[tuple, Bundle] = {}
    for b in out:
        k = b.key()
        if k not in dedup or b.score > dedup[k].score:
            dedup[k] = b
    return sorted(dedup.values(), key=lambda b: -b.score)


def coverage_gaps(cfs: list[CardFacets], contract: ResearchContract) -> list[dict]:
    """THE OUTLINE WRITES CHEQUES THE CORPUS CANNOT CASH. Here is the bank statement.

    An empty cell is a DERIVABLE research gap (synthesis_contract calls this COVERAGE_GAP and it is the
    one operation that needs no second premise). It is also the honest reason to DELETE a subsection:
    a promised 4-subsection industry section over a corpus with zero retail cards produces prose that
    lists nothing, and two criteria regressed for exactly that.
    """
    outs = list(contract.span_facets.get('outcome', {}))
    inds = list(contract.span_facets.get('industry', {}))
    matrix: dict[tuple[str, str], set[str]] = {}
    for c in cfs:
        for o in c.outcomes_all:
            for i in c.industries_all:
                matrix.setdefault((o, i), set()).add(c.doi)
    gaps = []
    for i in inds:
        srcs = {d for (o, ii), ds in matrix.items() if ii == i for d in ds}
        gaps.append({'industry': i, 'sources': len(srcs),
                     'outcomes_covered': sorted({o for (o, ii) in matrix if ii == i})})
    return sorted(gaps, key=lambda g: g['sources'])


# ===================================================================== THE SENTENCE IR

@dataclass
class SourceClause:
    card_id: str                 # BOUND BY CARD_ID. Never by surname -- 'Acemoglu' names two papers here.
    clause_text: str             # the VERBATIM SPAN. Immutable. This is the evidence.
    attribution: str = ''        # the exact in-prose citation form the writer must use
    unit: str = ''
    method: str = ''
    horizon: str = ''
    figures: list[str] = field(default_factory=list)   # span-verified figures the writer MUST print


@dataclass
class SentenceIR:
    voice: str                                   # 'attributed' | 'owned'
    text: str                                    # owned: the proposition, pre-validated. attributed: the brief.
    source_clauses: list[SourceClause] = field(default_factory=list)
    premise_card_ids: list[str] = field(default_factory=list)
    role: str = ''                               # thesis | evidence | verdict | boundary | bridge
    gate: str = ''                               # which bar this sentence has ALREADY cleared


def _corpus_surnames(cards: list[dict]) -> set[str]:
    return {a for c in cards for a in (c.get('authors') or []) if len(a) >= 4}


def owned_is_safe(text: str, surnames: set[str], premise_blob: str) -> tuple[bool, str]:
    """AN OWNED SENTENCE MAY NEVER SILENTLY INHERIT A SOURCE ATTRIBUTION.

    The reviewer's voice is licensed to be NON-ENTAILED -- that is what insight is. The price of that
    licence is that it names nobody and carries no particular. The moment an owned sentence names a
    source it has become an ATTRIBUTED sentence with no evidence behind it, which is a fabrication.
    Checked against EVERY surname in the corpus, not merely the ones in this bundle.
    """
    for s in sorted(surnames):
        if re.search(rf'\b{re.escape(s)}\b', text, re.I):
            return False, f'OWNED_NAMES_A_SOURCE:{s}'
    if re.search(r'\d', text):
        return False, 'OWNED_CARRIES_A_NUMBER'
    from synthesis_contract import SPELLED_QTY, FORECAST, UNIVERSAL, CAUSAL_IMPORT, CAP_TOKEN, SAFE_CAPS
    if SPELLED_QTY.search(text):
        return False, f'OWNED_CARRIES_A_SPELLED_QUANTITY:{SPELLED_QTY.search(text).group(0)}'
    if FORECAST.search(text):
        return False, f'OWNED_FORECASTS:{FORECAST.search(text).group(0)}'
    if UNIVERSAL.search(text):
        return False, f'OWNED_OVERCLAIMS:{UNIVERSAL.search(text).group(0)}'
    if CAUSAL_IMPORT.search(text):
        return False, f'OWNED_IMPORTS_A_MECHANISM:{CAUSAL_IMPORT.search(text).group(0)}'
    sent_initial = {m.group(1) for m in re.finditer(r"(?:^|[.!?;:]\s+)([A-Z][A-Za-z&.\-']*)", text)}
    blob_low = premise_blob.lower()
    for tok in CAP_TOKEN.findall(text):
        if tok in sent_initial or tok in SAFE_CAPS:
            continue
        if re.sub(r"'s$", '', tok).lower() in blob_low:
            continue
        return False, f'OWNED_NEW_ENTITY:{tok}'
    return True, ''


def _premises(bundle: Bundle, cards_by_id: dict[str, dict]) -> dict[str, Premise]:
    """Premises for synthesis_contract.validate().

    `text` IS THE VERBATIM SPAN, not the card's `claim`. The composer passes `claim` here, which makes
    the model-authored paraphrase the ALLOWLIST for the no-new-entity check: an entity hallucinated into
    a claim becomes a permitted entity in the reviewer's own voice. The span is the only evidence, so the
    span is what the premise carries.
    """
    prem = {}
    for cid in bundle.card_ids:
        c = cards_by_id[cid]
        prem[cid] = Premise(id=cid, text=c.get('span') or '', source=c.get('source') or '',
                            level=c.get('level') or '', horizon=c.get('horizon') or '',
                            method=c.get('method') or '', mechanisms=c.get('mechanisms') or [])
    return prem


# ---- the OWNED verdict templates. Built ONLY from declared field names and surface forms lifted from
#      the spans, so they carry no new particular BY CONSTRUCTION. Each is then run through
#      synthesis_contract.validate() before it is allowed into a plan: THE PLANNER CANNOT PLAN A
#      SENTENCE THE COMPOSER'S GATE WOULD DELETE. That is the floor the synthesis section never had.

def _verdict_text(bundle: Bundle, cf: dict[str, CardFacets]) -> str:
    o = bundle.shared.get('outcome', 'the outcome')
    ids = bundle.card_ids
    if bundle.kind == 'SAME_OUTCOME_DIFFERENT_UNIT':
        ua, ub = (bundle.varies[i] for i in ids)
        if bundle.apparent_conflict:
            return (f'These {o} findings are not contradictory: the two estimates observe different '
                    f'units of analysis, and the evidence establishes the effect at the {ua} level '
                    f'without establishing it at the {ub} level.')
        return (f'The evidence on {o} is limited to two different units of analysis, and the estimates '
                f'do not speak to the same quantity: what holds at the {ua} level does not establish '
                f'a comparable result at the {ub} level.')
    if bundle.kind == 'SAME_UNIT_OPPOSITE_DIRECTION':
        u = bundle.shared.get('unit_of_analysis', 'the same')
        return (f'The evidence on {o} at the {u} level genuinely conflicts: the estimates point in '
                f'opposite directions at the same unit of analysis, so the difference cannot be '
                f'dissolved by appeal to level, and it remains unresolved.')
    if bundle.kind == 'SAME_FINDING_DIFFERENT_METHOD':
        ma, mb = (bundle.varies[i] for i in ids)
        return (f'The {o} finding rests on a {ma} design in one case and a {mb} design in the other; '
                f'the evidence therefore establishes it more securely than either study does alone.')
    if bundle.kind == 'SAME_OUTCOME_DIFFERENT_HORIZON':
        ha, hb = (bundle.varies[i] for i in ids)
        return (f'These {o} estimates differ because they observe different time horizons: the evidence '
                f'is limited to the {ha} in one case and the {hb} in the other, and cannot distinguish '
                f'a transitional effect from a settled one.')
    if bundle.kind == 'UNCOUNTERED':
        u = bundle.shared.get('unit_of_analysis', '')
        return (f'The {o} result at the {u} level rests on a single source, and no other study in this '
                f'literature examines the same outcome at the same unit of analysis; the evidence is '
                f'therefore limited to that setting and cannot distinguish a general pattern from a '
                f'feature of one design.')
    return ''


def _boundary_text(bundle: Bundle, cf: dict[str, CardFacets]) -> str:
    o = bundle.shared.get('outcome', 'the outcome')
    if bundle.incomparability:
        return (f'What the evidence does not settle is the magnitude: the estimates on {o} are not on '
                f'the same footing, and the literature cannot distinguish a real difference from an '
                f'artefact of how each was measured.')
    return (f'What the evidence does not settle is whether the {o} result extends beyond the units and '
            f'horizons these designs observe.')


_BRIDGE = {
    'unit_of_analysis': ('the evidence just reviewed observes {a}, and cannot establish what happens '
                         'once these effects aggregate; the estimates that follow observe {b}'),
    'method': ('the finding above rests on a {a} design; what follows asks whether it survives a {b} '
               'design'),
    'horizon': ('the estimates above are limited to the {a}; what follows observes the {b}'),
    'outcome': ('the evidence above speaks to {a}; the estimates that follow measure {b}'),
    'industry': ('the evidence above is drawn from {a}; what follows asks whether it holds in {b}'),
}


def _bridge_text(axis: str, a: str, b: str) -> str:
    t = _BRIDGE.get(axis)
    if not t or not a or not b or a == b:
        return ''
    return t.format(a=a.replace('_', ' '), b=b.replace('_', ' ')).capitalize() + '.'


# ===================================================================== SUBSECTION PLANS

@dataclass
class SubsectionPlan:
    section: str
    subsection: str
    thesis: SentenceIR | None
    evidence: list[SentenceIR]
    comparison: Bundle | None
    comparable: bool
    incomparability: list[str]
    verdict: SentenceIR | None
    boundary: SentenceIR | None
    bridge: SentenceIR | None
    card_ids: list[str]
    refusals: list[str]

    def sentence_ir(self) -> list[SentenceIR]:
        out = [x for x in [self.thesis] if x]
        out += self.evidence
        out += [x for x in (self.verdict, self.boundary, self.bridge) if x]
        return out


def _relevance(sub: str, c: CardFacets, card: dict) -> int:
    """Retrieval only -- NOT an evidence check. Scored against the SPAN and the declared fields, because
    the claim is a paraphrase and we do not build on paraphrase."""
    want = {w for w in re.findall(r'[a-z]{4,}', sub.lower())}
    blob = f"{card.get('span') or ''} {' '.join(card.get('mechanisms') or [])} " \
           f"{c.f('outcome').value} {c.f('technology').value} {c.f('industry').value} " \
           f"{c.f('unit_of_analysis').value} {c.f('method').value}"
    have = {w for w in re.findall(r'[a-z]{4,}', blob.lower())}
    return len(want & have)


def plan_subsections(cards: list[dict], cfs: list[CardFacets], bundles: list[Bundle],
                     contract: ResearchContract) -> list[SubsectionPlan]:
    cards_by_id = {c['id']: c for c in cards}
    cf_by_id = {c.card_id: c for c in cfs}
    surnames = _corpus_surnames(cards)
    jobs = [(sec, sub) for sec, subs in contract.outline for sub in subs]
    real = [b for b in bundles if b.kind not in ('NOT_A_COMPARISON',)]
    used: set[tuple] = set()
    plans: list[SubsectionPlan] = []

    for sec, sub in jobs:
        refusals: list[str] = []
        scored = sorted(((_relevance(sub, cf_by_id[c['id']], c), c) for c in cards),
                        key=lambda x: -x[0])
        sel = [c for s, c in scored[:12] if s > 0]
        sel_ids = {c['id'] for c in sel}

        # THE COMPARISON: the highest-value bundle whose BOTH cards are relevant to this subsection and
        # which no earlier subsection has already argued. A bundle is never reused -- 41 exact
        # repetitions is what happens when 222 card slots are drawn from 82 cards with no bookkeeping.
        cand = [b for b in real
                if b.key() not in used and set(b.card_ids) <= sel_ids]
        cand.sort(key=lambda b: -b.score)
        bundle = cand[0] if cand else None
        if bundle:
            used.add(bundle.key())
        else:
            refusals.append('no comparison bundle available whose cards are both relevant here -- this '
                            'subsection can REPORT but must not ADJUDICATE')

        # THE EVIDENCE CLAUSES: >= 2, each bound to a CARD_ID, each carrying its own VERBATIM SPAN.
        ev_ids = list(bundle.card_ids) if bundle else []
        for c in sel:
            if len(ev_ids) >= 2:
                break
            if c['id'] not in ev_ids:
                ev_ids.append(c['id'])
        evidence = []
        for cid in ev_ids:
            c = cards_by_id[cid]
            cfx = cf_by_id[cid]
            figs = cfx.numbers
            evidence.append(SentenceIR(
                voice='attributed',
                text=('State this source\'s finding and, where a figure is present, PRINT THE FIGURE. '
                      'Every number must appear in the clause_text below.'),
                source_clauses=[SourceClause(
                    card_id=cid, clause_text=(c.get('span') or '').strip(),
                    attribution=c.get('attribution', ''),
                    unit=c.get('level', ''), method=c.get('method', ''), horizon=c.get('horizon', ''),
                    figures=figs)],
                premise_card_ids=[], role='evidence',
                gate='span-verified at extraction; the writer is bound to clause_text byte-for-byte'))
        if len(evidence) < 2:
            refusals.append('fewer than 2 attributable cards -- no adjudication is possible here')

        # THE OWNED VERDICT. Generated from declared fields + span-lifted surface forms, then VALIDATED.
        verdict = boundary = thesis = None
        comparable = bundle.comparable if bundle else False
        incomp = bundle.incomparability if bundle else ['no comparison was selected']
        if bundle:
            prem = _premises(bundle, cards_by_id)
            blob = ' '.join(p.text + ' ' + p.source for p in prem.values())
            vt = _verdict_text(bundle, cf_by_id)
            ok_safe, why_safe = owned_is_safe(vt, surnames, blob)
            ok_gate, why_gate = validate(
                Synthesis(bundle.operation, list(prem), vt), prem) if ok_safe else (False, why_safe)
            if ok_safe and ok_gate:
                verdict = SentenceIR(
                    voice='owned', text=vt, source_clauses=[],
                    premise_card_ids=list(bundle.card_ids), role='verdict',
                    gate=f'synthesis_contract:{bundle.operation} (PASSED at plan time)')
            else:
                # DO NOT REPAIR. DO NOT SHIP. The plan records that it could not license a verdict.
                refusals.append(f'OWNED verdict refused by the contract '
                                f'({why_safe or why_gate}) -- no verdict is planned for this subsection')

            bt = _boundary_text(bundle, cf_by_id)
            ok_b, why_b = owned_is_safe(bt, surnames, blob)
            if ok_b:
                boundary = SentenceIR(voice='owned', text=bt, source_clauses=[],
                                      premise_card_ids=list(bundle.card_ids), role='boundary',
                                      gate='owned-safety (no source, no particular, no mechanism)')
            else:
                refusals.append(f'boundary refused: {why_b}')

            th = (f'{sub.rstrip(".")} — the evidence below is adjudicated on '
                  f'{bundle.axis.replace("_", " ")}, not merely listed.')
            ok_t, why_t = owned_is_safe(th, surnames, blob)
            thesis = SentenceIR(
                voice='owned',
                text=('Open with a CLAIM that states what this subsection ARGUES, not what it covers. '
                      f'The argument turns on {bundle.axis.replace("_", " ")}: '
                      + ' vs '.join(sorted(set(bundle.varies.values()))) + '.'),
                source_clauses=[], premise_card_ids=list(bundle.card_ids), role='thesis',
                gate='owned-safety' if ok_t else f'owned-safety FAILED: {why_t}')

        plans.append(SubsectionPlan(
            section=sec, subsection=sub, thesis=thesis, evidence=evidence, comparison=bundle,
            comparable=comparable, incomparability=incomp, verdict=verdict, boundary=boundary,
            bridge=None, card_ids=ev_ids, refusals=refusals))

    # THE BRIDGES: computed from the DELTA between consecutive plans -- an analytical movement along a
    # NAMED axis. Never "Turning now to". If no axis moves, there is no bridge and we say nothing.
    for i, p in enumerate(plans[:-1]):
        nxt = plans[i + 1]
        if not (p.comparison and nxt.comparison):
            continue
        for axis in ('unit_of_analysis', 'outcome', 'method', 'horizon', 'industry'):
            a = p.comparison.shared.get(axis) or next(iter(p.comparison.varies.values()), '')
            b = nxt.comparison.shared.get(axis) or next(iter(nxt.comparison.varies.values()), '')
            if a and b and a != b:
                bt = _bridge_text(axis, a, b)
                if not bt:
                    continue
                ok, why = owned_is_safe(bt, _corpus_surnames(cards), ' '.join(
                    (cards_by_id[c].get('span') or '') for c in p.card_ids + nxt.card_ids))
                if ok:
                    p.bridge = SentenceIR(voice='owned', text=bt, source_clauses=[],
                                          premise_card_ids=list(p.comparison.card_ids), role='bridge',
                                          gate=f'owned-safety; analytical movement on {axis}')
                break
    return plans


# ===================================================================== SELF-TEST

def self_test() -> int:
    """THE ADVERSARIAL SUITE. Every attack here is a FALSE RECONCILIATION -- the failure mode a planner
    is uniquely able to produce, and the one no downstream gate can catch, because the lie is in the
    RELATION and every particular in the sentence is true."""
    print('=== ARGUMENT PLANNER — adversarial suite ===')
    print('    (the planner\'s unique failure is the FALSE RECONCILIATION: a true sentence about a\n'
          '     relation that does not exist. Every attack below is one.)\n')
    ct = default_contract()
    fails = 0

    def check(name: str, ok: bool, detail: str = '') -> None:
        nonlocal fails
        print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
        if detail:
            print(f'            {detail}')
        if not ok:
            fails += 1

    # 1. a span with NO polarity cue must NOT get a direction
    d = derive_direction('we estimate the probability of computerisation for 702 occupations',
                         ct, [p for v in ct.span_facets['outcome'].values() for p in v])
    check('no polarity cue -> direction is UNKNOWN (cannot enter a conflict)', not d.known,
          f'assigned {d.value}' if d.known else '')

    # 2. a span firing BOTH polarities is UNKNOWN, not a conflict
    d2 = derive_direction('robots reduce employment while raising the productivity of the firm',
                          ct, [p for v in ct.span_facets['outcome'].values() for p in v])
    check('a span that fires BOTH polarities -> UNKNOWN (a mixed span is not a direction)',
          not d2.known, f'assigned {d2.value}' if d2.known else '')

    # 3. NEGATION IS DISCARDED, NEVER FLIPPED
    d3 = derive_direction('we find no significant increase in employment in the treated regions',
                          ct, [p for v in ct.span_facets['outcome'].values() for p in v])
    check('a negated cue is DISCARDED, not flipped (flipping is inference)',
          d3.value != 'positive', f'read a negated "increase" as {d3.value}')

    # 4. a polarity cue far from the outcome does not colour the outcome
    d4 = derive_direction('the model improves prediction accuracy; employment is measured separately',
                          ct, [p for v in ct.span_facets['outcome'].values() for p in v])
    check('a polarity cue about something else does not become the outcome\'s direction',
          not d4.known or d4.evidence != 'improves',
          'read "improves prediction accuracy" as a positive EMPLOYMENT finding')

    # 5. TWO CARDS FROM ONE PAPER ARE NOT A COMPARISON
    mk = lambda i, doi, span, lvl, meth, hor: {
        'id': i, 'doi': doi, 'span': span, 'claim': 'IGNORED — model-authored', 'level': lvl,
        'method': meth, 'horizon': hor, 'mechanisms': [], 'authors': ['Solo'], 'year': 2020,
        'venue': 'J', 'attribution': 'Writing in J in 2020, Solo', 'source': 'Solo (2020), J',
        'has_number': True}
    same = [mk('a', '10.1/x', 'employment increased by 4.15 percent at the firm', 'firm',
               'observational', 'long-run'),
            mk('b', '10.1/x', 'employment increased by 12.0 percent in the economy', 'economy',
               'observational', 'long-run')]
    cf = [derive_facets(c, ct) for c in same]
    bs = [b for b in find_bundles(cf, ct, {c['id']: c for c in same}) if b.kind != 'NOT_A_COMPARISON']
    check('two cards from the SAME PAPER cannot form a comparison bundle',
          not any(len(b.card_ids) == 2 for b in bs),
          'a paper was allowed to corroborate itself')

    # 6. THE HEADLINE ATTACK: same outcome, different unit, DIRECTIONS UNKNOWN.
    #    The planner may NOT say "they only look contradictory". There was no conflict to dissolve.
    two = [mk('a', '10.1/x', 'the share of employment in routine occupations is measured across the '
                             'economy', 'economy', 'observational', 'long-run'),
           mk('b', '10.2/y', 'we document the employment of workers within the firm', 'firm',
              'observational', 'long-run')]
    two[1]['authors'] = ['Duo']
    two[1]['source'] = 'Duo (2020), J'
    cf2 = [derive_facets(c, ct) for c in two]
    b2 = [b for b in find_bundles(cf2, ct, {c['id']: c for c in two})
          if b.kind == 'SAME_OUTCOME_DIFFERENT_UNIT']
    ok = bool(b2) and not b2[0].apparent_conflict
    vt = _verdict_text(b2[0], {c.card_id: c for c in cf2}) if b2 else ''
    check('NO apparent conflict -> the verdict does NOT say "not contradictory"',
          ok and 'not contradictory' not in vt,
          f'FALSE RECONCILIATION: "{vt[:80]}"' if 'not contradictory' in vt else
          f'planned: "{vt[:76]}..."')

    # 7. an OWNED verdict may never name a source
    ok7, why7 = owned_is_safe('Acemoglu and Restrepo establish that the two estimates differ by level.',
                              {'Acemoglu', 'Restrepo'}, 'blob')
    check('an OWNED verdict that names a source is REFUSED', not ok7, why7)

    # 8. an OWNED verdict may never carry a figure
    ok8, _ = owned_is_safe('The evidence establishes a 47 percent effect at the task level.',
                           set(), 'blob')
    check('an OWNED verdict that carries a figure is REFUSED', not ok8)

    # 9. a bundle whose axis is MISSING on one card is refused as a comparison
    nohor = [mk('a', '10.1/x', 'employment fell in the treated regions', 'firm', 'observational', ''),
             mk('b', '10.2/y', 'employment fell across the economy', 'economy', 'observational', '')]
    nohor[1]['authors'] = ['Duo']
    cfn = [derive_facets(c, ct) for c in nohor]
    bn = find_bundles(cfn, ct, {c['id']: c for c in nohor})
    check('a HORIZON bundle is never built when the horizon is not declared on both cards',
          not any(b.kind == 'SAME_OUTCOME_DIFFERENT_HORIZON' for b in bn),
          'the planner invented a horizon contrast out of two blank fields')

    # 10. the derivation path cannot see `claim`
    poisoned = mk('a', '10.1/x', 'employment is measured', 'firm', 'observational', 'long-run')
    poisoned['claim'] = 'employment collapsed by 99 percent, according to Goldman Sachs'
    pf = derive_facets(poisoned, ct)
    check('a figure/entity hallucinated into `claim` never reaches a facet or a figure list',
          '99' not in pf.numbers and pf.f('direction').value != 'negative',
          'the claim leaked into the derivation path')

    print()
    if fails:
        print(f'** {fails} FAILURE(S). THE PLANNER CAN MANUFACTURE A FALSE RECONCILIATION. **')
        return 1
    print('** PLANNER GREEN: it refuses every comparison it cannot license. **')
    return 0


# ===================================================================== REPORT

def _short(card: dict) -> str:
    return f"{(card.get('authors') or ['?'])[0]} {card.get('year')}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--cards', default=str(cards_path()))
    ap.add_argument('--contract', default='')
    ap.add_argument('--bundles', action='store_true')
    ap.add_argument('--plans', action='store_true')
    ap.add_argument('--ir', default='')
    ap.add_argument('--json', default='')
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    ct = ResearchContract.load(Path(a.contract)) if a.contract else default_contract()
    cards = json.loads(Path(a.cards).read_text())
    cards_by_id = {c['id']: c for c in cards}
    cfs = [derive_facets(c, ct) for c in cards]
    bundles = find_bundles(cfs, ct, cards_by_id)
    real = [b for b in bundles if b.kind != 'NOT_A_COMPARISON']
    refused = [b for b in bundles if b.kind == 'NOT_A_COMPARISON']

    print(f'=== ARGUMENT PLANNER over {len(cards)} cards / '
          f'{len({c["doi"] for c in cards})} journal articles ===')
    print(f'    contract: {ct.question}')
    print(f'    THE SPAN IS THE ONLY EVIDENCE. `claim` is never read on a derivation path.\n')

    # ---- what the corpus can actually key on
    print('--- FACET AVAILABILITY (a facet nothing declares can key NOTHING) ---')
    for fn in ('unit_of_analysis', 'method', 'horizon', 'outcome', 'technology', 'industry',
               'geography', 'direction'):
        known = [c for c in cfs if c.f(fn).known]
        prov = 'declared' if fn in ct.declared_facets else 'span-derived'
        verdict = ''
        if len(known) < len(cfs) * 0.10:
            verdict = '  <-- DEAD FACET: it cannot key a comparison on this corpus'
        print(f'  {fn:<18} {len(known):>3}/{len(cfs)}  ({prov}){verdict}')
    print(f'  {"span-verified figure":<18} {sum(1 for c in cfs if c.quantitative):>3}/{len(cfs)}'
          f'  (recomputed from the span; `has_number` reads the claim and undercounts)')

    print(f'\n--- COMPARISON BUNDLES: {len(real)} licensed, {len(refused)} REFUSED ---')
    by_kind: dict[str, list[Bundle]] = {}
    for b in real:
        by_kind.setdefault(b.kind, []).append(b)
    for k in ('SAME_UNIT_OPPOSITE_DIRECTION', 'SAME_FINDING_DIFFERENT_METHOD',
              'SAME_OUTCOME_DIFFERENT_UNIT', 'SAME_OUTCOME_DIFFERENT_HORIZON', 'UNCOUNTERED'):
        bs = by_kind.get(k, [])
        print(f'\n  {k}  ({len(bs)})')
        print(f'    {BUNDLE_KINDS[k]}')
        if not bs:
            print('    -- none. The corpus does not support this comparison. --')
        for b in bs[:6]:
            print()
            for cid in b.card_ids:
                c = cards_by_id[cid]
                cf = next(x for x in cfs if x.card_id == cid)
                figs = f"  FIGURES={cf.numbers}" if cf.numbers else ''
                print(f'      [{_short(c):<16}] {b.varies.get(cid, "")or b.shared.get(b.axis,"")}'
                      f'  ({c.get("method")}/{c.get("horizon") or "no-horizon"}){figs}')
                print(f'          span: "{re.sub(chr(10), " ", (c.get("span") or ""))[:104]}..."')
            print(f'      axis={b.axis}  shared={b.shared}  op={b.operation}  score={b.score:.1f}')
            print(f'      apparent_conflict={b.apparent_conflict}  comparable={b.comparable}')
            if b.incomparability:
                print(f'      NOT COMPARABLE: {b.incomparability[0]}')
            if b.note:
                print(f'      -> {b.note}')

    if a.bundles:
        return 0

    # ---- the outline vs the corpus
    print('\n--- COVERAGE: DOES THE CORPUS COVER WHAT THE OUTLINE PROMISES? ---')
    for g in coverage_gaps(cfs, ct):
        flag = '  <-- the outline cannot cash this cheque' if g['sources'] <= 1 else ''
        print(f"  {g['industry']:<16} {g['sources']:>2} source(s){flag}")

    plans = plan_subsections(cards, cfs, bundles, ct)
    with_cmp = [p for p in plans if p.comparison]
    with_vd = [p for p in plans if p.verdict]
    print(f'\n--- SUBSECTION PLANS: {len(plans)} ---')
    print(f'    with a licensed comparison : {len(with_cmp)}')
    print(f'    with a CONTRACT-VALIDATED owned verdict: {len(with_vd)}')
    print(f'    refusing to adjudicate     : {len(plans) - len(with_cmp)}  (they may REPORT, not ADJUDICATE)')

    if a.plans or a.ir:
        for p in plans:
            if a.ir and a.ir.lower() not in p.subsection.lower():
                continue
            print(f'\n  === {p.section} / {p.subsection}')
            if p.comparison:
                b = p.comparison
                print(f'      COMPARISON  {b.kind} on {b.axis}')
                print(f'      cards       {[_short(cards_by_id[c]) for c in b.card_ids]}')
                print(f'      comparable  {b.comparable}')
                for w in b.incomparability:
                    print(f'          why not: {w}')
            for s in p.sentence_ir():
                print(f'      [{s.voice:<10}|{s.role:<8}] {s.text[:96]}')
                for sc in s.source_clauses:
                    print(f'           card_id={sc.card_id}  figures={sc.figures}')
                    print(f'           VERBATIM: "{sc.clause_text[:88]}..."')
                if s.gate:
                    print(f'           gate: {s.gate}')
            for r in p.refusals:
                print(f'      REFUSAL: {r}')

    if a.json:
        Path(a.json).write_text(json.dumps({
            'question': ct.question,
            'bundles': [asdict(b) for b in real],
            'refused': [asdict(b) for b in refused],
            'plans': [{**asdict(p), 'sentence_ir': [asdict(s) for s in p.sentence_ir()]}
                      for p in plans],
        }, indent=1, default=str))
        print(f'\nwrote {a.json}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
