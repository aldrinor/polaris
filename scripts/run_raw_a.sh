#!/usr/bin/env bash
# =============================================================================
# run_raw_a.sh — the ONE proven "raw-A" agentic-compose run, captured verbatim.
#
# This is the single clean, reproducible entrypoint for the raw-A recipe: it
# drives scripts/compose_agentic_report_s3gear329.py (the confirmed-safe compose
# driver) with the exact environment the proven run required. Every knob below
# is load-bearing — the header explains WHAT each one is and WHY it must be set.
# Override any --flag on the command line; the defaults reproduce raw-A.
#
# Usage:
#   scripts/run_raw_a.sh
#   scripts/run_raw_a.sh --corpus path/to/corpus.json --out-dir out/ --rq-drb-task 72
#
# WHY each knob (do not remove without understanding the failure it prevents):
#
#  (1) LD_LIBRARY_PATH  — sourced from the pinned browserlibs LDPATH.txt. The
#      headless-browser / native shared libs the fetch+render stack loads at
#      runtime live in that sideloaded lib tree; without this path the loader
#      fails to resolve them. Read from the file (not hardcoded) so the pinned
#      value is the single source of truth.
#
#  (2) PG_LOOPBACK_MODE=0 — MUST be 0. Loopback mode short-circuits LLM calls to
#      an in-process stub; with the agentic outliner + real compose it HANGS
#      (the loopback client is not wired for this async agent path). 0 = real
#      OpenRouter calls, which is the only mode raw-A ran under.
#
#  (3a) PG_OUTLINE_AGENT=1 — turn ON the agentic outliner (GLM driver + DeepSeek
#       seed/code model). This IS raw-A; with it off you get the legacy outliner,
#       a different report.
#  (3b) PG_CONTENT_RELEVANCE_SCORE_CHUNK=16 — content-relevance judge batch size.
#       16 is the proven chunking; changing it perturbs judge batching/timing.
#  (3c) PYTORCH_ALLOC_CONF=expandable_segments:True — CUDA allocator uses
#       expandable segments so long GPU-resident phases don't fragment the arena
#       and OOM. Required for the full-corpus run to fit.
#
#  (4) PG_OUTLINE_MAX_TOKENS=131072 / PG_OUTLINE_REASONING_MAX_TOKENS=32768 —
#      the DeepSeek reasoning model TRUNCATES mid-outline at smaller budgets;
#      these two ceilings are what stops the truncation. Proven values.
#
#  (5) OPENROUTER_API_KEY / SERPER_API_KEY — extracted via python-dotenv
#      dotenv_values(), NEVER by bash-sourcing .env. The .env has an unquoted
#      value with a space (line 304: `PG_EXA_CATEGORY=research paper`); `. .env`
#      splits it and bash errors `line 304: paper: command not found`, leaving a
#      half-loaded env. dotenv_values() parses it correctly. We export ONLY the
#      two keys the driver needs — nothing else from .env touches this shell.
#
#  (6) unset PYTHONPATH — a stray PYTHONPATH shadows the repo's own
#      src/polaris_graph with a sibling worktree's copy, causing subtle
#      wrong-module imports. Clear it so the interpreter resolves against this
#      repo only.
#
#  (7) interpreter — /home/polaris/pipeline-env/bin/python (python3.11). The
#      compose stack's deps (torch cu128, dotenv, openrouter client) live in
#      this venv; the system python does not have them.
#
#  (8) flags — --corpus / --rq-drb-task / --out-dir carry the exact raw-A
#      defaults, all overridable:
#        --corpus      data/cp4_corpus_s3gear_329.corrected.json — the same
#                      s3gear-329 corpus the proven run (and _run_16way_s3gear329.sh)
#                      composed over. It is a data artifact (git-ignored / not
#                      checked out in a fresh worktree); supply --corpus to point
#                      at your local copy if the default path is absent.
#        --rq-drb-task 72 — the DeepResearch-Bench task id raw-A judged. The
#                      driver loads its verbatim prompt from
#                      third_party/deep_research_bench/data/prompt_data/query.jsonl
#                      (also a git-ignored data artifact).
#        --out-dir     outputs/raw_a_run — where the composed report + provenance
#                      land; created if missing.
# =============================================================================
set -euo pipefail

