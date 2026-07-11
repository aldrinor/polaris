"""S4 OUTLINE — two-level sub-theme FULL-PARTITION layer (build plan O1/O2/O3/O6).

The section spine (which top-level sections, in order) is produced by ``_call_outline`` and is left
UNTOUCHED here — required sections stay pinned in order, facet sections stay evidence-emergent. This
module adds the SECOND level: it groups EVERY digest basket line-id (``Bxx`` corroboration baskets +
``ev_xxx`` singletons) into a NAMED sub-theme under exactly ONE section, so the paragraphs land in a
real two-level topic tree (FS-Researcher ``index.md`` analog) instead of a flat keep-all residual dump.

ARCHITECTURE DNA (operator-locked): WEIGHT-AND-CONSOLIDATE, not FILTER-AND-CAP. The full-partition is
CONSOLIDATE — a pure GROUPING with ZERO drops and ZERO caps. Every line-id gets a home; nothing is
deleted, thinned, or capped to hit a number. The sub-theme COUNT per section EMERGES from the evidence
(the 2-6 guidance is a soft compute-safety band, never a forced target). The faithfulness engine
(strict_verify / NLI / provenance) is UNTOUCHED — a sub-theme is a container for composition, not a
verdict; every sentence still re-passes strict_verify downstream.

WHY DECOMPOSED (not one giant call): GLM-5.2 is reasoning-first. Asking ONE call to both invent
sub-theme names AND route 300+ line-ids induces a massive reasoning trace that consumes the whole
completion budget before any JSON is emitted (finish_reason=length, empty content). So the partition
is split into small, bounded, LOW-reasoning steps that each finish cleanly:

O1  two-level schema — {title, focus, subthemes:[{name, focus, basket_ids, ev_ids}]}.
O1a NAMING call      — ONE call names 2-6 sub-themes per section from the evidence menu (small output).
O2  full-partition   — CHUNKED ROUTING calls file each line-id into one (section, sub-theme). Output
                       per call is bounded to a chunk, so routing is mechanical and never truncates.
                       Every line-id lands in exactly ONE sub-theme (primary home). A no-fit id falls
                       to an explicit "Cross-Cutting Evidence" sub-theme in the nearest section
                       (deterministic backstop) so the partition is TOTAL — zero drops.
O3  gap-completion   — code computes ``unassigned = domain − routed``; if non-empty, ONE follow-up
                       routing call over ONLY the unassigned ids merges them in; anything the live
                       rounds still miss goes to the deterministic backstop, DISCLOSED as ``residual``
                       with a count + fraction (fail-loud, never silent).
O6  self-review      — one bounded round (``PG_OUTLINE_REVISE_ROUNDS``, default 1) asking whether any
                       required aspect is unanswerable from its assigned baskets and whether any
                       one-basket sub-theme belongs elsewhere; it may MERGE a thin sub-theme into a
                       sibling in the SAME section (never crosses the pinned spine, never drops an id).

The module makes REAL GLM calls (LAW II — no synthetic partition). It is NOT a faithfulness gate, so a
model/transport failure DEGRADES to the deterministic backstop with a LOUD disclosure (residual rises)
rather than crashing a paid run — the high residual_fraction then tells the honest truth.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

# ── env knobs (LAW VI: all tunable, default-safe/generous; read at call time so they are
# unit-testable via monkeypatch and per-run overridable) ──────────────────────────────────────────
PG_OUTLINE_SUBTHEME_PARTITION_DEFAULT = "1"   # ON by default (a winner left default-OFF is the loop root)
PG_OUTLINE_MAX_TOKENS_DEFAULT = "32768"       # un-starved content ceiling (O4); a CAP not a target
PG_OUTLINE_MIN_MAX_TOKENS_DEFAULT = "16384"   # content floor (mirrors _call_outline)
PG_OUTLINE_REASONING_MAX_TOKENS_DEFAULT = "6144"        # naming call reasoning cap
PG_OUTLINE_PARTITION_ROUTE_REASONING_DEFAULT = "4096"   # routing is mechanical -> low reasoning
PG_OUTLINE_PARTITION_CHUNK_DEFAULT = "50"     # line-ids routed per call (bounds each output)
PG_OUTLINE_SUBTHEME_MIN_DEFAULT = "2"         # soft band; the real count EMERGES from evidence
PG_OUTLINE_SUBTHEME_MAX_DEFAULT = "6"
PG_OUTLINE_REVISE_ROUNDS_DEFAULT = 1          # O6 self-review bound (hard-clamped 0..2)

_CROSS_CUTTING_NAME = "Cross-Cutting Evidence"

# minimal English stop-set for the deterministic nearest-section overlap (backstop only; never a gate)
_STOPWORDS = frozenset(
    "the a an and or of to in on for with from by at as is are was were be been being this that these "
    "those it its their his her our your they we you i he she them us into over under about after before "
    "between within without during through against among per via than then so such not no nor but if "
    "while which who whom whose what when where why how all any each more most other some only own same "
    "can will just should now also may might must due can't cannot has have had do does did".split()
)


def _partition_enabled() -> bool:
    return os.getenv(
        "PG_OUTLINE_SUBTHEME_PARTITION", PG_OUTLINE_SUBTHEME_PARTITION_DEFAULT
    ).strip().lower() in ("1", "true", "yes", "on")


def _content_max_tokens() -> int:
    """Effective content ceiling = max(PG_OUTLINE_MAX_TOKENS, PG_OUTLINE_MIN_MAX_TOKENS) — un-starved
    so a routing chunk's JSON always fits (the 2500-token starve could not; 32768 can)."""
    def _read(name: str, dflt: str) -> int:
        try:
            return int(os.getenv(name, dflt))
        except (TypeError, ValueError):
            return int(dflt)
    return max(_read("PG_OUTLINE_MAX_TOKENS", PG_OUTLINE_MAX_TOKENS_DEFAULT),
               _read("PG_OUTLINE_MIN_MAX_TOKENS", PG_OUTLINE_MIN_MAX_TOKENS_DEFAULT))


