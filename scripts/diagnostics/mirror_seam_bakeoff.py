"""Faithful whole-system bakeoff of Mirror VOTER candidates through the REAL 2-pass seam.

WHY (operator, 2026-06-04): earlier simple proxies MISLED us — they read the wrong
result object fields (`.answer_text`, which does not exist; the verdict is `.classification`)
and used tiny payloads that did not reproduce the production blank. This harness drives EACH
candidate through the EXACT production seam:

    run_mirror(transport, claim, [EvidenceDocument(...)], model_slug=slug)

i.e. the real OpenRouter `OpenRouterRoleTransport` (pass-1 RAG-with-`<co>`-citations +
citation-binding guard, pass-2 JSON classification bound by content_hash). No proxy. No mock.

SEAM FACTS verified by reading the source (do NOT "clean up"):
  - The transport resolves the Mirror model from the env `PG_MIRROR_MODEL` (read lazily per
    call by `benchmark_verifier_slug`), NOT from `request.model_slug`. So switching candidate =
    set `os.environ['PG_MIRROR_MODEL']=slug`. The `model_slug=slug` arg to run_mirror only lands
    in the RoleCallRecord (passed anyway for honest records).
  - With PG_MIRROR_REASONING=false, `role_reasoning_enabled("mirror")` is False, so
    `_build_openrouter_body` takes the ELSE branch where the Mirror's OUTPUT budget is
    `PG_SENTINEL_MAX_TOKENS` (default 256). We set it to 4000 so pass-2 JSON does not truncate
    into a FAKE blank. This is intentional env coupling — keep both verbatim.
  - `benchmark_verifier_family` (the z-ai lane guard) is NOT called on the run_mirror path; only
    Gate-B preflight calls it. So an arbitrary open-weight candidate slug is accepted by the
    transport here — no lane patch needed.

LABELED SET (from outputs/audits/I-run11-004/m25_bakeoff/evidence_pool.json, 27 items):
  - 4 GROUNDED pairs: a declarative statement as the CLAIM + its OWN direct_quote as the SOLE
    EvidenceDocument. expected_grounded=True. A faithful Mirror should BIND (emit a grounded
    `<co>` citation -> a non-empty `.classification`).
  - 3 UNGROUNDED pairs: an AI-labor CLAIM + a TOPICALLY-DISTANT publication-bias span (systematic
    reviews / English-citation / journal-publishing items) as the SOLE doc. expected_grounded=
    False. A faithful Mirror should REFUSE via MirrorCitationError (no span binds).

A good Mirror: blank_count=0, grounded_bind_rate>=0.75, false_bind_rate<=0.34.

Secrets: OPENROUTER_API_KEY is loaded from .env if absent from env; NEVER printed/committed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# --- repo root on sys.path (run from C:\POLARIS) ----------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_openrouter_key_from_dotenv() -> None:
    """Load OPENROUTER_API_KEY from .env if not already in the environment. Never prints it."""
    if os.getenv("OPENROUTER_API_KEY"):
        return
    dotenv_path = _REPO_ROOT / ".env"
    if not dotenv_path.exists():
        return
    for line in dotenv_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == "OPENROUTER_API_KEY":
            value = value.strip().strip('"').strip("'")
            if value:
                os.environ["OPENROUTER_API_KEY"] = value
            return


# --- env coupling MUST be set BEFORE importing the transport ---------------------------------
_load_openrouter_key_from_dotenv()
os.environ["PG_MIRROR_REASONING"] = "false"
# In the reasoning-OFF branch this IS the Mirror's output budget (see module docstring). 4000 so
# pass-2 JSON does not truncate into a fake blank.
os.environ["PG_SENTINEL_MAX_TOKENS"] = "4000"
os.environ["PG_FOUR_ROLE_TRANSPORT"] = "openrouter"
# Budget safety: a blanking model still hits check_run_budget inside complete(); keep the cap high
# so all candidates finish (LAW VI: env-gated, not hard-coded into logic).
os.environ.setdefault("PG_MAX_COST_PER_RUN", "1000")

import json  # noqa: E402

import httpx  # noqa: E402

from src.polaris_graph.llm.openrouter_client import BudgetExceededError  # noqa: E402
from src.polaris_graph.roles.mirror_adapter import (  # noqa: E402
    MirrorBindingError,
    MirrorCitationError,
    MirrorParseError,
    run_mirror,
)
from src.polaris_graph.roles.openai_compatible_transport import (  # noqa: E402
    BlankVerdictError,
    RoleTransportError,
)
from src.polaris_graph.roles.openrouter_role_transport import (  # noqa: E402
    OpenRouterRoleTransport,
)
from src.polaris_graph.roles.role_transport import EvidenceDocument  # noqa: E402

# Candidate Mirror slugs (open-weight only; families moonshotai/mistralai/nvidia/meta-llama/z-ai
# are all DISTINCT from generator deepseek, sentinel minimax, judge qwen — family-legal).
CANDIDATES = [
    "moonshotai/kimi-k2.6",
    "mistralai/mistral-large-2512",
    "nvidia/nemotron-3-super-120b-a12b",
    "meta-llama/llama-4-maverick",
    "z-ai/glm-5.1",  # the incumbent benchmark default
]

INCUMBENT = "z-ai/glm-5.1"

EVIDENCE_POOL_PATH = (
    _REPO_ROOT / "outputs" / "audits" / "I-run11-004" / "m25_bakeoff" / "evidence_pool.json"
)

# Indices into the 27-item pool (verified by reading the file):
#   GROUNDED claims: declarative statements with substantive abstracts.
_GROUNDED_IDX = [0, 3, 5, 8]
#   UNRELATED spans for the ungrounded negatives: publication-bias / journal items, topically
#   DISTANT from any AI-labor claim (so a legitimate bind cannot happen -> a faithful Mirror
#   refuses). 9=systematic reviews exclude non-English, 24=English articles attract citations,
#   10=guide to publishing in reputable journals.
_UNGROUNDED_CLAIM_IDX = [0, 3, 5]
_UNGROUNDED_SPAN_IDX = [9, 24, 10]

_MAX_DOC_CHARS = 2000


def _load_pool() -> list[dict]:
    return json.loads(EVIDENCE_POOL_PATH.read_text(encoding="utf-8"))


def _build_labeled_set(pool: list[dict]) -> list[dict]:
    """Construct the 4 grounded + 3 ungrounded labeled pairs."""
    pairs: list[dict] = []
    # 4 GROUNDED: claim = item.statement, sole doc = item's OWN direct_quote.
    for i in _GROUNDED_IDX:
        item = pool[i]
        pairs.append(
            {
                "label": "grounded",
                "expected_grounded": True,
                "claim": item["statement"],
                "doc": EvidenceDocument(
                    doc_id=item["evidence_id"],
                    text=item["direct_quote"][:_MAX_DOC_CHARS],
                ),
                "claim_id": item["evidence_id"],
                "span_id": item["evidence_id"],
            }
        )
    # 3 UNGROUNDED: AI-labor claim + a topically-DISTANT publication-bias span.
    for claim_i, span_j in zip(_UNGROUNDED_CLAIM_IDX, _UNGROUNDED_SPAN_IDX):
        claim_item = pool[claim_i]
        span_item = pool[span_j]
        pairs.append(
            {
                "label": "ungrounded",
                "expected_grounded": False,
                "claim": claim_item["statement"],
                "doc": EvidenceDocument(
                    doc_id=span_item["evidence_id"],
                    text=span_item["direct_quote"][:_MAX_DOC_CHARS],
                ),
                "claim_id": claim_item["evidence_id"],
                "span_id": span_item["evidence_id"],
            }
        )
    return pairs


def _run_candidate(slug: str, pairs: list[dict]) -> dict:
    """Drive ONE candidate through the real seam for every labeled pair. Sequential."""
    # The ONLY thing that switches the served model (transport reads PG_MIRROR_MODEL lazily).
    os.environ["PG_MIRROR_MODEL"] = slug
    client = httpx.Client(timeout=180)
    transport = OpenRouterRoleTransport(client)

    blank_count = 0
    grounded_bound = 0
    grounded_total = 0
    false_bound = 0  # ungrounded pairs that WRONGLY returned a bound classification
    ungrounded_total = 0
    served_models: set[str] = set()
    notable: list[str] = []

    try:
        for pair in pairs:
            label = pair["label"]
            is_grounded = pair["expected_grounded"]
            if is_grounded:
                grounded_total += 1
            else:
                ungrounded_total += 1

            tag = f"[{slug}][{label}] claim={pair['claim_id']} span={pair['span_id']}"
            try:
                pass2, records = run_mirror(
                    transport, pair["claim"], [pair["doc"]], model_slug=slug
                )
                classification = pass2.classification
                bound = isinstance(classification, str) and bool(classification.strip())
                served = records[0].served_model if records else None
                if served:
                    served_models.add(str(served))
                if bound:
                    if is_grounded:
                        grounded_bound += 1
                    else:
                        false_bound += 1
                    print(
                        f"{tag} -> BOUND classification={classification!r:.80} "
                        f"served={served!r}"
                    )
                else:
                    print(f"{tag} -> EMPTY classification (not bound) served={served!r}")
            except BlankVerdictError as exc:
                blank_count += 1
                print(f"{tag} -> BLANK (BlankVerdictError): {exc}")
            except MirrorCitationError as exc:
                # No grounded citation = a REFUSAL. CORRECT for ungrounded; a miss for grounded.
                kind = "refusal(correct)" if not is_grounded else "refusal(miss-on-grounded)"
                print(f"{tag} -> {kind} (MirrorCitationError): {str(exc)[:140]}")
            except MirrorBindingError as exc:
                msg = f"{tag} -> UNBOUND (MirrorBindingError): {str(exc)[:140]}"
                notable.append(msg)
                print(msg)
            except MirrorParseError as exc:
                msg = f"{tag} -> PARSE-FAIL (MirrorParseError): {str(exc)[:140]}"
                notable.append(msg)
                print(msg)
            except BudgetExceededError as exc:
                msg = f"{tag} -> BUDGET (BudgetExceededError): {str(exc)[:140]}"
                notable.append(msg)
                print(msg)
                raise  # the run budget is shared/global; stop this candidate.
            except RoleTransportError as exc:
                # Non-200 / non-JSON / unresolving slug (e.g. a 404 on a forward-dated slug).
                msg = f"{tag} -> TRANSPORT-ERR (RoleTransportError): {str(exc)[:140]}"
                notable.append(msg)
                print(msg)
            except Exception as exc:  # noqa: BLE001 — record-and-continue, never abort the harness.
                msg = f"{tag} -> OTHER ({type(exc).__name__}): {str(exc)[:140]}"
                notable.append(msg)
                print(msg)
    except BudgetExceededError:
        notable.append("candidate aborted: shared run budget exceeded")
    finally:
        client.close()

    grounded_bind_rate = (grounded_bound / grounded_total) if grounded_total else 0.0
    false_bind_rate = (false_bound / ungrounded_total) if ungrounded_total else 0.0
    return {
        "slug": slug,
        "blank_count": blank_count,
        "grounded_bound": grounded_bound,
        "grounded_total": grounded_total,
        "grounded_bind_rate": grounded_bind_rate,
        "false_bound": false_bound,
        "ungrounded_total": ungrounded_total,
        "false_bind_rate": false_bind_rate,
        "served_models": sorted(served_models),
        "notable": notable,
    }


def _verdict(metrics: dict) -> str:
    """Faithfulness-VOTER verdict (NOT a blank-first metadata sort).

    For a faithfulness voter the PRIMARY failure is binding an UNGROUNDED claim (fabricated
    grounding — the §-1.1-lethal failure). So `false_bind_rate` gates hardest:
      - PASS iff blank=0 AND grounded_bind_rate>=0.75 AND false_bind_rate<=0.34 (the task bar).
      - FAIL if it false-binds beyond the bar (rubber-stamps unsupported claims), OR never binds
        a grounded claim (refuses everything), OR blanks. A 100%-false-bind model is the WORST
        profile for a voter — it is FAIL, never "WEAK" above a single-blank faithful model.
      - WEAK is reserved for the in-between (e.g. faithful on ungrounded but with a blank), which
        is genuinely "promising but not clean", strictly better than a fabricating binder.
    """
    blank = metrics["blank_count"]
    g = metrics["grounded_bind_rate"]
    f = metrics["false_bind_rate"]
    if blank == 0 and g >= 0.75 and f <= 0.34:
        return "PASS"
    # A voter that fabricates grounding (false-binds past the bar) or refuses everything is FAIL,
    # regardless of how clean its blank count is — that is the lethal direction for a voter.
    if f > 0.34 or g == 0.0:
        return "FAIL"
    # Faithful on ungrounded (f<=0.34) and binds some grounded, but blanks -> promising-not-clean.
    if blank > 0:
        return "WEAK"
    return "FAIL"


def main() -> None:
    if not os.getenv("OPENROUTER_API_KEY"):
        print(
            "FATAL: OPENROUTER_API_KEY not set (and not found in .env). "
            "Cannot run the real seam — refusing to fabricate metrics."
        )
        sys.exit(2)

    pool = _load_pool()
    print(f"Loaded evidence pool: {len(pool)} items from {EVIDENCE_POOL_PATH}")
    pairs = _build_labeled_set(pool)
    print(
        f"Labeled set: {sum(1 for p in pairs if p['expected_grounded'])} grounded + "
        f"{sum(1 for p in pairs if not p['expected_grounded'])} ungrounded = {len(pairs)} pairs"
    )
    for p in pairs:
        print(
            f"  PAIR [{p['label']}] claim={p['claim_id']!r} span={p['span_id']!r} "
            f"expected_grounded={p['expected_grounded']}"
        )
    print(
        "Env: PG_MIRROR_REASONING=false PG_SENTINEL_MAX_TOKENS=4000 "
        "PG_FOUR_ROLE_TRANSPORT=openrouter\n"
    )

    results: list[dict] = []
    for slug in CANDIDATES:
        print(f"\n========== CANDIDATE: {slug} ==========")
        metrics = _run_candidate(slug, pairs)
        metrics["verdict"] = _verdict(metrics)
        results.append(metrics)
        print(
            f"[SUMMARY {slug}] blank={metrics['blank_count']} "
            f"grounded_bind_rate={metrics['grounded_bind_rate']:.2f} "
            f"({metrics['grounded_bound']}/{metrics['grounded_total']}) "
            f"false_bind_rate={metrics['false_bind_rate']:.2f} "
            f"({metrics['false_bound']}/{metrics['ungrounded_total']}) "
            f"verdict={metrics['verdict']} served={metrics['served_models']}"
        )

    # --- final ranked table ------------------------------------------------------------------
    print("\n\n================ FINAL RANKED TABLE ================")
    print(
        f"{'slug':<36} {'blank':>5} {'g_bind':>7} {'f_bind':>7} {'verdict':>8}  served"
    )

    def _rank_key(m: dict) -> tuple:
        # FAITHFULNESS-VOTER ranking (NOT a blank-first sort): for a voter the PRIMARY metric is
        # NOT false-binding ungrounded claims (refusing the unsupported IS the job). So sort by
        # false_bind_rate FIRST (lower better), then grounded_bind_rate (higher better), then
        # blank_count (lower better). This ranks a model that rubber-stamps 100% of fabrications
        # BELOW a faithful model that blanked once — the correct order for a faithfulness voter.
        return (
            m["false_bind_rate"],
            -m["grounded_bind_rate"],
            m["blank_count"],
        )

    for m in sorted(results, key=_rank_key):
        print(
            f"{m['slug']:<36} {m['blank_count']:>5} "
            f"{m['grounded_bind_rate']:>7.2f} {m['false_bind_rate']:>7.2f} "
            f"{m['verdict']:>8}  {','.join(m['served_models']) or '(none)'}"
        )

    # --- winner: best FAMILY-LEGAL NON-INCUMBENT with blank=0 + best tradeoff ----------------
    eligible = [
        m
        for m in results
        if m["blank_count"] == 0 and m["slug"] != INCUMBENT and m["grounded_bind_rate"] > 0
    ]
    if eligible:
        winner = sorted(eligible, key=_rank_key)[0]["slug"]
    else:
        # Fall back to the incumbent only if IT genuinely is the best clean option.
        clean = [m for m in results if m["blank_count"] == 0 and m["grounded_bind_rate"] > 0]
        winner = sorted(clean, key=_rank_key)[0]["slug"] if clean else "(none — all blanked/errored)"
    print(f"\nWINNER (best family-legal non-incumbent): {winner}")

    # Machine-readable tail line for the orchestrator.
    print("\nRESULTS_JSON: " + json.dumps({"results": results, "winner": winner}))


if __name__ == "__main__":
    main()
