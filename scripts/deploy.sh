#!/usr/bin/env bash
# =============================================================================
# POLARIS Deployment Script
# =============================================================================
# Comprehensive deployment automation for the POLARIS Sovereign Deep Research
# Platform. Handles environment validation, GPU detection, dependency
# installation, health checking, and Docker-based deployments.
#
# Usage:
#   ./scripts/deploy.sh               Full deployment (venv + start server)
#   ./scripts/deploy.sh --check-only  Validate environment without deploying
#   ./scripts/deploy.sh --docker      Build and run via Docker Compose
#   ./scripts/deploy.sh --gpu         Force GPU mode (PG_DEVICE=cuda)
#   ./scripts/deploy.sh --no-gpu      Force CPU mode (PG_DEVICE=cpu)
#   ./scripts/deploy.sh --help        Show this help text
#
# Environment:
#   Requires: Python 3.10+, pip, venv
#   Optional: NVIDIA GPU + CUDA, Docker, cloudflared
#
# Exit codes:
#   0  Success
#   1  Prerequisites missing
#   2  Environment configuration error
#   3  Dependency installation failure
#   4  Server failed to start / health check failed
#   5  Docker deployment failure
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly VENV_DIR="${PROJECT_ROOT}/.venv"
readonly ENV_FILE="${PROJECT_ROOT}/.env"
readonly REQUIREMENTS="${PROJECT_ROOT}/requirements.txt"
readonly LOG_DIR="${PROJECT_ROOT}/logs"
readonly DEPLOY_LOG="${LOG_DIR}/deploy.log"
readonly PID_FILE="${PROJECT_ROOT}/.polaris.pid"
readonly DOCKER_IMAGE="polaris-research"
readonly DOCKER_COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
readonly MIN_PYTHON_MAJOR=3
readonly MIN_PYTHON_MINOR=10
readonly HEALTH_CHECK_RETRIES=30
readonly HEALTH_CHECK_INTERVAL=2

# Default server port — read from .env if present, else fallback
DEFAULT_PORT=8765

# ---------------------------------------------------------------------------
# Color output helpers
# ---------------------------------------------------------------------------
_supports_color() {
    if [[ -t 1 ]] && command -v tput &>/dev/null && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
        return 0
    fi
    return 1
}

if _supports_color; then
    readonly C_GREEN="\033[0;32m"
    readonly C_YELLOW="\033[0;33m"
    readonly C_RED="\033[0;31m"
    readonly C_CYAN="\033[0;36m"
    readonly C_BOLD="\033[1m"
    readonly C_DIM="\033[2m"
    readonly C_RESET="\033[0m"
else
    readonly C_GREEN="" C_YELLOW="" C_RED="" C_CYAN="" C_BOLD="" C_DIM="" C_RESET=""
fi

info()    { echo -e "${C_GREEN}[OK]${C_RESET}    $*"; }
warn()    { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
fail()    { echo -e "${C_RED}[FAIL]${C_RESET}  $*"; }
header()  { echo -e "\n${C_BOLD}${C_CYAN}=== $* ===${C_RESET}"; }
detail()  { echo -e "${C_DIM}        $*${C_RESET}"; }

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_log_init() {
    mkdir -p "${LOG_DIR}"
    echo "--- POLARIS deploy started at $(date -u '+%Y-%m-%dT%H:%M:%SZ') ---" >> "${DEPLOY_LOG}"
}

_log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" >> "${DEPLOY_LOG}"
}

# ---------------------------------------------------------------------------
# Cleanup trap
# ---------------------------------------------------------------------------
_cleanup() {
    local exit_code=$?
    if [[ ${exit_code} -ne 0 ]]; then
        _log "Deploy exited with code ${exit_code}"
        # Kill background server if we started one and it is still running
        if [[ -n "${_SERVER_PID:-}" ]] && kill -0 "${_SERVER_PID}" 2>/dev/null; then
            kill "${_SERVER_PID}" 2>/dev/null || true
            wait "${_SERVER_PID}" 2>/dev/null || true
            rm -f "${PID_FILE}"
            _log "Killed background server PID ${_SERVER_PID} due to deployment failure"
        fi
    fi
}
trap _cleanup EXIT

# ---------------------------------------------------------------------------
# State variables set during checks
# ---------------------------------------------------------------------------
_PYTHON_CMD=""
_PYTHON_VERSION=""
_GPU_AVAILABLE=0
_GPU_NAME=""
_GPU_MEMORY=""
_CUDA_VERSION=""
_DOCKER_AVAILABLE=0
_PORT=""
_SERVER_PID=""
_DEPLOY_MODE=""        # "native" or "docker"
_GPU_MODE=""           # "auto", "force", "disabled"
_CHECK_ONLY=0
_FEATURES_ENABLED=()
_FEATURES_DISABLED=()
_WARNINGS=()

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
show_help() {
    cat <<'HELPTEXT'
POLARIS Deployment Script
=========================

Usage:
  deploy.sh [OPTIONS]

Options:
  --check-only   Validate prerequisites and environment without deploying.
  --docker       Deploy using Docker Compose (builds image if needed).
  --gpu          Force GPU mode (sets PG_DEVICE=cuda). Fails if no GPU found.
  --no-gpu       Force CPU mode (sets PG_DEVICE=cpu). Skips GPU detection.
  --port PORT    Override the server port (default: from .env or 8765).
  --help, -h     Show this help text and exit.

Examples:
  # Standard native deployment
  ./scripts/deploy.sh

  # Validate environment only
  ./scripts/deploy.sh --check-only

  # Docker deployment with GPU passthrough
  ./scripts/deploy.sh --docker --gpu

  # Force CPU mode on a specific port
  ./scripts/deploy.sh --no-gpu --port 9000

Environment Variables (read from .env):
  OPENROUTER_API_KEY       Required. LLM gateway API key.
  PG_LIVE_SERVER_PORT      Server port (default 8765).
  PG_NLI_ENABLED           Enable NLI verification (requires GPU or CPU fallback).
  PG_DEVICE                Force device: "cuda" or "cpu".
  POLARIS_DEPLOYMENT_MODE  Deployment mode label (cloud/sovereign/development).

Exit Codes:
  0  Success
  1  Prerequisites missing
  2  Environment configuration error
  3  Dependency installation failure
  4  Server start / health check failure
  5  Docker deployment failure
HELPTEXT
}

