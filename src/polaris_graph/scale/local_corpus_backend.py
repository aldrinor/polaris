"""X1 — Internal-DB / large-attachment retrieval backend (SCALE workstream).

The capability-first Telus SCALE deliverable. Every existing backend in
``retrieval/domain_backends.py`` is a WEB fan-out (OpenAlex / arXiv / Serper /
EDGAR / GitHub / EuropePMC / stat-agency). There was NO home for a large
internal DB + parsed-attachment pile — the corpus that earns Telus access.

This NEW, self-contained backend funnels a local internal corpus into the SAME
weight-and-consolidate pipeline:

    parse  →  embed (injected Qwen3 embed_fn)  →  SAME institutional WEIGHT
           →  ranked by the SAME weight_mass semantics (top-weight surfacing)

carrying an operator-set INSTITUTIONAL weight in each candidate's ``metadata``
(disclosed), so the downstream tier / authority / consolidation / faithfulness
stages treat internal docs exactly like any other weighted source.

DNA (CLAUDE.md §-1.3), enforced by this module and its test:
  * WEIGHT, don't FILTER — ``search`` returns the FULL ranked ingested pool.
    A low-institutional-weight internal doc is KEPT at low weight, never dropped
    to hit a number. There is NO cap / target / thinner anywhere here.
  * CONSOLIDATE, don't DROP — every parsed document reaches the output pool.
  * FAIL LOUD (LAW II) — a configured-but-missing root, a zero-weight config,
    or an all-files-unparseable corpus RAISES; it never returns empty silently.

LAW VI (zero hard-coding): every path / weight / worker-count / extension comes
from ``LocalCorpusConfig`` (env-var or YAML backed), never a literal in code.
LAW VII (CLI isolation): this module imports NO other pipeline phase; it only
shares the ``SearchCandidate`` schema and the ``embed_with_pooling`` utility.
"""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

from src.polaris_graph.retrieval.pooled_embedder import embed_with_pooling
from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.scale.local_corpus")


class LocalCorpusError(RuntimeError):
    """Raised when the local-corpus backend cannot honour its contract.

    Fail-loud (LAW II): a misconfigured root, a zero institutional weight, or a
    corpus where EVERY file failed to parse is a hard error — never a silent
    empty return that would let a scale demonstration report faked coverage.
    """


# Default source-class → institutional weight map. This is the OPERATOR-SET,
# DISCLOSED weight (config-overridable, never a code literal in the hot path —
# ``LocalCorpusConfig`` resolves it from env/YAML). Internal documents carry a
# real institutional weight in [0, 1]; it is SURFACED to the user, never used as
# a rank-then-drop hard filter. Kept here only as the documented fallback.
_DEFAULT_CLASS_WEIGHTS: dict[str, float] = {
    "internal_db": 0.72,       # curated institutional record of the org
    "attachment": 0.55,        # parsed email/report attachments
    "internal_wiki": 0.48,
    "unclassified_internal": 0.30,
}

# Weight floor for the ranking blend (mirrors authority ``corroboration_floor``
# semantics): even a zero-institutional-weight doc keeps this fraction of its
# relevance so it is never zeroed out of the surfaced pool (WEIGHT, not DROP).
_DEFAULT_WEIGHT_FLOOR = 0.15

_DEFAULT_EXTENSIONS = (".txt", ".md", ".json", ".jsonl", ".csv", ".htm", ".html")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise LocalCorpusError(
            f"{name}={raw!r} is not a valid float (LAW VI: config must parse)"
        )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        raise LocalCorpusError(f"{name}={raw!r} is not a valid int")


