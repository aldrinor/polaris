"""F10 + F31 (I-arch-004 A3) — honest post-resolve verified count, gap-stub on
all-dropped, interior-collapse redaction, and bogus-marker span-grounding drop.

Both fixes strengthen reporting honesty / span-grounding and relax nothing.

F10(a) — verified-count overstatement
-------------------------------------
``resolve_provenance_to_citations`` drops degenerate fragments (and, with F31,
bogus-marker-only sentences) at RESOLUTION time. The callers historically reported
``sentences_verified`` from the PRE-resolve kept-list length (``report.total_kept`` /
``len(final_svs)`` / contract ``kept``), so the count OVERSTATED what actually shipped.
The counted resolver variant ``resolve_provenance_to_citations_with_count`` returns the
number of sentences ACTUALLY emitted; the callers now report that. ``is_gap_stub`` is
likewise POST-resolve: a section whose every kept sentence is dropped by the resolver
emits zero sentences and must render the gap stub.

F10(b) — redactor stale pre-resolve sentence (interior collapse)
----------------------------------------------------------------
The resolver collapses interior whitespace-before-punctuation (``word .`` -> ``word.``)
before a sentence ships, but the redactor's ``_normalize`` only stripped a TRAILING
period. So a non-VERIFIED claim whose audit_map sentence carried interior ``word ,`` /
``word .`` spacing was wrongly recorded ``already_absent`` while its collapsed form
SHIPPED — a silent leak. ``_normalize`` now applies the same interior collapse.

F31 — malformed provenance token survives in shipped prose
----------------------------------------------------------
A leaked bare ``[ev_<slug>]`` marker (e.g. ``[ev_brynjolfsson_genai_at_work]``) that
resolves to no real evidence-id was tolerated: it shipped as literal text AND its slug
words inflated the content-word floor. The resolver now strips every bogus bracketed
``[ev:...]`` / ``[ev_<slug>]`` marker whose id is not a real pool row, and DROPS the
sentence when no valid ``[#ev:...]`` grounding survives (stricter span-grounding).
"""

from __future__ import annotations

from src.polaris_graph.generator.provenance_generator import (
    ProvenanceToken,
    SentenceVerification,
    resolve_provenance_to_citations,
    resolve_provenance_to_citations_with_count,
    _strip_bogus_ev_markers,
)
from src.polaris_graph.roles.report_redactor import (
    reconcile_report_against_verdicts,
    _normalize,
)


def _pool() -> dict[str, dict[str, str]]:
    return {
        "ev_a": {"source_url": "https://example.com/a", "tier": "T1", "statement": "sa"},
        "ev_b": {"source_url": "https://example.com/b", "tier": "T4", "statement": "sb"},
    }


def _sv(sentence: str, ev_ids: list[str], *, warnings=None) -> SentenceVerification:
    """A kept SV. ``tokens`` is built ONLY from the given ev_ids (the canonical
    `[#ev:...]` grounding strict_verify would have parsed) — a bogus `[ev_<slug>]`
    in the prose is NOT a token here (exactly the F31 leak shape)."""
    toks = [
        ProvenanceToken(evidence_id=e, start=0, end=40, raw=f"[#ev:{e}:0-40]")
        for e in ev_ids
    ]
    return SentenceVerification(
        sentence=sentence,
        tokens=toks,
        is_verified=True,
        failure_reasons=[],
        soft_warnings=warnings or [],
    )


# ───────────────────────── F10(a): post-resolve verified count ─────────────────────────


def test_f10a_emitted_count_excludes_resolver_dropped_fragment():
    """A mixed section: one real verified sentence + one degenerate fragment that
    survived strict_verify. The emitted count is 1 (what ships), NOT 2 (the
    pre-resolve kept-list length). The count matches the number of sentences in
    the rendered text."""
    pool = _pool()
    kept = [
        _sv(
            "The treatment reduced mortality substantially in the trial [#ev:ev_a:0-40].",
            ["ev_a"],
        ),
        # Degenerate fragment: bare punctuation + citation, no content words.
        _sv(".[#ev:ev_b:0-40]", ["ev_b"]),
    ]
    text, biblio, emitted = resolve_provenance_to_citations_with_count(kept, pool)

    assert emitted == 1, "only the real sentence ships; the fragment is dropped"
    assert len(kept) == 2 and emitted < len(kept), (
        "the emitted count must be LOWER than the pre-resolve kept-list length — "
        "that is the overstatement F10(a) fixes"
    )
    # The rendered text carries exactly one sentence; the fragment's source never
    # earns an orphan bibliography row.
    assert "mortality" in text
    assert all(b["evidence_id"] != "ev_b" for b in biblio), (
        "a dropped fragment must not leave an orphan bibliography entry"
    )


def test_f10a_all_dropped_emits_zero_for_gap_stub():
    """When every kept sentence is a degenerate fragment, the resolver emits zero
    sentences — the signal a caller uses to set is_gap_stub=True (stricter: an
    all-dropped section can no longer ship a non-stub empty body)."""
    pool = _pool()
    kept = [_sv(".[#ev:ev_a:0-40]", ["ev_a"]), _sv("[#ev:ev_b:0-40]", ["ev_b"])]
    text, _biblio, emitted = resolve_provenance_to_citations_with_count(kept, pool)
    assert emitted == 0
    assert text.strip() == ""


