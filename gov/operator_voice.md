# Operator voice

The operator is blind and reads by ear. Every message is heard once, out loud,
in order. There is no scanning back. If a sentence only works on a screen, it
does not work.

This file is the rule. `tools/lint_operator_message.py` enforces it and reads
its banned word list straight out of this file, so there is one list and it
lives here.

## The five rules

1. Five sentences at most, for the whole message.
2. Flat lists only. A list item that is indented under another item is banned,
   because indentation is silent when read aloud.
3. No emoji. A screen reader says the whole name of the picture, and it breaks
   the sentence.
4. No jargon and no inflated adjectives. The banned list is below.
5. Thirty-five words at most in one sentence. Long sentences lose the listener
   before the verb arrives.

## What to do instead

Say the thing that happened. Then say what it means. Then say what is next.
Use the plain word, not the clever one. Say numbers as numbers. Name files and
commands in full so they can be repeated back.

## Fenced blocks are for pasted output, not for the message

If you must paste a command and its output, put it inside a fenced code block.
The linter skips fenced blocks, because pasted output is not your writing.

That skip used to be the way around every rule at once: put the whole message
in a fence and nothing was read. So the fence now has to be a real one.

1. It opens and closes with the same mark, and the closing run is at least as
   long as the opening run. A block opened with three backticks is not closed
   by three tildes.
2. It is indented no more than three spaces. Four spaces is an indented code
   block in normal markdown, which renders as plain text, so the linter reads
   it as plain text too.
3. It closes. A fence that never closes is rejected, because everything after
   it would be skipped without being read.
4. It is not the whole message. A message with no words outside the fence is
   rejected.

## Naming a banned word on purpose

Sometimes the plain thing to say is the banned word itself, as in a sentence
about this list. Put it in backticks and the linter leaves it alone, because a
quoted word is not you saying it.

## Structure a listener never hears

Tables and HTML layout tags are rejected. A table is read cell by cell with no
column names, and an HTML list can hide a nested list inside a line that looks
flat. Say it as sentences.

## Banned words and phrases

These are jargon, filler, or adjective inflation. Some of them appear in this
project's own specification files, and that is fine. The rule is about what you
say to the operator, not what a specification says. This file itself is a
specification, so do not point the linter at it.

<!-- banned_words_begin -->
```text
leverage
robust
seamless
comprehensive
holistic
synergy
cutting-edge
world-class
lethal
surgical
irreducible
empirical
converge
sprawl
load-bearing
by design
utilize
facilitate
streamline
paradigm
ecosystem
best-in-class
state-of-the-art
granular
orchestrate
delve
underscore
pivotal
myriad
plethora
deep dive
low-hanging fruit
move the needle
unlock
empower
elevate
bespoke
turnkey
frictionless
performant
non-trivial
actionable
operationalize
at the end of the day
going forward
it is worth noting
circle back
north star
table stakes
game-changer
```
<!-- banned_words_end -->

The linter also catches the normal endings of these words. If `leverage` is
banned then `leveraging` and `leveraged` are banned too, and so is
`leverage-based`, and so is the version split by bold marks, and so is the
version written with a lookalike letter from another alphabet.

## What this checker does not do

Say this plainly, because a checker that is trusted for more than it does is
worse than no checker.

1. The list is finite. Jargon that is not on it passes. A sentence like "the
   idempotent serializer preserves polymorphic payload invariants" breaks every
   rule of this document and the linter accepts it.
2. The list is context free. It cannot tell the banned verb from the innocent
   noun, so a sentence that needs one of these words as a plain noun is
   rejected. Put it in backticks, or say it another way.
3. Thirty five words is a judgement, not a measurement. It has not been checked
   against a body of real messages.
4. It does not measure whether a message is understandable. It measures shape.
   Read it aloud yourself before you send it.

## Bad, then good

Bad. This fails on four of the five rules at once.

> We leveraged a comprehensive audit across the retrieval substrate to surface
> the irreducible root cause, and the holistic finding is that the cache layer
> is structurally load-bearing in a way that was not seamless, so going forward
> we recommend a surgical fix.
> - Cache
>   - Empty body handling
>   - Retry path

Good. Same facts, said out loud.

> The fetch step returned empty pages for two sources. The cache stored those
> empty pages and handed them back as if they were real. I changed the cache to
> fetch again when the page is empty. The two sources now return real text.
> Next I will run the full fetch test set.

The good version has five sentences, no list, no banned words, and every
sentence is short enough to hear in one breath.

## How to check a message before sending it

```
python3 tools/lint_operator_message.py path/to/message.md
python3 tools/lint_operator_message.py --selftest
```

Exit code 0 means the message is fine to send. Exit code 1 means it is not, and
the offending sentence is printed back to you.
