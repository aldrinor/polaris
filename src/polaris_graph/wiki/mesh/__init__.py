"""
POLARIS wiki mesh — persistent research graph.

This package implements the persistent wiki mesh described in
docs/wiki_mesh_design.md. The mesh is a single-file SQLite database
(via sqlite-vec for vector similarity) that holds:

- Source pages (the raw markdown layer)
- Claims (atomic factual statements extracted from sources)
- Edges (corroborates / contradicts / elaborates / cites)
- Entities (canonical things the claims are about)
- Topics (emergent clusters)
- Questions and answers (Q&A history)
- Feedback (drives bounded snowball reinforcement)

Unit 1 exports:
    MeshStore   — CRUD layer over a mesh.db file
    MeshStoreError — raised on unrecoverable errors
    create_schema — DDL runner (re-exported from .schema)
"""

from .schema import SCHEMA_VERSION, create_schema
from .store import MeshStore, MeshStoreError

__all__ = ["MeshStore", "MeshStoreError", "create_schema", "SCHEMA_VERSION"]
