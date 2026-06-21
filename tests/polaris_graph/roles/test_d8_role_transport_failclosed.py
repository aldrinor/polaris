"""§-1.4 behavioral replay-harness — D8 role-transport force-close + per-role fail-closed disclosed
adjudication (I-beatboth-006 #1283 Fix A + Fix C). Offline, fake transport, NO network, NO spend.

Acceptance = the effect ACTUALLY FIRES in the real output (committed+green+Codex-approve != wired):

  Fix A (sovereign POST total-deadline force-close): a TRICKLE-HUNG sovereign socket whose `.post`
  blocks past `PG_ROLE_TRANSPORT_TOTAL_S` must FORCE-CLOSE + raise `RoleTransportError` within
  ~deadline+margin (NOT hang), exercising the SAME shared `_post_with_total_deadline` wall the
  OpenRouter path uses. PRE-FIX the bare `self._http_client.post(...)` hangs forever -> the test
  times out; POST-FIX it returns within the bound.

  Fix C (per-role fail-closed + DISCLOSURE PROPAGATION): a force-closed Mirror, Judge, AND Sentinel
  `RoleTransportError` each maps to that claim's UNSUPPORTED adjudication (fail-closed, NEVER
  credited) AND the synthetic `<{role}_role_unavailable>` `RoleCallRecord` (served_model=None, marker
  in raw_text) IS PRESENT in `ClaimPipelineResult.records` EXACTLY ONCE. PRE-FIX the `RoleTransportError`
  escapes the adapter/pipeline (Mirror :330 / Judge :370 uncaught; Sentinel record discarded at :335)
  and either tears the whole seam down OR drops the disclosure record; POST-FIX the claim is disclosed
  UNSUPPORTED and the record reaches `records`. The seam keeps adjudicating every OTHER claim. With the
  degrade flag OFF the seam HARD-HALTS loudly (typed `RoleTransportExhaustedError` +
  `state/halt_*_role_transport_exhausted.md` artifact), NEVER a raw coverage=0 teardown.

FAITHFULNESS: a transport-faulted role makes the claim fail CLOSED (UNSUPPORTED — never VERIFIED,
never credited). The LOCKED `_compose_final_verdict` is untouched. This can only TIGHTEN.
"""

from __future__ import annotations

import json
import re
import threading
import time

import httpx
import pytest

from src.polaris_graph.roles.mirror_contract import CitationSpan
from src.polaris_graph.roles.openai_compatible_transport import (
    OpenAICompatibleRoleTransport,
    RoleTransportError,
)
from src.polaris_graph.roles.release_policy import CoverageLedger
from src.polaris_graph.roles.role_pipeline import (
    _ROLE_UNAVAILABLE_MARKER,
    run_claim_pipeline,
)
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sweep_integration import (
    FourRoleClaim,
    RoleTransportExhaustedError,
    _ROLE_TRANSPORT_EXHAUSTED_STATUS,
    run_four_role_evaluation,
)

# I-beatboth-006 (#1283) Fix C.3 (Codex diff-gate iter-3 P1): the run-driver's EXTRACTED seam-exception
# router + the manifest.status taxonomy map. These ARE the production routing the seam block CALLS (NOT
# a mirrored predicate), so the harness asserts the REAL run-driver wiring — the `_credibility_abort_status`
# (#008b P1-1) precedent. The import is heavy-but-OFFLINE (the module has no top-level network/spend).
from scripts.run_honest_sweep_r3 import (  # noqa: E402
    _route_seam_worker_exception,
    to_unified_status,
)
from src.polaris_graph.llm.openrouter_client import BudgetExceededError

_MODEL_SLUGS = {
    "mirror": "cohere/command-a-plus",
    "sentinel": "ibm-granite/granite-guardian-4.1-8b",
    "judge": "qwen/qwen3.6-35b-a3b",
}
_TIMESTAMP = "2026-05-29T00:00:00Z"
_REQUIRED_S0 = ["contraindications"]
_CLAIM_IDX_RE = re.compile(r"\[\[CLAIMIDX=(\d+)\]\]")
_VERDICT_UNSUPPORTED = "UNSUPPORTED"
_VERDICT_VERIFIED = "VERIFIED"

