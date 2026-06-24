#!/usr/bin/env python3
"""I-ret-002 (#1294) reranker layer — OFFLINE stub smoke test.

Proves, with synthetic data and MOCKED model/API loaders (NO GPU, NO network, NO model download):
  1. all four layer files py_compile;
  2. the GATE-0 scorer-math canary passes (incl. the hand-computed FRACTIONAL NDCG case that a
     constant-1.0 scorer would FAIL, and the required-recall@K guard math);
  3. the GATE-0 lineage canary passes (the four gold slugs bind to a canonical idx);
  4. the per-candidate LIVENESS canary correctly FAILS LOUD on a simulated CONSTANT-stub reranker
     (the drb_72 anti-pattern) AND on a rank-INVERTED stub — while a healthy lexical-style stub
     PASSES;
  5. build_fixture's demote-only invariant + credibility-independence guard fire on bad input, and
     a tiny synthetic fixture builds end-to-end through graded NDCG;
  6. run_bakeoff's GPU gate / liveness-fail handling produce honest statuses (mocked, no real load).

Exit 0 on success; non-zero (with a printed reason) on any failure. This is the behavioral gate
the brief requires: the harness must FAIL LOUD on a stub, not score it a believable low number.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.dr_benchmark.retrieval_bakeoff.reranker import build_fixture, gate0, run_bakeoff


_FILES = ["__init__.py", "_lineage_seam.py", "build_fixture.py", "gate0.py", "run_bakeoff.py", "smoke_test.py"]


def _fail(msg: str) -> None:
    print(f"SMOKE FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def test_py_compile() -> None:
    paths = [os.path.join(_THIS_DIR, f) for f in _FILES]
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", *paths], capture_output=True, text=True
    )
    if proc.returncode != 0:
        _fail(f"py_compile failed:\n{proc.stderr}")
    print("  [ok] py_compile: all 6 files compile")


def test_scorer_math_canary() -> None:
    gate0.run_scorer_math_canary()  # raises GateZeroScorerError on any mismatch
    # Independently re-derive the fractional value to prove the canary checks the right number.
    log2_3 = math.log2(3)
    dcg = 2.0 + 3.0 / log2_3 + 0.5
    idcg = 3.0 + 2.0 / log2_3 + 0.5
    expected = dcg / idcg
    got = gate0.graded_ndcg_at_k([2, 3, 1, 0], k=4)
    if abs(got - expected) > 1e-9:
        _fail(f"fractional NDCG mismatch: expected {expected}, got {got}")
    # A constant-1.0 NDCG scorer would give 1.0 here -> the canary discriminates it.
    if abs(got - 1.0) < 1e-6:
        _fail("fractional case collapsed to 1.0 — discriminator is broken")
    print(f"  [ok] scorer-math canary: ideal=1.0, fractional NDCG@4={got:.8f} (discriminates const-1.0)")


def test_lineage_canary() -> None:
    gate0.run_lineage_canary()  # raises on an unbound/unregistered slug
    # And a genuinely-unregistered benchmark slug must fail loud.
    try:
        gate0.run_lineage_canary(["drb_99999_made_up"])
    except gate0.GateZeroLineageError:
        print("  [ok] lineage canary: gold slugs bound; unregistered drb_* fails loud")
        return
    _fail("lineage canary did NOT fail loud on an unregistered drb_* slug")


def test_liveness_canary_fails_on_stub() -> None:
    """The CORE behavioral proof: a constant-stub and a rank-inverted stub FAIL LOUD; a healthy
    lexical-style stub PASSES."""

    # (a) CONSTANT stub — returns the same score for relevant AND junk (a load-fail / OOM model).
    def constant_stub(query, docs):
        return [0.5 for _ in docs]

    try:
        gate0.run_liveness_canary(constant_stub, candidate_name="constant_stub")
    except gate0.RerankerLivenessError:
        print("  [ok] liveness: CONSTANT-stub correctly FAILED LOUD (drb_72 anti-pattern caught)")
    else:
        _fail("liveness canary did NOT fail on a constant-stub reranker (drb_72 hole)")

    # (b) rank-INVERTED stub — ranks junk above relevant.
    def inverted_stub(query, docs):
        return [0.1, 0.9]  # relevant=0.1 < junk=0.9

    try:
        gate0.run_liveness_canary(inverted_stub, candidate_name="inverted_stub")
    except gate0.RerankerLivenessError:
        print("  [ok] liveness: rank-INVERTED stub correctly FAILED LOUD")
    else:
        _fail("liveness canary did NOT fail on a rank-inverted stub")

    # (c) empty/malformed stub — wrong length.
    def empty_stub(query, docs):
        return []

    try:
        gate0.run_liveness_canary(empty_stub, candidate_name="empty_stub")
    except gate0.RerankerLivenessError:
        print("  [ok] liveness: EMPTY-output stub correctly FAILED LOUD")
    else:
        _fail("liveness canary did NOT fail on an empty-output stub")

    # (d) load-raising stub — simulates a missing key / failed model load.
    def raising_stub(query, docs):
        raise RuntimeError("simulated missing-key / load failure")

    try:
        gate0.run_liveness_canary(raising_stub, candidate_name="raising_stub")
    except gate0.RerankerLivenessError:
        print("  [ok] liveness: load-RAISING stub correctly FAILED LOUD")
    else:
        _fail("liveness canary did NOT fail on a load-raising stub")

    # (e) HEALTHY lexical-style stub — token-overlap with the relevant doc, none with junk: PASSES.
    relevant_tokens = set(gate0.LIVENESS_RELEVANT_DOC.lower().split())
    query_tokens = set(gate0.LIVENESS_QUERY.lower().split())

    def healthy_lexical_stub(query, docs):
        qtok = set(query.lower().split())
        return [float(len(qtok & set(d.lower().split()))) for d in docs]

    try:
        gate0.run_liveness_canary(healthy_lexical_stub, candidate_name="healthy_lexical_stub")
    except gate0.RerankerLivenessError as exc:
        _fail(f"liveness canary WRONGLY failed a healthy lexical scorer: {exc}")
    # Sanity: the probe really is lexically separable (else (e) would be vacuous).
    if not (query_tokens & relevant_tokens):
        _fail("liveness probe relevant doc shares no query tokens — probe is not lexically separable")
    print("  [ok] liveness: HEALTHY lexical-style scorer PASSED (no false-fail of the CPU baseline)")


def test_build_fixture_invariants() -> None:
    # Demote-only invariant holds on the real table.
    build_fixture.assert_demote_only_invariant(build_fixture.GRADED_GAIN_TABLE)
    # And fails loud if off_topic is given a positive gain (a §-1.3 breach).
    bad = dict(build_fixture.GRADED_GAIN_TABLE)
    bad[("off_topic", "high")] = 3
    try:
        build_fixture.assert_demote_only_invariant(bad)
    except build_fixture.FixtureError:
        pass
    else:
        _fail("demote-only invariant did NOT fail on off_topic->positive-gain")

    # Per-row credibility-independence backstop fires on a literal field echo (authority_score).
    try:
        build_fixture._assert_no_polaris_tier_leak({"authority_score": "high"}, "high")
    except build_fixture.FixtureError:
        pass
    else:
        _fail("per-row credibility backstop did NOT fire on an authority_score echo")
    # A real T1 tier value does NOT trip the per-row backstop (T1 != "high" literally) — that is by
    # design; independence is process-enforced. The per-row helper must NOT false-positive here.
    build_fixture._assert_no_polaris_tier_leak({"tier": "T1"}, "high")  # must not raise

    # AGGREGATE guard: an annotation that is a deterministic function of POLARIS tier fails loud.
    tier_derived = [
        ({"tier": "T1"}, "high"),
        ({"tier": "T3"}, "medium"),
        ({"tier": "T7"}, "spam"),
    ]
    try:
        build_fixture.assert_credibility_not_tier_derived(tier_derived)
    except build_fixture.FixtureError:
        pass
    else:
        _fail("aggregate credibility-independence guard did NOT fire on a fully tier-derived annotation")
    # A non-derived annotation (a T7 source judged 'high' on independent grounds) does NOT trip it.
    not_derived = [
        ({"tier": "T1"}, "high"),
        ({"tier": "T7"}, "high"),   # independent judgment disagrees with the tier-derived 'spam'
        ({"tier": "T3"}, "medium"),
    ]
    build_fixture.assert_credibility_not_tier_derived(not_derived)  # must not raise

    # Graded gain is deterministic + total over the label cross-product.
    for rel in build_fixture.RELEVANCE_LABELS:
        for cred in build_fixture.CREDIBILITY_LABELS:
            g = build_fixture.GRADED_GAIN_TABLE[(rel, cred)]
            if rel == "off_topic" and g != 0:
                _fail(f"off_topic x {cred} gain {g} != 0")
    print("  [ok] build_fixture: demote-only + credibility-independence guards fire; gain total")


def test_build_fixture_end_to_end_synthetic() -> None:
    """Build a tiny synthetic fixture for ONE gold slug through to graded NDCG — proves the schema
    + loader + math wire together offline. Mocks the (real) two-family judge job with a frozen
    synthetic annotation. Honest: this is a SYNTHETIC stand-in for the parallel judge annotation."""
    slug = "drb_78_parkinsons_dbs"
    idx = build_fixture.SLUG_TO_IDX[slug]
    with tempfile.TemporaryDirectory() as tmp:
        pool_dir = os.path.join(tmp, "pool")
        annot_dir = os.path.join(tmp, "annot")
        ir_dir = os.path.join(tmp, "info_recall")
        for d in (pool_dir, annot_dir, ir_dir):
            os.makedirs(d)
        # Frozen pool: 1 strongly-supporting/high (required sole-supporter), 1 supporting/medium,
        # 1 on-topic-irrelevant/low, 1 off-topic/spam.
        pool = [
            {"cand_id": "c1", "title": "STN-DBS RCT", "body": "deep brain stimulation parkinson motor", "url": "u1", "question": "Q?"},
            {"cand_id": "c2", "title": "DBS cohort", "body": "subthalamic stimulation levodopa", "url": "u2"},
            {"cand_id": "c3", "title": "PD review", "body": "parkinson disease general overview", "url": "u3"},
            {"cand_id": "c4", "title": "Recycling memo", "body": "curbside compost cardboard pickup", "url": "u4"},
        ]
        labels = [
            {"cand_id": "c1", "relevance_label": "strongly_supporting", "credibility_label": "high",
             "supports_claim_ids": ["k1"], "required": True},
            {"cand_id": "c2", "relevance_label": "supporting", "credibility_label": "medium",
             "supports_claim_ids": ["k2"], "required": False},
            {"cand_id": "c3", "relevance_label": "on_topic_irrelevant", "credibility_label": "low",
             "supports_claim_ids": [], "required": False},
            {"cand_id": "c4", "relevance_label": "off_topic", "credibility_label": "spam",
             "supports_claim_ids": [], "required": False},
        ]
        with open(os.path.join(pool_dir, f"{slug}.pool.jsonl"), "w", encoding="utf-8") as fh:
            for r in pool:
                fh.write(json.dumps(r) + "\n")
        with open(os.path.join(annot_dir, f"{slug}.labels.jsonl"), "w", encoding="utf-8") as fh:
            for r in labels:
                fh.write(json.dumps(r) + "\n")
        with open(os.path.join(ir_dir, f"idx_{idx}.claims.json"), "w", encoding="utf-8") as fh:
            json.dump(["k1", "k2"], fh)

        fx = build_fixture.build_idx_fixture(
            slug, pool_dir=pool_dir, annot_dir=annot_dir, info_recall_dir=ir_dir
        )
        gains = fx.gains()
        if gains != [3, 2, 0, 0]:
            _fail(f"synthetic fixture gains wrong: expected [3,2,0,0], got {gains}")
        if fx.required_ids() != ["c1"]:
            _fail(f"synthetic fixture required wrong: {fx.required_ids()}")

        # A healthy lexical scorer (token overlap with the question stand-in) re-orders correctly.
        def lexical_fn(query, docs):
            qtok = set("deep brain stimulation parkinson subthalamic motor".split())
            return [float(len(qtok & set(d.lower().split()))) for d in docs]

        m = run_bakeoff.score_candidate_on_idx(lexical_fn, fx, k=3)
        if not (0.0 < m["ndcg_at_k"] <= 1.0):
            _fail(f"synthetic end-to-end NDCG out of range: {m}")
        if m["gold_n"] != 2 or m["required_n"] != 1 or m["pool_n"] != 4:
            _fail(f"synthetic per-idx counts wrong: {m}")
        # Required source c1 (strong tokens) survives top-3 -> recall 1.0.
        if abs(m["required_recall_at_k"] - 1.0) > 1e-9:
            _fail(f"synthetic required-recall@3 expected 1.0, got {m['required_recall_at_k']}")
    print("  [ok] build_fixture end-to-end (synthetic): gains [3,2,0,0], NDCG in range, recall guard ok")


def test_run_bakeoff_honest_statuses() -> None:
    """run_bakeoff against a mocked candidate set: a needs_gpu candidate with no GPU -> skipped;
    a candidate whose loader yields a constant stub -> failed_liveness. No real model load."""
    slug = "drb_78_parkinsons_dbs"
    idx = build_fixture.SLUG_TO_IDX[slug]
    with tempfile.TemporaryDirectory() as tmp:
        pool_dir = os.path.join(tmp, "pool"); annot_dir = os.path.join(tmp, "annot"); ir_dir = os.path.join(tmp, "info_recall")
        for d in (pool_dir, annot_dir, ir_dir):
            os.makedirs(d)
        with open(os.path.join(pool_dir, f"{slug}.pool.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"cand_id": "c1", "title": "t", "body": "deep brain stimulation parkinson", "url": "u", "question": "Q"}) + "\n")
            fh.write(json.dumps({"cand_id": "c2", "title": "t2", "body": "recycling compost", "url": "u2"}) + "\n")
        with open(os.path.join(annot_dir, f"{slug}.labels.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"cand_id": "c1", "relevance_label": "supporting", "credibility_label": "high", "required": True}) + "\n")
            fh.write(json.dumps({"cand_id": "c2", "relevance_label": "off_topic", "credibility_label": "spam"}) + "\n")
        with open(os.path.join(ir_dir, f"idx_{idx}.claims.json"), "w", encoding="utf-8") as fh:
            json.dump(["k1"], fh)
        fixtures = build_fixture.build_all(slugs=(slug,), pool_dir=pool_dir, annot_dir=annot_dir, info_recall_dir=ir_dir)

        # Mock build_rerank_fn so NOTHING loads a real model.
        orig_builder = run_bakeoff.build_rerank_fn

        def mock_builder(cand, *, device):
            if cand.name == "polaris_lexical_rerank":
                def lex(query, docs):
                    qtok = set("deep brain stimulation parkinson".split())
                    return [float(len(qtok & set(d.lower().split()))) for d in docs]
                return lex
            # every "model" candidate is a broken constant stub here (offline) -> must fail liveness
            return lambda query, docs: [0.5 for _ in docs]

        run_bakeoff.build_rerank_fn = mock_builder
        try:
            # have_gpu=False so needs_gpu candidates are skipped; lexical (CPU) is scored.
            out = run_bakeoff.run_bakeoff(
                fixtures=fixtures,
                candidates=list(run_bakeoff.CANDIDATES),
                k=2, device="cpu", have_gpu=False,
            )
        finally:
            run_bakeoff.build_rerank_fn = orig_builder

    statuses = {r["name"]: r["status"] for r in out["candidates"]}
    if statuses.get("polaris_lexical_rerank") != "scored":
        _fail(f"CPU lexical baseline should be scored, got {statuses.get('polaris_lexical_rerank')}")
    # Every needs_gpu model candidate must be skipped honestly (no GPU here), never faked.
    gpu_models = [c.name for c in run_bakeoff.CANDIDATES if c.runnable == "needs_gpu"]
    for name in gpu_models:
        if statuses.get(name) != "skipped_needs_gpu":
            _fail(f"needs_gpu candidate {name} expected skipped_needs_gpu, got {statuses.get(name)}")
    # have_gpu path simulation: force the GPU gate open but keep the mocked constant stub -> must
    # come back failed_liveness (the constant stub is caught), never scored.
    run_bakeoff.build_rerank_fn = mock_builder
    try:
        out2 = run_bakeoff.run_bakeoff(
            fixtures=fixtures,
            candidates=[c for c in run_bakeoff.CANDIDATES if c.name == "gte_reranker_modernbert_base"],
            k=2, device="cpu", have_gpu=True,
        )
    finally:
        run_bakeoff.build_rerank_fn = orig_builder
    s2 = {r["name"]: r["status"] for r in out2["candidates"]}
    if s2.get("gte_reranker_modernbert_base") != "failed_liveness":
        _fail(f"constant-stub model candidate expected failed_liveness, got {s2.get('gte_reranker_modernbert_base')}")

    # FIX-B anti-silent-no-op: run a candidate WITHOUT the lexical baseline (and with a healthy
    # mocked scorer so it actually SCORES). The recall guard cannot be evaluated -> it must be
    # 'not_evaluated' and the candidate must NOT be crowned (never a believable-false True pass).
    def healthy_model_builder(cand, *, device):
        def fn(query, docs):
            qtok = set("deep brain stimulation parkinson".split())
            return [float(len(qtok & set(d.lower().split()))) for d in docs]
        return fn

    run_bakeoff.build_rerank_fn = healthy_model_builder
    try:
        out3 = run_bakeoff.run_bakeoff(
            fixtures=fixtures,
            candidates=[c for c in run_bakeoff.CANDIDATES if c.name == "gte_reranker_modernbert_base"],
            k=2, device="cpu", have_gpu=True,  # baseline NOT in this candidate set
        )
    finally:
        run_bakeoff.build_rerank_fn = orig_builder
    r3 = next(r for r in out3["candidates"] if r["name"] == "gte_reranker_modernbert_base")
    if r3["status"] != "scored":
        _fail(f"healthy model w/o baseline should be scored, got {r3['status']}")
    if r3.get("passes_recall_guard") != "not_evaluated":
        _fail(f"recall guard w/o baseline must be 'not_evaluated', got {r3.get('passes_recall_guard')!r} "
              f"(a believable-false True would crown an unvetted reranker — drb_72 class)")
    if out3["ranking_deployable_recall_guard_passed"]:
        _fail(f"no candidate may be crowned when the recall guard could not be evaluated, "
              f"got ranking={out3['ranking_deployable_recall_guard_passed']}")
    print("  [ok] run_bakeoff: CPU baseline scored; needs_gpu skipped; constant-stub -> failed_liveness; "
          "recall-guard w/o baseline -> not_evaluated + NOT crowned")


def main() -> int:
    print("=== reranker layer OFFLINE smoke (synthetic data, mocked loaders, no GPU/network) ===")
    test_py_compile()
    test_scorer_math_canary()
    test_lineage_canary()
    test_liveness_canary_fails_on_stub()
    test_build_fixture_invariants()
    test_build_fixture_end_to_end_synthetic()
    test_run_bakeoff_honest_statuses()
    print("SMOKE PASS: all reranker-layer canaries green; liveness FAILS LOUD on stubs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
