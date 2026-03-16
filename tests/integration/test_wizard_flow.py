"""
Integration tests for the pipeline wizard engine and wizard API endpoints.

Tests REAL code paths through:
  - src/polaris_graph/pipeline_wizard.py (PipelineWizard, _sessions, STAGE_CHIPS)
  - scripts/live_server.py wizard API endpoints (/api/wizard/*)

Zero mocks. Zero placeholders. All assertions against real wizard logic
and live ASGI transport.
"""

import sys
from pathlib import Path

import pytest
import pytest_asyncio
import httpx

# Ensure project root is on sys.path for src.* and scripts.* imports
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.polaris_graph.pipeline_wizard import (
    PipelineWizard,
    STAGE_CHIPS,
    WIZARD_STAGES,
    _sessions,
)


# ---------------------------------------------------------------------------
# The 6 canonical user messages that drive a wizard to completion.
# Each message corresponds to one wizard stage.
# ---------------------------------------------------------------------------
FULL_FLOW_MESSAGES = [
    "PFAS water contamination research",       # problem
    "Web + Academic sources",                   # sources
    "Comprehensive analysis with 50 queries",   # analysis
    "Strict 85% verification",                  # verification
    "Standard 8-12K words, DOCX export",        # output
    "60 minutes, English only",                 # constraints
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def wizard_engine():
    """Fresh PipelineWizard instance with a clean global session store."""
    _sessions.clear()
    return PipelineWizard()


@pytest_asyncio.fixture
async def client():
    """Real ASGI client hitting real FastAPI wizard endpoints."""
    import scripts.live_server as srv

    # Also clear wizard sessions to isolate API tests
    from src.polaris_graph.pipeline_wizard import _sessions as wiz_sessions
    wiz_sessions.clear()
    srv._custom_pipelines.clear()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=srv.app),
        base_url="http://testserver",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. start_session returns session_id, stage="problem", response text
# ---------------------------------------------------------------------------


def test_start_session_returns_valid_structure(wizard_engine):
    """start_session() returns session_id (wiz_ prefix), stage=problem, response text."""
    result = wizard_engine.start_session()
    assert "session_id" in result
    assert result["session_id"].startswith("wiz_")
    assert result["stage"] == "problem"
    assert result["stage_label"] == "Problem Understanding"
    assert result["completion_pct"] == 0.0
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 20
    assert result["pipeline_draft"] is None


# ---------------------------------------------------------------------------
# 2. chat advances to next stage (problem -> sources)
# ---------------------------------------------------------------------------


def test_chat_advances_stage(wizard_engine):
    """After one chat message, wizard advances from problem to sources."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    result = wizard_engine.chat(sid, "Investigate PFAS contamination in water")
    assert result["stage"] == "sources"
    assert result["stage_label"] == "Data Sources"
    assert result["completion_pct"] > 0.0
    assert result["pipeline_draft"] is None


# ---------------------------------------------------------------------------
# 3. Progress through all 6 stages to completion
# ---------------------------------------------------------------------------


def test_full_wizard_flow(wizard_engine):
    """Progressing through all 6 stages yields stage=complete with a pipeline draft."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    result = None
    for msg in FULL_FLOW_MESSAGES:
        result = wizard_engine.chat(sid, msg)

    assert result is not None
    assert result["stage"] == "complete"
    assert result["completion_pct"] == 100.0
    assert result["pipeline_draft"] is not None

    draft = result["pipeline_draft"]
    assert draft["name"]
    assert len(draft["macro_stages"]) >= 3


# ---------------------------------------------------------------------------
# 4. Each stage returns chips from STAGE_CHIPS
# ---------------------------------------------------------------------------


def test_each_stage_returns_chips(wizard_engine):
    """Every non-complete stage returns the correct chips list from STAGE_CHIPS."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    # Start already returns chips for "problem"
    assert start["chips"] == STAGE_CHIPS["problem"]

    for i, msg in enumerate(FULL_FLOW_MESSAGES[:-1]):
        result = wizard_engine.chat(sid, msg)
        stage = result["stage"]
        if stage != "complete":
            assert result["chips"] == STAGE_CHIPS[stage], (
                f"Stage '{stage}' chips mismatch"
            )

    # Final message yields complete with empty chips
    result = wizard_engine.chat(sid, FULL_FLOW_MESSAGES[-1])
    assert result["stage"] == "complete"
    assert result["chips"] == []


# ---------------------------------------------------------------------------
# 5. After all 6 stages, pipeline_draft is not None
# ---------------------------------------------------------------------------


def test_pipeline_draft_after_completion(wizard_engine):
    """After completing all stages, pipeline_draft contains a valid structure."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    result = None
    for msg in FULL_FLOW_MESSAGES:
        result = wizard_engine.chat(sid, msg)

    draft = result["pipeline_draft"]
    assert draft is not None
    assert "pipeline_id" in draft
    assert "macro_stages" in draft
    assert isinstance(draft["macro_stages"], list)
    assert all("stages" in m for m in draft["macro_stages"])


