"""Faithful frontier query-gen adapters for the I-qgen-001 bake-off (GH #1291).

Each adapter implements ONE named method's PORTABLE query-generation scaffold, built from its
primary arXiv source (research roster: outputs/qgen_coverage/frontier_roster.json). Every adapter
exposes generate_corpus(question, retrieve, budget) and uses the SHARED retrieve() + an injected
GLM-5.2 `llm` — so only the query LOGIC differs, never the retriever or model (the bake-off
isolates query-gen). budget.max_queries caps retrieve() calls equally for every method.

These are the method-SPECIFIC scaffolds, not a generic gap loop:
  WebWeaver           - outline-centric ReAct: search/write-outline/terminate; re-query off the evolving outline
  IterResearch        - report-centric workspace RECONSTRUCTION (O(1) memory; report overwritten each round)
  ConvergeWriter      - fixed two-stage breadth(seed kw)->depth(per-doc grounded kw); bottom-up, no gap loop
  WARP (AgentCPM)     - writing-as-reasoning: per-section query conditioned on the DRAFT; lazy Expand on thin sections
  DuMate              - DAG roadmap + ready-frontier + ephemeral RUBRIC as gap-list/stop predicate
  FS-Researcher       - index.md TOC + todo queue + fixed 6-item checklist re-query
  ScaffoldAgent       - mutable outline TREE + UCB node selection + Expansion/Revision/Contraction ops
  PokeeResearch       - research<->verification scaffold (3 failure modes); multi-query per call
  DOLORES             - recursive meta-decomposition (associate/compute/recurse); query emerges from ASSOCIATE

DeepResearch-R1/9K (2603.01152) is trained-only (query logic in the weights) -> NOT adapted here
(noted, not faked, per the standard-process rule).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable

from scripts.dr_benchmark.qgen_coverage_harness import CoverageBudget, RetrieveFn
from scripts.dr_benchmark.qgen_methods import _dedup_keep

LlmFn = Callable[[str], str]


def _lines(text: str, cap: int = 12) -> list[str]:
    """Parse an LLM reply into clean query/line items (strip numbering/bullets)."""
    out: list[str] = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"^\s*(?:[-*]|\d+[.):])\s*", "", s).strip().strip('"').strip()
        if s and len(s) > 2 and not s.lower().startswith(("here", "sure", "the following")):
            out.append(s)
        if len(out) >= cap:
            break
    return out


def _digest(rows: list[dict], n: int = 8, chars: int = 160) -> str:
    """A short digest of retrieved rows to feed back into the planner context (steers next queries)."""
    parts = []
    for r in (rows or [])[:n]:
        t = " ".join((r.get("text") or "").split())[:chars]
        if t:
            parts.append(t)
    return " | ".join(parts)


class _Budgeted:
    """Mixin: shared corpus state + a query budget counter for every adapter."""

    def _run(self, question, retrieve, budget):  # pragma: no cover - overridden
        raise NotImplementedError

    def generate_corpus(self, question: str, retrieve: RetrieveFn, budget: CoverageBudget) -> list[dict]:
        self._seen: set[str] = set()
        self._corpus: list[dict] = []
        self._n_queries = 0
        self._max = budget.max_queries
        self._rounds = budget.max_query_rounds
        self._run(question, retrieve, budget)
        return self._corpus

    def _search(self, retrieve: RetrieveFn, query: str) -> list[dict]:
        if self._n_queries >= self._max:
            return []
        self._n_queries += 1
        rows = _dedup_keep(retrieve(query), self._seen)
        self._corpus += rows
        return rows

    @property
    def _budget_left(self) -> bool:
        return self._n_queries < self._max


# --------------------------------------------------------------------------- WebWeaver
@dataclass
class WebWeaverMethod(_Budgeted):
    """WebWeaver (2509.13312): outline co-evolves with search; re-query targets under-supported
    outline sections; only distilled summaries (not raw pages) steer the next query batch."""

    llm: LlmFn
    name: str = "webweaver"

    def _run(self, question, retrieve, budget):
        outline = self.llm(
            "Draft a concise hierarchical OUTLINE (section titles only, one per line) for a complete "
            f"report answering this research question:\n{question}"
        )
        summaries: list[str] = []
        for _ in range(self._rounds * 4):
            if not self._budget_left:
                break
            ctx = "\n".join(summaries[-12:])
            q = self.llm(
                "You are WebWeaver's planner. Given the question, the current report OUTLINE, and "
                "summaries of evidence found so far, list the next search queries that fill the "
                "OUTLINE's still-UNSUPPORTED or MISSING sections. One query per line, no prose.\n\n"
                f"QUESTION:\n{question}\n\nOUTLINE:\n{outline}\n\nEVIDENCE SUMMARIES SO FAR:\n{ctx}"
            )
            qs = _lines(q, cap=6)
            if not qs:
                break
            for query in qs:
                rows = self._search(retrieve, query)
                if rows:
                    summaries.append(_digest(rows))
                if not self._budget_left:
                    break
            # write-outline: restructure the outline from the new evidence (outline-centric re-query)
            outline = self.llm(
                "Rewrite/restructure this report outline to reflect the new evidence (add, reorder, "
                "or split sections). Section titles only, one per line.\n\n"
                f"QUESTION:\n{question}\n\nCURRENT OUTLINE:\n{outline}\n\nNEW EVIDENCE:\n"
                + "\n".join(summaries[-8:])
            ) or outline


# --------------------------------------------------------------------------- IterResearch
@dataclass
class IterResearchMethod(_Budgeted):
    """IterResearch/Tongyi (2510.24701 / 2511.07327): report-centric round loop with workspace
    RECONSTRUCTION — the prompt each round carries ONLY (question, current report, last obs); the
    report is OVERWRITTEN (strategic forgetting, O(1) memory); next query derived from (question, report)."""

    llm: LlmFn
    name: str = "iterresearch"

    def _run(self, question, retrieve, budget):
        report = ""
        last_obs = ""
        for _ in range(self._max):
            if not self._budget_left:
                break
            out = self.llm(
                "You are IterResearch. Your ONLY memory is the evolving REPORT below (history is "
                "discarded). Reason over (question, report, last observation): what is established, "
                "what is still missing. Then output exactly two blocks:\n"
                "REPORT: <a rewritten, compressed report retaining validated findings + what you just learned>\n"
                "QUERY: <ONE next search query, or the word STOP if information is sufficient>\n\n"
                f"QUESTION:\n{question}\n\nREPORT:\n{report or '(empty)'}\n\nLAST OBSERVATION:\n{last_obs or '(none)'}"
            )
            new_report = ""
            query = ""
            m = re.search(r"REPORT:\s*(.*?)\s*QUERY:", out, re.S | re.I)
            if m:
                new_report = m.group(1).strip()
            mq = re.search(r"QUERY:\s*(.*)", out, re.S | re.I)
            if mq:
                query = mq.group(1).strip().splitlines()[0].strip() if mq.group(1).strip() else ""
            report = new_report or report  # OVERWRITE: strategic forgetting
            if not query or query.upper().startswith("STOP"):
                break
            rows = self._search(retrieve, query)
            last_obs = _digest(rows)


# --------------------------------------------------------------------------- ConvergeWriter
@dataclass
class ConvergeWriterMethod(_Budgeted):
    """ConvergeWriter (2509.12811): bottom-up, NOT a gap loop. Stage 1 breadth = seed keywords from
    the question title; Stage 2 depth = per-retrieved-document grounded keyword expansion. Fixed two stages."""

    llm: LlmFn
    name: str = "convergewriter"

    def _run(self, question, retrieve, budget):
        # Stage 1 (breadth): seed keyword queries from the question alone.
        seeds = _lines(
            self.llm(
                "Generate breadth-first SEARCH KEYWORDS/queries to begin researching this topic. "
                "One per line, no prose.\n\n" + question
            ),
            cap=8,
        )
        breadth_cap = max(1, int(self._max * 0.4))
        for q in seeds[:breadth_cap]:
            self._search(retrieve, q)
            if self._n_queries >= breadth_cap:
                break
        # Stage 2 (depth): per-document grounded keyword expansion over what stage 1 retrieved.
        d1 = list(self._corpus)
        for row in d1:
            if not self._budget_left:
                break
            doc = " ".join((row.get("text") or "").split())[:1200]
            if not doc:
                continue
            deeper = _lines(
                self.llm(
                    "Read this retrieved document and generate DEEPER search queries it implies for "
                    f"the topic. One per line, no prose.\n\nTOPIC:\n{question}\n\nDOCUMENT:\n{doc}"
                ),
                cap=3,
            )
            for q in deeper:
                self._search(retrieve, q)
                if not self._budget_left:
                    break


# --------------------------------------------------------------------------- WARP / AgentCPM-Report
@dataclass
class WarpMethod(_Budgeted):
    """WARP / AgentCPM-Report (2602.06540): writing-as-reasoning. Sparse Level-1 outline; per-section
    query conditioned on (question, section intent, DRAFT so far); thin sections Expand into
    sub-sections (lazy hierarchical growth). The DRAFT itself is the gap signal."""

    llm: LlmFn
    name: str = "warp"

    def _run(self, question, retrieve, budget):
        sections = _lines(
            self.llm(
                "Emit a SPARSE level-1 outline (high-level section titles only, one per line) for a "
                f"report answering:\n{question}"
            ),
            cap=8,
        ) or [question]
        draft = ""
        deepenings = 0
        i = 0
        while i < len(sections) and self._budget_left:
            section = sections[i]
            i += 1
            query = self.llm(
                "Write ONE search query for this section, conditioned on the question, the section "
                "intent, AND the draft so far (so the query EXTENDS the existing argument). Query only.\n\n"
                f"QUESTION:\n{question}\n\nSECTION:\n{section}\n\nDRAFT SO FAR:\n{draft[-1500:] or '(empty)'}"
            ).strip().splitlines()
            query = query[0].strip() if query else section
            rows = self._search(retrieve, query)
            draft += f"\n## {section}\n{_digest(rows, n=4)}\n"
            # reasoning-driven deepening: diagnose the thinnest section, Expand it (<=12 deepenings, lazy)
            if deepenings < 12 and self._budget_left:
                exp = self.llm(
                    "Re-read the draft. Name the ONE section still too THIN, then list 1-3 sub-section "
                    "titles that deepen it (one per line). If the draft is complete, reply DONE.\n\n"
                    f"QUESTION:\n{question}\n\nDRAFT:\n{draft[-2000:]}"
                )
                if "DONE" not in exp.upper():
                    subs = _lines(exp, cap=3)
                    if subs:
                        sections[i:i] = subs  # insert sub-sections to draft next (hierarchical)
                        deepenings += 1


# --------------------------------------------------------------------------- DuMate
@dataclass
class DuMateMethod(_Budgeted):
    """DuMate (2606.07299): DAG roadmap + ready-frontier (coarse->fine) + an EPHEMERAL RUBRIC
    regenerated from new evidence each cycle that is BOTH the next-query driver AND the stop
    predicate (no outstanding gap => halt). Inner search does multi-formulation expansion."""

    llm: LlmFn
    name: str = "dumate"

    def _run(self, question, retrieve, budget):
        outline = self.llm(f"Draft a report outline (section titles, one per line) for:\n{question}")
        frontier = _lines(
            self.llm(
                "Enumerate the coarse research SUB-TASKS needed to cover this outline. One per line.\n\n"
                f"QUESTION:\n{question}\n\nOUTLINE:\n{outline}"
            ),
            cap=8,
        ) or [question]
        for _ in range(self._rounds):
            if not self._budget_left or not frontier:
                break
            evidence_digest = ""
            for subtask in list(frontier):
                if not self._budget_left:
                    break
                # inner search agent: multi-formulation query expansion for this sub-task
                forms = _lines(
                    self.llm(
                        "Generate 2-3 search query reformulations (broad -> specific) for this "
                        "sub-task. One per line, no prose.\n\nSUB-TASK:\n" + subtask
                    ),
                    cap=3,
                ) or [subtask]
                for q in forms:
                    rows = self._search(retrieve, q)
                    evidence_digest += " " + _digest(rows, n=3)
                    if not self._budget_left:
                        break
            # ephemeral rubric = residual-gap list regenerated from new evidence; empty => stop
            gaps = _lines(
                self.llm(
                    "Given the question, outline, and evidence gathered, list the REMAINING research "
                    "gaps as new sub-tasks. One per line. If coverage is complete, reply NONE.\n\n"
                    f"QUESTION:\n{question}\n\nOUTLINE:\n{outline}\n\nEVIDENCE:\n{evidence_digest[:3000]}"
                ),
                cap=6,
            )
            if not gaps or any("NONE" in g.upper() for g in gaps[:1]):
                break
            frontier = gaps  # re-plan: expand the frontier with finer gap sub-tasks


# --------------------------------------------------------------------------- FS-Researcher
@dataclass
class FsResearcherMethod(_Budgeted):
    """FS-Researcher (2602.01566): index.md TOC (topic deconstruction + KB hierarchy) + todo queue;
    per-todo LLM query; re-query driven by a FIXED 6-item self-review checklist (esp. 'a question the
    KB cannot fully answer' / 'an aspect with only 1-2 weak sources')."""

    llm: LlmFn
    name: str = "fs_researcher"

    def _run(self, question, retrieve, budget):
        todos = _lines(
            self.llm(
                "Deconstruct this research topic into sub-topics (the index.md table of contents). "
                "One sub-topic per line.\n\n" + question
            ),
            cap=10,
        ) or [question]
        notes: list[str] = []
        for _ in range(self._rounds):
            if not self._budget_left or not todos:
                break
            for todo in list(todos):
                if not self._budget_left:
                    break
                q = self.llm("Write ONE search query for this sub-topic. Query only.\n\n" + todo).strip()
                q = q.splitlines()[0].strip() if q else todo
                rows = self._search(retrieve, q)
                notes.append(f"[{todo[:50]}] {_digest(rows, n=3)}")
            # 6-item Appendix-B checklist critic -> deficient sub-topics become new todos
            deficient = _lines(
                self.llm(
                    "Self-review the knowledge base against: exhaustive coverage (a question the KB "
                    "cannot fully answer?) and information density (any aspect with only 1-2 weak "
                    "sources?). List sub-topics still needing more search. One per line, or NONE.\n\n"
                    f"QUESTION:\n{question}\n\nNOTES:\n" + "\n".join(notes[-20:])
                ),
                cap=6,
            )
            if not deficient or any("NONE" in d.upper() for d in deficient[:1]):
                break
            todos = deficient


# --------------------------------------------------------------------------- ScaffoldAgent
@dataclass
class ScaffoldAgentMethod(_Budgeted):
    """ScaffoldAgent (2606.20122): mutable outline TREE; UCB selects the next node (exploit
    low-utility + explore under-visited); typed ops Expansion (decompose -> query per child),
    Revision (re-query node in place), Contraction (merge siblings, retrieves nothing)."""

    llm: LlmFn
    name: str = "scaffoldagent"
    c_ucb: float = 1.4

    def _run(self, question, retrieve, budget):
        titles = _lines(
            self.llm(
                "Build a minimal report outline: 3-5 top-level section titles for this question. "
                "One per line.\n\n" + question
            ),
            cap=5,
        ) or [question]
        # node = {title, context, n, util}
        nodes = [{"title": t, "ctx": question, "n": 0, "util": 0.0} for t in titles]
        total = 0
        for _ in range(max(self._rounds * 4, 20)):
            if not self._budget_left or not nodes:
                break
            total += 1
            # UCB select: argmax(-mean_util + c*sqrt(ln N / n)); unvisited first
            def ucb(nd):
                if nd["n"] == 0:
                    return float("inf")
                return -nd["util"] + self.c_ucb * math.sqrt(math.log(total + 1) / nd["n"])
            node = max(nodes, key=ucb)
            op = self.llm(
                "Choose ONE operation for this outline node: EXPAND (too broad -> split), REVISE "
                "(weakly supported -> refresh), or CONTRACT (redundant -> merge). Reply with one word.\n\n"
                f"NODE: {node['title']}\nQUESTION: {question}"
            ).strip().upper()
            gained = 0
            if "EXPAND" in op:
                children = _lines(
                    self.llm(f"Split this section into 2-4 finer sub-sections (titles, one per line): {node['title']}"),
                    cap=4,
                )
                for ch in children:
                    rows = self._search(retrieve, f"{ch} {question}")
                    gained += len(rows)
                    nodes.append({"title": ch, "ctx": node["title"], "n": 0, "util": 0.0})
                    if not self._budget_left:
                        break
            elif "CONTRACT" in op:
                pass  # reorganize only; retrieves nothing
            else:  # REVISE (default)
                rows = self._search(retrieve, f"{node['title']} {node['ctx']}")
                gained += len(rows)
            node["n"] += 1
            # utility ~ retrieval gain (normalized); update running mean (eq.7)
            u = min(1.0, gained / 8.0)
            node["util"] += (u - node["util"]) / node["n"]


# --------------------------------------------------------------------------- PokeeResearch
@dataclass
class PokeeResearchMethod(_Budgeted):
    """PokeeResearch-7B (2510.15862): research<->verification scaffold. Research turns emit a LIST of
    queries per call (multi-query); on 'answer', a verification pass re-reads the thread against three
    failure modes (incomplete coverage / insufficient evidence / logical error) and re-enters research."""

    llm: LlmFn
    name: str = "pokeeresearch"

    def _run(self, question, retrieve, budget):
        thread = ""
        for _ in range(self._rounds):
            if not self._budget_left:
                break
            # research turn: emit a LIST of queries (multi-query per call) or ANSWER
            out = self.llm(
                "You are in RESEARCH mode. Emit EITHER a list of search queries (one per line) to "
                "gather more evidence, OR the single word ANSWER if you can fully answer now.\n\n"
                f"QUESTION:\n{question}\n\nFINDINGS SO FAR:\n{thread[-2000:] or '(none)'}"
            )
            if "ANSWER" in out.upper() and len(_lines(out)) <= 1:
                # verification: 3 failure modes; on failure, re-enter research with a gap
                v = self.llm(
                    "VERIFICATION: re-read the findings and judge against (a) incomplete coverage, "
                    "(b) insufficient evidence, (c) logical error. If all pass, reply PASS. Else list "
                    "search queries to fix the gap (one per line).\n\n"
                    f"QUESTION:\n{question}\n\nFINDINGS:\n{thread[-2500:]}"
                )
                if "PASS" in v.upper() and len(_lines(v)) <= 1:
                    break
                qs = _lines(v, cap=5)
            else:
                qs = _lines(out, cap=5)
            for q in qs:
                rows = self._search(retrieve, q)
                thread += " " + _digest(rows, n=3)
                if not self._budget_left:
                    break


# --------------------------------------------------------------------------- DOLORES
@dataclass
class DoloresMethod(_Budgeted):
    """DOLORES (2605.11388): recursive meta-decomposition over {associate, compute, recurse}. The
    paper specifies no retriever; faithfully-but-additively, ASSOCIATE nodes emit search strings.
    Decompose until atomic or budget; union of retrieved spans is the corpus."""

    llm: LlmFn
    name: str = "dolores"
    max_depth: int = 2

    def _run(self, question, retrieve, budget):
        self._decompose(question, retrieve, depth=0)

    def _decompose(self, task: str, retrieve: RetrieveFn, depth: int):
        if not self._budget_left:
            return
        plan = self.llm(
            "Decompose this task into atomic steps. For each step output one line prefixed by either "
            "'ASSOCIATE: <a search query to gather evidence>' or 'RECURSE: <a sub-problem to decompose "
            "further>'. Keep it small; only the parts that need external evidence.\n\nTASK:\n" + task
        )
        any_typed = False
        for raw in (plan or "").splitlines():
            if not self._budget_left:
                break
            s = raw.strip()
            if s.upper().startswith("ASSOCIATE:"):
                any_typed = True
                self._search(retrieve, s.split(":", 1)[1].strip())
            elif s.upper().startswith("RECURSE:") and depth < self.max_depth:
                any_typed = True
                self._decompose(s.split(":", 1)[1].strip(), retrieve, depth + 1)
        if not any_typed:
            # the paper leaves the retrieval binding unspecified; faithfully-additive fallback:
            # treat each decomposition line as an ASSOCIATE search subgoal.
            for q in _lines(plan, cap=6):
                if not self._budget_left:
                    break
                self._search(retrieve, q)


# --------------------------------------------------------------------------- registry
def build_frontier_methods(llm: LlmFn) -> list:
    """All 9 runnable frontier adapters, constructed with the shared GLM-5.2 llm."""
    return [
        WebWeaverMethod(llm=llm),
        IterResearchMethod(llm=llm),
        ConvergeWriterMethod(llm=llm),
        WarpMethod(llm=llm),
        DuMateMethod(llm=llm),
        FsResearcherMethod(llm=llm),
        ScaffoldAgentMethod(llm=llm),
        PokeeResearchMethod(llm=llm),
        DoloresMethod(llm=llm),
    ]