parse_args() {
    _DEPLOY_MODE="native"
    _GPU_MODE="auto"
    _CHECK_ONLY=0
    _PORT=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --check-only)
                _CHECK_ONLY=1
                shift
                ;;
            --docker)
                _DEPLOY_MODE="docker"
                shift
                ;;
            --gpu)
                _GPU_MODE="force"
                shift
                ;;
            --no-gpu)
                _GPU_MODE="disabled"
                shift
                ;;
            --port)
                if [[ -z "${2:-}" ]]; then
                    fail "--port requires a value"
                    exit 1
                fi
                _PORT="$2"
                shift 2
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                fail "Unknown option: $1"
                echo "Run deploy.sh --help for usage."
                exit 1
                ;;
        esac
    done
}

# =============================================================================
# Section 1: Prerequisites Check
# =============================================================================
check_prerequisites() {
    header "Prerequisites Check"
    local errors=0

    # --- Python ---
    _PYTHON_CMD=""
    for candidate in python3 python; do
        if command -v "${candidate}" &>/dev/null; then
            local ver
            ver="$("${candidate}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || echo "")"
            if [[ -n "${ver}" ]]; then
                local major minor
                major="$(echo "${ver}" | cut -d. -f1)"
                minor="$(echo "${ver}" | cut -d. -f2)"
                if [[ "${major}" -ge ${MIN_PYTHON_MAJOR} && "${minor}" -ge ${MIN_PYTHON_MINOR} ]]; then
                    _PYTHON_CMD="${candidate}"
                    _PYTHON_VERSION="${ver}"
                    break
                fi
            fi
        fi
    done

    if [[ -n "${_PYTHON_CMD}" ]]; then
        info "Python ${_PYTHON_VERSION} (${_PYTHON_CMD})"
        detail "Path: $(command -v "${_PYTHON_CMD}")"
    else
        fail "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ not found"
        detail "Install Python from https://www.python.org/downloads/"
        errors=$((errors + 1))
    fi

    # --- pip ---
    if [[ -n "${_PYTHON_CMD}" ]]; then
        if "${_PYTHON_CMD}" -m pip --version &>/dev/null; then
            local pip_ver
            pip_ver="$("${_PYTHON_CMD}" -m pip --version 2>/dev/null | awk '{print $2}')"
            info "pip ${pip_ver}"
        else
            fail "pip not available for ${_PYTHON_CMD}"
            errors=$((errors + 1))
        fi
    fi

    # --- venv ---
    if [[ -n "${_PYTHON_CMD}" ]]; then
        if "${_PYTHON_CMD}" -c "import venv" &>/dev/null; then
            info "venv module available"
        else
            fail "venv module not available"
            detail "Install: apt install python3-venv  OR  dnf install python3-venv"
            errors=$((errors + 1))
        fi
    fi

    # --- requirements.txt ---
    if [[ -f "${REQUIREMENTS}" ]]; then
        local req_count
        req_count="$(grep -c '^[a-zA-Z]' "${REQUIREMENTS}" 2>/dev/null || echo 0)"
        info "requirements.txt found (${req_count} packages)"
    else
        fail "requirements.txt not found at ${REQUIREMENTS}"
        errors=$((errors + 1))
    fi

    # --- Docker (optional) ---
    if command -v docker &>/dev/null; then
        local docker_ver
        docker_ver="$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',')"
        _DOCKER_AVAILABLE=1
        info "Docker ${docker_ver}"
        if command -v docker-compose &>/dev/null || docker compose version &>/dev/null 2>&1; then
            info "Docker Compose available"
        else
            warn "Docker Compose not found (needed for --docker mode)"
            if [[ "${_DEPLOY_MODE}" == "docker" ]]; then
                errors=$((errors + 1))
            fi
        fi
    else
        _DOCKER_AVAILABLE=0
        if [[ "${_DEPLOY_MODE}" == "docker" ]]; then
            fail "Docker not installed (required for --docker mode)"
            errors=$((errors + 1))
        else
            warn "Docker not installed (optional, needed for --docker mode)"
        fi
    fi

    # --- Port availability ---
    _resolve_port
    if command -v ss &>/dev/null; then
        if ss -tlnp 2>/dev/null | grep -q ":${_PORT} "; then
            fail "Port ${_PORT} is already in use"
            detail "Free the port or use --port to specify an alternative"
            errors=$((errors + 1))
        else
            info "Port ${_PORT} is available"
        fi
    elif command -v lsof &>/dev/null; then
        if lsof -iTCP:"${_PORT}" -sTCP:LISTEN &>/dev/null; then
            fail "Port ${_PORT} is already in use"
            errors=$((errors + 1))
        else
            info "Port ${_PORT} is available"
        fi
    elif command -v netstat &>/dev/null; then
        if netstat -tlnp 2>/dev/null | grep -q ":${_PORT} "; then
            fail "Port ${_PORT} is already in use"
            errors=$((errors + 1))
        else
            info "Port ${_PORT} is available"
        fi
    else
        warn "Cannot verify port ${_PORT} availability (no ss/lsof/netstat)"
    fi

    # --- curl or wget for health checks ---
    if command -v curl &>/dev/null; then
        info "curl available (for health checks)"
    elif command -v wget &>/dev/null; then
        info "wget available (for health checks)"
    else
        warn "Neither curl nor wget found. Health checks will be skipped."
    fi

    # --- cloudflared (optional) ---
    if command -v cloudflared &>/dev/null; then
        info "cloudflared available (Quick Tunnel support)"
    else
        detail "cloudflared not found (optional: enables remote tunnel access)"
    fi

    if [[ ${errors} -gt 0 ]]; then
        echo ""
        fail "Prerequisites check failed with ${errors} error(s)"
        _log "Prerequisites check FAILED: ${errors} errors"
        exit 1
    fi
    _log "Prerequisites check passed"
}

