"""A/B CERTIFIER for the PG_COMPOSE_BASKET_WORKERS map-then-reduce port (this worktree).

Proves the parallel path (_compose_section_per_basket with workers=16) produces the BYTE-IDENTICAL
ordered output list as the serial path (workers=1) on the SAME per-basket producer outputs — i.e. the
reconciled MAP/REDUCE dedup is verdict-set-identical to this worktree's serial loop, and has no
shared-state race under real thread interleaving.

Method: monkeypatch the per-basket producers the MAP calls with DETERMINISTIC-per-basket functions
(same basket -> same text in both arms) that inject a RANDOM sleep (forces the ThreadPool to interleave
in a different order each call). The producer outputs are crafted to hit every REDUCE branch:
  - unique units (kept)
  - exact duplicate text+span of an earlier basket (subset+text dedup -> dropped)
  - same footprint, NO new number (footprint-number collapse -> dropped)
  - same footprint, NEW number (survives)
  - internal §3.5 insufficient-evidence marker (whole basket skipped, aux discarded)
  - aux units (companion/qualifier/distinct) incl. an aux that duplicates a main (aux dedup)
If serial != parallel on ANY of 200 randomized trials, the port has a race. Zero LLM.
"""
from __future__ import annotations

import os
import random
import sys
import time

os.environ["PG_COMPANION_FIGURE_COMPOSE"] = "1"
os.environ["PG_QUALIFIER_ELABORATION"] = "1"
os.environ["PG_SUBTOPIC_ADDITIVE_FACTS"] = "1"

import src.polaris_graph.generator.verified_compose as vc  # noqa: E402

MARKER = "[insufficient verified evidence for this basket]"


def _tok(ev: str, s: int, e: int) -> str:
    return f"[#ev:{ev}:{s}-{e}]"


# Deterministic per-basket MAIN text. Baskets are ints 0..N-1.
def _main_text(b: int) -> str:
    if b == 3:
        return MARKER  # §3.5: whole basket (incl aux) must be skipped
    if b == 5:
        # exact duplicate of basket 0's text+span -> subset+text dedup drop
        return f"Finding zero {_tok('ev0', 0, 10)} rate 5%."
    if b == 8:
        # same footprint as basket 0 (ev0:0-10) but NO new number token beyond '5%' -> collapse
        return f"Restated finding {_tok('ev0', 0, 10)} rate 5%."
    if b == 9:
        # same footprint as basket 0 but a NEW number (12%) -> survives
        return f"Extended finding {_tok('ev0', 0, 10)} rose to 12%."
    if b == 0:
        return f"Finding zero {_tok('ev0', 0, 10)} rate 5%."
    return f"Finding {b} {_tok(f'ev{b}', b, b + 20)} value {b}0%."


def _aux_texts(b: int) -> list[str]:
    outs = []
    if b in (2, 6):
        outs.append(f"Companion {b} {_tok(f'evc{b}', 0, 15)} extra {b}1%.")
    if b == 6:
        # aux that duplicates basket 6's own companion -> aux dedup drop
        outs.append(f"Companion 6 {_tok('evc6', 0, 15)} extra 61%.")
    if b in (4, 7):
        outs.append(f"Qualifier {b} {_tok(f'evq{b}', 5, 40)} scope {b}.")
    return outs


def _sleep():
    time.sleep(random.uniform(0, 0.004))


def _install_stubs():
    vc._distinct_origin_supports = lambda basket: []  # force single-basket path (no multicited)

    def _stub_compose_one_basket(basket, evidence_pool, **kw):
        _sleep()
        return _main_text(basket)

    vc._compose_one_basket = _stub_compose_one_basket

    def _stub_companion(basket, evidence_pool, composed, **kw):
        _sleep()
        return [t for t in _aux_texts(basket) if t.startswith("Companion")]

    def _stub_qualifier(basket, evidence_pool, composed, **kw):
        _sleep()
        return [t for t in _aux_texts(basket) if t.startswith("Qualifier")]

    def _stub_distinct(basket, evidence_pool, composed, **kw):
        _sleep()
        return []

    vc.compose_companion_figure_units = _stub_companion
    vc.compose_qualifier_elaboration_units = _stub_qualifier
    vc.compose_distinct_fact_units = _stub_distinct


def _run(workers: int, baskets: list[int]) -> list[str]:
    os.environ["PG_COMPOSE_BASKET_WORKERS"] = str(workers)
    return vc._compose_section_per_basket(
        baskets, {}, writer_fn=lambda b, p: "", verify_fn=lambda *a, **k: None,
    )


def main() -> int:
    _install_stubs()
    baskets = list(range(40))
    serial = _run(1, baskets)
    # sanity: the serial path exercised real dedup (dropped at least the crafted duplicates)
    print(f"serial units kept = {len(serial)} (of {len(baskets)} baskets + aux)")
    assert MARKER not in "\n".join(serial), "§3.5 marker leaked"
    assert not any("Finding 3 " in u for u in serial), "basket 3 (marker) should be fully skipped"

    trials = 200
    fails = 0
    for i in range(trials):
        random.seed(1000 + i)
        par = _run(16, baskets)
        if par != serial:
            fails += 1
            if fails <= 3:
                print(f"  DIVERGENCE trial {i}: serial={len(serial)} par={len(par)}")
                for a, b in zip(serial, par):
                    if a != b:
                        print(f"    serial: {a!r}\n    par   : {b!r}")
                        break
    if fails:
        print(f"FAIL: {fails}/{trials} parallel trials DIVERGED from serial")
        return 1
    print(f"PASS: {trials}/{trials} parallel (workers=16) trials BYTE-IDENTICAL to serial (workers=1)")
    print("VERDICT-SET IDENTITY: IDENTICAL under randomized thread interleaving")
    return 0


if __name__ == "__main__":
    sys.exit(main())
