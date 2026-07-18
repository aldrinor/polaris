# Third-Party Notices & Provenance

This document records the external components **of consequence**, their provenance and license, and
the boundary between **our own code** and **externally-authored code**. It is written so a reviewer can
*verify* each claim with the commands given, rather than take it on trust. A complete machine-generated
dependency inventory (SBOM) with per-package licenses is a scheduled deliverable (code-review-readiness
plan, **S6**); this document is not that inventory.

## 1. The runtime (`src/polaris_graph`) — clean-room, verifiable

To the project owner's knowledge, the production pipeline in `src/polaris_graph` is originally
authored. Two components take *algorithmic inspiration* from published research and are
reimplementations from the papers (citations in docstrings), **not code copies**:

- **STORM** (perspective-driven interview/outline) — inspired by Shao et al., *"Assisting in Writing
  Wikipedia-like Articles From Scratch with Large Language Models"* (Stanford, 2024).
- **FS-Researcher** (adaptive query generation) — inspired by the corresponding paper.

**Verify (no copied upstream code):**
```
grep -rIl -e "SPDX-License-Identifier" -e "Copyright (c)" src/polaris_graph   # expect: no upstream headers
grep -rl "third_party" src/polaris_graph                                       # expect: no runtime imports of third_party
```
The strings "STORM"/"FS-Researcher" appear as *conceptual* references; renaming those internal
identifiers is tracked separately and does not change provenance.

## 2. `third_party/` — external benchmarks (fetched, NOT vendored)

Used only for **scoring/evaluation**; **not imported by the runtime**; **not redistributed** by this
repository. Verify: `git ls-files third_party` (only `DeepResearch-Bench-II/uv.lock` is tracked;
`third_party/deep_research_bench/` is git-ignored — see `.gitignore`).

### 2.1 DeepResearch-Bench (the RACE scorer)
- **Path:** `third_party/deep_research_bench/` — **git-ignored; fetched locally, not committed.**
- **Upstream:** https://github.com/Ayanami0730/deep_research_bench · **Paper:** arXiv:2506.11763.
- **What we use:** `deepresearch_bench_race.py` (the RACE metric), as an external tool.
- **License:** the upstream **`LICENSE` file is Apache-2.0**, while the upstream **README badge
  advertises "MIT"** — an inconsistency *in the upstream project*, which we note but do not resolve on
  their behalf. We use the component under its shipped `LICENSE` (Apache-2.0) and preserve its
  `LICENSE`/`README`/attribution in the fetched copy.
- **Exact fetched revision:** **not yet pinned** in this repo. The retrieval date and commit SHA should
  be recorded when the fetch is made reproducible; pinning it is a follow-up under **S6**.

### 2.2 DeepResearch-Bench-II
- **Path:** `third_party/DeepResearch-Bench-II/` — **only `uv.lock` is present/tracked; no source, no
  README, no LICENSE is vendored here.** Its upstream identity and license are **to be confirmed**
  before it is relied upon or redistributed (follow-up, S6). Nothing under this path is imported by the
  runtime.

## 3. Python dependencies

Pinned in `requirements.lock` / `requirements.txt`. A full per-package license inventory (SBOM) is
scheduled (**S6**) and is not asserted here.

## 4. This project

Deep Cove Research — the code under `src/` and `scripts/` is the property of the project owner. A
project `LICENSE` will be added before any external distribution.
