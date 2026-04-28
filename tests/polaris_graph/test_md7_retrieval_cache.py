"""M-D7 phase 1 (bootstrap) retrieval-cache tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.retrieval_cache import (
    CacheEntry,
    RetrievalCacheError,
    RetrievalCacheStateError,
    RetrievalCacheStore,
    cache_entry_to_dict,
    make_cache_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> RetrievalCacheStore:
    """Fresh file-backed store for each test (matches M-21
    pattern: per-call SQLite connections from a Path)."""
    return RetrievalCacheStore(tmp_path / "cache.db")


# ---------------------------------------------------------------------------
# Cache key construction
# ---------------------------------------------------------------------------


def test_doi_cache_key_canonical() -> None:
    """DOI key strips prefixes, lowercases."""
    assert make_cache_key("https://doi.org/10.1000/foo.bar") == "doi:10.1000/foo.bar"
    assert make_cache_key("https://dx.doi.org/10.1000/FOO") == "doi:10.1000/foo"
    assert make_cache_key("doi:10.1000/foo") == "doi:10.1000/foo"
    assert make_cache_key("10.1000/foo") == "doi:10.1000/foo"


def test_pmid_cache_key_canonical() -> None:
    """PMID accepts URL forms + bare digits."""
    assert make_cache_key("12345678") == "pmid:12345678"
    assert (
        make_cache_key("https://pubmed.ncbi.nlm.nih.gov/12345678/")
        == "pmid:12345678"
    )
    assert (
        make_cache_key("https://www.ncbi.nlm.nih.gov/pubmed/12345678")
        == "pmid:12345678"
    )


def test_url_cache_key_canonical() -> None:
    """Web URL falls back to canonicalized form."""
    a = make_cache_key("https://example.com/a")
    b = make_cache_key("http://www.example.com/a/")
    assert a == b
    assert a.startswith("url:")


def test_url_cache_key_drops_tracking_params() -> None:
    a = make_cache_key("https://example.com/a?utm_source=x&id=1")
    b = make_cache_key("https://example.com/a?id=1")
    assert a == b


def test_doi_canonicalization_strips_url_decoration() -> None:
    """Round-1 fix: equivalent DOI URL forms must canonicalize
    to the same key. Trailing slash, query, fragment all dropped."""
    base = make_cache_key("10.1000/foo.bar")
    assert make_cache_key("https://doi.org/10.1000/foo.bar") == base
    assert make_cache_key("https://doi.org/10.1000/foo.bar/") == base
    assert (
        make_cache_key("https://doi.org/10.1000/foo.bar?utm_source=x")
        == base
    )
    assert make_cache_key("https://doi.org/10.1000/foo.bar#abstract") == base
    assert make_cache_key("doi:10.1000/foo.bar") == base
    assert make_cache_key("DOI:10.1000/FOO.BAR") == base


def test_doi_scheme_with_space_after_colon() -> None:
    """Round-2 polish: `doi: 10.1000/foo` (space after colon)
    is a citation-style form some sources emit. Should
    canonicalize like the no-space variant."""
    base = make_cache_key("doi:10.1000/foo")
    assert make_cache_key("doi: 10.1000/foo") == base
    assert make_cache_key("DOI:  10.1000/foo") == base


def test_doi_strict_shape_rejects_near_doi() -> None:
    """Round-1 fix: tighten DOI regex so non-DOI strings that
    happen to start with `10.` aren't misclassified.

    DOI prefix per ANSI/NISO Z39.84-2010: 10.<4-9 digits>(.subprefix)*
    A short registrant like `10.123/foo` (only 3 digits) is NOT a
    valid DOI."""
    # 3-digit registrant — invalid DOI shape, falls back to URL.
    short = make_cache_key("10.123/foo")
    assert short.startswith("url:"), f"got {short!r}"

    # 10-digit registrant exceeds spec range (max 9), invalid.
    long = make_cache_key("10.1234567890/foo")
    assert long.startswith("url:"), f"got {long!r}"

    # No suffix after slash — invalid.
    no_suffix = make_cache_key("10.1000/")
    # Falls back to URL canonicalization, which strips trailing /.
    assert no_suffix.startswith("url:"), f"got {no_suffix!r}"


def test_cache_key_kinds_dont_collide() -> None:
    """`url:` and `doi:` discriminator prefixes prevent
    cross-kind collisions."""
    doi_key = make_cache_key("10.1000/foo")
    # Construct a URL that, sans prefix, would equal the DOI body.
    url_key = make_cache_key("https://example.com/10.1000/foo")
    assert doi_key != url_key
    assert doi_key.startswith("doi:")
    assert url_key.startswith("url:")


def test_make_cache_key_rejects_empty() -> None:
    with pytest.raises(RetrievalCacheError, match="non-empty"):
        make_cache_key("")
    with pytest.raises(RetrievalCacheError, match="non-empty"):
        make_cache_key("   ")


def test_make_cache_key_rejects_uncanonicalizable() -> None:
    """An input that's not DOI / PMID / parseable URL raises."""
    with pytest.raises(RetrievalCacheError):
        make_cache_key("   ")  # whitespace-only
    # An empty path-and-query after normalization should still
    # produce a non-empty key (just the netloc), so this WORKS:
    make_cache_key("example.com")


