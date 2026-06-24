#!/usr/bin/env python3
"""OFFLINE stub smoke test for the quality_weight bake-off (I-ret-002 #1294, §4).

Proves, with NO GPU / NO network / NO model download (all model/API loaders MOCKED):
  1. all four layer files py_compile;
  2. the GATE-0 scorer-math canary PASSES (perfect=1.0 / inverted=0.0 / constant=0.5 /
     random-in-band / within-cell-kills-source-type-prior);
  3. the GATE-0 per-candidate LIVENESS canary correctly FAILS LOUD on a simulated STUB candidate
     (a constant-0.5 scorer) — the anti-drb_72 proof — AND PASSES on a synthetic real scorer;
  4. the negative controls (constant / random) land near 0.5;
  5. a mini end-to-end run on synthetic ADJUDICATED rows ranks a good scorer above a noisy one
     while a stub candidate is recorded as liveness_failed (never given a fake AUC);
  6. build_fixture's objective rubric labels real domains correctly (authoritative vs UGC/spam),
     and a 'proposed' fixture is NOT scored (provisional), all offline.

Exit 0 on success; non-zero with a printed reason on any failure.
"""

from __future__ import annotations

import os
import py_compile
import sys
import tempfile
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import gate0  # noqa: E402
import build_fixture  # noqa: E402
import run_bakeoff  # noqa: E402

_FAILURES: list[str] = []


def _check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" :: {detail}" if detail else ""))
    if not ok:
        _FAILURES.append(name)


# ---------------------------------------------------------------------------
# 1. py_compile all four files
# ---------------------------------------------------------------------------
def test_py_compile() -> None:
    print("[1] py_compile all four layer files")
    for fname in ("gate0.py", "build_fixture.py", "run_bakeoff.py", "smoke_test.py"):
        path = os.path.join(_HERE, fname)
        try:
            py_compile.compile(path, doraise=True)
            _check(f"py_compile {fname}", True)
        except py_compile.PyCompileError as exc:
            _check(f"py_compile {fname}", False, str(exc))


# ---------------------------------------------------------------------------
# 2. scorer-math canary PASSES
# ---------------------------------------------------------------------------
def test_scorer_math_canary() -> None:
    print("[2] GATE-0 scorer-math canary")
    try:
        report = gate0.run_scorer_math_canary()
        names = {c["name"]: c["ok"] for c in report["checks"]}
        _check("scorer_math all checks pass", all(names.values()), str(names))
    except gate0.GateZeroQualityError as exc:
        _check("scorer_math all checks pass", False, str(exc))


# ---------------------------------------------------------------------------
# 3. liveness canary FAILS on a stub, PASSES on a real scorer  (anti-drb_72)
# ---------------------------------------------------------------------------
def _good_synthetic_scorer(text: str) -> float:
    """A synthetic REAL classifier: rewards clinical/regulatory signal, penalizes spam markers.
    Used to prove the liveness canary lets a genuine varying classifier through."""
    t = text.lower()
    good = sum(t.count(k) for k in ("trial", "confidence interval", "endpoint", "dose",
                                    "contraindication", "hba1c", "placebo", "p<0.001"))
    bad = sum(t.count(k) for k in ("cookie", "subscribe", "buy now", "discount", "click here",
                                   "best deals", "sign up"))
    # bounded, varying, monotone in (good-bad)
    return 0.5 + 0.05 * (good - bad)


def _constant_stub_scorer(_text: str) -> float:
    """A SILENT-STUB candidate: returns a constant for every doc. This is the drb_72 failure mode
    — it would still produce a real-looking AUC. The liveness canary MUST reject it."""
    return 0.5


def test_liveness_canary() -> None:
    print("[3] GATE-0 per-candidate liveness canary (anti-drb_72)")
    auth = run_bakeoff._AUTHORITATIVE_CANARY_DOC
    junk = run_bakeoff._GARBAGE_CANARY_DOC

    # 3a: a real synthetic scorer PASSES liveness
    try:
        live = gate0.assert_candidate_live("synthetic_good", _good_synthetic_scorer, auth, junk)
        _check("real scorer passes liveness", live["ok"] and live["gap"] > 0,
               f"gap={live['gap']:.3f}")
    except gate0.GateZeroQualityError as exc:
        _check("real scorer passes liveness", False, str(exc))

    # 3b: a constant STUB candidate MUST FAIL LOUD (raise) — this is the load-bearing check
    raised = False
    try:
        gate0.assert_candidate_live("constant_stub", _constant_stub_scorer, auth, junk)
    except gate0.GateZeroQualityError as exc:
        raised = True
        detail = str(exc)[:90]
    _check("constant STUB candidate FAILS LOUD", raised,
           detail if raised else "stub was NOT rejected — canary too weak (the drb_72 hole)")

    # 3c: a load-fail candidate MUST FAIL LOUD (propagate, never a low score)
    def _exploding_scorer(_text: str) -> float:
        raise RuntimeError("simulated model load/runtime failure")

    raised2 = False
    try:
        gate0.assert_candidate_live("load_fail", _exploding_scorer, auth, junk)
    except gate0.GateZeroQualityError:
        raised2 = True
    _check("load-fail candidate FAILS LOUD", raised2,
           "raised" if raised2 else "load failure produced a score instead of raising")

    # 3d: a WRONG-DIRECTION scorer (ranks garbage above authoritative) MUST FAIL LOUD
    raised3 = False
    try:
        gate0.assert_candidate_live("inverted", lambda t: -_good_synthetic_scorer(t), auth, junk)
    except gate0.GateZeroQualityError:
        raised3 = True
    _check("wrong-direction candidate FAILS LOUD", raised3,
           "raised" if raised3 else "garbage-over-authoritative was accepted")


