"""Comparison-bundle builder — decides WHAT IS BEING COMPARED WITH WHAT, from the
champion corpus, before a word of the writer's synthesis/policy/conclusion prose exists.

Ported (with the corpus adaptations forced by the champion schema) from the cellcog
argument planner (READ-ONLY source in the flywheel tree,
``/home/polaris/wt/flywheel/scripts/argument_planner.py``). The cellcog originals this
ports, and what each contributes, are:

  * ``derive_facets`` (``:741``) / ``derive_span_facet`` (``:484``) /
    ``derive_outcome_direction`` (``:511``) — the 8-facet key, every facet matched
    VERBATIM against the span (here ``direct_quote``), outcome+direction derived
    JOINTLY so a polarity cue governs the nearest outcome in the same clause.
  * ``span_eligibility`` (``:671``) — the two firewalls. SECOND_HAND (fatal — the span
    reports ANOTHER paper's finding; bars attribution AND comparison) and FORECAST
    (soft — a projection; bars comparison only). This is the highest-value import for a
    web-scraped corpus full of third-party attributions inside surveys and blogs.
  * ``_comparability`` (``:831``) — two estimates are on the same footing only if BOTH
    are quantitative, BOTH use an ``empirical_designs`` method, and they share outcome,
    unit and horizon. Every mismatch appends a plain-English reason. This is the
    ``comparable`` + ``why`` the task asks for; it keeps every "X is bigger than Y" honest.
  * ``find_bundles`` (``:890``) — over eligible/adjudicable pairs sharing a KNOWN
    outcome, emits typed bundles (SAME_OUTCOME_DIFFERENT_UNIT, SAME_UNIT_OPPOSITE_
    DIRECTION, SAME_FINDING_DIFFERENT_METHOD, SAME_OUTCOME_DIFFERENT_HORIZON, the
    auditable NOT_A_COMPARISON refusals, single-occupant UNCOUNTERED boundaries).

THE CORPUS MISMATCH (the whole engineering problem)
---------------------------------------------------
The cellcog planner reads three DECLARED facets (level/method/horizon) straight off a
pre-faceted card. The champion corpus (``data/cp4_corpus_s3gear_329.json``, 997 evidence
rows) has NONE of them populated (0/997), and no ``span`` field either — the verbatim
text lives in ``direct_quote``. So this module derives ALL eight facets from scratch,
cheaply, regex-only, offline, from ``direct_quote``. Where a cue is absent the facet is
left MISSING — MISSING correctly routes a pair to the auditable NOT_A_COMPARISON, which
is the whole cellcog thesis: an INFERRED facet is what manufactures a false reconciliation.

Two champion-native groupings are reused rather than reinvented:

  * ``same_work_groups`` (55) — the champion's native same-paper grouping. ``pair_ok``
    keys on shared ``same_work_id`` (NOT ``doi``): DOI is unreliable here (only 6 unique
    DOIs across 997 rows), so it cannot separate papers, but ``same_work_id`` can. A paper
    may not corroborate itself.
  * ``document_type`` — seeds the method facet (JOURNAL_ARTICLE/PREPRINT try quote cues;
    BLOG_COMMENTARY/REPORT/ENCYCLOPEDIA are non-empirical review/theory).

GUARANTEES
----------
Default-OFF behind ``PG_COMPARISON_BUNDLES`` (:func:`is_enabled`). ``build_comparison_
bundles`` returns ``[]`` unless the flag is set, so the OFF path is byte-identical. This
module is standalone: no wiring into the driver/generator, no import from the flywheel
demo fixture, no touch of ``provenance_generator.py`` or any strict_verify / citation
logic. The GenAI/labor vocabulary is carried in this module's OWN contract (the champion
corpus IS a GenAI/labor question, so it is correct FOR THIS CORPUS) and never becomes a
global default. MISSING facets are NEVER repaired by inference.
"""

from __future__ import annotations

import itertools
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ===================================================================== TUNING CONSTANTS
# (ported verbatim from argument_planner.py:283-291)

DIR_WINDOW = 8      # a polarity cue must sit within this many tokens of an outcome cue
NEG_WINDOW = 3      # a negator this close BEFORE a cue voids the cue (we discard; we never flip)

# A POLARITY FLIPS AT A CONTRASTIVE CONNECTIVE. "Robots reduce employment while raising
# productivity" is one span carrying two opposite findings about two different quantities;
# a cue may only be read as the direction of an outcome that stands IN ITS OWN CLAUSE.
_CLAUSE_BREAK = re.compile(
    r"[;:]|\bwhile\b|\bwhereas\b|\bbut\b|\balthough\b|\bthough\b|\bhowever\b|\byet\b|"
    r"\bby contrast\b|\bin contrast\b|\bon the other hand\b|\beven as\b",
    re.I,
)

_FUT_MODALS = {"will", "shall", "'ll", "wo"}                        # 'wo' is how "won't" tokenizes
_BE_FORMS = {"is", "are", "was", "were", "be", "been", "being", "am", "'s", "'re"}


