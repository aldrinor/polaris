# I-gen-003 — Claude architect audit

**Issue:** GH#495 — make DeepSeek V4 Pro work as the multi_section generator
**Branch:** `bot/I-gen-003-v4pro-cot-handler`
**Auditor:** Claude (architect review, independent of the diff-authoring pass)
**Date:** 2026-05-14

## Scope of this audit

Five changes across two files. This audit reviews each change against: (a) the operator directive ("V4 Pro is THE generator, V3.2-Exp obsolete"), (b) the empirical smoke evidence, (c) regression surface for non-reasoning-first models, (d) LAW II (no silent fallbacks), (e) the 200-LOC PR cap.

## Change-by-change review

### Change 1 — `_call_section` HARD OUTPUT CONTRACT (committed `0c55a4bc`)

- **Correct.** Appended only on `tighter_retry=True` AND `model in _REASONING_FIRST_MODELS`. The contract is an explicit anti-CoT instruction — it targets the exact failure mode (planning prose with no `[ev_XXX]` markers).
- **Regression surface:** the `if model in _REASONING_FIRST_MODELS` guard means non-reasoning-first models never see the block. First pass is untouched for all models. **Clean.**
- **Risk:** the contract is prompt-only — a model can still ignore it. Mitigated by being one of three layers (contract + multi-retry + budget escalation), not the sole recovery.

### Change 2 — `_run_section` gated multi-retry + budget escalation (committed `0c55a4bc`, MODIFIED this iter)

- **`_regen_needed()` predicate:** for non-reasoning-first, preserves the exact original `total_in > 0` gate. For reasoning-first, also fires at `total_in == 0` — this is the *intended* fix for the silent-empty-section bug (V4 Pro emits unparseable planning → strict_verify parses zero sentences → old gate skipped the retry).
- **Bounded `while` loop:** `_max_regens = 3` reasoning-first / `1` else. Non-reasoning-first → exactly one iteration possible → byte-identical to the prior single `if`. **Clean.**
- **Budget escalation (new):** `_retry_max_tokens = int(_regen_base_max_tokens * (1 + 0.5 * _regen_count))` for reasoning-first; `max_tokens_per_section` (unchanged) for others. `_regen_base_max_tokens = max(max_tokens_per_section, _reasoning_first_floor)`. This is the advisor-flagged fix: same-budget retries would truncate identically. Escalation 1.5×/2.0×/2.5× on a 20000 base → 30k/40k/50k.
- **Post-filter metric recompute after a winning retry:** `post_filter_kept` + `post_filter_fraction` are recomputed inside the `if len(report2_kept_after_m41c) > post_filter_kept:` branch, so `_regen_needed()` re-evaluates against the winning draft. **Correct** — without this the loop could spin on stale metrics.
- **Risk — loop exit:** the loop exits on `_regen_count >= _max_regens` even if `_regen_needed()` is still True. That is intentional (bounded). Result: section ships whatever the best draft was (possibly empty) → handled honestly downstream by `dropped_due_to_failure`.

### Change 3 — `PG_GENERATOR_MODEL` default → `deepseek/deepseek-v4-pro` (committed `0c55a4bc`)

- **Correct per operator directive.** The I-bug-091 revert rationale is replaced, not just deleted — the comment now records *why V4 Pro works now* (the I-gen-003 mechanisms). Future readers see the full history.
- Also on-branch (commit `9a62ac1b`): `PG_MAX_COST_PER_RUN` default `0.10 → 10.00`. Reviewed: the `0.10` cap was V3.2-era and false-fired on V4 Pro's normal cost profile (smoke #1 died on it at `$0.1008`). `10.00` matches `v30_runner.py` and still catches a genuine runaway. **Justified.**

### Change 4 — `ReasoningFirstTruncationError` + raised reasoning-first floor (NEW this iter)

