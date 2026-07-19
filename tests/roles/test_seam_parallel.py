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

import src.polaris_graph.benchmark.benchmark_run_capture as pathB_capture
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
    FOUR_ROLE_SETTLED_VERDICTS_FILENAME,
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
        # Full decomposition contract (I-run11-004 brief-gate P1): supported needs a non-empty atoms
        # list + count, else the parser fails closed (bare/non-atomized supported).
        return ('{"verdict": "' + verdict + '", "unsupported_atoms": ' + n
                + ', "atoms": [{"atom": "x", "status": "' + verdict + '"}]}')
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


# === I-wire-007 (#1321) — the PARALLEL drain persists settled verdicts to the seam-preserve sidecar
def test_parallel_settle_writes_seam_preserve_sidecar(monkeypatch, tmp_path):
    """BEHAVIORAL (§-1.4): the parallel `_settle` drain must persist EACH settled claim's verdict to
    four_role_settled_verdicts.jsonl so a later outer-seam timeout can RECOVER the partials. Without
    this on-disk trail the orphaned worker's in-memory verdicts are lost on a seam wall."""
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 3)
    n = 4
    claims = [_claim(i, covers=[f"elem-{i}"]) for i in range(n)]
    ledger = CoverageLedger(required_element_ids=[f"elem-{i}" for i in range(n)])
    transport = _DelayedFakeTransport()

    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)

    sidecar = tmp_path / FOUR_ROLE_SETTLED_VERDICTS_FILENAME
    assert sidecar.exists(), "the parallel drain must persist the seam-preserve settled-verdict sidecar"
    rows = [json.loads(ln) for ln in sidecar.read_text(encoding="utf-8").splitlines() if ln.strip()]
    # EVERY settled claim is on disk with its verdict + covered ids (recoverable on a seam timeout).
    by_id = {r["claim_id"]: r for r in rows}
    assert set(by_id) == {f"claim-{i}" for i in range(n)}, "all settled claims persisted to the sidecar"
    for i in range(n):
        assert by_id[f"claim-{i}"]["verdict"] == result.final_verdicts[f"claim-{i}"]
        assert by_id[f"claim-{i}"]["covered_element_ids"] == [f"elem-{i}"]


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


def test_sequential_path_still_overshoots_cap_by_one_call(monkeypatch, tmp_path):
    # F22 (#1255, h4): the SEQUENTIAL path is UNCHANGED and byte-identical — it keeps the live
    # per-call RecordingTransport budget, which is soft-by-ONE-call (the breaching call spends, the
    # NEXT check_run_budget(0) raises). This documents the accepted sequential semantics so the
    # contrast with the now-HARD parallel path (next test) is explicit: F22 hardens ONLY parallel.
    #   cap = 0.20; parent pre-seed 0.10; the LAST claim's JUDGE carries the tipping usage (~$0.1207).
    #   live: 0.10 + claim-0 (~0.00911) + claim-1 mirror+sentinel (~0.009) = ~0.11811 < cap,
    #         then + Judge 0.1207 -> ~0.23881 > cap -> trips AT claim-1's Judge call (spend already in).
    n = 2
    usage = {(1, "judge"): dict(_BIG_JUDGE_USAGE)}
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 1)  # sequential fast path.
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.20)
    openrouter_client.reset_run_cost()
    openrouter_client._add_run_cost(0.10)  # near-cap generator pre-seed (shared accumulator).
    claims, ledger = _cost_claims(n)
    transport = _DelayedFakeTransport(usage_by_index_role=usage)
    with pytest.raises(BudgetExceededError):
        _run(transport, claims, run_dir=tmp_path, ledger=ledger)
    # Sequential overshoots by the breaching call (the spend was billed, then the next check raised).
    assert openrouter_client.current_run_cost() > 0.20


