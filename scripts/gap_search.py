#!/usr/bin/env python3
"""gap_search.py -- SOL PLAN 4, item 4: GAP-DRIVEN RECURSIVE SEARCH.

A COVERAGE CELL IS AN EVIDENCE REQUIREMENT, NOT A TOPIC KEYWORD. After each acquisition/extraction
round the pipeline holds a coverage matrix (research_contract.coverage_matrix). Every cell that has
not closed is a DIFFERENT KIND of gap, and each kind is answered by a DIFFERENT query family -- never
by another copy of the broad query.

    DISCOVERY_GAP     no candidate was ever found for this requirement
    ACCESS_GAP        a candidate exists but we hold no admissible, complete manifestation of it
    EXTRACTION_GAP    we hold the text, but no result span was extracted / the card could not be placed
    DIVERSITY_GAP     the evidence is real but comes from one study / one design / one context
    RECENCY_GAP       the claim is time-sensitive and our newest evidence is behind the frontier
    CONTRADICTION_GAP the findings conflict and the moderator that would reconcile them is missing
    EVIDENCE_GAP      routes are SATURATED and no eligible evidence exists -- the terminal state

A cell closes on evidence only with enough independent, result-bearing evidence for the requested
comparison. It closes as THIN only after multiple databases + query families + citation chasing +
version pursuit + recent queries were attempted and duplicates collapsed. THIS IS OPERATIONAL
SATURATION, not a claim of exhaustive recall. A BUDGET STOP IS NOT A GAP -- we do not know what is
there, so it is a pipeline limitation, reported as one.

GENERALITY IS NOT OPTIONAL (and it is DATA, not code). This file names no topic. Every query term is
drawn from the compiled contract (aliases the field's own papers print, the study designs that count
as evidence in this field, the recency floor the question imposed). The evidence-SHAPE vocabulary (a
null, a moderator, a synthesis) lives in config/gap_search_vocab.json. A domain change -- a clinical
question, a legal question, a thin-evidence question -- is a NEW CONTRACT (a data artifact), never an
edit here. Run `--demo-generality` to see one mechanism produce clinical, legal, and thin-evidence
behaviour from three different contracts with no branch on the domain.

THE LAW this serves: only SEARCHED_NONE after ADEQUATE route completion licenses an absence sentence
(event_ledger.derive_coverage_status). A DISCOVERY / ACCESS / EXTRACTION gap NEVER licenses an
absence; only a SATURATED EVIDENCE_GAP with a SEARCHED_NONE ledger does. For a thin-evidence question,
"the literature does not settle this" is the CORRECT answer, and an EVIDENCE_GAP that reaches THIN or
CONFLICTED is a SUCCESSFUL terminal state, not a failure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
ROOT = HERE.parent

import research_contract as RC          # the contract + coverage matrix we plug into
import event_ledger as EL              # the reducers that license (or forbid) an absence
import recency as RCY                  # the FRONTIER lane: date windows, SORTED BY DATE, never by cites
import weighting as WGT                # field-normalized quality VECTOR -- never a bare citation count

# ---- the seven gap types, plus two honest NON-gap verdicts ------------------------------------
DISCOVERY_GAP     = 'DISCOVERY_GAP'
ACCESS_GAP        = 'ACCESS_GAP'
EXTRACTION_GAP    = 'EXTRACTION_GAP'
DIVERSITY_GAP     = 'DIVERSITY_GAP'
RECENCY_GAP       = 'RECENCY_GAP'
CONTRADICTION_GAP = 'CONTRADICTION_GAP'
EVIDENCE_GAP      = 'EVIDENCE_GAP'
NOT_A_GAP         = 'NOT_A_GAP'        # the cell is adequately closed -- nothing to search for
BUDGET_STOP       = 'BUDGET_STOP'      # we stopped on budget: NOT a gap, a limitation

GAP_TYPES = [DISCOVERY_GAP, ACCESS_GAP, EXTRACTION_GAP, DIVERSITY_GAP,
             RECENCY_GAP, CONTRADICTION_GAP, EVIDENCE_GAP]

_VOCAB_PATH = ROOT / 'config' / 'gap_search_vocab.json'


# =============================================================================== the shape registry
def load_vocab(path: Path | str = _VOCAB_PATH) -> dict:
    """The evidence-SHAPE registry. Domain-general; the contract carries the domain."""
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    # A missing file must not silently disable the mechanism, but it also must not invent domain
    # knowledge. The embedded default is a faithful copy of the checked-in registry.
    return {
        'evidence_shape': {
            'null_result': ['no significant', 'no significant effect', 'no association', 'null result',
                            'statistically insignificant', 'not significant', 'found no evidence',
                            'did not differ', 'no detectable'],
            'moderator': ['moderator', 'moderating', 'subgroup', 'heterogeneity', 'interaction effect',
                          'depends on', 'conditional on', 'boundary condition', 'contingent on', 'varies by'],
            'counterevidence': ['contrary to', 'contradicts', 'challenges', 'in contrast to',
                                'fails to replicate', 'does not support', 'inconsistent with'],
            'synthesis_designs': ['systematic review', 'meta-analysis', 'meta analysis', 'scoping review',
                                  'evidence synthesis'],
            'by_genre': {},
        },
        'adapters': {'discovery': ['openalex', 'semantic_scholar', 'crossref'],
                     'access': ['unpaywall', 'openalex_locations', 'arxiv', 'content_host'],
                     'extraction': [], 'diversity': ['openalex', 'semantic_scholar', 'openalex_citations'],
                     'recency': ['openalex_recent', 'arxiv', 'semantic_scholar'],
                     'contradiction': ['openalex_citations', 'semantic_scholar', 'crossref'], 'evidence': []},
        'saturation': {'min_query_families': 3, 'min_adapters': 2,
                       'required_families': ['discovery', 'diversity', 'recency']},
        'limits': {'max_terms_per_query': 8, 'max_queries_per_family': 6, 'max_concept_aliases': 6},
    }


def genre_tags(contract) -> set[str]:
    """The DATA tags that select a genre-specific shape block: the contract's genre AND its study-
    design vocabulary (so a 'case-law analysis' block fires for a legal contract whose genre string is
    'analytical report with recommendations'). All from the contract; nothing hard-coded."""
    tags = {(getattr(contract, 'genre', '') or '').lower()}
    tags |= {(m or '').lower() for m in (getattr(contract, 'method_designs', None) or [])}
    return tags


def _shape(vocab: dict, key: str, tags: set[str] | str = '') -> list[str]:
    """A shape list, with any genre-specific rows merged in. Merging a genre row is a DATA edit."""
    es = vocab.get('evidence_shape', {})
    out = list(es.get(key, []))
    tagset = {tags.lower()} if isinstance(tags, str) else {str(t).lower() for t in tags}
    for gk, block in (es.get('by_genre', {}) or {}).items():
        if isinstance(block, dict) and gk.lower() in tagset:
            for w in block.get(key, []):
                if w not in out:
                    out.append(w)
    return out


# =============================================================================== small pure helpers
def _flatten_aliases(terms: list, cap: int | None = None) -> list[str]:
    """The surface forms a matcher/searcher would actually look for -- label + aliases, from the
    contract. NOTHING here is written by this module."""
    out: list[str] = []
    for t in terms or []:
        label = getattr(t, 'label', None) or (t.get('label') if isinstance(t, dict) else str(t))
        aliases = getattr(t, 'aliases', None) or (t.get('aliases') if isinstance(t, dict) else []) or []
        for s in [label, *aliases]:
            if s and s not in out:
                out.append(s)
    return out[:cap] if cap else out


def _contains_any(text: str, vocab: list[str]) -> bool:
    """DATA vocabulary matched against verbatim text -- the same operation research_contract uses to
    route a span. It is never a topic gate: the vocabulary describes the SHAPE of evidence."""
    t = (text or '').lower()
    return any(w in t for w in vocab)


def _card_year(card: dict) -> int | None:
    y = card.get('year')
    return y if isinstance(y, int) else None


def _card_design(card: dict) -> str:
    return (card.get('method') or card.get('study_design') or card.get('design') or '').strip().lower()


def _card_context(card: dict) -> tuple:
    """The population / place / setting a finding is about -- used to tell 'a different context' from
    'the same context again'. Values are contract-agnostic card facets."""
    return tuple(sorted({(card.get(k) or '').strip().lower()
                         for k in ('population', 'geography', 'geographic_scope', 'industry', 'technology')
                         if (card.get(k) or '').strip()}))


def _is_null(card: dict) -> bool:
    """A null / inconclusive result -- from the TYPED ACT (registry data), not a sentiment regex."""
    return (card.get('act') or '') == 'null_or_inconclusive_result'


def _has_result(card: dict) -> bool:
    return RC.has_verified_figure(card) or RC.has_direct_result(card)


def recency_binding(contract, vocab: dict) -> tuple[str, str | None]:
    """(claim_kind, boundary_key) -- BOTH FROM DATA. The claim kind is the registry row selected by the
    contract's own genre/design tags; the boundary is the row selected by the contract's own concept
    KEYS. No topic string, no year, and no regex appears in this file: a new domain is a row in
    config/gap_search_vocab.json:recency, never a code edit."""
    reg = (vocab or {}).get('recency', {}) or {}
    tags = genre_tags(contract)
    kind = reg.get('default_claim_kind', 'thin_evidence_current')
    for gk, ck in (reg.get('by_genre', {}) or {}).items():
        if str(gk).lower() in tags:
            kind = ck
            break
    boundary = None
    bbc = reg.get('boundary_by_concept', {}) or {}
    for c in (getattr(contract, 'core_concepts', None) or []):
        key = getattr(c, 'key', None) if not isinstance(c, dict) else c.get('key')
        if key and key in bbc:
            boundary = bbc[key]
            break
    # A claim kind with boundary_required=true is a HARD ERROR without a boundary (recency._policy_for
    # raises -- correctly: "add a policy ROW, do not special-case it in code"). So the genre rows name
    # only boundary-FREE kinds, and we upgrade to the boundary-requiring kind ONLY once a boundary has
    # actually resolved. A generic review keeps a relative frontier window instead of losing the lane.
    upgrade = reg.get('claim_kind_when_boundary')
    if boundary and upgrade and kind not in ('foundational_theory', 'landmark_method',
                                             'long_run_evidence'):
        kind = upgrade          # never upgrade a FOUNDATION claim into a frontier one: age is no defect
    return kind, boundary


def recency_need(contract, vocab: dict, cell=None, as_of: dt.date | None = None) -> RCY.RecencyNeed:
    """The contract (+ optionally ONE cell) -> the RecencyNeed scripts/recency.py plans against."""
    kind, boundary = recency_binding(contract, vocab)
    terms = _flatten_aliases(contract.core_concepts, 3)
    if cell is not None:
        terms = (_flatten_aliases([r for r in contract.subject_axis.values if r.key == cell.row])
                 + _flatten_aliases([c for c in contract.outcome_dimensions if c.key == cell.col])
                 + terms[:2])
    return RCY.RecencyNeed(claim_kind=kind, subject_terms=[t for t in terms if t][:8],
                           as_of=as_of or dt.date.today(), boundary=boundary,
                           unit=f'{cell.row}|{cell.col}' if cell is not None else '')


def frontier_year(contract, override: int | None = None, vocab: dict | None = None,
                  as_of: dt.date | None = None) -> int | None:
    """The recency FRONTIER: the year our NEWEST evidence must reach.

    THE BUG THIS REPLACES. This used to `return contract.source_policy.recency_from` -- but that is the
    FLOOR ("only cite work published from 2015 onward"), NOT the frontier. So `stale = newest < frontier`
    asked "is 2022 < 2015?", which is FALSE FOR EVERY CELL: RECENCY_GAP was structurally unable to fire
    and the entire 2023-2025 generative-AI turn was invisible to the acquisition planner. Backward
    citation expansion cannot reach that window (the edges do not exist yet) -- it must be searched BY
    DATE, which is exactly what scripts/recency.py builds.

    The frontier now comes from the RECENCY PROFILE (data): the named boundary's start year, else
    as_of - default_frontier_months. A FOUNDATION-ONLY claim kind (a theorem, a landmark method, a long
    panel) has NO frontier lane -> returns None -> that cell is NEVER stale and NEVER a RECENCY_GAP,
    because age is not a defect there. That is the generality guarantee, and it is data, not a branch."""
    if override is not None:
        return override
    vocab = vocab if vocab is not None else load_vocab()
    try:
        profile = RCY.load_profile()
    except RCY.RecencyProfileError:
        return None                        # no profile on disk -> no frontier claim. Never invent one.
    # NOTE: everything below is allowed to RAISE. A claim kind that requires a boundary and has none is
    # a DATA inconsistency in the registry, and recency.py is right to be loud about it. Swallowing it
    # here (an earlier draft of this function did) silently disabled the whole frontier lane for
    # clinical questions and reintroduced the exact bug this wiring exists to kill: a stale corpus that
    # never reports itself as stale. A misconfigured row must fail the run, not quietly downgrade it.
    need = recency_need(contract, vocab, as_of=as_of)
    pol = RCY._policy_for(need, profile)
    if 'frontier' not in (pol.get('lanes') or []):
        return None                        # foundation-only: age carries no penalty. Not a gap. Ever.
    sinces = [b.since for b in RCY.resolve_bands(need, profile) if b.since]
    return min(sinces).year if sinces else None


# =============================================================================== the per-cell funnel
@dataclass
class CellFunnel:
    """Everything OBSERVED about one requirement, kept as separate observations (never a scalar).

    It fuses two records the winning architecture already keeps: the COVERAGE MATRIX cell (what we can
    ground and count) and the EVENT LEDGER (whether we ever actually looked, and what the backends did).
    """
    cellkey: str
    row: str
    row_label: str
    col: str
    col_label: str
    status: str                 # the matrix verdict: CLOSED|THIN|GAP|LIMITATION|UNRESOLVED
    n_families: int             # DISTINCT independent evidence units (studies/decisions), not documents
    n_results: int
    designs: list[str]          # distinct study designs present
    contexts: int               # distinct populations/settings present
    n_ambiguous: int            # cards that MIGHT belong here and could not be placed
    n_unbound: int              # cards naming a DOI but no admissible manifestation
    newest_year: int | None
    frontier: int | None
    time_sensitive: bool
    stale: bool                 # newest evidence is behind the frontier
    has_null: bool
    has_nonnull_result: bool
    has_moderator: bool
    # ledger-derived (keyed by the cell requirement `row:col`):
    route_state: str
    budget_stopped: bool
    supports_absence: bool
    coverage_status: str        # UNROUTED|UNSEARCHED|SEARCH_FAILED|SEARCHED_NONE|THIN|SUPPORTED|CONFLICTED
    n_families_run: int         # distinct query families the ledger shows were tried on this cell
    n_adapters_run: int
    saturated: bool
    # source-level funnel (aggregated over the DOIs of the cards routed here):
    src_candidate: bool         # a candidate was identified for at least one source
    src_manifestation: bool     # bytes were fetched for at least one source
    src_admissible: bool        # at least one source produced a bound, groundable card

    @property
    def has_conflict(self) -> bool:
        """A tension the review must address: the ledger reduced the cell to CONFLICTED, OR the cell
        holds BOTH a null and a non-null result among its independent units. Both are act/ledger
        data, not a hand-read of the prose."""
        return self.coverage_status == EL.CONFLICTED or (self.has_null and self.has_nonnull_result)


def _doi_ledger_funnel(ledger: EL.Ledger) -> dict[str, dict]:
    """Per-source acquisition funnel, derived once from the ledger's OBSERVATIONS."""
    out: dict[str, dict] = {}
    for u in ledger.units():
        evs = ledger.events(u)
        kinds = {e.kind for e in evs}
        out[u] = {
            'candidate': EL.EventKind.CANDIDATE_IDENTIFIED in kinds,
            'manifestation': EL.EventKind.MANIFESTATION_FETCHED in kinds,
        }
    return out


