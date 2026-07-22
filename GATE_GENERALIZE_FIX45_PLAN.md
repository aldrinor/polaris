# GATE — Generalize Fix 4 (report shape) + Fix 5 (source-kind/quality eligibility)

> **This supersedes the Fable-only v1.** v1 was one external design (Fable) adjudicated by OPUS against a *baseline* (`78fe2ca`) whose line numbers no longer match reality. This v2 is a **genuine 3-way review** (Fable 5, Kimi K3, Codex Sol all returned) cross-checked against the **actually-committed** journal-flavored build at **`d44ee36`** on branch `gate-inversion` (worktree `/home/polaris/wt/outline_agent`). All edit anchors below are verified against `d44ee36`.

**Author:** OPUS (3-way consolidation)
**Date:** 2026-07-17
**Landed build under review:** `d44ee36` — "gate(inversion): apply the consolidated 5-fix plan …"
**Reviewers who returned:** FABLE 5, KIMI K3, CODEX SOL (all three)

---

## 0. Governing constraints (frozen)

- **C1 FAITHFULNESS FROZEN.** `provenance_generator.py`, strict_verify, drop rule, NLI, D8: **0-diff**. No new verification pass, no new faithfulness test.
- **C2 SCOPE AT RETRIEVAL, never hard-filter a frozen corpus** (997→131 tanked RACE 0.4447→0.3264, IF fell too). Hard strength buys *go-find + reorder + audit*, not a mask — unless the corpus is *provably adequate*.
- **C3 MINIMAL / anti-over-engineering.** Smallest faithfulness-safe change. This run's job is *prove-not-a-regression* (≈ champion IF 0.4587), not beat-champion. One env flag per fix, default OFF/prior; champion path double-guarded.
- **C4 Coverage > Insight > Readability > IF.**

### Reality of the landed build (this is what we generalize ON TOP OF)

`d44ee36` shipped Fix 4/5 in **journal-literal** form:

| Surface | Landed at `d44ee36` | File:anchor |
|---|---|---|
| Fix 4 shape | `PG_REPORT_LITREVIEW_SHAPE` **default ON**; hardcoded `## Introduction and Scope`; fixed order sections→depth→**KF→**biblio (KF always *after* thematic) | `run_honest_sweep_r3.py` `build_intro_and_scope_md` :6398, `reshape_report_body_litreview` :6424, call-site :17463 |
| Fix 4 table | drb_72-specific summary-table injection | `render_summary_table_into_artifact` :6454, call-site :17802 |
| Fix 5b | journal/DOI "second-chance" PASS at step "4.5" | `quality_eligibility.py` `_has_doi_or_journal_credential`, inserted in `score_source_quality` |
| Fix 5d | `_is_journal_lead` selection ordering keyed on `"journal" in allowed_source_kinds` | `run_honest_sweep_r3.py` :14609–14636 |
| Journal-only **hard mask** | an entire node module `journal_only_filter.py` — fail-closed corpus filter (`filter_to_citeable`, `assert_no_leak`, `prune_contract_plans`, `JournalOnlyAbort`), flag `PG_SOURCE_RESTRICTION_JOURNAL_ONLY` + protocol `source_restriction: journal_only`; wired at ~10 call-sites (`run_honest_sweep_r3.py` :10819, :12092, :14263, :14843, :15322, …) | `src/polaris_graph/nodes/journal_only_filter.py` |

**Already-general in the baseline (do NOT rebuild — all three models were right that the mechanism exists):**
- `retrieval_projection.py:695` already sets `predicate_force["allowed_source_kinds"]="hard" if is_hard else "soft"` from the ContractTerm force (clause ledger: restrict/oblige/exclude⇒HARD; prefer/quality/date⇒PREFER).
- `to_scope_protocol` (:336) already emits every allowed kind as `op="prefer"`, `strictness="hard"` iff the predicate is hard. **No journal literal there.**
- KF bullet integrity `_bullet_marker_integrity_ok` (:877) + `_reemit_key_findings_bullet` (:891) are kind-agnostic; `abacademies.org` is already in `_PREDATORY_HOST_PATTERNS`.

> **The single biggest reality-gap vs v1:** v1 assumed Fix 5d was *only* selection ordering and no hard journal flag shipped. In fact `d44ee36` ships a **whole hard fail-closed journal-only corpus filter** (`journal_only_filter.py`) — the exact C2-violating "mask a frozen corpus" pattern all three models warned against. It is **dormant** (`JOURNAL_ONLY_BENCHMARK_SLUGS = frozenset()`, flag default `0`), but it exists and is wired. The generalization must decide its fate (see §5, §7).

---

## 1. Convergence map (honest 3-way)

### Fix 4 — report shape

**All THREE agreed (strongest signal):**
1. **Closed archetype table, NOT a generative/LLM skeleton.** Fable: "Option 1 … deterministic, unit-testable, OFF-path trivially byte-identical" and Option 2 "walks straight at C1." Kimi: "closed archetype set — pick this, reject generative … a generative (LLM) skeleton … is exactly the 'new subsystem' the operator kills." Codex: "Use a small registry, not an LLM-generated skeleton. A generative skeleton adds nondeterminism, creates opportunities to invent sections or rewrite claims."
2. **"review / Introduction-and-Scope" is just ONE row of the table**, keyed off normalized `deliverable.kind`, default `review`, resolved via the *existing* `_resolve_facet_id`-style synonym pattern (no new vocab). All three list ≈ review / memo / brief / comparison / explainer.
3. **Arrange existing render blocks only — never edit block payload.** Fable: "pure permutation/concat of opaque block strings." Kimi: "a permutation of concatenation operands." Codex: "handles strings as opaque payloads. Verified sentences remain byte-identical."
4. **The framing paragraph is claim-free, citation-free, from the objective spans** — same faithfulness class as the abort-path H1s. All three say identical.
5. **The D8 banner is the *actual* fix for "opens on a blockquote"; adding an H1 at the assembly seam does not fix it** because the banner is prepended later (`:20778`). All three independently flag this; all three say do **not** edit the frozen builder (`provenance_generator.py:3212`) — relocate the *insertion*, keep bytes identical. (v1 chose to leave the banner alone and accept the blockquote-above-H1; see §2.4 adjudication.)

