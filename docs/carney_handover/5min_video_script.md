# POLARIS — 5-minute walkthrough script

**Audience:** PM Carney's office team
**Run-time target:** 5 minutes
**Filming:** record once with audio + screen capture; no edits unless content errors

---

## 0:00–0:30 · Cold open + frame

> [Camera on a clean POLARIS Canada landing page. Speak slowly.]

"This is POLARIS — a sovereign Canadian deep research AI built for the Office of the Prime Minister. In the next five minutes I'll show you a real research run end-to-end, and you'll see something no other system on the market does: every sentence carries a token that points to the exact span of the source it came from."

---

## 0:30–1:30 · Run start + scope discovery

> [Click "Start a research run" on the dashboard. Pick the housing template. Type the question.]

"I'll pick the housing template and ask: *What does the latest CMHC data say about Q3 2025 housing starts across Canadian metros?*

Before any cost is incurred, POLARIS runs a **scope check**. You can see the panel here. It says: accepted, the question fits the template, sources will draw from Tier-1 government and academic data. If I had instead asked something out-of-scope — *should I take a specific drug?* — POLARIS would refuse with rationale, and the Start-run button would be disabled. Let me show that briefly."

> [Demo the rejection: type "Should I take ozempic?", click Check scope. Show the red panel.]

"That refusal is enforced in code, not just policy. POLARIS is research synthesis, not a personal-advice service."

---

## 1:30–3:00 · Live run + Inspector view

> [Go back to the housing question. Click Start run. Wait for SSE events to populate.]

"As the run executes you can watch the verifier pipeline in real time — scope decision, retrieval progress, verifier verdicts per sentence, section completes. When it finishes, click into the **Inspector**.

Here's the run. Three things to notice.

> [Point at the top KPI cards.]

First, the two-family invariant. The generator was DeepSeek V4 Flash. The verifier was Gemma 4 31B. They are from different lineages, so neither can certify its own output. If they shared a lineage, POLARIS aborts the run before any token is billed.

> [Click the Verified Sentences tab. Hover over a provenance token.]

Second, click any token like this — `[#ev:ev_house_001:500-700]` — and the right-side pane shows the verbatim source span the sentence is anchored to. CMHC, characters 500 to 700, the URL, the actual text. Every claim, every sentence."

> [Click the Contradictions tab.]

"Third, when sources disagree — here CMHC reports a 3.4% rise and StatCan reports a 0.2% decline — POLARIS surfaces the contradiction explicitly. It does not paper over it. The Resolution column tells you which way it was handled — in this case, *noted both*."

---

## 3:00–4:00 · Audit bundle export

> [Click Export bundle JSON in the Inspector header.]

"For your office to own the artifact, every run exports as a single JSON file conforming to the **Evidence Contract v1.0** schema. That file in your downloads folder is everything: the question, the evidence pool with verbatim source spans, every verified sentence, every contradiction, the cost, the models, the family-segregation invariant verdict.

Hand this file to anyone — your policy team, an external reviewer, an opposition-party staffer — and they can replay every claim to its source without standing up POLARIS at all."

---

## 4:00–4:30 · Sovereign + replay

"Two more things.

The cluster running this is sitting in OVH Beauharnois — Canadian sovereign infrastructure. Cognition stays Canadian. CDN and observability use US providers; no Canadian-resident data crosses for those.

And every run can be **replayed**. If three months from now your team wants to verify whether POLARIS still produces the same answer to the same question with the same sources, click Replay on a saved Pin. POLARIS produces a diff: same answer, drift, or regression. You'll know before anyone else does."

---

## 4:30–5:00 · Close

"That's POLARIS. Sovereign Canadian. Two-family verified. Provenance per sentence. Contradictions surfaced. Bundle exportable. Replayable.

The full source code is in the GitHub repo handed over alongside this video. The runbook is in `docs/runbook.md`. Warm support runs 30 days from handover.

Built honest. Built sovereign. Thank you."

> [End on the POLARIS landing page.]

---

## Production checklist

- [ ] Record on the production cluster, not the dev cluster.
- [ ] Use a real recent question, not a contrived one.
- [ ] Confirm the rejection example actually shows the disabled Start-run button.
- [ ] Confirm the bundle JSON downloaded matches the Evidence Contract v1.0 schema.
- [ ] Audio: clear, no background hum; subtitled in EN-CA + FR-CA.
- [ ] Final review: user runs full walkthrough in fresh browser before recording (per memory `bpei_phantom_completion_lessons.md`).
