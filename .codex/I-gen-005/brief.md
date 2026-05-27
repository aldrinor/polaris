# I-gen-005 Step 3j iter 4 — symmetry fix on branch (a)

## §8.3.1 cap

```
HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
```

## Iter 3 verdict → iter 4 response

REQUEST_CHANGES with 1 novel P1:

> "Branch (a) covers 'primary/secondary endpoint of ... was NUMBER' but not the parallel 'primary/secondary outcome of ... was NUMBER', even though `_TRIAL_DESIGN_FRAME_RE` treats primary/secondary outcome phrases as trial-design markers."

Repro: "The primary outcome of change from baseline was -2.30."
- `_TRIAL_DESIGN_FRAME_RE` matches "primary outcome of" → marker fires
- iter-3 branch (a) requires "primary endpoint of" — NO match
- No outcome verb, no timepoint
- Would FALSELY pass exemption

## Fix

Branch (a): `(?:end\s?point|outcome)`:

```python
# Branch (a) UPDATED: covers both endpoint-of and outcome-of attribution
r"(?:primary|secondary)\s+(?:end\s?point|outcome)\s+of"
r"[^.]{1,80}?(?:was|were|is|are|=)\s*[-−]?\d|"
```

## Full iter-4 `_ENDPOINT_RESULT_ATTRIBUTION_RE`

```python
_ENDPOINT_RESULT_ATTRIBUTION_RE = re.compile(
    r"\b("
    # (a) "primary/secondary endpoint/outcome of <anything> was/were/is/are/= NUMBER"
    r"(?:primary|secondary)\s+(?:end\s?point|outcome)\s+of"
    r"[^.]{1,80}?(?:was|were|is|are|=)\s*[-−]?\d|"
    # (b) "at <timepoint> was/were/is/are/= NUMBER"
    r"at\s+(?:" + _TIMEPOINT_ALT + r")\s+(?:was|were|is|are|=)\s*[-−]?\d|"
    # (c) "<endpoint name> [at <timepoint>] was/= NUMBER"
    r"\b(?:" + _ENDPOINT_NAMES_ALT + r")"
    r"(?:\s+at\s+(?:" + _TIMEPOINT_ALT + r"))?"
    r"\s+(?:was|were|is|are|=)\s*[-−]?\d|"
    # (d) REVERSE-ORDER: "change/reduction/level/rate ... was NUMBER ... at <timepoint>"
    r"\b(?:change|reduction|level|rate|incidence|frequency)\b"
    r"[^.]{1,80}?(?:was|were|is|are|=)\s*[-−]?\d"
    r"[^.]{1,80}?at\s+(?:" + _TIMEPOINT_ALT + r")|"
    # (e) PASSIVE/INCIDENCE: passive-reported / occurred-in / achieved
    r"\b(?:" + _ENDPOINT_NAMES_ALT + r")\s+(?:was|were)\s+(?:reported|observed|recorded)\s+in\s+\d|"
    r"\b(?:" + _ENDPOINT_NAMES_ALT + r")\s+occurred\s+in\s+\d|"
    r"\d+\s*%?\s+achieved\s+(?:" + _ENDPOINT_NAMES_ALT + r")"
    r")",
    re.IGNORECASE,
)
```

## Verification — Codex iter-3 repro

| Sentence | Marker? | Branch (a) match? | Verdict |
|---|---|---|---|
| "The primary outcome of change from baseline was -2.30" | YES (primary outcome of) | **YES** (a, both endpoint/outcome) | **REFUSE** ✓ |
| "The primary endpoint of change from baseline was -2.30" | YES | **YES** (a) | **REFUSE** ✓ |
| s009 full sentence (no "was/=" attribution) | YES | NO (a) | **ALLOW** ✓ |
| All previous iter-3 verifications | unchanged | unchanged | unchanged ✓ |

## P2 acknowledged (not addressed in iter-4)

iter-3 P2: "Branch (b) `at <timepoint> was NUMBER` is broad as an independent trigger; acceptable if intentionally conservative." — Intentionally conservative. In clinical-safety context, a sentence asserting `at <timepoint> was NUMBER` without atom citation is more dangerous to allow than to over-refuse. Per §-1.1 "false-positive lethal, false-negative recoverable."

## Output

```yaml
verdict: APPROVE_DESIGN | REQUEST_CHANGES

iter3_p1_addressed: YES | NO

all_4_iter2_p1s_still_addressed: YES | NO

baseline_parenthetical_still_preserved: YES | NO

step3b_iter3_repro_still_refused: YES | NO

novel_p0: []
novel_p1: []
p2: []

ready_to_implement: YES | NO
```

EMIT YAML ONLY.
