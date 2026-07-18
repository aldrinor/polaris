#!/usr/bin/env python3
"""S6 VERIFY — thin checkpoint runner (cp5 -> cp6).

Reads ``cp5_generation_snapshot.json`` (the S5 compose checkpoint: composed section
drafts carrying ``[#ev:<id>:<a>-<b>]`` provenance tokens + the evidence pool), runs the
UNCHANGED production faithfulness engine
(``provenance_generator.verify_sentence_provenance``) once per sentence, and writes
``cp6_postverify_checkpoint.json``.

S6 SEMANTICS = DROP -> LABEL + REPAIR (operator 2026-07-10,
``.codex/I-arch-plan/OPERATOR_SECTION_DIRECTIVES.md`` S6 row; memory
``feedback_faithfulness_engine_unlocked_serves_visible_quality``): the verifier LABELS every
sentence with its verdict + confidence and KEEPS it. It NEVER silently deletes/thins a
sentence to make a number go up. The grounding signal (verifier_pass / failure_reasons /
certainty) is PRESERVED on each sentence so S7 render (and the compose loop) can present a
weak claim AS weak instead of shipping a thinned report. The engine's own internal
NLI re-anchor / local-window rescue IS the "repair"; this runner adds NO new gate and
rewrites NO prose — prose repair is owned by the compose loop, per the S6 build brief
(strict_verify.py / verified_compose.py are NOT touched here).

CONTEXT-LEVEL FAITHFULNESS (operator 2026-07-10,
``feedback_faithfulness_is_context_level_not_lexical_overlap``): a sentence is faithful iff
(1) its cited span semantically ENTAILS it (NLI-style, ``PG_STRICT_VERIFY_ENTAILMENT``) AND
(2) every number/decimal matches (``require_number_match=True``). This runner does NOT depend
on the lexical content-word-overlap ghost; it calls the engine exactly as the live flag slate
configures it and records the outcome. Numbers stay strict.

GENERALIZATION MANDATE: this runner generalizes to ANY research question / benchmark item.
There is NO question-specific branch, NO corpus-tuned magic number, and NO cap / target /
thinner. Every input is read from cp5 + the env flag slate; the section set, the sentences and
the evidence pool all come from the checkpoint. A fix that only helped one corpus would be a
bug (CLAUDE.md §-1.3 day-waster ban).

Usage:
    python scripts/run_s6_verify.py --cp5 <path/to/cp5_generation_snapshot.json> \
        [--corpus <path/to/cp2_corpus_snapshot.json>] [--out <path/to/cp6_...json>]

``--corpus`` is optional: the evidence pool is taken from cp5 itself when it embeds one, else
from ``--corpus``, else resolved from the cp5 ``upstream`` chain, else from a sibling
``cp2_corpus_snapshot.json`` in the cp5 run dir. FAIL LOUD if none is found (LAW II).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# Make the repo importable when run as a bare script (scripts/ is one level under the root).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    verify_sentence_provenance,
)
from src.polaris_graph.generator.verified_compose import (  # noqa: E402
    split_into_sentences,
)

# ---------------------------------------------------------------------------
# Constants (checkpoint envelope contract — mirrors the sibling section runners)
# ---------------------------------------------------------------------------

S6_STAGE = "s6_verify"
CP6_FILENAME = "cp6_postverify_checkpoint.json"
CP6_SCHEMA_VERSION = 1

# The verify-affecting env flags recorded on cp6 for reproducibility. Read at CALL TIME from
# the live env (LAW VI) — never hardcoded thresholds. The engine reads these itself; we only
# SNAPSHOT them so a reader knows the flag slate the labels were produced under.
VERIFY_FLAG_NAMES: tuple[str, ...] = (
    "PG_STRICT_VERIFY_ENTAILMENT",
    "PG_ENTAILMENT_MODEL",
    "PG_PROVENANCE_MIN_CONTENT_OVERLAP",
    "PG_PROVENANCE_PERCENT_ROLE_MATCH",
    "PG_STRICT_VERIFY_SCRIPT_AWARE",
    "PG_SPAN_RESOLVER",
    "PG_PROVENANCE_REANCHOR",
)

# §-1.1 per-claim verdict vocabulary. This runner labels each sentence with one of these and
# ALWAYS keeps the sentence (label-not-guts). The raw engine bool + reasons ride alongside so
# the mapping is fully transparent and never loses information.
VERDICT_VERIFIED = "VERIFIED"          # entailed + numbers match, clean
VERDICT_PARTIAL = "PARTIAL"            # kept, but carries a soft disclosure warning
VERDICT_UNSUPPORTED = "UNSUPPORTED"    # not grounded (no/invalid span, low overlap, NEUTRAL entailment)
VERDICT_FABRICATED = "FABRICATED"      # a number not in any cited span, or span CONTRADICTS the claim
VERDICT_UNREACHABLE = "UNREACHABLE"    # entailment judge was unreachable (kept + disclosed)

# Substrings of the engine's ``failure_reasons`` that mark a FABRICATED claim: a quantity the
# claim asserts is in NO cited span, or a semantic CONTRADICTED entailment verdict. These are the
# real provenance_generator reason literals (checked case-folded, so ``verdict=CONTRADICTED``
# inside an ``entailment_failed:...`` reason is caught too). A NEUTRAL entailment_failed carries
# none of these and stays UNSUPPORTED (unproven, not proven-false). Matched as substrings so
# eid-suffixed dynamic reasons (e.g. ``no_integer_overlap_any_cited_span:<eid>:missing=[...]``)
# are covered without pinning to one corpus.
_FABRICATED_REASON_MARKERS: tuple[str, ...] = (
    "no_integer_overlap",         # a claim integer appears in no cited span
    "no_decimal_overlap",         # a claim decimal appears in no cited span
    "numeric_mismatch",
    "percent_not_in_cited_span",
    "contradicted",               # entailment CONTRADICTED (bare, or verdict=CONTRADICTED)
)


class S6RunnerError(RuntimeError):
    """A cp5->cp6 verify-runner error. FAIL LOUD (LAW II) — never silent."""


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path: str | Path) -> Any:
    p = Path(path)
    if not p.exists():
        raise S6RunnerError(f"input checkpoint not found: {p}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise S6RunnerError(f"input checkpoint {p} is unreadable/corrupt: {exc}") from exc


def _capture_flag_slate() -> dict[str, str]:
    return {name: os.environ.get(name, "") for name in VERIFY_FLAG_NAMES}


# ---------------------------------------------------------------------------
# cp5 extraction (drafts + evidence pool) — shape-tolerant, fail-loud
# ---------------------------------------------------------------------------

def _extract_section_drafts(cp5: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ordered ``[{section_index, section_id, title, draft_text}]`` from cp5.

    S5 compose is expected to write the composed section prose (each sentence carrying its
    ``[#ev:<id>:<a>-<b>]`` tokens) under ``cp5['payload']['sections']`` (a list) or
    ``['section_drafts']`` (a title->prose dict). The env-level ``section_drafts`` map (the
    corpus-snapshot shape) is also accepted. FAIL LOUD if no composed prose is present — an
    empty/thinned verify result is NEVER produced silently (LAW II); the caller must run S5
    compose first.
    """
    if not isinstance(cp5, dict):
        raise S6RunnerError("cp5 is not a JSON object")
    payload = cp5.get("payload") if isinstance(cp5.get("payload"), dict) else {}

    # (1) list-of-sections shape: [{section_id/title, draft/prose/text/composed}, ...]
    for container in (payload, cp5):
        secs = container.get("sections") if isinstance(container, dict) else None
        if isinstance(secs, list) and secs and all(isinstance(s, dict) for s in secs):
            rows: list[dict[str, Any]] = []
            for i, s in enumerate(secs):
                draft = (
                    s.get("draft")
                    or s.get("prose")
                    or s.get("text")
                    or s.get("composed")
                    or s.get("draft_text")
                    or ""
                )
                title = str(s.get("title") or s.get("section_title") or f"Section {i}")
                sid = str(s.get("section_id") or s.get("id") or i)
                rows.append(
                    {"section_index": i, "section_id": sid, "title": title, "draft_text": str(draft)}
                )
            if any(r["draft_text"].strip() for r in rows):
                return rows

    # (2) dict shape: {section_title: composed_prose}
    for container in (payload, cp5):
        sd = container.get("section_drafts") if isinstance(container, dict) else None
        if isinstance(sd, dict) and any(str(v).strip() for v in sd.values()):
            rows = []
            for i, (title, prose) in enumerate(sd.items()):
                rows.append(
                    {
                        "section_index": i,
                        "section_id": str(title),
                        "title": str(title),
                        "draft_text": str(prose or ""),
                    }
                )
            return rows

    raise S6RunnerError(
        "cp5 carries no composed section drafts (looked in payload.sections, "
        "payload.section_drafts and env-level section_drafts). S6 verify has nothing to check "
        "until S5 compose writes the composed prose (with [#ev] provenance tokens) into cp5. "
        "Run S5 compose first; refusing to emit an empty/thinned cp6."
    )


