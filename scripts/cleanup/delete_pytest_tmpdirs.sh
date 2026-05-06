#!/usr/bin/env bash
# scripts/cleanup/delete_pytest_tmpdirs.sh — Linux/CI fallback (DRY-RUN ONLY).
# Allowlist-only DELETE for §3.3-§3.5. Implements --dry-run + resolved-path checks.
# Exits non-zero on any path NOT in allowlist or matching DO-NOT-TOUCH.
# iter 16 CLEAN-BASH-APPLY-STALE-15 fix: --apply rejects (use PowerShell canonical for Apply).
set -euo pipefail

MODE="${1:-}"
case "$MODE" in
  --dry-run) ;;
  --apply)
    # iter 15 CLEAN-BASH-MANIFEST-PARITY-1 fix: bash variant is dry-run only.
    # Apply-mode delete must use the PowerShell canonical script which emits manifest entries.
    echo "ERROR: bash variant is DRY-RUN ONLY. Use scripts/cleanup/delete_pytest_tmpdirs.ps1 -Mode Apply for real deletes (emits required manifest entries per §4)." >&2
    exit 64
    ;;
  *) echo "Usage: $0 --dry-run" >&2; exit 64;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Glob patterns to delete (literal-prefix, may contain trailing wildcards)
ALLOWLIST=(
  ".codex_tmp" ".codex_tmp_*" ".codex_pytest_tmp"
  ".tmp" ".tmp-pytest" ".tmp_pytest" ".tmp_pytest_base"
  ".tmp_pytest_*" ".tmp_walkthrough" ".tmp_md3_review"
  ".tmp_m_prod_1_r2_*" ".pytest_tmp" ".tmp_*"
  "POLARIS.tmppytest" "POLARIStmp_pytest_m_int_3_reviewbasetemp"
  "pytest_run_*" "py_pytest_*" "pytest-cache-files-*"
  "codex_tmp_*" "tmp_*" "tmp[0-9a-z]*"
  "manual_*" "manual_review_scratch_*" "manual_pytest_base_*"
  "manual_tmp_*" "manual_sqlite_dir"
  "m_int_*_manual_*" "m_int_*_v*_manual_*" "m_int_*_probe_*"
  "m9_v*" "m10v*" "m8_*" "md3_*"
  "dashboard_probe_*" "_m1v2_tmp2"
  "m_int_2_main_async_check" "m_int_2_manual_check"
  "m_int_7_concurrency_probe" "m_int_7_main_async_probe"
  "m_int_7_manual_probe" "m_int_7_manual_probe.txt"
  "m_int_10_manual_*" "m_int_11_*manual*" "m_new_race_*" "m_live_4_r2_*"
  "m26_v17_round4_*"
  "jobs_test_probe.sqlite" "m10v2_manual_*.sqlite" "m10v2_ws_probe_*.sqlite"
  "m10v3_*.sqlite" "m_int_11_manual_review_*.sqlite"
  "manual_probe_root.sqlite" "sqlite_probe_root.sqlite"
  "write_probe_root.txt"
  # iter 7 CLEAN-BASH-FALLBACK-2 fix: outputs/* pytest tmpdirs (parity with PowerShell allowlist)
  "outputs/codex_tmp_pytest" "outputs/pytest_basetemp"
  "outputs/pytest_temp" "outputs/pytest_tmp"
)

# DO-NOT-TOUCH: any of these resolved-path prefixes refuses deletion (CLEAN-EXEC-2)
# PR-1 dryrun-iter-4 P1-001 fix: cleanup_audit.md section 2 immutable list mirrored.
DO_NOT_TOUCH_PREFIXES=(
  "$REPO_ROOT/.git" "$REPO_ROOT/.github" "$REPO_ROOT/.gitignore" "$REPO_ROOT/.gitattributes"
  "$REPO_ROOT/.env" "$REPO_ROOT/.env.example"
  "$REPO_ROOT/.legacy"                          # cleanup_audit.md section 2:56 immutable
  "$REPO_ROOT/polaris-controls"                 # cleanup_audit.md section 2:39 admin-only sister repo
  "$REPO_ROOT/src" "$REPO_ROOT/web" "$REPO_ROOT/tests" "$REPO_ROOT/scripts"
  "$REPO_ROOT/docs" "$REPO_ROOT/config"
  "$REPO_ROOT/state/pg_" "$REPO_ROOT/state/polaris_restart"
  "$REPO_ROOT/archive" "$REPO_ROOT/.private"
  "$REPO_ROOT/outputs/codex_findings" "$REPO_ROOT/outputs/audits"
  "$REPO_ROOT/README.md" "$REPO_ROOT/CLAUDE.md" "$REPO_ROOT/architecture.md"
  "$REPO_ROOT/Dockerfile" "$REPO_ROOT/docker-compose.yml" "$REPO_ROOT/.dockerignore"
  "$REPO_ROOT/pyproject.toml" "$REPO_ROOT/requirements.txt" "$REPO_ROOT/package.json"
  "$REPO_ROOT/pytest.ini" "$REPO_ROOT/conftest.py"
)

count=0
for pattern in "${ALLOWLIST[@]}"; do
  for match in $pattern; do
    [[ -e "$match" ]] || continue
    abs="$(realpath "$match")"
    # Resolved-path check (CLEAN-EXEC-2): refuse anything inside DO-NOT-TOUCH
    for dnt in "${DO_NOT_TOUCH_PREFIXES[@]}"; do
      if [[ "$abs" == "$dnt"* ]]; then
        echo "REFUSING $match (resolves to $abs, inside protected $dnt)" >&2
        exit 2
      fi
    done
    if [ "$MODE" = "--dry-run" ]; then
      echo "WOULD DELETE: $match  (resolved: $abs)"
    fi
    count=$((count+1))
  done
done

echo ""
echo "Total: $count paths"
[ "$MODE" = "--dry-run" ] && echo "DRY RUN — nothing deleted. Bash variant is dry-run only (per iter 18 CLEAN-BASH-DRYRUN-MSG-17 fix); use scripts/cleanup/delete_pytest_tmpdirs.ps1 -Mode Apply for real Apply."
