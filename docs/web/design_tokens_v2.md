# POLARIS Design Tokens v2 (I-ux-001b / #876)

**Status:** SPEC — Codex review pending. Implements §12 of the Codex-APPROVED I-ux-001 experience plan. Supersedes the ad-hoc tokens that today live as a mix of Tailwind v4 `@theme` and inline Tailwind classes.

**Two principles drive every decision below:**
1. **Restraint does the hierarchy work.** Typography + space + a single meaning accent — never color or chrome for decoration (Linear/Stripe craft bar).
2. **Two judgments, two visual languages.** Faithfulness (sentence ↔ source span) and evidence strength (decision-safety) are independent claims; their tokens MUST never share a swatch, weight, or shape. Confusing them is the lethal failure mode in clinical context (plan §0 + §4).

---

## 1. Type

Single family, optical alignment per breakpoint. The current site is already Geist; keeping it.

```
Display       48 / 56   weight 700   tracking -0.02em   measure 28ch    use sparingly: home headline only
H1            32 / 40   weight 700   tracking -0.015em  measure 32ch    one per route
H2            24 / 32   weight 600   tracking -0.01em   measure 40ch    section headings
H3            20 / 28   weight 600   tracking -0.005em  measure 48ch    sub-section
Body-lg       18 / 28   weight 400   measure 62-72ch                    brief prose (the report; default reading width)
Body          16 / 24   weight 400   measure 62-72ch                    everything else
Caption       14 / 20   weight 400                                       metadata, secondary lines
Mono          13 / 20   weight 500   font ui-monospace, ...              hashes, IDs, span text in proof panel
```

- `body-lg` is the brief reading text. 62–72ch measure is enforced via container width, not on the paragraph itself (avoids orphan single-column edges).
- `font-feature-settings: "ss01", "ss03", "cv11"` on Geist for tabular numerals + alternate `a` (Linear-aligned). `tabular-nums` on every count display (verdict header, SoF tables).

**Tailwind v4 token (CSS `@theme` block in `web/app/globals.css`):**
```css
@theme {
  --font-display: var(--font-geist);
  --font-mono: ui-monospace, "JetBrains Mono", "Cascadia Code", Menlo, monospace;

  --text-display: 3rem;        --text-display--line-height: 3.5rem;
  --text-h1: 2rem;             --text-h1--line-height: 2.5rem;
  --text-h2: 1.5rem;           --text-h2--line-height: 2rem;
  --text-h3: 1.25rem;          --text-h3--line-height: 1.75rem;
  --text-body-lg: 1.125rem;    --text-body-lg--line-height: 1.75rem;
  --text-body: 1rem;           --text-body--line-height: 1.5rem;
  --text-caption: 0.875rem;    --text-caption--line-height: 1.25rem;
  --text-mono: 0.8125rem;      --text-mono--line-height: 1.25rem;
}
```

---

## 2. Color — meaning only

Near-monochrome ground; ONE brand accent (red, OPERATOR-LOCKED `#c8102e`); two independent semantic palettes for the two judgments. No decorative color.

### 2.1 Ground (light theme is the default; dark mode is out of scope for v2)
```
--background        oklch(0.99 0.005 95)    near-white, slight warm cast (warm-editorial)
--foreground        oklch(0.21 0.01 95)     near-black for text — 17.5:1 vs background (well above AA)
--muted             oklch(0.95 0.005 95)    surfaces (cards, table rows)
--muted-foreground  oklch(0.50 0.01 95)     secondary text — 6.0:1 vs background (AA pass)
--border            oklch(0.91 0.005 95)    hairlines, dividers
--card              oklch(1.00 0 0)         elevated surfaces
```

### 2.2 Brand (action + identity only — never decoration)
```
--primary           #c8102e (LOCKED)        primary CTA, sovereignty/identity beats
--primary-fg        oklch(0.99 0.005 95)    text on primary
--primary-hover     oklch from #c8102e * 0.92 lightness
--ring              color-mix(in oklch, #c8102e 70%, transparent)  focus ring
```

