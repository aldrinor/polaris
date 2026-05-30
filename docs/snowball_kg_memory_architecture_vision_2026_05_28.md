# POLARIS Snowball Knowledge-Graph Memory — Architecture Vision

## 1. Plain summary (read this first)

Here is the whole idea in plain words. POLARIS today is a research machine
that takes one question at a time through four AI models — a Generator that
writes the answer, a Mirror that checks each claim is actually supported, a
Sentinel that hunts for made-up statements, and a Judge that grades every
single claim one of five honest verdicts: verified, partial, unsupported,
fabricated, or unreachable — wrapped by plain Python checks and a final
line-by-line Codex audit; that is the "mighty machine," and it already runs.
We want to add two things: make it **pausable and resumable** so we can stop
at any stage and pick up exactly where we left off without paying twice or
losing a verdict, and give it a **memory that snowballs** — instead of
forgetting everything when a run ends, every claim the Judge verifies is
saved into one growing knowledge graph (claims, their sources, and how they
relate) so the next run builds on what we already proved and, most
importantly, can catch when a brand-new claim **contradicts something we
verified weeks ago or contradicts the wider record** — which a single run
looking only at today's evidence can never see. This is **design only**: no
build, no spend, everything self-hosted with no US vendor in the runtime
path, and the build happens **only after** the four-role base passes its
first clean dry run.

---

## 2. What exists today vs. what's new

Being honest about the starting line matters here, because parts of this
**look** done and are not.

### What genuinely exists

- **A per-run claim graph (real, but one run only).** The backend
  `build_graph_payload()` (`src/polaris_graph/api/graph_route.py`) already
  turns one finished run into a graph of nodes (sentence, source, section,
  frame) and edges (`cites`, `contradicts`, `section_member`), served at
  `GET /api/runs/{run_id}/graph`. It is rebuilt on request and **never
  saved** as a graph. It never joins two runs together.
- **A working graph UI for one run.** `web/app/runs/[runId]/graph/page.tsx`
  renders that graph with cytoscape, and there is even a working 2-hop
  "snowball" walk (`snowball.ts`) over the semantic edges. This viewer is
  reusable as-is — it just has nothing cross-run to point at yet.
- **A deterministic contradiction detector (one run only).**
  `contradiction_detector.py` is rule-based and compares
  `(subject, predicate, number, unit)` tuples **within a single run's
  evidence pool**. It deliberately refuses to use an LLM for numeric
  contradiction (LLMs treat 14% and 17% as "roughly the same"). This is the
  exact logic the cross-time check must extend — not replace.
- **The verified-claim record already has the right shape.** `ClaimRow`
  (`benchmark/claim_audit_scorer.py`) and the ledger `Claim`/`Verdict`
  (`scripts/dr_benchmark/ledger_schema.py`) already carry our five-verdict
  enum **byte-for-byte**, plus severity, citation id, the exact fetched span
  quote, and audit notes. The knowledge-graph claim node **is** this record
  plus an identity key, provenance, and a timestamp. We do not invent a new
  verdict shape.
- **The target research is written.**
  `docs/clinical_rag_sota_deepest_research_2026_05_27.md` specifies a
  persistent sovereign clinical-DB grounding layer (mirrors of
  ClinicalTrials.gov / FDA / EMA / Health Canada) and a claim-decomposition +
  3-way NLI + KG-fusion pattern. The snowball is **distinct from and
  composable with** that layer (see §3.5).

### What is sketched but is the wrong thing, or wired to the wrong pipeline

- **A flat vector store, not a graph.** `cross_vector.py`
  (`promote_to_ltm` / `query_ltm`, ChromaDB collection
  `polaris_ltm_global`) accumulates **statement documents with metadata** —
  no edges, no claim-to-claim relations, no contradiction links. It is a
  similarity cache, and a useful **retrieval substrate** for the snowball,
  but it is not a graph.
- **It has never accumulated anything.** The ChromaDB store
  (`data/chroma_db/chroma.sqlite3`) has **0 collections, 0 embeddings**. And
  `promote_to_ltm`/`query_ltm` are called only from `graph.py` (the
  LangGraph UI, pipeline B) — **never** from the active four-role
  honest-sweep path. The accumulation primitive exists, is empty, and is
  plumbed to the wrong pipeline.
- **Pause/resume exists, is off, and is for the wrong pipeline.**
  `checkpoint_manager.py` is real LangGraph SQLite checkpointing, but it is
  feature-flagged off (`PG_CHECKPOINT_ENABLED=0`), its DB is 3 bytes
  (never used), and it only attaches to pipeline B. The locked four-role
  path is **plain sequential Python** with no checkpointer — so today the
  "pausable/resumable" requirement is **not wired to the locked machine.**