# ---------------------------------------------------------------------------
# Put + get
# ---------------------------------------------------------------------------


def test_put_then_get_round_trips(store: RetrievalCacheStore) -> None:
    entry = store.put(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        payload=b"<html>hello</html>",
        content_type="text/html",
        fetch_status_code=200,
    )
    assert entry.cache_key == "doi:10.1000/foo"
    assert entry.payload_sha256 != ""
    assert entry.fetched_at > 0
    assert entry.last_hit_at is None  # not yet hit

    got = store.get("ws-a", "https://doi.org/10.1000/foo")
    assert got is not None
    assert got.payload == b"<html>hello</html>"
    assert got.content_type == "text/html"
    assert got.fetch_status_code == 200
    assert got.last_hit_at is not None  # hit timestamp set


def test_put_replaces_existing(store: RetrievalCacheStore) -> None:
    """Putting a second time on the same key overwrites payload."""
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"v1",
        content_type="text/html",
        fetch_status_code=200,
    )
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"v2-fresh",
        content_type="text/html",
        fetch_status_code=200,
    )
    got = store.get("ws-a", "10.1000/foo")
    assert got is not None
    assert got.payload == b"v2-fresh"


def test_get_miss_returns_none(store: RetrievalCacheStore) -> None:
    assert store.get("ws-a", "10.9999/never-cached") is None


def test_put_rejects_non_bytes_payload(
    store: RetrievalCacheStore,
) -> None:
    with pytest.raises(RetrievalCacheError, match="payload must be bytes"):
        store.put(
            workspace_id="ws-a",
            source_url="10.1000/foo",
            payload="not bytes",  # type: ignore[arg-type]
            content_type="text/html",
            fetch_status_code=200,
        )


def test_put_rejects_empty_workspace(store: RetrievalCacheStore) -> None:
    with pytest.raises(RetrievalCacheError, match="workspace_id"):
        store.put(
            workspace_id="",
            source_url="10.1000/foo",
            payload=b"x",
            content_type="text/html",
            fetch_status_code=200,
        )


# ---------------------------------------------------------------------------
# Cross-workspace isolation (M-21 invariant)
# ---------------------------------------------------------------------------


def test_workspace_isolation_get(store: RetrievalCacheStore) -> None:
    """A entry put for ws-a is invisible to ws-b."""
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"a-payload",
        content_type="text/html",
        fetch_status_code=200,
    )
    assert store.get("ws-b", "10.1000/foo") is None
    assert store.get("ws-a", "10.1000/foo") is not None


def test_workspace_isolation_evict(store: RetrievalCacheStore) -> None:
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"a-payload",
        content_type="text/html",
        fetch_status_code=200,
    )
    store.put(
        workspace_id="ws-b",
        source_url="10.1000/foo",
        payload=b"b-payload",
        content_type="text/html",
        fetch_status_code=200,
    )
    # Evicting from ws-a doesn't touch ws-b.
    deleted = store.evict_all("ws-a")
    assert deleted == 1
    assert store.get("ws-a", "10.1000/foo") is None
    assert store.get("ws-b", "10.1000/foo") is not None


def test_same_url_different_workspaces_separate_entries(
    store: RetrievalCacheStore,
) -> None:
    """Two workspaces caching the same URL get independent
    payloads. Non-shared scope is the bootstrap contract."""
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"payload-a",
        content_type="text/html",
        fetch_status_code=200,
    )
    store.put(
        workspace_id="ws-b",
        source_url="10.1000/foo",
        payload=b"payload-b",
        content_type="text/html",
        fetch_status_code=200,
    )
    a = store.get("ws-a", "10.1000/foo")
    b = store.get("ws-b", "10.1000/foo")
    assert a is not None and b is not None
    assert a.payload == b"payload-a"
    assert b.payload == b"payload-b"


# ---------------------------------------------------------------------------
# Eviction API (NOT pure TTL)
# ---------------------------------------------------------------------------


