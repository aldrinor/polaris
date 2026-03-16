"""
Long-Form Generation (KIMI K2.5 Parity)
========================================
Generates coherent documents up to 100K+ tokens.

KIMI K2.5 can generate 100K tokens in a single pass.
We achieve this through intelligent chunking with context preservation.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Section:
    """A document section."""
    title: str
    content: str
    word_count: int
    citations: List[str]
    subsections: Optional[List["Section"]] = None


class LongFormGenerator:
    """
    Long-form document generator.

    Generates reports up to 100K tokens with context continuity.
    """

    def __init__(
        self,
        max_tokens_per_chunk: int = 16000,
        overlap_tokens: int = 2000,
        target_total_tokens: int = 100000,
        enable_coherence_validation: bool = True,
        min_coherence_score: float = 0.7,
    ):
        self.max_chunk = max_tokens_per_chunk
        self.overlap = overlap_tokens
        self.target_total = target_total_tokens
        self.enable_coherence_validation = enable_coherence_validation
        self.min_coherence_score = min_coherence_score

        # Track generation state
        self.sections_generated: List[Section] = []
        self.total_tokens_generated = 0
        self.context_buffer = ""  # Maintains continuity

        # Coherence validator (initialized lazily)
        self._coherence_validator = None

    @property
    def coherence_validator(self):
        """Lazy-load coherence validator."""
        if self._coherence_validator is None:
            # Import here to avoid circular import at class definition time
            self._coherence_validator = CoherenceValidator(
                min_coherence_score=self.min_coherence_score
            )
        return self._coherence_validator

    def generate_document(
        self,
        outline: List[Dict],
        evidence: List[Dict],
        query: str,
    ) -> str:
        """
        Generate long-form document from outline and evidence.

        Args:
            outline: Document outline with section specs
            evidence: Available evidence for citations
            query: Original research query

        Returns:
            Generated document with coherence validation applied
        """
        from src.llm.kimi_client import get_kimi_client

        kimi = get_kimi_client(thinking=True)

        document_parts = []
        coherence_issues = []

        # Generate each section
        for section_spec in outline:
            section = self._generate_section(
                section_spec=section_spec,
                evidence=evidence,
                query=query,
                prior_sections=document_parts,
                kimi=kimi,
            )

            # Validate section coherence if enabled
            if self.enable_coherence_validation and document_parts:
                section_coherence = self.coherence_validator.validate_section(
                    section=section,
                    prior_sections=document_parts,
                )

                if not section_coherence.is_coherent:
                    logger.warning(
                        f"[LONGFORM] Section '{section.title}' coherence issues: "
                        f"{section_coherence.issues}"
                    )
                    coherence_issues.extend(section_coherence.issues)

                    # Attempt to regenerate with coherence hints
                    if section_coherence.score < 0.5:
                        logger.info(f"[LONGFORM] Regenerating section with coherence hints")
                        section = self._regenerate_with_hints(
                            section_spec=section_spec,
                            evidence=evidence,
                            query=query,
                            prior_sections=document_parts,
                            hints=section_coherence.suggestions,
                            kimi=kimi,
                        )

            document_parts.append(section)
            self.sections_generated.append(section)
            self.total_tokens_generated += section.word_count * 1.3  # Rough token estimate

            # Update context buffer
            self._update_context_buffer(section)

            logger.info(f"[LONGFORM] Generated section: {section.title} ({section.word_count} words)")

            # Check if we've hit target
            if self.total_tokens_generated >= self.target_total:
                logger.info("[LONGFORM] Reached target token count")
                break

        # Final document-level coherence validation
        if self.enable_coherence_validation:
            final_coherence = self.coherence_validator.validate_document(document_parts)
            logger.info(
                f"[LONGFORM] Final coherence score: {final_coherence.score:.2f}, "
                f"coherent: {final_coherence.is_coherent}"
            )

            if final_coherence.issues:
                logger.warning(f"[LONGFORM] Document coherence issues: {final_coherence.issues}")

        # Assemble final document
        return self._assemble_document(document_parts)

    def _regenerate_with_hints(
        self,
        section_spec: Dict,
        evidence: List[Dict],
        query: str,
        prior_sections: List[Section],
        hints: List[str],
        kimi,
    ) -> Section:
        """Regenerate a section with coherence hints."""
        # Add hints to section spec
        enhanced_spec = section_spec.copy()
        enhanced_spec["coherence_hints"] = hints

        return self._generate_section(
            section_spec=enhanced_spec,
            evidence=evidence,
            query=query,
            prior_sections=prior_sections,
            kimi=kimi,
        )

    def _generate_section(
        self,
        section_spec: Dict,
        evidence: List[Dict],
        query: str,
        prior_sections: List[Section],
        kimi,
    ) -> Section:
        """Generate a single section with context."""
        title = section_spec.get("title", "Section")
        target_words = section_spec.get("target_words", 2000)
        section_type = section_spec.get("type", "body")
        coherence_hints = section_spec.get("coherence_hints", [])

        # Filter relevant evidence
        relevant_evidence = self._filter_evidence_for_section(
            evidence, section_spec.get("topics", [])
        )

        # Build context from prior sections
        context = self._build_section_context(prior_sections)

        # Build coherence guidance if hints provided
        coherence_guidance = ""
        if coherence_hints:
            coherence_guidance = "\n\nCOHERENCE REQUIREMENTS (address these issues):\n"
            for i, hint in enumerate(coherence_hints, 1):
                coherence_guidance += f"{i}. {hint}\n"

        prompt = f"""
