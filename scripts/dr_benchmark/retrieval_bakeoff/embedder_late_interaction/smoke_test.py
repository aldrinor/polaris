#!/usr/bin/env python3
"""I-ret-002 (#1294) — embedder_late_interaction layer: OFFLINE stub smoke test.

NO GPU, NO network, NO real model download. It MOCKS the candidate loaders with tiny in-process
fake encoders and proves the harness is sound:

  1. ALL four layer files py_compile.
  2. The GATE-0 scorer-math canary passes (known input -> known score).
  3. The GATE-0 per-candidate LIVENESS canary:
       - PASSES on a GOOD fake encoder (on-topic scored strictly above off-topic),
       - FAILS LOUD on a STUB encoder (returns a constant -> on NOT > off),
       - FAILS LOUD on an IDENTITY-MISMATCH encoder (loaded_id != requested id; the
         I-arch-009 Gate-B no-silent-MiniLM-fallback lesson).
  4. build_fixture runs offline over the banked snapshots (no adjudication file present ->
     zero SCORED rows, which is the HONEST/expected offline state), and run_bakeoff's
     needs_gpu candidates are honestly SKIPPED on this CPU box (never faked).

Exit 0 ONLY if every assertion holds. Any failure exits non-zero (FAIL LOUD).
"""
from __future__ import annotations

import os
import subprocess
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def _print(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Step 1 — py_compile every file in this layer.
# ---------------------------------------------------------------------------
def step_py_compile() -> None:
    files = ["build_fixture.py", "scorer.py", "run_bakeoff.py", "gate0.py", "smoke_test.py"]
    paths = [os.path.join(_THIS_DIR, f) for f in files]
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", *paths],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        _print(proc.stdout)
        _print(proc.stderr)
        raise AssertionError(f"py_compile FAILED (rc={proc.returncode})")
    _print(f"  [PASS] py_compile: {len(files)} files compile clean")


# ---------------------------------------------------------------------------
# Fake encoders (synthetic, deterministic, no model). They implement the same
# LoadedEncoder interface run_bakeoff/gate0 use.
# ---------------------------------------------------------------------------
def _make_fakes():
    from run_bakeoff import Candidate, CandidateLoadError, LoadedEncoder

    # A tiny "semantic" embedding: bag-of-content-words hashed into a small fixed vector.
    import re

    _word = re.compile(r"[a-z]+")
    _dim = 64

    def embed(text: str) -> list[float]:
        vec = [0.0] * _dim
        for w in _word.findall(text.lower()):
            if len(w) < 3:
                continue
            vec[hash(w) % _dim] += 1.0
        # L2 normalize so cosine is meaningful.
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]

    def good_loader(cand: Candidate, device: str) -> LoadedEncoder:
        """A WORKING single-vector encoder: real bag-of-words embedding, correct identity."""
        def encode_single(texts, is_query):
            return [embed(t) for t in texts]

        enc = LoadedEncoder(
            candidate=cand, loaded_id=cand.hf_id, encode_single=encode_single
        )
        enc.assert_identity()
        return enc

    def stub_loader(cand: Candidate, device: str) -> LoadedEncoder:
        """A STUB encoder: returns the SAME constant vector for every text (no signal)."""
        const = [1.0] + [0.0] * (_dim - 1)

        def encode_single(texts, is_query):
            return [list(const) for _ in texts]

        # identity OK — the FAILURE must come from the on>off direction check, not identity.
        enc = LoadedEncoder(candidate=cand, loaded_id=cand.hf_id, encode_single=encode_single)
        enc.assert_identity()
        return enc

    def mismatch_loader(cand: Candidate, device: str):
        """An encoder that silently loaded a DIFFERENT model (the Gate-B failure)."""
        def encode_single(texts, is_query):
            return [embed(t) for t in texts]

        enc = LoadedEncoder(
            candidate=cand,
            loaded_id="sentence-transformers/all-MiniLM-L6-v2",  # silent fallback
            encode_single=encode_single,
        )
        enc.assert_identity()  # MUST raise CandidateLoadError for a non-MiniLM candidate
        return enc

    return good_loader, stub_loader, mismatch_loader, CandidateLoadError


# ---------------------------------------------------------------------------
# Step 2 — scorer-math canary.
# ---------------------------------------------------------------------------
def step_scorer_math() -> None:
    from gate0 import check_scorer_math

    passed = check_scorer_math()
    assert len(passed) >= 14, f"expected >=14 scorer-math checks, got {len(passed)}"
    _print(f"  [PASS] scorer-math canary: {len(passed)} checks green")


