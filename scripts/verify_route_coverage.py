"""
verify_route_coverage.py — route-coverage gate for codex-visual-required.

Given a list of changed files (one path per line on stdin) and a
manifest produced by visual_review_gate.py, verifies that:

  * Every `web/app/<segments>/page.tsx` change in the PR maps to a
    route present in the manifest's `route:` field. Next.js convention
    is followed: `web/app/foo/bar/page.tsx` → `/foo/bar`; dynamic
    segments like `[runId]` match any concrete value in the manifest.

  * `web/components/**` changes are reported as advisory — they can be
    used in any page, so per-file route coverage is undecidable without
    a build-time import graph. The operator is expected to list the
    affected pages explicitly in the brief; the gate logs them.

  * `web/app/<...>/layout.tsx`, `web/app/<...>/template.tsx`,
    `web/app/<...>/route.ts` etc. that are NOT `page.tsx` are also
    advisory — they affect any page below their directory, so coverage
    is operator-declared not auto-derivable.

Exits 0 on full coverage, 1 on any uncovered `page.tsx` route, 2 on
input error.

Codex iter-3 P1 fix: closes the gap where a current-head audit could
cover an unrelated route and still satisfy the manifest-walk check.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


PAGE_RE = re.compile(r"^web/app/(?P<segments>.*?)/?page\.tsx$")
DYNAMIC_SEG_RE = re.compile(r"\[[^/\]]+\]")


def changed_page_route(path: str) -> str | None:
    """Map web/app/<segments>/page.tsx → /<segments>.

    `web/app/page.tsx` → `/`
    `web/app/inspector/[runId]/page.tsx` → `/inspector/[runId]`
    `web/app/(group)/dashboard/page.tsx` → `/dashboard` (Next.js group)
    """
    m = PAGE_RE.match(path)
    if not m:
        return None
    segments = m.group("segments")
    if not segments:
        return "/"
    # Drop Next.js (group) segments — they don't affect URL.
    parts = [p for p in segments.split("/") if not (p.startswith("(") and p.endswith(")"))]
    if not parts:
        return "/"
    return "/" + "/".join(parts)


def matches_manifest_route(declared_route: str, manifest_routes: list[str]) -> bool:
    """`declared_route` may contain `[runId]`-style dynamic segments.

    A manifest route matches if, segment-by-segment:
      - declared is `[<name>]`  → any concrete segment in manifest matches
      - declared is concrete    → must equal the manifest segment exactly
    """
    declared_parts = [p for p in declared_route.split("/") if p]
    for mroute in manifest_routes:
        m_parts = [p for p in mroute.split("/") if p]
        if len(m_parts) != len(declared_parts):
            continue
        ok = True
        for d, m in zip(declared_parts, m_parts):
            if DYNAMIC_SEG_RE.fullmatch(d):
                # dynamic — accept any non-empty concrete
                if not m:
                    ok = False
                    break
            elif d != m:
                ok = False
                break
        if ok:
            return True
    return False


def discover_all_app_routes(repo_root: Path) -> list[str]:
    """Enumerate every web/app/<segments>/page.tsx in the repo.

    Returns the derived route list (Next.js convention). Used to require
    a conservative full-route sweep when the PR touches non-page UI
    surface (web/components/** or layout/template/loading/error/
    not-found.tsx) — those changes affect undetermined pages, so the
    only mechanically-enforceable contract is "audit every page".
    """
    routes: set[str] = set()
    app_dir = repo_root / "web" / "app"
    if not app_dir.exists():
        return []
    for page in app_dir.rglob("page.tsx"):
        rel = page.relative_to(repo_root).as_posix()
        r = changed_page_route(rel)
        if r is not None:
            routes.add(r)
    return sorted(routes)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--manifest", required=True, help="path to manifest.json")
    p.add_argument(
        "--changed-files",
        required=False,
        help="path to file with changed paths (one per line); defaults to stdin",
    )
    p.add_argument(
        "--repo-root",
        default=".",
        help="repo root for discovering all page.tsx routes (default: cwd)",
    )
    args = p.parse_args()

    mpath = Path(args.manifest)
    if not mpath.exists():
        print(f"ERROR: manifest not at {mpath}", file=sys.stderr)
        return 2
    try:
        entries = json.loads(mpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: manifest not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(entries, list):
        print("ERROR: manifest is not a list", file=sys.stderr)
        return 2

    manifest_routes = sorted({e.get("route") for e in entries if e.get("route")})
    if not manifest_routes:
        print("ERROR: manifest has no route fields", file=sys.stderr)
        return 2

    if args.changed_files:
        changed = Path(args.changed_files).read_text(encoding="utf-8").splitlines()
    else:
        changed = sys.stdin.read().splitlines()
    changed = [c.strip() for c in changed if c.strip()]

    uncovered: list[tuple[str, str]] = []
    broad_changes: list[str] = []
    page_changes: list[tuple[str, str]] = []

    for path in changed:
        if path.startswith("web/app/") and path.endswith("page.tsx"):
            route = changed_page_route(path)
            if route is None:
                continue
            page_changes.append((path, route))
            if not matches_manifest_route(route, manifest_routes):
                uncovered.append((path, route))
        elif path.startswith("web/components/"):
            broad_changes.append(path)
        elif path.startswith("web/app/") and (
            path.endswith("layout.tsx")
            or path.endswith("template.tsx")
            or path.endswith("loading.tsx")
            or path.endswith("error.tsx")
            or path.endswith("not-found.tsx")
        ):
            broad_changes.append(path)

    print(f"Manifest routes: {len(manifest_routes)}")
    for r in manifest_routes:
        print(f"  {r}")
    print(f"Page changes: {len(page_changes)}")
    for path, route in page_changes:
        covered = "OK" if (path, route) not in uncovered else "MISS"
        print(f"  [{covered}] {path} -> {route}")

    # Codex iter-4 P1 fix: broad changes (components, layouts,
    # templates, loading/error/not-found) require a CONSERVATIVE
    # full-route sweep. The manifest must cover every page.tsx route
    # discovered in the repo. This closes the bypass where a
    # `web/components/proof_replay/proof_replay.tsx` change could be
    # audited against an unrelated route like `/intake`.
    full_sweep_missing: list[str] = []
    if broad_changes:
        print(f"Broad UI changes (component / layout / template / loading / error / not-found): {len(broad_changes)}")
        for c in broad_changes:
            print(f"  {c}")
        repo_root = Path(args.repo_root).resolve()
        all_routes = discover_all_app_routes(repo_root)
        print(f"All page.tsx routes discovered in repo: {len(all_routes)}")
        for r in all_routes:
            covered_in_manifest = matches_manifest_route(r, manifest_routes)
            marker = "OK" if covered_in_manifest else "MISS"
            print(f"  [{marker}] {r}")
            if not covered_in_manifest:
                full_sweep_missing.append(r)

    if uncovered:
        print("ERROR: route coverage missing — these page changes are not in the manifest:")
        for path, route in uncovered:
            print(f"  {path} -> {route}")
        return 1

    if full_sweep_missing:
        print(
            "ERROR: broad UI changes (components / layouts / etc) require a"
            " FULL-ROUTE SWEEP. These page.tsx routes exist in the repo but"
            " are NOT in the manifest:"
        )
        for r in full_sweep_missing:
            print(f"  {r}")
        print(
            "Re-run scripts/visual_review_gate.py with --routes covering"
            " every discovered route, OR scope the PR to a single page so"
            " per-page coverage applies."
        )
        return 1

    print("OK: every changed page.tsx route is covered; broad changes (if any) have full-route sweep")
    return 0


if __name__ == "__main__":
    sys.exit(main())
