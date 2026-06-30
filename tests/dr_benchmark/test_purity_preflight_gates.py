"""Durable section-test for the I-deepfix-001 (#1344) WINNERS-ONLY purity preflight gates.

This is the pytest-native, COMPREHENSIVE successor to the proven 8/8 offline smoke
(scratchpad ``purity_preflight_smoke.py``). It section-tests the three serious-preflight gates
authored INTO ``preflight_full_capability`` plus the W9 loud operator-ack gate, each with POSITIVE
and NEGATIVE cases, so we trust each gate as a winner — functional AND bug-free — BEFORE it gates a
paid run.

The four gates under test (file:line in ``scripts/dr_benchmark/run_gate_b.py``):
  * GATE (A) NO-LOSER         — run_gate_b.py:2503  (every killed loser provably dead, fail-CLOSED)
  * GATE (B) WINNER-FIRES     — run_gate_b.py:2617  (firing-marker contract + offline identity probes)
  * GATE (C) SLATE-PURITY     — run_gate_b.py:2722  (every force-on flag maps to a winner/infra)
  * W9 GATE                   — run_gate_b.py:2744  (DARK winner; subsumed proceeds; DROP needs ack)

EVERYTHING IS OFFLINE: NO spend, NO network, NO GPU, NO model LOAD. ``preflight_full_capability`` is
always called with ``offline=True`` so the W4 GPU-present probe (run_gate_b.py:2632) and the W5 GPU
warning (run_gate_b.py:2701) — the only LIVE host-capability checks — are skipped exactly as on the
production offline path (``run_gate_b_query(transport=<fake>)`` passes ``offline=(transport is not None)``,
run_gate_b.py:3183). Every STRUCTURAL gate check (NO-LOSER, the W5/W6/W7 model-identity probes,
SLATE-PURITY, W9) is config-only and stays unconditional offline.

The FROZEN faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is NEVER
touched here — this is retrieval-orchestration purity only.

Hermetic: each test snapshots/restores os.environ (the _isolate_env autouse fixture) so a forced
loser/winner flag never leaks into a sibling test. Mirrors the conventions in
tests/dr_benchmark/test_slate_readiness_flags_iready016b.py.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

# The W4/W5 GPU probes are import-guarded inside the gate and only bind when offline=False, so an
# absent ``torch`` is irrelevant to these offline tests. But run_gate_b imports torch lazily in a few
# code paths; stub a minimal cuda-present module ONLY if torch is genuinely uninstalled (not merely
# unimported) so an unrelated import never fails the suite. (The gate is always called offline here, so
# cuda.is_available is never read.)
#
# Codex diff-gate P2 (P2-global-torch-stub-pollution): the prior ``if "torch" not in sys.modules`` stubbed
# a fake torch whenever torch had simply not been imported YET — even with REAL torch installed — which
# poisons any later pytest module that does ``import torch`` and gets the stub. Probe importlib for a real
# torch FIRST; only stub when torch is genuinely absent from the environment.
if "torch" not in sys.modules:  # pragma: no cover - only on a no-torch CI host
    import importlib.util as _importlib_util

    if _importlib_util.find_spec("torch") is None:
        _torch_stub = types.ModuleType("torch")
        _torch_stub.cuda = types.SimpleNamespace(is_available=lambda: True)
        sys.modules["torch"] = _torch_stub

from scripts.dr_benchmark import run_gate_b
from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_ON_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS,
    _FiringMarker,
    _WINNER_FIRING_MARKER_CONTRACT,
    _WINNER_FLAG_ALLOWLIST,
    apply_full_capability_benchmark_slate,
    firing_marker_contract_substrings,
    firing_marker_matched,
    preflight_full_capability,
)

# ── the killed LOSERS, one test per loser (NO-LOSER gate, run_gate_b.py:2503) ─────────────────────
# (env_var, value_to_arm, needle_that_must_appear_in_the_RuntimeError). Each is armed ALONE on top of
# the clean winners-only slate; the gate must fail CLOSED naming it. Sourced from the slate's killed
# losers (run_gate_b.py:518-539), the live-embedder hole (A.5, run_gate_b.py:2574), and the gemma
# absence (A.6, run_gate_b.py:2585).
_LOSER_NEGATIVE_CASES: tuple[tuple[str, str, str], ...] = (
    # boolean STORM / agentic / deepener / decompose / iterresearch / research-planner losers —
    # caught by the REQUIRED_OFF loop (run_gate_b.py:2362) the NO-LOSER gate consolidates.
    ("PG_STORM_ENABLED_IN_BENCHMARK", "1", "PG_STORM_ENABLED_IN_BENCHMARK"),
    ("PG_STORM_INGEST_WEB_RESULTS", "1", "PG_STORM_INGEST_WEB_RESULTS"),
    ("PG_AGENTIC_SEARCH_IN_BENCHMARK", "1", "PG_AGENTIC_SEARCH_IN_BENCHMARK"),
    ("PG_SWEEP_EVIDENCE_DEEPENER", "1", "PG_SWEEP_EVIDENCE_DEEPENER"),
    ("PG_SWEEP_QUERY_DECOMPOSE", "1", "PG_SWEEP_QUERY_DECOMPOSE"),
    ("PG_QGEN_ITERRESEARCH", "1", "PG_QGEN_ITERRESEARCH"),
    ("PG_USE_RESEARCH_PLANNER", "1", "PG_USE_RESEARCH_PLANNER"),
    # STORM under-fire floor must be 0 (A.3, run_gate_b.py:2548) — a non-zero re-introduces the STORM
    # self-abort surface.
    ("PG_STORM_MIN_EFFECTIVE_QUERIES", "12", "PG_STORM_MIN_EFFECTIVE_QUERIES"),
    # the live relevance embedder hole (A.5, run_gate_b.py:2574): PG_EMBED_MODEL is what the live loader
    # reads — a MiniLM value routes the embedder to a killed loser while the env-string preflight is green.
    ("PG_EMBED_MODEL", "all-MiniLM-L6-v2", "PG_EMBED_MODEL"),
    # gemma must be ABSENT from the live judge + evaluator (A.6, run_gate_b.py:2585).
    ("PG_ENTAILMENT_MODEL", "google/gemma-2-27b-it", "gemma"),
    ("PG_EVALUATOR_MODEL", "google/gemma-2-27b-it", "gemma"),
)


@pytest.fixture(autouse=True)
def _isolate_env():
    """Snapshot os.environ before each test and restore it after, so a forced loser/winner flag (or the
    full-capability slate) does not leak into sibling tests. The _BENCHMARK_FORCE_ON_FLAGS module
    frozenset is also restored by tests that mutate it (the SLATE-PURITY negative)."""
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


def _apply_clean_winners_only_slate() -> None:
    """Reproduce the production env state the run sees JUST BEFORE preflight_full_capability runs: the
    full-capability slate PLUS the programmatic env-forces run_gate_b_query applies before it calls
    preflight (run_gate_b.py:3036-3183). Sourced verbatim from the proven smoke + run_gate_b_query, then
    EXTENDED with the complete REQUIRED / REQUIRED-OFF flag sets so a negative test isolates exactly the
    gate under test (otherwise the preflight trips on the first unrelated unset required flag).

    This leaves a CLEAN winners-only slate: every winner pinned ON / to its winner value, every killed
    loser provably OFF — the exact state a paid run must satisfy.
    """
    # Clear any loser env an operator .env might carry, so the slate's force-EXACT "0" is the only value.
    for _k in (
        "PG_STORM_ENABLED_IN_BENCHMARK", "PG_STORM_INGEST_WEB_RESULTS", "PG_STORM_ENABLED",
        "PG_STORM_OUTLINE_SECTIONS", "PG_STORM_MIN_EFFECTIVE_QUERIES",
        "PG_AGENTIC_SEARCH_IN_BENCHMARK", "PG_SWEEP_EVIDENCE_DEEPENER", "PG_SWEEP_QUERY_DECOMPOSE",
        "PG_QGEN_ITERRESEARCH", "PG_USE_RESEARCH_PLANNER",
        "PG_EMBED_MODEL", "PG_ENTAILMENT_MODEL", "PG_EVALUATOR_MODEL",
        "PG_W9_CONTENT_DEDUP", "PG_W9_DARK_ACK",
    ):
        os.environ.pop(_k, None)

    apply_full_capability_benchmark_slate()

    # Mirror the programmatic env-forces run_gate_b_query sets BEFORE preflight (run_gate_b.py:3036-3175)
    # that are NOT in the slate dict but ARE pre-required by the pre-existing preflight checks that run
    # before the 3 new gates. Sourced verbatim from run_gate_b_query.
    for _name, _value in {
        "PG_AGENTIC_SEARCH_IN_BENCHMARK": "0",      # loser, force-off (run_gate_b.py:3104)
        "PG_DEPTH_ANNOTATION_IN_BENCHMARK": "1",
        "PG_NLI_IN_BENCHMARK": "1",
        "PG_USE_SAFETY_REFUSAL": "1",
        "PG_SWEEP_NLI_CONFLICT": "1",
        "PG_BENCHMARK_STRICT_GATES": "1",
        "PG_SWEEP_TABLE_CELL_VERIFY": "1",
        "PG_SECTION_DISTILL": "1",
        "PG_RELEVANCE_SCORER": "semantic_v2",
        "PG_TRAFILATURA_SUBPROCESS": "1",
        "PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY": "1",
    }.items():
        os.environ[_name] = _value

    # Satisfy the COMPLETE required-flag contract so a negative isolates the gate under test (mirrors
    # test_slate_readiness_flags_iready016b: set EVERY required flag, then arm exactly one loser/fault).
    for _flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[_flag] = "1"
    # Every killed loser provably OFF (the REQUIRED_OFF contract the NO-LOSER gate consolidates).
    for _flag in _BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS:
        os.environ[_flag] = "0"
    # The binding-verifier enforce mode the preflight requires (slate sets it; make it explicit so the
    # test is independent of slate ordering).
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"


def _run_preflight_offline() -> None:
    """Call the preflight on the OFFLINE path (offline=True) — skips ONLY the W4/W5 GPU-host probes, the
    3 purity gates' STRUCTURAL checks stay unconditional. No spend, no network, no GPU."""
    preflight_full_capability(offline=True)


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# GATE (A) NO-LOSER — run_gate_b.py:2503
# ════════════════════════════════════════════════════════════════════════════════════════════════════