def cell_funnel(cell, cards_here: list[dict], doi_funnel: dict[str, dict],
                contract, ledger, vocab: dict, override_frontier: int | None = None) -> CellFunnel:
    fr = frontier_year(contract, override_frontier, vocab)
    years = [y for y in (_card_year(c) for c in cards_here) if y is not None]
    newest = max(years) if years else None
    designs = sorted({d for d in (_card_design(c) for c in cards_here) if d})
    contexts = {_card_context(c) for c in cards_here if _card_context(c)}
    tags = genre_tags(contract)
    mod_vocab = _shape(vocab, 'moderator', tags)

    # per-family polarity -- a null vs a non-null result, counted at the INDEPENDENT-UNIT level so a
    # study restated by ten cards is one voice, not ten.
    fam_null: dict[str, bool] = {}
    fam_res: dict[str, bool] = {}
    for c in cards_here:
        fam, _ = RC.evidence_unit_of(c)
        if not fam:
            continue
        fam_null[fam] = fam_null.get(fam, False) or _is_null(c)
        fam_res[fam] = fam_res.get(fam, False) or (_has_result(c) and not _is_null(c))
    has_null = any(fam_null.values())
    has_nonnull = any(fam_res.values())
    has_mod = any(_contains_any(c.get('span', ''), mod_vocab) for c in cards_here)

    # source-level funnel: fold each routed card's DOI through the ledger.
    src_cand = src_manif = src_adm = False
    for c in cards_here:
        doi = c.get('doi') or ''
        f = doi_funnel.get(doi, {})
        src_cand = src_cand or f.get('candidate', False)
        src_manif = src_manif or f.get('manifestation', False)
        _, bound = RC.evidence_unit_of(c)
        src_adm = src_adm or bound

    # ledger view of the REQUIREMENT itself (keyed row:col). In a pipeline that only fetched by DOI
    # this is UNROUTED -- which is the honest statement that the per-requirement search never ran.
    ck = f'{cell.row}:{cell.col}'
    route = EL.derive_route_status(ledger.events(ck))
    cov, _covinfo = EL.derive_coverage_status(ledger, ck)
    plans = [e for e in ledger.events(ck) if e.kind == EL.EventKind.ROUTE_PLANNED]
    adapters_run = {a for e in plans for a in e.payload.get('adapters', [])}
    sat = vocab.get('saturation', {})
    saturated = (cov == EL.SEARCHED_NONE
                 and len(plans) >= sat.get('min_query_families', 3)
                 and len(adapters_run) >= sat.get('min_adapters', 2))

    return CellFunnel(
        cellkey=ck, row=cell.row, row_label=cell.row_label, col=cell.col, col_label=cell.col_label,
        status=cell.status, n_families=cell.n_works, n_results=cell.n_quant + cell.n_qual,
        designs=designs, contexts=len(contexts), n_ambiguous=len(cell.ambiguous),
        n_unbound=len(cell.unbound), newest_year=newest, frontier=fr,
        time_sensitive=fr is not None, stale=(fr is not None and newest is not None and newest < fr),
        has_null=has_null, has_nonnull_result=has_nonnull, has_moderator=has_mod,
        route_state=route.state, budget_stopped=route.budget_stopped,
        supports_absence=route.supports_absence, coverage_status=cov,
        n_families_run=len(plans), n_adapters_run=len(adapters_run), saturated=saturated,
        src_candidate=src_cand, src_manifestation=src_manif, src_admissible=src_adm)


