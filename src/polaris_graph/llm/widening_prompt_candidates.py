"""I-faith-006 (#1180) — candidate entailment-judge prompts that teach specific->general WIDENING.

F02 (BB5-F02, clinical overgeneralization): the real entailment judge ENTAILS a drb_76 claim that
WIDENS a specific strain/population to a broad class ("S. boulardii not recommended in
immunocompromised" -> "current evidence advises against routine probiotic use"). Enforcement cannot
fix an LLM-behavior gap; per operator policy the fix is a WIDENING-AWARE judge prompt, EMPIRICALLY
BAKED OFF against a labeled set (`tests/fixtures/widening_labeled_set.json`) and picked by
precision/recall — never a hand-chosen prompt.

This module holds ONLY the candidate prompt VARIANTS (pure strings) + the pure scoring helpers. The
BASELINE prompt stays in `entailment_judge._ENTAILMENT_PROMPT` (this module never imports it, to
avoid a cycle); `entailment_judge._select_entailment_prompt()` returns the baseline by default
(``PG_ENTAILMENT_PROMPT_VARIANT`` unset/"baseline" -> byte-identical) and a candidate only when
explicitly selected. The bakeoff (`scripts/dr_benchmark/widening_prompt_bakeoff.py`) scores every
variant against the labeled set with the REAL judge (spend-gated) and the winning variant is wired by
setting the env in the run slate.

Each variant MUST keep the same ``{span}`` / ``{sentence}`` format fields and the STRICT-JSON output
contract so it is a drop-in replacement.
"""

from __future__ import annotations

# The shared widening NEUTRAL exemplars, phrased differently per candidate. The directional rule is
# the same: when the SENTENCE generalizes a SPECIFIC entity / strain / drug member / subgroup /
# population / mechanism / setting in the SPAN to a BROADER class, that is specific->general = NEUTRAL
# (NOT entailed). The opposite direction (span general, sentence a faithful subset) stays ENTAILED.

# Candidate A — terse rule addition + one strain exemplar.
_WIDEN_A = """You are a strict entailment judge. You will be given a SPAN of source text and a SENTENCE that cites that span. Decide whether the SPAN entails the SENTENCE.

Rules:
- ENTAILED: every factual assertion in the SENTENCE is supported by the SPAN. Conservative paraphrase is allowed, and a faithful SUBSET of the span (general span -> narrower true sentence, dropping a CI bound) is still ENTAILED.
- NEUTRAL: the SENTENCE introduces a fact, entity, mechanism, or specificity NOT present in the SPAN (e.g. SPAN says "GLP-1 RAs", SENTENCE says "semaglutide"; SPAN says "adipocyte metabolism", SENTENCE adds "lipid metabolism"). ALSO NEUTRAL when the SENTENCE GENERALIZES a SPECIFIC entity/strain/drug/subgroup/population/setting in the SPAN to a BROADER class (specific->general is NOT entailed: SPAN "S. boulardii not recommended in immunocompromised", SENTENCE "probiotics are not recommended" is NEUTRAL).
- CONTRADICTED: the SENTENCE asserts something the SPAN explicitly disagrees with.

Return STRICT JSON only, no prose:
{{"verdict": "ENTAILED" | "NEUTRAL" | "CONTRADICTED", "reason": "<one short sentence>"}}

SPAN:
{span}

SENTENCE:
{sentence}

JSON:"""

# Candidate B — explicit "direction test" framing + two exemplars (strain + subgroup).
_WIDEN_B = """You are a strict entailment judge. You will be given a SPAN of source text and a SENTENCE that cites that span. Decide whether the SPAN entails the SENTENCE.

First apply the SCOPE-DIRECTION test: if the SENTENCE is BROADER than the SPAN — generalizing a specific entity, drug, strain, subgroup, population, mechanism, or study setting to a wider class — the SPAN does NOT entail it. Only a sentence whose scope is EQUAL TO or NARROWER THAN the span (and otherwise faithful) can be ENTAILED.

Rules:
- ENTAILED: every assertion in the SENTENCE is supported by the SPAN and the SENTENCE is no broader than the SPAN. Conservative paraphrase and faithful subsets are ENTAILED.
- NEUTRAL: the SENTENCE adds a fact/entity/mechanism/specificity absent from the SPAN, OR widens the span's specific scope to a broader class. Examples: SPAN "GLP-1 RAs", SENTENCE "semaglutide" (NEUTRAL); SPAN "S. boulardii not recommended in immunocompromised patients", SENTENCE "probiotics are not recommended" (NEUTRAL, strain+population widened); SPAN "in adults 65+, hospitalization fell 40%", SENTENCE "in adults, hospitalization fell 40%" (NEUTRAL, subgroup widened).
- CONTRADICTED: the SENTENCE asserts something the SPAN explicitly disagrees with.

Return STRICT JSON only, no prose:
{{"verdict": "ENTAILED" | "NEUTRAL" | "CONTRADICTED", "reason": "<one short sentence>"}}

SPAN:
{span}

SENTENCE:
{sentence}

JSON:"""

