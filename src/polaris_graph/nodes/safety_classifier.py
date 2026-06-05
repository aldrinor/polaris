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
    r"(?:someone|some\s?one|a\s+person|a\s+human\s+being|a\s+human\b|a\s+man|a\s+woman|a\s+child|"
    r"an\s+adult|people\b|humans\b|him\b|her\b|them\b|"
    # "my/the/a X" is anchored to a PERSON noun (Codex diff-gate iter-3 over-refusal: bare "my \w+"
    # matched "kill my time"/"my process"). Whitelisted relations / roles (Codex iter-4: broadened).
    r"(?:my|the|a|an|his|her|their|your)\s+(?:roommate|boss|coworker|co-worker|colleague|wife|husband|"
    r"spouse|partner|ex|girlfriend|boyfriend|mother|father|mom|dad|parent|sister|brother|sibling|son|"
    r"daughter|child|kid|baby|infant|toddler|newborn|friend|neighbou?r|enemy|rival|teacher|landlord|"
    r"tenant|patient|in-?law|family\s+member|relative|grand(?:mother|father|ma|pa|parent|son|daughter)|"
    r"aunt|uncle|cousin|niece|nephew|nurse|doctor|physician|boss|coworker|victim|elderly\s+\w+)|"
    r"the\s+(?:patient|victim|person|target|elderly|baby|infant)|"
    # an adjective-qualified patient / resident ("a hospital patient", "an elderly resident").
    r"(?:my|the|a|an)\s+(?:hospital\w*|hospitali[sz]ed|elderly|\bicu\b|nursing[-\s]home|dialysis|"
    r"comatose|sedated|sleeping|unconscious|vulnerable|disabled|bedridden|terminally\s+ill)\s+"
    r"(?:patient|resident|person|relative)|"
    # a capitalized given name directly after the kill verb (case-sensitive even under re.I).
    r"(?-i:[A-Z][a-z]{2,}))"
)

# Care / clinical-management / prevention FRAME for the LETHAL category — a query ABOUT treating or
# preventing harm, not causing it. Codex diff-gate iter-2 P1: bare care TOKENS ("treating", "ICU",
# "hospital") let an explicit kill-intent bypass ("...would kill the patient I am treating"). This now
# requires a genuine HELPING STRUCTURE (management/treatment OF, emergency/ICU/hospital MANAGEMENT,
# antidote/first-aid/...), AND the classifier additionally requires this frame to LEAD the kill clause
# (see _frame_leads) so a TRAILING incidental care word can never rescue a harm request.
_LETHAL_CARE_GUARD = re.compile(
    # Genuine clinical-management GOVERNING structures only (Codex diff-gate iter-3: a loose leading
    # "prevent"/"how to help" let "to prevent detection, what dose would kill my roommate" / "how to
    # help my friend to poison someone" bypass). Each form GOVERNS an overdose/poisoning/harm object.
    r"\b(?:manage|management|managing|treat(?:ment|ing)?|care)\s+(?:of|for)\b"
    r"|\b(?:emergency|clinical|hospital|\bicu\b|inpatient|paramedic|medical|prehospital)\s+"
    r"(?:management|treatment|care|protocol|guideline)"
    r"|\b(?:antidote|reversal|reverse|resuscitat\w*|first\s+aid|supportive\s+care|poison\s+control|"
    r"overdose\s+management)\b"
    # Codex diff-gate iter-4: clinicians/hospitals managing an overdose is a HELP query.
    r"|\b(?:hospitals?|clinicians?|doctors?|physicians?|nurses?|paramedics?|providers?|clinics?|"
    r"\bed\b|\ber\b|emergency\s+depart\w*|icus?|staff)\s+(?:\w+\s+){0,2}?"
    r"(?:manage|managing|treat|treating|handle|handling|respond|responding|care\s+for|stabili[sz])"
    r"|\bprevent\w*\s+(?:\w+\s+){0,3}?(?:death|deaths|overdose|poisoning|self[-\s]?harm|suicide|"
    r"from\s+(?:dying|overdosing))\b",
    re.IGNORECASE,
)