# =============================================================================== classification
def classify_gap(cell, f: CellFunnel, contract) -> str:
    """Which gap (if any) this requirement is in. Returns the BINDING constraint -- the single next
    action with the most leverage -- while the full CellFunnel is retained so nothing is collapsed."""
    # 0. A budget stop is never a gap. We do not know what is there.
    if f.budget_stopped:
        return BUDGET_STOP

    # 1. The cell already holds enough to close. The only reasons to keep searching are the three that
    #    add MORE INSIGHT than another same-context estimate would (item 5).
    if cell.status == RC.CLOSED:
        if f.has_conflict and not f.has_moderator:
            return CONTRADICTION_GAP
        if f.time_sensitive and f.stale:
            return RECENCY_GAP
        if len(f.designs) >= 2 and f.contexts >= 2:
            return NOT_A_GAP                      # independent, multi-design, multi-context: satisfied
        return DIVERSITY_GAP                      # closed, but a design/context contrast is still open

    # 2. THIN: real evidence that cannot yet settle the comparison. The lever is a contrast, a null, or
    #    current evidence -- never a fifth estimate from the same corner.
    if cell.status == RC.THIN:
        if f.has_conflict and not f.has_moderator:
            return CONTRADICTION_GAP
        if f.time_sensitive and f.stale:
            return RECENCY_GAP
        return DIVERSITY_GAP

    # 3. UNRESOLVED: cards we HOLD but could not ground or place. The fix is not the network.
    if cell.status == RC.UNRESOLVED:
        if f.n_unbound:
            return ACCESS_GAP                     # a DOI with no admissible manifestation -> pursue it
        return EXTRACTION_GAP                     # ambiguous placement -> re-mine held text, sharper facets

    # 4. Empty / LIMITATION cells. Walk the funnel from the bytes outward, then consult the ledger.
    if f.src_manifestation and not f.src_admissible:
        return ACCESS_GAP                         # we fetched bytes but hold nothing admissible
    if f.src_admissible and f.n_results == 0:
        return EXTRACTION_GAP                     # we hold admissible text but extracted no result
    if f.src_candidate and not f.src_manifestation:
        return ACCESS_GAP                         # a candidate address, no copy in hand

    if f.coverage_status == EL.SEARCHED_NONE:
        return EVIDENCE_GAP if f.saturated else DISCOVERY_GAP
    if f.coverage_status in (EL.THIN, EL.CONFLICTED):
        return EVIDENCE_GAP                       # terminal "does not settle this" -- a PASS, not a fail
    # UNROUTED / UNSEARCHED / SEARCH_FAILED, and the no-per-cell-route case: the discovery search for
    # this requirement has not (successfully) run. Generate it. It licenses NO absence.
    return DISCOVERY_GAP


