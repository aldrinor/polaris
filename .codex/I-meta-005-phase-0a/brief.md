# IMPLEMENTATION BRIEF — Phase 0a (GH #983): Computed Authority Model behind `PG_USE_AUTHORITY_MODEL`

Parent: #982 — `docs/polaris_fundamental_rearchitecture_plan.md` (Codex-APPROVED).
Issue: #983 (Phase 0a). Branch: `bot/I-fund-0a`. PR queued for **operator** merge (no auto-merge per `forbidden_autonomous_merge_is_cage_bypass_2026_05_20`).

> NOTE FOR OPERATOR: `state/active_issue.json` is STALE (points at #935 / I-meta-005). #983 is the real Phase-0a issue. Re-point `active_issue.json` to `I-fund-0a` / gh #983 before this PR merges.

---

## §0. HARD ITERATION CAP directive (verbatim §8.3.1 — Codex reads this first)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

---

## §1. SCOPE

### 1.1 What Phase 0a BUILDS
1. A new module `src/polaris_graph/authority/authority_model.py` that computes a **field-agnostic** credibility result from the five plan signals (A scholarly-graph, B institutional via ROR, C structural junk, D corroboration/KBT, E recency) — **no named-host allowlist anywhere in code**.
2. Versioned **DATA** files under `config/authority/*` holding ALL source knowledge (PSL gov suffixes, ROR-type→class map, OpenAlex field weights, junk regex patterns, recency profile, blend weights, the clinical T1–T7 view) — LAW VI, contract part (1).
3. A **clinical view renderer** that maps the computed authority primitives → the existing T1–T7 `TierLevel` so the model can run as a drop-in behind the kill-switch (primitives→tiers, NOT hosts→tiers).
4. The OpenAlex wiring extension required for signals A and B (extend `select=` fieldset + `OpenAlexWork` dataclass + sqlite cache schema) — see §3.4 P0 gap.
5. A **shadow harness** + the 6-group HEAVY offline smoke suite (§6).

### 1.2 What Phase 0a does NOT do (explicit non-goals — guards against scope creep)
- Does **NOT remove** `tier_classifier.py`'s frozensets. They stay live and unchanged. Removal is a later phase after the shadow run proves parity. 0a runs the new model in **shadow behind the kill-switch only**.
- Does **NOT change** the default runtime: `PG_USE_AUTHORITY_MODEL` defaults OFF; with it OFF, behaviour is byte-identical to HEAD.
- Does **NOT wire** `authority_score` / `source_class` / `corroboration_count` / `authority_confidence` into any downstream gate (adequacy gate / evidence selector / generator). Those fields are emitted but **inert** in 0a — they are consumed in phases 0b/3/5. (This is why 0a cannot regress the clinical wedge: the adequacy gate + selector are driven 100% by the T1–T7 string; see §3.3.)
- Does **NOT** serve or call the Granite Sentinel intrinsic scorer online. The optional intrinsic LLM scorer (= the LOCKED `ibm-granite/granite-guardian-4.1-8b` Sentinel, open-weight) is **OFF** in 0a offline smoke (no served model offline).
- No "while we're at it" polish, no unrelated refactors, no doc rewrites beyond the new module's own docstrings + `docs/file_directory.md` entry.

---

## §2. FILE LAYOUT (exact paths — careful, no sprawl)

```
src/polaris_graph/authority/
  __init__.py                 # explicit exports only (no wildcard); re-exports score_source_authority + AuthorityResult + SourceClass
  authority_model.py          # ENTRY: score_source_authority(signals, *, corpus_ctx=None) -> AuthorityResult ; blends A-E
  citation_graph.py           # Signal A: scholarly-graph authority from OpenAlex/Crossref fields (pure fn, data-driven)
  institutional.py            # Signal B: ROR-type + country_code + PSL gov pre-filter + issuer self-desc backstop
  junk_detection.py           # Signal C: structural junk (schema.org PressRelease / login-wall / blog path / self-interest) — regex, no hosts
  corroboration.py            # Signal D: independent-host agreement (KBT); eTLD+1 via shared PSL table
  recency.py                  # Signal E: temporal-fit decay
  source_class.py             # SourceClass enum + AuthorityResult dataclass + AuthorityConfidence enum
  clinical_view.py            # renderer: AuthorityResult -> TierLevel (T1-T7|UNKNOWN) using config/authority/clinical_view.yaml
  data_loader.py              # one cached loader for all config/authority/* versioned data files (fail-loud if missing)

config/authority/
  VERSION                     # single version string for the whole data bundle (bumped on any data change)
  scholarly_weights.yaml      # Signal A weights/anchors/norms
  ror_type_class_map.yaml     # Signal B: ROR type -> source_class
  psl_gov_suffixes.txt        # Signal B+D: versioned Public Suffix List gov subset snapshot (with provenance header: source URL + fetch date)
  junk_patterns.yaml          # Signal C: versioned regex by junk-class, each with precedence + ceiling
  recency_profile.yaml        # Signal E: default_horizon_years + decay_halflife
  blend_weights.yaml          # A-E blend weights + JUNK_CEIL + confidence-floor rules
  clinical_view.yaml          # primitives -> T1..T7 thresholds (the clinical VIEW, NOT a host map)

tests/fixtures/authority/
  clinical_200_urls.jsonl              # ~200 frozen clinical sources w/ reconstructed full ClassificationSignals + frozen HEAD tier (S2)
  clinical_tier_baseline_off.json      # frozen HEAD ClassificationResult for the 1,529-URL OFF-path byte-identity sweep (S1)
  cross_field_50_urls.jsonl            # >=50 non-clinical URLs (law/physics/policy/JP-gov/African-energy) + mocked OpenAlex/ROR
  adversarial_thin_field.jsonl         # grey-lit / non-English / niche-regional, deliberately THIN OpenAlex
  junk/{press_release,login_wall,blog,self_interest,control_primary}.json
  openalex_mocks/*.json                # frozen OpenAlex /works + /sources responses keyed by work_id (offline replay)

tests/polaris_graph/authority/
  test_authority_reproduces_clinical_tier_view.py   # S2
  test_kill_switch_off_byte_identical.py            # S1 + determinism
  test_authority_cross_field_sane.py                # S3
  test_thin_field_honest_low_confidence.py          # S4 (contract parts 3+4)
  test_zero_host_literal_in_authority_code.py       # S4-grep (contract parts 1+2)
  test_junk_detection.py                            # S5
  test_adequacy_selector_on_vs_off_integration.py   # S5-integration

scripts/
  freeze_clinical_tier_baseline.py    # one-time: run HEAD classifier OFF over the 1,529 corpus URLs -> baseline fixtures (committed)
  authority_shadow_diff.py            # shadow harness: run ON vs OFF over fixtures, emit per-URL diff + confusion matrix
```

Folder discipline: ALL new code under the single new package `src/polaris_graph/authority/`. ALL new data under the single new dir `config/authority/`. No utility dumped into existing modules. One responsibility per file (LAW V / §4.2).

---

## §3. THE DROP-IN INTERFACE (real file:line — consumers untouched when OFF)

### 3.1 Exact entry-point contract (verified against HEAD)
`src/polaris_graph/retrieval/tier_classifier.py`:
- Public entry `classify_source_tier(signals: ClassificationSignals) -> ClassificationResult` — **L1069**.
- Thin wrapper `classify_url(url, content_length=0, **extra) -> ClassificationResult` — **L1863**.
- Input dataclass `ClassificationSignals` — **L83-108** (fields: `url, fetched_content_length, openalex_publication_type, openalex_source_type, openalex_is_retracted, openalex_venue, openalex_is_peer_reviewed: bool|None, source_type_hint, publisher, author_affiliations, funding_disclosures, title, body_article_type`).
- Output dataclass `ClassificationResult` — **L111-123**: `tier: TierLevel, confidence: float, reasons: list[str], matched_rules: list[str], signals_used: dict`; `is_decided` property at L121-123.
- `TierLevel` enum — **L70-80** (T1–T7 + UNKNOWN).
- `_normalize_domain(url)` — **L718-727** (eTLD-ish host normalize, strips `www.`); reuse for the eTLD+1 dedup in Signal D, BUT note it does NOT compute a true registrable domain — Signal D must use the PSL table for eTLD+1 (flag below).

### 3.2 The dispatcher (the ONLY switch point)
`classify_source_tier` (L1069) is wrapped:
```python
def classify_source_tier(signals: ClassificationSignals) -> ClassificationResult:
    if os.getenv("PG_USE_AUTHORITY_MODEL", "0").lower() in ("1", "true", "yes"):
        return _classify_via_authority_model(signals)   # ON: score + render clinical view + attach AuthorityResult
    return _classify_source_tier_rules(signals)          # OFF: the existing body, renamed, byte-identical
```
- The entire existing body (L1082 onward through L1859) is renamed to `_classify_source_tier_rules` with **zero logic edits** (S1 enforces byte-identity).
- `_classify_via_authority_model` calls `authority.score_source_authority(signals)` → `AuthorityResult`, renders the clinical T1–T7 VIEW (`clinical_view.py`), and returns a `ClassificationResult` with the SAME five legacy fields populated PLUS `signals_used["authority"] = asdict(authority_result)` (additive; no consumer reads it yet — shadow only).
- `ClassificationResult` is extended **additively** (new fields default `None`): `authority_score: float|None`, `source_class: str|None`, `corroboration_count: int|None`, `authority_confidence: str|None`. OFF path never sets them (stay `None`) → byte-identical to HEAD for existing consumers.

### 3.3 Consumer map (what each reads — file:line — proves nothing breaks)
| Consumer | file:line | Reads | Impact when OFF | Impact when ON |
|---|---|---|---|---|
| `live_retriever` (PRIMARY prod caller) | `live_retriever.py:1789-1811` builds signals + calls L1801; reads `.tier.value` (L1807), `.confidence` (L1808), `.matched_rules[0]` (L1809), `.reasons` (L1810); `evidence_rows[i]["tier"]` (L1839) | none (same obj) | reads same 4 fields off the rendered view; unaffected |
| `openalex_client.authority_tier_t7` | `openalex_client.py:70-115` builds signals (L102-113), calls L114, returns `result.tier.value` (L115) | none | reads `.tier.value` off rendered view; unaffected |
| `deepener_sweep_adapter` | docstring mention L6 (routes via `run_live_retrieval`) | none | none — no direct call |
| adequacy gate | `nodes/corpus_adequacy_gate.py` consumes `tier_counts: dict[str,int]` keyed "T1".."T7"/"UNKNOWN" (NOT the result obj) | none | driven by the T1–T7 STRING only → unaffected by the new authority fields |
| evidence selector | `retrieval/evidence_selector.py` consumes the tier STRING off CorpusSource/dict (NOT the result obj) → T1/T2/T3 quota floors | none | driven by the T1–T7 STRING only → unaffected |

**Behavioral truth (load-bearing):** the adequacy gate + evidence selector + generator are driven 100% by the T1–T7 string carried on `CorpusSource.tier` / `evidence_rows["tier"]`. The four new authority fields are inert until later phases. THIS is why 0a cannot regress the clinical wedge as long as (a) OFF is byte-identical (S1) and (b) ON reproduces the clinical tier view ≥95% (S2).

### 3.4 P0 WIRING GAP (real, load-bearing — Codex must confirm the fix shape)
Signals A and B require OpenAlex/Crossref fields that are **NOT currently fetched**. Verified at HEAD:
- `OpenAlexWork` dataclass carries ONLY 8 fields — `openalex_client.py:50-59`: `work_id, doi, title, type, source_type, source_name, publication_year, is_retracted`. **No** `cited_by_count`, **no** venue `summary_stats` (`h_index`/`2yr_mean_citedness`), **no** `is_core`, **no** `is_in_doaj`, **no** `apc_prices`, **no** institution `ror`/`country_code`.
- The sqlite cache schema mirrors only those 8 — `openalex_client.py:122-135` (CREATE TABLE) + `:148-164` (`_cache_get` SELECT/construct).
- The `/works` request uses **no `select=` param** (grep for `select=` returns zero), so it relies on OpenAlex defaults; the signal-A/B fields are not requested.

**Required in 0a:** extend the OpenAlex `/works` `select=` fieldset + `OpenAlexWork` dataclass + the cache CREATE TABLE + `_cache_get`/`_cache_put` to carry `cited_by_count`, venue `summary_stats`, `is_core`, `is_in_doaj`, `apc_prices`, and `authorships[].institutions[].ror`+`country_code`. Where a field is absent in an OpenAlex record, the model degrades to `authority_confidence=LOW` (honest), NEVER fabricates. **Codex must web-verify the exact OpenAlex field paths (see §9).** This is the single biggest wiring item — it is in-scope for 0a and must not be glossed.

---

## §4. THE 5 SIGNALS (computation spec — each loads from versioned DATA, not code literals)

### Signal A — Scholarly-graph authority (`citation_graph.py`)
- **Inputs (OpenAlex /works + /sources):** `cited_by_count`; venue `summary_stats.h_index` + `summary_stats.2yr_mean_citedness`; `is_core`; `is_in_doaj` vs missing-DOAJ + high `apc_prices` (predatory-OA smell); `is_retracted` (hard-exclude → UNKNOWN, preserves current R0 at `tier_classifier.py:1094-1103`).
- **Compute:** `a = w_cite·squash(log1p(cited_by_count)) + w_hindex·squash(h_index/H_NORM) + w_recent·clamp(2yr_mean_citedness/C_NORM) + is_core_bonus − predatory_penalty(¬is_in_doaj ∧ apc_prices>APC_FLOOR)`; `squash`=min-max vs percentile anchors; clamp [0,1].
- **DATA:** `scholarly_weights.yaml` {w_cite,w_hindex,w_recent,H_NORM,C_NORM,APC_FLOOR,is_core_bonus,predatory_penalty,percentile_anchors}. No venue names.
- **Confidence:** both `cited_by_count` AND `summary_stats` present → HIGH; only `type`/`source_type` → LOW.
- **Peer-review inference:** OpenAlex has NO `is_peer_reviewed` flag — inferred from `is_core` + `type ∈ {article,review}` + `source_type=journal` (the inference already hard-coded at `openalex_client.py:109-111`). **Codex must web-verify** (§9).

### Signal B — Institutional (the region generalizer) (`institutional.py`)
- **Inputs (load-bearing = OpenAlex ROR):** `authorships[].institutions[].ror`, ROR `type ∈ {Government,Education,Healthcare,Facility,Nonprofit,Company,Other}`, `country_code`. **PSL gov pre-filter (cheap, secondary):** host carries a gov-style public suffix (`*.gov`, `*.gc.ca`, `*.go.jp`, `*.gouv.fr`, `*.go.ke`, `*.gob.mx`). **Issuer self-desc backstop:** schema.org `GovernmentOrganization` / `<meta name="dc.publisher">` matching an official-issuer pattern.
- **Compute:** `source_class` = PRIMARY-OFFICIAL if ROR type ∈ {Government, Healthcare-regulator} OR PSL gov-suffix OR issuer-self-desc official; PRIMARY-SCHOLARLY if ROR Education + journal; SECONDARY/COMMENTARY otherwise. `score_B` = max of the sub-signals' weights.
- **CRITICAL (plan §2 Codex correction):** PSL is a DNS suffix list, NOT a trust signal, and MISSES `canada.ca` / `bundesbank.de` / `rbi.org.in` (no gov suffix). So **ROR institution-type is load-bearing**; PSL is only a fast pre-filter; self-desc is the backstop. This is exactly how the model generalizes beyond the named biomedical hosts.
- **DATA:** `psl_gov_suffixes.txt` (versioned PSL gov subset snapshot w/ provenance header) + `ror_type_class_map.yaml` (ROR type → source_class).
- **Confidence:** ROR-resolved → HIGH; PSL-only → MEDIUM; self-desc-only → LOW.
- **Codex must web-verify** the PSL canonical source + gov ccTLD coverage AND the exact ROR `type` enum values + OpenAlex ROR field path (§9).

### Signal C — Structural junk detection (`junk_detection.py`) — replaces ~20 deny frozensets
- **Inputs (structural, NO hosts):** fetched content + HTTP metadata. Regex/JSON-LD over: schema.org `"@type":"PressRelease"` / "FOR IMMEDIATE RELEASE" / `/press-release/`; schema.org `SocialMediaPosting` / login-wall (`"loginwall"`, paywall JSON-LD `isAccessibleForFree:false`); self-published path shapes `/blog/`, `/pulse/`, `/@` (PATH shapes, not host names); self-interest = host-org token ∈ the vendor/product named in the claim.
- **Compute:** any junk pattern fires → `source_class ∈ {COMMENTARY,UGC,PRESS_RELEASE}`, `authority_score` capped at `JUNK_CEIL` (default 0.25), reason appended. Field-agnostic replacement for `INDUSTRY_MARKETING_DOMAINS`/`SOCIAL_PLATFORM_DOMAINS`/`VENDOR_BLOG_DOMAINS`/`MARKET_RESEARCH_DOMAINS`.
- **DATA:** `junk_patterns.yaml` — regex by junk-class w/ precedence + ceiling.
- **Confidence:** HIGH when JSON-LD present; MEDIUM on path-only heuristic.

### Signal D — Corroboration / Knowledge-Based-Trust (the sovereign multiplier) (`corroboration.py`)
- **Input:** `corroboration_count` = number of **independent hosts/institutions** in the current corpus asserting the same finding, post-dedup-by-finding. "Independent" = distinct registrable domain (eTLD+1) via the shared PSL table (NOT bare `_normalize_domain`, which gives host not eTLD+1).
- **Compute:** `score_D = squash(log1p(corroboration_count))`; additive multiplier on the blend.
- **Phase-0a behaviour:** single-source scoring has no corpus context yet → `corroboration_count` defaults to 1, wired live in a later phase. The FIELD is emitted now (stable schema); smoke asserts it is present + defaults honestly. (KBT rationale: arXiv 1502.03519; domain-general — the primary defense for thin-OpenAlex fields.)
- **DATA:** none beyond the shared PSL eTLD+1 table.

### Signal E — Recency / temporal-fit (`recency.py`)
- **Inputs:** OpenAlex `publication_year` (already on `OpenAlexWork` L58) OR HTTP `Last-Modified`; planner `recency_horizon_years` (absent in 0a → neutral 1.0).
- **Compute:** `score_E = recency_decay(now − year, horizon)`; neutral when no recency need.
- **DATA:** `recency_profile.yaml` {default_horizon_years, decay_halflife}.

### Blend + output (`authority_model.py` + `source_class.py`)
`authority_score = clamp01(Σ w_signal·score_signal) · junk_cap`; weights from `blend_weights.yaml` (one default profile in 0a). **`AuthorityResult`:** `authority_score ∈ [0,1]`, `source_class: SourceClass` enum, `corroboration_count: int`, `authority_confidence ∈ {HIGH,MEDIUM,LOW}` (= MIN of per-signal confidences that fired), `reasons: list[str]`. Optional intrinsic scorer = LOCKED Granite Sentinel (open-weight) — OFF in 0a offline smoke.

---

## §5. THE 4-PART CALIBRATED AUTHORITY CONTRACT (binding acceptance gate)

Each part is a MECHANICAL offline check (a test, not prose):
1. **NO host/suffix/platform literal in CODE.** PSL, ROR-type maps, OpenAlex surface, junk patterns are ALL loaded as VERSIONED DATA files (`config/authority/*`). Verified by S4-grep (Test 3).
2. **Zero-host grep over the code returns zero.** A regex scan over `src/polaris_graph/authority/**.py` for host/suffix/platform literals returns 0 matches; `config/authority/*` data files are git-tracked + diffable + non-empty. Verified by Test 3.
3. **Per-source `authority_confidence` is honest.** A thin-OpenAlex source (few/no fields) is labeled LOW-confidence, NEVER mislabeled HIGH. Verified by Test 4.
4. **Adversarial thin-field fixtures scored honest-low.** Grey-lit / non-English / niche-regional sources land in the honest-uncertain mid-band with LOW confidence — NOT false-authority (>0.8) and NOT false-junk (<0.1). Verified by Test 4.

A PR that fails ANY of the 4 parts is REQUEST_CHANGES regardless of reproduction %.

---

## §6. THE HEAVY OFFLINE SMOKE-TEST PLAN (the core of acceptance — operator's explicit requirement)

All OpenAlex/Crossref/HTTP calls **mocked** from frozen JSON under `tests/fixtures/authority/`. Zero live spend. Cycle: **build → HEAVY smoke (S1–S6) → BOTH a Claude architect review AND the Codex diff gate** — both real, line-by-line per §-1.1, no rubber-stamp.

**Fixture source + the load-bearing caveat (must be honored):** the 172 `outputs/**/live_corpus_dump.json` files give 1,529 unique classified URLs `{T1:128,T2:85,T3:108,T4:507,T5:51,T6:113,T7:430,UNKNOWN:107}`. BUT the dumps store classifier OUTPUT, not full INPUT signals — `openalex_pub_type`, `openalex_source_type`, `is_peer_reviewed`, `body_article_type`, `fetched_content_length` are ABSENT. A harness that re-derives signals from url+title alone CANNOT reproduce R8b/R9/R10/R11 tiers and would launder a high % via string-presence (forbidden §-1.1). **RESOLUTION (binding):** for the ~200-URL S2 fixture, re-fetch OpenAlex metadata ONCE (free API, then frozen as `openalex_mocks/*.json`), reconstruct full `ClassificationSignals`, and commit BOTH the frozen inputs AND the HEAD output tier → deterministic offline replay. Reject any S2 harness that re-derives from url+title.

### S1 — Kill-switch OFF byte-identical (over ALL 1,529)
`test_kill_switch_off_byte_identical`. With `PG_USE_AUTHORITY_MODEL` unset, run the full 1,529-URL corpus through `classify_source_tier`; assert each `ClassificationResult` (tier, confidence, matched_rules, reasons) is **byte-identical** to `clinical_tier_baseline_off.json` (frozen by `freeze_clinical_tier_baseline.py`). Proves NOTHING breaks when OFF. Hard-fail on any single diff.

### S2 — Reproduction ≥95% of the clinical T1–T7 view (200-URL stratified, full signals)
`test_authority_reproduces_clinical_tier_view`. With ON, render the clinical view over the 200-URL fixture (full reconstructed signals); assert `agreement = matches/200 ≥ 0.95`. Emit a **directional confusion matrix** (HEAD-tier × view-tier) as an artifact for the human review. **Hard-fail on ANY T1↔T6 inversion (authoritative↔junk flip is lethal — never tolerated even inside the 5% budget),** and on any T1/T2↔T7 collapse.

### S3 — Cross-field sanity (≥50 non-clinical URLs)
`test_authority_cross_field_sane`. ≥50 URLs across law / physics / policy / JP-gov (`*.go.jp`) / African-energy with frozen mocked OpenAlex+ROR. Assert each gets a non-UNKNOWN, defensible `source_class` (JP-ministry → PRIMARY-OFFICIAL via ROR+PSL; physics journal → PRIMARY-SCHOLARLY; law-firm blog → COMMENTARY) AND an `authority_confidence` matching field thickness. Assert NO non-clinical URL returns the legacy `no_rule_matched` UNKNOWN — this is the field-agnostic claim being proven.

### S4 — The 4-part calibrated contract (two tests)
- `test_zero_host_literal_in_authority_code` (contract parts 1+2): regex scan over `src/polaris_graph/authority/**.py` for `\.(gov|edu|org|com|net|int|ca|jp|fr|ke)\b`, `medium\.com`, `linkedin\.com`, `/pulse/`, and a curated known-host substring list → **0 matches in code**; assert every `config/authority/*` file exists, is git-tracked, non-empty.
- `test_thin_field_honest_low_confidence` (contract parts 3+4): over `adversarial_thin_field.jsonl` (grey-lit / non-English / niche-regional, deliberately THIN OpenAlex) assert for EVERY source `authority_confidence == "LOW"` AND `source_class ∉ {falsely PRIMARY-SCHOLARLY}` AND `0.1 ≤ authority_score ≤ 0.8` (honest mid-band) AND `reasons[]` cites "thin OpenAlex coverage."

### S5 — Junk detection + real ON-vs-OFF integration
- `test_junk_detection` (4 cases + 1 control): schema.org `PressRelease`; `isAccessibleForFree:false` login-wall; `/blog/` self-published path; self-interest (host-org token == claim-vendor). Each fires its junk-class, `source_class ∈ {PRESS_RELEASE,UGC,COMMENTARY}`, `authority_score ≤ JUNK_CEIL`, matching reason present. The control (legitimate primary source) must NOT trip any junk pattern (no false-junk).
- `test_adequacy_selector_on_vs_off_integration`: run the REAL `corpus_adequacy_gate` + `evidence_selector` over a frozen corpus with the switch OFF then ON; assert the gate verdict (EXPAND/ABORT/PROCEED) and the selector's per-tier quota outcome are IDENTICAL between OFF and ON for the clinical fixture (because both consume only the T1–T7 string and S2 reproduces it ≥95%). This is the end-to-end proof that the wedge does not regress.

### S6 — Determinism + full-suite green + fail-loud
- `test_authority_model_deterministic`: ON, two consecutive runs over the same fixtures → identical `AuthorityResult` (no RNG, no live calls, no dict-order leakage).
- Full existing suite green with switch OFF: run `pytest tests/polaris_graph/` (the 20+ `test_m*`/`test_bug771`/`test_r5`/`test_regression_pg_lb_sa_02`/`test_openalex_authority_tier_t7` suites that pin current frozenset behaviour) — ALL must stay green (S1 enforces the OFF path is byte-identical, this confirms at suite level).
- Fail-loud: `data_loader.py` raises (not silent-default) if any `config/authority/*` file is missing/empty/unparseable (LAW II — no silent fallback).

Resource discipline (§8.4): single pytest run at a time; pre/post `Get-Process -Name codex,python,node`; kill strays. No heavy ML/CUDA in the offline smoke (Sentinel scorer OFF).

---

## §7. KILL-SWITCH + LAW-VI CONFIG

- `PG_USE_AUTHORITY_MODEL` default **OFF** (`os.getenv("PG_USE_AUTHORITY_MODEL","0")`), the dispatcher in §3.2 is the SINGLE switch point. No other env read of the flag.
- ALL source knowledge in versioned DATA under `config/authority/*` (LAW VI / contract part 1). `config/authority/VERSION` bumped on any data change. `data_loader.py` is the single cached loader; thresholds/weights/maps/patterns are NEVER inlined in `.py` (S4-grep enforces).
- No hard-coded numbers in the authority `.py` files: every threshold/weight/norm/ceiling comes from the YAML (LAW VI / §9.4 magic-number ban).

---

## §8. EXIT CRITERION (offline)

PR is mergeable iff ALL hold:
1. **S1 OFF byte-identity** over all 1,529 URLs — zero diffs.
2. **S2 reproduction ≥95%** of the clinical T1–T7 view, zero T1↔T6 inversions, zero T1/T2↔T7 collapses.
3. **The 4-part calibrated authority contract** (S4) all green.
4. **S3 cross-field** sanity green (≥50 non-clinical, all non-UNKNOWN, defensible).
5. **S5 junk + S5 adequacy/selector ON-vs-OFF integration** green (gate verdict + selector quota identical OFF vs ON).
6. **S6** determinism + full existing `tests/polaris_graph/` suite green (switch OFF) + fail-loud loader.
7. The build→heavy-smoke→**BOTH Claude architect review AND Codex diff gate** cycle complete, both real (no rubber-stamp).

---

## §9. RISKS + what Codex MUST web-verify (do not guess)

**R1 (P0) — thin-OpenAlex-field credibility.** Many non-biomedical / non-English / grey-lit sources have sparse OpenAlex coverage → signals A/B starve. DEFENSE: Signal D corroboration (KBT, domain-general) + honest LOW `authority_confidence` (contract parts 3+4). The contract makes starvation HONEST, not silently-wrong.

**R2 (P1) — eTLD+1 correctness.** `_normalize_domain` (`tier_classifier.py:718`) returns host, NOT registrable domain. Signal D must use the PSL table for true eTLD+1 or corroboration counting double-counts subdomains. Flagged for Codex.

**R3 (P1) — OpenAlex wiring gap.** §3.4 — `OpenAlexWork` + cache + `select=` must be extended. Codex confirms the fix shape doesn't break the existing cache (schema migration / version bump on the sqlite table).

**R4 (namespace, P2) — pre-existing `authority_score`.** `crag_retriever.py` / `source_registry.py` / `graph_v2.py` (pipeline-B `source_confidence`) already use an `authority_score` name. Different namespace; flag only — ensure no import collision with the new `authority` package.

**Codex must WEB-VERIFY (note "Codex must web-verify", don't trust my memory):**
1. OpenAlex has **no `is_peer_reviewed` boolean** — confirm peer-review is inferred (`is_core` + `type` + Crossref peer-review metadata), and confirm the exact `is_core`/`is_in_doaj`/`apc_prices` field names + that they live on the `/sources` (venue) object.
2. `summary_stats` (`h_index`, `2yr_mean_citedness`) lives on OpenAlex `/sources`, not `/works` — confirm whether a second API call / `select=` is needed and the exact field path.
3. OpenAlex `authorships[].institutions[].ror` + `.country_code` is the right path for Signal B, and the exact ROR institution `type` enum values.
4. The canonical Public Suffix List source (publicsuffix.org / `publicsuffix` PyPI) + its gov ccTLD coverage (`*.go.jp`, `*.go.ke`, `*.gc.ca`, `*.gob.mx`, `*.gouv.fr`), AND confirm (plan §2) that PSL is explicitly NOT a trust signal and MISSES `canada.ca`/`bundesbank.de`/`rbi.org.in`, so ROR is load-bearing.
5. The OpenAlex `select=` parameter syntax for requesting nested fields (`summary_stats`, `authorships.institutions.ror`) in one `/works` call vs requiring per-source `/sources` lookups.

**Files I have ALSO checked and they're clean (no other consumer of the classifier interface):**
`tier_classifier.py` (entry L1069, wrapper L1863, `ClassificationSignals` L83-108, `ClassificationResult` L111-123, `TierLevel` L70-80, `_normalize_domain` L718, R0-retracted L1094-1103); `live_retriever.py` (import + call L1789-1811, evidence_rows tier L1839); `openalex_client.py` (`authority_tier_t7` L70-115, `OpenAlexWork` 8-field dataclass L50-59, cache schema L122-135 + `_cache_get` L148-164 — the wiring gap); `deepener_sweep_adapter.py` (L6 docstring, no direct call); `corpus_adequacy_gate.py` + `evidence_selector.py` (consume the tier STRING via tier_counts/url_to_tier, NOT the result object); `clinical_retrieval/clinical_source_registry.py` + `clinical_retriever.py` (a SEPARATE classifier with its own `SourceTier`, does NOT import `tier_classifier` — do NOT touch). No `__init__` re-exports of the classifier (all imports direct → the dispatcher is the only switch point). The 20+ `test_m*`/`test_bug771`/`test_r5`/`test_regression_pg_lb_sa_02`/`test_openalex_authority_tier_t7` suites pin current frozenset behaviour → all MUST stay green with switch OFF (S1 + S6 enforce).

---

## §10. OUTPUT SCHEMA (Codex returns this — §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Advisor tool NOT used (forbidden per task directive + `feedback_no_opus_advisor_use_codex_cli_2026_05_23`). All review routed to Codex CLI.

---

## ADDENDUM — Codex brief-gate iter-1 corrections (REQUEST_CHANGES → adopted, 2026-05-31). BINDING over the body above.

Codex web-verified against OpenAlex docs + PSL; four corrections, all in-scope for Phase 0a:

### C1 (P1) — the AuthoritySignals input bridge (load-bearing fields must REACH the classifier)
Extending `OpenAlexWork` alone does NOT deliver fields to `_classify_via_authority_model`. `ClassificationSignals`
(`tier_classifier.py:83`) carries only legacy OpenAlex hints, and `live_retriever.py:1789` populates only those.
FIX: add an ADDITIVE `AuthoritySignals` payload (new optional dataclass, default None — backward-compatible) carrying
`cited_by_count, source_id, venue_summary_stats, is_core, is_in_doaj, apc_prices, ror_id, institution_type,
country_code, publication_year`. Wire it end-to-end: `openalex_client._parse_work` populates it → `OpenAlexWork`
(+ `authority_tier_t7`) carries it → `live_retriever.py:1789-1811` passes it into `ClassificationSignals` (additive
field) → `score_source_authority(signals)` reads it. When the payload is absent/partial → `authority_confidence=LOW`
(fail-honest, never fabricate authority). The frozen S2 fixtures MUST capture this payload (see C2 fixture note).

### C2 (P1) — correct OpenAlex retrieval contract (root /works select + /sources lookup + real cache migration)
OpenAlex `select=` is ROOT-LEVEL ONLY (rejects nested props). Therefore:
- `/works` `select=`: `id,doi,title,type,publication_year,cited_by_count,is_retracted,primary_location,authorships`
  (root fields only; `primary_location.source.id` is reachable as part of the `primary_location` object).
- `summary_stats` (h_index / 2yr_mean_citedness), `apc_prices`, `is_core`, `is_in_doaj` are **SOURCE** fields →
  a SEPARATE `/sources/{source_id}` fetch keyed by `primary_location.source.id`, with its own cache table. Absent →
  `authority_confidence=LOW`.
- SQLite cache: `CREATE TABLE IF NOT EXISTS` does NOT add columns to an existing cache → ship a real VERSIONED
  MIGRATION (bump cache schema version + `ALTER TABLE`/rebuild path), do not silently no-op on an old cache.

### C3 (P2) — complete the consumer map
`src/polaris_graph/honest_pipeline.py:60,167` is also a direct `classify_source_tier` caller; it reads only
`.tier.value/.confidence/.matched_rules/.reasons` (legacy) → still wedge-safe, but it is added to the consumer map
so "all consumers checked" is honest.

### C4 (P2) — institution-type vocabulary
OpenAlex institution `type` includes `archive`; native ROR `types` also includes `funder`. The versioned
institution-type→class data map MUST handle `archive` and `funder` explicitly (deterministic class or intentional
LOW-confidence), not leave them to fall through.

### Unchanged + reconfirmed by Codex
PSL is a domain-boundary list, NOT a trust signal (ICANN explicit) — already framed as a PRE-FILTER only; ROR
institution-type is the load-bearing official-source signal. The 4-part calibrated authority contract, the 6-group
heavy smoke plan, the kill-switch-OFF byte-identity, and the no-string-presence-laundering fixture caveat all stand.
convergence_call was `continue` — these are real; addressed here, re-gating.

### C5 (P1, iter-2) — target the REAL production OpenAlex path, not tools/openalex_client
Codex iter-2 finding (correct): the production sweep enriches via `live_retriever._openalex_enrich`
(`live_retriever.py:573`, own httpx call to `OPENALEX_ENDPOINT` :57, returns the flat `openalex_*` dict) wrapped by
`_bounded_openalex_enrich` (:670), called at `:1751` and read into the classifier at `:1789`. It does NOT call
`tools/openalex_client`. So C1/C2 as written would land the new fetch/cache in the wrong module and the primary
classifier caller would still receive only the legacy `openalex_*` dict.
FIX (supersedes the C1/C2 routing): implement the new contract IN THE LIVE PATH. Either (a) refactor
`_openalex_enrich` to delegate to a single versioned cached OpenAlex client shared with `tools/openalex_client`, OR
(b) extend `_openalex_enrich` directly. Whichever: it MUST (1) add the root-level `/works` `select=`
(`id,doi,title,type,publication_year,cited_by_count,is_retracted,primary_location,authorships`); (2) add the separate
`/sources/{id}` fetch keyed by `primary_location.source.id` for `summary_stats,apc_prices,is_core,is_in_doaj`;
(3) add the local cache + VERSIONED migration (not CREATE-IF-NOT-EXISTS); (4) populate the additive `AuthoritySignals`
payload into the returned enrich dict so `:1751 -> :1789` carries it into `ClassificationSignals`; (5) LOW-confidence
on any missing field. The `tools/openalex_client` path is a SEPARATE (PAL/react) consumer — keep it consistent but
the PRODUCTION wedge path is `live_retriever._openalex_enrich`. Frozen S2 fixtures capture this live-path payload.
