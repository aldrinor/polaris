# Codex VISUAL audit — I-p2-043 (#833): Inspector centerpiece, A++/S bar

You have VISION. Audit the attached screenshots of the rebuilt POLARIS Inspector
(`/inspector/[runId]`), the public differentiator page. Grade against the **A++/S bar**:
visually competitive with AND differentiated from Perplexity / ChatGPT Deep Research /
Gemini. The operator's standard is explicit: "not half-ass, not B-. A++ to S."

HARD ITERATION CAP: 5. This is visual-gate iter 1. Front-load ALL real findings now; same
quality bar regardless of iteration; don't pick bone from egg (reserve P0/P1 for real
visual-quality blockers, classify polish as P2/P3).

## Attached images (in order)
1. `success_desktop.png` — populated success bundle, desktop 1280w. The intended hero:
   research question → proof-forward summary → slim trust chips → Proof Replay split-view.
2. `success_mobile.png` — same, 375w. Check the hero leads and metadata stays subordinate.
3. `success_manifest_open_desktop.png` — the "Full manifest" disclosure expanded (zero-loss
   audit IDs). Check it reads as subordinate, not competing with the hero.
4. `abort_desktop.png` — abort-shape bundle (no research question, 0 verified sections).

## What changed (this PR)
The page used to lead with two stacked audit-metadata cards (8-field bundle header + a
full two-family card) ABOVE the centerpiece. Now: research question is the `<h1>`; a
proof-forward summary line ("N verified sections · X% of claims verified · every sentence
traces to its cited source span"); the two-family invariant + signature are slim tokenized
chips; the full manifest is a collapsible disclosure. Proof Replay leads (default tab).

## Locked constraints (do NOT flag these as issues)
- Brand red `#c8102e` is OPERATOR-LOCKED. Do not propose a different brand color.
- Tokens: verified=green, contradiction=amber, destructive=maroon — fixed.
- The Proof Replay split-view INTERNALS (the claim list / source-span panel content) are
  OUT OF SCOPE this PR (separate component issue). Judge the PAGE FRAMING + the trust
  chips + hero + disclosure + how the centerpiece is *promoted*, not the panel internals.

## Audit it line-by-line, visually
For each screenshot, assess: visual hierarchy (does proof lead?), typographic scale/rhythm,
spacing systematics, color restraint, the trust chips' craft, the hero's authority,
mobile integrity, and whether THIS reads as S-tier research software vs. compliance tooling.
Give a letter grade per screenshot + the single highest-leverage change to reach S.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { success_desktop: "", success_mobile: "", manifest_open: "", abort: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff the page framing genuinely moves from "compliance-first" to "proof-leads" at a
defensible A-/A bar with zero P0/P1 visual blockers. If it's still B-tier, say REQUEST_CHANGES
with the specific fixes.
