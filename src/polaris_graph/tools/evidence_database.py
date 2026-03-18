"""GAP-5: SQLite evidence database for analytical queries.

Loads evidence into an in-memory SQLite database, enabling SQL-based
analysis that would be prohibitively slow with Python list operations
on 1000+ evidence pieces.

The LLM can write SQL queries to find patterns:
- GROUP BY source_url to find per-source stats
- AVG(relevance_score) to rank sources
- COUNT(*) WHERE quality_tier = 'GOLD' for tier distribution
- JOIN-based cross-referencing
"""

import json
import logging
import os
import re
import sqlite3
from typing import Optional

logger = logging.getLogger("polaris_graph")

_MAX_QUERY_RESULTS = int(os.getenv("PG_SQL_MAX_RESULTS", "500"))
_BLOCKED_SQL_PATTERNS = [
    r'\bDROP\b', r'\bDELETE\b', r'\bUPDATE\b', r'\bINSERT\b',
    r'\bALTER\b', r'\bCREATE\b', r'\bATTACH\b', r'\bDETACH\b',
    r'\bPRAGMA\b',
]


class EvidenceDatabase:
    """In-memory SQLite database for evidence analysis.

    Usage:
        db = EvidenceDatabase()
        db.load_evidence(evidence_store)
        results = db.query("SELECT source_url, COUNT(*) as n FROM evidence GROUP BY source_url ORDER BY n DESC")
        db.close()
    """

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._initialized = False

    def load_evidence(self, evidence_store: dict) -> int:
        """Load evidence from the side-channel store into SQLite.

        Creates tables: evidence, structured_data

        Returns: number of evidence rows loaded.
        """
        cursor = self._conn.cursor()

        # Create evidence table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                evidence_id TEXT PRIMARY KEY,
                source_url TEXT,
                source_title TEXT,
                source_type TEXT,
                statement TEXT,
                direct_quote TEXT,
                quality_tier TEXT,
                relevance_score REAL,
                perspective TEXT,
                fact_category TEXT,
                year INTEGER,
                source_confidence REAL,
                nli_score REAL
            )
        """)

        # Create structured_data table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS structured_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT,
                data_type TEXT,
                label TEXT,
                value REAL,
                unit TEXT,
                year TEXT,
                context TEXT,
                source_url TEXT,
                FOREIGN KEY (evidence_id) REFERENCES evidence(evidence_id)
            )
        """)

        # Create source_summary view
        cursor.execute("""
            CREATE VIEW IF NOT EXISTS source_summary AS
            SELECT
                source_url,
                source_title,
                COUNT(*) as evidence_count,
                AVG(relevance_score) as avg_relevance,
                SUM(CASE WHEN quality_tier = 'GOLD' THEN 1 ELSE 0 END) as gold_count,
                SUM(CASE WHEN quality_tier = 'SILVER' THEN 1 ELSE 0 END) as silver_count,
                SUM(CASE WHEN quality_tier = 'BRONZE' THEN 1 ELSE 0 END) as bronze_count,
                GROUP_CONCAT(DISTINCT perspective) as perspectives
            FROM evidence
            GROUP BY source_url
        """)

        # Load data
        loaded = 0
        for ev_id, ev in evidence_store.items():
            if ev.get("type") == "analysis":  # Skip analysis results
                continue

            try:
                cursor.execute("""
                    INSERT OR REPLACE INTO evidence
                    (evidence_id, source_url, source_title, source_type, statement,
                     direct_quote, quality_tier, relevance_score, perspective,
                     fact_category, year, source_confidence, nli_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ev_id,
                    ev.get("source_url", ""),
                    ev.get("source_title", ""),
                    ev.get("source_type", ""),
                    ev.get("statement", ""),
                    ev.get("direct_quote", ""),
                    ev.get("quality_tier", "BRONZE"),
                    ev.get("relevance_score", 0.0),
                    ev.get("perspective", ""),
                    ev.get("fact_category", ""),
                    ev.get("year"),
                    ev.get("source_confidence", 0.0),
                    ev.get("nli_self_check_score"),
                ))
                loaded += 1

                # Load structured data
                for dp in ev.get("structured_data", []):
                    value = dp.get("value", "")
                    numeric_value = None
                    try:
                        numeric_value = float(str(value).replace(",", "").strip("%$"))
                    except (ValueError, TypeError):
                        pass

                    if numeric_value is not None:
                        cursor.execute("""
                            INSERT INTO structured_data
                            (evidence_id, data_type, label, value, unit, year, context, source_url)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            ev_id,
                            dp.get("data_type", ""),
                            dp.get("label", ""),
                            numeric_value,
                            dp.get("unit", ""),
                            dp.get("year", ""),
                            dp.get("context", ""),
                            ev.get("source_url", ""),
                        ))
            except Exception as exc:
                logger.debug("[evidence_db] Failed to load %s: %s", ev_id, str(exc)[:100])

        self._conn.commit()
        self._initialized = True

        logger.info("[evidence_db] Loaded %d evidence pieces into SQLite", loaded)
        return loaded

    def validate_query(self, sql: str) -> tuple[bool, str]:
        """Validate a SQL query for safety.

        Only SELECT queries allowed. No DDL, DML, or PRAGMA.
        """
        normalized = sql.strip().upper()

        if not normalized.startswith("SELECT"):
            return False, "Only SELECT queries allowed"

        for pattern in _BLOCKED_SQL_PATTERNS:
            if re.search(pattern, normalized):
                return False, f"Blocked SQL pattern: {pattern}"

        return True, ""

    def query(self, sql: str, params: tuple = ()) -> dict:
        """Execute a SELECT query and return results.

        Args:
            sql: SQL SELECT query.
            params: Query parameters (for parameterized queries).

        Returns:
            {
                "success": bool,
                "columns": [str],
                "rows": [[value]],
                "row_count": int,
                "markdown_table": str,
                "error": str | None,
            }
        """
        is_valid, reason = self.validate_query(sql)
        if not is_valid:
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "markdown_table": "",
                "error": reason,
            }

        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, params)

            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = [list(row) for row in cursor.fetchmany(_MAX_QUERY_RESULTS)]

            # Build markdown table
            md_lines = []
            if columns and rows:
                md_lines.append("| " + " | ".join(str(c) for c in columns) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
                for row in rows[:50]:  # Cap markdown at 50 rows
                    md_lines.append("| " + " | ".join(str(v) if v is not None else "\u2014" for v in row) + " |")

            markdown = "\n".join(md_lines)

            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "markdown_table": markdown,
                "error": None,
            }
        except Exception as exc:
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "markdown_table": "",
                "error": str(exc)[:500],
            }

    def get_schema(self) -> str:
        """Return the database schema as a string for LLM context."""
        return """
Tables:
  evidence (evidence_id TEXT PK, source_url TEXT, source_title TEXT, source_type TEXT,
            statement TEXT, direct_quote TEXT, quality_tier TEXT, relevance_score REAL,
            perspective TEXT, fact_category TEXT, year INT, source_confidence REAL, nli_score REAL)

  structured_data (id INT PK, evidence_id TEXT FK, data_type TEXT, label TEXT,
                   value REAL, unit TEXT, year TEXT, context TEXT, source_url TEXT)

Views:
  source_summary (source_url, source_title, evidence_count, avg_relevance,
                  gold_count, silver_count, bronze_count, perspectives)

Example queries:
  SELECT quality_tier, COUNT(*) as n, AVG(relevance_score) as avg_rel FROM evidence GROUP BY quality_tier
  SELECT source_url, evidence_count, avg_relevance FROM source_summary ORDER BY avg_relevance DESC LIMIT 10
  SELECT label, AVG(value) as mean, MIN(value) as min, MAX(value) as max FROM structured_data GROUP BY label
""".strip()

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


