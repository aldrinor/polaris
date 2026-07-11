"""B2 (I-deepfix-001 #1344) — per-section boundary-conditions / counter-evidence line.

DeepTRACE one-sided #1 · DRB-II analysis · Telus clinical balance. The existing both-sides render
fires ONLY when a refuter CLUSTER exists (``refuter_cluster_ids``), which consolidation rarely
produces — so a headline claim renders with no opposing caveat or boundary even when the weighted
corpus already holds a LOWER-WEIGHT source that qualifies or bounds it.

THE FIX (this module, pure): for a section's headline baskets, synthesize ONE rendered
"Boundary conditions / counter-evidence" line drawn from LOWER-WEIGHT baskets that qualify or bound
the headline — a low-weight source that dissents or narrows the claim STAYS and is surfaced AT ITS
WEIGHT (WEIGHT-IN, not filter-out). The line quotes the lower-weight basket's OWN span-verified
member text (faithful-by-quotation — the same span already passed isolated verification), attributed
to its source; it NEVER fabricates opposition and fires even without a refuter cluster.

§-1.3 DNA — surfaces opposition ALREADY PRESENT in the weighted corpus; adds nothing, drops nothing,
invents nothing. A qualifying basket is one that (a) shares >=2 content words with the headline
(same topic), (b) carries strictly LOWER ``weight_mass`` than the headline, and (c) either is
referenced as a refuter OR its claim carries a boundary/qualifier marker ("only", "except",
"in patients with", "when", threshold wording). Faithfulness is untouched: the line is a marker-less
disclosure appended AFTER strict_verify, quoting an already-verified span; it is never a new claim
fed to the faithfulness engine. PURE / offline. LAW VI kill-switch. snake_case.
"""
from __future__ import annotations

import os
import re
from typing import Any, Iterable, Optional

_ENV_FLAG = "PG_SECTION_BOUNDARY_CONDITIONS"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})
_MIN_OVERLAP_ENV = "PG_SECTION_BOUNDARY_MIN_OVERLAP"
_DEFAULT_MIN_OVERLAP = 2

# Boundary / qualifier markers — a claim carrying one is a candidate to BOUND a headline. Overridable
# via config (comma-separated PG_SECTION_BOUNDARY_MARKERS) so it is not a hard-coded constant (LAW VI).
_DEFAULT_MARKERS = (
    "only", "except", "unless", "however", "but not", "limited to", "restricted to",
    "in patients with", "in adults with", "when ", "if ", "provided that", "conditional on",
    "no significant", "did not", "failed to", "not associated", "no difference", "no benefit",
    "at doses", "above ", "below ", "at least", "greater than", "less than", "subgroup",
    "baseline", "threshold", "contraindicated", "caution",
)

_CONTENT_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
_STOPWORDS = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "had", "was", "were",
    "are", "been", "will", "would", "could", "should", "their", "there", "these", "those",
    "which", "while", "when", "where", "what", "who", "whom", "into", "than", "then", "such",
    "also", "not", "but", "its", "our", "your", "his", "her", "they", "them", "some", "more",
    "most", "over", "under", "between", "among", "per", "via", "about", "each", "any", "all",
    "may", "can", "does", "did", "only",
})


def boundary_conditions_enabled() -> bool:
    """B2 kill-switch. Default ON; OFF => no boundary line synthesized (byte-identical revert)."""
    return os.environ.get(_ENV_FLAG, "1").strip().lower() not in _OFF_VALUES


def _min_overlap() -> int:
    try:
        return max(1, int(os.environ.get(_MIN_OVERLAP_ENV, str(_DEFAULT_MIN_OVERLAP)).strip()))
    except (TypeError, ValueError):
        return _DEFAULT_MIN_OVERLAP


def _markers() -> tuple:
    raw = os.environ.get("PG_SECTION_BOUNDARY_MARKERS", "").strip()
    if raw:
        return tuple(m.strip().lower() for m in raw.split(",") if m.strip())
    return _DEFAULT_MARKERS


def _content_words(text: str) -> set[str]:
    return {
        w.lower() for w in _CONTENT_WORD_RE.findall(text or "")
        if w.lower() not in _STOPWORDS
    }


