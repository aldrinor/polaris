# Wave Liveness Robustness Checklist (operator-locked 2026-07-06)

**Operator directive (verbatim intent): the liveness rule below is SUPER CRITICAL and EVERY wave must follow it.**
No fix is "done" until ALL of these are proven, by reading the committed code — not asserted from memory.

Applies to EVERY flag in EVERY wave of I-deepfix-001 (#1344). The whole campaign exists to kill the
build-dark-rebuild failure mode, so a flag that passes review but never fires in the official run is STILL the bug.

## The 6 robustness gates per flag (all must pass at the wave's commit)

1. **Turns ON in the official run.** The flag sits in ALL FOUR gate-B slate structures in `scripts/dr_benchmark/run_gate_b.py`:
   `_FULL_CAPABILITY_BENCHMARK_SLATE` (value "1") + `_BENCHMARK_PREFLIGHT_REQUIRED_FLAGS` + `_BENCHMARK_FORCE_ON_FLAGS` + `_WINNER_FLAG_ALLOWLIST`.
   (Numeric-value flags go in `_BENCHMARK_FORCE_EXACT_FLAGS` instead of the boolean lists — confirm the numeric-floor path still forces it ON.)
   VERIFY by actual line numbers per structure, not a raw count (a count of 4 can be 4 hits in one block).

2. **Gates real code.** The flag has a real read-site in `src/` (`os.getenv`/`os.environ`, directly or via a
   `_ENV_… = "PG_…"` constant read by a helper) that switches an ACTUAL code path — never a flag read by nothing.

3. **Announces itself when it fires.** A distinct fire-time log line exists at the ON path
   (e.g. `"[live_retriever] PG_POST_FETCH_ENRICH_PARALLEL ON — pre-batched …"`), so the VM preflight can PROVE it fired.

4. **OFF is byte-identical.** With the flag OFF (or `=0` kill-switch), behavior is byte-for-byte the legacy path. Dual-gate confirmed.

5. **Dual-gate APPROVE.** BOTH the real Codex CLI AND real Fable 5 APPROVE the diff (zero P0, zero P1). No single-gate, no self-report.

6. **Every new module the flag imports is git-TRACKED and IN THE REVIEW DIFF.** ← added 2026-07-06 (Wave-3 iter-4 P1.3).
   A FORCE-ON flag that imports an UNTRACKED module (`??` in `git status`) will `ModuleNotFoundError` on the official
   run = a dark/aborting flag, not a live one. The plain `git diff` used to build the review never shows untracked
   files, so the reviewer cannot verify the module either. FIX at build time: `git add -N src/…/<module>.py` (intent-to-add)
   so it appears in the unstaged review diff AND is in the commit's file list. Additive lanes that import such a module
   MUST also fail-OPEN (import/LLM failure adds zero sources, never aborts the host path) — §-1.3 additive-on-failure.

## STATIC vs DYNAMIC (do not conflate)

- Gates 1–6 are the STATIC proof, confirmed at each wave's commit from the committed code.
- The DYNAMIC proof — each flag ACTUALLY fired and changed real output — is a SINGLE small real run on the VM AFTER
  all waves land, emitting every flag's fire-log and producing a per-fix PROVEN / NOT-PROVEN table, BEFORE the big paid run.
  (Offline unit tests are NOT this proof — operator rule feedback_offline_tests_not_real_preflight_prove_small_real_run_2026_07_02.)
  Never claim "fired in a real run" for any wave until that table exists.

## Committed-wave audit trail (verified from committed code)

- Wave 1 (1577b62a): PG_WORKFORCE_T3_TARGETING, PG_DEBATE_CON_BASKET_CONSOLIDATION, PG_A1_BASKET_FALLBACK,
  PG_RENDER_CHROME_SCREEN, PG_DEPTH_DECHROME_MEMBERS — all quad-pinned (line-verified), all have real read-sites, OFF-identical, dual-gate APPROVE.
- Wave 2 (531c29be): PG_POST_FETCH_ENRICH_PARALLEL (fire-log line ~5990), PG_WALL_CLASSIFY_RESCUE — quad-pinned (line-verified),
  read-sites present, §-1.3 rescue keeps-at-floor, OFF-identical, dual-gate APPROVE.
- Wave 3 (10b3ab96): PG_QGEN_PARALLEL_QUERIES (numeric>=2, wall-rechecked, issued-count HONEST) + PG_OPENALEX_DATE_FILTER
  + PG_LANDMARK_EXPANDER (recovered landmark_study_expander.py, now TRACKED, fail-open at BOTH inner _enumerate + outer path).
  Dual-gate APPROVE iter-2 (Codex+Fable). Activation markers now report REALIZED effect not intent: fail-open landmark emits a
  distinct `unavailable_failopen` marker the canary REJECTS (no false-green); qgen marker logs issued=N. §-1.3 held — ran-ok
  count=0 still accepted, NO breadth threshold. Faithfulness engine untouched. 27 tests. Gate-6 satisfied (module tracked + in diff).
- Wave 4 (782e7d64): retrieval-dating contamination — PG_OPENALEX_MATCH_VALIDATE (validate title-search match; wrong match
  WITHHOLDS metadata but KEEPS the source = §-1.3 demote-not-drop; exact-DOI trusted; DOI-conflict hard-rejected) +
  cache validation-aware + AUTHORITY_CACHE_SCHEMA_VERSION 3→4 + ACTIVATED the DARK publication_date_resolver.py (was
  tracked-but-uncalled; now has a LIVE call site in live_retriever.py) under PG_RESOLVE_PUBDATE_FROM_HTML, fail-open.
  Honest realized-effect markers (checked/rejected, resolved/unresolved) + distinct fail/unavailable degrade markers the
  canary rejects; NO count>0 threshold. Dual-gate APPROVE iter-2 (Codex+Fable). 33 tests. Faithfulness engine untouched.
  ANNOTATION: activate = wired the caller, did NOT re-edit the module (ideal activate-not-rebuild). Both flags quad-pinned.
- Wave 5 (e55637b3): render truncation cleanliness — FF2 lexical copula/aux leg RETIRED as unsound (both reviewers proved it
  over-strips complete verified claims: have/has/had, that/bare-relative, noun-homographs will/must/May — unfixable by
  keep-set, same disease that removed the lone-letter leg; §-1.3 over-strip is the cardinal sin, so retire not patch-again).
  FF2 was uncommitted → declining to ship a bad leg, not removing production code. SHIPPED: FF3-TRUNC-SEM (PG_FF3_TRUNC_SEM,
  default OFF byte-identical) — the SOUND semantic leg (dangling complement-demanding connectives "…faster than"/"…held
  unless" that grammar cannot end; no homograph ambiguity). FF3 quad-pinned (4 slate structures line-verified: slate 1744 /
  required 2047 / force-on 2341 / allowlist 3697 + canary 3335), honest realized-effect marker (reached/screened/detected/
  repaired/dropped) + distinct unavailable_failopen degrade the canary rejects, NO count>0 gate. Codex APPROVE (0 P0/0 P1) +
  Fable APPROVE (0 P0/0 P1), FF3 tests 20/20. Faithfulness engine byte-untouched. _COPULA_SUBJECT_PRONOUN_KEEP kept (live FF3
  dep, not FF2-dangling). Pureshell + repetition-guard remain DEFERRED to Wave 7 (conflict-safe re-implement, not blind stash).
