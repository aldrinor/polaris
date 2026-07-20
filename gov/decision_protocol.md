# Decision protocol

The operator does not have the context to make a technical choice, and asking
for one stops the work until the next time they are at the keyboard. Handing
over a decision the operator cannot make is not caution. It is a stall.

## The binding rule

An agent never hands the operator a decision that needs context the operator
does not have.

There are exactly two allowed moves. Pick one. There is no third.

## Move A. Decide, and write it down

This is the default. Take the decision yourself, then say three things in three
sentences.

1. What you decided.
2. Why, in one plain reason.
3. What would make it wrong.

The third sentence is the important one. It is what lets the operator catch a
bad call without knowing the internals, and it is what an auditor reads later
to see the reasoning was real.

Shape:

```
I decided <the choice>.
I chose it because <the one reason>.
It would be wrong if <the observable thing that would prove it wrong>.
```

Worked example:

```
I decided to cache the fetched pages on disk instead of in memory.
I chose it because a run restarts often and memory is lost every restart.
It would be wrong if the pages change during a run, and I saw no sign of that.
```

## Move B. Ask exactly one question

Only when the decision needs something that lives with the operator and nowhere
else: money, legal risk, what the customer wants, what the demo must show, or
anything that cannot be worked out from the repository.

The question must have all four of these:

1. Exactly one question. Not two joined by "and".
2. Two or three options, no more.
3. A recommended option, marked with the word RECOMMENDED.
4. One plain line per option saying what happens if it is chosen.

The wording below is not decoration. `tools/lint_operator_message.py` looks for
these exact openings, counts them as one block instead of as sentences, and
then checks the four rules above. Three options and their three consequence
lines are seven lines in total, which would break the five sentence limit if
they were counted as sentences, so they are not. Write the lines in this shape
or the block is not recognised and the limit applies to every line.

Shape:

```
Question: <the one question, in plain words>

Option 1 (RECOMMENDED): <the option>
  If you pick this: <what happens, in plain words>

Option 2: <the option>
  If you pick this: <what happens, in plain words>
```

Worked example:

```
Question: Do you want me to spend about forty dollars on a paid run tonight?

Option 1 (RECOMMENDED): Yes, run it tonight.
  If you pick this: you get the real report tomorrow morning and it costs forty dollars.

Option 2: No, wait for the free test first.
  If you pick this: it costs nothing, and the real report slips to Monday.
```

## Banned

- A question with more than one question in it. Split it, decide the parts you
  can decide, and ask about the one part you cannot.
- Options written in jargon. If an option cannot be understood without reading
  the code, rewrite it in terms of what the operator will see or pay.
- "Which approach do you prefer" with no recommendation. If you cannot
  recommend one, you have not done the work yet.
- A list of five options. If there are five, you have not narrowed it down.
- Asking a question you can answer yourself by reading a file.

## The test before you ask

Ask yourself one thing: can I find this out by reading the repository, running
a command, or making a reversible choice?

If yes, do that. Use Move A.

If no, use Move B, and make the question small enough to answer with one word.

## Undo beats asking

A decision you can undo is not worth a question. Make it, write down how to
undo it, and keep going. Save Move B for the choices that cannot be taken back.

## The wording still has to pass

Whatever you send, it goes to a blind operator who hears it once. It has to
obey `gov/operator_voice.md`, and the checker is:

```
python3 tools/lint_operator_message.py path/to/message.md
```

The checker enforces this file too. If it finds a `Question:` line it then
requires exactly one question, two or three options, exactly one marked
RECOMMENDED, and one `If you pick this:` line for every option. A question with
four options is rejected by name, and so is a question with no recommendation.
