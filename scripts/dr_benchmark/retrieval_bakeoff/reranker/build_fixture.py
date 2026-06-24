#!/usr/bin/env python3
"""I-ret-002 (#1294) reranker-layer ISOLATION bake-off — labelled ground-truth fixture builder.

This module builds (or loads) the FROZEN pre-rerank candidate-pool fixture that every reranker
candidate is scored on. Per the brief (§6 "reranker") the fixture carries, per gold idx:

  * a byte-identical, banked pre-rerank candidate pool (so every reranker sees the EXACT same
    rows; no live re-retrieval per candidate — that would leak query-gen variance and break
    isolation), AND
  * per-candidate (claim-level RELEVANCE x INDEPENDENT CREDIBILITY) gain labels in {0,1,2,3}.

Two hard correctness rules from the brief + the Codex iter-2 resolution, encoded structurally
here so they cannot drift:

  1. CREDIBILITY LABEL INDEPENDENCE. The credibility label is produced by an INDEPENDENT
     two-family adjudication over the pre-rerank pool — it is NEVER read from POLARIS's own
     ``tier`` / ``authority_score`` metadata (grading a reranker's credibility ordering against
     POLARIS tier would just reward agreement with POLARIS). Independence is enforced primarily by
     PROCESS: this module NEVER computes a credibility label from tier — the SCORED label is the
     two-family-adjudicated + operator-spot-checked value LOADED from the separate annotation file,
     and the judge only PROPOSES. Two BACKSTOPS catch a lazily tier-derived annotation:
     ``_assert_no_polaris_tier_leak`` (per-row literal-echo check) and
     ``assert_credibility_not_tier_derived`` (aggregate: fail loud if the whole annotation is a
     deterministic function of the T1..T7 tier band). They are backstops, not the primary guarantee.

  2. CLAIM-LEVEL RELEVANCE RESOLUTION (the idx66 collapse fix). DRB-II ``info_recall`` findings
     without a quoted title (idx66: only 3/48 carry a title) are judge-mapped to their supporting
     source at the CLAIM level, never title-matched and silently dropped. Per-idx gold-N is
     reported so a thin denominator is visible (never a hidden drop).

DEMOTE-ONLY / WEIGHT-NOT-FILTER (§-1.3). The raw-json "off-topic-drop threshold" facet is
SUPERSEDED and SCRUBBED: off-topic items get gain 0 (they sink in graded NDCG), they are NEVER
removed. There is no drop threshold anywhere in this fixture. ``assert_demote_only_invariant``
fail-loud-checks that the gain map contains a 0 (demotion) and no "drop" key ever appears.

HONEST SCOPE. Real two-family credibility annotation is a separate parallel judge job (the brief
budgets it as such). This builder constructs the frozen pool + the adjudication SCHEMA/HOOKS +
the annotation LOADER. If the annotation file is absent it FAILS LOUD (never fabricates labels);
the offline smoke supplies a tiny synthetic annotation so it can prove the math + schema without
the real judge job. That honest gap is reported, never hidden.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

# --- reuse the lineage seam (idx binding; fail-loud on an unregistered benchmark slug) --------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.dr_benchmark.retrieval_bakeoff.reranker._lineage_seam import (  # noqa: E402
    SLUG_TO_IDX,
    GateZeroLineageError,
    assert_drb_slug_registered,
    is_benchmark_slug,
)

# The four gold-bearing benchmark slugs the reranker bake-off binds (brief §6 + raw-json
# holding_condition: drb_72->56, drb_75->62, drb_76->66, drb_78->72). Resolved from the lineage
# seam, never hardcoded as an idx here.
GOLD_SLUGS: tuple[str, ...] = (
    "drb_72_ai_labor",
    "drb_75_metal_ions_cvd",
    "drb_76_gut_microbiota_crc",
    "drb_78_parkinsons_dbs",
)

# Pre-registered graded-gain scale. RELEVANCE (claim-level info_recall support) x INDEPENDENT
# CREDIBILITY combine DETERMINISTICALLY into a single gain in {0,1,2,3}. Pre-registered here so it
# is NOT reverse-engineered to favour a candidate (advisor #11). off_topic -> 0 ALWAYS (demotion,
# never a drop). The mapping is intentionally explicit and total over the label cross-product.
#
#   relevance label : off_topic | on_topic_irrelevant | supporting | strongly_supporting
#   credibility label: spam | low | medium | high   (INDEPENDENT of POLARIS tier)
#
# gain = 0 unless the source actually SUPPORTS a gold claim; among supporting sources, gain rises
# with credibility. on_topic-but-non-supporting (e.g. on-topic SEO spam) stays low. This rewards
# "credible AND relevant ranked first", with off-topic demoted to the floor — never dropped.
RELEVANCE_LABELS: tuple[str, ...] = (
    "off_topic",
    "on_topic_irrelevant",
    "supporting",
    "strongly_supporting",
)
CREDIBILITY_LABELS: tuple[str, ...] = ("spam", "low", "medium", "high")

GRADED_GAIN_TABLE: dict[tuple[str, str], int] = {
    # off_topic -> 0 for ANY credibility (demote-only; off-topic never removed, never rewarded).
    ("off_topic", "spam"): 0,
    ("off_topic", "low"): 0,
    ("off_topic", "medium"): 0,
    ("off_topic", "high"): 0,
    # on-topic but NOT supporting a gold claim (on-topic spam / fluff): small or zero gain.
    ("on_topic_irrelevant", "spam"): 0,
    ("on_topic_irrelevant", "low"): 0,
    ("on_topic_irrelevant", "medium"): 1,
    ("on_topic_irrelevant", "high"): 1,
    # supporting a gold claim: gain scales with INDEPENDENT credibility.
    ("supporting", "spam"): 1,
    ("supporting", "low"): 1,
    ("supporting", "medium"): 2,
    ("supporting", "high"): 2,
    # strongly supporting a gold claim from a credible source: top gain.
    ("strongly_supporting", "spam"): 1,
    ("strongly_supporting", "low"): 2,
    ("strongly_supporting", "medium"): 2,
    ("strongly_supporting", "high"): 3,
}

# A source labelled "required" (its gold claim has NO other supporting source in the pool) is the
# cardinal recall@K guard target: a reranker that pushes a required source out of the top-K starves
# the downstream basket. This mirrors the dedup 0.97 precision floor — a hard NON-REGRESSION gate.
REQUIRED_RECALL_FLOOR_RELATIVE_TO_BASELINE: float = 1.0  # must be >= baseline recall@K (no regression)


class FixtureError(RuntimeError):
    """Fail-loud error building/loading the reranker fixture (never a silent empty fixture)."""


@dataclass
class PoolCandidate:
    """One row in the FROZEN pre-rerank pool for a gold idx."""

    cand_id: str
    title: str
    body: str  # extracted main content (held-fixed Trafilatura output, per holding_condition)
    url: str
    # SCORED labels — set ONLY by two-family adjudication (judge proposes, never sets). These are
    # loaded from the annotation file, NOT computed from POLARIS metadata.
    relevance_label: str = ""
    credibility_label: str = ""
    supports_claim_ids: list[str] = field(default_factory=list)  # claim-level resolution
    required: bool = False  # sole supporter of its gold claim -> recall@K guard target

    def gain(self) -> int:
        """DETERMINISTIC graded gain from the pre-registered table. Fail loud on an unknown label
        (never default to a believable middle value — that would mask a mislabel)."""
        key = (self.relevance_label, self.credibility_label)
        if key not in GRADED_GAIN_TABLE:
            raise FixtureError(
                f"cand {self.cand_id!r}: unknown (relevance,credibility) label pair {key!r}; "
                f"valid relevance={RELEVANCE_LABELS} credibility={CREDIBILITY_LABELS}. "
                f"The label must come from two-family adjudication, never a silent default."
            )
        return GRADED_GAIN_TABLE[key]


@dataclass
class GoldIdxFixture:
    """The frozen pool + labels for ONE gold idx."""

    slug: str
    idx: int
    question: str
    pool: list[PoolCandidate]
    gold_claim_ids: list[str]  # claim-level info_recall ids (the denominator we report per idx)

    def pool_sha(self) -> str:
        """Stable hash of the frozen pool ORDER+content (proves every candidate saw the same input)."""
        h = hashlib.sha256()
        for c in self.pool:
            h.update(c.cand_id.encode("utf-8"))
            h.update(b"\x00")
            h.update(c.body.encode("utf-8"))
            h.update(b"\x01")
        return h.hexdigest()

    def gains(self) -> list[int]:
        return [c.gain() for c in self.pool]

    def required_ids(self) -> list[str]:
        return [c.cand_id for c in self.pool if c.required]


# ---------------------------------------------------------------------------------------------
# Invariant assertions (structural §-1.3 guards) — called by the builder AND by gate0/smoke.
# ---------------------------------------------------------------------------------------------
def assert_demote_only_invariant(gain_table: dict[tuple[str, str], int]) -> None:
    """Fail loud unless the gain table is DEMOTE-ONLY (off_topic -> 0 for every credibility) and
    carries NO drop semantics. This is the structural scrub of the SUPERSEDED off-topic-drop facet
    (brief §6 BUILD-HANDOFF NOTE). A reranker may demote (gain 0), NEVER remove."""
    for cred in CREDIBILITY_LABELS:
        key = ("off_topic", cred)
        if gain_table.get(key) != 0:
            raise FixtureError(
                f"DEMOTE-ONLY violation: off_topic x {cred} must map to gain 0 (demotion), "
                f"got {gain_table.get(key)!r}. Off-topic items sink to the floor, never dropped."
            )
    # No key may encode a "drop"/"remove"/"filter" action — gains are integers only.
    for k, v in gain_table.items():
        if not isinstance(v, int) or v < 0:
            raise FixtureError(
                f"gain for {k!r} = {v!r} is not a non-negative int; a hard-drop / negative-gain "
                f"sentinel is a §-1.3 weight-not-filter breach and is forbidden."
            )


# POLARIS tier values are T1..T7. To catch a credibility label that was DERIVED from the tier (the
# obvious circular shortcut: T1/T2 -> "high", T3/T4 -> "medium", ...), we map tier -> the credibility
# band it would collapse to and fail loud if the scored label exactly matches that derivation for
# EVERY row. A single coincidental match is not proof of a leak (a genuinely-high source IS often
# T1); independence is enforced primarily by PROCESS (the scored label is loaded from the separate
# two-family annotation file, never computed from tier here). This guard is a BACKSTOP that catches
# the gross case where the annotation was lazily back-filled from tier.
_TIER_TO_CREDIBILITY_BAND: dict[str, str] = {
    "t1": "high", "t2": "high",
    "t3": "medium", "t4": "medium",
    "t5": "low", "t6": "low",
    "t7": "spam",
}


def _tier_derived_band(raw_row: dict[str, Any]) -> Optional[str]:
    """The credibility band a row's POLARIS tier WOULD collapse to (or None if no usable tier)."""
    for f in ("tier", "authority_tier", "credibility_tier"):
        v = str(raw_row.get(f) or "").strip().lower()
        if v in _TIER_TO_CREDIBILITY_BAND:
            return _TIER_TO_CREDIBILITY_BAND[v]
    return None