# The three roles the harness targets (the two the design names verbatim + Sentinel regression).
_HUNG_ROLE_PARAMS = ["mirror", "sentinel", "judge"]


@pytest.fixture(autouse=True)
def _degrade_default_on(monkeypatch):
    """Default-ON degrade for every test unless a test explicitly sets it OFF. Also pin a small
    sovereign POST timeout knob default so Fix A's force-close test is fast + deterministic."""
    monkeypatch.delenv("PG_ROLE_TRANSPORT_DEGRADE", raising=False)
    monkeypatch.delenv("PG_SENTINEL_TRANSPORT_DEGRADE", raising=False)
    # Sequential path keeps the harness deterministic for the pipeline-unit assertions; the seam
    # parallel-vs-sequential equivalence is covered by the existing test_seam_parallel suite.
    monkeypatch.setenv("PG_FOUR_ROLE_CLAIM_WORKERS", "1")


# =====================================================================================================
# Fix A — the SOVEREIGN POST is bounded by the shared total-deadline force-close (real hung socket).
# =====================================================================================================


def _hanging_sovereign_transport(target_role: str, *, hang_seconds: float) -> OpenAICompatibleRoleTransport:
    """A sovereign transport whose injected client's `.post` BLOCKS `hang_seconds` for `target_role`
    (the trickle-hang), returns a valid Judge-shaped 200 otherwise. The rebuild factory returns the
    same kind of client so a post-force-close rebuild stays OFF the network (no real socket/spend)."""

    def _make_client() -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            # Block to simulate a trickle-fed keep-alive socket that httpx's per-byte read timeout
            # never trips — the exact failure class _post_with_total_deadline force-closes.
            time.sleep(hang_seconds)
            return httpx.Response(
                200,
                json={
                    "model": "served/model",
                    "choices": [{"message": {"role": "assistant", "content": "VERIFIED"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 1},
                },
            )

        return httpx.Client(transport=httpx.MockTransport(handler))

    return OpenAICompatibleRoleTransport(_make_client(), http_client_factory=_make_client)


@pytest.mark.parametrize("role", _HUNG_ROLE_PARAMS)
def test_sovereign_post_force_closes_a_hung_socket_within_deadline(role, monkeypatch):
    """Fix A: a trickle-hung sovereign POST FORCE-CLOSES at PG_ROLE_TRANSPORT_TOTAL_S and raises
    RoleTransportError within ~deadline+margin — NOT an unbounded hang. PRE-FIX the bare POST blocks
    the full hang_seconds (>> deadline); POST-FIX it returns at the deadline."""
    # Endpoint env (LAW VI) — keyless self-host vLLM is valid; the URL is never really hit (MockTransport).
    monkeypatch.setenv(f"PG_{role.upper()}_BASE_URL", "http://sovereign.local")
    monkeypatch.delenv(f"PG_{role.upper()}_API_KEY", raising=False)
    # Tiny deadline + zero retries so the test is fast; the hang is 10x the deadline.
    monkeypatch.setenv("PG_ROLE_TRANSPORT_TOTAL_S", "0.5")
    monkeypatch.setenv("PG_ROLE_TRANSPORT_RETRIES", "0")
    # Pin a deterministic served slug for the role (role_endpoint reads the lock; monkeypatch the slug).
    monkeypatch.setattr(
        "src.polaris_graph.roles.openai_compatible_transport._lock_model_slug",
        lambda r: _MODEL_SLUGS[r],
    )
    transport = _hanging_sovereign_transport(role, hang_seconds=5.0)
    request = RoleRequest(role=role, model_slug=_MODEL_SLUGS[role], prompt="decide")

    start = time.monotonic()
    with pytest.raises(RoleTransportError):
        transport.complete(request)
    elapsed = time.monotonic() - start
    # The force-close must fire near the deadline, NOT wait out the full 5s hang.
    assert elapsed < 3.0, (
        f"PRE-FIX FAILURE: the sovereign POST was not bounded by the total-deadline force-close "
        f"(elapsed {elapsed:.2f}s ~ the {5.0}s hang). POST-FIX it force-closes near "
        f"PG_ROLE_TRANSPORT_TOTAL_S and fails closed."
    )


def test_sovereign_client_is_thread_local_no_cross_worker_cascade(monkeypatch):
    """Fix A step-4: the sovereign client is THREAD-LOCAL, so a force-close on one worker's client
    never tears down a sibling worker's in-flight POST on a shared client (Codex shared-client P1)."""
    monkeypatch.setenv("PG_JUDGE_BASE_URL", "http://sovereign.local")
    monkeypatch.setattr(
        "src.polaris_graph.roles.openai_compatible_transport._lock_model_slug",
        lambda r: _MODEL_SLUGS[r],
    )

    def _make_client() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})))

    transport = OpenAICompatibleRoleTransport(_make_client(), http_client_factory=_make_client)
    main_client = transport._http_client
    worker_clients: list[object] = []

    def _worker() -> None:
        worker_clients.append(transport._http_client)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    assert worker_clients and worker_clients[0] is not main_client, (
        "each worker thread must lazily build its OWN client (thread-local), so a force-close on one "
        "thread cannot close a sibling's client"
    )