# ---------------------------------------------------------------------------
# 4. negative controls land near 0.5
# ---------------------------------------------------------------------------
def test_controls_near_half() -> None:
    print("[4] negative controls near 0.5")
    # map scored_label -> label exactly as run_bakeoff does for adjudicated rows
    rows = run_bakeoff._adjudicated_rows(_synthetic_adjudicated_rows())
    for name, scorer in (("constant_0.5", run_bakeoff.constant_scorer),
                         ("random_seeded", run_bakeoff.make_random_scorer())):
        scored = [{**r, "score": scorer(r["post_extraction_body"])} for r in rows]
        auc = gate0.paired_within_cell_auc(scored, score_key="score")["auc"]
        try:
            gate0.assert_control_near_half(name, auc)
            _check(f"control {name} near 0.5", True, f"auc={auc:.3f}")
        except gate0.GateZeroQualityError as exc:
            _check(f"control {name} near 0.5", False, str(exc))


# ---------------------------------------------------------------------------
# 5. mini end-to-end with MOCKED loaders on synthetic ADJUDICATED rows
# ---------------------------------------------------------------------------
def _synthetic_adjudicated_rows() -> list[dict]:
    """Synthetic fixture: within each (topic x source_type) cell, an authoritative body (clinical
    signal) and a spam body (marketing junk). label_status=adjudicated so run_bakeoff scores them.
    NO real snapshot, NO model — pure offline."""
    auth_body = run_bakeoff._AUTHORITATIVE_CANARY_DOC
    spam_body = run_bakeoff._GARBAGE_CANARY_DOC
    rows = []
    for topic in ("topicA", "topicB", "topicC"):
        for st in ("peer_reviewed_publisher", "gov_regulator"):
            rows.append({"source_id": f"{topic}:{st}:auth", "topic_id": topic, "source_type": st,
                         "post_extraction_body": auth_body + f" study {topic}",
                         "label_status": "adjudicated", "scored_label": 1})
            rows.append({"source_id": f"{topic}:{st}:spam", "topic_id": topic, "source_type": st,
                         "post_extraction_body": spam_body + f" {topic}",
                         "label_status": "adjudicated", "scored_label": 0})
    return rows


