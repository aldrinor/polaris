# Proof Replay — Hero Motion Storyboard (I-ux-001b / #876)

**Status:** SPEC — Codex review pending. Implements §4 of the Codex-APPROVED I-ux-001 plan: the "challenge any sentence" chain-of-custody reveal. The single make-or-break interaction.

**Hard rules (plan §4 + §12 + Vercel motion guidance):**
- Motion **communicates state**, never decorates. Every frame answers: *what changed, why does this animation make that clearer?*
- **Timing targets (Codex iter-1 P1 clarification — the < 400ms is "time-to-first-proof", NOT the total reveal):**
  - **time-to-first-proof < 400ms**: from challenge click → **Beat 2 verdict visible** (the user has the answer in <400ms; remaining beats are progressive disclosure the user can read as they paint).
  - **span highlight in Beat 4 ≤ 150ms** once that beat is reached.
  - **claim-to-claim switch < 120ms** perceived (Stage 3).
  - The full 6-beat cumulative paint completes by ~700ms — but the user has already seen the verdict at 250ms; beats 3-6 enrich without blocking comprehension.
- `prefers-reduced-motion: reduce` → instant state swap, no animation, no scroll-jump (controlled re-render only).
- Keyboard-first: `J`/`K` navigate sentences, `Enter` challenges, `Esc` closes the panel, `Tab` walks the beats inside it.
- Mobile-real: hover-to-reveal does NOT exist. Tap to challenge → bottom-sheet at 75vh.
- The **two judgments stay visually orthogonal** at every beat (token §2.3 vs §2.4).

---

## Stage 0 — Resting state (the brief)

Calm clinical document. No animation. Each sentence carries TWO subtle, separately-coloured affordances:
- A **hairline underline tint** at the sentence's faithfulness color (`--verified` / `--partial` / `--unsupported`, alpha 0.35). Underline-offset 4px so it never confuses with a hyperlink.
- A **certainty dot** (4px circle) in the leading margin, color from the certainty scale (`--certainty-{high|moderate|low|very-low}`). Margin position not inline; never adjacent to the underline.

```
default (illustrated with a REAL verified sentence from the shipped bundle:
        web/public/canonical_bundles/v1_canonical_success/verified_report.json
        section "Efficacy", first verified sentence)
┌──────────────────────────────────────────────────────────────────────────────┐
│ ● The estimated treatment differences were −0.15 percentage points (95% CI   │  ←  ● = high certainty (slate-blue)
│ ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾  │  ←  underline = verified (green tint)
│   −0.28 to −0.03), −0.39 percentage points (95% CI −0.51 to −0.26), and      │
│   −0.45 percentage points (95% CI −0.57 to −0.32), all favoring tirzepatide. │
└──────────────────────────────────────────────────────────────────────────────┘
```

No chips inline; no hover until the user moves focus to a sentence. The brief reads as prose first.

---

## Stage 1 — Focus / hover a sentence (peek, not commit)

`:focus-visible` OR `:hover` on a sentence:
- **Underline tint:** alpha 0.35 → 0.7 over `--motion-fast` (120ms). Subtle "this is a leaf, and there's more to see."
- **Certainty dot:** 4px → 6px diameter, no color change. Same duration.
- **Cursor:** changes to `default` with a faint trailing `?` glyph (CSS `cursor: help`).
- **No panel opens.** This is the "peek" — confirms the affordance, doesn't commit the user.

`prefers-reduced-motion`: same end-states, applied instantly.

---

## Stage 2 — Challenge (click / tap / Enter): the 6-beat reveal

Trigger: pointer click on a sentence, tap on mobile, or `Enter` when the sentence has keyboard focus. Beats are sequenced with explicit waits — never simultaneous (that would read as a generic transition, not a sequence). Each beat MUST land with the previous beat still visible (cumulative, not replacing).

### Beat 0 (preamble — 0ms): commit the selection
- The challenged sentence gains a 2px left border of its faithfulness color, expanded from 0 → 2px over `--motion-fast`. No layout shift (the border is inset).
- The proof panel container slides in from the right (desktop) or bottom (mobile):
  - desktop: `transform: translateX(110%) → 0` over `--motion-base` (200ms), `ease-standard`. Width 480px (24% of a 1920 viewport).
  - mobile: `transform: translateY(100%) → 0` over `--motion-base`. Height 75vh, top sheet has a drag handle.
- Panel container is empty for one tick (~16ms) — beat-1 fills in instantly so there's no flash of empty box.

### Beat 1 (0 → 100ms): **Claim**
Beat-1 surfaces in the panel as: an H3 "Challenged sentence" label + the sentence text (the same text the user clicked, monospaced-quoted for unambiguity — no rewording).
- Text fades in via `opacity: 0 → 1` over `--motion-fast` (120ms). No vertical translate.
- The H3 label uses the **faithfulness color** for its leading icon (a small "?" badge), pre-staging beat-2.

**Why this beat:** the user must confirm "yes, that's the sentence I challenged" before the verdict lands. Removes the "wait, which sentence?" hiccup.

