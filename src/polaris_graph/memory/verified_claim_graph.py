"""Verified-claim knowledge graph (the snowball, canonical stage 17) — SQLite store.

I-meta-002 sub-PR-5. Persists every per-claim pipeline outcome and exposes a REUSE pool of
prior knowledge for later claims/questions in the same campaign. There is NO network here.
The store opens a SQLite file at an INJECTED path (default under a caller-supplied run dir),
and EVERY timestamp is passed in by the caller — this module never calls `datetime.now()`
(LAW VI: inject, do not self-source non-determinism).

Anti-snowball-poisoning (Codex iter-2 P1-3). `write_claim` persists ALL rows (including
FABRICATED / UNSUPPORTED / PARTIAL / UNREACHABLE) as AUDIT-ONLY records, but
`query_related_claims` returns ONLY rows whose stored verdict == VERIFIED. A claim that did
not clear the full Mirror -> Sentinel -> Judge fail-closed pipeline can therefore NEVER be
reused as prior knowledge — a hallucination cannot poison a later claim by being recalled as
"already established." The `reusable` column makes that filter explicit and machine-auditable.

`find_contradictions` is a cross-time contradiction-flag HOOK over the reuse pool. The
contract it owns is: surface prior VERIFIED claims that a new claim may contradict so a human
/ Codex §-1.1 audit can adjudicate. The heuristic here is a documented STUB (shared keyword
overlap + a negation-polarity mismatch OR a divergent numeric token); it intentionally
over-flags rather than under-flags (clinical-safety: a missed contradiction is the lethal
error). It is NOT a verdict — it is a flag for review.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# --- canonical verdict tokens (string-constant pattern; never an Enum here) ---------------
_VERDICT_VERIFIED = "VERIFIED"

# Default SQLite filename created under the injected run dir.
_DEFAULT_DB_FILENAME = "verified_claim_graph.sqlite"

# Tokens shorter than this are dropped from keyword matching (stop-word-ish noise control).
_MIN_KEYWORD_LEN = 4

# Negation markers used by the contradiction heuristic (documented stub).
_NEGATION_MARKERS = frozenset(
    {"no", "not", "never", "without", "absent", "lacks", "fails", "cannot", "neither", "nor"}
)

# Word + number tokenizers for the simple substring/keyword reuse + contradiction heuristics.
_WORD_RE = re.compile(r"[a-z0-9]+")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class VerifiedClaimRecord:
    """One row of the verified-claim graph (a stored claim + its provenance)."""

    claim_id: str
    claim_text: str
    verdict: str
    reusable: bool
    role_verdicts: dict
    timestamp: str


@dataclass
class ContradictionFlag:
    """A cross-time contradiction candidate flagged for human / Codex §-1.1 adjudication.

    `reason` documents WHY the pair was flagged (negation-polarity mismatch and/or divergent
    numeric tokens over a shared-keyword overlap). This is a REVIEW FLAG, not a verdict.
    """

    new_claim_text: str
    prior_claim_id: str
    prior_claim_text: str
    reason: str


def _keywords(text: str) -> set[str]:
    """Content keywords (lower-cased word tokens at/above the min length)."""
    return {tok for tok in _WORD_RE.findall(text.lower()) if len(tok) >= _MIN_KEYWORD_LEN}


def _numbers(text: str) -> set[str]:
    """Numeric tokens (as strings) appearing in the text."""
    return set(_NUMBER_RE.findall(text))


def _has_negation(text: str) -> bool:
    """True iff the text carries a negation marker word."""
    return bool(_NEGATION_MARKERS & set(_WORD_RE.findall(text.lower())))


class VerifiedClaimGraphStore:
    """SQLite-backed verified-claim graph (the snowball). Synchronous, offline, injected path.

    Open with an explicit `db_path`, OR pass a `run_dir` and the store creates
    `<run_dir>/verified_claim_graph.sqlite`. The connection is held open for the store's
    lifetime; call `close()` when done (the store is also a context manager).
    """

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        run_dir: str | Path | None = None,
        read_only: bool = False,
    ) -> None:
        if db_path is not None and run_dir is not None:
            raise ValueError("pass exactly one of db_path or run_dir, not both")
        if db_path is not None:
            resolved = Path(db_path)
        elif run_dir is not None:
            resolved = Path(run_dir) / _DEFAULT_DB_FILENAME
        else:
            raise ValueError("VerifiedClaimGraphStore requires db_path or run_dir")
        # I-meta-002-q1d (#948) Codex diff-gate iter-1 P1: a READ-ONLY open for the campaign reuse
        # read-path. Opens the existing db via the SQLite `mode=ro` URI — it does NOT create the parent
        # dir, does NOT create/migrate the table, and cannot mutate or write-lock the file. A missing or
        # unreadable db raises sqlite3.OperationalError (the caller fail-opens). Write mode (default) is
        # unchanged: mkdir + writable connection + _ensure_table.
        self._db_path = resolved
        self._read_only = read_only
        if read_only:
            self._conn = sqlite3.connect(
                f"file:{resolved}?mode=ro", uri=True, check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            # NO _ensure_table — a read-only connection must not attempt DDL.
        else:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(resolved))
            self._conn.row_factory = sqlite3.Row
            self._ensure_table()

    @property
    def db_path(self) -> Path:
        """The resolved SQLite path this store opened (read-only accessor for callers/audit)."""
        return self._db_path

    def __enter__(self) -> "VerifiedClaimGraphStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def _ensure_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS verified_claims (
                row_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id      TEXT NOT NULL,
                claim_text    TEXT NOT NULL,
                verdict       TEXT NOT NULL,
                reusable      INTEGER NOT NULL,
                role_verdicts TEXT NOT NULL,
                timestamp     TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def write_claim(
        self,
        *,
        claim_text: str,
        claim_id: str,
        verdict: str,
        role_verdicts: dict,
        timestamp: str,
    ) -> None:
        """Persist one claim outcome. ALL verdicts are stored (audit), only VERIFIED is reusable.

        `reusable` is derived solely from `verdict == "VERIFIED"` (anti-poisoning, Codex
        iter-2 P1-3): a non-VERIFIED row lands in the table for the audit trail but is EXCLUDED
        from `query_related_claims` reuse. `timestamp` is the caller-supplied audit time (this
        store never sources its own clock). `role_verdicts` (the per-role Mirror/Sentinel/Judge
        signals) is JSON-serialized for provenance.
        """
        reusable = 1 if verdict == _VERDICT_VERIFIED else 0
        self._conn.execute(
            """
            INSERT INTO verified_claims
                (claim_id, claim_text, verdict, reusable, role_verdicts, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                claim_id,
                claim_text,
                verdict,
                reusable,
                json.dumps(role_verdicts, sort_keys=True, default=str),
                timestamp,
            ),
        )
        self._conn.commit()

    def query_related_claims(self, claim_text: str) -> list[VerifiedClaimRecord]:
        """Return prior VERIFIED claims related to `claim_text` (the REUSE pool).

        ONLY rows with `reusable == 1` (verdict == VERIFIED) are eligible (anti-poisoning).
        Relatedness is a simple keyword-overlap match against the stored claim text (the
        contract only requires substring/keyword matching for reuse); an empty query keyword
        set returns nothing. Returns the eligible records ordered by recency (row_id desc).
        """
        query_keywords = _keywords(claim_text)
        # An empty / content-free query keyword set returns nothing (matches the docstring).
        # Without this guard an empty `claim_text` would substring-match EVERY stored row
        # (`"" in x` is True), returning the whole reuse pool (Codex sub-PR-5 diff P2).
        if not query_keywords:
            return []
        rows = self._conn.execute(
            "SELECT * FROM verified_claims WHERE reusable = 1 ORDER BY row_id DESC"
        ).fetchall()
        related: list[VerifiedClaimRecord] = []
        for row in rows:
            stored_keywords = _keywords(row["claim_text"])
            # Relate iff they share a content keyword OR one claim text contains the other.
            shares_keyword = bool(query_keywords & stored_keywords)
            substring_match = (
                claim_text.lower() in row["claim_text"].lower()
                or row["claim_text"].lower() in claim_text.lower()
            )
            if shares_keyword or substring_match:
                related.append(self._to_record(row))
        return related

    def find_contradictions(self, claim_text: str) -> list[ContradictionFlag]:
        """Flag prior VERIFIED claims that the new claim may CONTRADICT (cross-time hook).

        Documented heuristic STUB (over-flags by design — a missed contradiction is the lethal
        error in clinical context): among the related VERIFIED reuse pool, flag a pair when
        they share content keywords AND EITHER their negation polarity differs (one negates,
        the other does not) OR they carry divergent numeric tokens (a dose/percentage
        mismatch). This is a REVIEW FLAG for the human / Codex §-1.1 audit, never a verdict.
        """
        new_keywords = _keywords(claim_text)
        new_negated = _has_negation(claim_text)
        new_numbers = _numbers(claim_text)
        flags: list[ContradictionFlag] = []
        for record in self.query_related_claims(claim_text):
            prior_keywords = _keywords(record.claim_text)
            shared = new_keywords & prior_keywords
            if not shared:
                continue
            prior_negated = _has_negation(record.claim_text)
            prior_numbers = _numbers(record.claim_text)
            reasons: list[str] = []
            if new_negated != prior_negated:
                reasons.append("negation-polarity mismatch over shared keywords")
            if new_numbers and prior_numbers and new_numbers != prior_numbers:
                reasons.append(
                    f"divergent numeric tokens new={sorted(new_numbers)} "
                    f"prior={sorted(prior_numbers)}"
                )
            if reasons:
                flags.append(
                    ContradictionFlag(
                        new_claim_text=claim_text,
                        prior_claim_id=record.claim_id,
                        prior_claim_text=record.claim_text,
                        reason="; ".join(reasons),
                    )
                )
        return flags

    @staticmethod
    def _to_record(row: sqlite3.Row) -> VerifiedClaimRecord:
        return VerifiedClaimRecord(
            claim_id=row["claim_id"],
            claim_text=row["claim_text"],
            verdict=row["verdict"],
            reusable=bool(row["reusable"]),
            role_verdicts=json.loads(row["role_verdicts"]),
            timestamp=row["timestamp"],
        )
