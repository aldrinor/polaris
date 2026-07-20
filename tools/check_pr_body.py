#!/usr/bin/env python3
"""Check a pull request body against gov/pull_request_template.md.

Why this exists. A reviewer six months from now has to work out why a change
happened. If the body is missing sections, still holds the template
placeholders, or says the evidence exists without showing it, the change cannot
be reviewed. This checker blocks it and names the exact section at fault.

It does not take the body's word for anything it can check. An issue number
must be a real number and not zero. A file named as evidence must exist on
disk. A line reference must point at a real line. A traced data path must name
more than the one place the author tripped on.

The required sections are read out of the template file, so the template is the
only place the list lives. Point it at the issue template to check an issue:

    python3 tools/check_pr_body.py body.md
    python3 tools/check_pr_body.py issue.md --issue
    python3 tools/check_pr_body.py --selftest

Exit codes:
    0  accepted
    1  rejected, or the template could not be read
    2  the command line itself was wrong: no file given, or --selftest was
       given together with a file, which would check the wrong thing

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plain_text_rules import ascii_safe  # noqa: E402

DEFAULT_TEMPLATE = "pull_request_template.md"
ISSUE_TEMPLATE = "issue_template.md"

# A template thinner than this is not the real one. It is a swapped file.
MIN_TEMPLATE_SECTIONS = 3
# One stage is the place you tripped on. A path has more than one.
MIN_TRACE_STAGES = 2

# Rules keyed by section name. A rule never fires when the template in use has
# no section of that name, so one checker serves both templates.
REQUIRE_LINK = {"issue link"}
REQUIRE_FENCE = {"measured scope"}
REQUIRE_PROOF = {"evidence links"}
REQUIRE_FILE_LINE = {"data path trace"}
REQUIRE_NAMED_FILE = {"what changed"}
REQUIRE_VERDICT = {"review verdict"}
REQUIRE_COMMAND = {"rollback plan"}

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
_FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})\s*(\S*)\s*$")
_FENCE_LOOSE = re.compile(r"^( {0,3})(`{3,}|~{3,})")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CODE_SPAN = re.compile(r"`[^`\n]+`")
_ANGLE_PLACEHOLDER = re.compile(r"[<＜][^<>＜＞\n]{3,}[>＞]")
_URL_IN_ANGLES = re.compile(r"<https?://[^>\s]+>")
# A line number is a real line, so it is one or more and never zero.
_FILE_LINE = re.compile(r"(?<![\w/.-])([\w./\\-]+\.[A-Za-z0-9_]+):([1-9]\d*)\b")
_URL = re.compile(r"https?://[^\s<>\]]+")
_PATH_LIKE = re.compile(
    r"(?<![\w/.-])([\w./\\-]+\.(?:py|md|json|txt|log|ya?ml|patch|diff|html|csv))\b"
)
# An issue number is a real number, not zero, and not glued to other text.
_ISSUE_NUMBER = re.compile(r"(?<![\w#])#([1-9]\d*)(?!\w)")
_COMMAND_PROMPT = re.compile(r"(?m)^\s*(\$|>>>|PS[ >]|#)\s*\S")
_VERDICT_WORD = re.compile(
    r"(?<!\w)(APPROVE[DS]?|REQUEST_CHANGES|REQUESTED CHANGES|REJECT(?:ED)?|BLOCK(?:ED)?"
    r"|LGTM|SIGNED[- ]OFF|SIGN[- ]OFF|PASS(?:ED)?|FAIL(?:ED)?)(?!\w)",
    re.IGNORECASE,
)

# Words that fill a section without saying anything.
_FILLER = {
    "tbd", "tba", "tbc", "todo", "to do", "n/a", "na", "none", "nil", "null",
    "xxx", "fixme", "pending", "later", "?", "-", "see above", "same as above",
    "trust me", "obvious", "self explanatory", "self-explanatory",
}
# Acceptance criteria that only restate that the tests run.
_WEAK_ACCEPTANCE = {
    "the test passes", "the tests pass", "tests pass", "test passes",
    "all tests pass", "the test suite passes", "it works", "the code is correct",
    "ci is green", "ci passes",
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(name: str) -> str:
    work = name.strip().lower()
    work = work.strip("#").strip()
    work = work.rstrip(":.").strip()
    return re.sub(r"\s+", " ", work)


def normalize_prose(text: str) -> str:
    """Lowercase, drop punctuation, squeeze spaces. For comparing wording."""
    work = re.sub(r"[^\w\s]+", " ", text.lower())
    return re.sub(r"\s+", " ", work).strip()


def fence_map(lines: list[str]) -> tuple[set[int], str | None]:
    """Return the line numbers inside a fenced block, and any open-fence error.

    A fence only counts when it opens and closes with the same mark and the
    closing run is at least as long as the opening one. Anything else is
    ordinary text, so a mismatched pair cannot be used to make the checker and
    a reader disagree about where the block ends.
    """
    inside: set[int] = set()
    open_mark: str | None = None
    open_length = 0
    open_line = 0
    for number, line in enumerate(lines):
        match = _FENCE.match(line)
        if open_mark is None:
            if match:
                open_mark = match.group(2)[0]
                open_length = len(match.group(2))
                open_line = number + 1
                inside.add(number)
            continue
        inside.add(number)
        if match and match.group(2)[0] == open_mark and len(match.group(2)) >= open_length \
                and not match.group(3):
            open_mark = None
    if open_mark is not None:
        return inside, (
            "The fenced block opened on line %d never closes. A reader sees "
            "everything after it as pasted output, and the checker does not. "
            "Close it with %s." % (open_line, open_mark * open_length)
        )
    return inside, None


def strip_comments(text: str) -> tuple[str, str | None]:
    """Remove HTML comments, but not the ones shown as code, and not in fences.

    A comment inside backticks renders on the page as visible text, so removing
    it would let a template placeholder show on screen while the checker sees
    an empty section.
    """
    lines = text.splitlines()
    inside, _ = fence_map(lines)

    spans: list[str] = []

    def hide(match: re.Match) -> str:
        spans.append(match.group(0))
        return "\x00%d\x00" % (len(spans) - 1)

    out: list[str] = []
    for number, line in enumerate(lines):
        out.append(line if number in inside else _CODE_SPAN.sub(hide, line))
    joined = "\n".join(out)

    cleaned = _COMMENT.sub("", joined)
    unclosed = None
    if "<!--" in cleaned:
        unclosed = (
            "There is an opening <!-- with no closing -->. Everything after it is "
            "hidden from a reader while the checker still reads it. Close it."
        )
    for index, span in enumerate(spans):
        cleaned = cleaned.replace("\x00%d\x00" % index, span)
    return cleaned, unclosed


def parse_sections(text: str) -> list[dict]:
    """Split on headings. A section holds its own subsections.

    A subheading does not end its parent. Without that, writing sensible
    subsections under a required heading made the parent look empty, and a
    later heading of the wrong level could quietly replace the real one.
    """
    lines = text.splitlines()
    inside, _ = fence_map(lines)

    heads: list[tuple[int, int, str]] = []
    for number, line in enumerate(lines):
        if number in inside:
            continue
        match = _HEADING.match(line)
        if match:
            heads.append((number, len(match.group(1)), match.group(2).strip()))

    sections: list[dict] = []
    for index, (start, level, name) in enumerate(heads):
        end = len(lines)
        for later_start, later_level, _ in heads[index + 1:]:
            if later_level <= level:
                end = later_start
                break
        sections.append(
            {
                "level": level,
                "name": name,
                "key": normalize(name),
                "body": "\n".join(lines[start + 1:end]),
            }
        )
    return sections


def required_sections(template_text: str) -> list[tuple[str, int]]:
    """The level two headings of the template are the required sections."""
    clean, _ = strip_comments(template_text)
    return [(s["name"], s["level"]) for s in parse_sections(clean) if s["level"] == 2]


def required_section_names(template_text: str) -> list[str]:
    return [name for name, _ in required_sections(template_text)]


def template_placeholders(template_text: str) -> set[str]:
    clean, _ = strip_comments(template_text)
    return set(_ANGLE_PLACEHOLDER.findall(clean))


def has_content(body: str) -> bool:
    """True when the section holds prose, or a closed fence with something in it.

    A fence counts, so a section that is only pasted output gets the specific
    complaint about what the paste is missing rather than the blunt one about
    being empty.
    """
    lines = body.splitlines()
    inside, _ = fence_map(lines)
    for number, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or number in inside:
            continue
        if _HEADING.match(line):
            continue
        return True
    return has_fenced_block(body)


def visible_text(body: str) -> str:
    """The prose of a section, with fences and headings removed."""
    lines = body.splitlines()
    inside, _ = fence_map(lines)
    keep = [
        line
        for number, line in enumerate(lines)
        if number not in inside and not _HEADING.match(line)
    ]
    return "\n".join(keep).strip()


def has_fenced_block(body: str) -> bool:
    """A fence is only real if it opens, holds a line, and closes to match."""
    lines = body.splitlines()
    open_mark: str | None = None
    open_length = 0
    holds_content = False
    for line in lines:
        match = _FENCE.match(line)
        if open_mark is None:
            if match:
                open_mark = match.group(2)[0]
                open_length = len(match.group(2))
                holds_content = False
            continue
        if match and match.group(2)[0] == open_mark and len(match.group(2)) >= open_length \
                and not match.group(3):
            if holds_content:
                return True
            open_mark = None
            continue
        if line.strip():
            holds_content = True
    return False


def fenced_text(body: str) -> str:
    """Everything inside the fenced blocks of one section."""
    lines = body.splitlines()
    open_mark: str | None = None
    open_length = 0
    out: list[str] = []
    for line in lines:
        match = _FENCE.match(line)
        if open_mark is None:
            if match:
                open_mark = match.group(2)[0]
                open_length = len(match.group(2))
            continue
        if match and match.group(2)[0] == open_mark and len(match.group(2)) >= open_length \
                and not match.group(3):
            open_mark = None
            continue
        out.append(line)
    return "\n".join(out)


class PathChecker:
    """Open the files a body names, so an invented path cannot pass as proof."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.checked = 0

    def missing(self, candidate: str) -> bool:
        try:
            target = (self.repo_root / candidate).resolve()
            target.relative_to(self.repo_root)
        except (OSError, ValueError):
            return True
        self.checked += 1
        return not target.is_file()

    def line_out_of_range(self, candidate: str, line_number: int) -> int | None:
        """Return the file's real length when the line is past the end."""
        try:
            target = (self.repo_root / candidate).resolve()
            target.relative_to(self.repo_root)
            count = len(target.read_text(encoding="utf-8", errors="replace").splitlines())
        except (OSError, ValueError):
            return None
        return count if line_number > count else None