def test_no_loser_positive_clean_slate_passes():
    """POSITIVE: the clean winners-only slate (every winner pinned, every loser provably dead) PASSES the
    offline preflight with NO raise — the NO-LOSER + all sibling gates are satisfied."""
    _apply_clean_winners_only_slate()
    # Must not raise — a clean slate is exactly the state a paid run must reach.
    _run_preflight_offline()


@pytest.mark.parametrize(
    "loser_env, loser_value, needle",
    _LOSER_NEGATIVE_CASES,
    ids=[c[0] for c in _LOSER_NEGATIVE_CASES],
)
def test_no_loser_negative_one_loser_armed_raises(loser_env, loser_value, needle):
    """NEGATIVE, ONE TEST PER LOSER: arm exactly that loser on top of the clean slate; the NO-LOSER gate
    (or the REQUIRED_OFF loop it consolidates) must fail CLOSED with a RuntimeError naming the loser. A
    silently re-armed loser can therefore NEVER reach a paid run."""
    _apply_clean_winners_only_slate()
    os.environ[loser_env] = loser_value  # arm just this one loser
    with pytest.raises(RuntimeError) as exc:
        _run_preflight_offline()
    assert needle.lower() in str(exc.value).lower(), (
        f"NO-LOSER gate raised but the message does not name {needle!r}: {str(exc.value)[:200]}"
    )


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# GATE (C) SLATE-PURITY — run_gate_b.py:2722
# ════════════════════════════════════════════════════════════════════════════════════════════════════

