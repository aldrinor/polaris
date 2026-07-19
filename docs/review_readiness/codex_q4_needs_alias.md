# Phase 2 NEEDS-ALIAS — canonical renames (codex Q4 decision), Q4-SAFE

Codex chose the canonical names; renames applied with backward-compat aliases:
- `HonestSweepJobRunner` → **`V30ClinicalSweepJobRunner`** (+ `Config`, `make_default_v30_clinical_sweep_job_runner`); old names kept as same-object module aliases + package re-exports.
- `is_row_content_junk` → **`is_row_content_integrity_violation`**; old name kept as same-object alias.
- `junk_deletion_gate.py` → **`content_integrity_deletion_gate.py`**; old module kept as a compat shim (`from content_integrity_deletion_gate import *` + explicit re-exports) so `import ...junk_deletion_gate` still works.

**Safety (codex Q4-SAFE, high-reasoning re-gate):** aliases are same-object (`old is new`); the monkeypatch-direction risk is **grep-proven zero-instance** (no test/code patches any renamed symbol by old name); old module + old symbols remain importable; no persisted class-name/dict-key renamed; oracle replay byte-identical (9c0a3d43); collection 16738/11. Alias removal deferred to an owner-approved deprecation window per codex policy.
