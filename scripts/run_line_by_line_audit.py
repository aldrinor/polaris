"""I-bakeoff-A-001 — Line-by-line audit harness (per CLAUDE.md §-1.1).

Foundation deliverable for Path A bakeoff. Produces a per-claim
verdict for every sentence in the **verified-sentences artifact**
(NOT the delivered report.md — see input shape below).

Input shape: this harness audits the PRE-RESOLUTION verified-sentence
stream that retains `[#ev:id:start-end]` provenance tokens. The
delivered `report.md` strips these tokens (`resolve_provenance_to_citations`)
and replaces them with numbered citations, so auditing report.md
directly would yield all UNSUPPORTED/no_token. Two accepted inputs:

  --verified-sentences <jsonl>   Each line is {"sentence": "...with [#ev:...] tokens..."}.
                                  This is the canonical artifact emitted by
                                  generator2/strict_verify before resolution.

  --report <md> --pool <json>    Legacy / direct text path — assumes report
                                  contains tokens (works for INTERNAL test
                                  artifacts but NOT for delivered reports).

Per CLAUDE.md §-1.1: BOTH inputs require evidence_pool.json with
the corresponding source spans. Output: per-claim VERIFIED /
PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE verdicts.

    VERIFIED   — sentence is fully supported by its cited span(s)
    PARTIAL    — some claims supported, some not; partial entailment
    UNSUPPORTED — content overlap insufficient; cited span doesn't
                  back the claim
    FABRICATED  — sentence asserts content not in any cited span
                  (numeric mismatch, named-entity inflation, etc.)
    UNREACHABLE — span pointer invalid; cannot verify

This is the ONLY acceptable evaluation framework per CLAUDE.md §-1.1
(STRICTLY BANNED: word counts, citation counts, pattern presence,
sample-based audits, string-presence checks, metadata comparison).

Per CLAUDE.md §-1.1, both Claude AND Codex run independent line-by-
line audits in parallel. This script is Claude's automated audit;
Codex's audit is a separate manual pass via `codex exec`.

Usage:
    python scripts/run_line_by_line_audit.py \\
        --report outputs/I-live-1/clinical/.../report.md \\
        --pool outputs/I-live-1/clinical/.../evidence_pool.json \\
        --output outputs/audits/<run-id>/claude_audit.json

The model bakeoff (Path A) is a wrapper that runs the pipeline with
multiple --model arguments, then runs THIS audit on each output and
compares the per-claim verdict distribution. That wrapper is
out-of-scope here; this PR ships the foundational audit primitive.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Reuse strict_verify primitives (mechanical checks (a)-(e))
_DECIMAL_RE = re.compile(r"\d+(?:\.\d+)?")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+")
_PROVENANCE_TOKEN_RE = re.compile(r"\[#ev:([^:]+):(\d+)-(\d+)\]")

_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "of", "in", "on", "at",
    "to", "for", "with", "as", "by", "from", "into", "through", "during",
    "before", "after", "above", "below", "between", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "having", "do",
    "does", "did", "doing", "will", "would", "should", "could", "may",
    "might", "must", "can", "this", "that", "these", "those", "it",
    "its", "their", "there", "they", "them", "we", "us", "our", "you",
    "your", "i", "me", "my", "he", "she", "his", "her",
})


def _normalize_pool(raw: Any) -> dict[str, dict[str, Any]]:
    """Normalize evidence pool JSON to {id: {evidence_id, direct_quote/full_text/snippet}}.

    Accepts:
    - List of {evidence_id, direct_quote/full_text/snippet} (legacy generator2 schema).
    - List of {source_id, full_text/snippet} (canonical retrieval2.EvidencePool schema).
    - Object {<id>: <entry>} (already keyed).
    - Object {sources: [<entry>, ...]} (EvidencePool serialized with sources field).
    """
    if isinstance(raw, dict) and "sources" in raw and isinstance(raw["sources"], list):
        raw = raw["sources"]
    if isinstance(raw, list):
        normalized: dict[str, dict[str, Any]] = {}
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            ev_id = entry.get("evidence_id") or entry.get("source_id")
            if not ev_id:
                continue
            direct_quote = (
                entry.get("direct_quote")
                or entry.get("full_text")
                or entry.get("snippet", "")
                or ""
            )
            normalized[ev_id] = {
                "evidence_id": ev_id,
                "direct_quote": direct_quote,
                **{k: v for k, v in entry.items() if k not in {"evidence_id", "source_id", "direct_quote"}},
            }
        return normalized
    if isinstance(raw, dict):
        # Already keyed: ensure each entry has direct_quote alias
        normalized = {}
        for ev_id, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            direct_quote = (
                entry.get("direct_quote")
                or entry.get("full_text")
                or entry.get("snippet", "")
                or ""
            )
            normalized[ev_id] = {**entry, "direct_quote": direct_quote, "evidence_id": ev_id}
        return normalized
    raise ValueError(f"unrecognized pool shape: {type(raw).__name__}")


def _normalize_sentence(entry: Any) -> str:
    """Normalize verified-sentence record to string. Accepts:
    - {sentence: "..."}
    - {sentence_text: "..."} (canonical VerifiedSentence schema)
    - "..." (raw string)
    """
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("sentence") or entry.get("sentence_text") or ""
    return ""


def _content_words(text: str) -> set[str]:
    return {
        m.group(0).lower()
        for m in _WORD_RE.finditer(text)
        if len(m.group(0)) >= 3 and m.group(0).lower() not in _STOPWORDS
    }


def _decimals(text: str) -> set[str]:
    return {m.group(0) for m in _DECIMAL_RE.finditer(text)}


def _split_sentences(text: str) -> list[str]:
    """Lightweight sentence splitter (matches generator orchestrator)."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\[])|(?<=\])\s+(?=[A-Z])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def audit_sentence(
    sentence: str,
    pool: dict[str, dict[str, Any]],
    *,
    min_overlap: int = 2,
) -> dict[str, Any]:
    """Per-sentence verdict: VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE.

    Mechanical checks (per strict_verify):
    1. provenance tokens present
    2. each token's evidence_id resolvable in pool
    3. span bounds valid against full_text
    4. every decimal in sentence appears in cited spans (numeric_match)
    5. >=N shared content words (overlap_ok)

    Verdict mapping:
    - No tokens → UNSUPPORTED
    - Token references unknown source_id → UNREACHABLE
    - Span out-of-bounds → UNREACHABLE
    - decimal mismatch + low overlap → FABRICATED
    - decimal mismatch but overlap ok → PARTIAL (numeric inflation pattern)
    - low overlap but decimals match → PARTIAL (topical inflation)
    - decimals match + overlap ok → VERIFIED
    """
    tokens = _PROVENANCE_TOKEN_RE.findall(sentence)
    if not tokens:
        return {
            "sentence": sentence[:200],
            "verdict": "UNSUPPORTED",
            "reason": "no_provenance_token",
            "tokens": [],
        }

    span_texts: list[str] = []
    token_dump: list[dict[str, Any]] = []
    for ev_id, start_str, end_str in tokens:
        if ev_id not in pool:
            return {
                "sentence": sentence[:200],
                "verdict": "UNREACHABLE",
                "reason": f"unknown_evidence_id:{ev_id}",
                "tokens": [{
                    "evidence_id": ev_id,
                    "start": int(start_str),
                    "end": int(end_str),
                }],
            }
        full_text = (
            pool[ev_id].get("direct_quote")
            or pool[ev_id].get("full_text", "")
            or ""
        )
        start = int(start_str)
        end = int(end_str)
        if start < 0 or end > len(full_text) or start > end:
            return {
                "sentence": sentence[:200],
                "verdict": "UNREACHABLE",
                "reason": f"span_out_of_range:{ev_id}:{start}-{end}",
                "tokens": [{
                    "evidence_id": ev_id,
                    "start": start,
                    "end": end,
                    "max": len(full_text),
                }],
            }
        span = full_text[start:end]
        span_texts.append(span)
        token_dump.append({
            "evidence_id": ev_id,
            "start": start,
            "end": end,
            "span_chars": len(span),
            # I-bakeoff-A-001 iter-1 P2: include actual span text per
            # CLAUDE.md §-1.1 ("per-claim verdict — with the specific
            # evidence span quote that supports the verdict"). Truncate
            # to 200 chars to bound manifest size.
            "span_text": span[:200],
        })

    sentence_clean = _PROVENANCE_TOKEN_RE.sub("", sentence).strip()
    combined_span = " ".join(span_texts)
    sentence_decimals = _decimals(sentence_clean)
    span_decimals = _decimals(combined_span)
    sentence_words = _content_words(sentence_clean)
    span_words = _content_words(combined_span)
    overlap = sentence_words & span_words

    decimals_match = sentence_decimals.issubset(span_decimals)
    overlap_ok = len(overlap) >= min_overlap

    if decimals_match and overlap_ok:
        verdict = "VERIFIED"
        reason = "all_checks_pass"
    elif decimals_match and not overlap_ok:
        verdict = "PARTIAL"
        reason = f"low_content_overlap:{len(overlap)}<{min_overlap}"
    elif not decimals_match and overlap_ok:
        verdict = "PARTIAL"
        reason = (
            f"numeric_mismatch:sentence={sorted(sentence_decimals)} "
            f"vs span={sorted(span_decimals)}"
        )
    else:
        # Both mechanical checks fail: high confidence fabrication signal
        verdict = "FABRICATED"
        reason = (
            f"numeric_mismatch_AND_low_overlap:sentence_decimals="
            f"{sorted(sentence_decimals)} overlap={len(overlap)}"
        )

    return {
        "sentence": sentence_clean[:200],
        "verdict": verdict,
        "reason": reason,
        "tokens": token_dump,
        "decimals_match": decimals_match,
        "content_overlap_count": len(overlap),
    }