# ===================================================================== THE CHAMPION CONTRACT
#
# DATA, NOT LOGIC. Compiled for THIS corpus's question ("the impact of Generative AI on the
# future labor market"). Every vocabulary below is a list of surface forms we expect to find
# IN A SPAN (here ``direct_quote``); they are matched verbatim and the matched form is
# recorded so a human can audit the tag. They are NOT a taxonomy of the world — they are a
# taxonomy of what the papers actually SAY, the only thing we are allowed to key on.
#
# This is a near-exact fit for cellcog's ``_ai_labor_demo_contract`` vocab (:173-238), which
# is production-forbidden in cellcog (Sol P1) precisely BECAUSE it hardwires AI/labor. For the
# champion this corpus IS GenAI/labor, so reusing the vocab is correct FOR THIS CORPUS. It is
# kept here, flag-gated, and is never a global default.


@dataclass
class ChampionContract:
    question: str
    span_facets: Dict[str, Dict[str, List[str]]]   # facet -> value -> [regex]
    polarity: Dict[str, List[str]]                  # direction class -> [regex]
    negators: List[str]
    unit_vocab: Dict[str, List[str]]                # unit_of_analysis value -> [regex]
    horizon_vocab: Dict[str, List[str]]             # horizon value -> [regex]
    method_cues: Dict[str, List[str]]               # method value -> [regex] (refine from quote)
    empirical_designs: List[str]
    secondhand_cues: List[str] = field(default_factory=list)
    forecast_cues: List[str] = field(default_factory=list)
    outcome_facet: str = "outcome"


# document_type -> a seed method BEFORE the quote is consulted. Empirical seeds are then
# refined by quote cues; non-empirical seeds (review/theory) are terminal.
_DOCTYPE_METHOD_SEED: Dict[str, str] = {
    "JOURNAL_ARTICLE": "observational",     # empirical by default; refine from quote cues
    "REVIEW_ARTICLE": "review",
    "PREPRINT": "observational",
    "REPORT": "review",
    "BLOG_COMMENTARY": "theory",
    "ENCYCLOPEDIA": "review",
    "BOOK": "theory",
}


