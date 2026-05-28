"""Pure scoring/adapter logic for the POLARIS-vs-MedHallu verification-layer benchmark.

I-safety-002a (#924). Codex-designed run (see .codex/I-safety-002a/codex_medhallu_design.txt):
map MedHallu onto POLARIS's ENTAILMENT-verification layer (NOT strict_verify, which
needs provenance tokens and cannot run on raw MedHallu answers). Per row -> two
candidates (Ground Truth = faithful, Hallucinated = hallucinated); source = Question +
Knowledge ONLY (never the candidate answers); atomize the answer; verify each claim by
entailment against the Knowledge; aggregate: answer is hallucinated iff ANY substantive
claim is unsupported. Positive class = hallucinated.

This module holds ONLY pure functions (no model, no I/O) so the scorer can be validated
on fixtures BEFORE any model run, per the Codex-APPROVE'd plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Codex: pin the shipped direct-verifier threshold; the headline uses the verifier's
# internal threshold via PG_FAITHFULNESS_NLI_THRESHOLD. This mirror locks the boundary.
DEFAULT_NLI_FAITH_THRESHOLD = 0.65


class StrictVerifyMisuseError(RuntimeError):
    """Raised if anything tries to score raw MedHallu answers with strict_verify.

    strict_verify requires POLARIS provenance tokens ([#ev:id:start-end]); raw MedHallu
    answers have none, so strict_verify would return no_provenance_token for every row and
    produce a junk 0%-specificity "everything is hallucinated" result (Codex ruling).
    """


@dataclass
class Candidate:
    """One scored unit: a candidate answer with its mechanical gold label."""

    row_id: str
    split: str
    answer_text: str
    gold_hallucinated: bool
    candidate_kind: str  # "ground_truth" | "hallucinated"


def pair_row(row: dict, split: str) -> list[Candidate]:
    """Row -> exactly two candidates: Ground Truth (faithful) + Hallucinated (positive).

    Fixture 1 (pairing) + the per-row clustering unit for bootstrap CIs.
    """
    row_id = str(row["row_id"])
    gt = (row.get("ground_truth") or "").strip()
    hallu = (row.get("hallucinated_answer") or "").strip()
    return [
        Candidate(row_id, split, gt, gold_hallucinated=False, candidate_kind="ground_truth"),
        Candidate(row_id, split, hallu, gold_hallucinated=True, candidate_kind="hallucinated"),
    ]


def build_source_text(question: str, knowledge: str) -> str:
    """Verifier source = Question + Knowledge ONLY.

    Codex: the candidate answer (esp. Ground Truth) MUST NOT enter the evidence, or the
    negative label leaks. Fixture 2 (source isolation) asserts no candidate text leaks here.
    """
    return f"Question: {question.strip()}\n\nKnowledge: {knowledge.strip()}"


def assert_source_isolated(source_text: str, candidate: Candidate) -> None:
    """Fail-closed if a candidate answer leaked into the verifier source (Codex fixture 2)."""
    ans = candidate.answer_text.strip()
    if ans and ans in source_text:
        raise ValueError(
            f"label leak: candidate ({candidate.candidate_kind}) answer text found in "
            f"verifier source for row {candidate.row_id}"
        )


def build_evidence_object(claim: str, question: str, knowledge: str, candidate: Candidate) -> dict:
    """Build the single evidence dict fed to verify_evidence_nli (Codex spec).

    source content = Question + Knowledge; statement = the claim under test. Guards source
    isolation. research_query is left "" by the caller to disable off-topic keyword overrides.
    """
    source_text = build_source_text(question, knowledge)
    assert_source_isolated(source_text, candidate)
    source_url = f"medhallu:{candidate.split}:{candidate.row_id}:{candidate.candidate_kind}"
    return {
        "statement": claim,
        "source_url": source_url,
        "source_title": question.strip(),
        "direct_quote": knowledge.strip(),
    }


def claim_is_faithful(prob: float, label: int, threshold: float = DEFAULT_NLI_FAITH_THRESHOLD) -> bool:
    """Mirror of the verifier's rule: faithful iff entailed (label==1) AND prob >= threshold.

    Fixture 5 (threshold boundary): 0.65 passes with >=, 0.6499 fails.
    """
    return bool(label == 1) and prob >= threshold


def aggregate_answer_verdict(claim_faithful_flags: list[bool]) -> str:
    """Answer-level verdict from per-claim faithfulness (Codex aggregation rule).

    - no substantive claims -> "invalid" (report separately; do not silently drop).
    - all claims faithful    -> "faithful".
    - any claim unsupported   -> "hallucinated".
    Fixture 4 (aggregation).
    """
    if not claim_faithful_flags:
        return "invalid"
    return "faithful" if all(claim_faithful_flags) else "hallucinated"


@dataclass
class Confusion:
    """Positive class = hallucinated."""

    tp: int = 0  # predicted hallucinated, gold hallucinated
    fp: int = 0  # predicted hallucinated, gold faithful
    fn: int = 0  # predicted faithful, gold hallucinated
    tn: int = 0  # predicted faithful, gold faithful
    invalid: int = 0  # unparseable/empty answers (reported, not scored)


def add_prediction(conf: Confusion, predicted_verdict: str, gold_hallucinated: bool) -> None:
    """Fold one candidate prediction into the confusion matrix. Invalids counted aside."""
    if predicted_verdict == "invalid":
        conf.invalid += 1
        return
    pred_hallu = predicted_verdict == "hallucinated"
    if pred_hallu and gold_hallucinated:
        conf.tp += 1
    elif pred_hallu and not gold_hallucinated:
        conf.fp += 1
    elif (not pred_hallu) and gold_hallucinated:
        conf.fn += 1
    else:
        conf.tn += 1


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def metrics(conf: Confusion) -> dict:
    """F1/precision/recall/specificity/balanced-accuracy. Positive class = hallucinated.

    Fixture 6 (confusion -> known F1).
    """
    precision = _safe_div(conf.tp, conf.tp + conf.fp)
    recall = _safe_div(conf.tp, conf.tp + conf.fn)  # = sensitivity
    specificity = _safe_div(conf.tn, conf.tn + conf.fp)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    balanced_accuracy = (recall + specificity) / 2
    return {
        "f1": f1,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "balanced_accuracy": balanced_accuracy,
        "tp": conf.tp,
        "fp": conf.fp,
        "fn": conf.fn,
        "tn": conf.tn,
        "invalid": conf.invalid,
    }


def expected_candidate_count(n_labeled: int, n_artificial: int) -> dict:
    """Pairing-count math: each row -> 2 candidates (Codex fixture 7)."""
    return {
        "pqa_labeled": n_labeled * 2,
        "pqa_artificial": n_artificial * 2,
        "total": (n_labeled + n_artificial) * 2,
    }


@dataclass
class RunGuards:
    """Run-level guards that must hold for the headline number to be valid (Codex)."""

    nli_model_available: bool = True
    llm_fallback_used: bool = False
    negative_control: bool = False
    notes: list[str] = field(default_factory=list)

    def assert_headline_valid(self) -> None:
        """Headline run aborts if the NLI model is unavailable (Codex fixture 8: no silent
        fallback) or if it is a negative-control run masquerading as the headline."""
        if not self.nli_model_available:
            raise RuntimeError(
                "NLI model unavailable: verify_evidence_nli returned [] — abort the headline "
                "run, do NOT silently fall back to an LLM (Codex contamination control)."
            )
        if self.negative_control:
            raise RuntimeError(
                "negative-control run cannot be recorded as the headline artifact "
                "(Codex fixture 9)."
            )