# =====================================================================================================
# Fix C — per-role fail-closed + DISCLOSURE PROPAGATION, run DIRECTLY against run_claim_pipeline.
# =====================================================================================================


def _claim_idx_from_request(request: RoleRequest) -> int | None:
    documents = (request.params or {}).get("documents") or []
    for doc in documents:
        m = _CLAIM_IDX_RE.search(doc.get("text", "") or "")
        if m:
            return int(m.group(1))
    if request.prompt:
        m = _CLAIM_IDX_RE.search(request.prompt)
        if m:
            return int(m.group(1))
    for message in request.messages or []:
        m = _CLAIM_IDX_RE.search(message.get("content", "") or "")
        if m:
            return int(m.group(1))
    return None


def _sentinel_raw_for_mode(request: RoleRequest, grounded: bool) -> str:
    """Sentinel raw output matching the active groundedness mode (mirrors test_seam_parallel)."""
    final_instruction = request.messages[-1]["content"] if request.messages else ""
    if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
        verdict = "supported" if grounded else "unsupported"
        n = "0" if grounded else "1"
        return ('{"verdict": "' + verdict + '", "unsupported_atoms": ' + n
                + ', "atoms": [{"atom": "x", "status": "' + verdict + '"}]}')
    if "<guardian>" in final_instruction:
        return "<score>no</score>" if grounded else "<score>yes</score>"
    return "GROUNDED" if grounded else "UNGROUNDED"


class _HungRoleTransport:
    """Deterministic fake `RoleTransport`. Healthy roles return valid Mirror/Sentinel/Judge responses
    (so the claim would VERIFY); for `hung_role` (and ONLY claims in `hang_indices`, or all when None)
    the role POST raises `RoleTransportError` — the exact fail-closed output of the bounded transport
    in §3.1. NO network, NO spend (every completion is canned)."""

    def __init__(self, *, hung_role: str | None = None, hang_indices: set[int] | None = None) -> None:
        self._hung_role = hung_role
        self._hang_indices = hang_indices  # None => every claim's hung_role faults.
        self._lock = threading.Lock()
        self.completions = 0

    def _should_hang(self, role: str, idx: int | None) -> bool:
        if role != self._hung_role:
            return False
        if self._hang_indices is None:
            return True
        return idx in self._hang_indices

    def complete(self, request: RoleRequest) -> RoleResponse:
        with self._lock:
            self.completions += 1
        idx = _claim_idx_from_request(request)

        if request.role == "mirror":
            # The hung Mirror faults on its FIRST (pass-1) call; pass-2 (no index) is never reached.
            if self._should_hang("mirror", idx):
                raise RoleTransportError("simulated force-closed mirror socket")
            if "pass2_input" in (request.params or {}):
                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "supported"}
                return RoleResponse(raw_text=json.dumps(payload), served_model=request.model_slug)
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(f"doc-{idx}",))],
            )
        if request.role == "sentinel":
            if self._should_hang("sentinel", idx):
                raise RoleTransportError("simulated force-closed sentinel socket")
            return RoleResponse(
                raw_text=_sentinel_raw_for_mode(request, grounded=True),
                served_model=request.model_slug,
            )
        if request.role == "judge":
            if self._should_hang("judge", idx):
                raise RoleTransportError("simulated force-closed judge socket")
            return RoleResponse(raw_text=_VERDICT_VERIFIED, served_model=request.model_slug)
        raise AssertionError(f"unexpected role {request.role!r}")


