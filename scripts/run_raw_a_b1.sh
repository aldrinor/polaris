#!/usr/bin/env bash
# Batch-1 stage-boundary run: the Step-1 baseline recipe (run_raw_a.sh) with Round-2 Levers B/E/F
# ARMED. Used to score the Batch-1 evidence-substrate boundary against the Step-1 baseline
# (outputs/run_raw_a, RACE 0.4643 / FACT 20 cites 0.85).
#
# All four flags are central-config-gated (config_defaults.py) and DEFAULT OFF (empty => byte-
# identical). This recipe OPTS THIS RUN into them; it does NOT touch .env or the code defaults, so
# other pipelines and a normal run_raw_a.sh stay unchanged. The faithfulness engine is untouched
# (run_raw_a.sh keeps PG_STRICT_VERIFY_OFF for the scoring experiment; no post-gen gate is added).
#
# Lever B (source eligibility + citation re-anchoring):
#   PG_RQ_SOURCE_ELIGIBILITY_ENFORCE  -> task-derived eligibility contract; ineligible rows are KEPT
#                                        at the default 0.3 demote weight (never zeroed), same-facet
#                                        substitution + fetch recovery. (weight left at code default.)
#   PG_CITATION_REANCHOR_PRIMARY      -> re-point a secondary-cited claim to a strictly-more-primary
#                                        pool row grounding the SAME numbers, BEFORE strict_verify.
# Lever E (fetch-until-usable):
#   PG_FETCH_STUB_SALVAGE             -> route DOI/PMID scrape-stubs through the CrossRef/OpenAlex/
#                                        PubMed/S2 salvage lane (min body + max-sources defaults).
# Lever F (canonicalize works):
#   PG_CANONICAL_WORK_BIBLIOGRAPHY    -> fold same-work (DOI-first) mirrors to one canonical [N].
#
# Usage: scripts/run_raw_a_b1.sh [--corpus PATH] [--rq-drb-task N] [--out-dir DIR]
set -uo pipefail

export PG_RQ_SOURCE_ELIGIBILITY_ENFORCE=1
export PG_CITATION_REANCHOR_PRIMARY=1
export PG_FETCH_STUB_SALVAGE=1
export PG_CANONICAL_WORK_BIBLIOGRAPHY=1

HERE="$(cd "$(dirname "$0")" && pwd)"
# Default this recipe's out-dir to the Batch-1 run unless the caller overrides it.
case " $* " in
  *" --out-dir "*) exec "$HERE/run_raw_a.sh" "$@" ;;
  *)              exec "$HERE/run_raw_a.sh" --out-dir outputs/b1_run "$@" ;;
esac
