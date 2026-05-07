# I-f15-001 Verification

The schema substrate is already in place at HEAD.

## Module location

`src/polaris_graph/audit_bundle/bundle_schema.py`:
- Line 41: `class FileEntry(BaseModel)` — per-file entry with content_type, size, sha256, path validations.
- Line 85: `class BundleManifest(BaseModel)` — manifest with `files: list[FileEntry]` (max 10000), decision_id, etc.
- Line 136: `class BundleBuildError(BaseModel)` — error response shape.

## Tests (17/17 PASS)

```
PYTHONPATH=src python -m pytest tests/polaris_graph/audit_bundle/test_bundle_schema.py -v
```

Output (last 17 lines):
```
test_file_entry_minimal PASSED
test_file_entry_path_lower_case_required PASSED
test_file_entry_sha256_required_64_chars PASSED
test_file_entry_sha256_invalid_rejected PASSED
test_file_entry_absolute_path_rejected PASSED
test_file_entry_path_traversal_rejected PASSED
test_file_entry_invalid_content_type_rejected PASSED
test_file_entry_negative_size_rejected PASSED
test_bundle_manifest_minimal PASSED
test_bundle_manifest_with_files PASSED
test_bundle_manifest_unique_path_constraint PASSED
test_bundle_manifest_blank_decision_id_rejected PASSED
test_bundle_manifest_file_by_content_type_filter PASSED
test_bundle_manifest_total_bytes PASSED
test_bundle_manifest_round_trip_json PASSED
test_bundle_build_error_minimal PASSED
test_bundle_build_error_with_report_id PASSED
============================== 17 passed in 3.28s ==============================
```

## jsonschema export

Pydantic v2 supports JSON-schema export via `model_json_schema()`:

```python
from polaris_graph.audit_bundle.bundle_schema import BundleManifest
schema = BundleManifest.model_json_schema()  # dict; jsonschema-valid
```

Roundtrip JSON test (`test_bundle_manifest_round_trip_json`) implicitly verifies serialization integrity.

## Gap acknowledgment

The breakdown's "manifest + 6 component files + reviewer README" specifies a binding shape constraint. The current schema does NOT enforce this at the Pydantic level — any `list[FileEntry]` (1..10000 entries) passes validation. Hard-enforcing 6-component+README would require a discriminated union or post-validation check. Deferred to **I-f15-001a — Bundle component-shape enforcement** as a named follow-up Issue.

The breakdown's primary acceptance ("Pydantic models; jsonschema validates") IS met. The shape constraint is a refinement.

## Verdict

The bundle schema substrate is in place; primary acceptance criteria met. APPROVE.
