HARD ITERATION CAP: 5 per document. This is iter 1 of the offline-E2E DIFF gate.
- Front-load ALL real findings; reserve P0/P1 for real execution/safety risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit this exact YAML block as your final output)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

# Codex DIFF-gate — I-meta-002 PR-9 offline END-TO-END (no-spend capstone)

You APPROVED this e2e design (.codex/I-meta-002-pr9-e2e/codex_design_verdict_iter2.txt: zero P0/P1,
3 P2s). This diff implements it: ONE offline harness proving the whole toolchain runs end-to-end so
canary day adds ONLY real model calls. NO SPEND / NO NETWORK (socket blocked in the test).

## HARD CONSTRAINTS
- NO MONEY / NO NETWORK: zero real LLM calls (generator + 3 verifier roles faked/canned); the test
  BLOCKS sockets so any stray real connection FAILS. Confirm there is no hidden live call.
- NATIVE-ONLY: uses the EXISTING annotated clinical_tirzepatide_t2dm contract (NON-benchmark). The
  harness must NEVER read outputs/dr_benchmark gold rubric/competitor answers. Fixture rubric+ledger
  are SYNTHETIC, labeled, and isolated under tests/fixtures/offline_e2e/.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (NOT promoted). Reuses committed M3a/M3b/M4/M5
  + the external scorer scripts.

## Your 3 design P2s — confirm each is honored in the diff
1. Fixture rubric/ledger clearly labeled synthetic/non-benchmark + isolated from outputs/dr_benchmark.
2. No-network assertion FAIL-CLOSED by blocking socket/connect paths (not merely "fake transport used").
3. BOTH a matching served-metadata fixture (pathB PASS) AND a wrong-model fixture (pathB fail-closed).

## What to verify
- The chain genuinely connects: 4-role seam (fake transport + M3a builder over tirzepatide) ->
  manifest four_role_evaluation with final_verdicts + M5 evaluator_agrees map + four_role_claim_audit.json
  -> M4 pathB served==pinned (PASS on match, fail-closed on wrong-model) -> synthetic fixture
  reconciled ledger + rubric -> score_run -> aggregate_systems.
- Non-vacuous assertions (not a pass that proves nothing): non-empty evaluator_agrees obeying the safe
  rule (FABRICATED canned verdict -> False; VERIFIED+kept -> True); audit json keys == final_verdicts;
  pathB raises on wrong-model; score_run emits a scored ledger; aggregate emits a systems summary;
  socket blocked throughout.
- No frozen/lock drift; lock NOT promoted; no read of outputs/dr_benchmark.

## SMOKE (Claude main-thread; build agent was session-limited mid-report, Claude re-verified)
- offline_e2e test: 7 passed (socket-block + 4-role + FABRICATED-marker + pathB pass/fail-closed +
  scorer + full-chain-under-socket-block).
- pytest tests/dr_benchmark tests/roles tests/architecture -q: 401 passed (was 394 + 7 new). Exit 0.
- verify_lock --consistency: exit 0 (lock NOT promoted). gate_a_dry_run: OVERALL PASS, exit 0.
- tests/polaris_graph not re-run here (e2e adds only scripts/dr_benchmark/offline_e2e.py + test +
  fixtures; the 49 tests/polaris_graph failures are PRE-EXISTING per the M3b stash-comparison).

## DIFF (follows)

POLARIS I-meta-002 PR-9 offline-E2E — SMOKE (Claude main-thread, build agent was session-limited mid-report; Claude re-ran + verified by hand)

Date (UTC approx): 2026-05-29
HEAD: c4122b63 (item7) + uncommitted offline-e2e working tree
Execution: serialized, foreground (§8.4). NO network (socket blocked in the e2e test), NO spend.

OVERALL: PASS.

STEP 0 — offline_e2e test alone (verbose): 7 passed in 1.00s. Named tests:
  test_socket_is_blocked_in_this_module PASSED
  test_four_role_leg_manifest_evaluator_agrees_and_audit PASSED
  test_four_role_leg_fabricated_claim_carries_marker PASSED
  test_m4_gate_passes_on_matching_served_metadata PASSED
  test_m4_gate_fails_closed_on_wrong_model PASSED
  test_external_scorer_leg_emits_scored_and_summary PASSED
  test_full_offline_chain_runs_under_socket_block PASSED
  -> proves: 4-role manifest + evaluator_agrees map + audit; FABRICATED-carries-marker (safe rule);
     pathB PASS on matching served-metadata AND fail-closed on wrong-model; external scorer emits
     scored ledger + systems summary; the FULL chain runs with sockets BLOCKED (no-network fail-closed).

STEP 1 — pytest tests/dr_benchmark tests/roles tests/architecture -q: 401 passed (was 394 + 7 new). Exit 0.
STEP 2 — verify_lock --consistency: exit 0, "Consistency: OK" (lock NOT promoted).
STEP 3 — gate_a_dry_run: OVERALL PASS, exit 0. JSON: outputs/gate_a/dry_run_report.json.

NO NETWORK / NO SPEND: the e2e test blocks socket.socket/create_connection for the whole run; a stray
real connection FAILS the test (test_socket_is_blocked_in_this_module + the full-chain test pass under
the block). Verifier roles faked via canned RoleTransport; no live generator; nothing deployed.
Fixtures live under tests/fixtures/offline_e2e/ (synthetic, isolated from outputs/dr_benchmark).

