#!/bin/bash
set -euo pipefail
cd /share/ece592f26/hlee58/tmp/hazel-phase3-20260911/suite
srun --cpu-bind=cores python3 scripts/summarize_hazel.py --hosts haswell cascadelake icelake_8358 genoa turin
srun --cpu-bind=cores python3 scripts/package_hazel_results.py --skip-plots
