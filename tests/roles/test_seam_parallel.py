"""I-run11-001 (#1042) — the 4-role seam parallelizes the per-claim COMPUTE while keeping ALL
reduction + persistence deterministic on the parent thread in INPUT order. Offline, fake
transport, NO network, NO real LLM, NO spend.

Codex Path-B SAFE design (`.codex/I-run11-seam/codex_decision.txt`): the per-claim
Mirror->Sentinel->Judge pipeline is independent across claims (each `run_claim_pipeline` builds
its OWN `RecordingTransport`), so the COMPUTE half can run in a small thread pool while the D8
policy, coverage credit, KG write, run-budget cap, and `four_role_role_calls.jsonl` write all
stay on the PARENT thread in ORIGINAL claim order.

These tests prove the five acceptance criteria:
  (a) output order (final_verdicts / d8_rows / role_call_log) == INPUT order regardless of
      COMPLETION order — the fake sleeps INVERSELY to index (claim 0 longest) with workers >=
      len(claims) so completion order reverses input order, yet the reduction stays input-ordered.
  (b) parallel total cost == sequential total cost AND the SAME PG_MAX_COST_PER_RUN cap trips
      (BudgetExceededError) at the same accumulated spend — the tipping cost is on the LAST
      pipeline call (Judge) of the tripping claim, so sequential mid-claim trip and parallel
      claim-boundary trip both fire at total = sum(1..K).
  (c) coverage credited ONLY on VERIFIED.
  (d) role_call_log complete (one block of records per claim, in INPUT order).
  (e) PG_FOUR_ROLE_CLAIM_WORKERS=1 path matches the multi-worker result.

Worker-count control: `_CLAIM_WORKERS` is read from env AT IMPORT, so tests
`monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", n)` — the same module-attribute pattern
`test_four_role_budget_cap.py` uses for `PG_MAX_COST_PER_RUN` (an in-test env var would NOT take).
The cap is likewise patched via `monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", x)`
(import-time constant, NOT re-read from env), and `reset_run_cost()` is called at the top of every
cost test because `_RUN_COST_CTX` persists across synchronous tests in one process.

Thread-safety of the fake: the shared `complete()` counter is guarded by a `threading.Lock` (the
parallel path calls it from several worker threads at once); a plain `+= 1` would race.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time

import pytest

import src.polaris_graph.benchmark.pathB_capture as pathB_capture
import src.polaris_graph.llm.openrouter_client as openrouter_client
from src.polaris_graph.llm.openrouter_client import BudgetExceededError
from src.polaris_graph.roles import sweep_integration
from src.polaris_graph.roles.mirror_contract import CitationSpan
from src.polaris_graph.roles.release_policy import CoverageLedger
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sweep_integration import (
    FOUR_ROLE_COMPUTE_PROGRESS_FILENAME,
    FOUR_ROLE_ROLE_CALLS_FILENAME,
    FourRoleClaim,
    run_four_role_evaluation,
)

_MODEL_SLUGS = {
    "mirror": "cohere/command-a-plus",
    "sentinel": "ibm-granite/granite-guardian-4.1-8b",
    "judge": "qwen/qwen3.6-35b-a3b",
}
_TIMESTAMP = "2026-05-29T00:00:00Z"
_REQUIRED_S0 = ["contraindications"]


def _sentinel_raw_for_mode(request: RoleRequest, grounded: bool) -> str:
    """The Sentinel raw output that MATCHES the active groundedness mode (I-run11-002 L1 +
    I-run11-004).

    `run_sentinel` selects the parser off the resolved mode: decomposition (MiniMax-M2 default) ->
    JSON {"verdict": "supported"|"unsupported"}; guardian (`<guardian>` block) -> inverted
    `<score>yes|no</score>`; noninverted -> one-word GROUNDED/UNGROUNDED. The fake emits the
    SAME-mode format so canned output and parser always pair (whatever
    PG_SENTINEL_GROUNDEDNESS_MODE / PG_SENTINEL_MODEL / PG_FOUR_ROLE_TRANSPORT resolve to)."""
    final_instruction = request.messages[-1]["content"] if request.messages else ""
    if "Decompose the CLAIM into atomic sub-assertions" in final_instruction:
        verdict = "supported" if grounded else "unsupported"
        n = "0" if grounded else "1"
        return '{"verdict": "' + verdict + '", "unsupported_atoms": ' + n + ', "atoms": []}'
    if "<guardian>" in final_instruction:
        return "<score>no</score>" if grounded else "<score>yes</score>"
    return "GROUNDED" if grounded else "UNGROUNDED"


# A per-claim marker embedded in BOTH the claim text and the evidence text so the fake can recover
# a claim's index from ANY role call: the Mirror pass-1 + Sentinel calls carry it via the
# `documents` payload, and the Judge call carries it via its prompt (claim + evidence rendered in).
_CLAIM_IDX_RE = re.compile(r"\[\[CLAIMIDX=(\d+)\]\]")


class _DelayedFakeTransport:
    """Deterministic, thread-safe fake `RoleTransport` keyed on a per-claim index marker.

    Each claim's claim_text AND evidence text carry `[[CLAIMIDX=<idx>]]`; the fake recovers `<idx>`
    from the request's `documents` payload (Mirror pass-1, Sentinel) OR its `prompt` (Judge — the
    claim + evidence are rendered into the prompt by `build_judge_request`). The Mirror PASS-2 call
    carries NEITHER (its prompt is a fixed string, no documents), so its index is None and it gets
    `usage=None` — harmless for these tests, which never place usage on the Mirror pass-2 call.

    On the Mirror PASS-1 call (the FIRST call of each claim) it sleeps `delay_per_index[idx]` so a
    larger early-index delay makes COMPLETION order reverse INPUT order. Verdicts are per-index
    deterministic:

      * `judge_verdict_by_index[idx]` -> the Judge token for claim idx (default "VERIFIED").
      * `sentinel_grounded_by_index[idx]` -> Sentinel GROUNDED (`no`) vs UNGROUNDED (`yes`).
      * `usage_by_index_role[(idx, role)]` -> the per-call `usage` dict driving cost (cap tests).

    `completions` (lock-guarded) counts in-process completions; NEVER a socket.
    """

    def __init__(
        self,
        *,
        delay_per_index: dict[int, float] | None = None,
        judge_verdict_by_index: dict[int, str] | None = None,
        sentinel_grounded_by_index: dict[int, bool] | None = None,
        usage_by_index_role: dict[tuple[int, str], dict] | None = None,
    ) -> None:
        self._delay = delay_per_index or {}
        self._judge = judge_verdict_by_index or {}
        self._sentinel_grounded = sentinel_grounded_by_index or {}
        self._usage = usage_by_index_role or {}
        self._lock = threading.Lock()
        self.completions = 0

    @staticmethod
    def _index_from_request(request: RoleRequest) -> int | None:
        """Recover the claim index from the `[[CLAIMIDX=<idx>]]` marker in the documents or prompt.

        Searches the `documents` payload first (Mirror pass-1, Sentinel) then the prompt (Judge).
        Returns None when neither carries the marker (the Mirror pass-2 call), which the tests
        treat as a no-usage call.
        """
        documents = (request.params or {}).get("documents") or []
        for doc in documents:
            m = _CLAIM_IDX_RE.search(doc.get("text", "") or "")
            if m:
                return int(m.group(1))
        if request.prompt:
            m = _CLAIM_IDX_RE.search(request.prompt)
            if m:
                return int(m.group(1))
        # I-run11-004: the decomposition Sentinel carries the span (with its [[CLAIMIDX]] marker)
        # INLINE in the single user message (NOT in documents — see sentinel_adapter P1-2), so the
        # fake recovers the index from the message content, like the Judge prompt.
        for message in request.messages or []:
            m = _CLAIM_IDX_RE.search(message.get("content", "") or "")
            if m:
                return int(m.group(1))
        return None

    def complete(self, request: RoleRequest) -> RoleResponse:
        with self._lock:
            self.completions += 1

        if request.role == "mirror":
            if "pass2_input" in (request.params or {}):
                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "supported"}
                return RoleResponse(
                    raw_text=json.dumps(payload),
                    served_model=request.model_slug,
                    usage=None,  # Mirror pass-2 carries no index marker; tests place no usage here.
                )
            # Pass-1: this is the FIRST call of the claim — sleep here so completion order can
            # reverse input order. The citation binds the claim's `doc-<idx>` doc_id.
            idx = self._index_from_request(request)
            assert idx is not None, "pass-1 mirror request must carry the claim-index marker"
            delay = self._delay.get(idx, 0.0)
            if delay:
                time.sleep(delay)
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(f"doc-{idx}",))],
                usage=self._usage.get((idx, "mirror")),
            )

        idx = self._index_from_request(request)
        if request.role == "sentinel":
            grounded = self._sentinel_grounded.get(idx, True)
            return RoleResponse(
                raw_text=_sentinel_raw_for_mode(request, grounded),
                served_model=request.model_slug,
                usage=self._usage.get((idx, "sentinel")),
            )
        if request.role == "judge":
            verdict = self._judge.get(idx, "VERIFIED")
            return RoleResponse(
                raw_text=verdict,
                served_model=request.model_slug,
                usage=self._usage.get((idx, "judge")),
            )
        raise AssertionError(f"unexpected role {request.role!r}")


def _claim(idx: int, *, covers=None, s0=None) -> FourRoleClaim:
    """Build claim `idx`. The `[[CLAIMIDX=<idx>]]` marker rides in BOTH the claim text and the
    evidence text so the fake can recover the index from any role call (documents OR judge prompt);
    the citation binds `doc-<idx>`."""
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
        s0_categories=s0 if s0 is not None else ["contraindications"],
        covered_element_ids=covers if covers is not None else [f"elem-{idx}"],
    )


def _run(transport, claims, *, run_dir, ledger):
    return run_four_role_evaluation(
        transport,
        claims=claims,
        run_dir=run_dir,
        timestamp=_TIMESTAMP,
        coverage_ledger=ledger,
        required_s0_categories=_REQUIRED_S0,
        model_slugs=_MODEL_SLUGS,
        rewrite_already_attempted=True,
    )


def _read_role_call_log(run_dir) -> list[dict]:
    path = run_dir / FOUR_ROLE_ROLE_CALLS_FILENAME
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


# === (a) + (d) output/role_call_log order == INPUT order regardless of COMPLETION order ========
def test_output_order_is_input_order_under_reversed_completion(monkeypatch, tmp_path):
    # 4 workers, 4 claims; claim 0 sleeps LONGEST so it COMPLETES LAST (completion order is the
    # REVERSE of input order). The reduction must still be input-ordered.
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
    n = 4
    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
    # Decreasing delay with index -> claim 0 finishes LAST, claim n-1 finishes FIRST.
    delays = {i: 0.05 * (n - i) for i in range(n)}
    transport = _DelayedFakeTransport(delay_per_index=delays)

    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)

    # (a) final_verdicts iteration order == input order (dict preserves insertion order).
    assert list(result.final_verdicts.keys()) == [f"claim-{i}" for i in range(n)]
    # all_records are appended in input claim order: the per-claim record blocks (asserted from the
    # role-call log below) partition the served-identity trail in input order.
    # (d) role_call_log: one contiguous block per claim, claims in INPUT order.
    log = _read_role_call_log(tmp_path)
    claim_order_in_log = []
    for entry in log:
        if not claim_order_in_log or claim_order_in_log[-1] != entry["claim_id"]:
            claim_order_in_log.append(entry["claim_id"])
    assert claim_order_in_log == [f"claim-{i}" for i in range(n)]
    # Each claim contributes a CONTIGUOUS block (mirror x2, sentinel, judge == 4 records) and the
    # blocks do not interleave.
    from itertools import groupby

    block_ids = [cid for cid, _ in groupby(e["claim_id"] for e in log)]
    assert block_ids == [f"claim-{i}" for i in range(n)], "claim blocks must not interleave"
    per_claim_counts = {cid: sum(1 for e in log if e["claim_id"] == cid) for cid in block_ids}
    assert all(c == 4 for c in per_claim_counts.values()), per_claim_counts


# === Codex iter-2 P1 — the PARALLEL path mkdir's a missing run_dir (regression guard) ===========
def test_parallel_run_dir_created_when_missing(monkeypatch, tmp_path):
    # Codex iter-2 P1 (REGRESSION): the parallel as_completed loop writes
    # four_role_compute_progress.json under run_dir BEFORE VerifiedClaimGraphStore (which is what
    # historically created run_dir). With a run_dir that does NOT pre-exist, the pre-fix progress
    # write raised FileNotFoundError. Pass a non-existent run_dir + workers>=2 + a trivial fake
    # transport and assert the run does NOT raise and the progress marker landed with done==total.
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
    run_dir = tmp_path / "nonexistent_run"
    assert not run_dir.exists()  # the seam must create it itself, not the test.
    n = 2
    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
    transport = _DelayedFakeTransport()

    # Without the mkdir this raises FileNotFoundError on the first progress write inside the pool.
    result = _run(transport, claims, run_dir=run_dir, ledger=ledger)

    assert result.final_verdicts == {"claim-0": "VERIFIED", "claim-1": "VERIFIED"}
    progress_path = run_dir / FOUR_ROLE_COMPUTE_PROGRESS_FILENAME
    assert progress_path.exists(), "parallel compute must write the progress marker"
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    assert progress == {"done": n, "total": n}


# === (e) PG_FOUR_ROLE_CLAIM_WORKERS=1 result == multi-worker result =============================
def test_sequential_path_matches_multi_worker(monkeypatch, tmp_path):
    n = 3
    ledger_req = [f"elem-{i}" for i in range(n)]
    # Mixed verdicts so the comparison is non-trivial: claim 1 is Sentinel-UNGROUNDED -> UNSUPPORTED.
    judge = {0: "VERIFIED", 1: "VERIFIED", 2: "VERIFIED"}
    sentinel = {0: True, 1: False, 2: True}

    def run_with_workers(workers, sub_dir):
        monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", workers)
        run_dir = tmp_path / sub_dir
        run_dir.mkdir()
        claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
        ledger = CoverageLedger(required_element_ids=list(ledger_req))
        transport = _DelayedFakeTransport(
            judge_verdict_by_index=judge, sentinel_grounded_by_index=sentinel
        )
        return _run(transport, claims, run_dir=run_dir, ledger=ledger), run_dir

    seq, seq_dir = run_with_workers(1, "seq")
    par, par_dir = run_with_workers(4, "par")

    assert seq.final_verdicts == par.final_verdicts
    assert seq.final_verdicts == {
        "claim-0": "VERIFIED",
        "claim-1": "UNSUPPORTED",
        "claim-2": "VERIFIED",
    }
    # Gap is a plain dataclass -> structural equality; the gaps list must match in content + order.
    assert seq.gaps == par.gaps
    assert seq.release_allowed == par.release_allowed
    assert seq.coverage_fraction == pytest.approx(par.coverage_fraction)
    # The role-call logs are byte-identical between the two paths (input-ordered, same content).
    assert _read_role_call_log(seq_dir) == _read_role_call_log(par_dir)


# === (c) coverage credited ONLY on VERIFIED (parallel path) =====================================
def test_coverage_credit_only_on_verified_parallel(monkeypatch, tmp_path):
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
    n = 2
    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
    # claim-0 VERIFIED, claim-1 Sentinel-UNGROUNDED -> UNSUPPORTED -> elem-1 uncovered.
    transport = _DelayedFakeTransport(
        judge_verdict_by_index={0: "VERIFIED", 1: "VERIFIED"},
        sentinel_grounded_by_index={0: True, 1: False},
    )
    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)
    assert result.final_verdicts == {"claim-0": "VERIFIED", "claim-1": "UNSUPPORTED"}
    # Only elem-0 credited -> 0.5 < 0.70 -> held.
    assert result.coverage_fraction == pytest.approx(0.5)
    assert result.release_allowed is False
    # KG persisted both, only the VERIFIED row is reusable (anti-poisoning), order is input-order.
    conn = sqlite3.connect(str(result.kg_path))
    try:
        rows = conn.execute(
            "SELECT claim_id, verdict, reusable FROM verified_claims ORDER BY rowid"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [("claim-0", "VERIFIED", 1), ("claim-1", "UNSUPPORTED", 0)]


# === (b) parallel total cost == sequential total cost AND same cap trip point ===================
# The tipping cost is placed on the LAST pipeline call (the JUDGE) of the tripping claim, so the
# sequential live-mid-claim trip and the parallel claim-boundary trip fire at the SAME total.

# A LARGE reasoning block on the qwen Judge slug (~$0.12/call at $0.60/M output) — an order of
# magnitude above the ~$0.003 per-call floor, so it alone tips the cap and makes the trip point
# unambiguous (it is the LAST call of its claim, so the sequential live-trip and the parallel
# boundary-trip fire at the SAME accumulated total).
_BIG_JUDGE_USAGE = {
    "prompt_tokens": 1000,
    "completion_tokens": 1000,
    "completion_tokens_details": {"reasoning_tokens": 200_000},
}


def _cost_claims(n):
    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
    return claims, ledger


def test_parallel_and_sequential_trip_cap_at_same_total(monkeypatch, tmp_path):
    # (b) CUMULATIVE cap, same trip total on both paths. n=2; the LAST claim (claim-1) is the
    # tripping claim and its JUDGE (the LAST call of its pipeline) carries the tipping usage
    # (~$0.1207). Conditions (advisor): every claim is individually UNDER the cap (so NO worker
    # pre-trips in its reset context), and a parent pre-seed makes the CUMULATIVE — not a single
    # claim — cross the cap. With n=2 and the tip on the last claim, BOTH workers fully spend and
    # BOTH deltas are reduced, so the parent total equals the true spend (clean equality).
    #
    #   cap = 0.20; parent pre-seed 0.10.
    #   claim-0 total ~= 0.00911 ; claim-1 total ~= 0.00911 - 0.00011 + 0.1207 ~= 0.12970 (< cap,
    #     so claim-1's worker does NOT in-worker-trip).
    #   SEQUENTIAL live: 0.10 + 0.00911 (claim-0) + 0.009 (claim-1 mirror+sentinel) = 0.11811 < cap,
    #     then + Judge 0.1207 -> 0.23881 > cap -> trips AT claim-1's Judge call.
    #   PARALLEL boundary: parent re-adds claim-0 -> 0.10911 ok; claim-1 -> 0.23881 > cap -> trips.
    #   Both report 0.23881. The tip on claim-1's LAST call is what makes the totals identical.
    n = 2
    usage = {(1, "judge"): dict(_BIG_JUDGE_USAGE)}

    def run_path(workers, sub_dir):
        monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", workers)
        monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.20)
        openrouter_client.reset_run_cost()
        openrouter_client._add_run_cost(0.10)  # near-cap generator pre-seed (shared accumulator).
        run_dir = tmp_path / sub_dir
        run_dir.mkdir()
        claims, ledger = _cost_claims(n)
        transport = _DelayedFakeTransport(usage_by_index_role=usage)
        with pytest.raises(BudgetExceededError):
            _run(transport, claims, run_dir=run_dir, ledger=ledger)
        return openrouter_client.current_run_cost()

    seq_total = run_path(1, "seq")
    par_total = run_path(2, "par")
    # Same accumulated spend at the trip on BOTH paths (deterministic — no floor noise).
    assert seq_total > 0.20 and par_total > 0.20
    assert seq_total == pytest.approx(par_total, rel=1e-9)


def test_single_claim_over_cap_trips_in_worker_fail_closed(monkeypatch, tmp_path):
    # The SECOND parallel enforcement point (honest documentation): when a SINGLE claim's own cost
    # exceeds the FULL cap, its worker trips LIVE inside RecordingTransport (the per-worker reset
    # context baselines at 0, so the claim's own spend alone crosses the cap) and raises
    # BudgetExceededError BEFORE returning a delta — the parent never re-adds it. This is
    # fail-closed and correct; we assert it RAISES but do NOT assert an equal parent total (the
    # parent counter stays at the pre-seed because the worker aborted before reduction).
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.05)
    openrouter_client.reset_run_cost()
    n = 2
    # claim-0's Judge alone (~$0.1207) exceeds the 0.05 cap -> its worker trips in-worker.
    usage = {(0, "judge"): dict(_BIG_JUDGE_USAGE)}
    claims, ledger = _cost_claims(n)
    transport = _DelayedFakeTransport(usage_by_index_role=usage)
    with pytest.raises(BudgetExceededError):
        _run(transport, claims, run_dir=tmp_path, ledger=ledger)


def test_parallel_cost_equals_sequential_cost_under_cap(monkeypatch, tmp_path):
    # No cap pressure: prove the TOTAL accounted spend is identical between the sequential and the
    # parallel paths (the parent re-adds exactly each worker's per-claim delta — no double count,
    # no drop). 3 claims, each Judge carries a modest usage.
    n = 3
    modest = {
        "prompt_tokens": 100,
        "completion_tokens": 100,
        "completion_tokens_details": {"reasoning_tokens": 1000},
    }
    usage = {(i, "judge"): dict(modest) for i in range(n)}

    def total_for(workers, sub_dir):
        monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", workers)
        monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 1000.0)
        openrouter_client.reset_run_cost()
        run_dir = tmp_path / sub_dir
        run_dir.mkdir()
        claims, ledger = _cost_claims(n)
        transport = _DelayedFakeTransport(usage_by_index_role=usage)
        _run(transport, claims, run_dir=run_dir, ledger=ledger)
        return openrouter_client.current_run_cost()

    seq_total = total_for(1, "seq")
    par_total = total_for(4, "par")
    assert seq_total > 0.0
    assert seq_total == pytest.approx(par_total, rel=1e-9)


# === Codex iter-2 P1.2 — the PARENT Path-B capture sink is visible inside workers ===============
class _CapturingFakeTransport:
    """Fake `RoleTransport` that emits a CAPTUREABLE verifier call exactly as the real transports
    do: it scopes the role via `pathB_capture.llm_role(request.role)` and calls
    `pathB_capture.capture_llm_call(...)` for EVERY role call. The capture only lands in the parent
    `_PATHB_SINK` if the worker runs under a context snapshot that was taken on the PARENT (P1.2);
    with `copy_context()` taken INSIDE the worker the sink is the worker's empty default (None) and
    capture no-ops, so the parent sink stays empty. Verdicts are fixed VERIFIED so the seam reduces
    cleanly; this test is about CAPTURE VISIBILITY, not verdict math.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.completions = 0

    def complete(self, request: RoleRequest) -> RoleResponse:
        with self._lock:
            self.completions += 1
        # Emit a captureable call THE SAME WAY the real OpenRouter/OpenAI-compatible transports do:
        # scope the role, then capture. A minimal served-identity raw response so the capture record
        # carries response_metadata (the M4 gate's served==pinned surface).
        with pathB_capture.llm_role(request.role):
            pathB_capture.capture_llm_call(
                role=request.role,
                messages=[{"role": "user", "content": request.prompt or ""}],
                raw_response={"provider": "FakeProvider", "model": request.model_slug},
            )

        if request.role == "mirror":
            if "pass2_input" in (request.params or {}):
                content_hash = request.params["pass2_input"]["content_hash"]
                return RoleResponse(
                    raw_text=json.dumps(
                        {"content_hash": content_hash, "classification": "supported"}
                    ),
                    served_model=request.model_slug,
                    usage=None,
                )
            idx = _DelayedFakeTransport._index_from_request(request)
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(f"doc-{idx}",))],
                usage=None,
            )
        if request.role == "sentinel":
            return RoleResponse(
                raw_text=_sentinel_raw_for_mode(request, grounded=True),
                served_model=request.model_slug,
                usage=None,
            )
        if request.role == "judge":
            return RoleResponse(
                raw_text="VERIFIED", served_model=request.model_slug, usage=None
            )
        raise AssertionError(f"unexpected role {request.role!r}")


