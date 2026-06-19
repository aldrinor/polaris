HARD ITERATION CAP: 3 per document. This is iter 1 of 3.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 3 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings.
- If you detect "I'm holding back a P1 to surface next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

FRONTIER-TECH MANDATE: judge only against 2025-2026 frontier practice; do not grandfather an outdated
pattern. The faithfulness engine (strict_verify / NLI entailment / span-grounding) is the proven crown
jewel — it is NEVER relaxed; flag any change that would.

# Codex diff review — I-arch-011 FIX-B (verbatim-skip) + FIX-C (parallel verify) — the run-#6 enrichment-verify "freeze"

Review the patch FILE (static only, do NOT run pytest):

    .codex/iarch011_campaign/fixbc_diff.patch   (workdir C:/POLARIS read-only — cat/grep surrounding code as needed)

## THE DIAGNOSIS THIS FIX RESTS ON (verify the reasoning, not just the diff)
Run #6 (F2a, the 794->9 collapse fix) PROVED breadth restoration — 737 sources surfaced into the
baskets, faithful (5-reader forensic, no fabrication) — then HUNG ~13 min at the FINAL verify of the
737-source breadth-ENRICHMENT section and never rendered. The runbook called it a per-call entailment
DEADLOCK (a wedged ssl.read whose 45s total-deadline "never fired"). **That diagnosis was wrong, and
the fix does NOT build on it.** Evidence:
 1. `scripts/iarch011_entailment_deadline_repro.py` points the REAL `_EntailmentJudge` at a local
    trickle/wedge server: `_post_with_total_deadline` raised TimeoutError at EXACTLY the deadline (5.0s),
    `judge()` bounded at 2x (10.2s) then emitted the fail-closed sentinel, a 2nd call also bounded — NO
    deadlock, NO cross-call poison. `concurrent.futures.Future.result(timeout)` is a condition-variable
    timed wait — transport-agnostic, so a worker in `ssl.read` cannot change when it wakes.
 2. ROOT CAUSE: `provenance_generator._parallel_verify_workers()` (the I-arch-006 fix#19 bounded-parallel
    findings verify) reads `PG_PARALLEL_VERIFY`, default 1 = SERIAL — and the run_gate_b slate NEVER set
    it. So the 737-source section verified its ~2200 sentence-units SERIALLY. Even at a healthy ~6s/call
    that is ~3.7h for ONE section -> blows the run wall, looks frozen. The faulthandler snapshot (main at
    `result()`, worker at `ssl.read`) is exactly what a serial loop mid-call looks like.

## THE FIX (3 changes; faithfulness NEVER relaxed)

**FIX-B — `clinical_generator/strict_verify.py` (new shared helper) + 2 call sites
(`strict_verify.py:~289`, `provenance_generator.py:~2056`).** The breadth-enrichment section
(`weighted_enrichment.build_verified_span_draft`) renders each source's OWN verbatim sentence-units
(`split_into_sentences(direct_quote)`), each bound by `_rewrite_draft_with_spans` to a span that is a
window of that SAME `direct_quote`. So the unit appears VERBATIM inside its span — the LLM entailment
6th-check is asked a question whose answer is ENTAILED by IDENTITY. `is_trivial_verbatim_entailment`
returns True (skip the LLM, verdict=("ENTAILED","verbatim_substring_of_span")) iff the
whitespace-normalized sentence is a SENTENCE-BOUNDARY-ALIGNED substring of the span AND >= 40 chars
(== `_MIN_UNIT_CHARS`); ANY non-match returns False -> the REAL judge runs (gate NEVER disabled).
This removes most of the ~2200 redundant enrichment LLM calls — the keystone that lets the section finish.

**FIX-C — `scripts/dr_benchmark/run_gate_b.py` slate.** Add `"PG_PARALLEL_VERIFY": "16"` so the
existing fix#19 bounded-parallel verify actually engages (was unset -> serial). Overlaps the residual
real-judge calls FIX-B could not skip.

