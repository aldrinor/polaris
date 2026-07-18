# Third-Party Notices & Provenance

This document records the external components **of consequence** and their provenance, and the boundary
between our own code and externally-authored code. It states only what is currently substantiated; open
items are marked as scheduled under the code-review-readiness plan (**S6 — reproducible build / SBOM +
third-party audit**). It is not a complete dependency inventory.

## 1. Provenance of the runtime (`src/polaris_graph`)

To the project owner's knowledge, the pipeline in `src/polaris_graph` is originally authored. Two
components take *algorithmic inspiration* from published research and are reimplementations from the
papers (citations in docstrings):

- **STORM** — Shao et al., *"Assisting in Writing Wikipedia-like Articles From Scratch with LLMs"*
  (Stanford, 2024).
- **FS-Researcher** — the corresponding paper.

**Evidence (not proof):** a scan for upstream license headers / SPDX identifiers in `src/polaris_graph`
returns none —
```
grep -rIl -e "SPDX-License-Identifier" -e "Copyright (c)" src/polaris_graph
grep -rl "third_party" src/polaris_graph      # runtime does not import the benchmark trees
```
Absence of headers is evidence against verbatim file-copying; it is **not** a proof of independent
authorship. A formal third-party code-provenance audit is a **scheduled deliverable (S6)**.

## 2. `third_party/` — external benchmarks (fetched, NOT vendored)

Used only for scoring; not imported by the runtime; not redistributed by this repository.
Verify: `git ls-files third_party` → only `DeepResearch-Bench-II/uv.lock` is tracked;
`third_party/deep_research_bench/` is git-ignored (see `.gitignore`).

### 2.1 DeepResearch-Bench (the RACE scorer)
- **Path:** `third_party/deep_research_bench/` — git-ignored; fetched locally as a git clone.
- **Upstream:** `https://github.com/Ayanami0730/deep_research_bench.git`
- **Exact fetched revision:** **`469cce54ea7f6a63c163d3d9fec879cf289ec484`** · **Paper:** arXiv:2506.11763.
- **What we use:** `deepresearch_bench_race.py` (the RACE metric), as an external tool.
- **License:** the upstream **`LICENSE` file is Apache-2.0**; the upstream **README badge advertises
  "MIT"** — an inconsistency *in the upstream project*, noted but not ours to resolve. We use the
  component under its shipped `LICENSE` (Apache-2.0) and preserve its attribution in the fetched copy.

### 2.2 DeepResearch-Bench-II
- **Path:** `third_party/DeepResearch-Bench-II/` — the only tracked content is **`uv.lock`**.
- **Provenance:** the lockfile was **generated locally** — it declares an *editable root project*
  `deepresearch-bench-2` (`source = { editable = "." }`) and pins **9 ordinary PyPI dependencies**
  (certifi, charset-normalizer, idna, lxml, python-docx, …). All dependency `source` entries resolve to
  the PyPI registry; there are **no git/URL sources and no vendored third-party source code** — the
  file is a build artifact, not copied upstream code.
- **Licensing:** the transitive PyPI dependencies' licenses fall under the scheduled dependency SBOM
  (**S6**). The `deepresearch-bench-2` project's own source is **not present** in this repository, and
  nothing here is imported by the runtime.

## 3. Python dependencies

Pinned in `requirements.lock` / `requirements.txt`. A full per-package license inventory (SBOM) is
scheduled (**S6**) and is not asserted here.

## 4. This project

Deep Cove Research — the code under `src/` and `scripts/` is the property of the project owner. A
project `LICENSE` will be added before any external distribution.