# 1) LETHAL INTENT AGAINST PERSONS — requires an explicit intent-to-kill/poison clause toward a
#    person. Bare "drug + dose" carries no intent verb -> never matches. Codex diff-gate iter-1 P1:
#    the intent verb may be "would/will/that-would kill", not only "to kill" ("what dose of insulin
#    WOULD KILL my roommate" was missed).
_LETHAL_INTENT = re.compile(
    # (a) kill/poison/murder A PERSON, with any leading modal/infinitive/imperative. Codex diff-gate
    #     iter-3: "can/could", "how do/can I kill", "poison my coworker" were missed.
    r"\b(?:to|would|will|can|could|should)\s+"
    r"(?:kill|murder|poison|fatally\s+harm|cause\s+(?:the\s+)?death\s+of|end\s+the\s+life\s+of|"
    r"euthani[sz]e\s+(?!myself))\s+" + _PERSON
    + r"|\bhow\s+(?:to|do\s+i|can\s+i|would\s+i|should\s+i)\s+(?:kill|murder|poison|fatally\s+harm)\s+"
    + _PERSON
    # (b) lethal/fatal DOSE framed at a PERSON — anchored to _PERSON so "dose that would kill bacteria /
    #     tumor cells / norovirus" (legitimate science) does NOT match (Codex iter-3 over-refusal).
    + r"|\b(?:lethal|fatal|deadly)\s+(?:dose|amount|quantity)\b.{0,30}?\b(?:to|for)\s+" + _PERSON
    + r"|\b(?:overdose|dose|amount|quantity|how\s+much)\b.{0,45}?"
    r"\b(?:to|would|will|that\s+(?:would|will|could|can)|can|could|be\s+(?:lethal|fatal)\s+(?:to|for))\s+"
    r"(?:kill|murder|fatally\s+harm|cause\s+(?:the\s+)?death)\s+" + _PERSON
    + r"|\b(?:would|will|could|is|are)\s+(?:be\s+)?(?:lethal|fatal|deadly)\s+(?:to|for)\s+" + _PERSON
    # (c) explicit covert-kill markers.
    + r"|\b(?:poison|kill|murder)\s+" + _PERSON + r"\s+(?:undetectabl|untraceabl|without\s+(?:getting\s+"
    r"caught|detection|being\s+caught|a\s+trace))"
    r"|\bundetectable\s+poison|\buntraceable\s+(?:poison|method)\b"
    r"|\b(?:poison|toxin|substance|drug|chemical)\b.{0,30}?\b(?:undetectable|untraceable|undetected|"
    r"won['’]t\s+show|not\s+detected)\b.{0,20}?\b(?:autopsy|toxicology|post[-\s]?mortem|tox\s+screen)\b"
    r"|\bundetectable\s+(?:in\s+)?(?:an?\s+)?(?:autopsy|toxicology|post[-\s]?mortem)\b"
    r"|\bso\s+(?:that\s+)?(?:it|they|he|she|the\s+(?:patient|person|victim|baby|infant))\s+"
    r"(?:dies|die|will\s+die|won['’]t\s+survive)",
    re.IGNORECASE,
)

# An explicit NON-PERSON kill target — cells / microbes / pests / crops / in-vitro. Codex diff-gate
# iter-3 over-refusal: "what dose would kill bacteria / tumor cells / norovirus" is legitimate science.
# When present, the generic (un-targeted) lethal branch is vetoed.
_NONPERSON_TARGET = re.compile(
    r"\b(?:bacteri\w*|cells?|cellular|tumou?rs?|cancer|viral|virus(?:es)?|norovirus|pathogen\w*|"
    r"microb\w*|germs?|fung\w*|mold|mould|weeds?|pests?|insects?|larvae?|parasit\w*|amoeba\w*|"
    r"yeast|spores?|tissues?|crops?|plants?|rodents?|vermin|microorganism\w*|mosquito\w*|"
    r"in\s+(?:a\s+)?(?:culture|vitro|the\s+petri))\b",
    re.IGNORECASE,
)

