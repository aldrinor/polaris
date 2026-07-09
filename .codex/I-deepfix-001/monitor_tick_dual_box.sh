#!/bin/bash
# Dual-box military-order forensic tick — I-deepfix-001 wave-2 (#1370).
# CONTENT-READ PRIMARY (read every new line, catch the UNANTICIPATED problem) + 14-fix overlay.
# Reads EVERY new content line from BOTH boxes since the last byte-offset, per box, then the
# fetch-yield-first number + the fix-signal/red-flag overlay. Claude consolidates both boxes into
# ONE report to the operator each 5 min. RED FLAG -> IMMEDIATE Codex+Fable escalation (they decide
# hold/fix/relaunch-from-nearest-checkpoint vs let-run). Content read is the monitor; the greps are
# only a checklist so an inert flag or a known red does not slip past while reading.
#
# Set at launch (the actual run logs on each box):
#   BOX2_LOG  e.g. /workspace/paid_drb72_deep_wave3.log     (resume box, ssh6:38794)
#   BOX1_LOG  e.g. /workspace/paid_drb72_fresh_wave3.log    (fresh box,  ssh9:20988)
set -o pipefail
SO="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=25 -o ServerAliveInterval=20"

read_box () {
  local port="$1" host="$2" log="$3" tag="$4" offfile="$5"
  timeout 55 ssh -p "$port" $SO "$host" "
    L='$log'; OFF=\$(cat '$offfile' 2>/dev/null || echo 0); SZ=\$(stat -c%s \"\$L\" 2>/dev/null || echo 0)
    NOW=\$(date +%s); LMOD=\$(stat -c %Y \"\$L\" 2>/dev/null || echo \$NOW)
    echo '=== $tag | '\$(date -u +%H:%M:%S)' | alive='\$(pgrep -f run_gate_b.py | grep -v pgrep | head -1 || echo DEAD)' | silent='\$((NOW-LMOD))'s | new_bytes='\$((SZ-OFF))' ==='
    NEW=\$(tail -c +\$((OFF+1)) \"\$L\")
    # (0) CRASH / STALL scan
    echo '-- (0) CRASH --'; echo \"\$NEW\" | grep -aE 'Traceback|CUBLAS|CUDA out of memory|MemoryError|faulthandler|force-close' | tail -6 | cut -c1-180
    # (1) FETCH-YIELD FIRST (operator hard rule 2026-07-07) + A15 on resume
    echo '-- (1) FETCH-YIELD --'; echo \"\$NEW\" | grep -aE 'fetch_yield_gate|fetched=[0-9]|A15 refresh|A15 RE-FETCH|attempted=[0-9]|corpus ACCEPTED|weighted_mean' | tail -5 | cut -c1-180
    # (2) CONTENT — EVERY new line (strip ONLY literal tqdm spinner + pure boilerplate)
    echo '-- (2) CONTENT (every line, read it all) --'
    echo \"\$NEW\" | grep -avE 'Batches: +[0-9]+%\\|.*\\||^\\[A|^[[:space:]]*\$|OpenRouter client initialized|POOL-1: Reasoning logged' | tail -240 | cut -c1-200
    # (3) 14-FIX GREEN MARKERS (checklist overlay — did each fix fire at its stage)
    echo '-- (3) FIX SIGNALS --'; echo \"\$NEW\" | grep -aoE 'compose_offtopic_basket_screen: withheld=[0-9]+ kept=[0-9]+|\\[B1-FURNITURE\\][^\"]{0,60}|verified-compose PRIMARY: [0-9]+ baskets[^\"]{0,40}|pre-pass complete: [0-9]+/[0-9]+|K-span recovery pass[^\"]{0,40}|B3:[^\"]{0,50}rebuilt client|WS-1\\(b\\)[^\"]{0,40}|think-leak[^\"]{0,40}|fragment-prose dedup[^\"]{0,40}|summary_table[^\"]{0,30}anchored=(True|False)|FINDING#5[^\"]{0,40}|framing[- ]only|release_allowed=(True|False)' | tail -30
    # (4) RED FLAGS (kill-or-escalate triggers)
    echo '-- (4) RED FLAGS --'; echo \"\$NEW\" | grep -aiE 'Server disconnected|Task exception was never retrieved|429|circuit breaker OPEN|WALL-DEADLINE.*ABANDONING|all-chrome basket|kept=0|abort_|RunValidityGateError|fourth industrial revolution|mineru25 timed out after 75s' | tail -12 | cut -c1-170
    echo \"\$SZ\" > '$offfile'
  " 2>&1 | grep -aviE 'vast\.ai|Have fun|authentication'
}

echo "############## DUAL-BOX FORENSIC TICK  $(date -u +%Y-%m-%dT%H:%M:%SZ) ##############"
echo ">>>>>>>>>> BOX 2 (RESUME, ssh6:38794) <<<<<<<<<<"
read_box 38794 root@ssh6.vast.ai "${BOX2_LOG:?set BOX2_LOG}" "BOX2-RESUME" /workspace/.tick_off_box2
echo ""
echo ">>>>>>>>>> BOX 1 (FRESH, ssh9:20988) <<<<<<<<<<"
read_box 20988 root@ssh9.vast.ai "${BOX1_LOG:?set BOX1_LOG}" "BOX1-FRESH" /workspace/.tick_off_box1
echo "############## END TICK ##############"
