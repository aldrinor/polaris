#!/usr/bin/env python3
"""Schema-aware wheel monitor. Reads workflow journals + newest agent thinking.
Run: python3 wheels.py"""
import json, os, time, glob, sys

BASE = "/home/polaris/.claude/projects/-home-polaris-polaris-project/ea997c8e-37cf-4d9a-8a80-f7728137f18b/subagents/workflows"
WHEELS = [
    ("QUALITY", "wf_70ee53f7-a9c"),  # P0 safe no-deadlock config + guard; P1 kill degrade tail
]
now = time.time()
print(f"===== WHEELS @ {time.strftime('%H:%M:%S', time.gmtime())} UTC =====")
for name, wid in WHEELS:
    d = os.path.join(BASE, wid)
    j = os.path.join(d, "journal.jsonl")
    started = finished = 0
    last_result = None
    if os.path.exists(j):
        for l in open(j):
            try: e = json.loads(l)
            except: continue
            if e.get("type") == "started": started += 1
            if e.get("type") == "result":
                finished += 1
                last_result = e.get("result")
    # freshness
    files = glob.glob(os.path.join(d, "*.jsonl"))
    age = int(now - max(os.path.getmtime(f) for f in files)) if files else -1
    live = "WRITING" if 0 <= age < 30 else (f"idle {age}s" if age >= 0 else "no files")
    print(f"\n[{name}] {started} started / {finished} done — {live}")
    # freshest thinking from newest agent transcript
    agents = glob.glob(os.path.join(d, "agent-*.jsonl"))
    if agents:
        newest = max(agents, key=os.path.getmtime)
        think = ""
        for l in open(newest):
            try: e = json.loads(l)
            except: continue
            m = e.get("message", e); c = m.get("content") if isinstance(m, dict) else None
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip():
                        think = b["text"].strip()
        if think:
            print(f"   doing: {think[:200]}")
    if isinstance(last_result, dict):
        keys = [k for k in ('lane','refuted','real_impact','verdict','sign_off','sota',
                            'is_it_RACE','polaris_wins','binding_constraint','at_sota') if k in last_result]
        for k in keys[:3]:
            v = last_result[k]
            v = f"[{len(v)}]" if isinstance(v, list) else ("{...}" if isinstance(v, dict) else str(v)[:100])
            print(f"   last result .{k} = {v}")
print(f"\nload={open('/proc/loadavg').read().split()[0]}")
