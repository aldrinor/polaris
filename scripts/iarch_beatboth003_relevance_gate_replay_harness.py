#!/usr/bin/env python3
"""§-1.4 fail-loud BEHAVIORAL replay harness for the SURE-RAG per-citation relevance
gate (I-beatboth-003, #1280) — INCREMENT 1 (F3-0).

This harness drives the REAL ``strict_verify`` -> ``resolve_provenance_to_citations``
render path with a MOCKED three-way judge (deterministic, NO model spend) and asserts the
demotion / contradiction-routing / always-release / minimum-retention effects ACTUALLY
APPEAR IN THE RENDERED OUTPUT. It is the mechanical embodiment of CLAUDE.md §-1.4:
acceptance = "the effect ACTUALLY FIRES in the real output", NOT "Codex approved the diff"
NOT "tests are green". It FAILS LOUD (non-zero exit) on a silent no-op.

Assertions (each FAILS LOUD on violation):
  (a) a citation the fake judge labels INSUFFICIENT is DEMOTED from a support cite to
      listed-not-load-bearing (its inline ``[N]`` marker is GONE from the sentence).
  (b) a REFUTED citation is routed to a contradiction flag (not a support cite) — its inline
      marker is GONE and the sentence carries a contradiction soft-warning / flag.
  (b-new) the REFUTED citation produces a PERSISTED CONTRADICTION FLAG on the verification
      record: the SentenceVerification carries a ``relevance_refuted_contradiction`` soft-
      warning AND the refuter's evidence_id is in the SEPARATE ``relevance_refuted_eids``
      set (Refuted kept DISTINCT from Insufficient, not merely demoted). This proves the
      Refuted label is ROUTED to an inspectable contradiction marker, not silently dropped.
  (c) the report STILL ships (always-release) — the sentence text is present in the output.
  (d) MINIMUM-RETENTION: a statement whose ONLY citation would be demoted is NOT stranded —
      it retains >=1 inline citation (re-anchor / keep + mark weak), never cited->uncited.
  (c-new) the last-cite-retention case PERSISTS the WEAK mark on the statement: the solo
      sentence's SentenceVerification carries a ``relevance_statement_weak`` soft-warning
      (the statement is ACTUALLY marked weak, not merely a telemetry bump).
  (e) with the flag OFF, behavior is byte-identical — the injected judge is NEVER called
      (a judge that RAISES if invoked proves it), and the rendered output equals the
      no-judge baseline.

Run it directly:
    python scripts/iarch_beatboth003_relevance_gate_replay_harness.py
Exit 0 = all behavioral assertions PASS. Exit 1 = a silent no-op / regression FIRED LOUD.

RED-FIRST DISCIPLINE: run against the UNMODIFIED provenance_generator.py first — the
demotion path does not exist yet, so (a)/(b)/(d) FAIL LOUD (the INSUFFICIENT/REFUTED markers
still render as support cites). After F3-2/F3-3 wire the label semantics, the SAME harness
must PASS.

The two NEW assertions (b-new) + (c-new) are the §-1.4 completeness fix for diff-gate iter-2:
they target the Codex P1 silent no-ops. Pre-fix, the per-citation LABEL side-output is
COMPUTED then DISCARDED (``_rel_warnings`` never persisted), Refuted is collapsed into the
Insufficient demote set (no separate ``relevance_refuted_eids``), and the minimum-retention
guard only bumps telemetry (never marks the statement weak). Run this strengthened harness
against the CURRENT (pre-fix) code: (b-new)+(c-new) RED-fail LOUD (the contradiction flag and
the weak mark are absent from the SV). After the fix they GREEN.
"""

from __future__ import annotations

import os
import re
import sys

# Deterministic, fully offline env BEFORE importing the gate module.
os.environ.setdefault("PG_STRICT_VERIFY_ENTAILMENT", "off")  # no LLM in strict_verify
os.environ.setdefault("PG_PROVENANCE_REANCHOR", "0")  # keep render path simple/byte-stable
os.environ.setdefault("PG_SPAN_RESOLVER", "0")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.polaris_graph.generator import provenance_generator as pg  # noqa: E402
from src.polaris_graph.generator import relevance_judge as rj  # noqa: E402


