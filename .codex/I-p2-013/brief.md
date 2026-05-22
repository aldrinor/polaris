# Codex BRIEF+DIFF review — I-p2-013 (#752): rebuild home (frontier-grade)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
Rebuild the home page to frontier-DR grade. The operator flagged the live home by URL as "still ugly old UI" — the OLD home was a hero + an 8-card "Coming Soon" templates grid. #752 REPLACES that grid.

## Claude's VISUAL audit (I rendered via the production standalone harness + viewed the home screenshot @1366; Codex can't view PNGs — audit the DIFF + cross-check):
- White bg; big confident headline "Deep research you can check, line by line." (renders serif in the standalone because Geist isn't loaded there; Geist Sans on the live site — known harness artifact, NOT a defect).
- ONE primary CTA: the ask form + Canada-red "Verify" button. No competing CTAs.
- Three differentiator pillars (Provable / Sovereign / Snowball) with red icons + honest copy (3-13% hallucination stat; "no external AI vendor"; snowball graph). Replaces the 8-card grid.
- The "Coming Soon templates grid" the operator hated is GONE.
- RecentRunsStrip returns null when there are no runs → generous whitespace below pillars (intentional Frontier-Minimal; populates with real runs on the live VM). Footer present.

## Diff (app/page.tsx)
- Removed the templates GRID rendering + Card imports; kept the templates const (CommandPalette still consumes it).
- New hero (one CTA), PILLARS const + 3-up section, RecentRunsStrip, footer. max-w-4xl, gap-20, py-24.

## Review focus (rubric: visual/user-focus/honesty/a11y + code)
1. HONESTY: no fabricated "sample verified brief"/fake claims on the homepage? Copy honest (no "guaranteed true")?
2. One-CTA discipline (single primary action)? Grid actually removed (no dead Card imports / unused vars)?
3. a11y: form label, headings hierarchy (h1 + section h2s), pillar icons aria-hidden, AA?
4. Any P0/P1. (templates const retained intentionally for CommandPalette — not dead.)

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