def _normalize_pool(raw: Any) -> dict[str, dict[str, Any]]:
    """Coerce an evidence container to ``{evidence_id: row}`` (the shape verify expects).

    Accepts a list of rows (each with an ``evidence_id`` + ``direct_quote``/``statement``) or a
    dict already keyed by evidence-id. FAIL LOUD on anything else.
    """
    if isinstance(raw, dict):
        pool = {str(k): v for k, v in raw.items() if isinstance(v, dict)}
        if pool:
            return pool
    if isinstance(raw, list):
        pool = {}
        for row in raw:
            if isinstance(row, dict):
                eid = row.get("evidence_id")
                if eid:
                    pool[str(eid)] = row
        if pool:
            return pool
    raise S6RunnerError(
        "evidence pool has an unrecognized shape (expected a list of rows with 'evidence_id' + "
        "'direct_quote'/'statement', or a dict keyed by evidence-id)"
    )


def _pool_from_container(container: Any) -> Any | None:
    if not isinstance(container, dict):
        return None
    for key in ("evidence_for_gen", "evidence_pool", "evidence"):
        raw = container.get(key)
        if raw:
            return raw
    payload = container.get("payload")
    if isinstance(payload, dict):
        for key in ("evidence_for_gen", "evidence_pool", "evidence"):
            raw = payload.get(key)
            if raw:
                return raw
    return None


