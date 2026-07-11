"""S4 OUTLINE — Agentic outliner loop (W0 + W1).

Authoritative design: ``docs/fsr_build_plan.md`` section "AGENTIC OUTLINER LOOP — FABLE
AUTHORITATIVE DESIGN" (2026-07-11, effort max). This module is the THIN driver
(``OutlineAgent``, ~ design target 300 LOC for the core loop; this file additionally carries
the workspace/ledger/tool wiring the design assigns to the same file) that WIRES the existing
ReAct contract — ``ToolRegistry`` / ``ToolDefinition`` / ``ToolResult`` / ``AnalysisNotebook``
(``src/polaris_graph/tools/tool_registry.py`` + ``analysis_notebook.py``) and the
``ReactDecision`` schema (``src/polaris_graph/tools/react_agent.py``) — into a NEW small
per-turn decide/execute loop for the OUTLINE stage. It does **not** subclass the 8k-line
``ReactAnalysisAgent`` (react-mode is ~150 LOC of that file; the rest is the compose-writer,
an unrelated concern). It does **not** import smolagents.

CONTROL FLOW (verbatim from the design):
  seed via existing ``_call_outline`` (un-starved) -> sufficiency review#0 -> gap_ledger.
  Loop while turns < PG_OUTLINE_AGENT_MAX_TURNS(24): ``_decide`` picks ONE of
  {analysis tool | inspect_basket | search_more_evidence | update_outline | finish_outline};
  execute; if search: fold-in + re-check aspect; if update_outline: validated parse/apply via
  ``outline_revise``; if finish: sufficiency checklist — deficiencies+budget => bounce & continue;
  clean/exhausted => exit. EXIT: write cp4 (typed plans + unfilled_gaps[] + notebook ref + flag
  slate) via ``outline_checkpoint.build_cp4_payload`` / ``write_cp4_outline_snapshot``.

GAP TRIGGER — 3 detectors feeding ONE ``GapLedger``:
  (1) checklist (LLM, per-section exhaustive-coverage / density / compute-need) at seed,
      after every fold-in, and at every ``finish_outline`` attempt;
  (2) TOOL-FAILURE deterministic (empty comparison / zero datapoints / empty SQL / <2 studies);
  (3) agent-initiated (the decide step names a NEW aspect when calling ``search_more_evidence``).
  Per-aspect retry ``PG_OUTLINE_GAP_RETRIES_PER_ASPECT`` (default 2), then UNFILLED + disclosed;
  dedup by ``(section, aspect)``.

FAITHFULNESS: the strict_verify / NLI / 4-role / provenance engine is UNTOUCHED and stays the
ONLY hard gate downstream of this module. Every row this module folds into the corpus is a real
fetched-and-classified row from ``run_live_retrieval`` (same production path the rest of the
pipeline uses) — this module manufactures ZERO evidence text and never marks anything "verified"
itself. The id-collision seam at fold-in is a HARD fail-loud assert (new-ids intersect
existing-ids must be empty) — see ``_offset_renumber``.

Seat: ``PG_OUTLINE_AGENT`` (default OFF). OFF => the seam at
``multi_section_generator._call_outline`` call site is a pure pass-through — byte-identical to
pre-existing behavior (see ``run_outline_agent_or_legacy`` at the bottom of this file, which is
what the generator actually calls).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.polaris_graph.outline._fold_in import (
    _offset_renumber,
    _stamp_and_delete,
    fold_in_fetched_rows,
)
from src.polaris_graph.tools.analysis_notebook import AnalysisNotebook, AnalysisStep
from src.polaris_graph.tools.react_agent import ReactDecision
from src.polaris_graph.tools.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    ToolResult,
    build_default_registry,
)

logger = logging.getLogger("polaris_graph")

_OFF_VALUES = ("0", "false", "no", "off", "")


def _env_flag(name: str, default_on: bool) -> bool:
    raw = os.getenv(name, "1" if default_on else "0")
    return str(raw).strip().lower() not in _OFF_VALUES


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Seat + knobs (LAW VI — zero hard-coding; every knob is env-tunable)
# ---------------------------------------------------------------------------

def outline_agent_enabled() -> bool:
    """``PG_OUTLINE_AGENT`` kill-switch. DEFAULT OFF => the legacy ``_call_outline``-only path
    is byte-identical (the agentic loop never runs, never imports its heavy dependencies beyond
    this module's own top-level imports, and never touches the corpus)."""
    return _env_flag("PG_OUTLINE_AGENT", default_on=False)


PG_OUTLINE_AGENT_MODEL_DEFAULT = "z-ai/glm-5.2"
PG_OUTLINER_CODE_MODEL_DEFAULT = "deepseek/deepseek-v4-pro"
PG_OUTLINE_AGENT_MAX_TURNS_DEFAULT = 24
PG_OUTLINE_GAP_RETRIES_PER_ASPECT_DEFAULT = 2
PG_OUTLINE_AGENT_WALL_SECONDS_DEFAULT = 900
# Iter-6 P0 fix (Fable-confirmed real-corpus crash: matched_comparison_run5.log,
# ReasoningFirstTruncationError at _run_checklist on the dense DRB-72 AI-labor corpus —
# glm-5.2 is a reasoning-first model in _ALWAYS_REASON_MODELS; on a dense corpus its
# unbounded-effort reasoning prelude alone ran to ~84453 chars (~21k tokens), blowing past
# the 16384-token TOTAL budget before content was ever reached. Iter-5 re-ran the SAME
# starved defaults and reproduced the identical crash — the fix below was never actually
# applied to code in iters 1-5, only described. Per CLAUDE.md §9.1.8 ("reasoning effort +
# max_tokens ALWAYS go MAX, never starve; read the API don't guess") the real OpenRouter cap
# for z-ai/glm-5.2 is top_provider.max_completion_tokens=128000 (verified via GET
# https://openrouter.ai/api/v1/models 2026-07-11). These three control-plane budgets are
# raised well below that real ceiling (comfortable headroom for a large multi-page reasoning
# prelude) and — see the call sites below — now pass an EXPLICIT ``reasoning_max_tokens``
# (the same PG_OUTLINE_REASONING_MAX_TOKENS knob the seed ``_call_outline`` already uses,
# default 32768) so the reasoning pool is bounded within the total instead of running
# unbounded-effort until it eats the whole budget. Belt-and-suspenders: _run_checklist ALSO
# now degrades fail-open (one retry at 2x budget, then "no new deficiencies" + disclosure)
# instead of letting a control-plane truncation abort the entire outline stage.
# Un-starved to the CONFIRMED real OpenRouter provider cap for z-ai/glm-5.2
# (top_provider.max_completion_tokens=131072, GET /api/v1/models 2026-07-11 per
# CLAUDE.md §9.1.8 "read the API, don't guess" — NOT a moderate raise). Reasoning
# is bounded separately via PG_OUTLINE_REASONING_MAX_TOKENS (32768) so the reasoning
# prelude cannot eat the whole budget before content — leaving ~98k tokens of content
# headroom, comfortably above the ~21k-token prelude that caused the real-corpus crash.
PG_OUTLINE_DECIDE_MAX_TOKENS_DEFAULT = 131072
PG_OUTLINE_CHECKLIST_MAX_TOKENS_DEFAULT = 131072
PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS_DEFAULT = 131072
# W2 P0 fix: outer belt-and-suspenders wall on the whole ``agent.run()`` call (grace
# added on top of the loop's own internal wall-clock check, covering a single LLM call
# that hangs past its own inner timeout). Never the primary bound — ``_wall_seconds()``
# is — this only guarantees the outer ``run_outline_agent_or_legacy`` caller is never
# wedged indefinitely.
PG_OUTLINE_AGENT_RUN_TIMEOUT_GRACE_SECONDS_DEFAULT = 180


def outliner_agent_model() -> str:
    """ReAct decide + tool-calling model (§9.1.8 lock: glm-5.2, 1M ctx — context compounds
    across a growing digest + draft + ledger + notebook)."""
    return os.getenv("PG_OUTLINER_AGENT_MODEL", PG_OUTLINE_AGENT_MODEL_DEFAULT)


def outliner_code_model() -> str:
    """Write+run-Python / outline-prose model (§9.1.8 lock: deepseek-v4-pro — already the
    sweep's generator)."""
    return os.getenv("PG_OUTLINER_CODE_MODEL", PG_OUTLINER_CODE_MODEL_DEFAULT)


# Tools whose executor actually CONSUMES the ``client`` kwarg (LLM codegen). Not the same set as
# ``requires_llm=True``: search_more_evidence carries that flag but builds its own clients.
_CODEGEN_TOOLS = frozenset({"execute_python"})


def _max_turns() -> int:
    return _env_int("PG_OUTLINE_AGENT_MAX_TURNS", PG_OUTLINE_AGENT_MAX_TURNS_DEFAULT)


def _wall_seconds() -> int:
    return _env_int("PG_OUTLINE_AGENT_WALL_SECONDS", PG_OUTLINE_AGENT_WALL_SECONDS_DEFAULT)


# Iter-6 P0 fix: shared reasoning-pool knob (same env var + default the seed ``_call_outline``
# uses in multi_section_generator.py, so ONE setting governs the whole outline stage's
# reasoning budget — LAW VI, no duplicated config surface). Bounds the reasoning slice WITHIN
# the total max_tokens ceiling so a reasoning-first model (glm-5.2) always reaches content.
PG_OUTLINE_REASONING_MAX_TOKENS_DEFAULT = 32768
# Real OpenRouter provider cap for z-ai/glm-5.2 (top_provider.max_completion_tokens), verified
# via GET https://openrouter.ai/api/v1/models 2026-07-11 per §9.1.8 "read the API, don't
# guess". Used only as a safety ceiling on the fail-open retry-with-bigger-budget path below —
# never worth requesting more than the provider will honor.
PG_GLM52_REAL_MAX_COMPLETION_TOKENS = 131072  # confirmed via GET /api/v1/models 2026-07-11


def _reasoning_max_tokens() -> int:
    return _env_int("PG_OUTLINE_REASONING_MAX_TOKENS", PG_OUTLINE_REASONING_MAX_TOKENS_DEFAULT)


def _gap_retries_per_aspect() -> int:
    return _env_int(
        "PG_OUTLINE_GAP_RETRIES_PER_ASPECT", PG_OUTLINE_GAP_RETRIES_PER_ASPECT_DEFAULT,
    )


# ---------------------------------------------------------------------------
# Gap ledger — 3 detectors -> ONE ledger; per-aspect retry cap; UNFILLED+disclosed
# ---------------------------------------------------------------------------

# iter-2 P1-1 fix: a fresh checklist round re-words the SAME underlying gap almost every
# time (GLM does not reproduce its own exact phrasing across calls). Exact-string keying
# then spawns a brand-new PENDING todo each round and the per-aspect retry cap never bites
# — the loop re-fetches the same aspect forever. This is a ROUTING dedup (does this new
# phrase point at a todo we already have?), not a quality/faithfulness judgment about the
# corpus, so token-overlap collapse is in-scope here even though the SAME mechanism is
# banned for faithfulness verdicts (§-1.1 ghost-mindset) — those are two different jobs.
_ASPECT_DEDUP_JACCARD_THRESHOLD_DEFAULT = 0.4
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "with", "vs", "versus",
    "is", "are", "was", "were", "be", "been", "its", "it", "this", "that", "any", "no",
    "not", "at", "by", "from", "as", "about", "into", "over", "than", "other",
})


def _canon_tokens(text: str) -> frozenset[str]:
    """Lowercase, punctuation-stripped, stopword-dropped token SET — the canonical form used
    ONLY to collapse checklist paraphrases onto one ledger todo (see module note above)."""
    import re as _re
    words = _re.findall(r"[a-z0-9]+", str(text or "").lower())
    return frozenset(w for w in words if w and w not in _STOPWORDS)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _normalize_section_label(section: str) -> str:
    """Whitespace/case-insensitive key for ``OutlineWorkspace.unhomeable_sections`` — a section
    LABEL (not a specific aspect wording) is what's proven unhomeable, so this key deliberately
    ignores aspect text entirely (see the field's docstring)."""
    return " ".join(str(section or "").strip().lower().split())


def _aspect_dedup_threshold() -> float:
    try:
        return float(os.getenv(
            "PG_OUTLINE_ASPECT_DEDUP_JACCARD", str(_ASPECT_DEDUP_JACCARD_THRESHOLD_DEFAULT),
        ))
    except (TypeError, ValueError):
        return _ASPECT_DEDUP_JACCARD_THRESHOLD_DEFAULT