def _champion_contract() -> ChampionContract:
    return ChampionContract(
        question="the impact of Generative AI on the future labor market",
        span_facets={
            "technology": {
                "generative_ai": [r"generative ai\w*", r"large language model\w*", r"\bllms?\b",
                                  r"chatgpt", r"\bgpt-?\d?\b", r"generative artificial intelligence"],
                "ai_ml": [r"artificial intelligence", r"\bai\b", r"machine learning",
                          r"deep learning", r"\balgorithm\w*"],
                "automation": [r"automat\w*"],
                "robotics": [r"\brobot\w*"],
            },
            "outcome": {
                # An outcome pattern must name the QUANTITY, not merely share a word with it.
                # `\bjobs?\b` guarded so "JOB SATISFACTION"/"job security" is not employment.
                "employment": [r"\bemployment\b", r"\bunemploy\w*", r"\bjob loss\w*",
                               r"\bjobs?\b(?!\s+(?:satisfaction|security|quality|content|title|"
                               r"description|design))",
                               r"\bworkforce\b", r"\bhiring\b", r"\blab(?:o|ou)r demand\b"],
                "wages": [r"wages?\b", r"earnings?\b", r"salar\w*", r"\bincome\b", r"compensation"],
                "productivity": [r"productivity", r"output per", r"efficiency"],
                "skills": [r"skills?\b", r"skilled\b", r"reskill\w*", r"upskill\w*",
                           r"human capital", r"competenc\w*", r"\btraining\b"],
                "tasks": [r"tasks?\b", r"\broutine\b", r"job content"],
                "inequality": [r"inequalit\w*", r"polari[sz]\w*", r"disparit\w*", r"wage gap"],
            },
            "industry": {
                "healthcare": [r"health ?care", r"\bmedical\b", r"\bclinical\b", r"\bnurs\w*",
                               r"\bpatients?\b", r"physician\w*"],
                "finance": [r"\bfinanc\w*", r"\bbank\w*", r"insurance", r"fintech"],
                "education": [r"education\w*", r"\bschools?\b", r"\bteach\w*", r"\bstudents?\b"],
                "creative": [r"\bcreative\b", r"journalis\w*", r"\bdesigners?\b", r"\bartists?\b",
                             r"\bwriters?\b", r"\bcontent creat\w*"],
                "software_dev": [r"\bprogramm\w*", r"\bsoftware develop\w*", r"\bcoders?\b",
                                 r"\bcoding\b", r"\bdevelopers?\b"],
                "customer_service": [r"customer (?:service|support)", r"call cent\w*"],
                "prof_services": [r"professional service\w*", r"\bconsult\w*", r"\blegal\b",
                                  r"\blawyer\w*"],
                "manufacturing": [r"manufactur\w*", r"\bfactor(?:y|ies)\b", r"assembly line"],
            },
            "geography": {
                "united_states": [r"united states", r"\bu\.s\.", r"\bus\b", r"american\b"],
                "europe": [r"\beurope\w*", r"\bgermany\b", r"\bfrance\b", r"united kingdom", r"\beu\b"],
                "china": [r"\bchina\b", r"\bchinese\b"],
                "developing": [r"developing countr\w*", r"\bemerging econom\w*", r"\bglobal south\b"],
            },
        },
        # DIRECTION: verbs and magnitude nouns only. No adverbs, no comparative adjectives
        # (they matched the wrong word and manufactured cellcog's top false conflict).
        polarity={
            "negative": [r"\breduc(?:e|es|ed|ing|tion|tions)\b", r"\bdeclin(?:e|es|ed|ing)\b",
                         r"\bfell\b", r"\bfalls?\b", r"\bfalling\b", r"\bdecreas(?:e|es|ed|ing)\b",
                         r"\bdisplac(?:e|es|ed|ing|ement)\b", r"\bloss(?:es)?\b", r"\bshrink\w*",
                         r"\bshrank\b", r"\bsubstitut(?:e|es|ed|ing|ion)\b", r"\bdestroy\w*",
                         r"\berod(?:e|es|ed|ing)\b", r"\bnegative\b", r"\bredundant\b", r"\bobsolete\b",
                         r"\breplac(?:e|es|ed|ing|ement)\b", r"\beliminat(?:e|es|ed|ing)\b",
                         r"\bthreaten\w*", r"\bat risk\b"],
            "positive": [r"\bincreas(?:e|es|ed|ing)\b",          # NOT "increasingly"
                         r"\brais(?:e|es|ed|ing)\b", r"\bris(?:e|es|ing)\b", r"\brose\b",
                         r"\bgrow(?:s|ing|th)?\b", r"\bgrew\b", r"\bgains?\b",
                         r"\bcreat(?:e|es|ed|ing|ion)\b", r"\bcomplement(?:s|ed|ing|arity)?\b",
                         r"\bexpand(?:s|ed|ing)?\b", r"\bexpansion\b", r"\bimprov(?:e|es|ed|ing)\b",
                         r"\baugment(?:s|ed|ing)?\b", r"\bpositive\b", r"\benhanc(?:e|es|ed|ing)\b",
                         r"\bboost\w*"],
            "null": [r"\bno significant\b", r"\bno effect\b", r"\bno evidence\b", r"\binsignificant\b",
                     r"\btoo small to detect\b", r"\bnot significant\b", r"\bunchanged\b",
                     r"\bno measurable\b"],
        },
        negators=[r"\bnot\b", r"\bno\b", r"\bnor\b", r"\bnever\b", r"\bwithout\b", r"\bneither\b",
                  r"\bfails? to\b", r"\bunable to\b", r"\bcannot\b", r"\bdoes ?n[o']t\b", r"\blittle\b",
                  r"\bslow(?:er|ing|ly)?\b", r"\bweak(?:er|ening)?\b", r"\bless\b", r"\bslower\b",
                  r"\bdampen\w*", r"\bmuted\b", r"\bmodest\b", r"\blimited\b"],
        unit_vocab={
            "firm": [r"\bfirm-level\b", r"\bfirm level\b", r"\bcompany-level\b", r"\bestablishment\b"],
            "worker": [r"\bworker-level\b", r"\bworker level\b", r"\bindividual worker\w*",
                       r"\bemployee-level\b"],
            "individual": [r"\bindividual-level\b", r"\bindividual level\b"],
            "task": [r"\btask-level\b", r"\btask level\b"],
            "occupation": [r"\boccupation-level\b", r"\boccupational\b", r"\boccupations?\b"],
            "country": [r"\bcountry-level\b", r"\bcross-country\b", r"\bnational-level\b",
                        r"\bmacroeconomic\b", r"\baggregate\b"],
            "industry": [r"\bindustry-level\b", r"\bsector-level\b", r"\bsectoral\b"],
        },
        horizon_vocab={
            "short_run": [r"\bshort[- ]?run\b", r"\bshort[- ]?term\b", r"\bimmediate\w*"],
            "long_run": [r"\blong[- ]?run\b", r"\blong[- ]?term\b", r"\bby 20[3-9]\d\b",
                         r"\bover the (?:next )?decades?\b"],
            "medium_run": [r"\bmedium[- ]?run\b", r"\bmedium[- ]?term\b",
                           r"\bwithin \d+ years?\b"],
        },
        # Refinement cues, applied only when the doctype seed is empirical.
        method_cues={
            "experiment": [r"\brandomi[sz]ed\b", r"\bexperiment\w*", r"\brct\b",
                           r"\bcontrolled trial\b", r"\bfield experiment\b"],
            "quasi-experimental": [r"\bdifference-in-differences\b", r"\bdiff-in-diff\b",
                                   r"\bregression discontinuity\b", r"\binstrumental variable\w*",
                                   r"\bnatural experiment\b", r"\bquasi-experiment\w*"],
            "survey": [r"\bsurvey\b", r"\bquestionnaire\b", r"\bself-reported\b"],
            "observational": [r"\bregression\b", r"\bpanel data\b", r"\bempirical\w*",
                              r"\bobservational\b", r"\bcorrelation\w*"],
        },
        empirical_designs=["experiment", "quasi-experimental", "observational", "survey"],
        # SECOND_HAND / FORECAST cues port UNCHANGED (argument_planner.py:268-306) — the
        # highest-value import for this web-scraped serper corpus.
        secondhand_cues=[
            r"\b[A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+)?\s*\(\s*(?:19|20)\d\d\s*\)",
            r"\bet al\.\s*\(\s*(?:19|20)\d\d", r"\bcommission\s*\(\s*(?:19|20)\d\d",
            r"\b[A-Z][a-z]+(?:\s+(?:and|&)\s+[A-Z][a-z]+|\s+et al\.?)?\s+"
            r"(?:demonstrated|demonstrates|showed|shows|shown|found|finds|reported|reports|"
            r"argued|argues|documented|documents|observed|observes|noted|notes|concluded|"
            r"concludes|suggested|suggests|claimed|claims|established|establishes|revealed|"
            r"reveals|proved|proves|proven)\s+that\b",
            r"\btheir (?:results|findings|study|analysis|paper|estimates|data)\b",
            r"\baccording to\b", r"\bhas predicted\b", r"\bhave (?:shown|found|argued|documented)\b",
            r"\b(?:studies|scholars|researchers|authors|others) (?:have )?(?:show|find|argue|suggest)",
            r"\b(?:world economic forum|mckinsey|oecd|gartner|pwc|deloitte|goldman sachs)\b",
        ],
        forecast_cues=[r"\bwill\b", r"\bis going to\b", r"\bby 20[3-9]\d\b",
                       r"\b(?:is|are|was|were|has been|have been|being|be) (?:predicted|expected|"
                       r"projected|forecast|anticipated|poised|slated|set|likely|on track|about|going) "
                       r"to\b",
                       r"\b(?:anticipated|poised|slated|expected|projected|forecast) to\b",
                       r"\b(?:predicts|predicted|forecasts|projects|anticipates|anticipated) that\b",
                       r"\bhas predicted\b", r"\bexpected to\b"],
    )


