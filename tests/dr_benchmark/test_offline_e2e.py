"""Offline no-spend END-TO-END test (I-meta-002 PR-9 / readiness item 9). NO network, NO spend.

DRIVES `scripts.dr_benchmark.offline_e2e` through the WHOLE DR toolchain offline and asserts
the chain non-vacuously, so canary day adds ONLY real model calls. Codex DESIGN APPROVE iter 2
(.codex/I-meta-002-pr9-e2e/design_brief.md; zero P0/P1; 3 P2s folded in):

  * P2 #1 — the scorer-leg rubric/ledger fixtures are clearly labeled synthetic and live
    ISOLATED under tests/fixtures/offline_e2e/; the harness writes scored output ONLY to a
    tmp dir, NEVER under outputs/dr_benchmark/.
  * P2 #2 — NO-NETWORK FAIL-CLOSED: this module BLOCKS real network at the socket layer (a
    module-scoped autouse fixture monkeypatches socket.socket / socket.create_connection /
    socket.getaddrinfo to RAISE). A stray real connection therefore FAILS the test rather
    than silently networking; the whole e2e passing under the block IS the zero-network proof.
    The block is module-scoped (not session-global) so it can never surprise the other suites
    the Gate-A dry run / full pytest invoke.
  * P2 #3 — the M4 gate leg includes BOTH a MATCHING served-metadata fixture (PASS) and a
    WRONG-MODEL fixture (fail-closed / raises GateError).

Non-vacuous assertions (per the build spec):
  - manifest carries `four_role_evaluation` with a NON-EMPTY `evaluator_agrees` map obeying the
    §-1.1 safe rule (canned FABRICATED -> False; canned VERIFIED + kept -> True);
  - `four_role_claim_audit.json` is written + parseable, keys == final_verdicts keys;
  - the M4 pathB gate returns the per-role served identity on a MATCHING fixture and RAISES on
    the wrong-model fixture;
  - score_run emits a scored ledger file; aggregate_systems emits a systems summary file;
  - socket is blocked for the whole run and the e2e still passes (zero network/spend).
"""

from __future__ import annotations

import json
import socket

import pytest

from scripts.dr_benchmark.offline_e2e import (
    BENCHMARK_SLUG_EXPECTED_ENTITY_COUNT,
    FABRICATED_CLAIM_MARKER,
    JUDGE_FABRICATED,
    JUDGE_VERIFIED,
    PerClaimFakeRoleTransport,
    build_benchmark_denominator,
    build_wrong_model_gate_call,
    lookup_benchmark_query,
    resolve_benchmark_required_element_ids,
    run_external_scorer_leg,
    run_four_role_leg,
    run_m4_gate_pass,
)
from scripts.dr_benchmark.pathB_run_gate import (
    GateError,
    assert_post_run,
    preflight,
)

_SALT = b"offline-e2e-salt"
_MIRROR_BASE_URL = "http://10.0.0.5:8000"


# ---------------------------------------------------------------------------------------------
# Codex P2 #2 — NO-NETWORK FAIL-CLOSED at the socket layer (module-scoped, autouse).
# ---------------------------------------------------------------------------------------------
class _BlockedNetworkError(RuntimeError):
    """Raised if any offline-e2e code path tries to open a real socket (zero-network proof)."""


@pytest.fixture(autouse=True)
def _block_all_network(monkeypatch):
    """Block real network for the WHOLE e2e at the socket layer (Codex P2 #2).

    A stray real connection RAISES `_BlockedNetworkError` -> the test FAILS, rather than
    silently networking. Module-scoped via autouse on each test fn (NOT session-global) so it
    cannot surprise the other suites the Gate-A dry run / full pytest invoke. The e2e passing
    under this block is the affirmative zero-network proof (offline=True everywhere means no
    socket is ever opened; the fake transport is in-process only)."""

    def _blocked(*args, **kwargs):
        raise _BlockedNetworkError(
            "offline E2E attempted a real network connection — this run MUST be zero-network "
            "(no real LLM calls, no socket). A stray connection fails the test by design."
        )

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    yield


