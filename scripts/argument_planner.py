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
    secondhand_cues: list[str] = field(default_factory=list)   # the span reports ANOTHER paper's finding
    forecast_cues: list[str] = field(default_factory=list)     # the span is a projection, not a finding
    # ADJUDICATIVE SUBSECTIONS are about the ARGUMENT, not about a topic. "Where the literature
    # genuinely disagrees" shares no content word with any card, so a lexical matcher hands it NOTHING --
    # and that subsection is the one this whole planner exists to feed (Critical Synthesis: 210 words of
    # 8,012, scoring 6.36 on the joint-heaviest criterion). These are matched on the vocabulary of
    # ADJUDICATION, which is general to any research question, and they get FIRST PICK of the bundles.
    adjudicative_roles: dict[str, list[str]] = field(default_factory=dict)
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
                # `\bjobs?\b` matched "JOB SATISFACTION" and `\bemploy\w*` matched "EMPLOYEE EXPERIENCE".
                # Neither is the quantity of employment, and both were feeding a fabricated conflict.
                # An outcome pattern must name the QUANTITY, not merely share a word with it.
                'employment':      [r'\bemployment\b', r'\bunemploy\w*', r'\bjob loss\w*',
                                    r'\bjobs?\b(?!\s+(?:satisfaction|security|quality|content|title|'
                                    r'description|design))',
                                    r'\bworkforce\b', r'\bhiring\b', r'\blab(?:o|ou)r demand\b'],
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
        #
        #      A POLARITY CUE MUST PREDICATE A CHANGE OF THE OUTCOME. It may not merely be a word with
        #      a direction-ish flavour sitting near it. The first build shipped `\bincreas\w*`, which
        #      matched the ADVERB in "employment of the less-skilled is increasingly DEPENDENT on
        #      physical proximity" -- where 'increasingly' modifies 'dependent' and says nothing whatever
        #      about the level of employment -- and `\bhigher\b`/`\blower\w*`, which match the COMPARATIVE
        #      ADJECTIVE in "higher-skilled workers". Those two cues, between them, produced this
        #      planner's top-ranked GENUINE CONFLICT out of two cards that were not in tension and were
        #      not even about the same thing.
        #      So: verbs and magnitude nouns only. No adverbs, no comparative adjectives.
        polarity={
            'negative': [r'\breduc(?:e|es|ed|ing|tion|tions)\b', r'\bdeclin(?:e|es|ed|ing)\b',
                         r'\bfell\b', r'\bfalls?\b', r'\bfalling\b', r'\bdecreas(?:e|es|ed|ing)\b',
                         r'\bdisplac(?:e|es|ed|ing|ement)\b', r'\bloss(?:es)?\b', r'\bshrink\w*',
                         r'\bshrank\b', r'\bsubstitut(?:e|es|ed|ing|ion)\b', r'\bdestroy\w*',
                         r'\berod(?:e|es|ed|ing)\b', r'\bnegative\b', r'\bredundant\b', r'\bobsolete\b',
                         r'\breplac(?:e|es|ed|ing|ement)\b', r'\beliminat(?:e|es|ed|ing)\b'],
            'positive': [r'\bincreas(?:e|es|ed|ing)\b',          # NOT "increasingly"
                         r'\brais(?:e|es|ed|ing)\b', r'\bris(?:e|es|ing)\b', r'\brose\b',
                         r'\bgrow(?:s|ing|th)?\b', r'\bgrew\b', r'\bgains?\b',
                         r'\bcreat(?:e|es|ed|ing|ion)\b', r'\bcomplement(?:s|ed|ing|arity)?\b',
                         r'\bexpand(?:s|ed|ing)?\b', r'\bexpansion\b', r'\bimprov(?:e|es|ed|ing)\b',
                         r'\baugment(?:s|ed|ing)?\b', r'\bpositive\b'],
            'null':     [r'\bno significant\b', r'\bno effect\b', r'\bno evidence\b', r'\binsignificant\b',
                         r'\btoo small to detect\b', r'\bnot significant\b', r'\bunchanged\b'],
        },
        # ---- NEGATORS *AND ATTENUATORS*. An attenuator inverts a cue as surely as a negator does:
        #      "the SLOWER GROWTH of employment ... accounted for by an acceleration in the DISPLACEMENT
        #      effect" (Acemoglu and Restrepo 2019) is a finding about employment being DESTROYED, and the
        #      bare cue 'growth' read it as POSITIVE. We do not flip on these -- flipping is inference --
        #      we DISCARD the cue and return UNKNOWN, which is the one answer that cannot be wrong.
        negators=[r'\bnot\b', r'\bno\b', r'\bnor\b', r'\bnever\b', r'\bwithout\b', r'\bneither\b',
                  r'\bfails? to\b', r'\bunable to\b', r'\bcannot\b', r"\bdoes ?n[o']t\b", r'\blittle\b',
                  r'\bslow(?:er|ing|ly)?\b', r'\bweak(?:er|ening)?\b', r'\bless\b', r'\bslower\b',
                  r'\bdampen\w*', r'\bmuted\b', r'\bmodest\b', r'\blimited\b'],
        # ---- an ESTIMATE from a stronger design outranks one from a weaker design. DECLARED fields only.
        design_rank={'experiment': 5, 'quasi-experimental': 4, 'observational': 3, 'survey': 2,
                     'review': 1, 'theory': 0},
        empirical_designs=['experiment', 'quasi-experimental', 'observational', 'survey'],
        # ---- THE SECOND-HAND SPAN. A span can be VERBATIM IN THE PAPER and still not be the paper's
        #      own finding: a literature-review sentence inside Damioli 2021 reads "Graetz and Michaels
        #      (2018) use country-level data ... and find that ...". The extraction gate passes it --
        #      the text IS in the paper -- and the composer then prints "Writing in the Eurasian Business
        #      Review in 2021, Damioli et al. show that ..." over GRAETZ AND MICHAELS' FINDING AND THEIR
        #      FIGURES. That is a fabricated binding of exactly the kind this codebase already bled for
        #      ('task displacement' credited to Bresnahan), and no span check can see it, because the
        #      span check asks "is this text in the paper?" and never "is this finding the paper's OWN?"
        #      MEASURED: 5 such cards, 6 figures that would print under the wrong paper's name.
        secondhand_cues=[
            r'\b[A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?\s*\(\s*(?:19|20)\d\d\s*\)',
            r'\bet al\.\s*\(\s*(?:19|20)\d\d', r'\bcommission\s*\(\s*(?:19|20)\d\d',
            r'\btheir (?:results|findings|study|analysis|paper|estimates|data)\b',
            r'\baccording to\b', r'\bhas predicted\b', r'\bhave (?:shown|found|argued|documented)\b',
            r'\b(?:studies|scholars|researchers|authors|others) (?:have )?(?:show|find|argue|suggest)',
            r'\b(?:world economic forum|mckinsey|oecd|gartner|pwc|deloitte)\b',
        ],
        # ---- A PROJECTION IS NOT A FINDING. synthesis_contract already treats a forecast as fabrication
        #      when the REVIEWER writes one; it is no more ADJUDICABLE as evidence. "AI will make 75
        #      million jobs redundant" cannot be weighed against a measured estimate -- there is nothing
        #      to weigh, because nothing was measured. But a forecast is still CITABLE ("Agrawal and
        #      colleagues argue that AI will affect labor"), so this is the SOFTER penalty: barred from
        #      comparisons, admitted as attributed prose. Barring it outright starves the corpus, which
        #      is the failure this codebase already suffered when a gate ate its own evidence.
        #
        #      NOTE THE PATTERNS. A first draft used bare `\bpredict\w*` and it deleted Agrawal, Gans and
        #      Goldfarb entirely -- because "a PREDICTION technology" and "the cost of PREDICTION" are the
        #      SUBJECT MATTER of Prediction Machines, not forecasts. The noun sense is the whole framework
        #      and an outline subsection is named after it. Only the ATTRIBUTIVE, forward-looking forms
        #      count; `project` and `prediction` as nouns are technical vocabulary and are left alone.
        forecast_cues=[r'\bwill\b', r'\bis going to\b', r'\bby 20[3-9]\d\b',
                       r'\b(?:is|are|was|were|has been|have been) (?:predicted|expected|projected|'
                       r'forecast) to\b', r'\b(?:predicts|predicted|forecasts|projects) that\b',
                       r'\bhas predicted\b', r'\bexpected to\b'],
        # ---- WHICH SUBSECTIONS ADJUDICATE, AND ON WHAT. Keyed on the vocabulary of ARGUMENT (disagree,
        #      establish, resolve, gap), which belongs to no particular research question.
        adjudicative_roles={
            r'genuinely disagree|disagree|conflict|contested|tension|contradict':
                ['SAME_UNIT_OPPOSITE_DIRECTION', 'SAME_OUTCOME_DIFFERENT_UNIT'],
            r'establish|converge|robust|consensus|what the evidence (?:shows|establishes)':
                ['SAME_FINDING_DIFFERENT_METHOD', 'SAME_OUTCOME_DIFFERENT_HORIZON',
                 'SAME_OUTCOME_DIFFERENT_UNIT'],
            r'cannot yet resolve|unresolved|cannot resolve|does not settle|gap|agenda|research agenda':
                ['UNCOUNTERED', 'SAME_OUTCOME_DIFFERENT_HORIZON'],
            r'diverge|why .* differ|reconcile':
                ['SAME_OUTCOME_DIFFERENT_UNIT', 'SAME_UNIT_OPPOSITE_DIRECTION'],
        },
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

