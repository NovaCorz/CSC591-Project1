#!/bin/bash
echo "Starting Bash script..."

# Call the python file
./phase2_survey.sh > survey_$(hostname).txt

python3 pmu_eight_counter.py \
    --binary main_code/common/phase1/src/cache_bench --pmu-stat main_code/pmu/pmu_stat \
    --cpu <pinned CPU> --spacing 8 --samples 1000000 --steps 4096 --seed 592 \
    --l1-kib 34.0 --llc-kib 20480.0 --over-llc-kib 131072.0 \
    --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,dTLB-read-miss,cache-misses \
    --out data_raw/<hostname>/pmu/eight_counter-$(date +%Y%m%d)

python3 boundary_correlation.py \
    --host <hostname> --level l1 \
    --boundaries-json phase1_boundaries.json \
    --host-config main_code/common/phase1/config/followup-plan.json \
    --binary main_code/common/phase1/src/cache_bench \
    --pmu-stat main_code/pmu/pmu_stat \
    --cpu 2 \
    --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,dTLB-read-miss,cache-misses \
    --out data_raw/<hostname>/pmu/boundary_correlation-$(date +%Y%m%d)_l1

python3 boundary_correlation.py \
    --host <hostname> --level l2 \
    --boundaries-json phase1_boundaries.json \
    --host-config main_code/common/phase1/config/followup-plan.json \
    --binary main_code/common/phase1/src/cache_bench \
    --pmu-stat main_code/pmu/pmu_stat \
    --cpu 2 \
    --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,dTLB-read-miss,cache-misses \
    --out data_raw/<hostname>/pmu/boundary_correlation-$(date +%Y%m%d)_l2

python3 boundary_correlation.py \
    --host <hostname> --level llc \
    --boundaries-json phase1_boundaries.json \
    --host-config main_code/common/phase1/config/followup-plan.json \
    --binary main_code/common/phase1/src/cache_bench \
    --pmu-stat main_code/pmu/pmu_stat \
    --cpu 2 \
    --events cycles,instructions,L1D-read-access,L1D-read-miss,LL-read-access,LL-read-miss,dTLB-read-miss,cache-misses \
    --out data_raw/<hostname>/pmu/boundary_correlation-$(date +%Y%m%d)_llc

echo "Bash script finished."