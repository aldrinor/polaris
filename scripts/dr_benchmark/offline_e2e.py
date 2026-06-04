"""Offline no-spend END-TO-END harness (I-meta-002 PR-9 / readiness item 9).

ONE offline proof that the WHOLE DR toolchain runs end to end so canary day adds ONLY real
model calls. NO MONEY, NO NETWORK anywhere: zero real LLM calls (the generator AND the three
verifier roles are faked / canned), zero socket. Codex DESIGN APPROVE iter 2
(.codex/I-meta-002-pr9-e2e/design_brief.md; zero P0/P1; the 3 P2s are folded in here +
enforced by the driving test).

The chain this harness exercises (all offline):

  A. 4-ROLE SEAM (M3a builder + M3b seam + M5 evaluator_agrees) over the REAL annotated
     `clinical_tirzepatide_t2dm` contract, fed CANNED kept verified sentences + a canned
     evidence pool through an INJECTED FAKE `RoleTransport` (no httpx, no socket). Produces the
     manifest `four_role_evaluation` block (final_verdicts + held/coverage) PLUS the M5
     `evaluator_agrees` map (built by `sweep_integration.build_evaluator_agrees_map`, the SINGLE
     source of the §-1.1 safe rule — never reimplemented here) and the
     `four_role_claim_audit.json` the seam writes next to the run.

  B. M4 PATH-B served==pinned gate over FIXTURE self-host served-metadata: preflight (offline)
     + assert_post_run on a MATCHING `{model, endpoint}` -> PASS; and on a WRONG-MODEL fixture
     -> fail-closed (`GateError`). NO OpenRouter resolution (self-host serving_route branch),
     NO socket (offline=True everywhere).

  C. EXTERNAL SCORER on SYNTHETIC, ISOLATED fixtures (Codex P2 #1): two single-auditor ledgers
     (claude + codex) -> `reconcile` (conservative-MAX) -> a reconciled ledger ->
     `score_run.score_one` -> a per-claim scored JSON -> `aggregate_systems` -> a systems
     summary. The fixtures live under `tests/fixtures/offline_e2e/` and are clearly labeled
     synthetic; this leg NEVER reads or writes under `outputs/dr_benchmark/`.

IMPORT-SAFE: importing this module performs NO I/O, opens NO socket, and starts NO subprocess.
Every function below is pure orchestration over caller-supplied paths / an injected transport;
all real work happens only when a function is called (the driving test calls them with a
`tmp_path` and a fake transport). There is no `__main__` runtime path that spends or networks.

CONTAMINATION-CRITICAL (§-1.1, operator-locked): leg A uses ONLY the native scope contract;
leg C uses ONLY the synthetic isolated fixtures. NOTHING here reads `outputs/dr_benchmark/`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from scripts.dr_benchmark.ledger_schema import dump_ledger, load_ledger
from scripts.dr_benchmark.pathB_run_gate import (
    LLMCall,
    RolePin,
    assert_post_run,
    preflight,
)
from scripts.dr_benchmark.reconcile import reconcile
from scripts.dr_benchmark.run_gate_b import make_gate_b_input_builder
from scripts.dr_benchmark.score_run import score_one
from src.polaris_graph.nodes.scope_gate import load_scope_template
from src.polaris_graph.roles.mirror_contract import CitationSpan
from src.polaris_graph.roles.native_gate_b_inputs import load_required_entities
from src.polaris_graph.roles.role_transport import (
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sweep_integration import (
    FOUR_ROLE_CLAIM_AUDIT_FILENAME,
    FourRoleEvaluationResult,
    build_evaluator_agrees_map,
    run_four_role_seam,
)

# Caller-supplied audit timestamp (LAW VI: no datetime.now() in the harness).
DEFAULT_TIMESTAMP = "2026-05-29T00:00:00Z"

# The annotated NON-benchmark contract this E2E runs the seam over (operator-locked native
# config; NOT a benchmark gold rubric). Resolved by domain through scope_gate.load_scope_template.
TIRZEPATIDE_SLUG = "clinical_tirzepatide_t2dm"
# The native CLINICAL domain key the tirzepatide contract lives under. The harness now resolves
# templates through the SAME production path SWEEP_QUERIES uses — `load_scope_template(domain)` —
# so the tirzepatide default routes through the identical seam as the 5 benchmark questions.
TIRZEPATIDE_DOMAIN = "clinical"

# I-meta-002 PR-11b: the 5 wired benchmark slugs and the EXACT required-element COUNT each one's
# frozen PR-10 native contract declares (the right denominator per question — proven against the
# template, not hardcoded into the builder). The slug->domain ROUTING is NOT hardcoded here: it is
# looked up from the SWEEP_QUERIES registration (`lookup_benchmark_query`) so a routing typo in the
# registration fails the test. Counts: drb_75=6, drb_76=5, drb_78=5, drb_72=7, drb_90=6.
BENCHMARK_SLUG_EXPECTED_ENTITY_COUNT = {
    "drb_75_metal_ions_cvd": 6,
    "drb_76_gut_microbiota_crc": 5,
    "drb_78_parkinsons_dbs": 5,
    "drb_72_ai_labor": 7,
    "drb_90_adas_liability": 6,
}

# Canonical 5-enum verdict tokens the fake Judge may emit (mirror judge_contract.JUDGE_CHOICES;
# the harness only needs the two polarities the §-1.1 evaluator_agrees rule distinguishes).
JUDGE_VERIFIED = "VERIFIED"
JUDGE_FABRICATED = "FABRICATED"

# A marker substring the canned report embeds in a claim's text so the per-claim fake Judge can
# return FABRICATED for THAT claim (proving evaluator_agrees -> False) while every other claim
# gets VERIFIED (proving evaluator_agrees -> True). Deterministic, no network.
FABRICATED_CLAIM_MARKER = "[[offline-e2e-fabricated]]"

# I-meta-002 PR-9/M4: the locked self-hosted verifier roles + a synthetic self-host endpoint.
# These are FIXTURE served-metadata values (no real box) — the gate leg proves served==pinned
# logic offline, exactly as tests/dr_benchmark/test_pathB_run_gate.py does.
MIRROR_SLUG = "cohere/command-a-plus"
SELF_HOST_BASE_URL = "http://10.0.0.5:8000"


# ---------------------------------------------------------------------------------------------
# Benchmark routing — resolve a slug -> its SWEEP_QUERIES domain -> its native contract.
# This is the WIRING proof: the same path production uses (SWEEP_QUERIES registration -> the
# question's domain -> load_scope_template(domain) -> load_required_entities(template, slug)).
# ---------------------------------------------------------------------------------------------
def lookup_benchmark_query(slug: str) -> dict:
    """Return the SWEEP_QUERIES registration entry for `slug` (fail closed if unregistered).

    Imported LAZILY (inside the call) so this module stays import-safe: importing
    `scripts.dr_benchmark.offline_e2e` performs NO I/O and pulls no big sweep file at module
    load. A slug that is not registered — or a registration that lost its `domain` — fails LOUD
    here (a missing/typo'd registration must fail the wiring proof, never silently default).
    """
    from scripts.run_honest_sweep_r3 import SWEEP_QUERIES

    matches = [q for q in SWEEP_QUERIES if q.get("slug") == slug]
    if not matches:
        raise ValueError(
            f"lookup_benchmark_query: slug {slug!r} is not registered in SWEEP_QUERIES; the "
            f"4-role wiring proof requires the question to be routed by its registration "
            f"(fail-closed, no hardcoded slug->domain fallback)."
        )
    if len(matches) > 1:
        raise ValueError(
            f"lookup_benchmark_query: slug {slug!r} is registered {len(matches)} times in "
            f"SWEEP_QUERIES; a benchmark slug must route to exactly one domain (fail-closed)."
        )
    entry = matches[0]
    if not entry.get("domain"):
        raise ValueError(
            f"lookup_benchmark_query: SWEEP_QUERIES entry for slug {slug!r} has no domain; the "
            f"4-role builder keys the frozen contract by (domain template, slug) — a domain-less "
            f"registration cannot route (fail-closed)."
        )
    return entry


def resolve_benchmark_required_element_ids(slug: str) -> list[str]:
    """Resolve `slug`'s native required-element ids through the FULL production routing path.

    SWEEP_QUERIES[slug].domain -> `load_scope_template(domain)` (scope_gate, the same loader the
    sweep uses) -> `native_gate_b_inputs.load_required_entities(template, slug)`. Returns the
    ordered entity-id list (the coverage DENOMINATOR for that question). NON-EMPTY by contract
    (`load_required_entities` raises on a missing/empty contract). NO network, NO spend — pure
    YAML reads. This is the routing leg (build-spec item 1): the question's registered domain
    must load the template that actually holds that slug's contract.
    """
    entry = lookup_benchmark_query(slug)
    template = load_scope_template(entry["domain"])
    entities = load_required_entities(template, slug)
    return [entity["id"] for entity in entities]


def build_benchmark_denominator(slug: str) -> list[str]:
    """Build `slug`'s 4-role coverage denominator via the PRODUCTION M3a builder closure.

    Drives `make_gate_b_input_builder()` (the exact closure `run_gate_b` wires into the sweep)
    with the shared canned report + ev_pool over THAT slug's domain-routed native contract, and
    returns `bundle.inputs.coverage_ledger.required_element_ids`. This is build-spec item 2 (the
    robustness core): it proves the M3a builder, given THIS question, builds the denominator from
    THIS slug's contract — not from a hardcoded value and not from another question's contract.
    NO network, NO spend (the builder is a pure function; no transport is invoked here).
    """
    entry = lookup_benchmark_query(slug)
    domain = entry["domain"]
    template = load_scope_template(domain)
    builder = make_gate_b_input_builder()
    bundle = builder(
        multi=build_canned_report(),
        template=template,
        slug=slug,
        domain=domain,
        ev_pool=build_canned_ev_pool(),
    )
    return list(bundle.inputs.coverage_ledger.required_element_ids)


# ---------------------------------------------------------------------------------------------
# Leg A — the canned FAKE RoleTransport + in-memory report objects (NO network, NO spend).
# ---------------------------------------------------------------------------------------------
class PerClaimFakeRoleTransport:
    """Canned in-process `RoleTransport` — NO network, NO spend (reuses the proven
    tests/dr_benchmark/test_gate_b_seam.py pattern, extended to PER-CLAIM judge verdicts).

    Mirror pass-1 cites the FIRST supplied evidence doc_id (so the grounding binding holds for
    whatever evidence_id the builder minted); pass-2 echoes the embedded content_hash. Sentinel
    returns GROUNDED (`<score>no</score>`). Judge returns FABRICATED for any claim whose prompt
    carries `FABRICATED_CLAIM_MARKER`, else VERIFIED — so the SAME run produces both an
    evaluator_agrees=True (VERIFIED + kept) and an evaluator_agrees=False (FABRICATED) entry,
    which is the §-1.1 safe-rule property the E2E asserts. `completions` counts in-process
    completions (NEVER an HTTP POST) so the test can assert the verifier roles actually ran.
    """

    def __init__(self) -> None:
        self.completions = 0  # canned in-process completions (NEVER an HTTP POST).

    def complete(self, request: RoleRequest) -> RoleResponse:
        self.completions += 1
        if request.role == "mirror":
            if "pass2_input" in (request.params or {}):
                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "supported"}
                return RoleResponse(raw_text=json.dumps(payload), served_model=request.model_slug)
            documents = (request.params or {}).get("documents") or []
            doc_id = documents[0]["doc_id"] if documents else "doc0"
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(doc_id,))],
            )
        if request.role == "sentinel":
            # GROUNDED in whichever groundedness mode the adapter resolved (I-run11-002 L1 +
            # I-run11-004): decomposition (MiniMax-M2 default) -> JSON {"verdict": "supported"};
            # guardian -> `<score>no</score>` (no risk => grounded, lethal-polarity yes=risk);
            # noninverted -> one-word GROUNDED.
            final_instruction = request.messages[-1]["content"] if request.messages else ""
            if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
                sentinel_raw = '{"verdict": "supported", "unsupported_atoms": 0, "atoms": []}'
            elif "<guardian>" in final_instruction:
                sentinel_raw = "<score>no</score>"
            else:
                sentinel_raw = "GROUNDED"
            return RoleResponse(raw_text=sentinel_raw, served_model=request.model_slug)
        if request.role == "judge":
            verdict = (
                JUDGE_FABRICATED
                if FABRICATED_CLAIM_MARKER in (request.prompt or "")
                else JUDGE_VERIFIED
            )
            return RoleResponse(raw_text=verdict, served_model=request.model_slug)
        raise AssertionError(f"unexpected role {request.role!r}")


# --- minimal in-memory report objects (the M3a builder reads only these attributes) ----------
@dataclass
class _FakeToken:
    evidence_id: str


@dataclass
class _FakeVerification:
    sentence: str
    tokens: list
    is_verified: bool = True


class _FakeSection:
    def __init__(self, title: str, verifications: list) -> None:
        self.title = title
        self.kept_sentences_pre_resolve = verifications


class _FakeMulti:
    def __init__(self, sections: list) -> None:
        self.sections = sections


def build_canned_report() -> _FakeMulti:
    """A finished report (two KEPT verified sentences) that cites the canned evidence pool.

    Sentence 1 cites SURPASS-2's REAL DOI (an annotated S1 trial entity in the tirzepatide
    contract) -> covers that element on a VERIFIED Judge verdict -> evaluator_agrees True.
    Sentence 2 carries `FABRICATED_CLAIM_MARKER` -> the fake Judge returns FABRICATED -> final
    verdict FABRICATED -> evaluator_agrees False. Both are KEPT (is_verified=True), so the
    evaluator_agrees boolean is driven purely by the verdict, exactly as the sweep path does.
    """
    return _FakeMulti(
        sections=[
            _FakeSection(
                "Efficacy",
                [
                    _FakeVerification(
                        "SURPASS-2 randomized 1879 patients; tirzepatide lowered HbA1c.",
                        [_FakeToken("ev_000")],
                    )
                ],
            ),
            _FakeSection(
                "Safety",
                [
                    _FakeVerification(
                        f"{FABRICATED_CLAIM_MARKER} An unsupported safety claim with no "
                        "grounded evidence backing.",
                        [_FakeToken("ev_001")],
                    )
                ],
            ),
        ]
    )


def build_canned_ev_pool() -> dict:
    """Raw evidence-pool rows (the run's ev_pool shape) the canned report cites.

    `ev_000` carries SURPASS-2's real DOI via a journal URL so the M3a coverage matcher's EXACT
    canonical-identifier equality credits the trial element. `ev_001` is a generic source for
    the FABRICATED sentence (it never earns coverage because its final verdict is FABRICATED).
    """
    return {
        "ev_000": {
            "evidence_id": "ev_000",
            "direct_quote": "SURPASS-2 randomized 1879 patients; tirzepatide lowered HbA1c.",
            "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        },
        "ev_001": {
            "evidence_id": "ev_001",
            "direct_quote": "A generic source paragraph cited by the unsupported safety claim.",
            "source_url": "https://example.test/generic-source",
        },
    }


@dataclass
class FourRoleLegResult:
    """Leg-A output: the assembled manifest plus the seam result + the parsed audit map."""

    manifest: dict
    result: FourRoleEvaluationResult
    audit: dict


def run_four_role_leg(
    transport: PerClaimFakeRoleTransport,
    *,
    run_dir: Path,
    timestamp: str = DEFAULT_TIMESTAMP,
    domain: str = TIRZEPATIDE_DOMAIN,
    slug: str = TIRZEPATIDE_SLUG,
) -> FourRoleLegResult:
    """Leg A: run the REAL M3a/M3b 4-role seam offline over a NATIVE scope contract.

    Resolves the template through the SAME production loader the sweep uses
    (`scope_gate.load_scope_template(domain)`) — NOT a hardcoded file path — so this leg proves
    the WIRING (the question's domain loads the template that holds its slug's contract), then
    reuses the production builder closure (`make_gate_b_input_builder`) + `run_four_role_seam`
    with the INJECTED fake transport and the shared canned report/ev_pool. Defaults route the
    annotated non-benchmark tirzepatide contract (clinical); the 5 benchmark questions pass their
    own (domain, slug). Then assembles the manifest `four_role_evaluation` block EXACTLY as
    `scripts/run_honest_sweep_r3.py` does (including the M5 `evaluator_agrees` map via
    `build_evaluator_agrees_map`), and reads back the `four_role_claim_audit.json` the seam wrote
    next to the run. NO network, NO spend.
    """
    template = load_scope_template(domain)
    builder = make_gate_b_input_builder()
    result = run_four_role_seam(
        transport,
        run_dir=run_dir,
        timestamp=timestamp,
        four_role_input_builder=builder,
        multi=build_canned_report(),
        template=template,
        slug=slug,
        domain=domain,
        ev_pool=build_canned_ev_pool(),
    )

    # Assemble the manifest block exactly as the sweep does (run_honest_sweep_r3.py:3206-3235).
    # The M5 evaluator_agrees map uses build_evaluator_agrees_map — the SINGLE source of the
    # §-1.1 safe rule (VERIFIED + kept -> True; every other verdict -> False). kept_claim_ids is
    # None here for the same reason as the sweep: every claim_id in final_verdicts was built from
    # a KEPT (is_verified) sentence by the M3a builder.
    manifest: dict = {}
    manifest["four_role_evaluation"] = {
        "release_allowed": result.release_allowed,
        "held_reasons": result.held_reasons,
        "coverage_fraction": round(result.coverage_fraction, 3),
        "fabricated_occurrence_latched": result.fabricated_occurrence_latched,
        "final_verdicts": dict(result.final_verdicts),
    }
    manifest["four_role_evaluation"]["evaluator_agrees"] = build_evaluator_agrees_map(
        result.final_verdicts
    )

    audit_path = run_dir / FOUR_ROLE_CLAIM_AUDIT_FILENAME
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    return FourRoleLegResult(manifest=manifest, result=result, audit=audit)


# ---------------------------------------------------------------------------------------------
# Leg B — M4 Path-B served==pinned gate over FIXTURE self-host served-metadata (NO network).
# ---------------------------------------------------------------------------------------------
def _self_host_pin(role: str, slug: str) -> RolePin:
    """A self-host RolePin (surrogate_fields unused by the self-host branch but the preflight
    no-empty-surrogate guard still requires them non-empty — matches pathB_runner._role_pins())."""
    return RolePin(role, slug, "", ("provider_name", "model"))


def run_m4_gate_pass(
    *,
    salt: bytes,
    role: str = "mirror",
    slug: str = MIRROR_SLUG,
    base_url: str = SELF_HOST_BASE_URL,
) -> dict:
    """Leg B (PASS): preflight (offline) + assert_post_run on a MATCHING self-host served-meta.

    NO network: offline=True takes the self-host serving_route branch (no OpenRouter
    resolution); the served `{model, endpoint}` matches the pinned slug + base_url, so the gate
    returns the established per-role served-identity surrogates. `enforce_architecture_coverage`
    is False (offline test mode uses a single self-host pin, not the full 4-role architecture).
    The caller must set `PG_<ROLE>_BASE_URL` in the env (the test does so via monkeypatch).
    """
    pins = [_self_host_pin(role, slug)]
    pin = preflight([], pins, salt, offline=True, enforce_architecture_coverage=False)
    # Served endpoint reported WITH a trailing slash — must still match (trailing-slash tolerant).
    calls = [
        LLMCall(
            call_id="offline-e2e-mirror",
            role=role,
            prompt_messages_present=True,
            request_hash="offline-e2e-request-hash",
            response_metadata={"model": slug, "endpoint": base_url + "/"},
        )
    ]
    return assert_post_run(pin, [], salt, calls, {"serper", "semantic_scholar"})


def build_wrong_model_gate_call(
    *,
    role: str = "mirror",
    wrong_slug: str = "cohere/command-r-plus",
    base_url: str = SELF_HOST_BASE_URL,
) -> tuple[list, LLMCall]:
    """Leg B (FAIL-CLOSED): build the self-host pin + a WRONG-MODEL served-meta LLMCall.

    Returns `(pins, wrong_call)`; the test runs preflight + assert_post_run with these and
    asserts a `GateError` (a wrong verifier model is a silent capability downgrade — must abort).
    """
    pins = [_self_host_pin(role, MIRROR_SLUG)]
    wrong_call = LLMCall(
        call_id="offline-e2e-mirror-wrong",
        role=role,
        prompt_messages_present=True,
        request_hash="offline-e2e-request-hash",
        response_metadata={"model": wrong_slug, "endpoint": base_url},
    )
    return pins, wrong_call


# ---------------------------------------------------------------------------------------------
# Leg C — external scorer over SYNTHETIC, ISOLATED fixtures (NEVER outputs/dr_benchmark).
# ---------------------------------------------------------------------------------------------
# Repo-relative location of the synthetic, isolated scorer fixtures (Codex P2 #1).
OFFLINE_E2E_FIXTURE_DIR = Path("tests/fixtures/offline_e2e")
SYNTHETIC_RUBRIC_NAME = "synthetic_rubric.json"
SYNTHETIC_LEDGER_CLAUDE_NAME = "synthetic_ledger_claude.json"
SYNTHETIC_LEDGER_CODEX_NAME = "synthetic_ledger_codex.json"

# The synthetic fixtures are tagged (system, question). Kept here so the harness and the test
# read the same identity (and never a real benchmark question's gold data).
SYNTHETIC_SYSTEM = "chatgpt"
SYNTHETIC_QUESTION_ID = "Q75"


@dataclass
class ScorerLegResult:
    """Leg-C output: the paths written under the caller-supplied tmp out-dir + the scored dict."""

    reconciled_ledger_path: Path
    scored_json_path: Path
    systems_summary_path: Path
    scored: dict


def run_external_scorer_leg(
    *,
    out_dir: Path,
    fixture_dir: Path = OFFLINE_E2E_FIXTURE_DIR,
) -> ScorerLegResult:
    """Leg C: reconcile two synthetic single-auditor ledgers -> score_one -> aggregate_systems.

    Reads ONLY the synthetic, isolated fixtures under `fixture_dir` (NEVER
    `outputs/dr_benchmark/`). Writes the reconciled ledger, the scored JSON, and the systems
    summary ONLY under the caller-supplied `out_dir` (NEVER `outputs/dr_benchmark/`). Pure
    offline logic + JSON/markdown writes; no network, no spend.

    `score_one` requires `auditor == "reconciled"`, which only `reconcile()` produces — so this
    leg exercises the real dual-§-1.1 conservative-MAX reconciliation before scoring.
    """
    # aggregate_systems is imported lazily so this module's top-level import stays minimal /
    # side-effect-free (it is only needed when this leg actually runs).
    from scripts.dr_benchmark.aggregate_systems import render_final_report

    out_dir.mkdir(parents=True, exist_ok=True)
    rubric_path = fixture_dir / SYNTHETIC_RUBRIC_NAME
    claude = load_ledger(fixture_dir / SYNTHETIC_LEDGER_CLAUDE_NAME)
    codex = load_ledger(fixture_dir / SYNTHETIC_LEDGER_CODEX_NAME)

    reconciled = reconcile(claude, codex)
    reconciled_path = out_dir / "reconciled_ledger.json"
    dump_ledger(reconciled, reconciled_path)

    scored = score_one(
        system=SYNTHETIC_SYSTEM,
        question_id=SYNTHETIC_QUESTION_ID,
        rubric_path=rubric_path,
        ledger_path=reconciled_path,
    )
    # score_run.main writes <system>_<question>.json into a scored dir; mirror that name so
    # aggregate_systems._collect picks it up.
    scored_dir = out_dir / "scored"
    scored_dir.mkdir(parents=True, exist_ok=True)
    scored_json_path = scored_dir / f"{SYNTHETIC_SYSTEM}_{SYNTHETIC_QUESTION_ID}.json"
    scored_json_path.write_text(
        json.dumps(scored, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    systems_summary_path = out_dir / "systems_summary.md"
    # freeze_pin points at a non-existent path under out_dir so the aggregator renders the
    # "IDENTITY UNVERIFIED" branch (this is a SYNTHETIC dry-run summary, not a real report) and
    # never reads anything under outputs/dr_benchmark.
    render_final_report(
        scored_dir=scored_dir,
        freeze_pin=out_dir / "synthetic_freeze_pin_absent.txt",
        out_path=systems_summary_path,
    )
    return ScorerLegResult(
        reconciled_ledger_path=reconciled_path,
        scored_json_path=scored_json_path,
        systems_summary_path=systems_summary_path,
        scored=scored,
    )
