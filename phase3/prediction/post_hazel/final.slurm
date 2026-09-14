#!/bin/bash
#SBATCH --job-name=hz-compare-final
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=3G
#SBATCH --time=00:10:00
set -euo pipefail
cd /gpfs_common/share03/rotenberg/hlee58/ECE592_proj1
export PYTHONPATH=/share/ece592f26/hlee58/tmp/hazel-phase3-20260911/tools/python-packages
export MPLCONFIGDIR="${SLURM_TMPDIR:-/tmp}/hz-final-mpl-${SLURM_JOB_ID}"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
srun --cpu-bind=cores python3 prediction/post_hazel/build.py --output "prediction/post_hazel/results-${SLURM_JOB_ID}"
srun --cpu-bind=cores python3 prediction/post_hazel/audit.py "prediction/post_hazel/results-${SLURM_JOB_ID}"
