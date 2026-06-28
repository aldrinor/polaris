HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

## CHANGES SINCE ITER 1 (your P0 + P2a fixed — re-verify FIRST)
- **P0 (relevance gate not fail-open) FIXED** across 3 files. `prefetch_offtopic_filter._similarity_scores` now returns `None` (not `[0.0]*N`) on its three INFRA failures — no embed_batch/encode interface, zero-norm QUERY vector, encode exception — distinct from a genuine empty-SNIPPET 0.0 (the documented no-text drop). `filter_search_results` fails OPEN (keeps all candidates) when sims is None. `evidence_selector._semantic_relevance_scores` drops the None anchors and returns `None` when EVERY anchor failed, so B1/B4's live gate falls back LOUDLY to the lexical cut (keeps candidates) instead of mass-dropping. Updated the stale live_retriever reconciliation comment. Added `test_scorer_infra_failure_fails_open_to_lexical`. Verify: no path converts a scorer/embedder error into below-threshold drops; an empty SNIPPET still scores 0.0 and drops (intended).
- **P2a (B3 directive overmatch) FIXED**: `_IMPERATIVE_OPENER_RE` narrowed to only unambiguous injection openers (`please/ignore/disregard/do not/don't` + trailing space); removed the polysemous research verbs (return/output/ensure/keep/put) that dropped "return-to-work outcomes" etc. Their real injection forms remain high-precision in `_DIRECTIVE_MARKERS`.
- **P2b (B3 constraints not serialized)** deferred to wave-2 (auditability; wave-2 owns run_honest_sweep). Noted in state/deepfix_wiring_seams.md.

## (Original iter-1 brief follows.)

HARD ITERATION CAP (orig): 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd on remaining-non-P0/P1; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC ONLY. Do NOT run pytest / the pipeline / broad exploration. Read the combined diff at `.codex/I-deepfix-001/wave1_diff.patch` and the changed regions. Emit the verdict schema at the end.

# I-deepfix-001 Phase 3-fix WAVE 1 (#1344) — leaf modules + flag activations (deep wiring is wave-2)

This is the FIRST of two fix waves from the forensic campaign. Wave-1 deliberately lands ONLY the safe, self-contained parts: leaf modules, default-flag activations, detection vocab, prompt hardening, honest disclosure strings. The deep cross-file firing-wiring (the "foreign seams") is intentionally DEFERRED to a serial wave-2 — so some new modules here are not yet called. Your job: confirm what is applied is CORRECT, SAFE, and does not break the run or relax faithfulness; flag any applied piece that is a half-fix that silently degrades.

**THE ONLY HARD GATE is the faithfulness engine (strict_verify numeric/span/overlap, NLI, 4-role D8, provenance, span-grounding). It must NOT be relaxed. §-1.3 DNA: WEIGHT don't FILTER; CONSOLIDATE don't DROP; off-topic RELEVANCE is the one axis where a gate is allowed — credibility tier is NEVER a hard drop.**

## What wave-1 applies
- **B1 KEYSTONE (content_relevance_judge.py, prefetch_offtopic_filter.py):** flips PG_CONTENT_RELEVANCE_JUDGE + PG_RETRIEVAL_RELEVANCE_GATE to default-ON, and repoints the relevance embedder default to the locked Qwen3-Embedding-8B (was MiniLM). The off-topic relevance gate is the ONE allowed drop per §-1.3.
- **B3 (intent_frame.py, scope_query_validator.py):** prompt hardened for injected-directive isolation; new constraints[] field/parser; a deterministic directive-screen helper (strip_directive_clauses) added to scope_query_validator; default-ON. (The call-site substitution into the run script is wave-2.)
- **B5 (shell_detector.py):** anti-bot interstitial vocab extended (Anubis/Cloudflare/DataDome/PerimeterX/captcha). Detection only; recovery-leg activation is wave-2.
- **B7 (content_relevance_judge.py / live_retriever.py):** the W2 relevance weight now fires by default so each evidence row carries a relevance weight. (Adequacy denominator re-base is wave-2.)
- **B10 (NEW intake_constraint_extractor.py):** date-window/language/journal constraint extractor (dateparser-or-GLM). NOT yet wired — currently dead code.
- **B14 (NEW title_body_consistency.py):** title<->body identity gate (re-derives title, flags identity_consistent=False, NEVER drops). NOT yet wired — currently dead code.
- **B12 (multi_section_generator.py):** decouples the weighted_enrichment breadth call-site from the v30_contract_plans flag so the Codex-approved faithfulness-neutral enrichment FIRES on the generic (non-contract) path.
- **B15 (fact_dedup.py):** flips the in-tree prose dedup default-ON (PG_CONSOLIDATION_NLI_PROSE / PG_FACT_DEDUP_PROSE) to collapse degenerate repetition.
- **B4/B11 (run_honest_sweep_r3.py, release_policy.py):** HONEST disclosure strings only — Methods clause states the real gen/eval family relationship incl. "not family-segregated"/"same family '<fam>'"/"self-bias safeguard disabled" when applicable; release_disclosure carries a quality-score display field. (The substantive PT03 gate + provider-SLO transport are wave-2.)

## VERIFY HARDEST (adversarial — the real risks)
1. **B1 over-drop / breadth (P0/P1 if real):** PG_RETRIEVAL_RELEVANCE_GATE default-ON now DROPS sources. Confirm it gates ONLY on off-topic RELEVANCE (allowed), NOT on credibility tier (forbidden §-1.3); confirm it is FAIL-OPEN (a judge/embedder error must NOT drop a source — degrade to keep+weight, never silent-drop); confirm the threshold is conservative enough not to nuke on-topic breadth. A gate that hard-drops on error or tier = P0.
2. **Embedder repoint correctness:** prefetch_offtopic_filter repoints to Qwen3-Embedding-8B. The agent reported `from src.polaris_graph.agents.nli_verifier import EmbeddingService` currently FAILS (no such symbol) so it falls to the SentenceTransformer path. Confirm the applied fallback actually loads the locked model and is fail-open; confirm no path silently re-introduces MiniLM as the relevance embedder.
3. **B15 consolidate-not-drop:** confirm the prose dedup CONSOLIDATES degenerate repeats (keeps all corroborating sources on the survivor) and never DELETES a distinct claim or a source — §-1.3 keep-all. A dedup that drops corroboration = P1.
4. **Dead modules harmless:** intake_constraint_extractor.py + title_body_consistency.py are not yet called. Confirm they import cleanly (no module-load side effects, no heavy import at module top that would slow every run) and cannot accidentally fire.
5. **B4 disclosure honesty:** confirm the Methods/disclosure strings HONESTLY state non-segregation on an all-GLM same-family run (do NOT claim "separate family" when gen==eval). A disclosure that still asserts segregation = P1 (clinical-safety dishonesty).
6. **B12 faithfulness-neutral:** confirm decoupling the enrichment gate only surfaces MORE already-verified breadth (no new unverified content, strict_verify unchanged).
7. **No faithfulness-engine edit; default-ON flips only tighten/weight, never loosen.** Confirm strict_verify/NLI/span/4-role/provenance are untouched.

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