### What is genuinely new (the gap-to-real)

The one sentence that defines the work: **neither existing piece is a
persisted, cross-run, verdict-typed claim graph with cross-run
contradiction edges.** The vector store has accumulation but no structure;
the graph has structure but is per-run and ephemeral. The snowball is their
**union, plus a verdict-trust layer, plus a cross-time contradiction check,
plus a write path from the locked run.** All four are unbuilt.

> **Honesty flag for any demo:** the home-page "Snowball" card
> (`web/app/page.tsx`) says each run "grows a connected knowledge graph …
> and build the next question from." That is true **per run**. The cross-run
> **compounding it implies does not exist in code yet.** Scope the claim to
> per-run until the accumulating KG is built.

> **Not the KG (do not conscript it):** `relation_builder.py` is named like
> a graph builder but is **statistical** — it builds DEFF/ICC variance-
> deflation clustering criteria for the statistical contract, over one run.
> Its "relations" are unrelated to claim entailment/contradiction. (Its
> typed-pair, fail-closed primitive may be reused only as a generic
> edge-construction helper — never as the claim-relation engine.)

---

## 3. The snowball KG

### 3.1 The node and edge schema

**Claim node — the atom.** It wraps the existing `ClaimRow` verbatim and
adds the fields the snowball needs:

- *From `ClaimRow`:* `claim_id`, `severity` (S0–S3), `verdict` (the five-
  value enum), `citation_id`, `span_quote` (the **exact fetched cited span**
  — this is the §-1.1 anchor, never a title or abstract),
  `unreachable_subtype`, `audit_note`.
- *Identity key (clinical-safe dedup):*
  `canonical_key = hash(subject, predicate, dose, arm, timepoint,
  population, unit)`. This is the `contradiction_detector` tuple **extended**
  with arm/timepoint/population. Using `(subject, predicate)` alone is a
  clinical-safety bug — tirzepatide weight-loss at 5 mg and at 10 mg are
  **different claims**; collapsing them would manufacture a false
  contradiction or a false re-confirmation.
- *Numeric payload:* `value`, `unit`, `sign` (drives deterministic
  contradiction).
- *Provenance:* `source_url`, `source_tier` (T1 RCT … T6 industry blog),
  `evidence_id`, `run_id`, `vector_id`, `generator_model`, `judge_model`.
- *Verdict provenance (the load-bearing pair — see §3.6):*
  `verdict_source ∈ {judge_runtime, codex_s11_audit}`;
  `trust_tier ∈ {PROVISIONAL, DURABLE}`. **Only DURABLE compounds.**
- *Time:* `timestamp_verified` (**passed in** — the run's verification time,
  never machine-generated), `first_seen`, `last_confirmed`.
- *Re-confirmation:* `confirmation_count`, `confirming_run_ids[]`.

**Entity node** — typed: drug | condition | intervention | endpoint |
population. Carries a normalized label + a synonym set (tirzepatide ↔
LY3298176 ↔ Mounjaro/Zepbound), resolved by a deterministic, mirror-able
ontology (RxNorm/MeSH-style — sovereign).

**Source node** — one per normalized URL (reuses
`source_content_store._normalize_url`). Carries `source_tier`, domain, title,
`fetch_status`, `content_hash`.

**Edges** (each carries `created_at` + the introducing `run_id` for audit —
LAW IV):

- `(claim) -cites-> (source)` — with citation id + span offsets.
- `(claim) -about-> (entity)` — one per qualifier in the identity key.
- `(claim) -supports-> (claim)` — same identity key, numeric agreement,
  independent source → corroboration / re-confirmation.
- `(claim) -contradicts-> (claim)` — same identity key, numeric divergence
  past threshold, **same source tier** → genuine cross-time contradiction.
  Carries absolute/relative difference + severity (reuses
  `contradictions.json` shape) + an `adjudication` field filled later by
  Sentinel/Judge.
- `(claim) -supersedes-> (claim)` — same identity key, divergence, but
  **higher tier or newer authoritative timestamp** → knowledge evolution,
  **not** a contradiction (a T1 RCT superseding a T6 blog is an upgrade).

Every node traces to a fetched span, a verdict, a verdict source, and a
trust tier. **The graph never asserts a verdict — it stores the verdict the
Judge or the §-1.1 audit produced, with the provenance to know which.**

