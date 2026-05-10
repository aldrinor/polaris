## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

GH#365 I-bakeoff-A-001. Brief iter-1 force-APPROVE'd; both iter-1 P1 + P2 fixed:
- P1 (token-aware artifact): docstring + CLI now accept `--verified-sentences <jsonl>` (canonical pre-resolution input) OR `--report` (legacy/internal). Mutually exclusive. Output JSON unchanged.
- P2 (audit.md format): new `--output-md` flag + `_render_audit_md()` produces per-claim verdict table + summary stats + ACCEPT / REJECT / INVESTIGATE recommendation per Carney threshold (70% VERIFIED bar, REJECT on FABRICATED, INVESTIGATE on UNREACHABLE).

14 tests pass (11 existing + 3 audit.md format tests).

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
