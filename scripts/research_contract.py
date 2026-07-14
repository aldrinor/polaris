#!/usr/bin/env python3
"""THE QUERY COMPILER — compiles ANY question into a RESEARCH CONTRACT.

WHY THIS EXISTS
---------------
cellcog_composer.py is a TASK-72 MACHINE. The extraction question (:103), the outline (:264), the
title and abstract (:744), the sector list, the unit-of-analysis enum (:140) and the rubric reading
(:250) are all hardcoded. Every one of our 38 scored runs is task 72. WE DO NOT KNOW WHAT THIS
PIPELINE SCORES ON AN UNSEEN QUESTION, and the mission is a system that beats SOTA on ANY question.

This module is the layer that was missing: question in, CONTRACT out. Everything the composer needs
to be told about a topic -- what to mine, what to compare, what to cover, what genre to write, which
sources are admissible -- is DERIVED HERE, and nothing about any particular topic is written down.

    compile_contract(question)      -> Contract          ONE LLM call, cached on disk, span-gated
    coverage_matrix(contract, cards)-> Matrix            pure function
    derive_outline(contract, matrix)-> list[Slot]        pure function
    build_extract_prompt(...)       -> str               replaces the hardcoded EXTRACT_PROMPT

THE ONE LLM CALL IS THE ONLY NONDETERMINISM. Coverage, outline, facets, card allocation and prompts
are pure derivations from the compiled contract, so they are reproducible, auditable, and testable
without a network. `--no-llm` compiles a degraded contract from the question by regex alone, so CI
can exercise every derivation offline.

THE COMPILER IS ITSELF SPAN-GATED
---------------------------------
The same law that governs the report governs the contract. A SOURCE CONSTRAINT is an ATTRIBUTED
claim -- it is attributed to THE QUESTION -- so it must be entailed by a VERBATIM SPAN OF THE
QUESTION. The model must quote the clause that imposes each constraint; a constraint whose quote is
not literally in the question is DROPPED, never repaired. And because a model that forgets a
constraint is as dangerous as one that invents one, a REGEX FLOOR independently detects the
constraints that are cheap to detect, and the model may ADD to that floor but may never DROP it.

    Q: "Ensure the review only cites high-quality, English-language journal articles."
    -> peer_reviewed_only=True, languages=['English'], and neither can be argued away.

WHAT A CELL OF THE COVERAGE MATRIX IS
-------------------------------------
rows    = the SUBJECT AXIS (industries for one question, disease stages for another, liability
          scenarios for a third -- THE AXIS IS NAMED BY THE CONTRACT, not by this file)
columns = the OUTCOME DIMENSIONS

A cell CLOSES on evidence:      >=2 groundable works, >=1 result, method contrast where material
A cell CLOSES on an honest GAP: an explicit, corpus-scoped "the literature we hold does not cover
                                this" -- which is worth MORE than filler, and is the direct fix for
                                the outline writing cheques the corpus cannot cash (the task-72
                                outline promised a 4-subsection industry section over a corpus
                                holding retail=0, education=1).

Usage:
    set -a && . ./.env && set +a
    python scripts/research_contract.py                      # compiles task 72, prints everything
    python scripts/research_contract.py --task 90            # any DeepResearch Bench task
    python scripts/research_contract.py --question "..."     # any question at all
    python scripts/research_contract.py --no-llm             # offline, regex-only contract
    python scripts/research_contract.py --audit-rubric       # POST-HOC only. never an input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import textwrap
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

DRB = ROOT / 'third_party' / 'deep_research_bench' / 'data'
QUERIES = DRB / 'prompt_data' / 'query.jsonl'
CRITERIA = DRB / 'criteria_data' / 'criteria.jsonl'
CARDS = ROOT / 'outputs' / 'evidence_cards.json'
CACHE = ROOT / 'outputs' / 'contracts'

# THE COMPILER VERSION. It is part of the cache key, so a contract compiled by an older prompt OR an
# older gate can never be silently reused. Bump it when the prompt, the schema, OR the admission
# logic changes -- the cache stores the POST-GATE contract, so a loosened gate lives on in the cache
# until this changes. (rc-2 cached a fabricated `recency_from: 2015`.)
PROMPT_VERSION = 'rc-3'

# Coverage thresholds. Defaults from the specification; overridable per contract, never per topic.
MIN_WORKS_PER_CELL = 2       # >=2 groundable relevant works
MIN_RESULTS_PER_CELL = 1     # >=1 quantitative or direct qualitative result
METHOD_CONTRAST_MATERIAL_AT = 3   # below this many works, demanding two designs is not material
MAX_CARD_REUSE = 2           # 222 slots drawn from 82 cards; one finding was used 8 times


# ===================================================================== the contract

@dataclass
class Term:
    """A concept the matcher can look for: a label plus the surface forms it wears."""
    key: str
    label: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class Axis:
    """The rows of the coverage matrix. THE GENERALISATION OF 'INDUSTRIES'.

    For a question about AI and work this is `Industry`. For one about Parkinson's it is `Disease
    stage`. For one about ADAS liability it is `Accident scenario`. The composer must never assume.
    """
    name: str = 'Subpopulation'
    values: list[Term] = field(default_factory=list)


@dataclass
class Contrast:
    """A tension the review is OBLIGED to draw. This is the shared argument state that 28
    independently-generated subsections did not have, and that no later cohesion pass can invent."""
    key: str
    label: str
    a: str
    b: str
    why: str = ''


@dataclass
class Facet:
    """An extraction facet the miner harvests. Derived from the question -- for task 72 one of these
    is the Fourth Industrial Revolution, but NOTHING about the 4IR is written in this file."""
    key: str
    label: str
    probe: str            # the question asked of every paper
    priority: int = 2     # 1 = must-have
    serves: str = ''      # which contract element it feeds


@dataclass
class SourcePolicy:
    """The REQUESTED SOURCE CONSTRAINTS. Every field must point at a verbatim clause of the question."""
    peer_reviewed_only: bool = False
    languages: list[str] = field(default_factory=list)
    excluded_types: list[str] = field(default_factory=list)
    quality_bar: str = ''
    recency_from: int | None = None
    question_evidence: list[str] = field(default_factory=list)   # VERBATIM spans of the question

    def compliance_prose(self) -> str:
        """What the Scope & Methods section must SAY. On a question graded 'only cites high-quality
        journal articles', the winning system EXPLAINS ITS COMPLIANCE TO THE GRADER in prose and we
        currently say nothing.

        DELIBERATELY NUMBER-FREE. A sentence about our own procedure names no source, so the
        composer's gate reads it as OWNED -- and an OWNED sentence carrying a number is dropped
        (OWNED_CARRIES_A_NUMBER). Rather than widen a gate to admit prose (forbidden), the prose is
        written to be admissible. Corpus counts would need their own PROCEDURE lane, validated
        against the corpus manifest, which is a real non-model artifact.
        """
        bits = []
        if self.peer_reviewed_only:
            bits.append('draws exclusively on peer-reviewed journal articles')
        if self.quality_bar:
            bits.append(f'applies a {self.quality_bar} standard to every source admitted')
        if self.languages:
            langs = ' and '.join(self.languages)
            bits.append(f'admits only articles published in {langs}')
        if self.recency_from:
            bits.append(f'restricts the evidence base to work published from {self.recency_from} onward')
        if self.excluded_types:
            ex = ', '.join(self.excluded_types[:5])
            bits.append(f'excludes {ex}, which fall outside the requested source class')
        if not bits:
            return ''
        head = 'This review ' + '; it '.join(bits) + '.'
        tail = ('Sources that could not be verified against the stated criteria were excluded rather '
                'than reported with a caveat.')
        return head + ' ' + tail


@dataclass
class Contract:
    """THE RESEARCH CONTRACT. Everything the composer is allowed to know about the topic."""
    question: str
    question_id: int | None = None
    genre: str = 'literature review'
    genre_rules: list[str] = field(default_factory=list)
    review_subject: str = ''
    title: str = ''
    core_concepts: list[Term] = field(default_factory=list)
    framing_devices: list[Term] = field(default_factory=list)   # a lens the QUESTION imposes
    subject_axis: Axis = field(default_factory=Axis)
    outcome_dimensions: list[Term] = field(default_factory=list)
    geographies: list[str] = field(default_factory=list)
    time_horizons: list[str] = field(default_factory=list)
    method_designs: list[str] = field(default_factory=list)     # the design vocabulary FOR THIS Q
    unit_levels: list[str] = field(default_factory=list)        # the `level` enum FOR THIS Q
    required_contrasts: list[Contrast] = field(default_factory=list)
    source_policy: SourcePolicy = field(default_factory=SourcePolicy)
    facets: list[Facet] = field(default_factory=list)
    evidence_tuple: list[str] = field(default_factory=list)
    compiled_by: str = ''
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, ensure_ascii=False)

    @staticmethod
    def from_dict(d: dict) -> 'Contract':
        t = lambda xs: [Term(**x) for x in xs or []]
        c = Contract(**{k: v for k, v in d.items() if k not in (
            'core_concepts', 'framing_devices', 'subject_axis', 'outcome_dimensions',
            'required_contrasts', 'source_policy', 'facets')})
        c.core_concepts = t(d.get('core_concepts'))
        c.framing_devices = t(d.get('framing_devices'))
        ax = d.get('subject_axis') or {}
        c.subject_axis = Axis(name=ax.get('name', 'Subpopulation'), values=t(ax.get('values')))
        c.outcome_dimensions = t(d.get('outcome_dimensions'))
        c.required_contrasts = [Contrast(**x) for x in d.get('required_contrasts') or []]
        c.source_policy = SourcePolicy(**(d.get('source_policy') or {}))
        c.facets = [Facet(**x) for x in d.get('facets') or []]
        return c


# ===================================================================== the regex floor
#
# THE MODEL MAY ADD TO THIS. IT MAY NEVER DROP IT. A source constraint is 0.25 of instruction-
# following on task 72 (journal-only 0.15 + English-only 0.10); a compiler that can be talked out of
# a constraint by its own LLM is not a compiler.

_FLOOR = [
    # (regex over the question, field, value)
    (r'peer[-\s]?reviewed|journal article|scholarly (?:article|literature|source)|'
     r'academic (?:journal|literature)|published (?:in )?journals?', 'peer_reviewed_only', True),
    (r'english[-\s]?language|in english', 'language', 'English'),
    (r'high[-\s]?quality|top[-\s]?tier|leading journals?|reputable', 'quality_bar', 'high-quality'),
]
_EXCLUDE_IF_PEER_REVIEWED = ['books', 'conference proceedings', 'preprints', 'working papers',
                             'news articles', 'blog posts', 'non-peer-reviewed reports']

_GENRE_FLOOR = [
    (r'literature review|review the literature|systematic review', 'literature review'),
    (r'policy brief', 'policy brief'),
    (r'comparative analysis|compare and contrast', 'comparative analysis'),
    (r'\banalys[ei]s?\b.*\brecommendations?\b|propose[d]? (?:regulatory )?guidelines',
     'analytical report with recommendations'),
    (r'\breport\b', 'report'),
]

_RECENCY = re.compile(r'(?:since|after|from|published in or after|past\s+\d+\s+years?[, ]*since)\s+'
                      r'((?:19|20)\d\d)', re.I)


def _floor_source_policy(q: str) -> SourcePolicy:
    """Detect the constraints that are cheap to detect. The LLM cannot argue these away."""
    sp = SourcePolicy()
    for rx, fld, val in _FLOOR:
        m = re.search(rx, q, re.I)
        if not m:
            continue
        # THE CLAUSE, VERBATIM. A constraint that cannot point at its clause is not a constraint.
        sp.question_evidence.append(_clause_around(q, m.start(), m.end()))
        if fld == 'peer_reviewed_only':
            sp.peer_reviewed_only = True
        elif fld == 'language':
            if val not in sp.languages:
                sp.languages.append(val)
        elif fld == 'quality_bar':
            sp.quality_bar = val
    m = _RECENCY.search(q)
    if m:
        sp.recency_from = int(m.group(1))
        sp.question_evidence.append(_clause_around(q, m.start(), m.end()))
    if sp.peer_reviewed_only:
        sp.excluded_types = list(_EXCLUDE_IF_PEER_REVIEWED)
    sp.question_evidence = _dedup(sp.question_evidence)
    return sp


def _clause_around(q: str, i: int, j: int) -> str:
    """The verbatim clause of the question containing [i:j). This is the SPAN a constraint cites."""
    lo = max((q.rfind(c, 0, i) for c in '.;\n'), default=-1)
    hi = min([x for x in (q.find(c, j) for c in '.;\n') if x != -1] or [len(q)])
    return q[lo + 1:hi + 1].strip()


def _floor_genre(q: str) -> str:
    for rx, g in _GENRE_FLOOR:
        if re.search(rx, q, re.I):
            return g
    return 'analytical report'


# ===================================================================== the compile prompt
#
# NOTE ON LEAKAGE: the worked example below is deliberately from a domain UNRELATED to any benchmark
# task (urban transit). Putting an AI/labour example here would hardcode task 72 through the back
# door -- the model would pattern-match the example instead of reading the question, and the
# generality this module exists to provide would be fake.

COMPILE_PROMPT = """You are compiling a RESEARCH CONTRACT from a research question. The contract is the ONLY
thing a downstream research pipeline will be told about this topic: if a requirement is not in the
contract, the pipeline cannot honour it.

THE QUESTION (verbatim):
---
{question}
---

Return ONE JSON object with exactly these fields:

{{
 "genre": "the artifact the question asks for -- e.g. literature review / policy brief / comparative
           analysis / analytical report with recommendations / clinical guidance. Read the question.",
 "genre_rules": ["3-6 obligations that genre imposes on the writer, e.g. for a literature review:
                  'synthesise published work rather than present new empirical findings'"],
 "review_subject": "the subject of the artifact as a noun phrase, <=12 words, no verb",
 "title": "an academic title for the artifact",

 "core_concepts": [{{"key":"snake_case","label":"the concept","aliases":["surface forms a paper
                     would actually use, lowercase, 3-8 of them"]}}],

 "framing_devices": [{{"key":"snake_case","label":"a LENS THE QUESTION EXPLICITLY IMPOSES on the
                       analysis (a comparison it demands, a context it names, a frame it requires).
                       If the question names one, it is graded. If it names none, return [].",
                       "aliases":["..."], "why":"what the question obliges you to do with it"}}],

 "subject_axis": {{"name":"the name of the axis the question asks you to vary the analysis ACROSS --
                    e.g. Industry, Disease stage, Intervention type, Jurisdiction, Population group.
                    Choose the ONE axis the question actually demands breadth on.",
                   "values":[{{"key":"snake_case","label":"...","aliases":["..."]}}]}},

 "outcome_dimensions": [{{"key":"snake_case","label":"an OUTCOME the question asks about -- the
                          things that get measured or affected","aliases":["..."]}}],

 "geographies": ["geographies the question scopes to, or [] if unscoped"],
 "time_horizons": ["the time horizons over which effects must be distinguished, e.g. short-run /
                   long-run, or acute / chronic. 2-4 items."],
 "method_designs": ["the STUDY DESIGNS that would count as evidence in THIS field, e.g.
                    randomized-trial / cohort / quasi-experimental / observational / survey /
                    case-law analysis / simulation / theory / review. 4-7 items."],
 "unit_levels": ["the UNITS OF ANALYSIS results in this field are reported at, from most granular to
                 least, e.g. task/worker/firm/economy or cell/patient/clinic/health-system. 4-7."],

 "required_contrasts": [{{"key":"snake_case","label":"a tension the artifact is OBLIGED to draw",
                          "a":"one side","b":"the other side","why":"why the question demands it"}}],

 "source_policy": {{"peer_reviewed_only": true/false,
                   "languages": ["English"] or [],
                   "excluded_types": ["source types the question forbids"],
                   "quality_bar": "the quality wording the question uses, or \\"\\"",
                   "recency_from": 2015 or null,
                   "question_evidence": ["FOR EACH constraint above, the clause of THE QUESTION that
                     imposes it, COPIED VERBATIM. If you cannot copy a clause, the constraint is not
                     in the question and MUST NOT be asserted."]}},

 "facets": [{{"key":"snake_case","label":"a facet a miner must harvest from every source",
              "probe":"the question to ask of each paper","priority":1|2|3,
              "serves":"which contract element this feeds"}}],

 "evidence_tuple": ["the fields that make a finding INTERPRETABLE in this field -- typically effect,
                    unit, population, design, scope, uncertainty. Adapt to the field."]
}}

RULES
- DERIVE EVERYTHING FROM THE QUESTION. Do not import a template from another topic.
- If the question names a framing device ("as a key driver of X", "in the context of Y", "under
  condition Z"), that is GRADED. Put it in framing_devices and give it a facet.
- subject_axis: 5-9 values, and they must be the ones a literature in THIS field would actually be
  organised by. If the question demands breadth across nothing, return values: [].
- outcome_dimensions: 4-8. These are the columns of a coverage matrix; they must be distinct.
- aliases: THE WORDS PAPERS IN THIS FIELD ACTUALLY PRINT. A deterministic lexical matcher looks for
  these in the VERBATIM TEXT of journal articles, so give SURFACE FORMS, not restatements of the
  concept. Include: single words as well as phrases; the field's technical vocabulary; the terms the
  SEMINAL papers on this topic use; spelling variants (including British spellings). 6-12 per entry,
  lowercase, no punctuation. Prefer words that separate this entry from its SIBLINGS -- a word shared
  by every entry (like "job" across several outcome dimensions) routes nothing and is discarded.
  A concept whose aliases do not literally occur in real papers is INVISIBLE to the pipeline.
- source_policy.question_evidence MUST be verbatim substrings of the question. A constraint whose
  clause you cannot quote is DROPPED downstream.

WORKED EXAMPLE OF THE SHAPE (a different topic entirely -- do not copy its content):
  question: "Assess how bus rapid transit affects commuter outcomes in Latin American cities."
  genre: "analytical report"; review_subject: "bus rapid transit and commuter outcomes"
  subject_axis: {{"name":"City","values":[{{"key":"bogota","label":"Bogota","aliases":["bogota","transmilenio"]}}, ...]}}
  outcome_dimensions: [{{"key":"travel_time","label":"Travel time","aliases":["commute time","journey time"]}}, ...]
  framing_devices: []  (the question imposes no explicit lens)

Return ONLY the JSON object."""


# ===================================================================== compile

def _llm(prompt: str, max_tokens: int = 8192) -> str:
    """The composer's LLM helper. Imported LAZILY so that a future `import research_contract` at the
    top of cellcog_composer.py cannot create a circular import at module load."""
    from cellcog_composer import llm
    return llm(prompt, max_tokens=max_tokens)


def _jparse(s: str):
    from cellcog_composer import jparse
    return jparse(s)


def _dedup(xs) -> list:
    out, seen = [], set()
    for x in xs:
        k = x.lower().strip() if isinstance(x, str) else str(x)
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip() if isinstance(x, str) else x)
    return out


_STOP = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'have', 'has', 'are', 'its', 'their',
         'other', 'various', 'such', 'these', 'those', 'more', 'most', 'also', 'into', 'across'}


def _terms(raw, cap: int = 32) -> list[Term]:
    """Sanitise LLM-supplied terms into a deterministic matcher vocabulary."""
    out = []
    for d in (raw or [])[:cap]:
        if not isinstance(d, dict):
            continue
        label = (d.get('label') or '').strip()
        if not label:
            continue
        key = (d.get('key') or re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_'))[:48]
        al = [re.sub(r'\s+', ' ', str(a).lower().strip()) for a in (d.get('aliases') or [])]
        al = [a for a in al if len(a) >= 3 and a not in _STOP]
        # the label is always a surface form of itself
        al = _dedup([label.lower()] + al)
        out.append(Term(key=key, label=label, aliases=al))
    return out


def _key(question: str, model: str) -> str:
    h = hashlib.sha256(f'{PROMPT_VERSION}\x00{model}\x00{question}'.encode()).hexdigest()[:16]
    return h


def compile_contract(question: str, question_id: int | None = None, *, use_llm: bool = True,
                     force: bool = False, verbose: bool = True) -> Contract:
    """Question -> Contract. ONE LLM call, cached. The regex floor is applied AFTER the model, so the
    model can enrich the source policy but cannot weaken it."""
    import os
    model = os.getenv('PG_GENERATOR_MODEL', 'z-ai/glm-5.2') if use_llm else 'none'
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f'{_key(question, model)}.json'
    if path.exists() and not force:
        if verbose:
            print(f'  [contract] cache hit {path.name}', file=sys.stderr)
        return Contract.from_dict(json.loads(path.read_text()))

    warnings: list[str] = []
    d: dict = {}
    if use_llm:
        raw = _llm(COMPILE_PROMPT.format(question=question.strip()))
        d = _jparse(raw) or {}
        if not isinstance(d, dict) or not d:
            warnings.append('LLM returned no parsable contract; fell back to the regex floor')
            d = {}

    # ---- source policy: MODEL PROPOSES, QUESTION DISPOSES, FLOOR IS NON-NEGOTIABLE -------------
    floor = _floor_source_policy(question)
    sp_raw = d.get('source_policy') or {}
    qnorm = re.sub(r'\s+', ' ', question.lower())
    kept_ev, dropped_ev = [], []
    for ev in (sp_raw.get('question_evidence') or []):
        if isinstance(ev, str) and re.sub(r'\s+', ' ', ev.lower().strip()) in qnorm:
            kept_ev.append(ev.strip())
        elif ev:
            dropped_ev.append(str(ev)[:60])
    if dropped_ev:
        warnings.append(f'{len(dropped_ev)} source-constraint quote(s) were NOT verbatim in the '
                        f'question and were dropped: {dropped_ev[:2]}')

    # ---- PER-CONSTRAINT ENTAILMENT. THE HOLE I ALREADY DUG ONCE, IN A NEW PLACE. -----------------
    # This block first read `... if kept_ev`, i.e. a constraint was admitted whenever ANY OTHER
    # constraint had produced a verbatim quote. On task 72 the model asserted `recency_from: 2015`;
    # the question contains no year at all; and it was ADMITTED, because the quote for the
    # journal-only rule had verified. A claim validated by the evidence for a DIFFERENT claim is the
    # evidence-laundering shape, and it would have silently deleted Autor 2003, Bresnahan 2002 and
    # Frey and Osborne 2017 -- the seminal literature -- from our own corpus.
    #
    # EVERY CONSTRAINT NOW CARRIES ITS OWN PROOF, CHECKED AGAINST THE QUESTION ITSELF.
    def _asks_peer_review() -> bool:
        return bool(re.search(_FLOOR[0][0], question, re.I))

    langs = list(floor.languages)
    for l in (sp_raw.get('languages') or []):
        if isinstance(l, str) and re.search(rf'\b{re.escape(l)}\b', question, re.I) and l not in langs:
            langs.append(l)          # a language is admitted only if the question NAMES it

    qb = floor.quality_bar
    if not qb:
        cand = (sp_raw.get('quality_bar') or '').strip()
        if cand and re.sub(r'[-\s]+', ' ', cand.lower()) in re.sub(r'[-\s]+', ' ', qnorm):
            qb = cand                # a quality bar is admitted only if its wording is IN the question

    rec = floor.recency_from
    if rec is None:
        cand = sp_raw.get('recency_from')
        if isinstance(cand, int) and str(cand) in question:
            rec = cand               # a cutoff year is admitted only if THAT YEAR is in the question
        elif cand:
            warnings.append(f'DROPPED fabricated recency cutoff {cand}: the question names no year. '
                            f'It would have deleted every pre-{cand} paper in the corpus.')

    sp = SourcePolicy(
        peer_reviewed_only=bool(floor.peer_reviewed_only or
                                (sp_raw.get('peer_reviewed_only') and _asks_peer_review())),
        languages=_dedup(langs),
        # excluded_types are ENTAILMENTS of the journal-only rule, not assertions about the question.
        # Over-excluding cannot fabricate; it can only narrow the corpus, which is the requested
        # direction. So the model may add to this list freely.
        excluded_types=_dedup(list(floor.excluded_types) + list(sp_raw.get('excluded_types') or [])),
        quality_bar=qb,
        recency_from=rec,
        question_evidence=_dedup(list(floor.question_evidence) + kept_ev),
    )
    if sp.peer_reviewed_only and not sp.excluded_types:
        sp.excluded_types = list(_EXCLUDE_IF_PEER_REVIEWED)

    # ---- the rest ------------------------------------------------------------------------------
    ax = d.get('subject_axis') or {}
    contrasts = []
    for x in (d.get('required_contrasts') or [])[:8]:
        if isinstance(x, dict) and x.get('label'):
            contrasts.append(Contrast(
                key=(x.get('key') or re.sub(r'[^a-z0-9]+', '_', x['label'].lower()))[:48],
                label=x['label'], a=str(x.get('a') or ''), b=str(x.get('b') or ''),
                why=str(x.get('why') or '')))
    facets = []
    for x in (d.get('facets') or [])[:14]:
        if isinstance(x, dict) and x.get('label'):
            facets.append(Facet(
                key=(x.get('key') or re.sub(r'[^a-z0-9]+', '_', x['label'].lower()))[:48],
                label=x['label'], probe=str(x.get('probe') or x['label']),
                priority=int(x.get('priority') or 2), serves=str(x.get('serves') or '')))

    c = Contract(
        question=question.strip(),
        question_id=question_id,
        genre=(d.get('genre') or _floor_genre(question)).strip(),
        genre_rules=_dedup([str(x) for x in (d.get('genre_rules') or [])])[:8],
        review_subject=(d.get('review_subject') or '').strip(),
        title=(d.get('title') or '').strip(),
        core_concepts=_terms(d.get('core_concepts')),
        framing_devices=_terms(d.get('framing_devices')),
        subject_axis=Axis(name=(ax.get('name') or 'Subpopulation').strip(),
                          values=_terms(ax.get('values'), cap=12)),
        outcome_dimensions=_terms(d.get('outcome_dimensions'), cap=10),
        geographies=_dedup([str(x) for x in (d.get('geographies') or [])])[:8],
        time_horizons=_dedup([str(x) for x in (d.get('time_horizons') or [])])[:5],
        method_designs=_dedup([str(x).lower() for x in (d.get('method_designs') or [])])[:8],
        unit_levels=_dedup([str(x).lower() for x in (d.get('unit_levels') or [])])[:8],
        required_contrasts=contrasts,
        source_policy=sp,
        facets=facets,
        evidence_tuple=_dedup([str(x).lower() for x in (d.get('evidence_tuple') or [])]) or
                       ['effect', 'unit', 'population', 'design', 'scope', 'uncertainty'],
        compiled_by=f'{PROMPT_VERSION}/{model}',
        warnings=warnings,
    )

    # ---- degraded, offline contract: still usable, and honest about what it is ------------------
    if not c.review_subject:
        c.review_subject = _fallback_subject(question)
        c.warnings.append('review_subject derived by regex (no LLM)')
    if not c.title:
        c.title = c.review_subject[:1].upper() + c.review_subject[1:]
    if not c.outcome_dimensions:
        c.warnings.append('NO OUTCOME DIMENSIONS: the coverage matrix will have no columns')
    if not c.subject_axis.values:
        c.warnings.append(f'NO {c.subject_axis.name.upper()} VALUES: the matrix collapses to the '
                          f'cross-cutting row -- the question may simply not demand breadth on an axis')
    if not c.facets:
        c.warnings.append('NO FACETS: the miner has nothing question-specific to harvest')

    path.write_text(c.to_json())
    if verbose:
        print(f'  [contract] compiled -> {path}', file=sys.stderr)
    return c


def _fallback_subject(q: str) -> str:
    m = re.search(r'(?:literature review|review|analysis|report|brief)\s+(?:on|of|about)\s+(.{5,90}?)[.,;]', q, re.I)
    if m:
        return m.group(1).strip()
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", q) if w.lower() not in _STOP]
    return ' '.join(words[:10])


# ===================================================================== the matcher
#
# Deterministic. ROUTES ON THE SPAN AND THE TITLE ONLY -- both are SOURCE-AUTHORED. `claim` is
# model-authored (the extract prompt says "state the finding IN YOUR WORDS") and is a display cache;
# routing a card by its claim would let the model's paraphrase decide which cell its own evidence
# lands in, which is the same self-validation loop that shipped a fabricated figure.

from synthesis_contract import _stem  # noqa: E402  (one stemmer in the repo, not two)

# Words that appear in every research paper ever written and therefore route nothing. Without this,
# "effect" -- a stem of the dimension "Wage effects" -- would match every span in the corpus.
_GENERIC = {
    'effect', 'effects', 'impact', 'impacts', 'result', 'results', 'finding', 'findings', 'study',
    'studies', 'evidence', 'analysis', 'research', 'paper', 'article', 'data', 'model', 'models',
    'change', 'changes', 'level', 'levels', 'rate', 'rates', 'factor', 'factors', 'outcome',
    'outcomes', 'significant', 'increase', 'decrease', 'high', 'low', 'large', 'small', 'new',
    'different', 'various', 'related', 'associated', 'measure', 'measures', 'estimate', 'estimates',
    'approach', 'method', 'methods', 'framework', 'literature', 'review', 'context', 'role',
}


@dataclass
class TermMatcher:
    key: str
    phrases: list[str]          # multi-word surface forms: matched verbatim
    disc: set[str]              # stems UNIQUE to this term within its family -> a CONFIDENT route
    shared: set[str] = field(default_factory=set)   # stems a SIBLING also claims -> AMBIGUOUS, not dead
    vocab: set[str] = field(default_factory=set)    # its whole definition (disc | shared): stage-2 evidence
    label: str = ''


def build_matchers(family: list[Term]) -> tuple[dict[str, TermMatcher], list[str]]:
    """A term matches a span if the span contains one of its PHRASES verbatim, or one of its
    DISCRIMINATIVE stems. A stem it SHARES with a sibling makes the span AN AMBIGUOUS CANDIDATE FOR
    BOTH -- and ambiguity is resolved in a second stage, NOT by throwing the word away.

    WHY NOT JUST LOOK FOR THE ALIASES. The aliases are the compound noun phrases the CONTRACT speaks
    in ("job displacement", "wage effects"); the corpus is academic prose that says "computerisation",
    "wages and educational attainment", "substitute for labor". Exact-phrase matching routed 125 of
    133 real cards to NO CELL AT ALL -- a matcher artifact that prints as a corpus covering nothing,
    and is indistinguishable, in the output, from a genuine evidence gap. Manufacturing a false
    evidence gap is the exact failure this module exists to prevent, so the matcher may not do it.

    WHY DISCRIMINATIVE. Backing off to every content word makes "job" -- which occurs in three of
    task 72's five outcome dimensions -- match everything, and every card lands in every cell. A word
    earns the right to route a card ON ITS OWN only if it separates ONE term from its siblings.

    AND WHY A DROPPED STEM WAS A BUG, NOT A TRADE-OFF. `disc = {s for s in stems if df[s] == 1}`
    DELETED every stem two terms shared, so the dimension "Wages" -- whose entire vocabulary is the
    word `wage`, shared with "Wage inequality" -- ended up with NO vocabulary at all and COULD NOT
    MATCH THE WORD "WAGE". Every wage card in the corpus went unrouted, and its cell printed as an
    EVIDENCE GAP: the review would have reported that the literature it holds says nothing about
    wages, over a corpus full of wage results. The fix is NOT to special-case `wage` (that is a
    task-72 regex wearing a fix's clothes). A shared stem is not noise and it is not decisive: it is
    AMBIGUOUS, and it is kept, in `shared`, for `route_terms()` to resolve against the contract's own
    definitions and the span's own context.
    """
    stems: dict[str, set[str]] = {}
    phrases: dict[str, list[str]] = {}
    for t in family:
        forms = [t.label.lower()] + [a.lower() for a in t.aliases]
        phrases[t.key] = sorted({f for f in forms if ' ' in f and len(f) >= 6}, key=len, reverse=True)
        ws = {w for f in forms for w in re.findall(r'[a-z]{4,}', f)}
        stems[t.key] = {_stem(w) for w in ws if w not in _STOP and w not in _GENERIC} - _GENERIC

    df: dict[str, int] = {}
    for ss in stems.values():
        for s in ss:
            df[s] = df.get(s, 0) + 1

    out, warn = {}, []
    for t in family:
        disc = {s for s in stems[t.key] if df[s] == 1}
        shared = stems[t.key] - disc
        if not disc and not phrases[t.key] and not shared:
            # NOW this warning means what it says: the term has no vocabulary AT ALL. It no longer
            # fires for a term whose every word is shared -- that term routes through stage 2.
            warn.append(f'term "{t.label}" has no vocabulary of any kind -- it can never route a card')
        out[t.key] = TermMatcher(key=t.key, phrases=phrases[t.key], disc=disc, shared=shared,
                                 vocab=stems[t.key], label=t.label)
    return out, warn


def _card_text(card: dict, corpus_titles: dict | None = None) -> str:
    """THE SOURCE-AUTHORED TEXT OF A CARD. The span is the evidence; the title is Crossref metadata.
    Neither is written by the model, so neither can launder a routing decision."""
    span = card.get('span') or ''
    title = corpus_titles.get(card.get('doi'), '') if corpus_titles else ''
    return re.sub(r'\s+', ' ', f'{title} {span}').lower()


def route_terms(matchers: dict[str, TermMatcher], blob: str) -> tuple[list[str], list[str]]:
    """TWO STAGES. Returns (confidently routed keys, AMBIGUOUS keys).

    STAGE 1 — DECISIVE EVIDENCE. A verbatim phrase, or a stem no sibling claims. This is the old
    `_hits()`, unchanged, and it still does most of the work.

    STAGE 2 — THE AMBIGUOUS CANDIDATE SET. A stem two terms share ("wage", in both `Wages` and `Wage
    inequality`) does not route on its own and IS NOT DISCARDED. It nominates every term that claims
    it, and those terms then COMPETE on the evidence actually present: how much of each term's own
    contract definition the span contains. `hourly wages fell 0.2 percent` contains all of the
    definition of `Wages` and half of `Wage inequality`, so it is Wages. `wage inequality rose`
    carries `inequality`, which is decisive, so stage 1 has already answered and the shared `wage` is
    EXPLAINED -- it does not also route the span to `Wages`.

    NO WINNER -> AMBIGUOUS. Not a gap, not a silent drop, not a coin flip. The card belongs SOMEWHERE
    in this family and we cannot say where, and the cells it might belong to may not close or declare
    an absence until it is resolved.
    """
    blob_stems = {_stem(w) for w in re.findall(r'[a-z]{4,}', blob)}
    confident: list[str] = []
    candidates: dict[str, set[str]] = {}
    for k, m in matchers.items():
        if (m.disc & blob_stems) or any(p in blob for p in m.phrases):
            confident.append(k)
            continue
        hit = m.shared & blob_stems
        if hit:
            candidates[k] = hit

    # A sibling that ALREADY won on its own decisive evidence explains the shared stem. The span said
    # "wage inequality"; it is not also a bare wage-level finding.
    for k in list(candidates):
        if any(matchers[c].vocab & candidates[k] for c in confident):
            del candidates[k]
    if not candidates:
        return confident, []

    # THE SEMANTIC SECOND STAGE: the contract's definitions, scored against the span's own words.
    scores: dict[str, tuple] = {}
    for k, _hit in candidates.items():
        m = matchers[k]
        covered = len(m.vocab & blob_stems) / max(1, len(m.vocab))   # how much of ITS meaning is here
        scores[k] = (round(covered, 6), len(m.vocab & blob_stems))
    best = max(scores.values())
    winners = [k for k, s in scores.items() if s == best]
    if len(winners) == 1 and best[0] > 0:
        return confident + winners, []
    return confident, sorted(candidates)          # a tie is AMBIGUOUS. It is never broken by guessing.


def _hits(matchers: dict[str, TermMatcher], blob: str) -> list[str]:
    """Back-compat shim: the confidently-routed keys only. Anything that needs to know about
    ambiguity must call route_terms() -- a caller that cannot see an ambiguity will report it as a gap.
    """
    return route_terms(matchers, blob)[0]


_YEAR = re.compile(r'\b(?:1[89]|20)\d\d\b')
_VERSIONISH = re.compile(r'\b[A-Z][A-Za-z&.]*\s+\d\.\d\b')
_RESULT_VERB = re.compile(
    r'\b(found|find|finds|show|shows|showed|report|reports|reported|demonstrat\w+|associat\w+|'
    r'increas\w+|decreas\w+|declin\w+|rose|fell|higher|lower|greater|reduc\w+|improv\w+|'
    r'no (?:significant )?(?:effect|difference|association)|estimate[sd]?|significant\w*)\b', re.I)


def has_verified_figure(card: dict) -> bool:
    """A quantitative result, verified AGAINST THE SPAN -- not against `has_number`, which the
    extractor computed from the MODEL-WRITTEN claim (cellcog_composer.py:223)."""
    span = card.get('span') or ''
    t = _YEAR.sub(' ', _VERSIONISH.sub(' ', span))
    return bool(re.search(r'\d+(?:\.\d+)?\s*(?:percent|%|percentage points?|pp)\b|\b\d+\.\d+\b|\b\d{2,}\b', t))


def has_direct_result(card: dict) -> bool:
    """Does this card STATE SOMETHING the source found/held/recommended, rather than name a topic?

    A TYPED EVIDENCE ACT IS ALWAYS A RESULT OF ITS TYPE. If the card carries an `act`, it has already
    been through that act's required-field rule in the miner's registry gate, against the verbatim
    span: a `doctrinal_holding_or_rule` HAS a holding and an authority, or it would not exist.

    THIS BRANCH IS LOAD-BEARING AND IT WAS MISSING. The fallback below is `_RESULT_VERB`, and a
    judicial holding contains no result verb -- "the employer bears the burden of proving that the
    system is job-related" has no `found`, no `showed`, no `increased`. So the miner would mine the
    opinion, the gate would admit the holding, the card would be bound and correct -- and the coverage
    matrix would score the cell `0 results` and refuse to close it. The evidence would have been
    rescued at the extractor and thrown away at the matrix, which is exactly the shape of every defect
    in this project's history: a repair that stops one component short of the thing that ships.

    The fallback remains for LEGACY, untyped cards, and it is a heuristic, and it is labelled as one.
    It decides COVERAGE, never faithfulness.
    """
    if (card.get('act') or '').strip():
        return True
    return bool(_RESULT_VERB.search(card.get('span') or ''))


# ===================================================================== the coverage matrix

CLOSED, THIN, GAP = 'CLOSED', 'THIN', 'GAP'

#: A FACT ABOUT OUR PIPELINE. NEVER A FACT ABOUT THE LITERATURE.
#: An UNROUTED / UNSEARCHED / SEARCH_FAILED cell is one WE NEVER LOOKED IN, or looked in and the look
#: failed. It has exactly nothing to say about what the field contains, and the one thing it may never
#: do is print as an evidence gap. `GAP` now requires a LEDGER that says SEARCHED_NONE.
LIMITATION = 'LIMITATION'

#: Cards that MIGHT belong to this cell could not be assigned to it or to a sibling. Sol: "Unresolved
#: -> AMBIGUOUS/UNROUTED, NEVER GAP. Coverage cannot close or declare absence while relevant cards
#: remain unrouted." So the cell does neither.
UNRESOLVED = 'UNRESOLVED'

CROSS = Term(key='__cross__', label='Cross-cutting / not specific to one {axis}', aliases=[])


def evidence_unit_of(card: dict, graph=None) -> tuple[str, bool]:
    """(the INDEPENDENT EVIDENCE-UNIT FAMILY this card belongs to, is_bound).

    A family is a STUDY, a DECISION, a TRIAL -- never a document and never a DOI.

      scientific / clinical : distinct STUDIES or TRIALS. The NBER working paper and the JPE article
                              are TWO EXPRESSIONS OF ONE STUDY, and they are ONE unit. 0.37 vs 0.2 is
                              what PEER REVIEW DID TO A NUMBER -- it is A VERSION CHANGE, and it is
                              never cross-study corroboration and never a literature conflict.
      legal                 : distinct DECISIONS. Two reporters printing one judgment are ONE unit;
                              the appellate and the lower-court opinions are SEPARATE units (they are
                              separate decisions, and related authority), which falls out for free
                              because the graph models them as separate works.

    `len(dois)` gets every one of those wrong, in the direction that INFLATES the count -- and an
    inflated count is what closes a cell.
    """
    u = card.get('evidence_unit_id') or card.get('work_id')
    if u:
        return u, True
    if graph is not None:
        mid = card.get('manifestation_id')
        m = getattr(graph, 'manifestations', {}).get(mid) if mid else None
        if m is not None:
            return m.work_id, True

    # UNBOUND: the card names a DOI and NOTHING THAT RESOLVES TO BYTES. It gets NO FAMILY.
    #
    # It would be so easy to fall back to the DOI here — the card is not lost, and the count still
    # works. THAT FALLBACK IS THE ATTACK. Hand the matrix a working-paper card and a journal-article
    # card of ONE STUDY, each with its own DOI and no binding, and `doi:` families count TWO
    # independent works and CLOSE THE CELL on one piece of evidence. The adversary's attack 4 does
    # exactly this, and it still succeeded against the first version of this function.
    #
    # A DOI names a WORK and a work has no bytes. It cannot tell two studies from two versions of one,
    # so it cannot be an evidence unit, so an unbound card counts toward NOTHING. It is kept, reported
    # (Cell.unbound, Matrix.unbound) and it BLOCKS the cell from closing or denying — because evidence
    # we hold and cannot ground is not evidence of absence either.
    return '', False


@dataclass
class Cell:
    row: str            # axis value key ('__cross__' for evidence that is not axis-specific)
    row_label: str
    col: str            # outcome dimension key
    col_label: str
    card_ids: list[str] = field(default_factory=list)
    dois: list[str] = field(default_factory=list)
    families: list[str] = field(default_factory=list)    # DISTINCT EVIDENCE UNITS — what n_works counts
    unbound: list[str] = field(default_factory=list)     # card ids with no binding to any manifestation
    ambiguous: list[str] = field(default_factory=list)   # cards that MAY belong here; unresolved
    methods: list[str] = field(default_factory=list)
    n_quant: int = 0
    n_qual: int = 0
    status: str = LIMITATION
    reason: str = ''
    coverage_status: str = ''      # the LEDGER's verdict (event_ledger.derive_coverage_status)
    absence_licensed: bool = False  # may a scoped absence sentence be written off this cell?

    @property
    def n_works(self) -> int:
        """DISTINCT INDEPENDENT EVIDENCE-UNIT FAMILIES. This was `len(self.dois)`."""
        return len(self.families)


@dataclass
class Matrix:
    axis_name: str
    rows: list[Term]
    cols: list[Term]
    cells: dict[tuple[str, str], Cell]
    unrouted: list[str] = field(default_factory=list)   # cards no cell claimed
    ambiguous: list[str] = field(default_factory=list)  # cards a matcher could not disambiguate
    unbound: list[str] = field(default_factory=list)    # cards with no binding — they may not close a cell
    has_ledger: bool = False

    def cell(self, r: str, c: str) -> Cell:
        return self.cells[(r, c)]

    def by_status(self, s: str) -> list[Cell]:
        return [x for x in self.cells.values() if x.status == s]

    def closable_rows(self) -> list[Term]:
        """Rows the corpus CAN actually support. THE OUTLINE MAY ONLY PROMISE THESE.

        Task 72's hand-written outline promised a four-subsection industry section over a corpus with
        retail=0 and education=1. Two criteria regressed for it (w=.0725 and w=.0375). A row with no
        closed cell does not get a subsection; it gets a line in the evidence-gap section."""
        ok = {c.row for c in self.cells.values() if c.status in (CLOSED, THIN)}
        return [r for r in self.rows if r.key in ok]

    def gap_rows(self) -> list[Term]:
        """Rows we may say the reviewed literature is SILENT on.

        THIS IS AN ABSENCE CLAIM AND IT NOW REQUIRES A LICENCE. A row is only here if EVERY cell in it
        is a LICENSED gap — i.e. the ledger says we planned a route, every adapter genuinely answered,
        and nothing came back. A row full of LIMITATION cells (never routed, never searched, or the
        search failed) is NOT a gap row: we do not know what is there, and saying we do was the lie.
        """
        out = []
        for r in self.rows:
            if r.key == CROSS.key:
                continue
            mine = [c for c in self.cells.values() if c.row == r.key]
            if mine and all(c.status == GAP and c.absence_licensed for c in mine):
                out.append(r)
        return out

    def limitation_rows(self) -> list[Term]:
        """Rows we CANNOT SPEAK ABOUT AT ALL — a PIPELINE limitation, and it must be reported as one.
        These used to be printed as evidence gaps, which asserted a fact about the world out of a fact
        about our own plumbing."""
        out = []
        for r in self.rows:
            if r.key == CROSS.key:
                continue
            mine = [c for c in self.cells.values() if c.row == r.key]
            if mine and any(c.status == LIMITATION for c in mine) \
                    and not any(c.status in (CLOSED, THIN) for c in mine):
                out.append(r)
        return out


def coverage_matrix(contract: Contract, cards: list[dict],
                    corpus: list[dict] | None = None,
                    graph=None, ledger=None) -> Matrix:
    """cells = (subject axis x outcome dimension). IT CONSUMES BOTH THE GRAPH AND THE LEDGER.

    THE GRAPH says what an independent unit of evidence IS (a study, a decision, a trial — not a DOI),
    so a cell can be counted. THE LEDGER says whether we ever actually looked, so a cell can be allowed
    — or forbidden — to say the literature is silent.

    A cell CLOSES on the evidence we HOLD: >=2 independent evidence-unit families, >=1 result, and a
    methodological contrast where material. That is a POSITIVE claim and the cards license it.
    A cell may only declare an ABSENCE with a ledger that says SEARCHED_NONE. Without one it is a
    LIMITATION — a fact about this pipeline — and it says so.
    """
    titles = {c['doi']: c.get('title', '') for c in (corpus or []) if c.get('doi')}
    cross = Term(key=CROSS.key,
                 label=f'Cross-cutting / not specific to one {contract.subject_axis.name.lower()}',
                 aliases=[])
    rows = list(contract.subject_axis.values) + [cross]
    cols = list(contract.outcome_dimensions)

    row_m, w1 = build_matchers(contract.subject_axis.values)
    col_m, w2 = build_matchers(cols)
    for w in w1 + w2:
        if w not in contract.warnings:
            contract.warnings.append(w)

    cells: dict[tuple[str, str], Cell] = {
        (r.key, c.key): Cell(row=r.key, row_label=r.label, col=c.key, col_label=c.label)
        for r in rows for c in cols}

    unrouted: list[str] = []
    ambiguous_cards: list[str] = []
    unbound_cards: list[str] = []
    for card in cards:
        cid = card.get('id', '?')
        blob = _card_text(card, titles)
        hit_rows, amb_rows = route_terms(row_m, blob)
        hit_cols, amb_cols = route_terms(col_m, blob)
        family, bound = evidence_unit_of(card, graph)
        if not bound:
            unbound_cards.append(cid)

        # AN AMBIGUOUS CARD IS NOT A ROUTED CARD AND IT IS NOT A LOST ONE. It is registered against
        # every cell it MIGHT belong to, and those cells may then neither close nor deny.
        if amb_cols:
            ambiguous_cards.append(cid)
            for ck in amb_cols:
                for rk in (hit_rows or amb_rows or [CROSS.key]):
                    if (rk, ck) in cells:
                        cells[(rk, ck)].ambiguous.append(cid)
        if not hit_cols:
            if not amb_cols:
                unrouted.append(cid)
            continue
        # evidence that names no axis value is CROSS-CUTTING, not lost. Most of the strongest work in
        # any field is economy-wide / population-wide; a matrix that discards it would look empty and
        # would lie about the corpus.
        if not hit_rows:
            if amb_rows:
                ambiguous_cards.append(cid) if cid not in ambiguous_cards else None
                for rk in amb_rows:
                    for ck in hit_cols:
                        cells[(rk, ck)].ambiguous.append(cid)
                continue
            hit_rows = [CROSS.key]
        for rk in hit_rows:
            for ck in hit_cols:
                cell = cells[(rk, ck)]
                cell.card_ids.append(cid)
                doi = card.get('doi') or ''
                if doi and doi not in cell.dois:
                    cell.dois.append(doi)
                # THE COUNT THAT CLOSES THE CELL. Distinct STUDIES, not distinct DOIs — and an UNBOUND
                # card contributes NO unit at all, so it can never close anything.
                if bound and family and family not in cell.families:
                    cell.families.append(family)
                if not bound and cid not in cell.unbound:
                    cell.unbound.append(cid)
                m = (card.get('method') or '').strip().lower()
                if m and m not in cell.methods:
                    cell.methods.append(m)
                if has_verified_figure(card):
                    cell.n_quant += 1
                elif has_direct_result(card):
                    cell.n_qual += 1

    for cell in cells.values():
        _close(cell, contract, ledger)

    return Matrix(axis_name=contract.subject_axis.name, rows=rows, cols=cols, cells=cells,
                  unrouted=unrouted, ambiguous=sorted(set(ambiguous_cards)),
                  unbound=unbound_cards, has_ledger=ledger is not None)


def _ledger_status(cell: Cell, ledger) -> tuple[str, str]:
    """(coverage status, reason) from event_ledger.derive_coverage_status — THE ONLY FUNCTION THAT MAY
    LICENSE AN ABSENCE. With no ledger the answer is UNROUTED: we recorded no search, so we know
    nothing, and 'we know nothing' is never 'there is nothing'."""
    if ledger is None:
        return 'UNROUTED', ('no ledger: this pipeline recorded no search for this cell, so it cannot '
                            'know whether the literature is silent or whether we never looked')
    import event_ledger as EL          # deferred: keeps this module importable without the ledger
    st, info = EL.derive_coverage_status(ledger, f'{cell.row}:{cell.col}')
    return st, info.get('reason', '')


def _close(cell: Cell, contract: Contract, ledger=None) -> None:
    results = cell.n_quant + cell.n_qual
    # "methodological contrast where material": with only a couple of works, demanding two designs is
    # not a standard the literature can meet, so it is not material. Above the threshold it is.
    material = cell.n_works >= METHOD_CONTRAST_MATERIAL_AT and len(contract.method_designs) >= 2

    # ---- 1. A POSITIVE CLAIM, licensed by the cards we HOLD. No ledger is needed to say what we have,
    #         and an unplaceable card cannot UN-say it: routing an ambiguous card INTO a cell that
    #         already stands on its own confident evidence could only make the cell stronger. So the
    #         ambiguity is RECORDED here rather than used to destroy a close — evidence we could not
    #         place is a fact we must publish, not a reason to delete evidence we could.
    if cell.n_works >= MIN_WORKS_PER_CELL and results >= MIN_RESULTS_PER_CELL:
        notes = ''
        if cell.unbound:
            notes += (f' [{len(cell.unbound)} further card(s) here are NOT BOUND to any manifestation '
                      f'and were counted toward NOTHING — the cell closes without them]')
        if cell.ambiguous:
            notes += (f' [{len(cell.ambiguous)} further card(s) MAY belong here and could not be '
                      f'assigned — the cell closes on evidence that does not depend on them]')
        if material and len(cell.methods) < 2:
            cell.status = THIN
            cell.reason = (f'{cell.n_works} evidence units, {results} result(s), but a single design '
                           f'({cell.methods[0] if cell.methods else "?"}) -- narrate the design '
                           f'limitation{notes}')
        else:
            cell.status = CLOSED
            cell.reason = (f'{cell.n_works} independent evidence units, {cell.n_quant} quantitative + '
                           f'{cell.n_qual} qualitative result(s), {len(cell.methods)} design(s)'
                           f'{"" if material else " (design contrast not material at this depth)"}'
                           f'{notes}')
        return

    # ---- 2. THE CELL DOES NOT CLOSE. Everything from here is a claim ABOUT AN ABSENCE, and there are
    #         exactly two things that can license one — and an unrouted card forbids both.
    #
    #         AMBIGUITY FIRST. Sol: "Coverage cannot close or declare absence while relevant cards
    #         remain unrouted." Here it BITES: a card that might belong to this cell is a card that
    #         might CLOSE it, so we do not know that this cell is empty. Calling it an evidence gap is
    #         how a corpus full of wage results reported that the literature says nothing about wages.
    if cell.ambiguous or cell.unbound:
        cell.status = UNRESOLVED
        cell.absence_licensed = False
        bits = []
        if cell.ambiguous:
            bits.append(f'{len(cell.ambiguous)} card(s) could belong to this dimension or to a sibling '
                        f'and could not be assigned — one of them might be exactly this cell\'s '
                        f'evidence. An unrouted card is a MATCHER artifact, and printing it as an '
                        f'evidence gap asserts a fact about the literature out of a fact about a regex')
        if cell.unbound:
            bits.append(f'{len(cell.unbound)} card(s) here are NOT BOUND to a manifestation and cannot '
                        f'be counted as evidence units — a DOI names a WORK, and a work has no bytes, '
                        f'so it cannot tell two studies from two versions of one study')
        cell.reason = (f'{cell.n_works} groundable evidence unit(s). THIS CELL MAY NOT CLOSE AND MAY NOT '
                       f'DECLARE AN ABSENCE. ' + '; '.join(bits))
        return

    st, why = _ledger_status(cell, ledger)
    cell.coverage_status = st

    if st == 'SEARCHED_NONE':
        cell.status = GAP
        cell.absence_licensed = True
        cell.reason = (f'{cell.n_works} evidence unit(s), {results} result(s). THE SEARCH RAN AND CAME '
                       f'BACK EMPTY ({why}) -- a scoped absence MAY be stated, scoped to this corpus')
    elif st in ('THIN', 'CONFLICTED'):
        cell.status = THIN
        cell.absence_licensed = False
        cell.reason = (f'ledger says {st}: {why} -- the honest sentence is "THE LITERATURE DOES NOT '
                       f'SETTLE THIS", which is a correct answer, not a failure')
    else:
        # UNROUTED | UNSEARCHED | SEARCH_FAILED, and the no-ledger case.
        cell.status = LIMITATION
        cell.absence_licensed = False
        cell.reason = (f'{st}: {why}. THIS IS A PIPELINE LIMITATION AND MUST BE REPORTED AS ONE. It is '
                       f'NOT an evidence gap: we cannot say the literature is silent about something '
                       f'we never successfully looked for')


# ===================================================================== the outline

@dataclass
class Slot:
    """One subsection. THE SHARED ARGUMENT STATE the 28 independent generations never had.

    A slot is not a title -- it is an OBLIGATION: these cells, these cards, this contrast. The writer
    is told what it must close, and the allocator guarantees no other slot was handed the same
    evidence to say again."""
    section: str
    title: str
    kind: str                                  # scope|framing|concept|outcome|axis|contrast|gap|agenda
    cells: list[tuple[str, str]] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)   # every card eligible for this slot
    card_ids: list[str] = field(default_factory=list)     # what the allocator actually gave it
    must_do: str = ''
    evidence_status: str = ''


def _cells_of(matrix: Matrix | None, *, col: str | None = None, row: str | None = None,
              cols: set[str] | None = None) -> list[tuple[str, str]]:
    if not matrix:
        return []
    out = []
    for c in matrix.cells.values():
        if c.status not in (CLOSED, THIN):
            continue
        if col and c.col != col:
            continue
        if row and c.row != row:
            continue
        if cols is not None and c.col not in cols:
            continue
        out.append((c.row, c.col))
    return out


def _cands(matrix: Matrix | None, cells: list[tuple[str, str]]) -> list[str]:
    if not matrix:
        return []
    out = []
    for rc in cells:
        for cid in matrix.cells[rc].card_ids:
            if cid and cid not in out:
                out.append(cid)
    return out


def derive_outline(contract: Contract, matrix: Matrix | None = None,
                   cards: list[dict] | None = None) -> list[Slot]:
    """PURE FUNCTION. contract (+ what the corpus can actually cash) -> the outline.

    The genre picks the skeleton; the contract fills it; THE MATRIX VETOES ANY SUBSECTION THE CORPUS
    CANNOT SUPPORT. That veto is the whole point: an outline that promises what the corpus does not
    hold produces exactly the generic prose the judge scored 6.36 on critical synthesis."""
    slots: list[Slot] = []
    A = contract.subject_axis.name
    col_m, _ = build_matchers(contract.outcome_dimensions)

    # 1. SCOPE & METHODS -- the compliance narration. On a question graded "only cites high-quality
    #    journal articles", this EXPLAINS OUR COMPLIANCE TO THE GRADER, in prose that survives the
    #    cleaner. We currently say nothing.
    if contract.source_policy.compliance_prose():
        slots.append(Slot(
            section='Scope, Methods, and Source Selection',
            title='What this review admits as evidence, and what it excludes',
            kind='scope',
            must_do=contract.source_policy.compliance_prose(),
            evidence_status='contract'))
    if contract.core_concepts:
        slots.append(Slot(
            section='Scope, Methods, and Source Selection',
            title=f'What counts as {contract.review_subject}',
            kind='concept',
            must_do='Define the core concepts and state the boundary of the review: '
                    + ', '.join(t.label for t in contract.core_concepts[:6]),
            evidence_status='contract'))

    # 2. THE FRAMING DEVICE THE QUESTION IMPOSES. If the question names a lens, the lens is graded --
    #    and a lens dropped after paragraph one is a lens not used. The framing slot is given the
    #    cards that actually SPEAK to the lens, so it is not a paragraph of assertion.
    fd_m, _ = build_matchers(contract.framing_devices) if contract.framing_devices else ({}, [])
    for fd in contract.framing_devices:
        cand = []
        for c in (cards or []):
            if _hits({fd.key: fd_m[fd.key]}, _card_text(c)):
                cand.append(c.get('id'))
        slots.append(Slot(
            section=f'{fd.label}',
            title=f'How {fd.label} reframes {contract.review_subject}',
            kind='framing',
            candidates=[x for x in cand if x],
            must_do=f'Carry this framing THROUGH the review, not just in the introduction. Where a '
                    f'source itself invokes {fd.label}, say what it claims and whether the evidence '
                    f'bears it out.',
            evidence_status='evidence' if cand else 'contract'))

    # 3. OUTCOME DIMENSIONS -- one subsection per dimension the corpus can actually speak to.
    for col in contract.outcome_dimensions:
        cells = _cells_of(matrix, col=col.key)
        if matrix and not cells:
            continue
        slots.append(Slot(
            section='Evidence by Outcome Dimension',
            title=col.label,
            kind='outcome',
            cells=cells,
            candidates=_cands(matrix, cells),
            must_do=f'State what the evidence establishes about {col.label.lower()}, at what unit of '
                    f'analysis, over what horizon, and what it does not establish.',
            evidence_status='evidence'))

    # 4. THE SUBJECT AXIS -- ONLY the rows the corpus can cash.
    rows = matrix.closable_rows() if matrix else contract.subject_axis.values
    for r in rows:
        if r.key == CROSS.key:
            continue
        cells = _cells_of(matrix, row=r.key)
        slots.append(Slot(
            section=f'{_plural(A)}: Sector-Specific Evidence',
            title=r.label,
            kind='axis',
            cells=cells,
            candidates=_cands(matrix, cells),
            must_do=f'What does the evidence say specifically about {r.label}, and how does it differ '
                    f'from the cross-cutting picture?',
            evidence_status='evidence'))

    # 5. THE REQUIRED CONTRASTS -- the sentences that ARE critical synthesis, the joint-heaviest
    #    criterion on the board (w=0.0800). These slots used to be handed NO EVIDENCE AT ALL, which
    #    is how a "critical synthesis" section ends up 210 words long in an 8,012-word report: the
    #    writer had nothing to put in tension, so it wrote atmosphere. A contrast is routed to the
    #    OUTCOME DIMENSIONS ITS OWN TEXT NAMES, so both sides arrive with sources attached.
    for k in contract.required_contrasts:
        hit = set(_hits(col_m, f'{k.label} {k.a} {k.b}'.lower()))
        cells = _cells_of(matrix, cols=hit) if hit else []
        slots.append(Slot(
            section='Critical Synthesis',
            title=k.label,
            kind='contrast',
            cells=cells,
            candidates=_cands(matrix, cells),
            must_do=f'Put "{k.a}" and "{k.b}" in tension. Where they conflict, say WHY they can both '
                    f'be true (different unit of analysis? horizon? design?) and state what the '
                    f'evidence does NOT settle. {k.why}',
            evidence_status='evidence' if cells else 'UNGROUNDED'))

    # 6. THE EVIDENCE GAPS -- an HONEST CLOSE, and worth more than filler.
    #    NOTE THE SCOPE OF THE CLAIM. This says "the literature REVIEWED HERE does not cover X", not
    #    "the literature does not cover X". We hold 70 works; the field holds thousands. A gap in our
    #    corpus is a fact about our corpus. Overclaiming it as a fact about the field would be a
    #    fabrication with no source to check it against -- the worst kind.
    #
    #    AND IT IS NOW LICENSED. `by_status(GAP)` no longer means "few cards landed here": it means
    #    THE LEDGER SAYS WE SEARCHED AND FOUND NOTHING. A cell we never routed, never searched, or
    #    whose search returned 429 is a LIMITATION, and it gets the slot below instead — because the
    #    sentence "the literature does not cover X" and the sentence "we did not manage to look for X"
    #    are different sentences, and only one of them was true.
    if matrix:
        gaps = [c for c in matrix.by_status(GAP) if c.absence_licensed]
        gap_rows = matrix.gap_rows()
        if gaps:
            slots.append(Slot(
                section='Critical Synthesis',
                title='What the reviewed literature does not cover',
                kind='gap',
                cells=[],          # a gap slot cites NOTHING: that is what makes it a gap
                must_do=('State, SCOPED EXPLICITLY TO THE LITERATURE REVIEWED HERE (not to the field '
                         'at large), which combinations this review could not ground. THE SEARCH RAN '
                         'AND RETURNED NOTHING for each of these — that is what licenses the sentence. '
                         'Name them: ' +
                         '; '.join(f'{c.row_label} x {c.col_label}' for c in gaps[:8]) +
                         (f'. {_plural(A)} with no groundable evidence anywhere in the reviewed '
                          f'corpus: ' + ', '.join(r.label for r in gap_rows) if gap_rows else '') +
                         '. Do NOT fill these with generic prose -- the explicit gap IS the finding, '
                         'and it is worth more than filler.'),
                evidence_status='gap'))

        # 6b. THE PIPELINE LIMITATIONS. NOT an evidence gap, and it may NEVER be written as one.
        lims = matrix.by_status(LIMITATION)
        unres = matrix.by_status(UNRESOLVED)
        if lims or unres:
            bits = []
            if lims:
                bits.append('cells we could not establish coverage for at all: ' +
                            '; '.join(f'{c.row_label} x {c.col_label} [{c.coverage_status or "UNROUTED"}]'
                                      for c in lims[:8]))
            if unres:
                bits.append('cells holding evidence we could not route to a dimension: ' +
                            '; '.join(f'{c.row_label} x {c.col_label}' for c in unres[:6]))
            slots.append(Slot(
                section='Scope and Method',
                title='Limitations of this review\'s own evidence base',
                kind='limitation',
                cells=[],
                must_do=('Report these AS LIMITATIONS OF THIS REVIEW, in the review\'s own voice. '
                         'They are facts about OUR SEARCH, not about the literature. You may NOT '
                         'write "the literature does not address X" for any of them -- we do not '
                         'know whether it does. ' + '. '.join(bits) + '.'),
                evidence_status='limitation'))

    # 7. IMPLICATIONS -- what the genre obliges.
    if contract.genre_rules:
        slots.append(Slot(
            section='Implications and a Research Agenda',
            title='What follows from the evidence',
            kind='agenda',
            must_do=' '.join(contract.genre_rules[:4]),
            evidence_status='contract'))

    return slots


def _plural(s: str) -> str:
    if s.endswith('y') and not re.search(r'[aeiou]y$', s):
        return s[:-1] + 'ies'          # Industry -> Industries, not "Industrys"
    if s.endswith(('s', 'x', 'ch', 'sh')):
        return s + 'es'
    return s + 's'


def _rank(cand: list[str], by_id: dict[str, dict]) -> list[str]:
    """ROUND-ROBIN ACROSS PAPERS, strongest evidence first within each paper.

    A subsection that takes its top-k cards by lexical score takes them from whichever paper happens
    to use the subsection's words most often -- so one paper supplies the whole subsection and the
    review reads as a serial summary of it. Interleaving by DOI forces the writer to have more than
    one source in front of it, which is the precondition for a comparative sentence existing at all.
    """
    buckets: dict[str, list[str]] = {}
    for cid in cand:
        c = by_id.get(cid)
        if not c:
            continue
        buckets.setdefault(c.get('doi') or cid, []).append(cid)
    for doi, ids in buckets.items():
        ids.sort(key=lambda i: (not has_verified_figure(by_id[i]),      # figures first
                                not has_direct_result(by_id[i]),        # then stated results
                                i))                                     # then stable
    order = sorted(buckets)
    out: list[str] = []
    i = 0
    while any(buckets[d] for d in order):
        d = order[i % len(order)]
        if buckets[d]:
            out.append(buckets[d].pop(0))
        i += 1
    return out


def allocate_cards(slots: list[Slot], cards: list[dict], max_reuse: int = MAX_CARD_REUSE,
                   slot_cap: int = 12) -> dict:
    """GLOBAL CARD ALLOCATION. 222 card slots were drawn from 82 cards; one finding was used EIGHT
    times and there were 41 exact repetitions, because every subsection independently ran a lexical
    _select() over the whole deck with NO IDEA WHAT ITS NEIGHBOURS HAD TAKEN. Repetition is not a
    writing defect to be cleaned up afterwards; it is a PLANNING defect, and it belongs here.

    Deterministic, greedy, capped. A card may be handed to at most `max_reuse` slots; a slot may hold
    at most `slot_cap` cards. Slots are served in outline order, so the section with first claim on a
    finding gets it, and the ones after it are forced onto evidence nobody has spent yet."""
    by_id = {c.get('id'): c for c in cards}
    used: dict[str, int] = {}
    starved: list[str] = []
    for s in slots:
        if not s.candidates:
            continue
        avail = [c for c in _rank(s.candidates, by_id) if used.get(c, 0) < max_reuse]
        s.card_ids = avail[:slot_cap]
        if not s.card_ids:
            starved.append(s.title)
        for cid in s.card_ids:
            used[cid] = used.get(cid, 0) + 1
    hist: dict[int, int] = {}
    for n in used.values():
        hist[n] = hist.get(n, 0) + 1
    return {'cards_used': len(used), 'slot_assignments': sum(used.values()),
            'reuse_histogram': dict(sorted(hist.items())), 'max_reuse': max_reuse,
            'slot_cap': slot_cap, 'starved_slots': starved}


# ===================================================================== derived prompts
#
# These replace the hardcoded strings in cellcog_composer.py. Nothing topic-specific is written here.

def build_extract_prompt(contract: Contract, paper: dict, k: int, text: str) -> str:
    """Replaces EXTRACT_PROMPT (cellcog_composer.py:103), which hardcodes 'the restructuring impact of
    Artificial Intelligence on the labor market' and a task-72 `level` enum.

    The target is not a COUNT of figures (count-chasing yields contextless numbers). It is an
    INTERPRETABLE EVIDENCE TUPLE: effect + unit + population + design + scope + uncertainty, with the
    field vocabulary supplied by the contract."""
    facets = '\n'.join(f'  {i+1}. {f.label}: {f.probe}' for i, f in enumerate(
        sorted(contract.facets, key=lambda f: f.priority)))
    levels = ' | '.join(f'"{x}"' for x in contract.unit_levels) or '""'
    designs = ' | '.join(f'"{x}"' for x in contract.method_designs) or '""'
    horizons = ' | '.join(f'"{x}"' for x in contract.time_horizons) or '""'
    tup = ', '.join(contract.evidence_tuple)
    return f"""You are extracting evidence from a peer-reviewed journal article for a {contract.genre} on
"{contract.review_subject}".

PAPER: {paper.get('title')}
AUTHORS: {', '.join(paper.get('authors') or [])}
JOURNAL: {paper.get('venue')} ({paper.get('year')})

TEXT (verbatim from the paper):
---
{text}
---

Extract up to {k} findings that bear on this review. THE FACETS THIS REVIEW MUST COVER:
{facets}

** A FINDING IS AN INTERPRETABLE EVIDENCE TUPLE, NOT A NUMBER. **
The tuple for this review is: {tup}.
A figure with no population, no design and no scope is not evidence -- it is a decoration, and the
judge reads it as one. A finding WITHOUT a result is a topic description wearing a finding's clothes.
Prefer, in order: effect sizes and elasticities; magnitudes, shares, rates, counts; uncertainty
(intervals, significance, sample size, study period); and only then a direct qualitative result.

THE NUMBER MUST APPEAR IN THE SPAN. A downstream gate deletes any figure it cannot find verbatim in
this paper's own span, so a claim whose number is missing from its span is DISCARDED and the evidence
is lost. Copy the sentence that CONTAINS the figure.

For EACH finding return an object:

{{
 "claim": "one sentence stating the finding, in your words, NO citation markers",
 "span": "a VERBATIM quote from the TEXT above that supports the claim -- copy it EXACTLY",
 "level": {levels},
 "horizon": {horizons},
 "method": {designs},
 "population": "who or what was studied, as the paper describes them",
 "scope": "the setting/period the finding is limited to, as the paper states it",
 "uncertainty": "interval, significance, or sample size IF the span states one, else \"\"",
 "mechanisms": ["any causal mechanism the PAPER ITSELF states"],
 "facets": ["which of the numbered facets above this finding serves"],
 "has_number": true/false
}}

RULES:
- The "span" MUST appear verbatim in the TEXT. If you cannot find a supporting quote, DO NOT emit the
  finding.
- If the finding has a number, THE SPAN MUST CONTAIN THAT NUMBER. Never state a figure in the claim
  that is not in the span you quote -- that is the one thing that gets an entire report thrown away.
- "mechanisms", "population", "scope", "uncertainty" must come from the PAPER. Do not infer. Empty is
  correct and common.
Return ONLY a JSON array."""


def build_scope_prose(contract: Contract) -> str:
    """The Scope & Methods narration. Number-free by construction -- see SourcePolicy."""
    return contract.source_policy.compliance_prose()


# ===================================================================== rendering

def print_contract(c: Contract) -> None:
    W = 96
    print('=' * W)
    print(f'RESEARCH CONTRACT   (task {c.question_id if c.question_id is not None else "-"})   '
          f'compiled by {c.compiled_by}')
    print('=' * W)
    print(textwrap.fill(c.question, W, initial_indent='  Q: ', subsequent_indent='     '))
    print()
    print(f'  GENRE            : {c.genre}')
    for r in c.genre_rules:
        print(f'                     - {r}')
    print(f'  REVIEW SUBJECT   : {c.review_subject}')
    print(f'  TITLE            : {c.title}')
    print()
    print('  SOURCE CONSTRAINTS (each must cite a VERBATIM clause of the question)')
    sp = c.source_policy
    print(f'    peer-reviewed only : {sp.peer_reviewed_only}')
    print(f'    languages          : {sp.languages or "(unscoped)"}')
    print(f'    quality bar        : {sp.quality_bar or "(none stated)"}')
    print(f'    recency from       : {sp.recency_from or "(unscoped)"}')
    print(f'    excluded types     : {", ".join(sp.excluded_types) or "(none)"}')
    for ev in sp.question_evidence:
        print(textwrap.fill(f'"{ev}"', W - 6, initial_indent='    span> ', subsequent_indent='           '))
    print()
    print('    COMPLIANCE PROSE (goes into Scope & Methods, and is what the grader reads):')
    print(textwrap.fill(sp.compliance_prose() or '(nothing to declare)', W - 6,
                        initial_indent='      ', subsequent_indent='      '))
    print()
    _terms_block('CORE CONCEPTS', c.core_concepts)
    _terms_block('FRAMING DEVICES (a lens THE QUESTION imposes -- graded)', c.framing_devices)
    _terms_block(f'SUBJECT AXIS = {c.subject_axis.name.upper()}  (rows of the coverage matrix)',
                 c.subject_axis.values)
    _terms_block('OUTCOME DIMENSIONS (columns of the coverage matrix)', c.outcome_dimensions)
    print(f'  GEOGRAPHIES      : {", ".join(c.geographies) or "(unscoped)"}')
    print(f'  TIME HORIZONS    : {", ".join(c.time_horizons) or "(none)"}')
    print(f'  METHOD DESIGNS   : {", ".join(c.method_designs) or "(none)"}')
    print(f'  UNIT LEVELS      : {", ".join(c.unit_levels) or "(none)"}')
    print(f'  EVIDENCE TUPLE   : {" + ".join(c.evidence_tuple)}')
    print()
    print('  REQUIRED CONTRASTS (the review is OBLIGED to draw these)')
    for k in c.required_contrasts:
        print(f'    - {k.label}')
        print(f'        {k.a}  <->  {k.b}')
    print()
    print('  EXTRACTION FACETS (what the miner harvests from every paper)')
    for f in sorted(c.facets, key=lambda x: x.priority):
        print(f'    [p{f.priority}] {f.label}')
        print(textwrap.fill(f.probe, W - 10, initial_indent='          ? ', subsequent_indent='            '))
    if c.warnings:
        print()
        print('  WARNINGS')
        for w in c.warnings:
            print(textwrap.fill(w, W - 6, initial_indent='    ! ', subsequent_indent='      '))
    print()


def _terms_block(name: str, terms: list[Term]) -> None:
    print(f'  {name}')
    if not terms:
        print('    (none)')
        return
    for t in terms:
        al = ', '.join(t.aliases[:6])
        print(f'    - {t.label:<42.42} [{al[:44]}]')
    print()


def print_matrix(m: Matrix, cards: list[dict]) -> None:
    W = 96
    print('=' * W)
    print(f'COVERAGE MATRIX   rows = {m.axis_name}   cols = outcome dimension   '
          f'({len(cards)} cards)')
    print('=' * W)
    if not m.cols:
        print('  (no outcome dimensions -- nothing to cover)')
        return
    keys = [c.key for c in m.cols]
    hdr = ''.join(f'{k[:9]:>11.9}' for k in keys)
    print(f'  {"":<26}{hdr}')
    sym = {CLOSED: ' CLOSED', THIN: '  thin ', GAP: '  gap  ',
           LIMITATION: ' LIMIT ', UNRESOLVED: ' AMBIG '}
    for r in m.rows:
        cells = [m.cell(r.key, c.key) for c in m.cols]
        line = ''.join(f'{sym.get(x.status, "   ?   ")}({x.n_works:>2})' for x in cells)
        print(f'  {r.label[:25]:<26}{line}')
    print()
    n = len(m.cells)
    cl, th, gp = len(m.by_status(CLOSED)), len(m.by_status(THIN)), len(m.by_status(GAP))
    li, am = len(m.by_status(LIMITATION)), len(m.by_status(UNRESOLVED))
    print(f'  {cl}/{n} CLOSED   {th}/{n} thin   {gp}/{n} gap (LICENSED)   {li}/{n} LIMITATION   '
          f'{am}/{n} AMBIGUOUS')
    if not m.has_ledger:
        print(f'  NO LEDGER WAS SUPPLIED. No cell may declare an evidence gap: an absence needs a '
              f'record of a search that')
        print(f'  ran and came back empty, and we have none. Every empty cell is reported as a '
              f'PIPELINE LIMITATION.')
    if m.unbound:
        print(f'  {len(m.unbound)} card(s) carry NO BINDING to a manifestation. They are counted by '
              f'DOI, which cannot tell')
        print(f'  two studies from two versions of one study.')
    if m.ambiguous:
        print(f'  {len(m.ambiguous)} card(s) are AMBIGUOUS between sibling dimensions. Their cells may '
              f'not close OR declare an absence.')
    if m.unrouted:
        pct = 100 * len(m.unrouted) / max(1, len(cards))
        print(f'  {len(m.unrouted)}/{len(cards)} cards ({pct:.0f}%) speak to NO outcome dimension of this '
              f'question. That is a CORPUS signal, not a')
        print(f'  matcher one: the miner is holding evidence the question did not ask for, and every '
              f'one of those cards is')
        print(f'  a slot the writer can fill with something irrelevant.')
    print()
    print('  CELLS THE CORPUS CLOSES ON EVIDENCE:')
    for c in sorted(m.by_status(CLOSED), key=lambda x: -x.n_works)[:12]:
        print(f'    {c.row_label[:22]:<23} x {c.col_label[:22]:<23} {c.reason}')
    if th:
        print('  THIN (closeable, but narrate the single-design limitation):')
        for c in sorted(m.by_status(THIN), key=lambda x: -x.n_works)[:6]:
            print(f'    {c.row_label[:22]:<23} x {c.col_label[:22]:<23} {c.reason}')
    print()
    gr = m.gap_rows()
    if gr:
        print(f'  {_plural(m.axis_name).upper()} THE REVIEW MAY REPORT AS A SCOPED EVIDENCE GAP '
              f'(the search RAN and returned nothing):')
        print(textwrap.fill(', '.join(r.label for r in gr), W - 6,
                            initial_indent='    ', subsequent_indent='    '))
        print('    -> these close as an EXPLICIT, CORPUS-SCOPED EVIDENCE GAP, not as filler.')
    lr = m.limitation_rows()
    if lr:
        print(f'  {_plural(m.axis_name).upper()} THE OUTLINE MUST NOT PROMISE -- AND MUST NOT CALL AN '
              f'EVIDENCE GAP EITHER:')
        print(textwrap.fill(', '.join(r.label for r in lr), W - 6,
                            initial_indent='    ', subsequent_indent='    '))
        print('    -> WE NEVER SUCCESSFULLY LOOKED. This is a limitation OF THIS REVIEW, and saying')
        print('       "the literature does not cover it" would assert a fact about the world out of')
        print('       a fact about our own plumbing.')
    print()


def print_outline(slots: list[Slot], alloc: dict | None) -> None:
    W = 96
    print('=' * W)
    print(f'OUTLINE DERIVED FROM THE CONTRACT   ({len(slots)} subsections)')
    print('=' * W)
    sec = None
    for s in slots:
        if s.section != sec:
            sec = s.section
            print(f'\n  ## {sec}')
        if s.card_ids:
            n = f'{len(s.card_ids):>3} cards / {len(s.candidates):>3} elig'
        elif s.evidence_status == 'gap':
            n = '  cites nothing (that is the point)'
        elif s.evidence_status == 'UNGROUNDED':
            n = '  ** UNGROUNDED **'
        else:
            n = '  contract'
        print(f'     ### {s.title[:52]:<54} [{s.kind:<8}] {n}')
    if alloc:
        print()
        print(f'  CARD ALLOCATION: {alloc["cards_used"]} distinct cards -> '
              f'{alloc["slot_assignments"]} slot assignments '
              f'(cap {alloc["max_reuse"]}/card, {alloc["slot_cap"]}/slot)')
        print(f'  reuse histogram (N cards used exactly K times): {alloc["reuse_histogram"]}')
        if alloc['starved_slots']:
            print(f'  ** STARVED (every candidate already spent): {alloc["starved_slots"]}')
        print(f'  the shipped run drew 222 slots from 82 cards: one finding used 8 times, '
              f'41 exact repetitions.')
    print()


# ===================================================================== post-hoc rubric audit
#
# THE RUBRIC IS NEVER AN INPUT. The contract is compiled FROM THE QUESTION ALONE, because on an
# unseen question there is no rubric to read. This audit runs AFTER compilation and asks a different
# question: DID THE COMPILER REDISCOVER THE RUBRIC FROM THE QUESTION? If it did, we do not need the
# rubric, and we have evidence the compiler generalises rather than memorises.

def audit_rubric(contract: Contract, qid: int) -> None:
    if not CRITERIA.exists():
        print('  (no criteria.jsonl -- skipping)')
        return
    row = None
    for line in CRITERIA.open():
        d = json.loads(line)
        if d.get('id') == qid:
            row = d
            break
    if not row:
        print(f'  (no criteria for task {qid})')
        return
    vocab = set()
    for t in (contract.core_concepts + contract.framing_devices +
              contract.subject_axis.values + contract.outcome_dimensions):
        vocab |= {w for w in re.findall(r'[a-z]{4,}', (t.label + ' ' + ' '.join(t.aliases)).lower())}
    for f in contract.facets:
        vocab |= {w for w in re.findall(r'[a-z]{4,}', (f.label + ' ' + f.probe).lower())}
    for k in contract.required_contrasts:
        vocab |= {w for w in re.findall(r'[a-z]{4,}', f'{k.label} {k.a} {k.b}'.lower())}
    for g in contract.genre_rules + [contract.genre]:
        vocab |= {w for w in re.findall(r'[a-z]{4,}', g.lower())}
    sp = contract.source_policy
    if sp.peer_reviewed_only:
        vocab |= {'journal', 'peer', 'reviewed', 'article', 'articles', 'academic'}
    vocab |= {l.lower() for l in sp.languages}
    if sp.quality_bar:
        vocab |= {'quality', 'high'}

    print('=' * 96)
    print(f'POST-HOC AUDIT: did the compiler REDISCOVER task {qid}\'s rubric FROM THE QUESTION ALONE?')
    print('(the rubric was NOT an input to compilation. this is a diagnostic, never a lever.)')
    print('=' * 96)
    dw = row.get('dimension_weight', {})
    tot = 0.0
    for dim, crits in (row.get('criterions') or {}).items():
        for cr in crits:
            w = dw.get(dim, 0) * cr.get('weight', 0)
            words = {x for x in re.findall(r'[a-z]{4,}', cr['criterion'].lower()) if x not in _STOP}
            hit = words & vocab
            cov = len(hit) / max(1, len(words))
            mark = 'HIT ' if cov >= 0.34 else ('part' if cov >= 0.2 else 'MISS')
            if cov >= 0.34:
                tot += w
            print(f'  [{mark}] w={w:.4f} {dim[:6]:<6} {cr["criterion"][:56]:<58} '
                  f'{cov:.0%} {sorted(hit)[:4]}')
    print(f'\n  weight of criteria the contract explicitly names: {tot:.3f} of 1.000')
    print()


# ===================================================================== self-test
#
# NO NETWORK. Every derivation downstream of the single LLM call is a pure function, so all of it is
# testable offline -- including the branches the live corpus happens never to take. A gate nobody
# exercises is worth nothing; that lesson is already written on this repo in blood.

def self_test() -> int:
    fails: list[str] = []

    def ck(name: str, ok: bool, detail: str = '') -> None:
        print(f"  [{'PASS' if ok else '**FAIL**'}] {name}")
        if detail and not ok:
            print(f'            {detail}')
        if not ok:
            fails.append(name)

    print('=== research_contract self-test (no network) ===\n')

    # 1. THE MATCHER MUST DISCRIMINATE. "job" occurs in three of task 72's five outcome dimensions;
    #    if it routes, every card lands in every cell and the matrix says nothing.
    fam = [Term('job_displacement', 'Job displacement', ['job displacement', 'job loss', 'unemployment']),
           Term('job_creation', 'Job creation', ['job creation', 'new jobs', 'labor demand']),
           Term('wage_effects', 'Wage effects', ['wage effects', 'wages', 'earnings'])]
    m, _w = build_matchers(fam)
    ck('shared word ("job") is NOT discriminative and routes nothing ON ITS OWN',
       'job' not in m['job_displacement'].disc and 'job' not in m['job_creation'].disc)
    ck('unique word ("wage") DOES route', 'wage' in m['wage_effects'].disc)
    ck('a generic research word ("effect") never routes',
       'effect' not in m['wage_effects'].disc, '"effect" would match every span in any corpus')
    ck('the matcher stems: a span saying "wages" hits the term "Wage effects"',
       'wage_effects' in _hits(m, 'occupational wages and educational attainment'))
    ck('a span about nothing in the family routes nowhere',
       _hits(m, 'the gut microbiota regulates intestinal barrier integrity') == [])

    # 1b. THE WAGE MATCHER, GENERICALLY. Two sibling dimensions whose ONLY vocabulary is shared.
    #     Under the old rule BOTH lost every stem, `Wages` could not match the word "wage", and every
    #     wage card in the corpus went unrouted -- printing as an EVIDENCE GAP over a corpus full of
    #     wage results. There is no regex for "wage" anywhere in this fix.
    fam2 = [Term('wages', 'Wages', ['wages', 'wage', 'pay', 'earnings']),
            Term('wage_ineq', 'Wage inequality', ['wage inequality', 'wage dispersion', 'wage gap'])]
    m2, w2 = build_matchers(fam2)
    ck('the stem "wage" is SHARED by both dimensions and is therefore NOT discriminative',
       'wage' not in m2['wages'].disc and 'wage' not in m2['wage_ineq'].disc)
    ck('...and it is KEPT as an AMBIGUOUS signal, not deleted',
       'wage' in m2['wages'].shared and 'wage' in m2['wage_ineq'].shared,
       'DELETING it is how the dimension "Wages" stopped being able to match the word "wage"')
    ck('a term whose every stem is shared is NOT declared unroutable',
       not any('never route' in x for x in w2), f'{w2}')
    conf, amb = route_terms(m2, 'hourly wages fell by 0.2 percent for routine workers')
    ck('SHARED STEM + span context -> the SEMANTIC second stage routes it to "Wages"',
       conf == ['wages'] and not amb, f'confident={conf} ambiguous={amb}')
    conf, amb = route_terms(m2, 'wage inequality rose sharply across the distribution')
    ck('a DECISIVE sibling stem explains the shared one: "wage inequality" does NOT also route to Wages',
       conf == ['wage_ineq'] and not amb, f'confident={conf} ambiguous={amb}')
    # 'levels' and 'rates' are both GENERIC research words, so these two dimensions have the SAME
    # single stem, {wage}, and NOTHING separates them. That is a real tie, and it is not broken.
    fam3 = [Term('a', 'Wage levels', ['wage']), Term('b', 'Wage rates', ['wage'])]
    m3, _ = build_matchers(fam3)
    conf, amb = route_terms(m3, 'the wage was measured annually')
    ck('a TIE between siblings is AMBIGUOUS -- never guessed, never a GAP',
       conf == [] and amb == ['a', 'b'], f'confident={conf} ambiguous={amb}')

    # 2. THE SOURCE-POLICY GATE. Each constraint must be entailed by ITS OWN verbatim clause of the
    #    question -- not by some other constraint's clause. (rc-2 admitted a fabricated recency
    #    cutoff of 2015 because the journal-only quote had verified. That is evidence laundering.)
    Q = ('Please write a literature review on X. Ensure the review only cites high-quality, '
         'English-language journal articles.')
    sp = _floor_source_policy(Q)
    ck('regex floor detects journal-only + English + quality bar',
       sp.peer_reviewed_only and sp.languages == ['English'] and sp.quality_bar == 'high-quality')
    ck('the floor quotes a VERBATIM clause of the question',
       all(e.lower() in ' '.join(Q.lower().split()) for e in sp.question_evidence),
       f'{sp.question_evidence}')
    ck('a question with NO source constraint yields NO source policy',
       not _floor_source_policy('What causes Parkinson\'s disease?').peer_reviewed_only)
    ck('compliance prose carries no digits (an OWNED sentence with a number is dropped by the gate)',
       not re.search(r'\d', sp.compliance_prose()), sp.compliance_prose())

    # 3. THE CLOSE RULE, including the branch the live corpus never took.
    con = Contract(question=Q, method_designs=['observational', 'quasi-experimental'],
                   outcome_dimensions=fam, subject_axis=Axis('Industry', [Term('m', 'Manufacturing', ['manufacturing'])]))

    def mk(n_works, n_methods, quant, qual, ledger=None, ambiguous=()):
        c = Cell('m', 'Manufacturing', 'wage_effects', 'Wage effects')
        c.families = [f'work:w{i}' for i in range(n_works)]
        c.dois = [f'd{i}' for i in range(n_works)]
        c.methods = [f'meth{i}' for i in range(n_methods)]
        c.n_quant, c.n_qual = quant, qual
        c.ambiguous = list(ambiguous)
        _close(c, con, ledger)
        return c

    ck('2 works + 1 result + single design -> CLOSED (contrast not material at this depth)',
       mk(2, 1, 1, 0).status == CLOSED)
    ck('3 works + result + ONE design -> THIN (design contrast IS material here)',
       mk(3, 1, 1, 0).status == THIN, 'the THIN branch is dead')
    ck('3 works + result + TWO designs -> CLOSED', mk(3, 2, 1, 0).status == CLOSED)

    # ---- THE ABSENCE LICENCE. A positive close needs cards. An ABSENCE needs A LEDGER.
    ck('1 work, NO LEDGER -> LIMITATION, and the absence is NOT licensed',
       mk(1, 1, 1, 0).status == LIMITATION and not mk(1, 1, 1, 0).absence_licensed,
       'an empty cell with no record of a search USED TO PRINT AS AN EVIDENCE GAP')
    ck('2 works but no stated result, NO LEDGER -> LIMITATION, not GAP',
       mk(2, 2, 0, 0).status == LIMITATION)
    # AN UNROUTED CARD BITES WHERE IT COULD CHANGE THE ANSWER, AND ONLY THERE.
    c = mk(1, 1, 1, 0, ambiguous=['c1'])
    ck('a cell that does NOT close, with an AMBIGUOUS card, is UNRESOLVED -- never a GAP',
       c.status == UNRESOLVED and not c.absence_licensed,
       'that card might be exactly this cell\'s evidence; we do not know that the cell is empty')
    c = mk(4, 2, 3, 0, ambiguous=['c1'])
    ck('...but a cell that ALREADY closes on confident evidence still closes, and RECORDS the ambiguity',
       c.status == CLOSED and 'MAY belong here' in c.reason,
       'routing an unplaceable card INTO a closed cell could only strengthen it — destroying the close '
       'would delete evidence we can place to punish evidence we cannot')

    import event_ledger as EL
    from types import SimpleNamespace

    def fake_ledger(events):
        return SimpleNamespace(events=lambda unit=None, kind=None: [e for e in events
                                                                    if unit is None or e.unit == unit])

    _seq = [0]

    def ev(kind, unit, **payload):
        _seq[0] += 1
        return EL.Event(seq=_seq[0], kind=kind, unit=unit, actor='self_test', ts=0.0, payload=payload)

    # a route that was PLANNED, RAN on every adapter, and came back EMPTY -> a scoped absence IS sayable
    searched = fake_ledger([
        ev(EL.EventKind.ROUTE_PLANNED, 'm:wage_effects', adapters=['openalex']),
        ev(EL.EventKind.RESPONSE_RECEIVED, 'm:wage_effects', adapter='openalex', http_status=200)])
    c = mk(0, 0, 0, 0, ledger=searched)
    ck('SEARCHED_NONE (route ran, nothing came back) -> GAP, and the absence IS licensed',
       c.status == GAP and c.absence_licensed, f'{c.status} {c.coverage_status}')

    # the same empty cell, but the adapter was RATE-LIMITED. WE DO NOT KNOW WHAT IS THERE.
    throttled = fake_ledger([
        ev(EL.EventKind.ROUTE_PLANNED, 'm:wage_effects', adapters=['openalex']),
        ev(EL.EventKind.RESPONSE_RECEIVED, 'm:wage_effects', adapter='openalex', http_status=429)])
    c = mk(0, 0, 0, 0, ledger=throttled)
    ck('SEARCH_FAILED (HTTP 429) -> LIMITATION. NEVER an evidence gap.',
       c.status == LIMITATION and not c.absence_licensed and c.coverage_status == EL.SEARCH_FAILED,
       f'{c.status} {c.coverage_status} — a 429 is a fact about OUR REQUEST, not about the literature')

    # 4. QUANTITATIVE = VERIFIED AGAINST THE SPAN, never against the model-written `claim`.
    ck('a figure in the SPAN counts as quantitative',
       has_verified_figure({'span': 'employment fell by 0.2 percentage points per robot'}))
    ck('a figure the model put in `claim` but NOT in the span does NOT count',
       not has_verified_figure({'span': 'automation reduced employment.',
                                'claim': 'employment fell 47 percent'}),
       'the claim is a display cache and is never evidence')
    ck('a bare year in the span is not an effect size',
       not has_verified_figure({'span': 'we study the period since 2003.'}))

    # A TYPED ACT IS A RESULT OF ITS TYPE. Without this the miner rescues the judicial opinion and the
    # MATRIX throws it away again: a holding has no result verb, so the cell would score `0 results`.
    holding_card = {'act': 'doctrinal_holding_or_rule',
                    'span': 'the employer bears the burden of proving that the system is job-related '
                            'and consistent with business necessity',
                    'holding': 'the employer bears the burden', 'authority': 'the Court'}
    ck('a DOCTRINAL HOLDING counts as a direct result (it has no result verb, and it IS evidence)',
       has_direct_result(holding_card) and not _RESULT_VERB.search(holding_card['span']),
       'the extractor would have rescued it and the coverage matrix would have discarded it')
    ck('a legacy UNTYPED card still falls back to the result-verb heuristic',
       has_direct_result({'span': 'we found that adoption increased'})
       and not has_direct_result({'span': 'this paper is about robots'}))

    # 5. THE ALLOCATOR. A card may not be spent more than max_reuse times, and one paper may not
    #    supply a whole subsection.
    cards = [{'id': f'c{i}', 'doi': f'doi{i % 2}', 'span': f'employment fell by {i}.5 percent'}
             for i in range(6)]
    slots = [Slot('S', f't{i}', 'outcome', candidates=[c['id'] for c in cards]) for i in range(4)]
    alloc = allocate_cards(slots, cards, max_reuse=2, slot_cap=3)
    counts: dict[str, int] = {}
    for s in slots:
        for cid in s.card_ids:
            counts[cid] = counts.get(cid, 0) + 1
    ck('no card is handed to more than max_reuse slots',
       all(v <= 2 for v in counts.values()), f'{counts}')
    ck('no slot exceeds slot_cap', all(len(s.card_ids) <= 3 for s in slots))
    ck('a slot draws from >1 paper (round-robin by DOI, so one paper cannot own a subsection)',
       len({c['doi'] for c in cards if c['id'] in slots[0].card_ids}) > 1,
       f'{slots[0].card_ids}')
    ck('a starved slot is REPORTED, not silently emptied',
       'starved_slots' in alloc)

    print()
    if fails:
        print(f'** {len(fails)} FAILURE(S) **')
        for f in fails:
            print(f'    - {f}')
        return 1
    print('** ALL DERIVATIONS PASS (no network) **')
    return 0


# ===================================================================== entry point

def load_question(task: int) -> tuple[str, int]:
    for path in (QUERIES, DRB / 'prompt_data' / f'query_task{task}.jsonl'):
        if not path.exists():
            continue
        for line in path.open():
            d = json.loads(line)
            if d.get('id') == task:
                return d['prompt'], task
    raise SystemExit(f'task {task} not found under {DRB/"prompt_data"}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--task', type=int, default=72, help='DeepResearch Bench task id')
    ap.add_argument('--question', help='any question at all (overrides --task)')
    ap.add_argument('--cards', default=str(CARDS))
    ap.add_argument('--corpus', default=str(ROOT / 'outputs' / 'journal_corpus_content.json'))
    ap.add_argument('--no-llm', action='store_true', help='regex-only contract; no network')
    ap.add_argument('--force', action='store_true', help='ignore the cache and recompile')
    ap.add_argument('--json', action='store_true', help='dump the contract as JSON and exit')
    ap.add_argument('--audit-rubric', action='store_true', help='POST-HOC diagnostic only')
    ap.add_argument('--self-test', action='store_true', help='exercise every derivation, no network')
    a = ap.parse_args()

    if a.self_test:
        return self_test()

    if a.question:
        q, qid = a.question, None
    else:
        q, qid = load_question(a.task)

    c = compile_contract(q, qid, use_llm=not a.no_llm, force=a.force)
    if a.json:
        print(c.to_json())
        return 0

    print()
    print_contract(c)

    cards, corpus = [], []
    cp, up = Path(a.cards), Path(a.corpus)
    if cp.exists():
        cards = json.loads(cp.read_text())
    if up.exists():
        corpus = json.loads(up.read_text())

    if cards:
        m = coverage_matrix(c, cards, corpus)
        print_matrix(m, cards)
        slots = derive_outline(c, m, cards)
        alloc = allocate_cards(slots, cards)
        print_outline(slots, alloc)
    else:
        print(f'  (no evidence cards at {cp} -- outline shown WITHOUT the corpus veto)\n')
        slots = derive_outline(c, None)
        print_outline(slots, None)

    if a.audit_rubric and qid is not None:
        audit_rubric(c, qid)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