# iter-4 P0-1 fix knobs (real-corpus proof the checklist only ever proposed a phantom
# "Summary Table" section under the locked 4-section DRB-72 deliverable, then correctly
# vetoed it, leaving zero genuine within-section gaps found): two mechanical (never-LLM)
# thresholds that let a checklist/agent-proposed section label that does not resolve to a
# current outline title EXACTLY still be recognized/routed instead of silently vetoed.
_SECTION_TITLE_FUZZY_JACCARD_DEFAULT = 0.5
_SECTION_REMAP_JACCARD_DEFAULT = 0.06


def _section_title_fuzzy_threshold() -> float:
    """Threshold for recognizing a proposed section label as the SAME section under a
    different/short wording (e.g. 'Summary Table' vs 'Summary Table: Application Cases,
    Impacts, and Risks by Industry/Occupation') — high bar, this is identity recognition."""
    return _env_float(
        "PG_OUTLINE_SECTION_TITLE_FUZZY_JACCARD", _SECTION_TITLE_FUZZY_JACCARD_DEFAULT,
    )


def _section_remap_jaccard_threshold() -> float:
    """Threshold for remapping a facet to the EXISTING section whose own topic (title+focus)
    it most overlaps, when no section in the outline is even fuzzily the SAME section — low
    bar by design: under a locked required-structure deliverable, a genuine content facet
    must live in SOME existing section, never invent a new one, and 'weight don't filter'
    (§-1.3) means routing beats discarding whenever there is ANY real signal."""
    return _env_float("PG_OUTLINE_SECTION_REMAP_JACCARD", _SECTION_REMAP_JACCARD_DEFAULT)


# iter-2 P0-1 fix: the checklist's anti-invention grounding gate. A candidate deficiency line
# must carry a verbatim quote from the research question; these two helpers are the mechanical
# (never-LLM) check that the quote is real, not a paraphrase or a hallucinated snippet.
_MIN_GROUNDING_QUOTE_WORDS = 2


_QUOTE_WRAP_CHARS = "\"'‘’“”‹›«»`"


def _normalize_for_quote_check(text: str) -> str:
    import re as _re
    stripped = str(text or "").strip().strip(_QUOTE_WRAP_CHARS).strip()
    return _re.sub(r"\s+", " ", stripped.lower())


def _quote_is_grounded(quote: str, question_norm: str) -> bool:
    """True iff ``quote`` (whitespace/case-normalized, and with any wrapping quote-mark
    PUNCTUATION the model added around its own answer stripped — iter-4 robustness fix: a
    model reply like the literal three characters ``"foo bar"`` around an otherwise-correct
    verbatim excerpt must not be mechanically rejected just because those wrapping marks are
    not themselves part of the source text) is a literal substring of the (already-normalized)
    research question AND carries at least ``_MIN_GROUNDING_QUOTE_WORDS`` words (a bare
    one-word quote like the subject's name is not a specific-enough justification for a
    claimed missing FACET)."""
    q = _normalize_for_quote_check(quote)
    if not q or len(q.split()) < _MIN_GROUNDING_QUOTE_WORDS:
        return False
    return q in question_norm


@dataclass
class GapTodo:
    section: str
    aspect: str
    needed_kind: str = "coverage"   # "coverage" | "numeric_rows" | "density"
    status: str = "PENDING"          # PENDING | IN_PROGRESS | COMPLETE | UNFILLED
    attempts: int = 0
    source: str = "checklist"        # checklist | tool_failure | agent
    disclosure: str = ""

    def key(self) -> tuple[str, str]:
        return (str(self.section), str(self.aspect))


class GapLedger:
    """Dedup-by-(section,aspect) EXACT match, falling back to same-section token-overlap
    (Jaccard >= threshold) paraphrase collapse; per-aspect retry cap; UNFILLED + disclosed
    on exhaustion.

    §-1.3.1 / §-1.1: this ledger is a ROUTING signal (what to search next), never a quality
    verdict about the corpus — it names todos, it does not score the pipeline's own output.
    """

    def __init__(self, max_retries_per_aspect: Optional[int] = None):
        self._todos: dict[tuple[str, str], GapTodo] = {}
        self._max_retries = (
            max_retries_per_aspect
            if max_retries_per_aspect is not None
            else _gap_retries_per_aspect()
        )

    def _find_paraphrase(self, section: str, aspect: str) -> Optional[GapTodo]:
        """Same-section, token-overlap match against an EXISTING todo (any status). Iter-2
        P1-1: collapses re-worded checklist gaps onto the one todo already tracking that
        aspect so the per-aspect retry cap actually bites."""
        canon_new = _canon_tokens(aspect)
        if not canon_new:
            return None
        threshold = _aspect_dedup_threshold()
        best: Optional[GapTodo] = None
        best_score = 0.0
        for (sec2, asp2), todo in self._todos.items():
            if sec2 != section:
                continue
            score = _jaccard(canon_new, _canon_tokens(asp2))
            if score >= threshold and score > best_score:
                best, best_score = todo, score
        return best

    def add(
        self, section: str, aspect: str,
        needed_kind: str = "coverage", source: str = "checklist",
    ) -> GapTodo:
        section = str(section or "").strip()
        aspect = str(aspect or "").strip()
        key = (section, aspect)
        existing = self._todos.get(key)
        if existing is not None:
            return existing
        paraphrase = self._find_paraphrase(section, aspect)
        if paraphrase is not None:
            return paraphrase
        todo = GapTodo(
            section=section, aspect=aspect, needed_kind=needed_kind, source=source,
        )
        self._todos[key] = todo
        return todo

    def add_unfillable(
        self, section: str, aspect: str, reason: str,
        needed_kind: str = "coverage", source: str = "checklist",
    ) -> GapTodo:
        """Iter-3 P0 fix (real-corpus degeneration — 'Summary Table' gap re-fired ~10x over
        945s while every fetched row stayed orphaned in the pool): a gap whose named section
        can NEVER be routed to retrieval — it does not match any current outline title, and
        under a locked required-structure deliverable there is no way to add a new section for
        it — is a STRUCTURAL limitation, not a content gap. Recording it UNFILLED immediately
        (never PENDING) means ``next_pending()`` never selects it and the decide-loop never
        fires ``search_more_evidence`` for it, so the loop cannot burn its turn/wall budget
        re-fetching the same unhomeable aspect under a slightly different checklist wording
        each round. Still disclosed (§-1.3 — no silent drop), just never retried."""
        todo = self.add(section=section, aspect=aspect, needed_kind=needed_kind, source=source)
        if todo.status not in ("UNFILLED", "COMPLETE"):
            todo.status = "UNFILLED"
            todo.disclosure = reason
        return todo

    def get(self, section: str, aspect: str) -> Optional[GapTodo]:
        return self._todos.get((str(section or "").strip(), str(aspect or "").strip()))

    def next_pending(self) -> Optional[GapTodo]:
        for todo in self._todos.values():
            if todo.status == "PENDING":
                return todo
        return None

    def mark_in_progress(self, todo: GapTodo) -> None:
        todo.status = "IN_PROGRESS"
        todo.attempts += 1

    def mark_complete(self, todo: GapTodo) -> None:
        todo.status = "COMPLETE"

    def mark_retry_or_unfilled(self, todo: GapTodo, reason: str) -> None:
        """Per-aspect retry: PENDING again while attempts < cap; UNFILLED + disclosed at cap."""
        if todo.attempts >= self._max_retries:
            todo.status = "UNFILLED"
            todo.disclosure = reason
        else:
            todo.status = "PENDING"

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self._todos.values() if t.status == "PENDING")

    @property
    def unfilled(self) -> list[GapTodo]:
        return [t for t in self._todos.values() if t.status == "UNFILLED"]

    @property
    def all_todos(self) -> list[GapTodo]:
        return list(self._todos.values())

    def as_list(self) -> list[dict[str, Any]]:
        return [dataclasses.asdict(t) for t in self._todos.values()]

    def summary_for_llm(self) -> str:
        if not self._todos:
            return "  (empty — no gaps identified yet)"
        lines = []
        for t in self._todos.values():
            lines.append(
                f"  [{t.status}] section={t.section!r} aspect={t.aspect!r} "
                f"kind={t.needed_kind} attempts={t.attempts}/{self._max_retries} source={t.source}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# OutlineWorkspace — the agent's mutable state (checkpointed after every mutation)
# ---------------------------------------------------------------------------

@dataclass
class OutlineWorkspace:
    research_question: str
    ev_store: dict[str, dict[str, Any]]              # cp2 rows keyed by evidence_id, S2-stamped
    outline_draft: list[Any] = field(default_factory=list)   # list[SectionPlan]
    gap_ledger: GapLedger = field(default_factory=GapLedger)
    notebook: Optional[AnalysisNotebook] = None
    basket_menu: Any = None                            # outline_digest menu (or None)
    budgets: dict[str, Any] = field(default_factory=dict)
    disclosures: list[str] = field(default_factory=list)
    # W4: successful execute_python payloads, so a computed value is no longer discarded at
    # every exit. EXPLORATORY / NOT RENDERABLE — every row carries renderable=False +
    # bar_reason (see _compute_result_check). Telemetry + planner provenance only; this is
    # NOT a render path and never reaches a writer prompt.
    compute_results: list[dict] = field(default_factory=list)
    # W3-render (2026-07-11): run-scoped registry of VERIFIED quantified models, keyed by
    # (model_id, spec_hash) exactly as ``strict_verify(quantified_models=...)`` expects. This is
    # the ONLY compute-render surface: a number lands here solely by re-derivation through the
    # fail-closed ModelSpec lane (verified_compute.run_verified_compute -> build_quantified_spec ->
    # execute_quantified_model), and renders solely via its ``[#calc:model:hash:field]`` token,
    # which strict_verify force-routes to ``verify_modeled_atom``. Exploratory execute_python output
    # (compute_results above, renderable=False) NEVER enters this dict — that separation is the
    # faithfulness invariant (a derived number can never reach the [#ev]/[CITE] render path).
    quantified_models: dict = field(default_factory=dict)  # (model_id, spec_hash) -> QuantifiedResult
    turn: int = 0
    started_monotonic: float = field(default_factory=time.monotonic)
    checkpoint_dir: Optional[str] = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    # Iter-2 fix: the deliverable's REQUIRED section titles (empty => no structure lock, the
    # common case for the free-form acceptance/real-corpus runs). When non-empty, the outline's
    # section STRUCTURE is governed by the caller (S4 ORCH-2 PUSH 1 / `_call_outline`'s own
    # `required_sections` conform already enforced this at SEED time) and this module must never
    # silently add a 5th section behind the caller's back — see `_tool_update_outline` and the
    # auto-assign fallback in `OutlineAgent._execute_tool`.
    required_titles: list[str] = field(default_factory=list)
    # Iter-3 P0 fix (real-corpus THINNED run: 8 search_more_evidence calls, 31 genuinely NEW
    # fetched rows, ZERO landed in any required section — the whole retrieval budget was spent
    # re-chasing the SAME unhomeable section label, e.g. "Summary Table", under 8 differently
    # worded aspects that each failed the (section,aspect) paraphrase dedup because the ASPECT
    # text varied enough while the SECTION stayed constant). Once a section label is proven
    # unhomeable (checklist- or agent-initiated), it is banked here (normalized) and vetoed —
    # cheaply, before any real fetch — for the rest of the run, regardless of aspect rewording.
    unhomeable_sections: set = field(default_factory=set)
    _checkpoint_seq: int = 0

    def next_ev_offset(self) -> int:
        """Highest numeric suffix across current ev_ids, +1. Rows that don't parse as
        ``ev_<digits>`` are ignored for the offset computation (never crash the offset)."""
        mx = -1
        for eid in self.ev_store.keys():
            tail = str(eid).rsplit("_", 1)[-1]
            if tail.isdigit():
                mx = max(mx, int(tail))
        return mx + 1

    def existing_urls(self) -> set[str]:
        urls: set[str] = set()
        for row in self.ev_store.values():
            if isinstance(row, dict):
                u = str(row.get("source_url") or row.get("url") or "").strip()
                if u:
                    urls.add(u)
        return urls

    def disclose(self, text: str) -> None:
        self.disclosures.append(text)
        logger.info("[outline_agent] %s", text)

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_monotonic

    def checkpoint(self, event: str) -> None:
        """Best-effort checkpoint-after-every-mutation (crash-resume). NEVER raises — a
        checkpoint failure must not abort the loop (mirrors ``write_cp4_outline_snapshot``'s
        own best-effort contract one layer up)."""
        if not self.checkpoint_dir:
            return
        try:
            from src.polaris_graph.generator.outline_checkpoint import (  # noqa: PLC0415
                build_cp4_payload, write_cp4_outline_snapshot,
            )
            self._checkpoint_seq += 1
            plans_dicts = [_plan_to_dict(p) for p in self.outline_draft]
            payload = build_cp4_payload(
                question_sha="",
                upstream=None,
                run_config_sha="",
                flag_slate={"PG_OUTLINE_AGENT": "1", "event": str(event)},
                adjustments_applied=None,
                final_plans=plans_dicts,
                revision_audit={
                    "gap_ledger": self.gap_ledger.as_list(),
                    "disclosures": list(self.disclosures),
                    "turn": self.turn,
                    "checkpoint_seq": self._checkpoint_seq,
                    "notebook_steps": (
                        [
                            {
                                "tool_name": s.tool_name,
                                "reasoning": s.reasoning[:200],
                                "success": s.result.success,
                            }
                            for s in self.notebook.steps
                        ] if self.notebook is not None else []
                    ),
                },
                digest_stats={
                    "ev_store_size": len(self.ev_store),
                    "elapsed_seconds": round(self.elapsed_seconds(), 1),
                },
            )
            write_cp4_outline_snapshot(self.checkpoint_dir, payload)
        except Exception as exc:  # noqa: BLE001 — checkpoint is best-effort, never fatal
            logger.warning("[outline_agent] checkpoint write skipped (fail-open): %s", exc)


def _plan_field(plan: Any, key: str, default: Any = "") -> Any:
    """Iter-2 fix (found via offline smoke test, not in the original Fable P0/P1 list): plans in
    ``workspace.outline_draft`` are NOT a uniform type across the loop's lifetime — the SEED plans
    from ``_call_outline`` are ``SectionPlan`` dataclass instances, but ``outline_revise.apply_
    revision_ops`` (which BOTH ``update_outline`` and the new iter-2 auto-assign call after every
    successful search) always returns plain ``dict`` plans (``RevisionApplyResult.new_plans:
    list[dict]``). A bare ``getattr(p, 'title', default)`` silently returns ``default`` for a dict
    (dicts have no attribute access) — so the FIRST time any update_outline/auto-assign op ran,
    every downstream title lookup in THIS module (decide's outline summary, the checklist's
    section block, ``inspect_basket``'s assignment check, auto-assign's own section-title
    resolver) would have silently gone blank, breaking the very mutation this iteration exists to
    fix. Mirrors ``outline_revise._plan_get`` exactly (dict-or-attribute duck typing) — reproduced
    here rather than imported to keep this module's OFF-path import graph unchanged (LAW VI/V:
    small, side-effect-free helper; not worth a cross-module coupling for 4 lines)."""
    if isinstance(plan, dict):
        return plan.get(key, default)
    return getattr(plan, key, default)


def _plan_to_dict(plan: Any) -> dict[str, Any]:
    if isinstance(plan, dict):
        return dict(plan)
    if dataclasses.is_dataclass(plan):
        return dataclasses.asdict(plan)
    return {
        "title": _plan_field(plan, "title", ""),
        "focus": _plan_field(plan, "focus", ""),
        "ev_ids": list(_plan_field(plan, "ev_ids", []) or []),
        "basket_ids": list(_plan_field(plan, "basket_ids", []) or []),
        "archetype": _plan_field(plan, "archetype", ""),
        "undersupplied": _plan_field(plan, "undersupplied", False),
    }


# ---------------------------------------------------------------------------
# search_more_evidence — the retrieval pipe as a tool (the sharp seam)
# ---------------------------------------------------------------------------

def _sync_llm_bridge(model: str, max_tokens: int) -> Callable[[str], str]:
    """Build a SYNCHRONOUS ``str -> str`` callable bridging into the async
    ``OpenRouterClient.generate`` — the exact thread+contextvars pattern
    ``run_honest_sweep_r3.py``'s ``_topic_llm`` uses (that module is not importable here without
    dragging in the whole sweep script, so the ~20-line bridge is reproduced, not re-derived).
    Required because ``classify_topic_relevance`` (topic_relevance_gate.py) takes a sync
    callable and this module runs inside an ALREADY-RUNNING asyncio loop (the outline agent's
    own loop), where a bare ``asyncio.run()`` would raise."""

    def _llm(prompt: str) -> str:
        import concurrent.futures as _futures
        import contextvars as _contextvars

        async def _run() -> str:
            from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415
            client = OpenRouterClient(model=model)
            try:
                resp = await client.generate(prompt=prompt, max_tokens=max_tokens, temperature=0.0)
                return (resp.content or "").strip()
            finally:
                if hasattr(client, "close"):
                    try:
                        await client.close()
                    except Exception:  # noqa: BLE001 — client close is best-effort
                        pass

        parent_ctx = _contextvars.copy_context()

        def _worker() -> str:
            return parent_ctx.run(lambda: asyncio.run(_run()))

        with _futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_worker).result()

    return _llm


