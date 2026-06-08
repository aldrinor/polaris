HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# BRIEF (acceptance-criteria review) — FIX-CRED-01 (#1146): remove the journal-only restriction from the benchmark

You are reviewing the ACCEPTANCE CRITERIA / DESIGN of this brief (not a diff yet). Confirm the plan is correct, complete, and faithfulness-safe, OR return REQUEST_CHANGES with specific blockers.

## HARD CONSTRAINTS (operator-locked — not consultable)
- **Operator directive 2026-06-07 (verbatim):** "I don't like this approach, as many things are not journal, but still credibility. Mainstream news, gov, some credible sites, why you have tendency to make yourself into tunnel view." => The journal-only source restriction is REJECTED. This is the spec; do not propose keeping journal-only.
- Faithfulness gates (strict_verify per-sentence provenance, 4-role D8, two-family segregation, corpus_approval) MUST remain byte-unchanged and un-weakened.
- No paid spend in this change; offline only.

## CONTEXT
The operator-authorized paid drb_72 re-run held at `abort_corpus_inadequate`. Authoritative run stdout:
```
[agentic] merged +41 evidence rows from +93 sources; adequacy=proceed uncovered=0   <-- general corpus ADEQUATE
[journal_only] source-filter: evidence_rows 59 -> 11 citeable (48 non-journal excluded); classified_sources 247 -> 63
[journal_only] adequacy floor FAILED: ['too_few_distinct_journals:5<12']
[ABORT] Corpus inadequate. status=abort_corpus_inadequate
```
i.e. the general corpus was adequate; only the journal-only overlay (FIX-JO #1100/#1134) collapsed it below a distinct-peer-reviewed-journal **count** floor (5<12) and forced the abort. drb_72 is an AI/labor-ECONOMICS literature review whose primary evidence is working papers (NBER/IZA), government statistics (BLS/OECD), and reputable-institute reports — non-journal but credible. (Compounding, separately tracked as #1147: the AEA Journal of Economic Perspectives `10.1257/jep.*` is legally FREE but fetched 1 char due to anti-bot blocking — NOT in scope for THIS change.)

Research finding (for your weighing): a distinct-journal **count** floor is a metadata-as-quality proxy of the kind §-1.1 bans; the beat-both benchmark is scored on §-1.1 per-claim faithfulness, NOT on source-type. A broad credible corpus, every sentence still strict_verify-/4-role-gated, scores higher than a thin 5-journal one.

## THE CHANGE (FIX-CRED-01) — surgical, single activation seam
1. **`scripts/dr_benchmark/run_gate_b.py:827`** — change `JOURNAL_ONLY_BENCHMARK_SLUGS: frozenset[str] = frozenset({"drb_72_ai_labor"})` to `frozenset()` (EMPTY). No benchmark question is journal-only. KEEP the constant + `apply_journal_only_for_slug()` mechanism intact and dormant (so a FUTURE deliberate, operator-approved journal-only question can be added by appending a slug). Update the explanatory comments (lines ~815-826 and ~945-952) to cite the 2026-06-07 operator credibility-model directive and that faithfulness is enforced by the verify gates, not source-type purity.
2. **`tests/dr_benchmark/test_gate_b_journal_only_per_slug.py`** — rework to the new spec:
   - assert `JOURNAL_ONLY_BENCHMARK_SLUGS == frozenset()` and `"drb_72_ai_labor" not in JOURNAL_ONLY_BENCHMARK_SLUGS`.
   - NEW critical assertion: `apply_journal_only_for_slug("drb_72_ai_labor")` returns `False`, the flag is ABSENT, and `journal_only_active(load_scope_template("workforce")) is False` — i.e. drb_72 now uses the broad credibility corpus.
   - keep the deterministic-clear / no-loop-leak test (still valid for the dormant mechanism).
   - keep the mechanism alive (not dead code): with `monkeypatch.setattr(run_gate_b, "JOURNAL_ONLY_BENCHMARK_SLUGS", frozenset({"drb_72_ai_labor"}))`, assert `apply_journal_only_for_slug("drb_72_ai_labor")` sets the flag — proves a future slug can still activate.

## WHY THIS IS FAITHFULNESS-SAFE (verify this claim)
`journal_only` is a corpus-COMPOSITION restriction applied at retrieval/adequacy (`src/polaris_graph/nodes/journal_only_filter.py`, consumed in `scripts/run_honest_sweep_r3.py` only when `_jo_active`). The faithfulness gates operate on whatever corpus is present and are unchanged: every generated sentence still needs `[#ev:id:start-end]` provenance + numeric/content-overlap strict_verify against its cited span, still passes 4-role D8, still two-family. Broadening the corpus does NOT bypass any per-sentence check — it just lets credible non-journal evidence be cited (and verified). With the empty set, `journal_only_active()` (which requires BOTH the env flag AND the protocol field) is always False, so the filter + count-floor never run; the GENERAL workforce adequacy governs — and that already returned `adequacy=proceed uncovered=0` on the real run.

## FILES I HAVE ALSO CHECKED AND THEY'RE CLEAN
- `src/polaris_graph/nodes/journal_only_filter.py` — the filter predicate `is_citeable_journal` (208-264) + floor `DEFAULT_MIN_DISTINCT_JOURNALS=12` (531) + `assess_journal_only_adequacy` (543-607): UNCHANGED. Only ever invoked when `_jo_active` True, which is now never. `tests/polaris_graph/test_journal_only_filter_iready017.py` tests these functions directly (mechanism), so it stays green.
- `scripts/run_honest_sweep_r3.py` — `_jo_active = journal_only_active(...)` (2667), source-filter (3252), floor override (3321-3338): all gated by `_jo_active`, inert with the empty set. UNCHANGED.
- `src/polaris_graph/retrieval/live_retriever.py` — references journal_only only under the active flag; inert. UNCHANGED.
- `config/scope_templates/workforce.yaml` — declares `source_restriction: journal_only` at template level. With the env flag never set, this is DORMANT dead-config (journal_only_active needs both). General workforce `corpus_adequacy` bands apply (proven `proceed` on the run). NOT modified here to keep the change surgical and avoid touching other workforce-domain adequacy; removing the dead declaration is noted as an OPTIONAL cleanup follow-up. Confirm you agree leaving it dormant is acceptable, or flag if you want it removed in this PR.
- Faithfulness gates: strict_verify / 4-role D8 / provenance / two-family — NOT touched.

## ACCEPTANCE CRITERIA (GREEN)
- `JOURNAL_ONLY_BENCHMARK_SLUGS` is empty; no benchmark question activates journal-only.
- drb_72 resolves to the broad credibility corpus (general workforce adequacy), so the `too_few_distinct_journals` artifact can no longer block it.
- Reworked test passes; the dormant mechanism is still proven activatable for a future slug.
- Zero change to faithfulness gates; offline; no spend.
- Re-run (operator-gated) is expected to PROCEED past the corpus gate to generation → a report for §-1.1 audit (acceptance is the audit, not a green status).

## QUESTIONS FOR YOU
- Is emptying the activation set (keeping the dormant mechanism) the right granularity, or do you require removing `source_restriction: journal_only` from `workforce.yaml` in THIS PR?
- Any faithfulness or adequacy regression risk you see from broadening drb_72's corpus that the existing tier/adequacy/strict_verify/4-role stack does NOT already cover?

## OUTPUT SCHEMA (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
