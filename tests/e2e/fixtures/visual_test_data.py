"""
Deterministic mock data for POLARIS Observatory visual regression tests.
All data is hardcoded to ensure 100% reproducible screenshots.
"""

# --- SSE Stream Events (deterministic 50-event sequence) ---
DETERMINISTIC_SSE_FIXTURE = """event: phase
data: {"phase": "plan", "status": "complete", "detail": "Generated 15 search queries across 4 perspectives"}

event: phase
data: {"phase": "search", "status": "running", "detail": "Searching 15 queries across Serper, Semantic Scholar, DuckDuckGo"}

event: activity
data: {"type": "search", "message": "Serper: 10 results for 'quantum computing error correction 2024'", "ts": "2024-03-15T10:05:23Z"}

event: activity
data: {"type": "search", "message": "S2: 8 academic papers found for 'topological quantum error correction'", "ts": "2024-03-15T10:05:24Z"}

event: activity
data: {"type": "fetch", "message": "Fetching content from nature.com/articles/s41586-024-quantum", "ts": "2024-03-15T10:05:25Z"}

event: phase
data: {"phase": "search", "status": "complete", "detail": "Collected 247 results from 15 queries"}

event: phase
data: {"phase": "analyze", "status": "running", "detail": "Extracting evidence from 47 sources"}

event: activity
data: {"type": "analyze", "message": "Extracted 12 evidence pieces from nature.com article", "ts": "2024-03-15T10:06:01Z"}

event: activity
data: {"type": "analyze", "message": "Extracted 8 evidence pieces from arxiv.org paper", "ts": "2024-03-15T10:06:03Z"}

event: evidence
data: {"id": "ev_001", "quote": "Quantum error correction codes have achieved logical error rates below 1% for the first time", "source": "nature.com", "tier": "GOLD", "relevance": 0.95}

event: evidence
data: {"id": "ev_002", "quote": "Surface codes require approximately 1000 physical qubits per logical qubit", "source": "arxiv.org", "tier": "GOLD", "relevance": 0.91}

event: evidence
data: {"id": "ev_003", "quote": "Topological approaches show promise for reducing overhead by 40%", "source": "science.org", "tier": "SILVER", "relevance": 0.82}

event: phase
data: {"phase": "analyze", "status": "complete", "detail": "Extracted 156 evidence pieces from 47 sources"}

event: phase
data: {"phase": "verify", "status": "running", "detail": "Verifying 156 claims against source content"}

event: activity
data: {"type": "verify", "message": "Batch 1/8: 20 claims verified (18 supported, 2 partial)", "ts": "2024-03-15T10:07:30Z"}

event: activity
data: {"type": "verify", "message": "Batch 2/8: 20 claims verified (19 supported, 1 not supported)", "ts": "2024-03-15T10:07:45Z"}

event: phase
data: {"phase": "verify", "status": "complete", "detail": "Faithfulness: 92.3% (144/156 supported)"}

event: phase
data: {"phase": "synthesize", "status": "running", "detail": "Generating report outline with 12 sections"}

event: activity
data: {"type": "synthesize", "message": "Writing section 1/12: Introduction to Quantum Error Correction", "ts": "2024-03-15T10:08:20Z"}

event: activity
data: {"type": "synthesize", "message": "Writing section 2/12: Surface Code Architectures", "ts": "2024-03-15T10:08:45Z"}

event: section
data: {"title": "Introduction to Quantum Error Correction", "words": 850, "citations": 12}

event: section
data: {"title": "Surface Code Architectures", "words": 1200, "citations": 18}

event: phase
data: {"phase": "synthesize", "status": "complete", "detail": "Report generated: 8,450 words, 156 citations, 47 sources"}

event: metrics
data: {"evidence_count": 156, "citation_count": 156, "source_count": 47, "word_count": 8450, "faithfulness": 0.923, "iterations": 2, "cost_usd": 1.31, "elapsed_sec": 323}

event: complete
data: {"status": "success", "case": "CASE_1"}
"""