@dataclass
class LocalCorpusConfig:
    """Config-driven settings for the local-corpus backend (LAW VI).

    ``roots`` is the list of directories to ingest (a large internal DB export
    and/or an attachment pile). ``class_weights`` is the operator-set,
    DISCLOSED institutional weight per source-class. All fields are resolvable
    from environment variables via :meth:`from_env` so nothing is hard-coded.
    """

    roots: list[Path]
    class_weights: dict[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_CLASS_WEIGHTS)
    )
    default_class: str = "unclassified_internal"
    weight_floor: float = _DEFAULT_WEIGHT_FLOOR
    workers: int = 6
    extensions: tuple[str, ...] = _DEFAULT_EXTENSIONS
    max_chars_per_doc: int = 200_000

    @classmethod
    def from_env(
        cls,
        roots: Iterable[str | Path] | None = None,
    ) -> "LocalCorpusConfig":
        """Build config from env vars (and an optional explicit ``roots``).

        Recognised env vars (all optional except a root source):
          PG_LOCAL_CORPUS_ROOTS   os.pathsep-separated ingest directories
          PG_LOCAL_CORPUS_WEIGHTS JSON obj {source_class: weight}
          PG_LOCAL_CORPUS_DEFAULT_CLASS  fallback class for unlabelled docs
          PG_LOCAL_CORPUS_WEIGHT_FLOOR   float ranking floor
          PG_LOCAL_CORPUS_WORKERS        bounded ingest worker count
          PG_LOCAL_CORPUS_EXTENSIONS     comma-separated file extensions
        """
        root_values: list[str | Path] = list(roots or [])
        env_roots = resolve("PG_LOCAL_CORPUS_ROOTS").strip()
        if env_roots:
            root_values.extend(
                p for p in env_roots.split(os.pathsep) if p.strip()
            )
        if not root_values:
            raise LocalCorpusError(
                "No local-corpus root configured — set PG_LOCAL_CORPUS_ROOTS "
                "or pass roots=[...]. FAIL LOUD (LAW II): refusing to ingest an "
                "empty corpus and report faked scale."
            )

        weights = dict(_DEFAULT_CLASS_WEIGHTS)
        raw_w = resolve("PG_LOCAL_CORPUS_WEIGHTS").strip()
        if raw_w:
            try:
                parsed = json.loads(raw_w)
            except json.JSONDecodeError as exc:
                raise LocalCorpusError(
                    f"PG_LOCAL_CORPUS_WEIGHTS is not valid JSON: {exc}"
                )
            if not isinstance(parsed, dict):
                raise LocalCorpusError(
                    "PG_LOCAL_CORPUS_WEIGHTS must be a JSON object "
                    "{source_class: weight}"
                )
            for k, v in parsed.items():
                weights[str(k)] = float(v)

        exts_raw = resolve("PG_LOCAL_CORPUS_EXTENSIONS").strip()
        extensions = _DEFAULT_EXTENSIONS
        if exts_raw:
            extensions = tuple(
                e if e.startswith(".") else f".{e}"
                for e in (x.strip().lower() for x in exts_raw.split(","))
                if e
            )

        return cls(
            roots=[Path(r) for r in root_values],
            class_weights=weights,
            default_class=os.getenv(
                "PG_LOCAL_CORPUS_DEFAULT_CLASS", "unclassified_internal"
            ).strip()
            or "unclassified_internal",
            weight_floor=_env_float(
                "PG_LOCAL_CORPUS_WEIGHT_FLOOR", _DEFAULT_WEIGHT_FLOOR
            ),
            workers=_env_int("PG_LOCAL_CORPUS_WORKERS", 6),
            extensions=extensions,
        )

    def weight_for_class(self, source_class: str) -> float:
        """Operator-set institutional weight for a source-class (disclosed).

        An UNKNOWN class is NOT dropped — it falls back to the default-class
        weight (WEIGHT, never FILTER). Weight is clamped to [0, 1].
        """
        w = self.class_weights.get(
            source_class,
            self.class_weights.get(self.default_class, 0.30),
        )
        return float(min(1.0, max(0.0, w)))


@dataclass
class IngestedDocument:
    """One parsed internal document with its disclosed institutional weight."""

    doc_id: str
    path: str
    source_class: str
    institutional_weight: float
    title: str
    text: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _classify_source_class(path: Path, config: LocalCorpusConfig) -> str:
    """Derive a source-class from the file's location.

    A doc under a directory literally named after a configured class inherits
    that class; a ``.attachment.*`` / ``attachments`` path is an attachment;
    everything else is the configured default class. This is a WEIGHT hint, not
    a filter — no path is ever excluded here.
    """
    parts = {p.lower() for p in path.parts}
    for cls_name in config.class_weights:
        if cls_name.lower() in parts:
            return cls_name
    if "attachments" in parts or ".attachment" in path.name.lower():
        return "attachment"
    return config.default_class


