#!/usr/bin/env bash
# LOCKED-IN GENERATOR RECIPE: Kimi K3 (moonshotai/kimi-k3) as the report generator.
#
# Rationale (2026-07-21): a head-to-head A/B (this recipe vs the GLM-5.2 baseline run_raw_a.sh,
# same pipeline, only the generator model differs) scored RACE Overall 0.4903 vs 0.4605 — a +0.030
# win, non-overlapping over 3x re-scoring, driven by Insight (+0.045) and Comprehensiveness (+0.030).
# Kimi K3 is the top open-weights model as of July 2026 (Artificial Analysis Intelligence Index #3
# overall / #1 open). General (a frontier open model, not benchmark-overfit); this recipe only swaps
# the generator model + the routing needed to reach it, nothing task-specific.
#
# Routing to reach kimi-k3 on OpenRouter (Together is not one of the pinned GLM providers):
#   PG_GENERATOR_PROVIDER_FANOUT=1  -> UNPIN the generator from the GLM-5.2 provider order
#                                      (friendli/baseten/novita, allow_fallbacks:false) so kimi-k3
#                                      auto-routes to its own provider instead of NoEndpointError 404.
#   OPENROUTER_REQUIRE_PARAMETERS=false -> the pipeline sends `reasoning`; no kimi-k3 provider
#                                      ADVERTISES that param under strict matching, so strict routing
#                                      finds no endpoint. Relax it (the provider still HONORS reasoning).
#   OPENROUTER_ALLOW_FALLBACKS=true  -> allow fallback across kimi-k3 endpoints.
# (A cleaner hardening — retry a structural "no endpoints" 404 with strict routing relaxed instead of
# these env flags — is a tracked follow-up; the env recipe is what the validated 0.4903 run used.)
#
# Usage: scripts/run_k3.sh [--corpus PATH] [--rq-drb-task N] [--out-dir DIR]
set -uo pipefail

export PG_GENERATOR_MODEL="moonshotai/kimi-k3"
export PG_GENERATOR_PROVIDER_FANOUT="1"
export OPENROUTER_REQUIRE_PARAMETERS="false"
export OPENROUTER_ALLOW_FALLBACKS="true"

HERE="$(cd "$(dirname "$0")" && pwd)"
case " $* " in
  *" --out-dir "*) exec "$HERE/run_raw_a.sh" "$@" ;;
  *)              exec "$HERE/run_raw_a.sh" --out-dir outputs/k3gen_run "$@" ;;
esac
