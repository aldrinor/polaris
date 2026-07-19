"""W1 acceptance harness for the agentic outliner loop (I-outline-agent).

Runs TWO real, live scenarios against src/polaris_graph/outline/outline_agent.py:

  (a) THIN  — seed evidence covers ONLY part of the research question (efficacy), the question
      itself also asks about long-term cardiovascular safety. Acceptance: the checklist names
      the gap, search_more_evidence fires a real scoped query, new rows fold in with
      collision-free ids + S2 stamps, the outline mutates (ev_ids grow / new gap-covering rows
      cited).

  (b) SATURATED — a narrow question whose seed evidence already fully covers it (negative
      control). Acceptance: retrieval stays at ZERO (no search_more_evidence tool call ever
      fires) — the checklist should find nothing to search for and finish_outline should be
      accepted quickly.

FAIL LOUD: any exception is allowed to propagate and print a full traceback — this harness never
swallows an error to fake a pass (LAW II).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# PORTABLE COPY of acceptance_outline_agent.py (the four /workspace/... hardcodes replaced with
# repo-relative / env-var-configurable paths). This file lives at <repo>/tests/oracle/, so the
# repo root is three parents up. Behaviour of the harness is otherwise byte-identical to the
# original — only path resolution changed, so it can serve as the governing oracle from any
# checkout location. See ORACLE_PORTABILITY note at the bottom for the four substitutions.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# (1) repo root on sys.path — same intent as the original's dirname(dirname(__file__)), corrected
#     for this file's deeper location so `import src.polaris_graph...` resolves.
sys.path.insert(0, str(_REPO_ROOT))
# (2) the original second sys.path.insert("/workspace/outline_agent_wt") pointed at the SAME repo
#     root under its old container layout (the outline-agent worktree WAS the repo). It is
#     redundant with (1) now that the repo root is resolved from __file__; overridable via
#     PG_EXTRA_SYS_PATH for an out-of-tree checkout.
_extra = os.environ.get("PG_EXTRA_SYS_PATH")
if _extra:
    sys.path.insert(0, _extra)

from dotenv import load_dotenv  # noqa: E402
# (3) .env location: env override PG_DOTENV wins; else the repo-local .env; else the original
#     /workspace/POLARIS/.env if it still exists. Missing .env is non-fatal — the process env
#     (e.g. an exported OPENROUTER_API_KEY / SERPER_API_KEY) is used as-is.
_dotenv_candidates = [
    os.environ.get("PG_DOTENV"),
    str(_REPO_ROOT / ".env"),
    "/workspace/POLARIS/.env",
]
for _dp in _dotenv_candidates:
    if _dp and Path(_dp).is_file():
        load_dotenv(_dp, override=True)
        print(f"[portable] loaded dotenv from {_dp}")
        break
else:
    print("[portable] no .env file found; relying on the process environment for provider keys")

os.environ["PG_OUTLINE_AGENT"] = "1"
os.environ.setdefault("PG_OUTLINE_MAX_TOKENS", "131072")
os.environ.setdefault("PG_OUTLINE_REASONING_MAX_TOKENS", "32768")
# Keep the acceptance run FAST: small turn/wall budgets are fine for W1 proof (the design's
# defaults are 24 turns / 900s for a full production run; the smoke here just needs the loop to
# fire at least once on the thin case and zero times on the saturated case).
os.environ.setdefault("PG_OUTLINE_AGENT_MAX_TURNS", "6")
os.environ.setdefault("PG_OUTLINE_AGENT_WALL_SECONDS", "420")

from src.polaris_graph.outline import outline_agent as oa  # noqa: E402
from src.polaris_graph.retrieval.live_retriever import run_live_retrieval  # noqa: E402


def _bootstrap_seed(query: str, max_serper: int = 6) -> list[dict]:
    """A real, live, narrow-scoped retrieval call used ONLY to bootstrap a small realistic seed
    pool for the harness (not part of the agent loop itself)."""
    result = run_live_retrieval(
        research_question=query, max_serper=max_serper, fetch_cap=10, anchor_seed=True,
    )
    rows = list(result.evidence_rows or [])
    print(f"[bootstrap] query={query!r} -> {len(rows)} evidence rows "
          f"(fetched={result.candidates_fetched}, failed={result.candidates_failed_fetch})")
    return rows


async def run_thin() -> dict:
    print("\n" + "=" * 80)
    print("THIN RUN — seed covers only 'efficacy', question also asks 'long-term CV safety'")
    print("=" * 80)
    seed_rows = _bootstrap_seed(
        "tirzepatide 15mg HbA1c reduction efficacy SURPASS trial results", max_serper=6,
    )
    if len(seed_rows) < 3:
        raise RuntimeError(f"bootstrap seed too thin to test with ({len(seed_rows)} rows) — "
                            "live retrieval may be degraded; not faking a pass")

    question = (
        "What is the HbA1c-lowering efficacy of tirzepatide 15mg AND what is known about its "
        "long-term cardiovascular safety (major adverse cardiovascular events, SURMOUNT-MMO "
        "or equivalent outcome trial data)?"
    )
    evidence = list(seed_rows)
    ev_before = {r.get("evidence_id") for r in evidence if isinstance(r, dict)}

    t0 = time.monotonic()
    parse_result, retry_attempted, in_tok, out_tok = await oa.run_outline_agent_or_legacy(
        question, evidence, oa.outliner_code_model(), 0.2, 131072,
    )
    elapsed = time.monotonic() - t0

    stats = parse_result.digest_stats.get("outline_agent", {})
    seed_ev_by_title = {t: set(v) for t, v in stats.get("seed_ev_by_title", {}).items()}
    final_ev_by_title = {t: set(v) for t, v in stats.get("final_ev_by_title", {}).items()}
    outline_mutated = (
        set(seed_ev_by_title.keys()) != set(final_ev_by_title.keys())
        or any(
            seed_ev_by_title.get(t, set()) != final_ev_by_title.get(t, set())
            for t in final_ev_by_title
        )
    )
    update_outline_calls = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("update_outline:")
    )
    print(f"\n--- THIN RUN RESULT (elapsed {elapsed:.1f}s) ---")
    print(f"outline_mutated={outline_mutated} update_outline_calls={update_outline_calls}")
    print(f"seed_ev_by_title={ {t: len(v) for t, v in seed_ev_by_title.items()} }")
    print(f"final_ev_by_title={ {t: len(v) for t, v in final_ev_by_title.items()} }")
    print(f"turns={stats.get('turns')} ev_before={len(ev_before)} "
          f"ev_after={stats.get('ev_store_size')} new_evidence={stats.get('new_evidence_count')}")
    print("gap_ledger:")
    for t in stats.get("gap_ledger", []):
        print(f"  {t}")
    print("disclosures:")
    for d in stats.get("disclosures", []):
        print(f"  - {d}")
    print("final outline plans:")
    for p in parse_result.plans:
        print(f"  - {oa._plan_field(p, 'title', '')!r}: "  # noqa: SLF001 — harness, same-repo reuse
              f"{len(oa._plan_field(p, 'ev_ids', []) or [])} ev_ids")

    search_calls = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("search_more_evidence[")
    )
    checklist_gaps = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("checklist[")
    )
    # Enforceable POSITIVE control (mirrors run_saturated's valid_negative_control): the thin case
    # MUST have fired at least one real scoped retrieval AND mutated the outline vs the seed. If
    # either is false the harness is asserting nothing and the control is vacuous — fail loud.
    valid_positive_control = search_calls >= 1 and outline_mutated
    print(f"valid_positive_control={valid_positive_control} "
          f"(search_calls>=1={search_calls >= 1} [search_calls={search_calls}], "
          f"outline_mutated={outline_mutated})")
    return {
        "elapsed_s": round(elapsed, 1),
        "turns": stats.get("turns"),
        "ev_before": len(ev_before),
        "ev_after": stats.get("ev_store_size"),
        "new_evidence_count": stats.get("new_evidence_count"),
        "search_more_evidence_calls": search_calls,
        "checklist_gap_events": checklist_gaps,
        "unfilled_gaps": stats.get("unfilled_gaps"),
        "outline_mutated": outline_mutated,
        "valid_positive_control": valid_positive_control,
        "update_outline_calls": update_outline_calls,
        "final_section_ev_counts": {
            oa._plan_field(p, "title", ""): len(oa._plan_field(p, "ev_ids", []) or [])  # noqa: SLF001
            for p in parse_result.plans
        },
        "disclosures": stats.get("disclosures"),
    }


async def run_saturated() -> dict:
    print("\n" + "=" * 80)
    print("SATURATED RUN (negative control) — VALID multi-section outline, fully-covered facets")
    print("=" * 80)
    # Iter-2 fix (Fable verdict: the prior single-fact question was TOO narrow — the seed outline
    # came back below the 3-section floor, `run_outline_agent_or_legacy` early-returned BEFORE the
    # agent loop was ever constructed, and the checklist's anti-invention behavior was never
    # exercised at all. That "pass" was vacuous.). This question is deliberately THREE explicit,
    # separately-named facets — construction history, structural engineering design, and cultural
    # significance — so the seed outline is a genuine >=3-section plan and the agent loop actually
    # runs. Each facet gets its OWN thorough bootstrap query so the seed pool is rich enough that a
    # correctly-grounded checklist (the P0-1 verbatim-quote gate, outline_agent.py `_run_checklist`)
    # has nothing real left to flag — this exercises the SAME anti-invention gate the thin run
    # exercises the opposite side of, on a genuinely-built loop, not a skipped one.
    seed_rows_history = _bootstrap_seed(
        "Eiffel Tower construction history 1887 1889 timeline Gustave Eiffel build phases",
        max_serper=8,
    )
    seed_rows_engineering = _bootstrap_seed(
        "Eiffel Tower structural engineering design wrought iron lattice wind resistance load",
        max_serper=8,
    )
    seed_rows_culture = _bootstrap_seed(
        "Eiffel Tower French cultural identity symbol Paris landmark significance tourism",
        max_serper=8,
    )
    seen_urls: set[str] = set()
    seed_rows: list[dict] = []
    for r in seed_rows_history + seed_rows_engineering + seed_rows_culture:
        u = str(r.get("source_url") or r.get("url") or "")
        if u and u in seen_urls:
            continue
        if u:
            seen_urls.add(u)
        seed_rows.append(r)
    if len(seed_rows) < 9:
        raise RuntimeError(
            f"bootstrap seed too thin for a genuine 3-facet saturated control "
            f"({len(seed_rows)} rows across 3 facets) — live retrieval may be degraded; "
            "not faking a pass"
        )

    question = (
        "Describe the construction history of the Eiffel Tower, its structural engineering "
        "design, and its role in French cultural identity."
    )
    evidence = list(seed_rows)
    ev_before = {r.get("evidence_id") for r in evidence if isinstance(r, dict)}
    t0 = time.monotonic()
    parse_result, retry_attempted, in_tok, out_tok = await oa.run_outline_agent_or_legacy(
        question, evidence, oa.outliner_code_model(), 0.2, 131072,
    )
    elapsed = time.monotonic() - t0

    stats = parse_result.digest_stats.get("outline_agent", {})
    print(f"\n--- SATURATED RUN RESULT (elapsed {elapsed:.1f}s) ---")
    print(f"turns={stats.get('turns')} ev_before={len(ev_before)} "
          f"ev_after={stats.get('ev_store_size')} new_evidence={stats.get('new_evidence_count')}")
    print("gap_ledger:")
    for t in stats.get("gap_ledger", []):
        print(f"  {t}")
    print("disclosures:")
    for d in stats.get("disclosures", []):
        print(f"  - {d}")

    search_calls = sum(
        1 for d in stats.get("disclosures", []) if d.startswith("search_more_evidence[")
    )
    # "checklist[seed]" now covers BOTH the "named N gap(s)" and the "ran: NONE" disclosure
    # forms (outline_agent.py iter-2 telemetry fix) — either one proves the checklist LLM call
    # actually happened, distinct from the loop never reaching it.
    checklist_ran = any(d.startswith("checklist[seed]") for d in stats.get("disclosures", []))
    finish_accepted = any(
        d.startswith("finish_outline ACCEPTED") for d in stats.get("disclosures", [])
    )
    plans_nonempty = len(parse_result.plans) > 0
    zero_searches = search_calls == 0
    section_count = len(parse_result.plans)
    # Iter-2 fix: a `stats=={}` (seed-outline-invalid) early-return is NO LONGER accepted as a
    # pass path for THIS test. Fable's iter-2 verdict was explicit: that outcome is a degenerate
    # "the loop was never built" result, not evidence the checklist declines to invent gaps on a
    # VALID outline. This harness now REQUIRES the full agent loop to have actually run — a
    # 3-facet seed engineered to produce >=3 real sections (see bootstrap above) — and only then
    # checks that the checklist, when genuinely invoked against fully-covered facets, still
    # returns nothing to search for. If the seed STILL comes back invalid despite the 3-facet
    # design, that is reported honestly as a harness/seed problem (`seed_outline_invalid_early_
    # return=True`) and `valid_negative_control=False` — it is NOT silently treated as a pass.
    seed_outline_invalid_early_return = not stats  # stats=={} iff the early-return branch fired
    full_loop_ran = (
        plans_nonempty and section_count >= 3 and stats.get("turns", 0) >= 1
        and checklist_ran and finish_accepted
    )
    valid_negative_control = zero_searches and full_loop_ran
    print(f"valid_negative_control={valid_negative_control} "
          f"(full_loop_ran={full_loop_ran}, seed_outline_invalid_early_return="
          f"{seed_outline_invalid_early_return}, plans_nonempty={plans_nonempty}, "
          f"section_count={section_count} (>=3 required), turns>=1={stats.get('turns', 0) >= 1}, "
          f"checklist_ran={checklist_ran}, finish_accepted={finish_accepted}, "
          f"zero_searches={zero_searches} [search_calls={search_calls}])")
    if seed_outline_invalid_early_return:
        print(f"  DEGENERATE (not a pass): seed outline reason_codes="
              f"{getattr(parse_result, 'reason_codes', None)}, ok={getattr(parse_result, 'ok', None)}")

    return {
        "elapsed_s": round(elapsed, 1),
        "turns": stats.get("turns"),
        "ev_before": len(ev_before),
        "ev_after": stats.get("ev_store_size"),
        "new_evidence_count": stats.get("new_evidence_count"),
        "search_more_evidence_calls": search_calls,
        "section_count": section_count,
        "full_loop_ran": full_loop_ran,
        "valid_negative_control": valid_negative_control,
        "seed_outline_invalid_early_return": seed_outline_invalid_early_return,
        "seed_reason_codes": (
            list(getattr(parse_result, "reason_codes", []) or [])
            if seed_outline_invalid_early_return else None
        ),
        "gap_ledger": stats.get("gap_ledger"),
        "disclosures": stats.get("disclosures"),
    }


# --------------------------------------------------------------------------------------------
# Deterministic browser-free golden (Oracle Layer 2 wiring). The acceptance harness has TWO
# non-deterministic boundaries: the OpenRouter LLM (frozen by tests/oracle/llm_cassette.py) and the
# live retriever / browser (frozen by tests/oracle/retrieval_cassette.py). Freezing BOTH makes the
# whole run deterministic, so the produced result artifact is byte-identical across replays and any
# diff is a real regression.
#
# Modes (``--mode`` / legacy flags):
#   seed-retrieval : LIVE OpenRouter + LIVE retriever (network+browser ONCE). Captures BOTH the
#                    retrieval cassette (the reusable seed artifact) AND the llm cassette.
#   record         : LIVE OpenRouter + FROZEN retrieval (NO browser). Records the llm cassette
#                    against the already-frozen retrieval seed; emits the GOLDEN artifact.
#   replay         : FROZEN OpenRouter + FROZEN retrieval (NO network at all). Reproduces the
#                    golden byte-identically.
#   (none)         : legacy fully-live run (both boundaries live), unchanged behaviour.
_ORACLE_DIR = Path(__file__).resolve().parent
_CASSETTE_DIR = _ORACLE_DIR / "cassettes"
_RETRIEVAL_TAPE = _CASSETTE_DIR / "acceptance_retrieval.jsonl"
_LLM_TAPE = _CASSETTE_DIR / "acceptance_llm.jsonl"
_GOLDEN_PATH = _CASSETTE_DIR / "acceptance_golden.json"


def _parse_mode() -> str | None:
    for flag, mode in (("--seed-retrieval", "seed-retrieval"),
                       ("--record", "record"), ("--replay", "replay")):
        if flag in sys.argv:
            return mode
    if "--mode" in sys.argv:
        idx = sys.argv.index("--mode")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1].strip().lower()
    return None


import re as _re  # noqa: E402

# Wall-clock timings the outline agent bakes into disclosure strings (outline_agent.py:821 emits a
# per-search ``... in {elapsed:.1f}s``). These are the ONE non-deterministic substring inside the
# otherwise pure ``disclosures`` list — frozen retrieval returns instantly on replay, so the real
# fetch elapsed differs from the recorded one. Normalizing it to a fixed token keeps the golden a
# function of BEHAVIOUR (what searched/folded/mutated), not of fetch latency.
_ELAPSED_IN_DISCLOSURE = _re.compile(r" in \d+\.\d+s\b")


def _normalize_disclosure(s: str) -> str:
    return _ELAPSED_IN_DISCLOSURE.sub(" in <elapsed>s", s)


def _canonical_golden(result: dict) -> str:
    """Deterministic, byte-stable serialization of the acceptance result. Drops the ``elapsed_s``
    wall-time field, normalizes wall-clock timings embedded in disclosure strings, and sorts keys.
    Every remaining field (turn counts, evidence counts, search-call counts, the searched/folded
    disclosures, the control verdicts) is a pure function of the frozen LLM + retrieval I/O, so this
    string is identical across replays iff behaviour is unchanged."""
    def _strip(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            if k == "elapsed_s":
                continue
            if k == "disclosures" and isinstance(v, list):
                out[k] = [_normalize_disclosure(str(x)) for x in v]
            else:
                out[k] = v
        return out

    canon = {scen: _strip(payload) for scen, payload in result.items()}
    return json.dumps(canon, indent=2, sort_keys=True, ensure_ascii=True, default=str)


async def _run_scenarios(only: str | None) -> dict:
    result: dict = {}
    if only in (None, "thin"):
        result["thin"] = await run_thin()
    if only in (None, "saturated"):
        result["saturated"] = await run_saturated()
    return result


import contextlib as _contextlib_top  # noqa: E402


@_contextlib_top.contextmanager
def _frozen_step_clock():
    """Normalize the per-step wall-clock time the notebook bakes into the decide prompt.

    ``AnalysisNotebook.summary_for_llm`` renders ``({step.elapsed_seconds:.1f}s)`` INTO the decide
    LLM prompt (analysis_notebook.py:269). That elapsed is real fetch latency at record time (~58s for
    a live gap search) but ~0s on replay with frozen retrieval — so the decide prompt would differ
    and ``generate_structured`` would MISS. This is exactly the "wall clock ... frozen separately by
    the harness" carve-out the cassette documents: elapsed is a NON-behavioural input (the decision
    must not hinge on 58.3 vs 58.4s). We render it as a fixed ``0.0`` in BOTH record and replay, so
    the decide prompt — and therefore the whole loop — is timing-independent and record==replay.
    Applied identically in record and replay, it never hides a real behaviour change."""
    from src.polaris_graph.tools import analysis_notebook as _an  # noqa: PLC0415
    _orig = _an.AnalysisNotebook.summary_for_llm

    def _patched(self, include_results: bool = False) -> str:
        # Normalize BOTH wall-clock timings the notebook feeds the decide prompt, at their SOURCE so
        # the downstream length-sensitive truncation (_result_digest_lines caps the flattened result
        # markdown at a char budget) sees byte-identical text in record and replay:
        #   (a) the per-step ``({elapsed:.1f}s)`` in the step header line — zero elapsed_seconds; and
        #   (b) the ``... in {elapsed:.1f}s`` that search_more_evidence bakes INTO its ToolResult
        #       .markdown (outline_agent.py:821/825). Record's raw markdown carries e.g. "in 84.4s"
        #       (7 chars); replay's carries "in 0.0s" (6 chars). If we normalized only the FINAL
        #       summary the digest budget would already have truncated one char differently — the
        #       classic off-by-one that made the turn-2 decide prompt differ by a single character.
        #       So we rewrite each step's result.markdown to the fixed-width ``in <elapsed>s`` token
        #       BEFORE _orig renders/truncates it. Both are non-behavioural timings; the identical
        #       normalization in record and replay never hides a real change.
        saved_elapsed = [s.elapsed_seconds for s in self._steps]
        saved_md = [getattr(s.result, "markdown", None) for s in self._steps]
        try:
            for s in self._steps:
                s.elapsed_seconds = 0.0
                md = getattr(s.result, "markdown", None)
                if isinstance(md, str):
                    s.result.markdown = _ELAPSED_IN_DISCLOSURE.sub(" in <elapsed>s", md)
            summary = _orig(self, include_results)
        finally:
            for s, ev, md in zip(self._steps, saved_elapsed, saved_md):
                s.elapsed_seconds = ev
                if md is not None:
                    s.result.markdown = md
        return _ELAPSED_IN_DISCLOSURE.sub(" in <elapsed>s", summary)

    _an.AnalysisNotebook.summary_for_llm = _patched
    try:
        yield
    finally:
        _an.AnalysisNotebook.summary_for_llm = _orig


async def _main_oracle(mode: str, only: str | None) -> None:
    """Run the acceptance scenarios with the LLM and/or retrieval boundaries frozen, emit the
    golden artifact, and (in replay) enforce byte-identity + the two controls."""
    from tests.oracle.llm_cassette import llm_cassette  # noqa: PLC0415
    from tests.oracle.retrieval_cassette import retrieval_cassette  # noqa: PLC0415
    import hashlib  # noqa: PLC0415
    import contextlib as _contextlib  # noqa: PLC0415

    if mode == "seed-retrieval":
        retr_mode, llm_mode = "record", "record"
    elif mode == "record":
        retr_mode, llm_mode = "replay", "record"
    elif mode == "replay":
        retr_mode, llm_mode = "replay", "replay"
    else:
        raise SystemExit(f"unknown --mode {mode!r} (use seed-retrieval | record | replay)")

    print(f"[oracle] mode={mode} retrieval-cassette={retr_mode} llm-cassette={llm_mode}")
    print(f"[oracle] retrieval tape: {_RETRIEVAL_TAPE}")
    print(f"[oracle] llm tape:       {_LLM_TAPE}")

    _CASSETTE_DIR.mkdir(parents=True, exist_ok=True)

    # Order matters: retrieval cassette is the OUTER context so its patched run_live_retrieval is in
    # place before any scenario runs; the llm cassette patches the OpenRouter boundary independently.
    # _frozen_step_clock normalizes the per-step elapsed the notebook feeds the decide prompt (a
    # non-behavioural wall-clock input) so record and replay issue byte-identical decide requests.
    with _frozen_step_clock(), \
            retrieval_cassette(_RETRIEVAL_TAPE, retr_mode), \
            llm_cassette(_LLM_TAPE, llm_mode):
        result = await _run_scenarios(only)

    print("\n" + "#" * 80)
    print("ACCEPTANCE SUMMARY (oracle mode)")
    print("#" * 80)
    print(json.dumps(result, indent=2, default=str))

    golden = _canonical_golden(result)
    golden_bytes = golden.encode("utf-8")
    sha = hashlib.sha256(golden_bytes).hexdigest()

    out_dir = Path(os.environ.get("PG_ACCEPTANCE_OUT_DIR", str(_REPO_ROOT)))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "acceptance_result.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")

    if mode in ("seed-retrieval", "record") or (mode == "replay" and not _GOLDEN_PATH.is_file()):
        # Recording writes the golden as the reference artifact for later byte-compare. A replay run
        # ALSO writes it when the reference is absent (first-replay bootstrap after a canonicalizer
        # change), so the golden always reflects the current canonical form; subsequent replays then
        # byte-compare against it.
        _GOLDEN_PATH.write_bytes(golden_bytes)
        print(f"\n[oracle] wrote golden -> {_GOLDEN_PATH}")
    print(f"[oracle] GOLDEN SHA-256: {sha}")
    print(f"[oracle] GOLDEN bytes:   {len(golden_bytes)}")

    if mode == "replay" and _GOLDEN_PATH.is_file():
        ref = _GOLDEN_PATH.read_bytes()
        if ref != golden_bytes:
            print("\n[oracle] REPLAY MISMATCH vs recorded golden (behaviour change / non-determinism)")
            print(f"  recorded sha={hashlib.sha256(ref).hexdigest()}")
            print(f"  replay   sha={sha}")
            sys.exit(3)
        print("[oracle] replay artifact BYTE-IDENTICAL to recorded golden.")

    # Enforce BOTH controls exactly as the live harness does.
    failures: list[str] = []
    if "thin" in result and not result["thin"].get("valid_positive_control"):
        failures.append("positive control (THIN): valid_positive_control=False")
    if "saturated" in result and not result["saturated"].get("valid_negative_control"):
        failures.append("negative control (SATURATED): valid_negative_control=False")
    if failures:
        print("\nACCEPTANCE FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nACCEPTANCE PASSED: all run controls valid")


async def main() -> None:
    # Iter-2: allow re-verifying a single scenario (``--only thin`` / ``--only saturated``) so a
    # targeted fix to one path doesn't force re-spending on the other, already-passing scenario.
    # Default (no arg) runs BOTH, unchanged, and writes the full acceptance_result.json.
    only = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only = sys.argv[idx + 1].strip().lower()

    mode = _parse_mode()
    if mode is not None:
        await _main_oracle(mode, only)
        return

    result = await _run_scenarios(only)
    print("\n" + "#" * 80)
    print("ACCEPTANCE SUMMARY")
    print("#" * 80)
    print(json.dumps(result, indent=2, default=str))
    # (4) output dir: env override PG_ACCEPTANCE_OUT_DIR wins; else the repo root (mirrors the
    #     original which wrote into /workspace/outline_agent_wt, i.e. the repo root of the old
    #     container layout). Dir is created if absent.
    out_dir = Path(os.environ.get("PG_ACCEPTANCE_OUT_DIR", str(_REPO_ROOT)))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = "acceptance_result.json" if only is None else f"acceptance_result_{only}.json"
    out_path = out_dir / out_name
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(f"[portable] wrote {out_path}")

    # Enforce BOTH controls: the harness must exit NON-ZERO if the positive (THIN) control did not
    # fire a search + mutate the outline, or if the negative (SATURATED) control did not stay at
    # zero retrieval on a genuinely-built loop. A scenario that was not run this invocation
    # (``--only``) is skipped, not treated as a failure.
    failures: list[str] = []
    if "thin" in result and not result["thin"].get("valid_positive_control"):
        failures.append("positive control (THIN): valid_positive_control=False")
    if "saturated" in result and not result["saturated"].get("valid_negative_control"):
        failures.append("negative control (SATURATED): valid_negative_control=False")
    if failures:
        print("\nACCEPTANCE FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nACCEPTANCE PASSED: all run controls valid")


if __name__ == "__main__":
    asyncio.run(main())
