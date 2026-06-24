#!/usr/bin/env python3
"""I-ret-002 (#1294) dedup layer — OFFLINE stub smoke test.

Proves, with NO GPU, NO network, NO model download, and synthetic data only:
  1. All four layer files py_compile.
  2. build_fixture builds a labeled PAIR fixture from SYNTHETIC evidence rows (no real
     snapshots needed) with correct canonical-identity labels + a non-empty pending queue +
     anti-circularity guard passing.
  3. run_bakeoff scores candidates; the no-op (never-merge) candidate is correctly NOT crowned
     (precision undefined, blocked by the floor) — the dedup-specific drb_72 trap.
  4. GATE-0 scorer-math + Wilson + floor canaries pass; the bidirectional liveness canary
     correctly PASSES a live candidate and correctly FAILS a simulated STUB (no-op) candidate
     and an over-merge stub.
  5. SemHash+Model2Vec is exercised with a MOCKED encoder (no HF download) and scores in the
     correct direction — proving the adapter is wired without hitting the network.
  6. KEEP-ALL provenance conservation holds for every live candidate.

Exit 0 on success; non-zero (fail loud) on any failure.
"""
from __future__ import annotations

import json
import os
import py_compile
import sys
import tempfile
from typing import Any, Dict, List

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import build_fixture  # noqa: E402
import gate0  # noqa: E402
import run_bakeoff  # noqa: E402

_FAILS: List[str] = []


def _check(cond: bool, label: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}")
    if not cond:
        _FAILS.append(label)


# ---------------------------------------------------------------------------
# 1. py_compile all four files.
# ---------------------------------------------------------------------------

def smoke_py_compile() -> None:
    print("[1] py_compile all four layer files")
    files = ["build_fixture.py", "run_bakeoff.py", "gate0.py", "smoke_test.py"]
    for f in files:
        path = os.path.join(_THIS_DIR, f)
        try:
            py_compile.compile(path, doraise=True)
            _check(True, f"py_compile {f}")
        except py_compile.PyCompileError as exc:
            _check(False, f"py_compile {f}: {exc}")


# ---------------------------------------------------------------------------
# 2. build_fixture on SYNTHETIC rows (no real snapshots).
# ---------------------------------------------------------------------------

def _synthetic_rows(slug: str, topic_body: str, n: int) -> List[Dict[str, Any]]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "evidence_id": f"{slug}_ev_{i}",
                "source_url": f"https://example.org/{slug}/{i}",
                "doi": "",
                "title": f"{slug} source {i}",
                "direct_quote": f"{topic_body} variant body number {i} with additional padding text "
                "to exceed the minimum body length threshold used by the fixture builder so it is "
                "an eligible discriminative member for the pair construction stage of the harness",
            }
        )
    return rows


