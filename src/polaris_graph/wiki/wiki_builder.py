"""
Wiki Builder — converts evidence + outline into persistent wiki pages.

The wiki is the INTERMEDIATE ARTIFACT between raw evidence and the report.
Evidence is assigned to sections by embedding similarity (not front-to-back
allocation), eliminating the evidence starvation problem.

Each wiki page contains pre-cited claims: every claim already has its source
URL, direct quote, and global bibliography number. No late-binding citation
resolution needed.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

WIKI_BASE_DIR = Path(os.getenv("PG_WIKI_DIR", "wiki"))
OUTLINE_MAX_SECTIONS = int(os.getenv("PG_WIKI_MAX_SECTIONS", "10"))
MIN_SIMILARITY = float(os.getenv("PG_WIKI_MIN_SIMILARITY", "0.3"))
STARVATION_MIN_CLAIMS = int(os.getenv("PG_WIKI_STARVATION_MIN", "3"))
DEDUP_THRESHOLD = float(os.getenv("PG_WIKI_DEDUP_THRESHOLD", "0.85"))


@dataclass
class WikiResult:
    """Output of build_wiki(): everything the composer needs."""

    wiki_path: str
    section_claims: dict[str, list[dict]]
    bibliography: list[dict]
    stats: dict
    unassigned_evidence: list[dict] = field(default_factory=list)


async def generate_outline_for_wiki(
    client: Any,
    query: str,
    evidence: list[dict],
) -> list[dict]:
    """Generate a section outline from query + evidence when no outline exists in state.

    This is needed because the outline is normally generated inside synthesize_report(),
    which we're replacing. The wiki path needs an outline to assign evidence to sections.

    Returns a list of dicts with section_id, title, description.
    """
    # Build evidence summary for the LLM
    ev_statements = []
    for i, ev in enumerate(evidence[:50]):  # Cap at 50 for context window
        statement = ev.get("statement", "")
        tier = ev.get("quality_tier", "?")
        if statement:
            ev_statements.append(f"  {i+1}. [{tier}] {statement[:150]}")

    evidence_block = "\n".join(ev_statements)
    target_sections = min(OUTLINE_MAX_SECTIONS, max(5, len(evidence) // 5))

    prompt = (
        f"Create a {target_sections}-section outline for a systematic review answering:\n"
        f"\"{query}\"\n\n"
        f"Available evidence ({len(evidence)} pieces, showing top {min(50, len(evidence))}):\n"
        f"{evidence_block}\n\n"
        f"RULES:\n"
        f"1. Return ONLY a JSON array of objects: [{{\"section_id\": \"s01\", \"title\": \"...\", \"description\": \"...\"}}]\n"
        f"2. Include sections for: benefits, risks/safety, mechanisms, methodology, and comparisons\n"
        f"3. Each section must have a clear, specific title (not generic)\n"
        f"4. Descriptions should be 1-2 sentences explaining the section's focus\n"
        f"5. Order from general to specific: definition → findings → safety → methodology → implications\n"
        f"6. Do NOT include chain-of-thought or explanation — ONLY the JSON array\n"
    )

    try:
        result = await client.generate(
            prompt=prompt,
            system="You are a research outline planner. Return ONLY valid JSON.",
            max_tokens=2048,
            temperature=0.2,
            timeout=60,
        )

        import json as json_module
        content = result.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

        sections = json_module.loads(content)
        if isinstance(sections, list) and len(sections) >= 3:
            # Ensure section_ids
            for i, sec in enumerate(sections):
                if "section_id" not in sec:
                    sec["section_id"] = f"s{i+1:02d}"
                if "description" not in sec:
                    sec["description"] = sec.get("title", "")
            logger.info("[wiki] Generated outline: %d sections from LLM", len(sections))
            return sections

    except Exception as exc:
        logger.warning("[wiki] Outline generation failed: %s", str(exc)[:100])

    # Fallback: generate a standard outline without LLM
    logger.info("[wiki] Using fallback outline (8 standard sections)")
    return [
        {"section_id": "s01", "title": "Overview and Definitions", "description": f"Introduction to {query[:50]}"},
        {"section_id": "s02", "title": "Key Findings and Benefits", "description": "Primary positive outcomes from clinical evidence"},
        {"section_id": "s03", "title": "Mechanisms of Action", "description": "Biological and physiological mechanisms"},
        {"section_id": "s04", "title": "Comparative Analysis", "description": "Comparison with alternative approaches"},
        {"section_id": "s05", "title": "Safety Profile and Risks", "description": "Adverse effects, contraindications, and safety data"},
        {"section_id": "s06", "title": "Special Populations", "description": "Effects in specific demographic or clinical groups"},
        {"section_id": "s07", "title": "Research Quality and Limitations", "description": "Study design quality, evidence gaps, and methodological concerns"},
        {"section_id": "s08", "title": "Clinical Implications", "description": "Practical recommendations and future research directions"},
    ]


def build_wiki(
    evidence: list[dict],
    outline: list[dict],
    query: str,
    vector_id: str,
) -> WikiResult:
    """
    Build a persistent wiki from evidence and outline.

    1. Filter to GOLD + SILVER evidence
    2. Assign evidence to sections by embedding similarity
    3. Guard against starvation (fallback for thin sections)
    4. Dedup within sections
    5. Build global bibliography
    6. Write wiki files to disk
    7. Return WikiResult for composer
    """
    if not outline:
        logger.warning(
            "[wiki] No outline provided — this is expected on first synthesis. "
            "Outline will be generated by the wiki graph entry point."
        )

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Step 1: Quality filter ──────────────────────────────────────
    quality_evidence = [
        e for e in evidence
        if e.get("quality_tier") in ("GOLD", "SILVER")
    ]
    filtered_count = len(evidence) - len(quality_evidence)
    logger.info(
        "[wiki] Quality filter: %d → %d evidence (removed %d BRONZE/UNVERIFIED)",
        len(evidence), len(quality_evidence), filtered_count,
    )

    if not quality_evidence:
        logger.warning("[wiki] No GOLD/SILVER evidence — using all evidence as fallback")
        quality_evidence = list(evidence)

    if not quality_evidence:
        logger.error("[wiki] No evidence at all — cannot build wiki")
        return WikiResult(
            wiki_path="",
            section_claims={},
            bibliography=[],
            stats={"total_evidence": 0, "error": "no_evidence"},
        )

    # ── Step 2: Embedding-based assignment ──────────────────────────
    section_claims = _assign_evidence_by_embedding(quality_evidence, outline)

    # ── Step 3: Starvation guard ────────────────────────────────────
    assigned_ids = set()
    for claims in section_claims.values():
        for c in claims:
            assigned_ids.add(c.get("evidence_id"))

    unassigned = [
        e for e in quality_evidence
        if e.get("evidence_id") not in assigned_ids
    ]

    starved_sections = [
        sid for sid, claims in section_claims.items()
        if len(claims) < STARVATION_MIN_CLAIMS
    ]

    if starved_sections and unassigned:
        logger.info(
            "[wiki] Starvation guard: %d sections below %d claims, %d unassigned evidence",
            len(starved_sections), STARVATION_MIN_CLAIMS, len(unassigned),
        )
        _fill_starved_sections(
            section_claims, starved_sections, unassigned, outline,
        )

    # Second pass: steal from overfilled sections to fill empty ones.
    # This handles meta-sections like "Research Quality" or "Clinical Implications"
    # that don't match specific evidence but need claims to compose from.
    still_starved = [
        sid for sid, claims in section_claims.items()
        if len(claims) < STARVATION_MIN_CLAIMS
    ]
    if still_starved:
        # Find sections with the most claims (donors)
        overfilled = sorted(
            section_claims.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )

        for starved_sid in still_starved:
            need = STARVATION_MIN_CLAIMS - len(section_claims[starved_sid])
            donated = 0
            for donor_sid, donor_claims in overfilled:
                if donor_sid == starved_sid:
                    continue
                # Only steal if donor has more than fair share
                while (
                    len(section_claims[donor_sid]) > STARVATION_MIN_CLAIMS
                    and donated < need
                    and section_claims[donor_sid]
                ):
                    # Steal the LEAST relevant claim from the donor
                    worst_idx = min(
                        range(len(section_claims[donor_sid])),
                        key=lambda j: section_claims[donor_sid][j].get("relevance_score", 0),
                    )
                    stolen = section_claims[donor_sid].pop(worst_idx)
                    section_claims[starved_sid].append(stolen)
                    donated += 1

                if donated >= need:
                    break

            if donated:
                logger.info(
                    "[wiki] Starvation redistribution: donated %d claims to %s (from overfilled sections)",
                    donated, starved_sid,
                )

    # ── Step 4: Dedup within sections ───────────────────────────────
    total_deduped = 0
    for sid in section_claims:
        before = len(section_claims[sid])
        section_claims[sid] = _dedup_claims(section_claims[sid])
        total_deduped += before - len(section_claims[sid])

    if total_deduped:
        logger.info("[wiki] Dedup removed %d duplicate claims across sections", total_deduped)

    # ── Step 5: Build global bibliography ───────────────────────────
    bibliography = _build_bibliography(section_claims)

    # Attach bib numbers to each claim
    url_to_ref = {b["url"]: b["ref_num"] for b in bibliography}
    for claims in section_claims.values():
        for claim in claims:
            claim["ref_num"] = url_to_ref.get(claim.get("source_url", ""), 0)

    # ── Step 6: Write wiki to disk ──────────────────────────────────
    wiki_path = WIKI_BASE_DIR / vector_id
    _write_wiki_to_disk(
        wiki_path, section_claims, bibliography, outline, query, now_str,
    )

    # ── Step 7: Build stats and return ──────────────────────────────
    total_claims = sum(len(c) for c in section_claims.values())
    stats = {
        "total_evidence_input": len(evidence),
        "quality_filtered": len(quality_evidence),
        "total_claims_in_wiki": total_claims,
        "total_sources": len(bibliography),
        "sections_with_claims": sum(1 for c in section_claims.values() if c),
        "total_sections": len(outline),
        "deduped_count": total_deduped,
        "unassigned_count": len(unassigned),
        "starved_sections_fixed": len(starved_sections),
    }

    logger.info(
        "[wiki] Built wiki: %d claims across %d sections from %d sources → %s",
        total_claims, stats["sections_with_claims"], len(bibliography), wiki_path,
    )

    for sid, claims in section_claims.items():
        sec_title = _find_section_title(outline, sid)
        sources = len({c.get("source_url") for c in claims})
        logger.info("  %s: %d claims, %d sources — %s", sid, len(claims), sources, sec_title[:50])

    return WikiResult(
        wiki_path=str(wiki_path),
        section_claims=section_claims,
        bibliography=bibliography,
        stats=stats,
        unassigned_evidence=unassigned,
    )


# ── Evidence Assignment ─────────────────────────────────────────────


def _assign_evidence_by_embedding(
    evidence: list[dict],
    outline: list[dict],
) -> dict[str, list[dict]]:
    """Assign evidence to outline sections using embedding cosine similarity."""
    from src.utils.embedding_service import embed_texts

    section_claims: dict[str, list[dict]] = {
        s.get("section_id", f"s{i:02d}"): []
        for i, s in enumerate(outline)
    }

    if not evidence or not outline:
        return section_claims

    # Build texts for embedding
    evidence_texts = [
        f"{e.get('statement', '')} {e.get('direct_quote', '')[:200]}"
        for e in evidence
    ]
    section_texts = [
        f"{s.get('title', '')} {s.get('description', '')}"
        for s in outline
    ]

    # Embed everything in two batch calls
    try:
        evidence_embeddings = embed_texts(evidence_texts)
        section_embeddings = embed_texts(section_texts)
    except Exception as exc:
        logger.warning("[wiki] Embedding failed (%s) — falling back to keyword matching", exc)
        return _assign_evidence_by_keywords(evidence, outline)

    # Cosine similarity matrix: (num_evidence, num_sections)
    ev_matrix = np.array(evidence_embeddings)
    sec_matrix = np.array(section_embeddings)

    # Normalize
    ev_norms = np.linalg.norm(ev_matrix, axis=1, keepdims=True)
    sec_norms = np.linalg.norm(sec_matrix, axis=1, keepdims=True)
    ev_norms[ev_norms == 0] = 1.0
    sec_norms[sec_norms == 0] = 1.0
    ev_normed = ev_matrix / ev_norms
    sec_normed = sec_matrix / sec_norms

    similarity = ev_normed @ sec_normed.T  # (num_evidence, num_sections)

    section_ids = list(section_claims.keys())
    num_sections = len(section_ids)
    num_evidence = len(evidence)

    # Fair-share cap: prevent broad sections from absorbing everything
    fair_share = max(8, int(num_evidence / max(num_sections, 1) * 1.5))
    logger.info(
        "[wiki] Evidence assignment: %d evidence → %d sections (fair-share cap=%d)",
        num_evidence, num_sections, fair_share,
    )

    # Sort evidence by their best similarity score descending so high-confidence
    # assignments happen first (they're less likely to need redistribution)
    evidence_order = np.argsort(-np.max(similarity, axis=1))

    for i in evidence_order:
        ev = evidence[int(i)]
        # Try sections in order of similarity (best first)
        ranked_sections = np.argsort(similarity[int(i)])[::-1]

        assigned = False
        for sec_idx in ranked_sections:
            sec_idx = int(sec_idx)
            score = float(similarity[int(i), sec_idx])
            if score < MIN_SIMILARITY:
                break  # No more sections above threshold

            sid = section_ids[sec_idx]
            if len(section_claims[sid]) < fair_share:
                section_claims[sid].append(ev)
                assigned = True
                break

        # If all sections above threshold are full, assign to least-filled section
        # that has ANY similarity (>0.1) — prevents losing evidence entirely
        if not assigned:
            least_filled = sorted(
                range(num_sections),
                key=lambda idx: len(section_claims[section_ids[idx]]),
            )
            for sec_idx in least_filled:
                score = float(similarity[int(i), sec_idx])
                if score >= 0.1:
                    section_claims[section_ids[sec_idx]].append(ev)
                    assigned = True
                    break

    return section_claims


def _assign_evidence_by_keywords(
    evidence: list[dict],
    outline: list[dict],
) -> dict[str, list[dict]]:
    """Fallback: keyword overlap assignment (from Phase 0B)."""
    section_claims: dict[str, list[dict]] = {
        s.get("section_id", f"s{i:02d}"): []
        for i, s in enumerate(outline)
    }

    for ev in evidence:
        text = f"{ev.get('statement', '')} {ev.get('direct_quote', '')}".lower()
        ev_words = set(re.findall(r"\b[a-z]{4,}\b", text))

        scores = []
        for s in outline:
            sid = s.get("section_id", "")
            sec_text = f"{s.get('title', '')} {s.get('description', '')}".lower()
            sec_words = set(re.findall(r"\b[a-z]{4,}\b", sec_text))
            overlap = len(ev_words & sec_words)
            scores.append((sid, overlap))

        scores.sort(key=lambda x: x[1], reverse=True)
        for sid, score in scores[:2]:
            if score >= 2:
                section_claims[sid].append(ev)

    return section_claims


def _fill_starved_sections(
    section_claims: dict[str, list[dict]],
    starved_sids: list[str],
    unassigned: list[dict],
    outline: list[dict],
) -> None:
    """Fill sections with <STARVATION_MIN_CLAIMS from unassigned pool."""
    from src.utils.embedding_service import embed_texts

    if not unassigned:
        return

    unassigned_texts = [
        f"{e.get('statement', '')} {e.get('direct_quote', '')[:200]}"
        for e in unassigned
    ]

    try:
        un_embeddings = embed_texts(unassigned_texts)
    except Exception:
        return

    un_matrix = np.array(un_embeddings)
    un_norms = np.linalg.norm(un_matrix, axis=1, keepdims=True)
    un_norms[un_norms == 0] = 1.0
    un_normed = un_matrix / un_norms

    for sid in starved_sids:
        sec = next((s for s in outline if s.get("section_id") == sid), None)
        if not sec:
            continue

        sec_text = f"{sec.get('title', '')} {sec.get('description', '')}"
        try:
            sec_emb = np.array(embed_texts([sec_text])[0])
        except Exception:
            continue

        sec_norm = np.linalg.norm(sec_emb)
        if sec_norm == 0:
            continue
        sec_normed = sec_emb / sec_norm

        scores = un_normed @ sec_normed  # (num_unassigned,)
        top_indices = np.argsort(scores)[::-1]

        need = STARVATION_MIN_CLAIMS - len(section_claims[sid])
        added = 0
        for idx in top_indices:
            if added >= need:
                break
            if float(scores[idx]) >= 0.2:
                section_claims[sid].append(unassigned[int(idx)])
                added += 1

        if added:
            logger.info("[wiki] Starvation fix: added %d claims to %s", added, sid)


# ── Deduplication ────────────────────────────────────────────────────


def _dedup_claims(claims: list[dict]) -> list[dict]:
    """Remove near-duplicate claims within a section."""
    if len(claims) <= 1:
        return claims

    # Simple approach: same source URL + high statement similarity → dedup
    seen: list[dict] = []
    for claim in claims:
        is_dup = False
        for existing in seen:
            if (
                claim.get("source_url") == existing.get("source_url")
                and _text_similarity(
                    claim.get("statement", ""),
                    existing.get("statement", ""),
                ) > DEDUP_THRESHOLD
            ):
                is_dup = True
                break
        if not is_dup:
            seen.append(claim)

    return seen


def _text_similarity(a: str, b: str) -> float:
    """Quick Jaccard word similarity (no embeddings needed for dedup)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union else 0.0


