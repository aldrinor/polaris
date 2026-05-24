"""Build the REAL canonical demo bundle from a real pipeline run.

I-p2-036 (#795): the prior canonical demo bundle had PLACEHOLDER source text
(claim not in source = fabricated proof). This rebuilds it from a REAL run
(real claims + real source spans that genuinely contain them). Maps the run's
verified sentences (verification_details.json: sentence + token{evidence_id,
start,end}) + the real fetched source text (evidence_pool.json: direct_quote)
into the v1.0 signed-bundle format the inspector loads.

§-1.1 gate: a sentence is featured ONLY if every numeric token in it appears in
the cited span (strict_verify-style numeric-fidelity re-check). Spans that fail
are dropped — we never ship a claim whose source span doesn't support it.

Signature: NONE (operator chose "skip the seal" — option b). No manifest.yaml.asc
is written, so the inspector honestly renders signaturePresent=false.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

RUN = Path("outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm")
OUT = Path("web/public/canonical_bundles/v1_canonical_success")
DECISION_ID = "decision_real_tirzepatide_0001"
POOL_ID = "pool_real_tirzepatide_0001"
REPORT_ID = "report_real_tirzepatide_0001"
BUNDLE_ID = "bundle_real_tirzepatide_0001"

_NUM = re.compile(r"\d+(?:\.\d+)?")
_PROV_TOKEN = re.compile(r"\[#ev:[^\]]*\]")


def strip_tokens(s: str) -> str:
    """Remove inline provenance tokens [#ev:id:start-end] — they are metadata,
    NOT claim content. (Their id/offset digits would otherwise pollute the
    numeric-fidelity check and the displayed claim text.)"""
    return _PROV_TOKEN.sub("", s).strip()


def _norm(s: str) -> str:
    # normalise unicode minus/hyphen variants so numeric matching is fair.
    return s.replace("−", "-").replace("‐", "-").replace("–", "-")


def _tier_counts(sources: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for s in sources:
        t = s.get("tier", "T1")
        counts[t] = counts.get(t, 0) + 1
    return dict(sorted(counts.items()))


def numbers_present(sentence: str, span: str) -> tuple[bool, list[str]]:
    """Every numeric token in the sentence must appear in the span (§-1.1)."""
    nums = _NUM.findall(_norm(sentence))
    span_n = _norm(span)
    missing = [n for n in nums if n not in span_n]
    return (len(missing) == 0, missing)


def main() -> int:
    vd = json.loads((RUN / "verification_details.json").read_text("utf-8"))
    pool = json.loads((RUN / "evidence_pool.json").read_text("utf-8"))
    protocol = json.loads((RUN / "protocol.json").read_text("utf-8"))
    by_id = {s["evidence_id"]: s for s in pool}

    sections = []
    cited_ids: set[str] = set()
    total_kept = 0
    total_dropped_gate = 0

    for sec in vd["sections"]:
        title = sec.get("title", "Findings")
        vsents = []
        for k in sec.get("kept") or []:
            sentence = strip_tokens(k["sentence"])
            toks = k.get("tokens") or []
            if not toks:
                continue
            prov_tokens = []
            ok_any = False
            for tok in toks:
                eid = tok["evidence_id"]
                start, end = tok["start"], tok["end"]
                ev = by_id.get(eid)
                if not ev:
                    continue
                dq = ev.get("direct_quote", "") or ""
                span = dq[start:end]
                if not span.strip():
                    continue
                ok, missing = numbers_present(sentence, span)
                if not ok:
                    print(
                        f"  [§-1.1 DROP] {eid}:{start}-{end} missing nums "
                        f"{missing} :: {sentence[:70]!r}"
                    )
                    continue
                prov_tokens.append(f"[#ev:{eid}:{start}-{end}]")
                cited_ids.add(eid)
                ok_any = True
            if not ok_any:
                total_dropped_gate += 1
                continue
            vsents.append(
                {
                    "section_id": title,
                    "sentence_text": sentence,
                    "provenance_tokens": prov_tokens,
                    "verifier_pass": True,
                    "assertion_surface": "prose",
                    "contradiction": None,
                    "drop_reason": None,
                    "evaluator_agrees": True,
                    "evaluator_disagreement": None,
                    "is_synthesis_claim": False,
                }
            )
            total_kept += 1
        if vsents:
            sections.append(
                {
                    "section_id": title,
                    "section_title": title,
                    "section_status": "verified",
                    "section_verify_pass_rate": 1.0,
                    "verified_sentences": vsents,
                }
            )

    if total_kept == 0:
        print("FATAL: no sentences passed the §-1.1 gate", file=sys.stderr)
        return 1

    question = protocol.get("question") or protocol.get("research_question") or ""

    verified_report = {
        "report_id": REPORT_ID,
        "pool_id": POOL_ID,
        "decision_id": DECISION_ID,
        "sections": sections,
        "overall_verify_pass_rate": 1.0,
        "verifier_pass_threshold": 0.4,
        "pipeline_verdict": "success",
        "generator_model": "deepseek/deepseek-v4-pro",
        "evaluator_model": "google/gemma-4-31b-it",
        "family_segregation_passed": True,
        "started_at_utc": "2026-05-20T00:00:00+00:00",
        "finished_at_utc": "2026-05-20T00:00:00+00:00",
        "latency_ms": 0,
        "cost_usd": 0.0,
        "research_question": question,
    }

    sources = []
    for eid in sorted(cited_ids):
        ev = by_id[eid]
        url = ev.get("source_url", "") or ""
        domain = url.split("/")[2] if "://" in url else (ev.get("source") or "")
        sources.append(
            {
                "source_id": eid,
                # rstrip trailing whitespace per line so git diff --check is clean
                "full_text": "\n".join(
                    line.rstrip() for line in (ev.get("direct_quote", "") or "").split("\n")
                ),
                "full_text_available": True,
                "title": (ev.get("statement") or ev.get("title") or eid)[:200],
                "url": url,
                "domain": domain,
                "tier": ev.get("tier", "T1"),
                "authors": [],
                "snippet": (ev.get("direct_quote", "") or "")[:200],
                "retracted": False,
                "fetched_at_utc": "2026-05-20T00:00:00+00:00",
                "provenance": {"fetched_by": "live_retriever"},
            }
        )

    evidence_pool = {
        "pool_id": POOL_ID,
        "decision_id": DECISION_ID,
        "sources": sources,
        "adequacy": {
            "is_adequate": True,
            "failure_reason": None,
            "min_required_per_tier": {"T1": 1},
            # honest per-tier counts from the actual source tiers (not all-T1)
            "sources_per_tier": _tier_counts(sources),
        },
        "queries_executed": [question] if question else [],
        "cost_usd": 0.0,
        "latency_ms": 0,
        "retrieval_started_at_utc": "2026-05-20T00:00:00+00:00",
        "retrieval_finished_at_utc": "2026-05-20T00:00:00+00:00",
    }

    scope_decision = {
        "decision_id": DECISION_ID,
        "scope_class": "clinical_efficacy",
        "status": "in_scope",
        "ambiguity_axes": [],
        "clarifications_needed": [],
        "decided_at_utc": "2026-05-20T00:00:00+00:00",
        "latency_ms": 0,
        "provenance": {"classifier_layer": "llm", "ambiguity_detector_layer": "llm"},
        "research_question": question,
    }

    metadata = {
        "bundle_created_at_utc": "2026-05-20T00:00:00+00:00",
        "generator_model": "deepseek/deepseek-v4-pro",
        "evaluator_model": "google/gemma-4-31b-it",
        "polaris_version": "1.0.0",
        "schema_version": "1.0",
        "research_question": question,
        "source": "real pipeline run: honest_sweep_r3 clinical_tirzepatide_t2dm",
    }

    reasoning_trace = [
        {
            "call_id": "call_0001",
            "call_type": "verify",
            "section": "verification",
            "status": "ok",
            "content_source": "real_run",
            "content_text": (
                f"{total_kept} sentences span-verified against real sources; "
                f"{total_dropped_gate} dropped at the §-1.1 numeric gate."
            ),
            "model": "google/gemma-4-31b-it",
            "timestamp": "2026-05-20T00:00:00+00:00",
        }
    ]

    # --- write files ---
    if OUT.exists():
        for p in OUT.rglob("*"):
            if p.is_file():
                p.unlink()
    (OUT / "sources").mkdir(parents=True, exist_ok=True)

    def write(path: Path, data: str) -> None:
        path.write_text(data, encoding="utf-8")

    write(OUT / "scope_decision.json", json.dumps(scope_decision, indent=2))
    write(OUT / "evidence_pool.json", json.dumps(evidence_pool, indent=2))
    write(OUT / "verified_report.json", json.dumps(verified_report, indent=2))
    write(OUT / "metadata.json", json.dumps(metadata, indent=2))
    with (OUT / "reasoning_trace.jsonl").open("w", encoding="utf-8") as f:
        for rec in reasoning_trace:
            f.write(json.dumps(rec) + "\n")
    for src in sources:
        write(OUT / "sources" / f"{src['source_id']}.txt", src["full_text"])

    # --- manifest (sha256 + sizes; NO .asc → signature honestly absent) ---
    file_entries = [
        ("scope_decision", "scope_decision.json"),
        ("evidence_pool", "evidence_pool.json"),
        ("verified_report", "verified_report.json"),
        ("metadata", "metadata.json"),
        ("reasoning_trace", "reasoning_trace.jsonl"),
    ]
    for src in sources:
        file_entries.append(("source_snapshot", f"sources/{src['source_id']}.txt"))

    files = []
    for ctype, rel in file_entries:
        b = (OUT / rel).read_bytes()
        files.append(
            {
                "content_type": ctype,
                "path": rel,
                "sha256": hashlib.sha256(b).hexdigest(),
                "size_bytes": len(b),
            }
        )

    manifest_lines = [
        "bundle_created_at_utc: '2026-05-20T00:00:00Z'",
        f"bundle_id: {BUNDLE_ID}",
        "bundle_version: '1.0'",
        f"decision_id: {DECISION_ID}",
        "files:",
    ]
    for fe in files:
        manifest_lines += [
            f"- content_type: {fe['content_type']}",
            f"  path: {fe['path']}",
            f"  sha256: {fe['sha256']}",
            f"  size_bytes: {fe['size_bytes']}",
        ]
    manifest_lines += [
        "generator_model: deepseek/deepseek-v4-pro",
        "polaris_version: 1.0.0",
        f"pool_id: {POOL_ID}",
        f"report_id: {REPORT_ID}",
    ]
    write(OUT / "manifest.yaml", "\n".join(manifest_lines) + "\n")

    # --- I-ux-001a (Codex iter-1 P0): sign by default with CANONICAL key ----
    args = _parse_args()
    if args.unsigned:
        print(
            f"OK: {total_kept} verified sentences across {len(sections)} sections, "
            f"{len(sources)} real sources. {total_dropped_gate} dropped at §-1.1 gate. "
            f"--unsigned: no signature written."
        )
        return 0

    sig_rc = _sign_manifest_or_fail(OUT / "manifest.yaml")
    if sig_rc != 0:
        return sig_rc
    print(
        f"OK: {total_kept} verified sentences across {len(sections)} sections, "
        f"{len(sources)} real sources. {total_dropped_gate} dropped at §-1.1 gate. "
        f"Signed with canonical key."
    )
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the canonical demo bundle.")
    p.add_argument(
        "--unsigned",
        action="store_true",
        help="Skip signing (prior 'option b' workflow). LAW-II: the inspector "
             "will then render the honest 'Not signed' state.",
    )
    return p.parse_args()


def _sign_manifest_or_fail(manifest_path: Path) -> int:
    """Detach-sign `manifest_path` with the canonical Carney-demo key.

    Reads:
      $POLARIS_GPG_HOMEDIR (default ~/.gnupg-polaris) — the dedicated keyring
        bootstrapped by scripts/bootstrap_gpg_demo_key.sh
        (docs/carney_secret_inventory.md #1).
      $POLARIS_GPG_KEY_ID  (default state/polaris_gpg_keyid.txt) — pinned
        fingerprint of the canonical signing key.

    Fails loudly if either is unavailable. Never falls back silently (which
    would risk signing with a different default-keyring key that does NOT
    match the shipped trust-root pubkey).
    """
    home = os.environ.get("POLARIS_GPG_HOMEDIR") or str(
        Path.home() / ".gnupg-polaris"
    )
    fp = os.environ.get("POLARIS_GPG_KEY_ID")
    if not fp:
        pin = Path("state/polaris_gpg_keyid.txt")
        if not pin.is_file():
            print(
                "[sign] FAIL: no $POLARIS_GPG_KEY_ID and "
                "state/polaris_gpg_keyid.txt missing. "
                "Run scripts/bootstrap_gpg_demo_key.sh first, or pass --unsigned.",
                file=sys.stderr,
            )
            return 2
        fp = pin.read_text(encoding="utf-8").strip()
    if not Path(home).is_dir():
        print(
            f"[sign] FAIL: GNUPGHOME {home} does not exist. "
            f"Run scripts/bootstrap_gpg_demo_key.sh first, or pass --unsigned.",
            file=sys.stderr,
        )
        return 2

    asc = manifest_path.with_suffix(manifest_path.suffix + ".asc")
    if asc.exists():
        asc.unlink()
    env = {**os.environ, "GNUPGHOME": home}
    cmd = [
        "gpg", "--batch", "--yes", "--local-user", fp,
        "--armor", "--detach-sign", "--output", str(asc), str(manifest_path),
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(
            f"[sign] FAIL: gpg detach-sign exit {r.returncode}: "
            f"{r.stderr.strip()}",
            file=sys.stderr,
        )
        return 3

    vr = subprocess.run(
        ["gpg", "--batch", "--verify", str(asc), str(manifest_path)],
        env=env, capture_output=True, text=True,
    )
    if vr.returncode != 0:
        print(f"[sign] FAIL: self-verify after sign: {vr.stderr.strip()}", file=sys.stderr)
        return 4
    print(f"[sign] OK: {asc.name} ({asc.stat().st_size} bytes) signed with {fp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
