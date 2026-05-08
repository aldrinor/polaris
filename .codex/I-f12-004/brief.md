# Codex Brief Review — I-f12-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f12-004 — F12 functional: jurisdictional diff. Same query different jurisdictions. Acceptance: show jurisdictional differences. LOC estimate 100.
- **Substrate today:** `compute_claim_diff` (I-f12-003) does pairwise claim diff. `Jurisdiction = Literal["canada", "us", "eu", "uk", ...]` lives in `src/polaris_graph/generator2/verified_report.py`. EvidenceContract does not currently carry a jurisdiction field — but `template` and per-section content can be tagged.
- **Honest framing per CLAUDE.md §9.4:** ship a deterministic aggregator that takes a mapping `{jurisdiction: EvidenceContract}` and produces a `JurisdictionalDiffReport` containing pairwise `ClaimDiffReport`s. The contracts are produced upstream as separate runs of the SAME question across different jurisdictions; the aggregator does NOT classify jurisdiction-source relationships, just surfaces the per-pair diffs labeled by jurisdiction.

## Plan

### `src/polaris_v6/compare/jurisdictional_diff.py` (NEW, ~50 LOC)

```python
from dataclasses import dataclass
from itertools import combinations

from polaris_v6.compare.claim_diff import ClaimDiffReport, compute_claim_diff
from polaris_v6.schemas.evidence_contract import EvidenceContract


@dataclass(frozen=True)
class JurisdictionalDiffPair:
    left_jurisdiction: str
    right_jurisdiction: str
    claim_diff: ClaimDiffReport


@dataclass(frozen=True)
class JurisdictionalDiffReport:
    question: str
    jurisdictions: list[str]
    pairs: list[JurisdictionalDiffPair]


def compute_jurisdictional_diff(
    contracts: dict[str, EvidenceContract],
) -> JurisdictionalDiffReport:
    """Pairwise claim_diff across jurisdictions sharing the same question.

    Raises ValueError if fewer than 2 jurisdictions or if questions diverge.
    """
    if len(contracts) < 2:
        raise ValueError("jurisdictional diff requires >= 2 contracts")
    questions = {c.question.strip() for c in contracts.values()}
    if len(questions) != 1:
        raise ValueError(
            "jurisdictional diff requires identical question across contracts; "
            f"got {len(questions)} distinct"
        )
    jurisdictions = sorted(contracts.keys())
    pairs: list[JurisdictionalDiffPair] = []
    for left, right in combinations(jurisdictions, 2):
        pairs.append(
            JurisdictionalDiffPair(
                left_jurisdiction=left,
                right_jurisdiction=right,
                claim_diff=compute_claim_diff(contracts[left], contracts[right]),
            )
        )
    return JurisdictionalDiffReport(
        question=next(iter(questions)),
        jurisdictions=jurisdictions,
        pairs=pairs,
    )
```

### Tests `tests/v6/compare/test_jurisdictional_diff.py` (NEW, ~50 LOC, 5 tests)

1. `test_two_jurisdictions_one_pair` — `{canada, us}` → `pairs` length 1.
2. `test_three_jurisdictions_three_pairs` — `{canada, us, eu}` → C(3,2)=3 pairs.
3. `test_pairs_sorted_alphabetically_by_jurisdiction` — pair order is canonical (sorted).
4. `test_question_mismatch_rejected` — different `question` strings raise `ValueError`.
5. `test_single_jurisdiction_rejected` — 1-entry input raises `ValueError`.

## Risks for Codex Red-Team

1. **Question normalization.** `c.question.strip()` for whitespace-insensitive equality. Anything beyond strip is post-MVP.
2. **Same-run-id is unlikely** for two different jurisdictions (different runs); compute_claim_diff already raises if collision happens.
3. **§9.4 hygiene.** Clean.
4. **CHARTER §3 LOC cap.** ~100 LOC net (50 src + 50 test). Well under 200.

## Acceptance criteria

1. New `src/polaris_v6/compare/jurisdictional_diff.py` with `JurisdictionalDiffPair`, `JurisdictionalDiffReport`, `compute_jurisdictional_diff`.
2. Pairwise compute via existing `compute_claim_diff`.
3. Question-mismatch + single-jurisdiction rejected via `ValueError`.
4. 5 tests pass.
5. CHARTER §3 LOC cap respected.

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
