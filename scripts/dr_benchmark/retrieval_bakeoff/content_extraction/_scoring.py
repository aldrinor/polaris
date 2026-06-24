"""Shared scoring + faithfulness primitives for the content_extraction bake-off.

Two scorer paths kept strictly separate (advisor pt 3):

  * SCORER-MATH canary path -- a pure-Python, tokenizer-agnostic ROUGE-N used by
    GATE-0's gold-in->~1.0 / junk-in->~0 sanity check and by the OFFLINE smoke.
    It needs NO network, NO jieba, NO model: it must run anywhere.

  * PUBLISHED-NUMBER anchor path -- the WebMainBench OFFICIAL scorer
    (`eval_baselines.py`, jieba-tokenized ROUGE-N N=5) from the third-party
    `opendatalab/MinerU-HTML` repo. It is detect-or-fallback: used ONLY when the
    cloned repo is present; otherwise the documented blind re-derivation fires
    and is FLAGGED (never silently substituted, never circular).

Plus the layer-specific FAITHFULNESS check: every content-of-record extractor
output span must be a verbatim substring of the fetched page's VISIBLE text
(advisor pt 2 -- markdown syntax stripped, whitespace normalized, checked at
content-span / table-cell granularity so extractive tools are not false-flagged
and a paraphrasing/generative path IS flagged). This is harness-internal; it
never invokes or relaxes the faithfulness engine (strict_verify / NLI / 4-role /
provenance) -- those are not in this layer's data path at all.
"""

from __future__ import annotations

import html as _html
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from typing import Iterable

# ---------------------------------------------------------------------------
# Tunables (LAW VI: env-overridable, no magic numbers buried in logic).
# ---------------------------------------------------------------------------

# Default n for the pure-Python scorer-math canary. The OFFICIAL anchor uses
# N=5 jieba (the paper's locked config); the canary is tokenizer-agnostic and
# small-N so it is meaningful on short synthetic fixtures.
SCORER_CANARY_ROUGE_N = int(os.getenv("PG_CE_BAKEOFF_CANARY_ROUGE_N", "2"))

# The OFFICIAL WebMainBench config (locked by the Dripper paper, arXiv 2511.23119).
OFFICIAL_ROUGE_N = int(os.getenv("PG_CE_BAKEOFF_OFFICIAL_ROUGE_N", "5"))
OFFICIAL_TOKENIZER = os.getenv("PG_CE_BAKEOFF_OFFICIAL_TOKENIZER", "jieba")

# GATE-0 thresholds for the scorer-math canary.
CANARY_PERFECT_MIN_F1 = float(os.getenv("PG_CE_BAKEOFF_CANARY_PERFECT_MIN", "0.99"))
CANARY_JUNK_MAX_F1 = float(os.getenv("PG_CE_BAKEOFF_CANARY_JUNK_MAX", "0.05"))

# Faithfulness substring check: spans shorter than this many tokens are skipped
# (trivial fragments like "the" trivially substring-match and carry no signal).
FAITHFULNESS_MIN_SPAN_TOKENS = int(os.getenv("PG_CE_BAKEOFF_FAITH_MIN_TOKENS", "6"))

# Fraction of (non-trivial) output spans that must be verbatim substrings of the
# source visible text for an extractor to PASS the faithfulness check. A truly
# extractive tool clears this comfortably; a generative rewrite does not.
FAITHFULNESS_MIN_VERBATIM_FRACTION = float(
    os.getenv("PG_CE_BAKEOFF_FAITH_MIN_FRACTION", "0.90")
)


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
# Markdown syntax that extractors ADD and that is NOT present in source HTML text
# (so it must be stripped before the verbatim-substring check, advisor pt 2).
_MD_SYNTAX_RE = re.compile(r"(^[#>\-\*\+\|]+|[#\*`_~\|\[\]\(\)]+|\d+\.\s)")