### 3.2 Self-hosted store (license + maintenance verified May 2026)

- **PRIMARY — SQLite-as-graph.** Node/edge tables via `aiosqlite` +
  recursive-CTE traversal + `sqlite-vec` for embedding dedup. **It reuses
  the repo's exact substrate** — `campaign_store`, `evidence_hierarchy`,
  `source_content_store` are all already `aiosqlite`. Zero new server, zero
  ops, public-domain core, trivially sovereign (a file on POLARIS infra).
  The graph is shallow (claim→source/entity, 1–2 hop contradiction queries),
  so CTEs are sufficient — we are not doing deep graph analytics.
- **FALLBACK — Oxigraph** (Apache-2.0, actively maintained: repo updated
  2026-05-20; Rust; Python-embeddable; SPARQL; in-memory or RocksDB). Use
  only if native traversal outgrows CTEs. No JVM, strong sovereign fit.
- **REJECTED — KuzuDB.** The obvious embedded "SQLite-of-graphs" pick is MIT
  but was **archived/abandoned by Kuzu Inc in Oct 2025** (forks
  RyuGraph/bighorn immature). Maintenance disqualifier — recommending it on
  license alone would have been the bug.
- **NOT RECOMMENDED — Neo4j Community** (GPLv3 + JVM server): a
  Carney-distribution GPL caveat plus ops burden a single-operator zero-ops
  tool should avoid. Noted only as an "if we ever need Cypher + Bloom" line.
- **Embedding dedup index stays where it lives:** ChromaDB
  (`cross_vector`'s `polaris_ltm_global`) with the **local** SentenceTransformer
  `all-MiniLM-L6-v2` (`src/utils/embedding_service.py`) — no new vector
  store, no network embedding call.

### 3.3 Accumulation (the write path)

At the end of each run, for each claim the Judge VERIFIED (PARTIAL /
UNSUPPORTED are stored but quarantined; FABRICATED / UNREACHABLE never enter
the graph):

1. Build `canonical_key` from the full qualifier tuple.
2. Vector-retrieve candidate priors (`query_ltm`) by embedding similarity to
   narrow the deterministic search.
3. Deterministic identity match against those candidates:
   - **Key miss → NEW node.** `first_seen = last_confirmed =
     timestamp_verified`; `confirmation_count = 1`.
   - **Key hit + numeric agreement → RE-CONFIRMATION.** Do **not** duplicate
     the node. Increment `confirmation_count`, append `run_id` to
     `confirming_run_ids`, update `last_confirmed`, add a `supports` edge.
     *(This is exactly how the snowball distinguishes a new verified claim
     from a re-confirmation.)*
   - **Key hit + numeric divergence → §3.4.**
4. **Trust-tier on write:** a `judge_runtime` verdict is written
   **PROVISIONAL**. When the out-of-band Codex §-1.1 audit ledger for that
   run lands, a reconcile pass upgrades matching VERIFIED claims to
   **DURABLE** (`verdict_source = codex_s11_audit`). PROVISIONAL claims are
   stored and queryable for telemetry/contradiction, but are **excluded from
   "prior-verified ground truth" reads.**
5. **Idempotent on `run_id`** (re-running a run never double-counts), mirroring
   `source_content_store`'s INSERT-OR-REPLACE discipline.

### 3.4 Cross-time contradiction detection (the snowball superpower)

This is the thing per-run corpus checking **cannot** catch: *"this new claim
contradicts a claim we verified two months ago."*

- **WHO does it: a NEW deterministic write-time step,
  `graph_contradiction_check` — NOT an LLM role.** It extends
  `contradiction_detector`'s exact deterministic logic (same
  `(subject, predicate, value, unit)` tuple, same env-configurable
  thresholds, ~10% relative / 2.0 absolute) **from within-run to across the
  persistent graph.** The repo's ban on LLM numeric contradiction is
  preserved.
- **Mechanism on key-hit + divergence:** compare tiers + timestamps.
  - Same tier, divergent → emit a **`contradicts`** edge (genuine cross-time
    contradiction), severity from the difference.
  - Higher tier or newer-authoritative → emit a **`supersedes`** edge
    (knowledge evolution, not a contradiction).
- **Sentinel / Judge ADJUDICATE, never DETECT.** Once the deterministic step
  *flags* a `contradicts` edge, Sentinel (granite-guardian) and/or Judge
  (qwen) are invoked only to **explain** it — genuine disagreement vs. a
  stratification / dosing / population / duration artifact the identity key
  did not capture. Their structured output is written to the edge's
  `adjudication` field. Detection stays deterministic; interpretation is the
  LLMs' job.
