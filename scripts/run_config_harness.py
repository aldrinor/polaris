"""Offline hamster harness for the RunConfig foundation (MASTER_EXECUTION_PLAN §1).

Proves this section's contract WITHOUT the live corpus or any LLM/network: given a research
question + an optional --run-config override file (defaults to the committed fixture), it builds
the fully-resolved RunConfig, prints every knob with its winning layer + provenance span, writes
``cp0_run_config.json`` through the shared checkpoint envelope into a scratch run_dir, reloads +
validates it, and walks the traceability ledger's hash-chain. Fast (sub-second), deterministic.

    python scripts/run_config_harness.py \
        --question "comprehensive review of tirzepatide in type 2 diabetes" \
        --run-config tests/fixtures/run_config/panel_overrides.example.json

The live single-section / full-corpus hamster loops run later on the VM (§4 S0). This harness is
the offline oracle that must be GREEN before that.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph import run_config as rc  # noqa: E402
from src.polaris_graph.generator import checkpoint_envelope as ce  # noqa: E402

_DEFAULT_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "run_config" / "panel_overrides.example.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question", default="comprehensive review of tirzepatide in type 2 diabetes")
    ap.add_argument("--run-config", default=str(_DEFAULT_FIXTURE),
                    help="RunConfig override file (panel/parsed); the control-panel/CLI surface.")
    ap.add_argument("--run-dir", default=None, help="where to write cp0 (default: a temp dir).")
    args = ap.parse_args()

    reg = rc.default_registry()
    overrides = rc.load_overrides_file(args.run_config) if args.run_config else {"panel": {}, "parsed": {}}
    cfg = rc.build_run_config(registry=reg, **overrides)

    print(f"registry_version={reg.version}  knobs={len(reg.ids())}  run_config_sha={cfg.sha()[:16]}")
    print(f"question: {args.question!r}")
    print("\nresolved knobs (block | knob = value  [source]  <span>):")
    for block in sorted(rc.ALLOWED_BLOCKS):
        for knob_id in reg.block_ids(block):
            prov = cfg.provenance[knob_id]
            span = f"  <{prov.span}>" if prov.span else ""
            mark = " *" if prov.source != rc.SOURCE_DEFAULT else "  "
            print(f" {mark}{block:11s} | {knob_id:26s} = {prov.value!r:>10}  [{prov.source}]{span}")

    nd = cfg.non_default_knobs()
    print(f"\nnon-default (Methods disclosure) knobs: {len(nd)} -> {sorted(nd)}")

    # Write cp0 through the shared envelope and validate the round-trip + hash-chain.
    run_dir = Path(args.run_dir) if args.run_dir else Path(tempfile.mkdtemp(prefix="run_config_cp0_"))
    run_dir.mkdir(parents=True, exist_ok=True)
    path, sha = rc.write_cp0(run_dir, cfg, run_id="harness", slug="fixture/demo",
                             domain="clinical", question=args.question)
    env = ce.load_checkpoint(run_dir, ce.STAGE_S0_INTAKE, expected_question_sha=ce.question_sha(args.question),
                             expected_run_config_sha=cfg.sha())
    chain = ce.validate_hash_chain(run_dir)
    assert env["upstream"] is None, "cp0 must be the chain root"
    assert env["payload"]["run_config_sha"] == cfg.sha()

    print(f"\ncp0 written: {path}")
    print(f"  content_sha256={sha[:16]}  chain_root={env['upstream'] is None}  chain_len={len(chain)}")
    print(f"  reload OK: question_sha match + run_config_sha pinned + verdict-guard passed")
    print("\nGREEN: RunConfig foundation contract holds on the fixture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