async def _tool_search_more_evidence(
    workspace: OutlineWorkspace,
    agent_model: str,
    *,
    section: str = "",
    aspect: str = "",
    domain: Optional[str] = None,
    retrieval_deadline_monotonic: Optional[float] = None,
    **_ignored: Any,
) -> ToolResult:
    """The retrieval pipe as a ReAct tool. Steps (design §): per-todo query derivation
    (scope-anchored, ``_is_status_leak`` guard) -> ``run_live_retrieval(anchor_seed=False)`` ->
    ``merge_retrieval_results`` -> offset-renumber (hard assert) + URL-dedup vs existing ->
    S2 stamp pass (chrome delete + topic-judge fail-open) -> fold into ``ev_store`` -> disclosed
    ``ToolResult``. One retrieval in flight at a time (§8.4 — this coroutine is awaited, never
    fired concurrently by the driver)."""
    aspect_text = str(aspect or "").strip() or str(section or "").strip()
    if not aspect_text:
        return ToolResult(
            success=False, tool_name="search_more_evidence",
            markdown="search_more_evidence requires a `section` or `aspect`.",
            error="missing_aspect",
        )

    from src.polaris_graph.retrieval.fs_researcher_query_gen import (  # noqa: PLC0415
        _is_status_leak,
    )
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

    query_derive_max_tokens = _env_int(
        "PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS", PG_OUTLINE_QUERY_DERIVE_MAX_TOKENS_DEFAULT,
    )
    client = OpenRouterClient(model=agent_model)
    try:
        derive_prompt = (
            "Write ONE web-search query for the SUB-TOPIC below, kept STRICTLY within the "
            "scope of the RESEARCH QUESTION (carry its subject, domain and key entities; do "
            "NOT broaden the query into the sub-topic's generic field). Query only, one line, "
            "no quotes.\n\n"
            f"RESEARCH QUESTION:\n{workspace.research_question}\n\nSUB-TOPIC:\n{aspect_text}"
        )
        try:
            # Iter-6 P0 fix: same reasoning-pool bound as the checklist/decide calls above —
            # this call already fails open on ANY exception (including a truncation), but an
            # unbounded-effort reasoning prelude on a dense corpus still needlessly degrades a
            # one-line query derivation to the raw aspect text every time; bounding it means the
            # derived (scope-anchored) query actually gets used instead of the coarser fallback.
            resp = await client.generate(
                prompt=derive_prompt, max_tokens=query_derive_max_tokens, temperature=0.2,
                reasoning_max_tokens=_reasoning_max_tokens(),
            )
            derived = (resp.content or "").strip().splitlines()[0].strip().strip('"') if (
                resp.content or ""
            ).strip() else ""
        except Exception as exc:  # noqa: BLE001 — query derivation is a small text call; degrade to raw aspect
            logger.warning("[outline_agent] query derivation failed, using raw aspect: %s", exc)
            derived = ""
    finally:
        if hasattr(client, "close"):
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass

    query = derived or aspect_text
    if _is_status_leak(query, workspace.research_question):
        return ToolResult(
            success=False, tool_name="search_more_evidence",
            markdown=f"Derived query was a status-leak, aborted: {query[:120]!r}",
            error="status_leak_aborted",
        )

    from src.polaris_graph.retrieval.live_retriever import (  # noqa: PLC0415
        LiveRetrievalResult, run_live_retrieval,
    )
    from src.polaris_graph.retrieval.fs_researcher_query_gen import (  # noqa: PLC0415
        merge_retrieval_results,
    )

    t0 = time.monotonic()
    try:
        # BUG FOUND IN W1 LIVE ACCEPTANCE RUN (fixed same-iter): ``anchor_seed=False`` makes
        # ``run_live_retrieval`` build ``all_queries`` from ``amplified_queries`` ONLY (the
        # verbatim ``research_question`` is NOT auto-fired when the anchor is suppressed — see
        # the function's own docstring). The gap query MUST be passed via ``amplified_queries``;
        # ``research_question`` stays the WORKSPACE question (scope-validator anchor text) so a
        # scoped sub-query is validated against the real topic, not against itself.
        raw_result = await asyncio.to_thread(
            run_live_retrieval,
            research_question=workspace.research_question,
            amplified_queries=[query],
            domain=domain,
            anchor_seed=False,
            retrieval_deadline_monotonic=retrieval_deadline_monotonic,
        )
    except Exception as exc:  # noqa: BLE001 — a single retrieval round must not crash the loop
        return ToolResult(
            success=False, tool_name="search_more_evidence",
            markdown=f"run_live_retrieval raised for query {query!r}: {exc}",
            error=str(exc)[:500],
        )
    elapsed = time.monotonic() - t0

    merged = merge_retrieval_results([raw_result], LiveRetrievalResult)
    fetched_rows = list(getattr(merged, "evidence_rows", None) or [])
    n_fetched_of = f"{len(fetched_rows)} of {getattr(merged, 'candidates_total', len(fetched_rows))}"

    # THE shared fold-in seam (outline/_fold_in.py): url-dedup -> offset-renumber (hard
    # id-collision assert) -> S2 stamp/delete -> insert. fetch_url re-enters through the same unit.
    fold = await fold_in_fetched_rows(
        workspace, fetched_rows,
        research_question=workspace.research_question, agent_model=agent_model,
    )
    kept_rows = fold.kept_rows
    n_kept = fold.n_kept
    n_deleted = fold.n_deleted
    disclosure = (
        f"search_more_evidence[{aspect_text[:60]!r}] query={query!r} fetched {n_fetched_of}, "
        f"url-dup dropped {fold.n_url_dup}, kept {n_kept}, deleted {n_deleted} "
        f"(chrome={len(fold.deleted_chrome)}, off-topic={len(fold.deleted_offtopic)}) in {elapsed:.1f}s"
    )
    workspace.disclose(disclosure)

    md_lines = [f"**{disclosure}**", ""]
    for row in kept_rows[:10]:
        md_lines.append(
            f"- {row.get('evidence_id')}: {str(row.get('title') or '')[:80]} "
            f"[CITE:{row.get('evidence_id')}]"
        )
    if len(kept_rows) > 10:
        md_lines.append(f"- ... and {len(kept_rows) - 10} more")

    return ToolResult(
        success=n_kept > 0,
        tool_name="search_more_evidence",
        markdown="\n".join(md_lines),
        source_evidence_ids=[r["evidence_id"] for r in kept_rows],
        error=("" if n_kept > 0 else "no_new_evidence_survived_screen"),
    )


# ---------------------------------------------------------------------------
# inspect_basket
# ---------------------------------------------------------------------------

async def _tool_inspect_basket(
    workspace: OutlineWorkspace, *, basket_id: str = "", **_ignored: Any,
) -> ToolResult:
    """Pure read of the cp3 basket digest — members, corroboration, whether every member is
    already assigned to a section. No LLM, no network."""
    menu = workspace.basket_menu
    if menu is None or not basket_id:
        return ToolResult(
            success=False, tool_name="inspect_basket",
            markdown="No basket digest available or no basket_id supplied.",
            error="no_digest_or_id",
        )
    members = list(getattr(menu, "basket_member_ev_ids", {}).get(basket_id, []) or [])
    corroboration = getattr(menu, "basket_work_corroboration", {}).get(basket_id, 0)
    if not members:
        return ToolResult(
            success=False, tool_name="inspect_basket",
            markdown=f"Basket {basket_id!r} not found in the digest.",
            error="basket_not_found",
        )
    assigned_ev = {eid for p in workspace.outline_draft for eid in (_plan_field(p, "ev_ids", None) or [])}
    unassigned = [m for m in members if m not in assigned_ev]
    lines = [
        f"**Basket {basket_id}**: {len(members)} member(s), corroboration={corroboration}, "
        f"unassigned={len(unassigned)}",
    ]
    for m in members[:15]:
        row = workspace.ev_store.get(m, {})
        lines.append(f"- {m}: {str(row.get('title') or '')[:70]} [CITE:{m}]")
    return ToolResult(
        success=True, tool_name="inspect_basket", markdown="\n".join(lines),
        source_evidence_ids=members,
    )