_resolve_port() {
    # Priority: CLI --port > .env PG_LIVE_SERVER_PORT > default
    if [[ -n "${_PORT}" ]]; then
        return
    fi
    if [[ -f "${ENV_FILE}" ]]; then
        local env_port
        env_port="$(grep -E '^PG_LIVE_SERVER_PORT=' "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]')"
        if [[ -n "${env_port}" ]]; then
            _PORT="${env_port}"
            return
        fi
    fi
    _PORT="${DEFAULT_PORT}"
}

# =============================================================================
# Section 2: GPU Detection
# =============================================================================
detect_gpu() {
    header "GPU Detection"

    if [[ "${_GPU_MODE}" == "disabled" ]]; then
        info "GPU mode disabled via --no-gpu flag"
        _GPU_AVAILABLE=0
        return
    fi

    # --- nvidia-smi ---
    if ! command -v nvidia-smi &>/dev/null; then
        if [[ "${_GPU_MODE}" == "force" ]]; then
            fail "nvidia-smi not found but --gpu flag was specified"
            exit 1
        fi
        warn "nvidia-smi not found. Running in CPU mode."
        _GPU_AVAILABLE=0
        return
    fi

    # --- Query GPU info ---
    local gpu_query
    gpu_query="$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>/dev/null || echo "")"

    if [[ -z "${gpu_query}" ]]; then
        if [[ "${_GPU_MODE}" == "force" ]]; then
            fail "nvidia-smi found but no GPUs detected (--gpu flag requires a GPU)"
            exit 1
        fi
        warn "nvidia-smi found but no GPUs detected. Running in CPU mode."
        _GPU_AVAILABLE=0
        return
    fi

    _GPU_AVAILABLE=1
    _GPU_NAME="$(echo "${gpu_query}" | head -1 | cut -d, -f1 | xargs)"
    _GPU_MEMORY="$(echo "${gpu_query}" | head -1 | cut -d, -f2 | xargs)"
    local driver_ver
    driver_ver="$(echo "${gpu_query}" | head -1 | cut -d, -f3 | xargs)"

    info "GPU detected: ${_GPU_NAME}"
    detail "VRAM: ${_GPU_MEMORY} MiB"
    detail "Driver: ${driver_ver}"

    # --- CUDA version ---
    _CUDA_VERSION="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | xargs || echo "")"
    local cuda_runtime
    cuda_runtime="$(nvcc --version 2>/dev/null | grep -oP 'release \K[0-9]+\.[0-9]+' || echo "")"
    if [[ -n "${cuda_runtime}" ]]; then
        _CUDA_VERSION="${cuda_runtime}"
        info "CUDA Toolkit: ${_CUDA_VERSION}"
    else
        # Fall back to nvidia-smi reported CUDA version
        local smi_cuda
        smi_cuda="$(nvidia-smi 2>/dev/null | grep -oP 'CUDA Version: \K[0-9]+\.[0-9]+' || echo "")"
        if [[ -n "${smi_cuda}" ]]; then
            _CUDA_VERSION="${smi_cuda}"
            info "CUDA Version (driver): ${_CUDA_VERSION}"
            warn "nvcc not found. CUDA toolkit may not be installed."
            detail "Install: https://developer.nvidia.com/cuda-downloads"
        fi
    fi

    # --- PyTorch CUDA check (if venv exists) ---
    if [[ -d "${VENV_DIR}" ]]; then
        local torch_cuda
        torch_cuda="$(_activate_venv_cmd python -c 'import torch; print(torch.cuda.is_available())' 2>/dev/null || echo "unknown")"
        if [[ "${torch_cuda}" == "True" ]]; then
            info "PyTorch CUDA: available"
        elif [[ "${torch_cuda}" == "False" ]]; then
            warn "PyTorch installed but CUDA not available to it"
            detail "May need: pip install torch --index-url https://download.pytorch.org/whl/cu121"
        fi
    fi

    # --- Memory adequacy for NLI ---
    if [[ -n "${_GPU_MEMORY}" ]]; then
        local mem_int
        mem_int="$(echo "${_GPU_MEMORY}" | grep -oP '^[0-9]+' || echo 0)"
        if [[ "${mem_int}" -ge 8000 ]]; then
            info "GPU VRAM sufficient for NLI (flan-t5-large requires ~2GB, batch=32)"
        elif [[ "${mem_int}" -ge 4000 ]]; then
            warn "GPU VRAM is moderate (${mem_int} MiB). Consider reducing PG_NLI_BATCH_SIZE."
        else
            warn "GPU VRAM is low (${mem_int} MiB). NLI may fall back to CPU."
        fi
    fi

    _log "GPU detected: ${_GPU_NAME}, VRAM: ${_GPU_MEMORY} MiB, CUDA: ${_CUDA_VERSION}"
}