```
desktop panel (480w):
┌────────────────────────────────────────────┐
│  Challenged sentence    [?]                 │
│  ────────────────────────                   │
│  "Tirzepatide 15 mg once weekly reduced     │
│   HbA1c by 2.4% vs baseline at 40 weeks in  │
│   the SURPASS-2 trial."                     │
│                                              │
│  [ Beats 2-6 will appear below ... ]        │
└────────────────────────────────────────────┘
```

### Beat 2 (100 → 250ms): **Faithfulness verdict**
A `<FaithfulnessChip>` (token §2.3 palette) settles into place under the claim with:
- The chip translates `transform: translateY(8px) → 0` while opacity `0 → 1` over `--motion-base`. Single-axis — no scale, no rotate.
- A second-line caption appears at `+50ms` (offset from chip): *"Checked by an independent model family (not the writer)."* + the specific deterministic checks ("numeric match: 2/2 · content-word overlap: 7 words · span bounds: in range") in mono.
- A small "i" affordance opens a tooltip with the `TRUST_COPY.twoFamily.tooltip` line.
- The H3 "?" icon from beat-1 morphs into the verdict color (CSS `color` transition over `--motion-fast`).

```
│  [✓ VERIFIED]   independent-family check               │
│  numeric match: 2/2 · content-word overlap: 7 · span ok│
```