- **Output surface:** flagged cross-time contradictions are written into the
  run's existing `contradictions.json` **and** surfaced to the §-1.1 audit,
  so Codex sees *"your new claim X conflicts with previously-§-1.1-DURABLE
  claim Y"* — the global check a single-run corpus is blind to.

### 3.5 How this relates to the research doc's Layer-6

The SOTA research doc proposes a Layer-6 persistent mirror of external
authoritative DBs (ClinicalTrials.gov / FDA / EMA / Health Canada). The two
are **different truth sources, both global, both composable:**

- **Layer-6** catches *"contradicts an external authoritative database"* —
  requires external ETL of public registries.
- **The snowball** catches *"contradicts a claim WE ourselves verified
  before"* — self-bootstrapping, no ETL, self-feeding.

Both run at the same deterministic write-time hook. The snowball is the
cheaper, self-feeding one and ships first; Layer-6 layers in later.

### 3.6 Why the trust tier is the most important decision

The runtime lock makes the **Judge (qwen) the in-pipeline arbiter** while the
**Codex §-1.1 audit is the out-of-band human-equivalent gate** — two
different sources for the same five-value verdict. A claim can be
Judge-VERIFIED yet later §-1.1-FABRICATED. If we compound on un-§-1.1-audited
Judge verdicts at full confidence, **accumulation re-introduces the exact
"automated check is lethal in clinical context" failure that §-1.1 exists to
prevent — through the back door of compounding.** The `PROVISIONAL` →
`DURABLE` tier is the structural fix: **only DURABLE (§-1.1-confirmed
VERIFIED) claims may be cited as prior-verified ground truth in future runs.**

---

## 4. Pausable / resumable (in POLARIS's own Python)

The locked four-role path is plain sequential Python — **do not reuse the
LangGraph `checkpoint_manager` (pipeline B).** Instead, mirror the semantics
of `src/orchestration/persistence.py::save()` (atomic JSON write + named
history snapshots), the pipeline-A analog of pipeline-C's `last_pointer.json`
and `progress_ledger.jsonl`. Two artifacts per run, both under the run's own
`outputs/.../<slug>/` directory (so LAW VII CLI isolation holds — these are
**not** shared with pipeline C):

- **`run_state.json` (the resume cursor — new).** Holds: `run_id`, `slug`,
  `protocol_sha256` (binds resume to the exact protocol),
  `stage` ∈ {`retrieval_done` → `corpus_approved` → `generator_done` →
  `per_claim_loop` → `judge_done` → `complete`}, `effective_config_hash`,
  `retrieval_state` (evidence-pool sha + corpus-approval decision, so resume
  never re-bills retrieval), and **two integer cursors:**
  `verdict_done_through_n` (claims with a written Judge verdict) and
  `kg_committed_through_n` (claims flushed to the KG). A crash between
  verdict-write and KG-write then **loses neither and double-writes neither.**
- **`verdict_ledger.jsonl` (append + fsync after each Judge verdict).**
  Reuses `ledger_schema.Claim`. This single file is simultaneously the
  **resume log, the KG write-queue, and the §-1.1 audit input** — one
  structure serving three masters.

**Checkpoint boundaries** are the role boundaries: after Generator (partial
sections + provenance tokens), after each per-claim Mirror→Sentinel→Judge
step (append one ledger line, `verdict_done_through_n++`), and after Judge
(aggregate verdicts into `manifest.json` as today).

