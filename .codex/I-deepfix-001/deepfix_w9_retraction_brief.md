HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Review iter 3: I-deepfix-001 (#1344) — retraction gate + W9 consolidate-keep-all + W9 GRADUATION in the spend gate

FRONTIER-TECH MANDATE: judge only against current best practice; do not grandfather.

The diff is `.codex/I-deepfix-001/deepfix_w9_retraction_diff.patch` (read it from the repo). Tests: 18 retraction + 8 W9 + 28 purity-preflight gates = 54, all PASS. All files compile.

## Convergence so far
- iter-1 P0 (retraction bypassed by quantified analysis): FIXED at the run-level seam. iter-2 confirmed zero P0.
- iter-2 returned zero P0, one P1 (disclosure completeness for an M-52-pulled retracted row), two P2.

## What changed since iter 2 (each iter-2 finding addressed)
### iter-2 P1 (M-52 disclosure gap) — FIXED
The success manifest now MERGES the run-level disclosure (`_run_retraction_disclosed`) with the generator-internal `multi.retraction_disclosed` (the M-52 live_corpus pull can surface a retracted PRIMARY only the generator sees), deduped by evidence_id, so every excluded retracted source is disclosed exactly once. See run_honest_sweep_r3.py manifest block.
### iter-2 P2 (no-op manifest "byte-identical" overstated) — FIXED (wording)
The comment now states these are additive OBSERVABILITY keys present on every success manifest (legacy = strict SUBSET, not byte-identical). The keep-always-present choice is deliberate (§-1.4 observability — an auditor must always see the gate ran).
### iter-2 P2 (journal-only sidecar bool bug) — FIXED
The `_jo_meta_entry(is_retracted=...)` sidecar now uses the same `_retraction_is_truthy` predicate, so a string "false" is not coerced to retracted there either.

## NEW in iter 3 — W9 GRADUATION (operator-requested; please gate carefully — this touches the FAIL-CLOSED spend gate)
The operator asked to make W9 a first-class wired winner. run_gate_b.py changes (the pre-spend gate):
1. `_FULL_CAPABILITY_BENCHMARK_SLATE`: force-set `PG_CONTENT_DEDUP_CONSOLIDATE=1` (replaces the stale build-deferred comment).
2. `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS`: add `PG_CONTENT_DEDUP_CONSOLIDATE` (fail-closed if off before spend).
3. `_WINNER_FLAG_ALLOWLIST`: add it (the SLATE-PURITY gate requires every force-on flag be a recognized winner — without this the slate would FAIL CLOSED).
4. `_BENCHMARK_BUILD_DEFERRED_WINNERS`: now EMPTY (W9 was the only entry).
5. W9 GATE: message updated to "WIRED via keep-all (PG_CONTENT_DEDUP_CONSOLIDATE)". CRITICALLY the §-1.3-VIOLATING DROP-variant guard (PG_W9_CONTENT_DEDUP raises without PG_W9_DARK_ACK) is UNCHANGED — the DROP variant stays forbidden.
6. `_WINNER_FIRING_MARKER_CONTRACT`: add `W9_dedup_content_consolidate` = `[content_dedup_consolidate] W9:` so the post-run §-1.1 audit grep verifies W9 actually fired (the behavioral half).
7. Tests updated: 13->14 firing keys, W9-present assertion, back-compat count 13->14, producer-source map +W9, W9-gate docstrings de-stale'd. All pass.

## VERIFY (line-by-line) — focus on NOT breaking the fail-closed spend gate:
1. SLATE-PURITY consistency: PG_CONTENT_DEDUP_CONSOLIDATE is force-on AND allowlisted AND required — does any of the three gates (NO-LOSER, SLATE-PURITY, required-truthy) now false-FAIL or false-PASS the paid preflight? Is the flag also (wrongly) in any REQUIRED_OFF / loser list?
2. DROP-variant guard intact: confirm the W9 GATE still raises on PG_W9_CONTENT_DEDUP without PG_W9_DARK_ACK (the §-1.3 protection must not have been weakened by the message rewrite).
3. Firing-marker is real, not a phantom: the marker `[content_dedup_consolidate] W9:` must actually be emitted by content_dedup_consolidate.py on a real run (it is logged on both the early-return and main paths; the function only skips logging when disabled or <2 rows — confirm a real Gate-B corpus always hits >=2 rows so the post-run grep cannot false-fail).
4. Retraction P0 still closed: run-level seam clean covers generator + quantified + snapshot; manifest merge covers M-52. Any remaining grounding surface?
5. No-crash: the manifest merge (`_gen_retraction_disclosed` / dedup loop), the run_gate_b edits — any NameError / KeyError / wrong-collection-type path?
6. Faithfulness untouched: strict_verify / NLI / 4-role / span-grounding verdicts unchanged. W9 annotate-only; retraction narrows grounding (strengthens).
7. Accepted P2 (W9 before M-52 body-syndication): still accepted, non-blocking — confirm.

## Output schema (REQUIRED):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
