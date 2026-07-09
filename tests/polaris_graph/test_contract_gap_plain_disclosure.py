"""N4 (I-deepfix-001 wave-2) — plain-English contract gap disclosure.

Pure string/regex, no GPU/LLM/network. Proves flag-OFF byte-identity, the
plain-English ON register, and that the new sentence is recognized by every gap
consumer (so it never leaks into Key Findings / depth).
"""
import pytest

from src.polaris_graph.generator.contract_section_runner import _contract_gap_sentence

_ENT = "brynjolfsson_genai_at_work"
_LABEL = "GenAI at Work (QJE 2025)"


# (1) BYTE-IDENTITY OFF.
def test_off_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_CONTRACT_GAP_PLAIN_DISCLOSURE", "0")
    assert _contract_gap_sentence(_ENT, "[6]", _LABEL) == (
        "Contract-bound content for brynjolfsson_genai_at_work did not survive "
        "strict verification against retrieved primary source text; this slot is "
        "a curator-actionable gap. See manifest.frame_coverage_report and "
        "human_gap_tasks.json for per-entity detail.[6]"
    )
    # No-entity fallback branch.
    assert _contract_gap_sentence("", "", _LABEL) == (
        "Contract-bound content did not survive strict verification; "
        "curator-actionable gap."
    )
    # Unset also byte-identical.
    monkeypatch.delenv("PG_CONTRACT_GAP_PLAIN_DISCLOSURE", raising=False)
    assert _contract_gap_sentence(_ENT, "[6]", _LABEL).startswith("Contract-bound content for")


# (2) PLAIN ON.
def test_on_plain_register(monkeypatch):
    monkeypatch.setenv("PG_CONTRACT_GAP_PLAIN_DISCLOSURE", "1")
    out = _contract_gap_sentence(_ENT, "[6]", _LABEL)
    assert "brynjolfsson_genai_at_work" not in out
    assert "frame_coverage_report" not in out
    assert "human_gap_tasks" not in out
    assert "curator-actionable" not in out
    assert "Contract-bound" not in out
    assert "_" not in out
    assert out.endswith("[6]")
    assert "insufficient verified evidence" in out.lower()
    # No-entity ON branch: same sentence WITHOUT the marker.
    out_noent = _contract_gap_sentence("", "", _LABEL)
    assert "insufficient verified evidence" in out_noent.lower()
    assert not out_noent.endswith("]")


# (3) KEY-FINDINGS FILTER recognizes the new sentence.
def test_key_findings_filter(monkeypatch):
    monkeypatch.setenv("PG_CONTRACT_GAP_PLAIN_DISCLOSURE", "1")
    out = _contract_gap_sentence(_ENT, "[6]", _LABEL)
    from src.polaris_graph.generator.key_findings import _GAP_MARKER_RE
    assert _GAP_MARKER_RE.search(out) is not None


# (4) RENDER-SEAM RECOGNIZERS all match the new sentence.
def test_render_seam_recognizers(monkeypatch):
    monkeypatch.setenv("PG_CONTRACT_GAP_PLAIN_DISCLOSURE", "1")
    out = _contract_gap_sentence(_ENT, "[6]", _LABEL)
    from scripts.run_honest_sweep_r3 import _RENDER_GAP_MARKER_RE
    from scripts.rendered_report_acceptance_harness import _CURATOR_GAP_RE
    from scripts.dr_benchmark.pack_drb2 import _GAP_STUB_RE
    assert _RENDER_GAP_MARKER_RE.search(out) is not None
    assert _CURATOR_GAP_RE.search(out) is not None
    assert _GAP_STUB_RE.search(out) is not None


# (5) The legacy (OFF) recognizers still match the legacy template (regression).
def test_legacy_template_still_recognized(monkeypatch):
    monkeypatch.setenv("PG_CONTRACT_GAP_PLAIN_DISCLOSURE", "0")
    legacy = _contract_gap_sentence(_ENT, "[6]", _LABEL)
    from src.polaris_graph.generator.key_findings import _GAP_MARKER_RE
    assert _GAP_MARKER_RE.search(legacy) is not None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
