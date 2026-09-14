#!/bin/bash
echo "Starting Bash script..."

# Call the python file
./phase2_survey.sh > survey_thunderbird.txt

python3 pmu_eight_counter.py \
    --binary ../main_code/common/phase1/src/cache_bench --pmu-stat ../main_code/pmu/pmu_stat \
    --cpu 3 --stride 8 --samples 1000000 --batch 512 --seed 5922026 \
    --l1-kib 34.0 --llc-kib 20480.0 --over-llc-kib 131072.0 \
    --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,DTLB-read-miss,cache-misses \
    --events-per-run 2 \
    --out ../data_raw/thunderbird/pmu/eight_counter

python3 boundary_correlation.py \
    --host thunderbird \
    --level l1 \
    --boundaries-json phase1_boundaries.json \
    --host-config ../main_code/common/phase1/config/followup-plan.json \
    --binary ../main_code/common/phase1/src/cache_bench \
    --pmu-stat ../main_code/pmu/pmu_stat \
    --cpu 3 \
    --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,DTLB-read-miss,cache-misses \
    --events-per-run 2 \
    --out ../data_raw/thunderbird/pmu/boundary_correlation_l1

python3 boundary_correlation.py \
    --host thunderbird \
    --level l2 \
    --boundaries-json phase1_boundaries.json \
    --host-config ../main_code/common/phase1/config/followup-plan.json \
    --binary ../main_code/common/phase1/src/cache_bench \
    --pmu-stat ../main_code/pmu/pmu_stat \
    --cpu 3 \
    --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,DTLB-read-miss,cache-misses \
    --events-per-run 2 \
    --out ../data_raw/thunderbird/pmu/boundary_correlation_l2

python3 boundary_correlation.py \
    --host thunderbird \
    --level llc \
    --boundaries-json phase1_boundaries.json \
    --host-config ../main_code/common/phase1/config/followup-plan.json \
    --binary ../main_code/common/phase1/src/cache_bench \
    --pmu-stat ../main_code/pmu/pmu_stat \
    --cpu 3 \
    --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,DTLB-read-miss,cache-misses \
    --events-per-run 2 \
    --out ../data_raw/thunderbird/pmu/boundary_correlation_llc

python3 stride_correlation.py \
      --host thunderbird --binary ../common/phase1/src/cache_bench \
      --pmu-stat ../pmu/pmu_stat --cpu 3 \
      --host-config ../common/phase1/config/followup-plan.json \
      --events cycles,instructions,L1D-read-access,L1D-read-miss \
      --out ../../data_raw/thunderbird/pmu/stride_correlation

python3 associativity_correlation.py \
      --host charnwood --level l1 \
      --plan-json ../common/phase1/config/uncertainty-plan.json \
      --binary ../common/phase1/src/followup_bench \
      --pmu-stat ../pmu/pmu_stat --cpu 2 \
      --events cycles,instructions,L1D-read-access,L1D-read-miss,cache-misses \
      --events-per-run 2 \
      --out ../../data_raw/charnwood/pmu/associativity_correlation_l1

python3 associativity_correlation.py \
      --host charnwood --level l2 --period 32768 --ways 4 \
      --binary ../common/phase1/src/followup_bench \
      --pmu-stat ../pmu/pmu_stat --cpu 2 \
      --events cycles,instructions,LL-read-access,LL-read-miss,cache-misses \
      --events-per-run 2 \
      --out ../../data_raw/charnwood/pmu/associativity_correlation_l2

echo "Bash script finished."