"""I-deepfix-001 beat-both Wave A gate-fix — isolated OFFLINE tests for the 3 Codex findings.

NO paid API, NO GPU, NO network. Runs with a fake in-memory role transport + module-logger capture.

Covers:
  FIX 1 (P0, WS-1 judge cache run-scope): reset_judge_verdict_cache() wired at the per-document boundary.
    (a) a cache MISS falls through to a REAL judge call (never a synthesized default-VERIFIED);
    (b) after a reset, a claim from "document 2" does NOT inherit "document 1"'s cached verdict;
    (c) within ONE document, true byte-twins still SHARE the verdict (one paid call).
  FIX 2 (DROPPED per operator correction): the benchmark judge STAYS moonshotai/kimi-k2.6; the config is
    TWO-FAMILY (generator=glm vs judge=kimi, distinct lineages). Confirms the judge default is untouched,
    PG_BENCHMARK_JUDGE_MODEL was NOT force-pinned to glm, the 4-distinct-family check PASSES with
    gen=glm/judge=kimi, AND check_family_segregation still needs PERMIT=1 for the glm generator-vs-glm
    external-evaluator surface (so flipping PERMIT to 0 would ABORT — it is left at 1, flagged in the report).
  FIX 3 (P1, M6 firing-canary wiring): assert_cross_source_synthesis_fired is now callable in the post-run
    block; the capture handler tees the module-logger markers; the canary fails-closed on a silent-no-op.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

try:  # Windows console is cp1252; force UTF-8 so diagnostic prints never crash the test.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

# Arm the WS-1 idempotency cache (default ON already; be explicit so the test is env-independent).
os.environ["PG_JUDGE_VERDICT_IDEMPOTENCY"] = "1"
# Keep the enum un-wrap ON (default) — a bare token still falls through, so the fake can return bare tokens.

from src.polaris_graph.roles import judge_adapter  # noqa: E402
from src.polaris_graph.roles.judge_adapter import (  # noqa: E402
    reset_judge_verdict_cache,
    run_judge,
)
from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse  # noqa: E402

_PASS = 0
_FAIL = 0


def _check(name: str, cond: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}" + (f"  [{detail}]" if detail else ""))
    else:
        _FAIL += 1
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))


class _FakeTransport:
    """Minimal RoleTransport: returns a scripted verdict token per call and counts calls."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = list(tokens)
        self.calls = 0

    def complete(self, request: RoleRequest) -> RoleResponse:  # noqa: D401 - protocol impl
        self.calls += 1
        tok = self._tokens[min(self.calls - 1, len(self._tokens) - 1)]
        return RoleResponse(raw_text=tok, served_model="fake/glm-judge")


# ─────────────────────────────────────────────────────────────────────────────────────────────────────
# FIX 1 — judge verdict cache run-scope
# ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_fix1_cache_miss_falls_through_to_real_call() -> None:
    print("[FIX 1] (a) a cache MISS makes a REAL judge call — never a default-VERIFIED")
    reset_judge_verdict_cache()
    t = _FakeTransport(["UNSUPPORTED"])
    verdict, records = run_judge(
        t, "doc1 claim alpha", "doc1 span alpha", "grounded", "grounded",
        model_slug="fake/glm-judge",
    )
    _check("miss -> transport.complete called exactly once", t.calls == 1, f"calls={t.calls}")
    _check("miss -> returns the REAL served verdict (not default VERIFIED)", verdict == "UNSUPPORTED",
           f"verdict={verdict}")
    _check("miss -> a served RoleCallRecord is returned", bool(records) and records[0].parsed == "UNSUPPORTED")


def test_fix1_byte_twin_shares_verdict_within_one_document() -> None:
    print("[FIX 1] (c) within ONE document, byte-twins SHARE the verdict (one paid call)")
    reset_judge_verdict_cache()
    # If a second real call happened it would return UNSUPPORTED; a cache hit pins the first VERIFIED.
    t = _FakeTransport(["VERIFIED", "UNSUPPORTED"])
    v1, _ = run_judge(t, "same claim", "same span", "grounded", "grounded", model_slug="fake/glm-judge")
    v2, r2 = run_judge(t, "same claim", "same span", "grounded", "grounded", model_slug="fake/glm-judge")
    _check("first call served + pinned VERIFIED", v1 == "VERIFIED", f"v1={v1}")
    _check("byte-twin returns the SAME pinned verdict", v2 == "VERIFIED", f"v2={v2}")
    _check("byte-twin was a cache HIT — transport.complete called ONCE total", t.calls == 1, f"calls={t.calls}")
    _check("cache-hit record is marked, not a served call", "cache_hit" in (r2[0].raw_text or ""))