class _ConcurrencyTrackingTransport:
    """Thread-safe fake that records the MAX number of claims whose pipeline ran CONCURRENTLY.

    Each claim's Mirror PASS-1 (its first call) increments a live in-flight counter, sleeps so several
    claims would overlap if admitted together, then decrements — so `max_concurrent` captures the peak
    overlap. Used to prove the F22 reservation SERIALIZES admission down to what the cap affords (the
    mechanism that makes the cap a HARD ceiling), regardless of `_CLAIM_WORKERS`. Verdicts fixed
    VERIFIED; NEVER a socket.
    """

    def __init__(self, *, overlap_delay: float = 0.05) -> None:
        self._delay = overlap_delay
        self._lock = threading.Lock()
        self._live = 0
        self.max_concurrent = 0
        self.completions = 0

    def complete(self, request: RoleRequest) -> RoleResponse:
        with self._lock:
            self.completions += 1
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
            with self._lock:
                self._live += 1
                self.max_concurrent = max(self.max_concurrent, self._live)
            try:
                time.sleep(self._delay)  # hold the claim "in flight" so overlap is observable.
            finally:
                with self._lock:
                    self._live -= 1
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


def test_parallel_reservation_is_a_HARD_cap_serializes_to_what_cap_affords(monkeypatch, tmp_path):
    # F22 (#1255, h4) HEADLINE: under the PARALLEL 4-role path the atomic budget RESERVATION makes
    # PG_MAX_COST_PER_RUN a HARD ceiling. The invariant is "settled + reserved never exceeds the cap":
    # because anticipated >= actual (proven by the upper-bound tests), if the parent never lets
    # settled + reserved exceed the cap then the cumulative ACTUAL spend can never exceed it either.
    # We prove the invariant DIRECTLY by its observable consequence: when the cap affords only K
    # claims' reservations at once, AT MOST K claims ever run CONCURRENTLY — even with _CLAIM_WORKERS
    # far larger. The reservation throttles admission to the cap; without it (legacy) all n would run
    # at once. anticipated is from the SAME prod function (genuineness — not a test-known constant).
    per_claim = sweep_integration._anticipated_claim_cost(_MODEL_SLUGS)
    assert per_claim > 0.0
    affordable_k = 2
    n = 8
    # Cap fits EXACTLY `affordable_k` reservations (a sliver under k+1 so the (k+1)th cannot be
    # admitted while k are in flight). Workers are set HIGH (n) so ONLY the reservation — not the pool
    # size — limits concurrency.
    cap = per_claim * affordable_k + per_claim * 0.5
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", n)
    monkeypatch.setattr(sweep_integration, "_BUDGET_RESERVE_ENABLED", True)
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", cap)
    openrouter_client.reset_run_cost()
    claims, ledger = _cost_claims(n)
    transport = _ConcurrencyTrackingTransport(overlap_delay=0.05)

    # All claims FIT (tiny actuals release the reservation on settle), so the run COMPLETES — the cap
    # never blocks because the run genuinely fits; it only THROTTLES concurrency.
    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)

    assert result.final_verdicts == {f"claim-{i}": "VERIFIED" for i in range(n)}
    # HARD INVARIANT (observable): at most `affordable_k` claims ran at once — the reservation held
    # settled + reserved <= cap by THROTTLING admission. With the pool size = n and NO reservation,
    # max_concurrent would be n (all claims racing) and the cap could be overshot.
    assert transport.max_concurrent <= affordable_k, (
        f"max_concurrent={transport.max_concurrent} > affordable_k={affordable_k}: the reservation "
        f"did NOT throttle admission to what the cap affords (hard-cap invariant broken)."
    )
    # And the run never overshot the cap.
    assert openrouter_client.current_run_cost() <= cap


