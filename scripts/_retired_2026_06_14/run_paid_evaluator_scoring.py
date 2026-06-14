"""I-bench-002 — Paid sample evaluator scoring harness.

Wires a paid Layer-3 evaluator (e.g., GPT-5-mini, Opus 4.7, Gemini 2.5
Pro) into the benchmark proof-package per Carney delivery plan v6.2:
external evaluator scores POLARIS report against the 5-question
Carney goldset using PRISMA 2020 / AMSTAR-2 / GRADE per claim.

Per CLAUDE.md §-1.1: this is a SECOND independent line-by-line audit
on top of Claude's automated audit (I-bakeoff-A-001). The paid
evaluator is procured by the user; this harness wires the evaluator
output (per-claim verdict JSONL or scoring rubric YAML) into the
benchmark manifest format used downstream.

Status: SCAFFOLD. Evaluator procurement is user-action-blocked
(Carney v6.2 Phase 0 Task 0.1). When user provides credentials +
endpoint, the --live flag invokes the real evaluator; default mode
is dry-run that documents the integration shape without spending.

Usage:
    # Dry-run: load goldset + report, emit stub manifest
    python scripts/run_paid_evaluator_scoring.py \\
        --goldset config/benchmark/carney_goldset.jsonl \\
        --report outputs/<run>/report.md \\
        --pool outputs/<run>/evidence_pool.json \\
        --output outputs/I-bench-002/scoring.json

    # Live: pass --evaluator-endpoint + --evaluator-api-key
    python scripts/run_paid_evaluator_scoring.py ... \\
        --evaluator-endpoint https://api.openai.com/v1/chat/completions \\
        --evaluator-model gpt-5-mini \\
        --evaluator-api-key $OPENAI_API_KEY \\
        --live
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Default scoring rubric per CLAUDE.md §-1.1 — the FIVE per-claim
# verdicts the paid evaluator must produce.
RUBRIC_VERDICTS: tuple[str, ...] = (
    "VERIFIED",
    "PARTIAL",
    "UNSUPPORTED",
    "FABRICATED",
    "UNREACHABLE",
)


def build_evaluator_prompt(
    sentence: str,
    span: str,
    framework: str = "GRADE",
) -> str:
    """Construct the evaluator-facing prompt per CLAUDE.md §-1.1.

    The paid evaluator (e.g., GPT-5, Opus 4.7) reads:
      - the sentence + cited span quote
      - the rubric framework (PRISMA 2020 / AMSTAR-2 / GRADE)
    and returns ONE of the five verdicts in RUBRIC_VERDICTS.
    """
    return f"""You are a clinical-research evaluator. Apply the {framework} framework to assess whether the SENTENCE is supported by the CITED SPAN.

Return ONE verdict from this list:
- VERIFIED: every factual assertion in the SENTENCE is supported by the CITED SPAN. Conservative paraphrase allowed.
- PARTIAL: some claims supported, some are not. The sentence introduces facts beyond what the span supports.
- UNSUPPORTED: the cited span does not back the sentence's claims at all.
- FABRICATED: the sentence asserts content not in any cited span — numeric inflation, named-entity invention, or contradicted by the span.
- UNREACHABLE: the citation pointer is broken (unknown source, span out-of-bound).

Return STRICT JSON only:
{{"verdict": "VERIFIED" | "PARTIAL" | "UNSUPPORTED" | "FABRICATED" | "UNREACHABLE", "rationale": "<one short sentence with specific evidence>"}}

CITED SPAN:
{span}

SENTENCE:
{sentence}