===== DIFF =====
diff --git a/scripts/dr_benchmark/offline_e2e.py b/scripts/dr_benchmark/offline_e2e.py
new file mode 100644
index 00000000..70d58cf9
--- /dev/null
+++ b/scripts/dr_benchmark/offline_e2e.py
@@ -0,0 +1,424 @@
+"""Offline no-spend END-TO-END harness (I-meta-002 PR-9 / readiness item 9).
+
+ONE offline proof that the WHOLE DR toolchain runs end to end so canary day adds ONLY real
+model calls. NO MONEY, NO NETWORK anywhere: zero real LLM calls (the generator AND the three
+verifier roles are faked / canned), zero socket. Codex DESIGN APPROVE iter 2
+(.codex/I-meta-002-pr9-e2e/design_brief.md; zero P0/P1; the 3 P2s are folded in here +
+enforced by the driving test).
+
+The chain this harness exercises (all offline):
+
+  A. 4-ROLE SEAM (M3a builder + M3b seam + M5 evaluator_agrees) over the REAL annotated
+     `clinical_tirzepatide_t2dm` contract, fed CANNED kept verified sentences + a canned
+     evidence pool through an INJECTED FAKE `RoleTransport` (no httpx, no socket). Produces the
+     manifest `four_role_evaluation` block (final_verdicts + held/coverage) PLUS the M5
+     `evaluator_agrees` map (built by `sweep_integration.build_evaluator_agrees_map`, the SINGLE
+     source of the §-1.1 safe rule — never reimplemented here) and the
+     `four_role_claim_audit.json` the seam writes next to the run.
+
+  B. M4 PATH-B served==pinned gate over FIXTURE self-host served-metadata: preflight (offline)
+     + assert_post_run on a MATCHING `{model, endpoint}` -> PASS; and on a WRONG-MODEL fixture
+     -> fail-closed (`GateError`). NO OpenRouter resolution (self-host serving_route branch),
+     NO socket (offline=True everywhere).
+
+  C. EXTERNAL SCORER on SYNTHETIC, ISOLATED fixtures (Codex P2 #1): two single-auditor ledgers
+     (claude + codex) -> `reconcile` (conservative-MAX) -> a reconciled ledger ->
+     `score_run.score_one` -> a per-claim scored JSON -> `aggregate_systems` -> a systems
+     summary. The fixtures live under `tests/fixtures/offline_e2e/` and are clearly labeled
+     synthetic; this leg NEVER reads or writes under `outputs/dr_benchmark/`.
+
+IMPORT-SAFE: importing this module performs NO I/O, opens NO socket, and starts NO subprocess.
+Every function below is pure orchestration over caller-supplied paths / an injected transport;
+all real work happens only when a function is called (the driving test calls them with a
+`tmp_path` and a fake transport). There is no `__main__` runtime path that spends or networks.
+
+CONTAMINATION-CRITICAL (§-1.1, operator-locked): leg A uses ONLY the native scope contract;
+leg C uses ONLY the synthetic isolated fixtures. NOTHING here reads `outputs/dr_benchmark/`.
+"""
+
+from __future__ import annotations
+
+import json
+from dataclasses import dataclass
+from pathlib import Path
+
+from scripts.dr_benchmark.ledger_schema import dump_ledger, load_ledger
+from scripts.dr_benchmark.pathB_run_gate import (
+    LLMCall,
+    RolePin,
+    assert_post_run,
+    preflight,
+)
+from scripts.dr_benchmark.reconcile import reconcile
+from scripts.dr_benchmark.run_gate_b import make_gate_b_input_builder
+from scripts.dr_benchmark.score_run import score_one
+from src.polaris_graph.roles.mirror_contract import CitationSpan
+from src.polaris_graph.roles.role_transport import (
+    RoleRequest,
+    RoleResponse,
+)
+from src.polaris_graph.roles.sweep_integration import (
+    FOUR_ROLE_CLAIM_AUDIT_FILENAME,
+    FourRoleEvaluationResult,
+    build_evaluator_agrees_map,
+    run_four_role_seam,
+)
+
+# Caller-supplied audit timestamp (LAW VI: no datetime.now() in the harness).
+DEFAULT_TIMESTAMP = "2026-05-29T00:00:00Z"
+
+# The annotated NON-benchmark contract this E2E runs the seam over (operator-locked native
+# config; NOT a benchmark gold rubric).
+CLINICAL_TEMPLATE_PATH = "config/scope_templates/clinical.yaml"
+TIRZEPATIDE_SLUG = "clinical_tirzepatide_t2dm"
+
+# Canonical 5-enum verdict tokens the fake Judge may emit (mirror judge_contract.JUDGE_CHOICES;
+# the harness only needs the two polarities the §-1.1 evaluator_agrees rule distinguishes).
+JUDGE_VERIFIED = "VERIFIED"
+JUDGE_FABRICATED = "FABRICATED"
+
+# A marker substring the canned report embeds in a claim's text so the per-claim fake Judge can
+# return FABRICATED for THAT claim (proving evaluator_agrees -> False) while every other claim
+# gets VERIFIED (proving evaluator_agrees -> True). Deterministic, no network.
+FABRICATED_CLAIM_MARKER = "[[offline-e2e-fabricated]]"
+
+# I-meta-002 PR-9/M4: the locked self-hosted verifier roles + a synthetic self-host endpoint.
+# These are FIXTURE served-metadata values (no real box) — the gate leg proves served==pinned
+# logic offline, exactly as tests/dr_benchmark/test_pathB_run_gate.py does.
+MIRROR_SLUG = "cohere/command-a-plus"
+SELF_HOST_BASE_URL = "http://10.0.0.5:8000"
+
+
+# ---------------------------------------------------------------------------------------------
+# Leg A — the canned FAKE RoleTransport + in-memory report objects (NO network, NO spend).
+# ---------------------------------------------------------------------------------------------
+class PerClaimFakeRoleTransport:
+    """Canned in-process `RoleTransport` — NO network, NO spend (reuses the proven
+    tests/dr_benchmark/test_gate_b_seam.py pattern, extended to PER-CLAIM judge verdicts).
+
+    Mirror pass-1 cites the FIRST supplied evidence doc_id (so the grounding binding holds for
+    whatever evidence_id the builder minted); pass-2 echoes the embedded content_hash. Sentinel
+    returns GROUNDED (`<score>no</score>`). Judge returns FABRICATED for any claim whose prompt
+    carries `FABRICATED_CLAIM_MARKER`, else VERIFIED — so the SAME run produces both an
+    evaluator_agrees=True (VERIFIED + kept) and an evaluator_agrees=False (FABRICATED) entry,
+    which is the §-1.1 safe-rule property the E2E asserts. `completions` counts in-process
+    completions (NEVER an HTTP POST) so the test can assert the verifier roles actually ran.
+    """
+
+    def __init__(self) -> None:
+        self.completions = 0  # canned in-process completions (NEVER an HTTP POST).
+
+    def complete(self, request: RoleRequest) -> RoleResponse:
+        self.completions += 1
+        if request.role == "mirror":
+            if "pass2_input" in (request.params or {}):
+                content_hash = request.params["pass2_input"]["content_hash"]
+                payload = {"content_hash": content_hash, "classification": "supported"}
+                return RoleResponse(raw_text=json.dumps(payload), served_model=request.model_slug)
+            documents = (request.params or {}).get("documents") or []
+            doc_id = documents[0]["doc_id"] if documents else "doc0"
+            return RoleResponse(
+                raw_text="grounded answer",
+                served_model=request.model_slug,
+                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(doc_id,))],
+            )
+        if request.role == "sentinel":
+            # "no" => no risk => GROUNDED (lethal-polarity: yes=risk=ungrounded).
+            return RoleResponse(raw_text="<score>no</score>", served_model=request.model_slug)
+        if request.role == "judge":
+            verdict = (
+                JUDGE_FABRICATED
+                if FABRICATED_CLAIM_MARKER in (request.prompt or "")
+                else JUDGE_VERIFIED
+            )
+            return RoleResponse(raw_text=verdict, served_model=request.model_slug)
+        raise AssertionError(f"unexpected role {request.role!r}")
+
+
+# --- minimal in-memory report objects (the M3a builder reads only these attributes) ----------
+@dataclass
+class _FakeToken:
+    evidence_id: str
+
+
+@dataclass
+class _FakeVerification:
+    sentence: str
+    tokens: list
+    is_verified: bool = True
+
+
+class _FakeSection:
+    def __init__(self, title: str, verifications: list) -> None:
+        self.title = title
+        self.kept_sentences_pre_resolve = verifications
+
+
+class _FakeMulti:
+    def __init__(self, sections: list) -> None:
+        self.sections = sections
+
+
+def build_canned_report() -> _FakeMulti:
+    """A finished report (two KEPT verified sentences) that cites the canned evidence pool.
+
+    Sentence 1 cites SURPASS-2's REAL DOI (an annotated S1 trial entity in the tirzepatide
+    contract) -> covers that element on a VERIFIED Judge verdict -> evaluator_agrees True.
+    Sentence 2 carries `FABRICATED_CLAIM_MARKER` -> the fake Judge returns FABRICATED -> final
+    verdict FABRICATED -> evaluator_agrees False. Both are KEPT (is_verified=True), so the
+    evaluator_agrees boolean is driven purely by the verdict, exactly as the sweep path does.
+    """
+    return _FakeMulti(
+        sections=[
+            _FakeSection(
+                "Efficacy",
+                [
+                    _FakeVerification(
+                        "SURPASS-2 randomized 1879 patients; tirzepatide lowered HbA1c.",
+                        [_FakeToken("ev_000")],
+                    )
+                ],
+            ),
+            _FakeSection(
+                "Safety",
+                [
+                    _FakeVerification(
+                        f"{FABRICATED_CLAIM_MARKER} An unsupported safety claim with no "
+                        "grounded evidence backing.",
+                        [_FakeToken("ev_001")],
+                    )
+                ],
+            ),
+        ]
+    )
+
+
+def build_canned_ev_pool() -> dict:
+    """Raw evidence-pool rows (the run's ev_pool shape) the canned report cites.
+
+    `ev_000` carries SURPASS-2's real DOI via a journal URL so the M3a coverage matcher's EXACT
+    canonical-identifier equality credits the trial element. `ev_001` is a generic source for
+    the FABRICATED sentence (it never earns coverage because its final verdict is FABRICATED).
+    """
+    return {
+        "ev_000": {
+            "evidence_id": "ev_000",
+            "direct_quote": "SURPASS-2 randomized 1879 patients; tirzepatide lowered HbA1c.",
+            "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
+        },
+        "ev_001": {
+            "evidence_id": "ev_001",
+            "direct_quote": "A generic source paragraph cited by the unsupported safety claim.",
+            "source_url": "https://example.test/generic-source",
+        },
+    }
+
+
+@dataclass
+class FourRoleLegResult:
+    """Leg-A output: the assembled manifest plus the seam result + the parsed audit map."""
+
+    manifest: dict
+    result: FourRoleEvaluationResult
+    audit: dict
+
+
+def run_four_role_leg(
+    transport: PerClaimFakeRoleTransport,
+    *,
+    run_dir: Path,
+    timestamp: str = DEFAULT_TIMESTAMP,
+    template_path: str = CLINICAL_TEMPLATE_PATH,
+    slug: str = TIRZEPATIDE_SLUG,
+) -> FourRoleLegResult:
+    """Leg A: run the REAL M3a/M3b 4-role seam offline over the native tirzepatide contract.
+
+    Reuses the production builder closure (`make_gate_b_input_builder`) + `run_four_role_seam`
+    with the INJECTED fake transport and the canned report/ev_pool. Then assembles the manifest
+    `four_role_evaluation` block EXACTLY as `scripts/run_honest_sweep_r3.py` does (including the
+    M5 `evaluator_agrees` map via `build_evaluator_agrees_map`), and reads back the
+    `four_role_claim_audit.json` the seam wrote next to the run. NO network, NO spend.
+    """
+    import yaml
+
+    template = yaml.safe_load(Path(template_path).read_text(encoding="utf-8"))
+    builder = make_gate_b_input_builder()
+    result = run_four_role_seam(
+        transport,
+        run_dir=run_dir,
+        timestamp=timestamp,
+        four_role_input_builder=builder,
+        multi=build_canned_report(),
+        template=template,
+        slug=slug,
+        domain="clinical",
+        ev_pool=build_canned_ev_pool(),
+    )
+
+    # Assemble the manifest block exactly as the sweep does (run_honest_sweep_r3.py:3206-3235).
+    # The M5 evaluator_agrees map uses build_evaluator_agrees_map — the SINGLE source of the
+    # §-1.1 safe rule (VERIFIED + kept -> True; every other verdict -> False). kept_claim_ids is
+    # None here for the same reason as the sweep: every claim_id in final_verdicts was built from
+    # a KEPT (is_verified) sentence by the M3a builder.
+    manifest: dict = {}
+    manifest["four_role_evaluation"] = {
+        "release_allowed": result.release_allowed,
+        "held_reasons": result.held_reasons,
+        "coverage_fraction": round(result.coverage_fraction, 3),
+        "fabricated_occurrence_latched": result.fabricated_occurrence_latched,
+        "final_verdicts": dict(result.final_verdicts),
+    }
+    manifest["four_role_evaluation"]["evaluator_agrees"] = build_evaluator_agrees_map(
+        result.final_verdicts
+    )
+
+    audit_path = run_dir / FOUR_ROLE_CLAIM_AUDIT_FILENAME
+    audit = json.loads(audit_path.read_text(encoding="utf-8"))
+    return FourRoleLegResult(manifest=manifest, result=result, audit=audit)
+
+
+# ---------------------------------------------------------------------------------------------
+# Leg B — M4 Path-B served==pinned gate over FIXTURE self-host served-metadata (NO network).
+# ---------------------------------------------------------------------------------------------
+def _self_host_pin(role: str, slug: str) -> RolePin:
+    """A self-host RolePin (surrogate_fields unused by the self-host branch but the preflight
+    no-empty-surrogate guard still requires them non-empty — matches pathB_runner._role_pins())."""
+    return RolePin(role, slug, "", ("provider_name", "model"))
+
+
+def run_m4_gate_pass(
+    *,
+    salt: bytes,
+    role: str = "mirror",
+    slug: str = MIRROR_SLUG,
+    base_url: str = SELF_HOST_BASE_URL,
+) -> dict:
+    """Leg B (PASS): preflight (offline) + assert_post_run on a MATCHING self-host served-meta.
+
+    NO network: offline=True takes the self-host serving_route branch (no OpenRouter
+    resolution); the served `{model, endpoint}` matches the pinned slug + base_url, so the gate
+    returns the established per-role served-identity surrogates. `enforce_architecture_coverage`
+    is False (offline test mode uses a single self-host pin, not the full 4-role architecture).
+    The caller must set `PG_<ROLE>_BASE_URL` in the env (the test does so via monkeypatch).
+    """
+    pins = [_self_host_pin(role, slug)]
+    pin = preflight([], pins, salt, offline=True, enforce_architecture_coverage=False)
+    # Served endpoint reported WITH a trailing slash — must still match (trailing-slash tolerant).
+    calls = [
+        LLMCall(
+            call_id="offline-e2e-mirror",
+            role=role,
+            prompt_messages_present=True,
+            request_hash="offline-e2e-request-hash",
+            response_metadata={"model": slug, "endpoint": base_url + "/"},
+        )
+    ]
+    return assert_post_run(pin, [], salt, calls, {"serper", "semantic_scholar"})
+
+
+def build_wrong_model_gate_call(
+    *,
+    role: str = "mirror",
+    wrong_slug: str = "cohere/command-r-plus",
+    base_url: str = SELF_HOST_BASE_URL,
+) -> tuple[list, LLMCall]:
+    """Leg B (FAIL-CLOSED): build the self-host pin + a WRONG-MODEL served-meta LLMCall.
+
+    Returns `(pins, wrong_call)`; the test runs preflight + assert_post_run with these and
+    asserts a `GateError` (a wrong verifier model is a silent capability downgrade — must abort).
+    """
+    pins = [_self_host_pin(role, MIRROR_SLUG)]
+    wrong_call = LLMCall(
+        call_id="offline-e2e-mirror-wrong",
+        role=role,
+        prompt_messages_present=True,
+        request_hash="offline-e2e-request-hash",
+        response_metadata={"model": wrong_slug, "endpoint": base_url},
+    )
+    return pins, wrong_call
+
+
+# ---------------------------------------------------------------------------------------------
+# Leg C — external scorer over SYNTHETIC, ISOLATED fixtures (NEVER outputs/dr_benchmark).
+# ---------------------------------------------------------------------------------------------
+# Repo-relative location of the synthetic, isolated scorer fixtures (Codex P2 #1).
+OFFLINE_E2E_FIXTURE_DIR = Path("tests/fixtures/offline_e2e")
+SYNTHETIC_RUBRIC_NAME = "synthetic_rubric.json"
+SYNTHETIC_LEDGER_CLAUDE_NAME = "synthetic_ledger_claude.json"
+SYNTHETIC_LEDGER_CODEX_NAME = "synthetic_ledger_codex.json"
+
+# The synthetic fixtures are tagged (system, question). Kept here so the harness and the test
+# read the same identity (and never a real benchmark question's gold data).
+SYNTHETIC_SYSTEM = "chatgpt"
+SYNTHETIC_QUESTION_ID = "Q75"
+
+
+@dataclass
+class ScorerLegResult:
+    """Leg-C output: the paths written under the caller-supplied tmp out-dir + the scored dict."""
+
+    reconciled_ledger_path: Path
+    scored_json_path: Path
+    systems_summary_path: Path
+    scored: dict
+
+
+def run_external_scorer_leg(
+    *,
+    out_dir: Path,
+    fixture_dir: Path = OFFLINE_E2E_FIXTURE_DIR,
+) -> ScorerLegResult:
+    """Leg C: reconcile two synthetic single-auditor ledgers -> score_one -> aggregate_systems.
+
+    Reads ONLY the synthetic, isolated fixtures under `fixture_dir` (NEVER
+    `outputs/dr_benchmark/`). Writes the reconciled ledger, the scored JSON, and the systems
+    summary ONLY under the caller-supplied `out_dir` (NEVER `outputs/dr_benchmark/`). Pure
+    offline logic + JSON/markdown writes; no network, no spend.
+
+    `score_one` requires `auditor == "reconciled"`, which only `reconcile()` produces — so this
+    leg exercises the real dual-§-1.1 conservative-MAX reconciliation before scoring.
+    """
+    # aggregate_systems is imported lazily so this module's top-level import stays minimal /
+    # side-effect-free (it is only needed when this leg actually runs).
+    from scripts.dr_benchmark.aggregate_systems import render_final_report
+
+    out_dir.mkdir(parents=True, exist_ok=True)
+    rubric_path = fixture_dir / SYNTHETIC_RUBRIC_NAME
+    claude = load_ledger(fixture_dir / SYNTHETIC_LEDGER_CLAUDE_NAME)
+    codex = load_ledger(fixture_dir / SYNTHETIC_LEDGER_CODEX_NAME)
+
+    reconciled = reconcile(claude, codex)
+    reconciled_path = out_dir / "reconciled_ledger.json"
+    dump_ledger(reconciled, reconciled_path)
+
+    scored = score_one(
+        system=SYNTHETIC_SYSTEM,
+        question_id=SYNTHETIC_QUESTION_ID,
+        rubric_path=rubric_path,
+        ledger_path=reconciled_path,
+    )
+    # score_run.main writes <system>_<question>.json into a scored dir; mirror that name so
+    # aggregate_systems._collect picks it up.
+    scored_dir = out_dir / "scored"
+    scored_dir.mkdir(parents=True, exist_ok=True)
+    scored_json_path = scored_dir / f"{SYNTHETIC_SYSTEM}_{SYNTHETIC_QUESTION_ID}.json"
+    scored_json_path.write_text(
+        json.dumps(scored, indent=2, sort_keys=True, default=str) + "\n",
+        encoding="utf-8",
+    )
+
+    systems_summary_path = out_dir / "systems_summary.md"
+    # freeze_pin points at a non-existent path under out_dir so the aggregator renders the
+    # "IDENTITY UNVERIFIED" branch (this is a SYNTHETIC dry-run summary, not a real report) and
+    # never reads anything under outputs/dr_benchmark.
+    render_final_report(
+        scored_dir=scored_dir,
+        freeze_pin=out_dir / "synthetic_freeze_pin_absent.txt",
+        out_path=systems_summary_path,
+    )
+    return ScorerLegResult(
+        reconciled_ledger_path=reconciled_path,
+        scored_json_path=scored_json_path,
+        systems_summary_path=systems_summary_path,
+        scored=scored,
+    )
diff --git a/tests/dr_benchmark/test_offline_e2e.py b/tests/dr_benchmark/test_offline_e2e.py
new file mode 100644
index 00000000..50057bed
--- /dev/null
+++ b/tests/dr_benchmark/test_offline_e2e.py
@@ -0,0 +1,252 @@
+"""Offline no-spend END-TO-END test (I-meta-002 PR-9 / readiness item 9). NO network, NO spend.
+
+DRIVES `scripts.dr_benchmark.offline_e2e` through the WHOLE DR toolchain offline and asserts
+the chain non-vacuously, so canary day adds ONLY real model calls. Codex DESIGN APPROVE iter 2
+(.codex/I-meta-002-pr9-e2e/design_brief.md; zero P0/P1; 3 P2s folded in):
+
+  * P2 #1 — the scorer-leg rubric/ledger fixtures are clearly labeled synthetic and live
+    ISOLATED under tests/fixtures/offline_e2e/; the harness writes scored output ONLY to a
+    tmp dir, NEVER under outputs/dr_benchmark/.
+  * P2 #2 — NO-NETWORK FAIL-CLOSED: this module BLOCKS real network at the socket layer (a
+    module-scoped autouse fixture monkeypatches socket.socket / socket.create_connection /
+    socket.getaddrinfo to RAISE). A stray real connection therefore FAILS the test rather
+    than silently networking; the whole e2e passing under the block IS the zero-network proof.
+    The block is module-scoped (not session-global) so it can never surprise the other suites
+    the Gate-A dry run / full pytest invoke.
+  * P2 #3 — the M4 gate leg includes BOTH a MATCHING served-metadata fixture (PASS) and a
+    WRONG-MODEL fixture (fail-closed / raises GateError).
+
+Non-vacuous assertions (per the build spec):
+  - manifest carries `four_role_evaluation` with a NON-EMPTY `evaluator_agrees` map obeying the
+    §-1.1 safe rule (canned FABRICATED -> False; canned VERIFIED + kept -> True);
+  - `four_role_claim_audit.json` is written + parseable, keys == final_verdicts keys;
+  - the M4 pathB gate returns the per-role served identity on a MATCHING fixture and RAISES on
+    the wrong-model fixture;
+  - score_run emits a scored ledger file; aggregate_systems emits a systems summary file;
+  - socket is blocked for the whole run and the e2e still passes (zero network/spend).
+"""
+
+from __future__ import annotations
+
+import json
+import socket
+
+import pytest
+
+from scripts.dr_benchmark.offline_e2e import (
+    FABRICATED_CLAIM_MARKER,
+    JUDGE_FABRICATED,
+    JUDGE_VERIFIED,
+    PerClaimFakeRoleTransport,
+    build_wrong_model_gate_call,
+    run_external_scorer_leg,
+    run_four_role_leg,
+    run_m4_gate_pass,
+)
+from scripts.dr_benchmark.pathB_run_gate import (
+    GateError,
+    assert_post_run,
+    preflight,
+)
+
+_SALT = b"offline-e2e-salt"
+_MIRROR_BASE_URL = "http://10.0.0.5:8000"
+
+
+# ---------------------------------------------------------------------------------------------
+# Codex P2 #2 — NO-NETWORK FAIL-CLOSED at the socket layer (module-scoped, autouse).
+# ---------------------------------------------------------------------------------------------
+class _BlockedNetworkError(RuntimeError):
+    """Raised if any offline-e2e code path tries to open a real socket (zero-network proof)."""
+
+
+@pytest.fixture(autouse=True)
+def _block_all_network(monkeypatch):
+    """Block real network for the WHOLE e2e at the socket layer (Codex P2 #2).
+
+    A stray real connection RAISES `_BlockedNetworkError` -> the test FAILS, rather than
+    silently networking. Module-scoped via autouse on each test fn (NOT session-global) so it
+    cannot surprise the other suites the Gate-A dry run / full pytest invoke. The e2e passing
+    under this block is the affirmative zero-network proof (offline=True everywhere means no
+    socket is ever opened; the fake transport is in-process only)."""
+
+    def _blocked(*args, **kwargs):
+        raise _BlockedNetworkError(
+            "offline E2E attempted a real network connection — this run MUST be zero-network "
+            "(no real LLM calls, no socket). A stray connection fails the test by design."
+        )
+
+    monkeypatch.setattr(socket, "socket", _blocked)
+    monkeypatch.setattr(socket, "create_connection", _blocked)
+    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
+    yield
+
+
+@pytest.fixture(autouse=True)
+def _full_power_env(monkeypatch):
+    """The full-power gate env (mirrors test_pathB_run_gate._full_power_env) + the four-role
+    activation flag + the self-host endpoint. Set via monkeypatch so it never leaks across
+    modules. No secret VALUES are real; offline=True keeps every check off-network."""
+    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
+    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "deepinfra")
+    monkeypatch.setenv("SERPER_API_KEY", "offline-e2e-not-a-real-key")
+    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "offline-e2e-not-a-real-key")
+    monkeypatch.setenv("PG_FOUR_ROLE_MODE", "1")
+    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
+    yield
+
+
+# ---------------------------------------------------------------------------------------------
+# Sanity: the socket block is actually in force inside this module.
+# ---------------------------------------------------------------------------------------------
+def test_socket_is_blocked_in_this_module():
+    """Affirmatively prove the no-network guard is armed: opening a socket RAISES. If this ever
+    passes silently, the zero-network proof for the other tests would be vacuous."""
+    with pytest.raises(_BlockedNetworkError):
+        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
+    with pytest.raises(_BlockedNetworkError):
+        socket.create_connection(("example.test", 80))
+
+
+# ---------------------------------------------------------------------------------------------
+# Leg A — 4-role seam -> manifest four_role_evaluation + evaluator_agrees + audit file.
+# ---------------------------------------------------------------------------------------------
+def test_four_role_leg_manifest_evaluator_agrees_and_audit(tmp_path):
+    transport = PerClaimFakeRoleTransport()
+    leg = run_four_role_leg(transport, run_dir=tmp_path)
+
+    block = leg.manifest["four_role_evaluation"]
+    final_verdicts = block["final_verdicts"]
+    agrees = block["evaluator_agrees"]
+
+    # NON-EMPTY evaluator_agrees with BOTH polarities present (the §-1.1 safe rule, non-vacuous).
+    assert agrees, "evaluator_agrees map must be non-empty"
+    assert set(agrees.keys()) == set(final_verdicts.keys())
+
+    # Exactly one VERIFIED claim (-> True) and one FABRICATED claim (-> False) by construction.
+    verified_ids = [cid for cid, v in final_verdicts.items() if v == JUDGE_VERIFIED]
+    fabricated_ids = [cid for cid, v in final_verdicts.items() if v == JUDGE_FABRICATED]
+    assert len(verified_ids) == 1, f"expected one VERIFIED claim, got {final_verdicts}"
+    assert len(fabricated_ids) == 1, f"expected one FABRICATED claim, got {final_verdicts}"
+
+    # The §-1.1 safe rule: VERIFIED + kept -> True; FABRICATED -> False. Anchor on the
+    # verdict->claim_id correspondence (NOT a hardcoded sha-digest claim_id).
+    assert agrees[verified_ids[0]] is True
+    assert agrees[fabricated_ids[0]] is False
+    # No non-VERIFIED verdict may ever read as True (clinical-safety invariant).
+    assert all(
+        agrees[cid] is False for cid, v in final_verdicts.items() if v != JUDGE_VERIFIED
+    )
+
+    # four_role_claim_audit.json was written + parseable, keys == final_verdicts keys.
+    audit_path = tmp_path / "four_role_claim_audit.json"
+    assert audit_path.exists()
+    audit = json.loads(audit_path.read_text(encoding="utf-8"))
+    assert set(audit.keys()) == set(final_verdicts.keys())
+    for entry in audit.values():
+        assert entry["sentence"]
+        assert "covered_element_ids" in entry
+
+    # The verifier roles actually ran in-process (NEVER an HTTP POST — see the socket block).
+    assert transport.completions > 0
+
+    # Over the REAL 15-entity tirzepatide contract the many uncovered S0 must-cover categories
+    # correctly HOLD release (clinical fail-closed) — that is the right behavior; the point of
+    # leg A is the seam is builder-valid + the evaluator_agrees map is correct, not a release.
+    assert block["release_allowed"] is False
+    assert any("d8_s0_must_cover_missing" in r for r in block["held_reasons"])
+
+
+def test_four_role_leg_fabricated_claim_carries_marker(tmp_path):
+    """Guard: the FABRICATED polarity is driven by the canned marker, not luck. The marker
+    sentence must be the one whose verdict is FABRICATED (proves the per-claim fake Judge keyed
+    on the prompt, not a blanket verdict)."""
+    transport = PerClaimFakeRoleTransport()
+    leg = run_four_role_leg(transport, run_dir=tmp_path)
+    audit = leg.audit
+    final_verdicts = leg.manifest["four_role_evaluation"]["final_verdicts"]
+    fabricated_ids = [cid for cid, v in final_verdicts.items() if v == JUDGE_FABRICATED]
+    assert len(fabricated_ids) == 1
+    assert FABRICATED_CLAIM_MARKER in audit[fabricated_ids[0]]["sentence"]
+
+
+# ---------------------------------------------------------------------------------------------
+# Leg B — M4 pathB served==pinned gate: PASS on match, fail-closed on wrong model (P2 #3).
+# ---------------------------------------------------------------------------------------------
+def test_m4_gate_passes_on_matching_served_metadata():
+    result = run_m4_gate_pass(salt=_SALT)
+    # The gate returns the established per-role served-identity surrogates on success.
+    assert "mirror" in result["served_identity_by_role"]
+    assert result["served_identity_by_role"]["mirror"]
+
+
+def test_m4_gate_fails_closed_on_wrong_model():
+    pins, wrong_call = build_wrong_model_gate_call()
+    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
+    with pytest.raises(GateError, match="served model"):
+        assert_post_run(pin, [], _SALT, [wrong_call], {"serper", "semantic_scholar"})
+
+
+# ---------------------------------------------------------------------------------------------
+# Leg C — external scorer over SYNTHETIC isolated fixtures -> scored ledger + systems summary.
+# ---------------------------------------------------------------------------------------------
+def test_external_scorer_leg_emits_scored_and_summary(tmp_path):
+    leg = run_external_scorer_leg(out_dir=tmp_path)
+
+    # reconcile produced a reconciled ledger (auditor == 'reconciled' is what score_one requires).
+    assert leg.reconciled_ledger_path.exists()
+    reconciled = json.loads(leg.reconciled_ledger_path.read_text(encoding="utf-8"))
+    assert reconciled["auditor"] == "reconciled"
+    # conservative-MAX was non-vacuously exercised: the claude=VERIFIED / codex=FABRICATED
+    # disagreement reconciles to the WORSE verdict (FABRICATED).
+    verdicts = {c["claim_id"]: c["verdict"] for c in reconciled["claims"]}
+    assert verdicts["syn_claim_disagree"] == "FABRICATED"
+
+    # score_run emitted a scored ledger file.
+    assert leg.scored_json_path.exists()
+    scored = json.loads(leg.scored_json_path.read_text(encoding="utf-8"))
+    assert scored["system"] == "chatgpt"
+    assert scored["question_id"] == "Q75"
+    assert "passed" in scored
+    # The reconciled FABRICATED material claim + demoted coverage drive a non-vacuous result.
+    assert scored["passed"] is False
+    assert scored["reasons"]
+
+    # aggregate_systems emitted a systems summary file.
+    assert leg.systems_summary_path.exists()
+    summary_text = leg.systems_summary_path.read_text(encoding="utf-8")
+    assert "Path-B DR head-to-head" in summary_text
+
+    # P2 #1 isolation: every written artifact lives under the tmp out-dir (NEVER outputs/dr_benchmark).
+    for path in (leg.reconciled_ledger_path, leg.scored_json_path, leg.systems_summary_path):
+        assert tmp_path in path.parents or path.parent == tmp_path or tmp_path in path.resolve().parents
+
+
+# ---------------------------------------------------------------------------------------------
+# Full chain — all three legs back-to-back, under the socket block (the capstone proof).
+# ---------------------------------------------------------------------------------------------
+def test_full_offline_chain_runs_under_socket_block(tmp_path):
+    """Run leg A -> leg B -> leg C back-to-back in one test, all under the no-network socket
+    block. If any leg opened a real socket, _BlockedNetworkError would fail this test. Passing
+    here is the affirmative zero-network / zero-spend capstone proof."""
+    # Leg A
+    transport = PerClaimFakeRoleTransport()
+    leg_a = run_four_role_leg(transport, run_dir=tmp_path / "run")
+    assert leg_a.manifest["four_role_evaluation"]["evaluator_agrees"]
+    assert (tmp_path / "run" / "four_role_claim_audit.json").exists()
+
+    # Leg B (PASS + fail-closed)
+    gate_result = run_m4_gate_pass(salt=_SALT)
+    assert "mirror" in gate_result["served_identity_by_role"]
+    pins, wrong_call = build_wrong_model_gate_call()
+    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
+    with pytest.raises(GateError):
+        assert_post_run(pin, [], _SALT, [wrong_call], {"serper", "semantic_scholar"})
+
+    # Leg C
+    leg_c = run_external_scorer_leg(out_dir=tmp_path / "scorer")
+    assert leg_c.scored_json_path.exists()
+    assert leg_c.systems_summary_path.exists()
+
+    # Zero network proved: the verifier roles ran in-process only.
+    assert transport.completions > 0
diff --git a/tests/fixtures/offline_e2e/README.md b/tests/fixtures/offline_e2e/README.md
new file mode 100644
index 00000000..55b933fc
--- /dev/null
+++ b/tests/fixtures/offline_e2e/README.md
@@ -0,0 +1,31 @@
+# Offline E2E fixtures (I-meta-002 PR-9) — SYNTHETIC, non-benchmark, isolated
+
+**synthetic: true.** Every file in this directory is a SYNTHETIC, non-benchmark
+fixture used ONLY by the offline no-spend E2E harness
+(`scripts/dr_benchmark/offline_e2e.py` + `tests/dr_benchmark/test_offline_e2e.py`).
+
+These files are NOT real audits, NOT the frozen DR gold rubric, and NOT competitor
+answers. They prove the external-scorer SCRIPTS run end to end offline — they do NOT
+produce a real score.
+
+Codex P2 #1 (binding): these fixtures are clearly labeled synthetic and live here,
+ISOLATED under `tests/fixtures/offline_e2e/`. The harness NEVER reads anything under
+`outputs/dr_benchmark/` (gold rubric / freeze pin / competitor answers) and NEVER writes
+under `outputs/dr_benchmark/` (scored JSON + final report go to a caller-supplied tmp dir).
+
+Files:
+- `synthetic_rubric.json` — a synthetic 1-question (Q75) rubric with a synthetic
+  `rubric_sha256` pre-registration-anchor STRING (not a hash of any real rubric). Exists
+  only so `score_run`'s stored-field equality (`rubric_doc.rubric_sha256 ==
+  ledger.rubric_sha256`) can be exercised offline.
+- `synthetic_ledger_claude.json` / `synthetic_ledger_codex.json` — two single-auditor
+  ledgers (`auditor: claude` / `auditor: codex`) over the same (system=chatgpt,
+  question=Q75, rubric_sha256). They DISAGREE on one claim (claude=VERIFIED vs
+  codex=FABRICATED) and one coverage row so `scripts.dr_benchmark.reconcile`'s
+  conservative-MAX worse-of-two reconciliation is non-vacuously exercised before
+  `score_run.score_one` runs on the reconciled output.
+
+The 4-role-seam leg of the E2E (manifest `four_role_evaluation` + `four_role_claim_audit.json`)
+uses NO files here: it runs the REAL seam over the annotated `clinical_tirzepatide_t2dm`
+contract (`config/scope_templates/clinical.yaml`) with an INJECTED FAKE RoleTransport and
+canned in-memory report objects — see the harness/test for those in-code fixtures.
diff --git a/tests/fixtures/offline_e2e/synthetic_ledger_claude.json b/tests/fixtures/offline_e2e/synthetic_ledger_claude.json
new file mode 100644
index 00000000..228e981e
--- /dev/null
+++ b/tests/fixtures/offline_e2e/synthetic_ledger_claude.json
@@ -0,0 +1,29 @@
+{
+  "system": "chatgpt",
+  "question_id": "Q75",
+  "auditor": "claude",
+  "audit_method": "SYNTHETIC:true offline-e2e-fixture (NOT a real line-by-line audit; reconciled with synthetic_ledger_codex.json then scored offline; NEVER written under outputs/dr_benchmark)",
+  "audit_timestamp_utc": "2026-05-29T00:00:00+00:00",
+  "rubric_sha256": "synthetic-offline-e2e-rubric-sha256-do-not-use-for-scoring",
+  "claims": [
+    {
+      "claim_id": "syn_claim_agree_verified",
+      "severity": "S1",
+      "verdict": "VERIFIED",
+      "citation_id": "syn_cit_1",
+      "span_quote": "Synthetic span supporting the verified claim."
+    },
+    {
+      "claim_id": "syn_claim_disagree",
+      "severity": "S2",
+      "verdict": "VERIFIED",
+      "citation_id": "syn_cit_2",
+      "span_quote": "Claude read this span as supporting the claim."
+    }
+  ],
+  "coverage": [
+    {"element_id": "syn_element_covered_cited", "covered": true, "citation_supported": true},
+    {"element_id": "syn_element_covered_uncited", "covered": true, "citation_supported": true},
+    {"element_id": "syn_element_uncovered", "covered": false, "citation_supported": false}
+  ]
+}
diff --git a/tests/fixtures/offline_e2e/synthetic_ledger_codex.json b/tests/fixtures/offline_e2e/synthetic_ledger_codex.json
new file mode 100644
index 00000000..901f291a
--- /dev/null
+++ b/tests/fixtures/offline_e2e/synthetic_ledger_codex.json
@@ -0,0 +1,30 @@
+{
+  "system": "chatgpt",
+  "question_id": "Q75",
+  "auditor": "codex",
+  "audit_method": "SYNTHETIC:true offline-e2e-fixture (NOT a real line-by-line audit; DISAGREES with claude on syn_claim_disagree=FABRICATED + syn_element_covered_uncited coverage so conservative-MAX is non-vacuously exercised; NEVER written under outputs/dr_benchmark)",
+  "audit_timestamp_utc": "2026-05-29T00:00:00+00:00",
+  "rubric_sha256": "synthetic-offline-e2e-rubric-sha256-do-not-use-for-scoring",
+  "claims": [
+    {
+      "claim_id": "syn_claim_agree_verified",
+      "severity": "S1",
+      "verdict": "VERIFIED",
+      "citation_id": "syn_cit_1",
+      "span_quote": "Synthetic span supporting the verified claim."
+    },
+    {
+      "claim_id": "syn_claim_disagree",
+      "severity": "S2",
+      "verdict": "FABRICATED",
+      "citation_id": "syn_cit_2",
+      "span_quote": "Codex found the cited span does NOT support the claim (synthetic).",
+      "audit_note": "codex synthetic disagreement: span contradicts the claim"
+    }
+  ],
+  "coverage": [
+    {"element_id": "syn_element_covered_cited", "covered": true, "citation_supported": true},
+    {"element_id": "syn_element_covered_uncited", "covered": true, "citation_supported": false},
+    {"element_id": "syn_element_uncovered", "covered": false, "citation_supported": false}
+  ]
+}
diff --git a/tests/fixtures/offline_e2e/synthetic_rubric.json b/tests/fixtures/offline_e2e/synthetic_rubric.json
new file mode 100644
index 00000000..880e2698
--- /dev/null
+++ b/tests/fixtures/offline_e2e/synthetic_rubric.json
@@ -0,0 +1,15 @@
+{
+  "synthetic": true,
+  "note": "SYNTHETIC non-benchmark fixture for the offline E2E harness (I-meta-002 PR-9). NOT the frozen DR gold rubric. NEVER read from outputs/dr_benchmark. The rubric_sha256 below is a synthetic pre-registration anchor string (NOT a hash of any real rubric); it exists only so score_run's stored-field equality check (rubric_doc.rubric_sha256 == ledger.rubric_sha256) can be exercised offline.",
+  "rubric_sha256": "synthetic-offline-e2e-rubric-sha256-do-not-use-for-scoring",
+  "questions": [
+    {
+      "question_id": "Q75",
+      "elements": [
+        {"element_id": "syn_element_covered_cited"},
+        {"element_id": "syn_element_covered_uncited"},
+        {"element_id": "syn_element_uncovered"}
+      ]
+    }
+  ]
+}