# =============================================================================== query families
@dataclass
class QueryFamily:
    """A PLAN, not a socket. It is handed to acquisition.py's Acquirer.plan_route(cellkey, adapters)
    and the fetchers; this module never opens the network. Each gap yields a DIFFERENT family, so a
    requirement is never answered by another copy of the broad query."""
    gap_type: str
    cellkey: str
    intent: str
    adapters: list[str]
    queries: list[dict] = field(default_factory=list)   # {terms, filters, note}
    targets: list[str] = field(default_factory=list)     # specific works to pursue / re-mine
    filters: dict = field(default_factory=dict)
    stop_rule: str = ''
    absence_licensed: bool = False
    rationale: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


def _base_filters(contract) -> dict:
    sp = contract.source_policy
    f = {'peer_reviewed_only': sp.peer_reviewed_only, 'languages': list(sp.languages),
         'from_year': sp.recency_from, 'quality_bar': sp.quality_bar}
    # 'high-quality' IS NOT A FILTER. It is a BARE LABEL, and no fetcher can act on it. Expand it into
    # the DIMENSIONS the quality model actually scores, so what we mean by it is auditable downstream
    # instead of being a word we assert. (weighting.py owns the definition; this file names none of it.)
    comps = WGT.quality_bar_components(_weight_domain(contract))
    if comps:
        f['quality_bar_components'] = comps
    return f


def _weight_domain(contract) -> str:
    """The weight-profile domain for this contract -- a DATA lookup, never a branch. An unknown domain
    resolves to `general` inside weighting.profile_for (never to clinical or legal)."""
    for t in genre_tags(contract):
        if t and t in WGT.load_registry().get('profiles', {}):
            return t
    return 'general'


def _card_row(card: dict) -> dict:
    """An evidence CARD, viewed as the ROW weighting.py scores.

    WHY THIS ADAPTER EXISTS -- IT IS NOT COSMETIC. weighting.score_topical_relevance reads
    title/abstract/venue. A card has no title and no abstract: its text lives in `claim`, `finding` and
    the verbatim `span`. Without this mapping EVERY card matched 0/8 contract terms, took the 0.15
    relevance floor, and the ranking was therefore decided by `source_authority` alone -- which is
    precisely the "returns ResNet and SMOTE: famous, not relevant" failure weighting.py was built to
    kill, quietly reintroduced through a schema mismatch. We map the card's own text in; we do not
    touch a scorer."""
    r = dict(card)
    r['title'] = card.get('title') or card.get('claim') or card.get('finding') or ''
    r['abstract'] = ' '.join(str(card.get(k) or '') for k in ('span', 'finding', 'claim', 'source')).strip()
    r['design'] = card.get('design') or card.get('study_design') or card.get('method') or ''
    r['year'] = card.get('year') or card.get('publication_year')
    return r