# ===================================================================== FACETS
# (Facet / _tokens / _clauses / _match_spans / _forward_looking ported from
#  argument_planner.py:387-458, unchanged except for the module-local constants.)


@dataclass(frozen=True)
class Facet:
    name: str
    value: str = ""
    provenance: str = "missing"      # 'declared' | 'span' | 'missing'
    evidence: str = ""               # the VERBATIM surface form lifted from the span

    @property
    def known(self) -> bool:
        return self.provenance != "missing" and bool(self.value)


def _tokens(s: str) -> List[str]:
    return re.findall(r"[a-z0-9''.\-]+", s.lower())


def _clauses(span: str) -> List[str]:
    return [c for c in _CLAUSE_BREAK.split(span) if c and c.strip()]


def _match_spans(text: str, patterns: List[str]) -> List[Tuple[int, str]]:
    """Return (token_index, matched_surface_form) for every pattern hit. Operates on the SPAN."""
    out: List[Tuple[int, str]] = []
    low = text.lower()
    toks = _tokens(low)
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


def _forward_looking(toks: List[str], i: int) -> bool:
    """Is the polarity cue at token ``i`` a PROJECTION rather than an OBSERVED result?

    Structural, not lexical: a directional verb is forward-looking when it sits in a
    periphrastic-future / subject-raising frame — an infinitival 'to <cue>' governed by a
    BE-copula or a future modal, or a bare future modal directly.
    """
    if i <= 0:
        return False
    prev = toks[i - 1]
    if prev in _FUT_MODALS:
        return True
    if prev == "to":
        window = toks[max(0, i - 6):i - 1]
        if _BE_FORMS & set(window) or _FUT_MODALS & set(window):
            return True
    return False


def derive_span_facet(span: str, name: str, vocab: Dict[str, List[str]]) -> Facet:
    """Match a facet in the VERBATIM SPAN. Records the surface form so the tag is auditable."""
    hits: Dict[str, Tuple[int, str]] = {}
    for value, pats in vocab.items():
        ms = _match_spans(span, pats)
        if ms:
            hits[value] = min(ms, key=lambda x: x[0])
    if not hits:
        return Facet(name)
    best = min(hits.items(), key=lambda kv: kv[1][0])
    return Facet(name, best[0], "span", best[1][1])


def derive_span_facet_all(span: str, name: str, vocab: Dict[str, List[str]]) -> List[str]:
    """EVERY value of this facet the span mentions (a span can be about two industries)."""
    return sorted(v for v, pats in vocab.items() if _match_spans(span, pats))


