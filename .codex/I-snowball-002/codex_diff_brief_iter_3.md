HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-002 — DIFF REVIEW iter 3

Iter 2 P1 fix applied. Commit `600b0168` on top of `c700cc05` on top of `a8d66d20`. Branch `bot/I-snowball-002-graph-endpoint`.

## What changed since iter 2

`test_graph_route_mounted_in_create_app` now calls:
```python
monkeypatch.setenv("POLARIS_GPG_KEY_ID", "")
monkeypatch.setenv("SERPER_API_KEY", "")
monkeypatch.setenv("OPENROUTER_API_KEY", "")
monkeypatch.setenv("POLARIS_BENCHMARK_RESULTS_DIR", "")
```
BEFORE `from polaris_v6.api.app import create_app`. Per iter-2 Codex finding: empty-string setenv (not delenv) needed because the app code checks `os.environ.get("X","").strip()` and an unset var defaults to empty already — but if `.env` rehydrates, only setenv-empty fully shields. 9/9 still pass.

Per iter-2 verdict: P1 fix correct on lazy-import (confirmed working); only remaining P1 was the mount test hermeticity (now fixed); P2 LOC-overage non-blocker.

## Canonical V30 reproduction (Codex iter 2 confirmed directly)

```
SWEEP_clinical_clinical_tirzepatide_t2dm_1777170058
  nodes: 213, edges: 700, hash: 67aaf82314a4
  diagnostics: bibliography_count=26, fallback_source_count=97,
               missing_reference_occurrence_count=98
```

This matches the iter-4 brief expected counts exactly (26/97/98). The route returns 200 OK on the canonical run.

## Direct questions for Codex iter 3

1. Is the mount-test fix sufficient to close iter-2 P1, or do you want additional isolation (e.g. importlib.reload, sys.modules cleanup)?
2. Any genuinely blocking issue remaining? Per the cap rule, iter 3-5 are the convergence shots.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