def prioritise_targets(card_ids: list[str], idx: dict[str, dict], contract, cap: int = 20) -> list[str]:
    """WHICH held works we chase / re-mine / citation-expand, IN ORDER.

    THE BUG THIS REPLACES: this was `sorted(set(cell.card_ids))[:20]` -- an ALPHABETICAL SORT ON THE
    CARD ID, then truncated at 20. Which works we pursued was therefore decided by a string, and the
    21st was silently dropped. Raw citation count is no better: it "returns ResNet and SMOTE -- famous,
    not relevant".

    So we rank by weighting.py's FIELD-NORMALIZED VECTOR (relevance, directness, method quality,
    authority, influence, independence, recency, completeness, marginal coverage) and let
    `blended_priority` collapse it ONLY at the moment of comparison -- renormalizing over the dimensions
    we actually KNOW (offline, `influence` is UNKNOWN and is dropped from numerator AND normaliser, so a
    work is never sunk to zero for a number we failed to fetch). A hard-failed gate zeroes the priority.
    No network is opened here; gap_search never fetches."""
    if not card_ids:
        return []
    rows = [_card_row(idx[c]) for c in card_ids if c in idx]
    if not rows:
        return sorted(set(card_ids))[:cap]
    domain = _weight_domain(contract)
    terms = _flatten_aliases(contract.core_concepts, 8)
    probes = [{} for _ in rows]                       # OFFLINE: no influence probe, and we say so
    ctx = WGT.CorpusContext.build(rows, probes)
    scored = []
    for r, probe in zip(rows, probes):
        try:
            vec = WGT.build_vector(r, domain=domain, ctx=ctx, probe=probe, question_terms=terms)
            blend = WGT.blended_priority(vec, domain)
            scored.append((blend.priority, r.get('id'), vec, blend))
        except Exception:
            scored.append((0.0, r.get('id'), None, None))   # never let scoring drop a candidate
    scored.sort(key=lambda s: (-s[0], str(s[1])))     # priority DESC, id only as a stable tie-break
    return [cid for _, cid, _, _ in scored][:cap]


def _q(terms: list[str], note: str, limits: dict, extra: dict | None = None) -> dict:
    cap = limits.get('max_terms_per_query', 8)
    out = {'terms': [t for t in terms if t][:cap], 'note': note}
    if extra:
        out.update(extra)
    return out