def _resolve_evidence_pool(
    cp5: dict[str, Any], corpus_arg: str | None, cp5_path: Path
) -> tuple[dict[str, dict[str, Any]], str]:
    """Resolve the evidence pool + the source it came from (for the cp6 provenance record).

    Priority (fail-loud if none): (1) embedded in cp5; (2) explicit ``--corpus``; (3) the cp5
    ``upstream`` chain (any listed checkpoint that carries an evidence set); (4) a sibling
    ``cp2_corpus_snapshot.json`` in the cp5 run dir.
    """
    # (1) embedded in cp5 (payload or env level)
    raw = _pool_from_container(cp5)
    if raw:
        return _normalize_pool(raw), f"cp5:{cp5_path.name}"

    # (2) explicit --corpus
    if corpus_arg:
        corp = _load_json(corpus_arg)
        raw = _pool_from_container(corp)
        if raw:
            return _normalize_pool(raw), str(corpus_arg)
        raise S6RunnerError(
            f"--corpus {corpus_arg} carries no evidence_for_gen/evidence_pool"
        )

    # (3) upstream chain
    for up in cp5.get("upstream") or []:
        cpath = up.get("checkpoint") if isinstance(up, dict) else None
        if cpath and Path(cpath).exists():
            corp = _load_json(cpath)
            raw = _pool_from_container(corp)
            if raw:
                return _normalize_pool(raw), str(cpath)

    # (4) sibling cp2 corpus snapshot in the cp5 run dir
    sibling = cp5_path.parent / "cp2_corpus_snapshot.json"
    if sibling.exists():
        corp = _load_json(sibling)
        raw = _pool_from_container(corp)
        if raw:
            return _normalize_pool(raw), str(sibling)

    raise S6RunnerError(
        "could not resolve an evidence pool. cp5 embeds none; no --corpus was given; the "
        "upstream chain and the sibling cp2_corpus_snapshot.json carry none either. Pass "
        "--corpus <cp2_corpus_snapshot.json> so per-sentence spans can be verified."
    )


# ---------------------------------------------------------------------------
# Verdict labelling (LABEL-not-guts)
# ---------------------------------------------------------------------------

