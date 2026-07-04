#!/usr/bin/env python
"""I-wire-016 #1338: element-level chrome/content classifier bake-off.

Picks the render-seam furniture-vs-content classifier by benchmarking candidates on labeled gold:
content = real VERIFIED claim sentences; chrome = the §3.4-missed furniture/metadata/truncation gold.

§-1.3 ACCEPTANCE GATE: a classifier may be WIRED only if its CONTENT precision is >= --content-precision-floor
(default 0.99) — i.e. it almost NEVER labels a real claim as chrome (that would be a faithfulness DROP).
Among classifiers that clear that floor, the winner maximizes CHROME recall (how much furniture it removes).

Candidates (VM, GPU + OpenRouter):
  C1 embed-logreg : Qwen3-Embedding-8B embeddings + LogisticRegression head (stratified 5-fold CV).
  C2 embed-knn    : same embeddings, k-NN (k=5) cosine vote (5-fold CV).
  C3 glm-fewshot  : GLM-5.2 zero/few-shot LLM-as-classifier (conservative prompt: flag only obvious
                    furniture/metadata, KEEP anything that states a finding) — no training, eval on a sample.

Run on the VM after a run frees the GPU:
  PYTHONPATH=/root/polaris /opt/conda/bin/python scripts/iwire016_chrome_classifier_bakeoff.py \
    --content outputs/audits/iwire014/benchmark/clf_content_set.json \
    --chrome  outputs/audits/iwire014/benchmark/chrome_gold.json \
    --out     outputs/audits/iwire016/bakeoff_result.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _load_texts(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("items", raw.get("texts", list(raw.values())))
    out: list[str] = []
    for it in raw:
        if isinstance(it, str):
            t = it
        elif isinstance(it, dict):
            t = it.get("text") or it.get("sentence") or it.get("unit") or ""
        else:
            t = ""
        t = (t or "").strip()
        if len(t.split()) >= 3:
            out.append(t)
    return out


def _metrics(y_true: list[int], y_pred: list[int]) -> dict[str, float]:
    # label 1 = chrome (positive for "furniture removal"); 0 = content.
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    chrome_recall = tp / (tp + fn) if (tp + fn) else 0.0
    chrome_prec = tp / (tp + fp) if (tp + fp) else 0.0
    # CONTENT precision = of the units we KEEP (pred=0/content), how many are truly content.
    content_precision = tn / (tn + fn) if (tn + fn) else 0.0
    return {
        "content_precision": round(content_precision, 4),  # THE §-1.3 gate (keep no chrome? no — keep all real content)
        "chrome_recall": round(chrome_recall, 4),
        "chrome_precision": round(chrome_prec, 4),
        "fn_real_content_flagged_as_chrome": fp,  # the §-1.3 danger count
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
    }


def _embed(texts: list[str]) -> Any:
    import torch  # noqa: PLC0415
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415
    model_id = os.getenv("PG_EMBED_MODEL_ID", "Qwen/Qwen3-Embedding-8B")
    # fp16: the 8B embedder is ~23GB in fp32 and OOMs a 24GB GPU on the final alloc; fp16 ~16GB fits.
    m = SentenceTransformer(
        model_id, device="cuda", model_kwargs={"torch_dtype": torch.float16},
    )
    return m.encode(texts, batch_size=8, show_progress_bar=False, normalize_embeddings=True)


def _run_embed_candidates(content: list[str], chrome: list[str]) -> dict[str, Any]:
    import numpy as np  # noqa: PLC0415
    from sklearn.linear_model import LogisticRegression  # noqa: PLC0415
    from sklearn.model_selection import StratifiedKFold  # noqa: PLC0415
    from sklearn.neighbors import KNeighborsClassifier  # noqa: PLC0415

    texts = content + chrome
    y = [0] * len(content) + [1] * len(chrome)
    X = np.asarray(_embed(texts))
    y_arr = np.asarray(y)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    out: dict[str, Any] = {}
    for name, mk in (
        ("embed-logreg", lambda: LogisticRegression(max_iter=2000, class_weight="balanced")),
        ("embed-knn", lambda: KNeighborsClassifier(n_neighbors=5, metric="cosine")),
    ):
        yt, yp = [], []
        for tr, te in skf.split(X, y_arr):
            clf = mk(); clf.fit(X[tr], y_arr[tr])
            yp.extend(int(v) for v in clf.predict(X[te]))
            yt.extend(int(v) for v in y_arr[te])
        out[name] = _metrics(yt, yp)
    return out


def _run_glm_fewshot(content: list[str], chrome: list[str], sample: int) -> dict[str, Any]:
    import random  # noqa: PLC0415 — eval sampling only; seeded
    rnd = random.Random(0)
    cs = rnd.sample(content, min(sample, len(content)))
    hs = rnd.sample(chrome, min(sample, len(chrome)))
    texts = cs + hs
    y = [0] * len(cs) + [1] * len(hs)
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415
    client = OpenRouterClient(model=os.getenv("PG_JUDGE_MODEL", "z-ai/glm-5.2"))
    sys_prompt = (
        "You screen one text unit from a research report. Label it FURNITURE if it is page chrome / "
        "boilerplate / bibliographic or author metadata / article-access stats / a navigation or license "
        "fragment / a mid-word-truncated fragment — i.e. NOT a substantive research finding. Label it "
        "CONTENT if it states a substantive claim/finding (even briefly). When in doubt, answer CONTENT "
        "(never drop a real finding). Answer with EXACTLY one word: FURNITURE or CONTENT."
    )
    yp = []
    for t in texts:
        try:
            r = client.complete_sync(system=sys_prompt, prompt=t[:1200]) if hasattr(client, "complete_sync") else None
            txt = (r.content if r is not None else "")
        except Exception:
            txt = ""
        yp.append(1 if "FURNITURE" in (txt or "").upper() else 0)
    return {"glm-fewshot": _metrics(y, yp)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True, type=Path)
    ap.add_argument("--chrome", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--content-precision-floor", type=float, default=0.99)
    ap.add_argument("--glm-sample", type=int, default=80)
    ap.add_argument("--skip-glm", action="store_true")
    a = ap.parse_args(argv)

    content = _load_texts(a.content)
    chrome = _load_texts(a.chrome)
    print(f"[bakeoff] content={len(content)} chrome={len(chrome)}")
    results: dict[str, Any] = {}
    results.update(_run_embed_candidates(content, chrome))
    if not a.skip_glm:
        try:
            results.update(_run_glm_fewshot(content, chrome, a.glm_sample))
        except Exception as exc:  # noqa: BLE001
            results["glm-fewshot"] = {"error": str(exc)[:200]}

    floor = a.content_precision_floor
    eligible = {k: v for k, v in results.items() if isinstance(v, dict) and v.get("content_precision", 0) >= floor}
    winner = max(eligible, key=lambda k: eligible[k]["chrome_recall"], default=None)
    summary = {
        "content_precision_floor": floor,
        "results": results,
        "eligible_at_floor": list(eligible),
        "winner": winner,
        "winner_metrics": eligible.get(winner) if winner else None,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\n[bakeoff] WINNER (content_precision>={floor}, max chrome_recall): {winner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
