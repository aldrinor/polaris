"""I-arch-011 — LIVE behavioral gate: prove provider-rotation FIRES end-to-end on the REAL judge.

Discriminator (no need to wait for a real z-ai blank window): lead the mirror chain with NOVITA, which
the call-shape bake-off proved HTTP-404s on the entailment judge's request shape (json_object). So:
  * rotation OFF -> novita 404 -> retries exhaust on novita -> ('ENTAILED','judge_error: ...') sentinel.
  * rotation ON  -> novita 404 -> ADVANCE to baidu -> a REAL ENTAILED verdict (reason != judge_error).

FAILS LOUD (non-zero exit) if ON does not produce a real verdict — this is the §-1.4 behavioral harness:
the effect must APPEAR in the real output, not just be "in the slate".

Run on a VM:
  cd /root/polaris_v2 && /root/run_env/bin/python -m scripts.diagnostics.entailment_rotation_behavioral
"""
import os
import sys
import tempfile

sys.path.insert(0, "/root/polaris_v2")
try:
    from dotenv import load_dotenv

    load_dotenv("/root/polaris_v2/.env")
except Exception:  # noqa: BLE001
    pass

# Lead the mirror chain with novita (404s on json_object) so a CLEAN run is impossible WITHOUT rotation.
_TMP_YAML = os.path.join(tempfile.gettempdir(), "iarch011_rotate_routing.yaml")
with open(_TMP_YAML, "w", encoding="utf-8") as fh:
    fh.write(
        "roles:\n"
        "  mirror:\n"
        "    model: z-ai/glm-5.1\n"
        "    order: [novita, baidu, gmicloud]\n"
        "    ignore: [atlas-cloud, z-ai, siliconflow, parasail, chutes, phala]\n"
        "provider_aliases:\n"
        '  "Novita": novita\n'
        '  "Baidu": baidu\n'
        '  "GMICloud": gmicloud\n'
    )
os.environ["PG_PROVIDER_ROUTING_CONFIG"] = _TMP_YAML
os.environ["PG_OPENROUTER_PROVIDER_ROUTING"] = "1"

from src.polaris_graph.benchmark import pathB_capture  # noqa: E402
from src.polaris_graph.llm import entailment_judge  # noqa: E402
from src.polaris_graph.roles import provider_routing  # noqa: E402

provider_routing.reset_cache()

SENT = "Deep brain stimulation improved motor function in advanced Parkinson's disease."
SPAN = (
    "In a randomized controlled trial, deep brain stimulation of the subthalamic nucleus significantly "
    "improved motor function as measured by UPDRS-III compared with best medical therapy in patients "
    "with advanced Parkinson disease over 24 months of follow-up."
)


def _run(rotate: bool):
    if rotate:
        os.environ["PG_JUDGE_PROVIDER_ROTATE"] = "1"
    else:
        os.environ.pop("PG_JUDGE_PROVIDER_ROTATE", None)
    # Resolve the mirror provider to the chain LEAD (novita), exactly as a live preflight would.
    token = pathB_capture.set_role_providers({"mirror": "novita"})
    try:
        judge = entailment_judge._EntailmentJudge()
        verdict, reason = judge.judge(SENT, SPAN)
    finally:
        pathB_capture.reset_role_providers(token)
    is_judge_error = isinstance(reason, str) and reason.startswith("judge_error:")
    print(f"  rotate={'ON ' if rotate else 'OFF'} -> verdict={verdict!r} "
          f"judge_error={is_judge_error} reason={reason[:60]!r}", flush=True)
    return verdict, is_judge_error


if __name__ == "__main__":
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        print("FATAL: OPENROUTER_API_KEY not set", flush=True)
        sys.exit(2)
    print("=== entailment provider-rotation LIVE behavioral gate (novita-lead 404 -> baidu) ===", flush=True)
    off_verdict, off_jerr = _run(rotate=False)
    on_verdict, on_jerr = _run(rotate=True)

    # The gate: ON must produce a REAL verdict (not judge_error). The OFF arm is informational — it SHOULD
    # judge_error on the novita-404 lead, but the binding assertion is that rotation RESCUES it.
    ok = (on_verdict == "ENTAILED") and (not on_jerr)
    if ok:
        print("ROTATION_BEHAVIORAL_PASS: rotation advanced off the novita-404 lead to a REAL ENTAILED verdict",
              flush=True)
        sys.exit(0)
    print("ROTATION_BEHAVIORAL_FAIL: rotation did NOT produce a real verdict on the novita-404 lead",
          flush=True)
    sys.exit(1)
