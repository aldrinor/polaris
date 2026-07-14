#!/usr/bin/env python3
"""THE SYNTHESIS CONTRACT — the "deep thinking" half, without selling the faithfulness moat.

THE PROBLEM, PRECISELY
----------------------
POLARIS's entailment gate (entailment_judge.py:588) kills any sentence that introduces
"a fact, entity, MECHANISM ... NOT present in the SPAN". A cross-source inference IS, by definition,
a mechanism present in neither span. So our own gate deletes exactly the sentence type that earns
INSIGHT — 0.32 weight, the heaviest dimension, and our worst score (0.4238 vs bodhi's 0.5457).

We are not bad at analysis. We built a machine that cannot do it.

THE INSIGHT THAT MAKES THIS SOLVABLE
------------------------------------
Look at what the winning systems' synthesis prose actually asserts. cellcog, verbatim:

    "The three frameworks are complementary rather than competitive. SBTC remains the clearest model
     for relative skill demand. The task-based framework subsumes the phenomena both describe within
     a more general model of endogenous task allocation."

NO new fact. NO number. NO new entity. It RANKS and RELATES claims already on the page.
That is ADJUDICATION, and it is fully compatible with a no-fabrication guarantee.

So we do not relax the gate. We add a SECOND lane with a DIFFERENT PROOF OBLIGATION:

    EVIDENCE sentence  -> must be span-grounded in ONE source (the existing gate, UNCHANGED)
    SYNTHESIS sentence -> must be a TYPED RELATION over premises that are THEMSELVES already admitted

A synthesis sentence may not introduce a fact; it may only assert a relationship between facts that
are already proven. Its proof obligation is structural, not evidential.

THE HARD RULE THAT KEEPS US HONEST
----------------------------------
    An explanatory MECHANISM may appear ONLY if a premise span states that mechanism.
    Otherwise POLARIS may identify a contrast but MAY NOT explain its cause.

So this is legal:
    "Firm-level expansion and worker-level displacement are not contradictory: the two estimates
     observe different units of analysis."          [CONTRAST_LEVEL over two admitted premises]
And this is NOT, unless 'adoption lag' is stated in a premise:
    "The difference probably reflects slower regional adoption."   [imports an unproven mechanism]

Run the adversarial suite:  python scripts/synthesis_contract.py --self-test
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- the typed operations

OPERATIONS = {
    'CONVERGES':            'two or more premises agree on direction/finding',
    'CONTRASTS_DIRECTION':  'premises disagree on the direction of an effect',
    'CONTRASTS_LEVEL':      'premises differ because they observe different units (task/worker/firm/region/economy)',
    'CONTRASTS_HORIZON':    'premises differ because they observe different time horizons',
    'CONTRASTS_METHOD':     'premises differ because they use different identification strategies',
    'BOUNDARY_CONDITION':   'a premise holds only within a stated scope',
    'RANK_EVIDENCE':        'one premise rests on a stronger design than another (declared fields only)',
    'ESTABLISHES':          'the admitted evidence supports a claim AT A STATED LEVEL',
    'DOES_NOT_ESTABLISH':   'the admitted evidence does NOT support a claim at a stated level',
    'REMAINS_UNRESOLVED':   'the admitted evidence cannot distinguish between the competing accounts',
    'COVERAGE_GAP':         'a cell of the evidence matrix is empty — a real, derivable research gap',
    # ---- RUNG 4 verdict operations, each with a proof rule in prove():
    'RECONCILES':           'opposed results are simultaneously true because their span-bound scopes differ',
    'BOUNDARY':             'a pure limitation of the evidence — asserts no relation between premises',
}

# The rubric rewards ADJUDICATION, not hedging. This is the verdict vocabulary.
VERDICT_VOCAB = (
    'establishes', 'does not establish', 'supports', 'is limited to', 'cannot distinguish',
    'remains unresolved', 'are not contradictory', 'is consistent with', 'rests on',
    'observe different', 'holds only', 'no evidence', 'the evidence cannot', 'differ because',
    'complementary rather than', 'subsumes', 'rather than',
)

# A synthesis sentence may NEVER assert a causal mechanism of its own.
CAUSAL_IMPORT = re.compile(
    r'\b(because of|due to|caused by|driven by|reflects|reflecting|owing to|as a result of|'
    r'attributable to|explains why|the reason is|stems from|arises from|leads to|results in)\b', re.I)

# Forecasts / predictions are always fabrication in a literature review.
FORECAST = re.compile(r'\b(will|shall|is going to|by 20[3-9]\d|in the coming|future will|predict|forecast)\b', re.I)

# Universal quantifiers = overclaim.
UNIVERSAL = re.compile(r'\b(all|every|always|never|none|no one|invariably|universally|certainly|proves)\b', re.I)

NUMERIC = re.compile(r'\d')
SPELLED_QTY = re.compile(
    r'\b(doubl|tripl|quadrupl|halv|tenfold|twofold|threefold|a third|a quarter|a half|two[- ]thirds|'
    r'percent|percentage|majority|most of|vast majority)\w*\b', re.I)
CAP_TOKEN = re.compile(r"\b([A-Z][A-Za-z&.\-']{1,})\b")

# ── SOL P1 — THE SAFE_CAPS AUTHORITY IS DELETED FROM PRODUCTION VALIDATION ─────────────────────────
# A capitalised token used to clear the "new entity" gate by matching a HAND-CURATED set (SAFE_CAPS).
# V11 already stripped the task-72 entities from it; P1 finishes the job: there is NO subject allow-list.
# A capitalised name is permitted ONLY when it is (a) present in a premise, (b) present in the original
# QUESTION / compiled contract, (c) sentence-initial by orthography, or (d) emitted from a TYPED RENDERER
# ENUM — an operation name, a verdict marker, a declared facet field, or an epistemic tag. Those four are
# structural signals, not a list of fashionable nouns, so the same predicate protects a clinical, a legal
# and a CS review with no per-domain edit.
#
# `RENDERER_VOCAB` is DERIVED (not typed by hand) from the module's own typed enums: the operations, the
# verdict vocabulary, the declared `Premise` facet fields, and the epistemic tags the composer renders.
# Adding a new operation or facet extends it automatically; adding a world-entity to it is impossible,
# because none of those enums names one.
_EPISTEMIC_TAGS = ('Established', 'Contested', 'Unresolved', 'Emerging', 'Conceptual', 'Analytical',
                   'Hypothesis', 'Pattern', 'Synthesis', 'Proposed', 'Argument')
#: pure grammar/discourse: pronouns, determiners, conjunctions, small numbers, connectives. None of these
#: is a world-entity, and a fabricated NAME is still caught because it appears in none of the four signals.
_DISCOURSE_CAPS = {
    'the', 'this', 'these', 'those', 'taken', 'together', 'both', 'neither', 'either', 'while',
    'whereas', 'although', 'because', 'when', 'where', 'if', 'in', 'at', 'by', 'for', 'a', 'an',
    'it', 'they', 'their', 'its', 'however', 'yet', 'still', 'across', 'within', 'among', 'between',
    'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'our', 'we',
    'that', 'what', 'nor', 'read', 'seen', 'and', 'but', 'not', 'are', 'than', 'then', 'thus',
    'therefore', 'hence', 'also', 'only', 'more', 'most', 'less', 'least', 'former', 'latter',
    'whether', 'which', 'does', 'cannot', 'them', 'with', 'without', 'about', 'over', 'under',
}


#: the DECLARED facet fields (they mirror `Premise`'s dataclass fields — the axes a verdict may turn on),
#: plus the evidence-meta nouns the renderers emit. Every one describes the EVIDENCE, not a world-entity.
_FACET_WORDS = ('level', 'unit', 'analysis', 'scope', 'design', 'horizon', 'method', 'estimate',
                'outcome', 'direction', 'modality', 'comparator', 'population', 'mechanism', 'source',
                'premise', 'finding', 'result', 'evidence', 'study', 'studies', 'research',
                'literature', 'economy', 'aggregate', 'firm', 'worker', 'task', 'region', 'occupation',
                'industry', 'sector')


def _renderer_vocab() -> set[str]:
    words: set[str] = set()
    for phrase in (list(OPERATIONS) + list(VERDICT_VOCAB) + list(_EPISTEMIC_TAGS) + list(_FACET_WORDS)):
        for w in re.findall(r'[A-Za-z]+', str(phrase)):
            if len(w) >= 2:
                words.add(w.lower())
    return words


def caps_earned(token: str, *, premise_caps: set[str], premise_blob_lower: str,
                premise_stems: set[str], context_lower: str = '',
                context_caps: frozenset[str] | set[str] = frozenset()) -> bool:
    """THE single structural predicate for "is this capitalised token NOT a fabricated world-entity?".

    Both `validate()` (the deterministic gate) and `argument_planner.owned_is_safe()` (the owned-voice
    gate) call THIS — there is exactly one caps rule, not two allow-lists that can drift apart. True iff
    the token is earned by a premise, by the original question/compiled contract, by a typed renderer
    enum, or by pure discourse/orthography. It is NEVER earned by a subject allow-list, because there
    is none."""
    if token in premise_caps or token in context_caps:
        return True
    low = token.lower()
    if low in premise_blob_lower or _stem(low) in premise_stems:
        return True
    if context_lower and low in context_lower:
        return True
    return low in RENDERER_VOCAB or low in _DISCOURSE_CAPS


RENDERER_VOCAB = _renderer_vocab()

#: BACKWARD-COMPAT ONLY. `SAFE_CAPS` is no longer an authority anywhere in production validation; it is
#: retained as the union of the discourse + renderer vocabularies so any external diagnostic that still
#: imports the name keeps working. Nothing in `validate()` or `owned_is_safe()` consults it.
SAFE_CAPS = {w.capitalize() for w in (_DISCOURSE_CAPS | RENDERER_VOCAB)} | set(_EPISTEMIC_TAGS)


# ---- SOL V11 — THE RIDING-FABRICATION GUARD --------------------------------------------------------
# A recognised verdict phrase in ONE clause used to license the WHOLE sentence, so a fabrication could
# ride a SECOND clause on the same proof. THIS PASSED before the guard and must not:
#     'These studies observe different units of analysis, and the intervention eradicates disease.'
# The first clause matches _CLAIM_PATTERNS and PROVES as a CONTRASTS_LEVEL verdict; the proof checks the
# unit relation and NOTHING proves the eradication rider. A synthesis is a VERDICT ABOUT THE PREMISES,
# not a lane to smuggle a first-order finding, so EVERY clause must map to a proof conclusion — a
# verdict/relation marker, or a premise-STATED causal mechanism — or introduce NO NEW CONTENT (every
# content token already anchored in a premise or discourse). A clause that predicates a fresh, unanchored
# token has NO positive proof and is an UNPROVED RIDER -> REJECT. This is a list that may ONLY reject:
# an unaccounted content word is UNKNOWN, and the contract fails closed on the unknown (admission requires
# positive proof). The owned lane's semantic judge (report_ast) is the second, independent line; this is
# the deterministic one, so the moat does not rest on the judge alone.
_VERDICT_MARKERS = re.compile('|'.join(re.escape(v) for v in VERDICT_VOCAB), re.I)
# Clause boundaries that introduce an INDEPENDENT proposition. Deliberately NOT a bare ' and '/' or '/
# comma (those join noun phrases — 'the firm and regional levels', 'creation or reallocation') — only
# markers that begin a new predication: ', and', '; and', ';', ', but', ':', 'whereas', 'while',
# ', because', and 'and the <NP>' (the exact shape the eradication rider used).
_RIDER_SPLIT = re.compile(
    r',\s+and\s+|;\s*and\s+|;\s+|,\s+but\s+|:\s+|\s+whereas\s+|\s+while\s+|,\s+because\s+|\band\s+the\s+',
    re.I)
# Genuine discourse / orthography that may head a clause without being a first-order predicate. Derived
# from SAFE_CAPS (so it tracks the same allow-list) plus common function words. It exists ONLY to keep a
# pure connective fragment from being read as a rider; it can admit nothing a premise did not already say.
_DISCOURSE_WORDS = {w.lower() for w in SAFE_CAPS} | {
    'these', 'those', 'this', 'that', 'both', 'either', 'neither', 'taken', 'together', 'however',
    'still', 'therefore', 'thus', 'hence', 'while', 'whereas', 'because', 'since', 'although', 'though',
    'where', 'when', 'across', 'within', 'among', 'between', 'from', 'into', 'onto', 'than', 'then',
    'also', 'only', 'more', 'most', 'less', 'least', 'former', 'latter', 'whether', 'which', 'what',
    'does', 'cannot', 'they', 'their', 'them', 'with', 'without', 'about', 'over', 'under', 'and',
    'but', 'not', 'are', 'for', 'nor', 'the', 'two', 'one',
}


def _unproved_rider_clause(s: str, prem: list['Premise']) -> str:
    """Every clause of a synthesis must be a proved verdict or introduce no new content; a clause that
    predicates a fresh, unanchored token is an UNPROVED RIDER. Returns a refusal reason, or ''."""
    blob = ' '.join(p.text + ' ' + p.source for p in prem)
    blob_low = blob.lower()
    stems = _content_lemmas(blob)
    stated = {m.lower() for p in prem for m in p.mechanisms}
    for clause in _RIDER_SPLIT.split(s):
        low = clause.lower().strip()
        if not low:
            continue
        if _VERDICT_MARKERS.search(low):
            continue                                            # a proved verdict/relation clause
        if any(re.search(rx, low) for _, _, rx in _CLAIM_PATTERNS):
            continue                                            # a recognised verdict pattern
        if CAUSAL_IMPORT.search(low) and any(m in low for m in stated):
            continue                                            # the already-licensed causal path
        for w in re.findall(r'[a-z]{4,}', low):
            if w in _DISCOURSE_WORDS:
                continue
            if w in blob_low or _stem(w) in stems:
                continue                                        # this token is anchored in a premise
            return (f'UNPROVED_RIDER_CLAUSE: "{clause.strip()}" asserts "{w}", a predicate no premise '
                    f'states and no verdict proves — a synthesis may not smuggle a first-order finding')
    return ''


@dataclass
class Premise:
    """An ALREADY-ADMITTED evidence sentence — it passed the existing span-grounding gate.

    RUNG 4 adds the facets a PROOF needs, and the rule that keeps them honest: a facet is only usable in
    a verdict if it is SUPPORTED BY A VERBATIM SPAN. `level` is what the card DECLARES; `unit_span` is the
    verbatim excerpt of THIS premise's own span that supports that declaration. A declared level with an
    empty `unit_span` never entered the span — it is a string off the card, and argument_planner.py:599
    used to trust it. A verdict that turns on a unit no span states is a false reconciliation waiting to
    happen, so `prove()` refuses it.
    """
    id: str
    text: str
    source: str                      # attribution string, e.g. "Autor et al. (2003), QJE"
    level: str = ''                  # task | worker | firm | occupation | region | economy (DECLARED)
    horizon: str = ''                # short-run | long-run
    method: str = ''                 # experiment | quasi-experimental | observational | survey
    mechanisms: list[str] = field(default_factory=list)   # mechanisms STATED IN THE SPAN
    # ---- RUNG 4: span-bound facets. Each is derived from THIS premise's verbatim span, or is empty.
    outcome: str = ''                # the dependent variable, span-derived
    direction: str = ''             # positive | negative | null, span-derived (the SURFACE RESULT)
    unit_span: str = ''             # the verbatim excerpt supporting `level`; '' == level not in span
    outcome_span: str = ''          # the verbatim excerpt supporting `outcome`
    direction_span: str = ''        # the verbatim excerpt supporting `direction`
    horizon_span: str = ''          # the verbatim excerpt supporting `horizon`
    population: str = ''            # who/where the estimate is about (comparator compatibility)
    comparator: str = ''            # against what the effect is measured
    modality: str = 'associational'  # associational | causal — a verdict may not upgrade this


@dataclass
class Synthesis:
    operation: str
    premise_ids: list[str]
    text: str


# ---- LEVEL / UNIT-OF-ANALYSIS SPAN CUES. A declared `level` is only usable in a verdict if one of its
#      cues appears VERBATIM in the premise's own span. This is the span-binding of the most dangerous
#      facet in a reconciliation: the axis it turns on. (argument_planner.py:599 read `level` straight off
#      the card; a card can declare `firm` over a span that only ever says `regions`.)
LEVEL_CUES: dict[str, list[str]] = {
    'task':       ['task'],
    'worker':     ['worker', 'individual', 'employee', 'labor market', 'labour market'],
    'occupation': ['occupation', 'job'],
    # SOL V11: 'plant' removed — it is POLYSEMOUS (factory vs botanical) and would span-support a declared
    # 'firm' level off a sentence about vegetation. A cue that a verdict axis turns on must be unambiguous;
    # an ambiguous token is UNKNOWN, so it is dropped (level_span_support then returns '' and the verdict
    # fails closed) rather than trusted. Cues left here are firm-of-organisation senses only.
    'firm':       ['firm', 'establishment', 'company', 'employer', 'business'],
    'industry':   ['industry', 'sector'],
    'region':     ['region', 'local', 'commuting zone', 'area', 'city', 'county'],
    'economy':    ['econom', 'aggregate', 'national', 'country', 'macro', 'nationwide'],
}


def level_span_support(span: str, level: str) -> str:
    """The verbatim excerpt of `span` that supports the declared `level`, or '' if the span never states
    it. A declared level with no span support MAY NOT be a verdict axis (RUNG 4, obligation 2)."""
    if not span or not level:
        return ''
    low = span.lower()
    for cue in LEVEL_CUES.get(level.lower(), [level.lower()]):
        i = low.find(cue)
        if i >= 0:
            # widen to the surrounding word so the audit trail is a real token, not a fragment
            j, k = i, i + len(cue)
            while j > 0 and (low[j - 1].isalpha() or low[j - 1] in "-"):
                j -= 1
            while k < len(low) and (low[k].isalpha() or low[k] in "-"):
                k += 1
            return span[j:k]
    return ''


def _stem(w: str) -> str:
    """Crude stemmer. Needed because 'task level' must anchor to a premise that says 'tasks',
    and 'effect' to one that says 'effects'. Anchoring is a RELEVANCE check, not a safety check —
    loosening it cannot admit a fabrication (the entity/number/mechanism gates do that work)."""
    for suf in ('ies', 'es', 's'):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def _content_lemmas(s: str) -> set[str]:
    return {_stem(w) for w in re.findall(r'[a-z]{4,}', s.lower())}


def validate(syn: Synthesis, premises: dict[str, Premise], context: str = '') -> tuple[bool, str]:
    """Deterministic. No LLM. Returns (ok, reason_if_rejected).

    `context` is the original question / compiled-contract text (optional). A capitalised token that
    appears in it is EARNED — the reviewer asked about it — exactly as a token appearing in a premise
    is. This is what lets a clinical, a legal, or a CS review name its OWN subject without any per-domain
    allow-list: the subject is in the question, so it is not a fabricated entity."""
    s = syn.text.strip()
    if not s:
        return False, 'empty'

    # 1. the operation must be one we defined
    if syn.operation not in OPERATIONS:
        return False, f'unknown_operation:{syn.operation}'

    # 2. premises must exist and be ADMITTED evidence
    prem = [premises[p] for p in syn.premise_ids if p in premises]
    if len(prem) != len(syn.premise_ids):
        missing = [p for p in syn.premise_ids if p not in premises]
        return False, f'premise_not_admitted:{missing}'

    # 3. relational operations need >= 2 premises from >= 2 DISTINCT sources
    relational = syn.operation not in ('COVERAGE_GAP',)
    if relational:
        if len(prem) < 2:
            return False, 'relational_operation_needs_2+_premises'
        if len({p.source for p in prem}) < 2:
            return False, 'premises_share_a_single_source'

    # 4. NO NEW NUMBER. Ever. (A number belongs to an EVIDENCE sentence, not a synthesis.)
    if NUMERIC.search(s):
        return False, 'synthesis_carries_a_digit'
    if SPELLED_QTY.search(s):
        return False, f'synthesis_carries_a_spelled_quantity:{SPELLED_QTY.search(s).group(0)}'

    # 5. NO NEW ENTITY. Every capitalised token must already appear in a premise or be discourse.
    #    Hyphenated compounds are checked COMPONENT-WISE ("Firm-level" -> "Firm", "level"), because a
    #    compound built from known words introduces no new entity. Each component still has to clear
    #    the same bar, so this cannot let a fabricated name through.
    blob = ' '.join(p.text + ' ' + p.source for p in prem)
    blob_lower = blob.lower()
    prem_caps = set(CAP_TOKEN.findall(blob))
    prem_stems = _content_lemmas(blob)
    ctx_lower = (context or '').lower()
    ctx_caps = set(CAP_TOKEN.findall(context or ''))
    # A PROPER NOUN is a capitalised token appearing MID-SENTENCE. A capital at the start of a sentence
    # (or after a full stop) is ORTHOGRAPHY, not an entity. Turn 2 rejected "Whether", "Reconciliation",
    # "AI's" and "driven" (from "AI-driven") as FABRICATED ENTITIES — every one a false positive, and
    # together they deleted 74 legitimate sentences. The gate's job is to catch INVENTED NAMES, not
    # capital letters.
    sentence_initial = set()
    for m in re.finditer(r'(?:^|[.!?]\s+)([A-Z][A-Za-z&.\-\']*)', s):
        sentence_initial.add(m.group(1))
    for tok in CAP_TOKEN.findall(s):
        if tok in sentence_initial:
            continue                      # orthography, not an entity
        tok = re.sub(r"'s$", '', tok)     # strip the possessive: "AI's" -> "AI"
        for part in re.split(r'[-–]', tok):
            if not part:
                continue
            # THE ONE STRUCTURAL PREDICATE (Sol P1): earned by a premise, the question/contract, a typed
            # renderer enum, or pure discourse — never by a subject allow-list. Same rule owned_is_safe runs.
            if caps_earned(part, premise_caps=prem_caps, premise_blob_lower=blob_lower,
                           premise_stems=prem_stems, context_lower=ctx_lower, context_caps=ctx_caps):
                continue
            return False, f'new_entity:{part}'

    # 6. NO IMPORTED MECHANISM, AND NO FABRICATED BINDING.
    #    A fabrication can be assembled ENTIRELY FROM TRUE PARTICULARS: bind a REAL mechanism to a REAL
    #    paper that never states it. Found live on disk: "task displacement" (Autor-Levy-Murnane's term)
    #    attributed to Bresnahan et al. (2002), whose span never says it. No "new entity" rule catches
    #    that -- both the mechanism and the paper are real. THE LIE IS IN THE BINDING.
    #    So we check TWO things: (a) is a causal mechanism asserted at all, and (b) if the sentence NAMES
    #    a source, does THAT source's own span state the mechanism it is being credited with?
    m = CAUSAL_IMPORT.search(s)
    if m:
        stated = {mm.lower() for p in prem for mm in p.mechanisms}
        if not stated:
            return False, f'causal_language_with_no_stated_mechanism:"{m.group(0)}"'
        if not any(mech in s.lower() for mech in stated):
            return False, f'causal_language_names_a_mechanism_no_premise_states:"{m.group(0)}"'
    # (b) THE BINDING CHECK -- runs whether or not causal vocabulary is present.
    #     If the sentence names an author from a premise AND asserts a mechanism, that mechanism must be
    #     stated by THAT author's premise -- not by some other paper in the room.
    for p in prem:
        surname = p.source.split()[0].rstrip(',')
        if len(surname) < 4 or surname.lower() not in s.lower():
            continue                      # this source is not named in the sentence
        for other in prem:
            if other is p:
                continue
            for mech in other.mechanisms:
                if mech.lower() in s.lower() and mech.lower() not in {x.lower() for x in p.mechanisms}:
                    return False, (f'FABRICATED_BINDING: "{mech}" is stated by {other.source.split()[0]}, '
                                   f'not by {surname} — the sentence credits the wrong paper')

    # 7. NO FORECAST, NO UNIVERSAL
    if FORECAST.search(s):
        return False, f'forecast_or_prediction:"{FORECAST.search(s).group(0)}"'
    if UNIVERSAL.search(s):
        return False, f'universal_overclaim:"{UNIVERSAL.search(s).group(0)}"'

    # 8. (REMOVED AS A HARD GATE.) This demanded "verdict vocabulary" of every uncited sentence and
    #    DELETED 163 sentences in wheel turn 1 — gutting the report to 4,021 words, below the length
    #    floor. It is a STYLE RULE WEARING A SAFETY RULE'S CLOTHES: a sentence that reads as a "vibe"
    #    is weak prose, not a fabrication. Adjudication is what the RUBRIC pays for; the CONTRACT's job
    #    is only to make lying impossible. Conflating the two is why our gate rejects 97% of the prose
    #    that the judge scores 9.8/10. Style belongs in the writer's PROMPT, not in the safety gate.

    # 9. operation-specific structural obligations, checked against DECLARED fields only
    if syn.operation == 'CONTRASTS_LEVEL':
        if len({p.level for p in prem if p.level}) < 2:
            return False, 'CONTRASTS_LEVEL but the premises do not declare 2 distinct levels'
    if syn.operation == 'CONTRASTS_HORIZON':
        if len({p.horizon for p in prem if p.horizon}) < 2:
            return False, 'CONTRASTS_HORIZON but the premises do not declare 2 distinct horizons'
    if syn.operation == 'CONTRASTS_METHOD' or syn.operation == 'RANK_EVIDENCE':
        if len({p.method for p in prem if p.method}) < 2:
            return False, f'{syn.operation} but the premises do not declare 2 distinct methods'

    # 10. must be anchored in the premises it claims to relate
    if len(_content_lemmas(s) & _content_lemmas(blob)) < 2:
        return False, 'not_anchored_in_its_premises'

    # 11. SOL V11 — NO RIDING FABRICATION. Steps 1-10 prove the RELATION the sentence's recognised phrase
    #     asserts; they never inspect the REST of the sentence. A recognised verdict clause may not license
    #     an unproved rider ('...observe different units, and the intervention eradicates disease'). Every
    #     clause must be a proved verdict or introduce no new content, else the sentence smuggles a finding.
    why_rider = _unproved_rider_clause(s, prem)
    if why_rider:
        return False, why_rider

    return True, ''


# =================================================================================================
# RUNG 4 — PROOF-CARRYING VERDICTS. `validate()` above proves a verdict is SAFE (no new particular,
# anchored, no imported mechanism). It does NOT prove the verdict is TRUE: it let CONVERGES, CONTRASTS,
# ESTABLISHES and DOES_NOT_ESTABLISH pass on anchoring alone, so the gate admitted BOTH "these point in
# opposite directions" AND "these are not contradictory" for the SAME premises — a false reconciliation
# assembled entirely from true particulars. A verdict now needs a PROOF OBJECT, not a tag: an operation
# whose preconditions are checked against SPAN-BOUND facets, with the exact excerpt that supports each.
# =================================================================================================

@dataclass
class RelationProof:
    """The receipt a verdict must carry. Every dimension it asserts SHARED or DIFFERING is bound to the
    verbatim span that supports it, on each premise. If a facet is unproved, no proof is issued and no
    verdict ships."""
    operation: str
    claim_class: str
    premise_ids: list[str]
    shared: dict[str, list[tuple[str, str]]] = field(default_factory=dict)     # dim -> [(pid, span)]
    differing: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # dim -> [(pid, value, span)]
    polarity: dict[str, str] = field(default_factory=dict)                     # pid -> direction
    modality: dict[str, str] = field(default_factory=dict)                     # pid -> associational|causal
    comparator: dict[str, str] = field(default_factory=dict)                   # pid -> comparator
    rule: str = ''                                                             # the precondition satisfied
    conclusion: str = ''                                                       # the licensed claim template


# ---- THE VERDICT CLASS A SENTENCE ASSERTS. A verdict is checked against the proof of the operation that
#      licenses ITS OWN claim, not against "any operation that happens to pass". Order is load-bearing:
#      a reconciliation ("not contradictory") is tested before the milder "different units" reading,
#      because a sentence that says both must be held to the stronger obligation.
_CLAIM_PATTERNS: list[tuple[str, str, str]] = [
    # (claim_class, licensing_operation, regex)
    ('RECONCILES', 'RECONCILES',
     r'not contradictory|are consistent with|do not (?:conflict|contradict)|only look contradictory|'
     r'can both be true|simultaneously true|reconcil'),
    ('CONTRASTS_DIRECTION', 'CONTRASTS_DIRECTION',
     r'opposite direction|genuinely conflict|cannot be dissolved|does not speak with one voice|'
     r'\bin tension\b|point in opposite|remains unresolved|sets against itself|genuinely disagree'),
    ('CONTRASTS_LEVEL', 'CONTRASTS_LEVEL',
     r'different units? of analysis|not directly comparable|different levels?|'
     r'what holds at .* (?:does not|not) .*establish|does not establish .* at the .* level|'
     r'observe different units'),
    ('CONTRASTS_HORIZON', 'CONTRASTS_HORIZON',
     r'different time horizon|transitional effect|settled one|observe different .* horizon'),
    ('RANK_EVIDENCE', 'RANK_EVIDENCE',
     r'rests on (?:a|an) \w+ design|more securely|stronger design|'
     r'different identification (?:strategy|design)'),
    ('CONVERGES', 'CONVERGES',
     r'\bconverg|point in the same direction|same directional finding|agree on'),
    # A PURE LIMITATION STATEMENT asserts that the evidence CANNOT do something. It reconciles nothing and
    # relates no two directions, so it cannot be a false reconciliation; it is licensed by anchoring alone.
    ('BOUNDARY', 'BOUNDARY',
     r'does not settle|not on the same footing|cannot distinguish|is limited to|rests on a single '
     r'source|no other study|does not extend beyond|cannot establish'),
]


def classify_claim(text: str) -> tuple[str, str]:
    """(claim_class, licensing_operation). '' if the sentence makes no recognised verdict — in which case
    the gate FAILS CLOSED: an owned synthesis whose claim cannot be identified cannot be proved."""
    low = text.lower()
    for claim_class, op, rx in _CLAIM_PATTERNS:
        if re.search(rx, low):
            return claim_class, op
    return '', ''


def _both_known_opposed(a: Premise, b: Premise) -> bool:
    return (bool(a.direction) and bool(b.direction)
            and {a.direction, b.direction} in ({'positive', 'negative'},
                                               {'positive', 'null'}, {'negative', 'null'}))


def prove(operation: str, premises: list[Premise], text: str) -> tuple[RelationProof | None, str]:
    """Build the proof for `operation` over `premises`, or refuse with a reason. This is the whole point
    of RUNG 4: each operation verifies ITS OWN preconditions against span-bound facets. A verdict ships
    ONLY if the proof for the operation THAT LICENSES ITS CLAIM is issued. There is no "try them all".
    """
    if operation not in OPERATIONS:
        return None, f'unknown_operation:{operation}'
    # BOUNDARY / COVERAGE_GAP are NON-RELATIONAL: they state a limit of the evidence and relate no two
    # findings, so they neither need a second premise nor a second source. Every other operation does.
    non_relational = operation in ('BOUNDARY', 'COVERAGE_GAP')
    if not non_relational:
        if len(premises) < 2:
            return None, 'a relational verdict needs at least two premises'
        if len({p.source for p in premises if p.source}) < 2:
            return None, 'the premises share a single source — a paper cannot corroborate itself'

    a = premises[0]
    b = premises[1] if len(premises) > 1 else premises[0]
    ids = [p.id for p in premises]

    # SAME CONSTRUCT. Almost every operation first requires the premises to be about the SAME outcome;
    # opposed results on DIFFERENT outcomes are not in tension and cannot be reconciled or contrasted.
    outcomes = {p.outcome for p in premises if p.outcome}
    shared_outcome = bool(outcomes) and len(outcomes) == 1 and all(p.outcome for p in premises)

    def _unit_spans_present() -> str:
        for p in premises:
            if p.level and not p.unit_span:
                return (f'the {p.id} card declares level "{p.level}" but no verbatim span supports it — '
                        f'a facet a verdict turns on must be bound to the span')
            if not p.level:
                return f'the {p.id} card declares no unit of analysis'
        return ''

    def _proof(claim_class, shared, differing, rule, conclusion) -> tuple[RelationProof, str]:
        return RelationProof(
            operation=operation, claim_class=claim_class, premise_ids=ids,
            shared=shared, differing=differing,
            polarity={p.id: p.direction for p in premises},
            modality={p.id: p.modality for p in premises},
            comparator={p.id: p.comparator for p in premises},
            rule=rule, conclusion=conclusion), ''

    # ---- RECONCILES: "these opposed results are NOT contradictory". The strongest claim on the board,
    #      and the one the adversary forged. It is licensed ONLY by a full reconciliation: same construct,
    #      opposed surface results, a scope (unit) that DIFFERS and is span-bound on both premises, and a
    #      compatible time base. Same scope + opposed results is a GENUINE conflict, not a reconciliation.
    if operation == 'RECONCILES':
        if not shared_outcome:
            return None, 'reconciliation requires the same construct on both premises (no shared outcome)'
        if not _both_known_opposed(a, b):
            return None, ('reconciliation requires OPPOSED, span-derived surface results — there is '
                          'nothing to reconcile unless the two findings actually oppose')
        why = _unit_spans_present()
        if why:
            return None, why
        if len({p.level for p in premises}) < 2:
            return None, ('the premises share a scope, so opposed results are a GENUINE CONFLICT, not a '
                          'reconciliation — there is no scope difference that lets both be true at once')
        hs = {p.horizon for p in premises if p.horizon}
        if len(hs) > 1:
            return None, ('the premises also differ in time horizon, so the difference is not cleanly '
                          'attributable to scope — the reconciliation is unproved')
        return _proof(
            'RECONCILES',
            shared={'outcome': [(p.id, p.outcome_span or p.outcome) for p in premises]},
            differing={'unit_of_analysis': [(p.id, p.level, p.unit_span) for p in premises]},
            rule='same construct + opposed span-derived results + span-bound DIFFERING scope + compatible '
                 'horizon => both can be simultaneously true',
            conclusion='not_contradictory: they observe different units of analysis')

    # ---- CONTRASTS_DIRECTION: "the evidence genuinely conflicts / points in opposite directions". A REAL
    #      conflict: same construct, SAME span-bound scope, opposed span-derived directions. The scope
    #      must be the SAME — opposed results at DIFFERENT units are reconcilable, not a conflict.
    if operation == 'CONTRASTS_DIRECTION':
        if not shared_outcome:
            return None, 'a direction conflict requires the same construct (no shared outcome)'
        if not _both_known_opposed(a, b):
            return None, 'the directions are not both span-derived and opposed'
        why = _unit_spans_present()
        if why:
            return None, why
        if len({p.level for p in premises}) > 1:
            return None, ('the premises observe different units, so opposed results are not a direct '
                          'conflict — they are reconcilable by scope, not "genuinely contradictory"')
        return _proof(
            'CONTRASTS_DIRECTION',
            shared={'outcome': [(p.id, p.outcome_span or p.outcome) for p in premises],
                    'unit_of_analysis': [(p.id, p.unit_span) for p in premises]},
            differing={'direction': [(p.id, p.direction, p.direction_span or p.direction) for p in premises]},
            rule='same construct + SAME span-bound scope + opposed span-derived directions => genuine '
                 'conflict that cannot be dissolved by appeal to level',
            conclusion='genuine_conflict: opposed at the same unit of analysis')

    # ---- CONTRASTS_LEVEL: the MILD reading — "these concern different units and are not directly
    #      comparable". Licensed by a span-bound DIFFERING scope on the same construct. It does NOT license
    #      "not contradictory" (that is RECONCILES, and needs opposed results + a compatible time base).
    if operation == 'CONTRASTS_LEVEL':
        if not shared_outcome:
            return None, 'a unit contrast requires the same construct (no shared outcome)'
        why = _unit_spans_present()
        if why:
            return None, why
        if len({p.level for p in premises}) < 2:
            return None, 'the premises do not observe two distinct, span-bound units of analysis'
        return _proof(
            'CONTRASTS_LEVEL',
            shared={'outcome': [(p.id, p.outcome_span or p.outcome) for p in premises]},
            differing={'unit_of_analysis': [(p.id, p.level, p.unit_span) for p in premises]},
            rule='same construct + span-bound DIFFERING scope => not directly comparable',
            conclusion='different_units_not_comparable')

    # ---- CONTRASTS_HORIZON: same construct, differing declared time horizon.
    if operation == 'CONTRASTS_HORIZON':
        if not shared_outcome:
            return None, 'a horizon contrast requires the same construct (no shared outcome)'
        hs = {p.horizon for p in premises if p.horizon}
        if len([p for p in premises if p.horizon]) < len(premises):
            return None, 'at least one premise declares no horizon'
        if len(hs) < 2:
            return None, 'the premises do not declare two distinct horizons'
        return _proof(
            'CONTRASTS_HORIZON',
            shared={'outcome': [(p.id, p.outcome_span or p.outcome) for p in premises]},
            differing={'horizon': [(p.id, p.horizon, p.horizon_span or p.horizon) for p in premises]},
            rule='same construct + differing horizon => a horizon spread',
            conclusion='different_horizons')

    # ---- RANK_EVIDENCE: same directional finding, differing declared method.
    if operation == 'RANK_EVIDENCE':
        ms = {p.method for p in premises if p.method}
        if len([p for p in premises if p.method]) < len(premises):
            return None, 'at least one premise declares no method'
        if len(ms) < 2:
            return None, 'the premises do not declare two distinct methods to rank'
        return _proof(
            'RANK_EVIDENCE',
            shared={'outcome': [(p.id, p.outcome_span or p.outcome) for p in premises]},
            differing={'method': [(p.id, p.method, p.method) for p in premises]},
            rule='same finding + differing method => the stronger design ranks higher',
            conclusion='ranked_by_design')

    # ---- CONVERGES: the premises AGREE in span-derived direction on the same construct.
    if operation == 'CONVERGES':
        if not shared_outcome:
            return None, 'convergence requires the same construct (no shared outcome)'
        dirs = {p.direction for p in premises if p.direction}
        if len([p for p in premises if p.direction]) < len(premises):
            return None, 'convergence requires a span-derived direction on every premise'
        if len(dirs) != 1:
            return None, 'the premises do not point in the same direction — this is not convergence'
        return _proof(
            'CONVERGES',
            shared={'outcome': [(p.id, p.outcome_span or p.outcome) for p in premises],
                    'direction': [(p.id, p.direction, p.direction_span or p.direction) for p in premises]},
            differing={},
            rule='same construct + same span-derived direction => convergence',
            conclusion='converges')

    # ---- BOUNDARY / COVERAGE_GAP: a pure limitation or a derivable gap. They relate no two directions
    #      and reconcile nothing, so the only obligation is that the premises are admitted — they cannot
    #      be a false verdict.
    if operation in ('BOUNDARY', 'COVERAGE_GAP'):
        return _proof(operation, shared={}, differing={},
                      rule='a limitation/gap statement asserts no relation, so it carries no reconciliation',
                      conclusion='states a limit of the evidence')

    return None, f'no proof rule for operation {operation}'


def prove_owned(text: str, premises: list[Premise]) -> tuple[RelationProof | None, str]:
    """The release-boundary entry point. Classify the CLAIM the sentence makes, then demand the proof of
    the operation that licenses THAT claim. Fails closed on an unclassifiable claim."""
    claim_class, op = classify_claim(text)
    if not op:
        return None, ('the sentence makes no recognised verdict — an owned synthesis whose claim cannot '
                      'be identified cannot be proved, so it is refused')
    proof, why = prove(op, premises, text)
    if proof is None:
        return None, f'{claim_class}:{why}'
    return proof, ''


# ---------------------------------------------------------------- adversarial suite

P = {
    'p1': Premise('p1', 'Generative AI raised the productivity of professional writing tasks by 40 percent.',
                  'Noy and Zhang (2023), Science', level='task', horizon='short-run', method='experiment'),
    'p2': Premise('p2', 'Aggregate employment effects in AI-exposed occupations were too small to detect over the period studied.',
                  'Acemoglu et al. (2022), Journal of Labor Economics', level='economy', horizon='long-run',
                  method='observational'),
    'p3': Premise('p3', 'Firms adopting AI expanded employment relative to non-adopting competitors.',
                  'Babina et al. (2024), Journal of Financial Economics', level='firm', horizon='long-run',
                  method='observational'),
    'p4': Premise('p4', 'Routine task-intensive middle-wage occupations declined as computerisation spread, '
                        'a process the authors attribute to task displacement.',
                  'Autor et al. (2003), Quarterly Journal of Economics', level='occupation', horizon='long-run',
                  method='observational', mechanisms=['task displacement']),
}

ATTACKS = [
    # (should_admit, operation, premises, sentence, label)
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'The difference probably reflects slower regional adoption of the technology.',
     'imports a mechanism (adoption lag) no premise states'),
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'Task-level gains of 40 percent do not establish economy-wide employment growth.',
     'carries a digit — that belongs to an EVIDENCE sentence'),
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'Goldman Sachs analysts establish that these effects operate at different levels.',
     'fabricated attribution / new entity'),
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'Task-level productivity gains doubled while aggregate effects remain unproven.',
     'spelled-out quantity ("doubled")'),
    (False, 'ESTABLISHES', ['p1', 'p2'],
     'AI will establish permanent job losses across the economy by 2035.',
     'forecast'),
    (False, 'CONVERGES', ['p1', 'p2'],
     'All studies establish that AI displaces workers.',
     'universal overclaim'),
    (False, 'CONTRASTS_LEVEL', ['p1'],
     'These findings observe different units of analysis.',
     'relational operation with only ONE premise'),
    (False, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'The literature on artificial intelligence and work is complex and multifaceted.',
     'no verdict vocabulary — a vibe, not an adjudication'),
    (False, 'CONTRASTS_HORIZON', ['p2', 'p3'],
     'These results are not contradictory: they observe different time horizons.',
     'CONTRASTS_HORIZON but both premises declare the SAME horizon (long-run)'),
    # --- these MUST be admitted: real adjudication, no new facts ---
    (True, 'CONTRASTS_LEVEL', ['p1', 'p2'],
     'These findings are not contradictory: the evidence establishes gains at the task level but '
     'does not establish an effect at the level of the economy.',
     'LEGAL: adjudicates two admitted premises across declared levels, no new fact'),
    (True, 'CONTRASTS_LEVEL', ['p2', 'p3'],
     'Firm-level expansion and undetectable aggregate effects are not contradictory, because the two '
     'estimates observe different units of analysis; the evidence is limited to relative outcomes '
     'among firms and cannot distinguish reallocation from net creation.',
     'LEGAL: reconciles firm vs economy, states what the evidence cannot do'),
    (True, 'RANK_EVIDENCE', ['p1', 'p2'],
     'The task-level result rests on an experimental design, whereas the aggregate result rests on '
     'observational data; the evidence therefore establishes the former more securely than the latter.',
     'LEGAL: ranks by DECLARED method fields only'),
    (True, 'REMAINS_UNRESOLVED', ['p2', 'p3'],
     'Taken together, the evidence cannot distinguish whether firm-level gains represent net job '
     'creation or reallocation from competitors; this remains unresolved.',
     'LEGAL: names exactly what the literature cannot settle'),
    (True, 'CONTRASTS_LEVEL', ['p2', 'p4'],
     'The occupational decline is attributable to task displacement, whereas the aggregate series '
     'does not establish a comparable effect at the level of the economy.',
     'LEGAL: causal language permitted — "task displacement" IS stated in premise p4'),
]


def self_test() -> int:
    print('=== SYNTHESIS CONTRACT — adversarial suite ===')
    print('   (deterministic; no LLM; a FALSE ADMISSION is a breach of the moat)\n')
    false_admits = false_rejects = 0
    for should_admit, op, pids, text, label in ATTACKS:
        ok, why = validate(Synthesis(op, pids, text), P)
        good = (ok == should_admit)
        if not good and ok:
            false_admits += 1
        if not good and not ok:
            false_rejects += 1
        mark = 'PASS' if good else ('**FALSE ADMIT**' if ok else '**FALSE REJECT**')
        verdict = 'ADMIT ' if ok else 'REJECT'
        print(f'  [{mark:>15}] {verdict} :: {label}')
        if not ok and should_admit:
            print(f'                     rejected because: {why}')
        if ok and not should_admit:
            print(f'                     !! ADMITTED: "{text[:70]}"')
    n_valid = sum(1 for a in ATTACKS if a[0])
    n_invalid = len(ATTACKS) - n_valid
    print(f'\n  invalid examples: {n_invalid}  | FALSE ADMISSIONS: {false_admits}  (release requires ZERO)')
    print(f'  valid examples  : {n_valid}  | false rejections: {false_rejects}')
    if false_admits:
        print('\n  ** RELEASE BLOCKED: the contract admitted a fabrication. **')
        return 1
    if false_rejects:
        print('\n  ** contract is SAFE but too strict — it rejects legitimate adjudication. **')
        return 1
    print('\n  ** CONTRACT GREEN: zero false admissions, zero false rejections. **')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    print(json.dumps({'operations': OPERATIONS}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