def _check_section(
    name: str,
    key: str,
    body: str,
    reasons: list[str],
    paths: PathChecker | None,
) -> None:
    prose = normalize_prose(visible_text(body))

    if prose in _FILLER or (prose and all(part.strip() in _FILLER for part in prose.split(";"))):
        reasons.append(
            "The section '%s' says only '%s', which is a note to yourself, not "
            "content. Write what actually happened."
            % (ascii_safe(name), ascii_safe(visible_text(body).strip()[:60]))
        )
        return

    if key == "acceptance criterion" and prose in _WEAK_ACCEPTANCE:
        reasons.append(
            "The section '%s' says only that the tests pass. The template asks for "
            "the observable effect in real output, and where to look for it."
            % ascii_safe(name)
        )

    if key in REQUIRE_LINK and not (_ISSUE_NUMBER.search(body) or _URL.search(body)):
        reasons.append(
            "The section '%s' has no real link. Write an issue number like #123 or "
            "a full address. Zero is not an issue number, and a number glued to "
            "other text is not a link." % ascii_safe(name)
        )

    if key in REQUIRE_FENCE:
        if not has_fenced_block(body):
            reasons.append(
                "The section '%s' has no pasted command and output. Run the command, "
                "paste it and its real output in a fenced block. An estimate is "
                "rejected." % ascii_safe(name)
            )
        else:
            inner = fenced_text(body)
            if _COMMAND_PROMPT.search(inner) is None or not any(c.isdigit() for c in inner):
                reasons.append(
                    "The section '%s' has a fenced block with no command in it and no "
                    "number in the output. Start a line with $ and give the real "
                    "command, then the real count it printed." % ascii_safe(name)
                )

    if key in REQUIRE_PROOF:
        if not (has_fenced_block(body) or _URL.search(body) or _PATH_LIKE.search(body)):
            reasons.append(
                "The section '%s' shows no proof. Paste the real output in a fenced "
                "block, or give a path or address a reviewer can open."
                % ascii_safe(name)
            )

    if key in REQUIRE_NAMED_FILE and not (_PATH_LIKE.search(body) or _FILE_LINE.search(body)):
        reasons.append(
            "The section '%s' names no file. Say which file changed and what changed "
            "in it, one line per change." % ascii_safe(name)
        )

    if key in REQUIRE_VERDICT and not _VERDICT_WORD.search(body):
        reasons.append(
            "The section '%s' records no verdict. Name the reviewer and write what "
            "they decided, in a word a reader can find: APPROVE, REQUEST_CHANGES, "
            "or the like." % ascii_safe(name)
        )

    if key in REQUIRE_COMMAND:
        inner = fenced_text(body) + "\n" + visible_text(body)
        if _COMMAND_PROMPT.search(inner) is None and "git " not in inner and \
                "cannot be undone" not in inner.lower():
            reasons.append(
                "The section '%s' gives no command. Write the exact command that "
                "undoes this, or say plainly that it cannot be undone and what has "
                "to be done by hand instead." % ascii_safe(name)
            )

    if key in REQUIRE_FILE_LINE:
        hits = _FILE_LINE.findall(body)
        if not hits:
            reasons.append(
                "The section '%s' names no file and line. Trace every stage the data "
                "passes through as file.py:line, and every chokepoint where the "
                "effect can die. A line number of zero is not a line."
                % ascii_safe(name)
            )
        elif len(set(hits)) < MIN_TRACE_STAGES:
            reasons.append(
                "The section '%s' names only %d place. A path has more than one "
                "stage, and naming only the place you tripped on is how the same bug "
                "comes back. List every stage and every chokepoint."
                % (ascii_safe(name), len(set(hits)))
            )

    if paths is None:
        return

    for candidate, line_text in _FILE_LINE.findall(body):
        if paths.missing(candidate):
            reasons.append(
                "The section '%s' points at %s, and there is no such file. A "
                "reviewer cannot open it, so it is not a trace."
                % (ascii_safe(name), ascii_safe(candidate))
            )
            continue
        real_length = paths.line_out_of_range(candidate, int(line_text))
        if real_length is not None:
            reasons.append(
                "The section '%s' points at %s line %s, and that file has only %d "
                "lines." % (ascii_safe(name), ascii_safe(candidate), line_text, real_length)
            )

    if key in REQUIRE_PROOF or key in REQUIRE_NAMED_FILE:
        for candidate in _PATH_LIKE.findall(body):
            if paths.missing(candidate):
                reasons.append(
                    "The section '%s' offers %s as proof, and there is no such file. "
                    "Evidence a reviewer cannot open is not evidence."
                    % (ascii_safe(name), ascii_safe(candidate))
                )


