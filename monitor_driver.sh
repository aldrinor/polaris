#!/usr/bin/env bash
# Read-only pulse on the overnight driver. Touches nothing the driver owns.
DRIVER_PID=${1:-987961}

printf '=== %s UTC ===\n' "$(date -u +%H:%M:%S)"

if ps -p "$DRIVER_PID" >/dev/null 2>&1; then
  read -r etimes pcpu <<<"$(ps -o etimes=,%cpu= -p "$DRIVER_PID")"
  kids=$(pgrep -P "$DRIVER_PID" | wc -l)
  printf 'driver %s: ALIVE  %dm elapsed  %s%% cpu  %s child proc(s)' \
    "$DRIVER_PID" "$((etimes / 60))" "$pcpu" "$kids"
  # No children + low cpu means it is waiting on the API, not wedged.
  [ "$kids" -eq 0 ] && printf '  (idle on API call)'
  printf '\n'
else
  printf 'driver %s: NOT RUNNING\n' "$DRIVER_PID"
fi

printf '\n--- wheels ---\n'
for d in outline_agent tooluse compose; do
  wt=/home/polaris/wt/$d
  [ -d "$wt" ] || continue
  printf '%-13s %s\n' "$d" "$(git -C "$wt" log -1 --pretty='%h %ad %s' --date=format:'%H:%M' 2>/dev/null | cut -c1-90)"
done

printf '\n--- progress file ---\n'
tail -4 /home/polaris/polaris_project/OVERNIGHT_PROGRESS.md | cut -c1-130
