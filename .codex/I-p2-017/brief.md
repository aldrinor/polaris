# Codex DESIGN+DIFF review — I-p2-017 (#756): wire the Proof Replay centerpiece

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `8233e86153a65835a7e085a4018c1f0e951052e3a8827ca19174085b2eeb34e9`. web/ only, 1 file, 40-line diff. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## Context — a real phantom-completion gap
#756 = "Report = Proof Replay (CENTERPIECE)". The `ProofReplay` split-view
(#746) — POLARIS's centerpiece (click a verified claim → see its EXACT cited
source span) — was built but **imported by NO route** (`grep -rln ProofReplay
web/` returned only build-cache refs). The inspector's "Report" tab rendered a
plain `VerifiedReportSections` list; there is no `/report` route. So the
centerpiece was invisible in the shipped product — classic code-exists-no-UI
phantom completion.

## Diff (1 file: web/app/inspector/[runId]/inspector_view.tsx)
- Import `ProofReplay` from `@/components/proof_replay/proof_replay`.
- Add a `"proof"` tab labelled "Proof Replay" as the FIRST `TabsTrigger` +
  `defaultValue="proof"` (the centerpiece is now the default inspector view).
- Its `TabsContent` renders `<ProofReplay sections={bundle.verifiedReport.sections}
  evidencePool={bundle.evidencePool} />`. The existing "Report" tab
  (VerifiedReportSections prose list) stays as the second tab.

## Why this is safe + faithful (no fabrication)
ProofReplay is the existing #746 composition (resolveSpan #743 + SourceCard #745
+ VerdictChip #744) with honest edge-case handling (no-tokens / unresolvable-token
/ source-not-in-bundle / span-not-renderable each show an honest note, never
synthetic proof). Props match: `LoadedBundle.verifiedReport.sections`
(VerifiedReportSectionShape[]) + `LoadedBundle.evidencePool`. No new logic — pure
wiring.

## Files I have ALSO checked and they're clean
- `proof_replay.tsx` read in full: flatten() reads section.verified_sentences[]
  (sentence_text/provenance_tokens/verifier_pass) + section.section_title (falls
  back to null) — all present on the canonical bundle's verified_report.
- `resolveSpan` already works with the canonical bundle (the home proof-showcase
  #794 uses it on the same bundle).
- No other consumer of the inspector Report tab; VerifiedReportSections retained.

## Claude visual audit (standalone @1366, real canonical bundle v1-canonical-success)
Inspector renders; "Proof Replay" is the default tab. Split-view: LEFT = 8
verified claims (role=list); selecting the treatment-difference claim shows RIGHT
= the claim text + a VERIFIED chip + the SourceCard (NEJM tirzepatide-vs-
semaglutide) + the exact cited source span blockquote. Faithful claim→span
mapping (the span is the real NEJM SURPASS-2 content carrying the cited numbers).

## Review focus (8-dim rubric + diff)
1. Is "Report = Proof Replay" satisfied by surfacing ProofReplay as the default
   tab (centerpiece now viewable)? Any a11y regression (tab order, the new
   default tab's role=list/listitem)?
2. Faithfulness: the split-view shows ONLY real bundle data; honest notes on
   missing/unresolvable provenance; no synthetic proof.
3. Any P0/P1.

(Note: #756 acceptance also lists "operator sign-off" — that final close stays
with the operator per their deferral; this PR fixes the build gap so the
centerpiece is actually viewable for that sign-off.)

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
