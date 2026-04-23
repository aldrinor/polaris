# Codex M-61 audit — pass 2

**Verdict**: APPROVED

## Blocker 1 — DOI omission bypass
Verified. `validate_against_tasks()` in `src/polaris_graph/retrieval/human_gap_completion.py:409` now enforces the full three-way match:
- task DOI present + completion DOI `None` rejects
- task DOI `None` + completion DOI present rejects
- both `None` accepts

The targeted tests exist at `tests/polaris_graph/test_m61_human_completion.py:370` and `:388`, and the both-`None` acceptance case is covered at `:422`.

## Blocker 2 — HUMAN_CURATED marker permanent
Verified. `FrameRow.provenance_class` now carries `ProvenanceClass.HUMAN_CURATED` from `to_frame_rows()` (`human_gap_completion.py:510`), and the enum value is declared durably in `src/polaris_graph/retrieval/frame_fetcher.py:78-102`.

Downstream consumers continue to preserve the enum/string value rather than collapsing it to `abstract_only`. In particular, `slot_validator.py:262-265` treats only `"frame_gap_unrecoverable"` as a gap, so HUMAN_CURATED remains a non-gap payload class.

## Blocker 3 — Structured provenance survives boundary
Verified. `StructuredProvenance.to_dict()` (`human_gap_completion.py:138`) serializes all 8 required fields and conditionally includes `other_justification`. The dict is threaded through:
- `to_frame_rows()` → `FrameRow.human_curated_provenance` (`frame_fetcher.py:184`)
- `compose_frame_coverage()` → `SlotCoverageEntry.human_curated_provenance` (`frame_manifest.py:103`, `:291`)
- `FrameCoverageReport.to_manifest_dict()` via `asdict()` (`frame_manifest.py:126`)

Manual round-trip probe through `asdict()` + `json.dumps()`/`json.loads()` preserved all keys, including optional `other_justification`.

## Medium 1 — Schema closed
Verified. Completion parsing rejects unknown top-level keys via `_ALLOWED_COMPLETION_KEYS` (`human_gap_completion.py:190,221`) and names legacy `consent_proof` explicitly in the error. Provenance parsing rejects unknown keys via `_ALLOWED_PROVENANCE_KEYS_BASE` (`:193,279-294`).

Targeted tests exist at `tests/polaris_graph/test_m61_human_completion.py:228` and `:239`.

## Medium 2 — other_justification required
Verified. `_parse_provenance()` conditionally allows and requires `other_justification` only when `source_type == "other"` (`human_gap_completion.py:279-330`), and rejects it as an unknown key otherwise.

Targeted tests exist at `tests/polaris_graph/test_m61_human_completion.py:246` and `:271`.

## Nit — UTC enforcement
Verified. `acquired_at` now requires an explicit UTC offset and raises with `"UTC"` in the error (`human_gap_completion.py:343-358`). Non-UTC offsets fail; `"Z"` and `"+00:00"` pass.

Targeted test exists at `tests/polaris_graph/test_m61_human_completion.py:215`.

## Third-round adversarial attempts
- Other-field paper-binding bypass: not found. Acceptance is keyed on `entity_id` + DOI symmetry; `source_locator`, `artifact_retention_path`, `quote_source`, and manifest fields do not influence task acceptance.
- HUMAN_CURATED downstream collapse: not found. `slot_fill` and `slot_validator` branch only on `FRAME_GAP_UNRECOVERABLE`; HUMAN_CURATED stays a normal non-gap provenance class downstream.
- Manifest JSON round-trip: passed. `human_curated_provenance` survives `FrameRow` → `SlotCoverageEntry` → `asdict()` → JSON with the expected keys.
- Determinism regression from new field: not found. `human_curated_provenance` is derived entirely from completion input; two identical `to_frame_rows()` calls produced equal `FrameRow` objects in manual probing.
- Duplicate-completion rejection vs partial-fulfillment: the duplicate-completion defense works as intended. One non-blocking wrinkle remains: `validate_against_tasks()` is entity-keyed, so duplicate M-60 task entries for the same `entity_id` collapse to one accepted completion. That does not reopen the six audited issues, and later slot validation still catches underfilled slots.

## Residual concerns
- `python -m pytest tests/polaris_graph/test_m61_human_completion.py` was code-green except for the 3 `tmp_path`-based `load_completions` tests, which failed due environment `PermissionError` in pytest tempdir setup/cleanup. I manually verified those three behaviors using workspace-backed files: valid load, non-array root rejection, and malformed-record index reporting.
- If M-60 intentionally emits multiple human-completion tasks for the same `entity_id`, the entity-keyed acceptance contract should be documented or deduped upstream for clarity.

## Next
On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-62
(non-clinical generalization guard — V30's final layer).