def derive_outcome_direction(span: str, contract: ChampionContract) -> Tuple[Facet, Facet, List[str]]:
    """OUTCOME AND DIRECTION ARE ONE JOINT DERIVATION, OR THEY ARE NOTHING.

    Ported from argument_planner.py:511. A polarity cue governs exactly ONE quantity: the
    NEAREST one, in the same clause, within DIR_WINDOW tokens, un-negated, not forward-looking.
    """
    vocab = contract.span_facets.get("outcome", {})
    if not vocab:
        return Facet("outcome"), Facet("direction"), []

    pairs: Dict[str, Dict[str, str]] = {}       # outcome -> {polarity: matched_form}  (OBSERVED only)
    projected: Dict[str, str] = {}              # outcome -> forward-looking cue form  (a PROJECTION)
    first_seen: Dict[str, int] = {}
    for clause in _clauses(span):
        ctoks = _tokens(clause)
        neg_idx = {i for i, _ in _match_spans(clause, contract.negators)}
        occ: List[Tuple[int, str]] = []
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
                    continue
                if _forward_looking(ctoks, ti):
                    projected.setdefault(ov, form)
                    continue
                pairs.setdefault(ov, {}).setdefault(cls, form)

    mentioned = derive_span_facet_all(span, "outcome", vocab)
    if not mentioned:
        return Facet("outcome"), Facet("direction"), []

    directed = [ov for ov in sorted(pairs, key=lambda v: first_seen.get(v, 10 ** 6))]
    ov = directed[0] if directed else min(mentioned, key=lambda v: first_seen.get(v, 10 ** 6))
    o_form = derive_span_facet(span, "outcome", {ov: vocab[ov]}).evidence
    o_facet = Facet("outcome", ov, "span", o_form)

    pol = pairs.get(ov, {})
    if len(pol) == 1:
        cls, form = next(iter(pol.items()))
        return o_facet, Facet("direction", cls, "span", form), []
    if not pol and ov in projected:
        return o_facet, Facet("direction"), [
            f'FORECAST: the span PROJECTS the outcome\'s direction ("{projected[ov][:30]}") rather '
            f"than reporting a measured change -- citable as an argument, but nothing to adjudicate"]
    return o_facet, Facet("direction"), []


def derive_unit(span: str, contract: ChampionContract) -> Facet:
    """Unit of analysis — absent as a declared field; derived from the quote, MISSING if no cue.

    MISSING is by design: a pair with a missing unit routes to NOT_A_COMPARISON rather than
    to a fabricated level contrast. We do NOT infer a unit.
    """
    return derive_span_facet(span, "unit_of_analysis", contract.unit_vocab)


def derive_horizon(span: str, contract: ChampionContract) -> Facet:
    """Horizon — absent as a declared field; derived from the quote. Expect ~half MISSING."""
    return derive_span_facet(span, "horizon", contract.horizon_vocab)


def derive_method(span: str, document_type: str, contract: ChampionContract) -> Facet:
    """Method — seeded from document_type, refined from quote cues when the seed is empirical.

    A non-empirical seed (review/theory from BLOG_COMMENTARY/REPORT/ENCYCLOPEDIA/BOOK) is
    terminal. An empirical seed (JOURNAL_ARTICLE/PREPRINT) is upgraded to the strongest design
    cue found in the quote (experiment > quasi > survey > observational), else stays at the seed.
    """
    dt = (document_type or "").strip().upper()
    seed = _DOCTYPE_METHOD_SEED.get(dt)
    if seed is None:
        # UNKNOWN / unrecognised doc-type: refine purely from the quote, else MISSING.
        for design in ("experiment", "quasi-experimental", "survey", "observational"):
            if _match_spans(span, contract.method_cues.get(design, [])):
                return Facet("method", design, "span", design)
        return Facet("method")
    if seed not in contract.empirical_designs:
        return Facet("method", seed, "declared")            # review / theory: terminal
    # empirical seed: upgrade to the strongest design the quote actually evidences
    for design in ("experiment", "quasi-experimental", "survey", "observational"):
        if _match_spans(span, contract.method_cues.get(design, [])):
            return Facet("method", design, "span", design)
    return Facet("method", seed, "declared")


def span_numbers(span: str, year: str = "") -> List[str]:
    """The figures that STAND AS THEIR OWN NUMBER in the verbatim span (recomputed from the span,
    never trusted from a model-authored flag). A version number and a bare year are not effects."""
    s = re.sub(r"\b[A-Z][A-Za-z&.]*\s+\d\.\d\b", " ", span)
    s = re.sub(r"\b(?:1[89]|20)\d\d\b", " ", s)
    return [n for n in re.findall(r"\d+(?:\.\d+)?", s) if len(n) >= 2 and n != str(year)]


def span_eligibility(span: str, contract: ChampionContract) -> Tuple[List[str], List[str]]:
    """IS THIS SPAN THE PAPER'S OWN, MEASURED FINDING? Two failures, two severities.

    SECOND_HAND (fatal) — the span reports somebody ELSE's study; may not be attributed AT ALL,
    may not enter a comparison. FORECAST (soft) — the span projects rather than measures; barred
    from comparisons only, admitted as attributed prose. Ported unchanged from :671.
    """
    fatal: List[str] = []
    soft: List[str] = []
    for pat in contract.secondhand_cues:
        m = re.search(pat, span)
        if m:
            fatal.append(f'SECOND_HAND: the span reports another study ("{m.group(0)[:40]}") -- the '
                         f"finding is not this paper's own")
            break
    for pat in contract.forecast_cues:
        m = re.search(pat, span, re.I)
        if m:
            soft.append(f'FORECAST: the span projects rather than measures ("{m.group(0)[:30]}") -- '
                        f"citable as an argument, but there is no estimate to adjudicate")
            break
    return fatal, soft


@dataclass
class CardFacets:
    card_id: str
    same_work_id: str
    facets: Dict[str, Facet]
    outcomes_all: List[str]
    industries_all: List[str]
    numbers: List[str]
    ineligibility: List[str] = field(default_factory=list)     # FATAL: may not be attributed at all
    not_adjudicable: List[str] = field(default_factory=list)   # SOFT: citable, not a comparison term

    def f(self, name: str) -> Facet:
        return self.facets.get(name, Facet(name))

    @property
    def quantitative(self) -> bool:
        return bool(self.numbers)

    @property
    def eligible(self) -> bool:
        return not self.ineligibility

    @property
    def adjudicable(self) -> bool:
        return not self.ineligibility and not self.not_adjudicable


