# Competition submission entry points

## Competition 1

`scorecard.csv` contains 48 ECE and 22 Hazel candidates, their preserved timing values, published comparisons, source locators and provisional recommendations. `scorecard-sources.json` identifies the new literature sources. Existing Hazel source citations are also in `phase3/prediction/post_hazel/inputs/published-sources.json`. Yes* denotes a qualified recommendation; Hold and No retain unresolved or disagreeing cases. The one-page report table is maintained separately.

## Competition 2

The fixed configuration is `parameters.json`. The estimator is the **unchanged** `estimator()` function in `main_code/common/phase1/scripts/analyze.py`, using the unchanged `src/cache_bench.c` and `scripts/common.py` in the same suite. `classify.py` is a command-line adapter that checks the acquired inputs and invokes that function. `run.py` compiles the native code with the original flags, selects an idle allowed core using the existing idle-selection implementation, records commands and metadata, and collects the fixed hot/target/cold footprints. It never loads the Phase-II observer or consults published cache information. Core changes produce an unresolved estimate; all output is retained. The original classifier's historical validation note is superseded by the separately linked matched comparison, not by a change to its numerical algorithm.

Run from the repository root on an ECE lab host:

```bash
python3 competition/run.py --smoke --output /path/to/new/smoke-directory
python3 competition/run.py --output /path/to/new/full-directory
```

On Hazel, submit through Slurm from the repository root:

```bash
sbatch competition/run.slurm --smoke
# After inspecting the smoke output:
sbatch competition/run.slurm
```

Each output directory must be new. Full runs collect 1,000,000 intervals at each of 1 KiB, 1 MiB and 256 MiB; smoke runs use 2,048 and are explicitly non-scoring. Compilation and measurement logs, raw uint64 arrays, idle evidence, CPU/topology, timestamps and `estimate.json` are retained. No PMU-enabled environment is inherited. Hardware timing runs must not run on an HPC login node. Select a generation constraint when required; the sample Slurm file makes no particular-generation claim.

To classify existing output, on a compute node run `python3 competition/classify.py /path/to/full-directory`. Python uses only its standard library; acquisition additionally needs GCC and `lscpu`. Native x86-64 and AArch64 timer paths are in the frozen benchmark source.

## Validation and limitations

`../estimator_validation/results/comparison.csv` is the completed eight-machine software-versus-PMU comparison; adjacent files contain calibration, raw hashes, verification and the comparison figure. `../estimator_validation/README.md` explains the differing event populations and unavailable counters. These comparisons do not establish a universal individual-load hardware hit rate. The submitted estimator remains a timing-classified residency proxy with threshold sensitivity; official acceptance of that metric is not asserted.

`freeze.json` records the release timestamp and exact source/parameter hashes. The release Git commit and named tag will identify this snapshot. Freezing now does not establish that the earlier Hazel prediction freeze preceded Hazel execution, nor that official scoring has or has not already occurred. The original prediction artifacts and their timestamps are preserved.

## Raw data

Use `estimator_validation/raw-archive-locations.json`, `phase3/hazel/results/raw-record-inventory.json`, and the Phase-III README to locate retained raw data. This Git package does not replace the required raw-data handoff. No report or slides are included in Git.
