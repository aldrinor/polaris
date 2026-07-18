# Lessons: Pipeline architecture, depth & parallel composition (the moat)

Canonical home: memory `project_single_context_window_moat_parallel_compose_2026_07_11.md`, `project_connected_hamster_wheels_beat_sota_2026_07_11.md`, `project_architecture_pivot_fsresearcher_sections_2026_07_10.md`.

The moat and depth strategy (competitors capped by one context window; POLARIS is section/basket-modular so depth is the SUM of all baskets rendered in parallel; chain of connected per-stage hamster wheels; SURGICAL re-wire not rewrite) lives canonically in the pointed memory files. This hub captures the concrete architecture-correctness rules mined from the bug log — the silent-failure classes that quietly break a modular, parallel pipeline.

## Declare every node-returned key in the state schema, and return it from the node even if you mutated in place

Whenever a LangGraph node produces a new field: (1) declare it in the ResearchState/TypedDict AND initialize it in `create_initial_state`; (2) return it in the node's result dict even if you also mutated state in place; (3) keep routing/conditional-edge functions strictly read-only. LangGraph silently discards any undeclared key during state merging with NO warning, and downstream nodes then read a default/zero and the whole run mis-gates.

Why: This is the single best-evidenced recurring root cause in the log. It repeatedly caused CRITICAL mis-gating (CASE_3 instead of CASE_1) because measured faithfulness never reached the finalize node. The failure is invisible in logs — the value is correct at the checkpoint and gone in the final state.

Evidence: `logs/bug_log.md` BUG-067/FIX-67 (ResearchState missing 4 auditor fields), BUG-081 (`most_bond_analysis` dropped, has an explicit "Lesson Learned"), BUG-084/FIX-051c (VerifiedClaim missing nli_score/cross_source_score), FIX-051b (mutated `state['evidence']` but did not return it), BUG-017/FIX-21 (`route_after_auditor` mutated state, discarded); also `state.py:311` docstring.

Recurrence: Recurring — 5+ distinct CRITICAL/FATAL occurrences across 2026-01 to 2026-02.

## Verify producer-before-consumer ordering for every enriched field, and grep for any field read but never assigned

An enrichment that runs AFTER its consumer, or a field that is read but never set anywhere, silently defaults to a constant (0.0 or 0.5) and turns a 20–25% scoring weight into a no-op with no error. Check ordering for every enriched field and treat any read-but-never-assigned field as a dead signal.

Why: A distinct, silent, recurring class that degrades quality without ever failing.

Evidence: `logs/bug_log.md` BUG-082/FIX-49 (SOTA-11 source confidence ran after tier assignment, 40% of Signal 2 always zero), BUG-083/FIX-50 (quote grounding ran after tier assignment, self-labeled "same class as BUG-082"), BUG-084/FIX-51 (`nli_self_check_score` never set, Signal 5 a constant 0.1 for all evidence).

Recurrence: Recurring — 3 consecutive occurrences, self-labeled "same class."

## Give every non-essential LLM-output schema field a sensible default, and fail LOUD on validation failure

Make every non-essential Pydantic/LLM-output field Optional with a sensible default (default='' or 0), and make the on-validation-failure path fail LOUD rather than silently substituting an empty or unmodified result. One field the LLM occasionally omits must not nuke the whole response.

Why: A required field the LLM sometimes omits caused whole structured responses to fail validation; the caller's null-handling then silently kept an empty or unmodified report and mis-gated to CASE_3. A single missing title/excerpt on 1 of 17 references destroyed a complete 930-word report.

Evidence: `logs/bug_log.md` BUG-024/FIX-28 (Citation title/excerpt required → whole FullReport rejected → empty report → CASE_3), BUG-016/FIX-20 (RevisedReport `sentences_revised` no default → silent keep-original, faithfulness stuck at 41%).

Recurrence: Recurring — multiple structured-output schemas hit this.

## Never record a failure path as status=ok — fail loud on any empty, stub, or swallowed-exception result

Any code path that can produce nothing, a blank/empty completion, a stub, or an exception MUST raise or set an explicit degraded/abort status. A phase that "ran but produced no verified output" is a fail-loud event, not an "ok." Do not let a blank stream, a paywall stub, or a swallowed validator exception be recorded as success.

Why: This is the single most-recurring defect class. When a failure quietly returns "ok," the pipeline ships a normal-looking body and every downstream gate trusts the green status, so the failure reaches the user invisibly. Fixing it once does not stop it — new instances appear in every campaign at different call sites.

Evidence: `beatboth_p1_codex_verdict.txt` CX-24 (quantified analysis `manifest.fired=False` yet the phase "ran"); I-arch-004 `A3_master_fix_list.md` F02 (blank stream content='' finish_reason=None logged status=ok), F07, F14 (paywall stubs + status=ok masking), F26 (validator exceptions swallowed, strict-mode fail-open), F27 (fail-soft ledger silently drops the gap disclosure).

Recurrence: Recurring across ~75 issue folders with a matching P0/P1 line; a dominant thread of the I-arch-004 32-fix campaign.

## Under parallel workers, make shared primitives per-loop / atomic / UUID-scoped, and run teardown on the timeout path

Never bind a module-global asyncio primitive to the first query's event loop — re-bind per loop. Reserve any shared budget/cost counter atomically BEFORE each call, not reconciled after. Scope artifact dirs by run UUID to avoid same-slug clobber. Close every browser context, daemon thread, subprocess, and client in a `finally` that ALSO fires on the outer-timeout/abandonment path, and never share a client whose lifecycle can close it before a later gate call.

Why: The 4-role verifier and per-section work run in parallel, so any shared state or unclosed resource surfaces as a RuntimeError, overspend, clobbered artifacts, leaked browsers, or a disabled final gate — non-deterministic and hard to reproduce.

Evidence: I-arch-004 F01/F16 (module-global `asyncio.Semaphore` bound to query-1's loop → RuntimeError on Q2–5), F22 (`PG_MAX_COST_PER_RUN` not hard under parallel 4-role → overspend), F17 (sync httpx + `time.sleep` in async); I-arch-001a P1.3 (same-slug artifact concurrency); `A_stab/codex_diff_audit.txt` (browser context / daemon thread not closed when the outer deadline fires); `beatboth` CX-03 (judge client closed before the D8 call disabled final adjudication).

Recurrence: Recurring across many folders (concurrency ~42, teardown ~46 with matching lines), spanning A_stab, I-arch-001, I-arch-004 and the beatboth runs.