# ---------------------------------------------------------------------------
# 6. get_draft returns PipelineDefinition dict after completion
# ---------------------------------------------------------------------------


def test_get_draft_after_completion(wizard_engine):
    """get_draft() returns the full pipeline definition dict after wizard completes."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    # Before completion, no draft
    assert wizard_engine.get_draft(sid) is None

    for msg in FULL_FLOW_MESSAGES:
        wizard_engine.chat(sid, msg)

    draft = wizard_engine.get_draft(sid)
    assert draft is not None
    assert "pipeline_id" in draft
    assert "macro_stages" in draft
    assert len(draft["macro_stages"]) >= 3


# ---------------------------------------------------------------------------
# 7. finalize marks session as finalized, returns pipeline_id
# ---------------------------------------------------------------------------


def test_finalize_session(wizard_engine):
    """finalize() returns pipeline data and marks session as finalized."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    for msg in FULL_FLOW_MESSAGES:
        wizard_engine.chat(sid, msg)

    finalized = wizard_engine.finalize(sid)
    assert finalized is not None
    assert "pipeline_id" in finalized

    # Session should now be marked finalized
    session_state = wizard_engine.get_session(sid)
    assert session_state["finalized"] is True


# ---------------------------------------------------------------------------
# 8. Invalid session_id returns error dict
# ---------------------------------------------------------------------------


def test_invalid_session_id(wizard_engine):
    """chat() with a nonexistent session_id returns an error dict."""
    result = wizard_engine.chat("nonexistent_session_xyz", "Hello")
    assert "error" in result
    assert "not found" in result["error"].lower()


# ---------------------------------------------------------------------------
# 9. Empty message -- chat still processes (no crash)
# ---------------------------------------------------------------------------


def test_empty_message_no_crash(wizard_engine):
    """Sending an empty string message does not crash; wizard advances normally."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    result = wizard_engine.chat(sid, "")
    # Should advance to sources stage even with empty message
    assert result["stage"] == "sources"
    assert "error" not in result


# ---------------------------------------------------------------------------
# 10. Chat after finalize returns error
# ---------------------------------------------------------------------------


def test_chat_after_finalize_returns_error(wizard_engine):
    """Sending a message after finalize() returns an error."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    for msg in FULL_FLOW_MESSAGES:
        wizard_engine.chat(sid, msg)
    wizard_engine.finalize(sid)

    result = wizard_engine.chat(sid, "Another message after finalize")
    assert "error" in result
    assert "finalized" in result["error"].lower()


# ---------------------------------------------------------------------------
# 11. "academic" keyword -> pipeline includes academic tag
# ---------------------------------------------------------------------------


def test_academic_keyword_produces_academic_tag(wizard_engine):
    """Using 'academic' in sources stage produces an 'academic' tag in the pipeline."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    messages = [
        "Literature review on machine learning",
        "Academic papers and peer-reviewed sources only",
        "Comprehensive with citation chasing",
        "Standard 80% verification",
        "Standard 8-12K words",
        "60 minutes",
    ]
    result = None
    for msg in messages:
        result = wizard_engine.chat(sid, msg)

    assert result["stage"] == "complete"
    draft = result["pipeline_draft"]
    assert "academic" in draft["tags"], f"Expected 'academic' in tags, got {draft['tags']}"


# ---------------------------------------------------------------------------
# 12. "quick" keyword -> fewer stages, quick tag
# ---------------------------------------------------------------------------


def test_quick_keyword_produces_quick_pipeline(wizard_engine):
    """Using 'quick' in constraints produces a 'quick' tag and fewer macro stages."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    messages = [
        "Quick overview of solar panel efficiency",
        "Web only",
        "Focused 20 queries",
        "Standard verification",
        "Short 2-4K words",
        "15 minutes quick scan",
    ]
    result = None
    for msg in messages:
        result = wizard_engine.chat(sid, msg)

    assert result["stage"] == "complete"
    draft = result["pipeline_draft"]
    assert "quick" in draft["tags"], f"Expected 'quick' in tags, got {draft['tags']}"
    # Quick pipelines skip the verification macro-stage
    macro_ids = [m["macro_id"] for m in draft["macro_stages"]]
    assert "verification" not in macro_ids, (
        "Quick pipeline should skip verification macro-stage"
    )


