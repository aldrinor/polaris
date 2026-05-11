"""Slice the actual report text out of the raw textContent files."""
import re
from pathlib import Path


def extract_chatgpt() -> str:
    src = Path("state/compare_chatgpt_q1_raw.md").read_text(encoding="utf-8")
    # Find the start: "Canada's Sovereign Frontier-LLM" appears as the title
    start_markers = [
        "Canada's Sovereign Frontier-LLM",
        "Sovereign Frontier-LLM Compute",
    ]
    start = -1
    for m in start_markers:
        idx = src.find(m)
        if idx >= 0:
            start = idx
            break
    if start < 0:
        return ""
    # Find end: look for ChatGPT footer markers or end of citations
    end_markers = [
        "ChatGPT can make mistakes",
        "Send feedback",
    ]
    end = len(src)
    for m in end_markers:
        idx = src.find(m, start)
        if idx >= 0:
            end = min(end, idx)
    body = src[start:end].strip()
    return body


def extract_gemini() -> str:
    src = Path("state/compare_gemini_q1.md").read_text(encoding="utf-8")
    # Gemini saved file already has the report in it; find the actual report start
    start_markers = [
        "I've completed your research",
        "Canada AI Compute: Sovereign vs. Hyperscaler",
        "The 2026 AI Compute Trilemma",
    ]
    start = -1
    for m in start_markers:
        idx = src.find(m)
        if idx >= 0:
            start = idx
            break
    if start < 0:
        return ""
    # End markers
    end_markers = [
        "Gemini is AI and can make mistakes",
        "Send feedback",
        "Privacy Policy",
    ]
    end = len(src)
    for m in end_markers:
        idx = src.find(m, start + 5000)  # require some distance from start
        if idx >= 0:
            end = min(end, idx)
    body = src[start:end].strip()
    return body


Q1 = "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"


for label, src_path, out_path, extract_fn in [
    ("CHATGPT", "state/compare_chatgpt_q1_raw.md", "state/compare_chatgpt_q1.md", extract_chatgpt),
    ("GEMINI", "state/compare_gemini_q1.md", "state/compare_gemini_q1.md", extract_gemini),
]:
    body = extract_fn()
    if not body:
        print(f"{label}: extraction FAILED (no start marker)")
        continue
    out = Path(out_path)
    out.write_text(
        f"# {label} Deep Research - Q1\n\n**Question:** {Q1}\n\n---\n\n" + body,
        encoding="utf-8",
    )
    print(f"{label}: saved {out} ({out.stat().st_size} bytes, body {len(body)} chars)")
    print(f"  head: {body[:200]}")
    print(f"  tail: {body[-200:]}")
    print()
