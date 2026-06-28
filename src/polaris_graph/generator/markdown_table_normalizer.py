"""Deterministic post-render GFM-table normalizer (I-deepfix-001 B18, #1344).

Scope: the two render defects the forensic audit found in the rendered ``report.md``
summary table, both of which make specific numeric claims render WRONG (or UNCITED)
in any GFM viewer:

* **Missing GFM separator row.** A markdown table needs a ``| --- | --- |`` row
  immediately after the header for a GFM renderer to treat it as a table at all.
  When the LLM emits the header + data rows but omits the separator, the whole block
  renders as plain run-together text. We INSERT a separator row (one ``---`` column
  per header column) right after the header when it is absent.

* **First-cell drop / column shift on an empty leading cell.** A data row whose
  leading cell is empty — e.g. a row with no author/citation, written
  ``| | 14.9% | STEP 1 |`` or, worse, the leading delimiter dropped so it reads
  ``14.9% | STEP 1 |`` — shifts every cell one column left in some renderers, so the
  numeric value lands under the wrong header and the citation column is lost. We
  re-pad every data row to the header's column count WITHOUT dropping any cell: a
  short row is padded on the RIGHT with empty cells, an over-long row keeps all its
  cells (never truncated), and a row missing its leading ``|`` regains it. The
  leading cell is preserved exactly (an empty author cell stays an empty cell — the
  value never migrates into it).

Design: pure, deterministic, regex/string only — no LLM, no network. It runs on the
rendered text DOWNSTREAM of the frozen faithfulness engine and changes ONLY table
formatting (pipes / separator / cell padding); it never edits cell CONTENT, never
adds or removes a citation token, and never drops a row or a cell. The faithfulness
engine (strict_verify / NLI / 4-role / provenance / span-grounding) is untouched.

Behaviour is gated behind the default-ON kill-switch
``PG_RENDER_GFM_TABLE_NORMALIZE``; set it OFF for byte-identical pre-fix output.
Every change is recorded as a :class:`TableNormalizationFlag`; nothing is silently
dropped.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# --- canary -----------------------------------------------------------------
CANARY_TAG = "[gfm_table_normalizer]"

# --- env flag (default ON; LAW VI — behaviour change is env-gated) -----------
_NORMALIZE_FLAG = "PG_RENDER_GFM_TABLE_NORMALIZE"
_NORMALIZE_OFF_VALUES = frozenset({"0", "false", "off", "no"})

# --- flag kinds -------------------------------------------------------------
FLAG_SEPARATOR_INSERTED = "separator_row_inserted"
FLAG_ROW_REPADDED = "row_repadded_no_cell_dropped"

# A line that is a markdown table row: starts (after optional indent) with ``|`` OR
# contains at least one unescaped ``|`` between two non-pipe runs. We require a
# LEADING ``|`` for the strict row form, and separately detect a leading-pipe-missing
# row only inside an already-identified table block (so plain prose with an inline
# ``a | b`` is never mistaken for a table). The strict detector below is intentionally
# conservative: a table BLOCK is a run of >= 2 consecutive lines each containing
# ``|``, the FIRST of which starts with ``|`` (the header).
_PIPE_LINE_PATTERN = re.compile(r"\|")
_LEADING_PIPE_PATTERN = re.compile(r"^\s*\|")
# Split a row on column-delimiter pipes only: a pipe NOT preceded by a backslash.
# An escaped ``\|`` is a literal pipe inside a cell and must not start a column.
_UNESCAPED_PIPE_SPLIT = re.compile(r"(?<!\\)\|")
# A GFM separator row: only pipes, dashes, colons and whitespace, with >= 1 dash.
_SEPARATOR_ROW_PATTERN = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")

# Minimum consecutive pipe-bearing lines to treat the block as a table.
_MIN_TABLE_LINES = 2


@dataclass(frozen=True)
class TableNormalizationFlag:
    """One auditable table-normalizer action."""

    line_index: int
    kind: str
    detail: str


@dataclass
class TableNormalizationResult:
    """Outcome of :func:`normalize_gfm_tables`."""

    text: str
    flags: list[TableNormalizationFlag] = field(default_factory=list)
    line_count: int = 0
    separators_inserted: int = 0
    rows_repadded: int = 0

    @property
    def changed(self) -> bool:
        """True iff any repair altered the text."""
        return bool(self.separators_inserted or self.rows_repadded)

    @property
    def canary(self) -> str:
        """Behavioral canary with real per-run counts."""
        return (
            f"{CANARY_TAG} lines={self.line_count} "
            f"separators_inserted={self.separators_inserted} "
            f"rows_repadded={self.rows_repadded}"
        )


def _normalize_enabled() -> bool:
    """True (default) unless ``PG_RENDER_GFM_TABLE_NORMALIZE`` is OFF."""
    return (
        os.environ.get(_NORMALIZE_FLAG, "").strip().lower()
        not in _NORMALIZE_OFF_VALUES
    )


def _split_cells(line: str) -> list[str]:
    """Split a markdown table row into its cells, preserving every cell exactly.

    A leading and a trailing pipe are structural delimiters (not cell boundaries),
    so they are stripped before splitting; an EMPTY leading or trailing cell is
    therefore preserved as ``""`` and never collapsed. Inner whitespace around a
    cell is trimmed for re-emission consistency, but the cell TEXT is preserved.
    """
    body = line.strip()
    # Strip exactly one structural leading/trailing pipe; an empty cell on either
    # edge survives because split() keeps the empty field between two delimiters.
    # The trailing strip is ESCAPE-AWARE: a cell ending in an escaped pipe
    # (``\|``) is a literal pipe, not a structural delimiter, so it is not peeled.
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    # Split on UNESCAPED pipes only: an escaped ``\|`` is a literal pipe inside a
    # cell (GFM escaping), never a column boundary (I-deepfix-001 Codex P2).
    return [cell.strip() for cell in _UNESCAPED_PIPE_SPLIT.split(body)]


def _build_separator_row(num_columns: int) -> str:
    """Build a GFM separator row with ``num_columns`` ``---`` columns."""
    return "| " + " | ".join(["---"] * max(num_columns, 1)) + " |"


def _repad_row(
    cells: list[str], num_columns: int, *, restore_leading: bool = False
) -> str:
    """Re-emit ``cells`` as a pipe-delimited row of >= ``num_columns`` columns.

    A short row is padded with empty cells; an over-long row keeps ALL its cells
    (never truncated). This fixes the column-shift WITHOUT losing data.

    ``restore_leading`` (I-deepfix-001 Codex P1, iter 3->4): when the row LOST its
    leading structural pipe (a data row that does not begin with ``|`` though the
    header does), the missing column is the LEADING one — restore ONE empty leading
    cell so values land in their correct columns instead of right-shifting. Any
    further shortfall is then right-padded. A row that kept its leading pipe is
    right-padded only (a lost trailing cell).
    """
    padded = list(cells)
    if restore_leading and len(padded) < num_columns:
        padded.insert(0, "")  # restore the lost leading structural cell
    while len(padded) < num_columns:
        padded.append("")
    return "| " + " | ".join(padded) + " |"


def _is_table_row(line: str) -> bool:
    """True iff ``line`` carries at least one pipe (a candidate table row)."""
    return bool(_PIPE_LINE_PATTERN.search(line))


def _find_table_blocks(lines: list[str]) -> list[tuple[int, int]]:
    """Return [start, end) index ranges of contiguous pipe-bearing table blocks.

    A block is a maximal run of >= ``_MIN_TABLE_LINES`` consecutive lines each
    containing a pipe, whose FIRST line starts with a leading ``|`` (a real header
    row). The leading-pipe-on-the-header requirement keeps inline prose like
    ``cost is a | b tradeoff`` (no leading pipe) from being treated as a table.
    """
    blocks: list[tuple[int, int]] = []
    i = 0
    n = len(lines)
    while i < n:
        if _is_table_row(lines[i]) and _LEADING_PIPE_PATTERN.match(lines[i]):
            j = i + 1
            while j < n and _is_table_row(lines[j]):
                j += 1
            if (j - i) >= _MIN_TABLE_LINES:
                blocks.append((i, j))
            i = j
        else:
            i += 1
    return blocks


def normalize_gfm_tables(text: str) -> TableNormalizationResult:
    """Normalize malformed GFM tables in rendered report text.

    Inserts the missing GFM separator row after a header and re-pads data rows to the
    header column count WITHOUT dropping any cell (fixes the first-cell-drop /
    column-shift). Non-table text is byte-identical. Pure, deterministic, no LLM.

    Returns a :class:`TableNormalizationResult` carrying the normalized ``text``, the
    per-action audit ``flags``, and the behavioral counts in
    :attr:`TableNormalizationResult.canary`.
    """
    lines = text.split("\n")
    result = TableNormalizationResult(text=text, line_count=len(lines))
    if not _normalize_enabled():
        logger.info(result.canary)
        return result

    blocks = _find_table_blocks(lines)
    if not blocks:
        logger.info(result.canary)
        return result

    # Rebuild line list, processing blocks back-to-front so insertion indices stay
    # valid for the not-yet-processed earlier blocks.
    out_lines = list(lines)
    flags: list[TableNormalizationFlag] = []
    separators_inserted = 0
    rows_repadded = 0

    for (start, end) in sorted(blocks, key=lambda b: b[0], reverse=True):
        header_cells = _split_cells(out_lines[start])
        num_columns = len(header_cells)
        if num_columns < 1:
            continue

        second_is_separator = (
            (end - start) >= 2
            and _SEPARATOR_ROW_PATTERN.match(out_lines[start + 1]) is not None
        )

        # Re-pad every DATA row (rows after header + separator) without dropping a
        # cell. The header itself is left as-is (it already defines the columns); a
        # present separator is left as-is.
        data_start = start + (2 if second_is_separator else 1)
        for idx in range(data_start, end):
            row = out_lines[idx]
            if _SEPARATOR_ROW_PATTERN.match(row):
                continue  # never re-pad a separator row
            cells = _split_cells(row)
            # A data row that lost its leading structural pipe (the header has one
            # but this row does not) is short on the LEADING cell, not the trailing
            # one — restore the leading cell so values do not right-shift.
            lost_leading = _LEADING_PIPE_PATTERN.match(row) is None
            repadded = _repad_row(
                cells, num_columns, restore_leading=lost_leading
            )
            if repadded != row.rstrip():
                out_lines[idx] = repadded
                rows_repadded += 1
                flags.append(
                    TableNormalizationFlag(
                        idx, FLAG_ROW_REPADDED,
                        f"{len(cells)} cell(s) -> {max(len(cells), num_columns)} column(s)",
                    )
                )

        # Insert a GFM separator row right after the header when absent.
        if not second_is_separator:
            out_lines.insert(start + 1, _build_separator_row(num_columns))
            separators_inserted += 1
            flags.append(
                TableNormalizationFlag(
                    start + 1, FLAG_SEPARATOR_INSERTED,
                    f"{num_columns} column(s)",
                )
            )

    result.text = "\n".join(out_lines)
    result.flags = flags
    result.separators_inserted = separators_inserted
    result.rows_repadded = rows_repadded
    logger.info(result.canary)
    return result