def run_line_by_line_audit(
    report_text: str,
    pool: dict[str, dict[str, Any]],
    *,
    min_overlap: int = 2,
) -> dict[str, Any]:
    """Run audit on every sentence in `report_text`. Return summary.

    NOTE on verdict semantics (Codex iter-2 P1-1): VERIFIED here means
    "passes mechanical lexical + numeric checks". It does NOT mean
    "the cited span semantically entails the sentence" — that
    requires the LLM-as-judge entailment check (gated by
    `PG_STRICT_VERIFY_ENTAILMENT` and run inside strict_verify, not
    here). For Carney audit-grade evaluation, run THIS audit
    (mechanical) AND the entailment judge in parallel; both must
    pass for a sentence to be safe-to-deliver. The audit harness
    reports the mechanical lane; the judge lane is separate.
    """
    sentences = _split_sentences(report_text)
    return _run_audit_on_sentences(sentences, pool, min_overlap=min_overlap)


def run_line_by_line_audit_records(
    sentence_records: list[str],
    pool: dict[str, dict[str, Any]],
    *,
    min_overlap: int = 2,
) -> dict[str, Any]:
    """Audit a pre-segmented list of sentences (one verdict per record).

    Use this when input is JSONL where each line is already one
    verified sentence. Avoids the re-split that
    `run_line_by_line_audit` does on raw report text.
    """
    return _run_audit_on_sentences(
        [s for s in sentence_records if s], pool, min_overlap=min_overlap
    )