# =============================================================================
# Section 3: Environment Setup
# =============================================================================
setup_environment() {
    header "Environment Setup"

    # --- Virtual environment ---
    if [[ -d "${VENV_DIR}" ]]; then
        info "Virtual environment exists at ${VENV_DIR}"
    else
        info "Creating virtual environment at ${VENV_DIR} ..."
        "${_PYTHON_CMD}" -m venv "${VENV_DIR}"
        if [[ $? -eq 0 ]]; then
            info "Virtual environment created"
        else
            fail "Failed to create virtual environment"
            exit 3
        fi
    fi

    # Determine venv python path
    local venv_python
    if [[ -f "${VENV_DIR}/bin/python" ]]; then
        venv_python="${VENV_DIR}/bin/python"
    elif [[ -f "${VENV_DIR}/Scripts/python.exe" ]]; then
        venv_python="${VENV_DIR}/Scripts/python.exe"
    elif [[ -f "${VENV_DIR}/Scripts/python" ]]; then
        venv_python="${VENV_DIR}/Scripts/python"
    else
        fail "Cannot locate python in venv at ${VENV_DIR}"
        exit 3
    fi
    detail "venv Python: ${venv_python}"

    # --- Install / upgrade dependencies ---
    info "Installing dependencies from requirements.txt ..."
    _log "pip install -r requirements.txt starting"

    if "${venv_python}" -m pip install --upgrade pip --quiet 2>>"${DEPLOY_LOG}"; then
        detail "pip upgraded"
    fi

    if "${venv_python}" -m pip install -r "${REQUIREMENTS}" --quiet 2>>"${DEPLOY_LOG}"; then
        info "Dependencies installed successfully"
        _log "pip install completed"
    else
        fail "Dependency installation failed. Check ${DEPLOY_LOG} for details."
        _log "pip install FAILED"
        exit 3
    fi

    # --- .env file ---
    _check_env_file

    # --- GPU environment variable ---
    _set_gpu_env
}

_check_env_file() {
    header "Environment Configuration (.env)"

    if [[ ! -f "${ENV_FILE}" ]]; then
        warn ".env file not found at ${ENV_FILE}"
        echo ""
        echo "  A template .env file will be generated with required variables."
        echo "  You MUST edit it and add your API keys before running the server."
        echo ""
        _generate_env_template
        fail ".env file was generated at ${ENV_FILE}. Edit it and re-run deploy."
        exit 2
    fi

    info ".env file found"

    # --- Validate required variables ---
    local errors=0

    # OPENROUTER_API_KEY is required unless sovereign mode
    local deployment_mode
    deployment_mode="$(grep -E '^POLARIS_DEPLOYMENT_MODE=' "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]')"

    if [[ "${deployment_mode}" != "sovereign" ]]; then
        local or_key
        or_key="$(grep -E '^OPENROUTER_API_KEY=' "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]')"
        if [[ -z "${or_key}" || "${or_key}" == "your_openrouter_api_key_here" ]]; then
            fail "OPENROUTER_API_KEY is missing or placeholder in .env"
            detail "Get a key at https://openrouter.ai/keys"
            errors=$((errors + 1))
        else
            info "OPENROUTER_API_KEY is set"
        fi
    else
        info "Sovereign mode: OPENROUTER_API_KEY not required"
    fi

    # Check optional but important keys
    _check_optional_key "SERPER_API_KEY"            "Web search (Serper)"
    _check_optional_key "SEMANTIC_SCHOLAR_API_KEY"  "Academic search (S2)"
    _check_optional_key "EXA_API_KEY"               "Neural search (Exa)"
    _check_optional_key "JINA_API_KEY"              "Content fetch (Jina Reader)"

    # Check critical feature flags
    _check_feature_flag "POLARIS_CLUSTER_SYNTHESIS" "Cluster-based synthesis"
    _check_feature_flag "POLARIS_CITEFIRST_ENABLED" "Citation-first synthesis"
    _check_feature_flag "PG_NLI_ENABLED"            "NLI verification (GPU)"
    _check_feature_flag "PG_STORM_ENABLED"          "STORM multi-perspective interviews"
    _check_feature_flag "PG_EXA_ENABLED"            "Exa neural search"
    _check_feature_flag "PG_JINA_ENABLED"           "Jina Reader content fetch"
    _check_feature_flag "PG_AGENTIC_SEARCH_ENABLED" "Agentic search loop"
    _check_feature_flag "PG_CHECKPOINT_ENABLED"     "Pipeline checkpointing"
    _check_feature_flag "PG_TRACING_ENABLED"        "JSONL tracing"
    _check_feature_flag "PG_SMART_ART_ENABLED"      "Smart art generation (Mermaid.js)"
    _check_feature_flag "PG_SOURCE_AUTHORITY_ENABLED" "Source authority scoring"

    if [[ ${errors} -gt 0 ]]; then
        echo ""
        fail "Environment validation failed with ${errors} error(s)"
        exit 2
    fi

    _log "Environment configuration validated"
}

_check_optional_key() {
    local key_name="$1"
    local description="$2"
    local val
    val="$(grep -E "^${key_name}=" "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]')"
    if [[ -n "${val}" && "${val}" != *"your_"* ]]; then
        info "${description}: configured"
    else
        warn "${description}: not configured (${key_name})"
        _WARNINGS+=("${description} not configured")
    fi
}

_check_feature_flag() {
    local flag_name="$1"
    local description="$2"
    local val
    val="$(grep -E "^${flag_name}=" "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]')"
    if [[ "${val}" == "1" || "${val}" == "true" || "${val}" == "True" ]]; then
        _FEATURES_ENABLED+=("${description}")
    else
        _FEATURES_DISABLED+=("${description}")
    fi
}