def test_fix1_reset_blocks_cross_document_inheritance() -> None:
    print("[FIX 1] (b) after reset, document-2 does NOT inherit document-1's cached verdict")
    reset_judge_verdict_cache()
    # Document 1: pin VERIFIED for (claim X, span Y).
    t1 = _FakeTransport(["VERIFIED"])
    v1, _ = run_judge(t1, "claim X", "span Y", "grounded", "grounded", model_slug="fake/glm-judge")
    _check("doc1 pins VERIFIED for (claim X, span Y)", v1 == "VERIFIED", f"v1={v1}")
    # === per-document boundary: run_gate_b_query calls this at the top of each report ===
    reset_judge_verdict_cache()
    # Document 2: SAME (claim X, span Y) but the fresh judge now returns UNSUPPORTED.
    t2 = _FakeTransport(["UNSUPPORTED"])
    v2, _ = run_judge(t2, "claim X", "span Y", "grounded", "grounded", model_slug="fake/glm-judge")
    _check("doc2 makes a FRESH call (reset cleared the pin)", t2.calls == 1, f"calls={t2.calls}")
    _check("doc2 returns the FRESH verdict, NOT the inherited VERIFIED", v2 == "UNSUPPORTED", f"v2={v2}")


def test_fix1_reset_helper_gate_and_wiring() -> None:
    print("[FIX 1] the per-document reset is WIRED in run_gate_b and gated on PG_JUDGE_VERDICT_IDEMPOTENCY")
    import scripts.dr_benchmark.run_gate_b as rgb
    _check("run_gate_b imports reset_judge_verdict_cache",
           rgb.reset_judge_verdict_cache is reset_judge_verdict_cache)
    # gate helper honors the kill-switch (default ON, OFF when explicitly off)
    _prev = os.environ.get("PG_JUDGE_VERDICT_IDEMPOTENCY")
    try:
        os.environ["PG_JUDGE_VERDICT_IDEMPOTENCY"] = "1"
        _check("gate ON by default/1", rgb._judge_verdict_idempotency_enabled() is True)
        os.environ["PG_JUDGE_VERDICT_IDEMPOTENCY"] = "0"
        _check("gate OFF when explicitly 0 (byte-identical revert)",
               rgb._judge_verdict_idempotency_enabled() is False)
    finally:
        if _prev is None:
            os.environ.pop("PG_JUDGE_VERDICT_IDEMPOTENCY", None)
        else:
            os.environ["PG_JUDGE_VERDICT_IDEMPOTENCY"] = _prev
    # the reset call must be present at the top of run_gate_b_query (source-level proof)
    src = Path(rgb.__file__).read_text(encoding="utf-8")
    _check("reset_judge_verdict_cache() called at the per-document boundary",
           "if _judge_verdict_idempotency_enabled():\n        reset_judge_verdict_cache()" in src)


# ─────────────────────────────────────────────────────────────────────────────────────────────────────
# FIX 2 (DROPPED) — judge stays kimi-k2.6; two-family posture; PERMIT stays 1 (glm eval surface)
# ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_fix2_judge_stays_kimi_and_not_force_pinned_to_glm() -> None:
    print("[FIX 2/DROP] the benchmark judge resolves to moonshotai/kimi-k2.6 and is NOT force-pinned to glm")
    from src.polaris_graph.roles.openrouter_role_transport import benchmark_verifier_slug
    import scripts.dr_benchmark.run_gate_b as rgb
    _prev = os.environ.pop("PG_BENCHMARK_JUDGE_MODEL", None)
    try:
        slug = benchmark_verifier_slug("judge")
    finally:
        if _prev is not None:
            os.environ["PG_BENCHMARK_JUDGE_MODEL"] = _prev
    _check("benchmark judge default == moonshotai/kimi-k2.6", slug == "moonshotai/kimi-k2.6", f"slug={slug}")
    _check("PG_BENCHMARK_JUDGE_MODEL NOT force-EXACT-pinned in the slate (FIX 2 reverted/never applied)",
           "PG_BENCHMARK_JUDGE_MODEL" not in rgb._BENCHMARK_FORCE_EXACT_FLAGS)
    _check("PG_BENCHMARK_JUDGE_MODEL NOT in the slate dict",
           "PG_BENCHMARK_JUDGE_MODEL" not in rgb._FULL_CAPABILITY_BENCHMARK_SLATE)


