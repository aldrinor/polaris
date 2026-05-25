# Codex 12-page specialization mega-audit — I-ux-001d TRACK 3 (iter 1)

## §0 cap directive (verbatim CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iter count.
- "Don't pick bone from egg."
- Verdict APPROVE iff zero P0/P1.
```

## Scope

Per Codex iter-3 D3 cadence: "1 all-22-frame mega contact-sheet audit; per-page audits only for the A+ critical path or any page flagged by the mega audit."

This is the mega-audit on the 12 desktop page heros that specialize the 5 family templates (TRACK 2 APPROVED). Mobile variants will be a separate batch per the D3 cadence; the mega audit on desktop locks the page-level grammar first.

## What's being audited

12 desktop page heros in `web/p2shots/I-ux-001d/page_specializations/`:

| # | Page | Family | Tier | Notes |
|---|---|---|---|---|
| 01 | /home | marketing-auth | A+ | proof-as-CTA hero w/ real verified claim |
| 02 | /intake | edit-mode | A+ | just-ask input + decision-rationale + 3-button gate (Proceed/Amend/Refuse) + source-set chips |
| 03 | /source_review | edit-mode | A+ | step-2-of-intake; corpus adequacy check + tiered source list |
| 04 | /plan | edit-mode | A+ | step-3-of-intake; editable section plan + token budget + failure modes disclosed |
| 05 | /runs/[runId] | monitor-mode | A+ | live event stream + depth checklist + per-tier counter |
| 06 | /inspector/[runId] | read-mode | A+ CENTERPIECE | v6 hero (Codex iter-3 APPROVED) + intended-use strip overlay |
| 07 | /compare | read-mode | A+ | two-brief comparison with axis disclosure + contradiction flag |
| 08 | /runs/[runId]/graph | spatial | A+ | force-directed + focal spotlight + Expand/PNG/zoom controls |
| 09 | /runs/[runId]/audit | read-mode | A | 8-field manifest disclosure + signed bundle pill |
| 10 | /sign-in | marketing-auth | A | institutional auth, no proof block, 8 institution names |
| 11 | /dashboard | monitor-mode | A | run-list view: in-progress + completed + recent verdicts |
| 12 | /transparency | marketing-auth | A | long-read disclosure of models / data residency / verifier limits / GPG key |

## What I want from this mega-audit

1. **Specialization sufficiency.** Does each page read as its own thing — Intake feels like asking, Inspector feels like reading, Knowledge-graph feels like exploring — or do they all blur into "same template, different label"?
2. **Family-contract leakage.** Inspector ⇄ Compare ⇄ Audit (read-mode trio): visually related but distinct? Same for Intake/Source-Review/Plan-review trio? Same for Run-progress/Dashboard pair?
3. **Per-frame v6 checklist** holds across all 12: sealed evidence block where relevant, two-judgment separation (read-mode), tri-state signature, intended-use language, no decorative icons, zero-jargon banlist, six microstates implied.
4. **Critical-path A+ pages** (rows 1-8) at the same bar the v6 hero hit?
5. **Supporting A pages** (rows 9-12) — clearly subordinate to critical-path but not sloppy?
6. **Cross-page narrative.** When stitched into the demo journey (Home → Intake → Source-Review → Plan → Run → Inspector → Compare → Knowledge-graph), do they read as a coherent product, not 12 disconnected screens?
7. **TRACK 3 ready to sign off?** If APPROVE → TRACK 4 (e2e click-through prototype stitching all pages) + TRACK 5 (per-page critical-path audits IF flagged) + sign-off → hand to I-ux-001c.

## Output schema (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3: [...]
convergence_call: continue | accept_remaining
track_3_ready_to_signoff: yes | no | with_caveats
specific_check_responses:
  specialization_sufficiency: PASS | FAIL_with_detail
  family_contract_leakage: PASS | FAIL_with_detail
  per_frame_v6_checklist: PASS | FAIL_with_detail
  critical_path_aplus: PASS | FAIL_with_detail
  supporting_a_bar: PASS | FAIL_with_detail
  cross_page_narrative_coherence: PASS | FAIL_with_detail
  pages_flagged_for_track5_per_page: [list of page-row numbers OR "none"]
```

## Files to -i (12 frames, in /home → /transparency order)
