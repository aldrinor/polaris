"""POLARIS honest-rebuild external evaluator package (Phase 5).

Non-same-family evaluator: the generator (DeepSeek V4 Pro) and this
evaluator role MUST be from distinct training lineages (CLAUDE.md §9.1
two-family invariant). Under the LOCKED 4-role architecture
(``config/architecture/polaris_runtime_lock.yaml``, I-meta-001 #933) the
evaluator role maps to Mirror (Cohere Command A+); the legacy
``PG_EVALUATOR_MODEL`` knob is compat-mapped to ``PG_MIRROR_MODEL`` per the
lock's ``legacy_compat`` block. Both the generator and evaluator models are
swappable via ``PG_GENERATOR_MODEL`` / ``PG_MIRROR_MODEL``
(``PG_EVALUATOR_MODEL`` for back-compat) env vars, plus rule-based
PRISMA-trAIce compliance checks.
"""
