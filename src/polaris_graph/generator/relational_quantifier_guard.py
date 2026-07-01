"""I-beatboth-011 keystone-F1 (#1284, task #505) — the RELATIONAL-QUANTIFIER guard (F1-2).

A pure, deterministic guard over a candidate multi-cited sentence + its supporting ``ClaimBasket``.
``strict_verify`` / span-grounding can confirm that every FACT in a sentence is span-true, but it
CANNOT verify a RELATIONAL QUANTIFIER: "studies CONSISTENTLY show X", "MOST studies find X", "X higher
than Y", "n of m" — every cited fact can be span-true while the aggregate word is invented across the
basket's members. The faithfulness engine has no hook for that aggregate predicate; this guard is the
COMPOSITION-LAYER check that closes the gap WITHOUT touching the engine (design basis §32-46,
PHASE4_DESIGN_BASIS_2026.md; `lane_synthesis_baskets_design.md` §2.3).

CONTRACT (binding):
  * The guard NEVER edits or relaxes ``strict_verify`` / NLI / 4-role / span-grounding. It runs OUTSIDE
    the engine on already-composed prose; its only effect is to STRIP an UNLICENSED relational
    quantifier so the residue carries no aggregate claim the basket does not license. A stripped
    sentence still carries its original ``[#ev:...]`` provenance tokens unchanged, so it re-passes the
    UNCHANGED ``strict_verify`` (the caller re-verifies — this module asserts nothing).
  * UNDER-RELAX IS SAFE; OVER-RELAX IS LETHAL (design §40). When the licensing state is uncertain the
    guard STRIPS the quantifier (the conservative direction). A genuinely-licensed quantifier (the
    whole basket agrees, zero refuters, independence weight-mass above the env threshold) is KEPT —
    but the increment-1 producer never EMITS one, so in practice the guard only ever fires on an LLM
    writer's fabricated predicate.
  * DETERMINISTIC LEXICON: a high-precision multi-word aggregate-predicate lexicon (LAW VI threshold
    via ``PG_RELATIONAL_QUANTIFIER_AGREEMENT_MIN``). A lexicon may miss a paraphrase; the F1-0 harness
    is the escape-catcher (design §53). It is PRECISION-first — it strips a known aggregate predicate,
    it does not touch ordinary prose.
  * PURE: no input mutation, no network, no model, no faithfulness-file import. snake_case. LAW VI.

KNOWN BOUND (honest, for a future writer author) — the verbatim-preservation check
(``_is_verbatim_source_text``) is WHOLE-CLAUSE: it preserves a source quantifier when the ENTIRE
candidate clause (sans provenance token + terminal punctuation) is a substring of one of the basket's
member spans. This fully covers the two currently-wired writer configs:
  * DEFAULT writer ``build_short_member_sentence`` returns a PURE verbatim span -> whole-substring match
    -> the source's quantifier is preserved.
  * ABSTRACTIVE writer (``PG_ABSTRACTIVE_WRITER`` on) is keyed by ``claim_cluster_id`` and returns a
    WHOLE-basket draft; the within-basket producer's single-member sub-basket lookup fails the
    single-member scoped pool -> ``_member_writer_clause`` returns None -> the producer uses the
    UNGUARDED verbatim K-span fallback -> the guard never runs.
What it does NOT cover: a PARTIALLY-synthesized clause that EMBEDS a verbatim source quantifier inside a
FABRICATED frame (e.g. "Studies consistently show that most patients recovered [#ev]" over a span "most
patients recovered") — the whole candidate is longer than the span, so it routes to ``_strip_quantifiers``
which would strip the embedded "most" too. This path is UNREACHABLE on the current default/abstractive
wiring (above). A FUTURE per-member-keyed writer that produces single-member clauses passing the scoped
pool while embedding a source quantifier in synthesized framing MUST re-verify this case (add
per-occurrence span-presence logic then, against a behavioral test on that writer's real output).
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

# LAW VI: the independence-weighted agreement threshold a basket must clear for a relational quantifier
# to be LICENSED (design §52 — no 2026 paper gives the formula, so it is an env-tunable). The agreement
# proxy is the share of the basket's members that are isolated-``SUPPORTS`` (corroborating).
#
# INCREMENT-1 DEFAULT = STRIP-ALWAYS (the boundary contract, advisor 2026-06-21 + brief §35-43):
# ``strict_verify`` / span-grounding CANNOT verify a relational quantifier, and this increment's producer
# composes per-MEMBER single-source clauses — it NEVER deliberately computes-and-emits a whole-basket
# consensus statement. So ANY quantifier reaching the guard is a fabrication of the (LLM) writer over a
# single member's clause, and must be STRIPPED. The default ``2.0`` is UNREACHABLE (agreement is in
# [0,1]), so the guard ALWAYS strips an unlicensed-by-construction quantifier — "under-relax is safe;
# over-relax is the lethal direction". The env knob is the seam a LATER increment uses (a producer that
# deliberately composes a disclosed consensus statement after the independence weight-mass computation
# can lower the threshold to, e.g., ``1.0`` = every member corroborates AND zero refuters); until then
# the gate stays closed. A value in [0,1] enables the licensing branch (zero refuters AND agreement >=
# threshold); the default keeps it closed.
_ENV_AGREEMENT_MIN = "PG_RELATIONAL_QUANTIFIER_AGREEMENT_MIN"
_DEFAULT_AGREEMENT_MIN = 2.0  # UNREACHABLE by construction => strip-always in increment 1 (boundary contract)

# A provenance token: ``[#ev:<evidence_id>:<start>-<end>]`` (the same shape strict_verify parses).
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")


def _agreement_min() -> float:
    """The configured independence-weighted agreement minimum (LAW VI). Returns the STRICT default
    (``2.0`` = unreachable = strip-always) when unset or on any unparseable / negative value
    (fail-CONSERVATIVE — a bad config strips MORE, never less). A value the operator deliberately sets
    in [0,1] is honored (it OPENS the licensing branch for a later consensus-statement producer); a
    value > 1.0 keeps the branch closed (strip-always)."""
    raw = os.environ.get(_ENV_AGREEMENT_MIN, "").strip()
    if raw == "":
        return _DEFAULT_AGREEMENT_MIN
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_AGREEMENT_MIN  # unparseable -> strict default
    if val != val or val < 0.0:  # NaN / negative -> strict default (never licenses MORE on bad input)
        return _DEFAULT_AGREEMENT_MIN
    return val


# ── The aggregate-predicate lexicon (high-precision, multi-word where possible) ────────────────────
#
# Each entry is a compiled regex that matches an aggregate/relational predicate AS IT APPEARS in prose.
# Two repair shapes:
#   * LEADING predicates ("Most studies show that ...", "Studies consistently show that ...") — the
#     match is a sentence-leading clause; stripping it + re-capitalizing the residue yields the faithful
#     single-claim sentence.
#   * INLINE quantifiers ("most", "the majority of", "consistently", "broadly") — stripped in place.
# The lexicon is PRECISION-first: it targets aggregate predicates, never ordinary determiners. "a", "the",
# "some", "several" are NOT aggregate consensus claims and are left untouched.

# Leading aggregate-attribution clauses: "<quantifier> studies/sources/researchers <verb> that".
_LEADING_ATTRIBUTION_RE = re.compile(
    r"^\s*(?:the\s+)?"
    r"(?:most|many|the\s+majority\s+of|nearly\s+all|almost\s+all|the\s+bulk\s+of|"
    r"a\s+(?:broad|wide)\s+(?:range|body)\s+of|numerous|several|multiple)?\s*"
    r"(?:studies|sources|researchers|papers|analyses|reports|experts|authors|works)\s+"
    r"(?:have\s+)?(?:consistently\s+|broadly\s+|overwhelmingly\s+|universally\s+|generally\s+|"
    r"largely\s+)?"
    r"(?:show|shows|showed|find|finds|found|report|reports|reported|agree|agrees|agreed|"
    r"demonstrate|demonstrates|demonstrated|conclude|concludes|concluded|suggest|suggests|"
    r"suggested|indicate|indicates|indicated|confirm|confirms|confirmed)\s+that\s+",
    re.IGNORECASE,
)

# Standalone "broad/wide consensus" / "growing consensus" attributions.
_CONSENSUS_LEADING_RE = re.compile(
    r"^\s*(?:there\s+is\s+|there\s+exists\s+)?"
    r"(?:a\s+)?(?:broad|wide|growing|strong|general|emerging)\s+consensus\s+(?:that|exists\s+that)\s+",
    re.IGNORECASE,
)

# Inline aggregate quantifiers/adverbs that assert cross-member agreement. Stripped in place. Bounded by
# word boundaries; multi-word phrases first so the longest match wins.
_INLINE_QUANTIFIERS = (
    r"the\s+majority\s+of\s+",
    r"the\s+vast\s+majority\s+of\s+",
    r"a\s+(?:broad|wide)\s+(?:majority|consensus|range)\s+of\s+",
    r"most\s+of\s+the\s+",
    r"most\s+",
    r"consistently\s+",
    r"overwhelmingly\s+",
    r"universally\s+",
    r"broadly\s+",
    r"unanimously\s+",
)
_INLINE_QUANTIFIER_RE = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(_INLINE_QUANTIFIERS) + r")",
    re.IGNORECASE,
)

# "n of m" / "X of Y studies" relational counts (an aggregate over the basket's members).
_N_OF_M_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:out\s+of|of)\s+"
    r"(?:\d+|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:studies|sources|researchers|papers|analyses|reports|trials)\s+",
    re.IGNORECASE,
)

# CROSS-MEMBER COMPARATIVE adverbs ("X higher than Y", "more than", "greater than") that assert a
# RELATION the basket's members do NOT individually license — a comparative across two members' spans is
# an aggregate the engine cannot verify. DETECTION-ONLY in increment 1: a comparative is reported by
# ``contains_relational_quantifier`` so the producer never silently co-locates one as a SYNTHESIZED
# clause, but ``_strip_quantifiers`` does NOT attempt to rewrite a comparative (deleting "higher than"
# mangles the sentence). Repair = drop the synthesized comparative clause to its VERBATIM K-span fallback
# (the producer's member-level fallback already does this when the synthesized clause is annihilated).
# A comparative INSIDE a single member's verbatim span (the source's own comparison) is faithful and
# preserved (the guard never runs on a verbatim K-span). Comparative full-rewrite is a DEFERRED increment.
_COMPARATIVE_RE = re.compile(
    r"(?<![A-Za-z])"
    r"(?:higher|greater|larger|lower|smaller|stronger|weaker|faster|slower|better|worse|more|less|"
    r"longer|shorter)\s+than\b",
    re.IGNORECASE,
)


# I-deepfix-001 M6 — the CLOSED set of cross-source analytical connective PHRASES + their relation key.
# These mirror ``cross_source_synthesis.LICENSED_CONNECTIVES`` (kept in sync). A connective is LICENSED
# upstream by a certified relation engine (``claim_graph`` ContradictionEdge / ``consolidation_nli`` /
# equivalence); the composer passes the licensed relation(s) via ``licensed_relations`` so the guard can
# NEUTRALIZE any connective whose relation was NOT licensed back to pure juxtaposition — "a wrong
# 'in contrast' can never render". The neutral phrase asserts no relation, so it is never neutralized.
_ANALYTICAL_CONNECTIVE_RELATION: dict[str, str] = {
    "in contrast": "conflict",
    "consistent with this": "agreement",
    "extending this": "extension",
}
_NEUTRAL_CONNECTIVE_PHRASE = "separately"
# Each relation phrase as it appears inside the connective ``; <phrase>, `` — captured WITH its leading
# "; " and trailing ", " so a neutralized phrase swaps cleanly to ``; separately, ``.
_ANALYTICAL_CONNECTIVE_RE = re.compile(
    r";\s*(?P<phrase>in contrast|consistent with this|extending this)\s*,\s*",
    re.IGNORECASE,
)


def _neutralize_unlicensed_connectives(sentence: str, licensed_relations: "set[str]") -> str:
    """Replace any analytical connective whose relation is NOT in ``licensed_relations`` with the neutral
    juxtaposition connective ``; separately, ``. A connective whose relation IS licensed is preserved
    verbatim. Pure; deterministic. The neutral connective itself is never matched (it asserts no
    relation), so over-application is impossible."""
    def _swap(m: "re.Match") -> str:
        phrase = m.group("phrase").strip().lower()
        relation = _ANALYTICAL_CONNECTIVE_RELATION.get(phrase, "")
        if relation and relation in licensed_relations:
            return m.group(0)  # licensed -> keep verbatim
        return f"; {_NEUTRAL_CONNECTIVE_PHRASE}, "  # unlicensed -> neutralize
    return _ANALYTICAL_CONNECTIVE_RE.sub(_swap, sentence)


def contains_relational_quantifier(sentence: str) -> bool:
    """True iff ``sentence`` carries a detectable aggregate/relational quantifier (lexicon hit).

    Detection-only — used by the harness + the producer to decide whether the guard needs to act.
    A sentence with NO aggregate predicate returns False and is returned unchanged by the repair."""
    text = sentence or ""
    return bool(
        _LEADING_ATTRIBUTION_RE.search(text)
        or _CONSENSUS_LEADING_RE.search(text)
        or _INLINE_QUANTIFIER_RE.search(text)
        or _N_OF_M_RE.search(text)
        or _COMPARATIVE_RE.search(text)
    )


def _basket_licenses_quantifier(basket: Any) -> bool:
    """True iff the basket's consensus state LICENSES a relational quantifier (design §2.3):
      (a) ZERO refuters / ContradictionEdge among its members (an unrefuted claim), AND
      (b) the independence-weighted agreement (share of SUPPORTS members) is >= the env threshold.

    Conservative on missing data: an empty / unreadable basket does NOT license (returns False ⇒ the
    quantifier is stripped). UNDER-relax is safe; over-relax is lethal."""
    if basket is None:
        return False
    # (a) refuters / contradiction references mark the basket contested -> NEVER license a consensus word.
    refuters = getattr(basket, "refuter_cluster_ids", None) or ()
    try:
        if len(tuple(refuters)) > 0:
            return False
    except TypeError:
        return False
    verdict = str(getattr(basket, "basket_verdict", "") or "").strip().lower()
    if verdict == "contested":
        return False
    # (b) agreement = SUPPORTS share of the basket's members (independence proxy). A relational
    # quantifier asserts the WHOLE basket agrees; a basket with any non-SUPPORTS member is below 1.0.
    members = list(getattr(basket, "supporting_members", None) or [])
    if not members:
        return False
    supports = sum(1 for m in members
                   if str(getattr(m, "span_verdict", "") or "").upper() == "SUPPORTS")
    agreement = supports / float(len(members))
    return agreement >= _agreement_min()


def _strip_provenance_tokens(sentence: str) -> str:
    """The sentence with its ``[#ev:...]`` provenance token(s) removed + whitespace normalized — the
    bare prose to compare against the source span. Pure."""
    bare = _EV_TOKEN_RE.sub("", sentence or "")
    return re.sub(r"\s+", " ", bare).strip()


def _basket_source_spans(basket: Any) -> list[str]:
    """The whitespace-normalized ``direct_quote`` span text of every SUPPORTS member of the basket —
    the verbatim source words the writer may legitimately quote. Used to tell a SOURCE-WRITTEN quantifier
    (must be preserved) from a SYNTHESIZED one (must be stripped). Pure; empty list on a memberless
    basket."""
    spans: list[str] = []
    for m in (getattr(basket, "supporting_members", None) or []):
        if str(getattr(m, "span_verdict", "") or "").upper() != "SUPPORTS":
            continue
        quote = str(getattr(m, "direct_quote", "") or "")
        norm = re.sub(r"\s+", " ", quote).strip()
        if norm:
            spans.append(norm)
    return spans


def _is_verbatim_source_text(sentence: str, basket: Any) -> bool:
    """True iff ``sentence`` (sans provenance tokens + terminal punctuation) is a VERBATIM substring of
    one of the basket's SUPPORTS member spans — i.e. the writer QUOTED the source rather than synthesized.

    A quantifier inside such a quotation ("Most of the surveyed firms ...") is the SOURCE's own word, NOT
    a fabricated aggregate — the guard MUST NOT strip it (that would misquote the source). The default
    production writer ``build_short_member_sentence`` returns exactly such a verbatim span, so this check
    is what keeps the guard off the source's words on the default path. Case-insensitive on the prose, but
    only after token-stripping — the span comparison is on text the source actually wrote. Pure."""
    bare = _strip_provenance_tokens(sentence)
    # Drop a single trailing terminal so "X." matches a source span "X" (the producer adds the period).
    if bare[-1:] in ".!?":
        bare = bare[:-1].rstrip()
    if not bare:
        return False
    bare_low = bare.lower()
    for span in _basket_source_spans(basket):
        if bare_low in span.lower():
            return True
    return False


def _recapitalize(text: str) -> str:
    """Capitalize the FIRST alphabetic character of ``text`` (after a leading clause was stripped, the
    residue must read as a proper sentence). No-op on empty / non-alpha-leading text."""
    s = (text or "").lstrip()
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
        if ch.isalnum():
            return s  # leading digit — nothing to capitalize
    return s


def _strip_quantifiers(sentence: str) -> str:
    """Remove every detected aggregate/relational predicate from ``sentence`` (the conservative repair).

    LEADING attribution clauses ("Most studies show that ...") are removed and the residue
    re-capitalized; INLINE quantifiers ("most", "the majority of", "consistently") are removed in place;
    "n of m studies" counts are removed. The ``[#ev:...]`` provenance tokens are NEVER touched, so the
    residue re-passes the UNCHANGED strict_verify. Whitespace is normalized. Pure."""
    text = sentence or ""
    # 1) Leading attribution / consensus clauses (strip then re-capitalize the residue).
    leading_stripped = False
    m = _LEADING_ATTRIBUTION_RE.search(text)
    if m and m.start() == 0:
        text = text[m.end():]
        leading_stripped = True
    else:
        m = _CONSENSUS_LEADING_RE.search(text)
        if m and m.start() == 0:
            text = text[m.end():]
            leading_stripped = True
    # 2) Inline quantifiers + n-of-m counts (remove in place; iterate to convergence for stacked hits).
    prev = None
    while prev != text:
        prev = text
        text = _INLINE_QUANTIFIER_RE.sub("", text)
        text = _N_OF_M_RE.sub("", text)
    # 3) Normalize whitespace introduced by removals (keep token spacing intact).
    text = re.sub(r"\s+", " ", text).strip()
    # 4) Re-capitalize when a leading clause was removed (the residue is now the sentence head). Also
    #    capitalize when an inline leading quantifier ("Most studies ...") left a lowercased head.
    if leading_stripped or (sentence[:1].isupper() and text[:1].islower()):
        text = _recapitalize(text)
    return text


def guard_relational_quantifier(
    sentence: str,
    basket: Any,
    *,
    licensed_relations: "set[str] | None" = None,
) -> Optional[str]:
    """The guard: given a candidate sentence + its supporting basket, return the sentence with any
    UNLICENSED relational quantifier STRIPPED (faithful residue), else the sentence unchanged.

    Decision:
      * No detectable quantifier  -> return ``sentence`` unchanged (the common, fast path).
      * Quantifier present AND the basket LICENSES it (zero refuters, agreement >= threshold) -> KEEP
        (return unchanged). [Increment-1 producers never emit one, so this branch is rarely taken.]
      * Quantifier present AND NOT licensed -> STRIP it, returning the faithful residue (its provenance
        tokens intact, so the caller's UNCHANGED strict_verify re-passes it).

    I-deepfix-001 M6 — ``licensed_relations`` (cross-source analytical path): when supplied (a set of
    engine-licensed relation keys, e.g. ``{"conflict"}``), the sentence is a COMPOSED analytical
    sentence whose two atoms were ALREADY individually guarded/verified when built; the guard's ONLY job
    here is to NEUTRALIZE any analytical connective whose relation was NOT licensed (a wrong "in
    contrast" -> "; separately, "). It does NOT re-run the per-clause aggregate strip on the multi-basket
    sentence (that would mis-handle a verbatim comparative inside an atom). ``licensed_relations=None``
    (default) is BYTE-IDENTICAL to the legacy single-clause behavior.

    Returns ``None`` ONLY when stripping leaves NO content-bearing residue (the sentence was nothing but
    an aggregate predicate with no span-grounded claim) — the caller then drops that unit (an aggregate
    predicate with no underlying span is not a faithful claim to render). A residue that still carries a
    provenance token is ALWAYS returned (never annihilated). This module NEVER asserts the residue is
    verified — the caller re-runs the UNCHANGED strict_verify."""
    text = sentence or ""
    if not text.strip():
        return None
    if licensed_relations is not None:
        # Cross-source analytical sentence: license-check the connective only (atoms already guarded).
        neutralized = _neutralize_unlicensed_connectives(text, set(licensed_relations))
        return neutralized if neutralized.strip() else None
    if not contains_relational_quantifier(text):
        return text
    # VERBATIM SOURCE TEXT is faithful-by-construction: a quantifier the SOURCE itself wrote (the candidate
    # is a substring of one of the basket's member spans) is a QUOTATION, never a fabricated aggregate.
    # NEVER strip it — that would misquote the source (the lethal direction). The default production writer
    # ``build_short_member_sentence`` returns exactly such a verbatim span, so this is the load-bearing
    # check that keeps the guard off the source's own words. Only SYNTHESIZED prose (absent from every
    # member span) reaches the strip/drop branches below.
    if _is_verbatim_source_text(text, basket):
        return text
    if _basket_licenses_quantifier(basket):
        # Genuinely licensed by the whole-basket consensus state — keep as composed (the engine still
        # gates the underlying facts; the quantifier is the disclosed consensus state).
        return text
    # A SYNTHESIZED comparative ("X higher than Y") cannot be cleanly word-deleted without mangling the
    # sentence; full comparative rewrite is DEFERRED. DROP the synthesized clause (return None) so the
    # caller falls back to the member's VERBATIM K-span — under-relax is safe. (A comparative inside a
    # verbatim span never reaches the guard: the producer only guards synthesized writer output.)
    if _COMPARATIVE_RE.search(text):
        return None
    repaired = _strip_quantifiers(text)
    # Never annihilate a span-grounded claim: if a provenance token survives, return the residue. Only a
    # residue with NO token left (a pure predicate, no underlying span) returns None (caller drops it).
    if not repaired or not _EV_TOKEN_RE.search(repaired):
        return None
    return repaired
