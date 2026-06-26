#!/usr/bin/env python3
"""I-wire-002 (#1316): back-half REPLAY preflight harness (NO stubs, NO judge mocks).

Loads a banked ``corpus_snapshot.json`` (stage=pre_generation, with the billed
``evidence_for_gen`` rows + empty section_drafts) and drives the REAL PRODUCTION
back-half through the SAME entrypoint the paid benchmark uses
(``scripts.dr_benchmark.run_gate_b.run_gate_b_query(..., resume=True)``), with the
14 winner flags honored from the environment exactly as production reads them.

Why ``run_gate_b_query`` and NOT a hand-wired sub-function chain (advisor call,
this session): the post-generation glue — the 4-role D8 seam (release withhold),
the ``abort_report_redaction_failed`` reconciliation, and the report.md assembly —
IS faithfulness-critical logic. Re-implementing it would be exactly the
"committed+green != wired" false-confidence failure this replay harness exists to
catch (CLAUDE.md §-1.4, memory feedback_trace_path_replay_harness). So the harness
reconstructs the run ENTRY (the ``q`` dict + ``out_root``, the same state the
production ``--resume`` reconstructs) and lets the REAL back-half run end-to-end.

Production chain this exercises (file:func — proof it is NOT stubbed):
  - resume re-entry / state reconstruct ... scripts/run_honest_sweep_r3.py:run_one_query
  - back-half production entrypoint ....... scripts/dr_benchmark/run_gate_b.py:run_gate_b_query
  - consolidation (finding baskets) ....... src/polaris_graph/synthesis/finding_dedup.py:dedup_by_finding
  - consolidation NLI companion ........... src/polaris_graph/synthesis/consolidation_nli.py
  - adequacy (CRAG classifier) ............ src/polaris_graph/nodes/crag_adequacy_loop.py
  - composition (multi-section) ........... src/polaris_graph/generator/multi_section_generator.py:generate_multi_section_report
  - composition (abstractive writer) ...... src/polaris_graph/generator/abstractive_writer.py
  - per-sentence faithfulness ............. src/polaris_graph/generator/provenance_generator.py:strict_verify
  - 4-role D8 faithfulness seam ........... src/polaris_graph/roles/sweep_integration.py:run_four_role_seam
  - render (report.md assembly) ........... scripts/run_honest_sweep_r3.py:assemble_report_md (via run_one_query)

LAW VI: every parameter is a CLI arg or a PG_* env read — nothing is hardcoded.
This harness writes a REAL report.md; it does NOT mock the GLM client or any judge.

Usage (on drb_72, on the VM):
    python3 scripts/iwire002_backhalf_replay_preflight.py \
        --snapshot /root/polaris/outputs/<run>/clinical/clinical_tirzepatide_t2dm/corpus_snapshot.json \
        --out-root /root/polaris/outputs/iwire002_replay
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Repository root on sys.path so ``scripts.*`` / ``src.*`` import exactly as the
# production sweep does (run_one_query, run_gate_b_query, the generator chain).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# I-wire-013 (#1327): exercise the render chrome-as-claim CANARY in ENFORCE on the replay (the
# back-half this harness certifies must REFUSE a chrome-saturated report.md, not just log it).
# ``setdefault`` keeps an explicit operator diagnostic override (e.g. "off") while making enforce the
# replay default. run_gate_b_query ALSO force-pins this via the full-capability slate (defense-in-depth).
os.environ.setdefault("PG_RENDER_CHROME_CANARY", "enforce")


# ---------------------------------------------------------------------------
# Snapshot load + entry reconstruction (the SAME state production --resume rebuilds)
# ---------------------------------------------------------------------------
def load_snapshot(snapshot_path: Path) -> dict[str, Any]:
    """Load the banked corpus_snapshot.json. Fail loud on a missing/corrupt file
    (LAW II — never silently return an empty corpus)."""
    if not snapshot_path.is_file():
        raise FileNotFoundError(f"corpus_snapshot not found: {snapshot_path}")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"corpus_snapshot is not a JSON object: {snapshot_path}")
    stage = payload.get("stage")
    if stage and stage != "pre_generation":
        # Disclose, do not silently proceed — the back-half expects a pre-generation snapshot.
        print(
            f"[replay] WARNING: snapshot stage={stage!r} (expected 'pre_generation'); "
            "proceeding but the back-half re-entry assumes a pre-generation corpus."
        )
    return payload


def reconstruct_query(payload: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct the ``q`` dict the back-half re-entry needs, from the matching
    ``SWEEP_QUERIES`` entry (which carries the ``amplified`` set the resume path
    may reference) keyed by the snapshot's slug.

    GATE0-RESUME (run_honest_sweep_r3.py:5538) fails loud if ``q['question']`` does
    not match the snapshot's question — so we VERIFY the match here, before billing.
    """
    from scripts.run_honest_sweep_r3 import SWEEP_QUERIES

    snap_slug = payload.get("slug")
    snap_question = payload.get("question")
    if not snap_slug:
        raise ValueError("corpus_snapshot has no 'slug' — cannot reconstruct the query entry")

    match = next((qq for qq in SWEEP_QUERIES if qq.get("slug") == snap_slug), None)
    if match is None:
        raise ValueError(
            f"snapshot slug={snap_slug!r} has no matching SWEEP_QUERIES entry — "
            "cannot reconstruct the production query without inventing one (LAW II)"
        )

    # Verify the GATE0 question identity BEFORE the run (fail loud, not at re-entry).
    from scripts.dr_benchmark.gate0_lineage import sha256_text as _sha

    if snap_question and _sha(snap_question) != _sha(match["question"]):
        raise ValueError(
            "GATE0-RESUME mismatch: snapshot question != SWEEP_QUERIES question for slug "
            f"{snap_slug!r}. snapshot(sha)={_sha(snap_question)[:16]} "
            f"sweep(sha)={_sha(match['question'])[:16]} — refusing to replay on a "
            "split-brain corpus."
        )
    return dict(match)