def _naming_reasoning_max_tokens() -> int:
    try:
        return int(os.getenv("PG_OUTLINE_REASONING_MAX_TOKENS", PG_OUTLINE_REASONING_MAX_TOKENS_DEFAULT))
    except (TypeError, ValueError):
        return int(PG_OUTLINE_REASONING_MAX_TOKENS_DEFAULT)


def _route_reasoning_max_tokens() -> int:
    try:
        return int(os.getenv("PG_OUTLINE_PARTITION_ROUTE_REASONING",
                             PG_OUTLINE_PARTITION_ROUTE_REASONING_DEFAULT))
    except (TypeError, ValueError):
        return int(PG_OUTLINE_PARTITION_ROUTE_REASONING_DEFAULT)


def _chunk_size() -> int:
    try:
        v = int(os.getenv("PG_OUTLINE_PARTITION_CHUNK", PG_OUTLINE_PARTITION_CHUNK_DEFAULT))
    except (TypeError, ValueError):
        v = int(PG_OUTLINE_PARTITION_CHUNK_DEFAULT)
    return max(10, v)


def _subtheme_band() -> tuple[int, int]:
    def _read(name: str, dflt: str) -> int:
        try:
            return int(os.getenv(name, dflt))
        except (TypeError, ValueError):
            return int(dflt)
    lo = max(1, _read("PG_OUTLINE_SUBTHEME_MIN", PG_OUTLINE_SUBTHEME_MIN_DEFAULT))
    hi = max(lo, _read("PG_OUTLINE_SUBTHEME_MAX", PG_OUTLINE_SUBTHEME_MAX_DEFAULT))
    return lo, hi


def _revise_rounds() -> int:
    try:
        v = int(os.getenv("PG_OUTLINE_REVISE_ROUNDS", str(PG_OUTLINE_REVISE_ROUNDS_DEFAULT)))
    except (TypeError, ValueError):
        v = PG_OUTLINE_REVISE_ROUNDS_DEFAULT
    return max(0, min(v, 2))


def _tokenize(text: str) -> set[str]:
    toks = re.split(r"[^a-z0-9]+", (text or "").lower())
    return {t for t in toks if len(t) >= 3 and t not in _STOPWORDS}


