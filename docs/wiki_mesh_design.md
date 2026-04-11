# POLARIS Wiki Mesh — Design Document

**Status:** Design adopted 2026-04-10. Build in progress. Unit 1 (schema + store) starting.
**Owners:** PL branch.
**Supersedes:** `plans/vivid-waddling-riddle.md` (the original wiki ship plan, Phase 1 complete).
**Goal:** Transform POLARIS from a one-shot research pipeline into a persistent, self-growing research expert that beats top-tier human experts and top-tier AI research models (Gemini 3.1 Pro Deep Research, Claude Opus 4.6, GPT-5.4).

---

## 0. Why this document exists

Two earlier architectural passes gave partial answers. A deep advisor review identified **10 structural bugs** in the initial plan, three of them deadly. This document is the corrected, complete plan. Every fix from the review is integrated inline. Nothing selective.

The three deadly bugs the review caught, and how they're fixed in this plan:

| ID  | Bug                                                    | Fix                                                             |
| --- | ------------------------------------------------------ | --------------------------------------------------------------- |
| D1  | Dual-store (ChromaDB + SQLite) consistency race        | **sqlite-vec in the same database file** — single transaction  |
| D2  | Entity canonicalization permanently poisons the mesh   | **entity.confidence column** + quarantine queue + user review  |
| D3  | Snowball becomes a popularity trap                     | **10% exploration budget** + age-decayed usage bonus           |

Seven additional serious/underestimated issues are also corrected in this plan (S4–S8, U9–U10, see §4).

---

## 1. The whole system in one frame

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        POLARIS WIKI MESH SYSTEM                         │
│                                                                         │
│  INGEST                MESH (persistent)               Q&A              │
│  ──────                ─────────────────              ────              │
│                                                                         │
│  uploads  ┐                                                             │
│  (PDFs,   │  extract    ┌──────────────┐   retrieve   ┌──────────┐     │
│   MDs,    ├──────────►  │ L1 SOURCE    │◄─────────────┤ question │     │
│   CSVs)   │             │    PAGES     │              └────┬─────┘     │
│           │             ├──────────────┤                   │           │
│  web      │  fetch+     │ L2 CLAIM     │   edge-walk       ▼           │
│  results  ├──────────►  │    GRAPH     │◄────────────┌──────────┐     │
│  (Serper, │  extract    │  (edges:     │              │ compose  │     │
│   S2,     │             │  corrob,     │              │ +artifact│     │
│   OAX)    │             │  contradic,  │              └────┬─────┘     │
│           ┘             │  elaborate,  │                   │           │
│                         │  cites)      │                   ▼           │
│                         ├──────────────┤              ┌──────────┐     │
│                         │ L3 ENTITIES  │              │  answer  │     │
│                         │ (canonical,  │              │ +charts  │     │
│                         │  confidence) │              │ +tables  │     │
│                         ├──────────────┤              │ +slides  │     │
│                         │ L4 TOPICS    │              └────┬─────┘     │
│                         │  (emergent,  │                   │           │
│                         │  clustered)  │                   │           │
│                         └──────┬───────┘                   ▼           │
│                                │                     ┌──────────┐     │
│                                │  snowball feedback  │ feedback │     │
│                                │  (bounded, w/       │ (used,   │     │
│                                │   exploration)      │  rated)  │     │
│                                └─────────────────────┤          │     │
│                                                      └──────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
```

**Three facts to internalize:**
- **Sources and claims are separate.** A source is the markdown document. A claim is an atomic factual statement extracted from that document. The mesh is built on claims, not sources.
- **Edges, not topics, are primary.** Topics are derived from claims by clustering. Edges (corroboration, contradiction, elaboration) are authored by the system at ingest time.
- **Snowball is a bounded feedback loop, not a growth loop.** The mesh doesn't just grow; existing claims get heavier as they get cited, corroborated, or used to answer questions — but reinforcement is capped and includes an exploration budget for unused high-tier claims.

---

## 2. Storage layout on disk

Single-database design (post-fix D1). sqlite-vec provides vector virtual tables inside the same mesh.db file — no dual-store consistency bugs.

```
wiki/
├── workspaces/
│   └── {workspace_id}/
│       ├── mesh.db                  # SQLite — SINGLE source of truth for graph + vectors
│       ├── sources/                 # The raw L1 layer on disk
│       │   ├── web_abc123.md        # one markdown file per source
│       │   ├── upload_xyz789.md
│       │   └── {source_id}.meta.json
│       ├── artifacts/               # Generated by compose
│       │   └── {answer_id}/
│       │       ├── report.md
│       │       ├── chart_01.png
│       │       ├── table_01.md
│       │       ├── slides.pptx
│       │       └── flashcards.json
│       ├── snapshots/               # Versioning (U10: zstd compressed)
│       │   └── {timestamp}/mesh.db.zst
│       └── log.jsonl                # append-only operation log (mirrors op_log table)
```

SQLite holds the mesh AND the vectors (via sqlite-vec virtual tables). Markdown holds the reading-level truth. Artifacts hold the answer-level outputs. Nothing is in memory-only. Nothing is split across stores.

---

## 3. Schema — every table, every column

### 3.1 Core tables

```sql
-- ───────── META ─────────
CREATE TABLE mesh_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- seeded with ("schema_version", "1") at creation