_EVIDENCE = [EvidenceDocument(doc_id="doc-0", text="The trial reported a 0.0 mg dose. [[CLAIMIDX=0]]")]


def _run_claim(transport):
    return run_claim_pipeline(
        transport,
        claim_id="claim-0",
        claim="The dose is 0.0 mg. [[CLAIMIDX=0]]",
        evidence_documents=_EVIDENCE,
        severity="S0",
        s0_categories=["contraindications"],
        model_slugs=_MODEL_SLUGS,
        timestamp=_TIMESTAMP,
    )


def _unavailable_records(result):
    return [
        r for r in result.records
        if r.served_model is None and _ROLE_UNAVAILABLE_MARKER in (r.raw_text or "")
    ]


@pytest.mark.parametrize("hung_role", _HUNG_ROLE_PARAMS)
def test_hung_role_claim_is_unsupported_with_exactly_one_disclosure_record(hung_role):
    """Fix C (the binding iter-4 disclosure-propagation fix), run DIRECTLY against run_claim_pipeline:
    a hung Mirror / Judge / Sentinel POST -> that claim's final verdict UNSUPPORTED (fail-closed,
    NEVER credited) AND the synthetic `<{role}_role_unavailable>` record is PRESENT in
    ClaimPipelineResult.records EXACTLY ONCE. PRE-FIX: the RoleTransportError escapes (Mirror :330 /
    Judge :370 uncaught) OR the disclosure record is discarded at the underscore-bound call site, so
    this assertion FAILS; POST-FIX it passes."""
    transport = _HungRoleTransport(hung_role=hung_role)
    result = _run_claim(transport)

    assert result.final_verdict == _VERDICT_UNSUPPORTED, (
        f"a hung {hung_role} must fail the claim CLOSED (UNSUPPORTED), never credited"
    )
    unavailable = _unavailable_records(result)
    assert len(unavailable) == 1, (
        f"PRE-FIX FAILURE: the synthetic <{hung_role}_role_unavailable> disclosure record is not "
        f"present in ClaimPipelineResult.records exactly once (got {len(unavailable)}): "
        f"{[r.raw_text for r in result.records]}"
    )
    assert f"<{hung_role}_role_unavailable>" in unavailable[0].raw_text, (
        f"the disclosure record must name the faulted role ({hung_role})"
    )


def test_clean_success_path_has_no_unavailable_marker_and_no_duplicate_served_record():
    """Fix C: the SUCCESS path (no fault) produces NO `<…_role_unavailable>` record and the selective
    merge does NOT duplicate a served-call record. The claim VERIFIES (byte-behavior unchanged)."""
    transport = _HungRoleTransport(hung_role=None)
    result = _run_claim(transport)

    assert result.final_verdict == _VERDICT_VERIFIED, "the clean path must still VERIFY"
    assert _unavailable_records(result) == [], "no unavailable record on the success path"
    # No served-call record is duplicated: each served (role, raw_text) pair appears once. The
    # RecordingTransport appends one record per served complete(); the C.2-merge selector skips every
    # served record (served_model is not None), so no served call is double-recorded.
    served = [(r.role, r.raw_text) for r in result.records if r.served_model is not None]
    assert len(served) == len(set(served)), (
        "the selective disclosure merge must not duplicate any served-call record"
    )


def test_hung_judge_does_not_synthesize_a_pass():
    """Fix C.2 critical: a hung Judge returns a CONCRETE UNSUPPORTED verdict, NEVER None and NEVER a
    synthesized PASS (compose returns raw_judge_verdict on the sentinel-grounded path)."""
    transport = _HungRoleTransport(hung_role="judge")
    result = _run_claim(transport)
    assert result.final_verdict == _VERDICT_UNSUPPORTED
    assert result.final_verdict != _VERDICT_VERIFIED
    assert result.raw_judge_verdict == _VERDICT_UNSUPPORTED, (
        "the hung-Judge verdict must be a concrete disclosed UNSUPPORTED, never None"
    )