def check_body(
    body_text: str, template_text: str, paths: PathChecker | None = None
) -> list[str]:
    """Return a list of plain reasons the body is bad. Empty means good."""
    reasons: list[str] = []

    required = required_sections(template_text)
    if len(required) < MIN_TEMPLATE_SECTIONS:
        return [
            "The template has only %d level two sections, and the real templates "
            "have at least %d. This is not the standard template, so the check "
            "would pass almost anything." % (len(required), MIN_TEMPLATE_SECTIONS)
        ]

    body_lines = body_text.splitlines()
    _, fence_error = fence_map(body_lines)
    if fence_error:
        reasons.append(fence_error)

    clean_body, comment_error = strip_comments(body_text)
    if comment_error:
        reasons.append(comment_error)

    found: dict[str, list[dict]] = {}
    for section in parse_sections(clean_body):
        found.setdefault(section["key"], []).append(section)

    for name, level in required:
        key = normalize(name)
        matches = found.get(key, [])

        if not matches:
            reasons.append(
                "The section '%s' is missing. Add the heading and fill it in."
                % ascii_safe(name)
            )
            continue

        if len(matches) > 1:
            reasons.append(
                "The section '%s' appears %d times. A reader cannot tell which one "
                "counts. Keep one." % (ascii_safe(name), len(matches))
            )
            continue

        section = matches[0]
        if section["level"] != level:
            reasons.append(
                "The section '%s' is written at heading level %d and the template "
                "puts it at level %d. A heading at the wrong level reads as part of "
                "another section." % (ascii_safe(name), section["level"], level)
            )
            continue

        if not has_content(section["body"]):
            reasons.append(
                "The section '%s' is present but empty. Write the real content "
                "under it." % ascii_safe(name)
            )
            continue

        _check_section(name, key, section["body"], reasons, paths)

    # Placeholders, whatever bracket they were rewritten with.
    normalized_body = normalize_prose(clean_body)
    for placeholder in sorted(template_placeholders(template_text)):
        inner = normalize_prose(placeholder.strip("<>＜＞"))
        if inner and inner in normalized_body:
            reasons.append(
                "The template placeholder '%s' is still in the body. Replace it with "
                "the real content." % ascii_safe(placeholder)
            )

    return reasons


