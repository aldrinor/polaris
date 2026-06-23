HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

FRONTIER-TECH MANDATE: reference only 2025-2026 frontier methods, primary-source verified; no grandfather downgrade.

## ITER-1 RESOLUTIONS — verify each is correctly fixed (do not re-raise unless the fix is wrong)
Iter-1 returned REQUEST_CHANGES with 7 P1. Each is resolved; the patch now reflects them. Ground
truth was pulled from the live code (no guessing — the generate() crash was a guess, now fixed by
reading the real signature):

- **P1-1 (SLUG_TO_IDX gap):** real slugs are `drb_76_gut_microbiota_crc`/`drb_78_parkinsons_dbs`
  (bare `drb_76`/`drb_78` never matched). drb_90_adas_liability has NO DRB-II gold idx, so it is in
  a new explicit `DRB_SLUGS_WITHOUT_CANONICAL_GOLD` set. New `assert_drb_slug_registered()` FAILS
  LOUD on any `drb_*` slug that is neither mapped nor explicitly no-gold; wired into the sweep
  GATE0 loop (run_honest_sweep ~L13307).
- **P1-2 (resume bypasses GATE0):** snapshots store `"question"` (corpus_snapshot.py:112 /
  fetch_snapshot.py:134). New `_assert_snapshot_question()` at the resume-load site
  (run_honest_sweep ~L5528) fails loud if a snapshot's stored question != the run's canonical
  research_question (stale wrong-question corpus).
- **P1-3 (`--real` crash):** real signature is `OpenRouterClient(model=...).generate(prompt=, max_tokens=)`
  — no model/messages kwargs. make_glm_llm fixed to instance-scope the model = z-ai/glm-5.2.
- **P1-4 (budget by URL):** ClosedLoopMethod now counts QUERIES ISSUED, not unique URLs.
- **P1-5 (--idx overrides known slug):** main() now REFUSES `--idx` that != SLUG_TO_IDX[slug].
- **P1-6 (crippled floor):** floor_queries now pulls the hand-authored `amplified` set from
  SWEEP_QUERIES (the real current-POLARIS floor) + decompose; regulatory/trial are explicitly
  scoped out as a retrieval-section concern (documented, not silently dropped).
- **P1-7 (60000-char truncation):** the judge now CHUNKS the corpus (window 48000, cap 12 chunks,
  honest log if capped) and ORs across chunks — every source is judged, order no longer decides.
- **P2 also addressed:** per_point keeps the FULL rubric text (+preview); retrieval cache key now
  includes domain + schema version; make_glm_llm max_tokens raised to 8192 (governance, cap-not-target).

Smoke (all green): py_compile x5; fail-loud registration (known pass / drb_90 exempt / drb_99 raises);
ranking still fires (closed-loop 1.00 > floor 0.40); per_point full; --idx/slug mismatch refused.

## ITER-2 RESOLUTIONS — verify each (iter-2 returned REQUEST_CHANGES: 1 new P1 + 1 continuing P1 + 2 P2)
- **NEW P1 (blocked-reference leakage):** the DRB-II `blocked` field is a dict {title, authors, urls}.
  Added `load_blocked_references(idx)` + `make_blocked_filter()` (URL-normalized match across all
  mirror URLs + title-in-text). `run_coverage_test(..., blocked_refs=...)` now DROPS any retrieved
  blocked row before it reaches ANY method's corpus (uniform), counts it as `blocked_dropped`, and a
  point supportable ONLY by the blocked source therefore stays UNCOVERED. The runner loads the
  blocked ref by idx and passes it. Smoke: blocked url + mirror caught, clean row passes, blocked
  row dropped, the blocked-only point stays uncovered (no cheating).
- **CONTINUING P1-7 (judge truncation):** REMOVED the silent chunk cap. The judge now judges EVERY
  chunk (short-circuit on YES); if a corpus would exceed a generous SANITY bound
  (PG_QGEN_JUDGE_HARD_MAX_CHUNKS=500) it FAILS LOUD (raises) — never silently scores a prefix, so
  row order can no longer decide coverage. Smoke: oversize corpus raises; within-bound judges all.
- **P2 (metric label):** `_row_text` docstring now labels the metric explicitly (POLARIS
  generator-visible evidence = title+statement+grounding span; how to switch to full-body coverage).
- **P2 (slug/idx bypass):** main() now (a) fails loud on an unregistered drb_* slug, (b) REJECTS a
  no-gold slug (drb_90) outright, (c) lets a benchmark slug's --idx only CONFIRM not override, and
  (d) requires --idx only for genuinely non-benchmark slugs. Smoke: drb_90 rejected; non-bench needs idx.

## ITER-3 RESOLUTION + GROUND-TRUTH REBUTTAL (iter-3 raised 1 P1 — a field-path misread)
Iter-3's sole P1 claimed DRB-II stores `blocked` as a TOP-LEVEL field, so `load_blocked_references`
reading `content.blocked` returns None (no-op). **That is factually contradicted by the gold file.**
Ground truth for idx 56 (`third_party/DeepResearch-Bench-II/tasks_and_rubrics.jsonl`), verified three
independent ways (a direct key probe, a second inspection across idx 1-5, AND a passing behavioral smoke):
- TOP-LEVEL keys = `[id, idx, language, theme, description, prompt, content, license]` — **top-level
  `blocked` is ABSENT**.
