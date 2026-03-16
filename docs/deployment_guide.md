# POLARIS Deployment Guide

**Version**: 1.0.0
**Last Updated**: 2026-02-27
**Audience**: DevOps Engineers, System Administrators, IT Security Teams

---

## Table of Contents

1. [Hardware Requirements](#1-hardware-requirements)
2. [Software Prerequisites](#2-software-prerequisites)
3. [Quick Start (Demo Mode)](#3-quick-start-demo-mode)
4. [Cloud Mode Deployment](#4-cloud-mode-deployment)
5. [Sovereign Mode Deployment](#5-sovereign-mode-deployment)
6. [Configuration Reference](#6-configuration-reference)
7. [Network Requirements](#7-network-requirements)
8. [Kubernetes Deployment](#8-kubernetes-deployment)
9. [Troubleshooting](#9-troubleshooting)
10. [Health Check Verification](#10-health-check-verification)
11. [Upgrading Between Versions](#11-upgrading-between-versions)

---

## 1. Hardware Requirements

### 1.1 Minimum Specifications (Cloud Mode)

Cloud mode offloads LLM inference and NLI verification to external APIs. The host machine runs the pipeline orchestrator, embedding generation, and web UI.

| Component | Minimum | Notes |
|-----------|---------|-------|
| CPU | 4 cores (x86_64) | LangGraph orchestration, async I/O |
| RAM | 16 GB | ChromaDB vector store, embedding cache, SQLite caches |
| GPU | None required | Embedding uses CPU fallback (slower) |
| Storage | 50 GB SSD | Outputs, caches, checkpoint data, JSONL trace logs |
| Network | 25 Mbps sustained | API calls to OpenRouter, Serper, Exa, Semantic Scholar |

### 1.2 Recommended Specifications (Cloud Mode)

| Component | Recommended | Notes |
|-----------|-------------|-------|
| CPU | 8+ cores (x86_64 or ARM64) | Parallel content fetching (30 concurrent), analysis batches |
| RAM | 32 GB | Large evidence pools (3,000+ items), map-reduce clustering |
| GPU | NVIDIA RTX 3060+ (8 GB VRAM) | Local sentence-transformers embedding, 10x faster |
| Storage | 200 GB NVMe SSD | Multi-vector campaign data, ChromaDB persistence |
| Network | 100 Mbps sustained | STORM interviews, agentic search loops |

### 1.3 Sovereign Mode Specifications

Sovereign mode runs all inference locally. No data leaves the network boundary.

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| CPU | 16 cores | 32+ cores (Xeon/EPYC) | vLLM serving, SearxNG, concurrent fetch |
| RAM | 64 GB | 128 GB | Model weights, KV cache, pipeline state |
| GPU | 1x NVIDIA A10 (24 GB) | 2x NVIDIA A100 (80 GB) | vLLM with 32B+ active parameter models |
| VRAM | 24 GB minimum | 160 GB total | MoE models require substantial VRAM for KV cache |
| Storage | 500 GB NVMe SSD | 2 TB NVMe RAID | Model weights (~50-100 GB), search index, outputs |
| Network | Air-gapped or restricted | Air-gapped with DMZ proxy | Zero egress for classified workloads |

### 1.4 NLI Verification Hardware

The local NLI pipeline (MiniCheck flan-t5-large) requires GPU for production throughput:

| Configuration | Hardware | Throughput | Latency |
|---------------|----------|------------|---------|
| GPU (recommended) | NVIDIA RTX 4070+ (8 GB VRAM) | ~200 claims/sec | 0.14s per batch |
| CPU fallback | 8+ cores | ~5 claims/sec | 4-8s per batch |

---

## 2. Software Prerequisites

### 2.1 Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.11+ | Pipeline runtime, FastAPI server |
| pip | 23.0+ | Dependency management |
| Docker | 24.0+ | Container runtime (optional for quick start) |
| Docker Compose | 2.20+ | Multi-container orchestration (optional) |
| Git | 2.40+ | Version control, deployment |

### 2.2 GPU Software (Optional but Recommended)

| Software | Version | Purpose |
|----------|---------|---------|
| NVIDIA Driver | 535+ | GPU access |
| CUDA Toolkit | 12.1+ | GPU compute for PyTorch |
| cuDNN | 8.9+ | Accelerated neural network ops |

### 2.3 Sovereign Mode Additional Software

| Software | Version | Purpose |
|----------|---------|---------|
| vLLM | 0.4.0+ | Local LLM serving (OpenAI-compatible API) |
| SearxNG | Latest | Self-hosted metasearch engine |
| Playwright | 1.40+ | Browser automation for JS-rendered content |
| Chromium | Latest | Headless browser for Crawl4AI |

### 2.4 Python Dependencies

Install from the project root:

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Install MiniCheck for NLI verification (not on PyPI)
pip install "minicheck @ git+https://github.com/Liyan06/MiniCheck.git@main"

# Install Crawl4AI browser
playwright install chromium
```

---

## 3. Quick Start (Demo Mode)

Demo mode uses Docker Compose to bring up the full stack with cloud APIs. Suitable for evaluation and demonstration purposes.

### 3.1 Prerequisites

- Docker and Docker Compose installed
- API keys for OpenRouter and Serper (minimum)
- Network access to external APIs

### 3.2 Steps

```bash
# 1. Clone the repository
git clone https://github.com/your-org/polaris.git
cd polaris

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with your API keys (see Section 6 for all variables)

# 3. Launch the stack
docker-compose up -d

# 4. Verify health
curl http://localhost:8000/health

# 5. Open the dashboard
# Navigate to http://localhost:8000 in your browser
```

### 3.3 Docker Compose Configuration

```yaml
# docker-compose.yml
version: "3.9"

services:
  polaris:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./outputs:/app/outputs
      - ./logs:/app/logs
      - ./state:/app/state
      - polaris-chroma:/app/chroma_data
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  polaris-chroma:
```

### 3.4 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install "minicheck @ git+https://github.com/Liyan06/MiniCheck.git@main" && \
    playwright install chromium --with-deps

# Application code
COPY . .

# FastAPI server
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "src.polaris_graph.live_server:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

---

## 4. Cloud Mode Deployment

Cloud mode uses external APIs for LLM inference, web search, and content retrieval. The pipeline orchestration, embedding, NLI verification, and synthesis run locally.

### 4.1 Required API Keys

| Service | Environment Variable | Purpose | Cost Model |
|---------|---------------------|---------|------------|
| OpenRouter | `OPENROUTER_API_KEY` | LLM inference (Kimi K2.5 via 400+ models) | ~$0.45-2.25/M tokens |
| Serper | `SERPER_API_KEY` | Web search (10 results/query) | 2,500 queries/month free |
| Semantic Scholar | `SEMANTIC_SCHOLAR_API_KEY` | Academic paper search | Free with API key (1 RPS) |
| Exa | `EXA_API_KEY` | Neural semantic search | $0.005/search, $0.001/content |
| Jina | `JINA_API_KEY` | Content extraction (JS rendering) | 20 req/min free tier |

### 4.2 Optional API Keys

| Service | Environment Variable | Purpose | Notes |
|---------|---------------------|---------|-------|
| Firecrawl | `FIRECRAWL_API_KEY` | Premium content extraction | 500 credits/month free |
| Open PageRank | `OPEN_PAGERANK_API_KEY` | Source authority scoring | Free tier available |
| OpenAlex | `PG_OPENALEX_EMAIL` | Academic metadata search | Free, polite pool with email |

### 4.3 Configuration Steps

```bash
# 1. Set required API keys in .env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_DEFAULT_MODEL=moonshotai/kimi-k2.5
SERPER_API_KEY=your-serper-key
SEMANTIC_SCHOLAR_API_KEY=your-s2-key
EXA_API_KEY=your-exa-key
JINA_API_KEY=jina_your-key

# 2. Set pipeline configuration
PG_MAX_EXECUTION_MINUTES=180
PG_MAX_ITERATIONS=5
PG_MIN_FAITHFULNESS=0.70

# 3. Enable features
PG_NLI_ENABLED=1
PG_STORM_ENABLED=1
PG_AGENTIC_SEARCH_ENABLED=1
PG_CHECKPOINT_ENABLED=1
PG_TRACING_ENABLED=1

# 4. Start the server
python -m uvicorn src.polaris_graph.live_server:app --host 0.0.0.0 --port 8000
```

### 4.4 Cloud Mode Architecture

```
                    Internet
                       |
    +-----------------------------------------+
    |            POLARIS Server                |
    |  +-----------------------------------+  |
    |  | FastAPI (port 8000)               |  |
    |  |   /api/research   POST            |  |
    |  |   /api/events     SSE             |  |
    |  |   /health         GET             |  |
    |  +-----------------------------------+  |
    |  | LangGraph Pipeline (8 nodes)      |  |
    |  |   plan → search → storm →         |  |
    |  |   analyze → verify → evaluate →   |  |
    |  |   synthesize + search_gaps        |  |
    |  +-----------------------------------+  |
    |  | Local Components                  |  |
    |  |   ChromaDB | SQLite caches        |  |
    |  |   sentence-transformers           |  |
    |  |   MiniCheck NLI (GPU optional)    |  |
    |  +-----------------------------------+  |
    +-----------------------------------------+
              |        |        |
         OpenRouter  Serper  Semantic Scholar
         (LLM)      (Search)  (Academic)
              |        |        |
           Exa      Jina    OpenAlex
         (Neural)  (Fetch)  (Metadata)
```

---

## 5. Sovereign Mode Deployment

Sovereign mode eliminates all external API dependencies. Every component runs within the organization's network boundary. No data egresses.

### 5.1 Component Replacements

| Cloud Component | Sovereign Replacement | Configuration Change |
|-----------------|----------------------|---------------------|
| OpenRouter (LLM) | vLLM + local model | `OPENROUTER_BASE_URL=http://localhost:8080/v1` |
| Serper (web search) | SearxNG | `SERPER_BASE_URL=http://localhost:8888/search` |
| Exa (neural search) | Disabled or local Elasticsearch | `PG_EXA_ENABLED=0` |
| Jina (content fetch) | Crawl4AI + Trafilatura | `PG_JINA_ENABLED=0`, `PG_CRAWL4AI_ENABLED=1` |
| Semantic Scholar | Local S2 mirror or OpenAlex | `PG_OPENALEX_ENABLED=1` |
| Open PageRank | Disabled | `PG_SOURCE_CONFIDENCE_ENABLED=0` |

### 5.2 vLLM Setup

```bash
# Install vLLM
pip install vllm

# Serve a model (example: Kimi K2.5 or Qwen2.5-32B)
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-32B-Instruct \
    --host 0.0.0.0 \
    --port 8080 \
    --tensor-parallel-size 2 \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.90 \
    --dtype bfloat16

# Verify vLLM is serving
curl http://localhost:8080/v1/models
```

### 5.3 SearxNG Setup

```bash
# Docker deployment
docker run -d \
    --name searxng \
    -p 8888:8080 \
    -v ./searxng:/etc/searxng \
    searxng/searxng:latest

# Configure SearxNG for JSON API
# Edit searxng/settings.yml:
#   search:
#     formats:
#       - html
#       - json
```

### 5.4 Sovereign .env Configuration

The key insight: POLARIS uses OpenAI-compatible APIs throughout. Switching from cloud to sovereign requires changing URLs, not code.

```bash
# === THE SWITCH: Change these 3 lines ===
OPENROUTER_API_KEY=not-needed-for-local
OPENROUTER_BASE_URL=http://localhost:8080/v1
OPENROUTER_DEFAULT_MODEL=Qwen/Qwen2.5-32B-Instruct

# === Disable cloud search, enable local ===
SERPER_API_KEY=not-needed
PG_EXA_ENABLED=0
PG_JINA_ENABLED=0
PG_FIRECRAWL_ENABLED=0
PG_SOURCE_CONFIDENCE_ENABLED=0

# === Enable local alternatives ===
PG_CRAWL4AI_ENABLED=1
PG_TRAFILATURA_ENABLED=1
PG_NLI_ENABLED=1
PG_NLI_MODEL=flan-t5-large

# === Everything else stays the same ===
PG_STORM_ENABLED=1
PG_AGENTIC_SEARCH_ENABLED=1
PG_CHECKPOINT_ENABLED=1
PG_TRACING_ENABLED=1
PG_MAX_EXECUTION_MINUTES=180
```

### 5.5 Air-Gapped Deployment

For environments with no internet access:

1. **Pre-stage model weights** on a transfer device:
   ```bash
   # On internet-connected machine
   python -c "from transformers import AutoModel; AutoModel.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')"
   python -c "from transformers import AutoModel; AutoModel.from_pretrained('google/flan-t5-large')"
   # Copy ~/.cache/huggingface/ to transfer device
   ```

2. **Pre-stage Python packages**:
   ```bash
   pip download -r requirements.txt -d ./packages/
   # Transfer packages/ directory
   pip install --no-index --find-links=./packages/ -r requirements.txt
   ```

3. **Pre-stage Chromium binary** for Crawl4AI:
   ```bash
   playwright install chromium
   # Copy browser binary from ~/.cache/ms-playwright/
   ```

4. **Configure SearxNG** to use intranet search engines only.

5. **Set environment** to prevent any network egress:
   ```bash
   # Firewall: block all outbound on the POLARIS host
   # The only allowed connections: vLLM (8080), SearxNG (8888), localhost
   ```

---

## 6. Configuration Reference

### 6.1 Core API Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | (required) | API key for OpenRouter LLM gateway |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Base URL for LLM API (change for vLLM) |
| `OPENROUTER_DEFAULT_MODEL` | `moonshotai/kimi-k2.5` | Default LLM model identifier |
| `OPENROUTER_BUDGET_USD` | `50.0` | Maximum spend per session |
| `OPENROUTER_PROVIDER_ORDER` | `Chutes,DeepInfra,Fireworks` | Provider routing preference |
| `OPENROUTER_ALLOW_FALLBACKS` | `true` | Allow fallback to alternative providers |
| `OPENROUTER_REQUIRE_PARAMETERS` | `true` | Only route to providers supporting json_object |
| `OPENROUTER_INPUT_COST_PER_M` | `0.45` | Input token cost per million |
| `OPENROUTER_OUTPUT_COST_PER_M` | `2.25` | Output token cost per million |

### 6.2 Search Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SERPER_API_KEY` | (required for cloud) | Serper web search API key |
| `SEMANTIC_SCHOLAR_API_KEY` | (required for cloud) | Semantic Scholar API key |
| `EXA_API_KEY` | (optional) | Exa neural search API key |
| `JINA_API_KEY` | (optional) | Jina content extraction API key |
| `FIRECRAWL_API_KEY` | (optional) | Firecrawl content extraction API key |
| `OPEN_PAGERANK_API_KEY` | (optional) | Open PageRank authority scoring |
| `PG_EXA_ENABLED` | `1` | Enable Exa neural search |
| `PG_JINA_ENABLED` | `1` | Enable Jina content extraction |
| `PG_FIRECRAWL_ENABLED` | `0` | Enable Firecrawl content extraction |
| `PG_CRAWL4AI_ENABLED` | `1` | Enable Crawl4AI local content extraction |
| `PG_TRAFILATURA_ENABLED` | `1` | Enable Trafilatura content extraction |
| `PG_OPENALEX_ENABLED` | `1` | Enable OpenAlex academic search |
| `PG_SOURCE_CONFIDENCE_ENABLED` | `1` | Enable Open PageRank scoring |

### 6.3 Pipeline Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_QUERIES_PER_VECTOR` | `50` | Sub-queries generated per research vector |
| `PG_WEB_RESULTS_PER_QUERY` | `20` | Web results fetched per query |
| `PG_ACADEMIC_RESULTS_PER_QUERY` | `20` | Academic results fetched per query |
| `PG_WEB_CONCURRENCY` | `25` | Concurrent web search requests |
| `PG_ACADEMIC_CONCURRENCY` | `1` | Concurrent academic API requests (rate limited) |
| `PG_MAX_SOURCES_TO_ANALYZE` | `200` | Maximum sources to analyze per iteration |
| `PG_MAX_ACADEMIC_PAGES` | `3` | Maximum Semantic Scholar pagination pages |
| `PG_MIN_EVIDENCE_COUNT` | `20` | Minimum evidence items before synthesis |
| `PG_MIN_FAITHFULNESS` | `0.70` | Minimum faithfulness score (0.0-1.0) |
| `PG_MAX_ITERATIONS` | `5` | Maximum pipeline iteration loops |
| `PG_MAX_EXECUTION_MINUTES` | `180` | Total pipeline timeout in minutes |

### 6.4 Synthesis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_MAX_SECTIONS` | `15` | Maximum report sections |
| `PG_MAX_WORDS_PER_SECTION` | `2000` | Maximum words per section |
| `PG_MIN_TOTAL_WORDS` | `10000` | Minimum total report words |
| `PG_TARGET_TOTAL_WORDS` | `12000` | Target total report words |
| `PG_TARGET_WORDS_PER_SECTION` | `1000` | Target words per section |
| `PG_MIN_CITATIONS` | `30` | Minimum citation count |
| `PG_MIN_UNIQUE_SOURCES` | `20` | Minimum unique source URLs |
| `PG_MAX_CITATION_FREQUENCY` | `5` | Maximum times a single source can be cited |

### 6.5 STORM Multi-Perspective Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_STORM_ENABLED` | `1` | Enable STORM multi-perspective interviews |
| `PG_STORM_PERSPECTIVES_COUNT` | `5` | Number of expert perspectives |
| `PG_STORM_ROUNDS_PER_PERSPECTIVE` | `3` | Interview rounds per perspective |
| `PG_STORM_MAX_TIME_SECONDS` | `1200` | STORM phase timeout |
| `PG_STORM_INTERVIEW_TIMEOUT` | `300` | Per-interview timeout |

### 6.6 Verification Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_NLI_ENABLED` | `1` | Enable local NLI verification (MiniCheck) |
| `PG_NLI_MODEL` | `flan-t5-large` | NLI model name |
| `PG_NLI_BATCH_SIZE` | `32` | NLI inference batch size |
| `PG_NLI_DISPUTE_THRESHOLD` | `0.4` | NLI dispute detection threshold |
| `PG_FAITHFULNESS_NLI_THRESHOLD` | `0.75` | Minimum NLI score for faithfulness |
| `PG_BALANCED_PROMPTING` | `1` | Enable balanced verify-and-disprove prompting |
| `PG_VERIFY_BATCH_SIZE` | `5` | Claims per verification batch |
| `PG_VERIFY_CONCURRENCY` | `30` | Concurrent verification batches |
| `PG_VERIFY_BATCH_TIMEOUT` | `600` | Per-batch verification timeout (seconds) |
| `PG_VERIFY_RETRY_CAP` | `3` | Maximum consecutive timeout retries |

### 6.7 Agentic Search Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_AGENTIC_SEARCH_ENABLED` | `1` | Enable Gemini-style agentic search loop |
| `PG_AGENTIC_MAX_ROUNDS` | `8` | Maximum search-read-reason rounds |
| `PG_AGENTIC_MAX_QUERIES` | `120` | Maximum total queries across rounds |
| `PG_AGENTIC_MAX_TIME_SECONDS` | `1500` | Agentic phase timeout |
| `PG_AGENTIC_SEED_QUERIES` | `9` | Initial seed queries |
| `PG_AGENTIC_CONTENT_READING_ENABLED` | `1` | Enable in-loop page reading |
| `PG_AGENTIC_PAGES_PER_ROUND` | `6` | Pages read per search round |
| `PG_AGENTIC_PAGE_CONTENT_CAP` | `15000` | Characters per page to analyze |

### 6.8 Quality Gate Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_GOLD_CONFIDENCE_THRESHOLD` | `0.6` | Minimum confidence for GOLD tier |
| `PG_GOLD_RELEVANCE_THRESHOLD` | `0.6` | Minimum relevance for GOLD tier |
| `PG_SILVER_CONFIDENCE_THRESHOLD` | `0.3` | Minimum confidence for SILVER tier |
| `PG_SILVER_RELEVANCE_THRESHOLD` | `0.4` | Minimum relevance for SILVER tier |
| `PG_SOURCE_TOPIC_GATE` | `0.30` | Source topic relevance gate |
| `PG_OFFTOPIC_THRESHOLD` | `0.30` | Off-topic content detection threshold |
| `PG_MAX_EVIDENCE_FOR_VERIFY` | `1500` | Evidence cap for verification |
| `PG_MAX_EVIDENCE_FOR_SYNTHESIS` | `1500` | Evidence cap for synthesis |

### 6.9 Budget and Checkpoint Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_BUDGET_GUARD_USD` | `150.0` | Maximum USD spend per pipeline run |
| `PG_CHECKPOINT_ENABLED` | `1` | Enable LangGraph checkpointing |
| `PG_COST_LEDGER_PATH` | `logs/pg_cost_ledger.jsonl` | JSONL cost tracking file |
| `PG_TRACING_ENABLED` | `1` | Enable JSONL pipeline tracing |

---

## 7. Network Requirements

### 7.1 Cloud Mode

| Destination | Port | Protocol | Purpose |
|-------------|------|----------|---------|
| openrouter.ai | 443 | HTTPS | LLM inference |
| google.serper.dev | 443 | HTTPS | Web search |
| api.semanticscholar.org | 443 | HTTPS | Academic search |
| api.exa.ai | 443 | HTTPS | Neural search |
| r.jina.ai | 443 | HTTPS | Content extraction |
| api.firecrawl.dev | 443 | HTTPS | Content extraction (optional) |
| api.openpagerank.com | 443 | HTTPS | Authority scoring (optional) |
| api.openalex.org | 443 | HTTPS | Academic metadata |
| Various web domains | 443/80 | HTTPS/HTTP | Source content fetching |

**Bandwidth**: ~500 MB per research vector (search results + content fetching + LLM API payloads)

### 7.2 Sovereign Mode

| Destination | Port | Protocol | Purpose |
|-------------|------|----------|---------|
| localhost | 8080 | HTTP | vLLM inference server |
| localhost | 8888 | HTTP | SearxNG search engine |
| localhost | 8000 | HTTP | POLARIS FastAPI server |

**Bandwidth**: Zero external. All traffic is loopback or intranet only.

### 7.3 Firewall Rules (Sovereign)

```
# Allow only internal traffic
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -d 10.0.0.0/8 -j ACCEPT
iptables -A OUTPUT -d 172.16.0.0/12 -j ACCEPT
iptables -A OUTPUT -d 192.168.0.0/16 -j ACCEPT
iptables -A OUTPUT -j DROP
```

---

## 8. Kubernetes Deployment

### 8.1 Helm Chart Structure

```
polaris-helm/
  Chart.yaml
  values.yaml
  templates/
    deployment.yaml
    service.yaml
    configmap.yaml
    secret.yaml
    pvc.yaml
    hpa.yaml
    ingress.yaml
```

### 8.2 values.yaml

```yaml
# polaris-helm/values.yaml
replicaCount: 1

image:
  repository: your-registry/polaris
  tag: "1.0.0"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: true
  className: nginx
  annotations:
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
  hosts:
    - host: polaris.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: polaris-tls
      hosts:
        - polaris.example.com

resources:
  requests:
    cpu: "4"
    memory: "16Gi"
  limits:
    cpu: "8"
    memory: "32Gi"
    nvidia.com/gpu: "1"

persistence:
  enabled: true
  storageClass: "gp3"
  size: 200Gi

autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 3
  targetCPUUtilizationPercentage: 70

env:
  OPENROUTER_BASE_URL: "https://openrouter.ai/api/v1"
  OPENROUTER_DEFAULT_MODEL: "moonshotai/kimi-k2.5"
  PG_MAX_EXECUTION_MINUTES: "180"
  PG_NLI_ENABLED: "1"
  PG_STORM_ENABLED: "1"
  PG_CHECKPOINT_ENABLED: "1"
  PG_TRACING_ENABLED: "1"

secrets:
  OPENROUTER_API_KEY: ""
  SERPER_API_KEY: ""
  SEMANTIC_SCHOLAR_API_KEY: ""
  EXA_API_KEY: ""
  JINA_API_KEY: ""
```

### 8.3 Deployment Template

```yaml
# polaris-helm/templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "polaris.fullname" . }}
  labels:
    app: polaris
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: polaris
  template:
    metadata:
      labels:
        app: polaris
    spec:
      containers:
        - name: polaris
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: {{ include "polaris.fullname" . }}-config
            - secretRef:
                name: {{ include "polaris.fullname" . }}-secrets
          volumeMounts:
            - name: data
              mountPath: /app/outputs
              subPath: outputs
            - name: data
              mountPath: /app/logs
              subPath: logs
            - name: data
              mountPath: /app/state
              subPath: state
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: {{ include "polaris.fullname" . }}-data
```

### 8.4 Deploying

```bash
# Install
helm install polaris ./polaris-helm \
  --namespace polaris \
  --create-namespace \
  --set secrets.OPENROUTER_API_KEY=sk-or-v1-xxx \
  --set secrets.SERPER_API_KEY=xxx

# Upgrade
helm upgrade polaris ./polaris-helm \
  --namespace polaris \
  --reuse-values

# Verify
kubectl get pods -n polaris
kubectl logs -n polaris deployment/polaris -f
```

### 8.5 Sovereign Kubernetes (vLLM Sidecar)

```yaml
# Additional container for vLLM in sovereign mode
containers:
  - name: vllm
    image: vllm/vllm-openai:latest
    args:
      - "--model"
      - "Qwen/Qwen2.5-32B-Instruct"
      - "--host"
      - "0.0.0.0"
      - "--port"
      - "8080"
      - "--tensor-parallel-size"
      - "2"
    resources:
      limits:
        nvidia.com/gpu: "2"
    volumeMounts:
      - name: model-cache
        mountPath: /root/.cache/huggingface
  - name: searxng
    image: searxng/searxng:latest
    ports:
      - containerPort: 8080
        name: search
```

---

## 9. Troubleshooting

### 9.1 Common Issues

#### Issue: Pipeline hangs at verification phase
**Symptom**: Pipeline progress stalls after "analyze" node, no verification events.
**Cause**: Verification batch timeout with large evidence pools (3000+ items).
**Solution**:
```bash
# Increase verification timeout
PG_VERIFY_BATCH_TIMEOUT=600
PG_VERIFY_GATHER_TIMEOUT=7200
# Cap evidence to prevent unbounded growth
PG_MAX_EVIDENCE_FOR_VERIFY=1500
```

#### Issue: "CUDA out of memory" during NLI verification
**Symptom**: RuntimeError: CUDA out of memory.
**Cause**: NLI batch size too large for available VRAM.
**Solution**:
```bash
# Reduce NLI batch size (default 32 requires ~8GB VRAM)
PG_NLI_BATCH_SIZE=16  # For 4-6 GB VRAM
PG_NLI_BATCH_SIZE=8   # For 2-4 GB VRAM
# Or disable GPU NLI
PG_NLI_ENABLED=0      # Falls back to LLM-based verification
```

#### Issue: OpenRouter returns empty content
**Symptom**: LLM responses have empty `content` field, all output in `reasoning_content`.
**Cause**: Provider misroutes generate() output for reasoning models.
**Solution**: Built-in defense-in-depth: when `reasoning_content` exceeds 200 characters and `content` is empty, POLARIS automatically uses `reasoning_content` as the response.

#### Issue: Kimi K2.5 returns stub JSON
**Symptom**: Verification returns 3-character strings like `":[{"` instead of valid JSON.
**Cause**: Intermittent Kimi K2.5 behavior under load.
**Solution**: Built-in FIX-V6 detects stub JSON and falls back to `reasoning_content` extraction with retry.

#### Issue: Synthesis timeout with map-reduce clustering
**Symptom**: Clustering phase times out with "25/26 batches timed out".
**Solution**:
```bash
PG_CLUSTER_BATCH_TIMEOUT=600
PG_CLUSTER_CONCURRENCY=10
PG_CLUSTER_BATCH_SIZE=50
```

#### Issue: Low faithfulness scores (<70%)
**Symptom**: Faithfulness below threshold, pipeline iterates repeatedly.
**Cause**: Content cap mismatch between analyzer and verifier, or paywall sources.
**Solution**:
```bash
# Ensure caps are aligned
PG_CONTENT_PER_SOURCE=10000
PG_VERIFIER_CONTENT_CAP=10000
# Enable paywall detection
PG_MIN_USEFUL_CONTENT=500
```

#### Issue: SearxNG returns no results (Sovereign mode)
**Symptom**: All search queries return empty results.
**Cause**: SearxNG engines not configured or blocked by target sites.
**Solution**: Configure SearxNG with multiple engine backends (Google, Bing, DuckDuckGo). Enable JSON output format in `settings.yml`.

#### Issue: SSE events not reaching browser
**Symptom**: Dashboard shows "Connecting..." indefinitely.
**Cause**: Reverse proxy buffering SSE responses.
**Solution**: Configure proxy to disable buffering:
```nginx
# Nginx
proxy_buffering off;
proxy_cache off;
proxy_set_header Connection '';
proxy_http_version 1.1;
chunked_transfer_encoding off;
```

### 9.2 Log Locations

| Log | Path | Purpose |
|-----|------|---------|
| Pipeline log | `logs/polaris_graph.log` | Detailed pipeline execution log |
| Cost ledger | `logs/pg_cost_ledger.jsonl` | Per-call cost tracking |
| Trace events | `outputs/polaris_graph/{vector_id}/trace.jsonl` | Pipeline node events |
| Session log | `logs/session_log.md` | Development session audit trail |
| Bug log | `logs/bug_log.md` | Known issues and blockers |

### 9.3 Diagnostic Commands

```bash
# Check pipeline health
python scripts/preflight.py

# Run single-vector test
python scripts/flight_test.py --vector-id "WEB_test_001"

# View cost breakdown
python -c "
import json
with open('logs/pg_cost_ledger.jsonl') as f:
    total = sum(json.loads(line).get('cost_usd', 0) for line in f)
print(f'Total cost: \${total:.2f}')
"

# Check GPU availability
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
```

---

## 10. Health Check Verification

### 10.1 Endpoint

```
GET /health
```

### 10.2 Expected Response

```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime": 3600,
  "components": {
    "llm": "connected",
    "search": "connected",
    "nli": "loaded",
    "chromadb": "connected",
    "checkpoint": "enabled"
  }
}
```

### 10.3 Verification Script

```bash
#!/bin/bash
# health_check.sh

POLARIS_URL="${POLARIS_URL:-http://localhost:8000}"

echo "Checking POLARIS health at ${POLARIS_URL}..."

# Basic health
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${POLARIS_URL}/health")
if [ "$HTTP_CODE" = "200" ]; then
    echo "[PASS] Health endpoint: HTTP 200"
else
    echo "[FAIL] Health endpoint: HTTP ${HTTP_CODE}"
    exit 1
fi

# Full response
curl -s "${POLARIS_URL}/health" | python -m json.tool

# SSE connectivity
echo "Testing SSE stream..."
timeout 5 curl -s -N "${POLARIS_URL}/api/events" | head -3
if [ $? -eq 0 ]; then
    echo "[PASS] SSE endpoint responsive"
else
    echo "[WARN] SSE endpoint timeout (may be normal if no events)"
fi

echo "Health check complete."
```

### 10.4 Preflight Validation

Run the built-in preflight script to validate the entire environment:

```bash
python scripts/preflight.py
```

This checks:
- All required environment variables are set
- API keys are valid (test calls)
- GPU availability and VRAM
- NLI model loaded
- ChromaDB accessible
- Output directories writable
- No forbidden code patterns (The Sheriff)

---

## 11. Upgrading Between Versions

### 11.1 Pre-Upgrade Checklist

1. **Backup state files**:
   ```bash
   cp -r state/ state_backup_$(date +%Y%m%d)/
   cp -r outputs/ outputs_backup_$(date +%Y%m%d)/
   ```

2. **Review changelog** for breaking changes in environment variables.

3. **Check database migrations**: ChromaDB schema changes may require collection recreation.

### 11.2 Upgrade Procedure

```bash
# 1. Stop the running server
kill $(pgrep -f "uvicorn.*live_server")

# 2. Pull latest code
git pull origin main

# 3. Update dependencies
pip install -r requirements.txt

# 4. Review .env changes
diff .env .env.example  # Check for new required variables

# 5. Run preflight
python scripts/preflight.py

# 6. Restart server
python -m uvicorn src.polaris_graph.live_server:app --host 0.0.0.0 --port 8000
```

### 11.3 Kubernetes Upgrade

```bash
# Update image tag
helm upgrade polaris ./polaris-helm \
  --namespace polaris \
  --set image.tag="1.1.0" \
  --reuse-values

# Monitor rollout
kubectl rollout status deployment/polaris -n polaris
```

### 11.4 Rollback

```bash
# Helm rollback
helm rollback polaris 1 --namespace polaris

# Manual rollback
git checkout v1.0.0
pip install -r requirements.txt
# Restore state backup
cp -r state_backup_20260227/* state/
```

### 11.5 Version Compatibility Matrix

| POLARIS Version | Python | LangGraph | ChromaDB | vLLM (Sovereign) |
|----------------|--------|-----------|----------|-------------------|
| 1.0.x | 3.11+ | 0.2.x | 0.4.x | 0.4.x |
| 1.1.x | 3.11+ | 0.3.x | 0.5.x | 0.5.x |

---

## Appendix A: Environment Variable Quick Reference

For a complete `.env` template, copy `.env.example` and fill in your API keys. The minimum viable configuration for cloud mode requires:

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key
SERPER_API_KEY=your-serper-key
PG_NLI_ENABLED=1
PG_STORM_ENABLED=1
PG_CHECKPOINT_ENABLED=1
```

All other variables have sensible defaults that are production-tested through 50+ pipeline runs.