# Generic un-targeted lethal intent ("overdose protocol TO CAUSE DEATH") — a human victim is implied.
# Only fires when NO explicit non-person target is present (so legit science is not over-refused).
# Excludes bare "lethal dose" (dual-use toxicology, e.g. "lethal dose of acetaminophen").
_LETHAL_GENERIC = re.compile(
    r"\b(?:overdose|dose|amount|quantity|how\s+much\s+\w+)\b.{0,45}?"
    r"\b(?:to|would|that\s+(?:would|will|could))\s+"
    r"(?:cause\s+(?:a\s+|the\s+)?death|be\s+(?:lethal|fatal)|prove\s+fatal)\b",
    re.IGNORECASE,
)

# 2) WEAPONIZATION — Codex brief P2-1: require an ACTION verb (make/build/synthesize/deploy/...), NOT
#    a bare subject. "the Chemical Weapons Convention", "nerve-agent treatment guidelines",
#    "history of chemical weapons" carry no action verb -> never match.
# "bombs?" carries a negative lookahead for benign compounds (Codex diff-gate iter-4: "bomb
# calorimeter" / "bath bomb" / "smoke bomb" / "bomb cyclone" are not weapons).
_WEAPON_SUBJECT = (
    r"(?:bombs?(?!\s+(?:calorimeter|cyclone))|explosives?|explosive\s+device|bioweapon|"
    r"biological\s+weapon|chemical\s+weapon|nerve\s+agent|nerve\s+gas|sarin|\bvx\b|mustard\s+gas|"
    r"dirty\s+bomb|pipe\s+bomb|\bied\b|grenade|pathogen|anthrax|smallpox|botulinum|ricin|"
    r"weaponi[sz]ed\s+pathogen)"
)
_BENIGN_BOMB = re.compile(r"\b(?:bath|smoke|bond|photo|stink|colou?r)[-\s]?bombs?\b|\bbomb\s+(?:calorimeter|cyclone)\b", re.IGNORECASE)
_WEAPONIZATION = re.compile(
    # an ACTION verb governing a weapon subject (Codex diff-gate iter-3/4: bare "bomb", "how can I
    # make", "instructions/blueprint to build", "engineer anthrax for release" were missed).
    r"\b(?:synthesi[sz]e|synthesi[sz]ing|make|making|build|building|manufactur|produc(?:e|ing)|"
    r"construct|creat(?:e|ing)|assembl|deploy|weaponi[sz]|disperse|releas(?:e|ing)|aerosoli[sz]|"
    r"engineer(?:ing)?|cultur(?:e|ing)|grow(?:ing)?)"
    r"\w*\s+(?:a\s+|an\s+|the\s+|some\s+|your\s+own\s+)?"
    r".{0,30}?\b" + _WEAPON_SUBJECT
    + r"|\bhow\s+(?:to|do\s+i|can\s+i|would\s+i)\s+(?:make|build|synthesi[sz]e|construct|create|"
    r"assemble|engineer)\s+(?:a\s+|an\s+)?" + _WEAPON_SUBJECT
    + r"|\b(?:recipe|instructions|blueprint|guide|formula|plans?|steps?)\s+(?:for|to\s+(?:make|build|"
    r"construct|assemble|engineer))\s+(?:a\s+|an\s+)?" + _WEAPON_SUBJECT
    + r"|\b" + _WEAPON_SUBJECT + r"\s+for\s+release\b",
    re.IGNORECASE,
)