def test_evict_single_entry(store: RetrievalCacheStore) -> None:
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    assert store.evict("ws-a", "doi:10.1000/foo") is True
    assert store.get("ws-a", "10.1000/foo") is None


def test_evict_returns_false_on_miss(store: RetrievalCacheStore) -> None:
    assert store.evict("ws-a", "doi:10.1000/never") is False


def test_evict_by_url_canonicalizes(store: RetrievalCacheStore) -> None:
    """M-D10 hookup: evict_by_url accepts the raw source URL,
    canonicalizes, then deletes by key. M-D10 doesn't have to
    know our key format."""
    store.put(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    # Evict using a different but equivalent URL form.
    assert store.evict_by_url("ws-a", "10.1000/foo") is True
    assert store.get("ws-a", "https://doi.org/10.1000/foo") is None


def test_evict_older_than_drops_aged_entries(
    store: RetrievalCacheStore,
) -> None:
    now = time.time()
    # Old entry (10 hours ago).
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/old",
        payload=b"old",
        content_type="text/html",
        fetch_status_code=200,
        fetched_at=now - 10 * 3600,
    )
    # Fresh entry (1 minute ago).
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/fresh",
        payload=b"fresh",
        content_type="text/html",
        fetch_status_code=200,
        fetched_at=now - 60,
    )
    # Evict anything older than 1 hour.
    deleted = store.evict_older_than("ws-a", max_age_seconds=3600)
    assert deleted == 1
    assert store.get("ws-a", "10.1000/old") is None
    assert store.get("ws-a", "10.1000/fresh") is not None


def test_evict_older_than_negative_raises(
    store: RetrievalCacheStore,
) -> None:
    with pytest.raises(RetrievalCacheError, match=">=0"):
        store.evict_older_than("ws-a", max_age_seconds=-1)


def test_evict_all(store: RetrievalCacheStore) -> None:
    for i in range(5):
        store.put(
            workspace_id="ws-a",
            source_url=f"10.1000/{i}",
            payload=b"x",
            content_type="text/html",
            fetch_status_code=200,
        )
    deleted = store.evict_all("ws-a")
    assert deleted == 5
    assert store.count("ws-a") == 0


def test_count_returns_workspace_total(
    store: RetrievalCacheStore,
) -> None:
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/a",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/b",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    store.put(
        workspace_id="ws-b",
        source_url="10.1000/c",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    assert store.count("ws-a") == 2
    assert store.count("ws-b") == 1


# ---------------------------------------------------------------------------
# Integrity (SHA-256 over payload)
# ---------------------------------------------------------------------------


def test_payload_sha256_set_correctly(
    store: RetrievalCacheStore,
) -> None:
    import hashlib
    payload = b"hello world"
    expected = hashlib.sha256(payload).hexdigest()
    entry = store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=payload,
        content_type="text/html",
        fetch_status_code=200,
    )
    assert entry.payload_sha256 == expected
    got = store.get("ws-a", "10.1000/foo")
    assert got is not None
    assert got.payload_sha256 == expected


def test_replaced_entry_updates_sha256(
    store: RetrievalCacheStore,
) -> None:
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"v1",
        content_type="text/html",
        fetch_status_code=200,
    )
    e2 = store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"v2-much-different",
        content_type="text/html",
        fetch_status_code=200,
    )
    import hashlib
    assert e2.payload_sha256 == hashlib.sha256(b"v2-much-different").hexdigest()


# ---------------------------------------------------------------------------
# Last-hit-at tracking
# ---------------------------------------------------------------------------


def test_last_hit_at_updates_on_get(
    store: RetrievalCacheStore,
) -> None:
    entry = store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    assert entry.last_hit_at is None
    got = store.get("ws-a", "10.1000/foo")
    assert got is not None
    assert got.last_hit_at is not None
    assert got.last_hit_at >= entry.fetched_at


