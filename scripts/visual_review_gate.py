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
- Halt: returns non-zero exit code if any route fails the 14/16 threshold
  AND iter < 5; force-APPROVE at iter 5 per CLAUDE.md §8.3.1.

Why this lives OUTSIDE the writer agent's reasoning loop:
- The script's loop condition is the YAML pass_count, not the writer's
  judgment. The writer cannot "decide it's good enough" and skip the
  validator — the next-iter trigger is mechanical.
- The CI workflow `codex-visual-required` runs this script on the PR
  branch deterministically. The writer cannot bypass by editing prompts.
- Combined with codex-required.yml's `canonical-diff-sha256` binding,
  the visual gate cannot be approved on a different page than the one
  in the PR.

Usage:
    python scripts/visual_review_gate.py \\
        --issue-id I-ux-002 \\
        --routes /inspector/test-run-001,/intake,/plan,/dashboard \\
        --base-url http://127.0.0.1:3000 \\
        --max-iter 5

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
HARD_ITER_CAP = 5  # CLAUDE.md §8.3.1
RUBRIC_PATH = PROJECT_ROOT / ".codex" / "visual_audit_rubric.md"

# Final verdict regex matches the codex-required.yml convention:
# the LAST line of the form `verdict: APPROVE|REQUEST_CHANGES` is
# authoritative (PRD2-P1-001 hardening).
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
    output_path: Path

    @property
    def label(self) -> str:
        w, h = self.viewport
        # Stable slug; safe on Windows + Linux.
        safe_route = re.sub(r"[^a-zA-Z0-9]+", "_", self.route).strip("_") or "root"
        return f"{safe_route}_{w}x{h}"


@dataclass
class CodexVerdict:
    raw: str
    verdict: str | None = None
    pass_count: int | None = None
    rubric_sha256_declared: str | None = None
    screenshot_sha256_declared: str | None = None

    @classmethod
    def parse(cls, raw: str) -> "CodexVerdict":
        v = cls(raw=raw)
        m = FINAL_VERDICT_RE.findall(raw)
        v.verdict = m[-1] if m else None
        m = PASS_COUNT_RE.findall(raw)
        v.pass_count = int(m[-1]) if m else None
        m = RUBRIC_SHA_RE.findall(raw)
        v.rubric_sha256_declared = m[-1] if m else None
        m = SCREENSHOT_SHA_RE.findall(raw)
        v.screenshot_sha256_declared = m[-1] if m else None
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


# ---------------------------------------------------------------------------
# Screenshot pass (Playwright async)
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
                    job = ScreenshotJob(
                        route=route,
                        viewport=vw,
                        output_path=outdir / f"{ScreenshotJob(route, vw, Path()).label}.png",
                    )
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
                    # Force layout settle for any motion / shimmer.
                    await page.wait_for_timeout(500)
                    await page.screenshot(
                        path=str(job.output_path),
                        full_page=True,
                        animations="disabled",
                    )
                    jobs.append(job)
                    await context.close()
        finally:
            await browser.close()
    return jobs


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
2. Count PASS scores into `pass_count` (0..16). Threshold = 14.
3. Emit ONLY the YAML block specified in the rubric — no surrounding
   prose. The harness parses the LAST `verdict:` line as authoritative.
4. `rubric_sha256` MUST equal `{rubric_sha}` (the gate enforces this).
5. `screenshot_sha256` MUST equal `{screenshot_sha}` (the gate enforces this).
6. PARTIAL counts as NOT PASS for `pass_count`.

