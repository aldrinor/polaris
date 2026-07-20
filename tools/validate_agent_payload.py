#!/usr/bin/env python3
"""Validate an agent payload file against gov/agent_payload.schema.json.

Why this exists: agents drip-feed. They answer part of a question, hold the
rest, and wait to be asked again. This checker rejects any payload that does
not say, in its first and only reply, what it did not cover.

It also refuses to take the agent's word for things it can check itself. When
a finding quotes a file in this repository, the checker opens the file and
reads the quoted lines. A quote that is not there is a rejection.

Usage:
    python3 tools/validate_agent_payload.py path/to/payload.json
    python3 tools/validate_agent_payload.py path/to/payload.json --repo-root .
    python3 tools/validate_agent_payload.py --selftest

Exit codes:
    0  accepted
    1  rejected, or the payload or schema could not be read
    2  the command line itself was wrong: no file given, or --selftest was
       given together with a file, which would check the wrong thing

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

# The text rules live next to this file so the payload checker and the voice
# checker cannot drift apart on what counts as one sentence.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plain_text_rules import (  # noqa: E402
    ascii_safe,
    count_sentences,
    fold_confusables,
    find_invisible,
)

SCHEMA_NAME = "agent_payload.schema.json"
FULL_COVERAGE = "FULL_COVERAGE"
STATUS_NEEDS_BLOCKERS = ("PARTIAL", "BLOCKED", "FAILED")

# A full coverage claim has to show a command and what it printed.
_COMMAND_PROMPT = re.compile(r"(?m)^\s*(\$|>>>|PS[ >]|#)\s*\S")
_MIN_PROOF_LENGTH = 20

_URL_PREFIX = ("http://", "https://")


def find_schema_path(start: Path | None = None) -> Path | None:
    """Look for the schema next to this script, then upward from the caller."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "gov" / SCHEMA_NAME,
        here.parent / "gov" / SCHEMA_NAME,
    ]
    base = (start or Path.cwd()).resolve()
    for folder in [base] + list(base.parents):
        candidates.append(folder / "gov" / SCHEMA_NAME)
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_schema(path: Path | None = None) -> dict[str, Any]:
    """Read the schema file. Fail loudly if it is missing or broken."""
    schema_path = path or find_schema_path()
    if schema_path is None:
        raise FileNotFoundError(
            "Cannot find gov/%s. The checker needs the schema to run." % SCHEMA_NAME
        )
    text = schema_path.read_text(encoding="utf-8")
    return json.loads(text)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    """Two keys with the same name hide one value behind the other."""
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(
                "the key '%s' appears more than once in the same object, so one "
                "value is hidden behind the other" % ascii_safe(key)
            )
        seen[key] = value
    return seen


def _reject_constants(token: str) -> Any:
    raise ValueError(
        "the value %s is not a real number, and a number field cannot hold it"
        % ascii_safe(token)
    )


def _reject_huge_float(token: str) -> float:
    """A number so large it becomes infinity is not a measurement."""
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(
            "the value %s is too large to be a real number, and a number field "
            "cannot hold it" % ascii_safe(token)
        )
    return value


def load_payload_text(raw: str) -> Any:
    """Parse payload JSON, refusing duplicate keys and non numbers."""
    return json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constants,
        parse_float=_reject_huge_float,
    )


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "true or false"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "an object"
    if isinstance(value, (int, float)):
        return "a number"
    if value is None:
        return "empty"
    return type(value).__name__


def _check_text(
    value: Any,
    label: str,
    reasons: list[str],
    one_line: bool = False,
    max_sentences: int | None = None,
) -> bool:
    if not isinstance(value, str):
        reasons.append("%s must be text, but it is %s." % (label, _type_name(value)))
        return False
    if not value.strip():
        reasons.append("%s is empty. Write the real content there." % label)
        return False

    hidden = find_invisible(value)
    if hidden is not None:
        reasons.append(
            "%s holds the hidden character %s. Invisible characters can make one "
            "sentence look like several, or make a word look like another word. "
            "Remove it." % (label, ascii_safe(hidden))
        )
        return False

    if one_line and ("\n" in value or "\r" in value):
        reasons.append(
            "%s must be one line, and it holds a line break. Split it into "
            "separate entries." % label
        )
        return False

    if max_sentences is not None:
        found = count_sentences(value)
        if found > max_sentences:
            reasons.append(
                "%s has %d sentences and the limit is %d. Cut it down."
                % (label, found, max_sentences)
            )
            return False
    return True


def _plural(count: int, word: str) -> str:
    return "%d %s" % (count, word if count == 1 else word + "s")


def _check_extra_keys(
    item: dict, definition: dict, label: str, reasons: list[str]
) -> None:
    """Enforce additionalProperties false on a nested object."""
    if definition.get("additionalProperties") is not False:
        return
    known = set(definition.get("properties", {}).keys())
    for key in item:
        if key not in known:
            reasons.append(
                "%s has an extra key '%s'. The contract has one fixed shape, so "
                "extra keys are rejected. Anything you want to add goes in an "
                "existing field." % (label, ascii_safe(str(key)))
            )


