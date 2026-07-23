#!/usr/bin/env python3
"""STEP 15: compose the REAL scoreable multi-section report from the LIVE agentic run.

The mission's metric-(a) full-corpus gate (cp4_used=agentic on the 329-basket corpus) already
PASSED (docs/agentic_sweep_live_summary_s3gear329.json). What was missing was a *composed*
report we can score. This driver closes that gap: it runs the FULL generator
(``generate_multi_section_report``) with the agentic outliner ON (PG_OUTLINE_AGENT=1 + the
§9.1.8 model lock) over data/cp4_corpus_s3gear_329.json and writes report.md.

Model it on scripts/run_honest_on_prerebuild_corpus.py (which already produced report.md +
multi_section_outline.json), minus the retrieval/scope machinery (the corpus is pre-built).

Faithfulness gate (HARD): after composition, assert ZERO unverified numbers reach any
[CITE:ev_xxx] token in the composed report. The strict_verify lane already enforces this
per-section; this driver re-audits the final assembled text as an independent tripwire.

Run (key MUST be in env):
    set -a && . ./.env && set +a
    PG_OUTLINE_AGENT=1 python scripts/compose_agentic_report_s3gear329.py \
        --corpus data/cp4_corpus_s3gear_329.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# STEP-1 render cleanups read their config flags through the CENTRAL layer (settings.resolve
# over config_defaults), never bare os.getenv literals, so other pipelines/bots stay
# byte-identical unless a flag is set.
from src.polaris_graph.settings import resolve  # noqa: E402

DRB_QUERY = ROOT / "third_party" / "deep_research_bench" / "data" / "prompt_data" / "query.jsonl"

# STEP 2 (wheel: topic-driven structure) — the section headings are now produced TOPIC-DRIVEN by
# the generator itself (facet outline + general research-report skeleton: PG_FACET_OUTLINE=1 +
# PG_FACET_OUTLINE_SKELETON=1). The prior STEP-16 approach hardcoded a clinical-archetype ->
# AI/labor relabel MAP here — an overfit band-aid tuned to one benchmark task. That map is GONE:
# the outliner emits real topical titles (Introduction / thematic bodies / Cross-Study Synthesis /
# Conclusions and Research Gaps) for ANY domain, so assembly renders the section titles verbatim.


def _derive_title(rq: str) -> str:
    """Derive a neutral report title from the research question — GENERAL, not tuned to any task.

    Takes the first sentence/clause of the RQ, strips a leading imperative ("Please write a ...",
    "Research ...", "I am researching ..."), and Title-cases nothing (keeps the RQ's own wording).
    Falls back to a generic label. No topic is hardcoded."""
    import re as _re
    s = (rq or "").strip().replace("\n", " ")
    s = _re.sub(r"\s+", " ", s)
    # First sentence only.
    s = _re.split(r"(?<=[.?!])\s", s, maxsplit=1)[0]
    # Strip common leading imperatives so the title reads as a subject, not a command.
    s = _re.sub(r"^(please\s+)?(help me\s+)?(write|prepare|produce|conduct|research(ing)?|"
                r"provide|create|complete|collect( and)?( organi[sz]e)?|i am researching|"
                r"i would like|i need)\b[:,]?\s*", "", s, flags=_re.IGNORECASE)
    s = s.strip().rstrip(".").strip()
    if not s:
        return "Research Report"
    # Capitalize the first letter only (preserve proper-noun casing in the rest).
    return s[0].upper() + s[1:]


def _load_drb_prompt(task_id: str) -> str:
    """Load a DeepResearch-Bench task's EXACT prompt verbatim (target/ref/criteria all key on it)."""
    for line in DRB_QUERY.read_text().splitlines():
        o = json.loads(line)
        if str(o.get("id")) == str(task_id):
            return o["prompt"]
    raise SystemExit(f"BLOCKED: DRB task id {task_id} not in {DRB_QUERY}")

logging.basicConfig(
    level=os.environ.get("PG_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
for noisy in ("httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("compose")


def _resolved_or_env(key: str) -> dict[str, str | None]:
    """Capture a config value without allowing diagnostic recording to fail."""
    try:
        return {"value": resolve(key), "source": "resolve"}
    except KeyError:
        value = os.environ.get(key)
        return {"value": value, "source": "env" if value is not None else "unset"}


def _tier_fractions(evidence: list[dict]) -> dict[str, float]:
    from collections import Counter
    c = Counter((e.get("tier") or "T?").upper() for e in evidence)
    n = sum(c.values()) or 1
    return {k: v / n for k, v in sorted(c.items())}


# A numeric token that would be a faithfulness breach if it sat inside a [CITE:] sentence
# without having passed strict_verify. We audit the FINAL assembled report: any [CITE:ev_xxx]
# in the verified text is, by construction, already span-grounded — but we re-scan to prove it.
_CITE_RE = re.compile(r"\[CITE:(ev_[0-9a-fA-F]+|[a-z0-9_]+)\]")


def _audit_citations(report_text: str, biblio: list[dict]) -> dict:
    """Independent faithfulness tripwire on the FINAL assembled report.

    strict_verify resolves every kept sentence's provenance token into a global [N] bibliography
    marker and DROPS any sentence whose number failed the span match. So in a faithful final
    report: (1) ZERO raw [CITE:ev_xxx] tokens survive (any survivor is an unverified-number leak
    — the exact breach the mission forbids), and (2) every [N] marker in the prose resolves to a
    real bibliography entry. We assert both."""
    leaked_cites = _CITE_RE.findall(report_text)
    body = report_text.split("\n\n## References\n", 1)[0]  # markers in prose only
    n_markers = set(int(m) for m in re.findall(r"\[(\d+)\]", body))
    biblio_nums = {int(b.get("num")) for b in biblio if str(b.get("num", "")).isdigit()}
    unresolved = sorted(n for n in n_markers if n not in biblio_nums)
    return {
        "leaked_cite_ev_tokens": len(leaked_cites),
        "leaked_cite_samples": sorted(set(leaked_cites))[:10],
        "distinct_bib_markers_in_prose": len(n_markers),
        "bibliography_entries": len(biblio_nums),
        "unresolved_markers": unresolved,
    }


def _order_sections_by_required(verified: list, required_titles: list[str]) -> list:
    """Reorder VERIFIED sections so those matching the required titles come first,
    in the required order; all others keep their original relative order after.

    Matching is case-insensitive containment (a required title matched against a
    produced heading). ORDER-ONLY: every input section is present in the output
    exactly once — nothing is dropped or fabricated. A required title with no
    matching verified section is simply skipped (disclosure is the audit's job)."""
    want = [(t or "").strip().lower() for t in required_titles if (t or "").strip()]
    used: set[int] = set()
    ordered: list = []
    for w in want:
        for i, sr in enumerate(verified):
            if i in used:
                continue
            tl = (sr.title or "").strip().lower()
            if tl == w or w in tl or tl in w:
                ordered.append(sr)
                used.add(i)
                break
    for i, sr in enumerate(verified):
        if i not in used:
            ordered.append(sr)
    conclusion = [
        section for section in ordered
        if re.search(r"\bconclu(?:sion|sions|ding)\b", str(getattr(section, "title", "")), re.I)
    ]
    if conclusion:
        ordered = [section for section in ordered if section not in conclusion] + conclusion
    return ordered


def _insert_before_conclusion(items: list, item) -> list:
    """Insert an assembled section immediately before the report's closing section."""
    out = list(items)
    for index, candidate in enumerate(out):
        title = str(getattr(candidate, "title", "") or "")
        if re.search(r"\bconclu(?:sion|sions|ding)\b", title, re.I):
            out.insert(index, item)
            return out
    out.append(item)
    return out


def _sections_for_render(sections: list, required_titles: list[str] | None = None) -> list:
    """Return every non-failed section carrying verified/renderable text.

    There is intentionally no residual-section switch: once verified prose was
    generated, assembly may order it but may not excise it.  Under the facet-pack
    gate residual evidence is folded into topical sections *before* generation.
    """

    verified = [
        section for section in (sections or [])
        if not section.dropped_due_to_failure and section.verified_text
    ]
    return _order_sections_by_required(verified, list(required_titles or []))


def _dedup_biblio_by_work(biblio: list[dict]) -> list[dict]:
    """Collapse bibliography rows that resolve to the same underlying WORK.

    Key is the normalized URL when present, else the normalized statement text.
    The FIRST row for each work is kept (preserving its assigned number); later
    duplicates are removed. This drops only DUPLICATE reference lines — never a
    distinct source — and does not touch in-prose [N] markers."""
    seen: set[str] = set()
    out: list[dict] = []
    for b in biblio:
        url = str(b.get("url", "") or "").strip().lower().rstrip("/")
        key = url or str(b.get("statement", "") or "").strip().lower()[:160]
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(b)
    return out


def _live_topic_judge(prompt: str) -> str:
    """Synchronous scope-judge adapter used from the contract worker thread."""
    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
        OpenRouterClient,
        PG_GENERATOR_MODEL,
    )

    model = os.environ.get("PG_SCOPE_TOPIC_MODEL", PG_GENERATOR_MODEL)
    try:
        max_tokens = int(resolve("PG_SCOPE_CONTRACT_MAX_TOKENS") or "131072")
    except ValueError:
        max_tokens = 131072
    max_tokens = max_tokens if max_tokens > 0 else 131072

    async def _run() -> str:
        client = OpenRouterClient(model=model)
        try:
            response = await client.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.0,
                reasoning_effort="xhigh",
            )
            return (response.content or "").strip()
        finally:
            if hasattr(client, "close"):
                await client.close()

    return asyncio.run(_run())


def _live_contradiction_judge(prompt: str) -> str:
    """Synchronous plain-generator adapter used by the pre-generation miner."""
    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
        OpenRouterClient,
        PG_GENERATOR_MODEL,
    )

    max_tokens = int(resolve("PG_SCOPE_CONTRACT_MAX_TOKENS"))

    async def _run() -> str:
        client = OpenRouterClient(model=PG_GENERATOR_MODEL)
        try:
            response = await client.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.0,
                reasoning_effort="xhigh",
            )
            return (response.content or "").strip()
        finally:
            if hasattr(client, "close"):
                await client.close()

    return asyncio.run(_run())


