# Phase I selected timing raw data

This directory contains the one-million-sample compressed raw distributions that directly support the report's compact boundary/evidence panels and selected diagnostics. It includes run metadata, idle/activity evidence, logs and SHA-256 provenance.

Selection policy: All final capacity-boundary, L1-conflict, software-metric and Upgrade-refinement box records; one 56/64/72 B spatial cohort, one D/I pair and one inclusion pressure/control pair per ECE host; all reported L2-conflict records for Crux and Thunderbird.

This is a curated Git copy, not the exhaustive raw-data submission. The full archives retain every configuration, noisy retry and unsuccessful attempt. See `manifest.json` for every selected record, parameter, statistic, qualification and file hash. Verify this directory with `python3 scripts/verify_selected_raw.py data_raw/phase1_timing_selected`.
