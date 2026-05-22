# Codex BRIEF review — I-p2-003 (#742): design-system re-audit → white + Canada-red, evidence/state tokens

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
Re-audit + finalize the Frontier-Minimal design system (`web/app/globals.css`, merged at #730 with a BLUE accent) under the operator design lock + the 16-dim rubric. This is the foundation every page consumes.

## Acceptance criteria (the diff will implement; this brief reviews the PLAN)
1. **Accent → dark Canada-flag red on white** (operator lock): `--primary`/`--ring` = deep red, AA-safe on white (≥4.5:1 with white fg) — propose oklch(~0.52 0.20 25) ≈ #C8102E; `--accent` = light red tint; white `--background` confirmed.
2. **State colors SEPARATE from the national-accent red** (rubric color-token rule — "never rely on red alone"): the national red is reserved for primary action + proof-highlight. Distinct tokens for: `--verified` (success — a calm green, NOT red), `--contradiction` (amber), `--refusal` (neutral-strong), `--destructive` (must be visually distinguishable from the national red — e.g. a deeper maroon or paired with an icon, so "delete/error" ≠ "primary/proof"). Each AA on its surface.
3. **Evidence-role tokens:** `--tier-1` / `--tier-2` / `--tier-3` (near-mono weight + one tint), `--proof-token` (mono fg), `--verified-bundle`.
4. Type scale (12/14/16/20/24/32/48; report body 16/26 @ 68–75ch), motion tokens, dark-mode pairs (or explicitly defer dark mode with a logged note).
5. Keeps Geist + Geist Mono; hairline borders; max whitespace.

## Files I have ALSO checked and they're clean
- web/app/globals.css (current :root has blue --primary/--ring oklch(0.5 0.18 255) + red --destructive oklch(0.577 0.245 27) — the red-on-red collision risk #2 addresses).
- web/components/app_shell.tsx + web/app/components/home_keyboard_shell.tsx (sovereign mark — unaffected by tokens).

## Review focus
1. Is the Canada-red accent value AA-safe on white AND visually distinct from `--destructive`? Any collision the plan misses?
2. Are the state + evidence-role token additions complete per the rubric color rule (verified/contradiction/refusal/destructive/national all distinct + AA)?
3. Anything that would make the FOUNDATION non-top-tier or leak red-only signaling.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```

---
## iter-2 incorporations (all iter-1 P1 + P2 folded into the plan)
- **Canonical accent (P2):** `--primary`/`--ring` = **#C8102E** (the single canonical value; AA 5.88:1 on white) — drop the oklch≈#C21725 alt.
- **Focus ring (P1-1):** make the focus indicator OPAQUE (or ≥60% alpha) to clear the 3:1 bar — fix `globals.css:136` ring + `button.tsx:7` + `input.tsx:12` (`ring-ring/50`/`outline-ring/50` → opaque `ring`/`outline`).
- **Destructive ≠ national red (P1-2):** lock a concrete **deep maroon** `--destructive` clearly distinct from #C8102E (≥ a clear hue/lightness gap, not same-red-plus-icon); wire through destructive buttons + `aria-invalid` states.
- **@theme inline exports (P1-3):** every new state/evidence token gets a Tailwind `@theme inline` mapping (`--color-verified*`, `--color-contradiction*`, `--color-refusal*`, `--color-tier-1/2/3`, `--color-proof-token`, `--color-verified-bundle*`) — not naked `:root` vars.
- **Dark mode (P2):** neutralize the silent cyan `.dark` accent (it violates the Canada-red lock); set dark accent to the red OR explicitly defer dark mode with neutralized tokens + a logged note.
- **Follow-up (P2):** existing components hard-code emerald/amber/rose/blue (report, inspector, retrieval, contradiction, graph) — file a follow-up migration issue so the new tokens are actually consumed (this issue ships the FOUNDATION tokens; component migration is tracked separately).
Re-confirm APPROVE or list only true remaining P0/P1.