-- ───────── WORKSPACES ─────────
CREATE TABLE workspaces (
    id                              TEXT PRIMARY KEY,
    name                            TEXT NOT NULL,
    owner                           TEXT,
    root_question                   TEXT,
    created_at                      TIMESTAMP NOT NULL,
    source_count                    INTEGER DEFAULT 0,
    claim_count                     INTEGER DEFAULT 0,
    edge_count                      INTEGER DEFAULT 0,
    last_ingest_at                  TIMESTAMP,
    -- FIX S6: daily NEARBY expansion budget
    nearby_expansion_budget_daily   INTEGER DEFAULT 50,
    nearby_expansions_today         INTEGER DEFAULT 0,
    nearby_expansion_reset_at       DATE
);

-- ───────── L1: SOURCE PAGES ─────────
CREATE TABLE source_pages (
    id                TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    kind              TEXT NOT NULL CHECK (kind IN ('web', 'upload', 'api')),
    url               TEXT,
    filepath          TEXT NOT NULL,            -- relative path to markdown
    title             TEXT,
    authors           JSON,                     -- ["Smith, J", ...]
    year              INTEGER,
    doi               TEXT,
    venue             TEXT,
    fetched_at        TIMESTAMP NOT NULL,
    content_hash      TEXT NOT NULL,            -- sha256 of cleaned content (dedup)
    word_count        INTEGER,
    sig_authority     REAL NOT NULL,            -- 0.30 web / 0.85 peer-rev / 0.95 upload
    times_cited       INTEGER DEFAULT 0,        -- snowball
    last_used_at      TIMESTAMP,
    retracted         BOOLEAN DEFAULT 0,
    retraction_reason TEXT,
    UNIQUE (workspace_id, content_hash)
);
CREATE INDEX ix_src_workspace ON source_pages(workspace_id, kind);
CREATE INDEX ix_src_authority ON source_pages(workspace_id, sig_authority DESC);

-- ───────── L2: CLAIMS ─────────
CREATE TABLE claims (
    id                TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_page_id    TEXT NOT NULL REFERENCES source_pages(id) ON DELETE CASCADE,
    statement         TEXT NOT NULL,
    direct_quote      TEXT NOT NULL,
    char_start        INTEGER NOT NULL,
    char_end          INTEGER NOT NULL,
    tier              TEXT NOT NULL CHECK (tier IN ('GOLD', 'SILVER', 'BRONZE')),
    relevance_score   REAL NOT NULL,
    has_numeric       BOOLEAN DEFAULT 0,        -- CI / p-value / n= / % / ±
    extracted_at      TIMESTAMP NOT NULL,
    times_used        INTEGER DEFAULT 0,        -- snowball (D3: age-decayed)
    last_used_at      TIMESTAMP,
    flagged           BOOLEAN DEFAULT 0,        -- G5: user override
    flagged_reason    TEXT
);
CREATE INDEX ix_clm_source      ON claims(source_page_id);
CREATE INDEX ix_clm_ws_tier_rel ON claims(workspace_id, tier, relevance_score DESC);
CREATE INDEX ix_clm_ws_usage    ON claims(workspace_id, times_used DESC, last_used_at DESC);
CREATE INDEX ix_clm_ws_flagged  ON claims(workspace_id, flagged);

-- ───────── L2: EDGES (FIX S4: split weight columns) ─────────
CREATE TABLE edges (
    id                TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    claim_a           TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    claim_b           TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    kind              TEXT NOT NULL CHECK (kind IN ('corroborates','contradicts','elaborates','cites')),
    evidence_weight   REAL NOT NULL,            -- IMMUTABLE: from NLI/cosine at discovery
    usage_boost       REAL NOT NULL DEFAULT 0,  -- MUTABLE: capped at +0.2
    discovered_at     TIMESTAMP NOT NULL,
    discovery_method  TEXT NOT NULL,
    UNIQUE (claim_a, claim_b, kind)
);
CREATE INDEX ix_edge_a_kind ON edges(workspace_id, claim_a, kind);
CREATE INDEX ix_edge_b_kind ON edges(workspace_id, claim_b, kind);

-- ───────── L3: ENTITIES (FIX D2: confidence gating) ─────────
CREATE TABLE entities (
    id                TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    canonical_name    TEXT NOT NULL,
    aliases           JSON,                     -- ["PFOS","C8","perfluorooctane sulfonate"]
    entity_type       TEXT NOT NULL,            -- compound|method|organization|person|metric|concept
    description       TEXT,
    confidence        REAL NOT NULL DEFAULT 0.5,-- FIX D2: <0.8 quarantined from retrieval
    user_confirmed    BOOLEAN NOT NULL DEFAULT 0,
    times_referenced  INTEGER DEFAULT 0,
    UNIQUE (workspace_id, canonical_name)
);
CREATE INDEX ix_ent_ws_conf ON entities(workspace_id, confidence DESC);

CREATE TABLE claim_entities (
    claim_id          TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    entity_id         TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (claim_id, entity_id)
);
CREATE INDEX ix_ce_entity ON claim_entities(entity_id);

-- ───────── L4: TOPICS (emergent, clustered) ─────────
CREATE TABLE topics (
    id                TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title             TEXT NOT NULL,
    description       TEXT,
    created_from      JSON,                     -- seed claim_ids
    size              INTEGER DEFAULT 0,
    created_at        TIMESTAMP NOT NULL,
    last_refreshed_at TIMESTAMP,
    dirty             BOOLEAN DEFAULT 0         -- marked for re-cluster
);

CREATE TABLE topic_claims (
    topic_id          TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    claim_id          TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    rank              REAL NOT NULL,
    PRIMARY KEY (topic_id, claim_id)
);

-- ───────── Q&A LAYER ─────────
CREATE TABLE questions (
    id                TEXT PRIMARY KEY,
    workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    text              TEXT NOT NULL,
    parent_id         TEXT REFERENCES questions(id),  -- follow-up chain
    asked_at          TIMESTAMP NOT NULL,
    asked_by          TEXT
);

