"""Insert the /api/auth/history endpoint into live_server.py."""

from pathlib import Path

SERVER_PATH = Path(__file__).parent / "live_server.py"

content = SERVER_PATH.read_text(encoding="utf-8")

# Check if already applied
if "get_auth_history" in content:
    print("Auth history endpoint already exists, skipping.")
else:
    history_route = '''

# ---------------------------------------------------------------------------
# Authenticated research history endpoint (2B.1)
# ---------------------------------------------------------------------------
@app.get("/api/auth/history")
async def get_auth_history(request: Request):
    """Get research history for the authenticated user.

    Falls back to listing recent result files if session manager is unavailable.
    """
    # Try to get user from auth header
    user_id = "anonymous"
    if _AUTH_AVAILABLE and get_current_user is not None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from src.auth.auth_middleware import get_auth_manager
                auth_mgr = get_auth_manager()
                token = auth_header.split(" ", 1)[1]
                payload = auth_mgr.verify_token(token)
                if payload:
                    user_id = payload.get("user_id", payload.get("sub", "anonymous"))
            except Exception:
                pass

    # Try session manager first
    try:
        from src.auth.session_manager import SessionManager
        sm = SessionManager()
        history = sm.get_user_history(user_id, limit=50)
        return JSONResponse(history)
    except Exception:
        pass

    # Fallback: list recent result files
    results_dir = Path("outputs/polaris_graph")
    if not results_dir.exists():
        return JSONResponse([])

    result_files = sorted(
        results_dir.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    history = []
    for f in result_files[:20]:
        if f.name.endswith("_report.md"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            history.append({
                "vector_id": f.stem,
                "query": data.get("original_query", data.get("query", "")),
                "status": data.get("status", "unknown"),
                "created_at": f.stat().st_mtime,
                "depth": data.get("depth", "standard"),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return JSONResponse(history)

'''

    target = (
        '    logger.info("Auth routes: disabled (module not available or POLARIS_AUTH_ENABLED=0)")\n'
        '\n\n'
        '# ---------------------------------------------------------------------------\n'
        '# Global Exception Handler'
    )

    replacement = (
        '    logger.info("Auth routes: disabled (module not available or POLARIS_AUTH_ENABLED=0)")\n'
        + history_route
        + '\n# ---------------------------------------------------------------------------\n'
        '# Global Exception Handler'
    )

    if target in content:
        content = content.replace(target, replacement, 1)
        SERVER_PATH.write_text(content, encoding="utf-8")
        print("Auth history endpoint inserted successfully.")
    else:
        print("ERROR: Could not find insertion point for auth history endpoint.")
        print("Looking for alternative insertion point...")
        # Try alternative
        alt_target = 'logger.info("Auth routes: disabled (module not available or POLARIS_AUTH_ENABLED=0)")'
        if alt_target in content:
            content = content.replace(
                alt_target,
                alt_target + history_route,
                1,
            )
            SERVER_PATH.write_text(content, encoding="utf-8")
            print("Auth history endpoint inserted (alternative method).")
        else:
            print("FAILED: Could not find any insertion point.")