_set_gpu_env() {
    if [[ "${_GPU_MODE}" == "disabled" ]]; then
        export PG_DEVICE="cpu"
        info "PG_DEVICE=cpu (GPU disabled via --no-gpu)"
    elif [[ "${_GPU_MODE}" == "force" ]]; then
        if [[ ${_GPU_AVAILABLE} -eq 1 ]]; then
            export PG_DEVICE="cuda"
            info "PG_DEVICE=cuda (forced via --gpu, GPU: ${_GPU_NAME})"
        else
            fail "GPU forced via --gpu but no GPU detected"
            exit 1
        fi
    else
        # Auto-detect
        if [[ ${_GPU_AVAILABLE} -eq 1 ]]; then
            export PG_DEVICE="cuda"
            info "PG_DEVICE=cuda (auto-detected GPU: ${_GPU_NAME})"
        else
            export PG_DEVICE="cpu"
            info "PG_DEVICE=cpu (no GPU detected)"
        fi
    fi
}

_generate_env_template() {
    cat > "${ENV_FILE}" <<'ENVTEMPLATE'
# =============================================================================
# POLARIS Environment Configuration (Generated by deploy.sh)
# =============================================================================
# IMPORTANT: Replace placeholder values with your actual API keys.
# Documentation: See architecture.md and CLAUDE.md for full configuration reference.
# =============================================================================

# --- LLM Gateway (REQUIRED) ---
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_DEFAULT_MODEL=deepseek/deepseek-v4-pro
OPENROUTER_BUDGET_USD=50.0
OPENROUTER_PROVIDER_ORDER=Chutes,DeepInfra,Fireworks
OPENROUTER_ALLOW_FALLBACKS=true
OPENROUTER_REQUIRE_PARAMETERS=true

# --- Web Search (Serper) ---
SERPER_API_KEY=your_serper_api_key_here

# --- Academic Search (Semantic Scholar) ---
SEMANTIC_SCHOLAR_API_KEY=your_s2_api_key_here
SEMANTIC_SCHOLAR_RATE_LIMIT=1.0

# --- Neural Search (Exa) ---
EXA_API_KEY=your_exa_api_key_here
PG_EXA_ENABLED=1
PG_EXA_QUERIES_PER_VECTOR=5
PG_EXA_RESULTS_PER_QUERY=10

# --- Content Fetch (Jina Reader) ---
JINA_API_KEY=your_jina_api_key_here
PG_JINA_ENABLED=1

# --- Content Fetch (Firecrawl, optional) ---
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
PG_FIRECRAWL_ENABLED=0

# --- Pipeline Settings ---
PG_QUERIES_PER_VECTOR=50
PG_WEB_RESULTS_PER_QUERY=20
PG_ACADEMIC_RESULTS_PER_QUERY=20
PG_MAX_SOURCES_TO_ANALYZE=200
PG_MIN_EVIDENCE_COUNT=20
PG_MIN_FAITHFULNESS=0.70
PG_MAX_ITERATIONS=5
PG_MAX_EXECUTION_MINUTES=180
PG_MAX_SECTIONS=15
PG_MIN_TOTAL_WORDS=10000
PG_TARGET_TOTAL_WORDS=12000
PG_MIN_CITATIONS=30
PG_MIN_UNIQUE_SOURCES=20
PG_OUTPUT_DIR=outputs/polaris_graph

# --- Feature Flags ---
POLARIS_CLUSTER_SYNTHESIS=1
POLARIS_CITEFIRST_ENABLED=1
POLARIS_LLM_COT_FILTER=1
POLARIS_SECTION_COT_FILTER=1
PG_STORM_ENABLED=1
PG_AGENTIC_SEARCH_ENABLED=1
PG_CHECKPOINT_ENABLED=1
PG_TRACING_ENABLED=1
PG_SMART_ART_ENABLED=1
PG_SOURCE_AUTHORITY_ENABLED=1
PG_NLI_ENABLED=0
PG_NLI_MODEL=flan-t5-large
PG_NLI_BATCH_SIZE=32

# --- Server ---
PG_LIVE_SERVER_PORT=8765
POLARIS_DEPLOYMENT_MODE=cloud
POLARIS_VERSION=1.0.0

# --- Cost & Budget ---
PG_COST_LEDGER_PATH=logs/pg_cost_ledger.jsonl
PG_BUDGET_GUARD_USD=150.0
ENVTEMPLATE

    info "Template .env generated at ${ENV_FILE}"
}