You are writing a comprehensive research report.

ORIGINAL QUERY: {query}

SECTION TO WRITE: {title}
TARGET LENGTH: {target_words} words
SECTION TYPE: {section_type}

CONTEXT FROM PRIOR SECTIONS:
{context[:8000]}

AVAILABLE EVIDENCE:
{self._format_evidence(relevant_evidence[:30])}

INSTRUCTIONS:
1. Write the section content
2. Cite evidence using [CITE:evidence_id] format
3. Maintain coherent flow with prior sections
4. Include specific data and facts from evidence
5. Target approximately {target_words} words
6. Begin with a transition from the previous section{coherence_guidance}

Write the section content now:
"""

        messages = [
            {"role": "system", "content": "You are an expert research writer."},
            {"role": "user", "content": prompt}
        ]

        result = kimi.generate(messages, max_tokens=self.max_chunk)
        content = result["content"]

        # Extract citations
        citations = re.findall(r'\[CITE:([^\]]+)\]', content)

        return Section(
            title=title,
            content=content,
            word_count=len(content.split()),
            citations=citations,
        )

    def _filter_evidence_for_section(
        self,
        evidence: List[Dict],
        topics: List[str],
    ) -> List[Dict]:
        """Filter evidence relevant to section topics."""
        if not topics:
            return evidence[:50]  # Return first 50 if no topics

        relevant = []
        for ev in evidence:
            content = ev.get("content", "").lower()
            if any(topic.lower() in content for topic in topics):
                relevant.append(ev)

        return relevant if relevant else evidence[:30]

    def _build_section_context(self, prior_sections: List[Section]) -> str:
        """Build context summary from prior sections."""
        if not prior_sections:
            return "This is the first section of the document."

        context_parts = []
        for section in prior_sections[-3:]:  # Last 3 sections
            summary = section.content[:500] + "..." if len(section.content) > 500 else section.content
            context_parts.append(f"## {section.title}\n{summary}")

        return "\n\n".join(context_parts)

    def _format_evidence(self, evidence: List[Dict]) -> str:
        """Format evidence for prompt."""
        formatted = []
        for ev in evidence:
            ev_id = ev.get("evidence_id", "unknown")
            content = ev.get("content", "")[:500]
            source = ev.get("source_url", "")
            formatted.append(f"[{ev_id}] {content}\nSource: {source}")

        return "\n\n".join(formatted)

    def _update_context_buffer(self, section: Section):
        """Update running context buffer."""
        # Keep summary of recent content for continuity
        self.context_buffer = section.content[-2000:] if len(section.content) > 2000 else section.content

    def _assemble_document(self, sections: List[Section]) -> str:
        """Assemble final document from sections."""
        parts = []

        for section in sections:
            parts.append(f"## {section.title}\n\n{section.content}")

        return "\n\n".join(parts)

    def get_stats(self) -> Dict[str, Any]:
        """Get generation statistics."""
        return {
            "sections_generated": len(self.sections_generated),
            "total_words": sum(s.word_count for s in self.sections_generated),
            "total_tokens_estimated": self.total_tokens_generated,
            "total_citations": sum(len(s.citations) for s in self.sections_generated),
        }

    def generate_outline(self, query: str, evidence: List[Dict]) -> List[Dict]:
        """Generate document outline based on query and evidence."""
        # Standard research report structure
        outline = [
            {"title": "Executive Summary", "type": "introduction", "target_words": 500},
            {"title": "Introduction", "type": "introduction", "target_words": 1000},
            {"title": "Background and Context", "type": "background", "target_words": 2000},
            {"title": "Methodology", "type": "methodology", "target_words": 1500},
            {"title": "Key Findings", "type": "findings", "target_words": 3000},
            {"title": "Analysis and Discussion", "type": "analysis", "target_words": 3000},
            {"title": "Implications", "type": "implications", "target_words": 2000},
            {"title": "Limitations", "type": "limitations", "target_words": 1000},
            {"title": "Future Directions", "type": "future", "target_words": 1000},
            {"title": "Conclusion", "type": "conclusion", "target_words": 500},
        ]

        # Add topics from evidence
        topics = self._extract_topics(evidence)
        for i, section in enumerate(outline):
            section["topics"] = topics[i % len(topics)] if topics else []

        return outline

    def _extract_topics(self, evidence: List[Dict]) -> List[List[str]]:
        """Extract topics from evidence for section assignment."""
        # Simple keyword extraction
        all_text = " ".join(ev.get("content", "") for ev in evidence[:50])
        words = all_text.lower().split()

        # Get most common meaningful words
        from collections import Counter
        word_counts = Counter(words)

        # Filter out common words
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or"}
        topics = [word for word, count in word_counts.most_common(100) if word not in stop_words and len(word) > 3]

        # Group into batches for sections
        batch_size = max(len(topics) // 10, 5)
        return [topics[i:i+batch_size] for i in range(0, len(topics), batch_size)]


@dataclass
class CoherenceResult:
    """Result from coherence validation."""
    is_coherent: bool
    score: float
    issues: List[str]
    suggestions: List[str]


class CoherenceValidator:
    """
    Validates coherence across long-form document sections.

    Checks for:
    - Logical flow between sections
    - Consistent terminology
    - Proper transitions
    - No contradictions
    """

    def __init__(self, min_coherence_score: float = 0.7):
        self.min_score = min_coherence_score

    def validate_document(self, sections: List[Section]) -> CoherenceResult:
        """
        Validate coherence across all sections.

        Args:
            sections: List of document sections

        Returns:
            CoherenceResult with score and issues
        """
        if not sections:
            return CoherenceResult(
                is_coherent=False,
                score=0.0,
                issues=["No sections to validate"],
                suggestions=["Add content sections"],
            )

        issues = []
        suggestions = []
        scores = []

        # Check section transitions
        transition_score = self._check_transitions(sections)
        scores.append(transition_score)
        if transition_score < 0.7:
            issues.append("Weak transitions between sections")
            suggestions.append("Add transitional sentences between sections")

        # Check terminology consistency
        term_score = self._check_terminology_consistency(sections)
        scores.append(term_score)
        if term_score < 0.7:
            issues.append("Inconsistent terminology usage")
            suggestions.append("Standardize key terms across sections")

        # Check logical flow
        flow_score = self._check_logical_flow(sections)
        scores.append(flow_score)
        if flow_score < 0.7:
            issues.append("Logical flow issues detected")
            suggestions.append("Ensure each section builds on previous ones")

        # Check for contradictions
        contradiction_score = self._check_contradictions(sections)
        scores.append(contradiction_score)
        if contradiction_score < 0.8:
            issues.append("Potential contradictions found")
            suggestions.append("Review and reconcile conflicting statements")

        # Calculate overall score
        overall_score = sum(scores) / len(scores) if scores else 0.0

        return CoherenceResult(
            is_coherent=overall_score >= self.min_score,
            score=overall_score,
            issues=issues,
            suggestions=suggestions,
        )

    def _check_transitions(self, sections: List[Section]) -> float:
        """Check transition quality between sections."""
        if len(sections) < 2:
            return 1.0

        transition_words = {
            "furthermore", "moreover", "additionally", "however", "therefore",
            "consequently", "in contrast", "similarly", "as a result", "meanwhile",
            "subsequently", "nevertheless", "thus", "hence", "accordingly",
        }

        good_transitions = 0
        total_transitions = len(sections) - 1

        for i in range(1, len(sections)):
            first_paragraph = sections[i].content.split('\n')[0].lower() if sections[i].content else ""

            # Check if first paragraph has transition word/phrase
            has_transition = any(tw in first_paragraph for tw in transition_words)

            # Also check for referential phrases
            referential = any(
                phrase in first_paragraph
                for phrase in ["as mentioned", "building on", "continuing from", "following"]
            )

            if has_transition or referential:
                good_transitions += 1

        return good_transitions / max(total_transitions, 1)

    def _check_terminology_consistency(self, sections: List[Section]) -> float:
        """Check if terminology is used consistently."""
        # Extract key terms from each section
        term_variants = {}

        for section in sections:
            words = section.content.lower().split() if section.content else []

            # Look for potential term variants (simplified)
            for word in words:
                if len(word) > 5:
                    base = word[:5]
                    if base not in term_variants:
                        term_variants[base] = set()
                    term_variants[base].add(word)

        # Check for variant consistency
        inconsistent_terms = sum(1 for variants in term_variants.values() if len(variants) > 3)
        total_terms = len(term_variants)

        if total_terms == 0:
            return 1.0

        consistency_ratio = 1 - (inconsistent_terms / total_terms)
        return max(consistency_ratio, 0.0)

    def _check_logical_flow(self, sections: List[Section]) -> float:
        """Check if sections follow logical progression."""
        # Standard section order mapping
        standard_order = {
            "introduction": 0, "executive summary": 0,
            "background": 1, "context": 1, "literature": 1,
            "methodology": 2, "methods": 2, "approach": 2,
            "findings": 3, "results": 3, "analysis": 3,
            "discussion": 4, "implications": 4,
            "limitations": 5, "future": 5,
            "conclusion": 6, "summary": 6,
        }

        positions = []
        for section in sections:
            title_lower = section.title.lower()
            for key, pos in standard_order.items():
                if key in title_lower:
                    positions.append(pos)
                    break
            else:
                positions.append(-1)  # Unknown section

        # Check if positions are generally increasing
        valid_positions = [p for p in positions if p >= 0]
        if len(valid_positions) < 2:
            return 1.0

        inversions = 0
        for i in range(1, len(valid_positions)):
            if valid_positions[i] < valid_positions[i-1]:
                inversions += 1

        return 1 - (inversions / max(len(valid_positions) - 1, 1))

    def _check_contradictions(self, sections: List[Section]) -> float:
        """Check for potential contradictions between sections."""
        # Extract claims with numbers
        claims = []
        for section in sections:
            if not section.content:
                continue

            sentences = section.content.split('.')
            for sentence in sentences:
                # Look for sentences with numbers (potential factual claims)
                if any(char.isdigit() for char in sentence):
                    claims.append({
                        "section": section.title,
                        "text": sentence.strip(),
                    })

        # Simple contradiction check: same subject, different numbers
        contradictions = 0
        for i, claim1 in enumerate(claims):
            for claim2 in claims[i+1:]:
                if self._might_contradict(claim1["text"], claim2["text"]):
                    contradictions += 1

        max_contradictions = len(claims) * (len(claims) - 1) / 2 if len(claims) > 1 else 1
        return 1 - min(contradictions / max(max_contradictions, 1), 1.0)

    def _might_contradict(self, text1: str, text2: str) -> bool:
        """Check if two claims might contradict each other."""
        # Simple heuristic: same key nouns but different numbers
        words1 = set(w.lower() for w in text1.split() if len(w) > 4)
        words2 = set(w.lower() for w in text2.split() if len(w) > 4)

        # If significant word overlap
        overlap = words1 & words2
        if len(overlap) < 3:
            return False

        # Extract numbers
        import re
        nums1 = set(re.findall(r'\d+\.?\d*', text1))
        nums2 = set(re.findall(r'\d+\.?\d*', text2))

        # If same topic but different numbers, might contradict
        return len(nums1) > 0 and len(nums2) > 0 and nums1 != nums2

    def validate_section(self, section: Section, prior_sections: List[Section]) -> CoherenceResult:
        """Validate a single section against prior content."""
        issues = []
        suggestions = []
        scores = []

        # Check reference to prior sections
        if prior_sections:
            ref_score = self._check_references(section, prior_sections)
            scores.append(ref_score)
            if ref_score < 0.5:
                issues.append("Section lacks connection to prior content")
                suggestions.append("Add references to concepts introduced earlier")

        # Check internal coherence
        internal_score = self._check_internal_coherence(section)
        scores.append(internal_score)
        if internal_score < 0.7:
            issues.append("Section has internal coherence issues")
            suggestions.append("Ensure paragraphs flow logically within section")

        overall_score = sum(scores) / len(scores) if scores else 1.0

        return CoherenceResult(
            is_coherent=overall_score >= self.min_score,
            score=overall_score,
            issues=issues,
            suggestions=suggestions,
        )

    def _check_references(self, section: Section, prior_sections: List[Section]) -> float:
        """Check if section references concepts from prior sections."""
        prior_terms = set()
        for prior in prior_sections[-3:]:  # Check last 3 sections
            words = prior.content.lower().split() if prior.content else []
            prior_terms.update(w for w in words if len(w) > 5)

        current_words = set(section.content.lower().split()) if section.content else set()

        # How many prior terms appear in current section?
        overlap = prior_terms & current_words
        if not prior_terms:
            return 1.0

        return min(len(overlap) / 20, 1.0)  # Expect at least 20 shared terms

    def _check_internal_coherence(self, section: Section) -> float:
        """Check internal coherence within a section."""
        if not section.content:
            return 0.0

        paragraphs = [p.strip() for p in section.content.split('\n\n') if p.strip()]

        if len(paragraphs) < 2:
            return 1.0

        # Check paragraph connectivity
        connected = 0
        for i in range(1, len(paragraphs)):
            prev_words = set(paragraphs[i-1].lower().split())
            curr_words = set(paragraphs[i].lower().split())
            overlap = len(prev_words & curr_words)

            if overlap >= 3:  # At least 3 shared words
                connected += 1

        return connected / max(len(paragraphs) - 1, 1)
