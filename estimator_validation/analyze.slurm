#!/bin/bash
#SBATCH --job-name=estimator-validation
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=3G
#SBATCH --time=00:10:00
#SBATCH --output=estimator_validation/analysis.%j.stdout
#SBATCH --error=estimator_validation/analysis.%j.stderr
set -euo pipefail
cd /gpfs_common/share03/rotenberg/hlee58/ECE592_proj1
export PYTHONPATH=/share/ece592f26/hlee58/tmp/hazel-phase3-20260911/tools/python-packages
export MPLCONFIGDIR="${SLURM_TMPDIR:-/tmp}/estimator-validation-${SLURM_JOB_ID}"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
srun --cpu-bind=cores python3 estimator_validation/analyze.py