Begin YAML now:
""")


def run_codex_audit(job: ScreenshotJob, iter_n: int, rubric_sha: str, rubric_body: str) -> CodexVerdict:
    screenshot_sha = sha256_file(job.output_path)
    prompt = PROMPT_TEMPLATE.format(
        iter_n=iter_n,
        route=job.route,
        viewport_w=job.viewport[0],
        viewport_h=job.viewport[1],
        rubric_sha=rubric_sha,
        rubric_body=rubric_body,
        screenshot_sha=screenshot_sha,
    )
    # Mirror existing brief-review env: unset OPENAI_API_KEY to force OAuth.
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
        timeout=540,  # 9 min cap per §8.4 single-codex-at-a-time
        check=False,
    )
    if proc.returncode != 0:
        print(f"  codex stderr: {proc.stderr[:500]}", flush=True)
    raw = proc.stdout
    return CodexVerdict.parse(raw)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def emit_verdict_file(
    issue_id: str,
    iter_n: int,
    iter_result: IterResult,
    force_approved: bool,
) -> Path:
    target = PROJECT_ROOT / ".codex" / issue_id / "codex_visual_audit.txt"
    target.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# POLARIS visual gate — issue {issue_id}, iter {iter_n}")
    lines.append(f"# rubric: .codex/visual_audit_rubric.md")
    lines.append(f"# threshold: {PASS_THRESHOLD}/16 per route+viewport")
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
        "--max-iter",
        type=int,
        default=HARD_ITER_CAP,
        help="Iteration cap (default 5 per CLAUDE.md §8.3.1)",
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
    return p.parse_args()


def main() -> int:
    args = parse_args()

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

    screenshots_root = Path(args.screenshots_dir) / args.issue_id
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

    final_force_approved = False
    final_iter_result: IterResult | None = None

    for iter_n in range(1, args.max_iter + 1):
        iter_dir = screenshots_root / f"iter_{iter_n}"
        iter_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n=== iter {iter_n}/{args.max_iter} ===", flush=True)
        jobs = asyncio.run(
            capture_screenshots(routes, args.base_url, viewports, iter_dir)
        )

        if args.no_codex:
            print(
                f"--no-codex set; captured {len(jobs)} screenshots. Exiting iter loop.",
                flush=True,
            )
            return 0

        per_job: dict[str, CodexVerdict] = {}
        for job in jobs:
            verdict = run_codex_audit(job, iter_n, rubric_sha, rubric_body)
            per_job[job.label] = verdict

            # Cross-check rubric_sha + screenshot_sha — reviewer drift defense.
            if verdict.rubric_sha256_declared and verdict.rubric_sha256_declared != rubric_sha:
                print(
                    f"  WARN: rubric_sha drift on {job.label}: "
                    f"declared={verdict.rubric_sha256_declared} actual={rubric_sha}",
                    flush=True,
                )
            actual_screenshot_sha = sha256_file(job.output_path)
            if (
                verdict.screenshot_sha256_declared
                and verdict.screenshot_sha256_declared != actual_screenshot_sha
            ):
                print(
                    f"  WARN: screenshot_sha drift on {job.label}",
                    flush=True,
                )

            print(
                f"  {job.label}: verdict={verdict.verdict} pass_count={verdict.pass_count}",
                flush=True,
            )

        pass_counts = [v.pass_count for v in per_job.values() if v.pass_count is not None]
        min_pc = min(pass_counts) if pass_counts else None
        all_approve = all(v.is_approve() and (v.pass_count or 0) >= PASS_THRESHOLD for v in per_job.values())

        iter_result = IterResult(
            iter_n=iter_n,
            per_job=per_job,
            all_approve=all_approve,
            min_pass_count=min_pc,
        )
        final_iter_result = iter_result

        if all_approve:
            emit_verdict_file(args.issue_id, iter_n, iter_result, force_approved=False)
            print(f"\nAll routes APPROVE at iter {iter_n}. min_pass_count={min_pc}.")
            return 0

        if iter_n == args.max_iter:
            # §8.3.1 force-approve: emit APPROVE artifact AND annotation file.
            final_force_approved = True
            emit_verdict_file(args.issue_id, iter_n, iter_result, force_approved=True)
            annot = PROJECT_ROOT / ".codex" / args.issue_id / "codex_visual_audit_iter5_force_approve.txt"
            annot.parent.mkdir(parents=True, exist_ok=True)
            annot.write_text(
                json.dumps(
                    {
                        "issue_id": args.issue_id,
                        "force_approved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "cap_iter": args.max_iter,
                        "min_pass_count_at_cap": min_pc,
                        "rubric_sha256": rubric_sha,
                        "residual_jobs": [
                            label
                            for label, v in per_job.items()
                            if not (v.is_approve() and (v.pass_count or 0) >= PASS_THRESHOLD)
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

        emit_verdict_file(args.issue_id, iter_n, iter_result, force_approved=False)
        print(
            f"\niter {iter_n} REQUEST_CHANGES. min_pass_count={min_pc}. "
            f"Writer must address findings; re-run loop.",
            flush=True,
        )
        # Hand control back so writer can edit code; CI calls this script
        # again on the next push. Locally, this exit triggers the writer.
        return 1

    # unreachable; kept for type-checker happiness
    return 0


if __name__ == "__main__":
    sys.exit(main())