# 3) CSAM — unambiguous literal terms + acquisition/generation requests for sexual imagery of minors.
#    Codex diff-gate iter-3: "get explicit pictures of underage girls", "where to find underage nudes",
#    "generate nude images of a 13 year old" were missed. Any hit -> harmful (no legitimate frame).
_MINOR = (
    r"(?:minors?|child(?:ren)?|kids?|underage|under-?age|prepubescent|teen(?:age|ager)?s?|"
    r"\b(?:a\s+)?\d{1,2}[-\s]?year[-\s]?olds?\b|girls?|boys?)"
)
# CSAM ACQUISITION / GENERATION (imperative) — NEVER rescued by any frame (Codex diff-gate iter-4:
# "show me underage nudes"). Both word orders.
_CSAM_ACQUISITION = re.compile(
    r"\b(?:get|find|where\s+to\s+(?:find|get|buy)|download|generate|create|make|produce|share|access|"
    r"show\s+me|view|stream|trade|sell|buy)\b"
    r".{0,30}?\b(?:nudes?|naked|explicit|sexual|porn\w*)\b.{0,20}?\b(?:of\s+)?" + _MINOR
    + r"|\b(?:get|find|where\s+to\s+(?:find|get|buy)|download|generate|create|make|produce|share|access|"
    r"show\s+me|view|stream|trade|sell|buy)\b"
    r".{0,30}?\b" + _MINOR + r"\b.{0,15}?\b(?:nudes?|naked|explicit|sexual|porn\w*)\b"
    r"|\b(?:nudes?|naked|explicit|sexual|porn\w*)\b.{0,20}?\bof\s+(?:a\s+|an\s+)?" + _MINOR
    + r"|\b(?:get|find|where\s+to\s+(?:find|get|buy)|download|access|view|trade|sell|buy|show\s+me)\b"
    r".{0,20}?\b(?:csam|child\s+porn\w*)\b",
    re.IGNORECASE,
)
# CSAM LITERAL reference — rescuable by a clinical / legal / policy / research SAFE frame anywhere
# (Codex diff-gate iter-4 over-refusal: "CSAM reporting laws", "clinical treatment of a child sexual
# abuse survivor", "epidemiology of child sexual abuse survivors" are legitimate).
_CSAM_LITERAL = re.compile(
    r"\b(?:child\s+sexual\s+abuse\s+material|csam|child\s+(?:porn(?:ography)?|sexual\s+abuse)|"
    r"(?:sexual(?:i[sz]e)?|nude|naked|explicit)\s+\w{0,12}?\s*(?:minor|child|underage|prepubescent)|"
    r"(?:minor|child|underage|prepubescent)\s+\w{0,12}?\s*(?:porn|sexual|nude|explicit))\b",
    re.IGNORECASE,
)
_CSAM_SAFE_GUARD = re.compile(
    r"\b(?:report\w*|laws?|legislat\w*|legal|policy|policies|mandatory\s+report\w*|prevent\w*|"
    r"treat\w*|therap\w*|clinical|epidemiolog\w*|prevalence|incidence|statistics|survivors?|victims?|"
    r"support|hotline|ncmec|investigat\w*|prosecut\w*|takedown|moderation|trust\s+and\s+safety|"
    r"detect\w*|hash(?:ing)?|safeguard\w*|protect\w*|awareness|education|recover\w*)\b",
    re.IGNORECASE,
)