CREATE TABLE answers (
    id                TEXT PRIMARY KEY,
    question_id       TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    text              TEXT NOT NULL,
    retrieved_claims  JSON,
    cited_claims      JSON,
    artifact_paths    JSON,
    model             TEXT,
    quality_score     REAL,
    created_at        TIMESTAMP NOT NULL
);

-- ───────── FEEDBACK (drives snowball) ─────────
CREATE TABLE feedback (
    id                TEXT PRIMARY KEY,
    answer_id         TEXT NOT NULL REFERENCES answers(id) ON DELETE CASCADE,
    claim_id          TEXT REFERENCES claims(id) ON DELETE SET NULL,
    kind              TEXT NOT NULL CHECK (kind IN ('used','upvoted','downvoted','flagged_wrong','cited_in_export')),
    timestamp         TIMESTAMP NOT NULL
);

-- ───────── OP LOG (append-only, for undo/rewind) ─────────
CREATE TABLE op_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id      TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    timestamp         TIMESTAMP NOT NULL,
    op_kind           TEXT NOT NULL,            -- insert_source|insert_claim|insert_edge|flag|...
    affected_ids      JSON,
    actor             TEXT,
    details           JSON
);
CREATE INDEX ix_oplog_ws_ts ON op_log(workspace_id, timestamp DESC);
```

### 3.2 Vector virtual tables (sqlite-vec)

```sql
-- FIX D1: Same database file — single transaction boundary
-- Embedding dimension fixed at 768 (matches sentence-transformers / local models)
CREATE VIRTUAL TABLE vec_claims    USING vec0(embedding float[768]);
CREATE VIRTUAL TABLE vec_sources   USING vec0(embedding float[768]);
CREATE VIRTUAL TABLE vec_entities  USING vec0(embedding float[768]);
CREATE VIRTUAL TABLE vec_questions USING vec0(embedding float[768]);

-- Because vec0 uses INTEGER rowid, we maintain mapping tables:
CREATE TABLE vec_claims_mapping    (rowid INTEGER PRIMARY KEY, entity_id TEXT NOT NULL UNIQUE);
CREATE TABLE vec_sources_mapping   (rowid INTEGER PRIMARY KEY, entity_id TEXT NOT NULL UNIQUE);
CREATE TABLE vec_entities_mapping  (rowid INTEGER PRIMARY KEY, entity_id TEXT NOT NULL UNIQUE);
CREATE TABLE vec_questions_mapping (rowid INTEGER PRIMARY KEY, entity_id TEXT NOT NULL UNIQUE);
```

**Why mapping tables:** `vec0` virtual tables require INTEGER rowid. Our string IDs (`clm_xxx`, `src_xxx`) are mapped to deterministic int rowids (hash → 63-bit int). Mapping tables preserve the link. All inserts go through `_insert_vector()` in store.py which writes to BOTH the vec table AND the mapping table atomically.

**11 tables total + 4 vector virtual + 4 mapping = 19 DB objects. One file.**

---

## 4. The 10 fixes from the design review — integrated

Every fix is applied inline in §3 and §5–§8 below. This section is the quick-reference index.

### 4.1 DEADLY (silent data corruption if missed)

| ID | Bug | Applied in |
|----|-----|-----------|
| **D1** | Dual-store consistency race (ChromaDB + SQLite) | §3.2 (sqlite-vec virtual tables in same file); §7 (transaction context) |
| **D2** | Entity canonicalization poisons mesh permanently | §3.1 entities.confidence + user_confirmed; §6 canonicalize pipeline; §11 CLI quarantine queue |
| **D3** | Snowball popularity trap (early claims starve late claims) | §7 lethal retrieval stage 6 (10% exploration reservation); §8 snowball formula (age-decayed bonus) |

### 4.2 SERIOUS (degrades quality silently)

| ID | Bug | Applied in |
|----|-----|-----------|
| **S4** | Edge weight saturation (all frequent edges hit 1.0) | §3.1 edges split columns: evidence_weight (immutable) + usage_boost (capped +0.2) |
| **S5** | Retrieval stage 2 entity expansion has no cosine filter | §7 stage 2 adds `cosine ≥ 0.5` filter before entity expansion |
| **S6** | NEARBY auto-expansion has no cost budget | §3.1 workspaces.nearby_expansion_budget_daily + §7 gap_classify budget enforcement |
| **S7** | Artifact directives not validated post-compose | §9 render_artifacts validates claim_ids + data types, strips invalid blocks |
| **S8** | Multi-turn coreference missing entirely | §7 stage 0 resolve_coreference step prepends last 3 Q/A pairs |

### 4.3 UNDERESTIMATED (cost/time were wrong)

| ID | Issue | Correction |
|----|-------|-----------|
| **U9** | claim_extract.py said 250 lines, realistic is 500+ | §13 build estimate updated to 500 lines |
| **U10** | Snapshot storage grows linearly (36 GB/year) | §10 zstd compression + incremental WAL replay |

---

## 5. Data flow: upload → mesh

```
Step 1  | file received           | → uploads/xyz.pdf
Step 2  | content hash            | sha256 → "a7f3..."
Step 3  | dedup check             | source_pages WHERE content_hash='a7f3...' → skip if exists
Step 4  | extract text            | docling / trafilatura → sources/upload_xyz.md
Step 5  | parse metadata          | title, authors, year, doi from PDF + first-page parse
Step 6  | insert source_page      | sig_authority=0.95 (upload), kind='upload'
Step 7  | chunk for extract       | 3K-char overlapping windows, 600 char overlap
Step 8  | LLM extract claims      | analyzer → N claims with direct_quote + char span
Step 9  | insert claims           | tier from signals, relevance vs workspace root_question
Step 10 | embed claims            | embed(claim.statement) → vec_claims (same db, same txn)
Step 11 | entity extraction       | LLM: entities mentioned in claim?
Step 12 | entity canonicalize     | FIX D2: fuzzy match → if ambiguous, insert with confidence<0.8 (quarantined)
Step 13 | link claim↔entity       | claim_entities rows
Step 14 | edge discovery          | §8: candidates via vec KNN, type via NLI, insert with evidence_weight
Step 15 | topic refresh           | mark affected topics dirty
Step 16 | log operation           | INSERT INTO op_log (for undo)
Step 17 | update workspace        | source_count++, claim_count++, edge_count+=
```

ALL OF THIS happens within ONE transaction per claim batch (or per source). If any step fails, the entire batch rolls back. No ghost claims, no orphan vectors.

---

## 6. Entity canonicalization (FIX D2 in detail)

```python
def canonicalize_entity(surface_form, workspace_id):
    # (1) Exact canonical match  — confidence 1.0
    existing = sql("SELECT * FROM entities WHERE workspace_id=? AND canonical_name=?",
                   workspace_id, surface_form)
    if existing:
        return existing, 1.0

    # (2) Alias match  — confidence 0.95
    existing = sql("""SELECT * FROM entities
                      WHERE workspace_id=?
                      AND json_each(aliases).value = ?""",
                   workspace_id, surface_form.lower())
    if existing:
        return existing, 0.95

    # (3) Embedding match (cosine ≥ 0.92)  — confidence = cosine
    emb = embed(surface_form)
    neighbors = vec_search("vec_entities", emb, k=3, workspace_id=workspace_id)
    for n in neighbors:
        if n.cosine > 0.92 and same_type(surface_form, n.entity_type):
            n.aliases.append(surface_form)
            return n, n.cosine

    # (4) LLM disambiguation zone (cosine 0.80–0.92)  — confidence 0.60–0.80
    if neighbors and 0.80 < neighbors[0].cosine <= 0.92:
        decision = llm_ask(f"Are '{surface_form}' and '{neighbors[0].canonical_name}' "
                           f"referring to the same {neighbors[0].entity_type}? "
                           f"Answer YES/NO/UNSURE.")
        if decision == "YES":
            neighbors[0].aliases.append(surface_form)
            return neighbors[0], 0.70     # still quarantined until user confirms
        # NO or UNSURE → fall through to (5)

    # (5) Insert new entity with LOW confidence — FIX D2 quarantine
    new_entity = insert_entity(
        canonical_name=surface_form,
        aliases=[surface_form.lower()],
        entity_type=classify(surface_form),
        confidence=0.5,                   # below 0.8 threshold — quarantined
        user_confirmed=False,
    )
    return new_entity, 0.5