def derive_facets(card: Dict[str, Any], contract: ChampionContract) -> CardFacets:
    """The 8-facet key. Every facet from the SPAN (``card['span']`` <- ``direct_quote``),
    method seeded from ``card['document_type']``; nothing is INFERRED."""
    span = card.get("span") or ""
    fx: Dict[str, Facet] = {}
    for fname, vocab in contract.span_facets.items():
        fx[fname] = derive_span_facet(span, fname, vocab)
    o_facet, d_facet, ambiguous = derive_outcome_direction(span, contract)
    fx[contract.outcome_facet] = o_facet
    fx["direction"] = d_facet
    fx["unit_of_analysis"] = derive_unit(span, contract)
    fx["horizon"] = derive_horizon(span, contract)
    fx["method"] = derive_method(span, card.get("document_type", ""), contract)
    fatal, soft = span_eligibility(span, contract)
    return CardFacets(
        card_id=card["id"],
        same_work_id=card.get("same_work_id", "") or card.get("doi", ""),
        facets=fx,
        outcomes_all=derive_span_facet_all(span, "outcome", contract.span_facets.get("outcome", {})),
        industries_all=derive_span_facet_all(span, "industry", contract.span_facets.get("industry", {})),
        numbers=span_numbers(span, card.get("year", "")),
        ineligibility=fatal,
        not_adjudicable=soft + ambiguous,
    )


# ===================================================================== COMPARISON BUNDLES

BUNDLE_KINDS = {
    "SAME_OUTCOME_DIFFERENT_UNIT": "same outcome, different unit of analysis -- the classic "
                                   '"they only look contradictory" case',
    "SAME_UNIT_OPPOSITE_DIRECTION": "same unit, same outcome, opposite direction -- a GENUINE conflict",
    "SAME_FINDING_DIFFERENT_METHOD": "same outcome, same direction, different identification strategy "
                                     "-- robustness",
    "SAME_OUTCOME_DIFFERENT_HORIZON": "same outcome, different time horizon",
    "UNCOUNTERED": "a finding with NO counterpart anywhere in the corpus -- a boundary",
    "NOT_A_COMPARISON": "the axis this would turn on is NOT DECLARED on both cards",
}


def _evidence_tier(a: CardFacets, b: CardFacets, contract: ChampionContract) -> str:
    """WHAT KIND OF THING IS IN TENSION HERE? Ported from :806."""
    emp = set(contract.empirical_designs)
    ma, mb = a.f("method"), b.f("method")
    a_emp = ma.known and ma.value in emp
    b_emp = mb.known and mb.value in emp
    if not a_emp and not b_emp:
        return "positions"
    if a_emp != b_emp:
        return "model_vs_measurement"
    if a.quantitative and b.quantitative:
        return "estimates"
    return "findings"


def _comparability(a: CardFacets, b: CardFacets, contract: ChampionContract) -> Tuple[bool, List[str]]:
    """ARE THESE TWO ESTIMATES ON THE SAME FOOTING? Ported from :831. Every mismatch -> a reason."""
    why: List[str] = []
    emp = set(contract.empirical_designs)
    for c, tag in ((a, "first"), (b, "second")):
        m = c.f("method")
        if not m.known:
            why.append(f"the {tag} card declares no method")
        elif m.value not in emp:
            why.append(f"the {tag} card is a {m.value} paper -- it states a position, not an estimate")
        if not c.quantitative:
            why.append(f"the {tag} card reports no figure in its span -- there is no estimate to compare")
    ua, ub = a.f("unit_of_analysis"), b.f("unit_of_analysis")
    if ua.known and ub.known and ua.value != ub.value:
        why.append(f"they observe different units of analysis ({ua.value} vs {ub.value})")
    ha, hb = a.f("horizon"), b.f("horizon")
    if not (ha.known and hb.known):
        why.append("at least one card declares no horizon, so the time base cannot be matched")
    elif ha.value != hb.value:
        why.append(f"they observe different horizons ({ha.value} vs {hb.value})")
    oa, ob = a.f("outcome"), b.f("outcome")
    if oa.known and ob.known and oa.value != ob.value:
        why.append(f"they measure different outcomes ({oa.value} vs {ob.value})")
    return (not why), why


def _apparent_conflict(a: CardFacets, b: CardFacets) -> bool:
    """Do these two cards actually LOOK contradictory? Requires BOTH directions KNOWN and OPPOSED."""
    da, db = a.f("direction"), b.f("direction")
    if not (da.known and db.known):
        return False
    return {da.value, db.value} in (
        {"positive", "negative"}, {"positive", "null"}, {"negative", "null"})


def _score(a: CardFacets, b: CardFacets, apparent: bool, comparable: bool) -> float:
    s = 0.0
    s += 3.0 * (a.quantitative + b.quantitative)
    s += 4.0 if apparent else 0.0
    s += 2.0 if comparable else 0.0
    for c in (a, b):
        if c.f("method").known and c.f("method").value in ("experiment", "quasi-experimental"):
            s += 1.5
        if c.f("horizon").known:
            s += 0.5
    return s


