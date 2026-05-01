# Per-commit Codex brief — `9ccd286`

**Commit:** `9ccd286 PL: v6.2 Phase 5.3 — Carney handover bundle_export_sample.json + README`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (2):**
- `docs/carney_handover/bundle_export_sample.json` (new — copy of golden_run_clinical.json)
- `docs/carney_handover/bundle_export_sample_README.md` (new, ~50 lines)

## What this commit does

Closes a `one_pager.md` promise. The Carney handover one-pager said "three documents in this package" and listed `bundle_export_sample.json` as item 3 — but the file didn't exist on disk. This commit fixes the gap:

1. Copies `tests/v6/fixtures/evidence_contract_v1/golden_run_clinical.json` (the same fixture all 9 Inspector Playwright e2e tests load via the live backend) to `docs/carney_handover/bundle_export_sample.json`. So the sample is verifiably real — it's the same JSON that drives our test goldens.

2. Adds `bundle_export_sample_README.md` documenting:
   - Top-level field semantics (contract_version, family_segregation_passed, evidence_pool, verified_sentences, frame_coverage, contradictions).
   - How to validate the JSON independently with `EvidenceContract.model_validate_json(...)`.
   - How to inspect in the browser at `/inspector/golden_clinical_001`.
   - Schema versioning policy (additive = stay 1.0; breaking = 2.0 with migration).

Verified locally:
```
$ PYTHONPATH=src python -c "from polaris_v6.schemas.evidence_contract import EvidenceContract; ..."
OK contract_version=1.0 run_id=golden_clinical_001
  evidence_pool: 2
  verified_sentences: 1
  family_segregation_passed: True
```

## Acceptance criteria

1. **The sample bundle validates against the canonical Pydantic schema** at `src/polaris_v6/schemas/evidence_contract.py` — confirmed by the commit message's verification snippet.
2. **README references the right module path** — `polaris_v6.schemas.evidence_contract` (NOT `evidence_contract_v1`); fixed during commit prep when the first attempt failed with ModuleNotFoundError.
3. **Bundle is the SAME fixture our e2e tests use** — not a hand-crafted cousin. Carney's team can render it in their browser by visiting `/inspector/golden_clinical_001` and see exactly what's inside the JSON.
4. **No PII / CAN_REAL data leaked.** golden_clinical_001 is a synthetic fixture about ozempic CV outcomes — public-tier sources only, no patient data.
5. **Schema versioning policy explicitly documented** so the next maintainer doesn't accidentally bump 1.0 for additive changes.

## Codex focus

- **P1:** The sample is a `success`-status bundle with only 1 verified_sentence and 2 evidence_pool items. Should we provide a SECOND sample showing an `abort_no_verified_sections` path (use `golden_run_abort_no_verified.json`) so Carney's team sees both outcomes?
- **P2:** README claims the current `contract_version` is `1.0`. Verify by reading `src/polaris_v6/schemas/evidence_contract.py` — does the Pydantic field have a default of `"1.0"`, and is there a CHANGELOG-style record anywhere of when 1.0 was frozen?
- **P3:** Should the README include a tiny shell command to compute SHA-256 of the bundle so handover recipients can verify integrity? Trivial to add: `sha256sum docs/carney_handover/bundle_export_sample.json`.

## Cross-review

Lands at `outputs/audits/continuous/9ccd286/cross_review.md`. **NOTE**: this commit starts the NEXT 5-commit batch under A+C K=5 (the previous batch's adversarial-reviewer subagent is currently running on commits dae2a9f → 4fe03f7). Counter: **1/5 (new batch)**.