```

**Quarantine semantics (FIX D2):**
- Retrieval stage 2 entity expansion ONLY uses entities with `confidence ≥ 0.8 OR user_confirmed = TRUE`.
- CLI `polaris entities review` lists quarantined entities, sorted by times_referenced DESC.
- User confirms → `confidence = 1.0`, `user_confirmed = TRUE`, entity becomes active in retrieval.
- User rejects → entity deleted, claim_entities links cascade removed.
- Quarantined entities are STORED but INVISIBLE to retrieval expansion. They still participate in edge discovery (entity overlap), just not in retrieval fan-out.

---

## 7. Lethal retrieval algorithm (with all fixes)

Six stages. Pseudocode:

```python
def lethal_retrieve(workspace_id, question_text, thread_history, K=40):
    # ═════ STAGE 0: coreference resolution (FIX S8) ═════
    # Prepend last 3 Q/A pairs and resolve pronouns before embedding
    context_prefix = render_thread_context(thread_history, last_n=3)
    resolved_question = llm_resolve_coreference(context_prefix, question_text)
    # e.g. "What about the cost?" → "What is the cost of the GAC filter from question 1?"

    q_emb = embed(resolved_question)

    # ═════ STAGE 1: semantic seed ═════
    seeds = vec_knn(
        "vec_claims",
        q_emb,
        k=80,
        where={"workspace_id": workspace_id,
               "tier": ["GOLD", "SILVER"],
               "flagged": False},
    )
    # seeds = [(claim_id, cosine), ...]

    # ═════ STAGE 2: entity expansion (FIX S5 + FIX D2) ═════
    q_entities = extract_entities_from_question(resolved_question)
    entity_claims = sql("""
        SELECT DISTINCT c.id FROM claims c
        JOIN claim_entities ce ON ce.claim_id = c.id
        JOIN entities e ON e.id = ce.entity_id
        WHERE c.workspace_id = ?
        AND c.flagged = 0
        AND (e.confidence >= 0.8 OR e.user_confirmed = 1)    -- FIX D2
        AND (e.canonical_name IN ? OR json_contains(e.aliases, ?))
    """, workspace_id, q_entities, q_entities)

    # FIX S5: entity-matched claims must ALSO pass a cosine threshold vs the question
    entity_claim_scores = []
    for clm_id in entity_claims:
        clm_emb = get_claim_embedding(clm_id)
        cos = cosine(q_emb, clm_emb)
        if cos >= 0.5:                                       # FIX S5
            entity_claim_scores.append((clm_id, cos))

    pool = merge_unique(seeds, entity_claim_scores)

    # ═════ STAGE 3: corroboration walk (1 hop, decay) ═════
    # FIX S4: use evidence_weight + usage_boost separately for weighting
    walked = dict(pool)
    for (claim_id, score) in list(pool.items()):
        neighbors = sql("""
            SELECT claim_b, evidence_weight, usage_boost
            FROM edges
            WHERE workspace_id = ?
            AND claim_a = ?
            AND kind = 'corroborates'
            AND evidence_weight > 0.6
            ORDER BY evidence_weight DESC
            LIMIT 5
        """, workspace_id, claim_id)
        for (nb_id, ev_w, use_b) in neighbors:
            # Composite weight, but evidence_weight dominates — usage is a small tiebreaker
            composite = ev_w + 0.3 * use_b
            walked[nb_id] = max(walked.get(nb_id, 0), score * composite * 0.7)

    # ═════ STAGE 4: contradiction surface (always include if exists) ═════
    contradictions = []
    for claim_id in list(walked.keys()):
        contras = sql("""SELECT claim_b, evidence_weight FROM edges
                         WHERE claim_a = ? AND kind = 'contradicts'""", claim_id)
        for (c_id, c_w) in contras:
            contradictions.append((c_id, 0.3))
    for (c_id, s) in contradictions:
        walked[c_id] = max(walked.get(c_id, 0), s)

    # ═════ STAGE 5: elaboration follow (detail for high-score claims) ═════
    top_half = sorted(walked.items(), key=lambda x: -x[1])[:20]
    for (claim_id, score) in top_half:
        elabs = sql("""SELECT claim_b, evidence_weight FROM edges
                       WHERE claim_a = ? AND kind = 'elaborates'
                       ORDER BY evidence_weight DESC LIMIT 3""", claim_id)
        for (e_id, e_w) in elabs:
            walked[e_id] = max(walked.get(e_id, 0), score * e_w * 0.5)

    # ═════ STAGE 6: lethal re-rank (with FIX D3 exploration budget) ═════
    lethal_scored = []
    for claim_id, base_score in walked.items():
        claim = fetch_claim(claim_id)
        source = fetch_source(claim.source_page_id)

        corroboration_count = count_corroborations(claim_id)
        has_contradiction   = any_contradictions(claim_id)

        # FIX D3: age-decayed times_used bonus (not pure log)
        days_since_first_use = (today - claim.extracted_at).days
        age_decay = exp(-days_since_first_use / 365)                  # half-life 1 year
        times_used_bonus = 1 + log(1 + claim.times_used) * 0.1 * age_decay

        lethal = (
            base_score
            * source.sig_authority
            * (1 + 0.3 * sqrt(corroboration_count))
            * (0.7 if has_contradiction else 1.0)
            * (1.3 if source.kind == "upload" else 1.0)               # upload anchor bonus
            * (1 + 0.5 * entity_match_fraction(claim_id, q_entities))
            * (0.7 + 0.3 * exp(-(today.year - (source.year or 2020)) / 10))
            * times_used_bonus                                        # FIX D3 age-decayed
        )
        lethal_scored.append((claim_id, lethal))

    main = sorted(lethal_scored, key=lambda x: -x[1])[:int(K * 0.9)]  # FIX D3: reserve 10%

    # FIX D3: 10% exploration budget — random high-tier claims never seen
    exploration = sql("""
        SELECT id FROM claims
        WHERE workspace_id = ?
        AND tier = 'GOLD'
        AND times_used = 0
        AND flagged = 0
        AND id NOT IN ?
        ORDER BY RANDOM()
        LIMIT ?
    """, workspace_id, [c for (c, _) in main], int(K * 0.1))
    exploration_scored = [(cid, 0.5) for cid in exploration]

    return main + exploration_scored  # total K claims
