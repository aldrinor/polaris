"""
FIX-176: Full-Report Chain-of-Thought (CoT) Scrubber

Single authoritative CoT pattern list replacing fragmented defenses across
output_quality_gate.py, citefirst_synthesizer.py, and graph.py.

Run #11 deep audit found 31% CoT leakage (54/173 lines) — LLM working
document leaked as report text. This module consolidates all CoT patterns
into one place and provides three scrubbing functions:

1. scrub_cot_lines() — Line-level removal (anchored ^...$)
2. scrub_cot_inline() — Within-line fragment removal
3. scrub_cot_from_report() — Convenience wrapper applying both

FIX-196: Citation-blind CoT detection. Run #13 found 85% CoT contamination
because the LLM embeds [CITE:xxx] tokens into reasoning text, bypassing all
defenses that exempted lines with citations. Fix: strip citations from a COPY
of each line before pattern matching, so CoT is detected regardless of
embedded citations.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# FIX-196: Citation stripping regex (used to create citation-free copies)
# =============================================================================
_CITE_STRIP_RE = re.compile(r'\[CITE:[^\]]*\]')

# =============================================================================
# Line-Level CoT Patterns (anchored with ^ and $ in MULTILINE mode)
# =============================================================================
# These patterns match ENTIRE lines that are LLM self-talk, not domain content.
# Anchoring at ^ means "Let me check the EPA database" as domain content
# within a sentence won't be matched (it wouldn't start the line).

_COT_LINE_PATTERNS = [
    # --- Consolidated from output_quality_gate.py and citefirst_synthesizer.py ---
    r"^Let me (try|check|reach|count|think|ensure|verify|see|look|read|now|refine|analyze|examine|review|consider|summarize|organize|structure|assess|evaluate|compile|address|outline)\b.*$",
    r"^I will (now|try|write|check|generate|create|produce|compose|draft)\b.*$",
    r"^I need to\b.*$",
    r"^I should\b.*$",
    r"^Now (I|let|let's|we)\b.*$",
    r"^Okay,?\s+(let|so|I).*$",
    r"^First,?\s+I\b.*$",
    r"^Actually,?\s+.*$",
    r"^Wait,?\s+.*$",
    r"^Looking at\s+.*$",
    r"^The evidence\s+(says|provided|suggests|indicates|shows)\b.*$",
    r"^Hmm,?\s+.*$",
    r"^So,?\s+(?:the|this|I|we|let)\b.*$",

    # --- NEW for Run #11 specific leakage ---
    r"^Sentence \d+\s*:.*$",
    r"^Requirements?\s*:.*$",
    r"^That's \d+.*$",
    r"^Let me refine\s*:?.*$",
    r"^\d+\.\s+(Let me|I will|I need|Check)\b.*$",
    r"^(Draft|Attempt|Version)\s*\d+.*$",
    r"^(Better|Maybe|Perhaps)\s*:.*$",
    r"^But the user\b.*$",
    r"^The user (asks|wants|requires)\b.*$",
    r"^Since (I cannot|the evidence)\b.*$",
    r"^Groupings?\s*:.*$",
    r"^Could I write\s*:?.*$",
    r"^-\s+(no numbers|already cited|need)\b.*$",
    r"^(Similarly|For example)\s*:.*$",
    r"^Claim\s*:.*$",
    r"^Checking\s*:.*$",
    r"^(Note|Notice)\s*:.*$",

    # --- FIX-187: KIMI K2.5 specific patterns (Run #12) ---
    r"^\[\d+\]\s*(Constraints?|Must begin|Must cite|Must include|Should include)\s*:?.*$",
    r"^Possible combinations?\s*:.*$",
    r"^My sentence\s*\[\d+\].*$",
    r"^Evidence (provided|says|indicates|from)\s*:.*$",
    r"^Key (information|points?|findings?|facts?)\s*:.*$",
    r"^Here('s| is) (my|the) (attempt|paragraph|response|output)\s*:?.*$",
    r"^(Output|Result|Response)\s*:.*$",
    r"^-\s+(Must|Should|Need to|Can|Cannot)\s+\b.*$",
    r"^-\s+(use|include|avoid|don't)\s+\b.*$",
    r"^(I|We) (can|could|should|must|need)\s+\b.*$",
    r"^(Step|Phase|Part)\s+\d+\s*:.*$",
    r"^(Final|Revised|Updated)\s+(version|output|sentence|paragraph)\s*:?.*$",
    r"^(Combining|Merging|Integrating)\s+(evidence|sources|information)\s*:?.*$",
    r"^(Available|Relevant|Cited)\s+(evidence|sources)\s*:.*$",

    # --- FIX-196C: Run #13 patterns (CoT with citations) ---
    r"^This works\b.*$",
    r"^That works\b.*$",
    r"^Constraints?\s*(on|:)\b.*$",
    r"^But (to get|the research|the evidence|strictly|looking|I need|it|I must|wait)\b.*$",
    r"^Check(ing)?\s+citations?\b.*$",
    r"^It'?s a (compound|single|complex|multi)\s+claim\b.*$",
    r"^Alternative approach\b.*$",
    r"^Must cite\b.*$",
    r"^Only \d+\s+(pieces?|evidence|sources)\b.*$",
    r"^Need \d+\s+(sentences?|citations?|claims?|more)\b.*$",
    r"^Current text\b.*$",
    r"^Each sentence\b.*$",
    r"^One claim (about|regarding|for)\b.*$",
    r"^Two claims?\b.*$",
    r"^Or\s*:\s*\".*$",
    r"^\(Is this\b.*$",
    r"^\(Assuming\b.*$",
    r"^\(One claim\b.*$",
    r"^\(But\b.*$",
    r"^And I need\b.*$",
    r"^However,?\s+(looking|I|the|this|it)\b.*$",
    r"^Focus EXCLUSIVELY\b.*$",
    r"^The instruction\b.*$",
    r"^But rule \d+\b.*$",
    r"^Rule \d+\b.*$",
    r"^\d+\.\s+\".*\"\s*-\s*\d+\s+claim.*$",
    r"^\d+\.\s+and\b.*$",

    # --- FIX-196E: Run #13 residual patterns (post mega-line split analysis) ---
    # Bare numbered markers (just "8." or "11." on a line)
    r"^\d+\.\s*$",
    # Arrow annotations from LLM reasoning ("-> Relevant.", "-> Metadata.")
    r"^->\s+.*$",
    # Evidence bracket lines ("[]: Bottled water meeting...")
    r"^\[\]\s*:.*$",
    # Expanded "So" starter (catches "So if I", "So strictly", "So this is")
    r"^So\s+(if|strictly|this|that)\b.*$",
    # Task planning imperatives (Discuss/Connect/Introduce as line start)
    r"^(Connect|Discuss|Introduce|Mention|Include|Describe|Explain|Summarize|Address|Compare|Contrast|Highlight|Emphasize)\s+(to|the|that|how|why|this|whether|if|about|which|consumption|contamination)\b.*$",
    # Meta-commentary about claims/citations/sentences
    r"^(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve)\s+(citation|claim|sentence|point|fact)s?\.?\s*$",
    # Synthesis/meta labels
    r"^(Synthesis|Summary|Overview|Analysis)\s+(sentence|paragraph|section)\.?\s*$",
    # Evidence assessment ("The evidence is about...", "The evidence doesn't...")
    r"^The evidence\s+(is|doesn't|does|cannot|can|only|lacks)\b.*$",
    r"^The other\s+(evidence|source)\b.*$",
    r"^The research question\b.*$",
    # Self-assessment ("This might be off-topic", "Potentially yes")
    r"^This might\b.*$",
    r"^(Potentially|Therefore|Consequently|Hence|Thus),?\s+.*$",
    # "About preferences", "About the..." as meta-topic reference
    r"^About\s+(preferences|the|this|that|whether)\b.*$",
    # "Another point about..."
    r"^Another\s+(point|thing|issue|aspect|claim|sentence)\b.*$",
    # Prompt echo: "5. Must NOT start with..."
    r"^\d+\.\s+Must\s+(NOT|not|begin|cite|include)\b.*$",
    # "Identifies the specific..." meta-reference
    r"^(Identifies|Specifies|Describes|References|Mentions)\s+the\s+(specific|main|primary|key)\b.*$",
    # "They are all general statements..."
    r"^They are\s+(all|both|each|general)\b.*$",
    # Assessment of relevance or topic
    r"^(Relevant|Irrelevant|Off-topic|On-topic)\s+(to|for|because)\b.*$",
    # "for NORTH AMERICA" fragment (prompt echo)
    r"^for\s+[A-Z]{2,}\s+[A-Z]{2,}.*$",
    # Quote prefix patterns ("Furthermore, most U.S.")
    r"^\"Furthermore,\b.*$",
    # "Given the evidence provided..."
    r"^Given the evidence\b.*$",
    # "The user says/wants/provided..."
    r"^The user (says|wants|provided|asks|requires)\b.*$",
    # "Sentence N (Topic):" with parenthetical
    r"^Sentence \d+\s*\(.*$",
    # "Begin with a topic sentence..."
    r"^Begin with\b.*$",
    # "I think the safest/best/most..."
    r"^I think\b.*$",
    # "Then I can discuss..."
    r"^Then I can\b.*$",
    # "Write using the provided..."
    r"^Write using\b.*$",
    # "Perhaps the context/logic/safest..."
    r"^Perhaps\s+(the|this|I|it|we)\b.*$",
    # "The connection to..." meta-reference
    r"^The connection to\b.*$",
    # "If I say..." self-talk
    r"^If I (say|write|use|include|mention)\b.*$",
    # "The .* context might be..." meta-discussion
    r"^The\s+\"?[a-z]+\s+(water\s+)?[a-z]+\"?\s+context\b.*$",
    # "Academic and reference laboratories..." — prompt echo fragment
    r"^\"?Academic and reference\b.*$",
    # "Alternatively, perhaps/maybe..."
    r"^Alternatively,?\s+(perhaps|maybe|I|the)\b.*$",
    # Bullet claim annotations ("- Claim 3: ...")
    r"^-\s+Claim\s+\d+\s*:.*$",
    # "If the evidence says..."
    r"^If the evidence\b.*$",
    # "According to the source..." (meta-framing, not "According to Smith et al")
    r"^According to the (source|evidence|provided)\b.*$",
    # "Example: ..." prefix for draft examples
    r"^Example\s*:\s+.*$",
    # "Is this in the evidence?" self-questioning
    r"^Is this\s+(in|from|the|what)\b.*$",
    # "Skip evidence about..." prompt echo
    r"^Skip evidence\b.*$",
    # "Or I could..." self-planning
    r"^Or I could\b.*$",
    # "It seems to be..." meta-assessment
    r"^It (seems|appears|looks|only)\b.*$",
    # "This is ambiguous/a requirement..." meta-assessment
    r"^This is\s+(ambiguous|a requirement|unclear|the same|general|about)\b.*$",
    # "Building on the analysis of..." section transition prompt echo
    r"^Building on the analysis\b.*$",
    # "NORTH AMERICA could mean..." prompt interpretation
    r"^[A-Z]{2,}\s+[A-Z]{2,}\s+(could|would|might|should)\b.*$",
    # Evidence bracket annotations: "- []: ..." or "[]: ..."
    r"^-?\s*\[\]\s*:.*$",
    # Relevance annotations: "- Relevant:" or "- Irrelevant:"
    r"^-?\s*(Relevant|Irrelevant)\s*:.*$",
    # "WHO is global." meta-context about organizations
    r"^(WHO|EPA|NSF|CDC)\s+(is|are)\s+(global|national|international|the)\b.*$",

    # --- FIX-266: Instruction-echo patterns (Run #18 CoT leakage) ---
    # LLM echoes its synthesis instructions into output text.
    r"^Given the strict instruction\b.*$",
    r"^I must write\b.*$",
    r"^I only have\s+\d+\b.*$",
    r"^The content stays grounded\b.*$",
    r"^I should indicate\b.*$",
    r"^I should write\b.*$",
    r"^I cannot invent\b.*$",
    r"^I am instructed\b.*$",
    r"^I was told to\b.*$",
    r"^The provided evidence describes\b.*$",
    r"^The provided evidence contains\b.*$",
    # Numbered sub-reasoning like "2a." at line start
    r"^\d+[a-z]\.\s+.*$",

    # --- FIX-198: Run #14 patterns (massive CoT leakage in revision loop) ---
    # "The user explicitly says..." — word(s) between "user" and verb
    r"^The user\b.*\b(says|wants|asks|explicitly|provided)\b.*$",
    # "Write a coherent paragraph..." — instruction echo
    r"^Write\s+(a|the|this|my|an)\b.*$",
    # "Without knowing what..." — uncertainty preamble
    r"^Without (knowing|seeing|reading|understanding)\b.*$",
    # "Given the context/instruction/explicit..." — meta-framing
    r"^Given the (context|instruction|explicit|constraints?|section|evidence|research)\b.*$",
    # "Cite 2-3 evidence pieces..." — instruction echo
    r"^Cite\s+\d+.*$",
    # "This is partially..." — meta-assessment
    r"^This is\s+(partially|mostly|specifically|apparently|clearly|essentially|basically|pretty)\b.*$",
    # "Must connect/begin/use/include..." (bare, not bullet)
    r"^Must\s+(connect|begin|use|include|cite|NOT|not|have|add)\b.*$",
    # "In such cases..." — meta-reasoning
    r"^In such cases\b.*$",
    # "Another interpretation..." — meta-analysis
    r"^Another\s+(interpretation|approach|way|option|possibility)\b.*$",
    # "Better not..." — self-talk
    r"^Better not\b.*$",
    # "Better:" on its own
    r"^Better\s*:.*$",
    # "These are different/similar/related" — meta-assessment
    r"^These are\s+(different|similar|related|the same|all|both)\b.*$",
    # "Maybe mention/add/keep/combine..." — planning
    r"^Maybe\s+(mention|add|combine|include|keep|use|I|the|not|it|this)\b.*$",
    # "Good." or "Good," or "Good -" — self-assessment
    r"^Good\s*[.,\-].*$",
    r"^Good\.\s*$",
    # "Or keep/mention/maybe/just..." — planning
    r"^Or\s+(keep|mention|maybe|just|we|I|the|combine|perhaps)\b.*$",
    # Parenthetical meta-labels: "(General claim, relevant)"
    r"^\(?(General|Specific|Background|Meta|Main|Overall|Partial)\s+(claim|statement|info|context|relevance)\b.*$",
    # Bibliographic metadata in prose: "- The DOI/PMCID/PMID for..."
    r"^-?\s*The\s+(DOI|PMCID|PMID|article|review)\s+(for|was|is|received)\b.*$",
    # "The section I'm writing..." — meta-reference
    r"^The section\s+(I'm|I am|is|we're)\b.*$",
    # "This seems like..." — meta-assessment
    r"^This seems\b.*$",
    # "I already..." — self-reference
    r"^I already\b.*$",
    # "I should be careful/probably/only..." — self-instruction
    r"^I should (be|probably|only|not|just|include|exclude|skip)\b.*$",
    # "If I provide 0/1/N sentences..." — self-reasoning
    r"^If I (provide|give|write|produce|use|add|include|just)\b.*$",
    # "Still \d+. Need..." — counting
    r"^Still\s+\d+\b.*$",
    # "Need a third/another/more..." — planning
    r"^Need\s+(a|another|more|the|to)\b.*$",
    # "That works" with qualification
    r"^That works\b.*$",
    # Yes/No meta-answers at line start
    r"^(Yes|No)\s*[,:]\s+(the|this|I|it|we|but|\")\b.*$",
    # "- The review was published..." — bibliographic prose
    r"^-?\s*The review\s+(was|is|analyzed)\b.*$",
    # "- Approximately NN studies..." as bullet meta-data
    r"^-?\s*Approximately\s+\d+\s+studies\b.*$",
    # "- The article received..." — bibliographic
    r"^-?\s*The article\s+(received|was|is|has)\b.*$",
    # "Could mean..." / "Would logically..." meta-interpretation
    r"^(Could|Would|Should|Might)\s+(mean|logically|this|it|the)\b.*$",
    # Bare citation lines (only citation tokens, no text after stripping)
    r"^A\.\s*$",
    # "The Mexico data is..." — meta-reference
    r"^The\s+\w+\s+data\s+(is|are|was|seems)\b.*$",
    # Section transition meta: "this section examines..."
    r"^(This|The)\s+section\s+(examines|discusses|reviews|covers|focuses|addresses|analyzes|explores)\b.*$",
]

# Compile once for performance
_COT_LINE_RE = re.compile(
    "|".join(f"({p})" for p in _COT_LINE_PATTERNS),
    re.MULTILINE | re.IGNORECASE,
)

# =============================================================================
# FIX-225: Lite-mode patterns — unambiguous CoT that NEVER appears in research
# =============================================================================
# With FIX-220 structural reasoning/content separation, the full 280-pattern
# scrubber is no longer the primary defense. These 15 patterns catch only the
# most obvious behavioral CoT leakage as a thin safety net.
_COT_LINE_PATTERNS_LITE = [
    r"^<think>.*$",
    r"^</think>.*$",
    r"^Let me (try|check|think|verify|refine|analyze|review|consider)\b.*$",
    r"^I will (now|try|write|check|generate|create)\b.*$",
    r"^I need to\b.*$",
    r"^I should\b.*$",
    r"^Now (I|let|let's)\b.*$",
    r"^Okay,?\s+(let|so|I).*$",
    r"^Wait,?\s+.*$",
    r"^Hmm,?\s+.*$",
    r"^Sentence \d+\s*:.*$",
    r"^(Draft|Attempt|Version)\s*\d+.*$",
    r"^The user (asks|wants|requires)\b.*$",
    r"^But the user\b.*$",
    r"^Could I write\s*:?.*$",
    # FIX-266: Instruction-echo patterns (unambiguous, safe for lite mode)
    r"^Given the strict instruction\b.*$",
    r"^I must write\b.*$",
    r"^I only have\s+\d+\b.*$",
    r"^The content stays grounded\b.*$",
    r"^I cannot invent\b.*$",
    r"^I am instructed\b.*$",
    r"^I was told to\b.*$",
    r"^The provided evidence describes\b.*$",
    r"^The provided evidence contains\b.*$",
    r"^\d+[a-z]\.\s+.*$",
]

_COT_LINE_RE_LITE = re.compile(
    "|".join(f"({p})" for p in _COT_LINE_PATTERNS_LITE),
    re.MULTILINE | re.IGNORECASE,
)

# =============================================================================
# Inline CoT Patterns (match fragments within a line)
# =============================================================================
# These catch CoT that appears AFTER valid content (e.g., after a citation).

_COT_INLINE_PATTERNS = [
    # Match CoT AFTER citation — use lookbehind to preserve the [CITE:xxx] token
    r"(?<=\])\s+(Let me|I will|I need|Requirements|That's \d).*$",
    r"\bsuggesting that an atomic claim\b.*$",
    r"\bthe claim to express\b",
    r"\bthe original sentence\b",

    # FIX-196C: Run #13 inline patterns
    # Parenthetical reasoning after a sentence
    r"(?<=\.)\s*\(Is this claim\b.*$",
    r"(?<=\.)\s*\(Assuming\b.*$",
    r"(?<=\.)\s*\(One claim\b.*$",
    r"(?<=\.)\s*\(But\b.*$",
    # Trailing claim/citation metadata: " - 1 claim, 1 citation."
    r"\s+-\s+\d+\s+claims?,\s*\d+\s+citations?\.?\s*$",
    # Trailing parenthetical: "(these are contrasting types)"
    r"\s+\(these are\b.*$",
    r"\s+\(this is\b.*$",
    # "So this is combining" fragments
    r"(?<=\.)\s+So this is\b.*$",
    # FIX-196E: Trailing CoT after valid sentence
    # "Sentence 6: Many WDs..." trail
    r"\s+Sentence\s+\d+\s*:.*$",
    # "That's 6 sentences." trail
    r"\s+That's\s+\d+\s+sentences?\.?\s*$",
    # "CDC reporting." trail (meta-label)
    r"\s+(CDC|WHO|EPA)\s+reporting\.?\s*$",
    # Trailing numbered marker: ". - 1." or ". - 2." (draft count)
    r"\.\s+-\s+\d+\.\s*$",
    # Trailing count: "That's four.", "That's one sentence.", "That's 6."
    r"\s+That's\s+(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b[^.]*\.?\s*$",
]

# =============================================================================
# FIX-196E: Meta-phrase patterns (match ANYWHERE in a line, not just start)
# =============================================================================
# These phrases are unambiguous CoT — they never appear in real report text.
# Used by the structural heuristic Rule 6 to catch meta-discussion regardless
# of line length or starting pattern.
_META_PHRASE_PATTERNS = [
    r'\d+\s+claims?,\s*\d+\s+citations?',       # "1 claim, 1 citation"
    r'topic sentence',                            # meta-reference to sentence role
    r'connecting to (the\s+)?(previous|preceding)',  # section transition planning
    r'the user (says|wants|provided|asks)',       # meta-reference to prompt
    r'i think the safest',                        # self-deliberation
    r'write using the provided',                  # task instruction echo
    r'check citations?\s+(per|for)',              # self-instruction
    r'given the evidence provided',               # meta-framing
    r'the broader context of the report',         # meta-reference
    r'this specific section is about',            # meta-reference
    r'the evidence might be (considered|relevant)',  # meta-assessment
    r'perhaps the (context|logic) implies',       # meta-reasoning
    r'i can maybe combine',                       # self-planning
    r'not directly relevant',                     # meta-assessment
    r'the evidence doesn\'t (explicitly|mention)', # meta-assessment
    r'assuming it is relevant',                   # meta-assumption
    r'which ended with:',                         # section linking instruction
    r'the user wants me to',                      # meta-reference
    r'is relevant to understanding',              # meta-assessment
    r'might be the broader context',              # meta-reasoning
    r'provide(d|s) this evidence',                # meta-reference
    r'i cannot write the paragraph',              # self-admission
    r'the user (likely|expects|probably)',         # meta-reference
    r'according to the source',                   # meta-framing (vs "according to Smith et al")
    r'the same claim phrased',                    # meta-assessment
    r'if the evidence says',                      # meta-conditional
    r'sentence \d+ adds',                         # meta-annotation
    r'they only provide information',             # meta-assessment
    r'these are the same claim',                  # meta-assessment
    r'phrased differently',                       # meta-assessment
    r'the evidence says\s+"',                     # meta-quoting
    r'general pathogen information',              # meta-context
    r'expecting me to',                           # meta-reference
    r'expecting me to synthesize',                # meta-reference
    r'the regulatory foundation',                 # meta-context (common prompt echo)
    r'it doesn\'t explicitly (say|state|mention)', # meta-assessment
    r'is this in the evidence',                   # self-questioning
    r'this is ambiguous',                         # meta-assessment
    r'the strict rule',                           # prompt echo
    r'skip evidence about',                       # prompt echo
    r'would logically discuss',                   # meta-planning
    r'it seems to be (general|about|a)',          # meta-assessment
    r'or i could group',                          # self-planning
    r'could mean the content must',               # prompt interpretation
    r'could mean i should',                       # prompt interpretation
    r'this is a requirement',                     # meta-assessment
    r'i strictly follow',                         # meta-deliberation
    r'i cannot produce \d+',                      # self-admission
    r'i should only include',                     # self-instruction
    r'the priority is to',                        # meta-prioritization
    r'it only describes',                         # meta-assessment
    r'the evidence just says',                    # meta-assessment
    r'just says .* are',                          # meta-assessment
    r'evidence specific to .* is scarce',         # meta-assessment
    r'different geographic region',               # meta-assessment
    r'different subject matter',                  # meta-assessment
    r'unrelated topic',                           # meta-assessment
    r'focus exclusively',                         # prompt echo
    r'specific instruction',                      # prompt echo
    r'i think the priority',                      # self-deliberation
    r'general medical.*information',              # meta-assessment
    r'that\'s (one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b', # counting
    # FIX-198: Run #14 meta-phrases
    r'the user explicitly says',             # prompt echo
    r'write a coherent paragraph',           # instruction echo
    r'section header in the report',         # meta-reference
    r'violate the output format',            # self-reasoning
    r'cite-first research synthesizer',      # role awareness
    r'prioritize evidence fidelity',         # self-instruction
    r'i should be careful',                  # self-caution
    r'i should probably include',            # self-planning
    r'need a third',                         # planning
    r'need 3rd',                             # planning
    r'still \d+\.\s*need',                   # counting + planning
    r'that works.*though',                   # self-assessment with qualifier
    r'better not force',                     # self-talk
    r'let me check if',                      # self-instruction
    r'maybe mention',                        # planning
    r'maybe combine',                        # planning
    r'i already used',                       # self-reference
    r'must connect to previous',             # section planning
    r'must use inline',                      # instruction echo
    r'the doi for',                          # bibliographic meta
    r'the pmcid for',                        # bibliographic meta
    r'the pmid for',                         # bibliographic meta
    r'in such cases.*constraint',            # meta-reasoning
    r'another interpretation',               # meta-analysis
    # NOTE: "building on the analysis of" intentionally EXCLUDED — it's a valid template transition
    r'this section examines',                # section transition meta
    r'without knowing what',                 # uncertainty reasoning
    r'the evidence describes',               # meta-assessment
    r'while it doesn\'t give',              # meta-assessment
    r'partially relevant but',              # meta-assessment
    r'general claim',                        # meta-labeling
    r'the section i\'m writing',            # meta-reference
    r'if i provide \d+',                    # self-reasoning
    r'these are different',                  # meta-assessment
    r'cite \d+-\d+ evidence',               # instruction echo
    r'the research question',                # meta-reference
    r'given the explicit instruction',       # meta-framing
    r'rule \d+ (and|say|says)',             # prompt reference
    r'rule \d+ say',                        # prompt reference
    # FIX-266: Instruction-echo meta-phrases (Run #18 CoT leakage)
    r'given the strict instruction',        # instruction echo
    r'i must write',                        # instruction echo
    r'i only have \d+ sentences?',          # counting self-talk
    r'the content stays grounded',          # meta-assessment
    r'i should indicate',                   # self-instruction
    r'i cannot invent',                     # self-admission
    r'i am instructed',                     # instruction echo
    r'i was told to',                       # instruction echo
    r'the provided evidence describes',     # meta-framing
    r'the provided evidence contains',      # meta-framing
    r'grounded in evidence',               # instruction echo
    r'grounded in the provided',           # instruction echo
    r'without inventing',                   # instruction echo
    r'i should not (invent|fabricate|make up)', # self-instruction
    # FIX-201A: Evidence analysis note patterns (Run #15 root causes)
    r'none (of them )?mention\b',           # "None mention water, filters..."
    r'none of the(se)?\s+evidence',         # "none of the evidence provided"
    r'does not (discuss|mention|address|cover)', # "It does not discuss water filters"
    r'doesn\'t (discuss|cover|address)',    # contraction form
    r'the evidence discusses',              # "The evidence discusses hospital infections"
    r'the evidence is irrelevant',          # meta-assessment
    r'the evidence (simply|just|only)\s+(list|describe|state|say)', # "evidence simply lists"
    r'if i output nothing',                 # "If I output nothing..."
    r'if that\'s the case',                 # "If that's the case..."
    r'another idea\s*:',                    # "Another idea: Maybe..."
    r'this is problematic',                 # "This is problematic."
    r'\bso yes\b',                          # "So yes, most have..."
    r'every sentence must',                 # "every sentence must have at least one citation"
    r'given the impossibility',             # "Given the impossibility of..."
    r'i cannot write',                      # "I cannot write the requested paragraph"
    r'is being discussed in the context',   # "So Legionella is being discussed..."
    r'to provide a response that',          # "to provide a response that follows..."
    r'adhering to constraints',             # "while adhering to constraints"
    r'general template instruction',        # "might be a general template instruction"
    r'in the evidence id',                  # "Maybe the p2 in the evidence ID"
    r'implicitly relevant',                 # "it is implicitly relevant"
    r'the impossibility of satisfying',     # constraint reasoning
    r'none of these\s+(mention|discuss|address|are about)', # meta-assessment
    r'the section is\s*["\']',             # 'And the section is "Legionella"'
    r'\bso\s+\w+\s+is\s+being\s+discussed', # "So Legionella is being discussed"
    r'the evidence is\s+(about|regarding|concerning)', # "the evidence is about hospital infections"
    r'i need to make sure',                 # "I need to make sure I'm citing..."
    r'north america specific',              # meta-context label
    r'general consumption',                 # meta-context label
    r'contamination risk despite',          # meta-context label
    r'motivation for use',                  # meta-context label
    r'sources of contamination\.',          # meta-context label (with period)
    # FIX-201F: Additional patterns from Run #15 evidence analysis notes
    r'doesn\'t say anything about',        # "It doesn't say anything about residential gaps"
    r'these don\'t (specify|mention|discuss)', # "These don't specify household water filters"
    r'also,?\s+mentions that',             # "Also, mentions that for most pathogens..."
    r'doesn\'t (explicitly )?mention',     # "doesn't explicitly mention"
    r'they establish that',                # "but they establish that Legionella grows..."
    r'is relevant to any',                 # "relevant to any water system"
    r'but none mention',                   # "But NONE mention household water filters"
    r'not specifically about',             # "not specifically about household"
    r'the chapter was published',          # bibliographic meta-note
    r'contains no information regarding',  # meta-assessment
    r'and contains no information',        # meta-assessment
]

_META_PHRASE_RE = re.compile(
    "|".join(f"({p})" for p in _META_PHRASE_PATTERNS),
    re.IGNORECASE,
)

_COT_INLINE_RE = re.compile(
    "|".join(f"({p})" for p in _COT_INLINE_PATTERNS),
    re.MULTILINE | re.IGNORECASE,
)


def _strip_citations(text: str) -> str:
    """FIX-196: Remove all [CITE:xxx] tokens from text for pattern matching."""
    result = _CITE_STRIP_RE.sub('', text)
    # Collapse multiple spaces left by citation removal
    result = re.sub(r'  +', ' ', result).strip()
    return result


def scrub_cot_lines(text: str) -> str:
    """
    Remove entire lines that match CoT patterns.

    FIX-196A: Citation-blind matching. Each line is tested TWICE:
    1. Original line against CoT patterns
    2. Citation-stripped copy against CoT patterns
    If EITHER matches, the line is removed. This catches CoT like
    "[CITE:ev_001] This works - one claim..." which becomes
    "This works - one claim..." after stripping, matching the pattern.

    Args:
        text: Report text potentially containing CoT lines.

    Returns:
        Text with CoT lines removed.
    """
    if not text:
        return text

    lines = text.split("\n")
    cleaned = []
    removed_count = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue

        # Original match (existing behavior)
        if _COT_LINE_RE.match(stripped):
            removed_count += 1
            continue

        # FIX-196A: Citation-blind match
        cite_stripped = _strip_citations(stripped)
        if cite_stripped and cite_stripped != stripped and _COT_LINE_RE.match(cite_stripped):
            removed_count += 1
            continue

        cleaned.append(line)

    if removed_count > 0:
        logger.info(f"[FIX-176] Scrubbed {removed_count} CoT lines from report")

    return "\n".join(cleaned)


def scrub_cot_inline(text: str) -> str:
    """
    Remove CoT fragments that appear within otherwise valid lines.

    For example: "[CITE:ev_001] Let me refine: ..." -> "[CITE:ev_001]"

    Args:
        text: Report text potentially containing inline CoT fragments.

    Returns:
        Text with inline CoT fragments removed.
    """
    if not text:
        return text

    result = _COT_INLINE_RE.sub("", text)

    if result != text:
        logger.info(f"[FIX-176] Scrubbed inline CoT fragments from report")

    return result


def scrub_structural_heuristic(text: str) -> str:
    """
    FIX-190: Structural catch-all for CoT lines not matching explicit patterns.
    FIX-196B: Now operates on citation-stripped text (citation-blind).

    Heuristic rules operate on text AFTER stripping [CITE:xxx] tokens:
    1. < 12 words AND no terminal punctuation AND not a heading -> REMOVE
    2. Bullet lines (- ...) < 15 words AND no terminal punctuation -> REMOVE
    3. Label-colon patterns < 15 words AND not a heading -> REMOVE

    Feature flag: POLARIS_COT_STRUCTURAL_HEURISTIC (default "1").
    """
    import os
    if os.environ.get("POLARIS_COT_STRUCTURAL_HEURISTIC", "1") != "1":
        return text

    if not text:
        return text

    lines = text.split("\n")
    cleaned = []
    removed_count = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue

        # FIX-196B: Operate on citation-stripped text
        cite_stripped = _strip_citations(stripped)
        if not cite_stripped or not cite_stripped.strip():
            # FIX-201E: Line was ONLY citations with no other text — REMOVE
            # These are citation-only lines like "[CITE:ev_xxx]" with no prose
            removed_count += 1
            continue

        word_count = len(cite_stripped.split())
        has_terminal = cite_stripped[-1] in '.!?'
        is_heading = stripped.startswith('#')
        has_cite = '[CITE:' in stripped
        words_lower = cite_stripped.lower()

        # Rule 1: Short lines without terminal punctuation
        if (word_count < 12
                and not has_terminal
                and not is_heading):
            removed_count += 1
            continue

        # Rule 2: Bullet lines without terminal punctuation
        if (cite_stripped.startswith('- ')
                and word_count < 15
                and not has_terminal
                and not is_heading):
            removed_count += 1
            continue

        # Rule 3: Label-colon patterns
        colon_pos = cite_stripped.find(':')
        if (colon_pos > 0
                and colon_pos > len(cite_stripped) * 0.3
                and word_count < 15
                and not is_heading):
            removed_count += 1
            continue

        # Rule 4 (FIX-196E): Lines containing unambiguous meta-phrases
        # These phrases NEVER appear in real report text — they are always
        # LLM reasoning/annotation regardless of line length or citations
        if _META_PHRASE_RE.search(words_lower):
            removed_count += 1
            continue

        # Rule 5 (FIX-201B): Parenthesized assessment lines
        # After citation stripping, lines that are entirely parenthesized
        # are evidence relevance assessments: "(Relevant to consumption patterns)"
        paren_stripped = cite_stripped.strip().rstrip('.')
        if (paren_stripped.startswith('(')
                and paren_stripped.endswith(')')
                and word_count < 20
                and not is_heading):
            removed_count += 1
            continue

        # Rule 5b (FIX-201F): Parenthesized-prefix assessment lines
        # Catches "(Relevant to X) - evidence text" or "(US is North America) - text"
        # These are LLM relevance annotations followed by evidence fragments
        if (cite_stripped.startswith('(')
                and ') -' in cite_stripped
                and word_count < 30
                and not is_heading):
            removed_count += 1
            continue

        # Rule 6 (FIX-201C): Evidence analysis bullets with terminal punctuation
        # Catches "- Taxonomy, not water filters." and "- Risk factors, not water filters."
        # These are evidence notes that have periods (so Rule 2 doesn't catch them)
        if (cite_stripped.startswith('- ')
                and word_count < 10
                and has_terminal
                and not is_heading):
            # Additional check: must NOT look like a bullet list in an exec summary
            # Real exec summary bullets have > 8 words typically
            if word_count < 8:
                removed_count += 1
                continue

        # Rule 7 (FIX-201D): Lines starting with "- []:" (empty citation brackets)
        # Pattern: "[N] - []: text" → after cite strip: "- []: text"
        if cite_stripped.startswith('- []:') or cite_stripped.startswith('- [ ]:'):
            removed_count += 1
            continue

        # Rule 8 (FIX-201G): Very short citation-prefixed fragments (< 4 words)
        # Catches fragments like "[CITE:xxx] pneumophila concentration estimates."
        # Only applies when citations were stripped (indicating evidence-prefixed lines).
        # Standalone short sentences without citations are preserved.
        had_citations_stripped = cite_stripped != stripped
        if (word_count < 4
                and has_terminal
                and not is_heading
                and not cite_stripped.startswith('- ')
                and had_citations_stripped):
            removed_count += 1
            continue

        cleaned.append(line)

    if removed_count > 0:
        logger.info(f"[FIX-190] Structural heuristic removed {removed_count} CoT-like lines")

    return "\n".join(cleaned)


def _split_mega_lines(text: str) -> str:
    """
    FIX-196D: Split mega-lines into sentence-level lines for scrubbing.

    The LLM concatenates entire sections onto single lines (7000+ chars).
    Line-level CoT patterns only see the start of each line, missing CoT
    buried mid-line. This inserts newlines at sentence boundaries so each
    sentence becomes its own line for pattern matching.

    Split points:
    - Before [CITE:xxx] tokens that follow a sentence ending (. ! ?)
    - Before numbered items (1. 2. etc.) that follow sentence endings
    - Before evidence bracket notation ([]:) that follow sentence endings
    """
    if not text:
        return text

    # Only process lines > 200 chars (mega-lines)
    lines = text.split("\n")
    result_lines = []
    for line in lines:
        if len(line) > 200:
            # Split before [CITE:] after sentence boundary (. or ] + space)
            split = re.sub(r'(?<=\.\s)\[CITE:', '\n[CITE:', line)
            split = re.sub(r'(?<=\]\s)\[CITE:', '\n[CITE:', split)
            # Split before numbered items after sentence boundary
            split = re.sub(r'(?<=\.\s)(\d+\.\s)', r'\n\1', split)
            # Split before evidence brackets after sentence boundary
            split = re.sub(r'(?<=\.\s)\[\]:', '\n[]:', split)
            # FIX-198: Split before bullet items ("- ") after sentence endings
            split = re.sub(r'(?<=\.\s)-\s+', '\n- ', split)
            # FIX-198: Split before capitalized sentence starts after ". "
            # Only if the following word starts an obvious new sentence
            split = re.sub(
                r'(?<=\.\s)(The user|Rule \d|Write |Given |Without |Maybe |But |However |Must |I should|I already|If I |Or |Good\.|Yes[,:]|No[,:])',
                r'\n\1', split
            )
            result_lines.append(split)
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


def scrub_cot_from_report(text: str) -> str:
    """
    Full CoT scrubbing: line removal + inline fragment removal + whitespace normalization.

    This is the primary entry point. Call this on any report text before finalization.

    FIX-225: When POLARIS_COT_SCRUBBER_LITE=1, uses a minimal 15-pattern safety net
    instead of the full 280-pattern + 480-meta-phrase + 8-rule scrubber. This is the
    correct mode when FIX-220 structural reasoning/content separation is active, because
    the full scrubber produces false positives on legitimate research prose (e.g.,
    "Given the research methodology..." matches CoT pattern "^Given the (research)...").

    Args:
        text: Raw report text from LLM synthesis.

    Returns:
        Cleaned report text with CoT removed and whitespace normalized.
    """
    if not text:
        return text

    lite_mode = os.environ.get("POLARIS_COT_SCRUBBER_LITE", "0") == "1"
    original_len = len(text)

    # Step 0: FIX-196D — Split mega-lines into sentence-level lines
    result = _split_mega_lines(text)

    if lite_mode:
        # FIX-225: Lite mode — only 15 unambiguous patterns, no heuristics
        result = _scrub_cot_lines_lite(result)
    else:
        # Full mode — 280 patterns + inline + structural heuristics
        result = scrub_cot_lines(result)
        result = scrub_cot_inline(result)
        result = scrub_structural_heuristic(result)

    # Step 3: Normalize whitespace (always runs)
    # Collapse 3+ consecutive blank lines into 2
    result = re.sub(r"\n{3,}", "\n\n", result)
    # Strip trailing whitespace per line
    result = "\n".join(line.rstrip() for line in result.split("\n"))
    # Strip leading/trailing blank lines from whole document
    result = result.strip()

    chars_removed = original_len - len(result)
    mode_label = "LITE" if lite_mode else "FULL"
    if chars_removed > 0:
        logger.info(
            f"[FIX-176] CoT scrubber ({mode_label}) removed {chars_removed} characters "
            f"({chars_removed / max(original_len, 1) * 100:.1f}% of report)"
        )
    elif lite_mode:
        logger.info(f"[FIX-225] CoT scrubber LITE mode: 0 characters removed (clean synthesis)")

    return result


def _scrub_cot_lines_lite(text: str) -> str:
    """
    FIX-225: Lite-mode line scrubber — only 15 unambiguous CoT patterns.

    Used when FIX-220 structural separation is active. These patterns catch only
    the most obvious behavioral CoT leakage (e.g., "<think>", "I should", "Wait,")
    that could never appear in legitimate research text.

    Args:
        text: Report text with potential behavioral CoT leakage.

    Returns:
        Text with unambiguous CoT lines removed.
    """
    if not text:
        return text

    lines = text.split("\n")
    cleaned = []
    removed_count = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue

        # Match against lite patterns (original text)
        if _COT_LINE_RE_LITE.match(stripped):
            removed_count += 1
            continue

        # FIX-196A: Citation-blind match (lite patterns only)
        cite_stripped = _strip_citations(stripped)
        if cite_stripped and cite_stripped != stripped and _COT_LINE_RE_LITE.match(cite_stripped):
            removed_count += 1
            continue

        cleaned.append(line)

    if removed_count > 0:
        logger.info(f"[FIX-225] Lite scrubber removed {removed_count} unambiguous CoT lines")

    return "\n".join(cleaned)