# A POLARITY FLIPS AT A CONTRASTIVE CONNECTIVE. "Robots reduce employment while raising productivity"
# is one span carrying two opposite findings about two different quantities, and a cue may only be read
# as the direction of an outcome that stands IN ITS OWN CLAUSE. This is the same reading
# `cellcog_composer._gate_multi` already takes of a comparative sentence -- a conjunction of clauses,
# each answerable for itself.
_CLAUSE_BREAK = re.compile(
    r'[;:]|\bwhile\b|\bwhereas\b|\bbut\b|\balthough\b|\bthough\b|\bhowever\b|\byet\b|'
    r'\bby contrast\b|\bin contrast\b|\bon the other hand\b|\beven as\b|\bwhile\b', re.I)


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z0-9''.\-]+", s.lower())


def _clauses(span: str) -> list[str]:
    return [c for c in _CLAUSE_BREAK.split(span) if c and c.strip()]


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


def derive_outcome_direction(span: str, contract: ResearchContract) -> tuple[Facet, Facet, list[str]]:
    """OUTCOME AND DIRECTION ARE ONE JOINT DERIVATION, OR THEY ARE NOTHING.

    Derived separately, they need not even be about each other. That is not a hypothetical: this exact
    span, from Acemoglu and Restrepo 2018 --

        "In an extension with heterogeneous SKILLS, we show that INEQUALITY INCREASES during
         transitions driven by automation"

    was tagged outcome=SKILLS (the earliest outcome word in the span) and direction=POSITIVE (from
    'increases', which belongs to INEQUALITY). Neither tag was about the other, and the pair went on to
    become the planner's top-ranked GENUINE CONFLICT. Earliest-mention-wins is an arbitrary rule, and an
    arbitrary rule applied to the most dangerous facet on the board produces exactly what you would expect.

    THE OUTCOME OF A FINDING IS THE QUANTITY WHOSE CHANGE IS REPORTED. So we look for (outcome, polarity)
    pairs that stand together in one clause, and let the pair decide both facets at once:

      * exactly one outcome, exactly one polarity   -> A DIRECTIONAL FINDING. Both facets assigned.
        (Acemoglu above now resolves correctly to outcome=inequality, direction=positive.)
      * one outcome, MIXED polarity                 -> outcome assigned, direction UNKNOWN.
      * SEVERAL outcomes, each with a direction     -> the span reports several findings and we cannot
        say which is THE finding. AMBIGUOUS: citable, never a comparison term.
      * no polarity anywhere                        -> a TOPICAL mention, not a finding. Direction UNKNOWN.
        The outcome is assigned only if the span mentions exactly ONE outcome family; if it mentions
        several with nothing to choose between them, it is AMBIGUOUS and cannot anchor a bundle.

    MEASURED ON THIS CORPUS: 17 cards of 133 are directional findings. 15 report several directed
    outcomes at once. 98 report no direction at all. The scarcity is the point -- it is what makes a
    "genuine conflict" a claim that has to be earned.
    """
    vocab = contract.span_facets.get('outcome', {})
    if not vocab:
        return Facet('outcome'), Facet('direction'), []

    # A POLARITY CUE GOVERNS EXACTLY ONE QUANTITY: THE NEAREST ONE. Attaching it to every outcome inside
    # the window is what bound 'increases' to SKILLS at a distance of seven tokens, when it plainly
    # belongs to INEQUALITY at a distance of one. Nearest-cue attachment is the whole fix.
    pairs: dict[str, dict[str, str]] = {}       # outcome -> {polarity: matched_form}
    first_seen: dict[str, int] = {}
    for clause in _clauses(span):
        neg_idx = {i for i, _ in _match_spans(clause, contract.negators)}
        occ: list[tuple[int, str]] = []                            # (token_index, outcome_value)
        for ov, pats in vocab.items():
            for i, _ in _match_spans(clause, pats):
                occ.append((i, ov))
        if not occ:
            continue
        for i, ov in occ:
            first_seen.setdefault(ov, i)
            first_seen[ov] = min(first_seen[ov], i)
        for cls, ppats in contract.polarity.items():
            for ti, form in _match_spans(clause, ppats):
                if any(0 < ti - ni <= NEG_WINDOW for ni in neg_idx):
                    continue                                       # negated: DISCARD, never flip
                oi, ov = min(occ, key=lambda x: abs(ti - x[0]))    # the NEAREST outcome, and only it
                if abs(ti - oi) > DIR_WINDOW:
                    continue                                       # too far to govern anything here
                pairs.setdefault(ov, {}).setdefault(cls, form)

    mentioned = derive_span_facet_all(span, 'outcome', vocab)
    if not mentioned:
        return Facet('outcome'), Facet('direction'), []

    # THE PRIMARY OUTCOME IS THE ONE WHOSE CHANGE IS REPORTED -- the earliest outcome that actually
    # carries a direction. Only when nothing carries a direction do we fall back to the earliest
    # mention, and then the card is TOPICAL: direction UNKNOWN, so it can never enter a conflict.
    directed = [ov for ov in sorted(pairs, key=lambda v: first_seen.get(v, 10 ** 6))]
    ov = directed[0] if directed else min(mentioned, key=lambda v: first_seen.get(v, 10 ** 6))
    o_form = derive_span_facet(span, 'outcome', {ov: vocab[ov]}).evidence
    o_facet = Facet('outcome', ov, 'span', o_form)

    pol = pairs.get(ov, {})
    if len(pol) != 1:
        return o_facet, Facet('direction'), []     # no direction, or this outcome moves both ways
    cls, form = next(iter(pol.items()))
    return o_facet, Facet('direction', cls, 'span', form), []


