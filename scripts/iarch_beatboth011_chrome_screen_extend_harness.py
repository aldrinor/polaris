#!/usr/bin/env python3
"""FAIL-LOUD offline harness for the I-beatboth-011 b2 chrome-screen extension (#1289).

Acceptance (§-1.4 behavioral, not diff-approval): the NEW leaked chrome classes
seen VERBATIM in outputs/p6_postfix_resume/workforce/drb_72_ai_labor/report.md must
now be screened, AND real economics sentences (incl. adversarial near-misses that
share tokens with each new pattern) must STILL pass un-screened. Any regression =>
sys.exit(1) with a loud message. sys.exit(0) only if every assertion holds.

Two mechanisms, routed correctly (the advisor's framing):
  • INLINE chrome (collapsed mid-body, real prose around it) -> clean_fetch_body():
    assert the chrome token is gone from cleaned_text AND adjacent real prose survives.
  • WHOLE-UNIT chrome (the line/unit IS the chrome) -> is_boilerplate_or_nonassertional()
    returns True; for the negatives it returns False.

Importing the module IS the real regex compile-check — a malformed alternation passes
ast.parse (it is a string) but raises re.error at re.compile on import.
"""

import os
import sys

# Make the repo root importable regardless of CWD (LAW VI: no hard-coded abs path).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Import is the compile-check: a bad alternation raises re.error here.
from src.tools.access_bypass import (  # noqa: E402
    clean_fetch_body,
    is_boilerplate_or_nonassertional,
)

FAILURES: "list[str]" = []


def _fail(msg: str) -> None:
    FAILURES.append(msg)


# ── (a) NEW inline chrome classes: must be REMOVED from the body, prose preserved ──
# Each case: (label, body_with_chrome, chrome_substring_that_must_vanish,
#            real_prose_that_must_survive)
INLINE_CASES = [
    (
        "JEP masthead (full)",
        "Economic Perspectives—Volume 33, Number 2—Spring 2019 The implications "
        "of technological change for employment are substantial.",
        "Number 2",
        "The implications of technological change for employment are substantial.",
    ),
    (
        "JEP masthead (truncated 'onomic')",
        "onomic Perspectives—Volume 33, Number 2—Spring 2019—Pages 3-30 "
        "Automation displaced routine clerical work over the decade.",
        "Perspectives—Volume",
        "Automation displaced routine clerical work over the decade.",
    ),
    (
        "ResearchGate CITATIONS/READS",
        "CITATIONS 12 READS 345 Productivity growth slowed after 2005 in advanced economies.",
        "READS 345",
        "Productivity growth slowed after 2005 in advanced economies.",
    ),
    (
        "ResearchGate authors-including",
        "9 authors, including: The study estimates exposure for 702 occupations.",
        "authors, including",
        "The study estimates exposure for 702 occupations.",
    ),
    (
        "Crossref citing nav",
        "Crossref reports the following articles citing this paper. Wages diverged across skill groups.",
        "Crossref reports the following",
        "Wages diverged across skill groups.",
    ),
    (
        "markdown Twitter share button",
        "[ Twitter ](https://twitter.com/intent/tweet?url=https%3A) We analyze worker-level "
        "microdata from two advanced economies.",
        "Twitter",
        "We analyze worker-level microdata from two advanced economies.",
    ),
    (
        "twitter intent share URL",
        "share via https://twitter.com/intent/tweet?url=x The displacement effect dominates in manufacturing.",
        "twitter.com/intent",
        "The displacement effect dominates in manufacturing.",
    ),
    # NOTE (b2-fix #1289, Codex diff-review P1 over-strip): the bare inline
    # ``Share\s+Help`` and three-part ``\d.\d.\d Title Case`` patterns were REMOVED
    # (they could strip real economics prose under the global IGNORECASE sub — see
    # the negative controls in section (c)). The genuine standalone MDPI "Share Help"
    # and BLS TOC LINES are still screened by the whole-line allowlist (section (b)),
    # not the inline path, so they no longer have an INLINE positive case here.
    (
        "ILO Working-paper series-nav run (FULL literal)",
        "Generative AI and Jobs - Working paper Insights from job vacancy data "
        "Occupational exposure varies widely by region.",
        "- Working paper Insights from job vacancy data",
        "Occupational exposure varies widely by region.",
    ),
    (
        "ILO Pages-date listing run",
        "Insights 28 May 2026 56 Pages - 10 February 2026 The index refines exposure measurement.",
        "Pages - 10 February 2026",
        "The index refines exposure measurement.",
    ),
    (
        "MIT skip-to-content anchor",
        "#main-content The faculty page describes research on labor automation.",
        "#main-content",
        "The faculty page describes research on labor automation.",
    ),
]

for label, body, chrome_sub, prose in INLINE_CASES:
    cleaned = clean_fetch_body(body).cleaned_text or ""
    if chrome_sub.lower() in cleaned.lower():
        _fail(f"INLINE NOT SCREENED [{label}]: chrome '{chrome_sub}' still present in cleaned_text -> {cleaned!r}")
    # Adjacent real prose must survive (use a distinctive content fragment).
    key = prose.split(".")[0].strip()[-40:]
    if key.lower() not in cleaned.lower():
        _fail(f"PROSE DESTROYED [{label}]: expected fragment '{key}' missing from cleaned_text -> {cleaned!r}")