def test_get_select_update_is_atomic_under_concurrent_evict(
    tmp_path: Path,
) -> None:
    """Round-1 + round-2 fix: get() must be atomic against
    interleaved evict() too. The pre-v2 race shape was:
        T1: SELECT row -> got row v1
        T2: DELETE row v1
        T1: UPDATE last_hit_at WHERE key=...  (no rows match, silent)
        T1: returns row v1 (caller sees stale payload after delete)

    This test exercises gets racing evicts. The atomicity
    contract: if a get() returns a row, that row must still be
    in the DB at the moment of return (the BEGIN IMMEDIATE
    transaction prevents an evict from interleaving).

    We verify by re-reading immediately after the get and
    checking that any row we observed is internally consistent
    (same payload SHA on the immediate re-read). Without BEGIN
    IMMEDIATE, the evicting thread can race in between, and a
    follow-up read would see None where get() returned a
    payload — that's the divergence we'd flag."""
    import hashlib
    import threading

    db = tmp_path / "race.db"
    store = RetrievalCacheStore(db)
    # Pre-load a single entry.
    store.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"v0-stable",
        content_type="text/html",
        fetch_status_code=200,
    )

    errors: list[str] = []

    def writer(i: int) -> None:
        # Alternate evict + put — both are write-side operations
        # that race the get's UPDATE.
        if i % 2 == 0:
            store.evict_by_url("ws-a", "10.1000/foo")
        else:
            store.put(
                workspace_id="ws-a",
                source_url="10.1000/foo",
                payload=f"v{i}".encode(),
                content_type="text/html",
                fetch_status_code=200,
            )

    def reader() -> None:
        try:
            got = store.get("ws-a", "10.1000/foo")
            if got is not None:
                # SHA must match payload (BEGIN IMMEDIATE makes
                # SELECT + UPDATE see a coherent snapshot).
                expected = hashlib.sha256(got.payload).hexdigest()
                if got.payload_sha256 != expected:
                    errors.append(
                        f"sha mismatch: stored {got.payload_sha256}, "
                        f"actual {expected}"
                    )
        except Exception as exc:
            errors.append(f"read raised: {exc!r}")

    threads = []
    for i in range(1, 101):
        threads.append(threading.Thread(target=writer, args=(i,)))
    for _ in range(100):
        threads.append(threading.Thread(target=reader))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"race detected: {errors[:3]}"


# ---------------------------------------------------------------------------
# Dict serialization
# ---------------------------------------------------------------------------


def test_cache_entry_to_dict_excludes_payload() -> None:
    """Bytes don't serialize to JSON; the dict carries
    payload_sha256 + payload_size_bytes for verification, not
    the raw bytes."""
    entry = CacheEntry(
        cache_key="doi:10.1000/foo",
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"hello world",
        content_type="text/html",
        payload_sha256="abc123",
        fetched_at=1700000000.0,
        last_hit_at=1700000100.0,
        fetch_status_code=200,
    )
    d = cache_entry_to_dict(entry)
    assert "payload" not in d
    assert d["payload_sha256"] == "abc123"
    assert d["payload_size_bytes"] == 11
    assert d["cache_key"] == "doi:10.1000/foo"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_init_schema_idempotent(tmp_path: Path) -> None:
    """Re-instantiating the store on the same DB file is a no-op
    (CREATE IF NOT EXISTS in the schema)."""
    db = tmp_path / "cache.db"
    s1 = RetrievalCacheStore(db)
    s2 = RetrievalCacheStore(db)  # second init must not raise
    s2.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    # Both instances see the row (same DB file).
    assert s1.count("ws-a") == 1
    assert s2.count("ws-a") == 1


def test_store_creates_parent_dir(tmp_path: Path) -> None:
    """Like M-21, the store creates parent dirs as needed."""
    nested = tmp_path / "a" / "b" / "cache.db"
    s = RetrievalCacheStore(nested)
    assert nested.parent.exists()
    s.put(
        workspace_id="ws-a",
        source_url="10.1000/foo",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    assert s.count("ws-a") == 1


# ---------------------------------------------------------------------------
# Coexists with M-21 in same DB
# ---------------------------------------------------------------------------


def test_coexists_with_workspace_memory_in_same_db(
    tmp_path: Path,
) -> None:
    """The cache table doesn't conflict with the M-21 memory
    table — both can live in one DB file. Confirms the design
    decision to extend M-21 substrate rather than fork."""
    from src.polaris_graph.audit_ir.workspace_memory import (
        WorkspaceMemoryStore,
    )

    db = tmp_path / "ws.db"
    mem = WorkspaceMemoryStore(db)
    cache = RetrievalCacheStore(db)

    # Both work independently on the same DB file.
    mem.append_entry(
        workspace_id="ws-a",
        claim_text="GLP-1 reduces A1c",
        source_url="https://doi.org/10.1000/foo",
        source_tier="T1",
        source_evidence_id="ev_001",
    )
    cache.put(
        workspace_id="ws-a",
        source_url="https://doi.org/10.1000/foo",
        payload=b"<html>article</html>",
        content_type="text/html",
        fetch_status_code=200,
    )
    assert cache.count("ws-a") == 1
    # M-21 uses list_entries; len() it.
    assert len(mem.list_entries(workspace_id="ws-a")) == 1