def _bundle_dict(kind: str, outcome: str, members: List[str], comparable: bool, why: List[str],
                 apparent_conflict: bool, evidence_tier: str, shared: Dict[str, str],
                 varies: Dict[str, str], score: float, note: str) -> Dict[str, Any]:
    """The task-requested emitted shape, one dict per bundle."""
    return {
        "outcome": outcome,
        "kind": kind,
        "members": members,
        "comparable": comparable,
        "why": why,
        "apparent_conflict": apparent_conflict,
        "evidence_tier": evidence_tier,
        "shared": shared,
        "varies": varies,
        "score": score,
        "note": note,
    }


def find_bundles(cfs: List[CardFacets], contract: ChampionContract) -> List[Dict[str, Any]]:
    """Every comparison this corpus can actually support -- and no others. Ported from :890.

    ``pair_ok`` keys on ``same_work_id`` (NOT ``doi``): a paper cannot corroborate itself, and
    ``same_work_id`` is the champion's reliable same-paper key here.
    """
    out: List[Dict[str, Any]] = []
    eligible = [c for c in cfs if c.adjudicable]

    def pair_ok(a: CardFacets, b: CardFacets) -> bool:
        # A card cannot be compared with itself, and a paper cannot corroborate itself.
        # Empty same_work_id means "no known group": treated as distinct works (permitted).
        if a.same_work_id and b.same_work_id and a.same_work_id == b.same_work_id:
            return False
        return True

    seen_pairs: set = set()

    for a, b in itertools.combinations(eligible, 2):
        if not pair_ok(a, b):
            continue
        oa, ob = a.f("outcome"), b.f("outcome")
        if not (oa.known and ob.known and oa.value == ob.value):
            continue
        outcome = oa.value
        ua, ub = a.f("unit_of_analysis"), b.f("unit_of_analysis")
        ha, hb = a.f("horizon"), b.f("horizon")
        ma, mb = a.f("method"), b.f("method")
        da, db = a.f("direction"), b.f("direction")
        apparent = _apparent_conflict(a, b)
        comparable, why = _comparability(a, b, contract)
        tier = _evidence_tier(a, b, contract)
        sc = _score(a, b, apparent, comparable)
        shared = {"outcome": outcome}
        for fn in ("technology", "industry"):
            fa, fb = a.f(fn), b.f(fn)
            if fa.known and fb.known and fa.value == fb.value:
                shared[fn] = fa.value

        emitted_here = False
        # ---- 1. SAME OUTCOME, DIFFERENT UNIT
        if ua.known and ub.known and ua.value != ub.value:
            out.append(_bundle_dict(
                "SAME_OUTCOME_DIFFERENT_UNIT", outcome, [a.card_id, b.card_id], comparable, why,
                apparent, tier, shared, {a.card_id: ua.value, b.card_id: ub.value}, sc,
                ("the estimates point in opposite directions and differ on exactly one derived axis "
                 "-- a reconciliation is licensed" if apparent else
                 "the directions are not both known, so there is NO apparent conflict to reconcile; "
                 "the plan states the evidence bears on two different units, not that they agree")))
            emitted_here = True
        elif ua.value == ub.value and ua.known:
            if apparent:
                out.append(_bundle_dict(
                    "SAME_UNIT_OPPOSITE_DIRECTION", outcome, [a.card_id, b.card_id], comparable, why,
                    True, tier, {**shared, "unit_of_analysis": ua.value},
                    {a.card_id: da.value, b.card_id: db.value}, sc + 2,
                    "same outcome, same derived unit, opposed span-derived directions -- this conflict "
                    "cannot be dissolved by pointing at the unit of analysis"))
                emitted_here = True
            elif (ma.known and mb.known and ma.value != mb.value
                  and da.known and db.known and da.value == db.value):
                out.append(_bundle_dict(
                    "SAME_FINDING_DIFFERENT_METHOD", outcome, [a.card_id, b.card_id], comparable, why,
                    False, tier, {**shared, "unit_of_analysis": ua.value, "direction": da.value},
                    {a.card_id: ma.value, b.card_id: mb.value}, sc + 1,
                    "the same directional finding survives a change of identification strategy"))
                emitted_here = True

        # ---- 4. SAME OUTCOME, DIFFERENT HORIZON
        if ha.known and hb.known and ha.value != hb.value:
            out.append(_bundle_dict(
                "SAME_OUTCOME_DIFFERENT_HORIZON", outcome, [a.card_id, b.card_id], comparable, why,
                apparent, tier, shared, {a.card_id: ha.value, b.card_id: hb.value}, sc,
                "" if apparent else "no apparent conflict: this is a horizon SPREAD, not a dispute"))
            emitted_here = True

        if emitted_here:
            seen_pairs.add((a.card_id, b.card_id))

    # ---- 5. THE REFUSALS. Same outcome, undeclared axis -> NOT_A_COMPARISON, made visible.
    for a, b in itertools.combinations(eligible, 2):
        if not pair_ok(a, b):
            continue
        oa, ob = a.f("outcome"), b.f("outcome")
        if not (oa.known and ob.known and oa.value == ob.value):
            continue
        if (a.card_id, b.card_id) in seen_pairs:
            continue
        missing = [fn for fn in ("unit_of_analysis", "horizon", "method")
                   if not (a.f(fn).known and b.f(fn).known)]
        if missing:
            out.append(_bundle_dict(
                "NOT_A_COMPARISON", oa.value, [a.card_id, b.card_id], False,
                [f"{fn} is not declared on both cards" for fn in missing],
                False, _evidence_tier(a, b, contract), {"outcome": oa.value}, {}, 0.0,
                "REFUSED: the axis this would turn on is missing. Inventing it here is exactly how a "
                "false reconciliation is manufactured, so no comparison is planned."))

    # ---- 6. UNCOUNTERED: a cell of (outcome x unit) that exactly ONE work occupies -> a boundary.
    cell: Dict[Tuple[str, str], set] = {}
    for c in eligible:
        o, u = c.f("outcome"), c.f("unit_of_analysis")
        if o.known and u.known:
            cell.setdefault((o.value, u.value), set()).add(c.same_work_id or c.card_id)
    for c in eligible:
        o, u = c.f("outcome"), c.f("unit_of_analysis")
        if not (o.known and u.known):
            continue
        if len(cell[(o.value, u.value)]) == 1 and c.quantitative:
            out.append(_bundle_dict(
                "UNCOUNTERED", o.value, [c.card_id], False,
                ["there is no second source in this cell to compare against"],
                False, "estimates" if c.quantitative else "findings",
                {"outcome": o.value, "unit_of_analysis": u.value}, {}, 2.0 + len(c.numbers),
                "a span-verified figure that NO other source in the corpus counters at the same unit "
                "-- the review can state its scope, and must not generalise beyond it"))

    # Dedup by (kind, sorted members); keep the highest score. Sort by descending score.
    dedup: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for bd in out:
        k = (bd["kind"], tuple(sorted(bd["members"])))
        if k not in dedup or bd["score"] > dedup[k]["score"]:
            dedup[k] = bd
    return sorted(dedup.values(), key=lambda bd: -bd["score"])