def _check_string_list(
    value: Any, label: str, reasons: list[str], min_items: int
) -> None:
    if not isinstance(value, list):
        reasons.append("%s must be a list, but it is %s." % (label, _type_name(value)))
        return
    if len(value) < min_items:
        reasons.append(
            "%s needs at least %s, and it has %d."
            % (label, _plural(min_items, "entry"), len(value))
        )
        return
    for index, item in enumerate(value):
        _check_text(item, "%s entry %d" % (label, index + 1), reasons, one_line=True)


# ---------------------------------------------------------------------------
# Evidence is opened and read. A quote that is not in the file is a rejection.
# ---------------------------------------------------------------------------

_LINES_EXACT = re.compile(r"\A(?:([0-9]+)(?:-([0-9]+))?|n/a)\Z")


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class EvidenceVerifier:
    """Open the quoted file and check the quote is really at those lines."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.checked = 0
        self.unchecked: list[str] = []

    def verify(
        self, path_text: str, lines_text: str, quote: str, label: str, reasons: list[str]
    ) -> None:
        if path_text.startswith(_URL_PREFIX):
            self.unchecked.append(
                "%s quotes the address %s, which cannot be opened offline."
                % (label, ascii_safe(path_text))
            )
            return

        if lines_text == "n/a":
            reasons.append(
                "%s gives a file path but writes n/a for the lines. A file has "
                "lines. Write the line number or range the quote came from, so a "
                "reader can open it." % label
            )
            return

        try:
            target = (self.repo_root / path_text).resolve()
        except (OSError, ValueError):
            reasons.append("%s evidence path cannot be read as a path." % label)
            return

        try:
            target.relative_to(self.repo_root)
        except ValueError:
            reasons.append(
                "%s evidence path %s points outside the folder being checked."
                % (label, ascii_safe(path_text))
            )
            return

        if not target.is_file():
            reasons.append(
                "%s quotes %s, and there is no such file. Evidence that cannot be "
                "opened is not evidence." % (label, ascii_safe(path_text))
            )
            return

        try:
            file_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as error:
            reasons.append(
                "%s quotes %s and it could not be read: %s."
                % (label, ascii_safe(path_text), error)
            )
            return

        match = _LINES_EXACT.match(lines_text)
        if match is None or match.group(1) is None:
            return  # shape was already reported by the caller
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start

        if start < 1:
            reasons.append("%s evidence starts at line %d, and files start at line 1."
                           % (label, start))
            return
        if end < start:
            reasons.append(
                "%s evidence line range runs backwards, from %d to %d. Write the "
                "smaller number first." % (label, start, end)
            )
            return
        if end > len(file_lines):
            reasons.append(
                "%s quotes lines %d to %d of %s, and that file only has %s."
                % (label, start, end, ascii_safe(path_text),
                   _plural(len(file_lines), "line"))
            )
            return

        span = _normalize_space("\n".join(file_lines[start - 1:end]))
        wanted = _normalize_space(quote)
        self.checked += 1
        if wanted and wanted not in span:
            reasons.append(
                "%s quotes text that is not on lines %d to %d of %s. The quote must "
                "be copied from the real place, not written from memory. The file "
                "says: %s"
                % (label, start, end, ascii_safe(path_text),
                   ascii_safe(span[:160]) or "(nothing)")
            )


def _check_finding(
    item: Any,
    index: int,
    schema: dict,
    reasons: list[str],
    verifier: EvidenceVerifier | None,
) -> str | None:
    label = "Finding %d" % (index + 1)
    if not isinstance(item, dict):
        reasons.append("%s must be an object, but it is %s." % (label, _type_name(item)))
        return None

    finding_def = schema.get("definitions", {}).get("finding", {})
    _check_extra_keys(item, finding_def, label, reasons)
    for key in finding_def.get("required", []):
        if key not in item:
            reasons.append("%s is missing the key '%s'." % (label, key))

    finding_id = None
    if "id" in item and _check_text(item["id"], "%s id" % label, reasons, one_line=True):
        finding_id = item["id"].strip()
    if "claim" in item:
        _check_text(
            item["claim"], "%s claim" % label, reasons, one_line=True, max_sentences=1
        )
    if "recommendation" in item:
        _check_text(
            item["recommendation"],
            "%s recommendation" % label,
            reasons,
            one_line=True,
            max_sentences=1,
        )

    severity_rules = finding_def.get("properties", {}).get("severity", {})
    low = severity_rules.get("minimum", 1)
    high = severity_rules.get("maximum", 3)
    if "severity" in item:
        severity = item["severity"]
        if isinstance(severity, bool) or not isinstance(severity, int):
            reasons.append(
                "%s severity must be a whole number from %d to %d, but it is %s."
                % (label, low, high, _type_name(severity))
            )
        elif severity < low or severity > high:
            reasons.append(
                "%s severity is %d. It must be from %d to %d, where %d is worst."
                % (label, severity, low, high, low)
            )

    if "evidence" not in item:
        return finding_id
    evidence = item["evidence"]
    if not isinstance(evidence, dict):
        reasons.append(
            "%s evidence must be an object, but it is %s."
            % (label, _type_name(evidence))
        )
        return finding_id

    evidence_def = schema.get("definitions", {}).get("evidence", {})
    _check_extra_keys(evidence, evidence_def, "%s evidence" % label, reasons)
    for key in evidence_def.get("required", []):
        if key not in evidence:
            reasons.append("%s evidence is missing the key '%s'." % (label, key))

    path_ok = "path" in evidence and _check_text(
        evidence["path"], "%s evidence path" % label, reasons, one_line=True
    )

    quote_ok = False
    if "quote" in evidence:
        quote = evidence["quote"]
        if not isinstance(quote, str) or not quote.strip():
            reasons.append(
                "%s has an empty evidence quote. Every finding must quote the real "
                "text it came from, or it is only a guess." % label
            )
        else:
            quote_ok = True

    lines_ok = False
    if "lines" in evidence:
        lines = evidence["lines"]
        if not isinstance(lines, str) or _LINES_EXACT.match(lines) is None:
            reasons.append(
                "%s evidence lines is '%s'. Write a line number like 42, a range "
                "like 10-20, or n/a." % (label, ascii_safe(str(lines)))
            )
        else:
            lines_ok = True

    if verifier is not None and path_ok and quote_ok and lines_ok:
        verifier.verify(
            evidence["path"].strip(),
            evidence["lines"],
            evidence["quote"],
            "%s evidence" % label,
            reasons,
        )
    return finding_id


def _sentinel_lookalike(area: str) -> bool:
    """True when the area imitates FULL_COVERAGE without being it."""
    folded = fold_confusables(area).strip().upper().replace(" ", "_").replace("-", "_")
    return folded == FULL_COVERAGE and area.strip() != FULL_COVERAGE


def _check_not_covered(value: Any, schema: dict, reasons: list[str]) -> bool:
    """Check the anti drip list. Returns True when it is a full coverage claim."""
    rules = schema.get("properties", {}).get("not_covered", {})
    min_items = rules.get("minItems", 1)

    if not isinstance(value, list):
        reasons.append("not_covered must be a list, but it is %s." % _type_name(value))
        return False
    if len(value) < min_items:
        reasons.append(
            "not_covered is empty. This is never allowed. Write down every part of "
            "the scope you did not reach. If you reached all of it, write one entry "
            "with area set to %s and put the proof in the proof field." % FULL_COVERAGE
        )
        return False

    entry_def = schema.get("definitions", {}).get("not_covered_entry", {})
    required = entry_def.get("required", ["area", "reason"])
    full_coverage_at: list[int] = []

    for index, item in enumerate(value):
        label = "not_covered entry %d" % (index + 1)
        if not isinstance(item, dict):
            reasons.append(
                "%s must be an object with area and reason, but it is %s."
                % (label, _type_name(item))
            )
            continue
        _check_extra_keys(item, entry_def, label, reasons)
        for key in required:
            if key not in item:
                reasons.append("%s is missing the key '%s'." % (label, key))
        if "area" in item:
            _check_text(item["area"], "%s area" % label, reasons, one_line=True)
        if "reason" in item:
            _check_text(item["reason"], "%s reason" % label, reasons)
        if "proof" in item:
            _check_text(item["proof"], "%s proof" % label, reasons)

        area = item.get("area")
        if not isinstance(area, str):
            continue

        if _sentinel_lookalike(area):
            reasons.append(
                "%s area looks like %s but is spelled with lookalike letters. Write "
                "the plain word, or the coverage rule is silently skipped."
                % (label, FULL_COVERAGE)
            )
            continue

        if area.strip() != FULL_COVERAGE:
            continue

        full_coverage_at.append(index + 1)
        proof = item.get("proof")
        if not isinstance(proof, str) or not proof.strip():
            reasons.append(
                "%s claims full coverage but shows no proof. Paste the command "
                "you ran and its output in the proof field." % label
            )
        elif (
            _COMMAND_PROMPT.search(proof) is None
            or not any(ch.isdigit() for ch in proof)
            or len(proof.strip()) < _MIN_PROOF_LENGTH
        ):
            reasons.append(
                "%s claims full coverage and its proof does not show a command and "
                "what it printed. Start a line with $ and give the real command, "
                "then the real count it returned." % label
            )

    if full_coverage_at and len(value) > 1:
        reasons.append(
            "not_covered entry %d claims full coverage while the list also names "
            "work that was left out. Both cannot be true. Either the coverage was "
            "not full, or the other entries do not belong." % full_coverage_at[0]
        )
        return False

    return bool(full_coverage_at)


def _check_metrics(value: Any, schema: dict, reasons: list[str]) -> None:
    if not isinstance(value, dict):
        reasons.append("metrics must be an object, but it is %s." % _type_name(value))
        return
    metrics_def = schema.get("definitions", {}).get("metrics", {})
    _check_extra_keys(value, metrics_def, "metrics", reasons)
    for key in metrics_def.get("required", []):
        if key not in value:
            reasons.append("metrics is missing the key '%s'." % key)
    for key in ("tokens_in", "tokens_out"):
        if key in value:
            number = value[key]
            if isinstance(number, bool) or not isinstance(number, int):
                reasons.append("metrics %s must be a whole number." % key)
            elif number < 0:
                reasons.append("metrics %s cannot be below zero." % key)
    if "wall_seconds" in value:
        seconds = value["wall_seconds"]
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            reasons.append("metrics wall_seconds must be a number.")
        elif not math.isfinite(seconds):
            reasons.append(
                "metrics wall_seconds is not a real number. A run takes a real "
                "number of seconds."
            )
        elif seconds < 0:
            reasons.append("metrics wall_seconds cannot be below zero.")


def validate_payload(
    payload: Any,
    schema: dict,
    verifier: EvidenceVerifier | None = None,
    expect_task_id: str | None = None,
    expect_agent_id: str | None = None,
) -> list[str]:
    """Return a list of plain reasons the payload is bad. Empty list means good."""
    reasons: list[str] = []

    if not isinstance(payload, dict):
        return ["The payload must be a JSON object, but it is %s." % _type_name(payload)]

    required = schema.get("required", [])
    for key in required:
        if key not in payload:
            reasons.append("The payload is missing the key '%s'." % key)

    known = set(schema.get("properties", {}).keys())
    if schema.get("additionalProperties") is False:
        for key in payload:
            if key not in known:
                reasons.append(
                    "The payload has an extra key '%s'. The contract has one fixed "
                    "shape, so extra keys are rejected." % ascii_safe(str(key))
                )

    props = schema.get("properties", {})

    expected_version = props.get("schema", {}).get("const")
    if "schema" in payload and expected_version is not None:
        if payload["schema"] != expected_version:
            reasons.append(
                "The schema field says '%s'. It must say '%s'."
                % (ascii_safe(str(payload["schema"])), expected_version)
            )

    for key in ("agent_id", "task_id", "model"):
        if key in payload:
            _check_text(payload[key], "The field %s" % key, reasons, one_line=True)
    if "next_action" in payload:
        _check_text(
            payload["next_action"],
            "The field next_action",
            reasons,
            one_line=True,
            max_sentences=1,
        )

    # The caller owns the identity. An agent naming its own task proves nothing.
    if expect_task_id is not None and payload.get("task_id") != expect_task_id:
        reasons.append(
            "The payload says it answers task '%s', and the caller asked for '%s'. "
            "This is a reply to a different task."
            % (ascii_safe(str(payload.get("task_id"))), ascii_safe(expect_task_id))
        )
    if expect_agent_id is not None and payload.get("agent_id") != expect_agent_id:
        reasons.append(
            "The payload says it came from '%s', and the caller spawned '%s'."
            % (ascii_safe(str(payload.get("agent_id"))), ascii_safe(expect_agent_id))
        )

    status_values = props.get("status", {}).get("enum", [])
    if "status" in payload and status_values:
        if payload["status"] not in status_values:
            reasons.append(
                "status is '%s'. It must be one of: %s."
                % (ascii_safe(str(payload["status"])), ", ".join(status_values))
            )

    confidence_values = props.get("confidence", {}).get("enum", [])
    if "confidence" in payload and confidence_values:
        if payload["confidence"] not in confidence_values:
            reasons.append(
                "confidence is '%s'. It must be one of: %s."
                % (ascii_safe(str(payload["confidence"])), ", ".join(confidence_values))
            )

    max_sentences = props.get("summary", {}).get("x_max_sentences", 3)
    if "summary" in payload:
        _check_text(
            payload["summary"], "The summary", reasons, max_sentences=max_sentences
        )

    seen_ids: dict[str, int] = {}
    if "findings" in payload:
        findings = payload["findings"]
        if not isinstance(findings, list):
            reasons.append("findings must be a list, but it is %s." % _type_name(findings))
        else:
            for index, item in enumerate(findings):
                finding_id = _check_finding(item, index, schema, reasons, verifier)
                if finding_id is None:
                    continue
                if finding_id in seen_ids:
                    reasons.append(
                        "Finding %d reuses the id '%s', which finding %d already "
                        "used. Two findings with one name cannot be tracked apart."
                        % (index + 1, ascii_safe(finding_id), seen_ids[finding_id])
                    )
                else:
                    seen_ids[finding_id] = index + 1

    if "work_done" in payload:
        min_items = props.get("work_done", {}).get("minItems", 1)
        _check_string_list(payload["work_done"], "work_done", reasons, min_items)

    claims_full_coverage = False
    if "not_covered" in payload:
        claims_full_coverage = _check_not_covered(payload["not_covered"], schema, reasons)

    blocker_count = 0
    if "blockers" in payload:
        blockers = payload["blockers"]
        if not isinstance(blockers, list):
            reasons.append("blockers must be a list, but it is %s." % _type_name(blockers))
        else:
            blocker_count = len(blockers)
            for index, item in enumerate(blockers):
                _check_text(
                    item, "blockers entry %d" % (index + 1), reasons, one_line=True
                )

    # ------------------------------------------------------------------
    # DONE is derived, not asserted. The word has to agree with the rest.
    # ------------------------------------------------------------------
    status = payload.get("status")
    if status in STATUS_NEEDS_BLOCKERS and isinstance(payload.get("blockers"), list):
        if blocker_count == 0:
            reasons.append(
                "status is %s but the blockers list is empty. Say what stopped "
                "you, in plain words, one line each." % status
            )
    if status == "DONE":
        if blocker_count > 0:
            reasons.append(
                "status is DONE and the blockers list names %s. Something that "
                "stopped you means the task is not done. Write PARTIAL or BLOCKED."
                % _plural(blocker_count, "blocker")
            )
        if isinstance(payload.get("not_covered"), list) and not claims_full_coverage:
            reasons.append(
                "status is DONE and not_covered names work that was left out. Those "
                "two cannot both be true. Write PARTIAL, or claim %s with proof."
                % FULL_COVERAGE
            )

    if "metrics" in payload:
        _check_metrics(payload["metrics"], schema, reasons)

    return reasons


def check_file(
    path: Path,
    schema: dict,
    verifier: EvidenceVerifier | None = None,
    expect_task_id: str | None = None,
    expect_agent_id: str | None = None,
) -> tuple[bool, list[str]]:
    if not path.is_file():
        return False, ["There is no file at %s." % ascii_safe(str(path))]
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        return False, ["Cannot read %s: %s." % (ascii_safe(str(path)), error)]
    try:
        payload = load_payload_text(raw)
    except json.JSONDecodeError as error:
        return False, [
            "The file is not valid JSON. The reader stopped at line %d, column %d: %s."
            % (error.lineno, error.colno, error.msg)
        ]
    except ValueError as error:
        return False, ["The file cannot be read as a payload: %s." % ascii_safe(str(error))]
    reasons = validate_payload(payload, schema, verifier, expect_task_id, expect_agent_id)
    return (len(reasons) == 0), reasons


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Selftest. A rejected bad payload is a PASS. Blocking is the proof.
# ---------------------------------------------------------------------------

def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _real_evidence() -> dict:
    """Quote a real line of this very file, found at run time so it cannot drift."""
    here = Path(__file__).resolve()
    lines = here.read_text(encoding="utf-8").splitlines()
    wanted = 'FULL_COVERAGE = "FULL_COVERAGE"'
    for number, line in enumerate(lines, start=1):
        if line.strip() == wanted:
            return {
                "path": here.relative_to(repo_root()).as_posix(),
                "lines": str(number),
                "quote": wanted,
            }
    raise RuntimeError("The selftest anchor line is gone from this file.")


def _good_payload() -> dict:
    return {
        "schema": "agent_payload/v1",
        "agent_id": "claude_reviewer_01",
        "task_id": "I-gov-001",
        "model": "claude-opus-4-8",
        "status": "PARTIAL",
        "summary": "I read the payload checker end to end. The coverage rule is the "
                   "only hard gate. The rest is shape checking.",
        "findings": [
            {
                "id": "F1",
                "severity": 2,
                "claim": "The full coverage sentinel is a plain string constant.",
                "evidence": _real_evidence(),
                "recommendation": "Check lookalike spellings of the sentinel too.",
            }
        ],
        "work_done": [
            "Read tools/validate_agent_payload.py from the first line to the last.",
            "Ran the built in cases and recorded which ones block.",
        ],
        "not_covered": [
            {
                "area": "The pull request body checker",
                "reason": "It is a different file and was outside this task.",
            }
        ],
        "blockers": ["The pull request checker was not in scope for this pass."],
        "metrics": {"tokens_in": 41000, "tokens_out": 2600, "wall_seconds": 74.5},
        "next_action": "Read tools/check_pr_body.py with the same care.",
        "confidence": "high",
    }


def _done_payload() -> dict:
    """A DONE payload has to claim full coverage, with proof, and no blockers."""
    payload = _good_payload()
    payload["status"] = "DONE"
    payload["blockers"] = []
    payload["not_covered"] = [
        {
            "area": FULL_COVERAGE,
            "reason": "Every file named in the task was read start to end.",
            "proof": "$ ls tools/*.py | wc -l -> 3, and all 3 appear in work_done.",
        }
    ]
    return payload


def _case_list() -> list[dict]:
    """Each case: name, payload, whether it should be accepted, expected words."""
    cases: list[dict] = []

    cases.append({"name": "good_partial_payload", "payload": _good_payload(), "accept": True})
    cases.append({"name": "good_done_full_coverage", "payload": _done_payload(), "accept": True})

    empty = _good_payload()
    empty["not_covered"] = []
    cases.append({
        "name": "bad_empty_not_covered",
        "payload": empty,
        "accept": False,
        "expect": "not_covered is empty",
    })

    no_proof = _done_payload()
    no_proof["not_covered"] = [{"area": FULL_COVERAGE, "reason": "I did all of it."}]
    cases.append({
        "name": "bad_full_coverage_without_proof",
        "payload": no_proof,
        "accept": False,
        "expect": "claims full coverage but shows no proof",
    })

    thin_proof = _done_payload()
    thin_proof["not_covered"][0]["proof"] = "x"
    cases.append({
        "name": "bad_full_coverage_proof_is_one_letter",
        "payload": thin_proof,
        "accept": False,
        "expect": "does not show a command and what it printed",
    })

    done_with_gap = _good_payload()
    done_with_gap["status"] = "DONE"
    done_with_gap["blockers"] = []
    cases.append({
        "name": "bad_done_while_naming_uncovered_work",
        "payload": done_with_gap,
        "accept": False,
        "expect": "status is DONE and not_covered names work that was left out",
    })

    done_with_blockers = _done_payload()
    done_with_blockers["blockers"] = ["The build machine was offline all afternoon."]
    cases.append({
        "name": "bad_done_while_naming_a_blocker",
        "payload": done_with_blockers,
        "accept": False,
        "expect": "status is DONE and the blockers list names 1 blocker",
    })

    mixed = _done_payload()
    mixed["not_covered"].append(
        {"area": "src/unread.py", "reason": "I ran out of budget."}
    )
    cases.append({
        "name": "bad_full_coverage_mixed_with_a_gap",
        "payload": mixed,
        "accept": False,
        "expect": "claims full coverage while the list also names",
    })

    lookalike = _done_payload()
    lookalike["not_covered"][0]["area"] = "FULL_COVERAGЕ"
    cases.append({
        "name": "bad_full_coverage_lookalike_letters",
        "payload": lookalike,
        "accept": False,
        "expect": "lookalike letters",
    })

    no_quote = _good_payload()
    no_quote["findings"][0]["evidence"]["quote"] = ""
    cases.append({
        "name": "bad_finding_without_quote",
        "payload": no_quote,
        "accept": False,
        "expect": "empty evidence quote",
    })

    invented_quote = _good_payload()
    invented_quote["findings"][0]["evidence"]["quote"] = "the cache returns early here"
    cases.append({
        "name": "bad_quote_is_not_in_the_file",
        "payload": invented_quote,
        "accept": False,
        "expect": "quotes text that is not on lines",
    })

    missing_file = _good_payload()
    missing_file["findings"][0]["evidence"]["path"] = "src/invented.py"
    cases.append({
        "name": "bad_evidence_file_does_not_exist",
        "payload": missing_file,
        "accept": False,
        "expect": "there is no such file",
    })

    backwards = _good_payload()
    backwards["findings"][0]["evidence"]["lines"] = "80-10"
    cases.append({
        "name": "bad_evidence_line_range_runs_backwards",
        "payload": backwards,
        "accept": False,
        "expect": "runs backwards",
    })

    na_lines = _good_payload()
    na_lines["findings"][0]["evidence"]["lines"] = "n/a"
    cases.append({
        "name": "bad_local_file_with_n_a_lines",
        "payload": na_lines,
        "accept": False,
        "expect": "writes n/a for the lines",
    })

    trailing = _good_payload()
    trailing["findings"][0]["evidence"]["lines"] = "42\n"
    cases.append({
        "name": "bad_evidence_lines_with_trailing_newline",
        "payload": trailing,
        "accept": False,
        "expect": "Write a line number like 42",
    })

    extra_nested = _good_payload()
    extra_nested["findings"][0]["withheld_finding"] = "F2"
    cases.append({
        "name": "bad_extra_key_inside_a_finding",
        "payload": extra_nested,
        "accept": False,
        "expect": "has an extra key 'withheld_finding'",
    })

    duplicate_ids = _good_payload()
    duplicate_ids["findings"].append(json.loads(json.dumps(_good_payload()["findings"][0])))
    cases.append({
        "name": "bad_two_findings_share_one_id",
        "payload": duplicate_ids,
        "accept": False,
        "expect": "reuses the id 'F1'",
    })

    hidden = _good_payload()
    hidden["summary"] = "One.​Two.​Three.​Four.​Five."
    cases.append({
        "name": "bad_hidden_characters_in_summary",
        "payload": hidden,
        "accept": False,
        "expect": "holds the hidden character",
    })

    many_lines = _good_payload()
    many_lines["work_done"] = ["Looked at a.py\nSkipped b.py"]
    cases.append({
        "name": "bad_work_done_entry_is_two_lines",
        "payload": many_lines,
        "accept": False,
        "expect": "must be one line",
    })

    two_sentences = _good_payload()
    two_sentences["next_action"] = "Do one thing. Then hide the rest."
    cases.append({
        "name": "bad_next_action_is_two_sentences",
        "payload": two_sentences,
        "accept": False,
        "expect": "The field next_action has 2 sentences",
    })

    no_stops = _good_payload()
    no_stops["summary"] = "One\nTwo\nThree\nFour"
    cases.append({
        "name": "bad_summary_uses_line_breaks_not_full_stops",
        "payload": no_stops,
        "accept": False,
        "expect": "The summary has 4 sentences",
    })

    unicode_stops = _good_payload()
    unicode_stops["summary"] = "One。Two！Three？Four。"
    cases.append({
        "name": "bad_summary_uses_other_writing_system_stops",
        "payload": unicode_stops,
        "accept": False,
        "expect": "The summary has 4 sentences",
    })

    infinite = _good_payload()
    infinite["metrics"]["wall_seconds"] = float("inf")
    cases.append({
        "name": "bad_wall_seconds_is_not_a_real_number",
        "payload": infinite,
        "accept": False,
        "expect": "not a real number",
    })

    partial = _good_payload()
    partial["blockers"] = []
    cases.append({
        "name": "bad_partial_without_blockers",
        "payload": partial,
        "accept": False,
        "expect": "status is PARTIAL but the blockers list is empty",
    })

    long_summary = _good_payload()
    long_summary["summary"] = "One thing. Two things. Three things. Four things."
    cases.append({
        "name": "bad_summary_too_long",
        "payload": long_summary,
        "accept": False,
        "expect": "The summary has 4 sentences",
    })

    bad_severity = _good_payload()
    bad_severity["findings"][0]["severity"] = 7
    cases.append({
        "name": "bad_severity_out_of_range",
        "payload": bad_severity,
        "accept": False,
        "expect": "severity is 7",
    })

    missing_key = _good_payload()
    del missing_key["next_action"]
    cases.append({
        "name": "bad_missing_next_action",
        "payload": missing_key,
        "accept": False,
        "expect": "missing the key 'next_action'",
    })

    wrong_version = _good_payload()
    wrong_version["schema"] = "agent_payload/v0"
    cases.append({
        "name": "bad_wrong_schema_version",
        "payload": wrong_version,
        "accept": False,
        "expect": "It must say 'agent_payload/v1'",
    })

    return cases


def _text_case_list() -> list[dict]:
    """Cases that have to be checked as raw text, before JSON becomes a dict."""
    good = json.dumps(_done_payload())
    return [
        {
            "name": "bad_duplicate_key_hides_a_value",
            "text": good.replace('"status": "DONE"', '"status": "PARTIAL", "status": "DONE"', 1),
            "expect": "appears more than once",
        },
        {
            "name": "bad_not_a_number_literal",
            "text": good.replace('"wall_seconds": 74.5', '"wall_seconds": NaN', 1),
            "expect": "is not a real number",
        },
        {
            "name": "bad_number_too_large_to_be_real",
            "text": good.replace('"wall_seconds": 74.5', '"wall_seconds": 1e400', 1),
            "expect": "too large to be a real number",
        },
    ]


def run_selftest() -> int:
    print("SELFTEST validate_agent_payload")
    print("A bad payload that gets REJECTED is a PASS. Blocking is the proof.")
    print("")

    passed = 0
    total = 0

    total += 1
    try:
        schema = load_schema()
        required_count = len(schema.get("required", []))
        min_items = schema.get("properties", {}).get("not_covered", {}).get("minItems")
        if required_count >= 13 and min_items == 1:
            print(
                "[case 1] schema_file_loads: PASS (%d required keys, not_covered "
                "minItems=%s)" % (required_count, min_items)
            )
            passed += 1
        else:
            print(
                "[case 1] schema_file_loads: FAIL (required=%d, not_covered "
                "minItems=%s)" % (required_count, min_items)
            )
    except (FileNotFoundError, json.JSONDecodeError) as error:
        print("[case 1] schema_file_loads: FAIL (%s)" % ascii_safe(str(error)))
        print("")
        print("RESULT: 0 of 1 cases PASS")
        return 1

    verifier = EvidenceVerifier(repo_root())
    index = 1

    for case in _case_list():
        index += 1
        total += 1
        reasons = validate_payload(case["payload"], schema, verifier)
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
                print(
                    "[case %d] %s: REJECTED for the wrong reason -> FAIL" % (index, name)
                )
                print("           wanted to see: %s" % ascii_safe(wanted))
                for reason in reasons:
                    print("           got: %s" % ascii_safe(reason))
            else:
                print("[case %d] %s: REJECTED as expected -> PASS" % (index, name))
                print("           reason: %s" % ascii_safe(reasons[0]))
                passed += 1
        else:
            print("[case %d] %s: ACCEPTED but must be blocked -> FAIL" % (index, name))

    for case in _text_case_list():
        index += 1
        total += 1
        name = case["name"]
        try:
            load_payload_text(case["text"])
            print("[case %d] %s: ACCEPTED but must be blocked -> FAIL" % (index, name))
        except (ValueError, json.JSONDecodeError) as error:
            message = str(error)
            if case["expect"] in message:
                print("[case %d] %s: REJECTED as expected -> PASS" % (index, name))
                print("           reason: %s" % ascii_safe(message))
                passed += 1
            else:
                print("[case %d] %s: REJECTED for the wrong reason -> FAIL" % (index, name))
                print("           got: %s" % ascii_safe(message))

    index += 1
    total += 1
    code = main(["some_real_payload.json", "--selftest"])
    if code == 2:
        print(
            "[case %d] bad_selftest_together_with_a_file: REFUSED as expected -> PASS"
            % index
        )
        passed += 1
    else:
        print(
            "[case %d] bad_selftest_together_with_a_file: returned %d, wanted 2 -> FAIL"
            % (index, code)
        )

    print("")
    print(
        "Evidence really opened and read during this run: %d quote(s) checked "
        "against the file on disk." % verifier.checked
    )
    print("RESULT: %d of %d cases PASS" % (passed, total))
    return 0 if passed == total else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check an agent payload file against the payload contract."
    )
    parser.add_argument("payload", nargs="?", help="Path to the payload JSON file.")
    parser.add_argument(
        "--schema", type=Path, default=None, help="Path to the schema file."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Folder the evidence paths are relative to. Defaults to this folder.",
    )
    parser.add_argument(
        "--no-verify-evidence",
        action="store_true",
        help="Do not open the quoted files. The result then says so out loud.",
    )
    parser.add_argument(
        "--expect-task-id",
        default=None,
        help="The task id the caller asked for. A reply naming another task is rejected.",
    )
    parser.add_argument(
        "--expect-agent-id",
        default=None,
        help="The agent id the caller spawned. A reply naming another agent is rejected.",
    )
    parser.add_argument(
        "--expect-sha256",
        default=None,
        help="The exact bytes the caller sent. A different file is rejected.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run the built-in good and bad cases and print PASS or FAIL for each.",
    )
    args = parser.parse_args(argv)

    # Checking fixtures while a real file sits unread is how a bad payload
    # passes. Refuse the pair instead of quietly ignoring one of them.
    if args.selftest and args.payload:
        print(
            "Give me a payload file OR --selftest, not both. With both, the file "
            "you named would never be read.",
            file=sys.stderr,
        )
        return 2

    if args.selftest:
        return run_selftest()

    if not args.payload:
        print("Give me a payload file to check, or use --selftest.", file=sys.stderr)
        return 2

    try:
        schema = load_schema(args.schema)
    except FileNotFoundError as error:
        print("REJECTED: %s" % ascii_safe(str(error)), file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(
            "REJECTED: the schema file is not valid JSON (%s)." % ascii_safe(str(error)),
            file=sys.stderr,
        )
        return 1

    path = Path(args.payload)
    if not path.is_file():
        print("PAYLOAD REJECTED: there is no file at %s." % ascii_safe(str(path)),
              file=sys.stderr)
        return 1

    digest = sha256_of(path)
    if args.expect_sha256 and digest.lower() != args.expect_sha256.strip().lower():
        print(
            "PAYLOAD REJECTED: %s holds different bytes than the caller sent.\n"
            "  expected sha256 %s\n  found    sha256 %s"
            % (ascii_safe(str(path)), args.expect_sha256.strip().lower(), digest),
            file=sys.stderr,
        )
        return 1

    verifier = None
    if not args.no_verify_evidence:
        verifier = EvidenceVerifier(args.repo_root or Path.cwd())

    ok, reasons = check_file(
        path, schema, verifier, args.expect_task_id, args.expect_agent_id
    )

    if ok:
        print("PAYLOAD ACCEPTED: %s" % ascii_safe(str(path)))
        print("  sha256 %s" % digest)
        if verifier is None:
            print(
                "  NOT CHECKED: the quoted files were not opened, because "
                "--no-verify-evidence was given. Every quote is unproven."
            )
        else:
            print("  evidence quotes opened and matched: %d" % verifier.checked)
            for note in verifier.unchecked:
                print("  NOT CHECKED: %s" % ascii_safe(note))
        return 0

    print("PAYLOAD REJECTED: %s" % ascii_safe(str(path)), file=sys.stderr)
    print("  sha256 %s" % digest, file=sys.stderr)
    for number, reason in enumerate(reasons, start=1):
        print("  %d. %s" % (number, ascii_safe(reason)), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
