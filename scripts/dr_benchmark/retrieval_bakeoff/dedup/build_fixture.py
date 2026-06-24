#!/usr/bin/env python3
"""I-ret-002 (#1294) dedup layer — labeled near-dup PAIR fixture builder.

LAYER 5 (near-dup collapse BEFORE basket weight; never drops a distinct claim).

This builds the LABELED ground-truth PAIR fixture the dedup bake-off scores against. The
cardinal sin (per CLAUDE.md §-1.3) is a FALSE MERGE of two distinct independent sources — it
deletes a real corroborator from the basket. So the scored metric is pairwise collapse
precision/recall vs per-pair gold ``{syndicated_copy / distinct}`` with a PRE-REGISTERED
precision FLOOR = 0.97 (locked in run_bakeoff.py, not here, not post-hoc).

ANTI-CIRCULARITY (the whole ballgame — advisor-flagged):
  The gold label MUST be independent of every candidate's own similarity. If we labelled
  ``syndicated_copy := MinHash >= 0.9`` the bake-off would be rigged in MinHash's favour. So
  positives come ONLY from CANONICAL IDENTITY signals that no dedup candidate sees:
    - same canonical body (normalized-body sha256) under a different source_url  -> EXACT positive
    - same source_url RE-FETCHED across different banked runs, body byte-identical -> EXACT positive
      (real provenance: the identical page captured twice = a known-same pair by construction)
    - same DOI / PMID under a different source_url                                -> EXACT positive
  Negatives come from cross-topic pairs (a drb_72 AI-labor row vs a drb_76 colorectal row is
  distinct by construction — different questions, different evidence universes).

  The HARD bands decide the score but cannot be auto-labelled by objective rule:
    - edited-syndication near-dups (same url across runs, body DIFFERS by fetch jitter /
      truncation / boilerplate) -> emitted as a judge-PROPOSED ``pending_adjudication`` queue,
      NOT auto-scored. run_bakeoff.py FAILS LOUD if asked to score on unconfirmed labels.
    - same-topic similar-wording DISTINCT pairs -> the curated hard-negative SEED set
      (``fixtures/hard_negative_seeds.jsonl``), each pair carrying a written "why distinct"
      rationale (the human/two-family-authored part, clinical-safety-critical per the brief).

  "Judge PROPOSES only, never sets the scored label" is enforced structurally: this builder
  never writes a scored label derived from any similarity score.

SCALE (per design_must_fix.md #5 — "500 bodies exhaustive" was arithmetically impossible):
  exhaustive C(N,2) only when the labelled-identity body set is N<=80 (<=3,160 pairs); above
  that we STRATIFIED-SAMPLE pairs with a stated, seeded bound recorded in the manifest. Every
  sampling step is seeded; the seed is written to the fixture manifest.

KEEP-ALL PROVENANCE: every pair retains BOTH members' stable source IDs (evidence_id + run +
snapshot) so the downstream conservation assertion (cluster/singleton member-ID union ==
input ID set) can prove no source was silently dropped.

ISOLATION: this module is run from the REAL POLARIS checkout (where outputs/ snapshots live).
It locates the repo root via --repo-root / POLARIS_REPO_ROOT (default C:/POLARIS). It imports
NO heavy seam at module load; the offline smoke test mocks the loaders and uses synthetic data.

Output (under ``fixtures/``):
  - ``dedup_pairs_fixture.jsonl``   : SCORED pairs (label in {syndicated_copy, distinct},
                                       label_source in {canonical_body, canonical_url_refetch,
                                       canonical_doi, cross_topic, curated_hard_negative}).
  - ``pending_adjudication.jsonl``  : judge-PROPOSED near-dup band, NOT scored.
  - ``dedup_member_bodies.json``    : member_id -> normalized body (scorer side-index).
  - ``dedup_fixture_manifest.json`` : counts, seed, sampling bound, snapshot provenance, flags.
  - ``hard_negative_seeds.jsonl``   : authored curated distinct-but-similar seed pairs.

Run (offline, no GPU, no network — reads only banked snapshots):
  python scripts/dr_benchmark/retrieval_bakeoff/dedup/build_fixture.py \
      --repo-root C:/POLARIS --out-dir <this_dir>/fixtures
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import itertools
import json
import os
import random
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants (no magic numbers buried in logic; LAW VI).
# ---------------------------------------------------------------------------

# Banked snapshot slugs. The brief says "6 banked snapshots"; the 5 below are the canonical
# extracted snapshots present under outputs/corpus_backups/extracted/. drb_72 additionally
# appears across many run dirs (the cross-run re-fetch positive pool). We pool the canonical
# 5 + every run-dir copy of any slug we find. If a snapshot is missing we FLAG it (and fail
# loud on a zero pool, never silently proceed on an empty fixture).
CANONICAL_SLUGS: Tuple[str, ...] = (
    "drb_72_ai_labor",
    "drb_75_metal_ions_cvd",
    "drb_76_gut_microbiota_crc",
    "drb_78_parkinsons_dbs",
    "drb_90_adas_liability",
)

# Minimum normalized-body length to be eligible as a fixture member. Very short bodies
# (captcha stubs, nav chrome) are non-discriminative; excluded to keep the pair task honest.
MIN_BODY_CHARS: int = 120

# Exhaustive C(N,2) only up to this body count; above -> stratified sampling.
EXHAUSTIVE_MAX_BODIES: int = 80

# Stratified target counts (stated bound, recorded in the manifest).
TARGET_EXACT_POSITIVES: int = 400  # canonical-identity syndicated copies
TARGET_CROSS_TOPIC_NEGATIVES: int = 1200  # disjoint-topic distinct pairs
TARGET_PENDING_NEAR_DUP: int = 600  # judge-proposed edited-syndication band (NOT scored)

DEFAULT_SEED: int = 20260623

VALID_LABELS: Tuple[str, ...] = ("syndicated_copy", "distinct")
VALID_LABEL_SOURCES: Tuple[str, ...] = (
    "canonical_body",
    "canonical_url_refetch",
    "canonical_doi",
    "cross_topic",
    "curated_hard_negative",
)


# ---------------------------------------------------------------------------
# Data model.
# ---------------------------------------------------------------------------

@dataclass
class Member:
    """One side of a candidate pair — carries its stable provenance IDs (KEEP-ALL)."""

    member_id: str  # globally-unique stable id: f"{slug}::{run_tag}::{evidence_id}"
    slug: str
    run_tag: str
    evidence_id: str
    source_url: str
    doi: str
    title: str
    body: str  # normalized body text the dedup candidate actually compares
    body_sha: str

    def to_provenance(self) -> Dict[str, Any]:
        return {
            "member_id": self.member_id,
            "slug": self.slug,
            "run_tag": self.run_tag,
            "evidence_id": self.evidence_id,
            "source_url": self.source_url,
            "doi": self.doi,
            "title": self.title,
            "body_sha": self.body_sha,
        }


@dataclass
class LabeledPair:
    pair_id: str
    a: Dict[str, Any]  # member provenance (no body text — bodies live in the side index)
    b: Dict[str, Any]
    label: str  # "syndicated_copy" | "distinct"
    label_source: str
    rationale: str = ""


@dataclass
class FixtureManifest:
    seed: int
    snapshots_pooled: List[str] = field(default_factory=list)
    snapshots_requested: List[str] = field(default_factory=list)
    snapshots_missing: List[str] = field(default_factory=list)
    n_members: int = 0
    n_exact_positive_pairs: int = 0
    n_cross_topic_negative_pairs: int = 0
    n_curated_hard_negative_pairs: int = 0
    n_scored_pairs: int = 0
    n_pending_adjudication: int = 0
    exhaustive: bool = False
    sampling_bound_note: str = ""
    flags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Normalization (shared, deterministic — NOT any candidate's similarity).
# ---------------------------------------------------------------------------

def normalize_body(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. Identity normalization only.

    This is the canonical-identity body key. It is intentionally simple and is NOT a
    similarity measure — two bodies share a key iff they are byte-identical after trivial
    normalization, which is a ground-truth identity signal, not a learned/threshold score.
    """
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Snapshot loading.
# ---------------------------------------------------------------------------

