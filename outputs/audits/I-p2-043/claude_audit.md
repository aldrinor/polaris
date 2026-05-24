# Claude architect audit — I-p2-043 (#833): Inspector centerpiece S-rebuild

## Goal
Move `/inspector/[runId]` (the public differentiator) from "compliance-tooling-first" to
"proof-leads" at the A++/S bar, per the S-tier program (#829) build-order page-1 and Codex's
S-tier direction ("promote Proof Replay above metadata").

## What changed (5 files, +238/-111)
- `components/inspector/inspector_proof_header.tsx` (NEW): the bespoke proof-header band —
  H1 (research question, or "Signed research bundle" for abort) → verify-rate headline proof
  artifact (large green "100%") + section count + "every sentence traces to its cited source
  span" → grouped trust chips (two-family + signature) → zero-loss "Full manifest" disclosure.
- `components/inspector/bundle_header.tsx`: slim metadata line + `<details>` carrying all 8
  manifest fields; SignatureBadge exported + relocated to the chip row.
- `components/inspector/family_segregation_badge.tsx`: tokenized (pass=--verified,
  fail=--destructive; was hardcoded emerald/rose), compacted to an inline chip.
- `app/inspector/[runId]/inspector_view.tsx`: renders InspectorProofHeader; 8-tab rail wrapped
  in a horizontal-scroll lane (mobile overflow fix). Proof Replay stays default.
- `docs/web/s_tier_design_system.md`: per-screen grade update.

## LAW II — zero data loss (line-by-line)
Original BundleHeader rendered 8 manifest fields. After: `polaris_version`→MetadataPanel,
`decision_id`→ScopeDecisionCard, `pool_id`→EvidencePoolTable (already surfaced). `report_id`
and `bundle_version` are surfaced NOWHERE else → preserved in the "Full manifest" disclosure
(verified rendered in the manifest-open screenshot). generator/evaluator model names move to
the family chip's title and remain in MetadataPanel. **No field dropped.**

## e2e contract (preserved, verified)
`inspector_route.spec.ts` 11/11 active pass: `inspector-view`(+data-run-id), `bundle-header`
visible, `family-segregation-badge` visible + `data-state="pass"`, 6-tab activation +
`data-tab` ids, `toggle-provenance-tokens`, no console errors, no dev-language, 3 viewports,
abort `pipeline-verdict-badge` (single-sourced in Report tab — hero uses a distinct
`inspector-proof-summary` testid), pending CTA. `sentence_inspector.spec.ts` pass.
`inspector_offline_fallback.spec.ts` fails at its `tar -czf` setup step — pre-existing Windows
harness issue; this branch touches no test files.

## Dual Codex gate
- Brief APPROVE (iter 1) — `.codex/I-p2-043/codex_brief_verdict.txt`.
- Visual `-i` APPROVE (iter 3) — desktop A / mobile A- / manifest A / abort A-
  (`.codex/I-p2-043/codex_visual_audit_iter3.txt`). iter-1→3 closed 5 P1s (trust layer thin,
  abort hero lost, mobile tab overflow, manifest islands).
- Code diff APPROVE (iter 1) — `.codex/I-p2-043/codex_diff_audit.txt`, zero findings.

## Residuals (deferred, non-blocking)
- Mobile evidence-card density: lives in the Proof Replay split-view internals (separate
  component issue), not this PR's page-framing scope.
- The lower-left "N" badge in dev screenshots is the Next.js dev indicator (absent in prod).

## Constraints honored
Brand `#c8102e` untouched; tokens only; honest sovereignty wording (footer disclosure intact);
no test relaxation; no silent fallback.

Verdict: ready to merge. canonical-diff-sha256:
0e9245b67fe47ebd49163ad0d514421c0176dcad013abe67f90e760293207287