# =============================================================================
# Section 4: Data Directory Setup
# =============================================================================
setup_directories() {
    header "Directory Setup"

    local dirs=(
        "${PROJECT_ROOT}/data"
        "${PROJECT_ROOT}/data/documents"
        "${PROJECT_ROOT}/data/benchmarks"
        "${PROJECT_ROOT}/outputs"
        "${PROJECT_ROOT}/outputs/polaris_graph"
        "${PROJECT_ROOT}/logs"
        "${PROJECT_ROOT}/state"
        "${PROJECT_ROOT}/state/feedback_checkpoints"
        "${PROJECT_ROOT}/config"
        "${PROJECT_ROOT}/config/settings"
    )

    local created=0
    local existed=0

    for dir in "${dirs[@]}"; do
        if [[ -d "${dir}" ]]; then
            existed=$((existed + 1))
        else
            mkdir -p "${dir}"
            created=$((created + 1))
        fi
    done

    info "Directories verified: ${existed} existing, ${created} created"

    # --- Check SQLite caches ---
    local sqlite_files=(
        "state/pg_content_cache.sqlite"
        "state/pg_search_cache.sqlite"
        "state/pg_evidence_hierarchy.sqlite"
        "state/pg_session_feedback.sqlite"
        "state/pg_checkpoints.sqlite"
    )

    local cache_count=0
    for sf in "${sqlite_files[@]}"; do
        if [[ -f "${PROJECT_ROOT}/${sf}" ]]; then
            cache_count=$((cache_count + 1))
        fi
    done
    if [[ ${cache_count} -gt 0 ]]; then
        info "SQLite caches found: ${cache_count}/5"
    else
        detail "No SQLite caches yet (will be created on first run)"
    fi

    # --- Check outputs ---
    local result_count=0
    if [[ -d "${PROJECT_ROOT}/outputs/polaris_graph" ]]; then
        result_count="$(find "${PROJECT_ROOT}/outputs/polaris_graph" -name '*_result.json' 2>/dev/null | wc -l | tr -d '[:space:]')"
    fi
    if [[ "${result_count}" -gt 0 ]]; then
        info "Existing research results: ${result_count}"
    fi

    # --- Permissions (skip on Windows / Git Bash where chmod is limited) ---
    if [[ "$(uname -s)" != MINGW* && "$(uname -s)" != MSYS* && "$(uname -s)" != CYGWIN* ]]; then
        chmod -R u+rwX "${PROJECT_ROOT}/data" "${PROJECT_ROOT}/outputs" "${PROJECT_ROOT}/logs" "${PROJECT_ROOT}/state" 2>/dev/null || true
        detail "Permissions set (u+rwX) on data, outputs, logs, state"
    fi

    _log "Directory setup complete: ${existed} existing, ${created} created"
}

# =============================================================================
# Section 5: Health Check (Native Mode)
# =============================================================================
start_and_check_health() {
    header "Server Startup and Health Check"

    # Resolve venv python
    local venv_python
    venv_python="$(_find_venv_python)"

    # Kill any existing POLARIS server on the same port
    _kill_existing_server

    # Start server in background
    info "Starting POLARIS server on port ${_PORT} ..."
    _log "Starting server: ${venv_python} -m scripts.live_server --port ${_PORT}"

    cd "${PROJECT_ROOT}"

    # Set PG_DEVICE for the server process
    export PG_DEVICE="${PG_DEVICE:-cpu}"

    # Launch server
    "${venv_python}" -m scripts.live_server --port "${_PORT}" --no-tunnel >> "${DEPLOY_LOG}" 2>&1 &
    _SERVER_PID=$!
    echo "${_SERVER_PID}" > "${PID_FILE}"

    info "Server process started (PID: ${_SERVER_PID})"
    detail "Logs: ${DEPLOY_LOG}"

    # Wait for health check
    info "Waiting for server to become healthy ..."
    local attempt=0
    local healthy=0

    while [[ ${attempt} -lt ${HEALTH_CHECK_RETRIES} ]]; do
        attempt=$((attempt + 1))

        # Check process is still alive
        if ! kill -0 "${_SERVER_PID}" 2>/dev/null; then
            fail "Server process exited prematurely (PID: ${_SERVER_PID})"
            detail "Check logs: ${DEPLOY_LOG}"
            _log "Server died before health check passed"
            exit 4
        fi

        # Try health endpoint
        local status_code=""
        if command -v curl &>/dev/null; then
            status_code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${_PORT}/health" 2>/dev/null || echo "")"
        elif command -v wget &>/dev/null; then
            status_code="$(wget --spider -S "http://localhost:${_PORT}/health" 2>&1 | grep 'HTTP/' | awk '{print $2}' | tail -1 || echo "")"
        fi

        if [[ "${status_code}" == "200" ]]; then
            healthy=1
            break
        fi

        detail "Attempt ${attempt}/${HEALTH_CHECK_RETRIES}: waiting ${HEALTH_CHECK_INTERVAL}s ..."
        sleep "${HEALTH_CHECK_INTERVAL}"
    done

    if [[ ${healthy} -eq 0 ]]; then
        fail "Server did not become healthy after $((HEALTH_CHECK_RETRIES * HEALTH_CHECK_INTERVAL))s"
        detail "Check logs: ${DEPLOY_LOG}"
        _log "Health check FAILED after ${HEALTH_CHECK_RETRIES} attempts"
        exit 4
    fi

    info "Health check passed"

    # Fetch /health response for details
    local health_json=""
    if command -v curl &>/dev/null; then
        health_json="$(curl -s "http://localhost:${_PORT}/health" 2>/dev/null || echo "{}")"
    fi
    if [[ -n "${health_json}" ]]; then
        detail "Response: ${health_json}"
    fi

    # Verify /api/system/info
    local sysinfo_code=""
    if command -v curl &>/dev/null; then
        sysinfo_code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${_PORT}/api/system/info" 2>/dev/null || echo "")"
    fi
    if [[ "${sysinfo_code}" == "200" ]]; then
        info "/api/system/info endpoint: OK"
        local sysinfo
        sysinfo="$(curl -s "http://localhost:${_PORT}/api/system/info" 2>/dev/null || echo "")"
        if [[ -n "${sysinfo}" ]]; then
            detail "System info: ${sysinfo}"
        fi
    else
        warn "/api/system/info returned ${sysinfo_code:-no response}"
    fi

    _log "Server healthy on port ${_PORT}, PID ${_SERVER_PID}"
}

_find_venv_python() {
    if [[ -f "${VENV_DIR}/bin/python" ]]; then
        echo "${VENV_DIR}/bin/python"
    elif [[ -f "${VENV_DIR}/Scripts/python.exe" ]]; then
        echo "${VENV_DIR}/Scripts/python.exe"
    elif [[ -f "${VENV_DIR}/Scripts/python" ]]; then
        echo "${VENV_DIR}/Scripts/python"
    else
        fail "Cannot locate venv Python"
        exit 3
    fi
}

_activate_venv_cmd() {
    # Run a command inside the venv without sourcing activate
    local venv_python
    venv_python="$(_find_venv_python)"
    "${venv_python}" "$@"
}

