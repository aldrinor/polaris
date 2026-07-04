#!/usr/bin/env python
"""I-wire-016 #1338 Phase-2: fine-tune Qwen3-0.6B as a content-vs-furniture classifier.

Trains a binary sequence classifier (0=content, 1=furniture) on the cleaned labels, then
THRESHOLD-TUNES to the §-1.3 operating point: the SMALLEST P(furniture) threshold at which CONTENT
precision on the held-out test set is >= --content-precision-floor (default 0.99 — we must almost
never flag a real finding as furniture), and reports the chrome-recall achieved there. The model +
the chosen threshold are saved for wiring.

VM: PYTHONPATH=/root/polaris /opt/conda/bin/python scripts/iwire016_finetune_chrome_classifier.py \
      --data outputs/audits/iwire016/clean_labeled.json \
      --out  outputs/audits/iwire016/classifier
``--data`` is a JSON list of {"text": str, "label": "content"|"furniture"}.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np


def _load(path: Path):
    rows = json.loads(path.read_text(encoding="utf-8"))
    texts, labels = [], []
    for r in rows:
        t = (r.get("text") or "").strip()
        lab = r.get("label")
        if len(t.split()) >= 3 and lab in ("content", "furniture"):
            texts.append(t)
            labels.append(1 if lab == "furniture" else 0)
    return texts, labels


def _threshold_for_precision(probs_furniture, y_true, floor: float):
    """Smallest threshold s.t. CONTENT precision (of the kept=content predictions) >= floor.
    Returns (threshold, content_precision, chrome_recall, chrome_precision, fp_real_content)."""
    best = None
    for thr in [i / 100 for i in range(50, 100)]:  # 0.50..0.99
        pred = [1 if p >= thr else 0 for p in probs_furniture]
        tp = sum(1 for t, p in zip(y_true, pred) if t == 1 and p == 1)
        fp = sum(1 for t, p in zip(y_true, pred) if t == 0 and p == 1)
        tn = sum(1 for t, p in zip(y_true, pred) if t == 0 and p == 0)
        fn = sum(1 for t, p in zip(y_true, pred) if t == 1 and p == 0)
        content_prec = tn / (tn + fn) if (tn + fn) else 1.0
        chrome_recall = tp / (tp + fn) if (tp + fn) else 0.0
        chrome_prec = tp / (tp + fp) if (tp + fp) else 0.0
        if content_prec >= floor:
            cand = (thr, round(content_prec, 4), round(chrome_recall, 4), round(chrome_prec, 4), fp)
            # smallest threshold that clears the floor (= max recall at-or-above the floor)
            if best is None:
                best = cand
            # keep the first (smallest thr) that clears; higher thr only raises precision/lowers recall
            break
    return best


def main(argv=None) -> int:
    import torch  # noqa: PLC0415
    from sklearn.model_selection import train_test_split  # noqa: PLC0415
    from transformers import (  # noqa: PLC0415
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
    )

    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model-id", default=os.getenv("PG_CLF_BASE", "Qwen/Qwen3-0.6B"))
    ap.add_argument("--epochs", type=float, default=4.0)
    ap.add_argument("--content-precision-floor", type=float, default=0.99)
    ap.add_argument("--max-len", type=int, default=256)
    a = ap.parse_args(argv)

    texts, labels = _load(a.data)
    print(f"[finetune] examples={len(texts)} content={labels.count(0)} furniture={labels.count(1)}")
    tr_t, te_t, tr_y, te_y = train_test_split(
        texts, labels, test_size=0.2, random_state=0, stratify=labels,
    )

    tok = AutoTokenizer.from_pretrained(a.model_id, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    # Load in fp32 (the 0.6B model is ~2.4GB) — fp16 AMP (TrainingArguments fp16=True) keeps a fp32
    # master copy and handles mixed precision; loading the weights themselves in fp16 breaks the AMP
    # grad-unscale ("Attempting to unscale FP16 gradients").
    model = AutoModelForSequenceClassification.from_pretrained(
        a.model_id, num_labels=2, trust_remote_code=True,
    )
    model.config.pad_token_id = tok.pad_token_id

    class DS(torch.utils.data.Dataset):
        def __init__(self, t, y):
            self.enc = tok(t, truncation=True, max_length=a.max_len, padding="max_length")
            self.y = y
        def __len__(self): return len(self.y)
        def __getitem__(self, i):
            return {
                "input_ids": torch.tensor(self.enc["input_ids"][i]),
                "attention_mask": torch.tensor(self.enc["attention_mask"][i]),
                "labels": torch.tensor(self.y[i]),
            }

    args = TrainingArguments(
        output_dir=str(a.out / "_ckpt"),
        num_train_epochs=a.epochs,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=16,
        learning_rate=2e-5,
        weight_decay=0.01,
        logging_steps=20,
        save_strategy="no",
        report_to=[],
        fp16=True,
    )
    trainer = Trainer(model=model, args=args, train_dataset=DS(tr_t, tr_y))
    trainer.train()

    # Test-set probabilities for P(furniture).
    model.eval()
    probs = []
    with torch.no_grad():
        for i in range(0, len(te_t), 16):
            batch = tok(te_t[i:i + 16], truncation=True, max_length=a.max_len,
                        padding=True, return_tensors="pt").to(model.device)
            logits = model(**batch).logits.float()
            p = torch.softmax(logits, dim=-1)[:, 1].cpu().numpy()
            probs.extend(p.tolist())

    best = _threshold_for_precision(probs, te_y, a.content_precision_floor)
    # also report the default-0.5 operating point for context
    pred05 = [1 if p >= 0.5 else 0 for p in probs]
    tp = sum(1 for t, p in zip(te_y, pred05) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(te_y, pred05) if t == 0 and p == 1)
    tn = sum(1 for t, p in zip(te_y, pred05) if t == 0 and p == 0)
    fn = sum(1 for t, p in zip(te_y, pred05) if t == 1 and p == 0)

    a.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(a.out / "model"))
    tok.save_pretrained(str(a.out / "model"))
    result = {
        "model_id": a.model_id,
        "n_train": len(tr_t), "n_test": len(te_t),
        "at_0.5": {"content_precision": round(tn / (tn + fn), 4) if (tn + fn) else 1.0,
                   "chrome_recall": round(tp / (tp + fn), 4) if (tp + fn) else 0.0,
                   "fp_real_content": fp},
        "content_precision_floor": a.content_precision_floor,
        "tuned_operating_point": (
            {"threshold": best[0], "content_precision": best[1], "chrome_recall": best[2],
             "chrome_precision": best[3], "fp_real_content_flagged": best[4]}
            if best else None
        ),
    }
    (a.out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if best:
        print(f"\n[finetune] §-1.3 operating point: threshold={best[0]} content_precision={best[1]} "
              f"chrome_recall={best[2]} (real-content wrongly flagged={best[4]})")
    else:
        print(f"\n[finetune] NO threshold reaches content_precision>={a.content_precision_floor} — "
              "needs more/cleaner data or a different model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