# --- Resolve repo root from this script's location (reproducible from anywhere) --
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Pinned, load-bearing paths -------------------------------------------------
PYTHON_BIN="/home/polaris/pipeline-env/bin/python"
LDPATH_FILE="/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/browserlibs/LDPATH.txt"
ENV_FILE="${PG_ENV_FILE:-/workspace/POLARIS/.env}"

# --- (8) CLI flags with proven raw-A defaults -----------------------------------
CORPUS="${REPO_ROOT}/data/cp4_corpus_s3gear_329.corrected.json"
RQ_DRB_TASK="72"
OUT_DIR="${REPO_ROOT}/outputs/raw_a_run"

require_val() { # $1=flag name; guards against a flag given with no value
  [[ $# -ge 2 && -n "${2:-}" && "${2:0:2}" != "--" ]] || {
    echo "run_raw_a.sh: option $1 requires a value" >&2; exit 2; }
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --corpus)      require_val "$1" "${2:-}"; CORPUS="$2"; shift 2 ;;
    --rq-drb-task) require_val "$1" "${2:-}"; RQ_DRB_TASK="$2"; shift 2 ;;
    --out-dir)     require_val "$1" "${2:-}"; OUT_DIR="$2"; shift 2 ;;
    -h|--help)
      grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "run_raw_a.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
done

# --- (1) LD_LIBRARY_PATH from the pinned file -----------------------------------
if [[ ! -f "${LDPATH_FILE}" ]]; then
  echo "run_raw_a.sh: pinned LDPATH file not found: ${LDPATH_FILE}" >&2
  exit 3
fi
LDPATH_VALUE="$(cat "${LDPATH_FILE}")"
# Export EXACTLY the pinned value — do NOT append any inherited LD_LIBRARY_PATH.
# Appending the caller's path makes the effective loader search order depend on
# the invoking shell, which breaks reproducibility. The pinned file is the sole
# source of truth for this run.
export LD_LIBRARY_PATH="${LDPATH_VALUE}"

# --- (2) loopback OFF (else the agentic path hangs) -----------------------------
export PG_LOOPBACK_MODE=0

# --- (3) agentic outliner + judge chunk + CUDA allocator ------------------------
export PG_OUTLINE_AGENT=1
export PG_CONTENT_RELEVANCE_SCORE_CHUNK=16
export PYTORCH_ALLOC_CONF=expandable_segments:True

# --- (4) token ceilings that prevent DeepSeek truncation ------------------------
export PG_OUTLINE_MAX_TOKENS=131072
export PG_OUTLINE_REASONING_MAX_TOKENS=32768

# --- (5) API keys via python-dotenv (NEVER bash-source .env; line 304 breaks it) -
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "run_raw_a.sh: env file not found: ${ENV_FILE}" >&2
  exit 4
fi
OPENROUTER_API_KEY="$(
  "${PYTHON_BIN}" -c 'import sys; from dotenv import dotenv_values; print(dotenv_values(sys.argv[1]).get("OPENROUTER_API_KEY") or "")' "${ENV_FILE}"
)"
SERPER_API_KEY="$(
  "${PYTHON_BIN}" -c 'import sys; from dotenv import dotenv_values; print(dotenv_values(sys.argv[1]).get("SERPER_API_KEY") or "")' "${ENV_FILE}"
)"
if [[ -z "${OPENROUTER_API_KEY}" ]]; then
  echo "run_raw_a.sh: OPENROUTER_API_KEY missing from ${ENV_FILE}" >&2
  exit 5
fi
if [[ -z "${SERPER_API_KEY}" ]]; then
  echo "run_raw_a.sh: SERPER_API_KEY missing from ${ENV_FILE}" >&2
  exit 6
fi
export OPENROUTER_API_KEY SERPER_API_KEY

# --- (6) clear PYTHONPATH so imports resolve against THIS repo -------------------
unset PYTHONPATH

# --- (7)+(8) launch the proven compose driver -----------------------------------
mkdir -p "${OUT_DIR}"
cd "${REPO_ROOT}"
exec "${PYTHON_BIN}" scripts/compose_agentic_report_s3gear329.py \
  --corpus "${CORPUS}" \
  --out-dir "${OUT_DIR}" \
  --rq-drb-task "${RQ_DRB_TASK}"
