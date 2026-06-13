# Codex diff review — I-bench-veracity-003 18-blocker remediation (#1226–#1243)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this is
A single batched diff fixing 18 forensically-identified drb_72 pipeline blockers (GitHub #1226–#1243),
produced by 9 file-disjoint agents. Mission context: open up the generator's *source breadth* (drb_72
cites only ~21 of ~197 pool sources because the generator over-concentrates citations — one ~800-char
span cited 18–19×) WITHOUT relaxing any faithfulness gate. The fixes are the menu/telemetry/fail-loud
layer; strict_verify, the NLI entailment judge, the 4-role D8 audit, and provenance still re-verify
every sentence downstream.

## BINDING faithfulness constraint (verify it held)
NONE of these diffs may relax/weaken/bypass strict_verify (numeric + ≥2 content-word overlap), the NLI
entailment judge (PG_STRICT_VERIFY_ENTAILMENT=enforce), the 4-role D8 audit, or provenance/span
validation. Every behavioral change is either (a) env-gated DEFAULT-OFF so flag-unset == byte-identical,
or (b) a pure reliability/telemetry kill-switch (default-ON correct fix, env to revert) that cannot
change *which* output is verified — only how many already-selected fetches succeed, or honest counts.
On any failure the gates FAIL LOUD (raise / abort / typed error), never silently pass or fabricate.

## Test evidence (offline, this machine)
- 119/119 new blocker unit tests pass (`tests/polaris_graph/blockers/`).
- 206/206 existing tests for the touched modules pass — no regression. (One PRE-EXISTING collection
  error in `test_provenance_generator_entailment.py` from a `polaris_graph` vs `src.polaris_graph`
  import in an UNTOUCHED file — not caused by this diff.)
- Total 325 green.

## Diffs to review
- SOURCE diff (the faithfulness-critical part, your focus): `blocker_remediation_src_diff.patch` (11 files).
- FULL diff incl. tests: `blocker_remediation_diff.patch`.

## Per-blocker ledger — VERIFY each hunk against its claim. STATUS is my honest self-assessment; confirm or refute it.

### Fully fixed in code (verify correctness + faithfulness + default-OFF identity)
- **#1229** multi_section_generator.py `_augment_legacy_section_breadth`: off-topic augmentation. Env
  `PG_BREADTH_AUGMENT_MIN_OVERLAP` (default 2 == historical bar, clamped ≥2) + `PG_BREADTH_AUGMENT_REQUIRE_SECTION_OVERLAP`
  (default 0). Verify default-off selection is byte-identical and the bar can only TIGHTEN, never loosen below 2.
- **#1232** fact_dedup.py `apply_span_cite_cap`: per-span re-cite cap `PG_SPAN_PER_SOURCE_CITE_CAP`
  (default 0=off). Drop-only selection keyed on the `[#ev:id:start-end]` token; a sentence is droppable
  only when EVERY span it cites is saturated; nothing rewritten/fabricated. VERIFY: survivors are a strict
  verbatim subset; the local provenance regex mirrors provenance_generator (LAW VII — no cross-import);
  off==same-object identity.
- **#1233** multi_section_generator.py: breadth canary `PG_BREADTH_CANARY_MIN` (default 0). Only ever
  RAISES RuntimeError when achieved distinct-source breadth < floor; never fabricates. (The TARGET value
  itself is a runtime env knob, not in this diff.)
- **#1235** run_honest_sweep_r3.py: corpus-skew readiness gate fail-OPEN → under shared `PG_BENCHMARK_STRICT_GATES`
  (default 0) abort loudly on material tier deviation; keep disclosure. Verify off==identical.
- **#1236** completeness_checker.py + evaluator_gate.py: 0/0 vacuous pass → under `PG_BENCHMARK_STRICT_GATES`
  a not_applicable/empty-denominator completeness is NOT-READY (release_allowed=False). Verify off==identical
  and that a MEASURED fraction is unchanged in both states.
- **#1238** run_honest_sweep_r3.py: V30 Phase-2 broad-except silent legacy fallback → under strict gates
  re-raise unless `PG_V30_ALLOW_LEGACY_FALLBACK=1`; always log reason.
- **#1239** run_honest_sweep_r3.py: empty bibliography URLs → `PG_BIB_REQUIRE_LOCATOR` (default off);
  cited entry with blank URL/DOI resolved or emitted as non-cited gap.
- **#1242** run_honest_sweep_r3.py: tier-disclosure self-contradiction (Methods 11% vs Limitations 13%)
  → compute percentages ONCE; default-ON correctness with `PG_TIER_DISCLOSURE_SINGLE_SOURCE=0` revert.
- **#1228** evidence_selector.py: relevance-floor reported dropped=0 while cutting ~45% → honest drop
  count (default-ON, `PG_RELEVANCE_HONEST_DROP=0` revert) + `PG_RELEVANCE_PRESERVE_ANCHORS` (default off)
  marquee/required-entity floor exemption. Verify the floor default value is NOT changed in code and the
  preserve flag only ADDS an already-fetched row.
- **#1227** access_bypass.py (+ live_retriever.py): crawl4ai cross-loop semaphore EPIPE (~159 lost) →
  per-running-loop semaphore, kill-switch `PG_CRAWL4AI_PERLOOP_SEMAPHORE=0` reverts. Reliability only;
  must not change which URLs are fetched or any verification.