def test_pathb_sink_visible_in_workers(monkeypatch, tmp_path):
    # P1.2: register a Path-B capture sink on the PARENT (as pathB_runner does), run the seam with
    # 4 workers + a fake transport that emits captureable verifier calls, and assert the PARENT sink
    # received ALL workers' captures. This FAILS with copy_context() taken INSIDE the worker (the
    # worker's empty default context has _SINK=None, so capture no-ops and the parent sink stays
    # empty), and PASSES once the snapshot is taken on the parent before submit.
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
    n = 4
    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
    transport = _CapturingFakeTransport()

    # Register the parent capture sink THE SAME WAY pathB_runner.gate_around_question does, and
    # always clear it so the contextvar never leaks into another test.
    pathB_capture.register_pathB_capture()
    try:
        result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)
        captured = pathB_capture.collected_calls()
    finally:
        pathB_capture.clear_pathB_capture()

    assert result.final_verdicts == {f"claim-{i}": "VERIFIED" for i in range(n)}
    # Every claim runs Mirror(x2) + Sentinel + Judge == 4 captureable calls -> 4 claims * 4 = 16.
    # The exact count proves NO worker's captures were lost to an isolated empty context.
    assert len(captured) == n * 4, (
        f"parent sink saw {len(captured)} captures, expected {n * 4}; a missing batch means a "
        f"worker ran under an empty context and capture no-oped (P1.2 regression)."
    )
    # All three verifier roles are present at the parent (capture visibility is per-role).
    roles_seen = {c["role"] for c in captured}
    assert roles_seen == {"mirror", "sentinel", "judge"}, roles_seen
    # Every captured call carries the served-identity metadata the M4 gate reads (proves the
    # capture pipeline ran end-to-end inside the worker, not just an empty append).
    assert all(c["response_metadata"].get("provider_name") == "FakeProvider" for c in captured)


