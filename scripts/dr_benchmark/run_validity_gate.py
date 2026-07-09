"""Render-time RUN-VALIDITY gates for the Gate-B benchmark harness (I-deepfix-001 loss-risk must-fix).

Three pre-ship validity checks that make a paid benchmark run *actually valid* and fail CLOSED
before the report reaches the (expensive) scoring judge. They are the render-time half of the
loss-risk register FIX-2 / FIX-3:

  FIX-2  QUESTION-FIDELITY — after render, assert the report's H1/title reflects the BOUND
         question and was NOT silently reformulated. The drb_72 disaster shipped a report whose
         title answered "Fourth Industrial Revolution / English-language journal articles only"
         instead of the canonical DRB-II GenAI-labor task -> info_recall 0/57. A reformulation
         phrase is a wrong-question tell ONLY when it is ABSENT from the bound question (the
         I-safety-002b program prompt legitimately contains those phrases; the canonical idx-56
         prompt does not), so every check is RELATIVE to the bound question, never a global string.

  FIX-3  CONTRACT-SCAFFOLD — for a benchmark task whose gold prompt states an output CONTRACT
         (task72 = four named sections + a final 5-column summary table), assert the rendered
         report.md carries those sections + the table with the required header. A missing scaffold
         is a presentation-dimension loss the official judge scored 1/5. Config-driven from the
         per-task contract (``config/benchmark/task_output_contracts.yaml``), NEVER hardcoded to
         task72 — a slug with no contract entry is a NO-OP.

DESIGN INVARIANTS
  * FAITHFULNESS-NEUTRAL: this module reads the already-rendered report + the bound question and
    decides ship / do-not-ship. It touches NO faithfulness gate (strict_verify / NLI / 4-role D8 /
    provenance / span-grounding stay the only hard faithfulness gate).
  * §-1.3 WIDEN-ONLY: it adds a validity gate; it introduces no breadth cap / target / thinner.
  * NO SPEND / NO NETWORK / lazy heavy imports: pure functions operate on strings; the only I/O is
    reading the config file + the rendered report + writing a durable failure marker. Safe to import.
  * FAIL LOUD (LAW II): a violation raises ``RunValidityGateError`` — the run does NOT ship a report
    that answers the wrong question or drops the stated output contract.

The pure predicates (``check_question_fidelity`` / ``check_contract_scaffold`` /
``evaluate_report_validity``) take plain strings + a contract dict so they are unit-testable with no
config file, no gold file, no network. ``enforce_render_validity`` is the I/O wiring the Gate-B
entrypoint calls after ``run_one_query`` returns.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Config location (LAW VI: config-driven, cwd-independent, env-overridable).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = _REPO_ROOT / "config" / "benchmark" / "task_output_contracts.yaml"
_CONTRACT_PATH_ENV = "PG_TASK_OUTPUT_CONTRACT_PATH"

# The render-validity master kill-switch. DEFAULT ON (fail-closed behaviour armed for benchmark
# runs per the loss-risk directive); an operator may set it "0" to disable the render gates.
_GATE_ENABLED_ENV = "PG_RUN_VALIDITY_GATE"

# The statuses that ship a FULL rendered report (so the contract/fidelity gates apply). An abort
# verdict artifact (abort_no_verified_sections / abort_corpus_approval_denied / abort_safety_refused)
# is intentionally NOT a full report — the gates skip it (nothing shipped to score).
SHIPPED_REPORT_STATUSES = frozenset({"success", "released_with_disclosed_gaps"})

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)
_H1_RE = re.compile(r"^\s{0,3}#\s+(.*?)\s*#*\s*$", re.MULTILINE)
# The generator titles a report ``# Research report: <question>``; strip that stock prefix so the
# title region is the actual question echo, not the boilerplate.
_TITLE_PREFIX_RE = re.compile(r"^\s*research report\s*:\s*", re.IGNORECASE)
# A rendered citation marker is the canonical ``[N]`` (the analyst-synthesis scrubber normalizes
# every marker to ``[<int>]`` and drops malformed forms). A line carrying one is CITED evidence
# (every verified sentence carries [N] per §9.1) — the FIX-13 framing scan EXCLUDES such lines so
# legitimately-cited body/table mentions of a phrase are never mistaken for a title reformulation.
_CITATION_MARKER_RE = re.compile(r"\[\d+\]")


class RunValidityGateError(RuntimeError):
    """Raised when a rendered benchmark report fails a run-validity gate (fail loud, do not ship)."""


def run_validity_gate_enabled() -> bool:
    """Master kill-switch. DEFAULT ON — the fail-closed render gates are armed for benchmark runs.
    An explicit operator ``PG_RUN_VALIDITY_GATE=0`` disables them (LAW VI operator-override)."""
    return os.getenv(_GATE_ENABLED_ENV, "1").strip().lower() not in (
        "0", "false", "no", "off", "disabled", "",
    )


# The forbidden-reformulation FRAMING-ONLY switch (I-deepfix-001 FIX-13). DEFAULT OFF; ONLY the
# exact string "1" enables it. OFF => the reformulation scan keeps its verbatim body-wide substring
# containment (byte-identical). ON => a phrase counts ONLY when it appears in a FRAMING position
# (any heading OR an uncited body line) so 3 legitimately-CITED evidence mentions of the phrase no
# longer trip the gate (the drb_72 4IR false-positive that aborted a valid run), while a reformulated
# TITLE/heading and uncited generator prose adopting the phrase STAY fully detected.
_REFORMULATION_FRAMING_ONLY_ENV = "PG_RUN_VALIDITY_REFORMULATION_FRAMING_ONLY"


def run_validity_reformulation_framing_only_enabled() -> bool:
    """True iff the reformulation scan is restricted to FRAMING positions (headings + uncited body
    lines). DEFAULT OFF; ONLY the exact string ``"1"`` enables it (FIX-13 spec) so OFF => the
    verbatim body-wide containment => byte-identical. Read at call time (LAW VI operator-override)."""
    return os.getenv(_REFORMULATION_FRAMING_ONLY_ENV, "").strip() == "1"


# ---------------------------------------------------------------------------
# Contract loading.
# ---------------------------------------------------------------------------
def _contract_path() -> Path:
    override = os.getenv(_CONTRACT_PATH_ENV, "").strip()
    return Path(override) if override else DEFAULT_CONTRACT_PATH


def load_task_output_contract(
    slug: str, path: Optional[str | Path] = None
) -> Optional[dict[str, Any]]:
    """The per-task output contract for ``slug`` (or ``None`` if the slug has no entry / no file).

    Returning ``None`` makes the gates a documented NO-OP for any benchmark task that does not
    declare a contract — the gate is general, never hardcoded to one slug.
    """
    contract_file = Path(path) if path is not None else _contract_path()
    if not contract_file.is_file():
        return None
    import yaml  # lazy: keep module import cheap + dependency-local

    with contract_file.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    entry = data.get(slug)
    if not isinstance(entry, dict):
        return None
    return entry


# ---------------------------------------------------------------------------
# Text helpers.
# ---------------------------------------------------------------------------
def _norm(text: str) -> str:
    """Lowercase + collapse whitespace for tolerant, case-insensitive containment checks."""
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def extract_h1(report_md: str) -> Optional[str]:
    """The first level-1 heading text (stock ``Research report:`` prefix stripped), or None."""
    m = _H1_RE.search(report_md or "")
    if not m:
        return None
    return _TITLE_PREFIX_RE.sub("", m.group(1).strip())


def _heading_texts(report_md: str) -> list[str]:
    return [m.strip() for m in _HEADING_RE.findall(report_md or "")]


def _table_header_rows(report_md: str) -> list[list[str]]:
    """Every GFM table header row (the row immediately followed by a ``|---|---|`` delimiter),
    returned as a list of normalized cell strings.

    Only the leading + trailing bounding pipes are stripped; INTERNAL blank cells are KEPT so a
    header with a stray empty column does NOT silently collapse to the required column count and
    fail OPEN. A GFM row ``| A | B | C | D | E | |`` is a SIX-column header (last cell blank), not
    a five-column one, so it correctly fails an exact five-column contract (the Codex P1 fail-
    open where dropping the empty cell wrongly PASSED it)."""
    lines = (report_md or "").splitlines()
    rows: list[list[str]] = []

    def _cells(line: str) -> list[str]:
        raw = line.strip()
        if raw.startswith("|"):
            raw = raw[1:]
        if raw.endswith("|"):
            raw = raw[:-1]
        return [_norm(c) for c in raw.split("|")]

    for i in range(len(lines) - 1):
        line = lines[i]
        nxt = lines[i + 1].strip()
        if "|" not in line or "-" not in nxt:
            continue
        # A GFM delimiter row is composed ONLY of pipes / dashes / colons / spaces and has a dash.
        if set(nxt) <= set("|:- "):
            # KEEP internal blank cells (the bounding pipes were already stripped in ``_cells``);
            # a header must still carry at least one non-empty cell (a pure ``| | |`` divider is
            # not a header). A trailing/internal blank column therefore counts as a real column.
            cells = _cells(line)
            if any(cells):
                rows.append(cells)
    return rows


# ---------------------------------------------------------------------------
# FIX-2: question fidelity.
# ---------------------------------------------------------------------------
def _framing_violation(report_md: str, phrase_n: str) -> bool:
    """FIX-13 framing-only reformulation test. True iff the ALREADY-NORMALIZED phrase ``phrase_n``
    appears in a FRAMING position:

      (1) ANY heading text (H1 title + every subsection / disclosed-gap header) — the original
          drb_72 disaster class (a reformulated title/section header) stays fully detected; OR
      (2) any body LINE that carries NO citation marker — uncited prose adopting the phrase is the
          generator reframing.

    A body/table line carrying a ``[N]`` citation marker is CITED evidence (every verified sentence
    carries [N] per §9.1) and is EXCLUDED, so N legitimately-cited evidence mentions of the phrase do
    NOT trip the gate. Pure, no I/O; deterministic."""
    if not phrase_n:
        return False
    # (1) Headings — a reformulated title / section header (the original disaster class).
    for heading in _heading_texts(report_md):
        if phrase_n in _norm(heading):
            return True
    # (2) Uncited body lines — cited (``[N]``) lines and heading lines are excluded.
    for line in (report_md or "").splitlines():
        if _HEADING_RE.match(line):
            continue  # heading handled in (1)
        if _CITATION_MARKER_RE.search(line):
            continue  # cited evidence line / cited table cell -> excluded
        if phrase_n in _norm(line):
            return True
    return False


def check_question_fidelity(
    report_md: str,
    bound_question: str,
    contract: dict[str, Any],
    *,
    framing_only: bool = False,
) -> list[str]:
    """Violations where the rendered report drifted from the BOUND question intent.

    (1) A ``forbidden_reformulations`` phrase present in the report but ABSENT from the bound
        question is a wrong-question tell (the drb_72 title reformulation). When ``framing_only``
        is True (FIX-13, env ``PG_RUN_VALIDITY_REFORMULATION_FRAMING_ONLY``) a phrase counts ONLY
        in a FRAMING position (heading OR uncited body line) so legitimately-CITED evidence mentions
        no longer false-trip the gate; when False (DEFAULT) the verbatim body-wide substring
        containment is used (byte-identical to the pre-FIX-13 behaviour).
    (2) An ``intent_anchors`` group with NO hit in the H1/title region means the title does not
        reflect the bound question (or there is no H1 at all).
    """
    violations: list[str] = []
    report_n = _norm(report_md)
    question_n = _norm(bound_question)

    for phrase in contract.get("forbidden_reformulations", []) or []:
        phrase_n = _norm(phrase)
        if not phrase_n:
            continue
        if phrase_n in question_n:
            continue  # legitimately in the bound question -> never a reformulation flag
        present = (
            _framing_violation(report_md, phrase_n)
            if framing_only
            else (phrase_n in report_n)
        )
        if present:
            violations.append(
                f"question-fidelity: reformulation phrase {phrase!r} appears in the rendered "
                f"report but is ABSENT from the bound question - the report was reformulated "
                f"(the drb_72 wrong-question class)."
            )

    anchors = contract.get("intent_anchors", []) or []
    if anchors:
        h1 = extract_h1(report_md)
        if h1 is None:
            violations.append(
                "question-fidelity: rendered report has NO level-1 title heading to match "
                "against the bound-question intent."
            )
        else:
            h1_n = _norm(h1)
            for group in anchors:
                alts = group if isinstance(group, list) else [group]
                if not any(_norm(a) and _norm(a) in h1_n for a in alts):
                    violations.append(
                        f"question-fidelity: report title {h1!r} contains none of the bound-"
                        f"question intent anchors {list(alts)!r} - the title does not reflect "
                        f"the bound question."
                    )
    return violations


# ---------------------------------------------------------------------------
# FIX-3: output-contract scaffold.
# ---------------------------------------------------------------------------
def check_contract_scaffold(report_md: str, contract: dict[str, Any]) -> list[str]:
    """Violations where the rendered report is missing a stated section or the required table.

    ``required_sections`` — each entry is a list of accepted heading synonyms; a section is present
    iff SOME heading line contains one synonym. ``required_table.columns`` — the report must carry a
    GFM table whose header row EXACTLY equals the configured columns after the same whitespace/case
    normalization (same count, same order, element-by-element ==); a substring, subset, reordered, or
    extra-column header is a contract violation (fail closed, not a substring/subset match).
    """
    violations: list[str] = []
    headings_n = [_norm(h) for h in _heading_texts(report_md)]

    for section in contract.get("required_sections", []) or []:
        synonyms = section if isinstance(section, list) else [section]
        syn_n = [_norm(s) for s in synonyms if _norm(s)]
        if not any(any(s in h for h in headings_n) for s in syn_n):
            violations.append(
                f"contract-scaffold: required section {synonyms!r} is ABSENT - no heading "
                f"matches any of its accepted names (presentation-dimension loss)."
            )

    table = contract.get("required_table") or {}
    required_cols = [str(c) for c in (table.get("columns", []) or [])]
    if required_cols:
        required_cols_n = [_norm(c) for c in required_cols]
        header_rows = _table_header_rows(report_md)
        # EXACT match: some GFM header row must equal the configured columns element-by-element
        # (same count, same order) after the identical ``_norm`` normalization both sides use. NO
        # substring, NO subset, NO reorder tolerance — an extra 6th column, a reversed order, or a
        # substring header ("Research Literature Notes" vs "Research Literature") is a violation.
        matched = any(row == required_cols_n for row in header_rows)
        if not matched:
            violations.append(
                f"contract-scaffold: required summary table with header columns {required_cols!r} "
                f"is ABSENT - found {len(header_rows)} table header row(s), none EXACTLY matching "
                f"the required columns (same count + order; presentation-dimension loss)."
            )
    return violations


def evaluate_report_validity(
    report_md: str,
    bound_question: str,
    contract: dict[str, Any],
    *,
    framing_only: bool = False,
) -> list[str]:
    """All run-validity violations (question-fidelity + contract-scaffold) for one rendered report.

    ``framing_only`` (FIX-13) is threaded to ``check_question_fidelity`` only; it never touches the
    contract-scaffold check. DEFAULT False => byte-identical to the pre-FIX-13 behaviour."""
    return (
        check_question_fidelity(
            report_md, bound_question, contract, framing_only=framing_only
        )
        + check_contract_scaffold(report_md, contract)
    )


# ---------------------------------------------------------------------------
# I/O wiring: enforce on the rendered artifact, fail loud, do not ship.
# ---------------------------------------------------------------------------
def _write_failure_marker(run_dir: Path, slug: str, violations: list[str]) -> None:
    """Durable ``run_validity_gate.json`` marker + flip the on-disk manifest status to abort so a
    downstream scorer never silently ships an invalid report as a success (belt-and-suspenders to
    the raise). Best-effort: a marker/manifest write failure must NOT mask the fail-loud raise."""
    marker = {
        "verdict": "FAILED",
        "slug": slug,
        "gate": "run_validity_gate",
        "utc": datetime.now(timezone.utc).isoformat(),
        "violations": violations,
        "note": "report FAILED a render-time run-validity gate (question-fidelity / contract-"
                "scaffold); it must NOT be shipped to the scoring judge.",
    }
    try:
        (run_dir / "run_validity_gate.json").write_text(
            json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError:
        pass
    manifest_path = run_dir / "manifest.json"
    try:
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "abort_run_validity_gate"
            manifest["run_validity_gate"] = {"verdict": "FAILED", "violations": violations}
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    except (OSError, ValueError):
        pass


def enforce_render_validity(
    summary: dict[str, Any],
    q: dict[str, Any],
    run_dir: Path,
    *,
    bound_question: Optional[str] = None,
    contract_path: Optional[str | Path] = None,
) -> Optional[list[str]]:
    """Post-render gate for one Gate-B query. Returns ``None`` when the gate does not apply (no
    contract for the slug / no rendered report / non-shipping status / gate disabled); returns the
    empty list when the report is VALID; RAISES ``RunValidityGateError`` when it is not.

    ``bound_question`` defaults to the question the run actually answered (``q['question']`` — which,
    on the official-question-forced benchmark path, is the canonical DRB-II prompt). Faithfulness is
    untouched; this reads the shipped report + the bound question and decides ship / do-not-ship.
    """
    if not run_validity_gate_enabled():
        return None
    if summary.get("status") not in SHIPPED_REPORT_STATUSES:
        return None
    slug = q.get("slug", "")
    contract = load_task_output_contract(slug, path=contract_path)
    if not contract:
        return None
    report_path = Path(run_dir) / "report.md"
    if not report_path.is_file():
        return None

    report_md = report_path.read_text(encoding="utf-8", errors="replace")
    question = bound_question if bound_question is not None else q.get("question", "")
    # FIX-13: read the framing-only switch ONCE here (env I/O stays in the I/O wiring; the pure
    # predicates take it as an explicit keyword). DEFAULT OFF => body-wide containment => byte-identical.
    framing_only = run_validity_reformulation_framing_only_enabled()
    violations = evaluate_report_validity(
        report_md, question, contract, framing_only=framing_only
    )
    if not violations:
        return []

    _write_failure_marker(Path(run_dir), slug, violations)
    bullet = "\n  - ".join(violations)
    raise RunValidityGateError(
        f"RUN-VALIDITY GATE FAILED for {slug!r} - the rendered report is INVALID and must NOT be "
        f"shipped to the scoring judge:\n  - {bullet}\n"
        f"(marker: {run_dir / 'run_validity_gate.json'}; manifest status flipped to "
        f"abort_run_validity_gate)."
    )