# =====================================================================================================
# Fix C — the SEAM keeps adjudicating every OTHER claim (run_four_role_evaluation), NEVER a teardown.
# =====================================================================================================


def _claim(idx: int) -> FourRoleClaim:
    return FourRoleClaim(
        claim_id=f"claim-{idx}",
        claim_text=f"The dose is {idx}.0 mg. [[CLAIMIDX={idx}]]",
        evidence_documents=[
            EvidenceDocument(
                doc_id=f"doc-{idx}",
                text=f"The trial reported a {idx}.0 mg dose. [[CLAIMIDX={idx}]]",
            )
        ],
        severity="S0",
        s0_categories=["contraindications"],
        covered_element_ids=[f"elem-{idx}"],
    )


@pytest.mark.parametrize("hung_role", _HUNG_ROLE_PARAMS)
def test_seam_continues_adjudicating_when_one_claim_role_faults(hung_role, tmp_path, monkeypatch):
    """Fix C: with the degrade flag ON (default), ONE claim's hung Mirror/Judge/Sentinel POST does NOT
    tear the whole seam down. The faulted claim is disclosed UNSUPPORTED; the OTHER claims still
    ADJUDICATE (VERIFIED). NO seam-wide coverage_fraction=0.0 teardown, NEVER a synthesized PASS."""
    monkeypatch.setenv("PG_FOUR_ROLE_CLAIM_WORKERS", "2")
    claims = [_claim(0), _claim(1), _claim(2)]
    # Only claim index 1 faults on the target role; claims 0 and 2 are healthy and must VERIFY.
    transport = _HungRoleTransport(hung_role=hung_role, hang_indices={1})
    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(3)])

    result = run_four_role_evaluation(
        transport,
        claims=claims,
        run_dir=tmp_path,
        timestamp=_TIMESTAMP,
        coverage_ledger=ledger,
        required_s0_categories=_REQUIRED_S0,
        model_slugs=_MODEL_SLUGS,
        rewrite_already_attempted=True,
    )

    assert result.final_verdicts["claim-1"] == _VERDICT_UNSUPPORTED, (
        f"the {hung_role}-faulted claim must be disclosed UNSUPPORTED"
    )
    assert result.final_verdicts["claim-0"] == _VERDICT_VERIFIED, "claim-0 must still adjudicate"
    assert result.final_verdicts["claim-2"] == _VERDICT_VERIFIED, "claim-2 must still adjudicate"
    # The disclosure record for the faulted claim reached the seam's full records trail.
    unavailable = [
        r for r in result.records
        if r.served_model is None and f"<{hung_role}_role_unavailable>" in (r.raw_text or "")
    ]
    assert len(unavailable) == 1, (
        f"the seam records must carry exactly one <{hung_role}_role_unavailable> disclosure record"
    )
    # The seam credited coverage from the 2 VERIFIED claims (NOT a seam-wide coverage=0 teardown).
    assert result.coverage_fraction > 0.0, (
        "PRE-FIX FAILURE: a single role fault tore the WHOLE seam down (coverage_fraction=0.0). "
        "POST-FIX the seam keeps adjudicating, so the 2 healthy claims credit coverage."
    )