@pytest.fixture(autouse=True)
def _full_power_env(monkeypatch):
    """The full-power gate env (mirrors test_pathB_run_gate._full_power_env) + the four-role
    activation flag + the self-host endpoint. Set via monkeypatch so it never leaks across
    modules. No secret VALUES are real; offline=True keeps every check off-network."""
    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "deepinfra")
    monkeypatch.setenv("SERPER_API_KEY", "offline-e2e-not-a-real-key")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "offline-e2e-not-a-real-key")
    monkeypatch.setenv("PG_FOUR_ROLE_MODE", "1")
    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
    yield


# ---------------------------------------------------------------------------------------------
# Sanity: the socket block is actually in force inside this module.
# ---------------------------------------------------------------------------------------------
def test_socket_is_blocked_in_this_module():
    """Affirmatively prove the no-network guard is armed: opening a socket RAISES. If this ever
    passes silently, the zero-network proof for the other tests would be vacuous."""
    with pytest.raises(_BlockedNetworkError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(_BlockedNetworkError):
        socket.create_connection(("example.test", 80))


# ---------------------------------------------------------------------------------------------
# Leg A — 4-role seam -> manifest four_role_evaluation + evaluator_agrees + audit file.
# ---------------------------------------------------------------------------------------------
def test_four_role_leg_manifest_evaluator_agrees_and_audit(tmp_path):
    transport = PerClaimFakeRoleTransport()
    leg = run_four_role_leg(transport, run_dir=tmp_path)

    block = leg.manifest["four_role_evaluation"]
    final_verdicts = block["final_verdicts"]
    agrees = block["evaluator_agrees"]

    # NON-EMPTY evaluator_agrees with BOTH polarities present (the §-1.1 safe rule, non-vacuous).
    assert agrees, "evaluator_agrees map must be non-empty"
    assert set(agrees.keys()) == set(final_verdicts.keys())

    # Exactly one VERIFIED claim (-> True) and one FABRICATED claim (-> False) by construction.
    verified_ids = [cid for cid, v in final_verdicts.items() if v == JUDGE_VERIFIED]
    fabricated_ids = [cid for cid, v in final_verdicts.items() if v == JUDGE_FABRICATED]
    assert len(verified_ids) == 1, f"expected one VERIFIED claim, got {final_verdicts}"
    assert len(fabricated_ids) == 1, f"expected one FABRICATED claim, got {final_verdicts}"

    # The §-1.1 safe rule: VERIFIED + kept -> True; FABRICATED -> False. Anchor on the
    # verdict->claim_id correspondence (NOT a hardcoded sha-digest claim_id).
    assert agrees[verified_ids[0]] is True
    assert agrees[fabricated_ids[0]] is False
    # No non-VERIFIED verdict may ever read as True (clinical-safety invariant).
    assert all(
        agrees[cid] is False for cid, v in final_verdicts.items() if v != JUDGE_VERIFIED
    )

    # four_role_claim_audit.json was written + parseable, keys == final_verdicts keys.
    audit_path = tmp_path / "four_role_claim_audit.json"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert set(audit.keys()) == set(final_verdicts.keys())
    for entry in audit.values():
        assert entry["sentence"]
        assert "covered_element_ids" in entry

    # The verifier roles actually ran in-process (NEVER an HTTP POST — see the socket block).
    assert transport.completions > 0

    # Over the REAL 15-entity tirzepatide contract the many uncovered S0 must-cover categories
    # correctly HOLD release (clinical fail-closed) — that is the right behavior; the point of
    # leg A is the seam is builder-valid + the evaluator_agrees map is correct, not a release.
    assert block["release_allowed"] is False
    assert any("d8_s0_must_cover_missing" in r for r in block["held_reasons"])


def test_four_role_leg_fabricated_claim_carries_marker(tmp_path):
    """Guard: the FABRICATED polarity is driven by the canned marker, not luck. The marker
    sentence must be the one whose verdict is FABRICATED (proves the per-claim fake Judge keyed
    on the prompt, not a blanket verdict)."""
    transport = PerClaimFakeRoleTransport()
    leg = run_four_role_leg(transport, run_dir=tmp_path)
    audit = leg.audit
    final_verdicts = leg.manifest["four_role_evaluation"]["final_verdicts"]
    fabricated_ids = [cid for cid, v in final_verdicts.items() if v == JUDGE_FABRICATED]
    assert len(fabricated_ids) == 1
    assert FABRICATED_CLAIM_MARKER in audit[fabricated_ids[0]]["sentence"]


# ---------------------------------------------------------------------------------------------
# Leg B — M4 pathB served==pinned gate: PASS on match, fail-closed on wrong model (P2 #3).
# ---------------------------------------------------------------------------------------------
def test_m4_gate_passes_on_matching_served_metadata():
    result = run_m4_gate_pass(salt=_SALT)
    # The gate returns the established per-role served-identity surrogates on success.
    assert "mirror" in result["served_identity_by_role"]
    assert result["served_identity_by_role"]["mirror"]


def test_m4_gate_fails_closed_on_wrong_model():
    pins, wrong_call = build_wrong_model_gate_call()
    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
    with pytest.raises(GateError, match="served model"):
        assert_post_run(pin, [], _SALT, [wrong_call], {"serper", "semantic_scholar"})


# ---------------------------------------------------------------------------------------------
# Leg C — external scorer over SYNTHETIC isolated fixtures -> scored ledger + systems summary.
# ---------------------------------------------------------------------------------------------
def test_external_scorer_leg_emits_scored_and_summary(tmp_path):
    leg = run_external_scorer_leg(out_dir=tmp_path)

    # reconcile produced a reconciled ledger (auditor == 'reconciled' is what score_one requires).
    assert leg.reconciled_ledger_path.exists()
    reconciled = json.loads(leg.reconciled_ledger_path.read_text(encoding="utf-8"))
    assert reconciled["auditor"] == "reconciled"
    # conservative-MAX was non-vacuously exercised: the claude=VERIFIED / codex=FABRICATED
    # disagreement reconciles to the WORSE verdict (FABRICATED).
    verdicts = {c["claim_id"]: c["verdict"] for c in reconciled["claims"]}
    assert verdicts["syn_claim_disagree"] == "FABRICATED"

    # score_run emitted a scored ledger file.
    assert leg.scored_json_path.exists()
    scored = json.loads(leg.scored_json_path.read_text(encoding="utf-8"))
    assert scored["system"] == "chatgpt"
    assert scored["question_id"] == "Q75"
    assert "passed" in scored
    # The reconciled FABRICATED material claim + demoted coverage drive a non-vacuous result.
    assert scored["passed"] is False
    assert scored["reasons"]

    # aggregate_systems emitted a systems summary file.
    assert leg.systems_summary_path.exists()
    summary_text = leg.systems_summary_path.read_text(encoding="utf-8")
    assert "Path-B DR head-to-head" in summary_text

    # P2 #1 isolation: every written artifact lives under the tmp out-dir (NEVER outputs/dr_benchmark).
    for path in (leg.reconciled_ledger_path, leg.scored_json_path, leg.systems_summary_path):
        assert tmp_path in path.parents or path.parent == tmp_path or tmp_path in path.resolve().parents


# ---------------------------------------------------------------------------------------------
# I-meta-002 PR-11b — all 5 wired benchmark questions route to their OWN native contract.
#
# The robustness gate the operator asked for ("truly, robustly test e2e, confirm it is wired,
# functional and good to launch"): for EACH of the 5 SWEEP_QUERIES-registered benchmark
# questions, prove OFFLINE (1) ROUTING through the registration, (2) the RIGHT DENOMINATOR (exact
# entity ids + count + cross-question distinctness), and (3) the FULL CHAIN flows under the
# no-network socket block. Built per the PR-11b build_spec; Codex-gated separately.
#
# The slug->domain ROUTING is NOT hardcoded in the test — it is read from the SWEEP_QUERIES
# registration via `lookup_benchmark_query`, so a routing typo / missing registration FAILS the
# test (that is the wiring proof). The expected entity ids come from the frozen template, resolved
# by the production loader; only the COUNT per slug is pinned in the source-of-truth map.
# ---------------------------------------------------------------------------------------------
_BENCHMARK_SLUGS = sorted(BENCHMARK_SLUG_EXPECTED_ENTITY_COUNT)


@pytest.mark.parametrize("slug", _BENCHMARK_SLUGS)
def test_all_5_benchmark_questions_route_to_their_own_contract(slug, tmp_path):
    """Per-question robustness proof (parametrized over the 5 wired benchmark slugs).

    (1) ROUTING: the SWEEP_QUERIES registration's domain loads the template that holds THIS
        slug's contract; the native required-element set resolves NON-EMPTY.
    (2) RIGHT DENOMINATOR: the production M3a builder, given THIS question, builds its coverage
        denominator from THIS slug's required_entities — exactly that slug's contract entity ids,
        the right COUNT (75=6/76=5/78=5/72=7/90=6). (Cross-question distinctness is proven
        globally in test_benchmark_denominators_are_distinct.)
    (3) FULL CHAIN OFFLINE: the 4-role seam over THIS contract with the INJECTED fake transport
        produces a manifest four_role_evaluation block + a NON-EMPTY evaluator_agrees map obeying
        the §-1.1 safe rule + a parseable four_role_claim_audit.json; the M4 pathB gate PASSES on a
        matching served-meta fixture and FAILS CLOSED on a wrong-model fixture; and the external
        scorer leg emits a scored ledger + systems summary. All under the module socket block (4).
    """
    expected_count = BENCHMARK_SLUG_EXPECTED_ENTITY_COUNT[slug]

    # (1) ROUTING — through the registration (a typo'd / missing registration fails here).
    entry = lookup_benchmark_query(slug)
    assert entry["slug"] == slug
    routed_ids = resolve_benchmark_required_element_ids(slug)
    assert routed_ids, f"{slug}: native required-element set must be NON-EMPTY (fail-closed)"

    # (2) RIGHT DENOMINATOR — the production builder resolves EXACTLY this slug's contract.
    built_ids = build_benchmark_denominator(slug)
    assert built_ids == routed_ids, (
        f"{slug}: the M3a builder's denominator must equal the contract's required-element ids "
        f"resolved through routing (no drift between routing and the builder)."
    )
    assert len(built_ids) == expected_count, (
        f"{slug}: expected {expected_count} required elements, got {len(built_ids)} "
        f"({built_ids}) — wrong denominator means a cross-wired contract."
    )
    # Ids are unique within the contract (no duplicate inflates the denominator).
    assert len(set(built_ids)) == len(built_ids), f"{slug}: duplicate required-element id"

    # (3) FULL CHAIN OFFLINE — leg A: 4-role seam over THIS question's contract.
    transport = PerClaimFakeRoleTransport()
    leg = run_four_role_leg(transport, run_dir=tmp_path / "run", domain=entry["domain"], slug=slug)
    block = leg.manifest["four_role_evaluation"]
    final_verdicts = block["final_verdicts"]
    agrees = block["evaluator_agrees"]

    # NON-EMPTY evaluator_agrees with keys == final_verdicts (joinable to the audit map).
    assert agrees, f"{slug}: evaluator_agrees map must be non-empty"
    assert set(agrees.keys()) == set(final_verdicts.keys())
    # The shared canned report carries one VERIFIED + one FABRICATED claim regardless of contract
    # (the per-claim pipeline is contract-independent); the §-1.1 safe rule must hold for both.
    verified_ids = [cid for cid, v in final_verdicts.items() if v == JUDGE_VERIFIED]
    fabricated_ids = [cid for cid, v in final_verdicts.items() if v == JUDGE_FABRICATED]
    assert len(verified_ids) == 1, f"{slug}: expected one VERIFIED claim, got {final_verdicts}"
    assert len(fabricated_ids) == 1, f"{slug}: expected one FABRICATED claim, got {final_verdicts}"
    assert agrees[verified_ids[0]] is True
    assert agrees[fabricated_ids[0]] is False
    assert all(
        agrees[cid] is False for cid, v in final_verdicts.items() if v != JUDGE_VERIFIED
    ), f"{slug}: no non-VERIFIED verdict may ever read as evaluator_agrees=True (clinical-safety)"

    # four_role_claim_audit.json written + parseable, keys == final_verdicts keys.
    audit_path = tmp_path / "run" / "four_role_claim_audit.json"
    assert audit_path.exists(), f"{slug}: seam must write four_role_claim_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert set(audit.keys()) == set(final_verdicts.keys())

    # The verifier roles actually ran in-process (NEVER an HTTP POST — see the socket block).
    assert transport.completions > 0

    # Fail-closed is correct over a real contract the shared canned report does not cover: the
    # canned evidence DOIs never match THIS question's entities, so coverage is 0 and the
    # FABRICATED claim latches an unsupported-residual hold. Assert release HELD + a held reason
    # — NOT a question-specific S0 string (72/90 have NO S0 entity, so that reason never appears).
    assert block["release_allowed"] is False, f"{slug}: uncovered contract must HOLD release"
    assert block["held_reasons"], f"{slug}: a held release must record a held reason"

    # Leg B — M4 pathB served==pinned gate (question-agnostic: the verifier pins do not vary by
    # question; run it inside the per-question chain so 'full chain offline' is literally proven
    # for every question). PASS on a matching served-meta fixture; fail-closed on a wrong model.
    gate_result = run_m4_gate_pass(salt=_SALT)
    assert "mirror" in gate_result["served_identity_by_role"]
    pins, wrong_call = build_wrong_model_gate_call()
    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
    with pytest.raises(GateError):
        assert_post_run(pin, [], _SALT, [wrong_call], {"serper", "semantic_scholar"})

    # Leg C — external scorer over the SYNTHETIC isolated fixtures (question-agnostic data; the
    # scorer mechanics are identical per system/question). Emits a scored ledger + systems summary.
    leg_c = run_external_scorer_leg(out_dir=tmp_path / "scorer")
    assert leg_c.scored_json_path.exists()
    assert leg_c.systems_summary_path.exists()


def test_benchmark_denominators_are_distinct():
    """Cross-question DISTINCTNESS (no cross-contamination of contracts between questions).

    Each of the 5 questions must resolve its OWN required-element denominator. The entity ids are
    globally unique across the 5 frozen contracts, so the strongest no-cross-contamination proof
    is that the 5 denominators are PAIRWISE DISJOINT (a stronger claim than mere inequality):
    drb_75's elements share NOTHING with drb_76's, etc. A regression that cross-wired two
    questions to the same contract would surface here as a non-empty intersection.
    """
    denominators = {
        slug: set(build_benchmark_denominator(slug))
        for slug in _BENCHMARK_SLUGS
    }
    # Every denominator is non-empty and the right size (guards against an all-empty 'disjoint').
    for slug, ids in denominators.items():
        assert ids, f"{slug}: denominator must be non-empty"
        assert len(ids) == BENCHMARK_SLUG_EXPECTED_ENTITY_COUNT[slug]

    slugs = _BENCHMARK_SLUGS
    for i in range(len(slugs)):
        for j in range(i + 1, len(slugs)):
            a, b = slugs[i], slugs[j]
            overlap = denominators[a] & denominators[b]
            assert not overlap, (
                f"cross-contamination: {a} and {b} share required-element ids {overlap}; each "
                f"benchmark question MUST route to its OWN native contract."
            )


# ---------------------------------------------------------------------------------------------
# Full chain — all three legs back-to-back, under the socket block (the capstone proof).
# ---------------------------------------------------------------------------------------------
def test_full_offline_chain_runs_under_socket_block(tmp_path):
    """Run leg A -> leg B -> leg C back-to-back in one test, all under the no-network socket
    block. If any leg opened a real socket, _BlockedNetworkError would fail this test. Passing
    here is the affirmative zero-network / zero-spend capstone proof."""
    # Leg A
    transport = PerClaimFakeRoleTransport()
    leg_a = run_four_role_leg(transport, run_dir=tmp_path / "run")
    assert leg_a.manifest["four_role_evaluation"]["evaluator_agrees"]
    assert (tmp_path / "run" / "four_role_claim_audit.json").exists()

    # Leg B (PASS + fail-closed)
    gate_result = run_m4_gate_pass(salt=_SALT)
    assert "mirror" in gate_result["served_identity_by_role"]
    pins, wrong_call = build_wrong_model_gate_call()
    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
    with pytest.raises(GateError):
        assert_post_run(pin, [], _SALT, [wrong_call], {"serper", "semantic_scholar"})

    # Leg C
    leg_c = run_external_scorer_leg(out_dir=tmp_path / "scorer")
    assert leg_c.scored_json_path.exists()
    assert leg_c.systems_summary_path.exists()

    # Zero network proved: the verifier roles ran in-process only.
    assert transport.completions > 0
