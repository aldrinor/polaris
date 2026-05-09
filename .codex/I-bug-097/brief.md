# Codex Brief — I-bug-097 (log warning once on unknown PG_STRICT_VERIFY_ENTAILMENT)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- DO NOT call exec / rg / shell tools. Brief is self-contained.
```

## Context

Captured as Codex P2 advisory in `.codex/I-bug-092/codex_diff_audit.txt` iter 1:

> "Unknown PG_STRICT_VERIFY_ENTAILMENT values silently map to off. This is intentional and tested, but a typo can disable the gate; consider logging a warning once."

Real failure mode: operator types `PG_STRICT_VERIFY_ENTAILMENT=ENFORCE` (uppercase ✓ already lowercased) or `PG_STRICT_VERIFY_ENTAILMENT=enforced` (verb form, not in {off,warn,enforce}) — `_entailment_mode()` falls back to `"off"` and the gate silently runs without entailment checking. The operator believes the gate is enforcing; it isn't.

## Proposed change

In `src/polaris_graph/generator2/strict_verify.py:_entailment_mode()`:

Current behavior:
```python
def _entailment_mode() -> str:
    raw = os.environ.get("PG_STRICT_VERIFY_ENTAILMENT", "off").lower().strip()
    if raw not in ("off", "warn", "enforce"):
        return "off"
    return raw
```

Proposed:
```python
_UNKNOWN_MODE_WARNED: set[str] = set()

def _entailment_mode() -> str:
    raw = os.environ.get("PG_STRICT_VERIFY_ENTAILMENT", "off").lower().strip()
    if raw and raw not in ("off", "warn", "enforce"):
        if raw not in _UNKNOWN_MODE_WARNED:
            _UNKNOWN_MODE_WARNED.add(raw)
            logger.warning(
                "PG_STRICT_VERIFY_ENTAILMENT=%r unrecognized; "
                "treating as 'off'. Valid: off, warn, enforce.",
                raw,
            )
        return "off"
    return raw or "off"
```

Behavior:
- Empty / unset → `"off"` silently (no spam at module-import time when env is just default)
- Recognized value → return it
- Unrecognized value → log WARNING **once per process per typo string**, fall back to `"off"`

The "once per process per typo string" dedup avoids flooding logs when `_entailment_mode()` is called per-sentence in a long-running process.

## Test surface

- `test_unknown_mode_emits_warning_once_per_process` — set `PG_STRICT_VERIFY_ENTAILMENT=enforced`, call `_entailment_mode()` 3 times, assert exactly 1 WARNING in caplog.records
- `test_unknown_mode_warning_includes_value` — assert the WARNING message contains the typo string `'enforced'` so the operator can see what they typed
- `test_unknown_mode_different_typos_each_warn_once` — set `=enfoce` then `=warning`, assert 2 distinct warnings (different cache keys)
- `test_known_modes_emit_no_warning` — off/warn/enforce/empty/unset → zero WARNING records
- Reset `_UNKNOWN_MODE_WARNED` between tests via monkeypatch + module-level

## What I want from you

1. **Verdict** APPROVE / REQUEST_CHANGES.
2. **Sanity-check the dedup approach**: process-lifetime set vs reset-per-call. Process-lifetime is what I propose (avoids log flood). Alternative: lru_cache. I lean process-lifetime set because it's explicit + easy to reset in tests.
3. **LOC estimate**: ~12 src/ LOC + ~40 test LOC. Way under 200-LOC cap.
4. **Failure-mode coverage** — anything I'm missing?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
test_surface_complete: yes | no
loc_estimate_ok: yes | no
dedup_approach: process_set | lru_cache | other
extra_failure_modes: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
rationale: <2-3 sentences>
```
