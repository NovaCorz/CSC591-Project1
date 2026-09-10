#!/bin/bash
# phase2_survey.sh -- run this FIRST on every ECE machine before collecting
# any counters. It only inspects what's available; it does not touch your
# frozen Phase-I benchmark or its results.
#
# Usage: ./phase2_survey.sh > survey_$(hostname).txt

echo "== Host: $(hostname) =="
echo "== Date: $(date -u) =="
echo

echo "-- CPU identification --"
lscpu | grep -E 'Model name|Vendor ID|Architecture|CPU\(s\)|Socket'
echo

echo "-- perf_event_paranoid (lower = more access; -1 is fully open) --"
cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo "file not present"
echo "   If this blocks needed events and you cannot change it yourself,"
echo "   record the exact value/error and contact the TA -- do not change"
echo "   system-wide settings on a shared machine."
echo

echo "-- perf tool present? --"
if command -v perf >/dev/null 2>&1; then
    perf --version
else
    echo "perf not found on PATH"
fi
echo

echo "-- generic hardware events perf reports as supported --"
perf list hw 2>/dev/null
echo

echo "-- cache/TLB/cycle-related events (grep filter) --"
perf list 2>/dev/null | grep -Ei 'cache|L1|LLC|l2|tlb|cycle'
echo

echo "-- quick sanity check: can we open a basic hardware counter at all? --"
perf stat -e cycles -- /bin/true 2>&1 | tail -n 6
echo

echo "== End survey =="