def normalize_unicode(text: str) -> str:
    """NFKC-normalize so en-dashes/ligatures/width-variants match an extractor's
    decoded output (an extractive tool emits decoded, normalized text)."""
    return unicodedata.normalize("NFKC", text or "")


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace runs to single spaces; strip ends."""
    return _WS_RE.sub(" ", text or "").strip()


def html_visible_text(html: str) -> str:
    """Return the whitespace-normalized VISIBLE text of an HTML document.

    Strips <script>/<style> bodies then all tags, then DECODES HTML entities
    (&amp; &nbsp; &#39; ...) and NFKC-normalizes Unicode. Without the decode +
    normalize, a faithful extractive tool's DECODED output would not be a
    substring of still-encoded source text -- a harness artifact that would
    wrongly hard-drop the lead candidate (advisor blocker 2). This is the
    reference surface the faithfulness check compares against.
    """
    if not html:
        return ""
    no_scripts = _HTML_SCRIPT_STYLE_RE.sub(" ", html)
    no_tags = _HTML_TAG_RE.sub(" ", no_scripts)
    decoded = _html.unescape(no_tags)
    return normalize_whitespace(normalize_unicode(decoded))


def strip_markdown_syntax(text: str) -> str:
    """Remove markdown decoration so output can be matched against plain text."""
    if not text:
        return ""
    stripped = _MD_SYNTAX_RE.sub(" ", text)
    return normalize_whitespace(stripped)


def tokenize(text: str) -> list[str]:
    """Whitespace + lowercase tokenization (tokenizer-agnostic canary path)."""
    return normalize_whitespace(text).lower().split()


# ---------------------------------------------------------------------------
# Pure-Python ROUGE-N (the SCORER-MATH canary path -- offline, no jieba)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RougeScore:
    """ROUGE-N decomposed into its reportable halves (sec_1_1 compliance)."""

    n: int
    recall: float  # main-body completeness: did real gold content survive
    precision: float  # 1 - precision == junk leaked in
    f1: float

    @property
    def junk_fraction(self) -> float:
        """Fraction of candidate n-grams absent from the gold body (chrome/SEO)."""
        return 1.0 - self.precision


def _ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _multiset_overlap(a: list[tuple], b: list[tuple]) -> int:
    """Clipped (multiset) overlap count -- the standard ROUGE counting rule."""
    from collections import Counter

    ca, cb = Counter(a), Counter(b)
    return sum(min(ca[g], cb[g]) for g in ca.keys() & cb.keys())


def rouge_n(candidate: str, gold: str, n: int = SCORER_CANARY_ROUGE_N) -> RougeScore:
    """Pure-Python ROUGE-N F1 between candidate and gold (offline canary path).

    recall    = overlap / |gold n-grams|       (completeness)
    precision = overlap / |candidate n-grams|  (1 - junk)
    f1        = harmonic mean

    This is NOT the official jieba N=5 scorer (that is the published-number
    anchor path); this is the tokenizer-agnostic math used to PROVE the scorer
    rewards perfect extraction and scores junk low.
    """
    cand_tokens = tokenize(candidate)
    gold_tokens = tokenize(gold)
    cand_ng = _ngrams(cand_tokens, n)
    gold_ng = _ngrams(gold_tokens, n)
    if not cand_ng and not gold_ng:
        # Two empties: vacuously perfect (both nothing). Canary never feeds this.
        return RougeScore(n=n, recall=1.0, precision=1.0, f1=1.0)
    if not cand_ng or not gold_ng:
        return RougeScore(n=n, recall=0.0, precision=0.0, f1=0.0)
    overlap = _multiset_overlap(cand_ng, gold_ng)
    recall = overlap / len(gold_ng)
    precision = overlap / len(cand_ng)
    f1 = 0.0 if (recall + precision) == 0 else (2 * recall * precision) / (recall + precision)
    return RougeScore(n=n, recall=recall, precision=precision, f1=f1)


# ---------------------------------------------------------------------------
# FAITHFULNESS substring check (the layer-specific landmine, advisor pt 2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaithfulnessReport:
    """Result of the verbatim-substring faithfulness check on one extraction."""

    checked_spans: int
    verbatim_spans: int
    verbatim_fraction: float
    is_faithful: bool
    first_violation: str = ""


def _content_spans(extractor_output: str) -> list[str]:
    """Split markdown-stripped output into checkable content spans.

    Spans are sentence-ish / line-ish chunks; trivial fragments (< min tokens)
    are dropped so the fraction is computed over meaningful content only.
    """
    stripped = strip_markdown_syntax(extractor_output)
    # Split on sentence terminators AND newlines/pipes (table cells handled by
    # caller via check_table_cells); keep it deterministic and dependency-free.
    raw = re.split(r"(?<=[.!?])\s+|\n+|\s\|\s", stripped)
    spans: list[str] = []
    for chunk in raw:
        chunk = normalize_whitespace(chunk)
        if len(chunk.split()) >= FAITHFULNESS_MIN_SPAN_TOKENS:
            spans.append(chunk)
    return spans


def check_faithfulness(
    extractor_output: str,
    source_html: str,
    *,
    min_fraction: float = FAITHFULNESS_MIN_VERBATIM_FRACTION,
) -> FaithfulnessReport:
    """Assert extractor output spans are verbatim substrings of source visible text.

    Extractive tools (Trafilatura, Resiliparse, jusText, readability, union,
    MinerU-HTML) clear this; a generative rewrite (ReaderLM-v2) does NOT, which
    is exactly the structural never-crown guard. Harness-internal: it does not
    touch the faithfulness engine.
    """
    source_text = html_visible_text(source_html).lower()
    spans = _content_spans(extractor_output)
    if not spans:
        # No checkable content -> cannot certify faithful (fail closed).
        return FaithfulnessReport(0, 0, 0.0, False, "no_checkable_spans")
    verbatim = 0
    first_violation = ""
    for span in spans:
        # Strip leading/trailing punctuation: an extractor adds a sentence-final
        # period that the source HTML omits at a block boundary (e.g. an <h1>
        # heading), so boundary punctuation must not cause a false violation.
        # NFKC-normalize so en-dashes / width-variants match the decoded source.
        # The WORDS are still required to be a contiguous verbatim substring --
        # a paraphrase still fails (advisor pt 2: must fail the paraphrase).
        probe = normalize_unicode(span).lower().strip(" .,;:!?—–-\"'()[]")
        if probe and probe in source_text:
            verbatim += 1
        elif not first_violation:
            first_violation = span[:160]
    fraction = verbatim / len(spans)
    return FaithfulnessReport(
        checked_spans=len(spans),
        verbatim_spans=verbatim,
        verbatim_fraction=fraction,
        is_faithful=fraction >= min_fraction,
        first_violation=first_violation,
    )


# ---------------------------------------------------------------------------
# Official WebMainBench scorer: DETECT-or-FALLBACK (advisor pt 4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OfficialScorerStatus:
    """Whether the OFFICIAL WebMainBench scorer is present + runnable."""

    available: bool
    eval_script_path: str
    benchmark_jsonl_path: str
    reason: str  # why available / why fell back


def locate_official_scorer(repo_root: str | None = None) -> OfficialScorerStatus:
    """Locate the cloned `opendatalab/MinerU-HTML` official scorer if present.

    The scorer is `eval_baselines.py` + `benchmark/WebMainBench_100.jsonl`,
    cloned (not pip-installed, not vendored). If absent, the published-number
    GATE-0 anchor uses the DOCUMENTED blind re-derivation fallback and is
    FLAGGED -- never silently circular, never trusting a search-snippet number.
    """
    root = repo_root or os.getenv("PG_WEBMAINBENCH_REPO", "")
    if not root:
        return OfficialScorerStatus(
            available=False,
            eval_script_path="",
            benchmark_jsonl_path="",
            reason=(
                "PG_WEBMAINBENCH_REPO unset -- official eval_baselines.py not located; "
                "GATE-0 published-number anchor falls back to blind re-derivation (FLAGGED)."
            ),
        )
    eval_script = os.path.join(root, "eval_baselines.py")
    bench_jsonl = os.path.join(root, "benchmark", "WebMainBench_100.jsonl")
    if os.path.isfile(eval_script) and os.path.isfile(bench_jsonl):
        return OfficialScorerStatus(
            available=True,
            eval_script_path=eval_script,
            benchmark_jsonl_path=bench_jsonl,
            reason="official eval_baselines.py + WebMainBench_100.jsonl located",
        )
    return OfficialScorerStatus(
        available=False,
        eval_script_path=eval_script,
        benchmark_jsonl_path=bench_jsonl,
        reason=(
            f"PG_WEBMAINBENCH_REPO={root!r} present but eval_baselines.py and/or "
            "benchmark/WebMainBench_100.jsonl missing -- blind re-derivation fallback (FLAGGED)."
        ),
    )


def load_webmainbench_pages(status: OfficialScorerStatus, limit: int = 0) -> list[dict]:
    """Load the in-repo WebMainBench_100.jsonl pages (html + gold Markdown).

    Returns [] when the official benchmark file is not located (the anchor
    reproduction is then honestly DEFERRED, never green-on-nothing). Each record
    exposes at least an 'html' field and a gold body field; the exact gold key
    is resolved leniently across the known WebMainBench schema variants.
    """
    import json

    if not status.available or not os.path.isfile(status.benchmark_jsonl_path):
        return []
    pages: list[dict] = []
    with open(status.benchmark_jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001 -- skip a malformed line, never invent
                continue
            html = rec.get("html") or rec.get("raw_html") or ""
            gold = (
                rec.get("groundtruth_content")
                or rec.get("gold_markdown")
                or rec.get("markdown")
                or rec.get("content")
                or ""
            )
            if html and gold:
                pages.append({"html": html, "gold": gold})
            if limit and len(pages) >= limit:
                break
    return pages


def build_official_runner(status: OfficialScorerStatus):
    """Return a callable(candidate, gold)->f1 backed by the cloned official scorer.

    Imports the official ROUGE-N (N=5, jieba) from the cloned MinerU-HTML repo on
    the host where it is present. Returns None when the repo or jieba is absent
    (so the caller falls back to the FLAGGED re-derivation). Kept here (not at
    module import) so this module stays offline-importable.
    """
    if not status.available:
        return None
    repo_root = os.path.dirname(status.eval_script_path)
    try:
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        import jieba  # type: ignore  # noqa: F401 -- the official tokenizer
        from webmainbench.metrics import rouge_n_f1  # type: ignore
    except Exception:  # noqa: BLE001 -- repo layout/jieba missing -> flagged fallback
        return None

    def _run(candidate: str, gold: str) -> float:
        # The official scorer's per-pair ROUGE-N F1 (N=5, jieba). Exact module
        # path is resolved at build time from the cloned repo; if its public API
        # name differs, this import fails above and the FLAGGED fallback fires.
        return float(rouge_n_f1(candidate, gold, n=OFFICIAL_ROUGE_N))

    return _run


@dataclass(frozen=True)
class ScoredF1:
    """One F1 score plus WHICH scorer produced it (honest provenance)."""

    f1: float
    recall: float
    precision: float
    scorer_used: str  # "official" | "fallback_rederived"
    detail: str = ""


def score_official_or_fallback(
    candidate_output: str,
    gold: str,
    status: OfficialScorerStatus,
    *,
    official_runner=None,
) -> ScoredF1:
    """PRIMARY = the OFFICIAL WebMainBench scorer (N=5 jieba) when located;
    else the pure-Python re-derivation at N=5, EXPLICITLY FLAGGED per result.

    `official_runner` is an injectable callable(candidate_output, gold) -> f1
    that shells/imports the cloned `eval_baselines.py`; injected by run_bakeoff
    on the host where the repo is present (kept out of this module so the import
    surface stays offline-clean). When the official scorer is unavailable, the
    fallback runs at OFFICIAL_ROUGE_N (5) -- NOT the canary's small N -- and is
    recorded as scorer_used="fallback_rederived" so a downstream reader never
    mistakes a re-derived number for the published official one.
    """
    if status.available and official_runner is not None:
        try:
            f1 = float(official_runner(candidate_output, gold))
            return ScoredF1(
                f1=f1,
                recall=float("nan"),
                precision=float("nan"),
                scorer_used="official",
                detail=f"official eval_baselines.py (N={OFFICIAL_ROUGE_N}, {OFFICIAL_TOKENIZER})",
            )
        except Exception as exc:  # noqa: BLE001 -- a broken official run must be
            # visible (flagged), never silently swapped for the fallback as if equal.
            fb = rouge_n(candidate_output, gold, n=OFFICIAL_ROUGE_N)
            return ScoredF1(
                fb.f1,
                fb.recall,
                fb.precision,
                "fallback_rederived",
                f"official runner FAILED ({exc!r}); re-derived N={OFFICIAL_ROUGE_N} (FLAGGED)",
            )
    fb = rouge_n(candidate_output, gold, n=OFFICIAL_ROUGE_N)
    return ScoredF1(
        fb.f1,
        fb.recall,
        fb.precision,
        "fallback_rederived",
        f"official scorer unavailable; blind re-derivation N={OFFICIAL_ROUGE_N} (FLAGGED): {status.reason}",
    )


# Published Dripper Table-2 anchors, pinned from the repo's OWN results table
# (github.com/opendatalab/MinerU-HTML README + arXiv 2511.23119), NOT from a
# search snippet. Used ONLY as the tolerance target for the official-scorer
# reproduction check; never as a substitute for actually running the scorer.
# Each value is the WebMainBench_100 ROUGE-N (N=5, jieba) F1 for the named
# extractor variant. Tolerance band is intentionally wide (variant/split drift).
PUBLISHED_ANCHORS: dict[str, float] = {
    "trafilatura": 0.6402,
    "resiliparse": 0.6290,
    "readability": 0.6542,
    "justext": 0.4782,
    "mineru_html": 0.9001,
}
ANCHOR_TOLERANCE = float(os.getenv("PG_CE_BAKEOFF_ANCHOR_TOL", "0.05"))


def anchor_within_tolerance(extractor_key: str, observed_f1: float) -> bool:
    """True iff observed official-scorer F1 matches the published anchor +/- tol."""
    if extractor_key not in PUBLISHED_ANCHORS:
        return False
    return abs(observed_f1 - PUBLISHED_ANCHORS[extractor_key]) <= ANCHOR_TOLERANCE


def average(values: Iterable[float]) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0
