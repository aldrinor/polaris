"""U11 (I-deepfix-001) — clinical evidence-type query expansion (T1/T2 RECALL weight).

Clinical runs starve high-tier evidence (T1 randomized controlled trials /
systematic reviews / meta-analyses, T2 clinical practice guidelines) because the
sub-queries fired at the search backends (Serper / S2 / OpenAlex / Europe PMC) are
plain natural language with NO evidence-type targeting. The candidate pool is then
dominated by generic web pages and the primary literature ranks below the fold.

This module ADDS a small, bounded set of evidence-type-targeted VARIANTS of the
anchor query (e.g. ``"<q> randomized controlled trial"``,
``"<q> systematic review meta-analysis"``, ``"<q> clinical practice guideline"``)
so the high-tier literature SURFACES in the search results.

CLAUDE.md §-1.3 (WEIGHT, DON'T FILTER): expansion is purely ADDITIVE. It appends
discovery queries; it NEVER drops, caps, thins, or filters a source, and it never
targets a breadth NUMBER. The original NL queries still fire unchanged, and every
added candidate flows through the SAME fetch -> tier -> strict_verify / NLI /
provenance chokepoint as every other source. The faithfulness engine is untouched.

Deterministic, no LLM, no network — a pure string transform (reproducible).

All knobs are env vars (LAW VI): ``PG_EVIDENCE_TYPE_QUERY_EXPANSION`` (kill switch,
default OFF => byte-identical) and ``PG_EVIDENCE_TYPE_QUERY_TERMS`` (comma list of
evidence-type qualifiers, overrides the clinical defaults).
"""
from __future__ import annotations

import logging
import os
from typing import Iterable
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.evidence_type_query_expansion")

# The high-tier clinical evidence types the expansion targets, in GRADE order
# (RCT / systematic review + meta-analysis / practice guideline). These qualifiers
# are appended to the anchor query so the search engines rank the primary
# literature that carries them above generic web.
_DEFAULT_CLINICAL_EVIDENCE_TYPE_TERMS: tuple[str, ...] = (
    "randomized controlled trial",
    "systematic review meta-analysis",
    "clinical practice guideline",
)


def evidence_type_query_expansion_enabled() -> bool:
    """True iff the U11 evidence-type expansion flag is ON.

    Default OFF: unset / empty => no expansion and the effective query list is
    byte-identical to before this wiring.
    """
    return resolve("PG_EVIDENCE_TYPE_QUERY_EXPANSION").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _evidence_type_terms() -> tuple[str, ...]:
    """Parse ``PG_EVIDENCE_TYPE_QUERY_TERMS`` into the qualifier tuple.

    Format: ``randomized controlled trial,systematic review,practice guideline``.
    Unset / empty / all-blank => the clinical defaults. Malformed (all-blank
    entries) never crash: blanks are skipped and the defaults backstop an empty
    result (fail-safe, LAW II).
    """
    raw = resolve("PG_EVIDENCE_TYPE_QUERY_TERMS").strip()
    if not raw:
        return _DEFAULT_CLINICAL_EVIDENCE_TYPE_TERMS
    terms = tuple(t.strip() for t in raw.split(",") if t.strip())
    return terms or _DEFAULT_CLINICAL_EVIDENCE_TYPE_TERMS


def expand_evidence_type_queries(
    base_queries: Iterable[str],
    *,
    clinical: bool,
    enabled: bool | None = None,
    terms: Iterable[str] | None = None,
) -> list[str]:
    """Return ``base_queries`` UNCHANGED, plus evidence-type-targeted variants.

    A bounded set of variants is appended for the ANCHOR query (the first
    non-empty base query) — one per high-tier evidence type — so the search
    backends surface RCTs / systematic reviews / meta-analyses / guidelines that
    a plain NL query buries. Expansion is anchor-only so the added query count is
    bounded (it does not multiply with the sub-query count) and each backend
    round-trip stays affordable.

    Args:
        base_queries: the effective query list already compiled upstream.
        clinical: whether this is a clinical-domain run. Expansion fires ONLY
            when this is True — non-clinical runs are returned unchanged.
        enabled: kill-switch override (defaults to the env knob). When falsy the
            input is returned unchanged (byte-identical).
        terms: evidence-type qualifier override (defaults to the env knob).

    Returns:
        A NEW list: the original queries in their original order, followed by the
        de-duplicated (case-insensitive) evidence-type variants. Never drops or
        reorders the originals (WEIGHT-not-filter, §-1.3).
    """
    out = [q for q in base_queries]
    if enabled is None:
        enabled = evidence_type_query_expansion_enabled()
    if not enabled or not clinical:
        return out
    if terms is None:
        terms = _evidence_type_terms()

    anchor = ""
    for q in out:
        if isinstance(q, str) and q.strip():
            anchor = q.strip()
            break
    if not anchor:
        # No usable anchor text (empty / non-string queries) — nothing to expand.
        return out

    seen = {q.strip().lower() for q in out if isinstance(q, str)}
    added = 0
    for term in terms:
        term = term.strip()
        if not term:
            continue
        variant = f"{anchor} {term}"
        key = variant.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(variant)
        added += 1

    if added:
        logger.info(
            "[evidence_type_query_expansion] added %d clinical evidence-type "
            "sub-queries off anchor %r",
            added, anchor[:80],
        )
    return out
