"""
Persistent campaign storage backed by SQLite.

Stores research campaigns (multi-query batches) so they survive server
restarts.  Each campaign holds its queries, per-query status, aggregated
results, and optional metadata -- all serialised as JSON TEXT columns.

DB path controlled by PG_CAMPAIGN_DB_PATH (default: state/pg_campaigns.sqlite).
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import aiosqlite
from dotenv import load_dotenv
from src.polaris_graph.settings import resolve

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LAW VI -- all paths/thresholds from environment, never hard-coded
# ---------------------------------------------------------------------------
_DB_DIR = Path(resolve("PG_CACHE_DIR"))
_DB_PATH = Path(os.getenv("PG_CAMPAIGN_DB_PATH", str(_DB_DIR / "pg_campaigns.sqlite")))

# JSON serialisation helpers
_JSON_FIELDS = ("queries_json", "results_json", "metadata_json")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _ensure_table(db: aiosqlite.Connection) -> None:
    """Create the campaigns table and indices if they do not exist."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            campaign_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            description   TEXT NOT NULL DEFAULT '',
            queries_json  TEXT NOT NULL DEFAULT '[]',
            status        TEXT NOT NULL DEFAULT 'created',
            results_json  TEXT NOT NULL DEFAULT '{}',
            created_at    REAL NOT NULL,
            updated_at    REAL NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaigns_status
            ON campaigns (status)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_campaigns_created
            ON campaigns (created_at DESC)
    """)
    await db.commit()


def _serialize_json_fields(campaign: dict) -> dict:
    """Convert Python objects in JSON columns to JSON strings for storage.

    Operates on a *copy* so the caller's dict is not mutated.
    """
    row = dict(campaign)
    for field in _JSON_FIELDS:
        value = row.get(field)
        if value is not None and not isinstance(value, str):
            row[field] = json.dumps(value, ensure_ascii=False, default=str)
    return row


def _deserialize_json_fields(row: dict) -> dict:
    """Parse JSON TEXT columns back into Python objects."""
    result = dict(row)
    for field in _JSON_FIELDS:
        raw = result.get(field)
        if raw is not None and isinstance(raw, str):
            try:
                result[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "[campaign_store] Failed to parse %s for campaign %s: %s",
                    field,
                    result.get("campaign_id", "?"),
                    str(exc)[:200],
                )
                # Keep the raw string rather than silently dropping data
    return result


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """Convert an aiosqlite.Row to a plain dict, then deserialise JSON fields."""
    raw = {
        "campaign_id": row["campaign_id"],
        "name": row["name"],
        "description": row["description"],
        "queries_json": row["queries_json"],
        "status": row["status"],
        "results_json": row["results_json"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "metadata_json": row["metadata_json"],
    }
    return _deserialize_json_fields(raw)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def init_campaign_store() -> None:
    """Initialise the campaign store -- create the SQLite table if needed.

    Safe to call multiple times (idempotent).  Must be awaited at server
    startup before any other campaign_store function is used.
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            await _ensure_table(db)
        logger.info(
            "[campaign_store] Initialised at %s",
            _DB_PATH,
        )
    except Exception as exc:
        logger.error(
            "[campaign_store] Failed to initialise database at %s: %s",
            _DB_PATH,
            str(exc)[:300],
        )
        raise


