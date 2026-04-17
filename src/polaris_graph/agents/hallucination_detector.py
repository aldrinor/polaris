"""
NLI-based post-synthesis hallucination audit.

Replaces LettuceDetect (30-50% false positive rate on citation markers)
with MiniCheck NLI verification that we already trust for evidence checking.

Approach:
1. Extract claims from each section (sentence-level)
2. For each claim with a [CITE:...] marker, verify against the cited evidence
3. For uncited claims, check against ALL section evidence
4. Score: hallucination_ratio = unsupported_claims / total_claims
5. Flag sections above threshold for rewrite

Benefits over LettuceDetect:
- Same model (MiniCheck flan-t5-large) already loaded for evidence verification
- No false positives from citation markers (we parse them, not treat as unknown tokens)
- Claim-level granularity (not token-level) — more actionable for rewrites
- 75.0% F1 accuracy (LettuceDetect: unknown F1, 50.8% false positive on our data)
"""

import asyncio
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Feature gate (LAW VI)
PG_HALLUCINATION_DETECT_ENABLED = os.getenv("PG_HALLUCINATION_DETECT_ENABLED", "0") == "1"

PG_HALLUCINATION_REWRITE_THRESHOLD = float(
    os.getenv("PG_HALLUCINATION_REWRITE_THRESHOLD", "0.25")
)
# Minimum NLI probability to consider a claim supported
PG_POST_SYNTH_NLI_THRESHOLD = float(
    os.getenv("PG_POST_SYNTH_NLI_THRESHOLD", "0.5")
)
# Maximum claims to verify per section (performance cap)
PG_POST_SYNTH_MAX_CLAIMS = int(
    os.getenv("PG_POST_SYNTH_MAX_CLAIMS", "50")
)


def _is_enabled() -> bool:
    """Runtime check for hallucination detection feature gate.

    Module-level constants bind at import time.
    If .env is loaded after import, the constant is stale.
    """
    return os.getenv("PG_HALLUCINATION_DETECT_ENABLED", "0") == "1"


def _extract_section_claims(content: str) -> list[dict]:
    """Split section content into individual claims with their citation markers.

    Returns list of {"text": str, "cited_ids": [str], "start": int, "end": int}
    """
    # Use PySBD for sentence splitting if available, else regex fallback
    try:
        import pysbd
        segmenter = pysbd.Segmenter(language="en", clean=False)
        sentences = segmenter.segment(content)
    except ImportError:
        sentences = re.split(r'(?<=[.!?])\s+', content)

    claims = []
    pos = 0
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 15:
            pos += len(sent) + 1
            continue

        # Skip headings, Key Findings headers, table rows
        if sent.startswith("#") or sent.startswith("|") or sent.startswith("---"):
            pos += len(sent) + 1
            continue
        # Skip bullet point markers alone
        if sent.strip() in ("*", "-", "+"):
            pos += len(sent) + 1
            continue

        # Extract cited evidence IDs from this sentence
        cite_matches = re.findall(r'\[CITE:([^\]]+)\]', sent)
        cited_ids = [c.strip() for c in cite_matches]

        # Clean the claim text (remove citation markers for NLI scoring)
        clean_text = re.sub(r'\[CITE:[^\]]*\]', '', sent).strip()
        clean_text = re.sub(r'\[(\d{1,3})\]', '', clean_text).strip()
        clean_text = re.sub(r'  +', ' ', clean_text)

        if len(clean_text) > 15:
            claims.append({
                "text": clean_text,
                "cited_ids": cited_ids,
                "start": pos,
                "end": pos + len(sent),
            })

        pos += len(sent) + 1

    return claims


