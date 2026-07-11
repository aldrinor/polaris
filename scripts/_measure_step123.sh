#!/bin/bash
# MEASURE STEP 1+2+3 together on a CHEAP subset of the MEGA-section (section 4, residual, 274 baskets).
# Section 4's views are ALL role=primary, so --cap-primary CAP truncates it to a fixed CAP-basket subset
# of the SAME long-pole section — the valid small-scale exercise of intra-section basket concurrency.
#   STEP 1: PG_COMPOSE_BASKET_WORKERS=16  (map-then-reduce parallelizes the baskets)
#   STEP 2: PG_SIDE_JUDGE_MAX_CONCURRENCY=16 PG_MAX_CONCURRENT_LLM=48 PG_ABSTRACTIVE_WRITER_CONCURRENCY=24
#   STEP 3: PG_JUDGE_BURST_SPREAD=lb       (spread the judge burst across the ~27 glm-5.2 endpoints)
# Measures via _hb_probe_run.py: basket_max_concurrent (target -> 16), hb_max_loop_gap_s (<2s), and 429s.
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
WT=/home/polaris/wt/compose_fix
cd "$WT" || exit 9
export PYTHONPATH="$WT" PYTHONIOENCODING=utf-8

# activation flag slate (identical to the compose launcher)
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1 PG_SECTION_BASKET_MAP=1 PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1 PG_VERIFIED_COMPOSE=1 PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce PG_WRITER_DEADLINE_TRANSPORT_AWARE=1
export PG_CROSS_SECTION_REPETITION_GUARD=1 PG_RENDER_SEAM_SANITIZE=1
export PG_WRITER_WALL_BASKET_SCALED=1 PG_WRITER_KSPAN_RECOVERY_PASS=1
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=300 PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=1400
# I-arch-007-tail: FAIL-FAST the trickle-hung judge. Cut the per-call wall 300->120 so a stuck
# glm-5.2 host frees its side-judge slot in <=120s (was 300s), and RAISE the total-deadline retry
# budget 1->2 so total attempt budget (3x120=360s across THREE ROTATED hosts) still covers a
# slow-but-real response. Faithfulness-safe: rotation+retry recovers a REAL verdict, never a bare
# deadline cut that could flip KEEP->DROP.
export PG_ENTAILMENT_TOTAL_S=120 PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=2 PG_PARALLEL_VERIFY=8
# rotate the pinned judge host on a fault (blank/bad-verdict/total_deadline) across the mirror chain
export PG_JUDGE_PROVIDER_ROTATE=1
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072 PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000

# ── THE LEVERS UNDER TEST ──
export PG_COMPOSE_BASKET_WORKERS="${PG_COMPOSE_BASKET_WORKERS:-16}"   # STEP 1
export PG_SIDE_JUDGE_MAX_CONCURRENCY=16                                # STEP 2
export PG_MAX_CONCURRENT_LLM=48                                        # STEP 2
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=24                            # STEP 2
export PG_MAX_PARALLEL_SECTIONS=1                                      # single section 4 in this probe
export PG_JUDGE_BURST_SPREAD="${PG_JUDGE_BURST_SPREAD:-lb}"           # STEP 3

CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
CAP="${CAP:-20}"
OUT="$WT/outputs/s5_measure_bw${PG_COMPOSE_BASKET_WORKERS}_bs${PG_JUDGE_BURST_SPREAD}"
mkdir -p "$OUT"
LOG="$OUT/measure.log"

export HB_MODE=offloop
echo "=== measure launch $(date -u) commit=$(git rev-parse HEAD) BW=$PG_COMPOSE_BASKET_WORKERS BS=$PG_JUDGE_BURST_SPREAD CAP=$CAP sections=4 ===" | tee "$LOG"
python -u scripts/_hb_probe_run.py \
  --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
  --out "$OUT/cp5_generation_snapshot.json" --sections 4 --cap-primary "$CAP" >> "$LOG" 2>&1
RC=$?
echo "=== measure rc=$RC ===" | tee -a "$LOG"
echo "--- 429 count ---" | tee -a "$LOG"
grep -c -iE "429|rate.?limit|too many request" "$LOG" | tee -a "$LOG"
exit $RC
