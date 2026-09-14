#!/bin/bash
set -euo pipefail
root=/share/ece592f26/hlee58/tmp/hazel-phase3-20260911
constraint=${1:?constraint required}
cd "$root/suite"
srun --cpu-bind=cores python3 scripts/hazel_analyze_baseline.py "$constraint"
python3 "$root/suite/submit_aux.py" "$constraint" page_control
python3 "$root/suite/submit_aux.py" "$constraint" independent_load
python3 "$root/suite/submit_followup.py" "$constraint" smoke
