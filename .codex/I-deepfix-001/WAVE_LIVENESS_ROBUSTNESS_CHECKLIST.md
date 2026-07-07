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
- Wave 6 FINDING (surgical-not-rewrite grep): the 5-col summary table is ALREADY BUILT + WIRED — summary_table.py
  (render_requested_summary_table: verified-only, one row per verified source, span-grounded verbatim facet cells, "—"
  disclosed gap), PG_RENDER_SUMMARY_TABLE quad-pinned (run_gate_b.py 625/1962/2255/3613), CALLED in the render seam
  (run_honest_sweep_r3.py:6337 + 16688-16698, fail-open, canary [summary-table] at INFO). So Wave 6 = make it SCORE, not build.
- Wave 6a (593b0b3b): expand summary_table.py _GEO_PHRASES/_DOMAIN_PHRASES/_RISK_PHRASES to comprehensive general lists (the
  vocab lacked 5 of the 14 study countries → those rows rendered "—"). iter-1 both REVISE on a REAL P1 (case-insensitive
  nationality-adjective HOMOGRAPHS surfaced a FALSE country: polish/danish/turkey/french/dutch/swiss/greek/irish/chile +
  african/asian/indian/korean US-demographic) — NOT force-shipped. FIX (prune pass): removed exactly those 13 geo adjectives
  (all country NAMES stay, 5 targets work by name) + 18 neutral-polarity risk tokens; matchers (_word_boundary_search /
  _match_geography / _match_terms_ci) + own-source scoping BYTE-UNCHANGED → faithfulness-neutral surface-more-verified; OFF
  byte-identical. Codex APPROVE (0 P0/0 P1, 1 P2 polarity nit) + Fable APPROVE. 104 tests incl homograph regression suite.
  Wave-6b will add the summary_table FAIL-LOUD canary spec + retrieval seeding + Brynjolfsson NBER repoint.
- Wave 6b (1f3d2ced): summary-table FAIL-LOUD canary (anti-dark Rule #2). Render seam emits honest realized-effect
  `[activation] summary_table: reached=True rows=N cols=M` (+ distinct `unavailable_failopen` on the fail-open path);
  a fail-loud _ActivationMarkerSpec is registered so a DARK render (seam removed / import broken) CRASHES the run,
  honest rows=0 PASSES (§-1.3, no count>0 gate). iter-1 both REVISE on a REAL P1 (flag-predicate default-case gap:
  producer defaults PG_RENDER_SUMMARY_TABLE ON but the canary read unset as OFF → dark escape) — NOT force-shipped.
  FIX: new _ActivationMarkerSpec.flag_default_on field (default False; summary_table=True) → canary reads unset as ON
  matching the producer; explicit "0" still OFF; every other spec byte-identical. + P2a return-annotation fix. Consequent
  test maintenance: 4 sibling canary-test helpers opt summary_table OFF for their no-table logs. Codex APPROVE (0 P0/0 P1)
  + Fable APPROVE (0 P0/0 P1, 10/10 predicate byte-parity probe). 170 canary tests pass. Faithfulness engine untouched.
- Wave 6c (a09fe434): GENERAL stance/view-diversification retrieval-seed lane (default-OFF PG_STANCE_DIVERSIFY_SEEDS).
  Per planned facet ALSO issues queries framed from {supporting, opposing, challenges, opportunities} generic stances —
  helps ANY controversial-topic DR question (drb_72's 4 sections), NO benchmark study/country/topic hardcoded. §-1.3
  WEIGHT-not-filter: appends net-new stance queries only, NEVER raises max_queries, drops/caps/thins NOTHING; fail-open
  (error adds 0 + distinct unavailable_failopen degrade + suppresses positive marker + never aborts qgen). Quad-pinned +
  fail-loud spec. iter-1 both confirmed additive/general/fail-open; single Codex P1 = marker logged appended count
  pre-truncation → FIXED: marker moved AFTER _issue_seed_frontier, reports REALIZED issued count (live-probed
  appended=16/realized=15/marker=15). Codex APPROVE (0 P0/0 P1) + Fable APPROVE (0 P0/0 P1). 103 tests pass. Faithfulness
  engine untouched. HONEST NOTE: retrieval-seed payoff is only measurable in a real VM run corpus (offline-unverifiable).
- Wave 7 (f9173615): ACTIVATE the built-but-dark cross_section_repetition_guard.py (315-line, §-1.3-exemplary, already
  Codex+Fable diff-gated in a prior session, but UNTRACKED + imported by NOTHING). Committed the module + wired a FRESH
  caller (_apply_cross_section_repetition_guard) at the render-assembly seam in multi_section_generator.py:10251 (AFTER the
  per-section faithfulness engine, BEFORE the global marker remap; re-implemented stash@{0} intent conflict-safe, NOT blind
  apply). CONSOLIDATE-not-drop (exact verbatim cross-section duplicate → richest instance + citation-preserving back-ref;
  distinct content never clustered; no citation dropped). RENDER-ONLY (verified_text only, after engine). FAIL-CONSERVATIVE
  (guard error snapshots+restores every section's verified_text, never drops a section, emits unavailable_failopen). Honest
  marker consolidated=N realized. Quad-pinned + fail-loud spec (WAVE3 tuple; main tuple stays 10). Codex APPROVE (0 P0/0 P1)
  + Fable APPROVE. 55 tests. Faithfulness engine untouched. Pureshell PG_CONTENT_SHELL_REFETCH DEFERRED (retrieval-side).
  PRE-EXISTING unrelated test failure noted (NOT from Wave 7): test_gateb_containment_slate credibility inflight pinned 16
  but slate has 20 — a stale locked-pair assertion on HEAD; flagged for daylight reconcile.
