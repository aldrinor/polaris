# POLARIS DR Auto-Loop — In-Flight Handover (2026-04-20)

## Stop condition (current)

User mandate (2026-04-20): iterate until POLARIS beats BOTH ChatGPT DR
and Gemini DR head-to-head on 7 dimensions (citations, regulatory,
jurisdiction, claim-frames, structure, contradictions, narrative depth).
Competitor PDFs extracted to `state/compare_chatgpt_dr.txt` /
`state/compare_gemini_dr.txt`.

THRESHOLD-PASS is NOT the stop condition. "Matches tier-1" is not
enough; we need head-to-head victory on all 7 dimensions.

## State as of this handover

### Last sweep: V19 — ABORTED on PT11 false-positive
- Commit: `c7f4235` (M-29 jurisdictional-precision prompt)
- Status: `abort_evaluator_critical` / `rule_pt11_uncited_numeric_claims`
- Root cause diagnosed: PT11 regex treated `vs. ` as sentence boundary,
  leaving `10.7% vs. 4.8%, 8.1% vs. 2.7%, 5.7% vs. 1.2%` stranded from
  the `[7]` citation at the real sentence end. 4 false-positive decimals
  out of 43 — zero underlying quality defect.
- M-29 itself WORKED: V19 report has NO "both agencies / regulators
  require / authorities generally" overclaim.
- Pre-existing concern: V19 also had 3 outline JSON decode failures →
  fell back to 3 deterministic sections (755 words vs V18's 5 sections
  / 2922 words). Stochastic DeepSeek V3.2 brittleness, not caused by
  M-29. Tracked as task #8 (M-31).

### In-flight: M-30 Codex code audit
- Commit: `6056855` (`PL: M-30 — PT11 abbreviation-aware sentence
  boundary`)
- Tests: 724/724 (+17 M-30)
- Dispatched: `codex exec --full-auto < .codex/m30_code_audit_brief.md`
- Awaiting verdict at `outputs/codex_findings/m30_code_audit/findings.md`

### Next planned sequence
1. Codex M-30 verdict READY → V20 sweep
2. Codex DR audit pass 10 on V20 output with BEAT-BOTH head-to-head brief
3. If BEAT-BOTH: STOP
4. If not: implement next reconciled-plan fix (Fix B → Fix C → Fix A)
   and loop.

## Metric history (tirzepatide/T2D query)

| Sweep | Unique cites | Regulatory | T1+T2 | Words | Release | Notes |
|------:|-------------:|-----------:|------:|------:|:-------:|:------|
| V13   | 26           | 0          | 84.6% | 2100  | YES     | Threshold-pass pass 6 |
| V14   | —            | —          | —     | —     | NO      | Selector regression (M-26a) |
| V15   | —            | —          | —     | —     | NO      | Same-commit reproduction issue |
| V16   | 30           | 0          | 73.3% | —     | YES     | M-27 multi-source cite landed |
| V17   | 24           | 0          | 70.8% | 2077  | YES     | TOP-TIER threshold on pass 8 |
| V18   | 35           | 12         | 89% (T1+T2+T3) | 2922 | YES | M-28 regulatory retrieval landed |
| V19   | —            | —          | —     | 755   | **NO**  | PT11 false-positive (M-30 fixes) |

## Reconciled Claude+Codex fix plan (2026-04-20 deep compare)

From `outputs/codex_findings/v17_vs_tier1_deep_comparison/findings.md`
and `state/v17_vs_tier1_claude_deep_read.md`. Both agents agreed on
4 gap classes; disagreed on order. Reconciled order (ship lowest-risk
first — protects against M-26a-style regression):

1. ✅ Regulatory retrieval (M-28, V18)
2. ✅ Jurisdictional precision (M-29, V19, worked silently)
3. ✅ PT11 false-positive (M-30, this iteration)
4. ⏳ Primary-evidence claim frames (Fix B): force N + baseline +
   endpoint per named-study claim. Prompt-only. Low risk.
5. ⏳ Evidence-strength grammar + contradiction suppression (Fix C):
   noninferiority vs superiority labels; suppress >500% range
   artifacts. Low risk.
6. ⏳ Primary-entity sub-sections / trial matrix (Fix A): deepest
   structural change. Medium risk (M-26a history). Last.

## Commits this iteration

- `a278102` — DR audit pass 9 (V18 MATERIAL-GAPS verdict)
- `c7f4235` — M-29 jurisdictional precision
- `2ebe63a` — M-29 Codex code audit READY
- `6056855` — M-30 PT11 abbreviation boundary fix

## Task list

1. [in_progress] M-30: diagnose V19 PT11 failure (being audited by Codex)
2. [pending] Codex DR audit pass 10 — BEAT-BOTH verdict
3. [pending] Fix B: primary-evidence claim frames
4. [pending] Fix C: evidence-strength grammar
5. [pending] Fix A: primary-entity sub-sections
6. [pending] Deep-dive R2a-R2h (parked)
7. [pending] M-9 Pass 9 section-label alignment (parked)
8. [pending] M-31: outline JSON decode resilience (parked pending V20)

## Anti-regressions in the fix chain

- M-28 regulatory-anchor module has a CI-enforced no-hardcoded-hosts
  guard test (`test_m28_regulatory_expander_no_hardcoded_hosts`).
- M-29 jurisdictional-precision prompt uses placeholder "Jurisdiction
  A / B" pattern — no clinical hard-code.
- M-30 abbreviation list is standard English orthography — no
  domain-specific terms.
- PT11 fix preserves tolerance `uncited < max(3, len/10)` so real
  uncited decimals still flag.

## Environment

- Branch: `PL-honest-rebuild-phase-1`
- HEAD: `6056855` (post-M-30 commit)
- Tests passing: 724/724
- Cost-to-date this iteration: ~$0.30 (V16-V19 sweeps + Codex audits)
