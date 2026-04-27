"""Tests for src/polaris_graph/audit_ir/provenance.py (M-11)."""

from __future__ import annotations

import pytest

from src.polaris_graph.audit_ir.provenance import (
    PdfSpan,
    SheetCell,
    SlideRegion,
    TextSpan,
    Timecode,
    UploadProvenance,
    from_dict,
    to_dict,
)


# ---------------------------------------------------------------------------
# Variant construction
# ---------------------------------------------------------------------------


def test_text_span_round_trip() -> None:
    p = TextSpan(upload_id="up_1", char_start=0, char_end=100)
    d = to_dict(p)
    assert d["kind"] == "text_span"
    assert d["upload_id"] == "up_1"
    assert from_dict(d) == p


def test_pdf_span_round_trip() -> None:
    p = PdfSpan(upload_id="up_1", page=3, char_start=10, char_end=200)
    d = to_dict(p)
    assert d["kind"] == "pdf_span"
    assert d["page"] == 3
    assert from_dict(d) == p


def test_sheet_cell_round_trip() -> None:
    p = SheetCell(upload_id="up_1", sheet="Summary", cell_range="A1:C10")
    d = to_dict(p)
    assert d["kind"] == "sheet_cell"
    assert from_dict(d) == p


def test_slide_region_with_bbox_round_trip() -> None:
    p = SlideRegion(upload_id="up_1", slide_num=5, bbox=(0.0, 0.5, 1.0, 0.5))
    d = to_dict(p)
    assert d["kind"] == "slide_region"
    # JSON round-trip turns tuples into lists; from_dict must restore.
    import json
    serialized = json.dumps(d)
    deserialized = json.loads(serialized)
    assert from_dict(deserialized) == p


def test_slide_region_without_bbox_round_trip() -> None:
    p = SlideRegion(upload_id="up_1", slide_num=2, bbox=None)
    d = to_dict(p)
    assert d["bbox"] is None
    assert from_dict(d) == p


def test_timecode_round_trip() -> None:
    p = Timecode(upload_id="up_1", start_s=12.5, end_s=45.8)
    d = to_dict(p)
    assert d["kind"] == "timecode"
    assert from_dict(d) == p


# ---------------------------------------------------------------------------
# Tagged-union semantics
# ---------------------------------------------------------------------------


def test_all_variants_have_distinct_kind() -> None:
    kinds = {
        TextSpan.kind, PdfSpan.kind, SheetCell.kind,
        SlideRegion.kind, Timecode.kind,
    }
    assert len(kinds) == 5


def test_from_dict_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown provenance kind"):
        from_dict({"kind": "no_such_kind", "upload_id": "u"})


def test_from_dict_missing_kind_raises() -> None:
    with pytest.raises(ValueError, match="missing 'kind'"):
        from_dict({"upload_id": "u"})


def test_from_dict_malformed_payload_raises() -> None:
    """Missing required fields must raise ValueError, not TypeError."""
    with pytest.raises(ValueError, match="malformed"):
        from_dict({"kind": "text_span", "upload_id": "u"})  # missing offsets


# ---------------------------------------------------------------------------
# Codex M-11 review regression: type/shape validation
# ---------------------------------------------------------------------------


def test_from_dict_rejects_negative_text_span_offsets() -> None:
    with pytest.raises(ValueError, match="invalid range"):
        from_dict({
            "kind": "text_span", "upload_id": "u",
            "char_start": -5, "char_end": 10,
        })


def test_from_dict_rejects_inverted_text_span_range() -> None:
    with pytest.raises(ValueError, match="invalid range"):
        from_dict({
            "kind": "text_span", "upload_id": "u",
            "char_start": 100, "char_end": 50,
        })


def test_from_dict_rejects_non_int_text_span_offsets() -> None:
    with pytest.raises(ValueError, match="must be int"):
        from_dict({
            "kind": "text_span", "upload_id": "u",
            "char_start": "0", "char_end": "10",
        })


def test_from_dict_rejects_zero_pdf_page() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        from_dict({
            "kind": "pdf_span", "upload_id": "u",
            "page": 0, "char_start": 0, "char_end": 10,
        })


def test_from_dict_rejects_empty_sheet_name() -> None:
    with pytest.raises(ValueError, match="sheet must be"):
        from_dict({
            "kind": "sheet_cell", "upload_id": "u",
            "sheet": "", "cell_range": "A1",
        })


def test_from_dict_rejects_slide_region_wrong_bbox_arity() -> None:
    """Codex M-11 review regression: bbox must be 4-tuple. Old
    schema accepted [1, 2] silently."""
    with pytest.raises(ValueError, match="4-tuple"):
        from_dict({
            "kind": "slide_region", "upload_id": "u",
            "slide_num": 1, "bbox": [1.0, 2.0],
        })


def test_from_dict_rejects_slide_region_non_numeric_bbox() -> None:
    with pytest.raises(ValueError, match="numeric"):
        from_dict({
            "kind": "slide_region", "upload_id": "u",
            "slide_num": 1, "bbox": ["a", "b", "c", "d"],
        })


def test_from_dict_rejects_negative_timecode_start() -> None:
    with pytest.raises(ValueError, match="invalid range"):
        from_dict({
            "kind": "timecode", "upload_id": "u",
            "start_s": -1.0, "end_s": 5.0,
        })


def test_from_dict_rejects_inverted_timecode_range() -> None:
    with pytest.raises(ValueError, match="invalid range"):
        from_dict({
            "kind": "timecode", "upload_id": "u",
            "start_s": 10.0, "end_s": 5.0,
        })


def test_from_dict_rejects_empty_upload_id() -> None:
    with pytest.raises(ValueError, match="upload_id"):
        from_dict({
            "kind": "text_span", "upload_id": "",
            "char_start": 0, "char_end": 10,
        })


def test_dataclasses_are_frozen() -> None:
    """All variants must be immutable so callers can't mutate
    shared provenance records."""
    p = TextSpan(upload_id="u", char_start=0, char_end=10)
    with pytest.raises(Exception):
        p.upload_id = "v"  # type: ignore[misc]


def test_upload_provenance_type_alias_is_union() -> None:
    """Sanity: UploadProvenance is a typing.Union of all 5 variants."""
    p1: UploadProvenance = TextSpan("u", 0, 10)
    p2: UploadProvenance = PdfSpan("u", 1, 0, 10)
    p3: UploadProvenance = SheetCell("u", "S1", "A1")
    p4: UploadProvenance = SlideRegion("u", 1, None)
    p5: UploadProvenance = Timecode("u", 0.0, 1.0)
    for p in (p1, p2, p3, p4, p5):
        assert hasattr(p, "upload_id")