```

The lethal score combines 7 factors: semantic relevance (base_score), source authority, corroboration count, contradiction absence, upload anchor, entity match, recency, and age-decayed usage bonus. None of them dominates alone. No single failure mode can pin a bad claim at the top.

---

## 8. Snowball mechanisms (with FIX D3, FIX S4)

Four mechanisms, all bounded, all multiplicative.

```
M1. Usage reinforcement (FIX D3 age-decayed)
────────────────────────────────────────────
  on retrieval:
    claim.times_used += 1
    claim.last_used_at = now
  on re-rank:
    bonus = 1 + log(1 + claim.times_used) * 0.1 * exp(-age_days / 365)
  bounds:
    max bonus at times_used=100, age<30d  ≈ 1.46
    min bonus at age>2y                   ≈ 1.0 (decays to no-op)

M2. Corroboration reinforcement (FIX S4 two-column)
───────────────────────────────────────────────────
  on new claim insertion:
    for each existing c with cosine > 0.85 AND NLI(entailment):
      insert edge(new, c, 'corroborates', evidence_weight = cosine × nli_confidence)
  on successful answer that cited both a and c:
    edge.usage_boost = MIN(0.2, edge.usage_boost + 0.02)
  bounds:
    evidence_weight ∈ [0.7, 1.0]  (immutable, from cosine × NLI)
    usage_boost     ∈ [0.0, 0.2]  (mutable, capped)
    effective weight = evidence_weight + 0.3 × usage_boost  ∈ [0.7, 1.06]

M3. Contradiction flagging (unchanged)
──────────────────────────────────────
  on new claim insertion:
    for each existing c with cosine > 0.80 AND NLI(contradiction):
      insert edge(new, c, 'contradicts', evidence_weight = nli_confidence)
  effect on retrieval:
    both claims surfaced (always)
    re-rank penalty for claims with any contradiction = × 0.7
    user sees: "Two sources disagree on this point" with both direct quotes

M4. Upload gravity (FIX D3 bounded)
───────────────────────────────────
  source_pages.sig_authority = 0.95 for kind='upload' (vs 0.30–0.85 web)
  effect on retrieval:
    lethal × 1.3 when source is upload
  edge gravity:
    corroborating edges where one side is an upload claim get +0.05 usage_boost
    (bounded by the +0.2 cap on usage_boost)