# ---------------------------------------------------------------------------
# update_outline — wraps outline_revise parse/apply (validated, per-op reject, never free rewrite)
# ---------------------------------------------------------------------------

async def _tool_update_outline(
    workspace: OutlineWorkspace, *, ops: Any = None, **_ignored: Any,
) -> ToolResult:
    from src.polaris_graph.generator.outline_revise import (  # noqa: PLC0415
        apply_revision_ops, parse_revision_ops,
    )

    if ops is None:
        return ToolResult(
            success=False, tool_name="update_outline",
            markdown="update_outline requires `ops` (a revision op list).",
            error="missing_ops",
        )
    allowed_ev_ids = set(workspace.ev_store.keys())
    plan_titles = [str(_plan_field(p, "title", "")) for p in workspace.outline_draft]
    raw = ops if isinstance(ops, (dict, str)) else {"ops": ops}
    parse_result = parse_revision_ops(
        raw, allowed_ev_ids=allowed_ev_ids, plan_titles=plan_titles,
    )
    if parse_result.parse_failed or not parse_result.ops:
        return ToolResult(
            success=False, tool_name="update_outline",
            markdown=(
                f"No ops applied (parse_failed={parse_result.parse_failed}, "
                f"rejected={parse_result.rejected})."
            ),
            error="no_ops_applied",
        )

    # Iter-2 fix: thread the deliverable's required-structure lock (if any) into apply — mirrors
    # `scripts/orchestrator_lab/outline_lab.py`'s `_required` threading. Without this, a
    # required_sections-governed outline (e.g. the DRB-72 4-section canonical structure) could
    # silently grow a 5th section via an agent-issued `add` op, breaking the caller's exact-N-in-
    # order structural contract that `_call_outline` already conformed the seed to.
    apply_result = apply_revision_ops(
        workspace.outline_draft, parse_result,
        required_titles=(workspace.required_titles or None),
    )
    # Iter-2 fix (found via offline smoke test): ``apply_revision_ops`` ALWAYS returns
    # ``list[dict]`` (``outline_revise`` is dict-native; it is not currently wired into
    # production composition at all — grep confirms its only callers before this module were
    # the offline ``outline_lab.py`` harness). But THIS module's ``workspace.outline_draft`` is
    # handed straight back to ``generate_multi_section_report`` as ``parse_result.plans``, and
    # every downstream composition site (M-44 primary injection, section-budget code, the
    # manifest's ``[p.title for p in multi.outline]``, etc.) does direct ``.title``/``.ev_ids``
    # ATTRIBUTE access on real ``SectionPlan`` dataclass instances. Handing dicts downstream
    # would ``AttributeError`` the first real composition run the moment any update_outline (or
    # the iter-2 auto-assign) op fires. Reconcile back to ``SectionPlan`` HERE — the one seam
    # where outline_revise's dict world meets the rest of the pipeline's dataclass world — so
    # every OTHER call site in this module (and every downstream consumer) can keep doing plain
    # ``SectionPlan`` attribute access unconditionally.
    from src.polaris_graph.generator.multi_section_generator import SectionPlan  # noqa: PLC0415
    workspace.outline_draft = [
        SectionPlan(
            title=str(d.get("title", "")),
            focus=str(d.get("focus", "")),
            ev_ids=list(d.get("ev_ids", []) or []),
            archetype=str(d.get("archetype", "")),
            undersupplied=bool(d.get("undersupplied", False)),
            basket_ids=list(d.get("basket_ids", []) or []),
        )
        for d in apply_result.new_plans
    ]

    # Route the reviser's gap_queries into the shared gap ledger (design §).
    for gq in (parse_result.gap_queries or []):
        workspace.gap_ledger.add(
            section="(unassigned)", aspect=str(gq), needed_kind="coverage", source="agent",
        )

    md = (
        f"Applied {len(apply_result.applied_ops)} op(s); recompose={apply_result.recompose_titles}; "
        f"kept={len(apply_result.kept_titles)}; rejected={len(parse_result.rejected)}; "
        f"deferred={len(apply_result.deferred_ops)}; gap_queries routed to ledger: "
        f"{len(parse_result.gap_queries or [])}"
    )
    workspace.disclose(f"update_outline: {md}")
    return ToolResult(success=True, tool_name="update_outline", markdown=md)


# ---------------------------------------------------------------------------
# OutlineAgent driver
# ---------------------------------------------------------------------------

_OUTLINE_ONLY_ACTIONS = ("inspect_basket", "search_more_evidence", "update_outline")
_FINISH_ACTION = "finish_outline"


