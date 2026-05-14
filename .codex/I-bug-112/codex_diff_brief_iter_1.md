HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-bug-112 diff iter 1 — pin Dockerfile.v6 base to bookworm

Brief review AND diff review combined. Full brief at `.codex/I-bug-112/brief.md` in this diff.

## Summary

GH#492. P0 deploy blocker found during the G5 fallback-laptop drill:
`docker compose -f docker-compose.v6.yml build` fails with
`E: Package 'libgdk-pixbuf2.0-0' has no installation candidate` (exit 100).

Root cause: `Dockerfile.v6:10` was `FROM python:3.11-slim` (no Debian suite
pin). The tag floated bookworm→trixie; in trixie `libgdk-pixbuf2.0-0` was
renamed `libgdk-pixbuf-2.0-0`, so the apt block has no install candidate.

Fix: `FROM python:3.11-slim-bookworm` + a 4-line explanatory comment.
1-line functional change, 5 insertions / 1 deletion.

## Diff

`.codex/I-bug-112/codex_diff.patch` — 18 LOC (Dockerfile.v6 only),
canonical-diff-sha256 trailer included.

## Smoke test (done)

`docker compose -f docker-compose.v6.yml build api` with the pinned base:
the apt step that previously failed exit-100 now passes clean
(`grep -c 'no installation candidate|exit code: 100'` on the build log = 0);
build proceeds past apt into the pip-install phase.

## Adjacent files checked clean

- `web/Dockerfile` — `node:20-alpine`; alpine package names stable, not
  affected by the Debian float. Pinning node to a patch is separate hygiene.
- `Dockerfile` (legacy pipeline-B) — not in the v6 deploy path.
- `docker-compose.v6.yml` — references `Dockerfile.v6`; no change needed.
- All 8 apt packages in the block exist under the same names in bookworm —
  the failure was specifically + only the `libgdk-pixbuf2.0-0` trixie rename.

## Direct questions

1. Pin-to-bookworm vs migrate-to-trixie+rename — I chose the pin (1-line
   deterministic fix, demo 3 weeks out, bookworm still LTS). APPROVE?
2. `web/Dockerfile` node:20-alpine pin — scoped OUT as separate hygiene.
   Agree it's out of scope for this P0 fix?
3. Anything else blocking APPROVE?

## NOTE — separate finding, NOT this diff's scope

The same rebuild, AFTER the (now-fixed) apt step, shows pip backtracking
through `langchain-openai` 1.1.16→1.1.5 in `requirements-v6-pipeline-a.txt`
— a dependency-resolution slowness/possible-ResolutionImpossible in the pip
phase. That is a DIFFERENT subsystem from this base-pin bug. Do NOT flag it
against I-bug-112 — if it turns out to be a real blocker it gets its own
Issue. Mentioned here only for transparency.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