```

Key property: snowball is bounded. `times_used` bonus is age-decayed (half-life 1 year), `corroboration_count` enters as sqrt, `usage_boost` is capped at 0.2. No runaway feedback, no popularity cascades. And the 10% exploration reservation in lethal re-rank guarantees late-arriving high-quality claims get a fair shot.

---

## 9. Artifact generation pipeline (with FIX S7 validation)

Compose emits markdown with inline directive blocks. Post-processor renders each block AFTER validating it.

```python
ARTIFACT_PATTERN = re.compile(
    r"\[(TABLE|CHART|FLOW|DECK|FLASHCARDS):([^\]]+)\]\{([^}]*)\}",
    re.DOTALL
)

def render_artifacts(answer_text, claims_by_id, answer_id):
    artifacts = []

    def replace(match):
        kind = match.group(1)
        spec = match.group(2)
        payload = parse_payload(match.group(3))  # "claim_ids=a,b,c" → {"claim_ids": [...]}

        # ═══ FIX S7: Validation BEFORE rendering ═══
        cids = payload.get("claim_ids", [])
        missing = [c for c in cids if c not in claims_by_id]
        if missing:
            logger.warning(f"Stripped invalid [{kind}] block: missing claims {missing}")
            return f"_(artifact stripped: {kind})_"

        if kind == "TABLE":
            # Verify each claim contains the data type the table column references
            columns = spec.split(",")
            valid_rows = []
            for cid in cids:
                row = extract_row_data(claims_by_id[cid], columns)
                if row:   # row is None if claim doesn't contain the data
                    valid_rows.append((cid, row))
            if len(valid_rows) < 2:  # need at least 2 rows for a table
                logger.warning(f"Stripped [TABLE]: only {len(valid_rows)} valid rows")
                return f"_(table stripped: insufficient data)_"
            md_table = render_table_md(columns, valid_rows, claims_by_id)
            return md_table  # inline markdown

        if kind == "CHART":
            # Verify numeric data exists in claims
            data = extract_chart_data(payload, claims_by_id)
            if not data or len(data.values) < 2:
                return f"_(chart stripped: insufficient numeric data)_"
            fig = render_chart(spec, data)
            path = save_png(f"artifacts/{answer_id}/chart_{len(artifacts)}.png", fig)
            artifacts.append(path)
            return f"![{spec}]({path})"

        if kind == "FLOW":
            mermaid = render_flow_mermaid(payload, claims_by_id)
            return f"```mermaid\n{mermaid}\n```" if mermaid else "_(flow stripped)_"

        if kind == "DECK":
            pptx_path = render_deck(answer_text, list(claims_by_id.values()), answer_id)
            artifacts.append(pptx_path)
            return f"[📎 Slide deck]({pptx_path})"

        if kind == "FLASHCARDS":
            cards_path = render_flashcards(list(claims_by_id.values()), answer_id)
            artifacts.append(cards_path)
            return f"[📎 Flashcards]({cards_path})"

        return f"_(unknown artifact: {kind})_"

    final_text = ARTIFACT_PATTERN.sub(replace, answer_text)
    return final_text, artifacts
```

**Validation invariants (FIX S7):**
- Every `claim_id` referenced in a block must exist in the retrieved claim set.
- Every column referenced in a TABLE block must be extractable from at least 2 claim `direct_quote` fields.
- Every CHART block must have at least 2 numeric data points to plot.
- Failed validation → block stripped, inline stub message, warning logged. Does NOT fail the whole compose.

---

## 10. Failure modes and their handlers

| Failure | Detection | Handler |
|---|---|---|
| PDF corrupt / unparsable | docling exception | Mark source_pages.status='failed'. User notified. No cascade. |
| LLM extraction returns 0 claims | len(claims)==0 | Retry with smaller chunks. If still 0, flag source low-yield. |
| Embedding service down | HTTP timeout | **Transaction rolls back** — claim NOT inserted. Retry job queued. |
| Edge discovery takes too long | job > 10 min | Checkpoint, resume in background. Retrieval works with partial edges. |
| NLI service unavailable | flan-t5 import fails | Fall back to cosine-only edges (no contradictions). **User warned**. |
| Retrieval returns 0 claims | gap = ORTHOGONAL | Prompt user for workspace decision. |
| Compose LLM returns empty | len(text)==0 | Retry 3×. On final fail, return retrieved claims as structured output. |
| Compose hits token limit | OpenRouter 400 | Reduce context, retry. Split if still fails. |
| Artifact render fails | matplotlib/pptx exception | **FIX S7**: drop artifact, log, keep text. Validation prevents most cases. |
| Snapshot restore corrupts DB | SQLite integrity check fails | Roll forward to next snapshot, alert user. |
| Mesh.db file > 1GB | size monitor | Offer compaction (VACUUM). Archive old snapshots. **U10 zstd**. |
| Duplicate ingest | content_hash matches | Skip insert. Re-embed only if workspace changed. |
| Entity quarantine queue > 100 | periodic check | Alert user: "100 entities need review — retrieval quality degrading". |
| NEARBY expansion budget hit | counter check | **FIX S6**: reject further auto-expansion today. Log, surface to user. |
| User flags > 20% of source's claims | periodic review | Alert: "source_xyz may be unreliable — consider removing." |

Every failure has a named handler. Nothing panics silently. (LAW II.)

---

## 11. User interaction layer (CLI)

```
# workspace management
polaris workspace create "name" --seed "initial question"
polaris workspace list
polaris workspace switch <id>

# ingest
polaris upload <file> [--workspace <id>]
polaris search "topic"          # independent of a question

