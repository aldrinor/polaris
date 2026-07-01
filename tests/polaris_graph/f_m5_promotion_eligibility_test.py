"""I-deepfix-001 (#1344 M5) — isolated OFFLINE replay of the PROMOTION-ELIGIBILITY partition.

Runs ``weighted_enrichment.diagnose_unbound_supports_selection`` over the REAL banked drb_72
``bibliography.json`` baskets (no paid API, no GPU). Asserts the partition demotes EXACTLY the 8
named near-zero single-origin non-journal sources and ZERO promoted ones, conservation holds
(promoted UNION disclosed == the full list), the gate-OFF path is byte-identical, the
over-demotion guards (journal carve-out, corroboration leg, unknown-weight keep-neutral) all
rescue, and a garbage threshold env raises ValueError (fail-loud).

Direct run:  python tests/polaris_graph/f_m5_promotion_eligibility_test.py
Pytest:      python -m pytest tests/polaris_graph/f_m5_promotion_eligibility_test.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

# Make ``src`` importable when run directly (mirrors the pytest rootdir import).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.generator.weighted_enrichment import (  # noqa: E402
    diagnose_unbound_supports_selection,
)

# The REAL banked drb_72 artifact (absolute; outside the worktree per the task brief).
_BANKED_BIB = Path(
    "C:/POLARIS/.codex/I-deepfix-001/smoke_forensics/outputs/"
    "deepfix_safety_smoke/workforce/drb_72_ai_labor/bibliography.json"
)

# The 8 near-zero, single-origin, NON-journal sources the design says MUST demote (by evidence_id),
# with the URL substring that identifies each in the §-1.1 audit (for human-readable failure msgs).
_EXPECTED_DEMOTED = {
    "ev_000": ("wsu blog", "etm.wsu.edu"),          # 0.06
    "ev_009": ("iza working paper", "docs.iza.org"),  # 0.05
    "ev_050": ("cognifit blog", "blog.cognifit.com"),  # 0.03
    "ev_064": ("inboundlogistics", "inboundlogistics.com"),  # 0.00
    "ev_054": ("procom", "procomservices.com"),     # 0.01
    "ev_066": ("protolabs", "protolabs.com"),        # 0.00
    "ev_057": ("predatory 10.5555 doi", "10.5555"),  # 0.00
    "ev_061": ("off-topic 10.26163 doi", "10.26163"),  # 0.00
}


def _load_baskets_and_pool():
    """Rebuild the credibility_analysis baskets + a minimal evidence_pool from the banked bib.

    Each banked basket is attached to every member's bib row, so dedup by ``claim_cluster_id`` to
    mirror the real ``CredibilityAnalysis.baskets`` list (each basket once). Members + baskets are
    wrapped in SimpleNamespace so the production ``getattr`` access path is exercised unchanged."""
    bib = json.loads(_BANKED_BIB.read_text(encoding="utf-8"))
    baskets_by_ccid: dict[str, object] = {}
    pool: dict[str, dict] = {}
    for row in bib:
        for bk in (row.get("baskets") or []):
            ccid = str(bk.get("claim_cluster_id") or "")
            if not ccid or ccid in baskets_by_ccid:
                continue
            members = []
            for m in (bk.get("supporting_members") or []):
                eid = str(m.get("evidence_id") or "")
                if not eid:
                    continue
                members.append(
                    SimpleNamespace(
                        evidence_id=eid,
                        source_url=m.get("source_url", ""),
                        source_tier=m.get("source_tier", ""),
                        credibility_weight=m.get("credibility_weight"),
                        span_verdict=m.get("span_verdict", ""),
                        member_tier=m.get("member_tier", ""),
                    )
                )
                pool.setdefault(eid, {"source_url": m.get("source_url", "")})
            baskets_by_ccid[ccid] = SimpleNamespace(
                claim_cluster_id=ccid,
                weight_mass=bk.get("weight_mass", 0.0),
                verified_support_origin_count=bk.get("verified_support_origin_count", 0),
                supporting_members=members,
            )
    return list(baskets_by_ccid.values()), pool


class _Env:
    """Deterministic env scope: set the given M5 vars, restore prior values on exit."""

    _KEYS = (
        "PG_CWF_PROMOTION_ELIGIBILITY",
        "PG_CWF_PROMOTION_MIN_WEIGHT",
        "PG_CWF_PROMOTION_MIN_CORROBORATION",
    )

    def __init__(self, **overrides):
        self._overrides = overrides

    def __enter__(self):
        self._saved = {k: os.environ.get(k) for k in self._KEYS}
        for k in self._KEYS:
            os.environ.pop(k, None)
        for k, v in self._overrides.items():
            os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k in self._KEYS:
            os.environ.pop(k, None)
            if self._saved.get(k) is not None:
                os.environ[k] = self._saved[k]
        return False


def _run(baskets, pool):
    fake_cred = SimpleNamespace(baskets=baskets)
    return diagnose_unbound_supports_selection(
        evidence_pool=pool, credibility_analysis=fake_cred, contract_plans=[]
    )


# ── assertions, also callable directly ────────────────────────────────────────

def _require_banked():
    if not _BANKED_BIB.exists():
        msg = f"banked artifact missing: {_BANKED_BIB}"
        try:
            import pytest  # type: ignore

            pytest.skip(msg)
        except Exception:
            print(f"SKIP {msg}")
            raise SystemExit(0)


def test_gate_off_is_byte_identical_keep_all():
    _require_banked()
    baskets, pool = _load_baskets_and_pool()
    with _Env(PG_CWF_PROMOTION_ELIGIBILITY="0"):
        res = _run(baskets, pool)
    # All 25 distinct eids flow; the 8 are present; disclosed_only empty (legacy keep-all).
    assert len(res.ev_ids) == 25, f"expected 25 ev_ids gate-OFF, got {len(res.ev_ids)}"
    for eid in _EXPECTED_DEMOTED:
        assert eid in res.ev_ids, f"gate-OFF must KEEP {eid} in ev_ids"
    assert res.disclosed_only == (), "gate-OFF must yield empty disclosed_only"
    return res


def test_gate_on_demotes_exactly_the_eight():
    _require_banked()
    baskets, pool = _load_baskets_and_pool()
    with _Env():  # defaults: gate ON, W=0.10, K=2
        res = _run(baskets, pool)
    disclosed_ids = {d["evidence_id"] for d in res.disclosed_only}
    assert disclosed_ids == set(_EXPECTED_DEMOTED), (
        f"disclosed_only must be EXACTLY the 8; got {sorted(disclosed_ids)} "
        f"(missing {set(_EXPECTED_DEMOTED) - disclosed_ids}, "
        f"extra {disclosed_ids - set(_EXPECTED_DEMOTED)})"
    )
    for eid in _EXPECTED_DEMOTED:
        assert eid not in res.ev_ids, f"{eid} must be DEMOTED out of ev_ids"
    # ZERO over-demotion: every promoted source has weight >= 0.10 (or is rescued), none of the 8.
    assert len(res.ev_ids) == 17, f"expected 17 promoted, got {len(res.ev_ids)}"
    # Each disclosed record carries the full schema the render block consumes.
    for d in res.disclosed_only:
        assert set(d) == {
            "evidence_id", "source_url", "source_tier", "credibility_weight", "reason",
        }, f"disclosed record schema drift: {sorted(d)}"
        assert d["reason"] == "single_origin_low_weight_non_journal"
        assert isinstance(d["credibility_weight"], float) and d["credibility_weight"] < 0.10
    return res


def test_no_over_demotion_promoted_set_intact():
    _require_banked()
    baskets, pool = _load_baskets_and_pool()
    with _Env():
        res = _run(baskets, pool)
    # Every real source with weight >= 0.10 STAYS promoted (the design's named promoted set).
    expected_promoted_floor = {
        "ev_035": 0.12, "ev_021": 0.14, "ev_018": 0.1425, "ev_002": 0.16, "ev_040": 0.18,
        "ev_047": 0.24, "ev_026": 0.27, "ev_016": 0.32, "ev_044": 0.35, "ev_015": 0.36,
        "ev_032": 0.9025, "ev_024": 0.9025,
    }
    for eid in expected_promoted_floor:
        assert eid in res.ev_ids, f"{eid} (weight>=0.10) was wrongly demoted"
    return res


def test_over_correction_guards_rescue():
    """journal carve-out, corroboration leg, and unknown-weight keep-neutral all rescue a low weight."""
    _require_banked()
    baskets, pool = _load_baskets_and_pool()
    # (a) journal-domain member at weight 0.01 — KEPT via the journal carve-out.
    pool["synthetic_journal"] = {"source_url": "https://www.nejm.org/doi/10.1056/synthetic"}
    # (b) low-weight member whose basket has 2 verified origins — KEPT via the corroboration leg.
    pool["synthetic_corroborated"] = {"source_url": "https://example.org/corroborated"}
    # (c) unknown-weight (None) member — KEPT via keep-neutral (unknown => promote).
    pool["synthetic_unknown_weight"] = {"source_url": "https://example.org/unknown"}
    extra = [
        SimpleNamespace(
            claim_cluster_id="synthetic_journal_cluster", weight_mass=0.01,
            verified_support_origin_count=1,
            supporting_members=[SimpleNamespace(
                evidence_id="synthetic_journal", source_url="https://www.nejm.org/doi/10.1056/synthetic",
                source_tier="T1", credibility_weight=0.01, span_verdict="SUPPORTS",
                member_tier="ENTAILMENT_VERIFIED")],
        ),
        SimpleNamespace(
            claim_cluster_id="synthetic_corroborated_cluster", weight_mass=0.01,
            verified_support_origin_count=2,
            supporting_members=[SimpleNamespace(
                evidence_id="synthetic_corroborated", source_url="https://example.org/corroborated",
                source_tier="T6", credibility_weight=0.01, span_verdict="SUPPORTS",
                member_tier="ENTAILMENT_VERIFIED")],
        ),
        SimpleNamespace(
            claim_cluster_id="synthetic_unknown_cluster", weight_mass=0.0,
            verified_support_origin_count=1,
            supporting_members=[SimpleNamespace(
                evidence_id="synthetic_unknown_weight", source_url="https://example.org/unknown",
                source_tier="T6", credibility_weight=None, span_verdict="SUPPORTS",
                member_tier="ENTAILMENT_VERIFIED")],
        ),
    ]
    with _Env():
        res = _run(baskets + extra, pool)
    disclosed_ids = {d["evidence_id"] for d in res.disclosed_only}
    assert "synthetic_journal" in res.ev_ids, "journal carve-out must rescue a low-weight journal"
    assert "synthetic_corroborated" in res.ev_ids, "corroboration leg must rescue a 2-origin member"
    assert "synthetic_unknown_weight" in res.ev_ids, "unknown weight must keep-neutral (promote)"
    assert disclosed_ids == set(_EXPECTED_DEMOTED), (
        "the 3 rescued synthetics must NOT appear in disclosed_only"
    )
    return res


def test_conservation_nothing_vanishes():
    """promoted UNION disclosed == the full ordered list (routed, never dropped)."""
    _require_banked()
    baskets, pool = _load_baskets_and_pool()
    with _Env(PG_CWF_PROMOTION_ELIGIBILITY="0"):
        full = set(_run(baskets, pool).ev_ids)
    with _Env():
        on = _run(baskets, pool)
    union = set(on.ev_ids) | {d["evidence_id"] for d in on.disclosed_only}
    assert union == full, (
        f"conservation broken: union {len(union)} != full {len(full)} "
        f"(lost {full - union}, gained {union - full})"
    )
    assert not (set(on.ev_ids) & {d["evidence_id"] for d in on.disclosed_only}), (
        "promoted and disclosed_only must be DISJOINT"
    )
    return full, on


def test_garbage_env_raises_value_error():
    _require_banked()
    baskets, pool = _load_baskets_and_pool()
    raised = 0
    for k, v in (
        ("PG_CWF_PROMOTION_MIN_WEIGHT", "abc"),
        ("PG_CWF_PROMOTION_MIN_WEIGHT", "1.5"),
        ("PG_CWF_PROMOTION_MIN_CORROBORATION", "0"),
        ("PG_CWF_PROMOTION_MIN_CORROBORATION", "xx"),
    ):
        with _Env(**{k: v}):
            try:
                _run(baskets, pool)
            except ValueError:
                raised += 1
            else:
                raise AssertionError(f"garbage {k}={v!r} must raise ValueError (fail-loud)")
    assert raised == 4
    return raised


def main():
    _require_banked()
    off = test_gate_off_is_byte_identical_keep_all()
    print(f"[1] gate OFF: ev_ids={len(off.ev_ids)} disclosed={len(off.disclosed_only)}  PASS")
    on = test_gate_on_demotes_exactly_the_eight()
    demoted = sorted(d["evidence_id"] for d in on.disclosed_only)
    print(f"[2] gate ON : promoted={len(on.ev_ids)} demoted={len(on.disclosed_only)} -> {demoted}  PASS")
    test_no_over_demotion_promoted_set_intact()
    print("[3] no over-demotion: every weight>=0.10 source stays promoted  PASS")
    test_over_correction_guards_rescue()
    print("[4] guards: journal / corroboration / unknown-weight all rescue  PASS")
    full, oncons = test_conservation_nothing_vanishes()
    print(f"[5] conservation: promoted({len(oncons.ev_ids)}) U disclosed({len(oncons.disclosed_only)}) == full({len(full)})  PASS")
    n = test_garbage_env_raises_value_error()
    print(f"[6] fail-loud: {n}/4 garbage env values raised ValueError  PASS")
    print("\nALL M5 ASSERTIONS PASS")
    # Render-block smoke (the report surface), proving the disclosed records render.
    print("\n[disclosed block sample]")
    for d in oncons.disclosed_only:
        print(f"  - {d['source_url'] or d['evidence_id']} (tier {d['source_tier']}, weight {d['credibility_weight']:.2f})")


if __name__ == "__main__":
    main()