def smoke_build_fixture() -> str:
    print("[2] build_fixture on synthetic members (offline, no snapshots)")
    out_dir = tempfile.mkdtemp(prefix="dedup_smoke_")
    # Two topics -> cross-topic negatives are guaranteed distinct.
    topic_a = (
        "deep brain stimulation of the subthalamic nucleus improved motor symptoms in advanced "
        "parkinson disease in a randomized controlled multicenter clinical trial over twelve months"
    )
    topic_b = (
        "magnesium selenium and zinc trace element status was associated with cardiovascular "
        "mortality in a large prospective cohort after adjustment for established coronary risk"
    )
    rows_a = _synthetic_rows("drb_a", topic_a, 8)
    rows_b = _synthetic_rows("drb_b", topic_b, 8)

    members_a = build_fixture.members_from_rows(rows_a, "drb_a", "runX")
    members_b = build_fixture.members_from_rows(rows_b, "drb_b", "runX")

    # Inject CANONICAL-IDENTITY positives:
    #  (a) same body, different url  -> canonical_body
    #  (b) same url re-fetched (different run), identical body -> canonical_url_refetch
    import copy

    dup_body_member = copy.deepcopy(members_a[0])
    dup_body_member.member_id = "drb_a::runX::dup_body"
    dup_body_member.evidence_id = "dup_body"
    dup_body_member.source_url = "https://example.org/drb_a/DIFFERENT"
    # body identical to members_a[0] -> canonical_body positive

    refetch_member = copy.deepcopy(members_a[1])
    refetch_member.member_id = "drb_a::runY::refetch"
    refetch_member.run_tag = "runY"
    # same source_url + identical body as members_a[1] -> canonical_url_refetch positive

    # An edited-syndication near-dup (same url, body DIFFERS) -> pending_adjudication (not scored)
    edited_member = copy.deepcopy(members_a[2])
    edited_member.member_id = "drb_a::runZ::edited"
    edited_member.run_tag = "runZ"
    edited_member.body = members_a[2].body + " trailing fetch jitter appended only in this run"
    edited_member.body_sha = build_fixture.sha256_text(edited_member.body)

    members_by_slug = {
        "drb_a": members_a + [dup_body_member, refetch_member, edited_member],
        "drb_b": members_b,
    }
    all_members = members_by_slug["drb_a"] + members_by_slug["drb_b"]

    import random

    rng = random.Random(build_fixture.DEFAULT_SEED)
    manifest = build_fixture.build_pairs_into_files(
        members_by_slug,
        all_members,
        out_dir,
        rng,
        build_fixture.DEFAULT_SEED,
        ("drb_a", "drb_b"),
        ["synthetic://drb_a", "synthetic://drb_b"],
        [],
    )
    _check(manifest.n_exact_positive_pairs >= 2, f"exact-positive pairs built (got {manifest.n_exact_positive_pairs})")
    _check(manifest.n_cross_topic_negative_pairs >= 1, f"cross-topic negatives built (got {manifest.n_cross_topic_negative_pairs})")
    _check(manifest.n_curated_hard_negative_pairs >= 4, f"curated hard-negatives present (got {manifest.n_curated_hard_negative_pairs})")
    _check(manifest.n_pending_adjudication >= 1, f"pending adjudication queue non-empty (got {manifest.n_pending_adjudication})")

    # Load + anti-circularity guard.
    fixture = build_fixture.load_fixture(out_dir)
    _check(len(fixture["pairs"]) == manifest.n_scored_pairs, "load_fixture round-trips pair count")
    label_sources = {p["label_source"] for p in fixture["pairs"]}
    _check(
        label_sources.issubset(set(build_fixture.VALID_LABEL_SOURCES)),
        f"every scored label_source is canonical/authored (anti-circularity): {sorted(label_sources)}",
    )
    # Tamper: a similarity-derived label_source must be REJECTED by the guard.
    bad = list(fixture["pairs"]) + [
        {"pair_id": "bad", "label": "syndicated_copy", "label_source": "minhash_ge_0.9"}
    ]
    rejected = False
    try:
        build_fixture.assert_no_circular_labels(bad)
    except ValueError:
        rejected = True
    _check(rejected, "anti-circularity guard REJECTS a similarity-derived label_source")
    return out_dir


# ---------------------------------------------------------------------------
# 3. run_bakeoff scoring + the no-op trap.
# ---------------------------------------------------------------------------

class _MockModel2Vec:
    """Offline stand-in for a Model2Vec StaticModel: a tiny deterministic bag-of-words
    embedding, no network, no torch. Proves the SemHash adapter is wired in the correct
    direction without a download."""

    _VOCAB = [
        "deep", "brain", "stimulation", "parkinson", "motor", "magnesium", "selenium",
        "cardiovascular", "mortality", "trial", "cohort", "trace", "element", "subthalamic",
    ]

    def encode(self, texts: List[str]) -> List[List[float]]:
        out = []
        for t in texts:
            toks = set((t or "").lower().split())
            out.append([1.0 if w in toks else 0.0 for w in self._VOCAB])
        return out