# ---------------------------------------------------------------------------
# 13. "compliance" keyword -> compliance tag, strict faithfulness
# ---------------------------------------------------------------------------


def test_compliance_keyword_produces_compliance_pipeline(wizard_engine):
    """Using 'compliance' in problem stage produces compliance tag and strict config."""
    start = wizard_engine.start_session()
    sid = start["session_id"]

    messages = [
        "Compliance review of GDPR data retention policies",
        "Web + Academic sources",
        "Comprehensive with expert interviews",
        "Maximum 90% verification",
        "Standard 8-12K words",
        "60 minutes, English only",
    ]
    result = None
    for msg in messages:
        result = wizard_engine.chat(sid, msg)

    assert result["stage"] == "complete"
    draft = result["pipeline_draft"]
    assert "compliance" in draft["tags"], f"Expected 'compliance' in tags, got {draft['tags']}"
    # Compliance pipelines should set strict faithfulness
    overrides = draft.get("config_overrides", {})
    if "PG_MIN_FAITHFULNESS" in overrides:
        assert float(overrides["PG_MIN_FAITHFULNESS"]) >= 0.85


# ---------------------------------------------------------------------------
# 14. Concurrent sessions (2 wizards simultaneously)
# ---------------------------------------------------------------------------


def test_concurrent_sessions(wizard_engine):
    """Two wizard sessions can run in parallel without cross-contamination."""
    start_a = wizard_engine.start_session()
    start_b = wizard_engine.start_session()

    sid_a = start_a["session_id"]
    sid_b = start_b["session_id"]
    assert sid_a != sid_b

    # Advance session A through 3 stages
    wizard_engine.chat(sid_a, "Topic A: quantum computing")
    wizard_engine.chat(sid_a, "Academic sources")
    result_a = wizard_engine.chat(sid_a, "50 queries comprehensive")

    # Session B is still at problem stage
    session_b = wizard_engine.get_session(sid_b)
    assert session_b["stage"] == "problem"
    assert session_b["stage_index"] == 0

    # Session A should be at verification
    assert result_a["stage"] == "verification"

    # Advance session B differently
    wizard_engine.chat(sid_b, "Topic B: renewable energy")
    result_b = wizard_engine.chat(sid_b, "Web only")
    assert result_b["stage"] == "analysis"

    # Verify collected data is isolated
    session_a_data = wizard_engine.get_session(sid_a)
    session_b_data = wizard_engine.get_session(sid_b)
    assert "quantum" in session_a_data["collected"]["problem"].lower()
    assert "renewable" in session_b_data["collected"]["problem"].lower()


# ---------------------------------------------------------------------------
# 15. API round-trip: POST /start -> POST /chat (6x) -> GET /draft -> POST /finalize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_full_round_trip(client):
    """Full wizard round-trip through the HTTP API layer."""
    # Start session
    start_resp = await client.post("/api/wizard/start")
    assert start_resp.status_code == 200
    start_data = start_resp.json()
    sid = start_data["session_id"]
    assert sid.startswith("wiz_")
    assert start_data["stage"] == "problem"

    # Chat through all 6 stages
    last_result = None
    for msg in FULL_FLOW_MESSAGES:
        chat_resp = await client.post(
            f"/api/wizard/chat/{sid}",
            json={"message": msg},
        )
        assert chat_resp.status_code == 200
        last_result = chat_resp.json()

    assert last_result["stage"] == "complete"
    assert last_result["pipeline_draft"] is not None

    # Get draft via API
    draft_resp = await client.get(f"/api/wizard/draft/{sid}")
    assert draft_resp.status_code == 200
    draft_data = draft_resp.json()
    assert "pipeline_id" in draft_data
    assert "macro_stages" in draft_data

    # Finalize via API
    finalize_resp = await client.post(f"/api/wizard/finalize/{sid}")
    assert finalize_resp.status_code == 200
    finalize_data = finalize_resp.json()
    assert finalize_data["status"] == "finalized"
    pipeline_id = finalize_data["pipeline_id"]

    # Verify pipeline was saved to custom pipelines store
    # It should now appear in GET /api/pipelines
    pipelines_resp = await client.get("/api/pipelines")
    assert pipelines_resp.status_code == 200
    all_ids = [p["pipeline_id"] for p in pipelines_resp.json()["pipelines"]]
    assert pipeline_id in all_ids, (
        f"Finalized pipeline {pipeline_id} not found in pipelines list"
    )
