"""Tests for the `codex-required` workflow's ISSUE_ID derivation regex.

GH #571 (I-ci-001): the `extract_and_validate_issue_id` step of
`.github/workflows/codex-required.yml` derives the canonical issue id from
the PR head ref `bot/<issue_id>`. Before the I-ci-001 fix the regex:

  * collapsed `-followup` ids onto their parent
    (`bot/I-rdy-019-followup-*` -> `I-rdy-019` instead of
    `I-rdy-019-followup`), making the gate read the *parent's* already
    merged `.codex/<id>/` artifacts; and
  * failed to match carved `a/b/c...` ids at all
    (`bot/I-rdy-014a` -> regex no-match -> the PR is rejected outright).

The fix extends the base-id capture group to also absorb an optional
`-followup` literal OR a single bare carved letter `[a-z]` directly after
the 3-digit number.

To stay honest, this test does NOT hardcode a copy of the regex — it
*extracts* the live ERE from the workflow YAML so it cannot silently drift
from what CI actually runs. The regex uses only constructs common to POSIX
ERE (bash `[[ =~ ]]`) and Python `re` — literals, char classes, `{m,n}`
quantifiers, `?`, alternation, anchors — so `re.match(...).group(1)` is
equivalent to bash `BASH_REMATCH[1]`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_WORKFLOW = _REPO / ".github" / "workflows" / "codex-required.yml"


def _extract_issue_branch_regex() -> str:
    """Pull the arm-1 ISSUE_ID regex out of the live workflow YAML.

    Matches the `if [[ "$HEAD_REF" =~ <ERE> ]]; then` line whose ERE starts
    with `^bot/(I-` and returns the ERE verbatim. Fails loud (LAW II) if the
    line cannot be found — a refactor that moves/renames it must update this
    test deliberately rather than have it silently pass.
    """
    text = _WORKFLOW.read_text(encoding="utf-8")
    # The ERE sits between `=~ ` and ` ]]` on the issue-branch arm.
    m = re.search(r'=~\s+(\^bot/\(I-[^\n]*?)\s+\]\]', text)
    if not m:  # pragma: no cover - guards against a silent drift
        raise AssertionError(
            f"could not locate the issue-branch ISSUE_ID regex in {_WORKFLOW}"
        )
    return m.group(1)


ISSUE_BRANCH_REGEX = _extract_issue_branch_regex()


# (head_ref, expected issue_id)  — branches the gate must accept and gate.
_GATE_CASES = [
    # plain canonical ids — unchanged behaviour
    ("bot/I-ci-001", "I-ci-001"),
    ("bot/I-bug-079", "I-bug-079"),
    ("bot/I-f1-001", "I-f1-001"),
    # descriptive slug after the base id — slug dropped, unchanged behaviour
    ("bot/I-f1-001-scope-discovery", "I-f1-001"),
    ("bot/I-hand-003-final", "I-hand-003"),
    # a dashed single-letter slug stays a slug (leading `-` => not carved)
    ("bot/I-rdy-014-a", "I-rdy-014"),
    # -followup ids — FIXED: resolve to their own id, not the parent's
    ("bot/I-rdy-019-followup", "I-rdy-019-followup"),
    ("bot/I-rdy-019-followup-test-matrix", "I-rdy-019-followup"),
    ("bot/I-gen-004-followup", "I-gen-004-followup"),
    # carved letter ids — FIXED: previously failed the regex outright
    ("bot/I-rdy-014a", "I-rdy-014a"),
    ("bot/I-rdy-014b", "I-rdy-014b"),
    ("bot/I-rdy-014c", "I-rdy-014c"),
    # carved beyond c exists in repo history (I-arch-001d/e/f) — [a-z] covers it
    ("bot/I-arch-001d", "I-arch-001d"),
    ("bot/I-arch-001f", "I-arch-001f"),
    # carved id WITH a descriptive slug
    ("bot/I-rdy-014a-follow-up-answer-ui", "I-rdy-014a"),
]

# head refs the arm-1 regex must NOT match (handled by the infra-allowlist
# `elif` or the catch-all reject arm — out of scope for arm 1).
_NON_ARM1_CASES = [
    "bot/pr-d-mechanical-gates",
    "bot/cleanup-pr-3a-archive-m1m26",
    "bot/pr-malicious",
    "bot/setup-anything",
    "bot/slice-foo",
    "main",
    "polaris",
    # malformed: a multi-letter bare suffix is not a valid carved id
    "bot/I-rdy-014abc",
]


@pytest.mark.parametrize("head_ref,expected_id", _GATE_CASES)
def test_issue_id_extracted(head_ref: str, expected_id: str) -> None:
    m = re.match(ISSUE_BRANCH_REGEX, head_ref)
    assert m is not None, f"{head_ref!r} should match the issue-branch regex"
    assert m.group(1) == expected_id, (
        f"{head_ref!r} -> issue_id {m.group(1)!r}, expected {expected_id!r}"
    )


@pytest.mark.parametrize("head_ref", _NON_ARM1_CASES)
def test_non_issue_branch_does_not_match_arm1(head_ref: str) -> None:
    assert re.match(ISSUE_BRANCH_REGEX, head_ref) is None, (
        f"{head_ref!r} must not match the issue-branch arm-1 regex"
    )


def test_followup_does_not_collapse_onto_parent() -> None:
    """The exact #558/PR#569 failure: the gate must NOT resolve a
    `-followup` branch to the parent id, or it reads the parent's
    already-merged `.codex/<parent>/` artifacts.
    """
    m = re.match(ISSUE_BRANCH_REGEX, "bot/I-rdy-019-followup-test-matrix")
    assert m is not None
    assert m.group(1) != "I-rdy-019", (
        "followup branch collapsed onto the parent id — the #571 bug"
    )
    assert m.group(1) == "I-rdy-019-followup"


def test_carved_letter_not_rejected() -> None:
    """Carved a/b/c... ids previously failed the regex entirely and were
    rejected by the catch-all `bot/*` arm. They must now gate normally.
    """
    for ref in ("bot/I-rdy-014a", "bot/I-rdy-014b", "bot/I-rdy-014c"):
        assert re.match(ISSUE_BRANCH_REGEX, ref) is not None, (
            f"carved branch {ref!r} must match the issue-branch regex"
        )
