# Generalization rule — no benchmark overfit, no hardcoding (govkit)

We are building a GENERAL deep-research tool, not a benchmark-gamer. A score gained by tuning to one
task (task 72, the AI-labor-market corpus) is worthless — it must not exist. Every improvement MUST work
for any research question, any domain.

## Rules — apply to every fix, every round
1. **Read from the TASK, never hardcode the task's specifics.** e.g. a source-eligibility fix parses the
   RQ's own stated constraints ("peer-reviewed journals", "before 2023", a language) generically — it does
   NOT hardcode "journal-only, pre-June-2023" because task 72 asked for it. Structure, tiers, thresholds:
   all derived or configured, never task-literal.
2. **No hardcoded values** — every tunable through the central config layer (`resolve()` + `config_defaults`),
   never a bare literal or `os.getenv("X", literal)`. (This is the standing config discipline.)
3. **Domain-agnostic by construction.** No clinical-only / AI-labor-only branches. If a change helps only
   one corpus, it is wrong.
4. **Prove generality, not just the score.** A gain on task 72 alone is a red flag until the mechanism is
   shown to be general (would it help a chemistry review? a policy report?). State why the fix generalizes.
5. **Everything through the agentic infra** — govkit gates (Sol + K3), plain descriptive names, docs,
   checkpoint-safe. See `agent_iteration_protocol.md`, `background_task_discipline.md`.

## Why
The whole value is a tool that writes a rigorous, well-structured, faithful report on ANYTHING. Overfitting
to the benchmark would produce a number with no product behind it. Generality IS the product.
