#!/bin/bash
#SBATCH --job-name=cache-estimator
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:15:00
#SBATCH --output=estimator.%j.stdout
#SBATCH --error=estimator.%j.stderr
set -euo pipefail
# Submit from the repository root. Add a required generation constraint at submission.
srun --cpu-bind=cores python3 competition/run.py --output "${SLURM_SUBMIT_DIR}/competition-runs/job-${SLURM_JOB_ID}" "$@"
