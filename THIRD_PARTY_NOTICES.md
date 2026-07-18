# Third-Party Notices & Provenance

This document records every external dependency of consequence, its provenance and license, and —
importantly — the boundary between **our own code** and **externally-authored code**. It exists so an
independent reviewer can verify at a glance that the runtime is clean-room and that nothing is
misappropriated.

## 1. The runtime (`src/polaris_graph`) is clean-room

The production pipeline in `src/polaris_graph` is **originally authored**. Two components take
*algorithmic inspiration* from published research and are **reimplementations from the papers, with
citations in the docstrings — not code copies**:

- **STORM** (perspective-driven interview/outline). Inspired by Shao et al., *"Assisting in Writing
  Wikipedia-like Articles From Scratch with Large Language Models"* (Stanford, 2024). Our code shares
  no source with the STORM repository.
- **FS-Researcher** (adaptive query generation). Inspired by the corresponding paper; reimplemented.

Verification a reviewer can run: a grep for copied upstream file headers, license blocks, or SPDX
identifiers across `src/polaris_graph` returns **zero** hits. The names "STORM"/"FS-Researcher" appear
as *conceptual* references, not vendored code. (A branding rename of these internal identifiers is
tracked separately in the code-review-readiness plan; it does not change provenance.)

## 2. `third_party/` — external benchmarks (fetched, NOT vendored)

The `third_party/` trees are **evaluation/benchmark harnesses**, used only for **scoring**. They are:
- **NOT imported by the runtime** (`src/polaris_graph` does not import `third_party`), and
- **NOT redistributed by this repository** — `third_party/deep_research_bench/` is **git-ignored** and
  fetched locally; only `third_party/DeepResearch-Bench-II/uv.lock` is tracked.

### 2.1 DeepResearch-Bench (the RACE scorer)
- **Path:** `third_party/deep_research_bench/` (git-ignored; fetched, not committed).
- **Upstream:** https://github.com/Ayanami0730/deep_research_bench
- **Paper:** DeepResearch-Bench, arXiv:2506.11763.
- **What we use:** `deepresearch_bench_race.py` — the RACE metric scorer, as an external tool.
- **License — upstream inconsistency (noted, not ours to resolve):** the upstream **`LICENSE` file is
  Apache License 2.0**, while the upstream **README badge advertises "MIT."** We use the component under
  the terms of the shipped **`LICENSE` file (Apache-2.0)** and preserve its `LICENSE`, `README`, and
  attribution in the fetched copy. We do not redistribute it.

### 2.2 DeepResearch-Bench-II
- **Path:** `third_party/DeepResearch-Bench-II/` (only `uv.lock` tracked).
- **Nature:** successor benchmark; external, evaluation-only.

## 3. Python dependencies

Runtime and tooling dependencies are pinned in `requirements.lock` / `requirements.txt`. A full
license inventory (SBOM) is a scheduled deliverable (see the code-review-readiness plan, S6).

## 4. This project

Deep Cove Research — the code under `src/` and `scripts/` is the property of the project owner.
A project `LICENSE` will be added before any external distribution.
