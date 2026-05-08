# Claude architect audit — I-f12-004

Jurisdictional diff aggregator. compute_jurisdictional_diff takes
{jurisdiction: EvidenceContract}, validates question identity, and
fans out compute_claim_diff over pairwise combinations sorted
alphabetically by jurisdiction.

## What landed

- src/polaris_v6/compare/jurisdictional_diff.py (~53 LOC).
- tests/v6/compare/test_jurisdictional_diff.py (5 tests, all pass).

## Architectural alignment

- Plan F12: builds on I-f12-003 claim diff to surface jurisdiction-vs-jurisdiction differences for the same query.
- §9.4 hygiene clean. CHARTER §3 LOC: 124 net.

## Verdict

Ready to merge. Codex brief APPROVE iter 1; Codex diff APPROVE iter 1.