def test_slate_purity_positive_clean_allowlisted_slate_passes():
    """POSITIVE: with the clean slate, EVERY force-on flag (+ every truthy force-EXACT key) is in the
    _WINNER_FLAG_ALLOWLIST, so the SLATE-PURITY gate PASSES with no raise."""
    _apply_clean_winners_only_slate()
    _run_preflight_offline()
    # Sanity: the structural invariant the gate asserts — every current force-on flag is allowlisted.
    unrecognized = sorted(set(_BENCHMARK_FORCE_ON_FLAGS) - set(_WINNER_FLAG_ALLOWLIST))
    assert not unrecognized, f"force-on flags not in the winner allowlist: {unrecognized}"


def test_slate_purity_negative_bogus_force_on_flag_raises(monkeypatch):
    """NEGATIVE: inject a bogus non-winner flag into the force-on set (the 'next STORM' re-introduced as a
    force-on). The SLATE-PURITY gate must fail CLOSED — the flag maps to no winner in the allowlist —
    naming the flag. monkeypatch restores _BENCHMARK_FORCE_ON_FLAGS after the test."""
    _apply_clean_winners_only_slate()
    bogus = "PG_SOME_FAKE_LOSER"
    monkeypatch.setattr(
        run_gate_b,
        "_BENCHMARK_FORCE_ON_FLAGS",
        frozenset(set(_BENCHMARK_FORCE_ON_FLAGS) | {bogus}),
    )
    os.environ[bogus] = "1"
    with pytest.raises(RuntimeError) as exc:
        _run_preflight_offline()
    msg = str(exc.value)
    assert "SLATE-PURITY" in msg and bogus in msg, (
        f"SLATE-PURITY gate did not fail closed on the bogus force-on flag: {msg[:200]}"
    )
    assert "maps to no winner" in msg.lower()


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# GATE (B) WINNER-FIRES — run_gate_b.py:2617 (the firing-marker contract + offline identity probes)
# ════════════════════════════════════════════════════════════════════════════════════════════════════

