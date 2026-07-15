#!/usr/bin/env bash
# OVERNIGHT SUPERVISOR — mechanical auto-recovery + wakes Claude for judgment.
# Survives: stall(CPU-flat), dead(no proc), silent(no log), orphan-pileup, overlong-run.
# Exits (=> re-invokes Claude) on: REPORT ready, STALL killed, or ~10min periodic review.
WT=/home/polaris/wt/outline_agent
STATUS=/home/polaris/polaris_project/overnight_status.txt
SEEN=/tmp/seen_reports.txt; touch "$SEEN"
hb(){ echo "$(date -u +'%m-%d %H:%M:%S') | $1" >> "$STATUS"; }
py(){ for x in $(pgrep -u polaris -f 'python.*compose_agentic' 2>/dev/null); do echo "$(ps -o %cpu= -p $x 2>/dev/null|tr -d ' '|cut -d. -f1) $x"; done|sort -rn|head -1|awk '{print $2}'; }
last_progress=$(date +%s)
hb "supervisor armed (10min review, 30min-stall auto-kill, orphan cleanup)"
for cycle in $(seq 1 15); do   # ~15 * 40s = 10min per arming; Claude re-arms each wake
  # 1. NEW report? -> wake to score
  nr=$(find "$WT/outputs" -name 'report.md' -mmin -12 2>/dev/null | while read r; do k="$r:$(stat -c %Y "$r" 2>/dev/null)"; grep -qxF "$k" "$SEEN" || { echo "$k">>"$SEEN"; echo "$r"; }; done | head -1)
  [ -n "$nr" ] && { hb "REPORT READY -> wake Claude to score: $nr"; echo "WAKE=REPORT|$nr"; exit 0; }
  # 2. progress? (python compose CPU rising)
  p=$(py)
  if [ -n "$p" ]; then
    a=$(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null); sleep 20; b=$(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null)
    [ "${b:-0}" -gt "${a:-0}" ] 2>/dev/null && last_progress=$(date +%s)
  else sleep 20; fi
  # 3. STALL > 30min -> mechanical kill + wake to relaunch
  mins=$(( ($(date +%s)-last_progress)/60 ))
  if [ "$mins" -ge 30 ]; then
    hb "STALL ${mins}min: killing wedged composes, waking Claude to relaunch"
    pkill -9 -u polaris -f 'compose_agentic' 2>/dev/null
    echo "WAKE=STALL_KILLED|${mins}min"; exit 0
  fi
  # 4. orphan/overlong cleanup (a render should never exceed 55min)
  for x in $(pgrep -u polaris -f 'python.*compose_agentic' 2>/dev/null); do
    et=$(ps -o etimes= -p $x 2>/dev/null|tr -d ' '); [ "${et:-0}" -gt 3300 ] && { hb "killing overlong compose $x (${et}s)"; kill -9 $x 2>/dev/null; }
  done
  hb "cycle$cycle: compose=${p:-none} stall=${mins}min"
  sleep 20
done
hb "10min review checkpoint -> wake Claude"
echo "WAKE=PERIODIC_10min"; exit 0
