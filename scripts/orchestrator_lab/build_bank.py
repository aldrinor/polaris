"""Production-faithful cp3 -> S4 outline lab bank adapter (I-arch section-modular).

Builds the offline S4 hamster bank (``bank_plan.json``) from REAL cp2 + cp3 checkpoints — NO
synthetic data (LAW II). Pool = cp3 basket members enriched with the REAL cp2 corpus row
(title / statement / tier). Clusters = cp3 multi-member baskets. ``same_work_groups`` carried
straight from cp3.

Item 6a (I-arch s4-outline fix wave): bank rows now CARRY the cp2 content-integrity + topic + weight
STAMPS. The prior per-run adapter emitted only ``{evidence_id, title, statement, tier}``, DROPPING
the stamps, so the fail-open junk / off-topic / chrome predicates
(``junk_deletion_gate.is_row_deletable_offtopic`` and the content-integrity chrome predicate) could
never FIRE in the lab — a "Just a moment..." Cloudflare row or a confirmed off-topic source read as
normal evidence. Carrying the stamps lets the offline lab reproduce the production gate behaviour.
§-1.3.1: the gate KEEPS on any uncertainty (fail-open); a missing stamp is simply absent, which the
predicate reads as unjudged => KEEP.

LAW VI: all paths are CLI args (no hardcoding). There are no fixed corpus paths in this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

# item 6a: the cp2 stamp fields the fail-open junk / off-topic / chrome predicates + the weight
# channel consume (``junk_deletion_gate`` reads these exact names: content_integrity_junk /
# content_integrity_class / topic_off_subject / topic_relevance_verdict / topic_offtopic_demoted /
# content_relevance_label / deletion_reason). ``line_screen`` / ``provenance_class`` are the S2
# line-screen stamps Fable named. ``url`` / ``source_url`` help the chrome predicate. Any field that
# is present on the cp2 row is carried verbatim onto the bank row; an absent field is simply not
# added (the predicates treat a missing stamp as unjudged => KEEP, §-1.3.1 fail-open).
_STAMP_FIELDS = (
    "content_integrity_junk",
    "content_integrity_class",
    "topic_off_subject",
    "topic_relevance_verdict",
    "topic_offtopic_demoted",
    "content_relevance_label",
    "deletion_reason",
    "line_screen",
    "provenance_class",
    "url",
    "source_url",
)


def _carry_stamps(dst: dict, src: dict) -> None:
    """Copy any present stamp field from the cp2 row ``src`` onto the bank row ``dst`` (item 6a)."""
    for field in _STAMP_FIELDS:
        if field in src and src.get(field) is not None:
            dst[field] = src[field]


def build_bank(
    cp2_path: Path,
    cp3_path: Path,
    out_path: Path,
    *,
    deliverable: dict | None = None,
    scope: dict | None = None,
) -> dict:
    """Assemble the S4 bank from cp2 + cp3 and write ``out_path``. Returns the bank dict."""
    cp2 = json.loads(cp2_path.read_text(encoding="utf-8"))
    by_id = {str(r.get("evidence_id", "")): r for r in cp2.get("evidence_for_gen", [])}

    d = json.loads(cp3_path.read_text(encoding="utf-8"))
    baskets = d["payload"]["baskets"]
    same_work_groups = d["payload"].get("same_work_groups", []) or []
    question = d.get("question", "")
    domain = d.get("domain", "")
    cp3_sha = hashlib.sha256(cp3_path.read_bytes()).hexdigest()

    evidence: list[dict] = []
    index_of: dict[str, int] = {}
    missing: list[str] = []
    for b in baskets:
        for ev_id in (b.get("member_evidence_ids", []) or []):
            ev_id = str(ev_id)
            if ev_id in index_of:
                continue
            row = by_id.get(ev_id)
            if row is None:
                # cp2 row genuinely missing — carry the cp3 representative text, no synthetic fill.
                missing.append(ev_id)
                bank_row = {
                    "evidence_id": ev_id,
                    "title": str(b.get("representative_statement", "") or ""),
                    "statement": "",
                    "tier": "UNKNOWN",
                }
            else:
                bank_row = {
                    "evidence_id": ev_id,
                    "title": str(row.get("title", "") or ""),
                    "statement": str(row.get("statement", "") or ""),
                    "tier": str(row.get("tier", "") or ""),
                }
                _carry_stamps(bank_row, row)  # item 6a: real cp2 stamps flow into the lab
            index_of[ev_id] = len(evidence)
            evidence.append(bank_row)

    clusters: list[dict] = []
    for b in baskets:
        ids = [str(x) for x in (b.get("member_evidence_ids", []) or [])]
        if len(ids) < 2:
            continue
        member_indices = [index_of[i] for i in ids if i in index_of]
        rep_id = str(b.get("representative_evidence_id", "") or "")
        rep_idx = index_of.get(rep_id, member_indices[0])
        clusters.append({
            "representative_index": rep_idx,
            "member_indices": member_indices,
            "corroboration_count": len(member_indices),
            "member_hosts": list(b.get("member_hosts", []) or []),
        })

    bank = {
        "question": question,
        "domain": domain,
        "cp3_sha": cp3_sha,
        "evidence": evidence,
        "clusters": clusters,
        "same_work_groups": same_work_groups,
        "pool_ev_ids": [e["evidence_id"] for e in evidence],
    }
    if deliverable is not None:
        bank["deliverable"] = deliverable
    if scope is not None:
        bank["scope"] = scope

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")
    stamped_rows = sum(1 for e in evidence if any(f in e for f in _STAMP_FIELDS))
    print(f"wrote {out_path} bytes {out_path.stat().st_size}")
    print(f"evidence_rows {len(evidence)} clusters(multi>=2) {len(clusters)} "
          f"same_work_groups {len(same_work_groups)} missing_in_cp2 {len(missing)} "
          f"stamped_rows {stamped_rows}")
    print(f"cp3_sha {cp3_sha[:16]}")
    return bank


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="cp3 -> S4 outline lab bank adapter (carries cp2 content-integrity/topic stamps)"
    )
    p.add_argument("--cp2", required=True, type=Path, help="cp2 corpus snapshot JSON")
    p.add_argument("--cp3", required=True, type=Path, help="cp3 basket snapshot JSON")
    p.add_argument("--out", required=True, type=Path, help="bank_plan.json output path")
    p.add_argument("--deliverable", type=Path, default=None,
                   help="optional deliverable spec JSON (required_sections / tone / ...)")
    p.add_argument("--scope", type=Path, default=None, help="optional scope spec JSON")
    args = p.parse_args(argv)
    deliverable = (
        json.loads(args.deliverable.read_text(encoding="utf-8")) if args.deliverable else None
    )
    scope = json.loads(args.scope.read_text(encoding="utf-8")) if args.scope else None
    build_bank(args.cp2, args.cp3, args.out, deliverable=deliverable, scope=scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