# The 14 winner keys the post-run firing-marker contract MUST carry (W1-W14, ALL — I-deepfix-001 #1344
# GRADUATED W9 from DARK to wired, so it is now grep-asserted on the run like every other winner). Order
# matches the contract dict.
_EXPECTED_FIRING_MARKER_KEYS = (
    "W1_scope_intent_frame",
    "W2_qgen_fs_researcher",
    "W3_fusion_wrrf",
    "W4_clinical_pdf_mineru25",
    "W5_relevance_content_judge",
    "W6_embed_qwen3_8b",
    "W7_rerank_qwen3_4b",
    "W8_cred_llm_tiering",
    "W9_dedup_content_consolidate",
    "W10_consolidate_nli",
    "W11_adequacy_crag",
    "W12_compose_floor_abstractive",
    "W13_verify_keep_floor",
    "W14_render_det",
)


def test_winner_fires_firing_marker_contract_has_14_winner_keys_with_nonempty_markers():
    """The WINNER-FIRES post-run firing-marker contract (_WINNER_FIRING_MARKER_CONTRACT) must carry
    exactly the 14 expected winner keys (W1-W14, including the now-GRADUATED W9), each with a NON-EMPTY
    firing marker the post-run §-1.1 audit greps. A missing key / empty marker would let a wired-but-dark
    winner ship unverified."""
    assert set(_WINNER_FIRING_MARKER_CONTRACT.keys()) == set(_EXPECTED_FIRING_MARKER_KEYS), (
        "firing-marker contract keys drifted from the expected 14 winners: "
        f"missing={sorted(set(_EXPECTED_FIRING_MARKER_KEYS) - set(_WINNER_FIRING_MARKER_CONTRACT))}, "
        f"extra={sorted(set(_WINNER_FIRING_MARKER_CONTRACT) - set(_EXPECTED_FIRING_MARKER_KEYS))}"
    )
    assert len(_WINNER_FIRING_MARKER_CONTRACT) == 14
    for _key, _marker in _WINNER_FIRING_MARKER_CONTRACT.items():
        assert isinstance(_marker, _FiringMarker), (
            f"firing marker for {_key} must be a _FiringMarker predicate, not a bare substring "
            f"(Codex P1: a bare substring false-passes on degraded/premature lines)"
        )
        assert _marker.must_contain.strip(), (
            f"firing marker for {_key} has an empty must_contain — the post-run grep would never assert it fired"
        )
        assert all(isinstance(_f, str) and _f.strip() for _f in _marker.forbid), (
            f"firing marker for {_key} has an empty/blank forbid substring — a blank forbid matches every "
            f"line and would suppress EVERY genuine fire"
        )
    # I-deepfix-001 #1344: W9 GRADUATED — it MUST now be present in the firing-marker contract (its
    # consolidate-keep-all canary [content_dedup_consolidate] W9: is grep-asserted post-run like the rest).
    assert any(_k.startswith("W9") for _k in _WINNER_FIRING_MARKER_CONTRACT), (
        "W9 must be in the firing-marker contract — it was graduated from DARK to a wired winner"
    )