def resolve_out_root(snapshot_path: Path, payload: dict[str, Any], cli_out_root: Path | None) -> Path:
    """Resolve ``out_root`` so that ``out_root/<domain>/<slug>`` is the directory that
    holds the snapshot — that nesting is how run_one_query locates the run_dir + the
    corpus_snapshot.json on the resume path (run_honest_sweep_r3.py:5303).

    The snapshot lives at ``<out_root>/<domain>/<slug>/corpus_snapshot.json``, so the
    run_dir is the snapshot's parent and out_root is run_dir.parent.parent.
    """
    run_dir = snapshot_path.resolve().parent
    domain = payload.get("domain", "")
    slug = payload.get("slug", "")
    in_place_out_root = run_dir.parent.parent

    if cli_out_root is None:
        # Replay IN PLACE against the banked run_dir (the resume path reads its
        # snapshot from here). This is the faithful default.
        return in_place_out_root

    # An explicit --out-root: COPY the snapshot into the mirrored nesting so the
    # resume path finds it, leaving the banked corpus untouched.
    target_run_dir = cli_out_root / domain / slug
    target_run_dir.mkdir(parents=True, exist_ok=True)
    target_snapshot = target_run_dir / "corpus_snapshot.json"
    if target_snapshot.resolve() != snapshot_path.resolve():
        target_snapshot.write_text(snapshot_path.read_text(encoding="utf-8"), encoding="utf-8")
    return cli_out_root


# ---------------------------------------------------------------------------
# Input-row assertions (c) + (d): proof the UPSTREAM wiring fired, read off the
# snapshot's billed evidence_for_gen rows (these stages do NOT re-run on resume).
# ---------------------------------------------------------------------------
def _evidence_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (payload.get("evidence_for_gen") or []) if isinstance(r, dict)]


def assert_content_relevance_weight(payload: dict[str, Any]) -> tuple[bool, str]:
    """(c) content_relevance_weight present on evidence rows (W2 winner fired)."""
    rows = _evidence_rows(payload)
    if not rows:
        return False, "no evidence_for_gen rows in snapshot"
    with_weight = [r for r in rows if "content_relevance_weight" in r]
    labels = {str(r.get("content_relevance_label", "")) for r in rows if r.get("content_relevance_label")}
    ok = len(with_weight) > 0
    return ok, (
        f"{len(with_weight)}/{len(rows)} rows carry content_relevance_weight; "
        f"distinct labels={sorted(labels)[:5]}"
    )


