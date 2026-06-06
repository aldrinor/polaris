"""
LIVE end-to-end honest-rebuild pipeline — Phase 6 REAL VALIDATION.

Unlike scripts/run_honest_full_cycle.py, this script performs ACTUAL
network calls:
  - Serper (web search)
  - Semantic Scholar (academic search)
  - OpenAlex (publication type enrichment)
  - DeepSeek V3.2-Exp via OpenRouter (generator)
  - Judge model via OpenRouter (evaluator judge)

The canonical query is the same semaglutide 2.4mg / weight loss /
adults with obesity question that PG_LB_SA_02 ran.

Output: outputs/honest_live_cycle/ — every artifact + full run log.

Usage:
    python -X utf8 scripts/run_live_honest_cycle.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

# Load .env before importing modules that read env vars
from dotenv import load_dotenv
load_dotenv(override=False)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Keep logs visible but not overwhelming
logging.basicConfig(
    level=os.environ.get("PG_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from src.polaris_graph.evaluator.external_evaluator import (  # noqa: E402
    run_external_evaluation,
)
from src.polaris_graph.evaluator.live_judge import (  # noqa: E402
    judge_report,
)
from src.polaris_graph.generator.live_deepseek_generator import (  # noqa: E402
    generate_live_draft,
)
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    resolve_provenance_to_citations,
    strict_verify,
)
from src.polaris_graph.nodes.corpus_approval_gate import (  # noqa: E402
    CorpusApprovalDecision,
    authorization_from_env,
    check_auto_approve_allowed,
    compute_tier_distribution,
    save_approval_decision,
)
from src.polaris_graph.nodes.scope_gate import run_scope_gate  # noqa: E402
from src.polaris_graph.retrieval.contradiction_detector import (  # noqa: E402
    detect_contradictions,
    extract_numeric_claims,
)
from src.polaris_graph.retrieval.live_retriever import (  # noqa: E402
    run_live_retrieval,
)


RESEARCH_QUESTION = (
    "What is the efficacy and safety of semaglutide 2.4mg for weight "
    "loss in adults with obesity?"
)

# A few amplified queries to broaden retrieval. These are deliberately
# modest — the scope_query_validator will drop any that drift off.
AMPLIFIED_QUERIES = [
    "semaglutide 2.4 mg weight loss trial STEP",
    "semaglutide safety profile adverse events obesity",
    "GLP-1 agonist weight loss systematic review",
    "Wegovy FDA label indication contraindication",
]


async def main_async() -> int:
    run_dir = ROOT / "outputs" / "honest_live_cycle"
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"LIVE_HONEST_{int(time.time())}"

    log_path = run_dir / "run_log.txt"
    log_f = log_path.open("w", encoding="utf-8")

    def _log(msg: str) -> None:
        print(msg)
        log_f.write(msg + "\n")
        log_f.flush()

    _log("=" * 72)
    _log(f"LIVE HONEST-REBUILD CYCLE  run_id={run_id}")
    _log("=" * 72)
    _log(f"Run dir:    {run_dir}")
    _log(f"Question:   {RESEARCH_QUESTION}")
    _log(f"Time start: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    _log("")

    # ── Phase 2b: Scope gate ────────────────────────────────────────────
    _log("[1/7] SCOPE GATE — writing protocol.json")
    scope = run_scope_gate(
        research_question=RESEARCH_QUESTION,
        run_dir=run_dir,
        run_id=run_id,
        domain="clinical",
    )
    _log(f"       sha256={scope.protocol_sha256[:16]}...  "
         f"needs_review={scope.protocol.needs_user_review}")
    protocol_dict = scope.protocol.to_json_dict()

    # ── Phase 2a+2d+2e: Live retrieval + scope-validated amplified queries
    _log("")
    _log("[2/7] LIVE RETRIEVAL — Serper + Semantic Scholar + OpenAlex enrich")
    t0 = time.time()
    retrieval = run_live_retrieval(
        research_question=RESEARCH_QUESTION,
        amplified_queries=AMPLIFIED_QUERIES,
        protocol=protocol_dict,
        max_serper=10,
        max_s2=10,
        fetch_cap=24,
        enable_openalex_enrich=True,
        enable_prefetch_filter=False,  # embedder load is slow; skip on first live run
    )
    dt = time.time() - t0
    _log(f"       pre-filter candidates={retrieval.total_candidates_pre_filter}, "
         f"fetched={retrieval.candidates_fetched}, "
         f"failed_fetch={retrieval.candidates_failed_fetch}, "
         f"elapsed={dt:.1f}s")
    _log(f"       api_calls={retrieval.api_calls}")
    for n in retrieval.notes:
        _log(f"       note: {n}")

    classified_sources = retrieval.classified_sources
    evidence_rows = retrieval.evidence_rows

    if len(classified_sources) == 0:
        _log("FATAL: 0 sources retrieved. Aborting.")
        log_f.close()
        return 2

    # Write classified corpus dump for inspection
    corpus_dump_path = run_dir / "live_corpus_dump.json"
    corpus_dump_path.write_text(
        json.dumps(
            [asdict(s) for s in classified_sources],
            indent=2, sort_keys=True, default=str,
        ) + "\n",
        encoding="utf-8",
    )

    # ── Phase 2g: Corpus approval gate ──────────────────────────────────
    _log("")
    _log("[3/7] CORPUS APPROVAL GATE — computing tier distribution")
    dist_report = compute_tier_distribution(classified_sources, protocol_dict)
    tier_summary = ", ".join(
        f"{k}={v*100:.0f}%" for k, v in sorted(dist_report.tier_fractions.items())
    )
    _log(f"       total={dist_report.total_sources}  distribution: {tier_summary}")
    _log(f"       material_deviation={dist_report.has_material_deviation}")

    approval_note = "Live first-run; deviations expected."
    # FX-05 (I-ready-017): structured authorization, never a free-text note.
    authorization = authorization_from_env()
    if dist_report.has_material_deviation:
        ok, err = check_auto_approve_allowed(dist_report, authorization)
        approved = ok
        _log(f"       deviation-approval: {'ACCEPTED' if ok else 'REJECTED'}  {err}")
    else:
        approved = True
        _log("       auto-approved (no material deviation)")
    decision = CorpusApprovalDecision(
        run_id=run_id,
        decision_at_unix=time.time(),
        decision_at_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        approved=approved,
        user_note=approval_note,
        authorization=authorization,
        approved_source_urls=[s.url for s in classified_sources] if approved else [],
        rejected_source_urls=[] if approved else [s.url for s in classified_sources],
        report=dist_report,
        protocol_sha256=scope.protocol_sha256,
    )
    save_approval_decision(decision, run_dir)

    # FX-05 (I-ready-017): §9.1 #5 — a denied corpus aborts BEFORE any generator
    # token is billed. A material-deviation corpus with no structured
    # PG_AUTHORIZED_SWEEP_APPROVAL authorization is denied; do NOT proceed to
    # live generation.
    if not approved:
        _log("[ABORT] Corpus approval denied (material deviation without a "
             "structured PG_AUTHORIZED_SWEEP_APPROVAL authorization). "
             "Refusing to generate; no generator tokens billed.")
        (run_dir / "report.md").write_text(
            f"# Research report: {RESEARCH_QUESTION}\n\n"
            "## Pipeline verdict\n\n"
            "Corpus approval was denied: the corpus has a material deviation "
            "from the pre-registered protocol and no structured operator "
            "authorization (PG_AUTHORIZED_SWEEP_APPROVAL=1) was supplied. "
            "No generator tokens were billed.\n\n"
            "Status: abort_corpus_approval_denied\n",
            encoding="utf-8",
        )
        log_f.close()
        return 4

    # ── Phase 3: Contradiction detection ────────────────────────────────
    _log("")
    _log("[4/7] CONTRADICTION DETECTION")
    numeric_claims = extract_numeric_claims(evidence_rows)
    contradictions = detect_contradictions(numeric_claims)
    _log(f"       extracted={len(numeric_claims)} numeric claims, "
         f"contradictions={len(contradictions)}")
    for c in contradictions:
        _log(f"       - {c.subject}/{c.predicate} rel_diff={c.relative_difference*100:.1f}% "
             f"severity={c.severity}")
    (run_dir / "contradictions.json").write_text(
        json.dumps(
            [asdict(c) for c in contradictions],
            indent=2, sort_keys=True, default=str,
        ) + "\n",
        encoding="utf-8",
    )

    # ── Phase 4: Live DeepSeek generation ────────────────────────────
    _log("")
    _log("[5/7] DEEPSEEK V3.2-EXP LIVE GENERATION")
    # Cap evidence passed to generator (token budget)
    max_ev_to_generator = int(os.getenv("PG_LIVE_MAX_EV_TO_GEN", "20"))
    evidence_for_gen = evidence_rows[:max_ev_to_generator]
    t0 = time.time()
    try:
        gen = await generate_live_draft(
            research_question=RESEARCH_QUESTION,
            evidence=evidence_for_gen,
            temperature=0.3,
            max_tokens=1500,
        )
        dt = time.time() - t0
        _log(f"       model={gen.model}  elapsed={dt:.1f}s")
        _log(f"       input_tok={gen.input_tokens} output_tok={gen.output_tokens}")
        _log(f"       raw_draft_chars={len(gen.raw_draft)}")
        _log(f"       sentences={gen.total_sentences} "
             f"citations_converted={gen.citations_converted} "
             f"unverifiable={gen.citations_unverifiable}")
    except Exception as exc:
        _log(f"       GENERATION FAILED: {exc}")
        log_f.close()
        return 3

    (run_dir / "deepseek_raw_draft.txt").write_text(
        gen.raw_draft, encoding="utf-8",
    )
    (run_dir / "deepseek_rewritten_draft.txt").write_text(
        gen.rewritten_draft, encoding="utf-8",
    )

    # ── Phase 4 verification: strict_verify on rewritten draft ─────────
    _log("")
    _log("[6/7] STRICT PROVENANCE VERIFICATION")
    evidence_pool = {ev["evidence_id"]: ev for ev in evidence_for_gen}
    strict = strict_verify(gen.rewritten_draft, evidence_pool)
    _log(f"       total={strict.total_in}, verified={strict.total_kept}, "
         f"dropped={strict.total_dropped}")
    dropped_report = []
    for sv in strict.dropped_sentences[:5]:
        reasons = ", ".join(sv.failure_reasons[:3])
        dropped_report.append(
            f"   dropped: {sv.sentence[:90]}\n      reasons: {reasons}"
        )
    if dropped_report:
        _log("\n".join(dropped_report))

    rendered_text, biblio = resolve_provenance_to_citations(
        strict.kept_sentences, evidence_pool,
    )

    # ── Compose the final report (methods section + bibliography) ──────
    from src.polaris_graph.llm.openrouter_client import (
        PG_EVALUATOR_MODEL, PG_GENERATOR_MODEL,
    )
    methods_section = (
        "\n\n## Methods\n"
        f"This research follows the pre-registered protocol.json "
        f"(SHA-256 {scope.protocol_sha256[:16]}...).\n"
        f"Retrieved on {time.strftime('%Y-%m-%d')} from Serper web search, "
        f"Semantic Scholar, and OpenAlex.\n"
        f"Generator model: {PG_GENERATOR_MODEL}.\n"
        f"Evaluator model: {PG_EVALUATOR_MODEL} (different family).\n"
        f"Sources were classified using the T1-T7 tier taxonomy (T1 "
        f"peer-reviewed primary, T2 SR/MA, T3 regulatory, T4 narrative "
        f"review, T5 industry, T6 commentary/news, T7 stub).\n"
        f"Inclusion criteria: peer-reviewed journal articles, regulatory "
        f"documents, human studies. Exclusion criteria: user-upload "
        f"document hosts, student journals, press releases without "
        f"peer-reviewed corroboration. Sponsor / conflict-of-interest "
        f"funding was evaluated per source.\n"
        f"Prompt-injection sanitization was applied to all evidence.\n"
        f"Expected tier distribution per clinical template: T1 30-60%, "
        f"T2 15-40%, T3 5-25%. Actual distribution: {tier_summary}.\n"
    )
    if contradictions:
        n = len(contradictions)
        pluralized = "contradiction" if n == 1 else "contradictions"
        methods_section += (
            f"\n## Contradiction disclosures\n"
            f"{n} {pluralized} detected:\n\n"
        )
        for c in contradictions:
            vals = ", ".join(f"{cc.value}" for cc in c.claims)
            methods_section += (
                f"- {c.subject} / {c.predicate}: values [{vals}] {c.claims[0].unit} "
                f"(rel diff {c.relative_difference*100:.1f}%).\n"
            )
    biblio_section = "\n\n## Bibliography\n"
    for b in biblio:
        biblio_section += (
            f"[{b['num']}] {b['statement'][:200]} — {b['url']} (tier {b['tier']})\n"
        )

    final_report = (
        f"# Research report: {RESEARCH_QUESTION}\n\n"
        + rendered_text
        + methods_section
        + biblio_section
    )
    (run_dir / "report.md").write_text(final_report, encoding="utf-8")
    (run_dir / "bibliography.json").write_text(
        json.dumps(biblio, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _log(f"       final report: {len(final_report)} chars, "
         f"{len(final_report.split())} words, biblio={len(biblio)}")

    # ── Phase 5a: Rule-based evaluator ─────────────────────────────
    _log("")
    _log("[7/7] EVALUATOR — rule checks + judge")
    evaluator_output = run_external_evaluation(
        report_text=final_report,
        protocol=protocol_dict,
        tier_distribution_report=asdict(dist_report),
        contradictions=[asdict(c) for c in contradictions],
        evidence_pool=evidence_pool,
        enable_llm_judge=False,
    )
    _log(f"       rule checks: pass={evaluator_output.rule_check_pass_count} "
         f"fail={evaluator_output.rule_check_fail_count}")
    for r in evaluator_output.rule_checks:
        mark = "PASS" if r.passed else "FAIL"
        detail = f" — {r.details[:80]}" if not r.passed and r.details else ""
        _log(f"         [{mark}] {r.item_id} {r.name}{detail}")

    # ── Phase 5b: Judge (REAL LLM CALL) ──────────────────────────────
    _log("")
    _log("       live judge call...")
    t0 = time.time()
    try:
        judge = await judge_report(
            report_text=final_report,
            research_question=RESEARCH_QUESTION,
            temperature=0.2,
            max_tokens=700,
        )
        dt = time.time() - t0
        _log(f"       model={judge.model} elapsed={dt:.1f}s "
             f"parse_ok={judge.parse_ok} "
             f"input_tok={judge.input_tokens} output_tok={judge.output_tokens}")
        if judge.parse_ok:
            for axis, v in judge.verdicts.items():
                _log(f"       [{v['verdict'].upper():>15}] {axis}: {v['note'][:80]}")
        else:
            _log(f"       PARSE ERROR: {judge.error}")
            _log(f"       raw[:500]: {judge.raw_response[:500]}")
    except Exception as exc:
        _log(f"       JUDGE FAILED: {exc}")
        judge = None

    (run_dir / "evaluator_rule_checks.json").write_text(
        json.dumps(
            evaluator_output.to_json_dict(),
            indent=2, sort_keys=True, default=str,
        ) + "\n",
        encoding="utf-8",
    )
    if judge is not None:
        (run_dir / "judge_output.json").write_text(
            json.dumps(
                {
                    "model": judge.model,
                    "parse_ok": judge.parse_ok,
                    "verdicts": judge.verdicts,
                    "raw_response": judge.raw_response,
                    "error": judge.error,
                    "input_tokens": judge.input_tokens,
                    "output_tokens": judge.output_tokens,
                },
                indent=2, sort_keys=True, default=str,
            ) + "\n",
            encoding="utf-8",
        )

    # ── Manifest ────────────────────────────────────────────────────
    manifest = {
        "run_id": run_id,
        "research_question": RESEARCH_QUESTION,
        "protocol_sha256": scope.protocol_sha256,
        "live_retrieval": {
            "pre_filter_candidates": retrieval.total_candidates_pre_filter,
            "fetched": retrieval.candidates_fetched,
            "failed_fetch": retrieval.candidates_failed_fetch,
            "api_calls": retrieval.api_calls,
        },
        "corpus": {
            "total": dist_report.total_sources,
            "tier_fractions": dist_report.tier_fractions,
            "material_deviation": dist_report.has_material_deviation,
            "approved": decision.approved,
        },
        "contradictions": {
            "numeric_claims": len(numeric_claims),
            "contradictions_found": len(contradictions),
        },
        "generator": {
            "model": gen.model,
            "input_tokens": gen.input_tokens,
            "output_tokens": gen.output_tokens,
            "sentences": gen.total_sentences,
            "citations_converted": gen.citations_converted,
            "citations_unverifiable": gen.citations_unverifiable,
        },
        "verifier": {
            "total_in": strict.total_in,
            "verified": strict.total_kept,
            "dropped": strict.total_dropped,
        },
        "evaluator_rule": {
            "pass": evaluator_output.rule_check_pass_count,
            "fail": evaluator_output.rule_check_fail_count,
        },
        "evaluator_judge": (
            {
                "parse_ok": judge.parse_ok,
                "verdicts_counts": {
                    v: sum(
                        1 for j in judge.verdicts.values()
                        if j["verdict"] == v
                    )
                    for v in ("good", "acceptable", "needs_revision", "unknown")
                } if judge.parse_ok else {},
                "input_tokens": judge.input_tokens,
                "output_tokens": judge.output_tokens,
            } if judge is not None else {"error": "judge_failed"}
        ),
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _log("")
    _log("=" * 72)
    _log("LIVE CYCLE COMPLETE")
    _log("=" * 72)
    _log(f"  Sources retrieved:      {dist_report.total_sources}")
    _log(f"  Tier fractions:         {tier_summary}")
    _log(f"  Contradictions:         {len(contradictions)}")
    _log(f"  Sentences verified:     {strict.total_kept}/{strict.total_in}")
    _log(f"  Rule checks:            {evaluator_output.rule_check_pass_count}/12 pass")
    if judge and judge.parse_ok:
        v_counts = manifest["evaluator_judge"]["verdicts_counts"]
        _log(f"  Judge verdicts:         {v_counts}")
    _log("")
    _log(f"  Artifacts in:           {run_dir}")
    _log("")

    log_f.close()
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