def test_winner_fires_offline_identity_probes_pass_on_clean_slate():
    """The OFFLINE-tractable WINNER-FIRES identity probes (W5/W6/W7 model-identity, run_gate_b.py:2648-
    2700) run unconditionally and must PASS on the clean slate — they read the config/env id, NOT a GPU
    load. (The deep GPU-load probes are documented-DEFERRED to the VM run; see the next test — they are
    NOT faked here.) Reaching the end of preflight with no raise proves these identity probes passed."""
    _apply_clean_winners_only_slate()
    _run_preflight_offline()  # no raise == the offline identity probes (W5/W6/W7) all passed


def test_winner_fires_deep_load_probes_are_documented_deferred_not_faked():
    """The HEAVY behavioral probes (actual GPU model load / live LLM spend — W4 extract, W5 score_passages
    device, W6 4096-dim cosine, W7 reorder, W8 llm_success>0, W10 NLI merge, W11 CRAG grade, W12 drafts>0,
    W13 strict_verify fixture) are DEFERRED to the VM run + the post-run firing-marker grep — NOT faked at
    offline preflight (a heavy GPU load / real-corpus LLM spend is forbidden off-VM). This test asserts
    that deferral is DOCUMENTED in the source (the honest contract), so 'deferred' can never silently
    become 'skipped-and-forgotten'."""
    import inspect

    src = inspect.getsource(preflight_full_capability)
    # The DEFERRED-PROBE NOTE (run_gate_b.py:2715) names each deferred winner + the honest reason.
    assert "DEFERRED-PROBE NOTE" in src, "the honest deferred-probe note is missing from the gate source"
    assert "NOT faked" in src, "the gate source must state the deferred probes are NOT faked"
    # Each deferred heavy winner is named in the note so the post-run audit knows what to grep.
    for _deferred_winner in ("W4", "W8", "W11", "W12", "W13"):
        assert _deferred_winner in src, f"deferred heavy winner {_deferred_winner} not named in the gate"


# ── Codex diff-gate P1 fix: each firing marker is a SUCCESS-SPECIFIC predicate, NOT a bare substring ──
# (the contract is now {winner -> _FiringMarker(must_contain, forbid, conditional)}; firing_marker_matched
# is the matcher the post-run audit + this test both consume — run_gate_b.py:1898-1990).