def test_end_to_end_mocked() -> None:
    print("[5] mini end-to-end with MOCKED loaders (no GPU/net/download)")
    rows = _synthetic_adjudicated_rows()
    with tempfile.TemporaryDirectory() as td:
        fixture_path = os.path.join(td, "fixture.jsonl")
        with open(fixture_path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        out_path = os.path.join(td, "results.json")

        # Build a MOCKED registry: loaders return synthetic scorers (no torch/fasttext/API).
        registry = [
            run_bakeoff.Candidate(
                name="good_model", impl_id="mock://good", license="mock", runnable="yes",
                role="candidate", family="mockfamily",
                loader=lambda: _good_synthetic_scorer),
            run_bakeoff.Candidate(
                name="noisy_model", impl_id="mock://noisy", license="mock", runnable="yes",
                role="candidate", family="mockfamily2",
                loader=lambda: (lambda t: _good_synthetic_scorer(t) * 0.2
                                + run_bakeoff.make_random_scorer(3)(t) * 0.8)),
            run_bakeoff.Candidate(
                name="stub_model", impl_id="mock://stub", license="mock", runnable="yes",
                role="candidate", family="mockfamily3",
                loader=lambda: _constant_stub_scorer),  # MUST be liveness_failed, never scored
            run_bakeoff.Candidate(
                name="nokey_judge", impl_id="mock://judge", license="api", runnable="no_key",
                role="yardstick_non_sovereign", family="glm",
                loader=lambda: (_ for _ in ()).throw(RuntimeError("no key"))),  # skipped_no_key
        ]
        report = run_bakeoff.run(fixture_path=fixture_path, out_path=out_path, registry=registry)

        by_name = {c["name"]: c for c in report["candidates"]}
        _check("good_model scored", by_name["good_model"]["status"] == "scored",
               f"auc={by_name['good_model']['auc']}")
        _check("good_model auc == 1.0 on clean synthetic",
               by_name["good_model"]["auc"] == 1.0, f"auc={by_name['good_model']['auc']}")
        _check("stub_model liveness_failed (no fake AUC)",
               by_name["stub_model"]["status"] == "liveness_failed"
               and by_name["stub_model"]["auc"] is None)
        _check("nokey_judge skipped_no_key",
               by_name["nokey_judge"]["status"] == "skipped_no_key")
        _check("good ranks above noisy",
               (by_name["good_model"]["auc"] or 0) >= (by_name["noisy_model"]["auc"] or 0))
        _check("controls present and near 0.5",
               all(abs(c["auc"] - 0.5) <= gate0.RANDOM_BAND_HALF_WIDTH
                   for c in report["controls"]),
               str([(c["name"], round(c["auc"], 3)) for c in report["controls"]]))
        _check("results json written", os.path.isfile(out_path))


# ---------------------------------------------------------------------------
# 6. objective rubric labels real domains correctly + proposed fixture not scored
# ---------------------------------------------------------------------------
def test_objective_rubric() -> None:
    print("[6] build_fixture objective rubric + provisional handling")
    cases = [
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC123/", None, None, 1),
        ("https://accessdata.fda.gov/label/123.pdf", None, None, 1),
        ("https://www.youtube.com/watch?v=abc", None, None, 0),
        ("https://www.facebook.com/post/1", None, None, 0),
        ("https://www.researchgate.net/publication/x", None, None, 0),
        ("https://doi.org/10.1234/x", "10.1234/x", None, 1),       # DOI doc-id -> authoritative
        ("https://some-unlisted-blog.example/post", None, None, None),  # undecidable -> excluded
        ("https://unlisted.example/paper", None, "12345678", 1),   # carries PMID -> authoritative
    ]
    ok = True
    for url, doi, pmid, expect in cases:
        label, reason = build_fixture.objective_rubric_label(url=url, doi=doi, pmid=pmid)
        if label != expect:
            ok = False
            print(f"      MISMATCH {url} doi={doi} pmid={pmid}: got {label} ({reason}), want {expect}")
    _check("objective rubric labels verifiable domains", ok)

    # source_type pairing is identity-based, never POLARIS tier
    _check("source_type youtube -> social_video",
           build_fixture._source_type("www.youtube.com") == "social_video")
    _check("source_type pmc -> peer_reviewed_publisher",
           build_fixture._source_type("pmc.ncbi.nlm.nih.gov") == "peer_reviewed_publisher")

    # a 'proposed' (non-adjudicated) fixture must NOT be scored -> provisional, no fake AUCs
    rows = [{"source_id": "x", "topic_id": "t", "source_type": "peer_reviewed_publisher",
             "post_extraction_body": "body", "label_status": "proposed", "scored_label": None}]
    _check("proposed rows not scored (provisional)",
           len(run_bakeoff._adjudicated_rows(rows)) == 0)


def test_no_scorable_cells_guard() -> None:
    print("[7] zero-scorable-cell guard (collinearity / source-type proxy defense)")
    # Adjudicated rows where NO cell holds both classes: authoritative only in one source_type,
    # spam only in another (the banked-snapshot collinearity pattern). The metric must refuse to
    # score rather than emit a misleading number.
    rows = []
    for topic in ("topicA", "topicB"):
        rows.append({"source_id": f"{topic}:auth", "topic_id": topic,
                     "source_type": "peer_reviewed_publisher",
                     "post_extraction_body": run_bakeoff._AUTHORITATIVE_CANARY_DOC,
                     "label_status": "adjudicated", "scored_label": 1})
        rows.append({"source_id": f"{topic}:spam", "topic_id": topic,
                     "source_type": "social_video",
                     "post_extraction_body": run_bakeoff._GARBAGE_CANARY_DOC,
                     "label_status": "adjudicated", "scored_label": 0})
    with tempfile.TemporaryDirectory() as td:
        fixture_path = os.path.join(td, "f.jsonl")
        with open(fixture_path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        out_path = os.path.join(td, "r.json")
        registry = [run_bakeoff.Candidate(
            name="good_model", impl_id="mock://good", license="mock", runnable="yes",
            role="candidate", family="mock", loader=lambda: _good_synthetic_scorer)]
        report = run_bakeoff.run(fixture_path=fixture_path, out_path=out_path, registry=registry)
        c = report["candidates"][0]
        _check("collinear fixture -> no_scorable_cells (no fake AUC)",
               c["status"] == "no_scorable_cells" and c["auc"] is None, f"status={c['status']}")
        _check("all-candidates-no-cells flag set",
               report["no_scorable_cells_for_all_candidates"] is True)


def main() -> int:
    print("=" * 72)
    print("quality_weight bake-off OFFLINE smoke test (mocked loaders, no GPU/net)")
    print("=" * 72)
    test_py_compile()
    test_scorer_math_canary()
    test_liveness_canary()
    test_controls_near_half()
    test_end_to_end_mocked()
    test_objective_rubric()
    test_no_scorable_cells_guard()
    print("-" * 72)
    if _FAILURES:
        print(f"SMOKE FAILED: {len(_FAILURES)} check(s) failed: {_FAILURES}")
        return 1
    print("SMOKE PASSED: all checks green (scorer-math PASS; stub liveness correctly FAILED LOUD)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