### Beat 3 (250 → 400ms): **Evidence strength**
A `<CertaintyBadge>` (token §2.4 slate-blue palette) appears below the verdict with EXPLICIT relabeling so it's never confused with beat-2:
- Header line: **"How strong is the evidence?"** in caption.
- Badge: pill with the certainty level (`HIGH | MODERATE | LOW | VERY LOW`) in slate-blue.
- One-line *dominant downgrade reason* + the underlying study type (`RCT · Phase 3 · n=1879`) in caption + mono.
- A "→ Summary of Findings" link routes to the SoF view for this outcome.
- Same translateY+fade choreography as beat-2 but offset (it's a separate read, not a continuation).

```
│  How strong is the evidence?                            │
│  [HIGH]   ↓ downgrade: none · RCT · Phase 3 · n=1879   │
│           → Summary of Findings                          │
```

### Beat 4 (400 → 600ms): **Source span**
This is the moment the proof becomes tangible.
- Below the certainty section, a `<SourceCard>` slides up showing the source's header: journal · year · DOI · tier · *why this source was selected*.
- Simultaneously (this is the only acceptable simultaneity in the sequence), the **inline source preview** below the card scrolls to the cited span and the phrase-grouped highlight animates in:
  - Highlight progresses left-to-right via a CSS gradient mask (`mask-image: linear-gradient(90deg, black 0% → 100%)`) over `--motion-base` — reads as "this is the exact span."
  - Phrase-grouped: contiguous matched words share one highlight rectangle (`background: var(--verified-bg)` for verified claims; `var(--partial-bg)` for partial); non-matched separators have NO background.
  - NO "pink word tiles" — the iter-1 plan finding. Continuous reading bands only.

```
│  Source                                                 │
│  ────                                                   │
│  N Engl J Med · 2021 · doi:10.1056/NEJMoa2107519 · T1  │
│  → Why this source: T1 head-to-head RCT, primary endpoint match
│  ──────────────────────────────────────                 │
│  The reduction in HbA1c from baseline was ▒▒▒▒▒▒▒▒▒▒▒▒  │
│  ▒▒2.46 ± 0.07 percentage points▒▒ with tirzepatide 15 │
│  mg compared with ...                                   │
└────────────────────────────────────────────────────────┘
```

### Beat 5 (600 → 700ms): **Signature (the receipt)**
A `<SignaturePill>` appears at the panel's footer.
- ONLY renders the green "⬡ Signed bundle" affordance when `signatureState === "gpg_verified"` (per I-ux-001a). Otherwise the amber "Signature attached — verify offline" OR grey "Not signed — trust not established."
- One-line meaning: **"Sealed in bundle bundle_real_tirzepatide_0001 · POLARIS Carney Demo key."**
- One affordance: **"→ Receipt view"** opens the Receipt panel (offline-verify flow).
- Maple-leaf mark (stroke variant, §7 of tokens) fades in beside the verdict — visible sovereignty/identity beat.

```
│  ⬡ Signed bundle · POLARIS Carney Demo key             │
│  Sealed in bundle_real_tirzepatide_0001                 │
│  → Verify this offline (Receipt)                        │
```

### Beat 6 (always available, never the focus): **"What this does NOT prove"**
A collapsed disclosure at the very bottom of the panel, always present. Title: *"What this does NOT prove."* When expanded:
- "Faithfulness ≠ source correctness" — we checked the sentence against its source; we did not validate that the source is right.
- "Independent-family check ≠ clinical validation" — it's an independence/consistency signal with measured reliability X (gold-set %), not regulatory validation.
- "Absence of contradiction in this brief ≠ completeness" — we surface contradictions found in our retrieved set, not the entire literature.
- "Evidence strength rating ≠ a formal GRADE appraisal" — it's a decision-support read; a formal appraisal is the reviewer's job.

No animation when the panel opens — the disclosure is intentionally quiet. Reduced-motion treats it identically.

---

## Stage 3 — Switching claims inside the proof panel

User presses `J` / `K` (or taps the next sentence) without closing the panel:
- The panel **does not slide-out** — it transitions IN PLACE.
- Beat-1 (claim text) cross-fades to the new sentence over `--motion-fast`.
- Beats 2-3 (verdict + certainty) flip to the new values via opacity+translateY-8px-to-0 in `--motion-fast`, sequenced 0ms/40ms (compressed vs the first reveal — the panel is already open, the user expects speed).
- Beat-4 (source) cross-fades the card; the source-text preview scrolls to the new span at `--motion-base`. The previous span-highlight animates OUT (mask gradient right-to-left, 100ms) WHILE the new one animates IN — the two are spatially adjacent so the eye follows continuously.
- Beat-5 (signature) may stay the same (same bundle) — no animation; the pill quietly does nothing.

Performance target: claim-to-claim < 120ms perceived.

---

## Stage 4 — Mobile (bottom-sheet) variant

- Trigger: tap the sentence (no hover state on touch).
- Sheet slides up from below at 75vh, drag handle at top.
- Beats stack vertically; the source preview is below the source-card and gets a fixed 40vh region of its own.
- Swipe-left / swipe-right inside the sheet = next/previous claim (J/K analogue).
- Pinch-to-zoom is NOT intercepted (source text must remain zoomable for accessibility).
- Sheet dismiss: swipe-down on handle OR tap the dimmed page area above.

---

## Stage 5 — Reduced motion equivalent

`@media (prefers-reduced-motion: reduce)` collapses every above animation to instant state swap. The sequencing INTENT is preserved as VISUAL HIERARCHY (top-to-bottom in the panel):

- Beat 0: panel appears instantly with all six beats laid out.
- The user reads top-to-bottom; the layout itself is the storyboard.
- Cursor-help indicator is the only "hover" feedback (CSS cursor change requires no transition).

**Tested with `npm run test:e2e -- --grep proof_replay_reduced_motion`** as part of the I-ux-001 plan §15 acceptance.

---

## Stage 6 — Failure-state choreography

Cases the storyboard handles HONESTLY (plan §6 + §11). Column headings name the beat each row's content describes (Codex iter-1 P3 fix — the prior header was mislabeled):

| State | Affected beat | Reads as |
|---|---|---|
| `signatureState=missing` on the bundle | Beat 5 (Signature) | **"Not signed — trust not established."** in grey; no green pill |
| `signatureState=present_unverified` | Beat 5 (Signature) | **"Signature attached — verify offline."** in amber + the `gpg --verify` command in mono |
| `verdict=UNSUPPORTED` | Beat 2 (Faithfulness) | red chip + the failing-check reason (e.g. "numeric token 2.4% not in span"). Beat 3 is omitted (no evidence-strength read when the claim isn't supported by its source); Beat 4 still shows the source span so the reviewer can see the gap. |
| `inadequacy refusal` (bundle-level, plan §5) | whole brief | renders the *refusal screen* (plan §6 failure-state design), not individual sentence chips — Proof Replay is not the surface for "we won't answer." |

---

## Stage 7 — The Home teaser (compact 6-beat inline)

Per plan §4 Home teaser: the same 6-beat reveal runs **inline on the home page** for a single real claim from the existing real signed bundle. Compressed timing (total 500ms) + a more emphatic visual signature so it reads as a 30-second product demo.

```
HOME — proof-as-hero (illustrated with the REAL first verified sentence from
the shipped bundle web/public/canonical_bundles/v1_canonical_success — Codex
iter-1 P1 fix: the prior mock used fabricated text, the spec now uses the
actual claim the home page will render):
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                                │
│  Deep research you can check, line by line.                                   │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │ ● "The estimated treatment differences were −0.15 percentage points (95% │ │
│  │   ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾ │ │
│  │   CI −0.28 to −0.03), −0.39 percentage points (95% CI −0.51 to −0.26),   │ │
│  │   and −0.45 percentage points (95% CI −0.57 to −0.32), all favoring      │ │
│  │   tirzepatide."                                                            │ │
│  │                                                                            │ │
│  │       [→ Challenge this sentence]                                          │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
│           [ → Ask a question of your own ]                                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

On click, the same 6-beat reveal plays — the user sees the differentiator before they sign in.

---

## Interaction acceptance tests (plan §15)

Playwright traces (NOT just screenshots) verify:
1. **time-to-first-proof < 400ms** — from click to beat-2 verdict visible.
2. **claim-to-claim < 120ms** — `J`/`K` round-trip.
3. **full keyboard path** — Tab/Enter/Esc/J/K cycle without mouse.
4. **mobile tap path** — bottom-sheet appears, swipe-left advances, dismiss works.
5. **reduced-motion path** — instant state swap, no animation, full content visible.
6. **all six microstates** rendered on the FaithfulnessChip + CertaintyBadge + SourceCard + SignaturePill.

Per the plan §15 acceptance: traces are committed under `web/tests/e2e/proof_replay/` when the hero ships; this storyboard is the spec they verify against.