def _verdict_label(sv: Any) -> str:
    """Map an engine ``SentenceVerification`` to the §-1.1 per-claim verdict.

    The sentence is ALWAYS kept regardless of the label — the verdict is a disclosure signal,
    not a drop decision.
    """
    reasons = [str(r).lower() for r in (getattr(sv, "failure_reasons", None) or [])]
    judge_error = bool(getattr(sv, "judge_error", False)) or any("judge_error" in r for r in reasons)
    if getattr(sv, "is_verified", False):
        if judge_error:
            # Span-grounded yet the entailment judge failed OPEN — kept + disclosed
            # ("verifier never holds a report" rule).
            return VERDICT_UNREACHABLE
        if getattr(sv, "soft_warnings", None):
            return VERDICT_PARTIAL
        return VERDICT_VERIFIED
    # Not verified — still KEPT, labelled by why.
    if judge_error:
        return VERDICT_UNREACHABLE
    if any(marker in r for r in reasons for marker in _FABRICATED_REASON_MARKERS):
        return VERDICT_FABRICATED
    return VERDICT_UNSUPPORTED


def _sentence_record(sv: Any, sentence_index: int) -> dict[str, Any]:
    """Build one per-sentence cp6 record. KEEPS the prose (label-not-guts).

    Field names deliberately avoid the checkpoint-envelope forbidden-verdict-key set
    (``is_verified`` / ``verified`` / ``verified_text`` / ``final_verdicts`` /
    ``strict_verify_result`` / ``release_*``): ``verifier_pass`` carries the raw engine bool.
    """
    tokens = [getattr(t, "raw", str(t)) for t in (getattr(sv, "tokens", None) or [])]
    return {
        "sentence_index": sentence_index,
        "sentence_text": getattr(sv, "sentence", ""),
        "provenance_tokens": tokens,
        "verdict": _verdict_label(sv),
        "verifier_pass": bool(getattr(sv, "is_verified", False)),
        "failure_reasons": list(getattr(sv, "failure_reasons", None) or []),
        "soft_warnings": list(getattr(sv, "soft_warnings", None) or []),
        "certainty_label": str(getattr(sv, "certainty_label", "") or ""),
        "credibility_weight": getattr(sv, "credibility_weight", None),
        "independent_origin_count": getattr(sv, "independent_origin_count", None),
        # ALWAYS true: S6 is DROP->LABEL. This stage never deletes a sentence.
        "kept": True,
    }


# ---------------------------------------------------------------------------
# Core: verify one section, then the whole snapshot
# ---------------------------------------------------------------------------

