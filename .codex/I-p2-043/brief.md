# Codex brief — I-p2-043 (#833): Inspector centerpiece S-rebuild

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this brief is
A BRIEF (acceptance-criteria + design-plan review), NOT a diff review. Approve iff the
PLAN below (a) achieves the S-tier "Proof Replay leads" goal, (b) loses zero data (LAW II),
(c) does not break the e2e contract I enumerate. The diff + the dual Codex VISUAL gate
(`codex exec -i` on screenshots) come after your APPROVE here.

## Operator-locked constraints (HARD — not negotiable, do not reopen)
- Brand red `#c8102e` is OPERATOR-LOCKED. No palette change.
- Bar = A++/S, differentiating vs Perplexity/ChatGPT-DR/Gemini. "Not half-ass, not B-."
- Honest sovereignty wording only (no "fully sovereign" present-tense overclaim).
- §-1.1 clinical-safety: no field/data may be silently dropped.

## The page (current state, HEAD)
`web/app/inspector/[runId]/inspector_view.tsx` renders, top→bottom:
1. `<BundleHeader>` — a big Card with 8 manifest KeyValues (bundle_id, bundle_version
   "Schema version", polaris_version, generator_model, decision_id, pool_id, report_id,
   created). testid `bundle-header`; nests `signature-badge`.
2. `<FamilySegregationBadge>` — a full bordered Card (p-4, generator/evaluator grid,
   pass/fail pill in **hardcoded emerald/rose**, NOT design tokens). testid
   `family-segregation-badge` + `data-state={pass|fail}`.
3. `<Tabs defaultValue="proof">` — 8 tabs: Proof Replay / Report / Scope / Evidence /
   Reasoning / Sources / Hash chain / Metadata. ProofReplay is already the default.

**Codex's S-tier verdict (the gap):** "the top audit metadata dominates BEFORE the
centerpiece — promote Proof Replay above metadata." The eye lands on 8 audit IDs + a
two-family card before it ever sees the proof. Grade B+. Reads as compliance tooling,
not research software.

## The plan (3 files)

### A. `inspector_view.tsx` — hero restructure (proof leads)
Replace the two stacked metadata cards above the tabs with a compact **hero header**:
- `<h1>` = `bundle.verifiedReport.research_question` (the subject). The canonical demo
  bundle has it: *"What is the efficacy and safety of tirzepatide for glycemic control
  and weight loss in adults with type 2 diabetes?"* — this is what should greet the eye.
  If absent (abort fixture `v1_canonical`: rq=None, 0 sections) → render NO h1 (degrade).
- A proof-forward summary line UNDER the h1: section count + `overall_verify_pass_rate`
  (e.g. "4 sections · 100% claims verified"). Only when sections exist; for abort show a
  muted "No verified sections — see Report tab." This line uses a NEW testid (e.g.
  `inspector-proof-summary`), NOT `pipeline-verdict-badge` (which lives in the Report tab
  / VerifiedReportSections and the abort spec asserts there — must not collide).
- The slim trust strip (`<BundleHeader>`, see B) + compact two-family chip
  (`<FamilySegregationBadge>`, see C) sit as a single secondary row in the hero — visually
  subordinate to the h1, NOT a stack of big cards.
- `<Tabs defaultValue="proof">` unchanged (all 8 tabs, same labels + data-tab ids).
- `main` keeps `data-testid="inspector-view"` + `data-run-id`.

### B. `bundle_header.tsx` — slim trust strip + zero-loss disclosure
- Default render = one slim row: signature chip (`signature-badge`, tokenized
  verified/contradiction) + bundle_id (mono) + generator_model (mono) + created.
- **Zero field loss:** a collapsible "Full manifest" `<details>` inside the strip reveals
  ALL 8 manifest fields (incl. `report_id` and `bundle_version`, which are NOT surfaced in
  any other panel today — see scan below). `polaris_version`→MetadataPanel,
  `decision_id`→ScopeDecisionCard, `pool_id`→EvidencePoolTable already exist elsewhere, but
  the disclosure carries the complete set so the strip drops nothing.