class OutlineAgent:
    """The per-turn decide/execute loop over the outline workspace. Mirrors the SHAPE of
    ``ReactAnalysisAgent._run_react`` (react_agent.py:690) — decide -> execute -> record ->
    check-stop — without inheriting from it (design: WIRING, not building)."""

    def __init__(
        self,
        workspace: OutlineWorkspace,
        *,
        agent_model: Optional[str] = None,
        max_turns: Optional[int] = None,
        wall_seconds: Optional[int] = None,
        domain: Optional[str] = None,
        retrieval_deadline_monotonic: Optional[float] = None,
    ):
        self.workspace = workspace
        self.agent_model = agent_model or outliner_agent_model()
        self.max_turns = max_turns if max_turns is not None else _max_turns()
        self.wall_seconds = wall_seconds if wall_seconds is not None else _wall_seconds()
        self.domain = domain
        # Iter-2 P1-3 fix: the OUTER while-loop only checked the wall BETWEEN turns, so a
        # single in-flight ``search_more_evidence`` call could itself run well past the wall
        # (observed: 218s overshoot). ``run_live_retrieval`` already has its own internal
        # mid-fetch wall defense (WALL-03, ``retrieval_deadline_monotonic``) but nothing wired
        # it in — the parameter was accepted here and silently stayed ``None`` (unbounded) on
        # every call. Default it from the SAME wall the outer loop uses, anchored at workspace
        # start, so the in-flight fetch/enrich/classify sub-waits inside a single search call
        # are ALSO bounded by the agent's own wall. An explicit override (e.g. a shared
        # pipeline-wide deadline) still wins.
        self.retrieval_deadline_monotonic = (
            retrieval_deadline_monotonic
            if retrieval_deadline_monotonic is not None
            else workspace.started_monotonic + self.wall_seconds
        )
        self.registry: ToolRegistry = self._build_registry()
        if workspace.notebook is None:
            workspace.notebook = AnalysisNotebook(
                query=workspace.research_question, evidence_ids=list(workspace.ev_store.keys()),
            )

    def _build_registry(self) -> ToolRegistry:
        registry = build_default_registry()  # the 8 analysis tools, byte-identical reuse

        async def _exec_inspect_basket(evidence_store, data_points, client, **kw):  # noqa: ANN001
            return await _tool_inspect_basket(self.workspace, **kw)

        async def _exec_search_more_evidence(evidence_store, data_points, client, **kw):  # noqa: ANN001
            return await _tool_search_more_evidence(
                self.workspace, self.agent_model, domain=self.domain,
                retrieval_deadline_monotonic=self.retrieval_deadline_monotonic, **kw,
            )

        async def _exec_update_outline(evidence_store, data_points, client, **kw):  # noqa: ANN001
            return await _tool_update_outline(self.workspace, **kw)

        registry.register(ToolDefinition(
            name="inspect_basket",
            description="Inspect a cp3 basket's members, corroboration, and assignment status.",
            requires_data=False, requires_llm=False,
            parameters={"basket_id": "the basket id to inspect"},
            execute=_exec_inspect_basket,
        ))
        registry.register(ToolDefinition(
            name="search_more_evidence",
            description=(
                "Fetch MORE real evidence for a section/aspect that is thin or missing "
                "coverage. Derives a scoped query, runs live retrieval, screens junk/off-topic, "
                "and folds surviving rows into the evidence pool."
            ),
            requires_data=False, requires_llm=True,
            parameters={
                "section": "the section title this gap belongs to",
                "aspect": "the specific missing aspect / sub-topic to search for",
            },
            execute=_exec_search_more_evidence,
        ))
        registry.register(ToolDefinition(
            name="update_outline",
            description=(
                "Apply validated revision ops (keep/merge/split/retitle/reassign/add) to the "
                "outline draft."
            ),
            requires_data=False, requires_llm=False,
            parameters={"ops": "a revision op list, e.g. {\"ops\": [...]}"},
            execute=_exec_update_outline,
        ))
        return registry

    def _resolve_section_title(self, sec: str) -> Optional[str]:
        """Iter-2 P0-2 helper: resolve a (possibly slightly-off) section name from a tool call
        to the EXACT current outline plan title, so the auto-assign reassign-op always targets a
        real, existing section (never guesses a new one into being). Exact match first, then
        case-insensitive/whitespace-insensitive, then (iter-4 P0-1 fix — a real corpus run
        showed the checklist copy a SHORTENED version of a long real title, e.g. 'Summary
        Table' for the actual title 'Summary Table: Application Cases, Impacts, and Risks by
        Industry/Occupation', and the strict-exact match orphaned the fetched rows) a
        normalized substring-containment or high token-Jaccard match — still IDENTITY
        recognition of an existing section, never an invented one. Returns ``None`` (no guess)
        on no match."""
        sec_norm = str(sec or "").strip()
        if not sec_norm:
            return None
        titles = [str(_plan_field(p, "title", "") or "") for p in self.workspace.outline_draft]
        for title in titles:
            if title == sec_norm:
                return title
        sec_lower = sec_norm.lower()
        for title in titles:
            if title.strip().lower() == sec_lower:
                return title
        sec_canon = _canon_tokens(sec_norm)
        if not sec_canon:
            return None
        threshold = _section_title_fuzzy_threshold()
        best_title: Optional[str] = None
        best_score = 0.0
        for title in titles:
            title_lower = title.strip().lower()
            if title_lower and sec_lower and (sec_lower in title_lower or title_lower in sec_lower):
                return title
            score = _jaccard(sec_canon, _canon_tokens(title))
            if score > best_score:
                best_title, best_score = title, score
        if best_title is not None and best_score >= threshold:
            return best_title
        return None

    def _best_remap_title(self, aspect: str) -> Optional[str]:
        """Iter-4 P0-1 fix: when a proposed section label matches NO current outline title —
        not even fuzzily via ``_resolve_section_title`` — do not treat the underlying facet as
        automatically unhomeable. On the real DRB-72 AI-labor corpus the checklist's ONLY
        candidate gap was a phantom 'Summary Table' section describing facets (specific
        industries/occupations, impacts, risks) that are each genuinely topical to one of the
        FOUR LOCKED sections the deliverable actually has — vetoing the whole line as a
        'deliverable-level formatting request' discarded real, retrievable content gaps
        instead of routing them. Mechanical (never-LLM) token-overlap: score the aspect text
        against each existing section's OWN topic (title + focus, since focus was itself
        derived from the research question by the seed outline call, so this stays
        question-agnostic — no hardcoded domain vocabulary). This is a ROUTING decision, not a
        quality verdict about the corpus (§-1.3.1 — 'weight/route, don't drop'). Returns
        ``None`` (caller falls back to UNFILLED, honestly disclosed) if nothing clears the
        (deliberately low) floor."""
        aspect_canon = _canon_tokens(aspect)
        if not aspect_canon:
            return None
        threshold = _section_remap_jaccard_threshold()
        best_title: Optional[str] = None
        best_score = 0.0
        for p in self.workspace.outline_draft:
            title = str(_plan_field(p, "title", "") or "").strip()
            if not title:
                continue
            focus = str(_plan_field(p, "focus", "") or "")
            score = _jaccard(aspect_canon, _canon_tokens(f"{title} {focus}"))
            if score > best_score:
                best_title, best_score = title, score
        if best_title is not None and best_score >= threshold:
            return best_title
        return None

    # -- decide -----------------------------------------------------------

    async def _decide(self) -> ReactDecision:
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

        available = self.registry.available_tools(True) + [_FINISH_ACTION]
        tool_descriptions = self.registry.get_tool_descriptions(True)
        # W4 (2026-07-11): include_results=True. Without it this summary printed ONLY
        # "{n}. {tool} [{status}] ({elapsed}s) — {reasoning[:60]}", so a SUCCESSFUL
        # execute_python's computed value (present in .statistics/.insights/.markdown)
        # never reached the planner — while success also meant no gap was recorded, so
        # nothing was disclosed either. Undisclosed AND unreachable. The digest is
        # planner-facing only; it is NOT a render path (see the docstring).
        notebook_summary = (
            self.workspace.notebook.summary_for_llm(include_results=True)
            if self.workspace.notebook else ""
        )
        outline_summary = "\n".join(
            f"  - {_plan_field(p, 'title', '')!r}: {len(_plan_field(p, 'ev_ids', []) or [])} "
            f"ev_ids, focus={str(_plan_field(p, 'focus', ''))[:80]!r}"
            for p in self.workspace.outline_draft
        ) or "  (no outline yet)"

        ledger_is_empty = not self.workspace.gap_ledger.all_todos
        empty_ledger_note = (
            "\nNOTE: the gap ledger is CURRENTLY EMPTY. A careful, disciplined coverage-review "
            "already ran over this outline and found ZERO deficiencies against the research "
            "question. Treat that as strong evidence the outline is adequate.\n"
            if ledger_is_empty else ""
        )
        prompt = (
            f"RESEARCH QUESTION:\n{self.workspace.research_question}\n\n"
            f"CURRENT OUTLINE ({len(self.workspace.outline_draft)} sections):\n{outline_summary}\n\n"
            f"GAP LEDGER:\n{self.workspace.gap_ledger.summary_for_llm()}\n{empty_ledger_note}\n"
            f"NOTEBOOK:\n{notebook_summary}\n\n"
            f"Evidence pool size: {len(self.workspace.ev_store)}\n\n"
            f"Available tools:\n{tool_descriptions}\n"
            f"  - {_FINISH_ACTION}: stop the loop; the outline is ready.\n\n"
            "Rules:\n"
            "1. If the gap ledger has a PENDING item, prefer search_more_evidence for it "
            "(pass section/aspect in action_input) unless you have a stronger reason.\n"
            "2. Do not repeat a tool call that already failed for the same aspect twice.\n"
            f"3. Max {self.max_turns} turns total.\n"
            f"4. Only choose {_FINISH_ACTION} when the gap ledger has no PENDING items "
            "and you believe coverage is exhaustive and evidence density is adequate.\n"
            "5. ANTI-REDUNDANCY (this is what keeps a single-fact question from burning retrieval "
            "budget it does not need): when the gap ledger is EMPTY, do NOT self-initiate "
            "search_more_evidence just to 're-confirm', 'double-check', or gather 'the exact "
            "date/number/detail' of something the assigned evidence ALREADY states — that is "
            "redundant confirmation, not a real gap. Only self-initiate a search when you can name "
            "a CONCRETE aspect the RESEARCH QUESTION asks about that the current outline's assigned "
            "evidence genuinely does NOT answer at all. If the question is a single, narrow, "
            "already-answered fact and the gap ledger is empty, choose finish_outline.\n\n"
            "Pick ONE tool (or finish_outline) and give reasoning + action_input."
        )
        system = (
            "You are the outline agent for a deep-research pipeline. Interleave analysis and "
            "re-retrieval: when you notice the outline or evidence is thin on an aspect, go "
            "fetch more before finishing. Respond with reasoning, action, and action_input."
        )
        client = OpenRouterClient(model=self.agent_model)
        try:
            # Iter-6 P0 fix: (1) reasoning_max_tokens explicit so glm-5.2's unbounded-effort
            # reasoning pool is bounded WITHIN the raised total (see PG_OUTLINE_DECIDE_MAX_TOKENS
            # comment at top of file); (2) the inner ``timeout=120`` / outer ``wait_for(150)`` used
            # to actively DEFEAT openrouter_client._resolve_call_timeout's generous reasoning-
            # first-model budget (an explicit caller timeout always wins over the live generator
            # timeout per that function's own resolution order) — pass timeout=None so a
            # reasoning-first model gets the real ~600s generator budget, with a generous
            # env-tunable outer wall as the true backstop instead of a starving one.
            decision = await asyncio.wait_for(
                client.generate_structured(
                    prompt=prompt, schema=ReactDecision, system=system,
                    max_tokens=_env_int(
                        "PG_OUTLINE_DECIDE_MAX_TOKENS", PG_OUTLINE_DECIDE_MAX_TOKENS_DEFAULT,
                    ),
                    reasoning_enabled=True, reasoning_effort="high", timeout=None,
                    reasoning_max_tokens=_reasoning_max_tokens(),
                ),
                timeout=_env_int("PG_OUTLINE_DECIDE_WALL_SECONDS", 660),
            )
        finally:
            if hasattr(client, "close"):
                try:
                    await client.close()
                except Exception:  # noqa: BLE001
                    pass

        if decision.action != _FINISH_ACTION and decision.action not in available:
            logger.warning(
                "[outline_agent] LLM picked unavailable action %r, falling back to finish_outline",
                decision.action,
            )
            pending = self.workspace.gap_ledger.next_pending()
            if pending is not None:
                decision.action = "search_more_evidence"
                decision.action_input = {"section": pending.section, "aspect": pending.aspect}
                decision.reasoning = f"Fallback: pending gap {pending.key()}"
            else:
                decision.action = _FINISH_ACTION
        return decision

    # -- checklist (detector 1) --------------------------------------------

    async def _run_checklist(self, trigger: str) -> list[GapTodo]:
        """LLM self-review, PER SECTION: exhaustive coverage + information density +
        compute-need. Mirrors ``fs_researcher_query_gen.plan_fs_researcher_queries``'s checklist
        critic (same status-leak screen), scoped to the current outline draft.

        Iter-2 P0-1 fix (saturated negative control invented gaps on a single-fact question):
        every deficiency line now REQUIRES a verbatim quote from the research question that
        names or directly implies the claimed missing aspect. A line whose quote does not
        literally appear in the question text is mechanically dropped — never silently kept on
        trust. This is the same grounding philosophy strict_verify already applies to generated
        prose (claim must trace to cited text), applied here to the GAP-DETECTION step itself so
        the loop cannot manufacture retrieval work the question never asked for. Question-
        agnostic: no domain/topic vocabulary is hardcoded, only the require-a-literal-quote
        discipline.

        Iter-4 P0-1 fix (Fable-confirmed real-corpus finding: on the locked 4-section DRB-72
        AI-labor deliverable this checklist proposed EXACTLY ONE recurring candidate — a
        phantom 'Summary Table' section that can never be homed under an exact-N-in-order
        contract — and NOTHING ELSE, on both the full and a deliberately-thinned corpus. The
        model was reading the question's cross-cutting-table sentence as its OWN section
        instead of decomposing it into per-section facets. The prompt now (a) closes the
        <section title> field to an EXACT copy of a listed current-outline title and explicitly
        instructs decomposition of any table/summary/cross-cutting request into per-section
        facets, with a worked example, and (b) as a mechanical backstop independent of prompt
        compliance, ``_best_remap_title`` routes any section label that still doesn't resolve
        to the existing section whose own topic (title+focus) the facet text overlaps most,
        before ever falling back to an unhomeable veto."""
        if not self.workspace.outline_draft:
            return []
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415
        from src.polaris_graph.retrieval.fs_researcher_query_gen import (  # noqa: PLC0415
            _screen_status_lines,
        )

        section_block = "\n".join(
            f"- {_plan_field(p, 'title', '')!r} (focus: {str(_plan_field(p, 'focus', ''))[:100]!r}, "
            f"{len(_plan_field(p, 'ev_ids', []) or [])} sources)"
            for p in self.workspace.outline_draft
        )
        title_list = ", ".join(
            repr(str(_plan_field(p, "title", "") or "")) for p in self.workspace.outline_draft
        )
        prompt = (
            "Self-review this outline against the research question. For EACH section, check: "
            "(a) exhaustive coverage — any aspect of that section's focus the assigned sources "
            "cannot answer?, (b) information density — any aspect backed by only 1-2 sources?, "
            "(c) compute need — does the section's focus imply a numeric comparison that has no "
            "supporting data?\n\n"
            "SECTION FIELD RULE (read carefully): the <section title> field of every line you "
            f"write MUST be an EXACT character-for-character copy of one of these existing "
            f"outline titles: {title_list}. Never write a section title that is not in that "
            "list — do not invent a new section, and do not name a separate deliverable-level "
            "artifact (a standalone summary table, an appendix, a references list, a "
            "conclusion) as if it were its own section. If the QUESTION asks for something "
            "that would naturally live in such a cross-cutting artifact (e.g. 'create a "
            "summary table covering application cases, impacts, and risks'), DECOMPOSE it: "
            "write one deficiency line PER underlying facet and assign each line to whichever "
            "EXISTING section above is topically closest to that facet (a facet about risks or "
            "limitations goes under whichever section already discusses risks/challenges; a "
            "facet about applications, industries, or opportunities goes under whichever "
            "section already discusses applications/opportunities; a facet about outcomes or "
            "effects goes under whichever section already discusses impacts/findings). Every "
            "existing section is a valid home for SOME facet — a table/summary request is "
            "never, by itself, a reason to list zero deficiencies.\n\n"
            "STRICT GROUNDING RULE (read carefully — this is a precision gate, not a recall "
            "gate): only flag a deficiency for an aspect that is EXPLICITLY named or directly "
            "implied by the wording of the QUESTION below. Do NOT invent generic sub-topics, "
            "background, history, mechanisms, or comparisons just because they would be "
            "'interesting to know' about the subject — if the question does not ask for it, it "
            "is not a deficiency. When you list a deficiency you MUST include a QUOTE: a short "
            "verbatim excerpt copied EXACTLY (same words, same characters, no added quotation "
            "marks of your own around it) from the QUESTION text that names the specific "
            "missing facet. A quote that is just the subject's name (e.g. only the topic noun) "
            "does NOT count — it must name the FACET (e.g. 'long-term cardiovascular safety', "
            "'compared with other agents', 'in specific populations', 'particular industries "
            "or occupations', 'key risk points'). If you cannot produce such a quote, do not "
            "list the line.\n\n"
            "If the question is a single, narrow, already-answered factual question, or every "
            "section is fully adequate, reply exactly NONE and list nothing else.\n\n"
            "Format each deficiency as ONE line, four fields separated by ' :: ':\n"
            "<section title, copied EXACTLY from the list above> :: <specific missing aspect> "
            ":: <coverage|density|numeric_rows> :: <verbatim quote from QUESTION>\n\n"
            "Example (question asks two things, sources only cover one) — CORRECT:\n"
            "Safety :: long-term cardiovascular safety :: coverage :: long-term cardiovascular "
            "safety\n"
            "Example (question asks for a cross-cutting summary table of application cases and "
            "risks across industries; outline has sections 'Opportunities' and 'Challenges') — "
            "CORRECT (decomposed into 2 lines, each under an EXISTING section):\n"
            "Opportunities :: specific application cases by industry or occupation :: coverage "
            ":: particular industries or occupations\n"
            "Challenges :: key risk points emphasized by researchers :: coverage :: key risk "
            "points emphasized by researchers\n"
            "WRONG for the same question: 'Summary Table :: application cases, impacts, and "
            "risks by industry :: coverage :: summary table' — this invents a section that "
            "isn't in the list above instead of decomposing into the existing sections.\n"
            "Example (single-fact question, already answered) — CORRECT reply: NONE\n"
            "Example of what NOT to do: inventing 'engineering mechanisms' or 'other tall "
            "structures' for a question that only asks a completion year — WRONG, do not do "
            "this.\n\n"
            f"QUESTION:\n{self.workspace.research_question}\n\nSECTIONS:\n{section_block}"
        )
        checklist_max_tokens = _env_int(
            "PG_OUTLINE_CHECKLIST_MAX_TOKENS", PG_OUTLINE_CHECKLIST_MAX_TOKENS_DEFAULT,
        )
        # Iter-6 P0 fix (Fable-directed, both halves REQUIRED):
        #   (1) root cause — pass an explicit ``reasoning_max_tokens`` so glm-5.2's
        #       unbounded-effort reasoning pool is BOUNDED within the (now much larger)
        #       total, instead of running unbounded until it eats the whole budget and
        #       leaves content empty (the exact ReasoningFirstTruncationError trace from
        #       matched_comparison_run5.log — same starved defaults iters 1-5 never fixed).
        #   (2) defense in depth — this is an INTERNAL control-plane call (a self-review, not
        #       verified prose); a transient truncation here must never be able to abort the
        #       whole outline stage. One retry at 2x budget (capped at the real glm-5.2
        #       provider ceiling), then fail-OPEN to "no new deficiencies this round" with a
        #       disclosed reason — mirrors the fail-open pattern already used by
        #       ``_tool_search_more_evidence``'s query-derive call just below.
        resp = None
        last_exc: Optional[Exception] = None
        for attempt, attempt_max_tokens in enumerate((
            checklist_max_tokens,
            min(checklist_max_tokens * 2, PG_GLM52_REAL_MAX_COMPLETION_TOKENS),
        )):
            client = OpenRouterClient(model=self.agent_model)
            try:
                resp = await client.generate(
                    prompt=prompt,
                    max_tokens=attempt_max_tokens,
                    temperature=0.2,
                    reasoning_max_tokens=_reasoning_max_tokens(),
                )
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001 — a checklist truncation must degrade, never crash
                last_exc = exc
                logger.warning(
                    "[outline_agent] checklist call failed (trigger=%s, attempt=%d, "
                    "max_tokens=%d): %s", trigger, attempt + 1, attempt_max_tokens, exc,
                )
            finally:
                if hasattr(client, "close"):
                    try:
                        await client.close()
                    except Exception:  # noqa: BLE001
                        pass
        if resp is None:
            self.workspace.disclose(
                f"checklist (trigger={trigger}) degraded fail-open after "
                f"{attempt + 1} attempt(s), treating as 'no new deficiencies this round': "
                f"{last_exc}"
            )
            return []

        raw_lines = [
            ln.strip("- ").strip() for ln in (resp.content or "").splitlines() if ln.strip()
        ]
        screened = _screen_status_lines(raw_lines, self.workspace.research_question)
        question_norm = _normalize_for_quote_check(self.workspace.research_question)
        new_todos: list[GapTodo] = []
        n_ungrounded = 0
        ungrounded_lines: list[str] = []
        n_unhomeable = 0
        unhomeable_lines: list[str] = []
        n_remapped = 0
        remapped_lines: list[str] = []
        for line in screened[:12]:
            if line.upper().strip() == "NONE":
                continue
            parts = [p.strip() for p in line.split("::")]
            if len(parts) < 4:
                # iter-2: a line without the mandatory quote field is UNGROUNDED by
                # construction — never kept on trust (fail-closed, not fail-open — this is
                # the precision gate the P0-1 fix requires, the mirror image of the
                # fail-open junk-deletion carve-out which governs a different job).
                n_ungrounded += 1
                ungrounded_lines.append(line[:160])
                continue
            section, aspect, kind_raw, quote = parts[0], parts[1], parts[2], parts[3]
            if not _quote_is_grounded(quote, question_norm):
                n_ungrounded += 1
                ungrounded_lines.append(line[:160])
                continue
            kind = kind_raw if kind_raw in ("coverage", "density", "numeric_rows") else "coverage"
            # Iter-3 P0 fix (real-corpus degeneration): a gap whose named section resolves to
            # NO current outline title, under a LOCKED required-structure deliverable (no room
            # to add a new section), can never be routed to retrieval — it is a deliverable-
            # level/formatting request (e.g. "Summary Table"), not a content gap. This is a
            # STRUCTURAL check (does the section resolve?), not a keyword/domain-vocabulary
            # guess, so it stays question-agnostic.
            #
            # Iter-4 P0-1 fix: before recording it UNFILLED, try `_best_remap_title` — a
            # mechanical (never-LLM) backstop that routes the facet to whichever EXISTING
            # section its own vocabulary overlaps most, independent of whether the prompt-level
            # decomposition instruction above was actually followed. This is what turns a
            # phantom-section "Summary Table" line into a genuine, retrievable content gap
            # against a real locked section instead of a permanent veto.
            if self.workspace.required_titles and self._resolve_section_title(section) is None:
                remap_title = self._best_remap_title(aspect)
                if remap_title is not None:
                    n_remapped += 1
                    remapped_lines.append(f"{section!r}->{remap_title!r}::{aspect[:60]}")
                    section = remap_title
                else:
                    self.workspace.gap_ledger.add_unfillable(
                        section=section, aspect=aspect,
                        reason=(
                            f"named section {section!r} does not match any of the locked "
                            f"required section titles {self.workspace.required_titles!r}, a new "
                            "section cannot be added under this deliverable's exact-structure "
                            "contract, and no existing section's own topic overlaps this facet's "
                            "vocabulary enough to remap it — this reads as a deliverable-level/"
                            "formatting request, not a retrievable content gap; recorded as a "
                            "structural limitation, not retried"
                        ),
                        needed_kind=kind, source="checklist",
                    )
                    # Iter-3 P1 fix: bank the SECTION LABEL itself (not the (section,aspect)
                    # pair) as proven-unhomeable — see `OutlineWorkspace.unhomeable_sections`
                    # docstring. A real THINNED-corpus run showed the checklist re-wording the
                    # ASPECT text each round (dodging the (section,aspect) paraphrase dedup)
                    # while the SECTION label stayed constant; vetoing by section label closes
                    # that gap.
                    self.workspace.unhomeable_sections.add(_normalize_section_label(section))
                    n_unhomeable += 1
                    unhomeable_lines.append(f"{section}::{aspect}")
                    continue
            todo = self.workspace.gap_ledger.add(
                section=section, aspect=aspect, needed_kind=kind, source="checklist",
            )
            new_todos.append(todo)
        if new_todos:
            self.workspace.disclose(
                f"checklist[{trigger}] named {len(new_todos)} gap(s): "
                + "; ".join(f"{t.section}::{t.aspect}" for t in new_todos[:6])
            )
        if n_remapped:
            self.workspace.disclose(
                f"checklist[{trigger}] remapped {n_remapped} facet(s) from a section label "
                "that did not match any locked required title onto the existing section its "
                "vocabulary overlaps most (iter-4 P0-1 fix — routes content instead of vetoing "
                "a format-only request): " + "; ".join(remapped_lines[:6])
            )
        if n_unhomeable:
            self.workspace.disclose(
                f"checklist[{trigger}] recorded {n_unhomeable} unhomeable gap(s) as UNFILLED "
                "(no matching section under the locked required-structure deliverable — "
                "structural limitation, never retried): " + "; ".join(unhomeable_lines[:6])
            )
        if n_ungrounded:
            # §-1.1 auditability fix: the OLD disclosure was a bare count — a reader could never
            # verify whether the anti-invention gate correctly rejected an invented sub-topic or
            # wrongly swallowed a REAL gap that just phrased its quote loosely. Surface the actual
            # dropped line text (truncated) so a line-by-line read can judge each one.
            self.workspace.disclose(
                f"checklist[{trigger}] dropped {n_ungrounded} ungrounded line(s) "
                "(no verbatim question quote — anti-invention gate, P0-1 fix): "
                + " | ".join(ungrounded_lines[:6])
            )
        if not new_todos and not n_ungrounded and not n_unhomeable:
            # Iter-2 telemetry fix: previously a genuine "the checklist ran and found NOTHING"
            # outcome (the correct behavior on a saturated/fully-covered outline) left ZERO trace
            # in `disclosures` — indistinguishable from the checklist never having been invoked at
            # all. That ambiguity made the W1 saturated acceptance test unable to tell "loop
            # legitimately declined to search" apart from "loop never got far enough to check".
            # Always disclose the checklist having run, even on a clean NONE verdict.
            self.workspace.disclose(f"checklist[{trigger}] ran: NONE (no grounded deficiencies)")
        return new_todos

    # -- detector 2: tool-failure deterministic ----------------------------

    def _tool_failure_gap_check(self, step: AnalysisStep) -> None:
        """Deterministic: empty comparison / zero datapoints / empty SQL / <2 studies -> auto
        todo. This is a ROUTING signal from a mechanical check (empty result), not a quality
        verdict about the corpus (§-1.1 — the mechanical check here fires a SEARCH action, it
        never states a quality number)."""
        result = step.result
        if step.tool_name in (
            "statistical_summary", "comparison_table", "meta_analysis", "query_evidence_sql",
        ):
            empty = (
                not result.success
                or (not result.data_points_produced and not result.statistics)
            )
            if empty:
                self.workspace.gap_ledger.add(
                    section="(unassigned)",
                    aspect=f"{step.tool_name} returned no usable rows — need more numeric data",
                    needed_kind="numeric_rows", source="tool_failure",
                )
        # W3 (2026-07-11): a FAILED compute was previously invisible here — the agent moved on with
        # no record that the number it wanted was never derived. Record it UNFILLABLE, not PENDING:
        # a compute failure is NOT retrievable, and a PENDING "(unassigned)" todo is routed to
        # search_more_evidence (decide rule 1, :1182) — which burns real web fetches on an error
        # string and can auto-assign a section literally titled "(unassigned)" (:1681). add_unfillable
        # lands it UNFILLED + disclosed immediately and it is never selected by next_pending().
        elif step.tool_name == "execute_python" and not result.success:
            # section="(compute)", NOT "(unassigned)": add_unfillable delegates to add(), which
            # paraphrase-collapses (Jaccard) against SAME-SECTION todos of ANY status. The
            # retrievable numeric_rows tool-failure gaps above also live in "(unassigned)", so a
            # reworded compute-failure aspect could collapse onto a genuine PENDING todo and flip it
            # to UNFILLED — silently killing a real search. A distinct section label removes the
            # collision surface; the todo is UNFILLED so the label is never routed anywhere.
            self.workspace.gap_ledger.add_unfillable(
                section="(compute)",
                aspect=(
                    f"execute_python failed ({result.error or 'unknown error'}) — the value it was "
                    f"asked to derive was NOT computed"
                ),
                reason="compute failure is not retrievable — no web fetch can fill it",
                needed_kind="computed_value", source="tool_failure",
            )

    def _compute_result_check(self, step: AnalysisStep) -> None:
        """W4 (2026-07-11): a SUCCESSFUL compute must be DISCLOSED and CARRIED, never silently
        dropped — and must NOT thereby become a render path.

        Before W4 a successful ``execute_python`` was the worst of both worlds: success meant
        ``_tool_failure_gap_check`` recorded NO gap (so nothing was disclosed), while the value it
        computed was discarded at every exit (``summary_for_llm`` stripped it; the cp4 checkpoint
        keeps only tool_name/reasoning/success; the entry-point return carried no notebook payload).
        An UNDISCLOSED UNREACHABLE RESULT — the tool burned a turn + an OpenRouterClient + a sandbox
        exec for zero observable effect, i.e. it was strictly net-NEGATIVE.

        What this does: records the computed statistics on the workspace (so they survive the exit,
        see :2049 ``notebook_compute``) and DISCLOSES them as EXPLORATORY.

        What this deliberately does NOT do (binding invariant, docs/agentic_outline_redesign.md):
        it does not stamp these numbers ``[#calc:]`` and does not hand them to the renderer.
        Exploratory ``execute_python`` output is BARRED from rendering. The verified lane
        (``tradeoff_modeler.ModelSpec`` -> ``quantified_analysis.execute_quantified_model``) accepts
        only ``SourcedInput``s carrying an evidence span (``ev_id`` + ``raw_literal`` +
        ``literal_start``/``literal_end``) and RE-DERIVES the number by re-executing a validated
        formula, pinning ``display_value``; ``verify_modeled_atom`` then re-checks the rendered digits
        against that re-execution. A bare ``{"npv": 1234567.89}`` returned by an LLM-written script
        has no evidence span and no re-derivable formula, so wrapping it in a ModelSpec would FORGE
        provenance through the only hard gate. The number therefore stays planner-facing until the
        verified lane derives it independently; the disclosure below is what keeps that honest
        instead of silent.
        """
        result = step.result
        if step.tool_name not in _CODEGEN_TOOLS or not result.success:
            return
        stats = result.statistics if isinstance(result.statistics, dict) else {}
        if not stats:
            return

        self.workspace.compute_results.append({
            "turn": step.step_number,
            "tool_name": step.tool_name,
            "reasoning": step.reasoning,
            "statistics": dict(stats),
            "insights": list(result.insights or []),
            "source_evidence_ids": list(result.source_evidence_ids or []),
            "renderable": False,
            "bar_reason": (
                "exploratory execute_python output — BARRED from rendering; a computed number may "
                "render only via the verified [#calc:] / ModelSpec lane, which re-derives it from "
                "sourced evidence spans"
            ),
        })
        pairs = ", ".join(f"{k}={v}" for k, v in stats.items())
        self.workspace.disclose(
            f"execute_python (turn {step.step_number}) computed {len(stats)} value(s) [{pairs}] — "
            "EXPLORATORY ONLY: visible to the planner, BARRED from the report. Rendering a computed "
            "number requires the verified [#calc:] lane to re-derive it from sourced evidence spans."
        )

    # -- execute ------------------------------------------------------------

    async def _execute(self, decision: ReactDecision) -> AnalysisStep:
        t0 = time.monotonic()
        # Iter-3 P1 fix (real THINNED-corpus run: 8 real search_more_evidence fetches, 31
        # genuinely new rows, ALL orphaned — the loop spent its ENTIRE retrieval budget
        # re-chasing the SAME "Summary Table" section label under 8 differently-worded aspects,
        # each individually terminated by the iter-3 P0 fix but never PREVENTED from being
        # tried again). VETO before spending any real wall-clock/tokens on a fetch whose target
        # section is already banked as structurally unhomeable this run — cheap, no network
        # call, no LLM call.
        veto_reason: Optional[str] = None
        if decision.action == "search_more_evidence":
            veto_sec = str((decision.action_input or {}).get("section", ""))
            if (
                _normalize_section_label(veto_sec) in self.workspace.unhomeable_sections
                and self.workspace.required_titles
                and self._resolve_section_title(veto_sec) is None
            ):
                veto_reason = (
                    f"section {veto_sec!r} already proven unhomeable this run (no matching "
                    f"required section title, required_titles="
                    f"{self.workspace.required_titles!r}) — vetoed before any real fetch, "
                    "regardless of aspect rewording"
                )
        tool_def = self.registry.get_tool(decision.action)
        if veto_reason is not None:
            result = ToolResult(
                success=False, tool_name=decision.action,
                markdown=f"search_more_evidence VETOED: {veto_reason}",
                error="unhomeable_section_vetoed",
            )
            self.workspace.disclose(f"search_more_evidence VETOED: {veto_reason}")
        elif not tool_def or not tool_def.execute:
            result = ToolResult(
                success=False, tool_name=decision.action,
                markdown=f"Unknown tool: {decision.action}", error="unknown_tool",
            )
        else:
            # W3 (2026-07-11): the dispatch used to hardcode ``client=None``, so execute_python
            # failed 100% of the time with "No LLM client available" (tool_registry.py:556) — while
            # still being advertised as available in the decide prompt. It now gets a real client on
            # the CODE model, per-call, closed on every exit path (mirrors _decide, :1203).
            # Gated on the tool that actually CONSUMES the client, not on requires_llm:
            # search_more_evidence is also requires_llm=True but ignores the kwarg and builds its own
            # clients internally (:1036), so gating on the flag would construct+close a wasted
            # OpenRouterClient on every search turn.
            code_client = None
            try:
                if decision.action in _CODEGEN_TOOLS:
                    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
                        OpenRouterClient,
                    )
                    code_client = OpenRouterClient(model=outliner_code_model())
                result = await tool_def.execute(
                    evidence_store=self.workspace.ev_store,
                    data_points=self.workspace.notebook.data_points,
                    client=code_client,
                    **(decision.action_input or {}),
                )
            except Exception as exc:  # noqa: BLE001 — a single tool must never crash the loop
                logger.warning("[outline_agent] tool %r raised: %s", decision.action, exc)
                result = ToolResult(
                    success=False, tool_name=decision.action,
                    markdown=f"Tool raised: {exc}", error=str(exc)[:500],
                )
            finally:
                if code_client is not None and hasattr(code_client, "close"):
                    try:
                        await code_client.close()
                    except Exception:  # noqa: BLE001
                        pass
        step = AnalysisStep(
            step_number=self.workspace.turn, reasoning=decision.reasoning,
            tool_name=decision.action, result=result,
            elapsed_seconds=round(time.monotonic() - t0, 3),
        )
        self.workspace.notebook.add_step(step)
        self._tool_failure_gap_check(step)
        self._compute_result_check(step)

        # Agent-initiated gap (detector 3): the decide step named a NEW section/aspect for
        # search_more_evidence that was not already a ledger entry -> record it.
        if decision.action == "search_more_evidence":
            inp = decision.action_input or {}
            sec, asp = str(inp.get("section", "")), str(inp.get("aspect", ""))
            if asp and veto_reason is not None:
                # Iter-3 P1 fix: a vetoed attempt must land STRAIGHT in UNFILLED, never PENDING
                # — routing it through the generic add()+mark_in_progress()+retry-cap cycle
                # would let it come back PENDING for up to `_gap_retries_per_aspect()` more
                # rounds (cheap now that the real fetch is skipped, but still churns turns).
                self.workspace.gap_ledger.add_unfillable(
                    section=sec, aspect=asp, reason=veto_reason, source="agent",
                )
            elif asp:
                existing = self.workspace.gap_ledger.get(sec, asp)
                if existing is None:
                    existing = self.workspace.gap_ledger.add(
                        section=sec, aspect=asp, source="agent",
                    )
                self.workspace.gap_ledger.mark_in_progress(existing)
                if not result.success:
                    # A fetch that found nothing on-topic never gets to "did it cover the
                    # aspect" — it plainly didn't fill anything.
                    self.workspace.gap_ledger.mark_retry_or_unfilled(
                        existing, f"search_more_evidence failed: {result.error}",
                    )
                else:
                    # Iter-2 P0-2 fix: a successful fetch used to leave the new rows orphaned in
                    # the pool — the outline never mutated, so the SAME gap kept re-firing every
                    # round and the loop could not converge. AUTO-ASSIGN the surviving new ev_ids
                    # to the section that triggered the search (a validated `reassign` op through
                    # the SAME outline_revise apply path `update_outline` uses — never a free
                    # rewrite) BEFORE the after-fold checklist re-runs, so the checklist judges
                    # the outline as it will actually ship, not the stale pre-fold draft.
                    new_ev_ids = list(result.source_evidence_ids or [])
                    resolved_title = self._resolve_section_title(sec)
                    unhomeable_agent_gap = False
                    if resolved_title and new_ev_ids:
                        assign_result = await _tool_update_outline(
                            self.workspace,
                            ops={"ops": [{
                                "op": "reassign", "title": resolved_title,
                                "add_ev_ids": new_ev_ids,
                            }]},
                        )
                        if assign_result.success:
                            self.workspace.disclose(
                                f"auto-assign: routed {len(new_ev_ids)} new ev_id(s) to "
                                f"section {resolved_title!r} (P0-2 fix — search fold-in now "
                                "mutates the outline instead of orphaning rows)"
                            )
                        else:
                            self.workspace.disclose(
                                f"auto-assign FAILED for section {resolved_title!r}: "
                                f"{assign_result.markdown}"
                            )
                    elif new_ev_ids and not self.workspace.required_titles:
                        # Iter-2 fix: found via a real live thin-run (nondeterministic re-run) —
                        # when the checklist names a gap section that does NOT exist in the
                        # current outline (e.g. the seed never created a dedicated "Cardiovascular
                        # Safety" section for a question that asks about it), the OLD behavior
                        # here was a permanent SKIP: the new rows sat orphaned in the pool, the
                        # SAME gap re-fired every round under a slightly different name
                        # ("Missing Section" / "Cardiovascular Safety" / "[No matching section]"
                        # / "Outline"), and the loop burned its entire turn budget re-searching
                        # the exact same aspect without ever converging. This ONLY applies when
                        # there is no deliverable required-structure lock (see the required_titles
                        # branch below, which correctly still SKIPs to protect an exact-N-in-order
                        # contract) — free-form outlines are allowed to grow a genuinely new
                        # section for a genuinely new gap, via the SAME validated `add` op
                        # `update_outline` already supports (never a free rewrite).
                        new_title = sec.strip() or "Additional Coverage"
                        add_result = await _tool_update_outline(
                            self.workspace,
                            ops={"ops": [{
                                "op": "add", "title": new_title,
                                "focus": asp or new_title, "ev_ids": new_ev_ids,
                            }]},
                        )
                        if add_result.success:
                            self.workspace.disclose(
                                f"auto-assign: no existing section matched {sec!r} — ADDED new "
                                f"section {new_title!r} with {len(new_ev_ids)} new ev_id(s) "
                                "(iter-2 fix — a named gap with no home no longer orphans rows)"
                            )
                        else:
                            self.workspace.disclose(
                                f"auto-assign SKIPPED: {sec!r} does not match any current "
                                f"outline section title, and adding a new section "
                                f"{new_title!r} failed ({add_result.markdown}) — "
                                f"{len(new_ev_ids)} new ev_id(s) stay in the pool"
                            )
                    elif new_ev_ids:
                        # A deliverable required-structure lock IS active — never grow a 5th
                        # section behind the caller's exact-N-in-order contract (§9.1.8 /
                        # outline_revise.py `required_titles`).
                        #
                        # Iter-4 P0-1 fix: before giving up, try the SAME mechanical remap
                        # backstop the checklist detector uses — route the fetched rows to the
                        # existing section whose own topic (title+focus) the aspect text
                        # overlaps most. This is what lets an agent-initiated gap (not just a
                        # checklist-named one) still land in a real section instead of
                        # orphaning a genuinely fetched, on-topic row.
                        remap_title = self._best_remap_title(asp)
                        if remap_title is not None:
                            assign_result = await _tool_update_outline(
                                self.workspace,
                                ops={"ops": [{
                                    "op": "reassign", "title": remap_title,
                                    "add_ev_ids": new_ev_ids,
                                }]},
                            )
                            if assign_result.success:
                                resolved_title = remap_title
                                self.workspace.disclose(
                                    f"auto-assign: {sec!r} did not match any locked required "
                                    f"section title, but its vocabulary overlaps existing "
                                    f"section {remap_title!r} the most — remapped and routed "
                                    f"{len(new_ev_ids)} new ev_id(s) there (iter-4 P0-1 fix)"
                                )
                            else:
                                remap_title = None  # fall through to the unhomeable path below
                        if remap_title is None:
                            # Iter-3 P0 fix: this used to fall through to the generic after-fold
                            # recheck+retry cycle below, which re-ran the checklist (which had NO
                            # way to see these orphaned rows as "assigned" since they were never
                            # folded into any section) — so the SAME agent-initiated gap re-armed
                            # itself as PENDING every round it hadn't yet hit the retry cap, and in
                            # parallel the checklist detector kept minting FRESH differently-worded
                            # todos for the same unhomeable target. Both paths compounded into the
                            # measured ~10-round, ~945s degeneration on the real S2S3 corpus. This
                            # gap is now terminated here: UNFILLED immediately, never retried, and
                            # the after-fold recheck below is skipped (nothing changed for it to
                            # re-judge — retrieval structurally cannot help).
                            unhomeable_agent_gap = True
                            reason = (
                                f"{sec!r} does not match any current outline section title, "
                                f"required_titles={self.workspace.required_titles} forbids "
                                "adding a new one, and no existing section's own topic overlaps "
                                f"this facet's vocabulary enough to remap it — {len(new_ev_ids)} "
                                "new ev_id(s) stay in the pool; this is a structural limitation "
                                "(deliverable-level/formatting request), not a retrievable "
                                "content gap — recorded UNFILLED, not retried"
                            )
                            self.workspace.disclose(f"auto-assign SKIPPED: {reason}")
                            existing.status = "UNFILLED"
                            existing.disclosure = reason
                            # Iter-3 P1 fix: bank the section label (see docstring + the
                            # checklist side of this same fix above) so a FUTURE agent-initiated
                            # attempt under different aspect wording is vetoed BEFORE spending a
                            # real fetch.
                            self.workspace.unhomeable_sections.add(_normalize_section_label(sec))
                    # Design control flow: "if search: fold-in + re-check aspect". A successful
                    # FETCH+ASSIGN is not the same claim as "the aspect is now covered" — re-run
                    # the checklist so a fresh judge decides whether this (section, aspect) is
                    # still named deficient against the ENLARGED, NOW-ASSIGNED corpus. Only mark
                    # COMPLETE when the checklist no longer names it; otherwise treat the fetch as
                    # a partial fill and retry/exhaust normally. This avoids a "fetched something,
                    # therefore gap filled" false-complete (the ghost mindset banned by
                    # CLAUDE.md §-1.1). SKIPPED for an unhomeable agent-initiated gap (iter-3 fix
                    # above) — nothing was assigned, so nothing changed for the checklist to
                    # re-judge; re-running it here is what regenerated the runaway.
                    if not unhomeable_agent_gap:
                        still_named = await self._run_checklist(trigger="after_fold")
                        still_deficient = any(
                            t.key() == existing.key() for t in still_named
                        )
                        if still_deficient:
                            self.workspace.gap_ledger.mark_retry_or_unfilled(
                                existing,
                                "search_more_evidence fetched rows but the after-fold checklist "
                                "still names this aspect deficient",
                            )
                        else:
                            self.workspace.gap_ledger.mark_complete(existing)

        self.workspace.checkpoint(event=f"turn_{self.workspace.turn}:{decision.action}")
        return step

    # -- main loop ------------------------------------------------------------

    async def run(self) -> OutlineWorkspace:
        ws = self.workspace
        await self._run_checklist(trigger="seed")
        ws.checkpoint(event="seed_checklist")

        while ws.turn < self.max_turns and ws.elapsed_seconds() < self.wall_seconds:
            ws.turn += 1
            try:
                decision = await self._decide()
            except Exception as exc:  # noqa: BLE001 — a decide failure ends the loop, not the run
                logger.warning("[outline_agent] decide failed at turn %d: %s", ws.turn, exc)
                ws.disclose(f"decide failed at turn {ws.turn}: {exc}; stopping loop")
                break

            if decision.action == _FINISH_ACTION:
                deficiencies = await self._run_checklist(trigger=f"finish_attempt_turn_{ws.turn}")
                pending = ws.gap_ledger.pending_count
                budget_remains = ws.turn < self.max_turns and ws.elapsed_seconds() < self.wall_seconds
                if (deficiencies or pending) and budget_remains:
                    ws.disclose(
                        f"finish_outline BOUNCED at turn {ws.turn}: "
                        f"{len(deficiencies)} new + {pending} pending gap(s) remain, "
                        "budget available — continuing loop"
                    )
                    continue
                ws.disclose(
                    f"finish_outline ACCEPTED at turn {ws.turn}: "
                    f"pending={pending}, budget_remains={budget_remains}"
                )
                break

            await self._execute(decision)

        # Any todo still PENDING at exit — whether it was retried to the cap or NEVER attempted
        # (turns/wall ran out before the agent ever picked it up) — is honestly UNFILLED, not
        # silently dropped. The two reasons are disclosed distinctly (§-1.3: every gap that
        # wasn't filled is disclosed, never silently absent from the coverage/limitations trail).
        for todo in ws.gap_ledger.all_todos:
            if todo.status == "PENDING":
                reason = (
                    "budget exhausted after retries" if todo.attempts > 0
                    else "budget exhausted before this gap was ever searched"
                )
                todo.status = "UNFILLED"
                todo.disclosure = reason

        ws.checkpoint(event="exit")
        return ws

    def _max_retries_display(self) -> int:
        return self.workspace.gap_ledger._max_retries  # noqa: SLF001 — same-module access


