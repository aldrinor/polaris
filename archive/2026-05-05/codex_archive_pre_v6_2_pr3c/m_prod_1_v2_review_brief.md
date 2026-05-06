# Codex round 2 — M-PROD-1 v2 (2 R1 P0 closed)

## Pre-flight
- Branch: `polaris`
- Commit: `caa946b`
- Brief format: lean autoloop V3

## R1 closures (both manually reproduced)

**R1 P0 #1 [rglob fallback false-positive]:**
- v1: `REPO_ROOT.glob()` empty → fell back to
  `REPO_ROOT.rglob(tail)` matching basename anywhere
- v2: dropped rglob fallback. Glob is bound to documented
  prefix strictly.
- Repro: rename `config/settings/` → audit now reports gap
  on `config/settings/*.yaml`

**R1 P0 #2 [regex misses real refs]:**
- v1 missed: `.env`, `.gitignore`, `tests/`, `<phase>`, `...`
  placeholder forms
- v2 regex: 3 alternatives (extension-anchored, repo-dir-anchored,
  dotfile-anchored). `_to_glob()` treats `<var>` and `...` as `*`.
- Repro: rename `tests/` → audit now reports gap on `tests/`

## v2 result
26/26 intact (vs v1's 21/21 — 5 more refs caught)

## Acceptance bar (unchanged from R1)
1. Audit script exits 0 when no gaps; 1 when gaps found
2. Path extraction captures all backtick-quoted refs
3. Glob support (no false-positive rglob fallback)
4. Dedup correctness
5. Evidence remediation correctness
6. Manifest output

## Severity rubric
- **P0** — production-breaker
- **P1** — phase-rework
- **P2** — governance precision (non-blocking)
- **P3** — polish (non-blocking)

**APPROVE iff zero P0 + zero P1.**

## Reviewer instructions
- Find ALL P0/P1 defects. If zero, write "no P0/P1 found"
  explicitly.
- Do NOT re-raise R1 findings. In-scope: regressions in v2 +
  P0/P1 missed in R1.
- Re-run Codex's two synthetic regressions:
  - rename `config/settings/` → expect gap detected
  - rename `tests/` → expect gap detected

## Skepticism gate
List which files you read + line ranges + which R1 closures
you verified.

## Anti-nits (do NOT flag)
- Prose grammar / docstring style
- R1 findings already addressed
- Suggestions for additional features beyond v1 scope

## Verdict format
```
## Files scanned
## R1 closure verification
## Acceptance bar verification
## Findings (NEW only)
## Verdict APPROVE | REQUEST_CHANGES
```

## Round metadata
Round 2 of 5 hard cap.