**Two agreed:**
- **Key-Findings position varies by archetype (BLUF for memo/brief, after-framing for review).** Fable and Kimi make this the load-bearing degree of freedom; Fable: "a memo/brief audience wants findings first (BLUF)". Codex encodes it in its per-archetype slot tables (memo = "summary/key findings" early) but does not name a `kf_position` field.
- **Methods is NOT unconditionally machinery.** Kimi: "Blanket 'demote methods below the appendix' is wrong for systematic-review contracts, where Methods is scored content (PRISMA) … `contract.sections` already tells you which sections are required." Codex: "User-requested methods and substantive limitations are not automatically machinery." **Fable dissents** (see below).

**Single-model dissent:**
- **Fable: machinery placement is archetype-INVARIANT** — methods/disclosures/reliability all go below the appendix boundary for *every* archetype ("this is the key simplification"). This directly contradicts Kimi+Codex on Methods. **Adjudication in §7.**
- **Codex: split `allowed` (exclusive IN) vs `required` (REQUIRE, non-exclusive) vs `preferred` (PREFER) as three distinct policy lists**, driven by `ContractTerm.operator` *together with* `force`, not force alone. Fable and Kimi collapse to `allowed_source_kinds + predicate_force`. (This is a Fix-5 point but Codex is alone on it — §7.)
- **Kimi: archetype also relabels the KF/framing headings** (review `## Key Findings` vs memo `## Bottom Line`). Fable explicitly says keep `## Key Findings` verbatim everywhere in v1; Codex is silent. **Adjudication: keep verbatim (Fable) for v1** — relabeling is chrome churn with no measured payoff.

### Fix 5 — source-kind + quality eligibility

**All THREE agreed (strongest signal):**
1. **The journal-literal parts actively HARM non-journal contracts** (not merely fail to help). Fable: "It actively fights non-journal contracts." Kimi: "will actively harm the five non-journal prompts." Codex: "would mis-handle news, government, press-release, and blog-scoped prompts."
2. **UNKNOWN resolves by a general signal→tier model; "journal ⇒ PASS" is ONE T1 instance, not the mechanism.** Fable: signal→(tier,kind) table, "journal ⇒ PASS falls out as the T1-scholarly row." Kimi: deterministic signal registry, "the plan's 5b, demoted to one row." Codex: "journal PASS falls out from 'validated peer-reviewed scholarly source' … not from special-casing the prompt."
3. **T1 = authoritative-universal → PASS unconditionally; T2/T3 PASS only iff kind ∈ allowed_source_kinds and not excluded.** Fable states this rule verbatim. Kimi: T1 signals PASS + a "contract-relative FAIL guard" when kind ∈ allowed. Codex: "Allow only validated T1/T2 to convert … UNKNOWN into PASS," peer-reviewed-journal AND gov both T1.
4. **Adequacy must count in-scope-kind rows, not DOI/journal rows**, and hard enforcement arms **only** behind adequacy, else prefer + disclose. All three, verbatim. Codex adds an **acquisition-receipt** precondition (below).
5. **Exclusion always wins; evidence-positive only (never re-admit a strict_verify FAIL, never down-move a verdict); all Fix-5 code is upstream of the frozen verifier.** All three, verbatim.

**Two agreed:**
- **Rename/kill `PG_SOURCE_RESTRICTION_JOURNAL_ONLY`.** Fable: rename → `PG_SOURCE_RESTRICTION_HARD`, no alias. Kimi: "rename … kind-agnostic (or drop the env entirely and drive from `predicate_force`)." Codex: implicit (no journal branch anywhere). **Two name it; Codex would drive it from policy without a dedicated env.**
- **DOI alone is NOT sufficient T1 evidence** — Codex and Kimi both call this out (preprints/datasets/predatory carry DOIs). Codex: "DOI alone is not T1 evidence." Kimi: "DOI-only preprint does not [pass]." **Fable's table treats DOI-or-journal as the T1-scholarly predicate** (reusing the landed `_has_doi_or_journal_credential`, which *does* already reject preprint DOIs and predatory hosts upstream). **Adjudication in §7.**

**Single-model dissent:**
- **Codex: `abacademies.org` is NOT "evidence-positive only" — it creates a new FAIL**, so treat it as a separately-approved denylist correction, "otherwise the plan's claim that FAIL behavior is untouched is false." Fable/Kimi keep it inline as shipped. **Codex is correct on the letter** (it is already committed at `d44ee36`, so this is moot for the unwind, but note it honestly).
- **Codex: require an acquisition receipt** (`{contract_hash, source_policy_applied, retrieved_with_kind_lanes}`) matching the policy hash before a hard allowlist may arm — "A frozen unscoped corpus therefore always degrades to preference plus disclosure." Fable/Kimi gate hard-arming on the adequacy count alone. **Codex's receipt is the stronger C2 guarantee; adopt a lightweight form — §7.**
- **Codex: three-way operator split** (allowed/required/preferred). Fable/Kimi: two-way (allowed + exclude, force = strength). **Adjudication: defer required-vs-allowed to a labelled TODO — §7.**
- **Kimi: a "contract-relative FAIL guard"** that *relaxes* the `is_peer_reviewed=False`/low-tier FAIL to neutral UNKNOWN when the row's kind ∈ allowed. **Fable and Codex both refuse to touch FAIL branches.** Codex: "Explicit quality FAIL precedence remains before positive UNKNOWN resolution." **Adjudication: REJECT Kimi's FAIL-relaxation (§7)** — it violates "evidence-positive only," the one invariant all three otherwise share; the contradictory contract is a conflict-ledger case, not a silent relaxation.