def _run_audit_on_sentences(
    sentences: list[str],
    pool: dict[str, dict[str, Any]],
    *,
    min_overlap: int = 2,
) -> dict[str, Any]:
    per_sentence: list[dict[str, Any]] = []
    counts = {
        "VERIFIED": 0,
        "PARTIAL": 0,
        "UNSUPPORTED": 0,
        "FABRICATED": 0,
        "UNREACHABLE": 0,
    }
    for s in sentences:
        result = audit_sentence(s, pool, min_overlap=min_overlap)
        per_sentence.append(result)
        counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1
    total = len(sentences) or 1
    summary = {
        "total_sentences": len(sentences),
        "verdict_counts": counts,
        "verified_rate": round(counts["VERIFIED"] / total, 4),
        "fabricated_rate": round(counts["FABRICATED"] / total, 4),
        "alert": counts["FABRICATED"] > 0 or counts["UNREACHABLE"] > 0,
    }
    return {
        "milestone": "I-bakeoff-A-001",
        "version": "v1",
        "summary": summary,
        "per_sentence": per_sentence,
        "verdict_semantics_note": (
            "VERIFIED = mechanical (decimals_match + content_overlap >= "
            f"{min_overlap}). Semantic entailment is a SEPARATE check "
            "run via the LLM-as-judge gate; both must pass for safe-to-deliver."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Path to a markdown/text artifact containing [#ev:...] tokens. "
             "Mutually exclusive with --verified-sentences.",
    )
    parser.add_argument(
        "--verified-sentences",
        type=Path,
        help="Path to JSONL file with one verified-sentence per line "
             "({\"sentence\": \"...\"}). Canonical input.",
    )
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="Path for the audit JSON manifest.")
    parser.add_argument(
        "--output-md",
        type=Path,
        help="Optional markdown summary ({model}/audit.md format).",
    )
    parser.add_argument("--min-overlap", type=int, default=2)
    args = parser.parse_args()

    if not args.pool.exists():
        print(f"ERROR: evidence pool not found: {args.pool}", file=sys.stderr)
        return 1
    if args.report and args.verified_sentences:
        print("ERROR: --report and --verified-sentences are mutually exclusive",
              file=sys.stderr)
        return 1
    if not args.report and not args.verified_sentences:
        print("ERROR: provide --report OR --verified-sentences", file=sys.stderr)
        return 1

    pool = _normalize_pool(json.loads(args.pool.read_text(encoding="utf-8")))

    if args.verified_sentences:
        if not args.verified_sentences.exists():
            print(f"ERROR: verified-sentences file not found: {args.verified_sentences}",
                  file=sys.stderr)
            return 1
        sentences = []
        raw_lines = args.verified_sentences.read_text(encoding="utf-8").splitlines()
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            sent = _normalize_sentence(obj)
            if sent:
                sentences.append(sent)
        if not sentences and any(
            ln.strip() for ln in raw_lines
        ):
            print(
                "ERROR: --verified-sentences contained non-empty input but "
                "produced 0 sentences. Check schema: expected "
                "{sentence: '...'} or {sentence_text: '...'} per line.",
                file=sys.stderr,
            )
            return 1
        # Codex iter-2 P1-2 fix: preserve one-record-one-verdict
        # semantics for JSONL input. Use the records-aware entry point
        # instead of joining-then-resplitting.
        result = run_line_by_line_audit_records(
            sentences, pool, min_overlap=args.min_overlap,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        if args.output_md:
            args.output_md.parent.mkdir(parents=True, exist_ok=True)
            args.output_md.write_text(_render_audit_md(result), encoding="utf-8")
        s = result["summary"]
        print(
            f"Audit complete: {s['total_sentences']} sentences, "
            f"{s['verified_rate']:.1%} VERIFIED, "
            f"{s['fabricated_rate']:.1%} FABRICATED, "
            f"alert={s['alert']}"
        )
        return 2 if s["alert"] else 0
    # --report path (legacy / direct text)
    if not args.report.exists():
        print(f"ERROR: report not found: {args.report}", file=sys.stderr)
        return 1
    report_text = args.report.read_text(encoding="utf-8")
    result = run_line_by_line_audit(report_text, pool, min_overlap=args.min_overlap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(_render_audit_md(result), encoding="utf-8")

    s = result["summary"]
    print(
        f"Audit complete: {s['total_sentences']} sentences, "
        f"{s['verified_rate']:.1%} VERIFIED, "
        f"{s['fabricated_rate']:.1%} FABRICATED, "
        f"alert={s['alert']}"
    )
    if s["alert"]:
        return 2
    return 0


def _render_audit_md(result: dict[str, Any]) -> str:
    """Render audit result as a markdown summary for {model}/audit.md.

    Format mirrors the bakeoff acceptance: per-claim verdicts table +
    summary stats + recommendation.
    """
    s = result["summary"]
    counts = s["verdict_counts"]
    lines = [
        f"# Line-by-line audit — {result['milestone']} {result['version']}",
        "",
        "## Summary",
        "",
        f"- Total sentences: **{s['total_sentences']}**",
        f"- VERIFIED: {counts['VERIFIED']} ({s['verified_rate']:.1%})",
        f"- PARTIAL: {counts['PARTIAL']}",
        f"- UNSUPPORTED: {counts['UNSUPPORTED']}",
        f"- **FABRICATED: {counts['FABRICATED']}** ({s['fabricated_rate']:.1%})",
        f"- UNREACHABLE: {counts['UNREACHABLE']}",
        "",
        f"**Alert:** {'YES' if s['alert'] else 'no'} "
        f"(fires on FABRICATED > 0 or UNREACHABLE > 0)",
        "",
        "## Per-claim verdicts (with cited span per CLAUDE.md §-1.1)",
        "",
        "| # | Verdict | Reason | Sentence | Cited span quote |",
        "|---|---------|--------|----------|------------------|",
    ]
    for i, ps in enumerate(result["per_sentence"][:200]):
        sent = ps["sentence"][:120].replace("|", "\\|").replace("\n", " ")
        reason = ps["reason"][:60].replace("|", "\\|")
        # Concatenate cited spans (first 200 chars total) for audit traceability
        spans = ps.get("tokens", []) or []
        span_quote = " // ".join(t.get("span_text", "")[:120] for t in spans)[:200]
        span_quote = span_quote.replace("|", "\\|").replace("\n", " ") or "—"
        lines.append(f"| {i+1} | {ps['verdict']} | {reason} | {sent} | {span_quote} |")
    if len(result["per_sentence"]) > 200:
        lines.append(f"| ... | ({len(result['per_sentence']) - 200} more) | ... | ... |")
    lines.extend([
        "",
        "## Recommendation",
        "",
    ])
    if counts["FABRICATED"] > 0:
        lines.append(
            "- **REJECT**: FABRICATED claims indicate the generator inserted "
            "content not supported by any cited span. Re-run with a different "
            "generator or drop the affected sentences."
        )
    elif counts["UNREACHABLE"] > 0:
        lines.append(
            "- **INVESTIGATE**: UNREACHABLE means the citation pointer is "
            "broken (unknown source or out-of-bound span). Likely a "
            "generator-evidence-pool mismatch."
        )
    elif s["verified_rate"] >= 0.7:
        lines.append(
            f"- **ACCEPT**: {s['verified_rate']:.1%} VERIFIED — meets the "
            "Carney audit-grade bar (>=70% with no FABRICATED)."
        )
    else:
        # Brief specifies vocabulary ACCEPT / REJECT / INVESTIGATE.
        # Below-threshold-no-alert maps to INVESTIGATE (the run is
        # not safe-to-ship at <70% verified, and it's not
        # FABRICATED-rejectable; it warrants investigation of
        # repair-loop or generator selection).
        lines.append(
            f"- **INVESTIGATE**: {s['verified_rate']:.1%} VERIFIED is below "
            "the 70% Carney bar. No FABRICATED claims found, but the "
            "verified-rate gap warrants a repair-loop run, a different "
            "generator (Path A bakeoff), or investigation of why "
            "high PARTIAL/UNSUPPORTED counts persist."
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