async def save_campaign(campaign: dict) -> None:
    """Insert or update (upsert) a campaign.

    ``campaign`` must contain at least ``campaign_id``.  All JSON-column
    values (queries_json, results_json, metadata_json) may be passed as
    Python objects -- they are serialised automatically.

    Raises on database errors (LAW II -- no silent failures).
    """
    if not campaign.get("campaign_id"):
        raise ValueError("campaign dict must contain a non-empty 'campaign_id'")

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = _serialize_json_fields(campaign)
    now = time.time()

    # Fill defaults for required columns if the caller omitted them
    row.setdefault("name", "")
    row.setdefault("description", "")
    row.setdefault("queries_json", "[]")
    row.setdefault("status", "created")
    row.setdefault("results_json", "{}")
    row.setdefault("created_at", now)
    row.setdefault("updated_at", now)
    row.setdefault("metadata_json", "{}")

    # Always bump updated_at on save
    row["updated_at"] = now

    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            await _ensure_table(db)
            await db.execute(
                """INSERT OR REPLACE INTO campaigns
                   (campaign_id, name, description, queries_json, status,
                    results_json, created_at, updated_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["campaign_id"],
                    row["name"],
                    row["description"],
                    row["queries_json"],
                    row["status"],
                    row["results_json"],
                    row["created_at"],
                    row["updated_at"],
                    row["metadata_json"],
                ),
            )
            await db.commit()

        logger.debug(
            "[campaign_store] Saved campaign %s (status=%s)",
            row["campaign_id"],
            row["status"],
        )
    except Exception as exc:
        logger.error(
            "[campaign_store] Failed to save campaign %s: %s",
            campaign.get("campaign_id", "?"),
            str(exc)[:300],
        )
        raise


async def get_campaign(campaign_id: str) -> Optional[dict]:
    """Retrieve a single campaign by ID.

    Returns the campaign as a dict with JSON fields already parsed,
    or ``None`` if the campaign does not exist.
    """
    if not campaign_id:
        return None

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_dict(row)
    except Exception as exc:
        logger.error(
            "[campaign_store] Failed to get campaign %s: %s",
            campaign_id,
            str(exc)[:300],
        )
        raise


async def list_campaigns() -> list[dict]:
    """Return all campaigns, ordered by created_at descending (newest first).

    JSON fields are parsed before returning.  Returns an empty list if the
    store is empty or the database has not been initialised.
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM campaigns ORDER BY created_at DESC"
            )
            rows = await cursor.fetchall()
            return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.error(
            "[campaign_store] Failed to list campaigns: %s",
            str(exc)[:300],
        )
        raise


async def delete_campaign(campaign_id: str) -> bool:
    """Delete a campaign by ID.

    Returns ``True`` if a row was actually deleted, ``False`` if the
    campaign_id did not exist.
    """
    if not campaign_id:
        return False

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            await _ensure_table(db)
            cursor = await db.execute(
                "DELETE FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            )
            await db.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info(
                "[campaign_store] Deleted campaign %s",
                campaign_id,
            )
        else:
            logger.debug(
                "[campaign_store] Campaign %s not found for deletion",
                campaign_id,
            )
        return deleted
    except Exception as exc:
        logger.error(
            "[campaign_store] Failed to delete campaign %s: %s",
            campaign_id,
            str(exc)[:300],
        )
        raise


async def update_campaign_status(
    campaign_id: str,
    status: str,
    results: Optional[dict] = None,
) -> None:
    """Update a campaign's status and optionally its results.

    Raises ``ValueError`` if the campaign does not exist (LAW II --
    fail loudly, never silently no-op on missing data).
    """
    if not campaign_id:
        raise ValueError("campaign_id must be a non-empty string")

    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()

    try:
        async with aiosqlite.connect(str(_DB_PATH)) as db:
            await _ensure_table(db)

            # Verify existence first
            cursor = await db.execute(
                "SELECT campaign_id FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            )
            if await cursor.fetchone() is None:
                raise ValueError(
                    f"Campaign not found: {campaign_id}"
                )

            if results is not None:
                results_json = json.dumps(
                    results, ensure_ascii=False, default=str,
                )
                await db.execute(
                    """UPDATE campaigns
                       SET status = ?, results_json = ?, updated_at = ?
                       WHERE campaign_id = ?""",
                    (status, results_json, now, campaign_id),
                )
            else:
                await db.execute(
                    """UPDATE campaigns
                       SET status = ?, updated_at = ?
                       WHERE campaign_id = ?""",
                    (status, now, campaign_id),
                )
            await db.commit()

        logger.debug(
            "[campaign_store] Updated campaign %s -> status=%s",
            campaign_id,
            status,
        )
    except ValueError:
        # Re-raise domain errors without wrapping
        raise
    except Exception as exc:
        logger.error(
            "[campaign_store] Failed to update campaign %s: %s",
            campaign_id,
            str(exc)[:300],
        )
        raise