---

## 2. FIX 4 — the generalized design (adjudicated)

### 2.1 Closed archetype table (table, not generative — 3/3 converge)

```python
# NEW: src/polaris_graph/generator/report_skeleton.py  (pure; no I/O, no LLM, no provenance import)
@dataclass(frozen=True)
class Archetype:
    key: str            # review | memo | brief | comparison | explainer
    framing_title: str  # "Introduction and Scope" | "" | "Executive Summary" | "Scope and Criteria" | "Overview"
    kf_position: str    # "lead" (BLUF) | "after_framing" | "tail"

ARCHETYPES = {
  "review":     Archetype("review",     "Introduction and Scope", "after_framing"),
  "memo":       Archetype("memo",       "",                       "lead"),
  "brief":      Archetype("brief",      "Executive Summary",      "lead"),
  "comparison": Archetype("comparison", "Scope and Criteria",     "after_framing"),
  "explainer":  Archetype("explainer",  "Overview",               "tail"),
}
KIND_SYNONYMS = {  # normalized deliverable.kind value -> archetype key
  "literature review":"review","systematic review":"review","survey":"review","review":"review",
  "memo":"memo","decision memo":"memo","briefing memo":"memo",
  "brief":"brief","policy brief":"brief","executive brief":"brief",
  "comparison":"comparison","comparative analysis":"comparison","market scan":"comparison",
  "explainer":"explainer","primer":"explainer","overview":"explainer",
}
DEFAULT_ARCHETYPE = "review"   # least-wrong universal shape; disclosed via Assumption when assumed
```