@pytest.mark.parametrize("hung_role", _HUNG_ROLE_PARAMS)
def test_flag_off_hard_halts_with_disclosed_status_and_artifact(
    hung_role, tmp_path, monkeypatch
):
    """Fix C.3: with PG_ROLE_TRANSPORT_DEGRADE=0, a force-closed role HARD-HALTS the seam LOUDLY with
    a TYPED RoleTransportExhaustedError carrying status `abort_role_transport_exhausted` + a
    `state/halt_*_role_transport_exhausted.md` artifact — a DISCLOSED hard halt, NOT a bare coverage=0
    teardown. This asserts the SEAM-UNIT contract (the typed exception + the halt artifact); the
    complementary `test_run_driver_maps_role_transport_exhausted_to_manifest_status` below proves the
    run-driver (run_honest_sweep_r3.py) WIRES that typed exception into manifest.status (the I-beatboth-006
    #1283 Codex diff-gate P1: it must become the disclosed abort_role_transport_exhausted manifest
    status, NOT the generic released_with_disclosed_gaps the seam broad-except would otherwise produce)."""
    monkeypatch.setenv("PG_ROLE_TRANSPORT_DEGRADE", "0")
    monkeypatch.setenv("PG_FOUR_ROLE_CLAIM_WORKERS", "2")
    # Write halt artifacts under tmp_path/state so the test never pollutes the repo state/ dir.
    monkeypatch.chdir(tmp_path)
    claims = [_claim(0), _claim(1)]
    transport = _HungRoleTransport(hung_role=hung_role, hang_indices={1})
    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(2)])

    with pytest.raises(RoleTransportExhaustedError) as excinfo:
        run_four_role_evaluation(
            transport,
            claims=claims,
            run_dir=tmp_path / "run",
            timestamp=_TIMESTAMP,
            coverage_ledger=ledger,
            required_s0_categories=_REQUIRED_S0,
            model_slugs=_MODEL_SLUGS,
            rewrite_already_attempted=True,
        )
    assert excinfo.value.status == _ROLE_TRANSPORT_EXHAUSTED_STATUS, (
        "the typed error must carry the disclosed abort_role_transport_exhausted status"
    )
    artifact = excinfo.value.halt_artifact
    assert artifact is not None and artifact.exists(), (
        "the disclosed hard-halt must write a state/halt_*_role_transport_exhausted.md artifact"
    )
    body = artifact.read_text(encoding="utf-8")
    assert _ROLE_TRANSPORT_EXHAUSTED_STATUS in body and "role_transport_exhausted" in artifact.name


# =====================================================================================================
# I-beatboth-006 (#1283) Codex diff-gate iter-3 P1 — the RESULTING manifest.status, NOT only the typed
# seam exception. The seam raises a TYPED RoleTransportExhaustedError carrying
# status='abort_role_transport_exhausted'; on the flag-OFF path the run-driver
# (scripts/run_honest_sweep_r3.py) must propagate that typed error to its dedicated outer handler so
# manifest.status becomes the DISCLOSED abort — NOT the generic released_with_disclosed_gaps the seam's
# broad-except would otherwise produce. We assert this against the run-driver's EXTRACTED, PURE
# `_route_seam_worker_exception` (the production routing the seam block calls, the `_credibility_abort_status`
# #008b P1-1 precedent) + the run-driver's REAL `to_unified_status` taxonomy — so deleting the seam
# routing branch flips these RED (the §-1.4 discriminating check), NOT a mirrored predicate.
# =====================================================================================================


def test_run_driver_seam_routing_reraises_role_transport_exhausted():
    """Codex diff-gate iter-3 P1 — the DISCRIMINATING behavioral check. The run-driver's EXTRACTED seam
    classifier MUST RE-RAISE a RoleTransportExhaustedError (so it reaches the dedicated outer handler
    that writes the disclosed manifest.status), NEVER return a seam-held reason string. PRE-FIX (the
    RoleTransportExhaustedError branch absent from `_route_seam_worker_exception`): the typed error
    falls through to the generic `seam_error:...` return -> the seam-held path -> manifest.status
    released_with_disclosed_gaps, so this test goes RED. POST-FIX it re-raises -> GREEN. This is the
    one assertion that flips with the seam routing branch present/absent."""
    rte = RoleTransportExhaustedError(
        "force-closed role transport with degrade OFF",
        status=_ROLE_TRANSPORT_EXHAUSTED_STATUS,
        halt_artifact=None,
    )
    with pytest.raises(RoleTransportExhaustedError) as excinfo:
        _route_seam_worker_exception(rte)
    # The SAME typed object propagates (not a re-wrapped/swallowed one) carrying the disclosed status.
    assert excinfo.value is rte
    assert excinfo.value.status == _ROLE_TRANSPORT_EXHAUSTED_STATUS


def test_run_driver_seam_routing_reraises_budget_exceeded():
    """The seam classifier MUST also RE-RAISE a PG_MAX_COST_PER_RUN BudgetExceededError (it reaches the
    existing outer abort_budget_exceeded handler — the clean budget-abort contract), NEVER swallow it
    into a held seam_error. Guards the budget contract while the role-transport branch is added."""
    budget = BudgetExceededError("PG_MAX_COST_PER_RUN breached mid-seam")
    with pytest.raises(BudgetExceededError) as excinfo:
        _route_seam_worker_exception(budget)
    assert excinfo.value is budget


