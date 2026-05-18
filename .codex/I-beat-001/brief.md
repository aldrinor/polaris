# Codex BRIEF review — I-beat-001 / GH #400: finalize the BEAT-BOTH proof (definitive summary)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Pre-implementation **brief** review — you are reviewing the *plan* (acceptance-criteria correctness + the §-1.1 honesty of the planned consolidation), NOT a diff. The diff review is a separate later Codex call.

## 0.1 Operator-chosen path

#400 (I-beat-001) is the BEAT-BOTH proof. The operator was offered three completion paths and **explicitly chose "finalize as-is, no rerun"**: the §-1.1 line-by-line audit work is already done across 14 iterations; what is missing is a single definitive consolidated summary. The operator rejected (a) recalibrating the corpus-adequacy gate further and (b) swapping in curated-favorable questions. This PR is that finalization. Do NOT flag "should have run more questions / 15 triples not literally present" as P0/P1 — the operator made that scope call deliberately.

## 1. Issue + true current state

GH #400 asked for an end-to-end BEAT-BOTH proof. Since the 2026-05-11 issue body was written, the work advanced substantially:

- **I-tpl-009 (#405)** did a *principled* corpus-threshold recalibration — emerging-policy domains (`ai_sovereignty`, `workforce`, `policy`/housing, `canada_us`) were wrongly inheriting clinical T1+T2 thresholds; they now use domain-appropriate T2/T3/T4 thresholds (peer-reviewed policy + regulatory + think-tank are the *correct* primary sources for policy questions). This is a domain-mismatch correction, NOT a gate-weakening — it was its own Codex-reviewed issue.
- Post-recalibration, **all 5 Carney goldset questions (Q1-Q5) + the tirzepatide clinical question ran end-to-end** and were §-1.1 line-by-line audited.
- `cross_review_v12.md` is the real current audit state: **55 of ~85 deep claims** carry Claude + Codex *independent* verdicts. **0 FABRICATED, 0 UNREACHABLE** across all 55. POLARIS: 28 VERIFIED / 7 PARTIAL / 0 UNSUPPORTED across 35 claims (80%); ChatGPT DR 9/11 (82%); Gemini DR 6/10 (60%, 2 confirmed numeric errors).
- 2 correctable POLARIS prose-framing bugs were identified by the audit (Q3-C1 source attribution; Q5-C4 PBO-vs-Bill-C-64 framing) — neither is a fabrication.

**The problem:** the canonical-named `outputs/audits/I-beat-001/BEAT_BOTH_SUMMARY.md` is frozen at **v1** content; `_v2.md`/`_v3.md` exist but v3 is also stale — it still says "3 aborted" (pre-I-tpl-009). #400's acceptance names `BEAT_BOTH_SUMMARY.md` as the per-question + per-dimension verdict artifact; it currently misrepresents the result.

## 2. The change (plan)

**One deliverable file** + 2 GH issues + the issue close:

1. **Rewrite `outputs/audits/I-beat-001/BEAT_BOTH_SUMMARY.md`** as the definitive final consolidation, superseding v1/v2/v3 (which stay on disk as dated historical iterations). Content:
   - Methodology header: §-1.1 claim-by-claim, Claude + Codex independent verdicts, GRADE/AMSTAR-2/Cochrane-RoB-2 per domain; 5-verdict scale (VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE).
   - Per-question outcomes: all 5 Carney goldset questions + tirzepatide, with the post-recalibration produce/audit status.
   - Per-source verdict distribution (the cross_review_v12 table): POLARIS / ChatGPT DR / Gemini DR.
   - The honest BEAT-BOTH conclusion: all three produce 0 fabrications; POLARIS leads Gemini on first-pass decimal accuracy by ~20pp and ~ties ChatGPT; POLARIS uniquely refused/flagged corpora *before* I-tpl-009 recalibration and still surfaces evidence-tier transparency.
   - **Explicit honesty section** — what is NOT proven: claim coverage is 55/~85 (65%), not 100%; sample sizes too small for statistical significance; ChatGPT/Gemini DR fabrication rate on their *un-audited* claims is unknown; Codex CLI could not complete a single-call full-report audit (the cross-review used per-claim Codex calls).
   - The 2 correctable POLARIS bugs, linked to their new follow-up issue numbers.
   - Supersedes-note pointing at `cross_review_v12.md` as the claim-level evidence and v1/v2/v3 as historical.
2. **File 2 GH follow-up issues** (`gh issue create`) for the correctable bugs: (a) Q3-C1 attribution — the 75.5/68.4/62.6% AI-exposure decimals are cited to Goldman Sachs 2023 but match PWBM 2025; (b) Q5-C4 — the pharmacare Regulatory subsection frames PBO 2023 universal-plan numbers inside Bill C-64 phase-1 context. Both are prose-framing/citation-attribution, NOT fabrications.
3. **Close #400** on the consolidated honest result.

## 3. §-1.1 compliance — the central review point

The §-1.1 standard BANS metadata/count/pattern audits. This summary is **NOT** that: it is the *consolidation of a completed claim-by-claim audit*. Every count in it (28 VERIFIED, 0 FABRICATED, etc.) is the aggregate of 55 individual claims, each carrying a Claude verdict AND a Codex independent verdict against the actual cited source span — that work is in `cross_review_v1..v12.md` + `polaris/tirzepatide_full_audit_claude.md` + `polaris_q5/pharmacare_audit.md`.

**Verify:** the planned summary (a) states the methodology explicitly so a reader knows the numbers are claim-level audit aggregates, not pattern/metadata counts; (b) does NOT frame any "X vs Y count, therefore better" comparison of the banned type — the BEAT-BOTH conclusion must rest on per-claim faithfulness verdicts, not e.g. "POLARIS has fewer contradictions"; (c) does not overclaim — the honesty section must bound every claim. If the plan risks any of these, flag it.

## 4. Scope / diff shape

The deliverable lives in `outputs/audits/I-beat-001/` which the `codex-required` CI gate **excludes** from the canonical diff (along with `.codex/I-beat-001/`). So the canonical diff will be effectively just the `state/polaris_restart/iteration_trajectory.md` append. This is expected and correct — the BEAT_BOTH_SUMMARY *is* an issue audit artifact and legitimately lives under `outputs/audits/I-beat-001/`. The later Codex **diff** review will be pointed directly at the `BEAT_BOTH_SUMMARY.md` content, not just the canonical diff. No production code, no test, no config changes — zero runtime risk.

## 5. Files I have ALSO checked and they're clean

- `outputs/audits/I-beat-001/cross_review_v12.md` — the latest/most-complete cross-review (55 claims); the consolidation source of truth. NOT modified.
- `outputs/audits/I-beat-001/BEAT_BOTH_SUMMARY_v3.md` + `_v2.md` — stale earlier iterations; kept as dated history, NOT modified.
- `outputs/audits/I-beat-001/carney_goldset_q1_q5_results.md` — the 2026-05-11 pre-recalibration per-question detail; kept as history.
- `outputs/audits/I-beat-001/polaris/`, `polaris_q5/` — per-question audit JSON+MD; the claim-level evidence; NOT modified.
- `docs/polaris_locked_scope.md` §3.2 — confirms strict-verify + two-family segregation are locked invariants; the summary's framing is consistent with it.

## 6. Acceptance criteria for THIS PR

1. `BEAT_BOTH_SUMMARY.md` rewritten as the definitive consolidation; supersedes v1/v2/v3; faithfully reflects `cross_review_v12.md`.
2. Methodology + honesty-bounds sections present; no banned metadata-comparison framing; no overclaim.
3. 2 follow-up GH issues filed for the correctable bugs; referenced in the summary.
4. #400 closed on the honest result.

## 7. Required output schema (§8.3.9)

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
