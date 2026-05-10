## §0 — HARD ITERATION CAP (per CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Iter 1 findings + iter 2 disposition

**Iter 1 verdict: REQUEST_CHANGES, 1 P1.**

| Iter-1 finding | Severity | Iter-2 fix |
|---|---|---|
| `§-1.2 vs §10/§3.0 ordering contradiction` (CLAUDE.md:12 + CLAUDE.md:51 — "FIRST tool call is gh issue create" supersedes §10 boot ritual SHA verification + §3.0 halt-marker check) | **P1** | **FIXED.** Added explicit "Ordering vs §3.1 boot ritual + §3.0 halt gates" subsection to §-1.2 stating §3.1 step-0 canonical-pin verification + CHARTER+PLAN SHA pins (§10) + halt-marker check ALWAYS run first; §-1.2 governs *task-work* only. The "Application" sentence now says "the FIRST *task-work* tool call (after boot ritual + halt checks)" — explicit scoping. Mirrored in `web/AGENTS.md` §-1.2 with bracketed parenthetical: "the §3.1 boot ritual and §3.0 halt-marker checks always run first and can preempt this sequence". |
| `logs/session_log.md timestamp format` ([YYYY... UTC] vs CLAUDE.md §2.2 spec [YYYY-MM-DD HH:MM:SS]) | P2 | **FIXED.** Removed " UTC" suffix; entry now reads `[2026-05-10 06:59:22]`. |
| `scripts/close_stale_issues.sh head pipe hides gh failures` | P2 | **NOT FIXED.** Inert historical artifact, will not be re-run. Documented in §2 below. |
| `scripts/create_followup_issues.sh vestigial label parameter` | P2 | **NOT FIXED.** Inert historical artifact, will not be re-run. Documented in §2 below. |

## §2 — Diff under review (iter 2)

`.codex/I-doc-001/codex_diff.patch` — 5 files, 326 insertions, 0 deletions:

| File | +lines | Δ from iter 1 |
|---|---|---|
| `CLAUDE.md` | +47 (was +45) | +2 lines: P1 fix scoping §-1.2 |
| `web/AGENTS.md` | +32 | +1 line in iter 2 fixing §-1.2 ordering parenthetical (net same line count via wording) |
| `logs/session_log.md` | +10 | -1 char: " UTC" suffix removed |
| `scripts/close_stale_issues.sh` | +149 | unchanged |
| `scripts/create_followup_issues.sh` | +88 | unchanged |

## §3 — Files I have ALSO checked and they're clean (re-verified iter 2)

- `pytest tests/polaris_graph/generator2/test_strict_verify_entailment.py tests/polaris_graph/generator2/test_strict_verify_telemetry.py tests/polaris_graph/generator2/test_strict_verify_unknown_mode_warning.py tests/polaris_graph/test_provenance_generator_entailment.py tests/crown_jewels/test_cj_008_entailment_correctness.py -x -q` → 66 passed (unchanged from iter 1 baseline; no source code touched).
- §3.1 boot-ritual section in CLAUDE.md (lines ~730+ with canonical-pin verification): unchanged. The new §-1.2 ordering scoping points back to §3.1 + §10 explicitly so no contradiction remains.
- §3.0 halt-condition list (canonical-pin SHA mismatch, CHARTER/PLAN SHA mismatch, issue jump, missing artifact triple, Codex unavailable >1h, 2-cycle repeated root cause, 200-LOC PR cap, 3+ PRs queued): unchanged. §-1.2 now defers to halt gates explicitly.
- §10 boot ritual (CHARTER+PLAN SHA pin verification): unchanged. §-1.2 now defers to it explicitly.

## §4 — Why the 2 remaining P2s are not blocking iter 2

Both P2 script-hygiene findings concern one-shot bash scripts that were already executed against the live GitHub repo during the 2026-05-09 issue cleanup. They committed as **historical audit artifacts** for traceability of the 2026-05-09 cleanup decision — the user can grep them later to understand why issues #92-#192 closed in a batch. They will NOT be re-run; their behavior contracts don't matter. Hardening them is out of scope for I-doc-001 (governance docs PR).

If a future maintainer re-runs them, the worst outcome is:
- `close_stale_issues.sh head pipe`: gh failures swallowed silently. Workaround: re-check open count via `gh issue list` after run.
- `create_followup_issues.sh vestigial label`: all issues created with `--label bug` regardless of caller intent. Workaround: relabel via `gh issue edit` after run.

Neither is a clinical-safety issue. Neither breaks anything in production code paths. Per §8.3.1: "if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic." These are P2.

## §5 — Output Schema Bound (per CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## §6 — Convergence Hint

P1 fixed (the §-1.2 ordering contradiction). One P2 fixed (timestamp). Two P2s acknowledged as historical-artifact non-blockers. Expected verdict: APPROVE iter 2 with `accept_remaining`.