def find_template(name: str, start: Path | None = None) -> Path | None:
    here = Path(__file__).resolve()
    candidates = [here.parent.parent / "gov" / name, here.parent / "gov" / name]
    base = (start or Path.cwd()).resolve()
    for folder in [base] + list(base.parents):
        candidates.append(folder / "gov" / name)
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_template(path: Path | None = None, name: str = DEFAULT_TEMPLATE) -> tuple[str, Path]:
    template_path = path or find_template(name)
    if template_path is None:
        raise FileNotFoundError(
            "Cannot find gov/%s. The checker reads the required sections from it."
            % name
        )
    return template_path.read_text(encoding="utf-8"), template_path


def looks_like_the_other_template(body_text: str, other_text: str) -> bool:
    """True when the body matches the template that was not chosen."""
    clean, _ = strip_comments(body_text)
    keys = {s["key"] for s in parse_sections(clean)}
    wanted = {normalize(n) for n in required_section_names(other_text)}
    return bool(wanted) and len(keys & wanted) > len(wanted) / 2


def check_file(
    path: Path, template_text: str, paths: PathChecker | None = None
) -> tuple[bool, list[str]]:
    if not path.is_file():
        return False, ["There is no file at %s." % ascii_safe(str(path))]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return False, ["Cannot read %s: %s." % (ascii_safe(str(path)), error)]
    if not text.strip():
        return False, ["The body file is empty."]
    reasons = check_body(text, template_text, paths)
    return (len(reasons) == 0), reasons