def smoke_run_bakeoff(fixture_dir: str) -> None:
    print("[3] run_bakeoff scoring + no-op trap (datasketch real if present, SemHash MOCKED)")
    out_path = os.path.join(fixture_dir, "results.json")

    # Mock the SemHash candidate's model loader so no HF download happens.
    orig_ensure = run_bakeoff.SemHashModel2VecCandidate._ensure

    def _mock_ensure(self: run_bakeoff.SemHashModel2VecCandidate) -> None:
        if self._model is None:
            self._model = _MockModel2Vec()

    run_bakeoff.SemHashModel2VecCandidate._ensure = _mock_ensure  # type: ignore[assignment]
    # Also mock availability so the smoke runs SemHash even if the packages are absent.
    orig_avail = run_bakeoff.SemHashModel2VecCandidate.available
    run_bakeoff.SemHashModel2VecCandidate.available = lambda self: (True, "")  # type: ignore[assignment]
    try:
        report = run_bakeoff.run_bakeoff(fixture_dir, repo_root="C:/POLARIS", out_path=out_path)
    finally:
        run_bakeoff.SemHashModel2VecCandidate._ensure = orig_ensure  # type: ignore[assignment]
        run_bakeoff.SemHashModel2VecCandidate.available = orig_avail  # type: ignore[assignment]

    _check(os.path.isfile(out_path), "results JSON written")
    by_name = {c["name"]: c for c in report["candidates"]}

    # SemHash (mocked) must have SCORED in the correct direction (identical positives -> merge).
    sem = by_name.get("semhash_model2vec")
    _check(sem is not None and sem["status"] == "scored", "SemHash(mocked) scored without network")
    if sem and sem["status"] == "scored":
        _check((sem.get("recall") or 0.0) > 0.0, f"SemHash(mocked) recall>0 (merges identical): {sem.get('recall')}")

    # The in-repo ContentDeduplicator is skipped offline (src/ not in this worktree) -> honest skip.
    pcd = by_name.get("polaris_content_deduplicator")
    _check(
        pcd is not None and pcd["status"] in ("scored", "skipped_no_dep"),
        f"ContentDeduplicator reported honestly (status={pcd['status'] if pcd else 'MISSING'})",
    )

    # REGRESSION GUARD: the cached ContentDeduplicator candidate.merge() MUST equal the
    # production is_duplicate(a, b, threshold) on EVERY pair, including a mid-band (~75%-edited)
    # body that lands between similar_threshold(0.70) and near_dup_threshold(0.85). This catches
    # the caching-refactor bug where _check_duplicate's SIMILAR band silently widened merges.
    cand = run_bakeoff.PolarisContentDeduplicatorCandidate("C:/POLARIS")
    if cand.available()[0]:
        import importlib as _il

        if "C:/POLARIS" not in sys.path:
            sys.path.insert(0, "C:/POLARIS")
        cd_mod = _il.import_module("src.utils.content_deduplicator")
        fresh = cd_mod.ContentDeduplicator(
            cd_mod.DeduplicationConfig(near_duplicate_threshold=cand.threshold)
        )
        base = (
            "deep brain stimulation of the subthalamic nucleus improved motor symptoms in "
            "advanced parkinson disease over a twelve month randomized controlled trial across "
            "several centers with sustained benefit on quality of life measures and reduced "
            "medication burden in the active stimulation arm relative to medical therapy"
        )
        words = base.split()
        edited_75 = " ".join(words[: int(len(words) * 0.75)])  # truncated -> mid-band overlap
        probe_pairs = [
            (base, base),  # identical
            (base, edited_75),  # mid band
            (base, "an entirely unrelated body about autonomous vehicle liability and tort law"),
        ]
        agree = all(
            cand.merge(a, b) == fresh.is_duplicate(a, b, threshold=cand.threshold)
            for a, b in probe_pairs
        )
        _check(agree, "ContentDeduplicator candidate.merge == production is_duplicate (incl mid-band)")

    # SimHash baseline (no dep) must have scored.
    sh = by_name.get("simhash_baseline")
    _check(sh is not None and sh["status"] == "scored", "vendored SimHash baseline scored (no dep)")

    # Every scored candidate that passed the floor must have conserved provenance.
    for c in report["candidates"]:
        if c["status"] == "scored":
            _check(c["provenance_conserved"] is True, f"{c['name']} KEEP-ALL provenance conserved")


