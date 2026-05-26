# Visual Audit Rubric v1 — POLARIS v6 UI

**Status:** LOCKED. Single source of truth. Every Codex visual-audit prompt
cites this file by SHA-pin; rubric drift between PRs is forbidden.

**Authority:** matches `polaris-controls/PLAN.md` Phase 2 design bar and
`docs/stier_experience_directive_2026_05_24.md` (S-tier visual liveliness
directive).

**Citation in briefs:** every Codex visual-audit call MUST contain the
sentence

> "Score the screenshot against the 16-dimension rubric defined verbatim
> in `.codex/visual_audit_rubric.md` (SHA <pin>). Use exactly the field
> names; do not paraphrase dimension labels."

Sign-off threshold: **≥14 / 16 PASS**. PR ships ONLY when every screenshot
the brief enumerates clears the threshold OR Codex iter-5 force-APPROVE
fires per CLAUDE.md §8.3.1.

---

## The 16 dimensions

Each dimension scores **PASS / PARTIAL / FAIL** with one sentence of
evidence quoting the specific pixel region or token.

### Visual identity (4)

1. **Brand presence** — POLARIS wordmark + brand red `#c8102e` (exact
   hex; no near-match) visible above the fold; no competing accent color
   stronger than red.
2. **Typography hierarchy** — display, h1, h2, body, caption are
   visually distinct (≥1.25 scale ratio between adjacent levels);
   font-weight ladder consistent (regular / medium / semibold / bold —
   no rogue weights).
3. **Spacing rhythm** — 8-px or 4-px grid respected; no rogue margins
   (e.g., `margin-top: 13px`); section gaps follow the same step pattern
   throughout the page.
4. **Color palette** — every visible color belongs to the locked
   palette (`#c8102e` brand, neutral greys, `#0a7f3b` verified-green,
   `#b15206` honest-fail-amber, `#0066cc` link-blue); no off-brand
   accents (e.g., default React/Next purple, Tailwind cyan).

### Layout and craft (4)

5. **Above-the-fold composition** — first viewport shows the page's
   value proposition without scrolling; primary CTA is visible AND
   distinctively styled (not buried under chrome).
6. **Alignment** — text baselines, card edges, button rows align on
   shared columns; no 1–2-px drift; no orphan misaligned elements.
7. **Responsive integrity** — at the audit viewport, no horizontal
   scroll, no overflow clipping of meaningful content, no broken card
   wraps; text remains legible at the given width (≥16-px body, ≥1.4
   line-height).
8. **Empty / loading / error states** — if the viewport shows a list,
   the empty state has copy + icon + recovery action (not "[]" or
   blank); loading uses brand-styled skeletons (not default browser
   spinner); errors quote the actual error class.

### Content honesty (4 — the POLARIS differentiator)

9. **Per-sentence provenance visible** — every numeric claim and every
   factual sentence in proof-replay zones shows its evidence chip
   inline (citation number or visible chip), not just a footnote bar at
   page bottom.
10. **Verified vs honest-fail differentiation** — verified claims
    render in the verified-green pattern (e.g., `#0a7f3b` chip, bold
    numeric); honest-fail claims render in amber `#b15206` with the
    word "honest fail" or equivalent; the two are unambiguously
    distinguishable at a glance.
11. **Sovereignty disclosure honest** — if the page mentions
    "sovereign", "Canadian", or model identity, the disclosure language
    matches `/transparency` (no claims of fully-Canadian-LLM when the
    actual LLM transit is OpenRouter-US; per
    `feedback_sovereignty_threat_model_2026_05_13`). "Audit bundle"
    appears INSTEAD of "signed bundle" until the GPG path ships
    (memory: 2026-05-21 directive).
12. **No fabricated UI** — every datum on screen traces to a real
    backend response, a real fixture, or a labeled placeholder
    ("EXAMPLE" / "DEMO" overlay). No silent stub data presented as a
    live verified claim. (Lethal failure mode per CLAUDE.md §-1.1.)

