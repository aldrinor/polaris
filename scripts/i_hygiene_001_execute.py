"""Execute I-hygiene-001 surgical cleanup per Codex iter-4-APPROVE'd plan.

Steps:
1. Pre-flight: `git diff --name-only` AND `git diff --cached --name-only` both empty.
2. Re-run inventories deterministically.
3. Build reference sweep across .github/, docs/, scripts/, src/, tests/.
4. Create archive destinations.
5. Move each ARCHIVE entry (shutil.move; tracked → also `git rm -r -- <src>`).
6. Halt on any failure.
7. Manifest tracked at state/polaris_restart/i_hygiene_001_cleanup_manifest.md.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("C:/POLARIS")
ARCHIVE_BASE = ROOT / "archive" / "2026-05-11-root-hygiene"
ARCHIVE_ROOT = ARCHIVE_BASE / "root"
ARCHIVE_CODEX = ARCHIVE_BASE / "codex_historical"
MANIFEST = ROOT / "state/polaris_restart/i_hygiene_001_cleanup_manifest.md"
FAILURES = ROOT / "state/polaris_restart/i_hygiene_001_move_failures.txt"


def run(cmd, cwd=ROOT, capture=True):
    return subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)


def preflight():
    print("[1/7] Pre-flight: tracked-modifications must be empty.")
    r = run(["git", "diff", "--name-only"])
    cached = run(["git", "diff", "--cached", "--name-only"])
    if r.stdout.strip() or cached.stdout.strip():
        print(f"  ABORT: tracked changes present (diff={r.stdout.strip()!r}, cached={cached.stdout.strip()!r})")
        sys.exit(1)
    print("  OK: no tracked modifications. Untracked files preserved.")


def inventories():
    print("[2/7] Re-run inventories.")
    for s in ["inventory_root_hygiene.py", "inventory_codex_hygiene.py"]:
        r = subprocess.run([sys.executable, f"scripts/{s}"], cwd=ROOT, capture_output=True, text=True)
        print(f"  {s}: {r.stdout.strip()}")
        if r.returncode != 0:
            print(f"  ABORT: {s} failed: {r.stderr}")
            sys.exit(1)


def parse_inventory(path: Path, section: str) -> list[str]:
    """Parse the bullet list under '## ARCHIVE' or '## KEEP' from an inventory MD."""
    text = path.read_text(encoding="utf-8")
    pat = rf"## {section}.*?\n\n(.*?)(?=\n##|\Z)"
    m = re.search(pat, text, re.DOTALL)
    if not m:
        return []
    items = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("[D]") and not line.startswith("[F]"):
            continue
        # "[D] name — reason"
        m2 = re.match(r"^\[[DF]\]\s+(\S.*?)\s+—\s+", line)
        if m2:
            items.append(m2.group(1))
    return items


def reference_sweep(archive_paths: list[str]) -> str:
    """Pure-Python recursive scan: read each text-ish file in target dirs once,
    then check membership of each archive_path. Avoids per-path grep subprocess
    fan-out (which was ~376 * 5 = 1880 subprocess calls)."""
    print("[3/7] Reference sweep (pure Python).")
    out_path = ROOT / "state/polaris_restart/i_hygiene_001_reference_sweep.md"
    body = ["# I-hygiene-001 reference sweep", "",
            "For each archive candidate, scan across .github/, docs/, scripts/, src/, tests/ for references."
            " Hits below need post-move patching.", ""]
    targets = [".github", "docs", "scripts", "src", "tests"]
    text_exts = {".md", ".py", ".yaml", ".yml", ".toml", ".json", ".txt", ".sh", ".ts", ".tsx", ".js"}
    needles = list(archive_paths)
    hits_by_needle: dict[str, list[str]] = {n: [] for n in needles}
    files_scanned = 0
    for target in targets:
        tdir = ROOT / target
        if not tdir.exists():
            continue
        for f in tdir.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in text_exts:
                continue
            try:
                txt = f.read_text(encoding="utf-8", errors="ignore")
            except (OSError, PermissionError):
                continue
            files_scanned += 1
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            for needle in needles:
                if needle in txt:
                    hits_by_needle[needle].append(rel)
    n_hits = sum(len(v) for v in hits_by_needle.values())
    for needle, hits in hits_by_needle.items():
        if hits:
            body.append(f"## `{needle}` — {len(hits)} hit(s)")
            for h in hits:
                body.append(f"- `{h}`")
            body.append("")
    body.insert(2, f"Scanned {files_scanned} text files. Total hit count: {n_hits}.")
    out_path.write_text("\n".join(body), encoding="utf-8")
    print(f"  saved {out_path} ({files_scanned} files scanned, {n_hits} hits)")
    return str(out_path)


def chmod_recursive(path: Path) -> int:
    """Clear read-only on path + all descendants. Returns count of items chmod'd."""
    import stat as _stat
    n = 0
    try:
        path.chmod(_stat.S_IRWXU | _stat.S_IRWXG | _stat.S_IRWXO)
        n += 1
    except (PermissionError, OSError):
        pass
    if path.is_dir():
        for child in path.rglob("*"):
            try:
                child.chmod(_stat.S_IRWXU | _stat.S_IRWXG | _stat.S_IRWXO)
                n += 1
            except (PermissionError, OSError):
                pass
    return n