# Candidate C — checklist framing to reduce false-drops on legitimate paraphrase.
_WIDEN_C = """You are a strict entailment judge. You will be given a SPAN of source text and a SENTENCE that cites that span. Decide whether the SPAN entails the SENTENCE.

Decide in two steps:
1. SCOPE: Is the SENTENCE's claimed entity/drug/strain/subgroup/population/mechanism/setting the SAME AS or NARROWER THAN the SPAN's? If the SENTENCE is BROADER (generalizes the span's specific item to a wider class), the answer is NEUTRAL regardless of how similar the wording is.
2. SUPPORT: If scope is OK, is every factual assertion in the SENTENCE supported by the SPAN? If yes -> ENTAILED; if it adds an unsupported fact/specificity -> NEUTRAL; if it conflicts -> CONTRADICTED.

Conservative paraphrase, voice changes, and faithful SUBSETS of the span (e.g. dropping a CI bound, same scope) are ENTAILED. Do NOT mark a same-scope faithful paraphrase NEUTRAL.

Examples of widening (NEUTRAL): SPAN "S. boulardii not recommended in immunocompromised" -> SENTENCE "probiotics are not recommended"; SPAN "GLP-1 RAs reduced HbA1c" -> SENTENCE "semaglutide reduced HbA1c"; SPAN "approved for moderate-to-severe plaque psoriasis" -> SENTENCE "effective for psoriasis".

Return STRICT JSON only, no prose:
{{"verdict": "ENTAILED" | "NEUTRAL" | "CONTRADICTED", "reason": "<one short sentence>"}}

SPAN:
{span}

SENTENCE:
{sentence}

JSON:"""


# Variant registry. "baseline" is intentionally ABSENT here — the selector returns the canonical
# `entailment_judge._ENTAILMENT_PROMPT` for baseline so it is byte-identical and there is one source
# of truth for the current prompt.
WIDENING_VARIANTS: dict[str, str] = {
    "widen_a": _WIDEN_A,
    "widen_b": _WIDEN_B,
    "widen_c": _WIDEN_C,
}

_VALID_VERDICTS = ("ENTAILED", "NEUTRAL", "CONTRADICTED")


def score_predictions(rows: list[dict], predictions: list[str]) -> dict:
    """Pure scorer for a candidate's predictions over the labeled set.

    ``rows`` are the labeled triples (each with a ``gold`` verdict + ``category``); ``predictions``
    are the candidate's verdicts in the same order. Returns the confusion matrix plus the two binding
    metrics: ``widening_neutral_recall`` (recall on gold=NEUTRAL widening rows — the fix target) and
    ``entailed_precision`` (fraction of gold=ENTAILED rows kept ENTAILED — the no-false-drop guard).
    No LLM, no I/O.
    """
    if len(rows) != len(predictions):
        raise ValueError("rows and predictions length mismatch")
    confusion: dict[tuple[str, str], int] = {}
    gold_neutral = pred_neutral_on_gold_neutral = 0
    gold_entailed = pred_entailed_on_gold_entailed = 0
    for row, pred in zip(rows, predictions):
        gold = str(row.get("gold", "")).upper()
        pred = str(pred).upper()
        confusion[(gold, pred)] = confusion.get((gold, pred), 0) + 1
        if gold == "NEUTRAL":
            gold_neutral += 1
            if pred == "NEUTRAL":
                pred_neutral_on_gold_neutral += 1
        elif gold == "ENTAILED":
            gold_entailed += 1
            if pred == "ENTAILED":
                pred_entailed_on_gold_entailed += 1
    widening_neutral_recall = (
        pred_neutral_on_gold_neutral / gold_neutral if gold_neutral else 0.0
    )
    entailed_precision = (
        pred_entailed_on_gold_entailed / gold_entailed if gold_entailed else 0.0
    )
    return {
        "confusion": {f"{g}->{p}": n for (g, p), n in sorted(confusion.items())},
        "gold_neutral": gold_neutral,
        "gold_entailed": gold_entailed,
        "widening_neutral_recall": round(widening_neutral_recall, 4),
        "entailed_precision": round(entailed_precision, 4),
    }


def pick_winner(scores_by_variant: dict[str, dict], *, min_entailed_precision: float = 0.95) -> str:
    """Select the variant with the highest ``widening_neutral_recall`` subject to
    ``entailed_precision >= min_entailed_precision`` (no faithfulness regression on legitimate
    support). Ties break toward higher entailed_precision then variant name. Returns the variant key,
    or "baseline" if NO candidate clears the precision floor (fail-safe: do not regress)."""
    eligible = [
        (name, s)
        for name, s in scores_by_variant.items()
        if s.get("entailed_precision", 0.0) >= min_entailed_precision
    ]
    if not eligible:
        return "baseline"
    eligible.sort(
        key=lambda kv: (
            kv[1].get("widening_neutral_recall", 0.0),
            kv[1].get("entailed_precision", 0.0),
            kv[0],
        ),
        reverse=True,
    )
    return eligible[0][0]