### Interaction and liveliness (4)

13. **Motion-affordance visible at end state** — hover and focus
    states produce a VISIBLE difference between the static screenshot
    and the hovered/focused screenshot of the same route+viewport
    (color shift, ring, scale, shadow — not invisible); skeletons
    render as a branded loading affordance (e.g., red-accent shimmer
    bar), not a default browser spinner or blank box. Timing/easing of
    transitions is NOT screenshot-observable and is excluded from this
    dimension; that concern is checked by `feedback_ui_lively_to_100_2026_05_24`
    operator review, not by the gate.
14. **Keyboard + focus** — visible focus ring on tab through all
    interactives at the audit viewport (not the browser default outline
    that disappears under brand red); skip-link present at top.
15. **Touch targets** — at the mobile viewport (≤640 px), every tap
    target is ≥44 × 44 px (WCAG 2.5.5); no two interactives within 8 px
    of each other.
16. **Lively but disciplined** — motion enhances comprehension (numbers
    count up, chips fade in as evidence is verified, claims highlight
    on hover) but never blocks reading; no auto-playing video, no
    decorative animation on the critical content path that delays a
    100-ms FCP target on the route.

---

## How Codex calls this

Codex receives this rubric file via the brief reference (read-only) and
the screenshot via `-i <png>`. Codex's response MUST be machine-parseable
YAML:

```yaml
verdict: APPROVE | REQUEST_CHANGES
rubric_version: v1
rubric_sha256: <64-hex; the gate enforces it matches working-tree SHA>
viewport: { width: 1440, height: 900 }  # or 768x1024, 390x844
state: static  # one of static | focused | hovered — the harness captures all three
route: /inspector/[runId]
screenshot_sha256: <64-hex>
scores:
  brand_presence: PASS | PARTIAL | FAIL
  typography_hierarchy: PASS | PARTIAL | FAIL
  spacing_rhythm: PASS | PARTIAL | FAIL
  color_palette: PASS | PARTIAL | FAIL
  fold_composition: PASS | PARTIAL | FAIL
  alignment: PASS | PARTIAL | FAIL
  responsive_integrity: PASS | PARTIAL | FAIL
  empty_loading_error: PASS | PARTIAL | FAIL
  per_sentence_provenance: PASS | PARTIAL | FAIL
  verified_vs_honest_fail: PASS | PARTIAL | FAIL
  sovereignty_disclosure: PASS | PARTIAL | FAIL
  no_fabricated_ui: PASS | PARTIAL | FAIL
  motion_right_grain: PASS | PARTIAL | FAIL
  keyboard_focus: PASS | PARTIAL | FAIL
  touch_targets: PASS | PARTIAL | FAIL
  lively_but_disciplined: PASS | PARTIAL | FAIL
pass_count: <0..16>
evidence:
  brand_presence: "Brand red #c8102e in header at y=24px and CTA at y=420px; no purple/cyan accents."
  # ... one sentence per dimension ...
threshold: 14
verdict_reason: "pass_count=15 ≥ 14"
```

**The gate parses ONLY:** `verdict:`, `pass_count:`, `rubric_sha256:`,
`screenshot_sha256:`. The rest is documentation.

---

## Why these 16

- Dimensions 1–8 are the standard frontier-UI bar (Linear, Stripe,
  Vercel, Anthropic Console reviewed 2026-05-25).
- Dimensions 9–12 are POLARIS-specific: per-sentence provability is the
  differentiator per CHARTER §1 + Carney positioning; treating these as
  visual quality dimensions (not "QA") makes the reviewer see them.
- Dimensions 13–16 are the S-tier liveliness bar from
  `docs/stier_experience_directive_2026_05_24.md` — "ugly = no one
  looks; liveliness is first-class, not polish."

Adding a 17th dimension requires a Codex-approved Issue. Dropping any
dimension requires a Codex-approved Issue. Drift is a `state/halt_*`
condition.