def _verify_section(
    section: dict[str, Any], pool: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    sentences = split_into_sentences(section["draft_text"])
    records: list[dict[str, Any]] = []
    for i, sentence in enumerate(sentences):
        sv = verify_sentence_provenance(sentence, pool, require_number_match=True)
        records.append(_sentence_record(sv, i))
    counts: dict[str, int] = {}
    for rec in records:
        counts[rec["verdict"]] = counts.get(rec["verdict"], 0) + 1
    verified = sum(1 for r in records if r["verifier_pass"])
    return {
        "section_index": section["section_index"],
        "section_id": section["section_id"],
        "title": section["title"],
        "sentence_count": len(records),
        "kept_count": len(records),  # == sentence_count by construction (nothing dropped)
        "by_verdict": counts,
        # DISCLOSURE ONLY — never a drop gate. No section is thinned on this fraction.
        "verified_fraction": (verified / len(records)) if records else 0.0,
        "sentences": records,
    }


def run_cp5_to_cp6(
    cp5_path: str | Path, corpus_arg: str | None = None, out_path: str | Path | None = None
) -> Path:
    """Read cp5, verify every sentence (LABEL-not-guts), write cp6. Returns the cp6 path."""
    cp5_path = Path(cp5_path)
    cp5 = _load_json(cp5_path)
    if not isinstance(cp5, dict):
        raise S6RunnerError(f"cp5 at {cp5_path} is not a JSON object")

    drafts = _extract_section_drafts(cp5)
    pool, pool_source = _resolve_evidence_pool(cp5, corpus_arg, cp5_path)

    sections = [_verify_section(sec, pool) for sec in drafts]

    total = sum(s["sentence_count"] for s in sections)
    kept = sum(s["kept_count"] for s in sections)
    if kept != total:  # invariant: DROP->LABEL keeps every sentence
        raise S6RunnerError(
            f"internal invariant broken: kept {kept} != total {total} sentences. S6 must NEVER "
            "drop a sentence (label-not-guts)."
        )
    by_verdict: dict[str, int] = {}
    for s in sections:
        for verdict, n in s["by_verdict"].items():
            by_verdict[verdict] = by_verdict.get(verdict, 0) + n
    verified = by_verdict.get(VERDICT_VERIFIED, 0) + by_verdict.get(VERDICT_PARTIAL, 0)

    cp5_sha = _sha256_file(cp5_path)
    upstream = [{"stage": "s5_compose", "checkpoint": str(cp5_path), "sha": cp5_sha}]
    if pool_source and not pool_source.startswith("cp5:") and Path(pool_source).exists():
        upstream.append(
            {"stage": "corpus", "checkpoint": pool_source, "sha": _sha256_file(pool_source)}
        )

    envelope: dict[str, Any] = {
        "schema_version": CP6_SCHEMA_VERSION,
        "stage": S6_STAGE,
        "question_sha": cp5.get("question_sha"),
        "run_config_sha": cp5.get("run_config_sha"),
        "flag_slate": _capture_flag_slate(),
        "upstream": upstream,
        "evidence_pool_source": pool_source,
        "evidence_pool_size": len(pool),
        "faithfulness_invariant": (
            "cp6 is the S6 VERIFY OUTPUT: it carries this stage's per-sentence verdict LABELS "
            "(the product of the faithfulness engine), NOT a replayed upstream decision. "
            "DROP->LABEL+REPAIR: EVERY composed sentence is kept and labelled "
            "(VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE) with the raw engine bool + "
            "reasons; NOTHING is dropped or thinned (kept_count == sentence_count everywhere). "
            "Faithfulness is CONTEXT-LEVEL: NLI entailment (PG_STRICT_VERIFY_ENTAILMENT) + strict "
            "numeric match (require_number_match=True); the lexical overlap ghost is not depended "
            "on. The verify engine (strict_verify / provenance_generator) is UNCHANGED; prose "
            "repair is owned by the compose loop, not this runner. Question/RunConfig-driven; no "
            "corpus-tuned constant, no cap/target/thinner."
        ),
        "stats": {
            "sections": len(sections),
            "total_sentences": total,
            "kept_sentences": kept,
            "dropped_sentences": 0,
            "by_verdict": by_verdict,
            # DISCLOSURE ONLY — reported so a reader sees grounding strength; NEVER a gate.
            "verified_fraction": (verified / total) if total else 0.0,
        },
        "deferred_downstream_wps": [
            "Live context-level NLI entailment fires only when PG_STRICT_VERIFY_ENTAILMENT != off "
            "(warn/enforce); off = mechanical provenance + strict-numeric labels only.",
            "PROSE REPAIR of weak/unsupported sentences is owned by the compose loop "
            "(verified_compose / multi_section_generator), NOT this thin runner.",
            "S7 RENDER consumes cp6 labels to present weak claims as weak (confidence badges / "
            "disclosure), rather than dropping them.",
        ],
        "payload": {"sections": sections},
    }

    if out_path is None:
        out_path = cp5_path.parent / CP6_FILENAME
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="S6 VERIFY thin checkpoint runner (cp5 -> cp6): label-not-guts per-sentence "
        "faithfulness verdicts."
    )
    parser.add_argument(
        "--cp5", required=True, help="path to cp5_generation_snapshot.json (the S5 compose checkpoint)"
    )
    parser.add_argument(
        "--corpus",
        default=None,
        help="optional path to cp2_corpus_snapshot.json (evidence pool) if cp5 does not embed one",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="optional cp6 output path (default: <cp5 dir>/cp6_postverify_checkpoint.json)",
    )
    args = parser.parse_args(argv)

    out = run_cp5_to_cp6(args.cp5, corpus_arg=args.corpus, out_path=args.out)
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    stats = data["stats"]
    print(f"WROTE {out} bytes={Path(out).stat().st_size}")
    print(f"cp6_sha={_sha256_file(out)[:16]}")
    print(
        "sections={sections} total_sentences={total_sentences} kept={kept_sentences} "
        "dropped={dropped_sentences}".format(**stats)
    )
    print(f"by_verdict={json.dumps(stats['by_verdict'])}")
    print(f"verified_fraction={stats['verified_fraction']:.4f} (disclosure only, NOT a gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