def _assert_no_polaris_tier_leak(raw_row: dict[str, Any], scored_credibility: str) -> None:
    """Per-row BACKSTOP against a credibility label trivially copied/derived from POLARIS tier
    metadata (the circular trap §6 forbids). Independence is PROCESS-enforced (scored labels come
    from the separate two-family annotation file). This catches the gross derivation: the scored
    band equals the tier-derived band AND a raw band string was literally echoed.

    Note: a single match is NOT a leak (a T1 source legitimately IS 'high'). The aggregate guard
    ``assert_credibility_not_tier_derived`` (called over the whole pool) is the real independence
    check; this per-row helper only flags a literal field echo for fast feedback."""
    raw_echo_fields = ("authority_score", "credibility_label_from_tier")
    for f in raw_echo_fields:
        if f in raw_row and str(raw_row.get(f)).strip().lower() == str(scored_credibility).strip().lower():
            raise FixtureError(
                f"CREDIBILITY-INDEPENDENCE violation: scored credibility {scored_credibility!r} "
                f"literally echoes POLARIS metadata field {f!r}={raw_row.get(f)!r}. The credibility "
                f"label MUST be an independent two-family annotation, not POLARIS tier (brief §6)."
            )


def assert_credibility_not_tier_derived(
    rows_and_labels: list[tuple[dict[str, Any], str]],
) -> None:
    """AGGREGATE independence guard: fail loud if EVERY row whose POLARIS tier is known has a scored
    credibility label that exactly equals the tier-derived band — i.e. the whole annotation is a
    deterministic function of tier (the circular shortcut). Requires at least one tier-bearing row;
    a partial match is allowed (a credible T1 source genuinely mapping to 'high' is fine)."""
    derivable = [
        (band, scored)
        for raw, scored in rows_and_labels
        if (band := _tier_derived_band(raw)) is not None
    ]
    if len(derivable) < 2:
        return  # too few tier-bearing rows to conclude a systematic derivation
    if all(band == scored for band, scored in derivable):
        raise FixtureError(
            "CREDIBILITY-INDEPENDENCE violation (aggregate): every tier-bearing row's scored "
            "credibility label exactly equals its POLARIS tier-derived band — the annotation is a "
            "deterministic function of POLARIS tier, not an independent two-family judgment (§6). "
            f"({len(derivable)} rows checked.)"
        )


