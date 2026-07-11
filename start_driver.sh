#!/bin/bash
export HOME=/home/polaris
cd /home/polaris/polaris_project || exit 1
i=0
while true; do
  i=$((i+1))
  echo "=== driver start #$i $(date -u) ===" >> driver.log
  s=$(date +%s)
  claude -p "$(cat DRIVER_PROMPT.txt)" --dangerously-skip-permissions --verbose >> driver.log 2>&1
  e=$(date +%s)
  echo "=== driver exited #$i after $((e-s))s $(date -u) ===" >> driver.log
  if [ $((e-s)) -lt 60 ]; then sleep 120; else sleep 15; fi
done
