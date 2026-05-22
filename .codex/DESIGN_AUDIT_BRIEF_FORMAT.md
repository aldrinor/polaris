# Codex DESIGN-AUDIT brief template (Phase-2 UI) — v1, 2026-05-21 (I-p2-002 / #741)

Use this template for the DESIGN audit of every Phase-2 UI issue (I-p2-*), separate from and in addition to the code-diff review. Copy this skeleton into `.codex/<id>/design_audit_brief.md`, fill the brackets, attach the screenshot matrix, run Codex.

**AUTHORING RULE (per REVIEW_BRIEF_FORMAT §0):** the authored brief MUST begin with the §0 cap block as its very first content. When you copy this template, DROP this template's title + these two instruction paragraphs so the authored brief opens directly with `HARD ITERATION CAP: 5 ...`. The title/instructions above are template meta, not part of the authored brief.

---

## 0. Iteration-cap directive (verbatim from CLAUDE.md §8.3.1, MANDATORY first block — copy byte-for-byte)
```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```
(For design audits: "Verdict APPROVE" additionally requires all 16 dimensions PASS.)

## 1. What you are auditing
- Issue: `<I-p2-NNN (#GH)>` — `<page/component>`.
- You are the TOP-TIER design auditor. Bar: ahead-of-frontier (Perplexity / ChatGPT-DR / Gemini / Linear) on verifiable proof; ≥ par on polish. Audience: a PMO analyst, not an engineer.
- Locked design: WHITE background · dark Canada-flag red accent (by scarcity) · Frontier Minimal (Geist + Geist Mono, hairlines, whitespace) · Braille maple-leaf signature where present.

## 2. Rendered evidence ATTACHED (Codex cannot audit design from a diff)
- Screenshot MATRIX (paths): desktop 1440 / tablet 768 / mobile 390 + **200% AND 400% zoom** + **forced-colors mode** + **print/export view** + the key interaction states (default / hover / **focus-visible** / loading / empty / error / the proof-replay-open state). Captured via the **production standalone harness** (`node web/.next/standalone/server.js`), NOT `next dev`.
- **REQUIRED (not optional):** Playwright interaction trace, `axe` accessibility output, a **keyboard-only** walkthrough, a **screen-reader** pass, and **evidence-click tests** (claim → exact source span renders).
- The exact routes/fixtures used.

## 3. Audit ALL 16 dimensions → PASS / NEEDS-WORK (with specifics) per `state/polaris_phase2_ui_breakdown_2026_05_21.md`
Dims 9-13 use the concrete measurable thresholds in `.codex/PHASE2_GATES.md` (G-RESP / G-I18N / G-CONTENT / G-PERF / G-SEC) — cite the gate ID + the measured value.
1. Visual design  2. User flow  3. Data flow / IA  4. User focus / cognitive load  5. Clarity  6. Frontier head-to-head (AHEAD/PAR/BEHIND + specifics)  7. Accessibility (WCAG 2.2 AA)  8. Provability / honesty (no synthetic proof; uncertainty shown; click raises confidence)  9. Responsive / device / zoom  10. EN-FR i18n-readiness (EN-first waiver logged — check no hardcoded-string blockers, locale-safe formats, ~+30% expansion tolerance)  11. Content / microcopy  12. Security / privacy / sovereignty (verified, not badge)  13. Performance / resilience  14. Dense-table UX  15. Role / workflow governance  16. Independent rendered verification (the attached matrix/trace/axe actually prove the above).

## 4. Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
dimensions:               # all 16, each PASS or NEEDS-WORK + note
  visual: PASS|NEEDS-WORK — <note>
  user_flow: ...
  data_flow_ia: ...
  focus_cognitive_load: ...
  clarity: ...
  frontier_head_to_head: PASS|NEEDS-WORK — AHEAD|PAR|BEHIND, <specifics>
  accessibility: ...
  provability_honesty: ...
  responsive_zoom: ...
  i18n_en_fr_ready: ...
  content_microcopy: ...
  security_sovereignty: ...
  performance: ...
  dense_table_ux: ...
  role_governance: ...
  independent_verification: ...
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
Convergence: APPROVE iff all 16 PASS (zero P0, zero P1).
