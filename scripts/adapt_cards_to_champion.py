#!/usr/bin/env python3
"""Adapter: our richer evidence cards -> champion cp4 corpus schema.

Takes the flywheel curated cards (flat list of 838 cards / 285 works) and emits a corpus in the
EXACT runtime schema the champion driver (scripts/compose_agentic_report_s3gear329.py) consumes:

    {"research_question": str, "domain": str,
     "evidence": [ {evidence_id, tier, title, statement, direct_quote, journal, authors, doi,
                    pmid, source_url, provenance_class, year, ...}, ... ],
     "finding_clusters": [ {representative_index, member_indices, corroboration_count,
                            member_hosts, claim_group_id}, ... ],   # indices INTO ``evidence``
     "same_work_groups": [ {same_work_id, canonical_index, member_evidence_ids, member_urls}, ... ],
     "basket_total": int}

Design decisions (documented so the comparison is honest):
  * evidence_id: ev_NNNN by position (matches champion 'ev_' convention, guaranteed unique).
  * title: our cards carry NO real paper title anywhere (neither curated nor the 5691-card mine);
    the best human-readable source label available is ``attribution`` = "Author (year), Venue".
  * source_url: derived from the DOI (https://doi.org/<doi>) since cards carry no url.
  * tier: DETERMINISTIC venue-quality heuristic (T1 top-venue / T2 recognized-strong / T3 default
    peer-reviewed-journal-with-doi / T4 missing-authors-or-review). Tier is only consumed as a
    descriptive tier-profile line in the writer prompt (multi_section_generator: tier_fractions
    -> "T1=..%"); it does NOT filter or weight evidence, so no coverage is lost regardless.
  * finding_clusters: ONE basket per card (the cards are already deduped/curated). corroboration_count
    from n_sources. This is the faithful analog of the champion's claim-level baskets and lets
    PG_ROUTE_ALL_BASKETS surface every card.
  * same_work_groups: cards sharing a work_id are folded (canonical_index = first, member_evidence_ids
    = all) so same-paper cards do not over-corroborate — mirrors the champion's same-work fold.

Every card is kept; all 285 works are preserved.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

# Recognized strong venues for a light, deterministic tier spread (NOT task-specific content).
_T1_VENUES = {
    "proceedings of the national academy of sciences", "nature", "science",
    "quarterly journal of economics", "american economic review", "econometrica",
    "journal of political economy", "the review of economic studies", "nature human behaviour",
}
_T2_VENUE_HINTS = (
    "economic", "econom", "management science", "information systems", "review",
    "national bureau", "nber", "labour economics", "labor economics",
)


def _tier_for(card: dict) -> str:
    venue = (card.get("venue") or "").strip().lower()
    authors = card.get("authors") or []
    method = (card.get("method") or "").strip().lower()
    if venue in _T1_VENUES:
        return "T1"
    if not authors:
        return "T4"
    if method == "review":
        return "T4"
    if any(h in venue for h in _T2_VENUE_HINTS):
        return "T2"
    if card.get("doi"):
        return "T3"
    return "T5"


def _host_from_doi(doi: str) -> str:
    if not doi:
        return ""
    try:
        return urlparse(f"https://doi.org/{doi}").netloc or "doi.org"
    except Exception:  # noqa: BLE001
        return "doi.org"


def adapt(cards: list[dict], research_question: str, domain: str) -> dict:
    evidence: list[dict] = []
    work_to_indices: dict[str, list[int]] = defaultdict(list)

    for i, c in enumerate(cards):
        ev_id = f"ev_{i:04d}"
        doi = (c.get("doi") or "").strip()
        authors = c.get("authors") or []
        year = c.get("year")
        try:
            year = int(year) if year not in (None, "") else None
        except (TypeError, ValueError):
            year = None
        title = (c.get("attribution") or c.get("venue") or "").strip()
        source_url = f"https://doi.org/{doi}" if doi else ""
        row = {
            "evidence_id": ev_id,
            "statement": c.get("claim") or "",
            "direct_quote": c.get("span") or "",
            "title": title,
            "source_title": title,
            "journal": c.get("venue") or "",
            "authors": list(authors),
            "doi": doi,
            "pmid": "",
            "source_url": source_url,
            "provenance_class": None,
            "tier": _tier_for(c),
            "year": year,
            "publication_year": year,
            # provenance breadcrumb back to the source card (non-consumed, aids debugging)
            "_src_card_id": c.get("id"),
            "_work_id": c.get("work_id"),
        }
        evidence.append(row)
        wid = c.get("work_id") or f"__nowork_{i}"
        work_to_indices[wid].append(i)

    # finding_clusters: one basket per card (cards are pre-deduped/curated).
    finding_clusters = []
    for i, c in enumerate(cards):
        corro = c.get("n_sources") or c.get("n_evidence_units") or 1
        try:
            corro = max(1, int(corro))
        except (TypeError, ValueError):
            corro = 1
        finding_clusters.append({
            "representative_index": i,
            "member_indices": [i],
            "corroboration_count": corro,
            "member_hosts": [_host_from_doi((c.get("doi") or "").strip())],
            "claim_group_id": f"cg_{i:04d}",
        })

    # same_work_groups: fold cards that share a work_id (only groups with >1 member matter).
    same_work_groups = []
    for wid, idxs in work_to_indices.items():
        if len(idxs) < 2 or wid.startswith("__nowork_"):
            continue
        member_ids = [evidence[j]["evidence_id"] for j in idxs]
        urls = sorted({evidence[j]["source_url"] for j in idxs if evidence[j]["source_url"]})
        same_work_groups.append({
            "same_work_id": wid,
            "canonical_index": idxs[0],
            "member_evidence_ids": member_ids,
            "member_urls": urls,
        })

    return {
        "research_question": research_question,
        "domain": domain,
        "evidence": evidence,
        "finding_clusters": finding_clusters,
        "same_work_groups": same_work_groups,
        "basket_total": len(finding_clusters),
        "_provenance": {
            "adapter": "scripts/adapt_cards_to_champion.py",
            "n_cards": len(cards),
            "n_works": len({c.get("work_id") for c in cards}),
            "tier_dist": dict(Counter(r["tier"] for r in evidence)),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards",
                    default="/home/polaris/wt/flywheel/outputs/compose_inputs/task72_cards_curated.json")
    ap.add_argument("--ref-corpus", default=str(ROOT / "data" / "cp4_corpus_s3gear_329.corrected.json"),
                    help="champion corpus to copy research_question/domain from")
    ap.add_argument("--out", default=str(ROOT / "data" / "cp4_corpus_from_newcards.json"))
    args = ap.parse_args()

    cards = json.loads(Path(args.cards).read_text())
    if not isinstance(cards, list):
        raise SystemExit(f"expected a list of cards, got {type(cards)}")
    ref = json.loads(Path(args.ref_corpus).read_text())

    corpus = adapt(cards, research_question=ref["research_question"],
                   domain=ref.get("domain", "workforce"))
    Path(args.out).write_text(json.dumps(corpus, ensure_ascii=False, indent=1))

    p = corpus["_provenance"]
    print(f"wrote {args.out}")
    print(f"  evidence          : {len(corpus['evidence'])}")
    print(f"  works preserved   : {p['n_works']}")
    print(f"  finding_clusters  : {len(corpus['finding_clusters'])}")
    print(f"  same_work_groups  : {len(corpus['same_work_groups'])}")
    print(f"  tier_dist         : {p['tier_dist']}")
    print(f"  domain            : {corpus['domain']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
