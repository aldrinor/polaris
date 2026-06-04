"""Per-claim 4-role pipeline tests (I-meta-002 sub-PR-5). Offline, mock transport, NO network.

Exercises the LOCKED fail-closed composition rule + the RecordingTransport audit capture with
a configurable mock `RoleTransport`. There is NO real LLM call and NO spend: every completion
is canned by `MockTransport`.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.roles.mirror_contract import CitationSpan
from src.polaris_graph.roles.role_pipeline import (
    RecordingTransport,
    run_claim_pipeline,
)
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)

# Lock-sourced slugs (offline; the pipeline only uses them to tag records, never to call out).
_MODEL_SLUGS = {
    "mirror": "cohere/command-a-plus",
    "sentinel": "ibm-granite/granite-guardian-4.1-8b",
    "judge": "qwen/qwen3.6-35b-a3b",
}
_EVIDENCE = [EvidenceDocument(doc_id="doc1", text="The trial reported a 5.0 mg dose.")]
_TIMESTAMP = "2026-05-29T00:00:00Z"


class MockTransport:
    """Configurable mock `RoleTransport` keyed on the request role + Mirror pass.

    - Mirror pass-1 (no `pass2_input` in params): returns a managed-path grounded citation
      span pointing at `doc1` (in the evidence), so `_extract_citations` yields a grounded span
      and the Mirror does NOT fail closed. `mirror_fail_closed=True` flips pass-1 to an
      ungrounded citation (doc_id not in evidence) so `run_mirror` raises MirrorCitationError.
    - Mirror pass-2 (`pass2_input` present): echoes the embedded `content_hash` back in JSON so
      `verify_pass2_binding` holds.
    - Sentinel: returns `<score>yes</score>` (UNGROUNDED) or `<score>no</score>` (GROUNDED).
    - Judge: returns the configured verdict token.

    `seen_roles` records the ordered role sequence so tests can assert Mirror -> Sentinel ->
    Judge ordering.
    """

    def __init__(
        self,
        *,
        sentinel_grounded: bool = True,
        judge_verdict: str = "VERIFIED",
        mirror_fail_closed: bool = False,
    ) -> None:
        self._sentinel_grounded = sentinel_grounded
        self._judge_verdict = judge_verdict
        self._mirror_fail_closed = mirror_fail_closed
        self.seen_roles: list[str] = []

    def complete(self, request: RoleRequest) -> RoleResponse:
        self.seen_roles.append(request.role)
        if request.role == "mirror":
            if "pass2_input" in request.params:
                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "supported"}
                return RoleResponse(
                    raw_text=json.dumps(payload), served_model=request.model_slug
                )
            # pass-1: managed citation path. Grounded -> doc1 (in evidence); fail-closed ->
            # a hallucinated doc_id never supplied, which the binding guard rejects whole.
            doc_id = "ghost-doc" if self._mirror_fail_closed else "doc1"
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(doc_id,))],
            )
        if request.role == "sentinel":
            # Emit the format that MATCHES the active groundedness mode (I-run11-002 L1 +
            # I-run11-004) so the MockTransport stays faithful whichever mode the adapter resolved:
            #   - decomposition (MiniMax-M2 default): JSON {"verdict": "supported"|"unsupported"};
            #   - guardian (request carries `<guardian>`): inverted `<score>yes|no</score>`;
            #   - noninverted: one-word GROUNDED/UNGROUNDED.
            # (run_sentinel selects the matching parser off the same mode, so canned output + parser
            # always pair.)
            final_instruction = request.messages[-1]["content"] if request.messages else ""
            if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
                verdict = "supported" if self._sentinel_grounded else "unsupported"
                n_unsupported = "0" if self._sentinel_grounded else "1"
                raw_text = (
                    '{"verdict": "' + verdict + '", "unsupported_atoms": '
                    + n_unsupported + ', "atoms": []}'
                )
            elif "<guardian>" in final_instruction:
                score = "no" if self._sentinel_grounded else "yes"
                raw_text = f"<score>{score}</score>"
            else:
                raw_text = "GROUNDED" if self._sentinel_grounded else "UNGROUNDED"
            return RoleResponse(raw_text=raw_text, served_model=request.model_slug)
        if request.role == "judge":
            return RoleResponse(
                raw_text=self._judge_verdict, served_model=request.model_slug
            )
        raise AssertionError(f"unexpected role {request.role!r}")


def _run(transport, *, claim_id="claim-1", severity="S0", s0_categories=None):
    return run_claim_pipeline(
        transport,
        claim_id=claim_id,
        claim="The dose is 5.0 mg.",
        evidence_documents=_EVIDENCE,
        severity=severity,
        s0_categories=s0_categories or [],
        model_slugs=_MODEL_SLUGS,
        timestamp=_TIMESTAMP,
    )


# --- RecordingTransport: appends the served record BEFORE returning to the caller/adapter ---
def test_recording_transport_records_before_returning() -> None:
    # The wrapper must have appended the record by the time complete() returns, so a downstream
    # adapter that parses/raises on the returned response cannot drop the served-identity record.
    # (The end-to-end "record survives an adapter raise" guarantee is asserted by
    # test_mirror_fail_closed_unsupported_and_record_present below.)
    class _Inner:
        def complete(self, request: RoleRequest) -> RoleResponse:
            return RoleResponse(raw_text="x", served_model="served-x")

    rec = RecordingTransport(_Inner())
    resp = rec.complete(RoleRequest(role="mirror", model_slug="cohere/command-a-plus"))
    assert resp.served_model == "served-x"
    assert len(rec.records) == 1
    assert rec.records[0].role == "mirror"
    assert rec.records[0].served_model == "served-x"
    assert rec.records[0].parsed is None  # wrapper does not parse


# --- ordering: Mirror -> Sentinel -> Judge ---
def test_ordering_mirror_sentinel_judge() -> None:
    transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    _run(transport)
    # Mirror is two passes; the first three DISTINCT roles in order must be mirror,sentinel,judge.
    first_seen_order = []
    for role in transport.seen_roles:
        if role not in first_seen_order:
            first_seen_order.append(role)
    assert first_seen_order == ["mirror", "sentinel", "judge"]


# --- happy path: Sentinel grounded + Judge VERIFIED -> final VERIFIED ---
def test_grounded_verified_passes_through() -> None:
    transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = _run(transport)
    assert result.raw_judge_verdict == "VERIFIED"
    assert result.final_verdict == "VERIFIED"
    assert result.d8_row.verdict == "VERIFIED"


# --- Sentinel UNGROUNDED overrides Judge VERIFIED -> UNSUPPORTED (raw preserved) ---
def test_sentinel_ungrounded_overrides_judge_verified() -> None:
    transport = MockTransport(sentinel_grounded=False, judge_verdict="VERIFIED")
    result = _run(transport)
    assert result.raw_judge_verdict == "VERIFIED"  # raw preserved
    assert result.final_verdict == "UNSUPPORTED"   # overridden
    assert result.d8_row.verdict == "UNSUPPORTED"


# --- Sentinel UNGROUNDED PRESERVES a worse Judge FABRICATED (never upgraded to UNSUPPORTED) ---
def test_sentinel_ungrounded_preserves_judge_fabricated() -> None:
    transport = MockTransport(sentinel_grounded=False, judge_verdict="FABRICATED")
    result = _run(transport)
    assert result.raw_judge_verdict == "FABRICATED"
    assert result.final_verdict == "FABRICATED"  # NOT upgraded to UNSUPPORTED
    assert result.d8_row.verdict == "FABRICATED"


# --- Mirror fail-closed -> final UNSUPPORTED AND its served record still present ---
def test_mirror_fail_closed_unsupported_and_record_present() -> None:
    transport = MockTransport(mirror_fail_closed=True, judge_verdict="VERIFIED")
    result = _run(transport)
    assert result.final_verdict == "UNSUPPORTED"
    assert result.d8_row.verdict == "UNSUPPORTED"
    # Judge never ran on the short-circuit path.
    assert result.raw_judge_verdict is None
    assert result.judge_result is None
    assert result.mirror_result is None  # Mirror failed closed
    assert result.sentinel_result is None  # short-circuited
    # The Mirror pass-1 served-identity record is STILL captured (recorded before the raise).
    mirror_records = [r for r in result.records if r.role == "mirror"]
    assert mirror_records, "Mirror served-identity record must survive fail-closed"
    assert mirror_records[0].served_model == "cohere/command-a-plus"
    # And no sentinel/judge call was made (short-circuit).
    assert "sentinel" not in {r.role for r in result.records}
    assert "judge" not in {r.role for r in result.records}


# --- claim_id flows VERBATIM into the D8 row (never synthesized) ---
def test_claim_id_flows_into_d8_row() -> None:
    transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = _run(transport, claim_id="custom-claim-id-xyz")
    assert result.d8_row.claim_id == "custom-claim-id-xyz"


# === I-run11-002 L1: composition is byte-unchanged under the NON-INVERTED Sentinel path ======
# These assert the §-1.1 false-accept guard SURVIVES the new non-inverted parser: a grounded
# claim composes to VERIFIED (the run-11 wipeout is fixed) AND a genuinely-ungrounded claim STILL
# fail-closes to UNSUPPORTED (the new GROUNDED-returning parser did NOT blanket-pass).
@pytest.fixture
def _noninverted_env(monkeypatch):
    """Force the benchmark non-inverted Sentinel mode (the run-11 default)."""
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "noninverted")
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)


def test_noninverted_grounded_verified_passes_through(_noninverted_env) -> None:
    """The run-11 fix: under the non-inverted Sentinel, a grounded claim + Judge VERIFIED composes
    to VERIFIED — the verbatim-grounded claims that wrongly wiped to UNSUPPORTED in run 11 now
    pass. (MockTransport emits the one-word `GROUNDED` for the non-inverted prompt.)"""
    transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = _run(transport)
    assert result.raw_judge_verdict == "VERIFIED"
    assert result.final_verdict == "VERIFIED"
    assert result.d8_row.verdict == "VERIFIED"


def test_noninverted_ungrounded_still_unsupported_false_accept_guard(_noninverted_env) -> None:
    """THE §-1.1 false-accept guard: a genuinely-ungrounded claim under the non-inverted Sentinel
    (emits `UNGROUNDED`) STILL downgrades a Judge VERIFIED to UNSUPPORTED. Proves the new
    GROUNDED-returning parser did NOT make composition blanket-pass; the fail-closed safety
    property holds for the non-inverted path exactly as for guardian."""
    transport = MockTransport(sentinel_grounded=False, judge_verdict="VERIFIED")
    result = _run(transport)
    assert result.raw_judge_verdict == "VERIFIED"   # raw preserved
    assert result.final_verdict == "UNSUPPORTED"    # overridden by UNGROUNDED Sentinel
    assert result.d8_row.verdict == "UNSUPPORTED"


def test_noninverted_ungrounded_preserves_worse_judge_fabricated(_noninverted_env) -> None:
    """Under the non-inverted Sentinel, an UNGROUNDED claim still PRESERVES a worse Judge
    FABRICATED (never upgraded to merely UNSUPPORTED) — same preserve-branch behavior."""
    transport = MockTransport(sentinel_grounded=False, judge_verdict="FABRICATED")
    result = _run(transport)
    assert result.raw_judge_verdict == "FABRICATED"
    assert result.final_verdict == "FABRICATED"
    assert result.d8_row.verdict == "FABRICATED"


def test_guardian_env_still_composes_grounded_verified(monkeypatch) -> None:
    """The SOVEREIGN path is intact: with the guardian mode forced, the SAME pipeline composes a
    grounded claim (MockTransport emits `<score>no</score>`) + Judge VERIFIED to VERIFIED."""
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "guardian")
    transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = _run(transport)
    assert result.final_verdict == "VERIFIED"
    assert result.d8_row.verdict == "VERIFIED"


def test_self_host_transport_env_routes_guardian_in_pipeline(monkeypatch) -> None:
    """The runtime-desync guard end-to-end: PG_FOUR_ROLE_TRANSPORT=self_host (no explicit mode)
    with a granite-guardian Sentinel slug resolves to guardian, so the MockTransport's `<guardian>`
    request + `<score>no</score>` output composes correctly to VERIFIED — the sovereign
    granite-Guardian gets the inverted prompt it is trained on. (I-run11-004: with the minimax
    lock slug the self_host default would instead be decomposition; here we pin a guardian slug to
    exercise the transport-derived guardian fall-through.)"""
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    monkeypatch.setenv("PG_SENTINEL_MODEL", "ibm-granite/granite-guardian-4.1-8b")
    transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = _run(transport)
    assert result.final_verdict == "VERIFIED"
    assert result.d8_row.verdict == "VERIFIED"


# --- citation_id is harvested from the Mirror grounded span on the success path ---
def test_citation_id_from_grounded_span() -> None:
    transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = _run(transport)
    assert result.d8_row.citation_id == "doc1"


# --- records capture the full served-identity trail on the success path (no blind spot) ---
def test_records_complete_on_success() -> None:
    transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = _run(transport)
    roles = [r.role for r in result.records]
    # mirror pass-1 + pass-2 (2x) + sentinel (1x) + judge (1x) = 4 records.
    assert roles.count("mirror") == 2
    assert roles.count("sentinel") == 1
    assert roles.count("judge") == 1
    assert all(r.parsed is None for r in result.records)  # wrapper does not parse


# --- Sentinel parse-failure (parsed_ok False) is treated as UNSAFE -> downgrade VERIFIED ---
def test_sentinel_unparsed_is_unsafe_override() -> None:
    class _BadSentinel(MockTransport):
        def complete(self, request: RoleRequest) -> RoleResponse:
            if request.role == "sentinel":
                self.seen_roles.append(request.role)
                # Malformed -> parse fails closed (parsed_ok False, UNGROUNDED).
                return RoleResponse(raw_text="garbage", served_model=request.model_slug)
            return super().complete(request)

    transport = _BadSentinel(judge_verdict="VERIFIED")
    result = _run(transport)
    assert result.sentinel_result is not None
    assert result.sentinel_result.parsed_ok is False
    assert result.final_verdict == "UNSUPPORTED"  # unparsed sentinel downgrades VERIFIED