# ---------------------------------------------------------------------------
# Entry point — wired at the multi_section_generator `_call_outline` seam.
# ---------------------------------------------------------------------------

async def run_outline_agent_or_legacy(
    research_question: str,
    evidence: list[dict[str, Any]],
    gen_model: str,
    outline_temperature: float,
    outline_max_tokens: int,
    *,
    domain: str = "",
    finding_clusters: Any = None,
    deliverable_spec: Any = None,
    scope_spec: Any = None,
    same_work_groups: Any = None,
    checkpoint_dir: Optional[str] = None,
) -> tuple[Any, bool, int, int]:
    """Seam entry point. OFF (``PG_OUTLINE_AGENT`` unset/0) => calls ``_call_outline`` exactly
    as before and returns its result untouched (byte-identical legacy path — this function does
    NOT even import the agent-loop machinery on the OFF path beyond this module's top-level
    imports, which are cheap/side-effect-free). ON => seeds via the SAME ``_call_outline`` call
    (using the CODE model per §9.1.8 lock), then runs the ``OutlineAgent`` loop over the seeded
    plans, and returns an updated result of the SAME shape the caller already expects."""
    from src.polaris_graph.generator.multi_section_generator import _call_outline  # noqa: PLC0415

    if not outline_agent_enabled():
        return await _call_outline(
            research_question, evidence, gen_model, outline_temperature, outline_max_tokens,
            domain=domain, finding_clusters=finding_clusters,
            deliverable_spec=deliverable_spec, scope_spec=scope_spec,
            same_work_groups=same_work_groups,
        )

    seed_model = outliner_code_model()
    parse_result, retry_attempted, in_tok, out_tok = await _call_outline(
        research_question, evidence, seed_model, outline_temperature, outline_max_tokens,
        domain=domain, finding_clusters=finding_clusters,
        deliverable_spec=deliverable_spec, scope_spec=scope_spec,
        same_work_groups=same_work_groups,
    )
    if not parse_result.plans:
        logger.info("[outline_agent] seed produced zero plans — skipping agent loop (fail-open)")
        return parse_result, retry_attempted, in_tok, out_tok

    ev_store = {
        str(row.get("evidence_id")): row for row in evidence
        if isinstance(row, dict) and row.get("evidence_id")
    }
    basket_menu = None
    try:
        from src.polaris_graph.generator.outline_digest import build_outline_digest  # noqa: PLC0415
        basket_menu = build_outline_digest(
            evidence, finding_clusters or [], same_work_groups=same_work_groups,
            prioritize_tier1=True,
        )
    except Exception as exc:  # noqa: BLE001 — basket digest is an aid, never a hard requirement
        logger.warning("[outline_agent] basket digest build failed (fail-open): %s", exc)

    # Snapshot the SEED plan's per-section ev_ids BEFORE the loop runs, so a caller (and the W1
    # acceptance harness) can measure whether the outline actually mutated instead of trusting a
    # bare final count — and so this is the ACTUAL seed the loop started from, not a second
    # independent (nondeterministic) outline call.
    seed_ev_by_title = {p.title: list(p.ev_ids) for p in parse_result.plans}

    # Iter-2 P2-1 fix (was mis-reported as "new_evidence_count=0" every run): ``OutlineWorkspace``
    # is handed ``ev_store`` BY REFERENCE (not a copy) and the loop mutates it in place via
    # ``search_more_evidence``'s fold-in, so ``final_ws.ev_store is ev_store`` — the SAME dict
    # object. Any comparison of ``len(ev_store)`` computed AFTER the loop against
    # ``len(final_ws.ev_store)`` is comparing an object against itself and is always 0. This also
    # broke the "feed newly-fetched rows back into `evidence`" loop below (the exact same
    # aliasing made every row look like it was "already in ev_store", so it silently fed back
    # ZERO rows — the agent-fetched corpus never reached the caller's `evidence` list at all).
    # Snapshot the id SET before the loop runs; every later comparison is against this snapshot,
    # never against the (now-mutated) live dict.
    ev_ids_before = set(ev_store.keys())
    ev_store_size_before = len(ev_ids_before)

    # Iter-2 fix: thread the deliverable's required-structure lock (if any) through to the
    # workspace so `_tool_update_outline` (via `apply_revision_ops(required_titles=...)`) and the
    # auto-assign fallback both respect it — an exact-N-in-order required structure must never
    # silently grow a 5th section behind the caller's back. Mirrors `_call_outline`'s own
    # `_spec_read(deliverable_spec, "required_sections", [])` read (dict OR object shape).
    _required_titles = [
        str(t).strip()
        for t in (
            deliverable_spec.get("required_sections", [])
            if isinstance(deliverable_spec, dict)
            else getattr(deliverable_spec, "required_sections", [])
        ) or []
        if str(t).strip()
    ]
    workspace = OutlineWorkspace(
        research_question=research_question,
        ev_store=ev_store,
        outline_draft=list(parse_result.plans),
        basket_menu=basket_menu,
        checkpoint_dir=checkpoint_dir,
        total_input_tokens=in_tok,
        total_output_tokens=out_tok,
        required_titles=_required_titles,
    )
    agent = OutlineAgent(workspace, domain=domain or None)
    # W2 P0 fix (Fable-authoritative, 2026-07-11): this call used to be BARE. On the dense
    # full-corpus real run a single glm-5.2 ``ReasoningFirstTruncationError`` (reasoning
    # prelude alone exceeding the completion budget) — or ANY other exception, or the loop
    # simply running past its own wall-clock without ``_decide``/``_run_checklist`` ever
    # returning control — propagated straight out of ``agent.run()``, out of THIS function,
    # and aborted the entire outline stage; the caller (``multi_section_generator``) then fell
    # back to the PLAIN non-agentic outliner. That is a silent capability downgrade the operator
    # never asked for (LAW II). The fix DEGRADES TO SEED instead: ``workspace`` is the exact
    # same object ``agent`` was constructed with, and every mutation the loop makes (fold-ins,
    # revisions, ledger updates) is applied to it IN PLACE and checkpointed after every turn —
    # so on any failure ``workspace`` already holds the SEED outline merged with whatever
    # agentic turns completed before the failure, never a blank/plain fallback. The outer
    # ``asyncio.wait_for`` is belt-and-suspenders on top of the loop's own internal
    # turns/wall-clock check (a single hung LLM call inside one turn must not be able to wedge
    # the whole stage past the caller's own upstream timeout).
    degraded_to_seed = False
    degrade_reason = ""
    try:
        final_ws = await asyncio.wait_for(
            agent.run(),
            timeout=agent.wall_seconds + _env_int(
                "PG_OUTLINE_AGENT_RUN_TIMEOUT_GRACE_SECONDS",
                PG_OUTLINE_AGENT_RUN_TIMEOUT_GRACE_SECONDS_DEFAULT,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — degrade to SEED, never abort the outline stage
        degraded_to_seed = True
        degrade_reason = f"{type(exc).__name__}: {exc}"
        workspace.disclose(
            f"agentic outline loop ABORTED after {workspace.turn} completed turn(s) "
            f"({degrade_reason}) — DEGRADING TO SEED outline merged with whatever agentic "
            "turns completed before the failure (never falls back to plain non-agentic "
            "outline)"
        )
        workspace.checkpoint(event="agent_run_aborted_degrade_to_seed")
        logger.warning(
            "[outline_agent] agent.run() aborted, degrading to seed+partial-turns state: %s",
            degrade_reason,
        )
        final_ws = workspace

    parse_result.plans = list(final_ws.outline_draft)  # type: ignore[assignment]
    parse_result.digest_stats = dict(parse_result.digest_stats or {})
    parse_result.digest_stats["outline_agent"] = {
        "cp4_used": "agentic-degraded-seed" if degraded_to_seed else "agentic",
        "degraded_to_seed": degraded_to_seed,
        "degrade_reason": degrade_reason,
        "turns": final_ws.turn,
        "elapsed_seconds": round(final_ws.elapsed_seconds(), 1),
        "ev_store_size": len(final_ws.ev_store),
        "ev_store_size_at_seed": ev_store_size_before,
        "new_evidence_count": len(final_ws.ev_store) - ev_store_size_before,
        "gap_ledger": final_ws.gap_ledger.as_list(),
        "unfilled_gaps": [dataclasses.asdict(t) for t in final_ws.gap_ledger.unfilled],
        "disclosures": list(final_ws.disclosures),
        # W4: the computed values a successful execute_python produced. Before this the
        # entry-point return carried NO notebook payload at all, so the value died here.
        # EXPLORATORY: every row is renderable=False; the report may render a computed
        # number ONLY through the verified [#calc:] lane. Manifest/telemetry only — grep
        # confirms digest_stats never reaches a writer prompt.
        "notebook_compute": list(final_ws.compute_results),
        "seed_ev_by_title": seed_ev_by_title,
        "final_ev_by_title": {
            _plan_field(p, "title", ""): list(_plan_field(p, "ev_ids", []) or [])
            for p in final_ws.outline_draft
        },
    }
    # Feed the enlarged evidence pool back so downstream fold-in (evidence_for_gen etc.) sees
    # the new rows too — the caller reads `evidence` by reference in most call sites, but to
    # stay honest under any calling convention this is ALSO returned via digest_stats above.
    # (iter-2 fix: compare against the PRE-loop id snapshot, not the aliased live dict — see note
    # above; this is the actual corpus feed-back path and was silently a no-op before this fix.)
    for eid, row in final_ws.ev_store.items():
        if eid and eid not in ev_ids_before:
            evidence.append(row)

    return parse_result, retry_attempted, final_ws.total_input_tokens, final_ws.total_output_tokens
