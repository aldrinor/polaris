#!/usr/bin/env python3
"""S6 VERIFY — offline DROP -> LABEL + REPAIR harness (operator UNFREEZE 2026-07-10).

Runs a handful of FIXTURE sentences (built from a tiny in-memory evidence pool — NOT the
live corpus; that is the later VM hamster) through the real
``strict_verify.verify_sentence_to_record`` seam under the policy OFF and then ON, and
prints ONE line per sentence so a §-1.1 reader can read the KEEP / LABEL / REPAIR / DROP
decision line-by-line. It then builds and writes a ``cp6_postverify_checkpoint.json`` to a
temp dir and prints the rollup.

No network, no LLM, no paid call: the entailment judge is forced OFF and the default
repair mode is the deterministic hedge. Runnable as:

    python scripts/section_harness/s6_verify_label_repair_harness.py

Exit 0 iff the contract holds (OFF drops; ON label-keeps the eligible reasons and still
drops the fatal ones; cp6 writes).
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Make ``src`` importable when run from the repo root.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.polaris_graph.clinical_generator import verify_label_repair as lr  # noqa: E402
from src.polaris_graph.clinical_generator.strict_verify import (  # noqa: E402
    verify_sentence_to_record,
)
from src.polaris_graph.clinical_retrieval.evidence_pool import (  # noqa: E402
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


def _src(source_id: str, full_text: str) -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet",
        full_text=full_text,
        full_text_available=True,
        source_id=source_id,
    )


def _pool(*sources: Source) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=list(sources),
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _tok(source_id: str, text: str) -> str:
    return f"[#ev:{source_id}:0-{len(text)}]"


# (label, expected-fatal?, sentence, pool) fixtures spanning eligible + fatal reasons.
_OVERLAP_SPAN = "Xylophone zenith orbit."
_QUAL_SPAN = "Some estimates suggest 46.5 percent of tasks are affected."
_NUM_SPAN = "Aspirin reduced cardiovascular events in adults overall."

_CASES = [
    (
        "overlap_too_low (eligible)",
        f"Aspirin helps patients. {_tok('s-ovl', _OVERLAP_SPAN)}",
        _pool(_src("s-ovl", _OVERLAP_SPAN)),
    ),
    (
        "binding_qualifier_dropped (eligible+repair)",
        f"Affected tasks reach 46.5 percent. {_tok('s-qual', _QUAL_SPAN)}",
        _pool(_src("s-qual", _QUAL_SPAN)),
    ),
    (
        "numeric_mismatch (FATAL)",
        f"Aspirin reduced events by 12.7 percent. {_tok('s-num', _NUM_SPAN)}",
        _pool(_src("s-num", _NUM_SPAN)),
    ),
    (
        "no_provenance_token (FATAL)",
        "Aspirin works in adults.",
        _pool(_src("s-x", "x" * 50)),
    ),
]


def _decide(sentence: str, pool: EvidencePool):
    rec = verify_sentence_to_record(sentence, "sec-1", pool)
    if rec.verifier_pass and rec.kept_disclosure_label:
        kind = "REPAIR" if rec.kept_disclosure_label.endswith("_repaired") else "LABEL"
    elif rec.verifier_pass:
        kind = "KEEP"
    else:
        kind = "DROP"
    return rec, kind


def main() -> int:
    # Hermetic: no judge, deterministic repair.
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "off"

    print("=" * 78)
    print("S6 DROP -> LABEL + REPAIR harness (offline fixture)")
    print("=" * 78)

    print("\n--- policy OFF (PG_STRICT_VERIFY_LABEL_REPAIR unset) — expect all DROP ---")
    os.environ.pop("PG_STRICT_VERIFY_LABEL_REPAIR", None)
    off_ok = True
    for name, sentence, pool in _CASES:
        rec, kind = _decide(sentence, pool)
        print(f"  [{kind:6}] {name:42} drop_reason={rec.drop_reason}")
        off_ok = off_ok and (kind == "DROP")

    print("\n--- policy ON (hedge repair) — expect eligible KEPT, fatal DROPPED ---")
    os.environ["PG_STRICT_VERIFY_LABEL_REPAIR"] = "1"
    os.environ["PG_STRICT_VERIFY_REPAIR_MODE"] = "hedge"
    records: list[lr.Cp6SentenceRecord] = []
    on_ok = True
    for name, sentence, pool in _CASES:
        rec, kind = _decide(sentence, pool)
        fatal = "FATAL" in name
        label = rec.kept_disclosure_label
        print(
            f"  [{kind:6}] {name:42} label={label} "
            f"text='{rec.sentence_text[:60]}'"
        )
        if fatal:
            on_ok = on_ok and (kind == "DROP")
        else:
            on_ok = on_ok and (kind in ("LABEL", "REPAIR"))
        records.append(
            lr.Cp6SentenceRecord(
                section_id="sec-1",
                sentence_text=rec.sentence_text,
                kept=rec.verifier_pass,
                drop_reason=rec.drop_reason,
                disclosure_label=rec.kept_disclosure_label,
                repaired=bool(label and label.endswith("_repaired")),
                provenance_tokens=list(rec.provenance_tokens),
            )
        )

    print("\n--- cp6 checkpoint (DATA-only accounting) ---")
    payload = lr.build_cp6_postverify_payload(
        run_id="harness-run", question="Fixture question?", records=records,
        evidence_ids=["s-ovl", "s-qual", "s-num"],
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = lr.write_cp6_postverify_checkpoint(tmp, payload)
        cp6_ok = out is not None and out.name == lr.CP6_FILENAME
        print(f"  wrote: {out}")
        print(f"  rollup: {payload['rollup']}")

    ok = off_ok and on_ok and cp6_ok
    print("\n" + ("PASS" if ok else "FAIL") + f"  (off={off_ok} on={on_ok} cp6={cp6_ok})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
