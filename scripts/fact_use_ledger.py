#!/usr/bin/env python3
"""fact_use_ledger.py — RHETORICAL REUSE ACCOUNTING.

THE PROBLEM, MEASURED (not asserted):
    28 subsection jobs draw 222 card slots from only 82 distinct cards -- out of 133 we hold.
    One finding is selected EIGHT times. 51 cards are NEVER selected at all. The composer's
    `_select()` is a pure lexical-overlap top-k with NO MEMORY: every subsection re-runs the same
    argmax over the same corpus, so the same handful of cards win every single time. Nothing in the
    system has ever known that a fact was already spent.

    The result is a report that says the same thing repeatedly and, simultaneously, never says
    two-fifths of what it knows.

WHAT THIS IS NOT:
    It is NOT "one card, one section". Sol rejected that and he was right: it would starve the
    theory and synthesis sections, which legitimately need to re-use canonical findings, and it
    contradicts the consolidate-don't-drop architecture. A finding may be used many times.

    THE LEDGER GOVERNS RHETORICAL REUSE -- HOW OFTEN A FACT IS *NARRATED* -- NOT EVIDENCE
    RETENTION. Corroborating sources stay in the basket forever. Consolidation never deletes
    evidence; it only decides whose voice tells it, and how many times.

THE RULES IT ENFORCES:
    R1  NARRATE-ONCE     A finding is narrated IN FULL exactly once, in its primary section.
    R2  NEW-ROLE-OR-NOTHING  A later section may use it ONLY in an analytical role it has not yet
                         played. Same role twice = restatement.
    R3  MUST-ADD         Even a new role must ADD something: a new comparison, a boundary, a method
                         critique, or an implication. A new role that adds nothing is restatement
                         wearing a hat.
    R4  OWNED BACKREF    Otherwise the writer makes an OWNED BACKWARD REFERENCE: it points at the
                         fact without restating it. Under THE LAW an OWNED sentence names no source
                         and carries no new particular -- which is exactly what a backward reference
                         is. The rule does not fight the contract; it falls out of it.
    R5  BASKET IS SACRED Corroborators are never deleted. They stay citable (evidence table,
                         corroboration clause). Rhetorical consolidation != evidentiary deletion.
    R6  DISTINCT BUNDLES Each section is dealt a deliberately DIFFERENT evidence bundle.

ON EVIDENCE, AND WHY IDENTITY IS SPAN-ADDRESSED:
    THE VERBATIM SPAN IS THE ONLY EVIDENCE. `claim` is a display cache -- the model's own words --
    and it is the thing that let a hallucinated figure be "verified" against the hallucination that
    produced it.

    So finding identity is a hash of the SPAN, never of the claim. If identity were keyed on model
    prose, the model could change a finding's identity by rewording it, and the ledger's whole
    memory of what has already been spent would be forgeable by the writer it is supposed to
    police. It is keyed on the paper's own bytes.

    NOTE, PRECISELY: this module VALIDATES NOTHING. It makes no entailment decision, admits no
    sentence, and rejects no sentence. It is an accounting instrument. The gate
    (synthesis_contract.validate + cellcog_composer._gate_*) remains the only validator, and the
    span remains its only evidence. The ledger matches prose to findings only to COUNT, and where a
    match is ambiguous it says so instead of guessing.

GENERAL, NOT TASK-72:
    No topic strings. Section functions are classified with a lexicon of REVIEW MOVES (define,
    theorize, measure, evidence, synthesize, imply) that is universal to evidence reviews on any
    question, and the classifier accepts a compiled research contract to override it.

Usage:
    python scripts/fact_use_ledger.py                 # audit the shipped report + plan the fix
    python scripts/fact_use_ledger.py --audit-only
    python scripts/fact_use_ledger.py --plan-only
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

# Reuse the composer's OWN sentence boundaries and outline. If the ledger split sentences
# differently from the writer and the gate, its "duplicate sentence" counts would be artifacts of
# the splitter, not facts about the report. (Measured: a naive (?<=[.!?])\s+ split cuts at "et al."
# and inflates the duplicate count from 30 to 76. That number would have been a lie.)
from cellcog_composer import OUTLINE, split_sentences_safe, _select  # noqa: E402

CARDS_PATH = ROOT / 'outputs' / 'evidence_cards.json'
REPORT_PATH = ROOT / 'outputs' / 'cellcog_arm' / 'report.md'
LEDGER_PATH = ROOT / 'outputs' / 'fact_use_ledger.json'

# A pointer costs about this many words: "The displacement evidence considered earlier bears
# directly on this question." Used to price what an OWNED backward reference would have cost in
# place of a restatement. Deliberately generous -- it UNDERSTATES the waste.
BACKREF_COST_WORDS = 12

# Two narrations of the same finding count as a restatement at or above this content-word Jaccard,
# computed AFTER the attribution boilerplate is stripped (the attribution is supposed to repeat --
# the waste is repeating the FACT).
SIM_RESTATE = 0.55

# Corroboration threshold: two findings whose spans overlap this much MAY be saying the same thing.
#
# DO NOT TUNE THIS DOWN TO MANUFACTURE CLUSTERS. Measured: max cross-work span Jaccard is 0.231, and
# at a loosened threshold 5 of the 9 near-miss pairs would merge with NOTHING stopping them --
# including Pillai 2020 ("stickiness negatively moderates talent acquisition") with Baakeel 2020
# ("the correlation ... is strong and significant"), which are not the same claim at all.
#
# AND THE GUARDS ARE WEAKER THAN THEY LOOK. I wrote a polarity guard believing it caught this pair:
#
#     Autor 2015    span: "...complementarities between automation and labor that INCREASE
#                          productivity, RAISE earnings, and AUGMENT demand for labor."   -> {UP}
#     Acemoglu 2019 span: "automation always REDUCES the labor share in value added and may REDUCE
#                          labor demand EVEN AS IT RAISES productivity."             -> {UP, DOWN}
#
# It does not. Acemoglu's span is MIXED-polarity -- the paper's own sentence says one thing falls
# while another rises -- so the bags of direction words intersect and `contradicts()` returns False.
# The pair is actually saved by the UNIT-OF-ANALYSIS guard (worker vs economy), not by polarity.
#
# The lesson is structural: direction words BIND TO OBJECTS ("reduces [the labor share]" vs "raises
# [productivity]"), and a bag of words loses the binding. Sound contradiction detection needs
# (direction, quantity) tuples -- the interpretable evidence tuple the diagnosis already asks for
# (effect + unit + population + design + scope + uncertainty). It cannot be done at this layer.
#
# Note also, and this is the whole reason for THE LAW: the model's CLAIM for Acemoglu reads
# "...reduces labor's share and may diminish labor demand" -> polarity {DOWN}. The claim DROPPED the
# "even as it raises productivity" hedge. THE CLAIM IS MORE POLARIZED THAN THE PAPER. Had this
# detector run on `claim` instead of `span` it would have "found" a contradiction that the source
# does not contain, and been more confident for having lost the evidence.
#
# So: corroboration stays gated at 0.50 and correctly clusters ~nothing on this corpus. The basket
# is BUILT and CORRECT; the DETECTOR is the missing piece and it is not lexical. Zero is the honest
# answer. A tuned threshold would have been a cluster count that deletes evidence.
SIM_CORROBORATE = 0.50

# Direction words. Two findings that overlap lexically but point OPPOSITE WAYS are a CONTRAST -- the
# most valuable thing in a review -- not a corroboration. NECESSARY BUT NOT SUFFICIENT: this fires
# only on spans whose direction is UNMIXED (see above). It is a backstop, never a licence.
POLARITY: dict[str, str] = {}
for _up, _dn in [('increase', 'decrease'), ('increases', 'decreases'), ('increasing', 'decreasing'),
                 ('raise', 'reduce'), ('raises', 'reduces'), ('raising', 'reducing'),
                 ('rise', 'fall'), ('rises', 'falls'), ('rising', 'falling'),
                 ('higher', 'lower'), ('more', 'less'), ('grow', 'shrink'), ('growth', 'decline'),
                 ('gain', 'loss'), ('gains', 'losses'), ('positive', 'negative'),
                 ('complement', 'substitute'), ('complements', 'substitutes'),
                 ('complementary', 'substituting'), ('complementarities', 'substitution'),
                 ('enhance', 'diminish'), ('enhances', 'diminishes'),
                 ('expand', 'contract'), ('expansion', 'contraction'),
                 ('creates', 'destroys'), ('creation', 'destruction'),
                 ('reinstate', 'displace'), ('reinstates', 'displaces'),
                 ('reinstatement', 'displacement'), ('augment', 'replace'),
                 ('augments', 'replaces'), ('support', 'undermine')]:
    POLARITY[_up], POLARITY[_dn] = 'UP', 'DOWN'


def polarity(span: str) -> set[str]:
    """The direction(s) a span asserts. {'UP'}, {'DOWN'}, both, or neither."""
    return {POLARITY[w] for w in _content(span) if w in POLARITY} if span else set()


def contradicts(a: str, b: str) -> bool:
    """True when two spans assert UNMIXED OPPOSITE directions. A CONTRAST, never a merge.

    HONEST LIMIT: returns False on mixed-polarity spans ("reduces the labor share ... even as it
    raises productivity" -> {UP, DOWN}), which are common precisely in the literatures where the
    disagreement matters. It cannot bind a direction to the quantity it modifies. Treat a False as
    "not proven to disagree", NEVER as "agrees".
    """
    pa, pb = polarity(a), polarity(b)
    return bool(pa and pb and not (pa & pb))


# ===================================================================== identity
def _norm_text(s: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower())).strip()


def work_id(card: dict) -> str:
    """Stable id for the SOURCE. DOI when we have one; otherwise a slug of the bibliographic facts.

    Never the array index. Never the filename.
    """
    doi = (card.get('doi') or '').strip().lower()
    if doi:
        return 'W:' + re.sub(r'[^a-z0-9]+', '-', doi).strip('-')
    who = (card.get('authors') or ['anon'])[0]
    stem = f"{who}|{card.get('year')}|{card.get('venue')}"
    return 'W:x' + hashlib.sha1(_norm_text(stem).encode()).hexdigest()[:10]


def finding_id(card: dict) -> str:
    """Stable id for the FINDING, addressed by the VERBATIM SPAN.

    Why not the card's own `id`? It is `{doi}_{ordinal}` -- POSITIONAL. Drop one card upstream, or
    let the extractor return them in a different order, and every id after it silently shifts. A
    ledger keyed on that would mis-attribute its own history and never know.

    Why not the `claim`? Because the claim is written by the model. Identity keyed on model prose is
    identity the model can change by rewording -- the writer could launder a spent fact into a fresh
    one just by paraphrasing it. Keyed on the paper's bytes, it cannot.

    Why (WORK, SPAN) and not the span alone? Because two different papers can assert the same
    sentence, and that is CORROBORATION -- the most valuable thing evidence can do. Hashing the span
    alone collapses them into one finding and silently destroys the second paper's provenance: the
    basket would lose a source without anyone deleting anything. A finding is a claim MADE BY A
    WORK. (The span-only version passed on the live corpus -- 133 spans, 133 ids, no collision --
    and would have quietly eaten a corroborating source the first time two papers agreed verbatim.
    The self-test found it; the corpus never would have.)
    """
    return f'F:{work_id(card)[2:12]}:{hashlib.sha1(_norm_text(card.get("span")).encode()).hexdigest()[:10]}'


# ===================================================================== roles
class Role(str, Enum):
    """What a finding is DOING in a passage. General to any evidence review."""
    DEFINE = 'DEFINE'                    # fixes the meaning of a construct
    ESTABLISH = 'ESTABLISH'              # primary support for the section's claim
    MECHANISM = 'MECHANISM'              # explains WHY the effect occurs
    MAGNITUDE = 'MAGNITUDE'              # the size of the effect is the point
    CONTRAST = 'CONTRAST'                # set AGAINST another finding
    BOUNDARY = 'BOUNDARY'                # limits scope / states what is not shown
    METHOD_CRITIQUE = 'METHOD_CRITIQUE'  # the study's design is what is at issue
    IMPLICATION = 'IMPLICATION'          # a consequence is drawn from it
    CORROBORATE = 'CORROBORATE'          # backs an already-narrated finding (basket, not narration)


class Function(str, Enum):
    """What a SECTION is doing. A lexicon of review moves -- not of any subject matter."""
    SCOPE = 'scope'
    THEORY = 'theory'
    MEASUREMENT = 'measurement'
    EVIDENCE = 'evidence'
    DOMAIN = 'domain'
    SYNTHESIS = 'synthesis'
    IMPLICATION = 'implication'


# Review moves, not topics. "framework", "measure", "establishes", "implication" are words about
# ARGUMENT, and they mean the same thing in a review of oncology trials or monetary policy.
FUNCTION_LEXICON: list[tuple[str, Function]] = [
    (r'\b(scope|method|source|selection|criteri|what counts|definition|defining|draws only)\b', Function.SCOPE),
    (r'\b(theor|framework|model|hypothes|conceptual|mechanism|explanat)\b', Function.THEORY),
    (r'\b(measur|exposure|index|indicator|operationali|estimat|data|adoption)\b', Function.MEASUREMENT),
    (r'\b(synthes|establishes|establish|disagree|contested|unresolved|cannot|critical)\b', Function.SYNTHESIS),
    (r'\b(implication|agenda|gap|future|recommend|polic)\b', Function.IMPLICATION),
    (r'\b(sector|industr|across|domain|profession|setting|application)\b', Function.DOMAIN),
    (r'\b(evidence|effect|impact|outcome|result|finding)\b', Function.EVIDENCE),
]

# NARRATION-ONLY roles: these roles ARE the telling of the fact. To "reuse" a finding as ESTABLISH
# is to assert it again as primary support; to reuse it as MAGNITUDE is to print its number again;
# to reuse it as DEFINE is to restate it as a definition. None of these is a new analytical job --
# they are restatement wearing a hat, which is the exact thing R3 exists to stop.
#
# (The first version of this planner granted 49 of its 84 reuses in these three roles. The rule was
# in the docstring and the code did the opposite. That is how the report got this way in the first
# place: a plausible-sounding licence, never checked against what it actually emitted.)
NARRATION_ONLY_ROLES = frozenset({Role.ESTABLISH, Role.MAGNITUDE, Role.DEFINE})

# REUSABLE roles: the fact is PUT TO WORK rather than told. Each is a genuinely different job --
# it explains, it cuts against something, it bounds a claim, it impugns a design, it implies.
REUSABLE_ROLES = frozenset({Role.MECHANISM, Role.CONTRAST, Role.BOUNDARY,
                            Role.METHOD_CRITIQUE, Role.IMPLICATION})

# A finding may be used beyond its one full narration AT MOST this many times in the whole document.
# Without a global budget the canonical findings get re-granted to every section that scores them
# highly -- which is precisely how one card came to be drawn 8 times.
REUSE_BUDGET = 2
MAX_BACKREF_PER_SUBSECTION = 2      # more than this and the section reads like a table of contents

# Which roles a section of a given function may LICENSE. This is what makes reuse legitimate:
# a canonical finding may appear in THEORY as a MECHANISM and again in SYNTHESIS as a CONTRAST,
# because those are different jobs. It may not appear twice as ESTABLISH.
FUNCTION_ROLES: dict[Function, tuple[Role, ...]] = {
    Function.SCOPE:       (Role.DEFINE, Role.BOUNDARY),
    Function.THEORY:      (Role.MECHANISM, Role.CONTRAST, Role.BOUNDARY),
    Function.MEASUREMENT: (Role.METHOD_CRITIQUE, Role.DEFINE, Role.BOUNDARY),
    Function.EVIDENCE:    (Role.ESTABLISH, Role.MAGNITUDE, Role.CONTRAST),
    Function.DOMAIN:      (Role.ESTABLISH, Role.MAGNITUDE, Role.BOUNDARY),
    Function.SYNTHESIS:   (Role.CONTRAST, Role.BOUNDARY, Role.METHOD_CRITIQUE),
    Function.IMPLICATION: (Role.IMPLICATION, Role.BOUNDARY),
}


def classify_section(title: str, contract: dict | None = None) -> Function:
    """Section title -> review move. `contract` (compiled from the question) overrides the lexicon."""
    if contract:
        for pat, fn in (contract.get('section_functions') or {}).items():
            if re.search(pat, title, re.I):
                return Function(fn)
    for pat, fn in FUNCTION_LEXICON:
        if re.search(pat, title, re.I):
            return fn
    return Function.EVIDENCE


def natural_role(card: dict) -> Role:
    """The role a finding is BEST at, from its declared fields -- never from the model's prose."""
    if card.get('mechanisms'):
        return Role.MECHANISM
    if (card.get('method') or '').lower() in ('theoretical', 'model', 'simulation'):
        return Role.MECHANISM
    if card.get('has_number'):
        return Role.MAGNITUDE
    return Role.ESTABLISH


# ===================================================================== the basket
@dataclass
class Cluster:
    """A claim cluster. ONE narrated representative; every corroborator RETAINED.

    This is the consolidate-don't-drop architecture in one object: `corroborators` is evidence we
    keep, cite, and count -- it is simply not re-narrated in prose.
    """
    cluster_id: str
    representative: str                      # finding_id that gets the full narration
    corroborators: list[str] = field(default_factory=list)
    works: set[str] = field(default_factory=set)

    @property
    def n_sources(self) -> int:
        return len(self.works)


def _content(s: str) -> set[str]:
    stop = {'the', 'and', 'that', 'this', 'with', 'from', 'for', 'are', 'is', 'was', 'were', 'not',
            'but', 'their', 'they', 'which', 'while', 'than', 'more', 'have', 'has', 'been', 'its',
            'these', 'those', 'other', 'such', 'also', 'both', 'only', 'can', 'may', 'through'}
    return {w for w in re.findall(r'[a-z]{3,}', _norm_text(s)) if w not in stop}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def corroboration_blocks(a: dict, b: dict, ignore_lexical: bool = False) -> list[str]:
    """EVERY condition that fails, not just the first.

    Returns ALL blocking reasons so a caller can ask the counterfactual question that matters:
    "if I loosened the lexical threshold, what would still stop this merge?" A short-circuiting
    check cannot answer that -- it would report 'lexical' for every pair and the polarity guard
    would never get to speak, which would hide exactly the contradiction we are trying to see.

    1. LEXICAL   the spans overlap enough to plausibly be the same statement
    2. UNIT      same unit of analysis (a task-level and an economy-level result are not the same
                 finding however alike they read -- that conflation IS the exposure/adoption/outcome
                 error the review exists to avoid)
    3. POLARITY  they point the SAME WAY. Opposite directions = CONTRAST. Never merge a contrast.
    """
    out = []
    if not ignore_lexical and jaccard(_content(a.get('span')), _content(b.get('span'))) < SIM_CORROBORATE:
        out.append('lexical')
    if (a.get('level') or '') != (b.get('level') or ''):
        out.append('unit-of-analysis')
    if contradicts(a.get('span'), b.get('span')):
        out.append('POLARITY(they DISAGREE -- merging would delete the disagreement)')
    return out


def may_corroborate(a: dict, b: dict) -> tuple[bool, str]:
    blocks = corroboration_blocks(a, b)
    return (not blocks), (blocks[0] if blocks else 'corroborates')


def build_clusters(cards: list[dict]) -> dict[str, Cluster]:
    """Group findings that ASSERT THE SAME THING. Nothing is discarded -- only demoted to corroborator.

    Two findings cluster when their SPANS agree (the papers' own words), never when their claims do.
    A corroborator is RETAINED, cited, and counted. It is simply not narrated a second time.
    """
    fids = [finding_id(c) for c in cards]
    by_fid = {f: c for f, c in zip(fids, cards)}

    clusters: dict[str, Cluster] = {}
    assigned: dict[str, str] = {}
    # Findings with a number lead their cluster: a quantified statement is the better narration.
    order = sorted(by_fid, key=lambda f: (not by_fid[f].get('has_number'),
                                          -len(_content(by_fid[f].get('span')))))
    for f in order:
        if f in assigned:
            continue
        cid = f'C:{f[2:]}'
        cl = Cluster(cluster_id=cid, representative=f, works={work_id(by_fid[f])})
        assigned[f] = cid
        for g in order:
            if g in assigned or g == f:
                continue
            ok, _ = may_corroborate(by_fid[f], by_fid[g])
            if ok:
                cl.corroborators.append(g)          # RETAINED. Never deleted.
                cl.works.add(work_id(by_fid[g]))
                assigned[g] = cid
        clusters[cid] = cl
    return clusters


def corroboration_diagnostic(cards: list[dict]) -> dict:
    """WHY the cluster count is what it is. A cluster count of ~0 is a finding, not a bug to tune away."""
    import itertools
    best, blocked = [], collections.Counter()
    for x, y in itertools.combinations(cards, 2):
        if work_id(x) == work_id(y):
            continue
        j = jaccard(_content(x.get('span')), _content(y.get('span')))
        best.append((j, x, y))
        if j >= 0.15:
            # THE COUNTERFACTUAL: pretend the lexical gate were loosened enough to admit this pair.
            # What would STILL block the merge? That is the question the guard has to answer.
            for why in (corroboration_blocks(x, y, ignore_lexical=True) or ['NOTHING -- would merge']):
                blocked[why] += 1
    best.sort(key=lambda x: -x[0])
    return {'max_j': best[0][0] if best else 0.0, 'top': best[:3], 'blocked': blocked,
            'n_pairs': len(best)}


# ===================================================================== the ledger
@dataclass
class Use:
    section: str
    subsection: str
    role: Role
    mode: str                                # NARRATE | NEW_ROLE | BACKREF | CORROBORATE
    adds: set[str] = field(default_factory=set)
    sentence: str = ''
    words: int = 0
    verdict: str = ''                        # audit outcome: OK | RESTATEMENT | RESTATED_BUT_ADDS


@dataclass
class FindingRecord:
    finding_id: str
    work_id: str
    span: str
    label: str                               # display only -- the model's `claim`. NEVER evidence.
    cluster_id: str
    primary_section: str = ''
    primary_role: Role | None = None
    uses: list[Use] = field(default_factory=list)

    @property
    def narrations(self) -> list[Use]:
        return [u for u in self.uses if u.mode == 'NARRATE']

    def over_narrated(self) -> bool:
        return len(self.narrations) > 1

    def violations(self) -> list[str]:
        """R1/R2/R3, checked."""
        out: list[str] = []
        if len(self.narrations) > 1:
            out.append(f'R1 NARRATE-ONCE: narrated {len(self.narrations)}x')
        seen: set[Role] = set()
        for u in self.uses:
            if u.mode in ('BACKREF', 'CORROBORATE'):
                continue
            if u.role in seen:
                out.append(f'R2 NEW-ROLE: role {u.role.value} reused in "{u.subsection[:40]}"')
            seen.add(u.role)
            if u.mode == 'NEW_ROLE' and not u.adds:
                out.append(f'R3 MUST-ADD: reuse in "{u.subsection[:40]}" adds nothing')
        return out


# ===================================================================== the planner
@dataclass
class Bundle:
    section: str
    subsection: str
    function: Function
    narrate: list[str] = field(default_factory=list)
    new_role: list[tuple[str, Role, str]] = field(default_factory=list)   # fid, role, must_add
    backref: list[str] = field(default_factory=list)
    corroborate: list[str] = field(default_factory=list)

    def all_fids(self) -> set[str]:
        return set(self.narrate) | {f for f, _, _ in self.new_role} | set(self.backref)


def relevance(card: dict, subsection: str) -> int:
    """Lexical fit of a finding to a subsection.

    Scored on the SPAN plus the declared fields -- the paper's words, not the model's. (The
    composer's `_select` scores on `claim`, which means today's selection is driven by the model's
    paraphrase of the paper rather than the paper.)
    """
    want = _content(subsection)
    blob = f"{card.get('span')} {card.get('level')} {card.get('method')} {' '.join(card.get('mechanisms') or [])}"
    return len(want & _content(blob))


def plan_bundles(cards: list[dict], outline=OUTLINE, contract: dict | None = None,
                 max_narrate: int = 6) -> tuple[list[Bundle], dict[str, FindingRecord]]:
    """Deal every subsection a DELIBERATELY DIFFERENT evidence bundle.

    Narration is a PARTITION: each finding is narrated in exactly one subsection (R1), so no two
    subsections narrate the same fact. Reuse is then granted -- but only as a NEW ROLE that must ADD
    something (R2/R3), and everything else degrades to an OWNED BACKWARD REFERENCE (R4).
    """
    clusters = build_clusters(cards)
    fid_to_cluster = {}
    for cl in clusters.values():
        fid_to_cluster[cl.representative] = cl.cluster_id
        for g in cl.corroborators:
            fid_to_cluster[g] = cl.cluster_id
    reps = {cl.representative for cl in clusters.values()}

    by_fid = {finding_id(c): c for c in cards}
    ledger = {
        f: FindingRecord(finding_id=f, work_id=work_id(c), span=c.get('span', ''),
                         label=c.get('claim', ''), cluster_id=fid_to_cluster[f])
        for f, c in by_fid.items()
    }

    jobs = [(sec, sub) for sec, subs in outline for sub in subs]
    bundles = [Bundle(section=sec, subsection=sub, function=classify_section(f'{sec} {sub}', contract))
               for sec, sub in jobs]

    # ---- pass 1: PRIMARY ASSIGNMENT. Every representative finding is narrated exactly once, in the
    # subsection that fits it best AND that licenses the role it is naturally best at.
    scored = []
    for f in reps:
        c = by_fid[f]
        nrole = natural_role(c)
        for b in bundles:
            fit = relevance(c, f'{b.section} {b.subsection}')
            if nrole in FUNCTION_ROLES[b.function]:
                fit += 2                      # the section can actually USE what this finding is for
            scored.append((fit, f, b))
    scored.sort(key=lambda x: -x[0])

    placed: set[str] = set()
    cap = collections.Counter()
    for fit, f, b in scored:
        if f in placed or cap[b.subsection] >= max_narrate or fit <= 0:
            continue
        b.narrate.append(f)
        placed.add(f)
        cap[b.subsection] += 1
        rec = ledger[f]
        rec.primary_section, rec.primary_role = b.subsection, natural_role(by_fid[f])
        rec.uses.append(Use(b.section, b.subsection, rec.primary_role, 'NARRATE'))
    # overflow: findings that fit nowhere with capacity still get a home (nothing is dropped)
    for f in reps - placed:
        b = min(bundles, key=lambda x: cap[x.subsection])
        b.narrate.append(f)
        cap[b.subsection] += 1
        rec = ledger[f]
        rec.primary_section, rec.primary_role = b.subsection, natural_role(by_fid[f])
        rec.uses.append(Use(b.section, b.subsection, rec.primary_role, 'NARRATE'))

    # ---- pass 2: LEGITIMATE REUSE. Theory and synthesis sections need the canonical findings. They
    # get them -- but ONLY in a REUSABLE role (never a narration role), only if the finding has not
    # already played that role, only if the use ADDS something, and only within a GLOBAL budget.
    MUST_ADD = {Role.CONTRAST: 'comparison', Role.BOUNDARY: 'boundary',
                Role.METHOD_CRITIQUE: 'method', Role.IMPLICATION: 'implication',
                Role.MECHANISM: 'mechanism'}
    reuse_count: collections.Counter = collections.Counter()

    for b in bundles:
        # Rank candidates by fit, but PENALISE findings already spent elsewhere. This is what drives
        # sibling sections apart: without it, "What the evidence establishes" and "What the evidence
        # cannot yet resolve" score every finding identically and are dealt the SAME bundle (measured
        # Jaccard 0.750). The tie-break on prior reuse is the only thing that makes them diverge.
        want = sorted(((relevance(by_fid[f], f'{b.section} {b.subsection}'), -reuse_count[f], f)
                       for f in reps if f not in b.narrate),
                      key=lambda t: (-t[0], -t[1]))
        for score, _, f in want:
            if score <= 0 or (len(b.new_role) >= 3 and len(b.backref) >= MAX_BACKREF_PER_SUBSECTION):
                continue
            if reuse_count[f] >= REUSE_BUDGET:
                continue                      # this fact is spent. Some other section may not have it.
            rec = ledger[f]
            played = {u.role for u in rec.uses if u.mode in ('NARRATE', 'NEW_ROLE')}
            free = [r for r in FUNCTION_ROLES[b.function]
                    if r in REUSABLE_ROLES and r not in played]
            if free and len(b.new_role) < 3:
                role = free[0]
                b.new_role.append((f, role, MUST_ADD[role]))
                rec.uses.append(Use(b.section, b.subsection, role, 'NEW_ROLE',
                                    adds={MUST_ADD[role]}))
                reuse_count[f] += 1
            elif len(b.backref) < MAX_BACKREF_PER_SUBSECTION:
                # R4: the fact is spent, or this section has no new job for it. Point at it; do not
                # say it again. An OWNED backward reference names no source and carries no new
                # particular -- it is a legal OWNED sentence under THE LAW, by construction.
                b.backref.append(f)
                rec.uses.append(Use(b.section, b.subsection, Role.ESTABLISH, 'BACKREF'))
                reuse_count[f] += 1

    # ---- pass 3: THE BASKET. Corroborators ride along with their representative. Retained, cited,
    # never re-narrated.
    for b in bundles:
        for f in b.narrate:
            for g in clusters[fid_to_cluster[f]].corroborators:
                b.corroborate.append(g)
                ledger[g].uses.append(Use(b.section, b.subsection, Role.CORROBORATE, 'CORROBORATE'))

    return bundles, ledger


# ===================================================================== the auditor
ANAPHORA = re.compile(r'^\s*(they|these authors|the same (study|authors|paper)|the authors|he|she)\b', re.I)
REPORTING = re.compile(
    r'\b(show(s|ed)? that|report(s|ed)? that|note(s|d)? that|find(s)? that|found that|'
    r'establish(es)? that|argue(s)? that|demonstrate(s)? that|examine(s)?)\b', re.I)

ADDS_MARKERS: dict[str, re.Pattern] = {
    'comparison':  re.compile(r'\b(whereas|by contrast|in contrast|unlike|differ(s|ing)?|diverge|'
                              r'jointly|together|relative to|compared (with|to)|both .* and|'
                              r'contrasts?|mirrors?|aligns? with)\b', re.I),
    'boundary':    re.compile(r'\b(only if|only when|limited to|cannot|does not establish|'
                              r'is not established|conditional on|restricted to|does not distinguish|'
                              r'remains? unresolved|no evidence|insufficient|not sufficient|'
                              r'bounded by|does not preclude|fails? to)\b', re.I),
    'method':      re.compile(r'\b(observational|experimental|randomi[sz]ed|quasi-experiment|'
                              r'difference-in-difference|sample of|cross-section|panel|'
                              r'theoretical|simulation|survey of|controlled setting)\b', re.I),
    'implication': re.compile(r'\b(therefore|thus|hence|implies|it follows|consequently|'
                              r'suggests? that|means that|the upshot|as a result)\b', re.I),
}


@dataclass
class Narration:
    finding_id: str
    section: str
    subsection: str
    sentence: str
    words: int
    residue: set[str]                # the sentence MINUS its attribution -- i.e. the FACT it states
    adds: set[str]
    order: int                       # SENTENCE index. Two Narrations sharing an `order` are the SAME
    #                                  sentence telling two findings -- dedupe on this before summing
    #                                  words, or a compound sentence is billed once per fact it tells.
    anaphoric: bool = False
    multi: bool = False              # this sentence narrates >1 finding
    verdict: str = ''                # '' | OK | RESTATEMENT | RESTATED_BUT_ADDS. Declared, not
    #                                  monkey-patched: the first narration of every finding never
    #                                  gets one assigned, and any consumer reading it would explode.


def _strip_attribution(sent: str, card: dict) -> str:
    """Remove the attribution furniture, leaving the FACT.

    The attribution is *supposed* to repeat -- every attributed sentence must name its source. The
    waste is repeating the FACT. So we compare residues, not sentences.
    """
    s = sent
    attr = (card.get('attribution') or '').strip()
    if attr:
        s = re.sub(re.escape(attr), ' ', s, flags=re.I)
    # ...and the reordered variant the writer emits: "Bresnahan et al., writing in the QJE in 2002,"
    s = re.sub(r'\b[A-Z][\wÀ-ɏ\'-]+(?:\s+(?:and|et al\.?)\s*[\wÀ-ɏ\'-]*)?,?\s*'
               r'writing in the [^,]{3,60}?in \d{4},?', ' ', s, flags=re.I)
    s = re.sub(r'\bwriting in the [^,]{3,60}?in \d{4},?', ' ', s, flags=re.I)
    s = REPORTING.sub(' ', s)
    s = re.sub(r'\*\*\[[^\]]+\]\*\*', ' ', s)          # epistemic labels
    return s


def _parse_sections(md: str) -> list[tuple[str, str, str]]:
    """-> [(section, subsection, paragraph)] for PROSE only (no headings, no table rows)."""
    out, sec, sub = [], '', ''
    for block in md.split('\n\n'):
        b = block.strip()
        if not b:
            continue
        if b.startswith('## '):
            sec, sub = b[3:].strip(), ''
            continue
        if b.startswith('### '):
            sub = b[4:].strip()
            continue
        if b.startswith('#') or b.lstrip().startswith('|'):
            continue                                    # title, or the evidence table
        out.append((sec, sub, b))
    return out


def audit_report(report_md: str, cards: list[dict]) -> dict:
    """THE TRUTH PASS. Which findings are over-narrated, the exact repeated sentences, the waste.

    Attribution -> which WORK. Then, within that work, span-overlap -> which FINDING. If two
    findings of the same work tie, we fall back to the claim as a tiebreak AND SAY SO -- an
    unflagged fallback to model prose is how the last loop closed on itself.
    """
    by_fid = {finding_id(c): c for c in cards}
    surnames: dict[str, list[str]] = collections.defaultdict(list)   # surname -> [finding_id]
    for f, c in by_fid.items():
        for a in (c.get('authors') or []):
            surnames[a.lower()].append(f)

    narrations: list[Narration] = []
    unresolved = 0
    owned = 0
    order = 0

    for sec, sub, para in _parse_sections(report_md):
        last_work: str | None = None
        for sent in split_sentences_safe(para):
            if len(sent.split()) < 6:
                continue
            order += 1
            low = sent.lower()
            hits = {f for sn, fs in surnames.items() if re.search(rf'\b{re.escape(sn)}\b', low) for f in fs}
            anaphoric = False
            if not hits and ANAPHORA.match(sent) and last_work:
                hits = {f for f in by_fid if work_id(by_fid[f]) == last_work}
                anaphoric = True
            if not hits:
                owned += 1                                # OWNED voice: legal, and not a narration
                continue

            # WHICH finding(s) is this sentence telling? Score every candidate against its SPAN.
            #
            # MULTI-LABEL, because sentences are. Measured, in "Why large task gains coexist":
            #
            #   "Autor ... reports that automation creates strong COMPLEMENTARITIES ... , YET
            #    technological changes ... have POLARIZED the labor market ..."
            #
            # -- one 57-word sentence narrating TWO distinct Autor findings, both already spent.
            # Charging it to the argmax alone (0.286 vs 0.242 -- nearly a coin-flip) books one
            # restatement and misses the other. So a sentence is credited to EVERY finding it
            # substantially tells, and the WASTE is then deduped by sentence so no word is billed
            # twice. This mirrors the composer's own _gate_multi, which gates each clause against
            # the source it names rather than blaming the whole sentence on the first author it
            # recognises.
            #
            # This also retires the claim-tiebreak that used to sit here. `claim` now touches NO
            # logic in this module -- it is a display label and nothing else.
            scored = sorted(((jaccard(_content(_strip_attribution(sent, by_fid[f])),
                                      _content(by_fid[f].get('span'))), f) for f in hits),
                            key=lambda x: -x[0])
            best = scored[0][0]
            if best < 0.10:
                unresolved += 1                           # names a source but matches no span: say so
                continue
            told = [f for s, f in scored if s >= 0.10 and s >= 0.70 * best]

            last_work = work_id(by_fid[told[0]])
            adds = {k for k, p in ADDS_MARKERS.items() if p.search(sent)}
            for fid in told:
                card = by_fid[fid]
                residue = _content(_strip_attribution(sent, card))
                narrations.append(Narration(fid, sec, sub, sent, len(sent.split()), residue, adds,
                                            order, anaphoric, len(told) > 1))

    # ---- who is over-narrated, and what did the repeats cost?
    by_finding: dict[str, list[Narration]] = collections.defaultdict(list)
    for n in narrations:
        by_finding[n.finding_id].append(n)

    hard, soft = [], []
    for fid, ns in by_finding.items():
        ns.sort(key=lambda n: n.order)
        first = ns[0]
        for n in ns[1:]:
            sim = max(jaccard(n.residue, p.residue) for p in ns if p.order < n.order)
            new_adds = n.adds - first.adds
            if sim >= SIM_RESTATE and not new_adds:
                n.verdict = 'RESTATEMENT'
                hard.append((fid, n, sim))
            elif sim >= SIM_RESTATE:
                n.verdict = 'RESTATED_BUT_ADDS'
                soft.append((fid, n, sim))
            else:
                n.verdict = 'OK'

    # exact byte-level repeats (after normalisation) -- the unarguable floor. Dedupe by sentence:
    # a compound sentence appears once per finding it tells, and must be counted ONCE.
    seen_sent = {n.order: n for n in narrations}
    norm_counts = collections.Counter(_norm_text(n.sentence) for n in seen_sent.values())
    exact = {k: v for k, v in norm_counts.items() if v > 1}

    # A SENTENCE is wasted only if EVERY finding it tells was already spent and it adds nothing.
    # Billing per (sentence, finding) pair would charge a 57-word compound twice. Dedupe on `order`.
    hard_orders = {n.order for _, n, _ in hard}
    soft_orders = {n.order for _, n, _ in soft}
    ok_orders = {n.order for n in narrations if n.verdict == 'OK'}
    hard_orders -= ok_orders        # a sentence that does new work for ANY finding is not waste
    soft_orders -= (ok_orders | hard_orders)

    hard_words = sum(seen_sent[o].words for o in hard_orders)
    hard_waste = max(0, hard_words - BACKREF_COST_WORDS * len(hard_orders))
    soft_words = sum(seen_sent[o].words for o in soft_orders)

    return {
        'narrations': narrations,
        'by_finding': by_finding,
        'hard': hard, 'soft': soft, 'exact': exact,
        'hard_orders': hard_orders, 'soft_orders': soft_orders, 'sent_by_order': seen_sent,
        'owned': owned, 'unresolved': unresolved,
        'multi': len({n.order for n in narrations if n.multi}),
        'anaphoric': len({n.order for n in narrations if n.anaphoric}),
        'n_sentences': len(seen_sent),
        'hard_words': hard_words, 'hard_waste': hard_waste, 'soft_words': soft_words,
        'excess_exact': sum(v - 1 for v in exact.values()),
    }


# ===================================================================== report
def _rule(t=''):
    print('\n' + '=' * 78)
    if t:
        print(t)
        print('=' * 78)


def self_test() -> int:
    """Adversarial checks. A rule that is only asserted in a docstring is not a rule.

    (Both real defects this module shipped with -- 49 of 84 reuses granted in narration-only roles,
    and a polarity guard that never fired -- were rules that existed ONLY in prose. Test the rules.)
    """
    fails = []

    def ck(name, cond):
        print(f'  [{"PASS" if cond else "FAIL"}] {name}')
        if not cond:
            fails.append(name)

    print('--- identity: the span is the evidence; the claim is a display cache')
    base = {'span': 'robot adoption reduced employment by 0.2 percent per thousand workers',
            'claim': 'Robots cut jobs.', 'doi': '10.1/x', 'authors': ['A'], 'year': 2020,
            'level': 'firm', 'method': 'observational', 'mechanisms': [], 'has_number': True}
    reworded = dict(base, claim='A COMPLETELY DIFFERENT PARAPHRASE, invented by the model.')
    respanned = dict(base, span='robot adoption RAISED employment by 0.2 percent')
    ck('rewording `claim` does NOT change finding_id (the model cannot forge a fresh identity '
       'for a spent fact by paraphrasing it)', finding_id(base) == finding_id(reworded))
    ck('changing `span` DOES change finding_id (identity tracks the paper, not the prose)',
       finding_id(base) != finding_id(respanned))
    ck('work_id is DOI-stable across differing spans',
       work_id(base) == work_id(respanned))

    print('\n--- the basket: consolidation must never delete a disagreement')
    up = dict(base, span='automation increases labor demand and raises earnings for workers')
    dn = dict(base, span='automation decreases labor demand and reduces earnings for workers')
    ck('unmixed opposite polarity is detected as a contradiction',
       contradicts(up['span'], dn['span']))
    ck('a contradictory pair is BLOCKED from merging even at zero lexical distance',
       'POLARITY' in ' '.join(corroboration_blocks(up, dn, ignore_lexical=True)))
    mixed = dict(base, span='automation reduces the labor share even as it raises productivity')
    ck('mixed-polarity span does NOT report a contradiction (honest limit, documented)',
       not contradicts(up['span'], mixed['span']))
    diff_level = dict(up, level='economy')
    ck('same claim at a DIFFERENT unit of analysis is blocked from merging',
       'unit-of-analysis' in corroboration_blocks(up, diff_level, ignore_lexical=True))
    cl = build_clusters([base, dict(base, doi='10.1/y', authors=['B'])])
    ck('a corroborator is RETAINED in the basket, never dropped',
       sum(1 + len(c.corroborators) for c in cl.values()) == 2)

    print('\n--- the rules')
    rec = FindingRecord('F:1', 'W:1', 'span', 'label', 'C:1')
    rec.uses = [Use('S', 'a', Role.ESTABLISH, 'NARRATE'), Use('S', 'b', Role.ESTABLISH, 'NARRATE')]
    ck('R1 fires: a finding narrated twice is a violation',
       any(v.startswith('R1') for v in rec.violations()))
    rec.uses = [Use('S', 'a', Role.CONTRAST, 'NARRATE'), Use('S', 'b', Role.CONTRAST, 'NEW_ROLE',
                                                             adds={'comparison'})]
    ck('R2 fires: the same analytical role reused is a violation',
       any(v.startswith('R2') for v in rec.violations()))
    rec.uses = [Use('S', 'a', Role.ESTABLISH, 'NARRATE'), Use('S', 'b', Role.CONTRAST, 'NEW_ROLE')]
    ck('R3 fires: a new role that ADDS NOTHING is a violation',
       any(v.startswith('R3') for v in rec.violations()))
    ck('narration-only roles are excluded from reuse (ESTABLISH/MAGNITUDE/DEFINE)',
       not (NARRATION_ONLY_ROLES & REUSABLE_ROLES))

    print('\n--- the plan over the REAL corpus')
    cards = json.loads(CARDS_PATH.read_text())
    bundles, ledger = plan_bundles(cards)
    ck('the plan itself contains ZERO rule violations',
       sum(len(r.violations()) for r in ledger.values()) == 0)
    ck('narration is a PARTITION: every finding narrated exactly once',
       all(len(r.narrations) == 1 for r in ledger.values()))
    ck('no reuse is granted in a narration-only role',
       not any(r in NARRATION_ONLY_ROLES for b in bundles for _, r, _ in b.new_role))
    ck('no finding exceeds the global reuse budget',
       all(sum(1 for u in r.uses if u.mode in ('NEW_ROLE', 'BACKREF')) <= REUSE_BUDGET
           for r in ledger.values()))
    ck('every finding we hold is used somewhere (nothing is silently dropped)',
       all(r.uses for r in ledger.values()))

    print('\n--- waste accounting')
    au = audit_report(REPORT_PATH.read_text(), cards)
    ck('compound sentences are billed ONCE, not once per fact they tell',
       au['hard_words'] == sum(au['sent_by_order'][o].words for o in au['hard_orders']))
    ck('a sentence doing new work for ANY finding is not counted as waste',
       not (au['hard_orders'] & {n.order for n in au['narrations'] if n.verdict == 'OK'}))

    print(f'\n{"** ALL CHECKS PASS **" if not fails else "** " + str(len(fails)) + " FAILED **"}')
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--cards', default=str(CARDS_PATH))
    ap.add_argument('--report', default=str(REPORT_PATH))
    ap.add_argument('--audit-only', action='store_true')
    ap.add_argument('--plan-only', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    cards = json.loads(Path(a.cards).read_text())
    report_md = Path(a.report).read_text()
    by_fid = {finding_id(c): c for c in cards}
    clusters = build_clusters(cards)

    print(f'cards={len(cards)}  distinct findings (span-addressed)={len(by_fid)}  '
          f'works={len({work_id(c) for c in cards})}  claim clusters={len(clusters)}')
    dupe_spans = len(cards) - len(by_fid)
    if dupe_spans:
        print(f'  ! {dupe_spans} cards share a span with another card -- the SAME sentence of the '
              f'same paper, extracted twice. Positional ids hid this; span-addressed ids cannot.')
    multi = [c for c in clusters.values() if c.n_sources > 1]
    merged = sum(len(c.corroborators) for c in clusters.values())
    print(f'  corroborated clusters (>=2 independent works say it): {len(multi)}  '
          f'-- RETAINED in the basket, narrated once')
    print(f'  findings demoted to corroborator (retained, not re-narrated): {merged}')

    if len(multi) == 0:
        d = corroboration_diagnostic(cards)
        _rule('WHY ZERO CORROBORATION CLUSTERS -- AND WHY I DID NOT TUNE THE THRESHOLD TO FIX IT')
        print(f'  max cross-work span Jaccard over {d["n_pairs"]:,} pairs: {d["max_j"]:.3f} '
              f'(threshold {SIM_CORROBORATE}).')
        print('  If the lexical gate were loosened to admit them, what would STILL block these?\n')
        for j, x, y in d['top']:
            stops = corroboration_blocks(x, y, ignore_lexical=True)
            flag = ' + '.join(stops) if stops else '*** NOTHING -- WOULD MERGE ***'
            print(f'    J={j:.3f}  still blocked by: {flag}')
            print(f'      {x["authors"][0]} {x.get("year")}: {x["claim"][:76]}')
            print(f'      {y["authors"][0]} {y.get("year")}: {y["claim"][:76]}')
        print(f'\n  near-miss pairs (J>=0.15), what would STILL block each: {dict(d["blocked"])}')
        print('\n  READ THAT AGAIN: at a loosened threshold, most near-miss pairs merge with NOTHING')
        print('  stopping them -- and one of them (Pillai/Baakeel) is not the same claim at all.')
        print('\n  AND THE POLARITY GUARD IS WEAKER THAN IT LOOKS. I wrote it believing it caught')
        print('  Autor("...INCREASE productivity, RAISE earnings, AUGMENT demand") against')
        print('  Acemoglu("...REDUCES the labor share ... EVEN AS IT RAISES productivity").')
        print('  It does not. Acemoglu\'s span is MIXED ({UP,DOWN}), the bags intersect, and')
        print('  contradicts() returns False. That pair is saved by the UNIT-OF-ANALYSIS guard')
        print('  (worker vs economy) -- NOT by polarity. Direction words bind to OBJECTS, and a bag')
        print('  of words loses the binding. Sound detection needs (direction, quantity) tuples.')
        print('\n  Note what the model did to that sentence: its CLAIM reads "reduces labor\'s share')
        print('  and may diminish labor demand" -- the "even as it raises productivity" hedge is')
        print('  GONE. polarity(claim)={DOWN} but polarity(span)={UP,DOWN}. THE CLAIM IS MORE')
        print('  POLARIZED THAN THE PAPER. A detector run on `claim` would have "found" a')
        print('  contradiction the source does not contain -- and been more confident for having')
        print('  lost the evidence. This is why the span is the only evidence.')
        print('\n  The basket is BUILT and CORRECT; the DETECTOR is the missing piece and it is not')
        print('  lexical. Zero is the honest count. A tuned threshold would delete disagreements.')

    # ---------------------------------------------------------------- what the SELECTOR does today
    if not a.audit_only:
        _rule('WHAT THE CURRENT SELECTOR DOES (cellcog_composer._select, no memory)')
        jobs = [(sec, sub) for sec, subs in OUTLINE for sub in subs]
        slots, sel_count = 0, collections.Counter()
        for sec, sub in jobs:
            for c in _select(cards, sub):
                slots += 1
                sel_count[finding_id(c)] += 1

        never = len(by_fid) - len(sel_count)
        print(f'  {len(jobs)} subsections draw {slots} card slots from {len(sel_count)} distinct '
              f'findings.')
        print(f'  {never} of {len(by_fid)} findings are NEVER selected -- '
              f'{never / len(by_fid) * 100:.0f}% of the evidence we paid to extract is dead weight.')
        print(f'  selection histogram (times selected -> n findings): '
              f'{dict(sorted(collections.Counter(sel_count.values()).items()))}')
        print('  the most over-drawn findings:')
        for fid, n in sel_count.most_common(5):
            c = by_fid[fid]
            print(f'    {n}x  {c["authors"][0]:<12} {c["claim"][:66]}')

    # ---------------------------------------------------------------- THE AUDIT
    if not a.plan_only:
        _rule('THE AUDIT: WHAT THE SHIPPED REPORT ACTUALLY DID')
        au = audit_report(report_md, cards)
        print(f'  attributed SENTENCES              : {au["n_sentences"]}')
        print(f'  (finding, sentence) narration pairs : {len(au["narrations"])}  '
              f'-- {au["multi"]} sentences narrate MORE THAN ONE finding')
        print(f'    ...anaphoric ("They also find that...") : {au["anaphoric"]}')
        print(f'  OWNED sentences (name no source -- legal, not narrations) : {au["owned"]}')
        print(f'  names a source but matches no span (UNRESOLVED, not counted): {au["unresolved"]}')

        over = {f: ns for f, ns in au['by_finding'].items() if len(ns) > 1}
        print(f'\n  distinct findings narrated  : {len(au["by_finding"])} of {len(by_fid)} held')
        print(f'  findings narrated MORE THAN ONCE : {len(over)}')

        _rule('OVER-NARRATED FINDINGS (ranked by wasted words)')
        rank = []
        for fid, ns in over.items():
            w = sum(n.words for n in ns[1:] if n.verdict == 'RESTATEMENT')
            rank.append((w, len(ns), fid, ns))
        rank.sort(key=lambda x: (-x[0], -x[1]))
        for w, k, fid, ns in rank[:10]:
            c = by_fid[fid]
            verdicts = collections.Counter(n.verdict for n in ns[1:])
            print(f'\n  {fid}  narrated {k}x  [{w}w restated]  {c["authors"][0]} {c.get("year")}')
            print(f'    FACT (verbatim span): "{re.sub(chr(10), " ", c["span"])[:96]}"')
            print(f'    repeats: {dict(verdicts)}')
            for n in ns:
                tag = 'FULL NARRATION ' if n is ns[0] else f'{n.verdict:15s}'
                print(f'      [{tag}] {n.subsection[:44]:<44} ({n.words}w)')

        _rule('THE EXACT REPEATED SENTENCES (byte-identical after normalisation)')
        print(f'  {len(au["exact"])} sentence forms appear more than once; '
              f'{au["excess_exact"]} excess instances.\n')
        for k, v in sorted(au['exact'].items(), key=lambda x: -(x[1] * len(x[0].split())))[:8]:
            hitset = [n for n in au['sent_by_order'].values() if _norm_text(n.sentence) == k]
            print(f'  {v}x [{len(k.split())}w] "{hitset[0].sentence[:104]}..."')
            print(f'       in: {" | ".join(n.subsection[:30] for n in hitset)}\n')

        _rule('THE MEASURED RESTATEMENT WASTE')
        body_words = len(re.sub(r'(?m)^#.*$|^\|.*$', '', report_md).split())
        print(f'  report body                                     : {body_words:,} words')
        print(f'  [1] EXACT duplicate sentences (excess instances) : {au["excess_exact"]} sentences')
        print(f'  [2] HARD RESTATEMENT -- every fact it tells was already spent, and it adds nothing:')
        print(f'         {len(au["hard_orders"])} sentences, {au["hard_words"]:,} words')
        print(f'         replaced by an OWNED backward reference (~{BACKREF_COST_WORDS}w each):')
        print(f'         RECLAIMABLE = {au["hard_waste"]:,} words '
              f'({au["hard_waste"] / body_words * 100:.1f}% of the report)')
        print(f'  [3] SOFT -- fact restated but the sentence DOES add something:')
        print(f'         {len(au["soft_orders"])} sentences, {au["soft_words"]:,} words.')
        print(f'         NOT counted as waste. The fact could still be compressed to a pointer while')
        print(f'         keeping the new clause, but I am not going to put a number on that.')
        print(f'\n  HONEST TOTAL (defensible, [2] only) : {au["hard_waste"]:,} words '
              f'= {au["hard_waste"] / body_words * 100:.1f}% of the report says nothing new.')
        print(f'  Charging one backward reference per restatement OVERSTATES the replacement cost')
        print(f'  (a section restating a fact 5x needs one pointer, not five), so this UNDERSTATES')
        print(f'  the recoverable words. Words are billed per SENTENCE, never per (sentence,fact).')

    # ---------------------------------------------------------------- THE PLAN
    if not a.audit_only:
        _rule('THE LEDGER PLAN: WHAT THE BUNDLES WOULD BE INSTEAD')
        bundles, ledger = plan_bundles(cards)
        tot_n = sum(len(b.narrate) for b in bundles)
        tot_r = sum(len(b.new_role) for b in bundles)
        tot_b = sum(len(b.backref) for b in bundles)
        tot_c = sum(len(b.corroborate) for b in bundles)
        narrated_once = sum(1 for r in ledger.values() if len(r.narrations) == 1)
        print(f'  NARRATE (full, once)    : {tot_n}   <- a PARTITION: no fact is narrated twice')
        print(f'  NEW_ROLE (reuse, adds)  : {tot_r}   <- theory/synthesis DO get the canonical facts')
        print(f'  BACKREF (owned pointer) : {tot_b}   <- the fact is spent; point, do not restate')
        print(f'  CORROBORATE (basket)    : {tot_c}   <- retained evidence, never re-narrated')
        print(f'  findings narrated exactly once: {narrated_once} / {len(ledger)}')
        viol = [v for r in ledger.values() for v in r.violations()]
        print(f'  RULE VIOLATIONS IN THE PLAN: {len(viol)}   <- the plan is legal by construction')

        # bundle distinctness
        overlaps = []
        for i, x in enumerate(bundles):
            for y in bundles[i + 1:]:
                overlaps.append(jaccard(x.all_fids(), y.all_fids()))
        import statistics as st
        print(f'\n  bundle distinctness (pairwise Jaccard over 28 subsections):')
        print(f'    mean {st.mean(overlaps):.3f} | max {max(overlaps):.3f}  '
              f'-- each section argues from DIFFERENT evidence')

        print('\n  sample bundles:')
        for b in bundles[:3]:
            print(f'\n    [{b.function.value.upper():<11}] {b.subsection[:56]}')
            for f in b.narrate[:3]:
                print(f'       NARRATE  {ledger[f].label[:62]}')
            for f, role, add in b.new_role[:2]:
                print(f'       {role.value:<9}(must add a {add})  {ledger[f].label[:38]}')
            for f in b.backref[:2]:
                print(f'       BACKREF  (owned pointer, no restatement)  {ledger[f].label[:34]}')

        LEDGER_PATH.write_text(json.dumps({
            'findings': {f: {'work_id': r.work_id, 'cluster_id': r.cluster_id,
                             'primary_section': r.primary_section,
                             'primary_role': r.primary_role.value if r.primary_role else None,
                             'span': r.span,
                             'uses': [{'subsection': u.subsection, 'role': u.role.value,
                                       'mode': u.mode, 'adds': sorted(u.adds)} for u in r.uses]}
                         for f, r in ledger.items()},
            'clusters': {c: {'representative': cl.representative, 'corroborators': cl.corroborators,
                             'n_sources': cl.n_sources} for c, cl in clusters.items()},
            'bundles': [{'section': b.section, 'subsection': b.subsection,
                         'function': b.function.value, 'narrate': b.narrate,
                         'new_role': [(f, r.value, a_) for f, r, a_ in b.new_role],
                         'backref': b.backref, 'corroborate': b.corroborate} for b in bundles],
        }, indent=1))
        print(f'\n  wrote {LEDGER_PATH}  (the composer consumes this; it is not prose)')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
