"""
Static import-closure analysis to identify live vs orphaned code.

From live entry points (orchestrators, passing tests, smoke tests),
compute the transitive set of imported modules. Anything under src/
or scripts/ that is NOT reached is a candidate for archive.

Produces: docs/live_code_audit.md (markdown report).

No files are moved or deleted — this is read-only analysis.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(r"C:/POLARIS")
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"


# ─────────────────────────────────────────────────────────────────────────
# Entry points — files whose imports (direct + transitive) count as "live".
# ─────────────────────────────────────────────────────────────────────────
def _find_entry_points() -> list[Path]:
    """Every script with `if __name__ == "__main__":` is an entry point,
    plus every test file. This maximally widens the 'live' set so we
    don't falsely accuse tools the user runs directly."""
    eps: list[Path] = []
    # All __main__-scripts (under scripts/ only; src/ shouldn't have them)
    for p in SCRIPTS.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if 'if __name__ == "__main__":' in txt or "if __name__ == '__main__':" in txt:
            eps.append(p)
    # All tests
    for p in TESTS.rglob("test_*.py"):
        eps.append(p)
    return eps


ENTRY_POINTS: list[Path] = _find_entry_points()


@dataclass
class ModuleInfo:
    path: Path
    imports: set[str] = field(default_factory=set)


