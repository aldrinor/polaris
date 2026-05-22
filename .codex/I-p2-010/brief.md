# Codex BRIEF review — I-p2-010 (#749): contradiction / refusal panel

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
A reusable **contradiction / refusal panel** — surfaces genuine source disagreement AND honest pipeline refusals as FEATURES (the trust differentiator: POLARIS shows conflict + declines rather than fabricating).

## Verified current state (grounded — REAL fields)
- `ContradictionSignal { disagreeing_source_count, summary, sides?: ContradictionSide[], kind?: "multi_source"|"self_contradiction", category? }` (api.ts).
- `ContradictionSide { source_id, source_tier: "T1"|"T2"|"T3", sample_size?, hedge_language, pt08_flag?, claim_excerpt, evidence_type?, jurisdiction? }`.
- Refusal = the abort pipeline statuses: abort_scope_rejected, abort_corpus_inadequate, abort_corpus_approval_denied, abort_no_verified_sections (api.ts:72-75 + the manifest verdict).
- #742 tokens; VerdictChip (#744) has contradiction + refusal verdicts.

## Acceptance criteria (diff implements; brief reviews the plan)
1. `web/components/contradiction/contradiction_panel.tsx`: props = `contradictions?: ContradictionSignal[]` + `refusalStatus?: string | null` (an abort_* status).
2. REFUSAL (when refusalStatus is an abort_*): an honest, feature-framed card — "POLARIS declined to answer" + the specific reason mapped from the status:
   - abort_scope_rejected → "The question is outside POLARIS's research scope."
   - abort_corpus_inadequate → "Not enough qualifying sources to answer responsibly."
   - abort_corpus_approval_denied → "The source set failed approval (material tier deviation)."
   - abort_no_verified_sections → "No claim could be verified against a primary source."
   - Unknown abort_* → a generic honest "Declined — see run status." (no fabricated reason).
3. CONTRADICTIONS: render each ContradictionSignal — summary, "N sources disagree", kind badge, and per side: tier, claim_excerpt, jurisdiction/hedge if present. Real fields only.
4. Honest framing: refusal is a FEATURE not an error (calm, not alarming red); contradiction is shown faithfully. Frontier-Minimal; #742 tokens (contradiction=amber, refusal=neutral); WCAG 2.2 AA.

## Files I have ALSO checked and they're clean
- web/lib/api.ts (ContradictionSignal/Side/Kind + abort statuses), web/components/verdict/verdict_chip.tsx (#744 contradiction/refusal), web/app/globals.css (#742 tokens).

## Review focus
1. Refusal mapping correct + complete vs the 4 abort statuses + an honest unknown-fallback (no fabricated reason)?
2. Contradiction rendering uses only real ContradictionSignal/Side fields (no invented fields)?
3. Honest framing (refusal as feature, not alarming error)? tokens/a11y. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```

---
## iter-2 clarification (review scope)
This is a BRIEF / PLAN review, NOT a diff review. The component web/components/contradiction/contradiction_panel.tsx is INTENTIONALLY not yet implemented — it is built AFTER this brief is APPROVE'd (per the issue-driven workflow: brief → Codex brief APPROVE → diff → Codex diff APPROVE). "File does not exist" is the expected pre-implementation state, NOT a defect in the plan. Please evaluate the PLAN's correctness: (a) is the refusal-status→message mapping correct + complete vs the 4 abort statuses + honest unknown-fallback; (b) does the contradiction rendering use only real ContradictionSignal/ContradictionSide fields; (c) is the honest framing (refusal as feature) right. APPROVE iff the PLAN is sound; reserve P0/P1 for real plan defects (wrong field, wrong mapping, honesty violation), not the absence of the not-yet-written file.