# Q&A
polaris ask "question"          # retrieve → compose → answer + artifacts
polaris thread list
polaris thread show <id>

# entity review (FIX D2)
polaris entities review         # show quarantined entities sorted by times_referenced
polaris entities confirm <id>
polaris entities reject <id>
polaris entities merge <id1> <id2>

# mesh inspection
polaris mesh stats              # source/claim/edge counts, top entities
polaris mesh drill <claim_id>   # provenance, neighbors, usage history
polaris mesh flag <claim_id> --reason "wrong number"

# versioning (U10)
polaris snapshot create
polaris snapshot list
polaris snapshot restore <timestamp>

# export
polaris export report [--format md|pdf|docx]
polaris export deck             # python-pptx
polaris export flashcards       # CSV / Anki
```

---

## 12. Migration from current POLARIS

The current `wiki_builder.py` + `wiki_composer.py` path writes per-run `wiki/{vector_id}/` directories. Migration is incremental and gated.

| Phase | Change | Gated? | Breaks? |
|---|---|---|---|
| M1 | Add `workspace_id` parameter to existing code paths. Each run = one workspace. | No | No |
| M2 | Create SQLite schema alongside markdown. Existing code also writes to mesh.db. | No | No |
| M3 | Add edges table + discovery pass. Runs post-build, stores in SQLite. | No | No |
| M4 | Add entity extraction + canonicalization (FIX D2 quarantine). | No | No |
| M5 | Add questions/answers tables + `polaris ask` command. | No | No |
| M6 | **Replace retrieval in compose** — current embedding retrieval → lethal algorithm. | `PG_WIKI_LETHAL=1` | Gated |
| M7 | Add artifact renderers with FIX S7 validation. | `PG_WIKI_ARTIFACTS=1` | Gated |
| M8 | Add snapshot/undo, multi-workspace, API server. | No | No (additive) |

No big-bang migration. Existing `wiki_composer.py` keeps working throughout. Each phase ships independently.

---

## 13. Component inventory (post-review estimates)

Post-FIX U9 (realistic line counts, not initial optimism):

```
src/polaris_graph/wiki/
├── mesh/
│   ├── __init__.py
│   ├── schema.py             # DDL + create_schema()                  ~250 lines
│   ├── store.py              # CRUD + vector search                   ~500 lines
│   ├── ingest.py             # upload/fetch → source_pages            ~250 lines
│   ├── claim_extract.py      # LLM extraction (adapted)               ~500 lines  (U9 correction)
│   ├── entity.py             # canonicalize with confidence (D2)      ~300 lines
│   ├── edge_discovery.py     # corroborate/contradict/elaborate (S4)  ~350 lines
│   ├── topic_refresh.py      # emergent clustering                    ~200 lines
│   └── snowball.py           # bounded feedback formulas (D3/S4)      ~120 lines
├── retrieve/
│   ├── lethal.py             # 6-stage with D3 + S5 + S8              ~400 lines
│   └── gap_classify.py       # IN_SCOPE/NEARBY/ADJACENT/ORTHOGONAL    ~150 lines
├── compose/
│   ├── composer.py           # adapted from wiki_composer.py          (already built)
│   ├── artifact_directives.py# prompt fragments                       ~120 lines
│   └── renderers/
│       ├── table.py          # with S7 validation                     ~120 lines
│       ├── chart.py          # matplotlib                             ~180 lines
│       ├── flow.py           # mermaid                                ~80 lines
│       ├── deck.py           # python-pptx                            ~220 lines
│       └── flashcards.py                                              ~100 lines
├── workspace/
│   ├── create.py                                                      ~100 lines
│   ├── switch.py                                                      ~50 lines
│   ├── snapshot.py           # zstd compression (U10)                 ~180 lines
│   └── migrate.py            # workspace merge                        ~150 lines
├── qa/
│   ├── ask.py                # end-to-end Q → A                       ~250 lines
│   ├── thread.py             # multi-turn context (S8)                ~120 lines
│   └── feedback.py           # ratings, flags, entity confirm         ~120 lines
└── server/
    ├── cli.py                # polaris <cmd>                          ~350 lines
    └── api.py                # REST endpoints                         ~400 lines

tests/unit/                                                             ~500 lines
tests/integration/                                                     ~600 lines