def test_parallel_reservation_legacy_path_runs_all_claims_concurrently(monkeypatch, tmp_path):
    # CONTRAST: with the F22 reservation OFF (legacy), the SAME tight cap does NOT throttle concurrency
    # — all n claims race at once (pool size n), which is exactly how the pre-F22 path could overshoot
    # the cap. This pins that the throttling above is the reservation, not some other limiter.
    n = 8
    per_claim = sweep_integration._anticipated_claim_cost(_MODEL_SLUGS)
    cap = per_claim * 2 + per_claim * 0.5  # same tight cap as the hard-cap test.
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", n)
    monkeypatch.setattr(sweep_integration, "_BUDGET_RESERVE_ENABLED", False)  # legacy path.
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", cap)
    openrouter_client.reset_run_cost()
    claims, ledger = _cost_claims(n)
    transport = _ConcurrencyTrackingTransport(overlap_delay=0.05)
    # Tiny actuals (usage=None) -> the legacy reconcile-on-completion never trips the cap, so the run
    # completes — but with ALL n claims racing concurrently (no admission throttle).
    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)
    assert result.final_verdicts == {f"claim-{i}": "VERIFIED" for i in range(n)}
    # Legacy: concurrency is bounded only by the pool size (n), NOT by the cap -> all n overlap.
    assert transport.max_concurrent == n, (
        f"legacy max_concurrent={transport.max_concurrent} != n={n}: the legacy path should run all "
        f"claims concurrently (no reservation throttle) — this is the regime F22 hardens."
    )


def test_parallel_reservation_admits_all_when_headroom(monkeypatch, tmp_path):
    # F22: reservation must NOT starve a run that genuinely fits — with ample cap, every claim is
    # admitted and the run completes (no spurious BudgetExceededError). Guards against an
    # over-conservative bound silently blocking legitimate parallel work.
    n = 4
    per_claim = sweep_integration._anticipated_claim_cost(_MODEL_SLUGS)
    cap = per_claim * (n + 2)  # comfortably fits all n reservations at once.
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
    monkeypatch.setattr(sweep_integration, "_BUDGET_RESERVE_ENABLED", True)
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", cap)
    openrouter_client.reset_run_cost()
    claims, ledger = _cost_claims(n)
    transport = _DelayedFakeTransport()
    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)
    assert result.final_verdicts == {f"claim-{i}": "VERIFIED" for i in range(n)}
    # Actual spend is tiny (floored usage=None) and well under the cap — reservation released to
    # actual on each settle, never an overshoot.
    assert 0.0 < openrouter_client.current_run_cost() < cap


def test_parallel_reservation_off_reverts_to_bounded_overshoot(monkeypatch, tmp_path):
    # F22 flag OFF (PG_FOUR_ROLE_BUDGET_RESERVE=0): the parallel path reverts to the pre-F22
    # submit-all + reconcile-on-completion behaviour — bounded overshoot, NOT a hard cap. This proves
    # the new hard cap is gated and the OFF path is byte-equivalent to the prior code: the cumulative
    # spend OVERSHOOTS the cap (the breaching deltas were already spent before the cap re-check).
    #   cap = 0.20; pre-seed 0.10; claim-1's JUDGE tips (~$0.1207) -> parent re-adds and trips,
    #   AFTER the spend landed -> current_run_cost() > cap (overshoot).
    n = 2
    usage = {(1, "judge"): dict(_BIG_JUDGE_USAGE)}
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 2)
    monkeypatch.setattr(sweep_integration, "_BUDGET_RESERVE_ENABLED", False)  # legacy path.
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.20)
    openrouter_client.reset_run_cost()
    openrouter_client._add_run_cost(0.10)
    claims, ledger = _cost_claims(n)
    transport = _DelayedFakeTransport(usage_by_index_role=usage)
    with pytest.raises(BudgetExceededError):
        _run(transport, claims, run_dir=tmp_path, ledger=ledger)
    # OFF path overshoots (the breaching call's spend is in the counter before the cap re-check).
    assert openrouter_client.current_run_cost() > 0.20


