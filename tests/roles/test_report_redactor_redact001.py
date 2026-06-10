"""I-redact-001 (#1181) — report_redactor must REDACT a present-but-hard-to-pin
UNSUPPORTED claim, not abort the whole report.

Regression context
------------------
F01 (#1174) made redaction severity-INDEPENDENT (every non-VERIFIED claim, incl. S3
observe-only, must be redacted). That exposed a pre-existing weakness: when the renderer
under-split two real sentences into one over-long span (no terminal period before a [N]
marker, or a next sentence beginning with a digit), the rejected claim's stem covered
< ``_MIN_REDACTION_COVERAGE`` of that merged span, so no single span matched, the stem was
"present but unpinnable", and ``reconcile_report_against_verdicts`` raised
``ReportRedactionError`` -> ``abort_report_redaction_failed`` for the WHOLE run. All 5
beat-both questions aborted with zero reports shipped.

This module loads the 3 REAL failing cases (drb_76 / drb_78 / drb_90) from
``outputs/audits/I-redact-001/redaction_fixture.json`` and asserts each now redacts +
SHIPS (no ``ReportRedactionError``) while the unsupported prose is gone and the VERIFIED
neighbor sentence keeps its [N] markers byte-for-byte. It then pins the issue acceptance
matrix with SYNTHETIC invariant tests:
  (a) sub-clause-in-longer-sentence redacts;
  (b) a claim spanning 2 rendered sentences redacts both;
  (c) a VERIFIED neighbor keeps its [N] citation byte-for-byte;
  (d) a genuinely-ABSENT claim STILL raises ``ReportRedactionError`` (the real-inconsistency
      fail-closed path is preserved).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.polaris_graph.roles.report_redactor import (
    ReportRedactionError,
    reconcile_report_against_verdicts,
)
from src.polaris_graph.roles import report_redactor as _redactor

# The 3 REAL failing cases captured offline from the beat-both re-run @454b7652 on the VM.
# Codex iter-1 P1-2: the fixture lives under tests/fixtures/ (LAW VI: test fixtures live in
# tests/fixtures/) so a clean CI checkout always has it — the prior outputs/audits/ path is
# gitignored and untracked, so parametrize collection (which reads the fixture at COLLECT time)
# failed on CI and took down the whole module. parents[1] of tests/roles/<file> == tests/.
# A copy is retained under outputs/audits/I-redact-001/ for the audit trail; the TEST reads
# tests/fixtures/.
_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "redaction_fixture_redact001.json"
)


def _load_cases() -> list[dict]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) == 3, "fixture must carry exactly the 3 real failing cases"
    return cases


def _normalized(text: str) -> str:
    """Test-side normalize matching the module's matching projection (citation/whitespace-
    insensitive, trailing-period-stripped) so 'prose gone' is asserted in the same space the
    redactor matches in."""
    return _redactor._normalize(text)


# ─────────────────────────────────────────────────────────────────
# RED -> GREEN on the 3 REAL cases: each must now redact + ship (no abort).
# ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["case_id"])
def test_real_case_redacts_and_ships(case: dict):
    """The real failing claim is redacted, its prose is gone from the shipped report, and
    reconcile does NOT raise (status != abort_report_redaction_failed)."""
    res = reconcile_report_against_verdicts(
        case["report_text"], case["final_verdicts"], case["audit_map"]
    )
    target_id = case["target_claim_id"]
    redacted_ids = {rc.claim_id for rc in res.redacted}
    assert target_id in redacted_ids, f"{case['case_id']}: target {target_id} not redacted"
    # The rejected prose must be GONE from the shipped body (no leak).
    assert case["target_stem_normalized"] not in _normalized(res.report_text), (
        f"{case['case_id']}: UNSUPPORTED stem still present after redaction (leak)"
    )
    # The gap language was inserted (refuse-in-place, not a silent drop).
    assert _redactor._GAP_REPLACEMENT in res.report_text


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["case_id"])
def test_real_case_verified_neighbor_survives_byte_for_byte(case: dict):
    """The VERIFIED neighbor merged into the same under-split span keeps its rendered prose
    AND its [N] citation markers byte-for-byte (Codex iter-1 P1: never strip a survivor's
    citation). The neighbor lead text is asserted present unchanged."""
    res = reconcile_report_against_verdicts(
        case["report_text"], case["final_verdicts"], case["audit_map"]
    )
    # The neighbor's first words (a distinctive, citation-free lead) must survive verbatim.
    neighbor_lead = " ".join(case["neighbor_sentence"].split()[:8])
    assert neighbor_lead in res.report_text, (
        f"{case['case_id']}: VERIFIED neighbor lead {neighbor_lead!r} was over-redacted"
    )
    # The neighbor is still a VERIFIED verdict in the fixture (sanity on the fixture itself).
    assert case["final_verdicts"][case["neighbor_claim_id"]] == "VERIFIED"


def test_real_cases_preserve_neighbor_citation_markers():
    """Per-case byte-for-byte [N] survival of the VERIFIED neighbor's own citation markers."""
    # The neighbor's trailing rendered marker(s) per real case (the [N] that cite the survivor).
    neighbor_markers = {
        "drb_76": ["risk[1]"],            # 04-003 survivor ends "...risk[1]"
        "drb_78": ["days.[10]"],          # 05-007 survivor ends "...4.3 days.[10]"
        "drb_90": ["recovery[17][22]"],   # 07-001 survivor ends "...recovery[17][22]"
    }
    for case in _load_cases():
        res = reconcile_report_against_verdicts(
            case["report_text"], case["final_verdicts"], case["audit_map"]
        )
        for marker in neighbor_markers[case["case_id"]]:
            assert marker in case["report_text"], (
                f"fixture sanity: {marker!r} should be in the pre-redaction {case['case_id']}"
            )
            assert marker in res.report_text, (
                f"{case['case_id']}: VERIFIED neighbor marker {marker!r} dropped on redaction"
            )