def test_f10a_public_wrapper_is_byte_identical_two_tuple():
    """The legacy public 2-tuple API is unchanged for existing callers; the text +
    biblio it returns are identical to the counted variant's first two elements."""
    pool = _pool()
    kept = [
        _sv("Cohort survival improved by twelve percent overall [#ev:ev_a:0-40].", ["ev_a"]),
    ]
    text2, biblio2 = resolve_provenance_to_citations(kept, pool)
    text3, biblio3, _e = resolve_provenance_to_citations_with_count(kept, pool)
    assert (text2, biblio2) == (text3, biblio3)


# ───────────────────────── F31: bogus marker span-grounding ─────────────────────────


def test_f31_bogus_marker_stripped_when_valid_ev_grounds_sentence():
    """The 05-004 shape: a sentence riding a VALID [#ev:...] token PLUS a leaked
    bogus [ev_<slug>] marker. The sentence SHIPS (it has valid grounding) but the
    bogus marker is stripped from the prose — never leaks as literal text."""
    pool = _pool()
    kept = [
        _sv(
            "GenAI raised worker productivity by fourteen percent across the firm "
            "[#ev:ev_a:0-40][ev_brynjolfsson_genai_at_work].",
            ["ev_a"],
        ),
    ]
    text, biblio, emitted = resolve_provenance_to_citations_with_count(kept, pool)
    assert emitted == 1, "the sentence has a valid [#ev:] grounding -> it ships"
    assert "ev_brynjolfsson" not in text, "the bogus marker must not leak into prose"
    assert "productivity" in text
    assert text.rstrip().endswith("[1]"), "the VALID source's numbered marker rides"
    assert [b["evidence_id"] for b in biblio] == ["ev_a"]


def test_f31_bogus_only_sentence_is_dropped():
    """A sentence whose ONLY bracketed grounding is a bogus [ev_<slug>] marker — no
    valid [#ev:...] token — FAILS span-grounding and does NOT ship (stricter)."""
    pool = _pool()
    kept = [
        # No valid tokens (the leaked marker is not a parsed token); strict_verify
        # would normally not pass this, but the resolver is the belt-and-suspenders.
        _sv(
            "Productivity rose dramatically across every department last year "
            "[ev_brynjolfsson_genai_at_work].",
            [],
        ),
    ]
    text, biblio, emitted = resolve_provenance_to_citations_with_count(kept, pool)
    assert emitted == 0, "a bogus-only sentence must not ship"
    assert text.strip() == ""
    assert biblio == [], "no bibliography row for a dropped bogus-only sentence"


def test_f31_strip_keeps_real_id_bare_marker_and_numbered_markers():
    """The strip helper removes a marker whose id is NOT a real pool row, but leaves
    a bare marker whose id IS a real row, and never touches a numbered [N] marker."""
    pool = _pool()
    s = "Alpha beta gamma [ev_not_real] and delta epsilon [ev_a] zeta [3]."
    out = _strip_bogus_ev_markers(s, pool)
    assert "ev_not_real" not in out, "bogus id -> stripped"
    assert "[ev_a]" in out, "real id bare marker -> kept (defensive, not stripped)"
    assert "[3]" in out, "numbered markers are never touched"


def test_f31_bogus_slug_words_do_not_inflate_content_floor():
    """A degenerate fragment whose only 'content' comes from a bogus marker's slug
    must still be dropped — the slug words cannot prop a fragment over the floor."""
    pool = _pool()
    # After stripping [#ev:] and the bogus marker, the prose is just "." — a fragment.
    kept = [_sv(". [#ev:ev_a:0-40][ev_brynjolfsson_genai_at_work_productivity].", ["ev_a"])]
    _text, _biblio, emitted = resolve_provenance_to_citations_with_count(kept, pool)
    assert emitted == 0, "slug words must not let a punctuation-only fragment survive"


# ───────────────────────── F10(b): interior-collapse redaction ─────────────────────────


def test_f10b_normalize_collapses_interior_space_before_punct():
    """_normalize now collapses interior whitespace-before-punctuation so the stem
    matches the resolver's collapsed shipped form (was: only trailing period)."""
    # space-before-comma is the case the OLD rstrip('.') normalize could not fix.
    assert _normalize("twelve thousand dollars , per the rule") == _normalize(
        "twelve thousand dollars, per the rule"
    )
    assert _normalize("the rule applied here . Next") == _normalize(
        "the rule applied here. Next"
    )


def test_f10b_interior_collapse_claim_is_redacted_not_already_absent():
    """The 06-006 interior-collapse case: the audit_map sentence carries interior
    'word ,' spacing (pre-resolve); the shipped report has the collapsed 'word,'
    form. Before the fix the stem missed the shipped form and the claim was wrongly
    recorded already_absent (a silent leak). It must now be LOCATED and REDACTED,
    leaving the VERIFIED neighbor's [N] marker byte-for-byte."""
    audit_sentence = (
        "The penalty was 27874 dollars , per violation under the federal rule."
    )
    report = (
        "Findings: The penalty was 27874 dollars, per violation under the federal "
        "rule.[3] Other verified prose ships here cleanly and stays intact.[4]"
    )
    verdicts = {"06-006": "UNSUPPORTED"}
    audit_map = {"06-006": {"sentence": audit_sentence, "severity": "S1"}}

    result = reconcile_report_against_verdicts(report, verdicts, audit_map)

    assert result.redacted_count == 1, "the interior-collapse claim must be redacted"
    assert "06-006" not in result.already_absent, (
        "the present-but-collapsed claim must NOT be recorded already_absent (leak)"
    )
    assert "27874" not in result.report_text, "the unsupported penalty figure is gone"
    assert "[4]" in result.report_text, "the VERIFIED neighbor keeps its [N] marker"
    assert "Other verified prose ships here cleanly" in result.report_text