- `content` keys = `[task, rubric, blocked]` — **`content.blocked` IS PRESENT**, a dict
  `{title, authors, urls}` (real title "Impacts of generative artificial intelligence on the future of
  labor market…", 5 urls incl the sciencedirect S2451958825000673).
- Smoke: `load_blocked_references(56)` returns that dict; the filter DROPS the real Salari URL +
  its doaj/herts mirrors; the blocked-only point stays uncovered. `blocked_dropped` increments.

So `content.blocked` is the CORRECT path; switching to `record.get("blocked")` as iter-3 suggested
would BREAK the working loader. To make the question MOOT and the loader robust to any row-format
drift, it now reads `content.blocked` PRIMARY and falls back to a top-level `blocked` (correct under
either layout). **Please verify against idx 56 in the gold file that content.blocked is the real path.**

# Diff review — I-qgen-001 (GH #1291): query-gen COVERAGE-ISOLATION harness + GATE 0 canonical binding

This is a STATIC CODE review. Do NOT run pytest, do NOT execute anything. Read the patch file
at `.codex/I-qgen-001/codex_diff.patch` (5 files, ~779 lines, almost all NEW code) and review it
against the brief intent below.

## What this diff does (intent — approved brief at `.codex/I-qgen-001/brief.md`, ITER-6 refinement)
The operator method: test EACH pipeline section IN ISOLATION on the benchmark axis it drives, no
e2e per candidate, pick each section's winner, then combine winners for ONE final full run. This
diff is the FIRST section: QUERY GENERATION, scored on COVERAGE only.

A query-gen method's only job is COVERAGE — getting the right evidence into the corpus. So the
harness measures exactly that and nothing downstream:
  run a method's queries -> retrieve -> for each REQUIRED point (a DRB-II info_recall rubric) ask
  "is its evidence present in the retrieved corpus?" -> coverage fraction.
NO report generation, NO rendering, NO DeepTRACE judge here (those gate the faithfulness sections
+ the final combined run).

## The 5 files
1. `scripts/dr_benchmark/gate0_lineage.py` (NEW) — GATE 0 artifact-lineage enforcement. Binds every
   benchmark question to the CANONICAL gold file by idx (SLUG_TO_IDX). This is the fix for the
   drb_72 disaster: a hardcoded WRONG question was launched and scored against the right rubrics ->
   garbage 0.071 score. `assert_launched_question_is_canonical` / `assert_no_split_brain` /
   `build_lineage_manifest` make launched==packed==answered==canonical enforceable + hashable.
2. `scripts/dr_benchmark/qgen_coverage_harness.py` (NEW) — the pure harness: `load_required_points`
   (info_recall rubrics for an idx), `score_coverage`, `run_coverage_test`. retrieve()/judge() are
   INJECTED (deterministic, unit-testable). Every method sees the SAME retrieve()/judge() — only the
   queries differ (isolation).
3. `scripts/dr_benchmark/qgen_methods.py` (NEW) — two method adapters: FloorMethod (current POLARIS
   facets, the baseline to beat) + ClosedLoopMethod (frontier coverage-contract + gap-driven
   re-query; decomposes the question into its OWN sub-points, NEVER the gold rubrics — no answer-key
   leakage). Common-code dedup is identical for every method.
4. `scripts/dr_benchmark/run_qgen_coverage.py` (NEW) — the runner. Wires real POLARIS retrieval
   (`run_live_retrieval`, cached to disk by sha256(query) so isolation holds + re-runs are free) +
   a real GLM-5.2 coverage judge (`OpenRouterClient.generate`). `--dry-run` = stub world, NO spend
   (default). `--real` = real spend, GATED behind env `PG_QGEN_AUTHORIZED_SPEND=1` (Claude does NOT
   self-authorize spend). The floor's queries are POLARIS's CURRENT query-gen (`query_decomposer`).
5. `scripts/run_honest_sweep_r3.py` (MODIFIED, ~+15 lines) — wires the GATE 0 canonical binding into
   the live sweep right after `queries_to_run` is built: any benchmark slug whose launched question
   drifted from the gold file is OVERRIDDEN with the canonical question (+ a printed [GATE0] notice).
   This is the structural drift-proof fix so the wrong-question bug cannot recur on the paid run.

## What to check (the decision is yours — Codex is the only gate)
- CORRECTNESS: does the isolation actually isolate query quality? (same retrieve()/judge() for all;
  only queries vary; closed-loop adapts to retrieval but retrieval is deterministic per query).
- LEAKAGE: does ClosedLoopMethod avoid seeing the gold rubrics (it must decompose the question
  itself)? Confirm the gold info_recall points are used ONLY for scoring, never fed to a method.
- GATE 0: does the canonical binding in run_honest_sweep correctly override a drifted question for
  EVERY downstream read of `q["question"]`, and only for benchmark slugs in SLUG_TO_IDX (no effect
  on non-benchmark queries)? Any place the override could be bypassed?
- SPEND SAFETY: is `--real` genuinely gated so no accidental spend? Is the disk cache key correct
  (same query -> same file -> identical retrieval across methods)?
- FAITHFULNESS: this harness only scores COVERAGE; confirm it does NOT touch / relax any faithfulness
  gate (strict_verify / NLI / 4-role / provenance). It must not.
- EVIDENCE-TEXT FIDELITY: `_row_text` assembles per-source text from title+statement+direct_quote.
  Is that an honest coverage signal, or does it under/over-state what the source contributes? Flag if
  a richer field (full fetched body) should be used.
- Any NEW P0/P1 that makes the coverage numbers untrustworthy or the selection wrong.

## Output schema (this EXACT schema; loose prose rejected)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