JSON:"""


def score_claim_dry_run(sentence: str, span: str) -> dict[str, Any]:
    """Stub scoring (no LLM call). Returns a 'pending' placeholder."""
    return {
        "sentence": sentence[:200],
        "span_preview": span[:200],
        "verdict": "PENDING",
        "rationale": "dry-run: live evaluator not invoked",
    }


def score_claim_live(
    sentence: str,
    span: str,
    *,
    endpoint: str,
    api_key: str,
    model: str,
    framework: str = "GRADE",
) -> dict[str, Any]:
    """Invoke the paid evaluator on a single (sentence, span) pair.

    Uses httpx synchronously. The endpoint is OpenAI-compatible
    chat-completions; adjust if Anthropic / Gemini.
    """
    import httpx

    prompt = build_evaluator_prompt(sentence, span, framework=framework)
    response = httpx.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 200,
            "response_format": {"type": "json_object"},
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    verdict = str(parsed.get("verdict", "")).upper().strip()
    if verdict not in RUBRIC_VERDICTS:
        verdict = "UNREACHABLE"
    return {
        "sentence": sentence[:200],
        "span_preview": span[:200],
        "verdict": verdict,
        "rationale": str(parsed.get("rationale", ""))[:200],
        "model": model,
        "framework": framework,
    }


def run_paid_evaluator(
    sentences_with_spans: list[dict[str, str]],
    output_path: Path,
    *,
    live: bool = False,
    endpoint: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    framework: str = "GRADE",
) -> dict[str, Any]:
    """Score every claim in `sentences_with_spans` via the paid evaluator.

    `live=False` (default) emits stub PENDING placeholders for each
    claim so downstream pipeline can verify shape integration without
    spending. `live=True` requires endpoint + api_key + model.
    """
    if live:
        if not endpoint or not api_key or not model:
            raise ValueError(
                "live=True requires --evaluator-endpoint, --evaluator-api-key, "
                "and --evaluator-model"
            )

    per_claim: list[dict[str, Any]] = []
    for entry in sentences_with_spans:
        sentence = entry.get("sentence", "")
        span = entry.get("span", "")
        broken_pointers = entry.get("broken_pointers", "")
        if not sentence:
            continue
        # I-bench-002 iter-1 diff P1 fix: when any pointer is broken
        # (unknown source_id or out-of-bound span), force UNREACHABLE
        # without invoking the live evaluator. The evaluator can't
        # produce a meaningful verdict on a sentence whose citation
        # is provably broken; spending budget there is wrong.
        if broken_pointers:
            result = {
                "sentence": sentence[:200],
                "span_preview": span[:200],
                "verdict": "UNREACHABLE",
                "rationale": f"broken pointers: {broken_pointers}",
                "broken_pointers": broken_pointers,
            }
        elif live:
            result = score_claim_live(
                sentence, span,
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                framework=framework,
            )
        else:
            result = score_claim_dry_run(sentence, span)
        per_claim.append(result)

    counts = {v: 0 for v in RUBRIC_VERDICTS}
    counts["PENDING"] = 0
    for r in per_claim:
        v = r["verdict"]
        counts[v] = counts.get(v, 0) + 1
    total = len(per_claim) or 1

    manifest = {
        "milestone": "I-bench-002",
        "version": "v1",
        "live": live,
        "framework": framework,
        "model": model if live else None,
        "n_claims": len(per_claim),
        "verdict_counts": counts,
        "verified_rate": (
            round(counts.get("VERIFIED", 0) / total, 4) if live else None
        ),
        "fabricated_rate": (
            round(counts.get("FABRICATED", 0) / total, 4) if live else None
        ),
        "per_claim": per_claim,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _load_sentences_with_spans(
    report_path: Path,
    pool_path: Path,
) -> list[dict[str, str]]:
    """Extract (sentence, span) pairs from token-bearing report + pool.

    NOTE: this path expects a PRE-RESOLUTION verified-sentences artifact
    that retains `[#ev:id:start-end]` tokens. The DELIVERED `report.md`
    has those tokens stripped (`resolve_provenance_to_citations`) and
    replaced with numbered `[N]` markers — that path returns empty
    spans here. Use `_load_sentences_with_spans_from_jsonl` for the
    canonical pre-resolution input.

    Broken pointer preservation: invalid evidence_id or out-of-bound
    span produces an empty span_chars but the sentence is preserved
    in the output stream so downstream UNREACHABLE verdict can still
    fire (the evaluator sees a sentence with no evidence and returns
    UNREACHABLE per rubric).
    """
    from scripts.run_line_by_line_audit import (  # noqa: E402
        _normalize_pool,
        _PROVENANCE_TOKEN_RE,
        _split_sentences,
    )

    pool = _normalize_pool(json.loads(pool_path.read_text(encoding="utf-8")))
    sentences = _split_sentences(report_path.read_text(encoding="utf-8"))
    pairs: list[dict[str, str]] = []
    for sentence in sentences:
        tokens = _PROVENANCE_TOKEN_RE.findall(sentence)
        spans: list[str] = []
        broken_pointers: list[str] = []
        for ev_id, start_str, end_str in tokens:
            if ev_id not in pool:
                broken_pointers.append(f"unknown:{ev_id}")
                continue
            full = pool[ev_id].get("direct_quote", "")
            start, end = int(start_str), int(end_str)
            if 0 <= start <= end <= len(full):
                spans.append(full[start:end])
            else:
                broken_pointers.append(f"oob:{ev_id}:{start}-{end}")
        clean_sentence = _PROVENANCE_TOKEN_RE.sub("", sentence).strip()
        pairs.append({
            "sentence": clean_sentence,
            "span": " // ".join(spans),
            "broken_pointers": " | ".join(broken_pointers),
        })
    return pairs


def _load_sentences_with_spans_from_jsonl(
    verified_path: Path,
    pool_path: Path,
) -> list[dict[str, str]]:
    """Canonical input: JSONL of {sentence_text} or {sentence} per line
    where each sentence retains its [#ev:...] tokens.
    """
    from scripts.run_line_by_line_audit import (  # noqa: E402
        _normalize_pool,
        _normalize_sentence,
        _PROVENANCE_TOKEN_RE,
    )

    pool = _normalize_pool(json.loads(pool_path.read_text(encoding="utf-8")))
    pairs: list[dict[str, str]] = []
    for line in verified_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        sentence = _normalize_sentence(record)
        if not sentence:
            continue
        tokens = _PROVENANCE_TOKEN_RE.findall(sentence)
        spans: list[str] = []
        broken_pointers: list[str] = []
        for ev_id, start_str, end_str in tokens:
            if ev_id not in pool:
                broken_pointers.append(f"unknown:{ev_id}")
                continue
            full = pool[ev_id].get("direct_quote", "")
            start, end = int(start_str), int(end_str)
            if 0 <= start <= end <= len(full):
                spans.append(full[start:end])
            else:
                broken_pointers.append(f"oob:{ev_id}:{start}-{end}")
        clean_sentence = _PROVENANCE_TOKEN_RE.sub("", sentence).strip()
        pairs.append({
            "sentence": clean_sentence,
            "span": " // ".join(spans),
            "broken_pointers": " | ".join(broken_pointers),
        })
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--report", type=Path,
                        help="Path to a token-bearing artifact (NOT delivered report.md). See _load_sentences_with_spans docstring.")
    parser.add_argument("--verified-sentences", type=Path,
                        help="JSONL of {sentence_text} or {sentence}, canonical pre-resolution input.")
    parser.add_argument("--pool", type=Path)
    parser.add_argument("--goldset", type=Path,
                        help="JSONL of {sentence, span} for direct scoring (skip --report+--pool).")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--evaluator-endpoint", type=str)
    parser.add_argument("--evaluator-api-key", type=str)
    parser.add_argument("--evaluator-model", type=str)
    parser.add_argument("--framework", type=str, default="GRADE",
                        help="Audit framework: GRADE, PRISMA, AMSTAR-2.")
    args = parser.parse_args()

    if args.goldset and args.goldset.exists():
        pairs: list[dict[str, str]] = []
        for line in args.goldset.read_text(encoding="utf-8").splitlines():
            if line.strip():
                pairs.append(json.loads(line))
    elif args.verified_sentences and args.pool:
        if not args.verified_sentences.exists() or not args.pool.exists():
            print("ERROR: verified-sentences or pool path not found", file=sys.stderr)
            return 1
        pairs = _load_sentences_with_spans_from_jsonl(
            args.verified_sentences, args.pool,
        )
    else:
        if not args.report or not args.pool:
            print(
                "ERROR: provide --goldset, OR --verified-sentences + --pool, "
                "OR --report + --pool (token-bearing artifact only).",
                file=sys.stderr,
            )
            return 1
        if not args.report.exists() or not args.pool.exists():
            print("ERROR: report or pool path not found", file=sys.stderr)
            return 1
        pairs = _load_sentences_with_spans(args.report, args.pool)

    try:
        result = run_paid_evaluator(
            pairs,
            args.output,
            live=args.live,
            endpoint=args.evaluator_endpoint,
            api_key=args.evaluator_api_key,
            model=args.evaluator_model,
            framework=args.framework,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"Paid evaluator scoring: {result['n_claims']} claims, "
        f"live={result['live']}, framework={result['framework']}"
    )
    if result["live"]:
        print(
            f"  VERIFIED rate: {result['verified_rate']:.1%}, "
            f"FABRICATED rate: {result['fabricated_rate']:.1%}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