# --- Deterministic Report HTML ---
DETERMINISTIC_REPORT_HTML = '''<h1>Quantum Error Correction: Current State and Future Directions</h1>
<p><em>A comprehensive analysis of quantum error correction techniques, architectures, and recent breakthroughs in achieving fault-tolerant quantum computation.</em></p>

<h2>1. Introduction</h2>
<p>Quantum error correction (QEC) represents one of the most critical challenges in the development of practical quantum computers. Unlike classical bits, quantum bits (qubits) are inherently susceptible to decoherence and environmental noise, making error correction essential for any meaningful computation <sup class="cite-link" data-cite="1">[1]</sup>. Recent advances have demonstrated logical error rates below the threshold required for fault-tolerant quantum computation <sup class="cite-link" data-cite="2">[2]</sup><sup class="cite-link" data-cite="3">[3]</sup>.</p>

<h2>2. Surface Code Architectures</h2>
<p>The surface code remains the leading candidate for practical quantum error correction due to its high threshold error rate and compatibility with nearest-neighbor qubit connectivity <sup class="cite-link" data-cite="4">[4]</sup>. Current implementations require approximately 1,000 physical qubits per logical qubit <sup class="cite-link" data-cite="2">[2]</sup>, though recent advances in topological approaches have shown potential for reducing this overhead by 40% <sup class="cite-link" data-cite="5">[5]</sup>.</p>

<h3>2.1 Threshold Error Rates</h3>
<p>The threshold theorem establishes that if physical error rates are below a certain threshold, arbitrarily reliable quantum computation is possible. For surface codes, this threshold is approximately 1% per gate operation <sup class="cite-link" data-cite="6">[6]</sup>.</p>

<h2>3. Recent Experimental Breakthroughs</h2>
<p>In 2024, multiple research groups demonstrated significant milestones in quantum error correction. Google\\'s Willow processor achieved a logical error rate that decreased exponentially with increasing code distance <sup class="cite-link" data-cite="7">[7]</sup>, while IBM demonstrated real-time error correction on their 1,121-qubit Condor processor <sup class="cite-link" data-cite="8">[8]</sup>.</p>

<table>
<thead><tr><th>System</th><th>Qubits</th><th>Logical Error Rate</th><th>Year</th></tr></thead>
<tbody>
<tr><td>Google Willow</td><td>105</td><td>0.143%</td><td>2024</td></tr>
<tr><td>IBM Condor</td><td>1121</td><td>0.28%</td><td>2024</td></tr>
<tr><td>QuEra Aquila</td><td>256</td><td>0.5%</td><td>2024</td></tr>
</tbody>
</table>

<h2>4. Challenges and Future Directions</h2>
<p>Despite remarkable progress, several challenges remain. The qubit overhead for surface codes is substantial, and achieving the millions of physical qubits needed for practical applications requires advances in qubit manufacturing and control <sup class="cite-link" data-cite="9">[9]</sup>. Novel approaches such as quantum LDPC codes offer promising alternatives with potentially lower overhead <sup class="cite-link" data-cite="10">[10]</sup>.</p>

<h2>5. Conclusion</h2>
<p>Quantum error correction has transitioned from theoretical framework to experimental reality. The demonstration of below-threshold logical error rates represents a watershed moment for the field <sup class="cite-link" data-cite="1">[1]</sup><sup class="cite-link" data-cite="7">[7]</sup>. Continued progress in reducing qubit overhead and improving error thresholds will be essential for achieving practical fault-tolerant quantum computation within the next decade.</p>
'''

# --- Deterministic Evidence Cards ---
DETERMINISTIC_EVIDENCE = [
    {
        "id": "ev_001",
        "quote": "Quantum error correction codes have achieved logical error rates below 1% for the first time in experimental implementations.",
        "source_title": "Breaking the Error Floor: Quantum Error Correction in 2024",
        "source_url": "https://nature.com/articles/s41586-024-quantum-ec",
        "source_domain": "nature.com",
        "tier": "GOLD",
        "relevance": 0.95,
        "faithfulness": "SUPPORTED",
        "confidence": 0.92,
        "nli_score": 0.88,
        "signals": {"authority": 0.95, "recency": 0.90, "corroboration": 0.85, "specificity": 0.88, "peer_reviewed": 1.0},
    },
    {
        "id": "ev_002",
        "quote": "Surface codes require approximately 1000 physical qubits per logical qubit with current noise levels.",
        "source_title": "Scaling Surface Codes for Practical Quantum Computing",
        "source_url": "https://arxiv.org/abs/2401.12345",
        "source_domain": "arxiv.org",
        "tier": "GOLD",
        "relevance": 0.91,
        "faithfulness": "SUPPORTED",
        "confidence": 0.89,
        "nli_score": 0.91,
        "signals": {"authority": 0.88, "recency": 0.95, "corroboration": 0.82, "specificity": 0.90, "peer_reviewed": 0.5},
    },
    {
        "id": "ev_003",
        "quote": "Topological approaches to quantum error correction show promise for reducing qubit overhead by approximately 40%.",
        "source_title": "Topological Quantum Codes: A New Paradigm",
        "source_url": "https://science.org/doi/10.1126/science.topological",
        "source_domain": "science.org",
        "tier": "SILVER",
        "relevance": 0.82,
        "faithfulness": "SUPPORTED",
        "confidence": 0.78,
        "nli_score": 0.75,
        "signals": {"authority": 0.90, "recency": 0.80, "corroboration": 0.70, "specificity": 0.75, "peer_reviewed": 1.0},
    },
    {
        "id": "ev_004",
        "quote": "The threshold theorem proves that quantum computation can be made arbitrarily reliable if physical error rates fall below a certain threshold.",
        "source_title": "Fault-Tolerant Quantum Computation: Theory and Practice",
        "source_url": "https://journals.aps.org/prx/abstract/threshold",
        "source_domain": "journals.aps.org",
        "tier": "GOLD",
        "relevance": 0.88,
        "faithfulness": "SUPPORTED",
        "confidence": 0.95,
        "nli_score": 0.93,
        "signals": {"authority": 0.95, "recency": 0.60, "corroboration": 0.95, "specificity": 0.80, "peer_reviewed": 1.0},
    },
    {
        "id": "ev_005",
        "quote": "IBM's 1,121-qubit Condor processor demonstrated real-time error correction with continuous syndrome measurement.",
        "source_title": "IBM Quantum Roadmap: Condor and Beyond",
        "source_url": "https://research.ibm.com/blog/condor-quantum",
        "source_domain": "research.ibm.com",
        "tier": "SILVER",
        "relevance": 0.85,
        "faithfulness": "PARTIAL",
        "confidence": 0.72,
        "nli_score": 0.68,
        "signals": {"authority": 0.85, "recency": 0.95, "corroboration": 0.60, "specificity": 0.82, "peer_reviewed": 0.0},
    },
]

