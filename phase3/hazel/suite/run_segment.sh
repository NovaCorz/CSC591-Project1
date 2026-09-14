#!/bin/bash
set -euo pipefail

root=/share/ece592f26/hlee58/tmp/hazel-phase3-20260911
stage=${HAZEL_STAGE:?HAZEL_STAGE is required}
constraint=${HAZEL_CONSTRAINT:?HAZEL_CONSTRAINT is required}

cd "$root/suite"
echo "Hazel segment: job=$SLURM_JOB_ID constraint=$constraint stage=$stage start=$(date --iso-8601=seconds)"
echo "Invocation: srun --cpu-bind=cores --hint=nomultithread python3 scripts/hazel_worker.py $stage"
set +e
srun --cpu-bind=cores --hint=nomultithread python3 scripts/hazel_worker.py "$stage"
status=$?
set -e
echo "Hazel segment: job=$SLURM_JOB_ID constraint=$constraint stage=$stage status=$status end=$(date --iso-8601=seconds)"
if [[ "$status" -eq 75 && "$stage" == full ]]; then
    echo "Submitting one dependency-ordered continuation for checkpointed baseline acquisition"
    python3 "$root/suite/submit.py" "$constraint" full --continuation-of "$SLURM_JOB_ID"
    exit 0
fi
if [[ "$status" -eq 0 && "$stage" == full ]]; then
    echo "Submitting compute-node raw validation and blind baseline inference"
    python3 "$root/suite/submit_analysis.py" "$constraint"
fi
exit "$status"
