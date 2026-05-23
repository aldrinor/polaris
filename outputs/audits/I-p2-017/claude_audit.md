# Claude audit — I-p2-017 (#756): wire the Proof Replay centerpiece

## The gap (phantom completion — found by walking the sequence)
The #746 `ProofReplay` split-view — POLARIS's literal centerpiece (click a
verified claim → see its exact cited source span) — was built but imported by
NO route (`grep -rln ProofReplay web/` → only build-cache). The inspector's
"Report" tab rendered a plain `VerifiedReportSections` list; no `/report` route.
The centerpiece was invisible in the shipped product. The task tracker marked
#756 "completed" — it was phantom-complete.

## Fix
Surface `ProofReplay` as the inspector's DEFAULT first tab ("Proof Replay"), fed
`bundle.verifiedReport.sections` + `bundle.evidencePool`. Pure wiring of the
existing #746 component (resolveSpan #743 + SourceCard #745 + VerdictChip #744);
no new logic. The Report prose list stays as the second tab.

## §-1.1 faithfulness
The split-view renders ONLY real bundle data: each claim's verdict chip reflects
`verifier_pass`; each provenance token resolves via `resolveSpan` to the actual
evidence_pool span (shown as a blockquote with the SourceCard). Honest notes on
missing/unresolvable/out-of-bundle provenance — never synthetic proof. Verified
live on the canonical bundle: the treatment-difference claim → VERIFIED + the
exact NEJM SURPASS-2 cited span.

## Verification
typecheck + build green; standalone @1366: Proof Replay default tab, 8 verified
claims, faithful claim→span mapping. Codex DESIGN+DIFF APPROVE iter 1, zero P0/P1.

## Residual
- #756 acceptance also requires "operator sign-off" → that final close stays with
  the operator (per their deferral to the #766 demo-journey verify). This PR
  fixes the build gap so the centerpiece is actually viewable for that sign-off.
- Codex P2 (non-blocking): extend inspector_route.spec.ts to assert the proof
  tab — a regression guard for exactly this phantom-completion. Deferred: the
  e2e lane is non-functional (#720, operator-owned) so it can't run yet.