# ---------------------------------------------------------------------------
# Step 3 — liveness canary: good PASSES, stub FAILS, mismatch FAILS.
# ---------------------------------------------------------------------------
def step_liveness() -> None:
    from gate0 import check_candidate_liveness
    from run_bakeoff import CANDIDATES

    good_loader, stub_loader, mismatch_loader, _ = _make_fakes()
    # Use a CPU-eligible single-vector candidate so device gating does not skip it.
    cand = CANDIDATES["all_minilm_l6_v2"]

    good = check_candidate_liveness(cand, "cpu", good_loader)
    assert good.passed and good.status == "live", f"good encoder should pass, got {good}"
    assert good.on_topic_score > good.off_topic_score, "good: on must exceed off"
    _print(f"  [PASS] liveness GOOD encoder: on={good.on_topic_score:.4f} "
           f"> off={good.off_topic_score:.4f}")

    stub = check_candidate_liveness(cand, "cpu", stub_loader)
    assert (not stub.passed) and stub.status == "FAILED", (
        f"STUB encoder MUST fail liveness (constant scores), got {stub}"
    )
    _print(f"  [PASS] liveness STUB encoder correctly FAILED LOUD: {stub.detail[:70]}")

    mism = check_candidate_liveness(cand, "cpu", mismatch_loader)
    # all_minilm_l6_v2's requested id IS all-MiniLM — so for that candidate identity holds.
    # Use a NON-MiniLM candidate to exercise the identity-mismatch failure.
    other = CANDIDATES["gte_modernbert_embed"]
    mism = check_candidate_liveness(other, "cpu", mismatch_loader)
    assert (not mism.passed) and mism.status == "FAILED", (
        f"IDENTITY-MISMATCH encoder MUST fail liveness, got {mism}"
    )
    assert "identity" in mism.detail.lower() or "load" in mism.detail.lower()
    _print(f"  [PASS] liveness IDENTITY-MISMATCH correctly FAILED LOUD: {mism.detail[:70]}")


# ---------------------------------------------------------------------------
# Step 4 — build_fixture runs offline; needs_gpu candidates honestly skipped.
# ---------------------------------------------------------------------------
def step_fixture_and_skips() -> None:
    from build_fixture import build_fixture
    from run_bakeoff import CANDIDATES, run_candidate

    fixture = build_fixture(max_per_class=20)
    summary = fixture.to_dict()["summary"]
    # Offline: no adjudication file -> proposals exist but ZERO scored (honest, expected).
    assert summary["axis_a_scored"] == 0, (
        "offline (no adjudication) MUST yield 0 SCORED Axis-A rows — keyword proposals are not "
        f"scored labels (brief iter-2 P1); got {summary['axis_a_scored']}"
    )
    _print(f"  [PASS] build_fixture offline: proposed={summary['axis_a_proposed']} "
           f"scored={summary['axis_a_scored']} (0 scored is the honest no-adjudication state)")

    # needs_gpu candidate on this CPU box -> honest skip, never a fake score.
    gpu_cand = CANDIDATES["qwen3_embedding_8b"]
    res = run_candidate(gpu_cand, fixture, "cpu", k=10)
    assert res.status == "skipped_needs_gpu", (
        f"needs_gpu candidate on CPU MUST be skipped_needs_gpu, got {res.status}"
    )
    assert res.axis_a_macro is None and res.axis_b_macro is None, "skipped must carry no score"
    _print(f"  [PASS] needs_gpu candidate honestly skipped: {gpu_cand.name} -> {res.status}")

    # yardstick candidate flagged ineligible_to_win (sovereignty / CC-BY-NC guard).
    yard = CANDIDATES["reason_moderncolbert"]
    assert yard.license_role == "yardstick"
    res_y = run_candidate(yard, fixture, "cpu", k=10)
    assert res_y.ineligible_to_win, "CC-BY-NC yardstick MUST be ineligible_to_win"
    _print(f"  [PASS] yardstick ineligible_to_win: {yard.name} (CC-BY-NC, never crowned)")


def main() -> int:
    _print("=== embedder_late_interaction OFFLINE smoke (no GPU, no network) ===")
    try:
        _print("[1/4] py_compile")
        step_py_compile()
        _print("[2/4] scorer-math canary")
        step_scorer_math()
        _print("[3/4] liveness canary (good PASS / stub FAIL / mismatch FAIL)")
        step_liveness()
        _print("[4/4] fixture build + honest skips")
        step_fixture_and_skips()
    except AssertionError as exc:
        _print(f"\nSMOKE FAILED: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        _print(f"\nSMOKE ERROR: {exc!r}")
        return 1
    _print("\nSMOKE PASSED: all 4 steps green. GATE-0 math + per-candidate liveness verified "
           "(stub + identity-mismatch correctly fail loud).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
