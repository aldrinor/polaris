# Codex Diff Review — I-f10-008 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f10-008 — F10 walkthrough: tirzepatide vs semaglutide
**Brief:** APPROVED iter 2 (port → 3000 + N=5 wording + clinical-question disclaimer P2 fixes applied in this diff)
**Canonical-diff-sha256:** `de10e135e1182f84348c71442e85f7f2a2d228c78387bea016920f8c86ae473f`
**LOC:** 208 net (CHARTER §1 LOC cap N/A — documentation only)

## Files

```
docs/walkthroughs/I-f10-008-tirzepatide-vs-semaglutide.md   NEW +208 (markdown walkthrough)
```

## What changed

Documentation-only deliverable. 208-line markdown walkthrough exercises the F10 substrate end-to-end. Sections:

1. **Purpose** — explicit honest-gap framing per LAW II.
2. **Setup** — port 3000 with `npm run dev` per Codex iter-1 P1 fix.
3. **Step 1 (Comparison table):** route + expected substrate behavior + auto-coverage references. N=5 corrected to "5 entities × 2 metrics = 10 entity-metric data rows" per Codex iter-2 P2.
4. **Step 2 (Click-through):** route + expected pane content (evidence_id + tier + URL + excerpt) + honest-gap on SOURCE_REGISTRY-vs-production-fetch.
5. **Step 3 (ChartProvenance contract):** schema + tests reference + run command.
6. **Step 4 (Sandboxed execution sovereignty):** I-f10-007 hardening + 35 sovereignty tests + I-f10-007b follow-up framing.
7. **What's NOT yet wired** — explicit gap section: live LLM auto-table; real evidence_id resolution; OS-level isolation.
8. **Cross-references** — every I-f10-001..007 PR linked with file paths + commit SHAs + claude_audit.md paths.

Per Codex iter-2 P2: walkthrough explicitly states "the clinical question itself is NOT answered by live evidence today" and clarifies the demo routes show housing-starts data and SELECT-trial data, not pharmaceutical efficacy.

## Verification

- Markdown renders cleanly in GitHub (verified by inspection).
- Routes referenced (`/charts_test/comparison_table`, `/charts_test/click_through`) exist on polaris HEAD (just-merged through I-f10-006).
- Test commands are verbatim runnable (Windows PowerShell + POSIX shell variants).
- All cross-referenced PR commits exist: `bad6d9e` (I-f10-001), `a3f1f50` (I-f10-002), `6fb1b37` (I-f10-003), `bbe8dbc` (I-f10-004), `599bbe0` (I-f10-005), `54fc31a` (I-f10-006), `617605e` (I-f10-007).

## Risks for Codex Red-Team

1. **Documentation-only:** no code paths altered. CHARTER §1 LOC cap is N/A — this is a markdown deliverable per the issue spec ("LOC estimate 0 (walkthrough)").
2. **Honest framing per LAW II:** "the clinical question itself is NOT answered by live evidence today" stated explicitly in the Purpose section.
3. **Port 3000 (not 3738):** verified against `web/package.json` line 6 (`"dev": "next dev"`).
4. **§9.4 N/A documentation.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
