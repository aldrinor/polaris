"""
Mesh entity canonicalization — the L3 write path (FIX D2).

Given a surface form like "PFOS", "C8", or "perfluorooctane sulfonate",
figures out whether it refers to an existing entity in the workspace
(and if so, merges it as an alias) or creates a new entity. New
entities below the confidence threshold are QUARANTINED — stored but
excluded from retrieval stage 2 entity expansion until the user
confirms them.

Five-step pipeline (design doc §6):

  1. Exact canonical_name match → confidence 1.0
  2. Alias match (case-insensitive)  → confidence 0.95
  3. Embedding cosine ≥ 0.92         → confidence = cosine (merge)
  4. Embedding cosine 0.80 – 0.92    → LLM disambiguation call:
       - YES same → confidence 0.70 (still quarantined; user review)
       - NO / UNSURE / no disambig client → fall through to step 5
  5. Insert new entity with confidence 0.5 and user_confirmed=False
     (QUARANTINED — visible to the user-review CLI, invisible to
     retrieval expansion until confirmed).

Design choice (CP-A lock, variant c2):

  - Surface forms come from `AtomicFact.entities`, a list populated by
    the mesh-side extraction prompt. If an LLM run produces no entity
    list (backward-compat path), that claim simply has no entities to
    canonicalize — safe no-op, no retrieval penalty.
  - `classify_entity_type` is a simple heuristic — the production
    pipeline's 5-signal scorer is deferred until we have corroboration
    data from Unit 4. For v1, we tag by pattern: acronym → compound,
    percent/metric → metric, ALL CAPS → organization, title-cased
    phrase → organization, else concept.
  - The LLM disambiguation step is OPTIONAL. Tests that don't mock an
    LLM client just skip step 4 — any entity in the 0.80-0.92 zone
    falls through to step 5 (new quarantined insert). This means the
    pipeline works in test environments without network or LLM access.

Key integration points in store.py (already present from Unit 1):
  - `insert_entity(workspace_id, canonical_name, entity_type, aliases,
    confidence, user_confirmed, embedding)` — handles the write
  - `link_claim_entity(claim_id, entity_id)` — idempotent linking
  - `get_quarantined_entities(workspace_id)` — for the CLI review queue
  - `confirm_entity(entity_id)` — promotes quarantined → confirmed
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel, Field

from .store import EMBEDDING_DIM, MeshStore, MeshStoreError

logger = logging.getLogger(__name__)


# ───── thresholds (see design doc §6) ─────

# Above this cosine, we merge without asking. Borrowed from the design
# doc's step 3 threshold.
COSINE_MERGE_THRESHOLD = 0.92

# Between DISAMBIG_LO and MERGE_THRESHOLD, we ask the LLM. Below
# DISAMBIG_LO, we assume they're different entities.
COSINE_DISAMBIG_LO = 0.80

# New entities default confidence. Below the quarantine gate so they
# don't leak into retrieval expansion until the user confirms.
NEW_ENTITY_CONFIDENCE = 0.5

# Confidence assigned after an affirmative LLM disambig in the
# 0.80-0.92 zone. Still below the 0.8 quarantine gate — the disambig
# is weaker evidence than a high-cosine merge, so we keep it in the
# quarantine queue for user review.
DISAMBIG_YES_CONFIDENCE = 0.70

# The quarantine gate as enforced in store.get_quarantined_entities.
# Mirrors FIX D2's 0.8 threshold — entities with confidence below this
# AND `user_confirmed=False` are excluded from retrieval expansion.
QUARANTINE_GATE = 0.8


# ───── entity type classifier (v1 heuristic) ─────

_ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")                # "PFOS", "GAC", "EPA"
_ALL_CAPS_MULTI_RE = re.compile(r"^[A-Z]{2,}(?:\s+[A-Z]{2,})+$")  # "EPA ORD"
_CAPITALIZED_PHRASE_RE = re.compile(
    r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$"
)                                                                 # "Water Research"
_METRIC_RE = re.compile(
    r"(?:\d+\s*%|95\s*%\s*CI|p\s*[<>=]|n\s*=|mg/L|ng/L|μg/L|ppt|ppb|ppm)",
    re.IGNORECASE,
)
_PERSON_NAME_RE = re.compile(
    # Persons need an explicit disambiguating signal — otherwise 3-token
    # organizations like "Water Research Foundation" match a pure
    # title-cased pattern and get mis-classified. Accept either:
    #   (a) an honorific title prefix: "Dr./Prof./Mr./Mrs./Ms./Sr./Jr."
    #   (b) a middle-initial token with explicit dot: "John A. Smith"
    # Everything else falls through to the organization/concept branches.
    r"^(?:Dr|Prof|Mr|Mrs|Ms|Sr|Jr)\.\s+[A-Z][a-z]+(?:\s+[A-Z]\.?)*\s+[A-Z][a-z]+$"
    r"|"
    r"^[A-Z][a-z]+\s+[A-Z]\.\s+[A-Z][a-z]+$"
)

# Known method/technique names that look like compound acronyms but
# aren't. Keep this list small and domain-neutral — anything more
# specific belongs in a workspace-specific config.
_KNOWN_METHODS = frozenset({
    "GAC", "PAC", "RO", "NF", "UF", "MF",    # filtration
    "IX", "AIX", "CIX",                        # ion exchange
    "HPLC", "LC-MS", "GC-MS", "ICP-MS",        # analytical
    "ELISA", "PCR", "qPCR",                    # biochemistry
})

# FIX-C3: Full-name expansions of method acronyms. Without this,
# "nanofiltration" (concept) and "NF" (method) become separate entities
# because the canonicalization pipeline filters by type before merging.
_KNOWN_METHOD_PHRASES = frozenset({
    "granular activated carbon", "powdered activated carbon",
    "reverse osmosis", "nanofiltration", "ultrafiltration",
    "microfiltration", "ion exchange", "anion exchange",
    "ion exchange resins", "anion exchange resins",
    "adsorption",
})

# FIX-M1: Known non-entity abbreviations/units that LLMs emit as
# "entities" but are domain vocabulary, not discrete entities.
_KNOWN_UNITS = frozenset({
    "BAT", "MCL", "MCLs", "psi", "kWh", "Daltons",
})

# FIX-C4: Antonym pairs. If two surface forms differ ONLY by an
# antonym swap, they are opposite concepts and must NOT be merged.
_ANTONYM_PAIRS = frozenset({
    frozenset(("long", "short")),
    frozenset(("high", "low")),
    frozenset(("positive", "negative")),
    frozenset(("increase", "decrease")),
    frozenset(("above", "below")),
    frozenset(("greater", "lesser")),
})

# Known organization acronyms that look like compounds. Preflight
# showed "EPA" classified as compound — it's an organization.
_KNOWN_ORGS = frozenset({
    "EPA", "FDA", "WHO", "CDC", "NIH", "OSHA",   # US/intl agencies
    "USGS", "NOAA", "DOE", "DOD", "NASA",        # US agencies
    "EU", "UN", "NATO", "OECD", "IAEA",          # international
    "NSF", "ASTM", "ISO", "ANSI", "IEEE",        # standards bodies
    "AWWA", "WEF", "ASCE",                       # water/engineering
})

# Bare numeric patterns that LLMs emit as "entities" but are really
# just measurements — "95%", "40-60%", "$0.15". Not useful as
# canonical entities.
_BARE_NUMERIC_RE = re.compile(
    r"^[\d$.,\-+/%<>=~\s]+$"
)

# FIX-JUNK: Measurement fragments that start with a number and contain
# units or time words. These are quantitative data points, not entities.
# Catches: "3-5 kWh", "6-month pilot study", "8 water utilities",
# "$0.20-0.35 per 1000 gallons", "2-3 times", "1000 gallons".
_MEASUREMENT_FRAGMENT_RE = re.compile(
    r"^[$]?\d[\d.,\-/\s]*"         # starts with optional $ + digits
    r"(?:kWh|psi|mg|ng|ppm|ppb|ppt|Daltons|%|gallons?|times|x\b"
    r"|months?|years?|days?|hours?|minutes?"
    r"|water\s+utilities|pilot\s+stud"
    r"|per\s+)"                     # "per 1000 gallons"
    , re.IGNORECASE,
)

# FIX-M2: Known regulation/standard names that look like organizations
# because they are title-cased multi-word phrases.
_KNOWN_REGULATIONS = frozenset({
    "maximum contaminant levels", "maximum contaminant level",
    "safe drinking water act", "clean water act",
    "national primary drinking water regulations",
})


def classify_entity_type(surface_form: str) -> str:
    """
    Heuristic entity type classifier for v1.

    Returns one of: "compound" | "method" | "organization" | "person"
    | "metric" | "concept".

    Not meant to be perfect — the user can always correct an
    entity_type in the quarantine review queue. We only need this
    classification accurate enough that the 0.92-cosine merge doesn't
    merge a compound with an organization that happens to share a
    name vector.
    """
    surface = surface_form.strip()
    if not surface:
        return "concept"

    # Bare numeric strings ("95%", "40-60%", "$0.15") — reject as metric
    if _BARE_NUMERIC_RE.match(surface):
        return "metric"

    # FIX-JUNK: Measurement fragments ("3-5 kWh", "6-month pilot study")
    if _MEASUREMENT_FRAGMENT_RE.match(surface):
        return "metric"

    # Metric patterns (numeric + unit) — check early
    if _METRIC_RE.search(surface):
        return "metric"

    # FIX-M1: Known non-entity abbreviations/units
    if surface in _KNOWN_UNITS:
        return "metric"

    # FIX-M2: Known regulations classified before capitalized-phrase check
    if surface.lower() in _KNOWN_REGULATIONS:
        return "concept"

    # Known methods (explicit list) before acronym classification
    if surface in _KNOWN_METHODS:
        return "method"

    # FIX-C3: Known method phrases — use substring match so
    # "adsorption-based methods" matches via "adsorption" and
    # "ion exchange resin beads" matches via "ion exchange".
    surface_lower = surface.lower()
    if any(phrase in surface_lower for phrase in _KNOWN_METHOD_PHRASES):
        return "method"

    # Known organizations before compound classification
    if surface in _KNOWN_ORGS:
        return "organization"

    # 2-8 char all-caps (or caps + digits) → likely compound.
    # FIX-M3: also catch mixed-case PFAS names like "PFHxS" (caps
    # with lowercase interior — not pure _ACRONYM_RE match).
    if _ACRONYM_RE.match(surface):
        return "compound"
    if re.match(r"^PF[A-Za-z]{1,6}$", surface):
        return "compound"

    # Multi-word all caps → probably an organization
    if _ALL_CAPS_MULTI_RE.match(surface):
        return "organization"

    # Person name pattern
    if _PERSON_NAME_RE.match(surface):
        return "person"

    # Capitalized phrase → organization as default (e.g. "Water Research")
    # Exclude known non-org phrases that happen to be title-cased
    if _CAPITALIZED_PHRASE_RE.match(surface):
        return "organization"

    return "concept"


# ───── LLM disambig client protocol ─────

class DisambigResponse(BaseModel):
    """Minimal schema for the LLM disambiguation call."""
    same_entity: bool = Field(description="Are these two terms referring to the same entity?")
    reasoning: str = Field(default="", description="Brief justification")


class DisambigClient(Protocol):
    """
    Optional protocol for the LLM disambiguator. The real
    `OpenRouterClient` implements `generate_structured` which we
    wrap in `llm_disambiguate`. Tests can pass any object that has
    `async def generate_structured(prompt, schema, system, ...)`.
    """

    async def generate_structured(
        self,
        *,
        prompt: str,
        schema: Any,
        system: str,
        max_tokens: int,
        timeout: int,
        reasoning_enabled: bool,
    ) -> Any: ...


async def llm_disambiguate(
    client: DisambigClient,
    *,
    surface_form: str,
    candidate_canonical: str,
    entity_type: str,
) -> bool:
    """
    Ask the LLM whether two terms refer to the same entity.

    Returns True only if the LLM explicitly says YES. Any error,
    ambiguous answer, or missing response → False, so the caller
    falls through to the safe "new quarantined entity" path.
    """
    prompt = (
        f"Two terms are being compared for entity equality:\n"
        f"  Term A: {surface_form!r}\n"
        f"  Term B: {candidate_canonical!r}\n"
        f"  Entity type: {entity_type}\n\n"
        f"Do these terms refer to the SAME entity? Consider synonyms, "
        f"acronyms, and alternative names. Answer strictly YES or NO."
    )
    system = (
        "You are a precise disambiguator. You answer YES only if you "
        "are certain the two terms refer to the same real-world entity. "
        "Otherwise answer NO. When in doubt, answer NO."
    )
    try:
        response = await client.generate_structured(
            prompt=prompt,
            schema=DisambigResponse,
            system=system,
            max_tokens=256,
            timeout=30,
            reasoning_enabled=False,
        )
        return bool(response.same_entity)
    except Exception as exc:
        logger.warning(
            "llm_disambiguate failed for %r vs %r: %s — defaulting to NO",
            surface_form, candidate_canonical, exc,
        )
        return False


# ───── antonym guard (FIX-C4) ─────

def _is_antonym_pair(surface_a: str, surface_b: str) -> bool:
    """
    Check if two surface forms differ only by an antonym swap.

    Tokenize both, find the differing words, check if ALL differences
    are antonym pairs. E.g., "long-chain PFAS" vs "short-chain PFAS"
    differs only on {long, short} which is in _ANTONYM_PAIRS.
    """
    # Normalize: lowercase, split on whitespace and hyphens
    tokens_a = set(re.split(r"[\s\-]+", surface_a.lower()))
    tokens_b = set(re.split(r"[\s\-]+", surface_b.lower()))
    only_a = tokens_a - tokens_b
    only_b = tokens_b - tokens_a
    if not only_a or not only_b or len(only_a) != len(only_b):
        return False
    # Check if every differing word pair is an antonym
    for word_a in only_a:
        found_match = False
        for word_b in only_b:
            if frozenset((word_a, word_b)) in _ANTONYM_PAIRS:
                found_match = True
                break
        if not found_match:
            return False
    return True


# ───── canonicalization core ─────

async def canonicalize_entity(
    store: MeshStore,
    *,
    workspace_id: str,
    surface_form: str,
    embedding: np.ndarray | None = None,
    disambig_client: DisambigClient | None = None,
    entity_type: str | None = None,
) -> tuple[str, float, bool]:
    """
    Run the 5-step canonicalization pipeline for a single surface form.

    Returns `(entity_id, confidence, is_new)`:
      - `entity_id`     the canonical entity this surface form resolved to
      - `confidence`    the match confidence (1.0 exact ... 0.5 quarantined new)
      - `is_new`        True if a new entity row was inserted,
                        False if we merged into an existing entity

    Raises MeshStoreError on:
      - empty surface_form (upstream filter should already catch this)
      - unknown workspace_id

    The caller is responsible for calling `store.link_claim_entity`
    afterwards. This function ONLY manages the entity table.
    """
    surface = surface_form.strip()
    if not surface:
        raise MeshStoreError("canonicalize_entity requires a non-empty surface_form")

    if store.get_workspace(workspace_id) is None:
        raise MeshStoreError(f"Workspace not found: {workspace_id}")

    resolved_type = entity_type or classify_entity_type(surface)

    # ── Step 1: exact canonical_name match ──
    existing = _find_by_canonical(store, workspace_id, surface)
    if existing is not None:
        logger.debug("canonicalize: exact match %r → %s", surface, existing["id"])
        return existing["id"], 1.0, False

    # ── Step 2: alias match (case-insensitive across existing aliases) ──
    alias_hit = _find_by_alias(store, workspace_id, surface)
    if alias_hit is not None:
        logger.debug("canonicalize: alias match %r → %s", surface, alias_hit["id"])
        return alias_hit["id"], 0.95, False

    # ── Step 3+4: need an embedding ──
    if embedding is None:
        embedding = _embed_surface_form(surface)

    neighbours = _vec_neighbours(
        store,
        workspace_id=workspace_id,
        query_embedding=embedding,
        k=5,
    )

    # Filter neighbours to entities of the same type (avoid PFOS-compound
    # merging with a PFOS-organization that happens to cosine-near)
    same_type = [
        (ent, cos)
        for (ent, cos) in neighbours
        if ent["entity_type"] == resolved_type
    ]

    # ── Step 3: high-cosine merge ──
    if same_type and same_type[0][1] >= COSINE_MERGE_THRESHOLD:
        target_ent, cos = same_type[0]
        # FIX-C4: block merge when surface forms differ only by an
        # antonym ("long-chain PFAS" vs "short-chain PFAS" have cos>0.92
        # but are opposite concepts).
        if not _is_antonym_pair(surface, target_ent["canonical_name"]):
            _add_alias(store, target_ent, surface)
            logger.info(
                "canonicalize: cosine merge %r → %s (cos=%.3f)",
                surface, target_ent["id"], cos,
            )
            return target_ent["id"], float(cos), False
        else:
            logger.info(
                "canonicalize: blocked antonym merge %r vs %r (cos=%.3f)",
                surface, target_ent["canonical_name"], cos,
            )

    # ── Step 4: disambig zone 0.80–0.92 ──
    if same_type and COSINE_DISAMBIG_LO <= same_type[0][1] < COSINE_MERGE_THRESHOLD:
        target_ent, cos = same_type[0]
        if disambig_client is not None:
            try:
                same = await llm_disambiguate(
                    disambig_client,
                    surface_form=surface,
                    candidate_canonical=target_ent["canonical_name"],
                    entity_type=resolved_type,
                )
            except Exception as exc:
                logger.warning(
                    "canonicalize: disambig raised unexpectedly: %s — "
                    "treating as NO", exc,
                )
                same = False
            if same:
                _add_alias(store, target_ent, surface)
                # Promote confidence to DISAMBIG_YES (0.70, still quarantined)
                _update_entity_confidence(
                    store,
                    entity_id=target_ent["id"],
                    new_confidence=max(
                        float(target_ent["confidence"]),
                        DISAMBIG_YES_CONFIDENCE,
                    ),
                )
                logger.info(
                    "canonicalize: disambig YES %r → %s (cos=%.3f)",
                    surface, target_ent["id"], cos,
                )
                return target_ent["id"], DISAMBIG_YES_CONFIDENCE, False
        # No disambig_client or disambig NO → fall through to step 5

    # ── Step 5: insert new entity, quarantined ──
    new_id = store.insert_entity(
        workspace_id=workspace_id,
        canonical_name=surface,
        entity_type=resolved_type,
        aliases=[surface.lower()],
        confidence=NEW_ENTITY_CONFIDENCE,
        user_confirmed=False,
        embedding=embedding,
    )
    logger.info(
        "canonicalize: new quarantined %r → %s (type=%s, conf=%.2f)",
        surface, new_id, resolved_type, NEW_ENTITY_CONFIDENCE,
    )
    return new_id, NEW_ENTITY_CONFIDENCE, True


async def canonicalize_entities_for_claim(
    store: MeshStore,
    *,
    workspace_id: str,
    claim_id: str,
    surface_forms: list[str],
    disambig_client: DisambigClient | None = None,
    embeddings: dict[str, np.ndarray] | None = None,
) -> list[str]:
    """
    Canonicalize every surface form mentioned in a claim and link the
    claim to each resolved entity.

    Returns the list of entity_ids the claim is linked to.

    If `embeddings` is provided, it should map `surface_form -> np.ndarray`
    for pre-computed embeddings (avoids per-call embed_texts() overhead
    when a batch of claims shares many surface forms). Surface forms
    missing from the map fall back to on-the-fly embedding via
    `canonicalize_entity`'s default path.

    Idempotent: re-running with the same claim_id and surface_forms is
    safe — `store.link_claim_entity` already handles duplicate links.
    """
    if not surface_forms:
        return []

    entity_ids: list[str] = []
    seen: set[str] = set()
    for surface in surface_forms:
        surface = (surface or "").strip()
        if not surface or surface in seen:
            continue
        seen.add(surface)
        # Bound the length — upstream parsers occasionally emit an
        # entire clause as an "entity" by mistake. 80 chars covers all
        # real named entities without becoming a catch-all.
        if len(surface) > 80:
            logger.debug(
                "canonicalize: skipping surface %r (too long, %d chars)",
                surface[:60], len(surface),
            )
            continue

        precomputed = embeddings.get(surface) if embeddings else None
        try:
            ent_id, _conf, _is_new = await canonicalize_entity(
                store,
                workspace_id=workspace_id,
                surface_form=surface,
                embedding=precomputed,
                disambig_client=disambig_client,
            )
        except MeshStoreError as exc:
            logger.warning(
                "canonicalize: skipping %r due to %s", surface, exc,
            )
            continue
        store.link_claim_entity(claim_id, ent_id)
        entity_ids.append(ent_id)

    return entity_ids


# ───── store helpers ─────

def _find_by_canonical(
    store: MeshStore, workspace_id: str, canonical_name: str
) -> dict | None:
    row = store._conn.execute(
        """SELECT * FROM entities
           WHERE workspace_id = ? AND canonical_name = ?""",
        (workspace_id, canonical_name),
    ).fetchone()
    return dict(row) if row else None


def _find_by_alias(
    store: MeshStore, workspace_id: str, surface_form: str
) -> dict | None:
    """
    Case-insensitive alias match. Aliases are stored as JSON arrays in
    the `aliases` column, so we SELECT all entities in the workspace
    and filter in Python. At v1 scale (≤ a few hundred entities per
    workspace) this is fine. If the entity count grows past a few
    thousand, move to a normalized alias table.
    """
    needle = surface_form.lower()
    rows = store._conn.execute(
        "SELECT * FROM entities WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchall()
    import json as _json
    for row in rows:
        aliases_raw = row["aliases"]
        if not aliases_raw:
            continue
        try:
            aliases = _json.loads(aliases_raw)
        except (ValueError, TypeError):
            continue
        if any(
            (a or "").strip().lower() == needle
            for a in aliases if isinstance(a, str)
        ):
            return dict(row)
    return None


def _vec_neighbours(
    store: MeshStore,
    *,
    workspace_id: str,
    query_embedding: np.ndarray,
    k: int = 5,
) -> list[tuple[dict, float]]:
    """
    KNN over `vec_entities`, then hydrate each rowid back to an entity
    row. Uses the same over-fetch pattern as `search_claims_by_vector`
    — we ask vec0 for `k * 3` candidates and filter by workspace in
    the outer query to defend against the KNN-then-filter lossy
    behavior.

    Returns a list of (entity_dict, cosine_similarity) tuples sorted by
    descending cosine. If the `vec_entities` table has no rows yet,
    returns an empty list.
    """
    q_arr = np.asarray(query_embedding, dtype=np.float32)
    if q_arr.ndim != 1 or q_arr.shape[0] != EMBEDDING_DIM:
        raise MeshStoreError(
            f"Query embedding must be 1-D with dim={EMBEDDING_DIM}, "
            f"got shape {q_arr.shape}"
        )

    # Short-circuit: no entities yet → no neighbours
    count_row = store._conn.execute(
        "SELECT COUNT(*) AS c FROM vec_entities"
    ).fetchone()
    if count_row["c"] == 0:
        return []

    overfetch_k = max(k * 3, 30)
    sql = """
        SELECT m.entity_id AS ent_id, v.distance
        FROM vec_entities v
        JOIN vec_entities_mapping m ON m.rowid = v.rowid
        JOIN entities e ON e.id = m.entity_id
        WHERE v.embedding MATCH ?
          AND v.k = ?
          AND e.workspace_id = ?
        ORDER BY v.distance
        LIMIT ?
    """
    rows = store._conn.execute(
        sql, (q_arr.tobytes(), overfetch_k, workspace_id, k),
    ).fetchall()

    result: list[tuple[dict, float]] = []
    for row in rows:
        ent_row = store._conn.execute(
            "SELECT * FROM entities WHERE id = ?", (row["ent_id"],),
        ).fetchone()
        if ent_row is None:
            continue
        # sqlite-vec vec0 reports L2 distance for float vectors. The
        # embedding_service produces unit-length vectors, so
        # cos_sim = 1 - 0.5 * d². Clamp to [-1, 1] defensively.
        distance = float(row["distance"])
        cosine = 1.0 - 0.5 * distance * distance
        cosine = max(-1.0, min(1.0, cosine))
        result.append((dict(ent_row), cosine))
    return result


def _add_alias(store: MeshStore, entity_row: dict, new_alias: str) -> None:
    """Append `new_alias.lower()` to the entity's aliases list, dedup,
    and UPDATE the row in place. No-op if the alias is already there."""
    import json as _json
    existing = entity_row.get("aliases") or "[]"
    try:
        aliases = _json.loads(existing)
        if not isinstance(aliases, list):
            aliases = []
    except (ValueError, TypeError):
        aliases = []
    needle = new_alias.lower()
    if any(
        (a or "").strip().lower() == needle
        for a in aliases if isinstance(a, str)
    ):
        return
    aliases.append(new_alias.lower())
    store._conn.execute(
        "UPDATE entities SET aliases = ? WHERE id = ?",
        (_json.dumps(aliases), entity_row["id"]),
    )


def _update_entity_confidence(
    store: MeshStore, *, entity_id: str, new_confidence: float,
) -> None:
    store._conn.execute(
        "UPDATE entities SET confidence = ? WHERE id = ?",
        (float(new_confidence), entity_id),
    )


# ───── embedding helpers ─────

def _embed_surface_form(surface: str) -> np.ndarray:
    """
    Embed a single surface form using the production embedding service.
    Returns a unit-normalized float32 array of length EMBEDDING_DIM.

    Tests that want to avoid loading the real model can pass an
    embedding explicitly to `canonicalize_entity(embedding=...)`.
    """
    try:
        from src.utils.embedding_service import embed_texts
    except ImportError as exc:
        raise MeshStoreError(
            "src.utils.embedding_service is required for entity embedding "
            f"({exc}). Pass an explicit embedding= kwarg or install deps."
        ) from exc
    vecs = embed_texts([surface])
    arr = np.asarray(vecs[0], dtype=np.float32)
    if arr.shape != (EMBEDDING_DIM,):
        raise MeshStoreError(
            f"Embedding service returned shape {arr.shape}, expected "
            f"({EMBEDDING_DIM},). Model change detected."
        )
    return arr
