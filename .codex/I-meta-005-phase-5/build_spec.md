# Phase 5 BUILD SPEC — finding-dedup + relevance-floor (#989). BINDING.

The APPROVED brief `.codex/I-meta-005-phase-5/brief.md` (Codex APPROVE iter 2) is the
design contract. Implement it EXACTLY. This is the file-by-file checklist + the two
iter-2 P2 wording clarifications folded in.

## iter-2 P2 clarifications (BINDING)
- **P2-1 unknown-subject sentinel is per-CLAIM, not per-row.** When a claim's subject
  is the `"unknown"` fallback, its `FindingKey` gets a sentinel unique to
  `(evidence_id, claim_index_within_row)` so even multiple unknown claims on the SAME
  row never merge with each other.
- **P2-2 simplify retention.** `deduped_rows` = (every row that is the representative
  of ≥1 finding cluster) ∪ (every row with NO extractable numeric finding). A row
  that has findings but is the rep of none is REDUNDANT (dropped). Original order
  preserved. (This is equivalent to the brief's §3.1e, stated without redundancy.)

## FILE-BY-FILE
1. **NEW `src/polaris_graph/synthesis/finding_dedup.py`** (pure; brief §3.1):
   - imports: stdlib (`dataclasses`, `urllib.parse`), `extract_numeric_claims` from
     `..retrieval.contradiction_detector`, `registrable_domain` +
     `count_independent_hosts` from `..authority.corroboration`.
   - `_host_of(url) -> str`: `urlparse(url).hostname or ""`, lowercase, strip leading
     `www.`. Empty on unparseable.
   - `FindingKey` namedtuple/dataclass (frozen, hashable): `subject, predicate,
     value_rounded, unit, dose, arm, endpoint_phrase` — OR a per-claim sentinel
     string when subject == "unknown" (P2-1). `value_rounded = round(value, 3)`.
   - `FindingCluster` (subject..): `finding_key`, `representative_row`, `member_rows`,
     `member_hosts` (sorted unique registrable-domains), `corroboration_count`.
   - `FindingDedupResult`: `deduped_rows`, `clusters`, `raw_row_count`,
     `distinct_finding_count`, `collapsed_row_count`.
   - `dedup_by_finding(rows, *, gov_suffixes) -> FindingDedupResult`:
     a. For each row index i, `claims = extract_numeric_claims([row])`; enumerate
        claims with claim_index j.
     b. Build `FindingKey` per claim (conservative, brief §2.4): subject "unknown" →
        sentinel `f"__unknown__:{evidence_id}:{j}"`; else
        `(subject, predicate, round(value,3), unit, dose, arm, endpoint_phrase)`.
        Comparison is exact-equality on the tuple; ABSENT==ABSENT (`""`==`""`) matches
        naturally, ABSENT vs PRESENT differs naturally.
     c. Group `(row_index, claim, key)` by `key`. Each group = a `FindingCluster`.
     d. representative row of a cluster = the member row with max
        `(authority_score, selection_relevance, -row_index)` — read
        `row.get("authority_score", 0.0)` and `row.get("selection_relevance", 0.0)`.
     e. `member_hosts` = sorted unique
        `registrable_domain(_host_of(r["source_url"]), gov_suffixes)` over members
        (drop empties); `corroboration_count = count_independent_hosts([...hosts...],
        gov_suffixes)`.
     f. Rep-rows set = {rep of each cluster}. `deduped_rows` = rows whose index is a
        rep of ≥1 cluster, PLUS rows with ZERO extracted claims (qualitative), in
        original order. (A finding-bearing row that is the rep of no cluster is
        dropped.)
     g. Attach additive keys on each rep row (mutate a shallow copy, NOT the input —
        keep `dedup_by_finding` pure w.r.t. caller's list): `corroboration_count`
        (max across the clusters it reps), `independent_hosts` (union, sorted),
        `finding_keys` (list of the cluster keys it reps, as JSON-safe tuples/strings).
     h. telemetry counts.
   - **Module docstring MUST state the brief §2.4 DOCUMENTED RESIDUAL** (population/
     comparator not extracted → bounded corroboration over-count, never claim loss).
   - Resolve `gov_suffixes`: the caller (sweep) passes the same gov-suffix tuple the
     authority model uses; the module does NOT hardcode it. Provide a thin loader
     reuse if corroboration.py exposes one; else accept the tuple as a param.
2. **`src/polaris_graph/retrieval/evidence_selector.py`** (brief §3.2):
   - add `relevance_floor: float | None = None` param.
   - None → existing `max_rows` path BYTE-IDENTICAL, EXCEPT every selected row gains
     an additive `selection_relevance` float (the score already computed). Adding the
     key must NOT change which rows are selected or their order — pin in P5-1.
   - set → keep all rows with `relevance >= relevance_floor`, order
     `(-(relevance*authority), tier_priority, original_index)`,
     `authority = row.get("authority_score", 1.0)`; also stamp `selection_relevance`.
   - selection_strategy note string distinguishes the two modes.
3. **`scripts/run_honest_sweep_r3.py`** (brief §3.2 floor env + §3.3 order):
   - `PG_USE_FINDING_DEDUP` (default OFF). `PG_RELEVANCE_FLOOR` default `0.30`,
     range (0.0, 1.0]; ON-mode invalid/out-of-range → raise (fail loud).
   - ON-mode pipeline ORDER (initial AND each Phase-4 saturation re-selection):
     floor-select (no cap) → inject V30+upload → Phase-3 gate on FULL pre-dedup set →
     saturation terminal decision → `dedup_by_finding` on the final generator-visible
     `evidence_for_gen` (success full plan OR partial pruned pool) → generator.
   - Persist `manifest["finding_dedup"]` = telemetry + per-cluster {finding_key,
     corroboration_count, member_hosts}. OFF-mode: unchanged `max_rows=20`, no dedup,
     key absent.
   - gov_suffixes: load via the SAME path the authority model uses (Phase 0a config).

## SMOKE — `tests/polaris_graph/synthesis/test_finding_dedup_phase5.py`
Implement P5-1..P5-11 (brief §5) + P5-3b multi-claim row. Plain-class stubs, no
unittest.mock. Non-relaxable: P5-1 OFF byte-identity, P5-3/P5-3b unique-claim-loss,
P5-7 same-domain host dedup, P5-10 gate-sees-pre-dedup, P5-11 floor fail-loud. Run
`python -m pytest tests/polaris_graph/synthesis/test_finding_dedup_phase5.py -q -p
no:cacheprovider` green; then a retrieval/generator regression subset for OFF
byte-identity.
