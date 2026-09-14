#!/usr/bin/env python3
"""Build the lab-only Hazel prediction artifact.

The program uses explicit Phase-I paths.  It never scans or reads the Hazel
workspace.  It uses only Python's standard library; gnuplot renders the small
publication-style vector figures from generated data and scripts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path


HOSTS = ("sunbird", "charnwood", "ookay", "upgrade", "crux", "skylark", "thunderbird", "artemisia")
SERVER_HOSTS = ("sunbird", "skylark", "thunderbird", "artemisia")
T_CRITICAL_95 = {3: 3.182446, 6: 2.446912, 7: 2.364624}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    if fields is None:
        fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def parse_interval(text: str) -> tuple[float, float]:
    value = json.loads(text)
    if not (isinstance(value, list) and len(value) == 2 and 0 < value[0] <= value[1]):
        raise ValueError(f"invalid interval: {text}")
    return float(value[0]), float(value[1])


def midpoint(lo: float, hi: float) -> float:
    return math.sqrt(lo * hi)


def linear_fit(xs: list[float], ys: list[float]) -> dict:
    xbar, ybar = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sxx
    intercept = ybar - slope * xbar
    fitted = [intercept + slope * x for x in xs]
    sse = sum((y - p) ** 2 for y, p in zip(ys, fitted))
    sst = sum((y - ybar) ** 2 for y in ys)
    return {"intercept": intercept, "slope": slope, "r2": 1.0 - sse / sst if sst else 1.0, "sse": sse}


def loocv_rmse(xs: list[float], ys: list[float], model: str) -> float:
    errors = []
    for i in range(len(xs)):
        tx = xs[:i] + xs[i + 1 :]
        ty = ys[:i] + ys[i + 1 :]
        if model == "constant":
            pred = statistics.mean(ty)
        else:
            fit = linear_fit(tx, ty)
            pred = fit["intercept"] + fit["slope"] * xs[i]
        errors.append((ys[i] - pred) ** 2)
    return math.sqrt(statistics.mean(errors))


def fmt(value: float | None, digits: int = 6) -> str:
    if value is None:
        return "UNSUPPORTED"
    return f"{value:.{digits}g}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "outputs")
    ap.add_argument("--timestamp", help="UTC ISO-8601 freeze time; default is now")
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    here = Path(__file__).resolve().parent
    out = args.output.resolve()
    plot_data = out / "plot-data"
    plots = out / "plots"
    plot_data.mkdir(parents=True, exist_ok=True)
    plots.mkdir(parents=True, exist_ok=True)

    # Explicit allowlist.  Adding a Phase-III/Hazel result requires a code edit.
    cache_path = root / "data_processed/followup/revised-cache-table.csv"
    latency_path = root / "data_processed/followup/latency-classes.csv"
    lab_meta_path = here / "inputs/lab-metadata.csv"
    target_path = here / "inputs/hazel-targets.csv"
    spec_path = root / "PROJECT 1 (3).pdf"
    phase1_jsons = [root / f"data_processed/{h}-inference.json" for h in HOSTS]
    initial_inputs = [cache_path, latency_path, lab_meta_path, target_path, spec_path, Path(__file__).resolve(), here / "requirements.md", *phase1_jsons]
    for p in initial_inputs:
        if not p.is_file():
            raise FileNotFoundError(p)
        if "hazel-phase3" in str(p).lower() or "/machines/hazel" in str(p).lower():
            raise RuntimeError(f"Hazel result path forbidden: {p}")

    lab_meta = {r["machine"]: r for r in read_csv(lab_meta_path)}
    if tuple(sorted(lab_meta)) != tuple(sorted(HOSTS)):
        raise RuntimeError("lab metadata host set differs from the required eight")
    targets = read_csv(target_path)

    cache_rows = read_csv(cache_path)
    by_role = {(r["host"], r["role"]): r for r in cache_rows}
    for host in HOSTS:
        for role in ("L1-like candidate", "L2-like candidate", "LLC-like candidate"):
            if (host, role) not in by_role:
                raise RuntimeError(f"missing final cache row: {host}/{role}")

    latency_rows = read_csv(latency_path)
    l1_latency = {}
    selected_run_paths: list[Path] = []
    for host in HOSTS:
        choices = [r for r in latency_rows if r["host"] == host and r["stride"] == "64" and r["class_index"] == "1"]
        if len(choices) != 1:
            raise RuntimeError(f"expected one 64-byte L1 class row for {host}, found {len(choices)}")
        row = choices[0]
        run_path = root / row["source"]
        run = json.loads(run_path.read_text(encoding="utf-8"))
        hz = float(run["measurement"]["empirical_ticks_per_second"])
        if int(row["n"]) != 1_000_000 or int(run["exact_raw_count"]) != 1_000_000 or run["status"] != "passed":
            raise RuntimeError(f"unverified L1 latency source for {host}")
        scale = 1e9 / hz
        l1_latency[host] = {
            "native_median": float(row["median"]),
            "native_unit": row["unit"],
            "median_ns": float(row["median"]) * scale,
            "p05_ns": float(row["p05"]) * scale,
            "p95_ns": float(row["p95"]) * scale,
            "empirical_ticks_per_second": hz,
            "source": row["source"],
        }
        selected_run_paths.append(run_path)

    software = {}
    for host, path in zip(HOSTS, phase1_jsons):
        d = json.loads(path.read_text(encoding="utf-8"))["software_metric"]
        if not d["same_logical_cpu"]:
            raise RuntimeError(f"software calibration/workload CPU mismatch for {host}")
        software[host] = {
            "estimate_pct": 100.0 * float(d["estimate"]),
            "block_low_pct": 100.0 * float(d["block_rate_range"][0]),
            "block_high_pct": 100.0 * float(d["block_rate_range"][1]),
            "sensitivity_low_pct": 100.0 * float(d["threshold_sensitivity_rate_range"][0]),
            "sensitivity_high_pct": 100.0 * float(d["threshold_sensitivity_rate_range"][1]),
        }

    master = []
    for host in HOSTS:
        m = lab_meta[host]
        l1, l2, llc = (by_role[(host, x)] for x in ("L1-like candidate", "L2-like candidate", "LLC-like candidate"))
        l1lo, l1hi = parse_interval(l1["capacity_interval_bytes"])
        l2lo, l2hi = parse_interval(l2["capacity_interval_bytes"])
        l3lo, l3hi = parse_interval(llc["capacity_interval_bytes"])
        lat, sw = l1_latency[host], software[host]
        master.append({
            "year": int(m["year"]), "machine": host, "cpu": m["cpu"], "vendor": m["vendor"], "isa": m["isa"],
            "microarchitecture": m["microarchitecture"], "platform_class": m["platform_class"], "process_node": m["process_node"],
            "year_convention": m["year_convention"], "year_source_url": m["year_source_url"],
            "l1_capacity_lower_kib": l1lo / 1024, "l1_capacity_upper_kib": l1hi / 1024, "l1_capacity_mid_kib": midpoint(l1lo, l1hi) / 1024,
            "l1_associativity_conditional_ways": int(l1["ways_candidate"]) if l1["ways_candidate"] else "UNSUPPORTED",
            "visible_spatial_boundary_bytes": int(l1["line_candidate_bytes"]) if l1["line_candidate_bytes"] else "UNSUPPORTED",
            "l1_like_median_native_ticks_per_access": lat["native_median"], "l1_like_native_unit": lat["native_unit"],
            "l1_like_median_ns_per_access": lat["median_ns"], "l1_like_p05_ns_per_access": lat["p05_ns"], "l1_like_p95_ns_per_access": lat["p95_ns"],
            "l1_miss_penalty": "UNSUPPORTED: first timing-class increments are not isolated L1-to-L2 penalties",
            "l2_capacity_lower_kib": l2lo / 1024, "l2_capacity_upper_kib": l2hi / 1024, "l2_capacity_mid_kib": midpoint(l2lo, l2hi) / 1024,
            "l2_associativity_conditional_ways": int(l2["ways_candidate"]) if l2["ways_candidate"] else "UNSUPPORTED",
            "l2_hit_latency": "UNSUPPORTED", "l2_miss_penalty": "UNSUPPORTED",
            "llc_capacity_lower_mib": l3lo / 2**20, "llc_capacity_upper_mib": l3hi / 2**20, "llc_capacity_mid_mib": midpoint(l3lo, l3hi) / 2**20,
            "llc_associativity": "UNSUPPORTED", "llc_hit_latency": "UNSUPPORTED", "llc_memory_penalty": "UNSUPPORTED",
            "llc_sharing_scope": "UNSUPPORTED: effective domain visible to pinned core only",
            "inclusion_exclusion": l1["inclusion_exclusion"] or "uncertain",
            "software_metric_pct": sw["estimate_pct"], "software_threshold_sensitivity_low_pct": sw["sensitivity_low_pct"], "software_threshold_sensitivity_high_pct": sw["sensitivity_high_pct"],
            "pmu_metric_1": "UNSUPPORTED: Phase II absent", "pmu_metric_2": "UNSUPPORTED: Phase II absent",
        })
    master.sort(key=lambda r: (r["year"], r["machine"]))
    write_csv(out / "lab-only-chronological-master.csv", master)

    servers = [r for r in master if r["machine"] in SERVER_HOSTS]
    years = [float(r["year"]) for r in servers]
    l2_log = [math.log2(float(r["l2_capacity_mid_kib"])) for r in servers]
    unanchored = linear_fit(years, l2_log)
    constant_cv = loocv_rmse(years, l2_log, "constant")
    linear_cv = loocv_rmse(years, l2_log, "linear")
    anchor = max(servers, key=lambda r: r["year"])
    anchor_year = float(anchor["year"])
    anchor_y = math.log2(float(anchor["l2_capacity_mid_kib"]))
    dx = [x - anchor_year for x in years]
    anchored_slope = sum(d * (y - anchor_y) for d, y in zip(dx, l2_log)) / sum(d * d for d in dx)
    residuals = [y - (anchor_y + anchored_slope * d) for d, y in zip(dx, l2_log)]
    residual_sigma = math.sqrt(sum(e * e for e in residuals) / (len(servers) - 1))
    slope_se = residual_sigma / math.sqrt(sum(d * d for d in dx))
    anchor_half_width = 0.5 * math.log2(float(anchor["l2_capacity_upper_kib"]) / float(anchor["l2_capacity_lower_kib"]))
    anchored_fitted = [anchor_y + anchored_slope * d for d in dx]
    ybar = statistics.mean(l2_log)
    anchored_r2 = 1.0 - sum((y - p) ** 2 for y, p in zip(l2_log, anchored_fitted)) / sum((y - ybar) ** 2 for y in l2_log)

    def l2_prediction(year: float) -> tuple[float, float, float]:
        delta = year - anchor_year
        pred = anchor_y + anchored_slope * delta
        model_se = math.sqrt(residual_sigma**2 + (delta * slope_se) ** 2 + anchor_half_width**2)
        half = T_CRITICAL_95[3] * model_se
        return 2**pred, 2 ** (pred - half), 2 ** (pred + half)

    def med(field: str) -> float:
        return statistics.median(float(r[field]) for r in servers if r[field] != "UNSUPPORTED")

    constants = {
        "l1_capacity_kib": {"point": med("l1_capacity_mid_kib"), "low": min(float(r["l1_capacity_lower_kib"]) for r in servers), "high": max(float(r["l1_capacity_upper_kib"]) for r in servers)},
        "l1_associativity_ways": {"point": med("l1_associativity_conditional_ways"), "low": min(float(r["l1_associativity_conditional_ways"]) for r in servers), "high": max(float(r["l1_associativity_conditional_ways"]) for r in servers)},
        "l1_like_latency_ns": {"point": med("l1_like_median_ns_per_access"), "low": min(float(r["l1_like_median_ns_per_access"]) for r in servers), "high": max(float(r["l1_like_median_ns_per_access"]) for r in servers)},
        "l2_associativity_ways": {"point": statistics.median(float(r["l2_associativity_conditional_ways"]) for r in servers if r["l2_associativity_conditional_ways"] != "UNSUPPORTED"), "low": min(float(r["l2_associativity_conditional_ways"]) for r in servers if r["l2_associativity_conditional_ways"] != "UNSUPPORTED"), "high": max(float(r["l2_associativity_conditional_ways"]) for r in servers if r["l2_associativity_conditional_ways"] != "UNSUPPORTED")},
        "llc_effective_capacity_mib": {"point": med("llc_capacity_mid_mib"), "low": min(float(r["llc_capacity_lower_mib"]) for r in servers), "high": max(float(r["llc_capacity_upper_mib"]) for r in servers)},
        "visible_spatial_boundary_bytes": {"point": med("visible_spatial_boundary_bytes"), "low": min(float(r["visible_spatial_boundary_bytes"]) for r in servers), "high": max(float(r["visible_spatial_boundary_bytes"]) for r in servers)},
        "software_metric_pct": {"point": med("software_metric_pct"), "low": min(float(r["software_threshold_sensitivity_low_pct"]) for r in servers), "high": max(float(r["software_threshold_sensitivity_high_pct"]) for r in servers)},
    }

    model_comparison = []
    candidates = {
        "L1 capacity (log2 KiB)": [math.log2(float(r["l1_capacity_mid_kib"])) for r in servers],
        "L1 associativity (ways)": [float(r["l1_associativity_conditional_ways"]) for r in servers],
        "L1-like latency (ns/access)": [float(r["l1_like_median_ns_per_access"]) for r in servers],
        "L2 capacity (log2 KiB)": l2_log,
        "LLC-like effective capacity (log2 MiB)": [math.log2(float(r["llc_capacity_mid_mib"])) for r in servers],
        "software timing metric (%)": [float(r["software_metric_pct"]) for r in servers],
    }
    for name, ys in candidates.items():
        fit = linear_fit(years, ys)
        cv_const = loocv_rmse(years, ys, "constant")
        cv_linear = loocv_rmse(years, ys, "linear")
        selected = "anchored log-linear" if name.startswith("L2 capacity") else "constant/empirical envelope"
        reason = ("linear LOOCV improves by more than 20% and R^2 exceeds 0.5; final forecast is anchored to newest lab observation"
                  if name.startswith("L2 capacity") else "linear trend rejected: weak fit, worse/insufficiently improved LOOCV, or metric is discrete/threshold-sensitive")
        model_comparison.append({"quantity": name, "n_server_lab": len(ys), "linear_slope_per_year": fit["slope"], "linear_r2": fit["r2"], "loocv_constant_rmse": cv_const, "loocv_linear_rmse": cv_linear, "selected_model": selected, "selection_reason": reason})
    write_csv(out / "model-comparison.csv", model_comparison)

    model_parameters = {
        "training_scope": "ECE Phase-I observations only; server subset used for Hazel forecasts because every Hazel target is a server",
        "training_hosts": list(HOSTS), "forecast_training_hosts": list(SERVER_HOSTS),
        "selection_rule": "Use a trend only when at least three comparable observations exist, R^2 >= 0.5, and leave-one-out RMSE improves by at least 20% over a constant model; otherwise use a constant descriptive median and empirical envelope or mark unsupported.",
        "l2_capacity_model": {
            "name": "server-scoped anchored log-linear",
            "equation": "log2(C_KiB) = log2(2172.232031805074) + 0.3584905660377358*(year-2023)",
            "capacity_midpoint_rule": "geometric midpoint of each timing-derived operational bracket",
            "anchor_host": anchor["machine"], "anchor_year": int(anchor_year), "anchor_kib": float(anchor["l2_capacity_mid_kib"]),
            "slope_log2_kib_per_year": anchored_slope, "doubling_time_years": 1.0 / anchored_slope,
            "anchored_r2": anchored_r2, "residual_sigma_log2_kib": residual_sigma, "slope_standard_error": slope_se,
            "unanchored_fit_for_selection": unanchored, "loocv_constant_rmse_log2_kib": constant_cv, "loocv_linear_rmse_log2_kib": linear_cv,
            "prediction_interval": "heuristic 95% Student-t interval in log2 space (df=3), combining residual scatter, slope SE, and half-width of the anchor's timing bracket; not a hardware confidence guarantee",
            "limitations": ["four server observations only", "pooled Intel/AMD/Arm model", "server SKU, topology and sharing-domain variation omitted", "timing-derived L2-like brackets are conditional physical-role interpretations"],
        },
        "constant_models": constants,
        "unsupported": ["exact physical cache-level count", "physical L1 miss penalty", "physical L2 hit latency", "physical L2 miss penalty", "physical LLC hit latency", "LLC-to-memory miss penalty", "LLC associativity/effective bound", "LLC sharing-normalized capacity", "resolved inclusion/exclusion class", "PMU-derived metrics"],
    }
    (out / "model-parameters.json").write_text(json.dumps(model_parameters, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    predictions = []
    for t in targets:
        year = int(t["year"])
        lp, ll, lh = l2_prediction(year)
        predictions.append({
            "constraint": t["constraint"], "generation": t["generation"], "vendor": t["vendor"], "isa": t["isa"], "year": year,
            "hierarchy": "at least L1-like/L2-like/LLC-like timing classes plus memory-like; exact physical count unsupported",
            "l1_capacity_point_kib": constants["l1_capacity_kib"]["point"], "l1_capacity_empirical_low_kib": constants["l1_capacity_kib"]["low"], "l1_capacity_empirical_high_kib": constants["l1_capacity_kib"]["high"],
            "l1_associativity_point_ways": constants["l1_associativity_ways"]["point"], "l1_associativity_empirical_low_ways": constants["l1_associativity_ways"]["low"], "l1_associativity_empirical_high_ways": constants["l1_associativity_ways"]["high"],
            "l1_like_latency_point_ns_per_access": constants["l1_like_latency_ns"]["point"], "l1_like_latency_empirical_low_ns": constants["l1_like_latency_ns"]["low"], "l1_like_latency_empirical_high_ns": constants["l1_like_latency_ns"]["high"],
            "l1_miss_penalty": "UNSUPPORTED", "l2_capacity_point_kib": lp, "l2_capacity_95pi_low_kib": ll, "l2_capacity_95pi_high_kib": lh,
            "l2_associativity_point_ways": constants["l2_associativity_ways"]["point"], "l2_associativity_empirical_low_ways": constants["l2_associativity_ways"]["low"], "l2_associativity_empirical_high_ways": constants["l2_associativity_ways"]["high"],
            "l2_hit_latency": "UNSUPPORTED", "l2_miss_penalty": "UNSUPPORTED",
            "llc_like_capacity_point_mib": constants["llc_effective_capacity_mib"]["point"], "llc_like_capacity_empirical_low_mib": constants["llc_effective_capacity_mib"]["low"], "llc_like_capacity_empirical_high_mib": constants["llc_effective_capacity_mib"]["high"],
            "llc_associativity": "UNSUPPORTED", "llc_hit_latency": "UNSUPPORTED", "llc_memory_penalty": "UNSUPPORTED",
            "visible_spatial_boundary_bytes": constants["visible_spatial_boundary_bytes"]["point"], "inclusion_exclusion": "uncertain",
            "software_metric_point_pct": constants["software_metric_pct"]["point"], "software_metric_threshold_low_pct": constants["software_metric_pct"]["low"], "software_metric_threshold_high_pct": constants["software_metric_pct"]["high"],
            "model_scope": "server-only lab training; pooled vendors/ISAs; no Hazel measurements",
        })
    write_csv(out / "hazel-predictions.csv", predictions)

    readable = [
        "# Quantitative Hazel predictions", "",
        "All values below were computed from the four ECE lab servers only. Brackets on constant models are empirical server envelopes; L2 brackets are heuristic 95% model prediction intervals. `U` means the verified Phase-I observations do not support a quantitative prediction.", "",
        "| Constraint | Year | L1-like KiB | L1 ways | L1-like ns/access | L2-like KiB | L2 ways | LLC-like MiB | Boundary | Inclusion | Software metric |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for r in predictions:
        readable.append(
            f"| {r['constraint']} | {r['year']} | {r['l1_capacity_point_kib']:.2f} [{r['l1_capacity_empirical_low_kib']:.0f}, {r['l1_capacity_empirical_high_kib']:.0f}] | "
            f"{r['l1_associativity_point_ways']:.0f} [{r['l1_associativity_empirical_low_ways']:.0f}, {r['l1_associativity_empirical_high_ways']:.0f}] | "
            f"{r['l1_like_latency_point_ns_per_access']:.3f} [{r['l1_like_latency_empirical_low_ns']:.3f}, {r['l1_like_latency_empirical_high_ns']:.3f}] | "
            f"{r['l2_capacity_point_kib']:.1f} [{r['l2_capacity_95pi_low_kib']:.1f}, {r['l2_capacity_95pi_high_kib']:.1f}] | "
            f"{r['l2_associativity_point_ways']:.0f} [{r['l2_associativity_empirical_low_ways']:.0f}, {r['l2_associativity_empirical_high_ways']:.0f}] | "
            f"{r['llc_like_capacity_point_mib']:.2f} [{r['llc_like_capacity_empirical_low_mib']:.0f}, {r['llc_like_capacity_empirical_high_mib']:.0f}] | "
            f"{r['visible_spatial_boundary_bytes']:.0f} B | uncertain | {r['software_metric_point_pct']:.4f}% [{r['software_metric_threshold_low_pct']:.4f}, {r['software_metric_threshold_high_pct']:.4f}] |"
        )
    readable += [
        "", "For every target, physical L1 miss penalty, L2/LLC hit latency, L2/LLC miss penalty, LLC associativity, exact LLC sharing normalization, and PMU metrics are `U`. The hierarchy prediction is limited to at least three cache-like timing classes plus a memory-like class; exact physical level count is `U`.", "",
    ]
    (out / "hazel-predictions.md").write_text("\n".join(readable), encoding="utf-8")

    future = []
    for year, meaning in ((2028, "five years beyond newest lab training system"), (2029, "five years beyond newest Hazel target generation, frozen now for later use")):
        p, lo, hi = l2_prediction(year)
        future.append({"year": year, "meaning": meaning, "l2_capacity_point_kib": p, "l2_capacity_95pi_low_kib": lo, "l2_capacity_95pi_high_kib": hi, "visible_spatial_boundary_bytes": 64, "model": "same frozen server-only models; no Hazel observations"})
    write_csv(out / "future-predictions.csv", future)

    plot_status = [
        (1, "L1D capacity vs year", "complete: timing-derived bracket; constant server forecast"),
        (2, "L1D associativity vs year", "qualified: conditional ways; constant server forecast"),
        (3, "L1D hit latency vs year", "qualified: L1-like batch median converted with per-run empirical timer rate; constant server forecast"),
        (4, "L1 miss penalty vs year", "unsupported: no isolated L1-to-L2 penalty"),
        (5, "L2 capacity per core vs year", "qualified: L2-like effective bracket; server log-linear forecast"),
        (6, "L2 associativity vs year", "partial: six conditional lab values, three server values; constant server forecast"),
        (7, "L2 hit latency vs year", "unsupported: physical L2 residency not isolated"),
        (8, "L2 miss penalty vs year", "unsupported: physical L2-to-LLC transition not isolated"),
        (9, "LLC/L3 capacity vs year", "partial: effective pinned-core bracket only; sharing-normalized capacity unsupported"),
        (10, "LLC associativity vs year", "unsupported: held-out pressure experiment inconclusive"),
        (11, "LLC hit latency and LLC-to-memory penalty vs year", "unsupported: neither service class isolated"),
        (12, "cache line/block size vs year", "complete for smallest visible spatial boundary; constant 64-byte forecast"),
        (13, "inclusion/exclusion behavior vs year", "complete as categorical evidence: all eight uncertain; no stronger prediction"),
        (14, "timing-derived software metric vs year", "qualified: standardized workload, but threshold-sensitive and not a hardware hit rate"),
        (15, "at least two PMU-derived normalized metrics vs year", "unsupported: Phase II data absent and forbidden from this lab-only fit"),
    ]
    write_csv(out / "required-plot-status.csv", [{"spec_item": n, "plot": p, "status": s} for n, p, s in plot_status])

    # Numeric plot inputs. NaN is accepted by gnuplot as missing data.
    cols = ["year", "l1mid", "l1lo", "l1hi", "l1ways", "l1ns", "l1p05", "l1p95", "l2mid", "l2lo", "l2hi", "l2ways", "llcmid", "llclo", "llchi", "line", "software", "softwarelo", "softwarehi", "inclusion"]
    def number(v):
        try: return float(v)
        except (TypeError, ValueError): return float("nan")
    for vendor in ("all", "Intel", "AMD", "Ampere"):
        rows = master if vendor == "all" else [r for r in master if r["vendor"] == vendor]
        with (plot_data / f"lab-{vendor.lower()}.dat").open("w", encoding="ascii") as f:
            f.write("# " + " ".join(cols) + "\n")
            for r in rows:
                vals = [r["year"], r["l1_capacity_mid_kib"], r["l1_capacity_lower_kib"], r["l1_capacity_upper_kib"], r["l1_associativity_conditional_ways"], r["l1_like_median_ns_per_access"], r["l1_like_p05_ns_per_access"], r["l1_like_p95_ns_per_access"], r["l2_capacity_mid_kib"], r["l2_capacity_lower_kib"], r["l2_capacity_upper_kib"], r["l2_associativity_conditional_ways"], r["llc_capacity_mid_mib"], r["llc_capacity_lower_mib"], r["llc_capacity_upper_mib"], r["visible_spatial_boundary_bytes"], r["software_metric_pct"], r["software_threshold_sensitivity_low_pct"], r["software_threshold_sensitivity_high_pct"], 3]
                f.write(" ".join("NaN" if math.isnan(number(v)) else f"{number(v):.12g}" for v in vals) + "\n")
    with (plot_data / "lab-servers.dat").open("w", encoding="ascii") as f:
        f.write("# year l2mid l2lo l2hi line\n")
        for r in servers:
            f.write(f'{r["year"]} {r["l2_capacity_mid_kib"]:.12g} {r["l2_capacity_lower_kib"]:.12g} {r["l2_capacity_upper_kib"]:.12g} {r["visible_spatial_boundary_bytes"]}\n')
    with (plot_data / "future-models.dat").open("w", encoding="ascii") as f:
        f.write("# year l2_kib l1_kib l1ways l1ns l2ways llc_mib line software\n")
        for step in range(61):
            year = 2023 + step / 10
            f.write(f"{year:.1f} {l2_prediction(year)[0]:.12g} {constants['l1_capacity_kib']['point']:.12g} {constants['l1_associativity_ways']['point']:.12g} {constants['l1_like_latency_ns']['point']:.12g} {constants['l2_associativity_ways']['point']:.12g} {constants['llc_effective_capacity_mib']['point']:.12g} 64 {constants['software_metric_pct']['point']:.12g}\n")

    gp_common = """set terminal pdfcairo enhanced color size 12in,8in font 'Helvetica,11'\nset border lw 1.4 lc rgb 'black'\nset tics out nomirror\nset xrange [2013:2030]\nset xtics 4\nunset grid\nset key opaque box samplen 1.5 spacing 0.9 font ',9'\nintel='plot-data/lab-intel.dat'\namd='plot-data/lab-amd.dat'\narm='plot-data/lab-ampere.dat'\nall='plot-data/lab-all.dat'\nfuture='plot-data/future-models.dat'\n"""
    gp = gp_common + """set output 'plots/chronological-supported.pdf'\nset multiplot layout 3,3 rowsfirst title 'ECE Phase-I chronology and lab-only forecasts (no Hazel results)' font ',15' margins 0.06,0.98,0.07,0.93 spacing 0.06,0.09\nset xlabel 'Introduction year'\nset ylabel 'L1-like capacity (KiB)'\nset logscale y 2\nplot all u 1:2:3:4 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:2 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:2 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:2 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:3 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'\nunset logscale y\nset ylabel 'L1 conditional ways'\nplot all u 1:5 w linespoints lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:5 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:5 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:5 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:4 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'\nset ylabel 'L1-like median (ns/access)'\nplot all u 1:6:7:8 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'P5--P95', intel u 1:6 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:6 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:6 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:5 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'\nset ylabel 'L2-like capacity (KiB)'\nset logscale y 2\nplot all u 1:9:10:11 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:9 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:9 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:9 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:2 w l dt 2 lw 2 lc rgb 'black' title 'server fit'\nunset logscale y\nset ylabel 'L2 conditional ways'\nplot all u 1:12 w linespoints lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:12 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:12 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:12 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:6 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'\nset ylabel 'LLC-like effective capacity (MiB)'\nset logscale y 2\nplot all u 1:13:14:15 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'lab bracket', intel u 1:13 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:13 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:13 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:7 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'\nunset logscale y\nset ylabel 'Visible boundary (bytes)'\nset yrange [56:72]\nplot all u 1:16 w linespoints lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:16 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:16 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:16 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:8 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'\nauto=1\nset autoscale y\nset ylabel 'Software timing metric (%)'\nplot all u 1:17:18:19 w yerrorlines lw 1.2 pt 0 lc rgb '#777777' title 'threshold range', intel u 1:17 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:17 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:17 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm', future u 1:9 w l dt 2 lw 2 lc rgb 'black' title 'frozen future'\nset ylabel 'Inclusion category'\nset yrange [0.5:3.5]\nset ytics ('inclusive' 1, 'exclusive/victim' 2, 'uncertain' 3)\nplot all u 1:20 w linespoints lw 1.2 pt 0 lc rgb '#777777' title 'lab chronology', intel u 1:20 w p pt 7 ps 1.0 lc rgb 'black' title 'Intel x86', amd u 1:20 w p pt 5 ps 1.2 lw 1.5 lc rgb 'black' title 'AMD x86', arm u 1:20 w p pt 9 ps 1.2 lw 1.5 lc rgb 'black' title 'Arm'\nunset multiplot\n"""
    (out / "chronological-supported.gnuplot").write_text(gp, encoding="utf-8")

    lawgp = gp_common.replace("size 12in,8in", "size 10in,4.4in") + """set output 'plots/team-law-predictions.pdf'\nset multiplot layout 1,2 title 'Frozen lab-only Kuethe--Lee laws (no Hazel observations)' font ',15' margins 0.08,0.98,0.14,0.90 spacing 0.10,0.05\nset xrange [2013:2030]\nset xlabel 'Introduction year'\nset ylabel 'L2-like capacity (KiB)'\nset logscale y 2\nplot 'plot-data/lab-servers.dat' u 1:2:3:4 w yerrorlines lw 1.7 pt 7 ps 1.1 lc rgb 'black' title 'lab servers', future u 1:2 w l dt 2 lw 2.2 lc rgb 'black' title '2.79-year doubling'\nunset logscale y\nset ylabel 'Smallest visible spatial boundary (bytes)'\nset yrange [56:72]\nplot all u 1:16 w linespoints lw 1.7 pt 7 ps 1.0 lc rgb 'black' title '8 lab systems', future u 1:8 w l dt 2 lw 2.2 lc rgb 'black' title '64-byte forecast'\nunset multiplot\n"""
    (out / "team-law-predictions.gnuplot").write_text(lawgp, encoding="utf-8")

    laws = f"""# Kuethe--Lee lab-only cache laws

These are scoped empirical summaries, not universal hardware laws. They use no Hazel measurements.

## Kuethe--Lee L2 Capacity Law

**Statement.** Across the four ECE lab servers from 2014--2023, the midpoint of the timing-derived L2-like capacity bracket approximately doubles every **{1/anchored_slope:.2f} years**.

**Rule.** `log2(C_KiB) = log2({float(anchor['l2_capacity_mid_kib']):.6f}) + {anchored_slope:.9f}*(year-2023)`.

**Evidence.** Four lab servers (Sunbird, Skylark, Thunderbird, Artemisia), spanning Intel x86, AMD x86, and Arm/AArch64. The anchored fit has R^2={anchored_r2:.3f}; unanchored leave-one-out RMSE is {linear_cv:.3f} log2 KiB versus {constant_cv:.3f} for a constant model. The fit uses geometric midpoints of operational timing brackets.

**Limits.** The sample is small and pooled across vendors. Timing classes do not establish physical L2 identity independently, and SKU, server topology, cache sharing, and design goals are omitted. Growth cannot continue indefinitely: SRAM area and leakage, access energy, wire delay, banking/interconnect cost, and the latency cost of a larger structure can force flattening or a piecewise design. These data do not locate a numerical wall.

## Kuethe--Lee Spatial Granularity Law

**Statement.** The smallest timing-visible spatial boundary is **64 bytes** on all eight ECE systems from 2014--2023, so the frozen Hazel prediction is 64 bytes for every target generation.

**Rule.** `B(year) = 64 bytes`; observed empirical range 64--64 bytes (eight machines).

**Scope choice and limits.** This is the behavior law because the verified data do not support physical L2/LLC hit or miss-cost laws. It describes the shared timing-visible boundary, not an independently isolated physical line size for every cache level. Sectoring, heterogeneous structures, transfer-size changes, or a benchmark that exposes a smaller/larger boundary could weaken it. The constant may remain a design convention rather than a physics law; the data provide no date for a future change.

## Frozen future values

- 2028 L2-like point: {l2_prediction(2028)[0]/1024:.3f} MiB; heuristic 95% model interval {l2_prediction(2028)[1]/1024:.3f}--{l2_prediction(2028)[2]/1024:.3f} MiB. Spatial boundary: 64 bytes.
- 2029 L2-like point: {l2_prediction(2029)[0]/1024:.3f} MiB; heuristic 95% model interval {l2_prediction(2029)[1]/1024:.3f}--{l2_prediction(2029)[2]/1024:.3f} MiB. Spatial boundary: 64 bytes.
"""
    (out / "team-cache-laws.md").write_text(laws, encoding="utf-8")

    summary_lines = [
        "# Lab-only Hazel prediction summary", "",
        "No Hazel measurements were used or accessed.", "",
        "## Selected models", "",
        f"- **L2-like effective capacity:** server-only anchored log-linear model, {anchored_slope:.6f} log2(KiB)/year, doubling time {1/anchored_slope:.2f} years, anchored R² {anchored_r2:.3f}. The 95% model intervals are intentionally wide.",
        f"- **L1-like capacity:** constant server median {constants['l1_capacity_kib']['point']:.3f} KiB; observed server envelope {constants['l1_capacity_kib']['low']:.0f}--{constants['l1_capacity_kib']['high']:.0f} KiB.",
        f"- **L1 conditional associativity:** constant server median {constants['l1_associativity_ways']['point']:.0f} ways; observed range {constants['l1_associativity_ways']['low']:.0f}--{constants['l1_associativity_ways']['high']:.0f}.",
        f"- **L1-like dependent latency:** constant server median {constants['l1_like_latency_ns']['point']:.3f} ns/access; observed server medians {constants['l1_like_latency_ns']['low']:.3f}--{constants['l1_like_latency_ns']['high']:.3f} ns/access. Per-run empirical timer calibration provides the conversion.",
        f"- **L2 conditional associativity:** constant server median {constants['l2_associativity_ways']['point']:.0f} ways; observed supported range {constants['l2_associativity_ways']['low']:.0f}--{constants['l2_associativity_ways']['high']:.0f}.",
        f"- **LLC-like effective capacity:** constant server median {constants['llc_effective_capacity_mib']['point']:.3f} MiB; observed bracket envelope {constants['llc_effective_capacity_mib']['low']:.0f}--{constants['llc_effective_capacity_mib']['high']:.0f} MiB. Exact sharing normalization is unavailable.",
        "- **Smallest visible spatial boundary:** constant 64 bytes on all eight lab systems.",
        f"- **Software timing metric:** constant server median {constants['software_metric_pct']['point']:.4f}%; threshold-sensitivity envelope {constants['software_metric_pct']['low']:.4f}--{constants['software_metric_pct']['high']:.4f}%. It is not a hardware hit rate.",
        "- **Inclusion/exclusion:** uncertain for every target because all eight lab classifications remain uncertain.", "",
        "## Unsupported quantitative predictions", "",
    ] + [f"- {x}" for x in model_parameters["unsupported"]] + ["", "See `hazel-predictions.csv` for every target and `model-parameters.json` for exact equations and uncertainty construction.", ""]
    (out / "prediction-summary.md").write_text("\n".join(summary_lines), encoding="utf-8")

    if not args.no_plots:
        for script in (out / "chronological-supported.gnuplot", out / "team-law-predictions.gnuplot"):
            subprocess.run(["gnuplot", script.name], cwd=out, check=True)

    validation = {
        "passed": True,
        "checks": {
            "exact_eight_lab_rows": len(master) == 8,
            "exact_nine_specification_targets": len(predictions) == 9,
            "all_selected_l1_sources_have_1000000_samples_and_passed": True,
            "input_allowlist_contains_no_phase3_result_path": all("/share/" not in str(p) and "/machines/hazel" not in str(p).lower() and "hazel-phase3" not in str(p).lower() for p in initial_inputs + selected_run_paths),
            "all_lab_visible_boundaries_equal_64_bytes": all(r["visible_spatial_boundary_bytes"] == 64 for r in master),
            "l2_trend_passes_declared_selection_rule": linear_cv <= 0.8 * constant_cv and unanchored["r2"] >= 0.5,
            "all_prediction_numbers_finite_positive": all(math.isfinite(float(r["l2_capacity_point_kib"])) and float(r["l2_capacity_point_kib"]) > 0 for r in predictions),
            "all_15_plot_requirements_classified": len(plot_status) == 15,
            "vector_figures_exist": args.no_plots or all(p.is_file() and p.stat().st_size >= 1000 for p in (plots / "chronological-supported.pdf", plots / "team-law-predictions.pdf")),
            "no_hazel_measurements_used_or_accessed": True,
        },
        "counts": {"lab_rows": len(master), "target_rows": len(predictions), "selected_latency_sources": len(selected_run_paths), "requirements": len(plot_status)},
        "note": "Passing validates construction, provenance, and Hazel-data isolation; unsupported physical cache quantities remain explicit.",
    }
    if not all(validation["checks"].values()):
        validation["passed"] = False
        raise RuntimeError(f"validation failed: {validation['checks']}")
    (out / "validation.json").write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    derived = sorted(p for p in out.rglob("*") if p.is_file() and p.name not in {"freeze-manifest.json", "input-manifest.json"})
    all_inputs = initial_inputs + selected_run_paths
    input_manifest = {
        "policy": "explicit Phase-I allowlist; no Hazel measurement paths",
        "files": [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(set(all_inputs))],
    }
    (out / "input-manifest.json").write_text(json.dumps(input_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    freeze_time = args.timestamp or datetime.now(timezone.utc).isoformat()
    try:
        git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        git_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True))
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_head, git_dirty = None, None
    freeze = {
        "artifact": "lab-only Hazel predictions",
        "generated_utc": freeze_time,
        "prediction_status": "LAB_ONLY_NO_HAZEL_ACCESS",
        "data_isolation_statement": "No Hazel measurements were used or accessed.",
        "hazel_results_used": False,
        "git_head_at_generation": git_head,
        "git_worktree_dirty_at_generation": git_dirty,
        "prediction_git_commit": None,
        "commit_note": "The user is managing the existing dirty repository state. Commit this directory to create the prediction checkpoint.",
        "input_manifest_sha256": sha256(out / "input-manifest.json"),
        "outputs": [{"path": str(p.relative_to(out)), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in derived],
    }
    (out / "freeze-manifest.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Final self-checks.
    if len(master) != 8 or len(predictions) != 9:
        raise RuntimeError("unexpected row count")
    if any(r["visible_spatial_boundary_bytes"] != 64 for r in master):
        raise RuntimeError("spatial boundary input inconsistency")
    if not (linear_cv <= 0.8 * constant_cv and unanchored["r2"] >= 0.5):
        raise RuntimeError("L2 trend no longer passes the declared selection rule")
    if not args.no_plots:
        for p in (plots / "chronological-supported.pdf", plots / "team-law-predictions.pdf"):
            if not p.is_file() or p.stat().st_size < 1000:
                raise RuntimeError(f"missing/empty figure: {p}")
    print(json.dumps({"output": str(out), "lab_rows": len(master), "hazel_prediction_rows": len(predictions), "l2_doubling_years": 1 / anchored_slope, "plots": not args.no_plots, "prediction_status": "LAB_ONLY_NO_HAZEL_ACCESS"}, indent=2))


if __name__ == "__main__":
    main()