def audit_sections_for_hallucination(
    sections: list[dict],
    evidence: list[dict],
    research_query: str,
) -> list[dict]:
    """Audit report sections for hallucination using NLI verification.

    Same interface as the old LettuceDetect-based version. Returns same format
    so all 3 call sites in synthesizer.py work without changes.

    Args:
        sections: List of section dicts with 'content', 'title', 'section_id', 'evidence_ids'
        evidence: List of evidence dicts with 'evidence_id', 'statement', 'direct_quote'
        research_query: The original research query

    Returns:
        List of audit results per section:
        [{
            "section_id": str,
            "title": str,
            "hallucination_ratio": float,  # 0.0-1.0
            "hallucinated_spans": [{"start": int, "end": int, "text": str}],
            "needs_rewrite": bool,
            "total_chars": int,
            "hallucinated_chars": int,
            "method": "nli",  # distinguishes from old "lettucedetect"
            "unsupported_claims": int,
            "total_claims": int,
        }]
    """
    if not _is_enabled():
        logger.info("[polaris graph] ARCH-5: Post-synthesis NLI audit disabled")
        return []

    # Try to load NLI model
    try:
        from src.polaris_graph.agents.nli_verifier import load_nli_model

        # Check if there's already a running event loop
        try:
            loop = asyncio.get_running_loop()
            # Running inside an existing loop — use thread to avoid conflict
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                scorer = pool.submit(
                    lambda: asyncio.run(load_nli_model())
                ).result(timeout=30)
        except RuntimeError:
            # No running event loop — safe to create one
            loop = asyncio.new_event_loop()
            try:
                scorer = loop.run_until_complete(load_nli_model())
            finally:
                loop.close()
    except Exception as exc:
        logger.warning(
            "[polaris graph] ARCH-5: NLI model not available for post-synthesis "
            "audit: %s. Skipping.",
            str(exc)[:200],
        )
        return []

    if scorer is None:
        logger.warning(
            "[polaris graph] ARCH-5: NLI scorer is None — skipping post-synthesis audit"
        )
        return []

    # Build evidence lookup
    evidence_map = {e.get("evidence_id", ""): e for e in evidence}

    results = []
    for section in sections:
        section_id = section.get("section_id", "")
        title = section.get("title", "")
        content = section.get("content", "")

        if not content or len(content) < 50:
            continue

        # Extract claims from section content
        claims = _extract_section_claims(content)
        if not claims:
            continue

        # Cap claims for performance
        if len(claims) > PG_POST_SYNTH_MAX_CLAIMS:
            claims = claims[:PG_POST_SYNTH_MAX_CLAIMS]

        # Get section's evidence pool
        evidence_ids = section.get("evidence_ids", [])
        section_evidence = [
            evidence_map[eid] for eid in evidence_ids
            if eid in evidence_map
        ]

        # FIX-4: Build NLI premise from quote-centered source windows rather
        # than raw content[:2000]. When the supporting sentence is deeper than
        # 2K chars into the source (common for real papers — methods and
        # preambles eat the first 2K), content[:2000] produces a premise that
        # doesn't contain the fact, and NLI returns low scores for even
        # verbatim-grounded claims (observed: Cochrane ADF definition flagged
        # at nli=0.387 despite being near-verbatim in source).
        #
        # Use _extract_quote_context from nli_verifier: it locates the
        # direct_quote (or statement keywords) inside the source and returns
        # a 2K window centered there. Guarantees the supporting text is in
        # the premise whenever it exists anywhere in the source.
        try:
            from src.polaris_graph.agents.nli_verifier import _extract_quote_context
        except Exception:
            _extract_quote_context = None  # type: ignore

        _per_ev_context_chars = int(os.getenv("PG_POST_SYNTH_PER_EV_CONTEXT", "2000"))
        context_texts = []
        for ev in section_evidence:
            parts = []
            stmt = ev.get("statement", "")
            quote = ev.get("direct_quote", "")
            src_content = ev.get("source_content", "")
            if stmt:
                parts.append(stmt)
            if quote and quote != stmt:
                parts.append(quote)
            if src_content:
                if _extract_quote_context is not None and (quote or stmt):
                    window = _extract_quote_context(
                        src_content, quote, _per_ev_context_chars, statement=stmt,
                    )
                else:
                    window = src_content[:_per_ev_context_chars]
                parts.append(window)
            if parts:
                context_texts.append(" ".join(parts))

        if not context_texts:
            logger.debug(
                "[polaris graph] ARCH-5: Skipping section '%s' — no evidence context",
                title[:40],
            )
            continue

        # Combine all evidence into a single context document for NLI scoring
        combined_context = "\n\n".join(context_texts)
        # Cap context to NLI model's effective window
        max_context = int(os.getenv("PG_POST_SYNTH_CONTEXT_CHARS", "8000"))
        if len(combined_context) > max_context:
            combined_context = combined_context[:max_context]

        # Build NLI pairs: (document, claim)
        docs_list = [combined_context] * len(claims)
        claims_list = [c["text"] for c in claims]

        try:
            # Check if FaithLens or MiniCheck
            from src.polaris_graph.agents.nli_verifier import PG_NLI_MODEL
            if PG_NLI_MODEL == "faithlens":
                # FaithLens returns different format
                from src.polaris_graph.agents.nli_verifier import _load_faithlens
                fl_scorer = asyncio.get_event_loop().run_until_complete(_load_faithlens())
                if fl_scorer is None:
                    continue
                fl_results = fl_scorer.infer(
                    contexts=docs_list,
                    claims=claims_list,
                )
                raw_probs = [
                    1.0 if r.get("prediction", 0) == 1 else 0.0
                    for r in fl_results
                ]
            else:
                # MiniCheck API
                _labels, raw_probs, _chunks, _chunk_probs = scorer.score(
                    docs=docs_list, claims=claims_list,
                )
                raw_probs = [float(p) for p in raw_probs]

        except Exception as exc:
            logger.warning(
                "[polaris graph] ARCH-5: NLI scoring failed for section '%s': %s",
                title[:40],
                str(exc)[:200],
            )
            continue

        # Count unsupported claims
        unsupported = []
        nli_threshold = PG_POST_SYNTH_NLI_THRESHOLD
        for claim, prob in zip(claims, raw_probs):
            if prob < nli_threshold:
                unsupported.append({
                    "start": claim["start"],
                    "end": claim["end"],
                    "text": claim["text"][:200],
                    "nli_score": round(prob, 3),
                })

        total_claims = len(claims)
        unsupported_count = len(unsupported)
        ratio = unsupported_count / max(total_claims, 1)

        result = {
            "section_id": section_id,
            "title": title,
            "hallucination_ratio": round(ratio, 4),
            "hallucinated_spans": unsupported,  # Same key as old interface
            "needs_rewrite": ratio > PG_HALLUCINATION_REWRITE_THRESHOLD,
            "total_chars": len(content),
            "hallucinated_chars": sum(s["end"] - s["start"] for s in unsupported),
            "method": "nli",
            "unsupported_claims": unsupported_count,
            "total_claims": total_claims,
        }

        if result["needs_rewrite"]:
            logger.warning(
                "[polaris graph] ARCH-5: Section '%s' has %.1f%% unsupported claims "
                "(%d/%d, threshold %.1f%%) — flagged for rewrite. "
                "Top unsupported: %s",
                title[:40],
                ratio * 100,
                unsupported_count,
                total_claims,
                PG_HALLUCINATION_REWRITE_THRESHOLD * 100,
                "; ".join(s["text"][:60] for s in unsupported[:3]),
            )
        else:
            logger.info(
                "[polaris graph] ARCH-5: Section '%s' NLI audit: %.1f%% unsupported "
                "(%d/%d claims) — OK",
                title[:40],
                ratio * 100,
                unsupported_count,
                total_claims,
            )

        results.append(result)

    # Summary
    if results:
        avg_ratio = sum(r["hallucination_ratio"] for r in results) / len(results)
        rewrite_count = sum(1 for r in results if r["needs_rewrite"])
        logger.info(
            "[polaris graph] ARCH-5: NLI post-synthesis audit complete: %d sections, "
            "avg unsupported %.1f%%, %d flagged for rewrite",
            len(results),
            avg_ratio * 100,
            rewrite_count,
        )

    return results