- **Typed exception:** `ReasoningFirstTruncationError(RuntimeError)`. The I-bug-089 SF-15 check now raises this instead of a bare `RuntimeError`. **Correct** — this is what lets change 5 catch *only* truncation. `BudgetExceededError` is also `RuntimeError`-derived but distinct, so a real budget breach still propagates.
- **Floor `6000 → 20000`:** smoke #2 is the empirical basis — V4 Pro emitted ~5300+ reasoning tokens and was *still* truncated at the 6000 ceiling. The I-bug-090 estimate ("~2500 reasoning tokens") was wrong; the comment is updated with the corrected evidence. 20000 → ~5–8k reasoning + ~12–15k content headroom.
- **Risk:** 20000 is a guess — V4 Pro's *natural* (uncapped) reasoning length is unknown because smoke #2 capped it. Mitigated by (a) env-tunability (`PG_REASONING_FIRST_MIN_MAX_TOKENS`), (b) the change-2 escalation backing it. If 20000 still truncates, the smoke will show it and the floor gets raised again — the error is the instrument.
- **Scope check:** the floor sits in the `elif self.model in _REASONING_FIRST_MODELS:` branch (only v4-pro + v4-flash). GLM models use the *separate* `_ALWAYS_REASON_MODELS` branch — untouched.

### Change 5 — `_call_section` catches `ReasoningFirstTruncationError` (NEW this iter)

- **Correct layering.** The exception was raised inside `client.generate()`, propagating up and crashing the run before `_run_section`'s regen loop could engage. Catching it in `_call_section` and returning `("", 0, 0)` lets the regen loop do its job.
- **LAW II compliance:** this is *not* a silent fallback. The catch logs a loud WARNING (section, model, max_tokens, tighter_retry, exception detail). The empty draft surfaces in section telemetry. If all retries truncate, the section ends empty → `abort_no_verified_sections` (an honest pipeline verdict, §9.3) — never a masked success.
- **`finally` interaction:** verified — `return` inside the `except` still runs the `finally` (client close) before completing. No leaked client.
- **Telemetry gap:** the truncated call's input/output token counts are lost (`0, 0` returned). The run-cost ContextVar still tracks the actual $ for the budget guard, so the cost cap is unaffected — only the per-section token tally under-reports. Flagged to Codex as a direct question (acceptable vs. thread-the-counts-out).

## Cross-cutting checks

- **200-LOC cap:** diff is ~115 src LOC added/changed across the two files. **Under cap.**
- **Import hygiene:** `ReasoningFirstTruncationError` + `_REASONING_FIRST_MODELS` added to the existing `_call_section` local import; `_REASONING_FIRST_MODELS` already locally imported in `_run_section`. No new top-level imports, no wildcard. `os` already imported (line 36).
- **Two-family invariant:** untouched — this is generator-side only; `PG_EVALUATOR_MODEL` (Gemma 4 31B) unchanged.
- **§9.1 invariants:** provenance tokens, strict_verify, zero-verified-abort all unchanged — change 5 *routes into* the zero-verified-abort path honestly rather than bypassing it.
- **`_call_section` signature unchanged** — all call sites (lines 1143, 1271 first-pass + retry) pass positionally; the new `except` is internal. No caller breakage.

## Smoke #3 result — HONEST

`run_honest_sweep_r3.py --only clinical_tirzepatide_t2dm`, V4 Pro, 2026-05-14.
**`status=abort_evaluator_critical`, $0.0746, ~37 min wall.**

**This did NOT meet the brief's stated PASS criterion** (`status=ok*`/`partial*`). Stating that plainly, not slipping past it.

### Changes 4+5 — load-bearing, CONFIRMED WORKING
- Zero `ReasoningFirstTruncationError` raised — the 20000 floor held; V4 Pro completed all 6 sections without a truncation crash. The I-bug-091 revert reason ("V4 Pro crashes the pipeline") is genuinely fixed.
- Generator produced a complete report: `sections_kept=6`, `sentences_verified=21` (vs V3.2-Exp baseline 13), `sentences_dropped=52`, 1398-word Analyst Synthesis.

### Changes 1+2 — EMPIRICALLY INERT on V4 Pro
- 12 regen attempts (3 × Efficacy/Safety/Regulatory/Comparative) lifted **zero** verified sentences. kept_fraction byte-identical across all 3 regens per section. The HARD OUTPUT CONTRACT + escalated budget did not change V4 Pro's output style. ~20 min of the 37-min wall wasted on regens that produced nothing. This is dead code on V4 Pro as it stands — flagged to Codex (strip vs keep-as-scaffold).

### The evaluator abort — generator output failures, not "downstream"
- PT11 FAIL: 3/24 numeric claims uncited — V4 Pro citation discipline.
- Qwen `needs_revision` ×3: citation_tightness (uncited claims in Safety/Mechanism/Regulatory), flow (Efficacy collapsed to 1 sentence), completeness (1 uncovered corpus topic — this one not a generator fault).
- V3.2-Exp got `ok_qwen_advisory` on the same question — V4 Pro trips the gate one threshold worse despite verifying more sentences.