def test_fix2_four_distinct_family_passes_gen_glm_judge_kimi() -> None:
    print("[FIX 2/DROP] assert_four_role_families_distinct PASSES with generator=glm + judge=kimi (distinct)")
    import scripts.dr_benchmark.run_gate_b as rgb
    saved = {k: os.environ.get(k) for k in ("PG_FOUR_ROLE_TRANSPORT", "PG_GENERATOR_MODEL",
                                            "PG_MIRROR_MODEL", "PG_SENTINEL_MODEL", "PG_BENCHMARK_JUDGE_MODEL")}
    try:
        os.environ["PG_FOUR_ROLE_TRANSPORT"] = "openrouter"
        os.environ["PG_GENERATOR_MODEL"] = "z-ai/glm-5.2"   # the all-GLM generator
        for k in ("PG_MIRROR_MODEL", "PG_SENTINEL_MODEL", "PG_BENCHMARK_JUDGE_MODEL"):
            os.environ.pop(k, None)                          # use the operator-chosen benchmark defaults
        fams = rgb.assert_four_role_families_distinct()      # raises on a non-allowed collision
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    _check("generator family == z-ai (glm)", fams.get("generator") == "z-ai", f"fams={fams}")
    _check("judge family == moonshotai (kimi — DISTINCT from the glm generator)",
           fams.get("judge") == "moonshotai", f"judge={fams.get('judge')}")
    _check("sentinel family == minimax (distinct)", fams.get("sentinel") == "minimax")
    _check("no family-distinctness error fired (gen/mirror is the allowed collision; judge is its own lane)",
           True)


def test_fix2_permit_still_required_for_glm_evaluator_surface() -> None:
    print("[FIX 2/DROP] check_family_segregation still NEEDS PERMIT=1 (glm generator vs glm external evaluator)")
    from src.polaris_graph.llm.openrouter_client import check_family_segregation
    _prev = os.environ.get("PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY")
    try:
        # generator glm vs evaluator glm — the operator-locked side-judge->mirror (§9.1.8) is glm-5.2.
        os.environ["PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY"] = "0"
        raised = False
        try:
            check_family_segregation("z-ai/glm-5.2", "z-ai/glm-5.2")
        except RuntimeError:
            raised = True
        _check("PERMIT=0 -> ABORTS on glm-generator vs glm-evaluator (why FIX must leave PERMIT=1)", raised)
        os.environ["PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY"] = "1"
        gen_fam, eval_fam = check_family_segregation("z-ai/glm-5.2", "z-ai/glm-5.2")
        _check("PERMIT=1 -> passes (disclosed same-family relaxation), families both glm",
               gen_fam == "glm" and eval_fam == "glm", f"{gen_fam}/{eval_fam}")
    finally:
        if _prev is None:
            os.environ.pop("PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY", None)
        else:
            os.environ["PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY"] = _prev


# ─────────────────────────────────────────────────────────────────────────────────────────────────────
# FIX 3 — M6 firing-canary wiring
# ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_fix3_assert_fails_closed_on_silent_noop_and_passes_on_fired() -> None:
    print("[FIX 3] assert_cross_source_synthesis_fired: fails-closed on silent-no-op, passes on fired")
    import scripts.dr_benchmark.run_gate_b as rgb
    _prev = os.environ.get("PG_CROSS_SOURCE_SYNTHESIS")
    try:
        os.environ["PG_CROSS_SOURCE_SYNTHESIS"] = "1"
        noop = f"[cross_source_synthesis] 3 {rgb._CROSS_SOURCE_SILENT_NOOP_MARKER} per-clause re-verify"
        raised = False
        try:
            rgb.assert_cross_source_synthesis_fired(noop)
        except RuntimeError:
            raised = True
        _check("silent-no-op marker (and no fired marker) -> RuntimeError", raised)

        fired = f"{rgb._CROSS_SOURCE_FIRED_MARKER} 2 cross-source analytical unit(s) from 3 anchored pair(s)"
        ok = True
        try:
            rgb.assert_cross_source_synthesis_fired(fired)
        except RuntimeError:
            ok = False
        _check("fired/composed marker present -> no raise", ok)

        # both present (a section barren, another fired) -> run-level fired wins, no raise
        both = fired + "\n" + noop
        ok2 = True
        try:
            rgb.assert_cross_source_synthesis_fired(both)
        except RuntimeError:
            ok2 = False
        _check("fired + barren in same run -> run-level fired wins, no raise", ok2)

        # flag OFF -> self-skip even with the silent-no-op marker
        os.environ["PG_CROSS_SOURCE_SYNTHESIS"] = "0"
        ok3 = True
        try:
            rgb.assert_cross_source_synthesis_fired(noop)
        except RuntimeError:
            ok3 = False
        _check("PG_CROSS_SOURCE_SYNTHESIS off -> self-skip (no raise)", ok3)
    finally:
        if _prev is None:
            os.environ.pop("PG_CROSS_SOURCE_SYNTHESIS", None)
        else:
            os.environ["PG_CROSS_SOURCE_SYNTHESIS"] = _prev