def _resolve_idx(slug: str) -> int:
    """idx via the lineage seam; fail loud on an unregistered benchmark slug (drb_72 anti-pattern)."""
    if is_benchmark_slug(slug):
        assert_drb_slug_registered(slug)
    if slug not in SLUG_TO_IDX:
        raise FixtureError(
            f"slug {slug!r} has no canonical idx in SLUG_TO_IDX; resolve it from the gold file "
            f"before adding it (never guess the idx)."
        )
    return SLUG_TO_IDX[slug]


# ---------------------------------------------------------------------------------------------
# Annotation loader — the SCORED labels (two-family adjudicated, judge proposes only).
# ---------------------------------------------------------------------------------------------
def _load_pool_for_idx(slug: str, pool_dir: str) -> list[dict[str, Any]]:
    """Load the FROZEN pre-rerank pool rows for a slug from ``<pool_dir>/<slug>.pool.jsonl``.

    Each row = {cand_id, title, body, url, ...optional POLARIS metadata...}. Fail loud if missing
    or empty (never an empty pool silently)."""
    path = os.path.join(pool_dir, f"{slug}.pool.jsonl")
    if not os.path.isfile(path):
        raise FixtureError(
            f"frozen pool not found for {slug!r}: {path}. Build it ONCE from the banked "
            f"corpus_snapshot (held-fixed IterResearch queries) before running the bake-off."
        )
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise FixtureError(f"frozen pool for {slug!r} is EMPTY ({path}); refusing to score an empty pool.")
    return rows


