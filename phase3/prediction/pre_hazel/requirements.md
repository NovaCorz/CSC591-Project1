# Prediction requirements captured from the supplied specification

Authority: `PROJECT 1 (3).pdf`, especially sections 8.6 and 9 on pages 18--21.

The prediction/trend stage must:

- use only the eight ECE/lab machines as training observations;
- make and Git-freeze quantitative Hazel predictions before any Hazel cache run;
- sort observations by a consistent processor-generation or microarchitecture introduction-year convention;
- provide a chronological master table and plots for the major measured cache quantities;
- use at least three lab observations for a fitted predictive series;
- show observations with solid markers/lines and only future extrapolation beyond the newest training year with a dashed line;
- show uncertainty and distinguish Intel x86, AMD x86, and Arm/AArch64;
- fit only defensible trends and report a doubling time, slope, step frequency, or constant/non-monotonic result as appropriate;
- preserve the frozen prediction when Hazel observations are later overlaid, without refitting;
- provide two named team laws based only on lab observations, including at least one capacity/scaling quantity and one cost/behavior quantity when supported; and
- later make a quantitative prediction about five years beyond the newest measured system.

The minimum chronological plot list is tracked in `outputs/required-plot-status.csv`.

## Data isolation

No Hazel measurements were used or accessed. The builder reads only the allowlisted Phase-I files listed in `outputs/input-manifest.json`; no Hazel result file is an input.
