#!/usr/bin/env python3
"""One-command FULL-CORPUS cp4_used=agentic sweep — the mission's metric-(a) full-corpus gate.

Runs the agentic outliner (``run_outline_agent_or_legacy`` with ``PG_OUTLINE_AGENT=1`` +
the §9.1.8 model lock) over one or many saved cp3 corpora and ASSERTS, per corpus, the mission
invariant:

    cp4_used == "agentic"

NEVER fallback-plain. A seed fallback (``cp4_used == "agentic-degraded-seed"``) is accepted ONLY
when the degrade reason is a GLM-5.2 reasoning truncation (``ReasoningFirstTruncationError``,
openrouter_client.py:257) — the ONE sanctioned degrade. Any other degrade reason, or the plain
non-agentic path, is a HARD FAIL (a silent capability downgrade the operator never asked for).

It also records whether the MOAT is ARMED for that corpus: the agentic loop must export a
verified-compute registry (``quantified_models``) AND per-section render-ready ``[#calc:]``
sentences (``calc_claims``) so a computed number will RENDER through the verified lane
(metric (a)). The sweep does NOT itself score RACE/DeepTRACE — that is the downstream evaluator on
the composed report — but it proves the agentic path ran end-to-end over the full corpus and the
moat is live, which is the precondition metric (a)-full-corpus needs.

Usage:
    # real run (needs OPENROUTER_API_KEY):
    python scripts/outline_agentic_sweep.py --corpus path/to/corpus.json
    python scripts/outline_agentic_sweep.py --corpus-dir outputs/corpora/ --min-baskets 300

    # offline self-check of the assertion machinery (no LLM, no keys):
    python scripts/outline_agentic_sweep.py --dry-run

Corpus JSON shape (a saved cp3 stage dump):
    {"research_question": str, "evidence": [ {evidence_id, ...}, ... ],
     "finding_clusters": [...]  (optional), "same_work_groups": [...] (optional),
     "domain": str (optional)}

Exit codes: 0 = every corpus PASSED the invariant (or dry-run self-check passed);
            1 = at least one corpus FAILED the invariant;
            2 = BLOCKED before any run (missing credentials / no corpus) — never a fake pass.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The ONE sanctioned degrade signature (GLM-5.2 reasoning prelude exceeding the completion budget).
_SANCTIONED_DEGRADE_MARKER = "ReasoningFirstTruncationError"


def _classify(cp4_used: str, degrade_reason: str) -> tuple[bool, str]:
    """The mission invariant, in one place. Returns (passed, verdict_reason)."""
    if cp4_used == "agentic":
        return True, "agentic (full path, no degrade)"
    if cp4_used == "agentic-degraded-seed":
        if _SANCTIONED_DEGRADE_MARKER in (degrade_reason or ""):
            return True, f"agentic-degraded-seed via sanctioned GLM-5.2 truncation ({degrade_reason[:80]})"
        return False, (
            f"FAIL: degraded to seed for a NON-truncation reason ({degrade_reason[:120]}) — "
            "only ReasoningFirstTruncationError may fall back to seed"
        )
    # anything else (missing block, "plain", legacy) is a silent capability downgrade
    return False, f"FAIL: cp4_used={cp4_used!r} is not agentic (fallback-plain is forbidden)"


def _count_baskets(finding_clusters) -> int:
    """TOTAL baskets in the corpus = every cp3 claim-group cluster (singletons INCLUDED).

    The cp3 snapshot's canonical "N-basket corpus" size counts ALL claim groups, not only the
    multi-member ones — the s3gear full corpus is 329 baskets (38 multi-member + 291 singletons).
    Counting only ``member_indices>=2`` clusters undercounts to 38 and made ``--min-baskets 346``
    (a size no persisted corpus has) unsatisfiable; the mission's full-corpus assertion is
    ``--min-baskets 328`` against this total. Duck-typed over dict or object clusters.
    """
    return len(finding_clusters or [])


async def _run_one(corpus_path: Path, min_baskets: int) -> dict:
    """Run the agentic outliner over ONE corpus and evaluate the invariant. Real LLM path."""
    from src.polaris_graph.outline.outline_agent import (  # noqa: PLC0415
        outliner_agent_model, outliner_code_model, run_outline_agent_or_legacy,
    )

    corpus = json.loads(corpus_path.read_text())
    rq = corpus["research_question"]
    evidence = corpus["evidence"]
    raw_clusters = corpus.get("finding_clusters") or []
    # A corpus loaded from JSON carries clusters as dicts, but ``build_outline_digest`` duck-types
    # over ``FindingCluster`` via ATTRIBUTE access (getattr(c, "member_indices"), etc.). Passing bare
    # dicts would silently yield zero baskets (getattr -> default), a capability downgrade. Wrap each
    # dict as a SimpleNamespace so member_indices/representative_index resolve as attributes.
    from types import SimpleNamespace  # noqa: PLC0415
    clusters = [SimpleNamespace(**c) if isinstance(c, dict) else c for c in raw_clusters]
    swg = corpus.get("same_work_groups")
    domain = corpus.get("domain", "")
    n_baskets = _count_baskets(clusters)

    parse_result, _retry, _in, _out = await run_outline_agent_or_legacy(
        rq, evidence, outliner_code_model(), 0.2, 2500,
        domain=domain, finding_clusters=clusters, same_work_groups=swg,
    )
    oa = dict((parse_result.digest_stats or {}).get("outline_agent") or {})
    cp4_used = str(oa.get("cp4_used", "MISSING"))
    degrade_reason = str(oa.get("degrade_reason", ""))
    passed, verdict = _classify(cp4_used, degrade_reason)

    qmodels = getattr(parse_result, "quantified_models", None) or {}
    calc_claims = getattr(parse_result, "calc_claims", None) or {}
    moat_armed = bool(qmodels) and bool(calc_claims)

    # Observability tripwire (per-corpus): count how many DOI/title groups hit the same-work
    # false-merge REFUSAL branch on THIS corpus. Empirically ZERO on the real 346-basket cp3 dump
    # (no DOI spans >= 2 cp3 groups); surfaced here so a live sweep makes any breach VISIBLE rather
    # than silent. Computed directly off the corpus (independent of the agent's own digest build).
    from src.polaris_graph.generator.outline_digest import _build_alias_map  # noqa: PLC0415
    _guard_stats: dict[str, int] = {}
    _build_alias_map(swg, evidence, stats=_guard_stats)
    doi_guard_hits = _guard_stats.get("doi_false_merge_guard_hits", 0)
    title_guard_hits = _guard_stats.get("title_false_merge_guard_hits", 0)

    basket_ok = n_baskets >= min_baskets
    return {
        "corpus": corpus_path.name,
        "research_question": rq[:120],
        "baskets": n_baskets,
        "baskets_ok": basket_ok,
        "min_baskets": min_baskets,
        "cp4_used": cp4_used,
        "degrade_reason": degrade_reason[:200],
        "turns": oa.get("turns"),
        "ev_store_size": oa.get("ev_store_size"),
        "new_evidence": oa.get("new_evidence_count"),
        "quantified_models": len(qmodels),
        "calc_claim_sections": len(calc_claims),
        "moat_armed": moat_armed,
        "doi_false_merge_guard_hits": doi_guard_hits,
        "title_false_merge_guard_hits": title_guard_hits,
        "invariant_passed": passed and basket_ok,
        "verdict": verdict + ("" if basket_ok else f" | baskets {n_baskets} < min {min_baskets}"),
        "agent_model": outliner_agent_model(),
        "code_model": outliner_code_model(),
    }


def preflight_corpus(corpus_path: Path, min_baskets: int) -> tuple[bool, str]:
    """OFFLINE (no LLM) loadability check for one persisted corpus.

    Exercises the exact offline-checkable portion of ``_run_one``: parse JSON, wrap clusters as the
    attribute-accessed objects ``build_outline_digest`` expects, count TOTAL baskets, and assert
    every ``member_indices``/``representative_index`` resolves into the attached evidence pool. This
    is what proves the corpus is key-drop-ready before credentials land. Returns (ok, message).
    """
    from types import SimpleNamespace  # noqa: PLC0415
    try:
        corpus = json.loads(corpus_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return False, f"unreadable JSON: {exc}"
    for key in ("research_question", "evidence", "finding_clusters"):
        if key not in corpus:
            return False, f"missing required key {key!r}"
    evidence = corpus["evidence"]
    n_ev = len(evidence)
    raw_clusters = corpus.get("finding_clusters") or []
    clusters = [SimpleNamespace(**c) if isinstance(c, dict) else c for c in raw_clusters]
    n_baskets = _count_baskets(clusters)
    # every index a downstream consumer will dereference must be in-range
    bad = 0
    for c in clusters:
        idxs = list(getattr(c, "member_indices", []) or [])
        rep = getattr(c, "representative_index", None)
        if rep is not None:
            idxs.append(rep)
        for i in idxs:
            if not isinstance(i, int) or i < 0 or i >= n_ev:
                bad += 1
    if bad:
        return False, f"{bad} member/representative indices out of range for a {n_ev}-row pool"
    if n_baskets < min_baskets:
        return False, f"baskets {n_baskets} < min {min_baskets}"
    return True, (f"loadable: {n_baskets} baskets (>= {min_baskets}), {n_ev}-row pool, all indices "
                  "resolve")


def _dry_run_selfcheck(corpus_paths: list[Path] | None = None, min_baskets: int = 1) -> int:
    """Exercise the invariant machinery OFFLINE (no LLM, no keys) so we know the assertions are
    sound before credentials land. Four cases cover the whole decision surface. When ``corpus_paths``
    are given, ALSO preflight each corpus for loadability (parse, cluster-wrap, basket count, index
    resolution) so the mission's key-drop-ready proof runs offline against the real corpus."""
    cases = [
        ("agentic", "", True, "clean agentic path passes"),
        ("agentic-degraded-seed",
         "ReasoningFirstTruncationError: reasoning prelude exceeded completion budget",
         True, "sanctioned GLM-5.2 truncation degrade passes"),
        ("agentic-degraded-seed", "TimeoutError: agent wall exceeded", False,
         "non-truncation degrade FAILS"),
        ("plain", "", False, "fallback-plain FAILS"),
        ("MISSING", "", False, "missing cp4 block FAILS"),
    ]
    ok = True
    print("DRY-RUN self-check of the cp4_used invariant (_classify):")
    for cp4, reason, expect_pass, label in cases:
        passed, verdict = _classify(cp4, reason)
        mark = "OK " if passed == expect_pass else "BAD"
        if passed != expect_pass:
            ok = False
        print(f"  [{mark}] cp4_used={cp4!r:26} expect_pass={expect_pass!s:5} -> {passed!s:5} | {label}")
        print(f"        verdict: {verdict}")
    # basket counter check — TOTAL baskets = every cluster (singletons included)
    fake_clusters = [{"member_indices": [1, 2]}, {"member_indices": [3]}, {"member_indices": [4, 5, 6]}]
    nb = _count_baskets(fake_clusters)
    mark = "OK " if nb == 3 else "BAD"
    if nb != 3:
        ok = False
    print(f"  [{mark}] _count_baskets -> {nb} (expected 3: TOTAL clusters, singletons included)")

    for cp in corpus_paths or []:
        if not cp.exists():
            print(f"  [BAD] corpus preflight: {cp} does not exist")
            ok = False
            continue
        cok, msg = preflight_corpus(cp, min_baskets)
        print(f"  [{'OK ' if cok else 'BAD'}] corpus preflight {cp.name}: {msg}")
        if not cok:
            ok = False

    print("\nDRY-RUN", "PASSED — assertion machinery sound." if ok else "FAILED.")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=str, help="a single corpus JSON")
    ap.add_argument("--corpus-dir", type=str, help="a dir of corpus JSONs (one run each)")
    ap.add_argument("--min-baskets", type=int, default=1,
                    help="assert each corpus has >= this many TOTAL baskets (default 1; the s3gear "
                         "full corpus is 329 baskets — assert it with --min-baskets 328)")
    ap.add_argument("--out", type=str, default="outputs/agentic_sweep/summary.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline self-check of the assertion machinery (no LLM, no keys)")
    args = ap.parse_args()

    if args.dry_run:
        _dry_paths: list[Path] = []
        if args.corpus:
            _dry_paths.append(Path(args.corpus))
        if args.corpus_dir:
            _dry_paths.extend(sorted(Path(args.corpus_dir).glob("*.json")))
        return _dry_run_selfcheck(_dry_paths, args.min_baskets)

    # ── LAW VI: pin the seat + model lock for the sweep (env override still wins if pre-set) ──
    os.environ.setdefault("PG_OUTLINE_AGENT", "1")

    # ── HONEST BLOCKER: never fake a pass when the LLM cannot be called ──
    if not os.getenv("OPENROUTER_API_KEY"):
        print("BLOCKED: OPENROUTER_API_KEY is not set — the agentic outliner cannot call GLM-5.2.")
        print("  Present LLM-relevant env:",
              [k for k in os.environ if "API" in k or "KEY" in k or "TOKEN" in k] or "(none)")
        print("  This is the sole remaining gate for metric (a)-full-corpus. Run this exact command")
        print("  the instant credentials land; it will produce the cp4_used=agentic verdict per corpus.")
        print("  (Meanwhile: `--dry-run` proves the assertion machinery is sound offline.)")
        return 2

    if os.environ.get("PG_OUTLINE_AGENT") not in ("1", "true", "True", "on"):
        print("BLOCKED: PG_OUTLINE_AGENT is disabled — refusing to run a non-agentic 'agentic' sweep.")
        return 2

    corpora: list[Path] = []
    if args.corpus:
        corpora.append(Path(args.corpus))
    if args.corpus_dir:
        corpora.extend(sorted(Path(args.corpus_dir).glob("*.json")))
    corpora = [p for p in corpora if p.exists()]
    if not corpora:
        print("BLOCKED: no corpus given/found. Pass --corpus <file> or --corpus-dir <dir>.")
        print("  Build the full corpus first: python scripts/cp3_to_cp4_corpus.py")
        print("  then: --corpus data/cp4_corpus_s3gear_329.json --min-baskets 328 (329-basket corpus).")
        return 2

    results = [asyncio.run(_run_one(p, args.min_baskets)) for p in corpora]

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_pass = sum(1 for r in results if r["invariant_passed"])
    n_moat = sum(1 for r in results if r["moat_armed"])
    summary = {
        "corpora": len(results), "passed": n_pass, "failed": len(results) - n_pass,
        "moat_armed": n_moat, "results": results,
    }
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"\nAGENTIC SWEEP: {len(results)} corpus/corpora, {n_pass} PASSED the cp4_used=agentic invariant, "
          f"{n_moat} moat-armed")
    for r in results:
        mark = "PASS" if r["invariant_passed"] else "FAIL"
        print(f"  [{mark}] {r['corpus']}: cp4_used={r['cp4_used']} baskets={r['baskets']} "
              f"qmodels={r['quantified_models']} calc_sections={r['calc_claim_sections']} "
              f"moat_armed={r['moat_armed']}")
        # Observability: DOI/title false-merge REFUSAL count. Expected 0 on the real corpus; a
        # non-zero here means two multi-member cp3 works shared a DOI/title and the fold declined
        # to merge them — the zero-incidence assumption broke and warrants a key-level remap look.
        _dg = r.get("doi_false_merge_guard_hits", 0)
        _tg = r.get("title_false_merge_guard_hits", 0)
        _flag = "  <-- NON-ZERO: audit union-find assumption" if (_dg or _tg) else ""
        print(f"         false_merge_guard_hits: doi={_dg} title={_tg}{_flag}")
        print(f"         {r['verdict']}")
    print(f"\nsummary: {out_path}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