def _extract_json(raw: str) -> dict | None:
    """Fence-strip + first ``{`` .. last ``}`` + lenient trailing-comma recovery (same shape as
    ``_parse_outline``). Returns None on unrecoverable output (caller degrades gracefully)."""
    if not raw:
        return None
    stripped = raw.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```\s*$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        return None
    payload = stripped[start:end + 1]
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        try:
            obj = json.loads(re.sub(r",(\s*[}\]])", r"\1", payload))
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


# ── partition domain (the line-ids the model must fully partition) ─────────────────────────────────

def build_partition_domain(menu: Any) -> tuple[list[str], dict[str, str], dict[str, list[str]]]:
    """Return (domain_ids, id_to_text, id_to_ev_ids).

    domain_ids  — every digest line-id: the ``Bxx`` baskets + the ``ev_xxx`` singletons, in menu order
                  (baskets first, then singletons — the exact order the planner reads).
    id_to_text  — line-id -> the human text of that menu line (claim / title), fed to the router so it
                  can place the line, and used by the deterministic nearest-section backstop.
    id_to_ev_ids— line-id -> the underlying evidence rows it carries (basket members, or the singleton
                  itself plus its folded same-work aliases). Lets a sub-theme expand to real ev_ids for
                  the compose stage while the partition key stays the digest line-id.
    """
    id_to_text: dict[str, str] = {}
    id_to_ev_ids: dict[str, list[str]] = {}
    basket_ids: list[str] = []
    singleton_ids: list[str] = []

    for line in getattr(menu, "basket_lines", []) or []:
        parts = str(line).split(None, 1)
        if not parts:
            continue
        bid = parts[0]
        basket_ids.append(bid)
        id_to_text[bid] = parts[1] if len(parts) > 1 else ""
        id_to_ev_ids[bid] = list(getattr(menu, "basket_member_ev_ids", {}).get(bid, []) or [])

    alias_map = getattr(menu, "singleton_alias_ev_ids", {}) or {}
    for line in getattr(menu, "singleton_lines", []) or []:
        parts = str(line).split(None, 1)
        if not parts:
            continue
        sid = parts[0]
        singleton_ids.append(sid)
        id_to_text[sid] = parts[1] if len(parts) > 1 else ""
        id_to_ev_ids[sid] = [sid] + list(alias_map.get(sid, []) or [])

    domain_ids = basket_ids + singleton_ids   # baskets first, then singletons (menu.render() order)
    return domain_ids, id_to_text, id_to_ev_ids


# ── the three live prompts ─────────────────────────────────────────────────────────────────────────

_NAMING_SYSTEM = """You are a research-report structure planner. The top-level SECTIONS are ALREADY FIXED and given to you in order — do NOT add, drop, rename, or reorder them. Your ONLY job is to name each section's sub-themes.

You are shown a MENU of the evidence available (each line begins with an ID: "B.." = a corroboration basket of several sources on one claim; "ev_.." = a single source).

For EACH fixed section, propose the sub-themes that its evidence naturally splits into. Output JSON:
{"sections":[{"title":"<exact section title>","subthemes":[{"name":"<sub-theme name>","focus":"<one sentence>"}]}]}

RULES:
- Use the section titles VERBATIM, in the given order; emit all of them and only them.
- Give each section 2 to 6 sub-themes — as MANY as the evidence genuinely supports, as FEW as it supports. The number EMERGES from the evidence; never pad to a count, never invent a sub-theme with no evidence.
- Sub-theme names: Title Case, at most 8 words, SPECIFIC (e.g. "Wage Inequality Estimates", not "Other" or "Miscellaneous").
- Do NOT assign evidence IDs here — names and one-sentence focus only. Keep it brief; do not deliberate at length.

Return ONLY the JSON object. No preamble, no markdown fence, no commentary."""

_ROUTE_SYSTEM = """You are filing evidence lines into an EXISTING report structure. The sections and their sub-themes are FIXED and listed below — do NOT rename, add, or drop any of them.

For EACH evidence line I give you, output the ONE (section, sub-theme) it best belongs to. Output JSON:
{"assignments":[{"id":"B07","section":"<exact section title>","subtheme":"<exact existing sub-theme name>"}, ...]}

RULES:
- Assign EVERY line I give you, using the section titles and sub-theme names verbatim from the list below.
- Pick the single best-fitting sub-theme. If a line fits no specific sub-theme, assign it to the "Cross-Cutting Evidence" sub-theme of the most-related section.
- This is mechanical filing — do NOT deliberate at length. Return ONLY the JSON object, no commentary."""

_SELF_REVIEW_SYSTEM = """You are reviewing a research-report structure for two problems ONLY:
1. Is any required section left unanswerable — i.e. does a section have essentially no evidence filed under it?
2. Does any sub-theme hold only ONE basket/source that clearly belongs inside a sibling sub-theme of the SAME section?

You may ONLY merge a thin sub-theme into a sibling sub-theme in the SAME section. You may NOT move evidence across sections, rename sections, add/drop sections, or drop any evidence.

OUTPUT a JSON object: {"gaps":["<section title with too little evidence>", ...],"merges":[{"section":"<exact section title>","from_subtheme":"<thin sub-theme name>","into_subtheme":"<sibling sub-theme name>"}]}

Return ONLY the JSON object (empty "gaps"/"merges" arrays if nothing to change). No commentary."""


async def _one_call(*, model: str, system: str, prompt: str, temperature: float,
                    reasoning_max_tokens: int, attempt_tag: str) -> tuple[str, int, int]:
    """One GLM call. Returns (content, in_tok, out_tok). Never raises to the caller on a transport
    error — returns ("", 0, 0) so the orchestrator can degrade to the deterministic backstop with a
    LOUD disclosure (the partition is not a faithfulness gate)."""
    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
        OpenRouterClient,
        set_reasoning_call_context,
    )
    client = OpenRouterClient(model=model)
    try:
        set_reasoning_call_context(section="_outline_partition", call_type="outline", attempt_n=1)
        resp = await client.generate(
            prompt=prompt,
            system=system,
            max_tokens=_content_max_tokens(),
            temperature=temperature,
            reasoning_max_tokens=reasoning_max_tokens,
        )
        return (resp.content or "").strip(), int(resp.input_tokens), int(resp.output_tokens)
    except Exception as exc:  # noqa: BLE001 — degrade to backstop, never crash a paid run
        print(f"[outline_partition] WARNING: {attempt_tag} GLM call failed ({str(exc)[:200]}) — "
              "degrading (residual disclosed; deterministic backstop covers the miss).",
              file=sys.stderr)
        return "", 0, 0
    finally:
        if hasattr(client, "close"):
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass


# ── result container ────────────────────────────────────────────────────────────────────────────

@dataclass
class PartitionResult:
    section_subthemes: dict[str, list[dict[str, Any]]]   # title -> [{name, focus, basket_ids, ev_ids}]
    assignment: dict[str, dict[str, str]]                # line-id -> {"section","subtheme"} (full)
    domain_ids: list[str]
    assigned_by_model_ids: list[str]     # placed by the LIVE routing + gap rounds
    residual_ids: list[str]              # fell to the deterministic Cross-Cutting backstop
    duplicate_id_count: int              # ids the router listed twice (first placement won)
    unknown_id_count: int                # ids the router invented that are not in the domain
    naming_ok: bool                      # the NAMING call produced usable sub-themes
    route_call_count: int
    gap_round_fired: bool
    self_review_fired: bool
    self_review_merges: list[dict[str, str]]
    self_review_gaps: list[str]
    content_max_tokens: int
    total_in_tokens: int
    total_out_tokens: int

    @property
    def residual_fraction(self) -> float:
        n = len(self.domain_ids)
        return round(len(self.residual_ids) / n, 4) if n else 0.0

    @property
    def assigned_count(self) -> int:
        return len(self.assignment)


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────

def _norm_title_key(s: str) -> str:
    """Normalization key for a robust section-title match: fold the unicode punctuation a reasoning
    model routinely substitutes (curly apostrophes/quotes, en/em dashes) to ASCII, strip a leading
    list enumerator, collapse whitespace, lowercase. Without this, an echoed "AI’s" (curly) never
    matches the pinned "AI's" (straight) and the WHOLE section's sub-themes are silently discarded —
    the exact failure that degraded a good partition to a flat Cross-Cutting dump."""
    s = str(s or "")
    for a, b in (("’", "'"), ("‘", "'"), ("ʼ", "'"), ("`", "'"),
                 ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-")):
        s = s.replace(a, b)
    s = re.sub(r"^\s*\d+[.)]\s*", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _title_alnum_key(s: str) -> str:
    """Punctuation-blind key: only [a-z0-9]. A last-resort exact key when even quote-folding differs."""
    return re.sub(r"[^a-z0-9]+", "", _norm_title_key(s))


def _match_section_title(raw: str, section_titles: list[str]) -> str | None:
    """Map a model-emitted section title to the exact pinned title. Three tiers, most-strict first:
    (1) unicode/enum/whitespace-normalized exact; (2) punctuation-blind alnum-exact; (3) content-word
    token-overlap, accepted ONLY when the best required title is unambiguous (strictly beats the
    runner-up). Never guesses on a tie -> returns None so the id falls to the gap round / backstop."""
    key = _norm_title_key(raw)
    if not key:
        return None
    for t in section_titles:
        if _norm_title_key(t) == key:
            return t
    akey = _title_alnum_key(raw)
    if akey:
        for t in section_titles:
            if _title_alnum_key(t) == akey:
                return t
    # tier 3: token-overlap, unambiguous-only
    rtoks = _tokenize(key)
    if not rtoks:
        return None
    scored = sorted(
        ((len(rtoks & _tokenize(_norm_title_key(t))), t) for t in section_titles),
        key=lambda x: x[0], reverse=True,
    )
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


def _norm_subtheme_name(name: str) -> str:
    """Collapse whitespace + cap at 8 words (Title Case is the model's job, not forced here)."""
    words = str(name or "").strip().split()
    return " ".join(words[:8]) if words else ""


def _match_subtheme(name: str, section_map: dict[str, dict]) -> str:
    """Resolve a router-emitted sub-theme name to an EXISTING sub-theme of the section (exact, then
    case-insensitive). No match -> the section's Cross-Cutting sub-theme (created on demand)."""
    n = _norm_subtheme_name(name)
    if n in section_map:
        return n
    low = {k.lower(): k for k in section_map}
    if n.lower() in low:
        return low[n.lower()]
    return _CROSS_CUTTING_NAME


def _nearest_section(text: str, section_tokens: dict[str, set[str]],
                     section_load: dict[str, int], section_titles: list[str]) -> str:
    """Deterministic backstop: the section whose (title+focus) tokens overlap the id's text most;
    ties / zero-overlap -> the section carrying the FEWEST ids so far (load-balanced), first on tie."""
    toks = _tokenize(text)
    best_title = section_titles[0] if section_titles else ""
    best_score = -1
    for t in section_titles:
        score = len(toks & section_tokens.get(t, set()))
        if score > best_score:
            best_score = score
            best_title = t
    if best_score <= 0:
        return min(section_titles, key=lambda t: (section_load.get(t, 0), section_titles.index(t)))
    return best_title


def _apply_route_assignments(
    assignments: list, *, section_titles: list[str], domain_set: set[str],
    assignment: dict[str, dict[str, str]], per_section: dict[str, dict],
) -> tuple[int, int]:
    """Apply a router call's ``assignments`` (first placement wins). Returns (dup, unknown) deltas."""
    dup = 0
    unknown = 0
    for a in (assignments or []):
        if not isinstance(a, dict):
            continue
        sid = str(a.get("id", ""))
        if sid not in domain_set:
            if sid:
                unknown += 1
            continue
        if sid in assignment:
            dup += 1
            continue
        title = _match_section_title(a.get("section", ""), section_titles)
        if title is None:
            continue
        name = _match_subtheme(a.get("subtheme", ""), per_section[title])
        bucket = per_section[title].setdefault(name, {"focus": "", "ids": []})
        assignment[sid] = {"section": title, "subtheme": name}
        bucket["ids"].append(sid)
    return dup, unknown


# ── the orchestrator ──────────────────────────────────────────────────────────────────────────────

async def partition_outline_subthemes(
    *,
    sections: list[dict[str, str]],   # [{"title","focus"}] — the PINNED spine, in order
    menu: Any,                        # OutlineDigestMenu the planner read
    model: str,
    question: str = "",
    temperature: float = 0.2,
) -> PartitionResult:
    """Run the O1/O2/O3/O6 two-level full-partition over the section spine. LIVE + deterministic."""
    section_titles = [str(s.get("title", "")).strip() for s in sections if str(s.get("title", "")).strip()]
    domain_ids, id_to_text, id_to_ev_ids = build_partition_domain(menu)
    domain_set = set(domain_ids)
    lo, hi = _subtheme_band()
    total_in = 0
    total_out = 0

    # per_section: title -> ordered {subtheme_name -> {"focus":..., "ids":[...]}}
    per_section: dict[str, dict] = {t: {} for t in section_titles}
    assignment: dict[str, dict[str, str]] = {}
    dup = 0
    unknown = 0

    sec_block = "\n".join(
        f"- {s['title']}: {str(s.get('focus','') or '').strip() or '(no focus given)'}"
        for s in sections
    )
    menu_text = menu.render()

    # ---- O1a NAMING call (small output; names + focus per section, no ids) ------------------------
    naming_prompt = (
        f"Research question: {question}\n\n"
        f"FIXED SECTIONS (in order):\n{sec_block}\n\n"
        f"Propose {lo}-{hi} sub-themes per section from the evidence below.\n\n"
        f"EVIDENCE MENU ({len(domain_ids)} lines):\n{menu_text}\n\n"
        f"Return the JSON sub-theme structure."
    )
    def _ingest_naming(naming_obj: dict) -> None:
        for sec in (naming_obj.get("sections") or []):
            if not isinstance(sec, dict):
                continue
            title = _match_section_title(sec.get("title", ""), section_titles)
            if title is None:
                continue
            for st in (sec.get("subthemes") or []):
                if not isinstance(st, dict):
                    continue
                name = _norm_subtheme_name(st.get("name", ""))
                if not name:
                    continue
                per_section[title].setdefault(name, {"focus": str(st.get("focus", "") or ""), "ids": []})

    # first naming attempt; ONE retry if it produced nothing usable (a total-degrade guard — losing the
    # naming call drops the whole section tree to a flat Cross-Cutting dump, so it is worth one retry).
    for _attempt in range(2):
        n_content, ni, no = await _one_call(
            model=model, system=_NAMING_SYSTEM, prompt=naming_prompt, temperature=temperature,
            reasoning_max_tokens=_naming_reasoning_max_tokens(),
            attempt_tag="naming" if _attempt == 0 else "naming_retry",
        )
        total_in += ni
        total_out += no
        _ingest_naming(_extract_json(n_content) or {})
        if any(per_section[t] for t in section_titles):
            break
    naming_ok = any(per_section[t] for t in section_titles)

    # ---- O2 CHUNKED ROUTING calls (bounded output -> mechanical, never truncates) -----------------
    route_calls = 0
    if naming_ok:
        subtheme_menu = "\n".join(
            f"Section {t!r}:\n" + "\n".join(f"    - {n}" for n in per_section[t].keys())
            for t in section_titles
        )
        chunk = _chunk_size()
        for start in range(0, len(domain_ids), chunk):
            block_ids = domain_ids[start:start + chunk]
            lines = "\n".join(f"{i} | {id_to_text.get(i, '')[:200]}" for i in block_ids)
            route_prompt = (
                f"FIXED SECTIONS AND SUB-THEMES (file into these verbatim):\n{subtheme_menu}\n\n"
                f"EVIDENCE LINES TO FILE ({len(block_ids)} — assign every one):\n{lines}\n\n"
                f"Return the JSON assignments."
            )
            r_content, ri, ro = await _one_call(
                model=model, system=_ROUTE_SYSTEM, prompt=route_prompt, temperature=temperature,
                reasoning_max_tokens=_route_reasoning_max_tokens(), attempt_tag=f"route[{start}]",
            )
            total_in += ri
            total_out += ro
            route_calls += 1
            r_obj = _extract_json(r_content) or {}
            d, u = _apply_route_assignments(
                r_obj.get("assignments"), section_titles=section_titles, domain_set=domain_set,
                assignment=assignment, per_section=per_section,
            )
            dup += d
            unknown += u

    # ---- O3 gap-completion round (over ONLY what the routing missed) ------------------------------
    unassigned = [i for i in domain_ids if i not in assignment]
    gap_fired = False
    if naming_ok and unassigned:
        gap_fired = True
        subtheme_menu = "\n".join(
            f"Section {t!r}:\n" + "\n".join(f"    - {n}" for n in per_section[t].keys())
            for t in section_titles
        )
        lines = "\n".join(f"{i} | {id_to_text.get(i, '')[:200]}" for i in unassigned)
        gap_prompt = (
            f"FIXED SECTIONS AND SUB-THEMES (file into these verbatim):\n{subtheme_menu}\n\n"
            f"REMAINING UNFILED LINES ({len(unassigned)} — assign every one):\n{lines}\n\n"
            f"Return the JSON assignments."
        )
        g_content, gi, go = await _one_call(
            model=model, system=_ROUTE_SYSTEM, prompt=gap_prompt, temperature=temperature,
            reasoning_max_tokens=_route_reasoning_max_tokens(), attempt_tag="gap",
        )
        total_in += gi
        total_out += go
        g_obj = _extract_json(g_content) or {}
        d, u = _apply_route_assignments(
            g_obj.get("assignments"), section_titles=section_titles, domain_set=domain_set,
            assignment=assignment, per_section=per_section,
        )
        dup += d
        unknown += u

    assigned_by_model = list(assignment.keys())

    # ---- deterministic Cross-Cutting backstop (O2 no-fit / degrade -> nearest section) ------------
    residual = [i for i in domain_ids if i not in assignment]
    if residual:
        section_tokens = {
            s["title"].strip(): _tokenize(f"{s.get('title','')} {s.get('focus','')}")
            for s in sections if str(s.get("title", "")).strip()
        }
        section_load = {t: sum(len(v["ids"]) for v in per_section[t].values()) for t in section_titles}
        for i in residual:
            title = _nearest_section(id_to_text.get(i, ""), section_tokens, section_load, section_titles)
            bucket = per_section[title].setdefault(_CROSS_CUTTING_NAME, {"focus": "", "ids": []})
            bucket["ids"].append(i)
            assignment[i] = {"section": title, "subtheme": _CROSS_CUTTING_NAME}
            section_load[title] = section_load.get(title, 0) + 1

    # ---- O6 self-review (bounded; merge a thin sub-theme into a sibling in the SAME section) -------
    self_review_fired = False
    self_merges: list[dict[str, str]] = []
    self_gaps: list[str] = []
    if naming_ok and _revise_rounds() >= 1:
        self_review_fired = True
        struct_block = "\n".join(
            f"- {t!r}:\n"
            + "\n".join(f"    * {n!r}: {len(v['ids'])} baskets/sources"
                        for n, v in per_section[t].items())
            for t in section_titles
        )
        sr_content, si, so = await _one_call(
            model=model, system=_SELF_REVIEW_SYSTEM,
            prompt=f"CURRENT STRUCTURE:\n{struct_block}\n\nReturn the JSON review.",
            temperature=temperature, reasoning_max_tokens=_naming_reasoning_max_tokens(),
            attempt_tag="self_review",
        )
        total_in += si
        total_out += so
        sr = _extract_json(sr_content) or {}
        self_gaps = [str(g) for g in (sr.get("gaps") or []) if str(g).strip()]
        for m in (sr.get("merges") or []):
            if not isinstance(m, dict):
                continue
            title = _match_section_title(m.get("section", ""), section_titles)
            if title is None:
                continue
            frm = _norm_subtheme_name(m.get("from_subtheme", ""))
            into = _norm_subtheme_name(m.get("into_subtheme", ""))
            secmap = per_section[title]
            if not frm or not into or frm == into or frm not in secmap or into not in secmap:
                continue
            moved = secmap[frm]["ids"]
            secmap[into]["ids"].extend(moved)
            for sid in moved:
                assignment[sid] = {"section": title, "subtheme": into}
            del secmap[frm]
            self_merges.append({"section": title, "from": frm, "into": into})

    # ---- materialize the ordered sub-theme lists (O1 schema) --------------------------------------
    section_subthemes: dict[str, list[dict[str, Any]]] = {}
    for t in section_titles:
        out_list: list[dict[str, Any]] = []
        for name, v in per_section[t].items():
            b_ids = list(v["ids"])
            if not b_ids:
                continue  # never emit an empty sub-theme
            ev_ids: list[str] = []
            seen: set[str] = set()
            for bid in b_ids:
                for e in id_to_ev_ids.get(bid, []):
                    if e and e not in seen:
                        seen.add(e)
                        ev_ids.append(e)
            out_list.append({
                "name": name,
                "focus": v.get("focus", ""),
                "basket_ids": b_ids,     # digest line-ids (Bxx + ev_xxx) — the partition key
                "ev_ids": ev_ids,        # expanded evidence rows for the compose stage
            })
        section_subthemes[t] = out_list

    return PartitionResult(
        section_subthemes=section_subthemes,
        assignment=assignment,
        domain_ids=domain_ids,
        assigned_by_model_ids=assigned_by_model,
        residual_ids=residual,
        duplicate_id_count=dup,
        unknown_id_count=unknown,
        naming_ok=naming_ok,
        route_call_count=route_calls,
        gap_round_fired=gap_fired,
        self_review_fired=self_review_fired,
        self_review_merges=self_merges,
        self_review_gaps=self_gaps,
        content_max_tokens=_content_max_tokens(),
        total_in_tokens=total_in,
        total_out_tokens=total_out,
    )