def test_run_driver_seam_routing_holds_timeout_and_generic_as_seam_error():
    """The seam classifier maps the seam-WALL TimeoutError -> 'seam_timeout' and any OTHER failure ->
    'seam_error:<Type>:<msg>' (HELD, fail-closed) — the byte-behavior the collapsed broad-except MUST
    preserve (Codex diff-gate iter-3: the `except`-collapse keeps TimeoutError/generic semantics)."""
    import concurrent.futures as _cf

    assert _route_seam_worker_exception(_cf.TimeoutError()) == "seam_timeout"

    generic = ValueError("some other seam fault")
    routed = _route_seam_worker_exception(generic)
    assert routed.startswith("seam_error:ValueError:")
    assert "some other seam fault" in routed


def test_run_driver_maps_role_transport_exhausted_to_manifest_status():
    """Codex diff-gate iter-3 P1 — the RESULTING manifest.status terminal. The status the seam's
    RoleTransportExhaustedError carries (_ROLE_TRANSPORT_EXHAUSTED_STATUS) maps — through the SAME
    `to_unified_status` the run-driver's outer handler uses to set manifest['status'] — to the
    DISCLOSED `abort_role_transport_exhausted`, and is DISTINCT from the generic
    `released_with_disclosed_gaps` the seam-held broad-except path produces. This pins the taxonomy
    entry (_SUMMARY_TO_UNIFIED line ~317): a missing entry would silently degrade the disclosed abort
    to the error_unexpected default."""
    mapped = to_unified_status(_ROLE_TRANSPORT_EXHAUSTED_STATUS)
    assert mapped == _ROLE_TRANSPORT_EXHAUSTED_STATUS == "abort_role_transport_exhausted", (
        "to_unified_status must pass the disclosed abort_role_transport_exhausted status through to "
        "itself (not the error_unexpected default); register it in _SUMMARY_TO_UNIFIED."
    )
    # The bite: the disclosed abort is the PRECISE wrong-answer the swallow path produces, so the
    # `!=` is what distinguishes "wired to the disclosed abort" from "swallowed into the held release".
    assert mapped != "released_with_disclosed_gaps", (
        "the role-transport hard halt must NOT resolve to the generic released_with_disclosed_gaps "
        "the seam broad-except produces — that is exactly the Codex diff-gate P1 the run-driver fixes."
    )

    # The disclosed status string is a REGISTERED member of the runner's unified taxonomy (so the
    # outer handler's to_unified_status(...) result is an accepted manifest.status terminal).
    from scripts.run_honest_sweep_r3 import UNIFIED_STATUS_VALUES

    assert _ROLE_TRANSPORT_EXHAUSTED_STATUS in UNIFIED_STATUS_VALUES, (
        "the disclosed abort_role_transport_exhausted status must be a member of the runner's "
        "UNIFIED_STATUS_VALUES taxonomy (else it is not a valid manifest.status terminal)"
    )


# =====================================================================================================
# I-beatboth-006 (#1283) Codex diff-gate iter-3 P1 — the MIDDLE link: the run-driver's dedicated OUTER
# handler actually WRITES manifest.status from the typed exception. A full `run_one_query` manifest
# assertion is INFEASIBLE offline (it needs retrieval + generation + a real corpus, none available in
# this harness), so the three behavioral tests above prove the seam re-raise (link 1) + the taxonomy
# mapping (link 3), and THIS structural check proves link 2 — the `except RoleTransportExhaustedError`
# clause that does `manifest["status"] = to_unified_status(<exc>.status)`. Together: delete the helper
# re-raise branch -> link-1 test RED; delete the outer handler -> THIS test RED; delete the taxonomy
# entry -> the mapping test RED. Full-chain discrimination without a live run.
# =====================================================================================================

import ast as _ast  # noqa: E402 — used only by the outer-handler wiring assertion below.
import pathlib as _pathlib  # noqa: E402