# ── Bibliography ─────────────────────────────────────────────────────


def _build_bibliography(section_claims: dict[str, list[dict]]) -> list[dict]:
    """Build global bibliography from all claims, one entry per unique URL."""
    url_to_best: dict[str, dict] = {}
    url_to_evidence_ids: dict[str, list[str]] = {}

    for claims in section_claims.values():
        for claim in claims:
            url = claim.get("source_url", "")
            if not url:
                continue
            # Track all evidence IDs for this source
            eid = claim.get("evidence_id", "")
            if url not in url_to_evidence_ids:
                url_to_evidence_ids[url] = []
            if eid and eid not in url_to_evidence_ids[url]:
                url_to_evidence_ids[url].append(eid)
            # Track best evidence for metadata
            if url not in url_to_best:
                url_to_best[url] = claim
            elif claim.get("relevance_score", 0) > url_to_best[url].get("relevance_score", 0):
                url_to_best[url] = claim

    bibliography = []
    for i, (url, best) in enumerate(url_to_best.items(), 1):
        authors = best.get("authors", [])
        authors_str = ", ".join(authors[:3]) if authors else "Unknown"
        year = best.get("year", "n.d.")
        title = best.get("source_title", "Unknown")
        doi = best.get("doi", "")
        doi_str = f" DOI: {doi}" if doi else ""

        bibliography.append({
            "ref_num": i,
            "citation_number": i,
            "url": url,
            "title": title,
            "authors": authors,
            "year": year,
            "doi": doi,
            "source_type": best.get("source_type", "web"),
            "evidence_ids": url_to_evidence_ids.get(url, []),
            # formatted field expected by downstream consumers
            "formatted": f"{authors_str} ({year}). {title[:100]}.{doi_str} {url}",
        })

    return bibliography


