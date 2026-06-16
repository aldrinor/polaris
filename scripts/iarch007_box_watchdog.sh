#!/bin/bash
SLUG="$1"; PIDFILE="$2"
OUT=/root/polaris/outputs/beatboth_full
WLOG=$OUT/${SLUG}_watchdog.log
cd /root/polaris || exit 1
n=0; max=3
echo "[wd $(date -u +%H:%M)] start slug=$SLUG pid=$PIDFILE" >> $WLOG
while [ $n -lt $max ]; do
  sleep 300
  if find $OUT -path "*${SLUG}*" -name report.md 2>/dev/null | grep -q .; then
    echo "[wd $(date -u +%H:%M)] report.md present -> exit" >> $WLOG; exit 0; fi
  PID=$(cat $OUT/$PIDFILE 2>/dev/null)
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then continue; fi
  n=$((n+1))
  echo "[wd $(date -u +%H:%M)] proc '$PID' DEAD + no report -> relaunch --resume #$n/$max" >> $WLOG
  export PYTHONPATH=/root/polaris:/root/polaris/src
  export PG_FOUR_ROLE_REASONING_EFFORT=medium PG_CAPTURE_RAW_LLM_IO=1 PG_AUTHORIZED_SWEEP_APPROVAL=1 PG_STORM_OUTLINE_CALL_TIMEOUT_S=300
  setsid nohup /opt/conda/bin/python -m scripts.dr_benchmark.run_gate_b --only "$SLUG" --out-root outputs/beatboth_full --resume >> $OUT/${SLUG}_launch.log 2>&1 &
  echo $! > $OUT/$PIDFILE
  echo "[wd $(date -u +%H:%M)] relaunched pid=$(cat $OUT/$PIDFILE)" >> $WLOG
done
echo "[wd $(date -u +%H:%M)] max relaunch hit -> give up, surface in summary" >> $WLOG
