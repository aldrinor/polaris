"""Agentic outliner PRODUCTION run -- AI-labor drb_72 corpus (real cp2 evidence pool @
s2_hamster_i1, real cp3 basket snapshot @ s3_gear). Question: impact of Generative AI on the
future labor market. PG_OUTLINE_AGENT=1, PG_OUTLINER_AGENT_MODEL=z-ai/glm-5.2, un-starved
tokens to the CONFIRMED real GLM-5.2 OpenRouter completion cap (131072; GET /api/v1/models
2026-07-11), reasoning bounded at 32768 (CLAUDE.md sec 9.1.8). Mirrors the signed-off
real_corpus_run.py template but targets the operator-specified cp3/cp2 paths and, on success,
additionally writes (a) the FINAL fully-detailed cp4 (question_sha + upstream + full
digest_stats, not just the live per-mutation checkpoint) and (b) the enlarged cp2 evidence pool
(fold-in rows appended in place by run_outline_agent_or_legacy).

W2 fix (2026-07-11, Fable-authoritative): this launcher previously pre-filtered baskets to
member_count>=2 before building finding_clusters -- on this corpus that drops 307 of 346
baskets (the "44-basket cheat"), running the agentic outliner against a tiny sliver of the real
corpus instead of the FULL corpus. Removed: every basket (including member_count==1 singletons)
is now built into a cluster and fed to the agent -- singleton clusters have
member_indices==[representative_index] and corroboration_count==1, which build_outline_digest
already handles (it is fail-open aid code, never a hard requirement -- see
outline_agent.py:1877-1886).

Also asserts the worktree is committed+clean before running (no un-pinned code executes) and
prints the effective env + git HEAD SHA to stdout so a `tee` wrapper captures full traceability
in the box-persisted log.

FAIL LOUD on any exception (LAW II) -- never fakes a pass.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

REPO_DIR = "/workspace/outline_agent_wt"
sys.path.insert(0, REPO_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv("/workspace/POLARIS/.env", override=True)

# --------------------------------------------------------------------------------------
# Git-pin assertion: refuse to run against an un-committed / drifted worktree. This is the
# "chain P1 launcher must ... assert git HEAD pinned" requirement -- the code that actually
# executes must be exactly what's on HEAD, not silent local edits.
# --------------------------------------------------------------------------------------
_head_sha = subprocess.check_output(
    ["git", "-C", REPO_DIR, "rev-parse", "HEAD"], text=True,
).strip()
_dirty = subprocess.check_output(
    ["git", "-C", REPO_DIR, "status", "--porcelain"], text=True,
).strip()
if _dirty:
    raise RuntimeError(
        f"REFUSING un-pinned run: worktree {REPO_DIR} has uncommitted changes "
        f"(HEAD={_head_sha}):\n{_dirty}"
    )
print(f"[git-pin] HEAD={_head_sha} (worktree clean, code == committed code)")

# --------------------------------------------------------------------------------------
# Un-starved budgets (CLAUDE.md sec 9.1.8 -- reasoning + max_tokens ALWAYS go MAX, never
# starve). 131072 is the CONFIRMED real OpenRouter provider cap for z-ai/glm-5.2
# (top_provider.max_completion_tokens, GET /api/v1/models 2026-07-11) -- NOT a moderate raise.
# Every outline-stage LLM call is covered: the seed _call_outline (PG_OUTLINE_MAX_TOKENS, read
# by run_one_query's outline_max_tokens plumbing) AND the three agentic-loop control-plane
# calls (_decide / _run_checklist / query-derive). Reasoning is bounded separately at 32768 so
# the reasoning-first prelude (the ~21k-token prelude that caused the real-corpus
# ReasoningFirstTruncationError) can never eat the whole budget before content.
# setdefault (not direct assignment) so an operator override in the outer shell environment
# still wins -- LAW VI, no hardcoding that can't be overridden.
os.environ["PG_OUTLINE_AGENT"] = "1"
os.environ["PG_OUTLINER_AGENT_MODEL"] = "z-ai/glm-5.2"
os.environ.setdefault("PG_OUTLINE_MAX_TOKENS", "131072")
os.environ.setdefault("PG_OUTLINE_DECIDE_MAX_TOKENS", "131072")
os.environ.setdefault("PG_OUTLINE_CHECKLIST_MAX_TOKENS", "131072")
os.environ.setdefault("PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS", "131072")
os.environ.setdefault("PG_OUTLINE_REASONING_MAX_TOKENS", "32768")
# Default production wall/turns are 24 turns / 900s (outline_agent.py docstring). This corpus
# (996 evidence rows, 346 baskets) is much denser than the 41-basket harness corpus that 900s
# was tuned against (a comparable real-corpus run on a 41-basket/654-row snapshot took 948.8s
# at WALL=1500s -- see outputs/real_corpus_agent_run/real_corpus_result.json), so the wall is
# raised to 2100s to give the loop room to actually fire gap-fetches on a denser corpus while
# staying safely inside the operator's 2700s external hard timeout (600s buffer for the seed
# _call_outline + writes + any latency). Turns stay at the true default (24) -- not restricted.
os.environ.setdefault("PG_OUTLINE_AGENT_WALL_SECONDS", "2100")
# Outer asyncio.wait_for grace (degrade-to-seed belt-and-suspenders) -- default 180s is fine
# unchanged; recorded here so the effective-env dump below is complete.
os.environ.setdefault("PG_OUTLINE_AGENT_RUN_TIMEOUT_GRACE_SECONDS", "180")

from src.polaris_graph.outline import outline_agent as oa  # noqa: E402
from src.polaris_graph.generator import outline_checkpoint as oc  # noqa: E402

CP2_PATH = "/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json"
CP3_PATH = "/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json"
OUT_DIR = "/workspace/outline_agent_wt/outputs/agentic_outline_ailabor_labormarket_run1"

_EFFECTIVE_ENV_KEYS = [
    "PG_OUTLINE_AGENT", "PG_OUTLINER_AGENT_MODEL", "PG_OUTLINE_MAX_TOKENS",
    "PG_OUTLINE_DECIDE_MAX_TOKENS", "PG_OUTLINE_CHECKLIST_MAX_TOKENS",
    "PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS", "PG_OUTLINE_REASONING_MAX_TOKENS",
    "PG_OUTLINE_AGENT_WALL_SECONDS", "PG_OUTLINE_AGENT_RUN_TIMEOUT_GRACE_SECONDS",
    "PG_OUTLINE_AGENT_MAX_TURNS",
]


def _print_effective_env() -> None:
    print("[effective-env] " + json.dumps(
        {k: os.environ.get(k, "(unset/default)") for k in _EFFECTIVE_ENV_KEYS}, sort_keys=True,
    ))


def _build_clusters(baskets: list[dict], ev_id_to_idx: dict[str, int]) -> list[SimpleNamespace]:
    """Build ONE cluster per basket -- the FULL corpus, no member_count>=2 pre-filter (the
    "44-basket cheat" this launcher previously committed; removed 2026-07-11). Singleton
    baskets (member_count==1) still produce a valid cluster: member_indices falls back to
    [representative_index] when member_evidence_ids is empty/absent, corroboration_count
    defaults to 1. build_outline_digest treats finding_clusters as fail-open aid input (never
    a hard requirement -- outline_agent.py:1877-1886), so singleton clusters are safe.
    """
    clusters = []
    dropped = 0
    singleton_count = 0
    for b in baskets:
        rep_id = b.get("representative_evidence_id")
        member_ids = list(b.get("member_evidence_ids") or [])
        if not member_ids and rep_id:
            member_ids = [rep_id]
        if rep_id not in ev_id_to_idx or any(m not in ev_id_to_idx for m in member_ids):
            dropped += 1
            continue
        if int(b.get("member_count", len(member_ids) or 1)) <= 1:
            singleton_count += 1
        clusters.append(SimpleNamespace(
            representative_index=ev_id_to_idx[rep_id],
            member_indices=[ev_id_to_idx[m] for m in member_ids],
            corroboration_count=int(b.get("corroboration_count", len(member_ids) or 1)),
            member_hosts=list(b.get("member_hosts") or []),
        ))
    print(f"[bank] built {len(clusters)} clusters from {len(baskets)} baskets "
          f"({singleton_count} singleton/member_count<=1, "
          f"{len(clusters) - singleton_count} corroborated member_count>=2, "
          f"dropped {dropped} -- id not resolvable in cp2 evidence). "
          f"NO member_count>=2 pre-filter applied -- full corpus.")
    return clusters


async def main() -> None:
    with open(CP2_PATH, encoding="utf-8") as fh:
        cp2 = json.load(fh)
    with open(CP3_PATH, encoding="utf-8") as fh:
        cp3 = json.load(fh)

    evidence = list(cp2["evidence_for_gen"])
    question = str(cp2.get("question") or cp3.get("question") or "")
    domain = str(cp2.get("domain") or cp3.get("domain") or "")
    payload = cp3["payload"]
    same_work_groups = payload.get("same_work_groups")
    ev_id_to_idx = {
        str(row.get("evidence_id")): i for i, row in enumerate(evidence) if row.get("evidence_id")
    }
    clusters = _build_clusters(payload["baskets"], ev_id_to_idx)

    print(f"[agentic-outline] run_id={cp2.get('run_id')} domain={domain!r} "
          f"evidence_rows={len(evidence)} baskets={len(clusters)} "
          f"same_work_groups={len(same_work_groups or [])}")
    print(f"[agentic-outline] question (first 200 chars): {question[:200]!r}")
    print(f"[agentic-outline] agent_model={oa.outliner_agent_model()} "
          f"code_model={oa.outliner_code_model()} "
          f"max_turns={os.environ.get('PG_OUTLINE_AGENT_MAX_TURNS', '24(default)')} "
          f"wall_s={os.environ.get('PG_OUTLINE_AGENT_WALL_SECONDS')}")
    _print_effective_env()

    ev_ids_before = {str(r.get("evidence_id")) for r in evidence if r.get("evidence_id")}

    os.makedirs(OUT_DIR, exist_ok=True)

    t0 = time.monotonic()
    parse_result, retry_attempted, in_tok, out_tok = await oa.run_outline_agent_or_legacy(
        question, evidence, oa.outliner_code_model(), 0.2,
        int(os.environ.get("PG_OUTLINE_MAX_TOKENS", "131072")),
        domain=domain, finding_clusters=clusters, same_work_groups=same_work_groups,
        checkpoint_dir=OUT_DIR,
    )
    elapsed = time.monotonic() - t0

    stats = parse_result.digest_stats.get("outline_agent", {})
    cp4_used = stats.get("cp4_used", "(unset -- degrade-to-seed patch not present?)")
    print(f"\n=== AGENTIC OUTLINE RUN RESULT (elapsed {elapsed:.1f}s) ===")
    print(f"cp4_used={cp4_used} degraded_to_seed={stats.get('degraded_to_seed')} "
          f"degrade_reason={stats.get('degrade_reason')!r}")
    print(f"turns={stats.get('turns')} ev_before={len(ev_ids_before)} "
          f"ev_after={stats.get('ev_store_size')} "
          f"new_evidence={stats.get('new_evidence_count')}")
    print("\nGAP LEDGER:")
    for t in stats.get("gap_ledger", []):
        print(f"  {t}")
    print("\nDISCLOSURES:")
    for d in stats.get("disclosures", []):
        print(f"  - {d}")
    print("\nFINAL OUTLINE:")
    for p in parse_result.plans:
        title = oa._plan_field(p, "title", "")  # noqa: SLF001 -- harness, same-repo reuse
        ev_ids = oa._plan_field(p, "ev_ids", []) or []  # noqa: SLF001
        print(f"  - {title!r}: {len(ev_ids)} ev_ids")

    search_calls = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("search_more_evidence[")
    )
    checklist_events = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("checklist[")
    )

    # -----------------------------------------------------------------
    # Build + write the FINAL, fully-detailed cp4 -- overwrites the live
    # per-mutation checkpoint (written during the loop with placeholder
    # question_sha="" / run_config_sha="") with the complete picture
    # assembled by run_outline_agent_or_legacy (full digest_stats,
    # gap_ledger, unfilled_gaps, seed/final ev-by-title, disclosures).
    # -----------------------------------------------------------------
    question_sha = hashlib.sha256(question.strip().encode("utf-8")).hexdigest()
    final_plans = [oa._plan_to_dict(p) for p in parse_result.plans]  # noqa: SLF001
    cp4_payload = oc.build_cp4_payload(
        question_sha=question_sha,
        upstream=[
            {"stage": "corpus", "path": CP3_PATH},
            {"stage": "evidence_pool", "path": CP2_PATH},
        ],
        run_config_sha=_head_sha,
        flag_slate={
            "PG_OUTLINE_AGENT": "1",
            "PG_OUTLINER_AGENT_MODEL": oa.outliner_agent_model(),
            "PG_OUTLINER_CODE_MODEL": oa.outliner_code_model(),
            "PG_OUTLINE_MAX_TOKENS": os.environ.get("PG_OUTLINE_MAX_TOKENS", ""),
            "PG_OUTLINE_DECIDE_MAX_TOKENS": os.environ.get("PG_OUTLINE_DECIDE_MAX_TOKENS", ""),
            "PG_OUTLINE_CHECKLIST_MAX_TOKENS": os.environ.get("PG_OUTLINE_CHECKLIST_MAX_TOKENS", ""),
            "PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS": os.environ.get("PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS", ""),
            "PG_OUTLINE_REASONING_MAX_TOKENS": os.environ.get("PG_OUTLINE_REASONING_MAX_TOKENS", ""),
            "PG_OUTLINE_AGENT_MAX_TURNS": os.environ.get("PG_OUTLINE_AGENT_MAX_TURNS", "24(default)"),
            "PG_OUTLINE_AGENT_WALL_SECONDS": os.environ.get("PG_OUTLINE_AGENT_WALL_SECONDS", ""),
            "model": oa.outliner_agent_model(),
            "git_head_sha": _head_sha,
        },
        adjustments_applied=[],
        final_plans=final_plans,
        revision_audit={
            "gap_ledger": stats.get("gap_ledger", []),
            "unfilled_gaps": stats.get("unfilled_gaps", []),
            "disclosures": stats.get("disclosures", []),
            "seed_ev_by_title": stats.get("seed_ev_by_title", {}),
            "final_ev_by_title": stats.get("final_ev_by_title", {}),
        },
        digest_stats=parse_result.digest_stats,
    )
    cp4_path = oc.write_cp4_outline_snapshot(OUT_DIR, cp4_payload)
    print(f"\n[agentic-outline] wrote FINAL cp4 -> {cp4_path}")

    # -----------------------------------------------------------------
    # Write the ENLARGED evidence pool (cp2) alongside the run -- `evidence`
    # was mutated in place (new fold-in rows appended) by
    # run_outline_agent_or_legacy. Write it back in the SAME cp2 schema.
    # -----------------------------------------------------------------
    cp2_enlarged = dict(cp2)
    cp2_enlarged["evidence_for_gen"] = evidence
    cp2_enlarged["outline_agent_enlargement"] = {
        "seed_evidence_rows": len(ev_ids_before),
        "final_evidence_rows": len(evidence),
        "new_evidence_count": len(evidence) - len(ev_ids_before),
        "source_run_dir": OUT_DIR,
        "elapsed_s": round(elapsed, 1),
    }
    enlarged_cp2_path = os.path.join(OUT_DIR, "cp2_corpus_snapshot_enlarged.json")
    with open(enlarged_cp2_path, "w", encoding="utf-8") as fh:
        json.dump(cp2_enlarged, fh, indent=2, sort_keys=True, default=str)
    print(f"[agentic-outline] wrote ENLARGED cp2 -> {enlarged_cp2_path} "
          f"({len(ev_ids_before)} -> {len(evidence)} rows)")

    result = {
        "run_id": cp2.get("run_id"),
        "git_head_sha": _head_sha,
        "question_prefix": question[:300],
        "domain": domain,
        "elapsed_s": round(elapsed, 1),
        "seed_evidence_rows": len(ev_ids_before),
        "baskets_fed": len(clusters),
        "cp4_used": cp4_used,
        "degraded_to_seed": stats.get("degraded_to_seed"),
        "degrade_reason": stats.get("degrade_reason"),
        "turns": stats.get("turns"),
        "ev_before": len(ev_ids_before),
        "ev_after": stats.get("ev_store_size"),
        "new_evidence_count": stats.get("new_evidence_count"),
        "search_more_evidence_calls": search_calls,
        "checklist_events": checklist_events,
        "unfilled_gaps": stats.get("unfilled_gaps"),
        "final_section_ev_counts": {
            oa._plan_field(p, "title", ""): len(oa._plan_field(p, "ev_ids", []) or [])  # noqa: SLF001
            for p in parse_result.plans
        },
        "disclosures": stats.get("disclosures"),
        "gap_ledger": stats.get("gap_ledger"),
        "cp4_path": str(cp4_path),
        "enlarged_cp2_path": enlarged_cp2_path,
    }
    out_path = os.path.join(OUT_DIR, "agentic_outline_result.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(f"\n[agentic-outline] wrote {out_path}")
    print("AGENTIC_OUTLINE_RUN_DONE")


if __name__ == "__main__":
    asyncio.run(main())
