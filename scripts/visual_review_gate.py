"""
visual_review_gate.py — UI harness Action Authorization Boundary.

Implements the AAB pattern (Faramesh arxiv 2601.17744) + Ralph-Wiggum
loop (Vercel 2025) + Visual Validator Tool (Anthropic harness 2025) for
POLARIS v6 UI PRs.

Contract:
- Input:  PR head branch with v6 UI changes; routes-under-test list.
- Output: `.codex/<issue_id>/codex_visual_audit.txt` with machine-parseable
  YAML per `.codex/visual_audit_rubric.md`. Final `verdict: APPROVE` line
  is what the codex-visual-required CI gate parses (last-match wins, per
  the PR-D iter-2 hardening pattern already used by codex-required.yml).
- State: persisted per-Issue at `.codex/<issue_id>/visual_iter_state.json`
  so the iter counter survives across writer edits. Force-APPROVE fires
  ONLY when state.iter == 5 — `--max-iter` is informational, never an
  early-force lever (P0-iter1 fix: bind force-APPROVE to absolute iter 5
  not to user-supplied flag).
- Halt: returns non-zero exit code if any route fails the 14/16 threshold
  AND iter < 5; force-APPROVE at exact iter 5 per CLAUDE.md §8.3.1.

Why this lives OUTSIDE the writer agent's reasoning loop:
- The script's loop condition is the YAML pass_count, not the writer's
  judgment. The writer cannot "decide it's good enough" and skip the
  validator — the next-iter trigger is mechanical.
- The CI workflow `codex-visual-required` runs this script on the PR
  branch deterministically. The writer cannot bypass by editing prompts.
- Combined with codex-required.yml's `canonical-diff-sha256` binding,
  the visual gate cannot be approved on a different page than the one
  in the PR. The audit declares `pr_head_sha` + `screenshots_manifest_sha256`
  which CI cross-binds.

Usage:
    python scripts/visual_review_gate.py \\
        --issue-id I-ux-002 \\
        --routes /inspector/test-run-001,/intake,/plan,/dashboard \\
        --base-url http://127.0.0.1:3000

Environment:
    NEXT_PROD_BASE_URL  — defaults to http://127.0.0.1:3000; the script
                          does NOT start the server (the caller does;
                          must be `next start` of a production build,
                          NOT `next dev`, because Playwright Chromium
                          on Windows fails dev-mode WS handshake).
    PG_VISUAL_GATE_VIEWPORTS — comma list of WxH (default
                          1440x900,768x1024,390x844).
    CODEX_BIN           — defaults to `codex` on PATH.

This script is intentionally Pythonic (cross-platform) — `subprocess`
calls into `codex exec` mirror the existing brief-review workflow
(env -u OPENAI_API_KEY codex exec --skip-git-repo-check -i <png>).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Project root + config
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_VIEWPORTS = "1440x900,768x1024,390x844"
DEFAULT_BASE_URL = "http://127.0.0.1:3000"
PASS_THRESHOLD = 14  # of 16 per .codex/visual_audit_rubric.md
HARD_ITER_CAP = 5  # CLAUDE.md §8.3.1 — ABSOLUTE; not user-tunable below.
RUBRIC_PATH = PROJECT_ROOT / ".codex" / "visual_audit_rubric.md"

# Per-PR audit artifact carries cross-binding declarations so the CI
# gate can verify the audit was performed against this PR's actual
# rendered evidence (not a stale prior audit). The gate cross-checks:
#   - rubric_sha256: matches working-tree .codex/visual_audit_rubric.md
#   - pr_head_sha: matches GITHUB_SHA / current HEAD
#   - screenshots_manifest_sha256: matches sha256 of the screenshot inventory
# (P0-iter1 fix.)

FINAL_VERDICT_RE = re.compile(
    r"^verdict:\s+(APPROVE|REQUEST_CHANGES)\s*$", re.MULTILINE
)
PASS_COUNT_RE = re.compile(r"^pass_count:\s+(\d+)\s*$", re.MULTILINE)
RUBRIC_SHA_RE = re.compile(r"^rubric_sha256:\s+([a-f0-9]{64})\s*$", re.MULTILINE)
SCREENSHOT_SHA_RE = re.compile(
    r"^screenshot_sha256:\s+([a-f0-9]{64})\s*$", re.MULTILINE
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ScreenshotJob:
    route: str
    viewport: tuple[int, int]
    state: str  # "static", "focused", or "hovered"
    output_path: Path

    @property
    def label(self) -> str:
        w, h = self.viewport
        safe_route = re.sub(r"[^a-zA-Z0-9]+", "_", self.route).strip("_") or "root"
        return f"{safe_route}_{w}x{h}_{self.state}"


class CodexOutputError(RuntimeError):
    """Raised when Codex returns malformed or incomplete YAML.

    Codex diff-iter-1 P1 fix: invalid Codex output must NOT silently
    advance the iter counter and reach iter-5 force-APPROVE. Hard error
    instead. The harness fails closed; the writer must re-run.
    """


@dataclass
class CodexVerdict:
    raw: str
    verdict: str | None = None
    pass_count: int | None = None
    rubric_sha256_declared: str | None = None
    screenshot_sha256_declared: str | None = None

    @classmethod
    def parse(cls, raw: str, label: str = "<unknown>") -> "CodexVerdict":
        """Strict parser. Raises CodexOutputError on any missing field
        or out-of-range value. Iter-state save sites MUST catch and
        treat as hard harness failure, not as REQUEST_CHANGES.
        """
        v = cls(raw=raw)
        m = FINAL_VERDICT_RE.findall(raw)
        v.verdict = m[-1] if m else None
        if v.verdict not in ("APPROVE", "REQUEST_CHANGES"):
            raise CodexOutputError(
                f"{label}: missing or invalid `verdict:` line "
                f"(got {v.verdict!r}); Codex returned malformed output"
            )

        m = PASS_COUNT_RE.findall(raw)
        v.pass_count = int(m[-1]) if m else None
        if v.pass_count is None:
            raise CodexOutputError(
                f"{label}: missing `pass_count:` line"
            )
        if not (0 <= v.pass_count <= 16):
            raise CodexOutputError(
                f"{label}: pass_count={v.pass_count} out of range 0..16"
            )

        m = RUBRIC_SHA_RE.findall(raw)
        v.rubric_sha256_declared = m[-1] if m else None
        if not v.rubric_sha256_declared:
            raise CodexOutputError(
                f"{label}: missing `rubric_sha256:` declaration"
            )

        m = SCREENSHOT_SHA_RE.findall(raw)
        v.screenshot_sha256_declared = m[-1] if m else None
        if not v.screenshot_sha256_declared:
            raise CodexOutputError(
                f"{label}: missing `screenshot_sha256:` declaration"
            )

        return v

    def is_approve(self) -> bool:
        return self.verdict == "APPROVE"


@dataclass
class IterResult:
    iter_n: int
    per_job: dict[str, CodexVerdict] = field(default_factory=dict)
    all_approve: bool = False
    min_pass_count: int | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def codex_bin() -> str:
    return os.getenv("CODEX_BIN", "codex")


def viewport_list() -> list[tuple[int, int]]:
    raw = os.getenv("PG_VISUAL_GATE_VIEWPORTS", DEFAULT_VIEWPORTS)
    out = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        w, h = token.lower().split("x")
        out.append((int(w), int(h)))
    if not out:
        raise SystemExit("PG_VISUAL_GATE_VIEWPORTS produced empty viewport list")
    return out


def ui_surface_tree_sha() -> str:
    """Compute a stable hash of the UI surface tracked by the gate.

    Codex diff-iter-1 P0 fix: the previous design recorded
    `pr_head_sha = git rev-parse HEAD` in the audit. But the audit
    file must then be COMMITTED, which changes HEAD, and the CI gate
    compared declared `pr_head_sha` to `github.event.pull_request.head.sha`
    — an impossible fixed point.

    The fix: bind the audit to the UI surface CONTENT (web/app/** +
    web/components/**), not the commit identity. This hash is invariant
    across the audit-commit step because the audit-commit does not touch
    those paths.

    Implementation is delegated to `scripts/compute_ui_surface_sha.py`
    so the script and the CI workflow share one source of truth for
    the algorithm.
    """
    # Local import to avoid cycle at module load if compute_ui_surface_sha
    # is itself being introspected.
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    try:
        import compute_ui_surface_sha  # type: ignore
        return compute_ui_surface_sha.compute(PROJECT_ROOT)
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------------------
# Persisted iter state — survives writer edits between invocations.
# (P0-iter1 fix: 5-iter cap is absolute; force-APPROVE only at iter 5.)
# ---------------------------------------------------------------------------
def iter_state_path(issue_id: str) -> Path:
    return PROJECT_ROOT / ".codex" / issue_id / "visual_iter_state.json"


def load_iter_state(issue_id: str) -> dict[str, Any]:
    p = iter_state_path(issue_id)
    if not p.exists():
        return {"iter": 0, "last_verdict": None, "history": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_iter_state(issue_id: str, state: dict[str, Any]) -> None:
    p = iter_state_path(issue_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


def reset_iter_state(issue_id: str) -> None:
    p = iter_state_path(issue_id)
    if p.exists():
        p.unlink()


# ---------------------------------------------------------------------------
# Screenshot pass (Playwright async)
# Captures THREE states per route+viewport so the rubric's interaction
# dimensions (13 motion, 14 keyboard/focus, partially 16 liveliness) are
# observable from the harness inputs:
#   - static   : page as-loaded, animations disabled
#   - focused  : first interactive given keyboard focus (Tab)
#   - hovered  : first interactive given mouse hover
# (P1-iter1 fix: rubric dim 13/14/16 evidence path.)
# ---------------------------------------------------------------------------
async def capture_screenshots(
    routes: list[str],
    base_url: str,
    viewports: list[tuple[int, int]],
    outdir: Path,
) -> list[ScreenshotJob]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SystemExit(
            "playwright not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    outdir.mkdir(parents=True, exist_ok=True)
    jobs: list[ScreenshotJob] = []

    async with async_playwright() as pw:
        # Production build only — Chromium dev-mode WS handshake fails on
        # Windows per `feedback_*` notes. Caller starts `next start`.
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        try:
            for route in routes:
                for vw in viewports:
                    context = await browser.new_context(
                        viewport={"width": vw[0], "height": vw[1]},
                        device_scale_factor=2,
                    )
                    page = await context.new_page()
                    url = base_url.rstrip("/") + route
                    print(f"[shot] {url} @ {vw[0]}x{vw[1]}", flush=True)
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=30_000)
                    except Exception as exc:
                        print(f"  WARN: navigation failed: {exc}", flush=True)
                    await page.wait_for_timeout(500)

                    # static
                    static_job = ScreenshotJob(
                        route=route,
                        viewport=vw,
                        state="static",
                        output_path=outdir / "",
                    )
                    static_job.output_path = outdir / f"{static_job.label}.png"
                    await page.screenshot(
                        path=str(static_job.output_path),
                        full_page=True,
                        animations="disabled",
                    )
                    jobs.append(static_job)

                    # focused — Tab to first interactive, screenshot focus ring
                    try:
                        await page.keyboard.press("Tab")
                        await page.wait_for_timeout(150)
                    except Exception as exc:
                        print(f"  WARN: focus pass failed: {exc}", flush=True)
                    focused_job = ScreenshotJob(
                        route=route,
                        viewport=vw,
                        state="focused",
                        output_path=outdir / "",
                    )
                    focused_job.output_path = outdir / f"{focused_job.label}.png"
                    await page.screenshot(
                        path=str(focused_job.output_path),
                        full_page=False,  # viewport only — focus ring is in viewport
                    )
                    jobs.append(focused_job)

                    # hovered — hover first link/button if present, screenshot
                    try:
                        candidate = page.locator("a, button").first
                        if await candidate.count() > 0:
                            await candidate.hover(timeout=2_000)
                            await page.wait_for_timeout(150)
                    except Exception as exc:
                        print(f"  WARN: hover pass failed: {exc}", flush=True)
                    hovered_job = ScreenshotJob(
                        route=route,
                        viewport=vw,
                        state="hovered",
                        output_path=outdir / "",
                    )
                    hovered_job.output_path = outdir / f"{hovered_job.label}.png"
                    await page.screenshot(
                        path=str(hovered_job.output_path),
                        full_page=False,
                    )
                    jobs.append(hovered_job)

                    await context.close()
        finally:
            await browser.close()
    return jobs


def build_screenshots_manifest(jobs: list[ScreenshotJob]) -> str:
    """Deterministic JSON inventory of captured screenshots.

    Lists each screenshot with its content SHA256. The audit declares
    a single `screenshots_manifest_sha256:` line; the CI gate verifies
    that hash matches the screenshots directory currently in the PR.
    (P0-iter1 fix: bind audit to actual rendered evidence.)
    """
    entries = []
    for job in sorted(jobs, key=lambda j: j.label):
        entries.append(
            {
                "label": job.label,
                "route": job.route,
                "viewport": list(job.viewport),
                "state": job.state,
                "sha256": sha256_file(job.output_path),
            }
        )
    return json.dumps(entries, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Codex visual-audit call
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = textwrap.dedent("""\
HARD ITERATION CAP: 5 per document. This is iter {iter_n} of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

TASK
====

You are reviewing a screenshot of a POLARIS v6 UI route against the
locked 16-dimension visual rubric.

ROUTE        : {route}
VIEWPORT     : {viewport_w}x{viewport_h}
STATE        : {state}   # static / focused / hovered
SCREENSHOT   : attached via -i flag
RUBRIC PATH  : .codex/visual_audit_rubric.md
RUBRIC SHA   : {rubric_sha}
SCREENSHOT SHA: {screenshot_sha}

RUBRIC (verbatim, do NOT paraphrase dimension labels):

{rubric_body}

INSTRUCTIONS
============

1. Score each of the 16 dimensions PASS / PARTIAL / FAIL with ONE
   sentence of evidence quoting the pixel region or visible token.
2. For "focused" screenshots, weight dim 14 (keyboard+focus) primary
   evidence. For "hovered" screenshots, weight dim 13 (motion). For
   "static" screenshots, weight dims 1–12.
3. Count PASS scores into `pass_count` (0..16). Threshold = 14.
4. Emit ONLY the YAML block specified in the rubric — no surrounding
   prose. The harness parses the LAST `verdict:` line as authoritative.
5. `rubric_sha256` MUST equal `{rubric_sha}` (the gate enforces this).
6. `screenshot_sha256` MUST equal `{screenshot_sha}` (the gate enforces this).
7. PARTIAL counts as NOT PASS for `pass_count`.

Begin YAML now:
""")


def run_codex_audit(
    job: ScreenshotJob, iter_n: int, rubric_sha: str, rubric_body: str
) -> CodexVerdict:
    screenshot_sha = sha256_file(job.output_path)
    prompt = PROMPT_TEMPLATE.format(
        iter_n=iter_n,
        route=job.route,
        viewport_w=job.viewport[0],
        viewport_h=job.viewport[1],
        state=job.state,
        rubric_sha=rubric_sha,
        rubric_body=rubric_body,
        screenshot_sha=screenshot_sha,
    )
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    cmd = [
        codex_bin(),
        "exec",
        "--skip-git-repo-check",
        "-i",
        str(job.output_path),
        "-",
    ]
    print(f"[codex] iter={iter_n} {job.label}", flush=True)
    proc = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        env=env,
        timeout=540,
        check=False,
    )
    if proc.returncode != 0:
        print(f"  codex stderr: {proc.stderr[:500]}", flush=True)
    # Strict parse — raises CodexOutputError on malformed output. The
    # caller does NOT catch + treat as REQUEST_CHANGES; it propagates
    # to main() which exits without advancing iter state.
    return CodexVerdict.parse(proc.stdout, label=job.label)


# ---------------------------------------------------------------------------
# Audit artifact emission
# ---------------------------------------------------------------------------
def emit_verdict_file(
    issue_id: str,
    iter_n: int,
    iter_result: IterResult,
    rubric_sha: str,
    ui_surface_tree_sha256: str,
    screenshots_manifest_sha: str,
    force_approved: bool,
) -> Path:
    target = PROJECT_ROOT / ".codex" / issue_id / "codex_visual_audit.txt"
    target.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# POLARIS visual gate — issue {issue_id}, iter {iter_n}")
    lines.append(f"# rubric: .codex/visual_audit_rubric.md")
    lines.append(f"# threshold: {PASS_THRESHOLD}/16 per route+viewport+state")
    lines.append("")
    # Audit-to-PR cross-binding declarations — CI gate verifies each.
    lines.append(f"rubric_sha256: {rubric_sha}")
    lines.append(f"ui_surface_tree_sha256: {ui_surface_tree_sha256}")
    lines.append(f"screenshots_manifest_sha256: {screenshots_manifest_sha}")
    lines.append("")
    for label, v in iter_result.per_job.items():
        lines.append(f"## {label}")
        lines.append(v.raw.strip())
        lines.append("")
    lines.append("# ---- aggregate ----")
    lines.append(f"iter: {iter_n}")
    lines.append(f"min_pass_count: {iter_result.min_pass_count}")
    lines.append(f"all_approve: {iter_result.all_approve}")
    if force_approved:
        lines.append(
            f"# force-approved at iter {iter_n} cap per CLAUDE.md §8.3.1"
        )
        lines.append("verdict: APPROVE")
    elif iter_result.all_approve:
        lines.append("verdict: APPROVE")
    else:
        lines.append("verdict: REQUEST_CHANGES")
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--issue-id", required=True, help="GitHub issue id, e.g. I-ux-002")
    p.add_argument(
        "--routes",
        required=True,
        help="Comma-separated routes under audit, e.g. /inspector/r1,/intake",
    )
    p.add_argument(
        "--base-url",
        default=os.getenv("NEXT_PROD_BASE_URL", DEFAULT_BASE_URL),
        help="Where `next start` is listening",
    )
    p.add_argument(
        "--screenshots-dir",
        default=str(PROJECT_ROOT / "outputs" / "visual_review_gate"),
        help="Where screenshots are written",
    )
    p.add_argument(
        "--no-codex",
        action="store_true",
        help="Skip Codex calls; emit screenshots only (smoke test mode)",
    )
    p.add_argument(
        "--reset-state",
        action="store_true",
        help="Reset .codex/<id>/visual_iter_state.json (use only when starting a new Issue)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.reset_state:
        reset_iter_state(args.issue_id)
        print(f"reset visual_iter_state.json for {args.issue_id}")

    if not RUBRIC_PATH.exists():
        print(f"ERROR: rubric not found at {RUBRIC_PATH}", file=sys.stderr)
        return 2
    rubric_body = RUBRIC_PATH.read_text(encoding="utf-8")
    rubric_sha = sha256_text(rubric_body)
    print(f"rubric_sha256: {rubric_sha}", flush=True)

    routes = [r.strip() for r in args.routes.split(",") if r.strip()]
    if not routes:
        print("ERROR: --routes is empty", file=sys.stderr)
        return 2

    viewports = viewport_list()
    print(f"viewports: {viewports}", flush=True)

    # Persisted state — the absolute 5-iter cap lives here. (P0 fix.)
    # Iter counter is INCREMENTED-AND-SAVED only AFTER a successful
    # Codex iteration (P1 from diff iter-1): malformed Codex output
    # MUST NOT advance the iter counter, otherwise repeated garbage
    # responses reach iter-5 force-APPROVE without a single valid
    # review.
    state = load_iter_state(args.issue_id)
    iter_n = state.get("iter", 0) + 1  # tentative — saved only on success
    if iter_n > HARD_ITER_CAP:
        # Already force-approved on a prior call; the audit file should
        # exist. Re-running is a no-op.
        print(
            f"iter {iter_n} > HARD_ITER_CAP={HARD_ITER_CAP}; "
            f"force-APPROVE has already fired. Use --reset-state to start over.",
            flush=True,
        )
        return 0
    print(f"\n=== iter {iter_n}/{HARD_ITER_CAP} (tentative; saved on success) ===", flush=True)

    ui_surface_tree_sha256 = ui_surface_tree_sha()
    print(f"ui_surface_tree_sha256: {ui_surface_tree_sha256}", flush=True)

    screenshots_root = Path(args.screenshots_dir) / args.issue_id / f"iter_{iter_n}"
    if screenshots_root.exists():
        shutil.rmtree(screenshots_root)
    screenshots_root.mkdir(parents=True, exist_ok=True)

    if not shutil.which(codex_bin()) and not args.no_codex:
        print(
            f"ERROR: codex CLI not on PATH (`{codex_bin()}`). Install per "
            "https://platform.openai.com/docs/codex/overview, or pass --no-codex",
            file=sys.stderr,
        )
        return 2

    jobs = asyncio.run(
        capture_screenshots(routes, args.base_url, viewports, screenshots_root)
    )

    manifest_text = build_screenshots_manifest(jobs)
    manifest_path = screenshots_root / "manifest.json"
    manifest_path.write_text(manifest_text, encoding="utf-8")
    screenshots_manifest_sha = sha256_text(manifest_text)
    print(f"screenshots_manifest_sha256: {screenshots_manifest_sha}", flush=True)

    if args.no_codex:
        print(
            f"--no-codex set; captured {len(jobs)} screenshots. Exiting.",
            flush=True,
        )
        # Don't advance iter state — no codex review happened.
        return 0

    per_job: dict[str, CodexVerdict] = {}
    try:
        for job in jobs:
            # Strict parse: raises CodexOutputError on malformed YAML.
            verdict = run_codex_audit(job, iter_n, rubric_sha, rubric_body)
            per_job[job.label] = verdict

            # Cross-check rubric_sha + screenshot_sha — fail closed on drift.
            # (P2-iter1 fix.) Strict parser already enforced presence;
            # we now enforce VALUE match.
            if verdict.rubric_sha256_declared != rubric_sha:
                print(
                    f"  ERROR: rubric_sha drift on {job.label}: "
                    f"declared={verdict.rubric_sha256_declared} actual={rubric_sha}",
                    flush=True,
                )
                # Don't advance iter state on hard drift.
                return 3
            actual_screenshot_sha = sha256_file(job.output_path)
            if verdict.screenshot_sha256_declared != actual_screenshot_sha:
                print(
                    f"  ERROR: screenshot_sha drift on {job.label}: "
                    f"declared={verdict.screenshot_sha256_declared} actual={actual_screenshot_sha}",
                    flush=True,
                )
                return 3

            print(
                f"  {job.label}: verdict={verdict.verdict} pass_count={verdict.pass_count}",
                flush=True,
            )
    except CodexOutputError as exc:
        # P1-diff-iter1 fix: malformed Codex output is a HARD harness
        # failure. The iter counter does NOT advance. Writer re-runs
        # the script, which will retry the same iter (not the next).
        print(f"ERROR: Codex returned malformed output — {exc}", file=sys.stderr)
        print(
            f"Iter state NOT advanced; current iter remains {state.get('iter', 0)}.",
            file=sys.stderr,
        )
        return 4

    # All jobs parsed successfully — NOW it is safe to advance iter
    # state. (P1-diff-iter1 fix.)
    state["iter"] = iter_n

    pass_counts = [v.pass_count for v in per_job.values() if v.pass_count is not None]
    min_pc = min(pass_counts) if pass_counts else None
    all_approve = all(
        v.is_approve() and (v.pass_count or 0) >= PASS_THRESHOLD
        for v in per_job.values()
    )

    iter_result = IterResult(
        iter_n=iter_n,
        per_job=per_job,
        all_approve=all_approve,
        min_pass_count=min_pc,
    )

    # Persist state with this iter's outcome before deciding final action.
    state["last_verdict"] = "APPROVE" if all_approve else "REQUEST_CHANGES"
    state["history"].append(
        {
            "iter": iter_n,
            "min_pass_count": min_pc,
            "verdict": state["last_verdict"],
            "ui_surface_tree_sha256": ui_surface_tree_sha256,
            "rubric_sha256": rubric_sha,
            "screenshots_manifest_sha256": screenshots_manifest_sha,
        }
    )
    save_iter_state(args.issue_id, state)

    if all_approve:
        emit_verdict_file(
            args.issue_id,
            iter_n,
            iter_result,
            rubric_sha,
            ui_surface_tree_sha256,
            screenshots_manifest_sha,
            force_approved=False,
        )
        print(f"\nAll routes APPROVE at iter {iter_n}. min_pass_count={min_pc}.")
        return 0

    if iter_n == HARD_ITER_CAP:
        # Absolute iter-5 force-APPROVE per §8.3.1.
        emit_verdict_file(
            args.issue_id,
            iter_n,
            iter_result,
            rubric_sha,
            ui_surface_tree_sha256,
            screenshots_manifest_sha,
            force_approved=True,
        )
        annot = (
            PROJECT_ROOT
            / ".codex"
            / args.issue_id
            / "codex_visual_audit_iter5_force_approve.txt"
        )
        annot.parent.mkdir(parents=True, exist_ok=True)
        annot.write_text(
            json.dumps(
                {
                    "issue_id": args.issue_id,
                    "force_approved_utc": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                    "cap_iter": HARD_ITER_CAP,
                    "min_pass_count_at_cap": min_pc,
                    "rubric_sha256": rubric_sha,
                    "ui_surface_tree_sha256": ui_surface_tree_sha256,
                    "screenshots_manifest_sha256": screenshots_manifest_sha,
                    "residual_jobs": [
                        label
                        for label, v in per_job.items()
                        if not (
                            v.is_approve() and (v.pass_count or 0) >= PASS_THRESHOLD
                        )
                    ],
                    "directive": "CLAUDE.md §8.3.1 force-APPROVE at iter-5 cap",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            f"\nForce-APPROVE at iter {iter_n}. min_pass_count={min_pc}. "
            f"Annotation: {annot}",
            flush=True,
        )
        return 0

    emit_verdict_file(
        args.issue_id,
        iter_n,
        iter_result,
        rubric_sha,
        ui_surface_tree_sha256,
        screenshots_manifest_sha,
        force_approved=False,
    )
    print(
        f"\niter {iter_n}/{HARD_ITER_CAP} REQUEST_CHANGES. min_pass_count={min_pc}. "
        f"Writer must address findings; re-run script to advance to iter {iter_n + 1}.",
        flush=True,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