def assert_cred_tier(payload: dict[str, Any]) -> tuple[bool, str]:
    """(d) credibility tier present on evidence rows AND not floor-only (more than a
    single uniform tier => the tier classifier / weighting actually ran)."""
    rows = _evidence_rows(payload)
    if not rows:
        return False, "no evidence_for_gen rows in snapshot"
    tiers = [str(r.get("tier") or r.get("credibility_tier") or "") for r in rows]
    present = [t for t in tiers if t and t.upper() != "UNKNOWN"]
    distinct = sorted(set(present))
    authority = [r.get("authority_score") for r in rows if r.get("authority_score") is not None]
    distinct_auth = sorted({round(float(a), 3) for a in authority if isinstance(a, (int, float))})
    # floor-only would be a single uniform tier with a single uniform authority score.
    ok = len(present) > 0 and (len(distinct) > 1 or len(distinct_auth) > 1)
    return ok, (
        f"{len(present)}/{len(rows)} rows tiered; distinct tiers={distinct[:8]}; "
        f"distinct authority_score buckets={len(distinct_auth)}"
    )


# ---------------------------------------------------------------------------
# Output assertions (a),(b),(e),(f),(g): read off the REAL manifest.json +
# report.md the back-half produced.
# ---------------------------------------------------------------------------
def _load_manifest(run_dir: Path) -> dict[str, Any]:
    mpath = run_dir / "manifest.json"
    if not mpath.is_file():
        return {}
    try:
        return json.loads(mpath.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a malformed manifest is itself a FAIL signal
        return {}


def assert_completed(summary: dict[str, Any], manifest: dict[str, Any], run_dir: Path) -> tuple[bool, str]:
    """(a) completed with no UnboundLocalError / hang. The harness already survived the
    await without raising; a hang would have tripped the run-level wall-clock and set
    run_id='timeout'. Reject those terminal signals."""
    status = str(summary.get("status") or manifest.get("status") or "")
    run_id = str(summary.get("run_id") or "")
    err = str(summary.get("error") or "")
    hung = run_id == "timeout" or "wall-clock exceeded" in err
    crashed = "UnboundLocalError" in err or status.startswith("error_")
    # I-wire-002 #1316 iter-2 P1 fix: the canary MUST mirror the paid Gate-B success
    # policy exactly — a status the real paid run would FAIL (released_with_disclosed_gaps,
    # abort_*, partial_* unless the operator opts into partials) must NOT green-light the
    # preflight. `status != ""` was too lenient. query_status_ok = success-only (+ optional
    # partial); gate_b_allow_partial() reads the same operator knob the paid launcher reads.
    from scripts.dr_benchmark.run_gate_b import gate_b_allow_partial, query_status_ok

    ok = not hung and not crashed and query_status_ok(status, allow_partial=gate_b_allow_partial())
    return ok, f"status={status!r} run_id={run_id!r} error={err[:120]!r}"


def assert_consolidation_collapsed(manifest: dict[str, Any], run_dir: Path) -> tuple[bool, str]:
    """(b) the NLI CONSOLIDATION WINNER fired: same-claim paraphrase clusters merged > 0.

    The consolidation winner is the bidirectional-NLI seam (`PG_CONSOLIDATION_NLI`,
    I-wire-001 W1 #1306) which runs as a post-step OVER the literal finding-dedup
    clusters in src/polaris_graph/synthesis/finding_dedup.py:dedup_by_finding (this
    block RE-RUNS on the resume replay — it sits between the snapshot reload and the
    snapshot save, with no resume-skip guard). It MERGES literal clusters into larger
    same-claim baskets.

    The WINNER's purpose-built behavioral canary is FindingDedupResult.nli_merge_count
    (docstring: ">0 proves the NLI merged same-claim paraphrases the literal floor left
    separate"). The harness PRIMARY-asserts THAT signal — surfaced into
    manifest['finding_dedup']['nli_merge_count'] by the companion one-line wiring in
    this same I-wire-002 change. The legacy `collapsed_row_count` is NOT sufficient:
    it fires from the slate-forced literal duplicate-key collapse (PG_USE_FINDING_DEDUP)
    independently of the NLI winner, so a green on it alone would be the exact
    "winner green but never fired" false-PASS this harness exists to catch.

    PASS requires nli_merge_count > 0 (the winner actually merged a paraphrase basket).
    If the key is ABSENT (older run / pre-wiring manifest), the harness FAILS LOUD and
    discloses the gap — it does NOT silently fall back to the legacy collapse.
    """
    fd = manifest.get("finding_dedup")
    if not isinstance(fd, dict):
        return False, (
            "manifest['finding_dedup'] absent — finding-dedup/NLI consolidation did not "
            "run or did not record telemetry (consolidation winner not observable)"
        )
    nli_merge = fd.get("nli_merge_count")
    collapsed = fd.get("collapsed_row_count")
    clusters = fd.get("clusters") or []
    multi_source_baskets = sum(
        1 for c in clusters
        if isinstance(c, dict) and int(c.get("corroboration_count") or 0) > 1
    )
    if nli_merge is None:
        # The winner-specific signal is missing — refuse to certify on the legacy collapse.
        return False, (
            "manifest.finding_dedup.nli_merge_count ABSENT (NLI consolidation winner not "
            f"surfaced; legacy collapsed_row_count={collapsed}, multi_source_baskets="
            f"{multi_source_baskets}). The NLI winner signal is required — refusing to "
            "PASS on the slate-forced literal collapse alone (§-1.1 false-green guard)."
        )
    ok = int(nli_merge) > 0
    return ok, (
        f"manifest.finding_dedup.nli_merge_count={nli_merge} (NLI winner merges); "
        f"legacy collapsed_row_count={collapsed}; multi_source_baskets={multi_source_baskets}"
    )


def assert_abstractive(run_dir: Path, payload: dict[str, Any]) -> tuple[bool, str]:
    """(e) composition is abstractive (the report is NOT a single evidence span copied
    out wholesale). A legitimate block quote of one span is fine; the failure mode is a
    report that IS essentially one verbatim span (extractive, no synthesis). So the
    guard is the span-coverage RATIO: the longest single evidence span must not account
    for the bulk of the body. A >25-word quote inside a much larger report passes."""
    report = run_dir / "report.md"
    if not report.is_file():
        return False, "report.md absent — cannot judge abstractiveness"
    body = report.read_text(encoding="utf-8", errors="replace")
    body_words = [w for w in body.split() if w]
    if len(body_words) < 40:
        return False, f"report body too short to be abstractive ({len(body_words)} words)"
    spans = [
        str(r.get("direct_quote") or r.get("statement") or "")
        for r in _evidence_rows(payload)
    ]
    longest = max(spans, key=len) if spans else ""
    longest_words = len(longest.split())
    verbatim_present = bool(longest) and longest_words > 25 and longest.strip() in body
    # Extractive copy = one span verbatim AND it dominates the body (>= 60% of words).
    coverage = (longest_words / len(body_words)) if body_words else 0.0
    extractive_dump = verbatim_present and coverage >= 0.60
    ok = not extractive_dump
    return ok, (
        f"report body words={len(body_words)}; longest_evidence_span_words={longest_words}; "
        f"span_coverage={coverage:.0%}; verbatim_span_present={verbatim_present}; "
        f"extractive_dump={extractive_dump}"
    )


def assert_faithfulness_ran(manifest: dict[str, Any], run_dir: Path) -> tuple[bool, str]:
    """(f) the faithfulness engine RAN and was NOT bypassed: BOTH the 4-role D8 seam
    produced final_verdicts (non-empty, i.e. the gate adjudicated) AND strict_verify
    recorded per-sentence checks (verified/dropped present). Honest scope: this
    certifies the engine EXECUTED and ENFORCED (it dropped/adjudicated), not a
    threshold-by-threshold relaxation diff — that the env did not flip a gate OFF is
    proved by the slate's fail-CLOSED preflight (run_gate_b.preflight_full_capability /
    F07 strict-gates), which the run already passed to reach generation."""
    fr = manifest.get("four_role_evaluation") or {}
    final_verdicts = fr.get("final_verdicts") or {}
    audit_present = (run_dir / "four_role_claim_audit.json").is_file()
    verify_details = (run_dir / "verification_details.json").is_file()
    verified = manifest.get("total_sentences_verified")
    dropped = manifest.get("total_sentences_dropped")
    four_role_ran = bool(final_verdicts) or audit_present
    strict_ran = verify_details or isinstance(verified, int) or isinstance(dropped, int)
    ok = four_role_ran and strict_ran
    return ok, (
        f"four_role.final_verdicts={len(final_verdicts)} audit_json={audit_present} "
        f"verification_details={verify_details} verified={verified} dropped={dropped}"
    )


def assert_report_nonempty_cited(run_dir: Path) -> tuple[bool, str]:
    """(g) report.md is non-empty AND carries citations (provenance tokens or numbered refs)."""
    report = run_dir / "report.md"
    if not report.is_file():
        return False, "report.md does not exist"
    body = report.read_text(encoding="utf-8", errors="replace")
    nonempty = len(body.strip()) > 200
    has_provenance = "[#ev:" in body
    has_numbered = "](#ref" in body or "[^" in body or "## References" in body or "## Bibliography" in body
    cited = has_provenance or has_numbered
    ok = nonempty and cited
    return ok, (
        f"report bytes={len(body)} provenance_tokens={has_provenance} "
        f"numbered/biblio={has_numbered}"
    )


# ---------------------------------------------------------------------------
# Drive the REAL production back-half and report a-g.
# ---------------------------------------------------------------------------
async def _run_backhalf(q: dict[str, Any], out_root: Path, resume: bool) -> dict[str, Any]:
    """Invoke the SAME production entrypoint the paid Gate-B benchmark uses. It builds
    the REAL verifier transport + the native 4-role input builder, applies the full-
    capability slate, and calls run_one_query(resume=...) under the wall-clock guard.
    NO stub, NO fake transport (that path is only for the offline seam unit test)."""
    from scripts.dr_benchmark.run_gate_b import run_gate_b_query

    return await run_gate_b_query(q, out_root, resume=resume)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="I-wire-002 back-half replay preflight harness")
    parser.add_argument(
        "--snapshot", required=True, type=Path,
        help="path to a banked corpus_snapshot.json (stage=pre_generation)",
    )
    parser.add_argument(
        "--out-root", type=Path, default=None,
        help="output root; default = replay in place against the banked run_dir "
             "(out_root/<domain>/<slug>/corpus_snapshot.json). When set, the snapshot is "
             "mirrored into the new nesting so the banked corpus is untouched.",
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="(diagnostic) drive the entry WITHOUT resume — fresh retrieval. "
             "Default is resume=True (the back-half-only replay).",
    )
    args = parser.parse_args(argv)

    snapshot_path = args.snapshot.resolve()
    payload = load_snapshot(snapshot_path)
    q = reconstruct_query(payload)
    out_root = resolve_out_root(snapshot_path, payload, args.out_root)
    run_dir = out_root / payload.get("domain", "") / payload.get("slug", "")
    resume = not args.no_resume

    print(f"[replay] snapshot={snapshot_path}")
    print(f"[replay] slug={payload.get('slug')!r} domain={payload.get('domain')!r}")
    print(f"[replay] out_root={out_root}  run_dir={run_dir}  resume={resume}")
    print(f"[replay] evidence_for_gen rows in snapshot: {len(_evidence_rows(payload))}")

    # Pre-run INPUT assertions (c)+(d): read off the snapshot rows (upstream wiring).
    results: dict[str, tuple[bool, str]] = {}
    results["c"] = assert_content_relevance_weight(payload)
    results["d"] = assert_cred_tier(payload)

    # Drive the REAL back-half end-to-end (real GLM client, real 4-role seam).
    summary: dict[str, Any] = {}
    run_error: str = ""
    try:
        summary = asyncio.run(_run_backhalf(q, out_root, resume))
    except Exception as exc:  # noqa: BLE001 — a raise IS the (a) signal; record it, do not swallow
        run_error = f"{type(exc).__name__}: {exc}"
        summary = {"status": "error_unexpected", "error": run_error}

    manifest = _load_manifest(run_dir)

    # Post-run OUTPUT assertions (a),(b),(e),(f),(g): read off manifest.json + report.md.
    results["a"] = assert_completed(summary, manifest, run_dir)
    results["b"] = assert_consolidation_collapsed(manifest, run_dir)
    results["e"] = assert_abstractive(run_dir, payload)
    results["f"] = assert_faithfulness_ran(manifest, run_dir)
    results["g"] = assert_report_nonempty_cited(run_dir)

    print("\n=== I-wire-002 back-half replay assertions ===")
    order = ["a", "b", "c", "d", "e", "f", "g"]
    labels = {
        "a": "completed (no UnboundLocalError/hang)",
        "b": "NLI/finding baskets collapsed>0",
        "c": "content_relevance_weight on evidence rows",
        "d": "cred-tier present (not floor-only)",
        "e": "composition abstractive (not extractive copy)",
        "f": "faithfulness engine ran + not relaxed",
        "g": "report.md non-empty + has citations",
    }
    all_pass = True
    for key in order:
        ok, evidence = results.get(key, (False, "not evaluated"))
        all_pass = all_pass and ok
        print(f"ASSERT_{key}: {'PASS' if ok else 'FAIL'}  ({labels[key]}) — {evidence}")

    if run_error:
        print(f"\n[replay] run raised: {run_error}")
    print(f"\n[replay] OVERALL: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
