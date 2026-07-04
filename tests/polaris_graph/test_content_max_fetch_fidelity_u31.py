"""U31 fetch-fidelity regression (I-deepfix-001).

The legacy per-source extract cap ``PG_LIVE_CONTENT_MAX`` defaulted to 25000
chars, which cut 75-87% of long clinical papers mid-body. These offline tests
pin that:

1. The default cap is now generous (well above the old 25000), so a long paper
   is retained whole rather than truncated to its abstract + intro.
2. The exact ``content[:max_chars]`` truncation the fetch path applies keeps a
   >25000-char body intact under the new default.
3. The cap remains env-driven (LAW VI): ``PG_LIVE_CONTENT_MAX`` overrides it,
   both up and down.

No network / GPU / paid-LLM: we import the module constant and exercise the
same slice operator the live fetch path uses. RED before the default was
raised (25000 truncates the 120000-char body), GREEN after.
"""
from __future__ import annotations

import importlib

from src.polaris_graph.retrieval import live_retriever

# The old cap that cut long papers. The fix must land strictly above this.
_OLD_TRUNCATION_CAP = 25000


def test_default_content_cap_is_generous():
    """The default per-source extract cap must be far above the old 25000
    so long clinical papers are not cut mid-body."""
    assert live_retriever.DEFAULT_CONTENT_MAX_CHARS > _OLD_TRUNCATION_CAP
    # A full systematic review / guideline is ~100K-190K chars; require the
    # default to retain a whole long paper.
    assert live_retriever.DEFAULT_CONTENT_MAX_CHARS >= 200000


def test_long_body_retained_beyond_old_cap():
    """A >25000-char body survives the fetch-path truncation slice under the
    new default. Mirrors the exact ``content[:max_chars]`` cap applied in
    ``_fetch_content_httpx_naive`` / ``_fetch_content``."""
    long_body = "clinical finding sentence. " * 5000  # ~135000 chars
    assert len(long_body) > _OLD_TRUNCATION_CAP

    # Same operation the live fetch path performs.
    retained = long_body[: live_retriever.DEFAULT_CONTENT_MAX_CHARS]

    # The whole body is kept (default cap exceeds this body's length), and it is
    # emphatically beyond the old truncation point.
    assert len(retained) == len(long_body)
    assert len(retained) > _OLD_TRUNCATION_CAP
    # The methods/results tail (which the old cap dropped) is present.
    assert retained.endswith("clinical finding sentence. ")


def test_cap_is_env_overridable(monkeypatch):
    """LAW VI: PG_LIVE_CONTENT_MAX drives the cap. Reload the module with the
    env set and confirm the constant tracks it (both a large and a small
    override)."""
    monkeypatch.setenv("PG_LIVE_CONTENT_MAX", "500000")
    reloaded = importlib.reload(live_retriever)
    try:
        assert reloaded.DEFAULT_CONTENT_MAX_CHARS == 500000

        monkeypatch.setenv("PG_LIVE_CONTENT_MAX", "10000")
        reloaded = importlib.reload(reloaded)
        assert reloaded.DEFAULT_CONTENT_MAX_CHARS == 10000
    finally:
        # Restore the module to its unpatched (default-env) state so we do not
        # leak a monkeypatched constant into other tests in the session.
        monkeypatch.delenv("PG_LIVE_CONTENT_MAX", raising=False)
        importlib.reload(reloaded)