class HarnessFailure(AssertionError):
    """Raised when a behavioral assertion fails — surfaced as a non-zero exit."""


# ─────────────────────────────────────────────────────────────────────────────
# Fixture corpus. Each evidence row's direct_quote is a span that PASSES the
# deterministic strict_verify checks for its claim sentence (number match +
# >=2 content-word overlap), so all three citations are KEPT by strict_verify.
# The relevance judge (mocked) is what distinguishes their RELATION quality.
# ─────────────────────────────────────────────────────────────────────────────
def _evidence_pool() -> dict:
    return {
        "ev_support": {
            "source_url": "https://example.org/trial-a",
            "tier": "T1",
            "statement": "Drug X reduced systolic blood pressure by 12 mmHg versus placebo.",
            "direct_quote": "Drug X reduced systolic blood pressure by 12 mmHg versus placebo.",
        },
        "ev_offtopic": {
            "source_url": "https://example.org/review-b",
            "tier": "T2",
            # Mentions the right entities ("Drug X", "blood pressure") WITHOUT establishing
            # the reduction relation — the off-topic-but-topical INSUFFICIENT case. Carries
            # the same "12" so it clears the numeric check, but the relation is wrong.
            "statement": "Drug X and blood pressure were discussed at the 12th annual symposium.",
            "direct_quote": "Drug X and blood pressure were discussed at the 12th annual symposium.",
        },
        "ev_refuter": {
            "source_url": "https://example.org/trial-c",
            "tier": "T1",
            "statement": "Drug X increased systolic blood pressure by 12 mmHg in a subgroup.",
            "direct_quote": "Drug X increased systolic blood pressure by 12 mmHg in a subgroup.",
        },
        "ev_solo_offtopic": {
            "source_url": "https://example.org/news-d",
            "tier": "T4",
            "statement": "Therapy Y improved patient adherence rates by 30 percent overall.",
            "direct_quote": "Therapy Y improved patient adherence rates by 30 percent overall.",
        },
    }


# Span offsets are the FULL direct_quote length for each row, so the cited sub-span is the
# whole sentence and the mock judge can recognize it by a distinctive substring. The numbers
# (12 / 30) appear in each span so the deterministic strict_verify numeric check passes.
_SPAN_SUPPORT = len(_evidence_pool()["ev_support"]["direct_quote"])
_SPAN_OFFTOPIC = len(_evidence_pool()["ev_offtopic"]["direct_quote"])
_SPAN_REFUTER = len(_evidence_pool()["ev_refuter"]["direct_quote"])
_SPAN_SOLO = len(_evidence_pool()["ev_solo_offtopic"]["direct_quote"])


def _multi_cited_draft() -> str:
    """A sentence cited by THREE sources: one genuine support, one off-topic (INSUFFICIENT),
    one refuter (REFUTED). After the gate, only ev_support stays a support cite."""
    return (
        "Drug X reduced systolic blood pressure by 12 mmHg versus placebo "
        f"[#ev:ev_support:0-{_SPAN_SUPPORT}]"
        f"[#ev:ev_offtopic:0-{_SPAN_OFFTOPIC}]"
        f"[#ev:ev_refuter:0-{_SPAN_REFUTER}]."
    )


def _solo_cited_draft() -> str:
    """A sentence whose ONLY citation is off-topic (INSUFFICIENT). Minimum-retention forbids
    demoting it to zero — the citation must be KEPT (statement marked weak), never stranded."""
    return (
        "Therapy Y improved patient adherence rates by 30 percent overall "
        f"[#ev:ev_solo_offtopic:0-{_SPAN_SOLO}]."
    )


