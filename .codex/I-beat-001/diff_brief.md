# Codex DIFF review — I-beat-001 / GH #400: finalize the BEAT-BOTH proof

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #400. Because the deliverable —
`outputs/audits/I-beat-001/BEAT_BOTH_SUMMARY.md` — lives in a path the
`codex-required` gate **excludes** from the canonical diff, the canonical diff
(`.codex/I-beat-001/codex_diff.patch`) is effectively just the
`state/polaris_restart/iteration_trajectory.md` append. **Review the actual
deliverable directly: `outputs/audits/I-beat-001/BEAT_BOTH_SUMMARY.md`** (commit
`d0bf1689`, +152/-91). It implements the Codex-APPROVE'd brief
`.codex/I-beat-001/brief.md` (brief APPROVE iter 1, 4 P2s folded in).

This PR finalizes #400 — the operator chose "finalize as-is, no rerun". It is a
pure documentation consolidation: no production code, no test, no config. v1/v2/v3
`BEAT_BOTH_SUMMARY` files stay on disk as dated history.

## 2. The change

`outputs/audits/I-beat-001/BEAT_BOTH_SUMMARY.md` rewritten as the definitive
consolidation of `cross_review_v12.md` (the completed 55-claim Claude+Codex
§-1.1 cross-review). Supersedes the stale v3 (which still said "3 aborted",
pre-I-tpl-009).

## 3. Verify against the brief + §-1.1

1. **§-1.1: not a banned metadata audit.** The summary must read as the
   *consolidation of a claim-by-claim audit* — methodology stated (§1), every
   count an aggregate of individually Claude+Codex-verdicted claims. Confirm it
   does NOT drift into "fewer X, therefore better" metadata framing.
2. **Audited-sample bounding (brief P2-1).** Every BEAT-BOTH rate must be
   explicitly bounded to the 55-claim audited sample; the competitor
   un-audited remainder must be stated as unmeasured (§5).
3. **Q1-Q4 wording (brief P2-2).** The summary must say Q1-Q4 produced reports
   + sampled deep cross-review (not full per-sentence audits); coverage 55/~85.
4. **GRADE scoping (brief P2-3).** GRADE / Cochrane RoB 2 scoped to clinical
   (tirzepatide) claims; policy claims under tier/source-appropriateness.
5. **#422 de-dup (brief P2-4).** §6 must reference #422 (closed) for Q5-C4 and
   #586 for Q3-C1 — confirm no duplicate of #422 was implied as newly filed.
6. **No overclaim.** The honesty-bounds section (§5) must bound coverage,
   significance, and the Codex-CLI whole-report limitation.
7. **Numbers match the source.** Spot-check the §3 table against
   `cross_review_v12.md`: POLARIS 28V/7P/0U/0F across 35; ChatGPT 9/11; Gemini
   6/10 + 1 UNSUPPORTED; 0 FABRICATED / 0 UNREACHABLE across 55.

## 4. Files I have ALSO checked and they're clean

- `cross_review_v12.md` — the consolidation source of truth; NOT modified.
- `BEAT_BOTH_SUMMARY_v2.md` / `_v3.md` / `carney_goldset_q1_q5_results.md` —
  kept as dated history; NOT modified.
- `outputs/audits/I-beat-001/polaris/`, `polaris_q5/` — per-question claim
  evidence; NOT modified.
- GH#422 (I-gen-001) — verified CLOSED and a genuine match for the Q5-C4 bug;
  GH#586 (I-bug-117) — filed for Q3-C1.

## 5. Verification state

No code/test/config changed — nothing to smoke-test. The deliverable is a
markdown consolidation; its claim-level numbers are traceable to
`cross_review_v12.md`. `outputs/audits/I-beat-001/claude_audit.md` §3 records
the per-P2 verification.

## 6. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
