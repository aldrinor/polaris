"""I-wire-001 W2 — post-fetch content-relevance judge (Qwen3-Reranker-0.6B + GLM escalation).

This module implements the W2 winner: after a candidate's page BODY is fetched
and BEFORE it is tier-classified, score the body's relevance to the research
question so off-topic / junk passages are DEMOTED (down-weighted) while real
evidence is retained at full weight.

§-1.3 weight-not-filter (BINDING). This is a WEIGHT, never a hard drop. Every
candidate stays in the corpus; a low-relevance passage gets a low relevance
weight + a disclosed "demoted" telemetry entry. Nothing is silently deleted —
the faithfulness engine (strict_verify / NLI / 4-role / span-grounding) remains
the ONLY hard gate and is untouched here. W2's flag + telemetry are kept DISTINCT
from the existing B4 `relevance_gate` (PG_RETRIEVAL_RELEVANCE_GATE) so the two
never conflate.

Two-stage judge (the winner spec):

  1. Qwen3-Reranker-0.6B (always-on, GPU-first). A CrossEncoder scores
     (research_question, passage) for EVERY fetched body in ONE batched
     `predict` call — one model load, GPU-resident (CPU is a DISCLOSED fallback,
     wiring_standard point 2). This is the cheap, deterministic first pass.

  2. GLM-5.2 escalation, ONLY on the reranker's AMBIGUOUS band. A passage whose
     reranker score lands between the low and high thresholds is escalated to the
     existing GLM-5.2 relevance judge (relevance_judge.py) for a three-way
     SUPPORTED / INSUFFICIENT / REFUTED label. Confident-relevant and
     confident-junk passages skip the LLM (cost + latency). The GLM escalations
     are run BOUNDED-parallel under PG_CONTENT_RELEVANCE_WORKERS (network-bound,
     so a thread pool is correct — the single CUDA reranker is NOT thread-fanned).

Order-independent: the batch is scored by idx and the result map is keyed by idx,
so concurrency never changes which weight a passage gets (reproducible — point 15).

All knobs are env (LAW VI): the flag, the worker cap, the two band thresholds,
and the reranker model id (reused from the existing Qwen3 reranker selector).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("polaris_graph.content_relevance_judge")

# Reranker score band: a RELEVANCE PROBABILITY in [0, 1] (P(yes) from the
# Qwen3-Reranker yes/no head). Below LOW => confident junk (demote, no LLM).
# Above HIGH => confident relevant (full weight, no LLM). Between => escalate to
# GLM-5.2. The LOW default is deliberately NEAR-ZERO: empirically (the banked
# content_relevance gold, scored against own-questions) junk_chrome / off_topic
# cluster at P(yes) ~0.000-0.005 while real evidence sits at median ~0.996 with a
# false-negative tail down to ~0.09. A near-zero LOW puts ONLY clear junk in the
# direct-demote bucket; real-evidence false-negatives fall into the ambiguous
# band and are RESCUED by the GLM judge (§-1.1 clinical: a mis-scored FDA
# contraindication must NOT be demoted). HIGH is moderate so genuinely topical-
# but-useless passages (P(yes) spread 0.0-0.99) reach the GLM INSUFFICIENT check.
_DEFAULT_BAND_LOW = 0.05
_DEFAULT_BAND_HIGH = 0.70
# Demoted passages keep this fraction of full weight (§-1.3: kept-at-low-weight,
# never zero — a demoted source still flows to composition at reduced weight).
_DEFAULT_DEMOTE_WEIGHT = 0.25
_DEFAULT_WORKERS = 12

# Relevance labels surfaced per passage (telemetry + the weight the loop applies).
LABEL_RELEVANT = "relevant"      # full weight
LABEL_DEMOTED = "demoted"        # off-topic / junk -> low weight (NOT dropped)
LABEL_ESCALATED_KEEP = "escalated_relevant"   # GLM said SUPPORTED
LABEL_ESCALATED_DEMOTE = "escalated_demoted"  # GLM said INSUFFICIENT/REFUTED


def content_relevance_enabled() -> bool:
    """True iff the W2 content-relevance-judge flag is ON.

    DEFAULT ON (I-deepfix-001 B1 keystone, 2026-06-28): the off-topic ~50% junk
    finding made this the single highest-leverage fix, so the proven in-tree W2
    winner now fires by default. Set ``PG_CONTENT_RELEVANCE_JUDGE=0`` (or
    off/false/no) to revert to the byte-identical pre-keystone path (the judge is
    NEVER instantiated, NO reranker/GLM model loads, NO weight applied). This is a
    §-1.3 WEIGHT (demote-not-drop), never a hard filter — faithfulness untouched.
    """
    return os.getenv("PG_CONTENT_RELEVANCE_JUDGE", "1").strip().lower() not in {
        "0", "false", "no", "off", "disabled", "",
    }


def _band() -> tuple[float, float]:
    def _f(name: str, default: float) -> float:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default
    low = _f("PG_CONTENT_RELEVANCE_BAND_LOW", _DEFAULT_BAND_LOW)
    high = _f("PG_CONTENT_RELEVANCE_BAND_HIGH", _DEFAULT_BAND_HIGH)
    if low > high:  # misconfig guard — never invert the band
        low, high = _DEFAULT_BAND_LOW, _DEFAULT_BAND_HIGH
    return low, high


def _demote_weight() -> float:
    raw = os.getenv("PG_CONTENT_RELEVANCE_DEMOTE_WEIGHT", "").strip()
    if not raw:
        return _DEFAULT_DEMOTE_WEIGHT
    try:
        w = float(raw)
    except ValueError:
        return _DEFAULT_DEMOTE_WEIGHT
    # Clamp to (0, 1]: a demoted source is KEPT at low weight, never zero-dropped.
    if w <= 0.0:
        return _DEFAULT_DEMOTE_WEIGHT
    return min(w, 1.0)


def _workers() -> int:
    try:
        return max(1, int(os.getenv("PG_CONTENT_RELEVANCE_WORKERS", str(_DEFAULT_WORKERS))))
    except ValueError:
        return _DEFAULT_WORKERS


def _passage_chars() -> int:
    """Head-window of the body fed to the reranker (LAW VI). The reranker reads a
    bounded prefix — enough to judge topicality without paying full-body cost."""
    try:
        return max(200, int(os.getenv("PG_CONTENT_RELEVANCE_PASSAGE_CHARS", "2000")))
    except ValueError:
        return 2000


def _escalation_deadline_seconds() -> float:
    """I-deepfix-001 W06 (#1344): a fallback TOTAL wall (seconds) for the GLM escalation
    pool when the caller threads NO absolute deadline. At the campaign's 25x fetch_cap
    (~1000 candidates) a mis-calibrated reranker can escalate the whole mid-band; the pool
    BLOCKS until ALL futures finish (~ceil(N/workers)*per-call), with zero deadline checks
    inside, which can exceed the retrieval wall. ``<= 0`` disables the fallback wall (the
    caller's threaded deadline still applies if given). Default 600s (generous)."""
    raw = os.getenv("PG_CONTENT_RELEVANCE_DEADLINE_S", "600").strip()
    try:
        value = float(raw)
    except ValueError:
        return 600.0
    import math as _math
    if not _math.isfinite(value) or value <= 0:
        return 0.0
    return value


@dataclass
class RelevanceVerdict:
    """Per-passage relevance outcome (a WEIGHT + a disclosed label, never a drop)."""

    idx: int
    url: str
    label: str
    weight: float          # in (0, 1]; full weight = 1.0, demoted = _demote_weight
    reranker_score: float
    escalated: bool        # whether the GLM-5.2 judge was consulted
    reason: str = ""


@dataclass
class RelevanceReport:
    """Run-manifest telemetry for the content-relevance judge (point 1 disclosure)."""

    verdicts: list[RelevanceVerdict] = field(default_factory=list)
    n_scored: int = 0
    n_demoted: int = 0
    n_escalated: int = 0
    n_relevant: int = 0
    reranker_device: str = ""        # "cuda" / "cpu" (disclosed fallback)
    used_cpu_fallback: bool = False
    band_low: float = 0.0
    band_high: float = 0.0
    # I-deepfix-001 W06-content-relevance-deadline (#1344): set True when the GLM
    # escalation deadline elapsed and the remaining ambiguous passages were emitted at
    # FULL weight (always-release, never demote-on-timeout) instead of escalated.
    escalation_wall_hit: bool = False

    def by_idx(self) -> dict[int, RelevanceVerdict]:
        return {v.idx: v for v in self.verdicts}

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_scored": self.n_scored,
            "n_relevant": self.n_relevant,
            "n_demoted": self.n_demoted,
            "n_escalated": self.n_escalated,
            "reranker_device": self.reranker_device,
            "used_cpu_fallback": self.used_cpu_fallback,
            "escalation_wall_hit": self.escalation_wall_hit,
            "band_low": self.band_low,
            "band_high": self.band_high,
            # §-1.3: list the DEMOTED urls (kept at low weight) — never a drop list.
            "demoted_urls": [
                v.url for v in self.verdicts
                if v.label in (LABEL_DEMOTED, LABEL_ESCALATED_DEMOTE)
            ],
        }


def _reranker_model_name() -> str:
    """Qwen3-Reranker-0.6B (the W2 content-relevance pick). Env-overridable.

    Distinct from PG_RERANKER_MODEL (the 4B SELECTION reranker, evidence_selector)
    so the two rerankers do not collide on one env knob."""
    return os.getenv(
        "PG_CONTENT_RELEVANCE_RERANKER_MODEL", "Qwen/Qwen3-Reranker-0.6B",
    ).strip() or "Qwen/Qwen3-Reranker-0.6B"


def score_passages(
    research_question: str,
    passages: list[tuple[int, str, str]],
    *,
    glm_judge_fn: Optional[Callable[[str, str], "tuple[str, str]"]] = None,
    reranker_predict_fn: Optional[Callable[[list[list[str]]], list[float]]] = None,
    deadline_monotonic: "float | None" = None,
) -> RelevanceReport:
    """Score (idx, url, body) passages for relevance to the research question.

    Stage 1 — Qwen3-Reranker-0.6B scores ALL passages in one batched call
    (GPU-first; CPU fallback disclosed). Stage 2 — GLM-5.2 escalation runs
    BOUNDED-parallel ONLY on the ambiguous-band passages.

    Injection seams for the §-1.4 harness (NO model spend in the canary):
      * ``reranker_predict_fn(pairs) -> scores`` mocks the CrossEncoder.
      * ``glm_judge_fn(claim, span) -> (label, reason)`` mocks the GLM judge
        (reuses relevance_judge.py's SUPPORTED/INSUFFICIENT/REFUTED taxonomy).

    Returns a RelevanceReport whose ``by_idx()`` maps each passage idx to a
    WEIGHT the caller applies. NO passage is dropped — a demoted passage carries
    a low weight, never removal (§-1.3).
    """
    low, high = _band()
    demote_w = _demote_weight()
    passage_chars = _passage_chars()
    report = RelevanceReport(band_low=low, band_high=high)
    if not passages:
        return report

    # Bounded prefix of each body (topicality, not full-body cost).
    pairs = [
        [research_question or "", (body or "")[:passage_chars]]
        for _idx, _url, body in passages
    ]

    # ── Stage 1: Qwen3-Reranker-0.6B (batched, GPU-first) ──────────────
    # The reranker returns a RELEVANCE PROBABILITY in [0, 1] per pair (the yes/no
    # token softmax — see _predict_with_qwen3_reranker), so the band thresholds
    # operate on it directly (NO extra sigmoid).
    if reranker_predict_fn is not None:
        scores = list(reranker_predict_fn(pairs))
        report.reranker_device = "injected"
    else:
        scores = _predict_with_qwen3_reranker(pairs, report)
    if len(scores) != len(passages):
        # Defensive: a misbehaving reranker must NOT silently mis-weight. Fall
        # back LOUDLY to all-relevant (full weight) — never demote on a bug.
        logger.warning(
            "[content_relevance] reranker returned %d scores for %d passages — "
            "FALLING BACK to full weight for all (no demotion on a scorer bug).",
            len(scores), len(passages),
        )
        scores = [high + 1.0] * len(passages)

    # ── Partition by band ──────────────────────────────────────────────
    ambiguous: list[int] = []   # positions into `passages` needing GLM
    for pos, (idx, url, _body) in enumerate(passages):
        s = scores[pos]
        if s >= high:
            report.verdicts.append(RelevanceVerdict(
                idx=idx, url=url, label=LABEL_RELEVANT, weight=1.0,
                reranker_score=s, escalated=False,
                reason="reranker high-confidence relevant",
            ))
        elif s < low:
            report.verdicts.append(RelevanceVerdict(
                idx=idx, url=url, label=LABEL_DEMOTED, weight=demote_w,
                reranker_score=s, escalated=False,
                reason="reranker high-confidence off-topic (demoted, NOT dropped)",
            ))
        else:
            ambiguous.append(pos)

    # ── Stage 2: GLM-5.2 escalation on the ambiguous band, bounded-parallel ──
    if ambiguous:
        # I-deepfix-001 W06 (#1344): the escalation pool is bounded by an absolute
        # deadline — the caller's threaded `deadline_monotonic` (= the remaining
        # retrieval wall) when given, else the env fallback `PG_CONTENT_RELEVANCE_
        # DEADLINE_S`. The TIGHTER (earlier) of the two wins.
        _fallback_wall = _escalation_deadline_seconds()
        _eff_deadline = deadline_monotonic
        if _fallback_wall > 0:
            _fb_instant = time.monotonic() + _fallback_wall
            _eff_deadline = (
                _fb_instant if _eff_deadline is None else min(_eff_deadline, _fb_instant)
            )
        _resolve_ambiguous(
            research_question, passages, scores, ambiguous,
            demote_w, report, glm_judge_fn, _eff_deadline,
        )

    # Finalize counts.
    report.n_scored = len(report.verdicts)
    report.n_relevant = sum(
        1 for v in report.verdicts
        if v.label in (LABEL_RELEVANT, LABEL_ESCALATED_KEEP)
    )
    report.n_demoted = sum(
        1 for v in report.verdicts
        if v.label in (LABEL_DEMOTED, LABEL_ESCALATED_DEMOTE)
    )
    report.n_escalated = sum(1 for v in report.verdicts if v.escalated)
    # Stable order by idx (order-independent result).
    report.verdicts.sort(key=lambda v: v.idx)
    logger.info(
        "[content_relevance] scored=%d relevant=%d demoted=%d escalated=%d "
        "device=%s band=[%.2f,%.2f] (demote keeps weight=%.2f; NO drop)",
        report.n_scored, report.n_relevant, report.n_demoted, report.n_escalated,
        report.reranker_device, low, high, demote_w,
    )
    return report


# Qwen3-Reranker is a CAUSAL-LM reranker (NOT a sentence-transformers
# CrossEncoder — that loader attaches a RANDOM, untrained sequence-classification
# head and emits noise). The documented scoring path (model card) prompts the LM
# with a yes/no judge template and reads the softmax of the "yes"/"no" token
# logits at the last position. The official prompt template is fixed by the model.
_QWEN3_RERANK_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based "
    "on the Query and the Instruct provided. Note that the answer can only be "
    '"yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
_QWEN3_RERANK_SUFFIX = (
    "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
)
_QWEN3_RERANK_INSTRUCTION = (
    "Given a research question, judge whether the document passage is RELEVANT "
    "evidence that helps answer it."
)

# Process-lifetime cache of the loaded reranker (model, tokenizer, ids, device).
# Loading an LM per call would be ruinous; the handle is loaded once on first ON
# use and reused. None until first load; a sentinel string on a hard failure.
_QWEN3_RERANKER_HANDLE: Any = None


def _format_qwen3_pair(question: str, passage: str) -> str:
    return (
        f"<Instruct>: {_QWEN3_RERANK_INSTRUCTION}\n"
        f"<Query>: {question}\n<Document>: {passage}"
    )


def _load_qwen3_reranker(report: RelevanceReport) -> Any:
    """Load Qwen3-Reranker-0.6B as a causal LM (cached). GPU-first; CPU is a
    DISCLOSED fallback. FAIL-LOUD random-head canary: if transformers attaches a
    randomly-initialized classification head (the CrossEncoder failure mode), we
    are NOT using the documented path — raise rather than emit noise scores."""
    global _QWEN3_RERANKER_HANDLE
    if _QWEN3_RERANKER_HANDLE is not None:
        return _QWEN3_RERANKER_HANDLE

    import warnings

    import torch  # noqa: PLC0415
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415

    model_name = _reranker_model_name()
    device = os.getenv("PG_CONTENT_RELEVANCE_DEVICE", "").strip()
    if not device:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        report.used_cpu_fallback = True
        logger.warning(
            "[content_relevance] Qwen3-Reranker-0.6B running on CPU (DISCLOSED "
            "fallback — no CUDA). GPU is the production path (wiring_standard pt 2).",
        )

    # I-deepfix-001 FIX-1 (keystone): free any cached-but-unallocated CUDA blocks
    # (e.g. the co-resident Qwen3-Embedding-8B's embed-batch cache) on this card
    # BEFORE loading the W5 reranker, so its weights + scoring activations fit
    # alongside the 14.4GB resident embedder on cuda:0. cuda-only; a no-op on CPU.
    # Faithfulness-neutral — pure GPU-memory mechanics, no model/score change.
    if device.startswith("cuda"):
        try:
            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — best-effort cache free, never fatal
            pass

    tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
    # Random-head canary: AutoModelForCausalLM keeps the pretrained LM head, so no
    # "newly initialized" score.weight warning should fire. We surface any such
    # warning loudly (the documented path uses the LM head, not a new cls head).
    with warnings.catch_warnings(record=True) as _w:
        warnings.simplefilter("always")
        model = AutoModelForCausalLM.from_pretrained(model_name).eval().to(device)
    for _warn in _w:
        if "newly initialized" in str(_warn.message):
            raise RuntimeError(
                "Qwen3-Reranker loaded with a randomly-initialized head "
                f"({_warn.message}) — the documented causal-LM yes/no scoring "
                "path is NOT active; refusing to emit noise scores."
            )
    token_true_id = tokenizer.convert_tokens_to_ids("yes")
    token_false_id = tokenizer.convert_tokens_to_ids("no")
    prefix_tokens = tokenizer.encode(_QWEN3_RERANK_PREFIX, add_special_tokens=False)
    suffix_tokens = tokenizer.encode(_QWEN3_RERANK_SUFFIX, add_special_tokens=False)
    report.reranker_device = device
    _QWEN3_RERANKER_HANDLE = {
        "model": model, "tokenizer": tokenizer, "device": device,
        "true_id": token_true_id, "false_id": token_false_id,
        "prefix_tokens": prefix_tokens, "suffix_tokens": suffix_tokens,
    }
    return _QWEN3_RERANKER_HANDLE


def _predict_with_qwen3_reranker(
    pairs: list[list[str]], report: RelevanceReport,
) -> list[float]:
    """Score (question, passage) pairs with Qwen3-Reranker-0.6B via the documented
    causal-LM yes/no-token softmax. Returns a RELEVANCE PROBABILITY in [0, 1] per
    pair (P(yes)). Batched in one forward pass (one model load), GPU-first.

    On a hard import/load/scoring failure, fall back LOUDLY to all-relevant (never
    demote on a bug) — returns an empty list so the caller's length-guard fills
    full weight. This is a DISCLOSED degrade (point 1), not a silent one.
    """
    try:
        import torch  # noqa: PLC0415

        handle = _load_qwen3_reranker(report)
        model = handle["model"]
        tokenizer = handle["tokenizer"]
        prefix_tokens = handle["prefix_tokens"]
        suffix_tokens = handle["suffix_tokens"]
        max_length = max(512, int(os.getenv("PG_CONTENT_RELEVANCE_MAX_LENGTH", "4096")))
        # I-deepfix-001 FIX-1 (keystone): score in CHUNKS so the per-forward
        # ``model(**inputs).logits`` tensor ([chunk x seq x ~152k-vocab]) stays
        # small enough to fit alongside the co-resident Qwen3-Embedding-8B on
        # cuda:0 (the W5-dark → CRAG-non-convergence keystone bug). DEFAULT 0
        # (PG_CONTENT_RELEVANCE_SCORE_CHUNK unset) => ONE pass over all pairs =>
        # BYTE-IDENTICAL to prior behavior. >0 => score in groups of that size.
        # Parse-guarded (Codex iter1 P2): garbage/negative => 0 (one-pass), never
        # a ValueError leaking into the scorer's broad ``except`` (full-weight).
        try:
            _score_chunk = int(os.getenv("PG_CONTENT_RELEVANCE_SCORE_CHUNK", "0") or "0")
        except ValueError:
            _score_chunk = 0
        if _score_chunk < 0:
            _score_chunk = 0

        # Tokenize ALL pairs ONCE, then pad EVERY chunk to the SAME global-longest
        # length the one-pass path pads to. Codex iter1 P1-2: the reranker is a
        # LEFT-padded decoder-only causal LM, so the pad amount shifts RoPE position
        # ids; padding each chunk to its own LOCAL longest would perturb per-pair
        # scores across groupings. Padding every chunk to the GLOBAL longest makes
        # the chunked scores IDENTICAL to one-pass AND chunk-size-invariant — so
        # relevance stays a stable WEIGHT (faithfulness-neutral). chunk==0 => a
        # single group whose pad length == the one-pass batch-longest == byte-id.
        formatted_all = [_format_qwen3_pair(q, d) for q, d in pairs]
        enc_all = tokenizer(
            formatted_all, padding=False, truncation="longest_first",
            return_attention_mask=False,
            max_length=max_length - len(prefix_tokens) - len(suffix_tokens),
        )
        ids_all = [
            prefix_tokens + enc_all["input_ids"][idx] + suffix_tokens
            for idx in range(len(enc_all["input_ids"]))
        ]
        global_len = max((len(x) for x in ids_all), default=0)

        if _score_chunk == 0 or _score_chunk >= len(ids_all):
            index_groups = [list(range(len(ids_all)))]
        else:
            index_groups = [
                list(range(i, min(i + _score_chunk, len(ids_all))))
                for i in range(0, len(ids_all), _score_chunk)
            ]

        all_scores: list[float] = []
        for _grp in index_groups:
            inputs = tokenizer.pad(
                {"input_ids": [ids_all[i] for i in _grp]},
                padding="max_length", max_length=global_len, return_tensors="pt",
            )
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
            with torch.no_grad():
                logits = model(**inputs).logits[:, -1, :]
                true_v = logits[:, handle["true_id"]]
                false_v = logits[:, handle["false_id"]]
                stacked = torch.stack([false_v, true_v], dim=1)
                probs = torch.nn.functional.log_softmax(stacked, dim=1)
                scores = probs[:, 1].exp().tolist()
            all_scores.extend(float(s) for s in scores)
            # Codex iter1 P1-1: DROP refs to the large CUDA tensors BEFORE
            # empty_cache() so the [chunk x seq x vocab] block is actually released
            # before the next forward (otherwise empty_cache is a no-op — they are
            # still live — and the next allocation can overlap and OOM).
            del logits, true_v, false_v, stacked, probs, inputs
            if len(index_groups) > 1 and str(model.device).startswith("cuda"):
                try:
                    torch.cuda.empty_cache()
                except Exception:  # noqa: BLE001 — best-effort, never fatal
                    pass
        return all_scores
    except Exception as exc:
        logger.warning(
            "[content_relevance] Qwen3-Reranker load/scoring failed (%s) — FALLING "
            "BACK LOUDLY to full weight for all passages (no demotion on a scorer "
            "failure; disclosed degrade, not silent).",
            str(exc)[:200],
        )
        report.reranker_device = "unavailable"
        return []  # caller's length-guard => all full weight


def _resolve_ambiguous(
    research_question: str,
    passages: list[tuple[int, str, str]],
    scores: list[float],
    ambiguous: list[int],
    demote_w: float,
    report: RelevanceReport,
    glm_judge_fn: Optional[Callable[[str, str], "tuple[str, str]"]],
    deadline_monotonic: "float | None" = None,
) -> None:
    """GLM-5.2 escalation for the ambiguous-band passages, bounded-parallel.

    Network-bound, so a ThreadPoolExecutor(PG_CONTENT_RELEVANCE_WORKERS) is the
    correct fan-out (the single CUDA reranker is NOT thread-fanned). Each result
    is keyed by idx, so concurrency never changes the weight a passage gets.
    A GLM transport/parse error => keep the passage RELEVANT at full weight
    (always-release: a runtime error never demotes — relevance_judge.py contract).
    """
    from concurrent.futures import (  # noqa: PLC0415 — lazy by design
        FIRST_COMPLETED,
        ThreadPoolExecutor,
        wait as futures_wait,
    )

    # Resolve the GLM judge callable (real OpenRouter GLM-5.2 unless injected).
    judge_fn = glm_judge_fn
    if judge_fn is None:
        try:
            # W2 uses the question<->passage CONTENT-RELEVANCE prompt (NOT the
            # citation-claim #1280 prompt), gated SOLELY by PG_CONTENT_RELEVANCE_
            # JUDGE — decoupled from PG_RELEVANCE_GATE. Reuses the tested transport.
            from src.polaris_graph.generator.relevance_judge import (
                make_content_relevance_judge,
            )

            judge_fn = make_content_relevance_judge().judge
        except Exception as exc:
            logger.warning(
                "[content_relevance] GLM escalation judge unavailable (%s) — "
                "ambiguous-band passages KEPT at full weight (always-release).",
                str(exc)[:160],
            )
            judge_fn = None

    def _one(pos: int) -> RelevanceVerdict:
        idx, url, body = passages[pos]
        s = scores[pos]
        if judge_fn is None:
            return RelevanceVerdict(
                idx=idx, url=url, label=LABEL_ESCALATED_KEEP, weight=1.0,
                reranker_score=s, escalated=True,
                reason="GLM judge unavailable — kept (always-release)",
            )
        try:
            from src.polaris_graph.generator.relevance_judge import (
                LABEL_SUPPORTED,
            )

            label, reason = judge_fn(research_question, (body or "")[:_passage_chars()])
            if label == LABEL_SUPPORTED:
                return RelevanceVerdict(
                    idx=idx, url=url, label=LABEL_ESCALATED_KEEP, weight=1.0,
                    reranker_score=s, escalated=True,
                    reason=f"GLM SUPPORTED: {reason[:120]}",
                )
            # INSUFFICIENT / REFUTED -> demote (kept at low weight, NOT dropped).
            return RelevanceVerdict(
                idx=idx, url=url, label=LABEL_ESCALATED_DEMOTE, weight=demote_w,
                reranker_score=s, escalated=True,
                reason=f"GLM {label}: {reason[:120]} (demoted, NOT dropped)",
            )
        except Exception as exc:
            return RelevanceVerdict(
                idx=idx, url=url, label=LABEL_ESCALATED_KEEP, weight=1.0,
                reranker_score=s, escalated=True,
                reason=f"GLM error {str(exc)[:80]} — kept (always-release)",
            )

    def _full_weight_keep(pos: int) -> RelevanceVerdict:
        """I-deepfix-001 W06 (#1344): a passage NOT escalated because the deadline
        elapsed is KEPT at FULL weight (always-release, never demote-on-timeout). §-1.3:
        the wall NEVER demotes/drops a source — it just skips the escalation WEIGHT."""
        idx, url, _body = passages[pos]
        return RelevanceVerdict(
            idx=idx, url=url, label=LABEL_ESCALATED_KEEP, weight=1.0,
            reranker_score=scores[pos], escalated=True,
            reason="escalation wall hit — kept at full weight (always-release)",
        )

    workers = min(_workers(), max(1, len(ambiguous)))
    # I-deepfix-001 W06 (#1344): submit each ambiguous future and gather with the absolute
    # deadline. When the wall passes, STOP escalating the remainder and emit them at FULL
    # weight (always-release). pool.map BLOCKED until ALL futures finished with no deadline
    # check — at ~1000 candidates that can exceed the retrieval wall. The pool is managed
    # MANUALLY (NOT `with`): a `with ThreadPoolExecutor` __exit__ calls shutdown(wait=True),
    # which BLOCKS until the wedged worker finishes — defeating the wall entirely (the exact
    # seam-worker class). shutdown(wait=False, cancel_futures=True) returns promptly.
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        future_to_pos = {pool.submit(_one, pos): pos for pos in ambiguous}
        pending = set(future_to_pos)
        while pending:
            _remaining = (
                None if deadline_monotonic is None
                else max(0.0, deadline_monotonic - time.monotonic())
            )
            if _remaining is not None and _remaining <= 0:
                break
            done, pending = futures_wait(
                pending, timeout=_remaining, return_when=FIRST_COMPLETED,
            )
            if not done:
                break  # the wall elapsed mid-flight
            for fut in done:
                report.verdicts.append(fut.result())
        if pending:
            # The deadline elapsed: emit the un-escalated remainder at FULL weight
            # (never block on the still-running futures; SS-1.3 keep-all).
            report.escalation_wall_hit = True
            for fut in list(pending):
                _pos = future_to_pos[fut]
                if fut.done():
                    try:
                        report.verdicts.append(fut.result())
                        continue
                    except Exception:  # noqa: BLE001 — a late failure falls through to keep
                        pass
                report.verdicts.append(_full_weight_keep(_pos))
            logger.warning(
                "[content_relevance] W06: GLM escalation wall hit — %d ambiguous "
                "passage(s) kept at FULL weight (always-release, no demote/drop, §-1.3).",
                len(pending),
            )
    finally:
        # NON-BLOCKING teardown so a wedged GLM future cannot delay the return (the wall
        # would be cosmetic if __exit__ waited on it). The orphaned thread exits on its own
        # per-call timeout. Mirrors the seam-worker non-blocking shutdown.
        pool.shutdown(wait=False, cancel_futures=True)