> Focus-visible spacing is implemented in the component contract (`components_catalogue.md` §0) via the box-shadow stack `0 0 0 2px var(--background), 0 0 0 4px var(--ring)`. No separate `--ring-offset` token is defined — the offset is encoded in the shadow itself (Codex iter-2 P3 / iter-3 P3 fix: previous drafts named an undefined `--ring-offset`, removed).

### 2.3 Faithfulness palette (judgment #1: "is the sentence faithful to its source?")
Used by: verdict chips, sentence-level tints in the brief, proof-panel beat-2.
```
--verified            oklch(0.55 0.16 145)   green — claim ↔ span verified
--verified-bg         color-mix(in oklch, var(--verified) 12%, transparent)
--verified-border     color-mix(in oklch, var(--verified) 35%, transparent)
--verified-fg         oklch(0.32 0.12 145)   readable chip foreground on --verified-bg (≥4.5:1 AA)

--partial             oklch(0.70 0.16 75)    deep amber — partial support
--partial-bg          color-mix(in oklch, var(--partial) 14%, transparent)
--partial-border      color-mix(in oklch, var(--partial) 45%, transparent)
--partial-fg          oklch(0.36 0.14 65)    readable chip foreground on --partial-bg (≥4.5:1 AA)

--unsupported         oklch(0.52 0.20 320)   magenta-red — span does NOT support claim.
                                              DELIBERATELY chosen for chromatic distance from brand
                                              red (#c8102e ≈ oklch(0.53 0.21 22)). At hue 320° vs
                                              brand hue 22°, the eye cannot confuse "unsupported"
                                              with the primary CTA — clinical-safety-critical
                                              (Codex iter-1 P1 on this doc).
--unsupported-bg      color-mix(in oklch, var(--unsupported) 14%, transparent)
--unsupported-border  color-mix(in oklch, var(--unsupported) 45%, transparent)
--unsupported-fg      oklch(0.32 0.14 320)   readable chip foreground on --unsupported-bg (≥4.5:1 AA)
```

**Hue separation rule (binding):** the brand red occupies hue band 0°–40° (action+identity); the unsupported alarm occupies hue band 300°–340° (magenta-red). No other token may sit in either band. A perceptual color-distance test (deltaE-OKLCH) MUST be in CI before any new red/pink/magenta token lands.

### 2.4 Evidence-strength palette (judgment #2: "is the evidence strong enough to act on?")
Used by: certainty badges, SoF certainty column, proof-panel beat-3, dual-provenance strip "evidence-strength mix" pills. **Deliberately ordinal (saturation-step), not a hue chosen to match faithfulness** — so the user never visually conflates "supported" with "strong."
```
--certainty-high          oklch(0.42 0.10 245)   deep slate-blue (calm authority)
--certainty-high-fg       oklch(0.99 0.005 95)   near-white on the dark levels (≥7:1 AAA)
--certainty-moderate      oklch(0.50 0.10 245)   bumped 0.06 → 0.50 lightness so the near-white fg
                                                  passes WCAG AA. (Codex iter-3 P1: at lightness 0.56
                                                  the contrast was ~4.48:1 — JUST under AA 4.5:1.)
--certainty-moderate-fg   oklch(0.99 0.005 95)   near-white (≥4.6:1 AA verified)
--certainty-low           oklch(0.70 0.06 245)   light slate-blue
--certainty-low-fg        oklch(0.21 0.01 95)    near-black foreground (≥6.3:1 AAA)
                                                 — Codex iter-2 P1: near-white on --certainty-low is only ~2.6:1,
                                                 fails AA. Per-level foreground tokens fix this rather than
                                                 leaving the implementation to guess.
--certainty-very-low      oklch(0.85 0.03 245)   pale slate-blue
--certainty-very-low-fg   oklch(0.21 0.01 95)    near-black foreground (≥10:1 AAA)
```
**Foreground-by-level rule (binding):** dark backgrounds (`-high`, `-moderate`) use the near-white `*-fg`; light backgrounds (`-low`, `-very-low`) use the near-black `*-fg`. The component (§4 CertaintyBadge in `components_catalogue.md`) reads `var(--certainty-<level>-fg)` directly — never `var(--certainty-fg)` (which is intentionally NOT defined).