def query_family(gap: str, cell, f: CellFunnel, contract, vocab: dict,
                 idx: dict[str, dict] | None = None) -> QueryFamily:
    """The gap -> the query family. EVERY topical term comes from the contract; the evidence-shape
    words come from the registry; the structure is the same for every domain."""
    tags = genre_tags(contract)
    lim = vocab.get('limits', {})
    ad = vocab.get('adapters', {})
    concept = _flatten_aliases(contract.core_concepts, lim.get('max_concept_aliases', 6))
    row_terms = _flatten_aliases([r for r in contract.subject_axis.values if r.key == cell.row])
    col_terms = _flatten_aliases([c for c in contract.outcome_dimensions if c.key == cell.col])
    methods = list(contract.method_designs or [])
    filt = _base_filters(contract)
    idx = idx or {}
    ck = f.cellkey

    if gap == DISCOVERY_GAP:
        qs = [
            _q(row_terms + col_terms + concept[:2], 'axis-value x outcome x concept -- the SPECIFIC '
               'requirement, which the broad query never issued', lim),
            _q(concept[:2] + col_terms, 'outcome-specific, across the whole axis -- the column the broad '
               'query underweights', lim),
        ]
        if methods:
            qs.append(_q(methods[:2] + concept[:1] + col_terms[:2],
                         'method-specific -- name the designs that count as evidence in this field', lim))
        return QueryFamily(
            gap, ck, intent=f'DISCOVER a candidate for [{cell.row_label} x {cell.col_label}]',
            adapters=list(ad.get('discovery', [])), queries=qs[:lim.get('max_queries_per_family', 6)],
            filters=filt, absence_licensed=False,
            stop_rule='route completes on >=min_adapters over >=min_query_families and yields 0 new '
                      'evidence-unit families -> re-classify EVIDENCE_GAP (SEARCHED_NONE), not before',
            rationale='no candidate found: issue the OUTCOME- and METHOD-specific queries the broad '
                      'topic query never did -- discovery licenses NO absence claim')

    if gap == ACCESS_GAP:
        targets = (prioritise_targets(sorted(cell.unbound), idx, contract)
                   or prioritise_targets(list(cell.card_ids), idx, contract))
        return QueryFamily(
            gap, ck, intent=f'ACCESS an admissible complete manifestation for [{cell.col_label}]',
            adapters=list(ad.get('access', [])),
            queries=[_q([], 'pursue the SAME work by DOI/title across OA locations, repositories and '
                        'the publisher landing page -- a version chase, not a topic search', lim)],
            targets=targets[:20], filters=filt, absence_licensed=False,
            stop_rule='all known OA locations + repositories tried and none admissible -> report a '
                      'PIPELINE LIMITATION (403/paywall), which is NOT an evidence gap',
            rationale='a candidate exists but we hold no groundable copy: chase the manifestation, '
                      'never re-run discovery')

    if gap == EXTRACTION_GAP:
        # LOCAL: re-mine held text; the actor is evidence_miner, not a backend.
        probes = [fc.probe for fc in contract.facets
                  if fc.serves in ('', cell.col) or fc.key == cell.col][:6] or \
                 [f'What result does this source report about {cell.col_label}?']
        targets = (prioritise_targets(sorted(cell.ambiguous), idx, contract)
                   or prioritise_targets(list(cell.card_ids), idx, contract))
        return QueryFamily(
            gap, ck, intent=f'RE-EXTRACT a result / disambiguating facet for [{cell.col_label}]',
            adapters=list(ad.get('extraction', [])),           # [] -> no network
            queries=[_q([], 'evidence_miner re-run over HELD manifestations with result- and '
                        'sibling-discriminating facet probes', lim, {'facet_probes': probes})],
            targets=targets[:20], filters={}, absence_licensed=False,
            stop_rule='re-mine yields no result span / no discriminating facet -> the source genuinely '
                      'carries no result on this outcome (an EXTRACTION fact, still not an absence)',
            rationale='text is in hand; the gap is at the miner, so spend extraction, not a query')

    if gap == DIVERSITY_GAP:
        missing = [m for m in methods if m.lower() not in {d.lower() for d in f.designs}]
        siblings = _flatten_aliases([r for r in contract.subject_axis.values if r.key != cell.row], 8)
        # "null OR counter": a statistical null in a trial, an overruling/distinguishing case in law --
        # both come from the shape registry, the legal words via the genre-tagged DATA block.
        seek = _shape(vocab, 'null_result', tags)[:2] + _shape(vocab, 'counterevidence', tags)[:2]
        qs = []
        if missing:
            qs.append(_q(missing[:2] + concept[:1] + col_terms[:2],
                         'a DESIGN not yet present here -- resolve the single-design limitation', lim))
        qs.append(_q(seek + col_terms[:2],
                     'actively seek a NULL / counter-finding -- the first credible null outvalues a '
                     'fifth positive', lim))
        if siblings:
            qs.append(_q(siblings[:3] + col_terms[:2] + concept[:1],
                         'a DIFFERENT population/context on the same outcome', lim))
        return QueryFamily(
            gap, ck, intent=f'DIVERSIFY the evidence for [{cell.row_label} x {cell.col_label}]',
            adapters=list(ad.get('diversity', [])), queries=qs[:lim.get('max_queries_per_family', 6)],
            targets=prioritise_targets(list(cell.card_ids), idx, contract), filters=filt, absence_licensed=False,
            stop_rule='a second design + a null-or-counter + one different context are held -> the cell '
                      'is DIVERSE; else narrate the design limitation explicitly',
            rationale='evidence exists but from one study/design/context: buy a contrast or a null via '
                      'citation-chase and method-specific queries, not another same-corner estimate')

    if gap == RECENCY_GAP:
        # THE FRONTIER LANE IS scripts/recency.py's, NOT A HAND-ROLLED from_year FILTER. It builds
        # OVERLAPPING, EXPLICIT DATE WINDOWS against the databases' real date fields and SORTS BY DATE
        # -- and it REFUSES the citation sort, because a 2025 paper has no citations yet and citation
        # order would bury exactly the work we are trying to find. Removing this call collapses this
        # family back to one undated topic query.
        need = recency_need(contract, vocab, cell)
        plan_ = RCY.plan(need)
        qs: list[dict] = []
        for dq in plan_.frontier_queries:
            if not dq.supported:
                continue                      # the DB does not expose that date-type: say so, never fake it
            qs.append(_q(row_terms + col_terms + concept[:2],
                         f'FRONTIER [{dq.band}] on {dq.database}: {dq.date_type}-date window, '
                         f'sorted by {dq.sort or "the API own date order"} -- NEVER by citations',
                         lim, {'database': dq.database, 'band': dq.band, 'date_type': dq.date_type,
                               'date_field': dq.date_field, 'sort': dq.sort, 'url': dq.url}))
        bands = ' | '.join(f'{b.key}={b.window_prose()}' for b in plan_.frontier_bands)
        return QueryFamily(
            gap, ck, intent=f'REFRESH to the current frontier for [{cell.col_label}]',
            adapters=list(ad.get('recency', [])),
            queries=qs[:lim.get('max_queries_per_family', 6)] or [
                _q(row_terms + col_terms + concept[:2],
                   'no supported frontier window for this claim kind -- a limitation, not a search', lim)],
            filters={**filt, 'from_year': f.frontier, 'frontier_bands': bands,
                     'lanes': list(plan_.lanes), 'claim_kind': need.claim_kind,
                     'boundary': need.boundary},
            targets=[], absence_licensed=False,
            stop_rule=f'every supported frontier band is queried on >=2 databases and the newest '
                      f'admissible unit is STILL < {f.frontier} -> "{plan_.on_empty_template}" -- a '
                      f'SCOPED ABSENCE (a frontier limitation), never a disproof',
            rationale=f'time-sensitive claim ({need.claim_kind}), newest held evidence is '
                      f'{f.newest_year} but the frontier opens at {f.frontier}: backward citation '
                      f'expansion CANNOT reach that window (the citing edges do not exist yet), so '
                      f'search the dates directly. Bands: {bands or "(none)"}')

    if gap == CONTRADICTION_GAP:
        mods = _shape(vocab, 'moderator', tags)
        syn = [m for m in methods if _contains_any(m, _shape(vocab, 'synthesis_designs', tags))] \
              or _shape(vocab, 'synthesis_designs', tags)
        return QueryFamily(
            gap, ck, intent=f'RESOLVE the conflict in [{cell.row_label} x {cell.col_label}]',
            adapters=list(ad.get('contradiction', [])),
            queries=[
                _q([], 'citation-chase the conflicting works (cited-by + references) for the study that '
                   'adjudicates', lim, {'seed_works': sorted(set(cell.card_ids))[:12]}),
                _q(mods[:3] + col_terms[:2],
                   'find the MODERATOR / subgroup that explains the disagreement', lim),
                _q(syn[:2] + concept[:1] + col_terms[:2],
                   'find the synthesis (meta-analysis / systematic review) that reconciles them', lim),
            ][:lim.get('max_queries_per_family', 6)],
            targets=prioritise_targets(list(cell.card_ids), idx, contract), filters=filt, absence_licensed=False,
            stop_rule='a moderator or a reconciling synthesis is held -> a SETTLED contrast; else "the '
                      'literature does not settle this" is the correct, terminal answer',
            rationale='findings conflict and the moderator is missing: chase citations and moderators, '
                      'never bury the conflict under more of one side')

    if gap == EVIDENCE_GAP:
        licensed = f.coverage_status == EL.SEARCHED_NONE
        return QueryFamily(
            gap, ck, intent=f'TERMINAL for [{cell.row_label} x {cell.col_label}] -- routes saturated',
            adapters=[], queries=[], targets=[], filters={}, absence_licensed=licensed,
            stop_rule='no new family: STOP. This is operational saturation, not exhaustive recall.',
            rationale=('SEARCHED_NONE after adequate, saturated routing -> a SCOPED ABSENCE may be '
                       'stated, scoped to this corpus' if licensed else
                       'THIN / CONFLICTED after saturation -> "the literature does not settle this" is '
                       'a CORRECT terminal answer'))

    # NOT_A_GAP / BUDGET_STOP -> no family.
    reason = ('adequately closed: >=2 independent units, a result, a design and a context contrast'
              if gap == NOT_A_GAP else
              'we stopped on BUDGET -- a pipeline limitation, not an evidence gap; we do not know what '
              'is there')
    return QueryFamily(gap, ck, intent=reason, adapters=[], absence_licensed=False,
                       stop_rule='no search', rationale=reason)


# =============================================================================== the engine
@dataclass
class GapResult:
    cell: object
    funnel: CellFunnel
    gap: str
    family: QueryFamily