def derive_direction(span: str, contract: ResearchContract, outcome_vocab: list[str]) -> Facet:
    """THE FACET THAT MANUFACTURES FALSE CONFLICTS. It returns UNKNOWN at the first sign of trouble.

    A DIRECTION IS ALWAYS THE DIRECTION *OF AN OUTCOME*. A bare "positive" is not a fact about the
    world; it is a fact about some quantity, and if we do not know which quantity, we know nothing.
    So `outcome_vocab` is the vocabulary of THIS CARD'S PRIMARY OUTCOME -- not of outcomes in general.
    The first version of this function took every outcome pattern at once, and duly read

        "the model improves prediction accuracy; employment is measured separately"

    as a POSITIVE finding about EMPLOYMENT, because 'improves' fell within eight tokens of 'employment'.
    Pair that card with any negative employment card and the planner would have "discovered" a conflict
    between a paper about prediction accuracy and a paper about jobs, then dissolved it by pointing at
    the unit of analysis. A false reconciliation, assembled entirely from true particulars, and no
    downstream gate on earth would catch it: every word of the resulting sentence is true.

    A direction is assigned ONLY when, in the verbatim span:
       (a) a polarity cue and a cue for THIS CARD'S OUTCOME stand IN THE SAME CLAUSE (polarity flips at
           a contrastive connective, so a cue may not reach across one) and within DIR_WINDOW tokens;
       (b) no negator sits within NEG_WINDOW tokens before the cue -- a negated cue is DISCARDED, never
           FLIPPED, because flipping is an inference and inference is what we are refusing;
       (c) exactly ONE polarity class survives across all such clauses. A span that reports the outcome
           falling in one clause and rising in another is UNKNOWN, not a conflict we get to adjudicate.
    Measured on this corpus: 82/133 spans carry no polarity cue at all. Roughly three quarters of the
    corpus is direction-UNKNOWN and can never enter a conflict bundle. That is the honest number, and it
    is the whole reason this function exists.
    """
    if not outcome_vocab:
        return Facet('direction')
    neg_pats = contract.negators
    survivors: dict[str, str] = {}
    for clause in _clauses(span):
        out_idx = [i for i, _ in _match_spans(clause, outcome_vocab)]
        if not out_idx:
            continue                                         # this clause is not about our outcome
        neg_idx = {i for i, _ in _match_spans(clause, neg_pats)}
        for cls, pats in contract.polarity.items():
            for ti, form in _match_spans(clause, pats):
                if not any(abs(ti - oi) <= DIR_WINDOW for oi in out_idx):
                    continue                                 # cue is too far from the outcome it governs
                if any(0 < ti - ni <= NEG_WINDOW for ni in neg_idx):
                    continue                                 # negated: DISCARD, do not flip
                survivors.setdefault(cls, form)
    if len(survivors) != 1:
        return Facet('direction')                            # no cue, or the outcome moves both ways
    cls, form = next(iter(survivors.items()))
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