> **Why slate-blue, not green/amber/red:** evidence strength is independent of faithfulness. If both used the same family, a "VERIFIED + low" claim and a "PARTIAL + high" claim would visually blur. The contrast across families makes the two reads orthogonal at a glance.

### 2.5 Special states (orthogonal to both)
```
--contradiction     same as --partial          contradictions panel
--refusal           oklch(0.55 0.02 95)        neutral grey — refusal is dignified, not alarming
--refusal-bg        oklch(0.93 0.005 95)
--destructive       same as --unsupported      destructive actions, "Not signed" alarm
```

### 2.6 Contrast — WCAG 2.2 AA per surface
- All body text against `--background`: ≥7.0:1 (AAA where possible).
- Caption text against `--muted`: ≥4.5:1 (AA).
- Chip text on its own tinted background (`*-bg`): ≥4.5:1 (AA) — verified with axe in CI.
- Focus rings: ≥3:1 against the adjacent fill (UI-component contrast).

---

## 3. Space + density

8-pixel base rhythm. Two density modes; each component declares which it uses.

```
--space-0   0
--space-1   4px
--space-2   8px
--space-3   12px
--space-4   16px
--space-5   24px
--space-6   32px
--space-7   48px
--space-8   64px
```

**Comfortable** (reading surfaces — brief, intake, plan, run-progress): default. Generous padding (`space-4`/`space-5`), measure capped, line-height 1.55–1.6.
**Compact** (data surfaces — evidence pool table, SoF table, dashboard, audit hash chain): tighter padding (`space-2`/`space-3`), monospace numerals, no oversized type. Declared per surface via `data-density="compact"` attribute on the root container.

---

## 4. Radii, elevation, hairlines

```
--radius-sm   4px
--radius     8px
--radius-lg  12px
--radius-xl  16px      hero cards, proof panel
--radius-full 9999px   chips

--shadow-card        0 1px 2px oklch(0 0 0 / 0.04), 0 0 0 1px oklch(0 0 0 / 0.04)
--shadow-card-hover  0 4px 12px oklch(0 0 0 / 0.08), 0 0 0 1px oklch(0 0 0 / 0.06)
--shadow-popover     0 8px 24px oklch(0 0 0 / 0.12), 0 0 0 1px oklch(0 0 0 / 0.06)

--hairline     1px solid var(--border)
--hairline-strong  1px solid color-mix(in oklch, var(--border) 60%, var(--foreground))
```

Designed shadows only (no defaults). `<hr>` is replaced with `<div className="border-t border-border" />` at 1px or a 0.5px low-alpha variant for nested rules.

---

## 5. Motion tokens

Three durations, one easing. Every animation declares **why** it moves (state communication, Vercel guideline) — never decoration.

```
--motion-fast    120ms     micro-interactions: hover/focus tint, chip settle, pill swap
--motion-base    200ms     state reveals: badge appear, source card settle, proof beat advance
--motion-slow    320ms     view transitions: panel slide-in, tab cross-fade, page transition

--ease-standard  cubic-bezier(0.2, 0, 0, 1)    Material/Linear-aligned standard ease
--ease-emphasized cubic-bezier(0.2, 0, 0, 1)   same — we only use one curve for consistency
```

**`prefers-reduced-motion` is honored everywhere via CSS `@media (prefers-reduced-motion: reduce)`**: animations collapse to instant state swap (duration=0, no transform). Implemented as a Tailwind utility `motion-reduce:animate-none` plus token-aware components that bypass JS-orchestrated sequences when the query matches.

**Motion that is honest:**
- A revealing animation signals "this is the result of your action" (proof beat advance, source settle).
- A counter-up on the verdict header signals "this brief just loaded; here are its counts." (≤320ms; stops on second view via `prefers-reduced-motion` OR sessionStorage flag.)
- A skeleton fade signals "real content is replacing this skeleton" (not a decorative shimmer).

**Motion that is FORBIDDEN:**
- Decorative parallax, drift, "live" backgrounds.
- Animations that exceed `--motion-slow` (320ms) without an active loading reason.
- Anything that triggers more than once on the same view without a state change.