# ── (b) WHOLE-UNIT chrome lines: is_boilerplate_or_nonassertional must be True ──
WHOLE_UNIT_CHROME = [
    ("JEP masthead line", "onomic Perspectives—Volume 33, Number 2—Spring 2019—Pages 3-30"),
    ("ResearchGate CITATIONS line", "CITATIONS 12 READS 345"),
    ("ResearchGate authors line", "9 authors, including:"),
    ("Crossref line", "Crossref reports the following articles citing this paper"),
    ("MDPI Share Help line", "Share Help"),
    ("MIT main-content line", "#main-content"),
]

for label, unit in WHOLE_UNIT_CHROME:
    if not is_boilerplate_or_nonassertional(unit):
        _fail(f"WHOLE-UNIT NOT SCREENED [{label}]: is_boilerplate_or_nonassertional returned False for {unit!r}")


# ── (c) REAL economics sentences + adversarial near-misses: must ALL pass ──────────
# These share tokens with the new patterns; an over-greedy regex is caught ONLY here.
REAL_SENTENCES = [
    "Automation raised labor productivity in advanced economies over the 2010s.",
    "Trading volume rose; Number 2 ranked the firm among the largest exporters.",
    "The survey covered 12 countries, including Brazil and India.",
    "Labor's share of income fell in 23 OECD countries between 1990 and 2020.",
    "See section 2.3.2 for details on the wage decomposition.",
    "Several papers in the same series examine wages and skill premia.",
    "Metastases were not found in the control cohort after twelve months.",
    "Les changements technologiques ont transformé l'emploi dans le secteur manufacturier.",
    "The authors, including two from the central bank, dispute the elasticity estimate.",
]

for sent in REAL_SENTENCES:
    if is_boilerplate_or_nonassertional(sent):
        _fail(f"REAL SENTENCE WRONGLY SCREENED (whole-unit): {sent!r}")
    cleaned = clean_fetch_body(sent).cleaned_text or ""
    # The sentence must survive clean_fetch_body essentially intact (allow whitespace
    # normalization only). Compare the alpha content fragment.
    frag = sent.split(".")[0].strip()[-40:]
    if frag.lower() not in cleaned.lower():
        _fail(f"REAL SENTENCE MUTILATED (inline strip ate prose): {sent!r} -> cleaned {cleaned!r}")


# ── (d) NEGATIVE CONTROLS for the 3 Codex P1 over-strip fixes (b2-fix #1289) ───────
# These are the exact real-prose examples Codex flagged as collateral damage of the
# three TOO-BROAD inline patterns. The fix (remove ``Share\s+Help`` + the three-part
# ``\d.\d.\d Title Case`` patterns; tighten the ILO "- Working paper" pattern to its
# FULL series-nav literal) MUST leave every one of these UN-touched, BOTH as a whole
# unit (is_boilerplate_or_nonassertional == False) AND inline (the prose survives
# clean_fetch_body byte-faithfully). A regression here means a real economics sentence
# is being screened — over-strip, which §-1.1/§-1.3 rank as WORSE than a chrome leak.
# Each: (label, real_prose, must_survive_fragment)
NEGATIVE_CONTROLS = [
    (
        "P1#1 lowercase 'share help' in prose",
        "Local programs let workers share help to retrain for AI-exposed roles.",
        "share help to retrain",
    ),
    (
        "P1#2 markdown list '- Working paper NNN ...' as body prose",
        "- Working paper 245 examines wage effects of automation across regions.",
        "Working paper 245 examines wage effects",
    ),
    (
        "P1#3 in-prose section reference '2.3.2 Title Case'",
        "Section 2.3.2 Skill-Biased Technological Change shows rising inequality.",
        "2.3.2 Skill-Biased Technological Change shows rising inequality",
    ),
]

for label, prose, must_survive in NEGATIVE_CONTROLS:
    if is_boilerplate_or_nonassertional(prose):
        _fail(f"NEGATIVE CONTROL WRONGLY SCREENED (whole-unit) [{label}]: {prose!r}")
    cleaned = clean_fetch_body(prose).cleaned_text or ""
    if must_survive.lower() not in cleaned.lower():
        _fail(
            f"NEGATIVE CONTROL MUTILATED (inline over-strip ate prose) [{label}]: "
            f"expected '{must_survive}' to survive -> cleaned {cleaned!r}"
        )


if FAILURES:
    print("HARNESS FAILED — chrome-screen extension regressed:", file=sys.stderr)
    for f in FAILURES:
        print("  FAIL: " + f, file=sys.stderr)
    print(f"\n{len(FAILURES)} failure(s). The b2 chrome screen is NOT safe to ship.", file=sys.stderr)
    sys.exit(1)

print("HARNESS PASSED — all NEW chrome classes screened; all real/near-miss sentences + P1 negative controls preserved.")
print(
    f"  inline cases: {len(INLINE_CASES)} | whole-unit cases: {len(WHOLE_UNIT_CHROME)} | "
    f"real/near-miss: {len(REAL_SENTENCES)} | P1 negative controls: {len(NEGATIVE_CONTROLS)}"
)
sys.exit(0)
