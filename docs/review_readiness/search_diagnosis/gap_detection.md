# Gap-detection ("grounded deficiencies") diagnosis — outline agent

File under investigation: `/home/polaris/wt/outline_agent/src/polaris_graph/outline/outline_agent.py`

## Where the logic lives

The "checklist" / gap-ledger detector is `OutlineAgent._run_checklist(...)`, defined at
**outline_agent.py:1354**. It is detector #1 of 3 that all feed one `GapLedger`
(module note, outline_agent.py:23-24, 204-207). It:

1. Asks the LLM to self-review each section vs. the research question and emit deficiency
   lines in a 4-field `::`-separated format, each field REQUIRING a verbatim quote from the
   question (prompt, outline_agent.py:1396-1454).
2. Mechanically filters every returned line through an anti-invention **grounding gate**
   before anything reaches the ledger (loop, outline_agent.py:1518-1582).
3. If nothing survives, discloses the exact string in question:
   **`"checklist[{trigger}] ran: NONE (no grounded deficiencies)"`** at
   **outline_agent.py:1618** (guarded by `if not new_todos and not n_ungrounded and not n_unhomeable:` at 1611).

## The decision logic (quoted, with file:line)

The gate that admits or drops each candidate deficiency:

- Line-shape check — a line without 4 `::` fields is dropped as ungrounded
  (outline_agent.py:1521-1529):
  ```
  parts = [p.strip() for p in line.split("::")]
  if len(parts) < 4:
      n_ungrounded += 1
      ...
      continue
  ```
- The quote gate — outline_agent.py:1530-1534:
  ```
  section, aspect, kind_raw, quote = parts[0], parts[1], parts[2], parts[3]
  if not _quote_is_grounded(quote, question_norm):
      n_ungrounded += 1
      ungrounded_lines.append(line[:160])
      continue
  ```

`_quote_is_grounded` is the actual admission rule — **outline_agent.py:298-310**:
```
def _quote_is_grounded(quote: str, question_norm: str) -> bool:
    q = _normalize_for_quote_check(quote)
    if not q or len(q.split()) < _MIN_GROUNDING_QUOTE_WORDS:   # _MIN = 2  (line 286)
        return False
    return q in question_norm            # <-- LITERAL SUBSTRING of the question
```
Normalization (outline_agent.py:292-295) only lowercases, collapses whitespace, and strips
wrapping quote punctuation:
```
stripped = str(text or "").strip().strip(_QUOTE_WRAP_CHARS).strip()
return _re.sub(r"\s+", " ", stripped.lower())
```

So a deficiency is admitted **iff** the model's quote is a **case/whitespace-normalized literal
substring of the research question** AND is at least 2 words. There is NO semantic, synonym,
stemming, or entailment matching — it is a raw `in` substring test.

The prompt reinforces this as a *precision* gate, not a recall gate
(outline_agent.py:1418-1432): "only flag a deficiency for an aspect that is EXPLICITLY named
or directly implied by the wording of the QUESTION… you MUST include a QUOTE: a short verbatim
excerpt copied EXACTLY… from the QUESTION text… If you cannot produce such a quote, do not list
the line." And the model is told to reply exactly `NONE` when unsure (1431-1432, 1449).

## Why it returns "NONE (no grounded deficiencies)" on a genuine CV-safety coverage gap

The `NONE (no grounded deficiencies)` disclosure fires when the filtered result is empty
(outline_agent.py:1611-1618). There are two ways a REAL gap gets zeroed out:

1. **The model never emits the line** — instructed to reply `NONE` unless it can copy a
   verbatim question quote, a cautious model under the strict "precision gate, do not invent"
   framing (1418-1432) suppresses borderline lines. Nothing to filter -> empty -> NONE.

2. **The model emits the line but the literal-substring gate at 1531 rejects it.** This is the
   most likely under-detection path and it is structural, not stochastic:

### Most likely reason it under-detected

`_quote_is_grounded` requires the quote to be a **literal substring of the question text**
(outline_agent.py:310, `return q in question_norm`). A genuine CV-safety coverage gap is
under-detected whenever the question asks for cardiovascular safety **using different words than
the model's quote** — i.e. the gate cannot match a paraphrase or a synonym.

Concrete failure: the worked example the code itself ships (outline_agent.py:1427,
1437-1438) is `"long-term cardiovascular safety"`. That example only survives because those
exact words appear in the question. But real questions phrase it as "cardiac risk",
"CV outcomes", "heart-related adverse events", "MACE", "effects on the cardiovascular system",
or the requirement is *implied* by "safety profile" / "long-term safety" without the literal
token "cardiovascular." In every such case:

- The model (correctly) names the missing facet as e.g. `cardiovascular safety`.
- `_normalize_for_quote_check` lowercases both sides but does no synonym/stem expansion.
- `"cardiovascular safety" in question_norm` is **False** because the question says "cardiac
  risk" / "CV" / "heart", not the literal string "cardiovascular safety."
- Line is counted `n_ungrounded` and `continue`-dropped at 1532-1534.

If that was the ONLY candidate, `new_todos` is empty. Note the NONE disclosure at 1618 only
fires when `not n_ungrounded` too — so a dropped-paraphrase gap actually surfaces as the
`"dropped N ungrounded line(s)"` disclosure at 1607, NOT the NONE line. Therefore the exact
string **"NONE (no grounded deficiencies)"** most precisely corresponds to case (1): the model,
constrained by the strict precision prompt, **declined to name the CV-safety facet at all** (or
named it with a <2-word quote such as the bare drug name, rejected by the word-count guard at
1308/308), leaving zero lines to filter.

### Root cause, one sentence
The grounding gate is a **literal case-insensitive substring match** of the model's quote
against the raw question (outline_agent.py:298-310), with no synonym/stem/entailment tolerance
and a ≥2-word requirement; a real CV-safety gap that the question phrases with different or
merely-implied wording (or that the cautious "reply NONE if unsure" prompt at 1431-1449
suppresses) produces no admitted deficiency, so the checklist discloses
`NONE (no grounded deficiencies)` at outline_agent.py:1618 despite the gap being real.

## Suggested careful-refactor direction (for the caller, not applied)
- Relax `_quote_is_grounded` from raw substring to token-overlap / stem or a small entailment
  check, OR
- Accept a quote that matches an implied requirement (e.g. "safety" present in question =>
  admit "cardiovascular safety" as a sub-facet), OR
- Distinguish "model said NONE" from "gate dropped everything" in the disclosure so an operator
  can tell precision-suppression apart from genuine saturation. (The `n_ungrounded` disclosure
  at 1606-1610 already does the latter, but the pure-NONE path at 1618 hides case (1).)
