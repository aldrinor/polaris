HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff gate — beat-both Wave A (WS-0/WS-1/WS-2/WS-5/WS-6)

Review the consolidated diff `.codex/I-deepfix-001/wave_a_consolidated.patch` (1688 lines, 10 files). Read the touched files for context. Spec = `.codex/I-deepfix-001/BEATBOTH_PLAN_CORRECTIONS.md` (operator locked ALL-GLM) + `BEATBOTH_MASTER_PLAN.md` WS-0/1/2/5/6 + the audit `.codex/I-deepfix-001/RESMOKE_S11_FORENSIC_AUDIT.md`. Repo root C:/POLARIS.

## §-1.3 + frozen-engine law (your P0 checklist)
POLARIS is WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP. The faithfulness engine (strict_verify / NLI / verify_sentence_provenance / the 4-role D8 verdict LOGIC / span-grounding) is FROZEN. `git diff --name-only` over the engine files is empty — CONFIRM it stays empty. Every WS behind a default-ON kill-switch reverting byte-identical. No hard-drop of a source.

## The 5 workstreams (verify each does exactly what it claims, nothing more)

**WS-1 — GLM-5.2 D8 judge reliability (judge_adapter.py +405, openrouter_role_transport.py +51). FAITHFULNESS-ADJACENT — highest scrutiny.** Operator locked ALL-GLM (NO model swap; PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY stays 1, safeguard disclosed-off). Changes: (a) enforce the verdict enum via OpenRouter response_format/json_schema (PG_JUDGE_ENUM_RESPONSE_FORMAT); (b) bounded per-claim retry before the fail-closed degrade (PG_JUDGE_RETRY_BEFORE_DEGRADE); (c) verdict idempotency cache keyed on (normalized_claim, span-identity) (PG_JUDGE_VERDICT_IDEMPOTENCY); (d) raised seam wall.
- **CONFIRM:** the 4-role verdict DECISION LOGIC is UNCHANGED — only transport/enum/cache/wall wrapped. A real UNSUPPORTED still convicts; only transport-noise (blank/429) triggers a retry, never a conviction and never a spurious VERIFIED. The idempotency cache key must be tight enough that TWO DIFFERENT claims never share a cache entry (only true byte-twins on the same span), and must not let a stale/poisoned verdict leak across runs. A cache miss must fall through to a real judge call, never a default-VERIFIED. Any path where the cache or retry can turn a genuine UNSUPPORTED into VERIFIED is a P0.

**WS-5 — D1 caveat re-key (report_redactor.py +153, overstatement_guard.py +114, run_honest_sweep_r3.py caller). FAITHFULNESS-ADJACENT.** FIX-a: a claim sharing BOTH a span-identity tuple AND a numeric figure with a flagged (non-VERIFIED) claim inherits its `[confidence: …]` marker (ADVISORY twin — never triggers the fail-closed abort that mandatory non-VERIFIED claims do). FIX-b: effect_size_conditional_reason appends a caveat when a bare numeric re-lift's span has a governing conditional near the number. PG_FIGURE_CONSISTENCY_ANNOTATE default-ON.
- **CONFIRM:** it ONLY ADDS caveats — it never removes a mandatory non-VERIFIED label, never mutates a verdict, never widens a span. The implementer scoped FIX-a to span-tuple AND shared-figure (not pure span) to avoid falsely caveating a genuinely-VERIFIED non-figure claim on the same span — judge whether span+figure is correct or too narrow/broad. The inherited marker wording ("NOT confirmed by the cited source") is applied to a twin — is that accurate at the figure level, or should it soften to "a sibling claim on this figure was not confirmed"?

**WS-6 — D2 corroboration count (run_honest_sweep_r3.py _basket_corroboration_block).** count = min(recompute, int(basket.verified_support_origin_count or 0)); 0-count → "0 verified independent source(s)" + route to GROUNDED-BUT-WEAK; PG_CORROBORATION_COUNT_AUTHORITATIVE default-ON. CONFIRM: it only ever REDUCES an inflated count (never inflates); sources stay in the numbered Bibliography (no §-1.3 drop).

**WS-2 — winner-slate completion (run_gate_b.py +69, operational_readiness_preflight.py +13).** Adds PG_CROSS_SOURCE_SYNTHESIS to _FULL_CAPABILITY_BENCHMARK_SLATE + required-flags + force-on + allowlist + a fail-loud assert_cross_source_synthesis_fired; op-readiness paid preflight RED-blocks a slate-OFF launch on the 3 winner flags; PG_DOCUMENT_TYPE_WEIGHT deliberately NOT added. CONFIRM: the fail-loud assert only bites when the flag is ON; the preflight meta-governance guard does not weaken the existing breadth RED gates; no faithfulness impact (M6 producer untouched, each analytical atom re-passes strict_verify).

**WS-0 — GPU device split (NEW scripts/dr_benchmark/gpu_device_split.py).** Advisory launch config (2-card split + PG_CONTENT_RELEVANCE_SCORE_CHUNK=2 + co-residence preflight warning). CONFIRM: pure config/advisory — when the template is not sourced, device envs stay unset = byte-identical; the 5 env vars target their real consumers.

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
frozen_engine_untouched: true | false
s13_violations: [...]
ws1_cache_or_retry_can_flip_unsupported_to_verified: true | false   # the WS-1 P0 check
ws5_only_adds_caveats_never_mutates_verdict: true | false
ws6_only_reduces_count: true | false
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