def span_eligibility(span: str, contract: ResearchContract) -> tuple[list[str], list[str]]:
    """IS THIS SPAN THE PAPER'S OWN, MEASURED FINDING? Two failures, two DIFFERENT severities.

      SECOND-HAND (fatal) -- the span reports somebody ELSE'S study. The finding, and the figure, belong
        to a paper we have not read and are not citing. Printing it under this paper's name is a
        fabricated binding: "Writing in the Eurasian Business Review in 2021, Damioli et al. show that
        [Graetz and Michaels' result, and their number]". Such a card may not be attributed AT ALL, and
        may not enter a comparison. This is fraud, and it is invisible to every gate we have, because
        the span check asks "is this text in the paper?" and never "is this FINDING the paper's OWN?"

      FORECAST (soft) -- the span projects rather than measures. Nothing was estimated, so there is
        nothing to weigh against an estimate, and a projection placed in "conflict" with a measurement
        is a manufactured conflict. But it remains perfectly CITABLE as what it is -- an argument, an
        expectation -- so it is barred from COMPARISONS ONLY. Barring it from the prose as well would
        starve the corpus, and a gate that eats its own evidence is a failure this codebase has already
        paid for once.

    Returns (fatal, soft). Nothing is repaired; everything is recorded and counted.
    """
    fatal, soft = [], []
    for pat in contract.secondhand_cues:
        m = re.search(pat, span, re.I)
        if m:
            fatal.append(f'SECOND_HAND: the span reports another study ("{m.group(0)[:40]}") -- the '
                         f'finding is not this paper\'s own')
            break
    for pat in contract.forecast_cues:
        m = re.search(pat, span, re.I)
        if m:
            soft.append(f'FORECAST: the span projects rather than measures ("{m.group(0)[:30]}") -- '
                        f'citable as an argument, but there is no estimate to adjudicate')
            break
    return fatal, soft


@dataclass
class CardFacets:
    card_id: str
    doi: str
    facets: dict[str, Facet]
    outcomes_all: list[str]
    industries_all: list[str]
    numbers: list[str]
    ineligibility: list[str] = field(default_factory=list)     # FATAL: may not be attributed at all
    not_adjudicable: list[str] = field(default_factory=list)   # SOFT: citable, but not a comparison term

    def f(self, name: str) -> Facet:
        return self.facets.get(name, Facet(name))

    @property
    def quantitative(self) -> bool:
        return bool(self.numbers)

    @property
    def eligible(self) -> bool:
        """May this card be an ATTRIBUTED clause under its OWN authors' names? (No, if second-hand.)"""
        return not self.ineligibility

    @property
    def adjudicable(self) -> bool:
        """May this card be a TERM IN A COMPARISON? (No, if second-hand OR a projection.)"""
        return not self.ineligibility and not self.not_adjudicable