# Mock judge: deterministic label by a distinctive substring of the cited span text (the
# harness controls which span belongs to which row; matching on a contained substring is
# robust to the exact start/end offsets).
def _mock_judge(claim: str, span: str) -> "tuple[str, str]":
    if "reduced systolic blood pressure" in span:
        return (rj.LABEL_SUPPORTED, "establishes the reduction relation")
    if "discussed at the 12th annual symposium" in span:
        return (rj.LABEL_INSUFFICIENT, "mentions entity, wrong relation")
    if "increased systolic blood pressure" in span:
        return (rj.LABEL_REFUTED, "contradicts the reduction claim")
    if "improved patient adherence" in span:
        return (rj.LABEL_INSUFFICIENT, "off-topic for the cited claim")
    return (rj.LABEL_SUPPORTED, "default")


def _judge_that_raises(claim: str, span: str) -> "tuple[str, str]":
    raise AssertionError(
        "relevance judge was invoked while PG_RELEVANCE_GATE is OFF — OFF path is NOT a no-op!"
    )


_MARKER_RE = re.compile(r"\[(\d+)\]")


def _inline_markers(sentence_region: str) -> set[str]:
    return set(_MARKER_RE.findall(sentence_region))


def _num_for_url(biblio: list, url: str) -> str | None:
    for row in biblio:
        if row.get("url") == url:
            return str(row.get("num"))
    return None


def _render(draft: str, pool: dict, *, judge_fn, gate_on: bool) -> "tuple[str, list, list]":
    """Drive the REAL strict_verify -> resolve path. judge_fn is injected so the gate is
    mocked; gate_on toggles PG_RELEVANCE_GATE for this call.

    Returns (rendered_text, bibliography, kept_sentences). The kept_sentences are the SAME
    SentenceVerification objects the resolver mutates in place (it caches the final
    post-retention demote/refute decision + soft-warnings on each SV), so the harness can
    inspect the PERSISTED contradiction flag + weak mark on the verification record — the
    (b-new) + (c-new) §-1.4 assertions that the per-citation label side-output actually
    LANDS on the SV rather than being computed and discarded."""
    pg.reset_relevance_telemetry()
    prev = os.environ.get("PG_RELEVANCE_GATE")
    os.environ["PG_RELEVANCE_GATE"] = "1" if gate_on else "0"
    rj.reset_judge_singleton()
    try:
        report = pg.strict_verify(draft, pool, require_number_match=True)
        # The render call accepts the injected judge via the new keyword (added in F3-3).
        # When the keyword does not yet exist (RED, unmodified code) we fall back to the
        # 2-arg call so the harness still drives the path and the assertions fail LOUD on
        # the un-demoted output rather than on a TypeError.
        try:
            text, biblio = pg.resolve_provenance_to_citations(
                report.kept_sentences, pool, relevance_judge_fn=judge_fn,
            )
        except TypeError:
            text, biblio = pg.resolve_provenance_to_citations(
                report.kept_sentences, pool,
            )
        return text, biblio, report.kept_sentences
    finally:
        if prev is None:
            os.environ.pop("PG_RELEVANCE_GATE", None)
        else:
            os.environ["PG_RELEVANCE_GATE"] = prev


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise HarnessFailure(msg)


def _sv_soft_warnings(svs: list) -> list[str]:
    """Flatten the persisted soft_warnings across all kept SentenceVerifications. Uses
    getattr so a pre-fix SV (no soft_warnings populated by the gate) yields a value-RED
    (empty list) rather than crashing — the assertion fails LOUD on the MISSING effect,
    not on an AttributeError."""
    out: list[str] = []
    for sv in svs or []:
        out.extend(list(getattr(sv, "soft_warnings", None) or []))
    return out


def _sv_refuted_eids(svs: list) -> set[str]:
    """Union of the PERSISTED, SEPARATE Refuted-eid sets across kept SVs. getattr-guarded:
    pre-fix this attribute does not exist -> empty set -> value-RED, not a crash. This is
    the (b-new) proof that Refuted is kept DISTINCT from Insufficient (two sets), routed to
    a contradiction marker rather than merely demoted into the Insufficient set."""
    out: set[str] = set()
    for sv in svs or []:
        out |= set(getattr(sv, "relevance_refuted_eids", None) or frozenset())
    return out


