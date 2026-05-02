# `bundle_export_sample.json` — what this file is

**Purpose:** A real EvidenceContract v1.0 audit bundle, sampled from the POLARIS golden-fixture suite, so your team can inspect the canonical artifact format without standing up the cluster.

**Source:** `tests/v6/fixtures/evidence_contract_v1/golden_run_clinical.json` (the `golden_clinical_001` fixture, used by all 9 Inspector Playwright e2e tests).

## What you see

The file is a single JSON object conforming to `polaris_v6.schemas.evidence_contract.EvidenceContract`:

| Top-level field | What it contains |
|---|---|
| `contract_version` | Always `"1.0"` for this generation. |
| `run_id` | Stable identifier — same `run_id` always produces the same bundle. |
| `template` | Which of 8 v6 templates was used (`clinical`, `housing`, `defense`, ...). |
| `question` | The user's research question. |
| `queued_at` / `finished_at` | ISO-8601 timestamps. |
| `pipeline_status` | One of: `success`, `abort_scope_rejected`, `abort_corpus_inadequate`, `abort_corpus_approval_denied`, `abort_no_verified_sections`, `error_*` (see CLAUDE.md §9.3). |
| `generator_model` / `verifier_model` | Family-segregated model pair. The `family_segregation_passed` flag is enforced at construction (see CLAUDE.md §9.1). |
| `cost_usd` | Hard ceiling enforced by `PG_MAX_COST_PER_RUN`. |
| `evidence_pool` | Array of every source span the generator was allowed to cite. Each has an `evidence_id`, source URL, tier (T1/T2/T3), char span. |
| `verified_sentences` | Every sentence the generator wrote that passed strict_verify. Each has a list of `[#ev:<evidence_id>:<start>-<end>]` provenance tokens. |
| `frame_coverage` | Which template frames were covered + by how many verified sentences. |
| `contradictions` | Array of detected contradictions between sources. Each has a resolution badge — one of `unresolved`, `claim_a_preferred`, `claim_b_preferred`, `noted_both` (canonical enum from `src/polaris_v6/schemas/evidence_contract.py` line 80). |

## How to verify the bundle independently

```bash
python -c "
from polaris_v6.schemas.evidence_contract import EvidenceContract
import json
contract = EvidenceContract.model_validate_json(open('docs/carney_handover/bundle_export_sample.json').read())
print(f'OK — contract_version={contract.contract_version} run_id={contract.run_id}')
print(f'  evidence_pool: {len(contract.evidence_pool)} items')
print(f'  verified_sentences: {len(contract.verified_sentences)} items')
print(f'  family_segregation_passed: {contract.family_segregation_passed}')
"
```

## How to inspect in the browser

If the cluster is up:
```
https://polaris.gc.ca/inspector/golden_clinical_001
```
Or locally:
```
cd C:/POLARIS && PYTHONPATH=src python -m uvicorn polaris_v6.api.app:app --port 8000
cd web && npx next start -p 3738
# then visit http://127.0.0.1:3738/inspector/golden_clinical_001
```

The Inspector renders the same fields shown above plus charts + click-to-evidence + frame-coverage panel.

## Schema versioning

The `contract_version` field MUST match a version supported by your runtime. Current: `1.0`. Backward-incompatible changes will bump to `2.0` with migration code; additive changes (new optional fields) keep `1.0`. See `src/polaris_v6/schemas/evidence_contract.py` for the canonical Pydantic source of truth.
