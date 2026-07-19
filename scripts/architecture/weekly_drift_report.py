"""I-meta-001 (#933) Step 12: Weekly drift report.

Emits a markdown report covering:
- untracked decision docs (in docs/, state/, polaris-controls/, .codex/)
- stale model refs in tracked docs (Gemma 4 31B references after the 4-role lock)
- role-set conformance (lock declares N roles; code wires M)
- branch <-> state/active_issue.json conformance

Run weekly (cron) or on-demand. Output goes to state/drift_reports/<utc-date>.md.

Exit code: 0 if all green; 1 if any drift detected.
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

DECISION_DOC_PATTERNS = (
    re.compile(r"_lock_?\d", re.I),
    re.compile(r"_sota_?\d", re.I),
    re.compile(r"_pick", re.I),
    re.compile(r"_audit_\d{4}_\d{2}_\d{2}", re.I),
    re.compile(r"polaris_step_\w+_\d{4}", re.I),
)


def _run(cmd: list[str]) -> str:
    """Run a shell command in the repo, return stdout."""
    out = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    return out.stdout


def find_untracked_decision_docs() -> list[str]:
    """Return any untracked files in docs/, state/, polaris-controls/, .codex/ whose name
    matches a decision-doc pattern (lock, sota, pick, audit, step-X)."""
    raw = _run(["git", "ls-files", "--others", "--exclude-standard",
                "docs/", "state/", "polaris-controls/", ".codex/"])
    flagged: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        name = Path(line).name
        if any(p.search(name) for p in DECISION_DOC_PATTERNS):
            flagged.append(line)
    return flagged


def find_stale_model_refs() -> list[tuple[str, int, str]]:
    """Scan tracked docs for `google/gemma-4-31b-it` references that don't carry a
    superseded-frontmatter or archive context. Returns [(file, line_no, snippet), ...]."""
    raw = _run(["git", "grep", "-n", "-I", "google/gemma-4-31b-it", "--", "docs/", "*.md"])
    stale = []
    for line in raw.splitlines():
        if not line:
            continue
        if line.startswith("docs/archive/"):
            continue  # archived, expected
        # Quick frontmatter check: load the file and look for status: superseded
        try:
            path_str, line_no_str, *snippet_parts = line.split(":", 2)
            line_no = int(line_no_str)
            snippet = snippet_parts[0] if snippet_parts else ""
        except (ValueError, IndexError):
            continue
        full_path = REPO_ROOT / path_str
        if full_path.exists():
            head = full_path.read_text(encoding="utf-8", errors="replace")[:1000]
            if "status: superseded" in head:
                continue
        stale.append((path_str, line_no, snippet.strip()))
    return stale


def check_role_set_conformance() -> dict:
    """Compare lock's required_roles against code defaults in pathB_runner + entailment_judge.

    Returns a dict with declared (from lock) and actually-wired roles.
    """
    import yaml
    lock_path = REPO_ROOT / "config" / "architecture" / "polaris_runtime_lock.yaml"
    if not lock_path.exists():
        return {"lock_present": False, "declared": [], "wired": [], "missing": []}
    lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    declared = sorted(lock.get("required_roles", {}).keys())

    # Crude scan of pathB_runner for RolePin("<role>", ...) constructions
    runner = (REPO_ROOT / "src" / "polaris_graph" / "benchmark" / "benchmark_gate_runner.py").read_text(encoding="utf-8")
    wired = sorted(set(re.findall(r'RolePin\("(\w+)"', runner)))
    missing = sorted(set(declared) - set(wired))

    return {
        "lock_present": True,
        "declared": declared,
        "wired": wired,
        "missing": missing,
    }


def check_branch_active_issue_conformance() -> dict:
    """Compare current git branch name to state/active_issue.json:active_issue_id."""
    branch = _run(["git", "branch", "--show-current"]).strip()
    active_issue_path = REPO_ROOT / "state" / "active_issue.json"
    active = "(missing)"
    match = False
    if active_issue_path.exists():
        try:
            data = json.loads(active_issue_path.read_text(encoding="utf-8"))
            active = data.get("active_issue_id", "(no key)")
            # Branch convention: bot/I-<prefix>-<NNN>-<slug> → active_issue_id should be I-<prefix>-<NNN>
            m = re.match(r"bot/(I-[a-z0-9]+-\d+[a-z]?)", branch)
            if m and m.group(1) == active:
                match = True
        except Exception:
            pass
    return {"branch": branch, "active_issue_id": active, "match": match}


def render_report() -> tuple[str, int]:
    """Generate the markdown report. Returns (markdown, exit_code)."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    drift_count = 0
    lines = [
        f"# POLARIS weekly drift report — {now}",
        "",
        "Generated by `scripts/architecture/weekly_drift_report.py` (I-meta-001 Step 12).",
        "",
        "## 1. Untracked decision documents",
        "",
    ]
    untracked = find_untracked_decision_docs()
    if untracked:
        drift_count += len(untracked)
        lines.extend([f"- `{f}`" for f in untracked])
        lines.append("")
        lines.append("**Action:** `git add` + commit, or move to `docs/archive/` if obsolete.")
    else:
        lines.append("All decision documents tracked.")
    lines.append("")

    lines.extend(["## 2. Stale model refs in tracked docs", ""])
    stale = find_stale_model_refs()
    if stale:
        drift_count += len(stale)
        for path, line_no, snippet in stale[:20]:
            lines.append(f"- `{path}:{line_no}`  `{snippet[:120]}`")
        if len(stale) > 20:
            lines.append(f"- ...and {len(stale) - 20} more.")
        lines.append("")
        lines.append("**Action:** update or add `status: superseded` frontmatter; reference `config/architecture/polaris_runtime_lock.yaml`.")
    else:
        lines.append("No stale `google/gemma-4-31b-it` refs in tracked docs.")
    lines.append("")

    lines.extend(["## 3. Role-set conformance", ""])
    role = check_role_set_conformance()
    if not role["lock_present"]:
        lines.append("**No `config/architecture/polaris_runtime_lock.yaml`** — drift class not measurable.")
        drift_count += 1
    else:
        lines.append(f"- Declared in lock: `{role['declared']}`")
        lines.append(f"- Wired in `pathB_runner.py`: `{role['wired']}`")
        if role["missing"]:
            drift_count += 1
            lines.append(f"- **Missing:** `{role['missing']}`")
            lines.append("")
            lines.append("**Action:** wire the missing role modules + RolePin constructors.")
        else:
            lines.append("- **OK** — every locked role is wired.")
    lines.append("")

    lines.extend(["## 4. Branch ↔ active_issue conformance", ""])
    bi = check_branch_active_issue_conformance()
    lines.append(f"- Current branch: `{bi['branch']}`")
    lines.append(f"- `state/active_issue.json:active_issue_id`: `{bi['active_issue_id']}`")
    if bi["match"]:
        lines.append("- **OK** — branch name and active_issue agree.")
    else:
        drift_count += 1
        lines.append("- **MISMATCH** — branch name and active_issue diverge. This is the I-meta-001 V3 drift class.")
        lines.append("")
        lines.append("**Action:** rename branch OR update `state/active_issue.json` so they agree.")
    lines.append("")

    if drift_count == 0:
        lines.append("## Summary")
        lines.append("")
        lines.append("**ALL GREEN** — no drift detected.")
    else:
        lines.append("## Summary")
        lines.append("")
        lines.append(f"**DRIFT DETECTED** — {drift_count} class(es) of drift surfaced. Operator action required.")

    return "\n".join(lines), 0 if drift_count == 0 else 1


def main() -> int:
    report, code = render_report()
    out_dir = REPO_ROOT / "state" / "drift_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    out_file = out_dir / f"{date_str}.md"
    out_file.write_text(report, encoding="utf-8")
    # Print UTF-8-safe summary to stdout (Windows cp1252 chokes on Unicode arrows).
    sys.stdout.buffer.write(report.encode("utf-8", "replace"))
    sys.stdout.buffer.write(b"\n")
    print(f"\n[written to {out_file.relative_to(REPO_ROOT)}]", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