def _basket_field(basket: Any, name: str, default: Any = "") -> Any:
    if isinstance(basket, dict):
        return basket.get(name, default)
    return getattr(basket, name, default)


def _basket_weight(basket: Any) -> float:
    try:
        return float(_basket_field(basket, "weight_mass", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _basket_claim_text(basket: Any) -> str:
    txt = str(_basket_field(basket, "claim_text", "") or "").strip()
    if txt:
        return txt
    subj = str(_basket_field(basket, "subject", "") or "").strip()
    pred = str(_basket_field(basket, "predicate", "") or "").strip()
    return f"{subj} {pred}".strip()


def _supports_members(basket: Any) -> list:
    out = []
    for m in _basket_field(basket, "supporting_members", None) or []:
        verdict = str(
            (m.get("span_verdict") if isinstance(m, dict) else getattr(m, "span_verdict", "")) or ""
        ).upper()
        if verdict == "SUPPORTS":
            out.append(m)
    return out


_PROVENANCE_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
_WWW_RE = re.compile(r"^www\.", re.IGNORECASE)


def _member_field(member: Any, name: str, default: str = "") -> str:
    val = member.get(name) if isinstance(member, dict) else getattr(member, name, default)
    return str(val or default)


def _strip_provenance_tokens(text: str) -> str:
    """Drop every ``[#ev:...]`` provenance token from ``text`` — the boundary line is appended AFTER the
    section's citation resolve, so a leftover raw token would render as chrome. Pure."""
    return " ".join(_PROVENANCE_TOKEN_RE.sub(" ", text or "").split())


def _domain_of(url: str) -> str:
    """The bare host of a URL (scheme + leading ``www.`` stripped), e.g. `` scholar.google.com ``. Pure;
    returns "" for an empty / path-only string."""
    u = (url or "").strip()
    if not u:
        return ""
    u = _SCHEME_RE.sub("", u)
    u = u.split("/", 1)[0].split("?", 1)[0]
    u = _WWW_RE.sub("", u)
    return u.strip()


def _member_source_label(member: Any, weight: float = 0.0) -> str:
    """Fix 1 (P0-1, 2026-07-10 compose gear-loop iter 2): render the STANDARD citation marker for a
    boundary-line source — a human title or the bare source DOMAIN, plus the credibility WEIGHT — NEVER a
    raw ``https://…`` URL with a "(tier UNKNOWN)" suffix. A real tier is shown only when it is a genuine
    tier value (never the empty / "UNKNOWN" placeholder). Pure."""
    title = _member_field(member, "source_title").strip() or _member_field(member, "title").strip()
    domain = _domain_of(_member_field(member, "source_url"))
    label = title or domain or _member_field(member, "evidence_id").strip() or "source"
    if len(label) > 80:
        label = label[:77].rstrip() + "…"
    tier = _member_field(member, "source_tier").strip()
    parts = [label]
    if weight and weight > 0:
        parts.append(f"weight {weight:.2f}")
    if tier and tier.upper() not in ("", "UNKNOWN", "NONE"):
        parts.append(f"tier {tier}")
    return parts[0] + ((" — " + ", ".join(parts[1:])) if len(parts) > 1 else "")


def _carries_boundary_marker(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _markers())


def find_qualifying_lower_weight_basket(
    headline_basket: Any,
    candidate_baskets: Iterable[Any],
) -> Optional[Any]:
    """The best LOWER-WEIGHT basket that qualifies/bounds ``headline_basket`` — or None. PURE.

    A candidate qualifies iff it shares >= min-overlap content words with the headline, has strictly
    lower ``weight_mass``, carries a span-verified (SUPPORTS) member, and either is referenced by the
    headline's ``refuter_cluster_ids`` OR its claim carries a boundary/qualifier marker. Ties break by
    (max content overlap, then lowest weight) for determinism. Never returns the headline itself.
    """
    headline_words = _content_words(_basket_claim_text(headline_basket))
    if not headline_words:
        return None
    headline_weight = _basket_weight(headline_basket)
    headline_ccid = str(_basket_field(headline_basket, "claim_cluster_id", "") or "")
    refuter_ids = {str(c) for c in (_basket_field(headline_basket, "refuter_cluster_ids", ()) or ())}
    min_ov = _min_overlap()

    best = None
    best_key: tuple = (-1, 0.0)
    for cand in candidate_baskets or ():
        ccid = str(_basket_field(cand, "claim_cluster_id", "") or "")
        if ccid and ccid == headline_ccid:
            continue
        if _basket_weight(cand) >= headline_weight:
            continue  # must be strictly LOWER weight
        supports = _supports_members(cand)
        if not supports:
            continue  # can only surface a span-verified (faithful) quote
        claim = _basket_claim_text(cand)
        overlap = len(headline_words & _content_words(claim))
        if overlap < min_ov:
            continue
        is_refuter = bool(ccid and ccid in refuter_ids)
        if not is_refuter and not _carries_boundary_marker(claim):
            continue
        key = (overlap, -_basket_weight(cand))  # more overlap, then lower weight, wins
        if key > best_key:
            best_key = key
            best = cand
    return best


def select_boundary_qualifier(
    headline_baskets: Iterable[Any],
    candidate_baskets: Iterable[Any],
) -> Optional[tuple]:
    """Fix 1 (P0-1, 2026-07-10 compose gear-loop iter 2): PURE selection of the ONE boundary qualifier.

    For the section's headline baskets (highest weight first), return the FIRST ``(headline, qualifier,
    member)`` whose best lower-weight qualifying basket carries a span-verified (SUPPORTS) member, or
    None. This is the selection half of the boundary line; the CALLER then synthesizes ONE clean
    sentence from ``qualifier`` via the abstractive writer (same base verify bar) and hands it to
    :func:`synthesize_boundary_line`. Pure; no LLM, no I/O."""
    headlines = sorted((b for b in (headline_baskets or [])), key=lambda b: -_basket_weight(b))
    candidates = list(candidate_baskets or [])
    for headline in headlines:
        qualifier = find_qualifying_lower_weight_basket(headline, candidates)
        if qualifier is None:
            continue
        supports = _supports_members(qualifier)
        if not supports:
            continue
        return headline, qualifier, supports[0]
    return None


def synthesize_boundary_line(
    headline_baskets: Iterable[Any],
    candidate_baskets: Iterable[Any],
    synthesized_by_cluster: Optional[dict] = None,
) -> str:
    """Synthesize ONE per-section boundary-conditions / counter-evidence line, or "".

    Fix 1 (P0-1, 2026-07-10 compose gear-loop iter 2): STOP quoting the qualifier's RAW member text —
    with chunk-sized members that is a webpage DUMP by construction. Instead render ONE LLM-synthesized
    qualifier SENTENCE (produced upstream by the same abstractive writer + base verify bar: context NLI
    entailment + forward numeric match) stating what the lower-weight source bounds/qualifies, cited to
    the qualifier basket. ``synthesized_by_cluster`` maps the qualifier basket's ``claim_cluster_id`` ->
    its verified synthesized sentence (may still carry an ``[#ev:...]`` token, stripped for display here).
    When no synthesis is available for the selected qualifier — the writer produced nothing or the draft
    FAILED verify — this returns "" (the existing no-qualifier byte-identical path). It NEVER falls back
    to the raw quote. Returns "" when no qualifying lower-weight basket exists at all. Pure."""
    sel = select_boundary_qualifier(headline_baskets, candidate_baskets)
    if sel is None:
        return ""
    headline, qualifier, member = sel
    cid = str(_basket_field(qualifier, "claim_cluster_id", "") or "")
    synth = str((synthesized_by_cluster or {}).get(cid, "") or "")
    sentence = _strip_provenance_tokens(synth)
    if not sentence:
        # No verified synthesis for this qualifier -> emit nothing. NEVER a raw quote.
        return ""
    if sentence[-1:] not in ".!?":
        sentence += "."
    source = _member_source_label(member, _basket_weight(qualifier))
    subject = str(_basket_field(headline, "subject", "") or "").strip()
    # The " on {subject}" topic suffix reads as chrome when the subject is a single garbage token; require
    # >= 2 content words for it to render (else the bare label).
    topic = f" on {subject}" if len(_content_words(subject)) >= 2 else ""
    return (
        f"\n\n**Boundary conditions / counter-evidence{topic}:** a lower-weight source qualifies "
        f"or bounds the headline above — {sentence} ({source}) This opposing/limiting evidence "
        "is surfaced at its weight; weigh it against the headline."
    )
