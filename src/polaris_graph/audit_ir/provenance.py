"""Upload provenance schema (M-11 — Phase B).

Per FINAL_PLAN.md: "Page/sheet/slide/timecode provenance map (NOT
just char offsets)". When M-12's Question-Bound Corpus Brief
emits a cited paragraph, the citation must trace back to a precise
location in the source upload — page X of a PDF, cell A3 of a
spreadsheet, slide 12, or seconds 38.5–42.1 of an audio file.

Char offsets alone are not enough: a multi-page PDF flattened to
text loses the page break information; a spreadsheet flattened to
CSV loses the cell coordinates; a presentation flattened to text
loses the slide structure.

This module defines a TAGGED UNION of provenance variants. Every
variant carries `upload_id` so the chunk traces back to a row in
the `uploads` table. Specific location fields differ per kind.

Phase B emits only `TextSpan` and `PdfSpan` (TextParser is
shipped; PdfParser is a stub). The schema accepts all variants
from day 1 so Phase C parsers (sheet / slide / audio) plug in
without a schema migration.

Distinct from `audit_ir.loader.EvidenceSpanToken` which models
V30's `[#ev:<id>:<start>-<end>]` per-sentence evidence bindings —
that's report-side; this is upload-side.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar


@dataclass(frozen=True)
class TextSpan:
    """Plain-text upload — char offsets within the upload's
    extracted text. The fallback when no richer location info is
    available."""

    upload_id: str
    char_start: int
    char_end: int

    kind: ClassVar[str] = "text_span"


@dataclass(frozen=True)
class PdfSpan:
    """A region within a single page of a PDF. char offsets are
    relative to the PAGE's extracted text (so page 5's offsets
    don't bleed into page 6)."""

    upload_id: str
    page: int  # 1-indexed
    char_start: int
    char_end: int

    kind: ClassVar[str] = "pdf_span"


@dataclass(frozen=True)
class SheetCell:
    """A cell or cell range within a single sheet of a workbook.

    `cell_range` follows the canonical A1-style notation from the
    source format ("A1", "B5:D10", "Sheet1!A1") — preserved
    verbatim so the citation matches what users see in Excel /
    Google Sheets.
    """

    upload_id: str
    sheet: str
    cell_range: str

    kind: ClassVar[str] = "sheet_cell"


@dataclass(frozen=True)
class SlideRegion:
    """A region within a single slide of a presentation.

    `bbox` is optional (x_left, y_top, width, height) in slide
    coordinates. None means "the whole slide".
    """

    upload_id: str
    slide_num: int  # 1-indexed
    bbox: tuple[float, float, float, float] | None = None

    kind: ClassVar[str] = "slide_region"


@dataclass(frozen=True)
class Timecode:
    """A time range within an audio or video upload, in seconds."""

    upload_id: str
    start_s: float
    end_s: float

    kind: ClassVar[str] = "timecode"


# Tagged union — every variant carries `kind` for serialization.
UploadProvenance = TextSpan | PdfSpan | SheetCell | SlideRegion | Timecode


_KIND_TO_CLASS: dict[str, type] = {
    TextSpan.kind: TextSpan,
    PdfSpan.kind: PdfSpan,
    SheetCell.kind: SheetCell,
    SlideRegion.kind: SlideRegion,
    Timecode.kind: Timecode,
}


def to_dict(prov: UploadProvenance) -> dict[str, Any]:
    """Serialize a provenance variant to a dict with `kind` tag.
    Round-trips with `from_dict`."""
    out = asdict(prov)
    out["kind"] = prov.kind
    return out


def from_dict(data: dict[str, Any]) -> UploadProvenance:
    """Deserialize a dict (as produced by `to_dict`) back into the
    correct variant. Raises ValueError on unknown / malformed
    `kind`."""
    kind = data.get("kind")
    if kind is None:
        raise ValueError("provenance dict missing 'kind' tag")
    cls = _KIND_TO_CLASS.get(kind)
    if cls is None:
        raise ValueError(f"unknown provenance kind: {kind!r}")
    fields = {k: v for k, v in data.items() if k != "kind"}
    # tuple-typed fields lose type after JSON round-trip — restore.
    if cls is SlideRegion and isinstance(fields.get("bbox"), list):
        fields["bbox"] = tuple(fields["bbox"])
    try:
        return cls(**fields)
    except TypeError as exc:
        raise ValueError(f"malformed {kind} provenance: {exc}") from exc
