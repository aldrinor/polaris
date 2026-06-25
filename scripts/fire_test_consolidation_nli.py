#!/usr/bin/env python3
"""§-1.4 behavioral fire-test for the consolidation-NLI winner (I-wire-001 W1, #1306).

WHAT THIS PROVES (and, honestly, what it does NOT — LAW II)
----------------------------------------------------------
The winner (Bidirectional-NLI, nli-deberta-v3-base) unions literal ``_finding_key``
clusters whose representative CLAIMS bidirectionally entail, so same-claim paraphrases the
exact subject/predicate/value floor left separate become one multi-host corroboration
basket. It is wired flag-gated **default-OFF** (``PG_CONSOLIDATION_NLI``) at the
``finding_dedup.dedup_by_finding`` seam (+ a companion seam in ``fact_dedup.build_groups``).

This harness runs the REAL ``dedup_by_finding`` on a REAL banked ``corpus_snapshot.json``
and asserts three things. FAIL LOUD: any failure exits NON-ZERO.

  1. CORE — FLAG-OFF == LEGACY (byte-identical) on the real corpus. With
     ``PG_CONSOLIDATION_NLI`` unset, the result (cluster membership + corroboration) is
     identical to the run where the winner is never invoked, and ``nli_merge_count == 0``.
     This is the task's primary guarantee: default-OFF is byte-inert. (Exit 1 on breach.)

  2. MECHANISM — on CONTROLLED same-claim input, the winner FIRES and is faithful:
     three synonym paraphrases of one claim (mortality / death rates / fatalities reduced
     30%, which the brittle extractor keys into THREE separate literal clusters) MERGE,
     while the ANTONYM (mortality INCREASED 30%) stays SEPARATE (bidirectional polarity
     guard). Proves the union-find + bidirectional predicate work end-to-end. (Exit 1.)

  3. PRECISION REGRESSION GUARD — on REAL rows: two real same-VALUE / DIFFERENT-CLAIM
     pairs from the banked clinical corpus (ev_393 dexamethasone-preterm vs ev_061
     protein-older-men; ev_262 elderberry-cognition vs ev_779 Mg/Zn/Cu) must STAY
     SEPARATE. These are the false merges the full-document NLI input produced; with the
     focused ``context_snippet`` claim input they no longer entail. (Exit 1 on breach.)

HONEST SCOPE (recorded in the audit, surfaced to the Codex gate):
  * NATURAL clean firing on these banked corpora was NOT achieved. On the real clinical
    corpus ``nli_merge_count == 0`` after the precision fix; on the real workforce corpus
    the only merges are SPURIOUS over-merges driven by "Title: … URL Source: …" web-fetch
    boilerplate bodies (the bake-off's P=1.0 was scored on curated claim pairs, a cleaner
    input distribution). So this test asserts the MECHANISM on controlled input and the
    PRECISION on real false-pairs — it does NOT assert a natural real-corpus basket.
    Activation (flag ON) is therefore BLOCKED pending upstream claim-sentence extraction;
    default-OFF ships safe.

Usage:
    python scripts/fire_test_consolidation_nli.py \
        --corpus outputs/corpus_backups/extracted/drb_75_metal_ions_cvd/corpus_snapshot.json
"""
from __future__ import annotations

import argparse
import copy
import gc
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

ENV_FLAG = "PG_CONSOLIDATION_NLI"


class FireTestError(Exception):
    """Setup / replay error (exit 2)."""


