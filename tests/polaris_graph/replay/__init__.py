"""I-perm-009 behavioral replay harness.

Offline, deterministic replay of the D8 release policy + the §-1.1 zero-fabrication
invariant over SAVED real-run evidence (outputs/audits/beatboth8/drb_76/). This is the
proof ledger for the permanent-fix program (I-perm-001..008): every fix is proven on real
saved data BEFORE any paid re-run. No network, no spend, no model calls.

Modules:
    saved_run_loader   - typed loader for a saved run directory's artifacts.
    d8_replay_harness  - reconstruct D8 inputs from saved data + replay apply_d8_release_policy
                         (reuses the production helpers -> zero drift), with a labelled
                         corpus-wide-satisfaction SIMULATION of the I-perm-002 target.
    cited_span_audit   - the §-1.1 zero-fabrication invariant: every numeric shipped in a
                         claim appears verbatim in its cited span.
"""