def test_fix3_capture_handler_tees_module_logger_markers() -> None:
    print("[FIX 3] the capture handler tees the cross_source_synthesis MODULE-logger markers")
    import scripts.dr_benchmark.run_gate_b as rgb
    sink: list[str] = []
    handler = rgb._CrossSourceMarkerCaptureHandler(sink)
    lg = logging.getLogger(rgb._CROSS_SOURCE_SYNTHESIS_LOGGER)
    lg.addHandler(handler)
    try:
        # Emit EXACTLY as the producer does (module logger.warning with %d arg).
        lg.warning(
            "[cross_source_synthesis] %d anchored cross-source pair(s) but 0 analytical units survived "
            "per-clause re-verify/licensing — analytical layer produced nothing for this section", 3,
        )
    finally:
        lg.removeHandler(handler)
    joined = "\n".join(sink)
    _check("handler captured the module-logger line", bool(sink), f"captured={len(sink)}")
    _check("captured text carries the silent-no-op marker", rgb._CROSS_SOURCE_SILENT_NOOP_MARKER in joined)
    # end-to-end: captured text drives the assert to fail-closed
    _prev = os.environ.get("PG_CROSS_SOURCE_SYNTHESIS")
    try:
        os.environ["PG_CROSS_SOURCE_SYNTHESIS"] = "1"
        raised = False
        try:
            rgb.assert_cross_source_synthesis_fired(joined)
        except RuntimeError:
            raised = True
        _check("captured silent-no-op -> canary fails-closed end-to-end", raised)
    finally:
        if _prev is None:
            os.environ.pop("PG_CROSS_SOURCE_SYNTHESIS", None)
        else:
            os.environ["PG_CROSS_SOURCE_SYNTHESIS"] = _prev


def test_fix3_run_m6_firing_canary_status_and_killswitch() -> None:
    print("[FIX 3] _run_m6_firing_canary status matrix + PG_M6_FIRING_CANARY kill-switch")
    import scripts.dr_benchmark.run_gate_b as rgb
    _prev_cs = os.environ.get("PG_CROSS_SOURCE_SYNTHESIS")
    _prev_ks = os.environ.get("PG_M6_FIRING_CANARY")
    try:
        os.environ["PG_CROSS_SOURCE_SYNTHESIS"] = "1"
        noop = f"x {rgb._CROSS_SOURCE_SILENT_NOOP_MARKER} y"
        fired = f"{rgb._CROSS_SOURCE_FIRED_MARKER} 2 units"
        st_fail = rgb._run_m6_firing_canary([noop], "success", smoke_scale=False, domain="d", slug="s")
        _check("released + silent-no-op -> 'FAILED'", st_fail == "FAILED", f"st={st_fail}")
        st_ok = rgb._run_m6_firing_canary([fired], "released_with_disclosed_gaps",
                                          smoke_scale=False, domain="d", slug="s")
        _check("released + fired -> 'ok'", st_ok == "ok", f"st={st_ok}")
        st_skip = rgb._run_m6_firing_canary([noop], "abort_scope_rejected",
                                            smoke_scale=False, domain="d", slug="s")
        _check("non-released status -> skip (no fail)", st_skip.startswith("skip:"), f"st={st_skip}")
        st_smoke = rgb._run_m6_firing_canary([noop], "success", smoke_scale=True, domain="d", slug="s")
        _check("smoke_scale -> skip:smoke_scale", st_smoke == "skip:smoke_scale", f"st={st_smoke}")
        # kill-switch
        os.environ["PG_M6_FIRING_CANARY"] = "1"
        _check("PG_M6_FIRING_CANARY ON by default/1", rgb._m6_firing_canary_enabled() is True)
        os.environ["PG_M6_FIRING_CANARY"] = "0"
        _check("PG_M6_FIRING_CANARY OFF when 0 (byte-identical revert)",
               rgb._m6_firing_canary_enabled() is False)
    finally:
        for k, v in (("PG_CROSS_SOURCE_SYNTHESIS", _prev_cs), ("PG_M6_FIRING_CANARY", _prev_ks)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    tests = [
        test_fix1_cache_miss_falls_through_to_real_call,
        test_fix1_byte_twin_shares_verdict_within_one_document,
        test_fix1_reset_blocks_cross_document_inheritance,
        test_fix1_reset_helper_gate_and_wiring,
        test_fix2_judge_stays_kimi_and_not_force_pinned_to_glm,
        test_fix2_four_distinct_family_passes_gen_glm_judge_kimi,
        test_fix2_permit_still_required_for_glm_evaluator_surface,
        test_fix3_assert_fails_closed_on_silent_noop_and_passes_on_fired,
        test_fix3_capture_handler_tees_module_logger_markers,
        test_fix3_run_m6_firing_canary_status_and_killswitch,
    ]
    for t in tests:
        t()
    print(f"\n==== {_PASS} passed, {_FAIL} failed ====")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
