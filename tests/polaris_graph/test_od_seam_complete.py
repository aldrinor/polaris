"""GH I-deepfix-003 (#1374) over-deletion — seam-level fixes (Fix 4 topic-side, Fix 5).

Real-shaped fixtures, no network / no LLM key:
  * Fix 4 topic-side: a chrome/failed-fetch row is NOT sent to the topic judge (never
    stamped off_subject); flag OFF => the chrome row IS judged (byte-identical legacy).
  * Fix 5: `_attach_junk_deletion_disclosure` reads the DURABLE junk_deletion_disclosure.json
    and splits chrome vs off-topic (incl. the Fix-1 `confirmed_offtopic_subject` reason the
    old `== "confirmed_offtopic"` filter MISSED); missing file => keys absent.
  * Fix 5: the run-validity SUMMARY TABLE emit path fires for the official DRB-72 slug —
    the contract resolves, the renderer emits the exact 5-column header, and the
    contract-scaffold gate then finds it (no abort_run_validity_gate).
"""
import json
import re

import pytest

from src.polaris_graph.retrieval.topic_relevance_gate import classify_topic_relevance


# ── Fix 4 (topic-side): chrome rows are never judged for topicality ──────────────────────

def _stub_all_off_subject(prompt: str) -> str:
    """A stub LLM that marks EVERY judged source OFF_SUBJECT (one verdict line per source
    index found in the prompt's SOURCES block), so any row that reaches the judge gets the
    deletable stamp — the test then proves a chrome row NEVER reaches it."""
    idxs: list[int] = []
    in_sources = False
    for line in prompt.splitlines():
        if line.strip() == "SOURCES:":
            in_sources = True
            continue
        if in_sources:
            m = re.match(r"^(\d+):", line.strip())
            if m:
                idxs.append(int(m.group(1)))
    return "\n".join(f"{i}: OFF_SUBJECT" for i in idxs)


def _clean_row():
    return {
        "evidence_id": "ev_ok",
        "title": "Generative AI at Work",
        "direct_quote": "Access to a generative AI assistant raised worker productivity "
                        "by 14 percent among support agents.",
    }


def _chrome_row():
    return {
        "evidence_id": "ev_chrome",
        "title": "Just a moment...",
        "direct_quote": "Enable JavaScript and cookies to continue",
    }


def test_topic_gate_skips_chrome_row(monkeypatch):
    monkeypatch.setenv("PG_JUNK_CHROME_BEFORE_OFFTOPIC", "1")
    monkeypatch.setenv("PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT", "1")
    monkeypatch.setenv("PG_SCOPE_TOPIC_GATE", "1")
    clean, chrome = _clean_row(), _chrome_row()
    res = classify_topic_relevance(
        [clean, chrome], "Impact of generative AI on the labor market",
        _stub_all_off_subject,
    )
    # the judged clean row is stamped OFF_SUBJECT; the chrome row is NEVER judged => no stamp
    assert clean.get("topic_off_subject") is True
    assert chrome.get("topic_off_subject") is not True
    assert "topic_off_subject" not in chrome
    assert "chrome_skipped=1" in " ".join(res.notes)
    # chrome row is still KEPT in the pool (the chrome-delete leg removes it later)
    assert chrome in res.kept_rows


def test_topic_gate_chrome_guard_off_judges_chrome(monkeypatch):
    monkeypatch.setenv("PG_JUNK_CHROME_BEFORE_OFFTOPIC", "0")  # byte-identical legacy
    monkeypatch.setenv("PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT", "1")
    monkeypatch.setenv("PG_SCOPE_TOPIC_GATE", "1")
    chrome = _chrome_row()
    classify_topic_relevance(
        [chrome], "Impact of generative AI on the labor market", _stub_all_off_subject,
    )
    # guard OFF => the chrome row IS judged and stamped (proves the flag gates the skip)
    assert chrome.get("topic_off_subject") is True


# ── Fix 5: durable disclosure attach on every manifest write path ────────────────────────

