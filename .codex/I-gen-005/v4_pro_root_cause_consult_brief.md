# Codex consultation — V4 Pro fabrication root cause + fix path

## Operator directive (verbatim 2026-05-25 night)

> "How other people resolve this problem? How codex think about it? Did
> you deepen the research on the root cause of the problem properly on
> github/api doc/and all relevent website, to truly identify the
> solution, could claude and codex both investigate and research deeper
> on this issue"

You (Codex) are being asked for an independent verdict on the V4 Pro
fabrication problem POLARIS is hitting. The operator wants the TRUE
root cause and the TRUE fix, not another patch. Please search the web
yourself; verify what I claim below.

## §8.3.1 cap directive (verbatim — Codex must respect)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What POLARIS observed (empirical, this session)

POLARIS pipeline configuration:
- Generator: DeepSeek V4 Pro via OpenRouter
- Evaluator: Gemma 4 31B via OpenRouter
- Post-hoc verifier: POLARIS strict_verify (per-sentence span validation)

Smoke test on `clinical_tirzepatide_t2dm` (real clinical RAG question):

### Iteration 1 — baseline (no fix)
- 16/127 sentences verified (13% pass rate)
- `no_provenance_token: 68` (V4 Pro missing `[ev_XXX]` markers entirely)
- `number_not_in_any_cited_span: 12` (fabricated clinical numbers)
- CoT leakage in rendered report: 2 instances ("Let's use ev_000...")
- status: `partial_evaluator_advisory`, release_allowed: False

### Iteration 2 — cold-temp + HARD-CONTRACT prompt
Changed `multi_section_generator._call_section` for reasoning-first models:
- Added explicit anti-CoT prompt ("DO NOT write 'Let me…'", forbidden opener list, demanded `[ev_XXX]` on every sentence, included a 2-sentence few-shot example)
- Temperature 0.3 → 0.1 on retry
- `reasoning_enabled=False` already default in `generate()` but V4 Pro reasons anyway (capped at 40% via I-bug-089)

Result: 23/61 sentences verified (38% pass rate). Big improvements:
- `no_provenance_token: 68 → 2` (citation discipline works)
- CoT leakage: 2 → 0
- Sections kept: 3 → 5
But `number_not_in_any_cited_span` UNCHANGED at 12. Gate still
partial_evaluator_advisory, release_allowed: False.

### Iteration 3 — added Pattern A (evidence-value allow-list)
Added `src/polaris_graph/generator/evidence_value_extractor.py`:
- Regex-scans each evidence's `direct_quote` for numbers, trial names, drug names
- Builds per-evidence allow-list, e.g. `ev_001: {82, 86, 5.4, 12.9, 0.45}`
- Injects into system prompt: "When you cite [ev_001], numbers MUST be from this set."
- Gated to `_REASONING_FIRST_MODELS` only (V4 Pro)

Result: **status: `success`, release_allowed: True, gate_class: pass** — first time the pipeline passed the gate. BUT:
- 28/101 sentences verified (28% rate; verified count up, generated more)
- `number_not_in_any_cited_span: 12 → 17` (UP, not down — allow-list ignored)
- `trial_name_mismatch: 3 → 24` (UP — V4 Pro confidently fabricating "SURPASS-3", "SURPASS-4" stats not in evidence)
- Judge: 3 good / 1 acceptable / 1 needs_revision
- Cost $0.06 → $0.23 (allow-list adds ~1.5K prompt tokens; V4 Pro generates more)

## Examples of what V4 Pro fabricates (real dropped sentences)

> "In SURPASS-3, a 52-week trial randomizing 1,444 patients (mean
> baseline HbA1c 8.12-8.21%, mean weight 93.8-94.9 kg) on metformin ±
> SGLT-2 inhibitors to tirzepatide 5, 10, or 15 mg versus once-daily
> insulin… [ev_017, ev_021]"

ev_017 + ev_021 contain NONE of those specific numbers. V4 Pro is
producing plausible-sounding pseudo-clinical paragraphs from prior
training, then attaching cite tags to evidence that doesn't support
them.

## Root cause hypothesis (please verify or refute)

Reasoning-induced instruction drift. Research from Explore agent
(verified by spot-check):