# ─────────────────────────────────────────────────────────────────
# SYNTHETIC invariant tests (issue acceptance a-d).
# ─────────────────────────────────────────────────────────────────

def test_a_subclause_in_longer_sentence_redacts():
    """(a) A non-VERIFIED claim whose stored sentence is a SUB-CLAUSE of a longer rendered
    sentence (boundary under-split: no terminal period before the [N] marker) is redacted —
    not aborted — and the VERIFIED neighbor clause keeps its [N]."""
    # The renderer merged a VERIFIED neighbor and the UNSUPPORTED claim into one span because
    # the first sentence ended "...risk[1]" with no period before the marker (subtype A).
    report = (
        "A meta-analysis examined fiber and colorectal cancer risk[1] "
        "Cereal fiber yielded an RR of 0.90 based on eight studies.[1]\n"
    )
    audit = {
        "claim-bad": {
            "sentence": "Cereal fiber yielded an RR of 0.90 based on eight studies [#ev:e:0-9].",
            "severity": "S1",
        },
        "claim-good": {
            "sentence": "A meta-analysis examined fiber and colorectal cancer risk [#ev:e:0-9].",
            "severity": "S1",
        },
    }
    fv = {"claim-bad": "UNSUPPORTED", "claim-good": "VERIFIED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert "Cereal fiber yielded an RR of 0.90" not in res.report_text  # claim gone
    assert "A meta-analysis examined fiber and colorectal cancer risk[1]" in res.report_text
    assert "claim-bad" in {rc.claim_id for rc in res.redacted}


def test_b_claim_spanning_two_rendered_sentences_redacts_both():
    """(b) A claim whose stored sentence straddles TWO rendered sentence spans (the renderer
    split one stored claim across a '.' boundary) redacts BOTH spans (the minimal consecutive-
    span set), while a VERIFIED sentence on the same line is preserved with its marker."""
    # Stored claim text spans two rendered sentences: "...first half. And the second half...".
    report = (
        "Verified opening fact about the dataset.[9] "
        "The intervention reduced events by forty percent. And it did so without "
        "any increase in adverse outcomes.[3]\n"
    )
    audit = {
        "straddle": {
            "sentence": (
                "The intervention reduced events by forty percent. And it did so without "
                "any increase in adverse outcomes [#ev:e:0-9]."
            ),
            "severity": "S1",
        },
        "kept": {
            "sentence": "Verified opening fact about the dataset [#ev:e:0-9].",
            "severity": "S1",
        },
    }
    fv = {"straddle": "UNSUPPORTED", "kept": "VERIFIED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    # BOTH halves of the straddling claim are gone.
    assert "reduced events by forty percent" not in res.report_text
    assert "without any increase in adverse outcomes" not in res.report_text
    # The VERIFIED neighbor and its [9] marker survive byte-for-byte.
    assert "Verified opening fact about the dataset.[9]" in res.report_text
    assert "straddle" in {rc.claim_id for rc in res.redacted}


def test_c_verified_neighbor_keeps_its_citation():
    """(c) Redacting an UNSUPPORTED middle sentence consumes only ITS OWN marker; the [8] and
    [7] of the VERIFIED sentences on either side survive byte-for-byte."""
    report = "Alpha verified one.[8] Bravo bad claim sentence here.[4] Charlie verified two.[7]\n"
    audit = {"bravo": {"sentence": "Bravo bad claim sentence here [#ev:e:0-9].", "severity": "S1"}}
    fv = {"bravo": "UNSUPPORTED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert "Alpha verified one.[8]" in res.report_text
    assert "Charlie verified two.[7]" in res.report_text
    assert "Bravo bad claim sentence here" not in res.report_text
    assert "[4]" not in res.report_text  # the redacted claim's own marker leaves with it
    assert "bravo" in {rc.claim_id for rc in res.redacted}


def test_d_genuinely_absent_claim_still_raises():
    """(d) FAIL-CLOSED preserved: when a non-VERIFIED claim's prose is GENUINELY present only
    inside a heading the redactor must not touch (so it cannot be bounded to any redactable
    unit), reconcile STILL raises ReportRedactionError — a real inconsistency, not a hard-to-pin
    one — so the caller takes abort_report_redaction_failed rather than ship an unredacted leak.
    """
    report = "# Heading mentioning the secret penalty figure inline\n\nBody line unrelated.\n"
    audit = {
        "absent-in-body": {
            "sentence": "the secret penalty figure [#ev:x:0-10].",
            "severity": "S2",
        }
    }
    fv = {"absent-in-body": "UNSUPPORTED"}
    with pytest.raises(ReportRedactionError):
        reconcile_report_against_verdicts(report, fv, audit)


def test_d2_truly_absent_prose_is_already_absent_not_error():
    """(d, SAFE side) When the prose is GENUINELY absent from the rendered body (downstream
    dedup removed it), it is recorded as already_absent and does NOT raise — only a prose that
    is PRESENT-but-unbounded raises."""
    report = "An entirely unrelated verified body sentence about something else.[2]\n"
    audit = {"gone": {"sentence": "A claim about a topic not in the report [#ev:e:0-9].", "severity": "S2"}}
    fv = {"gone": "UNSUPPORTED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert "gone" in res.already_absent
    assert res.redacted == []
    assert res.report_text == report  # byte-identical: nothing redacted


# ─────────────────────────────────────────────────────────────────
# BOUNDARY-REGEX safety: the hardened _SENTENCE_BOUNDARY_RE must NOT introduce false splits
# on decimals / abbreviations (decimal/multilingual-safe invariant).
# ─────────────────────────────────────────────────────────────────

def test_boundary_does_not_split_decimal_or_abbreviation():
    """A short UNSUPPORTED claim sharing words with a LONGER VERIFIED sentence that contains
    decimals ('0.90'), an abbreviation ('U.S.', 'No. 157') must not over-redact the survivor —
    the hardened boundary still treats those as intra-sentence, so the coverage floor protects
    the longer VERIFIED sentence."""
    report = (
        "Recall is high.[1] "
        "Under U.S. rule No. 157 the model achieves recall of 0.90 across every benchmark.[2]\n"
    )
    audit = {"short": {"sentence": "Recall is high [#ev:e:0-9].", "severity": "S2"}}
    fv = {"short": "UNSUPPORTED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert "Recall is high.[1]" not in res.report_text  # own sentence redacted
    # The longer VERIFIED sentence with decimal + abbreviations survives untouched, with [2].
    assert "Under U.S. rule No. 157 the model achieves recall of 0.90 across every benchmark.[2]" in res.report_text


def test_digit_start_boundary_splits_for_redaction():
    """Subtype B (drb_78 shape): a real boundary '...adherence.[16] 87.3% of...' where the next
    sentence starts with a digit is now split, so the UNSUPPORTED first sentence redacts alone
    and the VERIFIED digit-led neighbor keeps its marker."""
    report = (
        "However the wearable evidence shows poor long-term adherence.[16] "
        "87.3% of patients used rechargeable devices over the study.[10]\n"
    )
    audit = {
        "bad": {
            "sentence": "However the wearable evidence shows poor long-term adherence [#ev:e:0-9].",
            "severity": "S3",
        },
        "good": {
            "sentence": "87.3% of patients used rechargeable devices over the study [#ev:e:0-9].",
            "severity": "S3",
        },
    }
    fv = {"bad": "UNSUPPORTED", "good": "VERIFIED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert "However the wearable evidence shows poor long-term adherence" not in res.report_text
    assert "87.3% of patients used rechargeable devices over the study.[10]" in res.report_text
    assert "bad" in {rc.claim_id for rc in res.redacted}


# ─────────────────────────────────────────────────────────────────
# Codex iter-1 P1-1 — MULTI-OCCURRENCE LEAK: a non-VERIFIED stem appearing twice (once clean,
# once under-split) must have BOTH occurrences removed, recorded ONCE in result.redacted.
# ─────────────────────────────────────────────────────────────────

def test_p1_1_multi_occurrence_both_removed_once_recorded():
    """The same UNSUPPORTED stem appears TWICE: once as a clean discrete sentence (TIER 1) and
    once inside a boundary-under-split merge with a VERIFIED neighbor (TIER 2 — no terminal
    period before the marker). The prior single-pass logic stopped after the first removal and
    left the second occurrence in the body (a leak). Both must now be gone, the claim recorded
    exactly once, and the VERIFIED neighbor's [N] preserved byte-for-byte."""
    stem_prose = "The device cut events by exactly forty two percent"
    # Occurrence 1 (line 1): a clean discrete rendered sentence — pins at TIER 1 (coverage >= floor).
    # Occurrence 2 (line 2): UNDER-SPLIT — the VERIFIED neighbor ends "...registry[7]" with NO
    # period before the marker. ARM 3 splits there, but the RIGHT span is long (the claim plus a
    # trailing verified-looking clause), so the stem covers < _MIN_REDACTION_COVERAGE of it and
    # TIER 1 misses it; only TIER 2 (minimal containing unit) catches this occurrence. This is
    # exactly the clean+under-split pair the P1-1 loop must clear (the prior single-pass logic
    # stopped after the line-1 removal and left line 2 in the body — a leak).
    report = (
        f"{stem_prose}.[3] An unrelated verified closing sentence here.[5]\n"
        f"The data came from a national registry[7] {stem_prose} and did so without raising "
        f"any adverse outcome at all over the multi year follow up window.[3]\n"
    )
    audit = {
        "dup": {"sentence": f"{stem_prose} [#ev:e:0-9].", "severity": "S1"},
        "reg": {"sentence": "The data came from a national registry [#ev:e:0-9].", "severity": "S1"},
    }
    fv = {"dup": "UNSUPPORTED", "reg": "VERIFIED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    # BOTH occurrences of the rejected prose are gone (no leak).
    assert stem_prose not in res.report_text
    assert _normalized(stem_prose) not in _normalized(res.report_text)
    # The claim is recorded exactly ONCE despite two physical removals (no double-count).
    assert [rc.claim_id for rc in res.redacted].count("dup") == 1
    # The VERIFIED neighbor on line 2 keeps its prose and its [7] marker byte-for-byte.
    assert "The data came from a national registry[7]" in res.report_text
    # The VERIFIED closing sentence on line 1 survives with its [5] marker byte-for-byte.
    assert "An unrelated verified closing sentence here.[5]" in res.report_text


def test_p1_1_multi_occurrence_both_clean_both_removed():
    """Two CLEAN occurrences of the same UNSUPPORTED stem on different lines are BOTH removed in
    one TIER-1 pass and the claim is recorded once."""
    stem_prose = "Mortality fell by thirteen percent under the protocol"
    report = (
        f"{stem_prose}.[2] Verified tail one.[9]\n"
        f"Verified head two.[4] {stem_prose}.[2]\n"
    )
    audit = {"m": {"sentence": f"{stem_prose} [#ev:e:0-9].", "severity": "S2"}}
    fv = {"m": "UNSUPPORTED"}
    res = reconcile_report_against_verdicts(report, fv, audit)
    assert stem_prose not in res.report_text
    assert [rc.claim_id for rc in res.redacted].count("m") == 1
    assert "Verified tail one.[9]" in res.report_text
    assert "Verified head two.[4]" in res.report_text


# ─────────────────────────────────────────────────────────────────
# Codex iter-1 P2 — ARM-3 OVER-SPLIT: a MID-sentence inline citation (whitespace before the
# bracket) must NOT be treated as a sentence boundary, so the verified sentence stays intact and
# the coverage floor protects it from over-redaction.
# ─────────────────────────────────────────────────────────────────

def test_p2_inline_midsentence_citation_not_split():
    """Unit pin on `_sentence_spans`: an inline mid-sentence citation '...as shown [5] In vivo...'
    (WHITESPACE before the bracket) is NOT a boundary — the word-anchored ARM 3 ``(?<=\\w)`` only
    fires on a word-attached marker like 'risk[1]'. The sentence stays ONE span; a real
    word-attached marker-as-terminator still splits."""
    # Inline citation mid-sentence: must remain ONE span (no false split).
    one = "The effect was robust as shown [5] In vivo assays confirmed the same trend.[2]"
    assert len(_redactor._sentence_spans(one)) == 1
    # Word-attached marker-as-terminator (real boundary, no preceding period): still TWO spans.
    two = "linked to higher colorectal cancer risk[1] Cereal fiber yielded an RR of 0.90.[1]"
    assert len(_redactor._sentence_spans(two)) == 2


def test_p2_inline_citation_verified_sentence_not_over_redacted():
    """End-to-end: a VERIFIED sentence with an INLINE mid-sentence citation followed by an
    UPPERCASE continuation ('as shown [5] Across …') is the exact shape that the un-hardened
    ARM 3 would FALSE-split (marker-run + whitespace + uppercase). Splitting it into two short
    spans drops each below the coverage floor and risks over-redaction. With the word-anchored
    ARM 3 the sentence stays ONE span and survives byte-for-byte (inline [5] + trailing [2]),
    while a co-located UNSUPPORTED short claim still redacts cleanly."""
    report = (
        "Recall was strong.[1] "
        "The effect was robust as shown [5] Across every clinical subgroup the model held.[2]\n"
    )
    audit = {"short": {"sentence": "Recall was strong [#ev:e:0-9].", "severity": "S2"}}
    fv = {"short": "UNSUPPORTED"}
    # Sanity: the verified sentence is a SINGLE span (no false split on the inline citation).
    verified = "The effect was robust as shown [5] Across every clinical subgroup the model held.[2]"
    assert len(_redactor._sentence_spans(verified)) == 1
    res = reconcile_report_against_verdicts(report, fv, audit)
    # The UNSUPPORTED short sentence (and only it) is redacted.
    assert "Recall was strong.[1]" not in res.report_text
    # The longer VERIFIED sentence with the inline citation survives untouched, markers intact.
    assert verified in res.report_text