def analyze(contract, cards: list[dict], ledger: EL.Ledger, vocab: dict | None = None,
            override_frontier: int | None = None, order_by_insight: bool = True) -> list[GapResult]:
    """Build the coverage matrix and classify every cell. THE reusable entry point (insight_value
    imports this).

    THE RETURNED LIST IS AN ACQUISITION SCHEDULE, NOT A MATRIX DUMP. It is ordered by MARGINAL INSIGHT
    (insight_value.schedule), so the cell that would buy a moderator for an open contradiction is
    searched BEFORE a 34th first-estimate-in-an-empty-corner. Pass order_by_insight=False to get raw
    matrix order (the ablation the wiring proof uses)."""
    vocab = vocab or load_vocab()
    matrix = RC.coverage_matrix(contract, cards, corpus=[], ledger=ledger)
    by_cell: dict[tuple[str, str], list[dict]] = {}
    idx = {c.get('id'): c for c in cards}
    for cell in matrix.cells.values():
        by_cell[(cell.row, cell.col)] = [idx[cid] for cid in cell.card_ids if cid in idx]
    doi_funnel = _doi_ledger_funnel(ledger)
    out: list[GapResult] = []
    for key, cell in matrix.cells.items():
        f = cell_funnel(cell, by_cell[key], doi_funnel, contract, ledger, vocab, override_frontier)
        gap = classify_gap(cell, f, contract)
        fam = query_family(gap, cell, f, contract, vocab, idx)
        out.append(GapResult(cell, f, gap, fam))
    if order_by_insight:
        # SELECTION ranks by the marginal-insight VECTOR, never by cell name and never by a scalar.
        # Imported HERE (not at module scope) because insight_value imports this module.
        import insight_value as IV
        out = IV.schedule(out)
    return out


def gap_census(results: list[GapResult]) -> dict[str, int]:
    c = {g: 0 for g in GAP_TYPES + [NOT_A_GAP, BUDGET_STOP]}
    for r in results:
        c[r.gap] = c.get(r.gap, 0) + 1
    return c


# =============================================================================== shared state loader
DEFAULT_CONTRACT = ROOT / 'outputs' / 'contracts' / '0ee18d01143274a5.json'   # task 72, canonical
DEFAULT_CARDS    = ROOT / 'outputs' / 'evidence_cards_bound.json'
DEFAULT_LEDGER   = ROOT / 'outputs' / 'event_ledger.jsonl'


def load_state(contract_path: str | Path = DEFAULT_CONTRACT,
               cards_path: str | Path = DEFAULT_CARDS,
               ledger_path: str | Path = DEFAULT_LEDGER):
    """(contract, cards, ledger). Shared by gap_search and insight_value so neither duplicates the
    other's loading. The contract is a DATA artifact; swapping it swaps the domain."""
    contract = RC.Contract.from_dict(json.loads(Path(contract_path).read_text()))
    cards = json.loads(Path(cards_path).read_text())
    lp = Path(ledger_path)
    ledger = EL.Ledger.load(lp) if lp.exists() else EL.Ledger()
    return contract, cards, ledger


# =============================================================================== generality demo
def demo_generality() -> int:
    """One mechanism, three domains, ZERO code branches. Each contract is a checked-in DATA artifact
    compiled from a question by research_contract; gap_search never learns which domain it is in."""
    vocab = load_vocab()
    cdir = ROOT / 'outputs' / 'contracts'
    trials = [
        ('CLINICAL  (Parkinson\'s, real cached contract)', cdir / '286ca878f3e45d3b.json'),
        ('CLINICAL  (plasma metal ions -> CV events)',     cdir / '850f82fd2d98a9d9.json'),
        ('LEGAL     (ADAS liability allocation)',          cdir / 'b53e70f0ba814545.json'),
    ]
    for tag, path in trials:
        if not path.exists():
            print(f'  (skip {tag}: {path.name} absent)')
            continue
        contract = RC.Contract.from_dict(json.loads(path.read_text()))
        print(f'\n=== {tag} ===')
        print(f'    genre={contract.genre!r}  axis={contract.subject_axis.name!r}  '
              f'designs={contract.method_designs[:4]}')
        # A DISCOVERY family for the first (axis-value x outcome) cell: watch the terms come from THIS
        # contract's own vocabulary -- RCTs for the clinical one, case-law analysis for the legal one.
        rk = contract.subject_axis.values[0].key if contract.subject_axis.values else RC.CROSS.key
        ckcol = contract.outcome_dimensions[0]
        cell = RC.Cell(row=rk, row_label=(contract.subject_axis.values[0].label
                                          if contract.subject_axis.values else 'cross'),
                       col=ckcol.key, col_label=ckcol.label)
        f = _empty_funnel(cell, contract, DISCOVERY_GAP)
        fam = query_family(DISCOVERY_GAP, cell, f, contract, vocab)
        print(f'    DISCOVERY_GAP -> adapters={fam.adapters}')
        for q in fam.queries:
            print(f'        query: {q["terms"]}')
        # A DIVERSITY family: the designs it seeks are THIS field's designs, from data.
        fd = _empty_funnel(cell, contract, DIVERSITY_GAP, designs=[contract.method_designs[0]]
                           if contract.method_designs else [])
        famd = query_family(DIVERSITY_GAP, cell, fd, contract, vocab)
        seek = [q['terms'] for q in famd.queries]
        print(f'    DIVERSITY_GAP -> seeks missing designs / null / different context: {seek[:2]}')

    # THIN-EVIDENCE: the CORRECT answer is "the literature does not settle this", and it is a PASS.
    print('\n=== THIN-EVIDENCE terminal states (ledger-driven, synthetic) ===')
    _demo_thin_terminals(vocab)
    print('\nNo branch on domain ran. The behaviour differed because the DATA differed.')
    return 0


def _empty_funnel(cell, contract, gap, designs=None) -> CellFunnel:
    fr = frontier_year(contract)
    return CellFunnel(
        cellkey=f'{cell.row}:{cell.col}', row=cell.row, row_label=cell.row_label, col=cell.col,
        col_label=cell.col_label, status=RC.THIN if gap == DIVERSITY_GAP else RC.LIMITATION,
        n_families=1 if gap == DIVERSITY_GAP else 0, n_results=1 if gap == DIVERSITY_GAP else 0,
        designs=designs or [], contexts=1, n_ambiguous=0, n_unbound=0, newest_year=None, frontier=fr,
        time_sensitive=fr is not None, stale=False, has_null=False, has_nonnull_result=False,
        has_moderator=False, route_state='UNROUTED', budget_stopped=False, supports_absence=False,
        coverage_status=EL.UNROUTED, n_families_run=0, n_adapters_run=0, saturated=False,
        src_candidate=False, src_manifestation=False, src_admissible=False)