Machinery placement is **archetype-invariant** (Fable), *with one Kimi/Codex carve-out*: the machinery set = `{methods, cwf_disclosed, drop_disclosure, reliability}` goes below the existing `_AUDIT_MACHINERY_APPENDIX_BOUNDARY` for **every** archetype — **except** `methods` stays in the scored body when a `SectionRequirement` in `contract.sections` matches it (Kimi/Codex's systematic-review case). This is the *only* adjudicated addition to Fable's invariant-machinery rule; it is a 2-line guard (`methods_is_machinery = not _contract_requires_section(contract, "methods")`), not a new subsystem. See §7.

Only two things vary per archetype: **KF position** and **framing title**. Ordered skeleton:

```
# {question}                        (H1 — existing "# Research report: {q}")
[KF]          if kf_position == "lead"          (memo / brief — BLUF)
[framing]     if framing_title != ""            (## {framing_title} from objective)
[KF]          if kf_position == "after_framing" (review / comparison)
sections_concat                                 (thematic ### — NEVER reordered internally)
_depth_layer                                    (synthesis)
[KF]          if kf_position == "tail"          (explainer — keep heading "## Key Findings")
biblio_section
## Appendix: audit, disclosure, and weighting (not scored as report claims)   (existing boundary, verbatim)
methods* + cwf_disclosed + drop_disclosure      (* methods here iff not a required section)
[reliability appended UNDER the same boundary]
```

Three pure functions: `resolve_archetype(contract) -> (Archetype, assumed:bool)`, `build_framing_md(contract, archetype) -> str`, `order_report_blocks(archetype, blocks, *, methods_is_machinery) -> (scored_body, machinery_appendix)`.

### 2.2 The drb_72 summary table (`render_summary_table_into_artifact`)

This is genuinely prompt-driven ("some prompts explicitly ask the report to END with a titled summary TABLE and name the exact column headers"). It already reads `contract_headers` from the contract — so it is **already contract-driven**, not journal-hardcoded. **Keep it, but gate its invocation on a contract term** (`deliverable.format == "table"` / presence of `contract_headers`), not a slug. Verify at implementation that the call-site (:17802) is not slug-gated; if it is, replace the slug check with the contract-term check. This is the one Fix-4 surface none of the three models saw (it is not in the pack); flag it and generalize its *trigger*, not its body.

### 2.3 Exact edits (Fix 4) ON TOP OF `d44ee36`

1. **NEW `src/polaris_graph/generator/report_skeleton.py`** — the tables + three pure functions. No `provenance_generator` import.
2. **`run_honest_sweep_r3.py` `build_intro_and_scope_md` (:6398) → `build_framing_md(contract, archetype)`.** Replace the hardcoded `## Introduction and Scope` string with `f"## {archetype.framing_title}\n\n"` (emit nothing when `framing_title == ""`, i.e. memo). Keep the claim-free/citation-free prose class byte-for-byte otherwise.
3. **`run_honest_sweep_r3.py` `reshape_report_body_litreview` (:6424) → `order_report_blocks`.** Replace the fixed `sections + depth + KF + biblio` order with the archetype-driven order (KF position from `kf_position`; methods-in-body iff required section). Keep the "position only, nothing deleted, count-invariant" contract.
4. **Call-site (:17463) — flag rename + default flip.** `litreview_shape_enabled()` / `PG_REPORT_LITREVIEW_SHAPE` → `report_shape_enabled()` / **`PG_REPORT_SHAPE`**. **Default: keep ON** (the landed build ships it ON and OFF is byte-identical to the pre-fix machinery-first bug, which we do not want as the default). Resolve archetype from `contract.deliverable`; when no contract / archetype unresolved → `review` + `Assumption` ledger entry (default archetype == current behavior, so ON-path for a review contract is byte-identical to `d44ee36`).
5. **`render_summary_table_into_artifact` (:17802) trigger** — gate on the contract term, not a slug (§2.2).
6. **KF integrity (`_bullet_marker_integrity_ok` / `_reemit_key_findings_bullet`) — KEEP AS-IS.** Kind-agnostic; a malformed bullet is a bug in every archetype. No unwind.
7. **Preamble shrink — KEEP AS-IS** (already kind-agnostic).
8. **D8 banner (:20778) — see §2.4 adjudication.** No edit to `provenance_generator.py` either way.

### 2.4 D8 banner — adjudication (3-way split resolved)

All three say adding an H1 does not fix "opens on a blockquote" because the banner prepends at `:20778`. Kimi and Codex say **relocate the insertion** so the banner sits after the H1 (Codex: "place the returned banner verbatim in the audit appendix"; Kimi: "insert `_d8_banner` *after* the title block"). Fable says leave it — the honest fix is Fix 3 (D8 actually adjudicating). **Adjudication: relocate the banner insertion into the appendix in shape-ON mode (Kimi/Codex), keep the frozen builder 0-diff, keep legacy prepend in shape-OFF mode.** Rationale: the banner is *disclosure chrome* (§-1.3 QUALITY), its bytes are unchanged, and moving disclosure below scored content is the exact already-shipped `compose_report_with_reliability` precedent. This is faithfulness-neutral and directly closes verified-item-1 without waiting on Fix 3.

### 2.5 Faithfulness + OFF-path (Fix 4)

- `order_report_blocks` permutes whole opaque block strings; interiors (every strict_verify sentence, every KF bullet) are byte-identical. Provable by a **body-line-multiset test**: pre/post differ only by order + the new framing/boundary/preamble lines.
- Only new text = the framing paragraph (claim-free, citation-free, numeral-free, from the user's objective spans) — same class as the abort-path H1s.
- Nothing deleted; machinery moves below the existing boundary (shipped precedent). Disclosure stays in file AND manifest.
- `provenance_generator.py` 0-diff. Banner bytes unchanged (relocated only).
- **OFF-path (`PG_REPORT_SHAPE=0`): the exact legacy concat runs verbatim** (`_key_findings + sections_concat + _depth_layer + methods + biblio + cwf + drop`) and the banner prepends legacy — byte-identical to pre-fix. Golden-file byte-compare test.

---

## 3. FIX 5 — the generalized design (adjudicated)

### 3.1 The projection is already general — do NOT add a branch (3/3)

`retrieval_projection.py:695` sets `predicate_force["allowed_source_kinds"]` from term force; `:336` emits `op="prefer"`. **Do not rewrite the compiler or the projection.** Fix 5's work is entirely in the layers around it.

### 3.2 Signal→(tier,kind) model (journal ⇒ PASS is one T1 instance)

```python
# quality_eligibility.py — replace the journal-only "4.5 second-chance" with:
def _positive_signal_tier(row, url) -> tuple[str, str] | None:   # -> (tier, kind) or None
    ok, _basis = _has_doi_or_journal_credential(row, url)  # REUSE landed predicate = T1-scholarly
    if ok:
        return ("T1", "peer_reviewed_journal")             # journal ⇒ PASS is JUST THIS ROW
    if _official_gov_host(url):        return ("T1", "government")
    if _reputable_newsroom(row, url):  return ("T2", "news")
    if _issuer_primary(row, url):      return ("T3", "press_release" if _is_pr(row) else "corporate")
    return None

# Resolution rule — inserted where the "4.5" second-chance is today (after every FAIL return,
# before the UNKNOWN shell/no-metadata returns):
#   sig = _positive_signal_tier(row, url)
#   if sig:
#       tier_id, kind = sig
#       if tier_id == "T1":                                      -> PASS  (quality is quality, any contract)
#       elif kind in allowed_kinds and kind not in excluded_kinds:-> PASS  (contract explicitly wants this kind)
#   # else fall through to the existing UNKNOWN + demote weight (unchanged)
```

- **T1 = authoritative-universal → PASS unconditionally** (peer-reviewed-journal AND gov both T1). **T2/T3 PASS iff kind ∈ allowed_kinds and not excluded.** Journal⇒PASS is the T1-scholarly row.
- **Over-engineering guard (all three):** keep the table to ≤4 predicates over already-fetched fields; **no credibility ontology.** If `_official_gov_host` / `_reputable_newsroom` / `_issuer_primary` are not cheaply available from the existing facet/tier classifier, ship **T1-scholarly + the `kind ∈ allowed` gate seeded by the existing journal helper** for v1 and leave T2/T3 host predicates as a labelled TODO. The *shape* (signal→tier→∈allowed) is the deliverable; adding a kind later must be data, not a branch.
- **DOI-alone caveat (Codex/Kimi):** we reuse `_has_doi_or_journal_credential`, which already rejects preprint DOIs (its genre classifier requires article/review + journal source-type; the landed `is_citeable_journal` rejects `_PREPRINT_DOI_MARKERS`). So the DOI path is *not* "DOI alone ⇒ T1"; it is "registered scholarly DOI that also passes the genre predicate." Keep it, but add the property test that a preprint/dataset DOI does **not** PASS (M8).

### 3.3 Exact edits (Fix 5) ON TOP OF `d44ee36`

1. **`quality_eligibility.py:score_source_quality`** — add keyword-only params `allowed_kinds: frozenset[str] = frozenset()`, `excluded_kinds: frozenset[str] = frozenset()` (defaults empty ⇒ every existing caller byte-identical). **Replace the "4.5" journal-only second-chance** (the `_has_doi_or_journal_credential` PASS block) with the `_positive_signal_tier` resolution rule, in the *same position* (after all FAIL returns, before the UNKNOWN returns). `_has_doi_or_journal_credential` is **reused** as the T1-scholarly predicate — single source of truth, no duplicate journal logic.
2. **`quality_eligibility.py:build_quality_eligibility`** — thread `allowed_kinds=frozenset(policy.allowed_source_kinds)`, `excluded_kinds=frozenset(policy.excluded_source_kinds)` into the `score_source_quality` call. Receipts carry new basis strings automatically.
3. **`run_honest_sweep_r3.py` Fix 5d selection ordering (:14609–14636)** — replace `_is_journal_lead` / `"journal" in allowed_source_kinds` with a **kind-match** key:
   ```python
   _allowed = frozenset(str(k).lower() for k in (getattr(_gate_policy,"allowed_source_kinds",None) or []))
   def _kind_match(_r) -> bool: return classified_kind(_r) in _allowed   # same facet classifier
   evidence_for_gen = sorted(evidence_for_gen, key=lambda _r: 0 if _kind_match(_r) else 1)  # stable
   ```
   Keep the `assert len == _n_before` count-invariant; reword the log "journal" → "in-scope-kind". Empty `_allowed` ⇒ every row `False` ⇒ stable no-op (byte-identical).
4. **`_PREDATORY_HOST_PATTERNS` `abacademies.org` — KEEP** (already committed; kind-agnostic; per Codex, note it is a FAIL-band addition, not part of the UNKNOWN resolver — the resolver stays evidence-positive-only).
5. **`PG_CREDIBILITY_LLM_TIERING`, topicality two-tier (`PG_TOPICALITY_HARD_FLOOR`) — KEEP** (already kind-agnostic).
6. **S4 audit** — parametrize the "journal share" numerator by `policy.allowed_source_kinds` (in-scope-kind share). *Anchor to be located at implementation; if inside a frozen file, compute at menu construction.*
7. **`corpus_kind_adequacy` (new, ~15 LOC) + hard-arm rename** — §3.5.
8. **`journal_only_filter.py` hard mask — §5 unwind decision.**

### 3.4 Invariants and how each is coded

- **INV-1 never re-admit a strict_verify FAIL.** All Fix-5 code is *eligibility* (which rows may enter the citable menu), always upstream of the frozen verifier. Eligibility neither reads nor writes verify verdicts; a PASS-promoted row's claims still go through the untouched verifier. Enforced by C1's 0-diff check.
- **INV-2 never override an EXCLUSION.** **Load-bearing layer = the upstream exclude facet mask** (`op="exclude"`, hard iff NOT_IN term FORCE_HARD), which removes excluded-kind rows from the menu *before* selection — so a T1 `.gov`-hosted **blog** under exclude-blogs never cites even though its tier rule is unconditional T1 PASS. (OPUS correction of Fable/Kimi, who leaned on the tier rule; the T1 clause is unconditional, so the *mask* is the guarantee.) Secondary: `_positive_signal_tier`'s T2/T3 clause checks `kind not in excluded_kinds`.
- **INV-3 evidence-POSITIVE only (verdict monotonicity).** The inserted block contains ONLY `return PASS`; every FAIL return is lexically above and untouched; UNKNOWN fall-throughs remain the else-path. Property: `∀ row,contract: new_verdict ∈ {old_verdict} ∪ ({PASS} if old_verdict==UNKNOWN else {})`. The kind-match ordering assigns no weights/verdicts. **Kimi's FAIL-relaxation guard is REJECTED here** (it would violate this).

### 3.5 Corpus-adequacy + disclosure fallback (any kind) + acquisition receipt

```python
# quality_eligibility.py (new, ~15 LOC — NOT a new module)
def corpus_kind_adequacy(rows, allowed_kinds, *, min_rows=25) -> tuple[bool, int]:
    n = sum(1 for r in rows
            if classified_kind(r) in allowed_kinds
            and score_source_quality(r, allowed_kinds=allowed_kinds)[0] != FAIL)
    return (n >= min_rows, n)
```

At the sweep call-site the kind-restriction hard mask arms **only** as
`term_is_hard AND env_flag(PG_SOURCE_RESTRICTION_HARD) AND adequate AND acquisition_receipt_matches`,
else force degrades to *prefer* + one disclosure line in the machinery appendix:

> "Scope note: the prompt restricts sources to {kinds}; only {n} in-scope sources were retrievable, below the {min_rows} adequacy floor — in-scope sources were prioritized rather than exclusively enforced."

- **Adequacy counts in-scope-kind rows, not DOI rows** (3/3). Adequacy gates only the eligibility hard mask; retrieval-side go-find (C2) always runs, keeping the count honest.
- **Acquisition receipt (Codex, adopted lightweight):** the hard mask also requires proof the corpus was fetched *under this contract's kind lanes* — a `{contract_hash, source_policy_applied}` check against the policy hash. A **frozen/replayed unscoped corpus never arms the hard mask**, it degrades to prefer+disclose. This is the strongest available C2 guarantee against the 997→131 replay; adopt the cheap form (contract-hash match on the retrieval receipt already stamped on `RetrievalPolicy.contract_hash`).
- **Flag rename:** `PG_SOURCE_RESTRICTION_JOURNAL_ONLY` → **`PG_SOURCE_RESTRICTION_HARD`** (kind-agnostic; reads kinds from the policy). Default **OFF**. No alias (C3).

### 3.6 Faithfulness + OFF-path (Fix 5)

- All changes shape the citable **menu** upstream of the frozen verifier; no FAIL row re-admitted (INV-3); UNKNOWN handling adds *evidence*, not leniency; `provenance_generator.py` / strict_verify **0-diff**.
- Selection ordering is promote-by-sort only — no weight, no verdict, count-invariant.
- **OFF-path byte-identical:** `allowed_kinds`/`excluded_kinds` default empty ⇒ `score_source_quality` byte-identical; `corpus_kind_adequacy` never called without a policy; kind-match sort is a stable no-op when `_allowed` empty; `PG_SOURCE_RESTRICTION_HARD` default OFF; `RetrievalPolicy.is_empty()` ⇒ caller applies no filter. Champion path (no contract) ⇒ all Fix-5 code no-ops.

---

## 4. Faithfulness + OFF-path safety argument (whole plan)

1. **`provenance_generator.py` 0-diff.** No edit, no import, from either fix. The D8 builder (:3212) is untouched (banner only *relocated*).
2. **Verified sentences byte-identical.** Fix 4 permutes whole opaque blocks; Fix 5 changes only *which rows are eligible to cite*, never the text of a verified sentence. Body-line-multiset test proves the report body differs only by order + new framing/boundary lines; per-section `verified_text` hashes unchanged pre/post.
3. **Upstream of the frozen verifier.** Every Fix-5 change is eligibility (menu shaping); every Fix-4 change is render assembly *downstream* of strict_verify (verified text already fixed) — neither reads/writes verdicts.
4. **PG_GATE-OFF byte-identical.** Champion path passes no contract ⇒ archetype defaults + all kind params empty ⇒ every new branch no-ops. Both new flags (`PG_REPORT_SHAPE` shape-ON but review-default == pre-fix for review contracts; `PG_SOURCE_RESTRICTION_HARD` OFF) plus `is_empty()`/`plan=None` double-guard. Golden byte-compare test (M9).
5. **New behavior behind default-OFF/None flags.** `allowed_kinds=frozenset()`, `excluded_kinds=frozenset()`, `hard_floor=None`, `PG_SOURCE_RESTRICTION_HARD` OFF, archetype `review` default. Every generalization is inert until a contract term flows in.

**Conclusion: the design is faithfulness-safe.** It is render-only (Fix 4) + menu-eligibility-only (Fix 5), both classes CLAUDE.md §-1.3 already treats as QUALITY-not-faithfulness, both proven byte-identical OFF-path, with `provenance_generator.py`/strict_verify/D8/drop 0-diff.

---

## 5. UNWIND LIST — exact edits ON TOP OF `d44ee36`

| # | Location (`d44ee36`) | Landed (journal-literal) | Generalize to |
|---|---|---|---|
| U1 | `run_honest_sweep_r3.py:6398` `build_intro_and_scope_md` | hardcoded `## Introduction and Scope` string | `build_framing_md(contract, archetype)` → `## {archetype.framing_title}` (empty for memo) |
| U2 | `run_honest_sweep_r3.py:6424` `reshape_report_body_litreview` | fixed order sections→depth→**KF**→biblio (KF always after thematic) | `order_report_blocks(archetype, blocks, methods_is_machinery)` — KF position by `kf_position`; methods in body iff required section |
| U3 | `run_honest_sweep_r3.py:6386` `_LITREVIEW_SHAPE_ENV` + `litreview_shape_enabled` (:6391) | `PG_REPORT_LITREVIEW_SHAPE` (default ON) | `PG_REPORT_SHAPE` (default ON; review-default ⇒ byte-identical to landed for review contracts) |
| U4 | `run_honest_sweep_r3.py:17463` call-site | passes hardcoded intro + fixed reshape | resolve archetype from `contract.deliverable`; default `review` + `Assumption`; drive U1/U2 |
| U5 | `run_honest_sweep_r3.py:17802` `render_summary_table_into_artifact` trigger | (verify) slug/drb_72-gated | gate on contract term (`deliverable.format=="table"` / `contract_headers` present) |
| U6 | `run_honest_sweep_r3.py:20778` D8 banner prepend | prepend (blockquote above H1) | relocate insertion below H1/into appendix in shape-ON mode; frozen builder 0-diff |
| U7 | `quality_eligibility.py` `score_source_quality` "4.5" second-chance | `_has_doi_or_journal_credential` PASS (journal-only) | `_positive_signal_tier` rule; reuse the helper as the T1-scholarly row; add `allowed_kinds`/`excluded_kinds` params |
| U8 | `quality_eligibility.py` `build_quality_eligibility` | calls `score_source_quality(row)` | thread `allowed_kinds`/`excluded_kinds` from policy |
| U9 | `run_honest_sweep_r3.py:14609–14636` Fix 5d `_is_journal_lead` | `"journal" in allowed_source_kinds` + journal/DOI-first sort | `_kind_match(row) ∈ allowed_source_kinds` stable sort; keep count-invariant; reword log |
| U10 | S4 "journal share" audit (anchor TBD) | scores journal share | parametrize numerator by `allowed_source_kinds` (in-scope-kind share) |
| U11 | **`src/polaris_graph/nodes/journal_only_filter.py`** + ~10 call-sites (`:10819,:12092,:14263,:14843,:15322,…`) + `run_gate_b.py` `apply_journal_only_for_slug` (:5383), `JOURNAL_ONLY_FLAG`, `JOURNAL_ONLY_BENCHMARK_SLUGS` | a **hard fail-closed journal-only corpus filter** (`filter_to_citeable`/`assert_no_leak`/`prune_contract_plans`/`JournalOnlyAbort`), flag `PG_SOURCE_RESTRICTION_JOURNAL_ONLY` + protocol `source_restriction: journal_only`; currently dormant (`JOURNAL_ONLY_BENCHMARK_SLUGS=frozenset()`, flag default 0) | **This is the C2-violating hard-mask-a-frozen-corpus pattern all three models reject.** Decision (§7): **do NOT extend it to other kinds.** Replace its role with the adequacy-gated + acquisition-receipt-gated `PG_SOURCE_RESTRICTION_HARD` eligibility path (§3.5). Retire the journal-only module and its call-sites, OR keep it inert behind the corpus-adequacy + receipt gate and rename kind-agnostically. **Adjudication: retire it** — a hard fail-closed corpus filter cannot be made C2-safe by generalization; the adequacy+receipt eligibility path replaces its legitimate function. |
| U12 | `run_honest_sweep_r3.py:358–359,432–434,6539,6561` `abort_journal_only_*` statuses | journal_only fail-closed abort statuses | remove with U11 (or leave as dead statuses if U11 kept-but-inert — but they should go) |

**KEEP unchanged (already general, verified at `d44ee36`):** KF `_bullet_marker_integrity_ok`/`_reemit_key_findings_bullet`; preamble shrink; `abacademies.org` denylist; `PG_TOPICALITY_HARD_FLOOR` two-tier topicality; `PG_CREDIBILITY_LLM_TIERING`; `retrieval_projection.py:695` predicate_force wiring; `:336` `op="prefer"` projection.

**Do NOT rebuild:** the compiler `predicate_force` step (already at :695) and the projection branch (already `op="prefer"`).

---

## 6. Metamorphic cross-prompt tests (M1–M9)

Shared fixture: one synthetic **60-row corpus** — 10 DOI journals, 12 `.gov` reports, 15 wire news, 8 issuer press releases, 8 analyst blogs, 7 metadata-less UNKNOWNs, plus **safety mutants** (1 retracted DOI, 1 predatory-host journal, 1 preprint-DOI, 1 DOI content-shell). Six contract fixtures. **Zero code differences between runs; only the contract is swapped.**

- **M1 `journal` (hard, systematic lit review):** journal/DOI UNKNOWNs → PASS (T1); menu sorts journal rows first; S4 reports journal share; adequacy n=10 < 25 ⇒ hard degrades to prefer + disclosure line. Fix 4: archetype `review`, H1 + "Introduction and Scope", KF after framing; **Methods stays in body** (systematic-review required section); machinery below boundary.
- **M2 `news+press_release` (hard, decision memo):** wire + issuer-PR UNKNOWNs → PASS (T2/T3-∈-allowed); journals get NO ordering boost beyond T1 quality (menu majority in-scope, NOT journal-first); S4 reports news+PR share; adequacy n=23 < 25 ⇒ degrade+disclose. Fix 4: archetype `memo`, **KF leads (BLUF)**, no "Introduction and Scope" anywhere.
- **M3 `government` (hard, policy brief):** `.gov` UNKNOWNs → PASS (T1-gov) without DOI; menu gov-first; disclosure absent iff adequacy passes at n=12. Fix 4: archetype `brief`, "Executive Summary" framing, KF leads.
- **M4 `blogs allowed` (soft prefer, market scan, no quality clause):** `build_quality_eligibility` empty plan (no high-quality request); blog rows in menu, sorted first; nothing masked; **anonymous blogs stay UNKNOWN** (not promoted merely for being blogs). Fix 4: archetype `comparison`, "Scope and Criteria" framing.
- **M5 `exclude blogs` (hard NOT_IN):** blog rows masked by the exclude facet; **a T1 `.gov`-hosted blog must NOT reach the citable menu** (INV-2 via facet mask, not tier rule); receipts show exclusion basis.
- **M6 open (no scope, no deliverable):** `RetrievalPolicy.is_empty()` ⇒ all Fix-5 code no-ops; only universal-T1 rescue may fire on UNKNOWNs; menu order unchanged. Fix 4: archetype defaults `review` + Assumption ledger entry; flag-OFF ⇒ report bytes identical to baseline.
- **M7 anti-hardcode grep (REQUIRED):** the diff introduces **no literal `journal` / `peer_review` / `doi`** outside the one T1-scholarly predicate (`_positive_signal_tier`'s reuse of `_has_doi_or_journal_credential`) and its tests, and **no literal `review` / `Introduction and Scope`** outside `ARCHETYPES` / `KIND_SYNONYMS` and their tests. Concretely: `git grep -nE 'journal|Introduction and Scope|litreview' -- src scripts | grep -v -E 'report_skeleton\.py|_positive_signal_tier|test_|journal_only_filter is RETIRED'` returns empty. **Fails the build if any journal/review literal leaks into control flow.** Then re-run M1–M6 asserting every behavioral delta traces to a contract field by diffing `SourceReceipt.basis` across swaps.
- **M8 invariant properties:** INV-3 verdict-monotonicity over all rows × all contracts; **preprint-DOI / DOI-content-shell / predatory-host / retracted do NOT PASS** (DOI-alone caveat); INV-1 via 0-diff on frozen files; adequacy boundary test (n = min_rows ± 1 flips degrade/enforce + disclosure); **acquisition-receipt test (hard mask does NOT arm on a replayed unscoped corpus even at n ≥ min_rows)**; Fix 4 body-line-multiset test (pre/post differ only by framing/boundary/preamble/order — verified sentences byte-identical).
- **M9 OFF-path golden:** champion PG_GATE-OFF render byte-identical with all flags default (`PG_REPORT_SHAPE` review-default, `PG_SOURCE_RESTRICTION_HARD` OFF) — covers both fixes.

---

## 7. Disagreements & adjudication (code-grounded)

1. **Machinery placement: Fable (archetype-invariant, methods always to appendix) vs Kimi+Codex (methods stays in body when a required section).** → **Adopt Kimi/Codex's carve-out.** Code reason: `contract.sections` (`SectionRequirement` list) already exists and already tells us which sections are contract-required; a systematic-review PRISMA Methods is scored content. The guard is 2 lines (`methods_is_machinery = not _contract_requires_section(contract,"methods")`), not a subsystem — cheap and correct. Fable's invariant is right for every archetype *except* the one where Methods is a required deliverable section.
2. **Kimi's FAIL-relaxation guard (relax `is_peer_reviewed=False`/low-tier FAIL to UNKNOWN when kind ∈ allowed).** → **REJECT.** Code reason: it violates "evidence-positive only" (INV-3), the one invariant Fable and Codex both hold absolute ("FAIL branches untouched"; Codex: "Explicit quality FAIL precedence remains"). The "high-quality-only + cite-blogs" case Kimi is solving is a genuine user contradiction → `ResearchContract.conflicts`, not a silent relaxation. And `build_quality_eligibility` only arms on `_is_high_quality_request`, so a blogs-wanted-without-quality-clause contract never enters the FAIL gate at all — the case Kimi fears is already handled by the existing `:338` gate.
3. **DOI-as-T1: Fable (DOI-or-journal ⇒ T1-scholarly) vs Codex/Kimi (DOI alone insufficient).** → **Keep Fable's reuse of `_has_doi_or_journal_credential`, add Codex/Kimi's guard as a TEST (M8).** Code reason: the landed helper is *not* "DOI alone" — its genre classifier requires article/review + journal source-type and rejects preprint DOIs; `is_citeable_journal` rejects `_PREPRINT_DOI_MARKERS`. So the substance of Codex/Kimi's objection is already met; we lock it with the preprint/shell property test rather than adding a redundant predicate.
4. **Codex's 3-way operator split (allowed IN / required REQUIRE / preferred PREFER) vs 2-way (allowed + exclude, force = strength).** → **Defer required-vs-allowed to a labelled TODO; ship 2-way for v1.** Code reason: the landed `RetrievalPolicy` has `allowed_source_kinds` + `excluded_source_kinds` + `predicate_force` only; adding `required_source_kinds`/`preferred_source_kinds` lists is a real data-model change (Codex's own §"minimal policy data model"). Under C3 (prove-not-a-regression, one thing at a time) the hard-vs-soft distinction via `predicate_force` covers the task-72 shape; "REQUIRE = represent-but-don't-exclude" is a genuinely different semantics worth doing *next*, not in the hardening pass. TODO it explicitly so it's data-not-branch later.
5. **Codex's acquisition receipt (hard mask requires proof the corpus was fetched under the contract's kind lanes).** → **Adopt, lightweight** (contract-hash match on `RetrievalPolicy.contract_hash`/retrieval receipt). Code reason: it is the strongest guard against the exact 997→131 replay failure — a frozen/replayed corpus can never arm the hard mask. Fable/Kimi's adequacy-count-alone can be fooled by a replayed corpus that *happens* to contain matching rows; the receipt closes that.
6. **Heading relabels (Kimi: memo `## Bottom Line`) vs keep `## Key Findings` (Fable).** → **Keep verbatim for v1** (Fable). Chrome churn with no measured payoff; adds anti-hardcode-grep surface for zero IF gain.
7. **D8 banner: relocate (Kimi/Codex) vs leave (Fable).** → **Relocate below H1/into appendix in shape-ON mode** (§2.4). Code reason: it directly closes verified-item-1 now, is faithfulness-neutral disclosure chrome (§-1.3), keeps the frozen builder 0-diff, and follows the shipped `compose_report_with_reliability` precedent — no need to wait on Fix 3.
8. **The journal-only hard corpus filter (`journal_only_filter.py`).** None of the three saw it (not in the pack), but all three's core thesis condemns it. → **Retire it** (U11). Code reason: a fail-closed corpus filter (`filter_to_citeable` + `assert_no_leak` + `JournalOnlyAbort`) is definitionally the "hard-mask-a-frozen-corpus" pattern C2 forbids; it cannot be made C2-safe by generalizing the kind — the adequacy-gated + acquisition-receipt-gated `PG_SOURCE_RESTRICTION_HARD` *eligibility* path (§3.5) replaces its one legitimate function (honor a hard kind restriction) without starving a frozen corpus.

---

## 8. Over-engineering watch — what NOT to build (3-way synthesis)

- **No generative/LLM report skeleton** (3/3). No LLM intro (Kimi). No audience/tone/length layout logic (Fable/Codex — "tone adaptation belongs upstream in composition," Codex). No per-archetype heading relabels for v1 (Fable).
- **No credibility ontology / no LLM inside `score_source_quality`** (3/3). Tier table ≤4 predicates over already-fetched fields; if host predicates aren't cheap, ship T1-scholarly + `kind∈allowed` and TODO the rest.
- **Do NOT generalize `_LOW_QUALITY_TIERS` / the quality tier bands.** OPUS code check: `_LOW_QUALITY_TIERS = {T5,T6,T7}` keys on **tier IDs**, not kind words — "industry/news/blog/stub" is only in the human-readable basis string. There is no kind-literal in the mask to generalize away. The contradictory contract is a conflict-ledger case.
- **Do NOT rewrite the compiler or the projection** — `predicate_force` from term force is already at `retrieval_projection.py:695`; projection already emits `op="prefer"` (:336).
- **Do NOT add `required`/`preferred` source-kind lists this run** (Codex's own model, deferred — §7.4). TODO, not build.
- **No "skeleton DSL," no new subsystem, one env flag per fix, default OFF/prior** (3/3). Champion path double-guarded by contract-presence.
- **Locate the two unanchored surfaces before writing them:** the S4 in-scope-share audit and (if kept) any residual journal-only wiring in `run_honest_sweep_r3.py`. If inside a frozen file, compute at menu construction. Do not guess.
- **The run's job is prove-not-a-regression** — reach ≈ champion IF 0.4587; do not add scope to beat it.
