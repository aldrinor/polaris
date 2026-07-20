#!/usr/bin/env bash
# Score a composed report with the official DeepResearch Bench FACT pipeline (citation trustworthiness).
# Stages: build target jsonl -> extract -> deduplicate -> scrape (Jina) -> validate -> stat -> fact_result.txt
# Outputs: <DRB>/results/fact/<model_name>/fact_result.txt  (total_citations, total_valid_citations, valid_rate)
#
# Usage: scripts/score_report_fact.sh <report.md> <model_name> [task_id]
# Env overrides: DRB (benchmark dir), PY (interpreter), ENV_FILE (dotenv), FACT_MODEL.
set -uo pipefail
REPORT="$1"; NAME="$2"; TASK="${3:-72}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DRB="${DRB:-$REPO/third_party/deep_research_bench}"
PY="${PY:-/home/polaris/pipeline-env/bin/python}"     # torch cu128 env (same interpreter as run_raw_a.sh)
ENV_FILE="${ENV_FILE:-/workspace/POLARIS/.env}"
[ -d "$DRB" ] || { echo "FACT: benchmark dir not found: $DRB (set DRB=...)"; exit 2; }
cd "$DRB"

export LLM_BACKEND=openrouter
export FACT_MODEL="${FACT_MODEL:-openai/gpt-5.4-mini}"    # official FACT judge
export OPENROUTER_API_KEY="$("$PY" -c "from dotenv import dotenv_values;print(dotenv_values('$ENV_FILE')['OPENROUTER_API_KEY'])")"
export JINA_API_KEY="$("$PY" -c "from dotenv import dotenv_values;print(dotenv_values('$ENV_FILE').get('JINA_API_KEY',''))")"
unset PYTHONPATH
export PYTHONUNBUFFERED=1

# Build the target jsonl {id,prompt,article} from the report + the benchmark prompt for this task.
"$PY" - "$REPORT" "$NAME" "$TASK" <<'PYEOF'
import json,sys
report,name,task=sys.argv[1],sys.argv[2],sys.argv[3]
art=open(report,encoding='utf-8').read()
prompt=None
for line in open("data/prompt_data/query.jsonl",encoding='utf-8'):
    o=json.loads(line)
    if str(o["id"])==str(task): prompt=o["prompt"]; break
assert prompt, f"task {task} not in query.jsonl"
open(f"data/test_data/raw_data/{name}.jsonl","w",encoding='utf-8').write(
    json.dumps({"id":int(task),"prompt":prompt,"article":art},ensure_ascii=False)+"\n")
print(f"[fact] wrote raw_data/{name}.jsonl article_chars={len(art)}")
PYEOF

OUT="results/fact/$NAME"; mkdir -p "$OUT"
Q="data/prompt_data/query.jsonl"; N="${N_TOTAL_PROCESS:-6}"
run(){ echo "### $1"; shift; "$@"; rc=$?; [ $rc -ne 0 ] && { echo "STAGE_FAILED rc=$rc"; exit $rc; }; }
run extract      "$PY" -u -m utils.extract     --raw_data_path "data/test_data/raw_data/$NAME.jsonl" --output_path "$OUT/extracted.jsonl"    --query_data_path "$Q" --n_total_process "$N"
run deduplicate  "$PY" -u -m utils.deduplicate --raw_data_path "$OUT/extracted.jsonl"                --output_path "$OUT/deduplicated.jsonl" --query_data_path "$Q" --n_total_process "$N"
run scrape       "$PY" -u -m utils.scrape      --raw_data_path "$OUT/deduplicated.jsonl"            --output_path "$OUT/scraped.jsonl"      --n_total_process "$N"
run validate     "$PY" -u -m utils.validate    --raw_data_path "$OUT/scraped.jsonl"                 --output_path "$OUT/validated.jsonl"    --query_data_path "$Q" --n_total_process "$N"
run stat         "$PY" -u -m utils.stat        --input_path "$OUT/validated.jsonl"                  --output_path "$OUT/fact_result.txt"
echo "===== FACT RESULT ($NAME) ====="; cat "$OUT/fact_result.txt"
echo "FACT_DONE"
