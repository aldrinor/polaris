"""Phase 0b (#984, gap #18) RE-DIAGNOSIS harness — part 2.

Probes the entailment-NEUTRAL local-window rescue path for NON-NUMERIC
reasoning prose, and the decimal regimes, to nail down whether a grounded
qualitative reasoning sentence can ever survive a NEUTRAL judge verdict.
"""
import os

os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
os.environ.pop("PG_PROVENANCE_MIN_CONTENT_OVERLAP", None)

from src.polaris_graph.clinical_generator import strict_verify as csv  # noqa: E402
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    verify_sentence_provenance,
)


class StubJudge:
    def __init__(self, force=None):
        self.calls = []
        self.force = force

    def judge(self, sentence, span):
        self.calls.append({"sentence": sentence, "span": span})
        if self.force is not None:
            return self.force
        return ("NEUTRAL", "default neutral")


def run_case(name, sentence, pool, *, force_judge=None, require_number_match=True):
    stub = StubJudge(force=force_judge)
    csv._get_judge = lambda: stub
    csv._JUDGE_SINGLETON = stub
    csv._record_judge_outcome = lambda v, r: None
    res = verify_sentence_provenance(sentence, pool,
                                     require_number_match=require_number_match)
    print(f"\n=== CASE: {name} ===")
    print(f"  sentence: {sentence!r}")
    print(f"  is_verified: {res.is_verified}")
    print(f"  failure_reasons: {res.failure_reasons}")
    print(f"  judge_calls: {len(stub.calls)}")
    return res


# Two spans whose content words DO overlap the reasoning sentence (so it
# clears the >=2 content-word floor), forcing the flow to reach entailment.
SPAN_A = ("The carbon levy reduced industrial emissions across the province "
          "over the four-year window.")
SPAN_B = ("The provincial electricity grid relies on hydro generation, "
          "producing low-carbon power.")
POOL = {
    "ev_a": {"direct_quote": SPAN_A, "title": "Levy report"},
    "ev_b": {"direct_quote": SPAN_B, "title": "Grid factsheet"},
}


def tok(ev, s, e):
    return f"[#ev:{ev}:{s}-{e}]"


if __name__ == "__main__":
    fa = tok("ev_a", 0, len(SPAN_A))
    fb = tok("ev_b", 0, len(SPAN_B))

    # NON-NUMERIC qualitative reasoning sentence, good overlap (emissions,
    # provincial, hydro, generation, low-carbon...), judge returns NEUTRAL.
    # Expectation per code: sentence_dec_local is empty -> local-window loop
    # `continue`s -> local_window_text None -> fail closed at line 1284.
    s_qual = ("The emissions decline and the provincial hydro generation mix "
              f"together indicate a low-carbon trajectory {fa}{fb}.")
    run_case("nonnumeric_NEUTRAL_no_rescue", s_qual, POOL,
             force_judge=("NEUTRAL", "synthesis not directly stated"))

    # Same sentence, judge ENTAILED on the union: passes (control).
    run_case("nonnumeric_ENTAILED_control", s_qual, POOL,
             force_judge=("ENTAILED", "union supports"))

    # Judge fails OPEN on a non-numeric reasoning sentence: ENTAILED+judge_error.
    run_case("nonnumeric_judge_fails_open", s_qual, POOL,
             force_judge=("ENTAILED", "judge_error: JSONDecodeError"))
