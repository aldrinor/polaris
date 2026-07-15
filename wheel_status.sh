#!/usr/bin/env bash
# WHEEL STATUS — one line of truth about everything that is ACTUALLY running.
# Used by the 5-minute watchdog during autonomous operation.
#
# A killed or completed workflow leaves its files behind, so "idle" alone is not a stall signal.
# We therefore track only workflows listed in ACTIVE_WF (written when a workflow is launched, cleared
# when it lands or is killed). A noisy alarm is as bad as no alarm.

SESS=/home/polaris/.claude/projects/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e
FW=/home/polaris/wt/flywheel
ACTIVE=/home/polaris/polaris_project/.active_wf     # one workflow run-id per line
now=$(date +%s)
out=""
alarm=""

# --- 1. ONLY the workflows we declared active ----------------------------
if [ -s "$ACTIVE" ]; then
  while read -r wf; do
    [ -z "$wf" ] && continue
    d="$SESS/subagents/workflows/$wf"
    j="$d/journal.jsonl"
    [ -f "$j" ] || { out="$out ${wf:3:8}(starting)"; continue; }
    newest=$(ls -t "$d"/*.jsonl 2>/dev/null | head -1)
    nmt=$(stat -c %Y "$newest" 2>/dev/null || echo "$now")
    idle=$(( (now - nmt) / 60 ))
    dn=$(grep -c '"type":"result"' "$j" 2>/dev/null || echo 0)
    live=$(ls "$d"/agent-*.jsonl 2>/dev/null | wc -l)
    # HUNG = agents outstanding AND nothing written for 15m
    if [ "$idle" -ge 15 ] && [ "$live" -gt "$dn" ]; then
      alarm="${alarm}🚨 WORKFLOW HUNG: $wf idle ${idle}m ($dn done / $live agents) — RESTART IT\n"
    fi
    out="$out ${wf:3:8}($dn/$live,${idle}m)"
  done < "$ACTIVE"
fi

# --- 2. composes (the expensive thing; rank10 took ~65m) ------------------
for p in $(pgrep -f "compose_agentic_report|cellcog_composer" 2>/dev/null); do
  et=$(ps -p "$p" -o etimes= 2>/dev/null | tr -d ' ')
  out="$out compose($((et/60))m)"
  [ "${et:-0}" -gt 6600 ] && alarm="${alarm}🚨 COMPOSE STUCK: pid $p at $((et/60))m (expected ~65m) — KILL AND DIAGNOSE\n"
done

# --- 3. scorers / judge --------------------------------------------------
for p in $(pgrep -f "score_report_race|judge_feedback|criterion_ab" 2>/dev/null); do
  et=$(ps -p "$p" -o etimes= 2>/dev/null | tr -d ' ')
  out="$out score($((et/60))m)"
  [ "${et:-0}" -gt 3600 ] && alarm="${alarm}🚨 SCORER STUCK: pid $p at $((et/60))m — KILL AND RETRY\n"
done

# --- 4. THE INTEGRITY FLAG — the unlocked door, reported every 5 minutes --
if grep -qE "^\s+ok, why = validate\(|validate\(Synthesis|= validate\(" "$FW/scripts/cellcog_composer.py" 2>/dev/null; then
  gate="WIRED"
else
  gate="**UNWIRED**"      # 43% of mechanisms are fabricated behind this door
fi

# --- 5. git: nothing may sit un-pushed ----------------------------------
cd "$FW" 2>/dev/null || { echo "heartbeat: (no worktree)"; exit 0; }
dirty=$(git status --porcelain 2>/dev/null | wc -l)
head_sha=$(git rev-parse --short flywheel-v1 2>/dev/null)
[ "$dirty" -gt 0 ] && out="$out git(${dirty}-UNCOMMITTED)"

[ -n "$alarm" ] && printf "%b" "$alarm"
echo "heartbeat:${out:-  idle} | gate:$gate | head:$head_sha"