def _demo_thin_terminals(vocab: dict) -> None:
    """Tiny synthetic ledgers, event_ledger's own idiom, showing each terminal is data-driven and that
    for a thin-evidence question the terminal states are CORRECT ANSWERS, not failures."""
    def route(planned, *, answered_none=False, budget=False, throttle=None):
        L = EL.Ledger()
        L.emit('c', EL.EventKind.ROUTE_PLANNED, 'router', adapters=planned)
        for a in planned:
            L.emit('c', EL.EventKind.BACKEND_ATTEMPTED, 'f', adapter=a, request_id=f'{a}#1')
            if a == throttle:
                L.emit('c', EL.EventKind.THROTTLED, 'f', adapter=a, request_id=f'{a}#1', http_status=429)
            else:
                L.emit('c', EL.EventKind.RESPONSE_RECEIVED, 'f', adapter=a, request_id=f'{a}#1',
                       http_status=200, n_results=0 if answered_none else 1)
        if budget:
            L.emit('c', EL.EventKind.BUDGET_STOPPED, 'sched')
        return L

    # 1. every planned adapter genuinely answered and returned nothing -> the ONLY state that licenses
    #    a scoped absence. classify_gap turns this (once saturated) into EVIDENCE_GAP with a licence.
    cov, _ = EL.derive_coverage_status(route(['openalex', 'crossref'], answered_none=True), 'c')
    print(f'    every adapter answered, 0 candidates -> {cov}: a SCOPED ABSENCE is licensed')
    # 2. a budget stop is NEVER a gap: we do not know what is there.
    covb, _ = EL.derive_coverage_status(route(['openalex', 'crossref'], budget=True), 'c')
    print(f'    all answered but we hit the budget   -> {covb}: NOT a gap, NOT an absence (a limitation)')
    # 3. a 429 leaves a hole -> a limitation, not silence.
    covt, _ = EL.derive_coverage_status(route(['openalex', 'crossref'], throttle='openalex'), 'c')
    print(f'    one adapter 429s                     -> {covt}: NOT an absence (a failed request)')
    # 4. THIN / CONFLICTED coverage -> EVIDENCE_GAP whose CORRECT answer is "does not settle this".
    fake = _empty_funnel(RC.Cell(row='r', row_label='niche', col='o', col_label='rare outcome'),
                         _thin_contract(), EVIDENCE_GAP)
    fake.coverage_status = EL.THIN
    fam = query_family(EVIDENCE_GAP, RC.Cell(row='r', row_label='niche', col='o', col_label='rare outcome'),
                       fake, _thin_contract(), vocab)
    print(f'    thin-evidence cell (ledger says THIN)-> EVIDENCE_GAP  absence_licensed={fam.absence_licensed}: '
          f'"the literature does not settle this" is a PASS')


def _thin_contract():
    """A minimal, deliberately sparse contract -- the DATA form of a thin-evidence question."""
    return RC.Contract(question='Is there evidence that a rarely-studied intervention affects a rare '
                       'outcome?', genre='literature review',
                       core_concepts=[RC.Term(key='iv', label='the intervention', aliases=['intervention'])],
                       outcome_dimensions=[RC.Term(key='o', label='rare outcome', aliases=['rare outcome'])],
                       method_designs=['observational', 'case study'])


# =============================================================================== CLI
def _print_result(r: GapResult, verbose: bool) -> None:
    f = r.family
    c = r.cell
    print(f'[{c.row_label} x {c.col_label}]  status={r.cell.status}  ->  {r.gap}')
    fu = r.funnel
    print(f'    funnel: families={fu.n_families} results={fu.n_results} designs={fu.designs} '
          f'contexts={fu.contexts} amb={fu.n_ambiguous} newest={fu.newest_year} '
          f'stale={fu.stale} conflict={fu.has_conflict} cov={fu.coverage_status}')
    if r.gap in (NOT_A_GAP, BUDGET_STOP):
        print(f'    {f.intent}')
        return
    print(f'    query family: adapters={f.adapters}  absence_licensed={f.absence_licensed}')
    for q in f.queries:
        extra = ''
        if q.get('facet_probes'):
            extra = f'  facet_probes={q["facet_probes"][:2]}'
        if q.get('seed_works'):
            extra = f'  seeds={len(q["seed_works"])} works'
        print(f'        - terms={q["terms"]}{extra}\n          ({q["note"]})')
    if f.targets and verbose:
        print(f'    targets: {f.targets[:6]}')
    print(f'    stop: {f.stop_rule}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--contract', default=str(DEFAULT_CONTRACT))
    ap.add_argument('--cards', default=str(DEFAULT_CARDS))
    ap.add_argument('--ledger', default=str(DEFAULT_LEDGER))
    ap.add_argument('--frontier', type=int, default=None, help='override the recency frontier year')
    ap.add_argument('--only', help='print only cells of this gap type')
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--json', action='store_true', help='dump machine-readable results')
    ap.add_argument('--demo-generality', action='store_true',
                    help='clinical / legal / thin-evidence behaviour from data, no code branch')
    a = ap.parse_args()

    if a.demo_generality:
        return demo_generality()

    vocab = load_vocab()
    contract, cards, ledger = load_state(a.contract, a.cards, a.ledger)
    results = analyze(contract, cards, ledger, vocab, a.frontier)

    if a.json:
        print(json.dumps({'census': gap_census(results),
                          'cells': [{'cell': r.funnel.cellkey, 'gap': r.gap,
                                     'family': r.family.to_dict()} for r in results]}, indent=1))
        return 0

    census = gap_census(results)
    print(f'CONTRACT: {contract.review_subject or contract.question[:70]!r}')
    print(f'  axis={contract.subject_axis.name!r}  cells={len(results)}  '
          f'recency_frontier={frontier_year(contract, a.frontier)}')
    print(f'\nGAP CENSUS (this corpus): ' + '  '.join(f'{k}={v}' for k, v in census.items() if v))
    print('=' * 96)
    order = {g: i for i, g in enumerate(GAP_TYPES + [NOT_A_GAP, BUDGET_STOP])}
    shown = [r for r in results if not a.only or r.gap == a.only]
    for r in sorted(shown, key=lambda r: (order.get(r.gap, 99), r.cell.row_label, r.cell.col_label)):
        _print_result(r, a.verbose)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