def test_attach_junk_deletion_disclosure_splits_reasons(tmp_path):
    from scripts.run_honest_sweep_r3 import _attach_junk_deletion_disclosure

    recs = [
        {"evidence_id": "c1", "deletion_reason": "content_integrity_junk:bot_challenge"},
        {"evidence_id": "s1", "deletion_reason": "confirmed_offtopic_subject"},
        {"evidence_id": "s2", "deletion_reason": "confirmed_offtopic"},
    ]
    (tmp_path / "junk_deletion_disclosure.json").write_text(
        json.dumps({"deleted": recs, "count": len(recs)}), encoding="utf-8"
    )
    manifest = _attach_junk_deletion_disclosure({}, tmp_path)
    chrome_ids = {r["evidence_id"] for r in manifest["deleted_chrome_nonsources"]}
    off_ids = {r["evidence_id"] for r in manifest["deleted_offtopic_sources"]}
    assert chrome_ids == {"c1"}
    # BOTH the Fix-1 subject reason AND the legacy reason land in the off-topic bucket
    # (the prior == "confirmed_offtopic" filter silently missed confirmed_offtopic_subject).
    assert off_ids == {"s1", "s2"}


def test_attach_junk_deletion_disclosure_no_file_byte_identical(tmp_path):
    from scripts.run_honest_sweep_r3 import _attach_junk_deletion_disclosure

    # no durable file (pre-seam abort) => keys ABSENT (byte-identical manifest shape)
    manifest = _attach_junk_deletion_disclosure({"status": "abort_x"}, tmp_path)
    assert "deleted_chrome_nonsources" not in manifest
    assert "deleted_offtopic_sources" not in manifest
    assert manifest == {"status": "abort_x"}


def test_attach_junk_deletion_disclosure_none_run_dir():
    from scripts.run_honest_sweep_r3 import _attach_junk_deletion_disclosure

    # run_dir None (entry-setup error manifest) must not raise and must not add keys
    manifest = _attach_junk_deletion_disclosure({"status": "error_setup"}, None)
    assert manifest == {"status": "error_setup"}


# ── Fix 5: the run-validity SUMMARY TABLE emit path fires for the official DRB-72 slug ────

def test_drb72_contract_resolves_five_column_table():
    from scripts.dr_benchmark.run_validity_gate import load_task_output_contract

    contract = load_task_output_contract("drb_72_ai_labor")
    assert contract is not None, "official DRB-72 slug must resolve a contract"
    cols = (contract.get("required_table") or {}).get("columns") or []
    assert cols == [
        "Research Literature", "Country/Region", "Application Area/Occupation",
        "Specific Applications and Impacts", "Key Risks and Limitations",
    ]


def test_drb72_summary_table_emits_and_passes_validity(monkeypatch):
    monkeypatch.setenv("PG_RENDER_SUMMARY_TABLE", "1")
    from scripts.dr_benchmark.run_validity_gate import (
        load_task_output_contract,
        check_contract_scaffold,
    )
    from src.polaris_graph.generator.summary_table import render_requested_summary_table

    contract = load_task_output_contract("drb_72_ai_labor")
    cols = contract["required_table"]["columns"]
    bib = [{
        "evidence_id": "e1", "num": 1, "title": "Generative AI at Work",
        "url": "https://doi.org/10.1093/qje/qjae044",
    }]
    claims = [{
        "evidence_id": "e1", "is_verified": True,
        "sentence": "Access to a generative AI assistant raised worker productivity by 14 "
                    "percent among customer-support agents in the United States.",
    }]
    result = render_requested_summary_table(
        research_question="Impact of generative AI on the future labor market",
        bibliography=bib, section_claims=claims, existing_report_md="",
        contract_headers=cols,
    )
    assert result.changed is True, "the emit path must FIRE (a verified claim + contract headers)"
    assert result.headers == cols
    # the rendered table header row EXACTLY matches the 5 contract columns (the gate
    # normalizes case/whitespace via _table_header_rows, so compare on the same footing)
    from scripts.dr_benchmark.run_validity_gate import _table_header_rows
    header_rows = _table_header_rows(result.text)
    want = [c.strip().lower() for c in cols]
    assert any(hr == want for hr in header_rows), f"header rows: {header_rows}"
    # and the contract-scaffold gate now finds the table => no run-validity violation
    violations = check_contract_scaffold(result.text, contract)
    table_violations = [v for v in violations if "table" in v.lower()]
    assert table_violations == [], f"unexpected table violations: {table_violations}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
