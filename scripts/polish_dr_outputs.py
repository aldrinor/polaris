"""Unescape JSON-style \\n in ChatGPT extract and trim trailing extension UI noise."""
import re
from pathlib import Path

Q1 = "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"


# ChatGPT: unescape \\n -> actual newlines, trim Chinese extension trailers
chat = Path("state/compare_chatgpt_q1.md").read_text(encoding="utf-8")
chat = chat.replace("\\\\n", "\n").replace("\\\\\"", '"').replace("\\\\t", "\t")
# Cut at the Chinese trailer
for marker in ["收缩到边缘", "导出聊天记录", "Chat Stats", "ChatGPT Stats"]:
    idx = chat.find(marker)
    if idx >= 0:
        chat = chat[:idx].rstrip()
        break
Path("state/compare_chatgpt_q1.md").write_text(chat, encoding="utf-8")
print(f"chatgpt: {len(chat)} chars")
print(f"  head: {chat[:300]}")
print(f"  tail: {chat[-200:]}")

print()

# Gemini: minor cleanup — also extract bibliography/source list if present
gem = Path("state/compare_gemini_q1.md").read_text(encoding="utf-8")
# Look for sources section in the raw file to grab citations
raw_gem = Path("state/compare_gemini_q1.md").read_text(encoding="utf-8")
print(f"gemini: {len(gem)} chars")
print(f"  head: {gem[:300]}")
print(f"  tail: {gem[-200:]}")
print(f"  contains 'Sources': {'Sources' in gem}")
print(f"  contains 'Works cited': {'Works cited' in gem}")
print(f"  contains 'References': {'References' in gem}")