# For each flagged winner: a GENUINE-fire log line (must match) and the DEGRADED / PREMATURE / FAILURE
# twin that previously false-passed the bare substring (must NOT match). The genuine lines are the EXACT
# producer success strings (file:line in the per-winner comment); the degraded lines are the EXACT producer
# degrade strings the prior bare substring matched. (winner_key, genuine_line, degraded_line).
_FIRING_PREDICATE_CASES: tuple[tuple[str, str, str], ...] = (
    # W5 — genuine reranker fire stamps a real device; the load-FAILURE twin stamps device=unavailable
    # (silent full-weight fallback) yet still carries "scored=" (live_retriever.py:4699).
    (
        "W5_relevance_content_judge",
        "[live_retriever] W2 content-relevance: scored=42 relevant=30 demoted=12 escalated=0 device=cuda (DEMOTE keeps low weight, NO drop)",
        "[live_retriever] W2 content-relevance: scored=42 relevant=42 demoted=0 escalated=0 device=unavailable (DEMOTE keeps low weight, NO drop)",
    ),
    # W6 — genuine 8B load line; the load-failure twin (prefetch_offtopic_filter.py:121) means embedder=None.
    (
        "W6_embed_qwen3_8b",
        "[prefetch_offtopic] loading relevance embedder model=Qwen/Qwen3-Embedding-8B (B1 locked-slate default; PG_EMBED_MODEL overrides)",
        "[prefetch_offtopic] Embedder not available: CUDA OOM — skipping filter (fail-open)",
    ),
    # W8 — genuine GLM tiering (llm_success>0); the DEGRADED rules-floor twin (credibility_llm_tiering.py:294).
    (
        "W8_cred_llm_tiering",
        "[credibility_llm_tiering] tiered via GLM: attempted=20 llm_success=18 fallback=2 error=0",
        "[credibility_llm_tiering] DEGRADED (rules-floor only): attempted=20 llm_success=0 fallback=20 error=0 — GLM tiering did NOT fire",
    ),
    # W11 — genuine graded verdict in {correct,ambiguous,incorrect}; the error twin (crag_adequacy_loop.py:360
    # returns verdict="error" on a raised classifier call) the bare substring false-passed.
    (
        "W11_adequacy_crag",
        "[crag-adequacy] classifier verdict=correct  sufficient=True  ",
        "[crag-adequacy] classifier verdict=error  sufficient=False  ",
    ),
    # W12 — genuine drafts>0; the 0/0 degraded skip (abstractive_writer.py:603) the bare substring matched.
    (
        "W12_compose_floor_abstractive",
        "[abstractive_writer] pre-pass complete: 7/9 baskets drafted (model=z-ai/glm-5.2, retries=1, wall=540s, abandoned=2)",
        "[abstractive_writer] pre-pass complete: 0/0 baskets drafted (model=z-ai/glm-5.2)",
    ),
    # W13 — genuine per-section verified-compose fire (the section TITLE sits between the tag and the phrase);
    # the degraded twin is an unrelated "[multi_section]" drop line the prior bare "[multi_section]" matched.
    (
        "W13_verify_keep_floor",
        "[multi_section] Clinical efficacy verified-compose PRIMARY: 4 baskets -> draft_chars=812",
        "[multi_section] outline dropped off-list title 'Appendix'",
    ),
)


@pytest.mark.parametrize(
    "winner_key, genuine_line, degraded_line",
    _FIRING_PREDICATE_CASES,
    ids=[c[0] for c in _FIRING_PREDICATE_CASES],
)
def test_firing_marker_matches_genuine_fire_and_rejects_degraded(winner_key, genuine_line, degraded_line):
    """Codex P1 (P1-winner-firing-contract-false-positive): the firing-marker predicate must MATCH a genuine
    fire and REJECT the degraded / premature / failure twin that the prior bare substring false-passed. Both
    lines share the bare substring; only the genuine line is a clean fire. This is the exact "add tests that
    degraded logs do NOT match" Codex asked for."""
    marker = _WINNER_FIRING_MARKER_CONTRACT[winner_key]
    assert firing_marker_matched(marker, genuine_line), (
        f"{winner_key}: the GENUINE fire line did not match the predicate {marker!r}"
    )
    assert not firing_marker_matched(marker, degraded_line), (
        f"{winner_key}: the DEGRADED/premature line FALSE-MATCHED the predicate {marker!r} — the bare-"
        f"substring false-positive Codex flagged is NOT fixed"
    )
    # And in a real multi-line run log where BOTH appear, the winner DID fire (one clean line is enough).
    assert firing_marker_matched(marker, degraded_line + "\n" + genuine_line), (
        f"{winner_key}: a run with one degraded + one genuine line must count as a genuine fire"
    )
    # ...but a log with ONLY the degraded line must NOT count as a fire (the winner-dark case).
    assert not firing_marker_matched(marker, "unrelated line\n" + degraded_line + "\nanother line"), (
        f"{winner_key}: a run with ONLY the degraded line must NOT count as a genuine fire"
    )