def _load_annotation_for_idx(slug: str, annot_dir: str) -> dict[str, dict[str, Any]]:
    """Load the two-family-adjudicated SCORED labels for a slug from
    ``<annot_dir>/<slug>.labels.jsonl``: cand_id -> {relevance_label, credibility_label,
    supports_claim_ids, required, adjudication{...}}. Judge PROPOSES only; this file holds the
    adjudicated value. Fail loud if missing (never fabricate labels)."""
    path = os.path.join(annot_dir, f"{slug}.labels.jsonl")
    if not os.path.isfile(path):
        raise FixtureError(
            f"two-family credibility/relevance annotation not found for {slug!r}: {path}. This is "
            f"the separate parallel judge job (brief execution plan); it must be produced + "
            f"operator-spot-checked before the bake-off scores trust this idx. NOT fabricated."
        )
    out: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            cid = rec.get("cand_id")
            if not cid:
                raise FixtureError(f"annotation row missing cand_id in {path}: {rec!r}")
            out[cid] = rec
    return out


def _load_gold_claims_for_idx(idx: int, info_recall_dir: str) -> list[str]:
    """Load the claim-level info_recall gold-claim ids for an idx from
    ``<info_recall_dir>/idx_<idx>.claims.json`` (a list of claim ids). Claim-level resolution fixes
    the idx66 collapse (untitled findings judge-mapped to their source). Fail loud if missing."""
    path = os.path.join(info_recall_dir, f"idx_{idx}.claims.json")
    if not os.path.isfile(path):
        raise FixtureError(
            f"info_recall gold claims not found for idx={idx}: {path}. Build claim-level gold "
            f"(judge-map untitled findings to supporting source; report per-idx gold-N)."
        )
    with open(path, encoding="utf-8") as fh:
        claims = json.load(fh)
    if not isinstance(claims, list) or not claims:
        raise FixtureError(f"info_recall gold claims for idx={idx} must be a non-empty list ({path}).")
    return [str(c) for c in claims]


