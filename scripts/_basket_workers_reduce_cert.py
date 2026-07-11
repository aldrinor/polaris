"""FAST deterministic certification for PG_COMPOSE_BASKET_WORKERS map-then-reduce.

Drives the REAL ``_compose_section_per_basket`` twice through the SAME entry point — once serial
(workers=1 => original loop) and once parallel (workers=8 => map-then-reduce) — with the pure compose
helpers monkeypatched to deterministic per-basket outputs (a small sleep forces genuine thread
interleaving so a reduce race would surface). The REAL dedup path (_resolved_spans / _dedup_norm /
_number_tokens / _attach_citation_tokens / _consolidate_same_meaning_units) runs unpatched, so this
certifies the order-sensitive survivor selection is byte-identical between the two arms across:
  * text-identity collapse + citation UNION-consolidation onto the survivor,
  * same-footprint no-new-number collapse vs same-footprint NEW-number survival,
  * the §3.5 insufficient-evidence marker skip (and its aux being skipped with it),
  * companion (aux) units deduped against the running seen_* state in original basket order.
Exit 0 iff the two arms produce the byte-identical ``out`` list. Zero LLM, zero network.
"""
import os
import sys
import time

os.environ["PG_CROSS_SOURCE_SYNTHESIS"] = "0"   # isolate the per-basket map/reduce (skip the tail pass)
os.environ.setdefault("PG_VERIFIED_COMPOSE_MULTICITED", "0")  # route every basket via _compose_one_basket
sys.path.insert(0, os.getcwd())

from src.polaris_graph.generator import verified_compose as vc  # noqa: E402

# Each fake basket is just an int id; the patched producers key off it. `direct_quote`/span tokens are
# authored so the REAL dedup helpers make genuine keep/collapse decisions.
_MAIN = {
    0: "Alpha finding is significant.[#ev:s1:0-10]",         # kept
    1: "Beta finding is notable.[#ev:s2:5-20]",              # kept
    2: "Alpha finding is significant.[#ev:s3:0-10]",         # text-identical to #0 -> collapse+union
    3: "[insufficient verified evidence for this basket]",   # §3.5 marker -> skipped (+ its aux skipped)
    4: "Beta finding is notable.[#ev:s2:5-20]",              # same footprint+text as #1 -> collapse
    5: "Gamma metric rose 5 percent.[#ev:s2:5-20]",          # same footprint as #1 but NEW number 5 -> kept
    6: "Delta outcome improved.[#ev:s4:0-30]",               # kept
}
# Companion (aux) units, keyed by basket id. Basket 6's companion duplicates basket 0's companion text
# so it must collapse in BOTH arms at the same running-state point.
_COMPANION = {
    0: ["Companion note about alpha.[#ev:s1:40-55]"],
    3: ["Should never appear (parent is a marker).[#ev:s9:0-9]"],  # parent skipped -> aux never reached
    6: ["Companion note about alpha.[#ev:s7:40-55]"],  # text-dup of basket 0's companion -> collapse
}


def _fake_compose_one_basket(basket, evidence_pool, **kw):
    time.sleep(0.02)  # force overlap between MAP threads so any shared-state race would surface
    return _MAIN[basket]


def _fake_companions(basket, evidence_pool, composed, **kw):
    time.sleep(0.01)
    return list(_COMPANION.get(basket, []))


def _run(workers: int):
    os.environ["PG_COMPOSE_BASKET_WORKERS"] = str(workers)
    return vc._compose_section_per_basket(
        list(_MAIN.keys()), {},
        writer_fn=lambda b, p: "", verify_fn=lambda *a, **k: ("ENTAILED", "ok"),
    )


def main() -> int:
    vc._distinct_origin_supports = lambda basket: []          # every basket -> _compose_one_basket
    vc._compose_one_basket = _fake_compose_one_basket
    vc.compose_companion_figure_units = _fake_companions      # default-ON pass

    t0 = time.monotonic()
    serial = _run(1)
    t1 = time.monotonic()
    parallel = _run(8)
    t2 = time.monotonic()

    print(f"serial   (workers=1) units={len(serial)} wall={t1 - t0:.2f}s")
    print(f"parallel (workers=8) units={len(parallel)} wall={t2 - t1:.2f}s")
    for i, u in enumerate(serial):
        print(f"  serial[{i}]   = {u!r}")
    for i, u in enumerate(parallel):
        print(f"  parallel[{i}] = {u!r}")

    ok = serial == parallel
    # Assert the reduce actually did meaningful work (else the test is vacuous).
    joined = "\n".join(serial)
    assert "insufficient verified evidence" not in joined, "marker leaked -> §3.5 filter broken"
    assert "Should never appear" not in joined, "aux of a marker basket leaked"
    assert "s3:0-10" in joined, "citation UNION-consolidation onto survivor missing (basket 2)"
    assert "rose 5 percent" in joined, "same-footprint NEW-number unit wrongly dropped (basket 5)"
    print(f"\nspeedup serial/parallel = {(t1 - t0) / max(1e-9, (t2 - t1)):.1f}x "
          f"(MAP genuinely concurrent if >1x)")
    print(f"=== BASKET-WORKERS REDUCE IDENTITY: {'IDENTICAL (PASS)' if ok else 'DIVERGED (FAIL)'} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