**Resume algorithm:** load `run_state.json`; **re-verify
`protocol_sha256` + `effective_config_hash`, fail closed on drift** (reuse
the gate's existing no-drift check — never relax this); skip all stages ≤
`stage`; replay surviving claims from `verdict_done_through_n` onward
(Generator output + strict_verify survivors are deterministic given the
persisted evidence pool, so they need not re-run). The run can stop and
resume after Generator, after Mirror, after Sentinel, after Judge, or
mid per-claim loop.

---

## 5. Integration — a 5th cross-cutting layer that WRAPS the locked 4 roles

**The four LLM roles (Generator / Mirror / Sentinel / Judge) and the two
deterministic layers (python_validators / §-1.1) are LOCKED and UNTOUCHED.**
Both the KG and pausability are a **cross-cutting 5th layer that wraps the
four roles** — a memory + run-state harness *around* the pipeline, never a
node *inside* it. No new inference role; no `family_policy` change. The lock
pins models / families / role-existence, **not prompt inputs** — so feeding a
KG-derived signal into an existing prompt is provably not a lock mutation.

**Two read sites, both as SIGNALS only:**

- **(a) Generator grounding time** — query the KG for **DURABLE,
  canonical-tier** prior claims related to the question and inject them as
  *additional evidence rows*. **Hard provenance constraint (§9.1 invariant):**
  an injected node must carry its **original `evidence_id` + source span**,
  so `strict_verify` (numeric match + ≥2 content-word overlap + span overlap)
  and provenance tokens still hold. *"The KG asserted X" must NEVER become a
  citation* — re-inject the original source, not the claim text as a
  pseudo-source. **Only `section_1_1_confirmed`/DURABLE nodes are eligible to
  feed back; `judge_verified`/PROVISIONAL nodes are not** (this is the
  fabrication-propagation firewall).
- **(b) Pre-Judge cross-time contradiction check** — for each surviving
  claim, run `graph_contradiction_check` (§3.4) and feed any
  `cross_time_contradiction` flag as an extra input into the existing
  Mirror→Sentinel→Judge chain. **Judge arbitrates; the KG never decides.**

**One write site:** after Judge, per §3.3 (two-tier, idempotent, retraction-
capable). A `retraction` path (reuse `cross_vector.store_human_override`)
marks a node `retracted` with the refuting span + auditor + timestamp when
§-1.1 or a later cross-time check refutes it; retracted nodes are excluded
from all reads. This closes the *"one Judge-passed fabrication compounds
forever"* failure mode.

**The planned-layer entry for the runtime lock.** Add a **new top-level key,
sibling to `required_roles`** (never under it), to
`config/architecture/polaris_runtime_lock.yaml`:

```yaml
planned_layers:
  snowball_kg:
    status: design_only        # design_only -> planned -> active
    layer_type: cross_cutting_memory
    touches_required_roles: false
    read_sites: [generator_grounding_durable_tier, pre_judge_cross_time_contradiction]
    write_trigger: judge_verdict_in [VERIFIED, PARTIAL]
    node_tiers: [judge_verified_provisional, section_1_1_confirmed_durable, retracted]
    store: sqlite_as_graph_local            # fallback: oxigraph_local
    embedding: sentence_transformers_all_minilm_l6_v2_local
    contradiction_comparator: src/polaris_graph/retrieval/contradiction_detector.py
    edge_primitive: deterministic_typed_pair
  pausable_resume:
    status: design_only
    layer_type: cross_cutting_runstate
    artifacts: [run_state.json, verdict_ledger.jsonl]
    checkpoint_boundaries: [generator_done, per_claim_mirror_sentinel_judge, judge_done]
```

Because `pathB_run_gate._assert_architecture_coverage()` iterates **only**
the `required_roles` keys, this sibling key is **invisible to the coverage
gate** — the four-role freeze behaves byte-for-byte as it does today. The
same lock-mutation policy still applies (Codex APPROVE on a brief + operator
commit signature + propagation manifest re-run + `canonical_pin.txt` re-track).
Promotion `design_only -> active` is gated on §6.

---

## 6. Sequencing — design now, build after the base dry-runs

This is **design only.** No build, no spend. The explicit dependency chain:

1. **I-meta-002 (the locked four-role base) must reach a passing dry run
   first.** It is itself currently **blocked** — Cohere Command A+ and
   Granite Guardian 4.1 8B are not on OpenRouter, serving is routed to
   Vast.ai, and the Vast.ai balance is **$0** pending operator credit-load.
2. **Why the dependency is hard, not cosmetic:** the verdict-typed nodes
   (§3.1) and the run-to-graph write path (§3.3) both **require the Judge to
   actually emit the five-value verdicts.** Building the KG before the Judge
   exists would force placeholder verdict values — a LAW-II violation. The
   schema can be designed now; the write path cannot be built until the Judge
   emits.
3. **Build order once unblocked:** (a) pausable run-state harness (§4) —
   independent of the KG, lowest risk; (b) KG store + write path on
   PROVISIONAL tier (§3.3); (c) §-1.1 reconcile → DURABLE promotion (§3.6);
   (d) cross-time `graph_contradiction_check` (§3.4); (e) DURABLE-only
   Generator grounding read (§5a); (f) cross-run UI surface (reuses the
   existing cytoscape viewer + `snowball.ts` BFS verbatim, new
   `getGlobalGraph` endpoint + route).

---

## 7. Sovereignty

- The KG is a **single local file** (SQLite primary) or a single RocksDB dir
  (Oxigraph fallback) on POLARIS-controlled infra (OVH Québec / EU).
  Gitignored like the other `state/` DBs. **No US-managed graph cloud**
  (Neptune, TigerGraph Cloud are disqualified).
- Embeddings use the **local** `all-MiniLM-L6-v2` SentenceTransformer — no
  network embedding call, no US embedding vendor. Per the narrow threat
  model: US-origin open-source self-hosted is fine (license path, not
  training origin); a US-**managed-runtime** vendor is not.
- The research doc's Layer-6 mirrors (ClinicalTrials.gov / FDA / EMA) are
  public-domain and mirror-able locally — consistent with the no-US-runtime
  threat model.
- No PII: claims are about drugs / conditions / endpoints from public
  literature, not patients. If patient-derived corpora are ever ingested, a
  span-level redaction gate at the write path is the documented extension
  point (out of scope here).
- All thresholds (numeric divergence, tier-supersede rules, trust-tier
  promotion, similarity cutoff) come from env vars per LAW VI — zero
  hardcoding.

---

## 8. Open questions for Codex

1. **Trust-tier latency.** The PROVISIONAL→DURABLE firewall only works if the
   §-1.1 reconcile pass actually runs and upgrades. If the §-1.1 audit lags
   the run, the graph holds only PROVISIONAL nodes and **nothing compounds.**
   Is "stale PROVISIONAL claims are visibly quarantined, never silently
   promoted, and never read as ground truth" sufficient, or do we need a
   freshness/staleness alarm on PROVISIONAL backlog?
2. **Identity-key completeness.** The qualifier set
   `(subject, predicate, dose, arm, timepoint, population, unit)` is a
   starting point. Are we missing material clinical qualifiers (fasting vs.
   fed, background therapy, ITT vs. per-protocol)? A missing qualifier is a
   clinical-safety bug — false merge or false contradiction — not a tuning
   knob. Does this need clinical-SME sign-off before BUILD?
3. **Entity resolution.** A missed alias (tirzepatide ↔ Mounjaro ↔
   LY3298176) splits one entity into two and **silently breaks cross-time
   linkage** — the contradiction is never detected because the claims do not
   share an entity node. Is a deterministic RxNorm/MeSH mirror the right
   sovereign dependency, and does it compose cleanly with the research-doc
   Layer-6 ETL?
4. **Snowball poisoning / error propagation.** A wrong DURABLE claim becomes
   future ground truth (the adversarial-propagation class, ~82% propagation
   in the literature). DURABLE requires §-1.1 confirmation and `supersedes`
   keeps history for retraction — is that enough, or do we need periodic
   re-audit of high-fan-out DURABLE claims?
5. **Cross-time threshold profiles.** The detector's 10%-relative /
   2.0-absolute thresholds were tuned for intra-run metabolic predicates.
   Cross-time / cross-domain scope likely needs per-domain profiles.
   Over-flagging floods Judge; under-flagging misses real global
   contradictions. How should the profile set be governed?
6. **KG growth / eviction.** An unbounded store accumulating across all runs
   needs a freshness/eviction policy (an FDA label or trial readout can be
   superseded). `freshness_monitor.py` exists for the retrieval cache — is it
   the right model for canonical KG nodes, and should `supersedes` be the
   eviction mechanism (keep history) rather than deletion?
7. **Store pick reversibility.** SQLite-as-graph is the lowest-risk reuse,
   but if queries outgrow recursive CTEs, migrating to Oxigraph is real work.
   Given the KuzuDB abandonment, is "pick the substrate the repo already runs
   (SQLite), accept a possible later Oxigraph migration" the right risk
   posture for a single-operator zero-ops tool?
8. **Fail-loud on write.** `cross_vector` degrades silently (returns empty /
   logs a warning) when ChromaDB is unavailable — which is how the store is
   empty today with no error. A future KG must **fail loudly** on write/read
   failure (LAW II), or the snowball silently stops growing. Confirm the
   write path is fail-closed, not degrade-silent.

---

## Document metadata

- **title:** POLARIS Snowball Knowledge-Graph Memory — Architecture Vision
- **status:** DESIGN-ONLY (no build, no spend)
- **audience:** operator (blind-readable; plain summary leads) + Codex review
- **date:** 2026-05-28
- **depends_on:** I-meta-002 (4-role base) reaching a passing dry run before any BUILD
- **sovereignty:** everything self-hosted, no US runtime vendor
- **verdict_scale:** {VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE}
