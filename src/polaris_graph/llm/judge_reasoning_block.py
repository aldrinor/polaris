"""I-deepfix-001 — shared reasoning-block builder for the reasoning-model side judges.

§9.1.8 (I-arch-003 #1253, operator-locked 2026-06-13): a reasoning model emits its internal reasoning
burst FIRST, drawn from the SAME ``max_tokens`` budget as the answer. If a provider lets reasoning run up
to the full budget, the JSON verdict never lands and ``message.content`` comes back EMPTY (finish_reason=
``length``). The operator's live probe proved this on ``z-ai/glm-5.2`` (max_tokens=20 -> content=None; the
reasoning burst ate the whole budget; max_tokens=300 -> content='OK'). A starved verdict then either
fails-closed (quality degrade) or, on a slow pinned provider, stalls.

THE PROVEN CURE is NOT "raise max_tokens" (already generous at 131072) — it is a NUMERIC
``reasoning.max_tokens`` cap STRICTLY BELOW the total ``max_tokens`` so the verdict ALWAYS keeps at least
``content_floor`` tokens no matter how long a provider runs reasoning. This is exactly what the D8 Mirror
does (``roles/openrouter_role_transport`` mirror branch, EMPIRICALLY validated 2026-06-14 by
``scripts/diagnostics/mirror_glm_provider_bakeoff.py``: GLM at reasoning_cap=100000 / max_tokens=131072
returned 3/3 clean, finish=stop, on ALL of atlas-cloud/z-ai/baidu/novita/gmicloud). The three glm-family
side judges (credibility / entailment / semantic-conflict) never got this cap — they relied on
``reasoning:{effort:...}``, and ``effort`` is a NO-OP on GLM (its OpenRouter endpoints do not list it), so
a provider that runs reasoning long could still blank them. This leaf helper carries the ONE proven
invariant to all three, keeping the fix in a single place.

Model-aware (mirrors ``roles/openrouter_role_transport._judge_reasoning_block`` semantics):
  * glm family -> ``{"max_tokens": reasoning_cap}``  numeric cap; reasoning STAYS ON; content guaranteed.
  * otherwise  -> ``{"effort": effort}``             BYTE-IDENTICAL to the prior side-judge default (e.g.
                                                     the kimi-k2.6 entailment override keeps its proven
                                                     effort-tier shape; kimi's own 21-provider breadth +
                                                     small reasoning burst already prevent starvation).

FAITHFULNESS-NEUTRAL: reasoning stays ON for every reasoning model; only HOW glm reasoning is bounded
changes (a numeric ceiling instead of an ignored effort tier). No verdict logic, no model, no drop.
LAW VI: the reasoning cap and content floor are env-overridable named knobs (no magic numbers).

Leaf module — stdlib only, no heavy imports — so the off-mode side judges pay zero import cost.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("polaris_graph.judge_reasoning_block")

# LAW VI (env-overridable, no magic numbers). Defaults mirror the PROVEN D8 Mirror bound
# (reasoning_cap 100000, content floor 4000 => the invariant reasoning_cap <= max_tokens - 4000).
_ENV_REASONING_MAX_TOKENS = "PG_JUDGE_REASONING_MAX_TOKENS"
_DEFAULT_REASONING_MAX_TOKENS = 100000
_ENV_REASONING_CONTENT_FLOOR = "PG_JUDGE_REASONING_CONTENT_FLOOR"
_DEFAULT_REASONING_CONTENT_FLOOR = 4000
# Absolute lower bound for the reasoning cap: a per-claim NLI/credibility burst is ~300 tokens live, so
# 1024 is already ~3x headroom while guaranteeing the cap can never collapse to a starving value even if
# a bad env pushes max_tokens very low.
_REASONING_CAP_FLOOR = 1024

# glm-family slug detection. The lock pins generator+mirror (and the legacy_compat side judges) to
# ``z-ai/glm-5.2``; other glm hosts/mirrors may carry the family in the slug (``glm``) or a known vendor
# prefix. Substring + prefix keeps it robust to a provider-scoped slug.
_GLM_SLUG_PREFIXES = ("z-ai/", "zhipuai/", "zhipu/", "thudm/")


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def is_glm_slug(slug: str | None) -> bool:
    """True iff ``slug`` names a GLM-family model (the family that ignores ``effort`` and needs the
    numeric reasoning cap)."""
    if not slug:
        return False
    s = str(slug).strip().lower()
    return "glm" in s or s.startswith(_GLM_SLUG_PREFIXES)


_STARVED_BUDGET_WARNED = False


def _warn_starved_budget_once(total: int, floor: int) -> None:
    """Warn LOUDLY (once per process) that a reasoning judge was configured with a total
    ``max_tokens`` too small to keep the full content floor — a §9.1.8 misconfiguration
    ("max_tokens ALWAYS go to the model REAL max"). Warn-once avoids per-claim log spam."""
    global _STARVED_BUDGET_WARNED
    if _STARVED_BUDGET_WARNED:
        return
    _STARVED_BUDGET_WARNED = True
    logger.warning(
        "[judge_reasoning_block] STARVED reasoning budget: total max_tokens=%d is below the "
        "healthy floor (content_floor=%d + reasoning_cap_floor=%d = %d). Per CLAUDE.md §9.1.8 a "
        "reasoning judge's max_tokens must go to the model REAL max; this tiny budget degrades the "
        "reasoning burst. Bounding reasoning STRICTLY BELOW the total so content can NEVER blank — "
        "but RAISE the judge's max_tokens env knob.",
        total, floor, _REASONING_CAP_FLOOR, floor + _REASONING_CAP_FLOOR,
    )


def reasoning_cap_for(max_tokens: int) -> int:
    """The numeric reasoning ceiling for a glm judge given its total ``max_tokens`` budget.

    HARD INVARIANT (Codex I-deepfix-001 diff-gate iter1 P1): the returned cap is ALWAYS STRICTLY
    BELOW ``max_tokens`` — reasoning can never consume the entire budget, so the verdict JSON always
    keeps at least some content headroom. Two regimes:

      * HEALTHY budget (``max_tokens - content_floor >= _REASONING_CAP_FLOOR``): reserve the FULL
        ``content_floor`` for the verdict and cap reasoning at ``min(cap_env, max_tokens - floor)``
        (<= max_tokens - floor, hence strictly below max_tokens). The 131072 mirror-chain-min budget
        every side judge uses lands here (cap 100000, floor 4000 => 31072 tokens of content headroom).
      * STARVED budget (a §9.1.8 MISCONFIGURATION — a reasoning judge should never run this small):
        the full content floor no longer fits. We STILL never let reasoning eat the whole budget —
        reasoning is bounded to ~half (strictly below max_tokens; content keeps the other half) and a
        loud warn-once fires so the bad token knob is visible. Fixes the prior inversion where the
        1024 floor could exceed a low total (e.g. the 256-token relevance-judge starvation config),
        making ``reasoning.max_tokens >= max_tokens`` and re-opening the blank-verdict path.

    Env-overridable per LAW VI (``PG_JUDGE_REASONING_MAX_TOKENS`` / ``PG_JUDGE_REASONING_CONTENT_FLOOR``).
    """
    cap_env = _int_env(_ENV_REASONING_MAX_TOKENS, _DEFAULT_REASONING_MAX_TOKENS)
    floor = _int_env(_ENV_REASONING_CONTENT_FLOOR, _DEFAULT_REASONING_CONTENT_FLOOR)
    try:
        total = int(max_tokens)
    except (TypeError, ValueError):
        total = 0
    headroom = total - floor
    if headroom >= _REASONING_CAP_FLOOR:
        # cap <= headroom = total - floor < total  -> strictly below AND full content floor kept.
        return min(cap_env, headroom)
    # Starved budget: the content floor no longer fits. Keep reasoning STRICTLY below the total so
    # SOME content room always remains, and warn loudly (this violates §9.1.8's max-budget lock).
    _warn_starved_budget_once(total, floor)
    if total <= 1:
        # Degenerate (never a real config: every side judge clamps its total >= 64). Nothing sensible
        # fits; return the smallest positive cap. Real callers never send total <= 1.
        return 1
    return max(1, min(total - 1, total // 2))


def build_judge_reasoning_block(model_slug: str | None, effort: object, max_tokens: int) -> dict:
    """Build the ``reasoning`` block for a reasoning-model side judge's OpenRouter body.

    * A GLM-family judge gets a NUMERIC ``{"max_tokens": reasoning_cap}`` ceiling (the proven Mirror
      pattern) so the verdict can never be blanked by reasoning eating the budget — the §9.1.8 fix.
    * Any other model keeps the prior ``{"effort": effort}`` shape (byte-identical), so the kimi-k2.6
      entailment override and any future non-glm judge are UNCHANGED.

    Faithfulness-neutral, transport-only. ``effort`` is passed through verbatim for the non-glm path.
    """
    if is_glm_slug(model_slug):
        return {"max_tokens": reasoning_cap_for(max_tokens)}
    return {"effort": effort}
