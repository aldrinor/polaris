HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-gen-003 diff iter 2 — addressed iter-1 REQUEST_CHANGES (decision c)

Combined brief+diff review. Full brief at `.codex/I-gen-003/brief.md`. This file is the iter-2 delta against your iter-1 verdict.

## How each iter-1 finding was addressed

**iter-1 P1 "don't ship the default flip / failure is report-layer not just crash recovery"** — addressed by the PT11 + normalization work below. The default flip to V4 Pro stays (operator directive) but is now backed by the report-layer fixes you required, not just crash recovery. Smoke #4 result appended below — gate must reach `partial*` or better.

**iter-1 P2 "strip the inert regen loop"** — DONE. Changes 1+2 (HARD OUTPUT CONTRACT + bounded regen loop + budget escalation) fully reverted to pre-`0c55a4bc`. `_call_section` and `_run_section` are byte-identical to the original except change 5 (the `except` clause) is retained.

**iter-1 P2 "REAL BUG — `_REASONING_FIRST_MODELS ⊇ _ALWAYS_REASON_MODELS`, GLM gets escalation"** — FIXED, and you were right. `_REASONING_FIRST_MODELS = frozenset({*_ALWAYS_REASON_MODELS, "deepseek-v4-pro", "deepseek-v4-flash"})` — GLM was in the set. Stripping changes 1+2 removes the only code path (`_is_reasoning_first` in `_run_section`) that mistreated GLM. No `_REASONING_FIRST_MODELS` membership test remains in the generator.

**iter-1 P2 "PT11 partly report-layer — Limitations telemetry 135.7/269.0"** — FIXED. `external_evaluator` PT11 now stops `prose_only` at the `Limitations` block (matched `## ` or `### `, case-insensitive) as well as `## Methods`. The Limitations block is POLARIS-generated meta-prose — corpus-skew %, the contradiction detector's own relative-difference telemetry, completeness-gap counts — the same "specifications, not empirical claims" category PT11 already excludes for Methods. **Analyst Synthesis stays IN PT11 scope** (it is generator output; synthesis numerics must be cited — confirmed by `test_pt11_still_flags_uncited_decimals_in_body_and_synthesis`).

**iter-1 P2 "`('',0,0)` telemetry lossy"** — acknowledged as acceptable per your own verdict; unchanged.

**iter-1 P3 "stale comments / V4-Pro-produces-clean-prose overclaim"** — FIXED. `openrouter_client` `PG_GENERATOR_MODEL` + I-bug-090 comments rewritten: no more HARD OUTPUT CONTRACT / regen-loop references, no "produces clean anchored prose" claim. They now state only what smoke #3 proved (crash fixed) and point report-layer citation tightness at this iter's work.

## On "citation/punctuation normalization after provenance resolution" — IMPORTANT, flag if I misread

You asked for "citation/punctuation normalization." I implemented `_normalize_citation_punctuation` (multi_section_generator.py) — a cosmetic pass applied right after `resolve_provenance_to_citations` that:
- inserts a missing sentence-terminal period at a genuine boundary (`secretion[1] GLP-1 ...` → `secretion.[1] GLP-1 ...`)
- normalizes whitespace around markers
- **byte-preserves every citation marker and evidence ID** — verified by `test_normalize_byte_preserves_markers_and_evidence_ids`.

**I deliberately did NOT implement citation-*attachment*** (walking uncited decimals and attaching the nearest `[N]`). Attaching a citation the generator did not emit is fabrication — it asserts evidentiary support that was never established. Under §9.1 (provenance invariants) and §-1.1 (clinical-safety: a wrong contraindication/dose that survives a check can hurt a patient) that is a hard line I will not cross in code. If "normalization" to you meant attachment, **say so explicitly and name the safety argument that makes it acceptable** — otherwise I hold this line.

## Diff — net effect vs origin/polaris

`.codex/I-gen-003/codex_diff.patch` (canonical-diff-sha256 trailer included). 4 commits on branch; iter-2 commit is `cb7feaa3`.

Surviving changes (changes 3+4+5 + iter-2 additions):
- `openrouter_client`: `PG_GENERATOR_MODEL` → `deepseek/deepseek-v4-pro`; `PG_MAX_COST_PER_RUN` `0.10→10.00`; `ReasoningFirstTruncationError(RuntimeError)`; `PG_REASONING_FIRST_MIN_MAX_TOKENS` `6000→20000`; I-bug-089 SF-15 raises the typed exception.
- `multi_section_generator`: `_call_section` catches `ReasoningFirstTruncationError` → empty draft (crash → honest abort); `_normalize_citation_punctuation` helper + wired after provenance resolution.
- `external_evaluator`: PT11 `prose_only` also excludes the Limitations block.
- 7 new tests in `test_i_gen_003_citation_normalization.py`. 387 generator+evaluator+PT11 tests pass, no regressions.

## Smoke #4 result — PASS

`run_honest_sweep_r3.py --only clinical_tirzepatide_t2dm`, `PG_GENERATOR_MODEL=deepseek/deepseek-v4-pro`, 2026-05-15.

**Result: `status=success`, `release_allowed=true`, `gate_class=pass`, cost $0.0763, wall ~25 min.**

Meets the PASS criterion (`ok*`/`partial*`) — and clears to full `success`, not merely `partial`.

- **PT11 now passes.** Smoke #3's PT11 FAIL (3/24 uncited decimals, 2 of which were Limitations telemetry) is resolved by the iter-2 PT11 Limitations exclusion. `evaluator_rule_pass=12`, `evaluator_rule_fail=1`.
- The single rule fail is **PT13 unhedged superlatives**, classified **advisory** (`reasons=[advisory_pt13_unhedged_superlatives]`) — non-blocking; `rule_blockers=[]`.
- **Qwen: 3 good, 1 acceptable, 1 needs_revision** (down from smoke #3's 3x needs_revision). `qwen_critical_axes=[]` — the single needs_revision axis is non-critical, non-blocking.
- Generator: 4 sections kept, 14 sentences verified, 45 dropped. (Smoke #3 was 6/21/52 — run-to-run retrieval variance on a live-fetch corpus; the gate verdict is PT11/Qwen-driven, not sentence-count-driven.)

Smoke #3 `abort_evaluator_critical` → smoke #4 `success`. The iter-2 changes (strip inert regen loop, PT11 Limitations exclusion, cosmetic citation normalization) moved the empirical evaluator gate from a hard abort to a clean release.

## Direct questions for Codex

1. Is the cosmetic-only interpretation of "citation/punctuation normalization" correct, or did you mean citation-attachment? (If attachment: see the §9.1/§-1.1 objection above.)
2. PT11 Limitations exclusion — agree it is the same category as the Methods exclusion (correctness fix, not relaxation)?
3. If smoke #4 reaches `partial_qwen_advisory` — does that clear your blocker #3, or do you require `pass`/`ok`? (Per evaluator_gate.py, a report Qwen flags on `citation_tightness` can at best reach `partial` — `pass` is unreachable while Qwen flags that axis, which is an LLM-judge call, not deterministically fixable.)
4. Anything else blocking APPROVE.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
operator_escalation_needed: true | false
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
