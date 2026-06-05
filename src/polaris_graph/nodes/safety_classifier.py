"""I-ready-007 (#1072): deterministic input harm-refusal classifier (offline, no model, §8.4-safe).

POLARIS had NO input harm-refusal layer: a harmful-but-answerable, clinically-shaped query (e.g.
"optimal insulin dose to fatally harm an adult") passed the scope gate and yielded a FAITHFUL,
well-cited, audit-bundled report assisting the harmful objective. This module is the input guardrail.

DESIGN — a HIGH-PRECISION floor, NOT a complete guardrail:
  * It keys on an explicit harm-INTENT / weaponization-ACTION clause, NOT on clinical / policy /
    epidemiology subject matter. "insulin dose for an adult with type 1 diabetes",
    "management of warfarin overdose", "the Chemical Weapons Convention verification regime", and
    "fentanyl overdose mortality statistics" all carry NO intent clause -> harmful=False. The clinical
    / policy product is never over-refused.
  * It catches EXPLICIT harm-intent: an intent-to-kill/poison clause against a person, a make/build/
    synthesize weaponization clause, CSAM, suicide-METHOD-seeking, illicit-drug-SYNTHESIS.
  * It is honestly a FLOOR: paraphrased / obfuscated / novel harm phrasing is OUT OF SCOPE and is
    deferred to a follow-up (a robust open-weight intent classifier). A keyword classifier cannot be
    complete (the #1082 clinical-router lesson); here incompleteness = under-refusal, so this is
    scoped as "strictly better than the current zero-layer", not "safe by completeness".

FAIL-OPEN (Codex brief-gate decision exception_polarity=fail_open_proceed): any internal error returns
harmful=False so the caller proceeds to the normal path (a safety-classifier bug must never silently
abort a legitimate clinical run; the downstream faithfulness gate still bounds hallucination, and the
flag is OFF in the locked benchmark). The operator's "refuse when uncertain" lean is honored for
explicit category hits (which always refuse), NOT for ambiguous clinical subjects (over-refusing those
would break the product).

The caller wires this behind ``PG_USE_SAFETY_REFUSAL`` (default OFF -> byte-identical). On harmful=True
the caller emits manifest status ``abort_safety_refused`` + a refuse-with-redirection message (2026
partial-compliance best practice, arXiv 2506.00195) BEFORE any retrieval or generator spend.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class HarmDecision:
    """The harm-refusal decision. ``reasons`` is auditable telemetry for the manifest."""

    harmful: bool
    category: str            # "" when harmful is False; else the matched category
    confidence: float        # 0.0 - 1.0
    reasons: list[str] = field(default_factory=list)


# A person/victim object — the lethal-intent patterns anchor to a PERSON so "kill a process",
# "kill the pain", "kill time" never match. Includes generic + clinical-victim nouns. The bare
# pronouns carry a trailing \b so a REFLEXIVE ("themselves"/"himself"/"herself") does NOT match —
# reflexive self-kill is self-harm semantics (its own category + help-guard), not lethal-against-
# others, so "support someone who wants to kill themselves" is a HELP query, not a harm request.
_PERSON = (
    r"(?:someone|some\s?one|a\s+person|a\s+human|a\s+man|a\s+woman|a\s+child|an\s+adult|"
    r"people\b|humans?\b|him\b|her\b|them\b|my\s+\w+|"
    r"the\s+(?:patient|victim|person|target|elderly|baby|infant))"
)

# Care / prevention / first-aid context — a query about STOPPING or TREATING harm is not a harm
# request. Vetoes the lethal category (mirrors the self-harm help-guard). High-precision floor: this
# slightly widens under-refusal for adversarial "...please support" suffixes, but the priority is to
# never over-refuse legitimate prevention / poison-management / first-aid queries (the product).
_LETHAL_CARE_GUARD = re.compile(
    r"\b(?:prevent|preventing|stop|stopping|protect|save|rescu(?:e|ing)|talk\s+\w+\s+out\s+of|"
    r"first\s+aid|antidote|reverse|reversal|how\s+to\s+help|support\s+(?:someone|a\s+\w+|them)|"
    # Codex diff-gate iter-1 P1: clinical-MANAGEMENT framing is a HELP query, not a harm request, even
    # when the case presentation describes a third party's lethal intent ("management of intentional
    # insulin overdose intended to kill a patient"). The product MUST answer these.
    r"manage|management|treat(?:ment|ing|s)?|clinical|emergency|\bicu\b|hospital|"
    r"poison\s+control|overdose\s+management|resuscitat|supportive\s+care|nursing|paramedic)\b",
    re.IGNORECASE,
)

# 1) LETHAL INTENT AGAINST PERSONS — requires an explicit intent-to-kill/poison clause toward a
#    person. Bare "drug + dose" carries no intent verb -> never matches. Codex diff-gate iter-1 P1:
#    the intent verb may be "would/will/that-would kill", not only "to kill" ("what dose of insulin
#    WOULD KILL my roommate" was missed).
_LETHAL_INTENT = re.compile(
    r"\b(?:to|would|will)\s+(?:kill|murder|poison|fatally\s+harm|cause\s+(?:the\s+)?death\s+of|"
    r"end\s+the\s+life\s+of|euthani[sz]e\s+(?!myself))\s+" + _PERSON
    + r"|\b(?:lethal|fatal|deadly)\s+(?:dose|amount|quantity)\s+(?:to|that\s+(?:would\s+)?(?:kill|cause)|"
    r"of\s+\w+\s+(?:to|that\s+(?:would|will|could))\s+kill)"
    r"|\bhow\s+to\s+(?:kill|murder|poison)\s+" + _PERSON
    + r"|\b(?:overdose|dose|amount|quantity|how\s+much)\b.{0,45}?"
    r"\b(?:to|would|will|that\s+(?:would|will|could|can))\s+(?:kill|murder|fatally\s+harm|cause\s+death)"
    r"|\bso\s+(?:that\s+)?(?:it|they|he|she|the\s+(?:patient|person|victim|baby|infant))\s+"
    r"(?:dies|die|will\s+die|won['’]t\s+survive)"
    r"|\bundetectable\s+poison|\buntraceable\s+(?:poison|method)\b",
    re.IGNORECASE,
)

# 2) WEAPONIZATION — Codex brief P2-1: require an ACTION verb (make/build/synthesize/deploy/...), NOT
#    a bare subject. "the Chemical Weapons Convention", "nerve-agent treatment guidelines",
#    "history of chemical weapons" carry no action verb -> never match.
_WEAPONIZATION = re.compile(
    r"\b(?:synthesi[sz]e|synthesi[sz]ing|make|making|build|building|manufactur|produc(?:e|ing)|"
    r"construct|creat(?:e|ing)|assembl|deploy|weaponi[sz]|disperse|releas(?:e|ing)|aerosoli[sz])"
    r"\w*\s+(?:a\s+|an\s+|the\s+|some\s+)?"
    r".{0,30}?\b(?:bioweapon|biological\s+weapon|chemical\s+weapon|nerve\s+agent|nerve\s+gas|"
    r"sarin|\bvx\b|mustard\s+gas|dirty\s+bomb|explosive\s+device|pipe\s+bomb|\bied\b|"
    r"pathogen|anthrax|smallpox|botulinum|ricin|weaponi[sz]ed\s+pathogen|bioweapon)"
    r"|\bhow\s+to\s+(?:make|build|synthesi[sz]e|construct|create)\s+(?:a\s+|an\s+)?"
    r"(?:bomb|explosive|bioweapon|chemical\s+weapon|nerve\s+agent|nerve\s+gas|dirty\s+bomb|"
    r"pipe\s+bomb|grenade)\b",
    re.IGNORECASE,
)

# 3) CSAM — unambiguous literal terms. Any hit -> harmful.
_CSAM = re.compile(
    r"\b(?:child\s+sexual\s+abuse\s+material|csam|child\s+(?:porn(?:ography)?|sexual\s+abuse)|"
    r"(?:sexual(?:i[sz]e)?|nude|explicit)\s+\w{0,12}?\s*(?:minor|child|underage|prepubescent)|"
    r"(?:minor|child|underage|prepubescent)\s+\w{0,12}?\s*(?:porn|sexual|nude|explicit))\b",
    re.IGNORECASE,
)

# 4) SELF-HARM METHOD-SEEKING — method-seeking, NOT help/awareness. The help/awareness guard below
#    vetoes "suicide hotline", "prevention", "signs of", "help a friend who", "support".
_SELF_HARM_METHOD = re.compile(
    r"\b(?:how\s+(?:do\s+i|to|can\s+i)|best\s+way\s+to|easiest\s+way\s+to|fastest\s+way\s+to|"
    r"method[s]?\s+(?:to|of|for)|ways?\s+to|painless\s+way\s+to)\s+"
    r"(?:commit\s+suicide|kill\s+myself|end\s+my\s+life|end\s+it\s+all|take\s+my\s+(?:own\s+)?life|"
    r"hang\s+myself|overdose\s+(?:on\s+\w+\s+)?(?:to\s+die|and\s+die)|self[-\s]?harm|cut\s+myself)\b"
    r"|\bsuicide\s+method[s]?\b|\bhow\s+much\s+\w+\s+(?:to|will)\s+\w*\s*(?:overdose|be\s+lethal|kill\s+me)\b",
    re.IGNORECASE,
)
_SELF_HARM_HELP_GUARD = re.compile(
    r"\b(?:hotline|helpline|prevention|crisis\s+line|support|resources?|help\s+(?:a|my|someone|"
    r"them|him|her)|signs?\s+of|warning\s+signs|how\s+to\s+help|talk\s+to|reach\s+out|cope|coping|"
    r"recover(?:y|ing)?|therapy|counsel|988|samaritans)\b",
    re.IGNORECASE,
)

# 5) ILLICIT DRUG SYNTHESIS — requires a synthesis/manufacture verb OR a recipe/instructions request.
#    "fentanyl overdose deaths", "the opioid epidemic", "methamphetamine addiction treatment" carry no
#    synthesis verb -> no match. Codex diff-gate iter-1 P1: "recipe for methamphetamine" was missed.
_ILLICIT_SYNTHESIS = re.compile(
    r"\b(?:synthesi[sz]e|synthesi[sz]ing|cook|cooking|manufactur|produc(?:e|ing)|make|making|"
    r"extract(?:ing)?|brew|refin(?:e|ing))\w*\s+(?:a\s+|some\s+|your\s+own\s+|home(?:made)?\s+)?"
    r".{0,20}?\b(?:methamphetamine|crystal\s+meth|\bmeth\b|fentanyl|carfentanil|heroin|cocaine|"
    r"\bmdma\b|\blsd\b|\bpcp\b|ghb)\b"
    r"|\b(?:recipe|instructions|guide|blueprint|formula|protocol)\s+for\s+"
    r"(?:making\s+|cooking\s+|synthesi[sz]ing\s+|producing\s+)?"
    r"(?:methamphetamine|crystal\s+meth|\bmeth\b|fentanyl|carfentanil|heroin|cocaine|\bmdma\b)\b"
    r"|\bclandestine\s+(?:drug\s+)?(?:synthesis|lab|manufactur)"
    r"|\bsynthesis\s+route\s+(?:for|of)\s+(?:fentanyl|methamphetamine|meth|heroin|mdma|carfentanil)\b"
    r"|\bhow\s+to\s+(?:cook|make|synthesi[sz]e|manufacture)\s+(?:meth|methamphetamine|fentanyl|"
    r"crystal\s+meth|heroin|mdma|cocaine)\b",
    re.IGNORECASE,
)

# Prevention / policy / enforcement framing for the MAKE/BUILD categories (weaponization, illicit
# synthesis). Codex diff-gate iter-1 P1: "public health interventions to prevent people from making
# fentanyl" and "policy to stop bioweapon proliferation" are legitimate policy queries, not how-to
# requests. This guard requires explicit POLICY/PREVENTION nouns (not a bare "stop"), so an
# adversarial "...to stop my enemy" suffix does NOT trip it.
_ACTION_PREVENTION_GUARD = re.compile(
    r"\b(?:public\s+health|policy|policies|regulat\w*|enforcement|law\s+enforcement|interdict\w*|"
    r"nonproliferation|non-?proliferation|counter[-\s]?(?:terror\w*|prolifer\w*|narcotic\w*)|"
    r"treaty|treaties|convention|disarmament|crackdown|seizure|surveillance|epidemiolog\w*|"
    r"prevent\w*\s+(?:people|the\s+public|others|them|the\s+spread|production|traffick\w*|"
    r"proliferat\w*|access|\w+\s+from\s+(?:making|producing|synthesi))|"
    r"(?:reduce|disrupt|combat\w*|stop|curb|tackle)\s+(?:the\s+)?(?:production|traffick\w*|spread|"
    r"proliferat\w*|manufactur\w*|supply|distribution|epidemic))\b",
    re.IGNORECASE,
)


def classify_harm_intent(question: str) -> HarmDecision:
    """Classify ``question`` for explicit harm INTENT. Deterministic, fail-open, never raises.

    Returns ``harmful=True`` only on an explicit harm-intent / weaponization-action / CSAM /
    suicide-method / illicit-synthesis clause. Bare clinical / policy / epidemiology subjects
    (no intent clause) return ``harmful=False`` so the legitimate research product is never
    over-refused. Each category with a legitimate counterpart (lethal/self-harm → care/help;
    weaponization/illicit → policy/prevention) carries its own guard veto — handled INLINE below, NOT
    a generic loop, so a guard can never be bypassed. Any internal error returns ``harmful=False``."""
    try:
        q = (question or "").strip()
        if not q:
            return HarmDecision(False, "", 0.0, ["empty_question"])

        # Self-harm: method-seeking AND not help/awareness (the veto preserves the support use case).
        if _SELF_HARM_METHOD.search(q) and not _SELF_HARM_HELP_GUARD.search(q):
            return HarmDecision(True, "self_harm_method", 0.9, ["self_harm_method_seeking"])

        # Lethal-against-persons: explicit intent AND not a care / management / prevention context.
        if _LETHAL_INTENT.search(q) and not _LETHAL_CARE_GUARD.search(q):
            return HarmDecision(
                True, "lethal_intent_against_persons", 0.9,
                ["lethal_intent_against_persons_explicit_intent"],
            )

        # Weaponization: make/build ACTION AND not a policy / prevention / enforcement context.
        if _WEAPONIZATION.search(q) and not _ACTION_PREVENTION_GUARD.search(q):
            return HarmDecision(True, "weaponization", 0.9, ["weaponization_explicit_intent"])

        # Illicit synthesis: synthesis verb / recipe AND not a policy / prevention / enforcement context.
        if _ILLICIT_SYNTHESIS.search(q) and not _ACTION_PREVENTION_GUARD.search(q):
            return HarmDecision(True, "illicit_synthesis", 0.9, ["illicit_synthesis_explicit_intent"])

        # CSAM: no legitimate counterpart -> any literal hit refuses (no guard).
        if _CSAM.search(q):
            return HarmDecision(True, "csam", 0.9, ["csam_explicit"])

        return HarmDecision(False, "", 0.0, ["no_explicit_harm_intent"])
    except Exception as exc:  # noqa: BLE001 — fail open: a classifier bug must never abort a run.
        return HarmDecision(False, "", 0.0, [f"classifier_error_fail_open:{type(exc).__name__}"])


# Refuse-with-redirection message (2026 partial-compliance best practice, arXiv 2506.00195) — a
# redirection toward legitimate help, NOT a flat "denied". Tunable, not hard-coded at the call site.
SAFETY_REFUSAL_REDIRECTION: str = (
    "This request appears to seek information that could be used to cause serious harm, so POLARIS "
    "will not research it. If you have a legitimate need:\n"
    "- Clinical questions (safe dosing, adverse-effect profiles, overdose *management*): consult a "
    "licensed clinician, a hospital pharmacy, or your regional poison-control centre.\n"
    "- Policy / regulatory / historical questions about controlled materials: rephrase toward the "
    "policy, treaty, epidemiology, or clinical-management aspect and resubmit.\n"
    "- If you or someone you know is in crisis or considering self-harm: please contact a local "
    "emergency line or a suicide-prevention hotline (e.g. 988 in the US/Canada) right now."
)
