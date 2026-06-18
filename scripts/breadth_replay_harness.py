#!/usr/bin/env python3
"""I-arch-007 BREADTH REPLAY HARNESS - the behavioral acceptance gate for the
consolidation fix.

WHAT THIS PROVES (and what it does NOT)
---------------------------------------
The forensic finding (state/iarch007_breadth_collapse_finding.md) is: the rendered
report cites 7 of 787 visible sources and shows "Multi-source corroborated (>=2
origins): 0". The runtime log says ``[finding-dedup] raw=787 distinct=99
collapsed=0 -> 787 generator rows``. Diff-review kept missing the bug because every
phase was "green + flag-set + Codex-approved" while consolidation silently no-op'd
in the OUTPUT. This harness replays the REAL consolidation code on a banked corpus
snapshot and FAILS LOUD (non-zero exit) if consolidation is still a no-op.

THE INVERTED ASSERTION (read before editing)
--------------------------------------------
``collapsed>0`` is the WRONG acceptance signal. Under ``PG_SWEEP_CREDIBILITY_REDESIGN``
(default-ON), ``dedup_by_finding`` KEEPS ALL ROWS (CONSOLIDATE-keep-all, CLAUDE.md
§-1.3 Principle 2), so ``collapsed_row_count == 0`` BY DESIGN - the code comment
literally says "collapsed_row_count honestly becomes 0". A harness asserting
``collapsed>0`` would fail on a correctly-consolidated corpus and pass only when the
legacy DROP path runs (the bug). So this harness asserts the REAL consolidation
signal instead:

    >>> at least one finding cluster has corroboration_count >= 2

``corroboration_count`` = ``count_independent_hosts`` over registrable domains - a
genuine multi-origin signal, computed with NO LLM. It also asserts the redesign flag
is ON and ``collapsed == 0`` (proving keep-all engaged, so a regression to the legacy
drop path ALSO fails the gate).

FAITHFULNESS HARD CONSTRAINT
----------------------------
Breadth must come from CONSOLIDATING already-verified corroborators into multi-citation
baskets, NEVER from relaxing a gate. This harness touches NO faithfulness gate. It
calls the SAME pure ``dedup_by_finding`` the live run calls
(``run_honest_sweep_r3.py:8079``) with the SAME flag state and SAME corpus rows. The
fuller mode's per-member verify is the REAL ``verify_sentence_provenance`` (an LLM
entailment call) - it is never faked, because a fake verify_fn would change what passes
verification (BANNED).

THE THREE NUMBERS (keep them distinct - the checkpoints file warns of exactly this)
-----------------------------------------------------------------------------------
1. STRUCTURAL pre-verify corroboration (Tier-1, no LLM): clusters with
   ``corroboration_count >= 2``. This is the consolidation CEILING - necessary, NOT
   sufficient. Tier-1 passing does NOT prove breadth fired in the output.
2. VERIFIED multi-origin baskets (``verified_support_origin_count >= 2``): needs the
   real ``verify_fn`` (LLM). The number that reaches the report's "Multi-source
   corroborated" line.
3. DISTINCT-CITED in the rendered report (``#ev`` tokens / bibliography): the actual
   "fired in the output." Only a full render produces this - fuller mode approximates
   the ceiling, it does not re-render.

Usage
-----
    # Tier-1 (no LLM) - the hard acceptance gate every consolidation fix MUST pass:
    python scripts/breadth_replay_harness.py \
        --corpus outputs/corpus_backups/drb_75_metal_ions_cvd_corpus.tgz \
        --domain clinical --expect-rows 787

    # or point at an already-extracted snapshot dir / file:
    python scripts/breadth_replay_harness.py \
        --corpus outputs/clean_deepseek/clinical/drb_75_metal_ions_cvd/corpus_snapshot.json \
        --domain clinical

    # Fuller mode - also build the claim graph + baskets (the --baskets verify is the
    # ONE unavoidable LLM call; --no-verify reports the structural ceiling only):
    python scripts/breadth_replay_harness.py --corpus <...> --domain clinical --baskets --no-verify

Exit codes: 0 = consolidation produced >=1 multi-origin basket (gate PASS).
            2 = consolidation is a NO-OP (gate FAIL - loud).
            3 = could not load / replay (corpus missing, schema mismatch, etc.).

Pure-ish: constructs no network client in Tier-1. Fuller-mode --baskets --verify is the
only path that issues LLM calls, and only through the production verifier.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

# Project root on sys.path so ``src.polaris_graph...`` imports resolve when run as a script.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

SNAPSHOT_FILENAME = "corpus_snapshot.json"


def _eprint(*a: Any) -> None:
    # ASCII-safe on a Windows cp1252 console (box-drawing glyphs would raise).
    msg = " ".join(str(x) for x in a)
    try:
        print(msg, file=sys.stderr, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), file=sys.stderr, flush=True)


def _load_snapshot_rows(corpus: str) -> tuple[list[dict], dict]:
    """Load ``evidence_for_gen`` from a .tgz, a snapshot dir, or a snapshot .json.

    Returns (rows, payload). Fails loud (CorpusReplayError) on a missing/empty/
    version-mismatched snapshot - never silently substitutes an empty corpus.
    """
    p = Path(corpus)
    snap_path: Path | None = None
    if p.is_file() and p.suffix in (".tgz", ".gz") or str(p).endswith(".tar.gz"):
        tmp = Path(tempfile.mkdtemp(prefix="breadth_replay_"))
        with tarfile.open(p) as tf:
            member = next((m for m in tf.getmembers()
                           if Path(m.name).name == SNAPSHOT_FILENAME), None)
            if member is None:
                raise CorpusReplayError(f"{p}: no {SNAPSHOT_FILENAME} inside the archive")
            tf.extract(member, tmp)  # noqa: S202 - trusted local backup, data-only JSON
            snap_path = tmp / member.name
    elif p.is_dir():
        snap_path = p / SNAPSHOT_FILENAME
    elif p.is_file():
        snap_path = p
    if snap_path is None or not snap_path.exists():
        raise CorpusReplayError(f"{corpus}: could not locate {SNAPSHOT_FILENAME}")

    payload = json.loads(snap_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CorpusReplayError(f"{snap_path}: snapshot is not a JSON object")
    rows = payload.get("evidence_for_gen") or []
    if not rows:
        raise CorpusReplayError(
            f"{snap_path}: empty evidence_for_gen - refusing to replay an empty corpus"
        )
    return list(rows), payload


class CorpusReplayError(RuntimeError):
    """Fail-loud: the banked corpus could not be replayed (LAW II, no silent green)."""


# Step-4 gate (task interface): only when PG_BASKET_CONSUME_FINDING_DEDUP is SET do we
# run credibility_pass's basket assembly. Mirrors credibility_pass off-value semantics.
_BASKET_STEP_FLAG = "PG_BASKET_CONSUME_FINDING_DEDUP"
_OFF_VALUES = {"", "0", "off", "false", "no"}


def _basket_step_requested() -> bool:
    """True iff PG_BASKET_CONSUME_FINDING_DEDUP is explicitly SET to a non-off value."""
    raw = os.environ.get(_BASKET_STEP_FLAG, "")
    return raw != "" and raw.strip().lower() not in _OFF_VALUES


def _resolve_corpus_for_slug(slug: str) -> str:
    """Resolve a slug to a corpus path: prefer an already-extracted
    ``outputs/clean_local/<slug>/corpus_snapshot.json``; else fall back to
    ``outputs/corpus_backups/<slug>_corpus.tgz``. FAIL LOUD if neither exists.

    NOTE (cQ75): the clean_local dir may exist WITHOUT corpus_snapshot.json (it holds
    only bibliography/report/run_status/verification_details), so we check for the
    snapshot FILE, not just the dir, before falling through to the tgz.
    """
    snap = _REPO_ROOT / "outputs" / "clean_local" / slug / SNAPSHOT_FILENAME
    if snap.is_file():
        return str(snap)
    tgz = _REPO_ROOT / "outputs" / "corpus_backups" / f"{slug}_corpus.tgz"
    if tgz.is_file():
        return str(tgz)
    raise CorpusReplayError(
        f"slug {slug!r}: no snapshot at {snap} and no backup at {tgz}. Cannot replay."
    )


def run_tier1(rows: list[dict], domain: str, expect_rows: int | None) -> dict[str, Any]:
    """Replay the REAL ``dedup_by_finding`` exactly as run_honest_sweep_r3.py:8079 does.

    Returns a report dict. Raises on a replay/import failure so the caller exits 3.
    """
    # Import here so a bad environment surfaces as exit-3 (replay error), not a stack at top.
    from src.polaris_graph.authority.data_loader import load_authority_data
    from src.polaris_graph.synthesis.credibility_pass import credibility_redesign_enabled
    from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding

    redesign_on = credibility_redesign_enabled()
    gov = load_authority_data()["psl_gov_suffixes"]

    # EXACT live call shape (run_honest_sweep_r3.py:8079-8082).
    res = dedup_by_finding(rows, gov_suffixes=gov, domain=domain)

    clusters = res.clusters
    multi = [c for c in clusters if c.corroboration_count >= 2]
    # A REAL basket is a multi-MEMBER cluster on a KNOWN subject (the unknown-subject
    # sentinel can never merge, so a corrob>=2 on a ``__unknown__`` key is a single row
    # with two hosts, NOT a consolidated basket - report it separately, honestly).
    real_baskets = [
        c for c in clusters
        if c.corroboration_count >= 2
        and len(c.member_indices) >= 2
        and not (isinstance(c.finding_key, tuple)
                 and len(c.finding_key) >= 1 and c.finding_key[0] == "__unknown__")
    ]
    # Honest disclosure: a corroboration>=2 cluster on an ``__unknown__`` finding_key is
    # NOT genuine cross-row consolidation — the unknown-subject sentinel embeds the row's
    # evidence_id, so two rows only "merge" onto it when they SHARE an evidence_id (a data
    # quirk: duplicate evidence_id across distinct rows). Surface these so corr>=2 is never
    # mistaken for breadth when it is a sentinel artifact (the cQ75 case: ev_713 dup).
    sentinel_corr_clusters = [
        {
            "finding_key": list(c.finding_key)[:3],
            "member_indices": list(c.member_indices),
            "shared_evidence_ids": sorted({
                str(rows[ri].get("evidence_id", ri)) for ri in c.member_indices
            }),
            "hosts": list(c.member_hosts[:5]),
        }
        for c in clusters
        if c.corroboration_count >= 2 and len(c.member_indices) >= 2
        and isinstance(c.finding_key, tuple) and c.finding_key and c.finding_key[0] == "__unknown__"
    ]
    corr_dist = dict(sorted(Counter(c.corroboration_count for c in clusters).items()))
    member_dist = dict(sorted(Counter(len(c.member_indices) for c in clusters).items()))
    distinct_cited_ceiling = len({
        str(r.get("evidence_id", i)) for i, r in enumerate(res.deduped_rows)
    })

    report = {
        "tier": 1,
        "redesign_flag_on": redesign_on,
        "raw_row_count": res.raw_row_count,
        "distinct_finding_count": res.distinct_finding_count,
        "collapsed_row_count": res.collapsed_row_count,
        "deduped_rows": len(res.deduped_rows),
        "clusters_total": len(clusters),
        "clusters_corroboration_ge2": len(multi),
        "real_multi_member_baskets": len(real_baskets),
        "max_corroboration": max((c.corroboration_count for c in clusters), default=0),
        "sentinel_corroboration_artifacts": sentinel_corr_clusters,
        "corroboration_distribution": corr_dist,
        "member_count_distribution": member_dist,
        "distinct_cited_ceiling": distinct_cited_ceiling,
        "expect_rows": expect_rows,
        "input_fidelity_ok": (expect_rows is None or res.raw_row_count == expect_rows),
        "top_baskets": [
            {
                "corroboration_count": c.corroboration_count,
                "members": len(c.member_indices),
                "hosts": list(c.member_hosts[:5]),
                "finding_key": list(c.finding_key)[:4],
            }
            for c in sorted(real_baskets or multi,
                            key=lambda c: c.corroboration_count, reverse=True)[:5]
        ],
    }
    return report


def evaluate_gate(report: dict[str, Any]) -> tuple[bool, list[str]]:
    """The acceptance assertions. Returns (passed, failure_reasons).

    HARD assertions (any failure => gate FAIL, exit 2):
      A1. redesign flag is ON           (keep-all path is the one under test)
      A2. collapsed_row_count == 0       (proves keep-all engaged; a >0 means the
                                          legacy DROP path regressed back in)
      A3. clusters_corroboration_ge2 > 0 (CONSOLIDATION IS NOT A NO-OP - the real signal)
      A4. real_multi_member_baskets > 0  (>=1 KNOWN-subject multi-member basket - the
                                          unknown-subject sentinel does not count)
      A5. input_fidelity_ok              (raw_row_count matches --expect-rows if given,
                                          proving we replayed the SAME corpus)
    """
    reasons: list[str] = []
    if not report["redesign_flag_on"]:
        reasons.append(
            "A1 FAIL: PG_SWEEP_CREDIBILITY_REDESIGN is OFF - the legacy filter-and-cap "
            "drop path is active; this harness gates the WEIGHT-AND-CONSOLIDATE path. "
            "Set PG_SWEEP_CREDIBILITY_REDESIGN=on (the Gate-B / live default)."
        )
    if report["collapsed_row_count"] != 0:
        reasons.append(
            f"A2 FAIL: collapsed_row_count={report['collapsed_row_count']} != 0 - the "
            "legacy collapse-to-representative DROP re-engaged (CONSOLIDATE-keep-all "
            "regressed). Under the redesign flag every same-claim row must flow through."
        )
    if report["clusters_corroboration_ge2"] <= 0:
        reasons.append(
            "A3 FAIL: ZERO clusters with corroboration_count>=2 - consolidation is a "
            "NO-OP. finding_dedup detected "
            f"{report['distinct_finding_count']} distinct findings among "
            f"{report['raw_row_count']} rows but grouped NONE into a multi-source "
            "basket. This is the exact breadth-collapse bug (Multi-source corroborated=0)."
        )
    if report["real_multi_member_baskets"] <= 0:
        reasons.append(
            "A4 FAIL: ZERO known-subject multi-member baskets - every corroboration>=2 "
            "cluster (if any) is an unknown-subject sentinel (a single row with multiple "
            "hosts, which CANNOT merge across rows by the conservative-singleton rule), "
            "NOT a consolidated basket. The extractor returns 'unknown'/nothing for the "
            "rows, so real consolidation never happens."
        )
    if not report["input_fidelity_ok"]:
        reasons.append(
            f"A5 FAIL: raw_row_count={report['raw_row_count']} != --expect-rows="
            f"{report['expect_rows']} - replayed a DIFFERENT corpus than the live run saw."
        )
    return (not reasons), reasons


def run_tier2_baskets(rows: list[dict], domain: str, *, verify: bool) -> dict[str, Any]:
    """Fuller mode: build the claim graph + assemble baskets on the snapshot.

    ATTRIBUTION (precise): the GROUPING/consolidation half is FULLY OFFLINE and
    deterministic. ``build_claim_graph(nli_judge=None)`` is EXACTLY production's call
    shape (credibility_pass.py:653 calls it with no nli_judge), so the multi-member
    cluster count this reports is the SAME number production gets — genuine sparsity on
    this corpus, NOT an offline limitation. Only the per-member VERIFY
    (``verify_sentence_provenance`` -> the NLI entailment judge) is LLM-bearing, and it
    feeds ONLY ``verified_support_origin_count`` (the report's 'Multi-source corroborated
    (>=2 verified origins)' number) — never the grouping.

    With ``verify=False`` the basket STRUCTURE (claim clusters x members) is reported as
    the offline ceiling, NO LLM call. ``verified_support_origin_count`` requires
    ``--verify`` (the ONE unavoidable real entailment call). The harness NEVER substitutes
    a fake verify_fn and NEVER sets PG_STRICT_VERIFY_ENTAILMENT=off — either would change
    what passes verification (BANNED, CLAUDE.md §-1.3).
    """
    from src.polaris_graph.synthesis.claim_graph import build_claim_graph

    # nli_judge=None == production's call shape (credibility_pass.py:653) — offline,
    # deterministic; the count here equals production's, never an offline downgrade.
    graph = build_claim_graph(rows, domain=domain, nli_judge=None)
    clusters = getattr(graph, "clusters", {}) or {}
    claims = getattr(graph, "claims", []) or []
    multi_member_clusters = [cid for cid, idxs in clusters.items() if len(idxs) >= 2]

    out: dict[str, Any] = {
        "tier": 2,
        "claim_count": len(claims),
        "claim_clusters_total": len(clusters),
        "claim_clusters_multi_member": len(multi_member_clusters),
        "verify_ran": False,
        "note": (
            "Structural basket ceiling (no LLM). verified_support_origin_count needs the "
            "real verify_fn; pass --verify to run it (the ONE unavoidable LLM call)."
        ),
    }

    if verify:
        import os as _os
        from src.polaris_graph.authority.data_loader import load_authority_data
        from src.polaris_graph.synthesis.credibility_pass import run_credibility_analysis
        # run_credibility_analysis wires the production verify_sentence_provenance internally
        # (the SAME path the live run uses). Its per-member isolated verify is the REAL NLI
        # entailment gate — an LLM call — so this branch is LLM/spend-bearing (guarded by
        # --verify). judge=None ⇒ no separate credibility judge (priors-only, disclosed gap),
        # but the entailment verify still fires; we NEVER inject a fake verify_fn (BANNED:
        # a deterministic stand-in would change what passes verification). Serial isolated
        # verify for determinism.
        _os.environ.setdefault("PG_CREDIBILITY_PASS_MAX_INFLIGHT", "1")
        gov = tuple(load_authority_data()["psl_gov_suffixes"])
        result = run_credibility_analysis(
            "breadth_replay_harness basket assembly", rows,
            gov_suffixes=gov, domain=domain, judge=None,
        )
        baskets = getattr(result, "baskets", None) or getattr(result, "claim_baskets", []) or []
        verified_multi = [
            b for b in baskets
            if int(getattr(b, "verified_support_origin_count", 0) or 0) >= 2
        ]
        out.update({
            "verify_ran": True,
            "baskets_total": len(baskets),
            "verified_multi_origin_baskets": len(verified_multi),
            "note": (
                "verified_multi_origin_baskets == the report's 'Multi-source corroborated "
                "(>=2 origins)' number. The rendered distinct-cited count (#ev tokens) is "
                "produced only by a full render - fuller mode reports the ceiling."
            ),
        })
    return out


def run_tier_k_render(rows: list[dict], *, k_min: int) -> dict[str, Any]:
    """FIX K acceptance gate — does the verified-span render flip 0->many citations?

    Replays the EXACT production K path on the snapshot:
      build_verified_span_draft(ev_ids, pool) -> _rewrite_draft_with_spans -> strict_verify
    and counts the DISTINCT sources whose own verbatim span survives the UNCHANGED gate.
    The bug it guards: the enrichment section rendered EMPTY (590 unbound-SUPPORTS in -> 0
    cited) because the LLM re-generated prose that re-failed strict_verify. K skips the LLM
    and surfaces each source's already-verified span; this gate FAILS LOUD if the rendered
    distinct-cited count does not clear ``k_min`` (i.e. K still collapses).

    Faithfulness: NO gate is relaxed. The entailment strictness is whatever
    ``PG_STRICT_VERIFY_ENTAILMENT`` is in the environment — run with ``=off`` for the
    DETERMINISTIC floor (offline, no LLM), or unset (=enforce, the production gate) for the
    real number (LLM-bearing). This harness NEVER fakes the gate. The ev_id set here is the
    full usable-quote pool (the offline ceiling proxy for the live unbound-SUPPORTS
    selection); the real selection is a subset, so a PASS here is necessary, not inflated.
    """
    import os as _os

    from src.polaris_graph.generator.live_deepseek_generator import (
        _rewrite_draft_with_spans,
    )
    from src.polaris_graph.generator.provenance_generator import (
        parse_provenance_tokens,
        strict_verify,
    )
    from src.polaris_graph.generator.weighted_enrichment import (
        build_verified_span_draft,
        spans_per_source,
    )

    evidence_pool = {
        str(r.get("evidence_id")): r for r in rows if r.get("evidence_id")
    }
    ev_ids = [
        str(r.get("evidence_id"))
        for r in rows
        if r.get("evidence_id") and (r.get("direct_quote") or "").strip()
    ]
    draft = build_verified_span_draft(ev_ids, evidence_pool)
    rewritten, converted, unverifiable = _rewrite_draft_with_spans(draft, evidence_pool)
    report = strict_verify(rewritten, evidence_pool)

    cited: set[str] = set()
    for sv in report.kept_sentences:
        toks = getattr(sv, "tokens", None) or parse_provenance_tokens(
            getattr(sv, "sentence", "") or ""
        )
        for tok in toks:
            eid = getattr(tok, "evidence_id", None)
            if eid:
                cited.add(str(eid))

    entail_mode = _os.environ.get("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    return {
        "tier": "k_render",
        "entailment_mode": entail_mode,
        "spans_per_source": spans_per_source(),
        "ev_ids_offered": len(ev_ids),
        "draft_chars": len(draft),
        "markers_rewritten": converted,
        "markers_unverifiable": unverifiable,
        "sentences_kept": report.total_kept,
        "sentences_in": report.total_in,
        "distinct_cited_sources": len(cited),
        "k_min": k_min,
        "passed": len(cited) >= k_min,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", default="drb_75_metal_ions_cvd",
                    help="corpus slug (default drb_75_metal_ions_cvd). Resolved to "
                         "outputs/clean_local/<slug>/corpus_snapshot.json if present, else "
                         "outputs/corpus_backups/<slug>_corpus.tgz. Overridden by --corpus.")
    ap.add_argument("--corpus", default=None,
                    help="explicit path to a *_corpus.tgz, a run dir, or a corpus_snapshot.json "
                         "(overrides --slug)")
    ap.add_argument("--domain", default=None,
                    help="run-level domain to pin the extractor (e.g. clinical); "
                         "defaults to the snapshot's own 'domain' field")
    ap.add_argument("--expect-rows", type=int, default=None,
                    help="assert raw_row_count == this (input-fidelity guard)")
    ap.add_argument("--baskets", action="store_true",
                    help="fuller mode: also build the claim graph + baskets")
    ap.add_argument("--verify", dest="verify", action="store_true",
                    help="(with --baskets) run the REAL per-member verify (LLM/spend-bearing)")
    ap.add_argument("--no-verify", dest="verify", action="store_false",
                    help="(with --baskets) structural ceiling only, no LLM (default)")
    ap.set_defaults(verify=False)
    ap.add_argument("--k-render", action="store_true",
                    help="FIX K gate: replay build_verified_span_draft -> rewrite -> "
                         "strict_verify and assert distinct-cited >= --k-min. Run with "
                         "PG_STRICT_VERIFY_ENTAILMENT=off for the deterministic floor.")
    ap.add_argument("--k-min", type=int, default=50,
                    help="FIX K gate floor: minimum distinct-cited sources to PASS (default 50; "
                         "the broken baseline is ~7).")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON to stdout")
    args = ap.parse_args(argv)

    # Resolve corpus: explicit --corpus wins; else resolve the --slug.
    try:
        corpus = args.corpus or _resolve_corpus_for_slug(args.slug)
    except CorpusReplayError as exc:
        _eprint(f"[breadth-replay] REPLAY ERROR: {exc}")
        return 3

    try:
        rows, payload = _load_snapshot_rows(corpus)
    except (CorpusReplayError, OSError, json.JSONDecodeError) as exc:
        _eprint(f"[breadth-replay] REPLAY ERROR: {exc}")
        return 3
    domain = args.domain or payload.get("domain")

    # Task interface: PG_BASKET_CONSUME_FINDING_DEDUP set ⇒ also run the basket step
    # (equivalent to --baskets). Honest constraint: the per-member verify is the REAL
    # NLI entailment gate (an LLM call), so a faithful basket verdict is NOT no-LLM.
    # We therefore run the STRUCTURAL basket ceiling (no LLM) by default and only issue
    # the verify LLM call when --verify is passed. verified_support_origin_count (the
    # task's >=2 assertion) requires that real verify — never a fake verify_fn (BANNED).
    run_baskets = args.baskets or _basket_step_requested()

    # FIX K gate: a SEPARATE acceptance gate (verified-span render), not the consolidation
    # one. Run it standalone so its PASS/FAIL is unambiguous and exit code reflects only K.
    if args.k_render:
        try:
            krep = run_tier_k_render(rows, k_min=args.k_min)
        except Exception as exc:  # noqa: BLE001 - any replay failure is exit-3, fail loud
            _eprint(f"[breadth-replay] REPLAY ERROR (FIX-K execution): {exc!r}")
            return 3
        if args.json:
            print(json.dumps(krep, indent=2, default=str))
        else:
            _eprint("== BREADTH REPLAY (FIX-K verified-span render gate) ==")
            _eprint(f"  corpus              : {corpus}")
            _eprint(f"  entailment_mode     : {krep['entailment_mode']} "
                    f"(off=deterministic floor; enforce=production gate, LLM-bearing)")
            _eprint(f"  spans_per_source    : {krep['spans_per_source']}")
            _eprint(f"  ev_ids offered      : {krep['ev_ids_offered']}")
            _eprint(f"  sentences kept / in : {krep['sentences_kept']} / {krep['sentences_in']}")
            _eprint(f"  DISTINCT CITED      : {krep['distinct_cited_sources']} "
                    f"(broken baseline ~7; k_min={krep['k_min']})")
            if krep["passed"]:
                _eprint("  VERDICT             : PASS - K surfaced the verified-span basket.")
            else:
                _eprint("  VERDICT             : FAIL - K still collapses (distinct-cited "
                        "below k_min). The render is NOT firing in the output.")
        return 0 if krep["passed"] else 1

    try:
        report = run_tier1(rows, domain=domain, expect_rows=args.expect_rows)
        if run_baskets:
            report["tier2"] = run_tier2_baskets(rows, domain=domain, verify=args.verify)
    except Exception as exc:  # noqa: BLE001 - any replay failure is exit-3, fail loud
        _eprint(f"[breadth-replay] REPLAY ERROR (Tier-1/2 execution): {exc!r}")
        return 3

    passed, reasons = evaluate_gate(report)

    if args.json:
        print(json.dumps({"report": report, "passed": passed, "reasons": reasons},
                         indent=2, default=str))
    else:
        _eprint("== BREADTH REPLAY (consolidation acceptance gate) ==")
        _eprint(f"  corpus            : {corpus}")
        _eprint(f"  domain            : {domain}")
        _eprint(f"  redesign_flag_on  : {report['redesign_flag_on']}")
        _eprint(f"  raw / distinct    : {report['raw_row_count']} / "
                f"{report['distinct_finding_count']}")
        _eprint(f"  collapsed         : {report['collapsed_row_count']} (must be 0 = keep-all)")
        _eprint(f"  clusters corr>=2  : {report['clusters_corroboration_ge2']}")
        _eprint(f"  REAL baskets      : {report['real_multi_member_baskets']} "
                f"(known-subject, >=2 members)")
        _eprint(f"  max corroboration : {report['max_corroboration']}")
        if report.get("sentinel_corroboration_artifacts"):
            _eprint(f"  SENTINEL ARTIFACTS: {len(report['sentinel_corroboration_artifacts'])} "
                    f"corr>=2 cluster(s) are unknown-subject sentinels (dup evidence_id, NOT breadth):")
            for s in report["sentinel_corroboration_artifacts"]:
                _eprint(f"    - shared_evidence_ids={s['shared_evidence_ids']} "
                        f"rows={s['member_indices']} hosts={s['hosts']}")
        _eprint(f"  corr distribution : {report['corroboration_distribution']}")
        _eprint(f"  cited ceiling     : {report['distinct_cited_ceiling']}")
        if report.get("tier2"):
            t2 = report["tier2"]
            _eprint(f"  [tier2] claim clusters multi-member: "
                    f"{t2['claim_clusters_multi_member']}/{t2['claim_clusters_total']}")
            if t2.get("verify_ran"):
                _eprint(f"  [tier2] VERIFIED multi-origin baskets: "
                        f"{t2['verified_multi_origin_baskets']}/{t2['baskets_total']}")
        if passed:
            _eprint("  VERDICT           : PASS - consolidation produced >=1 multi-origin basket.")
        else:
            _eprint("  VERDICT           : FAIL - consolidation is a NO-OP:")
            for r in reasons:
                _eprint(f"    - {r}")

    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