_RUN_DRIVER_PATH = (
    _pathlib.Path(__file__).resolve().parents[3] / "scripts" / "run_honest_sweep_r3.py"
)
# The aliases the dedicated outer handler may catch the typed seam exception under.
_RTE_HANDLER_ALIASES = {"RoleTransportExhaustedError", "_RoleTransportExhaustedError"}


def _role_transport_except_handlers(source: str) -> "list[_ast.ExceptHandler]":
    """Every `except <RoleTransportExhaustedError-by-any-alias> as e:` handler in the run-driver
    (bare `Name` or dotted `Attribute`, single type or tuple). EMPTY => the run-driver has NO dedicated
    handler -> the typed exception falls to the generic broad-except and manifest.status becomes the
    GENERIC released path (the PRE-FIX state this gate goes RED on)."""
    handlers: "list[_ast.ExceptHandler]" = []
    for node in _ast.walk(_ast.parse(source)):
        if not isinstance(node, _ast.ExceptHandler) or node.type is None:
            continue
        caught = node.type.elts if isinstance(node.type, _ast.Tuple) else [node.type]
        for t in caught:
            name = (
                t.id if isinstance(t, _ast.Name)
                else t.attr if isinstance(t, _ast.Attribute)
                else None
            )
            if name in _RTE_HANDLER_ALIASES:
                handlers.append(node)
                break
    return handlers


def _handler_wires_manifest_status(handler: "_ast.ExceptHandler") -> bool:
    """True iff the handler body BOTH (a) routes a value through `to_unified_status(...)` AND
    (b) assigns a `<...>manifest[...]["status"]` subscript — i.e. it WIRES the typed exception's status
    into the manifest (not merely logs it). Distinguishes the real OUTER handler that writes the
    manifest from the seam-level `except ...: <route>` that only re-raises."""
    routes_via_unifier = False
    writes_manifest_status = False
    for sub in _ast.walk(handler):
        if (
            isinstance(sub, _ast.Call)
            and isinstance(sub.func, _ast.Name)
            and sub.func.id == "to_unified_status"
        ):
            routes_via_unifier = True
        if isinstance(sub, _ast.Assign):
            for tgt in sub.targets:
                if (
                    isinstance(tgt, _ast.Subscript)
                    and isinstance(tgt.value, _ast.Name)
                    and tgt.value.id.endswith("manifest")
                    and isinstance(tgt.slice, _ast.Constant)
                    and tgt.slice.value == "status"
                ):
                    writes_manifest_status = True
    return routes_via_unifier and writes_manifest_status


def test_run_driver_outer_handler_wires_role_transport_exhausted_into_manifest_status():
    """Codex diff-gate iter-3 P1 — link 2 (the RESULTING manifest.status write). The run-driver
    (run_honest_sweep_r3.py) MUST have a dedicated `except RoleTransportExhaustedError` handler whose
    body routes the exception's `.status` through `to_unified_status` and assigns `manifest['status']`.
    PRE-FIX (no dedicated handler): the typed seam exception falls to the generic broad-except ->
    manifest.status becomes released_with_disclosed_gaps / error_unexpected, so this goes RED. POST-FIX
    the handler exists and wires manifest['status'] -> GREEN. Structural (not a live run) because a
    full run_one_query manifest assertion needs retrieval/generation/corpus unavailable offline."""
    source = _RUN_DRIVER_PATH.read_text(encoding="utf-8")
    handlers = _role_transport_except_handlers(source)
    assert handlers, (
        "run_honest_sweep_r3.py has NO dedicated `except RoleTransportExhaustedError` handler -> the "
        "typed seam exception falls to the generic broad-except and manifest.status becomes the GENERIC "
        "released_with_disclosed_gaps / error_unexpected, NOT the disclosed abort_role_transport_exhausted "
        "(Codex diff-gate P1). Wire a handler that sets manifest['status'] from the exception's .status."
    )
    wiring_handlers = [h for h in handlers if _handler_wires_manifest_status(h)]
    assert wiring_handlers, (
        "a `except RoleTransportExhaustedError` handler exists but NONE wires the exception's .status "
        "into manifest['status'] via to_unified_status — the disclosed abort_role_transport_exhausted "
        "manifest status is not actually produced (Codex diff-gate P1)."
    )