**(provider stability — NOT in this diff)**: the launch env already sets `PG_ROLE_ALLOW_FALLBACKS=1`,
which free-routes glm-5.1 to its fastest provider (the slate's `PG_JUDGE_PROVIDER_ROTATE=1` is inert
under free-route). No change needed; flagged for context.

## THE FAITHFULNESS ARGUMENT FOR FIX-B (scrutinize this hardest — it touches check (f))
NOT a relaxation, for THREE independent reasons:
 1. Every OTHER strict_verify check (token validity, span-in-bounds, every sentence decimal present in
    the span, >=2 content-word overlap) has ALREADY run and still binds — FIX-B only short-circuits the
    LLM call inside check (f), and only when the sentence is literally present in the span.
 2. BOUNDARY ALIGNMENT kills the negation-fragment edge: the match must begin at span-start OR just after
    a sentence terminator (.!?…) AND end at span-end OR just before one. So the matched text is a COMPLETE
    assertion the span makes — never a sub-clause lifted out of a negating context. Concretely: a span
    "found no evidence that the drug works" does NOT trivially-entail a bare fragment "the drug works"
    (the fragment is preceded by "that ", not a terminator -> False -> real judge). A mid-clause "X" in
    "X and causes harm" is followed by " and" not a terminator -> False -> real judge. (Both proven in
    the offline helper test embedded in the harness control.)
 3. A short fragment (< 40 chars) never qualifies.
 The verdict is IDENTICAL to what the judge returns on a verbatim-present complete sentence (ENTAILED),
 so faithfulness is verdict-NEUTRAL (it removes judge flakiness on a definitionally-true case, never
 admits an unsupported claim). LAW VI: env-gated `PG_ENTAILMENT_VERBATIM_SKIP` (default on), telemetry-
 counted (`verbatim_skip_telemetry()`) so a behavioral harness PROVES it fired AND that non-verbatim
 units still judged.

## BEHAVIORAL PROOF (offline, banked drb_78 corpus, ZERO network)
`scripts/iarch011_enforce_breadth_preflight.py` drives the EXACT production path
(build_verified_span_draft -> _rewrite_draft_with_spans -> strict_verify) under
PG_STRICT_VERIFY_ENTAILMENT=ENFORCE + FIX-B on + a STUB judge that DROPS every residual (non-verbatim)
unit. So `report.total_kept` counts ONLY units that clear every mechanical check AND pass FIX-B's
identity entailment = a GUARANTEED LOWER BOUND on the production enforce-path cited count (the real
glm-5.1 judge can only ADD by passing residual). Result: <<HARNESS_NUMBERS_HERE>>. A control asserts a
deliberately NON-substring sentence STILL routes to the judge (gate alive).

## YOUR JOB
A. 3-PRONG: does FIX-B (1) relax check (f) / any binding gate? (2) grandfather an outdated pattern?
   (3) add a cap/floor/throttle/hard-filter or WRONG-MERGE non-same claims? Confirm it adds none —
   specifically confirm the boundary-alignment makes the skip verdict-equivalent to the judge on a
   verbatim complete sentence, and that EVERY non-match (paraphrase, negation-fragment, mid-clause,
   sub-40-char, non-substring) falls through to the REAL judge.
B. Confirm FIX-B's normalization cannot create a FALSE verbatim-match that the judge would have failed
   (i.e. the negation/context edges are actually closed by the boundary check, not just claimed).
C. Confirm FIX-C is faithfulness-neutral: the parallel path copies the parent contextvars context and
   `map` preserves order, so kept/dropped is byte-identical to the serial loop (concurrency = timing,
   not verdicts); a worker exception still propagates fail-loud.
D. Any NEW P0/P1 introduced (e.g. a residual-judge path that no longer runs, a telemetry race that
   could mask a no-op, an env default that silently disables the gate).

## OUTPUT SCHEMA (return EXACTLY this; last `verdict:` line is parsed)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