def module_name_for_path(path: Path) -> str:
    """Convert /abs/src/polaris_graph/x/y.py -> src.polaris_graph.x.y"""
    rel = path.relative_to(ROOT).with_suffix("")
    parts = rel.parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def extract_imports(path: Path) -> set[str]:
    """Return the fully-qualified modules imported by this file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Handle relative imports by resolving against package
                if node.level and node.level > 0:
                    # Relative import — need to resolve
                    pkg = module_name_for_path(path)
                    pkg_parts = pkg.split(".")
                    if node.level >= len(pkg_parts):
                        continue
                    base = ".".join(pkg_parts[: -node.level + 1] if node.level > 1
                                     else pkg_parts[:-0 or None])
                    # Simpler: rebuild absolute path
                    anchor = pkg_parts[:-node.level]
                    full = ".".join(anchor + [node.module]) if anchor else node.module
                    imports.add(full)
                else:
                    imports.add(node.module)
                    for alias in node.names:
                        # Also record sub-import (from x import y may reach x.y module)
                        imports.add(f"{node.module}.{alias.name}")
            else:
                # from . import x
                pkg = module_name_for_path(path)
                pkg_parts = pkg.split(".")
                if node.level <= len(pkg_parts):
                    anchor = pkg_parts[:-node.level] if node.level > 0 else pkg_parts
                    for alias in node.names:
                        imports.add(".".join(anchor + [alias.name]))
    return imports


def scan_all_python_files(base: Path) -> dict[Path, ModuleInfo]:
    """Parse every .py under `base` and return path -> ModuleInfo."""
    out: dict[Path, ModuleInfo] = {}
    for p in base.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        out[p.resolve()] = ModuleInfo(path=p, imports=extract_imports(p))
    return out


def build_module_index(all_files: dict[Path, ModuleInfo]) -> dict[str, Path]:
    """Map module name (fully qualified) -> file path."""
    idx: dict[str, Path] = {}
    for path in all_files:
        name = module_name_for_path(path)
        idx[name] = path
    return idx


def resolve_import_to_path(
    imp: str, module_index: dict[str, Path],
) -> Path | None:
    """Given an import string like 'src.polaris_graph.generator.x',
    return the path to that module, or None if not a project file."""
    # Exact match
    if imp in module_index:
        return module_index[imp]
    # Strip trailing component (for `from x.y import Z` where Z is a name, not a module)
    parts = imp.split(".")
    while len(parts) > 1:
        parts = parts[:-1]
        candidate = ".".join(parts)
        if candidate in module_index:
            return module_index[candidate]
    return None


def compute_live_closure(
    entry_points: list[Path],
    all_files: dict[Path, ModuleInfo],
    module_index: dict[str, Path],
) -> set[Path]:
    """Transitive closure of imports from entry points."""
    live: set[Path] = set()
    queue: list[Path] = []
    for ep in entry_points:
        ep_res = ep.resolve()
        if ep_res in all_files:
            queue.append(ep_res)
            live.add(ep_res)
    while queue:
        current = queue.pop()
        info = all_files.get(current)
        if info is None:
            continue
        for imp in info.imports:
            target = resolve_import_to_path(imp, module_index)
            if target is not None and target not in live:
                live.add(target)
                queue.append(target)
    return live


def git_last_commit_date(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "log", "-1", "--format=%cd",
             "--date=short", "--", str(path.relative_to(ROOT))],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "never"
    except Exception:
        return "error"


def first_docstring(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        doc = ast.get_docstring(tree)
        if doc:
            first_line = doc.strip().split("\n")[0]
            return first_line[:120]
    except Exception:
        pass
    return ""


def grep_dynamic_imports() -> set[str]:
    """Secondary pass: look for importlib.import_module('x'), __import__('x')
    calls that static analysis misses."""
    dynamic: set[str] = set()
    for py in list(SRC.rglob("*.py")) + list(SCRIPTS.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Quick-and-dirty patterns
        import re
        for m in re.finditer(r"""importlib\.import_module\(['"]([^'"]+)['"]""", text):
            dynamic.add(m.group(1))
        for m in re.finditer(r"""__import__\(['"]([^'"]+)['"]""", text):
            dynamic.add(m.group(1))
    return dynamic


def main() -> int:
    print(f"Scanning {SRC} and {SCRIPTS}...", file=sys.stderr)
    all_files = scan_all_python_files(SRC) | scan_all_python_files(SCRIPTS)
    print(f"  total .py files: {len(all_files)}", file=sys.stderr)

    module_index = build_module_index(all_files)

    live = compute_live_closure(ENTRY_POINTS, all_files, module_index)
    print(f"  live (reachable from entry points): {len(live)}", file=sys.stderr)

    dead = sorted(set(all_files) - live, key=lambda p: str(p))
    print(f"  orphaned (NOT reachable): {len(dead)}", file=sys.stderr)

    dynamic = grep_dynamic_imports()
    print(f"  dynamic imports detected: {len(dynamic)}", file=sys.stderr)

    # Group orphans properly:
    #   src/<subpkg>/... -> group key = "src/<subpkg>"
    #   scripts/...      -> group key = "scripts"
    groups: dict[str, list[Path]] = {}
    for p in dead:
        try:
            rel = p.relative_to(ROOT)
        except ValueError:
            rel = p
        parts = rel.parts
        if parts[0] == "scripts":
            key = "scripts"
        elif parts[0] == "src" and len(parts) >= 2:
            key = f"src/{parts[1]}"
        else:
            key = parts[0]
        groups.setdefault(key, []).append(p)

    # Write report
    out_md = ROOT / "docs" / "live_code_audit.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Live-code audit — 2026-04-18")
    lines.append("")
    lines.append(
        f"Static import-closure analysis from {len(ENTRY_POINTS)} entry points "
        f"(orchestrators + preflight + tests). Produced by "
        f"`scripts/audit_live_code.py`."
    )
    lines.append("")
    lines.append(f"- Total `.py` files under `src/` + `scripts/`: **{len(all_files)}**")
    lines.append(f"- Reachable from entry points (LIVE): **{len(live)}**")
    lines.append(f"- Not reachable (ORPHAN candidates): **{len(dead)}**")
    lines.append(f"- Dynamic imports detected: **{len(dynamic)}** "
                 f"(listed in appendix — may make orphans live)")
    lines.append("")
    lines.append("## Orphan candidates by subpackage")
    lines.append("")
    lines.append(
        "Files below are NOT reachable from any entry point via static "
        "import analysis. They may still be used via dynamic imports "
        "(see appendix) or as standalone scripts. Archive only after "
        "human review."
    )
    lines.append("")
    for top in sorted(groups.keys()):
        lines.append(f"### `{top}/` — {len(groups[top])} orphan file(s)")
        lines.append("")
        lines.append("| File | Size | Last commit | First docstring line |")
        lines.append("|------|------|-------------|----------------------|")
        for p in groups[top]:
            try:
                rel = p.relative_to(ROOT)
            except ValueError:
                rel = p
            size_kb = p.stat().st_size // 1024
            date = git_last_commit_date(p)
            doc = first_docstring(p).replace("|", "\\|")
            lines.append(f"| `{rel.as_posix()}` | {size_kb}K | {date} | {doc} |")
        lines.append("")
    lines.append("## Entry points used")
    lines.append("")
    for ep in ENTRY_POINTS[:10]:
        try:
            rel = ep.relative_to(ROOT)
        except ValueError:
            rel = ep
        lines.append(f"- `{rel.as_posix()}`")
    if len(ENTRY_POINTS) > 10:
        lines.append(f"- ... plus {len(ENTRY_POINTS) - 10} test files under `tests/`")
    lines.append("")
    lines.append("## Dynamic imports appendix")
    lines.append("")
    if dynamic:
        for d in sorted(dynamic):
            lines.append(f"- `{d}`")
    else:
        lines.append("_None detected._")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {out_md}", file=sys.stderr)

    # Also write a machine-readable summary
    out_json = ROOT / "docs" / "live_code_audit.json"
    out_json.write_text(json.dumps({
        "total_files": len(all_files),
        "live_count": len(live),
        "orphan_count": len(dead),
        "orphans_by_top": {k: [str(p.relative_to(ROOT)) for p in v]
                           for k, v in groups.items()},
        "dynamic_imports": sorted(dynamic),
    }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
