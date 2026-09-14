#!/bin/bash
set -euo pipefail
root=/share/ece592f26/hlee58/tmp/hazel-phase3-20260911
constraint=${1:?constraint required}
cd "$root/suite"
srun --cpu-bind=cores python3 scripts/analyze_followup.py --hosts "$constraint" --jobs 1
python3 "$root/suite/try_finalize.py"
