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
            score = "no" if grounded else "yes"
            return RoleResponse(
                raw_text=f"<score>{score}</score>",
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
