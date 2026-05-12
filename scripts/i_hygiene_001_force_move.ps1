# I-hygiene-001 force-move pass for Windows perm-locked dirs
$ErrorActionPreference = 'Continue'
$root = 'C:\POLARIS'
$dest = 'C:\POLARIS\archive\2026-05-11-root-hygiene\root'
$skipped = @('archive','config','data','docs','helm','logs','memory','models','outputs','polaris-controls','scripts','src','state','tests','web','.claude','.codex','.git','.github','.legacy','.private')
$total = 0
$moved = 0
$failed = @()
Get-ChildItem -Path $root -Directory -Force | Where-Object { $skipped -notcontains $_.Name } | ForEach-Object {
    $total++
    $src = $_.FullName
    $dst = Join-Path $dest $_.Name
    if (Test-Path $dst) {
        # Destination collision — skip (already moved by prior pass)
        return
    }
    try {
        # Clear read-only / hidden on all descendants
        & attrib -R -H -S "$src\*" /S /D 2>$null
        Move-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop
        $moved++
    } catch {
        $failed += "$src : $($_.Exception.Message)"
    }
}
Write-Output "force_move: total=$total moved=$moved failed=$($failed.Count)"
if ($failed.Count -gt 0) {
    $failed | Out-File -FilePath 'state\polaris_restart\i_hygiene_001_force_move_failures.txt' -Encoding utf8
    Write-Output "wrote failures to state\polaris_restart\i_hygiene_001_force_move_failures.txt"
}
