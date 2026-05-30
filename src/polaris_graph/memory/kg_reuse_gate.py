"""Campaign knowledge-graph reuse read-path, FAIL-CLOSED (I-meta-002-q1d #948).

The `VerifiedClaimGraphStore` was WRITE-ONLY — nothing read `query_related_claims` back into generation, so
the citation-snowball never reused a prior question's VERIFIED facts. This wires the read-path in, but the
reuse is MECHANICALLY fail-closed (Codex brief-gate iter-1 P1): a prior-VERIFIED claim is OMITTED before it
ever reaches a prompt UNLESS the CURRENT question's corpus independently supports it, judged by the SAME
content-overlap + decimal primitives the verified chokepoint (`strict_verify`) uses. A surviving claim is
anchored ONLY to the CURRENT evidence id that supports it — NEVER a prior evidence id, NEVER prior provenance.

So reuse can only ever SURFACE a fact that is already present-and-supported in this question's corpus
(a cross-question relevance signal); it can never introduce an unsupported claim. The verified core
(multi_section generator + strict_verify) and the anti-poisoning store (only VERIFIED rows reusable) are
untouched. Default OFF (`PG_SWEEP_KG_REUSE`); read-only; no network; no model; NO SPEND.
"""

from __future__ import annotations

import os
from typing import Any

# Reuse the verified chokepoint's OWN primitives so the match-gate is identical to strict_verify's
# content rule (§9.1.3 checks (d) decimal-subset + (e) >= min content-word overlap).
from src.polaris_graph.clinical_generator.strict_verify import (
    _content_words,
    _decimals,
    _min_overlap_threshold,
)

_OFF_VALUES = frozenset({"0", "false", "False", "no", "off", ""})


def kg_reuse_enabled() -> bool:
    """Default OFF — the read-path changes the analyst prompt; opt-in until a live smoke validates it.
    Normalize before comparison (Codex diff-gate iter-1 P2) so FALSE/NO/OFF (any case) stay disabled."""
    return os.getenv("PG_SWEEP_KG_REUSE", "0").strip().lower() not in _OFF_VALUES


def match_prior_claims_to_current_corpus(
    prior_claim_texts: list[str],
    evidence_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """MECHANICAL fail-closed gate. Return one record per prior claim that is INDEPENDENTLY supported by
    the CURRENT corpus — `{"claim_text", "evidence_id"}` anchored to the matching CURRENT evidence id.
    A prior claim is kept iff some current evidence row shares >= min-overlap content words AND contains
    every decimal in the claim (mirroring strict_verify). Unmatched prior claims are OMITTED (never
    returned, so they never reach a prompt). NEVER returns a prior evidence id."""
    threshold = _min_overlap_threshold()
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for claim in prior_claim_texts or []:
        claim = (claim or "").strip()
        if not claim or claim in seen:
            continue
        claim_words = _content_words(claim)
        claim_decimals = _decimals(claim)
        for ev in evidence_rows or []:
            quote = ev.get("direct_quote") or ev.get("statement") or ""
            if not quote:
                continue
            if (len(claim_words & _content_words(quote)) >= threshold
                    and claim_decimals <= _decimals(quote)):
                seen.add(claim)
                out.append({"claim_text": claim, "evidence_id": str(ev.get("evidence_id", ""))})
                break  # first current-corpus support is enough
    return out


def gather_reuse_context(
    campaign_db_path: str,
    question: str,
    evidence_rows: list[dict[str, Any]],
    *,
    cap: int = 5,
) -> list[dict[str, str]]:
    """Open the campaign KG READ-ONLY, query prior-VERIFIED claims related to `question`, and return only
    those mechanically supported by the CURRENT corpus (capped). Fail-open: any store/read error returns
    [] (reuse is advisory; it must never abort or alter a run)."""
    if not kg_reuse_enabled():
        return []
    try:
        from src.polaris_graph.memory.verified_claim_graph import VerifiedClaimGraphStore
        # READ-ONLY open (Codex diff-gate iter-1 P1): never create/migrate/write-lock/mutate the campaign
        # db. A missing/unreadable db raises → the outer except fail-opens to [].
        store = VerifiedClaimGraphStore(db_path=campaign_db_path, read_only=True)
        try:
            related = store.query_related_claims(question)
        finally:
            store.close()
        prior_texts = [r.claim_text for r in related if getattr(r, "claim_text", "")]
        matched = match_prior_claims_to_current_corpus(prior_texts, evidence_rows)
        return matched[:cap]
    except Exception:  # noqa: BLE001 — read-only advisory; never abort the run
        return []