async def query_evidence_with_llm(
    client,
    evidence_store: dict,
    question: str,
    research_context: str = "",
) -> dict:
    """Let the LLM write SQL queries to analyze evidence.

    The LLM sees the schema, writes a query, we execute it, return results.
    Retries once if the query fails.

    Args:
        client: OpenRouterClient for LLM calls.
        evidence_store: Evidence to load into database.
        question: What to analyze.
        research_context: Topic context.

    Returns:
        {
            "success": bool,
            "query": str,
            "result": dict (from EvidenceDatabase.query),
            "interpretation": str (LLM explanation of results),
        }
    """
    db = EvidenceDatabase()
    loaded = db.load_evidence(evidence_store)

    if loaded == 0:
        db.close()
        return {"success": False, "query": "", "result": {}, "interpretation": "No evidence to analyze"}

    schema = db.get_schema()

    # Ask LLM to write SQL
    from pydantic import BaseModel, Field

    class SQLQuery(BaseModel):
        query: str = Field(description="SQL SELECT query to answer the question")
        explanation: str = Field(description="What this query does", default="")

    prompt = (
        f"Research context: {research_context}\n"
        f"Question: {question}\n\n"
        f"Database schema:\n{schema}\n\n"
        f"Evidence loaded: {loaded} pieces\n\n"
        "Write a SQL SELECT query to answer this question. "
        "Use aggregation (GROUP BY, AVG, COUNT) to find patterns. "
        "ONLY SELECT queries allowed."
    )

    prev_error = ""
    for attempt in range(2):
        try:
            sql_result = await client.generate_structured(
                prompt=prompt if attempt == 0 else (
                    f"{prompt}\n\nPrevious query failed: {prev_error}. Fix the query."
                ),
                schema=SQLQuery,
                system="You are a SQL analyst. Write precise SELECT queries for research evidence analysis.",
                max_tokens=1024,
                timeout=30,
            )

            query_text = sql_result.query.strip()
            result = db.query(query_text)

            if result["success"]:
                db.close()
                return {
                    "success": True,
                    "query": query_text,
                    "result": result,
                    "interpretation": sql_result.explanation,
                }
            else:
                prev_error = result["error"]
        except Exception as exc:
            prev_error = str(exc)[:200]

    db.close()
    return {"success": False, "query": "", "result": {}, "interpretation": f"Query failed: {prev_error}"}