# ===================================================================== CORPUS ADAPTER


def _same_work_index(corpus: Dict[str, Any]) -> Dict[str, str]:
    """evidence_id -> same_work_id, from ``same_work_groups`` (the champion same-paper key)."""
    idx: Dict[str, str] = {}
    for g in corpus.get("same_work_groups", []) or []:
        swid = g.get("same_work_id") or ""
        for eid in g.get("member_evidence_ids", []) or []:
            idx[eid] = swid
    return idx


def _row_to_card(row: Dict[str, Any], same_work: Dict[str, str]) -> Dict[str, Any]:
    """A corpus evidence row -> the card shape the ported helpers consume.

    ``span`` <- ``direct_quote`` (NOT ``statement`` — 635/997 statements are just the title).
    ``same_work_id`` from ``same_work_groups`` (falls back to the evidence_id, so an unmapped
    row is its own singleton work and can still be compared against distinct works).
    """
    eid = row.get("evidence_id", "")
    return {
        "id": eid,
        "span": row.get("direct_quote") or "",
        "same_work_id": same_work.get(eid, "") or f"__singleton__:{eid}",
        "doi": row.get("doi", "") or "",
        "document_type": row.get("document_type", "") or "",
        "year": row.get("year", "") or row.get("publication_year", "") or "",
    }


def build_bundles(rows: List[Dict[str, Any]],
                  same_work_groups: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Build comparison bundles from champion evidence ``rows``.

    ``rows`` are champion ``evidence`` dicts (``evidence_id`` / ``direct_quote`` / ``document_type``
    / ...). ``same_work_groups`` is the champion's same-paper grouping; when omitted, every row is
    its own singleton work (no self-corroboration guard beyond card identity). This is PLANNING
    data for the writer's starved synthesis/policy/conclusion sections — it writes no prose and
    touches no verification. Returns bundles sorted by descending score.
    """
    contract = _champion_contract()
    same_work: Dict[str, str] = {}
    for g in same_work_groups or []:
        swid = g.get("same_work_id") or ""
        for eid in g.get("member_evidence_ids", []) or []:
            same_work[eid] = swid
    cfs = [derive_facets(_row_to_card(r, same_work), contract) for r in rows]
    return find_bundles(cfs, contract)


def build_comparison_bundles(corpus: Dict[str, Any]) -> List[Dict[str, Any]]:
    """corpus = loaded cp4_corpus_s3gear_329.json.

    OFF unless ``PG_COMPARISON_BUNDLES`` is truthy; returns ``[]`` when off (byte-identical path).
    """
    if not is_enabled():
        return []
    rows = corpus.get("evidence", []) or []
    return build_bundles(rows, corpus.get("same_work_groups", []) or [])


def is_enabled() -> bool:
    """True iff the default-OFF ``PG_COMPARISON_BUNDLES`` flag is truthy.

    Read at call time so the harness can toggle without re-import. This module ships wired to
    nothing, so OFF is the current state and the OFF path is byte-identical to today.
    """
    return os.getenv("PG_COMPARISON_BUNDLES", "0").strip().lower() in ("1", "true", "yes", "on")
