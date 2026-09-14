# Competition release handoff

- Repository: https://github.com/NovaCorz/CSC591-Project1
- Frozen release commit: `62d3d2b1b8539303772e2783c575cd0972df3335`
- Freeze tag: `competition-v1`
- Parameter/source freeze timestamp (UTC): `2026-09-14T03:22:58.604722+00:00`
- Commit timestamp: `2026-09-13T23:24:02-04:00` (`2026-09-14T03:24:02Z`)
- GitHub publishing account: `hclee706`; author email: `hclee412@gmail.com`.

The tag identifies the competition code/results snapshot. Later handoff-only commits do not move the tag or change the frozen estimator. Check out the release with `git checkout competition-v1`.

## Included work

- `phase3/`: verified five-generation Hazel timing results, source and Slurm scripts, ECE-only predictions, published comparisons, chronological plots, two cache laws and the 2029 forecast.
- `estimator_validation/`: verified eight-machine software-estimator/PMU comparison and reference-population limitations.
- `competition/`: fixed estimator parameters and source hashes, runnable timing-only entry point, 70-candidate scorecard and citations.

## Verification

Slurm job 824844 verified 648 Phase-III files and 107 estimator-validation files against their manifests. The entry-point smoke collected 6,144 intervals across the three footprints; full mode rejects smoke-sized inputs, and the adapter matches the unchanged original classifier. No official competition score or eligibility decision is claimed. Full measurement results are the preserved earlier experiments, not the entry-point smoke.

## Report and raw-data submission

The separately maintained report records this same release hash. Latest files in the shared workspace are `report/CSC591-Project1-latest.pdf` and `report/phase3-report-source.zip`. The Overleaf ZIP is report source, not the complete Moodle raw-data submission.

Raw-data locations and hashes remain in `estimator_validation/raw-archive-locations.json`, `phase3/hazel/results/raw-record-inventory.json`, `phase3/README.md`, and the original Phase-I archive manifests. Include the required raw data or approved alternate handoff with the final submission. Reports/slides and large raw archives are outside this Git release. The original Hazel prediction timestamps are preserved; this competition freeze does not alter that chronology.