def archive_one(src: Path, dst_dir: Path) -> dict:
    """Move src into dst_dir; if tracked, git rm -r --. On PermissionError, retry once with chmod.
    Returns dict with status='moved' or status='skipped_perm' (NOT halted — caller handles)."""
    if not src.exists():
        # Already moved on prior run; idempotent.
        return {"src": str(src.relative_to(ROOT)).replace("\\", "/"),
                "dst": "(already absent)", "tracked": False, "method": "noop-source-missing",
                "size_bytes": 0, "status": "noop"}
    src_rel = str(src.relative_to(ROOT)).replace("\\", "/")
    tracked_check = subprocess.run(
        ["git", "ls-files", "--error-unmatch", src_rel],
        cwd=ROOT, capture_output=True, text=True
    )
    tracked = tracked_check.returncode == 0
    dst = dst_dir / src.name
    if dst.exists():
        raise RuntimeError(f"destination collision: {dst}")
    method = "shutil-move-only"
    try:
        shutil.move(str(src), str(dst))
    except PermissionError:
        # Try once with recursive chmod to clear Windows read-only bits.
        chmod_recursive(src)
        try:
            shutil.move(str(src), str(dst))
            method = "shutil-move-after-chmod"
        except PermissionError as e:
            return {"src": src_rel, "dst": "(skipped)", "tracked": tracked,
                    "method": "skipped-permission-denied", "size_bytes": -1,
                    "status": "skipped_perm", "error": str(e)}
    if tracked:
        r = subprocess.run(
            ["git", "rm", "-r", "--", src_rel],
            cwd=ROOT, capture_output=True, text=True
        )
        if r.returncode != 0:
            raise RuntimeError(f"git rm -r failed for {src_rel}: {r.stderr}")
        method = method + "+git-rm-r" if method.endswith("chmod") else "shutil-move-then-git-rm-r"
    try:
        size = sum(f.stat().st_size for f in dst.rglob("*") if f.is_file()) if dst.is_dir() else dst.stat().st_size
    except Exception:
        size = -1
    return {
        "src": src_rel,
        "dst": str(dst.relative_to(ROOT)).replace("\\", "/"),
        "tracked": tracked,
        "method": method,
        "size_bytes": size,
        "status": "moved",
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    preflight()
    inventories()

    root_archive = parse_inventory(ROOT / "state/polaris_restart/i_hygiene_001_inventory.md", "ARCHIVE")
    codex_archive = parse_inventory(ROOT / "state/polaris_restart/i_hygiene_001_codex_inventory.md", "ARCHIVE")
    print(f"  parsed: root ARCHIVE={len(root_archive)}, codex ARCHIVE={len(codex_archive)}")

    # Reference sweep BEFORE moves
    reference_sweep([f"{p}" for p in root_archive] + [f".codex/{p}" for p in codex_archive])

    print("[4/7] Create archive destinations.")
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    ARCHIVE_CODEX.mkdir(parents=True, exist_ok=True)

    print("[5/7] Move root ARCHIVE entries.")
    manifest_rows = []
    skipped_perm = []
    failures = []
    for name in root_archive:
        src = ROOT / name
        try:
            row = archive_one(src, ARCHIVE_ROOT)
            manifest_rows.append(row)
            if row.get("status") == "skipped_perm":
                skipped_perm.append(row)
        except Exception as e:
            failures.append(f"ROOT {name}: {e}")
            print(f"  FAIL {name}: {e}")
            break  # halt on hard failure (not skipped_perm)
    print(f"  root: {len(manifest_rows)} processed, {len(skipped_perm)} skipped (perm), {len(failures)} hard failed")

    if not failures:
        print("[6/7] Move .codex ARCHIVE entries.")
        for name in codex_archive:
            src = ROOT / ".codex" / name
            try:
                row = archive_one(src, ARCHIVE_CODEX)
                manifest_rows.append(row)
                if row.get("status") == "skipped_perm":
                    skipped_perm.append(row)
                if len(manifest_rows) % 50 == 0:
                    print(f"  ... {len(manifest_rows)} processed")
            except Exception as e:
                failures.append(f"CODEX {name}: {e}")
                print(f"  FAIL .codex/{name}: {e}")
                break
        print(f"  total processed: {len(manifest_rows)} ({len(skipped_perm)} perm-skipped), {len(failures)} hard failed")

    print(f"[7/7] Write manifest + failures.")
    body = ["# I-hygiene-001 cleanup manifest",
            "",
            f"Total moves: {len(manifest_rows)} | failures: {len(failures)}",
            "",
            "| src | dst | tracked | method | size_bytes |",
            "|---|---|---|---|---:|"]
    for r in manifest_rows:
        body.append(f"| `{r['src']}` | `{r['dst']}` | {r['tracked']} | {r['method']} | {r['size_bytes']} |")
    MANIFEST.write_text("\n".join(body), encoding="utf-8")
    if failures:
        FAILURES.write_text("\n".join(failures), encoding="utf-8")
        print(f"  WROTE FAILURES TO {FAILURES} — halting non-zero")
        sys.exit(2)
    print(f"  manifest saved {MANIFEST}")
    print(f"  SUCCESS: {len(manifest_rows)} moves completed; 0 failures.")


if __name__ == "__main__":
    main()