1. arxiv [2505.11423](https://arxiv.org/abs/2505.11423) "When Thinking
   Fails" (NeurIPS 2025) — VERIFIED title + authors via direct fetch.
   Claims CoT degrades instruction-following; specific percentages not
   in abstract (may be in body, needs body verification).
2. arxiv [2505.14810](https://arxiv.org/abs/2505.14810) "Scaling
   Reasoning, Losing Control" — UNVERIFIED. Agent Z claims hard
   constraint accuracy collapses to ~50% in high-capacity reasoning
   models.
3. arxiv [2603.05706](https://arxiv.org/abs/2603.05706) "Reasoning
   Models Struggle to Control CoT" — UNVERIFIED. Agent Z claims Claude
   Sonnet 4.5 controls CoT only 2.7% of the time.
4. arxiv [2601.01490](https://arxiv.org/abs/2601.01490) "Distortion
   Instead of Hallucination" — UNVERIFIED. Agent Z claims reasoning
   models DISTORT facts to comply with constraints rather than admit
   failure. **Most directly relevant if true** — POLARIS sees exactly
   this behavior.
5. arxiv [2510.00880](https://arxiv.org/abs/2510.00880) "HalluGuard" —
   VERIFIED title + 84.0% balanced accuracy + ORPO method. But does NOT
   specifically target fabricated numbers (general hallucination).

## OpenRouter constraints (binding)

- `guided_json`, `guided_regex`, `response_schema` (the CRANE-style
  constrained-decoding path) NOT exposed by OpenRouter for DeepSeek
  models. Would require self-hosting V4 Pro.
- `stop` parameter is supported via OpenRouter but not plumbed through
  POLARIS's `client.generate()` today (would need to add).
- `reasoning_effort` and `reasoning_enabled` ARE plumbed; we already
  set `reasoning_enabled=False` but V4 Pro reasons anyway (40% cap via
  I-bug-089).

## Architectural reality

V4 Pro WILL fabricate clinical numbers. POLARIS strict_verify catches
them post-hoc. Today's smoke produced 28 span-grounded verified
sentences out of 101 generated; the 73 dropped were V4 Pro's
fabrications, correctly caught. **The gate passed for the first time
with this configuration.**

## Your questions, Codex

Please answer with primary-source evidence:

1. **Is the "reasoning-induced instruction drift" thesis correct?**
   Search the web; verify the cited papers. If you find a stronger
   competing thesis, name it.

2. **Is V4 Pro's behavior (ignoring system-prompt allow-lists) a known
   property?** Find official DeepSeek docs / GitHub / community
   reports.

3. **What's the highest-confidence fix POLARIS can implement TODAY
   that doesn't require self-hosting?** Rank candidate paths:
   - A. Add Pattern C regen loop (catch fab → re-prompt with named bad numbers → retry once)
   - B. Plumb `stop` sequences through `client.generate()` (forbid known fab patterns like "SURPASS-3" if not in trial allow-list)
   - C. Add a separate small validator model (HalluGuard pattern) — but no published OpenRouter model is HalluGuard
   - D. Move allow-list from system to user message (production teams reportedly say V4 Pro weights user > system)
   - E. Reduce allow-list size (current ~1.5K tokens) to <300 tokens (lost-in-the-middle hypothesis)
   - F. Switch to function-calling-style request (V4 Pro outputs JSON `{sentence, citations[]}` per atomic claim) — would be major rework
   - G. **Accept current state.** Gate passes, release_allowed=True, 28 verified sentences across 6 sections is clinically-honest output. Optimize for verified-count not pass-rate. Ship.

4. **For the Carney demo on 2026-06-05 to 2026-06-09**: is the current
   28-verified-sentences-per-question state acceptable, given the
   alternative (V3.2-Exp) was operator-forbidden per
   [feedback_top_tier_model_only_2026_05_25](C:/Users/msn/.claude/projects/C--POLARIS/memory/feedback_top_tier_model_only_2026_05_25.md)?

5. **Most importantly:** if you (Codex) were the senior engineer
   on-call making this call before a demo to the Prime Minister of
   Canada, what would you ship?

## Output schema

```yaml
verdict: APPROVE_CURRENT | REQUEST_CHANGES
fix_recommendation:
  primary: <one of A-G above, or NEW>
  rationale: |
    Why this is the highest-confidence fix per primary-source evidence.
  secondary: <fallback if primary doesn't work>
verified_claims:
  - claim: "Reasoning-induced instruction drift is a documented phenomenon"
    verdict: TRUE | FALSE | UNCONFIRMED
    sources: [...]
  - claim: "V4 Pro ignores system-prompt allow-lists by design"
    verdict: TRUE | FALSE | UNCONFIRMED
    sources: [...]
  - claim: "Pattern A (allow-list injection) is the right primary fix"
    verdict: TRUE | FALSE | NEEDS_MORE_DATA
    sources: [...]
demo_recommendation: |
  Concrete: ship the current state as-is / iterate further / something else.
  Weigh operator's top-tier-model-only directive against demo safety.
fabricated_or_unverified_in_brief: [...]  # call out anything I claimed that you can't verify
remaining_blockers_for_execution: [...]
convergence_call: continue | accept_remaining
```

## Files for your context

- `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/manifest.json` — current smoke result
- `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/verification_details.json` — drop reasons
- `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/report.md` — actual generated report
- `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/reasoning_trace.jsonl` — what V4 Pro thought
- `src/polaris_graph/generator/multi_section_generator.py:880-980` — current generator code with all 3 fixes
- `src/polaris_graph/generator/evidence_value_extractor.py` — new Pattern A module
- `docs/v4_pro_root_cause_2026_05_25.md` — prior root cause doc
- `docs/v4_pro_academic_literature_2026_05_25.md` — Agent Z research synthesis
- CLAUDE.md §0.4 — top-tier-model-only directive (V3.2-Exp revert forbidden)

EMIT YAML PER SCHEMA. Do your own research; verify my claims; don't drip-feed.