# === Codex iter-2 P1.1 — a cumulative cap trip is BOUNDED to ~(workers) in-flight ===============
class _CountingCostTransport:
    """Fake `RoleTransport` that bills a FIXED cost on each claim's JUDGE call (the LAST call of the
    pipeline) and records WHICH claim indices actually started, so a test can prove that a cumulative
    cap trip stops further claims rather than running all N. Thread-safe; NEVER a socket.

    Each claim's Mirror PASS-1 (its FIRST call) sleeps `per_claim_delay` so workers process claims in
    bounded WAVES instead of racing the whole batch to completion before the parent re-adds any
    delta — without the delay a near-instant fake would let all N claims finish before the parent's
    cumulative cap check fires, defeating the in-flight-bound assertion.
    """

    def __init__(self, *, judge_usage: dict, per_claim_delay: float = 0.0) -> None:
        self._judge_usage = judge_usage
        self._delay = per_claim_delay
        self._lock = threading.Lock()
        self.started_indices: set[int] = set()
        self.completions = 0

    def complete(self, request: RoleRequest) -> RoleResponse:
        idx = _DelayedFakeTransport._index_from_request(request)
        with self._lock:
            self.completions += 1
            if idx is not None:
                self.started_indices.add(idx)

        if request.role == "mirror":
            if "pass2_input" in (request.params or {}):
                content_hash = request.params["pass2_input"]["content_hash"]
                return RoleResponse(
                    raw_text=json.dumps(
                        {"content_hash": content_hash, "classification": "supported"}
                    ),
                    served_model=request.model_slug,
                    usage=None,
                )
            # Pass-1 is the FIRST call of the claim -> sleep here so workers advance in bounded waves.
            if self._delay:
                time.sleep(self._delay)
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(f"doc-{idx}",))],
                usage=None,
            )
        if request.role == "sentinel":
            return RoleResponse(
                raw_text=_sentinel_raw_for_mode(request, grounded=True),
                served_model=request.model_slug,
                usage=None,
            )
        if request.role == "judge":
            return RoleResponse(
                raw_text="VERIFIED",
                served_model=request.model_slug,
                usage=dict(self._judge_usage),
            )
        raise AssertionError(f"unexpected role {request.role!r}")


