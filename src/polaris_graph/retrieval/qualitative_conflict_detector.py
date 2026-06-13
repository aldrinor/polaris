"""Qualitative present-vs-absent clinical-safety conflict detector (I-meta-002-q1d #944).

The numeric `contradiction_detector` only sees disagreements that carry a number. The most
patient-dangerous disagreements — contraindication PRESENT vs ABSENT, drug-interaction warning
present vs absent, eligibility/exclusion — carry NO number and are structurally invisible to it
(the lethal-error class per `feedback_qualitative_negation_escapes_regex_2026_05_26`). This module
adds a parallel, precision-first qualitative assertion-status conflict path, surfaced into the SAME
`contradictions.json` + report.

Method: NegEx (Chapman 2001) / ConText (Harkema-Chapman 2009) rule-cue assertion-status — no LLM by
default (NO SPEND). Cue precedence per span (Codex brief-gate iter-2 P1.a):
    permissive_allow -> statistical_null -> uncertainty -> real_negation(net XOR) -> antonym/affirm -> hedge
so a deontic "may be co-administered" (ABSENT, definite) wins over the epistemic hedge "may"
(INDETERMINATE) and the mandatory DDI antonym recall case hard-fires.

Two-pass detection (Codex brief-gate iter-1 P1.2 + iter-2 P1.b):
- PASS A (hard conflict): group by the FULL key (subject, concept_type, object_slot, condition_scope);
  flag only same-key clusters with >=2 DISTINCT sources holding DIFFERING DEFINITE polarity
  (PRESENT vs ABSENT). INDETERMINATE / STATISTICAL_NULL cannot anchor a hard conflict.
- PASS B (review candidate): group by the COARSE key (subject, concept_type) only; every definite-
  disagreeing distinct-source pair NOT already a hard conflict — because object_slot/condition_scope
  differ or are missing/broad, or a definite opposes an INDETERMINATE/STATISTICAL_NULL — is emitted as
  a `review_flag` (severity "review"), NEVER dropped. Only BOTH object_slots resolved to clearly-
  different specific entities is a determinable non-conflict (no flag).

Fail-safe = escalate-to-review, never silent: a missed contradiction is the lethal error.
"High precision" means do NOT fire on a DETERMINABLE non-conflict, NOT go quiet when unsure.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

# ─────────────────────────────────────────────────────────────────────────────
# Lexicon (LAW VI: SME-editable config, validated fail-loud at first use)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_LEXICON_PATH = (
    Path(__file__).resolve().parents[3]
    / "config" / "clinical_safety" / "qualitative_conflict_lexicon.yaml"
)
_REQUIRED_SECTIONS = (
    "concept_types", "object_slot_owner", "permissive_allow", "statistical_null",
    "uncertainty", "no_assertion", "real_negation", "hedge", "termination_terms",
    "condition_scope_cues", "scope_token_cap",
)
_lexicon_cache: dict[str, Any] | None = None


def _load_lexicon() -> dict[str, Any]:
    """Load + validate the cue lexicon once. Fail-loud RuntimeError on a missing/empty section
    (Codex brief-gate iter-2 P2: validate required sections, no silent partial lexicon)."""
    global _lexicon_cache
    if _lexicon_cache is not None:
        return _lexicon_cache
    path = Path(os.getenv("PG_QUALITATIVE_CONFLICT_LEXICON", str(_DEFAULT_LEXICON_PATH)))
    if not path.exists():
        raise RuntimeError(f"qualitative_conflict_lexicon not found at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = [s for s in _REQUIRED_SECTIONS if not data.get(s)]
    if missing:
        raise RuntimeError(
            f"qualitative_conflict_lexicon at {path} missing/empty required sections: {missing}"
        )
    if not isinstance(data["concept_types"], dict) or not data["concept_types"]:
        raise RuntimeError("qualitative_conflict_lexicon: concept_types must be a non-empty mapping")
    _lexicon_cache = data
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Assertion status + loader-safe finite float encoding (Codex iter-1 P1.4)
# ─────────────────────────────────────────────────────────────────────────────

PRESENT = "present"
ABSENT = "absent"
INDETERMINATE = "indeterminate"
STATISTICAL_NULL = "statistical_null"

_VALUE_BY_STATUS: dict[str, float] = {
    PRESENT: 1.0, ABSENT: 0.0, INDETERMINATE: 0.5, STATISTICAL_NULL: 0.5,
}
_DEFINITE = frozenset({PRESENT, ABSENT})

_OFF_VALUES = frozenset({"0", "false", "False", "no", "off"})


def qualitative_conflict_enabled() -> bool:
    """The sweep kill-switch. Default ON (no-spend, additive); `PG_SWEEP_QUALITATIVE_CONFLICT=0`
    disables the qualitative pass (numeric detection is unaffected)."""
    return os.getenv("PG_SWEEP_QUALITATIVE_CONFLICT", "1") not in _OFF_VALUES


@dataclass
class QualitativeAssertion:
    """One clinical-safety assertion extracted from one evidence quote."""
    evidence_id: str
    subject: str
    concept_type: str
    object_slot: str
    condition_scope: str
    assertion_status: str
    cue: str
    context_snippet: str
    source_url: str
    source_tier: str
    # Intra-slot ontology discriminators (Wave 3 I-arch-001 #1245, design §4.4). '' == UNKNOWN.
    # Emitted on a PRESENT-cue hit by classifying the matched cue against the lexicon's
    # causal_strength_cues / warning_severity_cues buckets. Dormant carriers: read ONLY by
    # claim_graph.build_merge_key under PG_SWEEP_CREDIBILITY_REDESIGN; never serialized on the
    # OFF path (NOT in _claim_dict), so additive defaults are byte-identical when the redesign is off.
    causal_strength: str = ''      # {causal, associational} for ae_causation, else ''
    warning_severity: str = ''     # {boxed_regulatory, routine_caution} for warning, else ''
    # condition_polarity: the POPULATION polarity of condition_scope — {with, without}
    # when a population/organ qualifier is named, else '' (no population qualifier).
    # Wave-3 I-arch-001 #1245 P0 (Claude audit): the merge key was polarity-BLIND on the
    # population, so "causes nausea in patients WITH renal impairment" and "...WITHOUT
    # renal impairment" produced an IDENTICAL key and over-merged into a fabricated
    # multi-source basket of OPPOSITE populations (clinical-lethal; the per-sentence
    # faithfulness engine is basket-blind and cannot catch a false-merge). Same dormant
    # contract as causal_strength/warning_severity: read ONLY by claim_graph.build_merge_key
    # under PG_SWEEP_CREDIBILITY_REDESIGN; never serialized (NOT in _claim_dict), so the
    # additive default is byte-identical when the redesign is OFF.
    condition_polarity: str = ''   # {with, without} when a population is named, else ''


@dataclass
class QualitativeConflictRecord:
    """A qualitative conflict (or review-flag) record. Shaped for `audit_ir.loader`: it has the
    REQUIRED `predicate` + `claims` (list>=2, each with evidence_id/predicate/value:float), so the
    sweep's existing `[asdict(c) for c in contradictions]` writer serializes it without a mixed
    serializer (Codex iter-1 P1.1). `type`/`conflict_reason`/`assertion_status` ride as loader-
    tolerated extras; downstream MUST branch on `type` + `severity` (Codex iter-1 P1.5)."""
    predicate: str
    claims: list[dict]
    subject: str = ""
    severity: str = "medium"          # high | medium | review
    type: str = "qualitative"         # discriminator vs numeric records
    conflict_reason: str = ""
    recommended_action: str = (
        "Qualitative present-vs-absent disagreement across sources — verify against primary labels."
    )
    absolute_difference: float = 0.0  # loader-tolerated numeric fields (N/A for qualitative)
    relative_difference: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────────────────────────

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-']*")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


def _split_clauses(text: str, term_terms: list[str]) -> list[str]:
    """Split a sentence into clauses on commas/semicolons AND termination terms (NegEx conjunctions),
    so high-precedence status cues (permissive/statistical/uncertainty/hedge) are scoped to the clause
    that holds the concept — NOT leaked across clauses (Codex diff-gate iter-1 P1.3). ALSO splits on
    coordinating `and`/`or` so same-concept coordinated assertions ('safe in pregnancy AND
    contraindicated in lactation') become SEPARATE assertions each bound to its own condition (Codex
    diff-gate iter-4 P1); a clause that loses its drug inherits the sentence subject. Over-splitting a
    compound condition ('renal AND hepatic impairment') only UNDER-captures (the trailing fragment has
    no concept cue) — it never manufactures a false conflict. Original case preserved for the snippet."""
    pattern = r"[;,]|\b(?:and|or|" + "|".join(re.escape(t) for t in term_terms) + r")\b"
    return [p.strip() for p in re.split(pattern, text or "", flags=re.IGNORECASE) if p and p.strip()]


def _find_longest_cue(sentence_lc: str, cues: list[str]) -> Optional[tuple[str, int]]:
    """Return (cue, position) of the LONGEST matching cue in the sentence, else None.
    Longest-first so 'no contraindication' (absent) beats 'contraindication' (present)."""
    best: Optional[tuple[str, int]] = None
    for cue in cues:
        pos = sentence_lc.find(cue)
        if pos >= 0 and (best is None or len(cue) > len(best[0])):
            best = (cue, pos)
    return best


def _phrase_present(sentence_lc: str, phrases: list[str]) -> Optional[str]:
    for p in phrases:
        if p in sentence_lc:
            return p
    return None


def _pre_scope(sentence_lc: str, concept_pos: int, term_terms: list[str], token_cap: int) -> str:
    """Bounded pre-negation region: up to token_cap words BEFORE the concept term, stopping at the
    nearest termination term (NegEx directional, precision-tightened window)."""
    pre = sentence_lc[:concept_pos]
    # truncate at the last termination term before the concept
    cut = 0
    for tt in term_terms:
        idx = pre.rfind(f" {tt} ")
        if idx >= 0:
            cut = max(cut, idx + len(tt) + 2)
    pre = pre[cut:]
    words = _WORD_RE.findall(pre)
    return " ".join(words[-token_cap:])


def _net_negation_flip(pre_region: str, concept_cue: str, real_neg: list[str]) -> bool:
    """Count real-negation cues in the bounded pre-region + a leading 'non-' on the concept; return
    True if the NET polarity flips (odd count) — collapses double negation (Codex iter-1 P1.6 net XOR).
    Cues are matched LONGEST-FIRST and each match is MASKED so an overlapping short cue cannot
    re-count inside it (Codex diff-gate iter-2 P1.b: 'no evidence of' must NOT also count 'no')."""
    region = " " + pre_region + " "
    count = 0
    for cue in sorted(real_neg, key=len, reverse=True):
        if " " in cue:
            pat = re.compile(re.escape(cue))
        else:
            pat = re.compile(rf"(?<![A-Za-z]){re.escape(cue)}(?![A-Za-z])")
        region, n = pat.subn(lambda m: " " * (m.end() - m.start()), region)
        count += n
    if concept_cue.startswith("non-") or " non-" in (" " + pre_region):
        count += 1
    return count % 2 == 1


def _local_window(text_lc: str, concept_pos: int, cue_len: int, token_window: int,
                  term_terms: list[str]) -> str:
    """A bounded window around the matched concept cue, CLIPPED at the nearest coordinating boundary
    (comma/semicolon/'and'/'or'/termination term) on EACH side, then capped to `token_window` words.
    High-precedence status cues are checked HERE (not clause-wide) so a permissive/statistical/hedge
    cue that belongs to a DIFFERENT coordinated concept cannot leak onto this one — in EITHER order
    (Codex diff-gate iter-2 P1.a + iter-3 P1: '... and may be co-administered' must not flip a
    preceding contraindication)."""
    boundary = re.compile(r"[;,]|\b(?:and|or|" + "|".join(re.escape(t) for t in term_terms) + r")\b",
                          re.IGNORECASE)
    start = 0
    for m in boundary.finditer(text_lc[:concept_pos]):
        start = m.end()
    cue_end = concept_pos + cue_len
    nxt = boundary.search(text_lc, cue_end)
    end = nxt.start() if nxt else len(text_lc)
    seg, cpos = text_lc[start:end], concept_pos - start
    pre_words = _WORD_RE.findall(seg[:cpos])[-token_window:]
    post_words = _WORD_RE.findall(seg[cpos + cue_len:])[:token_window]
    return " ".join(pre_words) + " " + seg[cpos:cpos + cue_len] + " " + " ".join(post_words)


def _classify_status(clause_lc: str, concept_cue: str, concept_pos: int, base: str,
                     lex: dict[str, Any]) -> str:
    """Resolve assertion status with the fixed cue precedence, evaluating the high-precedence cue
    classes in a BOUNDED, coordinator-clipped WINDOW around the matched concept (not clause-wide)."""
    window = _local_window(clause_lc, concept_pos, len(concept_cue),
                           int(lex["scope_token_cap"]), lex["termination_terms"])
    # 1. permissive/deontic permission -> ABSENT (definite), wins over hedge.
    if _phrase_present(window, lex["permissive_allow"]):
        return ABSENT
    # 2. statistical null (the lethal-FP class) -> STATISTICAL_NULL.
    if _phrase_present(window, lex["statistical_null"]):
        return STATISTICAL_NULL
    # 3. epistemic uncertainty -> INDETERMINATE.
    if _phrase_present(window, lex["uncertainty"]):
        return INDETERMINATE
    # 4. real-negation net XOR over the bounded pre-scope, applied to the base antonym polarity.
    pre = _pre_scope(clause_lc, concept_pos, lex["termination_terms"], int(lex["scope_token_cap"]))
    status = base
    if _net_negation_flip(pre, concept_cue, lex["real_negation"]):
        status = ABSENT if base == PRESENT else PRESENT
    # 5. epistemic hedge (permissive already ruled out at step 1) -> INDETERMINATE.
    if _phrase_present(window, lex["hedge"]):
        return INDETERMINATE
    return status


def _normalize_subject_co_drug(sentence: str, subject: str) -> str:
    """Return the FIRST drug name in the sentence that is NOT the subject (DDI co-drug), else ''."""
    from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE
    for m in _DRUG_NAME_RE.finditer(sentence or ""):
        name = m.group(1).lower()
        if name and name != (subject or "").lower():
            return name
    return ""


_OBJECT_AFTER_CUE_RE = re.compile(r"[A-Za-z][A-Za-z0-9\- ]{2,40}")


def _extract_object_slot(sentence: str, sentence_lc: str, concept_type: str, concept_pos: int,
                         concept_cue: str, subject: str) -> str:
    """Concept-specific object_slot (canonical ownership; '' when unresolved -> routes to review)."""
    if concept_type == "drug_interaction":
        return _normalize_subject_co_drug(sentence, subject)
    if concept_type in ("ae_causation", "warning", "eligibility_exclusion"):
        tail = sentence_lc[concept_pos + len(concept_cue):].lstrip(" :,")
        m = _OBJECT_AFTER_CUE_RE.match(tail)
        if m:
            phrase = m.group(0).strip()
            # cut at a clause boundary word for tightness
            for stop in (" but ", " however ", " and ", " which ", " in patients", " with "):
                k = phrase.find(stop)
                if k > 0:
                    phrase = phrase[:k]
            return phrase.strip().lower()[:40]
    return ""


# Severity/normality qualifiers that DISCRIMINATE a condition scope. Adjacent to the organ/condition
# cue, they distinguish "renal impairment" / "severe renal" from "normal renal function" so condition-
# stratified statements do NOT collapse to the same key. Concept-polarity words (contraindicated/safe/
# avoid) are NEVER included — only the population/organ qualifier survives.
_PRE_QUALIFIERS = frozenset({"normal", "severe", "mild", "moderate", "preserved", "chronic", "acute",
                             "advanced", "significant", "end-stage", "endstage", "decompensated"})
_POST_QUALIFIERS = frozenset({"impairment", "insufficiency", "failure", "dysfunction", "disease"})


def _extract_condition_scope(sentence_lc: str, lex: dict[str, Any]) -> str:
    """Return a DISCRIMINATING condition-scope phrase = the organ/condition cue word plus an adjacent
    severity/normality qualifier ONLY (never the concept-polarity verb). 'renal impairment' and
    'normal renal function' stay distinct (the red-team condition-stratified false-positive), while
    identical conditions ('pregnancy' both sides) collapse to the same key (a real conflict)."""
    tokens = [re.sub(r"[^a-z\-]", "", w) for w in sentence_lc.split()]
    for i, tok in enumerate(tokens):
        if not tok:
            continue
        if any(cue in tok for cue in lex["condition_scope_cues"]):
            parts = [tok]
            if i > 0 and tokens[i - 1] in _PRE_QUALIFIERS:
                parts.insert(0, tokens[i - 1])
            if i + 1 < len(tokens) and tokens[i + 1] in _POST_QUALIFIERS:
                parts.append(tokens[i + 1])
            return " ".join(parts)[:48]
    return ""


# Population-NEGATION cues that flip a condition_scope from the (default) WITH-population
# polarity to WITHOUT-population. A cue counts ONLY when it sits INSIDE the population
# phrase (between a population introducer and the condition cue) — see the bounded
# back-scan in _extract_condition_polarity.
_POPULATION_NEGATION_CUES = frozenset({
    "without", "not", "no", "non", "absent", "absence", "free", "lacking", "lack",
    "lacks", "devoid", "sans", "minus", "negative",
})
# Affirmative population INTRODUCERS ('in patients with renal'): a SOFT boundary for the
# negation scan (a negation BEFORE the introducer governs the verb/object, not the
# population — "causes NO nausea IN renal") but TRANSPARENT to the exclusion scan.
_POPULATION_INTRODUCERS = frozenset({"in", "among", "amongst", "with"})
# HARD clause boundaries: a coordinating/subordinating conjunction starts a NEW clause —
# nothing before it is part of THIS population phrase. Relative pronouns (who/that/which)
# are deliberately NOT here: they are part of the population description ("patients WHO HAVE
# renal", "those WITH renal"), so the scan stays transparent across them.
_POPULATION_CLAUSE_BOUNDARIES = frozenset({
    "and", "or", "but", "while", "whereas", "because", "since", "however",
    "though", "although", "nevertheless",
})
# A RELATIVE-CLAUSE marker inside the population description ('patients WHO HAVE renal') means
# the population carries an embedded restriction the token scan cannot fully parse. With no
# resolved negation/exclusion the polarity is therefore UNCERTAIN ⇒ fail-closed to a
# SINGLETON (never a guessed 'with'). Over-fragmentation is SAFE; a guessed 'with' on a
# hidden exclusion is the lethal over-merge (Codex Slice-B iter-4 P0).
_RELATIVE_CLAUSE_MARKERS = frozenset({
    "who", "whom", "whose", "that", "which", "where", "wherein", "whereby",
})
# UNAMBIGUOUS exclusion operators that INVERT the population ("excluding/except/other than/
# rather than/apart from those with renal" ⇒ the population WITHOUT renal). Deliberately
# conservative: a FALSE-positive flip of an affirmative "with X" to "without X" would ITSELF
# be a lethal over-merge (with a genuine "without X"), so only operators that reliably denote
# exclusion are listed; ambiguous ones ('besides'/'outside'/'exclusive') are NOT.
_EXCLUSION_SINGLE = frozenset({
    "excluding", "except", "exclude", "excludes", "excluded",
    "omitting", "omit", "omits", "omitted",
})
_EXCLUSION_BIGRAMS = frozenset({("other", "than"), ("rather", "than"), ("apart", "from")})
# POST-cue passive restriction verbs whose population-restriction sense is COMMON but not
# unambiguous (they have benign uses: "drug WITHDRAWN from market"). When one appears AFTER
# the condition cue in the population clause it MIGHT restrict the population, so it FAILS
# CLOSED to a singleton (never a guessed 'with') rather than risk a false 'without' (a false
# 'without' would itself over-merge with a genuine without-population — the lethal direction).
_POST_CUE_RESTRICTION_CUES = frozenset({
    "removed", "dropped", "withdrawn", "barred", "disqualified", "ineligible",
    "precluded", "prohibited", "censored",
})
# Exclusion-META nouns ("renal impairment AS AN EXCLUSION CRITERION" — eligibility
# meta-language, not a clean population statement). Presence anywhere in the clause ⇒
# FAIL CLOSED to a singleton (Codex Slice-B iter-7 P0). Bare "criterion/criteria" is NOT
# here (it is usually inclusion language); only the explicit exclusion noun.
_EXCLUSION_META_NOUNS = frozenset({"exclusion", "exclusions"})
# Sentinel: a population is present but its polarity cannot be confidently resolved.
# build_merge_key (via _ambiguous_polarity) treats it as UNKNOWN ⇒ forces a singleton.
POLARITY_AMBIGUOUS = "ambiguous"


def _extract_condition_polarity(sentence_lc: str, lex: dict[str, Any]) -> str:
    """Polarity of the population/condition qualifier (Wave-3 I-arch-001 #1245 P0).

    SAFE-BY-CONSTRUCTION (Codex Slice-B iter-2..iter-4): the only LETHAL error is reading a
    WITHOUT/EXCLUDED population as the mergeable affirmative 'with', so anything not provably
    a clean affirmative or a clean negation/exclusion FAILS CLOSED to a singleton.

    Returns:
      * 'without' — the population is NEGATED ('without renal', 'no evidence of renal', 'free
        of hepatic disease', 'do not have renal', 'non-renal') or EXCLUDED ('other than /
        excluding / except / rather than / apart from ... renal', incl. across a relative
        clause or a long participant description — the WHOLE population clause is scanned).
      * 'with' — a CLEAN affirmative population: an introducer ('in'/'with'/'among') with no
        negation, no exclusion operator, and NO embedded relative clause.
      * ``POLARITY_AMBIGUOUS`` — a population is present but carries an unresolved relative
        clause ('patients WHO HAVE renal impairment'); fail-closed to a SINGLETON rather than
        guess 'with' (a hidden restriction could make it a different population).
      * '' — NO population cue (an unstratified claim).

    Scoping rules: the population CLAUSE is the cue back to a hard clause boundary
    ('and'/'but'/'while'/...). Exclusion operators count ANYWHERE in that clause (no token
    cap — fixes the long-participant-description miss). A negation counts only INSIDE the
    population phrase, i.e. before crossing an introducer scanning back ('causes NO nausea IN
    renal' stays 'with' — the "no" governs the verb). A negation PREFIX on the cue token
    ('non-renal') ⇒ 'without'. Tokenisation mirrors `_extract_condition_scope`. Dormant: read
    ONLY by `build_merge_key` under PG_SWEEP_CREDIBILITY_REDESIGN; never serialized.
    """
    tokens = [re.sub(r"[^a-z\-]", "", w) for w in sentence_lc.split()]
    for i, tok in enumerate(tokens):
        if not tok:
            continue
        if any(cue in tok for cue in lex["condition_scope_cues"]):
            # (a) a negation PREFIX on the cue token itself ('non-renal' -> 'non' + 'renal').
            if any(p in _POPULATION_NEGATION_CUES for p in tok.split("-")[:-1]):
                return "without"
            # delimit the population CLAUSE: cue OUT to a hard clause boundary in BOTH
            # directions (a population restriction can appear before OR after the cue —
            # "EXCLUDING those with renal" / "renal impairment EXCLUDED").
            lo = 0
            for j in range(i - 1, -1, -1):
                if tokens[j] in _POPULATION_CLAUSE_BOUNDARIES:
                    lo = j + 1
                    break
            hi = len(tokens)
            for j in range(i + 1, len(tokens)):
                if tokens[j] in _POPULATION_CLAUSE_BOUNDARIES:
                    hi = j
                    break
            clause = tokens[lo:hi]
            post = tokens[i + 1:hi]
            clause_set = set(clause)
            has_exclusion = bool(clause_set & _EXCLUSION_SINGLE) or any(
                (clause[k], clause[k + 1]) in _EXCLUSION_BIGRAMS
                for k in range(len(clause) - 1))
            has_negation = bool(clause_set & _POPULATION_NEGATION_CUES)
            # (b) negation AND exclusion TOGETHER ⇒ FAIL CLOSED. The combinatorics are unsafe
            # to resolve by token order — "renal impairment NOT EXCLUDED" is INCLUSION (with),
            # not exclusion (Codex Slice-B iter-7 P0). Singleton, never a guessed with/without.
            if has_exclusion and has_negation:
                return POLARITY_AMBIGUOUS
            # (c) a CLEAN exclusion operator ANYWHERE in the clause (pre OR post cue, no
            # negation) ⇒ 'without': "excluding those with renal" / "renal impairment excluded".
            if has_exclusion:
                return "without"
            # (d) a negation INSIDE the population phrase ⇒ 'without'. Bounded by the OUTERMOST
            # (earliest) introducer: a negation BEFORE it governs the verb ("causes NO nausea
            # IN renal" -> 'with'), AFTER it governs the population ("patients NOT including
            # those with renal" -> 'without'). No introducer ⇒ the whole pre-cue span.
            intro_lo = next(
                (j for j in range(lo, i) if tokens[j] in _POPULATION_INTRODUCERS), None)
            neg_lo = intro_lo + 1 if intro_lo is not None else lo
            if any(tokens[j] in _POPULATION_NEGATION_CUES for j in range(neg_lo, i)):
                return "without"
            # (e) a POST-cue negation restricting the population ("renal impairment NOT
            # present") ⇒ FAIL CLOSED. The pre-cue verb-negation is before the cue, so the
            # verb-negation guard "causes no nausea in renal" -> 'with' is preserved.
            if any(t in _POPULATION_NEGATION_CUES for t in post):
                return POLARITY_AMBIGUOUS
            # (f) a POST-cue passive restriction verb (removed/withdrawn/...) ⇒ FAIL CLOSED.
            if any(t in _POST_CUE_RESTRICTION_CUES for t in post):
                return POLARITY_AMBIGUOUS
            # (g) an exclusion-META noun ("as an EXCLUSION criterion") ⇒ FAIL CLOSED.
            if clause_set & _EXCLUSION_META_NOUNS:
                return POLARITY_AMBIGUOUS
            # (h) an unresolved relative clause ⇒ FAIL CLOSED to a singleton (never 'with').
            if clause_set & _RELATIVE_CLAUSE_MARKERS:
                return POLARITY_AMBIGUOUS
            return "with"
    return ""


def _classify_cue_bucket(cset: dict[str, Any], bucket_field: str, cue: str) -> str:
    """Return the ontology bucket name a matched PRESENT cue falls into, else '' (UNKNOWN).

    `bucket_field` is the per-concept lexicon sub-map name (`causal_strength_cues` for ae_causation,
    `warning_severity_cues` for warning). The matched `cue` is the exact lexicon string, so an exact
    `cue in bucket_list` membership test is sufficient and deterministic. A concept_type that owns no
    such sub-map, or a cue not partitioned into any bucket, yields '' (UNKNOWN) — design §4.4 Wave 3.
    """
    buckets = cset.get(bucket_field)
    if not isinstance(buckets, dict):
        return ''
    for bucket_name, bucket_cues in buckets.items():
        if cue in (bucket_cues or []):
            return str(bucket_name)
    return ''


def extract_qualitative_assertions(
    evidence: list[dict[str, Any]], domain: str | None = None,
) -> list[QualitativeAssertion]:
    """Extract qualitative clinical-safety assertions from evidence rows. One row may yield several
    (one per concept occurrence per sentence). `no_assertion` pseudo cues skip the span entirely."""
    lex = _load_lexicon()
    from src.polaris_graph.retrieval.contradiction_detector import _normalize_subject
    out: list[QualitativeAssertion] = []
    for ev in evidence or []:
        quote = ev.get("direct_quote") or ev.get("statement") or ""
        if not quote:
            continue
        evid = str(ev.get("evidence_id", ""))
        url = ev.get("source_url", "") or ev.get("url", "")
        tier = ev.get("tier", "") or ev.get("source_tier", "")
        for sentence in _split_sentences(quote):
            # the drug usually appears once at the head of the sentence; a clause that names no drug
            # inherits the sentence subject (so 'X is contraindicated ... but safe in ...' keeps X).
            sentence_subject = _normalize_subject(sentence, fallback="")
            for clause_raw in _split_clauses(sentence, lex["termination_terms"]):
                clause = clause_raw.lower()
                # true pseudo / no-assertion -> the concept is not asserted; skip this clause.
                if _phrase_present(clause, lex["no_assertion"]):
                    continue
                for concept_type, cset in lex["concept_types"].items():
                    present_hit = _find_longest_cue(clause, cset.get("present_cues", []))
                    absent_hit = _find_longest_cue(clause, cset.get("absent_cues", []))
                    hit, base = None, None
                    # prefer the longest matching cue across both polarities
                    if present_hit and absent_hit:
                        if len(absent_hit[0]) >= len(present_hit[0]):
                            hit, base = absent_hit, ABSENT
                        else:
                            hit, base = present_hit, PRESENT
                    elif present_hit:
                        hit, base = present_hit, PRESENT
                    elif absent_hit:
                        hit, base = absent_hit, ABSENT
                    if hit is None:
                        continue
                    cue, pos = hit
                    status = _classify_status(clause, cue, pos, base, lex)
                    subject = _normalize_subject(clause, fallback="") or sentence_subject
                    owner = lex["object_slot_owner"].get(concept_type, "object_slot")
                    object_slot, condition_scope = "", ""
                    cscope = _extract_condition_scope(clause, lex)
                    # POPULATION polarity of the same condition cue (Wave-3 #1245 P0).
                    # Aligns with cscope: non-empty cscope <-> polarity in {with, without};
                    # empty cscope <-> ''. Dormant: read ONLY by build_merge_key under the flag.
                    condition_polarity = _extract_condition_polarity(clause, lex)
                    if owner == "condition_scope":
                        condition_scope = cscope
                    else:
                        object_slot = _extract_object_slot(
                            clause_raw, clause, concept_type, pos, cue, subject
                        )
                        condition_scope = cscope
                    # Intra-slot ontology discriminators (Wave 3 §4.4): classify the matched cue ONLY
                    # on a PRESENT hit (an ABSENT cue is not partitioned into the present buckets).
                    # '' (UNKNOWN) for every other concept_type and on every absent hit. Dormant until
                    # claim_graph.build_merge_key reads it under PG_SWEEP_CREDIBILITY_REDESIGN.
                    causal_strength, warning_severity = '', ''
                    if base == PRESENT:
                        if concept_type == "ae_causation":
                            causal_strength = _classify_cue_bucket(
                                cset, "causal_strength_cues", cue)
                        elif concept_type == "warning":
                            warning_severity = _classify_cue_bucket(
                                cset, "warning_severity_cues", cue)
                    out.append(QualitativeAssertion(
                        evidence_id=evid, subject=subject, concept_type=concept_type,
                        object_slot=object_slot, condition_scope=condition_scope,
                        assertion_status=status, cue=cue, context_snippet=clause_raw[:200],
                        source_url=url, source_tier=tier,
                        causal_strength=causal_strength, warning_severity=warning_severity,
                        condition_polarity=condition_polarity,
                    ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Conflict detection (two-pass)
# ─────────────────────────────────────────────────────────────────────────────

_NCT_RE = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.IGNORECASE)
_PMID_RE = re.compile(r"/pubmed/(\d+)|[?&]pmid=(\d+)|\bPMID[:\s]+(\d+)", re.IGNORECASE)


def _normalize_source_id(url: str) -> str:
    """Normalize a source to a stable identity (NCT / DOI / PMID / host+path), so the same source
    self-quoted in two sections counts as ONE source and cannot raise a cross-source conflict."""
    u = (url or "").strip().lower()
    if not u:
        return ""
    m = _NCT_RE.search(u)
    if m:
        return "nct:" + m.group(0).lower()
    m = _DOI_RE.search(u)
    if m:
        return "doi:" + m.group(0)
    m = _PMID_RE.search(u)
    if m:
        return "pmid:" + next(g for g in m.groups() if g)
    u = re.split(r"[?#]", u)[0].rstrip("/")
    return u


def _claim_dict(a: QualitativeAssertion) -> dict[str, Any]:
    return {
        "evidence_id": a.evidence_id,
        "predicate": a.concept_type,
        "value": _VALUE_BY_STATUS.get(a.assertion_status, 0.5),  # finite float, loader-safe
        "subject": a.subject,
        "assertion_status": a.assertion_status,
        "object_slot": a.object_slot,
        "condition_scope": a.condition_scope,
        "source_url": a.source_url,
        "source_tier": a.source_tier,
        "context_snippet": a.context_snippet,
    }


def _predicate_label(concept_type: str, object_slot: str, condition_scope: str) -> str:
    qual = object_slot or condition_scope
    return f"{concept_type} ({qual})" if qual else concept_type


def _distinct_sources(assertions: list[QualitativeAssertion]) -> set[str]:
    return {_normalize_source_id(a.source_url) for a in assertions if _normalize_source_id(a.source_url)}


def _owner_value(a: QualitativeAssertion, owner_of: dict[str, str]) -> str:
    """The canonical discriminating slot value for this assertion's concept_type (Codex iter-2 P2.b)."""
    return a.object_slot if owner_of.get(a.concept_type, "object_slot") == "object_slot" else a.condition_scope


def _objects_disjoint(o1: str, o2: str) -> bool:
    """Two resolved object slots are 'determinably different' ONLY if both are non-empty and NEITHER
    contains the other — so 'an increased risk of pancreatitis' and 'pancreatitis' are NOT treated as
    different (same outcome, looser extraction), but 'nausea' and 'pancreatitis' ARE. An empty slot is
    unresolved → not determinably different → routes to review (never a silent drop)."""
    if not o1 or not o2:
        return False
    return o1 != o2 and o1 not in o2 and o2 not in o1


def detect_qualitative_conflicts(
    assertions: list[QualitativeAssertion],
) -> list[QualitativeConflictRecord]:
    """Two-pass: exact-key hard conflicts (Pass A) + coarse-key review flags (Pass B)."""
    owner_of = _load_lexicon()["object_slot_owner"]
    records: list[QualitativeConflictRecord] = []
    full: dict[tuple[str, str, str, str], list[QualitativeAssertion]] = {}
    coarse: dict[tuple[str, str], list[QualitativeAssertion]] = {}
    for a in assertions:
        if a.subject:
            full.setdefault((a.subject, a.concept_type, a.object_slot, a.condition_scope), []).append(a)
        coarse.setdefault((a.subject, a.concept_type), []).append(a)

    # ── PASS A: hard conflicts on the FULL key — ONLY when the owner slot is RESOLVED ────────────
    # (Codex diff-gate iter-1 P1.1: an unresolved/empty owner key must NOT hard-fire; it routes to
    # Pass B review.) The hard-conflict identity is keyed by the FULL key + the exact source pair
    # (Codex diff-gate iter-1 P1.2), so a hard conflict at one scope does NOT suppress review flags
    # for a DIFFERENT object_slot/condition_scope between the same sources.
    hard_keys: set[tuple] = set()  # (subject, concept_type, object_slot, condition_scope, src_a, src_b)
    for (subject, concept_type, object_slot, condition_scope), group in full.items():
        owner_val = object_slot if owner_of.get(concept_type, "object_slot") == "object_slot" else condition_scope
        if not owner_val:
            continue  # unresolved owner -> defer to Pass B review, never a hard conflict
        present = [a for a in group if a.assertion_status == PRESENT]
        absent = [a for a in group if a.assertion_status == ABSENT]
        if not present or not absent:
            continue
        src_present, src_absent = _distinct_sources(present), _distinct_sources(absent)
        if not src_present or not src_absent:
            continue  # need resolvable sources on both sides
        if not any(sp != sa for sp in src_present for sa in src_absent):
            continue  # all present/absent from the same single source -> not cross-source
        records.append(QualitativeConflictRecord(
            predicate=_predicate_label(concept_type, object_slot, condition_scope),
            claims=[_claim_dict(a) for a in present + absent], subject=subject, severity="high",
            conflict_reason=(
                f"{concept_type} asserted PRESENT and ABSENT across "
                f"{len(src_present | src_absent)} distinct sources at the same "
                f"{owner_of.get(concept_type, 'object')}='{owner_val}'."
            ),
        ))
        for sp in present:
            for sa in absent:
                pair = tuple(sorted((_normalize_source_id(sp.source_url),
                                     _normalize_source_id(sa.source_url))))
                hard_keys.add((subject, concept_type, object_slot, condition_scope, pair[0], pair[1]))

    # ── PASS B: review flags on the COARSE key (Codex iter-1 P1.2 + iter-2 P1.b/P2.a) ───────────
    for (subject, concept_type), group in coarse.items():
        definite = [a for a in group if a.assertion_status in _DEFINITE]
        soft = [a for a in group if a.assertion_status not in _DEFINITE]
        for i in range(len(definite)):
            for j in range(i + 1, len(definite)):
                ai, aj = definite[i], definite[j]
                if ai.assertion_status == aj.assertion_status:
                    continue
                sid_i, sid_j = _normalize_source_id(ai.source_url), _normalize_source_id(aj.source_url)
                if not sid_i or not sid_j or sid_i == sid_j:
                    continue  # same/unresolved source: not a cross-source disagreement
                # Suppress ONLY the EXACT pair already emitted as a hard conflict (same full key +
                # same source pair) — a hard conflict at a DIFFERENT scope/object does not suppress.
                if ai.object_slot == aj.object_slot and ai.condition_scope == aj.condition_scope:
                    pair = tuple(sorted((sid_i, sid_j)))
                    if (subject, concept_type, ai.object_slot, ai.condition_scope, pair[0], pair[1]) in hard_keys:
                        continue
                # determinable non-conflict ONLY if both object_slots resolved + clearly different
                if _objects_disjoint(ai.object_slot, aj.object_slot):
                    continue
                records.append(_review_record(
                    subject, concept_type, [ai, aj],
                    "object_slot or condition_scope differs/missing — review (not auto-fired)",
                ))
        # definite opposed by an INDETERMINATE / STATISTICAL_NULL across distinct sources -> review
        for d in definite:
            for s in soft:
                sid_d, sid_s = _normalize_source_id(d.source_url), _normalize_source_id(s.source_url)
                if not sid_d or not sid_s or sid_d == sid_s:
                    continue
                # determinable-different outcomes are unrelated -> no review noise (Codex diff-gate
                # iter-4 P2; same containment-aware guard as the definite-vs-definite path).
                if _objects_disjoint(d.object_slot, s.object_slot):
                    continue
                records.append(_review_record(
                    subject, concept_type, [d, s],
                    f"definite {d.assertion_status} vs {s.assertion_status} across sources — review",
                ))

    rank = {"high": 0, "medium": 1, "review": 2}
    records.sort(key=lambda r: (rank.get(r.severity, 3), r.predicate))
    return records


def _review_record(subject: str, concept_type: str, pair: list[QualitativeAssertion],
                   reason: str) -> QualitativeConflictRecord:
    objs = [a.object_slot for a in pair if a.object_slot]
    scopes = [a.condition_scope for a in pair if a.condition_scope]
    qual = (objs or scopes or [""])[0]
    return QualitativeConflictRecord(
        predicate=_predicate_label(concept_type, objs[0] if objs else "", scopes[0] if scopes else ""),
        claims=[_claim_dict(a) for a in pair], subject=subject, severity="review",
        conflict_reason=reason,
        recommended_action="Indeterminate qualitative disagreement — route to human review; do not treat as resolved.",
    )
