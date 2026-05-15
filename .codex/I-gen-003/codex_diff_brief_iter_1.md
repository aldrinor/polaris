HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-gen-003 diff iter 1 — V4 Pro generator: SHIP-vs-REVERT decision

Brief review AND diff review combined. **Full brief at `.codex/I-gen-003/brief.md` — READ IT FIRST.** It carries the honest smoke #3 result and the three-option decision axis. This file is the diff-side summary; the brief is the decision document.

## This is not a clean APPROVE request — it is a decision request

The smoke #3 on V4 Pro returned `status=abort_evaluator_critical` — it did **NOT** meet the brief's stated PASS criterion (`status=ok*`/`partial*`). I am not asking you to rubber-stamp; I am asking you to choose (a)/(b)/(c) from brief.md §"The decision for Codex".

## Diff — 5 changes, ~115 src LOC (2 files)

`.codex/I-gen-003/codex_diff.patch` (canonical-diff-sha256 trailer included). Commits on branch: `0c55a4bc` (changes 1+2+3), `9a62ac1b` (PG_MAX_COST_PER_RUN), + 1 new commit (changes 4+5 + change-2 escalation).

1. `_call_section` HARD OUTPUT CONTRACT (reasoning-first, tighter_retry path).
2. `_run_section` single retry `if` → bounded `while`; `_regen_needed()` fires at `total_in==0` too; `_max_regens=3` reasoning-first; **retry budget escalates `base*(1+0.5*N)` → 30k/40k/50k**.
3. `PG_GENERATOR_MODEL` → `deepseek/deepseek-v4-pro`; `PG_MAX_COST_PER_RUN` `0.10→10.00`.
4. NEW `ReasoningFirstTruncationError(RuntimeError)`; I-bug-089 SF-15 raises it (not bare `RuntimeError`); `PG_REASONING_FIRST_MIN_MAX_TOKENS` `6000→20000`.
5. `_call_section` catches `ReasoningFirstTruncationError` → loud WARNING → returns `("", 0, 0)` (crash → honest abort).

## Smoke #3 — the empirical result (honest)

`abort_evaluator_critical`, $0.0746, ~37 min wall.

**Worked (changes 4+5, load-bearing):** V4 Pro completed all 6 sections, **zero `ReasoningFirstTruncationError`** (20000 floor held). `sentences_verified=21` (vs V3.2-Exp baseline 13), 1398-word Analyst Synthesis.

**Did not work:**
- `abort_evaluator_critical` — PT11 FAIL (3/24 numerics uncited) + Qwen `needs_revision` ×3 (citation_tightness, flow, completeness). These are **generator output failures**, not downstream noise. V3.2-Exp got `ok_qwen_advisory` on the same question — V4 Pro is one gate-threshold worse.
- **Changes 1+2 are EMPIRICALLY INERT on V4 Pro.** 12 regen attempts, **zero** verified-sentence lift (kept_fraction byte-identical across all 3 regens per section: Efficacy 0.10×3, Safety 0.25×3, Regulatory 0.36×3, Comparative 0.18×3). ~20 of 37 wall-min wasted. Shipped labelled-honest, not pretending-to-work — **diff-review question: strip or keep as scaffold?**

## Key diff-review questions

1. **Decision (a)/(b)/(c)** per brief.md. If (b) — revert `PG_GENERATOR_MODEL` to V3.2-Exp, keep changes 4+5 — note this **contradicts the operator's repeated "I want V4 Pro" directive**; flag `operator_escalation_needed: true`.
2. Changes 1+2 inert regen loop — strip (revert `_call_section`/`_run_section` to pre-`0c55a4bc`) or keep? It is dead weight on V4 Pro but harmless to non-reasoning-first models.
3. `_call_section` returning `("", 0, 0)` on caught truncation — truncated-call token counts lost from section telemetry (run-cost ContextVar still tracks $). Acceptable?
4. PT11 / citation_tightness — in I-gen-003 scope (post-generation citation-binding pass) or follow-up Issue?
5. Anything else blocking.

## Diff hygiene checks (done)

- Non-reasoning-first regression surface: `_max_regens=1`, `total_in>0` gate half, `if model in _REASONING_FIRST_MODELS` guards → V3.2-Exp/qwen/GLM byte-identical.
- `_REASONING_FIRST_MODELS` (v4-pro+v4-flash) ≠ `_ALWAYS_REASON_MODELS` (GLM) — separate code paths; floor raise does not touch GLM.
- `_call_section` `finally` (client close) runs on the new `except` path — verified.
- `BudgetExceededError` (also `RuntimeError`) still propagates — the `except` is `ReasoningFirstTruncationError`-specific.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
decision: a | b | c
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
operator_escalation_needed: true | false
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
