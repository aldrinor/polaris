"""S6 VERIFY — DROP -> LABEL + REPAIR policy (operator UNFREEZE 2026-07-10).

Master execution plan S6 row + OPERATOR_SECTION_DIRECTIVES §S6: the faithfulness
engine is UNFROZEN. The silent per-sentence DROP that ``strict_verify`` performs
on an unverified sentence is rewired to **LABEL + REPAIR** — keep the sentence in
the report with a visible confidence label (and, where safe, an NLI/hedge repair),
instead of deleting it. This preserves the grounding / provenance SIGNAL (the label
IS the signal) while killing the thin-report backfire where dropping otherwise-fine
sentences empties a section.

This is the operator's own ``feedback_always_release_verifier_labels_never_holds``
rule made concrete at the strict_verify seam: *the verifier labels weak claims weak,
it never silently guts the report.* It mirrors the EXISTING judge-error always-release
path in ``strict_verify.verify_sentence`` (which already returns
``(True, "entailment_unverified_judge_error")`` and ships the caveat in
``VerifiedSentence.kept_disclosure_label``) — this module generalizes that one special
case into a governed policy.

CLINICAL-SAFETY BOUNDARY (§-1.1, lethal-in-clinical — this is the load-bearing rule).
Not every drop is a "weak claim". A claim the evidence actively CONTRADICTS, or one
that cites a non-existent source, or one with no grounding at all, is not weak — it is
WRONG or FABRICATED, and shipping it with a small label would hurt a patient. So the
drop-reason set is split:

  * LABEL-ELIGIBLE (default): the sentence IS grounded (valid evidence-id, in-bounds
    span) and its numbers match the cited span — only the *soft* grounding signal is
    weak. Keep it, label it, repair it. Default set:
        - overlap_too_low          (grounded numerically, lexically thin)
        - unsegmentable_script     (grounded, non-Latin script we cannot segment)
        - binding_qualifier_dropped(number matches; a hedge was dropped -> re-attach it)
  * FATAL (never label-kept; faithfulness NOT relaxed): everything else stays a DROP
    exactly as today —
        - invalid_token / span_out_of_range   (fabricated / malformed citation)
        - no_provenance_token / empty_or_contentless_sentence (nothing to ground)
        - numeric_mismatch / percent_not_in_cited_span (an unsupported NUMBER — a wrong
          dose is lethal; never ship on a label)
        - entailment_failed (the semantic judge said NEUTRAL/CONTRADICTED — the
          strongest "possibly wrong" signal)

The LABEL-ELIGIBLE set is a config, not a baked constant
(``PG_STRICT_VERIFY_LABEL_REPAIR_REASONS``), so the later live hamster can widen or
narrow it empirically WITHOUT a code change (§-1.3 weight-not-hardcode discipline).

EVERYTHING here is default-OFF and byte-identical when
``PG_STRICT_VERIFY_LABEL_REPAIR`` is unset/0 — a run with the flag off drops exactly
what it dropped before. LAW VI: every knob reads through an env helper at call time;
no hardcoded thresholds. When the WAVE-0 ``run_config`` resolver lands, each helper
swaps its ``os.getenv`` for ``run_config.get`` at the same call site (master §1.5).

The cp6 checkpoint (``cp6_postverify_checkpoint.json``) is DATA-ONLY per-sentence
kept/labeled/repaired/dropped accounting — it stores NO release verdict, and the
recursive forbidden-verdict-key guard mirrors the A12 checkpoint loader
(``run_honest_sweep_r3.load_a12_checkpoint``). A resume re-runs every faithfulness
gate from data; it can never replay this accounting as a decision.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Knobs (LAW VI — read at call time; resolver-ready; default-OFF byte-identical)
# ---------------------------------------------------------------------------

#: Drop-reasons that are SAFE to keep-with-label (grounded but weak). Fatal reasons
#: (fabricated citation / unsupported number / contradicted / ungrounded) are omitted
#: on purpose — see the module docstring's CLINICAL-SAFETY BOUNDARY.
DEFAULT_LABEL_ELIGIBLE_REASONS: frozenset[str] = frozenset(
    {
        "overlap_too_low",
        "unsegmentable_script",
        "binding_qualifier_dropped",
    }
)

#: Repair modes for ``PG_STRICT_VERIFY_REPAIR_MODE``.
#:   off   -> label only, sentence text unchanged.
#:   hedge -> deterministic, offline: re-attach a source-attribution hedge lead-in so a
#:            certainty-distorted claim ("46%") ships as an attributed one ("According
#:            to the cited evidence, 46%"). No LLM, so it is safe in an offline harness.
#:   nli   -> call an injected ``repair_fn`` (the live mirror re-grounder) and re-verify;
#:            when no ``repair_fn`` is supplied it FALLS BACK to hedge (never crashes,
#:            never silently drops). The live wiring wave supplies the governed mirror.
_VALID_REPAIR_MODES = ("off", "hedge", "nli")
_DEFAULT_REPAIR_MODE = "hedge"

#: Default source-attribution hedge lead-in for ``hedge`` repair. Overridable (LAW VI).
_DEFAULT_HEDGE_LEADIN = "According to the cited evidence,"

CP6_FILENAME = "cp6_postverify_checkpoint.json"
CP6_STAGE = "post_verification_label_repair"
CP6_SCHEMA_VERSION = 1

#: Verdict keys a DATA-ONLY checkpoint may NEVER contain (mirrors the A12 loader guard
#: in ``run_honest_sweep_r3._A12_FORBIDDEN_VERDICT_KEYS``). If any appears at ANY depth
#: a release decision leaked in and the payload is rejected (fail loud).
_FORBIDDEN_VERDICT_KEYS: frozenset[str] = frozenset(
    {
        "release_outcome",
        "release_allowed",
        "released",
        "verified",
        "is_verified",
        "final_verdicts",
        "d8_decision",
        "four_role_evaluation",
    }
)


def label_repair_enabled() -> bool:
    """Master switch. False (DEFAULT) => byte-identical silent-DROP behavior; the whole
    LABEL+REPAIR policy is inert. PG_STRICT_VERIFY_LABEL_REPAIR in {1,true,yes,on}."""
    v = os.environ.get("PG_STRICT_VERIFY_LABEL_REPAIR", "0").strip().lower()
    return v in ("1", "true", "yes", "on", "enabled")


def label_eligible_reasons() -> frozenset[str]:
    """The active LABEL-ELIGIBLE drop-reason set. LAW VI:
    PG_STRICT_VERIFY_LABEL_REPAIR_REASONS (comma-separated) overrides the curated
    default; an empty / all-blank override falls back to the default rather than
    silently disabling the policy. A reason NOT in this set stays a FATAL DROP."""
    raw = os.environ.get("PG_STRICT_VERIFY_LABEL_REPAIR_REASONS", "").strip()
    if not raw:
        return DEFAULT_LABEL_ELIGIBLE_REASONS
    items = frozenset(part.strip() for part in raw.split(",") if part.strip())
    return items or DEFAULT_LABEL_ELIGIBLE_REASONS


def repair_mode() -> str:
    """One of 'off' | 'hedge' | 'nli' (default 'hedge'). Unknown values map to the
    default. Read at call time so tests can override."""
    raw = os.environ.get("PG_STRICT_VERIFY_REPAIR_MODE", _DEFAULT_REPAIR_MODE).strip().lower()
    return raw if raw in _VALID_REPAIR_MODES else _DEFAULT_REPAIR_MODE


def _hedge_leadin() -> str:
    """Source-attribution hedge lead-in for ``hedge`` repair (LAW VI). An empty
    override falls back to the default so repair can never emit a bare comma."""
    raw = os.environ.get("PG_STRICT_VERIFY_REPAIR_HEDGE", "").strip()
    return raw or _DEFAULT_HEDGE_LEADIN


# ---------------------------------------------------------------------------
# Confidence labels — the per-sentence grounding SIGNAL preserved on a KEPT sentence
# ---------------------------------------------------------------------------

#: drop_reason -> the confidence label carried in VerifiedSentence.kept_disclosure_label.
#: The label is machine-parseable ("unverified_<reason>") AND human-readable; the "why"
#: is the drop-reason itself, so a §-1.1 auditor and the downstream D8 judge both see
#: exactly which grounding check was weak. A repaired sentence gets the "_repaired"
#: suffix so the accounting distinguishes label-only from label+repair.
def confidence_label(drop_reason: str, *, repaired: bool) -> str:
    base = f"unverified_{drop_reason}"
    return f"{base}_repaired" if repaired else base


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LabelRepairDecision:
    """Outcome of the policy for ONE failed-verify sentence.

    ``outcome`` is one of:
      * ``"drop"``   — policy off, OR the reason is FATAL. Byte-identical to today:
                       the caller drops the sentence (verifier_pass=False, drop_reason).
      * ``"label"``  — KEEP with a confidence label; text unchanged.
      * ``"repair"`` — KEEP with a confidence label AND a repaired sentence text.

    ``kept`` is True for label/repair, False for drop.
    """

    outcome: str
    kept: bool
    drop_reason: str
    sentence_text: str
    disclosure_label: str | None = None
    repaired: bool = False
    repair_note: str | None = None


def apply_label_repair_policy(
    sentence_text: str,
    drop_reason: str,
    span_texts: list[str] | None = None,
    *,
    repair_fn: Callable[[str, list[str], str], str] | None = None,
) -> LabelRepairDecision:
    """Decide LABEL / REPAIR / DROP for a sentence that FAILED strict_verify.

    Parameters
    ----------
    sentence_text : the original (token-bearing) sentence.
    drop_reason   : the DropReason strict_verify returned (non-None).
    span_texts    : the cited-span texts (used only by the qualifier repair; may be None).
    repair_fn     : optional live re-grounder for ``nli`` mode: (sentence, spans, reason)
                    -> repaired_sentence. When None, ``nli`` falls back to hedge.

    Contract:
      * policy OFF  -> outcome="drop" (byte-identical).
      * reason FATAL (not in label_eligible_reasons()) -> outcome="drop"
        (faithfulness NOT relaxed).
      * reason LABEL-ELIGIBLE -> outcome="label" (or "repair" when repair fires),
        kept=True, disclosure_label set, provenance tokens preserved by construction
        (the repair only PREPENDS a clause / rewrites via repair_fn; it never removes
        a ``[#ev:...]`` token).

    Fail-open: any exception inside the repair step degrades to label-only (KEEP with
    label) — a repair fault must never crash the run nor silently drop a grounded
    sentence.
    """
    if not label_repair_enabled():
        return LabelRepairDecision(
            outcome="drop", kept=False, drop_reason=drop_reason,
            sentence_text=sentence_text,
        )

    if drop_reason not in label_eligible_reasons():
        # FATAL — fabricated / unsupported-number / contradicted / ungrounded. Never
        # keep on a label. This is the clinical-safety boundary; do NOT relax it.
        return LabelRepairDecision(
            outcome="drop", kept=False, drop_reason=drop_reason,
            sentence_text=sentence_text,
        )

    mode = repair_mode()
    repaired_text = sentence_text
    repaired = False
    note: str | None = None

    if mode != "off":
        try:
            repaired_text, repaired, note = _attempt_repair(
                sentence_text, span_texts or [], drop_reason, mode, repair_fn,
            )
        except Exception as exc:  # noqa: BLE001 — fail-open: label-only, never crash/drop
            repaired_text, repaired, note = sentence_text, False, f"repair_error:{exc}"

    label = confidence_label(drop_reason, repaired=repaired)
    return LabelRepairDecision(
        outcome="repair" if repaired else "label",
        kept=True,
        drop_reason=drop_reason,
        sentence_text=repaired_text,
        disclosure_label=label,
        repaired=repaired,
        repair_note=note,
    )


def _attempt_repair(
    sentence_text: str,
    span_texts: list[str],
    drop_reason: str,
    mode: str,
    repair_fn: Callable[[str, list[str], str], str] | None,
) -> tuple[str, bool, str | None]:
    """Return (repaired_text, repaired_bool, note). PURE for hedge mode; ``nli`` mode
    delegates to ``repair_fn`` and falls back to hedge when it is absent."""
    if mode == "nli" and repair_fn is not None:
        candidate = repair_fn(sentence_text, span_texts, drop_reason)
        if isinstance(candidate, str) and candidate.strip() and candidate != sentence_text:
            # Provenance guard: a repair must never delete a provenance token.
            if _tokens_preserved(sentence_text, candidate):
                return candidate, True, "nli_regrounded"
        return sentence_text, False, "nli_noop"

    # hedge mode (also the nli fallback): re-attach a source-attribution lead-in. For
    # binding_qualifier_dropped this restores the epistemic honesty the composer stripped
    # ("46%" -> "According to the cited evidence, 46%"); for the other eligible reasons it
    # makes the weak grounding explicit in-prose in addition to the label.
    leadin = _hedge_leadin()
    if sentence_text.lstrip().lower().startswith(leadin.lower()):
        return sentence_text, False, "hedge_already_present"
    marker = _span_qualifier_marker(span_texts) if drop_reason == "binding_qualifier_dropped" else None
    repaired = f"{leadin} {sentence_text.lstrip()}"
    return repaired, True, (f"hedge_leadin;span_marker={marker}" if marker else "hedge_leadin")


def _tokens_preserved(original: str, repaired: str) -> bool:
    """True iff every provenance token in ``original`` still appears in ``repaired``.
    Lazy import keeps this module free of an import cycle with strict_verify/provenance."""
    from src.polaris_graph.clinical_generator.provenance import extract_tokens  # noqa: PLC0415

    orig = {t.raw for t in extract_tokens(original)}
    rep = {t.raw for t in extract_tokens(repaired)}
    return orig.issubset(rep)


def _span_qualifier_marker(span_texts: list[str]) -> str | None:
    """First epistemic marker phrase found in any cited span, using the SAME lexicon the
    strict_verify qualifier gate uses (LAW VI: PG_STRICT_VERIFY_QUALIFIER_LEXICON). Lazy
    import breaks the strict_verify<->this cycle. Best-effort; None on any failure."""
    try:
        from src.polaris_graph.clinical_generator.strict_verify import (  # noqa: PLC0415
            _qualifier_lexicon,
            _qualifier_marker_re,
        )

        marker_re = _qualifier_marker_re(_qualifier_lexicon())
        for span in span_texts:
            m = marker_re.search(span or "")
            if m is not None:
                return m.group(0)
    except Exception:  # noqa: BLE001 — disclosure hint only; never abort the repair
        return None
    return None


# ---------------------------------------------------------------------------
# cp6 checkpoint — DATA-ONLY per-sentence kept/labeled/repaired/dropped accounting
# ---------------------------------------------------------------------------

@dataclass
class Cp6SentenceRecord:
    """One row of the cp6 accounting. DATA ONLY — no verdict."""

    section_id: str
    sentence_text: str
    kept: bool
    drop_reason: str | None = None
    disclosure_label: str | None = None
    repaired: bool = False
    repair_note: str | None = None
    provenance_tokens: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "sentence_text": self.sentence_text,
            "kept": bool(self.kept),
            "drop_reason": self.drop_reason,
            "disclosure_label": self.disclosure_label,
            "repaired": bool(self.repaired),
            "repair_note": self.repair_note,
            "provenance_tokens": list(self.provenance_tokens),
        }


def _stable_hash(obj: Any) -> str:
    """SHA256 over a JSON-serializable object (sorted keys). Identity fingerprint only."""
    try:
        blob = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    except Exception:  # noqa: BLE001 — a fingerprint must never abort a checkpoint
        blob = repr(obj).encode("utf-8", "replace")
    return hashlib.sha256(blob).hexdigest()


def _assert_no_forbidden_verdict_keys(obj: Any, _path: str = "$") -> None:
    """Recursively reject any forbidden verdict key at ANY depth (fail loud). Mirrors the
    A12 loader guard but recursive, per master §5 'RECURSIVE forbidden-verdict-key guard
    extended to every checkpoint'."""
    if isinstance(obj, dict):
        leaked = sorted(_FORBIDDEN_VERDICT_KEYS & set(obj.keys()))
        if leaked:
            raise ValueError(
                f"cp6 payload contains FORBIDDEN verdict key(s) {leaked} at {_path} — a "
                "checkpoint stores DATA ONLY (§-1.3); a resume re-runs every gate and can "
                "NEVER replay a stored decision."
            )
        for k, v in obj.items():
            _assert_no_forbidden_verdict_keys(v, f"{_path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_no_forbidden_verdict_keys(v, f"{_path}[{i}]")


def build_cp6_postverify_payload(
    *,
    run_id: str,
    question: str,
    records: list[Cp6SentenceRecord],
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the cp6 DATA-ONLY payload from per-sentence records. Includes the rollup
    counts, the policy snapshot (so the accounting is self-describing), and the
    faithfulness invariant marker. Raises if a forbidden verdict key ever slipped in."""
    rows = [r.to_dict() for r in records]
    rollup = {
        "total": len(rows),
        "kept": sum(1 for r in rows if r["kept"]),
        "dropped": sum(1 for r in rows if not r["kept"]),
        "labeled": sum(1 for r in rows if r["kept"] and r["disclosure_label"]),
        "repaired": sum(1 for r in rows if r["repaired"]),
    }
    payload: dict[str, Any] = {
        "stage": CP6_STAGE,
        "schema_version": CP6_SCHEMA_VERSION,
        "run_id": run_id,
        "question": question,
        "label_repair": {
            "enabled": label_repair_enabled(),
            "eligible_reasons": sorted(label_eligible_reasons()),
            "repair_mode": repair_mode(),
        },
        "sentences": rows,
        "rollup": rollup,
        "evidence_id_hash": _stable_hash(sorted(evidence_ids or [])),
        "faithfulness_invariant": (
            "DATA ONLY; no D8/release verdict stored; every KEPT-with-label sentence is a "
            "disclosed weak-grounding signal, not a pass; a resume MUST re-run every "
            "faithfulness gate (strict_verify / NLI / 4-role / D8) from scratch."
        ),
    }
    _assert_no_forbidden_verdict_keys(payload)
    return payload


def write_cp6_postverify_checkpoint(
    run_dir: str | Path, payload: dict[str, Any]
) -> Path | None:
    """Atomically write ``cp6_postverify_checkpoint.json`` (temp + os.replace, sorted
    keys). Best-effort: a write failure must NOT abort a paid run — returns None. Re-runs
    the forbidden-verdict-key guard before writing (defense in depth)."""
    try:
        _assert_no_forbidden_verdict_keys(payload)
        run_dir = Path(run_dir)
        final = run_dir / CP6_FILENAME
        tmp = run_dir / f".{CP6_FILENAME}.tmp"
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, final)
        return final
    except ValueError:
        # A leaked verdict key is a HARD contract breach — re-raise (fail loud).
        raise
    except Exception:  # noqa: BLE001 — durability is best-effort, never a run blocker
        return None


def build_cp6_records_from_verif_details(
    verif_details: dict[str, Any],
) -> list[Cp6SentenceRecord]:
    """Map the existing per-sentence ``verif_details`` accounting (the shape
    ``write_postverify_checkpoint`` already persists, i.e. ``{"sections": [{"section_id",
    "verified_sentences": [{...}]}]}``) into cp6 records. Defensive: unknown shapes are
    skipped, never crashed on — cp6 is best-effort accounting."""
    records: list[Cp6SentenceRecord] = []
    for section in verif_details.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("section_id") or section.get("section_title") or "")
        for vs in section.get("verified_sentences", []) or []:
            if not isinstance(vs, dict):
                continue
            kept = bool(vs.get("verifier_pass"))
            # A verif_details row carries no explicit "repaired" flag; infer it from the
            # label suffix the policy stamps (confidence_label(..., repaired=True)).
            lbl = vs.get("kept_disclosure_label")
            records.append(
                Cp6SentenceRecord(
                    section_id=section_id,
                    sentence_text=str(vs.get("sentence_text") or ""),
                    kept=kept,
                    drop_reason=vs.get("drop_reason"),
                    disclosure_label=lbl,
                    repaired=bool(isinstance(lbl, str) and lbl.endswith("_repaired")),
                    repair_note=None,
                    provenance_tokens=list(vs.get("provenance_tokens") or []),
                )
            )
    return records