# 4) SELF-HARM METHOD-SEEKING — method-seeking, NOT help/awareness. The help/awareness guard below
#    vetoes "suicide hotline", "prevention", "signs of", "help a friend who", "support".
_SELF_HARM_METHOD = re.compile(
    r"\b(?:how\s+(?:do\s+i|to|can\s+i)|best\s+way\s+to|easiest\s+way\s+to|fastest\s+way\s+to|"
    r"method[s]?\s+(?:to|of|for)|ways?\s+to|painless\s+way\s+to)\s+"
    r"(?:commit\s+suicide|kill\s+myself|end\s+my\s+life|end\s+it\s+all|take\s+my\s+(?:own\s+)?life|"
    r"hang\s+myself|overdose\s+(?:on\s+\w+\s+)?(?:to\s+die|and\s+die)|self[-\s]?harm|cut\s+myself)\b"
    r"|\bsuicide\s+method[s]?\b|\bhow\s+much\s+\w+\s+(?:to|will)\s+\w*\s*(?:overdose|be\s+lethal|kill\s+me)\b"
    # Codex diff-gate iter-4: direct first-person lethal-dose/overdose phrasing.
    r"|\b(?:dose|amount|quantity|how\s+much)\b.{0,40}?\b(?:would|to|that\s+would|will)\s+kill\s+me\b"
    r"|\bhow\s+much\s+\w+\s+(?:do\s+i\s+need\s+|to\s+|would\s+i\s+need\s+)(?:to\s+)?die\b"
    r"|\b(?:lethal|fatal|deadly)\s+(?:dose|amount)\s+(?:of\s+\w+\s+)?(?:for|to\s+kill)\s+(?:myself|me)\b"
    r"|\bwhat\s+would\s+kill\s+me\b",
    re.IGNORECASE,
)
# Self-harm RESEARCH / AWARENESS frame — only rescues when it LEADS (see _frame_leads). Codex diff-gate
# iter-3: a bare anywhere-match "support"/"resources" let "how to kill myself without my support network
# noticing" bypass. First-person method-seeking otherwise ALWAYS refuses-with-redirection (the redirect
# IS the help). Legit resource / third-party / awareness queries do not fire _SELF_HARM_METHOD at all.
_SELF_HARM_RESEARCH_GUARD = re.compile(
    r"\b(?:epidemiolog\w*|prevalence|incidence|statistics|rates?\s+of|research|study|studies|"
    r"news|article|report\w*|history\s+of|prevention\s+(?:program|programme|strateg|campaign)|"
    r"public\s+health)\b",
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
    r"(?:methamphetamine|crystal\s+meth|\bmeth\b|fentanyl|carfentanil|heroin|cocaine|\bmdma\b|"
    r"\blsd\b|\bghb\b|\bpcp\b)\b"
    r"|\bclandestine\s+(?:drug\s+)?(?:synthesis|lab|manufactur)"
    r"|\bsynthesis\s+route\s+(?:for|of)\s+(?:fentanyl|methamphetamine|meth|heroin|mdma|carfentanil|"
    r"cocaine|\blsd\b|\bghb\b|\bpcp\b)\b"
    r"|\bhow\s+to\s+(?:cook|make|synthesi[sz]e|manufacture)\s+(?:meth|methamphetamine|fentanyl|"
    r"crystal\s+meth|heroin|mdma|cocaine)\b",
    re.IGNORECASE,
)

# Prevention / policy / enforcement FRAME for the MAKE/BUILD categories (weaponization, illicit
# synthesis). Codex diff-gate iter-2 P1: bare evasion-prone tokens ("enforcement", "surveillance",
# "seizure", bare "stop") let "cook meth while avoiding law enforcement" / "synthesize fentanyl
# without triggering surveillance" bypass. This now requires genuine POLICY/PREVENTION STRUCTURE
# (policy / regulation / treaty / nonproliferation / harm-reduction nouns; "prevent ... from making";
# "reduce|disrupt|combat ... production"), AND the classifier requires the frame to LEAD the harm
# clause (see _frame_leads) so a TRAILING evasion phrase can never rescue a how-to request.
_ACTION_PREVENTION_GUARD = re.compile(
    # GOVERNING policy/prevention structures only (Codex diff-gate iter-3: standalone "policy research:"
    # / "for policy analysis," prefixes let a how-to-synthesize/build imperative bypass). Each form
    # GOVERNS the harm as its object — "prevent ... from making", "reduce|disrupt ... production",
    # a policy noun + a governing verb. A loose leading policy noun alone no longer rescues.
    r"\bprevent\w*\s+(?:people|the\s+public|others|them|the\s+spread\s+of|access\s+to|"
    r"\w+\s+from\s+(?:making|producing|manufactur|synthesi|building|developing|acquiring))"
    r"|\b(?:reduce|disrupt|combat\w*|curb|tackle|ban|banning|restrict\w*|stop|stem|interdict\w*|"
    r"intercept)\s+(?:the\s+)?(?:illicit\s+|illegal\s+)?(?:production|traffick\w*|spread|proliferat\w*|"
    r"manufactur\w*|supply|distribution|smuggling)\b"
    r"|\b(?:public\s+health|policy|regulatory|legislative|law\s+enforcement|harm[-\s]reduction|"
    r"nonproliferation|non-?proliferation|treaty|epidemiolog\w*)\s+"
    r"(?:program|programme|initiative|intervention|strateg|effort|measure|approach|response|"
    r"framework|campaign)s?\b",
    re.IGNORECASE,
)


