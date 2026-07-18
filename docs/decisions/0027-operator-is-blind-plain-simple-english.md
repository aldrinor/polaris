# 0027. The operator is blind: plain simple English in every message

Status: accepted

Date: 2026-06-18

## Context

The operator reads by ear through a screen reader (`user_is_blind_screen_reader_2026_05_28`). A blind operator cannot skim a dense paragraph, cannot read the `/workflows` panel, and hears every message read aloud once. This is the conversation arm of the standing "no cheerleading — it is lethal" rule and the plain-declarative writing standard (`CLAUDE.md` §0.4, operator-locked 2026-06-18).

## Decision

Talk in plain simple English in EVERY message — status, explanations, answers, recaps — not only in deliverables. Short sentences: subject, verb, fact. State numbers and names plainly. No jargon or clever phrasing (banned examples: "irreducible", "empirical", "converge", "sprawl", "load-bearing", "structurally", caption-fragments, compressed multi-idea sentences). Keep a needed technical noun, but say the sentence around it plainly.

Self-check before sending any message: would a person understand this if it were read aloud once? If not, rewrite it simpler. Announce each Workflow launch in one spoken line and read the key result (verdict plus counts) inline when it completes, because the operator cannot read the `/workflows` panel. Keep recurring loop triggers to one short line so the screen reader is not buried.

## Consequences

- Every message is a spoken message; there is no "skimmable" tier, so density that a sighted reader would skim past becomes noise read aloud.
- Workflow progress that lives only in a visual panel is invisible to the operator, so launches and results must be spoken inline or they effectively do not exist.
- Cheerleading and clever phrasing actively harm comprehension when heard once; plain declaration is the requirement, not a style preference.
- Status reports are a full list with every run on its own line, never grouped or omitted, because the operator cannot visually scan a compressed table.
