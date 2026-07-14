#!/usr/bin/env python3
"""insight_value.py -- SOL PLAN 4, item 5: MARGINAL-INSIGHT SCHEDULING.

The acquisition objective is not "more papers". It is MARGINAL INSIGHT READINESS, and it is a VECTOR
that is retained -- never collapsed to a scalar -- all the way through composition:

    value(candidate) = new required-cell coverage
                     + a complete, interpretable result tuple
                     + independent corroboration
                     + method / population / context contrast
                     + null-or-counterevidence
                     + current-frontier contribution
                     + explains-an-existing-contradiction
                     - same-study / same-version redundancy

"A FIFTH POSITIVE ESTIMATE IN THE SAME CONTEXT usually adds less insight than THE FIRST CREDIBLE NULL,
a different population, or a design that resolves a disagreement." So this module actively values
nulls, counterexamples, and different methods, and it DEMOTES redundancy. It DOES NOT collapse quality
into one number: authority, method quality (with risk-of-bias carried explicitly), relevance,
independence, recency, and contrast value stay SEPARATE dimensions, and the ranking is LEXICOGRAPHIC
over the insight vector -- so a high-authority venue can never buy rank over a genuine null.

GENERALITY. The unit of "independent" evidence is the evidence-unit FAMILY from provenance/research_
contract: a STUDY or a DECISION, never a document -- so two versions of one working paper are one
voice, and (legally) two reporters of one judgment are one decision while "two sources" NEVER
substitutes for one controlling authority. The cells vary by domain because the CONTRACT does
(clinical: population x intervention x comparator x outcome x time; legal: jurisdiction x issue x
authority-level x period). This file branches on none of it.

It plugs straight into gap_search: for every gap cell, `target_profile()` says WHICH insight vector a
candidate would have to carry to be worth acquiring -- turning the gap census (item 4) into a ranked
acquisition schedule (item 5).
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ROOT = HERE.parent

import research_contract as RC
import event_ledger as EL
import gap_search as GS                 # BUILD ON IT: load_state, analyze, the funnel + shape helpers


# =============================================================================== the insight vector
@dataclass
class InsightVector:
    """The marginal value of ONE candidate (an evidence-unit family) given the corpus we already hold.
    Every field is a SEPARATE, named observation. Nothing here is summed into a quality scalar."""
    family: str
    label: str
    # ---- marginal INSIGHT components (item 5's value() terms) ----
    new_cell_coverage: int = 0        # required cells this family alone keeps at/above closure
    completes_tuple: int = 0          # carries a complete, interpretable result tuple
    independent_corroboration: int = 0   # cells where it corroborates >=1 OTHER independent unit
    method_contrast: int = 0          # cells where it adds a design no other unit here provides
    context_contrast: int = 0         # cells where it adds a population/context no other unit provides
    null_or_counter: int = 0          # it contributes null / counter-evidence
    current_frontier: int = 0         # its newest evidence is at/after the recency frontier
    explains_contradiction: int = 0   # cells in conflict where it carries the missing moderator
    redundancy: int = 0               # cells where it only repeats a design+context already held
    # ---- SEPARATE quality dimensions (kept apart, never collapsed) ----
    authority: str = ''               # venue / authority label (legal: authority level)
    method_quality: str = ''          # design vocabulary present
    risk_of_bias: str = 'unstated'    # carried EXPLICITLY, never averaged away
    relevance: int = 0                # required cells it routes to at all
    independence: int = 1             # it is ONE independent evidence unit (a study / a decision)
    n_cards: int = 0                  # how many cards restate this one unit (card-level redundancy)
    recency: int | None = None
    notes: list[str] = field(default_factory=list)

    def rank_key(self) -> tuple:
        """LEXICOGRAPHIC priority. Ascending sort => most marginal insight first. Authority is NOT in
        the key: it is a separate dimension and may never trade against a null or a contrast."""
        return (
            -self.new_cell_coverage,                              # 1. load-bearing coverage
            -(self.explains_contradiction + self.null_or_counter),  # 2. resolve/ add counter-evidence
            -(self.method_contrast + self.context_contrast),     # 3. a genuine contrast
            -self.independent_corroboration,                     # 4. corroboration of another unit
            -self.completes_tuple,                               # 5. a complete result tuple
            -self.current_frontier,                              # 6. current-frontier contribution
            self.redundancy,                                     # 7. redundancy DEMOTES
            -self.relevance,                                     # 8. broad relevance breaks ties
        )

    def dominates(self, other: 'InsightVector') -> bool:
        """Pareto domination over the insight dimensions (redundancy inverted). Makes the vector's
        multi-dimensionality explicit: a family on the frontier is beaten by no single other family."""
        dims = ['new_cell_coverage', 'completes_tuple', 'independent_corroboration', 'method_contrast',
                'context_contrast', 'null_or_counter', 'current_frontier', 'explains_contradiction']
        ge = all(getattr(self, d) >= getattr(other, d) for d in dims) and self.redundancy <= other.redundancy
        gt = any(getattr(self, d) > getattr(other, d) for d in dims) or self.redundancy < other.redundancy
        return ge and gt

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================== computation
def _family_of(card: dict) -> str:
    fam, _ = RC.evidence_unit_of(card)
    return fam


def _closed_keys(matrix) -> set:
    return {k for k, c in matrix.cells.items() if c.status in (RC.CLOSED, RC.THIN)}


def marginal_vectors(contract, cards: list[dict], ledger: EL.Ledger,
                     vocab: dict | None = None) -> list[InsightVector]:
    """For each independent evidence-unit family, its marginal value GIVEN THE REST of the corpus --
    computed by leaving the family out of the coverage matrix and diffing (provenance's evidence-unit
    families are the leave-one-out unit, so removing a version-twin would change nothing)."""
    vocab = vocab or GS.load_vocab()
    mod_vocab = GS._shape(vocab, 'moderator', GS.genre_tags(contract))
    frontier = GS.frontier_year(contract)
    idx = {c.get('id'): c for c in cards}

    fam_cards: dict[str, list[dict]] = collections.defaultdict(list)
    for c in cards:
        fam_cards[_family_of(c)].append(c)

    full = RC.coverage_matrix(copy.deepcopy(contract), cards, corpus=[], ledger=ledger)
    closed_full = _closed_keys(full)

    # per-cell, per-family design/context contributions -- reconstructed from the matrix's own routing.
    cell_fam_design: dict = collections.defaultdict(lambda: collections.defaultdict(set))
    cell_fam_ctx: dict = collections.defaultdict(lambda: collections.defaultdict(set))
    cell_fam_null: dict = collections.defaultdict(lambda: collections.defaultdict(bool))
    cell_fam_res: dict = collections.defaultdict(lambda: collections.defaultdict(bool))
    for key, cell in full.cells.items():
        for cid in cell.card_ids:
            c = idx.get(cid)
            if not c:
                continue
            fm = _family_of(c)
            if GS._card_design(c):
                cell_fam_design[key][fm].add(GS._card_design(c))
            if GS._card_context(c):
                cell_fam_ctx[key][fm].add(GS._card_context(c))
            cell_fam_null[key][fm] = cell_fam_null[key][fm] or GS._is_null(c)
            cell_fam_res[key][fm] = cell_fam_res[key][fm] or (GS._has_result(c) and not GS._is_null(c))

    out: list[InsightVector] = []
    for fam, fcards in fam_cards.items():
        if not fam:
            continue
        v = InsightVector(family=fam, label=_family_label(fcards))
        v.n_cards = len(fcards)
        v.recency = max((GS._card_year(c) for c in fcards if GS._card_year(c)), default=None)
        v.current_frontier = int(frontier is not None and v.recency is not None and v.recency >= frontier)
        v.completes_tuple = int(any(c.get('complete_tuple') for c in fcards))
        v.method_quality = ', '.join(sorted({GS._card_design(c) for c in fcards if GS._card_design(c)}))
        v.authority = _authority(fcards)
        v.risk_of_bias = _risk_of_bias(fcards)

        # leave-one-family-out coverage delta.
        minus = RC.coverage_matrix(copy.deepcopy(contract),
                                   [c for c in cards if _family_of(c) != fam], corpus=[], ledger=ledger)
        v.new_cell_coverage = len(closed_full - _closed_keys(minus))

        # in-cell contrasts, corroboration, redundancy.
        cells_here = [k for k, c in full.cells.items() if fam in c.families]
        v.relevance = len(cells_here)
        for key in cells_here:
            others = [o for o in full.cells[key].families if o != fam]
            if others:
                v.independent_corroboration += 1
            # a null / counter-estimate is valued ONLY where it lands in a required cell (a null about
            # nothing the review asks is not counter-evidence). Counting per-cell gates it by relevance.
            if cell_fam_null[key][fam]:
                v.null_or_counter += 1
            others_designs = set().union(*(cell_fam_design[key][o] for o in others)) if others else set()
            others_ctx = set().union(*(cell_fam_ctx[key][o] for o in others)) if others else set()
            my_designs = cell_fam_design[key][fam]
            my_ctx = cell_fam_ctx[key][fam]
            if my_designs - others_designs:
                v.method_contrast += 1
            if my_ctx - others_ctx:
                v.context_contrast += 1
            # redundant here: adds no new design AND no new context, and someone else already carries a
            # result in this cell -- the "fifth positive estimate in the same context".
            if others and not (my_designs - others_designs) and not (my_ctx - others_ctx) \
                    and any(cell_fam_res[key][o] or cell_fam_null[key][o] for o in others):
                v.redundancy += 1
            # explains a contradiction: this cell holds both a null and a non-null unit, and THIS family
            # carries the moderator that would reconcile them.
            has_conflict = any(cell_fam_null[key].values()) and any(cell_fam_res[key].values())
            if has_conflict and any(GS._contains_any(c.get('span', ''), mod_vocab)
                                    for c in fcards if c.get('id') in set(full.cells[key].card_ids)):
                v.explains_contradiction += 1
        out.append(v)

    out.sort(key=lambda v: v.rank_key())
    return out


def pareto_frontier(vectors: list[InsightVector]) -> list[InsightVector]:
    return [v for v in vectors if not any(o.dominates(v) for o in vectors if o is not v)]


def _family_label(fcards: list[dict]) -> str:
    for c in fcards:
        if c.get('attribution'):
            return c['attribution'][:60]
        if c.get('authors'):
            a = c['authors']
            return f'{a[0] if a else "?"} et al. ({c.get("year","")})'
    return fcards[0].get('doi', '?') if fcards else '?'


def _authority(fcards: list[dict]) -> str:
    for c in fcards:
        if c.get('venue'):
            return c['venue']
        if c.get('authority'):
            return c['authority']
    return ''


def _risk_of_bias(fcards: list[dict]) -> str:
    """Carried EXPLICITLY. A methodological_limitation act or a stated limitation/uncertainty facet is
    the source declaring its own bounds; otherwise it is UNSTATED (which is itself a risk signal)."""
    if any(c.get('act') == 'methodological_limitation' for c in fcards):
        return 'stated (limitation act)'
    if any((c.get('limitation') or c.get('uncertainty') or '').strip() for c in fcards):
        return 'stated (facet)'
    return 'unstated'


# =============================================================================== acquisition schedule
def target_profile(gap_result) -> dict:
    """Given a gap cell (from gap_search.analyze), the insight vector a candidate MUST carry to be
    worth acquiring for it. This is where item 4 (what is missing) becomes item 5 (what to prefer)."""
    g = gap_result.gap
    base = {'cell': gap_result.funnel.cellkey, 'gap': g}
    want = {
        GS.DISCOVERY_GAP:     {'new_cell_coverage': '>0', 'completes_tuple': 'preferred'},
        GS.ACCESS_GAP:        {'independence': 'the SAME work, made groundable (no new unit)'},
        GS.EXTRACTION_GAP:    {'completes_tuple': 'from held text', 'new_cell_coverage': 'via placement'},
        GS.DIVERSITY_GAP:     {'method_contrast': '>0', 'context_contrast': '>0', 'null_or_counter': 'high value'},
        GS.RECENCY_GAP:       {'current_frontier': '1', 'new_cell_coverage': 'preferred'},
        GS.CONTRADICTION_GAP: {'explains_contradiction': '1', 'null_or_counter': 'or a reconciling synthesis'},
        GS.EVIDENCE_GAP:      {'_terminal': 'acquire nothing; STOP (saturated)'},
        GS.NOT_A_GAP:         {'_terminal': 'satisfied; a further same-context unit is REDUNDANCY'},
        GS.BUDGET_STOP:       {'_terminal': 'lift the budget; not an evidence decision'},
    }.get(g, {})
    base['acquire_a_candidate_with'] = want
    return base


# =============================================================================== CLI
def _fmt_vec(v: InsightVector) -> str:
    pos = []
    for k in ('new_cell_coverage', 'null_or_counter', 'explains_contradiction', 'method_contrast',
              'context_contrast', 'independent_corroboration', 'completes_tuple', 'current_frontier'):
        val = getattr(v, k)
        if val:
            pos.append(f'{k}={val}')
    tail = f'  [redundancy={v.redundancy}]' if v.redundancy else ''
    return '  '.join(pos) + tail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--contract', default=str(GS.DEFAULT_CONTRACT))
    ap.add_argument('--cards', default=str(GS.DEFAULT_CARDS))
    ap.add_argument('--ledger', default=str(GS.DEFAULT_LEDGER))
    ap.add_argument('--schedule', action='store_true',
                    help='also print the per-gap acquisition target profiles')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    vocab = GS.load_vocab()
    contract, cards, ledger = GS.load_state(a.contract, a.cards, a.ledger)
    vectors = marginal_vectors(contract, cards, ledger, vocab)

    if a.json:
        print(json.dumps({'ranking': [v.to_dict() for v in vectors],
                          'pareto_frontier': [v.family for v in pareto_frontier(vectors)]}, indent=1))
        return 0

    n_fam = len(vectors)
    n_cards = sum(v.n_cards for v in vectors)
    print(f'CONTRACT: {contract.review_subject or contract.question[:70]!r}')
    print(f'  {n_cards} cards collapse to {n_fam} INDEPENDENT evidence-unit families (studies), the '
          f'unit of marginal value.')
    print(f'  quality is a VECTOR, not a scalar; ranking is lexicographic over insight (authority '
          f'never buys rank).')
    print('\nMARGINAL-INSIGHT RANKING (most marginal insight first):')
    print('=' * 96)
    for i, v in enumerate(vectors, 1):
        print(f'{i:2}. {v.label}')
        print(f'    INSIGHT: {_fmt_vec(v) or "(adds no new insight dimension)"}')
        print(f'    quality (SEPARATE): authority={v.authority!r}  method={v.method_quality or "-"!r}  '
              f'risk_of_bias={v.risk_of_bias!r}  recency={v.recency}  relevance={v.relevance}cells  '
              f'restated_by={v.n_cards}cards')
    front = pareto_frontier(vectors)
    print('\nPARETO FRONTIER (non-dominated on the insight dimensions -- proves it is multi-dimensional):')
    for v in front:
        print(f'    * {v.label}  <-  {_fmt_vec(v) or "(dominant on some single dimension)"}')

    # the thesis, on the real corpus: a null / contrast unit outranks a redundant same-context one.
    nulls = [v for v in vectors if v.null_or_counter]
    reds = [v for v in vectors if v.redundancy and not v.null_or_counter and not v.new_cell_coverage]
    print('\nTHE THESIS, HELD ALL ELSE EQUAL (first credible null > fifth positive in the same context):')
    fifth_positive = InsightVector(family='cand_A', label='a 5th positive estimate, same context',
                                   redundancy=1, authority='top-tier journal', relevance=1)
    first_null = InsightVector(family='cand_B', label='the first credible null, same cell',
                               null_or_counter=1, authority='mid-tier journal', relevance=1)
    winner = min([fifth_positive, first_null], key=lambda v: v.rank_key())
    print(f'    5th-positive (authority=top-tier, redundancy=1) rank_key={fifth_positive.rank_key()}')
    print(f'    first-null   (authority=mid-tier, null=1)       rank_key={first_null.rank_key()}')
    print(f'    -> preferred candidate: {winner.label!r} (authority did NOT rescue the redundant one)')

    print('\nTHE THESIS ON THIS CORPUS:')
    if nulls:
        b = nulls[0]
        print(f'    null/counter-evidence unit ranks #{vectors.index(b)+1}: {b.label} '
              f'(null_or_counter={b.null_or_counter})')
    if reds:
        w = reds[-1]
        print(f'    a purely-redundant same-context unit ranks #{vectors.index(w)+1}: {w.label} '
              f'(redundancy={w.redundancy}, adds no new dimension)')
    if not reds:
        print('    (no family is purely redundant here -- with only ten works each still carries a '
              'distinct design or context; redundancy bites hardest at the CARD level, where '
              f'{n_cards} cards restate {n_fam} units)')

    if a.schedule:
        print('\nACQUISITION SCHEDULE -- what to acquire for each open gap (item 4 -> item 5):')
        print('=' * 96)
        results = GS.analyze(contract, cards, ledger, vocab)
        order = {g: i for i, g in enumerate(GS.GAP_TYPES)}
        gaps = [r for r in results if r.gap in GS.GAP_TYPES]
        seen = set()
        for r in sorted(gaps, key=lambda r: order.get(r.gap, 99)):
            if r.gap in seen:
                continue
            seen.add(r.gap)
            tp = target_profile(r)
            print(f'  {r.gap} (e.g. [{r.cell.row_label} x {r.cell.col_label}]):')
            print(f'      acquire a candidate with -> {tp["acquire_a_candidate_with"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
