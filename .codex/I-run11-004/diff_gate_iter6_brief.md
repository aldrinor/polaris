# Codex diff-gate — I-run11-004 — FOCUSED iter-6 (lethal fail-open confirmation)

HARD ITERATION CAP: 5 per document. This is iter 6 of 5 — INTENTIONALLY past the cap.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Why this is past the 5-cap (honest disclosure)

The 5-cap (CLAUDE.md §8.3.1) normally force-APPROVEs at iter 5. This document is the
EXCEPTION carved out by §-1.1 + §8.3.6: **a clinical-safety fail-OPEN in the faithfulness
verifier is the "lethal" case — fix it, do not force-approve.** Your iter-5 verdict named a
CONTINUING P1 fail-open in `parse_sentinel_decomposition` (a `{"verdict":"supported"}` output
with a non-numeric `unsupported_atoms` could be released as GROUNDED — i.e. a fabricated
clinical claim laundered to VERIFIED). That is not force-approvable. I fixed it. This focused
gate confirms ONLY that the specific fail-open is closed and that the fix introduced no new one.

## Scope of THIS gate (narrow on purpose)

Review ONLY `parse_sentinel_decomposition` in `src/polaris_graph/roles/sentinel_contract.py`
and its regressions in `tests/roles/test_sentinel_contract.py`. The rest of the diff
(adapter/transport/lock/pricing/seam/wiring) was reviewed and APPROVE-tracked iters 1–5; it is
unchanged since iter-5 except this one function + its tests.

## Your iter-5 finding (verbatim, the thing to confirm closed)

> Continuing iter-4 P1: `unsupported_atoms` present as JSON `true`, `false`, or `null` is treated
> like an absent count and can release `{"verdict":"supported"}` as GROUNDED. The bool branch sets
> `raw_count = None`, then skips the veto because the check is `if raw_count is not None`... This
> violates the claimed "present-but-non-coercible veto" and is a remaining fail-open path.
> Fix the `unsupported_atoms` presence check: distinguish missing from present invalid values, and
> veto any present value that is not clean numeric/string zero. Add regressions for `true`, `false`,
> and `null` under `verdict=="supported"`.

## The fix (root cause + change)

ROOT CAUSE: the gate keyed on the COERCED VALUE (`if raw_count is not None:`). A bool/null/list
coerces to `None`, which then took the SAME branch as an ABSENT key → veto skipped → fail-open.

FIX: key on KEY PRESENCE, not coerced value. `if "unsupported_atoms" in parsed:` enters the veto
block for ANY present value. Inside, the value coerces to `count`; a present value is released
ONLY if it coerces to a CLEAN ZERO (`count == 0`). `bool`, `null`, `list`, `dict`, and
non-coercible strings all coerce to `count = None`; the release condition `count is None or
count != 0` then vetoes to UNGROUNDED. ABSENT key (the only safe skip) bypasses the block entirely
and falls through to the per-atom list check + the top "supported" verdict.

## Current function — VERBATIM from committed HEAD (01465865)

```python
    if not isinstance(raw, str):
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    try:
        parsed = _strip_json(raw)
    except ValueError:
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    if not isinstance(parsed, dict):
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    verdict_token = parsed.get("verdict")
    if not isinstance(verdict_token, str):
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    verdict = _DECOMPOSITION_VERDICT_TO_VERDICT.get(verdict_token.strip().lower())
    if verdict is None:
        return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=False)
    if verdict is SentinelVerdict.GROUNDED:
        if "unsupported_atoms" in parsed:
            raw_count = parsed["unsupported_atoms"]
            count: float | None
            if isinstance(raw_count, bool):
                count = None  # a JSON bool is not a count -> present-but-invalid
            elif isinstance(raw_count, (int, float)):
                count = raw_count
            elif isinstance(raw_count, str):
                token = raw_count.strip()
                try:
                    count = int(token)
                except ValueError:
                    try:
                        count = float(token)
                    except ValueError:
                        count = None
            else:
                count = None  # null (None), list, dict, ... -> present-but-invalid
            if count is None or count != 0:
                return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=True)
        atoms = parsed.get("atoms")
        if isinstance(atoms, list):
            for atom in atoms:
                if not isinstance(atom, dict):
                    continue
                status = atom.get("status") or atom.get("verdict")
                if isinstance(status, str) and status.strip().lower() == "unsupported":
                    return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=True)
                if atom.get("supported") is False:
                    return SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=True)
    return SentinelResult(verdict, parsed_ok=True)
```

## Regressions added (the ones you asked for)

```python
def test_decomposition_non_numeric_unsupported_atoms_vetoes_to_ungrounded() -> None:
    for present_value in ("true", "false", "null", "[]", '["a"]', "{}"):
        payload = '{"verdict":"supported","unsupported_atoms":%s}' % present_value
        assert parse_sentinel_decomposition(payload) == \
            SentinelResult(SentinelVerdict.UNGROUNDED, parsed_ok=True), present_value
    # ABSENT key is the only path that may stay GROUNDED on a clean verdict.
    assert parse_sentinel_decomposition('{"verdict":"supported"}') == \
        SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)
    # PRESENT clean numeric zero stays GROUNDED.
    assert parse_sentinel_decomposition('{"verdict":"supported","unsupported_atoms":0}') == \
        SentinelResult(SentinelVerdict.GROUNDED, parsed_ok=True)
```
Plus the retained iter-4 quoted-count test: `"1"`/`"abc"`/`1.5` → UNGROUNDED, `"0"` → GROUNDED.
All 99 tests in `tests/roles/test_sentinel_contract.py` pass; full `tests/roles
tests/architecture tests/dr_benchmark` = 661 passed.

## The exhaustive truth table (please verify against the code above)

| `unsupported_atoms` value under `verdict:"supported"` | coerces to `count` | result |
|---|---|---|
| absent (key missing) | — (block skipped) | GROUNDED (falls to atoms/verdict) |
| `0` (int) | `0` | GROUNDED |
| `"0"` (str) | `0` | GROUNDED |
| `1`, `2`, `1.5` | `1`/`2`/`1.5` | UNGROUNDED |
| `"1"`, `"abc"` | `1` / `None` | UNGROUNDED |
| `true`, `false` (bool) | `None` | UNGROUNDED |
| `null` | `None` | UNGROUNDED |
| `[]`, `["a"]`, `{}` | `None` | UNGROUNDED |

## Ask

Confirm: (1) the bool/null/list/non-coercible fail-open is CLOSED; (2) the fix introduces no NEW
fail-open (e.g. is `bool` correctly excluded BEFORE `int|float`, given `isinstance(True, int)` is
True in Python?); (3) the ABSENT-key skip is safe because the downstream atoms check + the existing
section-level fail-closed (`_compose_final_verdict`) still hold. If clean, APPROVE.

## Output schema (required)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