# ── Disk I/O ─────────────────────────────────────────────────────────


def _write_wiki_to_disk(
    wiki_path: Path,
    section_claims: dict[str, list[dict]],
    bibliography: list[dict],
    outline: list[dict],
    query: str,
    now_str: str,
) -> None:
    """Write wiki markdown files to disk."""
    wiki_path.mkdir(parents=True, exist_ok=True)
    topics_dir = wiki_path / "topics"
    topics_dir.mkdir(exist_ok=True)

    # ── index.md ────────────────────────────────────────────────
    total_claims = sum(len(c) for c in section_claims.values())
    index_lines = [
        f"# Wiki Index",
        f"",
        f"> Query: {query}",
        f"> Built: {now_str}",
        f"> Total claims: {total_claims} | Sources: {len(bibliography)}",
        f"",
        f"## Sections",
        f"",
    ]

    for sec in outline:
        sid = sec.get("section_id", "")
        title = sec.get("title", "Unknown")
        slug = _slugify(title)
        claims = section_claims.get(sid, [])
        sources = len({c.get("source_url") for c in claims})
        index_lines.append(f"- [{title}](topics/{slug}.md) — {len(claims)} claims, {sources} sources")

    (wiki_path / "index.md").write_text("\n".join(index_lines), encoding="utf-8")

    # ── topics/*.md ─────────────────────────────────────────────
    for sec in outline:
        sid = sec.get("section_id", "")
        title = sec.get("title", "Unknown")
        slug = _slugify(title)
        claims = section_claims.get(sid, [])

        lines = [
            f"---",
            f"title: \"{title}\"",
            f"section_id: {sid}",
            f"claim_count: {len(claims)}",
            f"source_count: {len({c.get('source_url') for c in claims})}",
            f"created: {now_str}",
            f"---",
            f"",
            f"# {title}",
            f"",
        ]

        for j, claim in enumerate(claims, 1):
            ref_num = claim.get("ref_num", 0)
            lines.append(f"### Claim {j}")
            lines.append(f"- **Statement**: {claim.get('statement', '')} [REF:{ref_num}]")
            quote = claim.get("direct_quote", "")
            if quote:
                lines.append(f"- **Quote**: \"{quote[:250]}\"")
            lines.append(f"- **Source**: [{claim.get('source_title', 'Unknown')[:80]}]({claim.get('source_url', '')})")
            lines.append(f"- **Tier**: {claim.get('quality_tier', '?')} | Relevance: {claim.get('relevance_score', 0):.2f}")
            lines.append("")

        (topics_dir / f"{slug}.md").write_text("\n".join(lines), encoding="utf-8")

    # ── bibliography.md ─────────────────────────────────────────
    bib_lines = ["# Bibliography", ""]
    for b in bibliography:
        authors = ", ".join(b.get("authors", [])[:3]) if b.get("authors") else "Unknown"
        year = b.get("year", "n.d.")
        doi_str = f" DOI: {b['doi']}" if b.get("doi") else ""
        bib_lines.append(f"[{b['ref_num']}] {authors} ({year}). {b['title'][:100]}.{doi_str}")
        bib_lines.append(f"    URL: {b['url']}")
        bib_lines.append("")

    (wiki_path / "bibliography.md").write_text("\n".join(bib_lines), encoding="utf-8")

    # ── log.md ──────────────────────────────────────────────────
    log_lines = [
        f"# Wiki Log",
        f"",
        f"## [{now_str}] create | Wiki built",
        f"- Query: {query}",
        f"- Evidence: {total_claims} claims from {len(bibliography)} sources",
        f"- Sections: {sum(1 for c in section_claims.values() if c)}/{len(outline)}",
        f"",
    ]

    (wiki_path / "log.md").write_text("\n".join(log_lines), encoding="utf-8")


# ── Helpers ──────────────────────────────────────────────────────────


def _slugify(title: str) -> str:
    """Convert section title to filename slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return slug[:60]


def _find_section_title(outline: list[dict], section_id: str) -> str:
    """Find section title by ID."""
    for s in outline:
        if s.get("section_id") == section_id:
            return s.get("title", "Unknown")
    return "Unknown"