# ---------------------------------------------------------------------------
# Selftest. A rejected bad body is a PASS. Blocking is the proof.
# ---------------------------------------------------------------------------

def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build_good_body(template_text: str) -> str:
    """Build a filled body from the template so the fixture cannot drift.

    The files it names are real files in this repository, because the checker
    now opens them.
    """
    lines: list[str] = []
    for name in required_section_names(template_text):
        key = normalize(name)
        lines.append("## %s" % name)
        lines.append("")
        if key in REQUIRE_LINK:
            lines.append("Closes #123.")
        elif key in REQUIRE_VERDICT:
            lines.append("Codex reviewed it and returned APPROVE in .codex/verdict.txt.")
        elif key in REQUIRE_COMMAND:
            lines.append("Run `git revert abc1234` and restart nothing else.")
        elif key in REQUIRE_NAMED_FILE:
            lines.append("Rewrote tools/check_pr_body.py to open the files it names.")
        elif key == "acceptance criterion":
            lines.append("A body naming a file that does not exist is rejected by name.")
        else:
            lines.append("Real content written for the %s section." % key)
        if key in REQUIRE_FILE_LINE:
            lines.append("- tools/check_pr_body.py:1 reads the body")
            lines.append("- tools/plain_text_rules.py:1 counts the sentences")
            lines.append("- tools/validate_agent_payload.py:1 opens the evidence")
        if key in REQUIRE_FENCE or key in REQUIRE_PROOF:
            lines.append("")
            lines.append("```")
            lines.append("$ python3 tools/check_pr_body.py --selftest")
            lines.append("RESULT: 24 of 24 cases PASS")
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def drop_section(body: str, name: str) -> str:
    """Remove one whole section from a body, heading and content."""
    out: list[str] = []
    skipping = False
    for line in body.splitlines():
        match = _HEADING.match(line)
        if match:
            skipping = normalize(match.group(2)) == normalize(name)
        if not skipping:
            out.append(line)
    return "\n".join(out) + "\n"


def replace_section_body(body: str, name: str, new_lines: list[str]) -> str:
    """Swap the content under one heading, keeping every other section as is."""
    out: list[str] = []
    skipping = False
    for line in body.splitlines():
        match = _HEADING.match(line)
        if match:
            skipping = normalize(match.group(2)) == normalize(name)
            out.append(line)
            if skipping:
                out.append("")
                out.extend(new_lines)
            continue
        if not skipping:
            out.append(line)
    return "\n".join(out) + "\n"


