HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-hygiene-001 plan iter 4 — iter-3 fixes

## P1 (iter 3) resolved

### I-HYGIENE-ITER3-P1-001 — tracked dir handling needs `git rm -r --`

**Resolution:** execution module now ALWAYS uses `git rm -r -- <src>` for any tracked path (file or dir, treats files same as dirs since `-r` is a no-op on a single file).

Implementation:
```python
import subprocess, shutil

def archive_one(src: Path, dst: Path) -> dict:
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(src)],
        capture_output=True
    ).returncode == 0
    shutil.move(str(src), str(dst))
    method = "shutil-move-only"
    if tracked:
        r = subprocess.run(["git", "rm", "-r", "--", str(src)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"git rm -r failed for {src}: {r.stderr}")
        method = "shutil-move-then-git-rm-r"
    return {"src": str(src), "dst": str(dst), "tracked": tracked, "method": method}
```

Failure mode: any nonzero from `git rm -r --` halts the executor immediately, logs to `state/polaris_restart/i_hygiene_001_move_failures.txt`, exits non-zero.

### Method label (P3 cosmetic) renamed

`shutil-move-only` (untracked) and `shutil-move-then-git-rm-r` (tracked) — chronological order matches actual execution.

## P2 (iter 3) resolved — .gitignore tracked-audit-trail conflict

The current `.gitignore` at line 162 (per Codex's reference) un-ignores `.codex/continuous/<sha>_*.md` as a tracked audit trail. I am decommissioning `.codex/continuous/` per Codex's iter-1 inspect_adjudication.

**Resolution:** during `.gitignore` patching step, REMOVE the obsolete unignore rule for `.codex/continuous/*.md`. The line to delete is in the "Test / Lint caches" or similar block in current .gitignore.

`grep -n "codex/continuous" .gitignore` will be run; the unignore line removed; replaced with a comment: `# .codex/continuous/ decommissioned 2026-05-11 per I-hygiene-001 (archived to archive/2026-05-11-root-hygiene/codex_historical/)`.

## Final execution plan (all P0/P1/P2/P3 resolved)

1. **Pre-flight:** `git diff --name-only` must be empty; untracked files preserved.
2. **Re-run inventories** (deterministic source: KEEP=174 + ARCHIVE=230 in .codex/; KEEP=35 + ARCHIVE=146 at root).
3. **Reference sweep** across `.github/ docs/ scripts/ src/ tests/` for each ARCHIVE path; save to `state/polaris_restart/i_hygiene_001_reference_sweep.md`.
4. **Create archive destinations:** `archive/2026-05-11-root-hygiene/{root,codex_historical}/`.
5. **Move per inventory** with the function above; manifest row per move.
6. **Patch references** per sweep results.
7. **Update `.gitignore`:** add anchored patterns + remove `.codex/continuous/*.md` unignore.
8. **Sanity test:** `python -c "import polaris_graph; print('ok')"` + `pytest --collect-only -q tests/polaris_graph/`.
9. **Codex diff review** (separate brief).

## Files Codex will see in the diff

- `scripts/inventory_root_hygiene.py` (NEW)
- `scripts/inventory_codex_hygiene.py` (NEW, patched twice for adjudication)
- `scripts/i_hygiene_001_execute.py` (NEW — the executor with archive_one above)
- `state/polaris_restart/i_hygiene_001_inventory.md` (NEW)
- `state/polaris_restart/i_hygiene_001_codex_inventory.md` (NEW)
- `state/polaris_restart/i_hygiene_001_cleanup_manifest.md` (NEW — 376 rows)
- `state/polaris_restart/i_hygiene_001_reference_sweep.md` (NEW)
- `.gitignore` (anchored patterns appended + continuous unignore removed)
- `.codex/<archived-path>` (376 git-rm -r removals — most files small, most dirs small)
- Reference patches in `.github/workflows/*`, `docs/**`, etc. (small textual edits)

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
