# Claude audit — I-p2-038 (#821) top-tier visual overhaul (pages 1-3)
Operator: P2 is a UI phase; live UI was B/B-; refocus on UI. 3 pages/components,
each VISUALLY VERIFIED on a local next-dev build (screenshots):
1. Home proof-showcase: exact cited span HIGHLIGHTED in real source context
   (was a mid-word fragment). Faithful: <mark> === full_text[start:end].
2. Centerpiece Proof Replay: same span-in-context treatment.
3. Intake: killed internal jargon → user-facing benefit copy.
New spanInContext() helper (evidence_span.ts): span = exact slice; before/after
real adjacent text snapped to word boundaries; null on invalid bounds (no
synthetic text). box-decoration-clone so the highlight wraps across lines.
Codex review: APPROVE iter-2 (zero P0/P1), MERGE AUTHORIZED; iter-1 P1 (CI
format_check) + iter-2 P2 (box-decoration-clone) both addressed. tsc clean;
prettier --check clean on all 4 files. Operator: "Codex decide when to merge".
Honest: web/ has no unit-test runner (only playwright e2e); spanInContext
faithfulness is by-construction + visually verified — vitest harness is a
separate infra follow-up.