# --- Deterministic Citation Chain Data ---
DETERMINISTIC_CHAIN = {
    "source": {
        "title": "Breaking the Error Floor: Quantum Error Correction in 2024",
        "url": "https://nature.com/articles/s41586-024-quantum-ec",
        "domain": "nature.com",
        "type": "peer_reviewed",
        "year": 2024,
        "authors": "Chen, A.; Smith, B.; Wang, C.",
        "venue": "Nature",
    },
    "evidence": [
        {
            "id": "ev_001",
            "quote": "Quantum error correction codes have achieved logical error rates below 1% for the first time.",
            "tier": "GOLD",
            "relevance": 0.95,
            "verdict": "SUPPORTED",
            "nli_score": 0.88,
            "sections_used": ["Introduction", "Surface Code Architectures"],
        }
    ],
    "reasoning_chain": {
        "source_discovery": "Found via Serper search for 'quantum error correction breakthrough 2024'",
        "extraction": "Extracted 12 evidence pieces from 8,420 chars of content",
        "verification": "NLI verification: 0.88 entailment score against source content",
        "synthesis": "Used in Introduction (2 citations) and Surface Code section (1 citation)",
    },
}

# --- Deterministic API Response ---
DETERMINISTIC_RESULT = {
    "vector_id": "v_test_visual_001",
    "query": "What are the latest advances in quantum error correction?",
    "status": "complete",
    "case": "CASE_1",
    "iterations": 2,
    "report_html": DETERMINISTIC_REPORT_HTML,
    "evidence_count": 156,
    "citation_count": 156,
    "source_count": 47,
    "word_count": 8450,
    "faithfulness": 0.923,
    "cost_usd": 1.31,
    "elapsed_sec": 323,
    "quality_gates": {
        "word_count": {"value": 8450, "threshold": 2000, "pass": True},
        "citation_count": {"value": 156, "threshold": 5, "pass": True},
        "faithfulness": {"value": 0.923, "threshold": 0.70, "pass": True},
        "source_count": {"value": 47, "threshold": 10, "pass": True},
    },
    "evidence": DETERMINISTIC_EVIDENCE,
    "sources": [
        {"url": "https://nature.com/articles/s41586-024-quantum-ec", "title": "Breaking the Error Floor", "domain": "nature.com", "type": "peer_reviewed", "year": 2024},
        {"url": "https://arxiv.org/abs/2401.12345", "title": "Scaling Surface Codes", "domain": "arxiv.org", "type": "preprint", "year": 2024},
        {"url": "https://science.org/doi/10.1126/science.topological", "title": "Topological Quantum Codes", "domain": "science.org", "type": "peer_reviewed", "year": 2024},
        {"url": "https://journals.aps.org/prx/abstract/threshold", "title": "Fault-Tolerant Quantum Computation", "domain": "journals.aps.org", "type": "peer_reviewed", "year": 2023},
        {"url": "https://research.ibm.com/blog/condor-quantum", "title": "IBM Quantum Roadmap", "domain": "research.ibm.com", "type": "blog", "year": 2024},
    ],
    "storm_perspectives": [
        {"name": "Experimental Physicist", "expertise": "Qubit fabrication and noise characterization", "focus": "Physical implementations of error correction"},
        {"name": "Theoretical Computer Scientist", "expertise": "Coding theory and complexity", "focus": "Optimal code constructions and thresholds"},
        {"name": "Quantum Engineer", "expertise": "System architecture and control", "focus": "Scalable quantum error correction systems"},
        {"name": "Industry Analyst", "expertise": "Technology commercialization", "focus": "Timeline and feasibility of fault-tolerant QC"},
    ],
}

# --- JS injection for freezing dynamic counters ---
FREEZE_DYNAMIC_COUNTERS_JS = """
window._visualTestMode = true;
document.querySelectorAll('.elapsed-time').forEach(e => e.textContent = '00:05:23');
document.querySelectorAll('.event-count').forEach(e => e.textContent = '247');
document.querySelectorAll('.cost-display').forEach(e => e.textContent = '$1.31');
document.querySelectorAll('.evidence-counter').forEach(e => e.textContent = '156');
document.querySelectorAll('.source-counter').forEach(e => e.textContent = '47');
"""