---

## 6. The Six Microstates (every interactive element)

Each component declares its concrete CSS contract per-state in `components_catalogue.md`. The states + when each is the only acceptable visual:

| State | Trigger | Visual contract |
|---|---|---|
| **default** | resting | base tokens; calm |
| **hover** | pointer in (`:hover`) | tint shift (≤8% saturation) at `--motion-fast`; no layout shift |
| **focus** | keyboard `:focus-visible` | `--ring` 2px outset, with the offset encoded directly in the box-shadow stack (see `components_catalogue.md` §0); *always visible* |
| **active** | pressed (`:active`) | tint shift +12%, micro-scale 0.97 at `--motion-fast` |
| **disabled** | `aria-disabled` / `disabled` | opacity 0.55, cursor not-allowed, no hover/active reaction |
| **loading** | in-flight | stable skeleton (no layout shift), `aria-busy="true"`, accessible "loading <thing>" label |

All six are mandatory and tested via Playwright traces (per the I-ux-001 plan §15 acceptance "interaction acceptance tests"). The catalogue (`components_catalogue.md`) gives concrete CSS for each component × state.

---

## 7. The Maple Leaf — production spec

The sovereignty mark. Operator flagged the current "low-fidelity dot-cloud" — replaced with a crisp SVG.

```
asset:    web/components/marks/maple_leaf.svg   (single inline-able SVG, viewBox=0 0 24 24)
fill:     currentColor (tinted by container)
sizes:    sm 14×14, md 18×18 (default), lg 24×24, hero 48×48
contrast: ≥3:1 vs surrounding fill
placement: sovereignty/identity beats only — site header lockup, transparency page hero, signed-receipt seal, sign-in left panel. Never as a decorative repeating motif.
```

Stroke variant for the proof-replay signature affordance (beat 5): outlined ring + leaf, 1px stroke at `--motion-base`-fade-in when `signatureState === "gpg_verified"`.

---

## 8. Trust copy (de-jargon, plan §12)

Authoritative substitutions — implemented as content constants under `web/lib/trust_copy.ts` so no string drifts.

```ts
// web/lib/trust_copy.ts — single source of truth for user-facing trust language
export const TRUST_COPY = {
  twoFamily: {
    badge: "Independent-family check",  // was: "two-family invariant"
    tooltip: "Verified by a different model family than the writer.",
  },
  signature: {
    verified: "Signed bundle",                      // gpg_verified
    attached: "Signature attached — verify offline", // present_unverified
    missing: "Not signed — trust not established",   // missing  (was: "Signature missing")
  },
  evidenceSet: "Evidence set",            // was: "POOL ID"
  scopeRefusal: "Out of scope — won't answer",
  inadequateCorpus: "Evidence cannot support a safe answer for this question",
  // verbiage that gets templated into proof beats, intended-use banner, etc.
} as const;
```

No internal strings (`refusal-bait`, `PICO axis`, `scope` without explanation, `POOL ID`, `two-family invariant`) appear in user-visible copy. Enforced by an axe content-rule rule or a simple Playwright assertion that asserts the rendered text doesn't contain the banlist.

---

## 9. Implementation order (no code in this Issue — spec only)

The migration to v2:
1. **This Issue** (`I-ux-001b`): all tokens + components + storyboards specified in docs only.
2. **Subsequent Issues** (per-page rebuilds): each page consumes v2 tokens incrementally. The audit + visual review on each page is the validation. Tokens become real CSS variables in a single small PR when the first page-rebuild Issue lands.

---

## Acceptance for I-ux-001b (this doc + the catalogue + the storyboards together)

- Codex APPROVE on a single brief covering all three foundation docs.
- Each token has a stated use + a stated reason (this doc).
- Each component has a spec (next doc: `components_catalogue.md`) covering all six microstates + responsive behavior + a11y.
- Hero motion storyboard (next doc: `proof_replay_storyboard.md`) is frame-level: what moves, when, why, reduced-motion equivalent.
- (When Figma OAuth is live) the hero prototype + key frames are exported to `web/p2shots/I-ux-001b/` and Codex visual-audits via `codex exec -i`.
