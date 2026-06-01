HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-meta-005 Phase 5 (#989) — Finding-dedup + relevance-floor corpus — BRIEF (acceptance criteria review)

You are reviewing the ACCEPTANCE CRITERIA (this brief), not code.

## Iter-1 → iter-2 changelog (all 4 P1 + 4 P2 addressed)
- P1-1 corroboration input: now extract HOSTNAME (urlparse) per source_url BEFORE
  `registrable_domain`/`count_independent_hosts` (§2.2, §3.1d).
- P1-2 no-unique-claim-loss: now a CONSERVATIVE-SINGLETON rule — a finding is
  mergeable ONLY if subject is known (not "unknown") AND value+unit match AND every
  qualifier the extractor exposes (dose, arm, endpoint_phrase) is PRESENT on BOTH
  sides and equal. Any missing/unknown qualifier or unknown subject → singleton,
  never merged (§2.4, §3.1b).
- P1-3 multi-claim rows: dedup is FINDING-level, then ROW-level retention keeps a
  row unless EVERY finding it asserts is already represented (§3.1e).
- P1-4 ordering: pinned — floor-select → inject → Phase-3 gate on the FULL pre-dedup
  set → terminal proceed/partial decision → dedup the generator-visible pool →
  generator (§3.3).
- P2-1 floor default/fail-loud (§3.2). P2-2 persist `selection_relevance` sidecar
  (§3.2). P2-3 dedup applies to the partial pruned pool too (§3.3). P2-4 manifest
  carries per-cluster member hosts + finding key (§3.1f, §4).

## 1. Goal (plan row 82 + gap D row 27)
1. **Relevance-floor corpus (no arbitrary cap).** Replace the hard
   `PG_LIVE_MAX_EV_TO_GEN=20` cap (`run_honest_sweep_r3.py:2583`,
   `select_evidence_for_generation(max_rows=max_ev)`) with: keep EVERY row whose
   relevance ≥ floor, ranked `relevance × authority` (`authority_score` sidecar
   from Phase 3).
2. **Dedup-by-finding + corroboration.** Cluster the generator-visible rows by the
   *numeric finding asserted*, collapse rehashes to one representative, attach
   `corroboration_count` = independent registrable-domains carrying that finding
   (Knowledge-Based Trust, gap D — sovereign, self-computed, no external service).

## 2. HARD CONSTRAINTS
1. **Gated behind new `PG_USE_FINDING_DEDUP` (default OFF). OFF byte-identical** to
   today's `max_rows=20` selection → generator path. Separately togglable from
   `PG_USE_RESEARCH_PLANNER` (for shadow comparison).
2. **Corroboration counting reuses `src/polaris_graph/authority/corroboration.py`
   (`registrable_domain`, `count_independent_hosts`).** That module expects HOSTS,
   not URLs — so each member `source_url` MUST be reduced to its hostname via
   `urllib.parse.urlparse(...).hostname` (lowercased, strip leading `www.`) BEFORE
   it is handed to the counter. NO host/TLD literals in code; gov-suffixes come from
   corroboration.py's config-driven list.
3. **Field-agnostic.** Finding extraction reuses
   `contradiction_detector.extract_numeric_claims` (already field-agnostic:
   subject, predicate, numeric value, unit; plus dose/arm/endpoint_phrase). NO
   `if domain ==` / clinical literal as an on-path control value.
4. **NO unique-claim loss (safety-critical, clinical-lethal) — CONSERVATIVE
   SINGLETON.** `ExtractedNumericClaim` fields: subject (fallback `"unknown"`),
   predicate, value, unit, dose (default `""`), arm (default `"treatment"`),
   endpoint_phrase (default `""`), evidence_id, source_url. Two findings merge ONLY
   when ALL hold:
   (a) **subject is known** — i.e. NOT the `"unknown"` fallback — AND equal. Any
       claim whose subject is `"unknown"` is FORCED to a per-row-unique singleton key
       and can NEVER merge (covers non-clinical "unknown" subjects too);
   (b) predicate equal;
   (c) numeric value equal within a tight epsilon AND unit equal;
   (d) dose equal, arm equal, endpoint_phrase equal — comparing the raw field values,
       where ABSENT==ABSENT matches (e.g. dose `""` vs `""`), but ABSENT vs PRESENT
       does NOT match (dose `""` vs `"2.4 mg"` → separate). Any qualifier DIFFERENCE
       → separate.
   The default on ambiguity is ALWAYS "keep separate."
   **DOCUMENTED RESIDUAL (must be stated in the module docstring + manifest):**
   `ExtractedNumericClaim` does NOT extract population or comparator. Two findings
   identical on every extracted field but differing only in an UNEXTRACTED qualifier
   (e.g. T2D vs obesity population) could merge. This is bounded to a corroboration
   OVER-count — a TRUST signal, never a safety gate — and NEVER causes unique-claim
   LOSS: the finding the representative asserts (subject/predicate/value/unit/dose/
   arm/endpoint) is identical across all members by construction, and ALL `member_rows`
   + `member_hosts` are preserved on the cluster for audit (#16 + manifest). A future
   phase may add a population/comparator extractor to tighten the key.
5. **Money: zero spend.** Pure CPU. No LLM, no network. Build + smoke spend-free;
   assert no live client constructed.
6. **Dedup is downstream of the Phase-3 gate.** The plan-sufficiency gate and the
   raw retrieved corpus/provenance keep seeing the FULL pre-dedup billed set. Dedup
   only reshapes the generator-visible pool, AFTER the terminal proceed/partial
   decision.
7. snake_case; no `unittest.mock` in `src/`; explicit imports.

## 3. FILE-BY-FILE
### 3.1 NEW `src/polaris_graph/synthesis/finding_dedup.py` (pure)
- `FindingKey` = (subject, predicate, value_rounded, unit, dose, arm, endpoint_phrase)
  built ONLY from known/present fields; if subject is "unknown" the key is made
  intrinsically unique (per-row sentinel) so it can never collide → singleton.
- `FindingCluster`: `finding_key`, `representative_row`, `member_rows`,
  `member_hosts` (deduped registrable-domains), `corroboration_count`.
- `dedup_by_finding(rows, *, gov_suffixes) -> FindingDedupResult`:
  a. For each row, `extract_numeric_claims([row])` → 0..N `ExtractedNumericClaim`.
  b. Build each claim's `FindingKey` per §2.4 (conservative; unknown→singleton).
  c. Group claims by `FindingKey`. Each group = a finding cluster.
  d. `corroboration_count` = `count_independent_hosts(member_hosts, gov_suffixes)`
     where `member_hosts` = `{urlparse(r["source_url"]).hostname (lc, strip www.)
     for r in members}` (P1-1).
  e. **Row retention (P1-3, multi-claim safe):** a row is REDUNDANT (collapsible)
     iff it has ≥1 finding AND EVERY finding it asserts belongs to a cluster whose
     representative is a DIFFERENT row. The representative per cluster = the row
     with the highest `(authority_score, selection_relevance, -index)`. `deduped_rows`
     = all representatives + all rows that have at least one finding for which they
     ARE the representative + all rows with NO extractable finding (qualitative rows
     are always kept). Original order preserved. This guarantees: every distinct
     finding survives on exactly one row, and no row carrying a unique finding is
     dropped.
  f. Attach additive keys onto each retained row that is a representative:
     `corroboration_count`, `independent_hosts` (sorted list), `finding_keys`
     (the cluster keys it represents) — for manifest/#16 auditability (P2-4).
  g. Telemetry: `raw_row_count`, `distinct_finding_count`, `collapsed_row_count`.
- Constructs NO client; imports only stdlib + contradiction_detector + corroboration.

### 3.2 `src/polaris_graph/retrieval/evidence_selector.py`
- `select_evidence_for_generation(..., relevance_floor: float | None = None)`:
  - `relevance_floor is None` (OFF) → existing `max_rows` tier-balanced path,
    BYTE-IDENTICAL.
  - `relevance_floor` set (ON) → keep EVERY row with `relevance ≥ floor`, no
    `max_rows` truncation, ordered `(-(relevance * authority), tier_priority, index)`,
    `authority = row.get("authority_score", 1.0)`.
  - In BOTH modes, persist the computed per-row relevance onto each selected row as
    an additive `selection_relevance` float (P2-2) so finding_dedup's representative
    pick uses the identical score (no recompute drift). OFF-mode adding this key is
    the ONLY delta and must not change selection/order — verify in P5-1.
- `PG_RELEVANCE_FLOOR` (P2-1): read in the sweep, default `0.30`, valid range
  (0.0, 1.0]; if ON-mode and unset → use default; if set-but-unparseable/out-of-range
  → FAIL LOUD (raise), never silently send an unbounded pool.

### 3.3 `scripts/run_honest_sweep_r3.py` — ON-mode pipeline ORDER (P1-4, pinned)
Both the initial pass AND each Phase-4 saturation re-selection:
1. `select_evidence_for_generation(relevance_floor=PG_RELEVANCE_FLOOR)` (no cap).
2. Inject V30 contract rows + upload rows (the existing prepend).
3. Phase-3 `assess_plan_sufficiency` on this FULL pre-dedup `evidence_for_gen`.
4. Saturation loop runs to its terminal decision (Phase 4) — gate ALWAYS sees the
   pre-dedup set.
5. ONLY AFTER STOP_SUFFICIENT (full plan) OR partial_saturation (pruned plan):
   `dedup_by_finding(evidence_for_gen)` → pass `deduped_rows` to the generator.
   Dedup applies to the partial pruned generator-visible pool too (P2-3).
6. Persist `manifest["finding_dedup"]` = telemetry + per-cluster {finding_key,
   corroboration_count, member_hosts} (P2-4).
OFF-mode (`PG_USE_FINDING_DEDUP` unset): unchanged single `max_rows=20` path, no
dedup, manifest key absent.

## 4. GREEN (exit, #989 + plan row 82)
- distinct-finding < raw-source on a rehash corpus, with **NO unique-claim loss**
  (every distinct finding survives on exactly one rep; multi-finding rows safe).
- No arbitrary count cap on-mode (relevance floor).
- `relevance × authority` ranking.
- `corroboration_count` = independent registrable-domains via corroboration.py
  (hosts parsed from URLs; no literals).
- OFF byte-identical. Phase-3 gate sees the full pre-dedup set.

## 5. SMOKE (`tests/polaris_graph/synthesis/test_finding_dedup_phase5.py` + selector)
Plain-class stubs, no unittest.mock. Non-relaxable:
- **P5-1 OFF byte-identity**: flag OFF → selector returns exact 20-cap selection,
  same order; only additive `selection_relevance` key; no dedup; manifest unchanged.
- **P5-2 collapse rehashes**: 3 rows, same finding, 3 distinct registrable-domains →
  1 rep, `corroboration_count == 3`.
- **P5-3 NO unique-claim loss (clinical-lethal)**: same (subject,predicate,value)
  but different dose/endpoint → SEPARATE (2 reps). PLUS: subject "unknown" on both →
  SEPARATE singletons (never merged on unknown).
- **P5-3b multi-claim row**: row A asserts finding X (dup of row B) AND finding Y
  (unique) → row A is RETAINED (its unique finding Y survives).
- **P5-4 relevance-floor, no cap**: 35 rows ≥ floor, ON → all 35 kept; sub-floor
  dropped.
- **P5-5 relevance×authority ranking**: high-authority high-relevance ranks above
  high-relevance low-authority.
- **P5-6 single-host** → `corroboration_count == 1`.
- **P5-7 same-domain duplicates** (3 rows, one registrable-domain, different paths) →
  `corroboration_count == 1` (urlparse host → registrable_domain dedup).
- **P5-8 field-agnostic**: a non-clinical numeric finding clusters identically.
- **P5-9 qualitative rows** (no numeric finding) → always kept as singletons.
- **P5-10 ordering**: dedup runs AFTER the Phase-3 gate; assert the object the gate
  receives is the full pre-dedup set and dedup only touches the generator input.
- **P5-11 floor fail-loud**: ON-mode + invalid `PG_RELEVANCE_FLOOR` → raises.
Then a retrieval/generator regression subset for OFF byte-identity.

## 6. Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
