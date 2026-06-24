#!/usr/bin/env python3
"""I-ret-002 (#1294) — embedder_late_interaction layer: LABELED ground-truth fixture builder.

Builds the TWO-AXIS labeled fixture this layer is scored on (brief §7):

  Axis A  — AUC(on-topic > off-topic) separation.
            Candidate POS/NEG rows are SEEDED from
            ``scripts/relevance_scorer_bakeoff.py`` LABEL_SETS keywords, but the keywords
            PROPOSE rows only. EVERY scored row's relevance label must be confirmed by an
            independent TWO-FAMILY adjudication (Claude + Codex) with an operator sample
            spot-check (brief iter-2 P1 fix). A keyword-proposed row that has NO two-family
            adjudication record is marked ``scored=False`` and is EXCLUDED from the scored set
            — never silently scored against a string-pattern label (that would make AUC reward
            agreement with a keyword, not true relevance, a §-1.1 banned pattern-proxy).

  Axis B  — reasoning-retrieval recall@k on NON-LEXICAL evidence (the late-interaction edge).
            (rubric-claim -> non-lexically-overlapping supporting source) pairs, hand/judge
            verified via the same two-family adjudication. The "non-lexical" property is what a
            single-vector bag-of-words-ish embedder misses and a token-level MaxSim (ColBERT)
            late-interaction model can recover; the pairs are screened so the claim and the
            supporting body share FEW surface content words (lexical-overlap below a
            pre-registered ceiling), so recall@k measures reasoning retrieval, not term match.

GROUND-TRUTH SOURCE: the 6 banked ``corpus_snapshot.json`` files (real POLARIS retrieval
output), NOT synthetic data. The adjudication LABELS live in a side file
(``axis_a_adjudication.jsonl`` / ``axis_b_adjudication.jsonl``) that records, per row/pair, the
two-family verdicts; the SCORED label is the adjudicated label, never the keyword proposal.

This builder is OFFLINE and deterministic: it loads JSON snapshots + the adjudication side
files; it loads NO model and hits NO network. The model loading happens only in
``run_bakeoff.py`` on the GPU box.

REPO-ROOT note: this file may run from a sparse git worktree where the read-only seams/data
(``scripts/relevance_scorer_bakeoff.py``, banked snapshots) live in the MAIN checkout. The repo
root is resolved by walking up for the seam, then falling back to ``POLARIS_REPO_ROOT`` env /
``C:/POLARIS`` — so the same code works in the worktree and on the GPU box.

Per CLAUDE.md §-1.1 (label against real labeled ground truth, no count/pattern proxy),
§-1.3 (weight-not-filter — nothing is hard-dropped here; the off-topic rows are KEPT as the
negative class), LAW II (no fake working — adjudication records are real files, missing ones
fail loud or are honestly excluded, never faked).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


class FixtureBuildError(RuntimeError):
    """Raised fail-loud when the labeled fixture cannot be built honestly."""


def resolve_repo_root() -> str:
    """Find the checkout that holds the read-only seams/data (relevance_scorer_bakeoff.py).

    Tries, in order: walk up from this file; ``POLARIS_REPO_ROOT`` env; the canonical
    ``C:/POLARIS``. Fails loud if none contain the required seam (LAW II — no silent default).
    """
    seam_rel = os.path.join("scripts", "relevance_scorer_bakeoff.py")
    candidates: list[str] = []
    cur = _THIS_DIR
    for _ in range(8):
        candidates.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    env_root = os.getenv("POLARIS_REPO_ROOT")
    if env_root:
        candidates.append(env_root)
    candidates.append(r"C:/POLARIS")
    candidates.append("/c/POLARIS")
    for root in candidates:
        if root and os.path.isfile(os.path.join(root, seam_rel)):
            return root
    raise FixtureBuildError(
        "could not locate the repo root containing scripts/relevance_scorer_bakeoff.py "
        f"(searched {candidates}); set POLARIS_REPO_ROOT to the main checkout"
    )


def _import_label_sets() -> dict[str, Any]:
    """Import LABEL_SETS + label helpers from the named seam without a hard dependency on cwd."""
    import importlib.util

    root = resolve_repo_root()
    seam = os.path.join(root, "scripts", "relevance_scorer_bakeoff.py")
    spec = importlib.util.spec_from_file_location("relevance_scorer_bakeoff", seam)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return {
        "LABEL_SETS": mod.LABEL_SETS,
        "label_rows": mod.label_rows,
        "rtext": mod.rtext,
        "_txt": mod._txt,
        "_repo_root": root,
    }


# Pre-registered NON-LEXICAL ceiling for Axis B (locked before execution, brief §7):
# a (claim, supporting-source) pair qualifies as "non-lexical evidence" only if the
# Jaccard content-word overlap between the claim text and the supporting body is BELOW this
# ceiling. This is the property a single-vector embedder fails and late-interaction recovers.
AXIS_B_LEXICAL_OVERLAP_CEILING = float(os.getenv("PG_EMBED_AXISB_OVERLAP_CEILING", "0.10"))

# Pre-registered BOUNDS on Axis-B candidate-pair generation (locked before execution; the same
# "stratified with a STATED bound, not exhaustive C(N,2)" discipline the brief mandates for the
# dedup layer, applied here so the builder is deterministic and does not blow up O(N^2) on a
# ~600-row snapshot). These bound only the CANDIDATE set; the SCORED set is still gated solely
# by the two-family adjudication file.
AXIS_B_MAX_CLAIMS_PER_SLUG = int(os.getenv("PG_EMBED_AXISB_MAX_CLAIMS_PER_SLUG", "60"))
AXIS_B_MAX_CANDIDATES_PER_CLAIM = int(os.getenv("PG_EMBED_AXISB_MAX_CANDS_PER_CLAIM", "40"))


def default_snapshot_roots(repo_root: str) -> list[str]:
    """Default banked snapshot search roots (real POLARIS output, not synthetic)."""
    return [
        os.path.join(repo_root, "state", "reserved_corpus_snapshots"),
        os.path.join(repo_root, "outputs", "corpus_backups", "extracted"),
    ]


@dataclass
class AxisARow:
    """One Axis-A scored row: a snapshot evidence row + an adjudicated relevance label.

    ``scored`` is True ONLY when a two-family adjudication record set this row's label.
    Keyword-proposed-but-unadjudicated rows carry ``scored=False`` and are excluded from AUC.
    """

    slug: str
    evidence_id: str
    text: str
    proposed_label: str  # "pos" | "neg" from the keyword seam (PROPOSAL ONLY)
    adjudicated_label: Optional[str] = None  # "pos" | "neg" set by two-family adjudication
    scored: bool = False
    adjudication_source: str = ""  # which family pair / record set the label

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "evidence_id": self.evidence_id,
            "text": self.text,
            "proposed_label": self.proposed_label,
            "adjudicated_label": self.adjudicated_label,
            "scored": self.scored,
            "adjudication_source": self.adjudication_source,
        }


@dataclass
class AxisBPair:
    """One Axis-B (rubric-claim -> non-lexically-overlapping supporting source) pair."""

    slug: str
    claim_id: str
    claim_text: str
    supporting_evidence_id: str
    supporting_text: str
    lexical_overlap: float
    adjudicated: bool = False  # two-family confirmed the support relation
    adjudication_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "supporting_evidence_id": self.supporting_evidence_id,
            "supporting_text": self.supporting_text,
            "lexical_overlap": round(self.lexical_overlap, 4),
            "adjudicated": self.adjudicated,
            "adjudication_source": self.adjudication_source,
        }


@dataclass
class EmbedderFixture:
    """The full labeled fixture: scored Axis-A rows (per question) + scored Axis-B pairs."""

    axis_a_rows: list[AxisARow] = field(default_factory=list)
    axis_b_pairs: list[AxisBPair] = field(default_factory=list)
    questions: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def scored_axis_a(self) -> list[AxisARow]:
        return [r for r in self.axis_a_rows if r.scored]

    def scored_axis_b(self) -> list[AxisBPair]:
        return [p for p in self.axis_b_pairs if p.adjudicated]

    def to_dict(self) -> dict[str, Any]:
        scored_a = self.scored_axis_a()
        scored_b = self.scored_axis_b()
        return {
            "questions": self.questions,
            "axis_a_rows": [r.to_dict() for r in self.axis_a_rows],
            "axis_b_pairs": [p.to_dict() for p in self.axis_b_pairs],
            "summary": {
                "axis_a_proposed": len(self.axis_a_rows),
                "axis_a_scored": len(scored_a),
                "axis_a_pos_scored": sum(1 for r in scored_a if r.adjudicated_label == "pos"),
                "axis_a_neg_scored": sum(1 for r in scored_a if r.adjudicated_label == "neg"),
                "axis_b_candidate_pairs": len(self.axis_b_pairs),
                "axis_b_scored_pairs": len(scored_b),
                "axis_b_overlap_ceiling": AXIS_B_LEXICAL_OVERLAP_CEILING,
            },
            "meta": self.meta,
        }


_WORD = re.compile(r"[a-z0-9]+")


def _content_words(text: str) -> set[str]:
    """Lowercased content tokens (length>=3) for the lexical-overlap (non-lexical) screen."""
    return {w for w in _WORD.findall((text or "").lower()) if len(w) >= 3}


def lexical_overlap(a: str, b: str) -> float:
    """Jaccard overlap of content words between two texts (0..1). Used for the Axis-B screen."""
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return 0.0
    inter = len(wa & wb)
    union = len(wa | wb)
    return inter / union if union else 0.0


def find_snapshot(slug: str, roots: list[str]) -> Optional[str]:
    """Locate a banked corpus_snapshot.json for a slug across the known layouts.

    Tries: <root>/<slug>/corpus_snapshot.json, <root>/<slug>_corpus_snapshot.json,
    and the bare-id form (<root>/<short>_corpus_snapshot.json). Returns the first hit or None.
    """
    short = "_".join(slug.split("_")[:2])  # e.g. drb_76
    candidates = []
    for root in roots:
        candidates.append(os.path.join(root, slug, "corpus_snapshot.json"))
        candidates.append(os.path.join(root, f"{slug}_corpus_snapshot.json"))
        candidates.append(os.path.join(root, f"{short}_corpus_snapshot.json"))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _load_snapshot(path: str) -> tuple[str, list[dict[str, Any]]]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    rows = data.get("evidence_for_gen") or data.get("evidence") or []
    return data.get("question", ""), rows


def _row_id(row: dict[str, Any], fallback_index: int) -> str:
    return str(row.get("evidence_id") or row.get("id") or f"row_{fallback_index}")


def _load_adjudication(path: str) -> dict[str, dict[str, Any]]:
    """Load a two-family adjudication side file (jsonl). Returns {key -> record}.

    The record sets the SCORED label. Missing file -> {} (rows then remain unscored / excluded;
    fail loud only when --require-adjudication is set in main()).
    """
    out: dict[str, dict[str, Any]] = {}
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            key = rec.get("key")
            if key:
                out[str(key)] = rec
    return out


def build_axis_a(
    seam: dict[str, Any],
    slugs: list[str],
    snapshot_roots: list[str],
    adjudication: dict[str, dict[str, Any]],
    max_per_class: int,
) -> tuple[list[AxisARow], dict[str, str]]:
    """Propose Axis-A rows from keywords, then attach two-family adjudicated labels."""
    label_sets = seam["LABEL_SETS"]
    label_rows = seam["label_rows"]
    rtext = seam["rtext"]

    rows: list[AxisARow] = []
    questions: dict[str, str] = {}
    for slug in slugs:
        if slug not in label_sets:
            continue
        snap = find_snapshot(slug, snapshot_roots)
        if not snap:
            # Honest: a missing snapshot is recorded, never faked. The slug contributes nothing.
            continue
        question, raw = _load_snapshot(snap)
        questions[slug] = question
        pos, neg = label_rows(raw, label_sets[slug])
        pos = pos[:max_per_class]
        neg = neg[:max_per_class]

        for proposed, group in (("pos", pos), ("neg", neg)):
            for i, r in enumerate(group):
                eid = _row_id(r, i)
                key = f"axis_a::{slug}::{eid}"
                rec = adjudication.get(key)
                adj_label = rec.get("label") if rec else None
                src = rec.get("source", "") if rec else ""
                rows.append(
                    AxisARow(
                        slug=slug,
                        evidence_id=eid,
                        text=rtext(r),
                        proposed_label=proposed,
                        adjudicated_label=adj_label,
                        # scored ONLY if two-family adjudication set a {pos,neg} label.
                        scored=adj_label in ("pos", "neg"),
                        adjudication_source=src,
                    )
                )
    return rows, questions


def build_axis_b(
    seam: dict[str, Any],
    slugs: list[str],
    snapshot_roots: list[str],
    adjudication: dict[str, dict[str, Any]],
    overlap_ceiling: float,
    max_claims_per_slug: int = AXIS_B_MAX_CLAIMS_PER_SLUG,
    max_candidates_per_claim: int = AXIS_B_MAX_CANDIDATES_PER_CLAIM,
) -> list[AxisBPair]:
    """Build candidate (claim -> non-lexically-overlapping supporting source) pairs.

    The CLAIM text is taken from a snapshot row's ``statement`` and the SUPPORTING body from a
    *different* row's ``direct_quote``/body; a pair is a CANDIDATE only if its lexical overlap is
    below the pre-registered ceiling. A candidate becomes a SCORED pair only when the two-family
    adjudication file confirms the support relation (``adjudicated=True``). No adjudication ->
    candidate stays unscored (honest; never auto-confirmed by a string heuristic).

    BOUNDED generation (pre-registered): at most ``max_claims_per_slug`` claims and
    ``max_candidates_per_claim`` candidate bodies per claim — the brief's dedup-§5 "stratified
    with a stated bound, not exhaustive C(N,2)" rule, applied so this is deterministic and does
    not blow up O(N^2) on a ~600-row snapshot. The bound is on the CANDIDATE set only.
    """
    rtext = seam["rtext"]
    pairs: list[AxisBPair] = []
    for slug in slugs:
        snap = find_snapshot(slug, snapshot_roots)
        if not snap:
            continue
        _question, raw = _load_snapshot(snap)
        # Claims = rows that carry a non-trivial 'statement'; supports = the body of other rows.
        bodies = [(i, _row_id(r, i), rtext(r)) for i, r in enumerate(raw)]
        claims_emitted = 0
        for i, r in enumerate(raw):
            if claims_emitted >= max_claims_per_slug:
                break
            claim = str(r.get("statement") or "").strip()
            if len(claim) < 40:
                continue
            cid = _row_id(r, i)
            cand_emitted = 0
            for j, eid, body in bodies:
                if cand_emitted >= max_candidates_per_claim:
                    break
                if j == i or len(body) < 60:
                    continue
                ov = lexical_overlap(claim, body)
                if ov > overlap_ceiling:
                    continue  # too lexically similar -> not a non-lexical reasoning pair
                cand_emitted += 1
                key = f"axis_b::{slug}::{cid}::{eid}"
                rec = adjudication.get(key)
                pairs.append(
                    AxisBPair(
                        slug=slug,
                        claim_id=cid,
                        claim_text=claim,
                        supporting_evidence_id=eid,
                        supporting_text=body,
                        lexical_overlap=ov,
                        adjudicated=bool(rec and rec.get("supports") is True),
                        adjudication_source=(rec.get("source", "") if rec else ""),
                    )
                )
            if cand_emitted > 0:
                claims_emitted += 1
    return pairs


def build_fixture(
    slugs: Optional[list[str]] = None,
    snapshot_roots: Optional[list[str]] = None,
    adjudication_dir: Optional[str] = None,
    max_per_class: int = 60,
) -> EmbedderFixture:
    """Build the full embedder fixture (Axis A + Axis B) from banked snapshots + adjudication."""
    seam = _import_label_sets()
    repo_root = seam["_repo_root"]
    if slugs is None:
        slugs = list(seam["LABEL_SETS"].keys())
    snapshot_roots = snapshot_roots or default_snapshot_roots(repo_root)
    adjudication_dir = adjudication_dir or os.path.join(_THIS_DIR, "fixture_adjudication")

    adj_a = _load_adjudication(os.path.join(adjudication_dir, "axis_a_adjudication.jsonl"))
    adj_b = _load_adjudication(os.path.join(adjudication_dir, "axis_b_adjudication.jsonl"))

    axis_a_rows, questions = build_axis_a(seam, slugs, snapshot_roots, adj_a, max_per_class)
    axis_b_pairs = build_axis_b(
        seam, slugs, snapshot_roots, adj_b, AXIS_B_LEXICAL_OVERLAP_CEILING
    )

    fixture = EmbedderFixture(
        axis_a_rows=axis_a_rows,
        axis_b_pairs=axis_b_pairs,
        questions=questions,
        meta={
            "repo_root": repo_root,
            "snapshot_roots": snapshot_roots,
            "adjudication_dir": adjudication_dir,
            "axis_b_overlap_ceiling": AXIS_B_LEXICAL_OVERLAP_CEILING,
            "slugs": slugs,
            "label_policy": (
                "keywords PROPOSE rows; the SCORED label is set ONLY by a two-family "
                "(Claude+Codex) adjudication record + operator sample spot-check. "
                "Unadjudicated rows are excluded from scoring (never keyword-scored)."
            ),
        },
    )
    return fixture


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Build embedder_late_interaction labeled fixture")
    ap.add_argument("--slugs", default="", help="comma-separated slugs (default: all LABEL_SETS)")
    ap.add_argument("--snapshot-roots", default="", help="comma-separated snapshot root dirs")
    ap.add_argument("--adjudication-dir", default="", help="dir with axis_*_adjudication.jsonl")
    ap.add_argument("--max-per-class", type=int, default=60)
    ap.add_argument("--out", default="", help="write fixture JSON here (default: stdout summary)")
    ap.add_argument(
        "--require-adjudication",
        action="store_true",
        help="FAIL LOUD if no scored Axis-A rows exist (adjudication file missing) — for the "
        "real build on the GPU box, never for the offline smoke",
    )
    args = ap.parse_args()

    slugs = [s for s in args.slugs.split(",") if s.strip()] or None
    roots = [s for s in args.snapshot_roots.split(",") if s.strip()] or None
    adj_dir = args.adjudication_dir or None

    fixture = build_fixture(
        slugs=slugs,
        snapshot_roots=roots,
        adjudication_dir=adj_dir,
        max_per_class=args.max_per_class,
    )
    summary = fixture.to_dict()["summary"]
    print(json.dumps(summary, indent=2))

    if args.require_adjudication and summary["axis_a_scored"] == 0:
        raise FixtureBuildError(
            "no SCORED Axis-A rows — the two-family adjudication file is missing or empty. "
            "Keyword proposals are NOT scored labels (brief iter-2 P1). Provide "
            "axis_a_adjudication.jsonl before the real run, or run without "
            "--require-adjudication for offline inspection."
        )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(fixture.to_dict(), handle, indent=2)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
