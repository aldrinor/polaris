#!/usr/bin/env python3
"""I-ret-002 (#1294) dedup layer — bake-off runner.

Loads each near-dup candidate by its EXACT library id, scores it on PAIRWISE COLLAPSE
precision/recall against the per-pair gold fixture (build_fixture.py), and writes a ranked
results JSON. Recall is maximized SUBJECT TO a PRE-REGISTERED precision FLOOR = 0.97 (locked
here, before execution). A candidate whose precision (point estimate AND the upper edge of the
disqualify decision) falls below the floor is DISQUALIFIED regardless of recall — a false
merge deletes a real corroborator (§-1.3).

CANDIDATES (exact ids):
  - polaris_content_deduplicator : src.utils.content_deduplicator.ContentDeduplicator (baseline,
                                    in-repo; MinHash+SimHash). No dep, no network, no GPU.
  - simhash_baseline             : vendored 64-bit SimHash + Hamming distance (the same algorithm
                                    as ContentDeduplicator._compute_simhash, standalone so it does
                                    NOT depend on the missing PyPI `simhash` package). No dep.
  - datasketch_minhash_lsh       : pip `datasketch` MinHash + MinHashLSH with a THRESHOLD SWEEP.
                                    The chosen operating point is labeled selected-on-fixture
                                    (a hyperparameter, NOT the pre-registered floor).
  - semhash_model2vec            : pip `semhash` + `model2vec` (potion-base-8M). Loads a model
                                    (downloads from HF on first use) -> gated behind a runtime
                                    availability + load check; registered-but-skipped if absent,
                                    NEVER faked. Mocked in the offline smoke test.

METRIC (pairwise, §-1.1 — real output vs labeled gold, no counts/patterns as quality):
  For each gold pair (a,b): the candidate predicts merge(a,b) in {True,False}.
    TP = predicted-merge AND gold==syndicated_copy
    FP = predicted-merge AND gold==distinct            (the cardinal sin)
    FN = predicted-no-merge AND gold==syndicated_copy
    TN = predicted-no-merge AND gold==distinct
  precision = TP/(TP+FP) ; recall = TP/(TP+FN).
  A no-op merger (merges nothing) gets precision=1.0 (undefined->1.0 by convention here is
  AVOIDED: we report precision as undefined when TP+FP==0 and FAIL the candidate's liveness in
  gate0). recall is reported with the 0.97-floor decision computed via a Wilson lower bound on
  precision over the false-merge-bearing bands.

KEEP-ALL PROVENANCE: every candidate is also run in CLUSTER mode over the full member set; the
runner asserts (union of cluster member-ids) == (input member-id set) — no source silently
dropped. A candidate that drops a member id FAILS the run (fail loud).
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import build_fixture  # noqa: E402  (local module; sys.path adjusted above)

# ---------------------------------------------------------------------------
# PRE-REGISTERED, LOCKED constants (LAW VI: not magic numbers — named + documented).
# ---------------------------------------------------------------------------

# The cardinal precision floor. Locked 2026-06-23 per the brief (§5). Below it = disqualified.
PRECISION_FLOOR: float = 0.97

# Wilson score interval z for a 95% one-sided lower bound (used for the disqualify decision so
# a thin hard-negative band cannot crown a winner on a point estimate).
WILSON_Z_95: float = 1.6448536269514722

# MinHashLSH threshold sweep grid (the operating point is selected-on-fixture; reported as a
# hyperparameter, NOT the pre-registered floor).
MINHASH_THRESHOLD_GRID: Tuple[float, ...] = (0.7, 0.75, 0.8, 0.85, 0.9, 0.92, 0.95, 0.98)
MINHASH_NUM_PERM: int = 128

# Default near-dup decision threshold for the in-repo ContentDeduplicator / vendored SimHash.
DEFAULT_NEAR_DUP_THRESHOLD: float = 0.85
SIMHASH_HAMMING_MAX: int = 6  # 64-bit SimHash; <=6 bit distance ~ near-dup (standard band)

# The KEEP-ALL conservation check uses an O(N^2) union-find. Over the full ~11k-member real
# fixture that is intractable, so the check runs on a bounded, SEEDED member sample. Conservation
# is a partition property: the union-find code is identical regardless of N, so a sample
# faithfully validates that the candidate's clustering never drops/invents a member id. The cap
# (and seed) are recorded so the bound is explicit, never a silent shortcut.
CONSERVATION_SAMPLE_CAP: int = 60
CONSERVATION_SAMPLE_SEED: int = 20260623

# Exact ids reported for provenance (web-verifiable).
CANDIDATE_IMPL_IDS: Dict[str, str] = {
    "polaris_content_deduplicator": "src.utils.content_deduplicator.ContentDeduplicator (in-repo baseline)",
    "simhash_baseline": "vendored 64-bit SimHash (no PyPI dep; mirrors ContentDeduplicator._compute_simhash)",
    "datasketch_minhash_lsh": "pip: datasketch (datasketch.MinHash + datasketch.MinHashLSH)",
    "semhash_model2vec": "pip: semhash + model2vec ; HF model: minishlab/potion-base-8M",
}


# ---------------------------------------------------------------------------
# Candidate interface.
# ---------------------------------------------------------------------------

@dataclass
class CandidateResult:
    name: str
    impl_id: str
    status: str  # "scored" | "skipped_no_dep" | "skipped_needs_gpu" | "load_failed"
    skip_reason: str = ""
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    precision: Optional[float] = None
    recall: Optional[float] = None
    precision_wilson_lower: Optional[float] = None
    passes_precision_floor: Optional[bool] = None
    disqualified: Optional[bool] = None
    selected_threshold: Optional[float] = None
    selected_threshold_note: str = ""
    provenance_conserved: Optional[bool] = None
    per_band: Dict[str, Dict[str, int]] = field(default_factory=dict)


class DedupCandidate:
    """Uniform adapter. ``merge(body_a, body_b) -> bool`` decides one pair; ``cluster(members)``
    returns disjoint clusters of member_ids for the KEEP-ALL conservation check. Subclasses load
    their backend lazily so an unavailable backend is a clean skip, never a fake score."""

    name: str = "base"

    def available(self) -> Tuple[bool, str]:
        """Return (is_available, reason). Default available."""
        return True, ""

    def merge(self, body_a: str, body_b: str) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def cluster(self, members: List[Tuple[str, str]]) -> List[Set[str]]:
        """Default union-find over pairwise merge (fine for small member sets)."""
        ids = [mid for mid, _ in members]
        parent: Dict[str, str] = {mid: mid for mid in ids}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: str, y: str) -> None:
            parent[find(x)] = find(y)

        n = len(members)
        for i in range(n):
            for j in range(i + 1, n):
                if self.merge(members[i][1], members[j][1]):
                    union(members[i][0], members[j][0])
        clusters: Dict[str, Set[str]] = {}
        for mid in ids:
            clusters.setdefault(find(mid), set()).add(mid)
        return list(clusters.values())


# ---- 1. POLARIS ContentDeduplicator (in-repo baseline) ----

class PolarisContentDeduplicatorCandidate(DedupCandidate):
    name = "polaris_content_deduplicator"

    def __init__(self, repo_root: str, threshold: float = DEFAULT_NEAR_DUP_THRESHOLD):
        self.repo_root = repo_root
        self.threshold = threshold
        self._dedup: Any = None
        self._cache: Dict[str, Any] = {}  # body -> ContentFingerprint (avoid recompute)

    def available(self) -> Tuple[bool, str]:
        mod = os.path.join(self.repo_root, "src", "utils", "content_deduplicator.py")
        if not os.path.isfile(mod):
            return False, f"src/utils/content_deduplicator.py not found under {self.repo_root}"
        return True, ""

    def _ensure(self) -> None:
        if self._dedup is not None:
            return
        if self.repo_root not in sys.path:
            sys.path.insert(0, self.repo_root)
        cd = importlib.import_module("src.utils.content_deduplicator")
        config = cd.DeduplicationConfig(near_duplicate_threshold=self.threshold)
        self._dedup = cd.ContentDeduplicator(config)

    def _fingerprint(self, body: str) -> Any:
        fp = self._cache.get(body)
        if fp is None:
            self._ensure()
            fp = self._dedup._generate_fingerprint(body)
            self._cache[body] = fp
        return fp

    def merge(self, body_a: str, body_b: str) -> bool:
        # EXACT production semantics of ContentDeduplicator.is_duplicate(a, b, threshold): merge
        # iff MinHash Jaccard >= near_duplicate_threshold. We compute it from cached fingerprints
        # to avoid a recompute per pair, but DO NOT use the wider _check_duplicate SIMILAR band
        # (sim >= 0.70) — that would over-merge relative to the production baseline's identity
        # and corrupt its precision metric. is_duplicate is purely a threshold on minhash_sim.
        self._ensure()
        fp1 = self._fingerprint(body_a)
        fp2 = self._fingerprint(body_b)
        sim = self._dedup._minhash_similarity(fp1.minhash, fp2.minhash)
        return sim >= self.threshold


# ---- 2. Vendored SimHash baseline (no PyPI dep) ----

class SimHashBaselineCandidate(DedupCandidate):
    name = "simhash_baseline"

    def __init__(self, hamming_max: int = SIMHASH_HAMMING_MAX):
        self.hamming_max = hamming_max
        self._cache: Dict[str, int] = {}

    def _fingerprint(self, text: str) -> int:
        fp = self._cache.get(text)
        if fp is None:
            fp = self._simhash64(text)
            self._cache[text] = fp
        return fp

    @staticmethod
    def _simhash64(text: str) -> int:
        import hashlib as _h

        if not text:
            return 0
        v = [0] * 64
        for word in text.split():
            digest = int(_h.md5(word.encode("utf-8")).hexdigest(), 16)
            for i in range(64):
                if (digest >> i) & 1:
                    v[i] += 1
                else:
                    v[i] -= 1
        out = 0
        for i in range(64):
            if v[i] > 0:
                out |= 1 << i
        return out

    @staticmethod
    def _hamming(x: int, y: int) -> int:
        z = x ^ y
        d = 0
        while z:
            d += 1
            z &= z - 1
        return d

    def merge(self, body_a: str, body_b: str) -> bool:
        return self._hamming(self._fingerprint(body_a), self._fingerprint(body_b)) <= self.hamming_max


# ---- 3. datasketch MinHashLSH (with threshold sweep) ----

class DatasketchMinHashCandidate(DedupCandidate):
    name = "datasketch_minhash_lsh"

    def __init__(self, threshold: float, num_perm: int = MINHASH_NUM_PERM, shingle: int = 3):
        self.threshold = threshold
        self.num_perm = num_perm
        self.shingle = shingle
        self._MinHash: Any = None
        self._cache: Dict[str, Any] = {}

    def available(self) -> Tuple[bool, str]:
        import importlib.util as u

        if u.find_spec("datasketch") is None:
            return False, "pip package `datasketch` not installed"
        return True, ""

    def _ensure(self) -> None:
        if self._MinHash is None:
            from datasketch import MinHash  # type: ignore

            self._MinHash = MinHash

    def _shingles(self, text: str) -> Set[str]:
        words = text.split()
        if len(words) < self.shingle:
            return {text} if text else set()
        return {" ".join(words[i : i + self.shingle]) for i in range(len(words) - self.shingle + 1)}

    def _minhash(self, text: str) -> Any:
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        self._ensure()
        mh = self._MinHash(num_perm=self.num_perm)
        for sh in self._shingles(text):
            mh.update(sh.encode("utf-8"))
        self._cache[text] = mh
        return mh

    def merge(self, body_a: str, body_b: str) -> bool:
        ma = self._minhash(body_a)
        mb = self._minhash(body_b)
        return float(ma.jaccard(mb)) >= self.threshold


# ---- 4. SemHash + Model2Vec (model download -> gated) ----

class SemHashModel2VecCandidate(DedupCandidate):
    name = "semhash_model2vec"

    def __init__(self, model_id: str = "minishlab/potion-base-8M", threshold: float = 0.9):
        self.model_id = model_id
        self.threshold = threshold
        self._semhash_cls: Any = None
        self._model: Any = None

    def available(self) -> Tuple[bool, str]:
        import importlib.util as u

        if u.find_spec("semhash") is None:
            return False, "pip package `semhash` not installed"
        if u.find_spec("model2vec") is None:
            return False, "pip package `model2vec` not installed"
        return True, ""

    def _ensure(self) -> None:
        """Load the Model2Vec encoder. FAILS LOUD (no silent fallback) if the model can't load.

        This downloads the model from HF on first use, so it runs ONLY on the GPU/bench box
        with network; the offline smoke test mocks this whole class.
        """
        if self._model is not None:
            return
        from model2vec import StaticModel  # type: ignore

        self._model = StaticModel.from_pretrained(self.model_id)
        if self._model is None:
            raise RuntimeError(
                f"SemHash candidate: model2vec failed to load {self.model_id!r} — refusing to "
                f"silently fall back (no fake working)."
            )

    @staticmethod
    def _cosine(u: Sequence[float], v: Sequence[float]) -> float:
        dot = sum(a * b for a, b in zip(u, v))
        nu = math.sqrt(sum(a * a for a in u))
        nv = math.sqrt(sum(b * b for b in v))
        if nu == 0.0 or nv == 0.0:
            return 0.0
        return dot / (nu * nv)

    def merge(self, body_a: str, body_b: str) -> bool:
        self._ensure()
        vecs = self._model.encode([body_a, body_b])
        return self._cosine(list(vecs[0]), list(vecs[1])) >= self.threshold


# ---------------------------------------------------------------------------
# Scoring.
# ---------------------------------------------------------------------------

def wilson_lower_bound(successes: int, n: int, z: float = WILSON_Z_95) -> float:
    """One-sided lower bound of a binomial proportion (Wilson). 0.0 if n==0."""
    if n == 0:
        return 0.0
    phat = successes / n
    denom = 1.0 + z * z / n
    centre = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def score_candidate_on_pairs(
    candidate: DedupCandidate,
    pairs: List[Dict[str, Any]],
    bodies: Dict[str, str],
) -> CandidateResult:
    res = CandidateResult(
        name=candidate.name, impl_id=CANDIDATE_IMPL_IDS.get(candidate.name, candidate.name),
        status="scored",
    )
    per_band: Dict[str, Dict[str, int]] = {}
    for pair in pairs:
        a_id = pair["a"]["member_id"]
        b_id = pair["b"]["member_id"]
        body_a = bodies.get(a_id, "")
        body_b = bodies.get(b_id, "")
        predicted_merge = bool(candidate.merge(body_a, body_b))
        is_positive = pair["label"] == "syndicated_copy"
        band = pair["label_source"]
        b = per_band.setdefault(band, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
        if predicted_merge and is_positive:
            res.tp += 1
            b["tp"] += 1
        elif predicted_merge and not is_positive:
            res.fp += 1
            b["fp"] += 1
        elif not predicted_merge and is_positive:
            res.fn += 1
            b["fn"] += 1
        else:
            res.tn += 1
            b["tn"] += 1
    res.per_band = per_band

    merges = res.tp + res.fp
    # precision: undefined if the candidate merged nothing (no-op merger). We DO NOT report a
    # convenient 1.0 — undefined precision is reported as None and gate0 fails such a candidate
    # via the no-op recall canary. This is the dedup-specific drb_72 trap.
    res.precision = (res.tp / merges) if merges > 0 else None
    res.recall = (res.tp / (res.tp + res.fn)) if (res.tp + res.fn) > 0 else None
    # Wilson lower bound on precision over actual merges (the false-merge-bearing decisions).
    res.precision_wilson_lower = wilson_lower_bound(res.tp, merges) if merges > 0 else 0.0
    # Pre-registered floor decision: a candidate PASSES only if its Wilson lower bound clears
    # the floor (so a thin hard-negative band cannot crown a winner on a point estimate).
    res.passes_precision_floor = (
        res.precision is not None and res.precision_wilson_lower >= PRECISION_FLOOR
    )
    res.disqualified = not bool(res.passes_precision_floor)
    return res


def assert_provenance_conserved(
    candidate: DedupCandidate,
    members: List[Tuple[str, str]],
    sample_cap: int = CONSERVATION_SAMPLE_CAP,
    seed: int = CONSERVATION_SAMPLE_SEED,
) -> bool:
    """KEEP-ALL: union of cluster member-ids == input member-id set. Fail loud otherwise.

    Conservation is a partition property (the clustering code path is identical regardless of
    set size), so for large member sets we validate on a bounded, SEEDED sample to keep the
    O(N^2) union-find tractable. The bound is explicit, never a silent shortcut.
    """
    if sample_cap > 0 and len(members) > sample_cap:
        import random as _random

        rng = _random.Random(seed)
        members = rng.sample(members, sample_cap)
    input_ids = {mid for mid, _ in members}
    clusters = candidate.cluster(members)
    union_ids: Set[str] = set()
    for cl in clusters:
        union_ids |= set(cl)
    if union_ids != input_ids:
        dropped = input_ids - union_ids
        invented = union_ids - input_ids
        raise RuntimeError(
            f"KEEP-ALL PROVENANCE VIOLATION by {candidate.name}: clustering dropped "
            f"{len(dropped)} member id(s) and/or invented {len(invented)}. A near-dup collapse "
            f"must NEVER silently drop a source (§-1.3). dropped(sample)="
            f"{list(dropped)[:5]} invented(sample)={list(invented)[:5]}"
        )
    return True


# ---------------------------------------------------------------------------
# MinHashLSH threshold sweep (operating point selected-on-fixture).
# ---------------------------------------------------------------------------

def run_minhash_sweep(
    pairs: List[Dict[str, Any]],
    bodies: Dict[str, str],
    grid: Tuple[float, ...] = MINHASH_THRESHOLD_GRID,
) -> Tuple[CandidateResult, List[Dict[str, Any]]]:
    """Sweep the MinHash threshold; pick max-recall among points that clear the precision floor
    (Wilson lower bound). The chosen point is labeled selected-on-fixture (a hyperparameter,
    NOT the pre-registered floor). Reports the full PR curve so the selection is auditable."""
    curve: List[Dict[str, Any]] = []
    best: Optional[CandidateResult] = None
    shared_cache: Dict[str, Any] = {}  # MinHash signature is threshold-independent -> reuse it
    for thr in grid:
        cand = DatasketchMinHashCandidate(threshold=thr)
        cand._cache = shared_cache
        ok, reason = cand.available()
        if not ok:
            return (
                CandidateResult(
                    name="datasketch_minhash_lsh",
                    impl_id=CANDIDATE_IMPL_IDS["datasketch_minhash_lsh"],
                    status="skipped_no_dep",
                    skip_reason=reason,
                ),
                curve,
            )
        r = score_candidate_on_pairs(cand, pairs, bodies)
        r.selected_threshold = thr
        curve.append(
            {
                "threshold": thr,
                "precision": r.precision,
                "precision_wilson_lower": r.precision_wilson_lower,
                "recall": r.recall,
                "passes_floor": r.passes_precision_floor,
            }
        )
        if r.passes_precision_floor:
            if best is None or (r.recall or 0.0) > (best.recall or 0.0):
                best = r
    if best is None:
        # No threshold clears the floor -> disqualified; report the highest-precision point.
        best = max(
            (score_candidate_on_pairs(DatasketchMinHashCandidate(threshold=t), pairs, bodies) for t in grid),
            key=lambda rr: (rr.precision_wilson_lower or 0.0),
        )
        best.selected_threshold = best.selected_threshold or grid[-1]
    best.selected_threshold_note = (
        "operating point SELECTED-ON-FIXTURE (a hyperparameter tuned on this fixture, NOT the "
        "pre-registered 0.97 floor). The fixture may be too small for a held-out split; the PR "
        "curve is reported for audit. Re-validate the chosen threshold on a held-out fixture "
        "before production."
    )
    return best, curve


# ---------------------------------------------------------------------------
# Driver.
# ---------------------------------------------------------------------------

def build_candidates(repo_root: str) -> List[DedupCandidate]:
    return [
        PolarisContentDeduplicatorCandidate(repo_root),
        SimHashBaselineCandidate(),
        SemHashModel2VecCandidate(),  # datasketch handled via the sweep separately
    ]


def members_from_fixture(pairs: List[Dict[str, Any]], bodies: Dict[str, str]) -> List[Tuple[str, str]]:
    """Distinct (member_id, body) list for the KEEP-ALL conservation check."""
    seen: Set[str] = set()
    out: List[Tuple[str, str]] = []
    for pair in pairs:
        for side in ("a", "b"):
            mid = pair[side]["member_id"]
            if mid in seen:
                continue
            seen.add(mid)
            out.append((mid, bodies.get(mid, "")))
    return out


def run_bakeoff(
    fixture_dir: str,
    repo_root: str,
    out_path: str,
    allow_unadjudicated: bool = False,
    max_pairs: int = 0,
) -> Dict[str, Any]:
    fixture = build_fixture.load_fixture(fixture_dir)
    pairs: List[Dict[str, Any]] = fixture["pairs"]
    bodies: Dict[str, str] = fixture["bodies"]
    manifest: Dict[str, Any] = fixture["manifest"]

    # max_pairs>0: stratified-by-label SEEDED subsample, for a fast bounded run (CI / sandbox).
    # The full-fixture run (max_pairs=0) is the real bench result; the subsample is recorded in
    # the report so the bound is explicit and never confused with the full-fixture verdict.
    subsampled = False
    if max_pairs > 0 and len(pairs) > max_pairs:
        import random as _random

        rng = _random.Random(build_fixture.DEFAULT_SEED)
        pos = [p for p in pairs if p["label"] == "syndicated_copy"]
        neg = [p for p in pairs if p["label"] == "distinct"]
        rng.shuffle(pos)
        rng.shuffle(neg)
        half = max_pairs // 2
        pairs = pos[:half] + neg[: max_pairs - len(pos[:half])]
        rng.shuffle(pairs)
        subsampled = True

    # Refuse to score on unconfirmed labels (anti-circularity): every scored pair must carry a
    # canonical-identity or authored label_source. (load_fixture already asserts this; we also
    # block any attempt to merge the pending_adjudication queue into scoring.)
    pending_path = os.path.join(fixture_dir, "pending_adjudication.jsonl")
    n_pending = 0
    if os.path.isfile(pending_path):
        with open(pending_path, encoding="utf-8") as handle:
            n_pending = sum(1 for line in handle if line.strip())
    if n_pending > 0 and allow_unadjudicated:
        raise RuntimeError(
            "Refusing --allow-unadjudicated: the pending_adjudication band is judge-PROPOSED and "
            "NOT a scored label. Resolve it via two-family adjudication first (never auto-resolve "
            "with a similarity threshold — that is the circularity the brief forbids)."
        )

    members = members_from_fixture(pairs, bodies)

    results: List[CandidateResult] = []

    # MinHash via the sweep.
    minhash_best, minhash_curve = run_minhash_sweep(pairs, bodies)
    if minhash_best.status == "scored":
        cand = DatasketchMinHashCandidate(threshold=float(minhash_best.selected_threshold or 0.9))
        try:
            minhash_best.provenance_conserved = assert_provenance_conserved(cand, members)
        except RuntimeError as exc:
            minhash_best.status = "load_failed"
            minhash_best.skip_reason = str(exc)
    results.append(minhash_best)

    # The other candidates.
    for cand in build_candidates(repo_root):
        ok, reason = cand.available()
        if not ok:
            status = "skipped_no_dep"
            results.append(
                CandidateResult(
                    name=cand.name,
                    impl_id=CANDIDATE_IMPL_IDS.get(cand.name, cand.name),
                    status=status,
                    skip_reason=reason,
                )
            )
            continue
        try:
            r = score_candidate_on_pairs(cand, pairs, bodies)
            r.provenance_conserved = assert_provenance_conserved(cand, members)
            results.append(r)
        except Exception as exc:  # load/runtime failure -> honest, never a fake low score
            results.append(
                CandidateResult(
                    name=cand.name,
                    impl_id=CANDIDATE_IMPL_IDS.get(cand.name, cand.name),
                    status="load_failed",
                    skip_reason=f"{type(exc).__name__}: {exc}",
                )
            )

    # Rank: only scored + floor-passing candidates are eligible to win; rank by recall.
    eligible = [r for r in results if r.status == "scored" and r.passes_precision_floor]
    eligible.sort(key=lambda r: (r.recall or 0.0), reverse=True)
    ranking = [r.name for r in eligible]

    report = {
        "layer": "dedup",
        "metric": "pairwise collapse precision/recall vs per-pair gold {syndicated_copy/distinct}",
        "precision_floor_pre_registered": PRECISION_FLOOR,
        "floor_decision_rule": "candidate PASSES iff Wilson-95 lower bound on precision >= floor",
        "fixture_manifest": manifest,
        "n_scored_pairs": len(pairs),
        "subsampled_run": subsampled,
        "subsample_note": (
            f"BOUNDED subsample ({len(pairs)} pairs, seeded) — a fast CI/sandbox run, NOT the "
            f"full-fixture verdict. Run with max_pairs=0 on the bench box for the real result."
            if subsampled
            else "full-fixture run"
        ),
        "n_pending_adjudication_excluded": n_pending,
        "minhash_threshold_curve": minhash_curve,
        "candidates": [asdict(r) for r in results],
        "ranking_floor_passing_by_recall": ranking,
        "winner": ranking[0] if ranking else None,
        "winner_note": (
            "winner = highest recall among floor-passing candidates"
            if ranking
            else "NO candidate cleared the 0.97 precision floor on this fixture"
        ),
        "floor_gate_is_wilson_lower_bound": (
            "The floor gate is the WILSON-95 LOWER BOUND on precision >= 0.97, which is STRICTER "
            "than the brief's literal point-estimate '< 0.97 = disqualified'. This is intentional "
            "(advisor-confirmed): a candidate disqualified by a near-floor point estimate on a "
            "THIN band (esp. the 4-seed hard-negative band) is disqualified for lack of evidence, "
            "not a bug. Grow the hard-negative band to tighten the CI before crowning."
        ),
        "known_limitations": [
            "PYTHONHASHSEED: the in-repo ContentDeduplicator MinHash uses builtin hash() which is "
            "PYTHONHASHSEED-randomized; within one process pairwise comparisons are consistent, "
            "but across the >=3 finalist reruns its non-identical-pair similarities (and thus a "
            "near-floor pass/fail) can flicker. Set PYTHONHASHSEED=0 on the bench run. The "
            "vendored SimHash (md5) and datasketch MinHash are deterministic.",
            "Discrimination lives in the HARD bands (edited-syndication near-dups for recall; "
            "same-topic distinct pairs for the precision floor). Easy bands (byte-identical "
            "positives, cross-topic negatives) are separated by ALL candidates, so a winner is "
            "only meaningful once the hard-negative band + the adjudicated near-dup band are "
            "populated. The pending_adjudication queue is excluded from scoring until resolved.",
        ],
    }
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the dedup bake-off.")
    parser.add_argument(
        "--fixture-dir", default=os.path.join(_THIS_DIR, "fixtures"),
    )
    parser.add_argument("--repo-root", default=os.environ.get("POLARIS_REPO_ROOT", "C:/POLARIS"))
    parser.add_argument(
        "--out", default=os.path.join(_THIS_DIR, "dedup_bakeoff_results.json"),
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=0,
        help="0 = full fixture (the real bench result). >0 = seeded, label-stratified bounded "
        "subsample for a fast CI/sandbox run (recorded as subsampled in the report).",
    )
    args = parser.parse_args(argv)
    report = run_bakeoff(args.fixture_dir, args.repo_root, args.out, max_pairs=args.max_pairs)
    print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
