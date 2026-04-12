"""
Mesh CLI — thin presentation layer over mesh operations.

v1 design (CP-A lock):

  6 commands using argparse (no external deps):
    workspace-create, workspace-list, ask, ingest, stats, entities-review

  Each command function opens a MeshStore, calls the relevant mesh
  function, prints the result, and closes the store. No business
  logic in the CLI — it's purely presentation.

  The `ask` command uses `asyncio.run()` to call the async `ask()`
  orchestrator. A `--dry-run` flag skips the LLM call and prints
  the retrieval result directly (testable without network).

  Snapshots deferred to Unit 10. Config layer deferred. `--workspace`
  required on commands that need it (no "active workspace" state).

Usage:
    python -m src.polaris_graph.wiki.mesh.cli.main workspace-create "PFAS Research"
    python -m src.polaris_graph.wiki.mesh.cli.main workspace-list
    python -m src.polaris_graph.wiki.mesh.cli.main ask "How does GAC remove PFOS?" --workspace ws_abc
    python -m src.polaris_graph.wiki.mesh.cli.main ingest paper.pdf --workspace ws_abc
    python -m src.polaris_graph.wiki.mesh.cli.main stats --workspace ws_abc
    python -m src.polaris_graph.wiki.mesh.cli.main entities-review --workspace ws_abc
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

DEFAULT_DB_PATH = os.getenv("PG_MESH_DB", "mesh.db")


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code (0=success, 1=error)."""
    parser = argparse.ArgumentParser(
        prog="polaris-mesh",
        description="POLARIS persistent wiki mesh CLI",
    )
    parser.add_argument(
        "--db", default=DEFAULT_DB_PATH,
        help=f"Path to mesh.db (default: {DEFAULT_DB_PATH})",
    )
    sub = parser.add_subparsers(dest="command")

    # workspace-create
    p_wsc = sub.add_parser("workspace-create", help="Create a new workspace")
    p_wsc.add_argument("name", help="Workspace name")
    p_wsc.add_argument("--seed", default=None, help="Initial root question")

    # workspace-list
    sub.add_parser("workspace-list", help="List all workspaces")

    # ask
    p_ask = sub.add_parser("ask", help="Ask a question")
    p_ask.add_argument("question", help="The question to ask")
    p_ask.add_argument("--workspace", required=True, help="Workspace ID")
    p_ask.add_argument("--thread", default=None, help="Parent question ID for follow-ups")
    p_ask.add_argument("--dry-run", action="store_true", help="Retrieve only, skip LLM compose")

    # ingest
    p_ing = sub.add_parser("ingest", help="Ingest a file into the mesh")
    p_ing.add_argument("file", help="Path to file (PDF/HTML/markdown/text)")
    p_ing.add_argument("--workspace", required=True, help="Workspace ID")
    p_ing.add_argument("--url", default=None, help="Source URL for attribution")

    # stats
    p_stat = sub.add_parser("stats", help="Show workspace statistics")
    p_stat.add_argument("--workspace", required=True, help="Workspace ID")

    # entities-review
    p_ent = sub.add_parser("entities-review", help="Review quarantined entities")
    p_ent.add_argument("--workspace", required=True, help="Workspace ID")

    # snapshot-create
    p_snap_c = sub.add_parser("snapshot-create", help="Create a zstd-compressed snapshot")
    p_snap_c.add_argument("--snapshot-dir", default="snapshots", help="Snapshot directory")

    # snapshot-list
    p_snap_l = sub.add_parser("snapshot-list", help="List available snapshots")
    p_snap_l.add_argument("--snapshot-dir", default="snapshots", help="Snapshot directory")

    # snapshot-restore
    p_snap_r = sub.add_parser("snapshot-restore", help="Restore from a snapshot")
    p_snap_r.add_argument("path", help="Path to .mesh.zst snapshot file")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    dispatch = {
        "workspace-create": cmd_workspace_create,
        "workspace-list": cmd_workspace_list,
        "ask": cmd_ask,
        "ingest": cmd_ingest,
        "stats": cmd_stats,
        "entities-review": cmd_entities_review,
        "snapshot-create": cmd_snapshot_create,
        "snapshot-list": cmd_snapshot_list,
        "snapshot-restore": cmd_snapshot_restore,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    try:
        return handler(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


# ───── command handlers ─────

def cmd_workspace_create(args: argparse.Namespace) -> int:
    from ..store import MeshStore
    store = MeshStore.open(Path(args.db))
    try:
        ws_id = store.create_workspace(
            name=args.name,
            root_question=args.seed,
        )
        print(f"Created workspace: {ws_id}")
        print(f"  Name: {args.name}")
        if args.seed:
            print(f"  Seed question: {args.seed}")
    finally:
        store.close()
    return 0


def cmd_workspace_list(args: argparse.Namespace) -> int:
    from ..store import MeshStore
    store = MeshStore.open(Path(args.db))
    try:
        rows = store._conn.execute(
            "SELECT id, name, root_question, source_count, claim_count, "
            "created_at FROM workspaces ORDER BY created_at DESC"
        ).fetchall()
        if not rows:
            print("No workspaces found.")
            return 0
        for row in rows:
            print(f"{row['id']}  {row['name']}")
            print(f"  Sources: {row['source_count']}  "
                  f"Claims: {row['claim_count']}  "
                  f"Created: {row['created_at']}")
            if row["root_question"]:
                print(f"  Seed: {row['root_question']}")
    finally:
        store.close()
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    from ..qa.ask import ask
    from ..retrieve.lethal import lethal_retrieve
    from ..store import MeshStore

    store = MeshStore.open(Path(args.db))
    try:
        if args.dry_run:
            result = lethal_retrieve(
                store,
                workspace_id=args.workspace,
                question_text=args.question,
            )
            print(f"Gap: {result.gap_category}")
            print(f"Seed: {result.seed_count}  "
                  f"Entity expansion: {result.entity_expansion_count}  "
                  f"Walk: {result.walked_count}  "
                  f"Exploration: {result.exploration_count}")
            print(f"Total claims: {len(result.scored_claims)}")
            for i, (cid, score) in enumerate(result.scored_claims[:10]):
                claim = store.get_claim(cid)
                stmt = claim["statement"][:80] if claim else "?"
                print(f"  {i+1}. [{score:.3f}] {stmt}")
            return 0

        client = _make_llm_client()
        result = asyncio.run(ask(
            client, store,
            workspace_id=args.workspace,
            question_text=args.question,
            parent_question_id=args.thread,
        ))
        print(f"\n{result.answer_text}\n")
        if result.bibliography:
            print("--- Bibliography ---")
            for entry in result.bibliography:
                print(f"[{entry['ref_num']}] {entry.get('title', 'Untitled')} "
                      f"({entry.get('year', '?')}) — {entry.get('url', '')}")
        print(f"\nGap: {result.gap_category}  "
              f"Claims used: {len(result.claim_ids_used)}")
    finally:
        store.close()
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from ..ingest import ingest_file
    from ..store import MeshStore

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 1

    store = MeshStore.open(Path(args.db))
    try:
        src_id, was_new = ingest_file(
            store=store,
            workspace_id=args.workspace,
            file_path=file_path,
            kind="upload",
            url=args.url,
        )
        status = "Ingested (new)" if was_new else "Already exists (dedup)"
        print(f"{status}: {src_id}")
        print(f"  File: {file_path.name}")
    finally:
        store.close()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from ..store import MeshStore
    store = MeshStore.open(Path(args.db))
    try:
        stats = store.workspace_stats(args.workspace)
        print(f"Workspace: {stats['name']} ({stats['id']})")
        print(f"  Sources: {stats['source_count']}")
        print(f"  Claims: {stats['claim_count']} "
              f"(GOLD: {stats['gold_claims']}, "
              f"SILVER: {stats['silver_claims']}, "
              f"BRONZE: {stats['bronze_claims']})")
        print(f"  Flagged: {stats['flagged_claims']}")
        print(f"  Quarantined entities: {stats['quarantined_entities']}")
        print(f"  Edges: {stats['edge_count']}")
    finally:
        store.close()
    return 0


def cmd_entities_review(args: argparse.Namespace) -> int:
    from ..store import MeshStore
    store = MeshStore.open(Path(args.db))
    try:
        quarantined = store.get_quarantined_entities(args.workspace)
        if not quarantined:
            print("No quarantined entities. All entities are confirmed.")
            return 0
        print(f"{len(quarantined)} quarantined entities "
              f"(confidence < 0.8, not confirmed):\n")
        for ent in quarantined:
            aliases_raw = ent.get("aliases", "[]")
            try:
                aliases = json.loads(aliases_raw) if aliases_raw else []
            except (ValueError, TypeError):
                aliases = []
            alias_str = ", ".join(aliases[:3]) if aliases else "(none)"
            print(f"  {ent['id']}  {ent['canonical_name']}")
            print(f"    Type: {ent['entity_type']}  "
                  f"Confidence: {ent['confidence']:.2f}  "
                  f"Referenced: {ent.get('times_referenced', 0)}x")
            print(f"    Aliases: {alias_str}")
    finally:
        store.close()
    return 0


def cmd_snapshot_create(args: argparse.Namespace) -> int:
    from ..snapshot import create_snapshot
    path = create_snapshot(args.db, args.snapshot_dir)
    print(f"Snapshot created: {path}")
    print(f"  Size: {path.stat().st_size / 1024:.1f} KB")
    return 0


def cmd_snapshot_list(args: argparse.Namespace) -> int:
    from ..snapshot import list_snapshots
    snapshots = list_snapshots(args.snapshot_dir)
    if not snapshots:
        print("No snapshots found.")
        return 0
    for s in snapshots:
        size_kb = s["size_bytes"] / 1024
        print(f"  {s['name']}  ({size_kb:.1f} KB)")
    return 0


def cmd_snapshot_restore(args: argparse.Namespace) -> int:
    from ..snapshot import restore_snapshot
    restore_snapshot(args.path, args.db)
    print(f"Restored: {args.path} → {args.db}")
    return 0


# ───── LLM client factory ─────

def _make_llm_client():
    """
    Construct an LLM client for the ask command. Uses OpenRouterClient
    from the production pipeline if available, otherwise raises.
    """
    try:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        return OpenRouterClient()
    except ImportError:
        raise RuntimeError(
            "OpenRouterClient not available. Use --dry-run for "
            "retrieval-only mode without LLM."
        )


if __name__ == "__main__":
    sys.exit(main())
