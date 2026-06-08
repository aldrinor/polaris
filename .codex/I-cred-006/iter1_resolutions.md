## 7. ITER-1 RESOLUTIONS (binding amendments — supersede §3 Q2 / §4 AC2; all implemented in the diff)

Per your iter-1 verdict:
- **Q1 CONFIRMED:** ship only the pure aggregator; defer journal-floor removal + corpus-adequacy wiring + clinical per-claim veto to I-cred-006b (own flag/brief).
- **Q3 CONFIRMED:** a canonical with no P2 judgment → `credibility_weight = 1.0` (mass = pure authority), origin NOT dropped.
- **Q2 RESOLVED (P1-1) — HARD PRECONDITION, not fail-soft:** the canonical origin is a REQUIRED, VALIDATED input. Each COLLAPSED `origin_cluster_id` must carry EXACTLY ONE row with `is_canonical_origin=True` (Phase-4 metadata merged onto rows). The aggregator FAILS LOUD (`ValueError`) on a missing OR duplicate canonical for any collapsed origin — it NEVER falls back to a member, so a copy can never become the mass carrier. An uncollapsed row (no `origin_cluster_id`) is its own singleton canonical. (Implemented: validation loop over `collapsed_origins`; the old `sorted(members)[0]` fallback is removed.)
- **AC2 reframed (P2-1) — the binding invariant is NO INFLATION:** `weight_mass` must NOT INCREASE under copy additions. Equality holds for dated / unchanged-canonical / higher-authority-copy fixtures; but per #1161's conservative-min, if Phase-4 re-marks a LOWER-authority member as canonical (all-undated), the mass may DROP (monotonic non-increase). Test `test_lower_authority_copy_becoming_canonical_lowers_mass_never_inflates` covers the drop; `test_single_origin_copies_uninflatable` covers the higher-authority-copy equality.
- **New AC (P2-2) — copy-only support:** a claim cluster supported ONLY by a derivative copy uses the GLOBAL Phase-4 canonical row's authority for that origin, never the copy's; `copy_count` counts supporting members that are NOT the canonical (no 0-copy undercount). Test `test_copy_only_support_uses_global_canonical`.
- **New ACs — fail-loud:** `test_missing_canonical_fails_loud`, `test_duplicate_canonical_fails_loud`.

SMOKE after these amendments: 18 passed.