# Each marker's must_contain is verified to be a REAL producer SUCCESS string (NOT a phantom): the post-run
# audit greps these against the run log, so a typo'd / drifted / phantom marker would silently FALSE-FAIL
# every run (or, for a removed producer line, can never assert a genuine fire). {winner_key -> (producer
# source path relative to repo root, expected #-of-matches lower bound)}. The producer files are read as
# TEXT (no import, no spend, no network) and the must_contain (with %s format placeholders accounted for) is
# asserted present. This catches the OPPOSITE-direction defect from the false-positive: a marker pointing at
# a string no producer emits.
_PRODUCER_SOURCE_FOR_MARKER: dict[str, str] = {
    "W1_scope_intent_frame": "src/polaris_graph/nodes/intent_frame.py",
    "W2_qgen_fs_researcher": "scripts/run_honest_sweep_r3.py",
    "W3_fusion_wrrf": "src/polaris_graph/retrieval/live_retriever.py",
    "W4_clinical_pdf_mineru25": "src/tools/access_bypass.py",
    "W5_relevance_content_judge": "src/polaris_graph/retrieval/live_retriever.py",
    "W6_embed_qwen3_8b": "src/polaris_graph/retrieval/prefetch_offtopic_filter.py",
    "W7_rerank_qwen3_4b": "src/polaris_graph/retrieval/qwen_reranker_scorer.py",
    "W8_cred_llm_tiering": "src/polaris_graph/retrieval/credibility_llm_tiering.py",
    "W9_dedup_content_consolidate": "src/polaris_graph/synthesis/content_dedup_consolidate.py",
    "W10_consolidate_nli": "src/polaris_graph/synthesis/consolidation_nli.py",
    "W11_adequacy_crag": "scripts/run_honest_sweep_r3.py",
    "W12_compose_floor_abstractive": "src/polaris_graph/generator/abstractive_writer.py",
    "W13_verify_keep_floor": "src/polaris_graph/generator/multi_section_generator.py",
    "W14_render_det": "scripts/run_honest_sweep_r3.py",
}

# The producer emits the marker via a %s-formatted logger/_log call, so the runtime line contains the
# must_contain as a literal PREFIX up to the first format placeholder. The producer SOURCE therefore contains
# the must_contain verbatim EXCEPT where a model id / count is interpolated mid-string. For the two markers
# whose must_contain embeds an interpolated value, assert the stable literal stem the producer source carries.
_PRODUCER_SOURCE_STEM_OVERRIDE: dict[str, str] = {
    # W6/W7 must_contain embeds the model id; the producer logs it via "model=%s" / "loading %s", so the
    # source carries the bracket-tag stem, and the id is pinned by the separate offline IDENTITY probe.
    "W6_embed_qwen3_8b": "[prefetch_offtopic] loading relevance embedder model=",
    "W7_rerank_qwen3_4b": "[qwen-reranker] loading ",
}


