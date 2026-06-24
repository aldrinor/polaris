#!/usr/bin/env python3
"""Run the quality_weight retrieval-isolation bake-off (I-ret-002 #1294, §4).

For each candidate quality-weight model: load it by its EXACT HF/pip/API id, score every
ADJUDICATED fixture source -> a scalar weight, compute the within-(topic x source_type)-cell
ROC-AUC of that weight vs the binary label (gate0.paired_within_cell_auc), and write a ranked
results JSON.

GATE-0 IS MANDATORY and runs FIRST (gate0.run_scorer_math_canary + per-candidate liveness via
gate0.assert_candidate_live). No candidate AUC is emitted until the scorer-math canary is green
AND the candidate passed its own liveness check. A stub / constant / load-failed / missing-key
candidate FAILS LOUD and is recorded as non-functional — it is NEVER given a believable-low AUC.

HONEST FLAGS (never faked):
  * runnable == "no_key"   -> registered but SKIPPED (recorded, not scored). E.g. GLM-5.2 judge.
  * runnable == "needs_gpu" -> gated behind a real runtime check (torch.cuda / fasttext import);
    if the runtime is absent the candidate is recorded as skipped-needs-gpu, never faked.
  * runnable == "yes"      -> CPU; runs anywhere.

NEGATIVE CONTROLS (constant / random): NOT candidates, EXEMPT from the semantic-direction
liveness canary; the harness instead asserts they land near 0.5 (gate0.assert_control_near_half).

WEIGHT-NOT-FILTER (§-1.3): the scalar weight is NEVER thresholded to drop a source here. The
metric (ROC-AUC) integrates over all thresholds — it is the formal statement of weight-not-filter.

FAITHFULNESS untouched: every candidate is a SCORER (no span is rewritten); strict_verify / NLI /
4-role / provenance are never invoked.

The candidate loaders are written as `load() -> scorer_callable`. Heavy model loads (fastText /
transformers / torch / API) are imported INSIDE load() so smoke_test.py can monkeypatch load()
with a synthetic scorer — NO GPU, NO network, NO download in the smoke.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
# repo root = .../scripts/dr_benchmark/retrieval_bakeoff/quality_weight -> up 4 (so `from src...`
# resolves regardless of cwd, e.g. the POLARIS heuristic baseline loader).
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
for _p in (_HERE, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gate0  # noqa: E402  (sibling module in the same layer dir)
import build_fixture  # noqa: E402

# Family of the label-adjudication producers; the LLM-judge candidate must NOT be in this set
# (no-self-grade guard, advisor pt 2). Labels are produced by Claude + Codex families.
LABEL_ADJUDICATION_FAMILIES = frozenset({"claude", "codex"})

# Canary docs for the per-candidate liveness gate (obvious authoritative vs obvious garbage).
# Real, hand-written extremes — an FDA/Cochrane-style clinical body vs keyword-stuffed cookie spam.
_AUTHORITATIVE_CANARY_DOC = (
    "FULL PRESCRIBING INFORMATION. INDICATIONS AND USAGE. This randomized, double-blind, "
    "placebo-controlled trial enrolled 1,248 adults with type 2 diabetes mellitus. The primary "
    "endpoint was the change in HbA1c from baseline at 24 weeks. Treatment reduced HbA1c by 1.2 "
    "percentage points (95% confidence interval 1.0 to 1.4, p<0.001) versus placebo. Adverse "
    "events were consistent with the known safety profile. CONTRAINDICATIONS: known "
    "hypersensitivity to the active ingredient. DOSAGE AND ADMINISTRATION: the recommended "
    "starting dose is 5 mg once daily, titrated based on tolerability and glycemic response."
)
_GARBAGE_CANARY_DOC = (
    "Accept all cookies. Subscribe now for our newsletter! BEST cheap pills online buy now "
    "discount discount discount. cookie policy privacy policy terms of service all rights "
    "reserved. Click here click here click here. weight loss miracle cure buy cheap meds no "
    "prescription needed share this article sign up sign up sign up best deals best deals."
)


@dataclass
class Candidate:
    name: str
    impl_id: str
    license: str
    runnable: str            # "yes" | "no_key" | "needs_gpu"
    role: str                # "baseline" | "candidate" | "yardstick_non_sovereign" | "control"
    family: str              # model lineage tag (for the no-self-grade guard)
    loader: Optional[Callable[[], Callable[[str], float]]] = None  # load() -> scorer(text)->float
    notes: str = ""
    flags: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Candidate loaders. Each returns scorer(text)->float. Heavy imports INSIDE the
# loader so smoke can monkeypatch without importing torch/fasttext.
# ---------------------------------------------------------------------------
def _load_polaris_heuristic() -> Callable[[str], float]:
    """Baseline: POLARIS heuristic score_content_quality used as a RANKER (the 0..1 score is the
    weight), NOT as the document-gate drop it ships as (the gate stays default-OFF)."""
    from src.polaris_graph.retrieval.content_quality_gate import score_content_quality

    def scorer(text: str) -> float:
        score, _reasons = score_content_quality(text)
        return float(score)

    return scorer


def _load_dclm_fasttext() -> Callable[[str], float]:
    """DCLM OH-2.5+ELI5 fastText (mlfoundations/fasttext-oh-eli5). P(__label__hq) = the weight."""
    import fasttext  # noqa
    from huggingface_hub import hf_hub_download

    # resolve the .bin via the hub (exact filename varies; pick the single .bin in the repo).
    from huggingface_hub import list_repo_files
    files = list_repo_files("mlfoundations/fasttext-oh-eli5")
    bins = [f for f in files if f.endswith(".bin")]
    if not bins:
        raise RuntimeError("no .bin in mlfoundations/fasttext-oh-eli5")
    model_path = hf_hub_download("mlfoundations/fasttext-oh-eli5", bins[0])
    model = fasttext.load_model(model_path)

    def scorer(text: str) -> float:
        t = " ".join(text.split())[:100000]
        labels, probs = model.predict(t, k=2)
        d = {lab: float(p) for lab, p in zip(labels, probs)}
        return d.get("__label__hq", 0.0)

    return scorer


def _load_ultra_fineweb() -> Callable[[str], float]:
    """Ultra-FineWeb verification-loop fastText (openbmb/Ultra-FineWeb-classifier). Pred score of
    the high-quality label = the weight."""
    import fasttext  # noqa
    from huggingface_hub import hf_hub_download, list_repo_files
    files = list_repo_files("openbmb/Ultra-FineWeb-classifier")
    bins = [f for f in files if f.endswith(".bin")]
    if not bins:
        raise RuntimeError("no .bin in openbmb/Ultra-FineWeb-classifier")
    model_path = hf_hub_download("openbmb/Ultra-FineWeb-classifier", bins[0])
    model = fasttext.load_model(model_path)

    def scorer(text: str) -> float:
        t = " ".join(text.split())[:100000]
        labels, probs = model.predict(t, k=2)
        # high-quality label is the positive class; pick the max-prob positive-ish label
        d = {lab: float(p) for lab, p in zip(labels, probs)}
        for pos in ("__label__1", "__label__hq", "__label__pos"):
            if pos in d:
                return d[pos]
        # fallback: prob of the lexicographically-last label (positive convention varies)
        return d.get(sorted(d)[-1], 0.0) if d else 0.0

    return scorer


def _load_fineweb_edu() -> Callable[[str], float]:
    """FineWeb-Edu regression classifier (HuggingFaceFW/fineweb-edu-classifier). 0..5 educational
    score = the weight. Educational value is a quality PROXY, not clinical authority (honest)."""
    import torch  # noqa
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    mid = "HuggingFaceFW/fineweb-edu-classifier"
    tok = AutoTokenizer.from_pretrained(mid)
    model = AutoModelForSequenceClassification.from_pretrained(mid)
    model.eval()

    def scorer(text: str) -> float:
        inp = tok(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = model(**inp).logits
        return float(logits.squeeze(-1).item())

    return scorer


def _load_nemotron_cc() -> Callable[[str], float]:
    """Nemotron-CC ensemble: mean of the two NVIDIA arctic-embed edu heads (nemotron-4 + mixtral),
    each 0..5, mean-of-normalized per the Nemotron-CC paper. (DCLM fastText fusion is folded in by
    its own candidate; here we score the two NVIDIA heads' mean as the ensemble weight.)"""
    import torch  # noqa
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    ids = [
        "nvidia/nemocurator-fineweb-nemotron-4-edu-classifier",
        "nvidia/nemocurator-fineweb-mixtral-edu-classifier",
    ]
    heads = []
    for mid in ids:
        tok = AutoTokenizer.from_pretrained(mid)
        model = AutoModelForSequenceClassification.from_pretrained(mid)
        model.eval()
        heads.append((tok, model))

    def scorer(text: str) -> float:
        vals = []
        for tok, model in heads:
            inp = tok(text, return_tensors="pt", truncation=True, max_length=512)
            with torch.no_grad():
                logits = model(**inp).logits
            vals.append(float(logits.squeeze(-1).item()) / 5.0)  # normalize 0..5 -> 0..1
        return sum(vals) / len(vals)

    return scorer


def _load_essential_web() -> Callable[[str], float]:
    """Essential-Web EAI-Distill-0.5b taxonomy SLM (EssentialAI/eai-taxonomy-0.5b). Use the
    reasoning-depth / technical-correctness ordinal axis as the weight — NOT the topic (FDC) field
    (that would leak relevance). License under-specified on card (401) -> VERIFY-BEFORE-ADOPT.

    The taxonomy SLM emits a 12-field STRUCTURED label, not a scalar; the exact reasoning-depth
    field decode/parse must be finalized against the model card (pending the 401 resolution).
    Until then this loader FAILS LOUD AT LOAD TIME (status -> load_failed) rather than (a) wasting
    a 0.5B download to then liveness-fail, or (b) returning a fake number. Wire the parse before
    enabling this candidate. NOT wired yet — registered so it is never silently dropped."""
    raise RuntimeError(
        "eai-taxonomy-0.5b NOT wired: 12-field taxonomy reasoning-depth parse not finalized "
        "(card 401, VERIFY-BEFORE-ADOPT). Wire the structured-field decode before scoring; fail "
        "loud at load time instead of downloading a model only to return a fake/raising weight."
    )


def _load_glm_judge() -> Callable[[str], float]:
    """GLM-5.2 LLM-judge yardstick (OpenRouter z-ai/glm-5.1). no_key: registered but skipped here
    (informative ceiling only; an LLM-in-extraction-loop is a faithfulness hazard => never a
    production pick). Scored ONLY vs a DIFFERENT family's labels (no self-grading)."""
    raise RuntimeError("GLM-5.2 judge requires an API key (no_key) — registered but not run here.")


def build_registry() -> list[Candidate]:
    return [
        Candidate(
            name="polaris_heuristic",
            impl_id="src/polaris_graph/retrieval/content_quality_gate.py::score_content_quality",
            license="in-repo (POLARIS)", runnable="yes", role="baseline", family="polaris",
            loader=_load_polaris_heuristic,
            notes="incumbent floor, used as a ranker not a drop-gate",
        ),
        Candidate(
            name="dclm_fasttext",
            impl_id="mlfoundations/fasttext-oh-eli5",
            license="MIT (model) / Apache-2.0 (code)", runnable="yes", role="candidate",
            family="dclm", loader=_load_dclm_fasttext,
            notes="CPU fastText; REQUIRES numpy<2.0; P(__label__hq) is the weight",
            flags=["requires_numpy_lt_2"],
        ),
        Candidate(
            name="ultra_fineweb_fasttext",
            impl_id="openbmb/Ultra-FineWeb-classifier",
            license="Apache-2.0", runnable="yes", role="candidate", family="ultrafineweb",
            loader=_load_ultra_fineweb,
            notes="CPU fastText; REQUIRES numpy<2.0; Pred score (P high-quality) is the weight",
            flags=["requires_numpy_lt_2"],
        ),
        Candidate(
            name="fineweb_edu",
            impl_id="HuggingFaceFW/fineweb-edu-classifier",
            license="Apache-2.0", runnable="needs_gpu", role="candidate", family="finewebedu",
            loader=_load_fineweb_edu,
            notes="BERT/arctic-embed-m regression 0..5; educational PROXY, not clinical authority",
        ),
        Candidate(
            name="nemotron_cc_ensemble",
            impl_id="nvidia/nemocurator-fineweb-nemotron-4-edu-classifier + "
                    "nvidia/nemocurator-fineweb-mixtral-edu-classifier",
            license="NVIDIA Open Model License + Apache-2.0 (VERIFY commercial clause)",
            runnable="needs_gpu", role="candidate", family="nemotron",
            loader=_load_nemotron_cc,
            notes="mean-of-normalized 0..5 edu heads per Nemotron-CC paper",
            flags=["verify_commercial_license_before_adopt"],
        ),
        Candidate(
            name="essential_web_taxonomy",
            impl_id="EssentialAI/eai-taxonomy-0.5b",
            license="under-specified (card 401); base Qwen2.5-0.5B Apache-2.0 — VERIFY-BEFORE-ADOPT",
            runnable="needs_gpu", role="candidate", family="essentialweb",
            loader=_load_essential_web,
            notes="0.5B taxonomy SLM; reasoning-depth axis (NOT topic FDC field)",
            flags=["license_unverified_card_401", "parse_pending"],
        ),
        Candidate(
            name="glm52_llm_judge",
            impl_id="z-ai/glm-5.1 via OpenRouter (GLM-5.2 campaign backbone)",
            license="API (non-sovereign-as-judge; ceiling only)", runnable="no_key",
            role="yardstick_non_sovereign", family="glm", loader=_load_glm_judge,
            notes="ceiling yardstick; scored ONLY vs a different family's labels (no self-grade)",
        ),
    ]


# ---------------------------------------------------------------------------
# Negative controls (NOT candidates; exempt from semantic-direction liveness).
# ---------------------------------------------------------------------------
def constant_scorer(_text: str) -> float:
    return 0.5


def make_random_scorer(seed: int = 7) -> Callable[[str], float]:
    import random
    rng = random.Random(seed)
    return lambda _text: rng.random()


def _adjudicated_rows(rows: list[dict]) -> list[dict]:
    """Rows whose label has completed two-family + spot-check adjudication and so carry a
    scored_label. run_bakeoff scores ONLY these — a rubric proposal is never the scored label."""
    out = []
    for r in rows:
        if r.get("label_status") == "adjudicated" and r.get("scored_label") in (0, 1):
            out.append({**r, "label": r["scored_label"]})
    return out


def score_candidate(cand: Candidate, scoring_rows: list[dict]) -> dict:
    """Load + liveness-gate + score one candidate. Honest skip for no_key / needs_gpu-without-gpu."""
    result = {"name": cand.name, "role": cand.role, "runnable": cand.runnable,
              "impl_id": cand.impl_id, "license": cand.license, "family": cand.family,
              "flags": list(cand.flags), "status": None, "auc": None}

    # No-self-grade guard (advisor pt 2): an LLM-judge candidate must not be a label-adjudication
    # family — else it grades its own labels. Assert structurally so a future judge swap can't
    # silently reintroduce circularity.
    if cand.role.startswith("yardstick") or cand.family == "glm":
        if cand.family in LABEL_ADJUDICATION_FAMILIES:
            raise gate0.GateZeroQualityError(
                f"NO-SELF-GRADE violation: judge candidate family {cand.family!r} is in the "
                f"label-adjudication families {set(LABEL_ADJUDICATION_FAMILIES)} — it would grade "
                f"its own labels. Use a different-family label set for this candidate."
            )

    if cand.runnable == "no_key":
        result["status"] = "skipped_no_key"
        return result

    if cand.loader is None:
        result["status"] = "skipped_no_loader"
        return result

    if cand.runnable == "needs_gpu" and not _gpu_available():
        result["status"] = "skipped_needs_gpu"
        return result

    # Load -> scorer. A load failure is fail-loud non-functional, never a fake score.
    try:
        scorer = cand.loader()
    except Exception as exc:
        result["status"] = "load_failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    # Per-candidate LIVENESS canary (GATE-0 half B). Raises fail-loud on stub/constant/wrong-dir.
    try:
        live = gate0.assert_candidate_live(
            cand.name, scorer, _AUTHORITATIVE_CANARY_DOC, _GARBAGE_CANARY_DOC
        )
        result["liveness"] = live
    except gate0.GateZeroQualityError as exc:
        result["status"] = "liveness_failed"
        result["error"] = str(exc)
        return result

    if not scoring_rows:
        result["status"] = "no_adjudicated_rows"
        return result

    scored = [{**r, "score": float(scorer(r["post_extraction_body"]))} for r in scoring_rows]
    metric = gate0.paired_within_cell_auc(scored, score_key="score")
    result["n_pairs"] = metric["n_pairs"]
    result["n_cells_scored"] = metric["n_cells_scored"]
    result["n_cells_skipped"] = metric["n_cells_skipped"]
    # Zero-scorable-cell guard: a within-(topic x source_type) cell scores only when it holds
    # BOTH an authoritative and a spam item. If no cell qualifies, paired_within_cell_auc returns
    # auc=None — emit status 'no_scorable_cells', NEVER 'scored' with a misleading number. This is
    # the same fail-loud spirit as the provisional path: a ranking over empty cells is meaningless
    # (and would re-admit the source-type proxy this metric exists to kill).
    if metric["auc"] is None or metric["n_pairs"] == 0:
        result["status"] = "no_scorable_cells"
        result["auc"] = None
        return result
    result["status"] = "scored"
    result["auc"] = metric["auc"]
    return result


def _gpu_available() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def run(*, fixture_path: str, out_path: str, registry: Optional[list[Candidate]] = None) -> dict:
    """End-to-end: GATE-0 math canary -> load fixture -> score adjudicated rows -> ranked JSON."""
    # GATE-0 half A (scorer-math) FIRST. Raises fail-loud if mis-wired.
    math_report = gate0.run_scorer_math_canary()

    rows = build_fixture.load_fixture(fixture_path)
    scoring_rows = _adjudicated_rows(rows)
    provisional = len(scoring_rows) == 0

    registry = registry or build_registry()
    candidate_results = [score_candidate(c, scoring_rows) for c in registry]

    # Negative controls: assert they land near 0.5 — only meaningful when the fixture HAS scorable
    # within-cell pairs. If no cell holds both classes the control AUC is undefined (None); the
    # near-half assertion is undefined too, so we record controls as skipped rather than fail on a
    # degenerate fixture (the no_scorable_cells guard below carries that signal loudly).
    control_results = []
    if scoring_rows:
        for ctrl_name, ctrl in (("constant_0.5", constant_scorer),
                                ("random_seeded", make_random_scorer())):
            scored = [{**r, "score": float(ctrl(r["post_extraction_body"]))} for r in scoring_rows]
            metric = gate0.paired_within_cell_auc(scored, score_key="score")
            if metric["auc"] is None or metric["n_pairs"] == 0:
                control_results.append({"name": ctrl_name, "role": "control", "auc": None,
                                        "status": "skipped_no_scorable_cells"})
                continue
            gate0.assert_control_near_half(ctrl_name, metric["auc"])
            control_results.append({"name": ctrl_name, "role": "control", "auc": metric["auc"],
                                    "status": "scored_near_half"})

    scored_ok = [r for r in candidate_results if r["status"] == "scored" and r["auc"] is not None]
    ranked = sorted(scored_ok, key=lambda r: r["auc"], reverse=True)

    # Top-level fail-loud flag: if rows were adjudicated yet EVERY runnable candidate landed in
    # 'no_scorable_cells', the fixture has no within-(topic x source_type) cell with both classes
    # — the metric cannot rank anything. Surface it loudly rather than ship an empty ranking.
    runnable_attempts = [r for r in candidate_results
                         if r["status"] in ("scored", "no_scorable_cells")]
    all_no_cells = bool(runnable_attempts) and all(
        r["status"] == "no_scorable_cells" for r in runnable_attempts
    )

    report = {
        "layer": "quality_weight",
        "gate0_scorer_math": math_report,
        "fixture": fixture_path,
        "n_fixture_rows": len(rows),
        "n_adjudicated_rows": len(scoring_rows),
        "provisional": provisional,
        "provisional_reason": (
            "0 adjudicated rows: fixture labels are 'proposed' (two-family + operator spot-check "
            "pending). AUCs not emitted; candidates show liveness/skip status only. Adjudicate "
            "labels then re-run for a final ranking."
        ) if provisional else None,
        "no_scorable_cells_for_all_candidates": all_no_cells,
        "no_scorable_cells_reason": (
            "All runnable candidates returned no_scorable_cells: no within-(topic x source_type) "
            "cell holds BOTH an authoritative and a spam item. Root cause: the proposed-label "
            "rubric labels quality by DOMAIN IDENTITY, which is collinear with source_type, so "
            "same-source-type quality contrasts are absent. The two-family adjudication must "
            "deliberately add same-source-type contrasts (legit vs predatory journal, real gov vs "
            "gov-mimic farm, reputable outlet vs SEO health farm) before a ranking is valid."
        ) if all_no_cells else None,
        # Secondary metric KNOWN-NOT-YET-IMPLEMENTED (brief §4): recall-preservation guard =
        # fraction of adjudicated-authoritative sources landing in the bottom weight-decile must
        # stay near zero (weight never demotes a real authoritative source). Moot until adjudicated
        # rows exist; flagged here so it is not silently dropped.
        "recall_preservation_guard": "not_yet_implemented (pending adjudicated rows; brief §4 "
                                      "secondary — authoritative-in-bottom-decile must be ~0)",
        "candidates": candidate_results,
        "controls": control_results,
        "ranking": [{"name": r["name"], "auc": r["auc"]} for r in ranked],
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", default=os.path.join(_HERE, "clinical_quality_weight_fixture.jsonl"))
    ap.add_argument("--out", default=os.path.join(_HERE, "quality_weight_results.json"))
    args = ap.parse_args(argv)
    try:
        report = run(fixture_path=args.fixture, out_path=args.out)
    except gate0.GateZeroQualityError as exc:
        print(f"GATE-0 FAIL (no score trusted): {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"{exc}", file=sys.stderr)
        return 1
    print(f"quality_weight bake-off: {len(report['candidates'])} candidates, "
          f"{report['n_adjudicated_rows']} adjudicated rows "
          f"(provisional={report['provisional']})")
    for c in report["candidates"]:
        auc = "n/a" if c["auc"] is None else f"{c['auc']:.4f}"
        print(f"  [{c['status']:>18}] {c['name']:<24} auc={auc}")
    for ctrl in report["controls"]:
        cauc = "n/a" if ctrl["auc"] is None else f"{ctrl['auc']:.4f}"
        print(f"  [{ctrl['status']:>18}] {ctrl['name']:<24} auc={cauc}")
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
