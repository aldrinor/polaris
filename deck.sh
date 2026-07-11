#!/usr/bin/env bash
# POLARIS master monitoring deck. Read-only. Run any time: bash deck.sh
WFDIR=/home/polaris/.claude/projects/-home-polaris-polaris-project/ea997c8e-37cf-4d9a-8a80-f7728137f18b/subagents/workflows

printf '\033[1m=== POLARIS DECK  %s UTC ===\033[0m\n' "$(date -u +%H:%M:%S)"

printf '\n\033[1m-- wheels (workflow journals) --\033[0m\n'
for wf in "$WFDIR"/wf_*; do
  [ -d "$wf" ] || continue
  j="$wf/journal.jsonl"
  [ -f "$j" ] || { printf '  %-18s (no journal yet)\n' "$(basename "$wf")"; continue; }
  # last log line tells us the round + phase
  last=$(grep -o '"message":"[^"]*"' "$j" 2>/dev/null | tail -1 | sed 's/"message":"//;s/"$//')
  n=$(grep -c '"type":"agent_end"' "$j" 2>/dev/null); n=${n:-0}
  printf '  %-18s agents_done=%-3s %s\n' "$(basename "$wf" | cut -c1-18)" "$n" "${last:0:95}"
done

printf '\n\033[1m-- commits (is anything actually landing?) --\033[0m\n'
for d in outline_agent tooluse compose; do
  wt=/home/polaris/wt/$d
  [ -d "$wt" ] || continue
  printf '  %-13s %s\n' "$d" "$(git -C "$wt" log -1 --pretty='%h %ad %s' --date=format:'%H:%M' 2>/dev/null | cut -c1-88)"
  dirty=$(git -C "$wt" status --porcelain | wc -l)
  [ "$dirty" -gt 0 ] && printf '                \033[33m%s file(s) uncommitted\033[0m\n' "$dirty"
done

printf '\n\033[1m-- SMOKING GUNS --\033[0m\n'
hit=0

# 1. OpenRouter 429 contention — the #1 measurement poisoner.
#    Match a REAL rate-limit signature, not a bare '429' (which hits token counts like
#    '1429 in' / '429 reasoning tokens'). Exclude committed .codex artifact logs whose
#    mtimes are checkout-time, not event-time.
r429=$(find /home/polaris/wt /workspace/POLARIS/logs -name '*.log' -mmin -10 2>/dev/null \
       | grep -v '/\.codex/' \
       | xargs -r grep -lEi '429 Too Many|HTTP[^0-9]*429|rate.?limit' 2>/dev/null | wc -l)
if [ "$r429" -gt 0 ]; then
  printf '  \033[31m[429]\033[0m OpenRouter rate-limit hits in %s log(s) in last 10min — timings are DIRTY\n' "$r429"; hit=1
fi

# 2. The root job that poisons every measurement — match by cmdline, not a hardcoded PID
#    that silently rots the moment the PID is recycled.
s5pids=$(pgrep -f 'run_s5_i3.py' 2>/dev/null | paste -sd' ')
if [ -n "$s5pids" ]; then
  printf '  \033[31m[CONTENTION]\033[0m root run_s5_i3.py (%s) still on OpenRouter -> sudo kill %s\n' "$s5pids" "$s5pids"; hit=1
fi

# 3. Leaked VRAM — match the vLLM engine by cmdline, and report the GPU memory actually in
#    use per index (not a fixed 'sed -n 2p' that assumes GPU ordering never changes).
vllmpids=$(pgrep -f 'VLLM::EngineCore' 2>/dev/null | paste -sd' ')
if [ -n "$vllmpids" ]; then
  gpumem=$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits 2>/dev/null \
           | awk -F', ' '$2+0>1000{printf "GPU%s=%sMiB ", $1, $2}')
  printf '  \033[33m[VRAM]\033[0m orphan vLLM (%s) holding %s-> sudo kill -9 %s\n' "$vllmpids" "${gpumem:-<none> }" "$vllmpids"; hit=1
fi

# 4. A wheel that claims a pass but committed nothing
# 5. Resource blowout
load=$(cut -d' ' -f1 /proc/loadavg)
mem=$(free -g | awk '/^Mem:/{printf "%d/%dGB", $3, $2}')
printf '  load=%s  mem=%s  gpu=%s\n' "$load" "$mem" "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader | paste -sd' ')"
[ "$hit" -eq 0 ] && printf '  \033[32mno new smoking guns\033[0m\n'
exit 0
