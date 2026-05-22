# Phase-2 standards gates — responsive / i18n / content / performance / security (I-p2-030, #769)

Operationalizes rubric dimensions 9-13 of `state/polaris_phase2_ui_breakdown_2026_05_21.md` into **concrete, measurable** pass/fail gates. Every Phase-2 UI task (I-p2-*) is audited against these; the Codex design audit (DESIGN_AUDIT_BRIEF_FORMAT.md dims 9-13) cites these thresholds. Evidence captured via the production standalone harness.

## G-RESP — Responsive / device / zoom (dim 9)
- **Viewport matrix:** 1440 (desktop), 1024 (laptop), 768 (tablet), 390 (mobile). PASS = no horizontal scroll, no clipped/overlapping content, the evidence rail collapses to a drawer ≤768.
- **Zoom:** 200% AND 400% (WCAG 2.2 1.4.10 reflow) — content reflows to single column, no loss of function, no 2-D scroll.
- **Forced-colors** (Windows high-contrast): all text/borders/focus visible; no information conveyed by color alone.
- **Print/export view:** the report prints cleanly (no clipped evidence, page breaks sane).
- **Target size:** interactive targets ≥ 24×24 CSS px (WCAG 2.2 2.5.8).

## G-I18N — Official languages / i18n readiness (dim 10, EN-first waiver)
Demo ships EN-only (operator waiver logged), but new code MUST be FR-ready:
- **No hardcoded user-facing strings** in new components — route display copy through a strings module / i18n-ready structure (grep: no bare JSX text literals in new UI beyond a strings file).
- **Locale-safe formatting:** dates/numbers/units via `Intl.*` (no manual `toLocaleDateString()` with hardcoded `en-`, no string-concatenated numbers).
- **Layout tolerates +30% text expansion** (FR is ~25-30% longer) — no fixed-width labels that truncate; pseudo-localization +30% screenshot doesn't break layout.
- FR translation itself = post-demo follow-up issue (not built now).

## G-CONTENT — Content design / microcopy (dim 11)
- **Honesty copy (BANNED → REQUIRED):** never "guaranteed true" / "100% accurate" → use "verified provenance" / "traceable to source". Uncertainty is shown, not hidden.
- **Caveats present:** evidence grade, limitations, date-freshness, jurisdiction shown on every report.
- **Refusal/contradiction wording** = a feature ("can't verify this honestly — here's why"), never a raw error.
- **Empty/loading/error copy** is operational + specific (no generic spinners / "Something went wrong").
- **Domain-specific copy:** labels/headings/templates speak the actual domain (clinical / regulatory / policy / legal — e.g. "evidence grade", "jurisdiction", "contraindication"), NOT generic SaaS boilerplate ("Dashboard", "Items", "Untitled"). Evidence: a copy pass confirming no generic placeholder/boilerplate strings in shipped UI.

## G-PERF — Performance / resilience (dim 13)
- **LCP < 2.5s**, **CLS < 0.1**, **INP < 200ms** (Core Web Vitals, measured).
- **Route JS budget < 250KB gzipped** per page (three.js maple-leaf chunk lazy-loaded + excluded from initial; KG lib lazy on the graph route only).
- **Source-span open < 1s** after a sentence click (the proof-replay interaction).
- **Export budget:** signed bundle / PDF / report export completes < 5s for a typical report (≤50 claims); progress shown for larger.
- **Knowledge graph** renders ≥ 1k nodes at ~60fps (WebGL); degrades gracefully above.
- **Resilience:** offline / backend-down / abort states render the honest empty/error UI, never a hang.

## G-SEC — Security / privacy / sovereignty, VERIFIED not badge (dim 12)
- **RBAC:** each route/resource enforces the role model (analyst/counsel/clinical/records); unauthorized = 403, not a blank screen. Evidence: a denied-access test.
- **Egress proof:** public-source retrieval shown as logged Canadian egress in the sovereignty panel (not an air-gap claim).
- **Data classification:** PUBLIC/CAN_REAL/PRIVATE/CLIENT labels surfaced; PHI/PII never written to client console/logs.
- **Redaction:** PHI/PII is redacted in shared/exported/screenshot-able views per data class. Evidence: a redaction test (a PRIVATE/CLIENT field is masked in export + in the shared link).
- **Tamper-evident audit log:** the per-run audit log is signed / hash-chained (each entry references the prior hash); altering an entry breaks the chain. Evidence: a chain-verify check + a tamper-detection test.
- **Signed artifacts:** report bundle + export are signed (sha256 + signature shown); "not used for training" stated.
- **Evidence required:** each security claim is backed by an artifact (test, log, screenshot) — a badge alone fails the gate.

## How applied
- Every I-p2-* page/component design-audit brief references these gate IDs; Codex returns PASS/NEEDS-WORK per gate with the measured value.
- CI wiring (Lighthouse budget, axe, the i18n grep) is a follow-up once `.github/workflows` is operator-editable (#567/#720 track that); until then these gates are enforced by the Codex design audit + screenshot/measurement evidence.
