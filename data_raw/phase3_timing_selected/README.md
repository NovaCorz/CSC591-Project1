# Phase III selected timing raw data

This directory contains the one-million-sample compressed raw distributions that directly support the report's compact boundary/evidence panels and selected diagnostics. It includes run metadata, idle/activity evidence, logs and SHA-256 provenance.

Selection policy: All Hazel report box-panel records for capacity, spatial, conflict and inclusion; all three software-metric calibration/target records and one D/I pair per generation.

This is a curated Git copy, not the exhaustive raw-data submission. The full archives retain every configuration, noisy retry and unsuccessful attempt. See `manifest.json` for every selected record, parameter, statistic, qualification and file hash. Verify this directory with `python3 scripts/verify_selected_raw.py data_raw/phase3_timing_selected`.
