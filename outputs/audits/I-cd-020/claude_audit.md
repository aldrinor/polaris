# Claude audit — I-cd-020 (#630)

## Scope verified

Per Codex scope consult 2026-05-20 (highest-quality-impact ranking D > C > A > B), Option D is the only path that avoids fabricating audit-critical provenance fields. Pipeline-A's `evidence_pool.json` lacks span char-offsets and `verification_details.json` lacks per-sentence sentence_text/provenance_tokens. Synthesizing those would violate LAW II + CLAUDE.md §-1.1.

## What landed

- `src/polaris_v6/api/bundle.py:55-92` — disambiguated 404 for real completed runs (enriched detail pointing to /bundle.tar.gz + #680) vs unknown UUIDs (original generic 404).
- `tests/v6/test_api_bundle.py` — 2 new tests + auth_disabled + db_path fixtures; 6/6 passed.
- `docs/runbook.md` — "Run bundle export — two endpoints" subsection.
- New Issue #680 (I-cd-020-followup) carved for the pipeline-A capability extension.

## Acceptance — interpreted correctly

Parent #544 acceptance: "real run → signed bundle conforming to I-A-02b schema → renders in /inspector/[runId]". The I-A-02b frozen schema is **BundleManifest v1.0** (I-cd-012), not `EvidenceContract`. The existing `GET /runs/{run_id}/bundle.tar.gz` (I-arch-001d) serves real-run bundles conforming to BundleManifest v1.0. Inspector frontend wiring (Seq 21 / #631) is the consumer.

## Quality bar

- Codex brief APPROVE iter 2 (after Option D rescope from initial Option A).
- Codex diff APPROVE iter 1.
- 6/6 tests pass.
- 128 LOC canonical diff — well under 200-LOC halt.
- Zero data fabrication.

## Files I have checked clean

`.codex/I-cd-020/brief.md` §D + diff_brief.md §C list all adjacent files verified clean. Follow-up Issue #680 captures the pipeline-A capability extension.
