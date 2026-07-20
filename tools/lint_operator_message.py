#!/usr/bin/env python3
"""Check a message written for the operator against gov/operator_voice.md.

The operator is blind and reads by ear. Long nested jargon is unreadable out
loud. This checker blocks the message before it is sent and quotes the exact
sentence that broke the rule.

Fenced blocks are skipped, because pasted command output is not the agent's
writing. That skip used to be the way around every rule: put the whole message
in a fence and nothing was read. So the fence has to be a real, closed, matched
fence, and a message that is nothing but fenced text is rejected.

Usage:
    python3 tools/lint_operator_message.py path/to/message.md
    python3 tools/lint_operator_message.py --selftest

Exit codes:
    0  the message is fine to send
    1  the message is rejected, or the voice document could not be read
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
from plain_text_rules import (  # noqa: E402
    HTML_STRUCTURE,
    ascii_safe,
    build_term_pattern,
    count_words,
    find_invisible,
    fold_for_matching,
    split_sentences,
)

VOICE_DOC_NAME = "operator_voice.md"
BANNED_BEGIN = "<!-- banned_words_begin -->"
BANNED_END = "<!-- banned_words_end -->"

MAX_SENTENCES = 5
# A judgement call, not a measurement. Thirty five words is about the point
# where a listener loses the start of the sentence before the verb arrives.
MAX_WORDS_PER_SENTENCE = 35
# A policy file thinner than this is not the real list. It is a swapped file.
MIN_BANNED_TERMS = 20

# Bullets in every shape a renderer accepts, including the picture ones.
_BULLET = re.compile(r"^(\s*)([-*+•‣▪▫●○◦]|\d+[.)]|[A-Za-z][.)])\s+")
# A fence opens with three or more of one mark, indented no more than three
# spaces. Four spaces is an indented code block, which renders as plain text.
_FENCE_OPEN = re.compile(r"^( {0,3})(`{3,}|~{3,})\s*(\S*)\s*$")
_FENCE_ANY = re.compile(r"^( {0,3})(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"`[^`\n]+`")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")

_QUESTION = re.compile(r"^\s*Question:\s*\S")
_OPTION = re.compile(r"^\s*Option\s+(\d+)\s*(\(RECOMMENDED\))?\s*:\s*\S")
_IF_PICK = re.compile(r"^\s*If you pick this:\s*\S")

# Ranges that hold the pictures. Arrows and tick marks are in here too: a
# screen reader says the whole name of those as well, so they are no better
# than an emoji for a listener.
_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE0E, 0xFE0F),
    (0x20E3, 0x20E3),  # the keycap mark, which turns 1 into a picture
    (0x2049, 0x2049),
    (0x231A, 0x231B),
    (0x23E9, 0x23FA),
    (0x24C2, 0x24C2),
    (0x2934, 0x2935),
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3299),
)


def is_emoji(ch: str) -> bool:
    point = ord(ch)
    for low, high in _EMOJI_RANGES:
        if low <= point <= high:
            return True
    return False


def find_voice_doc(start: Path | None = None) -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "gov" / VOICE_DOC_NAME,
        here.parent / "gov" / VOICE_DOC_NAME,
    ]
    base = (start or Path.cwd()).resolve()
    for folder in [base] + list(base.parents):
        candidates.append(folder / "gov" / VOICE_DOC_NAME)
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_banned_terms(path: Path | None = None) -> tuple[list[str], Path]:
    """Read the banned list out of gov/operator_voice.md. Fail loudly if absent."""
    doc_path = path or find_voice_doc()
    if doc_path is None:
        raise FileNotFoundError(
            "Cannot find gov/%s. The checker needs it for the banned word list."
            % VOICE_DOC_NAME
        )
    text = doc_path.read_text(encoding="utf-8")
    if BANNED_BEGIN not in text or BANNED_END not in text:
        raise ValueError(
            "gov/%s has no banned word block. Expected the markers %s and %s."
            % (VOICE_DOC_NAME, BANNED_BEGIN, BANNED_END)
        )
    block = text.split(BANNED_BEGIN, 1)[1].split(BANNED_END, 1)[0]
    terms = []
    for line in block.splitlines():
        item = line.strip()
        if not item or _FENCE_ANY.match(item):
            continue
        terms.append(item.lower())
    if not terms:
        raise ValueError("The banned word block in gov/%s is empty." % VOICE_DOC_NAME)
    if len(terms) < MIN_BANNED_TERMS:
        raise ValueError(
            "The banned word block in %s holds only %d terms, and the real list "
            "holds at least %d. This is not the standard policy file, so the check "
            "would pass almost anything."
            % (ascii_safe(str(doc_path)), len(terms), MIN_BANNED_TERMS)
        )
    return terms, doc_path


def strip_fences(lines: list[str]) -> tuple[list[tuple[int, str]], int, str | None]:
    """Drop fenced blocks. Pasted output is not the agent's writing.

    A fence only counts when it opens and closes with the same mark, the
    closing run is at least as long as the opening one, and neither is indented
    past three spaces. Anything else is ordinary text and gets read. An
    unclosed fence is reported, because everything after it would be skipped.
    """
    kept: list[tuple[int, str]] = []
    skipped = 0
    open_mark: str | None = None
    open_length = 0
    open_line = 0

    for number, line in enumerate(lines, start=1):
        match = _FENCE_OPEN.match(line)
        if open_mark is None:
            if match:
                open_mark = match.group(2)[0]
                open_length = len(match.group(2))
                open_line = number
                skipped += 1
                continue
            kept.append((number, line))
            continue

        # Inside a block. Only a matching closing fence gets us out.
        if match and match.group(2)[0] == open_mark and len(match.group(2)) >= open_length \
                and not match.group(3):
            open_mark = None
            skipped += 1
            continue
        skipped += 1

    if open_mark is not None:
        return kept, skipped, (
            "The fenced block opened on line %d never closes. Everything after it "
            "would be skipped without being read. Close it with %s."
            % (open_line, open_mark * open_length)
        )
    return kept, skipped, None


def clean_line(line: str) -> str:
    """Remove the quote marker and the bullet marker, keep the words."""
    work = re.sub(r"^\s*>\s?", "", line)
    work = _BULLET.sub("", work)
    work = re.sub(r"^\s*#{1,6}\s*", "", work)
    return work.strip()


def _quote_to_space(line: str) -> str:
    """Keep the column of a quoted line so its real depth is still visible."""
    return re.sub(r">", " ", line) if line.lstrip().startswith(">") else line


def _check_decision_block(
    decision_lines: list[tuple[int, str]], reasons: list[str]
) -> None:
    """A Move B question has one question and two or three priced options."""
    questions = [n for n, line in decision_lines if _QUESTION.match(line)]
    options = [(n, _OPTION.match(line)) for n, line in decision_lines if _OPTION.match(line)]
    picks = [n for n, line in decision_lines if _IF_PICK.match(line)]

    if len(questions) != 1:
        reasons.append(
            "A decision message asks exactly one question, and this one has %d. "
            "Split it, decide the parts you can decide, and ask about the one part "
            "you cannot." % len(questions)
        )
    if not 2 <= len(options) <= 3:
        reasons.append(
            "A decision message offers two or three options, and this one offers "
            "%d. More than three means it was not narrowed down." % len(options)
        )
    recommended = [n for n, m in options if m.group(2)]
    if len(recommended) != 1:
        reasons.append(
            "Exactly one option must be marked RECOMMENDED, and %d are. Without a "
            "recommendation the operator is being asked to do the work."
            % len(recommended)
        )
    if len(picks) != len(options):
        reasons.append(
            "Every option needs one line starting 'If you pick this:' saying what "
            "happens. There are %d options and %d of those lines."
            % (len(options), len(picks))
        )


def lint_message(text: str, banned_terms: list[str]) -> list[str]:
    """Return a list of plain reasons the message is bad. Empty means good."""
    reasons: list[str] = []
    lines = text.splitlines()
    kept, skipped, fence_error = strip_fences(lines)
    if fence_error:
        reasons.append(fence_error)

    # Invisible characters first. They make one sentence look like five and one
    # word look like another, so every count below is wrong while they are here.
    for number, line in kept:
        hidden = find_invisible(line)
        if hidden is not None:
            reasons.append(
                "Line %d holds the hidden character %s. It is silent on screen and "
                "silent out loud, and it hides the real shape of the sentence. "
                "Remove it." % (number, ascii_safe(hidden))
            )
            break

    # Structure a listener never hears.
    for number, line in kept:
        if HTML_STRUCTURE.search(line):
            reasons.append(
                "Line %d uses HTML layout tags. A listener hears none of that "
                "structure, and it can hide a nested list. Write plain lines. The "
                "line is: %s" % (number, ascii_safe(line.strip()))
            )
            break
    for number, line in kept:
        if _TABLE_ROW.match(line):
            reasons.append(
                "Line %d is a table row. A table is read cell by cell with no "
                "column names, so it cannot be followed by ear. Say it as "
                "sentences. The line is: %s" % (number, ascii_safe(line.strip()))
            )
            break

    # Rule 2: flat lists only. Up to three leading spaces is still a top level
    # item in normal markdown, so only a bullet deeper than one above it counts.
    bullet_depths: list[int] = []
    for number, raw in kept:
        line = _quote_to_space(raw)
        match = _BULLET.match(line)
        if not match:
            continue
        depth = len(match.group(1).expandtabs(4))
        deeper = any(depth >= previous + 2 for previous in bullet_depths)
        if deeper or depth >= 4:
            reasons.append(
                "Line %d is an indented list item, and indentation is silent when "
                "read aloud. Make the list flat. The line is: %s"
                % (number, ascii_safe(raw.strip()))
            )
            break
        bullet_depths.append(depth)

    # Rule 3: no emoji.
    for number, line in kept:
        found = None
        for ch in line:
            if is_emoji(ch):
                found = ch
                break
        if found is not None:
            reasons.append(
                "Line %d has an emoji (%s). A screen reader says its whole name "
                "and it breaks the sentence. The line is: %s"
                % (number, ascii_safe(found), ascii_safe(line.strip()))
            )
            break

    # The decision protocol shape is counted as a block, not as sentences.
    decision_lines = [
        (n, line)
        for n, line in kept
        if _QUESTION.match(line) or _OPTION.match(line) or _IF_PICK.match(line)
    ]
    if decision_lines:
        _check_decision_block(decision_lines, reasons)
    decision_numbers = {n for n, _ in decision_lines}

    # Sentences, kept with the line they came from.
    numbered: list[tuple[int, str]] = []
    body_lines = 0
    for number, line in kept:
        body = clean_line(line)
        if not body:
            continue
        body_lines += 1
        if number in decision_numbers:
            continue
        for sentence in split_sentences(body):
            numbered.append((number, sentence))

    # The whole message cannot live inside a fence.
    if body_lines == 0:
        if skipped > 0 and not fence_error:
            reasons.append(
                "Every line of this message is inside a fenced block, so nothing "
                "was checked. A fence is for pasted output, not for the message. "
                "Write the message in plain lines outside the fence."
            )
        elif skipped == 0:
            reasons.append("The message has no words in it.")

    # Rule 1: five sentences at most.
    if len(numbered) > MAX_SENTENCES:
        first_over = numbered[MAX_SENTENCES]
        reasons.append(
            "The message has %d sentences and the limit is %d. Cut it down. The "
            "first sentence over the limit is on line %d: %s"
            % (len(numbered), MAX_SENTENCES, first_over[0], ascii_safe(first_over[1]))
        )

    # Rule 5: thirty-five words at most in one sentence.
    for number, sentence in numbered:
        words = count_words(sentence)
        if words > MAX_WORDS_PER_SENTENCE:
            reasons.append(
                "The sentence on line %d has %d words and the limit is %d. Split it. "
                "The sentence is: %s"
                % (number, words, MAX_WORDS_PER_SENTENCE, ascii_safe(sentence))
            )

    # Rule 4: no jargon, no inflated adjectives. A word inside backticks is
    # quoted, not spoken as your own, so it is left alone.
    checked: list[tuple[int, str]] = []
    for number, line in kept:
        if number in decision_numbers or clean_line(line):
            spoken = _CODE_SPAN.sub(" ", clean_line(line) or line)
            checked.append((number, fold_for_matching(spoken)))
    joined_text = "\n".join(line for _, line in checked)

    for term in banned_terms:
        pattern = build_term_pattern(term)
        if not pattern.search(joined_text):
            continue
        where = None
        for number, line in checked:
            found = pattern.search(line)
            if found:
                where = (number, found.group(0), line)
                break
        if where is None:
            # The phrase runs across a line break.
            found = pattern.search(joined_text)
            reasons.append(
                "The phrase '%s' is banned, and it is split across two lines. Say "
                "it in plain words." % ascii_safe(found.group(0).replace("\n", " "))
            )
            continue
        number, hit, line = where
        kind = "phrase" if re.search(r"[-\s]", term.strip()) else "word"
        reasons.append(
            "The %s '%s' is banned. Say it in plain words. It is on line %d: %s"
            % (kind, ascii_safe(hit), number, ascii_safe(line.strip()))
        )

    return reasons


def check_file(path: Path, banned_terms: list[str]) -> tuple[bool, list[str]]:
    if not path.is_file():
        return False, ["There is no file at %s." % ascii_safe(str(path))]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return False, ["Cannot read %s: %s." % (ascii_safe(str(path)), error)]
    if not text.strip():
        return False, ["The message file is empty."]
    reasons = lint_message(text, banned_terms)
    return (len(reasons) == 0), reasons


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Selftest. A rejected bad message is a PASS. Blocking is the proof.
# ---------------------------------------------------------------------------

GOOD_MESSAGE = (
    "The fetch step returned empty pages for two sources.\n"
    "The cache stored those empty pages and handed them back as real text.\n"
    "I changed the cache to fetch again when a page is empty.\n"
    "Both sources now return real text.\n"
    "Next I will run the full fetch test set.\n"
)

GOOD_FLAT_LIST = (
    "Three files changed.\n"
    "- src/fetch/cache.py\n"
    "- src/fetch/client.py\n"
    "- tests/test_fetch.py\n"
)

GOOD_WITH_FENCE = (
    "Here is the count you asked for.\n"
    "```\n"
    "$ grep -c leverage report.md\n"
    "12 comprehensive matches\n"
    "```\n"
    "The number is twelve.\n"
)

GOOD_THREE_SPACE_LIST = (
    "Two files changed.\n"
    "   - src/fetch/cache.py\n"
    "   - tests/test_fetch.py\n"
)

GOOD_QUOTED_TERM = (
    "The check blocks one word I have to name here.\n"
    "The banned word is `comprehensive`, and it is in the list.\n"
)

GOOD_DECISION = (
    "Question: Do you want me to spend about forty dollars on a paid run tonight?\n"
    "\n"
    "Option 1 (RECOMMENDED): Yes, run it tonight.\n"
    "  If you pick this: you get the real report tomorrow and it costs forty dollars.\n"
    "\n"
    "Option 2: No, wait for the free test first.\n"
    "  If you pick this: it costs nothing, and the real report slips to Monday.\n"
)

BAD_TOO_MANY_SENTENCES = (
    "One thing happened. Two things happened. Three things happened.\n"
    "Four things happened. Five things happened. Six things happened.\n"
)

BAD_NESTED_LIST = (
    "Two files changed.\n"
    "- src/fetch/cache.py\n"
    "  - the empty body check\n"
    "- tests/test_fetch.py\n"
)

BAD_EMOJI = "The fetch tests pass now \U0001F600 and the run is clean.\n"

BAD_BANNED_WORD = (
    "I ran a comprehensive check of the fetch layer.\nThe run is clean.\n"
)

BAD_LONG_SENTENCE = (
    "The fetch step returned empty pages for two of the sources that the run "
    "needed, and the cache stored those empty pages and then handed them back "
    "to the caller as if they were real text, which is why the report came out "
    "short and wrong today.\n"
)

BAD_WHOLE_MESSAGE_IN_FENCE = (
    "```\n"
    "We leveraged a comprehensive plan \U0001F600.\n"
    "  - Nested item\n"
    "One. Two. Three. Four. Five. Six. Seven.\n"
    "```\n"
)

BAD_UNCLOSED_FENCE = (
    "Here is the output.\n"
    "```\n"
    "We leveraged a comprehensive plan.\n"
    "One. Two. Three. Four. Five. Six. Seven.\n"
)

BAD_MISMATCHED_FENCE = (
    "```\n"
    "We leveraged a comprehensive plan.\n"
    "~~~\n"
    "One. Two. Three. Four. Five. Six. Seven.\n"
)

BAD_INDENTED_FAKE_FENCE = (
    "    ```\n"
    "comprehensive operator prose\n"
    "    ```\n"
)

BAD_MORPHOLOGY = "We are leveraging the cache for the run.\n"

BAD_HYPHEN_ADJACENT = "This is a leverage-based plan for the week.\n"

BAD_EMPHASIS_SPLIT = "Take a deep **dive** into the cache path.\n"

BAD_PHRASE_ACROSS_LINES = "The plan holds going\nforward from here.\n"

BAD_ZERO_WIDTH = "One.​Two.​Three.​Four.​Five.​Six.\n"

BAD_HOMOGLYPH = "We leverаge the cache for this run.\n"

BAD_UNICODE_STOPS = "One。Two！Three？Four。Five。Six。\n"

BAD_SLASH_WORDS = (
    "The run touched " + "/".join("part%d" % n for n in range(1, 40)) + " today.\n"
)

BAD_UNICODE_BULLET = (
    "Two files changed.\n- src/fetch/cache.py\n  • the empty body check\n"
)

BAD_HTML_LIST = (
    "Two files changed.\n<ul><li>Parent<ul><li>Child</li></ul></li></ul>\n"
)

BAD_TABLE = (
    "Here are the counts.\n| file | count |\n| --- | --- |\n| cache.py | 12 |\n"
)

BAD_KEYCAP_EMOJI = "The fetch tests pass now 1⃣ and the run is clean.\n"

BAD_DECISION_FOUR_OPTIONS = (
    "Question: Which cache should I use?\n"
    "Option 1 (RECOMMENDED): Disk.\n"
    "  If you pick this: it survives a restart.\n"
    "Option 2: Memory.\n"
    "  If you pick this: it is faster and it is lost on restart.\n"
    "Option 3: Both.\n"
    "  If you pick this: it costs more to build.\n"
    "Option 4: Neither.\n"
    "  If you pick this: nothing is cached.\n"
)

BAD_DECISION_NO_RECOMMENDATION = (
    "Question: Which cache should I use?\n"
    "Option 1: Disk.\n"
    "  If you pick this: it survives a restart.\n"
    "Option 2: Memory.\n"
    "  If you pick this: it is faster and it is lost on restart.\n"
)


def _case_list() -> list[dict]:
    return [
        {"name": "good_message", "text": GOOD_MESSAGE, "accept": True},
        {"name": "good_flat_list", "text": GOOD_FLAT_LIST, "accept": True},
        {"name": "good_fenced_output_is_skipped", "text": GOOD_WITH_FENCE, "accept": True},
        {"name": "good_three_space_list_is_not_nested", "text": GOOD_THREE_SPACE_LIST, "accept": True},
        {"name": "good_banned_word_inside_backticks", "text": GOOD_QUOTED_TERM, "accept": True},
        {"name": "good_decision_question_with_two_options", "text": GOOD_DECISION, "accept": True},
        {
            "name": "bad_six_sentences",
            "text": BAD_TOO_MANY_SENTENCES,
            "accept": False,
            "expect": "has 6 sentences and the limit is 5",
        },
        {
            "name": "bad_nested_list",
            "text": BAD_NESTED_LIST,
            "accept": False,
            "expect": "indented list item",
        },
        {"name": "bad_emoji", "text": BAD_EMOJI, "accept": False, "expect": "has an emoji"},
        {
            "name": "bad_banned_word",
            "text": BAD_BANNED_WORD,
            "accept": False,
            "expect": "The word 'comprehensive' is banned",
        },
        {
            "name": "bad_long_sentence",
            "text": BAD_LONG_SENTENCE,
            "accept": False,
            "expect": "words and the limit is 35",
        },
        {
            "name": "bad_whole_message_hidden_in_a_fence",
            "text": BAD_WHOLE_MESSAGE_IN_FENCE,
            "accept": False,
            "expect": "Every line of this message is inside a fenced block",
        },
        {
            "name": "bad_unclosed_fence_swallows_the_rest",
            "text": BAD_UNCLOSED_FENCE,
            "accept": False,
            "expect": "never closes",
        },
        {
            "name": "bad_fence_closed_with_the_wrong_mark",
            "text": BAD_MISMATCHED_FENCE,
            "accept": False,
            "expect": "never closes",
        },
        {
            "name": "bad_four_space_fence_is_not_a_fence",
            "text": BAD_INDENTED_FAKE_FENCE,
            "accept": False,
            "expect": "The word 'comprehensive' is banned",
        },
        {
            "name": "bad_banned_word_with_an_ing_ending",
            "text": BAD_MORPHOLOGY,
            "accept": False,
            "expect": "The word 'leveraging' is banned",
        },
        {
            "name": "bad_banned_word_joined_by_a_hyphen",
            "text": BAD_HYPHEN_ADJACENT,
            "accept": False,
            "expect": "The word 'leverage' is banned",
        },
        {
            "name": "bad_banned_phrase_split_by_bold_marks",
            "text": BAD_EMPHASIS_SPLIT,
            "accept": False,
            "expect": "The phrase 'deep dive' is banned",
        },
        {
            "name": "bad_banned_phrase_split_across_two_lines",
            "text": BAD_PHRASE_ACROSS_LINES,
            "accept": False,
            "expect": "split across two lines",
        },
        {
            "name": "bad_zero_width_spaces_hide_six_sentences",
            "text": BAD_ZERO_WIDTH,
            "accept": False,
            "expect": "holds the hidden character",
        },
        {
            "name": "bad_lookalike_letter_hides_a_banned_word",
            "text": BAD_HOMOGLYPH,
            "accept": False,
            "expect": "is banned",
        },
        {
            "name": "bad_other_writing_system_full_stops",
            "text": BAD_UNICODE_STOPS,
            "accept": False,
            "expect": "has 6 sentences and the limit is 5",
        },
        {
            "name": "bad_words_joined_by_slashes",
            "text": BAD_SLASH_WORDS,
            "accept": False,
            "expect": "words and the limit is 35",
        },
        {
            "name": "bad_picture_bullet_nested",
            "text": BAD_UNICODE_BULLET,
            "accept": False,
            "expect": "indented list item",
        },
        {
            "name": "bad_nested_html_list",
            "text": BAD_HTML_LIST,
            "accept": False,
            "expect": "HTML layout tags",
        },
        {
            "name": "bad_markdown_table",
            "text": BAD_TABLE,
            "accept": False,
            "expect": "is a table row",
        },
        {
            "name": "bad_keycap_emoji",
            "text": BAD_KEYCAP_EMOJI,
            "accept": False,
            "expect": "has an emoji",
        },
        {
            "name": "bad_decision_with_four_options",
            "text": BAD_DECISION_FOUR_OPTIONS,
            "accept": False,
            "expect": "offers two or three options",
        },
        {
            "name": "bad_decision_with_no_recommendation",
            "text": BAD_DECISION_NO_RECOMMENDATION,
            "accept": False,
            "expect": "marked RECOMMENDED",
        },
    ]


def run_selftest() -> int:
    print("SELFTEST lint_operator_message")
    print("A bad message that gets REJECTED is a PASS. Blocking is the proof.")
    print("")

    passed = 0
    total = 1
    try:
        banned, doc_path = load_banned_terms()
        print(
            "[case 1] banned_list_loads: PASS (%d terms read from %s)"
            % (len(banned), ascii_safe(doc_path.name))
        )
        passed += 1
    except (FileNotFoundError, ValueError) as error:
        print("[case 1] banned_list_loads: FAIL (%s)" % ascii_safe(str(error)))
        print("")
        print("RESULT: 0 of 1 cases PASS")
        return 1

    for index, case in enumerate(_case_list(), start=2):
        total += 1
        reasons = lint_message(case["text"], banned)
        accepted = len(reasons) == 0
        name = case["name"]

        if case["accept"]:
            if accepted:
                print("[case %d] %s: ACCEPTED as expected -> PASS" % (index, name))
                passed += 1
            else:
                print("[case %d] %s: REJECTED but should pass -> FAIL" % (index, name))
                for reason in reasons:
                    print("           reason: %s" % ascii_safe(reason))
            continue

        if not accepted:
            wanted = case.get("expect", "")
            joined = " ".join(reasons)
            if wanted and wanted not in joined:
                print("[case %d] %s: REJECTED for the wrong reason -> FAIL" % (index, name))
                print("           wanted to see: %s" % ascii_safe(wanted))
                for reason in reasons:
                    print("           got: %s" % ascii_safe(reason))
            else:
                print("[case %d] %s: REJECTED as expected -> PASS" % (index, name))
                print("           reason: %s" % ascii_safe(reasons[0]))
                passed += 1
        else:
            print("[case %d] %s: ACCEPTED but must be blocked -> FAIL" % (index, name))

    print("")
    print("RESULT: %d of %d cases PASS" % (passed, total))
    return 0 if passed == total else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a message for the operator against the operator voice rule."
    )
    parser.add_argument("message", nargs="?", help="Path to the message file.")
    parser.add_argument(
        "--voice-doc", type=Path, default=None, help="Path to gov/operator_voice.md."
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run the built-in good and bad messages and print PASS or FAIL for each.",
    )
    args = parser.parse_args(argv)

    if args.selftest and args.message:
        print(
            "Give me a message file OR --selftest, not both. With both, the file "
            "you named would never be read.",
            file=sys.stderr,
        )
        return 2

    if args.selftest:
        return run_selftest()

    if not args.message:
        print("Give me a message file to check, or use --selftest.", file=sys.stderr)
        return 2

    try:
        banned, doc_path = load_banned_terms(args.voice_doc)
    except (FileNotFoundError, ValueError) as error:
        print("REJECTED: %s" % ascii_safe(str(error)), file=sys.stderr)
        return 1

    path = Path(args.message)
    ok, reasons = check_file(path, banned)
    policy_note = "  policy %s sha256 %s" % (
        ascii_safe(str(doc_path)),
        sha256_of(doc_path),
    )

    if ok:
        print("MESSAGE ACCEPTED: %s" % ascii_safe(str(path)))
        print("  sha256 %s" % sha256_of(path))
        print(policy_note)
        return 0

    print("MESSAGE REJECTED: %s" % ascii_safe(str(path)), file=sys.stderr)
    print(policy_note, file=sys.stderr)
    for number, reason in enumerate(reasons, start=1):
        print("  %d. %s" % (number, ascii_safe(reason)), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
