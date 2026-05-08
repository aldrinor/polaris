# Codex Brief Review — I-f12-003 (ITER 3 of 5)

## Iter 3 changes per Codex iter 2

- **P1 (LOC trim):** target ~85 src + ~85 test = ~170 net (under 200). Cut redundant test verbosity by parametrizing the matrix tests in iter-3 plan.
- **P1 (drop_reason filter):** `_shipped(s)` helper filters sentences where `drop_reason is None AND verifier_local_pass AND verifier_global_pass`. Only shipped sentences enter the pairing logic. Added `test_dropped_sentences_excluded_from_pairing` (8 tests total).
- **P2 (mid-overlap parametrized):** `test_partial_mid_overlap` now uses `pytest.mark.parametrize` for `(shared_evidence, expected_verdict)` covering both shared-evidence and disjoint-evidence cells.
- **P2 (same-run guard):** `compute_claim_diff` raises `ValueError` if `left.run_id == right.run_id` (mirrors `compare_reports`).

## Iter 2 changes per Codex iter 1

- **P1 (complete classification matrix):** Replaced 3-threshold spec with a 2-axis matrix on text-overlap × evidence-overlap. Two thresholds suffice: `AGREEMENT_TOKEN_OVERLAP=0.7`, `PARTIAL_TOKEN_OVERLAP=0.3`. Matrix:

  | text overlap | shared evidence ≥ 1 | shared evidence = 0 |
  |---|---|---|
  | ≥ 0.7 | `agreement` | `partial` |
  | 0.3–0.7 | `partial` | `partial` |
  | < 0.3 | `partial` | `disagreement` |

  Removed reference to undefined `DISAGREEMENT_THRESHOLD`. Every paired claim is classified; only_left/only_right cover unpaired.

- **P2 (provenance parser scope):** parser extracts `<evidence_id>` from the `[#ev:<id>:<start>-<end>]` token format regardless of `ev_` prefix. Regex: `\[#ev:([^:\]]+):\d+-\d+\]`.

- **P2 (low-overlap/shared-evidence fixture):** added `test_partial_low_text_overlap_shared_evidence` (verdict `partial`, NOT disagreement, when text overlap < 0.3 but evidence-id is shared). Total tests: 7.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f12-003 — Claim-level diff algorithm. Acceptance: diff sample fixtures. LOC estimate 200.
- **Substrate today:** `src/polaris_v6/compare/differ.py` ships pool/frame diff. No claim-level diff.

## Plan

### `src/polaris_v6/compare/claim_diff.py` (NEW, ~110 LOC)

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Literal

from polaris_v6.schemas.evidence_contract import EvidenceContract, VerifiedSentence

ClaimVerdict = Literal["agreement", "partial", "disagreement", "only_left", "only_right"]

AGREEMENT_TOKEN_OVERLAP = 0.7
PARTIAL_TOKEN_OVERLAP = 0.3
_PROV_RE = re.compile(r"\[#ev:([^:\]]+):\d+-\d+\]")
_WORD_RE = re.compile(r"[a-z0-9]+")

@dataclass(frozen=True)
class ClaimDiffEntry:
    section_id: str
    verdict: ClaimVerdict
    left_sentence: str | None
    right_sentence: str | None
    shared_evidence_ids: list[str]
    only_left_evidence_ids: list[str]
    only_right_evidence_ids: list[str]
    text_overlap_ratio: float

@dataclass(frozen=True)
class ClaimDiffReport:
    left_run_id: str
    right_run_id: str
    entries: list[ClaimDiffEntry]
    counts_by_verdict: dict[ClaimVerdict, int]


def _evidence_ids(s: VerifiedSentence) -> set[str]:
    return {m for tok in s.provenance_tokens for m in _PROV_RE.findall(tok)}

def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))

def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)

def _classify_paired(
    text_overlap: float, shared_evidence_count: int
) -> ClaimVerdict:
    if shared_evidence_count >= 1 and text_overlap >= AGREEMENT_TOKEN_OVERLAP:
        return "agreement"
    if shared_evidence_count == 0 and text_overlap < PARTIAL_TOKEN_OVERLAP:
        return "disagreement"
    return "partial"

def compute_claim_diff(left: EvidenceContract, right: EvidenceContract) -> ClaimDiffReport:
    # group by section_id
    # for each section in left ∩ right: best-jaccard pair every left sentence;
    # consume matched right sentences; remaining go to only_left / only_right
    # sections only-on-left → all sentences only_left; symmetric for only-on-right
    ...
```

### Tests `tests/v6/compare/test_claim_diff.py` (NEW, ~85 LOC, 8 tests)

1. `test_agreement_same_text_shared_evidence` — overlap≥0.7 + shared → `agreement`.
2. `test_partial_high_overlap_disjoint_evidence` — overlap≥0.7 + disjoint → `partial`.
3. `test_partial_mid_overlap` (parametrized 2x: shared, disjoint) — overlap in [0.3, 0.7) → `partial`.
4. `test_partial_low_text_overlap_shared_evidence` — overlap<0.3 + shared → `partial` (not disagreement).
5. `test_disagreement_low_overlap_disjoint_evidence` — overlap<0.3 + disjoint → `disagreement`.
6. `test_only_left_section_missing_right` — left S2, no right S2 → `only_left`.
7. `test_counts_by_verdict_correctly_aggregated` — multi-section; counts match.
8. `test_dropped_sentences_excluded_from_pairing` — sentence with drop_reason set is filtered before pairing; doesn't appear in entries.

## Risks for Codex Red-Team

1. **Threshold rationale.** 0.7 / 0.3 documented as MVP heuristic per CLAUDE.md §9.4 honest framing.
2. **Best-pair greedy:** within a section, pair each left sentence with the highest-Jaccard right sentence; then consume that right sentence so it can't pair twice. Non-optimal but deterministic.
3. **§9.4 hygiene.** Named module constants, no magic numbers, no `try/except: pass`, no `time.sleep`, no TODO.
4. **CHARTER §3 LOC cap.** ~170 LOC net (85 src + 85 test). Under 200.

## Acceptance criteria

1. New `src/polaris_v6/compare/claim_diff.py` with `ClaimVerdict`, `ClaimDiffEntry`, `ClaimDiffReport`, `compute_claim_diff`.
2. Token-Jaccard text overlap + provenance-id parsing (any id format) implemented.
3. Complete classification matrix (every paired claim classified; no undefined branch).
4. 7 tests pass (covering every cell of the 3×2 matrix + only_left/right + counts).
5. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-5.
**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
