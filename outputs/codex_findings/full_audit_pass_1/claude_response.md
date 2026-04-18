---
response_to: outputs/codex_findings/full_audit_pass_1/findings.md
status: scoping_accepted_no_fixes_yet
blockers: 3
mediums: 8
minors: 1
disputes: 0
---

# Claude response — full audit scoping pass 1

Codex's scoping pass completed with `verdict: PRIORITIZED`. All
findings accepted; zero disputes.

The three blockers are design-level, not code-level, and they validate
the user's instinct that the narrow 5-round B-1..B-5 audit missed
things. Summary:

## B-100 (intake_scope, blocker): scope gate never rejects

Codex is correct. `scope_gate.py` sets `needs_user_review=True` but
has no rejection branch, and `run_honest_sweep_r3.py:288-317`
acknowledges the flag then proceeds anyway. The documented
`abort_scope_rejected` status is unreachable.

This is exactly the kind of silent-degradation LAW II was supposed
to prevent. The documentation said the status existed; Codex proved
no code path emits it.

## B-101 (orchestration, blocker): success manifest lacks `status`

Codex is correct. `scripts/run_honest_sweep_r3.py:851-907` builds
the success manifest without a `"status"` key. Status lives only in
`summary["status"]` at `:915-929`. Meanwhile, abort manifests DO
include `"status"` (correctly).

The `docs/pipeline_audit_context/03_json_contracts.md` I wrote said
`manifest.status` is authoritative — that's a lie about the actual
code. I documented an aspiration, not reality. Codex caught it.

Also: the orchestrator uses a SEPARATE summary-only taxonomy
(`ok`, `ok_thin_corpus`, `warn_rule_checks`) that doesn't match the
`success | abort_* | error_*` taxonomy documented in the README
I just rewrote.

## B-102 (pipeline_b_parity, blocker): UI production path un-hardened

Codex is correct. The Docker-default path (`live_server.py` → v1/v2/v3)
has ZERO matches for `strict_verify | sanitize_evidence_text |
corpus_approval | abort_no_verified_sections`. The entire 5-round
B-1..B-5 hardening is inapplicable to users hitting the UI.

This was already flagged in `docs/todo_list.md` and
`05_known_failure_modes.md` as "A1: Pipeline-B parity gap" — Codex
confirmed and correctly classified it as a blocker, not a medium.

## Medium findings (8) — accepted, deferred to deep-dives

- **M-201 retrieval_tiering**: gate sees 20 sources, generator sees
  4 (unbalanced truncation). Certification diverges from synthesis.
- **M-202 contradictions**: hard-coded obesity/cardiometabolic
  predicates, misses almost all clinical/policy/DD contradictions.
- **M-203 generation**: empty outline silently falls back to one
  generic "Efficacy" section; no abort signal.
- **M-204 strict_verify**: Limitations paragraph bypasses
  `verify_sentence_provenance` entirely; telemetry claims
  un-verified at the sentence level.
- **M-205 evaluator**: Qwen judge sees only report text, not
  evidence pool; `needs_revision` verdict is advisory, doesn't
  block success.
- **M-206 observability**: cost ledger is global (`logs/pg_cost_ledger.jsonl`)
  not per-run-dir; hard to correlate a run to its cost stream.
- **M-207 testing**: no tests assert success-manifest contract;
  the B-101 contract drift would not be caught by current suite.
- **M-208 frozen_c_disposition**: broken CLI entrypoint still
  advertised; retire/repair/leave decision still pending.

## Minor findings (1) — accepted

- **N-301 budget_cost attribution**: generator/judge clients not
  instantiated with session ID, so `pg_cost_ledger.jsonl` entries
  can't be joined per-run.

## No disputes

Everything Codex surfaced maps to real code positions I can verify.
Two of the three blockers (B-100, B-101) are things I personally
wrote documentation for and got wrong — the scoping pass caught me
claiming things are true that the code doesn't implement.

## Recommended next step

Codex proposed this deep-dive order:

```
1. orchestration          (B-101 manifest contract)
2. pipeline_b_parity      (B-102 UI un-hardened)
3. intake_scope           (B-100 unreachable abort status)
4. generation             (M-203 outline collapse)
5. evaluator              (M-205 advisory vs gating)
6. retrieval_tiering      (M-201 gate/generator divergence)
7. contradictions         (M-202 narrow predicate list)
8. observability          (M-206 per-run vs global ledger)
9. testing                (M-207 contract coverage)
10. strict_verify         (M-204 limitations bypass — light touch)
11. budget_cost           (N-301 session ID — light touch)
12. frozen_c_disposition  (M-208 retire decision — user-facing)
```

Each deep-dive round would be a scoped brief with:
- Concrete reproducers
- Code-level recommendations
- New regression tests if the issue is fixable without architectural changes
- Clear retire/redesign signals if the issue is architectural

At round-1..5 cadence (~3-6 min of Codex + 30-40 min of Claude
addressing per round), the full deep-dive sweep is ~8-12 hours of
work across 12 rounds.

## What Claude is NOT doing in this pass

- No code fixes (per the scoping-pass brief)
- No deep-dive launched yet (awaiting user direction)
- No test additions (deep-dive territory)

The scoping pass is a risk register. The user's ABCD directive was
"launch the audit"; the audit has launched and produced findings.
Whether to proceed with deep-dive rounds 1-12 is a separate scope
decision for the user.