def _retrieve_scope_candidates(
    research_question: str,
    queries: list[str],
    native_filters: dict,
    domain: str,
) -> list[dict]:
    """Run the normal live acquisition path for one contract-deepening round."""
    from src.polaris_graph.retrieval.live_retriever import (  # noqa: PLC0415
        run_live_retrieval,
    )

    result = run_live_retrieval(
        research_question=research_question,
        amplified_queries=queries,
        protocol=dict(native_filters),
        domain=domain or None,
        anchor_seed=False,
    )
    return list(result.evidence_rows)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--max-parallel", type=int, default=3)
    ap.add_argument("--rq-drb-task", default="72",
                    help="override the corpus RQ with this DRB task's verbatim prompt so the "
                         "composed report answers the SAME task it is scored against; empty string "
                         "keeps the corpus RQ")
    ap.add_argument("--title", default=None,
                    help="report title for the judged report.md; default DERIVES it from the RQ "
                         "(general — no title is hardcoded to any task)")
    # S4 render projection (default-OFF): when a pinned planning_gate_artifact.json is
    # supplied, thread its deliverable/scope/compose projections into composition and
    # run the disclosure-only contract-compliance audit alongside the (untouched)
    # citation audit. Omitted (the default) => byte-identical to today's champion.
    ap.add_argument("--gate-artifact", default=None,
                    help="OPTIONAL path to a pinned planning_gate_artifact.json. When given, its "
                         "contract projections steer contract-aware assembly (required sections/"
                         "order, references dedup) and the compose voice, and audit_contract runs. "
                         "Absent => byte-identical champion behavior (no gate).")
    args = ap.parse_args()

    if not os.getenv("OPENROUTER_API_KEY"):
        log.error("BLOCKED: OPENROUTER_API_KEY not in env — source .env first "
                  "(set -a && . ./.env && set +a)")
        return 2
    # The mission model-lock: agentic outliner ON.
    os.environ.setdefault("PG_OUTLINE_AGENT", "1")
    # P0 CONFIRMED-SAFE COMPOSE CONFIG (2026-07-12) — PIN the non-deadlocking config in the launch
    # path. The clean 24.2min/1449.7s run used exactly this: off-loop ON (shipped, verdict-safe),
    # PG_COMPOSE_BASKET_WORKERS=1 (serial byte-identical MAP+REDUCE — NEVER >1 without a full-328
    # verdict-identity A/B), PG_SIDE_JUDGE_MAX_CONCURRENCY in the 4-8 band (NEVER >=48), and
    # PG_PARALLEL_SECTIONS=3. These are setdefault (an explicit operator override still wins) but they
    # keep this driver on the certified-safe path; the startup guard (compose_config_guard) refuses the
    # deadlocking regime regardless. Faithfulness-neutral: pure concurrency knobs.
    os.environ.setdefault("PG_COMPOSE_BASKET_WORKERS", "1")
    os.environ.setdefault("PG_SIDE_JUDGE_MAX_CONCURRENCY", "8")
    os.environ.setdefault("PG_PARALLEL_SECTIONS", "3")
    # P1-SPEED (2026-07-12) — collapse the ISOLATED pre-compose credibility member-verify pass.
    # ROOT-CAUSE of the 43min (2589.7s) >> 24min (1449.7s) gap, MEASURED from the phase timeline in
    # logs/step3_full328_render.log: threading the PSL gov_suffixes (below) to lift route_all basket
    # utilization ALSO activates the ADVISORY credibility corroboration pass. On this 997-member corpus
    # that pass ran SERIALLY (PG_CREDIBILITY_PASS_MAX_INFLIGHT default=1) and BANKED at its
    # wall*0.85 soft deadline = 1020s, verifying only 207/997 members — a full +1020s phase the 1449.7s
    # baseline NEVER ran (it did not thread gov_suffixes -> credibility degraded-to-unscored, skipped).
    # This pass runs ENTIRELY BEFORE compose (an ISOLATED flat phase — NO PG_PARALLEL_SECTIONS x
    # PG_COMPOSE_BASKET_WORKERS x inner-TPE nesting), so bounding its OWN loop concurrency is NOT the
    # multiplicative compose oversubscription the deadlock guard protects against. Parallelize the
    # member-verify loop and raise the side-judge cap FOR THIS PHASE ONLY (the designed I-deepfix-001
    # box2 lever; credibility_pass_concurrency RESTORES the compose-time cap of 8 before compose starts).
    # Faithfulness-neutral & UNDERCOUNT-only: the pass is ADVISORY (strict_verify / 4-role D8 /
    # span-grounding are untouched); verifying MORE members in LESS time yields STRICTLY MORE
    # corroboration than the 207-serial run and far more than the baseline's zero. All env-overridable.
    os.environ.setdefault("PG_CREDIBILITY_PASS_MAX_INFLIGHT", "16")
    os.environ.setdefault("PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY", "16")
    os.environ.setdefault("PG_CREDIBILITY_PASS_WALL_S", "600")
    # STEP 2: topic-driven, synthesis-enabling structure. Facet outline (thematic sections emerge
    # from the evidence) + the general research-report skeleton (intro / thematic bodies /
    # cross-study synthesis+contradictions / conclusions+gaps). GENERAL structural flags — they
    # hardcode no topic and are overridable from the environment.
    os.environ.setdefault("PG_FACET_OUTLINE", "1")
    os.environ.setdefault("PG_FACET_OUTLINE_SKELETON", "1")
    # STEP 3 (INSIGHT depth): make the cross-study synthesis section quantify agreement/disagreement
    # across the [ev]-backed body figures (enrich its evidence + directive). GENERAL structural
    # lever — role detected structurally, no topic/title hardcoded; strict_verify unchanged.
    os.environ.setdefault("PG_SYNTHESIS_QUANT_DIRECTIVE", "1")
    # STEP 4 (UTILIZATION): keep a facet's full matched payload by dropping the PG_MAX_EV_PER_SECTION
    # row-cap ceiling.
    #
    # Route-all is single-sourced in config_defaults.  This driver deliberately
    # carries no hidden override; the central champion default is authoritative.
    os.environ.setdefault("PG_EV_BUDGET_TRACKS_PAYLOAD", "1")

    corpus_path = Path(args.corpus)
    corpus = json.loads(corpus_path.read_text())
    corpus_rq = corpus["research_question"]
    if args.rq_drb_task:
        rq = _load_drb_prompt(args.rq_drb_task)
        log.info("RQ OVERRIDE: composing to DRB task %s verbatim prompt (corpus RQ kept as "
                 "provenance only). task_rq[:90]=%r", args.rq_drb_task, rq[:90])
    else:
        rq = corpus_rq
    evidence = corpus["evidence"]
    corpus_evidence_count = len(evidence)
    raw_clusters = corpus.get("finding_clusters") or []
    clusters = [SimpleNamespace(**c) if isinstance(c, dict) else c for c in raw_clusters]
    swg = corpus.get("same_work_groups")
    domain = corpus.get("domain", "")

    # Scope + coverage obligations share the existing generic constraint schema.
    # The scope contract is default-ON, so extraction must not depend on the
    # optional coverage-obligations presentation flag.
    _scope_constraints: dict = {}
    from src.polaris_graph.retrieval.scope_contract import (  # noqa: PLC0415
        scope_contract_enabled,
        scope_deepening_enabled,
    )
    _coverage_on = (resolve("PG_COVERAGE_OBLIGATIONS") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if _coverage_on or scope_contract_enabled():
        try:
            from src.polaris_graph.instruction.constraint_extractor import (  # noqa: PLC0415
                extract_constraints_async,
            )
            from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
                OpenRouterClient, PG_EVALUATOR_MODEL,
            )
            _constraint_client = OpenRouterClient(model=PG_EVALUATOR_MODEL)
            _scope_constraints = dict(await extract_constraints_async(
                rq,
                max_tokens=int(resolve("PG_SCOPE_CONTRACT_MAX_TOKENS")),
                reasoning_effort="xhigh",
                client=_constraint_client,
            ))
        except Exception as exc:  # noqa: BLE001 — disclosed empty constraints; corpus remains intact
            log.warning("[constraints] extraction unavailable: %s", exc)
            _scope_constraints = {}
        finally:
            if "_constraint_client" in locals() and hasattr(_constraint_client, "close"):
                await _constraint_client.close()

    run_id = time.strftime("agentic_report_%Y%m%d_%H%M%S")
    run_dir = ROOT / (args.out_dir or f"outputs/{run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)

    # Atomic pre-generation scope partition. The input corpus is retained
    # byte-for-byte in ``corpus``; only copied survivors reach the writer.
    _deepening_on = scope_deepening_enabled()
    _scope_disclosure: dict = {
        "input_count": corpus_evidence_count,
        "composition_evidence_count": corpus_evidence_count,
        "off_topic_excluded_count": 0,
        "wrong_type_excluded_count": 0,
        "contract_enabled": scope_contract_enabled(),
        "deepening_status": "requires_retrieval_pipeline" if not _deepening_on else "pending",
    }
    if scope_contract_enabled():
        try:
            from src.polaris_graph.retrieval.scope_contract import (  # noqa: PLC0415
                apply_scope_contract,
                deepen_scope_contract,
                remap_finding_clusters,
                remap_same_work_groups,
            )
            _scope_result = await asyncio.to_thread(
                apply_scope_contract,
                evidence,
                rq,
                _live_topic_judge,
                constraints=_scope_constraints,
            )
            _scoped_clusters = remap_finding_clusters(
                raw_clusters, _scope_result.kept_original_indices,
            )
            _kept_ids = {
                str(row.get("evidence_id") or "") for row in _scope_result.evidence
                if str(row.get("evidence_id") or "")
            }
            _scoped_swg = remap_same_work_groups(
                swg or [], _scope_result.kept_original_indices, _kept_ids,
            )
            if _deepening_on:
                _scope_result = await asyncio.to_thread(
                    deepen_scope_contract,
                    _scope_result,
                    rq,
                    lambda queries, filters: _retrieve_scope_candidates(
                        rq, queries, dict(filters), domain,
                    ),
                    None,
                    _live_topic_judge,
                    wall_seconds=float(resolve("PG_SCOPE_DEEPENING_WALL_SECONDS")),
                    novelty_judge=_live_topic_judge,
                )
            _scope_disclosure = _scope_result.disclosure()
            _scope_disclosure.update({
                "contract_enabled": True,
                "deepening_status": (
                    _scope_result.deepening.get("stop_reason", "complete")
                    if _deepening_on else "requires_retrieval_pipeline"
                ),
                "finding_clusters_before": len(raw_clusters),
                "finding_clusters_after": len(_scoped_clusters),
                "same_work_groups_before": len(swg or []),
                "same_work_groups_after": len(_scoped_swg),
            })
            # Atomic commit only after partition + dependent-index remaps +
            # disclosure all succeed.  Any exception leaves the full pool.
            evidence = _scope_result.evidence
            raw_clusters = _scoped_clusters
            clusters = [SimpleNamespace(**c) for c in raw_clusters]
            swg = _scoped_swg
            log.info(
                "[scope-contract] input=%d off_topic_excluded=%d "
                "wrong_type_excluded=%d composition=%d (corpus retained)",
                corpus_evidence_count,
                _scope_disclosure["off_topic_excluded_count"],
                _scope_disclosure["wrong_type_excluded_count"],
                len(evidence),
            )
        except Exception as exc:  # noqa: BLE001 — fail-open, never nuke a paid run
            log.warning("[scope-contract] failed open; composition pool unchanged: %s", exc)
            _scope_disclosure["judge_failed_open"] = True
            _scope_disclosure["failure"] = str(exc)[:300]

    _contradictions: list[dict] = []
    from src.polaris_graph.generator.contradiction_mining import (  # noqa: PLC0415
        contradiction_mining_enabled,
        find_contradictions,
    )
    _contradiction_on = contradiction_mining_enabled()
    if _contradiction_on:
        try:
            _contradictions = await asyncio.to_thread(
                find_contradictions,
                evidence,
                rq,
                _live_contradiction_judge,
            )
            log.info(
                "[contradiction-mining] confirmed=%d candidate pool=%d",
                len(_contradictions),
                len(evidence),
            )
        except Exception as exc:  # noqa: BLE001 — disclosed fail-open before generation
            log.warning("[contradiction-mining] failed open: %s", exc)
            _scope_disclosure["contradiction_mining_failure"] = str(exc)[:300]
    (run_dir / "scope_contract_disclosure.json").write_text(
        json.dumps(_scope_disclosure, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    _retrieval_scope_status = (
        "prebuilt_corpus_scope_contract_applied_with_deepening"
        if _deepening_on
        else "prebuilt_corpus_scope_contract_applied_no_deepening"
    )
    log.info("corpus=%s  evidence=%d  clusters=%d  same_work_groups=%s  domain=%s",
             corpus_path.name, len(evidence), len(clusters),
             len(swg or []), domain or "(none)")
    log.info("PG_OUTLINE_AGENT=%s  out_dir=%s", os.getenv("PG_OUTLINE_AGENT"), run_dir)

    # LOGGING FIX (LOGGING-LOSSY): wire the run-scoped reasoning-trace sink. The sweep
    # path registers it (run_honest_sweep_r3.py:9384) but the compose path never did, so
    # openrouter_client found no sink and reasoning was silently dropped —
    # reasoning_trace.jsonl came out empty (0 bytes). Write-through collector + up-front
    # flush so the file is current on disk on any exit path. The generator already sets
    # the per-call reasoning context (multi_section_generator.py:3248), so registering
    # the sink here is all that was missing.
    from src.polaris_graph.generator.reasoning_trace import (  # noqa: PLC0415
        ReasoningTraceCollector,
    )
    from src.polaris_graph.llm.openrouter_client import set_reasoning_sink  # noqa: PLC0415
    _reasoning_collector = ReasoningTraceCollector(out_dir=run_dir)
    _reasoning_collector.flush(run_dir)
    set_reasoning_sink(_reasoning_collector)
    try:

        from src.polaris_graph.generator.multi_section_generator import (  # noqa: PLC0415
            generate_multi_section_report,
        )
        from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
            PG_EVALUATOR_MODEL, PG_GENERATOR_MODEL,
        )
        from src.polaris_graph.outline.outline_agent import (  # noqa: PLC0415
            outliner_agent_model, outliner_code_model,
        )

        dist = _tier_fractions(evidence)
        log.info("tier fractions: %s", {k: round(v, 3) for k, v in dist.items()})
        log.info("[gen] agent_model=%s code_model=%s generator=%s",
                 outliner_agent_model(), outliner_code_model(), PG_GENERATOR_MODEL)

        # STEP 4 (UTILIZATION): thread the PSL government-suffix list so the credibility pass RUNS
        # priors-only (judge=None under always-release => ZERO LLM scoring calls) and BUILDS the per-claim
        # baskets. Without gov_suffixes the pre-run guard DEGRADES to credibility_analysis=None (the
        # 794->9 collapse), which strands EVERY basket and makes PG_ROUTE_ALL_BASKETS inert — the report
        # then renders only the LLM-writer's directly-cited sources. Faithfulness-neutral: priors weights
        # are deterministic authority weights; strict_verify / 4-role D8 / span-grounding stay the ONLY
        # binding gates. Fail-open: an empty/unavailable suffix list leaves the legacy None path.
        _gov_suffixes = None
        try:
            from src.polaris_graph.authority.data_loader import load_authority_data  # noqa: PLC0415
            _gov_suffixes = tuple(load_authority_data().get("psl_gov_suffixes") or ()) or None
            log.info("[credibility] threaded psl_gov_suffixes=%d (priors-only basket build enabled)",
                     len(_gov_suffixes or ()))
        except Exception as _e:  # noqa: BLE001
            log.warning("[credibility] could not load psl_gov_suffixes (%s); credibility pass will "
                        "degrade to None and PG_ROUTE_ALL_BASKETS will be inert", _e)

        # S4 render/compose projections (default-OFF): load a pinned gate artifact when
        # supplied and compile its deliverable/scope/compose views. Absent => every
        # projection is None => byte-identical champion composition + assembly.
        _gate_contract = None
        _deliverable_spec = None
        _scope_spec = None
        _compose_projection = None
        _render_plan: dict = {}
        _contract_sha = ""
        if args.gate_artifact:
            try:
                from src.polaris_graph.planning.planning_gate_schema import (  # noqa: PLC0415
                    contract_from_dict,
                )
                from src.polaris_graph.planning.compose_render_projection import (  # noqa: PLC0415
                    from_contract as _crp_from_contract,
                )
                _art = json.loads(Path(args.gate_artifact).read_text())
                _gate_contract = contract_from_dict(_art.get("contract") or {})
                _contract_sha = str(_art.get("contract_sha256") or "")
                _crp = _crp_from_contract(_gate_contract)
                _compose_projection = _crp  # exposes .voice_advisory()
                _render_plan = _crp.render_plan()
                # deliverable_spec surfaced to the outliner as required-section titles/order
                # (the S4 ORCH-2 seam already in _call_outline). scope_spec passthrough.
                _deliverable_spec = {
                    "required_sections": _render_plan.get("required_titles", []),
                    "document_type": _render_plan.get("document_type", ""),
                }
                _scope_spec = {}
                log.info("[gate] loaded artifact=%s contract_sha=%s required_sections=%d "
                         "doc_type=%r voice=%s",
                         args.gate_artifact, _contract_sha[:12],
                         len(_render_plan.get("required_titles", [])),
                         _render_plan.get("document_type", ""), _crp.has_voice())
            except Exception as _e:  # noqa: BLE001 — fail-open: no gate => champion path
                log.warning("[gate] could not load --gate-artifact %s (%s); running "
                            "byte-identical champion path (no projections)",
                            args.gate_artifact, _e)
                _gate_contract = None
                _deliverable_spec = _scope_spec = _compose_projection = None
                _render_plan = {}

        t0 = time.time()
        multi = await generate_multi_section_report(
            research_question=rq,
            evidence=evidence,
            finding_clusters=clusters,
            same_work_groups=swg,
            section_temperature=0.3,
            outline_max_tokens=2500,
            min_kept_fraction=0.4,
            max_parallel_sections=args.max_parallel,
            tier_fractions=dist,
            domain=domain,
            credibility_pass_gov_suffixes=_gov_suffixes,
            # S4: None (default, no --gate-artifact) => byte-identical to HEAD.
            deliverable_spec=_deliverable_spec,
            scope_spec=_scope_spec,
            compose_projection=_compose_projection,
            prompt_scope_constraints=_scope_constraints or None,
            contradictions=_contradictions or None,
        )
        dt = time.time() - t0
        kept = [s for s in multi.sections if not s.dropped_due_to_failure]
        log.info("[gen] elapsed=%.1fs  outline=%d sections  kept=%d  words=%s  "
                 "verified=%s  dropped=%s  in_tok=%s out_tok=%s",
                 dt, len(multi.outline), len(kept), getattr(multi, "total_words", "?"),
                 getattr(multi, "total_sentences_verified", "?"),
                 getattr(multi, "total_sentences_dropped", "?"),
                 getattr(multi, "total_input_tokens", "?"),
                 getattr(multi, "total_output_tokens", "?"))
        for sr in multi.sections:
            mark = "OK " if not sr.dropped_due_to_failure else "DROP"
            log.info("   [%s] %-42s verified=%s dropped=%s regen=%s",
                     mark, sr.title[:42], sr.sentences_verified,
                     sr.sentences_dropped, sr.regen_attempted)

        # Persist the outline
        (run_dir / "multi_section_outline.json").write_text(
            json.dumps([{"title": p.title, "focus": p.focus, "ev_ids": p.ev_ids}
                        for p in multi.outline], indent=2, sort_keys=True) + "\n",
            encoding="utf-8")

        # Assemble the JUDGED report body from VERIFIED text only.
        #  - Section headings are the generator's OWN topic-driven titles (facet outline + skeleton):
        #    an Introduction, thematic bodies, a Cross-Study Synthesis & Contradictions section, and a
        #    Conclusions & Research Gaps section — no clinical archetypes, no relabel map.
        #  - A single GENERAL, topic-neutral framing sentence under the title (NO factual claims / no
        #    numbers — pure presentation). The report's substantive framing lives in the generated
        #    Introduction section; this line only states the organizing method. The tripwire re-audits.
        title = args.title or _derive_title(rq)
        # Reader-register preamble is the production default. The diagnostic variant remains available
        # through an explicit false/pipeline register for internal runs.
        if resolve("PG_REPORT_PREAMBLE_REGISTER").strip().lower() in ("1", "true", "yes", "on", "reader"):
            intro = (
                "This review addresses the question above within its stated scope. It is organized around "
                "the principal distinctions supported by the literature, moving from context through the "
                "main findings and their relationships to a closing synthesis."
            )
        else:
            intro = (
                "This report synthesizes the retrieved research evidence on the question above. It is "
                "organized as a coherent review: an introduction that frames the scope, thematic sections "
                "that group the evidence by sub-topic, a cross-study synthesis that surfaces where the "
                "findings agree and conflict, and a closing discussion of conclusions and open research "
                "gaps. Every quantitative claim is span-grounded to a cited source; claims that could not "
                "be verified against the underlying evidence were removed rather than paraphrased."
            )
        # Verified section bodies (VERIFIED text only — never dropped/edited here).
        # S4 contract-aware order: when the render plan names required section titles
        # in order, place matching verified sections FIRST in that order; every other
        # verified section keeps its original relative order AFTER them. This ORDERS
        # verified content — it never drops or fabricates a section. Absent render
        # plan => original order => byte-identical.
        _required_titles = list(_render_plan.get("required_titles", [])) if _render_plan else []
        _verified = _sections_for_render(multi.sections, _required_titles)
        _outline_for_render = list(multi.outline)
        if getattr(multi, "limitations_text", ""):
            _limitations_section = SimpleNamespace(
                title="Limitations",
                verified_text=multi.limitations_text,
                dropped_due_to_failure=False,
            )
            _verified = _insert_before_conclusion(_verified, _limitations_section)
            _outline_for_render = _insert_before_conclusion(
                _outline_for_render,
                SimpleNamespace(title="Limitations"),
            )
        _missing_planned_sections: list[str] = []
        if (resolve("PG_COVERAGE_OBLIGATIONS") or "").strip().lower() in ("1", "true", "yes", "on"):
            from src.polaris_graph.generator.coverage_obligations import (  # noqa: PLC0415
                render_sections_preserving_outline,
            )
            bodies, _missing_planned_sections = render_sections_preserving_outline(
                _outline_for_render, _verified,
            )
        else:
            bodies = [f"## {sr.title}\n\n{sr.verified_text}" for sr in _verified]
        sections_concat = "\n\n".join(bodies)

        biblio = getattr(multi, "bibliography", []) or []
        # S4 references dedup by WORK: when the render plan requests it (default True
        # in a loaded contract), collapse bibliography rows that resolve to the same
        # underlying work (same url, else same statement). The FIRST row's number is
        # kept; this only removes DUPLICATE reference lines, never a distinct source,
        # and does not renumber in-prose markers. No gate artifact => biblio unchanged.
        _dedup_by_work = bool(_render_plan.get("references_dedup_by_work")) if _render_plan else False
        biblio_render = _dedup_biblio_by_work(biblio) if _dedup_by_work else biblio
        # STEP-1 render cleanup (change #3): the trailing '(tier X)' label on each
        # References entry is cosmetic. When PG_REFERENCE_TIER_LABELS='0' it is omitted
        # from the rendered References block (the tier still rides in bibliography.json).
        # Default '1' = keep the tier label = today's byte-identical References render.
        _keep_tier_labels = resolve("PG_REFERENCE_TIER_LABELS") != "0"
        biblio_section = "\n\n## References\n"
        for b in biblio_render:
            _tier_suffix = f" (tier {b.get('tier','')})" if _keep_tier_labels else ""
            biblio_section += (f"[{b.get('num')}] {str(b.get('statement',''))[:200]} — "
                               f"{b.get('url','')}{_tier_suffix}\n")

        final_report = (f"# {title}\n\n{intro}\n\n{sections_concat}{biblio_section}")
        _summary_table_canary = "disabled"
        if resolve("PG_SUMMARY_TABLE_COMPOSE").strip().lower() in ("1", "true", "yes", "on"):
            from src.polaris_graph.generator.summary_table import (  # noqa: PLC0415
                extract_section_claims,
                render_requested_summary_table,
            )
            _summary_result = render_requested_summary_table(
                research_question=rq,
                bibliography=biblio,
                section_claims=extract_section_claims(multi.sections),
                existing_report_md=final_report,
                appendix_boundary_marker="## References",
            )
            final_report = _summary_result.text
            _summary_table_canary = _summary_result.canary
        from dataclasses import asdict  # noqa: PLC0415
        from src.polaris_graph.generator.cleaned_output_guard import (  # noqa: PLC0415
            find_malformed_tables,
        )
        _cleaned_output_defects = [
            asdict(item) for item in find_malformed_tables(final_report)
        ]
        if _cleaned_output_defects:
            log.warning(
                "[cleaned-output] detected %d malformed-table defect(s); report left unchanged",
                len(_cleaned_output_defects),
            )
        (run_dir / "report.md").write_text(final_report, encoding="utf-8")

        # Pipeline telemetry / Methods is a SIDECAR artifact (provenance for us), NOT part of the judged
        # deliverable — a research report's reader does not want the generator's internal telemetry.
        tier_summary = ", ".join(f"{k}={v*100:.0f}%" for k, v in sorted(dist.items()))
        _deepening_methods = (
            "Deepening: unavailable at this prebuilt-corpus seam; run the retrieval pipeline "
            "with the contract deepening hook for target/saturation-aware acquisition.\n"
            if not _deepening_on else
            f"Deepening: {_scope_disclosure.get('deepening_status', 'complete')}; "
            f"details={json.dumps(_scope_disclosure.get('deepening', {}), sort_keys=True)}.\n"
        )
        _contradiction_methods = (
            f"Contradictions detected: {len(_contradictions)}.\n"
            if _contradiction_on else ""
        )
        methods = (
            "# Methods / pipeline telemetry (sidecar — NOT part of the judged report.md)\n\n"
            f"Judged task: DRB task {args.rq_drb_task} (verbatim prompt).\n"
            f"Corpus RQ (provenance): {corpus_rq[:200]}...\n"
            f"Corpus: {corpus_path.name} ({corpus_evidence_count} archived evidence rows; "
            f"{len(evidence)} composition-eligible rows, {len(clusters)} baskets; "
            f"domain={domain or 'general'}).\n"
            f"Scope contract: off-topic excluded={_scope_disclosure.get('off_topic_excluded_count', 0)}; "
            f"wrong-type/language excluded={_scope_disclosure.get('wrong_type_excluded_count', 0)}; "
            "excluded rows retained in the source corpus and disclosed in "
            "scope_contract_disclosure.json.\n"
            f"{_deepening_methods}"
            f"{_contradiction_methods}"
            f"Outliner: AGENTIC (PG_OUTLINE_AGENT=1) — agent {outliner_agent_model()}, "
            f"code {outliner_code_model()}.\n"
            f"Generator: {PG_GENERATOR_MODEL} (multi-section: agentic outline + "
            f"{len(kept)} parallel verified sections + strict_verify + regen-on-failure).\n"
            f"Evaluator/mirror: {PG_EVALUATOR_MODEL}.\n"
            f"Tier distribution: {tier_summary}.\n"
        )
        (run_dir / "methods.md").write_text(methods, encoding="utf-8")
        (run_dir / "bibliography.json").write_text(
            json.dumps(biblio, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        # P0/proof: the agentic-outliner digest surfaced on MultiSectionResult — PROVE the deep render
        # stayed agentic (cp4_used='agentic'), NOT degraded-to-seed (mission metric-1).
        oa_stats = dict(getattr(multi, "outline_agent_stats", None) or {})
        cp4_used = str(oa_stats.get("cp4_used", "MISSING"))
        degraded_to_seed = bool(oa_stats.get("degraded_to_seed", False))
        degrade_reason = str(oa_stats.get("degrade_reason", ""))
        log.info("[agentic] cp4_used=%s degraded_to_seed=%s turns=%s degrade_reason=%r -> %s",
                 cp4_used, degraded_to_seed, oa_stats.get("turns"), degrade_reason[:160],
                 "AGENTIC" if cp4_used == "agentic" else "NOT-AGENTIC")

        audit = _audit_citations(final_report, biblio)
        faithful = (audit["leaked_cite_ev_tokens"] == 0 and not audit["unresolved_markers"])
        log.info("[faithfulness] leaked_[CITE:ev]=%d  bib_markers_in_prose=%d  bib_entries=%d  "
                 "unresolved_markers=%s -> %s",
                 audit["leaked_cite_ev_tokens"], audit["distinct_bib_markers_in_prose"],
                 audit["bibliography_entries"], audit["unresolved_markers"],
                 "PASS" if faithful else "FAIL")

        # S4 contract-compliance audit — DISCLOSURE-ONLY, ALONGSIDE (never in place of)
        # the citation audit above (which is untouched). It reads the finished report +
        # outline + biblio and reports term-level SATISFIED/FAILED/UNSATISFIABLE/UNKNOWN
        # per contract term with its owning stage. It NEVER drops/edits content and NEVER
        # touches strict_verify.  This prebuilt corpus is scope-partitioned before
        # composition, but discovery/deepening did not run under the contract; the
        # status names both facts. No --gate-artifact => no planning contract => an
        # empty audit (fail-open).
        compliance = None
        if _gate_contract is not None:
            try:
                from src.polaris_graph.planning.contract_compliance import (  # noqa: PLC0415
                    audit_contract,
                )
                outline_titles = [s.title for s in multi.sections
                                  if not s.dropped_due_to_failure and s.verified_text]
                _ca = audit_contract(
                    _gate_contract,
                    final_report,
                    outline=outline_titles,
                    biblio=biblio,
                    retrieval_scope_status=_retrieval_scope_status,
                    contract_sha256=_contract_sha,
                )
                compliance = _ca.to_dict()
                (run_dir / "contract_compliance.json").write_text(
                    json.dumps(compliance, indent=2) + "\n", encoding="utf-8")
                log.info("[compliance] counts=%s retrieval_scope_status=%s -> "
                         "contract_compliance.json",
                         compliance.get("counts"), compliance.get("retrieval_scope_status"))
            except Exception as _e:  # noqa: BLE001 — disclosure-only, never fails the run
                log.warning("[compliance] audit_contract failed (%s); skipping disclosure "
                            "(faithfulness + citation audit unaffected)", _e)
                compliance = None

        summary = {
            "corpus": corpus_path.name,
            "judged_drb_task": args.rq_drb_task or None,
            "composed_to_rq": rq[:160],
            "corpus_rq": corpus_rq[:160],
            "report_title": title,
            "section_headings": [s.title for s in multi.sections
                                 if not s.dropped_due_to_failure and s.verified_text],
            "corpus_evidence_rows": corpus_evidence_count,
            "evidence_rows": len(evidence),
            "scope_contract": _scope_disclosure,
            "baskets": len(clusters),
            "same_work_groups": len(swg or []),
            "outline_sections": len(multi.outline),
            "kept_sections": len(kept),
            "dropped_sections": len(multi.sections) - len(kept),
            "total_words": getattr(multi, "total_words", None),
            "total_sentences_verified": getattr(multi, "total_sentences_verified", None),
            "total_sentences_dropped": getattr(multi, "total_sentences_dropped", None),
            "bibliography_entries": len(biblio),
            "report_chars": len(final_report),
            "report_words": len(final_report.split()),
            "faithfulness_audit": audit,
            "faithfulness_pass": faithful,
            # S4 disclosure: scope was evaluated on the prebuilt rows, while live
            # contract-aware discovery/deepening was not run at this seam.
            "retrieval_scope_status": _retrieval_scope_status,
            "contract_compliance": compliance,
            "cp4_used": cp4_used,
            "degraded_to_seed": degraded_to_seed,
            "degrade_reason": degrade_reason[:200],
            "outline_agent_turns": oa_stats.get("turns"),
            "moat_quantified_models": len(getattr(multi, "quantified_models", None) or {}),
            "agent_model": outliner_agent_model(),
            "code_model": outliner_code_model(),
            "generator_model": PG_GENERATOR_MODEL,
            "elapsed_seconds": round(dt, 1),
            "out_dir": str(run_dir),
            "summary_table_canary": _summary_table_canary,
            "prompt_scope_weight_ledger": getattr(multi, "prompt_scope_weight_ledger", {}) or {},
            "attribution_coverage": getattr(multi, "attribution_coverage", {}) or {},
            "evidence_pack_coverage": getattr(multi, "evidence_pack_coverage", {}) or {},
            "coverage_obligation_audit": getattr(multi, "coverage_obligation_audit", {}) or {},
            "missing_planned_sections": _missing_planned_sections,
            "cleaned_output_defects": _cleaned_output_defects,
            # STEP 1 (measurement honesty): record the RESOLVED state of every RACE lever so a run can
            # never again "measure" a silently-inert lever. Effective env value at compose time.
            "resolved_lever_states": {
                k: _resolved_or_env(k)
                for k in (
                    "PG_RENDER_BLOCKS", "PG_SECTION_STRUCTURE",
                    "PG_SYNTHESIS_MATRIX", "PG_SYNTHESIS_MATRIX_MIN_ROWS",
                    "PG_SYNTHESIS_TABLE_CONSTRUCT", "PG_SUMMARY_TABLE_COMPOSE",
                    "PG_TRIAL_TABLE_MIN_MAX_TOKENS", "PG_TRIAL_TABLE_REASONING_MAX_TOKENS",
                    "PG_COVERAGE_SPINE", "PG_SOURCE_ROUTING", "PG_RQ_SOURCE_ELIGIBILITY_ENFORCE",
                    "PG_PROMPT_SCOPE_WEIGHTING", "PG_NARRATIVE_ATTRIBUTION",
                    "PG_FACET_EVIDENCE_PACKS", "PG_BASKET_SYNTHESIS",
                    "PG_CROSS_SECTION_REPETITION_GUARD",
                    "PG_COVERAGE_OBLIGATIONS",
                    "PG_CONTRADICTION_MINING", "PG_SCOPE_DEEPENING",
                    "PG_RELATION_EVIDENCE_PACKS",
                    "PG_LIMITATIONS_REGISTER", "PG_REPORT_PREAMBLE_REGISTER",
                    "PG_ROUTE_ALL_BASKETS", "PG_INCLUDE_RESIDUAL_SECTION",
                    "PG_STRICT_VERIFY_OFF", "PG_STRICT_VERIFY_ENTAILMENT",
                )
            },
        }
        if _contradiction_on:
            summary["contradictions_detected"] = len(_contradictions)
            summary["contradictions"] = _contradictions
        (run_dir / "compose_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        log.info("WROTE %s (%d chars, %d words) + compose_summary.json",
                 run_dir / "report.md", len(final_report), len(final_report.split()))
        print(json.dumps(summary, indent=2))
        return 0 if faithful else 1
    finally:
        # LOGGING FIX: clear the run-scoped sink so it cannot leak into a reused process.
        set_reasoning_sink(None)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