- Keeps `data-testid="bundle-header"` VISIBLE + `signature-badge`.

### C. `family_segregation_badge.tsx` — tokenize + compact
- Swap hardcoded `emerald-*/rose-*` → design tokens (`--verified` pass / `--destructive`
  or `--contradiction` fail). This is an S-tier color-restraint fix.
- Compact to an inline chip ("Two families ✓ Generator ⋮ Evaluator") suitable for the hero
  secondary row, instead of a full p-4 card.
- Keeps `data-testid="family-segregation-badge"` VISIBLE + `data-state={pass|fail}`.

## e2e contract I MUST NOT break (verified against tests/e2e/inspector_route.spec.ts)
- `inspector-view` visible (+ data-run-id).
- `bundle-header` visible (`:46`). Also masked in deferred visual baselines `:172/:181`.
- `family-segregation-badge` visible (`:47`) + `data-state="pass"` (`:55`).
- 6 tabs report/scope/evidence/reasoning/sources/hashchain activate by role-name + their
  `[data-tab="<id>"]` panel visible/others hidden (`:58-82`). (proof + metadata not in the
  loop but must remain present with same labels.)
- `toggle-provenance-tokens` in Report tab (`:84-90`) — in VerifiedReportSections, NOT my
  scope; untouched.
- No console errors (`:92`).
- **No dev-language in rendered text** (`:104` — /TODO/FIXME/XXX/placeholder/lorem ipsum/).
  My hero copy must avoid these words.
- 3 viewports render (`:114-120`).
- Abort fixture `v1-canonical`: `pipeline-verdict-badge` data-state="abort" in Report tab
  (`:123-133`) — my hero must NOT define a second `pipeline-verdict-badge`.
- Unknown runId → `bundle-pending-cta` (`:136`) — unaffected (different render path).

## Files I have ALSO checked and they're clean (no change needed / no break)
- `web/components/proof_replay/proof_replay.tsx` — the centerpiece default-tab content;
  untouched this PR (its internal S-quality is a separate concern, not page framing).
- `web/components/inspector/metadata_panel.tsx` — shows polaris/generator/evaluator/
  created/schema_version (metadata.*); does NOT show manifest IDs (hence the disclosure in B).
- `web/components/inspector/scope_decision_card.tsx` (`decision_id`),
  `evidence_pool_table.tsx` (`pool_id`, `decision_id`) — already surface those IDs.
- `web/components/inspector/hash_chain_panel.tsx`, `sources_panel.tsx`,
  `reasoning_trace_timeline.tsx`, `verified_report_sections.tsx` — tab contents, untouched.
- `web/lib/inspector_bundle_loader.ts` — `verifiedReport.research_question?` optional;
  `overall_verify_pass_rate`, `pipeline_verdict`, sections[] available. Types unchanged.
- e2e: `inspector_offline_fallback.spec.ts`, `audit_bundle.spec.ts`, `bundle_preview.spec.ts`,
  `demo_journey.spec.ts` (uses `family-segregation-badge` getByTestId at `:53`, satisfied by
  keeping the testid), `sentence_inspector*.spec.ts` (exercise ProofReplay, untouched).
- Brand `#c8102e` + tokens in `globals.css` — reused, not changed.

## Acceptance criteria (issue #833)
1. Proof Replay leads — research question + proof above audit metadata.
2. BundleHeader slim trust strip, `bundle-header`+`signature-badge` visible.
3. ZERO field loss — report_id + bundle_version reachable (the disclosure).
4. Tabs unchanged (8 labels + data-tab ids).
5. Dual Codex gate (this brief = code-plan APPROVE; then diff + visual `-i`).
6. e2e green; deferred visual baselines stay masked.
7. Docs: s_tier_design_system.md per-screen grade + file_directory if structure changes.

## Question for you
APPROVE iff this plan (a) genuinely moves the Inspector from "compliance-tooling-first" to
"proof-leads" at the A++/S bar, (b) loses zero data, (c) breaks none of the enumerated e2e
contract. If you see a stronger S-tier structure (e.g. a different hero composition, or the
two-family chip belongs elsewhere), say so as P1/P2 with the specific change.
