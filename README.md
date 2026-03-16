# POLARIS Research Pipeline

A high-integrity, multi-phase research pipeline for evidence-based analysis with citation verification and adversarial quality assurance.

## Overview

POLARIS implements a 13-phase pipeline (P0-P12) for automated research:

| Phase | Name | Function |
|-------|------|----------|
| P0 | Initialization | Vector registration, novelty check |
| P1 | Contextualization | Strategic research planning (HPRP) |
| P2 | Query Generation | Multi-modal search query creation |
| P3 | Search Execution | Federated search across 4 engines |
| P4 | Relevance Filtering | Two-stage IsREL with cross-encoder |
| P5 | VWM Indexing | Vector embedding + ChromaDB storage |
| P6 | NLI Integrity | DeBERTa contradiction detection |
| P7 | Dual RAG | Dense + Sparse retrieval fusion |
| P8 | Adversarial QA | Skeptical question generation |
| P9 | Gating Logic | CASE_1/2/3/4 decision matrix |
| P10 | Knowledge Integration | LTM promotion, claim archival |
| P11 | Research Packaging | Citation binding, report generation |
| P12 | Narrative Synthesis | Cross-vector pattern extraction |

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd POLARIS

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your API keys:
# - GEMINI_API_KEY
# - SERPER_API_KEY
```

## Quick Start

```bash
# Run preflight checks
python scripts/preflight.py

# Run a single vector through the full pipeline
python scripts/flight_test.py --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA

# Run P6-P12 only (for vectors with existing P0-P5 outputs)
python -m src.runner --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA

# Run postflight audit on outputs
python scripts/postflight_audit.py --dir outputs/P11
```

## Gating Cases

The P9 gating logic produces one of four outcomes:

| Case | Condition | Action |
|------|-----------|--------|
| CASE_1 | Sufficiency >= 0.60, Confidence >= 0.50, Integrity >= 0.55 | Finalize (P10-P12) |
| CASE_2 | Sufficiency >= 0.40, Integrity >= 0.55, iterations < 3 | Re-iterate P7-P9 |
| CASE_3 | Integrity >= 0.55, insufficient evidence | Generate gap report |
| CASE_4 | Integrity < 0.55 | Generate failure report |

## Directory Structure

```
POLARIS/
├── config/
│   ├── settings/
│   │   ├── thresholds.yaml    # Quality thresholds
│   │   ├── models.yaml        # LLM configuration
│   │   └── search_sources.yaml
│   └── vector_library.py      # Vector definitions (175 vectors)
│
├── src/
│   ├── phases/                # P0-P12 implementations
│   ├── schemas/               # Pydantic models
│   ├── memory/                # ChromaDB integration
│   ├── llm/                   # Gemini client
│   ├── search/                # Search engines
│   ├── state/                 # Ledger management
│   ├── utils/                 # Citation registry, cost tracker
│   └── runner.py              # P6-P12 orchestrator
│
├── scripts/
│   ├── preflight.py           # Environment checks
│   ├── flight_test.py         # Full pipeline runner
│   ├── postflight_audit.py    # Output verification
│   ├── debug_p6.py            # NLI contradiction analyzer
│   └── clean_vwm_garbage.py   # VWM data cleanup
│
├── outputs/                   # Phase outputs (P0-P12)
├── state/                     # Progress ledger, cost tracker
└── memory/chroma_db/          # Vector database
```

## Configuration

All thresholds are in `config/settings/thresholds.yaml`:

```yaml
gating:
  case1_sufficiency: 0.60
  case1_confidence: 0.50
  case4_integrity: 0.55

output:
  min_word_count: 500
  min_citations: 5
```

## Cost Tracking

The pipeline tracks LLM costs with a default $5.00 budget:

```bash
# Check current spend
python -c "from src.utils.cost_tracker import get_cost_tracker; ct = get_cost_tracker(); print(f'Spent: {ct.get_total_cost()}, Remaining: {ct.get_remaining_budget()}')"

# Reset cost tracker
python -c "from src.utils.cost_tracker import get_cost_tracker; get_cost_tracker().reset()"
```

## Troubleshooting

### CASE_4 Results

If vectors produce CASE_4 (failure reports):

1. **Run debug script**: `python scripts/debug_p6.py <vector_id>`
2. **Check for garbage data**: Binary/PDF/EXIF metadata in chunks
3. **Clean VWM**: `python scripts/clean_vwm_garbage.py --vector-id <id> --execute`
4. **Re-run pipeline**: `python -m src.runner --vector-id <id>`

### Common Issues

- **P8 returns 0 evidence**: Check ChromaDB collection exists
- **High contradiction count**: Run VWM garbage cleanup
- **Budget exceeded**: Reset cost tracker or increase limit

## Scripts

| Script | Purpose |
|--------|---------|
| `preflight.py` | Environment and dependency checks |
| `flight_test.py` | Full P0-P12 pipeline execution |
| `postflight_audit.py` | Output verification (citation integrity, logic consistency) |
| `debug_p6.py` | Analyze NLI contradictions and garbage data |
| `clean_vwm_garbage.py` | Remove binary/metadata garbage from VWM |

## License

Proprietary. All rights reserved.
