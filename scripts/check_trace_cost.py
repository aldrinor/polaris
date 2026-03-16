"""Quick trace file cost analyzer."""
import json
import sys

trace_path = "C:/POLARIS/logs/pg_trace_GEMINI_E2E_20260315_192524.jsonl"

with open(trace_path) as f:
    lines = f.readlines()

# Get cumulative cost from the last llm_call event
max_cost = 0
last_cost_event = None
for line in lines:
    e = json.loads(line)
    c = e.get("cumulative_cost_usd", 0)
    if c and c > max_cost:
        max_cost = c
        last_cost_event = e

print(f"Current cumulative cost: ${max_cost:.4f}")
if last_cost_event:
    print(f"Last cost event node: {last_cost_event.get('node', '?')}")
    print(f"Last cost event ts: {last_cost_event.get('ts', '?')}")

# Count how many structured extraction calls
struct_calls = []
for line in lines:
    e = json.loads(line)
    if e.get("type") == "llm_call" and "structured" in e.get("node", ""):
        struct_calls.append(e)

print(f"\nStructured extraction LLM calls: {len(struct_calls)}")
if struct_calls:
    print(f"First: {struct_calls[0].get('ts', '?')[:19]}")
    print(f"Last:  {struct_calls[-1].get('ts', '?')[:19]}")
    total_in = sum(c.get("input_tokens", 0) for c in struct_calls)
    total_out = sum(c.get("output_tokens", 0) for c in struct_calls)
    total_reason = sum(c.get("reasoning_tokens", 0) for c in struct_calls)
    total_cost = sum(c.get("cost_usd", 0) for c in struct_calls)
    print(f"Tokens: in={total_in:,}, out={total_out:,}, reasoning={total_reason:,}")
    print(f"Structured cost: ${total_cost:.4f}")
    for c in struct_calls[-3:]:
        ts = c.get("ts", "?")[:19]
        dur = c.get("duration_ms", 0) / 1000
        cost = c.get("cost_usd", 0)
        print(f"  {ts} | dur={dur:.1f}s | cost=${cost:.4f}")

# All LLM calls summary
all_calls = [json.loads(l) for l in lines if json.loads(l).get("type") == "llm_call"]
print(f"\nAll LLM calls: {len(all_calls)}")
total_cost_all = sum(c.get("cost_usd", 0) for c in all_calls)
print(f"Total cost from LLM calls: ${total_cost_all:.4f}")
