"""I-ready-018 FIX-GLM (#1145/#1100): the Mirror provider chain must exclude the flaky Parasail
provider while keeping the GLM-5.1 model and the other three role chains unchanged.

drb_72 evidence: GLM-5.1 returned blank verdicts on ~18% of Parasail calls (23/126) but 0/39 on
Io Net — a provider defect, not the model. With allow_fallbacks:false, removing Parasail from the
Mirror `order` and adding it to `ignore` ensures the binding Mirror is never routed through it.
No model swap; the 4-distinct-family lock (deepseek/glm/minimax/qwen) is untouched. NO network.
"""
from __future__ import annotations

from pathlib import Path

import yaml

_CFG = Path(__file__).resolve().parents[2] / "config" / "settings" / "openrouter_provider_routing.yaml"


def _roles() -> dict:
    return yaml.safe_load(_CFG.read_text(encoding="utf-8"))["roles"]


def test_mirror_excludes_parasail_keeps_glm():
    mirror = _roles()["mirror"]
    assert mirror["model"] == "z-ai/glm-5.1", "model must NOT be swapped"
    assert "parasail" not in mirror["order"], "Parasail must be out of the Mirror order"
    assert "parasail" in mirror["ignore"], "Parasail must be in the Mirror ignore list"
    # Io Net (0 blanks in the held run) leads the chain.
    assert mirror["order"][0] == "io-net"
    # The chain is still non-empty with healthy providers.
    assert len(mirror["order"]) >= 3


def test_other_role_chains_unchanged():
    roles = _roles()
    # The other three role models + chains are not touched by FIX-GLM (4-distinct-family lock).
    assert roles["generator"]["model"] == "deepseek/deepseek-v4-pro"
    assert roles["generator"]["order"] == ["streamlake", "siliconflow", "baidu", "novita", "gmicloud", "deepseek"]
    assert roles["sentinel"]["model"] == "minimax/minimax-m2"
    assert roles["sentinel"]["order"] == ["google-vertex", "novita", "atlas-cloud", "minimax"]
    assert roles["judge"]["model"] == "qwen/qwen3.6-35b-a3b"
    assert roles["judge"]["order"] == ["wandb", "io-net", "atlas-cloud"]
