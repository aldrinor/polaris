# scripts/cleanup/delete_pytest_tmpdirs.ps1 -- Windows/PowerShell canonical
# Allowlist-only DELETE for section 3.3-section 3.5. Refuses any path resolving to DO-NOT-TOUCH prefix.
# iter 17 CLEAN-PS1-FUNCTION-ORDER-16 fix: helper functions defined BEFORE main loop body.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('DryRun','Apply')]
  [string]$Mode
)
$ErrorActionPreference = 'Stop'
$repoRoot = (git rev-parse --show-toplevel) -replace '/', '\'
Set-Location $repoRoot

# === Helper functions (iter 20 CLEAN-PS1-SINGLE-FILE-STILL-CONTRADICTED-19 fix:
# bodies inlined below; this fenced block is now the SINGLE source of truth for
# scripts/cleanup/delete_pytest_tmpdirs.ps1 -- paste-runnable as one file) ===

function Convert-ToRepoRelativePosix {
    param([string]$abs_path, [string]$repo_root)
    $rel = $abs_path
    if ($abs_path.StartsWith($repo_root, [StringComparison]::OrdinalIgnoreCase)) {
        $rel = $abs_path.Substring($repo_root.Length).TrimStart('\','/')
    }
    return $rel -replace '\\', '/'
}

function Get-DirectoryMerkleHash {
    param([string]$dir_path)
    $entries = @()
    $perm_denied = @()
    $errs = $null
    # iter 21 CLEAN-PS1-LITERALPATH-PARTIAL-20 fix: -LiteralPath consistently
    Get-ChildItem -LiteralPath $dir_path -Recurse -File -Force -ErrorAction SilentlyContinue -ErrorVariable +errs |
      Sort-Object FullName |
      ForEach-Object {
        $file_path = $_.FullName
        try {
            $hash = (Get-FileHash -LiteralPath $file_path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLower()
            $rel = $file_path.Substring($dir_path.Length).TrimStart('\','/')
            $entries += "$rel`t$hash"
        } catch {
            $perm_denied += $file_path
        }
    }
    if ($errs) { foreach ($e in $errs) { $perm_denied += [string]$e.TargetObject } }
    $combined = ($entries -join "`n") + "`n"
    $merkle = [System.BitConverter]::ToString(
        [System.Security.Cryptography.SHA256]::Create().ComputeHash(
            [System.Text.Encoding]::UTF8.GetBytes($combined)
        )
    ).Replace('-','').ToLower()
    return @{
        merkle_root = $merkle
        per_file_count = $entries.Count
        permission_denied = $perm_denied
        per_file_lines = $entries
    }
}

function Append-ManifestEntryDirectory {
    param([string]$entry_id, [string]$path, $info, [string]$manifest_path, [string]$sidecars_subdir, [string]$repo_root)
    $rel_path = Convert-ToRepoRelativePosix $path $repo_root
    $perm_count = @($info.permission_denied).Count
    $unreadable = if ($perm_count -gt 0) { 'true' } else { 'false' }
    $perm_rel = @($info.permission_denied) | ForEach-Object { Convert-ToRepoRelativePosix $_ $repo_root }
    $perm_paths_inline = if ($perm_count -le 20) {
        '[' + (($perm_rel | ForEach-Object { "'" + ($_ -replace "'","''") + "'" }) -join ', ') + ']'
    } else {
        '[]  # truncated; see permission_denied_sidecar_path'
    }
    $size_bytes = (Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    if (-not $size_bytes) { $size_bytes = 0 }
    $combined_text = ($info.per_file_lines -join "`n") + "`n"
    $per_file_checksums_sha256 = [System.BitConverter]::ToString(
        [System.Security.Cryptography.SHA256]::Create().ComputeHash(
            [System.Text.Encoding]::UTF8.GetBytes($combined_text)
        )
    ).Replace('-','').ToLower()
    $perm_sidecar_field = if ($perm_count -gt 0) {
        "permission_denied_sidecar_path: '$sidecars_subdir/$entry_id.permission_denied.txt'"
    } else {
        "permission_denied_sidecar_path: null"
    }
    $yaml = @"
  - entry_id: $entry_id
    path: '$rel_path'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: $size_bytes
    recursive_file_count: $($info.per_file_count)
    permission_denied_count: $perm_count
    permission_denied_paths: $perm_paths_inline
    $perm_sidecar_field
    merkle_root_sha256: '$($info.merkle_root)'
    per_file_checksums_sha256: '$per_file_checksums_sha256'
    per_file_checksums_sidecar_path: '$sidecars_subdir/$entry_id.per_file.txt'
    unreadable_marker: $unreadable
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
"@
    Add-Content -LiteralPath $manifest_path -Value $yaml
}

function Append-ManifestEntryFile {
    param([string]$entry_id, [string]$path, [string]$manifest_path, [string]$repo_root)
    $rel_path = Convert-ToRepoRelativePosix $path $repo_root
    $sha = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
    $size = (Get-Item -LiteralPath $path).Length
    $yaml = @"
  - entry_id: $entry_id
    path: '$rel_path'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per section 3.3-section 3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: $size
    sha256: '$sha'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: 'section 3.3-section 3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
"@
    Add-Content -LiteralPath $manifest_path -Value $yaml
}

$allowlist = @(
  '.codex_tmp', '.codex_tmp_*', '.codex_pytest_tmp',
  '.tmp', '.tmp-pytest', '.tmp_pytest', '.tmp_pytest_base',
  '.tmp_pytest_*', '.tmp_walkthrough', '.tmp_md3_review',
  '.tmp_m_prod_1_r2_*', '.pytest_tmp', '.tmp_*',
  'POLARIS.tmppytest', 'POLARIStmp_pytest_m_int_3_reviewbasetemp',
  'pytest_run_*', 'py_pytest_*', 'pytest-cache-files-*',
  'codex_tmp_*', 'tmp[0-9a-z]*', 'tmp_*',
  'manual_*', 'manual_review_scratch_*', 'manual_pytest_base_*',
  'manual_tmp_*', 'manual_sqlite_dir',
  'm_int_*_manual_*', 'm_int_*_v*_manual_*', 'm_int_*_probe_*',
  'm9_v*', 'm10v*', 'm8_*', 'md3_*',
  'dashboard_probe_*', '_m1v2_tmp2',
  'm_int_2_main_async_check', 'm_int_2_manual_check',
  'm_int_7_concurrency_probe', 'm_int_7_main_async_probe',
  'm_int_7_manual_probe', 'm_int_7_manual_probe.txt',
  'm_int_10_manual_*', 'm_int_11_*manual*', 'm_new_race_*', 'm_live_4_r2_*',
  'm26_v17_round4_*',
  'jobs_test_probe.sqlite', 'm10v2_manual_*.sqlite', 'm10v2_ws_probe_*.sqlite',
  'm10v3_*.sqlite', 'm_int_11_manual_review_*.sqlite',
  'manual_probe_root.sqlite', 'sqlite_probe_root.sqlite',
  'write_probe_root.txt',
  # iter 6 CLEAN-OUTPUTS-ALLOWLIST-2 fix: outputs/* pytest tmpdirs (paths from section 3.8)
  'outputs\codex_tmp_pytest', 'outputs\pytest_basetemp',
  'outputs\pytest_temp', 'outputs\pytest_tmp'
)

$doNotTouch = @(
  '.git', '.github', '.gitignore', '.gitattributes',
  '.env', '.env.example',
  '.legacy',                         # PR-1 dryrun-iter-4 P1-001 fix: cleanup_audit.md section 2:56 immutable
  'polaris-controls',                # PR-1 dryrun-iter-4 P1-001 fix: cleanup_audit.md section 2:39 admin-only sister repo
  'src', 'web', 'tests', 'scripts',
  'docs', 'config',
  'state\pg_', 'state\polaris_restart',
  'archive', '.private',
  'outputs\codex_findings', 'outputs\audits',
  'README.md', 'CLAUDE.md', 'architecture.md',
  'Dockerfile', 'docker-compose.yml', '.dockerignore',
  'requirements.txt', 'pyproject.toml', 'package.json',
  'pytest.ini', 'conftest.py'
) | ForEach-Object { Join-Path $repoRoot $_ }

# iter 10 CLEAN-PS1-INIT-IN-BLOCK-1 fix: initialize tracking arrays INSIDE the
# fenced script before main loop (was previously documented as a sidebar after
# the block, leaving the script non-runnable as-pasted).
$deletedPaths = @()
$failedPaths = @()

# PR-1 dryrun-iter-1 fix-001 (Codex P1: Windows -Filter doesn't honor bracket ranges):
# Enumerate root-level entries ONCE then test each candidate against every
# allowlist pattern via PowerShell's `-like` operator (which DOES honor `[abc]`
# and `[0-9]` ranges). This catches dirs like `tmp2ef0ie4p` that `Get-ChildItem
# -Filter 'tmp[0-9a-z]*'` misses on Windows.
#
# PR-1 dryrun-iter-1 fix-002 (Codex P1: duplicate matches across patterns):
# Build a HashSet of resolved abs paths so each unique candidate is processed
# exactly once, even if it matches multiple allowlist patterns.
$candidatePaths = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$rootEntries = Get-ChildItem -Path . -Force -ErrorAction SilentlyContinue
foreach ($entry in $rootEntries) {
    $name = $entry.Name
    foreach ($pattern in $allowlist) {
        # outputs/* patterns need separate handling (not at root)
        if ($pattern -like '*\*' -or $pattern -like '*/*') { continue }
        if ($name -like $pattern) {
            [void]$candidatePaths.Add($entry.FullName)
            break
        }
    }
}
# Handle outputs/* patterns (paths with separators) explicitly
foreach ($pattern in $allowlist) {
    if (-not ($pattern -like '*\*' -or $pattern -like '*/*')) { continue }
    $resolved = Get-Item -LiteralPath $pattern -Force -ErrorAction SilentlyContinue
    if ($resolved) {
        [void]$candidatePaths.Add($resolved.FullName)
    }
}

# PR-1 dryrun-iter-1 fix-003 (Codex P1: partial-failure rerun manifest collision):
# In Apply mode, scan existing manifest for the highest del_NNN entry_id and
# resume counter from max+1. DryRun starts from 0 (no manifest writes).
$count = 0
if ($Mode -eq 'Apply') {
    $manifest_check = Join-Path $repoRoot 'state/polaris_restart/cleanup_manifest.md'
    if (Test-Path -LiteralPath $manifest_check) {
        # PR-1 dryrun-iter-6 P1-001 fix: array-wrap to avoid scalar-0 falsy-check
        # bug. PowerShell unwraps single-element pipelines to scalars; when the
        # only existing entry is `del_000`, `Select-String | ForEach-Object` returns
        # the scalar integer 0, and `if ($existing_ids)` evaluates false (because
        # 0 is falsy), so counter resets to 0 and overwrites sidecars on rerun.
        # `@(...)` forces array context; `$existing_ids.Count -gt 0` is the safe check.
        $existing_ids = @(Select-String -LiteralPath $manifest_check -Pattern '^\s*-?\s*entry_id:\s*del_(\d+)' -AllMatches |
            ForEach-Object { [int]$_.Matches[0].Groups[1].Value })
        if ($existing_ids.Count -gt 0) {
            $max_id = ($existing_ids | Measure-Object -Maximum).Maximum
            $count = $max_id + 1
            Write-Host "Apply mode resumes manifest counter at del_$('{0:D3}' -f $count) (max existing del_$('{0:D3}' -f $max_id))"
        }
    }
}

foreach ($abs in $candidatePaths) {
    $name = Split-Path -Leaf $abs
    foreach ($dnt in $doNotTouch) {
      if ($abs.StartsWith($dnt, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Error "REFUSING $name (resolves to $abs, inside protected $dnt)"
        exit 2
      }
    }
    if ($Mode -eq 'DryRun') {
      Write-Host "WOULD DELETE: $name  (resolved: $abs)"
    } else {
      # iter 16 CLEAN-PR1-MANIFEST-INTEGRATION-15 fix: emit manifest entry BEFORE deletion.
      # Earlier iter-13/14/15 placed Append-ManifestEntry calls in a separate snippet block;
      # this fold-in moves them inline so the script is single-runnable.
      $entry_id = "del_{0:D3}" -f $count
      $manifest_path = Join-Path $repoRoot 'state/polaris_restart/cleanup_manifest.md'
      $sidecars_dir = Join-Path $repoRoot 'state/polaris_restart/cleanup_manifest_sidecars'
      $sidecars_subdir = 'state/polaris_restart/cleanup_manifest_sidecars'
      New-Item -ItemType Directory -Path $sidecars_dir -Force | Out-Null
      try {
        if (Test-Path -LiteralPath $abs -PathType Container) {
          $info = Get-DirectoryMerkleHash $abs
          # iter 20 CLEAN-SIDECAR-HASH-BYTE-SEMANTICS-19 fix: write UTF-8 no-BOM with LF line endings
          # so sidecar bytes match the in-memory `path\tsha\n` body the merkle/per_file_checksums hash.
          $per_file_body = ($info.per_file_lines -join "`n") + "`n"
          [System.IO.File]::WriteAllText(
            (Join-Path $sidecars_dir "$entry_id.per_file.txt"),
            $per_file_body,
            (New-Object System.Text.UTF8Encoding($false))
          )
          if (@($info.permission_denied).Count -gt 0) {
            $perm_body = (($info.permission_denied) -join "`n") + "`n"
            [System.IO.File]::WriteAllText(
              (Join-Path $sidecars_dir "$entry_id.permission_denied.txt"),
              $perm_body,
              (New-Object System.Text.UTF8Encoding($false))
            )
          }
          Append-ManifestEntryDirectory $entry_id $abs $info $manifest_path $sidecars_subdir $repoRoot
        } else {
          Append-ManifestEntryFile $entry_id $abs $manifest_path $repoRoot
        }
      } catch {
        Write-Warning "MANIFEST-EMIT FAILED for $abs -- $($_.Exception.Message)"
        $failedPaths += [pscustomobject]@{
          path = $abs
          error = "manifest-emit failed: $($_.Exception.Message)"
          error_type = $_.Exception.GetType().FullName
        }
        $count++
        continue
      }
      # iter 8 CLEAN-DELETE-ACL-1 fix: capture failures from permission-denied tmpdirs
      try {
        # iter 20 CLEAN-PS1-LITERALPATH-HARDENING-19 fix: -LiteralPath consistently
        Remove-Item -LiteralPath $abs -Recurse -Force -ErrorAction Stop
        Write-Host "DELETED: $abs (manifest entry: $entry_id)"
        $deletedPaths += $abs
      } catch {
        Write-Warning "FAILED: $abs -- $($_.Exception.Message)"
        $failedPaths += [pscustomobject]@{
          path = $abs
          error = $_.Exception.Message
          error_type = $_.Exception.GetType().FullName
        }
      }
    }
    $count++
}

Write-Host ""
Write-Host "Total: $count paths processed"
if ($Mode -eq 'Apply') {
  Write-Host "Deleted: $($deletedPaths.Count); Failed: $($failedPaths.Count)"
  # iter 8 CLEAN-DELETE-ACL-1 fix: write failure manifest for forensic recovery + manual cleanup
  if ($failedPaths.Count -gt 0) {
    $failureManifestPath = Join-Path $repoRoot 'state/polaris_restart/cleanup_delete_failures.txt'
    $failedPaths | ForEach-Object {
      "$($_.path)`t$($_.error_type)`t$($_.error)"
    } | Out-File -FilePath $failureManifestPath -Encoding utf8
    Write-Host "Failure manifest: $failureManifestPath"
    # Non-zero exit so PR-1 review surfaces the failures
    exit 3
  }
}
if ($Mode -eq 'DryRun') {
  Write-Host "DRY RUN -- nothing deleted. Re-run with -Mode Apply after Codex APPROVE."
}