- **#1226** openrouter_role_transport.py: 4-role blank-verdict unbounded stall → bound blank retries
  (`PG_ROLE_BLANK_MAX_RETRIES` default 3, truncates the ladder) + cooperative wall-clock watchdog
  (`PG_ROLE_CALL_TIMEOUT_S`), kill-switch `PG_ROLE_BLANK_WATCHDOG=0`. CRITICAL: confirm it NEVER passes
  or fabricates an empty verdict — on exhaustion it re-raises the EXISTING fail-loud BlankVerdictError so
  the release stays HELD. (Operator also sets PG_FOUR_ROLE_REASONING_EFFORT=medium at runtime — config,
  not in this diff.)
- **#1241** provenance_generator.py: content-empty sentences counted as verified → exclude from numerator
  AND denominator, default-ON `PG_PROVENANCE_SKIP_EMPTY=0` revert. Verify it does not change which REAL
  sentences pass strict_verify.

### Partial in code — in-file half done, deeper root cause cross-file & LOGGED (verify I did NOT fake-close, and did NOT weaken a gate)
- **#1231** marquee anchors (Acemoglu-Restrepo, Eloundou) produce ZERO verified prose. In-file:
  `PG_BREADTH_MARQUEE_PRIORITY` floats anchor rows first in the augmentation menu. ROOT CAUSE is
  DOWNSTREAM: contract anchors arrive METADATA_ONLY with empty/paywalled `direct_quote` and hit the
  all-not_extractable gap-stub path in `contract_section_runner.py:374-387` — which CORRECTLY refuses to
  LLM-generate over an empty span (a faithfulness protection). Real fix = upstream Zyte fetch for paywalled
  anchor URLs (`required_entity_retrieval.py` fetch path; ZYTE_API_KEY). VERIFY: the empty-span gate was
  NOT weakened.
- **#1237** quantified_analysis.py: typed status {ok, declined_no_spec, empty_transport, parse_error}
  + bounded retry, kill-switch `PG_QUANTIFIED_TYPED_STATUS=0`. EMPTY_TRANSPORT is reserved-but-unreachable
  until the caller closure in run_honest_sweep_r3.py raises on a true transport miss instead of collapsing
  it to None (logged as cross_file_deferred). Verify the module-side typed status + retry are correct and
  never fabricate numbers (failure still returns (None, telem) fail-closed).
- **#1240** provenance_generator.py: malformed `[ev:...]` tokens (no `#`) silently dropped → canonicalize-
  if-valid OR count as malformed_dropped telemetry, kill-switch `PG_PROVENANCE_TOKEN_HONEST_DROP=0`. The
  SOURCE (fact_dedup REWRITE_SYSTEM_PROMPT teaching `[ev_X]`) is deferred. VERIFY: canonicalization only
  fixes the bracket format and the SAME full validation still runs — an out-of-bounds/invalid span STILL
  DROPS after the bracket fix (there are tests asserting this).

### Honestly NOT fixed in this diff (verify the defer is correct, not a hidden no-op)
- **#1230** "English-only" prompt CONSTRAINT leaking into the search query. The owning agent found this
  does NOT live in evidence_selector.py — it's in query_decomposer.py / planner.py — so it added NO flag
  here (no accidental no-op `PG_QUERY_STRIP_CONSTRAINTS`). Recorded as cross-file deferred. Test
  `test_g_no_constraint_strip_flag_introduced` asserts the absence. VERIFY the selector did not silently
  alter sub-query handling.

### Config-only (no code in this diff; set at A/B runtime)
- **#1233** raise PG_LEGACY_SECTION_BREADTH_TARGET, **#1234** PG_AGENTIC_BENCHMARK_URL_CAP, **#1243** distill
  concurrency. These are env knobs for the proof-run slate.

## Specific things to scrutinize (front-loaded so you verify, not hunt)
1. fact_dedup `apply_span_cite_cap`: does the call site still pass strings carrying `[#ev:...]` tokens
   (pre-resolve), not already-resolved `[N]` markers? If resolved, the cap is a silent no-op.
2. role transport: the watchdog default 3600s = 4×900s has near-zero margin over worst-case legitimate
   composition — confirm a healthy call is NOT aborted, and the abort path re-raises a typed error (HELD),
   never a synthesized APPROVE/verdict.
3. completeness/evaluator_gate: PG_BENCHMARK_STRICT_GATES is read in two modules via mirrored env helpers
   (LAW VII forbids cross-import). Confirm token sets match and a strict 0/0 maps to a HOLD, not a crash.
4. provenance: canonicalization MUTATES the working sentence string before verify — confirm that is the
   correct choke point and no caller depends on the pre-canonical text; confirm module-level telemetry
   counters are reset between runs.
5. quantified retry re-bills spec_provider — confirm it is exception-path-only and a decline is never retried.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
APPROVE iff zero P0 and zero P1. Default-OFF dormant code, honest cross-file defers, and the
config-only items are NOT defects. A real faithfulness-gate weakening, a fix that does not actually
do what its blocker claims, or a default-OFF path that is NOT byte-identical — those ARE P0/P1.
