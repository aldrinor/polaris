# Components Catalogue (I-ux-001b / #876)

**Status:** SPEC — Codex review pending. Implements the foundation catalogue Codex iter-1 P1 flagged as strictly required before any implementation Issue can start.

Scope (Codex iter-1 §13): the minimum components subsequent implementation Issues need — the hero stack + the shared interactive primitives. Each entry: purpose · props · all six microstates × concrete CSS contract · responsive behavior · a11y. Tokens referenced are from `docs/web/design_tokens_v2.md`.

---

## 0. Shared interactive contract (every clickable/focusable element)

Six microstates × the CSS contract that satisfies them. Selector group `.interactive` is applied as a Tailwind v4 layer; every component-level class composes from it (Codex iter-2 P1: not just `.btn` — links, `[role="button"]`, sentence affordances all consume the contract).

```css
@layer components {
  /* Selector group: every clickable/focusable element opts in via `.interactive`
     or via the role/tag selectors below — implementations may rely on either. */
  .interactive,
  button, [role="button"], a[href], summary,
  .btn, .link, .chip[role="button"], [tabindex="0"][data-claim] {
    transition:
      background-color var(--motion-fast) var(--ease-standard),
      border-color var(--motion-fast) var(--ease-standard),
      transform var(--motion-fast) var(--ease-standard),
      color var(--motion-fast) var(--ease-standard),
      box-shadow var(--motion-fast) var(--ease-standard);
  }

  /* hover: tint shift ≤8%, no layout shift */
  .interactive:hover,
  button:not(:disabled):hover, [role="button"]:not([aria-disabled="true"]):hover,
  a[href]:hover, .btn:hover, .link:hover {
    background-color: color-mix(in oklch, currentColor 6%, transparent);
  }

  /* focus-visible: always-visible 2px ring + 2px offset against background.
     Codex iter-2 P3: avoids any reference to a non-existent --ring-offset
     token by encoding the offset directly in the box-shadow stack. */
  .interactive:focus-visible,
  button:focus-visible, [role="button"]:focus-visible,
  a[href]:focus-visible, summary:focus-visible, .btn:focus-visible, .link:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px var(--background), 0 0 0 4px var(--ring);
  }

  /* active: tint +12%, micro-scale 0.97 */
  .interactive:active,
  button:not(:disabled):active, [role="button"]:not([aria-disabled="true"]):active,
  a[href]:active, .btn:active, .link:active {
    transform: scale(0.97);
    background-color: color-mix(in oklch, currentColor 10%, transparent);
  }

  /* disabled: opacity 0.55, cursor not-allowed, no hover/active reaction */
  .interactive[aria-disabled="true"],
  button:disabled, [role="button"][aria-disabled="true"],
  a[aria-disabled="true"], .btn[aria-disabled="true"], .btn:disabled, .link[aria-disabled="true"] {
    opacity: 0.55;
    cursor: not-allowed;
    pointer-events: none;
  }

  /* loading: stable skeleton + aria-busy + VISIBLE spinner.
     Codex iter-2 P1: the prior contract set `color: transparent` while the
     spinner used `currentColor`, making the spinner invisible. Fix: hide the
     text via a span wrapper, NOT color, and color the spinner from an
     explicit token (--foreground or its on-surface inverse). */
  .interactive[aria-busy="true"],
  button[aria-busy="true"], [role="button"][aria-busy="true"],
  .btn[aria-busy="true"], .link[aria-busy="true"] {
    position: relative;
    pointer-events: none;
  }
  .interactive[aria-busy="true"] > *,
  .btn[aria-busy="true"] > *, .link[aria-busy="true"] > * {
    visibility: hidden; /* hide label without losing layout/width */
  }
  .interactive[aria-busy="true"]::after,
  .btn[aria-busy="true"]::after, .link[aria-busy="true"]::after {
    content: "";
    position: absolute; inset: 0; margin: auto;
    width: 1em; height: 1em; border-radius: 50%;
    /* explicit, NOT currentColor — currentColor was inheriting the
       text color which we previously zeroed. */
    border: 2px solid var(--foreground);
    border-right-color: transparent;
    animation: polaris-spin 0.8s linear infinite;
  }
  @keyframes polaris-spin { to { transform: rotate(360deg); } }

  @media (prefers-reduced-motion: reduce) {
    .interactive, button, [role="button"], a[href], summary, .btn, .link {
      transition: none;
    }
    .interactive:active, button:active, .btn:active, .link:active { transform: none; }
    .interactive[aria-busy="true"]::after,
    .btn[aria-busy="true"]::after, .link[aria-busy="true"]::after {
      animation: none;
      /* still show a non-spinning indicator so loading remains visible */
      border-right-color: var(--foreground);
    }
  }
}
```