def derive_facets(card: dict, contract: ResearchContract) -> CardFacets:
    """The 8-facet key. DECLARED fields are read off the card; the rest come from the SPAN, or are MISSING."""
    span = card.get('span') or ''
    fx: dict[str, Facet] = {}
    for fname, field_name in contract.declared_facets.items():
        v = (card.get(field_name) or '').strip()
        fx[fname] = Facet(fname, v, 'declared') if v else Facet(fname)
    for fname, vocab in contract.span_facets.items():
        fx[fname] = derive_span_facet(span, fname, vocab)
    # OUTCOME AND DIRECTION ARE DERIVED TOGETHER. Derived apart, they need not be about each other --
    # and on the real corpus they were not. This OVERWRITES the independent outcome tag above.
    o_facet, d_facet, ambiguous = derive_outcome_direction(span, contract)
    fx[contract.outcome_facet] = o_facet
    fx['direction'] = d_facet
    _elig = span_eligibility(span, contract)
    return CardFacets(
        card_id=card['id'], doi=card.get('doi', ''), facets=fx,
        outcomes_all=derive_span_facet_all(span, 'outcome', contract.span_facets.get('outcome', {})),
        industries_all=derive_span_facet_all(span, 'industry', contract.span_facets.get('industry', {})),
        numbers=span_numbers(card),
        ineligibility=_elig[0], not_adjudicable=_elig[1] + ambiguous,
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
    evidence_tier: str = ''         # estimates | findings | positions -- WHAT KIND of thing conflicts

    def key(self) -> tuple:
        return (self.kind, self.axis, tuple(sorted(self.card_ids)))


def _evidence_tier(a: CardFacets, b: CardFacets, contract: ResearchContract) -> str:
    """WHAT KIND OF THING IS IN TENSION HERE? The verdict is only allowed to say what is true of it.

    'The evidence conflicts' is a claim ABOUT EVIDENCE. Two theoretical models that reach opposite
    conclusions are not evidence in conflict -- they are FRAMEWORKS in disagreement, and a review that
    reports the second as the first has overstated the literature. This tier decides which sentence the
    planner is permitted to license, and it is the difference between an adjudication and an overclaim.
    """
    emp = set(contract.empirical_designs)
    ma, mb = a.f('method'), b.f('method')
    a_emp = ma.known and ma.value in emp
    b_emp = mb.known and mb.value in emp
    if not a_emp and not b_emp:
        return 'positions'                      # two models/reviews: frameworks disagree, not evidence
    if a_emp != b_emp:
        # ONE MODEL, ONE MEASUREMENT. This is neither "the frameworks disagree" nor "the estimates
        # disagree" -- it is a prediction that has not been reconciled with the one measurement we hold,
        # and saying exactly that is both true and more interesting than either alternative. Both of the
        # genuine conflicts this corpus actually contains are of this kind.
        return 'model_vs_measurement'
    if a.quantitative and b.quantitative:
        return 'estimates'
    return 'findings'


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

    # A SECOND-HAND OR FORECAST SPAN IS NOT A TERM IN AN ARGUMENT. Excluded here, at the source, so no
    # bundle anywhere downstream can be built on one. Before this line, FOUR of the five "genuine
    # conflicts" this planner found were artifacts: the top-scoring one set Acemoglu's theoretical model
    # against a World Economic Forum press-release projection quoted inside a review paper, and called it
    # a conflict in the literature.
    eligible = [c for c in cfs if c.adjudicable]

    def pair_ok(a: CardFacets, b: CardFacets) -> bool:
        # A CARD CANNOT BE COMPARED WITH ITSELF, AND A PAPER CANNOT CORROBORATE ITSELF.
        # synthesis_contract rejects this as `premises_share_a_single_source`; we must not hand the
        # writer a "comparison" that its own gate will refuse. (Damioli 2021 carries three productivity
        # cards at two levels -- a tempting, and entirely invalid, level contrast.)
        return a.doi != b.doi

    for a, b in itertools.combinations(eligible, 2):
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
        tier = _evidence_tier(a, b, contract)
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
                operation='CONTRASTS_LEVEL', apparent_conflict=apparent, evidence_tier=tier,
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
                    operation='CONTRASTS_DIRECTION', apparent_conflict=True, evidence_tier=tier,
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
                    operation='RANK_EVIDENCE', apparent_conflict=False, evidence_tier=tier,
                    comparable=comparable, incomparability=why, score=sc + 1,
                    note='the same directional finding survives a change of identification strategy'))

        # ---- 4. SAME OUTCOME, DIFFERENT HORIZON (only when BOTH declare one -- 43% do not)
        if ha.known and hb.known and ha.value != hb.value:
            out.append(Bundle(
                kind='SAME_OUTCOME_DIFFERENT_HORIZON', axis='horizon',
                card_ids=[a.card_id, b.card_id], shared=shared,
                varies={a.card_id: ha.value, b.card_id: hb.value},
                operation='CONTRASTS_HORIZON', apparent_conflict=apparent, evidence_tier=tier,
                comparable=comparable, incomparability=why, score=sc,
                note='' if apparent else 'no apparent conflict: this is a horizon SPREAD, not a horizon '
                                         'DISPUTE'))

    # ---- 5. THE REFUSALS. Two cards on the same outcome whose axis is NOT DECLARED are NOT a comparison.
    #         We emit them so the refusal is VISIBLE and auditable, instead of silently inventing a tag.
    for a, b in itertools.combinations(eligible, 2):
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
    for c in eligible:
        o, u = c.f('outcome'), c.f('unit_of_analysis')
        if o.known and u.known:
            cell.setdefault((o.value, u.value), set()).add(c.doi)
    for c in eligible:
        o, u = c.f('outcome'), c.f('unit_of_analysis')
        if not (o.known and u.known):
            continue
        if len(cell[(o.value, u.value)]) == 1 and c.quantitative:
            out.append(Bundle(
                kind='UNCOUNTERED', axis='unit_of_analysis', card_ids=[c.card_id],
                shared={'outcome': o.value, 'unit_of_analysis': u.value}, varies={},
                operation='COVERAGE_GAP', apparent_conflict=False, comparable=False,
                evidence_tier=('estimates' if c.quantitative else 'findings'),
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

def _anchor_forms(bundle: Bundle, cf: dict[str, CardFacets]) -> tuple[str, str]:
    """THE VERBATIM SURFACE FORMS, LIFTED FROM THE SPANS. Two jobs, both load-bearing.

    1. THE SOURCE'S OWN WORD. The facet VALUE is our canonical label ('wages'); the span may say
       'earnings'. A verdict that says "wages" about a paper that said "earnings" has quietly restated
       the source in our vocabulary -- and it also fails to anchor, because 'wages' is nowhere in the
       span. Using the matched surface form fixes the faithfulness and the anchoring at one stroke.
    2. ANCHORING. `synthesis_contract.validate()` requires a synthesis to share >= 2 content lemmas with
       its premises, and it rejected 7 of our verdicts for exactly this. A form lifted verbatim from a
       span is guaranteed to be in that span, so anchoring becomes a property of construction rather
       than a hope.
    """
    forms: list[str] = []
    for cid in bundle.card_ids:
        c = cf.get(cid)
        if not c:
            continue
        for fname in ('outcome', 'technology', 'direction', 'industry'):
            ev = c.f(fname).evidence
            if ev and len(ev) >= 4 and ev.lower() not in [f.lower() for f in forms]:
                forms.append(ev)
    primary = cf[bundle.card_ids[0]].f('outcome').evidence or bundle.shared.get('outcome', 'the outcome')
    second = next((f for f in forms if f.lower() != primary.lower()), '')
    return primary, second


def _verdict_text(bundle: Bundle, cf: dict[str, CardFacets]) -> str:
    o, o2 = _anchor_forms(bundle, cf)
    ids = bundle.card_ids
    ctx = f' in studies of {o2}' if o2 else ''   # number-agnostic: the surface form may be sing. or pl.
    if bundle.kind == 'SAME_OUTCOME_DIFFERENT_UNIT':
        ua, ub = (bundle.varies[i] for i in ids)
        if bundle.apparent_conflict:
            return (f'These {o} findings are not contradictory{ctx}: the two estimates observe '
                    f'different units of analysis, and the evidence establishes the effect at the '
                    f'{ua} level without establishing it at the {ub} level.')
        return (f'The evidence on {o} is limited to two different units of analysis{ctx}, and the '
                f'estimates do not speak to the same quantity: what holds at the {ua} level does not '
                f'establish a comparable result at the {ub} level.')
    if bundle.kind == 'SAME_UNIT_OPPOSITE_DIRECTION':
        u = bundle.shared.get('unit_of_analysis', 'the same')
        # THE VERDICT MAY ONLY SAY WHAT IS TRUE OF THE THING IN TENSION. Two theoretical models reaching
        # opposite conclusions are NOT "the evidence" conflicting, and a review that says so has
        # overstated its own literature -- the quietest and most respectable way to lie.
        if bundle.evidence_tier == 'positions':
            return (f'The literature on {o} at the {u} level does not speak with one voice, but the '
                    f'disagreement is between frameworks rather than between measurements: what is in '
                    f'tension is how the process is modelled, and the evidence does not settle it.')
        if bundle.evidence_tier == 'model_vs_measurement':
            return (f'What the {o} literature sets against itself at the {u} level is a model and a '
                    f'measurement, not two measurements: the theoretical account and the observed '
                    f'result point in opposite directions, and the evidence is limited to a single '
                    f'design, so the prediction has not yet been confronted with enough measurement '
                    f'to be either established or overturned.')
        thing = 'estimates' if bundle.evidence_tier == 'estimates' else 'findings'
        return (f'The evidence on {o} at the {u} level genuinely conflicts{ctx}: the {thing} point in '
                f'opposite directions at the same unit of analysis, so the difference cannot be '
                f'dissolved by appeal to level, and it remains unresolved.')
    if bundle.kind == 'SAME_FINDING_DIFFERENT_METHOD':
        ma, mb = (bundle.varies[i] for i in ids)
        return (f'The {o} finding{ctx} rests on a {ma} design in one case and a {mb} design in the '
                f'other; the evidence therefore establishes it more securely than either study alone.')
    if bundle.kind == 'SAME_OUTCOME_DIFFERENT_HORIZON':
        ha, hb = (bundle.varies[i] for i in ids)
        return (f'These {o} estimates differ because they observe different time horizons{ctx}: the '
                f'evidence is limited to the {ha} in one case and the {hb} in the other, and cannot '
                f'distinguish a transitional effect from a settled one.')
    if bundle.kind == 'UNCOUNTERED':
        u = bundle.shared.get('unit_of_analysis', '')
        return (f'The {o} result at the {u} level rests on a single source{ctx}, and no other study in '
                f'this literature examines the same outcome at the same unit of analysis; the evidence '
                f'is therefore limited to that setting and cannot distinguish a general pattern from a '
                f'feature of one design.')
    return ''


def _boundary_text(bundle: Bundle, cf: dict[str, CardFacets]) -> str:
    o, _o2 = _anchor_forms(bundle, cf)
    if bundle.incomparability:
        return (f'What the evidence does not settle is the magnitude: the estimates on {o} are not on '
                f'the same footing, and the literature cannot distinguish a real difference from an '
                f'artefact of how each was measured.')
    return (f'What the evidence does not settle is whether the {o} result extends beyond the units and '
            f'horizons these designs observe.')


_BRIDGE = {
    'unit_of_analysis': ('the evidence just reviewed observes the {a} level, and cannot establish what '
                         'happens once these effects aggregate; the estimates that follow observe the '
                         '{b} level'),
    'method': ('the finding above rests on a {a} design; what follows asks whether it survives a {b} '
               'design'),
    'horizon': ('the estimates above are limited to the {a}; what follows observes the {b}'),
    'outcome': ('the evidence above speaks to {a}; the estimates that follow measure {b}'),
    'industry': ('the evidence above is drawn from {a}; what follows asks whether it holds in {b}'),
}


def _bridge_text(axis: str, a: str, b: str) -> str:
    """AN ANALYTICAL MOVEMENT ALONG A NAMED AXIS. Never "Turning now to". If no axis moves between two
    subsections, there is no movement to narrate and the planner emits NOTHING -- an invented transition
    is a claim that an argument advanced when it did not."""
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

    def roles_for(sub: str) -> list[str]:
        for pat, kinds in contract.adjudicative_roles.items():
            if re.search(pat, sub, re.I):
                return kinds
        return []

    # PASS 1: THE ADJUDICATIVE SUBSECTIONS GET FIRST PICK. They are about the argument itself, so they
    # are matched on bundle KIND, not on lexical overlap -- "Where the literature genuinely disagrees"
    # shares no content word with any evidence card, and a lexical matcher hands it nothing at all. It
    # was handed nothing, which is precisely how a Critical Synthesis section ends up 210 words long.
    preassigned: dict[str, Bundle] = {}
    for _sec, sub in jobs:
        kinds = roles_for(sub)
        if not kinds:
            continue
        cand = [b for b in real if b.kind in kinds and b.key() not in used]
        cand.sort(key=lambda b: (kinds.index(b.kind), -b.score))
        if cand:
            preassigned[sub] = cand[0]
            used.add(cand[0].key())

    for sec, sub in jobs:
        refusals: list[str] = []
        # ONLY ELIGIBLE CARDS MAY BE ATTRIBUTED. A second-hand span ("Graetz and Michaels (2018) ...
        # find that ...", sitting inside Damioli 2021) would otherwise be printed as "Writing in the
        # Eurasian Business Review in 2021, Damioli et al. show that ..." -- crediting one paper with
        # another's finding and another's figures.
        pool = [c for c in cards if cf_by_id[c['id']].eligible]
        n_drop = len(cards) - len(pool)
        scored = sorted(((_relevance(sub, cf_by_id[c['id']], c), c) for c in pool),
                        key=lambda x: -x[0])
        sel = [c for s, c in scored[:12] if s > 0]
        sel_ids = {c['id'] for c in sel}

        # THE COMPARISON: an adjudicative subsection already claimed one by KIND in pass 1. A topical
        # subsection takes the highest-value bundle whose BOTH cards are relevant to it and which no
        # earlier subsection has argued. A bundle is NEVER reused -- 41 exact repetitions is what
        # happens when 222 card slots are drawn from 82 cards with no bookkeeping anywhere.
        bundle = preassigned.get(sub)
        if bundle is None:
            cand = [b for b in real if b.key() not in used and set(b.card_ids) <= sel_ids]
            cand.sort(key=lambda b: -b.score)
            bundle = cand[0] if cand else None
            if bundle:
                used.add(bundle.key())
        if bundle is None:
            refusals.append('no comparison bundle available whose cards are both relevant here -- this '
                            'subsection can REPORT but must not ADJUDICATE')
        else:
            # an adjudicative subsection is argued FROM its bundle, so its cards must be in scope
            sel_ids |= set(bundle.card_ids)
            sel = sel + [cards_by_id[c] for c in bundle.card_ids if c not in {x['id'] for x in sel}]

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

    mk = lambda i, doi, span, lvl, meth, hor: {
        'id': i, 'doi': doi, 'span': span, 'claim': 'IGNORED — model-authored', 'level': lvl,
        'method': meth, 'horizon': hor, 'mechanisms': [], 'authors': ['Solo'], 'year': 2020,
        'venue': 'J', 'attribution': 'Writing in J in 2020, Solo', 'source': 'Solo (2020), J',
        'has_number': True}
    # Direction is exercised THROUGH derive_facets -- the real path, including the binding of direction
    # to the card's PRIMARY outcome. A test that calls the function in isolation tests a function; the
    # bug that shipped here last time lived in the WIRING, not in the function.
    dirof = lambda span: derive_facets(mk('t', '10.0/t', span, 'firm', 'observational', 'long-run'),
                                       ct).f('direction')

    # 1. a span with NO polarity cue must NOT get a direction
    d = dirof('we estimate the probability of computerisation for 702 detailed occupations')
    check('no polarity cue -> direction is UNKNOWN (cannot enter a conflict)', not d.known,
          f'assigned {d.value}' if d.known else '')

    # 2. THE SAME OUTCOME MOVING BOTH WAYS IS UNKNOWN -- not a conflict for us to adjudicate
    d2 = dirof('employment fell in manufacturing but employment rose in services')
    check('the SAME outcome moving both ways -> UNKNOWN (we do not get to pick one)',
          not d2.known, f'assigned {d2.value}' if d2.known else '')

    # 3. NEGATION IS DISCARDED, NEVER FLIPPED
    d3 = dirof('we find no significant increase in employment in the treated regions')
    check('a negated cue is DISCARDED, not flipped (flipping is inference)',
          d3.value != 'positive', f'read a negated "increase" as {d3.value}')

    # 4. THE CROSS-QUANTITY LEAK. A cue governing ANOTHER quantity must never become this outcome's
    #    direction. This attack FAILED on the first build: 'improves prediction accuracy' was read as a
    #    positive EMPLOYMENT finding because it fell within eight tokens of the word 'employment'.
    d4 = dirof('the model improves prediction accuracy; employment is measured separately')
    check('a polarity cue governing ANOTHER quantity is not this outcome\'s direction',
          not d4.known,
          f'read "improves prediction accuracy" as a {d4.value} EMPLOYMENT finding' if d4.known else '')

    # 4b. ...but a contrastive span still yields the direction of ITS OWN primary outcome
    d4b = dirof('robots reduce employment while raising the productivity of the firm')
    check('a contrastive span still resolves the PRIMARY outcome (employment: negative)',
          d4b.value == 'negative', f'got {d4b.value or "UNKNOWN"} for a span that says employment fell')

    # 4c. THE ADVERB TRAP -- found by reading the REAL output, not by writing a test. This exact span
    #     produced the planner's TOP-RANKED "genuine conflict": 'increasingly' modifies DEPENDENT, and
    #     says nothing whatever about the level of employment.
    d4c = dirof('employment of the less-skilled is increasingly dependent on physical proximity to '
                'the more-skilled')
    check('"increasingly dependent" is NOT a positive employment finding (the adverb trap)',
          not d4c.known,
          f'read an adverb of degree as a {d4c.value} direction -- this fabricated a conflict')

    # 4d. THE COMPOUND-NOUN TRAP -- 'job satisfaction' is not employment, and was the OTHER half of
    #     that same fabricated conflict.
    jf = derive_facets(mk('j', '10.7/s', 'fear of future replacement does negatively affect workers\' '
                                         'job satisfaction at present', 'worker', 'quasi-experimental',
                          'short-run'), ct)
    check('"job satisfaction" is not the EMPLOYMENT outcome (the compound-noun trap)',
          jf.f('outcome').value != 'employment',
          f'tagged outcome={jf.f("outcome").value} from the word "job" in "job satisfaction"')

    # 4f. THE JOINT-DERIVATION ATTACK, TAKEN VERBATIM FROM ACEMOGLU AND RESTREPO 2018. Derived apart,
    #     outcome and direction were not even about each other: outcome=SKILLS (the earliest outcome
    #     word) and direction=POSITIVE (from 'increases', which belongs to INEQUALITY). That pair became
    #     the planner's top-ranked GENUINE CONFLICT.
    acem = derive_facets(mk('ac', '10.a/1', 'In an extension with heterogeneous skills, we show that '
                                            'inequality increases during transitions driven by '
                                            'automation', 'worker', 'theory', ''), ct)
    check('outcome is the quantity WHOSE CHANGE IS REPORTED, not the first one mentioned',
          acem.f('outcome').value == 'inequality' and acem.f('direction').value == 'positive',
          f'tagged outcome={acem.f("outcome").value or "NONE"} / '
          f'direction={acem.f("direction").value or "NONE"} -- these are not about each other')

    # 4g. NEAREST-CUE ATTACHMENT. A span carrying several directed outcomes must bind each direction to
    #     the quantity it actually governs, and must never let one outcome inherit another's direction.
    many = derive_facets(mk('mn', '10.b/2', 'employment fell and wages declined, but productivity '
                                            'increased across the sample', 'firm', 'observational',
                            'long-run'), ct)
    check('each direction binds to the outcome it GOVERNS (employment: negative, not productivity\'s +)',
          many.f('outcome').value == 'employment' and many.f('direction').value == 'negative',
          f'outcome={many.f("outcome").value} direction={many.f("direction").value} -- an outcome '
          f'inherited a direction that belongs to another quantity')

    # 4h. THE ATTENUATOR TRAP -- "SLOWER GROWTH" IS NOT A POSITIVE FINDING. Verbatim from Acemoglu and
    #     Restrepo 2019, where the bare cue 'growth' read a passage about DISPLACEMENT as POSITIVE.
    d4h = dirof('the slower growth of employment over the last three decades is accounted for by an '
                'acceleration in the displacement effect')
    check('"slower growth" is not a positive finding (the attenuator trap)',
          d4h.value != 'positive',
          f'read "slower growth of employment" as a {d4h.value} finding')

    # 4e. TWO THEORY PAPERS DISAGREEING IS NOT "THE EVIDENCE CONFLICTING"
    t1 = mk('t1', '10.8/a', 'automation reduces employment in the model', 'economy', 'theory', 'long-run')
    t2 = mk('t2', '10.9/b', 'automation creates employment through new tasks', 'economy', 'theory',
            'long-run')
    t2['authors'] = ['Duo']
    cft = [derive_facets(c, ct) for c in (t1, t2)]
    bt = [b for b in find_bundles(cft, ct, {c['id']: c for c in (t1, t2)})
          if b.kind == 'SAME_UNIT_OPPOSITE_DIRECTION']
    vtt = _verdict_text(bt[0], {c.card_id: c for c in cft}) if bt else ''
    check('two THEORY papers in tension -> "frameworks", never "the evidence genuinely conflicts"',
          bool(bt) and bt[0].evidence_tier == 'positions' and 'genuinely conflicts' not in vtt,
          f'OVERCLAIM: "{vtt[:78]}"')

    # 5. TWO CARDS FROM ONE PAPER ARE NOT A COMPARISON
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

    # 11. THE SECOND-HAND SPAN. Verbatim in the paper; the finding is somebody else's. THE SPAN GATE
    #     CANNOT SEE THIS -- it asks "is this text in the paper?", never "is this finding the paper's
    #     own?" -- and it is live on disk in the real corpus (5 cards, 6 misbindable figures).
    sh = mk('sh', '10.3/z', 'Graetz and Michaels (2018) use country-level data on industrial robots '
                            'and find that they raised labor productivity by 15 percent.',
            'economy', 'observational', 'long-run')
    shf = derive_facets(sh, ct)
    check('a SECOND-HAND span cannot be attributed to the paper that merely quotes it',
          not shf.eligible, (shf.ineligibility or ['ADMITTED — it would print Graetz and Michaels\' '
                                                   'finding under Damioli\'s name'])[0][:88])

    # 12. A PROJECTION IS NOT A FINDING and may not be a term in a conflict -- but it stays CITABLE.
    fc = mk('fc', '10.4/w', 'the adoption of AI will make 75 million jobs redundant and create 133 '
                            'million new roles', 'economy', 'review', 'long-run')
    fcf = derive_facets(fc, ct)
    check('a FORECAST span cannot be a term in a comparison', not fcf.adjudicable,
          (fcf.not_adjudicable or ['ADMITTED — a press-release projection would be "adjudicated" '
                                   'against a measured estimate'])[0][:88])
    check('...but a FORECAST is still CITABLE as an argument (a gate must not eat its own evidence)',
          fcf.eligible, 'the forecast was barred from the prose entirely -- the corpus is starving')

    # 12b. THE FALSE POSITIVE THAT KILLED A FRAMEWORK. "a prediction technology" is the SUBJECT MATTER
    #      of Prediction Machines, not a forecast. A bare \\bpredict\\w* cue deleted Agrawal entirely.
    pm = mk('pm', '10.6/u', 'Recent advances in artificial intelligence are primarily driven by machine '
                            'learning, a prediction technology, lowering the cost of prediction',
            'task', 'theory', 'long-run')
    pmf = derive_facets(pm, ct)
    check('the NOUN "prediction" is technical vocabulary, not a forecast (do not delete the framework)',
          pmf.eligible and pmf.adjudicable,
          f'Prediction Machines was excluded as a forecast: {(pmf.not_adjudicable or [""])[0][:60]}')

    # 13. ...and neither can reach a BUNDLE. (The real corpus built 4 of its 5 "genuine conflicts" on
    #     exactly these before they were excluded.)
    real_c = mk('ok', '10.5/v', 'automation reduces employment across the economy', 'economy',
                'observational', 'long-run')
    real_c['authors'] = ['Duo']
    pool = [sh, fc, real_c]
    cfp = [derive_facets(c, ct) for c in pool]
    bp = [b for b in find_bundles(cfp, ct, {c['id']: c for c in pool}) if b.kind != 'NOT_A_COMPARISON']
    tainted = [b for b in bp if {'sh', 'fc'} & set(b.card_ids)]
    check('no bundle anywhere can be built on a second-hand or forecast span',
          not tainted, f'{len(tainted)} tainted bundle(s) formed')

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

    inelig = [c for c in cfs if not c.eligible]
    soft = [c for c in cfs if c.eligible and not c.adjudicable]
    if inelig:
        print(f'\n--- {len(inelig)} SECOND-HAND CARDS: THE FINDING IS NOT THIS PAPER\'S OWN ---')
        print('    A span can be VERBATIM in the paper and still not be the paper\'s finding. The span')
        print('    gate cannot see this -- it asks "is this text in the paper?", never "is this FINDING')
        print('    the paper\'s OWN?" Each of these would print A DIFFERENT PAPER\'S RESULT under the')
        print('    named authors. This is the fabricated-binding failure, live on disk.')
        for c in inelig:
            card = cards_by_id[c.card_id]
            print(f'\n      [{_short(card):<16}] {c.ineligibility[0][:92]}')
            if c.numbers:
                print(f'          FIGURES THAT WOULD BE MISATTRIBUTED: {c.numbers}')
            print(f'          would print as: "{(card.get("attribution") or "")[:60]}..."')
            print(f'          span: "{re.sub(chr(10), " ", card.get("span") or "")[:94]}..."')
    if soft:
        print(f'\n--- {len(soft)} FORECAST CARDS: citable, but barred from every comparison ---')
        print('    Nothing was measured, so there is no estimate to weigh. Putting one of these in')
        print('    "conflict" with a measured result manufactures the conflict.')
        for c in soft[:6]:
            card = cards_by_id[c.card_id]
            figs = f'  figures={c.numbers}' if c.numbers else ''
            print(f'      [{_short(card):<16}]{figs}  "{re.sub(chr(10), " ", card.get("span") or "")[:74]}..."')

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
