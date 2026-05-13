"""Test-level setup for tests/polaris_v6/ (mirrors tests/v6/conftest.py).

I-carney-004: create_app() invokes verify_app_startup() which raises on
missing POLARIS_JWT_SECRET / static_accounts.yaml. Default tests/ to
auth-disabled mode; individual auth tests opt back in via
`monkeypatch.delenv("POLARIS_AUTH_DISABLED")`.
"""

from __future__ import annotations

import os

os.environ.setdefault("POLARIS_AUTH_DISABLED", "1")
os.environ.setdefault("POLARIS_V6_QUEUE_USE_STUB", "1")