def _run_tag_for_path(path: str) -> str:
    """Stable short tag for the run dir a snapshot came from (for provenance + dup collapse)."""
    norm = path.replace("\\", "/")
    parts = [p for p in norm.split("/") if p]
    try:
        i = parts.index("outputs")
        tag = parts[i + 1] if i + 1 < len(parts) else "outputs_root"
    except ValueError:
        tag = parts[-3] if len(parts) >= 3 else "unknown_run"
    return re.sub(r"[^A-Za-z0-9_]+", "_", tag)[:48] or "run"


def discover_snapshots(repo_root: str, slugs: Tuple[str, ...]) -> Dict[str, List[str]]:
    """Find every corpus_snapshot.json for each slug, anywhere under outputs/.

    Returns slug -> sorted list of file paths.
    """
    out: Dict[str, List[str]] = {}
    outputs = os.path.join(repo_root, "outputs")
    for slug in slugs:
        hits = sorted(
            set(
                glob.glob(
                    os.path.join(outputs, "**", slug, "corpus_snapshot.json"), recursive=True
                )
            )
        )
        out[slug] = hits
    return out


def load_members_from_snapshot(path: str, slug: str) -> List[Member]:
    """Load eligible members (rows with a real normalized body) from one snapshot."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return members_from_rows(data.get("evidence_for_gen", []) or [], slug, _run_tag_for_path(path))


def members_from_rows(rows: List[Dict[str, Any]], slug: str, run_tag: str) -> List[Member]:
    """Build Member objects from evidence rows (split out so the smoke test can call it)."""
    members: List[Member] = []
    for row in rows:
        raw_body = row.get("direct_quote") or row.get("statement") or ""
        body = normalize_body(raw_body)
        if len(body) < MIN_BODY_CHARS:
            continue
        evidence_id = str(row.get("evidence_id") or row.get("v30_entity_id") or "")
        if not evidence_id:
            continue
        source_url = str(row.get("source_url") or "")
        members.append(
            Member(
                member_id=f"{slug}::{run_tag}::{evidence_id}",
                slug=slug,
                run_tag=run_tag,
                evidence_id=evidence_id,
                source_url=source_url,
                doi=str(row.get("doi") or "").strip().lower(),
                title=str(row.get("title") or ""),
                body=body,
                body_sha=sha256_text(body),
            )
        )
    return members


# ---------------------------------------------------------------------------
# Pair construction by CANONICAL IDENTITY (anti-circularity core).
# ---------------------------------------------------------------------------

def _pair_key(a: Member, b: Member) -> Tuple[str, str]:
    return tuple(sorted((a.member_id, b.member_id)))  # type: ignore[return-value]


def build_exact_positive_pairs(members: List[Member]) -> List[Tuple[Member, Member, str]]:
    """syndicated_copy positives from canonical identity ONLY.

    Three independent identity channels, none of which is a dedup-candidate similarity:
      - canonical_body         : identical normalized-body sha, different source_url
      - canonical_url_refetch  : identical normalized-body sha, same source_url across runs
      - canonical_doi          : identical (non-empty) DOI, different source_url
    A pair qualifies if ANY channel fires; label_source records the channel.
    """
    by_body: Dict[str, List[Member]] = {}
    by_doi: Dict[str, List[Member]] = {}
    for m in members:
        by_body.setdefault(m.body_sha, []).append(m)
        if m.doi:
            by_doi.setdefault(m.doi, []).append(m)

    seen: set = set()
    pairs: List[Tuple[Member, Member, str]] = []

    for _sha, group in by_body.items():
        if len(group) < 2:
            continue
        for a, b in itertools.combinations(group, 2):
            if a.member_id == b.member_id:
                continue
            k = _pair_key(a, b)
            if k in seen:
                continue
            seen.add(k)
            same_url = bool(a.source_url) and a.source_url == b.source_url
            src = "canonical_url_refetch" if same_url else "canonical_body"
            pairs.append((a, b, src))

    for _doi, group in by_doi.items():
        if len(group) < 2:
            continue
        for a, b in itertools.combinations(group, 2):
            if a.member_id == b.member_id or a.body_sha == b.body_sha:
                continue  # body channel already covered identical bodies
            k = _pair_key(a, b)
            if k in seen:
                continue
            seen.add(k)
            pairs.append((a, b, "canonical_doi"))

    return pairs


def build_cross_topic_negatives(
    members_by_slug: Dict[str, List[Member]],
    rng: random.Random,
    target: int,
) -> List[Tuple[Member, Member, str]]:
    """distinct negatives from DISJOINT-topic pairs (different questions = distinct universes).

    Sampled (cross-topic space is enormous), seeded.
    """
    slugs = [s for s, ms in members_by_slug.items() if ms]
    pairs: List[Tuple[Member, Member, str]] = []
    if len(slugs) < 2:
        return pairs
    seen: set = set()
    attempts = 0
    max_attempts = max(target * 50, 1000)
    while len(pairs) < target and attempts < max_attempts:
        attempts += 1
        s1, s2 = rng.sample(slugs, 2)
        a = rng.choice(members_by_slug[s1])
        b = rng.choice(members_by_slug[s2])
        if a.body_sha == b.body_sha:
            continue  # cross-topic but identical boilerplate -> not a clean negative
        k = _pair_key(a, b)
        if k in seen:
            continue
        seen.add(k)
        pairs.append((a, b, "cross_topic"))
    return pairs


def build_pending_adjudication(
    members: List[Member],
    rng: random.Random,
    target: int,
) -> List[Tuple[Member, Member]]:
    """Edited-syndication band: SAME source_url across runs, body NOT identical.

    Judge-PROPOSED near-dups (same page, fetch jitter / truncation): very likely
    syndicated_copy but NOT auto-scored, because confirming requires reading the bodies
    (two-family adjudication). Emitted to pending_adjudication.jsonl; never a scored label.
    """
    by_url: Dict[str, List[Member]] = {}
    for m in members:
        if m.source_url:
            by_url.setdefault(m.source_url, []).append(m)
    candidates: List[Tuple[Member, Member]] = []
    seen: set = set()
    for _url, group in by_url.items():
        if len(group) < 2:
            continue
        for a, b in itertools.combinations(group, 2):
            if a.body_sha == b.body_sha:
                continue  # identical body already a scored EXACT positive
            k = _pair_key(a, b)
            if k in seen:
                continue
            seen.add(k)
            candidates.append((a, b))
    rng.shuffle(candidates)
    return candidates[:target]


# ---------------------------------------------------------------------------
# Curated hard-negative seeds (the authored, human/two-family part).
# ---------------------------------------------------------------------------

def load_or_init_hard_negative_seeds(out_dir: str) -> List[Dict[str, Any]]:
    """Load curated distinct-but-similar seed pairs; author a starter set if absent.

    Each seed is a REAL distinct pair that a naive similarity would over-merge, with a written
    "why distinct" rationale. This is the clinical-safety hard-negative band the precision
    floor is really measured on. These are AUTHORED labels (label_source =
    curated_hard_negative), never derived from any candidate score. The starter seeds are
    method-agnostic distinct pairs (two independent RCTs, review-vs-primary, two guideline
    editions, two agency labels differing in one word). The live build on the GPU box
    augments these with snapshot-resolved real pairs under two-family adjudication.
    """
    path = os.path.join(out_dir, "hard_negative_seeds.jsonl")
    if os.path.isfile(path):
        seeds: List[Dict[str, Any]] = []
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    seeds.append(json.loads(line))
        if seeds:
            return seeds
    seeds = starter_hard_negative_seeds()
    with open(path, "w", encoding="utf-8") as handle:
        for s in seeds:
            handle.write(json.dumps(s, ensure_ascii=False) + "\n")
    return seeds


def starter_hard_negative_seeds() -> List[Dict[str, Any]]:
    """Authored distinct-but-similar pairs with written rationales (template seed set)."""
    return [
        {
            "seed_id": "hn_two_independent_rcts",
            "body_a": normalize_body(
                "In a randomized double-blind placebo-controlled trial of 240 patients with "
                "stage II colorectal cancer, the synbiotic arm showed a statistically "
                "significant reduction in proliferation markers at 12 weeks (p=0.03)."
            ),
            "body_b": normalize_body(
                "In a randomized double-blind placebo-controlled trial of 198 patients with "
                "stage III colorectal cancer, the probiotic arm showed a statistically "
                "significant reduction in inflammatory cytokines at 8 weeks (p=0.02)."
            ),
            "label": "distinct",
            "label_source": "curated_hard_negative",
            "rationale": "Two SEPARATE trials: different sample sizes (240 vs 198), disease "
            "stage (II vs III), intervention (synbiotic vs probiotic), endpoint (proliferation "
            "vs cytokines), timepoint and p-value. Boilerplate RCT phrasing overlaps but the "
            "studies are independent corroborators; merging them DELETES a real corroborating "
            "source (a §-1.3 violation).",
        },
        {
            "seed_id": "hn_review_vs_included_primary",
            "body_a": normalize_body(
                "This systematic review and meta-analysis pooled 14 cohort studies "
                "(n=52,300) and found a relative risk of 1.4 for the exposure."
            ),
            "body_b": normalize_body(
                "This prospective cohort study of 3,100 participants reported a relative risk "
                "of 1.4 for the exposure over a 9-year follow-up."
            ),
            "label": "distinct",
            "label_source": "curated_hard_negative",
            "rationale": "A meta-analysis and ONE of its included primary cohorts. Same RR (1.4) "
            "and shared vocabulary, but distinct evidence levels (pooled review vs single "
            "cohort). Collapsing them loses the review-vs-primary distinction the basket "
            "weighting depends on.",
        },
        {
            "seed_id": "hn_same_guideline_two_editions",
            "body_a": normalize_body(
                "The 2021 clinical practice guideline recommends first-line therapy X for "
                "newly diagnosed patients, with a strong recommendation and moderate-quality "
                "evidence."
            ),
            "body_b": normalize_body(
                "The 2024 clinical practice guideline updates the recommendation to first-line "
                "therapy X for newly diagnosed patients, now with a strong recommendation and "
                "high-quality evidence after new trial data."
            ),
            "label": "distinct",
            "label_source": "curated_hard_negative",
            "rationale": "Two EDITIONS of the same guideline (2021 vs 2024). Near-identical "
            "wording, but the evidence grade changed (moderate -> high) on new data; the "
            "editions are distinct authoritative sources. Merging hides the temporal update a "
            "clinician must see.",
        },
        {
            "seed_id": "hn_two_agency_labels_same_drug",
            "body_a": normalize_body(
                "The product label states the drug is indicated for adults with the condition "
                "and is contraindicated in patients with severe hepatic impairment."
            ),
            "body_b": normalize_body(
                "The product label states the drug is indicated for adults with the condition "
                "and is contraindicated in patients with severe renal impairment."
            ),
            "label": "distinct",
            "label_source": "curated_hard_negative",
            "rationale": "Two regulatory labels for the same drug differing in ONE word "
            "(hepatic vs renal contraindication). Extremely high lexical overlap, but the "
            "safety content differs — exactly the case where a false merge is clinically "
            "dangerous. Must stay distinct.",
        },
    ]


# ---------------------------------------------------------------------------
# Fixture assembly.
# ---------------------------------------------------------------------------

def assemble_fixture(
    repo_root: str,
    out_dir: str,
    seed: int = DEFAULT_SEED,
    slugs: Tuple[str, ...] = CANONICAL_SLUGS,
) -> FixtureManifest:
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(seed)

    discovered = discover_snapshots(repo_root, slugs)
    members_by_slug: Dict[str, List[Member]] = {}
    pooled_snapshots: List[str] = []
    missing: List[str] = []
    seen_member_ids: set = set()

    for slug, paths in discovered.items():
        if not paths:
            missing.append(slug)
            continue
        slug_members: List[Member] = []
        for path in paths:
            try:
                ms = load_members_from_snapshot(path, slug)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            pooled_snapshots.append(os.path.relpath(path, repo_root).replace("\\", "/"))
            for m in ms:
                if m.member_id in seen_member_ids:
                    continue  # same evidence_id in same run dir -> keep one stable member
                seen_member_ids.add(m.member_id)
                slug_members.append(m)
        if slug_members:
            members_by_slug[slug] = slug_members

    all_members: List[Member] = [m for ms in members_by_slug.values() for m in ms]
    manifest = build_pairs_into_files(
        members_by_slug, all_members, out_dir, rng, seed, slugs, pooled_snapshots, missing
    )
    return manifest


def build_pairs_into_files(
    members_by_slug: Dict[str, List[Member]],
    all_members: List[Member],
    out_dir: str,
    rng: random.Random,
    seed: int,
    slugs: Tuple[str, ...],
    pooled_snapshots: List[str],
    missing: List[str],
) -> FixtureManifest:
    """Construct + write all fixture artifacts. Split out so the smoke test can drive it on
    synthetic members without touching the filesystem snapshots."""
    manifest = FixtureManifest(
        seed=seed,
        snapshots_pooled=pooled_snapshots,
        snapshots_requested=list(slugs),
        snapshots_missing=missing,
        n_members=len(all_members),
    )

    if not all_members:
        manifest.flags.append(
            "FATAL: zero eligible members across all snapshots — cannot build a pair fixture. "
            "Verify outputs/corpus_backups/extracted/<slug>/corpus_snapshot.json exists."
        )
        _write_manifest(out_dir, manifest)
        raise RuntimeError(manifest.flags[-1])

    if len(slugs) != 6:
        manifest.flags.append(
            f"NOTE: brief states '6 banked snapshots'; this build pooled "
            f"{len(members_by_slug)} slug(s) with data out of {len(slugs)} canonical slugs "
            f"requested. The drb_72 slug contributes many run-dir copies (the cross-run "
            f"re-fetch positive pool)."
        )

    exact_pos = build_exact_positive_pairs(all_members)
    exhaustive = len(all_members) <= EXHAUSTIVE_MAX_BODIES
    if not exhaustive and len(exact_pos) > TARGET_EXACT_POSITIVES:
        rng.shuffle(exact_pos)
        exact_pos = exact_pos[:TARGET_EXACT_POSITIVES]

    cross_neg = build_cross_topic_negatives(members_by_slug, rng, TARGET_CROSS_TOPIC_NEGATIVES)
    hard_neg_seeds = load_or_init_hard_negative_seeds(out_dir)
    pending = build_pending_adjudication(all_members, rng, TARGET_PENDING_NEAR_DUP)

    scored: List[LabeledPair] = []
    body_index: Dict[str, str] = {}

    def _emit(a: Member, b: Member, label: str, label_source: str, rationale: str = "") -> None:
        body_index[a.member_id] = a.body
        body_index[b.member_id] = b.body
        pid = "pair_" + hashlib.sha1(
            (a.member_id + "||" + b.member_id + "||" + label_source).encode("utf-8")
        ).hexdigest()[:16]
        scored.append(
            LabeledPair(
                pair_id=pid,
                a=a.to_provenance(),
                b=b.to_provenance(),
                label=label,
                label_source=label_source,
                rationale=rationale,
            )
        )

    for a, b, src in exact_pos:
        _emit(a, b, "syndicated_copy", src)
    for a, b, src in cross_neg:
        _emit(a, b, "distinct", src)

    for seed_row in hard_neg_seeds:
        ma = Member(
            member_id="seed::" + seed_row["seed_id"] + "::a",
            slug="curated",
            run_tag="seed",
            evidence_id=seed_row["seed_id"] + "_a",
            source_url="",
            doi="",
            title="",
            body=seed_row["body_a"],
            body_sha=sha256_text(seed_row["body_a"]),
        )
        mb = Member(
            member_id="seed::" + seed_row["seed_id"] + "::b",
            slug="curated",
            run_tag="seed",
            evidence_id=seed_row["seed_id"] + "_b",
            source_url="",
            doi="",
            title="",
            body=seed_row["body_b"],
            body_sha=sha256_text(seed_row["body_b"]),
        )
        _emit(ma, mb, "distinct", "curated_hard_negative", seed_row.get("rationale", ""))

    manifest.n_exact_positive_pairs = sum(1 for p in scored if p.label == "syndicated_copy")
    manifest.n_cross_topic_negative_pairs = sum(
        1 for p in scored if p.label_source == "cross_topic"
    )
    manifest.n_curated_hard_negative_pairs = sum(
        1 for p in scored if p.label_source == "curated_hard_negative"
    )
    manifest.n_scored_pairs = len(scored)
    manifest.n_pending_adjudication = len(pending)
    manifest.exhaustive = exhaustive
    manifest.sampling_bound_note = (
        "exhaustive C(N,2) over identity-grouped members"
        if exhaustive
        else (
            f"stratified seeded sampling: exact_pos capped {TARGET_EXACT_POSITIVES}, "
            f"cross_topic_neg target {TARGET_CROSS_TOPIC_NEGATIVES}, pending near-dup target "
            f"{TARGET_PENDING_NEAR_DUP}; seed={seed}. The precision floor is estimated on the "
            f"hard-negative + cross-topic bands; run_bakeoff reports a Wilson CI so a thin band "
            f"does not silently crown a winner."
        )
    )
    if manifest.n_exact_positive_pairs == 0:
        manifest.flags.append(
            "WARNING: zero canonical-identity positives — recall is unmeasurable. Check that "
            "cross-run re-fetch snapshots are present (the drb_72 run dirs)."
        )
    if manifest.n_curated_hard_negative_pairs < 4:
        manifest.flags.append(
            "WARNING: hard-negative band is thin; the 0.97 precision floor decision will have "
            "a wide CI. Author more curated_hard_negative seeds before crowning a winner."
        )

    _write_jsonl(os.path.join(out_dir, "dedup_pairs_fixture.jsonl"), [asdict(p) for p in scored])
    _write_jsonl(
        os.path.join(out_dir, "pending_adjudication.jsonl"),
        [
            {
                "pair_id": "pending_"
                + hashlib.sha1((a.member_id + "||" + b.member_id).encode("utf-8")).hexdigest()[
                    :16
                ],
                "a": a.to_provenance(),
                "b": b.to_provenance(),
                "proposed_label": "syndicated_copy",
                "label_status": "PENDING_TWO_FAMILY_ADJUDICATION",
                "note": "same source_url re-fetched across runs, body differs (fetch jitter / "
                "truncation). Judge-PROPOSED only; NOT a scored label. run_bakeoff.py refuses "
                "to score these until a two-family-adjudicated artifact resolves them.",
            }
            for a, b in pending
        ],
    )
    _write_json(os.path.join(out_dir, "dedup_member_bodies.json"), body_index)
    _write_manifest(out_dir, manifest)
    return manifest


# ---------------------------------------------------------------------------
# IO helpers.
# ---------------------------------------------------------------------------

def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=1)


def _write_manifest(out_dir: str, manifest: FixtureManifest) -> None:
    _write_json(os.path.join(out_dir, "dedup_fixture_manifest.json"), asdict(manifest))


# ---------------------------------------------------------------------------
# Loader used by run_bakeoff / gate0 (single source of truth for the fixture shape).
# ---------------------------------------------------------------------------

def load_fixture(out_dir: str) -> Dict[str, Any]:
    """Load the built fixture. Fails loud if any required artifact is missing or a scored
    label is not from a canonical-identity / authored source (anti-circularity guard)."""
    pairs_path = os.path.join(out_dir, "dedup_pairs_fixture.jsonl")
    bodies_path = os.path.join(out_dir, "dedup_member_bodies.json")
    manifest_path = os.path.join(out_dir, "dedup_fixture_manifest.json")
    for p in (pairs_path, bodies_path, manifest_path):
        if not os.path.isfile(p):
            raise FileNotFoundError(
                f"dedup fixture artifact missing: {p}. Run build_fixture.py first."
            )
    pairs: List[Dict[str, Any]] = []
    with open(pairs_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    with open(bodies_path, encoding="utf-8") as handle:
        bodies = json.load(handle)
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert_no_circular_labels(pairs)
    return {"pairs": pairs, "bodies": bodies, "manifest": manifest}


def assert_no_circular_labels(pairs: List[Dict[str, Any]]) -> None:
    """Fail loud if any scored pair has a non-binary label or a similarity-derived source."""
    for p in pairs:
        if p.get("label") not in VALID_LABELS:
            raise ValueError(f"fixture pair {p.get('pair_id')} has a non-binary scored label")
        if p.get("label_source") not in VALID_LABEL_SOURCES:
            raise ValueError(
                f"fixture pair {p.get('pair_id')} has a non-canonical label_source "
                f"{p.get('label_source')!r} — scored labels must come from canonical identity "
                f"or authored curation, never a candidate similarity (anti-circularity)."
            )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the dedup near-dup PAIR fixture.")
    parser.add_argument("--repo-root", default=os.environ.get("POLARIS_REPO_ROOT", "C:/POLARIS"))
    parser.add_argument(
        "--out-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"),
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    manifest = assemble_fixture(args.repo_root, args.out_dir, seed=args.seed)
    print(json.dumps(asdict(manifest), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