def test_cap_trip_is_bounded_in_flight(monkeypatch, tmp_path):
    # P1.1: N claims, each individually UNDER the cap, but the CUMULATIVE spend crosses the cap after
    # a few claims. With the cap enforced DURING compute (parent re-adds each completed claim's delta
    # and re-checks immediately), a BudgetExceededError fires and the pool is shut down with
    # cancel_futures=True — so the number of claims that ACTUALLY RAN is bounded near the worker count
    # in-flight at the breach, NOT all N. With the OLD code (submit+drain ALL, then re-add in the
    # reduction) every one of the N claims would have run and spent before the cap tripped.
    workers = 2
    n = 12
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", workers)
    # Each claim's Judge bills ~$0.1207 (the _BIG_JUDGE_USAGE block). Cap 0.30 -> the cumulative
    # total crosses after claim #3's delta is re-added (3 * 0.1207 = 0.3621 > 0.30), so only a
    # SMALL prefix of the 12 claims should ever start.
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.30)
    openrouter_client.reset_run_cost()
    judge_usage = dict(_BIG_JUDGE_USAGE)
    claims, ledger = _cost_claims(n)
    # A small per-claim delay makes workers advance in bounded waves of `workers`, so the parent's
    # cumulative cap check fires BEFORE the whole batch of 12 finishes (a near-instant fake would let
    # all N complete first and defeat the in-flight bound).
    transport = _CountingCostTransport(judge_usage=judge_usage, per_claim_delay=0.05)

    with pytest.raises(BudgetExceededError):
        _run(transport, claims, run_dir=tmp_path, ledger=ledger)

    ran = len(transport.started_indices)
    # BOUNDED: each Judge bills ~$0.1207; the cumulative cap (0.30) crosses once the parent has
    # re-added ~3 claims' deltas (3 * 0.1207 = 0.3621 > 0.30). At the breach at most `workers` more
    # claims can be in flight, so `ran` is bounded near (3 + workers), NEVER all 12. The headline
    # assertion is `ran < n`: the OLD submit-and-drain-all code would have run every one of the 12.
    assert ran < n, f"cap trip ran {ran}/{n} claims — should be bounded near the worker count, not all N"
    assert ran <= 3 + 2 * workers, (
        f"cap trip ran {ran} claims; the cumulative cap crosses after ~3 claims and only a bounded "
        f"number more can be in-flight at the breach (bounded overspend, P1.1, workers={workers})."
    )