# ---------------------------------------------------------------------------
# 4. GATE-0 canaries + the simulated-stub liveness failure.
# ---------------------------------------------------------------------------

def smoke_gate0() -> None:
    print("[4] GATE-0: scorer-math passes; liveness FAILS a simulated stub")
    # Scorer-math + Wilson + floors.
    sm = gate0.check_scorer_math()
    _check(sm.passed, f"GATE-0 scorer_math_canary passes: {sm.detail}")
    wm = gate0.check_wilson_math()
    _check(wm.passed, f"GATE-0 wilson_math_canary passes: {wm.detail}")
    for fc in gate0.check_floors_bite():
        _check(fc.passed, f"GATE-0 {fc.name} passes: {fc.detail}")

    # Liveness must PASS the correct-direction reference stub.
    ref_live = gate0.check_candidate_liveness(gate0._ExactOnlyStub())
    _check(ref_live.passed, f"GATE-0 liveness PASSES correct candidate: {ref_live.detail}")

    # CRITICAL: liveness must FAIL the no-op (never-merge) stub — the drb_72 trap.
    noop_live = gate0.check_candidate_liveness(gate0._NeverMergeStub())
    _check(not noop_live.passed, f"GATE-0 liveness FAILS the no-op stub (drb_72 trap killed): {noop_live.detail}")

    # And must FAIL an over-merge stub.
    over_live = gate0.check_candidate_liveness(gate0._AlwaysMergeStub())
    _check(not over_live.passed, f"GATE-0 liveness FAILS the over-merge stub: {over_live.detail}")

    # A candidate that RAISES on a control pair is a liveness FAIL (dead), not a skip.
    class _RaisingStub(run_bakeoff.DedupCandidate):
        name = "stub_raises"

        def merge(self, body_a: str, body_b: str) -> bool:
            raise RuntimeError("simulated load failure")

    raise_live = gate0.check_candidate_liveness(_RaisingStub())
    _check(not raise_live.passed, f"GATE-0 liveness FAILS a raising/dead stub: {raise_live.detail}")

    # Full gate run: inject a no-op stub as an extra candidate -> the whole gate must report FAIL.
    rep = gate0.run_gate0(repo_root="C:/POLARIS", extra_candidates=[gate0._NeverMergeStub()])
    _check(rep.all_passed is False, "full GATE-0 with an injected no-op stub returns all_passed=False")

    # Full gate run WITHOUT a bad stub: the backend-independent canaries must all pass (real
    # backends may be skipped offline, but no enabled check should FAIL).
    rep_clean = gate0.run_gate0(repo_root="C:/POLARIS")
    failed = [c.name for c in rep_clean.checks if not c.passed]
    _check(rep_clean.all_passed is True, f"clean GATE-0 passes its enabled checks (failed={failed})")


def main() -> int:
    print("=== dedup layer OFFLINE smoke test ===")
    smoke_py_compile()
    fixture_dir = smoke_build_fixture()
    smoke_run_bakeoff(fixture_dir)
    smoke_gate0()
    print("=== summary ===")
    if _FAILS:
        print(f"SMOKE FAILED ({len(_FAILS)} check(s)):")
        for f in _FAILS:
            print(f"  - {f}")
        return 1
    print("SMOKE PASSED (all checks green)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
