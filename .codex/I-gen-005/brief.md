# I-gen-005 Step 3b umbrella PR #906 iter 5 (FINAL — cap) — [N] preserved

## §8.3.1 cap

```
HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE per §8.3.1.
- Verdict APPROVE iff zero NOVEL P0/P1.
```

**ITER 5 — the cap. After this verdict, force-APPROVE if REQUEST_CHANGES.**

## Iter 4 verdict → iter 5 response

REQUEST_CHANGES with novel P1 — my iter-3 `(?:\[\d+\])?` was inside a `re.split` delimiter, so [N] markers were consumed/dropped. Strict mode would silently drop bibliography citations.

### Iter-5 fix (commit `8bada6ae`)

Replaced `re.split` with `finditer`-based slicing:

```python
_SENTENCE_BOUNDARY_RE = re.compile(
    r"[.;!?](?:\[\d+\])?(?=\s+(?:[A-Z\[]|$))"
)

def split_sentences(text):
    # ... sentinel-protect decimals ...
    pieces = []
    last_end = 0
    for m in _SENTENCE_BOUNDARY_RE.finditer(protected):
        end_pos = m.end()  # AFTER the [N] marker
        pieces.append(protected[last_end:end_pos])  # marker IN this piece
        while end_pos < n and protected[end_pos].isspace():
            end_pos += 1  # consume whitespace delimiter
        last_end = end_pos
    if last_end < n:
        pieces.append(protected[last_end:])
    return [p.replace(sentinel, ".").strip() for p in pieces if p.strip()]
```

`finditer` returns the boundary match. We slice protected[last_end:m.end()] which INCLUDES the optional [N] in the preceding sentence. Only the trailing whitespace is consumed by the manual advance loop.

Live probe (5/5 cases, EXACT contents):
- `A.[1] B.[2]` → `['A.[1]', 'B.[2]']` ✓
- `Tirzepatide ... (atom_003).[1] Semaglutide ... -1.86.[2]` → `['Tirzepatide ... (atom_003).[1]', 'Semaglutide ... -1.86.[2]']` ✓
- `Single sentence.` → `['Single sentence.']` ✓
- `Two sentences. Second.` → `['Two sentences.', 'Second.']` ✓
- `HbA1c was -2.30. AE rate was 43%.` → `['HbA1c was -2.30.', 'AE rate was 43%.']` ✓

Tests: 99/99 pass. iter-3 regression test tightened per Codex iter-4 advice — asserts exact split contents (not just count), so any future regression that drops the [N] marker is caught.

## Updated canonical diff hash (HEAD `8bada6ae`)

SHA256: `8fbbecf9409238bf2de2adfbe4cf6221bae9fb42c6885ede305d6cbf893b5768`

## Force-APPROVE acknowledgment per §8.3.1

If REQUEST_CHANGES: force-APPROVE per §8.3.1 cap + capture residual concerns as follow-up Issues. The CI gate parses the LAST `verdict:` line of codex_diff_audit.txt — I'll append `verdict: APPROVE` with the cap-hit marker if needed.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

p1_iter4_marker_preserved_in_preceding_sentence: YES | NO

novel_p0: [...]
novel_p1: [...]
continuing_p0: [...]
continuing_p1: [...]
p2: [...]

approval_to_merge: YES | NO
convergence_call: continue | accept_remaining
```

EMIT YAML ONLY.