_kill_existing_server() {
    # Kill server by PID file
    if [[ -f "${PID_FILE}" ]]; then
        local old_pid
        old_pid="$(cat "${PID_FILE}" 2>/dev/null || echo "")"
        if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
            warn "Stopping existing POLARIS server (PID: ${old_pid})"
            kill "${old_pid}" 2>/dev/null || true
            # Wait up to 10 seconds for graceful shutdown
            local wait_count=0
            while kill -0 "${old_pid}" 2>/dev/null && [[ ${wait_count} -lt 10 ]]; do
                sleep 1
                wait_count=$((wait_count + 1))
            done
            if kill -0 "${old_pid}" 2>/dev/null; then
                kill -9 "${old_pid}" 2>/dev/null || true
            fi
            info "Previous server stopped"
        fi
        rm -f "${PID_FILE}"
    fi
}

# =============================================================================
# Section 6: Docker Mode
# =============================================================================
deploy_docker() {
    header "Docker Deployment"

    if [[ ${_DOCKER_AVAILABLE} -eq 0 ]]; then
        fail "Docker is not installed. Cannot proceed with --docker mode."
        exit 5
    fi

    if [[ ! -f "${DOCKER_COMPOSE_FILE}" ]]; then
        fail "docker-compose.yml not found at ${DOCKER_COMPOSE_FILE}"
        exit 5
    fi

    if [[ ! -f "${ENV_FILE}" ]]; then
        fail ".env file required for Docker deployment"
        exit 2
    fi

    # Determine docker compose command
    local compose_cmd=""
    if docker compose version &>/dev/null 2>&1; then
        compose_cmd="docker compose"
    elif command -v docker-compose &>/dev/null; then
        compose_cmd="docker-compose"
    else
        fail "Neither 'docker compose' nor 'docker-compose' available"
        exit 5
    fi

    # --- Build the image ---
    info "Building Docker image '${DOCKER_IMAGE}' ..."
    _log "Docker build starting"

    cd "${PROJECT_ROOT}"
    if docker build -t "${DOCKER_IMAGE}" . 2>>"${DEPLOY_LOG}"; then
        info "Docker image built successfully"
        local image_size
        image_size="$(docker images "${DOCKER_IMAGE}" --format '{{.Size}}' 2>/dev/null | head -1)"
        detail "Image size: ${image_size}"
    else
        fail "Docker build failed. Check ${DEPLOY_LOG} for details."
        exit 5
    fi

    # --- Stop existing containers ---
    info "Stopping any existing containers ..."
    ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" down 2>>"${DEPLOY_LOG}" || true

    # --- Compose up with GPU if available ---
    local gpu_flag=""
    if [[ ${_GPU_AVAILABLE} -eq 1 && "${_GPU_MODE}" != "disabled" ]]; then
        info "GPU passthrough enabled (${_GPU_NAME})"
        # For compose, GPU is defined in the compose file via deploy.resources
        # For standalone docker run, we would use --gpus all
        # Set env var so the container knows to use GPU
        export PG_DEVICE="cuda"
    else
        export PG_DEVICE="cpu"
    fi

    # --- Override port if specified ---
    export POLARIS_PORT="${_PORT}"

    info "Starting containers via Docker Compose ..."
    _log "Docker compose up starting"

    if ${compose_cmd} -f "${DOCKER_COMPOSE_FILE}" up -d 2>>"${DEPLOY_LOG}"; then
        info "Containers started"
    else
        fail "Docker Compose up failed. Check ${DEPLOY_LOG} for details."
        exit 5
    fi

    # --- Wait for health ---
    info "Waiting for Docker health check ..."
    local attempt=0
    local healthy=0

    # Docker Compose maps to POLARIS_PORT on host
    local docker_port="${_PORT}"
    # The compose file maps ${POLARIS_PORT:-8000}:8000, but our port config may differ
    # Read from compose: the internal port is 8000
    local compose_port
    compose_port="$(grep -oP '\$\{POLARIS_PORT:-\K[0-9]+' "${DOCKER_COMPOSE_FILE}" 2>/dev/null | head -1 || echo "${_PORT}")"
    docker_port="${compose_port}"

    while [[ ${attempt} -lt ${HEALTH_CHECK_RETRIES} ]]; do
        attempt=$((attempt + 1))

        local status_code=""
        if command -v curl &>/dev/null; then
            status_code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${docker_port}/health" 2>/dev/null || echo "")"
        fi

        if [[ "${status_code}" == "200" ]]; then
            healthy=1
            break
        fi

        detail "Attempt ${attempt}/${HEALTH_CHECK_RETRIES}: waiting ${HEALTH_CHECK_INTERVAL}s ..."
        sleep "${HEALTH_CHECK_INTERVAL}"
    done

    if [[ ${healthy} -eq 0 ]]; then
        fail "Docker container did not become healthy"
        detail "Check logs: docker logs polaris-web-1"
        exit 5
    fi

    info "Docker deployment healthy"
    _PORT="${docker_port}"
    _log "Docker deployment complete on port ${docker_port}"
}