# Clause separators — a care/prevention frame does NOT govern a harm clause across one of these
# (Codex diff-gate iter-4: "clinical management: what dose would kill my roommate" / "policy program:
# how to synthesize fentanyl" — a colon-prefixed frame is detached, not governing).
_CLAUSE_SEPARATOR = re.compile(r"[:;.?!–—\n]|\s-\s")


def _frame_leads(harm_match: re.Match[str], guard: re.Pattern[str], q: str) -> bool:
    """True iff a care/prevention frame GOVERNS the harm clause — it must START BEFORE the harm match
    (Codex iter-2: a TRAILING incidental word must not veto) AND there must be NO clause separator
    between the frame and the harm (Codex iter-4: a detached "clinical management:" / "research:"
    prefix does not govern an imperative harm clause). Only a genuinely governing frame vetoes."""
    for g in guard.finditer(q):
        if g.start() < harm_match.start():
            gap = q[g.end():harm_match.start()]
            if not _CLAUSE_SEPARATOR.search(gap):
                return True
    return False


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

        # Self-harm: first-person method-seeking refuses-with-redirection UNLESS a research/awareness
        # frame LEADS (a trailing "support network" no longer rescues — Codex diff-gate iter-3).
        _m = _SELF_HARM_METHOD.search(q)
        if _m and not _frame_leads(_m, _SELF_HARM_RESEARCH_GUARD, q):
            return HarmDecision(True, "self_harm_method", 0.9, ["self_harm_method_seeking"])

        # Lethal-against-persons: explicit intent AND no care/management frame LEADING the kill clause.
        _m = _LETHAL_INTENT.search(q)
        if _m and not _frame_leads(_m, _LETHAL_CARE_GUARD, q):
            return HarmDecision(
                True, "lethal_intent_against_persons", 0.9,
                ["lethal_intent_against_persons_explicit_intent"],
            )
        # Generic un-targeted lethal ("overdose to cause death") — human implied; vetoed by an explicit
        # non-person target (science) or a leading care frame.
        _m = _LETHAL_GENERIC.search(q)
        if _m and not _NONPERSON_TARGET.search(q) and not _frame_leads(_m, _LETHAL_CARE_GUARD, q):
            return HarmDecision(
                True, "lethal_intent_against_persons", 0.9, ["lethal_generic_cause_death"],
            )

        # Weaponization: make/build ACTION AND no policy/prevention frame governing it. Benign
        # compounds ("bath bomb", "bomb calorimeter") are stripped before matching (Codex iter-4).
        _q_w = _BENIGN_BOMB.sub("  ", q)
        _m = _WEAPONIZATION.search(_q_w)
        if _m and not _frame_leads(_m, _ACTION_PREVENTION_GUARD, _q_w):
            return HarmDecision(True, "weaponization", 0.9, ["weaponization_explicit_intent"])

        # Illicit synthesis: synthesis verb / recipe AND no policy/prevention frame governing it.
        _m = _ILLICIT_SYNTHESIS.search(q)
        if _m and not _frame_leads(_m, _ACTION_PREVENTION_GUARD, q):
            return HarmDecision(True, "illicit_synthesis", 0.9, ["illicit_synthesis_explicit_intent"])

        # CSAM: an ACQUISITION/generation imperative is never rescued; a LITERAL reference is rescued
        # only by a clinical/legal/policy/research safe frame (Codex iter-4).
        if _CSAM_ACQUISITION.search(q):
            return HarmDecision(True, "csam", 0.9, ["csam_acquisition"])
        if _CSAM_LITERAL.search(q) and not _CSAM_SAFE_GUARD.search(q):
            return HarmDecision(True, "csam", 0.9, ["csam_literal_no_safe_frame"])

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