def test_every_firing_marker_must_contain_is_a_real_producer_string():
    """Every marker's ``must_contain`` (or its stable literal stem) MUST appear verbatim in its named producer
    source file — so a phantom / drifted marker (a string no producer emits) fails LOUDLY here instead of
    silently false-failing every paid run's post-run audit. Reads producer files as TEXT (no import / spend /
    network). This is the opposite-direction guard to the false-positive predicate test above."""
    import pathlib

    repo_root = pathlib.Path(run_gate_b.__file__).resolve().parents[2]
    assert set(_PRODUCER_SOURCE_FOR_MARKER.keys()) == set(_WINNER_FIRING_MARKER_CONTRACT.keys()), (
        "the producer-source map drifted from the firing-marker contract keys"
    )
    for winner_key, marker in _WINNER_FIRING_MARKER_CONTRACT.items():
        needle = _PRODUCER_SOURCE_STEM_OVERRIDE.get(winner_key, marker.must_contain)
        src_path = repo_root / _PRODUCER_SOURCE_FOR_MARKER[winner_key]
        assert src_path.is_file(), f"{winner_key}: producer source {src_path} does not exist"
        text = src_path.read_text(encoding="utf-8", errors="replace")
        assert needle in text, (
            f"{winner_key}: must_contain stem {needle!r} not found in producer {src_path} — the marker is a "
            f"PHANTOM (a string no producer emits); the post-run audit would never assert this winner fired"
        )


def test_firing_marker_contract_substrings_back_compat_view():
    """``firing_marker_contract_substrings()`` returns the {winner -> must_contain} positive-substring view
    (back-compat surface for a consumer that only needs the positive grep needle); it must carry the same 14
    keys (W1-W14 incl. the graduated W9), each non-empty."""
    subs = firing_marker_contract_substrings()
    assert set(subs.keys()) == set(_WINNER_FIRING_MARKER_CONTRACT.keys())
    assert len(subs) == 14
    for _key, _needle in subs.items():
        assert _needle and _needle.strip(), f"{_key}: empty positive substring"


# ════════════════════════════════════════════════════════════════════════════════════════════════════
# W9 GATE — run_gate_b.py:2744 (DARK winner; loud operator-ack; never a silent pass, never a block)
# ════════════════════════════════════════════════════════════════════════════════════════════════════

def test_w9_subsumed_default_proceeds():
    """POSITIVE: with the §-1.3-violating DROP variant UNWIRED (the default), the W9 gate LOGS the
    keep-all-wired status loudly and PROCEEDS (no raise). I-deepfix-001 #1344: W9 is now WIRED via the
    consolidate-keep-all stage (PG_CONTENT_DEDUP_CONSOLIDATE, applied by the clean slate); the gate's only
    remaining job is to forbid the DROP variant."""
    _apply_clean_winners_only_slate()
    os.environ.pop("PG_W9_CONTENT_DEDUP", None)
    os.environ.pop("PG_W9_DARK_ACK", None)
    _run_preflight_offline()  # no raise == DROP variant unwired, keep-all winner proceeds


def test_w9_drop_variant_without_ack_raises():
    """NEGATIVE: wiring the ContentDeduplicator DROP variant (PG_W9_CONTENT_DEDUP truthy) WITHOUT the
    §-1.3 waiver (PG_W9_DARK_ACK) must fail CLOSED — a hard-drop content-dedup stage sheds corroborators
    and violates consolidate-keep-all. The error must name the flag."""
    _apply_clean_winners_only_slate()
    os.environ["PG_W9_CONTENT_DEDUP"] = "1"
    os.environ.pop("PG_W9_DARK_ACK", None)
    with pytest.raises(RuntimeError) as exc:
        _run_preflight_offline()
    msg = str(exc.value)
    assert "W9" in msg and "PG_W9_CONTENT_DEDUP" in msg, (
        f"W9 gate did not fail closed on the un-acked DROP variant: {msg[:200]}"
    )


def test_w9_drop_variant_with_ack_proceeds():
    """POSITIVE: wiring the DROP variant WITH the signed §-1.3 waiver (PG_W9_DARK_ACK=1) PROCEEDS under
    the explicit operator override (logged loudly, no raise) — the gate is never a hard block, only a
    loud ack requirement."""
    _apply_clean_winners_only_slate()
    os.environ["PG_W9_CONTENT_DEDUP"] = "1"
    os.environ["PG_W9_DARK_ACK"] = "1"
    _run_preflight_offline()  # no raise == the signed-waiver override branch proceeded
