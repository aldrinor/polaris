# M-51 Code Audit - V29 Strategy beta cycle 1, item 1

Commit audited: `0143deb` (`PL: M-51 - anchor-matched primary hard-reservation post-process (V29-a)`)

Verdict: **CONDITIONAL-no-blockers**

Claude can proceed to M-52. The selector-side custody mechanism is directionally correct and I found no blocker in the production path. One test fixture should be tightened because it is currently proving M-42e retention, not M-51 insertion/trim.

## Findings

### Non-blocking: trim fixture does not actually force M-51

`tests/polaris_graph/test_m51_selector_primary_custody.py::test_insertion_triggers_trim_to_max_rows` uses a T1 `SURPASS-4` primary. In the current selector, M-42e scans all T1 rows for configured anchors before T1 relevance fill, so that primary is already reserved by M-42e. Local reproduction of that fixture emits:

```text
m42e_primary_floor matched=1 reserved=1 cap=6 anchors=['SURPASS-4']
```

and no `m51_anchor_primary_custody` note. So the fixture verifies "reserved primary remains selected under max_rows", but not specifically "M-51 insertion caused overflow and M-51 trim protected the inserted row."

Recommended revision: make the fixture primary non-T1, e.g. T4, or otherwise outside M-42e's T1 floor, and assert:

- `m51_anchor_primary_custody` telemetry is present
- final length is exactly `max_rows`
- the M-51 primary survives
- one non-M-51 row was evicted

I verified the production path does fire M-51 with the same shape when the primary is T4: the selected IDs include `ev_s4` and telemetry includes `m51_anchor_primary_custody matched=1 inserted=1 cap=1`.

## Audit Answers

1. **Canonical identity**: main-branch helper correctly prefers non-empty string `evidence_id`, else falls back to `("key", url_lower, title_lower[:200], direct_quote[:200])`. The short-pool helper has the same fallback shape, but its computed `already_canon` is currently unused; this is dead code rather than a blocker because short-pool keeps all rows and uses M-51 only for priority class.

2. **Cap**: main branch correctly derives `m51_cap = min(len(unique_anchors), max_rows)`. Duplicate anchors are deduped before cap calculation.

3. **Trim order**: `(-tier_priority, +score, -idx)` is correct for "evict worst first" under the local tier convention where larger `_TIER_PRIORITY` means lower value. It evicts worse tier, then lower score, then later original index.

4. **Backward compatibility**: `primary_trial_anchors=None` or `[]` bypasses M-51 activity in both main and short-pool paths. Targeted tests pass and no M-51 telemetry is emitted.

5. **Short-pool path**: M-51 scans full `scored` for unique anchors not already caught by M-42e and promotes matches into priority class 0 through `m51_extra_ids`. This covers non-T1 primaries and short-pool M-42e misses.

6. **Trim protects reserved primaries**: production code protects rows whose tuple IDs are in `m51_inserted_ids` from eviction. The submitted fixture does not prove that invariant because M-42e, not M-51, catches the T1 primary; adjust the fixture as noted above.

## Verification

Ran:

```text
python -m pytest tests/polaris_graph/test_m51_selector_primary_custody.py -q
```

Result: `11 passed`. Pytest emitted a cache write warning for `.pytest_cache` permissions, unrelated to the selector behavior.
