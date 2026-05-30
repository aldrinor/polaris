"""Per-claim 4-role orchestration — Mirror -> Sentinel -> Judge, fail-closed composition.

I-meta-002 sub-PR-5. This is the COMPOSABLE orchestration layer that drives the three
sub-PR-4 role adapters (Mirror, Sentinel, Judge) over ONE injected `RoleTransport` and
produces a single `D8ClaimRow` (sub-PR-3) per claim, plus a complete per-call audit trail.

There is NO network here and NO spend: the transport is DEPENDENCY-INJECTED. Tests inject a
mock transport. The runtime transport that wraps `openrouter_client` is wired in the sweep
surgery (sub-PR-6), NOT here.

Two safety properties this module guarantees (both clinical-lethal if absent):

1. RECORDING TRANSPORT (Codex iter-2 P1-4). `RecordingTransport` WRAPS the injected transport
   and appends one `RoleCallRecord` to `self.records` on EVERY `complete()` — BEFORE returning
   to the adapter, so the record exists even when the adapter later raises (Mirror fail-closed).
   The Path-B identity gate therefore has no blind spot: every served completion is captured,
   including the highest-risk fail-closed paths.

2. FAIL-CLOSED FINAL VERDICT (Codex iter-2 P1-1, LOCKED rule). `run_claim_pipeline` computes a
   `final_verdict` and writes THAT into `D8ClaimRow.verdict`, while preserving the
   `raw_judge_verdict` separately on the result. The rule (documented inline below) makes it
   impossible for a hallucination — a Mirror with no grounded citation, or a Sentinel
   UNGROUNDED — to reach VERIFIED, while never UPGRADING a worse Judge verdict
   (FABRICATED/UNREACHABLE) to merely UNSUPPORTED.

`claim_id` is a REQUIRED caller-supplied param (Codex iter-2 P1-2): it is used verbatim for
`D8ClaimRow.claim_id` and is NEVER synthesized from claim text (duplicate/edited claims would
otherwise collide and break rewrite/gap traceability).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.polaris_graph.roles.judge_adapter import run_judge
from src.polaris_graph.roles.judge_contract import Verdict
from src.polaris_graph.roles.mirror_adapter import (
    MirrorBindingError,
    MirrorCitationError,
    run_mirror,
)
from src.polaris_graph.roles.mirror_contract import MirrorPass1, MirrorPass2
from src.polaris_graph.roles.release_policy import D8ClaimRow
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleCallRecord,
    RoleRequest,
    RoleResponse,
    RoleTransport,
)
from src.polaris_graph.roles.sentinel_adapter import run_sentinel
from src.polaris_graph.roles.sentinel_contract import SentinelResult, SentinelVerdict

# --- canonical verdict tokens (Verdict is a Literal of plain strings, NOT an Enum) -------
# Mirror release_policy.py's _VERDICT_* string-constant pattern; never write `Verdict.X`.
_VERDICT_VERIFIED = "VERIFIED"
_VERDICT_PARTIAL = "PARTIAL"
_VERDICT_UNSUPPORTED = "UNSUPPORTED"
_VERDICT_FABRICATED = "FABRICATED"
_VERDICT_UNREACHABLE = "UNREACHABLE"

# Judge verdicts that the Sentinel-override DOWNGRADES to UNSUPPORTED (an apparently-good
# verdict on an UNGROUNDED claim). FABRICATED/UNREACHABLE/UNSUPPORTED are NEVER upgraded.
_SENTINEL_OVERRIDE_DOWNGRADE_FROM = (_VERDICT_VERIFIED, _VERDICT_PARTIAL)


class RecordingTransport:
    """Wrap an injected `RoleTransport`; record EVERY completion before returning it.

    On each `complete(request)` the wrapper appends a `RoleCallRecord(role, model_slug,
    served_model, raw_text, parsed=None)` to `self.records` BEFORE returning the underlying
    response (Codex iter-2 P1-4). Because the record is appended before the adapter sees the
    response — and therefore before the adapter can parse or raise — the served-identity
    record survives even on the fail-closed paths (a Mirror pass-1 that then raises
    `MirrorCitationError`). `parsed` is left None here: it is the role contract that parses,
    and the parsed sub-results are carried separately on `ClaimPipelineResult`.
    """

    def __init__(self, transport: RoleTransport) -> None:
        self._transport = transport
        self.records: list[RoleCallRecord] = []

    def complete(self, request: RoleRequest) -> RoleResponse:
        response = self._transport.complete(request)
        # Append BEFORE returning so a downstream adapter raise cannot drop the record.
        self.records.append(
            RoleCallRecord(
                role=request.role,
                model_slug=request.model_slug,
                served_model=response.served_model,
                raw_text=response.raw_text,
                parsed=None,
                # I-meta-002-q1b (#939): carry the separated reasoning so the seam can persist it
                # to four_role_role_calls.jsonl apart from the verdict (None if the role had none).
                reasoning=response.reasoning,
            )
        )
        return response


@dataclass
class ClaimPipelineResult:
    """The full per-claim orchestration result.

    `d8_row` carries the POST-OVERRIDE `final_verdict` in `D8ClaimRow.verdict`.
    `raw_judge_verdict` preserves the Judge's pre-override verdict (None if the Judge never
    ran because Mirror failed closed). `records` is the complete served-identity audit trail
    from the `RecordingTransport` (complete even on fail-closed paths). The raw
    `mirror_result` / `sentinel_result` / `judge_result` are preserved for auditability and
    are None where that stage failed closed / did not run.
    """

    d8_row: D8ClaimRow
    raw_judge_verdict: Verdict | None
    final_verdict: Verdict
    records: list[RoleCallRecord]
    mirror_result: MirrorPass2 | None
    sentinel_result: SentinelResult | None
    judge_result: Verdict | None


def _first_grounded_citation_id(mirror_records: list[RoleCallRecord]) -> str | None:
    """Extract a grounded citation doc_id from the Mirror pass-1 record, else None.

    The grounded doc_ids live on the pass-1 `MirrorPass1.citation_spans` (the pass-2
    `MirrorPass2` carries only a classification + hash, NOT doc_ids). `run_mirror` returns
    its OWN record list whose pass-1 record's `parsed` is a `MirrorPass1`; the first grounded
    span's first doc_id is used for D8 gap reporting. Returns None if no grounded span exists.
    """
    for record in mirror_records:
        parsed = record.parsed
        if isinstance(parsed, MirrorPass1) and parsed.citation_spans:
            for span in parsed.citation_spans:
                if span.doc_ids:
                    return span.doc_ids[0]
    return None


def _compose_final_verdict(
    *,
    mirror_failed_closed: bool,
    sentinel_result: SentinelResult | None,
    raw_judge_verdict: Verdict | None,
) -> Verdict:
    """LOCKED fail-closed composition rule (Codex iter-2 P1-1).

    A hallucination can NEVER reach VERIFIED; a worse Judge verdict is NEVER upgraded.

      (1) Mirror raised MirrorCitationError/MirrorBindingError (no grounded/bound citation)
          -> UNSUPPORTED, regardless of Judge. A claim with no grounded citation can never be
          VERIFIED. (On this path the Judge never ran, so raw_judge_verdict is None.)
      (2) ELSE if Sentinel == UNGROUNDED OR Sentinel.parsed_ok is False
          -> if raw Judge verdict is VERIFIED/PARTIAL, OVERRIDE to UNSUPPORTED;
             if raw Judge verdict is FABRICATED/UNREACHABLE/UNSUPPORTED, PRESERVE it
             (never upgrade a worse verdict to merely UNSUPPORTED).
      (3) ELSE -> raw_judge_verdict (Sentinel grounded + parsed_ok; trust the arbiter).
    """
    # (1) Mirror fail-closed -> UNSUPPORTED.
    if mirror_failed_closed:
        return _VERDICT_UNSUPPORTED

    # raw_judge_verdict is non-None here: the Judge ran (Mirror succeeded). It fails LOUD on a
    # non-enum token (JudgeEnumError propagates from run_judge), so it is a valid Verdict.
    assert raw_judge_verdict is not None  # invariant: Judge ran iff Mirror succeeded.

    # (2) Sentinel UNGROUNDED or unparsed -> downgrade an apparently-good Judge verdict.
    sentinel_unsafe = sentinel_result is None or (
        sentinel_result.verdict == SentinelVerdict.UNGROUNDED
        or not sentinel_result.parsed_ok
    )
    if sentinel_unsafe:
        if raw_judge_verdict in _SENTINEL_OVERRIDE_DOWNGRADE_FROM:
            return _VERDICT_UNSUPPORTED
        return raw_judge_verdict  # FABRICATED / UNREACHABLE / UNSUPPORTED preserved.

    # (3) Sentinel grounded + parsed_ok -> the Judge's verdict stands.
    return raw_judge_verdict


def run_claim_pipeline(
    transport: RoleTransport,
    *,
    claim_id: str,
    claim: str,
    evidence_documents: list[EvidenceDocument],
    severity: str,
    s0_categories: list[str],
    model_slugs: dict[str, str],
    timestamp: str,
) -> ClaimPipelineResult:
    """Run Mirror -> Sentinel -> Judge over the injected transport for ONE claim.

    `model_slugs` maps role -> pinned slug (keys: "mirror", "sentinel", "judge"). `claim_id`
    is REQUIRED and flows verbatim into `D8ClaimRow.claim_id` (never synthesized). `timestamp`
    is passed through for the caller's audit record (this function does NOT call
    datetime.now()).

    Composition is FAIL-CLOSED per `_compose_final_verdict`. On a Mirror fail-closed
    (MirrorCitationError/MirrorBindingError) the pipeline SHORT-CIRCUITS: Sentinel and Judge
    do not run, `final_verdict = UNSUPPORTED`, and the raw sub-results are None — but the
    RecordingTransport still holds the served-identity record for the Mirror call(s) that did
    fire, so the identity gate sees them.
    """
    recording = RecordingTransport(transport)

    mirror_slug = model_slugs["mirror"]
    sentinel_slug = model_slugs["sentinel"]
    judge_slug = model_slugs["judge"]

    mirror_result: MirrorPass2 | None = None
    sentinel_result: SentinelResult | None = None
    judge_result: Verdict | None = None
    raw_judge_verdict: Verdict | None = None
    citation_id: str | None = None
    mirror_failed_closed = False

    # --- stage 14: Mirror (fail CLOSED) ----------------------------------------------
    # Catch the two grounding/binding errors EXPLICITLY (NOT `except: pass`) so they drive the
    # UNSUPPORTED override; any OTHER exception propagates (a transport fault is not a verdict).
    try:
        mirror_result, mirror_records = run_mirror(
            recording, claim, evidence_documents, model_slug=mirror_slug
        )
        citation_id = _first_grounded_citation_id(mirror_records)
    except (MirrorCitationError, MirrorBindingError):
        mirror_failed_closed = True

    # --- stage 15 + 16: Sentinel -> Judge (only if Mirror produced a grounded claim) -----
    if not mirror_failed_closed:
        sentinel_result, _sentinel_records = run_sentinel(
            recording, claim, evidence_documents, model_slug=sentinel_slug
        )
        evidence_text = "\n\n".join(doc.text for doc in evidence_documents)
        # Judge fails LOUD by design: a non-enum token raises JudgeEnumError, which we do NOT
        # catch — a missing/garbage arbiter verdict must propagate, never coerce to a default.
        raw_judge_verdict, _judge_records = run_judge(
            recording,
            claim,
            evidence_text,
            mirror_verdict=str(mirror_result.classification),
            sentinel_verdict=sentinel_result.verdict.value,
            model_slug=judge_slug,
        )
        judge_result = raw_judge_verdict

    final_verdict = _compose_final_verdict(
        mirror_failed_closed=mirror_failed_closed,
        sentinel_result=sentinel_result,
        raw_judge_verdict=raw_judge_verdict,
    )

    d8_row = D8ClaimRow(
        claim_id=claim_id,
        severity=severity,
        verdict=final_verdict,
        citation_id=citation_id,
        s0_categories=list(s0_categories),
    )

    return ClaimPipelineResult(
        d8_row=d8_row,
        raw_judge_verdict=raw_judge_verdict,
        final_verdict=final_verdict,
        records=recording.records,
        mirror_result=mirror_result,
        sentinel_result=sentinel_result,
        judge_result=judge_result,
    )
