"""Empirical sentinel bake-off for the POLARIS faithfulness gate (#1046).

DECISIVE MEASUREMENT. Each candidate is a pure detector:
    (context = cited_evidence_text, claim = claim_text) -> supported | unsupported
run over the 33 labeled claims in
    outputs/audits/I-run11-003/labeled_groundtruth.json
(28 grounded, 5 GENUINELY-ungrounded = {00-007, 00-026, 03-004, 03-007, 03-012}).

Two pivotal failure-mode probes the winner MUST get right:
  - 00-026 SCOPE-INFLATION: the sub-clause "output growth can offset some of
    the displacement" is genuinely ABSENT from the cited span (the rest is
    verbatim). Detector MUST flag 00-026 unsupported.
  - 03-007 WRONG-ATTRIBUTION: the span attributes the Hulten/0.66% result to
    an unnamed "He"; the claim names "Acemoglu". Detector MUST flag 03-007.
  - 03-000 GROUNDED control: span self-attributes ("We present a framework")
    and the cited source IS Acemoglu&Restrepo, so naming them is CORRECT.
    A good detector MUST NOT drop 03-000 (the false-drop that beat the
    entailment arbiter — see scripts/diagnostics/bakeoff_C3_arbiter.py).

CANDIDATES:
  (1) LettuceDetect lettucedect-large-modernbert-en-v1 (transformer, local).
  (2) FactCG-DeBERTa-Large (sequence-classification NLI, local).
  (3) ENSEMBLE = fail-closed union of (1) OR (2).
  (4) Vectara HHEM-2.1-Open (local cross-encoder, score<0.5 => unsupported).
  (5) GRANITE BASELINE (OpenRouter) — over-flag rate to beat.
  (6) GLM-5.1 OPEN-LLM-DECOMPOSITION (OpenRouter) — atomic sub-assertion
      decomposition + per-atom span check. Designed to catch BOTH 00-026
      inflation AND 03-007 attribution while keeping 03-000. ALWAYS run.

ROBUSTNESS: a candidate that fails to install/load records
{candidate, status:"install_failed", error} and the others CONTINUE.

§8.4: after loading each torch model, del + gc.collect(); torch candidates run
one at a time; the process exits cleanly at the end.

LAW VI: OPENROUTER_API_KEY from .env. No hard-coded secrets.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LABELED = REPO / "outputs" / "audits" / "I-run11-003" / "labeled_groundtruth.json"
OUT_DIR = REPO / "outputs" / "audits" / "I-run11-004"
OUT_MD = OUT_DIR / "sentinel_bakeoff.md"
OUT_JSON = OUT_DIR / "sentinel_bakeoff_result.json"
CACHE_DIR = OUT_DIR / "cache"

# The 5 GENUINE-ungrounded claim-id prefixes (ground-truth invariant).
UNGROUNDED_PREFIXES = {"00-007", "00-026", "03-004", "03-007", "03-012"}
SCOPE_INFLATION_PREFIX = "00-026"
ATTRIBUTION_PREFIX = "03-007"
GROUNDED_CONTROL_PREFIX = "03-000"

# Stability: re-run these (the 5 ungrounded + the 03-000 control) N times.
STABILITY_PREFIXES = UNGROUNDED_PREFIXES | {GROUNDED_CONTROL_PREFIX}
N_STABILITY = int(os.environ.get("BAKEOFF_N_STABILITY", "2"))

ENDPOINT = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/") + "/chat/completions"

GLM_MODEL = os.environ.get("BAKEOFF_GLM_MODEL", "z-ai/glm-5.1")
# NOTE (verified 2026-06-03 against OpenRouter /models): the task-named
# `ibm-granite/granite-guardian-4.1-8b` is NOT served on OpenRouter; the only
# IBM Granite slug available is `ibm-granite/granite-4.1-8b` (a general
# instruct model, not the Guardian classifier). We run it as the Granite
# baseline with a faithfulness-classification prompt and record the
# substitution honestly. This is the closest commercial-clean Granite proxy
# reachable without standing up a local Guardian classifier.
GRANITE_MODEL = os.environ.get("BAKEOFF_GRANITE_MODEL", "ibm-granite/granite-4.1-8b")


# --------------------------------------------------------------------------- #
# Shared: OpenRouter key + chat call
# --------------------------------------------------------------------------- #
def _load_env_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("OPENROUTER_API_KEY not found in env or .env (LAW VI)")


def openrouter_chat(model: str, prompt: str, *, json_mode: bool = True,
                    max_tokens: int = 2000, temperature: float = 0.0) -> str:
    """One live OpenRouter chat call. FAILS LOUD after retries.

    Fail-loud (not fail-open): a transient error must never be silently scored
    as supported/unsupported — that would manufacture a false-accept or a
    false-drop and corrupt the bake-off.
    """
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                ENDPOINT, data=data,
                headers={
                    "Authorization": f"Bearer {_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = json.load(resp)
            choice = (payload.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content")
            finish = choice.get("finish_reason")
            if not content:
                raise ValueError(f"empty content (finish_reason={finish!r})")
            return content
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError,
                KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
            last_err = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"OpenRouter call failed after retries ({model}): {last_err}")


_API_KEY = ""  # set in main()


# --------------------------------------------------------------------------- #
# Disk cache (temp-0 deterministic; survives resume; keyed per candidate)
# --------------------------------------------------------------------------- #
def _cache_path(candidate: str) -> Path:
    return CACHE_DIR / f"{candidate}.jsonl"


def load_cache(candidate: str) -> dict:
    p = _cache_path(candidate)
    out: dict = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out[d["key"]] = d["value"]
    return out


def cache_put(candidate: str, key: str, value: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_cache_path(candidate), "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "value": value}) + "\n")


def _strip_json(text: str) -> dict:
    """Robust JSON extraction from a frontier-LLM response.

    Frontier models wrap JSON in markdown fences, prepend reasoning text, or emit
    trailing commas. A brittle parser CRASHES the whole bake-off on one such reply
    (Kimi K2.6 JSONDecodeError, 2026-06-03). This handles: fenced ```json blocks,
    reasoning prefixes/suffixes (largest {...} span), and trailing commas.
    """
    if not isinstance(text, str):
        raise ValueError(f"non-string response: {type(text).__name__}")
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        block = s[start:end + 1]
        for attempt in (block, re.sub(r",(\s*[}\]])", r"\1", block)):
            try:
                return json.loads(attempt)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no parseable JSON object in response: {text[:200]!r}")


# --------------------------------------------------------------------------- #
# Candidate 6: GLM-5.1 atomic-decomposition detector (ALWAYS run)
# --------------------------------------------------------------------------- #
# The decomposition prompt is the heart of the bake-off. It must:
#  - atomize the claim into EACH factual assertion, separating (a) mechanisms,
#    (b) named-entity ATTRIBUTIONS, (c) causal/offset RELATIONS;
#  - check EACH atom against the cited span ONLY (nothing else);
#  - flag the claim unsupported if ANY atom is not covered (fail-closed union).
# The attribution rule is grammatical-voice based (advisor-confirmed
# discriminator that separates 03-007 from 03-000 WITHOUT injecting any
# author/evidence-id metadata, preserving the fixed context=span protocol):
#   * A first-person self-attribution in the span ("We present a framework")
#     SUPPORTS a claim atom that names the cited source's authors.
#   * A third-person pronoun with no proper-noun antecedent in the span
#     ("He applies Hulten's Theorem") does NOT support a claim atom that names
#     a specific person — that named identity is not in the span.
GLM_PROMPT = """You are a strict faithfulness checker for a clinical-grade research pipeline. You are given a SPAN of source text and a CLAIM that cites ONLY that span. Your job: decide whether EVERY factual assertion in the CLAIM is supported by the SPAN alone.

STEP 1 — Decompose the CLAIM into atomic sub-assertions. Separate them into:
  - mechanism/fact atoms (what happens, numbers, findings),
  - attribution atoms (WHO said / did / authored / found something — any named person, group, or framework),
  - relation atoms (causal or "offsets / counterbalances / compensates" links between two things).
List every atom; do not merge two assertions into one.

STEP 2 — Check EACH atom against the SPAN ONLY. An atom is:
  - "supported" if the SPAN states it (conservative paraphrase allowed), OR
  - "unsupported" if the SPAN does not state it.

Rules that decide hard cases:
  - SCOPE / OFFSET: if the CLAIM says one thing "offsets / counterbalances / compensates for / cancels" another, the SPAN must actually state that offsetting relation. The SPAN merely listing both things separately (e.g. "raises output" AND "displaces labor") does NOT support an "offset" relation atom — that atom is unsupported.
  - ATTRIBUTION by grammatical voice:
      * If the SPAN attributes a result with FIRST PERSON ("We present...", "We show...", "Our framework..."), then a CLAIM atom that names the cited source's own authors as the source IS supported (the source is speaking about itself).
      * If the SPAN attributes a result with a THIRD-PERSON pronoun that has NO proper-noun antecedent inside the SPAN ("He applies...", "She finds...", "They argue..."), then a CLAIM atom that names a SPECIFIC PERSON as the source is UNSUPPORTED — that named identity is not present in the SPAN.
      * If the SPAN names the person explicitly, an attribution atom naming that same person is supported.
  - SPECIFICITY: if the CLAIM names a specific entity/number/mechanism the SPAN does not contain, that atom is unsupported.

STEP 3 — Verdict: "unsupported" if ANY atom is unsupported; otherwise "supported".

Return STRICT JSON only, no prose outside it:
{{"atoms": [{{"atom": "<text>", "type": "mechanism|attribution|relation", "status": "supported|unsupported", "why": "<short>"}}], "unsupported_atoms": <int>, "verdict": "supported" | "unsupported"}}

SPAN:
{span}

CLAIM:
{claim}

JSON:"""


def run_glm_decomposition(claims: list[dict]) -> dict:
    cand = "glm_decomposition"
    cache = load_cache(cand)
    results = {}
    latencies = []
    for c in claims:
        cid = c["claim_id"]
        prefix = cid[:6]
        npass = N_STABILITY if prefix in STABILITY_PREFIXES else 1
        passes = []
        details = []
        for i in range(npass):
            key = f"{GLM_MODEL}|{cid}|{i}"
            if key in cache:
                rec = cache[key]
            else:
                rec = None
                last_exc = None
                dt = 0.0
                for _try in range(3):
                    t0 = time.time()
                    content = openrouter_chat(
                        GLM_MODEL,
                        GLM_PROMPT.format(span=c["cited_evidence_text"], claim=c["claim_text"]),
                        json_mode=True, max_tokens=3000,
                    )
                    dt = time.time() - t0
                    try:
                        parsed = _strip_json(content)
                        verdict = str(parsed.get("verdict", "")).lower().strip()
                        if verdict not in ("supported", "unsupported"):
                            raise ValueError(f"bad verdict {verdict!r}")
                        rec = {
                            "verdict": verdict,
                            "unsupported_atoms": parsed.get("unsupported_atoms"),
                            "atoms": parsed.get("atoms", []),
                            "latency_s": dt,
                        }
                        break
                    except ValueError as exc:
                        last_exc = exc
                        continue
                if rec is None:
                    # Frontier model returned unparseable JSON 3x. FAIL CLOSED (clinical-safe:
                    # an unverifiable claim is held, not released) and FLAG the parse failure so
                    # the model's unreliability is recorded honestly in the bake-off, not silent.
                    rec = {
                        "verdict": "unsupported", "unsupported_atoms": None,
                        "atoms": [], "latency_s": dt, "parse_error": str(last_exc)[:160],
                    }
                    print(f"  [WARN] {GLM_MODEL} unparseable JSON x3 for {cid} -> fail-closed",
                          flush=True)
                cache_put(cand, key, rec)
                cache[key] = rec
            passes.append(rec["verdict"])
            details.append(rec)
            if rec.get("latency_s"):
                latencies.append(rec["latency_s"])
            print(f"  [glm {i+1}/{npass}] {cid}: {rec['verdict']} "
                  f"(unsupported_atoms={rec.get('unsupported_atoms')})", flush=True)
        # fail-closed across stability passes: any 'unsupported' => unsupported
        final = "unsupported" if any(p == "unsupported" for p in passes) else "supported"
        results[cid] = {
            "verdict": final, "passes": passes,
            "stable": len(set(passes)) == 1,
            "detail": details[0],
        }
    return {
        "status": "ok",
        "results": results,
        "mean_latency_s": (sum(latencies) / len(latencies)) if latencies else None,
        "model": GLM_MODEL,
    }


# --------------------------------------------------------------------------- #
# Candidate 5: Granite baseline (OpenRouter) — over-flag rate to beat
# --------------------------------------------------------------------------- #
GRANITE_PROMPT = """You are a faithfulness classifier. You are given a SPAN of source text and a CLAIM that cites only that span. Decide whether the SPAN fully supports the CLAIM (every assertion in the CLAIM is stated by the SPAN; conservative paraphrase is allowed). If the CLAIM adds any fact, entity, attribution, number, or relation not present in the SPAN, it is unsupported.

Return STRICT JSON only:
{{"verdict": "supported" | "unsupported"}}

SPAN:
{span}

CLAIM:
{claim}

JSON:"""


def run_granite(claims: list[dict]) -> dict:
    cand = "granite_baseline"
    cache = load_cache(cand)
    results = {}
    latencies = []
    try:
        for c in claims:
            cid = c["claim_id"]
            prefix = cid[:6]
            npass = N_STABILITY if prefix in STABILITY_PREFIXES else 1
            passes = []
            for i in range(npass):
                key = f"{GRANITE_MODEL}|{cid}|{i}"
                if key in cache:
                    rec = cache[key]
                else:
                    t0 = time.time()
                    content = openrouter_chat(
                        GRANITE_MODEL,
                        GRANITE_PROMPT.format(span=c["cited_evidence_text"],
                                              claim=c["claim_text"]),
                        json_mode=True, max_tokens=600,
                    )
                    dt = time.time() - t0
                    parsed = _strip_json(content)
                    verdict = str(parsed.get("verdict", "")).lower().strip()
                    if verdict not in ("supported", "unsupported"):
                        raise ValueError(f"bad Granite verdict {verdict!r} for {cid}")
                    rec = {"verdict": verdict, "latency_s": dt}
                    cache_put(cand, key, rec)
                    cache[key] = rec
                passes.append(rec["verdict"])
                if rec.get("latency_s"):
                    latencies.append(rec["latency_s"])
                print(f"  [granite {i+1}/{npass}] {cid}: {rec['verdict']}", flush=True)
            final = "unsupported" if any(p == "unsupported" for p in passes) else "supported"
            results[cid] = {"verdict": final, "passes": passes,
                            "stable": len(set(passes)) == 1}
    except Exception as exc:  # robustness clause
        return {"status": "install_failed", "error": f"{type(exc).__name__}: {exc}",
                "model": GRANITE_MODEL, "results": results}
    return {
        "status": "ok", "results": results,
        "mean_latency_s": (sum(latencies) / len(latencies)) if latencies else None,
        "model": GRANITE_MODEL,
    }


# --------------------------------------------------------------------------- #
# Candidate 1: LettuceDetect (local transformer)
# --------------------------------------------------------------------------- #
def run_lettucedetect(claims: list[dict]) -> dict:
    cand = "lettucedetect"
    try:
        from lettucedetect.models.inference import HallucinationDetector
    except Exception as exc:
        return {"status": "install_failed",
                "error": f"import failed: {type(exc).__name__}: {exc}"}
    try:
        detector = HallucinationDetector(
            method="transformer",
            model_path="KRLabsOrg/lettucedect-large-modernbert-en-v1",
        )
    except Exception as exc:
        return {"status": "install_failed",
                "error": f"model load failed: {type(exc).__name__}: {exc}"}
    results = {}
    latencies = []
    try:
        for c in claims:
            cid = c["claim_id"]
            t0 = time.time()
            spans = detector.predict(
                context=[c["cited_evidence_text"]],
                question="",
                answer=c["claim_text"],
                output_format="spans",
            )
            dt = time.time() - t0
            latencies.append(dt)
            # any predicted hallucination span => unsupported
            flagged = bool(spans)
            verdict = "unsupported" if flagged else "supported"
            results[cid] = {"verdict": verdict, "n_spans": len(spans) if spans else 0}
            print(f"  [lettuce] {cid}: {verdict} (spans={len(spans) if spans else 0})",
                  flush=True)
    except Exception as exc:
        out = {"status": "install_failed",
               "error": f"predict failed: {type(exc).__name__}: {exc}",
               "results": results}
    else:
        out = {"status": "ok", "results": results,
               "mean_latency_s": (sum(latencies) / len(latencies)) if latencies else None}
    # §8.4 cleanup
    try:
        del detector
    except Exception:
        pass
    _torch_cleanup()
    return out


# --------------------------------------------------------------------------- #
# Candidate 2: FactCG-DeBERTa (local NLI sequence-classification)
# --------------------------------------------------------------------------- #
FACTCG_CANDIDATE_IDS = [
    os.environ.get("BAKEOFF_FACTCG_MODEL", "").strip() or None,
    "lytang/FactCG-DeBERTa",
    "derenlei/FactCG",
    "lytang/FactCG-DeBERTa-Large",
]


def run_factcg(claims: list[dict]) -> dict:
    cand = "factcg"
    import_err = None
    try:
        import torch  # noqa: F401
        from transformers import (AutoModelForSequenceClassification,
                                  AutoTokenizer)
    except Exception as exc:
        return {"status": "install_failed",
                "error": f"import failed: {type(exc).__name__}: {exc}"}
    model = tok = None
    loaded_id = None
    for mid in [m for m in FACTCG_CANDIDATE_IDS if m]:
        try:
            tok = AutoTokenizer.from_pretrained(mid)
            model = AutoModelForSequenceClassification.from_pretrained(mid)
            model.eval()
            loaded_id = mid
            break
        except Exception as exc:
            import_err = f"{mid}: {type(exc).__name__}: {exc}"
            model = tok = None
    if model is None:
        return {"status": "install_failed",
                "error": f"no FactCG model id loaded; last error: {import_err}"}
    results = {}
    latencies = []
    try:
        import torch
        # Resolve which label index = entailment/supported from config.
        id2label = {int(k): str(v).lower() for k, v in
                    (model.config.id2label or {}).items()}
        # FactCG: typically label 1 = consistent/entailed/factual.
        ent_idx = None
        for idx, lab in id2label.items():
            if any(t in lab for t in ("entail", "consist", "support", "factual",
                                       "1", "true")):
                ent_idx = idx
        if ent_idx is None:
            ent_idx = max(id2label) if id2label else 1
        for c in claims:
            cid = c["claim_id"]
            t0 = time.time()
            inputs = tok(c["cited_evidence_text"], c["claim_text"],
                         truncation=True, max_length=1024, return_tensors="pt")
            with torch.no_grad():
                logits = model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            pred = int(torch.argmax(probs).item())
            dt = time.time() - t0
            latencies.append(dt)
            entailed = (pred == ent_idx)
            verdict = "supported" if entailed else "unsupported"
            results[cid] = {"verdict": verdict, "pred_label": id2label.get(pred, str(pred)),
                            "ent_prob": float(probs[ent_idx].item())}
            print(f"  [factcg] {cid}: {verdict} "
                  f"(pred={id2label.get(pred, pred)}, ent_p={probs[ent_idx].item():.3f})",
                  flush=True)
    except Exception as exc:
        out = {"status": "install_failed",
               "error": f"inference failed: {type(exc).__name__}: {exc}",
               "model": loaded_id, "results": results}
    else:
        out = {"status": "ok", "results": results, "model": loaded_id,
               "id2label": id2label,
               "mean_latency_s": (sum(latencies) / len(latencies)) if latencies else None}
    try:
        del model, tok
    except Exception:
        pass
    _torch_cleanup()
    return out


# --------------------------------------------------------------------------- #
# Candidate 4: Vectara HHEM-2.1-Open (local cross-encoder)
# --------------------------------------------------------------------------- #
def run_hhem(claims: list[dict]) -> dict:
    cand = "hhem"
    try:
        import torch  # noqa: F401
        from transformers import AutoModelForSequenceClassification
    except Exception as exc:
        return {"status": "install_failed",
                "error": f"import failed: {type(exc).__name__}: {exc}"}
    try:
        model = AutoModelForSequenceClassification.from_pretrained(
            "vectara/hallucination_evaluation_model", trust_remote_code=True)
        model.eval()
    except Exception as exc:
        return {"status": "install_failed",
                "error": f"model load failed: {type(exc).__name__}: {exc}"}
    results = {}
    latencies = []
    try:
        for c in claims:
            cid = c["claim_id"]
            t0 = time.time()
            # HHEM predict expects list of (premise, hypothesis) pairs;
            # score in [0,1], higher = more consistent/factual.
            score = float(model.predict([(c["cited_evidence_text"],
                                          c["claim_text"])])[0])
            dt = time.time() - t0
            latencies.append(dt)
            verdict = "unsupported" if score < 0.5 else "supported"
            results[cid] = {"verdict": verdict, "score": score}
            print(f"  [hhem] {cid}: {verdict} (score={score:.3f})", flush=True)
    except Exception as exc:
        out = {"status": "install_failed",
               "error": f"predict failed: {type(exc).__name__}: {exc}",
               "results": results}
    else:
        out = {"status": "ok", "results": results,
               "mean_latency_s": (sum(latencies) / len(latencies)) if latencies else None}
    try:
        del model
    except Exception:
        pass
    _torch_cleanup()
    return out


def _torch_cleanup() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    gc.collect()


# --------------------------------------------------------------------------- #
# Candidate 3: ENSEMBLE = fail-closed union (Lettuce OR FactCG)
# --------------------------------------------------------------------------- #
def build_ensemble(claims, lettuce, factcg) -> dict:
    if lettuce.get("status") != "ok" and factcg.get("status") != "ok":
        return {"status": "install_failed",
                "error": "both ensemble members failed to load"}
    members = []
    if lettuce.get("status") == "ok":
        members.append(("lettucedetect", lettuce["results"]))
    if factcg.get("status") == "ok":
        members.append(("factcg", factcg["results"]))
    results = {}
    for c in claims:
        cid = c["claim_id"]
        flagged = any(m[1].get(cid, {}).get("verdict") == "unsupported"
                      for m in members)
        results[cid] = {"verdict": "unsupported" if flagged else "supported",
                        "members": [m[0] for m in members]}
    lat = [x.get("mean_latency_s") for x in (lettuce, factcg)
           if x.get("status") == "ok" and x.get("mean_latency_s")]
    return {"status": "ok", "results": results,
            "members": [m[0] for m in members],
            "mean_latency_s": sum(lat) if lat else None,
            "note": "fail-closed union; latency = sum of member latencies"
                    + ("" if len(members) == 2 else f" (only {len(members)} member loaded)")}


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def compute_metrics(claims: list[dict], cand_out: dict) -> dict:
    if cand_out.get("status") != "ok":
        return {"status": cand_out.get("status"), "error": cand_out.get("error")}
    res = cand_out["results"]
    grounded = [c for c in claims if c["ground_truth"] == "grounded"]
    ungrounded = [c for c in claims if c["ground_truth"] == "ungrounded"]

    def verdict_of(cid):
        return res.get(cid, {}).get("verdict", "MISSING")

    def starts(c, pfx):
        return c["claim_id"].startswith(pfx)

    # scope-inflation recall: does it flag 00-026 unsupported?
    si = [c for c in ungrounded if starts(c, SCOPE_INFLATION_PREFIX)]
    scope_inflation_recall = (
        1 if si and verdict_of(si[0]["claim_id"]) == "unsupported" else 0)
    # attribution recall: does it flag 03-007 unsupported?
    at = [c for c in ungrounded if starts(c, ATTRIBUTION_PREFIX)]
    attribution_recall = (
        1 if at and verdict_of(at[0]["claim_id"]) == "unsupported" else 0)
    # false accepts: of 5 ungrounded, how many wrongly pass as supported
    false_accepts = sum(1 for c in ungrounded
                        if verdict_of(c["claim_id"]) == "supported")
    fa_claims = [c["claim_id"] for c in ungrounded
                 if verdict_of(c["claim_id"]) == "supported"]
    # over-flag: of 28 grounded, how many wrongly flagged unsupported
    over_flag = sum(1 for c in grounded
                    if verdict_of(c["claim_id"]) == "unsupported")
    over_flag_rate = over_flag / len(grounded)
    # drops 03-000?
    ctrl = [c for c in grounded if starts(c, GROUNDED_CONTROL_PREFIX)]
    drops_03_000 = bool(ctrl and verdict_of(ctrl[0]["claim_id"]) == "unsupported")
    # overall recall: grounded correctly supported / 28
    overall_recall = sum(1 for c in grounded
                         if verdict_of(c["claim_id"]) == "supported") / len(grounded)

    return {
        "status": "ok",
        "scope_inflation_recall": scope_inflation_recall,
        "attribution_recall": attribution_recall,
        "false_accepts": false_accepts,
        "false_accept_claims": fa_claims,
        "over_flag_count": over_flag,
        "over_flag_rate": round(over_flag_rate, 4),
        "drops_03_000": drops_03_000,
        "overall_recall": round(overall_recall, 4),
        "overall_recall_count": sum(1 for c in grounded
                                    if verdict_of(c["claim_id"]) == "supported"),
        "latency_per_claim_s": (round(cand_out["mean_latency_s"], 3)
                                if cand_out.get("mean_latency_s") else None),
    }


def rank_candidates(metrics_by_cand: dict) -> list[str]:
    """Rank: false_accepts=0 first, then lowest over_flag_rate, then highest
    overall_recall, then lowest latency. Only OK candidates are rankable."""
    ok = [(name, m) for name, m in metrics_by_cand.items() if m.get("status") == "ok"]

    def key(item):
        name, m = item
        lat = m.get("latency_per_claim_s")
        lat = lat if lat is not None else 1e9
        return (
            m["false_accepts"],            # 0 first
            m["over_flag_rate"],           # lower better
            -m["overall_recall"],          # higher better
            lat,                           # lower better
        )

    return [name for name, _ in sorted(ok, key=key)]


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
CANDIDATE_LABELS = {
    "lettucedetect": "(1) LettuceDetect lettucedect-large-modernbert-en-v1",
    "factcg": "(2) FactCG-DeBERTa-Large",
    "ensemble": "(3) ENSEMBLE (fail-closed union Lettuce OR FactCG)",
    "hhem": "(4) Vectara HHEM-2.1-Open",
    "granite_baseline": "(5) Granite baseline (OpenRouter)",
    "glm_decomposition": "(6) GLM-5.1 open-LLM decomposition (OpenRouter)",
}


def write_report(claims, raw_by_cand, metrics_by_cand, ranking, granite_ofr):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    L = []
    L.append("# Sentinel bake-off — faithfulness gate (#1046) — MEASURED")
    L.append("")
    L.append("- Data root `C:/POLARIS`; labeled set "
             "`outputs/audits/I-run11-003/labeled_groundtruth.json` "
             "(33 claims: 28 grounded, 5 ungrounded).")
    L.append("- 5 GENUINE-ungrounded = {00-007, 00-026, 03-004, 03-007, 03-012}.")
    L.append("- Each candidate is a pure detector: "
             "(context=cited_evidence_text, claim=claim_text) -> supported|unsupported.")
    L.append("- Pivotal probes: 00-026 SCOPE-INFLATION (must flag), "
             "03-007 WRONG-ATTRIBUTION (must flag), 03-000 GROUNDED control "
             "(must NOT drop).")
    L.append(f"- Stability: {N_STABILITY} passes on the 5 ungrounded + 03-000 "
             "(OpenRouter candidates); any 'unsupported' across passes => unsupported.")
    L.append("")
    L.append("## Summary per candidate")
    L.append("")
    L.append("| candidate | scope_inflation_recall | attribution_recall | "
             "false_accepts | over_flag_rate | overall_recall | drops_03_000 | "
             "latency/claim (s) | status |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for name in CANDIDATE_LABELS:
        m = metrics_by_cand.get(name, {})
        st = m.get("status", "missing")
        if st != "ok":
            L.append(f"| {CANDIDATE_LABELS[name]} | - | - | - | - | - | - | - | "
                     f"**{st}** |")
            continue
        L.append(
            f"| {CANDIDATE_LABELS[name]} | "
            f"{m['scope_inflation_recall']}/1 | {m['attribution_recall']}/1 | "
            f"**{m['false_accepts']}** | {m['over_flag_rate']:.3f} "
            f"({m['over_flag_count']}/28) | "
            f"{m['overall_recall']:.3f} ({m['overall_recall_count']}/28) | "
            f"{m['drops_03_000']} | "
            f"{m['latency_per_claim_s'] if m['latency_per_claim_s'] is not None else '-'} | "
            f"ok |")
    L.append("")
    L.append("Ranking rule: false_accepts=0 first, then lowest over_flag_rate, "
             "then highest overall_recall, then lowest latency.")
    L.append("")
    L.append(f"**Ranking (best first):** {', '.join(ranking) if ranking else 'none ok'}")
    L.append("")
    for name in metrics_by_cand:
        m = metrics_by_cand[name]
        if m.get("status") != "ok":
            err = (raw_by_cand.get(name, {}) or {}).get("error", "")
            L.append(f"- `{name}`: status **{m.get('status')}** — {err}")
    L.append("")
    # per-claim table
    L.append("## Full per-claim table")
    L.append("")
    header = "| claim_id | GT |"
    sep = "|---|---|"
    ok_cands = [n for n in CANDIDATE_LABELS if metrics_by_cand.get(n, {}).get("status") == "ok"]
    for n in ok_cands:
        header += f" {n} |"
        sep += "---|"
    L.append(header)
    L.append(sep)
    for c in claims:
        cid = c["claim_id"]
        gt = "GR" if c["ground_truth"] == "grounded" else "**UN**"
        row = f"| {cid} | {gt} |"
        for n in ok_cands:
            v = raw_by_cand[n]["results"].get(cid, {}).get("verdict", "?")
            cell = "sup" if v == "supported" else ("UNS" if v == "unsupported" else v)
            # mark errors
            is_ung = c["ground_truth"] == "ungrounded"
            if is_ung and v == "supported":
                cell = "**FA**"          # false-accept
            elif not is_ung and v == "unsupported":
                cell = "_of_"            # over-flag
            row += f" {cell} |"
        L.append(row)
    L.append("")
    L.append("Legend: sup=supported (passes), UNS=unsupported (flagged), "
             "**FA**=FALSE-ACCEPT (ungrounded wrongly passed — clinically lethal), "
             "_of_=over-flag (grounded wrongly dropped).")
    L.append("")
    # GLM atom detail for the pivotal claims
    glm = raw_by_cand.get("glm_decomposition", {})
    if glm.get("status") == "ok":
        L.append("## GLM-5.1 decomposition — atoms for the pivotal claims")
        L.append("")
        focus = sorted(UNGROUNDED_PREFIXES | {GROUNDED_CONTROL_PREFIX})
        for c in claims:
            if not any(c["claim_id"].startswith(p) for p in focus):
                continue
            r = glm["results"].get(c["claim_id"], {})
            det = r.get("detail", {})
            L.append(f"### {c['claim_id']} (GT={c['ground_truth']}) -> "
                     f"**{r.get('verdict')}** (passes={r.get('passes')}, "
                     f"stable={r.get('stable')})")
            for a in det.get("atoms", []):
                mark = "OK" if a.get("status") == "supported" else "**MISS**"
                L.append(f"- [{a.get('type')}] {mark} {a.get('atom')} "
                         f"— _{a.get('why', '')}_")
            L.append("")
    L.append("## Granite over-flag rate (the metric Granite is expected to FAIL)")
    L.append("")
    if granite_ofr is not None:
        L.append(f"- Granite baseline over_flag_rate = **{granite_ofr:.3f}** "
                 f"(of 28 grounded). LOWER is better; this is the bar a precise "
                 f"detector must beat.")
    else:
        L.append("- Granite baseline did not produce metrics (see status above).")
    L.append("")
    L.append("## Honest caveats")
    L.append("")
    L.append("- **Granite slug substitution:** the task named "
             "`ibm-granite/granite-guardian-4.1-8b`, which is NOT served on "
             "OpenRouter (verified against /models 2026-06-03). The Granite "
             "Guardian classifier is HF-only. We ran the closest available "
             "commercial-clean Granite slug `ibm-granite/granite-4.1-8b` "
             "(general instruct, not the Guardian classifier) with a "
             "faithfulness-classification prompt. Its over-flag number is a "
             "proxy for the Granite family, not the exact Guardian model.")
    L.append("- **Disputed labels:** 00-026 is disputed "
             "(claude_audit=SPURIOUS vs codex_audit=GENUINE) and 03-007 is "
             "Codex-only (claude_audit=None). The bake-off treats the recorded "
             "ground_truth as authoritative, but a false-accept that lands only "
             "on a disputed label is weaker evidence than one on an undisputed "
             "label. Flagged in the recommendation where relevant.")
    L.append("- **Fixed protocol:** every candidate sees ONLY "
             "(context=span, claim=claim_text). No author/evidence-id metadata "
             "is injected to rescue 03-000 — the grammatical-voice rule in the "
             "GLM prompt is the only in-span discriminator used.")
    L.append("")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    global _API_KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma list of candidates to run")
    ap.add_argument("--skip-torch", action="store_true",
                    help="skip local torch candidates (lettuce/factcg/hhem)")
    args = ap.parse_args()

    _API_KEY = _load_env_key()
    claims = json.loads(LABELED.read_text(encoding="utf-8"))
    only = {x.strip() for x in args.only.split(",") if x.strip()}

    def want(name):
        return (not only) or (name in only)

    raw_by_cand = {}

    # --- OpenRouter candidates FIRST (carry the core result, no local deps) ---
    if want("glm_decomposition"):
        print("\n=== Candidate 6: GLM-5.1 decomposition (ALWAYS) ===", flush=True)
        raw_by_cand["glm_decomposition"] = run_glm_decomposition(claims)
    if want("granite_baseline"):
        print("\n=== Candidate 5: Granite baseline ===", flush=True)
        raw_by_cand["granite_baseline"] = run_granite(claims)

    # --- local torch candidates (fail-soft, one at a time) ---
    lettuce = factcg = {"status": "skipped"}
    if not args.skip_torch:
        if want("lettucedetect"):
            print("\n=== Candidate 1: LettuceDetect ===", flush=True)
            lettuce = run_lettucedetect(claims)
            raw_by_cand["lettucedetect"] = lettuce
        if want("factcg"):
            print("\n=== Candidate 2: FactCG-DeBERTa ===", flush=True)
            factcg = run_factcg(claims)
            raw_by_cand["factcg"] = factcg
        if want("hhem"):
            print("\n=== Candidate 4: Vectara HHEM-2.1-Open ===", flush=True)
            raw_by_cand["hhem"] = run_hhem(claims)
    else:
        for n in ("lettucedetect", "factcg", "hhem"):
            raw_by_cand[n] = {"status": "install_failed",
                              "error": "skipped via --skip-torch"}
        lettuce = raw_by_cand["lettucedetect"]
        factcg = raw_by_cand["factcg"]

    # --- ensemble (derived) ---
    if want("ensemble"):
        print("\n=== Candidate 3: ENSEMBLE ===", flush=True)
        raw_by_cand["ensemble"] = build_ensemble(claims, lettuce, factcg)

    # --- metrics + ranking ---
    metrics_by_cand = {n: compute_metrics(claims, raw_by_cand[n])
                       for n in raw_by_cand}
    ranking = rank_candidates(metrics_by_cand)
    granite_m = metrics_by_cand.get("granite_baseline", {})
    granite_ofr = granite_m.get("over_flag_rate") if granite_m.get("status") == "ok" else None

    write_report(claims, raw_by_cand, metrics_by_cand, ranking, granite_ofr)

    winner = ranking[0] if ranking else None
    wm = metrics_by_cand.get(winner, {}) if winner else {}
    out = {
        "candidates": [
            {
                "name": n,
                "scope_inflation_recall": m.get("scope_inflation_recall"),
                "attribution_recall": m.get("attribution_recall"),
                "false_accepts": m.get("false_accepts"),
                "over_flag_rate": m.get("over_flag_rate"),
                "overall_recall": m.get("overall_recall"),
                "drops_03_000": m.get("drops_03_000"),
                "latency_per_claim_s": m.get("latency_per_claim_s"),
                "status": m.get("status"),
            }
            for n, m in metrics_by_cand.items()
        ],
        "winner": winner,
        "winner_false_accepts": wm.get("false_accepts"),
        "winner_over_flag_rate": wm.get("over_flag_rate"),
        "granite_over_flag_rate": granite_ofr,
        "ranking": ranking,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    print("\n=== RESULT ===")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