TOTAL: ~6,360 lines across 30 files
```

Realistic effort with integration testing: **~9 weeks full-time**.

---

## 14. Cost reality (advisor numbers)

### Per-month, 1000 sources, 500 questions (modest power user)

| Component | Calculation | Monthly |
|---|---|---|
| Claim extraction | 30K claims ÷ 10/call = 3K calls @ 3.5K tok | ~$8 |
| Entity disambiguation | ~4K LLM calls | ~$4 |
| Compose (500 × 5 sections) | 2,500 calls @ 50K tok in | ~$45 |
| Gap expansion (150 rounds) | Serper free tier | $0 |
| NLI edge discovery (local flan-t5) | 35 GPU-hours cloud | ~$35 |
| Embedding (local ST) | 5 GPU-hours | ~$5 |
| **Via OpenRouter API (GLM 5.1)** | | **~$100-150/mo** |
| **Self-hosted GLM 5.1 full (2×A100)** | $3-5/hr × 8hr/day | **~$500-750/mo** |

**Conclusion:** OpenRouter API wins until ~2,000 questions/month. Self-hosting is an ops burden without cost advantage below that scale.

---

## 15. Build order

| Unit | Files | Lines | Depends on |
|---|---|---|---|
| **1** | `mesh/__init__.py`, `mesh/schema.py`, `mesh/store.py` + tests | 750 + 500 tests | — |
| 2 | `mesh/ingest.py`, `mesh/claim_extract.py` + tests | 750 + 300 | 1 |
| 3 | `mesh/entity.py` + tests | 300 + 200 | 1, 2 |
| 4 | `mesh/edge_discovery.py`, `mesh/snowball.py` + tests | 470 + 300 | 1–3 |
| 5 | `retrieve/lethal.py`, `retrieve/gap_classify.py` + tests | 550 + 400 | 1–4 |
| 6 | `compose/` adaptation + `renderers/` + tests | 820 + 300 | 1–5 |
| 7 | `qa/` + tests | 490 + 300 | 5–6 |
| 8 | `workspace/` + `server/cli.py` + tests | 830 + 200 | all |
| 9 | `server/api.py` + tests | 400 + 300 | all |
| 10 | Integration + regression tests | 600 | all |

**Unit 1 is starting now.**

---

## 16. Environment + dependencies

Required Python packages (additions to requirements.txt):
```
sqlite-vec>=0.1.6     # single-db vector search (FIX D1)
zstandard>=0.22       # snapshot compression (FIX U10)
python-pptx>=0.6.23   # slide deck artifact (§9)
matplotlib>=3.8       # chart artifact (§9)
```

Already in requirements:
- numpy, sentence-transformers, trafilatura, docling
- openrouter client, sqlite3 (stdlib)

Env vars (new):
```
PG_WIKI_MESH_ROOT=wiki/workspaces
PG_WIKI_LETHAL=0                  # Phase M6 gate
PG_WIKI_ARTIFACTS=0                # Phase M7 gate
PG_WIKI_ENTITY_QUARANTINE_THRESHOLD=0.8
PG_WIKI_NEARBY_BUDGET_DAILY=50
```

---

## 17. Testing strategy

**Unit tests** (per unit, co-located in tests/unit/)
- test_schema.py: DDL runs, version check, all tables present
- test_store.py: CRUD, transactions, vector search, snowball increments
- test_entity.py: canonicalization paths, confidence gating
- test_edge_discovery.py: edge types, S4 split columns
- test_lethal.py: 6-stage retrieval, D3 exploration, S5 cosine filter
- test_snowball.py: bounds, age decay, no saturation
- test_artifacts.py: S7 validation strips invalid blocks

**Integration tests** (tests/integration/)
- test_upload_to_retrieve.py: full pipeline upload → claim → edge → retrieve
- test_q_to_a.py: question → compose → answer with artifacts
- test_multi_turn.py: 3-question thread with coreference (S8)
- test_snapshot_roundtrip.py: snapshot → destructive op → restore → identical

**Regression tests** (tests/regression/)
- test_geval_baseline.py: PFAS answer G-Eval ≥ 75 (from 4-domain validation)
- test_latency.py: query on 10K-claim mesh < 3s
- test_scale.py: build 50K-claim mesh, measure edge discovery time

**Property tests**
- test_snowball_bounds.py: usage_bonus never > 2.0, usage_boost never > 0.2
- test_citation_integrity.py: every [N] → real claim
- test_no_orphan_vectors.py: every claim has vector, every vector has claim

---

## 18. Why this beats everyone (sharpened)

| Competitor | Weakness | Mesh advantage |
|---|---|---|
| Gemini Deep Research | No persistence — dies after session | Mesh persists. Every session compounds. |
| Claude Opus | Session-scoped, no snowball | times_used + corroboration weight make repeated answers better |
| Perplexity | Short answers, pre-indexed | Agentic expansion per question, long-form compose with validated artifacts |
| NotebookLM | Bounded to uploaded docs only | Fetches + anchors uploads, expands when gaps detected |
| Hermes Wiki | Prompt-only, no enforcement | Code-level gates: authority, contradiction, provenance, retraction sweep |
| Human experts | Forget, bias, can't read 500 papers/day | No forgetting, no bias, reads everything, surfaces contradictions honestly |

The combination that's lethal: **persistent graph memory + agentic expansion + user-anchored authority + contradiction surfacing + bounded snowball**. Each competitor has 1-2 of these. None have all five.

---

## 19. Open questions

- Embedding dim: fixed at 768 for sentence-transformers. GLM 5.1 embeddings may be 1024 or 4096. If we switch, `vec_*` tables need `float[1024]` and a re-embed pass. Deferred until embedding model is chosen.
- Citation edge kind `cites` is in the schema but not yet used (reserved for explicit DOI citation chains from S2).
- Topic refresh cadence: mark dirty on insert, re-cluster nightly? Or on read? Deferred to Unit 8.
- Multi-user: workspaces.owner is a column but auth is not in scope for v1. Single-user local v1 → multi-user v2.

---

## 20. What Unit 1 delivers (starting now)

- `src/polaris_graph/wiki/mesh/__init__.py`
- `src/polaris_graph/wiki/mesh/schema.py` — DDL for all 15 tables (11 core + 4 vec mappings) + 4 vec virtual tables
- `src/polaris_graph/wiki/mesh/store.py` — MeshStore class with transaction context, CRUD for workspaces/sources/claims/edges/entities, vector insert + KNN search, all fixes inline
- `tests/unit/test_mesh_store.py` — 15+ tests covering schema creation, CRUD, transactions, snowball, entity confidence gating, vector search

After Unit 1 the mesh database file exists, can be opened, supports atomic writes across claims + vectors, and has no known bugs from the advisor review. It does NOT yet ingest files, extract claims, discover edges, or retrieve. Those are Units 2-5.

---

## Changelog

- **2026-04-10** — Initial design (v1), adopted Option A from advisor review. All 10 fixes integrated inline. Unit 1 build starting.