def test_single_claim_over_cap_blocked_pre_spend(monkeypatch, tmp_path):
    # F22: when even a SINGLE claim's anticipated reservation exceeds the FULL cap, admission control
    # blocks it PRE-SPEND with BudgetExceededError (no worker is ever submitted for it) — fail loud,
    # no silent thin (§-1.3). (Pre-F22 this tripped LIVE inside the worker AFTER the claim's own spend
    # crossed its reset-context cap; with reservation the block is now genuinely pre-spend.)
    per_claim = sweep_integration._anticipated_claim_cost(_MODEL_SLUGS)
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 4)
    monkeypatch.setattr(sweep_integration, "_BUDGET_RESERVE_ENABLED", True)
    # Cap BELOW one claim's anticipated reservation -> the very first claim cannot be admitted.
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", per_claim / 2.0)
    openrouter_client.reset_run_cost()
    n = 2
    claims, ledger = _cost_claims(n)
    transport = _DelayedFakeTransport()
    with pytest.raises(BudgetExceededError):
        _run(transport, claims, run_dir=tmp_path, ledger=ledger)
    # Nothing was ever admitted -> no verifier spend landed on the counter (pre-spend block).
    assert openrouter_client.current_run_cost() == pytest.approx(0.0)


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
    # P1.1 (LEGACY path, PG_FOUR_ROLE_BUDGET_RESERVE=0): N claims, each individually UNDER the cap, but
    # the CUMULATIVE spend crosses the cap after a few claims. With the legacy cap enforced DURING
    # compute (parent re-adds each completed claim's delta and re-checks immediately), a
    # BudgetExceededError fires and the pool is shut down with cancel_futures=True — so the number of
    # claims that ACTUALLY RAN is bounded near the worker count in-flight at the breach, NOT all N.
    # With the OLDER code (submit+drain ALL, then re-add in the reduction) every one of the N claims
    # would have run and spent before the cap tripped. NOTE: this is the bounded-OVERSHOOT regime; the
    # F22 reservation path (default ON) blocks pre-spend instead (a HARD cap) — see the F22 tests above.
    # This test pins the OFF-path regression so the legacy behaviour stays intact.
    workers = 2
    n = 12
    monkeypatch.setattr(sweep_integration, "_BUDGET_RESERVE_ENABLED", False)
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


# === I-ready-017 FX-08b (#1113): claim-level dedup + determinism knobs ==========================
def _dup_claim(claim_id: str, *, input_idx: int, covers=None) -> FourRoleClaim:
    """A claim with an explicit claim_id but the SAME pipeline INPUT as _claim(input_idx)
    (identical claim_text + evidence + severity + s0). Two _dup_claims with the same input_idx
    but different claim_id share ONE dedup key (the key excludes claim_id + covered_element_ids)."""
    return FourRoleClaim(
        claim_id=claim_id,
        claim_text=f"The dose is {input_idx}.0 mg. [[CLAIMIDX={input_idx}]]",
        evidence_documents=[
            EvidenceDocument(
                doc_id=f"doc-{input_idx}",
                text=f"The trial reported a {input_idx}.0 mg dose. [[CLAIMIDX={input_idx}]]",
            )
        ],
        severity="S0",
        s0_categories=["contraindications"],
        covered_element_ids=covers if covers is not None else [f"elem-{input_idx}"],
    )


def test_claim_dedup_runs_pipeline_once_and_fans_verdict(monkeypatch, tmp_path):
    # Two byte-identical-INPUT claims, different claim_id. Dedup ON (default): the pipeline runs
    # ONCE (4 role calls, not 8) and BOTH claims get the SAME final_verdict (the determinism
    # guarantee — they can never SPLIT VERIFIED/UNSUPPORTED).
    monkeypatch.setenv("PG_FOUR_ROLE_CLAIM_DEDUP", "1")
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 1)
    claims = [_dup_claim("claim-a", input_idx=0), _dup_claim("claim-b", input_idx=0)]
    ledger = CoverageLedger(required_element_ids=["elem-0"])
    transport = _DelayedFakeTransport(judge_verdict_by_index={0: "VERIFIED"})

    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)

    # Pipeline invoked ONCE (mirror x2 + sentinel + judge == 4), NOT twice (8).
    assert transport.completions == 4, transport.completions
    # Both claim_ids present, IDENTICAL verdict (fan-out under each claim's own id).
    assert result.final_verdicts == {"claim-a": "VERIFIED", "claim-b": "VERIFIED"}
    # Audit trail NOT inflated: role_call_log has exactly one claim's worth of rows, and the
    # duplicate (records=[]) contributes none.
    log = _read_role_call_log(tmp_path)
    assert len(log) == 4, log
    assert {e["claim_id"] for e in log} == {"claim-a"}, "duplicate must not emit phantom call records"


