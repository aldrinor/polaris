#!/usr/bin/env python3
"""Build the LABELED ground-truth fixture for the quality_weight bake-off (I-ret-002 #1294, §4).

Output: clinical_quality_weight_fixture.jsonl — one row per source drawn from the banked
corpus_snapshot.json bodies, each carrying the post-extraction body text + an OBJECTIVE,
pre-registered quality label.

WHAT THE FIXTURE TESTS (brief §4): does a learned content-quality classifier RANK authoritative
clinical sources above on-topic-SEO/shallow sources, WITHIN the same topic AND within the same
source-type? AUC is computed over (topic_id x source_type) cells (gate0.paired_within_cell_auc),
so the score measures QUALITY separation, never a topic or source-type prior (§-1.1 proxy).

LABEL INTEGRITY (the Codex iter-1 P1 — do NOT soften):
  * The SCORED label is set by a PRE-REGISTERED OBJECTIVE rubric on VERIFIABLE signals
    (peer-reviewed venue / gov-agency / guideline-body domain identity vs known SEO-spam /
    social / content-farm domain) — NOT "reads high-quality", NOT POLARIS tier metadata.
  * This deterministic rubric is FAMILY-A and it PROPOSES rows only. Per row we record:
        rubric_label        — the objective-rubric proposal (family A, deterministic here)
        family_a_label      — = rubric_label (the Claude-family proposal)
        family_b_label      — None until Codex family adjudication is wired (out-of-band)
        operator_spotcheck  — None until the operator stratified spot-check is done
        label_status        — "proposed" until two-family + spot-check => "adjudicated"
        scored_label        — None while proposed; set ONLY when label_status == "adjudicated"
  * run_bakeoff.py scores ONLY rows with label_status == "adjudicated" (it fails loud / flags
    provisional otherwise) — a rubric proposal is NEVER silently used as the scored label.
  * The labels are INDEPENDENT of all candidate classifiers AND of tier_classifier /
    authority_model (no circularity, the drb_72 fake-real-number trap).

This script is fully OFFLINE and deterministic: the family-A objective-rubric PROPOSAL is doable
now from the banked snapshots; the family-B (Codex) adjudication + operator spot-check are
out-of-band and reported as an honest blocker (label_status stays "proposed").

LABEL_SETS reuse (the named seam): scripts/relevance_scorer_bakeoff.py LABEL_SETS is reused ONLY
to confirm a body is ON-TOPIC for its question (both classes must be on-topic — a "good clinical
vs random junk" fixture would measure topic relevance, the reranker layer's job). It is NEVER
used to set the QUALITY label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from urllib.parse import urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
# repo root = .../scripts/dr_benchmark/retrieval_bakeoff/quality_weight -> up 4
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Reuse the named LABEL_SETS seam for ON-TOPIC confirmation only (never for the quality label).
try:
    from scripts.relevance_scorer_bakeoff import LABEL_SETS, label_rows
except Exception:  # pragma: no cover - import-time guard so smoke can stub it
    LABEL_SETS = {}
    label_rows = None  # type: ignore

DEFAULT_SNAPSHOT_ROOT = os.path.join("outputs", "corpus_backups", "extracted")
DEFAULT_SLUGS = [
    "drb_75_metal_ions_cvd",
    "drb_76_gut_microbiota_crc",
    "drb_78_parkinsons_dbs",
    "drb_72_ai_labor",
]
DEFAULT_OUT = os.path.join(_HERE, "clinical_quality_weight_fixture.jsonl")

# Minimum post-extraction body length to enter the fixture (a too-short body is a fetch stub, a
# separate layer's concern — here we want real bodies both classes can be scored on). Named
# constant (LAW VI), not a hidden magic number.
MIN_BODY_CHARS = 300

# ---------------------------------------------------------------------------
# PRE-REGISTERED OBJECTIVE QUALITY RUBRIC (locked before execution).
# Label = 1 (AUTHORITATIVE) / 0 (on-topic-SPAM/shallow) / None (UNDECIDABLE -> excluded from
# the proposal so a guess never enters the fixture). Signals are VERIFIABLE DOMAIN IDENTITY +
# document-identity markers (DOI / PMID presence, peer-reviewed publisher, gov agency, guideline
# body) vs known SEO-spam / social / content-farm / UGC hosts. This is NOT "reads high-quality"
# and NOT POLARIS tier — it is registered-domain + document-id identity an auditor can re-check.
# ---------------------------------------------------------------------------
# Authoritative registered domains: peer-reviewed publishers, indexers, gov agencies, guideline
# bodies, regulator labels. Matched on the registered domain (suffix-aware), document-id-tied.
AUTHORITATIVE_DOMAINS = {
    # peer-reviewed publishers / indexers
    "pmc.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "europepmc.org",
    "nature.com", "sciencedirect.com", "link.springer.com", "onlinelibrary.wiley.com",
    "academic.oup.com", "bmj.com", "bmjopen.bmj.com", "thelancet.com", "jamanetwork.com",
    "nejm.org", "cell.com", "frontiersin.org", "mdpi.com", "plos.org", "journals.plos.org",
    "tandfonline.com", "sagepub.com", "journals.sagepub.com", "cambridge.org", "karger.com",
    "ahajournals.org", "diabetesjournals.org", "aeaweb.org", "pubs.aeaweb.org",
    "journals.uchicago.edu", "jmir.org",
    # gov agencies / regulators / guideline bodies
    "accessdata.fda.gov", "fda.gov", "ema.europa.eu", "europa.eu", "efsa.europa.eu",
    "canada.ca", "gc.ca", "nih.gov", "cdc.gov", "who.int", "nice.org.uk", "cochranelibrary.com",
    "cochrane.org", "clinicaltrials.gov", "gov.uk",
}
# DOI resolver — authoritative ONLY when the body/source carries a real DOI/PMID (document
# identity), since doi.org resolves to many publishers. Handled specially below.
DOI_HOSTS = {"doi.org", "dx.doi.org"}

# Known SEO-spam / social / UGC / content-farm hosts: on-topic but NOT authoritative sources.
# These are public UGC / video / social / Q&A / content-aggregator hosts — verifiable identity,
# not a quality read.
SPAM_OR_UGC_DOMAINS = {
    "youtube.com", "m.youtube.com", "youtu.be", "facebook.com", "m.facebook.com",
    "twitter.com", "x.com", "reddit.com", "old.reddit.com", "quora.com", "medium.com",
    "linkedin.com", "pinterest.com", "tiktok.com", "instagram.com", "blogspot.com",
    "wordpress.com", "substack.com", "slideshare.net", "scribd.com", "academia.edu",
    "researchgate.net",  # UGC author-upload aggregator: on-topic but not the source of record
    "wikipedia.org",     # tertiary; on-topic but not a primary authoritative clinical source
    "healthline.com", "webmd.com", "verywellhealth.com", "medicalnewstoday.com",
}


def _registered_domain(host: str) -> str:
    """Return a registered-domain-ish key (last two labels, suffix-aware for common 2-part TLDs)."""
    host = (host or "").lower().lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    two_part_tlds = {"co.uk", "org.uk", "gov.uk", "ac.uk", "com.au", "gov.au", "co.jp"}
    last2 = ".".join(parts[-2:])
    if last2 in two_part_tlds:
        return ".".join(parts[-3:])
    return last2


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _domain_matches(host: str, domain_set: set[str]) -> bool:
    """True if host == d or host endswith .d for any d in the set."""
    host = (host or "").lower().lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    for d in domain_set:
        if host == d or host.endswith("." + d):
            return True
    return False


def _source_type(host: str) -> str:
    """Coarse source-type bucket for WITHIN-source-type pairing. Identity-based (verifiable
    registered domain), NOT a quality read. Used to form (topic x source_type) cells so the AUC
    cannot be inflated by a 'journal beats youtube' source-type prior."""
    if _domain_matches(host, DOI_HOSTS):
        return "doi_resolver"
    if _domain_matches(host, {"youtube.com", "youtu.be", "facebook.com", "twitter.com", "x.com",
                              "reddit.com", "tiktok.com", "instagram.com", "linkedin.com"}):
        return "social_video"
    if _domain_matches(host, {"medium.com", "substack.com", "blogspot.com", "wordpress.com",
                              "quora.com", "researchgate.net", "academia.edu", "slideshare.net",
                              "scribd.com"}):
        return "ugc_aggregator"
    if _domain_matches(host, {"healthline.com", "webmd.com", "verywellhealth.com",
                              "medicalnewstoday.com", "wikipedia.org"}):
        return "consumer_health"
    # Peer-reviewed article HOSTS that sit under a .gov/.nih.gov suffix (PubMed Central, NCBI,
    # PubMed) are article indexers, NOT regulators — match them BEFORE the broad gov_regulator
    # set so a `*.nih.gov` PMC article is not mis-bucketed as a regulator. (source_type is an
    # identity bucket for within-source-type pairing, never a quality read.)
    if _domain_matches(host, {"pmc.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
                              "pubmed.ncbi.nlm.nih.gov", "europepmc.org"}):
        return "peer_reviewed_publisher"
    if _domain_matches(host, {"fda.gov", "accessdata.fda.gov", "ema.europa.eu", "europa.eu",
                              "canada.ca", "gc.ca", "nih.gov", "cdc.gov", "who.int",
                              "clinicaltrials.gov", "nice.org.uk", "gov.uk"}):
        return "gov_regulator"
    if _domain_matches(host, AUTHORITATIVE_DOMAINS):
        return "peer_reviewed_publisher"
    return "other_web"


def objective_rubric_label(*, url: str, doi: str | None, pmid: str | None) -> tuple[int | None, str]:
    """PRE-REGISTERED objective rubric. Returns (label, reason).

    label = 1 authoritative iff (a) the registered domain is a peer-reviewed publisher / gov /
    guideline body, OR (b) the source carries a real DOI or PMID (document-of-record identity)
    AND is not a known UGC/social host. label = 0 iff the host is a known SEO-spam / social /
    UGC / consumer-health-farm domain. label = None (UNDECIDABLE -> excluded) otherwise — we
    NEVER guess a label into the fixture.
    """
    host = _host(url)
    has_doc_id = bool((doi or "").strip()) or bool((pmid or "").strip())

    if _domain_matches(host, SPAM_OR_UGC_DOMAINS):
        return 0, f"known_ugc_or_spam_domain:{_registered_domain(host)}"
    if _domain_matches(host, AUTHORITATIVE_DOMAINS):
        return 1, f"authoritative_domain:{_registered_domain(host)}"
    if _domain_matches(host, DOI_HOSTS) and has_doc_id:
        return 1, "doi_resolver_with_document_id"
    if has_doc_id:
        # carries a DOI/PMID but on an unlisted host: document-of-record identity present, not
        # a known UGC host -> authoritative by document identity (verifiable, auditable).
        return 1, "carries_doi_or_pmid_document_id"
    return None, f"undecidable_unlisted_domain:{_registered_domain(host)}"


def _body_text(ev: dict) -> str:
    """Post-extraction body span for a source. The banked snapshot stores the cleaned body as
    `direct_quote` (verified: up to 25000 chars, the post-extraction/clean_fetch_body output)."""
    return (ev.get("direct_quote") or "").strip()


def _on_topic_ids(rows: list[dict], slug: str) -> set[str]:
    """Evidence ids confirmed ON-TOPIC for the question via the reused LABEL_SETS seam (POS side
    only — clearly on-topic). Both fixture classes must be on-topic; off-topic rows are dropped
    so we measure quality, not topic."""
    if not LABEL_SETS or label_rows is None or slug not in LABEL_SETS:
        # seam unavailable: keep all rows (the rubric still labels quality); flagged in manifest.
        return {ev.get("evidence_id") for ev in rows if ev.get("evidence_id")}
    pos, _neg = label_rows(rows, LABEL_SETS[slug])
    return {ev.get("evidence_id") for ev in pos if ev.get("evidence_id")}


def build_rows_from_snapshot(snapshot: dict, slug: str) -> list[dict]:
    """Build proposed fixture rows from one loaded corpus_snapshot dict."""
    evidence = snapshot.get("evidence_for_gen") or snapshot.get("evidence") or []
    on_topic = _on_topic_ids(evidence, slug)
    rows: list[dict] = []
    for ev in evidence:
        ev_id = ev.get("evidence_id")
        url = ev.get("source_url") or ev.get("url") or ""
        body = _body_text(ev)
        if len(body) < MIN_BODY_CHARS:
            continue
        if on_topic and ev_id not in on_topic:
            continue  # keep both classes on-topic
        label, reason = objective_rubric_label(
            url=url, doi=ev.get("doi"), pmid=ev.get("pmid")
        )
        if label is None:
            continue  # undecidable -> never guessed into the fixture
        host = _host(url)
        rows.append({
            "source_id": f"{slug}:{ev_id}",
            "topic_id": slug,
            "url": url,
            "registered_domain": _registered_domain(host),
            "source_type": _source_type(host),
            "post_extraction_body": body,
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            # ---- label provenance (the Codex iter-1 P1 contract) ----
            "rubric_label": label,
            "rubric_reason": reason,
            "family_a_label": label,            # deterministic objective rubric = family A proposal
            "family_b_label": None,             # Codex family adjudication (out-of-band)
            "operator_spotcheck": None,         # operator stratified spot-check (out-of-band)
            "label_status": "proposed",         # -> "adjudicated" only after two-family + spotcheck
            "scored_label": None,               # set ONLY when label_status == "adjudicated"
            "label_independent_of_tier": True,  # rubric never reads POLARIS tier/authority_score
        })
    return rows


def load_snapshot(snapshot_root: str, slug: str) -> dict | None:
    path = os.path.join(snapshot_root, slug, "corpus_snapshot.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_fixture(*, snapshot_root: str, slugs: list[str]) -> tuple[list[dict], dict]:
    """Build all proposed rows + a manifest. Returns (rows, manifest)."""
    all_rows: list[dict] = []
    per_slug = {}
    missing = []
    for slug in slugs:
        snap = load_snapshot(snapshot_root, slug)
        if snap is None:
            missing.append(slug)
            continue
        rows = build_rows_from_snapshot(snap, slug)
        per_slug[slug] = {
            "n_rows": len(rows),
            "n_authoritative": sum(1 for r in rows if r["rubric_label"] == 1),
            "n_spam": sum(1 for r in rows if r["rubric_label"] == 0),
        }
        all_rows.extend(rows)

    n_auth = sum(1 for r in all_rows if r["rubric_label"] == 1)
    n_spam = sum(1 for r in all_rows if r["rubric_label"] == 0)
    fixture_sha = hashlib.sha256(
        json.dumps([r["source_id"] for r in all_rows], sort_keys=True).encode("utf-8")
    ).hexdigest()
    source_types = sorted({r["source_type"] for r in all_rows})
    manifest = {
        "fixture": "clinical_quality_weight_fixture.jsonl",
        "n_rows": len(all_rows),
        "n_authoritative": n_auth,
        "n_spam": n_spam,
        "n_topics": len({r["topic_id"] for r in all_rows}),
        "source_types": source_types,
        "per_slug": per_slug,
        "missing_slugs": missing,
        "min_body_chars": MIN_BODY_CHARS,
        "label_status": "proposed",
        "fixture_id_sha256": fixture_sha,
        "label_integrity": {
            "scored_label_source": "pre-registered objective rubric (verifiable domain/document "
                                    "identity) -> family-A proposal; NEVER reads/quality, NEVER "
                                    "POLARIS tier/authority_score",
            "family_a": "deterministic objective rubric (this script)",
            "family_b": "Codex adjudication — OUT OF BAND, pending (label_status stays 'proposed')",
            "operator_spotcheck": "stratified sample spot-check — OUT OF BAND, pending",
            "judge_role": "PROPOSE only; never sets the scored label",
            "llm_judge_candidate_no_self_grade": "GLM-5.2 LLM-judge candidate is scored ONLY vs "
                                                 "a different family's labels (no circularity)",
        },
        "adjudication_blocker": (
            "label_status == 'proposed' for all rows: two-family (Codex) adjudication + operator "
            "stratified spot-check are out-of-band and PENDING. run_bakeoff scores only "
            "'adjudicated' rows; until adjudication, results are flagged provisional, never "
            "silently treated as final."
        ),
    }
    return all_rows, manifest


def write_fixture(rows: list[dict], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_fixture(path: str) -> list[dict]:
    """Load a built fixture jsonl. Fail loud if missing (never a silent empty)."""
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"quality_weight fixture not found: {path} — run build_fixture.py first "
            f"(it builds from banked corpus_snapshot.json bodies)."
        )
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot-root", default=DEFAULT_SNAPSHOT_ROOT)
    ap.add_argument("--slugs", default=",".join(DEFAULT_SLUGS))
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--manifest", default=os.path.join(_HERE, "clinical_quality_weight_manifest.json"))
    args = ap.parse_args(argv)

    slugs = [s for s in args.slugs.split(",") if s.strip()]
    rows, manifest = build_fixture(snapshot_root=args.snapshot_root, slugs=slugs)
    if not rows:
        print(
            f"FAIL LOUD: built 0 fixture rows from {args.snapshot_root} (slugs={slugs}). "
            f"Check the snapshot root exists and contains corpus_snapshot.json files.",
            file=sys.stderr,
        )
        return 1
    write_fixture(rows, args.out)
    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"built {manifest['n_rows']} rows "
          f"({manifest['n_authoritative']} authoritative / {manifest['n_spam']} spam) "
          f"across {manifest['n_topics']} topics, {len(manifest['source_types'])} source-types")
    print(f"  source_types: {manifest['source_types']}")
    print(f"  -> {args.out}")
    print(f"  -> {args.manifest}")
    print(f"  label_status=proposed (BLOCKER: {manifest['adjudication_blocker']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