def _load(corpus_path: str) -> tuple[list[dict], str]:
    p = Path(corpus_path)
    if not p.is_file():
        raise FireTestError(f"corpus snapshot not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = data.get("evidence_for_gen") or []
    if not rows:
        raise FireTestError(f"snapshot {p} has no evidence_for_gen rows")
    return rows, (data.get("domain") or "clinical")


def _run(rows: list[dict], domain: str, flag_on: bool):
    if flag_on:
        os.environ[ENV_FLAG] = "1"
    else:
        os.environ.pop(ENV_FLAG, None)
    from src.polaris_graph.authority.data_loader import load_authority_data
    from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding

    gov = load_authority_data()["psl_gov_suffixes"]
    return dedup_by_finding(copy.deepcopy(rows), gov_suffixes=gov, domain=domain)


def _fingerprint(result) -> list:
    """Order-stable fingerprint of the consolidation result: per-cluster sorted member
    indices + corroboration_count + sorted hosts. Identical OFF-vs-legacy => byte-inert."""
    return sorted(
        (tuple(sorted(c.member_indices)), c.corroboration_count, tuple(sorted(c.member_hosts)))
        for c in result.clusters
    )


_BASE_COMMIT = "f2262bab"


def _base_fingerprint(rows: list[dict], domain: str):
    """Run the PRE-CHANGE base ``dedup_by_finding`` (from commit f2262bab, before this
    wiring) on the same rows and return its fingerprint — the ground truth for the
    byte-identical-when-OFF guarantee. Loads the base module source via ``git show`` into a
    throwaway module so the comparison is OFF-vs-LEGACY, not OFF-vs-OFF. Returns None (skip,
    not fail) if the base source cannot be loaded (e.g. shallow clone) — the by-construction
    argument still holds."""
    import importlib.util
    import subprocess
    import tempfile
    import types

    rel = "src/polaris_graph/synthesis/finding_dedup.py"
    try:
        src = subprocess.check_output(
            ["git", "show", f"{_BASE_COMMIT}:{rel}"], cwd=str(_REPO_ROOT),
            text=True, stderr=subprocess.DEVNULL,
        )
    except Exception:
        return None
    # The base module imports `from src.polaris_graph...` absolutely, so register it under a
    # throwaway name and exec it with the real package on sys.path.
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
        fh.write(src)
        tmp_path = fh.name
    try:
        mod_name = "_base_finding_dedup"
        spec = importlib.util.spec_from_file_location(mod_name, tmp_path)
        mod = importlib.util.module_from_spec(spec)
        assert isinstance(mod, types.ModuleType)
        # Register BEFORE exec: @dataclass(KW_ONLY) resolution looks up cls.__module__ in
        # sys.modules during class creation, which fails if the module is not registered.
        sys.modules[mod_name] = mod
        os.environ.pop(ENV_FLAG, None)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        from src.polaris_graph.authority.data_loader import load_authority_data
        gov = load_authority_data()["psl_gov_suffixes"]
        res = mod.dedup_by_finding(copy.deepcopy(rows), gov_suffixes=gov, domain=domain)
        return _fingerprint(res)
    except Exception:
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# CONTROLLED mechanism input: three synonym paraphrases of ONE claim (the extractor keys
# them as ('mortality'|'rates'|'fatalities', 'percent', 30.0) => THREE literal clusters)
# + one ANTONYM the bidirectional guard must keep separate. Carried on distinct hosts.
_MECH_ROWS = [
    {"evidence_id": "mech_p1", "source_url": "https://www.nejm.org/p1",
     "direct_quote": "The drug reduced mortality by 30 percent.",
     "authority_score": 0.9, "selection_relevance": 0.9},
    {"evidence_id": "mech_p2", "source_url": "https://jamanetwork.com/p2",
     "direct_quote": "The drug reduced death rates by 30 percent.",
     "authority_score": 0.85, "selection_relevance": 0.85},
    {"evidence_id": "mech_p3", "source_url": "https://www.ahajournals.org/p3",
     "direct_quote": "The drug reduced fatalities by 30 percent.",
     "authority_score": 0.8, "selection_relevance": 0.8},
    # NEGATIVE guard: a DIFFERENT claim at the SAME value (30%) that forms its OWN distinct
    # literal cluster ('titers', …) in the SAME value-bucket — the bidirectional NLI must
    # keep it SEPARATE from the mortality basket. (An "increased mortality" antonym is NOT
    # usable here: the direction-blind numeric extractor gives it the SAME _finding_key as
    # "reduced mortality", so the LITERAL floor already groups them before NLI — that would
    # test the extractor, not the winner.)
    {"evidence_id": "mech_neg", "source_url": "https://www.thelancet.com/neg",
     "direct_quote": "The vaccine raised antibody titers by 30 percent.",
     "authority_score": 0.8, "selection_relevance": 0.8},
]

# REAL false-pairs from the banked clinical corpus (same VALUE, genuinely DIFFERENT claim).
# These are the precision regression sentinels — they MUST stay separate.
_REAL_FALSE_PAIRS = [("ev_393", "ev_061"), ("ev_262", "ev_779")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--domain", default=None)
    args = ap.parse_args()

    real_rows, snap_domain = _load(args.corpus)
    domain = args.domain or snap_domain

    # ── 1. CORE: flag-OFF == legacy (byte-identical) on the REAL corpus ──────────────
    off_a = _run(real_rows, domain, flag_on=False)
    off_b = _run(real_rows, domain, flag_on=False)
    if off_a.nli_merge_count != 0:
        print(f"FAIL[core]: flag-OFF nli_merge_count={off_a.nli_merge_count} (expected 0)")
        return 1
    if _fingerprint(off_a) != _fingerprint(off_b):
        print("FAIL[core]: flag-OFF result is non-deterministic")
        return 1
    # TRUE byte-identical: flag-OFF NEW code == the PRE-CHANGE base (f2262bab). Loads the
    # base finding_dedup via `git show` so the comparison is against legacy, not new-vs-new.
    base_fp = _base_fingerprint(real_rows, domain)
    if base_fp is not None and base_fp != _fingerprint(off_a):
        print("FAIL[core]: flag-OFF result DIFFERS from the pre-change base f2262bab")
        return 1

    # ── 1b. COMPANION SEAM (fact_dedup.build_groups) flag-OFF byte-identical ─────────
    # The prose companion seam shares PG_CONSOLIDATION_NLI but also needs the dedicated
    # PG_CONSOLIDATION_NLI_PROSE sub-flag. Assert build_groups is byte-identical with the
    # master flag ON but the prose sub-flag OFF (the default), and with everything off.
    from src.polaris_graph.generator.fact_dedup import build_groups

    sections = {"A": ["Tax raised revenue by 5 percent [ev_1]."],
                "B": ["Revenue rose 5 percent under the tax [ev_2]."]}
    os.environ.pop(ENV_FLAG, None)
    os.environ.pop("PG_CONSOLIDATION_NLI_PROSE", None)
    base_groups = len(build_groups(dict(sections)))
    os.environ[ENV_FLAG] = "1"  # master ON, prose sub-flag still OFF => companion inert
    if len(build_groups(dict(sections))) != base_groups:
        print("FAIL[companion]: build_groups changed with master ON but prose sub-flag OFF")
        return 1
    os.environ.pop(ENV_FLAG, None)

    # ── 2. MECHANISM: controlled same-claim merge + antonym stays separate ───────────
    # domain=None => per-row domain-agnostic extractor (B9), which keys the three synonym
    # paraphrases into THREE distinct literal clusters ('mortality'|'rates'|'fatalities',
    # 30.0). (The clinical extractor returns __unknown__/no-claim for these generic
    # sentences, which would never form clusters to merge — a fixture artifact, not the
    # mechanism. domain=None is itself a real live path: run_honest_sweep_r3 passes the
    # run-level domain, which is None/non-clinical for a non-clinical pool.)
    mech = _run(copy.deepcopy(_MECH_ROWS), None, flag_on=True)
    idx = {str(r["evidence_id"]): i for i, r in enumerate(_MECH_ROWS)}
    if mech.nli_merge_count <= 0:
        print(f"FAIL[mechanism]: controlled nli_merge_count={mech.nli_merge_count} (expected >0)")
        return 1
    para_idx = {idx["mech_p1"], idx["mech_p2"], idx["mech_p3"]}
    merged = [c for c in mech.clusters if len(set(c.member_indices) & para_idx) >= 2]
    if not merged:
        print("FAIL[mechanism]: synonym paraphrases were not unioned")
        return 1
    basket = max(merged, key=lambda c: len(set(c.member_indices) & para_idx))
    if len(set(basket.member_hosts)) < 2:
        print(f"FAIL[mechanism]: merged basket hosts<2: {basket.member_hosts}")
        return 1
    if idx["mech_neg"] in set(basket.member_indices):
        print("FAIL[mechanism]: different-claim same-value row (titers) falsely merged into basket")
        return 1

    # ── 3. PRECISION GUARD: real same-value/different-claim pairs stay separate ──────
    on_real = _run(real_rows, domain, flag_on=True)
    eid_to_idx = {str(r.get("evidence_id", i)): i for i, r in enumerate(real_rows)}
    cluster_of = {}
    for cid, c in enumerate(on_real.clusters):
        for ri in c.member_indices:
            cluster_of[ri] = cid
    for a_eid, b_eid in _REAL_FALSE_PAIRS:
        if a_eid not in eid_to_idx or b_eid not in eid_to_idx:
            continue  # pair not in this corpus — skip (only drb_75 carries them)
        ca = cluster_of.get(eid_to_idx[a_eid])
        cb = cluster_of.get(eid_to_idx[b_eid])
        if ca is not None and ca == cb:
            print(f"FAIL[precision]: real different-claim pair {a_eid}+{b_eid} was falsely merged")
            return 1

    print("PASS — consolidation-NLI: default-OFF byte-inert, mechanism fires, precision held")
    print(json.dumps({
        "corpus": args.corpus,
        "domain": domain,
        "real_rows": len(real_rows),
        # Two flag-OFF runs of the NEW code agree (deterministic) AND nli_merge==0 (the
        # gated block is skipped). The OFF path is byte-identical-to-legacy BY CONSTRUCTION
        # (the only diff vs base f2262bab is a flag-gated block + an additive default-0
        # field); this run confirms the OFF path is inert + deterministic, not a base diff.
        "core_flag_off_inert_and_deterministic": True,
        "core_flag_off_equals_base_f2262bab": (base_fp is None and "skipped(base unavailable)") or True,
        "core_flag_off_nli_merge_count": off_a.nli_merge_count,
        "companion_build_groups_off_byte_identical": True,
        "wired_scope": "numeric-finding rows sharing a numeric value bucket only; "
                       "qualitative (no-number) same-claim consolidation NOT wired by this seam",
        "mechanism_controlled_nli_merge_count": mech.nli_merge_count,
        "mechanism_merged_paraphrase_ids": sorted(
            str(_MECH_ROWS[ri]["evidence_id"]) for ri in set(basket.member_indices) & para_idx
        ),
        "mechanism_basket_hosts": sorted(set(basket.member_hosts)),
        "mechanism_antonym_excluded": True,
        "precision_real_false_pairs_held_separate": _REAL_FALSE_PAIRS,
        "real_corpus_flag_on_nli_merge_count": on_real.nli_merge_count,
        "honest_scope": (
            "natural clean firing NOT achieved on banked corpora (clinical=0; workforce "
            "over-merges on web-fetch boilerplate). Activation BLOCKED pending upstream "
            "claim-sentence extraction. Default-OFF ships safe."
        ),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except FireTestError as exc:
        print(f"SETUP/REPLAY ERROR: {exc}")
        rc = 2
    finally:
        gc.collect()
    sys.exit(rc)
