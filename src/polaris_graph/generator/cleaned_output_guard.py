"""Read-only structural diagnostics for rendered Markdown tables."""
from __future__ import annotations

from dataclasses import dataclass
import re

_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


@dataclass(frozen=True)
class TableDefect:
    line_number: int
    reason: str


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def find_malformed_tables(markdown: str) -> list[TableDefect]:
    lines = markdown.splitlines()
    defects: list[TableDefect] = []
    in_table = False
    width = 0
    for position, line in enumerate(lines):
        stripped = line.strip()
        if position + 1 < len(lines) and "|" in stripped:
            separator = _cells(lines[position + 1])
            if separator and all(_SEPARATOR_CELL_RE.match(cell) for cell in separator):
                width = len(_cells(stripped))
                in_table = True
                if len(separator) != width:
                    defects.append(TableDefect(position + 2, "separator_width"))
                continue
        if not in_table:
            continue
        if not stripped:
            in_table = False
            width = 0
            continue
        if not stripped.startswith("|"):
            defects.append(TableDefect(position + 1, "multiline_cell"))
            in_table = False
            width = 0
            continue
        if len(_cells(stripped)) != width:
            defects.append(TableDefect(position + 1, "row_width"))
    return defects
