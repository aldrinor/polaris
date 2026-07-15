#!/usr/bin/env bash
# POLARIS master monitoring deck. Read-only. Run any time: bash deck.sh
# LAW VI: every knob env-tunable (override WFDIR/WT_BASE/DECK_WHEELS/DECK_COMMIT_WINDOW to test).
WFDIR=${WFDIR:-/home/polaris/.claude/projects/-home-polaris-polaris-project/ea997c8e-37cf-4d9a-8a80-f7728137f18b/subagents/workflows}
WT_BASE=${WT_BASE:-/home/polaris/wt}
DECK_WHEELS=${DECK_WHEELS:-outline_agent tooluse compose}
DECK_COMMIT_WINDOW=${DECK_COMMIT_WINDOW:-2 hours ago}

printf '\033[1m=== POLARIS DECK  %s UTC ===\033[0m\n' "$(date -u +%H:%M:%S)"

printf '\n\033[1m-- wheels (workflow journals) --\033[0m\n'
for wf in "$WFDIR"/wf_*; do
  [ -d "$wf" ] || continue
  j="$wf/journal.jsonl"
  [ -f "$j" ] || { printf '  %-18s (no journal yet)\n' "$(basename "$wf")"; continue; }
  # Journals only contain "started"/"result" events (no "agent_end"/"message" keys).
  # Count completed agents by the key that actually exists.
  n=$(grep -c '"type":"result"' "$j" 2>/dev/null); n=${n:-0}
  # Status: prefer a known status field from any result record; else summarize the last
  # result record; else fall back to the last started agentId. Never the nonexistent "message".
  last=$(grep -oE '"(verdict|fatal|honest_status|sign_off_reason)":"[^"]{0,90}' "$j" 2>/dev/null | tail -1)
  [ -z "$last" ] && last=$(grep '"type":"result"' "$j" 2>/dev/null | tail -1 \
        | grep -oE '"result":(\{"[a-zA-Z_]+":[^,}]{0,60}|"[^"]{0,80})' | head -1)
  [ -z "$last" ] && last=$(grep '"type":"started"' "$j" 2>/dev/null | tail -1 \
        | grep -oE '"agentId":"[^"]{0,20}')
  last=${last//\"/}
  printf '  %-18s agents_done=%-3s %s\n' "$(basename "$wf" | cut -c1-18)" "$n" "${last:0:95}"
done

printf '\n\033[1m-- commits (is anything actually landing?) --\033[0m\n'
for d in $DECK_WHEELS; do
  wt=$WT_BASE/$d
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
#    NUL-delimited so log paths containing spaces are not split/mangled.
r429=$(find "$WT_BASE" /workspace/POLARIS/logs -name '*.log' -mmin -10 -print0 2>/dev/null \
       | grep -zv '/\.codex/' \
       | xargs -0 -r grep -lEi '429 Too Many|HTTP[^0-9]*429|rate.?limit' 2>/dev/null | wc -l)
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

# 4. A wheel that CLAIMS A PASS but committed nothing recently — the "green board, empty repo"
#    smoking gun. A journal claims a pass if any result carries verdict":"PASS or sign_off":true.
#    We flag when such a claim exists yet NO tracked wheel worktree has a commit inside the
#    window. (No reliable journal->worktree name mapping exists in the schema, so this is an
#    aggregate check: pass claimed somewhere, but nothing landed anywhere.)
pass_claimed=""
for wf in "$WFDIR"/wf_*; do
  j="$wf/journal.jsonl"; [ -f "$j" ] || continue
  if grep -qE '"verdict":"PASS"|"sign_off":true' "$j" 2>/dev/null; then
    pass_claimed="$pass_claimed $(basename "$wf" | cut -c1-15)"
  fi
done
if [ -n "$pass_claimed" ]; then
  recent_commit=0
  for d in $DECK_WHEELS; do
    wt=$WT_BASE/$d; [ -d "$wt" ] || continue
    if [ -n "$(git -C "$wt" log -1 --since="$DECK_COMMIT_WINDOW" --pretty=%h 2>/dev/null)" ]; then
      recent_commit=1; break
    fi
  done
  if [ "$recent_commit" -eq 0 ]; then
    printf '  \033[31m[NO-COMMIT-PASS]\033[0m journal(s)%s claim a PASS but no wheel worktree committed within "%s"\n' "$pass_claimed" "$DECK_COMMIT_WINDOW"; hit=1
  fi
fi

# 5. Resource blowout
load=$(cut -d' ' -f1 /proc/loadavg)
mem=$(free -g | awk '/^Mem:/{printf "%d/%dGB", $3, $2}')
printf '  load=%s  mem=%s  gpu=%s\n' "$load" "$mem" "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader | paste -sd' ')"
[ "$hit" -eq 0 ] && printf '  \033[32mno new smoking guns\033[0m\n'
exit 0
