"""Final clean pass: remove Chinese extension trailers, normalize whitespace."""
import re
from pathlib import Path


for label, p in [("CHATGPT", "state/compare_chatgpt_q1.md"), ("GEMINI", "state/compare_gemini_q1.md")]:
    src = Path(p).read_text(encoding="utf-8")
    # Cut at any Chinese fullwidth chars chunk (extension UI)
    # Find the LAST run of meaningful English content
    for marker in ["未知模型", "正常", "未知 (未知)", "1个模型", "1次", "GPT使用详情"]:
        idx = src.find(marker)
        if idx >= 0:
            # Trim from start of the line containing this marker
            line_start = src.rfind("\n", 0, idx)
            if line_start >= 0:
                src = src[:line_start].rstrip()
                break
    # Collapse 3+ blank lines to 2
    src = re.sub(r"\n{3,}", "\n\n", src)
    # Collapse runs of leading whitespace on otherwise empty lines
    src = re.sub(r"^[ \t]+$", "", src, flags=re.MULTILINE)
    Path(p).write_text(src, encoding="utf-8")
    print(f"{label}: {len(src)} chars")
    print(f"  tail (last 300): {src[-300:]!r}")
    print()
