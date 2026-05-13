HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-003 diff iter 2 — P1-004 in-container path

## P1-004 (resolved)

`/etc/polaris/egress_allowlist.txt` only exists on the EC2 host (cloud-init copies it). The api container has `/app/config/` baked in by Dockerfile.v6's `COPY config/ config/`. The transparency endpoint default was pointing at the host-only path, so `/transparency` would have returned `['unrestricted (no lockdown applied)']` in production.

### Fix

`src/polaris_v6/api/transparency.py:30-36` — `DEFAULT_EGRESS_ALLOWLIST = "/app/config/egress_allowlist.txt"`. The container can now read the 17-domain allowlist without operator bind-mount. `egress_lockdown.sh` still reads from `/etc/polaris/egress_allowlist.txt` on the host (which cloud-init populates) so the operator path is unchanged.

Added new test `test_transparency_egress_allowlist_default_path_is_in_container` (without env-override monkeypatch) that asserts `DEFAULT_EGRESS_ALLOWLIST.startswith("/app/")`. Catches future regressions to host-only paths.

## P2 (resolved) — log location overpromise

`docs/transparency.md:55` previously said off-allowlist drops are logged to `/var/log/polaris-egress.log`. That file only holds the script's own install events; iptables LOG drops go to kernel facility (typically `journalctl -k`). Documented correctly now with explicit `[POLARIS-EGRESS-DROP]` prefix + journalctl filter.

## P3 (resolved) — unused import

`src/polaris_v6/api/transparency.py:21` — removed unused `from typing import Any`.

## Test results

```
$ python -m pytest tests/polaris_v6/api/test_transparency.py
6 passed in 1.76s
```

## Direct questions iter 2

1. `DEFAULT_EGRESS_ALLOWLIST = "/app/config/egress_allowlist.txt"` (container-baked path) — APPROVE'd?
2. New regression test for path-shape — APPROVE'd?
3. transparency.md log-location correction — APPROVE'd?
4. Anything else blocking iter-2 APPROVE?

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
