#!/usr/bin/env bash
# Deep-think GATE = Codex 5.6 Sol Max. Reasoning-VISIBLE (streams detailed summaries to the events file
# so Opus can watch/assess the cognition), answer captured via -o, on the user's plan (danger-full-access
# avoids the broken bwrap). COST: caller MUST keep the prompt under ~258K tokens (272K cliff = 2x/1.5x).
# Usage: codex_gate.sh <answer_file> <events_file> [timeout_s]  < prompt
ANS="${1:?answer_file}"; EV="${2:?events_file}"; TO="${3:-1800}"
mkdir -p "$(dirname "$ANS")" "$(dirname "$EV")"; rm -f "$ANS"
cd /tmp/codex_scratch 2>/dev/null || cd /tmp
timeout "$TO" codex exec -s danger-full-access --skip-git-repo-check --json \
  -c model_reasoning_effort=high -c model_reasoning_summary=detailed -o "$ANS" > "$EV" 2>/tmp/codex_gate.err
rc=$?
echo "codex_gate exit=$rc answer_lines=$(wc -l <"$ANS" 2>/dev/null||echo 0) events=$(wc -l <"$EV" 2>/dev/null||echo 0)"