Every component below references this baseline; departures are documented inline.

---

## 1. `<ClaimSentence>` — the affordance every sentence in a brief carries

Purpose: render a sentence with the two-judgment affordances (faithfulness underline, certainty dot) and make it the interaction target for "challenge."

```ts
interface ClaimSentenceProps {
  id: string;                                          // for keyboard nav focus targets
  text: string;
  faithfulness: "verified" | "partial" | "unsupported";
  certainty: "high" | "moderate" | "low" | "very-low";
  onChallenge: (id: string) => void;                   // click / Enter / tap
}
```

**Visual** (Stage 0 of `proof_replay_storyboard.md`):
- Inline element rendered as `<span>` (NOT a button — semantically a paragraph word; keyboard focusability is added via `tabindex="0"` so the sentence reads naturally in screen readers).
- Underline: `box-shadow: inset 0 -0.18em 0 0 color-mix(in oklch, var(--<faithfulness>) 35%, transparent)` (avoids `text-decoration` which can't carry a tint without `text-decoration-color` only on modern engines).
- Leading-margin certainty dot: `::before { content: ""; … background: var(--certainty-<level>); width: 4px; height: 4px; border-radius: 50%; margin-right: 6px; }` — rendered in the left margin via negative `margin-left` of the paragraph so it doesn't disrupt the prose measure.

**Microstates:**
- **default** as above.
- **hover** (`:hover` only — mobile uses tap): underline tint alpha 35% → 70% over `--motion-fast`; certainty dot 4px → 6px (no color change); cursor `help`.
- **focus** (`:focus-visible`): same as hover PLUS the `--ring` 2px outline + 2px offset.
- **active** (`:active`): tint alpha 70% → 85%; brief scale on the dot (4 → 6 → 4) is too noisy → just the alpha bump.
- **disabled**: rare for a sentence; if present (locked report), set `aria-disabled="true"`, opacity 0.55, no hover.
- **loading**: rare; only when the per-sentence verdict is still being computed → render the sentence with a faint pulse on the underline (`@keyframes pulse-underline` 1.2s, reduced-motion → solid 50% alpha).

**A11y:**
- `role="button"` with `aria-label="Challenge: <truncated text>"` (sentence text in label is truncated to first 80 chars for screen-reader brevity).
- `aria-keyshortcuts="Enter Space"` so AT announces the interaction.
- The certainty dot has `aria-hidden="true"` (decorative); its semantic content is mirrored in the chip the proof panel surfaces.

---

## 2. `<ProofPanel>` — the docked surface for the 6-beat reveal

Purpose: docked right rail on desktop / bottom sheet on mobile (Stages 2–4 of the storyboard).

```ts
interface ProofPanelProps {
  open: boolean;
  claim?: ClaimSentenceProps;       // the sentence being challenged
  evidenceSpan?: SourceCardProps;
  signatureState: SignatureState;
  onClose: () => void;
  onPrev: () => void;               // J
  onNext: () => void;               // K
}
```

**Visual:**
- Desktop: fixed right `top: 0; right: 0; bottom: 0; width: 480px;` over a 50% scrim on the brief. Slide-in `transform: translateX(110%) → 0` over `--motion-base` `ease-standard`.
- Mobile: fixed bottom `left: 0; right: 0; bottom: 0; height: 75vh;` with a drag handle. Slide-in `transform: translateY(100%) → 0`.
- Inside: scrollable vertical layout of beats 1→6 (component children).

**Microstates:**
- **default open** = visible per visual.
- **default closed** = `transform: translate(110% | 100%)` + `pointer-events: none` + `aria-hidden="true"`.
- **hover** N/A (panel is a surface, not an interactive element itself).
- **focus** — focus *trap* engaged when open (`focus-trap-react` or manual); on open, focus moves to a "Challenged sentence" header element (`tabindex="-1"`); on close, focus returns to the originating `<ClaimSentence>`.
- **active** N/A.
- **disabled** N/A.
- **loading** — when waiting for the verdict payload, render the layout skeleton (claim block + 5 placeholder bars) with `aria-busy="true"`.

**Keyboard contract:**
- `Esc` → `onClose()`.
- `J` / `↓` → `onNext()`; `K` / `↑` → `onPrev()`. (Compatible with Vim users + standard arrow expectations; both bindings active.)
- `Tab` walks: claim header → faithfulness chip detail-trigger → certainty badge → source-card "Open source" → signature pill → "what this does NOT prove" disclosure.
- Inside the bottom-sheet on mobile: swipe-down on the handle → `onClose()`; swipe-left → `onNext()`; swipe-right → `onPrev()` (`touchstart`/`touchmove`/`touchend`; not gestures wrapper to keep deps light).

**A11y:**
- `role="dialog"` + `aria-modal="true"` + `aria-labelledby="proof-panel-claim-header"`.
- Focus trap engaged on open.
- Backdrop click → `onClose` (configurable; per the operator's UX preference can be set to ignore to prevent accidental dismiss during exploration).

---

## 3. `<FaithfulnessChip>` — Beat-2 verdict badge

Purpose: at-a-glance "is the sentence faithful to its source?" One of three states.

```ts
interface FaithfulnessChipProps {
  state: "verified" | "partial" | "unsupported";
  family?: string;                  // e.g. "Gemma-4-31B" (the independent-family evaluator name)
  reason?: string;                  // shown on hover/expand for partial/unsupported
}
```

**Visual:**
- Pill: `padding: 4px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.04em;`
- States:
  - **verified**: `background: var(--verified-bg); color: var(--verified-fg); border: 1px solid var(--verified-border);` icon `<Check>`.
  - **partial**: same pattern using `--partial-*` tokens, icon `<MinusCircle>`.
  - **unsupported**: same pattern using `--unsupported-*` tokens (magenta-red per tokens §2.3), icon `<XCircle>`.
- Label text: `VERIFIED · PARTIAL · UNSUPPORTED`.

**Microstates:** baseline (§0) — except this chip is NOT clickable by default; it becomes interactive (cursor: help, focus ring) only if `reason` is provided, in which case it opens a popover with `reason` text.

**A11y:**
- `role="status"` (non-interactive read) OR `role="button"` when interactive.
- `aria-label="Faithfulness: VERIFIED"` (state spelled out).

---

## 4. `<CertaintyBadge>` — Beat-3 evidence-strength badge

Purpose: at-a-glance "how strong is the underlying evidence?" Ordinal. **Visually orthogonal to FaithfulnessChip** (token §2.4 slate-blue, not green/amber/red).

```ts
interface CertaintyBadgeProps {
  level: "high" | "moderate" | "low" | "very-low";
  studyType: string;                 // "RCT · Phase 3 · n=1879"
  dominantDowngrade?: string;        // "imprecision: wide CI" — null for HIGH
  href?: string;                     // → Summary of Findings for this outcome
}
```

**Visual:**
- Pill: same dimensions as FaithfulnessChip (visual rhyme) but **different shape detail**: square corners on the leading edge (`border-radius: 4px 9999px 9999px 4px`). Squareness signals "different category of read" without needing a different color family.
- Color per level: solid `--certainty-<level>` background, `--certainty-fg` text. No tint+border; this is a solid pill (vs the FaithfulnessChip tint+border) — the visual treatment itself signals "different read."
- Beneath: caption row `<studyType>` + (if present) `<dominantDowngrade>` + `<a href=>→ Summary of Findings</a>` (the link inherits the shared baseline §0).

**Microstates:** baseline. Interactive only via the SoF link, not the pill itself.

**A11y:** `role="status"`, `aria-label="Evidence strength: HIGH · RCT · Phase 3 · n=1879"`.

---

## 5. `<SourceCard>` — Beat-4 source identity

```ts
interface SourceCardProps {
  journal: string; year: number; doi?: string; tier: "T1" | "T2" | "T3";
  whySelected: string;               // "T1 head-to-head RCT, primary endpoint match"
  // The actual span text is rendered by a sibling <SourceSpanPreview>, not here
}
```

**Visual:**
- Compact card: `padding: 12px; border: var(--hairline); border-radius: var(--radius); background: var(--card);`
- Header row: `<journal>` bold + ` · <year> · <doi> · <tier-pill>`.
- Body: `<small>Why this source: <whySelected></small>` in `--muted-foreground` text-caption.
- Tier pill: `T1` solid `var(--certainty-high)` bg; `T2` solid `var(--certainty-moderate)`; `T3` solid `var(--certainty-low)` — reuse the certainty palette so "tier" reads as "evidence-strength input" (which it semantically is).

**Microstates:** baseline (entire card is clickable to "open the source" — a link inherits §0).

---

## 5a. `<SourceSpanPreview>` — the in-context source-text window (Beat 4 sibling)

Purpose: render the source text with the matched span(s) highlighted continuously (phrase-grouped, NOT pink word tiles). Companion to `<SourceCard>`.

```ts
interface SourceSpanPreviewProps {
  /** The full source text (already fetched by the loader). */
  text: string;
  /** Span ranges to highlight, half-open intervals in chars (start inclusive, end exclusive). */
  spans: { start: number; end: number; faithfulness: "verified" | "partial" }[];
  /** Tint family: takes its color from the FaithfulnessChip's state. */
  tint: "verified" | "partial";
  /** Scroll the first span into view on mount/update. Default true. */
  autoScroll?: boolean;
}
```

**Visual:**
- `<pre>` wrapper with `white-space: pre-wrap; font-family: var(--font-mono); font-size: var(--text-mono);` — fixed-width so highlights align cleanly with the source text.
- Each contiguous range from `spans` is rendered as a single `<mark>` with `background: var(--<tint>-bg); color: var(--foreground); border-radius: 2px; padding: 0 2px;` — phrase-grouped (one rect per range; non-matched text has NO background).
- A leading `<MapleLeaf>` mark NOT shown here (that's for the SignaturePill); the source preview is calm and editorial.
- Container has `max-height: 60vh; overflow: auto;` on desktop, `40vh` on the mobile bottom-sheet variant.

**Reveal animation (Beat 4 within the proof panel):**
- Highlight in: `mask-image: linear-gradient(90deg, black 0%, black 0%, transparent 0%) → linear-gradient(90deg, black 0%, black 100%, transparent 100%)` over `--motion-fast` (120ms — Codex iter-2 P2 fix), `ease-standard`. Reads as left-to-right reveal.
- Auto-scroll: smooth scroll to bring the first highlight to ~30% of the visible area, over `--motion-base` (200ms).
- Reduced-motion: instant, no scroll-animation (`scrollTo({ behavior: "instant" })`).

**Microstates** (baseline §0 applies only to the optional "Open full source" link rendered above the preview).
- The `<mark>` highlights are NOT interactive themselves.

**Responsive:** mobile bottom-sheet caps height per above; pinch-to-zoom is honored (no `touch-action: none`).

**A11y:**
- `<pre>` has `role="region"` + `aria-label="Source span containing the cited evidence"`.
- Each `<mark>` is announced by AT as "marked text" natively; supplement with `aria-label="Matched evidence span"` on the first mark in the range.
- Source text size respects browser font-size + supports up to 400% zoom without horizontal scroll on desktop.

---

## 6. `<SignaturePill>` — Beat-5 receipt

```ts
interface SignaturePillProps {
  state: "missing" | "present_unverified" | "gpg_verified";
  bundleId?: string;
  keyName?: string;                   // "POLARIS Carney Demo key"
  onOpenReceipt: () => void;
}
```

**Visual:**
- **gpg_verified**: green tint pill (token `--verified-bg`/`--verified-fg`) + `<MapleLeaf>` mark (stroke variant, tokens §7) + label `"Signed bundle · {keyName}"`. Sub-line: `"Sealed in {bundleId}"` in mono + ` · → Verify offline (Receipt)` link.
- **present_unverified**: amber tint (`--partial-bg`/`--partial-fg`) + `<ShieldAlert>` icon + label `"Signature attached — verify offline"`. Sub-line: the `gpg --verify` command in mono + ` · → Receipt`.
- **missing**: grey-on-grey (`--muted`/`--muted-foreground`) + `<ShieldAlert>` icon + label `"Not signed — trust not established"`. No Receipt link.

**Microstates:** baseline. The `→ Receipt` link inherits §0.

**A11y:**
- `role="status"` with the state spelled out: `aria-label="Signature: signed and GPG-verified"` etc.

---

## 7. `<WhatThisDoesNotProve>` — Beat-6 honesty disclosure

Purpose: always-present collapsed disclosure with the LAW-II limits of the verification.

```ts
interface WhatThisDoesNotProveProps {
  /** Optional override list of bullet points; default = the 4 standard limits. */
  bullets?: string[];
}
```

**Visual:**
- `<details>` element. Summary: `"What this does NOT prove"` in `--muted-foreground`, small caps, leading `<Info>` icon.
- On open: bullet list with the four default limits (tokens §8 + the proof-replay storyboard Beat 6 copy).

**Microstates:** baseline; the `<summary>` inherits §0 focus contract via `summary { outline: none; }` override + focus-visible ring.

**A11y:** `<details>` is natively accessible; AT announces "expand/collapse." Don't add `aria-expanded` manually — the browser does it.

---

## 8. `<IntendedUseBanner>` — the "non-device CDS" banner

Purpose: standing visible per plan §6 — appears on the brief, the receipt, and `/transparency`. Compact, calm, not alarming.

```ts
interface IntendedUseBannerProps {
  variant?: "inline" | "footer";    // inline = beneath the brief title; footer = at audit/transparency
}
```

**Visual:** muted card, `--muted` background, `--hairline` border, body text states the intended user / use / non-use / non-reliance. No animation.

---

## 9. Shared `<Button>` / `<Link>` baseline

Defined elsewhere in the codebase today (base-ui shadcn). The §0 contract above is added as a Tailwind-v4 layer override; existing button sizes (default/sm/lg/xs/icon) remain. New requirement: the `aria-busy` loading variant (§0) is added.

---

## 10. Wiring catalogue

For implementation Issues to consume:

| Storyboard surface | Components used |
|---|---|
| Stage 0 brief reading | `<ClaimSentence>` (n×, one per sentence) |
| Stage 2 the 6 beats | `<ProofPanel>` containing `<FaithfulnessChip>`, `<CertaintyBadge>`, `<SourceCard>` + `<SourceSpanPreview>` (§5a), `<SignaturePill>`, `<WhatThisDoesNotProve>` |
| Stage 4 mobile bottom-sheet | same as Stage 2 with the panel in bottom-sheet variant |
| Home teaser (Stage 7) | inline `<ProofPanel>` variant + `<ClaimSentence>` |
| Brief level | `<IntendedUseBanner>` |

That covers every interactive element the storyboard exercises. No component is "assumed" anymore (Codex iter-1 §4 P1 close).
