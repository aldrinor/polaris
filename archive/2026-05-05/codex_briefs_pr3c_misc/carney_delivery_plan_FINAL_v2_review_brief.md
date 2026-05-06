# Codex GREEN verification — FINAL plan with 5 redlines applied

**Model:** gpt-5.5, xhigh reasoning. Final verification.

**Your role:** verify the 5 redlines from your previous review are correctly applied. If yes, give explicit GREEN so user can commit and start Phase 0. If anything is still wrong, name it specifically as the last surgical pass.

**Word budget:** ~800 words.

---

## What was done

You returned YELLOW on `docs/carney_delivery_plan_FINAL.md` with 5 specific surgical redlines. I applied all 5:

**Redline 1 — Mandatory paid sample evaluator**: section "Validation roles" rewritten. Paid sample evaluator now mandatory ($3-8k). Blind-scores benchmark sample, all 8 template smoke tests, adversarial cases, evidence-contract behavior. Budget table updated.

**Redline 2 — Honest naming**: User renamed from "Layer 3 evaluator" to "product-owner acceptance." Stated explicitly that user has commercial interest, NOT independent validation. Pre-handover validation = product-owner + paid sample evaluator + Codex; final = Carney's office.

**Redline 3 — Code-enforced data classification**: section "Provider routing enforcement" added. Five classifications (PUBLIC_SYNTHETIC | CAN_REAL | PRIVATE | CLIENT | UNKNOWN). Default-deny external API calls. Only PUBLIC_SYNTHETIC may route to DeepSeek API. CI test (`tests/sovereignty/test_routing_policy.py`) proves all four other classifications get blocked. Routing decisions logged.

**Redline 4 — TTL/autostop/budget gates**: section "Hardware strategy" expanded with enforcement subsection. Every GPU instance gets TTL tag (default 4h max, configurable), idle autostop after 10 min, daily budget cap via `scripts/gpu_budget_guard.py`, weekly audit committed to `docs/gpu_audit_log.md`, phase-end Codex review of cost/uptime; over-budget by >10% = RED escalation.

**Redline 5 — Explicit 8-template content calendar**: section "8 templates" rewritten with owner + content-week + acceptance packet per template. Each template's acceptance packet contains: charter, source policy, 10 example queries, 15-question eval set, smoke test. Templates aren't "incidental Phase 2-3 polish" — they have explicit content-weeks (T2 in Phase 0-1 weeks 1-2, T3 in Phase 1 weeks 2-3, T4 in Phase 2 week 1, ..., T8 in Phase 3 week 1). Per-template gate: Codex reviews packet + user signs off + smoke test passes.

**Bonus**: Budget framing redline applied. "$25-58k external cash ceiling, EXCLUDING user labor, Codex API costs, internal review labor." Be honest the cash savings came from moving work into user/Codex labor.

## What I want you to verify

For each of the 5 redlines:
- Closed (correctly applied)
- Partial (specify gap)
- Unaddressed (specify what's missing)

Then verdict:
- **GREEN**: plan is sprint-startable; user commits budget; Phase 0 begins.
- **YELLOW**: a small additional fix needed (name the specific lines).
- **RED**: structural issue (name it).

## Output structure

- Per-redline status (1-5)
- Final verdict (GREEN / YELLOW / RED)
- One-sentence start recommendation

## Constraints

- Brutal as before.
- The user wants no further iteration after this. If GREEN, they will commit and start Phase 0 today.
- If you find a remaining issue, name the specific line(s) so I can fix it in one more pass.
- Don't soften.

The plan is at `docs/carney_delivery_plan_FINAL.md`. Read it directly.