def blank_section(body: str, name: str) -> str:
    """Keep the heading, remove everything under it."""
    return replace_section_body(body, name, [])


def run_selftest() -> int:
    print("SELFTEST check_pr_body")
    print("A bad body that gets REJECTED is a PASS. Blocking is the proof.")
    print("")

    passed = 0
    total = 0
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, note: str) -> None:
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        results.append((name, ok, note))

    try:
        pr_template, _ = load_template(name=DEFAULT_TEMPLATE)
        issue_template, _ = load_template(name=ISSUE_TEMPLATE)
    except FileNotFoundError as error:
        print("[case 1] templates_load: FAIL (%s)" % ascii_safe(str(error)))
        print("")
        print("RESULT: 0 of 1 cases PASS")
        return 1

    paths = PathChecker(repo_root())
    pr_sections = required_section_names(pr_template)
    issue_sections = required_section_names(issue_template)
    record(
        "pr_template_loads",
        len(pr_sections) == 6,
        "%d required sections: %s" % (len(pr_sections), ", ".join(pr_sections)),
    )
    record(
        "issue_template_loads",
        len(issue_sections) == 5,
        "%d required sections: %s" % (len(issue_sections), ", ".join(issue_sections)),
    )

    good_pr = build_good_body(pr_template)
    good_issue = build_good_body(issue_template)

    sham_pr = (
        "### Issue link\nNot linked; #0.\n"
        "### What changed\nTBD\n"
        "### Evidence links\nThere is no proof; missing.log.\n"
        "### Review verdict\nTBD\n"
        "### Not in scope\nTBD\n"
        "### Rollback plan\nTBD\n"
    )
    sham_issue = (
        "### Problem\nTBD\n"
        "### Measured scope\n```\nabout twenty\n```\n"
        "### Data path trace\nNo trace was done; fake.py:0.\n"
        "### Acceptance criterion\nThe test passes.\n"
        "### Out of scope\nTBD\n"
    )
    nested_pr = replace_section_body(
        good_pr,
        "What changed",
        ["### Stages", "", "Rewrote tools/check_pr_body.py to open the files it names."],
    )

    checks: list[dict] = [
        {"name": "good_pr_body", "body": good_pr, "template": pr_template, "accept": True},
        {"name": "good_issue_body", "body": good_issue, "template": issue_template, "accept": True},
        {
            "name": "good_pr_body_with_a_subsection",
            "body": nested_pr,
            "template": pr_template,
            "accept": True,
        },
        {
            "name": "bad_sham_pr_body_that_used_to_pass",
            "body": sham_pr,
            "template": pr_template,
            "accept": False,
            "expect": "heading level",
        },
        {
            "name": "bad_sham_issue_body_that_used_to_pass",
            "body": sham_issue,
            "template": issue_template,
            "accept": False,
            "expect": "heading level",
        },
        {
            "name": "bad_pr_issue_number_is_zero",
            "body": good_pr.replace("Closes #123.", "Closes #0."),
            "template": pr_template,
            "accept": False,
            "expect": "has no real link",
        },
        {
            "name": "bad_pr_issue_number_glued_to_text",
            "body": good_pr.replace("Closes #123.", "Closes C#123abc."),
            "template": pr_template,
            "accept": False,
            "expect": "has no real link",
        },
        {
            "name": "bad_pr_section_says_tbd",
            "body": replace_section_body(good_pr, "Not in scope", ["TBD"]),
            "template": pr_template,
            "accept": False,
            "expect": "a note to yourself",
        },
        {
            "name": "bad_pr_evidence_file_does_not_exist",
            "body": replace_section_body(
                good_pr, "Evidence links", ["The run is recorded in missing.log."]
            ),
            "template": pr_template,
            "accept": False,
            "expect": "there is no such file",
        },
        {
            "name": "bad_pr_rollback_has_no_command",
            "body": replace_section_body(
                good_pr, "Rollback plan", ["We would put it back the way it was."]
            ),
            "template": pr_template,
            "accept": False,
            "expect": "gives no command",
        },
        {
            "name": "bad_pr_review_verdict_names_no_verdict",
            "body": replace_section_body(
                good_pr, "Review verdict", ["Someone looked at it last week."]
            ),
            "template": pr_template,
            "accept": False,
            "expect": "records no verdict",
        },
        {
            "name": "bad_pr_what_changed_names_no_file",
            "body": replace_section_body(
                good_pr, "What changed", ["I made the checker stricter."]
            ),
            "template": pr_template,
            "accept": False,
            "expect": "names no file",
        },
        {
            "name": "bad_pr_missing_rollback_plan",
            "body": drop_section(good_pr, "Rollback plan"),
            "template": pr_template,
            "accept": False,
            "expect": "The section 'Rollback plan' is missing",
        },
        {
            "name": "bad_pr_empty_what_changed",
            "body": blank_section(good_pr, "What changed"),
            "template": pr_template,
            "accept": False,
            "expect": "is present but empty",
        },
        {
            "name": "bad_pr_duplicate_heading",
            "body": good_pr + "\n## Rollback plan\n\nSomething else entirely.\n",
            "template": pr_template,
            "accept": False,
            "expect": "appears 2 times",
        },
        {
            "name": "bad_pr_placeholder_left_in",
            "body": replace_section_body(
                good_pr,
                "Rollback plan",
                ["<the exact command to undo this, and anything that needs a hand>"],
            ),
            "template": pr_template,
            "accept": False,
            "expect": "is still in the body",
        },
        {
            "name": "bad_pr_placeholder_in_square_brackets",
            "body": replace_section_body(
                good_pr,
                "Rollback plan",
                ["[the exact command to undo this, and anything that needs a hand]"],
            ),
            "template": pr_template,
            "accept": False,
            "expect": "is still in the body",
        },
        {
            "name": "bad_pr_placeholder_shown_as_code",
            "body": replace_section_body(
                good_pr,
                "Rollback plan",
                ["`<!-- <the exact command to undo this, and anything that needs a hand> -->`"],
            ),
            "template": pr_template,
            "accept": False,
            "expect": "is still in the body",
        },
        {
            "name": "bad_pr_unclosed_comment_hides_the_rest",
            "body": good_pr + "\n<!-- everything after this is hidden from a reader\n",
            "template": pr_template,
            "accept": False,
            "expect": "no closing",
        },
        {
            "name": "bad_pr_evidence_without_proof",
            "body": replace_section_body(
                good_pr, "Evidence links", ["The tests all pass, trust me."]
            ),
            "template": pr_template,
            "accept": False,
            "expect": "shows no proof",
        },
        {
            "name": "bad_issue_missing_data_path_trace",
            "body": drop_section(good_issue, "Data path trace"),
            "template": issue_template,
            "accept": False,
            "expect": "The section 'Data path trace' is missing",
        },
        {
            "name": "bad_issue_trace_names_only_one_stage",
            "body": replace_section_body(
                good_issue,
                "Data path trace",
                ["The data dies here.", "- tools/check_pr_body.py:1 reads the body"],
            ),
            "template": issue_template,
            "accept": False,
            "expect": "names only 1 place",
        },
        {
            "name": "bad_issue_trace_line_number_is_zero",
            "body": good_issue.replace(".py:1", ".py:0"),
            "template": issue_template,
            "accept": False,
            "expect": "names no file and line",
        },
        {
            "name": "bad_issue_trace_line_past_end_of_file",
            "body": good_issue.replace("tools/check_pr_body.py:1", "tools/check_pr_body.py:999999"),
            "template": issue_template,
            "accept": False,
            "expect": "lines.",
        },
        {
            "name": "bad_issue_scope_without_pasted_output",
            "body": replace_section_body(
                good_issue, "Measured scope", ["About twenty places, I think."]
            ),
            "template": issue_template,
            "accept": False,
            "expect": "has no pasted command and output",
        },
        {
            "name": "bad_issue_scope_fence_holds_no_command",
            "body": replace_section_body(
                good_issue, "Measured scope", ["The count is here.", "```", "trust me", "```"]
            ),
            "template": issue_template,
            "accept": False,
            "expect": "no command in it",
        },
        {
            "name": "bad_issue_scope_fence_closed_with_the_wrong_mark",
            "body": replace_section_body(
                good_issue,
                "Measured scope",
                ["The count is here.", "```", "$ wc -l x.py", "42", "~~~"],
            ),
            "template": issue_template,
            "accept": False,
            "expect": "never closes",
        },
        {
            "name": "bad_issue_acceptance_is_only_tests_pass",
            "body": replace_section_body(
                good_issue, "Acceptance criterion", ["The tests pass."]
            ),
            "template": issue_template,
            "accept": False,
            "expect": "says only that the tests pass",
        },
        {
            "name": "bad_weak_template_would_pass_anything",
            "body": "## X\n\nx\n",
            "template": "## X\n",
            "accept": False,
            "expect": "not the standard template",
        },
    ]

    for case in checks:
        reasons = check_body(case["body"], case["template"], paths)
        accepted = len(reasons) == 0
        wanted = case.get("expect", "")
        joined = " ".join(reasons)
        if case["accept"]:
            record(
                case["name"],
                accepted,
                "ACCEPTED as expected" if accepted else "REJECTED: %s" % joined,
            )
        elif not accepted and (not wanted or wanted in joined):
            record(case["name"], True, "REJECTED: %s" % reasons[0])
        elif not accepted:
            record(
                case["name"],
                False,
                "REJECTED for the wrong reason. Wanted: %s. Got: %s" % (wanted, joined),
            )
        else:
            record(case["name"], False, "ACCEPTED but must be blocked")

    code = main(["some_real_body.md", "--selftest"])
    record(
        "selftest_together_with_a_file_is_refused",
        code == 2,
        "returned exit code %d, and 2 means it refused to check the wrong thing" % code,
    )

    for index, (name, ok, note) in enumerate(results, start=1):
        verdict = "PASS" if ok else "FAIL"
        print("[case %d] %s: %s" % (index, name, verdict))
        print("           %s" % ascii_safe(note))

    print("")
    print("Files really opened while checking these bodies: %d." % paths.checked)
    print("RESULT: %d of %d cases PASS" % (passed, total))
    return 0 if passed == total else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a pull request body, or an issue, against its template."
    )
    parser.add_argument("body", nargs="?", help="Path to the body file.")
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="Template to check against. Defaults to gov/pull_request_template.md.",
    )
    parser.add_argument(
        "--issue",
        action="store_true",
        help="Check against gov/issue_template.md instead of the pull request one.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Folder the named files are relative to. Defaults to this folder.",
    )
    parser.add_argument(
        "--no-verify-paths",
        action="store_true",
        help="Do not open the files the body names. The result then says so out loud.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run the built-in good and bad bodies and print PASS or FAIL for each.",
    )
    args = parser.parse_args(argv)

    if args.selftest and args.body:
        print(
            "Give me a body file OR --selftest, not both. With both, the file you "
            "named would never be read.",
            file=sys.stderr,
        )
        return 2

    if args.selftest:
        return run_selftest()

    if not args.body:
        print("Give me a body file to check, or use --selftest.", file=sys.stderr)
        return 2

    wanted_name = ISSUE_TEMPLATE if args.issue else DEFAULT_TEMPLATE
    try:
        template_text, template_path = load_template(args.template, wanted_name)
    except FileNotFoundError as error:
        print("REJECTED: %s" % ascii_safe(str(error)), file=sys.stderr)
        return 1

    path = Path(args.body)
    paths = None if args.no_verify_paths else PathChecker(args.repo_root or Path.cwd())
    ok, reasons = check_file(path, template_text, paths)

    if not ok and not args.template and not args.issue:
        other = find_template(ISSUE_TEMPLATE)
        if other is not None and path.is_file():
            if looks_like_the_other_template(
                path.read_text(encoding="utf-8"), other.read_text(encoding="utf-8")
            ):
                reasons.append(
                    "This body looks like an issue, not a pull request. Run it again "
                    "with --issue."
                )

    note = "  template %s sha256 %s" % (
        ascii_safe(str(template_path)),
        sha256_of(template_path),
    )

    if ok:
        print("BODY ACCEPTED: %s" % ascii_safe(str(path)))
        print("  sha256 %s" % sha256_of(path))
        print(note)
        if paths is None:
            print(
                "  NOT CHECKED: the files this body names were not opened, because "
                "--no-verify-paths was given."
            )
        else:
            print("  files opened and found: %d" % paths.checked)
        return 0

    print("BODY REJECTED: %s" % ascii_safe(str(path)), file=sys.stderr)
    print(note, file=sys.stderr)
    for number, reason in enumerate(reasons, start=1):
        print("  %d. %s" % (number, ascii_safe(reason)), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
