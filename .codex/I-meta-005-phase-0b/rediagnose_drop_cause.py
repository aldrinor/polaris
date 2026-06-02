"""Phase 0b (#984, gap #18) RE-DIAGNOSIS harness.

Runs the REAL production verifier (provenance_generator.verify_sentence_provenance,
the function scripts/run_honest_sweep_r3.py:58 + multi_section_generator.py:1471
actually call) on grounded multi-source policy/analytical reasoning sentences,
OFFLINE, with a stub entailment judge (no live spend).

Goal: prove EXACTLY which drop regime fires on a grounded reasoning sentence
TODAY, and confirm/refute Codex's claim that the union A+B sentence already
passes.

Stub judge is installed on src.polaris_graph.clinical_generator.strict_verify
because verify_sentence_provenance lazy-imports _get_judge / _record_judge_outcome
/ _entailment_mode FROM that module (provenance_generator.py:1184-1188).
"""
import os
import sys

# Force enforce mode (production default) so the entailment lane runs.
os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
# Keep default content-overlap floor (2) unless a case overrides.
os.environ.pop("PG_PROVENANCE_MIN_CONTENT_OVERLAP", None)

from src.polaris_graph.clinical_generator import strict_verify as csv  # noqa: E402
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    verify_sentence_provenance,
)


class StubJudge:
    """Returns ENTAILED when the combined span text contains the sentence's
    key content anchors (a real union would entail it); NEUTRAL otherwise.
    Records every (sentence, span) it is asked to judge so we can SEE which
    span text the verifier actually fed it (single-span vs union)."""

    def __init__(self, force=None):
        self.calls = []
        self.force = force  # e.g. ("ENTAILED", "judge_error: Timeout") to model fail-open

    def judge(self, sentence, span):
        self.calls.append({"sentence": sentence, "span": span})
        if self.force is not None:
            return self.force
        # A grounded reasoning sentence is ENTAILED iff BOTH premises are
        # present in the (possibly unioned) span text handed to the judge.
        s = span.lower()
        if "emission" in s and "hydro" in s:
            return ("ENTAILED", "union of A+B supports the linkage")
        return ("NEUTRAL", "single span does not entail the linkage")


def run_case(name, sentence, pool, *, force_judge=None, require_number_match=True,
             min_overlap=None):
    if min_overlap is not None:
        os.environ["PG_PROVENANCE_MIN_CONTENT_OVERLAP"] = str(min_overlap)
        # MIN_CONTENT_WORD_OVERLAP is read at import; re-bind for the test.
        import src.polaris_graph.generator.provenance_generator as pg
        pg.MIN_CONTENT_WORD_OVERLAP = min_overlap
    else:
        os.environ.pop("PG_PROVENANCE_MIN_CONTENT_OVERLAP", None)
        import src.polaris_graph.generator.provenance_generator as pg
        pg.MIN_CONTENT_WORD_OVERLAP = 2

    stub = StubJudge(force=force_judge)
    csv._get_judge = lambda: stub
    csv._JUDGE_SINGLETON = stub
    # neutralize telemetry side effects
    csv._record_judge_outcome = lambda v, r: None

    res = verify_sentence_provenance(
        sentence, pool, require_number_match=require_number_match,
    )
    print(f"\n=== CASE: {name} ===")
    print(f"  sentence: {sentence!r}")
    print(f"  is_verified: {res.is_verified}")
    print(f"  failure_reasons: {res.failure_reasons}")
    print(f"  judge_calls: {len(stub.calls)}")
    for i, c in enumerate(stub.calls):
        print(f"    judge[{i}].span = {c['span']!r}")
    return res


# Realistic 2-source policy/analytical reasoning spans.
SPAN_A = ("The provincial carbon levy reduced industrial emissions by an "
          "estimated 12 percent between 2019 and 2023.")
SPAN_B = ("Quebec's electricity grid is supplied almost entirely by hydro "
          "generation, giving it one of the lowest grid carbon intensities "
          "in North America.")

POOL = {
    "ev_a": {"direct_quote": SPAN_A, "statement": "carbon levy emissions reduction",
             "title": "Provincial carbon levy impact report"},
    "ev_b": {"direct_quote": SPAN_B, "statement": "Quebec hydro grid carbon intensity",
             "title": "Grid carbon intensity factsheet"},
}


def tok(ev, start, end):
    return f"[#ev:{ev}:{start}-{end}]"


if __name__ == "__main__":
    full_a = tok("ev_a", 0, len(SPAN_A))
    full_b = tok("ev_b", 0, len(SPAN_B))

    # CASE 1: 2-span A+B analytical reasoning sentence WITH provenance tokens,
    # grounded in the UNION. Does it pass today? (Codex's claim.)
    s1 = ("The emissions reduction is reinforced by the province's reliance on "
          f"low-carbon hydro generation {full_a}{full_b}.")
    run_case("union_AB_with_tokens", s1, POOL)

    # CASE 2: same analytical reasoning sentence but NO provenance token at all
    # (the analyst-synthesis layer that writes prose without [#ev:...]).
    s2 = ("The emissions reduction is reinforced by the province's reliance on "
          "low-carbon hydro generation.")
    run_case("synthesis_NO_token", s2, POOL)

    # CASE 3: abstract synthesis prose WITH tokens but weak lexical overlap
    # with the spans (paraphrased, policy-analytic vocabulary).
    s3 = ("Taken together, these dynamics suggest the decarbonization trajectory "
          f"is structurally durable rather than incidental {full_a}{full_b}.")
    run_case("abstract_synthesis_low_overlap", s3, POOL)

    # CASE 4: union sentence WITH tokens, but the judge fails OPEN
    # (returns ENTAILED with reason 'judge_error: ...'). Does the verifier
    # currently DROP it? (P1 #3 — the fail-open contract.)
    run_case("union_AB_judge_fails_open", s1, POOL,
             force_judge=("ENTAILED", "judge_error: ReadTimeout"))

    # CASE 5: a grounded reasoning sentence the judge calls NEUTRAL even on the
    # union (true-but-not-directly-entailed synthesis). Fail-closed at 1204?
    run_case("union_AB_judge_neutral", s1, POOL,
             force_judge=("NEUTRAL", "synthesis not directly stated by any span"))
