#!/bin/bash
set -euo pipefail
root=/share/ece592f26/hlee58/tmp/hazel-phase3-20260911
constraint=${HAZEL_CONSTRAINT:?HAZEL_CONSTRAINT required}
stage=${HAZEL_STAGE:?HAZEL_STAGE required}
cd "$root/suite"
set +e
srun --distribution=block:block --cpu-bind=cores --hint=nomultithread python3 scripts/hazel_followup_worker.py "$stage"
status=$?
set -e
echo "Follow-up segment job=$SLURM_JOB_ID constraint=$constraint stage=$stage status=$status end=$(date --iso-8601=seconds)"
if [[ "$status" -eq 75 ]]; then
    python3 "$root/suite/submit_followup.py" "$constraint" "$stage" --continuation-of "$SLURM_JOB_ID"
    exit 0
fi
if [[ "$status" -eq 0 ]]; then
    if [[ "$stage" == inclusion_final ]]; then
        python3 "$root/suite/submit_followup_analysis.py" "$constraint"
    else
        python3 "$root/suite/submit_followup.py" "$constraint" --next-after "$stage"
    fi
fi
exit "$status"
