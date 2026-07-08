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


def _member_quote(member: Any) -> str:
    return str(
        (member.get("direct_quote") if isinstance(member, dict)
         else getattr(member, "direct_quote", "")) or ""
    ).strip()


def _member_source_label(member: Any) -> str:
    url = str(
        (member.get("source_url") if isinstance(member, dict)
         else getattr(member, "source_url", "")) or ""
    ).strip()
    eid = str(
        (member.get("evidence_id") if isinstance(member, dict)
         else getattr(member, "evidence_id", "")) or ""
    ).strip()
    tier = str(
        (member.get("source_tier") if isinstance(member, dict)
         else getattr(member, "source_tier", "")) or ""
    ).strip()
    label = url or eid or "source"
    return f"{label}" + (f" (tier {tier})" if tier else "")


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


def _boundary_quote_hygiene_enabled() -> bool:
    """``PG_BOUNDARY_QUOTE_HYGIENE`` kill-switch (default ON, LAW VI). OFF => the boundary quote is emitted
    unscreened (byte-identical to legacy). ON => a truncated / glued / render-chrome candidate quote is
    SKIPPED (the section falls through to the next candidate or emits nothing) so a broken 'graduatio...'
    fragment never renders as counter-evidence."""
    return os.getenv("PG_BOUNDARY_QUOTE_HYGIENE", "1").strip().lower() not in ("", "0", "false", "off", "no")


def _quote_is_unrenderable(quote: str) -> bool:
    """I-deepfix-001 (#1369) STEP 4: True iff a boundary candidate quote is render-chrome OR a
    truncated/glued fragment that reads as broken (the 'graduatio...' mid-word cut). Conservative — only
    rejects clear artifacts; a complete verbatim sentence is never rejected. Over-rejection is safe (it
    only withholds an anti-signal line, never a fact). Pure; never raises."""
    q = (quote or "").strip()
    if not q:
        return True
    # An embedded blank line signals a GLUED multi-fragment span (the 'graduatio' class).
    if "\n\n" in q or "\n \n" in q:
        return True
    try:
        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
            is_render_chrome_or_unrenderable,
        )
        if is_render_chrome_or_unrenderable(q):
            return True
    except Exception:  # noqa: BLE001 — screen is advisory; never break the render on a probe fault
        pass
    # Ends MID-WORD: no sentence-terminal punctuation AND the final token is a bare lowercase word fragment
    # (>=6 letters) — the 'graduatio' cut. Conservative: a quote ending in punctuation or a short word passes.
    if q[-1] not in ".!?\"')]}%":
        toks = q.split()
        last = toks[-1] if toks else ""
        if last.isalpha() and last.islower() and len(last) >= 6:
            return True
    return False


def synthesize_boundary_line(
    headline_baskets: Iterable[Any],
    candidate_baskets: Iterable[Any],
) -> str:
    """Synthesize ONE per-section boundary-conditions / counter-evidence line, or "".

    For the section's headline baskets (highest weight first), find the best qualifying lower-weight
    basket and quote its OWN span-verified member text, attributed to its source at its weight. Fires
    even without a refuter cluster. Returns "" when no qualifying lower-weight basket exists (caller
    appends nothing => byte-identical). Never fabricates — the quote is an already-verified span.
    """
    headlines = sorted(
        (b for b in (headline_baskets or [])),
        key=lambda b: -_basket_weight(b),
    )
    candidates = list(candidate_baskets or [])
    for headline in headlines:
        qualifier = find_qualifying_lower_weight_basket(headline, candidates)
        if qualifier is None:
            continue
        supports = _supports_members(qualifier)
        if not supports:
            continue
        member = supports[0]
        quote = _member_quote(member)
        if not quote:
            continue
        # I-deepfix-001 (#1369) STEP 4 anti-signal: skip a truncated / glued / chrome fragment (the
        # 'graduatio...' class) so it never renders as counter-evidence. Skipping falls through to the next
        # candidate; if none qualify the section emits nothing (byte-identical to no-qualifier).
        if _boundary_quote_hygiene_enabled() and _quote_is_unrenderable(quote):
            continue
        source = _member_source_label(member)
        subject = str(_basket_field(headline, "subject", "") or "").strip()
        topic = f" on {subject}" if subject else ""
        return (
            f"\n\n**Boundary conditions / counter-evidence{topic}:** a lower-weight source qualifies "
            f"or bounds the headline above — \"{quote}\" ({source}). This opposing/limiting evidence "
            "is surfaced at its weight; weigh it against the headline."
        )
    return ""