def test_claim_dedup_disabled_runs_each(monkeypatch, tmp_path):
    # Flag OFF -> byte-identical-to-pre-fix: both claims run independently (8 calls).
    monkeypatch.setenv("PG_FOUR_ROLE_CLAIM_DEDUP", "0")
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 1)
    claims = [_dup_claim("claim-a", input_idx=0), _dup_claim("claim-b", input_idx=0)]
    ledger = CoverageLedger(required_element_ids=["elem-0"])
    transport = _DelayedFakeTransport(judge_verdict_by_index={0: "VERIFIED"})

    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)

    assert transport.completions == 8, transport.completions
    assert result.final_verdicts == {"claim-a": "VERIFIED", "claim-b": "VERIFIED"}


def test_distinct_claims_are_not_deduped(monkeypatch, tmp_path):
    # DIFFERENT pipeline input (idx 0 vs 1) -> different dedup keys -> BOTH run (no false collision).
    # This is the faithfulness guard: two genuinely-different claims must never share one verdict.
    monkeypatch.setenv("PG_FOUR_ROLE_CLAIM_DEDUP", "1")
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 1)
    claims = [_claim(0), _claim(1)]
    ledger = CoverageLedger(required_element_ids=["elem-0", "elem-1"])
    transport = _DelayedFakeTransport(
        judge_verdict_by_index={0: "VERIFIED", 1: "UNSUPPORTED"},
    )

    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)

    assert transport.completions == 8, transport.completions
    # Distinct claims keep their distinct verdicts (NOT collapsed).
    assert result.final_verdicts == {"claim-0": "VERIFIED", "claim-1": "UNSUPPORTED"}


def test_dedup_fan_out_credits_coverage_per_claim(monkeypatch, tmp_path):
    # Two identical-INPUT claims differing ONLY in claim_id + covered_element_ids still DEDUP
    # (covered_element_ids is not pipeline input), and BOTH elements are credited on the shared
    # VERIFIED verdict (per-claim coverage fan-out).
    monkeypatch.setenv("PG_FOUR_ROLE_CLAIM_DEDUP", "1")
    monkeypatch.setattr(sweep_integration, "_CLAIM_WORKERS", 1)
    claims = [
        _dup_claim("claim-a", input_idx=0, covers=["elem-a"]),
        _dup_claim("claim-b", input_idx=0, covers=["elem-b"]),
    ]
    ledger = CoverageLedger(required_element_ids=["elem-a", "elem-b"])
    transport = _DelayedFakeTransport(judge_verdict_by_index={0: "VERIFIED"})

    result = _run(transport, claims, run_dir=tmp_path, ledger=ledger)

    assert transport.completions == 4
    assert result.final_verdicts == {"claim-a": "VERIFIED", "claim-b": "VERIFIED"}
    # Both elements covered (each claim credits its OWN covered_element_ids on the shared VERIFIED
    # verdict) -> full coverage despite the single deduped pipeline run.
    assert result.coverage_fraction == pytest.approx(1.0), result.coverage_fraction


def test_build_openrouter_body_temperature_zero_and_seed_optin(monkeypatch):
    # FX-08b determinism knobs: temperature=0 always (safe under require_parameters); seed OPT-IN.
    from src.polaris_graph.roles.openrouter_role_transport import _build_openrouter_body
    from src.polaris_graph.roles.role_transport import RoleRequest

    req = RoleRequest(role="judge", model_slug="qwen/qwen3.6-35b-a3b",
                      prompt="claim + evidence", params={})
    monkeypatch.delenv("PG_VERIFIER_SEED", raising=False)
    monkeypatch.delenv("PG_VERIFIER_TEMPERATURE", raising=False)
    body = _build_openrouter_body(req, "qwen/qwen3.6-35b-a3b", [{"role": "user", "content": "x"}])
    assert body["temperature"] == 0.0
    assert "seed" not in body, "seed must be opt-in (require_parameters routing safety)"

    monkeypatch.setenv("PG_VERIFIER_SEED", "42")
    body2 = _build_openrouter_body(req, "qwen/qwen3.6-35b-a3b", [{"role": "user", "content": "x"}])
    assert body2["seed"] == 42