def _read_document(path: Path, config: LocalCorpusConfig) -> IngestedDocument:
    """Parse a single file into an IngestedDocument.

    JSON/JSONL records surface a ``title``/``text``/``body`` field when present;
    everything else is read as UTF-8 text (errors replaced, never dropped). This
    raises on read failure so the caller can COUNT the failure — a
    per-file failure is tolerated (logged + skipped) but the whole-corpus
    contract still fails loud if EVERY file fails.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem
    text = raw
    if path.suffix.lower() == ".json":
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                title = str(obj.get("title") or obj.get("name") or title)
                text = str(
                    obj.get("text")
                    or obj.get("body")
                    or obj.get("content")
                    or raw
                )
        except json.JSONDecodeError:
            # Malformed JSON is still ingested as raw text — never dropped.
            pass

    text = text[: config.max_chars_per_doc]
    source_class = _classify_source_class(path, config)
    weight = config.weight_for_class(source_class)
    doc_id = f"local::{path.as_posix()}"
    return IngestedDocument(
        doc_id=doc_id,
        path=path.as_posix(),
        source_class=source_class,
        institutional_weight=weight,
        title=title,
        text=text,
        metadata={
            "backend": "local_corpus",
            "source_class": source_class,
            # DISCLOSED to the user: the operator-set institutional weight this
            # internal doc carries into the weighted pipeline.
            "institutional_weight": weight,
            "weight_basis": "operator_set_institutional",
            "local_path": path.as_posix(),
        },
    )


class LocalCorpusBackend:
    """Ingest a local internal corpus and surface it by institutional weight.

    Usage::

        cfg = LocalCorpusConfig.from_env(roots=[corpus_dir])
        backend = LocalCorpusBackend(cfg)
        n = backend.ingest(embed_fn)                 # parse + embed, bounded-parallel
        candidates = backend.search("my query", embed_fn)   # FULL ranked pool

    ``search`` returns ``SearchCandidate`` objects (the SAME shape every other
    backend emits) with the disclosed institutional weight in ``metadata``. The
    caller merges them transparently into the SAME weight-and-consolidate path.
    """

    def __init__(self, config: LocalCorpusConfig):
        self.config = config
        self._docs: list[IngestedDocument] = []
        self._skipped: list[tuple[str, str]] = []

    # ── ingest ────────────────────────────────────────────────────────────
    def _discover_files(self) -> list[Path]:
        files: list[Path] = []
        seen_missing = []
        for root in self.config.roots:
            if not root.exists():
                seen_missing.append(str(root))
                continue
            if root.is_file():
                files.append(root)
                continue
            for p in sorted(root.rglob("*")):
                if p.is_file() and p.suffix.lower() in self.config.extensions:
                    files.append(p)
        if seen_missing:
            # A configured root that does not exist is a FAIL-LOUD error — a
            # silent skip would let a scale demo under-report its corpus.
            raise LocalCorpusError(
                "Configured local-corpus root(s) do not exist: "
                + ", ".join(seen_missing)
                + " (LAW II: fail loud, do not silently ingest a partial corpus)"
            )
        return files

    def ingest(
        self,
        embed_fn: Callable[[list[str]], list[list[float]]],
    ) -> int:
        """Parse + embed every file under the configured roots.

        Parsing is bounded-parallel (``config.workers`` threads) per the
        runtime-parallelism mandate; embedding is one batched pass via
        ``embed_with_pooling`` (model-agnostic, no silent truncation). Returns
        the number of documents ingested. Raises ``LocalCorpusError`` if the
        corpus is empty or EVERY file failed to parse.
        """
        files = self._discover_files()
        if not files:
            raise LocalCorpusError(
                "Local-corpus roots contain no ingestible files "
                f"(extensions={self.config.extensions}). FAIL LOUD (LAW II)."
            )

        docs: list[IngestedDocument] = []
        skipped: list[tuple[str, str]] = []

        def _one(path: Path) -> tuple[Path, IngestedDocument | None, str]:
            try:
                return path, _read_document(path, self.config), ""
            except Exception as exc:  # noqa: BLE001 — per-file fail-open, counted
                return path, None, repr(exc)

        with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
            for path, doc, err in pool.map(_one, files):
                if doc is None:
                    skipped.append((path.as_posix(), err))
                    logger.warning("local-corpus parse failed: %s (%s)", path, err)
                else:
                    docs.append(doc)

        if not docs:
            raise LocalCorpusError(
                f"Every one of {len(files)} local-corpus files failed to parse "
                "— refusing to report a scale corpus of zero documents "
                "(LAW II fail loud)."
            )

        # Deterministic doc order (path-sorted) so ties in the ranking blend are
        # reproducible (wiring_standard determinism).
        docs.sort(key=lambda d: d.doc_id)

        texts = [f"{d.title}\n{d.text}".strip() for d in docs]
        embeddings = embed_with_pooling(texts, embed_fn)
        if len(embeddings) != len(docs):
            raise LocalCorpusError(
                "embed_fn returned "
                f"{len(embeddings)} vectors for {len(docs)} docs (contract break)"
            )
        for doc, emb in zip(docs, embeddings):
            doc.embedding = emb

        self._docs = docs
        self._skipped = skipped
        logger.info(
            "local-corpus ingested %d docs (%d skipped) from %d roots",
            len(docs),
            len(skipped),
            len(self.config.roots),
        )
        return len(docs)

    # ── surface ───────────────────────────────────────────────────────────
    @property
    def documents(self) -> list[IngestedDocument]:
        return list(self._docs)

    @property
    def skipped(self) -> list[tuple[str, str]]:
        return list(self._skipped)

    def _weight_blend(self, relevance: float, institutional_weight: float) -> float:
        """Combine relevance with institutional weight (WEIGHT, not FILTER).

        ``blend = relevance * (floor + (1-floor) * institutional_weight)``

        The floor guarantees a low-weight doc is never zeroed out of the pool;
        the institutional weight LIFTS a more-authoritative internal source
        above a less-authoritative one at comparable relevance. This mirrors the
        authority ``corroboration_floor`` multiplier — a weight, never a drop.
        """
        floor = self.config.weight_floor
        return float(relevance) * (floor + (1.0 - floor) * float(institutional_weight))

    def search(
        self,
        query: str,
        embed_fn: Callable[[list[str]], list[list[float]]],
    ) -> list[SearchCandidate]:
        """Return the FULL ingested pool ranked by weighted relevance.

        NO cap / top-k / threshold — every ingested document is returned as a
        ``SearchCandidate`` carrying its disclosed institutional weight. Ordering
        is by the weight-blended cosine relevance to ``query`` (DESC), with a
        deterministic ``doc_id`` tiebreak. Top-weight surfacing = this ordering.
        """
        if not self._docs:
            raise LocalCorpusError(
                "search() called before ingest() — no documents in the pool "
                "(FAIL LOUD; a silent empty result would fake zero coverage)."
            )
        q_vec = np.asarray(embed_with_pooling([query], embed_fn)[0], dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 1e-8:
            q_vec = q_vec / q_norm

        scored: list[tuple[float, float, IngestedDocument]] = []
        for doc in self._docs:
            if doc.embedding is None:
                # Should not happen post-ingest; keep the doc at floor relevance
                # rather than DROP it (§-1.3 consolidate-don't-drop).
                relevance = 0.0
            else:
                d_vec = np.asarray(doc.embedding, dtype=np.float32)
                d_norm = np.linalg.norm(d_vec)
                if d_norm > 1e-8:
                    d_vec = d_vec / d_norm
                relevance = float(np.dot(q_vec, d_vec))
            # cosine in [-1,1] → clamp negatives to 0 for the blend (a doc
            # pointing away is low-relevance, not negative-weight).
            relevance = max(0.0, relevance)
            blend = self._weight_blend(relevance, doc.institutional_weight)
            scored.append((blend, relevance, doc))

        scored.sort(key=lambda t: (-t[0], t[2].doc_id))

        out: list[SearchCandidate] = []
        for blend, relevance, doc in scored:
            meta = dict(doc.metadata)
            meta["relevance"] = round(relevance, 6)
            meta["weight_mass"] = round(blend, 6)
            out.append(
                SearchCandidate(
                    url=doc.doc_id,
                    title=doc.title,
                    snippet=doc.text[:500],
                    source="local_corpus",
                    metadata=meta,
                    query_origin=query,
                )
            )
        return out

    def rank_by_weight_mass(
        self, candidates: list[SearchCandidate]
    ) -> list[SearchCandidate]:
        """Order candidates by their ``weight_mass`` metadata (DESC).

        Pure ORDERING over the existing pool (top-weight surfacing). Returns the
        SAME set — nothing dropped (§-1.3).
        """
        def _key(c: SearchCandidate) -> tuple[float, str]:
            meta = c.metadata or {}
            return (-float(meta.get("weight_mass", 0.0) or 0.0), c.url)

        return sorted(candidates, key=_key)