## Verdict — REVISED after smoke

**NOT a clean PASS. This is a SHIP-vs-REVERT decision that belongs to Codex, not to me.**

- The architecture of changes 4+5 is sound and confirmed working — the crash fix is real and load-bearing.
- Changes 1+2 are inert on V4 Pro — my own design (HARD OUTPUT CONTRACT + regen loop) did not deliver; the 12-retry/zero-lift data is unambiguous.
- The honest question is (a) ship V4 Pro at this quality, (b) revert `PG_GENERATOR_MODEL` to V3.2-Exp keeping changes 4+5 as future-model insurance, or (c) a specific harder generator-side intervention. Option (b) collides with the operator's repeated "I want V4 Pro" directive and would need operator escalation.
- I am NOT declaring this done, and I am NOT declaring it needs-rework, on my own judgment. The brief + this audit go to Codex with the decision framed honestly; Codex adjudicates.

## Iter 2 — addressing Codex iter-1 REQUEST_CHANGES (decision c)

Codex iter 1: REQUEST_CHANGES, decision (c) — keep changes 4+5, strip the inert regen loop, add deterministic citation/punctuation normalization + PT11 handling, fix the GLM bug. It also caught a real diff bug.

### What changed (commit `cb7feaa3`)
- **Stripped changes 1+2** — `_call_section` HARD OUTPUT CONTRACT and `_run_section` bounded regen loop + budget escalation reverted to pre-`0c55a4bc`. Smoke #3 proved them inert (12 retries, zero lift). Change 5 (the `except ReasoningFirstTruncationError` clause) retained.
- **Fixed the GLM bug Codex caught** — `_REASONING_FIRST_MODELS = frozenset({*_ALWAYS_REASON_MODELS, ...})` genuinely is a superset; my iter-1 brief's "GLM untouched" claim was wrong. Stripping changes 1+2 removes the only `_is_reasoning_first` branch — no `_REASONING_FIRST_MODELS` membership test remains in the generator. Verified.
- **PT11 Limitations exclusion** (`external_evaluator.py`) — `prose_only` now also stops at the Limitations block. The Limitations section is POLARIS-generated meta-prose (corpus-skew %, contradiction-detector relative-difference telemetry, completeness-gap counts) — the same "specifications not empirical claims" category PT11 already excludes for Methods. This is a correctness fix, not a relaxation: the Analyst Synthesis stays IN PT11 scope (verified by `test_pt11_still_flags_uncited_decimals_in_body_and_synthesis`).
- **`_normalize_citation_punctuation`** — cosmetic pass after provenance resolution: inserts a missing sentence terminator at genuine boundaries, normalizes marker spacing. **Byte-preserves every marker + evidence ID** — verified by test. I deliberately did NOT implement citation-*attachment* (attaching a marker the generator didn't emit is fabrication — §9.1/§-1.1 hard line); flagged that interpretation to Codex explicitly.
- Stale-comment fixes in `openrouter_client` (Codex P3).
- 7 new tests; 387 generator+evaluator+PT11 tests pass, zero regressions.

### Iter-2 verdict
Architecturally sound and tightly scoped. The strip removes empirically-dead code + a real bug in one move. The PT11 exclusion is the load-bearing abort→partial fix and is a defensible correctness change. The normalization pass is cosmetic-safe by construction. The one open interpretation question (cosmetic-normalization vs citation-attachment) is flagged to Codex, not hidden. Smoke #4 result is the empirical gate — appended to the iter-2 diff-brief and below.

### Smoke #4 result — PASS
`run_honest_sweep_r3.py --only clinical_tirzepatide_t2dm`, V4 Pro, 2026-05-15.
**`status=success`, `release_allowed=true`, `gate_class=pass`, $0.0763, ~25 min wall.**

Smoke #3 `abort_evaluator_critical` → smoke #4 `success`. The iter-2 PT11 Limitations
exclusion resolves the PT11 FAIL (12/13 rule checks pass; the 1 fail = PT13
unhedged superlatives, advisory/non-blocking). Qwen 3 good / 1 acceptable / 1
non-critical needs_revision; `qwen_critical_axes=[]`. Generator kept 4 sections,
14 verified sentences (run-to-run retrieval variance vs smoke #3's 6/21). The
V4 Pro generator now produces a releasable, gate-passing report — the I-gen-003
objective (make V4 Pro work as the generator) is empirically met.