def run() -> None:
    pool = _evidence_pool()

    # ── Case 1: multi-cited sentence (support + insufficient + refuter) ──────────
    multi = _multi_cited_draft()
    text, biblio, svs = _render(multi, pool, judge_fn=_mock_judge, gate_on=True)

    # (c) always-release: the sentence text must still ship.
    _check(
        "reduced systolic blood pressure by 12 mmHg" in text,
        "(c) always-release VIOLATED: the verified sentence did not ship in the output:\n" + text,
    )

    markers = _inline_markers(text)
    n_support = _num_for_url(biblio, "https://example.org/trial-a")
    n_offtopic = _num_for_url(biblio, "https://example.org/review-b")
    n_refuter = _num_for_url(biblio, "https://example.org/trial-c")

    # The genuine support citation MUST remain inline.
    _check(
        n_support is not None and n_support in markers,
        f"(genuine support) VIOLATED: ev_support cite [{n_support}] is not an inline support "
        f"marker. markers={sorted(markers)} text={text!r}",
    )

    # (a) INSUFFICIENT -> demoted: its inline support marker must be GONE.
    _check(
        n_offtopic is None or n_offtopic not in markers,
        f"(a) DEMOTION VIOLATED: ev_offtopic (INSUFFICIENT) still renders as inline support "
        f"cite [{n_offtopic}]. markers={sorted(markers)} text={text!r}",
    )

    # (b) REFUTED -> contradiction flag, not a support cite: inline marker GONE.
    _check(
        n_refuter is None or n_refuter not in markers,
        f"(b) REFUTED-ROUTING VIOLATED: ev_refuter (REFUTED) still renders as inline support "
        f"cite [{n_refuter}]. markers={sorted(markers)} text={text!r}",
    )

    # (b-new) §-1.4 COMPLETENESS: the REFUTED label must produce a PERSISTED, INSPECTABLE
    # contradiction flag on the verification record — NOT just be removed from inline support
    # (the Codex P1 silent no-op). Two persisted effects, both checked:
    #   1. the SV carries a ``relevance_refuted_contradiction`` soft-warning naming the refuter
    #      (the side-output the pre-fix code COMPUTED at _classify_sentence_citations then
    #      DISCARDED at the _rel_warnings call site — never landed on the SV).
    #   2. the refuter's eid is in the SEPARATE ``relevance_refuted_eids`` set, kept DISTINCT
    #      from the Insufficient demote set (pre-fix Refuted was collapsed into one
    #      ``relevance_demoted_eids`` frozenset — "merely demoted", no contradiction routing).
    _all_warnings = _sv_soft_warnings(svs)
    _refuted_eids = _sv_refuted_eids(svs)
    _contradiction_marker = any(
        w.startswith("relevance_refuted_contradiction") and "ev_refuter" in w
        for w in _all_warnings
    )
    _check(
        _contradiction_marker,
        "(b-new) REFUTED-CONTRADICTION NOT PERSISTED: the REFUTED citation (ev_refuter) was "
        "removed from inline support but NO 'relevance_refuted_contradiction' soft-warning "
        "landed on the SentenceVerification — the contradiction flag was COMPUTED then "
        f"DISCARDED (silent no-op). persisted soft_warnings={_all_warnings!r}",
    )
    _check(
        "ev_refuter" in _refuted_eids,
        "(b-new) REFUTED NOT KEPT SEPARATE: ev_refuter is not in the distinct "
        "relevance_refuted_eids set — Refuted was merely collapsed into the Insufficient "
        f"demote set, not routed to a contradiction flag. relevance_refuted_eids={sorted(_refuted_eids)}",
    )

    # (d) over-drop tripwire on the multi-cited sentence: it had >=1 inline cite before the
    # gate, so it must retain >=1 after (it keeps ev_support). cited->uncited is FORBIDDEN.
    _check(
        len(markers) >= 1,
        "(d) OVER-DROP TRIPWIRE: a previously-cited sentence went cited->UNCITED "
        f"(stranded). markers={sorted(markers)} text={text!r}",
    )

    # ── Case 2: minimum-retention — solo off-topic citation must NOT strand ───────
    solo = _solo_cited_draft()
    text2, biblio2, svs2 = _render(solo, pool, judge_fn=_mock_judge, gate_on=True)
    _check(
        "improved patient adherence rates by 30 percent" in text2,
        "(c/solo) always-release VIOLATED: the solo sentence did not ship:\n" + text2,
    )
    markers2 = _inline_markers(text2)
    _check(
        len(markers2) >= 1,
        "(d) MINIMUM-RETENTION VIOLATED: a statement whose ONLY citation was INSUFFICIENT "
        f"was STRANDED uncited. markers={sorted(markers2)} text={text2!r}",
    )

    # (c-new) §-1.4 COMPLETENESS: when the retention guard fires (the last support cite would
    # have been demoted), the statement must be ACTUALLY MARKED WEAK — a persisted
    # ``relevance_statement_weak`` soft-warning on the SV — NOT merely a telemetry counter
    # bump (the Codex P1 silent no-op). Pre-fix RELEVANCE_WEAK_PREFIX is DEFINED but never
    # constructed anywhere, so this RED-fails LOUD on the current code.
    _solo_warnings = _sv_soft_warnings(svs2)
    _check(
        any(w.startswith("relevance_statement_weak") for w in _solo_warnings),
        "(c-new) WEAK MARK NOT PERSISTED: the minimum-retention guard fired (citation kept) "
        "but NO 'relevance_statement_weak' soft-warning landed on the SentenceVerification — "
        "the statement was never actually marked weak, only telemetry bumped (silent no-op). "
        f"persisted soft_warnings={_solo_warnings!r}",
    )

    # ── Case 3: OFF path is byte-identical AND never calls the judge ──────────────
    # A judge that RAISES if called proves the OFF path never invokes it.
    baseline_text, baseline_biblio, _baseline_svs = _render(
        multi, pool, judge_fn=None, gate_on=False,
    )
    off_text, off_biblio, _off_svs = _render(
        multi, pool, judge_fn=_judge_that_raises, gate_on=False,
    )
    _check(
        off_text == baseline_text,
        "(e) OFF byte-identity VIOLATED: PG_RELEVANCE_GATE=0 render differs from the "
        f"no-judge baseline.\nbaseline={baseline_text!r}\noff={off_text!r}",
    )
    # With the gate OFF, ALL THREE original citations must still render as inline support
    # (the gate did nothing) — confirms the OFF path is the legacy behavior.
    off_markers = _inline_markers(off_text)
    for url, lbl in (
        ("https://example.org/trial-a", "support"),
        ("https://example.org/review-b", "offtopic"),
        ("https://example.org/trial-c", "refuter"),
    ):
        n = _num_for_url(off_biblio, url)
        _check(
            n is not None and n in off_markers,
            f"(e) OFF path is NOT legacy: {lbl} cite [{n}] missing from the OFF render. "
            f"markers={sorted(off_markers)} text={off_text!r}",
        )

    print("RELEVANCE-GATE REPLAY HARNESS: PASS")
    print(f"  case1 multi-cite render: {text!r}")
    print(f"  case2 solo-retention render: {text2!r}")
    print(f"  case3 OFF byte-identical to baseline: {off_text == baseline_text}")


def main() -> int:
    try:
        run()
    except HarnessFailure as exc:
        print("RELEVANCE-GATE REPLAY HARNESS: FAIL (behavioral assertion)", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — any unexpected error is a loud failure
        print("RELEVANCE-GATE REPLAY HARNESS: ERROR", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