# =============================================================================
# Section 7: Summary
# =============================================================================
print_summary() {
    header "Deployment Summary"

    echo ""
    echo -e "  ${C_BOLD}POLARIS Sovereign Deep Research Platform${C_RESET}"
    echo -e "  ${C_DIM}$(date -u '+%Y-%m-%d %H:%M:%S UTC')${C_RESET}"
    echo ""

    # --- Mode ---
    if [[ ${_CHECK_ONLY} -eq 1 ]]; then
        echo -e "  Mode:       ${C_CYAN}Check Only${C_RESET} (no server started)"
    elif [[ "${_DEPLOY_MODE}" == "docker" ]]; then
        echo -e "  Mode:       ${C_CYAN}Docker${C_RESET}"
    else
        echo -e "  Mode:       ${C_CYAN}Native (venv)${C_RESET}"
    fi

    # --- URLs ---
    if [[ ${_CHECK_ONLY} -eq 0 ]]; then
        echo -e "  Dashboard:  ${C_GREEN}http://localhost:${_PORT}${C_RESET}"
        echo -e "  Health:     ${C_GREEN}http://localhost:${_PORT}/health${C_RESET}"
        echo -e "  System:     ${C_GREEN}http://localhost:${_PORT}/api/system/info${C_RESET}"
        echo -e "  SSE Events: ${C_GREEN}http://localhost:${_PORT}/api/events${C_RESET}"
    fi

    # --- GPU ---
    echo ""
    if [[ ${_GPU_AVAILABLE} -eq 1 ]]; then
        echo -e "  GPU:        ${C_GREEN}${_GPU_NAME} (${_GPU_MEMORY} MiB)${C_RESET}"
        echo -e "  CUDA:       ${_CUDA_VERSION}"
        echo -e "  Device:     ${C_GREEN}cuda${C_RESET}"
    else
        echo -e "  GPU:        ${C_DIM}Not available${C_RESET}"
        echo -e "  Device:     cpu"
    fi

    # --- Python ---
    echo -e "  Python:     ${_PYTHON_VERSION}"

    # --- PID ---
    if [[ -n "${_SERVER_PID}" ]]; then
        echo -e "  Server PID: ${_SERVER_PID}"
        echo -e "  PID file:   ${PID_FILE}"
    fi

    # --- Features ---
    echo ""
    echo -e "  ${C_BOLD}Enabled Features:${C_RESET}"
    if [[ ${#_FEATURES_ENABLED[@]} -gt 0 ]]; then
        for feat in "${_FEATURES_ENABLED[@]}"; do
            echo -e "    ${C_GREEN}[ON]${C_RESET}  ${feat}"
        done
    else
        echo -e "    ${C_DIM}(none detected)${C_RESET}"
    fi

    if [[ ${#_FEATURES_DISABLED[@]} -gt 0 ]]; then
        echo ""
        echo -e "  ${C_BOLD}Disabled Features:${C_RESET}"
        for feat in "${_FEATURES_DISABLED[@]}"; do
            echo -e "    ${C_DIM}[OFF]${C_RESET} ${feat}"
        done
    fi

    # --- Warnings ---
    if [[ ${#_WARNINGS[@]} -gt 0 ]]; then
        echo ""
        echo -e "  ${C_BOLD}${C_YELLOW}Warnings:${C_RESET}"
        for w in "${_WARNINGS[@]}"; do
            echo -e "    ${C_YELLOW}*${C_RESET} ${w}"
        done
    fi

    # --- Quick commands ---
    echo ""
    echo -e "  ${C_BOLD}Useful Commands:${C_RESET}"
    if [[ "${_DEPLOY_MODE}" == "docker" ]]; then
        echo -e "    ${C_DIM}View logs:${C_RESET}    docker logs -f polaris-web-1"
        echo -e "    ${C_DIM}Stop:${C_RESET}         docker compose down"
        echo -e "    ${C_DIM}Restart:${C_RESET}      docker compose restart"
        echo -e "    ${C_DIM}Shell:${C_RESET}        docker exec -it polaris-web-1 /bin/bash"
    else
        echo -e "    ${C_DIM}View logs:${C_RESET}    tail -f ${DEPLOY_LOG}"
        echo -e "    ${C_DIM}Stop:${C_RESET}         kill \$(cat ${PID_FILE})"
        echo -e "    ${C_DIM}Restart:${C_RESET}      ./scripts/deploy.sh"
        echo -e "    ${C_DIM}Check only:${C_RESET}   ./scripts/deploy.sh --check-only"
    fi

    echo ""
    _log "Deployment summary printed. Deployment complete."
}

# =============================================================================
# Main
# =============================================================================
main() {
    parse_args "$@"

    echo ""
    echo -e "${C_BOLD}${C_CYAN}"
    echo "  ____   ___  _        _    ____  ___ ____  "
    echo " |  _ \\ / _ \\| |      / \\  |  _ \\|_ _/ ___| "
    echo " | |_) | | | | |     / _ \\ | |_) || |\\___ \\ "
    echo " |  __/| |_| | |___ / ___ \\|  _ < | | ___) |"
    echo " |_|    \\___/|_____/_/   \\_\\_| \\_\\___|____/ "
    echo ""
    echo -e "${C_RESET}${C_DIM}  Sovereign Deep Research Platform — Deployment${C_RESET}"
    echo ""

    _log_init
    _log "Deploy started: mode=${_DEPLOY_MODE}, gpu=${_GPU_MODE}, check_only=${_CHECK_ONLY}"

    # Step 1: Prerequisites
    check_prerequisites

    # Step 2: GPU detection
    detect_gpu

    if [[ ${_CHECK_ONLY} -eq 1 ]]; then
        # Check-only: validate env and dirs but do not start anything
        if [[ -f "${ENV_FILE}" ]]; then
            _check_env_file
        else
            warn ".env file not found (would be generated on full deploy)"
        fi
        setup_directories
        print_summary
        echo ""
        info "Check-only mode complete. No server started."
        exit 0
    fi

    if [[ "${_DEPLOY_MODE}" == "docker" ]]; then
        # Docker path: validate env, then build and run
        _check_env_file
        setup_directories
        deploy_docker
    else
        # Native path: full setup
        setup_environment
        setup_directories
        start_and_check_health
    fi

    print_summary
}

main "$@"
