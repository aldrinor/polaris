"""Unit tests for FIX-059-E: _prefilter_academic_results in searcher.py."""

import pytest


def test_prefilter_rejects_no_abstract():
    """H-12: Papers without abstracts are rejected."""
    from src.polaris_graph.agents.searcher import _prefilter_academic_results

    papers = [
        {"title": "Water filtration methods", "abstract": ""},
        {"title": "Water purification review", "abstract": None},
        {"title": "Clean water technology", "abstract": "Short"},
    ]
    result = _prefilter_academic_results(papers, "water filtration")
    assert len(result) == 0, f"Expected 0, got {len(result)}: all have no/short abstracts"


def test_prefilter_rejects_off_topic():
    """BUG-5: Papers with zero topic overlap are rejected."""
    from src.polaris_graph.agents.searcher import _prefilter_academic_results

    papers = [
        {
            "title": "UAV Radar Signal Processing for Target Detection",
            "abstract": "This paper presents a novel radar signal processing "
            "algorithm for unmanned aerial vehicle target detection and "
            "tracking in cluttered environments with multiple reflections.",
        },
        {
            "title": "Canine Gastric Tumor Treatment Outcomes",
            "abstract": "A retrospective study of surgical outcomes in dogs "
            "diagnosed with gastric tumors, analyzing survival rates and "
            "postoperative complications across 200 veterinary cases.",
        },
    ]
    result = _prefilter_academic_results(papers, "water filtration membrane technology")
    assert len(result) == 0, f"Expected 0, got {len(result)}: off-topic papers should be rejected"


def test_prefilter_keeps_relevant_papers():
    """Relevant papers with abstracts are kept."""
    from src.polaris_graph.agents.searcher import _prefilter_academic_results

    papers = [
        {
            "title": "Membrane Filtration for Water Treatment",
            "abstract": "A comprehensive review of membrane filtration "
            "technologies for drinking water treatment, covering "
            "microfiltration, ultrafiltration, nanofiltration, and "
            "reverse osmosis membrane systems and their performance.",
        },
        {
            "title": "Advanced Water Purification Technologies",
            "abstract": "This study evaluates advanced water purification "
            "methods including activated carbon filtration, UV disinfection, "
            "and electrochemical treatment for removing contaminants "
            "from municipal water supplies.",
        },
    ]
    result = _prefilter_academic_results(papers, "water filtration membrane technology")
    assert len(result) == 2, f"Expected 2, got {len(result)}: relevant papers should be kept"


def test_prefilter_abstract_fallback():
    """Papers with no title overlap but abstract overlap are kept."""
    from src.polaris_graph.agents.searcher import _prefilter_academic_results

    papers = [
        {
            "title": "Novel Approaches to Municipal Infrastructure",
            "abstract": "This paper reviews water filtration systems used in "
            "municipal infrastructure, including membrane technology "
            "advances and cost-benefit analyses for large-scale deployment.",
        },
    ]
    result = _prefilter_academic_results(papers, "water filtration membrane")
    assert len(result) == 1, f"Expected 1, got {len(result)}: abstract overlap should save this paper"


def test_prefilter_empty_input():
    """Empty paper list returns empty."""
    from src.polaris_graph.agents.searcher import _prefilter_academic_results

    result = _prefilter_academic_results([], "water filtration")
    assert len(result) == 0


def test_prefilter_mixed_results():
    """Mix of relevant and off-topic papers -- only relevant kept."""
    from src.polaris_graph.agents.searcher import _prefilter_academic_results

    papers = [
        {
            "title": "Water Filtration Using Ceramic Membranes",
            "abstract": "Ceramic membranes for water filtration offer superior "
            "chemical resistance and longer lifespans compared to polymeric "
            "membranes in industrial water treatment applications.",
        },
        {
            "title": "Brain Tumor Classification Using Deep Learning",
            "abstract": "A convolutional neural network approach to classifying "
            "brain tumors from MRI scans with 97% accuracy across four "
            "tumor categories in a dataset of 3000 medical images.",
        },
        {
            "title": "Reverse Osmosis Membrane Performance",
            "abstract": "Performance evaluation of thin-film composite reverse "
            "osmosis membranes for desalination and water purification, "
            "measuring salt rejection rates and permeate flux under varying conditions.",
        },
    ]
    result = _prefilter_academic_results(papers, "water filtration membrane")
    assert len(result) == 2, f"Expected 2, got {len(result)}"
    titles = [p["title"] for p in result]
    assert "Brain Tumor Classification Using Deep Learning" not in titles
