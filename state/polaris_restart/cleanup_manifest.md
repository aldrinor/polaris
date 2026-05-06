# POLARIS cleanup manifest — append-only audit trail

**Schema:** YAML stream, one entry per cleanup-PR action. Each entry contains:

- `entry_id` — sequential `del_NNN` / `arc_NNN` / `ren_NNN` per session
- `path` — POSIX-style repo-relative path (forward-slashes)
- `action` — `DELETE` | `ARCHIVE` | `RENAME` (verbatim from cleanup_audit.md classification)
- `destination` — for ARCHIVE: archive path; for RENAME: new path; for DELETE: `null`
- `reason` — section reference from cleanup_audit.md
- `references_grep` — count of git-tracked refs to this path (0 = unreferenced)
- `last_modified` — `git log -1 --format=%ci` for tracked files; `untracked` for untracked
- `last_committed_sha` — `git log -1 --format=%H` for tracked files; `untracked` for untracked
- `size_bytes` — total recursive size at action time
- For directories: `recursive_file_count`, `permission_denied_count`, `permission_denied_paths`, `permission_denied_sidecar_path`, `merkle_root_sha256`, `per_file_checksums_sha256`, `per_file_checksums_sidecar_path`, `unreadable_marker`
- For files: `sha256`
- `evidence_chain` — drafted_by / drafted_in_session / referenced_in_plan
- `cleanup_pr` — 1..8 sequential
- `codex_audit_verdict` — `APPROVE_PENDING` until Codex APPROVE on dry-run

**Append rule:** entries are appended BY scripts/cleanup/delete_pytest_tmpdirs.ps1 (Apply mode) BEFORE the underlying file/dir is deleted. A delete failure does NOT roll back the manifest entry — the on-disk file remains, and the entry stays for forensic recovery.

**Sidecars directory:** `state/polaris_restart/cleanup_manifest_sidecars/` holds per-entry `<entry_id>.per_file.txt` (per-file SHA tree dump in UTF-8 no-BOM with LF line endings) and `<entry_id>.permission_denied.txt` (only when permission_denied_count > 0).

**Iter 21 schema lock:** `per_file_checksums_sha256` is computed as `SHA256(combined_text)` where `combined_text = (per_file_lines joined by "\n") + "\n"`. The sidecar file `<entry_id>.per_file.txt` MUST be written with the SAME bytes (UTF-8 no BOM, LF endings) for verification to succeed.

---

## Entries

The block below is an append-only YAML document. Cleanup-PR-1 -Mode Apply
appends entries under the `entries:` key. Cleanup-PR-2..PR-8 append further
archive/rename entries to the same list. The fenced YAML block is intentionally
unclosed at file end so `Add-Content` writes append INTO the YAML body, not
after a closing fence.