def build_idx_fixture(
    slug: str,
    *,
    pool_dir: str,
    annot_dir: str,
    info_recall_dir: str,
) -> GoldIdxFixture:
    """Build the frozen-pool + SCORED-label fixture for ONE gold idx. The judge only PROPOSES;
    the scored labels come from the two-family annotation file. Credibility independence + claim-
    level resolution + demote-only are enforced structurally."""
    idx = _resolve_idx(slug)
    pool_rows = _load_pool_for_idx(slug, pool_dir)
    annot = _load_annotation_for_idx(slug, annot_dir)
    gold_claim_ids = _load_gold_claims_for_idx(idx, info_recall_dir)

    question = ""
    pool: list[PoolCandidate] = []
    rows_and_creds: list[tuple[dict[str, Any], str]] = []
    for row in pool_rows:
        cid = row.get("cand_id")
        if not cid:
            raise FixtureError(f"pool row for {slug!r} missing cand_id: {row!r}")
        question = question or str(row.get("question") or "")
        a = annot.get(cid)
        if a is None:
            raise FixtureError(
                f"pool cand {cid!r} ({slug}) has NO adjudicated label; every scored row must be "
                f"two-family-confirmed (no silent default). Annotate it or exclude it explicitly."
            )
        rel = str(a.get("relevance_label") or "")
        cred = str(a.get("credibility_label") or "")
        if rel not in RELEVANCE_LABELS:
            raise FixtureError(f"cand {cid!r}: relevance_label {rel!r} not in {RELEVANCE_LABELS}")
        if cred not in CREDIBILITY_LABELS:
            raise FixtureError(f"cand {cid!r}: credibility_label {cred!r} not in {CREDIBILITY_LABELS}")
        # Independence backstop: scored credibility must not literally echo POLARIS tier metadata.
        _assert_no_polaris_tier_leak(row, cred)
        rows_and_creds.append((row, cred))
        pool.append(
            PoolCandidate(
                cand_id=str(cid),
                title=str(row.get("title") or ""),
                body=str(row.get("body") or ""),
                url=str(row.get("url") or ""),
                relevance_label=rel,
                credibility_label=cred,
                supports_claim_ids=[str(x) for x in (a.get("supports_claim_ids") or [])],
                required=bool(a.get("required", False)),
            )
        )

    assert_demote_only_invariant(GRADED_GAIN_TABLE)
    # Aggregate independence guard: the annotation must NOT be a deterministic function of POLARIS
    # tier (the real circularity check; the per-row helper above only catches a literal echo).
    assert_credibility_not_tier_derived(rows_and_creds)
    fixture = GoldIdxFixture(
        slug=slug, idx=idx, question=question, pool=pool, gold_claim_ids=gold_claim_ids
    )
    # Touch gains so a mislabel fails loud at BUILD time, not silently at score time.
    _ = fixture.gains()
    return fixture


def build_all(
    *,
    slugs: tuple[str, ...] = GOLD_SLUGS,
    pool_dir: str,
    annot_dir: str,
    info_recall_dir: str,
) -> dict[str, GoldIdxFixture]:
    """Build the fixture for every gold idx. Reports per-idx gold-N (visible thin denominator)."""
    out: dict[str, GoldIdxFixture] = {}
    for slug in slugs:
        fx = build_idx_fixture(
            slug, pool_dir=pool_dir, annot_dir=annot_dir, info_recall_dir=info_recall_dir
        )
        out[slug] = fx
        print(
            f"[{slug}] idx={fx.idx} pool={len(fx.pool)} gold_claims(N)={len(fx.gold_claim_ids)} "
            f"required={len(fx.required_ids())} pool_sha={fx.pool_sha()[:16]}",
            flush=True,
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the reranker ISOLATION bake-off fixture.")
    ap.add_argument("--pool-dir", required=True, help="dir of <slug>.pool.jsonl frozen pre-rerank pools")
    ap.add_argument("--annot-dir", required=True, help="dir of <slug>.labels.jsonl two-family labels")
    ap.add_argument("--info-recall-dir", required=True, help="dir of idx_<idx>.claims.json gold claims")
    ap.add_argument("--slugs", default=",".join(GOLD_SLUGS))
    args = ap.parse_args()

    slugs = tuple(s for s in args.slugs.split(",") if s)
    try:
        build_all(
            slugs=slugs,
            pool_dir=args.pool_dir,
            annot_dir=args.annot_dir,
            info_recall_dir=args.info_recall_dir,
        )
    except (FixtureError, GateZeroLineageError) as exc:
        print(f"FIXTURE BUILD FAILED (fail-loud): {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