```yaml
entries:
  # Cleanup-PR-1 -Mode Apply appends here. Each entry conforms to the schema
  # documented above (directory entries with merkle_root_sha256 + sidecar refs;
  # file entries with sha256 + size_bytes).
  - entry_id: del_000
    path: '.codex_pytest_tmp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['.codex_pytest_tmp/m_int_0a']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_000.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_000.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_001
    path: '.codex_tmp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 11
    permission_denied_paths: ['.codex_tmp/basetemp', '.codex_tmp/dashboard_pins_vwiv5zh_', '.codex_tmp/dashboard_probe_nnhlji68', '.codex_tmp/pytest-cache-files-dic6qlpl', '.codex_tmp/pytest-cache-files-gspffvcb', '.codex_tmp/pytest-cache-files-rw5it5lu', '.codex_tmp/pytest-cache-files-ws141xdj', '.codex_tmp/pytest-of-msn', '.codex_tmp/pytest-temp', '.codex_tmp/tmpa1p3yho_', '.codex_tmp/tmp_0e75uq2']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_001.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_001.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_002
    path: '.codex_tmp_md3_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 3
    permission_denied_paths: ['.codex_tmp_md3_review/basetemp', '.codex_tmp_md3_review/pytest-cache-files-9j2dzpz7', '.codex_tmp_md3_review/pytest-cache-files-nqn88doc']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_002.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_002.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_003
    path: '.codex_tmp_m_int_6_v1_review_fresh'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['.codex_tmp_m_int_6_v1_review_fresh']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_003.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_003.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_004
    path: '.pytest_tmp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['.pytest_tmp']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_004.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_004.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_005
    path: '.tmp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 180217
    recursive_file_count: 12
    permission_denied_count: 11
    permission_denied_paths: ['.tmp/mprod1_route_rename_60s__hyo', '.tmp/m_live_4_r2_y5pvii09', '.tmp/pytest', '.tmp/pytest-cache-files-a7xb53r_', '.tmp/pytest-cache-files-asfemdyj', '.tmp/pytest-of-msn', '.tmp/pytest_m_int_0b_v2', '.tmp/pytest_m_int_0b_v2_single', '.tmp/pytest_run', '.tmp/tmpjz6l_afq', '.tmp/tmpsp4xdf87']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_005.permission_denied.txt'
    merkle_root_sha256: 'e82d59cc0795e3b18faee73804bb9ba7e22a2b5b25b39dfdbd24ae7f084f24da'
    per_file_checksums_sha256: 'e82d59cc0795e3b18faee73804bb9ba7e22a2b5b25b39dfdbd24ae7f084f24da'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_005.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_006
    path: '.tmp-pytest'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['.tmp-pytest']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_006.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_006.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_007
    path: '.tmp_md3_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 147456
    recursive_file_count: 6
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '180ebc84beaecaa5f9a24c59efd65862ef0748f1426bfe2d2efc69ebdd4b90d1'
    per_file_checksums_sha256: '180ebc84beaecaa5f9a24c59efd65862ef0748f1426bfe2d2efc69ebdd4b90d1'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_007.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_008
    path: '.tmp_m_prod_1_r2_5b4477eb46764de48895701b90e5e7ae'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 96183
    recursive_file_count: 81
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '069abe8d1f65ed572c30c1334a2bdc99370e1e439472efa251140ae0d922ef04'
    per_file_checksums_sha256: '069abe8d1f65ed572c30c1334a2bdc99370e1e439472efa251140ae0d922ef04'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_008.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_009
    path: '.tmp_prb_hook_bash_iter7_122a88d13ed4439bb273a5d7eefdf989'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 206
    recursive_file_count: 2
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'e99824730e6204d37e1d0e6791a2d4996432a9c72709797b8f900041cd750460'
    per_file_checksums_sha256: 'e99824730e6204d37e1d0e6791a2d4996432a9c72709797b8f900041cd750460'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_009.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_010
    path: '.tmp_prb_hook_review_f7247467baaa4bd58a7e654e0e12d6bc'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 353
    recursive_file_count: 3
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'c101708ddfda4b72c8ad532a39c6a8905f5a833ce6e41b9850aa03f549088945'
    per_file_checksums_sha256: 'c101708ddfda4b72c8ad532a39c6a8905f5a833ce6e41b9850aa03f549088945'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_010.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_011
    path: '.tmp_prb_hook_review_iter7_7118088b317d4f7ca3164f67a3ab6fc0'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 206
    recursive_file_count: 2
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'e99824730e6204d37e1d0e6791a2d4996432a9c72709797b8f900041cd750460'
    per_file_checksums_sha256: 'e99824730e6204d37e1d0e6791a2d4996432a9c72709797b8f900041cd750460'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_011.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_012
    path: '.tmp_prb_hook_test_c12e22c530f74b11920906d5ecb674f5'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 1585
    recursive_file_count: 3
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '106eede2e073664c3062ac4125d02c9a2ce174be28a3d2e21479cb5795e9c991'
    per_file_checksums_sha256: '106eede2e073664c3062ac4125d02c9a2ce174be28a3d2e21479cb5795e9c991'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_012.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_013
    path: '.tmp_pytest'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 4
    permission_denied_paths: ['.tmp_pytest/basetemp', '.tmp_pytest/pytest-cache-files-9d49poqp', '.tmp_pytest/pytest-cache-files-sc3pv95m', '.tmp_pytest/pytest-of-msn']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_013.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_013.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_014
    path: '.tmp_pytest_base'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['.tmp_pytest_base']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_014.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_014.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_015
    path: '.tmp_pytest_md3_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['.tmp_pytest_md3_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_015.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_015.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_016
    path: '.tmp_pytest_md3_review2'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['.tmp_pytest_md3_review2']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_016.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_016.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_017
    path: '.tmp_pytest_m_int_2'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 3
    permission_denied_paths: ['.tmp_pytest_m_int_2/basetemp', '.tmp_pytest_m_int_2/pytest-cache-files-ohy5ka6b', '.tmp_pytest_m_int_2/pytest-cache-files-th4c1its']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_017.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_017.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_018
    path: '.tmp_pytest_m_int_3'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['.tmp_pytest_m_int_3']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_018.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_018.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_019
    path: '.tmp_pytest_m_live_1_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['.tmp_pytest_m_live_1_review/basetemp']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_019.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_019.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_020
    path: '.tmp_walkthrough'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 16617
    recursive_file_count: 5
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '3534d8947a985972712587e177dc8f9acfffc791762ec83ad008a1edd6fd898a'
    per_file_checksums_sha256: '3534d8947a985972712587e177dc8f9acfffc791762ec83ad008a1edd6fd898a'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_020.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_021
    path: 'codex_tmp_billing_quota_store_review_alt'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_billing_quota_store_review_alt']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_021.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_021.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_022
    path: 'codex_tmp_md3_pytest'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 3
    permission_denied_paths: ['codex_tmp_md3_pytest/basetemp', 'codex_tmp_md3_pytest/pytest-cache-files-5p4pe18f', 'codex_tmp_md3_pytest/pytest-cache-files-g5_66my5']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_022.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_022.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_023
    path: 'codex_tmp_m_int_10_v1_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_10_v1_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_023.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_023.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_024
    path: 'codex_tmp_m_int_10_v1_review_rerun'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_10_v1_review_rerun']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_024.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_024.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_025
    path: 'codex_tmp_m_int_10_v1_single'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_10_v1_single']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_025.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_025.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_026
    path: 'codex_tmp_m_int_10_v1_single2'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_10_v1_single2']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_026.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_026.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_027
    path: 'codex_tmp_m_int_10_v2_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_10_v2_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_027.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_027.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_028
    path: 'codex_tmp_m_int_10_v2_review_fresh'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_10_v2_review_fresh']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_028.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_028.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_029
    path: 'codex_tmp_m_int_10_v3_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_10_v3_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_029.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_029.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_030
    path: 'codex_tmp_m_int_10_v3_review_probe'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_10_v3_review_probe']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_030.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_030.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_031
    path: 'codex_tmp_m_int_11_v1_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_11_v1_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_031.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_031.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_032
    path: 'codex_tmp_m_int_11_v1_review_fresh_20260429'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_11_v1_review_fresh_20260429']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_032.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_032.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_033
    path: 'codex_tmp_m_int_11_v2_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_11_v2_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_033.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_033.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_034
    path: 'codex_tmp_m_int_11_v2_review_fresh'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_11_v2_review_fresh']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_034.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_034.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_035
    path: 'codex_tmp_m_int_11_v2_review_fresh_subset'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_11_v2_review_fresh_subset']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_035.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_035.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_036
    path: 'codex_tmp_m_int_5_v2_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_5_v2_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_036.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_036.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_037
    path: 'codex_tmp_m_int_5_v3_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_5_v3_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_037.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_037.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_038
    path: 'codex_tmp_m_int_5_v3_review_probe'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_5_v3_review_probe']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_038.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_038.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_039
    path: 'codex_tmp_m_int_5_v4_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_5_v4_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_039.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_039.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_040
    path: 'codex_tmp_m_int_5_v4_review_fresh'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_5_v4_review_fresh']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_040.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_040.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_041
    path: 'codex_tmp_m_int_5_v4_review_fresh2'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_5_v4_review_fresh2']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_041.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_041.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_042
    path: 'codex_tmp_m_int_6_v1_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_6_v1_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_042.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_042.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_043
    path: 'codex_tmp_m_int_7_v1_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_7_v1_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_043.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_043.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_044
    path: 'codex_tmp_m_int_7_v1_review_fresh'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_7_v1_review_fresh']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_044.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_044.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_045
    path: 'codex_tmp_m_int_7_v2_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_7_v2_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_045.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_045.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_046
    path: 'codex_tmp_m_int_7_v2_review_alt'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_7_v2_review_alt']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_046.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_046.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_047
    path: 'codex_tmp_m_int_7_v2_single'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_7_v2_single']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_047.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_047.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_048
    path: 'codex_tmp_m_int_7_v3_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_7_v3_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_048.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_048.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_049
    path: 'codex_tmp_m_int_7_v3_review_fresh'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_7_v3_review_fresh']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_049.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_049.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_050
    path: 'codex_tmp_m_int_9_v1_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_9_v1_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_050.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_050.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_051
    path: 'codex_tmp_m_int_9_v1_review_single'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_9_v1_review_single']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_051.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_051.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_052
    path: 'codex_tmp_m_int_9_v2_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_9_v2_review']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_052.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_052.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_053
    path: 'codex_tmp_m_int_9_v2_review_fresh'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_m_int_9_v2_review_fresh']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_053.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_053.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_054
    path: 'codex_tmp_pytest'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 18
    permission_denied_paths: ['codex_tmp_pytest/basetemp', 'codex_tmp_pytest/m1_v3_review', 'codex_tmp_pytest/m6_review', 'codex_tmp_pytest/m6_v2_review', 'codex_tmp_pytest/m8_v3_repeat/pytest-cache-files-emy3jzim', 'codex_tmp_pytest/m8_v3_repeat/pytest-cache-files-ifrpgfwe', 'codex_tmp_pytest/m8_v3_repeat/run1', 'codex_tmp_pytest/m8_v3_review/basetemp', 'codex_tmp_pytest/m8_v3_review/pytest-cache-files-gdsntehr', 'codex_tmp_pytest/m8_v3_review/pytest-cache-files-w2ydeerr', 'codex_tmp_pytest/m9_v2_review/basetemp', 'codex_tmp_pytest/m9_v4_direct/pause_test_k7931r_x', 'codex_tmp_pytest/m9_v4_review/basetemp', 'codex_tmp_pytest/pytest-cache-files-hpfzlu65', 'codex_tmp_pytest/pytest-cache-files-nhxwstx3', 'codex_tmp_pytest/pytest-of-msn', 'codex_tmp_pytest/tmp3mznye_6', 'codex_tmp_pytest/tmphqr_2pxb']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_054.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_054.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_055
    path: 'codex_tmp_pytest_m11'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 7
    permission_denied_paths: ['codex_tmp_pytest_m11/basetemp', 'codex_tmp_pytest_m11/pytest-cache-files-3r1xbz5a', 'codex_tmp_pytest_m11/pytest-cache-files-j3bgq3dp', 'codex_tmp_pytest_m11/pytest-cache-files-uhc9n9ki', 'codex_tmp_pytest_m11/pytest-cache-files-z05ztwqu', 'codex_tmp_pytest_m11/run', 'codex_tmp_pytest_m11/run2/pytest-of-msn']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_055.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_055.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_056
    path: 'codex_tmp_pytest_m15a_v2'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 3
    permission_denied_paths: ['codex_tmp_pytest_m15a_v2/basetemp', 'codex_tmp_pytest_m15a_v2/pytest-cache-files-3igrvw1b', 'codex_tmp_pytest_m15a_v2/pytest-cache-files-6xqnwb4w']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_056.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_056.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_057
    path: 'codex_tmp_pytest_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['codex_tmp_pytest_review/basetemp']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_057.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_057.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_058
    path: 'codex_tmp_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 3
    permission_denied_paths: ['codex_tmp_review/basetemp', 'codex_tmp_review/pytest', 'codex_tmp_review/tmporwu3ryq']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_058.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_058.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_059
    path: 'dashboard_probe_f2ltuo3t'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['dashboard_probe_f2ltuo3t']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_059.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_059.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_060
    path: 'dashboard_probe_hhthuj3n'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['dashboard_probe_hhthuj3n']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_060.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_060.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_061
    path: 'dashboard_probe_xdvktanm'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['dashboard_probe_xdvktanm']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_061.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_061.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_062
    path: 'dashboard_probe_znaia9ry'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['dashboard_probe_znaia9ry']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_062.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_062.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_063
    path: 'dashboard_probe_zw62d2fs'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['dashboard_probe_zw62d2fs']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_063.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_063.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_064
    path: 'm10v2_manual_yz_33hqh'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['m10v2_manual_yz_33hqh']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_064.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_064.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_065
    path: 'm10v3_one_wlcrnh2f'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['m10v3_one_wlcrnh2f']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_065.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_065.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_066
    path: 'm26_v17_round4_2yv6i6cq'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 57344
    recursive_file_count: 1
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'db9b8543c8e03af31b8b68291ba645cd8e55c576dc3333ca3c8469fe0f5c3ed0'
    per_file_checksums_sha256: 'db9b8543c8e03af31b8b68291ba645cd8e55c576dc3333ca3c8469fe0f5c3ed0'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_066.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_067
    path: 'm8_tmp_check'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['m8_tmp_check/basetemp']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_067.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_067.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_068
    path: 'm8_v4_manual_runs'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 204800
    recursive_file_count: 10
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'd071d69eca857924920c6b404225ce0d96a076b2c511fc3562538ca14f3b7756'
    per_file_checksums_sha256: 'd071d69eca857924920c6b404225ce0d96a076b2c511fc3562538ca14f3b7756'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_068.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_069
    path: 'm8_v4_manual_suite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 102400
    recursive_file_count: 5
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '94829e6f3ff6752b796a40ebee53b7ad5bf51967df4c0720b0de9466cce2f76f'
    per_file_checksums_sha256: '94829e6f3ff6752b796a40ebee53b7ad5bf51967df4c0720b0de9466cce2f76f'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_069.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_070
    path: 'm8_v4_pytest'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['m8_v4_pytest/basetemp_target_1']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_070.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_070.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_071
    path: 'm9_v2_debug_pause'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 21709
    recursive_file_count: 2
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '7b4375ee0ee775465114eebb34a00f1ecc939819e795f8a001d9ec8d07186fd4'
    per_file_checksums_sha256: '7b4375ee0ee775465114eebb34a00f1ecc939819e795f8a001d9ec8d07186fd4'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_071.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_072
    path: 'm9_v2_manual_verify'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 4
    permission_denied_paths: ['m9_v2_manual_verify/debug_67nfxsqx', 'm9_v2_manual_verify/test_concurrent_same_slug_jobs_get_isolated_artifact_dirs_ucrg74d6', 'm9_v2_manual_verify/test_pause_request_fails_loudly_for_v30_clinical_u0fuejnk', 'm9_v2_manual_verify/test_runner_completes_and_returns_artifact_dir_98bbq1o9']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_072.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_072.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_073
    path: 'm9_v2_pause_flake'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 217258
    recursive_file_count: 23
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '9d584a7533174c2521427edf7014dc3fb8b583341641e9f4da11323cc479372e'
    per_file_checksums_sha256: '9d584a7533174c2521427edf7014dc3fb8b583341641e9f4da11323cc479372e'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_073.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_074
    path: 'm9_v2_pause_history'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 108657
    recursive_file_count: 12
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'b73d66102373c212cfff5504a94ecfb88cf5f8d3ff7d60aee6e8b52d7293086a'
    per_file_checksums_sha256: 'b73d66102373c212cfff5504a94ecfb88cf5f8d3ff7d60aee6e8b52d7293086a'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_074.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_075
    path: 'm9_v2_summary_verify'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 130425
    recursive_file_count: 15
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '120184d76c385711d1e413151eea37bbc19dd5b53430908ef26a0f00cbd739d9'
    per_file_checksums_sha256: '120184d76c385711d1e413151eea37bbc19dd5b53430908ef26a0f00cbd739d9'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_075.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_076
    path: 'm9_v4_manual'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 26034
    recursive_file_count: 3
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'a52038ac624ed556dcabd1ca3e96973c82befd203b143362d690e42e00d124df'
    per_file_checksums_sha256: 'a52038ac624ed556dcabd1ca3e96973c82befd203b143362d690e42e00d124df'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_076.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_077
    path: 'm9_v4_manual_repro'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 21938
    recursive_file_count: 3
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '47011b998d49a95ee8972721608d5bac3a07159be8d680788a32b24ff45aa983'
    per_file_checksums_sha256: '47011b998d49a95ee8972721608d5bac3a07159be8d680788a32b24ff45aa983'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_077.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_078
    path: 'm9_v4_repeat_runs'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 65814
    recursive_file_count: 9
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'eb8a1215ad8e4f3a72c5137c76dc52b36a13bb43558550f95dfc7da02e77191a'
    per_file_checksums_sha256: 'eb8a1215ad8e4f3a72c5137c76dc52b36a13bb43558550f95dfc7da02e77191a'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_078.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_079
    path: 'manual_m_int_5_v4_probe'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 1741
    recursive_file_count: 6
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '35f6f5696462784ee163e37eb24355531c4fdadc350c20d4166a18d1f40cfb23'
    per_file_checksums_sha256: '35f6f5696462784ee163e37eb24355531c4fdadc350c20d4166a18d1f40cfb23'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_079.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_080
    path: 'manual_m_int_5_v4_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 1741
    recursive_file_count: 6
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'aaeb30b07330c146d794ea7ca82c416a055c0c06a16dbfe29b655b34f18a9225'
    per_file_checksums_sha256: 'aaeb30b07330c146d794ea7ca82c416a055c0c06a16dbfe29b655b34f18a9225'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_080.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_081
    path: 'manual_pytest_base_m_int_7'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['manual_pytest_base_m_int_7']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_081.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_081.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_082
    path: 'manual_pytest_base_m_int_7_ok'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['manual_pytest_base_m_int_7_ok']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_082.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_082.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_083
    path: 'manual_review_scratch'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 330502
    recursive_file_count: 4
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '77c35b7213ee4eca57ade6e8a8b50f6a0a92391e614340c2a3cb2d6083e3bd50'
    per_file_checksums_sha256: '77c35b7213ee4eca57ade6e8a8b50f6a0a92391e614340c2a3cb2d6083e3bd50'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_083.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_084
    path: 'manual_review_scratch_m_int_10_v3'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 7
    permission_denied_paths: ['manual_review_scratch_m_int_10_v3/case_0fi46bg0', 'manual_review_scratch_m_int_10_v3/multi_6s8_s1qq', 'manual_review_scratch_m_int_10_v3/norm_bjq0be8a', 'manual_review_scratch_m_int_10_v3/norm_rg5jsj56', 'manual_review_scratch_m_int_10_v3/probe_5m0km2ig', 'manual_review_scratch_m_int_10_v3/pytest_base_single', 'manual_review_scratch_m_int_10_v3/pytest_cbed7372a7bb40aea2391561685324a6']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_084.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_084.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_085
    path: 'manual_review_scratch_m_int_9_v2'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 2
    permission_denied_paths: ['manual_review_scratch_m_int_9_v2/pytest_base', 'manual_review_scratch_m_int_9_v2/pytest_temp2/pytest-of-msn']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_085.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_085.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_086
    path: 'manual_sqlite_dir'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 172032
    recursive_file_count: 6
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'f0d25d29fefcac59fcb5f1b59da2d31c28e19d9ee25c5d2fcd14a898166e1375'
    per_file_checksums_sha256: 'f0d25d29fefcac59fcb5f1b59da2d31c28e19d9ee25c5d2fcd14a898166e1375'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_086.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_087
    path: 'manual_tmp_m_int_3'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 6
    permission_denied_paths: ['manual_tmp_m_int_3/m_int_3_vuogvrw1', 'manual_tmp_m_int_3/tmp0mgvzuit', 'manual_tmp_m_int_3/tmpaxxfmfxi', 'manual_tmp_m_int_3/tmpil0qrijb', 'manual_tmp_m_int_3/tmplt41kesg', 'manual_tmp_m_int_3/tmppwq_ebab']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_087.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_087.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_088
    path: 'manual_tmp_m_int_3_v3'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['manual_tmp_m_int_3_v3']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_088.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_088.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_089
    path: 'md3_manual_check'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 98304
    recursive_file_count: 4
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '2deb207538c4f20d59dc87c238365c0a695b5591fa24c6fbdf2f41f22c681fbc'
    per_file_checksums_sha256: '2deb207538c4f20d59dc87c238365c0a695b5591fa24c6fbdf2f41f22c681fbc'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_089.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_090
    path: 'md3_pytest_run2'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['md3_pytest_run2']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_090.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_090.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_091
    path: 'md3_round3_manual_tmp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['md3_round3_manual_tmp/tmpow6efjpr']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_091.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_091.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_092
    path: 'md3_round3_pytest_tmp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 2
    permission_denied_paths: ['md3_round3_pytest_tmp/base1', 'md3_round3_pytest_tmp/base2']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_092.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_092.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_093
    path: 'm_int_10_manual_57asn199'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['m_int_10_manual_57asn199']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_093.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_093.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_094
    path: 'm_int_11_probe_7cc8ad01'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 65536
    recursive_file_count: 2
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '42b9fe3167bad6a7d66e532525060d71f71d37482961b6aac9587542bf1535fb'
    per_file_checksums_sha256: '42b9fe3167bad6a7d66e532525060d71f71d37482961b6aac9587542bf1535fb'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_094.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_095
    path: 'm_int_2_main_async_check'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 687
    recursive_file_count: 2
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '365ce2fab2469e05277981a0216c6635f3d8316337f25efea46c4e64d97b1b1c'
    per_file_checksums_sha256: '365ce2fab2469e05277981a0216c6635f3d8316337f25efea46c4e64d97b1b1c'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_095.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_096
    path: 'm_int_7_concurrency_probe'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 28672
    recursive_file_count: 1
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '87cbc5a3927c19e1865ec3b4bd89d0fbf3f24abf2314edaffd3f49c4a55a9c5b'
    per_file_checksums_sha256: '87cbc5a3927c19e1865ec3b4bd89d0fbf3f24abf2314edaffd3f49c4a55a9c5b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_096.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_097
    path: 'm_int_7_main_async_probe'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 29744
    recursive_file_count: 3
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '42559114f2d778590d415b07d8edfb1a6fc699e78c454cf391655b17b12dff5d'
    per_file_checksums_sha256: '42559114f2d778590d415b07d8edfb1a6fc699e78c454cf391655b17b12dff5d'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_097.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_098
    path: 'm_int_7_v2_manual_5fgxbzoc'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['m_int_7_v2_manual_5fgxbzoc']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_098.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_098.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_099
    path: 'm_int_7_v3_manual_dhypw5bz'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['m_int_7_v3_manual_dhypw5bz']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_099.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_099.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_100
    path: 'm_live_4_r2_3qyr9r66'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['m_live_4_r2_3qyr9r66']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_100.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_100.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_101
    path: 'm_new_race_5ammwgpi'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 28672
    recursive_file_count: 1
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: '0b92a393a5e0d5504e9e4d4b54fba02d624ff74a96afbf7a155970032c640132'
    per_file_checksums_sha256: '0b92a393a5e0d5504e9e4d4b54fba02d624ff74a96afbf7a155970032c640132'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_101.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_102
    path: 'POLARIS.tmppytest'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['POLARIS.tmppytest']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_102.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_102.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_103
    path: 'POLARIStmp_pytest_m_int_3_reviewbasetemp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['POLARIStmp_pytest_m_int_3_reviewbasetemp']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_103.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_103.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_104
    path: 'pytest-cache-files-o969a6s7'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['pytest-cache-files-o969a6s7']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_104.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_104.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_105
    path: 'pytest-cache-files-tw8jzxb3'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['pytest-cache-files-tw8jzxb3']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_105.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_105.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_106
    path: 'pytest_run_3842f3b95af34ad8b6f93080344d5110'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['pytest_run_3842f3b95af34ad8b6f93080344d5110']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_106.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_106.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_107
    path: 'pytest_run_554e954860ba4943a4f9f6097fe8541f'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['pytest_run_554e954860ba4943a4f9f6097fe8541f']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_107.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_107.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_108
    path: 'pytest_run_ae0dcde87f184046b2b4b8ec9cc6f7ba'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['pytest_run_ae0dcde87f184046b2b4b8ec9cc6f7ba']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_108.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_108.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_109
    path: 'py_pytest_b6ae8d9d497443b4b0306f18bf9b8ee9'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['py_pytest_b6ae8d9d497443b4b0306f18bf9b8ee9']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_109.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_109.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_110
    path: 'tmp2ef0ie4p'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmp2ef0ie4p']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_110.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_110.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_111
    path: 'tmp2hhmpr2y'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmp2hhmpr2y']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_111.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_111.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_112
    path: 'tmp48c8ko2m'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmp48c8ko2m']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_112.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_112.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_113
    path: 'tmp63988s99'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmp63988s99']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_113.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_113.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_114
    path: 'tmp8u9ua575'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmp8u9ua575']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_114.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_114.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_115
    path: 'tmp9h7v7fon'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmp9h7v7fon']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_115.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_115.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_116
    path: 'tmpaufjwjy5'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmpaufjwjy5']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_116.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_116.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_117
    path: 'tmpgb143kt_'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmpgb143kt_']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_117.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_117.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_118
    path: 'tmppvxh8fwq'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmppvxh8fwq']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_118.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_118.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_119
    path: 'tmpq5bdi1rl'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmpq5bdi1rl']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_119.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_119.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_120
    path: 'tmptgnkdlz5'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmptgnkdlz5']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_120.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_120.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_121
    path: 'tmpu2b082f6'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmpu2b082f6']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_121.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_121.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_122
    path: 'tmpuyki_w88'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmpuyki_w88']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_122.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_122.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_123
    path: 'tmpv1dnokk6'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmpv1dnokk6']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_123.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_123.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_124
    path: 'tmpw2ru3yoj'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmpw2ru3yoj']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_124.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_124.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_125
    path: 'tmpxnalraft'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmpxnalraft']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_125.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_125.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_126
    path: 'tmpyl5f0goo'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmpyl5f0goo']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_126.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_126.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_127
    path: 'tmp_ae3ucgg'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmp_ae3ucgg']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_127.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_127.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_128
    path: 'tmp_pytest_m_int_0b'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmp_pytest_m_int_0b/basetemp']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_128.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_128.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_129
    path: 'tmp_pytest_m_int_2'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 3
    permission_denied_paths: ['tmp_pytest_m_int_2/basetemp', 'tmp_pytest_m_int_2/pytest-cache-files-6aj13ym2', 'tmp_pytest_m_int_2/pytest-cache-files-yfgponc6']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_129.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_129.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_130
    path: 'tmp_pytest_m_int_3'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['tmp_pytest_m_int_3']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_130.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_130.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_131
    path: 'tmp_pytest_m_int_3_review'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 3
    permission_denied_paths: ['tmp_pytest_m_int_3_review/basetemp', 'tmp_pytest_m_int_3_review/pytest-cache-files-8vum0pcs', 'tmp_pytest_m_int_3_review/pytest-cache-files-tygwhrz0']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_131.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_131.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_132
    path: '_m1v2_tmp2'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 2026
    recursive_file_count: 25
    permission_denied_count: 0
    permission_denied_paths: []
    permission_denied_sidecar_path: null
    merkle_root_sha256: 'facb5155275f22b2f7916b142748e089a773d82e80785c04f93ffb3bcce3b5a0'
    per_file_checksums_sha256: 'facb5155275f22b2f7916b142748e089a773d82e80785c04f93ffb3bcce3b5a0'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_132.per_file.txt'
    unreadable_marker: false
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_133
    path: 'jobs_test_probe.sqlite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 8192
    sha256: '6ea03c47528308fb468d2ff38b76dd34dab587ed3deaa8f5ff345d81ffaa205d'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_134
    path: 'm10v2_manual_ee33796eb72948efb789f96e10d7b959.sqlite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 32768
    sha256: 'c2114ed5bdbed676242fd8b2ee0edf968ec7683c10757b075a1393eedec34427'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_135
    path: 'm10v2_ws_probe_18ebe8de2df9451d993d048629b7e8b5.sqlite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 32768
    sha256: '9d01281cf132fd1e2aa330e5a3c694d36abfb30653b93c89a22eb8c2a6d1b917'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_136
    path: 'm10v3_case_1bb42af907ae42d0aa277865c6b5c4a4.sqlite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 32768
    sha256: 'b2d0c46d27272217cdba3a7eea32aec920b5121a3d186270d5630acab646cf2a'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_137
    path: 'm10v3_multi_f88f4f91329844d197e114ce668c3ab9.sqlite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 32768
    sha256: '8594395eefb546df072c903540e94a5641556673d4bc3f63241a3ef268bcb9cc'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_138
    path: 'm10v3_norm_0490d7335ec24c35a6fd9c465babc451.sqlite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 32768
    sha256: '6bd9de6d866310695686f9ed8f218432970d5246619040f0673f9f1cc083fa69'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_139
    path: 'manual_probe_root.sqlite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 8192
    sha256: 'acb18b86c03ae5dcb9124bfa7cb818c1292be5cca66da3fd0db04242df37be4d'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_140
    path: 'm_int_11_manual_review_d0ebf148fcc849eb9d7f91daaa5d4443.sqlite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 32768
    sha256: '51f7c1c4dce0a52e4adb49e57ee4cb40db9dd00bf3bfca0a98be603c3304916f'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_141
    path: 'm_int_7_manual_probe.txt'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_142
    path: 'sqlite_probe_root.sqlite'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 8192
    sha256: '32d6aef5c827049bac90e9f1b362abc1ae6c920b5b9edef41dfc9e53e8a49786'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_143
    path: 'write_probe_root.txt'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 2
    sha256: '2689367b205c16ce32ed4200942b8b8b1e262dfc70d9bc9fbc77c49699a4f1df'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_144
    path: 'outputs/codex_tmp_pytest'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 287984
    recursive_file_count: 18
    permission_denied_count: 14
    permission_denied_paths: ['outputs/codex_tmp_pytest/m8_v2_review/basetemp', 'outputs/codex_tmp_pytest/m8_v4_review/basetemp_router', 'outputs/codex_tmp_pytest/m8_v4_review/basetemp_target', 'outputs/codex_tmp_pytest/m8_v4_review/pytest-cache-files-awr1k0_j', 'outputs/codex_tmp_pytest/m8_v4_review/pytest-cache-files-g693n1fn', 'outputs/codex_tmp_pytest/m8_v4_review/pytest-cache-files-lcz1hd3_', 'outputs/codex_tmp_pytest/m8_v4_review/pytest-cache-files-o49ruyzk', 'outputs/codex_tmp_pytest/m9_v3_review/basetemp', 'outputs/codex_tmp_pytest/m9_v3_review/pytest-cache-files-hf82j1ev', 'outputs/codex_tmp_pytest/m9_v3_review/pytest-cache-files-nkj6x505', 'outputs/codex_tmp_pytest/m9_v3_review_loop/pytest-cache-files-trpp2lhz', 'outputs/codex_tmp_pytest/m9_v3_review_loop/pytest-cache-files-z3ditaf2', 'outputs/codex_tmp_pytest/m9_v3_review_loop/run1', 'outputs/codex_tmp_pytest/md10']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_144.permission_denied.txt'
    merkle_root_sha256: '2507a57df01cc74309e7672bb04913008b6b43b6edb655352b11b4173d46fcfc'
    per_file_checksums_sha256: '2507a57df01cc74309e7672bb04913008b6b43b6edb655352b11b4173d46fcfc'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_144.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_145
    path: 'outputs/pytest_basetemp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['outputs/pytest_basetemp']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_145.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_145.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_146
    path: 'outputs/pytest_temp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['outputs/pytest_temp']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_146.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_146.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
  - entry_id: del_147
    path: 'outputs/pytest_tmp'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: 0
    recursive_file_count: 0
    permission_denied_count: 1
    permission_denied_paths: ['outputs/pytest_tmp/basetemp']
    permission_denied_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_147.permission_denied.txt'
    merkle_root_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sha256: '01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b'
    per_file_checksums_sidecar_path: 'state/polaris_restart/cleanup_manifest_sidecars/del_147.per_file.txt'
    unreadable_marker: true
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
